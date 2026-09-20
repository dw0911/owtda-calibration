# data/ — 数据与大型归档

> 本目录**不含**真实数据，也不含大型正式账本。它只保存描述、清单与校验和；数据获取与验证由脚本完成。

| 路径 | 内容 |
|---|---|
| `README.md` | 本文件 |
| `manifests/formal_ledgers.json` | 正式账本登记（路径、行数、SHA-256、seal 绑定） |
| `manifests/external_artifacts.json` | 外部归档登记（Zenodo DOI 占位、大小、SHA-256、来源） |
| `manifests/SHA256SUMS` | 清单文件自身的校验和 |
| `sample/` | 极小样例（测试与示例脚本用，不含真实数据） |
| `external/` | 下载目标目录（`.gitkeep` 占位；内容不入库） |

## 1. 三类数据

| 类别 | 位置 | 是否入库 | 说明 |
|---|---|---|---|
| 合成实验数据（N-AR / N-CIRCLE） | 由代码 + 冻结种子程序化生成 | — | 复现合成主线只需代码与种子，不需要任何外部数据 |
| 真实数据（PAMAP2 Protocol） | 外部，见 [`../DATA_SOURCES.md`](../DATA_SOURCES.md) | 否 | 出处/许可/逐文件 SHA-256 已完整登记；本代 REAL 线因数据闸门 omission |
| 正式账本与大型索引 | 外部归档（`manifests/external_artifacts.json`） | 否 | 哈希与 seal 绑定一致；用 `python scripts/fetch_archived_data.py` 验证/获取 |

## 2. 使用

```powershell
python scripts/fetch_archived_data.py --list          # 查看登记与 DOI 状态
python scripts/fetch_archived_data.py --verify-only   # 校验本地已有副本
python scripts/fetch_archived_data.py                 # 下载/复制到 data/external/（DOI 就绪后）
```

获取到账本后即可执行 Level 2 分析：

```powershell
python scripts/analyse_h0.py --from-ledger data/external/H0_NULL_evaluation.scientific.jsonl
python scripts/analyse_h1.py --from-ledgers --delivery <交付目录> --h0-eval <H0 账本> --h1-eval <H1 账本> --out-dir <新目录>
```

> 归档 DOI 在创建 GitHub release 后由 Zenodo 生成；本文件与 `CITATION.cff`、`reproducibility/RELEASE_MANIFEST.json`
> 三处同步更新（见 `reproducibility/DATA_AVAILABILITY.md`）。
