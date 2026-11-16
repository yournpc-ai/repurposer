# Video Project — 视频作品、Skill 与渲染目标架构

> Status: 已拍板目标架构，开发中（2026-11-10）。本文是新架构唯一目标事实源；能力与验收统筹归 [promo-video 施工合同](tasks/skill-package-promo-video.md)，工作草稿、条件工具与预览反馈的实施归 [创作循环合同](tasks/composition-authoring-context-convergence.md)，A–C 证据归 video-project-implementation，当前批次归 PROGRESS §0。目标能力与单条旅程通过不代表全量实施或生产就绪，现行实现查代码与 RENDERING。
>
> 范围：先把网页宣传片与 MG 的创建、分镜、CRUD、版本、制作和交付做通；混合合成、程序化画面与生成媒体按施工合同分批接入；外部 Skill 持久化与加载随后开放；旧 Clip 高层能力内化与完整 Scrub Inspector 后置。最小 Chat 内 Scrub Input 已提前接入。**不迁移既有业务数据**；新表、新列和索引仍须走 Alembic schema migration。

## 0. 核心决策

1. **Project 是 Chat 与执行上下文，Composition 是一部持续编辑的视听作品身份**。同一 Chat 可创建多部 Composition 并通过 @ 分别持续修订；不引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
2. **CompositionVersion 是不可变编辑版本**，自身直接承载设置、素材引用、Scenes 与 Timeline；Timeline 只是版本内部的时间结构。
3. **Track 上是 Clip，Clip 内是 Object**；Animation 统一作用于 Object 属性，Transition 表达 Clip 之间的衔接。
4. **Storyboard 是 CompositionVersion 的分镜读面**，不是第二份可独立修改的作品数据。
5. **launch-film 在新链只是内置 Skill**。通用 `design_video` / `revise_video` / `produce_video` 承载所有视频创作，Skill 不拥有执行链。
6. **Chat 是唯一意图面**，`/任务名 + prompt` 只是确定调用语法；Graph/Run 继续负责执行，Canvas 不再是作品成立或审阅的前提。
7. **video-spec 是 Film 的继任渲染契约**，renderer-neutral；迁移期是明确的新旧替换，不建设第三套永久视频架构。
8. **不为旧 FilmStoryboard、film-spec 或旧项目数据建设迁移层**。新链验收后删除旧 Film 实现；Clip 的迁移与删除另行评估。
9. **同一作品允许混合画面来源**：原生文字/图形动画、已有实拍/图片、模型生成媒体及程序化画面可共同参与合成。内容类型与生产方式分开；支持范围以当前能力声明为准，文字动画不冒充自由 2D/3D 创作。
10. **所有创作来源共用一条创作循环与同一个可精修作品**：真实素材 grounding → 方法与能力选择 → CompositionVersion → 真实内容呈现 → 授权制作 → 视听检查 → 结构化修订与交付。固定 Skill、外部 Skill、自由设计和 Generator 只在创作来源上不同；出生后都展开为 Tracks / Clips / Objects / Animations / Audio / Speech / SourceSnapshots，后续修订与 worker 不再依赖 Skill。能力迭代只扩展这本体、Generator 和已注册工具，不另起作品根或生产链。

### 0.1 长期创作方针（所有阶段施工必读）

产品是**模型无关、以 Chat 和 Skill 为主要入口的视频创作工具**。用户提出要求、查看结果、多轮修改并交付作品；不要求用户理解轨道、节点或编写代码。A–C 基线与统一后续合同建立可持续扩展的基础，不要求一次达到参考作品的全部制作质量。

1. **少量能力组合出丰富作品**：优先建设素材、时间、叠放、文字/图形、动画、声音与可再生产媒体等可复用能力。代表样片是阶段验收，不是永久模板上限；不为单条参考片预建完整 NLE、3D 引擎、特效库或通用插件平台。
2. **原生内容与媒体生产互补**：需要精确独立修改的文字、图形等保留原生身份；复杂、特殊、变化快的画面可通过程序或模型生产为媒体，并保留可再次生产的来源。创作层统一用 `GeneratorObject` 表达后者，具体边界见 §4.3.2。
3. **代码也是创作材料**：受控程序路线须允许 Agent 根据需求编写、修改视觉程序，经预览反馈改善结果，不能只调用开发者预置效果。`draw-2d` 承载受控 2D 绘制；`remotion-project` 允许 Agent 按讲稿、文案和素材编写完整 Remotion 工程，包括多文件、多组件、共享 helper、Composition 注册与内部时间线。工程在上游隔离烘焙为固定媒体，最终 video-spec 仍无 React/Remotion。执行图的拓扑与权限仍由系统代码裁决；创作自由不等于业务调度、计费、数据库、动态依赖、网络或任意文件权限。
4. **生成可增量，保存与制作必须固定**：首稿通过多次有界工具调用形成同一个服务端工作草稿；每一步只校验和修改所属范围，完整呈现前做一次全量校验，并经唯一写口保存一个不可变 CompositionVersion。制作前默认只呈现 Storyboard、修改摘要和必要静态代表帧；动态检查只针对明确 Scene/Clip 时间窗或独立 Object 的可选 Scrub，完整成片动态预览永不提供。只有动态需求需要比较/澄清、用户修改后需要核对局部结果，或用户明确要求看特定效果时才放出局部预览；通用效果示例可走 Preset 候选。反馈只修订目标范围。用户明确制作后才由 produce_video 钉版本、程序、输入与执行摘要，恢复/重试不追 current、不重新设计。预览的调用、资源与费用有界并复用既有计量；内容、图、Run、队列、渲染与交付不新增平行生产链。
   首稿默认完整校验、保存并呈现分镜。模型遇到影响交付、可通过真实画面确认的具体动态疑点，或用户明确要求查看某个效果时，才检查对应幕或接缝。开启按幕审片后按播放顺序推进，复用仍有效的证据。保存后的 Chat 反馈以目标作品当前版本为基准，执行定向编辑，按需核对受影响的局部。当前接线见 [P2 创作循环合同](tasks/sequential-video-authoring.md#63-施工顺序与退出条件)。
5. **模型独立是领域边界，不是全模型已支持的声明**：作品、Skill、编辑操作不绑定某个模型品牌；文本/代码创作模型与媒体生产模型可不同，provider 能力、私有参数和用量留在适配边界。按真实消费者接入和验证，不先搭全供应商框架，也不承诺任意模型都有相同能力与质量。
6. **分开验收表达、执行、创作、编辑**：能保存不等于能渲染，能渲染不等于 Chat 能稳定创作，媒体可播放不等于内部元素可编辑。每批说明四层的实际出口、证据与未支持项；通过动态预览和必要试听判断结果，静帧/结构检查不代替视听验收。
7. **Skill 保存方法，扩展由真实需求驱动**：内置与外置 Skill 共用 `SKILL.md`、shot cards、sequences、静态 library index、demos 与可选 template 六类逻辑资源；Agent 经有界只读工具渐进读取选中的卡片、arc、预览和参考源码，不一次注入全包，也不建立 ShotRecipe 或运行期镜头注册表。外部能力按形态内化：instructions → 创作方法，结构 → VideoTemplate，局部参数 → Preset，媒体 → Asset/SourceSnapshot，动作 → 注册工具/provider，视觉程序 → 受控 Generator。声明式能力可校验后加载。外部脚本与普通 TSX 读取均为只读参考。包显式声明的 TSX 入口、源文件和固定资源经宿主校验及依赖锁定后，可组成不可变 Generator，按需交给现有隔离 runner 执行。字段、函数和执行能力随首个真实消费者增补；现有能力按统一合同分批交付，不因作品复杂便预设新的大阶段。

一个 Composition 至多绑定一个 Skill 版本。一个 Chat 内的不同作品可以分别使用各自的 Skill。已保存作品的定向编辑沿用作品来源与当前版本。

基础能力能够组合出同类作品，不等于能自动复现参考视频的全部创意、素材质量、节奏和人工设计。阶段出口允许用户提供素材、反馈与多轮指导，不以世界级自动创作为当前封板条件。

## 1. 行业坐标与名词

### 1.1 Composition / Sequence 与行业坐标

- [Final Cut Pro 创建 Project](https://support.apple.com/guide/final-cut-pro/create-a-new-project-verdb79783e/mac) 将 Project 定义为安排和编辑媒体的可编辑项目，并携带视频、音频与渲染设置；Project 不是导出的电影文件。它上面还有 Library/Event；不能据此把本产品已有的 Chat 项目与一部影片合并。
- [Final Cut Pro Magnetic Timeline](https://support.apple.com/guide/final-cut-pro/intro-to-the-magnetic-timeline-verb8fcfc133/mac) 使用 primary storyline、connected clips 与 connected storylines 维持同步；本架构借鉴其连接与分组思想，但不复制磁吸、自动 ripple 或 trackless 编辑。
- [Final Cut Pro roles](https://support.apple.com/guide/final-cut-pro/intro-to-roles-verafcc84f77/mac) 用角色组织 clips 和音频 lanes；本架构把 `role` 作为 Track 的分类元数据，不把 role 与固定 Track 混为一谈。
- CapCut 官方资料使用 project/draft、timeline、track、clip、split、text、audio 与 transition 等词，并强调多轨对齐；[官方基础编辑说明](https://www.capcut.com/resource/how-to-use-capcut) 和 [桌面多轨说明](https://www.capcut.com/resource/capcut-ipad-vs-desktop) 不提供可直接照搬的正式 schema。`Draft` 在本项目已有大量“未确认草稿”语义，不作为新的作品根名称。
- [OpenTimelineIO 的结构](https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-timeline-structure.html) 提供 Timeline / Stack / Track / Clip / Gap / Transition 与 RationalTime 的可交换参照。未来适配器可以映射这些概念，但 OTIO 的根命名不反向决定本产品的作品身份。
- [After Effects Composition](https://www.adobe.com/learn/after-effects/web/understanding-layers-composition) 组织视觉元素、时间动画与 transform；[Premiere Sequence](https://helpx.adobe.com/premiere/desktop/edit-projects/change-clip-sequence/create-a-sequence.html) 组织并行音视频轨道、片段、转场与效果。两者均可表达完整影片，不是跨厂商强制标准。本产品选择 **Composition**：当前同时面向 MG、网页画面、文字与媒体的时空组合，用户经 Chat 和对象属性组件编辑，不以专业剪辑时间线界面为前提。
- Composition 是领域数据身份，不是 Remotion/React 类型；用户界面使用影片名称、画面、字幕和版本等自然表达。工具名继续使用 `design_video / revise_video / produce_video`。

### 1.2 本架构词汇

| 名词 | 定义 | 明确不是 |
|---|---|---|
| **Project** | 一个 Chat 及其创作上下文、素材引用、执行图、Runs 与 Outputs，可创作多部影片 | 不是一部影片的身份，不限制跨 Chat 引用 |
| **Composition** | 一部视听作品持续修订时保持不变的身份，拥有当前版本引用 | 不是 Project、Timeline、Output 或渲染器组件 |
| **CompositionVersion** | Composition 的一个不可变编辑版本 | 不是整个 Project 的快照，不是 Run、Output 或消息草稿 |
| **Timeline** | CompositionVersion 内的 Track、Clip、Transition 与时间结构 | 不是 Project 之上的根实体，不单独建 Timeline 表 |
| **Scene** | 作品中的叙事范围与导演分组 | 不是 Track，不等于单个素材切片 |
| **Track** | 横贯整个 Timeline 的视觉或音频轨道 | 不嵌在 Scene 内 |
| **Clip** | Track 上具有输出时间范围的编辑项 | 不再专指旧 clip-spec；无需 `is_clip` |
| **Asset** | 视频、音频、图片、网页、文字稿等源素材 | 不是时间线实例 |
| **SourceSnapshot** | Asset 某次采集/处理后的不可变内容快照 | 不是会随 refresh 改写的“最新素材” |
| **Object** | Clip 内可渲染、可变换、可动画的内容 | 不自行决定所在 Track 与输出时间 |
| **Animation** | 针对 Object 属性的关键帧动画 | 不是 Clip 间 Transition |
| **Transition** | 同一 Track 上两个 Clip 的衔接关系 | 不是单对象 fade/zoom |
| **Storyboard** | CompositionVersion 按 Scene 聚合的分镜读面 | 不另存第二份可编辑作品 |
| **Output** | 某个 CompositionVersion 制作出的交付产物 | 不是可编辑版本 |
| **VideoTemplate** | 可实例化为 CompositionVersion 的声明式影片结构 | 不是 PromptTemplate，不是执行代码 |
| **Preset** | Animation、Caption、TextStyle、Audio 等局部参数组合 | 不是整部影片模板 |
| **Skill** | 可版本化、保存、导入的创作包，可含 instructions、VideoTemplate、Presets、输入要求与示例 | 不是 Tool，不授予权限 |
| **PromptTemplate** | composer 的可见提示词预填 | 不携带隐藏执行参数；不承担 VideoTemplate 的结构确定性 |

同一 Project 可同时创作长宣传片、短广告等多个 Composition，分别持续修改。独立维护的语言/画幅成片可有独立 Composition 并记录来源版本；一次性导出格式差异属于制作参数。首版不建设分支管理 UI 或完整变体系统。

全局素材库是用户可跨 Chat @ 引用的素材与产物读面，不另存一套作品内容。Project 不是全局引用的权限边界；任何引用均由服务端按 owner/权限解算。Skill 只保存创作方法；引用既有产物、继续修订或作为新影片素材，不需要“复制确切作品”功能。

## 2. Composition 与 CompositionVersion

### 2.1 结构

```text
Project / Chat
├── 素材与全局库引用
├── Composition A / B …       origin_project_id 记录创作来源
│   ├── owner / current_version
│   └── CompositionVersion 1 … N
│       ├── settings / sources / scenes / timeline
│       └── skill_provenance / content_digest / base_version_id
├── Runs / graph nodes        属于本次执行所在的 Chat
└── Outputs                   钉 Composition 与确切版本
```

Composition 使用独立 id 与 owner，`origin_project_id` 记录来源而不锁定编辑入口；跨 Chat 的引用、修订与执行事件保留各自 Chat 血缘。删除 Chat 与全局素材的保留/删除关系须在 A 的 schema 冻结前明确，不得默认级联删除跨 Chat 使用中的作品与快照。

`CompositionVersion` 自身直接承载下列字段，不再包一层 Document：

| 字段 | 职责 |
|---|---|
| `schema_version` | 后续向前演进的 schema 版本；不等于旧 Film 数据迁移 |
| `composition_id` | 所属作品身份；不能用当前 Chat 的 project_id 代替 |
| `version` | Composition 内单调递增版本号 |
| `base_version_id` | 本版基于哪个版本产生 |
| `settings` | 帧尺寸、fps、timebase、sample_rate 等制作设置 |
| `sources` | 本版绑定的 SourceSnapshots 与素材槽位 |
| `scenes` | 叙事范围、导演意图、画面描述与脚本 |
| `timeline` | Tracks、Clips、Transitions |
| `skill_provenance` | 实例化所用 Skill/Template/Preset 版本；仅为血缘，不是运行依赖 |
| `content_digest` | 规范化后的版本内容、设置、素材快照与创作 provenance 的身份；不含呈现回执和临时签名 URL |

### 2.2 唯一写口与并发

所有 LLM 创作与修订、确定性手势和未来 Markdown 组件提交都经 `apply_composition_edits` 落版。**生成原子性不等于保存原子性**：工作草稿可以逐步生成，CompositionVersion 仍一次完整校验、一次原子提交。

```text
首稿 / 开放重稿：
design_video(draft_ref?, settings?/sources?/完整实体写入/稳定 id 删除, save=false)
→ 服务端保留同一个未提交工作草稿
→ 每次只校验本次实体及其可独立判断的来源/时间/权限约束
→ 返回新的 draft_ref 与有界摘要，不生成 CompositionVersion

完整呈现前：
design_video(draft_ref, save=true)
→ 解算不可变 SourceSnapshot 身份与 digest
→ 对组装后的完整 Composition 做 schema + 内容校验
→ apply_composition_edits 一次性插入不可变 CompositionVersion
→ 完整分镜进入反馈循环；仅在创作意图需要时附精确版本局部 Scrub/代表帧

已保存版本的定向修订：
base_ref(composition_id, version_id, content_digest)
+ 自由路径的完整 Scene / Track / Clip / Transition 写入与稳定 id 删除，或内置 promo 的一个封闭 action
+ request_id
→ 原子合并到当前工作内容
→ 校验完整 Composition
→ 插入一个新 CompositionVersion
→ 条件更新 Composition.current_version
```

- 工作草稿复用 ConversationContext，不新建 Draft/AuthoringSession 表或另一作品根。草稿不是版本，不进入正式 Storyboard 呈现、制作或交付；成功保存后退役。
- 自由创作与高级修订保留完整实体协议：本次只携带设置、来源绑定或完整实体，未提供的范围保持原值；所有内容写入先经 `save=false` 合并，`save=true` 只携带当前 `draft_ref` 与允许的非内容保存参数。Object、Animation、Keyframe 随完整所属 Clip 提交，完整 Track 自带完整 Clips。
- 内置 promo-video 与其他无声明 Generator 的创作共用 `scene_plan / scene` 高层协议：首次以 `scene_plan + source_ids` 决定叙事顺序并建立草稿，随后每次只写当前 `scene` 的来源、取景、原生文案和既有 Preset；`music_snapshot_id` 只接受现有 Music 流程准备好的 audio Snapshot。`save=true` 只保存当前 `draft_ref`，服务端确定性展开 Tracks/Clips/Objects、布局、时间窗与动画，完整校验后经唯一写口落版。模型不得提交 raw Track/Clip/Animation/Keyframe、布局、timebase、track order 或通用 motion/placement 字段袋。
- 服务端固定 Skill 版本并绑定当前用户约束、来源身份、digest 与时间事实；原生展开不执行 demo TSX。高层参数候选由现有纠错机制处理，非法展开作为宿主缺陷失败闭，不向模型泄漏底层修复协议。Generator 仍按自身局部任务读取参考源码。
- 内置 promo 的 `revise_video` 只接受 `set_text`、`set_clip_duration`、`apply_preset`、`add_media_overlay`、`remove_clip` 的封闭 action union。服务端解算 target/source/base_ref，展开普通 Op，分配 Track/order、LayoutBox 和 ticks，完整校验后保存。目标或时间窗不唯一时复用 `ask_user`，询问前零内容写入、零 Run；其他 Skill 和自由创作的高级完整实体修订能力不删除。
- 首稿 schema/语义错误与保存版局部错误都回到当前工作草稿或当前 base_ref，只修正报错范围。`fresh_design`、`rejected_candidate_ref` 和“首稿结构错误必须整片重交”不再是恢复合同。高层参数候选由现有 `correct_tool_candidate` 修正；合法高层输入若展开出非法 Op/Composition，则作为 builder 缺陷失败闭，不让模型修底层字段。
- Chat 不让 LLM 编写构造 Op 程序，也没有底层 Op 替换、字段 patch 或执行顺序语言。完整实体写入是声明式状态，不是 Op 流；服务端确定性 shot/action/Preset 展开与受控 Generator 编程不等同于恢复这种模型协议。
- 只有 Scene、Track、Clip、Transition 可独立寻址；Object、Animation、Keyframe 随完整所属 Clip 提交，完整 Track 自带完整 Clips。Clip 写入使用 `{track_id, clip}`；既有稳定 id 为更新，新 id 为新增，独立 remove 列表删除。完整 Track 中的既有 Clip 会从旧 Track 原子移出，不得复制稳定 id。拆分 = 同批删除旧 Clip + 写入两个完整替代 Clip。Settings 与 Sources 在工作草稿中作为完整所属值更新，最终仍执行全量校验。
- 每个新实体先做自身 schema 和可独立判断的规则校验；跨 Scene/Track/Clip 的覆盖、全局容量、呈现完整性与最终渲染约束在 `save=true` 时统一校验。权限、owner、不可变来源、摘要、并发、幂等、计费与 Generator 隔离不因增量创作延后或绕过。
- 过期 base_ref/draft_ref、并发覆盖和非法字段失败闭；跨 Chat 编辑同一 Composition 使用同一当前版本条件更新。
- 相同 owner/Composition/request_id 的同一提交重试返回已提交结果；同 key 不同载荷拒绝。请求幂等与并发检查分开，不能用过期版本错误代替成功请求的恢复。
- change_set 由系统比较 base/result 得出，不由模型自报。未触碰的 Scenes、Tracks、Clips、Objects 保持原值；确定性地刷新或清空受影响的描述/派生字段不视为额外创作。
- 新版本不反向改写已经执行的 Run 或已交付 Output。Output 钉 `composition_id + composition_version_id + content_digest`，其 `project_id` 记录本次制作所在 Chat；旧 Output 在新制作真实完成前保持可用。
- 新视频 Output 的既有 `work_id` 映射到 Composition.id，承接现有发布/归档作品锚；内容版本、Output 行与制作尝试不混用。旧 Clip/非视频的 work/edit/restore 契约保持当前作用域。
- `pending_brief` 只保留 plan/question/confirmation 状态，不再兼任 Film 或视频版本库；plan/propose 两条 Chat 路径调用同一个编辑服务，不各复制一套 compose/patch。
- `get_video_version(version_id | composition_id + current)` 是明确版本读面；多影片时不得用“本 Chat 最新视频”替代目标解算。

### 2.3 可审阅呈现也是版本事实

`storyboard_payload(version)` 由服务端从保存后的 CompositionVersion 确定性生成，向工具与 LLM 提供完整分镜事实和回退事实标签。用户可见呈现不是这份 DTO 的技术表，而是 LLM 基于这些事实写出的简洁 Markdown 创作概要：整体方向、主要段落的画面与动作，以及有助于理解的屏上文字、旁白和音频事实；标题、列表或表格按内容自由组织。`visual_description` 是画面描述的主要来源，缺失时只能概述真实结构支持的事实。保存版仍是唯一制作真相，概要不是第二份可编辑作品数据。

呈现记录持久化 `presented_message_id + presentation_digest + composition_version_id`。消息块只保存版本引用；可见 Markdown 走普通 assistant 正文与 Streamdown，保存版事实就绪且分镜 Markdown 完整打字释放后才 ACK。ACK 同时匹配该块的版本/已有 `content_digest` 与当前 DTO 的 `presentation_digest`，再更新版本外呈现回执；旧引用缺失的 content digest 在这次真实呈现时补齐。刷新后旧展示摘要不得否决当前真实呈现，过期摘要回放仍拒绝。这里的“完整呈现”指分镜表与创作概要已经释放，不要求技术字段全量上屏，也不证明用户主观已读。首稿 Start 同时校验版本、完整呈现记录与后续用户批准；用户确认的是创作方向，不是逐项审批技术分镜。

### 2.4 内容、执行与产物身份

- `content_digest` 标识保存内容；修改视觉摘要等版本字段也产生新内容版本，呈现状态在版本外保存。
- 制作请求在 Start 固定版本、编译器/adapter 版本、字体资源、声音与合成参数、制作政策及能力要求，生成执行输入摘要；不得声称此时已有尚未合成音频的内容 hash。
- 准备完成后把真实音频/派生素材的 digest、最终 video-spec 与运行依赖固化成执行 manifest，生成 `execution_digest`；重试复用已成功的准备结果，不重新采样或静默换引擎。Run/Output 记录两阶段身份，worker 分阶段复核。摘要使用不可变存储身份与资源 digest，临时签名 URL 只作为传输凭据；同内容重签不改变内容或执行身份。
- 制作请求另有幂等键，避免重复 Start、重复 Output 和重复收费；内容 digest 不是请求幂等键。
- 显式选定的历史版本可以制作；“过期”指编辑 base_ref 或授权/制作引用已失配，不意味着历史内容版本本身失效。当前新版本不会使已启动 Run 换版。

## 3. Scene、导演信息与 Storyboard

### 3.1 Scene 的职责

Scene 表达“这一幕为什么存在、覆盖什么时间、观众看到什么”，不拥有另一套局部 Timeline。

```text
Scene
├── scene_id
├── range                 全片输出时间范围
├── intent                导演目的：这一幕承担什么叙事任务
├── visual_description    LLM 撰写的用户可读“画面与动作”摘要，可空
└── speech_clip_ids[]     引用旁白；精确脚本仅保存在 SpeechObject
```

Clip 可带可空 `scene_id` 表示叙事归属：

- 网页、标题、说明文字和幕内旁白可随 Scene 整体移动；
- 跨幕音乐等全局 Clip 为 `scene_id=null`；
- `scene_id` 不改变 Clip 的全片输出时间坐标；
- Scene 与 Clip 的范围一致性由 validator 和编辑操作共同维护。

一个 Scene 可含多个镜头和多个素材切片；“一个视频 Clip 切一刀”不自动产生新 Scene。

Scene 的移动、复制、删除与时间变换都作用于显式目标集合；Scene.range 与所属 Clips 必须由同一原子操作维护，不能只改叙事标记而留下旧时间结构。`move_scene` 只表达平移，不能代替改时长。通用目标、时间变换与联动语义见 §6.6；当前已支持的操作以施工合同为准。

Scene 的移动、复制和删除以同一批原子编辑维护归属 Clips、动画、旁白引用与受影响 Transition；移动不改变源区间，复制按 §4.2 重映射 ID，删除不能留下悬空引用。跨幕/全局 Clip 不因时间上与该 Scene 相交就被连带修改；跨组关联不能可靠保留时明确冲突，不隐式 ripple 或挪动其他 Scene。首批实现实际 CRUD 所需操作，不扩展成磁吸时间线编辑器。

### 3.2 `visual_description` 是独立的导演表达字段

分镜表不能只是把内部元素枚举序列化成“webpage + text + image”。每个 Scene 都有可空 `visual_description`，由 LLM 根据实际设计用简洁自然语言描述：

- 画面里有哪些可见元素；
- 主体是什么；
- 元素以什么方式进入、运动或退出；
- 镜头如何推进或切换。

例如：“网页总览缓慢推近，左侧标题逐行升起，右下角功能标签随后淡入。”它不是冻参模板，也不是 renderer 输入。

**真实性约束：**

1. `visual_description` 只能描述当前版本真实存在的 Objects、Clips 和 Animations，不得发明元素或运动。
2. 时间、帧数、精确屏上文字、旁白和音频状态从结构化字段读取，不由该摘要代替。
3. Chat 修订改变视觉内容时，修订 agent 根据保存后的当前 Scene 重写受影响摘要。
4. 确定性组件/手势直接改变视觉内容时，旧的 `visual_description` 必须清空并回退到事实标签；不得继续展示旧描述冒充新画面，也不要求一次额外 LLM 调用才能保存。
5. 该字段 null 读容忍；进入用户散文或表格流时遵守打字机两牙。描述与结构冲突时，结构是执行真相，描述必须失效而不是反向改结构。

### 3.3 Storyboard 投影

Storyboard 由 CompositionVersion 投影，分镜表最少包含：

| 列 | 来源 |
|---|---|
| 幕号 / 时间 / 帧 | Scene.range 与统一时间量化 |
| **画面与动作** | `Scene.visual_description`；空缺时用真实元素事实标签 |
| 屏上文字 | 当前 Scene 内 TextClips 的精确内容 |
| 旁白 | 引用的 SpeechObject.text 原文；无旁白明确标记 |
| 素材与音频事实 | SourceSnapshots 与覆盖该范围的音频 Clips |

修改分镜就是修改 CompositionVersion；修改后重新投影**完整当前事实**，不是拿旧表加一段模型猜测的 diff。结构化 `storyboard_payload` 是工具、版本身份与修订的读面，不直接平铺给用户；LLM 根据保存版撰写当前创作概要，`visual_description` 已随版本保存，因此不需要让 Chat 模型再次转录内部元素或技术参数。

## 4. Timeline、Track、Clip、Object

### 4.1 Track

```text
Track
├── track_id
├── kind = visual | audio
├── role = main | title | caption | dialogue | music | effect
├── order
└── clips[]
```

- 视觉 Track 的 `order` 决定叠放，不再维护一套平行全局 `z`。
- 音频 Track 进入混音；role 支持组织、定点修改和未来分轨导出。
- Track 横贯整片，Scene 只标记叙事范围；跨幕音乐不复制到每个 Scene。
- 首批只创建实际能力需要的 Tracks，不开放自由 NLE 轨道编辑器。
- Layer 不再作为另一套持久容器；需要此词时仅表示视觉投影或 UI 分组，不与 Track 各存一份 Clips/Objects。Track、Clip、Object、Animation 是版本内容中的结构化实体，不按元素各建数据库表。

### 4.2 Clip

```text
Clip
├── clip_id
├── range                 全片输出时间窗
├── scene_id?             叙事归属，可空
├── source?               固定 SourceSnapshot + 可选源素材时间区间
├── object
└── animations[]
```

| Clip | Object | Source |
|---|---|---|
| VideoClip | VideoObject | 视频快照 + source_range |
| AudioClip | AudioObject / SpeechObject | 音频快照；待合成 Speech 不伪造媒体 source，脚本/声音绑定归 Object |
| ImageClip | ImageObject | 图片快照 |
| TextClip | TextObject | 无源素材 |
| WebClip | WebObject | 网页快照、页面视图或录屏 |

同一 Asset 可由多个 Clips 引用不同 `source_range`；每个 Clip 有自己的 id、输出窗、对象与动画。Clip 是统一编辑项契约，不要求为表中每一行建设继承类或数据表；对象 kind 与轨道能力共同校验，不另加 `is_clip`。

源引用结构为：

```text
source?: {
  asset_id,
  snapshot_digest,
  source_range?: { start, end }   // 源时间，采用 §6 的时间表示
}
```

- 有 source 时 asset_id 与 snapshot_digest 必须解算到本版绑定的同一不可变快照，不使用含义模糊的 `clip_source_id`。
- 视频、音频、网页录屏等有时间轴的素材使用 source_range；图片和静态网页视图不伪造源时间窗，显示时长由 Clip.range 决定。Text 无需媒体 source；待合成 Speech 的原文与声音绑定归 Object，真实合成音频归执行 manifest，不能在制作后回写不可变版本来补 source。
- 例如 Clip A/B/C 分别引用 asset X 同一快照的 00:10–00:18、00:32–00:41、01:03–01:09；各自的全片输出位置独立指定。源窗不等于输出窗，移动 Clip 不重新裁源。
- Scene/Track/Clip/Object/Animation 的 ID 在版本内按各自类型唯一；同一实体跨版本保持 ID。新增或复制实体生成新 ID，并原子重映射内部动画、Scene 和 Transition 等引用；复制可继续共享同一 SourceSnapshot，不复制源媒体。移动/改属性不换 ID；TextPart 身份另按 §5.2 的文本派生规则处理。

### 4.3 Object

Object 负责内容、布局和表现，Clip 负责时间与轨道。

- VisualObject：layout、transform、opacity、style、effects。
- AudioObject：gain、pan 与音频 effects。
- WebObject：网页快照/视图引用及取景、相机所需的结构化参数。
- VideoObject：真实视频快照的画面与原声共用 Clip 源窗，携带 layout/fit/transform/opacity/gain/muted；背景等静音层不复制第二条原声 Clip。
- SpeechObject：`text` 是旁白原文唯一来源，另存声音绑定与合成 provenance；Scene 和分镜表引用该文本，制作后才解析成可渲染音频。
- GeneratorObject：保留程序或模型媒体生产的可审阅来源及参数，准备后解析为图片/视频参与合成；当前已接受控 `draw-2d`、隔离部署下的 `remotion-project` 与 `image-generation` 单图请求。生命周期见 §4.3.2/§8.1.1。

每个 Object 有稳定 `object_id` 和类型 `kind`。视觉属性明确 layout box、transform origin、相对 position/scale/rotation、opacity、style/effects；音频使用 gain/pan/effects，不强套视觉 transform。素材绑定由 Clip.source 与版本 sources 共同确定；WebObject 的 view/元素/取景选择必须属于该快照，不另存会独立漂移的素材身份。

ASR words/segments、翻译与字幕对齐、speaker_map、crop_track 等上游事实属于素材快照或带输入 provenance 的派生结果，不粗暴塞进通用 Object，也不丢弃其高层语义。需要显示/播放的结果再编译为 Text/Video/Audio Clips。旧 Clip 的这些能力仍后置逐项承接；本轮不会为了通用模型重写 ASR 或提前删除旧 Clip。

Layout 与 Transform 不得形成双真相：layout 决定静态盒，transform 只表达相对盒的位移、缩放、旋转与透明度。相同位置不得同时由 `rect.x` 和 `transform.x` 两套值决定。

### 4.3.1 混合画面与生产来源

Scene 只组织叙事范围，不限定为“文字幕/网页幕/视频幕”，也不拥有独立执行引擎。视觉 Track 的 order 表达叠放，跨幕背景可与跨幕音乐一样不绑定单个 Scene。目标允许在同一场景组合以下内容：

| 内容 | 领域承载 | 生产方式与可编辑性 |
|---|---|---|
| 标题、字幕 | TextObject + Clip | 原生内容，可精确改字/样式/动画；已烧录进素材的字不是独立 TextObject |
| 实拍、已固定的生成/程序视频 | VideoObject + 源快照/源时间窗 | 作为媒体使用时共享布局、裁切、时间和外部动画；保留可再生产来源的创作对象另见 GeneratorObject，不承诺直接编辑烘焙视频内部元素 |
| 上传图片、已固定的生成图片、装饰图 | ImageObject + 源快照 | 作为媒体使用时来源不决定新 Object 类型 |
| 可编辑图形 MG | 原生图形/路径与 Animation | 按代表场景添加最小受支持图元，参数可编辑；不预建完整矢量设计系统 |
| 受控 2D/3D 程序画面、模型生产画面 | GeneratorObject → 固定媒体 | 保留程序/请求与参数，显式生产后参与合成；内部修改需改来源并重新生产。当前实际 producer 为 draw-2d 的受限 2D 绘图命令、隔离部署下的 remotion-project 多文件 TSX 与 image-generation 的 MiniMax image-01 单图请求 |

**当前能力边界**：原生 Object 已接 text/image/web/video/audio/shape；ShapeObject 支持 rect/ellipse/path 几何，MG Director 当前按需创作 rect/ellipse，多个同幕图元分轨。VideoObject 支持真实视频源窗、布局/fit、外部 transform/opacity、原声 gain/muted，已与原生标题/字幕、动态背景和音乐经过同一 CompositionVersion 合成及 Chat 局部修订。GeneratorObject 已接 `draw-2d`：Agent 编写 `render(ctx)`，受限运行为固定 MP4/PNG，最终按普通 video 参与合成；已接 `remotion-project`：Agent 编写受控多文件 TSX，在部署同时开启 API 与真实隔离 runner 时烘焙为固定 MP4/PNG；也已接 `image-generation`：保存 MiniMax `image-01` 的 16:9 单图请求，经既有 Run 授权后真实生成并按普通 image 参与合成。局部换源窗当前保持输出时长。Speech 已接首个 MG 固定切点旁白消费者；已接首个固定媒体 split/trim、全画幅不透明媒体 crossfade 和冻结音乐节拍吸附消费者；通用 target × move/trim/delete/time_map × ripple/source policy 已落码，原生/Web 输出时间映射与固定 Audio 显式 1× 裁取复用同一写口，Speech、Generator、VideoObject 的时长映射失败闭，验证状态见施工合同。其他模型、生成视频、通用媒体 rate 和自由 NLE 仍按施工合同分批实现。“自由 MG”不承诺任意 2D/3D 画面。

代表性出口分为两类，均须经过 Chat 设计、审阅、制作与局部修订：

1. **产品宣传/混合作品**：图片、原生文字、真实视频和网站在同一个 CompositionVersion 混合；网页可以提供真实状态、底板与元素层，视频保留原声关联，文字与图片独立修订。不能用四条彼此独立的单素材样片推定这条通过。
2. **知识讲解**：输入可以只是用户给出的知识，或明确标注的模拟知识文字稿；最终音频与 NarrationAlignment 驱动 Scene 和具体词锚动画，原生代表 Preset 负责高频文字/图形与可编辑字幕，Generator 负责解释知识的概念主视觉。真实图片/视频/网页不是必要输入；模拟知识稿是演示创作输入，不冒充真实采访、研究引用或事实来源。修改一个 Generator 不得重做未点名的旁白、字幕或其他对象。

既有“动态背景 + 中央实拍 + 独立标题/定时字幕 + 原声/音乐”出口继续有效。平台播放器按钮、账号与弹幕不属于作品内容；不能用静态网页或纯文字片通过替代混合合成能力。

视觉布局与时间编辑继续落到 Clip/Object；已有原声关联、字幕对齐等上游事实保留来源。原生对象可由后续 Inspector 编辑；生成或程序媒体只能编辑对外暴露的参数及布局/裁切等外部属性，不虚构内部元素可编辑性。

### 4.3.2 GeneratorObject：可再次生产的画面（draw-2d / remotion-project / image-generation 已接）

`GeneratorObject` 是 **Object 的一种创作层类型**，`kind="generator"`；不是业务执行图的 `prototype="generator"`，不是 Run，也不建立每个对象一个图节点。受控程序与首个模型图片消费者已分别接入；不按每种效果或供应商创建 Object 子类。

`draw-2d` 已冻结以下最小语义；后续消费者按实际需求扩展，不预建函数注册平台：

| 语义 | 归属与边界 |
|---|---|
| 稳定身份与外部表现 | 沿用 object_id、Clip 输出时间与受支持的布局/变换；外部布局修订不等于修改内部画面 |
| 可再生产来源 | 不可变程序内容或可解析且有 digest 的程序引用，或模型生成请求；明确生产方式及版本，不保存会漂移的路径或“最新程序” |
| 参数、资源与输出约束 | 已声明的参数、固定参考/依赖资源、尺寸/时长/帧率等约束；不能接受一个绕过校验与权限的任意可执行函数对象 |
| 实际生产结果 | 在执行 manifest 记录实际文件、digest、来源与执行血缘；pending 不伪装成 SourceSnapshot，生成完成不回写不可变 CompositionVersion |
| 再编辑与复用 | 改来源/参数经唯一内容写口生成新版本；只重做受影响生产结果，其余已成功且输入匹配的结果复用。把既有结果当普通素材时，显式绑定其快照为 Image/VideoObject，与继续修改 Generator 来源区分 |

draw-2d 的来源字段为 `producer/code/parameters/output`，program_digest 覆盖四者的规范 JSON；output 固定完整 Composition 画布、30fps、duration_frames 与背景，单 Scene 最长 30 秒。Agent 程序只实现 `render(ctx)`，逐帧返回 rect/ellipse/polygon/line JSON 命令；独立 Node 权限进程不暴露业务数据库、调度、计费、DOM、网络或任意文件能力，限制初始化/逐帧/总执行时间、命令数与输出字节。stdout 在读取中累计，超限立即终止并回收子进程；超时、异常与取消共用同一清理路径。Pillow 光栅化、PyAV/libx264 生成 MP4 与代表帧，`video-generators/{program_digest}.json` 固定媒体、预览、输出约束和诊断；相同 digest 读取并校验既有媒体后才复用。迁移前持久化的 `runtime=drawing-v1/component-v1/image-v1` 只在 `editing/store.py:content_of` 的读取副本中映射为对应 producer；不回写历史版本，不重算其已存 content_digest，新保存内容只含 producer。

`remotion-project` 是当前受控 producer：Agent 根据真实讲稿、文案、素材与 Skill 方法编写完整 Remotion 工程，可自主组织多文件、多组件、共享 helper、Composition 注册与内部时间线。自由 component 设计把 1–6 个独立 Generator 顺序放进同一个普通 Composition；不同叙事阶段可分 Scene，连续变换也可保持一个长 Scene，每幕最长 30 秒、总长不超过 118 秒，不把多幕作品烘焙成一个不可定位来源的整体。CompositionVersion 保存每幕不可变文件集合及逐文件 digest、入口、Composition id、typed props/props_schema、固定图片资源、完整画布 30fps 输出与锁定依赖，digest 覆盖全部生产来源。用户显式 @ 的已处理 IMAGE Asset 先冻结为本人 SourceSnapshot，Director 只能逐字段回引服务端给出的资源身份；外部 SkillVersion 图片继续按包身份校验，URL、视频 Output、未声明媒体与网络资源不得进入。`staticFile` 的参数可以是字符串字面量、props、变量或计算表达式；bake 只改写临时执行副本，为直接调用注入运行时守卫，实际路径必须精确命中当前 Generator 的已声明资源，未声明路径、遍历、URL 与非字符串仍拒绝，CompositionVersion 中原始源码及 digest 不变。内联 SVG 可使用同文档 `url(#id)` 滤镜/遮罩引用；data-URI 与外部 URL 仍禁止，程序纹理由内联 SVG/普通元素生成。受控上游 runner 只允许审核后的声明 API、依赖和固定素材，禁止动态安装、未声明 import/eval、网络、业务文件、DB、调度与计费。当前隔离实现仅支持 macOS Seatbelt：外部网络与本地 PostgreSQL/MySQL/Redis 端口拒绝，仅保留渲染所需 loopback；读取限于声明依赖/render 包与临时工作目录，写入限于工作目录；全局一次一个 bake，CPU 220s、墙钟 240s、进程树 RSS 8GiB、临时目录 512MiB、固定图片单资源 16MiB/单组件合计 32MiB、MP4 24MiB、PNG 4MiB、结果 40MiB，并回收所有后代进程组与临时树。API 开关与 render `/health` 的活跃隔离必须同时成立，设计才开放；其他平台、未配置或健康检查失败均 fail-closed。确认前只保存来源与静态结构，不执行 bake；授权制作后按 digest 固定 MP4/PNG，参数或代码修订经唯一写口产生新版本并只重做受影响媒体。重要独立文字、字幕、旁白和音乐保留原生对象；图形关系必需的短标签可随代码画面烘焙，但不因此获得独立原生可编辑性。

普通 Chat 的工作草稿按完整 Scene/Track/Clip/Transition 合并，重复或非法实体仍拒绝。空 props 与语义为空的 props_schema（包括仅含空 type/properties 的等价形态）规范化为封闭的零参数合同；受控 Generator 未给 output 时，服务端仅按所属 Composition 画布/fps/背景与 Clip 整数时间窗推导，不能精确整除为帧时仍拒绝。网页 Generator 图片只能复制准备结果中的 `fixed_resource` 完整身份，不能把 web Snapshot 与某个 view 的文件路径拼成资源。

旋转轨道消费者已验证 Agent 原创三轨道、几何符号及差速/反向运动；初版与 `speed_multiplier` 修订各有独立 program digest 和精确预览，固定媒体与原生 Text/Image 同版合成，重试准备复用同一固定媒体而不重新创作。该出口是 run-less 领域消费者证据，不代表正式 Chat/Run 计费旅程已通过。

image-generation 当前只声明 `producer/prompt/provider/model/parameters/output`，首个消费者固定 provider=`minimax`、model=`image-01`、16:9 单图，不暴露种子、参考图或任意供应商参数。设计与修订只保存请求；授权 Run 缺失媒体时先在对应执行键持久化 `submitted` 标记，再发出一次非幂等生成 POST。MiniMax 同步 image-01 接口未文档化幂等键、客户端请求 ID 或历史结果查询；传输/响应解析失败，或恢复时只读到 submitted 而没有固定媒体，均按“结果未确认”失败闭，不自动再次提交，不把未知供应商消费记成 0 或 1 张。该标记只保证同一执行键的恢复不盲重放，不承诺供应商恰好一次执行；用户明确重新生成仍须新 Run 和独立执行命名空间。

`video-generated-images/` 下的固定执行 manifest 记录完整请求、run_id、实际图片字节 digest、尺寸、格式与实际返回用量；同一 Composition/Object 的当前复用指针指向最新固定结果，普通恢复和原生内容修订不重新生成。明确重生成由 `produce_video.params.regenerate_media=true` 与新 Run 身份共同表达，不被相同来源 digest 吞掉；同一 Run 已有固定结果后的重试仍读同一执行清单。

Generator 的内部画面只在声明的参数、源程序或模型请求层面可修改，修改后须重新生产；不会自动获得文字/路径等原生对象的逐项可编辑性。最终 video-spec 把固定结果编译为普通 muted video 或静态 image 与合成属性，不含生成任务、程序、prompt 或模型调用。能保留来源不保证第三方模型再次生成完全相同的像素，固定结果本身才是可靠复用依据。

### 4.4 Transition

```text
Transition
├── transition_id
├── from_clip_id / to_clip_id
├── kind
├── duration
├── alignment
└── easing / params
```

Transition 属于同一 Track 上相邻 Clips 的编辑关系；单 Object 的 fade、slide、zoom 仍是 Animation。当前首个消费者为 crossfade + center：同轨相邻、全画幅 cover、无外部视觉 transform/opacity 动画的不透明固定 image/web/video；不移动切点或总长。编译围绕切点扩展两侧覆盖窗，视频使用真实前后 source handles，余量不足明确冲突；VideoObject 内原声同时交叉淡化，独立文字和音乐不连带。单独关联 AudioClip 的转场淡化、透明层及其他转场仍未声明支持，不做转场画廊。

## 5. Animation 与 TextPart

### 5.1 统一属性动画

```text
Animation
├── animation_id
├── target_object_id
├── property
└── keyframes[{ at, value, easing }]
```

Animation 存在所属 Clip 内并随 Clip 移动、复制和删除；target 必须指向该 Clip 内的 Object 或其派生 TextPart，不允许悬空引用其他 Clip。

| 用户效果 | 属性 |
|---|---|
| fade in / fade out | `opacity` |
| zoom in / zoom out / push / pull | `transform.scale` |
| rotate | `transform.rotation` |
| slide in from / slide out to | `transform.position` |
| 音量淡入淡出 | `audio.gain` |
| 路径描画 / 手绘下划线 | `path.reveal`（仅 ShapeObject.path，0→1） |
| 网页推近与取景运动 | WebObject 的结构化取景/transform 属性 |

基础是**关键帧 + 每段 easing**，不是单一贝塞尔：

- `linear`、`cubic-bezier`、`hold` 是基础枚举；easing 归前一关键帧到后一关键帧的插值段，hold 保持前值直到后一关键帧时跳变，不等于整段都瞬时完成；`text.color` / `text.stroke_color` 只支持 hold，未声明 easing 时默认 hold，显式其他插值仍拒绝；
- 多段关键帧表达“先变大、迅速回缩一点、再稳定”等 overshoot；
- 现有 spring 行为可先作为受支持 easing 或确定性烘焙输入保留，不在首批强行重写；
- AnimationPreset 只在实例化时展开为属性和关键帧，Renderer 不查 Preset 注册表。

插值求值还须冻结首关键帧之前、末关键帧之后与 Clip 边界的行为，重复时间键与非法目标/属性明确拒绝；按 §6.5 的共享 fixtures 对照 Preview/Render。首批只提供实际使用的属性与 easing，不预建通用动画编辑器。

Effect 描述模糊、颜色等处理；Animation 描述属性随时间如何变化。两者可组合，但不合并概念。

### 5.2 TextObject 与派生 TextPart

TextObject 是 VisualObject，整块文字与视频、图片共享 transform/opacity/animation。

```text
TextObject
└── TextPart[]            由当前文本与排版确定性派生
    ├── part_id
    ├── kind = line | word | grapheme | span
    ├── text_range
    └── layout_range
```

- TextPart 可被 Animation 定点或按 stagger 批量展开；逐字动画不需要逐字独立 Track。
- 完整 TextObject 一次排版，保留 grapheme、字距、换行和文本编辑语义。
- TextPart 默认不独立持久化内容，不成为独立 Clip。
- 只有用户需要独立位置、独立内容或长期单独编辑时，才通过 `detach_text_parts` 提升为独立 TextObject/TextClip。
- 文本变更后重新派生；无法可靠映射的旧动画明确报冲突，不静默套到错误字符。
- 首批实现当前 MG 所需 line/word/grapheme 与 stagger，不做每字符自由编辑器。

## 6. 时间、FPS、BPM 与音频

### 6.1 三个时间域

| 时间域 | 使用位置 |
|---|---|
| **Output time** | Scene.range、Clip.range、Transition |
| **Source time** | 视频、音频、网页动态素材的 source_range 与 BeatGrid |
| **Clip-local time** | Animation keyframes；随 Clip 移动 |

同名字段不得跨时间域换义。Clip 在输出时间移动时，源区间不变、内部动画随动；Scene 移动只带动明确归属的 Clips。

有时间轴的源素材还须明确源窗到输出窗的播放映射。默认 1×；源不足不能静默循环、冻结末帧、拉伸或截断。非 1× 仅在有显式参数且 adapter 支持时开放，不支持即冲突；本轮不要求实现通用变速引擎。旁白有界适配按 §6.4 的独立制作政策处理，不改变已审阅切点。

### 6.2 时间表示与帧

- 采用 OTIO 风格 `RationalTime` / `TimeRange` 思想；实现使用整数 ticks + rate，不以裸 float 秒作为核心真相。
- `settings.fps` 是有理数，支持 24、25、30、30000/1001、60；当前 30fps 无损映射。
- `settings.timebase` 与 fps 分家；Timecode 只是显示格式，不另存第二时间。
- 帧号、总帧数和 Renderer 所需整数帧由唯一量化座推导，Python/TS/替代 Renderer 共用 golden fixtures。
- 当前 120s 等限制先作为制作政策保留，不写成永久 schema 限制。
- `sample_rate`、声道与音频格式属于 settings/spec，不由视频 fps 代替。

### 6.3 BPM 与 BeatGrid

- `bpm` 是音乐素材的名义速度，可空；BeatGrid 是实际分析出的源时间节拍，可空。
- 音乐 Clip 的 source_range 决定 BeatGrid 如何映射到输出时间。
- 有真实 BeatGrid 时优先吸附真实节拍；只有 BPM 时才按均匀拍长推导。
- snap 后统一量化到输出时间/帧；不得由 API 与 Renderer 各自 round。当前 snap_cut 读取该版本音乐 SourceSnapshot.meta.beat_grid，将源时间节拍经音乐 source_range 映射到输出时间，在显式容差内吸附所选相邻切点；BPM 仅在无真实 beats 时按均匀拍长推导，无两者则明确不吸附。总长、独立文字和音乐不自动 ripple。
- 没有音乐不伪造 BPM；BPM 不代替 fps，也不自动改变所有 Object 动画。
- 本地 Music 的试听比较经 `show_music_candidates` 只呈现真实候选，后续普通消息的序号选择经 `select_music` 解算持久化成员；应用时由 prepare 冻结 Music 字节，再由 `revise_video.add_audio(role="music")` 形成新版本。BGM 与 SFX 都是原生 AudioObject Clip，但分别位于 music/effect 轨；候选与选曲本身不产生制作意图。

### 6.4 旁白、字幕与固定切点

旁白有两种合法时序来源，最后都进入同一 CompositionVersion、Run、video-spec 与交付链：

- **固定切点 MG**：保留当前设计先审阅 Scene/Clip 切点、制作时 TTS 在显式政策的 1.0–1.35× 有界语速内适配的方式；每条 SpeechClip 至多两次付费合成、`fit_margin=1.08`，`max_tts_characters` 按剩余需求报价并钉入授权 Run。原速原件可跨 Chat 复用，加速适配只属当前 Run；已提交但结果未确认的供应商请求不自动重放，已固定音频的字幕下载可单独恢复。不得借用其他 Scene 帧数、移动切点、改旁白原文、静默截断或交付缺失旁白的成片。
- **源对齐知识讲解**：先确定最终讲稿与最终音频，再完成完整句/词对齐和 Agent 语义标注，最后生成依赖这些事实的 Scene、Clip 与 Animation。已有录音直接使用其固定 AUDIO SourceSnapshot；TTS 先经现有报价、制作意图、守卫线和 VideoNarration 未知结果保护准备原速音频，再冻结为音频快照。最终分镜保存后，produce 不重新合成、不重新对齐，也不靠限速改变已审阅的词锚。

字幕可由旁白派生，记录源 SpeechObject、文本版本与对齐 provenance；用户手改后标记独立编辑，不再被旁白重生成静默覆盖。字幕同步刷新是显式编辑。视频与其原声分离到视觉/音频 Clip 时记录关联；split/trim/move 明确同步范围，不能只移动画面留下旧音轨，也不能强制连带用户已解除关联的声音。

#### 6.4.1 NarrationAlignment：完整句/词对齐、语义与词锚

`NarrationAlignment` 是最终音频与精确讲稿的派生事实，不是作品根，也不是可独立修改的 timestamps 文件。每行属于一个 owner，引用固定 `audio_snapshot_id`，保存 `text_digest`、`audio_digest`、`algorithm`、`normalization_version`、`provider/model`、`source_timebase`、`timing_digest`、`content_digest`、lease/error 与状态。状态使用 String 列：`PENDING → PROCESSING → ALIGNED → READY`，确定性失败进入 `FAILED`；worker 只认领 PENDING，Agent 只能在 ALIGNED 填语义，CompositionVersion 只能引用 READY 的 `alignment_id + content_digest`。

完整 payload 至少保留以下结构；字段使用整数源时间 ticks，文本范围是对原始讲稿的半开 Unicode scalar offsets，禁止裸 float 秒成为下游真相：

```text
NarrationAlignment.payload
├── source_timebase
├── duration_ticks
└── sentences[]
    ├── sentence_id
    ├── text                       原始句子，不是 ASR 改写稿
    ├── text_start / text_end
    ├── start_tick / end_tick
    ├── match                      直接锚点覆盖率，不是置信度或实测误差
    ├── status                     aligned | review_required
    ├── words[]
    │   ├── word_id
    │   ├── text                   原始讲稿 token
    │   ├── text_start / text_end
    │   ├── start_tick / end_tick
    │   └── timing                 anchored | interpolated
    └── semantics                  Agent 在 ALIGNED 状态填写
        ├── role                   definition | process | comparison | evidence | example | summary | transition
        ├── weight                 main | sub
        ├── entities[]
        ├── needs[]                native_text | diagram | real_media | data | generator
        └── emphasis_word_ids[]    必须引用本句真实 word_id
```

CJK 可以逐字成 token，连续 Latin/digit run 可以整词成 token；标点与空白仍由原始句子和 text ranges 完整保留，任何文本位置都必须能确定性映射到相邻发声 token 或明确的零时长边界。归一化只用于匹配，永不覆盖原始讲稿。插值必须显式可见；低覆盖、零全局锚点、文本/audio digest 漂移、非单调时间或越出真实音频时长必须进入 review_required 或 FAILED，不能静默折叠成零时长后继续制作。

语义由 Agent 填写并由服务端整批校验，LLM 不直接写数据库。`emphasis_word_ids` 只指出值得视觉强调的 token，不预先决定具体动画；main/sub 表达“允许引入新视觉主角/优先改变已有元素”的编辑意图。语义修订不得改写文本或时间；任一句仍为 review_required 就不得 READY，不能用用户确认或语义标注补造缺失时间。READY 后整行不可变，后续文本、音频或算法变化必须创建新行。

`SpeechObject` 增加可空 `alignment={alignment_id, content_digest}`；源对齐 SpeechClip 同时绑定真实音频 SourceSnapshot/source_range。`Animation` 增加可空 `NarrationAnchor`，保存 alignment 引用及 sentence/word/text_range 来源。设计时由服务端把锚点解算成 Clip-local 整数 keyframes，video-spec 只携带最终帧值；renderer 不读取 NarrationAlignment。锚点解算必须支持指定 sentence、word_id 或 text_range + occurrence，缺失、歧义、跨句或超窗明确报错，禁止“找不到就返回 0”。

讲稿、音频或 source_range 改变会使旧对齐/锚点失效：模型通过 `revise_video` 提交完整所属 Speech Clip；源对齐 Speech 的文本或媒体变化先准备新 NarrationAlignment，再生成新 CompositionVersion 并重解算受影响动画，未点名的对象保持 id 与内容。确定性时间平移按现有时间映射移动锚点 provenance；不支持保持语义的 Speech time_map/rate 继续失败闭。

`timestamps`、`timing`、`beats` 和语义表都可以从 READY NarrationAlignment + CompositionVersion 生成只读 DTO、调试 JSON 或交付导出，**这些内容必须完整保留，但不获得第二份独立编辑权**。唯一可编辑讲稿仍是 SpeechObject.text，唯一创作结构仍是 CompositionVersion。

### 6.5 A 阶段必须冻结的求值合同

A 的最小纵向样片开工前，给出纯函数与 golden fixtures，冻结：时间范围 `[start, end)`、各时间域单位、量化/舍入与时长换算、视觉 Track order 方向及唯一性。同轨非转场重叠首版拒绝；需要叠放时使用不同 Track。

Transition 明确输出覆盖窗、前后 source handles 与余量不足行为；首版无足够余量就拒绝，不偷改时长。当前 split_clip/trim_clip 通过唯一内容写口保留选定输出子区间：固定媒体源窗按同一帧映射同步，VideoObject 内原声一起移动；显式 linked_group_id 的固定媒体随同拆分/裁短，独立 Clip 不连带。左段保留身份，右段重映射 clip/object/animation 与内部关联；局部动画（含 TextPart stagger）按既有帧求值采样并重新定基，保持可见帧值，动画可继续修改。无 ripple；待生产 Speech 和 Generator 内部媒体切分不在该消费者范围。同一 Object/属性的重叠动画首版拒绝，TextPart 与父对象的变换按声明的层级组合。

字体文件与 digest、文本切分、grapheme/word/line 寻址及排版实现版本必须可追溯。Preview/Render 用相同资源与一致求值；不同实现通过中文、英文、换行和 Emoji fixtures 对照，不能只验证时间插值。

### 6.6 编辑目标、时间变换与联动

Composition 的持续修订使用一套与 Skill、模板和具体影片无关的时间编辑代数。自然语言中的“整片改为 30 秒”“第三章缩短后前移后续内容”“删除这一幕并收拢”都编译为目标集合上的通用操作，不新增 `retime_composition`、官网片专用分支或按目标秒数写死的操作。

**时间线总长**永远是所有 Tracks、所有 Clips 的 `max(clip.range.end)`，包括 `scene_id=null` 的跨幕音乐和其他全局 Clip；不读取 Skill 的目标时长、Scene 的最后结束时间或 Clip 数组顺序作为总长。

**编辑目标 `target`** 可解算为 Clip、Scene、Track、显式选择集或整个 Timeline。服务端把目标解析为本版稳定实体 id；“当前一幕”“后续内容”必须有结构边界，不能用时间相交猜测归属，也不能用 Chat 最新产物代替目标。整个 Timeline 只是最大目标集合，不拥有另一套编辑器。

**基础时间操作**共享同一目标与联动解析：

| 操作 | 统一语义 |
|---|---|
| `move` | 平移输出时间；源窗不变，Clip-local 动画随动 |
| `trim` | 保留输出子区间；固定媒体按显式 source policy 映射，默认不 ripple |
| `split` | 在输出切点拆分；按 §4.2 保留/重映射身份与关联 |
| `delete` | 删除目标；`lift` 留空与 `ripple` 收拢必须显式区分 |
| `time_map` | 对目标输出范围应用 `t′ = a × t + b`（`a > 0`）；Transition duration 与 TextPart stagger 按 `a` 缩放，Clip-local keyframe 在所属 Clip 的输出网格量化后重新定基，不叠加输出平移 `b` |
| `rate` | 改变动态媒体的 Source→Output 播放映射；与输出时间映射分开，仅在显式参数和 adapter 能力同时存在时开放 |

`time_map` 是通用时间变换，不等于媒体变速。静态网页、Text/Image/Shape 等原生内容保持 Object、布局、属性值和来源不变，只改时间坐标；动画 keyframe 的 `at` 先随所属 Clip 映射到输出网格，量化后减去新 Clip start，使局部 0 与末尾 keyframe 分别对齐 0 和新 Clip 时长，`b` 不成为局部延迟；TextPart stagger 只按 `a` 更新，`value` 不按属性名特判。动态媒体必须逐 Clip 明确 source policy：1× 裁取、显式 `rate`，或不支持即拒绝。Music 等跨幕 AudioClip 也在目标集合内，不能因不属于 Scene 被遗漏。Speech、待生产 Generator 和其他不能保持已审阅语义的内容失败闭，不静默截断、变速或重新创作。确定性媒体能力拒绝与可修复参数错误分型：前者零新版、零制作并结束本回合修订循环，回复真实版本与时长。

**联动策略与基础操作正交**：

- `ripple=none|forward`：是否把操作边界之后的下游内容同步平移；默认不隐式 ripple。下游范围按 Track/Clip 结构确定，遇到重叠、Transition、跨组关联或无法保持约束时整批拒绝，不建设磁吸时间线。forward 只平移下游，不拉伸保留 Scene、延长结尾或重裁全局音频来消除音乐-only 尾部；用户点名的范围已保存后即停止，额外时间或美学调整等下一条用户消息。
- 关联只来自 `scene_id`、显式 `linked_group_id` 和已登记的声画关系；时间相交本身不构成关联。
- Scene 被编辑或其成员被整体变换时，Scene.range 与成员使用同一时间映射；Scene 不拥有第二套局部时间线。
- 所有 ops 先在同一候选版本完成映射，再由唯一量化座统一取整，避免逐 Clip 累计舍入误差。

每次修订仍只经 `revise_video → apply_composition_edits` 原子产生一个 CompositionVersion；保留未改实体 id、SourceSnapshot 与 `skill_provenance`，不调用 Director redraft。任一目标或媒体不支持时零新版、零部分写入。通用操作不等于承诺所有媒体能力；操作语义共享，Object/adapter 的能力矩阵独立裁决。

## 7. Skill、VideoTemplate、Preset、PromptTemplate

### 7.1 四层职责

- **PromptTemplate**：Home/ composer 的可见预填；UI 不需要出现“配方”一词，不自动发送或执行。
- **VideoTemplate**：Scene/Track/Clip/Object/Animation 的参数化结构、内容槽位、有界 repeat 与变体。
- **Preset**：局部动画、字幕、文字样式或音频参数。
- **Skill**：版本化创作包，组合 instructions、VideoTemplate、Presets、输入要求、能力要求与示例。

VideoTemplate/Preset 实例化后展开进 CompositionVersion；之后修改 Skill 或 Template 不暗中改变旧作品，Renderer 也不依赖 Skill 仍存在。

launch-film 已是内置 Skill 的首个完整范式：SKILL.md 保存创作方法，video-template.json 保存固定 Scene/Track/Clip 结构，代码展开命名 Preset，音乐以固定 AudioClip 进入版本。固定程序组件不是所有 Skill 的必备项，只在原生对象不足以表达画面时引用；Preset 也不要求独立文件。Skill 可声明默认 SFX cue 与固定音频资产，cue 经原生 AudioClip 落轨并随所属 Scene/Clip 参与时间联动；Gallery 风格的完整声音是上架必要条件，用户明确关闭声音仍不得被默认值重开。

当前建立十六个分类代表 Preset：文字与字幕、标注与信息结构、UI 与图文编排、开场与收尾。它们覆盖高频可参数化语法，不追求一次复刻外部镜头库。Camera/Scene/Clip 运镜与转场仍由镜头方法表达，真实网页状态由 CapturePlan 提供，媒体变速/定格由通用时间内核表达，自由 3D、复杂形变与内容特定画面才交给 `remotion-project`；不得为了组件数量把这些不同能力压成同一种运行时。

### 7.2 launch-film 只是内置 Skill

目标包：

```text
launch-film/
├── SKILL.md
│   ├── 章节、hook、reveal、旁白与命名工艺
│   └── 引用与事实纪律中的创作部分
└── video-template.json
    ├── cold open / hero / home 静态定场卡
    ├── 3–5 章有界 repeat
    ├── divider / chapter walk / optional plate
    ├── reveal / proof / end
    ├── Track、Clip、Object 与 Animation 结构
    └── 内容、网页视图与时间策略槽位
```

capture、SSRF、citation resolver、grounding、素材权限、容量、报价、授权、TTS、存储、渲染与失败降级仍属代码能力。Skill 可调用已注册 binder 的能力，不能提交脚本修改它们。

无 Skill 的自由 MG 由 `design_video` 逐步写入服务端工作草稿；有 Skill 的官网片由同一工具按方法创作。固定 VideoTemplate 由代码确定性展开到同一草稿，模型只填创作槽。后续版本、CRUD、Run、Render 和交付完全同链。

### 7.3 外部 Skill 持久化与加载

- 当前产品边界：内置包随应用部署，由内部注册和使用，不开放用户自助安装。外部 SkillVersion 链只用于内部登记、测试与历史 provenance，不承诺 Claude Code / Codex 插件运行时兼容，也不把用户导入列为当前验收欠账。
- 用户 Skill 按 owner 隔离，SkillVersion 不可变；保存原始 instructions、references、声明输入、能力报告、Strict/Adaptive policy 与 `source_uri/source_revision/source_hash`。原始外部包无需改名或内容改写即可导入；旧作品不随后续 SkillVersion 改变。
- **Strict** 只固定导入审阅时明确声明的必要输入、场景数、时长与 Generator producer；这些确定性字段无法满足时给出具体冲突。参考 demo 的词数、示例文案和坐标不自动成为 Strict 产品规则。**Adaptive** 只允许在声明边界内由 Agent 适配，实际故事板、程序与参数随结果呈现。这里不发明通用约束求解器、第二套模板 DSL 或通用插件平台。
- 唯一创作链为：SkillVersion → 有界选择 instructions/references 并作为不可信创作输入注入现有设计/Generator Agent → 普通原生编辑或受控 Generator 来源 → 预览与 `revise_video` 修订 → `apply_composition_edits` → 固定生产与 Output。不得新增第二意图入口、第二作品内容写口或第二生产链。
- 外部 `scripts/` 不自动执行，`allowed-tools` 只是未授权依赖声明。外部内容不能覆盖系统、grounding、素材权限、报价和授权；Generator 仍无业务数据库、调度、计费、任意网络或任意文件能力。
- 渐进读取预算是整个 SkillPackageSession 的共享上限：24 次包读取、16 次 Director 生成（初稿、schema repair、grounding repair 合计）、240 秒 Director 创作墙钟（前置素材采集与 CapturePlan 不计入，嵌套修复不重置）、240k 文本字符、24 个 demo、4 个预览媒体与 16MiB 媒体字节；嵌套修复不刷新计数，缓存媒体不重复计费，媒体在 I/O 前做容量预检。当前绑定 SkillVersion 的 PNG/JPEG/WebP 预览可返回服务端推导的 `{path,snapshot_id,snapshot_digest,content_type}`；Director 只能逐字段回引该身份。设计写口再次读取并校验真实字节，以 owner + SkillVersion/路径/digest 锚注册 asset-less 图片 SourceSnapshot，再发出普通 `bind_source`；跨 owner、跨版本、路径/digest/MIME 替换或任意 owner 快照都不能成为组件资源。
- 首版不做市场、团队共享、多 Skill 自由叠加，也不从自己的 CompositionVersion 形成或保存 Skill。固定源码适配器只作合同测试夹具，不是产品加载实现；产品加载链不得按包名、镜头名、仓库 URL、commit 或 digest 分支。
- C 的真实外部消费者为 [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)：固定源 commit，原始包完成通用导入与 SkillVersion 持久化，再选一个未参与固定适配的 held-out 镜头，用新产品文案经真实 Agent 创作、预览、修订与 run-less 精确版本 Output 验证。可只支持明确声明的镜头与能力范围，不声称兼容整个镜头库；正式 Chat/Run 用户旅程归 C2/C5 验收。

### 7.4 Skill 调用与 Home 入口

- `/` 打开的 Skill picker 同时接纳平台内置 Skill 与当前用户可访问的外部 SkillVersion。内置 Skill 的 picker/chip 显示本地化用户任务名——产品宣传视频制作、口播动效视频制作、文字动画视频制作、知识讲解视频制作及对应英文——不显示 `launch-film` 等内部包名；内部 skill id、目录和版本引用保持不变。选中后形成可见 Skill chip，并随消息携带统一的 Skill 引用：内置 Skill 由注册表 id + 版本解算，用户 Skill 由不可变 SkillVersion id 解算；不能使用隐藏 recipe_id 或另一套发射载荷。
- 文字动画首稿支持 Scene 内独立时间窗、字号/字重、位置与入场的多个 text_beats，各自展开为原生 TextObject/Clip；逐字保留来源顺序，校验时间窗、画布范围与基本阅读时长，旧单文字块仍兼容。首稿使用 Director 选定的原生文字/图形、配色、对齐与运动；不按 Skill 身份覆盖为固定深色舞台、第二幕关键词染色、末幕打字机或固定点击音。Preset 只在用户明确选择时展开，不自动混用 word/grapheme 层级。段落数不等于固定 Scene 数；既有版本保持不可变，新设计按当前方法生成。
- 每个作品至多绑定一个 Skill 版本。保存版保留不可变 Skill 引用、实际来源、声明 Generator 资源和用户明确约束的 provenance；完整重设计与普通修订继承出生血缘，历史空值不伪造回填。包内方法、幕纲与镜头卡只是按需读取的创作证据，不是另一套模型提交协议；Prompt 不复制包注册表。
- Home 的视频 Skill 卡是同一入口的可选快捷形态：点击形成 Skill chip + 可编辑 prompt，与手动 `/任务名 + prompt` 使用完全相同的 `POST /chat` 载荷。卡片不自动发送、上传素材、建项目或 Start，也不产生制作意图。**当前开发/手测货架直接呈现产品宣传、口播动效、文字动画、知识讲解四个主 Tab**：主 Tab 使用 `skills.builtin.<id>.shortName`，完整 picker/chip 任务名不变；每类固定两个典型应用子 Tab，依次是网站/产品宣传与课程/服务宣传、观点口播与课程/讲座预告、观点文字片与金句/公告短片、概念讲解与研究/报告解读。暂无真实样片的应用显示统一 en/zh 空态，不用旧 Film、复用片或其他素材填充。产品宣传混合四种输入并使用真实网页状态；口播动效包装真人原片与原生社交标题；文字动画使用内容驱动的原生文字/图形与可选 Preset；知识讲解可以只输入知识文字稿，由 READY NarrationAlignment、原生组件和解释知识的 Generator 共同驱动，不要求真实证据素材。
- 用户不选 Skill 时，LLM 可从普通语言推断四类任务、素材需求和通用设计方向，不得强制先问产品分类；这种推断不冒充固定 Skill/风格绑定。只有消息携带具体 Skill reference 才从该 Skill 的模板、输入要求与固定起点开始。固定风格必须经 Skill 确定性绑定，prompt 只承载用户内容与要求。
- **正式公开 Gallery 上架**只接受对应 Skill 已走完真实「预填 → 首稿 → 授权 → 制作 → 交付 → 修订」的样片；实际文件必须包含声明的音乐/SFX/旁白，完整动态观看和实际试听通过。当前 Home 开发/手测入口与五个诚实空态不等于这道公开验收已通过。Home 自动静音播放不改变成片音轨事实，占位、静音或仅 run-less 的领域样片不能证明可售能力。四类逐张验收，不以其中一类通过代替其余三类。
- Chat 内组件选择复用 Candidate Surface：`show_video_presets` 展示 2–4 个真实动态 `video_preset_set`，`VideoPresetCandidateSurface` 只负责播放与呈现；用户下一轮用普通语言选择，`select_video_preset` 只记录 selection，不写版本/Run。应用选择时由模型经自由路径完整实体或内置 promo 的 `apply_preset(clip_id, preset_id)` 写出实际创作结果，不把 candidate set/member 当作编辑载荷；不跳外部 Gallery、不复制内部镜头名、不新增候选查询端点。浏览 Preset 是可选比较，不是制作前置。
- 非 Skill Recipe 继续使用 PromptTemplate；Recipe 不进入 @ picker，也不借 Skill 之名获得隐藏执行参数。视频 Skill chip 是独立实体，不把既有 Recipe 改名成 Skill。
- 自然语言明确点名时只解算唯一可访问 Skill，歧义必须询问。一次创作至多绑定一个显式 Skill，普通 Chat 未显式选择时仍可按现有设计路由进行通用创作。
- Strict/Adaptive 只约束首版设计。CompositionVersion 出生后，后续时间、内容与 Generator 修订统一走 `revise_video`，不重新执行 Skill；`skill_provenance` 仅保留来源血缘。制作完成由既有 delivery 正文 + Output 卡收口，不自动打开 Workbench/Inspector 或固定追加下一步建议；后续创作与修订动作仍回到普通 Chat。

## 8. Chat → CompositionVersion → Run → video-spec

### 8.1 新管线

```text
/任务名 + prompt + materials
→ 唯一 POST /chat
→ 解算 @asset/@output 与目标 Composition；固定 SkillVersion 与 SourceSnapshots
→ 同一普通 Chat 创作循环按需读取 Skill、采集并复用成功事实
→ design_video：共用 scene_plan / 逐幕 scene 或声明式完整实体写入；服务端展开原生 Composition，并保留可恢复工作草稿
→ save=true：完整 validator + apply_composition_edits
→ 一个不可变 CompositionVersion
→ Storyboard 完整呈现 + 按需精确版本局部 Scrub/代表帧（永不整片预览）
→ 用户反馈后局部修订，或按既有制作意图 / 报价 / 授权 / Start
→ produce_video 钉 composition_id + composition_version_id + content_digest
→ 固定执行输入，准备 Generator 媒体/旁白等派生素材（按已实现能力，无需时跳过）
→ 编译最终 video-spec，固化执行 manifest / execution_digest
→ Renderer 黑盒
→ Output(type=video)
```

已保存版本的定向修订走 `revise_video`：自由路径提交完整 Scene/Track/Clip/Transition 写入或稳定 id 删除，内置 promo 提交一个封闭 action，均产生一个新 CompositionVersion；开放重稿从当前版本建立工作草稿。新版本继承基版本的出生 `skill_provenance`，内容修订不能抹掉实例化来源。只有当前消息具备制作意图时才进入后续制作，普通修订不自动重制。

### 8.1.1 生成媒体与程序化画面的生产边界（draw-2d / remotion-project / image-generation 已接）

- 内容版本用 GeneratorObject 保存可审阅的程序或模型请求，语义见 §4.3.2。draw-2d 与隔离部署下的 remotion-project 共用“提出要求→有界代码创作→精确动态预览/代表帧→局部改程序→再预览”闭环。Generator 的代码与诊断只围绕目标 Clip，不与整片共享一份巨型 JSON；完成后的完整 Generator Clip 合并进工作草稿，重要原生文字、字幕和音频不随之烘焙失去身份。
- 预览与生产始终使用相同源码、完整画布、fps 与时间窗，并标明对应 program_digest；修改后不得沿用旧预览冒充新版。工作草稿保存为 CompositionVersion 后，可在正式 produce_video 前准备有界的本地程序预览并读取真实代表帧；模型媒体仍按授权与费用规则执行。预览失败只诊断对应 Generator，不要求重交其他 Scene/Track/Clip。
- 预览和纠错复用现有有界 agent/harness，冻结实际尝试次数、资源与费用上限；不新建开放式自主循环或通用 look 平台。运行器缺失、容量、超时、内存/临时空间、传输与缓存完整性错误不当作源码修复，也不降级成截图、静态图或短循环。首个程序消费者须给出可播放短预览或动态序列、执行诊断及 Agent 可读取的代表画面；模型无法看图时如实声明并接受用户视觉反馈。
- 生成输入须固定用户素材/参考、请求参数、供应商及模型版本（可获得时）、程序与依赖资源身份、尺寸/时长等输出约束；相关费用与授权进入既有 Run 机制。image-generation 的设计/修订只保存请求，报价按本次缺失图片数计算，授权制作才真实生成。供应商私有参数留在 provider 边界，不进入通用 VideoObject。
- 本地受控的程序生产与导入外部 Skill 脚本分开：外部 scripts/ 不因引入程序画面而获得执行权限。代码画面运行须隔离可用能力、依赖、时间/资源与外部访问；只围绕实际样例建立最小执行边界，不开发通用插件平台。
- 生成成功后将实际媒体、资源 digest 与请求/执行血缘固定在执行 manifest，编译为 renderer 可消费的资源；不得回写原不可变版本。后续版本只在来源 digest 与同一 Composition/Object 的固定执行结果匹配时复用；把既有结果当独立素材时，经正常内容写口显式绑定其快照。
- 准备/渲染重试复用已成功结果，不重新随机采样或更换模型/程序。用户明确重新生成属于新的制作请求与执行身份，若改变内容要求则先形成新内容版本；失败保持已有作品与成片，不伪造可交付结果。
- 程序化生产可以输出烘焙媒体，不把 React/Three.js/回调注入 video-spec。需要精确内部编辑的内容优先采用支持的原生图元；两条路径共享最终合成与交付，但不能声称编辑粒度等价。

### 8.1.2 创作循环、工作草稿、局部 Scrub 与条件工具

`/promo-video` 是部署方提供的宣传片入口，绑定本地安装的固定 Shotcraft 版本。发布目录为 `<MANAGED_SKILL_ROOT>/promo-video/<version>/`，当前目录版本由 `MANAGED_SKILL_VERSIONS` 选择，已绑定作品沿用自己的版本引用。通用包读取器消费上游方法、镜头卡、Gallery 变体及实际存在的本地预览；配乐经平台共享 Music 库准备与冻结。普通制作请求默认自主完成首稿分镜，分镜后的制作授权由宿主管理。

Composition 的统一同时覆盖创作入口与最终落库。普通视频创作复用现有 Chat 工具循环：确定性组装用户原话、确切 CompositionVersion、Project 公共资源及成功工具事实，按需读取绑定 Skill/预览、执行 CapturePlan 与准备规范资源。自由创作通过多次 `design_video` 写入同一个服务端工作草稿，每次只包含本次设置、来源或完整实体；内置 Promo 与其他无声明 Generator 的作品共用 `scene_plan` 和逐幕 `scene` 高层输入，由服务端展开原生 Composition。最终 `save=true` 只提交已存在的 `draft_ref`。Skill 不拥有强制多导演流水线；CapturePlan 是工具参数，Generator 工程是 Object 的生产来源，Storyboard 是版本读面，不另起作品数据层。

**固定 Skill、自由创作和 Generator 只在创作入口分工不同**：固定 VideoTemplate 由代码把模型填写的创作槽确定性展开为草稿；自由创作由模型逐 Scene/Track/Clip 写作；Generator 在目标 Clip 范围内进行有界代码创作与真实预览纠错。三者最后共用同一完整校验、CompositionVersion、修订和制作链。

工具注册与模型可见工具分开。现有 ToolLoop 每轮在真实世界状态刷新后投影当前必要工具：是否绑定 Skill、是否存在活动 draft_ref、是否有当前版本，以及当前明确素材是否已有准备好的快照。需要准备素材的首稿在冻结来源就绪后才开放当前阶段的 `design_video` schema；无草稿时不发送 revise/draft 修复 schema；有活动草稿时优先提供继续写入与保存；已有版本时才提供对应版本修订/预览；制作工具仍受制作意图、呈现与费用门约束。System 每轮按实际工具集投影对应规则，执行端继续独立校验权限和状态，隐藏工具不是安全边界。条件投影复用现有每轮 `round_tools` 接缝，不新增用户侧阶段机、第二套 Director 链或持久化 AuthoringSession。

绑定 Skill 的根方法在首次 Chat 模型请求前由现有 PackageReader 静态读取并注入；builtin promo 只预置当前创作所需的有界索引/方法。首轮普通模型先发言并调用必要的网页/素材准备，工具等待完成或失败后才进入下一轮。每轮刷新业务事实，默认只注入 base_ref、候选目标摘要、目标当前值和相关素材，不注入整份 Composition、Layout/Animation/Keyframe、完整被拒参数或无关工具 schema。修订失败只恢复高层 candidate 与世界事实；成功后旧参数退出投影，保留新 version_ref、真实 change_set 和紧凑 Storyboard。音乐库经 material_music_ids 冻结为 AUDIO Snapshot；Track role 可重复、同轨片段互斥、并发对象使用多轨。

公共资源来自既有业务表；过程事实、活动草稿与必要读取回执归既有 ConversationContext/Turn/Message 元数据，实际图像证据与文字 manifest 分开。成功资源不因后续作品校验失败消失；局部参数错误不抹掉此前有效草稿。规范资源由准备层交付，raw 只作血缘；引用按冻结来源标识确定性回填，不要求模型反复抄写原文。超限资源须明确 omitted，不以“共享”承诺无限 prompt。

实施与验收细节归 [Composition 创作循环与上下文收敛](tasks/composition-authoring-context-convergence.md) 和 [顺序创作合同](tasks/sequential-video-authoring.md)。每轮 system、工具和动态事实由真实阶段共同投影。计划形成前保留已读取的方法与来源；形成后保留简报、用户明确约束、幕纲、当前幕和精简来源引用，旧 Skill 长文与已送达的单幕观察退出当前 wire。折叠不得改变 ConversationContext 的持久化与草稿恢复，新工具结果必须先完整送达一次。`draft_present` 只消费保存结果和呈现事实；`version_edit` 只消费当前目标与版本事实。保存读面从实际 Tracks/Clips 报告音乐有无，未落轨的搜索或选曲计划不得进入分镜、确认或交付表述。制作前完整动态预览已撤除。

### 8.2 Graph / Run / Node 的保留与解耦

**Graph 是执行图，不是视频时间线。**Scene、Track、Clip、TextPart 不逐个成为 graph node。

| 层 | 保留的职责 | 新边界 |
|---|---|---|
| Chat tools | 理解意图、设计、修订、呈现、授权对话 | `design_video` / `revise_video` 只经 `apply_composition_edits` 写版本 |
| Composition editing | 作品内容、版本、digest、素材绑定 | 不依赖 graph node 的位置、rank 或 Canvas 可见性 |
| Graph | 持久执行/产品图与可选投影 | `apply_wiring_ops` 仍是唯一图写口；节点只保存版本引用与执行状态，不复制整份 CompositionVersion |
| RunPlan / worker | 拓扑、估价、队列、重试、fencing、计量 | `produce_video` 是通用执行节点；`run.context.version_ref` 钉 Composition/版本/content_digest 与执行输入摘要；准备完成再固化 execution_digest，按 §2.4 分阶段复核 |
| Output / render queue | 交付产物、render_status、文件、probe | Output 钉 CompositionVersion；render_spec 为 video-spec |
| Run review / delivery | 核对确认版、实扣与真实交付 | 对照 CompositionVersion 与 Output provenance，不比较 Canvas 状态 |

`produce_video` 只接受已存在且身份匹配的 CompositionVersion；缺失、引用身份失配或素材漂移时失败，**不得在 production 内临时调用 Director 重新设计**。若保留无人值守首稿能力，必须走显式 design 操作，不能藏在 produce 的 fallback 里。

首版可继续使用单个 `produce_video` 执行节点；是否拆 prepare/narrate/assemble 由真实恢复与计量需求决定，不为图形美观预拆宏链。

已有提案/草稿图在修订时通过现有计划修订机器更新版本引用；已经开始的 Run 永不追随后台新版本。Canvas/FlowView 可保留为 Graph 的一种投影，也可以退役；两种情况下 CompositionVersion、Run 和 Output 都成立。

### 8.3 Prompt 与 validator 分座

- Chat prompt：对话、工具选择、呈现和授权规则。
- Skill instructions：创作方法与风格判断。
- Director schema：当前支持的创意内容/槽位、精确脚本与 `visual_description`；`video/draw_2d_director` 承载 draw-2d 的受控来源/参数，`video/remotion_project_director` 承载 1–6 幕完整作品的受控多文件 TSX、固定图片与原生旁白拆分，`video/aligned_narration_director` 在真实对齐时间窗内选择至多一个 draw-2d 或 remotion-project 主视觉，`video/generated_image_director` 承载首个 image-generation 背景请求与独立标题。模板槽位不是永久创作边界，散文字段 null 读容忍；修码反馈只携带当前源码与世界诊断，不携带 assistant 言语草稿。
- VideoTemplate：声明式结构，不携带 assistant 言语草稿。
- Project validator：身份、来源、grounding、时间、布局、容量和完整草稿闭包。
- Director 结构修正只暴露报错的顶层字段；代码保留已通过字段、组装修正结果并再次完整校验，不要求模型重写整份分镜。可选快捷文字/图层的 null 或空字符串按空数组读取，实际文字与素材身份不据此补造。原生文字层按自己的入场与阅读时间窗校验，不把所有层再合并成整幕段落重复计时；快捷文字按整幕校验。
- 只有用户明确要求逐字或精确文案时才投影 `verbatim_copy`；普通简报不由模型自造全局逐字限制。确有逐字要求时保持全文与顺序；否则允许忠实翻译或概括。改编文案以 `copy_evidence` 关联实际屏幕文字、已绑定 snapshot_id 与冻结原文 quote，引用来源随版本绑定、对应关系写入版本 provenance；代码校验来源身份、引文存在和屏幕文字对应，不用原文子串匹配判断翻译，也不宣称已完成语义忠实度自动审查。产品事实、数字、单位与交互结果仍不得编造。一次语义校验汇总时间、来源、动画、文案证据、镜头实现及显式要求的全部诊断，再进入唯一修正机会。
- `scene_count / target_seconds / aspect / background` 仅在用户明确固定时进入硬约束。首稿 wire 只开放这些已固定字段并限定为实际值；续接和保存由服务端从当前用户原话、user-stated Brief 或草稿的 `user_constraints` 恢复，绕开精简 wire 的提交仍由执行门拒绝。未指定时使用服务端默认值或正常创作自由度，助手自己的提案和默认画幅不升级为用户要求。无固定总时长、无旁白的新宣传片首稿由代码按阅读下限单调扩展原生时间边界，所有后续入场/离场同步顺延，保留原有先后和重叠关系；不改内容与固定媒体源窗，不对已保存设计自动重定时，30 秒单幕与 118 秒总容量保持校验。
- Run gate：呈现、版本、制作意图、费用与执行身份。
- video-spec schema：Renderer 输入合法性与能力边界。

一部法只在一个座位说；工具观察只返回世界事实与指回规则座位，不携带可转述的 assistant 文案。

### 8.4 当前代码接缝

- `design_video` / `revise_video` 在 plan/propose 两路共用 `chat/video_turn_seats.py` 与 `editing/service.py`；内容只经 `apply_composition_edits`。
- `GET /chat/video/versions/{id}/storyboard` 同时提供 canonical Storyboard、完整 Clip 读面与按内容需要的精确版本预览；不存在第二作品读面或平行预览路由。
- 呈现回执住 `pending_brief.video_presentation`，Run 钉 `run.context.version_ref`；`produce_video` 只消费已呈现、获授权的确切 CompositionVersion，不在生产内重设计。
- 最小 Scrub 的 Apply 是确定性完整 Clip 修订，不经 POST /chat，不调 LLM，不创建 Run 或 Output。
- Graph/Run/Node、队列、fencing、计费、Output render ownership、probe 与终态写继续共享；Clip 当前能力不因新视频链删除。

### 8.5 基于画面证据的内容质量检查（静帧与确定性信号检查已接，完整检查待扩）

目标是让 Agent 根据真实画面发现问题、修订并复核。`render_probe` 保留媒体文件硬检查；内容 reviewer 归 `tools/video`，复用既有 Agent harness；`run_review.py` 保持事实聚合。无需先建立通用质量平台或新的审批流程。

当前 `review_video` 只接受确切 delivered Output id，校验其完成文件、执行 spec 与版本血缘后直接解码该 Output 的媒体；默认按执行场景抽少量静帧，`at_seconds` 存在时只抽这些指定复核点，`motion_scene_id` 存在时只对该 Output 执行 spec 中的一个确切 Scene 抽取有界有序离散帧，且与 `at_seconds` 互斥。动作采样覆盖该 Scene 首帧与最后可执行帧，约 2fps、最多 16 张，不用重复帧凑数。报告写入该 Output 的 `quality.content_review`，记录真实帧号/时间、内容寻址帧证据、实际场景窗口/采样间隔、`motion_reviewed_scene_ids`、检查范围与限制；finding 必须引用实际解码帧，只有该帧 active facts 能证明时才保留 clip/object 引用。无问题允许空 findings，可观察问题与审美建议分开；有意静止阅读段和重复/平坦帧仍只是候选，不自动判成缺陷。`output-checks-v1` 同时记录采样帧平坦/重复候选，并完整解码首个音频流测量 RMS、峰值与削波比例；候选不直接判成缺陷，只有执行 spec 明确期待声音时才把静音/低电平列为问题。音频检查覆盖流存在与 PCM 信号，不冒充主观听感。报告复用须匹配确切 Output、实际视频 digest、检查要求、当前报告/检查器版本和显式持久化的 `at_seconds` / `motion_scene_id` 采样范围；动作报告还必须有完整实际采样元数据，缺元数据或旧 schema 的报告不猜测覆盖新请求，单点或单 Scene 复核不能代替整片场景抽样，`refresh=true` 强制重新检查。有序离散帧只能支持实际采样范围内的动作阶段判断，不证明采样点之间每一帧的状态；未取动作序列的其他 Scene、Scene 间转场、连续播放、BS.1770 integrated LUFS 与音画同步仍不声称已检查。

首个消费者直接从实际 Output 抽取少量关键帧，对照用户要求和对应内容版本，返回问题描述、帧号/时间与证据；能可靠解算时附 clip/object 引用。运动或声音问题再按需取短片/音频，不要求静帧检查覆盖所有质量维度。报告沿用既有质量/交付读面，说明实际检查范围；模型未能检查时如实说明。

发现问题后通过现有创作/修订流程修改并检查结果。已有授权范围内可自动推进有界修复，不因增加 reviewer 而逐次新增确认；改变确认内容须形成新版本，制作仍服从现有授权与计量。首版主观判断作为建议，不作为未经校准的强制交付门。

审片首版可直接解码成片，不依赖 P10 编辑上下文或新建通用帧服务；出现真实复用时再提取共享实现。

首批修复一个问题仅证明闭环成立。声明的内容质检出口还须覆盖实际影片的文字可读性/遮挡、内容与要求一致性、运动与镜头衔接，以及适用的声音/音画同步；可组合确定性检测、关键帧、短片与必要试听，逐项说明结果和未检查范围。重要文案的句首/句尾被画布裁掉就是可观察问题，运镜或入场动画的“电影感”不能豁免；装饰/背景裁切与应阅读文字必须分开，按钮文字与控件间距也属于画面检查。用户要求配乐时，即使执行 spec 未声明音频预期，全流静音仍是不满足要求。尚缺媒体理解或音频能力的项目继续登记，不能把未检查缩写为通过；不要求对每帧运行模型。

当前增加两类确定性复核：网页镜头必须对照 CapturePlan 的 state/element/artifact，检查真实 after/selected 状态、同布局 before/after、底板与切片套合、字体图片加载和输出锐度，不能用装饰性选框冒充真实功能状态；源对齐旁白必须抽检具体词锚动画的实际帧、镜尾保护带和最终音画偏移，SFX 另记录音源峰值、输出管线偏移、integrated LUFS/true peak 与必要的交叉相关。确定性观察与主观听感/审美建议继续分列。

## 9. 素材快照与多轮上下文

当前 `page_readings` 的 consult-first 继续作为网页读取缓存；新架构不以重复缓存代替素材身份。

1. **SourceSnapshot**：以 asset_id/canonical URL、content digest、captured_at、manifest/transcript/views 与不可变存储键固定一次内容。refresh 产生新快照，旧 CompositionVersion 不变。
2. **版本绑定**：CompositionVersion.sources 记录实际使用的快照。工作草稿最终提交时以显式 sources 为已绑定集合，把 Clip source 与 Generator resource 的真实引用补齐为绑定并覆盖为服务端 digest；“被引用”不等于“已绑定”。后续修订不从聊天历史猜 URL、截图、素材时长或文本版本。
3. **MaterialDigest**：Chat 上下文确定性列出已有素材、读取/采集状态、当前版本绑定和可更新事实；不全文重复注入。
4. **读取复用**：同回合、同 canonical read key、同快照复用 Observation；设计装配器直接读取已绑定 manifest，不要求模型为导演再次调用 `get_web_page`。
5. **显式刷新**：只有用户明确请求或选择新快照才更新绑定；新旧 digest 不同必须呈现，不静默替换。

### 9.1 全局素材库与跨 Chat @ 引用

全局库按用户权限索引已有 Asset/Output，不复制媒体文件、不建设第二个可编辑作品库。A 固定身份与权限接口，B 验证跨 Chat 引用和修订闭环；完整素材库页面、搜索与管理体验不阻塞视频基座。

- `@asset` 解算为用户有权使用的具体 SourceSnapshot；`@output` 钉确切 Output 与其 CompositionVersion，不能自动跳到该作品最新版。
- “把 @视频当素材”固定该 Output 的成片文件/probe/digest，并作为新设计的素材；“继续修改 @视频”解算到同一 Composition 的确切 base_ref。歧义通过 Chat 询问，不凭引用动作自动复制或编辑。
- 若被引用 Output 已不是 Composition 当前版本，展示差异并让用户明确采用当前版还是基于所指旧版修订；后者必须针对当前 head 做一次显式条件提交，不能静默覆盖其他 Chat 的修改。首版不建设通用分支/合并引擎。
- 素材、作品、版本与 Output 权限均由服务端校验；跨 Chat 同 owner 可引用，跨 owner 不因知道 UUID 或 URL 而获得权限。
- origin Chat 与当前执行 Chat 分开记录；Run、确认回执、费用和新 Output 属于当前执行上下文，作品内容引用保持稳定。
- 删除、归档、权限撤回与快照保留的策略必须一致；引用失效要明确失败，不偷偷换成“最新素材”。

### 9.2 网页理解与镜头素材采集（两阶段）

网页采集分为两个用途明确的阶段，均沿用 Asset → SourceSnapshot、现有网络/权限/资源约束与不可变版本绑定：

1. **初始侦察**：用户给出 URL 后，现有 `capture_page(url)` 继续生成结构化正文、2× 整页图、视口图和候选元素，用于产品理解与方向讨论。普通 `get_web_page` 仍沿用 `page_readings` / 服务器 HTML 读取及 6000 字符上限，不等同于制作采集。正文仍有界，SourceSnapshot manifest 在根级冻结 `body_truncated`；状态信息不进入可引用产品正文。
2. **通用最终采集**：`capture_web` 的唯一公开输入是 `CaptureRequest`。模型只提供源 URL/不可变快照、同 origin route、viewport、states、targets 与 outputs，不接触 shot_id、arc、内部 artifact role、required 或配对 id。output 只有 `page / elements / blank_plate`；page 不接受目标，elements 恰好一个目标，blank plate 可共同移除一个或多个目标。动作仍只有 `click/fill/hover/scroll/wait`，且只能定位单元素 target。服务端绑定侦察 selector 和 digest，机械生成相关 state/scale 的 populated baseline、几何与同状态血缘，再经既有 WEB_PAGE Asset 队列执行。CapturePlan 仅是内部 worker/provenance 格式，不是模型协议。

最终采集必须满足：

- 每个状态从 fresh credential-free context 独立 replay 并 settle，随后重新采集页面高度、目标 `css_box/full_css_box`、正文和截断事实；不得复用交互前坐标。动作完成后暂停页面 JS/canvas 时钟。禁止登录、凭证、购买、删除、表单提交、跨站导航和无界等待；所有请求继续经过 `_PolicyProxy` 与 per-hop 策略。
- target 默认必须解析到恰好一个元素；`all=true` 按稳定阅读序采集，单 target 与单请求成员总量至多 32，outputs 至多 16、实际视图至多 64，采集图片总量沿用 60MiB 有界预算。每个成员显式保存 `member_id`、member digest、文本、selector 与几何，消费者不得依赖隐含数组下标猜测身份。
- blank plate 在同一 state/scale 一次隐藏全部指定目标，以 `visibility:hidden` 保持布局，截图后统一恢复。普通 elements 输出保留目标矩形内的真实不透明像素；`transparent=true` 才隔离目标、清除背景并以 `omit_background` 取得 RGBA。透明纹理继续无缩放放入配对视口大小的全透明画布，形成固定图片资源；原始紧裁切保留血缘。
- **部分成功是一等结果**：每个 output、集合 member、state/scale 和写盘分别隔离失败。至少一个真实可用视图时 Asset 可 COMPLETED 并冻结不可变 SourceSnapshot；成功 views 与派生 image Snapshot 立即携带精确 `fixed_resource` 供 design 使用。零可用视图、浏览器不可用或入口 SSRF 仍诚实 FAILED。
- Asset meta 与 Snapshot provenance 保存全部有界 `capture_issues`，至少含 state/output 和可知的 target/member/error；返回同时带真实成功图片、`media_files/media_omitted`、精确 context keys、issue 数量与截断事实。即时投影只保留通用 output 血缘和必要目标几何，完整 manifest 继续经 context key 装配。
- 同 digest 的 PENDING/PROCESSING 或有视图的 COMPLETED 部分结果直接复用，不因缺 peer 或配对不完整自动 reset 重跑。补救必须修改 target/state/output 形成新请求；旧 Snapshot 和已保存 CompositionVersion 不变。
- Generator 同一 `RemotionProjectSource.resources` 可携带至多 64 个固定图片，以容纳页面、共同空底板与 26 卡集；单资源 16MiB、总量 32MiB、权限和 digest 校验不变，不拆 Generator 绕过预算。

既有 WebObject、Composition 校验与 `web_shots` 继续读取冻结 views；具体镜头只消费真实存在的资源，不能把其他 output 的成功说成失败 output 已补齐。功能状态必须来自真实动作结果，合成光标、选框和文字不得冒充功能响应。`page_script` 与任意 JavaScript 不属于当前协议，归后续独立批次。

局部取景修订继续使用 `revise_video.focus_web`：模型只给 Clip 与冻结元素 id，服务端经 grounding 重算相机关键帧，不转写相机数值，也不重新采集或重设计其他内容。参考 video-shotcraft 的采集模板与 PageCam 方法，但不复制其任意 `page.evaluate`、过期 post-state 坐标或合成状态冒充真实状态的实现。


## 10. Chat 组件、Canvas 与 Scrub

新链不依赖全局 Canvas、FlowView 相机、节点 rank 或 `canvas_available`。Graph 与执行图不因 Canvas 退役而删除。B 必须在既有 Chat 页面布局下完成全程，并完成下述对话与制作过程接入；不等待全面视觉改版、完整素材库页面或 Scrub。前端仍需接好版本/分镜 DTO、@、SSE、Start、播放与交付协议，视觉不变不代表前端零改动。UI 可基于共同 DTO/事件 fixtures 并行开发，不反向依赖旧 Film 信封。

Chat 内组件通过结构化 block 引用 `composition_id + composition_version_id (+ clip/object ids)`，并记录承载组件的 Chat/project_id，组件读取服务端 DTO；不把可变 spec JSON 或模型手写 HTML 当作持久真相。

- Storyboard 呈现：Markdown 创作概要、版本引用与呈现回执；
- CompositionPreview：只承载明确范围的局部 Scrub；正式完整视频由交付后的 Output 播放器承担；
- Clip/ObjectInspector：最小文字字号 Scrub 已接；完整 Inspector 后续扩展；
- Canvas 若保留，是同类可视化组件/Graph 投影，不再是所有项目的默认归宿。

[Scrub Input](https://uiarc.dev/components/scrub-input) 是 Chat 内的对象属性输入，支持位置、字号、旋转和透明度等值；它不要求时间线编辑器。完整 Scrub Inspector 后置；当前最小切片只编辑当前版本的一个 TextObject 字号。P10 首版形态是 **Chat 内局部编辑窗口**：默认编辑一个明确的 Clip/Object；预览保持影片宽高比与准确位置，可显示场景背景或干净背景；不要求轨道、多选或完整视频播放。连续调整与 `onValueCommit` 都只更新本地草稿——用户点击「应用」才提交一次完整所属 Clip（Object/Animation 随 Clip）或 Track 写入，携带 base_ref 经 `apply_composition_edits` 产生一个新版本；取消与冲突处理保留。不为 mousemove/commit 调 LLM、建版本或触发付费渲染。多对象批量编辑归完整 Inspector 后续扩展；制作前整片预览永不提供，正式制作后的 Output 播放不受影响。字幕组件可采用左侧真实画面、右侧参数的形式。

Inspector 的内容/来源、位置/尺寸、文字样式、Clip 时间与动画分组均读同一版本 DTO。提交携带 base_ref 与完整所属 Clip/Track 实体；Object 不脱离 Clip 单独写入。当前切片支持 Escape/取消、键盘步进、失败回滚与 base 冲突；双击复位和更多属性归完整 Inspector。旧消息卡片钉旧版本，只读历史不追随 current；继续修改旧版须走 §9.1 的显式选择与当前 head 条件提交，不静默用旧卡覆盖新版。

SFX/Music 候选与音频 Inspector 共用真实 `WaveformPlayer` 的 play/pause、seek、进度和时长；语音消息形态由圆形播放钮、确定性 bars 与单时间显示组成，已播放部分通过 clip/mask 投影真实 `audio.currentTime`。bars 可以是不解码 PCM 的确定性视觉表达，但 seed 必须绑定稳定 candidate/audio identity，live/history/remount 同形，不得随机重生成；motion 只服务视觉过渡与真实进度投影，不创造第二套音频状态机。候选阶段只解算 candidate set/member，不写 Composition；落轨后的 Inspector 以 version + audio Clip 为目标，本地试听/调值只改草稿，Apply 才经 `revise_video(base_ref, clips=[{track_id, clip=完整 audio Clip}])` 生成新版本。共享播放器与草稿交互不合并 search/import/revise 的服务端语义，也不创造第二写口。

### 10.1 Chat 创作、工具过程与交付

本节为 TARGET，随 B 实施，不表示当前 Chat 已具备这些能力。通用 SSE、消息顺序、打字机、活动折叠与工作段收口继续归 CHAT_ARCHITECTURE §8；本节只定义视频旅程中的职责；呈现面的区分不要求独立渲染，可由整合 block 统一组织。

| 呈现面 | 职责 |
|---|---|
| assistant 正文 | 创作意图、修改理由、必要问题与结果的关键变化；开工句仍由模型生成，不由组件模板替说 |
| Storyboard / 版本呈现 | LLM 基于保存版撰写的 Markdown 方向简介与分镜表（镜头、时间、内容、画面/动效、时长）、必要 change_set、未解决项与准确版本引用；默认没有动态整片预览，只在当前创作意图需要时附同版局部 Scrub 或静态代表帧 |
| 工具活动 / Run 工作段 | 世界事实支持的读取、设计、修订与制作过程；提供当前阶段和可查看的真实执行记录 |
| Output / 成片卡片 | 通过交付准入后的播放、下载、@引用和继续修改；始终关联实际制作版本 |

工作草稿先增量创作并做局部校验，完整呈现前完整校验并保存为版本。保存后、制作确认前，仅当动态需求需要比较/澄清、用户修改后需核对本次局部结果，或用户明确要求看特定效果时，才由 PreviewAdapter 对明确 Scene/Clip 时间窗或独立 Object 生成可选 Scrub；通用效果示例可使用 Preset 候选。Scrub 钉 composition_version_id、content_digest 与 target，只把归一化局部 spec 交给浏览器；独立 Object 不冒充场景布局、遮挡与衔接已验收。预览不是 Output，不启动正式 Run，也不把 pending 的模型媒体冒充 ready；首稿和纯静态修改均不自动预烘焙 Generator 或附整片 spec。首稿完整呈现等待保存版事实与 Markdown 正文就绪；仅本次实际声明的局部 Scrub 参与就绪等待。用户审阅后按既有授权/费用规则进入 produce_video，由该 Run 生成与渲染固定版本。交付后使用 ChatDock → ChatOutputViewer → MediaLightboxStage 的既有成片查看器。设计与预览成本如实计量，不因尚未制作成片就描述为零消耗。

- 主旅程为讨论需求 → 设计并完整呈现首稿 → 审阅/修订 → 按已有授权规则制作 → 查看过程 → 收到产物 → @继续修改。普通修订只产生版本，不能伪装成新成片；新版本不让在飞 Run 追随改变。
- 正文、活动与结构化产物在同一 transcript 中按既有有序消息/事件协议呈现，能够对应同一次动作；不能把所有工具过程挪到长篇总结之后，也不为每个工具另造一条冗长 assistant 回复。刷新/断线重连保持关联、顺序和去重。
- 制作事实以保存版为准；首稿、开放重稿或用户要求完整分镜时，正文先概述全片方向，再用 Markdown 表格呈现实际场景或独立文字节拍的时间、内容、画面/运动和时长；节拍用场景子编号，不冒充额外 Scene。画面描述依据保存版的布局、样式、时间窗和动画说明主体位置、先后运动与停留，不能把未实现的构想当作已保存事实；空描述只从实际结构归纳。局部修订仍用简短变化说明。正文不转录内部标识、坐标、关键帧或计费机制。费用与执行确认仍在决策位置完整呈现，不能以精简文案省略授权。首稿完整呈现指分镜表与必要概要全部释放，不要求完整技术 DTO 上屏。
- `CompositionVersion` 回答“制作哪一版”，Run/step/attempt 回答“这次执行到哪里”。RunTaskList/WorkSegmentRow 显示真实过程，不把 Scene/Track 当执行节点，也不为 UI 把单个 produce 节点预拆成 DAG。
- 内部阶段由真实执行点报告。准备、旁白、渲染、交付检查只在实际发生时出现；缓存复用、排队、失败与恢复有事实依据。旁白关闭不显示虚假合成；渲染完成不冒充交付完成；无可靠分母不显示百分比，无证据不承诺后台通知。
- 当前可覆盖的 `stage` 不是历史记录。B 在既有 Run/step 存储与推送机制上补最小可回放阶段记录，区分执行尝试、稳定事件身份与顺序，防止重试重复或旧 attempt 覆盖当前状态；不新建通用事件总线。记录不携带原始工具参数、推理或敏感结果，作品/产物只用受权限约束的引用。
- 设计与读取继续投影为语义活动，制作阶段投影到现有 Run 工作段，不出现两份并行进度真相。沿用 RUNNING → REVIEWING → SETTLED 与真实交付收口；Run 终态不能独自提前封口。通用 Chat live 折叠行为不因换组件而改写。
- 失败记录定位真实阶段与可行恢复动作；可复用的准备结果不重复执行或收费。partial/failed/delivered 仍由服务端裁决，卡片与正文不另推一套状态。

### 10.2 TurnBlock / RunBlock 整合呈现

视频 Chat 的一体化呈现采用 [CHAT_ARCHITECTURE §8.10](CHAT_ARCHITECTURE.md#810-turnblock--runblock-与渐进揭示target)：TurnBlock 统一承载一次用户 Turn 的正文、活动、结构化组件与块级动作；RunBlock 按 `runId` 独立承载后台制作、内部阶段与交付。Research run、AI chat 与 crypto agent 仅作为工作块解剖和渐进揭示的参考，不构成安装或替换现有 Chat 机器的决定。

§10.1 的语义职责映射为 Block 内保序 Slot，而不是平级等距消息碎片。组件只消费真实 DTO、保存版与 Output；视觉 reveal 等待必要的前序正文实际 drain，不用客户端定时器伪造生成过程。组件内部 composer、状态机和自动启动行为不能形成第二意图入口或执行真相；完整 Scrub Inspector 仍是后续范围。

B 的 Chat 行为与真实过程要求独立于视觉改版先成立；TurnBlock/RunBlock、通用揭示、目录拆分和同源回放按 [四阶段施工合同](tasks/chat-turn-block-implementation.md) 渐进替换，不以一次性 Big Bang 阻断现有创作链。

### 10.3 与呈现组件解耦的接口与数据

A 定义最小关联与 fixtures，B 实现真实读写、推送和回放。接口返回领域事实，前端将其投影为 TurnBlock/RunBlock 及内部 Slot；不返回组件 props、React 组件名、模型生成的 HTML 或预拼接进度正文。

- **关联明确**：在既有 message/turn、tool activity、Run/step/attempt、CompositionVersion 和 Output 身份上补齐必要引用，使正文、活动和结果能够归于同一次用户操作。异步 Run 可跨越多个 Chat 回合，不能强塞进一个 turn 生命周期；不另建通用 Work/Task 作品根，也不靠相邻位置、时间戳或文本相似度推断关系。
- **事实结构化**：读取/准备/制作活动提供稳定语义类型、状态与必要的安全结果摘要；内容结果通过 canonical 版本、素材/来源和 Output 引用读取。用户文案是事实的本地化或模型说明，不是让前端解析的状态协议。只读工具观察仍可供 Agent 使用，但用户 wire 不直接透传原始参数、结果或推理。
- **快照与增量同源**：历史读取提供当前状态和必要过程记录，SSE 推送同一身份的变更；沿用既有 seq、append/update 与确认边界，明确事件顺序、去重和重连补读方式。不能只靠一次性 SSE 展示过程，也不另造与历史矛盾的 block 本地状态。具体新增字段/索引以实际代码缺口为准，不预建全量事件溯源系统。
- **行为回到领域写口**：设计、修订、制作、确认、重试/取消若已支持，均复用各自服务端校验与幂等机制。组件的按钮只发出对应用户操作；停止前端流不等于取消后台制作，重新显示或刷新不产生新执行。
- **验收看可替换性**：同一组后端 fixtures/真实记录能够支持现有 Chat 与 TurnBlock/RunBlock 呈现，无需改变内容模型或再加一条意图入口；重点验证多轮修改、后台 Run、失败重试、刷新与重连。单项原型通过不等于四阶段施工或完整视觉改版已完成。

### 10.4 Chat 产物平铺与共享查看器

每个 Output 都是独立交付产物。同一作品不同内容版本制作出的多个视频，是多个不同的 Outputs；版本是它们的逻辑关系与展示信息。浏览层按 Output 平铺，不要求用户先选择作品或进入版本分组。

- **分散入口，共享浏览**：产物卡保留在各轮实际交付消息行；点击任意卡片，从其确切 `output_id` 打开当前 Chat 共用的查看器。消息行不需要组成同一个 DOM gallery，不新增一张合集卡替代原消息中的产物。
- **列表与顺序**：纳入当前 Chat 已交付的 Outputs，包含已归档的历史交付；按首次交付的 transcript 顺序排列，同一交付内沿用持久化的产物引用顺序，按 `output_id` 去重。同一作品的不同 Outputs 与其他作品的 Outputs 平等排列，不按 Composition 折叠、不合并同版再制作的不同 Outputs，不增加版本树或作品筛选作为浏览前置。
- **版本标识**：产物 DTO 提供准确的版本展示字段，由实际关联的内容版本投影；新视频沿用 `composition_id + composition_version_id`，不按卡片位置或 Output 数量编造版本号。同一内容版本的多次交付可以显示相同版本号；普通修订没有新交付时不新增 Output 浏览项。
- **浏览与动作**：查看器支持上一项/下一项、当前位置与总数、底部缩略导航；播放、下载、@引用与继续修改始终针对当前确切 Output。历史卡不追随 current，查看历史不触发恢复、重新制作或付费；旧版修订继续遵守 §9.1。
- **类型适配**：图片、视频、文本与分页文档共用查看器外壳，内部复用声明类型、画幅与已有展示原语；产物 contain 不裁剪。文档内部页码与外层 Output 序号分开；切换视频暂停上一项并沿用声音互斥。
- **历史与回放**：按持久化交付引用读取历史产物，不能仅收集已挂载卡片或只用活跃 outputs 列表；归档不让旧卡消失。沿用服务端权限与交付准入；仍存在但属于内部节点、失败或未完成制作的 Output 不进入浏览列表，引用目标确实不存在或权限失效时明确显示不可用，不替换为最新版。刷新/重连保持身份、顺序与去重，新增交付不抢走当前查看项。
- **关闭与可访问性**：关闭恢复打开前的聊天滚动位置与触发焦点；当前浏览项位于其他消息行时，不自动滚动 Chat 追踪它。触发卡未挂载时焦点回到合理的 Chat 容器；保留键盘、移动端、双主题与 reduced-motion，跨消息飞行动画可降级为淡入淡出。

交互参考 [UIArc Lightbox gallery](https://uiarc.dev/components/lightbox-gallery)，采用其共享翻页与缩略导航思路；现成源码或自建实现仍需适配现有 Dialog、主题与媒体组件，不因交互需求已确定便认定组件已安装或选型通过。此需求归 B 的独立 UI 增量，施工与验收见基线合同 §2.5.2，不依赖 C 或 P10。

## 11. video-spec 与 Renderer 替换

### 11.1 契约

`video-spec` 是 CompositionVersion 的不可变渲染编译产物：

- 只含 JSON、量化时间、Tracks/Clips/Objects、Animations/Transitions、样式、音频参数和已解析素材 URL；
- 不含 React、Remotion、DOM、任意 CSS、回调或 Renderer 私有参数；该限制针对最终合成契约，不禁止上游显式、受控的程序化画面生产。新增原生图形需同步 schema、编译、adapter 能力与预览语义；烘焙媒体则按图片/视频资源消费；
- 不含 Project/Skill 权限与数据库读取需求；provenance digest 仅作身份事实；
- Renderer 不读 DB、不知用户/Project/Skill，不决定内容；
- preview、首次渲染、重试和交付 probe 使用同一家族语义。

### 11.2 Adapter 与预览

`packages/video-spec` 及纯时间/插值求值不得 import Remotion。Remotion 只存在于其 adapter；未来替代实现消费同一 video-spec。

服务端 RenderAdapter 与客户端 PreviewAdapter 分家。首版可用 Remotion 实现两者，但 Chat 组件不得散落 Remotion Player 依赖；更换实现时必须有对应预览或明确的服务端预览方案。

商业许可要求把替代实现作为真实约束；具体授权条款另按官方文本与采购判断核对。每个 adapter 必须声明能力，不支持的文字分割、网页相机、Bezier、Transition 或音频能力明确失败，不静默降级。

代表性验收至少覆盖：网页相机、整体与逐字动画、多段 scale + Bezier、Scene 边界、字幕、音乐压拍、旁白、多个时间点帧对照和真实音轨检查。架构隔离不等于替代实现零成本。

### 11.3 时间点查看与 Scrub 预览（目标，按消费者实施）

成片查看按真实文件取帧；Scrub 从对应 CompositionVersion 与固定素材加载目标对象，在指定时间点用现有时间/动画求值和同一 adapter 预览。编排真相仍在内容版本中，不从 MP4 像素重建，也不另存一套 Scene 快照。

从某份 Output 打开查看或编辑预览时，同时解算其内容版本与执行 manifest，使用该次制作固定的媒体；同一内容版本可有多次重生成结果，仅凭 version_id 不能确定实际画面。进入当前版本或另一制作结果时明确切换，不按最新复用指针悄悄替换所指 Output 的资源。尚无交付的设计预览使用该版本已解析的固定素材，并如实表示尚未生成的部分。

当前最小用例钉明确版本、content digest、目标 TextObject 与现有字号属性；本地输入更新草稿，Apply 才产生新版本。Scrub 只编译明确 Scene/Clip 时间窗或独立 Object，窗口内 Clip 的媒体源和动画按现有 `slice_clip` 保留帧语义；整片目标直接拒绝。独立 Object 不保留场景其他对象，也不声称验证了完整布局。预览保留影片画幅与对象自身准确位置，本地输入更新草稿，点击“应用”才经既有内容写口产生一个新版本；取消不写入，动画驱动属性明确编辑作用域。复用现有版本/权限/冲突处理，不为拖动添加 LLM 调用或制作请求。

按目标属性实现足够准确的预览，并与实际渲染对照。不预建全对象求值 DTO、独立帧服务、通用像素 bbox 测量或多维缓存系统；按性能证据补缓存，按第二个真实消费者提取共享代码。审片与编辑可以共用版本/时间定位，但无需在 B 阶段一次实现两者的全部接口。

## 12. 目标目录与新旧代码处置

本节是**目标代码归属和新旧处置的唯一目录合同**，不是当前仓库树。A/B/C 按实际职责逐批建文件，不提前创建空骨架；共享文件只修改相关分支，不整目录删除。表的 TARGET 归属登记于 MODULE_ARCHITECTURE §4.2；当前代码地图仍描述现状。

Generator 的内容 schema/编辑/校验归 `app/editing`，创作调用与生产准备归 `app/tools/video` 并复用既有 agents harness；provider 差异归适配边界，执行资源限制归受控生产器。实际文件按首个消费者登记，不预建 Generator 表/队列/服务；renderer 只消费准备完成的媒体，不执行程序或调用模型。

### 12.1 新目标目录

```text
apps/api/
├── app/
│   ├── editing/                         新内容领域与应用服务，A/B
│   │   ├── schemas.py                   CompositionVersion / Scene / Track / Clip / Object
│   │   ├── timing.py                    时间域、量化、snap、split/trim 时间规则
│   │   ├── animation.py                 Animation/TextPart 展开与纯求值合同
│   │   ├── validators.py                完整候选、引用、布局、时间与容量校验
│   │   ├── edits.py                     apply_composition_edits 唯一内容写口
│   │   ├── store.py                     事务、版本 CAS、请求去重；仅供统一写口调用
│   │   ├── sources.py                   SourceSnapshot 绑定、权限与全局引用解算
│   │   ├── alignment.py                 NarrationAlignment 纯模型、锚点解算与失效规则，扩展
│   │   ├── presets.py                   内置代表 Preset 注册表与原生 Objects/Animations 展开，扩展
│   │   ├── storyboard.py                保存版 → canonical 分镜 DTO
│   │   ├── video_spec.py                保存版 + 已准备素材 → video-spec
│   │   ├── service.py                   design/revise/read 共用应用服务，B
│   │   ├── director.py                  创意调用装配；复用 agents harness，B
│   │   ├── grounding.py                 引用/事实与网页视图绑定校验，B
│   │   └── templates.py                 VideoTemplate 实例化与 Preset 展开，B
│   ├── tools/video/                     资源准备与制作执行，不拥有作品内容，A/B
│   │   ├── production/                  produce_video 声明、估价、准备与执行
│   │   ├── design.py / agents.py        design_video 编排与 Director 声明
│   │   ├── authored.py                  初稿/修订共用的有界源码修复，不写版本
│   │   ├── params.py                    版本引用与制作输入参数
│   │   ├── preparation.py               素材冻结/上传、字体发布；调用 editing 快照登记
│   │   ├── programs.py                  draw-2d 校验、固定媒体、预览与 exact-digest 复用
│   │   ├── components.py                remotion-project 隔离烘焙、固定媒体与 exact-digest 复用
│   │   ├── sfx.py                       SFX 候选、导入与固定平台音效能力，扩展
│   │   ├── generated_images.py          image-generation 单图生产、执行清单与 Composition 复用指针
│   │   ├── review.py                    首个 exact-Output 静帧审片消费者，复用既有 Agent 与媒体取帧
│   │   ├── program_runner.mjs           无业务能力的权限受限 Node 程序入口
│   │   ├── narration.py                 固定切点、有界语速、真实音频准备
│   │   ├── narration_store.py           合成复用、占位/接管/完成与失败恢复
│   │   ├── narration_alignment.py       句/词对齐准备、语义工具与 worker processor，扩展
│   │   └── alignment_store.py           NarrationAlignment 认领、digest、READY 冻结与恢复，扩展
│   ├── tools/research/
│   │   └── capture.py                   初始侦察 + CapturePlan 最终采集；同一浏览器安全边界
│   ├── skills/
│   │   ├── __init__.py                  保留并扩展内置包加载，不另建注册表
│   │   ├── package_reader.py            内置/外置不可变包的同构渐进读取与静态索引
│   │   ├── launch-film/
│   │   │   ├── SKILL.md                 保留创作工艺，移除专属执行器依赖
│   │   │   └── video-template.json      新声明式固定骨架，B
│   │   ├── talking-head-video/          真人原片与三层常驻文字包装，扩展
│   │   ├── text-animation/              原生文字/图形代表动效，扩展
│   │   ├── knowledge-explainer/         最终旁白、词锚与概念/证据画面，扩展
│   │   ├── store.py                     用户 Skill/SkillVersion，C
│   │   └── import_skill.py              不可信文档包解析与能力差异报告，C
│   ├── prompts/
│   │   ├── video/                      website/MG/mixed/aligned-narration/draw-2d/remotion-project/image Director 与 reviewer 合同
│   │   └── chat/                       system.j2 / user.j2 唯一入口；plan/conversation/event/delivery mode 与真实共享 partial
│   ├── models/tables.py                 原地新增/退役 ORM 行，不复制第二套 Base（B 上半批：messages.blocks）
│   ├── models/schemas.py                共用 Chat/Output DTO；领域模型引用 editing
│   ├── chat/                           保留服务与双入口，共用 editing service（B 上半批：video_turn_seats.py 两路径共座；分镜 DTO 读口住 chat/routes.py）
│   ├── pipeline/                       保留执行/渲染/交付机制，改视频分派与版本引用
│   └── platform/                       保留费用与存储能力，更新视频配置/计量接缝
├── migrations/versions/                增量 schema 迁移；不删除已应用迁移历史
├── test/core/                          核心 API/DB 确定性测试
├── test/journeys/                      真实用户全旅程
└── scripts/                            架构门/剧本原地修改；诊断工具按消费者处置

packages/video-spec/                    新 renderer-neutral 契约，A
└── src/
    ├── schema.ts                       唯一 TS 渲染 schema/type
    ├── timing.ts / animation.ts         纯量化/插值；无 React/Remotion
    └── index.ts                        公开契约；golden fixtures 随包测试维护

apps/render/src/
├── server.ts / stage.ts / artifacts.ts  原地扩 video 分派与受控上游 bake 入口；保留共享服务
├── component-runtime/                  remotion-project 的声明依赖、固定素材与完整工程上游烘焙；不是最终 spec 分派
├── video/
│   ├── index.ts / capabilities.ts       adapter 边界与能力声明
│   └── remotion/                       第一实现；新 video 链的 Remotion 依赖限于此 adapter
│       ├── render.ts / entry.tsx / Root.tsx
│       └── Video.tsx / components.tsx
└── render.ts                           旧 Clip driver 保留

apps/web/src/
├── components/chat/
│   ├── ChatDock.tsx                   两形态外壳、组合根与 composer 恒渲染承重结构
│   ├── ChatConversation.tsx           消息 scroller 与 Block 渲染，不拥有面板几何
│   ├── hooks/                        可选：真实 Block 边界稳定后按消费者提取，禁止前置巨型 hook
│   ├── timeline/                     无 React 的共享类型与纯投影
│   │   ├── types.ts                  OverlayMessage / ConversationUnit / Block / Slot
│   │   ├── project.ts                rows → units → blocks；保序与稳定身份
│   │   ├── activity.ts               activity fold 与 category 聚合
│   │   ├── history.ts                历史行读容忍适配，不决定布局
│   │   ├── speech.ts                 多段正文所有权、received/shown 与 drain
│   │   └── reveal.ts                 Slot 揭示判断；无 DOM / motion
│   ├── blocks/
│   │   ├── TurnBlock.tsx             用户边界与完整 assistant 回复容器
│   │   ├── AssistantResponse.tsx     正文、工作段与组件槽位的内部布局
│   │   ├── RunBlock.tsx              runId 持有的独立制作容器
│   │   ├── ComponentSlot.tsx         结构化事实的判别分派，无动态 UI schema
│   │   └── RevealSlot.tsx            真实 ready + 前序 drain 后的挂载与入场
│   ├── rows/                         UserMessage / AssistantText / Activity / WorkSegment / Meta
│   ├── run/                          RunTaskList / RunCard / Run 纯投影
│   └── video/
│       ├── StoryboardCard.tsx               版本呈现回执与真实 Generator 预览，B
│       ├── CompositionPreview.tsx           版本化最小预览，B
│       ├── WaveformPlayer.tsx               真实音频播放/seek/进度 + identity-seeded bars，SFX 与 Inspector 共用，扩展
│       ├── AudioCandidateSurface.tsx        SFX 可试听候选，消息持久化与自然语言选择，扩展
│       ├── VideoPresetCandidateSurface.tsx  注册 Preset 的真实动态候选与自然语言选择，扩展
│       ├── preview/                        PreviewAdapter；先复用播放器/服务端预览
│       └── inspectors/                     完整 Clip/Object/Scrub 交互，P10
├── components/mentions/                复用 picker，不新建第二 @ 体系
└── lib/                                版本 DTO、mentions、SSE 原地接线
```

目录树标的是职责座位，不要求文件名与纯函数一一对应；合并小文件可以，但跨内容/执行/渲染边界的移动必须更新本合同。`design_video / revise_video / get_video_version` 是 Chat action，注册/适配在现有 `chat/turn_tools.py` 与 plan/propose 路径，共用 editing/service；只有 `produce_video` 是制作节点，不把设计工具都注册成付费 DAG 节点。

### 12.2 当前边界与退役处置

- 当前作品内容、版本与 Storyboard 归 `app/editing`；本地/模型媒体准备与制作归 `app/tools/video`；Run/Output/render queue 归 `app/pipeline`；Renderer 只消费 clip-spec 或 video-spec。
- 旧 Film 专用 Chat tools、schema、prompt、pending 信封、plan/propose 分派、render family、配置、启动清理和诊断入口已删除，不保留兼容层、双读/双写、缺版回退或旧开关。`film_narrations` 的删除使用独立 Alembic migration，历史迁移不改写。
- `SourceSnapshot`、CapturePlan、网页采集、video-spec、renderer 服务底座保留；VideoTemplate、NarrationAlignment、受控 Generator 与共享 narration/media 能力按真实消费者保留。
- `packages/clip`、`tools/clips`、reframe/dub/captions 等旧 Clip 能力继续保留，逐项承接归 P9。
- 新文件或改名仍须符合 §12.1 的职责边界；删除任何仍有消费者的共享能力前必须重新清点注册、启动、render 与资源消费。

### 12.3 边界与目录验收

- `apply_composition_edits` 是内容唯一写口；store/sources 等提供受控能力，不产生绕过版本校验的第二写入口。`apply_wiring_ops` 继续守执行图。
- editing owns 内容/版本/快照，tools/video owns 制作与配音准备，skills owns 创作方法，pipeline owns Run/Output/render queue，Renderer 只消费自足 spec；不以“共用服务”名义把它们重新塞进巨型 storyboard.py。
- 表中路径以仓库根为基准；写“原地修改”的文件必须逐个核对，不把目录存在当接线完成。C 的 Skill 生命周期与 P10 Inspector 文件不属于首批 A 必建清单。
- D 删除前复跑 import/注册表/运行调用链与资源引用清单，对照每行处置结果；提交说明列实际删除/保留及理由。静态零引用不能替代真实启动、Clip 回归与新视频旅程。
- 目标目录/表归属、测试和构建引用同批更新；新文件或改名与本节不一致时先修唯一合同，不在施工文档再维护第二份目录树。

## 13. 替换与数据边界

- 不迁移既有业务数据，不写 FilmStoryboard/film-spec → CompositionVersion 数据适配器；旧 Film API 与实现不保留兼容层。
- 保存版真实预览、最小 Scrub 与旧 Film 清理已提前落码，但完整 P6+P7、制作、剧本矩阵与视听验收没有因此通过。
- 废弃表/列只能经新的 Alembic migration 删除；不 reset、清库或删除历史迁移。
- Clip 保留到 P9 逐项等价验收后处理。多选、批量编辑、自由时间线、完整 Inspector、CompoundClip、多用户 Skill 市场和完整 NLE 不在当前最小切片。

## 14. Prohibited Behaviors

- 禁把 Project 与单部影片身份合并，禁用“Chat 最新产物”隐式替代 Composition/版本；禁再引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
- 禁把 Scene/Track/Clip/TextPart 展开成执行图节点，或让 Canvas 成为版本真相。
- 禁让 `visual_description` 描述不存在的元素/动画，或在视觉修改后保留失实摘要。
- 禁把每个字符默认持久化为独立 Clip，禁文本变更后静默错配动画。
- 禁让 Skill 执行任意脚本、授予工具权限、绕过 grounding/授权/计费或拥有第二执行链。
- 禁让 Renderer 概念进入通用 Track/Clip/Object、VideoTemplate 或 video-spec；唯一例外是受控 GeneratorObject 的不可变生产来源，`remotion-project` 可保存 Agent 编写的完整工程，但只能经声明 runner 上游烘焙，最终 spec 仍只含普通媒体。
- 禁为 SFX 新增 Object/spec/生产链，禁用确定性模拟 bars 冒充真实音频分析或真实播放进度；共享波形播放器不携带录音器、随机重生成波形或第二内容写口。
- 禁以“未来可替换”为由把 PreviewAdapter、能力矩阵和替代实现验收省略。
- 禁建设旧 Film 数据迁移层；也不得借“不迁移数据”提前删除仍需对照的当前实现。
- 禁把 Recipe 改名后仍暗含执行；PromptTemplate 永远只是可见预填。
- 禁把一次性完整 Composition 当作所有首稿的唯一模型协议；禁用 `fresh_design`、整片重交或全量参数回放处理局部错误。完整实体写入不是恢复构造 Op 的理由。
- 禁为条件工具投影新增平行阶段状态机、AuthoringSession 作品根或第二套生产链；模型不可见不代替执行端权限与状态校验。
- 禁把完整成片动态预览当作制作前审阅能力；禁按动画/媒体特征自动附整片 spec。局部 Scrub 不能冒充正式 Output、完整场景验收或制作授权。

## 15. 新链必须承接的产品语义与验收缺口

本节是有效影片需求的当前归位，不保存旧实现方案。混合内容与生成/程序化生产的目标边界见 §4.3.1–§4.3.2、§8.1.1；当前实现与分批出口归施工合同，不因列入目标就声称可用。旧 Film 任务与专属实现测试退出不代表能力已完成；A 最小基座与部分 B 主链已有证据，剩余目标与未验证能力不能因为其余测试通过而宣称生产就绪。

- **输入与意图**：网页源、文字源、图片源与真实视频源走同一作品链；产品宣传必须在同一版本混合四类输入，知识讲解可以只输入知识文字稿并由最终旁白和词锚驱动，不能用四条单素材样片替代。模拟知识稿仅作演示创作输入，不冒充真实事实来源，也不要求补真实证据素材。用户原文、创作要求、生成稿区分来源。未决定逐字展示还是改编时问最影响方向的一题，不一次收齐参数；明确委托/明确方向直接设计。零原文但有创作要求的自由 MG 合法，不伪造来源。verbatim 模式每段恰好一次、按原文顺序、零改写增删，换行不丢字；容量不足点名段落/差额/处置，不无限缩字硬塞。
- **用户约束与技术政策**：用户要求、agent 选择和默认值分别记录来源。当前 120s/3600帧等仍运行的政策只作旧链事实；新链以设置/制作政策冻结，139s 若不支持就明确拒绝，不截断。画幅变体、字体枚举/vendor 字体、网页录屏与声音选择/试听的需求继续保留；不建设旧 set_aspect/指纹迁移兼容路径。
- **音频三态**：未指定/明确关闭/明确选定分开；用户选择/关闭优先，其次既有版本选择，再 persona/default，关闭不被默认重开。voice_id、实际音乐 track/resource 与参数须在版本/执行输入固定，mood 不是曲目身份。复用 hash 包含归一化文字、已解 voice、语言、合成配置/模型，保留原速原件；运行适配另算，成功准备可恢复。
- **试听后置边界**：用户要求先听时给真实可播放样例并等待，优先现有资源，否则显式短样例成本；不预生成全库或整片旁白。试听选择与成片同配置，重开已有旁白不强迫整片重设计。声音目录/试听 UI 后续排期，不伪装本批已完成。
- **安全采集与 grounding**：capture/SSRF、章节/视图/元素身份与引用校验留代码；网页屏上事实引用可解析，旁白可复述但不编造事实。element focus 由已识别元素盒推导，不盲猜坐标；最终采集只执行 CapturePlan 的有界动作，交互后重测状态与坐标，不用合成状态冒充功能事实。当前有限同 host 子页采集沿已有 policy（最多3个子页、过滤 login/blog/legal、不递归外站）。Chrome 不可用要诚实缺截图/能力，不能伪造视图；录屏不等于截图推拉，不默认支持登录、系统声音或复杂操作。
- **独立视觉与字幕**：默认字幕 ON、旁白默认 OFF，显式开关与既有版本继承必须可读、可编辑；无旁白不等于无字幕/音乐。字幕 TextObject 的 `style.background` 默认 null，不自动添加黑色/半透明底条、背板、盒子或 pill；仅用户明确要求背板时才添加，可读性由位置、字号、字重、颜色及必要时的克制原生描边/阴影保证。字幕最后 cue、文字最后入场/停留必须落入实际执行窗。纯 slide 不混入 opacity/blur/rise，单文字淡出不影响背景或兄弟对象；presence 的 absent/null/0 各有含义。逐字/逐行间隔量化累计偏差须按最终落点呈现，不拿单值误差冒充整段误差。
- **局部修改**：只改末幕时前幕保持；clear grouping、切换文字组织单位时显式重算/清除旧 timing，禁止旧字符节奏静默套成行节奏。超窗明确冲突，不截短/重排素材。严格样例：30fps、开始0.3s、间隔0.5s、时长0.4s，两行分别 f9→f21、f24→f36，第二行 f24 前不可见；以真实动态帧验证，不能锁旧字段名/公式。
- **有界设计**：共享墙钟与调用硬上限贯穿初稿、局部写入、预览与多模态降级，嵌套重试不刷新；局部错误只修目标范围，无进展诚实终止、旧版保留，失败不伪装成已保存作品或假 busy。旧固定 worker fallback、30fps唯一格式与三段宏 DAG 不继承为新实现义务。
- **B 真实旅程**：网页/MG 双源；首稿完整呈现→下一轮制作；普通修订与改完直接做；auto/ask、费用/制作意图、copy drift/unmet condition；跨 Chat @ 与过期引用；声音/音乐/原声独立试听、字幕开关/极短cue、完整章节标题/reveal可读性；8幕仅改末幕严格slide；真实断网/停止/迟到/60s无回复、刷新与WorkSegment/交付卡。现有on_row_append未接线/显示与执行一致性缺口需在canonical payload新链验证，不沿旧例外继续打补丁。
- **A/B 新覆盖缺口**：Composition原子版本/请求幂等/跨Chat权限，三时间域与切分/转场，TextPart/字体排版，renderer-neutral spec、实际音轨与动态对照，Start版本和执行manifest、重试计费都必须新建合同覆盖。旧 Film-only测试退役后这些项目仍明确未验证，不要求旧接口重绿，也不以删测减少失败数报通过。
- **共享能力保留**：配音身份/有界适配、provider完成语义、通用配置/计量与授权/执行fencing守卫继续有效，按真实模块归测试。Clip尚未迁移，独立Clip编辑、轨道、字幕、归档与渲染测试继续运行。


### 用户可见剪辑术语

Chat 正文、进度说明、询问与选项、界面文案采用专业剪辑常用词汇，参考 [Final Cut Pro 导入媒体](https://support.apple.com/zh-cn/guide/final-cut-pro/verd0e77425/mac)及[添加音乐和声音](https://support.apple.com/zh-cn/guide/final-cut-pro/ver549f1ed1/mac)。媒体准备称“导入素材/导入音乐”，复用称“使用已导入素材”；只有已保存的编辑实际包含该音频片段，才称“已添加到时间线”。标题、字幕、旁白、转场、关键帧、渲染、导出和保存版本各按真实行为使用，不把标题泛称为语音字幕，也不把保存草稿说成导出成片。

SourceSnapshot、snapshot_id、digest、冻结、绑定、Composition、Generator 保留内部数据及工具协议的精确语义，不直接作为用户操作名称。用户主动询问实现或诊断时可以解释。此规则在共享发言模板中维护，适用于 promo 及其他 Chat 入口；不重命名持久化字段、不修改资源身份与复用合同。
