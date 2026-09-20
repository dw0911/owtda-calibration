#!/usr/bin/env python3
"""Generate the reproducibility manifests:

* ``reproducibility/SEED_MANIFEST.csv``    - flat view of ``governance/SEED_REGISTRY_v1.0.json``
* ``reproducibility/ARTIFACT_INDEX.csv``   - every registered figure/table artifact with its
  generator, inputs and hashes (from the ``*.meta.json`` files, never hand-typed)
* ``reproducibility/FORMAL_MANIFEST.json`` - freeze identity, sealed counts, ledger hashes and
  seal objects for the formal H0/H1 evidence
* ``reproducibility/EXPECTED_OUTPUTS.json``- the counts and headline values a reviewer should see

Run after any change to the canonical results, artifacts or governance registries.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEED_REGISTRY = REPO / "governance" / "SEED_REGISTRY_v1.0.json"
FREEZE_MANIFEST = REPO / "governance" / "FREEZE_MANIFEST.json"
OUT = REPO / "reproducibility"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def first_list_of_dicts(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for value in obj.values():
            found = first_list_of_dicts(value)
            if found:
                return found
    return None


def flat(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def write_seed_manifest() -> int:
    if not SEED_REGISTRY.exists():
        print("seed registry missing; skipped")
        return 0
    entries = first_list_of_dicts(load(SEED_REGISTRY))
    if not entries:
        print("seed registry has no entry list; skipped")
        return 0
    columns: list[str] = []
    for entry in entries:
        for key in entry:
            if key not in columns:
                columns.append(key)
    target = OUT / "SEED_MANIFEST.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*columns, "git_commit"])
        writer.writeheader()
        commit = _git_commit()
        for entry in entries:
            row = {key: flat(entry.get(key)) for key in columns}
            row["git_commit"] = commit
            writer.writerow(row)
    print(f"wrote reproducibility/SEED_MANIFEST.csv ({len(entries)} entries)")
    return len(entries)


def _git_commit() -> str:
    import subprocess

    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNCOMMITTED_OR_NO_GIT"


def write_artifact_index() -> int:
    rows = []
    for meta_path in sorted(list((REPO / "artifacts" / "figures").rglob("*.meta.json"))
                            + list((REPO / "artifacts" / "tables").glob("*.meta.json"))):
        meta = load(meta_path)
        base = meta_path.name.replace(".meta.json", "")
        kind = str(meta.get("kind", "")).lower()
        outputs = sorted(p for p in meta_path.parent.glob(base + ".*") if p.name != meta_path.name)
        primary = next((p for p in outputs if p.suffix in (".pdf", ".csv", ".json")), None)
        generator = "paper/scripts/make_figures.py" if kind == "figure" else "audit/build_corrected_assets.py"
        rows.append(
            {
                "artifact_id": base,
                "paper_reference": meta.get("paper_reference", ""),
                "description": kind or meta_path.name,
                "source_data": ";".join(sorted((meta.get("input_sha256") or {}).keys())),
                "generation_script": generator + " (inferred from kind)",
                "config": "",
                "output_path": str(primary.relative_to(REPO).as_posix()) if primary else "",
                "input_sha256": ";".join(f"{k}={v}" for k, v in sorted((meta.get("input_sha256") or {}).items())),
                "script_sha256": str(meta.get("script_sha256", "")),
                "output_sha256": sha256_of(primary) if primary else "",
            }
        )
    target = OUT / "ARTIFACT_INDEX.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote reproducibility/ARTIFACT_INDEX.csv ({len(rows)} artifacts)")
    return len(rows)


def write_formal_manifest() -> None:
    ledgers = load(REPO / "data" / "manifests" / "formal_ledgers.json")
    freeze = load(FREEZE_MANIFEST) if FREEZE_MANIFEST.exists() else {}
    seals = {}
    for phase in ("H0_NULL", "H1_ALT"):
        entry = {}
        for name in ("RUN_SEAL.json", "PHASE_SEAL.json"):
            path = REPO / "artifacts" / "seals" / phase / name
            if path.exists():
                entry[name] = {
                    "path": str(path.relative_to(REPO).as_posix()),
                    "file_sha256": sha256_of(path),
                    "recorded": {k: v for k, v in load(path).items() if "hash" in k.lower()},
                }
        seals[phase] = entry
    manifest = {
        "release": "v1.0.0-paper",
        "git_commit": _git_commit(),
        "freeze": {
            "freeze_id": freeze.get("freeze_id"),
            "evidence_generation_id": freeze.get("evidence_generation_id", "G01"),
            "source_tree_scope": freeze.get("source_tree_scope"),
            "note": "source_tree_hash recorded by FREEZE_MANIFEST refers to an earlier revision; the published src/ is the later R4/R5 repair revision (see FAILURE_POLICY.md disclosures).",
        },
        "phases": ledgers["phases"],
        "totals": ledgers["totals"],
        "seals": seals,
        "paper_pdf_sha256": sha256_of(REPO / "paper" / "main.pdf"),
        "canonical_results_sha256": {
            path.relative_to(REPO).as_posix(): sha256_of(path)
            for path in sorted((REPO / "results" / "canonical").rglob("*.json"))
        },
        "code_doi": None,
        "data_doi": None,
        "paper_version": "2026-09 (R5-paper snapshot)",
    }
    (OUT / "FORMAL_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote reproducibility/FORMAL_MANIFEST.json")


def write_expected_outputs() -> None:
    summary = load(REPO / "results" / "bootstrap" / "P1_P3_BOOTSTRAP_SUMMARY.json")
    expected = {
        "level1_quick": "python scripts/verify_release.py --level quick  ->  all checks PASS",
        "counts": {"h0_units": 112, "h0_cells": 28, "h1_cell_features": 16,
                   "h0_evaluation_rows": 280000, "h1_evaluation_rows": 51200},
        "primary_contrasts": {key: {"p_raw": row["p_raw_one_sided"], "p_holm": row["p_holm"],
                                    "ci95_basic": row["ci95_basic"]}
                              for key, row in summary["results"].items()},
        "required_files": [
            "results/canonical/H0_POINTWISE.json",
            "results/canonical/H0_PRIMARY_CONTRASTS.json",
            "results/canonical/H1_REANALYSIS.json",
            "results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json",
            "artifacts/tables/H0_ALL_112.csv",
            "artifacts/tables/H1_ALL_16_GEOMETRY_COMPLETE.csv",
            "artifacts/figures/Figure1_method_schematic.pdf",
            "artifacts/figures/Figure5_H1_power_and_difference.pdf",
            "paper/main.pdf",
            "reproducibility/SHA256SUMS",
        ],
    }
    (OUT / "EXPECTED_OUTPUTS.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("wrote reproducibility/EXPECTED_OUTPUTS.json")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write_seed_manifest()
    write_artifact_index()
    write_formal_manifest()
    write_expected_outputs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
