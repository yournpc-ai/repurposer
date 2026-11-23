# 模块职责与执行边界

## 项目中的一次创作

Studio 经项目会话向 Agent 提交用户意图。Agent 通过原生 Tool Call 调用即时编辑、读取、预览与领域 Job。来源、版本、媒体和成片均有自己的持久身份。Chat 从执行回执继续决策。开发与部署须核对数据库目标后显式运行 Alembic；API 和 Worker 启动时读取 revision。

| 模块 | 持有的数据与职责 | 主要代码 |
| --- | --- | --- |
| 项目与对话 | Project、Conversation、Message；用户约束、opening、原生调用、费用问题、Stop、回放与续行 | app/chat、app/platform/project_context.py |
| 创作与观察 | 唯一版本写口、CAS、不可变 CompositionVersion、SourceSnapshot、来源权限与 digest；固定窗口预览和审片 | app/editing、app/chat/editor.py、app/tools/video |
| 模型 | 统一 ToolLoop 与 Provider 请求，按调用身份记录参数和结果 | app/agents/tool_loop.py、app/providers/llm |
| 媒体生成 | MediaJob 的报价、预占、领取、原音或图片固定及结算；旁白占位与 Unknown 防重发由 narration_store 管理 | app/pipeline/media_jobs.py、app/tools/video/narration_store.py |
| 正式导出 | ExportJob 固定已观察的版本；使用 Renderer 的条件 PUT，核对结果后提交 Output、费用和原回执 | app/pipeline/export_jobs.py、app/pipeline/rendering.py |
| 渲染 | 预览和正式输出共享编译语义；渲染器消费固定的 video-spec | app/editing/video_spec.py、packages/video-spec、packages/video-remotion、apps/render |
| 独立后台业务 | 上传素材处理、旁白对齐、社交发布、发布异常邮件、支付告警及 staging 清理 | app/worker.py、app/pipeline、app/distribution、app/platform |
| 资金与账户 | 账户、LoginSession、用户设置、权限、配置、Wallet 与 CreditTransaction；钱包写入使用原生 Job 幂等键 | app/platform/billing.py、app/platform/routes.py |
| Skill 与创作参考 | 固定版本和权限、受控的创作资料和候选；结果进入普通素材、作品或消息 | app/skills、app/tools/video |
| Studio | 按持久消息和领域 ID 呈现工具、授权、历史作品和成片 | apps/web/src/components/chat |

## 执行权与事务

Worker 分别领取 Asset、NarrationAlignment、MediaJob、ExportJob、Publication、PaymentAlert 和 Notification 的待发邮件，并定期清理 staging。各领域保留自己的认领条件与并发上限。行锁、数据库时钟、lease、claim_token 以及提交时的 fencing 共同约束同时执行和晚到回执。可恢复的失败使用有界重试，供应商结果未知时保留核对凭证与必要预占。公开发布已经进入平台写入边界时，只有核实结果才能继续处理原发布单。

费用预占与 Job 入队同一事务提交。成功后的实际扣款与释放由同一账本处理。Stop 与成功争用原 Job；项目删除与付费入队争用原 Project。删除前校验后台任务、外部结果与账本。项目返回 409 时应保留素材、消息、账本及对象存储。

各业务的详细合同见 [Chat](CHAT_ARCHITECTURE.md)、[作品](VIDEO_PROJECT.md)、[渲染](RENDERING.md)、[费用](BILLING.md)、[发布](DISTRIBUTION.md) 和 [支付](PAYMENTS.md)。排期及未来能力见 [PROGRESS](PROGRESS.md)。
