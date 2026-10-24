# 素材理解与对话面——当前合同（ADR-102/113）

> Status: 代码层已落，prompt_gate、当前矩阵与 live 验收未完成。本文合并回合内读取前提和对话面剩余规则；长期行为以 ADR-102/113 与 CHAT_ARCHITECTURE 为准。

## 1. 当前行为

- **上传是休眠纯存储**：上传、寒暄、能力问答和围观不创建 worker 事件。只有 `get_understanding` 的真实读意图，以及 run-birth 的生产兜底，才写 `processing_requested_at`。
- **能力决定读取方式**：provider 的 `understands_video_audio` 决定能否直接读视频字节；M3 为 false，走文本理解，不把视频字节塞进 context。
- **工具内等终态**：未就绪时盖章、打开真实 read activity，并使用独立短事务等待 ready/failed；全部失败可提前结束。没有超时常数、轮询 cap 或第二 writer；同回合由一个 writer 给出 grounded answer 或诚实失败。
- **后续读取**：digest 命中后零等待；没有 understanding relay/review trigger，也没有“我看了”式主动开口。机制判断在代码，prompt 只承载内容与工具引导。
- **消息与回放**：DB messages 是唯一存档/回放源。不得另设 pinned prompt bubble、`openingAssets` 或 content-equality skip predicate；`prompt` prop 可保留非渲染逻辑，但不能成为第二渲染源。
- **读取 beat**：项目会话有 in-flight user turn 时抑制 `_record_reading_beat`，避免重复叙事；直接 SQL 保持 pipeline ↛ chat。没有 in-flight turn 的合法 run-birth 路径仍可记录自己的 beat。
- **没有独立转写节点/卡**：transcript 是资产内容，不是 graph node。真实处理状态显示在资产卡上；不得在 read path 或 plan path 另造 transcript card。

## 2. 当前风险与延期边界

- worker 停摆时读取可能无限等待；这是当前已知风险，不得擅自用重新引入 cap 的方式“修复”。如需超时、取消或降级语义，必须先形成新的产品决策。
- ASR GPU / 云加速是独立运营评估，不属于本验收。
- 对话阶段理解是语义级、无时间码；生产链的本地 ASR 词级时间戳仍是精确编辑真值。只有引入合格云 ASR 时才重评双用时间戳。

## 3. 验收

自动检查按当前仪式链执行：prompt_gate、当前注册矩阵（尤其素材与咨询旅程）、相关纯测试和 web 检查；不恢复已删除的 material-wait 事故套件。

live 至少覆盖：

1. 寒暄/能力问答：零 worker 事件、零素材处理。
2. 视频提问：出现真实 read-active，等待实际 ASR 时长，随后同回合给出 grounded answer 或诚实失败。
3. 同素材追问：digest 命中，零等待。
4. 硬刷新：每条 opening/user message 恰好出现一次，无重复、无丢失。
5. 无素材问题的上传：不产生处理活动或虚假叙事。
6. 素材读取回合：只有一个 read Activity 生命周期；同回合回答有依据，不按资产逐条重复讲述。
7. `ask_user`：无可见/散文式 default-path 宣告，不复读内部法条。
8. in-flight beat 被抑制时，合法 run-birth beat 仍能出现。
9. read/plan 两条路径都没有独立转写节点或卡；资产卡只反映真实处理状态。

验证完成后更新 PROGRESS；未运行项不得写成通过。
