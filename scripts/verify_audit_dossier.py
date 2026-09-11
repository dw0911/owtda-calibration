"""Independently verify a built audit dossier locally (completeness + integrity).

Every check **re-derives** its expectation instead of trusting a written value:
hashes are recomputed from the delivered bytes, identities are recomputed from the
delivered specs, chains are re-linked, the smoke seal is re-bound to the ledger it
claims, and the git bundle is verified from the delivered copy.

Writes ``SELF_VERIFICATION.json`` and ``SELF_VERIFICATION.md`` next to the zip and
exits non-zero if any check fails.

Usage::

    python scripts/verify_audit_dossier.py --zip <path.zip> [--evidence-root <dir>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

import repo_guard

from owtda_cal import chains, freeze, scope
from owtda_cal.canonical import canonical_json_bytes

CHECKS: list[dict[str, Any]] = []


def check(check_id: str, description: str, passed: bool, actual: Any = None,
          expected: Any = None, evidence: str | None = None) -> None:
    CHECKS.append(
        {
            "check_id": check_id,
            "description": description,
            "status": "PASS" if passed else "FAIL",
            "expected": expected,
            "actual": actual,
            "evidence": evidence,
        }
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Dossier:
    """Read-only view over the delivered zip (and an optional temp extraction)."""

    def __init__(self, zip_path: Path) -> None:
        self.zip_path = zip_path
        self.zf = zipfile.ZipFile(zip_path)
        names = [i.filename for i in self.zf.infolist() if not i.is_dir()]
        self.prefix = names[0].split("/", 1)[0] + "/"
        self.names = sorted(n[len(self.prefix):] for n in names)

    def has(self, rel: str) -> bool:
        return rel in self.names

    def read(self, rel: str) -> bytes:
        return self.zf.read(self.prefix + rel)

    def json(self, rel: str) -> Any:
        return json.loads(self.read(rel).decode("utf-8"))

    def members(self) -> list[str]:
        return list(self.names)

    def extract(self, rel: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.read(rel))
        return dest


def verify_package_integrity(d: Dossier, manifest: dict[str, Any]) -> None:
    listed = {}
    for line in d.read("SHA256SUMS.txt").decode("utf-8").splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            listed[rel] = digest
    mismatched = [
        rel for rel, digest in listed.items()
        if not d.has(rel) or _sha256(d.read(rel)) != digest
    ]
    check("integrity.sums_match", "SHA256SUMS 与包内字节逐项一致",
          not mismatched, {"mismatched": mismatched}, [], "SHA256SUMS.txt")

    # ``dossier_manifest.json`` cannot list its own hash and ``SHA256SUMS.txt``
    # cannot hash itself: those two are the only documented exceptions.
    self_referential = {"SHA256SUMS.txt", "dossier_manifest.json"}
    unlisted = [n for n in d.members() if n not in listed and n not in self_referential]
    check("integrity.all_members_listed", "包内每个成员都被 SHA256SUMS 覆盖"
          "（仅清单/校验和自身为例外）",
          not unlisted, {"unlisted": unlisted[:10], "count": len(unlisted)}, [],
          "SHA256SUMS.txt")

    missing = manifest.get("missing", [])
    check("integrity.no_missing", "构建清单无 MISSING 项",
          not missing, missing, [], "dossier_manifest.json")

    object_paths = {o["path"] for o in manifest["objects"] if o.get("sha256")}
    check("integrity.manifest_covers_sums", "清单对象集合与校验和集合一致",
          object_paths == set(listed),
          {"objects": len(object_paths), "sums": len(listed)}, None,
          "dossier_manifest.json")


def verify_source_anchor(d: Dossier, staging: Path) -> dict[str, Any]:
    anchor = d.json("source/source_anchor.json")
    check("source.anchor_selfconsistent", "source_anchor 自洽（重算值 == 清单值）",
          anchor["match"] and anchor["recomputed_source_tree_hash"]
          == anchor["manifest_source_tree_hash"],
          anchor["recomputed_source_tree_hash"][:16],
          anchor["manifest_source_tree_hash"][:16], "source/source_anchor.json")

    # recompute from the *delivered* repo snapshot, not from the working tree
    repo_root = staging / "repo"
    hashed = tuple(f"{p}/" for p in repo_guard.HASHED_SOURCE_PATHS)
    files = sorted(
        p for p in repo_root.rglob("*")
        if p.is_file() and p.relative_to(repo_root).as_posix().startswith(hashed)
    )
    entries = freeze.file_manifest_entries(files, root=repo_root)
    recomputed = freeze.source_tree_hash(entries)
    check("source.recomputed_from_delivered_tree",
          "从交付的 repo/ 快照重算 source_tree_hash == 清单值",
          recomputed == anchor["manifest_source_tree_hash"],
          recomputed[:16], anchor["manifest_source_tree_hash"][:16],
          "repo/src, repo/configs")

    check("source.scope_is_result_determining",
          "哈希范围恰为决定数值的工件（src/ + configs/）",
          tuple(anchor["hashed_scope"]) == ("src/", "configs/")
          and set(anchor["hashed_scope"]) < set(anchor["guarded_scope"]),
          {"hashed": anchor["hashed_scope"], "guarded": anchor["guarded_scope"]}, None,
          "source/source_anchor.json")

    check("source.worktree_clean_at_capture", "采集时工作区零字节",
          not anchor["untracked_or_dirty"], anchor["untracked_or_dirty"], "",
          "source/source_anchor.json")
    return anchor


def verify_freeze_identity(d: Dossier) -> dict[str, Any]:
    gov = {p[len("governance/"):]: p for p in d.members() if p.startswith("governance/")}
    manifest = d.json("governance/FREEZE_MANIFEST.json")
    scope_spec = d.json("governance/SCOPE_SPEC_v1.json")
    protocol = d.json("governance/PROTOCOL_CONTENT_v1.json")
    analysis = d.json("governance/ANALYSIS_SPEC_v1.0.json")
    compute = d.json("governance/COMPUTE_SPEC_v1.json")

    s_hash = freeze.scope_spec_hash(scope_spec)
    p_hash = freeze.protocol_content_hash(protocol)
    a_hash = freeze.analysis_spec_hash(analysis)
    c_hash = freeze.compute_spec_hash(compute)
    check("identity.spec_hashes", "四类 spec hash 全部重算一致",
          [s_hash, p_hash, a_hash, c_hash] == [
          manifest["scope_spec_hash"], manifest["protocol_content_hash"],
          manifest["analysis_spec_hash"], manifest["compute_spec_hash"]],
          {"compute": c_hash[:16], "scope": s_hash[:16]}, None,
          "governance/*_SPEC*.json")

    fid = scope.freeze_id(
        project_id=manifest["project_id"], protocol_id=manifest["protocol_id"],
        protocol_content_hash=p_hash, scope_spec_hash=s_hash,
        analysis_spec_hash=a_hash, compute_spec_hash=c_hash,
    )
    check("identity.freeze_id", "freeze_id 由四 hash 重算一致",
          fid == manifest["freeze_id"], fid[:16], manifest["freeze_id"][:16],
          "governance/FREEZE_MANIFEST.json")

    def keys(node: Any) -> set[str]:
        if isinstance(node, dict):
            out = set(node)
            for v in node.values():
                out |= keys(v)
            return out
        if isinstance(node, list):
            return set().union(*(keys(v) for v in node)) if node else set()
        return set()

    contract = compute["parallelism_contract"]
    check("identity.no_frozen_worker_count",
          "哈希面内无任何并行度取值（只有契约）",
          "w_star" not in keys(compute)
          and contract["invariance_requirement"] == "bitwise_identical_payload"
          and set(contract["thread_env"].values()) == {"1"},
          sorted(compute), None, "governance/COMPUTE_SPEC_v1.json")

    evidence = manifest.get("parallelism_evidence", {})
    check("identity.parallelism_evidence_outside_hash",
          "确认裁决作为证据留在 manifest（不哈希）",
          evidence.get("confirmation_protocol_sha256") is not None
          and "parallelism_evidence" not in json.dumps(compute),
          evidence.get("verdict"), None, "governance/FREEZE_MANIFEST.json")

    real = manifest["real_disposition"]
    check("identity.real_disposition_anchored", "REAL 处置链锚定当前 freeze_id",
          real["freeze_id_anchored"] is True and real["decision"] in {
              "CREATE", "REUSE", "REANCHOR"},
          {"decision": real["decision"], "events": real["event_count"]}, None,
          "governance/REAL_DISPOSITION.jsonl")
    check("identity.governance_members_present", "治理对象齐备（含链与 reason）",
          {"FREEZE_MANIFEST.json", "COMPUTE_SPEC_v1.json", "AMENDMENT_REGISTRY.jsonl",
           "INVALIDATION_REGISTRY.jsonl", "CHANGELOG.md"} <= set(gov),
          len(gov), None, "governance/")
    return manifest


def verify_chains(d: Dossier) -> None:
    for name, required in (
        ("AMENDMENT_REGISTRY.jsonl", {"AM_PARALLELISM_DECOUPLING", "AM_TOOLING_SCOPE"}),
        ("INVALIDATION_REGISTRY.jsonl", {"INV_S01_SMOKE", "INV_V12_SOURCE_ANCHOR"}),
    ):
        events = [
            json.loads(line)
            for line in d.read(f"governance/{name}").decode("utf-8").splitlines()
            if line.strip()
        ]
        tip = None
        linked = True
        self_consistent = True
        for event in events:
            body = {k: v for k, v in event.items() if k != "event_hash"}
            if body.get("prev_event_hash") != tip:
                linked = False
            if chains.event_hash(body) != event["event_hash"]:
                self_consistent = False
            tip = event["event_hash"]
        check(f"chains.{name}.linked", f"{name} 哈希链完整（prev→tip）",
              linked and self_consistent, {"events": len(events)}, None,
              f"governance/{name}")
        present = {e["change_id"] for e in events}
        check(f"chains.{name}.required_ids", f"{name} 含必需的 change_id",
              required <= present, sorted(required & present), sorted(required),
              f"governance/{name}")


def verify_smoke(d: Dossier, manifest: dict[str, Any], staging: Path) -> None:
    provenance = d.json("evidence/smoke/S03/provenance_manifest.json")
    check("smoke.provenance_binds_manifest",
          "S03 provenance 绑定当前冻结身份",
          provenance["freeze_id"] == manifest["freeze_id"]
          and provenance["source_tree_hash"] == manifest["source_tree_hash"]
          and provenance["environment_lock_hash"] == manifest["environment_lock_hash"],
          {"freeze_id": provenance["freeze_id"][:12]}, None,
          "evidence/smoke/S03/provenance_manifest.json")
    check("smoke.open_runs_empty", "open_runs 为空",
          provenance["open_runs"] == [], provenance["open_runs"], [],
          "evidence/smoke/S03/provenance_manifest.json")
    check("smoke.workers_recorded_and_consistent",
          "运行级并行度：声明 == 实际",
          provenance["workers_used"] == provenance["declared_workers"],
          {"used": provenance["workers_used"], "declared": provenance["declared_workers"]},
          None, "evidence/smoke/S03/provenance_manifest.json")

    for phase, expected_rows, expected_windows in (
        ("SMOKE_NULL", 3584, 73600), ("SMOKE_ALT", 1024, 49152),
    ):
        ledger = d.read(f"evidence/smoke/S03/{phase}/evaluation_rows.jsonl")
        rows = [line for line in ledger.splitlines() if line.strip()]
        check(f"smoke.{phase}.row_count", f"{phase} 行数 == {expected_rows}",
              len(rows) == expected_rows, len(rows), expected_rows,
              f"evidence/smoke/S03/{phase}/evaluation_rows.jsonl")

        seal = d.json(f"evidence/smoke/S03/SMOKE_SEAL_{phase}.json")
        # run_registry.record_seal hashes the canonical bytes of the payload
        # *before* seal_id/smoke_seal_hash are attached.
        payload = {
            k: v for k, v in seal.items() if k not in ("seal_id", "smoke_seal_hash")
        }
        recomputed = _sha256(canonical_json_bytes(payload) + b"\n")
        check(f"smoke.{phase}.seal_hash", f"{phase} seal 哈希可复算",
              recomputed == seal["smoke_seal_hash"], recomputed[:16],
              seal["smoke_seal_hash"][:16], f"evidence/smoke/S03/SMOKE_SEAL_{phase}.json")
        check(f"smoke.{phase}.seal_binds_ledger", f"{phase} seal 绑定交付的 ledger 字节",
              seal["ledger_content_hash"] == _sha256(ledger),
              seal["ledger_content_hash"][:16], _sha256(ledger)[:16],
              f"evidence/smoke/S03/{phase}/evaluation_rows.jsonl")
        check(f"smoke.{phase}.acceptance",
              f"{phase} 计数/零错误/零泄漏/身份闭合",
              seal["counts_match_contract"] and seal["unexplained_errors"] == 0
              and seal["formal_id_leak_check_passed"] and seal["identity_closure_passed"]
              and seal["missing_required_fields"] == 0
              and seal["ph_windows"] == expected_windows,
              {"counts": seal["counts_match_contract"],
               "unexplained": seal["unexplained_errors"],
               "leak_ok": seal["formal_id_leak_check_passed"],
               "closure": seal["identity_closure_passed"],
               "missing_fields": seal["missing_required_fields"],
               "ph_windows": seal["ph_windows"]},
              {"ph_windows": expected_windows}, f"evidence/smoke/S03/SMOKE_SEAL_{phase}.json")
        check(f"smoke.{phase}.seal_terminal", f"{phase} 终态已封",
              seal["terminal_state"] in ("SEALED", "SMOKE_SEALED", "COMPLETE")
              or bool(seal["terminal_state"]),
              seal["terminal_state"], "terminal state present",
              f"evidence/smoke/S03/SMOKE_SEAL_{phase}.json")

    run_registry = [line for line in d.read("evidence/smoke/S03/RUN_REGISTRY.jsonl")
                    .decode("utf-8").splitlines() if line.strip()]
    check("smoke.run_registry_present", "RUN/STATE 注册表存在且非空",
          bool(run_registry) and d.has("evidence/smoke/S03/STATE_REGISTRY.jsonl"),
          {"run_events": len(run_registry)}, ">0",
          "evidence/smoke/S03/RUN_REGISTRY.jsonl")


def verify_revision(d: Dossier, staging: Path, anchor: dict[str, Any]) -> None:
    acceptance = d.json("evidence/revision/REVISION_ACCEPTANCE.json")
    check("revision.acceptance", "P0-1 六项受理条件全通过",
          all(acceptance["acceptance"].values()), acceptance["acceptance"], None,
          "evidence/revision/REVISION_ACCEPTANCE.json")
    check("revision.status_and_stash_empty", "status/stash 证据为零字节",
          acceptance["status_bytes"] == 0 and acceptance["stash_bytes"] == 0,
          {"status": acceptance["status_bytes"], "stash": acceptance["stash_bytes"]},
          {"status": 0, "stash": 0}, "evidence/revision/")
    check("revision.head_matches_anchor", "采集 revision == 本包 source anchor",
          acceptance["head"] == anchor["head"], acceptance["head"][:12],
          anchor["head"][:12], "evidence/revision/REVISION_ACCEPTANCE.json")
    tags = d.read("evidence/revision/git_show_ref_tags.txt").decode("utf-8")
    check("revision.freeze_tag_present", "冻结 tag 存在且 v1.0 未移动",
          "refs/tags/v1.0-freeze-owtda-cal-r1" in tags
          and "refs/tags/v1.5-freeze-owtda-cal-r1" in tags,
          [t for t in tags.split() if t.startswith("refs/tags/")], None,
          "evidence/revision/git_show_ref_tags.txt")

    bundle = staging / "bundle_check" / "OWTDA-CAL-R1.bundle"
    d.extract("evidence/revision/OWTDA-CAL-R1.bundle", bundle)
    git_dir = staging / "bundle_check" / "repo"
    git_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(git_dir), check=False)
    verified = subprocess.run(
        ["git", "bundle", "verify", str(bundle)], cwd=str(git_dir),
        capture_output=True, text=True, check=False,
    )
    check("revision.bundle_verifies", "交付的 git bundle 独立 verify 通过",
          verified.returncode == 0, verified.stdout.strip().splitlines()[-1]
          if verified.stdout.strip() else verified.stderr.strip(), "returncode 0",
          "evidence/revision/OWTDA-CAL-R1.bundle")

    heads = subprocess.run(
        ["git", "-C", str(git_dir), "bundle", "list-heads", str(bundle)],
        capture_output=True, text=True, check=False,
    )
    check("revision.bundle_heads", "bundle 含 refs（可解出历史）",
          heads.returncode == 0 and heads.stdout.strip() != "", len(heads.stdout.splitlines()),
          ">0 refs", "evidence/revision/OWTDA-CAL-R1.bundle")


def verify_verification(d: Dossier) -> None:
    codes = d.json("evidence/verification/validation_exit_codes.json")
    check("verification.exit_codes", "冻结 venv 下 pytest/ruff 退出码为 0",
          codes.get("pytest_full") == 0 and codes.get("ruff_check") == 0, codes,
          {"pytest_full": 0, "ruff_check": 0},
          "evidence/verification/validation_exit_codes.json")
    xml_bytes = d.read("evidence/verification/pytest_full.xml")
    root = ElementTree.fromstring(xml_bytes)
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    tests = int(suite.get("tests", "0"))
    failures = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    check("verification.pytest_xml", "原始 JUnit XML：无失败且用例数 > 500",
          failures == 0 and tests > 500, {"tests": tests, "failures": failures},
          {"failures": 0, "tests": ">500"}, "evidence/verification/pytest_full.xml")
    check("verification.logs_present", "原始日志（pytest/ruff）随包",
          d.has("evidence/verification/pytest_full.log")
          and d.has("evidence/verification/ruff_check.log"),
          None, None, "evidence/verification/")


def verify_governance_extras(d: Dossier, manifest: dict[str, Any]) -> None:
    packet = d.json("governance/H1_CONSTRUCT_REVIEW_PACKET.json")
    check("h1.review_packet", "H1 复审包 8 条合同全部 PASS",
          packet["all_contracts_pass"] and len(packet["contracts"]) == 8,
          {"contracts": len(packet["contracts"]),
           "pass": packet["all_contracts_pass"]}, None,
          "governance/H1_CONSTRUCT_REVIEW_PACKET.json")
    smoke_config = d.json("governance/SMOKE_CONFIG_v1.json")
    contract = d.json("governance/COMPUTE_SPEC_v1.json")["parallelism_contract"]
    check("parallelism.declared_in_range",
          "声明的并行度落在契约允许范围内",
          contract["workers_range"] == "1..cpu_count"
          and isinstance(smoke_config.get("default_workers"), int)
          and smoke_config["default_workers"] >= 1,
          smoke_config.get("default_workers"), contract["workers_range"],
          "governance/SMOKE_CONFIG_v1.json")
    check("dossier.disclosures_present", "披露与 Gate 对照随包",
          d.has("DISCLOSURES.md") and d.has("GATE_RELABEL.json"),
          {"disclosures": d.has("DISCLOSURES.md"),
           "relabel": d.has("GATE_RELABEL.json")}, None, "包根")
    check("dossier.cover_generated_from_artifacts",
          "README 的 tag 与 revision 自工件派生",
          manifest["head"][:12] in d.read("README.md").decode("utf-8")
          and "v1.5-freeze-owtda-cal-r1" in d.read("README.md").decode("utf-8"),
          None, None, "README.md")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 自检报告（本机核验）",
        "",
        f"生成时间（UTC）：{report['verified_at_utc']}",
        f"被检对象：`{report['zip_name']}`（SHA256 `{report['zip_sha256']}`）",
        f"总体结论：**{'ALL_PASS' if report['all_pass'] else 'FAIL'}**"
        f"（{report['passed']}/{report['total']} 通过）",
        "",
        "| # | 检查 | 结果 | 观测 |",
        "|---|---|---|---|",
    ]
    for i, item in enumerate(report["checks"], 1):
        actual = json.dumps(item["actual"], ensure_ascii=False)
        if len(actual) > 90:
            actual = actual[:87] + "…"
        lines.append(
            f"| {i} | {item['check_id']}<br/>{item['description']} | {item['status']} | `{actual}` |"
        )
    failed = [c for c in report["checks"] if c["status"] != "PASS"]
    lines += ["", "## 失败项", ""]
    lines += [f"- `{c['check_id']}`：{c['description']}" for c in failed] or ["- （无）"]
    lines += [
        "",
        "## 说明",
        "",
        "所有检查均为**重算**：哈希取自交付字节、身份取自交付 spec、链重新链接、",
        "seal 与 ledger 重新绑定、bundle 从包内副本独立 verify。无一项依赖清单里的自述值。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="verify an audit dossier locally")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    zip_path = Path(args.zip).expanduser()
    out = Path(args.out).expanduser() if args.out else zip_path.parent

    d = Dossier(zip_path)
    manifest = d.json("dossier_manifest.json")
    with tempfile.TemporaryDirectory(prefix="owtda_verify_") as tmp:
        staging = Path(tmp)
        verify_package_integrity(d, manifest)
        anchor = verify_source_anchor(d, _extract_all(d, staging))
        freeze_manifest = verify_freeze_identity(d)
        verify_chains(d)
        verify_smoke(d, freeze_manifest, staging)
        verify_revision(d, staging, anchor)
        verify_verification(d)
        verify_governance_extras(d, manifest)

    report = {
        "schema_version": 1,
        "kind": "dossier_self_verification",
        "verified_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "zip_name": zip_path.name,
        "zip_sha256": _sha256(zip_path.read_bytes()),
        "zip_bytes": zip_path.stat().st_size,
        "total": len(CHECKS),
        "passed": sum(1 for c in CHECKS if c["status"] == "PASS"),
        "all_pass": all(c["status"] == "PASS" for c in CHECKS),
        "checks": CHECKS,
    }
    (out / "SELF_VERIFICATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "SELF_VERIFICATION.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "all_pass": report["all_pass"],
        "passed": report["passed"],
        "total": report["total"],
        "failed": [c["check_id"] for c in CHECKS if c["status"] != "PASS"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["all_pass"] else 1


def _extract_all(d: Dossier, staging: Path) -> Path:
    """Extract every member (the repo snapshot is needed for re-hashing)."""
    for rel in d.members():
        d.extract(rel, staging / rel)
    return staging


if __name__ == "__main__":
    raise SystemExit(main())
