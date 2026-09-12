"""Attack the dossier verifier (audit verdict, phase two).

The verdict asks that the verifier be attacked *before* the expensive smoke run:
every important contract needs a "deliberately broken -> must fail" test.  The
unit tests in ``tests/`` do this at the level of individual checks; this harness
does it end to end, on a **built dossier**:

1. verify the delivered zip unchanged (baseline),
2. verify it again after an extract/repackage round trip (the harness must not be
   what breaks it),
3. for each attack, copy the dossier, break exactly one thing, repackage and
   verify again.

Two properties are reported per attack:

* ``detected``       -- the named check is not PASS on the mutant (required);
* ``attributable``   -- that check *was* PASS on the baseline, so the mutation is
  what flipped it (this is the strong form; a baseline that already fails a check
  makes the corresponding attack uninformative, which is reported, not hidden).

Each mutation is applied **without re-signing** the hash chain.  That is
deliberate: if a defect can only be caught by re-hashing, the semantic check is
not doing its job.  Chain integrity itself is covered by the ``integrity.*``
checks and by the mutation tests in ``tests/``.

Usage::

    python scripts/attack_dossier.py --zip <dossier.zip> [--out DIR] [--only ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
VERIFIER = REPO / "scripts" / "verify_audit_dossier.py"
PYTHON = REPO / ".venv/Scripts/python.exe"
DEFAULT_OUT = REPO.parent / "_incoming" / "_verifier_attacks"


# --------------------------------------------------------------------------- #
# dossier helpers
# --------------------------------------------------------------------------- #
def extract(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)


def repackage(src: Path, out_zip: Path) -> None:
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(src).as_posix())


def verify(zip_path: Path, out_dir: Path) -> tuple[int, dict[str, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [str(PYTHON), str(VERIFIER), "--zip", str(zip_path), "--out", str(out_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )
    report_path = out_dir / "SELF_VERIFICATION.json"
    if not report_path.exists():
        raise RuntimeError(
            f"verifier produced no report (exit {done.returncode}): "
            f"{(done.stderr or done.stdout)[-800:]}"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return done.returncode, {c["check_id"]: c["status"] for c in report["checks"]}


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _edit_json(path: Path, mutate: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    _write_json(path, data)


def _edit_jsonl(path: Path, mutate: Callable[[list[dict]], None]) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    mutate(rows)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def _current_smoke_dir(root: Path) -> str | None:
    """The smoke directory the delivered provenance actually describes.

    The package also carries the superseded attempts (the re-audit asked for them), so
    "sorted first match" is no longer unique: the *current* generation must be
    resolved from the provenance rather than from directory order.
    """
    for provenance in sorted(root.rglob("provenance_manifest.json")):
        try:
            generation = json.loads(
                provenance.read_text(encoding="utf-8")
            ).get("smoke_generation_id")
        except json.JSONDecodeError:
            continue
        if generation:
            return f"evidence/smoke/{generation}"
    return None


def _one(root: Path, pattern: str) -> Path:
    hits = sorted(root.rglob(pattern))
    if not hits:
        raise RuntimeError(f"attack target not found: {pattern}")
    if len(hits) > 1:
        preferred = _current_smoke_dir(root)
        if preferred:
            scoped = [p for p in hits if preferred in p.as_posix()]
            if scoped:
                return scoped[0]
    return hits[0]


def _seal(root: Path, phase: str) -> Path:
    return _one(root, f"SMOKE_SEAL_{phase}.json")


# --------------------------------------------------------------------------- #
# the attacks
# --------------------------------------------------------------------------- #
def a05_terminal_bogus(root: Path) -> list[str]:
    """Claim a non-existent terminal state."""
    path = _one(root, "STATE_REGISTRY.jsonl")

    def mutate(rows: list[dict]) -> None:
        rows[-1]["event_type"] = "BOGUS"
        rows[-1]["state"] = "BOGUS"

    _edit_jsonl(path, mutate)
    return [str(path)]


def a05_terminal_open(root: Path) -> list[str]:
    """Leave the run non-terminal (the old check accepted any non-empty value)."""
    path = _one(root, "STATE_REGISTRY.jsonl")

    def mutate(rows: list[dict]) -> None:
        rows[-1]["event_type"] = "RUN_OPEN"
        rows[-1]["state"] = "RUN_OPEN"

    _edit_jsonl(path, mutate)
    return [str(path)]


def a10_ph_windows_doubled(root: Path) -> list[str]:
    """Count MOMENTS windows as PH work again (the audited x2 inflation)."""
    path = _seal(root, "SMOKE_NULL")

    def mutate(seal: dict) -> None:
        seal["ph_windows"] = int(seal["ph_windows"]) * 2

    _edit_json(path, mutate)
    return [str(path)]


def _inject_resources(seal: dict) -> dict:
    """A plausible resource block, added if the seal predates A08 evidence.

    Values are integers on purpose: the seal hash is taken over a canonical
    payload in which bare floats are forbidden.
    """
    return seal.setdefault(
        "resources",
        {
            "schema_version": 1,
            "kind": "run_resources_v1",
            "peak_total_rss_bytes": 1024**3,
            "host_swap_growth_bytes": 0,
            "disk_free_before_bytes": 500 * 1024**3,
            "evidence_bytes_written": 1024,
            "run_id": seal.get("run_id"),
            "phase": seal.get("phase"),
        },
    )


def a08_swap_growth(root: Path) -> list[str]:
    """A page-file increase (the audited NULL record had +4 MB)."""
    path = _seal(root, "SMOKE_NULL")

    def mutate(seal: dict) -> None:
        _inject_resources(seal)["host_swap_growth_bytes"] = 4 * 1024 * 1024

    _edit_json(path, mutate)
    return [str(path)]


def a08_resource_unbound(root: Path) -> list[str]:
    """Attach the resources to a run id that is not the sealed run."""
    path = _seal(root, "SMOKE_NULL")

    def mutate(seal: dict) -> None:
        _inject_resources(seal)["run_id"] = "S99:SMOKE_NULL:w8:r32"

    _edit_json(path, mutate)
    return [str(path)]


def a01_wrong_cell_id(root: Path) -> list[str]:
    """Replace one ledger cell id: counts stay right, the identity does not."""
    path = _one(root, "SMOKE_NULL/evaluation_rows.jsonl")

    def mutate(rows: list[dict]) -> None:
        rows[0]["logical_cell_id"] = "0" * 64

    _edit_jsonl(path, mutate)
    return [str(path)]


def a02_zero_based_replicate(root: Path) -> list[str]:
    """Go back to 0-based replicate numbering (protocol requires 1..32).

    The replicate is not a column: it is baked into the ids.  This attack rebuilds
    one row's ``logical_data_key``/``data_unit_id`` exactly as a 0-based
    implementation would have produced them, so the row names a replicate that the
    specification does not contain.
    """
    from owtda_cal import smoke_ids

    path = _one(root, "SMOKE_NULL/evaluation_rows.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    manifest = json.loads(
        _one(root, "FREEZE_MANIFEST.json").read_text(encoding="utf-8")
    )
    generation = None
    for candidate in ("S01", "S02", "S03", "S04", "S05"):
        if candidate in rows[0]["logical_data_key"]:
            generation = candidate
            break
    common = {
        "project_id": manifest["project_id"],
        "protocol_id": manifest["protocol_id"],
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "smoke_generation_id": generation,
        "phase": rows[0]["phase"],
    }
    row = rows[0]
    master_replicate_id = smoke_ids.smoke_master_replicate_id(
        **common, DGP_family=row["DGP_family"], replicate_id=0
    )
    row["logical_data_key"] = smoke_ids.smoke_logical_data_key(
        smoke_generation_id=generation,
        smoke_logical_cell_id=row["logical_cell_id"],
        smoke_master_replicate_id=master_replicate_id,
    )
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )
    return [str(path)]


def a06_source_null_wrong(root: Path) -> list[str]:
    """Point one H1 source-null field away from the N-CIRCLE NULL cell."""
    path = _one(root, "H1_CONSTRUCT_REVIEW_PACKET.json")

    def mutate(packet: dict) -> None:
        packet["evidence"]["null_scope_join"][0]["source_null_logical_cell_id"] = "0" * 64

    _edit_json(path, mutate)
    return [str(path)]


ATTACKS: list[dict[str, Any]] = [
    {
        "id": "A05_terminal_bogus", "finding": "A05",
        "description": "终态改成不存在的 BOGUS（旧检查 `in (...) or bool(state)` 会放过）",
        "mutate": a05_terminal_bogus,
        "targets": ["smoke.terminal_states_exact"],
    },
    {
        "id": "A05_terminal_open", "finding": "A05",
        "description": "终态改成 RUN_OPEN（运行未闭合却仍按已封存记）",
        "mutate": a05_terminal_open,
        "targets": ["smoke.terminal_states_exact"],
    },
    {
        "id": "A10_ph_windows_doubled", "finding": "A10",
        "description": "把 PH 计算量翻倍（MOMENTS 窗口重新计入）",
        "mutate": a10_ph_windows_doubled,
        "targets": ["smoke.SMOKE_NULL.declared_matches_recomputed"],
    },
    {
        "id": "A08_swap_growth", "finding": "A08",
        "description": "资源记录出现 4 MB swap 增长（被审计的 NULL 记录同因）",
        "mutate": a08_swap_growth,
        "targets": ["smoke.SMOKE_NULL.resources_recomputed"],
    },
    {
        "id": "A08_resource_unbound", "finding": "A08",
        "description": "资源记录挂到另一次 run（尺寸/资源与 run 不绑定）",
        "mutate": a08_resource_unbound,
        "targets": ["smoke.SMOKE_NULL.resources_bound_to_run"],
    },
    {
        "id": "A01_wrong_cell_id", "finding": "A01",
        "description": "改动一行 logical_cell_id：计数不变，身份不再闭合",
        "mutate": a01_wrong_cell_id,
        "targets": ["smoke.SMOKE_NULL.closure_recomputed"],
    },
    {
        "id": "A02_zero_based_replicate", "finding": "A02",
        "description": "replicate 回到 0 基编号（协议要求 1..32）",
        "mutate": a02_zero_based_replicate,
        "targets": ["smoke.SMOKE_NULL.closure_recomputed"],
    },
    {
        "id": "A06_source_null_wrong", "finding": "A06",
        "description": "H1 某 cell 的 source-null 外键指向别处",
        "mutate": a06_source_null_wrong,
        "targets": ["h1.source_null_join_recomputed"],
    },
]


# --------------------------------------------------------------------------- #
# re-audit 2026-09-12 probes: the outer hashes are re-signed, so only the internal
# contracts are under test.  All eight were accepted by the verifier before the
# internal-contract checks were added.
# --------------------------------------------------------------------------- #
def _dossier_root(root: Path) -> Path:
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if len(dirs) != 1:
        raise RuntimeError(f"expected one top-level dir, found {len(dirs)}")
    return dirs[0]


def _resign(root: Path) -> None:
    """Recompute SHA256SUMS.txt and dossier_manifest.json after a mutation."""
    dossier = _dossier_root(root)
    sums_path = dossier / "SHA256SUMS.txt"
    lines: list[str] = []
    updated: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        _, rel = re.split(r"\s+", line.strip(), maxsplit=1)
        rel = rel.strip()
        target = dossier / rel
        digest = (
            hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else "0" * 64
        )
        updated[rel] = digest
        lines.append(f"{digest}  {rel}\n")
    sums_path.write_text("".join(lines), encoding="utf-8")
    manifest_path = dossier / "dossier_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for obj in manifest.get("objects", []):
        rel = obj.get("path")
        if rel in updated:
            target = dossier / rel
            obj["sha256"] = updated[rel]
            obj["size"] = target.stat().st_size if target.exists() else 0
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def p1_fixture_missing_seal(root: Path) -> list[str]:
    seal = _one(root, "PHASE_SEAL_TEST_ANALYSIS.json")
    seal.unlink()
    return [str(seal)]


def p2_fixture_wrong_ledger_hash(root: Path) -> list[str]:
    seal = _one(root, "PHASE_SEAL_TEST_ANALYSIS.json")

    def mutate(payload: dict) -> None:
        payload["active_ledger_content_hash"] = "0" * 64

    _edit_json(seal, mutate)
    return [str(seal)]


def p3_smoke_invalid_p_value(root: Path) -> list[str]:
    path = _one(root, "SMOKE_NULL/evaluation_rows.jsonl")

    def mutate(rows: list[dict]) -> None:
        rows[0]["p_value"] = 2.0

    _edit_jsonl(path, mutate)
    return [str(path)]


def p4_resource_false_delta(root: Path) -> list[str]:
    path = _seal(root, "SMOKE_NULL")

    def mutate(seal: dict) -> None:
        res = seal["resources"]
        res["host_swap_peak_bytes"] = int(res["host_swap_peak_bytes"]) + 4 * 1024 * 1024

    _edit_json(path, mutate)
    return [str(path)]


def p5_state_field_open_event_sealed(root: Path) -> list[str]:
    path = _one(root, "STATE_REGISTRY.jsonl")

    def mutate(rows: list[dict]) -> None:
        for row in rows:
            if row.get("event_type") == "RUN_SEALED":
                row["state"] = "RUN_OPEN"

    _edit_jsonl(path, mutate)
    return [str(path)]


def p6_broken_run_chain_hash(root: Path) -> list[str]:
    path = _one(root, "RUN_REGISTRY.jsonl")

    def mutate(rows: list[dict]) -> None:
        rows[0]["run_registry_event_hash"] = "0" * 64

    _edit_jsonl(path, mutate)
    return [str(path)]


def p7_h1_join_truncated(root: Path) -> list[str]:
    path = _one(root, "H1_CONSTRUCT_REVIEW_PACKET.json")

    def mutate(packet: dict) -> None:
        joins = packet["evidence"]["null_scope_join"]
        packet["evidence"]["null_scope_join"] = joins[:1]

    _edit_json(path, mutate)
    return [str(path)]


def p8_smoke_scope_bad_cell(root: Path) -> list[str]:
    import csv as _csv
    import io as _io

    # Resolve the CSV the seal actually names: several SCOPE_DESIGN variants ship,
    # and the sorted-first glob would attack a file nobody references.
    seal = _seal(root, "SMOKE_NULL")
    scope_hash = json.loads(seal.read_text(encoding="utf-8"))["scope_design_hash"]
    path = _one(root, f"SCOPE_DESIGN_SMOKE_NULL_{scope_hash}.csv")
    raw = path.read_text(encoding="utf-8")
    rows = list(_csv.DictReader(_io.StringIO(raw.lstrip("\ufeff"))))
    bad = rows[0]["logical_cell_id"]
    path.write_text(raw.replace(bad, "0" * 64, 1), encoding="utf-8")
    return [str(path)]


ATTACKS.extend([
    {
        "id": "R1_fixture_missing_analysis_seal", "finding": "re-audit A11",
        "description": "删除真正的分析 seal 文件（重签外层哈希后）",
        "mutate": p1_fixture_missing_seal, "resign": True,
        "targets": ["fixture.seals_present"],
    },
    {
        "id": "R2_fixture_wrong_ledger_hash", "finding": "re-audit A11",
        "description": "把分析 seal 的账本哈希改成全零",
        "mutate": p2_fixture_wrong_ledger_hash, "resign": True,
        "targets": ["fixture.seals_match_chain"],
    },
    {
        "id": "R3_smoke_invalid_p_value", "finding": "re-audit 数值",
        "description": "把一行 smoke 的 p 值改成 2.0",
        "mutate": p3_smoke_invalid_p_value, "resign": True,
        "targets": ["ledger.SMOKE_NULL.p_value_formula"],
    },
    {
        "id": "R4_resource_false_delta", "finding": "re-audit A08",
        "description": "swap peak 加 4 MiB 却保留 growth=0",
        "mutate": p4_resource_false_delta, "resign": True,
        "targets": ["resources.SMOKE_NULL.internally_consistent"],
    },
    {
        "id": "R5_state_open_event_sealed", "finding": "re-audit A05",
        "description": "保留封存事件名，把实际 state 改成 RUN_OPEN",
        "mutate": p5_state_field_open_event_sealed, "resign": True,
        "targets": ["state.events_self_consistent"],
    },
    {
        "id": "R6_broken_run_chain_hash", "finding": "re-audit A05",
        "description": "破坏 RUN 注册表的事件哈希",
        "mutate": p6_broken_run_chain_hash, "resign": True,
        "targets": ["registry.RUN_REGISTRY.jsonl.chain"],
    },
    {
        "id": "R7_h1_join_truncated", "finding": "re-audit A06",
        "description": "H1 source-null 只保留 8 项中的 1 项",
        "mutate": p7_h1_join_truncated, "resign": True,
        "targets": ["h1.join_complete"],
    },
    {
        "id": "R8_smoke_scope_bad_cell", "finding": "re-audit A01 gate",
        "description": "修改实际 scope CSV 中一个 logical cell ID",
        "mutate": p8_smoke_scope_bad_cell, "resign": True,
        "targets": ["scope.SMOKE_NULL.rows_equal_spec"],
    },
])


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run_attacks(zip_path: Path, out_dir: Path, only: str | None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    # Short temp prefix and short mutant directory names: the package contains deep
    # 64-hex paths (shard directories), and Windows MAX_PATH bites when a full copy is
    # made under a long attack id.
    with tempfile.TemporaryDirectory(prefix="oa_") as tmp:
        tmpdir = Path(tmp)
        clean = tmpdir / "clean"
        extract(zip_path, clean)
        baseline_exit, baseline = verify(zip_path, out_dir / "_baseline")

        roundtrip_zip = tmpdir / "roundtrip.zip"
        repackage(clean, roundtrip_zip)
        _, roundtrip = verify(roundtrip_zip, out_dir / "_roundtrip")
        roundtrip_ok = roundtrip == baseline

        for attack in ATTACKS:
            if only and attack["id"] != only:
                continue
            mutant_dir = tmpdir / f"m{len(results):02d}"
            shutil.copytree(clean, mutant_dir)
            try:
                touched = attack["mutate"](mutant_dir)
            except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:  # one unusable attack must not stop the battery
                results.append({
                    "id": attack["id"], "finding": attack["finding"],
                    "description": attack["description"], "touched": [],
                    "verifier_exit_code": None, "targets": [],
                    "detected": False, "attributable": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "failed_checks_on_mutant": [],
                })
                continue
            if attack.get("resign"):
                # Re-sign the outer hashes so the *internal* contracts are tested
                # (the re-audit's probes did the same: `resigned_integrity_only`).
                _resign(mutant_dir)
            mutant_zip = tmpdir / f"{attack['id']}.zip"
            repackage(mutant_dir, mutant_zip)
            try:
                exit_code, statuses = verify(mutant_zip, out_dir / attack["id"])
            except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
                results.append({
                    "id": attack["id"], "finding": attack["finding"],
                    "description": attack["description"], "touched": touched,
                    "verifier_exit_code": None, "targets": [],
                    "detected": False, "attributable": False,
                    "error": f"verifier did not produce a report: {exc}",
                    "failed_checks_on_mutant": [],
                })
                continue
            targets = [
                {
                    "check_id": check_id,
                    "baseline": baseline.get(check_id, "ABSENT"),
                    "mutant": statuses.get(check_id, "ABSENT"),
                    "detected": statuses.get(check_id) not in (None, "PASS"),
                    "attributable": baseline.get(check_id) == "PASS",
                }
                for check_id in attack["targets"]
            ]
            results.append({
                "id": attack["id"],
                "finding": attack["finding"],
                "description": attack["description"],
                "touched": [str(Path(p).relative_to(mutant_dir)) for p in touched],
                "verifier_exit_code": exit_code,
                "targets": targets,
                "detected": all(t["detected"] for t in targets),
                "attributable": all(t["attributable"] for t in targets),
                "failed_checks_on_mutant": sorted(
                    k for k, v in statuses.items() if v != "PASS"
                ),
            })

    report = {
        "schema_version": 1,
        "kind": "verifier_attack_report",
        "zip_name": zip_path.name,
        "baseline_exit_code": baseline_exit,
        "baseline_all_pass": all(v == "PASS" for v in baseline.values()),
        "baseline_failed_checks": sorted(k for k, v in baseline.items() if v != "PASS"),
        "roundtrip_identical_to_baseline": roundtrip_ok,
        "attacks": results,
        "attacks_total": len(results),
        "attacks_detected": sum(1 for r in results if r["detected"]),
        "attacks_attributable": sum(1 for r in results if r["attributable"]),
        "all_detected": bool(results) and all(r["detected"] for r in results),
        "all_attributable": bool(results) and all(r["attributable"] for r in results),
    }
    _write_json(out_dir / "ATTACK_REPORT.json", report)
    (out_dir / "ATTACK_REPORT.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 验证器攻击报告",
        "",
        f"- 目标包：`{report['zip_name']}`",
        f"- 基线：exit={report['baseline_exit_code']}，全通过={report['baseline_all_pass']}"
        f"，失败检查={report['baseline_failed_checks'] or '（无）'}",
        f"- 提取/重打包往返与基线一致：{report['roundtrip_identical_to_baseline']}",
        f"- 攻击：{report['attacks_detected']}/{report['attacks_total']} 被检出，"
        f"{report['attacks_attributable']}/{report['attacks_total']} 可归因（基线该检查为 PASS）",
        "",
        "| 攻击 | 条目 | 变异 | 目标检查 | 基线 | 变异后 | 检出 | 可归因 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for attack in report["attacks"]:
        for target in attack["targets"]:
            lines.append(
                f"| `{attack['id']}` | {attack['finding']} | {attack['description']} "
                f"| `{target['check_id']}` | {target['baseline']} | {target['mutant']} "
                f"| {target['detected']} | {target['attributable']} |"
            )
    lines += ["", "## 每条攻击触动的文件", ""]
    for attack in report["attacks"]:
        lines.append(f"- `{attack['id']}`：{', '.join(attack['touched'])}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="attack the dossier verifier")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    report = run_attacks(
        Path(args.zip).expanduser(), Path(args.out).expanduser(), args.only
    )
    print(json.dumps({
        "all_detected": report["all_detected"],
        "attacks": f"{report['attacks_detected']}/{report['attacks_total']}",
        "attributable": f"{report['attacks_attributable']}/{report['attacks_total']}",
        "baseline_all_pass": report["baseline_all_pass"],
        "baseline_failed": report["baseline_failed_checks"],
        "report": str(Path(args.out).expanduser() / "ATTACK_REPORT.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if report["all_detected"] else 1


if __name__ == "__main__":
    sys.exit(main())
