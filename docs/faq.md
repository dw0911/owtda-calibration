# FAQ

**Q1 我只想确认"数字没问题"，最短路径是什么？**
`python scripts/verify_release.py --level quick`（秒级）。它把论文用到的每个量都与 `results/canonical/` 对账。

**Q2 为什么 `src/` 里叫 `owtda_cal` 而不是 `owtda`？**
包名被 `pyproject.toml` 与逐文件 `code_file_manifest` 绑定，改名会使已封存 run 身份无法复核。见 `docs/artifact_map.md`。

**Q3 为什么仓库里没有 3.2 GB 的账本？**
GitHub 单文件 100 MiB 限制 + 学术归档惯例：账本登记在 `data/manifests/external_artifacts.json`
（大小 + SHA-256 + seal 绑定），用 `scripts/fetch_archived_data.py` 获取与校验；DOI 待 Zenodo 归档。

**Q4 `H0_PRIMARY_CONTRASTS.json` 里的 `p = 0` 是怎么回事？**
那是 2026-09-18 交付对象的旧字段：在加一规则下 p 不可能为 0，R1 审计已裁定重算。
为保哈希链，旧字节保留；**现行有效值**在 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`
（tail = 0 → p = 1/10001，Holm = 3/10001）。`verify_release` 只对现行值强制"p > 0"。

**Q5 为什么 `validate_freeze.py` 会报一项 FAIL？**
`source_tree_hash` 单项：入库 `src/` 是 R4/R5 修复后的较新版本，而 `FREEZE_MANIFEST` 记录的是更早一次冻结的源树。
其余检查全 PASS；已封存 seal 不受影响。见 `reproducibility/FAILURE_POLICY.md` §5。

**Q6 表 1–5 能重生成吗？**
原始生成器未随项目保留（已如实披露）。表数据、输入文件与输入哈希都在仓库里，
`verify_release` 会校验表 `meta.json` 记录的输入哈希；重生成器将随图表重构轮补入。见 `REPRODUCIBILITY.md` §3.5。

**Q7 我能改 `pyproject.toml` 加个依赖吗？**
不能直接改：它进入 `environment_lock_hash`，与既有 seal 绑定。需要走 amendment 流程（见 `governance/CHANGELOG.md`）。

**Q8 图件重新生成后为什么 PDF/SVG 的哈希变了？**
它们内嵌创建时间等元数据；**PNG 逐字节稳定**，内容由 canonical 表决定。`scripts/build_figures.py --check`
因此校验的是"输入哈希"而不是输出字节。见 `REPRODUCIBILITY.md` §3.3。

**Q9 双盲审稿怎么办？**
若目标期刊双盲：公开仓库/作者名/ORCID/提交历史的暴露时间须服从期刊规定。见 `AUTHORS.md` 与 README §Contact。
