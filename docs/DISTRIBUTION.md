# 渠道账号与历史发布

适用于仍持有渠道授权、Publication 或已发布 Output 的账户。新作品在 Chat 中通过 Native Tools 编辑，按指定 CompositionVersion 预览和交付。渠道发布是独立的存量业务，发布状态不决定编辑进度或交付是否完成。

| 消费者 | 维护边界 |
|---|---|
| 渠道设置与 OAuth 回调 | `/channels` 路由维护账户授权、可用平台和解绑。保留 owner 检查、令牌保护及失效处理。[路由](../apps/api/app/distribution/routes.py) · [授权](../apps/api/app/distribution/channels.py) |
| Publication API | 创建、列出、查看、取消或重试用户的发布单。保留原 Output、账户归属、幂等键和状态迁移。[发布服务](../apps/api/app/distribution/core.py) |
| Worker、通知与历史深链 | 已经排队或处于不确定状态的发布仍需要认领、超时处理和远端核对。清理 UI 前应沿真实调用盘点存量任务、引用和 FK。不得因撤下入口删除用户数据。[认领与对账](../apps/api/app/distribution/publishing.py) |

默认 Output 的发布入口已撤下。旧平台扩张、审核 UI、数据回流及多渠道工作台的设计仅用于解释存量表和既有客户记录。第三方平台联调仍以实际凭据和回执验收。[I8 已处置项](tasks/i8.md) · [完整历史设计](https://github.com/yournpc-ai/repurposer/blob/b01823d614ddff4972e26fc1a56987f5f5f30336/docs/DISTRIBUTION.md)
