"""Build the incremental audit supplement `OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910`.

Assembles, from the out-of-repo evidence root and the repository, exactly the P0
material the audit demanded (the previously submitted package stays read-only)::

    revision/      P0-1  git bundle + verify/fsck + zero-byte status/stash + identity_check
    environment/   P0-2  pins, uv.lock, versions, BLAS, thread env, fresh-venv rebuild test
    wstar/         P0-3  preregistered protocol, paired 8/12 runs, payload comparison, verdict
    configs/schema P0-4  strict schemas + manifest + schema_check evidence
    governance/    P0-5  AMENDMENT/INVALIDATION chains, reasons, B12 disposition, changelog
    smoke/S03/     P0-6  sealed smoke evidence, run/state registries, provenance manifest
    verification/  P0-7  raw pytest (log+xml), ruff log, commands, exit codes, environment
    gates/         re-labelled gate objects (BLOCKED_IDENTITY / PROVISIONAL / ...)
    GATE_RELABEL.json + DISCLOSURES.md + README.md + package_manifest.json + SHA256SUMS.txt

A missing P0 input is reported as ``MISSING:<path>`` in the manifest instead of
being silently skipped, so the supplement can never look complete while incomplete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SUBMISSION_ID = "OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910"
OUT_PARENT = REPO.parent / "_incoming" / "OWTDA_CAL_R1_AUDIT_SUPPLEMENT_R1_20260910"
ZIP_STAMP = (2026, 9, 10, 0, 0, 0)
GOV = REPO / "governance"

#: (archive_path, source_path, required)
PLAN: list[tuple[str, str, bool]] = [
    # P0-1 revision
    ("revision/OWTDA-CAL-R1.bundle", "revision/OWTDA-CAL-R1.bundle", True),
    ("revision/git_bundle_verify.txt", "revision/git_bundle_verify.txt", True),
    ("revision/git_fsck_full.txt", "revision/git_fsck_full.txt", True),
    ("revision/git_rev_parse_HEAD.txt", "revision/git_rev_parse_HEAD.txt", True),
    ("revision/git_show_ref_tags.txt", "revision/git_show_ref_tags.txt", True),
    ("revision/git_log_graph.txt", "revision/git_log_graph.txt", True),
    ("revision/git_status_porcelain_v1.txt", "revision/git_status_porcelain_v1.txt", True),
    ("revision/git_stash_list.txt", "revision/git_stash_list.txt", True),
    ("revision/source_manifest.json", "revision/source_manifest.json", True),
    ("revision/source_tree_hash.txt", "revision/source_tree_hash.txt", True),
    ("revision/REVISION_ACCEPTANCE.json", "revision/REVISION_ACCEPTANCE.json", True),
    # P0-2 environment
    ("environment/pyproject.toml", "repo/environment/pyproject.toml", True),
    ("environment/uv.lock", "repo/environment/uv.lock", True),
    ("environment/environment_manifest.json", "repo/environment/environment_manifest.json", True),
    ("environment/pip_freeze_all.txt", "repo/environment/pip_freeze_all.txt", True),
    ("environment/python_VV.txt", "repo/environment/python_VV.txt", True),
    ("environment/numpy_show_config.txt", "repo/environment/numpy_show_config.txt", True),
    ("environment/tool_versions.json", "repo/environment/tool_versions.json", True),
    ("environment/thread_env.json", "repo/environment/thread_env.json", True),
    (
        "environment/environment_rebuild_test.json",
        "repo/environment/environment_rebuild_test.json",
        True,
    ),
    # P0-3 wstar
    (
        "wstar/WSTAR_CONFIRMATION_PROTOCOL.json",
        "repo/configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json",
        True,
    ),
    ("wstar/worker_confirmation_raw.jsonl", "wstar/worker_confirmation_raw.jsonl", True),
    ("wstar/worker_payload_comparison.json", "wstar/worker_payload_comparison.json", True),
    ("wstar/worker_confirmation_RC.json", "wstar/worker_confirmation_RC.json", True),
    ("wstar/resource_samples.jsonl", "wstar/resource_samples.jsonl", True),
    # P0-4 schemas
    ("configs/schema/scientific_row.schema.json", "repo/configs/schema/scientific_row.schema.json", True),
    (
        "configs/schema/scientific_row_wire.schema.json",
        "repo/configs/schema/scientific_row_wire.schema.json",
        True,
    ),
    (
        "configs/schema/feature_sufficient_row.schema.json",
        "repo/configs/schema/feature_sufficient_row.schema.json",
        True,
    ),
    (
        "configs/schema/feature_sufficient_row_wire.schema.json",
        "repo/configs/schema/feature_sufficient_row_wire.schema.json",
        True,
    ),
    (
        "configs/schema/scientific_result_projection.schema.json",
        "repo/configs/schema/scientific_result_projection.schema.json",
        True,
    ),
    (
        "configs/schema/feature_result_projection.schema.json",
        "repo/configs/schema/feature_result_projection.schema.json",
        True,
    ),
    ("configs/schema/schemas_manifest.json", "repo/configs/schema/schemas_manifest.json", True),
    # P0-5 governance is collected by glob (_copy_governance): an explicit list
    # silently omitted newly added objects (disclosed defect D-2), so the whole
    # governance tree is copied and REQUIRED_GOVERNANCE only marks what must exist.
    # P0-6 smoke S03
    ("smoke/S03/SMOKE_NULL/evaluation_rows.jsonl", "smoke/S03/SMOKE_NULL/evaluation_rows.jsonl", True),
    ("smoke/S03/SMOKE_ALT/evaluation_rows.jsonl", "smoke/S03/SMOKE_ALT/evaluation_rows.jsonl", True),
    ("smoke/S03/smoke_null_RC.json", "smoke/S03/smoke_null_RC.json", True),
    ("smoke/S03/smoke_alt_RC.json", "smoke/S03/smoke_alt_RC.json", True),
    ("smoke/S03/SMOKE_SEAL_SMOKE_NULL.json", "smoke/S03/SMOKE_SEAL_SMOKE_NULL.json", True),
    ("smoke/S03/SMOKE_SEAL_SMOKE_ALT.json", "smoke/S03/SMOKE_SEAL_SMOKE_ALT.json", True),
    ("smoke/S03/RUN_REGISTRY.jsonl", "smoke/S03/RUN_REGISTRY.jsonl", True),
    ("smoke/S03/STATE_REGISTRY.jsonl", "smoke/S03/STATE_REGISTRY.jsonl", True),
    ("smoke/S03/commands.jsonl", "smoke/S03/commands.jsonl", True),
    ("smoke/S03/stdout_stderr/smoke_s03.log", "smoke/S03/stdout_stderr/smoke_s03.log", True),
    ("smoke/S03/provenance_manifest.json", "smoke/S03/provenance_manifest.json", True),
    # P0-7 verification
    ("verification/pytest_full.log", "verification/pytest_full.log", True),
    ("verification/pytest_full.xml", "verification/pytest_full.xml", True),
    ("verification/ruff_check.log", "verification/ruff_check.log", True),
    ("verification/validation_commands.jsonl", "verification/commands.jsonl", True),
    ("verification/validation_exit_codes.json", "verification/validation_exit_codes.json", True),
    ("verification/validation_environment.json", "verification/validation_environment.json", True),
]

GATE_RELABEL = {
    "archive_byte_integrity": {"in_package": "PASS", "material_admission": "PASS"},
    "G0-FREEZE-CHAIN-AND-IDENTITY": {"in_package": "PASS", "material_admission": "BLOCKED_IDENTITY"},
    "G3-BLIND-SMOKE-BOTH-PHASES": {"in_package": "PASS", "material_admission": "PROVISIONAL"},
    "SECTION-9-4-COMPUTE-BUDGET": {"in_package": "PASS", "material_admission": "PROVISIONAL"},
    "W-STAR-CONFIRMATION": {"in_package": "FAIL_UNCONFIRMED", "material_admission": "FAIL_UNCONFIRMED"},
    "H1-ALTERNATIVE-CONSTRUCT-CONTRACTS": {"in_package": "PASS_L0", "material_admission": "PENDING_CODE_REVIEW"},
    "L2/L3-SCIENCE": {"in_package": "NOT_STARTED", "material_admission": "NO_RESULTS_TO_AUDIT"},
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(source: str, evidence_root: Path) -> Path:
    return REPO / source[5:] if source.startswith("repo/") else evidence_root / source


def _copy_p0_smoke(evidence_root: Path, staging: Path) -> list[dict[str, Any]]:
    """P0-6: copy the whole S03 evidence tree (ledgers, seals, registries)."""
    copied: list[dict[str, Any]] = []
    src_root = evidence_root / "smoke" / "S03"
    if not src_root.exists():
        return [{"path": "smoke/S03", "status": f"MISSING:{src_root}"}]
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(evidence_root).as_posix()
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        copied.append(
            {"path": rel, "status": "ok", "size": path.stat().st_size, "sha256": _sha256(path)}
        )
    return copied


REQUIRED_GOVERNANCE = (
    "governance/FREEZE_MANIFEST.json",
    "governance/COMPUTE_SPEC_v1.json",
    "governance/COMPUTE_FREEZE.json",
    "governance/AMENDMENT_REGISTRY.jsonl",
    "governance/INVALIDATION_REGISTRY.jsonl",
    "governance/CHANGELOG.md",
    "governance/B12_DISPOSITION.json",
    "governance/GOVERNANCE_REGISTRY_VERIFICATION.json",
)


def _copy_governance(staging: Path) -> list[dict[str, Any]]:
    """Copy the whole governance tree by glob (fixes disclosed defect D-2)."""
    root = REPO / "governance"
    copied: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = f"governance/{path.relative_to(root).as_posix()}"
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        seen.add(rel)
        copied.append(
            {
                "path": rel,
                "source": f"repo/{path.relative_to(REPO).as_posix()}",
                "status": "ok",
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    for rel in REQUIRED_GOVERNANCE:
        if rel not in seen:
            copied.append(
                {
                    "path": rel,
                    "source": f"repo/{rel}",
                    "status": f"MISSING:{root / rel[len('governance/'):]}",
                    "required": True,
                }
            )
    return copied


_FREEZE_TAG_RE = re.compile(r"^refs/tags/v(\d+)\.(\d+)-freeze-owtda-cal-r1$")


def _derive_freeze_tag(staging: Path) -> str:
    """The active freeze tag, read from the collected revision artifacts (D-1).

    F-R1-2: the numeric part is ``MAJOR.MINOR`` (``v1.4``), so an ``isdigit()``
    test on the whole component always failed and the derivation silently returned
    ``UNKNOWN``; parse both components explicitly instead.
    """
    path = staging / "revision" / "git_show_ref_tags.txt"
    if not path.exists():
        return "UNKNOWN"
    numbered: list[tuple[tuple[int, int], str]] = []
    for token in path.read_text(encoding="utf-8").split():
        match = _FREEZE_TAG_RE.match(token)
        if match:
            numbered.append(
                ((int(match.group(1)), int(match.group(2))), token.split("/", 2)[2])
            )
    return max(numbered)[1] if numbered else "UNKNOWN"


def _cover(*, now: str, head: str, manifest: dict[str, Any], freeze_tag: str) -> str:
    return f"""# {SUBMISSION_ID}

补件（增量）：原 `OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910` 包保持**只读**，本包只补
材料准入层要求的 P0-1..P0-7。生成时间（UTC）：{now}；冻结 revision：`{head}`。

## 阅读顺序

1. `GATE_RELABEL.json` —— 每个 Gate 的「包内声明」与「材料准入裁定」对照；
2. `DISCLOSURES.md` —— 本轮缺陷、顺序修正、样式让步与未验证外部事实；
3. `revision/REVISION_ACCEPTANCE.json` —— P0-1 六项受理条件；
4. `wstar/worker_confirmation_RC.json` —— P0-3 预登记裁决（含 voided 原因）；
5. `smoke/S03/*_RC.json` 与 `SMOKE_SEAL_*.json` —— P0-6 封 seal 的 G3 证据；
6. `configs/schema/schema_check.json`、`verification/validation_*` —— P0-4/P0-7。

## P0 对照

| P0 | 目录 | 关键对象 |
|---|---|---|
| P0-1 Git 冻结身份 | `revision/` | `OWTDA-CAL-R1.bundle`、零字节 status/stash、`identity_check_*.json` |
| P0-2 真实环境锁 | `environment/` | `uv.lock`、`thread_env.json`、`environment_rebuild_test.json` |
| P0-3 `w*` 确认 | `wstar/` | 预登记协议、12 次配对原始记录、裁决 RC |
| P0-4 严格 schema | `configs/schema/` | 7 个对象 + `schema_check.json` |
| P0-5 amendment/invalidation | `governance/` | 两条哈希链、`reasons/`、`B12_DISPOSITION.json` |
| P0-6 sealed S03 smoke | `smoke/S03/` | ledgers、seals、RUN/STATE 注册表、provenance |
| P0-7 原始测试证据 | `verification/` | `pytest_full.log/.xml`、`ruff_check.log`、环境 |

## 补件后处置（本轮追加）

- `governance/H1_CONSTRUCT_REVIEW_PACKET.{{json,md}}` —— 回答
  `H1-ALTERNATIVE-CONSTRUCT-CONTRACTS = PENDING_CODE_REVIEW`：受审函数按源码 SHA256 固定，
  8 条构造合同全部 PASS，并列出刻意不作的声明；
- `governance/AMENDMENT_PROPOSAL_PARALLELISM_DECOUPLING.md` —— §1 为 `w*` 的历史处置
  （未采纳 12）；§2 的并行度解耦提案**已采纳并生效**（`AM_PARALLELISM_DECOUPLING`，
  `requires_refreeze=true`）。该 amendment 改变了 `compute_spec_hash → freeze_id →
  SCOPE_DESIGN 行哈希`，故**全部合成身份已随之重派生**（这是本轮唯一的身份变更）；
- fail-closed 冻结守卫（`audit/repo_guard.py`）：`build_freeze` / `build_run_admission`
  在写任何字节前拒绝脏的 `src/ configs/ audit/`，杜绝「静默漏项」这一类缺陷（S02 的
  stale `compute_git_commit`、F-B15c-4 的 `source_tree_hash` 漏项）。

## 锚点

- 冻结 tag：`{freeze_tag}`（**从本包 `revision/git_show_ref_tags.txt` 派生**，不再硬编码；
  `v1.0-freeze-owtda-cal-r1` 自始未移动，历史 amendment 标签见该文件与 `DISCLOSURES.md`）
- `freeze_id`：`{manifest.get("freeze_id", "see repo governance/FREEZE_MANIFEST.json")}`
- `source_tree_hash`：见 `revision/source_tree_hash.txt` 与 `revision/source_manifest.json`

## 验证方法

```powershell
certutil -hashfile {SUBMISSION_ID}.zip SHA256     # 与 .zip.sha256 比对
python -c "import hashlib,pathlib;r=pathlib.Path('<解压目录>');L=[l for l in (r/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines() if l.strip()];bad=[l.split('  ',1)[1] for l in L if hashlib.sha256((r/l.split('  ',1)[1]).read_bytes()).hexdigest()!=l.split('  ',1)[0]];print('checked',len(L),'mismatched',len(bad))"
```

> 本包不含任何 L2/L3 科学结论；`§9.4` 与 G3 在新环境下重算后仍为 **PROVISIONAL**。
"""


def _disclosures(*, now: str, freeze_tag: str) -> str:
    return f"""# 披露（{SUBMISSION_ID}）

生成时间（UTC）：{now}；当前冻结 tag：`{freeze_tag}`（由本包 `revision/` 工件派生）。

## 1. 并行度：从「冻结取值」改为「冻结契约」

预登记协议 `configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json` 在任何测量之前入 git
（`protocol_sha256 = df17eb1c…`），**事后未被修改**。执行结果：

| phase | 8 workers（中位数） | 12 workers（中位数） | payload 逐位一致 | 验收 |
|---|---|---|---|---|
| SMOKE_NULL | 166.9 win/s | 187.8 win/s | ✓ | **VOIDED**（一次运行 swap 增量 4 MB） |
| SMOKE_ALT | 358.4 win/s | 403.9 win/s | ✓ | CONFIRMED |

按协议「任一验收条件失败即作废、且**不得重跑改善数字**」，**未采纳 12**；该次作废的确认
未被重跑，全部 12 次运行（含失败运行）原样保留于 `wstar/worker_confirmation_raw.jsonl`。

**`AM_PARALLELISM_DECOUPLING`**：`compute_spec` 的覆盖面收窄为**契约**——线程变量=1、
`invariance_requirement = bitwise_identical_payload`、资源验收（RSS≤24 GiB、swap 增量=0、
未解释 error=0）；实际并行度改为**每 run 记录**——声明值 `SMOKE_CONFIG_v1.json:default_workers`，
实际值 `RUN_REGISTRY.jsonl:workers_used` 与 `provenance.workers_used`（启动时校验两者一致）。
`COMPUTE_FREEZE` 不再含 `w_star`（环境锁只记录观察量）；确认协议与其裁决作为契约证据保留在
`FREEZE_MANIFEST.parallelism_evidence`（**不哈希**，故后续确认不会再次静默移动身份）。
后果：`compute_spec_hash` → `freeze_id` → `SCOPE_DESIGN` 行哈希与全部合成身份随之变更，
因此在正式 run 之前实施（本次即如此）。

## 2. 顺带堵住的静默漂移缺陷

`build_freeze` 在 `freeze_id` 变更时会**静默复用旧 freeze_id 的 REAL 处置链**（
`disposition.validate_chain` 只用各事件自身的 `freeze_id` 重算 genesis，从不与当前冻结比对）。
本 amendment 改为显式判定 `CREATE / REANCHOR / REUSE`：漂移时**追加一条 re-anchor 事件**，
并以 `freeze_id_anchored` 做 fail-closed 校验；`FREEZE_MANIFEST.real_disposition` 记录
`decision` 与 `freeze_id_anchored`。

## 3. 顺序纪律与标签处置

第一次补充序列在 commit **之前**重建冻结，导致 `RUN_COMPONENT_SET.compute_git_commit` 指向的
revision 不包含实际运行源码（与被驳回的 S02 同因）。修正后的顺序固定为「**先提交源码 →
再重建 → 再登记 → 后运行**」，并已加入 fail-closed 守卫（`audit/repo_guard.py`：冻结域脏即
拒绝构建，「无法证明干净」视为不干净）。

- `v1.0-freeze-owtda-cal-r1` **自始未移动**；
- `v1.1`、`v1.2` 保留为历史 amendment 锚点（分别登记 `INV_V11_FREEZE_TAG`、
  `INV_V12_SOURCE_ANCHOR`）；
- 当前冻结 tag 以本包 `revision/git_show_ref_tags.txt` 为准（本节标题行即由该文件派生）。

## 3. 样式让步（显式披露）

`pyproject.toml` 的 ruff 配置新增两条 ignore，理由如下（不是为通过检查而隐匿缺陷）：

- `ISC004`（集合中的隐式字符串拼接）：证据长句按可读性写成编译期拼接，均为相邻字面量对/三元组；
- `UP047`（PEP 695 泛型语法）：`src/owtda_cal/parallel.py` 刻意保留 `TypeVar` 风格；迁移会触碰
  smoke 执行路径，故推迟到本轮之后。

其余 lint 发现（未用导入、`subprocess.run` 缺 `check`、百分号格式、未用 noqa）均已实际修复。

## 4. 未验证的外部数据事实

PAMAP2「恰 23 个合格任务、故 REAL 线 OMITTED」在**未随包提供原始数据**时只能标记
`UNVERIFIED_EXTERNAL_DATA_FACT`：需要官方归档身份（来源、许可证、archive SHA256）、9 个
subject 文件的逐文件 hash、以及 task enumeration 原始输出与拒绝原因明细。该事项**不阻断**
合成 L0 审计。

## 5. 未闭合 / 仍为临时

- `§9.4` 预算与 G3 在新环境（线程变量=1、`ripser` 已声明、`uv.lock` 冻结）下重算，但按裁定
  仍标 **PROVISIONAL**，不得写成最终 PASS；
- 正式 L2/L3 未开始；本包无拒绝率/功效结论；
- B12 编号从未使用，已由 `governance/B12_DISPOSITION.json` 显式处置（无遗漏证据）。

## 6. 禁止事项（本轮遵守）

未启动正式 H0/H1 MC、未生成 L2 拒绝率/功效、未创建 formal `EXPECTED_*_INDEX`/shards/
`PHASE_SEAL`，也未把 G3/预算写成最终 PASS。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="build the audit supplement")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--out", default=str(OUT_PARENT))
    parser.add_argument(
        "--freeze-tag",
        default=None,
        help="override the freeze tag; by default it is derived from the collected "
        "revision/git_show_ref_tags.txt (D-1 fix: never hard-code an identity)",
    )
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root).expanduser()
    out = Path(args.out).expanduser()
    staging = out / SUBMISSION_ID
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for archive_path, source, required in PLAN:
        src = _resolve(source, evidence_root)
        dest = staging / archive_path
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            entries.append(
                {
                    "path": archive_path,
                    "source": source,
                    "status": "ok",
                    "size": src.stat().st_size,
                    "sha256": _sha256(src),
                }
            )
        else:
            entries.append(
                {"path": archive_path, "source": source, "status": f"MISSING:{src}", "required": required}
            )
    entries.extend(_copy_p0_smoke(evidence_root, staging))
    # P0-5: the whole governance tree by glob (D-2: an explicit list went stale).
    entries.extend(_copy_governance(staging))
    freeze_tag = args.freeze_tag or _derive_freeze_tag(staging)

    # newest schema_check_*.json is copied under a stable name
    schema_checks = sorted((evidence_root / "schemas").glob("schema_check_*.json"))
    if schema_checks:
        src = schema_checks[-1]
        dest = staging / "configs/schema/schema_check.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        entries.append(
            {
                "path": "configs/schema/schema_check.json",
                "source": str(src),
                "status": "ok",
                "size": src.stat().st_size,
                "sha256": _sha256(src),
            }
        )
    else:
        entries.append(
            {
                "path": "configs/schema/schema_check.json",
                "source": str(evidence_root / "schemas"),
                "status": "MISSING:schema_check_*.json",
                "required": True,
            }
        )

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (staging / "GATE_RELABEL.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "gate_relabel",
                "submitted_at_utc": now,
                "note": "material-admission labels replace the in-package labels for the read-only package",
                "gates": GATE_RELABEL,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "kind": "supplement_package_manifest",
        "submission_id": SUBMISSION_ID,
        "generated_at_utc": now,
        "supersedes": "none (incremental; the B15c package stays read-only)",
        "closed_p0_items": [
            "P0-1 git freeze identity",
            "P0-2 real environment lock",
            "P0-3 w* confirmation",
            "P0-4 strict schemas",
            "P0-5 amendment/invalidation chains",
            "P0-6 sealed S03 smoke + run/state registries + open_runs fail-closed",
            "P0-7 raw test evidence",
        ],
        "objects": entries,
        "missing_count": sum(1 for e in entries if e["status"] != "ok"),
    }
    (staging / "package_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    head = (
        (staging / "revision/git_rev_parse_HEAD.txt").read_text(encoding="utf-8").strip()
        if (staging / "revision/git_rev_parse_HEAD.txt").exists()
        else "UNKNOWN"
    )
    (staging / "README.md").write_text(
        _cover(now=now, head=head, manifest=manifest, freeze_tag=freeze_tag),
        encoding="utf-8",
    )
    (staging / "DISCLOSURES.md").write_text(
        _disclosures(now=now, freeze_tag=freeze_tag), encoding="utf-8"
    )

    contents: list[tuple[str, bytes]] = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            contents.append((path.relative_to(staging).as_posix(), path.read_bytes()))
    sums = "".join(f"{hashlib.sha256(b).hexdigest()}  {rel}\n" for rel, b in contents)
    (staging / "SHA256SUMS.txt").write_bytes(sums.encode("utf-8"))
    contents.append(("SHA256SUMS.txt", sums.encode("utf-8")))

    zip_path = out / f"{SUBMISSION_ID}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, blob in sorted(contents):
            info = zipfile.ZipInfo(f"{SUBMISSION_ID}/{rel}", date_time=ZIP_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, blob)
    zip_sha = _sha256(zip_path)
    (out / f"{SUBMISSION_ID}.zip.sha256").write_text(
        f"{zip_sha}  {zip_path.name}\n", encoding="utf-8"
    )

    print(json.dumps(
        {
            "submission_id": SUBMISSION_ID,
            "objects": len(entries),
            "missing": [e["path"] for e in entries if e["status"] != "ok"],
            "zip": str(zip_path),
            "zip_bytes": zip_path.stat().st_size,
            "zip_sha256": zip_sha,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if manifest["missing_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
