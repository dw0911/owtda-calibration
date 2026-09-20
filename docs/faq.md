# FAQ

**Q1 我只想确认"数字没问题"，最短路径是什么？**
`python scripts/verify_release.py --level quick`（秒级）。它把论文用到的每个量都与 `results/canonical/` 对账。

**Q2 为什么 `src/` 里叫 `owtda_cal` 而不是 `owtda`？**
包名被 `pyproject.toml` 与逐文件清单绑定，改名会使已封存 run 身份无法复核。

**Q3 为什么仓库里没有 3.2 GB 的账本？**
账本是正式运行的完整记录，体积超过 GitHub 限制且**不随仓库分发**；其哈希登记在
`data/manifests/external_artifacts.json` 供核对。**复现论文的合成实验不需要账本**——
从头重跑用 `scripts/reproduce.py`。

**Q4 `H0_PRIMARY_CONTRASTS.json` 里的 `p = 0` 是怎么回事？**
那是旧交付对象的字段：在加一规则下 p 不可能为 0。为保哈希链，旧字节保留；
**现行有效值**在 `results/bootstrap/P1_P3_BOOTSTRAP_SUMMARY.json`
（tail = 0 → p = 1/10001，Holm = 3/10001）。`verify_release` 只对现行值强制"p > 0"。

**Q5 表 1–5 能重生成吗？**
能。`paper/scripts/make_tables.py` 从 canonical 源生成正文表 1–5，正文 `\input` 生成结果；
`python scripts/build_tables.py --check` 做 fail-closed 比对。

**Q6 我能改 `pyproject.toml` 加个依赖吗？**
不能直接改：它进入 `environment_lock_hash`，与冻结身份绑定。

**Q7 图件重新生成后为什么 PDF/SVG 的哈希变了？**
它们内嵌创建时间等元数据；**PNG 逐字节稳定**，内容由 canonical 表决定。`scripts/build_figures.py --check`
因此校验的是"输入哈希"而不是输出字节。
