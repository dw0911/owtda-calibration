#!/usr/bin/env python3
"""Rebuild the registered P1-P3 primary-contrast inference from the actual draws.

Registered rule (see PAPER/SAP and the R1 audit):
  * unstudentized cluster-bootstrap, two DGP strata sampled independently;
  * one-sided tail count ``extreme = #{d : (d - estimate) >= (estimate - threshold)}``;
  * Monte Carlo p value ``p = (extreme + 1) / (B + 1)`` (the added one forbids p = 0);
  * basic (nearest-rank) 95% interval ``[2*est - q_0.975, 2*est - q_0.025]``;
  * Holm step-down across P1-P3.

Sources of truth (never hand-copied):
  * draws           ``governance/actual_primary_draws.json``   (P1/P2/P3, 10,000 each)
  * point estimates ``results/canonical/H0_PRIMARY_CONTRASTS.json`` (also carries thresholds)

Outputs (results/bootstrap/, see REPRODUCIBILITY.md level 2):
  * ``P1_P3_DRAWS.npz``               float64 arrays P1/P2/P3
  * ``P1_P3_BOOTSTRAP_SUMMARY.json``  point estimate, threshold, tail count, p, Holm, CI
  * ``P1_P3_DRAWS.meta.json``         hashes, rule, sampling unit, git commit

Usage:
  python scripts/bootstrap_primary_contrasts.py                 # (re)generate
  python scripts/bootstrap_primary_contrasts.py --check         # verify committed outputs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DRAWS = REPO / "governance" / "actual_primary_draws.json"
DEFAULT_CONTRASTS = REPO / "results" / "canonical" / "H0_PRIMARY_CONTRASTS.json"
DEFAULT_OUT = REPO / "results" / "bootstrap"

CONTRASTS = ("P1", "P2", "P3")
EXPECTED_DRAWS = 10000
SAMPLING_UNIT = "DGP-master-cluster"
STRATIFICATION = "two registry DGPs sampled independently"
CI_METHOD = "basic interval, nearest-rank"
PVALUE_RULE = "(tail_count + 1) / (B + 1)"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - commit is provenance, never a hard requirement
        return "UNCOMMITTED_OR_NO_GIT"


def nearest_rank(values: np.ndarray, probability: float) -> float:
    ordered = np.sort(values)
    return float(ordered[math.ceil(probability * len(ordered)) - 1])


def finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: finite number required")
    return float(value)


def primary_from_draws(estimate: float, threshold: float, draws: list[float]) -> dict:
    if len(draws) != EXPECTED_DRAWS:
        raise ValueError(f"expected exactly {EXPECTED_DRAWS} registered draws, got {len(draws)}")
    values = np.asarray([finite(v, "draw") for v in draws], dtype=np.float64)
    extreme = int(np.count_nonzero((values - estimate) >= (estimate - threshold)))
    return {
        "point_estimate": estimate,
        "threshold": threshold,
        "tail_count": extreme,
        "p_raw_one_sided": (extreme + 1) / (len(values) + 1),
        "ci95_basic": [2 * estimate - nearest_rank(values, 0.975), 2 * estimate - nearest_rank(values, 0.025)],
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    order = sorted(pvalues, key=lambda key: (pvalues[key], key))
    running = 0.0
    result: dict[str, float] = {}
    for rank, key in enumerate(order):
        running = max(running, (len(order) - rank) * pvalues[key])
        result[key] = min(1.0, running)
    return result


def build(draws_path: Path, contrasts_path: Path, out_dir: Path) -> dict[str, object]:
    raw = json.loads(draws_path.read_text(encoding="utf-8"))
    contrasts = json.loads(contrasts_path.read_text(encoding="utf-8"))
    primary = contrasts["primary"]
    thresholds = {key: float(primary[key]["threshold"]) for key in CONTRASTS}
    registered = {key: float(primary[key]["point_estimate"]) for key in CONTRASTS}
    canonical_ci = {key: [float(x) for x in primary[key]["ci95_basic"]] for key in CONTRASTS}
    legacy_p = {key: float(primary[key].get("p_boot_one_sided", 1.0)) for key in CONTRASTS}

    arrays: dict[str, np.ndarray] = {}
    results: dict[str, dict] = {}
    for key in CONTRASTS:
        if key not in raw or "draws" not in raw[key]:
            raise ValueError(f"draws file lacks {key}.draws")
        estimate = float(raw[key]["estimate"])
        if abs(estimate - registered[key]) > 1e-12:
            raise ValueError(f"{key}: draws estimate {estimate} != canonical {registered[key]}")
        arrays[key] = np.asarray([finite(v, key) for v in raw[key]["draws"]], dtype=np.float64)
        results[key] = primary_from_draws(estimate, thresholds[key], raw[key]["draws"])
        ci = results[key]["ci95_basic"]
        if any(abs(a - b) > 1e-9 for a, b in zip(ci, canonical_ci[key])):
            raise ValueError(f"{key}: recomputed CI {ci} != canonical {canonical_ci[key]}")
        if legacy_p[key] == 0.0 and results[key]["p_raw_one_sided"] > 0:
            # 2026-09-18 delivered objects recorded p = 0; the R1 audit ruled that illegal under
            # the (tail+1)/(B+1) rule. The legacy bytes stay hash-bound; the value is superseded here.
            results[key]["supersedes_legacy_p_zero"] = True

    holm_values = holm({key: float(results[key]["p_raw_one_sided"]) for key in CONTRASTS})
    for key, value in holm_values.items():
        results[key]["p_holm"] = value

    summary = {
        "bootstrap_iterations": EXPECTED_DRAWS,
        "sampling_unit": SAMPLING_UNIT,
        "stratification": STRATIFICATION,
        "ci_method": CI_METHOD,
        "pvalue_rule": PVALUE_RULE,
        "multiple_testing": "Holm step-down",
        "results": results,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / "P1_P3_DRAWS.npz"
    np.savez_compressed(npz_path, **arrays)
    summary_path = out_dir / "P1_P3_BOOTSTRAP_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta = {
        "schema_version": 1,
        "kind": "BOOTSTRAP_DRAWS",
        "analysis_id": json.loads(
            (REPO / "results" / "canonical" / "bootstrap_context.json").read_text(encoding="utf-8")
        ).get("analysis_id"),
        "source_draws": str(draws_path.relative_to(REPO)).replace("\\", "/"),
        "source_draws_sha256": sha256_of(draws_path),
        "point_estimate_source": str(contrasts_path.relative_to(REPO)).replace("\\", "/"),
        "point_estimate_source_sha256": sha256_of(contrasts_path),
        "outputs": {
            "P1_P3_DRAWS.npz": sha256_of(npz_path),
            "P1_P3_BOOTSTRAP_SUMMARY.json": sha256_of(summary_path),
        },
        "seed_registry": "governance/SEED_REGISTRY_v1.0.json (entry: ANALYSIS bootstrap)",
        "script": "scripts/bootstrap_primary_contrasts.py",
        # Provenance fields are deliberately separated: the commit that produced the bytes is not
        # necessarily the commit at which someone re-verified them (2026-09-20 audit finding P0-2).
        "generated_at_commit": git_commit(),
        "verified_at_commit": None,
        "note": "draw generation itself is registered under the frozen plan; this script re-runs only the registered tail rule.",
    }
    (out_dir / "P1_P3_DRAWS.meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def compare_semantically(fresh_dir: Path, committed_dir: Path) -> tuple[bool, list[str]]:
    """Compare regenerated outputs with the committed ones by scientific content, not by bytes.

    Cross-platform note (2026-09-20 audit finding P0-2): the committed JSON/P1-P3 npz are
    byte-stable only within one platform. Line endings (CRLF vs LF) and the ZIP metadata field
    ``create_system`` written by ``numpy.savez_compressed`` differ between Windows and Linux, so a
    SHA-256 comparison of the files is not a valid reproducibility criterion. The registered
    numbers are identical; this checker therefore compares:

      * the summary JSON as parsed objects;
      * the npz by member names, dtype, shape and element-wise equality.

    Byte-level differences are reported as informational notes, never as failures.
    """
    notes: list[str] = []
    ok = True

    summary_name = "P1_P3_BOOTSTRAP_SUMMARY.json"
    fresh_summary, committed_summary = fresh_dir / summary_name, committed_dir / summary_name
    if not committed_summary.exists():
        return False, [f"MISSING {summary_name} in {committed_dir}"]

    fresh_obj = json.loads(fresh_summary.read_text(encoding="utf-8"))
    committed_obj = json.loads(committed_summary.read_text(encoding="utf-8"))
    if fresh_obj != committed_obj:
        ok = False
        notes.append(f"SEMANTIC MISMATCH {summary_name}: parsed objects differ")
    elif fresh_summary.read_bytes() != committed_summary.read_bytes():
        notes.append(f"byte-only difference (line endings): {summary_name} — semantics identical")

    npz_name = "P1_P3_DRAWS.npz"
    fresh_npz, committed_npz = fresh_dir / npz_name, committed_dir / npz_name
    if not committed_npz.exists():
        return False, notes + [f"MISSING {npz_name} in {committed_dir}"]

    with np.load(fresh_npz) as fresh_arrays, np.load(committed_npz) as committed_arrays:
        if list(fresh_arrays.files) != list(committed_arrays.files):
            ok = False
            notes.append(f"SEMANTIC MISMATCH {npz_name}: member sets differ")
        else:
            for key in fresh_arrays.files:
                a, b = fresh_arrays[key], committed_arrays[key]
                if a.dtype != b.dtype or a.shape != b.shape or not np.array_equal(a, b):
                    ok = False
                    notes.append(f"SEMANTIC MISMATCH {npz_name}: array {key} differs")
            if ok and fresh_npz.read_bytes() != committed_npz.read_bytes():
                notes.append(
                    f"byte-only difference (ZIP create_system metadata): {npz_name} — "
                    "arrays element-wise identical"
                )

    meta_path = committed_dir / "P1_P3_DRAWS.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        generated = meta.get("generated_at_commit")
        head = git_commit()
        if generated and generated != head:
            notes.append(
                f"INFO meta.generated_at_commit={generated[:12]} != HEAD={head[:12]} "
                "(provenance of the bytes; not a reproducibility failure)"
            )
        if "git_commit" in meta:
            ok = False
            notes.append("SEMANTIC MISMATCH meta: legacy field git_commit must be split into "
                         "generated_at_commit / verified_at_commit")

    return ok, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=Path, default=DEFAULT_DRAWS)
    parser.add_argument("--contrasts", type=Path, default=DEFAULT_CONTRASTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="regenerate to a temp dir and compare hashes")
    args = parser.parse_args(argv)

    if not args.check:
        summary = build(args.draws, args.contrasts, args.out_dir)
        for key, row in summary["results"].items():
            print(
                f"{key}: est={row['point_estimate']} thr={row['threshold']} "
                f"tail={row['tail_count']} p={row['p_raw_one_sided']:.6g} holm={row['p_holm']:.6g} "
                f"ci={row['ci95_basic']}"
            )
        print(f"wrote {args.out_dir}")
        return 0

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build(args.draws, args.contrasts, Path(tmp))
        ok, notes = compare_semantically(Path(tmp), args.out_dir)
        for note in notes:
            print(f"  {note}")
        print(f"verified_at_commit={git_commit()}")
        print("P1-P3 bootstrap: OK" if ok else "P1-P3 bootstrap: SEMANTIC MISMATCH")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
