# Composition 创作循环与上下文收敛

> Status: 当前合同（2026-11-16）。高层首稿、续轮、定向编辑及代表交付已验证。顺序审片与包资源见 [顺序创作](sequential-video-authoring.md)，发布与完整验收见 [统一视频合同](skill-package-promo-video.md)。

## 1. 工作草稿、候选与保存

- `design_video` 在现有 ConversationContext 上写入或续接服务端工作草稿，保持稳定身份、digest、已固定来源与有效回执。首稿可按幕推进或直接保存完整、合法的分镜；最终版本由 `apply_composition_edits` 保存。保存版以 `revise_video` 和当前 `base_ref` 定向编辑。服务端绑定来源、作品、时间窗与明确用户答案，并展开内部实体及操作。
- 有效草稿遇到局部错误时保留，只修受影响实体。非法来源、越权、过期版本、无进展和耗尽各自诚实收尾。禁止回放整份被拒参数或恢复旧 Promo 专用协议。只有真实保存观察允许报告已落版。
- 根据真实目标和素材决定是否询问。歧义复用 `ask_user`，询问前零内容写入、零 Run；候选回答必须重校验，问题在工具接受后结算。相同包版本与 digest 才复用读取回执，SSE 与非流式保存统一。
- 项目证据按需注入来源 ID、citable lines 与有界代表帧；完整动态证据只在实际审片时读取。历史媒体折叠为紧凑事实，保留可回读引用。重复的网页正文、素材与快照摘要应去重。

## 2. 每步局部校验，最后完整校验

| 时点 | 校验范围 |
|---|---|
| 每次实体写入 | 本次参数 JSON/schema、完整实体自身、稳定 id 冲突、owner/权限、已引用来源身份，以及不依赖未来实体即可判断的局部时间/几何规则 |
| 草稿合并 | 容器形态、重复 id、同批写删冲突、完整 Track/Clip 所有权与原子移动 |
| `save=true` | 完整 CompositionContent、跨 Scene/Track/Clip 关系、全局时长/容量、来源闭包、呈现与最终渲染约束 |
| produce_video | 既有呈现、首稿审阅、制作意图、报价/守卫线、钉版与执行 manifest |

可确定修复的空值/序列化方言在 schema 边界规范化，不让模型重写整片。例如 `props={}` 配合 `{}`、null、空字符串或仅含空 `type/properties` 的 `props_schema`，统一为封闭的零参数 schema；非空 props、未知字段、类型冲突和越权来源仍拒绝。不要把所有校验删掉，也不要把用户明确约束、权限、安全、计费或最终可渲染性延后到制作后才检查。

## 3. 每轮工具投影

复用 ToolLoop 已有的每轮 `round_tools` 接缝，在上下文刷新和活动草稿恢复后计算模型可见工具。执行端仍独立校验工具状态与权限；不可见不是安全控制。

**一法一座，禁止四个座位复述同一恢复协议**：

- 参数语义只由 `CompositionDesignVideoArgs` / `EntityWrites` 生成的 wire schema 表达；`turn_tools.py` 只投影 schema 与短描述，不手写第二份字段法律。
- `working_drafts.py` 只负责合并、身份、digest 与错误事实；工具观察不附“下一步重写什么”的教学文案。
- `tool_loop.py` 只调用条件投影并执行真实工具，不携带 fresh/revise 恢复说明。
- prompt 只讲逐步创作、保持未改范围、查看真实结果与明确制作；不复述字段约束或修复流程。

| 当前真实条件 | 模型侧必要能力 |
|---|---|
| 无活动草稿，正在理解/准备 | 必要读取、Skill/素材准备、提问/回答、首稿 `design_video` |
| 有活动草稿 | 当前 `draft_ref` 的继续写入/保存，必要读取与准备；不投另一份无目标首稿 schema |
| 已有保存版本，无活动草稿 | 精确版本读取、局部 `revise_video`；用户要求开放重稿时才由 `design_video` 建立草稿 |
| 活动草稿与保存版本并存 | 保留 `draft_ref` 续写/保存，同时保留基于保存版的 `revise_video`；草稿不得遮蔽已保存版本的局部修订写口 |

首版只看绑定 Skill、活动草稿和当前版本三类已有事实，不创建 `PREPARING/AUTHORING/REVIEWING` 持久阶段字段，也不从用户措辞再造条件矩阵。活动视频草稿及绑定视频 Skill 的未存版创作轮不投执行计划工具，内容直接经 `design_video` 写入；无活动草稿且已有保存版本时制作计划工具恢复。通用 answer/ask、review、交付、取消、Stop、context 补读和非视频工具继续按现有规则工作；工具可见性本身永不授权制作。

## 4. 分镜与局部 Scrub

工作草稿完整校验并保存后，默认呈现 canonical Storyboard、修改摘要与必要静态代表帧，不按内容是否含 Animation/Transition/Generator 自动附预览。只有动态需求需要比较或澄清、用户修改后需要核对本次局部结果，或用户明确要求看特定效果时，才可选附一个 Scrub：要么是有明确 Scene/Clip id 与时间窗的片段，要么是独立 Object。通用效果示例走既有 Preset 候选；制作前完整成片动态预览永不提供，即使用户主动要求也不例外。

Scrub 复用精确版本 PreviewAdapter 与 `slice_clip` 的媒体源/动画裁剪语义，钉 `composition_version_id + content_digest + target`，只向浏览器发送归一化局部 spec。独立 Object 不证明场景布局、遮挡与衔接；纯文案等静态修改不提供 Scrub。只有显式目标的本地 draw-2d/remotion-project 可按既有隔离 runner、资源上限和 digest 缓存准备，默认首稿不预烘焙；模型生成图片、Speech 等付费或 pending 媒体不伪装 ready。预览不是 Output，不启动正式 Run。局部修订产生新版本后旧目标失效，只能展示新版本本次声明的局部目标。用户明确制作后才由 produce_video 固定版本并进入既有生成/烘焙/渲染/检查/交付链。

首稿完整呈现、review hold、打字机、Activity、Stop、取消、刷新和消息自有 output_refs 保持现行 Chat 法律。本切片不改这些共享机器。

## 5. 验收

- 当前注册的首稿、续轮、修订、overlay、外置资源和短确认交付旅程分别检查真实保存、结构化问题结算、局部版本差异与同版本制作。旧版本刷新保持原引用。
- 复验多来源首稿、长视频代表帧与连续证据、复杂或歧义编辑、错误恢复与同题不同简报的稳定性。验证 stale base、越权来源、取消、工具预算耗尽和 SSE 诚实收尾。
- 最小文字 Inspector 通过当前版本的明确 Text Clip 调整字号，本地 Scrub 不写库，Apply 才经完整 Clip 及 base_ref 落新版。保留键盘、取消、失败回滚与 409 检查。完整验收归统一视频合同 P10。
