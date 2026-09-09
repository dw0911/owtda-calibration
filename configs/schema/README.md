# configs/schema — 配置与 schema 目录（B03 占位）

按 OW-TDA-CAL-R1 计划 §20，本目录承载 strict schema（JSON Schema）与配置族：

```
configs/
├── schema/        # scientific_row.schema.json / *_wire.schema.json / config schema
├── smoke/         # blind smoke 配置（phase=SMOKE_NULL/SMOKE_ALT）
├── confirm_null/  # NULL 正式配置
├── confirm_h1/    # ALT 正式配置
└── real/          # REAL_DATA_CONFIG_v1.json / TASK_BUILDER_CONFIG_v1.json / REAL_SCOPE_SPEC_v1.json
```

规则（冻结前闭合）：
- 每个 config 对象用 strict schema 解析并拒绝未知字段；
- `config_hash = H("config", config_kind=..., schema_version=..., config=<strict object>)`
  （由 `owtda_cal.identity.config_hash` 提供）；
- 配置实数以 canonical decimal 文本（`canonical_decimal_text`）进入 payload；
- 首份 machine schema（`scientific_row` 族与 `*_wire` 双 schema）随 scope/index 批次建立
  （B05 预告），届时 golden fixtures 一并登记。

当前状态：目录占位（B03）。除本 README 外暂无 schema 文件。
