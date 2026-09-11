"""Build the append-only amendment / invalidation chains (audit P0-5).

Creates ``governance/AMENDMENT_REGISTRY.jsonl`` and
``governance/INVALIDATION_REGISTRY.jsonl`` as hash chains (each event carries
``prev_event_hash`` and its own ``event_hash``), the strict reason objects under
``governance/reasons/``, and ``governance/B12_DISPOSITION.json``.

The chains are rebuilt from this builder only while they are uncommitted; once
committed they are append-only and a later event must use ``chains.append_cas``
against the recorded tip (the verifier in :func:`verify_chain` re-derives both).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

from owtda_cal import chains, scope

GOV = REPO / "governance"
REASONS = GOV / "reasons"
AMENDMENTS = GOV / "AMENDMENT_REGISTRY.jsonl"
INVALIDATIONS = GOV / "INVALIDATION_REGISTRY.jsonl"


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reason(code: str, statement: str, evidence: list[str], extra: dict) -> dict:
    return {
        "schema_version": 1,
        "kind": "governance_reason",
        "reason_code": code,
        "statement": statement,
        "evidence": evidence,
        **extra,
    }


def _write_chain(path: Path, events: list[dict]) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    tips: list[str] = []
    for event in events:
        prev = tips[-1] if tips else None
        body = {**event, "prev_event_hash": prev}
        tip = chains.append_cas(
            str(path), body, expected_tip=prev, hash_field="event_hash"
        )
        tips.append(tip)
    return tips


def verify_chain(path: Path) -> dict[str, Any]:
    tip = None
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        stored = event.pop("event_hash")
        if event.get("prev_event_hash") != tip:
            raise ValueError(f"chain break in {path.name} at event {count + 1}")
        if chains.event_hash(event) != stored:
            raise ValueError(f"event hash mismatch in {path.name} at event {count + 1}")
        tip = stored
        count += 1
    return {"file": path.name, "events": count, "tip": tip}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="build governance registries")
    parser.add_argument("--wstar-rc", default=None, help="path to worker_confirmation_RC.json")
    args = parser.parse_args()
    at = _now()

    wstar: dict[str, Any] = {"status": "OPEN_NOT_YET_DECIDED"}
    if args.wstar_rc:
        candidate = Path(args.wstar_rc).expanduser()
        if candidate.exists():
            wstar = json.loads(candidate.read_text(encoding="utf-8"))

    reasons = {
        "AM_ENVIRONMENT_LOCK_CORRECTION": _reason(
            "AM_ENVIRONMENT_LOCK_CORRECTION",
            "pyproject.toml 未声明实际运行必需的 ripser 与证据工具 psutil，且无 uv.lock；"
            "COMPUTE_SPEC 声明四个线程变量为 \"1\"，但 COMPUTE_FREEZE 的 observed 全为 unset。"
            "本修正补齐直接依赖、加入 uv.lock、以 scripts/frozen_env.py 在解释器启动前设定"
            "线程变量，并让 environment_lock_hash 覆盖 pyproject/uv.lock/版本/OS/CPU/BLAS/线程设置；"
            "旧环境下的时间、内存与预算结果降为历史诊断。",
            [
                "governance/COMPUTE_SPEC_v1.json",
                "governance/COMPUTE_FREEZE.json",
                "pyproject.toml",
                "uv.lock",
                "scripts/frozen_env.py",
            ],
            {
                "affected_objects": ["COMPUTE_FREEZE.json", "FREEZE_MANIFEST.json"],
                "requires_refreeze": True,
                "old_evidence_status": "HISTORICAL_DIAGNOSTIC_ONLY",
            },
        ),
        "AM_SMOKE_SHIFT_DIRECTION": _reason(
            "AM_SMOKE_SHIFT_DIRECTION",
            "Plan §12.2 的 mean-shift 需要独立 shift 方向流；§15.2 只登记了 formal 行 "
            "shift_direction，smoke 对应行为表外。新增 smoke_shift_direction，命名域与其它 smoke "
            "数据流一致 {smoke_generation_id, phase, DGP_family, replicate_id}，恰执行一次 "
            "rng.random(dtype=np.float64)，仅由 mean-shift alternative 消费。",
            ["src/owtda_cal/dgp.py", "governance/CHANGELOG.md"],
            {
                "spec_section": "15.2 流表增行（未新增表外字段）",
                "delivered_in_batch": "B15c",
            },
        ),
        "AM_WORKER_CONFIRMATION_RULE": _reason(
            "AM_WORKER_CONFIRMATION_RULE",
            "冻结的 COMPUTE_SPEC.w_star=8 从未经过正式确认；8-replicate 扫描指向 12，"
            "差异超 §9.4 的 2% 并列阈值。本修正登记确认协议：两 phase 均使用完整 32-replicate "
            "worklist，workers=8 与 12 各 3 次配对运行，顺序固定 8→12、12→8、8→12，"
            "以三次吞吐中位数裁决，2% 内取 8，并要求 payload 逐位一致、error=0、swap 增量=0、"
            "peak RSS≤24 GiB；协议在测量前登记并进入冻结源域。",
            ["configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json", "audit/run_wstar_confirmation.py"],
            {
                "delivered_in_batch": "audit-supplement-R1",
                "prior_8_replicate_sweep": "HISTORICAL_DIAGNOSTIC_ONLY",
            },
        ),
        "AM_PARALLELISM_DECOUPLING": _reason(
            "AM_PARALLELISM_DECOUPLING",
            "冻结的 COMPUTE_SPEC.w_star 把一个**已被证明与结果无关**的操作参数写进了科学身份："
            "同一对象里已声明 worker_consistency=bitwise_identical_payload（全长 32-replicate 的 12 次"
            "配对运行 payload 逐位一致），可任何换机器/换核数都必须重新冻结并重派生全部合成身份"
            "（R1 已因此付出一次确认作废与两次标签迁移）。本修正把 compute_spec 的覆盖面收窄为**契约**："
            "线程变量=1、逐位不变性、资源验收（RSS/swap/error）；实际并行度改为每 run 记录——声明值在"
            "SMOKE_CONFIG.default_workers，实际值在 RUN_REGISTRY.workers_used 与 provenance.workers_used，"
            "并在启动时校验两者一致。COMPUTE_FREEZE 移除 w_star（环境锁只记录观察量）。"
            "确认协议及其 VOIDED 裁决作为契约的证据保留在 FREEZE_MANIFEST.parallelism_evidence（不哈希，"
            "故后续确认不会再次静默移动身份）。后果：compute_spec_hash 变更 → freeze_id 与 SCOPE_DESIGN "
            "行哈希变更 → 全部合成身份变更，因此必须在正式 run 之前实施。另：REAL 处置链因 freeze_id "
            "变更需锚定到新身份；此前 build_freeze 会在 freeze_id 变更时**静默复用旧链**（同类静默漂移），"
            "现已改为显式 re-anchor 并 fail-closed 校验。",
            [
                "governance/COMPUTE_SPEC_v1.json",
                "governance/COMPUTE_FREEZE.json",
                "audit/build_freeze.py",
                "audit/build_run_admission.py",
                "audit/run_smoke_s03.py",
                "governance/AMENDMENT_PROPOSAL_PARALLELISM_DECOUPLING.md",
            ],
            {
                "scope": "compute_identity",
                "requires_refreeze": True,
                "freeze_id_changes": True,
                "removed_identity_input": "COMPUTE_SPEC.w_star（含 COMPUTE_FREEZE.w_star）",
                "still_frozen_as_contract": [
                    "thread_env.* = 1",
                    "invariance_requirement = bitwise_identical_payload",
                    "acceptance: RSS<=24GiB, swap growth=0, unexplained errors=0",
                ],
                "run_level_records": [
                    "SMOKE_CONFIG_v1.json:default_workers",
                    "RUN_REGISTRY.jsonl:workers_used",
                    "smoke_provenance_manifest:workers_used / declared_workers",
                ],
                "preregistration_untouched": (
                    "configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json（预登记不可事后修改，"
                    "其裁决转为契约证据）"
                ),
                "closed_defect": "real_disposition_decision（freeze_id 变更时不再静默复用旧链）",
            },
        ),
        "INV_S01_SMOKE": _reason(
            "INV_S01_SMOKE",
            "F-B15c-1：B15b 的 smoke runner 借用 formal 身份函数（cells.* / scope.logical_*）与 "
            "formal 流 kind/字段（null_*、{data_generation_id, DGP_family, master_replicate_id}），"
            "违反 Plan §16（smoke 独立身份域）、§9.3（stream_kind 必须 smoke_ 前缀）与 §15.2"
            "（smoke 字段表）。按 §9.3 umbrella 规则，新增 H1 DGP 使 smoke generation 由 S01 整体"
            "提升为 S02 并重跑两 phase，故 S01 运行证据全部作废。",
            [
                "src/owtda_cal/smoke_ids.py",
                "governance/CHANGELOG.md",
                "artifacts/archive/OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip",
            ],
            {
                "applies_to": ["B15b drift smoke S01"],
                "superseded_by": "smoke_generation_id S02（B15c）",
                "defect_id": "F-B15c-1",
            },
        ),
        "INV_S02_PREFREEZE_SMOKE": _reason(
            "INV_S02_PREFREEZE_SMOKE",
            "审计裁定：现有 S02 smoke 不能作为最终 G3 证据。三项理由：(1) 两个 "
            "RUN_COMPONENT_SET.compute_git_commit 均为 52ad45a，而实际计算源码包含未提交的 B15c "
            "修改，事后补 commit 不能追溯修正该字段；(2) 环境锁缺失 uv.lock 与 ripser 声明，"
            "且四个线程变量的 observed 全为 unset；(3) w* 尚未确认。故 S02 降为 pre-freeze "
            "historical evidence，最终 G3 证据在新冻结下以 smoke_generation_id=S03 重跑并封 seal。",
            [
                "artifacts/audit/smoke_RC.json",
                "artifacts/audit/smoke_alt_RC.json",
                "governance/FREEZE_MANIFEST.json",
                "artifacts/archive/OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip",
            ],
            {
                "applies_to": ["smoke_generation_id S02（B15c）"],
                "superseded_by": "smoke_generation_id S03（audit supplement R1）",
                "audit_verdict": "MATERIAL_ADMISSION_REJECT",
            },
        ),
    }
    for name, body in reasons.items():
        _write_json(REASONS / f"{name}.json", body)

    reason_hash = {
        name: chains.event_hash(body) for name, body in reasons.items()
    }

    amendment_events = [
        {
            "schema_version": 1,
            "event_type": "AMENDMENT",
            "amendment_id": "AM-2026-09-10-01",
            "at_utc": at,
            "change_id": "AM_ENVIRONMENT_LOCK_CORRECTION",
            "scope": "compute_identity",
            "reason_object_hash": reason_hash["AM_ENVIRONMENT_LOCK_CORRECTION"],
            "requires_refreeze": True,
            "old_evidence_status": "HISTORICAL_DIAGNOSTIC_ONLY",
        },
        {
            "schema_version": 1,
            "event_type": "AMENDMENT",
            "amendment_id": "AM-2026-09-10-02",
            "at_utc": at,
            "change_id": "AM_SMOKE_SHIFT_DIRECTION",
            "scope": "stream_contract",
            "reason_object_hash": reason_hash["AM_SMOKE_SHIFT_DIRECTION"],
            "requires_refreeze": True,
            "spec_section": "15.2",
        },
        {
            "schema_version": 1,
            "event_type": "AMENDMENT",
            "amendment_id": "AM-2026-09-10-03",
            "at_utc": at,
            "change_id": "AM_WORKER_CONFIRMATION_RULE",
            "scope": "compute_identity",
            "reason_object_hash": reason_hash["AM_WORKER_CONFIRMATION_RULE"],
            "requires_refreeze": True,
        },
        {
            "schema_version": 1,
            "event_type": "AMENDMENT",
            "amendment_id": "AM-2026-09-10-04",
            "at_utc": at,
            "change_id": "AM_SMOKE_GENERATION_ADVANCE",
            "scope": "smoke_generation",
            "from_generation": "S02",
            "to_generation": "S03",
            "reason": "schema/environment/compute identity 变更后旧代次不能作为最终 G3 证据（§9.3）",
            "reason_object_hash": reason_hash["INV_S02_PREFREEZE_SMOKE"],
            "requires_refreeze": False,
        },
    ]
    if wstar.get("frozen_w_star_confirmed") is not None:
        confirmed = bool(wstar.get("frozen_w_star_confirmed"))
        amendment_events.append(
            {
                "schema_version": 1,
                "event_type": "AMENDMENT",
                "amendment_id": "AM-2026-09-10-05",
                "at_utc": at,
                "change_id": "AM_WSTAR_ADOPTION",
                "scope": "compute_identity",
                "preregistered_protocol_sha256": wstar.get("protocol_sha256"),
                "frozen_w_star_before": wstar.get("frozen_w_star"),
                "measured_selection": wstar.get("selected_workers"),
                "confirmed": confirmed,
                # Only a confirmation for *every* phase may change the frozen value;
                # a voided confirmation keeps it and the open item is recorded.
                "adopted_w_star": wstar.get("frozen_w_star"),
                "status": "CONFIRMED_NO_CHANGE" if confirmed
                else "VOIDED_OR_NOT_CONFIRMED_PREVIOUS_VALUE_KEPT",
                "follow_up": None if confirmed else (
                    "新的预登记才能更换 w*（协议禁止用重跑改善数字）；"
                    "失败运行已保留，未丢弃、未重跑"
                ),
                "requires_refreeze": True,
                "reason_object_hash": reason_hash["AM_WORKER_CONFIRMATION_RULE"],
            }
        )
    amendment_events.append(
        {
            "schema_version": 1,
            "event_type": "AMENDMENT",
            "amendment_id": "AM-2026-09-11-06",
            "at_utc": at,
            "change_id": "AM_PARALLELISM_DECOUPLING",
            "scope": "compute_identity",
            "reason_object_hash": reason_hash["AM_PARALLELISM_DECOUPLING"],
            "requires_refreeze": True,
            "freeze_id_changes": True,
            "removed_identity_input": "COMPUTE_SPEC.w_star",
            "status": "ADOPTED_BEFORE_FORMAL_RUNS",
        }
    )
    amendment_tips = _write_chain(AMENDMENTS, amendment_events)

    invalidation_events = [
        {
            "schema_version": 1,
            "event_type": "INVALIDATION",
            "invalidation_id": "INV-2026-09-10-01",
            "at_utc": at,
            "change_id": "INV_S01_SMOKE",
            "target": "B15b drift smoke generation S01",
            "reason_object_hash": reason_hash["INV_S01_SMOKE"],
            "replacement": "smoke_generation_id S02",
            "defect_id": "F-B15c-1",
        },
        {
            "schema_version": 1,
            "event_type": "INVALIDATION",
            "invalidation_id": "INV-2026-09-10-02",
            "at_utc": at,
            "change_id": "INV_S02_PREFREEZE_SMOKE",
            "target": "B15c smoke generation S02",
            "reason_object_hash": reason_hash["INV_S02_PREFREEZE_SMOKE"],
            "replacement": "smoke_generation_id S03",
            "status_after": "PRE_FREEZE_HISTORICAL_EVIDENCE",
        },
    ]
    invalidation_tips = _write_chain(INVALIDATIONS, invalidation_events)

    b12 = {
        "schema_version": 1,
        "kind": "batch_number_disposition",
        "batch_id": "B12",
        "status": "NEVER_USED",
        "statement": (
            "编号 B12 未在任何批次交付目录、git commit、治理对象或计划条目中使用；"
            "批次序列为 B01、B02、B03–B11A、B11B1–B11B3、B13、B14a、B14b、B15a、B15b、B15c。"
            "本对象以显式处置替代补交四件套，并更正既往“覆盖 B01–B15c”的表述。"
        ),
        "evidence": {
            "incoming_directories_with_b12": [],
            "commits_matching_B12": [],
            "search_scope": ["_incoming/*", "git log --all", "governance/*", "README.md"],
            "search_date": at,
        },
        "consequence": "不存在遗漏的执行或证据；凡引用“全部批次”处应以显式批次清单为准。",
        "batch_sequence": [
            "B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10",
            "B11A", "B11B1", "B11B2", "B11B3", "B13", "B14a", "B14b", "B15a", "B15b", "B15c",
        ],
        "generated_at_utc": at,
    }
    _write_json(GOV / "B12_DISPOSITION.json", b12)

    verification = {
        "amendments": verify_chain(AMENDMENTS),
        "invalidations": verify_chain(INVALIDATIONS),
        "s03_generation": "S03",
        "current_smoke_generation": scope.SMOKE_GENERATION_ID,
        "wstar_status": wstar.get("frozen_w_star_confirmed", "OPEN_NOT_YET_DECIDED"),
        "amendment_tips": amendment_tips,
        "invalidation_tips": invalidation_tips,
        "reason_hashes": reason_hash,
    }
    _write_json(GOV / "GOVERNANCE_REGISTRY_VERIFICATION.json", verification)
    print(json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
