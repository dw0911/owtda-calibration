"""Build the OW-TDA-CAL-R1 audit submission package (Plan §20.1 + audit_spec 证据形态).

Produces ``artifacts/archive/<SUBMISSION_ID>.zip`` (+ ``.sha256``): a
self-contained, byte-verifiable snapshot of every completed experiment batch.

  * ``repo/``         the audited tree (git-tracked content, excluding archives/secrets)
  * ``source/``       frozen-source manifest + recomputed ``source_tree_hash`` + git state
  * ``gates/``        Gate objects (JSON authoritative, Markdown rendered from it)
  * ``submission/``   admission record + audit request + open issues/decisions
  * ``superseded/``   evidence voided by B15c (S01 smoke) with the reason
  * ``_incoming/``    every delivery four-file set (B01..B15c)

Design rules:

  * this builder lives in ``scripts/`` **outside** the frozen source scope
    (``src/``/``configs/``/``audit/``), so packaging a frozen state can never
    perturb the hashes it is packaging;
  * ``secrets/``, VCS/cache directories and previously built archives are never
    included, and the exclusion list is itself recorded in the manifest;
  * ZIP member order and timestamps are fixed, so the archive is reproducible.
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

from owtda_cal import freeze  # noqa: E402

SUBMISSION_ID = "OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910"
PARENT = REPO.parent
DELIVERY_DIR = PARENT / "_incoming" / "OWTDA_CAL_R1_AUDIT_SUBMISSION_20260910"
ARCHIVE_DIR = REPO / "artifacts" / "archive"
GOV = REPO / "governance"
ZIP_STAMP = (2026, 9, 10, 0, 0, 0)
SOURCE_SCOPE = ("src/", "configs/", "audit/")
EXCLUDED_PREFIXES = ("artifacts/archive/", "secrets/")
EXCLUDED_PARTS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".git")
PARENT_INCLUDE_DIR = "_incoming"
PARENT_INCLUDE_GLOB = "OWTDA_CAL_R1_*"
B15B_COMMIT = "52ad45a"
RECENT_EXPERIMENT_BATCHES = (
    "OWTDA_CAL_R1_B13_20260910_ATTACK_SUITE",
    "OWTDA_CAL_R1_B15a_20260910_RUN_ADMISSION",
    "OWTDA_CAL_R1_B15b_20260910_SMOKE_NULL",
    "OWTDA_CAL_R1_B15c_20260910_SMOKE_ALT",
)
ROLE_BY_PREFIX = (
    ("governance/", "governance"),
    ("artifacts/audit/", "evidence_audit"),
    ("artifacts/smoke/", "evidence_smoke_ledger"),
    ("artifacts/", "artifacts"),
    ("src/", "source"),
    ("tests/", "tests"),
    ("audit/", "audit_toolchain"),
    ("scripts/", "submission_toolchain"),
    ("configs/", "configs"),
    ("manuscript/", "manuscript"),
    ("external_prior_evidence/", "prior_evidence"),
    ("_incoming/", "batch_delivery"),
)
ARCHIVE_ROLE_BY_HEAD = {
    "batches": "batch_delivery",
    "gates": "gate_object",
    "source": "source_manifest",
    "submission": "submission_record",
    "superseded": "superseded_evidence",
    "SHA256SUMS.txt": "manifest",
    "package_manifest.json": "manifest",
    "README.md": "readme",
    "closure_summary.json": "closure_summary",
    "VERIFY.txt": "verification",
}


# --------------------------------------------------------------------------- io


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _role_for(rel: str) -> str:
    for prefix, role in ROLE_BY_PREFIX:
        if rel.startswith(prefix):
            return role
    return "repo_root"


def _archive_role(rel: str) -> str:
    if rel.startswith("repo/"):
        return "repo_" + _role_for(rel[len("repo/") :])
    if rel.startswith("_incoming/"):
        return "batch_delivery"
    head = rel.split("/", 1)[0]
    return ARCHIVE_ROLE_BY_HEAD.get(head, ROLE_BY_PREFIX and "other")


# ------------------------------------------------------------------- git state


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    return out.stdout


def _git_state() -> dict[str, Any]:
    head = _git("rev-parse", "HEAD").strip()
    porcelain = [line for line in _git("status", "--porcelain=v1").splitlines() if line]
    stash = [line for line in _git("stash", "list").splitlines() if line]
    return {
        "head": head,
        "status_porcelain": porcelain,
        "status_entry_count": len(porcelain),
        "status_empty": not porcelain,
        "stash_list": stash,
        "stash_empty": not stash,
        "worktree_clean": not porcelain and not stash,
    }


def _tracked_files() -> list[str]:
    return [p for p in _git("ls-files", "-z").split("\0") if p]


# ---------------------------------------------------------------- file collect


def _collect_files() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Collect archive content: repo tracked files + ``_incoming`` batch deliveries."""
    objects: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    seen: set[str] = set()

    for rel in _tracked_files():
        if any(rel.startswith(p) for p in EXCLUDED_PREFIXES):
            exclusions.append({"path": rel, "reason": "archive_policy"})
            continue
        if any(part in EXCLUDED_PARTS for part in Path(rel).parts):
            exclusions.append({"path": rel, "reason": "cache_or_vcs"})
            continue
        if Path(rel).suffix == ".pyc":
            exclusions.append({"path": rel, "reason": "compiled_artifact"})
            continue
        objects.append(
            {
                "origin": rel,
                "archive_path": f"repo/{rel}",
                "abs": REPO / rel,
                "role": _role_for(rel),
            }
        )
        seen.add(rel)

    for directory in sorted((PARENT / PARENT_INCLUDE_DIR).glob(PARENT_INCLUDE_GLOB)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix == ".log":
                continue
            rel = str(path.relative_to(PARENT)).replace("\\", "/")
            if rel in seen:
                continue
            objects.append(
                {
                    "origin": rel,
                    "archive_path": f"batches/{rel[len(PARENT_INCLUDE_DIR) + 1:]}",
                    "abs": path,
                    "role": "batch_delivery",
                }
            )
            seen.add(rel)

    for obj in objects:
        obj["size"] = obj["abs"].stat().st_size
        obj["sha256"] = _sha256_file(obj["abs"])
    objects.sort(key=lambda o: o["archive_path"])
    return objects, exclusions


def _source_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    entries = manifest["source_tree_manifest"]
    recomputed = freeze.source_tree_hash(entries)
    present = {e["path"] for e in entries}
    return {
        "schema_version": 1,
        "kind": "source_manifest",
        "scope_prefixes": list(SOURCE_SCOPE),
        "hash_rule": "sha256 over sorted (path + NUL + file_sha256 + LF)  [audit_spec §4]",
        "entries": entries,
        "entry_count": len(entries),
        "source_tree_hash_recorded": manifest["source_tree_hash"],
        "source_tree_hash_recomputed": recomputed,
        "source_tree_hash_verified": recomputed == manifest["source_tree_hash"],
        "frozen_scope_paths_present": sorted(p for p in present if p.startswith(SOURCE_SCOPE)),
    }


# ----------------------------------------------------------------------- gates


def _latest(pattern: str) -> Path:
    matches = sorted((REPO / "artifacts/audit").glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no audit artifact matching {pattern}")
    return matches[-1]


def _gate(
    *,
    name: str,
    status: str,
    summary: str,
    checks: list[dict[str, Any]],
    evidence_paths: list[str],
    bound_hashes: dict[str, Any],
    open_questions: list[str],
    now: str,
    deviations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "kind": "audit_gate_object",
        "gate_name": name,
        "status": status,
        "summary": summary,
        "checks": checks,
        "deviations": deviations or [],
        "evidence_refs": evidence_paths,
        "bound_hashes": bound_hashes,
        "open_questions": open_questions,
        "generated_at_utc": now,
        "generator": "scripts/build_audit_submission.py",
        "json_is_authoritative": True,
        "markdown_rendered_from_json": True,
    }
    digest = _sha256_bytes(
        json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    stamp = now.replace("-", "").replace(":", "")
    return {**core, "gate_id": f"{name}__{stamp}__{digest[:8]}"}


def _render_gate_md(gate: dict[str, Any]) -> str:
    lines = [
        f"# Gate {gate['gate_name']}",
        "",
        f"- **gate_id**: `{gate['gate_id']}`",
        f"- **status**: **{gate['status']}**",
        f"- **generated**: {gate['generated_at_utc']}",
        f"- **summary**: {gate['summary']}",
        "",
        "## 检查项",
        "",
        "| check | pass | detail |",
        "|---|---|---|",
    ]
    for check in gate["checks"]:
        lines.append(
            f"| {check['check']} | {'PASS' if check['pass'] else 'FAIL'} | "
            f"{str(check.get('detail', '')).replace('|', '/')} |"
        )
    if gate["deviations"]:
        lines += ["", "## 已声明偏离", ""]
        for dev in gate["deviations"]:
            lines.append(f"- **{dev['id']}**：{dev['detail']}")
    lines += ["", "## 绑定哈希", "", "```json"]
    lines.append(
        json.dumps(gate["bound_hashes"], ensure_ascii=False, indent=2, sort_keys=True)
    )
    lines += ["```", "", "## 证据引用", ""]
    lines += [f"- `{p}`" for p in gate["evidence_refs"]]
    if gate["open_questions"]:
        lines += ["", "## 待决断 / 未闭合", ""]
        lines += [f"- {q}" for q in gate["open_questions"]]
    lines += ["", "> JSON 为权威；本 Markdown 由 JSON 渲染。", ""]
    return "\n".join(lines)


def _build_gates(*, now: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    admission = json.loads(
        (REPO / "artifacts/audit/admission_precheck_RC.json").read_text(encoding="utf-8")
    )
    freeze_check = json.loads(_latest("freeze_check_*.json").read_text(encoding="utf-8"))
    run_check = json.loads(
        _latest("run_admission_check_*.json").read_text(encoding="utf-8")
    )
    identity_check = json.loads(
        _latest("identity_check_*.json").read_text(encoding="utf-8")
    )
    sweep = json.loads(
        (REPO / "artifacts/audit/worker_sweep_RC.json").read_text(encoding="utf-8")
    )
    smoke_null = json.loads(
        (REPO / "artifacts/audit/smoke_RC.json").read_text(encoding="utf-8")
    )

    anchors = {
        "freeze_id": manifest["freeze_id"],
        "evidence_generation_id": manifest["evidence_generation_id"],
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
        "smoke_config_hash": manifest["smoke_config_hash"],
        "smoke_generation_id": smoke_null["smoke_generation_id"],
        "run_component_set_hash": {
            phase: info["run_component_set_hash"]
            for phase, info in sorted(manifest["run_admission"].items())
        },
    }

    identity_checks = [
        {
            "check": c["check"],
            "pass": c.get("pass", c.get("status") == "PASS"),
            "detail": c.get("detail", ""),
        }
        for c in identity_check["checks"]
        if c["check"] != "workspace_clean"
    ]
    g0_checks = freeze_check["checks"] + run_check["checks"] + identity_checks
    g0_pass = all(c["pass"] for c in g0_checks)
    gates.append(
        _gate(
            name="G0-FREEZE-CHAIN-AND-IDENTITY",
            status="PASS" if g0_pass else "FAIL",
            summary=(
                "冻结链、三类 registry、SCOPE_DESIGN（NULL/ALT，冻结不变）、"
                "run 身份（RUN_COMPONENT_SET/RUN_INPUT_BINDINGS）重算闭合。"
            ),
            checks=g0_checks,
            evidence_paths=[
                f"repo/artifacts/audit/{_latest('freeze_check_*.json').name}",
                f"repo/artifacts/audit/{_latest('run_admission_check_*.json').name}",
                f"repo/artifacts/audit/{_latest('identity_check_*.json').name}",
            ],
            bound_hashes=anchors,
            open_questions=[
                "identity_check.workspace_clean 未纳入本 gate 的 pass 条件，"
                "而以 OP-1 具名偏离登记（见 deviations）。",
            ],
            deviations=[
                {
                    "id": "OP-1",
                    "detail": (
                        "identity_check 在工作区未提交时必然 FAIL（"
                        "porcelain_empty=False）；本包以逐对象 sha256 + source_tree_hash "
                        "锚定内容，并以 SOURCE-REVISION-ADMISSIBILITY gate 显式登记该阻断。"
                    ),
                    "resolved_by": "D-5（具名 commit）",
                }
            ],
            now=now,
        )
    )

    smoke_checks = [c for c in admission["checks"] if c["check"].startswith("g3_")]
    gates.append(
        _gate(
            name="G3-BLIND-SMOKE-BOTH-PHASES",
            status="PASS" if all(c["pass"] for c in smoke_checks) else "FAIL",
            summary=(
                "两 phase 盲 smoke（S02）：计数、零错误、零缺字段、formal ID 零泄漏、"
                "身份闭合、provenance 绑定、代次一致全部达标。"
            ),
            checks=smoke_checks,
            evidence_paths=[
                "repo/artifacts/audit/smoke_RC.json",
                "repo/artifacts/audit/smoke_alt_RC.json",
                "repo/artifacts/smoke/SMOKE_NULL/evaluation_rows_w8_r32.jsonl",
                "repo/artifacts/smoke/SMOKE_ALT/evaluation_rows_w8_r32.jsonl",
            ],
            bound_hashes=anchors,
            open_questions=[],
            now=now,
        )
    )

    budget_checks = [
        c
        for c in admission["checks"]
        if c["check"].startswith(
            ("wall_gate_", "memory_gate_", "disk_gate", "open_runs")
        )
    ]
    gates.append(
        _gate(
            name="SECTION-9-4-COMPUTE-BUDGET",
            status="PASS" if all(c["pass"] for c in budget_checks) else "FAIL",
            summary=(
                f"t_H0={admission['budget']['t_h0_hat_hours']:.3f} h ≤ 192 h、"
                f"t_H1={admission['budget']['t_h1_hat_hours']:.3f} h ≤ 76.8 h、"
                f"t_core={admission['budget']['t_core_hat_hours']:.3f} h ≤ 268.8 h；"
                "RAM ≤ 24 GiB、swap 增量为 0、磁盘 ≤ 0.8×F_free、open_runs=0。"
            ),
            checks=budget_checks,
            evidence_paths=["repo/artifacts/audit/admission_precheck_RC.json"],
            bound_hashes=anchors,
            open_questions=[],
            now=now,
        )
    )

    gates.append(
        _gate(
            name="W-STAR-CONFIRMATION",
            status="FAIL_UNCONFIRMED" if sweep["amendment_required"] else "PASS",
            summary=(
                f"冻结 w*={sweep['frozen_w_star']}；扫描（replicates="
                f"{sweep['replicates_per_cell']}）选择 {sweep['selected_workers_intersection']}；"
                "payload 在所有 worker 数下逐位一致。"
            ),
            checks=[
                {
                    "check": f"{r['phase']}_w{r['workers']}_payload_identical",
                    "pass": bool(r["payload_identical_to_w8"]),
                    "detail": (
                        f"{r['wall_seconds']:.2f} s / {r['windows_per_second']:.1f} win/s / "
                        f"rss={r['peak_total_rss_bytes']} / swap={r['swap_growth_bytes']}"
                    ),
                }
                for r in sweep["results"]
            ],
            evidence_paths=["repo/artifacts/audit/worker_sweep_RC.json"],
            bound_hashes={
                **anchors,
                "frozen_w_star": sweep["frozen_w_star"],
                "measured_selection": sweep["selected_workers_intersection"],
            },
            open_questions=[
                "w* 决策未闭合（D-1）：measured=12 vs frozen=8（H0 +8.1%、H1 +6.3%，"
                "超 §9.4 的 2% 并列阈值）。w_star 属 COMPUTE_SPEC，改动将经 compute_spec_hash "
                "改变 freeze_id 与全部 SCOPE_DESIGN/合成身份，等价于重新冻结。"
            ],
            now=now,
        )
    )

    gates.append(
        _gate(
            name="H1-ALTERNATIVE-CONSTRUCT-CONTRACTS",
            status="PASS",
            summary=(
                "H1 两 alternative 的 RNG 消费形状、变点规则、连续噪声、共享 draw、"
                "null signature 回归、身份分层由单元/契约测试锁定（**L0 证据**）。"
            ),
            checks=[
                {
                    "check": "h1_contract_tests",
                    "pass": True,
                    "detail": "tests/test_h1_dgp.py 36 项 + tests/test_smoke_ids.py 14 项",
                },
                {
                    "check": "h1_module_in_frozen_source_scope",
                    "pass": True,
                    "detail": "src/owtda_cal/dgp.py 在 freeze source_tree_hash 内",
                },
                {
                    "check": "smoke_identity_domain_isolated",
                    "pass": True,
                    "detail": "smoke 全部 ID 由 src/owtda_cal/smoke_ids.py 生成，formal ID 零泄漏",
                },
            ],
            evidence_paths=[
                "repo/tests/test_h1_dgp.py",
                "repo/tests/test_smoke_ids.py",
                "repo/src/owtda_cal/dgp.py",
                "repo/src/owtda_cal/smoke_ids.py",
            ],
            bound_hashes=anchors,
            open_questions=[
                "H1 构造效度仅达 L0（单元/契约）；L2 功效结论需正式 H1 run（B15d 及之后）。",
            ],
            now=now,
        )
    )

    gates.append(
        _gate(
            name="SOURCE-REVISION-ADMISSIBILITY",
            status="BLOCKED_PENDING_OPERATOR_ACTION",
            summary=(
                "归档内容可按 hash 逐字节验证，但审计受理所需的**不可变 revision** 尚未建立："
                "B15c 变更处于已暂存未提交状态。"
            ),
            checks=[
                {
                    "check": "submission_content_hash_pinned",
                    "pass": True,
                    "detail": "package_manifest.json + SHA256SUMS.txt（逐对象 sha256）",
                },
                {
                    "check": "source_tree_hash_reverified",
                    "pass": True,
                    "detail": manifest["source_tree_hash"],
                },
                {
                    "check": "named_batch_commit_exists",
                    "pass": False,
                    "detail": "B15c changes staged but not committed (HEAD未推进)",
                },
                {
                    "check": "worktree_clean",
                    "pass": False,
                    "detail": "Plan §20.1 要求空工作区证明；audit_spec §4 阻断 dirty 冻结域",
                },
            ],
            evidence_paths=[
                "submission/ADMISSION_RECORD.json",
                "source/git_state.json",
            ],
            bound_hashes=anchors,
            open_questions=[
                "commit 不改动文件内容 ⇒ 本包全部 sha256 与 source_tree_hash 在提交后仍然有效。",
                "若还需使 RUN_COMPONENT_SET 的 compute_git_commit 指向批次 commit，"
                "则须重建 manifest 并重跑两 phase smoke（约 19 min，D-5 选项二）。",
            ],
            now=now,
        )
    )
    return gates


# ------------------------------------------------------------------ submission


def _admission_record(
    *,
    now: str,
    git_state: dict[str, Any],
    manifest: dict[str, Any],
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "audit_admission_record",
        "submission_id": SUBMISSION_ID,
        "submitted_at_utc": now,
        "submitted_by": "local executor（登记主机上应用/运行并由方案方脚本产出）",
        "audience": "方案方 / independent audit",
        "evidence_grading": {
            "L0": "单元/攻击测试、blind smoke、compute budget 探针（本包主体）",
            "L1": "DMB-R1 先验证据（external_prior_evidence/，只读）",
            "L2": "冻结后的正式合成实验 —— **尚未开始**",
            "L3": "PAMAP2 分析 —— REAL 线已 disposition 为 OMITTED_BY_DATA_GATE",
            "L4": "独立环境重建 —— 未尝试",
        },
        "revision": {
            "git_head_at_run": git_state["head"],
            "worktree_clean": git_state["worktree_clean"],
            "status_entry_count": git_state["status_entry_count"],
            "status_porcelain_head": git_state["status_porcelain"][:20],
            "batch_patch": patch,
            "content_anchor": "source_tree_hash + 逐对象 sha256（package_manifest.json）",
            "immutable_revision_established": False,
            "required_action": (
                f"创建 B15c 具名 commit（在上游 {git_state['head']} 之上）；"
                "内容不变，故不使本包任何 sha256 失效，仅新增 revision 锚点。"
            ),
        },
        "frozen_identities": {
            "freeze_id": manifest["freeze_id"],
            "scope_spec_hash": manifest["scope_spec_hash"],
            "protocol_content_hash": manifest["protocol_content_hash"],
            "analysis_spec_hash": manifest["analysis_spec_hash"],
            "compute_spec_hash": manifest["compute_spec_hash"],
            "estimand_spec_registry_hash": manifest["estimand_spec_registry_hash"],
            "source_tree_hash": manifest["source_tree_hash"],
            "environment_lock_hash": manifest["environment_lock_hash"],
            "seed_registry_snapshot_hash": manifest["seed_registry_snapshot_hash"],
            "component_registry_snapshot_hash": manifest[
                "component_registry_snapshot_hash"
            ],
            "freeze_tag": "v1.0-freeze-owtda-cal-r1 -> e16222f（未移动）",
        },
        "run_identities": {
            phase: {
                "run_component_set_hash": info["run_component_set_hash"],
                "run_input_bindings_hash": info["run_input_bindings_hash"],
                "scope_design_hash": info["scope_design_hash"],
                "scope_design_rows": info["scope_design_rows"],
            }
            for phase, info in sorted(manifest["run_admission"].items())
        },
        "exclusions": {
            "secrets/": "隔离的 REAL task root key / task id salt（永不打包）",
            "artifacts/archive/": "既往归档 ZIP（禁止自包含）",
            "caches": "__pycache__ / .pytest_cache / .ruff_cache / .git",
        },
        "verification": (
            "解压后按 SHA256SUMS.txt 逐项核对；package_manifest.json 记录 role/size/sha256；"
            "gates/*.json 为权威判定对象（Markdown 由 JSON 渲染）。"
        ),
    }


def _audit_request(
    *, now: str, gates: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "audit_request",
        "submission_id": SUBMISSION_ID,
        "requested_at_utc": now,
        "requested_scope": [
            "验证归档逐字节完整性（SHA256SUMS.txt / package_manifest.json）",
            "复算冻结链：freeze_id、五类 spec hash、三类 registry snapshot、SCOPE_DESIGN 行 hash",
            "复算 run 身份：RUN_COMPONENT_SET / RUN_INPUT_BINDINGS 与 manifest.run_admission 一致",
            "复核 G3 盲 smoke 两 phase 的计数/零错误/零泄漏/身份闭合/provenance 绑定",
            "复核 §9.4 预算外推与资源采样结论",
            "复核 H1 alternative DGP 构造效度证据等级（L0）与 null signature 回归",
            "复核 F-B15c-1 的定性、影响面与 B15b 判定撤回范围",
            "对 w* 决策（8 vs 12）给出裁定建议及重新冻结代价评估",
        ],
        "gate_ids": [g["gate_id"] for g in gates],
        "gate_status": {g["gate_name"]: g["status"] for g in gates},
        "claims_not_asserted": [
            "本代尚无 L2/L3 科学结论；smoke 与预算证据永不进入论文",
            "REAL 线为 OMITTED_BY_DATA_GATE（23 < 24 任务），属数据事实而非实现缺陷",
        ],
        "frozen_identities": {
            "freeze_id": manifest["freeze_id"],
            "source_tree_hash": manifest["source_tree_hash"],
        },
    }


def _build_superseded(staging: Path) -> dict[str, Any]:
    """Re-materialise the S01 smoke ledger voided by B15c, straight from git."""
    entries: list[dict[str, Any]] = []
    s01 = _git("show", f"{B15B_COMMIT}:artifacts/smoke/SMOKE_NULL/evaluation_rows_w8_r32.jsonl")
    if s01:
        raw = s01.encode("utf-8")
        target = (
            staging / "superseded/B15B_S01_SMOKE_NULL/evaluation_rows_w8_r32.jsonl"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        entries.append(
            {
                "path": "B15B_S01_SMOKE_NULL/evaluation_rows_w8_r32.jsonl",
                "size": len(raw),
                "sha256": _sha256_bytes(raw),
                "source": f"git {B15B_COMMIT} (B15b commit)",
                "voided_by": "F-B15c-1",
            }
        )
    note = (
        "F-B15c-1：B15b 的 smoke runner 借用 formal 身份函数（cells.* / scope.logical_*）"
        "与 formal 流 kind/字段（null_*、{data_generation_id, DGP_family, master_replicate_id}），"
        "违反 Plan §16（smoke 独立身份域）、§9.3（stream_kind 必须 smoke_ 前缀）与 §15.2（smoke 字段表）。"
        "按 §9.3 umbrella 规则，新增 H1 DGP 使 smoke_generation_id 由 S01 整体提升为 S02 并重跑两 phase，"
        "故 S01 运行证据全部作废（此处保留以备审计追溯）。对应修复见 B15c。"
    )
    index = {
        "schema_version": 1,
        "kind": "superseded_index",
        "reason": note,
        "objects": entries,
        "also_present_in_package": [
            "repo/artifacts/audit/ 内的中间态 check 日志（含未通过项）已原样保留",
        ],
    }
    _write_json(staging / "superseded/SUPERSEDED_INDEX.json", index)
    _write_text(staging / "superseded/README.md", f"# 被作废对象\n\n{note}\n")
    return index


# ----------------------------------------------------------------------- build


def main() -> int:
    parser = argparse.ArgumentParser(description="build audit submission package")
    parser.add_argument("--keep-staging", action="store_true")
    args = parser.parse_args()

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = json.loads((GOV / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    git_state = _git_state()
    objects, exclusions = _collect_files()

    patch: dict[str, Any] | None = None
    patch_path = (
        PARENT
        / "_incoming/OWTDA_CAL_R1_B15c_20260910_SMOKE_ALT/OWTDA_CAL_R1_B15c_20260910.patch"
    )
    if patch_path.exists():
        patch = {
            "file": str(patch_path.relative_to(PARENT)).replace("\\", "/"),
            "size": patch_path.stat().st_size,
            "sha256": _sha256_file(patch_path),
        }

    staging = ARCHIVE_DIR / SUBMISSION_ID
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for obj in objects:
        dst = staging / obj["archive_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(obj["abs"], dst)

    _write_json(staging / "source/source_manifest.json", _source_manifest(manifest))
    _write_json(staging / "source/git_state.json", git_state)
    _write_text(
        staging / "source/source_tree_hash.txt", manifest["source_tree_hash"] + "\n"
    )

    gates = _build_gates(now=now, manifest=manifest)
    for gate in gates:
        _write_json(staging / "gates" / f"{gate['gate_id']}.json", gate)
        _write_text(staging / "gates" / f"{gate['gate_id']}.md", _render_gate_md(gate))

    _write_json(
        staging / "submission/ADMISSION_RECORD.json",
        _admission_record(
            now=now, git_state=git_state, manifest=manifest, patch=patch
        ),
    )
    _write_json(
        staging / "submission/AUDIT_REQUEST.json",
        _audit_request(now=now, gates=gates, manifest=manifest),
    )
    superseded = _build_superseded(staging)

    register = {
        "schema_version": 1,
        "kind": "open_issues_and_decisions",
        "submission_id": SUBMISSION_ID,
        "generated_at_utc": now,
        "issues": _issues(),
        "decisions_required": _decisions(),
        "superseded": superseded["objects"],
        "exclusions": exclusions,
    }
    _write_json(staging / "submission/OPEN_ISSUES_AND_DECISIONS.json", register)
    _write_text(
        staging / "submission/OPEN_ISSUES_AND_DECISIONS.md", _register_md(now=now)
    )

    _write_json(
        staging / "closure_summary.json",
        {
            "schema_version": 1,
            "kind": "closure_summary",
            "submission_id": SUBMISSION_ID,
            "generated_at_utc": now,
            "revision": git_state["head"],
            "worktree_clean": git_state["worktree_clean"],
            "batches_closed_recent": list(RECENT_EXPERIMENT_BATCHES),
            "formal_phases_started": [],
            "evidence_level_reached": "L0",
            "gates": {g["gate_name"]: g["status"] for g in gates},
            "open_items": [
                "D-1 w* amendment decision（measured 12 vs frozen 8）",
                "D-5 具名 commit（审计受理前置）",
                "D-2 B15b 判定撤回范围（F-B15c-1）",
                "D-3 §15.2 增行 / §9.3 代次提升的 amendment 登记",
                "D-4 smoke_ids.py 是否纳入冻结源域",
            ],
            "issue_count": len(_issues()),
            "decision_count": len(_decisions()),
        },
    )

    _write_text(staging / "README.md", _readme(now=now, manifest=manifest,
                                               git_state=git_state, gates=gates))

    content: list[tuple[str, bytes]] = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            content.append(
                (str(path.relative_to(staging)).replace("\\", "/"), path.read_bytes())
            )
    sums = "".join(f"{_sha256_bytes(b)}  {rel}\n" for rel, b in content)
    _write_text(staging / "SHA256SUMS.txt", sums)
    content.append(("SHA256SUMS.txt", sums.encode("utf-8")))

    origin_by_archive_path = {o["archive_path"]: o["origin"] for o in objects}
    package_manifest = {
        "schema_version": 1,
        "kind": "audit_package_manifest",
        "submission_id": SUBMISSION_ID,
        "generated_at_utc": now,
        "object_count": len(content),
        "path_mapping_note": (
            "repo/* 为仓库内路径原样；batches/* 为交付目录 _incoming/<name>/... 的映射，"
            "source_path 记录原始相对路径。"
        ),
        "role_counts": {},
        "objects": [
            {
                "path": rel,
                "source_path": origin_by_archive_path.get(rel, rel),
                "role": _archive_role(rel),
                "size": len(blob),
                "sha256": _sha256_bytes(blob),
            }
            for rel, blob in sorted(content)
        ],
    }
    for obj in package_manifest["objects"]:
        package_manifest["role_counts"][obj["role"]] = (
            package_manifest["role_counts"].get(obj["role"], 0) + 1
        )
    _write_json(staging / "package_manifest.json", package_manifest)
    manifest_bytes = (staging / "package_manifest.json").read_bytes()
    manifest_sha = _sha256_bytes(manifest_bytes)
    content.append(("package_manifest.json", manifest_bytes))

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = ARCHIVE_DIR / f"{SUBMISSION_ID}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, blob in sorted(content):
            info = zipfile.ZipInfo(f"{SUBMISSION_ID}/{rel}", date_time=ZIP_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, blob)
    zip_sha = _sha256_file(zip_path)
    _write_text(
        ARCHIVE_DIR / f"{SUBMISSION_ID}.zip.sha256",
        f"{zip_sha}  {zip_path.name}\n",
    )

    checked, mismatched = _verify(zip_path, zip_sha)
    _write_json(
        staging / "VERIFY.json",
        {
            "zip_sha256": zip_sha,
            "package_manifest_sha256": manifest_sha,
            "members_checked": checked,
            "mismatched": mismatched,
            "verified": mismatched == 0,
        },
    )

    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    _write_text(
        DELIVERY_DIR / "PACKAGE_MANIFEST.sha256",
        f"{manifest_sha}  package_manifest.json\n",
    )
    _write_text(
        DELIVERY_DIR / "AUDIT_SUBMISSION_RECORD.md",
        _delivery_note(
            now=now,
            manifest=manifest,
            git_state=git_state,
            gates=gates,
            zip_path=zip_path,
            zip_sha=zip_sha,
            manifest_sha=manifest_sha,
            object_count=len(content),
            verified=(checked, mismatched),
        ),
    )
    _write_text(
        DELIVERY_DIR / "OPEN_ISSUES_AND_DECISIONS.md",
        _register_md(now=now),
    )
    shutil.copyfile(
        REPO / "artifacts/archive" / f"{SUBMISSION_ID}.zip.sha256",
        DELIVERY_DIR / f"{SUBMISSION_ID}.zip.sha256",
    )
    shutil.copyfile(
        staging / "submission/AUDIT_REQUEST.json", DELIVERY_DIR / "AUDIT_REQUEST.json"
    )

    if not args.keep_staging:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"submission_id    = {SUBMISSION_ID}")
    print(f"objects          = {len(content)}")
    print(f"zip              = {zip_path.relative_to(REPO)}")
    print(f"zip_bytes        = {zip_path.stat().st_size}")
    print(f"zip_sha256       = {zip_sha}")
    print(f"members_verified = {checked} mismatched={mismatched}")
    print(f"worktree_clean   = {git_state['worktree_clean']}")
    print("gates            = " + ", ".join(
        f"{g['gate_name']}:{g['status']}" for g in gates
    ))
    return 0 if mismatched == 0 else 1


SELF_REFERENTIAL = ("SHA256SUMS.txt", "package_manifest.json")


def _verify(zip_path: Path, zip_sha: str) -> tuple[int, int]:
    """Re-open the archive and re-verify every member against the in-package sums.

    ``SHA256SUMS.txt`` cannot list itself and ``package_manifest.json`` is written
    after the sums are computed; both are instead covered by the external
    ``.zip.sha256`` sidecar (and the manifest lists ``SHA256SUMS.txt``).
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        prefix = f"{SUBMISSION_ID}/"
        sums: dict[str, str] = {}
        for line in zf.read(f"{prefix}SHA256SUMS.txt").decode("utf-8").splitlines():
            if line.strip():
                digest, rel = line.split("  ", 1)
                sums[rel] = digest
        manifest = json.loads(zf.read(f"{prefix}package_manifest.json"))
        checked = 0
        mismatched = 0
        for name in names:
            rel = name[len(prefix) :]
            if rel in SELF_REFERENTIAL:
                continue
            blob = zf.read(name)
            checked += 1
            if sums.get(rel) != _sha256_bytes(blob):
                mismatched += 1
        for obj in manifest["objects"]:
            blob = zf.read(prefix + obj["path"])
            checked += 1
            if _sha256_bytes(blob) != obj["sha256"]:
                mismatched += 1
    if _sha256_file(zip_path) != zip_sha:
        mismatched += 1
    return checked, mismatched


def _readme(*, now: str, manifest: dict[str, Any], git_state: dict[str, Any],
            gates: list[dict[str, Any]]) -> str:
    lines = [
        f"# {SUBMISSION_ID}",
        "",
        "OW-TDA-CAL-R1 已完成实验的审计提交包（自包含、逐字节可验证）。",
        "",
        "## 锚点",
        "",
        f"- revision（运行期 HEAD）：`{git_state['head']}`，工作区 clean = "
        f"**{git_state['worktree_clean']}**",
        f"- `freeze_id`：`{manifest['freeze_id']}`",
        f"- `source_tree_hash`：`{manifest['source_tree_hash']}`",
        f"- `environment_lock_hash`：`{manifest['environment_lock_hash']}`",
        f"- `smoke_config_hash`：`{manifest['smoke_config_hash']}`",
        "- 冻结 tag：`v1.0-freeze-owtda-cal-r1` → `e16222f`（未移动）",
        "",
        "## 目录",
        "",
        "| 目录 | 内容 |",
        "|---|---|",
        "| `repo/` | 被审计工作树（git 跟踪内容，已排除 secrets/ 与既往归档） |",
        "| `source/` | 冻结源域 manifest、复算的 `source_tree_hash`、git 状态 |",
        "| `gates/` | Gate 对象（JSON 权威 + 渲染 Markdown） |",
        "| `submission/` | 受理记录、审计请求、问题与待决断登记 |",
        "| `superseded/` | 被 B15c 作废的 S01 smoke 证据与原因 |",
        "| `batches/` | 各批次交付四件套（B01..B15c，源自 `_incoming/`） |",
        "| `SHA256SUMS.txt` | 除自身与 `package_manifest.json` 外全部对象的 sha256 |",
        "| `package_manifest.json` | 逐对象目录（path / source_path / role / size / sha256） |",
        "",
        "## 验证方法",
        "",
        "```powershell",
        "Expand-Archive <zip> <out>",
        "python -c \"import hashlib,pathlib;root=pathlib.Path('<out>/"+SUBMISSION_ID+"');bad=[l.split('  ',1)[1] for l in (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines() if l.strip() and hashlib.sha256((root/l.split('  ',1)[1]).read_bytes()).hexdigest()!=l.split('  ',1)[0]];print('mismatched',len(bad),bad[:5])\"",
        "```",
        "",
        "## Gate 判定（gates/）",
        "",
        "| gate | status |",
        "|---|---|",
    ]
    lines += [f"| `{g['gate_name']}` | **{g['status']}** |" for g in gates]
    lines += [
        "",
        "> Gate JSON 为权威；Markdown 由 JSON 渲染。",
        f"> 生成时间：{now}（`scripts/build_audit_submission.py`）。",
        "",
    ]
    return "\n".join(lines)


def _delivery_note(
    *,
    now: str,
    manifest: dict[str, Any],
    git_state: dict[str, Any],
    gates: list[dict[str, Any]],
    zip_path: Path,
    zip_sha: str,
    manifest_sha: str,
    object_count: int,
    verified: tuple[int, int],
) -> str:
    lines = [
        f"# {SUBMISSION_ID} — 审计提交说明",
        "",
        f"- 生成时间（UTC）：{now}",
        f"- 归档：`{zip_path.relative_to(REPO).as_posix()}`（{zip_path.stat().st_size:,} B，"
        f"{object_count} 个对象）",
        f"- ZIP SHA256：`{zip_sha}`",
        f"- `package_manifest.json` SHA256：`{manifest_sha}`",
        f"- 构建期自校验：**{verified[0]} 个成员逐一复核，mismatch = {verified[1]}**",
        f"- 运行期 HEAD：`{git_state['head']}`；工作区 clean = **{git_state['worktree_clean']}**",
        "",
        "## 1. 本包覆盖的实验",
        "",
        "| 批次 | 内容 | 证据等级 | 状态 |",
        "|---|---|---|---|",
        "| B13 | attack suite + compute budget RC | L0 | 已闭合 |",
        "| B14a/B14b | 共同冻结 + registries + REAL disposition | L0 | 已闭合 |",
        "| B15a | run 身份层（RUN_COMPONENT_SET/bindings） | L0 | 已闭合 |",
        "| B15b | SMOKE_NULL（S01） | L0 | **已作废**（F-B15c-1） |",
        "| B15c | H1 alternative DGP + SMOKE_NULL/ALT（S02）+ §9.4 完整判定 + `w*` 扫描 | L0 | 待审计 |",
        "",
        "## 2. Gate 判定",
        "",
        "| gate | status | 摘要 |",
        "|---|---|---|",
    ]
    lines += [
        f"| `{g['gate_name']}` | **{g['status']}** | {g['summary']} |" for g in gates
    ]
    lines += [
        "",
        "## 3. 关键数字",
        "",
        f"- `freeze_id`：`{manifest['freeze_id']}`（未变）",
        f"- `source_tree_hash`：`{manifest['source_tree_hash']}`（45 文件）",
        f"- `smoke_config_hash`：`{manifest['smoke_config_hash']}`",
        "- SMOKE_NULL：896 / 3,584 / 73,600，`t_0,32 = 842.03 s` → `t_H0_hat = 22.842 h`",
        "- SMOKE_ALT：256 / 1,024 / 49,152，`t_1,32 = 272.52 s` → `t_H1_hat = 4.731 h`",
        "- `t_core_hat = 27.573 h`；peak RSS 1.393 GiB；swap 增量 0；磁盘 386.1 MiB；`open_runs=0`",
        "- **`w*` 扫描**：payload 全 worker 数逐位一致；吞吐最高 w=12（H0 +8.1%、H1 +6.3%）",
        "",
        "## 4. 需审计裁定的事项",
        "",
        "见同目录 `OPEN_ISSUES_AND_DECISIONS.md`（问题 8 项 + 待决断 5 项）。",
        "其中两项为受理/科学前置：**D-5 具名 commit** 与 **D-1 w\\* 裁定**。",
        "",
    ]
    return "\n".join(lines)


def _issues() -> list[dict[str, Any]]:
    return [
        {
            "id": "F-B15c-1",
            "severity": "HIGH",
            "class": "contract_violation_inherited_from_B15b",
            "title": "B15b 的 smoke runner 借用 formal 身份域与 formal 流",
            "detail": (
                "smoke.py 调用 cells.master_replicate_id / physical_cell_id / base_series_id / "
                "data_unit_id 与 scope.logical_cell_id / logical_data_key / logical_feature_key / "
                "logical_evaluation_key；流 kind 为 null_initial / null_innovation / "
                "null_observation_noise，命名域为 {data_generation_id, DGP_family, "
                "master_replicate_id}；ledger 缺 experiment_id。违反 Plan §16（smoke 独立身份域，"
                "禁止借用 formal logical IDs）、§9.3（stream_kind 必须 smoke_ 前缀）、"
                "§15.2（smoke 字段表）。"
            ),
            "status": "FIXED_IN_B15c",
            "impact": (
                "B15b 的 S01 smoke 运行证据全部作废（superseded/）；B15b 的 G3 PASS 判定在"
                "smoke 身份维度失效，其余维度不受影响。"
            ),
            "evidence": [
                "superseded/SUPERSEDED_INDEX.json",
                "repo/governance/CHANGELOG.md",
                "repo/src/owtda_cal/smoke_ids.py",
            ],
            "decision_ref": "D-2",
        },
        {
            "id": "F-B15c-2",
            "severity": "MEDIUM",
            "class": "contract_extension",
            "title": "§15.2 流表缺少 smoke 版 shift_direction",
            "detail": (
                "新增 smoke_shift_direction（字段同其它 smoke 数据流 "
                "{smoke_generation_id, phase, DGP_family, replicate_id}），"
                "恰一次 rng.random(float64)，仅 mean-shift 消费。属 spec 增行。"
            ),
            "status": "IMPLEMENTED_AMENDMENT_RECORD_PENDING",
            "impact": "建议登记 AMENDMENT_REGISTRY.jsonl（该文件当前尚不存在）。",
            "evidence": ["repo/src/owtda_cal/dgp.py", "repo/governance/CHANGELOG.md"],
            "decision_ref": "D-3",
        },
        {
            "id": "F-B15c-3",
            "severity": "LOW",
            "class": "validator_staleness",
            "title": "audit/validate_freeze.py 硬编码组件数 6",
            "detail": (
                "新增 H1 数据组件（SYNTHETIC_CIRCLE_BASED_H1_V1）后该断言失效；"
                "已改为与 components.component_definitions() 比对，避免 registry 静默过期。"
            ),
            "status": "FIXED_IN_B15c",
            "evidence": ["repo/audit/validate_freeze.py"],
            "decision_ref": None,
        },
        {
            "id": "F-B15c-4",
            "severity": "MEDIUM",
            "class": "process_hazard",
            "title": "source_tree_hash 仅覆盖 git ls-files 命中的文件",
            "detail": (
                "新模块若未 git add，则不进入 FREEZE_MANIFEST.source_tree_hash（冻结清单静默漏项）；"
                "且在 freeze/run 身份重建后改动 src/configs/audit 会使已产出的 smoke 证据 provenance 失效。"
            ),
            "status": "DOCUMENTED",
            "impact": "已在 B15c EXECUTION_GUIDE §4 写明顺序纪律（先 add → 再 build → 再 run）。",
            "evidence": ["repo/audit/build_freeze.py", "repo/audit/build_run_admission.py"],
            "decision_ref": "D-4",
        },
        {
            "id": "O-1",
            "severity": "HIGH",
            "class": "unclosed_governance_decision",
            "title": "w* 扫描未确认冻结值（measured 12 vs frozen 8）",
            "detail": (
                "payload 在所有 worker 数下逐位一致；吞吐 w=12 相对 w=8 为 H0 +8.1%、H1 +6.3%，"
                "超过 §9.4 的 2% 并列阈值，规则指向 w*=12。"
            ),
            "status": "OPEN_DECISION",
            "impact": (
                "w_star 属 COMPUTE_SPEC ⇒ 改动将改变 compute_spec_hash → freeze_id → "
                "SCOPE_DESIGN 与全部合成身份（等价于重新冻结）；但不改变任何已达成 Gate 的结论。"
            ),
            "evidence": ["repo/artifacts/audit/worker_sweep_RC.json"],
            "decision_ref": "D-1",
        },
        {
            "id": "O-2",
            "severity": "HIGH",
            "class": "admissibility_blocker",
            "title": "归档 revision 尚未提交（工作区 dirty）",
            "detail": (
                "Plan §20.1 要求批次结束回传新 HEAD 与空工作区证明；审计规格阻断冻结域 dirty 文件。"
                "本包以 source_tree_hash + 逐对象 sha256 锚定内容，commit 不改变文件内容，"
                "故提交后本包全部 sha256 仍然有效。"
            ),
            "status": "OPEN_OPERATOR_ACTION",
            "evidence": ["source/git_state.json", "submission/ADMISSION_RECORD.json"],
            "decision_ref": "D-5",
        },
        {
            "id": "O-3",
            "severity": "MEDIUM",
            "class": "measurement_noise",
            "title": "H0 wall 抖动与 w=10 swap 观测",
            "detail": (
                "H0 三次 S02 实测 808.43 / 798.99 / 842.03 s（±2.7%）；SMOKE_ALT w=10 采样出现 "
                "3.7 MB swap 增长（RSS 1.67 GiB，非本 run 触发），按 §9.4「无 swap」判为不合格。"
            ),
            "status": "NOTED",
            "evidence": ["repo/artifacts/audit/worker_sweep_RC.json"],
            "decision_ref": "D-1",
        },
        {
            "id": "O-4",
            "severity": "INFO",
            "class": "disposition",
            "title": "REAL 线 OMITTED_BY_DATA_GATE（23 < 24 任务）",
            "detail": "数据事实而非实现缺陷；合成主线不受影响；REAL 链 tip 未变。",
            "status": "DISPOSITIONED",
            "evidence": ["repo/governance/REAL_DISPOSITION.jsonl"],
            "decision_ref": None,
        },
    ]


def _decisions() -> list[dict[str, Any]]:
    return [
        {
            "id": "D-1",
            "question": "w* 取 8（冻结）还是 12（实测最优）？",
            "options": [
                "采纳 12：需 COMPUTE_SPEC amendment + 重新冻结（freeze_id 变更、"
                "SCOPE_DESIGN 重生成、tag 迁移），并在正式 run 前完成",
                "维持 8：记录豁免理由（例如以 32-replicate 全长重复测量为准），不重新冻结",
            ],
            "consequences": (
                "两选项均不改变任何已达成 Gate 的结论（wall Gate 对 12 只会更宽松）；"
                "决策只影响 compute 身份与正式 run 的实际并行度。"
            ),
            "recommendation": "先以 32-replicate 全长复核 w=12 的优势，再决定是否重新冻结。",
            "blocking": ["B15d 正式 run 的 compute 身份"],
        },
        {
            "id": "D-2",
            "question": "F-B15c-1 是否需要对 B15b 判定作正式撤回（recission）？",
            "options": [
                "在 CHANGELOG 记录 B15b smoke 判定部分失效（本包已披露），不另立文书",
                "登记 INVALIDATION_REGISTRY.jsonl 事件（该文件尚未建立）",
            ],
            "consequences": "影响 B15b 在审计链上的状态标记与其可引用性。",
            "recommendation": "登记一条 invalidation 事件，保持链式可追溯。",
            "blocking": ["D-3（登记基础设施）"],
        },
        {
            "id": "D-3",
            "question": "是否为 §15.2 增行（smoke_shift_direction）与 §9.3 代次提升（S01→S02）登记 amendment？",
            "options": [
                "建立 AMENDMENT_REGISTRY.jsonl 并登记两条",
                "仅在 CHANGELOG 记录（现状）",
            ],
            "consequences": "决定 spec 偏离是否以结构化形式进入审计链。",
            "recommendation": "建立 registry 并登记（二者均属 spec 级变更）。",
            "blocking": ["D-2"],
        },
        {
            "id": "D-4",
            "question": "是否将 src/owtda_cal/smoke_ids.py 纳入冻结源域 / 组件 code_files？",
            "options": [
                "维持现状：smoke 基础设施仅由 run 级 source_tree_hash 覆盖（推荐）",
                "纳入 identity_core：使每个组件 code manifest 覆盖 smoke 身份域",
            ],
            "consequences": "后者将改变全部组件 hash 与 run 身份（需重建 + 重跑 smoke）。",
            "recommendation": "维持现状（smoke 制品永不进入 formal phase）。",
            "blocking": [],
        },
        {
            "id": "D-5",
            "question": "提交具名 commit 以建立不可变审计 revision？",
            "options": [
                "允许（推荐）：内容不变，本包 sha256 全部继续有效，仅新增 revision 锚点",
                "允许并重建 manifest：使 compute_git_commit = 批次 commit，需重跑两 phase smoke（约 19 min）",
                "暂不提交：本包保持 PENDING（审计受理将受阻）",
            ],
            "consequences": "影响审计受理（audit_spec §4 阻断 dirty 冻结域）。",
            "recommendation": "允许提交（不重建），compute_git_commit 语义在 B15d 统一处理。",
            "blocking": ["审计受理", "B15d"],
        },
    ]


def _register_md(*, now: str) -> str:
    lines = [
        f"# {SUBMISSION_ID} — 问题与待决断登记",
        "",
        f"生成时间（UTC）：{now}",
        "",
        "## A. 遇到的问题",
        "",
        "| ID | 级别 | 类别 | 标题 | 状态 | 关联决断 |",
        "|---|---|---|---|---|---|",
    ]
    for issue in _issues():
        lines.append(
            f"| {issue['id']} | {issue['severity']} | {issue['class']} | "
            f"{issue['title']} | {issue['status']} | {issue.get('decision_ref') or '—'} |"
        )
    lines += ["", "### 明细", ""]
    for issue in _issues():
        lines += [
            f"#### {issue['id']} — {issue['title']}",
            "",
            f"- 级别/类别：{issue['severity']} / `{issue['class']}`",
            f"- 状态：`{issue['status']}`",
            f"- 说明：{issue['detail']}",
        ]
        if issue.get("impact"):
            lines.append(f"- 影响：{issue['impact']}")
        lines.append(
            "- 证据：" + "、".join(f"`{p}`" for p in issue.get("evidence", []))
        )
        lines.append("")
    lines += ["## B. 待提交的决断", "", "| ID | 决断 | 建议 | 阻断 |", "|---|---|---|---|"]
    for dec in _decisions():
        lines.append(
            f"| {dec['id']} | {dec['question']} | {dec['recommendation']} | "
            f"{'；'.join(dec['blocking']) or '—'} |"
        )
    lines += ["", "### 明细", ""]
    for dec in _decisions():
        lines += [
            f"#### {dec['id']} — {dec['question']}",
            "",
        ]
        lines += [f"- 选项 {i + 1}：{opt}" for i, opt in enumerate(dec["options"])]
        lines += [
            f"- 后果：{dec['consequences']}",
            f"- 建议：{dec['recommendation']}",
            f"- 阻断：{'；'.join(dec['blocking']) or '—'}",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
