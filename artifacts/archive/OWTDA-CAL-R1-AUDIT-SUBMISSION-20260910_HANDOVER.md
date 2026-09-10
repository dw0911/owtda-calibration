# OW-TDA-CAL-R1 审计提交包 — 交接说明

> 提交 ID：`OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910`
> 生成日期：2026-09-10（北京时间）
> 生成者：本地执行方（登记主机 `f:/BPI/owtda-calibration`，Windows 11 / 16 核）
> 对象：方案方 / 独立审计

本文件夹是**自包含、逐字节可验证**的归档：覆盖 OW-TDA-CAL-R1 全部已完成的实验批次
（B01–B15c），并已按审计要求（`audit_spec` 的 run/seal/gate/freeze 证据形态 + Plan §20.1
的交付合同）组织。

---

## 1. 建议的阅读顺序

1. `OPEN_ISSUES_AND_DECISIONS.md` —— **问题 8 项 + 待你裁定的决断 5 项**（本次提交的重点）；
2. `AUDIT_SUBMISSION_RECORD.md` —— 提交说明：覆盖的实验、关键数字、Gate 判定表；
3. `AUDIT_REQUEST.json` —— 机器可读的审计请求（请求复核的范围、Gate ID 列表）；
4. `package/gates/*.md` —— 6 个 Gate 对象（JSON 为权威，MD 由其渲染）；
5. `package/README.md` —— 归档内部结构与校验方法。

---

## 2. 锚点（Anchor）

| 项 | 值 |
|---|---|
| 运行期 HEAD | `52ad45aa3f80d6424658c43a47f2879df5fb8841`（B15b commit；工作区 clean = **False**） |
| `freeze_id` | `7cb4f85e31394b23f6c9d6bcaa9ce6a7fc7b824b2b5c8fb6b600c9181979322d`（未变） |
| `source_tree_hash` | `0cd15a9676961622e9c203f8f9fbd9c51d1d61566affe3a3c0282f2176015ee6`（45 文件） |
| `smoke_config_hash` | `fc4c54b9023d0194b3d805500f50f21dc999a46a6633eb331d02211673800be0` |
| 冻结 tag | `v1.0-freeze-owtda-cal-r1` → `e16222f`（未移动） |
| ZIP SHA256 | 见 `OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip.sha256` |
| `package_manifest.json` SHA256 | 见 `PACKAGE_MANIFEST.sha256` |

---

## 3. 如何校验（两条命令）

```powershell
# (a) 密封包本身
certutil -hashfile OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip SHA256
#     应与同名 .zip.sha256 中的值一致

# (b) 解压内容逐项自校验（应输出 sums_mismatched 0）
python -c "import hashlib,pathlib;r=pathlib.Path('package');L=[l for l in (r/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines() if l.strip()];bad=[l.split('  ',1)[1] for l in L if hashlib.sha256((r/l.split('  ',1)[1]).read_bytes()).hexdigest()!=l.split('  ',1)[0]];print('checked',len(L),'mismatched',len(bad),bad[:5])"
```

规则：`SHA256SUMS.txt` 覆盖除自身与 `package_manifest.json` 外的全部成员；
`package_manifest.json` 覆盖除自身外的全部成员（含 `SHA256SUMS.txt`），并记录
`path / source_path / role / size / sha256`；两者 + 外部 `.zip.sha256` 共同封闭整个包。

---

## 4. Gate 判定（摘要）

| gate | status |
|---|---|
| `G0-FREEZE-CHAIN-AND-IDENTITY` | **PASS**（含 1 项具名偏离 OP-1：工作区未提交） |
| `G3-BLIND-SMOKE-BOTH-PHASES` | **PASS** |
| `SECTION-9-4-COMPUTE-BUDGET` | **PASS** |
| `H1-ALTERNATIVE-CONSTRUCT-CONTRACTS` | **PASS**（L0 证据） |
| `W-STAR-CONFIRMATION` | **FAIL_UNCONFIRMED** ← 待裁定（D-1） |
| `SOURCE-REVISION-ADMISSIBILITY` | **BLOCKED_PENDING_OPERATOR_ACTION** ← 待提交（D-5） |

关键数字：SMOKE_NULL 896/3,584/73,600（`t_0,32 = 842.03 s`）、SMOKE_ALT 256/1,024/49,152
（`t_1,32 = 272.52 s`）；`t_H0_hat = 22.842 h`、`t_H1_hat = 4.731 h`、`t_core_hat = 27.573 h`；
peak RSS 1.393 GiB、swap 增量 0、磁盘 386.1 MiB、`open_runs = 0`。

---

## 5. 文件夹内容

```text
OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910/
├── 00_START_HERE.md                    本文件
├── AUDIT_SUBMISSION_RECORD.md          提交说明
├── OPEN_ISSUES_AND_DECISIONS.md        问题 8 项 + 待决断 5 项（人读）
├── AUDIT_REQUEST.json                  审计请求（机器可读）
├── OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip        密封归档
├── OWTDA-CAL-R1-AUDIT-SUBMISSION-20260910.zip.sha256 其 SHA256
├── PACKAGE_MANIFEST.sha256             package_manifest.json 的 SHA256
└── package/                            解压后的完整归档（可原地校验）
    ├── README.md / SHA256SUMS.txt / package_manifest.json / closure_summary.json
    ├── repo/          被审计工作树（git 跟踪内容）
    ├── source/        冻结源域 manifest、复算的 source_tree_hash、git 状态
    ├── gates/         6 个 Gate 对象（JSON 权威 + 渲染 MD）
    ├── submission/    受理记录、审计请求、问题/决断登记
    ├── superseded/    被 B15c 作废的 S01 smoke 证据与作废理由
    └── batches/       B01–B15c 全部 21 个批次交付四件套
```

---

## 6. 未闭合事项（提交前请先看）

1. **D-5 具名 commit（受理前置）**：当前工作区含未提交变更（HEAD 仍为 `52ad45a`），
   而审计要求阻断冻结域内 dirty 文件。归档内容已按 `source_tree_hash` + 逐对象 sha256 锚定，
   **commit 不改动文件内容，故提交后本包所有哈希依旧有效**。
2. **D-1 `w*` 裁定**：worker 扫描显示 payload 在全部 worker 数下逐位一致，但吞吐
   **w=12 高于冻结的 w=8**（H0 +8.1%、H1 +6.3%，超过 §9.4 的 2% 并列阈值）。
   因 `w_star` 属 `COMPUTE_SPEC`（改动将经 `compute_spec_hash → freeze_id → SCOPE_DESIGN`
   波及全部合成身份，等价重新冻结），本次**未作单方面修改**；两选项均不改变任何已达成
   Gate 的结论。
3. 其余：D-2（B15b 判定撤回登记）、D-3（§15.2 增行 / S01→S02 代次提升的 amendment 登记）、
   D-4（`smoke_ids.py` 是否纳入冻结源域）—— 详见 `OPEN_ISSUES_AND_DECISIONS.md`。

---

## 7. 明确排除项（按合同）

| 排除 | 原因 |
|---|---|
| `secrets/` | 隔离的 REAL task root key / task id salt（永不打包、永不入库） |
| `.git/` | 仓库历史；审计所需内容已由 `repo/` + `batches/` + `source/` 覆盖 |
| `artifacts/archive/` | 既往归档 ZIP 与封套文件（禁止自包含） |
| `__pycache__` / `.pytest_cache` / `.ruff_cache` | 缓存 |

> 本代证据等级目前为 **L0**（单元/攻击测试、blind smoke、预算探针）；正式合成实验（L2）
> 尚未开始，REAL 线（L3）已 disposition 为 `OMITTED_BY_DATA_GATE`（23 < 24 任务，属数据事实）。
> 本包不含任何可用于论文的 L2/L3 数字。
