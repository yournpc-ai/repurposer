# Agent Working Loop——剩余验收

> Status: 现行路径待验收（2026-11-16）。用户流程见 [Chat 架构](../CHAT_ARCHITECTURE.md)，覆盖与运行条件见 [验收规范](../VERIFICATION.md)。

- **读取与过程**：模糊目标和附带素材进入现行理解路径，长程序经 `get_node` 读取，定向指令使用 `specific_instruction`。检查可访问的 pending-plan 和 run-history 读面。真实 SSE 核查工具活动及 WorkSegment 的顺序和回放，raw payload、reasoning/think 不得进入用户流。
- **授权与完成**：修改当前制作范围时刷新同一确认座的报价；覆盖延续、扩展和无法证明的范围，以及 auto/ask、无制作意图与费用守卫线。复验 delivered/partial/failed 的事实收尾，失败不伪造卡片、支出或产物。
- **修订、候选和上下文**：用真实长媒体验证目标指认、边界、失效候选和 replay。现行候选读面若可达，覆盖时间、摘要、发言人事实、重选替换、失败回滚与刷新。复验至少 60 秒、两个主题的 CJK 来源，覆盖单字分词后的 `search_cues` 检索与 excerpt。历史摘要必须有界，exemplar 只提供参考，偏好写入需明确授权。
- **手动 Graph**：现行 Chat 工具 `edit_graph` 调用 `edit_manual_graph`，只编辑基础手动节点和边。验证 plan/propose 两路同样处理权限、错误和刷新，不产生制作 Run 或版本。保留对仍可达路径的覆盖。
- **迁移**：用含旧数据的目标 DB 副本验证退役 migration，核对保留的共享素材、用户消息、作品和账本，及备份/回退条件。旧探索表没有现行编译或回放任务。

使用当前注册旅程、核心 API/DB 与相关 Web 检查。真实模型、worker 与费用按验收规范执行。
