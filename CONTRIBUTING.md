# CONTRIBUTING — 贡献与提交路径

> 本仓库是**论文配套的可复现发布**：科学结果已被封存（seal 不可改写），因此贡献主要面向
> 工具、文档、测试与复现路径；**不得**改动已封存对象或冻结的科学内容。

## 1. 提交前自检（全部必须通过）

```powershell
python -m pytest tests -q
python -m ruff check src tests audit scripts configs
python scripts/run_smoke.py
python scripts/verify_release.py --level quick
```

涉及 `results/`、`artifacts/`、`reproducibility/` 的改动还需：

```powershell
python scripts/build_reproducibility_index.py
python scripts/build_sha256sums.py
python scripts/verify_release.py --level quick    # 再跑一次，SHA256SUMS 必须自洽
```

## 2. 硬性约束

| 约束 | 原因 |
|---|---|
| **不得**修改 `pyproject.toml` / `uv.lock` | 二者被 `environment_lock_hash` 绑定；如需变更须走 `governance/AMENDMENT_REGISTRY.jsonl` 流程 |
| **不得**改写 `artifacts/seals/`、`results/canonical/` 中已登记对象、`governance/*_REGISTRY.jsonl` | 均被哈希链绑定，只允许 append-only 追加 |
| 任何"看似等价"的数值改写都需先给"故意破坏后必须失败"的测试 | 本项目的合同纪律（见 `governance/CHANGELOG.md` 2026-09-11 裁决） |
| 新增结果一律写入**新文件/新目录**，不得就地覆盖 | 复现与审计要求（输出目录必须不存在） |

## 3. 提交信息

- 中文/英文均可；请写清：改了什么、为什么、如何验证；
- 若涉及科学内容或治理对象，请在信息中给出来源文档与哈希；
- 一次提交只做一件事（工具/文档/复现链分离）。

## 4. 缺陷与复现报告

- 代码缺陷 → 用 `Bug report` 模板；
- 复现结果（成功/失败）→ 用 `Reproducibility report` 模板，并附 `git rev-parse HEAD`、环境与本机输出。
