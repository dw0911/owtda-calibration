# ENVIRONMENT — 环境与依赖

## 1. 权威锁定

| 项 | 值 |
|---|---|
| 解释器 | CPython **3.12.10**（`requires-python = ">=3.12,<3.13"`） |
| 直接依赖 | `numpy==2.2.6`、`scipy==1.15.3`、`ripser==0.6.15`（`pyproject.toml`） |
| 开发/证据工具 | `pytest==9.1.1`、`ruff==0.16.6`、`psutil==7.2.2` |
| 锁文件 | `uv.lock`（权威）；冻结环境记录见 `environment/`（版本、BLAS、线程、`pip freeze`、仓库外重建测试） |
| 环境锁哈希 | `environment_lock_hash` 覆盖 `pyproject.toml` + `uv.lock` + 版本/OS/CPU/BLAS/线程设置（见 `governance/COMPUTE_FREEZE.json`） |

> ⚠️ `pyproject.toml` / `uv.lock` 属**已被 seal 绑定**的文件：修改会使 `environment_lock_hash` 与既有 seal 不一致。
> 复现请勿改动它们。

## 2. 安装

```powershell
uv sync --frozen          # 按锁定版本安装（推荐）
# 或
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[test,dev]"; python -m pip check
```

## 3. 运行约定（与正式结果一致）

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"; $env:NUMEXPR_NUM_THREADS = "1"
```

`scripts/frozen_env.py` 在解释器启动前设定这四个线程变量并留证（`environment/thread_env.json`）。
并行度契约（`governance/COMPUTE_FREEZE.json`）：`workers ∈ 1..cpu_count`、逐位一致的载荷、
`workers_used` 每 run 记录、验收 `RSS ≤ 24 GiB ∧ swap 增量 = 0 ∧ 未解释 error = 0`。

## 4. 已验证的环境

| 平台 | 结果 |
|---|---|
| Windows（本仓库快照的构建环境） | `pytest tests -q` → **1069 passed / 1 skipped**；`ruff check src tests audit scripts configs paper/scripts` 全清；论文 XeLaTeX 编译通过（MiKTeX） |
| 纯净克隆（从 git bundle，`uv sync --frozen`） | 同上（2026-09-20 复现校验，见 `../reproducibility/VALIDATION_SUMMARY.md`） |

## 5. 论文图表生成路径的附加依赖

| 项 | 说明 |
|---|---|
| `matplotlib` | 生成 `artifacts/figures/*` 所需；通过锁定环境（`uv sync --frozen`）获得。`pyproject.toml`/`uv.lock` 属冻结对象（见 §1 警告），本代未把 matplotlib 提升为直接依赖；CI 设有一项 `import matplotlib` 检查，确保该路径可用。 |
| CJK 字体 | 图内标签为中文，需可确定获得的字体：Windows/macOS 用系统字体，Debian/Ubuntu 用 `fonts-noto-cjk`（本机与 CI 均解析到 `Noto Sans SC`）。`paper/scripts/make_figures.py --check-fonts` 断言字体存在；缺字体时生成脚本默认**报错退出**，不静默产出缺字方框。 |
| 论文编译 | 工作目录为 `paper/`（`main.tex` 使用 paper 相对输入）；XeLaTeX + bibtex（本机 MiKTeX；CI 用 `xu-cheng/latex-action`）。CI 与发布构建使用严格模式 `touch paper/STRICT.tex`：缺图件、缺表或未定义引用都会失败。 |
