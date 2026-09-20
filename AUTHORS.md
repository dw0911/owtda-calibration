# AUTHORS — 作者与贡献者

> ⚠️ **待填写（PENDING）**：作者姓名、单位与 ORCID 需由通讯作者在投稿前确认。
> 本文件与 `CITATION.cff` 必须保持一致；**不要**在此处填写未经确认的个人信息。

## 论文作者（PENDING）

| 顺序 | 姓名 | 单位 | ORCID | 角色 |
|---|---|---|---|---|
| 1 | （待填） | （待填） | （待填） | 通讯作者 |
| … | | | | |

## 软件贡献

| 范围 | 说明 |
|---|---|
| 设计与实现 | 见论文作者名单 |
| 复现链工具（`scripts/`、`audit/`、`paper/scripts/`） | 本仓库批次记录，见 `governance/CHANGELOG.md` |
| 匿名审稿兼容 | 若目标期刊采用双盲审稿：公开仓库、作者名单、ORCID 与提交历史的暴露时间须服从期刊规定（见 `README.md` §Contact） |

## 填写流程

1. 通讯作者确认名单与顺序 → 2. 填入本表 → 3. 同步 `CITATION.cff`（`authors` / `preferred-citation`，
   并在同一提交中设置 `repository-code`）→ 4. 提交信息注明 "authors finalized for submission"。

## 与发布门的关系（P0-1）

公开发布前必须同时闭合：作者名单（本文件）、代码/数据/论文三项许可（`LICENSE`、`LICENSES/`）、
版本口径（`CITATION.cff` 的 `version` ↔ tag `v1.0.0-paper`）、以及双盲策略。
这些项目前均为 PENDING；在闭合之前仓库保持 **private**。
