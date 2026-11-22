# Chat 中的素材与作品指认

用户在 Home 或项目 Chat 通过同一个 MentionEditor 点名项目内的素材或既有 Output。用户给出目标，原生编辑轮检查实际素材和作品。显示名可重复，所选实体由持久 ID 区分。

| 输入 | 含义和边界 |
|---|---|
| `asset` | 素材引用随原消息保存。服务端核对可访问范围，Agent 按需检查、准备固定来源，再决定编辑动作。普通上传附件也有各自的 Asset ID 和消息内顺序。 |
| `output` | 指认既有交付。引用可带选区或已有引文；Output 及其版本仍须可访问。 |
| Skill | 通过独立的斜杠选择器进入同一 Chat 请求，提供创作方法。 |
| 历史类型 | 保留旧消息的可读性。`workflow_step` 的注册项不给 picker 提供候选；不据此恢复 Canvas 或 Plan 路由。历史 `focus_output` 只读。 |

可见 chip 与发送载荷一致。删除 chip 应一并移除它的结构化引用。项目内候选不能混入其他项目的私有资料。实际类型、选项及服务端作用以源码和原请求核对。[前端注册表](../apps/web/src/lib/mentions.ts) · [Chat 合同](CHAT_ARCHITECTURE.md) · [Agent 总合同](tasks/new-agent.md)

- **画面局部选择（`region` 是 output mention 的字段，不是新类型）**：Output 查看器的「局部选择」暂停当前帧，框选时以 mask 暗化选区外画面、显示选区框/角点与实时源像素尺寸；选择事实同时保存源视频像素尺寸与整数区域、0～1 归一化区域、框选时 CSS 像素区域和毫秒级 `mediaTimeMs`，坐标空间明示为 `source_pixels`。「引用选区」在 dock 形成带时间与宽高的 @output chip；本次消息正文包含用户框选的 x/y/宽/高/源尺寸/媒体时间，结构化 `region` 随 `mentions` 持久化并由服务端上下文确定性注入。region 只寄存在对应 chip，文本删除 chip 即同步删除正文摘要与全部结构化选区记录；替换为同 Output 的整片引用也移除旧 region。「引用此素材」始终钉整个 Output，不暗用局部选区。region 是用户指认事实，不是像素编辑能力证明；工具不支持局部修改时必须诚实说明，手势永不直接改产物。
