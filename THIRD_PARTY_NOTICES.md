# THIRD_PARTY_NOTICES — 第三方组件与数据声明

> 本仓库**不重新分发**任何第三方数据、字体或图标；下表列出直接使用的第三方软件与数据的来源与许可。

## 1. 直接依赖（`pyproject.toml`）

| 组件 | 版本 | 许可 | 用途 |
|---|---|---|---|
| NumPy | 2.2.6 | BSD-3-Clause | 数值计算 |
| SciPy | 1.15.3 | BSD-3-Clause | 统计与线性代数 |
| ripser | 0.6.15 | MIT | 持续同调（PH）计算 |
| pytest | 9.1.1 | MIT | 测试（开发） |
| ruff | 0.16.6 | MIT | 静态检查（开发） |
| psutil | 7.2.2 | BSD-3-Clause | 资源采样（证据） |
| Matplotlib（传递依赖，供绘图） | ≤3.11 | PSF-based（Matplotlib License） | 图件生成 |

完整传递依赖树与锁定版本见 `uv.lock`；各组件许可以其发布包内的 LICENSE 为准。

## 2. 数据

| 数据 | 来源 | 许可 | 本仓库处理 |
|---|---|---|---|
| PAMAP2 Physical Activity Monitoring | UCI ML Repository（Reiss & Stricker, 2012） | CC BY 4.0（以 UCI 页面为准） | **不重新分发**；出处与逐文件 SHA-256 见 `DATA_SOURCES.md` |
| 旧代 DMB-R1 证据 | 本项目旧代终止归档 | 本项目所有 | **不重新分发**（2026-09-20 已从公共树剔除）；不参与本代任何估计，保留在开发历史与工作区归档中 |
| 合成数据（N-AR / N-CIRCLE） | 本项目生成 | 适用本仓库数据许可 | 由代码 + 冻结种子生成，不含第三方内容 |

## 3. 字体与图形

- 图件脚本引用的 `SimHei` / `Microsoft YaHei` 为**系统字体**，本仓库不包含字体文件；
  在缺字体的环境中重绘时，请自行安装具有相应授权的字体（或修改 `paper/scripts/make_figures.py` 的字体设置）。
- 未使用第三方图标或剪贴画。

## 4. 上游代码片段

- `paper/scripts/make_figures.py` 为本项目自有代码；
- 未包含任何来源不明的复制代码。若你在本仓库中发现疑似第三方片段，请提交 issue。
