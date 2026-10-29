# Video Project 四阶段施工与验收

> Status: 施工中（2026-10-29）。目标架构唯一事实源 = [VIDEO_PROJECT](../VIDEO_PROJECT.md)，所有阶段先读其 §0 创作方针；本文维护 A/B/C/D 阶段及 B 内增量批次、依赖与验收。B-I～VI 当前已声明出口的实现、证据与保留欠账见 §2.0，完整 B 未封板。B-IV 原生图形与 drawing-v1 Generator 两个出口、B-V 首个 image-v1 单图消费者已分别通过真实 Chat 验收；B-VI 及后续出口见 §2.5。A 最小基座及剩余能力见 §1.2–1.3。当前批次与优先级只归 [PROGRESS §0](../PROGRESS.md)，通用接手入口见 §9。
>
> **数据边界：不迁移既有业务数据。**新表、新列、索引和约束仍需 Alembic；旧 Film 数据适配器、旧板 digest 迁移和全库回填均不建设。生产环境无实际用户；用户已授权为本轮重构破坏旧业务数据，必要时可清理/reset 本应用开发与生产数据，无需为同一范围重复确认。执行前核对目标实例、数据范围和 dry-run，不扩大到其他项目或基础设施；本次文档更新不执行清库。

## 0. 开工规则与总边界

1. 新链为 Project/Chat → Composition → CompositionVersion；同一 Chat 可分别持续修订多部影片，全局 @ 引用不受来源 Chat 限制。不引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
2. A/B 建立服务官网片、MG与混合内容视频的共同底座；B 的程序化/生成媒体按 §2.5 分批交付，不与当前官网片修复混做。C 提供个人创作方法复用。旧 Film 用作行为/画面对照，旧 Clip 产品迁移/删除仍后置。
3. 开发期不承担旧 Film API、旧数据或旧内部结构的兼容承诺。A 保留旧链作样片对照；B 集中替换注册表→prompt→工具菜单→Start/Run→Output 的 Film 专用接缝，只保留一个有效设计/制作家族，不长期双写、双读或保留自动 fallback。临时 feature flag 仅服务开发隔离，D 必须清理。
4. Graph/Run/worker/render ownership 复用，不建第二执行引擎。Scene、Track、Clip、TextPart 不成为执行图节点。
5. `pending_brief` 只保留通用计划/问题/确认状态；CompositionVersion 是唯一作品内容真相。
6. `apply_composition_edits` 与 `apply_wiring_ops` 分别守作品内容和执行图，路由不得绕写。
7. 不擅自调用付费模型、TTS、采集或渲染；真实验证按用户授权和预算执行。未运行的检查必须写“未运行”。
8. 保留工作区与并行成果，不用 reset/checkout/stash 制造基线；每批在当前工作树重新核对代码与验证，不转信其他会话的基线绿。
9. 新模块、表、队列和名词在首批代码同批登记 `MODULE_ARCHITECTURE.md`、`NAMING.md`、`docs/README.md`；新 prompt 走当前 prompt 写作法与 prompt_gate。
10. 旧 Film 固定骨架、pending信封、legacy指纹/schema 专属测试不再是兼容目标；有效创作/视听要求归 VIDEO_PROJECT §15，旧结构套件不要求重绿。新覆盖随 A/B 实现建立，未建不算通过。测试只保留用户主流程旅程与承重架构守卫；时间量化、唯一写口、版本并发、模板展开、spec/renderer 隔离属于承重纯函数覆盖。

### 0.1 现有 UI 可用与并行 UI 施工

- A 是内部基座，完成不等于用户已能从 Chat 使用；B 完成接入和验收后，新链必须能在现有 Chat 交互与页面布局下使用。不以 UI 改版、完整素材库页面或 Scrub 组件为前置。
- “UI 不变”指使用方式与视觉布局可保持，不承诺前端零代码变动。分镜 payload、版本引用、@ 解算、SSE 回放、Start、产物卡/播放/下载须做必要协议接线；先复用现有组件，预览可先使用现有播放器或服务端预览。
- UI 可并行开发视觉与交互；双方先固定最小 DTO/事件契约：Composition/版本引用、storyboard_payload、Output 与引用解算结果、编辑提交/冲突形状。UI 使用同一契约的 fixtures/mock，不依赖 pending_brief 中旧 Film JSON 或 Remotion 私有组件。
- B 同批完成 Chat 旅程、正文/工具/产物集成与真实制作过程；行为合同见 VIDEO_PROJECT §10.1。全面视觉改版可独立验收，默认布局下也要通过完整旅程，不能以“UI 后置”推迟过程协议与回放。
- 整合 block 替代 message/tool 分散呈现的可能性见 VIDEO_PROJECT §10.2；UIArc 仅为调研候选，不构成安装或选型决定。A 冻结最小关联/事件 fixtures，B 接真实运行；呈现组件可替换，D 清理实际被替代 UI。

### 0.2 分支、环境与合并策略

- 本轮在用户指定的 `feat/mg` 分支内完成破坏性更新，生产无实际用户，不要求旧 Film API、旧数据或过渡期持续可用；不因此豁免新链正确性与生产验收。
- 建分支前核对当前 HEAD、工作区和与 main 的差异；保留本轮必要的未提交成果和并行 UI 工作，不用 reset/checkout/stash 清场，也不把无关改动批量提交。基础分支取包含必要现有成果的状态，不盲目从 main 起步丢掉已完成工作。
- 分支内按 A/B/C/D 的依赖拆小批提交；合并前同步 main、处理冲突并对最终候选重验。首个限定能力发布须 A、B-I～III 与所声明功能的验收、D1/D2 达标才可合并；后续 B-IV～VI 与 C 可分批交付，未完成项继续登记；完整 B 不因限定能力发布而标为完成。C 若同批交付则须一并验收，否则留后续独立批次。
- main 合并与环境部署分开处理：生产就绪需 schema/reset 路径、API/worker/render/web 配套版本、旧任务处理及失败后重部署路径明确。无用户环境可停机/reset，不建设旧业务恢复兼容层；Git 分支不会隔离数据库和队列。

## 1. 阶段 A——CompositionVersion、时间/对象模型与 video-spec

### 1.1 目标

在不承接旧 Film 数据的前提下，建立能表达当前网页宣传片/MG 的新领域内核，并用一个 Remotion adapter 证明 `CompositionVersion → video-spec → MP4` 可走通。旧 Film 默认入口不切。

### 1.2 施工范围

**A1. Composition 身份、不可变版本与请求幂等**

- 新建 `app/editing/`：`schemas.py`、`timing.py`、`edits.py`、`store.py`、`templates.py`、`storyboard.py`、`video_spec.py`。
- 新增 `compositions`：独立 id、owner、origin_project_id、current_version；来源 Chat 不作为跨 Chat 引用的权限边界。
- 新增 `composition_versions`：`composition_id / id / version / base_version_id / schema_version / settings / sources / scenes / timeline / skill_provenance / content_digest / created_at`；版本在 Composition 内唯一。
- Composition 保存当前版本引用；避免循环外键造成写入顺序依赖。A schema 冻结前定义 Chat 删除、全局作品/快照保留和权限撤回策略。
- `apply_composition_edits` 在一个事务内完成 owner/引用校验、base_ref 校验、整批 ops、完整候选校验、子版本插入和 current 条件更新；同一作品跨 Chat 共用该并发锁点。
- 编辑 request_id 与载荷摘要持久化：同请求重试返回首次提交结果，同 key 不同载荷拒绝；失败不留半版。请求去重不能只依赖 content_digest。
- `version` 在 Composition 内单调递增；内容版本不可原地改写。呈现回执属于确认状态，不改写内容 digest。
- Output 增加可空 `composition_id / composition_version_id` 并校验一致性；新视频 `work_id = Composition.id`，保留发布/归档作品锚。Run/Output.project_id 属于本次执行 Chat，不要求等于 origin_project_id。
- Run 使用通用 `version_ref`；按目标架构 §2.4 区分 Start 执行输入与准备完成后的 execution_digest，不复制 FilmStoryboard 信封。

**A2. SourceSnapshot**

- 建立内容寻址、不可变的素材快照引用；需要独立持久化时新增 `source_snapshots`，记录 asset_id/canonical URL、digest、captured_at、manifest/transcript/views 或对应不可变存储键。
- 不只保存可变 Asset 行 id。网页 refresh、转写修改或素材替换必须产生新快照。
- CompositionVersion.sources 绑定真实快照；执行时再次验证 digest 和素材可用性。
- `page_readings` 继续服务 consult-first；SourceSnapshot 服务制作与版本，不合并两者职责。

**A3. Timeline / Track / Clip / Object**

- 实现当前网页片/MG 需要的 Web/Video/Image/Text/Audio/Speech Objects 与对应 Clips。
- Track 有 `kind/role/order`；视觉 order 决定叠放，音频进入混音。
- Scene 保存 range、intent、可空 visual_description 与 speech_clip_ids；旁白原文只保存在 SpeechObject.text，Storyboard 读取其投影；Clip 的 scene_id 可空。
- 定义视频/原声音频关联，split/trim/move 不造成非预期声画脱离；不做完整 NLE 联动编辑器。
- Source time、Output time、Clip-local time 三个时间域在 schema 命名和 validator 中分开。
- 按 VIDEO_PROJECT §3–4 冻结 source 的静态/动态/待合成差异、实体 ID 的保留/复制重映射与 Scene 原子操作；Layer 不建平行持久列表，元素不逐个建表。只实现当前样片/CRUD 需要的操作，不预建继承体系。
- Transition 先定义关系、输出覆盖窗、source handles 与余量不足即拒绝；只实现当前对照样片需要的封闭枚举。同轨非转场重叠拒绝。
- 按母文档 §6.5 冻结 split/trim 的关键帧裁剪、端点取样与重新定基；同对象/属性重叠动画拒绝。

**A4. Animation / TextPart**

- Animation 挂在所属 Clip 内，target 只能指向该 Clip 的 Object/TextPart。
- 属性首批：opacity、position、scale、rotation、audio.gain 与网页取景所需属性。
- Easing 首批：linear、cubic-bezier、hold；现有 spring 对照行为选择受支持 easing 或确定性烘焙，不静默改观感。
- 冻结 easing 的段归属、hold 跳变与首末关键帧外求值；共享 fixtures 覆盖 Clip 边界，非法目标/属性与重复时间键拒绝。
- TextPart 由完整 TextObject 派生 line/word/grapheme/span；支持 stagger，不默认落独立 Clip。
- 固定字体资源 digest、分词/排版版本与父子变换组合规则；中文、英文、Emoji 与换行 fixtures 校验 Preview/Render 一致性。
- 文本修改后的 part 映射失败必须拒绝；不得按数组下标静默错配。

**A5. 时间、fps 与 BeatGrid**

- `RationalTime/TimeRange` 采用整数 ticks + rate；fps 用有理数，30fps 无损承接当前行为。
- 所有时间范围采用 `[start, end)`；冻结 timebase、量化/舍入与 source→output 换算规则，统一 Python/TS golden fixtures；Timecode 仅显示。
- settings 携带帧尺寸、fps、timebase、sample_rate/声道。
- 音乐 SourceSnapshot 可含 bpm/beats；实现 source_range → 输出时间映射和统一 snap 量化。

**A6. video-spec 与第一 Renderer adapter**

- 新建 `packages/video-spec/`：TS schema、纯时间/插值求值、测试 fixtures；不得 import Remotion/React。
- `app/editing/video_spec.py` 把 CompositionVersion 编译为自足 `family="video"` spec：消费已展开的具体参数、量化时间、解析 SourceSnapshot URL、携带 provenance digest；编译不再查询/展开可变 Template/Preset 注册表。临时 URL 不进入内容 hash，过期重签不得换素材。
- `apps/render/src/video/` 实现第一 adapter；现有 `POST /render`、staging、上传、probe、render fencing 复用。
- PreviewAdapter 单独定义；Chat 组件不直接散落 Remotion Player。
- 建立 renderer capability 声明与不支持即失败的入口。
- 替代 Renderer 的能力/成本 spike 归 D2 生产门，不阻塞 B 开发；生产前仍必须有明确许可或替代结论，不把 adapter 隔离当作替换完成。

A 内按三次可验证交付推进，不先造齐全量框架：

1. **最小纵向闭环**：冻结作品身份、范围/量化、版本写口；用最小 Text/Image + 固定音频版本打通 worker → MP4 → probe，证明权限、版本、Output 血缘与实际渲染成立。
2. **代表性表达**：扩到 Web/Video、逐字动画、多段 scale/Bezier、字幕和音轨关联，手工重建一支官网片与一支 MG；先验证内容表达，不接 LLM。
3. **最小基座收口**：内容写口、关联操作、资源边界和必要回归成立后进入 B；不为清空全部未来能力清单阻塞产品闭环。B 在具体消费者接入前补其依赖，生产前仍须通过完整可靠性与 D 门。

**A 当前状态——最小内容基座已收口，完整能力未齐**：

- 已实现 Composition/不可变版本、owner/来源 Chat 校验、行锁/CAS、完整请求幂等与并发重放；Output 钉版、video-spec 与 Remotion adapter 已接既有渲染基础设施。已有批 1 worker→上传→probe 实测；内部 run-less 接缝不开放为产品制作入口。
- 当前支持 Text/Image/Web 静帧/Video/Audio、固定字体 digest、TextPart line/word/grapheme、整体/分段动画、scale/Bezier。A 的 base/edited 样片位于 `artifacts/video-project-a2/{website,mg}/`，B-III 真实混合片位于 `artifacts/video-project-b/mixed/`，均 Git 忽略；样片与真实 Chat 证据分开，不替代人工审美或听感验收。
- `move_scene` 原子平移所属 Clips，源窗/Clip-local 动画与全局音乐不动；`remove_scene` 删除所属内容并清理旁白引用。带内容 Scene 的范围重设不能静默只改标记：移动走 move_scene，缩放/改时长当前明确不支持。复制 Scene 与自由改时长仍未实现；固定媒体 split/trim、首个 crossfade 和节拍吸附已有下述限定消费者，不宣称完整 NLE CRUD。
- SourceSnapshot 登记/绑定与字体描述归 editing；资源读取、冻结上传及字体发布归 `tools/video/preparation.py`，editing 不依赖 providers。快照已接入 Chat 网页采集、视频/音频 Asset 与视频 Output 素材冻结；redraft 复用已绑定快照，只有显式刷新才更换绑定。
- 收口验证：受影响 editing/DB/animation/spec/样片契约测试 **44 项通过**，check_gates 通过；只新增 Scene 移动/删除两项承重用例，未扩写验收脚本。未复跑全量 API/web/render，未重渲染或人工播放验收样片；已有样片与批 1 渲染证据不升级为本次新证据。
- 旧 Film 入口/Clip 链不切换。所有改动仍在 feat/mg 未提交；开发基座收口不等于生产就绪。

### 1.3 A 出口与保留的能力欠账

A 的最小出口：版本写口与权限/幂等成立、代表性静态网页/MG 内容可编译渲染、Scene 移动/删除语义明确、内容/存储/renderer 边界检查通过。上述出口已达到，可以进入 B；停止增加同类样片与通用检查脚本。

以下能力不因 A 收口取消，也不标成已完成：

| 剩余项 | 实施 / 验收位置 |
|---|---|
| Speech 与旁白准备 | B-VI 按真实消费者接通；既有版本/执行 manifest 与 digest 接缝已落地，新增音频沿用并补齐实际输入/结果身份；付费合成仍受预算授权约束 |
| launch-film 模板所需的 Scene/Clip/Object CRUD、split/trim、转场与 BeatGrid | B 按内置模板和真实修改需要补齐；模板不得静默省略不支持能力。自由 NLE/完整转场库后置 |
| 同源多切片完整对照 | B-III 已验单源双层、原声静音/音乐与一次等长换窗；更多同源多切片组合仍按真实需求验证 |
| 跨 Chat 引用/删除保留、素材 refresh/生产接入、重试/恢复 | B 的真实用户链路；已有 DB 验证不替代端到端权限与恢复验证 |
| PreviewAdapter | B 先用隔离的服务端 MP4 预览，复用现有播放器；交互式预览后续扩展 |
| 字体/排版与预览导出一致性、动态画面、独立音轨听感 | B 最小闭环接通后集中人工验收；只对实际失败补定向回归 |
| 替代 renderer spike / 商业许可 / 能力矩阵 | D2，生产前必须收口 |

## 2. 阶段 B——launch-film Skill 化、Chat 分镜与 CRUD 制作闭环

### 2.0 B 当前状态（2026-10-29）

上下半批、B-III 混合合成、B-IV 两个纵向出口与 B-V 首个模型图片消费者均已落码于 `feat/mg`，具体提交状态以 git 为准；**真实 MG、官网片、混合实拍、原生图形、受控程序画面及 MiniMax image-01 单图混合短片的制作/交付与修订闭环均已按各自出口通过，B 主链收口，仍未封板**（欠账见下）。不要按旧提示词重做上半批、生产链或已通过的 B-IV 出口；B-V 只声明当前单供应商单图用例，不扩张为全模型媒体能力。

- **已有实现**：`editing/service.py`、`chat/video_turn_seats.py` 共用 plan/propose，canonical 版本引用、真实消息 id、完整呈现 ACK、首稿批准守卫、明确后续修订并制作的延迟启动与现有确认/费用设置接线。补齐版本上下文、幕数/时长/背景约束、背景修订、全局 @asset/@output owner 读面。新增 `tools/video/params.py`、`tools/video/production/`，produce_video 经既有图写口/create_run 固定版本、估价/hold、manifest、渲染/上传/probe、成功 capture、交付；成功才归档同作品旧完成产物。
- **当前呈现改动（未验收）**：用户可见分镜改为 LLM 基于完整保存版撰写的 Markdown 创作概要，标题/列表/表格自由组织，重点讲整体方向与大致画面设计；原 CompositionVersion、`storyboard_payload`、消息 block 和 digest 结构不变，技术 DTO 不再平铺。首稿/修订提示词、工具描述与 observation 已同步；ACK 随正文完成打字释放且必要真实 Generator 预览就绪后发送，首稿批准、制作、Run 和费用链不变。尚未运行 TypeScript、API、真实 Chat、prompt_gate 或刷新/延迟启动验收，既有卡片证据不覆盖本次呈现改动。
- **B-III 已有实现**：VideoObject 与真实视频 SourceSnapshot 接入 validator、video-spec、Remotion `OffthreadVideo` 和 render probe；画面与原声共享同一 Clip 源窗，支持 layout/fit/transform/opacity/gain/muted。`instantiate_mixed` 生成同源全屏静音动态背景、中央原比例录像、独立标题/定时字幕与既有音乐床；`update_video` 通过唯一写口局部改布局、源窗与原声，目标源窗修改保持当前输出时长。视频 Asset 与 Output 均可冻结为新素材，继续修改 Output 原作品仍走版本修订。
- **B-IV 已有实现**：ShapeObject 支持 rect/ellipse/path 几何、绘制与外部表现，MG Director 可按需创作 rect/ellipse，多个同幕图元分轨避免重叠；`update_shape`/`update_animation` 精确局部修订。GeneratorObject 固定 `runtime/code/parameters/output` 与 program_digest；首个 runtime `drawing-v1` 由权限受限 Node 进程执行 Agent 的 `render(ctx)`，只接受有界 JSON 绘图命令，经 Pillow/PyAV 生成固定 MP4/PNG。设计、修订和生产共享 exact-digest 媒体准备；预览绑定版本来源，执行 manifest 固定媒体血缘，最终 video-spec 只含普通 muted video，不包含程序。
- **B-V 已有实现**：新增单一 `image-v1` 消费者，保存可审阅的 MiniMax `image-01` 16:9 单图请求及独立原生标题；设计/修订只经既有写口保存来源，不生成、不计图片费。只有带授权 `execution_id` 的 produce Run 才调用供应商；共享 `generate_image` 每次调用只发一次非幂等 POST，image-v1 在调用前持久化 `submitted` 标记，传输/响应解析失败或恢复仅见该标记时按“结果未确认”失败闭，不自动重放、不虚记确定用量。真实图片返回后按实际数量计量并固定为不可变媒体；固定执行 manifest 记录完整请求、Run 身份与实际媒体 digest，Composition/Object 复用指针指向该作品最新固定结果。普通恢复与原生内容修订复用媒体；只有 `produce_video.params.regenerate_media=true` 的新 Run 明确重生成，使用 Run 独立执行命名空间，同 Run 重试仍复用。报价只计缺失图片；最终 video-spec 只含无源窗的普通静态 image，不泄漏 prompt/provider/model，也不把生成像素冒充原生可编辑元素。
- **B-VI 首个旁白消费者**：MG `design_video` 接收精确 `narration` 与显式开关，实例化 SpeechClip、派生字幕和既有音乐床；SpeechObject 保存原文/voice/language/gain，制作不回写版本。MiniMax `speech-2.6-hd` 非流式 T2A 返回真实音频与句级时间，授权 Run 以 1.0–1.35×、至多两次、`fit_margin=1.08` 和钉入 step 的 `max_tts_characters` 执行；解码实测超长即冲突，不删词、改写、截断或移动切点。共享 speed-1.0 原件按 `(user_id, content_hash)` 复用，适配件与 manifest 归 Run；未知提交失败闭，已固定音频可只恢复字幕下载。`update_speech` 只刷新 derived 字幕，手改字幕转 independent，`sync_captions` 才显式重联。编译只产普通 audio 与按真实 cue 定时的 TextClip，renderer 不接触 Speech 或模型。报价按剩余付费合成与实际 MiniMax 计费字符，produce step capture TTS，render mirror 只计成片秒，避免双计。
- **环境**：默认闸仍 false，本机忽略的 `.env` 已开 `VIDEO_PROJECT_ENABLED=true`；DB head `a6e9c2d4f801`。API8000、web3000、render3001；worker/render 不热加载，改执行代码后无活跃任务再重启。当前日志 `/tmp/rep-api.log`、`/tmp/rep-worker.log`、`/tmp/rep-render.log`。
- **真实成功（同 Chat）**：Chat `2cce4c18`，Composition `05c66c6f`；Run `e32ed9f2` COMPLETED，Output `94ccf1d8`（v3）。
- **真实成功（跨 Chat，2026-10-27 收尾通过）**：Chat `1b89291a` @output 引用成片，仅改第三幕为 Keep editing 并直接制作；保存 v4 `0d6df014`，浏览器回放卡片完整呈现 → ACK → 延迟启动 Run `f6b64fb6`（version_ref 钉 v4）→ 渲染/上传/probe → Output `36383c3f` COMPLETED，hold→release→capture 各一次（-12 积分），旧片在新片成功后才归档；浏览器真实播放，5.2s 帧确认第三幕为 Keep editing、其余不变（"in focus" 是 v2 的用户修订，非串改）。成片存 `artifacts/video-project-b/`（已 git 忽略）。
- **真实成功（B-III，2026-10-28）**：项目 `7da1c453` / Composition `1978090d` 经真实 Chat 从 15 秒录像设计 5 秒混合片；v1 Run `0f50ec33` → Output `36f15832`，随后只改第二句字幕、中央布局缩至 80%、关闭中央原声保留音乐、中央源窗改为 1–6 秒，依次保存同一 Composition 的 v2–v5。系统 change_set 证明每次仅目标 Clip/源窗变化；v5 完整呈现与 ACK 后 Run `57310339` 钉 v5 digest → Output `417ac081` COMPLETED，旧 v1 仅在新片成功后归档，两次 Run 均 hold→release→capture 各一次。浏览器真实播放并刷新回放，Run 数保持 2；1920×1080/150 帧成片与 2.5 秒帧确认动态背景、缩小的中央实拍、标题及修订字幕同时存在。两层 VideoObject 均 muted 时输出仍有 48kHz 双声道非静音音频，证明音乐床保留；未把这等同于亲耳听感验收。媒体与浏览器证据在 `artifacts/video-project-b/mixed/`。
- **真实成功（B-V，2026-10-28）**：项目 `e6f80236` / Chat `97fa8002` / Composition `ce1795ff` 经真实 Chat 首稿审阅后生成并交付 4 秒 16:9 混合片。v1 `cf1c9c71` 的 Run `a7d1b840` 真实生成首图；仅改独立原生标题得到 v2 `bd4f9951`，Run `c6569a65` 复用首图且无图片费用；同一 v2 明确重生成由新 Run `98639a0f` 产生不同图片与第二次 `images=1`；随后普通 Run `bce7f2c6` 复用最新图且无图片费用。四个 Output 均 COMPLETED，成片均为 1920×1080/120 帧；v1→v2 系统 change_set 仅含标题 Clip 的 object 变化。持久化消息/API 回放保留两张分镜引用，ACK 重放 `accepted:false` 且 Run 数保持 4。两张真实 JPEG 均为 1280×720，供应商实际费用合计 USD0.007；帧确认无字生成背景与独立原生标题同时存在。原始信封、Run/Output/账本、manifest 与帧证据在 `artifacts/video-project-b/b-v/`（已 git 忽略）。
- **真实成功（B-VI 首个两幕旁白闭环，2026-10-28）**：项目 `9d028c39` / Composition `d5e2e575` 经真实 Chat 设计 8 秒两幕 MG，v1 `540f6c97` 完整呈现 ACK 后授权制作。首 Run `136ecd62` 已固定第一幕真实音频，因 MiniMax 实际句级时间是浮点毫秒、初版解析只收整数而失败；解析修复后 Run `b429b0e4` 只恢复该音频字幕下载并合成第二幕，Output `ad02d47e` COMPLETED，没有重复提交第一幕 TTS。随后仅手改第一幕字幕得到 v2、零 Run；只改第二幕旁白得到 v3 `aeecf06a`，Run `705d21a2` → Output `93a28207`，第一幕音频 digest 不变、`cache_hit=true`、本 Run TTS=0，人工字幕「先看挑战。」保留，派生字幕按真实时间显示「答案在这里。」。v4 长旁白 Run `473dbc9e` 实测 9.892s 对固定 4.000s、所需 2.522× 超过 1.35×，以专门冲突失败，无新 Output，文字与切点不变，hold 35 全 release，前一交付仍可播放。两次成功交付均在真实浏览器播放；硬刷新保留 v4 分镜、两版成片和 4 个 Run，不重启制作。帧证据确认第 4 秒切点与两版字幕，音轨解码确认非静音旁白段与持续音乐床；未亲耳试听，不把这算作听感验收。首个成功 Run 曾暴露 produce 与 render mirror 双计 TTS，镜像已修为只计 film_seconds，后续修订 Run 实扣为 produce `tts_chars=11` + render `film_seconds=8`，历史开发账本不改写。原始响应、版本、Run/Output/manifest/账本、浏览器与帧证据在 `artifacts/video-project-b/b-vi-narration/`（Git 忽略）。
- **本批修复**：① 回放洞——pending/已答 task_book 行的 video_storyboard blocks 不进历史流，刷新后卡片不再呈现、ACK 永不再发、授权延迟启动永久卡死；`historyReplay.ts` 两条分支现携带 blocks 回放（已答 echo 行与 pending echo 行），旧无 blocks 的 plan dock 行为不变。② `_video_project.j2` REVISION 律补状态真言：改版卡片呈现完成前制作未开始，禁称"渲染已在后台进行"。③ 三个守卫测试随门控世界更新（工具桶 XOR 断言、plan stub 补 user_id、trigger 工具预算 18→21 注明出处）。
- **检查（当前工作树）**：B-UI 收尾后全量 API 1365 项通过，web 23 文件 / 260 项及 web/render TypeScript 通过，check_gates、API compileall 与 git diff --check 通过。付费 prompt_gate 已取得 A/B/C/E/F/H/H4 各12/12、D/G各11/12，九探针通过；I 未得结论，完整门未通过；完整剧本矩阵未跑。真实旅程证据归 artifacts/video-project-b/b-close/，不以静帧或参数检查替代独立听感。
- **真实成功（官网片，同 Chat 全闭环，2026-10-27 独立复验）**：项目 `bd2b2f2e` / Chat `9ee217bc` / Composition `79035790`。首稿 v1 `e09d8509` 完整呈现 → ACK `run_id=None`（呈现不动工）→ 用户批准 → Run 钉 v1 digest；首 Run `98a70678` FAILED（render POST 被系统代理截断，hold 176 全额 release），重试 `b943bf22` COMPLETED（capture 一次）。局部修订「hero 副标题补空格」→ v2 `dc75f1ba`（settings/sources 逐字节相同，timeline 仅 `clp_hero_text1` 文本变，零重新采集、零重新设计费），普通修订零 Run；「改完直接做」→ Run `3f3262f5` 钉 v2 → Output `31e444aa`。同版再产 → Run `59762ae8` → Output `558c6547`（终片，88s/1920×1080）。每次 Run hold→release→capture 恰各一次；ACK 重放 `accepted: false` 不产生新 Run；渲染中 Output `files={}` 不冒充完成。帧级核验：屏幕文字取页面原文且字体正常、hero 文案空格已复、章节字幕正确、音乐床全程约 -20dB 且 88s 处淡出至静音、无旁白（内容模型无语音对象，结构性保证）。
- **本批修复（官网片链，均有真实证据）**：① `SKILL.md` 陈旧槽位词汇（法条座位冲突，首设计回合 29 个 schema 错误的根因）全文重写为 v1.3.0；② `CiteLine._fold` 从未注册为 validator → 接上 `model_validator` 并扩拼写（非法引用仍 raise，纯函数实测）；③ 字幕 `{text,citation}`/片段列表 fold 成纯文本（不丢词不乱序，不可解析结构 raise 不静默置空，纯函数实测）；④ 音乐床：`video-template.json` 增 `trk_music` + `MusicBed` 平铺 + gain 关键帧淡入淡出 + `resolve_bed_track` 三态（off 终态无人 reopen，实测 `off→None` 且不建空音轨）+ `snapshot_music_track` 内容寻址冻结；⑤ `storage.py` S3 client 显式 `proxies={}`（urllib3 隐式走 macOS 系统代理吞大 PUT 响应，boto3 全项目仅此一座）；⑥ `rendering.py` render POST `trust_env=False`（长渲染请求被代理中途切断）；⑦ 字体缺陷：`fonts.py`/`schema.ts`/`Video.tsx` 给 emoji 字体资源加 `unicode_range`（Noto Emoji 含拉丁字形且 family 排序在前，整行拉丁渲染成 emoji 面、词距崩塌；修复后帧实测正常）；⑧ `capture.py` 研究清单把 `<br>` 视为词边界（`actions.<br>Not` 空格被吞，真实页面 HTML 实测修复）；⑨ `grounding.py`：focus 取元素**可见部分**（视口裁剪截图的元素坐标可越界 >1）+ camera 平移钳制在 cover 余量内（聚焦越界元素会把画面推出画布露黑；真实 view-1 库存上纯函数实测钳到界内）。
- **本次代码审查与必要修复（2026-10-28）**：相机原钳制把 cover 图片的额外像素误作实际 Img 盒子的可移动余量，且忽略起点/末段漂移；改为按 renderer 的画布大小盒子与各关键点实际 scale 限位，并由模板透传起始 scale。CiteLine canonical `line` 改 strict integer，拒绝此前会被折叠成1的 bool/整值float；字幕空/空白片段列表不再静默变成 null，而交字段校验拒绝。增加12个现有套件参数用例；API1322、web257、web/render tsc、video-spec9、check_gates 通过。用现有本地入口实际渲染4秒/120帧边缘聚焦白底短片，全部边缘RGB=255；这是针对裁切盒边界的真实 renderer 验证，不冒充原官网片重渲染或音乐试听。样片位于 `artifacts/video-project-b/camera-review/camera-coverage.mp4`，未调用付费模型。
- **未验收欠账**：旧官网样片仍未重渲染；新 AgentVeil 首章真实取景已由本次 v2/v3 实帧核验；官网片与 B-III 音乐均未亲耳试听（结构与电平核验，听感不冒充验收）；音乐多瓦片循环接缝未真实渲染（现有素材单瓦片即够长）；`run_failed` 触发回合沉默一次（FAILURE FACTS 装配正确但模型读满预算未发声，同机制其余回合正常，登记为 LLM 漫游方差未修）；完整付费 prompt_gate；B-III 局部换源窗只接受与当前输出窗等长的片段，不做自由改时长，1× 与 B-VI 有界旁白适配不冒充通用变速；自由改时长与通用转场仍未实现，首个固定媒体 crossfade 已补齐；B-III 首稿曾出现正文宣称背景推移但保存版无该动画、以及“逐项打开”等过度表述，canonical 内容未受影响，正文质量仍需按真实 payload 归因处理；B-V 一次“修订并制作”回合在修订版已保存后反复尝试未呈现版本的生产，并把 `regenerate_media` 错放到顶层，最终耗尽工具预算；随后经真实 Chat 重新呈现 v2、ACK 与制作完成交付，但该交互稳定性仍留集中验收，不能以最终成功抹除。B-VI 另一次同回合「长旁白修订并制作」先尝试未呈现版本生产，保存 v4 后仍未重新呈现而耗尽 12 次工具预算；随后通过独立呈现/ACK/制作回合取得真实冲突，该多轮稳定性同样未关闭。B-VI 未做亲耳试听；真实加速第二 pass 已由本次收尾样片补齐；完整付费 prompt_gate、完整剧本矩阵和音乐循环接缝继续开放。B-V 刷新证据为持久化消息/API 回放，不是新的浏览器硬刷新播放会话；真实帧与 PyAV 结构核验不冒充独立完整视听验收；完整 redraft 的 `numbers_plate` 阻断已解除且 v5 已保存/呈现，但保存后主 Chat 仍发生无关修订/重设计漫游并被中止，Director/多轮稳定性未关闭；§2.4 其余未勾选条目；多作品交付与 B-UI 移动端/双主题/reduced-motion 本次已补齐。
- **定向可靠性结果**：`_execute_program` 改为读取期累计 stdout，超限立即终止；正常完成、超时、异常与取消统一 kill/reap 并回收读取任务。定向进程探针实测普通程序完成 2 帧，超限程序 0.032 秒内停止并回收，超时/取消/运行错误均回收子进程且保留对应诊断；未重做已接受的 B-IV 样片。B-V 以隔离存储的代码级故障注入验证：普通重试/原生修订复用首图，明确重生成获得新执行身份，同 Run 恢复复用本 Run 结果，后续普通生产读取最新图，其他 Composition 不串用；manifest 已固定、复用指针写入失败后的恢复未再次调用供应商或重复计量。这些是代码级故障证据，不冒充额外真实供应商生成。
- **B-V 供应商重试修复（已定向验收）**：官方同步 image-01 参考仅提供响应 trace `id`，未文档化幂等键、客户端请求 ID 或历史结果查询，不能以 seed 或本地台账冒充供应商防重。共享 `generate_image` 已移除通用三次重试，并保持 quote-card/cover 调用签名与正常成功返回不变；`ProduceVideo.retries=0`，传输错误不包装成 `TransientNodeError`。image-v1 在 POST 前写 submitted，故 worker 孤儿节点 requeue 或同执行恢复也只能读到“结果未确认”，不会再次调用供应商；新明确重生成走新 Run 键。无网络替身实测首次 ReadTimeout 后 `provider_posts=1`、`usage=[]`，同执行再次恢复仍 `provider_posts=1` 并返回专门的中英文恢复信息；正常生成固定媒体并记录 `images=1`，缓存不再调用，明确重生成与后续最新复用保持原语义。保证范围是同一执行键的顺序恢复不盲重放；供应商实际是否执行/收费仍可能未知，须对账，不承诺恰好一次。submitted 也可能是请求尚未到达供应商的保守标记，此时仍需用户明确新生产，而非系统自动试探。
- **B-VI 字幕量化修复（当前工作树）**：`editing/video_spec.py:_compile_derived_caption` 不再先把浮点毫秒截成整数；毫秒以十进制有理数保留到最终起点 floor / 终点 ceil 帧量化，继续沿用既有固定窗、相邻 cue 顺序与不重叠规则。无网络回归覆盖 30fps 的 33.9–1000.1ms 从修复前 `[0,30)` 更正为 `[1,31)`，并覆盖相邻 cue 与整帧终点；旁白、video-spec、修订与 probe 四个定向套件共 63 项及 `check_gates` 通过，未重新调用 TTS 或重做既有样片。既有真实旁白交付证据保留，字幕同步与完整视听验收不因此封板。
- **真实成功（增强网页采集首个静态镜头闭环，2026-10-29）**：项目 `432c0cd3` / Composition `2eb8f349` 经正常 Chat 使用真实 `https://agentveil.dev/`。同一 Asset `51a61dad` 保存渲染正文 80 行（`body_truncated=true`，长页补读未实现）、2× 整页图、6 张 2× 视口图与 12 张目标元素图；SourceSnapshot `993bd3fc` 冻结上述文本/图片及 CSS→像素映射，Director 实收 6 张视口图 + 4 张元素图（`media_count=10`），不是只存字段。首稿 v1 完整呈现 ACK 零 Run；`focus_web` 以 `clp_chapter_1_walk_web + s1e8` 生成 v2 `8ffcd898`，唯一内容 Clip 变更为首章相机，服务端按元素中心/可见部分重算关键帧。Run `1f606707` 钉 v2 → Output `28b03b27` COMPLETED。随后只把第一章标题改为 “Review the next move” 得 v3 `d729517a`，仅 `clp_chapter_1_divider_text1` 变化，首章相机及所有版本 SourceSnapshot 绑定不变；Run `f798e508` 钉 v3 → Output `260e3883` COMPLETED。两次 Run 均 completed、各净计 176 渲染积分，无重新采集、图片或 TTS 调用。20 秒实帧确认真实标题 “Don’t just stop the agent. Give it the next move.” 清晰占据首章主体，v3 15.5 秒实帧确认修订标题；两版 20 秒帧逐通道平均像素差仅 0.42–0.63/255。真实浏览器播放 v3，硬刷新保留两版视频与 3 个分镜版本，Run 数保持 2。原始响应、Asset/快照/版本/Run/Output/账本、浏览器和帧证据在 `artifacts/video-project-b/web-capture/`（Git 忽略）。这只是首个静态镜头切片，不是完整采集能力或完整 B 封板。
- **真实成功（首个 exact-Output 内容审片闭环，2026-10-29）**：同一 AgentVeil 项目 / Composition 的已交付 v3 Output `260e3883` 经正常 Chat 审片，reviewer 直接解码其真实 MP4、保存 15 张内容寻址静帧及 `quality.content_review`；后续正常 Chat 默认复用该报告，未重复解码/调用 reviewer。报告在 48.067s 以 `clp_chapter_3_walk_web` / `obj_chapter_3_walk_web` 证明第三章主标题左侧被裁。自然语言局部修订保存 v4 `01207347`：settings/sources/全部 Clip id 不变，内容 Clip 仅该网页 Clip 的 animations 改变，另同步刷新该 Scene 的 `visual_description`；呈现 ACK 后 Run `fe665967` 钉 v4 → 新 Output `d930fbc1` COMPLETED，净计 176 渲染积分，无图片/TTS/重新采集。对新 Output 的正常 Chat 复核只抽 48.100s 这一真实帧（frame 1443），确认完整标题 “Keep sensitive data local. Share only bounded proof.” 及支持文案已在画面内可读，该点未见新取景问题，findings 为空；旧 Output 虽按现行规则归档，文件与确切版本/审片报告仍可读取。原始回合、版本/Run/Output/账本、消息/API 回放及复核帧在 `artifacts/video-project-b/content-review/`（Git 忽略）。这只修复一个静帧问题；原 caption band 遮挡不在本次修订范围，运动、转场、音乐、音画同步、其他时间点与完整内容质检均未通过。
- **短修与完整 redraft 复验**：新 SourceSnapshot manifest 根级冻结 `body_truncated`，Director 独立 `CAPTURE STATUS` 读取三态，旧快照 UNKNOWN；普通 `get_web_page` 未改。完整 redraft 已保存并呈现同一 Composition 的 v5 `514d6426`（base=v4，88.1s/15 scenes），SourceSnapshot 绑定不变，ACK 零 Run，未再出现 `numbers_plate` schema 拒绝。Director 对实际出现的固定弧分组/系统 proof 回声只做限定读容忍，未知字段仍拒绝；保存后仍发生无关修订/重设计漫游，故 Director/多轮稳定性不关闭。
- **审片报告复用已短修**：`tools/video/review.py:_reusable_report` 只在确切 Output id、检查要求与显式持久化的 `at_seconds` 采样范围全部一致且 `refresh=false` 时复用；新报告保存请求采样范围，缺该元数据的旧报告不猜测复盖新请求，单点复核与整片场景抽样不能互相替代，`refresh=true` 仍强制重新检查。相关纯测试覆盖相同请求复用、要求变化、旧元数据缺失与两种采样范围互斥。
- **B-UI 视觉与交互代表旅程已通过，声音待复验**：Docker/数据库已恢复。新真实 Chat `92486f3c` 完成 Morning/Night 两作品各 v1/v2 四交付，后有 Morning v3 及同 v3 再交付；浏览器硬刷新仍为六项，版本号依次 1/1/2/2/3/3。查看器打开时新交付将 3/5 更新为 3/6，当前仍为原 v2；关闭回到原消息位置与触发焦点。440×956 移动视口、浅/深主题、reduced-motion、键盘左右/Escape、竖屏 contain、真实文本、三页 carousel（Output 序号与页码独立）、真实 PNG 阅读/切换已实测。归档 AgentVeil v2/v3 的打开、播放、切换、25,505,600 字节 MP4 下载与精确引用，以及同版三个独立 Output 的既有证据保留。实测补修图片固有尺寸导致的移动端溢出、键盘导航及 reduced-motion；旧金句图虽已按生产步骤持久化但未写入旧 refs，读面按既有步骤归属补齐，无历史数据回写。内部/未完成行不进列表，确实缺失的历史引用仍为不可用。证据归 `artifacts/video-project-b/b-ui/` 与 `b-close/`；视觉与交互通过；用户已确认重新展示的视频有声音；完整视听与完整 B 仍另行验收。
- **预算与能力边界**：累计授权人民币60元，历史费用不重置。历史可核 USD4.212835；本次 Chat USD0.982962、生产 LLM USD0.0224367、三次真实加速合成共273字符 USD0.0273、prompt_gate 484条已返回供应商 usage 按现有价目 USD4.8637083，本批已知合计 USD5.896407，累计 USD10.109242（按既有7.2约人民币72.79），已超授权。完整 gate 的工具 loop 调用量超过估计且未及时限制累计费用，不能写成预算内；后续付费已停止，无运行中 prompt_gate。历史中止回合最后一个在途请求及 gate 未返回用量仍待供应商对账，不视为零。明细与 gate 原日志归 artifacts/video-project-b/b-close/。当前只声明既有 Text/Image/Web静帧/Video/Audio/Shape/Speech/drawing-v1/image-v1 消费者；其他模型、生成视频、通用转场、自由改时长、完整NLE/交互式Preview 未实现；本批限定 split/trim/crossfade/BeatGrid 证据见下文，C/D 未实施。

- **B 收尾的实际修复（2026-10-29）**：同 Chat 两作品实测复现修订后生产反复拒绝、耗尽 12 次工具。根因是 pending 呈现可能指向另一作品，且修订读面未携带实际 previous_version_ref；现按实际 base 恢复对应历史呈现，保留首版审阅/ACK 和当前消息制作意图。修复后正常 @Morning v2 → v3「Hello morning」→ ACK → Run `3472df22` 成功交付。只证明该具体故障修复，不把其他 Director 漫游一并关闭。
- **B-VI 真实加速与校准**：缓存原音的报价曾使用上次实际字符数，下一次提交却要求保守字符上界，现统一按保守上界报价。原 2% 余量下两条真实适配分别为 8.278s/8.100s 与 9.741s/9.600s，诚实失败、均无 Output。依真实供应商时长波动将新 Run 的 fit_margin 校准为 1.08，速度上限仍 1.35、最多两次。项目 `0e53ac24` 新 Run `dff58884` → Output `d7e02165` COMPLETED：缓存原音 9.891719s，1.318896× 第二次合成实测 7.569719s，固定 8.1s/243 帧，原文/版本不变；本 Run 计 91 字符，未再计原音。失败尝试的真实供应商消费保留，不因开发积分退回而算作零费用。样片与 manifest 归 `artifacts/video-project-b/b-close/`。
- **声音入口反馈已解除，完整听感仍待验收**：用户实测 delivered-v1.mp4、delivered-v2.mp4、mixed-v5.mp4 均无声。文件检查均有 AAC 48kHz 双声道，解码 RMS 分别约 0.0658/0.0644/0.1097，未见左右相消；这些结构证据不推翻用户播放无声，也不等于听感通过。已原样提取 WAV 并重新展示原始视频，用户确认视频有声音；完整音乐接缝和音画同步不因此自动通过。

- **当前授权批次**：一次贯通 split/trim、首个全画幅固定媒体 crossfade、冻结音乐 BeatGrid 的 cut snap；新增全部供应商费用上限人民币10元，历史已知约人民币72.79元不重置。先无付费编码与本地渲染，再集中真实 Chat/制作验收；不跑完整付费 prompt_gate，不因预算或首个消费者删除原需求。三个首个限定出口已通过下述真实 Chat 与制作旅程，未提交、未部署；不等同完整 B 封板。

- **B-VI 时间编辑三个限定出口已通过**：`editing/temporal.py` 承载固定媒体/原生画面的帧值保真 slice 与源窗映射，显式 linked_group_id 随拆分/裁短同步，VideoObject 内原声自然沿同一源窗；split 左侧保留身份、右侧生成新 clip/object/animation 身份，trim 不 ripple。`editing/transitions.py` 为首个全画幅不透明固定媒体 crossfade 解算真实 handles；版本保留原切点，video-spec 固定覆盖窗，renderer 同时对 VideoObject 内原声交叉淡化。透明层、外部视觉 transform/opacity 动画、独立关联 AudioClip 的转场淡化、待生产 Speech/Generator 的内部切分未声明支持。音乐快照冻结实际 beat_grid，snap_cut 经音乐源窗映射到输出帧，优先真实 beats，BPM 仅作已知名义拍长的后备；无节拍数据或无容差内节拍时不伪造吸附。
- **同一作品的真实编辑与再交付**：项目 `2f875e94` / Composition `37733138`，正常 Chat 从15秒真实访谈素材设计并审阅后，去掉重复背景、拆分、裁短右段、将右段换为固定新源窗、吸附音乐节拍、添加0.4s叠化；v6 `73254d28` → Run `cdd41289` → Output `97dcdebd` COMPLETED。切点固定3.533333s/frame106，总长8s/240帧，右段在7.5s结束，末半秒保留独立标题与音乐。随后正常 Chat 仅把同一 transition 的时长改为0.6s，v7 `4564a375` → Run `610ca8b9` → Output `b5deb79f` COMPLETED。服务端比对证明 v6/v7 settings、sources、全部 tracks/clips 完全一致，只有 transition.duration 及相应 Scene 视觉摘要变化；两次净计各16开发积分，无新图片/TTS/采集。浏览器分镜可读两段输出/源窗及0.4s/0.6s叠化，两个实际 MP4 播放、旧v6归档仍可读，硬刷新保留两交付、Run数始终2。
- **本批验证与费用**：API1366、web260、video-spec9项测试通过；web/render TypeScript、check_gates、ruff F、compileall、git diff --check通过。红→紫→蓝本地实际渲染证明叠化像素，原生 Bezier 裁剪与关联音轨有对应主流程定向覆盖；真实两版均240帧并含非静音音轨，源窗两段的解码相对映射一致，不以参数/相关性替代完整独立听感。初次混合设计失败时的9次供应商用量USD0.0950493仍计入；已提交 ConversationUsage USD0.275518（含真实交付触发），另有新/旧 Chat 能力问答 USD0.024655，未新增 Run；当前对话收口后的已记录总支出USD0.8168918，按既有7.2约人民币5.88，含失败及已返回未落账用量，未超新增10元；被reload中断的Director最终用量未知，不记零。本批没有重跑完整付费 prompt_gate 或剧本矩阵；旧I探针未结论等欠账保留。证据归 `artifacts/video-project-b/b-vi-temporal/`（Git忽略）。
- **能力入口**：三个出口均归原 A3/A5 定义与 B-VI 实施范围；plan/propose 的 `revise_video` schema 暴露 split_clip、trim_clip、set_transition、remove_transition、snap_cut，说明及用户能力菜单同步更新，不另建三个执行工具。正常新 Chat 与已有交付 Chat 均回答拆分、裁短、叠化、音乐卡点及主要适用前提，Run 数分别保持0/2；能力问答不冒充完整语言稳定性通过。原始答复归同目录 `capability-proof.json`。代码集中在主工作树 `feat/mg`，未新建 worktree、未提交、未部署。
- **本批顺路修复**：narration_enabled=false 在媒体设计中不再被当作开启旁白；mixed Director 只返回其实际支持的平面字段；remove_clip 经唯一候选校验删除确切媒体及其转场链接，不再受过期的“只能删文字”限制。storage.read 使用已配置的下载客户端，避免内存读取绕过现有下载代理。未建新调度链、框架或数据库表。
- **对话与呈现收口复验**：项目 `2f875e94` 经正常 Chat 完成「仅保存标题 v8 → 插入能力问答且零版本/零 Run → 后续按刚存 v8 制作」，Run `fc0668b3` 与 Output `b6a6e87c` COMPLETED；能力答复的 BeatGrid 容差数值为默认0.2s、大于0且至多1s。用户报告项目 `822a422d` 首次续跑因素材 schema 与 captured-page 上下文矛盾而12次工具耗尽；补齐既有页面 URL/id/view 事实并解除该矛盾后，正常纠错消息复用三张既有网页及冻结音乐保存 Composition `d047448e` v1 `30ed2ad0`，零重新采集、零 Run。该回合首轮工具参数拒绝后的零 delta 属现行 frame-silent 法，最终信封由客户端打字释放；未为放行修改流断言。卡片 ACK 原先把消息块旧展示 hash 与当前 DTO 强绑，现严格校验同版 content_digest + 当前实际 DTO digest，并同步更新消息块和版本外 receipt；真实浏览器初次与硬刷新后的 ACK 均200，两处 digest/complete 一致，设计活动行在刷新前后均回放，零新 Output、零控制台错误、零翻译 key 泄漏。video design/revise/review 的持久活动 replay key 已对齐；定向 API283、web69、tsc 与 check_gates 通过。普通仅保存修订 v10 虽保存/ACK/零 Run 成功，回复仍逐项复述未改层、字号、源窗与音频参数，且明显承接前一轮技术汇报形态；表达验收未通过，未继续用付费回合试措辞，完整 B 不因此封板。证据归 `artifacts/video-project-b/b-vi-temporal/`。


- **Use prompt 与 Chat 收口（2026-10-30，进行中）**：按当前代码及真实首页盘点14项：6个可点击 demo、6个禁用族配方、2个隐藏配方（image-video同时reserved）。未启用隐藏入口。正常前端已交付英文逐字短片项目 `1dcdfbac` / Run `a13c943d` / Output `9a35636a`、文案节奏短片 `dd0c2062` / Run `7b86600b` / Output `b6d96fcb`、基础网站片 `28c04380` / Run `6f716937` / Output `555f14c1`；首片局部修订v4只保存、零新Run。字幕入口 `47f045f4` 因Mixed Director任意 prose字数限制两次失败；去掉 intent/visual_description 的非领域限制并暴露现有文字布局字段后，v2的两个字幕分别0–4s顶端、4–8s底端，原声/源窗保留，Run `d5866541` 已发起。第二网站入口 `6675b8b3` / Run `cd7fa91a` 已发起；这两条最终交付须待Docker/数据库恢复核验。最后上传操作演示入口只证明预填，浏览器上传权限及原生选择器阻塞，未标通过。
- **本批源头修复与取证**：design/revise工具说明与canonical卡片职责一致；修订观察用系统字段差异。MG Director明确实际background字段与读得清的配色，微推近/拉远通过既有transform.scale表达，不建相机引擎；首条暗字深底且缺运镜的错误首稿及正常Chat纠错保留。分镜区分逐词/逐字/逐行，update_text支持现有布局的像素x/y/width/height。一次英文片交付被错误称为中文，来源是project.language；新视频按保存设计声明传递content_language，历史未声明者不向交付模型声称语言，不回写旧版本/账本。当前简单修订已有简短回复样例，不宣称所有多轮语言稳定。旧展示hash调查原结论与original_hash_reproduced=false矛盾，已修正；当前重复DTO一致，历史原始工作树/DTO不全，无法声明完全复现旧漂移。
- **本批检查、费用与证据**：相关API125项、check_gates通过；Ruff检查中无用导入已删除，最终检查以本批收尾为准。前端TypeScript初次报既有并行mentions/支付改动类型问题，未写成全绿。原¥10窗口已记录USD0.9543168/约¥6.87及旧未知项不重置；用户另授权¥20，本次已返回供应商用量约¥4.73，含失败、修复与worker，当前API日志无未返回调用，历史未知仍另列。完整中英预填、实际消息、全部捕获模型payload/工具观察、SSE、证据与失败过程合并为 `artifacts/video-project-b/b-vi-temporal/chat-journey-review.md`，该文件不代替尚未完成的前端/交付验收。当前数据库重置连接且Docker命令超时，暂停新增收费操作，继续无付费检查；不擅自强杀Docker，不以环境阻塞删需求或标完整B完成。

### 2.1 目标

新链按 §2.5 分批支持“网页/MG/混合内容 → 分镜 → 首稿审阅 → 授权 → 制作 → 交付 → 持续修改”，逐步接入程序画面、生成媒体与旁白；不能把文字动画的阶段成果称为全部画面能力。launch-film 在新链只是 Skill，不再拥有专用设计或生产链。

### 2.2 施工范围

**B1. 内置 Skill 与通用设计**

- `app/skills/launch-film/SKILL.md` 保留创作工艺；新增 `video-template.json` 承接固定场景结构、Tracks/Clips/Objects/Animations、3–5 章 repeat 和可选 plate。
- `app/editing/templates.py` 实现有界槽位、repeat、variant 和展开；Template 不含 assistant 文案或可执行脚本。
- 新建通用 `design_video`：有 Skill 时实例化 VideoTemplate，无 Skill 时以结构化 edits 自由设计；两者共用 validator 与版本写口。
- Director 输出当前支持的创意内容/槽位、精确脚本和每幕 `visual_description`；B-IV 接入 Generator 来源与参数，受控视觉程序不受“只能填模板槽位”的永久限制；事实文案仍走 citation/grounding。
- capture、citation、网页视图绑定和容量校验保留在代码能力中，不复制进 Skill 文本。

**B2. 统一 Chat 编辑服务与工具**

- `design_video` / `revise_video` / `produce_video` 共用一个应用服务；plan/propose 不再各复制 compose/patch。
- `revise_video` 支持 Scene、Clip、Object、Animation 的当前所需 CRUD；结构化修改和开放修改都产生子版本。
- 新增 `get_video_version(version_id | composition_id + current)`，返回 canonical 保存版；多影片不能隐式选择 Chat 最新产物。
- 视觉内容的 Chat 修订同步更新受影响 `visual_description`；确定性手势修改则清空该字段并回退事实标签。
- 新版本完整呈现、change_set、未解决项与当前制作设置都由保存版生成；仅内容修订不产生虚假已交付 Output，制作成功后才交付新产物，旧产物保留。
- @output 服务端解算确切 CompositionVersion；“继续修改”与“当素材使用”分开。旧版不是 current 时明确差异与选择，以当前 head 条件提交，不静默覆盖。

**B3. 创作概要与首稿授权**

- `storyboard_payload(version)` 继续由服务端生成完整事实：时间/帧、visual_description、精确屏上文字、旁白、素材和音频事实，供工具、版本身份与修订使用，不直接作为用户技术表。
- LLM 基于完整保存版撰写简洁 Markdown 创作概要，自由使用标题、列表或表格，重点说明整体方向与大致画面设计；不输出第二份可编辑数据，不转录技术 DTO。
- 持久化 `presented_message_id + presentation_digest + composition_version_id` 到通用确认状态；消息块只携带版本引用，可见正文由 Streamdown 渲染。
- 按 VIDEO_PROJECT §2.3 明确概要与必要真实预览完整释放后的回执边界；生成 payload 不冒充已呈现，回执不冒充用户已读，首稿另需呈现之后的批准。
- 保留“首版先呈现创作概要并等待”、普通修订不重制、明确“改完直接做”才进入制作、auto/ask 与守卫线规则。用户确认方向，不逐项审批技术分镜。
- 所有 assistant 散文与 LLM 散文字段继续满足 null 读容忍和打字机节拍；真实预览不得成为提前 ACK 的旁路。

**B4. Graph / Run / Node 接缝**

- `produce_video` 只接受已存在且 digest 匹配的 CompositionVersion；缺版、引用身份失配或素材漂移即失败，不调用 Director 补设计。
- Start 固定 `run.context.version_ref = {composition_id, composition_version_id, content_digest}` 与执行输入摘要，仍经唯一 `create_run`；准备完成再固化 execution_digest 和真实派生素材 manifest，重试复用准备结果。
- `produce_video` 节点声明输入、估价和 Output；CompositionVersion/SourceSnapshots 提供需求事实，不在 orchestrator 增加 launch-film 式白名单和文字源例外。
- `step_context` 从版本与执行快照取估价事实，不读 pending_brief 的 Film 板。
- `graph_fill` 只投影响应版本/素材/产物血缘，不保存完整 CompositionVersion，不创建 Scene/Clip 节点。
- `lifecycle` 使用通用呈现回执与 version_ref；`run_review` 对照 CompositionVersion 与 Output provenance。
- Output payload registry、visible/delivered 判定、下载/产物卡、render probe 与 Chat delivery 同批接纳 `type=video + composition_version_id`；不能让 B 的真实视频产出了文件却被现有 film/clip 准入过滤。
- 保留 `create_run`、WorkflowStep inputs、NODE_KINDS、render ownership、队列、fencing、hold→capture→release 和 run finalization。
- 当前 LaunchFilm 的“无 prepared state 就重新 orchestrate”不得进入新 produce；如无人值守设计仍需保留，另走显式 design 操作。
- TTS 默认固定切点：有界语速适配，超界返回冲突并经 Chat 形成新版本；不得借帧、改原文、静默截断或丢旁白。配置语速范围、尝试次数与成本上限后才接付费合成。
- 字幕记录旁白派生关系；用户手改后的字幕不得被旁白重生成覆盖；显式同步才修改。制作/Start 幂等、部分准备恢复、失败结算与授权版本一致性同批验证。

**B5. 素材上下文与 Chat 表面**

- MaterialDigest 列出当前素材、读取/采集状态、CompositionVersion 绑定和可更新事实。
- 同回合同 canonical read key + snapshot 复用 Observation；设计装配器直接读取绑定 manifest，不反复要求 `get_web_page`。
- 只有用户明确刷新才更换 SourceSnapshot；digest 差异必须呈现。
- 新链不以 `canvas_available`、FlowView reveal、rank 或相机状态作为设计/Start 条件。
- Graph 先保留作隐藏血缘/修订拓扑；Canvas 可保留现状，但 Storyboard/CompositionPreview 必须能在纯 Chat 中完成全程。B 提供最小预览，C 直接复用。
- Chat 产物按 Output 平铺，消息行分散触发同一个可翻页查看器；版本仅作标识，行为唯一合同见 VIDEO_PROJECT §10.4，独立增量出口见 §2.5.2。
- 接入全局素材库所需的跨 Chat @asset/@output 解算、权限和素材快照固定；可先复用现有 picker/查询，不以完整素材库页面或管理功能为前置。
- Run/确认/费用归当前 Chat，Composition 记录来源 Chat；保留现有项目级执行互斥，同时阻止跨 Chat 并发生产破坏同作品发布/归档不变量，不能擅自把全平台改成多 Run 调度。

**B6. 开发期直接替换的集成批次**

- 按一个可审查的集成范围替换旧 Film 内容模型、工具/读面、首稿呈现与授权引用、估价/计费输入和交付判定，避免新旧版本信封之间反复转换。集成中可分小提交，不要求一个巨大提交或重写 Chat/Run 内核。
- 旧 Film 专用调用者随其替代接缝一起删除，不为旧请求/旧数据增加兼容层。B 不再被调用的代码立即清理；D 做最终全链引用审计和残留删除，不把已发现死代码都拖到 D。
- 开发集成窗口允许 Film 通路暂时不可用；标记真实状态，不把半接通的新链设为已可用。默认入口切换与批次验收以完整用户旅程为门，不能只凭编译或 MP4 成功。
- 破坏旧内部合同不等于取消首稿审阅、制作意图、费用守卫、owner 校验、幂等/fencing、真实交付和项目执行互斥。复用通用可靠性机制，重新证明新版本引用贯穿这些机制。

**B7. Chat 旅程与真实制作过程**

- 后端接口与数据按 VIDEO_PROJECT §10.3 解耦呈现：补齐正文/活动/版本/执行/产物关联，结构化安全事实，历史快照与 SSE 同源。不把 UIArc 或现有组件字段固化进领域模型，不为整合显示新增第二意图面或通用 Work/Task 根。
- 按 VIDEO_PROJECT §10.1 分配正文、canonical 版本卡、工具活动/Run 工作段与成片卡职责；设计、修订、制作与交付依序呈现，不靠模型长篇汇报替代过程。
- 基于现有 Activity / Run 协议实现真实阶段的最小持久化、推送与回放，呈现可采用整合 block，不要求保留 WorkSegmentRow / RunTaskList 组件；绑定版本、run、step、attempt，保证事件有序去重、旧尝试不覆盖新尝试。单个 produce 节点可有内部阶段，不为显示扩张执行图。
- 选定的呈现组件适配已有 DTO、状态机和主题；正文继续走既有打字机与 null 读容忍，活动不暴露 raw tool calls/reasoning，首稿与费用授权不被视觉调整绕过。通用 Chat live 折叠与 Run 工作段按既有合同分别处理。
- 列出实际阶段及其唯一发射点、缓存/关闭/失败/重试表现和记录写口；采用短事务与现有 fencing，不能让进度写入干扰计量、执行或终态。A 可先提供 fixtures，B 接真实路径，不要求 A 首个 MP4 切片先实现整套 Chat。

### 2.3 当前代码处置与目录验收

新旧文件的新增/拆分/原地修改/保留/删除及阶段归属，唯一清单见 [VIDEO_PROJECT §12](../VIDEO_PROJECT.md#12-目标目录与新旧代码处置)。本处不复制第二份目录树。

- A 先落实 editing、tools/video 最小执行、video-spec、renderer adapter 与必要 ORM/迁移/Output 接线；不创建 C/D4 空目录。
- B 按母文档 §12.2 逐行核对，尤其不能漏掉 main 启动 sweep、FilmNarration 存储、工具/Skill 注册、费用单位、render/probe/route 准入与 UI 协议。
- D1 按同一清单审计实际删除结果；Film 目录须先提取配音复用、grounding、相机/文本等有效能力，不做整目录盲删。packages/clip 与共享依赖另按消费者保护。

### 2.4 B 阶段验收

- [ ] launch-film 在新链不出现在执行工具名中；同一 VideoTemplate 能生成当前固定官网弧。
- [ ] 无 Skill 的 MG 与有 Skill 的官网片共用 CompositionVersion、CRUD、produce、render 和交付。
- [ ] 分镜“画面与动作”列使用真实 visual_description；无虚构元素，视觉手改后旧摘要失效。
- [ ] 首条“直接做”仍只完整呈现首版；呈现回执未持久化时 Start 失败闭。
- [x] 实际 Run 的 version_ref 等于刚呈现版本；worker 不重新设计，Output 可回溯同一版本。（官网片旅程实测：Run 钉 v1/v2 digest，Output provenance 回溯同版）
- [x] 普通修订只落版；“改完直接做”按当前消息制作意图与 auto/ask/费用规则执行。（实测：文本修订只落 v2 零 Run；「改完直接做」176<守卫线 auto 档直接开工）
- [ ] 网页 Scene 可新增黑底白字说明而不改相机；同一 Object 可修改位置/文字/动画后删除；同一动画 Preset 可作用于 Text/Image/Video。
- [ ] 连续多轮修改不需要重复网页采集或重复读取同一快照；显式 refresh 才产生新绑定。
- [ ] 同 Chat 两部影片分别 @ 修订，各自生成正确新版本/新交付；跨 Chat @ 旧产物能明确继续修订或作为素材，不建“复制确切作品”流程。
- [x] 固定切点下旁白有界语速适配通过；超长明确冲突、切点不动；手改字幕不被重生成覆盖。（B-VI 两幕真实首产/修订复用、9.892s 对 4.000s 的真实冲突及独立字幕帧证据通过；本次真实第二 pass 样片见 §2.0；用户已确认视频有声音，完整独立听感仍未关闭。）
- [ ] 纯 Chat 无 Canvas 时可完成设计、审阅、Start、交付和修订；Graph/Run 状态不依赖布局坐标。
- [ ] 正文、工具活动、版本与成片卡顺序一致；刷新/重连不丢失、不重复、不串作品；拒绝回合不泄漏未接受的预览或产物。
- [x] Chat 产物共享查看器通过 §2.5.2 的多轮交付、历史归档与刷新回放验收；不同作品和同作品不同交付均按 Output 平铺，版本字段准确。
- [ ] 同一后端数据可驱动既有 Chat 与整合 block 呈现原型；异步 Run 跨回合仍可准确关联，刷新不重启执行，停止接收流不误作后台取消。原型验证不代表 UIArc 选型通过。
- [x] 旁白关闭、准备缓存命中、渲染后交付检查、失败恢复与重试均呈现真实阶段；旧 attempt 不覆盖新状态，未交付不提前显示完成。live 与回放对应同一执行事实。（实测：无旁白为内容模型结构性保证；失败 Run 全额 release + 诚实文案；重试 capture 恰一次；渲染中 Output files={} 不冒充完成；ACK 重放 accepted:false）
- [ ] 默认布局与选定呈现组件均保持授权、工作段收口、打字机、中英文、移动端、键盘可用性及 reduced-motion；不依赖模型整块汇报才知道进度。
- [ ] 完整动态看片与独立音轨试听通过；配置、probe 或静帧不冒充动态/听感验收。
- [ ] 有界失败、统一 LLM 调用预算、报价/实扣、重试幂等和过期 base_ref 均有真实旅程证据。

- [ ] **B-III**：动态背景、中央录像、独立标题/字幕、原声/音乐可混合；源窗/输出窗与声画同步正确，Chat 局部修订不串改其他层，真实播放与试听通过。（真实 Chat 五版修订、再交付、浏览器播放、帧/音轨结构与刷新不重复开工已通过；亲耳试听未完成，故不勾）
- [x] **B-IV**：至少一条原生图形动画经 Chat 设计并精确修订；至少一条 Generator 程序画面经 Chat 编写来源→预览→按反馈改内部参数或程序→固定生产→与其他独立内容合成并交付。保留 object_id/版本血缘与未改层，成功结果可复用，渲染重试不重新创作；不以开发者手写预设代替 Agent 程序创作，不虚构烘焙媒体内部原生可编辑性。两个纵向出口见 §2.5.1。（两个独立真实 Chat 项目分别完成设计、v2 局部修订、固定 Run/Output 与帧核验；Generator 另有浏览器动态预览/ACK、exact-digest 缓存与真实 Output resume 复用、交付后 v3 标题修订证据。）
- [x] **B-V（仅首个单图消费者）**：复用 GeneratorObject 的来源/结果边界，至少一个明确声明的图片或视频生成用例经请求/费用授权、真实生成、固定结果、合成与交付；失败/重试/明确重新生成的身份与收费边界正确。单一用例不等于两类生成均支持，也不等于所有模型支持。（MiniMax image-01 16:9 单图经真实 Chat 完成首产、原生标题修订复用、同版明确重生成及最新媒体再交付；四次 Run/Output、两次真实图片计量、回放不重复开工与固定 manifest 后恢复证据保留。供应商响应未知窗口已补单次 POST + submitted 失败闭及定向替身证据，见 §2.0；仍不承诺供应商恰好一次，其他供应商与生成视频未接，完整 B 未封板。）

### 2.5 B 的增量批次与出口

下列罗马编号标识增量批次，依赖按 §8，§2.2 的 B1–B7 仍为职责清单。批次分开不取消原合同；每次仅实施一个明确出口，不要求一次 compact 完成全部 B。

| 批次 | 内容与出口 | 当前层级 |
|---|---|---|
| **B-I 基础 Chat 闭环** | MG 设计/呈现/批准/制作/播放，同作品多轮与跨 Chat @output 修订；唯一写口、固定版本、计费/交付可靠性 | 主链真实通过，剩余过程/恢复守卫持续按实际缺口补 |
| **B-II 官网片与过程收口** | 官网模板/grounding/快照/镜头/字幕/音乐；真实 Chat 首稿审阅→制作→播放/试听→局部修订；刷新恢复、真实阶段和剩余 prompt 检查 | 真实 Chat 闭环、修订同一性、刷新恢复与帧级播放核验已通过（证据见 §2.0）；欠账：听感试听、付费 prompt_gate、运镜修复像素级复验（随下一首稿）、音乐循环接缝真实渲染 |
| **B-III 混合合成底座** | VideoObject 的 schema→source/probe→编译→adapter→Chat 全链；源窗与输出窗、原声同步/音量/静音、画面位置/尺寸/裁切；与原生标题/字幕、动态背景/音乐同时合成 | 真实 Chat 首稿、四种局部修订、v5 再交付与浏览器播放/刷新已通过；局部换源窗保持输出时长，亲耳试听与付费 prompt_gate 仍未验收 |
| **B-IV 原生 MG 与程序画面** | 原生最小图元/路径可经 Chat 精确改动画；GeneratorObject 允许 Agent 编写、预览、修改受控视觉程序，固定来源与结果后混合合成，解锁可再创作的特殊背景/示意画面 | 两个纵向真实 Chat 出口分别通过；drawing-v1 动态预览、局部程序修订、固定生产/交付、缓存与 resume 复用已验；不扩为全量图形引擎或代码平台 |
| **B-V 模型生成媒体** | 在 Generator 来源上增加一个确切 provider 的图片或视频生产，沿既有授权/费用→固定媒体/血缘→合成，解锁生成素材与原生可编辑层组合 | 首个 MiniMax image-01 16:9 单图真实消费者已通过 Chat 首产、原生修订复用、明确重生成与最新媒体再交付；固定/执行身份、计量和回放边界有定向证据。响应未知窗口已补单次 POST、submitted 恢复失败闭与无网络回归，未知消耗仍需对账且不承诺恰好一次。只声明 image-v1，其他供应商与生成视频未接，完整 B 未封板 |
| **B-VI 旁白与原合同余项** | Speech/TTS 固定切点、有界语速、超长冲突、字幕派生及手改保护；split/trim/首个必要转场/BeatGrid 按已声明消费者实施与验收 | 首个 MG + MiniMax speech-2.6-hd 两幕中文消费者已通过真实 Chat 首产、字幕单独恢复、单幕旁白修订再交付、未改音频复用、人工字幕保护、实测超长冲突与浏览器硬刷新；真实加速样片及具体跨作品回执故障已补齐，完整听感和其他多轮稳定性仍开放；本批另已补齐固定媒体 split/trim、全画幅 crossfade 与冻结音乐节拍吸附，真实 v6/v7 证据见 §2.0；仍不声明完整 B 封板 |
| **B-UI 产物平铺与共享查看器** | 各轮交付消息保留产物卡，当前 Chat 全部已交付 Outputs 共用翻页与缩略导航；版本作字段标识，历史交付仍可读取 | 代表旅程通过，用户已确认视频有声音，见 §2.0 / §2.5.2；不等待 C/D4 |

**B-III 的代表性验收**：动态背景 + 中央真实录像 + 独立顶部标题 + 定时字幕 + 原声/音乐，在同一 Scene/Composition 混合；通过 Chat 只改一处字幕或中央录像布局，未改内容/源窗保持，再制作交付。背景可先用已有动态素材或受支持对象动画，不把复杂自由 MG 当作混合合成的前置。此后 B-IV 再验证原生/程序画面替换背景，B-V 再验证生成媒体替换其中一段；不为每次接入重复建设生产链。

**声明与发布门**：§2.4 逐项按证据更新，未实现/未验收不勾选。首个限定能力发布可以只声明 B-I～III 中实际通过的内容，但仍需完整授权/收费/恢复/交付和 D1/D2 发布门；明确不支持的生成视频、通用转场、自由改时长等继续留在合同，不标完整 B 完成。需要这些能力的产品承诺必须先完成对应批次。不因新增 B-IV/V/VI 批次自动授权外部模型费用、安装依赖或部署。

**实现纪律**：一次代表性真实旅程驱动必要功能及少量承重守卫；不提前创建未来模块/表/空目录，不建立另一份目录树。新增文件/模块按 VIDEO_PROJECT §12 及模块图同批登记。用户可用入口、版本和成片优先于样片脚本数量；仅对实际修改运行必要检查，最终集中回归。

### 2.5.1 B-IV 的两个纵向出口（已分别验收）

1. **原生图形**：从一条真实需求选择最少必要图元/路径属性，贯通表达→Chat 设计/修订→编译→renderer→交付；至少修改一项形状属性或动画而保留其他层。沿用 Animation 与唯一内容写口，不先扩成矢量编辑器。
2. **Generator 程序画面**：从一种受控运行时和一条短 2D 或 3D 需求开始，冻结 VIDEO_PROJECT §4.3.2/§8.1.1 的首个实际 schema、程序/资源身份、参数和输出约束。用现有 Chat/Director/harness 生成视觉程序，给出动态预览、真实诊断与可读取的视觉反馈，按用户意见修改内部画面，再钉来源生产并合成；不是仅改烘焙视频的外部布局。完成片继续可按同一 Composition 修订。

最小预览随程序消费者交付，完整 scrub/Inspector 仍归 D4；不另建预览任务系统或无限自修复环。程序运行只获得声明资源与受限能力，不获得业务图/数据库/计费/任意网络访问权；依赖及运行方式按真实需求选择，不把安装授权或第三方许可视为默认存在。

当前四层结果均有真实证据：

- **表达**：CompositionVersion 可保存原生 ShapeObject 的几何/填充/layout/transform/opacity，以及 GeneratorObject 的 drawing-v1 code/parameters/output；跨版本 object_id 与 program_digest 稳定。MG Director 当前按需创作 rect/ellipse，path 是原生 schema/精确编辑能力，不宣称 Director 已覆盖任意路径设计。
- **执行**：原生图形经 video-spec 与 SVG adapter 渲染；drawing-v1 在受限进程中生成固定 MP4/PNG，生产与合成复用既有 Run/Output/Render。最终 spec 只消费固定媒体，程序与模型请求不进入 renderer。exact-digest 缓存命中不执行程序；真实已交付 Output 的受控 resume 分支返回原 Output、原 execution_digest 与原媒体，未重新准备。
- **创作**：原生项目 `5bf0b8f3` / Composition `c8cb1b68` 的 v2 Run `5c260ea6` → Output `083c8b3b` COMPLETED。Generator 项目 `e0736859` / Composition `c41b1ce9` 由 Agent 写出真实 `render(ctx)`，v1→v2 改绿色与双倍速度，60 帧均不同；Run `eb9a70e9` → Output `2c45efe4` COMPLETED。浏览器中预览从可播放前零 ACK 到真实播放后对应 ACK，1 秒与 2.5 秒成片帧确认程序画面与原生标题合成。
- **编辑**：原生 v1→v2 的 change_set 仅含目标 shape 的 object+animations，另一图元与标题不变；Generator v1→v2 仅改 Generator object 的 code/parameters，标题不变；交付后 v3 在同一 Composition 仅改标题，程序 digest 不变且未新增 Run。烘焙媒体内部元素不冒充原生可编辑对象。

每条代表旅程只证明上述实际能力，不穷举特效。本出口不覆盖其他模型媒体或生成视频；旁白留 B-VI，Skill 持久化/导入留 C，完整 scrub/Inspector 仍归 D4。第二模型接入只在出现实际能力需求时另明确范围，不预先承诺同等创作质量。证据位于 `artifacts/video-project-b/b-iv/`（Git 忽略）。

### 2.5.2 B-UI：产物平铺与共享查看器（代表旅程通过）

本批归 B5 的 Chat 表面接入，在已有交付链与 Output 引用上独立施工、独立验收；不等待个人 Skill、完整视觉改版或 D4 Inspector，不改变既有首个限定能力发布门。当前代表旅程与有声播放证据见 §2.0；不代替完整音乐接缝/音画同步听感或完整 B 验收。产品行为唯一事实源为 VIDEO_PROJECT §10.4。

当前查看器已在共享 `MediaLightbox` 内接入全屏媒体舞台、卡片往返飞行、滑动/下拉手势、图片缩放与底部缩略导航；视频保留原生控制，选中事实仍按 exact Output ID。此次视觉与手势替换仅完成落码，TypeScript、API 与真实浏览器检查尚未运行，下方既有代表旅程证据不自动覆盖新交互。

**施工范围**：

1. 核对并补齐前后端 Output DTO 的准确版本标识、作品/内容版本引用与归档信息；复用现有身份，不新增作品根或浏览专用持久化模型。
2. 从持久化交付记录构建 Chat 的 Output 顺序与索引；补齐受权限约束的历史归档读面，复用既有查询与推送，不能只依赖当前活跃结果列表或 DOM 注册。
3. 将查看器状态提升到 Chat 共同宿主，各消息行按 `output_id` 打开；复用/演进 MediaLightbox、AnchorCards 与共享媒体展示原语，适配现有 Dialog、主题和声音互斥。UIArc 为交互参考，组件源码采用方式按实际接口核对。

**代表旅程与验收**：

- [x] 同 Chat 两个作品各有两次真实交付：四个 Outputs 在各自消息行保留入口；从任意项打开均可按交付顺序浏览全部四项，无作品分组或版本树前置，版本标识与实际内容引用一致。项目 `92486f3c` 的 Morning/Night 各 v1/v2 四交付已实测；另有 Morning v3 与同版再交付。
- [x] 同内容版本再交付仍是独立 Output、保持相同内容版本标识；普通修订未制作不新增成片项，失败/未完成制作不冒充交付。真实项目已有三个同 v2 Output 独立显示；AgentVeil v5 仅保存无 Output；内部/未完成行由交付准入排除。
- [x] 新交付使旧 Output 归档后，旧消息仍可打开、播放、下载和准确引用；刷新/重连顺序不变、不重复，新增交付不抢走当前项，引用失效明确显示不可用。归档 v2/v3 的打开、播放、下载与 @ 引用已通过；硬刷新六项顺序与身份保持；打开状态 3/5 → 3/6 不抢原 v2；不可用替代禁止已有纯测试。
- [x] 混合媒体按声明类型和画幅展示，竖屏不裁；文档页码不混用 Output 序号，视频切换无残留声音。关闭恢复聊天位置与焦点，移动端、键盘、双主题和 reduced-motion 通过。竖屏 contain、真实文本/PNG、三页 carousel、视频切换、关闭消息位置/焦点恢复、440×956 移动端、双主题、左右/Escape 与 reduced-motion 均有真实浏览器证据；用户已确认重新展示的视频有声音；完整独立听感不在本浏览能力通过范围。
- [ ] 当前全屏舞台与 Arc 式交互完成真实复验：卡片打开/返回飞行、跨消息关闭不追滚、图片 pinch/滚轮/双击缩放与惯性 pan、视频原生控制不受手势拦截、移动端缩略导航、双主题和 reduced-motion；先通过 TypeScript 检查，再跑上述浏览器旅程。

### 2.5.3 B 支撑增量：按需采集与内容质检（两个首个最小闭环已通过，完整能力待扩）

以一个真实产品页的页面特写/元素运镜镜头和一次真实审片修复作为首批出口，按需补现有能力，不另建大阶段。两个首个切片均已按 §2.0 的真实 Chat 证据通过，只证明链路成立，不替代完整需求验收。产品规则归 VIDEO_PROJECT §9.2 / §8.5，排期归 PROGRESS §0；B-UI 仍为 B 最后一个功能批次。D4 时间点编辑另按 §4.4 实施，不作为审片前置。

| 增量 | 首批代码改动 | 验收 |
|---|---|---|
| 镜头素材采集 | 在 `tools/research/capture.py` 补渲染正文和整页高清图；按所选镜头补元素截图/坐标，复用 `pipeline/web_capture.py` 与 `tools/video/preparation.py` 存储、冻结和消费。仅扩实际需要的 DTO 与 grounding 接缝 | 一个真实产品页的内容足够支撑设计，所需截图和元素能完成一个实际镜头，位置/清晰度正确；需要空底板或交互状态时随此镜头验收，不强制首批覆盖全部选项 |
| 内容审片 | 在 `tools/video` 增加小型审片实现（可为 `review.py`），直接解码成片取帧，复用 `agents.py` 与现有质量/交付读面；`run_review.py` 只读报告事实。只在确有消费者时扩 verify/quality | 对一条真实影片报告一个可复核问题，经正常修订后复核改善；范围与未检查项诚实，费用和执行复用既有机制 |

只补与旅程风险相称的检查。稳定身份、权限、授权和资源限制复用既有实现，不逐处重复设置守卫；不把全站采集、完整帧平台或所有异常分支覆盖设为本批前置。

**需求保留与封板条件**：

- 采集仍须满足选定 video-shotcraft 镜头和自我介绍视频的实际素材需要；当前 AgentVeil 正文采集有界且 `body_truncated=true`，新冻结 manifest 已在根级携带该标志，Director 独立 `CAPTURE STATUS` 区读取三态且不作为产品正文引用；旧快照缺字段只读 UNKNOWN，不做历史回写。长页补读仍开放，空底板与交互状态也未实现。后续镜头确需这些能力时登记并补齐，不以首个静态镜头成功关闭整项。
- 内容审片按 VIDEO_PROJECT §8.5 对实际作品逐项说明文字/构图、内容一致性、运动衔接与适用声音检查的覆盖；单次问题修复只算最小闭环，未检查项不算通过。
- 不为覆盖未来情况先建平台，也不因简化实现删除已经明确的产出能力；剩余实现/验证有当前归属后才结束一个切片。

## 3. 阶段 C——个人 Skill 保存、调用与外部导入

### 3.1 目标

用户能把满意的作品保存为自己的 Skill，并在以后通过 `/skill + prompt` 或明确点名复用；外部 Claude/Codex Skill 能安全转换为当前能力可表达的 SkillDraft。

### 3.2 施工范围

**C1. Skill 存储与版本**

- 新增用户 Skill 与 SkillVersion 持久化；平台内置 Skill 继续走代码注册表，用户 Skill 按 owner 隔离。
- SkillVersion 包含 instructions、VideoTemplate、Presets、输入/能力要求、可选 PromptTemplate、示例 provenance 和 source hash。
- 保存时从 CompositionVersion 确定性抽取，不由 LLM 重写数值；LLM 只协助名称、description 和使用说明。
- 默认排除用户事实文案和源素材；示例引用必须遵守权限与公开性。
- 已支持的 Generator 可保存固定程序来源、参数槽位与能力依赖；把私有素材改为显式输入要求，不复制结果冒充可复用方法，沿用唯一作品/制作链。
- Template/Preset 实例化后展开进 CompositionVersion，旧作品不随 Skill 更新变化。

**C2. `/skill + prompt`**

- `/` 打开 Skill picker，选中形成可见 Skill chip；消息携带确定的 `skill_id + version`，仍走唯一 `POST /chat`。
- 自然语言明确点名时通过普通 Chat 解析到用户拥有的唯一 Skill；歧义必须询问，不能任意搜索加载。
- 首版一次创作只绑定一个显式用户 Skill；平台安全/grounding 规则始终优先。
- Skill 不自动发送、不自动 Start、不免除首稿审阅或费用确认。
- Home 现有 Recipe 只按 PromptTemplate 语义继续使用；涉及其代码改名时全栈同步，UI 不新增“配方”标签。

**C3. Strict / Adaptive**

- Strict 保留模板声明的结构、时间和参数；新素材不满足就给出具体冲突。
- Adaptive 只使用模板声明的章节数、时长、布局等可调边界；每次适配都要呈现。
- Skill 只保存创作方法；使用现有素材/产物通过全局 @ 引用，不建设“复制确切作品”功能。新素材复用不得承诺不成立的像素级“一模一样”。

**C4. 外部 Skill 导入**

- 解析 SKILL.md、frontmatter 和 references；限制大小、数量、路径与类型。
- 分离创作指令、结构要求、示例和外部依赖，生成 SkillDraft + 能力差异报告。
- 外部 `scripts/` 不自动执行；`allowed-tools` 不授权。导入内容只能转换到已支持且受控的能力；Generator 的显式程序创作按 VIDEO_PROJECT §8.1.1 执行，不将外部任意脚本、网络/文件访问或私有工具直接放入运行链。
- 只能映射到已注册 Objects、Animations、Binders 和 Validators；缺失能力明确列出。
- 外部内容视为不可信创作输入，不能覆盖系统、grounding、权限、报价和授权。
- 用户用真实素材审阅生成的 CompositionVersion 后才可保存。
- **必验消费者 = video-shotcraft**：固定仓库 commit 与选定卡名/变体，解析 SKILL.md、references、准确 demo 实现及共享依赖。先选一段能体现其真实方法与实现的代表镜头，完成换素材制作与文案/配色等实际修订；保留原生可编辑层和受控程序来源的区别。所需能力按首个消费者补齐，不能以“已报告不支持”结束此验收，也不能把只读提示词后另写简化动画称为成功加载。
- 代表镜头是首批切片；C4 最终须用导入后的方法和选定实现完成真实产品的多镜头成片、局部修订，以及换另一产品内容的完整复用，不以单个 demo 代替。
- 保存声明支持范围的 SkillVersion，绑定新产品素材再制作；日常复用不要求开发者逐次改业务代码。未选镜头、私有工具或未支持依赖明确列出，不宣称完整兼容镜头库。沿用唯一制作链；源程序适配保留 provenance，外部安装、采集或发布命令不因导入而自动获准执行。

**C5. 复用 Chat 预览与引用组件**

- Storyboard/CompositionPreview 以版本引用加载 DTO，可刷新回放，不依赖 Canvas。
- 预览通过 PreviewAdapter；不把 Remotion 组件名写入消息或 spec。
- 本阶段不做 Scrub；仅建立后续 Inspector 所需的稳定 version/clip/object 引用。

### 3.3 C 阶段验收

- [ ] 保存 Skill 后，结构、Track、布局、动画和参数与来源 CompositionVersion 的声明范围一致。
- [ ] `/skill + prompt` 在刷新后仍绑定同一 SkillVersion，无隐藏 recipe_id 或第二执行链。
- [ ] Strict 不可满足时明确失败/询问；Adaptive 的变化完整可见。
- [ ] 外部 instruction-only Skill 可转换；依赖脚本/私有工具的样本得到明确能力缺口而非静默降级。
- [ ] video-shotcraft 的声明镜头范围完成真实加载→使用本产品素材制作→保存 SkillVersion→换另一产品素材复用→Chat 局部修订与交付；固定来源/依赖，准确区分原生与烘焙编辑能力，不靠片外工程替产品完成。
- [ ] 恶意 Skill 不能越权读取素材、调用工具、绕过授权或修改系统规则。
- [ ] 个人越权访问、版本固定、旧作品独立性和纯 Chat 回放通过。

## 4. 阶段 D——切换、旧 Film 退役与后续扩展

D 是独立依赖门集合，不是等待 C 全部完成后的大批次。D1 依赖 A 与所声明发布范围的 B 验收（首批至少 B-I～III）及 D2 生产许可结论；个人 Skill 的 C 可独立推进，不阻塞内置 Skill/MG 切换。D3/D4 为后续扩展，不计入首个限定能力发布条件；B-IV～VI 的未完成项继续独立存在，不能借 D1 清理抹掉需求。

### 4.1 D1：新链切换、旧 Film 删除与最终清理验收

- 新链默认承接网页宣传片与 MG；旧入口在注册表、prompt、Chat tools、Run 和 UI 同步关闭。
- 删除旧 Film 专用 design_storyboard、LaunchFilm、FilmStoryboard、film-spec 及其不再使用的 prompts/validators；可复用通用部分已在前置阶段归位。
- 不写旧数据迁移；按 §0 数据授权可清理本应用开发/生产旧数据，先核对目标与 dry-run，不重复索取已给出的同范围许可。
- Output、发布、下载、probe、计费和交付读面完成 `type=video + composition_version_id` 接缝核对。
- 当前 Film 的有效安全/授权/视听要求必须已由 B 吸收并验收，不能因删代码消失。

**D1 必须包含一次显式删除清理，关闭旧入口不算完成。**逐行对照 VIDEO_PROJECT §12.2 的实际路径和处置（旧文档/结构锁可先退出，实际运行代码仍按消费者门删除），不维护另一份删除目录表。

- [ ] 审计运行调用链与仓库引用，删除旧 Film 专用工具/schema、compiler slot/白名单、pending_brief 信封读写、prepared_storyboard fallback、估价/审阅特判及旧 render family 分派；共享能力先核对 Clip 和其他消费者。
- [ ] 删除无消费者的旧 film-spec 包/adapter、预览代码、依赖、临时开关、环境配置、开发脚本和失效 fixtures；只有仍需该依赖的消费者为零才移除，不能连带删除旧 Clip 所需能力。
- [ ] 删除被新 Chat 呈现替代的 Film 专属汇报 prompt、重复状态映射和无消费者组件；复用的 WorkSegmentRow/Activity 与旧 Clip 仍有消费者时保留，不维护两套进度或 transcript 顺序推导。
- [ ] 测试按新语义更新：保留有效授权/并发/计费/交付守卫，删除只断言旧结构的测试；更新 prompts、注册表、类型导出、文档导航和唯一合同，不保留失效规范或归档副本。
- [ ] schema 废弃列/表以新的 Alembic 迁移处理，保留已执行迁移历史；实际清库/删数据按 §0 的已有授权、目标核对和 dry-run 执行，不扩大删除范围。
- [ ] 核对 API/worker/render/web 运行版本，确认无旧 worker、队列任务或缓存载荷仍要求旧 Film 合同，再完成部署切换；测试隔离环境先排空/取消旧任务，不能让旧任务被新 schema 错误解释。
- [ ] 允许保留 launch-film Skill 名称、有效研究与新旧对照的必要证据；验收目标是旧执行链无活跃消费者与回退入口，不是全库 film 关键词清零。
- [ ] 清理后重跑依赖方向/引用检查和受影响测试，再走现有 UI 下的设计、审阅、制作、交付、@修订与失败恢复旅程；无新旧双写/双读，旧 Clip 与共享 Run/计费链不回归。


### 4.2 D2：Renderer 商业与能力收口

- 根据 A 的 spike 选择购买许可或替代实现；生产前必须有明确结论。
- 替代 adapter 与 PreviewAdapter 同批验收，不仅替换服务端打包命令。
- 完成能力矩阵、golden fixtures、动态帧/音轨对照、失败闭和真实渲染成本测量。
- 不支持的能力在 Start 前暴露，不在制作后静默降级。

### 4.3 D3：Clip 后置

B-III 的 Video/原声混合合成不等待 D3。D3 在共同底座稳定后逐项承接旧 Clip 产品的 reframe、segments、ASR/caption/translation、dub/music/intro/outro 等高层能力；原生字幕/音频基础能力与整套旧产品迁移分开。每项独立验证读写、渲染、真实旅程和费用；旧 Clip 只有在全部仍需能力有等价承接后才删除。本四阶段不以删除 Clip 为完成条件。

保留能力映射：reframe/crop_track → 视频取景与源时间派生数据；segments → 源窗和选段决策；title → TextClip；caption/translation → 语义/对齐结果及其 TextClips；dub/music → AudioClips；intro/outro → Scene 预设。ASR words、speaker_map 等仍保留上游事实与 provenance，不为统一 Object 丢弃高层操作或重写理解链。

### 4.4 D4：Scrub 与 Inspector 最后实施

- 在稳定 CompositionVersion、Clip/Object id、PreviewAdapter 和 `apply_composition_edits` 上构建。
- 按 VIDEO_PROJECT §11.3，从一个明确版本、时间点和目标对象做起；复用现有求值/渲染实现预览本地草稿。首批选定一个真实属性（如字幕位置或字号）贯通，不先建设全对象时间点接口；动画驱动属性明确修改作用域。 首个属性通过仅代表该切片通过；本节及 VIDEO_PROJECT §10 已声明的其余局部编辑、取消/冲突和预览一致性要求继续保留。
- 首版 = Chat 内局部编辑窗口（参考 UIArc Scrub Input 示例）：默认编辑一个明确的 Clip/Object；预览保持影片宽高比与准确位置，可显示场景背景或干净背景；不要求轨道、多选或完整视频播放。字幕 Inspector 可采用左侧真实画面、右侧位置/样式/动画；推荐文案由当前真实状态产生。
- 连续调整与 `onValueCommit` 都只更新本地草稿；用户点击「应用」才携带 base_ref、稳定目标标识与批量 edits 经唯一内容写口形成一个新版本。Escape/取消、冲突处理与失败回滚乐观预览保留；键盘可访问。
- mousemove/commit 不调 LLM、不建版本、不触发付费渲染。
- 多对象批量编辑与整片预览留作后续扩展，不是首版前置。
- 旧消息组件钉旧版本，只有当前版本可编辑；重制与授权仍走现有 Run 机器。

## 5. 跨阶段验证与交付纪律

1. 纯函数：按实际改动运行必要定向套件，不为覆盖率扩张测试/脚本；集中回归在 B 完整闭环与发布候选执行，命令为 `cd apps/api && uv run --extra dev python -m pytest tests/ -q`。
2. 架构门：`cd apps/api && uv run python scripts/check_gates.py`，新增依赖方向、唯一写口、renderer-neutral 与退役节点检查。
3. Prompt 面变化：`cd apps/api && uv run python scripts/prompt_gate.py`；付费与配额先获授权，失败不为放行调阈。
4. 真实旅程：更新当前 `chat_scenarios.py` 的网页/MG 旅程或登记新的主流程旅程，断言版本/工具/授权/交付形态，不锁 LLM 文案。
5. Web/render：按改动运行 TS schema、纯求值、组件与渲染测试；preview/render parity 需要真实帧证据。
6. 人工验收：完整 Chat、首稿停等、Start、CRUD、刷新恢复、动态看片、独立音轨试听；这些不得由 pytest/tsc 替代。
7. 并发、计费、授权、素材权限和有界失败是上线硬门，不能以“内部开发”名义豁免；不迁移业务数据不等于不做 schema/安全验证。
8. 验证结果写入本文对应阶段和 PROGRESS 当前快照；未运行项明确保留，不合并成“已验收”。

### 5.1 ABCD 综合验收作品（计划，未制作）

最终产物是 **Repurposer 自我介绍视频**：用产品自身讲清“我能做什么、用户如何提出要求、助手如何创作/检查/修改并交付”，验证真实工具组合与方法复用。建议约 60–90 秒，时长随叙事和已支持政策调整，不建立专用模板或自动聊天纪录片子系统。

- 通过实际 Chat/Skill 入口完成：需求→设计→原生文字/图形与实拍/图片混合→Generator 程序画面→针对原生元素及程序内部画面的局部修订→成片。允许用户提供素材、创意与多轮反馈，不要求一轮自动复刻参考视频。
- 以真实过程的已核对摘要、截图/录屏和成果作素材；拟人化旁白可以是创作，但不得伪造实际工具、耗时或执行结果。模型生成媒体、旁白按已声明能力和叙事需要使用，不强迫每个功能都出镜；核心检查与修订验证见下。
- 使用 C4 实际加载的 video-shotcraft 声明能力制作主片中的代表镜头，以本产品真实素材替换演示素材；镜头来源、适配和未支持范围可追溯。不能仅在片中提及该 Skill 来代替加载验收。
- 保存其中方法为个人 Skill，再换另一产品的内容调用，证明可复用；独立文字/图形仍可改，Generator 可回到来源修改并重新生产，作为普通素材引用成片与继续编辑原作品清楚区分。
- 影片以讲清产品价值和真实使用过程为目标，按叙事需要展示审片或 Scrub，不把所有功能演示强塞进主片。内容检查与 D4 修订能力仍分别按阶段验收，不由是否出镜推定通过。
- 完整动态观看并试听，核对画面/声音、节奏、局部修改保留范围与版本/交付事实；不以静帧、测试计数或一条漂亮成片替代四层能力证据。不能靠片外手改专用 renderer 或开发者离线拼片冒充产品完成。

这是 ABCD 的综合创作验收，不取代各阶段功能、D1/D2 发布门及 D3/D4 独立出口，也不扩大首个限定能力发布的前置范围。尚未完成的阶段仍分别登记；同类作品的基础可组合，不等于自动达到参考片的全部创意与制作质量。

## 6. 阶段 A 开工顺序

1. 在 NAMING/MODULE_ARCHITECTURE 登记 Composition/CompositionVersion、editing 模块、compositions/composition_versions/source_snapshots 与 video-spec；核对当前引用权限、Output.work_id/发布、删除级联与执行互斥接缝。
2. 冻结最小 schemas/timing：身份、三时间域、半开范围、量化与同轨/动画冲突规则；删除保留和未定数值按 §8 明确后再落相应实现。
3. 写 `apply_composition_edits`，先做事务原子性、跨 Chat 并发、请求幂等和 owner 校验，不先接 LLM。
4. 用最小内容与固定素材绑定打通 video-spec → render worker → probe → Output 血缘；不等所有对象/模板类写齐。
5. 扩 SourceSnapshot、Animation/TextPart、字体与 PreviewAdapter，手工构造官网片/MG 对照 fixtures。
6. 补完整素材权限、快照 refresh、split/trim/音频关联、失败恢复、两阶段 digest 与架构门。
7. A 最小出口后转 B 的真实 Chat 闭环；完整视听人工验收在 B 集中做，替代 renderer 归 D2，不继续扩充独立样片与检查脚本。未授权/未接费用机制的内部渲染入口仍不得暴露。

## 7. 不做清单

- 不做旧业务数据迁移、旧 FilmStoryboard 兼容读或全库回填。
- 不做第二执行引擎、Scene/Clip 执行图节点或 Canvas 版本库。
- 不做自由 NLE、任意关键帧 UI、转场画廊或每字符独立编辑器；最终 video-spec 不开放任意 CSS，受控程序内部采用何种视觉技术按 §2.5.1 选择，不混淆两个边界。
- 不执行导入的第三方 Skill 脚本，不做 Skill 市场、多 Skill 自由叠加或隐藏 recipe 执行参数；B-IV 显式受控的程序画面生产不等于授权执行外部任意脚本。
- 不做 production-time 缺版重设计、LLM 转录 canonical 分镜或视觉修改后保留失实描述。
- 不在 A–C 迁移/删除 Clip，不提前实施完整 Scrub；不建设“复制确切作品”或通用分支合并功能。

## 8. 施工评估与开工前置

**判断：主干可施工，采用 A 内纵向切片 + B 开发期直接替换与产品闭环 + D 显式删除清理和独立发布门。**不重写 Chat/Run 内核，不先建设完整 NLE、全局素材库页面或通用模板语言。UI 可并行施工，既有 Chat 布局也是必验路径；Chat 旅程、正文/工具/产物集成和真实阶段回放纳入 B，不归后续美化。首批成功标准是官网片、文字 MG 与混合实拍内容共享同一内容内核、可精确修订并可靠交付，不以目录/类/名词齐备为完成。

| 必须明确的接缝 | 截止门 | 交付物与失败处理 |
|---|---|---|
| 全局 owner/引用权限、Chat 删除与快照保留、Output.work_id 与发布/归档的对应 | A schema 冻结前 | 查当前代码/约束后冻结最小字段与删除规则；记录不一致，不能假设这些全局能力已实现 |
| 时间量化、Transition handles、split/trim 关键帧与音频关联、字体/文本求值 | A 代表样片前 | 纯函数合同 + 跨语言/预览渲染 fixtures；首版不支持即明确拒绝 |
| 内容摘要、执行输入摘要、准备产物 manifest、请求幂等与恢复 | A 出口 / B Start 接入前 | 模拟超时/重试/并发，证明无重复落版、无执行漂移；实际收费在 B 验证 |
| Chat 正文/活动/产物关联、实际阶段与 attempt 回放 | A 最小 DTO fixtures / B 过程接入前 | 冻结关联与事件最小形状，核对真实阶段发射点；B 用关闭/缓存/失败/重连旅程验证，不用组件演示进度冒充执行事实 |
| TTS 语速上下界、尝试次数、超长/可懂度判定与成本上限 | B 合成接入前 | 使用当前合成能力确定有界制作政策；超界回到修订，不偷改切点 |
| Generator 来源/参数、预览身份、生产 manifest 与受控运行权限 | B-IV drawing-v1 已按真实旅程验收；B-V 扩模型消费者时复核 | 首个 schema 与资源/尝试/费用边界已冻结；内容不回写，成功结果可恢复，重试不重新创作；不另建生产链 |
| 替代 Renderer 的能力与成本、Remotion 商业方案 | D2 生产前 | 实测能力与成本差异并作明确选择；不以“已隔离 adapter”冒充已替换 |

**依赖顺序**：A → B-I → B-II → B-III；B-III 后优先按代表需求推进 B-IV/B-V，B-VI 保留独立实施出口。C 在稳定且已声明的内容能力上复用创作方法，不阻塞首批发布；遇未支持的程序/生成能力必须列缺口。D2 可并行研究，生产前通过；所声明 B 能力验收 + D2 → D1。B-III 后可安排 D4 首版，不依赖 C 或全部 B-IV～VI；程序/生成媒体仅暴露实际支持参数。D3 后置且不阻塞 B-III。任何限定发布均不把完整 B 或全部 ABCD 标为完成。

## 9. 新会话接手入口

当前批次以 **PROGRESS §0** 为准，授权范围以本次用户指令为准；先读本文 §2.0 区分已提交基线、工作树成果、真实验收与保留欠账，不按旧会话提示词重做已完成主链，也不把未试听、未运行或未提交写成通过/已发布。

阅读顺序：CLAUDE.md → PROGRESS §0 → VIDEO_PROJECT §0 → 本文 §1.3/§2.0/§2.4/§2.5 及命中阶段 → VIDEO_PROJECT 对应章节。Generator 施工必读 §4.3.2/§8.1.1/§11/§12；按实际修改补读 Chat/Rendering/Billing 和适用 AGENTS.md，不通读整个 docs。代码先定位 editing、tools/video、Chat tools、video-spec 和 renderer 的实际接缝。

明确本批最小可复用能力和代表旅程后实施。按表达/执行/创作/编辑四层报告；受控视觉程序是内容生产，业务图拓扑仍由代码裁决。所有内容修订经 apply_composition_edits，图变更经 apply_wiring_ops，Run 只经 create_run；不按每个 Object 建执行节点，不增加平行执行引擎或通用插件层。

沿用不可变版本、固定执行身份、既有授权/计费/交付/fencing。沿真实主流程补少量必要守卫，不新增独立样片/检查框架；完成后运行适用检查，分别记录实证与未验收项。保留工作树，禁止 reset/stash/擅自部署；提交、重启及迁移按本次授权和环境约束执行。付费前核对有效授权范围、累计预算与已消费，§2.0 的历史额度不自动重置或扩大；授权已覆盖就继续，缺失只询问必要付费范围，并推进不依赖付费的工作。
