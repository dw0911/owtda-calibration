# OW-TDA-CAL-R1 论文骨架（Manuscript Outline）

> 状态：骨架（B01）。正文数字只允许来自 L2/L3 sealed ledger 经 canonical summary 派生，
> 禁止在草稿中硬编码任何结果数字。
> 内部完整标题：《重叠滑动窗口下拓扑扫描检验的交换性失效与有限样本校准边界》
> 投稿题目（暂定）：《重叠窗口拓扑扫描的校准边界》

## 1. 论文结构（计划 §22，正文 10 章）

1. **引言**：TDA 变点背景、IID 检验与重叠派生对象之间的缺口、三项贡献。
2. **拓扑窗口扫描框架**：窗口、点云、VR 持续同调、BPI/MOMENTS、CUSUM 扫描统计量（候选集、plateau、中位索引）。
3. **交换性与校准理论**：T1 依赖继承 → T2 交换性失效精确反例 → T3 有限样本方差放大 → T4 过程极限错配 → T5 trace 诊断。
4. **实验协议**：N-AR / N-CIRCLE DGP、fixed-M / fixed-T 双预算、M0/M1、MC 规模、审计链。
5. **有限样本校准边界**：28 格 Type-I（图3/4）、p 值左尾与 critical value（图5）、依赖放大（图6）。
6. **构造效度、功效与定位**：单时点边际均值-协方差匹配形状变化与 mean-shift 反向控制。
7. **PAMAP2 说明性案例**（条件章节：完整通过身份/隔离/evaluation seal 才进正文；否则删除并说明外部验证尚缺）。
8. **讨论**：适用边界、DMB-R1 局限、未来 stride-equivariant 方法（→ R2）。
9. **结论**。
10. **补充材料**：完整证明（含 T1）、全部次级格、配置、seed、旧证据披露、复现说明。

## 2. 图表计划（计划 §21，只读 L2/L3）

主图 8 张：
| # | 内容 | 数据来源 |
|---|---|---|
| 图1 | raw series → windows → diagrams → BPI → scan 机制图 | 示意图（非结果） |
| 图2 | 窗口均值解析 A_mean,M 与 overlap 关系 | 解析/数值（T3） |
| 图3 | Fixed-M Type-I heatmap | H0 L2 |
| 图4 | Fixed-T Type-I heatmap | H0 L2 |
| 图5 | p 值 ECDF 左尾 + 经验 0.95 critical value | H0 L2 |
| 图6 | A^tr_Phi,M 与 Type-I 联合图 | H0 L2 |
| 图7 | 两种 H1 的 size-standardized power | H1 L2 + N-CIRCLE H0 |
| 图8 | PAMAP2 转移区间示例及 stride-dependent decisions | L3（条件） |

主表 6 张：表1 DGP/预算/stride/T/M/overlap/方法；表2 主 H0 拒绝率 + Wilson CI；
表3 P1–P3 对比 + basic bootstrap CI + Holm p；表4 校准分类与 eligibility；表5 功效/size/size-adjusted/定位；
表6 PAMAP2 subject-level 完整结果（条件）。

输出：PDF/SVG/PNG + `.meta.json`（含输入 ledger hash、脚本 hash、环境 hash、生成时间）。

## 3. 数据流（唯一，禁止手工硬编码数字）

```
sealed trial JSON → validated canonical ledger → canonical summaries
→ tables/figures → manuscript_values.json → manuscript consistency checker
```

## 4. 稿件 GO/NO-GO（2026-10-12，计划 §18.3）

必要条件：
- C1 理论反例成立；T3 解析式与独立数值一致；
- C2 或 C3 至少一项按 Holm 规则得到 L2 支持；
- 28 格 H0 与 8 格 H1 全部 seal；
- 论文主张与近邻文献仍有明确差异。

不满足即停止赶投本专题，完整负结果继续归档。该判断不触发参数调整。

## 5. 文件落位（后续批次创建）

- `manuscript/main.tex` 或 Word（期刊格式转换排在 2026-10-24/25）
- `manuscript/figures/`、`manuscript/tables/`（程序化产物，暂不提交）
- `manuscript/manuscript_values.json`（由 consistency checker 派生）
