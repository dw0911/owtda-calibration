# DATA_SOURCES — 数据出处与校验

> 原则：**数据不随本仓库分发**；出处、许可、文件清单与逐文件 SHA256 完整登记于此，便于独立获取与校验。

## 1. PAMAP2 Physical Activity Monitoring Data Set

| 项 | 值 |
|---|---|
| 名称 | PAMAP2 Physical Activity Monitoring Data Set |
| 作者 | Attila Reiss, Didier Stricker |
| 发布 | UCI Machine Learning Repository（Dataset ID 231），2012 |
| 下载页 | https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring |
| 建议引用 | Reiss, A., & Stricker, D. (2012). *Introducing a New Benchmarked Dataset for Activity Monitoring.* 16th IEEE International Symposium on Wearable Computers (ISWC), pp. 108–109. DOI: 10.1109/ISWC.2012.13 |
| 许可 | CC BY 4.0（以 UCI 页面当前声明为准；使用时请遵守其条款） |
| 本项目用途 | 本代实验的唯一真实数据来源；REAL 线为条件章节（见 §4） |

### 1.1 官方归档（外层下载包）

| 项 | 值 |
|---|---|
| 官方静态包 | `PAMAP2_Dataset.uci_static_231.zip`（raw_download/） |
| 大小 | 688,226,940 B |
| SHA256 | `76b3580bd5a804121f507717cb498c66a312ef5c774f4a78ac470e6558add352` |
| 内层 zip SHA256 | `6c2282b5b52775cd0588d450d10a315260c94fa3228b9fe453f48c47fda106f4` |
| `readme.pdf` SHA256 | `99a0339f1d754089fc2f7f2c24f5a47888a51dc0646a8b210af60358c00da30d` |

### 1.2 Protocol 数据文件（数据身份对象）

放置约定：`<base_dir>/Protocol/subject101.dat … subject109.dat`；
数据身份：`dataset_hash = H("pamap2_protocol_dataset", 9 × {path, size, file_sha256})`
（路径按 POSIX、排序固定；实现见 `src/owtda_cal/realdata.py`）。

| 相对路径 | 大小 (B) | SHA256 |
|---|---:|---|
| `Protocol/subject101.dat` | 141,698,539 | `80b3fffd089c236ae88098df3b906b8d3c67a858023fe4f75045d78612147266` |
| `Protocol/subject102.dat` | 207,349,310 | `468f3c6ba3e6e961f383783665265afbcddbbd33a3a84bba0386b7d0d4e3c632` |
| `Protocol/subject103.dat` | 117,863,364 | `5be64631d085e3efc700728395516da3512ff9de17dab30d253508441a98d3f0` |
| `Protocol/subject104.dat` | 153,227,482 | `7eb272213cbfe11d9e466a2163b6c9c2ed8d2542fc6f08283fd1bf222cac8994` |
| `Protocol/subject105.dat` | 173,773,599 | `7837cfede57fe45ec20d553c6c2b0c498ab324daae23bfd202c0ffea9f71a7f6` |
| `Protocol/subject106.dat` | 168,263,273 | `0da1dda3fa56d75d6413fc9198949d3ebc2102d77574cb5fe0739674687609f2` |
| `Protocol/subject107.dat` | 145,823,268 | `a02195e9599eb249f79103912d27eb4f62d8a0f59e4763b0dd8250fee5f3f020` |
| `Protocol/subject108.dat` | 190,019,653 | `81ce6b21b9c1e01dc02099c4f9387699547b08b28b387d09a56e0cb0a8af22fc` |
| `Protocol/subject109.dat` | 3,891,140 | `5109d5cd8334769566b4ae602adf3e5f4bb7b9ee8ca678f0c481d333114b07c7` |

> 上述大小与 SHA256 来自项目的数据引入探测记录（`download_probe_manifest.json`，2026-09-09），
> 与正式数据身份冻结记录同源，可逐文件独立复算。

## 2. 获取步骤

1. 从 UCI 数据集页下载 `PAMAP2_Dataset` 归档；
2. 解出 `Protocol/subject101.dat … subject109.dat` 九个文件；
3. 按 §1.1、§1.2 的 SHA256 逐文件校验；
4. 将 `Protocol/` 目录置于本地任意 `base_dir` 下（见 §1.2 放置约定）。

## 3. 数据操作与溯源

- 数据引入为冻结规则（54 令牌/行、严格时钟网格、缺失不填补、固定插值序列等），实现于
  `src/owtda_cal/pamap2_import.py`，契约测试见 `tests/test_pamap2_import.py`；
- 数据操作（下载、校验、切分）必须留脚本记录；不得覆盖式修改原始数据。

## 4. 本代 REAL 线状态（如实披露）

REAL 任务闸门判定为**数据事实失败**：9 名受试者中 8 名准入、合格任务 23 < 24（`subject109` 无候选），
按预注册分流登记 `REAL_OMITTED_BY_DATA_GATE`（stage `REAL_DATA_FROZEN`，reason `TASK_GATE_MIN_TASKS_NOT_MET`），
未下调准入线、未放宽阈值。因此：

- 论文正文的 REAL/PAMAP2 为**条件章节**（`manuscript/sections/07_real.tex` 仅保留说明）；
- **复现合成主线（H0/H1、P1–P3、图 1–5 与表 1–4）不需要 PAMAP2 数据**。

## 5. 其他数据

| 对象 | 说明 |
|---|---|
| 合成实验数据（N-AR / N-CIRCLE DGP） | 由代码 + 冻结种子程序化生成（`src/owtda_cal/dgp.py`、`seeding.py`），无需外部数据 |
| 旧代 DMB-R1 证据 | `external_prior_evidence/DMB_R1/`（L1 历史证据，含归档校验清单；不参与本代估计） |
