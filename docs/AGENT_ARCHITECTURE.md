# Agent Editor 执行架构

用户的当前要求保存在项目会话的 opening 消息。Agent 通过原生工具读取素材与作品、修改时间线、查看预览、生成素材及交付。实际注册与调度见 `app/chat/turn_tools.py`、`app/chat/editor.py`、`app/chat/plan_turn.py` 与 `app/agents/tool_loop.py`。

| 操作 | 写入或读取 | 恢复身份 |
| --- | --- | --- |
| 即时剪辑 | apply_composition_edits 校验 head 和 digest，保存新的 CompositionVersion | 原生调用、版本、结果回执 |
| 预览 | preview_range 读取指定版本和窗口的真实帧及混音分析 | 版本、范围、预览摘要 |
| 图片、旁白、音乐 | MediaJob 复用媒体领域实现，固定 SourceSnapshot，结算已有钱包 | 项目、opening、call、Job、claim_token |
| 正式导出 | ExportJob 锁定版本，Renderer 上传后核对 MP4，提交 Output、资金和回执 | 版本、Job、对象 key、实际字节摘要 |
| 审阅、交付 | review_video 读取实际 Output，deliver_video 核对已审阅身份 | 持久消息、版本和 Output 引用 |

费用批准、Stop、租约与原 opening 的续行仲裁由服务端执行。后台 Worker 分别认领素材、旁白对齐、MediaJob、ExportJob、社交发布及支付告警，并清理暂存对象。Publication 记录外部发帖是否已提交；无法核实的结果需要保留凭据。

模型边界位于 `app/providers/llm`。工具的原生名称、参数 Schema、项目事实与消息回放在模型请求时装配。可复核的实测样本见[原生模型请求](tasks/agent-editor-evidence/iteration-6/6d-native-journey.json)。编辑器产品合同、专业剪辑扩展与阶段验收见[主合同](tasks/new-agent.md)。
