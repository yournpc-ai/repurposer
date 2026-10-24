# 首发推荐分维度——剩余合同

> Status: 保真检查、锚点转写、确定性 verify、响度与数量意图等已有实现；当前未闭环范围是**评分维度明细及其展示**。本文不再保留旧实施清单，完整质量架构归 AGENT_ARCHITECTURE 与现行代码/ADR。

## 1. 已批准需求

首发推荐分必须可解释、可证伪，不只保存 `{value, reason}`：

- 四轴：`completeness` / `opening` / `representativeness` / `delivery`，各 1–100。
- 计划/schema 增加可选 `score_axes`；产物保存 `score={value, reason, axes}`，旧行没有 axes 时只显示总分，不崩溃。
- 生成 prompt 要求 overall、四轴与一句 reason；reason 点名真实驱动轴，不预测播放量或 reach。
- Clip 详情显示四轴及 i18n 名称；卡片现有总分徽章不必重复堆四条。

## 2. 实施前必须对账

- 当前 reviser 仍会 re-score。必须明确修订后的 overall 与 axes 是同一版本一起重算，还是有依据地继承；不得让 overall 来自新版、axes 来自旧版，也不得为补字段让模型凭空编分。
- 评分仍是推荐参考，不是内容质量真值，也不替代确定性 verify 或人工看片。
- 维度进入 plan/score/schema、prompt、DB 读面和 UI 时保持同一命名；不需要新表。

## 3. 验收

1. 新 clips 的 score 同时含 overall、reason 与四个合法范围内 axes；旧行无 axes 正常显示。
2. 详情弹窗四轴与总体评价来自同一产物版本；深浅主题、en/zh 均完整。
3. 修订后核对 overall/axes/reason 的版本一致性，不出现混合快照。
4. 构造不同内容证据，检查 reason 能指向对应驱动轴；不断言固定 LLM 分值或文案。
5. 当前相关纯测试、prompt_gate 与受影响旅程通过；全片质检、LLM judge、modifier 质检不随本项自动扩 scope。

## Prohibited Behaviors

- 禁把分数写成客观质量或传播效果承诺。
- 禁用总分反推四个假维度；禁让旧行迁移时编造 axes。
- 禁把 verify 改为 LLM judge，或让评分替代文件/保真/交付检查。
