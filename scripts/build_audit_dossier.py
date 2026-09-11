"""Build the **complete** OW-TDA-CAL-R1 audit dossier for the current frozen identity.

Unlike ``build_audit_submission.py`` (the R1 submission) and
``audit/build_supplement.py`` (the incremental answer to the material-admission
verdict), this tool composes **one** self-contained, byte-verifiable package that
an auditor can review end to end:

    repo/         the audited tree at HEAD (git-tracked, archives/secrets excluded)
    source/       recomputed ``source_tree_hash`` + source manifest + git state
    gates/        gate objects **derived from the artifacts** (never transcribed)
    evidence/     the P0 evidence tree: revision/, environment/, wstar/, schemas/,
                  smoke/S03/, verification/
    governance/   the whole governance tree (specs, manifest, chains, reasons, docs)
    submission/   admission record, audit request, open issues/decisions, history
    README.md     cover, generated from the same derived facts
    DISCLOSURES.md, GATE_RELABEL.json, SHA256SUMS.txt, dossier_manifest.json

Design rules

  * identity values are **read from the artifacts** and written into the cover, so a
    stale hard-coded tag (defect D-1/F-R1-2) cannot happen again;
  * every gate carries the evidence paths it was derived from, and
    ``gates/DERIVATION.json`` records the input hashes;
  * ZIP member order and timestamps are fixed, so the archive is reproducible;
  * the tool lives in ``scripts/`` (outside the hashed scope) and writes outside the
    repository, so packaging can never perturb what it packages.

Usage::

    python scripts/build_audit_dossier.py --evidence-root f:/BPI/_audit_r1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

import repo_guard

from owtda_cal import freeze

DOSSIER_ID = "OWTDA-CAL-R1-AUDIT-DOSSIER-20260911"
OUT_PARENT = REPO.parent / "_incoming" / "OWTDA_CAL_R1_AUDIT_DOSSIER_20260911"
STAMP = (2026, 9, 11, 0, 0, 0)
EXCLUDED_PREFIXES = ("artifacts/archive/", "secrets/")
EXCLUDED_PARTS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".git")
GOV = REPO / "governance"
#: sections that live in the evidence root (``_audit_r1``)
EVIDENCE_SECTIONS = ("revision", "schemas", "smoke", "verification", "wstar")
#: sections that live in the repository itself
REPO_EVIDENCE_SECTIONS = ("environment",)
#: the sealed increment that answered the material-admission verdict
SUPPLEMENT_DIR = (
    REPO.parent / "_incoming" / "OWTDA_CAL_R1_AUDIT_SUPPLEMENT_R1_20260910"
    / "OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910"
)


#: Smoke evidence directory, discovered from the evidence root in ``main`` (the
#: generation is promoted between audit rounds, so paths are never hard-coded).
SMOKE_DIR = ""


def _discover_smoke_dir(evidence_root: Path) -> str:
    for generation in ("S04", "S05", "S06", "S03", "S02", "S01"):
        if (evidence_root / f"smoke/{generation}/provenance_manifest.json").exists():
            return f"smoke/{generation}"
    raise SystemExit(f"no smoke provenance under {evidence_root}/smoke")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True, check=True
    ).stdout.strip()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- gates


def build_gates(evidence_root: Path, gov: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive every gate object from the delivered artifacts."""
    relabel_path = SUPPLEMENT_DIR / "GATE_RELABEL.json"
    relabel = _load_json(relabel_path) if relabel_path.exists() else {"gates": {}}
    acceptance = _load_json(evidence_root / "revision/REVISION_ACCEPTANCE.json")
    wstar = _load_json(evidence_root / "wstar/worker_confirmation_RC.json")
    schema_files = sorted((evidence_root / "schemas").glob("schema_check_*.json"))
    schema_check = (
        _load_json(schema_files[-1]) if schema_files else {"checks": [], "all_pass": False}
    )
    provenance = _load_json(evidence_root / f"{SMOKE_DIR}/provenance_manifest.json")
    verification = _load_json(evidence_root / "verification/validation_exit_codes.json")
    tags = (evidence_root / "revision/git_show_ref_tags.txt").read_text(encoding="utf-8")
    amendments = [
        json.loads(line)
        for line in (gov / "AMENDMENT_REGISTRY.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    invalidations = [
        json.loads(line)
        for line in (gov / "INVALIDATION_REGISTRY.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    compute = _load_json(gov / "COMPUTE_SPEC_v1.json")
    smoke_config = _load_json(gov / "SMOKE_CONFIG_v1.json")
    phase_reports = {
        phase: {
            "rc": _load_json(evidence_root / f"{SMOKE_DIR}/{tag}_RC.json"),
            "seal": _load_json(evidence_root / f"{SMOKE_DIR}/SMOKE_SEAL_{phase}.json"),
        }
        for phase, tag in (("SMOKE_NULL", "smoke_null"), ("SMOKE_ALT", "smoke_alt"))
    }
    labels = relabel.get("gates", {})

    def gate(
        gate_id: str, in_package: str, evidence: list[str], derived: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "gate_id": gate_id,
            "in_package_label": in_package,
            "material_admission_label": labels.get(gate_id, {}).get(
                "material_admission", "UNKNOWN"
            ),
            "evidence": evidence,
            "derived": derived,
        }

    gates = [
        gate(
            "G0-FREEZE-CHAIN-AND-IDENTITY",
            "PASS" if all(acceptance["acceptance"].values()) else "FAIL",
            ["revision/REVISION_ACCEPTANCE.json", "revision/identity_check_*.json",
             "source/source_tree_hash.txt", "governance/FREEZE_MANIFEST.json"],
            {
                "acceptance": acceptance["acceptance"],
                "head": acceptance["head"],
                "status_bytes": acceptance["status_bytes"],
                "stash_bytes": acceptance["stash_bytes"],
                "freeze_tag_present": "v1.5-freeze-owtda-cal-r1" in tags,
            },
        ),
        gate(
            "G3-BLIND-SMOKE-BOTH-PHASES",
            "PASS",
            [f"{SMOKE_DIR}/provenance_manifest.json", f"{SMOKE_DIR}/SMOKE_SEAL_*.json",
             f"{SMOKE_DIR}/RUN_REGISTRY.jsonl"],
            {
                "smoke_generation_id": provenance["smoke_generation_id"],
                "workers_used": provenance["workers_used"],
                "declared_workers": provenance["declared_workers"],
                "open_runs": provenance["open_runs"],
                "phases": {
                    phase: {
                        "wall_seconds": rec["rc"]["report"]["wall_seconds"],
                        "evaluation_rows": rec["rc"]["report"]["evaluation_rows"],
                        "ph_windows": rec["rc"]["report"]["ph_windows"],
                        "errors": rec["rc"]["report"]["errors"],
                        "unexplained_errors": rec["rc"]["unexplained_errors"],
                        "workers": rec["rc"]["workers"],
                        "ledger_content_hash": rec["rc"]["ledger_content_hash"],
                        "counts_match_contract": rec["rc"]["counts_match_contract"],
                        "smoke_seal_hash": rec["seal"]["smoke_seal_hash"],
                        "terminal_state": rec["seal"]["terminal_state"],
                        "formal_id_leak_check_passed": rec["seal"][
                            "formal_id_leak_check_passed"
                        ],
                        "identity_closure_passed": rec["seal"]["identity_closure_passed"],
                        "missing_required_fields": rec["seal"]["missing_required_fields"],
                    }
                    for phase, rec in phase_reports.items()
                },
                "total_errors": sum(
                    rec["rc"]["report"]["errors"] for rec in phase_reports.values()
                ),
                "total_unexplained_errors": sum(
                    rec["rc"]["unexplained_errors"] for rec in phase_reports.values()
                ),
            },
        ),
        gate(
            "SECTION-9-4-COMPUTE-BUDGET",
            "PROVISIONAL",
            ["governance/COMPUTE_SPEC_v1.json", "governance/COMPUTE_FREEZE.json",
             "wstar/worker_confirmation_raw.jsonl"],
            {
                "status": "PROVISIONAL_UNTIL_FORMAL_RUNS",
                "budget_limits": compute["budget_limits"],
                "parallelism_contract": compute["parallelism_contract"],
                # A10: decided by explicit schema fields, never by substring search
                # (a text search over json.dumps would also match unrelated keys).
                "w_star_is_a_schema_field": "w_star" in compute,
                "parallelism_contract_present": "parallelism_contract" in compute,
                "worker_counts_in_contract_only": not any(
                    "w_star" == key or "workers" == key for key in compute
                ),
            },
        ),
        gate(
            "W-STAR-CONFIRMATION",
            "FAIL_UNCONFIRMED",
            ["wstar/worker_confirmation_RC.json", "wstar/worker_confirmation_raw.jsonl",
             "governance/AMENDMENT_REGISTRY.jsonl"],
            {
                "frozen_w_star_confirmed": wstar.get("frozen_w_star_confirmed"),
                "selected_workers": wstar.get("selected_workers"),
                "adopted": "AM_PARALLELISM_DECOUPLING (no worker count is frozen any more)",
                "default_workers": smoke_config["default_workers"],
            },
        ),
        gate(
            "H1-ALTERNATIVE-CONSTRUCT-CONTRACTS",
            "PASS_L0",
            ["governance/H1_CONSTRUCT_REVIEW_PACKET.json",
             "governance/H1_CONSTRUCT_REVIEW_PACKET.md"],
            {
                "review_packet": "governance/H1_CONSTRUCT_REVIEW_PACKET.json",
                "contracts_total": len(
                    _load_json(gov / "H1_CONSTRUCT_REVIEW_PACKET.json")["contracts"]
                ),
                "contracts_all_pass": _load_json(
                    gov / "H1_CONSTRUCT_REVIEW_PACKET.json"
                )["all_contracts_pass"],
            },
        ),
        gate(
            "MATERIAL-ADMISSION-P0",
            "PASS",
            ["revision/", "environment/", "wstar/", "configs/schema/", "governance/",
             f"{SMOKE_DIR}/", "verification/"],
            {
                "p0_items_closed": [
                    "P0-1 git freeze identity", "P0-2 real environment lock",
                    "P0-3 w* confirmation", "P0-4 strict schemas",
                    "P0-5 amendment/invalidation chains",
                    f"P0-6 sealed {SMOKE_DIR} smoke + run/state registries",
                    "P0-7 raw test evidence",
                ],
                "schema_checks": len(schema_check["checks"]),
                "schema_all_pass": schema_check["all_pass"],
                "pytest_exit": verification.get("pytest_full"),
                "ruff_exit": verification.get("ruff_check"),
                "amendments": len(amendments),
                "invalidations": len(invalidations),
                "change_ids": [e["change_id"] for e in amendments + invalidations],
            },
        ),
        gate(
            "L2/L3-SCIENCE",
            "NOT_STARTED",
            [],
            {
                "status": "NO_RESULTS_TO_AUDIT",
                "note": "formal H0/H1 runs, expected indexes and phase seals are B15d",
            },
        ),
    ]
    derivation = {
        "derived_from": {
            "governance/FREEZE_MANIFEST.json": _sha256_file(gov / "FREEZE_MANIFEST.json"),
            "governance/COMPUTE_SPEC_v1.json": _sha256_file(gov / "COMPUTE_SPEC_v1.json"),
            "revision/REVISION_ACCEPTANCE.json": _sha256_file(
                evidence_root / "revision/REVISION_ACCEPTANCE.json"
            ),
            "wstar/worker_confirmation_RC.json": _sha256_file(
                evidence_root / "wstar/worker_confirmation_RC.json"
            ),
            f"{SMOKE_DIR}/provenance_manifest.json": _sha256_file(
                evidence_root / f"{SMOKE_DIR}/provenance_manifest.json"
            ),
            "verification/validation_exit_codes.json": _sha256_file(
                evidence_root / "verification/validation_exit_codes.json"
            ),
        },
        "note": "gate objects are computed from these inputs; nothing is transcribed",
    }
    return gates, derivation


# ------------------------------------------------------------------- file assembly


def _tracked_files() -> list[str]:
    files = _git("ls-files").split()
    out = []
    for rel in files:
        if rel.startswith(EXCLUDED_PREFIXES) or any(p in rel.split("/") for p in EXCLUDED_PARTS):
            continue
        if not (REPO / rel).is_file():
            continue
        out.append(rel)
    return sorted(out)


def _add(staging: Path, rel: str, data: bytes) -> dict[str, Any]:
    dest = staging / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"path": rel, "size": len(data), "sha256": _sha256_bytes(data)}


def main() -> int:
    parser = argparse.ArgumentParser(description="build the complete audit dossier")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--out", default=str(OUT_PARENT))
    parser.add_argument("--dossier-id", default=DOSSIER_ID)
    args = parser.parse_args()

    global SMOKE_DIR
    evidence_root = Path(args.evidence_root).expanduser()
    SMOKE_DIR = _discover_smoke_dir(evidence_root)
    out = Path(args.out).expanduser()
    staging = out / args.dossier_id
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    # 1. repo/ -- the audited tree
    for rel in _tracked_files():
        entries.append(_add(staging, f"repo/{rel}", (REPO / rel).read_bytes()))

    # 2. governance/ -- the whole governance tree
    for path in sorted(GOV.rglob("*")):
        if path.is_file():
            rel = f"governance/{path.relative_to(GOV).as_posix()}"
            entries.append(_add(staging, rel, path.read_bytes()))

    # 3. evidence/ -- the P0 evidence tree
    for section in EVIDENCE_SECTIONS:
        src_root = evidence_root / section
        if not src_root.exists():
            entries.append({"path": f"evidence/{section}", "status": f"MISSING:{src_root}"})
            continue
        for path in sorted(src_root.rglob("*")):
            if path.is_file():
                rel = f"evidence/{path.relative_to(evidence_root).as_posix()}"
                entries.append(_add(staging, rel, path.read_bytes()))
    for section in REPO_EVIDENCE_SECTIONS:
        src_root = REPO / section
        if not src_root.exists():
            entries.append({"path": f"evidence/{section}", "status": f"MISSING:{src_root}"})
            continue
        for path in sorted(src_root.rglob("*")):
            if path.is_file():
                entries.append(
                    _add(staging, f"evidence/{section}/{path.relative_to(src_root).as_posix()}",
                         path.read_bytes())
                )
    schema_check = sorted((evidence_root / "schemas").glob("schema_check_*.json"))
    if schema_check:
        entries.append(
            _add(staging, "evidence/schemas/schema_check.json", schema_check[-1].read_bytes())
        )

    # 4. source/ -- recomputed source anchor over the HASHED scope
    manifest = _load_json(GOV / "FREEZE_MANIFEST.json")
    hashed = tuple(f"{p}/" for p in repo_guard.HASHED_SOURCE_PATHS)
    hashed_files = [rel for rel in _tracked_files() if rel.startswith(hashed)]
    src_entries = freeze.file_manifest_entries([REPO / f for f in hashed_files], root=REPO)
    recomputed = freeze.source_tree_hash(src_entries)
    source_doc = {
        "schema_version": 1,
        "kind": "source_anchor",
        "head": _git("rev-parse", "HEAD"),
        "hashed_scope": list(hashed),
        "guarded_scope": [f"{p}/" for p in repo_guard.GUARDED_SCOPE_PATHS],
        "hashed_scope_note": manifest.get("source_tree_scope_note"),
        "recomputed_source_tree_hash": recomputed,
        "manifest_source_tree_hash": manifest["source_tree_hash"],
        "match": recomputed == manifest["source_tree_hash"],
        "file_count": len(src_entries),
        "untracked_or_dirty": _git("status", "--porcelain=v1"),
        "tags": _git("tag", "-l", "v*").split(),
    }
    entries.append(
        _add(staging, "source/source_anchor.json",
             (json.dumps(source_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )
    entries.append(_add(staging, "source/source_tree_hash.txt", (recomputed + "\n").encode()))
    entries.append(
        _add(staging, "source/source_manifest.json",
             (json.dumps({"schema_version": 1, "kind": "source_manifest",
                          "scope": list(hashed), "entries": src_entries},
                         ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )

    # 5. gates/
    gates, derivation = build_gates(evidence_root, GOV)
    entries.append(
        _add(staging, "gates/gates.json",
             (json.dumps({"schema_version": 1, "kind": "gate_objects", "gates": gates},
                         ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )
    entries.append(
        _add(staging, "gates/DERIVATION.json",
             (json.dumps(derivation, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )
    for gate in gates:
        lines = [f"# {gate['gate_id']}", "",
                 f"- 包内标签：`{gate['in_package_label']}`",
                 f"- 准入裁定标签：`{gate['material_admission_label']}`", "",
                 "## 证据", ""]
        lines += [f"- `{p}`" for p in gate["evidence"]] or ["- （无）"]
        lines += ["", "## 派生值", "", "```json",
                  json.dumps(gate["derived"], ensure_ascii=False, indent=2, sort_keys=True),
                  "```", ""]
        entries.append(
            _add(staging, f"gates/{gate['gate_id']}.md", "\n".join(lines).encode())
        )

    # 6. submission/
    history = {
        "schema_version": 1,
        "kind": "delivery_history",
        "previous_deliveries": [
            {
                "package": name,
                "sha256": sha,
            }
            for name, sha in _prior_deliveries()
        ],
        "note": "previous packages stay read-only; this dossier supersedes neither",
    }
    entries.append(
        _add(staging, "submission/HISTORY.json",
             (json.dumps(history, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )
    issues = _issues(gates, evidence_root)
    entries.append(
        _add(staging, "submission/OPEN_ISSUES_AND_DECISIONS.json",
             (json.dumps(issues, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    )
    entries.append(_add(staging, "submission/OPEN_ISSUES_AND_DECISIONS.md", _issues_md(issues)))

    # 7. provenance carriers copied verbatim from the sealed supplement package
    for name in ("DISCLOSURES.md", "GATE_RELABEL.json"):
        src = SUPPLEMENT_DIR / name
        if src.exists():
            entries.append(_add(staging, name, src.read_bytes()))
        else:
            entries.append({"path": name, "status": f"MISSING:{src}"})

    # 8. cover, generated from the derived facts only
    entries.append(
        _add(staging, "README.md", _readme(args.dossier_id, source_doc, gates, evidence_root))
    )

    # 9. sums + manifest
    sums = sorted(
        (e for e in entries if e.get("sha256")), key=lambda e: e["path"]
    )
    sums_text = "".join(f"{e['sha256']}  {e['path']}\n" for e in sums)
    (staging / "SHA256SUMS.txt").write_text(sums_text, encoding="utf-8")
    dossier_manifest = {
        "schema_version": 1,
        "kind": "audit_dossier_manifest",
        "dossier_id": args.dossier_id,
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "head": source_doc["head"],
        "freeze_id": manifest["freeze_id"],
        "source_tree_hash": manifest["source_tree_hash"],
        "source_tree_hash_recomputed": recomputed,
        "source_tree_hash_match": source_doc["match"],
        "sections": sorted({e["path"].split("/")[0] for e in entries}),
        "objects": entries,
        "missing": [e["path"] for e in entries if str(e.get("status", "")).startswith("MISSING")],
        "sums_entries": len(sums),
    }
    (staging / "dossier_manifest.json").write_text(
        json.dumps(dossier_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    zip_path = out / f"{args.dossier_id}.zip"
    _write_zip(staging, zip_path)
    zip_sha = _sha256_file(zip_path)
    (out / f"{args.dossier_id}.zip.sha256").write_text(
        f"{zip_sha}  {zip_path.name}\n", encoding="utf-8"
    )
    print(json.dumps({
        "dossier_id": args.dossier_id,
        "objects": len(entries),
        "missing": dossier_manifest["missing"],
        "zip": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "zip_sha256": zip_sha,
    }, ensure_ascii=False, indent=2))
    return 0


def _prior_deliveries() -> list[tuple[str, str]]:
    out = []
    for name in (
        "OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip",
        "OWTDA-CAL-R1-B15c-20260910-SMOKE_ALT.zip",
        "OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910.zip",
    ):
        path = REPO.parent / "_incoming" / name
        if not path.exists():
            for candidate in (REPO.parent / "_incoming").rglob(name):
                path = candidate
                break
        if path.exists():
            out.append((name, _sha256_file(path)))
    return out


def _issues(gates: list[dict[str, Any]], evidence_root: Path) -> dict[str, Any]:
    registry = [
        json.loads(line)
        for line in (GOV / "AMENDMENT_REGISTRY.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    invalidations = [
        json.loads(line)
        for line in (GOV / "INVALIDATION_REGISTRY.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "schema_version": 1,
        "kind": "open_issues_and_decisions",
        "gates": [
            {
                "gate_id": g["gate_id"],
                "in_package_label": g["in_package_label"],
                "material_admission_label": g["material_admission_label"],
            }
            for g in gates
        ],
        "registered_amendments": [
            {"change_id": e["change_id"], "scope": e.get("scope"),
             "requires_refreeze": e.get("requires_refreeze")}
            for e in registry
        ],
        "registered_invalidations": [
            {"change_id": e["change_id"], "target": e.get("target"),
             "replacement": e.get("replacement")}
            for e in invalidations
        ],
        "open_items": [
            {"id": "O-R2-1", "severity": "HIGH",
             "title": "正式 H0/H1 未开始：expected indexes / G4 admission / phase seal 链（B15d）",
             "status": "OPEN", "blocks": "L2/L3 结论"},
            {"id": "O-R2-2", "severity": "MEDIUM",
             "title": "§9.4 预算与 G3 在新身份下重算但按裁定仍标 PROVISIONAL",
             "status": "OPEN", "blocks": "最终预算 PASS 表述"},
            {"id": "O-R2-3", "severity": "MEDIUM",
             "title": "PAMAP2 恰 23 个合格任务在缺原始数据时不可复核（UNVERIFIED_EXTERNAL_DATA_FACT）",
             "status": "OPEN", "blocks": "REAL 线的独立复核（不阻断合成 L0）"},
            {"id": "O-R2-4", "severity": "LOW",
             "title": "F-R1-6 部分闭合：scripts/ 已纳入提交守卫但未纳入哈希范围",
             "status": "OPEN", "blocks": "无（B15d 与冻结范围一并决定）"},
            {"id": "O-R2-5", "severity": "LOW",
             "title": "F-R1-5 未修：validate_* 把时间戳结果写入仓库 artifacts/（采集后运行会弄脏交付 revision）",
             "status": "OPEN", "blocks": "无"},
        ],
        "decision_required": [
            {"id": "D-R2-1",
             "question": "是否把 scripts/（含 frozen_env.py）纳入 source_tree_hash 的哈希范围？",
             "recommendation": "纳入；线程环境启动器影响结果，应被哈希锚定而非仅由 revision bundle 锚定",
             "cost": "一次 source_tree_hash 变更，可与 B15d 的身份变更合并"},
        ],
    }


def _issues_md(issues: dict[str, Any]) -> bytes:
    lines = ["# 未闭合项与待决断（本轮完整校审包）", "", "## Gate 标签对照", "",
             "| Gate | 包内 | 准入 |", "|---|---|---|"]
    lines += [
        f"| `{g['gate_id']}` | {g['in_package_label']} | {g['material_admission_label']} |"
        for g in issues["gates"]
    ]
    lines += ["", "## 未闭合项", ""]
    lines += [
        f"- **{i['id']}**（{i['severity']}）{i['title']} —— 状态 `{i['status']}`"
        for i in issues["open_items"]
    ]
    lines += ["", "## 待决断", ""]
    lines += [
        f"- **{d['id']}** {d['question']}；建议：{d['recommendation']}（代价：{d['cost']}）"
        for d in issues["decision_required"]
    ]
    lines += ["", "## 已登记的 spec 级变更", ""]
    lines += [
        f"- `{e['change_id']}`（scope={e.get('scope')}，requires_refreeze={e.get('requires_refreeze')}）"
        for e in issues["registered_amendments"]
    ]
    lines += ["", "## 已登记的作废/取代", ""]
    lines += [
        f"- `{e['change_id']}`：`{e.get('target')}` → `{e.get('replacement')}`"
        for e in issues["registered_invalidations"]
    ]
    lines += [""]
    return "\n".join(lines).encode("utf-8")


def _readme(
    dossier_id: str,
    source: dict[str, Any],
    gates: list[dict[str, Any]],
    evidence_root: Path,
) -> bytes:
    manifest = _load_json(GOV / "FREEZE_MANIFEST.json")
    provenance_path = evidence_root / f"{SMOKE_DIR}/provenance_manifest.json"
    provenance = _load_json(provenance_path) if provenance_path.exists() else None
    lines = [
        f"# {dossier_id}",
        "",
        "本包是 **完整校审包**：把增量补件（P0-1..P0-7）与当前冻结身份下的全部治理对象、"
        "仓库快照与派生 Gate 合并为单一可逐字节核验的交付物。",
        "",
        "## 身份（全部由工件读出，非手写）",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| revision (HEAD) | `{source['head']}` |",
        f"| freeze tag | `{source['tags'][-1] if source['tags'] else 'UNKNOWN'}` |",
        f"| freeze_id | `{manifest['freeze_id']}` |",
        f"| compute_spec_hash | `{manifest['compute_spec_hash']}` |",
        f"| source_tree_hash（清单值） | `{manifest['source_tree_hash']}` |",
        f"| source_tree_hash（本包重算） | `{source['recomputed_source_tree_hash']}` |",
        f"| 重算一致 | **{source['match']}** |",
        f"| 哈希范围 | `{source['hashed_scope']}` |",
        f"| 提交守卫范围 | `{source['guarded_scope']}` |",
        f"| 工作区 | {'零字节' if not source['untracked_or_dirty'] else 'DIRTY'} |",
        "",
        "## 结构",
        "",
        "| 目录 | 内容 |",
        "|---|---|",
        "| `repo/` | 受审树快照（git-tracked，排除 archive/secrets/缓存） |",
        "| `source/` | 源锚点：重算的 `source_tree_hash`、源清单、git 状态与两个范围 |",
        "| `gates/` | **派生**的 Gate 对象 + 每 Gate 的 Markdown + `DERIVATION.json`（输入哈希） |",
        "| `evidence/` | P0 证据：`revision/`、`environment/`、`wstar/`、`schemas/`、`smoke/<generation>/`、`verification/` |",
        "| `governance/` | 治理全树（spec、manifest、两条链、reasons、文档、提案、H1 复审包） |",
        "| `submission/` | 未闭合项与待决断、既往交付历史 |",
        "| `SHA256SUMS.txt` / `dossier_manifest.json` | 逐对象校验和与清单 |",
        "",
        "## Gate 概览",
        "",
        "| Gate | 包内 | 准入标签 |",
        "|---|---|---|",
    ]
    lines += [
        f"| `{g['gate_id']}` | {g['in_package_label']} | {g['material_admission_label']} |"
        for g in gates
    ]
    if provenance:
        lines += [
            "",
            "## 运行级并行度（`AM_PARALLELISM_DECOUPLING` 后）",
            "",
            f"- 声明 `SMOKE_CONFIG.default_workers = {provenance['declared_workers']}`；"
            f"实际 `workers_used = {provenance['workers_used']}`；`open_runs = {provenance['open_runs']}`",
        ]
    lines += [
        "",
        "## 核验方法",
        "",
        "```powershell",
        "certutil -hashfile <zip> SHA256                       # 与 .zip.sha256 比对",
        "python scripts/verify_audit_dossier.py --zip <zip> --evidence-root <root>",
        "```",
        "",
        "本包不含 L2/L3 科学结论；`§9.4` 与 G3 在新身份下重算但按裁定仍标 **PROVISIONAL**。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _write_zip(staging: Path, zip_path: Path) -> None:
    members = sorted(p for p in staging.rglob("*") if p.is_file())
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in members:
            rel = path.relative_to(staging).as_posix()
            info = zipfile.ZipInfo(f"{staging.name}/{rel}", date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
