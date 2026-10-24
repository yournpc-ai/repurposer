# 选项唯一座位——剩余合同（ADR-100）

> Status: answer 路径的 suggestions 已在代码层移除；文档收窄、全量验证和 live 验收仍开放。现行交互归 ADR-081/099/100/116 与 CHAT_ARCHITECTURE；本文不保留 O1/O2 施工记录。

## 1. 当前契约

- 消息流内零可点击选项；`answer` 只提供信息。浏览、探索与下一方向的问题使用 `ask_user` OptionDock。
- decision asks 最多 3 个选项，exploration asks 最多 5 个；结构外层只接受 1–5。选项 ID 遵守 ADR-081 的数字语法，字母 ID 不是合法替代。
- trigger 建议 dock 的机器保留：wrap_up 校验、建议 stamp、answer endpoint 的 ref 重构、解算与 stale note。
- 历史 suggestion/ref 列保留，不清洗、不迁移。历史 answer 行只显示散文，不渲染建议卡且不得崩溃。
- `run_completed` 不得被当作建议来源；live trigger 回归应选择当前仍会产生建议的事件，如 `run_failed` 或 `craft_decompiled`。
- 已删除的 material-understanding trigger 不得重新引入；不恢复 suggestions→mentions。

## 2. 剩余文档与实现对账

1. ADR-099 只保留三种现行终态形态与 trigger-only provenance，删除 answer+suggestions 退役正文；保留四层架构、交互宪法、Speech Commit Protocol 与默认吸收边界。
2. NAMING 的终态形态、`suggestion_ref` / `source_state` 收窄到 trigger 链；CHAT 与 PROGRESS 删除 answer-path 建议表述。
3. prompt_gate probe I 以 browse→ask_user 为目标，先取得读数再校准；不得为放行回归调阈。
4. **已知法/实现差异**：`chat_intent_system.j2` 仍出现小写字母选项 ID 指令，而 `check_options_dock` 未断言数字语法。需按 ADR-081 修正实现与覆盖；本轮文档整理未改产品代码。
5. 建议/ask_user 发射率需要固定模型、参数与场景的基线，区分模型未提、未调用和应用丢弃；不得靠放松剧本吸收方差。

## 3. 验收

自动检查：当前纯 pytest（含 `test_suggestion_provenance_pure.py`）、prompt_gate、当前注册旅程矩阵、web tsc/build。另补或明确归属以下覆盖：

- trigger 点击 → 下一回合编译；
- stale trigger → 具名 stale reason；
- 数字选项 ID 语法与 1–5 结构外界；
- 历史 answer replay 安全。

live 至少覆盖：

1. 浏览问题产生可用 dock，含推荐、×/pencil 退出与合法 default path。
2. 能力问答/闲聊只产生纯 answer，无卡片。
3. 当前有效的 suggestion-producing trigger 仍能 dock、点选和解算。
4. 历史 answer 行刷新后只读散文，无建议卡、无崩溃。

全部验收完成且文档收窄后删除本合同，不留归档或跳转页。
