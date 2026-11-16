# 宣传视频核心 Skill、统一 Skill 包与视频后续施工

> Status: 验收与精确编辑开放（2026-11-16）。优先级见 [PROGRESS](../PROGRESS.md)，长期契约见 [VIDEO_PROJECT](../VIDEO_PROJECT.md)，创作循环见 [Composition 创作循环](composition-authoring-context-convergence.md)。

## 0. 目标与硬边界

建立内置与外置 Skill 共用的渐进式创作工作流，让 Agent 像工程师一样按需读文档、读参考源码和查看真实预览，再为当前作品编写视觉来源。`promo-video` 是首个完整消费者，用户面名称为「宣传视频制作」。

- 不引入 `ShotMethod`、`ShotRecipe`、运行期 ShotRegistry、动态镜头 import 或通用插件平台。镜头库是 Skill 包内的创作资源，不是新的作品层。
- 不新增作品根、第二意图面、第二内容写口或第二生产链。作品内容仍只经 `apply_composition_edits` 形成 CompositionVersion。
- Provider 只能通过 harness 的有界只读工具获取当前绑定 SkillVersion 的内容；不能自行访问本地路径、外站或业务数据库。
- 外部卡片、TSX、模板和脚本均为不可信参考。外部脚本永不直接执行，外部 TSX 不因被读取而获得运行资格。
- Generator 允许 LLM 自主编写完整 Remotion 工程：多文件、多组件、共享 helper、Composition 注册与内部时间线均可由创作需要决定。限制的是系统权限、依赖与资源，不是工程内部的创作结构。
- 完整 Remotion 工程只作为 Generator 的不可变生产来源，经隔离 runner 烘焙为固定媒体；最终 video-spec 仍只消费固定媒体，不含 React/Remotion、生成任务或模型请求。
- Home demo 展示精心校准的有限强组合，不是能力全集。Skill、template 和 arc 只决定首稿起点；作品出生后，用户可在 Chat 改 arc、场景、镜头、素材、文字、声音和可用 Generator。
- 已注册且验收可用的能力应能从 Chat 询问和使用。
- Skill 不进入 worker；修订不重新执行外部包。制作继续钉版本、来源、依赖和 digest，恢复不重新创作。
- 支付、通用 Chat 基础设施和其他非 Video Project 工作仍归各自合同，不借本计划扩大范围。

## 1. 统一 Skill 包

内置包位于 `app/skills/<skill_id>/`，随应用部署、内部注册和使用，不开放用户自助安装；外部包持久化为 owner 隔离、不可变 SkillVersion，仅用于内部登记、测试与历史 provenance，不承诺 Claude Code / Codex 插件运行时兼容。两者支持同一组逻辑资源：

```text
SKILL.md
references/
├── shots/<category>/<card>.md
└── sequences/<arc>.md
gallery/
├── api/library.json
└── media/...
demos/
└── <category>/<card>/
    ├── 参考源码
    ├── fixtures / textures
    └── 所需共享资源与依赖说明
template/
└── 可选的完整起始作品、VideoTemplate 与预览
```

分类 id 固定复用：

```text
opening / camera / transition / typography / ui-entrance
interaction / data / effects / rhythm / outro
```

| 资源 | 职责 |
|---|---|
| `SKILL.md` | 任务判断、创作路线与工作流入口 |
| shot cards | 镜头意图、适用场景、能量、参数、已知坑与参考实现位置 |
| sequences | 可选全片 arc、段位、节奏与候选镜头 |
| `library.json` | 静态发现、卡名/变体消歧和预览定位；不是执行注册表 |
| `demos/` | 调校后的参考源码与依赖事实；常规工具只读 |
| `template/` | 可选首稿起点，以及显式声明的隔离 Generator 资源 |

`promo-video` 六类资源齐全。外部包允许缺少 template 或部分资源，能力报告必须明示，不伪造完整度。共享 `assets/lib`、fixtures 和纹理作为 demo 的声明依赖处理，不另建作品概念。

## 2. 命名与 Generator 合同

`GeneratorObject.runtime` 改为 `GeneratorObject.producer`，生产方式的跨栈名称为：

| producer | 含义 |
|---|---|
| `draw-2d` | Agent 编写受控 2D 绘制程序，生产固定图片或视频 |
| `remotion-project` | Agent 编写完整、不可变的 Remotion 工程，经隔离 runner 生产固定媒体 |
| `image-generation` | 保存模型图像生成请求，授权制作后生成并固定图片 |

版本由 schema_version、内容/程序 digest、依赖锁和执行配置承担，不把 `v1` 塞进能力名。旧标识符只在当前实现证据中保留到命名迁移完成，不作为目标名称继续扩展。

`remotion-project` 的来源至少包含：文件集合及逐文件 digest、入口、Composition id、props/schema、固定资源清单、依赖锁、输出约束和执行摘要。预览与制作对同一来源 digest 使用同一固定结果；修订只使受影响生产结果失效。需要独立精修的重要文字、字幕和音频仍优先保留为原生对象，不把整片烘焙后谎称内部可编辑。

## 3. 渐进式创作工作流

绑定 Skill → 在同一普通 Chat 工具循环按需读取方法/预览、采集和准备规范资源 → 多次写入同一服务端工作草稿 → 最终完整校验并经唯一写口保存 → 完整分镜与按需局部 Scrub → 局部反馈/修订 → 既有授权与固定生产。

镜头卡、sequence、demo 是创作资源，不是强制阶段或执行注册表；固定模板由代码展开，自由创作逐完整实体写入，Generator 在目标 Clip 范围内进行有界代码创作和预览纠错。作品出生后，后续修订与 worker 不依赖 Skill 重新创作。

`list_skill_shots` / `read_skill_reference` / `read_skill_demo` / `get_skill_preview` 保留为有 owner/路径/文本/媒体边界的包读取能力。模型可见工具按当前绑定 Skill、活动草稿、保存版本、Output 与真实制作意图逐轮投影，不把全部视频 schema 和无目标修订工具同场发送；执行端权限和状态校验不变。

保留完整工具结果按 call id 回传、owner/来源/几何/唯一写口、总预算、取消/失败真实性、制作与费用授权；设计失败不显示成功，不虚构零消耗，不自动重买设计。局部 schema/语义错误只修目标范围，禁止 fresh-design 整片重交；未保存工作草稿不冒充作品版本。具体协议、文件级删改和验收归 [创作循环合同](composition-authoring-context-convergence.md)，视觉质量与原生可修要求仍归 P6+P7。

## 4. 实施基线与剩余验收

- **视频作品**：网页、原生 MG、混合实拍、受控程序、生成图片、旁白和限定时间修订已有代表旅程。仍需复验跨 Chat 的授权指认、过期版本冲突、时间改动与言语编辑拒绝。已有录音对齐、worker 恢复、READY 不可变、失效后重建与多语言词锚仍需验收。
- **Skill**：已验证外部包持久化、owner 隔离、版本不可变、Strict/Adaptive 与 held-out 资源样本。仍需验收同一版本在刷新/移动端一致绑定，Home 与手动选择器同载荷，正常 Chat 授权、计费、固定交付和修订；旧作品应独立于之后的包版本。验证越权素材、无权工具、绕过授权和恶意包声明均被拒绝。部署方安装的 `/promo-video` 固定绑定 Shotcraft `bdd94be16d60fa8f`。
- **素材与预览**：CaptureRequest 支持有界集合、共同 blank plate、透明元素及部分成功，真实 Chat 采集/首稿与 DB fixture 仍需复验；批 2 `page_script` 未实现。SFX、Preset、局部 Scrub 已有代表验证，保留试听、刷新回放、偏移、响度、修订与 preview/render parity 验收。
- **Home**：已接文字动画、产品宣传与知识讲解候选样片，应用空态按真实可用内容展示。候选样片需连续看片、实际试听和发布授权；口播需指定素材或获授权的真人素材。

## 5. 当前验收与后续编辑

### P6+P7——集中测试、真实验收、Renderer 生产门与样片

**范围**：

- 在整个 promo-video 创作链接通后集中补测试：只覆盖真实用户旅程与核心 API/DB 合同，包括新旧命名读兼容、唯一写口、PackageReader 权限/digest、渐进读取、完整工程来源与 renderer-neutral、外部 held-out 和 arc/局部修订。
- 按实际改动运行 `test/core`、当前 `JOURNEYS` 与 Web/render 检查；真实付费调用在本批统一授权和执行，不在施工批分散烧钱。
- 同批完成 Remotion 许可或替代实现结论，覆盖最终 Renderer 与上游 runner；完成能力矩阵、golden fixtures、动态帧/音轨对照、失败闭、PreviewAdapter 和真实渲染成本测量。不支持能力在 Start 前暴露。
- 为宣传视频制作少量不同 arc 的强组合样片；另以 Repurposer 自我介绍视频综合验证 Chat/Skill、外部 SkillVersion、原生对象和 Generator 的创作与修订，不伪造工具、耗时或执行结果。
- 对现有文字动画、产品宣传和知识讲解样片完成用户连续看片与实际试听；口播先恢复指定素材或取得明确授权真人素材。收口 SFX、Preset、CapturePlan、词锚、回复事实、刷新回放和共享查看器。
- 用户明确授权后才逐张公开上架；内部预跑、空态和机制证据不冒充公开 Gallery 通过。

**出口**：测试、许可、能力、预览、成本和失败恢复均有当前证据；机制、动态画面、实际听感、回复事实与 Home 入口分别验收。未通过不得生产发布，未运行项保持开放。

**当前状态**：本地 macOS 隔离 runner 已有真实 bake、固定资源与解码证据。固定资源上限为 64 个、单件 16 MiB、合计 32 MiB。部署需显式启用 component bake。部署环境隔离、超时清理、资源限制、成本与 Remotion 许可或替代结论仍是发布门。轮次共享上下文、工作草稿和局部反馈按 [创作循环合同](composition-authoring-context-convergence.md) 验收。

#### P6+P7 视觉质量代表镜头施工

当前先以 OxValue 真实估值卡完成一个约 6–8 秒的代表镜头，再扩成完整宣传片。四批是 P6+P7 内部的顺序切片，不新增作品根、生产链、运行期镜头注册表或 renderer 分支；保存、可播放和文件交付不等于视觉验收通过。

代表镜头的固定动作弧为：整页建立场景 → 聚焦并压暗周围 → 推向真实估值卡 → 卡片独立抬升并短暂悬浮 → 真实指标逐项展开 → 卡片归位 → 稳定阅读停留。£18.7m / 94% / High / 03 等内容必须来自冻结来源；不得用整页缩放冒充主体运动，不得用虚构中间数字做滚动。重要新增文案保留原生身份，网页原有文字仍属于真实截图像素。

**视觉质量批 1——运镜语义与网页文字安全区**

- 工作草稿使用既有网页 focus 运镜、对象 Animation 与几何校验；`push_in` 只表示无目标的整页轻推，有明确元素目标时使用 `motion="focus"` 与既有相机关键帧能力。描述与执行不一致、缺少冻结元素或越界的候选在唯一写口前拒绝，不重建一套 promo Direction。
- 在 `editing/grounding.py` 增加纯几何映射，将冻结 view 的元素盒按实际 base layout/fit 映射到归一化画布。新原生 TextLayer 必须完整处于画布内；普通网页 view 上不得覆盖已采集的可见 `heading/text/button`。blank plate 只豁免被正式移除的目标区域，其余文字仍参与避让；不解析 `visual_description` 代替几何校验。
- 校验诊断指出场景、layer 与冲突元素，并进入现有一次汇总修正； Shape 出血、非目标装饰和既有不可变版本不在本批重写。无真实元素盒时不发明坐标，最终可读性仍由成片帧验收。

**当前实施状态**：批 1 已落码；2026-11-06 指定七座验收测试在最小修正后为 183 passed，包含运镜冲突、文字边界/网页碰撞与阅读窗覆盖。真实同源 AgentVeil 参考已渲染并抽帧；OxValue 新项目仍在有界 Chat 验收，不能以纯几何通过代替成片文字、换行和字体可读性。
- 出口：`focus` 沿用既有真实元素取景，非法组合在保存前被拒绝；OxValue 当前出现的中文压英文标题与文字越界形态有确定性拒绝覆盖。纯函数测试归现有 promo/capture 测试座，不新增事故编号套件。

**视觉质量批 2——真实网页资源与 Generator 原生层**

- 在 `editing/sources.py` 保留窄的 web-view 派生 Snapshot 注册，由普通 Chat 的 `capture_web` / `prepare_video_materials` 对每个成功视图调用；失败 output/member 只进入有界 issues，不撤回其他派生。完整视图、共同 blank plate、普通元素纹理和透明 cutout 分别注册为普通 `kind="image"` Snapshot；identity 包含 `web_snapshot_id + view_id + view_digest`，storage/digest 指向真实 PNG，`meta` 保存来源 Snapshot、通用 state/output/target/member 血缘及内部执行配对。透明 cutout 继续派生全画布固定资源。
- 派生图片进入本次 Director 的精确资源清单与最终 facts，复用现有 `RemotionResource`、权限、digest、bake、缓存和恢复；不直接把 `kind="web"` 的清单字节放行给 `_fixed_resources()`，不给资源 schema 增加第二套身份。cutout 分辨率不足以支撑输出特写时失败或重新采集，不把低清放大称为高清。
- Generator 场景与重要文案逐步写入工作草稿；定向修订提交完整所属 Track/Clip：GeneratorObject 承载受控视觉程序，独立 TextObject/ShapeObject 保留原生位置、时间窗与可精修身份。来源引用经 `copy_references(snapshot_id, line_id)` 确定性回填，video-spec 不变。只改原生文字不得使 Generator digest 或固定媒体失效，修改 Generator 不得重写未改原生层。
- 本地真实制作要求 API 与 render 同时开启 `COMPONENT_BAKE_ENABLED=true`，并通过 `/health` 证实真实隔离。保存版制作前的有界 Generator 预览复用同一 runner/digest 缓存，不是 Output；正式制作仍从授权后的 `produce_video` 开始。当前仅有 macOS Seatbelt 隔离，本地样片通过不等于其他部署环境已开放。

**视觉质量批 3——参考方法、真实预览与声音节拍**

- 只新增一个真实消费者 `interaction/spotlight-card`：原创 demo、固定 fixtures、真实 MP4 与由该 MP4 抽出的带时间标注 timeline JPEG，登记 `library.json` 和适用的 sequence。卡片写明 plate/cutout、共享相机、抬升/悬浮/归位、高度阴影、相机锁定后的原生指标与静止阅读段；外部参考源码仍只读不执行。
- 方法与真实预览按当前任务需要读取并复用成功事实；本代表镜头显式要求查看 spotlight 参考，须保留真实读取证据。旧多 Director 研究/提交门已删除，不作为目标工作流恢复；现有 owner、媒体大小与总用量边界保留，不另建 loop。
- 本次代表镜头的 provenance 必须证明指定预览被真实读取（有可用媒体时 `media_files>0`）；现有采集工具取得真实配对 plate/cutout，正式 Composition 包含 Generator 与独立原生指标对象。不以必须生成 ShotDraft/Direction 为验收目标。无预览的外部包记录真实不可用事实，不伪造读取。
- 声音复用现有 SFX 搜索、固定 Snapshot 与 Composition 原生音轨；只给锁定、抬升、指标展开、归位等主要动作选点，不按配额堆音效，不强制旁白。

**视觉质量批 4——逐镜动作复核与样片终审**

- `ReviewVideoArgs` 增加精确的可选 `motion_scene_id`；`tools/video/review.py` 对该 Scene 抽取有界的有序帧序列，报告记录实际场景、时间窗、采样间隔与 `motion_reviewed_scene_ids`，缓存身份和 review schema 同步升级。未取动作序列的场景仍明确未检查连续运动；reviewer 只能依据实际序列判断该镜头的动作阶段与衔接。
- 自动音频检查继续区分 PCM/RMS/peak 与主观听感，不把信号存在写成音画同步或通过试听。整条样片必须连续看片与实际试听；发现问题后走 `revise_video` 形成新版本并复核确切 Output。

**代表镜头与完整片出口**

- 代表镜头：真实卡片独立抬升，plate/cutout 全程对齐，五个动作阶段可辨认，真实指标准确，重要新增文字原生可修，零遮挡/越界/明显低清放大；只改一条原生指标时 Generator digest 与固定媒体不变。
- 完整片：代表镜头通过后，再组合原生开场、产品证据、核心技术/能力、治理流程与原生收尾；时长服务内容，不用长静置截图填片。完成连续看片、试听、一次真实 Chat 局部修订与重新交付后才称视觉样片通过。
- 测试只归核心 API/DB 合同与宣传视频真实旅程：纯几何/资源身份/时间窗、唯一写口、权限、renderer-neutral、重试复用，以及 `builtin_promo_skill` 的 plate → Generator + 原生层 → 制作 → 动作审片 → 只改文字不重 bake。prompt 改动由相关真实旅程验收；模型、采集、声音与渲染分别登记，不以静态检查代替。

**剩余视觉与声音验收**：

- 用真实网页核对 overflow 浮层、透明 cutout 与 backdrop blur、panel 裁切、文字安全区和相邻幕衔接。
- 对已保存片段复查 `motion_scene_id`、原生文字修订、固定媒体复用、SSE 的结果呈现与失败反馈。代表镜头与完整片已技术交付，真实首稿仍需验证有界错误恢复、arc 血缘、同题不同简报及静态资源守卫的最新行为。
- 对候选成片独立完成连续主观看片、听感、音画同步和终审。抽帧与完整解码分别证明画面样本与技术可播性。

### P8——Chat-only 与旧产品、交付概念彻底退役

**当前合同**：

- 用户在同一个全页 Chat 完成创作、分镜、反馈、授权、制作、交付和观看。普通请求默认先出可编辑分镜，确认后制作固定 CompositionVersion；后台素材理解、语音准备和执行文件仍走现有机制。Run 开始或完成不自动展开 Canvas，也不把全页 Chat 切成侧栏。
- 每条交付消息只从自己的 `output_refs` 解出本次精确视频，保留视频卡、播放、下载、@ 引用和刷新恢复。同一 Chat 可以有多条归属各自消息的交付；重复确认去重。跨交付的多 Output 目录、画廊、平铺、上一条/下一条、缩略导航和用户侧版本树不再存在。CompositionVersion、内部 Output、Run 与执行事实继续承重。
- `article / post / quote / quotes / quote_frame / carousel` 及其 Recipe、工具、agent、prompt、schema、DAG 分支、payload、Graph 投影、结果卡、下载和旧样片生成入口全部退役。普通 Chat 仍可直接用持久化 Markdown 回答文案请求，不增加专用文案工具、隐藏产物类型或专项旅程。
- `launch-film` 的新入口、固定模板和默认回退已删除。`/promo-video` 继续绑定部署方内部安装的固定 Shotcraft 版本 `bdd94be16d60fa8f`，不恢复仓库自研 Promo 包，也不扩展用户自助安装。
- Canvas 用户入口与工作区布局切换已退出，仅保留素材节点、普通手动节点及连线的基础 CRUD 与交互底座，后续独立迭代，不作为本轮验收项。`apply_wiring_ops` 按 ops 顺序执行，`add_node.after` 与显式 connect 去重；旧产物投影、传统任务节点和 Clip 专用节点不再生成。Chat 的 plan/propose 两路共用 `edit_manual_graph`，工具 schema 是明确的手动节点判别联合，不是松散任务 Op。
- Chat 是唯一制作入口，项目 `/generate` 已删除。DAG 继续作为内部执行内核，RunPlan 只接受 `produce_video` 与 `prepare_narration`。既有授权、估价、计费、认领、fencing、渲染、上传、恢复和交付机制保留，不重写 Run 引擎。

**指定验收已通过**：`promo_short_confirmation_delivery` 覆盖 URL 首稿、完整 ACK、固定版本、原 Chat 唯一交付和重复确认幂等。普通 Markdown 请求零版本与 Run，手动 Graph 的正常 Chat 基础 CRUD 已验证。

**迁移核验**：`g7d4a1c9e2f6_retire_legacy_editor_state.py` 移除退役编辑/探索表与对应 Graph 外键，历史 migration 保留。定向清理复查无剩余目标，保留源素材、用户消息、新作品、账本和必要共享血缘。对象存储删除在数据库提交后执行，可重试；其他目标环境按迁移操作规程另行验证。

### P9——旧 Clip / ClipSpec 退役与媒体能力内化

**当前合同**：

- ASR 是素材事实，冻结原片、逐字时间、源窗、原声和必要 provenance。`editing/source_selection.py` 用真实词轴与语义选择派生并校验 `source_range`，多个段可以组成同一 Composition；用户不需要提供轨道、时间码或原始 Op。初始选段进入普通 Video Clip。
- 本批不实现旧式二次裁短，也不恢复 `SetClipDurationAction`。保留的底座是初始 source window、Composition 的实际视口，以及固定 `layout / fit / transform`。后续裁剪能力若独立建设，应从该对象与视口模型出发，不复活旧裁切任务。旧逐帧跟拍、说话人切镜和 `crop_track` 已删除。视频视觉 `speaker_map` 处理器与权重消费者已退出；图片构图锚点及仍有消费者的 YuNet/OpenCV 保留。
- `editing/source_captions.py` 将原片 ASR 投影为普通 caption Track 上的原生 TextObject；`editing/narration_audio.py` 将 READY NarrationAlignment 的语音与词锚投影为普通 dialogue AudioObject 和原生字幕。需要独立布局时使用多条普通 caption Track。两种来源共用对象、校验和时间内核，不建立专用字幕/配音 Output、作品根、时间线、渲染 family 或制作链。字幕默认不添加背板；用户手改的 independent 字幕不被重新派生覆盖。
- 配音复用现有 TTS 与素材冻结，产出有来源和 digest 的可复用音频素材；`dialogue` 是默认轨道用途，`music` 仍可按普通剪辑用途使用。放置、源窗、增益、原声保留与混音由普通 Clip/Track 决定。`editing/audio.py`、`aligned_narration.py`、`web_shots.py` 只保留现役公共能力。
- 旧 Clip 的注册、任务编译、专用执行、独立编辑器、operations、路由和 Canvas 节点已删除。`pipeline/clip_spec.py`、旧 render clip 分支、`packages/clip`、在线 ClipSpec 联合类型、旧字幕字段和旧 `outputs → Clip tasks` 转换均已删除。`apps/render/src/audio.ts` 是 `normalizeLoudness` 的新家，renderer 只接受 video-spec。Docker 与 workspace 只复制/引用现役 video-spec、video-remotion 包。

**指定验收已通过**：真实上传走 ASR、自然语言选段、9:16、原生字幕和 READY 配音，保存版保留手改字幕，固定版本交付后重复确认无额外费用或作品。上传失败缓存重传复用同 Run、Output 和 spec，真实 Chrome 播放至结束并在硬刷新后恢复同一视频。

### P10——Scrub 与 Inspector 精确编辑

**范围**：

- 在稳定 CompositionVersion、Clip/Object id、PreviewAdapter 与唯一内容写口上，先贯通一个明确版本、时间点、目标对象和真实属性。
- 连续调整只更新本地草稿；Apply 携带 base_ref 与完整所属 Clip/Track 实体形成一个新版本，保留取消、冲突、失败回滚和键盘可用性。
- 音频 Inspector 复用现有真实 WaveformPlayer；mousemove、seek、试听和调值不调 LLM、不建版本、不触发付费渲染。
- 旧消息钉旧版本，只有当前版本可编辑；多对象和更多属性按真实消费者后续扩展，制作前整片预览永不开放，不建设完整 NLE。

**出口**：至少一个视觉属性完成本地预览、Apply、版本血缘、冲突与刷新验收；Chat 修订不被强制迁移到独立编辑器。音频属性与完整 Inspector 仍是后续范围。

## 6. 参考产品的可学习边界

video-shotcraft 的 Motion Workbench 是交付后的浏览器微调工具，不是 Skill 加载器。可学习其稳定镜头/clip 身份、typed props/schema、逐镜修订和 Preview/Render 一致性；本计划不复制完整 NLE，也不在交付后强制打开另一编辑器。精确 Inspector 归 P10。

社区存在 Claude + Remotion Skill，可学习其“生成 → 渲染 → 查看实际帧 → 修复”的闭环和 Remotion API 创作知识；它不是 Anthropic 官方的「Claude Motion」产品，不改变本计划的权限与版本边界。
