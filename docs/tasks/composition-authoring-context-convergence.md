# Composition 创作循环与上下文收敛

> Status: 当前施工合同（2026-11-12）。P0 入口/初始上下文与 P1 高层创作协议已落码并有局部真实证据，但续轮状态、真实媒体和注册旅程未闭环，P1 不得关闭。长期法归 VIDEO_PROJECT §0/§2.2/§8，用户主流程归 PRD §6.4/§9，其余视频能力与视听欠账归 skill-package-promo-video。本文不再把一次性完整 Composition 或 `fresh_design` 当作目标。

> 下一批创作循环按 [P2 当前接线顺序与代码验收](sequential-video-authoring.md#64-当前接线顺序与代码验收) 推进首稿顺序审片和保存后定向编辑的统一装配。本合同保留 P1 的实现与开放验收，现有封闭 Promo 协议作为对照。

## 0. 目标与边界

让 Agent 像人使用剪辑工具一样，在同一个普通 Chat 工具循环中逐步建立作品、查看真实结果并局部修复。优先恢复“能稳定形成首稿 → 能看到 → 能局部改”的主链，不继续为一次性整片输出增加提示词、重试和防护分支。

保留 Composition / CompositionVersion、SourceSnapshot、SkillVersion、Track/Clip/Object/Animation、`apply_composition_edits`、Run/Output、权限、授权、计费、固定制作与视听验收。创作增量化只改变模型写入方式，不改变作品本体和生产边界。

不做：第二意图端点、第二作品根/内容写口/生产链、Draft/AuthoringSession 新表、多 Director 阶段链、模型构造 Op 程序、字段 patch 语言、无界 Bash/HTML/JS、通用插件平台、完整 NLE 或新的质量平台。现有 dirty tree 不 reset/checkout/stash。

### 当前阻塞事实

Project `42eadd7c-3cf5-4e90-a423-2d682d18f5ff` 的网页素材处理成功，但 Chat 在 12 次迭代后耗尽：素材准备 1 次、Skill/音乐/字幕读取 6 次、成功 `design_video(save=false)` 3 次、参数校验失败 2 次，没有 `save=true`。数据库没有 Composition、Run 或 Output；活动工作草稿仍保留 3 个 Scene、2 个 Track、22 个 Clip，不能表述为创作内容全部丢失。

第一次参数错误包含无法确定归属的根级 `item` 动画；第二次把裸 Clip 放进 `clips`，缺少 `{track_id, clip}` wrapper，并带有根级 `track_id` 和 `item`。严格校验必须继续拒绝，不得丢弃动画、猜目标 Clip 或放宽 `extra="forbid"` 来伪造成功。读取、增量写入和恢复共享同一预算，已有批量读取指引仍未避免顺序调用；参数稳定性与为最终保存保留预算仍未关闭，不能只提高 12 次上限。

该回合最终消息曾把成功草稿观察的 `ok=True, saved=false` 误报为“作品版本已保存”。当前修复让 `LoopResult.version_saved` 只由非草稿更新的成功 `design_video` / `revise_video` 观察置位，plan/propose 共用的耗尽收尾只读这一事实；核心 DB 回归覆盖“草稿成功、保存失败、耗尽”与正式保存对照，相关定向回归已通过。该事实修复不等于新创作主链已稳定，续轮状态与真实旅程仍须验收。

## 1. 当前架构：保留什么，缺什么

| 能力 | 当前事实 | 处置 |
|---|---|---|
| Composition / CompositionVersion | 持续作品身份与不可变版本已存在；最终内容只经 `apply_composition_edits` | **保留**，不重写本体 |
| 完整实体合并 | `EntityWrites` 与 `apply_entity_writes_raw` 已能在原始工作 JSON 上按 Scene/Track/Clip/Transition 合并 | **保留自由创作与高级修订**，不再投给内置 promo |
| 跨调用/跨回合状态 | ConversationContext 已保存实际工具交换、候选/草稿、媒体、digest、生命周期和恢复 | **复用**，成功草稿也走这里；不建表 |
| 素材与 Skill | PackageReader、渐进读取、CapturePlan、固定 SourceSnapshot 与成功资源独立提交已存在 | **保留**，减少无关注入，不改资源身份 |
| 固定 Skill / 源对齐 / Generator | 确定性模板实例化与若干有界 Director/代码生产路径仍有消费者 | **保留真实消费者**；固定模板填槽，Generator 只在目标 Clip 内创作，不整目录删除 |
| 首稿协议 | 内置 promo 的 `design_video` 只接收封闭 shot-specific union；自由创作仍接收完整实体 | **已落码，待真实旅程**；底层 Track/Clip/Animation/Keyframe 不再进入 promo wire |
| 修订协议 | 内置 promo 的 `revise_video` 只接收五个封闭 action；服务端展开现有 Op 并保存 | **已落码，待真实旅程**；其他高级完整实体修订保留 |
| 工具投影 | plan/propose 每轮在上下文刷新与草稿恢复后调用同一 `video_round_tool_projection`，按活动草稿和当前版本投影工具 | **已落码，待验证**；执行端权限与状态校验仍独立 |
| 预览反馈 | 精确版本 PreviewAdapter、Generator digest 媒体/代表帧和 Output review 已存在 | **复用局部 Scrub**，不新造 look 系统 |
| 制作与交付 | produce_video 钉版本、execution_digest、队列、计费、Output 与 review 已存在 | **保留**；预览不是 Output，普通修订不自动制作 |

已有代码和单次真实交付不等于主链稳定。完整测试、真实视听、runner 环境、Remotion 许可、P9、完整 Inspector 与其他样片欠账继续归母合同，不因本切片改写而关闭。

## 2. 最小目标合同

### 2.1 一个创作入口，一个最终保存写口

保留现有公开工具名，不新增 `create_draft` / `update_draft` / `commit_draft` 工具族：

```text
自由创作：
design_video(draft_ref?, composition_id?, settings?/sources?/完整实体, save=false)
design_video(draft_ref, save=true)

内置 promo：
design_video(arc_id, shots, save=false|true, draft_ref?, composition_id?, 创作槽位)
revise_video(base_ref, action, scrub?)
```

- 自由创作每次只提交本次完整设置、来源绑定或完整实体。Object/Animation/Keyframe 随完整 Clip；完整 Track 携带完整 Clips；稳定 id 决定新增/更新，删除使用既有 remove 列表。`save=true` 只提交既有 `draft_ref`。
- 内置 promo 每次提交完整高层设计；`shots + save=true` 可一次落版，`save=false` 保留高层工作草稿，后续可只带 `draft_ref + save=true`。三个已接 shot 是 `brand-emergence`、`evidence-push`、`next-step-lockup`，各有独立模型、展开函数、包声明映射和核心合同测试。
- promo 修订只有 `set_text`、`set_clip_duration`、`apply_preset`、`add_media_overlay`、`remove_clip`。服务端校验 owner/source/target/base_ref，计算 Track/order、Layout、Animation 和 ticks，展开普通 Op，再经 `apply_composition_edits` 保存。自由路径高级完整实体修订不删除。
- 任何阶段目标、素材或时间窗不唯一时复用现有 `ask_user`；能由上下文、@mention、当前目标或唯一候选确定时不问。询问前零内容写入、零 Run，不新增 ask action。
- 最终校验失败保留当前有效草稿和高层输入；下一次只修报错范围。权限、stale ref、系统错误与无进展仍按真实类型结束，不伪装成内容修复。
- 不恢复模型 Op 数组、底层字段 patch、执行顺序或底层 error-id 修正矩阵。服务端 shot/action/Preset 展开、确定性规范化与受控 Generator 编程不属于这类模型协议。

### 2.2 每步局部校验，最后完整校验

| 时点 | 校验范围 |
|---|---|
| 每次实体写入 | 本次参数 JSON/schema、完整实体自身、稳定 id 冲突、owner/权限、已引用来源身份，以及不依赖未来实体即可判断的局部时间/几何规则 |
| 草稿合并 | 容器形态、重复 id、同批写删冲突、完整 Track/Clip 所有权与原子移动 |
| `save=true` | 完整 CompositionContent、跨 Scene/Track/Clip 关系、全局时长/容量、来源闭包、呈现与最终渲染约束 |
| produce_video | 既有呈现、首稿审阅、制作意图、报价/守卫线、钉版与执行 manifest |

可确定修复的空值/序列化方言在 schema 边界规范化，不让模型重写整片。例如 `props={}` 配合 `{}`、null、空字符串或仅含空 `type/properties` 的 `props_schema`，统一为封闭的零参数 schema；非空 props、未知字段、类型冲突和越权来源仍拒绝。不要把所有校验删掉，也不要把用户明确约束、权限、安全、计费或最终可渲染性延后到制作后才检查。

### 2.3 条件工具 = 每轮模型投影，不是新业务状态机

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

首版只看绑定 Skill、活动草稿和当前版本三类已有事实，不创建 `PREPARING/AUTHORING/REVIEWING` 持久阶段字段，也不从用户措辞再造条件矩阵。活动视频草稿及绑定视频 Skill 的未存版创作轮不投 `present_plan` / `propose_tasks`，内容直接经 `design_video` 写入；无活动草稿且已有保存版本时制作计划工具恢复。通用 answer/ask、review、交付、取消、Stop、context 补读和非视频工具继续按现有规则工作；工具可见性本身永不授权制作。

### 2.4 保存后默认看分镜，动态检查只做局部 Scrub

工作草稿完整校验并保存后，默认呈现 canonical Storyboard、修改摘要与必要静态代表帧，不按内容是否含 Animation/Transition/Generator 自动附预览。只有动态需求需要比较或澄清、用户修改后需要核对本次局部结果，或用户明确要求看特定效果时，才可选附一个 Scrub：要么是有明确 Scene/Clip id 与时间窗的片段，要么是独立 Object。通用效果示例走既有 Preset 候选；制作前完整成片动态预览永不提供，即使用户主动要求也不例外。

Scrub 复用精确版本 PreviewAdapter 与 `slice_clip` 的媒体源/动画裁剪语义，钉 `composition_version_id + content_digest + target`，只向浏览器发送归一化局部 spec。独立 Object 不证明场景布局、遮挡与衔接；纯文案等静态修改不提供 Scrub。只有显式目标的本地 draw-2d/remotion-project 可按既有隔离 runner、资源上限和 digest 缓存准备，默认首稿不预烘焙；模型生成图片、Speech 等付费或 pending 媒体不伪装 ready。预览不是 Output，不启动正式 Run。局部修订产生新版本后旧目标失效，只能展示新版本本次声明的局部目标。用户明确制作后才由 produce_video 固定版本并进入既有生成/烘焙/渲染/检查/交付链。

首稿完整呈现、review hold、打字机、Activity、Stop、取消、刷新和消息自有 output_refs 保持现行 Chat 法律。本切片不改这些共享机器。

## 3. 文件级 Keep / Change / Delete

### 3.1 直接复用，不另建层

| 文件 | 保留职责 |
|---|---|
| `apps/api/app/editing/store.py` / `service.py` | 唯一版本写口、owner/base/digest、并发/幂等、canonical read 与呈现事实 |
| `apps/api/app/editing/edits.py` | `EntityWrites` 与 `apply_entity_writes_raw`；补草稿所需 settings/sources 完整值合并，不新增 Op 语言 |
| `apps/api/app/chat/conversation_context.py` | 活动草稿、工具事实、媒体、恢复、预算、Stop/终态退役；成功草稿复用现有记录形态 |
| `apps/api/app/tools/video/preview.py` / `programs.py` / `components.py` | 精确版本预览、固定 Generator 媒体、代表帧与 digest 复用 |
| `apps/api/app/tools/video/production/`、`pipeline/`、`run_review.py` | 钉版制作、队列、计量、渲染、恢复、交付与审片 |
| `apps/api/app/editing/templates.py` 与仍有消费者的 Director | 固定 Skill 确定性实例化、源对齐与 Generator 有界代码创作；不按目录误删 |

### 3.2 修改现有座位

| 文件 | 最小修改 | 不再做什么 |
|---|---|---|
| `apps/api/app/tools/video/design.py` | `CompositionDesignVideoArgs` 只含草稿 writes + `save` + 真实用户约束/Skill provenance；当前草稿合并后经现有来源解算、完整校验和唯一写口保存 | 删除旧 Director 方向入口与独占 helpers；不要求 `composition`，不保留旧字段继承或首稿兼容分支 |
| `apps/api/app/agents/working_drafts.py` | 从“拒绝后诊断”扩展为正常草稿的创建、更新、digest 和最终提交诊断；继续调用 `apply_entity_writes_raw` | 删除 `fresh_design` 分支与只读候选语义，不新建 ORM |
| `apps/api/app/agents/tool_loop.py` | 在现有每轮 `round_tools` 处调用 caller 提供的条件投影；接受并恢复成功草稿；保留 call id 配对、批处理、预算与 Stop | 删除 fresh-design 参数替换和专用尾部反馈，不把草稿修改变成 correction-only |
| `apps/api/app/chat/turn_tools.py` | 从实际 args 投影当前草稿写入 schema；只按绑定 Skill、活动草稿和当前版本过滤工具 | 删除完整 CompositionContent wire 注入、手写字段法律和 fresh/revise 双族说明 |
| `apps/api/app/chat/plan_turn.py` / `propose_turn.py` | 两条入口传入同一个工具投影与现有 ConversationContext，保持 plan/propose 语义 | 不各复制一套草稿机或 Director 链 |
| `apps/api/app/chat/video_turn_seats.py` | 返回“草稿已更新”或“版本已保存”的真实 ToolObservation；仅显式 scrub 参数接局部预览事实；保留 owner/base/权限/授权 | 删除 `fresh_design_required → recovery=fresh_design` 映射、整片重交文案与保存后无条件完整预览 |
| `apps/api/app/chat/routes.py` | 复用现有 `GET /video/versions/{id}/storyboard`；默认无 preview DTO，只有显式合法 scrub target 才附同版局部预览 | 不按版本内容自动附整片 spec；pending/unavailable 仍诚实返回 |
| `apps/web/src/components/chat/video/StoryboardCard.tsx` | 默认分镜独立就绪并 ACK；仅 block 自带 scrub 时挂载局部 CompositionPreview；手动 Scrub 在 Popover 内按独立 Object 按需读取 | 不按内容类型自动挂 Player，不让按需手动预览阻塞普通 ACK |
| `apps/web/src/components/chat/video/preview/CompositionPreview.tsx` / `RemotionPreviewAdapter.tsx` | 复用现有精确版本播放、ready/error 与身份校验；只有实际缺口才改 | 不新增第二 Player、客户端作品镜像或付费生产入口 |
| `apps/api/app/editing/schemas.py` / `validators.py` | 局部实体校验与最终全校验分开；规范化语义相同的空 props schema；让实际 wire schema 表达约束 | 不通过放宽权限、来源、安全或最终渲染约束换成功率 |
| `apps/api/app/models/schemas.py` | 删除已无消费者的旧 `DesignVideoArgs`；视频草稿参数由 Composition 模型独立表达 | 不保留一份隐藏完整 composition 兼容载荷 |
| `apps/api/app/skills/loading.py` | 保留不可变 SkillVersion、渐进读取与 provenance | 删除只消费旧 Director 方向参数的 validate/instruction 接口 |
| `apps/api/app/prompts/chat/_video_project.j2` / `_promo_composition_authoring.j2` | 只描述逐步创作、保持未改范围、查看真实结果与明确制作 | 删除字段/恢复流程复述、fresh complete、整片重交和“所有局部修复都禁止”的过时法律 |
| `apps/api/app/prompts/_component_project_contract.j2` | 保留 Generator closed schema 与来源约束，供真实 coding 消费者使用 | 不把整份 Generator 合同塞进所有普通创作轮次 |

### 3.3 明确删除，而不是继续兼容

- 删除 `fresh_design_required`、`recovery="fresh_design"`、`rejected_candidate_ref` 及对应工具反馈/上下文投影。
- 删除 `CompositionDesignVideoArgs.composition` 的完整首稿必填合同、其整片 wire schema 注入和只为该合同服务的误嵌套 Track 修补。
- 删除“首稿 schema 错误不能形成可修改草稿”的测试与文档断言；替换为新用户旅程和唯一写口守卫，不保留注释尸体。
- 删除新路径接通后无消费者的旧 direct-candidate 分支与重复提示，不为旧协议增加 feature flag 或 fallback。
- **不删除**仍有消费者的 VideoTemplate、源对齐 NarrationAlignment、Generator coding Director、CapturePlan、非视频通用 candidate correction 或旧 Clip 编辑器。旧 Film 专用实现已随新链接线删除。

## 4. 施工顺序：当前主链

1. **封闭 Promo 输入与条件工具**：自由创作保留完整实体草稿；内置 promo 的高层 shots/actions 由服务端展开，最终一次校验与落版。
2. **局部 Scrub 反馈**：默认 Storyboard 零动态 spec；仅显式目标复用 PreviewAdapter 与 Generator digest 缓存，同版 storyboard DTO 携带局部预览；未变 Generator 不重新生产。
3. **最小 Scrub Input**：当前版本的一个文字 Clip 可调字号；本地草稿驱动同版预览，Apply 才经完整 Clip + base_ref 落新版。
4. **旧 Film 删除**：新链接线后删除旧工具、schema、prompt、pending、render 与启动残留，不保留双读/双写或 fallback。
5. **真实用户主旅程**：运行普通与 promo-video 的素材 → 首稿 → 预览 → 局部修订/Scrub → 明确制作 → Output；真实模型、付费生成与渲染只在明确授权的验收阶段执行。
6. 完整 P6+P7 的视觉/声音/许可/部署验收仍归母合同；P9 旧 Clip 承接与完整 Inspector 后置。

## 5. 验收矩阵

| 旅程/承重门 | 必须证明 |
|---|---|
| Promo 首稿 | 至少两次 fresh 官网运行保存版本并完整呈现；copy-only 一次 `shots + save=true` 可合法保存；零 Run/Output；wire 不含底层 Track/Clip/Animation/Keyframe |
| 局部参数/语义错误 | 已保存的有效草稿和成功素材保留；只修当前高层 error_ids 或有界 shots/action；没有 fresh_design、底层 Op 修正或完整被拒 Composition 回放 |
| builder 失败 | 合法高层输入展开出非法 Op/Composition 时零版本、有效草稿不被覆盖、进入诚实终态；以确定性核心测试脱离 LLM 重放，不让模型修底层字段 |
| 最终完整校验 | 缺失全局关系、非法来源、越界/容量问题仍失败闭；失败后草稿可继续修复，权限与授权不放宽 |
| 条件工具 | 各真实状态下只见当前必要工具；执行端拒绝伪造/过期 ref；answer/ask/Stop/context 不被误裁 |
| 预览与局部修订 | 默认无动态 spec；局部 Scrub 钉确切版本/content digest/target，拒绝整片窗口；只改目标范围，其他实体不变；未变 Generator 媒体复用，新版不沿用旧预览 |
| 首稿审阅与制作 | 完整分镜已呈现；若本次实际声明局部 Scrub，则该目标也就绪；下一轮用户明确制作才创建 Run，Run 钉同一版本，不重新设计 |
| 刷新/Stop/失败 | 草稿、工具事实与消息恢复一致；取消不留假版本/Run/Output；无进展和预算耗尽诚实收尾 |
| 既有能力 | 固定 Skill、源对齐、Generator、非视频候选修订和旧 Clip 当前消费者不回归 |

测试只使用 `test/core` 的核心 API/DB 合同与 `test/journeys/chat.py` 的真实用户旅程：Composition/版本/权限/预览归核心测试，工作草稿、多轮 Skill 创作、局部修订、授权与交付归真实旅程。不是另建事故编号套件，也不为旧 fresh-design 行为保留兼容锁。

实现完成后按 CLAUDE 运行 `test/core`、相关真实旅程和 Web 检查；真实旅程需要活 API + fresh dev worker 与可用配额，付费制作另行授权。文档更新、静态代码存在和单次保存均不冒充真实创作或视听通过。

## 6. 三批施工与新会话交接

### 6.1 P0：入口与初始上下文（限定范围已验证）

- Chat prompt 收敛为 `chat/system.j2` / `user.j2` 两个入口，plan/conversation/event/delivery 仍是现有四种路由，不合并运行时 Agent。
- direct promo 按真实状态投影规则和工具；典型 fresh website 首轮从 46,408 降至 18,284 provider prompt_tokens。
- 清理旧 Skill/Composition 协议；保留先言语后工具、授权、review hold、打字机、Stop 和诚实失败。
- Prompt 保持英文，不做翻译或中英双语。

### 6.2 P1：高层创作与精确执行（共用链已落码，P1 已关闭）

- 内置 Promo 首稿与保存版共用 `scene_plan / scene` 高层输入和五个封闭 revision action；旧 Promo 专用参数、模板、展开和分派已删除。
- 模型负责理解需求、选择目标与创作槽位；服务端绑定当前 `base_ref`，解算来源/目标与用户明确答案，生成 Op/实体，完整校验并经唯一写口保存。
- 不把底层 Op、完整 Composition 或无限语义字段袋交给模型；不为假设需求新增 action。
- 四秒视频、普通修订、overlay 询问/回答/删除、第三轮续接和两条外置资源旅程均已真实通过。`promo_short_confirmation_delivery` 已在项目 `11b96089-3e1b-41fd-b843-e601c3dff6bc` 完成真实 URL 首稿、ACK、OK 同版本制作、原 Chat 自动交付、重复 Yes 幂等和 1266 帧完整解码；最终为 1 个版本、1 个 Run、1 个视频 Output。完整 core 为 391 passed / 1 个既有 SFX 文案失败，逐阶段 ID 与用量见 [动态 Skill 切换与删除](sequential-video-authoring.md#631-动态-skill-切换与删除)。

### 6.3 P1 收口合同：状态与证据闭环（独立放行条件已闭合）

以下 P1 独立收口条件均已闭合。P2 的两轮验收只提供对应事实；最终付费交付由同一注册旅程独立通过。真实浏览器、连续主观视听和完整 P6+P7 仍属后续验收，不随 P1 自动关闭。

1. **Skill + receipt 同链续接**：先核清 SSE 与非流式的 receipt 持久化；非流式不能因没有 Activity 行而丢失读取回执。同包/version/digest 才复用，预览 receipt 不冒充当前视觉证据。
2. **pending 全链闭合**：恢复 direct 模式的 pending 法律，同时验证模型省略字段、工具接受/保存、问题结算、后续提醒消失。歧义必须形成真实 `ask_user`，不能只以散文追问。
3. **当前媒体与历史媒体分座**：当前 `prepare_video_materials` 不默认附完整长视频；按创作/修订需要提供有界代表帧，连续审片才走连续证据。历史媒体继续按项目事实折叠、按 item 恢复。
4. **修正链保持高层**：空 optional/remove 当前已有支持，不重复施工；修正后仍须重跑完整高层校验，处理非法源窗口、stale base 和错误目标，不增加循环次数来掩盖问题。
5. **文本与工具投影去重**：fresh 的 PageReading、Asset 全文与 Snapshot citable lines 不得重复占用；保存版不回退完整 Composition。
6. **注册拆分而非加测试墙**：`promo_p1_first_draft`、`promo_p1_continuation`、`promo_p1_revision`、`promo_p1_overlay` 均可独立运行；外部 provider/storage 故障与业务红项分开报告。

保留 20 次全局上限，但不把提高上限当作修复。不新增 shot/action、通用 correction 重构、通用 IR、新表、新 Agent、新生产链或预览平台。付费复验只沿用现有短确认交付旅程，不另建生产入口。

### 6.4 新会话架构交接

施工窗口只实施并报告；后续新会话负责架构 review，不以施工总结代替证据：

1. 先读 CLAUDE、PROGRESS §0、本合同和当前 git status；禁止 reset/checkout/stash/clean 或覆盖无关 dirty-tree 修改。
2. review 必须核对真实 diff、模型 trace、数据库版本/消息/问题和测试结果；区分代码存在、单次真实成功、注册通过与最终视听。
3. 若报告与代码冲突，以当前代码和可复现证据为准，先修正合同，再决定下一批。
4. P1 关闭后才可以讨论新的能力扩展；真实浏览器、最终视听、付费制作和正式渲染仍需单独授权与验收。

### 6.5 两份后续提示词

以下两段分别用于施工和独立架构验收。施工结束后再启用第二段，不让同一窗口自行证明方案正确。

#### A. P1 收口施工提示词

```text
你负责 Repurposer 的 P1 状态与证据收口。请直接实施和验证，不扩大范围。

先读 CLAUDE.md、docs/PROGRESS.md §0、docs/tasks/composition-authoring-context-convergence.md §6 及当前代码。先执行 git status；禁止 reset/checkout/stash/clean，不覆盖无关修改，不新增任务报告文件。

本批只处理现有阻塞，不新增 shot/action、外部 Skill、通用 correction、通用 IR、新表、新 Agent、新生产链或预览平台，不执行付费制作或正式渲染，不提高 20 次循环上限。

1. Skill + receipt：
   - 核清 SSE 与非流式的 receipt 持久化；Activity 只负责显示，不能成为持久化前提。
   - 选择现有 ConversationContext 或消息事实中的一个座位，不双写、不建表。
   - 续轮同时恢复 Skill 绑定与 arc/shot 文本读取回执；只有同包/version/digest/owner 才能复用。
   - 历史预览 receipt 不冒充当前视觉证据；已有保存版时使用其 provenance/base_ref，不重新绑定首稿 Skill。
   - 续轮不得退回完整 Composition 协议或出现 arc_not_read。

2. Pending：
   - 恢复 direct 模式的简洁 pending 法律，不复制到多个模板。
   - 覆盖 answer/skip/none、模型省略字段、工具接受/保存、问题结算和后续提醒消失。
   - 服务端返回目标歧义后必须形成真实 ask_user/question block，不能只以散文追问。
   - “整个第二镜”保存后结算原问题；后续修订和删除不得复活旧问题；修正使用当前 base_ref 和已结算目标/时间。

3. 媒体：
   - 当前 prepare_video_materials 不默认附完整长视频；普通创作/overlay 提供 source 身份、时长、宽高和有界代表帧。
   - 复用 craft_scan 或 review 的现有抽帧能力，不新建预览平台；代表帧不冒充连续审片。
   - builder 仍使用真实 SourceSnapshot/source_range/权限事实，不产生新 Output。
   - 历史媒体继续折叠，原始 item 可经 read_conversation_context 恢复。

4. Correction 与文本投影：
   - 空 optional/remove 已有支持，不重复施工；只修高层 shots/action，修正后重新校验完整当前输入。
   - 非法源窗口、错误目标和 stale base 失败闭；不让模型修底层 Op。
   - fresh 的 PageReading、Asset 全文与 Snapshot citable lines 不重复注入同一正文；保存版不回退完整 Composition。

5. 注册：
   - 将过长 promo_p1_authoring 拆为首稿、普通修订、overlay 询问/回答三个可独立运行的真实旅程；复用 helpers，不复制断言。
   - 外部 provider/storage 故障与业务红项分开报告；不把手工单项成功写成注册通过。

验证：
- 运行 cd apps/api && uv run --extra dev python -m pytest test/core -q；范围外旧 SFX 文案失败单列。
- 直接 Chat video 续轮无需重新绑 Skill/重读 arc，能保存 CompositionVersion/Storyboard，零 Run。
- 标题歧义形成真实 ask_user；overlay 回答后保存且旧提醒消失，删除后不复活。
- fresh 第二轮保持 ≤45k provider prompt_tokens；overlay 询问轮从 108,414 降到 ≤70k。
- 分别报告 system/tools、项目文本、历史文本、当前媒体和历史媒体；字符估算不得冒充 provider tokens。
- 外部服务不可用时明确 blocked，不盲重试，不宣称通过。

交接报告列出修改文件、状态唯一座位、真实消息/版本/问题 id、三个旅程独立结果、测试和逐轮 tokens，以及未运行/未验证事项。任一续轮回退、旧提醒、散文追问、完整长视频默认注入或底层 Op 修正仍存在，都不得宣称 P1 完成。
```

#### B. 施工后的独立架构评估与验收提示词

```text
你是新的独立架构评估与验收窗口。你的职责不是继续施工，也不是维护既有方案，而是根据证据决定：继续当前路线、只做一次限量修正，还是暂停投入并重新思考对策。

先读 CLAUDE.md、docs/PROGRESS.md §0、docs/tasks/composition-authoring-context-convergence.md（尤其三批合同、当前状态和本提示词）以及施工交接。先执行 git status。禁止 reset/checkout/stash/clean，不覆盖无关修改。本批原则上不改实现；发现缺陷时先记录，不用新补丁扩大 review 范围。

一、先建立证据，不接受施工总结代替事实
1. 审查实际 git diff：是否出现新通用层、重复状态、双写、无消费者接口或超出合同的 shot/action。
2. 阅读 artifacts/p1-closeout/provider-exchange.jsonl 及施工新增 trace；核对真实模型调用、参数、错误和 provider usage。
3. 查询真实数据库中的 Project、CompositionVersion、Message、pending question、Run/Output；不依赖报告中的“已保存”。
4. 运行相关核心测试与已拆分真实旅程。外部 529/disconnect/storage/timeout 单列，不能掩盖业务红项；环境不足时写未验证。
5. 不执行付费制作或正式渲染；本轮验收不等于最终浏览器和视听验收。

二、逐项判断用户价值是否真的成立
- 精确原文“/promo-video 使用这个skill帮我的网站做一个宣传片：https://agent.oxvalue.ai/”能否稳定形成首稿并呈现，零 Run。
- copy-only 是否逐字、按顺序、无重复、无额外文字。
- 直接 Chat video 续轮是否无需重新绑 Skill/重读 arc，并能通过 Chat 保存。
- set_text、set_clip_duration、apply_preset、add_media_overlay、remove_clip 是否只改目标范围。
- 目标不明确时是否真实 ask_user；回答后是否正确保存、结算并停止提醒。
- 高层参数错误是否只修高层 candidate；builder 错误是否可脱离 LLM 确定性复现，不转成几十个 Clip 修正。
- fresh、普通修订、overlay 询问轮是否达到合同中的真实 token 目标，且没有删除必要用户证据。

三、评估复杂度是否仍然值得
比较当前方案与继续维护旧完整实体协议的真实成本：
- 新代码是否真的减少模型错误类别，而不是只把错误搬到服务端；
- 高层协议是否仍受控，还是已经长成万能语义对象；
- 状态是否唯一归属，还是 Skill/receipt/pending/candidate 继续双写；
- 单场景展开失败是否能脱离模型复现并修复；
- 是否需要不断加 Prompt、守卫、重试和循环上限才能维持；
- 每轮 token、延迟、外部故障面和维护成本是否仍与目标不匹配。

四、只能给三种结论之一

A. 继续投入：
仅当主要用户旅程有独立真实证据，状态闭环成立，核心错误类别消失，上下文目标达成，且剩余工作主要是已定义的浏览器/正式渲染/视听验收。说明下一阶段及边界，不自动扩功能。

B. 限量修正：
仅当剩余问题是一个或少数明确局部缺陷，有确定根因、可复现证据和不改变主协议的修法。写出唯一修正范围、验证方式和停止条件；不得用它掩护继续扩 scope。

C. 暂停当前路线并重新思考：
出现任一强信号即可选择：
- 收口后仍重复出现底层 Composition/Track/Clip 纠错；
- Skill/receipt/pending 仍无唯一所有权或续轮仍断；
- 只有单次手工成功，无法重复用户旅程；
- builder 持续产生非法 Composition 且无法稳定脱离模型复现；
- 有界媒体和状态收敛后仍频繁出现约 100k 级请求；
- 复杂度继续增加但用户可见成功率没有相应提高；
- 外部故障与业务失败仍无法分离，导致无法取得可信证据。

选择 C 时，不继续施工。重新列出需要验证的替代假设，例如更小产品边界、不同模型/provider 的结构化能力、不同创作协议或更确定性的首稿路径；不要把旧方案换名字继续。

五、最终输出格式
- 结论：A/B/C，一句话说明理由。
- 已确认事实：按真实代码、trace、DB、测试和旅程列出。
- 未验证/外部阻塞：明确区分，不猜。
- 当前架构是否减少错误及维护成本：给证据。
- 继续投入的价值与下一次停止条件。
- 若 B：唯一修正范围与验收。
- 若 C：需要重新验证的核心假设和替代方向，不写新实现。
- 更新现有 tasks 合同的当前结论，不新增事故报告或会话编年史。

不得因为已经投入较多代码和时间而默认继续，也不得因为单次失败就否定已验证的有效部分。最终决定必须回答：用户现在是否更能稳定完成视频创作，以及继续当前路线是否仍值得。
```

## 7. 当前状态

批 1 的服务端工作草稿、条件工具和旧首稿恢复协议删除已落码。普通项目与 promo-video 已有真实 Chat 首稿保存及普通局部修订证据；活动草稿与保存版并存时 `revise_video` 保持可见。拒绝反馈、历史 seq 合并等批 1 修复保留。

保存/修订后的自动完整预览已撤除。默认 storyboard GET 只返回版本与分镜事实；`design_video(save=true)`、`revise_video` 和 `get_video_version(present=true)` 可携带一个显式 `scrub` 目标，block 持久化同一目标，刷新后经原路由重编译局部 spec。整片窗口失败闭，独立 Object 与无关 pending 媒体分离；无效目标不推翻已保存版本。ACK 不再重编译整片，只由客户端等待本次实际声明的局部 Scrub。

最小 Scrub Input 已接当前版本的明确 Text Clip / TextObject：Popover 中选择目标并调整现有 `style.font_size`，打开后按独立 Object 获取局部预览，拖动与 commit 只更新本地 Clip 草稿。Apply 通过 `PUT /chat/video/versions/{version_id}/clips/{clip_id}` 携带 base_ref、track_id、完整 Clip 与 request_id，经 `revise_video` / `apply_composition_edits` 生成新版本；取消、键盘、失败回滚与 409 冲突入口已落码。旧版本只读，不自动 rebase；Apply 后旧 Scrub 目标不追随新版本。

旧 Film 的 Chat tools/schema/prompt/pending、plan/propose 分派、render family、配置、启动清理、专属脚本和失效 fixtures 已删除；`film_narrations` 由新 Alembic migration 删除。共享 Chat/Run/Output/授权/计费/交付、SourceSnapshot、CapturePlan、video-spec、renderer、Clip、VideoTemplate、NarrationAlignment、受控 Generator 与 narration/media 能力保留。

P1 的内置 promo 封闭 shots/action、服务端展开、出生 provenance 投影和高层候选修正已落码。`design_video` 的 Promo wire 不再包含底层 Track/Clip/Animation/Keyframe，`revise_video` 只含五个 action；自由创作与高级完整实体修订保留。首稿可一次 `shots + save=true`，可选 `music_snapshot_id` 复用 MusicBed，`target_seconds` 由代码分配末尾阅读 hold。续轮缺少 Skill chip 时仍可能回退完整实体协议，且新 PackageSession 可能丢失 arc 已读回执；该问题未关闭。

显式逐字文案使用可选 `verbatim_copy: list[str]`：只有用户同时要求逐字、顺序、无其他屏上文字且不重复时才提供。展开后的每个原生 TextObject 必须按 journey 的空白归一化口径逐项相等，否则以 `shots/copy` 的 `PromoInputError` 进入现有高层 candidate correction；普通宣传片不受全局去重限制。`add_media_overlay` 支持绝对 start/end、无歧义 start+duration 和 `whole_scene`，后两者由代码基于保存版 Scene range 计算；Scene 或窗口不唯一时在任何写入前返回候选并继续 ask_user，不再扫描历史消息数字。

`evidence-push` 共用一条展开路径支持 web/web-view、普通 image 和 real video。普通媒体使用真实默认构图，不伪造 view/element；web 焦点从完整数据库事实解算，视频 source_range 不得超过真实素材时长。默认项目证据只含 snapshot 身份、citable lines、紧凑 view/target 摘要，但 fresh 的 PageReading 与 Asset 全文仍可能和 Snapshot 文本重复注入，不能写成去重已完成。`prepare_video_materials.material_targets` 按需返回选中 snapshot/view/element 的完整事实与媒体；默认每个网页只附一个代表 view，显式 element 才附 crop。被当前项目事实覆盖的历史媒体观察在同 Loop 和跨回合都折叠为紧凑文本，原始 ConversationContext item 不变，可按 id 经 `read_conversation_context` 恢复。

当前完整核心测试 **353 passed / 1 failed**，唯一失败仍是范围外 `test_media_import.py` 的旧 SFX 文案断言；Promo ruff、相关 py_compile 与 diff check 通过。`promo_p1_authoring` 已加入本批断言，但完整注册未通过：真实运行分别遇到 copy 候选未保存、MiniMax HTTP 529 overloaded、对象存储 `IncompleteRead`、provider disconnect 和 300 秒 `ReadTimeout`，后续单项结果不冒充注册通过。copy-only 项目 `7bff9291-d2f2-44d5-b4e3-5e2f19d3f113` 已确认首句只在 lead、第二句只在 close；修订项目 `2561005f-d099-4c9c-96ca-63fd57252503` 已保存到 v7，overlay 先 ask_user 零写入，回答整个第二镜后按 Scene range 270000–720000 保存，随后删除。普通 image 项目 `a19e0cc0-dbd6-47c8-9bfe-0524ceaaa8a1` 已经 Chat 保存 evidence-push；真实 video 经同源高层服务在项目 `32b8febb-059a-485a-8837-4e9e5e2b3210` 保存 version `127184fd-b18d-4573-b25c-ff0a1c802658`，source_range 为 0–360000，直接 Chat video 旅程未保存，不能记为 Chat 通过。标题歧义一次真实请求零写入但只有散文追问，没有结构化 ask_user；fresh 提问续轮的 Skill 继承与 video candidate scene_id 修正仍开放。非流式回合没有 Activity 行时 Skill receipt 不持久化；overlay 回答并保存后，旧问题提醒仍出现在后续消息中，pending 全链未闭合。20 次迭代上限只提供有界余量，不是这些状态问题的修复。

上述阶段的 provider trace 归 `artifacts/p1-closeout/provider-exchange.jsonl`。当时 fresh 素材准备后下一轮从基线 90,255 降到 28,039 / 42,243 / 42,257 prompt_tokens。多版本普通修订降至 54,956–61,161，overlay 询问仍为 108,414。当前代码已默认对普通视频投影有界代表帧。更新的真实 DB 记录分别确认了真实视频续轮继承 Skill 后保存分镜，以及 overlay 问题回答后保存、结算并删除。独立注册、稳定性、真实浏览器与最终视听仍开放。完整 Inspector、多选/批量、自由时间线、音频 Inspector、P9 与发布阻塞不归本批完成。

### 7.1 窄首稿对照与下一步

当前 MiniMax M3 对照使用相同用户需求和同一真实视频源，每种路径每题两次。基线走正常 Chat，窄首稿原型用一次结构化调用，服务端绑定原文、素材和现有模板，经 `design_video` 保存，再用公开 storyboard GET 核验。时间含首稿准备、保存和分镜读取，省略测试项目创建与素材复制。输入 tokens 为首稿请求的 provider 实测累计，含与该回合同 ID 的模型调用。

| 首稿 | 正常 Chat | 窄首稿原型 |
| --- | --- | --- |
| 两句逐字文案、两镜、10 秒 | 1/2，成功 15.79 秒，86,962–102,104 输入 tokens | 2/2，1.64–2.44 秒，每次 279 输入 tokens |
| 真实视频、单镜、4 秒、无屏上文字 | 1/2，成功 75.82 秒，132,253–220,029 输入 tokens | 2/2，9.01–9.96 秒，每次 3,321 输入 tokens |

基线两个失败项目 `17e9ed7b-7002-4b3c-9ddd-1e0d2fb9065c` 和 `23a0d3de-e2ff-4769-8fef-ffe6a8d4b3eb` 均为零版本，provider 正常返回。文案候选先触发最短阅读时长，随后违反原文约束。视频候选依次产生越界、反向和与成片时长不一致的源区间。六个已保存首稿都可通过普通 Chat 完成指定修订，标题仅改目标 TextObject，视频从 4 秒延到 5 秒并保留源入点。八个测试项目均零 Run，基线一例产生素材理解 Output。

保留 Composition 与同一写口。原型在脚本里直接读取分镜，稳定性证据限于本表样本。视频选段的审美质量和浏览器交付尚未验收。

### 7.2 官网同题对照与 overlay 定位

P1 保持开放，暂停扩展现有首稿纠错，P2 后置。用原始官网请求、MiniMax M3 和同一份已冻结网页捕获做两次对照，四个项目的六张截图 digest 一致。正常 Chat 两轮均调用模型 8 次，分别用时 80.92、123.41 秒，累计输入 329,777、323,325 tokens，零版本、零分镜。拒绝包含 Skill 可读但当前协议不接受的 shot、文案引用与原生文字不一致，以及为静态网页填视频源区间。

窄原型让模型选择中文主标题及两张官网截图，代码绑定身份、截图和既有镜头模板，经同一写口两次均保存四镜分镜。首稿保存和分镜读取用时 10.51、24.00 秒，每次结构化调用为 1,848 输入 tokens。随后另发普通 Chat 请求展示，分别用时 8.95、14.67 秒，均返回可确认的分镜卡。两次普通 Chat 改标题均只更新目标 TextObject，零新增/删除 Clip。四个项目均零 Run/Output。原型缺少从原始请求到同回合分镜卡的接线，浏览器和最终视听仍待验收。

Overlay 守卫已做局部修复：只有当前 pending 存在、`pending_disposition=answer` 且候选 base_ref 与本次歧义来源一致时，回答轮的合法修订才可重新进入校验；保存成功后才清理歧义并结算原问题。校验失败保持零写入和问题开放，无 pending 的歧义仍必须形成真实 `ask_user`。确定性回归先复现「只填结束秒数被拒 → whole_scene 被旧守卫误挡」，修复后覆盖保存、结算和删除后不复活；相关 44 项通过，完整 core 为 365 passed，唯一失败仍是范围外旧 SFX 文案断言。

窄原型的产品接线暂停，保留上述实验结果，原始 Chat 首稿路径未改。能力核对发现 Skill 实际暴露 15 个 shot cards，原生工具 schema 与 builder 只支持 `brand-emergence`、`evidence-push`、`next-step-lockup` 三个；`copy_references` 的说明称服务端填充原文，实际仍要求模型重复提交 `text`。后续减参只考虑服务端派生首稿 `scene_id`、复用已选身份、按稳定行引用解析原文和省略非必要视频窗口；叙事、镜头数/顺序、文案和素材选择仍由模型决定，不以固定四镜取代。

独立 `promo_p1_overlay` 本轮两次均为业务失败而非外部阻塞：第一次在消息 `53994724-ab18-486e-864e-3687bbe099c1` 直接把 overlay 保存到开场，版本 `2dab5594-05e2-49af-9c3f-66171e863d8d`，没有形成应有的问题。第二次原问题 `b65ec3ac-4025-4671-aeeb-3ff89dfe6df4` 被主动 `craft_decompiled` 问题 `c1943374-d3ff-4334-a8df-96787bb126b4` supersede；回答消息 `01ce0472-c1d3-44d8-bd37-dce57086f5b7` 保存了覆盖整个第二镜的版本 `c1f1e7d3-b72c-4de0-afd9-9d4f52ca5df9`，但结算的是后一个问题，所以旅程仍红。随后普通 Chat 删除消息 `81287038-0a38-4039-a399-0110f18f33fe` 保存版本 `bd76262d-7a1b-49a2-aefb-795e832db1b1`，零 Run、无开放问题，两个真实模型输入均无旧 pending 提醒。第二轮询问/回答整轮累计输入分别为 87,903 / 71,014 tokens；删除轮两次调用为 23,339 / 23,002 tokens。该真实旅程的问题竞态、官网首稿和第三轮跨 SSE／非流式续接均未验收，P1 保持开放。

### 7.3 同站点不同简报的创作与落版验证

两份简报使用同一份冻结官网证据（六张截图、91 条原文）、同一 MiniMax M3 和实际首稿 schema。模型自行选择主张、镜头数量、顺序、素材和文案，脚本将首个候选原样提交给现有写口。此对照没有经过普通 Chat 的首稿路由。

- **解释产品流程**：先看工作空间，再用两镜讲清证据入口和估值意见形成，最后邀请开始估值。模型选七镜，展开 26.5 秒。18,608 输入 tokens，模型调用 46.83 秒。项目 `d22af633-c053-4b2a-a197-e5aac83a9cc4` 零版本、零 Run。
- **说服谨慎买家**：用方法依据、人工审批、版本发布和决策追溯建立信任，最后邀请请求演示。模型选七镜，展开 26.5 秒。18,607 输入 tokens，模型调用 48.54 秒。项目 `dd4d8ecf-b244-41e8-92db-ea3675648d6e` 零版本、零 Run。

两份候选均能展开并通过 Composition 内容校验，实际保存均被 `copy_reference_mismatch` 拒绝。模型把支持中文转述和网页截图的英文原文装进只认实际原生屏上文本的 `copy_references`，分别有 11、28 条不匹配。需让逐字屏上引用与支撑转述或素材的证据有明确语义，保留逐字校验。两份方案的内容和行动邀请不同，但画面手段仍高度相似。流程版计划分别展示四步流程的前半和后半，实际使用同一截图、同一焦点，生成了相同的推镜和时长。首稿评估同时核对方案、编译后的画面意图和最终保存，不以其中任何一项代替全链。两例未进入浏览器或视听验收。
