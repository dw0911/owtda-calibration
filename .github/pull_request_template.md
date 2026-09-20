## 变更内容

（一段话说明改了什么、为什么）

## 检查清单

- [ ] `python -m pytest tests -q` 通过
- [ ] `ruff check src tests audit scripts configs` 全清
- [ ] `python scripts/run_smoke.py` 通过
- [ ] `python scripts/verify_release.py --level quick` 全部 PASS
- [ ] 若改动涉及 `results/canonical/`、`artifacts/` 或 `reproducibility/`：
      `python scripts/build_reproducibility_index.py && python scripts/build_sha256sums.py` 已重跑
- [ ] 若改动涉及测试/契约：按纪律附一个"故意破坏后必须失败"的测试
- [ ] **未改动** `pyproject.toml` / `uv.lock`（二者被 `environment_lock_hash` 绑定，如需改动须走 amendment 流程）
- [ ] 未覆盖任何已封存对象（seal / ledger / registry / attempt）

## 关联 issue

Closes #
