# OW-TDA-CAL-R1 — 快捷入口
# 正式入口仍是 Python CLI（scripts/*.py）；本 Makefile 只是糖衣。
# 需要 uv（https://docs.astral.sh/uv/）。Windows 用户可用 `uv run` 直接执行对应命令。

PY ?= uv run python

.PHONY: help install test lint smoke quick analysis tables figures p1p3 paper sums index clean

help:
	@echo "install   安装锁定环境 (uv sync --frozen)"
	@echo "test      回归测试 (pytest tests -q)"
	@echo "lint      静态检查（代码与工具域）"
	@echo "smoke     端到端冒烟（不含论文结论）"
	@echo "quick     Level 1 快速完整性验证"
	@echo "analysis  Level 2（P1-P3 / 表 / 图 的再生成一致性）"
	@echo "tables    由 canonical 汇总重建表"
	@echo "figures   由表重建图"
	@echo "p1p3      P1-P3 真实 draws → p / CI / Holm"
	@echo "paper     编译论文（XeLaTeX）"
	@echo "sums      重算 reproducibility/SHA256SUMS"
	@echo "index     重算复现清单（SEED/ARTIFACT/FORMAL/EXPECTED）"
	@echo "clean     清理编译中间件与临时目录"

install:
	uv sync --frozen

test:
	$(PY) -m pytest tests -q

lint:
	uv run ruff check src tests audit scripts configs

smoke:
	$(PY) scripts/run_smoke.py

quick:
	$(PY) scripts/verify_release.py --level quick

analysis:
	$(PY) scripts/bootstrap_primary_contrasts.py --check
	$(PY) scripts/build_tables.py --check
	$(PY) scripts/build_figures.py --check
	$(PY) scripts/analyse_h0.py --check
	$(PY) scripts/analyse_h1.py --check
	$(PY) scripts/verify_release.py --level analysis

tables:
	$(PY) scripts/build_tables.py

figures:
	$(PY) scripts/build_figures.py

p1p3:
	$(PY) scripts/bootstrap_primary_contrasts.py

paper:
	cd paper && xelatex -interaction=nonstopmode main.tex && bibtex main && xelatex -interaction=nonstopmode main.tex && xelatex -interaction=nonstopmode main.tex

sums:
	$(PY) scripts/build_sha256sums.py

index:
	$(PY) scripts/build_reproducibility_index.py

clean:
	rm -rf build paper/*.aux paper/*.log paper/*.out paper/*.blg paper/*.bbl paper/*.synctex.gz
