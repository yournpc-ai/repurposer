# 产品架构与可靠性方向

Repurposer 让用户通过自然语言与 AI 剪辑师合作。Project 提供素材和会话上下文，Composition 保存作品，CompositionVersion 固定每次编辑结果。时间线、轨道、片段、对象及动画承载专业编辑能力。后续剪辑扩展与已验收能力分别登记在[产品合同](tasks/new-agent.md)。

Agent 自主选择下一项工具，服务端检查参数、权限、版本和授权。工具返回可复核的来源、版本、预览或成片。重型计算交给各业务 Worker。可见结果、费用结算与失败恢复都指回实际操作的持久身份。详见[执行架构](AGENT_ARCHITECTURE.md)及[恢复与费用验收](tasks/agent-editor-evidence/iteration-6/6d.md)。

Renderer 消费版本编译出的 video-spec。媒体复用依赖固定来源与摘要。发布到外部账号另有 Publication 及渠道权限。支付、分发、许可证、隐私部署与后续产品计划见[进度与开放事项](PROGRESS.md)。视频结构的专业目标见[作品领域合同](VIDEO_PROJECT.md)。
