# Home 示例与 Chat 首发

Home 提供叠图、构图和裁剪三个普通剪辑示例。点击只预填可编辑文字，保留已有的显式 Skill 选择。草稿为空或仍是上次的预填原文时可替换；已有用户文字或 @ 引用时追加。Landing 带来的提示词与显式 Skill 可在登录后回填同一 Composer，用户点击发送才创建项目并提交附件。[Home 实现](../apps/web/src/routes/_app.home.tsx)

新 opening 只凭用户提交的 `request.skill` 绑定经权限核验的方法版本。示例不指定用户未要求的渠道、配音或画幅。工具活动、费用授权、预览与交付沿用项目 Chat。[创作合同](tasks/new-agent.md) · [费用与授权](BILLING.md)

## 示例素材与未完成要求

- 历史 demo 媒体使用内容寻址的公开对象。保留原 key、真实画幅、离屏暂停和声音互斥；匿名展示只用已获公开许可的素材。公开 Gallery 或 remix 仍需核实项目权限、来源血缘与再制作许可。旧样片的实测、失败与待验范围见[入口验收记录](tasks/home-creation-entry-refresh.md)和[视频样片合同](tasks/skill-package-promo-video.md)。
- 素材的词级时间、话轮与说话者位置来自实际分析，位置记录不识别人脸身份。长素材 CJK 检索、取景缓存、并发、报价精度与动态视听仍需对应证据。
- 历史 Persona 的皮肤与声纹归原资料维护。系统音色目录、多语言试听、语速、发音与术语控制仍属待验或延期能力。指定原声配音时须核实可用且获准的声纹；换用 stock 须由用户选择。保留合成披露、来源与计量要求。旧合成发言提案留有独有边界，尚无本轮施工排期。[声音合同](MUSIC_ARCHITECTURE.md) · [R5 提案](tasks/synthetic-talk-video.md)
- 外部音效只在用户请求与权限允许时检索，候选展示可播放来源与许可，实际导入复核许可和字节。音效使用作品内普通 Audio Clip。用户的选用、授权、试听及最终导出各留对应回执。[声音来源与落轨](MUSIC_ARCHITECTURE.md)
