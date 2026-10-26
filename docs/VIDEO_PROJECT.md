# Video Project — 视频作品、Skill 与渲染目标架构

> Status: 已拍板目标架构（2026-10-26），**未实施**。本文是 Film/MG 新架构的唯一目标事实源；四阶段施工与验收归 [video-project-implementation](tasks/video-project-implementation.md)。当前代码仍由 `clip-spec` / `film-spec`、FilmStoryboard 与 `launch_film` 承载，现行实现事实仍读对应代码与 RENDERING，不得把本文目标写成 CURRENT。
>
> 范围：先把网页宣传片与 MG 的创建、分镜、CRUD、版本、制作和交付做通；个人 Skill 随后开放；Clip 能力内化与 Scrub Inspector 后置。**不迁移既有业务数据**；新表、新列和索引仍须走 Alembic schema migration。

## 0. 核心决策

1. **Project 是 Chat 与执行上下文，Composition 是一部持续编辑的视听作品身份**。同一 Chat 可创建多部 Composition 并通过 @ 分别持续修订；不引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
2. **CompositionVersion 是不可变编辑版本**，自身直接承载设置、素材引用、Scenes 与 Timeline；Timeline 只是版本内部的时间结构。
3. **Track 上是 Clip，Clip 内是 Object**；Animation 统一作用于 Object 属性，Transition 表达 Clip 之间的衔接。
4. **Storyboard 是 CompositionVersion 的分镜读面**，不是第二份可独立修改的作品数据。
5. **launch-film 在新链只是内置 Skill**。通用 `design_video` / `revise_video` / `produce_video` 承载所有视频创作，Skill 不拥有执行链。
6. **Chat 是唯一意图面**，`/skill + prompt` 只是确定调用语法；Graph/Run 继续负责执行，Canvas 不再是作品成立或审阅的前提。
7. **video-spec 是 Film 的继任渲染契约**，renderer-neutral；迁移期是明确的新旧替换，不建设第三套永久视频架构。
8. **不为旧 FilmStoryboard、film-spec 或旧项目数据建设迁移层**。新链验收后删除旧 Film 实现；Clip 的迁移与删除另行评估。

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

所有 LLM 修订、确定性手势和未来 Markdown 组件提交都经 `apply_composition_edits`：

```text
base_ref(composition_id, version_id, content_digest) + request_id + edits
→ 读取并校验当前版本
→ 原子应用完整 op 批次
→ 校验完整候选版本
→ 插入新 CompositionVersion
→ 条件更新 Composition.current_version
```

- 任一 op 失败则整批不落版。
- 过期 base_ref、并发覆盖和非法字段失败闭；跨 Chat 编辑同一 Composition 使用同一当前版本条件更新。
- 相同 owner/Composition/request_id 的同一载荷重试返回已提交结果；同 key 不同载荷拒绝。请求幂等与并发检查分开，不能用过期版本错误代替成功请求的恢复。
- change_set 由系统比较 base/result 得出，不由模型自报。
- 未触碰的 Scenes、Tracks、Clips、Objects 保持原值；确定性地刷新或清空受影响的描述/派生字段不视为额外创作。
- 新版本不反向改写已经执行的 Run 或已交付 Output。
- Output 钉 `composition_id + composition_version_id + content_digest`，其 `project_id` 记录本次制作所在 Chat；旧 Output 在新制作真实完成前保持可用。
- 新视频 Output 的既有 `work_id` 映射到 Composition.id，承接现有发布/归档作品锚；内容版本、Output 行与制作尝试不混用。旧 Clip/非视频的 work/edit/restore 契约保持当前作用域，不把旧“版本内原地编辑”套到新 Composition。
- `pending_brief` 只保留 plan/question/confirmation 状态，不再兼任 Film 或视频版本库；plan/propose 两条 Chat 路径调用同一个编辑服务，不各复制一套 compose/patch。
- `get_video_version(version_id | composition_id + current)` 是明确版本读面；多影片时不得用“本 Chat 最新视频”替代目标解算。

### 2.3 可审阅呈现也是版本事实

`storyboard_payload(version)` 由服务端从保存后的 CompositionVersion 确定性生成，包含完整分镜表和回退事实标签。Chat 呈现这份 canonical payload 并补充解释，不要求 LLM 把整张表重新转录一遍。

成功呈现时持久化 `presented_message_id + presentation_digest + composition_version_id`。首稿 Start 同时校验版本与呈现摘要；仅有“消息曾提到某版”不等于用户看过当前完整分镜。结构化表格、组件和 LLM 散文字段的释放都遵守现有打字机律，不能借 canonical payload 整段瞬移。

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

修改分镜就是修改 CompositionVersion；修改后重新投影**完整当前表**，不是拿旧表加一段模型猜测的 diff。结构化表格由 `storyboard_payload` 生成；`visual_description` 虽然是 LLM 创作字段，也已经随版本保存，因此不需要让 Chat 模型再次概括或转录内部元素。

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

### 4.2 Clip

```text
Clip
├── clip_id
├── range                 全片输出时间窗
├── scene_id?             叙事归属，可空
├── source?               SourceSnapshot + 源素材时间区间
├── object
└── animations[]
```

| Clip | Object | Source |
|---|---|---|
| VideoClip | VideoObject | 视频快照 + source_range |
| AudioClip | AudioObject / SpeechObject | 音频快照，或待合成旁白信息 |
| ImageClip | ImageObject | 图片快照 |
| TextClip | TextObject | 无源素材 |
| WebClip | WebObject | 网页快照、页面视图或录屏 |

同一 Asset 可由多个 Clips 引用不同 `source_range`；每个 Clip 有自己的 id、输出窗、对象与动画。`source` 明确包含 `asset_id + snapshot_digest + source_range`，不使用含义模糊的 `clip_source_id`。

### 4.3 Object

Object 负责内容、布局和表现，Clip 负责时间与轨道。

- VisualObject：layout、transform、opacity、style、effects。
- AudioObject：gain、pan 与音频 effects。
- WebObject：网页快照/视图引用及取景、相机所需的结构化参数。
- SpeechObject：`text` 是旁白原文唯一来源，另存声音绑定与合成 provenance；Scene 和分镜表引用该文本，制作后才解析成可渲染音频。

Layout 与 Transform 不得形成双真相：layout 决定静态盒，transform 只表达相对盒的位移、缩放、旋转与透明度。相同位置不得同时由 `rect.x` 和 `transform.x` 两套值决定。

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

Transition 属于同一 Track 上相邻 Clips 的编辑关系；单 Object 的 fade、slide、zoom 仍是 Animation。首批只实现当前宣传片/MG 需要的封闭枚举，不做转场画廊。

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
| 网页推近与取景运动 | WebObject 的结构化取景/transform 属性 |

基础是**关键帧 + 每段 easing**，不是单一贝塞尔：

- `linear`、`cubic-bezier`、`hold` 是基础枚举；
- 多段关键帧表达“先变大、迅速回缩一点、再稳定”等 overshoot；
- 现有 spring 行为可先作为受支持 easing 或确定性烘焙输入保留，不在首批强行重写；
- AnimationPreset 只在实例化时展开为属性和关键帧，Renderer 不查 Preset 注册表。

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
- snap 后统一量化到输出时间/帧；不得由 API 与 Renderer 各自 round。
- 没有音乐不伪造 BPM；BPM 不代替 fps，也不自动改变所有 Object 动画。

### 6.4 旁白、字幕与固定切点

- 默认固定已审阅 Scene/Clip 切点；TTS 可在显式制作政策的有界语速范围内适配，不借用其他 Scene 帧数、不移动切点、不改旁白原文、不静默截断或交付缺失旁白的成片。
- 语速上下界、适配重试次数、超长判定和费用上限在 B 接通 TTS 前配置并进入报价/执行输入；超出边界返回具体冲突，经 Chat 修订形成新版本后再制作。
- 字幕可由旁白派生，记录源 SpeechObject、文本版本与对齐 provenance；用户手改后标记独立编辑，不再被旁白重生成静默覆盖。字幕同步刷新是显式编辑。
- 视频与其原声分离到视觉/音频 Clip 时记录关联；split/trim/move 明确同步范围。不能只移动画面留下旧音轨，也不能强制连带用户已解除关联的声音。

### 6.5 A 阶段必须冻结的求值合同

A 的最小纵向样片开工前，给出纯函数与 golden fixtures，冻结：时间范围 `[start, end)`、各时间域单位、量化/舍入与时长换算、视觉 Track order 方向及唯一性。同轨非转场重叠首版拒绝；需要叠放时使用不同 Track。

Transition 明确输出覆盖窗、前后 source handles 与余量不足行为；首版无足够余量就拒绝，不偷改时长。split/trim 必须明确关键帧裁剪、端点取样和重新定基规则；同一 Object/属性的重叠动画首版拒绝，TextPart 与父对象的变换按声明的层级组合。

字体文件与 digest、文本切分、grapheme/word/line 寻址及排版实现版本必须可追溯。Preview/Render 用相同资源与一致求值；不同实现通过中文、英文、换行和 Emoji fixtures 对照，不能只验证时间插值。

## 7. Skill、VideoTemplate、Preset、PromptTemplate

### 7.1 四层职责

- **PromptTemplate**：Home/ composer 的可见预填；UI 不需要出现“配方”一词，不自动发送或执行。
- **VideoTemplate**：Scene/Track/Clip/Object/Animation 的参数化结构、内容槽位、有界 repeat 与变体。
- **Preset**：局部动画、字幕、文字样式或音频参数。
- **Skill**：版本化创作包，组合 instructions、VideoTemplate、Presets、输入要求、能力要求与示例。

VideoTemplate/Preset 实例化后展开进 CompositionVersion；之后修改 Skill 或 Template 不暗中改变旧作品，Renderer 也不依赖 Skill 仍存在。

### 7.2 launch-film 只是内置 Skill

目标包：

```text
launch-film/
├── SKILL.md
│   ├── 章节、hook、reveal、旁白与命名工艺
│   └── 引用与事实纪律中的创作部分
└── video-template.json
    ├── cold open / hero / home walk
    ├── 3–5 章有界 repeat
    ├── divider / chapter walk / optional plate
    ├── reveal / proof / end
    ├── Track、Clip、Object 与 Animation 结构
    └── 内容、网页视图与时间策略槽位
```

capture、SSRF、citation resolver、grounding、素材权限、容量、报价、授权、TTS、存储、渲染与失败降级仍属代码能力。Skill 可调用已注册 binder 的能力，不能提交脚本修改它们。

无 Skill 的自由 MG 由 `design_video` 生成结构化 edits；有 Skill 的官网片由同一工具实例化模板。后续版本、CRUD、Run、Render 和交付完全同链。

### 7.3 个人 Skill 与外部导入

- “保存创作方法”才生成 Skill：从 CompositionVersion **确定性抽取**结构、轨道、布局、动画和参数；LLM 只协助名称、description 与使用说明，不重新猜数值。内容槽位、固定品牌元素和可适配范围由用户审阅确认，不声称能从一次成片自动推断全部创作规律。
- 默认排除事实文案和用户源素材，保留声明复用的结构与风格；示例引用须有权限。
- SkillVersion 不可变；`/skill-name + prompt` 绑定确定版本，仍走唯一 `POST /chat`，不跳过首稿审阅、制作意图或费用授权。
- **Strict** 表示无法复现声明参数就明确冲突；**Adaptive** 只允许在声明边界内适配。不得静默变化后声称“完全一样”。
- 外部 SKILL.md/references 可导入为草稿；`scripts/` 不自动执行，`allowed-tools` 只是依赖声明，不授予权限。
- 新对象、动画或私有工具不受支持时列能力缺口，不伪装完整兼容。
- 首版仅个人 Skill、单次创作一个显式用户 Skill；不做市场、团队共享或自由叠加。

## 8. Chat → CompositionVersion → Run → video-spec

### 8.1 新管线

```text
/skill + prompt + materials
→ 唯一 POST /chat
→ 解算 @asset/@output 与目标 Composition；固定 SkillVersion 与 SourceSnapshots
→ Director 创作内容槽位与 visual_description
→ VideoTemplate 实例化，或自由设计生成结构化 edits
→ validator + apply_composition_edits
→ CompositionVersion
→ Storyboard 完整呈现与首稿审阅
→ 既有制作意图 / 报价 / 授权 / Start
→ produce_video 钉 composition_id + composition_version_id + content_digest
→ CompositionVersion 编译为 video-spec
→ Renderer 黑盒
→ Output(type=video)
```

修订走 `revise_video(base_ref, edits)` 产生新 CompositionVersion；只有当前消息具备制作意图时才进入后续制作，普通修订不自动重制。

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
- Director schema：创意槽位、精确脚本与 `visual_description`，散文字段 null 读容忍。
- VideoTemplate：声明式结构，不携带 assistant 言语草稿。
- Project validator：身份、来源、grounding、时间、布局、容量和 op 闭包。
- Run gate：呈现、版本、制作意图、费用与执行身份。
- video-spec schema：Renderer 输入合法性与能力边界。

一部法只在一个座位说；工具观察只返回世界事实与指回规则座位，不携带可转述的 assistant 文案。

### 8.4 当前代码接缝与必须拆除的 Film 特判

以下是新链开工时的实际接缝，不是需要保留的目标结构：

- `Project.pending_brief` 当前混合通用确认状态与 Film 版本信封（`models/tables.py:123`、`models/schemas.py:2302`）；新链以 CompositionVersion 取代其作品内容职责。
- plan/propose 当前各有一套 compose/patch（`chat/plan_turn.py:890`、`chat/propose_turn.py:656`）；新链只许一个共享编辑服务。
- Start 当前清空 pending draft 并把 `prepared_storyboard` 复制进 `run.context`（`chat/service.py:2219`、`chat/service.py:2315`）；新链改为通用 `version_ref`，不再从 Run 历史恢复唯一作品真相。
- LaunchFilm 已有钉版校验，但缺 prepared state 时会重新 orchestrate（`tools/film/storyboard.py:8429`、`8594`）；新 produce 只保留严格钉版语义。
- Film 的 compiler slot、requirement、estimate、graph、Start/review 特判当前散在 `pipeline/orchestrator.py`、`step_context.py`、`graph_fill.py`、`lifecycle.py`、`run_review.py`；新视频链通过 CompositionVersion、`produce_video` 节点声明和通用 version_ref 提供事实，不复制这些 if/else。
- 当前首稿呈现依赖 LLM 转录保存版（`prompts/chat/_website_film.j2`）；新链改为 canonical `storyboard_payload` 与呈现摘要。
- Graph 当前还服务 graph read/revision，不只是 Canvas UI；首版保留其隐藏血缘/修订能力。未来若彻底删除 Graph，必须另行替换这些路径并把 `create_run` 的 graph stamping 变为可选，不能把“隐藏 Canvas”误写成“删除 Graph”。

可复用的底层保持不变：`create_run` 唯一 Run 出生地、WorkflowStep inputs/状态调度、NODE_KINDS、队列、fencing、计费、Output render ownership、render_status 认领、artifact probe 与终态写。当前设计/修订双路重复、Film 版本落 pending JSON 和 produce 缺版重设计是新链明确消除的耦合。

## 9. 素材快照与多轮上下文

当前 `page_readings` 的 consult-first 继续作为网页读取缓存；新架构不以重复缓存代替素材身份。

1. **SourceSnapshot**：以 asset_id/canonical URL、content digest、captured_at、manifest/transcript/views 与不可变存储键固定一次内容。refresh 产生新快照，旧 CompositionVersion 不变。
2. **版本绑定**：CompositionVersion.sources 记录实际使用的快照。后续修订不从聊天历史猜 URL、截图、素材时长或文本版本。
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

## 10. Chat 组件、Canvas 与 Scrub

新链不依赖全局 Canvas、FlowView 相机、节点 rank 或 `canvas_available`。Graph 与执行图不因 Canvas 退役而删除。B 必须在既有 Chat 页面布局下完成全程，并完成下述对话与制作过程接入；不等待全面视觉改版、完整素材库页面或 Scrub。前端仍需接好版本/分镜 DTO、@、SSE、Start、播放与交付协议，视觉不变不代表前端零改动。UI 可基于共同 DTO/事件 fixtures 并行开发，不反向依赖旧 Film 信封。

Chat 内组件通过结构化 block 引用 `composition_id + composition_version_id (+ clip/object ids)`，并记录承载组件的 Chat/project_id，组件读取服务端 DTO；不把可变 spec JSON 或模型手写 HTML 当作持久真相。

- StoryboardCard：分镜表与当前版本；
- CompositionPreview：作品预览与交付；B 提供最小版本化预览，C 复用而不重新建设；
- Clip/ObjectInspector：后续定点修改；
- Canvas 若保留，是同类可视化组件/Graph 投影，不再是所有项目的默认归宿。

[Scrub Input](https://uiarc.dev/components/scrub-input) 是 Chat 内的对象属性输入，支持位置、字号、旋转和透明度等值；它不要求时间线编辑器。完整 Scrub Inspector 后置，数据与写口在 A/B 预留。`onValueChange` 只做本地预览，`onValueCommit` 才提交一次编辑；其连续拖动只做本地预览，commit 才携带 base_ref 经 `apply_composition_edits`；不为 mousemove 调 LLM、建版本或触发付费渲染。字幕组件可采用左侧真实画面、右侧参数的形式。

### 10.1 Chat 创作、工具过程与交付

本节为 TARGET，随 B 实施，不表示当前 Chat 已具备这些能力。通用 SSE、消息顺序、打字机、活动折叠与工作段收口继续归 CHAT_ARCHITECTURE §8；本节只定义视频旅程中的职责；呈现面的区分不要求独立渲染，可由整合 block 统一组织。

| 呈现面 | 职责 |
|---|---|
| assistant 正文 | 创作意图、修改理由、必要问题与结果的关键变化；开工句仍由模型生成，不由组件模板替说 |
| Storyboard / 版本卡片 | canonical 内容、配置、change_set、未解决项与准确版本引用；承担完整首稿呈现与属性编辑 |
| 工具活动 / Run 工作段 | 世界事实支持的读取、设计、修订与制作过程；提供当前阶段和可查看的真实执行记录 |
| Output / 成片卡片 | 通过交付准入后的播放、下载、@引用和继续修改；始终关联实际制作版本 |

- 主旅程为讨论需求 → 设计并完整呈现首稿 → 审阅/修订 → 按已有授权规则制作 → 查看过程 → 收到产物 → @继续修改。普通修订只产生版本，不能伪装成新成片；新版本不让在飞 Run 追随改变。
- 正文、活动与结构化产物在同一 transcript 中按既有有序消息/事件协议呈现，能够对应同一次动作；不能把所有工具过程挪到长篇总结之后，也不为每个工具另造一条冗长 assistant 回复。刷新/断线重连保持关联、顺序和去重。
- 配置事实以版本卡片为准；正文不例行转录整份分镜、音乐/字幕设置和计费机制。费用与执行确认仍在决策位置完整呈现，不能以精简文案省略授权。首稿完整呈现不因正文简短而缩减。
- `CompositionVersion` 回答“制作哪一版”，Run/step/attempt 回答“这次执行到哪里”。RunTaskList/WorkSegmentRow 显示真实过程，不把 Scene/Track 当执行节点，也不为 UI 把单个 produce 节点预拆成 DAG。
- 内部阶段由真实执行点报告。准备、旁白、渲染、交付检查只在实际发生时出现；缓存复用、排队、失败与恢复有事实依据。旁白关闭不显示虚假合成；渲染完成不冒充交付完成；无可靠分母不显示百分比，无证据不承诺后台通知。
- 当前可覆盖的 `stage` 不是历史记录。B 在既有 Run/step 存储与推送机制上补最小可回放阶段记录，区分执行尝试、稳定事件身份与顺序，防止重试重复或旧 attempt 覆盖当前状态；不新建通用事件总线。记录不携带原始工具参数、推理或敏感结果，作品/产物只用受权限约束的引用。
- 设计与读取继续投影为语义活动，制作阶段投影到现有 Run 工作段，不出现两份并行进度真相。沿用 RUNNING → REVIEWING → SETTLED 与真实交付收口；Run 终态不能独自提前封口。通用 Chat live 折叠行为不因换组件而改写。
- 失败记录定位真实阶段与可行恢复动作；可复用的准备结果不重复执行或收费。partial/failed/delivered 仍由服务端裁决，卡片与正文不另推一套状态。

### 10.2 整合 block 的待选呈现方案

UIArc 仅为调研候选，未决定采用、安装或替换组件。当前考察 [Research run](https://uiarc.dev/components/blocks/research-run)、[AI answer](https://uiarc.dev/components/blocks/ai-answer)、[Document extraction](https://uiarc.dev/components/blocks/document-extract) 等整合 block：能否把一次工作的正文、过程、来源和结果组织成连续的交互单元，替代现有 message/tool 分散拼装的视觉效果。

§10.1 是语义职责划分，不要求对应四个独立 UI 组件，也不要求保留 RunTaskList/WorkSegmentRow 的具体呈现实现。可以由一个整合 block 渲染相关事实，底层仍保留版本、执行与产物各自的身份和权限。是否采用现成 block、提取其中结构或继续自建，需以真实多轮创作、版本修改、后台制作与刷新回放原型比较后决定；不先冻结新的 block schema 或引入通用 UI 编排层。组件内部 composer、状态机和自动启动行为不能形成第二意图入口或执行真相。

B 的 Chat 行为与真实过程要求独立于组件选型；完整视觉改版可并行，复杂 Scrub Inspector 仍属 D4。外部示例中的流式、停止、重试与本地历史语义须核对后适配，不直接等同于服务端 Run 的取消、重做或持久记录。

### 10.3 与呈现组件解耦的接口与数据

A 定义最小关联与 fixtures，B 实现真实读写、推送和回放。接口返回领域事实，前端可将其渲染为分散消息或整合 block；不返回 UIArc props、React 组件名、模型生成的 HTML 或预拼接进度正文。

- **关联明确**：在既有 message/turn、tool activity、Run/step/attempt、CompositionVersion 和 Output 身份上补齐必要引用，使正文、活动和结果能够归于同一次用户操作。异步 Run 可跨越多个 Chat 回合，不能强塞进一个 turn 生命周期；不另建通用 Work/Task 作品根，也不靠相邻位置、时间戳或文本相似度推断关系。
- **事实结构化**：读取/准备/制作活动提供稳定语义类型、状态与必要的安全结果摘要；内容结果通过 canonical 版本、素材/来源和 Output 引用读取。用户文案是事实的本地化或模型说明，不是让前端解析的状态协议。只读工具观察仍可供 Agent 使用，但用户 wire 不直接透传原始参数、结果或推理。
- **快照与增量同源**：历史读取提供当前状态和必要过程记录，SSE 推送同一身份的变更；沿用既有 seq、append/update 与确认边界，明确事件顺序、去重和重连补读方式。不能只靠一次性 SSE 展示过程，也不另造与历史矛盾的 block 本地状态。具体新增字段/索引以实际代码缺口为准，不预建全量事件溯源系统。
- **行为回到领域写口**：设计、修订、制作、确认、重试/取消若已支持，均复用各自服务端校验与幂等机制。组件的按钮只发出对应用户操作；停止前端流不等于取消后台制作，重新显示或刷新不产生新执行。
- **验收看可替换性**：同一组后端 fixtures/真实记录能够支持既有 Chat 和一个整合 block 的呈现原型，无需改变内容模型或再加一条意图入口；重点验证多轮修改、后台 Run、失败重试、刷新与重连。该原型用于验证数据充分性，不代表采用 UIArc 或交付完整视觉改版。

## 11. video-spec 与 Renderer 替换

### 11.1 契约

`video-spec` 是 CompositionVersion 的不可变渲染编译产物：

- 只含 JSON、量化时间、Tracks/Clips/Objects、Animations/Transitions、样式、音频参数和已解析素材 URL；
- 不含 React、Remotion、DOM、任意 CSS、回调或 Renderer 私有参数；
- 不含 Project/Skill 权限与数据库读取需求；provenance digest 仅作身份事实；
- Renderer 不读 DB、不知用户/Project/Skill，不决定内容；
- preview、首次渲染、重试和交付 probe 使用同一家族语义。

### 11.2 Adapter 与预览

`packages/video-spec` 及纯时间/插值求值不得 import Remotion。Remotion 只存在于其 adapter；未来替代实现消费同一 video-spec。

服务端 RenderAdapter 与客户端 PreviewAdapter 分家。首版可用 Remotion 实现两者，但 Chat 组件不得散落 Remotion Player 依赖；更换实现时必须有对应预览或明确的服务端预览方案。

商业许可要求把替代实现作为真实约束；具体授权条款另按官方文本与采购判断核对。每个 adapter 必须声明能力，不支持的文字分割、网页相机、Bezier、Transition 或音频能力明确失败，不静默降级。

代表性验收至少覆盖：网页相机、整体与逐字动画、多段 scale + Bezier、Scene 边界、字幕、音乐压拍、旁白、多个时间点帧对照和真实音轨检查。架构隔离不等于替代实现零成本。

## 12. 目标目录与新旧代码处置

本节是**目标代码归属和新旧处置的唯一目录合同**，不是当前仓库树。A/B/C 按实际职责逐批建文件，不提前创建空骨架；共享文件只修改相关分支，不整目录删除。表的 TARGET 归属登记于 MODULE_ARCHITECTURE §4.2；当前代码地图仍描述现状。

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
│   │   ├── storyboard.py                保存版 → canonical 分镜 DTO
│   │   ├── video_spec.py                保存版 + 已准备素材 → video-spec
│   │   ├── service.py                   design/revise/read 共用应用服务，B
│   │   ├── director.py                  创意调用装配；复用 agents harness，B
│   │   ├── grounding.py                 引用/事实与网页视图绑定校验，B
│   │   └── templates.py                 VideoTemplate 实例化与 Preset 展开，B
│   ├── tools/video/                     通用付费执行，不拥有作品内容，A/B
│   │   ├── __init__.py / node.py         produce_video 声明、估价、准备与执行
│   │   ├── params.py                    版本引用与制作输入参数
│   │   ├── narration.py                 固定切点、有界语速、真实音频准备
│   │   └── narration_store.py           合成复用、占位/接管/完成与失败恢复
│   ├── skills/
│   │   ├── __init__.py                  保留并扩展内置包加载，不另建注册表
│   │   ├── launch-film/
│   │   │   ├── SKILL.md                 保留创作工艺，移除专属执行器依赖
│   │   │   └── video-template.json      新声明式固定骨架，B
│   │   ├── store.py                     用户 Skill/SkillVersion，C
│   │   └── import_skill.py              不可信文档包解析与能力差异报告，C
│   ├── prompts/
│   │   ├── video_director.j2            通用导演输入/输出合同，B
│   │   └── chat/                       原地收敛通用设计/修订/呈现/授权规则
│   ├── models/tables.py                 原地新增/退役 ORM 行，不复制第二套 Base
│   ├── models/schemas.py                共用 Chat/Output DTO；领域模型引用 editing
│   ├── chat/                           保留服务与双入口，共用 editing service
│   ├── pipeline/                       保留执行/渲染/交付机制，改视频分派与版本引用
│   └── platform/                       保留费用与存储能力，更新视频配置/计量接缝
├── migrations/versions/                增量 schema 迁移；不删除已应用迁移历史
├── tests/                              按现有布局增加 editing/video 覆盖与旅程
└── scripts/                            架构门/剧本原地修改；诊断工具按消费者处置

packages/video-spec/                    新 renderer-neutral 契约，A
└── src/
    ├── schema.ts                       唯一 TS 渲染 schema/type
    ├── timing.ts / animation.ts         纯量化/插值；无 React/Remotion
    └── index.ts                        公开契约；golden fixtures 随包测试维护

apps/render/src/
├── server.ts / stage.ts / artifacts.ts  原地扩 video 分派；保留共享服务
├── video/
│   ├── index.ts / capabilities.ts       adapter 边界与能力声明
│   └── remotion/                       第一实现；新 video 链的 Remotion 依赖限于此 adapter
│       ├── render.ts / entry.tsx / Root.tsx
│       └── Video.tsx / components.tsx
└── render.ts                           旧 Clip driver 保留

apps/web/src/
├── components/chat/video/
│   ├── StoryboardCard.tsx               canonical 分镜呈现，B
│   ├── CompositionPreview.tsx           版本化最小预览，B
│   ├── preview/                        PreviewAdapter；先复用播放器/服务端预览
│   └── inspectors/                     完整 Clip/Object/Scrub 交互，D4
├── components/chat/                    现有 Chat/产物卡原地接线
├── components/mentions/                复用 picker，不新建第二 @ 体系
└── lib/                                版本 DTO、mentions、SSE 原地接线
```

目录树标的是职责座位，不要求文件名与纯函数一一对应；合并小文件可以，但跨内容/执行/渲染边界的移动必须更新本合同。`design_video / revise_video / get_video_version` 是 Chat action，注册/适配在现有 `chat/turn_tools.py` 与 plan/propose 路径，共用 editing/service；只有 `produce_video` 是制作节点，不把设计工具都注册成付费 DAG 节点。

### 12.2 当前代码 → 目标处置

| 当前实际位置 | 处理与目标 | 阶段 / 删除条件 |
|---|---|---|
| `tools/film/storyboard.py` | **拆分后删除**：固定骨架 → Skill JSON；时间/校验/grounding/spec → editing 对应文件；创意调用 → director/service；制作/估价 → tools/video/node.py；pending 信封/fallback 不迁入 | A 先做对照，B 迁有效能力并删除调用者，D 删除原文件/目录残留；不是整文件改名 |
| `tools/film/edits.py` | **重写后删除**：有效 op、change_set 与局部修改约束 → editing/edits.py + validators；FilmStoryboard patch/pending 持久化废弃 | B，目标唯一写口与真实修订通过后删 |
| `tools/film/narration.py` / `narration_store.py` | **提取重构后删除旧文件** → tools/video 同名职责；保留合成去重、原件复用与恢复，去掉 FilmStoryboard/FILM_FPS/借帧依赖，缓存归属支持跨 Chat | B，固定切点、超长、恢复和计费验证后删 |
| `models/tables.py` / `migrations/versions/` | **原地修改/新增迁移**：compositions、composition_versions、source_snapshots、Output 引用；`FilmNarration/film_narrations` 替换为 `VideoNarration/video_narrations`，不做旧行搬运；C 再增 user_skills/skill_versions | A/B/C；D 用新迁移删无消费者旧表/列，不删历史迁移文件 |
| `models/schemas.py` | **原地修改** Chat/Output payload registry 和 DTO，领域模型住 editing/schemas.py；FilmStoryboard/旧 Film 编辑/信封类型退役 | A/B 接线，D 删除无消费者旧类型；文件本身保留 |
| `chat/turn_tools.py`、`plan_turn.py`、`propose_turn.py`、`service.py`、`context.py`、`perception/executes.py` | **原地修改** action 注册、双路共享服务、显式读版、@/素材上下文、呈现回执、Start version_ref；删除复制板和无 id 默认 Film | B；保留整个 Chat 机器，不能整目录替换 |
| `prompts/film_director.j2` / `film_director_text.j2` | **合并重构后删除** → video_director.j2 + 素材类型输入装配；不保留两套作品写链 | B，网页与文本 MG 旅程通过后删旧模板 |
| `prompts/chat/_website_film.j2` / `_text_film.j2`、`chat_intent_system.j2`、`intent_router_system.j2` | **原地收敛/删专属块**：通用设计/授权规则留 Chat，固定结构归 Skill JSON，不再要求模型转录分镜；旧专用 partial 无引用时删 | B/D；主模板和其他工具规则保留 |
| `skills/launch-film/`、`skills/__init__.py`、`agents/contexts.py` / `registry.py` | **保留并修改** 内置工艺包与装配入口，加载 versioned template；更新旧“仅装配期、无用户 Skill”约束的适用范围，C 加显式用户绑定 | B/C；不删其他 Skill，不另造 agent runtime/注册表 |
| `tools/__init__.py` | **原地修改**：移除 LaunchFilm import/entry，注册 ProduceVideo；设计 action 仍在 Chat 工具面 | B；Clip 与其他 tool imports 保留 |
| `pipeline/orchestrator.py`、`step_context.py`、`graph_fill.py`、`lifecycle.py`、`run_review.py`、`outputs.py` | **原地修改** 通用 version_ref、估价、血缘、授权与交付；删除 launch_film 白名单/Film 信封特判 | B/D；不重写 create_run/执行图/共享调度 |
| `pipeline/rendering.py` / `render_probe.py`、`pipeline/routes/outputs.py` | **原地修改** family=video 的资源解析、格式/时长/音轨 probe、产物 render 准入；新视频尺寸/fps 读 spec，不复制 Film 固定常量 | A/B，D 移除 film 分支；clip 分支与共享上传/恢复保留 |
| `main.py` | **原地修改**：移除 sweep_orphan_film_draft_markers 等旧启动清理调用，有效新恢复逻辑归实际 owner | B/D；删除旧 import 前核对启动链，不能只清工具注册表 |
| `platform/configs.py`、`providers/llm/minimax.py` | **原地修改** film.usd_per_second / film_seconds 等报价和聚合接缝为通用视频计量；新键/单位全链同步，不保留双计量 | B/D；LLM provider、统一成本路径保留，不借机重写 Billing |
| `pipeline/web_capture.py`、`tools/research/capture.py` / `web.py`、资产/存储/provider 能力 | **保留复用** capture/SSRF/网页读取；editing 绑定快照与 grounding，不复制抓取器 | A/B，按实际签名接入；不是 Film 目录一起删 |
| `apps/render/src/film/`（schema/render/Root/Film/components/entry） | **重构替换后删除目录**：schema → packages/video-spec，具体画面能力 → src/video/remotion；subtitle 有效覆盖转新测试 | A 对照实现，D 无活跃消费者后删；仓库**不存在独立 packages/film-spec**，不按想象路径删除 |
| `apps/render/src/server.ts`、`stage.ts`、`artifacts.ts`、`upload.ts` | **保留/原地修改** family 分派、资源 staging、产物验证和上传；不能随 film renderer 删除服务底座 | A/B/D；Clip 当前 render.ts 路径继续工作 |
| `packages/clip/`、`tools/clips/`、reframe/dub/captions 等旧工具 | **保留** 当前 Clip 能力；不迁入 editing，不在 A–C 或 D1 删除 | 仅 D3 后续逐项等价验收后处理 |
| `ChatDock.tsx`、`OutputChatCard.tsx`、`lib/chat-stream.ts`、`lib/mentions.ts`、`components/mentions/` 与现有产物 inspector/下载 | **原地接线** 新 DTO、版本、@、播放、SSE/刷新；新视频组件住 chat/video | B，保持现有外观可用；FlowView 与其他产物 UI 不整片删除 |
| API/web/render 测试与新video fixtures | **按合同归属**：新editing/video覆盖随A/B建立；旧Film-only结构锁已退出，通用provider/配置守卫归现有通用套件，配音reuse身份守卫暂沿当前模块，B迁imports | 当前缺口归§15/VERIFICATION；D核对无旧helper悬空；共享Clip/授权/计费/身份守卫保留 |
| `scripts/film_draft_marker_drill.py` / `film_stage_ledger.py`、render scratch/scripts | **逐项审计**：旧 marker 专属工具删；仍有诊断/对照价值的先改新事实输入或保留必要证据，不因名字删除 | D；scratch 删除前核对未跟踪成果和独有 fixtures |
| 根/各应用 package.json、锁文件、Dockerfile、compose、环境配置 | **按实际依赖修改** 新 workspace 引用、打包/字体/资源路径；清临时开关和无消费者依赖 | A/B 接入、D 清理；Remotion/React 仍被 Clip 使用时不能全仓删除 |
| RENDERING、CLAUDE、README、NAMING、MODULE_ARCHITECTURE、VERIFICATION | **同步收敛** 新目标与§15有效需求、当前代码事实、共享验收各有座位；不再维护旧Film施工三件套 | A/B/D随实现更新；文档/旧实现锁退出不等于新链已验收 |

### 12.3 边界与目录验收

- `apply_composition_edits` 是内容唯一写口；store/sources 等提供受控能力，不产生绕过版本校验的第二写入口。`apply_wiring_ops` 继续守执行图。
- editing owns 内容/版本/快照，tools/video owns 制作与配音准备，skills owns 创作方法，pipeline owns Run/Output/render queue，Renderer 只消费自足 spec；不以“共用服务”名义把它们重新塞进巨型 storyboard.py。
- 表中路径以仓库根为基准；写“原地修改”的文件必须逐个核对，不把目录存在当接线完成。C 的 Skill 生命周期与 D4 Inspector 文件不属于首批 A 必建清单。
- D 删除前复跑 import/注册表/运行调用链与资源引用清单，对照每行处置结果；提交说明列实际删除/保留及理由。静态零引用不能替代真实启动、Clip 回归与新视频旅程。
- 目标目录/表归属、测试和构建引用同批更新；新文件或改名与本节不一致时先修唯一合同，不在施工文档再维护第二份目录树。

## 13. 替换与数据边界

- 不迁移既有业务数据，不写 FilmStoryboard/film-spec → CompositionVersion 的数据适配器。
- A 并行建立内容基座，旧 Film 只作行为与画面对照；B 在开发期直接替换旧 Film 专用合同，不承担旧 API/旧数据兼容，不长期双写/双读或保留缺版 fallback。可分小提交，默认切换须完成完整 Chat 旅程验收；共享 Chat/Run、权限、授权、计费与交付不变量继续保留。
- D 必须执行最终删除清理：清点旧工具、schema、分派、prompt、测试、配置、依赖与文档的活跃消费者并删除残留；清理后复跑真实旅程。只关闭入口或长期留在开关后不算退役；具体检查表归施工合同 D1。
- 生产无实际用户，本轮在独立分支直接破坏旧 Film 合同，生产就绪后合并 main；不做旧业务兼容或数据搬运。必要的 schema 变更仍须可复现；用户已授权本应用开发/生产旧数据清理/reset，执行前核对目标与 dry-run，无需为同范围重复确认。分支、部署与数据操作分工归施工合同 §0.2。
- Clip 在 A–C 不迁移、不删除；新 Composition/Track/Clip/Object 稳定并完成真实验收后，再逐项评估 reframe、segments、ASR/caption/translation、dub 等能力，确认等价后才删除旧 Clip。
- Scrub、自由 Transition 编辑、CompoundClip、多用户 Skill 市场和完整 NLE 均不属于首批。

## 14. Prohibited Behaviors

- 禁把 Project 与单部影片身份合并，禁用“Chat 最新产物”隐式替代 Composition/版本；禁再引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
- 禁把 Scene/Track/Clip/TextPart 展开成执行图节点，或让 Canvas 成为版本真相。
- 禁让 `visual_description` 描述不存在的元素/动画，或在视觉修改后保留失实摘要。
- 禁把每个字符默认持久化为独立 Clip，禁文本变更后静默错配动画。
- 禁让 Skill 执行任意脚本、授予工具权限、绕过 grounding/授权/计费或拥有第二执行链。
- 禁让 Renderer 概念进入 CompositionVersion、VideoTemplate 或 video-spec。
- 禁以“未来可替换”为由把 PreviewAdapter、能力矩阵和替代实现验收省略。
- 禁建设旧 Film 数据迁移层；也不得借“不迁移数据”提前删除仍需对照的当前实现。
- 禁把 Recipe 改名后仍暗含执行；PromptTemplate 永远只是可见预填。

## 15. 新链必须承接的产品语义与验收缺口

本节是旧影片需求的当前归位，不保存旧实现方案。旧 Film 任务与专属实现测试退出不代表能力已完成；A/B 仍待施工，新视频没有覆盖的能力不能因为剩余测试通过而宣称生产就绪。

- **输入与意图**：网页源与文字源走同一作品链；用户原文、创作要求、生成稿区分来源。未决定逐字展示还是改编时问最影响方向的一题，不一次收齐参数；明确委托/明确方向直接设计。零原文但有创作要求的自由 MG 合法，不伪造来源。verbatim 模式每段恰好一次、按原文顺序、零改写增删，换行不丢字；容量不足点名段落/差额/处置，不无限缩字硬塞。
- **用户约束与技术政策**：用户要求、agent 选择和默认值分别记录来源。当前 120s/3600帧等仍运行的政策只作旧链事实；新链以设置/制作政策冻结，139s 若不支持就明确拒绝，不截断。画幅变体、字体枚举/vendor 字体、网页录屏与声音选择/试听的需求继续保留；不建设旧 set_aspect/指纹迁移兼容路径。
- **音频三态**：未指定/明确关闭/明确选定分开；用户选择/关闭优先，其次既有版本选择，再 persona/default，关闭不被默认重开。voice_id、实际音乐 track/resource 与参数须在版本/执行输入固定，mood 不是曲目身份。复用 hash 包含归一化文字、已解 voice、语言、合成配置/模型，保留原速原件；运行适配另算，成功准备可恢复。
- **试听后置边界**：用户要求先听时给真实可播放样例并等待，优先现有资源，否则显式短样例成本；不预生成全库或整片旁白。试听选择与成片同配置，重开已有旁白不强迫整片重设计。声音目录/试听 UI 后续排期，不伪装本批已完成。
- **安全采集与 grounding**：capture/SSRF、章节/视图/元素身份与引用校验留代码；网页屏上事实引用可解析，旁白可复述但不编造事实。element focus 由已识别元素盒推导，不盲猜坐标；当前有限同 host 子页采集沿已有 policy（最多3个子页、过滤 login/blog/legal、不递归外站）。Chrome 不可用要诚实缺截图/能力，不能伪造视图；录屏不等于截图推拉，不默认支持登录、系统声音或复杂操作。
- **独立视觉与字幕**：默认字幕 ON、旁白默认 OFF，显式开关与既有版本继承必须可读、可编辑；无旁白不等于无字幕/音乐。字幕最后 cue、文字最后入场/停留必须落入实际执行窗。纯 slide 不混入 opacity/blur/rise，单文字淡出不影响背景或兄弟对象；presence 的 absent/null/0 各有含义。逐字/逐行间隔量化累计偏差须按最终落点呈现，不拿单值误差冒充整段误差。
- **局部修改**：只改末幕时前幕保持；clear grouping、切换文字组织单位时显式重算/清除旧 timing，禁止旧字符节奏静默套成行节奏。超窗明确冲突，不截短/重排素材。严格样例：30fps、开始0.3s、间隔0.5s、时长0.4s，两行分别 f9→f21、f24→f36，第二行 f24 前不可见；以真实动态帧验证，不能锁旧字段名/公式。
- **有界设计**：共享墙钟与调用硬上限贯穿初稿、候选/schema修复、多模态降级，嵌套重试不刷新；设计最多10次生成调用作为首发验收上限，系统错误不交导演改文案。无进展诚实终止、旧版保留，失败不留半稿/假 busy；完整字段级修复只有真实成功率/保留范围要求触发时才做。旧固定 worker fallback、30fps唯一格式与三段宏 DAG 不继承为新实现义务。
- **B 真实旅程**：网页/MG 双源；首稿完整呈现→下一轮制作；普通修订与改完直接做；auto/ask、费用/制作意图、copy drift/unmet condition；跨 Chat @ 与过期引用；声音/音乐/原声独立试听、字幕开关/极短cue、完整章节标题/reveal可读性；8幕仅改末幕严格slide；真实断网/停止/迟到/60s无回复、刷新与WorkSegment/交付卡。现有on_row_append未接线/显示与执行一致性缺口需在canonical payload新链验证，不沿旧例外继续打补丁。
- **A/B 新覆盖缺口**：Composition原子版本/请求幂等/跨Chat权限，三时间域与切分/转场，TextPart/字体排版，renderer-neutral spec、实际音轨与动态对照，Start版本和执行manifest、重试计费都必须新建合同覆盖。旧 Film-only测试退役后这些项目仍明确未验证，不要求旧接口重绿，也不以删测减少失败数报通过。
- **共享能力保留**：配音身份/有界适配、provider完成语义、通用配置/计量与授权/执行fencing守卫继续有效，按真实模块归测试。Clip尚未迁移，独立Clip编辑、轨道、字幕、归档与渲染测试继续运行。
