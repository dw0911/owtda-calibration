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

import csv
import io

import repo_guard
import resource_sampler

from owtda_cal import chains, dgp, freeze, indexes, scope
from owtda_cal import smoke as smoke_mod
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
        ("AMENDMENT_REGISTRY.jsonl",
         {"AM_PARALLELISM_DECOUPLING", "AM_TOOLING_SCOPE", "AM_RESOURCE_INSTRUMENT"}),
        ("INVALIDATION_REGISTRY.jsonl",
         {"INV_S01_SMOKE", "INV_V12_SOURCE_ANCHOR", "INV_S03_G3_REVOKED"}),
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


def _smoke_root(d: Dossier) -> str | None:
    """Locate the smoke evidence directory by generation (never hard-code S03).

    Audit phase three promotes the smoke generation; a verifier with the old
    generation baked into its paths would silently look in the wrong place.
    """
    for generation in ("S04", "S05", "S06", "S03", "S02", "S01"):
        root = f"evidence/smoke/{generation}"
        if d.has(f"{root}/provenance_manifest.json"):
            return root
    return None


def verify_smoke(d: Dossier, manifest: dict[str, Any], staging: Path) -> None:
    smoke_root = _smoke_root(d)
    check("smoke.evidence_present", "smoke 证据目录存在（按代次发现，不硬编码）",
          smoke_root is not None, smoke_root, "evidence/smoke/<generation>", None)
    if smoke_root is None:
        return
    provenance = d.json(f"{smoke_root}/provenance_manifest.json")
    check("smoke.provenance_binds_manifest",
          f"{smoke_root} provenance 绑定当前冻结身份",
          provenance["freeze_id"] == manifest["freeze_id"]
          and provenance["source_tree_hash"] == manifest["source_tree_hash"]
          and provenance["environment_lock_hash"] == manifest["environment_lock_hash"],
          {"freeze_id": provenance["freeze_id"][:12]}, None,
          "{smoke_root}/provenance_manifest.json")
    check("smoke.open_runs_empty", "open_runs 为空",
          provenance["open_runs"] == [], provenance["open_runs"], [],
          "{smoke_root}/provenance_manifest.json")
    check("smoke.workers_recorded_and_consistent",
          "运行级并行度：声明 == 实际",
          provenance["workers_used"] == provenance["declared_workers"],
          {"used": provenance["workers_used"], "declared": provenance["declared_workers"]},
          None, "{smoke_root}/provenance_manifest.json")

    for phase, expected_rows, expected_windows in (
        ("SMOKE_NULL", 3584, 73600), ("SMOKE_ALT", 1024, 49152),
    ):
        ledger = d.read(f"{smoke_root}/{phase}/evaluation_rows.jsonl")
        rows = [line for line in ledger.splitlines() if line.strip()]
        check(f"smoke.{phase}.row_count", f"{phase} 行数 == {expected_rows}",
              len(rows) == expected_rows, len(rows), expected_rows,
              f"{smoke_root}/{phase}/evaluation_rows.jsonl")

        seal = d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        # run_registry.record_seal hashes the canonical bytes of the payload
        # *before* seal_id/smoke_seal_hash are attached.
        payload = {
            k: v for k, v in seal.items() if k not in ("seal_id", "smoke_seal_hash")
        }
        recomputed = _sha256(canonical_json_bytes(payload) + b"\n")
        check(f"smoke.{phase}.seal_hash", f"{phase} seal 哈希可复算",
              recomputed == seal["smoke_seal_hash"], recomputed[:16],
              seal["smoke_seal_hash"][:16], f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        check(f"smoke.{phase}.seal_binds_ledger", f"{phase} seal 绑定交付的 ledger 字节",
              seal["ledger_content_hash"] == _sha256(ledger),
              seal["ledger_content_hash"][:16], _sha256(ledger)[:16],
              f"{smoke_root}/{phase}/evaluation_rows.jsonl")
        # Audit A05: the seal's own booleans are NOT the verdict.  The identity
        # closure is recomputed from the frozen specification (set equality plus
        # row-by-row foreign keys) and the terminal state is replayed from the
        # registries; the declared values are only *cross-checked*.
        rows = [
            json.loads(line)
            for line in ledger.decode("utf-8").splitlines()
            if line.strip()
        ]
        replicates = int(d.json("governance/SMOKE_CONFIG_v1.json")["replicates_per_cell"])
        try:
            closure = smoke_mod.assert_smoke_ledger_matches_expected(
                ctx=smoke_mod.smoke_context(manifest, phase),
                replicate_count=replicates,
                ledger_rows=rows,
            )
            closure_ok, closure_detail = True, closure
        except ValueError as exc:  # the expectation is the specification's
            closure_ok, closure_detail = False, str(exc)
        check(f"smoke.{phase}.closure_recomputed",
              f"{phase} 身份闭合由规格独立重算（集合相等 + 逐行外键）",
              closure_ok, closure_detail,
              "no exception; ledger ids == spec-derived ids",
              f"{smoke_root}/{phase}/evaluation_rows.jsonl")

        declared = (
            bool(seal["counts_match_contract"])
            and bool(seal["formal_id_leak_check_passed"])
            and bool(seal["identity_closure_passed"])
            and seal["unexplained_errors"] == 0
            and seal["missing_required_fields"] == 0
            and seal["ph_windows"] == expected_windows
        )
        # A08: the resource claims are recomputed against the frozen limits, and
        # must name the run they were sampled from.
        limits = resource_sampler.load_limits()
        resource_verdict = resource_sampler.resource_verdict(
            seal.get("resources"),
            limits=limits,
            unexplained_errors=int(seal["unexplained_errors"]),
        )
        check(f"smoke.{phase}.resources_recomputed",
              f"{phase} 资源（峰值 RSS／swap 增长／磁盘）按冻结限值独立重算",
              resource_verdict["passed"],
              resource_verdict["observed"], limits,
              f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        check(f"smoke.{phase}.resources_bound_to_run",
              f"{phase} 资源记录绑定到同一次 run（run_id 一致）",
              bool(seal.get("resources"))
              and seal["resources"].get("run_id") == seal["run_id"]
              and seal["resources"].get("phase") == phase,
              {"resources_run_id": (seal.get("resources") or {}).get("run_id"),
               "seal_run_id": seal["run_id"]},
              "equal run ids", f"{smoke_root}/SMOKE_SEAL_{phase}.json")

        check(f"smoke.{phase}.declared_matches_recomputed",
              f"{phase} seal 自报与独立重算**都为通过**（任一为否即失败）",
              declared and closure_ok,
              {"declared": declared, "recomputed": closure_ok},
              "both PASS", f"{smoke_root}/SMOKE_SEAL_{phase}.json")

    run_events = [
        json.loads(line)
        for line in d.read(f"{smoke_root}/RUN_REGISTRY.jsonl")
        .decode("utf-8").splitlines() if line.strip()
    ]
    state_events = [
        json.loads(line)
        for line in d.read(f"{smoke_root}/STATE_REGISTRY.jsonl")
        .decode("utf-8").splitlines() if line.strip()
    ]
    check("smoke.run_registry_present", "RUN/STATE 注册表存在且非空",
          bool(run_events) and bool(state_events),
          {"run_events": len(run_events), "state_events": len(state_events)}, ">0",
          f"{smoke_root}/RUN_REGISTRY.jsonl")
    terminal: dict[str, str] = {}
    for event in state_events:
        terminal[str(event.get("run_id"))] = str(event.get("event_type"))
    check("smoke.terminal_states_exact",
          "STATE 注册表每个 run 的终态恰为 RUN_SEALED（精确匹配，非『非空即可』）",
          bool(terminal) and all(v == "RUN_SEALED" for v in terminal.values()),
          terminal, {"every run": "RUN_SEALED"},
          f"{smoke_root}/STATE_REGISTRY.jsonl")
    for phase in ("SMOKE_NULL", "SMOKE_ALT"):
        seal = d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        registry_state = terminal.get(seal["run_id"])
        check(f"smoke.{phase}.seal_terminal_matches_registry",
              f"{phase} seal 声明的终态 == 注册表重放的终态",
              seal["terminal_state"] == registry_state == "RUN_SEALED",
              {"seal": seal["terminal_state"], "registry": registry_state},
              "RUN_SEALED",
              f"{smoke_root}/SMOKE_SEAL_{phase}.json")

    # --- admission recomputed with the *current* semantics ------------------- #
    # AM_RESOURCE_MEASUREMENT_SEMANTICS retired a check that was named for paging but
    # measured commit charge.  The sealed runs still carry the verdict they were
    # computed with, so the dossier must show a *recomputed* verdict and prove that
    # the only reason the inline one differs is that retired check.
    limits = resource_sampler.load_limits()
    recomputed_resources = {
        phase: resource_sampler.resource_verdict(
            d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json").get("resources"),
            limits=limits,
            unexplained_errors=int(
                d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json")["unexplained_errors"]
            ),
        )
        for phase in ("SMOKE_NULL", "SMOKE_ALT")
    }
    check("smoke.resource_admission_recomputed",
          "按现行语义重算：两 phase 的声明资源条件均满足（峰值 RSS / 机器级页文件增长 / 错误 / 磁盘）",
          all(v["passed"] for v in recomputed_resources.values()),
          {phase: v["checks"] for phase, v in recomputed_resources.items()},
          "all true", f"{smoke_root}/SMOKE_SEAL_*.json")

    amendments = [
        json.loads(line)
        for line in d.read("governance/AMENDMENT_REGISTRY.jsonl").decode("utf-8").splitlines()
        if line.strip()
    ]
    retired = sorted(
        {
            event["retired_check"]
            for event in amendments
            if event.get("retired_check") and event.get("change_id")
            == "AM_RESOURCE_MEASUREMENT_SEMANTICS"
        }
    )
    inline = provenance.get("verdict") or {}
    inline_failing = sorted(k for k, ok in (inline.get("checks") or {}).items() if not ok)
    inline_resource_failures = {
        phase: sorted(
            name
            for name, ok in (
                (inline.get("resources") or {}).get(phase, {}).get("checks") or {}
            ).items()
            if not ok
        )
        for phase in ("SMOKE_NULL", "SMOKE_ALT")
    }
    disclosed = (
        bool(retired)
        and inline_failing in ([], ["resource_admission"])
        and all(set(names) <= set(retired) for names in inline_resource_failures.values())
        and all(recomputed_resources[phase]["passed"] for phase in recomputed_resources)
    )
    check("smoke.inline_verdict_disclosed",
          "运行内联判定与重算不一致时：其唯一依据是已登记的退役检查（不是未解释的分歧）",
          disclosed,
          {"inline_failing": inline_failing,
           "inline_resource_failures": inline_resource_failures,
           "retired_checks": retired,
           "recomputed_passed": {p: v["passed"] for p, v in recomputed_resources.items()}},
          None, "governance/AMENDMENT_REGISTRY.jsonl")


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
    # Re-audit 2026-09-12: the delivered JUnit was byte-identical to the previous
    # submission's (544 tests, source 265c9151...) while the current source collects
    # 636 -- the evidence was from the *previous* source generation.  The evidence must
    # therefore name the current fingerprints, and the test count must be derived from
    # the delivered tree rather than from a literal threshold.
    environment = d.json("evidence/verification/validation_environment.json")
    collection = (
        d.json("evidence/verification/collection_manifest.json")
        if d.has("evidence/verification/collection_manifest.json") else None
    )
    check("verification.collection_manifest_present",
          "收集清单随包（缺它就无法把测试数与交付测试树绑定）",
          collection is not None,
          {"present": collection is not None}, None,
          "evidence/verification/collection_manifest.json")
    freeze_manifest = d.json("governance/FREEZE_MANIFEST.json")
    delivered_tests = sorted(
        name.split("repo/tests/", 1)[1]
        for name in d.members()
        if name.startswith("repo/tests/") and name.endswith(".py")
        and name.rsplit("/", 1)[-1].startswith("test_")
    )
    check("verification.bound_to_current_source",
          "测试证据绑定当前源码/环境指纹（上一代源码的 XML 必须被拒）",
          environment.get("source_tree_hash") == freeze_manifest["source_tree_hash"]
          and environment.get("environment_lock_hash")
          == freeze_manifest["environment_lock_hash"]
          and environment.get("freeze_id") == freeze_manifest["freeze_id"],
          {"evidence_source": str(environment.get("source_tree_hash"))[:16],
           "current_source": freeze_manifest["source_tree_hash"][:16],
           "evidence_env": str(environment.get("environment_lock_hash"))[:16],
           "current_env": freeze_manifest["environment_lock_hash"][:16]},
          None, "evidence/verification/validation_environment.json")
    check("verification.collection_matches_delivered_tests",
          "收集清单 == 交付的测试文件集合，且 JUnit 用例数 == 收集数（不写死门槛）",
          bool(collection)
          and collection["test_files"] == delivered_tests
          and collection["collected_count"] == collection["junit_testcases"],
          {"manifest_files": len(collection["test_files"]) if collection else None,
           "delivered_files": len(delivered_tests),
           "collected": collection["collected_count"] if collection else None,
           "junit": collection["junit_testcases"] if collection else None},
          None, "evidence/verification/collection_manifest.json")

    xml_bytes = d.read("evidence/verification/pytest_full.xml")
    root = ElementTree.fromstring(xml_bytes)
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    tests = int(suite.get("tests", "0"))
    failures = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    check("verification.pytest_xml", "原始 JUnit XML：无失败，且用例数 == 收集清单数",
          failures == 0 and bool(collection)
          and tests == collection["collected_count"],
          {"tests": tests, "failures": failures,
           "collected": collection["collected_count"] if collection else None},
          {"failures": 0, "tests": ">500"}, "evidence/verification/pytest_full.xml")
    check("verification.logs_present", "原始日志（pytest/ruff）随包",
          d.has("evidence/verification/pytest_full.log")
          and d.has("evidence/verification/ruff_check.log"),
          None, None, "evidence/verification/")


def _csv_rows(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8").lstrip("\ufeff")
    return [row for row in csv.DictReader(io.StringIO(text)) if row]


def verify_internal_contracts(
    d: Dossier, manifest: dict[str, Any], smoke_root: str
) -> None:
    """Recompute what the seals claim, from the files they point at.

    Re-audit 2026-09-12: eight probes that re-signed the outer integrity hashes were
    all accepted (58/58), so the internal contracts are re-derived here rather than
    read off summary booleans: the scope CSV a seal names, the p-value arithmetic of
    every ledger row, the internal consistency of the resource record, the ``state``
    field of every state event, both registry hash chains, the full H1 join set, and
    the delivered lifecycle-fixture seals.
    """
    limits = resource_sampler.load_limits()

    # 1) the scope CSV the seal names must exist, hash to that name, and carry
    #    exactly the specification's cells (this is the gate that keeps the A01
    #    class of defect from recurring).
    for phase in ("SMOKE_NULL", "SMOKE_ALT"):
        seal = d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        scope_hash = seal["scope_design_hash"]
        rel = f"governance/SCOPE_DESIGN_{phase}_{scope_hash}.csv"
        if not d.has(rel):
            check(f"scope.{phase}.file_present", f"{phase} seal 引用的 scope CSV 随包",
                  False, rel, None, rel)
            continue
        rows = _csv_rows(d.read(rel))
        expected = smoke_mod.enumerate_smoke_expected(
            ctx=smoke_mod.smoke_context(manifest, phase),
            replicate_count=int(seal["replicates_per_cell"]),
        )
        # Compare the delivered rows against the *specification*, as a set of
        # (cell, feature, method) triples: a swapped or edited cell id changes the
        # set, which a count or a summary boolean cannot see.  (The hash in the file
        # name is the builder's own scope-design hash over rows, not the file bytes.)
        triples = {
            (r["logical_cell_id"], r["feature_id"], r["method_id"]) for r in rows
        }
        expected_triples = {
            (r["logical_cell_id"], r["feature_id"], r["method_id"])
            for r in expected.rows
        }
        counts_ok = all(
            int(r["expected_logical_evaluations"]) == int(seal["replicates_per_cell"])
            for r in rows
        )
        check(f"scope.{phase}.rows_equal_spec",
              f"{phase} scope 行集合 == 规格派生集合（cell×feature×method，逐行比对）",
              bool(expected_triples) and triples == expected_triples and counts_ok,
              {"rows": len(rows), "expected_rows": len(expected_triples),
               "scope_only": sorted(triples - expected_triples)[:2],
               "spec_only": sorted(expected_triples - triples)[:2],
               "replicates_per_row_ok": counts_ok},
              None, rel)

    # 2) p-value arithmetic, row by row: p = (K+1)/1000, 0 <= K <= 999,
    #    reject = 1{K <= 49} (re-audit §一).
    for phase in ("SMOKE_NULL", "SMOKE_ALT"):
        rel = f"{smoke_root}/{phase}/evaluation_rows.jsonl"
        rows = [json.loads(line) for line in d.read(rel).decode("utf-8").splitlines()
                if line.strip()]
        bad: list[dict[str, Any]] = []
        for row in rows:
            p = row.get("p_value")
            k = row.get("exceed_count")
            if not isinstance(p, (int, float)) or not (0.001 <= float(p) <= 1.0):
                bad.append({"id": str(row.get("evaluation_id"))[:12], "p": p})
                continue
            expected_k = round(float(p) * 1000) - 1
            if k != expected_k:
                bad.append({"id": str(row.get("evaluation_id"))[:12], "p": p,
                            "exceed_count": k, "expected": expected_k})
            elif bool(row.get("reject")) != bool(expected_k <= 49):
                bad.append({"id": str(row.get("evaluation_id"))[:12], "p": p,
                            "reject": row.get("reject"), "expected_reject": expected_k <= 49})
        check(f"ledger.{phase}.p_value_formula",
              f"{phase} 每行 p=(K+1)/1000 且 reject=1{{K<=49}}（逐行重算）",
              bool(rows) and not bad,
              {"rows": len(rows), "bad": bad[:3]}, None, rel)

    # 3) the resource record must be internally consistent, and the paging metric
    #    must actually cover what was persisted (re-audit §二/5).
    for phase in ("SMOKE_NULL", "SMOKE_ALT"):
        seal = d.json(f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        res = seal.get("resources") or {}
        pairs = (
            ("host_swap", "host_swap_peak_bytes", "host_swap_before_bytes",
             "host_swap_growth_bytes"),
            ("own_commit_charge", "own_commit_charge_peak_bytes",
             "own_commit_charge_before_bytes", "own_commit_charge_growth_bytes"),
        )
        deltas = {}
        consistent = True
        for name, peak, before, growth in pairs:
            p, b, g = res.get(peak), res.get(before), res.get(growth)
            if all(isinstance(v, int) for v in (p, b, g)):
                deltas[name] = {"peak_minus_before": p - b, "growth": g}
                consistent = consistent and (p - b == g) and g >= 0
            else:
                consistent = False
                deltas[name] = {"missing": [peak, before, growth]}
        check(f"resources.{phase}.internally_consistent",
              f"{phase} 资源记录自洽（peak-before == growth，且 growth >= 0）",
              consistent, deltas, None, f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        written = res.get("evidence_bytes_written")
        persisted = int(seal["ledger_bytes"])
        check(f"resources.{phase}.covers_persistence",
              f"{phase} 资源记录覆盖持久化输出（写入字节 >= 账本字节）",
              isinstance(written, int) and written >= persisted,
              {"evidence_bytes_written": written, "ledger_bytes": persisted},
              None, f"{smoke_root}/SMOKE_SEAL_{phase}.json")
        # Disk: the registered formula is estimated_peak_disk = SCALE * persisted, with
        # SCALE = 1.25; the acceptance envelope additionally names the copies a formal
        # run has on disk at peak, so "not yet counted" never hides behind a single
        # number (re-audit ruling 2026-09-12: save / merge / seal / recovery overhead
        # must be listed separately).
        SCALE = 1.25
        components = {
            "ledger": persisted,
            "staging_copy": persisted,      # written before the rename
            "sealed_final_copy": persisted,  # coexists with staging only transiently
            "recovery_copy": persisted,      # repair/orphan recomputation keeps both
            "archive_copy": persisted,       # the delivered archive
        }
        worst_case = int(SCALE * sum(components.values()))
        free = res.get("disk_free_before_bytes")
        check(f"resources.{phase}.disk_estimate_within_rule",
              f"{phase} 磁盘峰值估计（登记公式 + 单列未计入开销）满足 <= 0.8*F_free",
              isinstance(free, int) and free > 0 and worst_case <= 0.8 * free,
              {"components_bytes": components, "estimated_peak_disk": worst_case,
               "free_bytes": free, "scale": SCALE,
               "note": "conservative envelope, not an expected value"},
              {"rule": limits["disk_rule"]}, f"{smoke_root}/SMOKE_SEAL_{phase}.json")

    # 4) every state event must agree with its own ``state`` field.
    state_events = [
        json.loads(line)
        for line in d.read(f"{smoke_root}/STATE_REGISTRY.jsonl").decode("utf-8").splitlines()
        if line.strip()
    ]
    mismatched = [
        {"run_id": e.get("run_id"), "event_type": e.get("event_type"),
         "state": e.get("state")}
        for e in state_events if e.get("state") != e.get("event_type")
    ]
    check("state.events_self_consistent",
          "STATE 每个事件的 state 字段 == event_type（封存事件名配 RUN_OPEN 必须被抓）",
          bool(state_events) and not mismatched, {"events": len(state_events),
                                                 "mismatched": mismatched[:3]},
          None, f"{smoke_root}/STATE_REGISTRY.jsonl")

    # 5) both registry hash chains must recompute and link.
    for name, field in (
        ("RUN_REGISTRY.jsonl", "run_registry_event_hash"),
        ("STATE_REGISTRY.jsonl", "state_registry_event_hash"),
    ):
        tip = None
        linked = True
        recomputes = True
        events = [
            json.loads(line)
            for line in d.read(f"{smoke_root}/{name}").decode("utf-8").splitlines()
            if line.strip()
        ]
        for event in events:
            body = {k: v for k, v in event.items() if k != field}
            if body.get("prev_event_hash") != tip:
                linked = False
            if chains.event_hash(body) != event.get(field):
                recomputes = False
            tip = event.get(field)
        check(f"registry.{name}.chain",
              f"{name} 事件哈希可复算且 prev 链接完整",
              bool(events) and linked and recomputes,
              {"events": len(events), "linked": linked, "recomputes": recomputes},
              None, f"{smoke_root}/{name}")

    # 6) the H1 source-null join must be the *full* set, not a surviving subset.
    packet = d.json("governance/H1_CONSTRUCT_REVIEW_PACKET.json")
    joins = packet["evidence"].get("null_scope_join", [])
    expected_keys = {(c.scenario, c.rho, c.stride) for c in scope.h1_alt_cells()}
    joined_keys = {
        (entry.get("scenario"), entry.get("rho"), entry.get("stride")) for entry in joins
    }
    check("h1.join_complete",
          "H1 source-null 外键覆盖全部 8 个 cell（缺项即失败，不接受子集）",
          bool(expected_keys) and joined_keys == expected_keys,
          {"joined": len(joined_keys), "expected": len(expected_keys),
           "missing": sorted(str(k) for k in expected_keys - joined_keys)[:3]},
          None, "governance/H1_CONSTRUCT_REVIEW_PACKET.json")

    # 7) the delivered fixture seals must exist and be the ones the chain names.
    fixture_dir = "evidence/fixture"
    required = (
        "PHASE_SEAL_TEST_PREDICTION.json", "PHASE_SEAL_TEST_ANALYSIS.json",
        "LIFECYCLE_FIXTURE.json", "expected_evaluation_index.json",
    )
    missing = [name for name in required if not d.has(f"{fixture_dir}/{name}")]
    check("fixture.seals_present",
          "fixture 的 seal 与工件全部随包（缺任一即失败，而不是整段中止）",
          not missing, {"missing": missing}, None, fixture_dir)
    if missing:
        return
    prediction = d.json(f"{fixture_dir}/PHASE_SEAL_TEST_PREDICTION.json")
    analysis = d.json(f"{fixture_dir}/PHASE_SEAL_TEST_ANALYSIS.json")
    report = d.json(f"{fixture_dir}/LIFECYCLE_FIXTURE.json")
    evaluation_rows = json.loads(
        d.read(f"{fixture_dir}/expected_evaluation_index.json").decode("utf-8")
    )
    ledger = b"".join(canonical_json_bytes(r) + b"\n" for r in evaluation_rows)
    chain = report["chain"]
    check("fixture.seals_match_chain",
          "fixture 两段 phase seal 与链事件互相印证（含分析封存的父链与账本绑定）",
          indexes.phase_seal_hash(prediction) == chain[0]["new_phase_seal_hash"]
          and indexes.phase_seal_hash(analysis) == chain[1]["new_phase_seal_hash"]
          and analysis["parent_phase_seal_hash"]
          == indexes.phase_seal_hash(prediction)
          and analysis["active_ledger_content_hash"]
          == hashlib.sha256(ledger).hexdigest(),
          {"prediction_matches": indexes.phase_seal_hash(prediction)
           == chain[0]["new_phase_seal_hash"],
           "analysis_matches": indexes.phase_seal_hash(analysis)
           == chain[1]["new_phase_seal_hash"],
           "parent_bound": analysis["parent_phase_seal_hash"]
           == indexes.phase_seal_hash(prediction),
           "ledger_recomputes": analysis["active_ledger_content_hash"]
           == hashlib.sha256(ledger).hexdigest()},
          None, fixture_dir)

    # Re-audit 2026-09-12: metadata alone is not a lifecycle.  The delivered fixture
    # must show a real computation, a shard commit with both recovery paths, a RUN_SEAL
    # referenced by the phase seals, and a bound analysis entry with an output.
    execution = d.json(f"{fixture_dir}/EXECUTION_CHAIN.json")
    check("fixture.execution_chain",
          "fixture 真实执行链随包（真实计算 / 分片提交与两类恢复 / RUN_SEAL / 分析输出）",
          execution["computation"]["rows"] > 0
          and execution["computation"]["B"] == 999
          and set(execution["computation"]["features"]) == {"bpi", "moments"}
          and execution["shards"]["idempotent_recommit"] is True
          and execution["shards"]["deleted_final_blocked"] is True
          and execution["shards"]["orphan_refused"] is True
          and execution["shards"]["orphan_committed_by_repair"] is True,
          {"computation": execution["computation"], "shards": execution["shards"]},
          None, f"{fixture_dir}/EXECUTION_CHAIN.json")
    check("fixture.phase_seals_carry_source_run_seal",
          "两段 phase seal 的 ordered_source_run_seal_hashes 指向真实 RUN_SEAL（非空且一致）",
          bool(prediction["ordered_source_run_seal_hashes"])
          and prediction["ordered_source_run_seal_hashes"]
          == analysis["ordered_source_run_seal_hashes"]
          == [execution["run_seal_hash"]]
          and bool(prediction["ordered_upstream_artifact_refs"])
          and bool(analysis["ordered_upstream_artifact_refs"]),
          {"prediction": prediction["ordered_source_run_seal_hashes"][:1],
           "analysis": analysis["ordered_source_run_seal_hashes"][:1],
           "run_seal": execution["run_seal_hash"]},
          None, fixture_dir)
    analysis_input = d.json(f"{fixture_dir}/analysis_input.json")
    analysis_output = d.json(f"{fixture_dir}/analysis_output.json")
    check("fixture.analysis_entry_bound",
          "分析入口绑定 phase seal，输出为描述性且绑定账本哈希",
          analysis_input.get("analysis_seal_hash") == indexes.phase_seal_hash(analysis)
          and bool(analysis_input.get("phase_seal_hashes"))
          and analysis_output.get("descriptive_only") is True
          and analysis_output.get("ledger_sha256")
          == execution["computation"]["ledger_sha256"],
          {"phase_seal_hashes": len(analysis_input.get("phase_seal_hashes") or []),
           "descriptive_only": analysis_output.get("descriptive_only"),
           "ledger_bound": analysis_output.get("ledger_sha256")
           == execution["computation"]["ledger_sha256"]},
          None, f"{fixture_dir}/analysis_output.json")


def verify_governance_extras(d: Dossier, manifest: dict[str, Any]) -> None:
    packet = d.json("governance/H1_CONSTRUCT_REVIEW_PACKET.json")
    statuses = [c["status"] for c in packet["contracts"]]
    check("h1.review_packet",
          "H1 复审包逐条合同均为 PASS（不是只看汇总标志）",
          bool(statuses) and packet["all_contracts_pass"]
          and all(s == "PASS" for s in statuses),
          {"contracts": len(statuses), "summary": packet["all_contracts_pass"],
           "non_pass": [c["check_id"] for c in packet["contracts"] if c["status"] != "PASS"]},
          None, "governance/H1_CONSTRUCT_REVIEW_PACKET.json")

    # Audit A06: the source-null foreign key is recomputed here from the frozen
    # context, so a packet whose ids point somewhere else cannot pass by simply
    # declaring itself consistent.
    freeze_manifest = d.json("governance/FREEZE_MANIFEST.json")
    # Two H1 cells share (scenario, stride) and differ only in rho, so rho must be
    # part of the lookup key -- keying on (scenario, stride) silently compares
    # against the wrong cell.
    cells_by_key = {
        (c.scenario, c.rho, c.stride): c for c in scope.h1_alt_cells()
    }
    deviations: list[dict[str, Any]] = []
    joins = packet["evidence"].get("null_scope_join", [])
    for entry in joins:
        cell = cells_by_key.get(
            (entry.get("scenario"), entry.get("rho"), entry.get("stride"))
        )
        if cell is None:
            deviations.append({"scenario": entry.get("scenario"),
                               "rho": entry.get("rho"),
                               "stride": entry.get("stride"), "reason": "unknown cell"})
            continue
        expected_id = scope.logical_cell_id(
            project_id=freeze_manifest["project_id"],
            protocol_id=freeze_manifest["protocol_id"],
            freeze_id=freeze_manifest["freeze_id"],
            evidence_generation_id=freeze_manifest["evidence_generation_id"],
            phase=scope.PHASE_NULL,
            DGP_family=dgp.DGP_FAMILY_N_CIRCLE,
            scenario_id=scope.SCENARIO_NULL,
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M,
        )
        expected_signature = dgp.build_null_signature(
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M
        )
        if (entry.get("source_null_logical_cell_id") != expected_id
                or entry.get("null_model_config_hash") != expected_signature):
            deviations.append({
                "scenario": entry.get("scenario"), "stride": entry.get("stride"),
                "declared_id": entry.get("source_null_logical_cell_id"),
                "expected_id": expected_id,
            })
    check("h1.source_null_join_recomputed",
          "H1 每个 cell 的 source-null 外键按冻结上下文独立重算一致",
          bool(joins) and not deviations,
          {"entries": len(joins), "deviations": deviations[:3]},
          "0 deviations", "governance/H1_CONSTRUCT_REVIEW_PACKET.json")
    # Audit A11 (verdict phase four): the TEST-identity lifecycle fixture is
    # delivered as evidence, and its chain must actually close: expected indexes ->
    # shard plan -> phase seal -> analysis seal bound to it, with the TEST identity
    # domain provably disjoint from the formal one.
    fixture = d.json("evidence/fixture/LIFECYCLE_FIXTURE.json")
    chain = fixture["chain"]
    check("fixture.lifecycle_chain",
          "TEST 生命周期 fixture：链走通、分析封存绑定 phase seal、终态激活",
          fixture["verdict"]["admitted"] is True
          and fixture["verdict"]["chain_walked"] is True
          and fixture["verdict"]["analysis_bound_to_phase_seal"] is True
          and fixture["verdict"]["terminal_state"] == "PHASE_ACTIVATED"
          and len(chain) == 2
          and chain[1]["expected_parent_phase_seal_hash"] == chain[0]["new_phase_seal_hash"],
          {"phases": [e["phase"] for e in chain], "counts": fixture["counts"],
           "tip": fixture["hashes"]["phase_state_tip"][:16]},
          None, "evidence/fixture/LIFECYCLE_FIXTURE.json")
    check("fixture.test_identity_domain",
          "TEST 身份域与正式域隔离（构造性不同 id）",
          fixture["identity_domain"] == "TEST"
          and str(fixture["project_id"]).startswith("TEST-")
          and fixture["project_id"] != manifest.get("project_id"),
          {"project_id": fixture["project_id"]}, None,
          "evidence/fixture/LIFECYCLE_FIXTURE.json")

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
    readme = d.read("README.md").decode("utf-8")
    tags_evidence = (
        d.read("evidence/revision/git_show_ref_tags.txt").decode("utf-8").split()
    )
    # `git show-ref --tags` prints "<hash> refs/tags/<tag>": take the tag half.
    freeze_tags = sorted(
        {
            token.split("refs/tags/")[-1]
            for token in tags_evidence
            if "refs/tags/" in token and "freeze" in token
        }
    )
    check("dossier.cover_generated_from_artifacts",
          "README 的 revision 与冻结 tag 自工件派生（tag 不硬编码）",
          manifest["head"][:12] in readme and bool(freeze_tags)
          and any(tag in readme for tag in freeze_tags),
          {"head": manifest["head"][:12], "freeze_tags": freeze_tags[-3:]},
          None, "README.md")


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

        def section(name: str, fn, *args):
            """Run one verification section; a crash is a finding, not an abort.

            A dossier is untrusted input: a malformed object must be *rejected*,
            never allowed to take the verifier down before it writes a report.
            """
            try:
                return fn(*args)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                check(f"verifier.section.{name}",
                      f"{name} 段在异常输入下不崩溃（崩溃即判 FAIL）",
                      False, f"{type(exc).__name__}: {exc}", None, None)
                return None

        section("integrity", verify_package_integrity, d, manifest)
        anchor = section("source", verify_source_anchor, d, _extract_all(d, staging))
        freeze_manifest = section("freeze", verify_freeze_identity, d) or {}
        section("chains", verify_chains, d)
        if freeze_manifest:
            section("smoke", verify_smoke, d, freeze_manifest, staging)
        section("revision", verify_revision, d, staging, anchor)
        section("verification", verify_verification, d)
        section("governance", verify_governance_extras, d, manifest)
        contracts_root = _smoke_root(d)
        if contracts_root and freeze_manifest:
            section("contracts", verify_internal_contracts, d, freeze_manifest,
                    contracts_root)

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
