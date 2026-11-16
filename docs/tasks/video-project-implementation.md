# Video Project A–C 基线施工与验收证据

> Status: 基线证据与遗留验收（2026-11-04）。目标架构唯一事实源 = [VIDEO_PROJECT](../VIDEO_PROJECT.md)，所有阶段先读其 §0 创作方针；本文只维护 A/B/C 基线及 B 内增量批次的实现证据。A 最小基座与 B-I～VI、C 的已声明出口和保留欠账见对应章节；完整 B/C 未封板。全部剩余施工与验收统一归 [宣传视频核心 Skill、统一 Skill 包与视频后续施工](skill-package-promo-video.md)，当前批次与优先级只归 [PROGRESS §0](../PROGRESS.md)。
>
> **数据边界：不迁移既有业务数据。**新表、新列、索引和约束仍需 Alembic；旧 Film 数据适配器、旧板 digest 迁移和全库回填均不建设。生产环境无实际用户；用户已授权为本轮重构破坏旧业务数据，必要时可清理/reset 本应用开发与生产数据，无需为同一范围重复确认。执行前核对目标实例、数据范围和 dry-run，不扩大到其他项目或基础设施；本次文档更新不执行清库。

## 0. 开工规则与总边界

1. 新链为 Project/Chat → Composition → CompositionVersion；同一 Chat 可分别持续修订多部影片，全局 @ 引用不受来源 Chat 限制。不引入 Work / WorkDocument、Sequence 或独立 Timeline 作品根。
2. A/B 建立服务官网片、MG与混合内容视频的共同底座；B 的程序化/生成媒体按 §2.5 分批交付，不与当前官网片修复混做。C 提供个人创作方法复用。旧 Film 用作行为/画面对照，旧 Clip 产品迁移/删除仍后置。
3. 开发期不承担旧 Film API、旧数据或旧内部结构的兼容承诺。A 保留旧链作样片对照；B 集中替换注册表→prompt→工具菜单→Start/Run→Output 的 Film 专用接缝，只保留一个有效设计/制作家族，不长期双写、双读或保留自动 fallback。临时 feature flag 仅服务开发隔离，后续清理统一归新合同 P8。
4. Graph/Run/worker/render ownership 复用，不建第二执行引擎。Scene、Track、Clip、TextPart 不成为执行图节点。
5. `pending_brief` 只保留通用计划/问题/确认状态；CompositionVersion 是唯一作品内容真相。
6. `apply_composition_edits` 与 `apply_wiring_ops` 分别守作品内容和执行图，路由不得绕写。
7. 不擅自调用付费模型、TTS、采集或渲染；真实验证按用户授权和预算执行。未运行的检查必须写“未运行”。
8. 保留工作区与并行成果，不用 reset/checkout/stash 制造基线；每批在当前工作树重新核对代码与验证，不转信其他会话的基线绿。
9. 新模块、表、队列和名词在首批代码同批登记 `MODULE_ARCHITECTURE.md`、`NAMING.md`、`docs/README.md`；新 prompt 走当前写作法，并由相关真实用户旅程验收。
10. 旧 Film 固定骨架、pending信封、legacy指纹/schema 专属测试不再是兼容目标；有效创作/视听要求归 VIDEO_PROJECT §15，旧结构套件不要求重绿。新覆盖随 A/B 实现建立，未建不算通过。测试只保留用户主流程旅程与承重架构守卫；时间量化、唯一写口、版本并发、模板展开、spec/renderer 隔离属于承重纯函数覆盖。

### 0.1 现有 UI 可用与并行 UI 施工

- A 是内部基座，完成不等于用户已能从 Chat 使用；B 完成接入和验收后，新链必须能在现有 Chat 交互与页面布局下使用。不以 UI 改版、完整素材库页面或 Scrub 组件为前置。
- “UI 不变”指使用方式与视觉布局可保持，不承诺前端零代码变动。分镜 payload、版本引用、@ 解算、SSE 回放、Start、产物卡/播放/下载须做必要协议接线；先复用现有组件，预览可先使用现有播放器或服务端预览。
- UI 可并行开发视觉与交互；双方先固定最小 DTO/事件契约：Composition/版本引用、storyboard_payload、Output 与引用解算结果、编辑提交/冲突形状。UI 使用同一契约的 fixtures/mock，不依赖 pending_brief 中旧 Film JSON 或 Remotion 私有组件。
- B 同批完成 Chat 旅程、正文/工具/产物集成与真实制作过程；行为合同见 VIDEO_PROJECT §10.1。全面视觉改版可独立验收，默认布局下也要通过完整旅程，不能以“UI 后置”推迟过程协议与回放。
- Chat 一体化呈现采用 VIDEO_PROJECT §10.2 与 CHAT_ARCHITECTURE §8.10 的 TurnBlock/RunBlock；四阶段目录拆分、渐进揭示与回放改造归 [专项施工合同](chat-turn-block-implementation.md)。A 冻结最小关联/事件 fixtures，B 接真实运行；本文件不另建第二套 Chat 呈现或目录合同。

### 0.2 分支、环境与合并策略

- 本轮在用户指定的 `feat/mg` 分支内完成破坏性更新，生产无实际用户，不要求旧 Film API、旧数据或过渡期持续可用；不因此豁免新链正确性与生产验收。
- 建分支前核对当前 HEAD、工作区和与 main 的差异；保留本轮必要的未提交成果和并行 UI 工作，不用 reset/checkout/stash 清场，也不把无关改动批量提交。基础分支取包含必要现有成果的状态，不盲目从 main 起步丢掉已完成工作。
- 基线按 A/B/C 的依赖留证；后续合并与生产切换只按新合同 P0→P10 推进。合并前同步 main、处理冲突并对最终候选重验；不得用限定能力发布把完整 B/C 或其他未验收范围标为完成。
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
- 替代 Renderer 的商业许可、能力/成本与 PreviewAdapter 生产门归新合同 P7，不阻塞 A/B 开发；adapter 隔离不等于替换完成。

A 内按三次可验证交付推进，不先造齐全量框架：

1. **最小纵向闭环**：冻结作品身份、范围/量化、版本写口；用最小 Text/Image + 固定音频版本打通 worker → MP4 → probe，证明权限、版本、Output 血缘与实际渲染成立。
2. **代表性表达**：扩到 Web/Video、逐字动画、多段 scale/Bezier、字幕和音轨关联，手工重建一支官网片与一支 MG；先验证内容表达，不接 LLM。
3. **最小基座收口**：内容写口、关联操作、资源边界和必要回归成立后进入 B；不为清空全部未来能力清单阻塞产品闭环。B 在具体消费者接入前补其依赖，生产前仍须通过新合同的可靠性、Renderer 与发布门。

**A 当前状态——最小内容基座已收口，完整能力未齐**：

- 已实现 Composition/不可变版本、owner/来源 Chat 校验、行锁/CAS、完整请求幂等与并发重放；Output 钉版、video-spec 与 Remotion adapter 已接既有渲染基础设施。已有批 1 worker→上传→probe 实测；内部 run-less 接缝不开放为产品制作入口。
- 当前支持 Text/Image/Web 静帧/Video/Audio、固定字体 digest、TextPart line/word/grapheme、整体/分段动画、scale/Bezier。A 的 base/edited 样片位于 `artifacts/video-project-a2/{website,mg}/`，B-III 真实混合片位于 `artifacts/video-project-b/mixed/`，均 Git 忽略；样片与真实 Chat 证据分开，不替代人工审美或听感验收。
- `move_scene` 原子平移所属 Clips，源窗/Clip-local 动画与全局音乐不动；`remove_scene` 删除所属内容并清理旁白引用。带内容 Scene 的范围重设不能静默只改标记：移动、trim、delete 与 time_map 统一走通用时间内核。复制 Scene、通用媒体 rate 与自由 NLE 仍未实现；固定媒体 split/trim、首个 crossfade 和节拍吸附已有下述限定消费者，不宣称完整 NLE CRUD。
- SourceSnapshot 登记/绑定与字体描述归 editing；资源读取、冻结上传及字体发布归 `tools/video/preparation.py`，editing 不依赖 providers。快照已接入 Chat 网页采集、视频/音频 Asset 与视频 Output 素材冻结；redraft 复用已绑定快照，只有显式刷新才更换绑定。
- 收口验证：受影响 editing/DB/animation/spec/样片契约测试 **44 项通过**；只新增 Scene 移动/删除两项承重用例，未扩写验收脚本。未复跑全量 API/web/render，未重渲染或人工播放验收样片；已有样片与批 1 渲染证据不升级为本次新证据。
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
| 替代 renderer spike / 商业许可 / 能力矩阵 | 新合同 P7，生产前必须收口 |

## 2. 阶段 B——launch-film Skill 化、Chat 分镜与 CRUD 制作闭环

### 2.0 B 当前状态（2026-10-29）

上下半批、B-III 混合合成、B-IV 两个纵向出口与 B-V 首个模型图片消费者均已落码于 `feat/mg`，具体提交状态以 git 为准；**真实 MG、官网片、混合实拍、原生图形、受控程序画面及 MiniMax image-01 单图混合短片的制作/交付与修订闭环均已按各自出口通过，B 主链收口，仍未封板**（欠账见下）。不要按旧提示词重做上半批、生产链或已通过的 B-IV 出口；B-V 只声明当前单供应商单图用例，不扩张为全模型媒体能力。

- **已有实现**：`editing/service.py`、`chat/video_turn_seats.py` 共用 plan/propose，canonical 版本引用、真实消息 id、完整呈现 ACK、首稿批准守卫、明确后续修订并制作的延迟启动与现有确认/费用设置接线。补齐版本上下文、幕数/时长/背景约束、背景修订、全局 @asset/@output owner 读面。新增 `tools/video/params.py`、`tools/video/production/`，produce_video 经既有图写口/create_run 固定版本、估价/hold、manifest、渲染/上传/probe、成功 capture、交付；成功才归档同作品旧完成产物。
- **当前呈现改动（未验收）**：用户可见分镜改为 LLM 基于完整保存版撰写的 Markdown 创作概要，标题/列表/表格自由组织，重点讲整体方向与大致画面设计；原 CompositionVersion、`storyboard_payload`、消息 block 和 digest 结构不变，技术 DTO 不再平铺。首稿/修订提示词、工具描述与 observation 已同步；ACK 随正文完成打字释放且必要真实 Generator 预览就绪后发送，首稿批准、制作、Run 和费用链不变。尚未运行 TypeScript、当前核心 API、真实 Chat 或刷新/延迟启动验收，既有卡片证据不覆盖本次呈现改动。
- **B-III 已有实现**：VideoObject 与真实视频 SourceSnapshot 接入 validator、video-spec、Remotion `OffthreadVideo` 和 render probe；画面与原声共享同一 Clip 源窗，支持 layout/fit/transform/opacity/gain/muted。`instantiate_mixed` 生成同源全屏静音动态背景、中央原比例录像、独立标题/定时字幕与既有音乐床；`update_video` 通过唯一写口局部改布局、源窗与原声，目标源窗修改保持当前输出时长。视频 Asset 与 Output 均可冻结为新素材，继续修改 Output 原作品仍走版本修订。
- **B-IV 已有实现**：ShapeObject 支持 rect/ellipse/path 几何、绘制与外部表现，MG Director 可按需创作 rect/ellipse，多个同幕图元分轨避免重叠；`update_shape`/`update_animation` 精确局部修订。GeneratorObject 固定 `producer/code/parameters/output` 与 program_digest；`draw-2d` 由权限受限 Node 进程执行 Agent 的 `render(ctx)`，只接受有界 JSON 绘图命令，经 Pillow/PyAV 生成固定 MP4/PNG。设计、修订和生产共享 exact-digest 媒体准备；预览绑定版本来源，执行 manifest 固定媒体血缘，最终 video-spec 只含普通 muted video，不包含程序。
- **B-V 已有实现**：新增单一 `image-generation` 消费者，保存可审阅的 MiniMax `image-01` 16:9 单图请求及独立原生标题；设计/修订只经既有写口保存来源，不生成、不计图片费。只有带授权 `execution_id` 的 produce Run 才调用供应商；共享 `generate_image` 每次调用只发一次非幂等 POST，image-generation 在调用前持久化 `submitted` 标记，传输/响应解析失败或恢复仅见该标记时按“结果未确认”失败闭，不自动重放、不虚记确定用量。真实图片返回后按实际数量计量并固定为不可变媒体；固定执行 manifest 记录完整请求、Run 身份与实际媒体 digest，Composition/Object 复用指针指向该作品最新固定结果。普通恢复与原生内容修订复用媒体；只有 `produce_video.params.regenerate_media=true` 的新 Run 明确重生成，使用 Run 独立执行命名空间，同 Run 重试仍复用。报价只计缺失图片；最终 video-spec 只含无源窗的普通静态 image，不泄漏 prompt/provider/model，也不把生成像素冒充原生可编辑元素。
- **B-VI 首个旁白消费者**：MG `design_video` 接收精确 `narration` 与显式开关，实例化 SpeechClip、派生字幕和既有音乐床；SpeechObject 保存原文/voice/language/gain，制作不回写版本。MiniMax `speech-2.6-hd` 非流式 T2A 返回真实音频与句级时间，授权 Run 以 1.0–1.35×、至多两次、`fit_margin=1.08` 和钉入 step 的 `max_tts_characters` 执行；解码实测超长即冲突，不删词、改写、截断或移动切点。共享 speed-1.0 原件按 `(user_id, content_hash)` 复用，适配件与 manifest 归 Run；未知提交失败闭，已固定音频可只恢复字幕下载。`update_speech` 只刷新 derived 字幕，手改字幕转 independent，`sync_captions` 才显式重联。编译只产普通 audio 与按真实 cue 定时的 TextClip，renderer 不接触 Speech 或模型。报价按剩余付费合成与实际 MiniMax 计费字符，produce step capture TTS，render mirror 只计成片秒，避免双计。
- **环境**：默认闸仍 false，本机忽略的 `.env` 已开 `VIDEO_PROJECT_ENABLED=true`；DB head `a6e9c2d4f801`。API8000、web3000、render3001；`scripts/dev.sh` 为四个长期服务提供退出自动重启与旧 supervisor 清理，但这不等于代码热加载，改执行代码后仍须在无活跃任务时重启对应进程。当前日志 `/tmp/rep-api.log`、`/tmp/rep-worker.log`、`/tmp/rep-render.log`。
- **真实成功（同 Chat）**：Chat `2cce4c18`，Composition `05c66c6f`；Run `e32ed9f2` COMPLETED，Output `94ccf1d8`（v3）。
- **真实成功（跨 Chat，2026-10-27 收尾通过）**：Chat `1b89291a` @output 引用成片，仅改第三幕为 Keep editing 并直接制作；保存 v4 `0d6df014`，浏览器回放卡片完整呈现 → ACK → 延迟启动 Run `f6b64fb6`（version_ref 钉 v4）→ 渲染/上传/probe → Output `36383c3f` COMPLETED，hold→release→capture 各一次（-12 积分），旧片在新片成功后才归档；浏览器真实播放，5.2s 帧确认第三幕为 Keep editing、其余不变（"in focus" 是 v2 的用户修订，非串改）。成片存 `artifacts/video-project-b/`（已 git 忽略）。
- **真实成功（B-III，2026-10-28）**：项目 `7da1c453` / Composition `1978090d` 经真实 Chat 从 15 秒录像设计 5 秒混合片；v1 Run `0f50ec33` → Output `36f15832`，随后只改第二句字幕、中央布局缩至 80%、关闭中央原声保留音乐、中央源窗改为 1–6 秒，依次保存同一 Composition 的 v2–v5。系统 change_set 证明每次仅目标 Clip/源窗变化；v5 完整呈现与 ACK 后 Run `57310339` 钉 v5 digest → Output `417ac081` COMPLETED，旧 v1 仅在新片成功后归档，两次 Run 均 hold→release→capture 各一次。浏览器真实播放并刷新回放，Run 数保持 2；1920×1080/150 帧成片与 2.5 秒帧确认动态背景、缩小的中央实拍、标题及修订字幕同时存在。两层 VideoObject 均 muted 时输出仍有 48kHz 双声道非静音音频，证明音乐床保留；未把这等同于亲耳听感验收。媒体与浏览器证据在 `artifacts/video-project-b/mixed/`。
- **真实成功（B-V，2026-10-28）**：项目 `e6f80236` / Chat `97fa8002` / Composition `ce1795ff` 经真实 Chat 首稿审阅后生成并交付 4 秒 16:9 混合片。v1 `cf1c9c71` 的 Run `a7d1b840` 真实生成首图；仅改独立原生标题得到 v2 `bd4f9951`，Run `c6569a65` 复用首图且无图片费用；同一 v2 明确重生成由新 Run `98639a0f` 产生不同图片与第二次 `images=1`；随后普通 Run `bce7f2c6` 复用最新图且无图片费用。四个 Output 均 COMPLETED，成片均为 1920×1080/120 帧；v1→v2 系统 change_set 仅含标题 Clip 的 object 变化。持久化消息/API 回放保留两张分镜引用，ACK 重放 `accepted:false` 且 Run 数保持 4。两张真实 JPEG 均为 1280×720，供应商实际费用合计 USD0.007；帧确认无字生成背景与独立原生标题同时存在。原始信封、Run/Output/账本、manifest 与帧证据在 `artifacts/video-project-b/b-v/`（已 git 忽略）。
- **真实成功（B-VI 首个两幕旁白闭环，2026-10-28）**：项目 `9d028c39` / Composition `d5e2e575` 经真实 Chat 设计 8 秒两幕 MG，v1 `540f6c97` 完整呈现 ACK 后授权制作。首 Run `136ecd62` 已固定第一幕真实音频，因 MiniMax 实际句级时间是浮点毫秒、初版解析只收整数而失败；解析修复后 Run `b429b0e4` 只恢复该音频字幕下载并合成第二幕，Output `ad02d47e` COMPLETED，没有重复提交第一幕 TTS。随后仅手改第一幕字幕得到 v2、零 Run；只改第二幕旁白得到 v3 `aeecf06a`，Run `705d21a2` → Output `93a28207`，第一幕音频 digest 不变、`cache_hit=true`、本 Run TTS=0，人工字幕「先看挑战。」保留，派生字幕按真实时间显示「答案在这里。」。v4 长旁白 Run `473dbc9e` 实测 9.892s 对固定 4.000s、所需 2.522× 超过 1.35×，以专门冲突失败，无新 Output，文字与切点不变，hold 35 全 release，前一交付仍可播放。两次成功交付均在真实浏览器播放；硬刷新保留 v4 分镜、两版成片和 4 个 Run，不重启制作。帧证据确认第 4 秒切点与两版字幕，音轨解码确认非静音旁白段与持续音乐床；未亲耳试听，不把这算作听感验收。首个成功 Run 曾暴露 produce 与 render mirror 双计 TTS，镜像已修为只计 film_seconds，后续修订 Run 实扣为 produce `tts_chars=11` + render `film_seconds=8`，历史开发账本不改写。原始响应、版本、Run/Output/manifest/账本、浏览器与帧证据在 `artifacts/video-project-b/b-vi-narration/`（Git 忽略）。
- **本批修复**：① 回放洞——pending/已答 task_book 行的 video_storyboard blocks 不进历史流，刷新后卡片不再呈现、ACK 永不再发、授权延迟启动永久卡死；`historyReplay.ts` 两条分支现携带 blocks 回放（已答 echo 行与 pending echo 行），旧无 blocks 的 plan dock 行为不变。② `_video_project.j2` REVISION 律补状态真言：改版卡片呈现完成前制作未开始，禁称"渲染已在后台进行"。③ 三个守卫测试随门控世界更新（工具桶 XOR 断言、plan stub 补 user_id、trigger 工具预算 18→21 注明出处）。
- **检查（当前工作树）**：B-UI 收尾后全量 API 1365 项通过，web 23 文件 / 260 项及 web/render TypeScript、API compileall 与 git diff --check 通过；完整真实旅程未跑。真实旅程证据归 artifacts/video-project-b/b-close/，不以静帧或参数检查替代独立听感。
- **真实成功（官网片，同 Chat 全闭环，2026-10-27 独立复验）**：项目 `bd2b2f2e` / Chat `9ee217bc` / Composition `79035790`。首稿 v1 `e09d8509` 完整呈现 → ACK `run_id=None`（呈现不动工）→ 用户批准 → Run 钉 v1 digest；首 Run `98a70678` FAILED（render POST 被系统代理截断，hold 176 全额 release），重试 `b943bf22` COMPLETED（capture 一次）。局部修订「hero 副标题补空格」→ v2 `dc75f1ba`（settings/sources 逐字节相同，timeline 仅 `clp_hero_text1` 文本变，零重新采集、零重新设计费），普通修订零 Run；「改完直接做」→ Run `3f3262f5` 钉 v2 → Output `31e444aa`。同版再产 → Run `59762ae8` → Output `558c6547`（终片，88s/1920×1080）。每次 Run hold→release→capture 恰各一次；ACK 重放 `accepted: false` 不产生新 Run；渲染中 Output `files={}` 不冒充完成。帧级核验：屏幕文字取页面原文且字体正常、hero 文案空格已复、章节字幕正确、音乐床全程约 -20dB 且 88s 处淡出至静音、无旁白（内容模型无语音对象，结构性保证）。
- **本批修复（官网片链，均有真实证据）**：① `SKILL.md` 陈旧槽位词汇（法条座位冲突，首设计回合 29 个 schema 错误的根因）全文重写为 v1.3.0；② `CiteLine._fold` 从未注册为 validator → 接上 `model_validator` 并扩拼写（非法引用仍 raise，纯函数实测）；③ 字幕 `{text,citation}`/片段列表 fold 成纯文本（不丢词不乱序，不可解析结构 raise 不静默置空，纯函数实测）；④ 音乐床：`video-template.json` 增 `trk_music` + `MusicBed` 平铺 + gain 关键帧淡入淡出 + `resolve_bed_track` 三态（off 终态无人 reopen，实测 `off→None` 且不建空音轨）+ `snapshot_music_track` 内容寻址冻结；⑤ `storage.py` S3 client 显式 `proxies={}`（urllib3 隐式走 macOS 系统代理吞大 PUT 响应，boto3 全项目仅此一座）；⑥ `rendering.py` render POST `trust_env=False`（长渲染请求被代理中途切断）；⑦ 字体缺陷：`fonts.py`/`schema.ts`/`Video.tsx` 给 emoji 字体资源加 `unicode_range`（Noto Emoji 含拉丁字形且 family 排序在前，整行拉丁渲染成 emoji 面、词距崩塌；修复后帧实测正常）；⑧ `capture.py` 研究清单把 `<br>` 视为词边界（`actions.<br>Not` 空格被吞，真实页面 HTML 实测修复）；⑨ `grounding.py`：focus 取元素**可见部分**（视口裁剪截图的元素坐标可越界 >1）+ camera 平移钳制在 cover 余量内（聚焦越界元素会把画面推出画布露黑；真实 view-1 库存上纯函数实测钳到界内）。
- **本次代码审查与必要修复（2026-10-28）**：相机原钳制把 cover 图片的额外像素误作实际 Img 盒子的可移动余量，且忽略起点/末段漂移；改为按 renderer 的画布大小盒子与各关键点实际 scale 限位，并由模板透传起始 scale。CiteLine canonical `line` 改 strict integer，拒绝此前会被折叠成1的 bool/整值float；字幕空/空白片段列表不再静默变成 null，而交字段校验拒绝。增加12个现有套件参数用例；API1322、web257、web/render tsc、video-spec9 通过。用现有本地入口实际渲染4秒/120帧边缘聚焦白底短片，全部边缘RGB=255；这是针对裁切盒边界的真实 renderer 验证，不冒充原官网片重渲染或音乐试听。样片位于 `artifacts/video-project-b/camera-review/camera-coverage.mp4`，未调用付费模型。
- **未验收欠账**：旧官网样片仍未重渲染；新 AgentVeil 首章真实取景已由本次 v2/v3 实帧核验；官网片与 B-III 音乐均未亲耳试听（结构与电平核验，听感不冒充验收）；音乐多瓦片循环接缝未真实渲染（现有素材单瓦片即够长）；`run_failed` 触发回合沉默一次（FAILURE FACTS 装配正确但模型读满预算未发声，同机制其余回合正常，登记为 LLM 漫游方差未修）；B-III 局部换源窗只接受与当前输出窗等长的片段，不做自由改时长，1× 与 B-VI 有界旁白适配不冒充通用变速；B-VII 通用时间映射已落码但未验收，通用媒体 rate 与通用转场仍未实现，首个固定媒体 crossfade 已补齐；B-III 首稿曾出现正文宣称背景推移但保存版无该动画、以及“逐项打开”等过度表述，canonical 内容未受影响，正文质量仍需按真实 payload 归因处理；B-V 一次“修订并制作”回合在修订版已保存后反复尝试未呈现版本的生产，并把 `regenerate_media` 错放到顶层，最终耗尽工具预算；随后经真实 Chat 重新呈现 v2、ACK 与制作完成交付，但该交互稳定性仍留集中验收，不能以最终成功抹除。B-VI 另一次同回合「长旁白修订并制作」先尝试未呈现版本生产，保存 v4 后仍未重新呈现而耗尽 12 次工具预算；随后通过独立呈现/ACK/制作回合取得真实冲突，该多轮稳定性同样未关闭。B-VI 未做亲耳试听；真实加速第二 pass 已由本次收尾样片补齐；完整真实旅程和音乐循环接缝继续开放。B-V 刷新证据为持久化消息/API 回放，不是新的浏览器硬刷新播放会话；真实帧与 PyAV 结构核验不冒充独立完整视听验收；完整 redraft 的 `numbers_plate` 阻断已解除且 v5 已保存/呈现，但保存后主 Chat 仍发生无关修订/重设计漫游并被中止，Director/多轮稳定性未关闭；§2.4 其余未勾选条目；多作品交付与 B-UI 移动端/双主题/reduced-motion 本次已补齐。
- **定向可靠性结果**：`_execute_program` 改为读取期累计 stdout，超限立即终止；正常完成、超时、异常与取消统一 kill/reap 并回收读取任务。定向进程探针实测普通程序完成 2 帧，超限程序 0.032 秒内停止并回收，超时/取消/运行错误均回收子进程且保留对应诊断；未重做已接受的 B-IV 样片。B-V 以隔离存储的代码级故障注入验证：普通重试/原生修订复用首图，明确重生成获得新执行身份，同 Run 恢复复用本 Run 结果，后续普通生产读取最新图，其他 Composition 不串用；manifest 已固定、复用指针写入失败后的恢复未再次调用供应商或重复计量。这些是代码级故障证据，不冒充额外真实供应商生成。
- **B-V 供应商重试修复（已定向验收）**：官方同步 image-01 参考仅提供响应 trace `id`，未文档化幂等键、客户端请求 ID 或历史结果查询，不能以 seed 或本地台账冒充供应商防重。共享 `generate_image` 已移除通用三次重试，并保持 quote-card/cover 调用签名与正常成功返回不变；`ProduceVideo.retries=0`，传输错误不包装成 `TransientNodeError`。image-v1 在 POST 前写 submitted，故 worker 孤儿节点 requeue 或同执行恢复也只能读到“结果未确认”，不会再次调用供应商；新明确重生成走新 Run 键。无网络替身实测首次 ReadTimeout 后 `provider_posts=1`、`usage=[]`，同执行再次恢复仍 `provider_posts=1` 并返回专门的中英文恢复信息；正常生成固定媒体并记录 `images=1`，缓存不再调用，明确重生成与后续最新复用保持原语义。保证范围是同一执行键的顺序恢复不盲重放；供应商实际是否执行/收费仍可能未知，须对账，不承诺恰好一次。submitted 也可能是请求尚未到达供应商的保守标记，此时仍需用户明确新生产，而非系统自动试探。
- **B-VI 字幕量化修复（当前工作树）**：`editing/video_spec.py:_compile_derived_caption` 不再先把浮点毫秒截成整数；毫秒以十进制有理数保留到最终起点 floor / 终点 ceil 帧量化，继续沿用既有固定窗、相邻 cue 顺序与不重叠规则。无网络回归覆盖 30fps 的 33.9–1000.1ms 从修复前 `[0,30)` 更正为 `[1,31)`，并覆盖相邻 cue 与整帧终点；旁白、video-spec、修订与 probe 四个定向套件共 63 项通过，未重新调用 TTS 或重做既有样片。既有真实旁白交付证据保留，字幕同步与完整视听验收不因此封板。
- **真实成功（增强网页采集首个静态镜头闭环，2026-10-29）**：项目 `432c0cd3` / Composition `2eb8f349` 经正常 Chat 使用真实 `https://agentveil.dev/`。同一 Asset `51a61dad` 保存渲染正文 80 行（`body_truncated=true`，长页补读未实现）、2× 整页图、6 张 2× 视口图与 12 张目标元素图；SourceSnapshot `993bd3fc` 冻结上述文本/图片及 CSS→像素映射，Director 实收 6 张视口图 + 4 张元素图（`media_count=10`），不是只存字段。首稿 v1 完整呈现 ACK 零 Run；`focus_web` 以 `clp_chapter_1_walk_web + s1e8` 生成 v2 `8ffcd898`，唯一内容 Clip 变更为首章相机，服务端按元素中心/可见部分重算关键帧。Run `1f606707` 钉 v2 → Output `28b03b27` COMPLETED。随后只把第一章标题改为 “Review the next move” 得 v3 `d729517a`，仅 `clp_chapter_1_divider_text1` 变化，首章相机及所有版本 SourceSnapshot 绑定不变；Run `f798e508` 钉 v3 → Output `260e3883` COMPLETED。两次 Run 均 completed、各净计 176 渲染积分，无重新采集、图片或 TTS 调用。20 秒实帧确认真实标题 “Don’t just stop the agent. Give it the next move.” 清晰占据首章主体，v3 15.5 秒实帧确认修订标题；两版 20 秒帧逐通道平均像素差仅 0.42–0.63/255。真实浏览器播放 v3，硬刷新保留两版视频与 3 个分镜版本，Run 数保持 2。原始响应、Asset/快照/版本/Run/Output/账本、浏览器和帧证据在 `artifacts/video-project-b/web-capture/`（Git 忽略）。这只是首个静态镜头切片，不是完整采集能力或完整 B 封板。
- **真实成功（首个 exact-Output 内容审片闭环，2026-10-29）**：同一 AgentVeil 项目 / Composition 的已交付 v3 Output `260e3883` 经正常 Chat 审片，reviewer 直接解码其真实 MP4、保存 15 张内容寻址静帧及 `quality.content_review`；后续正常 Chat 默认复用该报告，未重复解码/调用 reviewer。报告在 48.067s 以 `clp_chapter_3_walk_web` / `obj_chapter_3_walk_web` 证明第三章主标题左侧被裁。自然语言局部修订保存 v4 `01207347`：settings/sources/全部 Clip id 不变，内容 Clip 仅该网页 Clip 的 animations 改变，另同步刷新该 Scene 的 `visual_description`；呈现 ACK 后 Run `fe665967` 钉 v4 → 新 Output `d930fbc1` COMPLETED，净计 176 渲染积分，无图片/TTS/重新采集。对新 Output 的正常 Chat 复核只抽 48.100s 这一真实帧（frame 1443），确认完整标题 “Keep sensitive data local. Share only bounded proof.” 及支持文案已在画面内可读，该点未见新取景问题，findings 为空；旧 Output 虽按现行规则归档，文件与确切版本/审片报告仍可读取。原始回合、版本/Run/Output/账本、消息/API 回放及复核帧在 `artifacts/video-project-b/content-review/`（Git 忽略）。这只修复一个静帧问题；原 caption band 遮挡不在本次修订范围，运动、转场、音乐、音画同步、其他时间点与完整内容质检均未通过。
- **短修与完整 redraft 复验**：新 SourceSnapshot manifest 根级冻结 `body_truncated`，Director 独立 `CAPTURE STATUS` 读取三态，旧快照 UNKNOWN；普通 `get_web_page` 未改。完整 redraft 已保存并呈现同一 Composition 的 v5 `514d6426`（base=v4，88.1s/15 scenes），SourceSnapshot 绑定不变，ACK 零 Run，未再出现 `numbers_plate` schema 拒绝。Director 对实际出现的固定弧分组/系统 proof 回声只做限定读容忍，未知字段仍拒绝；保存后仍发生无关修订/重设计漫游，故 Director/多轮稳定性不关闭。
- **审片报告复用已短修**：`tools/video/review.py:_reusable_report` 只在确切 Output id、检查要求与显式持久化的 `at_seconds` 采样范围全部一致且 `refresh=false` 时复用；新报告保存请求采样范围，缺该元数据的旧报告不猜测复盖新请求，单点复核与整片场景抽样不能互相替代，`refresh=true` 仍强制重新检查。相关纯测试覆盖相同请求复用、要求变化、旧元数据缺失与两种采样范围互斥。
- **B-UI 视觉与交互代表旅程已通过，声音待复验**：Docker/数据库已恢复。新真实 Chat `92486f3c` 完成 Morning/Night 两作品各 v1/v2 四交付，后有 Morning v3 及同 v3 再交付；浏览器硬刷新仍为六项，版本号依次 1/1/2/2/3/3。查看器打开时新交付将 3/5 更新为 3/6，当前仍为原 v2；关闭回到原消息位置与触发焦点。440×956 移动视口、浅/深主题、reduced-motion、键盘左右/Escape、竖屏 contain、真实文本、三页 carousel（Output 序号与页码独立）、真实 PNG 阅读/切换已实测。归档 AgentVeil v2/v3 的打开、播放、切换、25,505,600 字节 MP4 下载与精确引用，以及同版三个独立 Output 的既有证据保留。实测补修图片固有尺寸导致的移动端溢出、键盘导航及 reduced-motion；旧金句图虽已按生产步骤持久化但未写入旧 refs，读面按既有步骤归属补齐，无历史数据回写。内部/未完成行不进列表，确实缺失的历史引用仍为不可用。证据归 `artifacts/video-project-b/b-ui/` 与 `b-close/`；视觉与交互通过；用户已确认重新展示的视频有声音；完整视听与完整 B 仍另行验收。
- **预算与能力边界**：累计授权人民币60元，历史费用不重置。历史可核 USD.212835；本次 Chat USD0.982962、生产 LLM USD0.0224367、三次真实加速合成共273字符 USD0.0273、既有模型调用 484 条已返回供应商 usage 按现有价目 USD.8637083，本批已知合计 USD5.896407，累计 USD10.109242（按既有7.2约人民币72.79），已超授权。该批工具 loop 调用量超过估计且未及时限制累计费用，不能写成预算内；后续付费已停止，无运行中模型探针。历史中止回合最后一个在途请求及 gate 未返回用量仍待供应商对账，不视为零。明细与原始日志归 artifacts/video-project-b/b-close/。当前只声明既有 Text/Image/Web静帧/Video/Audio/Shape/Speech/drawing-v1/image-v1 消费者；其他模型、生成视频、通用转场、通用媒体 rate、完整NLE/交互式Preview 未实现；B-VII 通用时间映射已落码但未验证；本批限定 split/trim/crossfade/BeatGrid 证据见下文；后续切换与发布门归新合同。

- **B 收尾的实际修复（2026-10-29）**：同 Chat 两作品实测复现修订后生产反复拒绝、耗尽 12 次工具。根因是 pending 呈现可能指向另一作品，且修订读面未携带实际 previous_version_ref；现按实际 base 恢复对应历史呈现，保留首版审阅/ACK 和当前消息制作意图。修复后正常 @Morning v2 → v3「Hello morning」→ ACK → Run `3472df22` 成功交付。只证明该具体故障修复，不把其他 Director 漫游一并关闭。
- **B-VI 真实加速与校准**：缓存原音的报价曾使用上次实际字符数，下一次提交却要求保守字符上界，现统一按保守上界报价。原 2% 余量下两条真实适配分别为 8.278s/8.100s 与 9.741s/9.600s，诚实失败、均无 Output。依真实供应商时长波动将新 Run 的 fit_margin 校准为 1.08，速度上限仍 1.35、最多两次。项目 `0e53ac24` 新 Run `dff58884` → Output `d7e02165` COMPLETED：缓存原音 9.891719s，1.318896× 第二次合成实测 7.569719s，固定 8.1s/243 帧，原文/版本不变；本 Run 计 91 字符，未再计原音。失败尝试的真实供应商消费保留，不因开发积分退回而算作零费用。样片与 manifest 归 `artifacts/video-project-b/b-close/`。
- **声音入口反馈已解除，完整听感仍待验收**：用户实测 delivered-v1.mp4、delivered-v2.mp4、mixed-v5.mp4 均无声。文件检查均有 AAC 48kHz 双声道，解码 RMS 分别约 0.0658/0.0644/0.1097，未见左右相消；这些结构证据不推翻用户播放无声，也不等于听感通过。已原样提取 WAV 并重新展示原始视频，用户确认视频有声音；完整音乐接缝和音画同步不因此自动通过。

- **当前授权批次**：一次贯通 split/trim、首个全画幅固定媒体 crossfade、冻结音乐 BeatGrid 的 cut snap；新增全部供应商费用上限人民币10元，历史已知约人民币72.79元不重置。先无付费编码与本地渲染，再集中真实 Chat/制作验收；不运行额外模型探针，不因预算或首个消费者删除原需求。三个首个限定出口已通过下述真实 Chat 与制作旅程，未提交、未部署；不等同完整 B 封板。

- **B-VI 时间编辑三个限定出口已通过**：`editing/temporal.py` 承载固定媒体/原生画面的帧值保真 slice 与源窗映射，显式 linked_group_id 随拆分/裁短同步，VideoObject 内原声自然沿同一源窗；split 左侧保留身份、右侧生成新 clip/object/animation 身份，trim 不 ripple。`editing/transitions.py` 为首个全画幅不透明固定媒体 crossfade 解算真实 handles；版本保留原切点，video-spec 固定覆盖窗，renderer 同时对 VideoObject 内原声交叉淡化。透明层、外部视觉 transform/opacity 动画、独立关联 AudioClip 的转场淡化、待生产 Speech/Generator 的内部切分未声明支持。音乐快照冻结实际 beat_grid，snap_cut 经音乐源窗映射到输出帧，优先真实 beats，BPM 仅作已知名义拍长的后备；无节拍数据或无容差内节拍时不伪造吸附。
- **同一作品的真实编辑与再交付**：项目 `2f875e94` / Composition `37733138`，正常 Chat 从15秒真实访谈素材设计并审阅后，去掉重复背景、拆分、裁短右段、将右段换为固定新源窗、吸附音乐节拍、添加0.4s叠化；v6 `73254d28` → Run `cdd41289` → Output `97dcdebd` COMPLETED。切点固定3.533333s/frame106，总长8s/240帧，右段在7.5s结束，末半秒保留独立标题与音乐。随后正常 Chat 仅把同一 transition 的时长改为0.6s，v7 `4564a375` → Run `610ca8b9` → Output `b5deb79f` COMPLETED。服务端比对证明 v6/v7 settings、sources、全部 tracks/clips 完全一致，只有 transition.duration 及相应 Scene 视觉摘要变化；两次净计各16开发积分，无新图片/TTS/采集。浏览器分镜可读两段输出/源窗及0.4s/0.6s叠化，两个实际 MP4 播放、旧v6归档仍可读，硬刷新保留两交付、Run数始终2。
- **本批验证与费用**：API1366、web260、video-spec9项测试通过；web/render TypeScript、ruff F、compileall、git diff --check通过。红→紫→蓝本地实际渲染证明叠化像素，原生 Bezier 裁剪与关联音轨有对应主流程定向覆盖；真实两版均240帧并含非静音音轨，源窗两段的解码相对映射一致，不以参数/相关性替代完整独立听感。初次混合设计失败时的9次供应商用量USD0.0950493仍计入；已提交 ConversationUsage USD0.275518（含真实交付触发），另有新/旧 Chat 能力问答 USD0.024655，未新增 Run；当前对话收口后的已记录总支出USD0.8168918，按既有7.2约人民币5.88，含失败及已返回未落账用量，未超新增10元；被reload中断的Director最终用量未知，不记零。本批没有重跑完整真实旅程。证据归 `artifacts/video-project-b/b-vi-temporal/`（Git忽略）。
- **能力入口**：三个出口均归原 A3/A5 定义与 B-VI 实施范围；plan/propose 的 `revise_video` schema 暴露 split_clip、trim_clip、set_transition、remove_transition、snap_cut，说明及用户能力菜单同步更新，不另建三个执行工具。正常新 Chat 与已有交付 Chat 均回答拆分、裁短、叠化、音乐卡点及主要适用前提，Run 数分别保持0/2；能力问答不冒充完整语言稳定性通过。原始答复归同目录 `capability-proof.json`。代码集中在主工作树 `feat/mg`，未新建 worktree、未提交、未部署。
- **本批顺路修复**：narration_enabled=false 在媒体设计中不再被当作开启旁白；mixed Director 只返回其实际支持的平面字段；remove_clip 经唯一候选校验删除确切媒体及其转场链接，不再受过期的“只能删文字”限制。storage.read 使用已配置的下载客户端，避免内存读取绕过现有下载代理。未建新调度链、框架或数据库表。
- **对话与呈现收口复验**：项目 `2f875e94` 经正常 Chat 完成「仅保存标题 v8 → 插入能力问答且零版本/零 Run → 后续按刚存 v8 制作」，Run `fc0668b3` 与 Output `b6a6e87c` COMPLETED；能力答复的 BeatGrid 容差数值为默认0.2s、大于0且至多1s。用户报告项目 `822a422d` 首次续跑因素材 schema 与 captured-page 上下文矛盾而12次工具耗尽；补齐既有页面 URL/id/view 事实并解除该矛盾后，正常纠错消息复用三张既有网页及冻结音乐保存 Composition `d047448e` v1 `30ed2ad0`，零重新采集、零 Run。该回合首轮工具参数拒绝后的零 delta 属现行 frame-silent 法，最终信封由客户端打字释放；未为放行修改流断言。卡片 ACK 原先把消息块旧展示 hash 与当前 DTO 强绑，现严格校验同版 content_digest + 当前实际 DTO digest，并同步更新消息块和版本外 receipt；真实浏览器初次与硬刷新后的 ACK 均200，两处 digest/complete 一致，设计活动行在刷新前后均回放，零新 Output、零控制台错误、零翻译 key 泄漏。video design/revise/review 的持久活动 replay key 已对齐；定向 API283、web69 与 tsc 通过。普通仅保存修订 v10 虽保存/ACK/零 Run 成功，回复仍逐项复述未改层、字号、源窗与音频参数，且明显承接前一轮技术汇报形态；表达验收未通过，未继续用付费回合试措辞，完整 B 不因此封板。证据归 `artifacts/video-project-b/b-vi-temporal/`。


- **Use prompt 与 Chat 收口（2026-10-30，进行中）**：按当前代码及真实首页盘点14项：6个可点击 demo、6个禁用族配方、2个隐藏配方（image-video同时reserved）。未启用隐藏入口。正常前端已交付英文逐字短片项目 `1dcdfbac` / Run `a13c943d` / Output `9a35636a`、文案节奏短片 `dd0c2062` / Run `7b86600b` / Output `b6d96fcb`、基础网站片 `28c04380` / Run `6f716937` / Output `555f14c1`；首片局部修订v4只保存、零新Run。字幕入口 `47f045f4` 因Mixed Director任意 prose字数限制两次失败；去掉 intent/visual_description 的非领域限制并暴露现有文字布局字段后，v2的两个字幕分别0–4s顶端、4–8s底端，原声/源窗保留，Run `d5866541` 已发起。第二网站入口 `6675b8b3` / Run `cd7fa91a` 已发起；这两条最终交付须待Docker/数据库恢复核验。最后上传操作演示入口只证明预填，浏览器上传权限及原生选择器阻塞，未标通过。
- **本批源头修复与取证**：design/revise工具说明与canonical卡片职责一致；修订观察用系统字段差异。MG Director明确实际background字段与读得清的配色，微推近/拉远通过既有transform.scale表达，不建相机引擎；首条暗字深底且缺运镜的错误首稿及正常Chat纠错保留。分镜区分逐词/逐字/逐行，update_text支持现有布局的像素x/y/width/height。一次英文片交付被错误称为中文，来源是project.language；新视频按保存设计声明传递content_language，历史未声明者不向交付模型声称语言，不回写旧版本/账本。当前简单修订已有简短回复样例，不宣称所有多轮语言稳定。旧展示hash调查原结论与original_hash_reproduced=false矛盾，已修正；当前重复DTO一致，历史原始工作树/DTO不全，无法声明完全复现旧漂移。
- **本批检查、费用与证据**：相关API125项通过；Ruff检查中无用导入已删除，最终检查以本批收尾为准。前端TypeScript初次报既有并行mentions/支付改动类型问题，未写成全绿。原¥10窗口已记录USD0.9543168/约¥6.87及旧未知项不重置；用户另授权¥20，本次已返回供应商用量约¥4.73，含失败、修复与worker，当前API日志无未返回调用，历史未知仍另列。完整中英预填、实际消息、全部捕获模型payload/工具观察、SSE、证据与失败过程合并为 `artifacts/video-project-b/b-vi-temporal/chat-journey-review.md`，该文件不代替尚未完成的前端/交付验收。当前数据库重置连接且Docker命令超时，暂停新增收费操作，继续无付费检查；不擅自强杀Docker，不以环境阻塞删需求或标完整B完成。

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
- 基于现有 Activity / Run 协议实现真实阶段的最小持久化、推送与回放，绑定版本、run、step、attempt，保证事件有序去重、旧尝试不覆盖新尝试。单个 produce 节点可有内部阶段，不为显示扩张执行图；内部阶段在 RunBlock 内呈现，不能只留下当前 `stage` 而无法回放。
- 呈现采用 CHAT_ARCHITECTURE §8.10 的 TurnBlock/RunBlock；WorkSegmentRow / RunTaskList 可作为内部适配器，不再分别占有顶层等距消息槽。正文继续走既有打字机与 null 读容忍，活动不暴露 raw tool calls/reasoning，首稿与费用授权不被视觉调整绕过。通用 Chat live 折叠与 Run 工作段按既有合同分别处理，具体拆分与替换顺序归 [Chat TurnBlock 施工合同](chat-turn-block-implementation.md)。
- 列出实际阶段及其唯一发射点、缓存/关闭/失败/重试表现和记录写口；采用短事务与现有 fencing，不能让进度写入干扰计量、执行或终态。A 可先提供 fixtures，B 接真实路径，不要求 A 首个 MP4 切片先实现整套 Chat。

### 2.3 当前代码处置与目录验收

新旧文件的新增/拆分/原地修改/保留/删除及阶段归属，唯一清单见 [VIDEO_PROJECT §12](../VIDEO_PROJECT.md#12-目标目录与新旧代码处置)。本处不复制第二份目录树。

- A 先落实 editing、tools/video 最小执行、video-spec、renderer adapter 与必要 ORM/迁移/Output 接线；不预建外部 Skill 或 Inspector 空目录。
- B 按母文档 §12.2 逐行核对，尤其不能漏掉 main 启动 sweep、FilmNarration 存储、工具/Skill 注册、费用单位、render/probe/route 准入与 UI 协议。
- 后续按新合同 P8 依同一清单审计实际删除结果；Film 目录须先提取配音复用、grounding、相机/文本等有效能力，不做整目录盲删。packages/clip 与共享依赖另按消费者保护。

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
- [ ] 同一后端数据可驱动既有 Chat 与 TurnBlock/RunBlock 呈现；异步 Run 跨回合仍可准确关联，刷新不重启执行，停止接收流不误作后台取消。单项原型通过不等于 Chat TurnBlock 四阶段施工已经完成。
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
| **B-II 官网片与过程收口** | 官网模板/grounding/快照/镜头/字幕/音乐；真实 Chat 首稿审阅→制作→播放/试听→局部修订；刷新恢复、真实阶段和剩余 prompt 检查 | 真实 Chat 闭环、修订同一性、刷新恢复与帧级播放核验已通过（证据见 §2.0）；欠账：听感试听、运镜修复像素级复验（随下一首稿）、音乐循环接缝真实渲染 |
| **B-III 混合合成底座** | VideoObject 的 schema→source/probe→编译→adapter→Chat 全链；源窗与输出窗、原声同步/音量/静音、画面位置/尺寸/裁切；与原生标题/字幕、动态背景/音乐同时合成 | 真实 Chat 首稿、四种局部修订、v5 再交付与浏览器播放/刷新已通过；局部换源窗保持输出时长，亲耳试听仍未验收 |
| **B-IV 原生 MG 与程序画面** | 原生最小图元/路径可经 Chat 精确改动画；GeneratorObject 允许 Agent 编写、预览、修改受控视觉程序，固定来源与结果后混合合成，解锁可再创作的特殊背景/示意画面 | 两个纵向真实 Chat 出口分别通过；drawing-v1 动态预览、局部程序修订、固定生产/交付、缓存与 resume 复用已验；不扩为全量图形引擎或代码平台 |
| **B-V 模型生成媒体** | 在 Generator 来源上增加一个确切 provider 的图片或视频生产，沿既有授权/费用→固定媒体/血缘→合成，解锁生成素材与原生可编辑层组合 | 首个 MiniMax image-01 16:9 单图真实消费者已通过 Chat 首产、原生修订复用、明确重生成与最新媒体再交付；固定/执行身份、计量和回放边界有定向证据。响应未知窗口已补单次 POST、submitted 恢复失败闭与无网络回归，未知消耗仍需对账且不承诺恰好一次。只声明 image-v1，其他供应商与生成视频未接，完整 B 未封板 |
| **B-VI 旁白与原合同余项** | Speech/TTS 固定切点、有界语速、超长冲突、字幕派生及手改保护；split/trim/首个必要转场/BeatGrid 按已声明消费者实施与验收 | 首个 MG + MiniMax speech-2.6-hd 两幕中文消费者已通过真实 Chat 首产、字幕单独恢复、单幕旁白修订再交付、未改音频复用、人工字幕保护、实测超长冲突与浏览器硬刷新；真实加速样片及具体跨作品回执故障已补齐，完整听感和其他多轮稳定性仍开放；本批另已补齐固定媒体 split/trim、全画幅 crossfade 与冻结音乐节拍吸附，真实 v6/v7 证据见 §2.0；仍不声明完整 B 封板 |
| **B-VII 通用时间线编辑内核** | 统一 target、move/trim/split/delete/time_map、ripple/source policy；Scene/Clip/Animation/Transition/全局音频协同变换；`revise_video` 一次原子落版 | 首轮真实 Chat 三项问题的修复已落码，复验未运行；端点同网格量化、能力拒绝一次终态、成功后不额外补版；纯函数/DB/temporal_revision/speech_edit_refusal 已写待跑，联合验收按 §2.5.4 |
| **B-UI 产物平铺与共享查看器** | 各轮交付消息保留产物卡，当前 Chat 全部已交付 Outputs 共用翻页与缩略导航；版本作字段标识，历史交付仍可读取 | 代表旅程通过，用户已确认视频有声音，见 §2.0 / §2.5.2；不等待 C/新合同 P10 |

**B-III 的代表性验收**：动态背景 + 中央真实录像 + 独立顶部标题 + 定时字幕 + 原声/音乐，在同一 Scene/Composition 混合；通过 Chat 只改一处字幕或中央录像布局，未改内容/源窗保持，再制作交付。背景可先用已有动态素材或受支持对象动画，不把复杂自由 MG 当作混合合成的前置。此后 B-IV 再验证原生/程序画面替换背景，B-V 再验证生成媒体替换其中一段；不为每次接入重复建设生产链。

**声明与发布门**：§2.4 逐项按证据更新，未实现/未验收不勾选。限定能力发布只声明实际通过的内容，完整授权/收费/恢复/交付和新合同 P7/P8 发布门不可省略；明确不支持的生成视频、通用转场、通用媒体 rate 等继续留在新合同，不标完整 B 完成。新增批次不自动授权外部模型费用、安装依赖或部署。

**实现纪律**：一次代表性真实旅程驱动必要功能及少量承重守卫；不提前创建未来模块/表/空目录，不建立另一份目录树。新增文件/模块按 VIDEO_PROJECT §12 及模块图同批登记。用户可用入口、版本和成片优先于样片脚本数量；仅对实际修改运行必要检查，最终集中回归。

### 2.5.1 B-IV 的两个纵向出口（已分别验收）

1. **原生图形**：从一条真实需求选择最少必要图元/路径属性，贯通表达→Chat 设计/修订→编译→renderer→交付；至少修改一项形状属性或动画而保留其他层。沿用 Animation 与唯一内容写口，不先扩成矢量编辑器。
2. **Generator 程序画面**：从一种受控运行时和一条短 2D 或 3D 需求开始，冻结 VIDEO_PROJECT §4.3.2/§8.1.1 的首个实际 schema、程序/资源身份、参数和输出约束。用现有 Chat/Director/harness 生成视觉程序，给出动态预览、真实诊断与可读取的视觉反馈，按用户意见修改内部画面，再钉来源生产并合成；不是仅改烘焙视频的外部布局。完成片继续可按同一 Composition 修订。

最小预览随程序消费者交付，完整 scrub/Inspector 仍归 新合同 P10；不另建预览任务系统或无限自修复环。程序运行只获得声明资源与受限能力，不获得业务图/数据库/计费/任意网络访问权；依赖及运行方式按真实需求选择，不把安装授权或第三方许可视为默认存在。

当前四层结果均有真实证据：

- **表达**：CompositionVersion 可保存原生 ShapeObject 的几何/填充/layout/transform/opacity，以及 GeneratorObject 的 drawing-v1 code/parameters/output；跨版本 object_id 与 program_digest 稳定。MG Director 当前按需创作 rect/ellipse，path 是原生 schema/精确编辑能力，不宣称 Director 已覆盖任意路径设计。
- **执行**：原生图形经 video-spec 与 SVG adapter 渲染；drawing-v1 在受限进程中生成固定 MP4/PNG，生产与合成复用既有 Run/Output/Render。最终 spec 只消费固定媒体，程序与模型请求不进入 renderer。exact-digest 缓存命中不执行程序；真实已交付 Output 的受控 resume 分支返回原 Output、原 execution_digest 与原媒体，未重新准备。
- **创作**：原生项目 `5bf0b8f3` / Composition `c8cb1b68` 的 v2 Run `5c260ea6` → Output `083c8b3b` COMPLETED。Generator 项目 `e0736859` / Composition `c41b1ce9` 由 Agent 写出真实 `render(ctx)`，v1→v2 改绿色与双倍速度，60 帧均不同；Run `eb9a70e9` → Output `2c45efe4` COMPLETED。浏览器中预览从可播放前零 ACK 到真实播放后对应 ACK，1 秒与 2.5 秒成片帧确认程序画面与原生标题合成。
- **编辑**：原生 v1→v2 的 change_set 仅含目标 shape 的 object+animations，另一图元与标题不变；Generator v1→v2 仅改 Generator object 的 code/parameters，标题不变；交付后 v3 在同一 Composition 仅改标题，程序 digest 不变且未新增 Run。烘焙媒体内部元素不冒充原生可编辑对象。

每条代表旅程只证明上述实际能力，不穷举特效。本出口不覆盖其他模型媒体或生成视频；旁白留 B-VI，Skill 持久化/导入留 C，完整 scrub/Inspector 仍归 新合同 P10。第二模型接入只在出现实际能力需求时另明确范围，不预先承诺同等创作质量。证据位于 `artifacts/video-project-b/b-iv/`（Git 忽略）。

### 2.5.2 B-UI：产物平铺与共享查看器（代表旅程通过）

本批归 B5 的 Chat 表面接入，在已有交付链与 Output 引用上独立施工、独立验收；不等待个人 Skill、完整视觉改版或 新合同 P10 Inspector，不改变既有首个限定能力发布门。当前代表旅程与有声播放证据见 §2.0；不代替完整音乐接缝/音画同步听感或完整 B 验收。产品行为唯一事实源为 VIDEO_PROJECT §10.4。

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

以一个真实产品页的页面特写/元素运镜镜头和一次真实审片修复作为首批出口，按需补现有能力，不另建大阶段。两个首个切片均已按 §2.0 的真实 Chat 证据通过，只证明链路成立，不替代完整需求验收。产品规则归 VIDEO_PROJECT §9.2 / §8.5，排期归 PROGRESS §0；B-UI 的产物查看与 B-VII 的通用时间编辑分别验收。精确时间点编辑归新合同 P10，不作为审片前置。

| 增量 | 首批代码改动 | 验收 |
|---|---|---|
| 镜头素材采集 | 在 `tools/research/capture.py` 补渲染正文和整页高清图；按所选镜头补元素截图/坐标，复用 `pipeline/web_capture.py` 与 `tools/video/preparation.py` 存储、冻结和消费。仅扩实际需要的 DTO 与 grounding 接缝 | 一个真实产品页的内容足够支撑设计，所需截图和元素能完成一个实际镜头，位置/清晰度正确；需要空底板或交互状态时随此镜头验收，不强制首批覆盖全部选项 |
| 内容审片 | 在 `tools/video` 增加小型审片实现（可为 `review.py`），直接解码成片取帧，复用 `agents.py` 与现有质量/交付读面；`run_review.py` 只读报告事实。只在确有消费者时扩 verify/quality | 对一条真实影片报告一个可复核问题，经正常修订后复核改善；范围与未检查项诚实，费用和执行复用既有机制 |

当前 `output-checks-v1` 已接入 `review_video`：除真实静帧内容审片外，报告增加采样帧平坦/重复候选及首个音频流的 RMS、峰值与削波事实；只有执行 spec 明确期待声音时，静音/低电平才列为问题。报告与复用身份绑定检查器版本。定向核心测试已通过；首条 B Output 与四条 C4 Output 各完成一次付费审片，确定性检查无异常、内容 findings 为空，相同请求复用一致。该证据不覆盖连续运动、主观听感、integrated LUFS 或音画同步，也不替代其他作品的完整旅程。

只补与旅程风险相称的检查。稳定身份、权限、授权和资源限制复用既有实现，不逐处重复设置守卫；不把全站采集、完整帧平台或所有异常分支覆盖设为本批前置。

**需求保留与封板条件**：

- 采集仍须满足选定 video-shotcraft 镜头和自我介绍视频的实际素材需要；当前 AgentVeil 正文采集有界且 `body_truncated=true`，新冻结 manifest 已在根级携带该标志，Director 独立 `CAPTURE STATUS` 区读取三态且不作为产品正文引用；旧快照缺字段只读 UNKNOWN，不做历史回写。长页补读仍开放，空底板与交互状态也未实现。后续镜头确需这些能力时登记并补齐，不以首个静态镜头成功关闭整项。
- 内容审片按 VIDEO_PROJECT §8.5 对实际作品逐项说明文字/构图、内容一致性、运动衔接与适用声音检查的覆盖；单次问题修复只算最小闭环，未检查项不算通过。
- 不为覆盖未来情况先建平台，也不因简化实现删除已经明确的产出能力；剩余实现/验证有当前归属后才结束一个切片。

### 2.5.4 B-VII：通用时间线编辑内核（修复已落码，真实 Chat 复验未运行）

目标是补齐 Composition 的通用编辑代数，而不是为“整片改成 30 秒”增加专用操作。领域合同唯一事实源为 VIDEO_PROJECT §6.6；本批不新增作品根、第二写口、第二生产链、数据库表或 renderer 专用时间字段。

当前实现以 `EditTarget` + `TemporalEdit` 承载统一目标、操作、ripple 与 source policy；旧 `move_scene` / `trim_clip` / `remove_scene` / `remove_clip` 转入同一纯候选变换，split 复用同一目标与关联解算。Scene/Clip/Transition 保持精确有理数直到共享 tick 量化座；Clip-local keyframe 在所属 Clip 的输出网格量化后重新定基，局部 0 与末尾 keyframe 分别对齐 0 和新 Clip 时长，stagger 只按 scale 映射。原生/Web 内容可做输出时间映射，固定 Audio 仅在显式 `crop_1x` 下重裁 1× 源窗，Speech、Generator、VideoObject 的时长映射失败闭。确定性媒体能力拒绝经 `TemporalCapabilityError` → `TerminalRefusal` 在首次拒绝后结束工具 loop，并由两条 Chat 路径根据基版本真实读取回复版本、时长与未制作；可修复参数错误仍走普通反馈。ripple 只平移下游，用户点名范围保存后不得再擅自延长结尾或拉伸全片。`revise_video` 仍只经 `apply_composition_edits` 原子落一个版本并继承 `skill_provenance`，观察携带真实 `duration_seconds`。

首轮真实 Chat 已暴露端点独立量化差 1 tick、能力拒绝反复重试和成功后额外补版三项问题，上述修复均已落码但复验未运行，不能写成验收通过。纯函数、过期 base_ref DB、temporal_revision 的 88→30 秒与 Scene trim 两回合、speech_edit_refusal 的 Speech 一次拒绝诚实收尾覆盖已写入；当前核心套件和真实 Chat 复跑仍是当前出口。

**施工范围**：

1. **统一目标与策略解析**：在 editing 层实现 Clip/Scene/Track/显式选择集/Timeline 的稳定 id 解算，以及 `ripple=none|forward`、显式关联和 source policy。目标与关联不能按时间相交猜测。
2. **统一时间变换**：实现 `time_map(t′=a×t+b)`，对目标 Scene/Clip/Transition 范围和 Clip-local keyframe 时间应用同一映射，最后由唯一量化座取整。Object/animation value、布局、SourceSnapshot 与未改实体 id 保持；`skill_provenance` 原样继承。
3. **归并现有操作语义**：`move_scene`、现有 split/trim 与新目标解析共享同一法律，不能保留“Scene 一套、Clip 一套、整片再一套”的三套联动规则。至少让 Clip 平移、Scene ripple trim、显式 delete 的 lift/ripple 都使用同一内核。
4. **首个动态媒体消费者**：官网/原生画面使用输出时间映射；跨幕 Music 以显式 1× 裁取适配新输出窗并保留音频属性值。Speech、待生产 Generator、无法保持 1× 或已审阅语义的媒体整批拒绝；通用 `rate` 不在本批伪装实现。
5. **Chat 编译而非逐 Clip 心算**：`revise_video` 接收通用目标、操作与策略，由服务端一次生成 op batch 并经 `apply_composition_edits` 落版。总时长请求只负责推导 Timeline 上的时间映射，不进入 `design_video` redraft，不产生多次中间版本。
6. **诚实失败**：工具观察返回真实保存版与系统 change_set；连续无进展及时终止。回合已经写入草稿但未达到目标时，最终回复必须说明当前版本、实际总长和未制作事实，不能退化为与零写入相同的通用能力拒绝。

**本批不做**：通用变速引擎、磁吸时间线、自由 NLE 选择器、完整 roll/slip/slide、Scrub Inspector，以及按 `launch-film`、模板名、Scene 名或固定秒数分派。新增动画属性不得要求时间映射逐属性打补丁。

**出口与验收**：

- 同一内核分别完成：移动一个 Clip、缩短一个 Scene 并 ripple 后续、删除目标的 lift/ripple、整个 Timeline 的时间映射；证明没有官网片或“30 秒”特判。
- 从一部含四章、开场/收束、网页相机动画和跨幕音乐的 88 秒 Composition 出发，正常 Chat 请求“总时长压到 30 秒，章节保留，其他风格不变，只更新分镜不制作”，只新增一个版本；新分镜 `max(all clip.range.end)=30s`（允许统一量化的一帧内误差），Run 数保持 0。
- 上述版本中 Scene/Clip/Transition/动画时间相互一致，章节与实体 id 保留，网页快照、文案、布局、动画 value 不变，Music 不静默变速，`skill_provenance` 不变；不得留下前段已改、后段仍在旧时间的部分草稿。
- 不支持媒体、非法目标、过期 base_ref 与无法满足的关联整批拒绝且零新版；已有部分草稿时的回合回复与零写入失败明确区分。
- 纯函数覆盖不同 fps/timebase、多段映射、全局/关联 Clip、Transition 和新注册动画属性；真实 Chat 旅程覆盖整片、Scene ripple 与失败闭。验证按当前用户分工执行，未运行项不得写成通过。
- 与 C 的联合验收只消费稳定接口：内置或外部 Skill 创建 v1 后，经 B-VII 得到 v2，Skill 不重新执行，provenance 与固定生产引用保持。C2/C5 的基本入口施工不以 B-VII 完成为前置。

## 3. 阶段 C——外部 Skill 持久化、加载与领域策略

### 3.1 目标

原始 Claude/Codex 外部 Skill 能按 owner 保存为不可变 SkillVersion，并通过现有设计/Generator Agent 指导真实创作、预览、修订与固定生产；Strict/Adaptive 只执行显式声明的领域约束。

### 3.2 施工范围

**C1. Skill 存储与版本**

- 新增用户 Skill 与 SkillVersion 持久化；平台内置 Skill 继续走代码注册表，用户 Skill 按 owner 隔离。
- SkillVersion 保存 instructions、references、声明输入、能力报告、Strict/Adaptive policy 与 `source_uri/source_revision/source_hash`；原始外部包无需改名或内容改写即可导入。
- 相同审阅 draft 重导入幂等，不同来源或声明/policy 追加不可变版本；`source_hash` 只标识原始来源，完整版本另有 digest；数据库拒绝版本 UPDATE/DELETE，读取必须校验 owner。
- 本阶段不从自己的 CompositionVersion 形成或保存 Skill，不做市场、团队共享、多 Skill 自由叠加或第二套模板 DSL。

**C2. `/任务名 + prompt`**

- `/` 打开统一 Skill picker，同时列出平台内置 Skill 与当前用户可访问的外部 SkillVersion；选中形成可见 Skill chip。消息携带统一 Skill 引用：内置由注册表 id + 版本解算，用户 Skill 由不可变 SkillVersion id 解算，仍走唯一 `POST /chat`。
- 自然语言明确点名时通过普通 Chat 解算唯一可访问 Skill；歧义必须询问，不能任意搜索加载。一次创作至多绑定一个显式 Skill，普通 Chat 未选择时仍可按现有路由使用内置默认。
- Home 的视频 Skill 卡复用完全相同的 Skill chip + 可编辑 prompt 载荷，不能另走隐藏 recipe_id、PromptTemplate-only 或第二发送链。未注册/未声明能力的 Skill 不伪装成可点击卡；非 Skill Recipe 继续使用 PromptTemplate。
- Skill 不自动发送、不自动 Start、不免除首稿审阅、制作意图或费用确认；平台安全/grounding 规则始终优先。
- Strict/Adaptive 只约束首版设计。版本出生后继续走 `revise_video`，不重新执行 Skill，并保留 `skill_provenance`；通用时间编辑归 B-VII，不在 C2 复制。

**C3. Strict / Adaptive**

- Strict 只检查导入审阅时显式钉入的必要输入、场景数、时长和 Generator producer；冲突在 Agent 调用前给出具体字段与期望/实际值，不发明通用约束求解器。
- Adaptive 只把声明边界交给现有创作 Agent 适配；实际故事板、Generator 程序/参数与 policy 事实随同一设计读面呈现。
- 参考 demo 的词数、示例文案、坐标和时长不会仅因出现在 references 中就成为 Strict 规则；只有导入时明确声明的字段才由代码强制执行。
- Skill 使用现有素材/产物通过全局 @ 引用，不建设“复制确切作品”功能；任何模式都不能绕过 grounding、权限、报价、首稿审阅或制作授权。

**C4. 外部 Skill 导入**

- 解析 SKILL.md、frontmatter 和 references；限制大小、数量、路径与类型。
- 分离创作指令、结构要求、示例和外部依赖，生成 SkillDraft + 能力差异报告。
- 外部 `scripts/` 不自动执行；`allowed-tools` 不授权。导入内容只能转换到已支持且受控的能力；Generator 的显式程序创作按 VIDEO_PROJECT §8.1.1 执行，不将外部任意脚本、网络/文件访问或私有工具直接放入运行链。
- 原生路径只能映射到已注册 Objects、Animations、Binders 和 Validators；需要自定义几何或连续程序运动的画面，由 Agent 在现有受控 Generator 中编写、预览和修改程序来源后固定生产。不得为每张外部卡手写产品级固定适配器；两条路径都无法表达时才列能力缺口。
- 外部内容视为不可信创作输入，不能覆盖系统、grounding、权限、报价和授权。
- 用户用真实素材审阅生成的 CompositionVersion 后才可进入固定生产；导入 SkillVersion 本身不等于创作或制作授权。
- **必验消费者 = video-shotcraft**：固定仓库 commit，原始包未经改名或内容改写完成通用导入与 SkillVersion 持久化。选择一个未参与固定适配的 held-out 镜头，用新的产品文案/素材，经保存版本的通用加载链让真实设计/Generator Agent 完成创作；能原生表达就生成普通原生编辑，需要自定义视觉程序就走现有 drawing-v1，开发者不得代替 Agent 写死结果。
- 同一 held-out 镜头须完成一次真实修订，证明继承的 Skill 方法与 Generator 参数可继续使用；经 run-less 精确版本接缝得到一个真实 Output 并检查实际帧。保留程序/编辑来源、预览、digest、CompositionVersion、Output 和真实模型用量证据，不伪造 Chat/Run 授权或计费旅程。
- 产品加载链不得按包名、镜头名、仓库 URL、commit 或固定 digest 分支，不得 import/调用固定适配器、为镜头硬编码 ops、新增专用 Object/runtime 或执行外部 scripts。固定适配器只保留为合同测试夹具；结构级防特化测试必须覆盖这些禁令。
- 只声明实际验证的镜头与能力范围；未选镜头、私有工具和未支持依赖明确列出，不宣称完整兼容镜头库。真实付费只用于必要的 held-out 创作/修订和至多一次 exact Output 审片，先核对报价，不批量跑镜头库。

固定 `blur-slide` / `title-demote-to-label` 原生适配器与旋转轨道消费者只保留为 Composition、Generator 与渲染合同夹具，不在产品 Skill 加载链中；其固定词数、坐标、URL、commit 与 digest 不成为产品分派规则。当前未承诺附属标点、选区高亮、方向性运动模糊、杂志/工作台家具、未选镜头或外部脚本执行。

原始 video-shotcraft 包固定于 `1266a3ec4831289c4d893d42dd5102723658039a`，通用导入保留 1217 个非 VCS 包文件中的 1015 份 accepted references，原名称与内容未改写；SkillVersion `e3027644-2d15-4965-a168-95adab26d0e9` 已持久化，owner 隔离、同 draft 幂等与数据库不可变拦截均经真实数据库验证。`source_hash` 为 `03fb2160266daa15daf74765238fc081b22227dd040b2bfb023ae61f07ee5c56`，完整审阅 draft 另有 `version_digest`，同一来源可在声明/policy 变化时追加版本。

held-out 为此前未适配的 `marker-underline-title`。保存版本只通过通用 `SkillCreativeContext` 注入原始镜头卡与 TSX 参考，真实 `program_director` 为新产品文案 “Turn dense research into a clear weekly briefing” 编写 drawing-v1 程序；Composition `b13aef5c-2df5-4b3a-a48b-1441dd52a21b` 的 v1 `bad3211f-4d1b-42f4-90ea-d5cd8c06faa0` program digest 为 `4f54d1d55037ebe725881fd3066331d4ab4065a3f7c167094e8c9bab5f4bec6b`。v2 `0942ecaa-17cd-48ee-911d-8a2f7fd07ee2` 经 `revise_video.update_generator` 将 `marker_draw_frames` 从 10 改为 12、`marker_color` 从 `#C9822B` 改为 `#A94E20`，代码不变，新 program digest 为 `c87803cc5b8e037d82e04a4147c06484a755eda1ebe2471611365543df02776c`。v3 `7f6ea43f-d113-4717-a891-446fd1ff937c` 再经原生 `update_text` 居中标题、改深色并清除 chip，Generator 代码/digest 不变且固定媒体复用。

最终 run-less Output `a7186f7d-5c0b-4ff6-ae65-58653681c242` 已完成真实 3 秒渲染，content digest `397f4406b397e591088d4b84d8ccbd32a169edc0a747af60f779509115986f0b` 与 v3、render-spec provenance 一致，未扣 credits。0.5s / 1.5s / 2.7s 实际帧显示标题可读、马克笔尚未起笔及暖色变宽毛糙笔迹落在 “clear” 字底；静帧证据不冒充完整连续动态看片。创作过程保留 Agent 请求/返回、预览、失败校验、版本与 Output 证据于 `scratch/c1-external-skill/evidence.json`；6 次真实 MiniMax M3 调用共 55,357 prompt + 104,847 completion tokens，按当前价目估算 USD 0.142424，包含被拒候选，修订与 run-less 渲染无新增模型调用。该批既往检查不替代当前 `test/core` 与真实旅程复证。正式 Chat 呈现授权、Run 计费旅程、C2/C5 与整个镜头库兼容性未由该领域切片替代。

**C5. 复用 Chat 预览与引用组件**

- Storyboard/CompositionPreview 以版本引用加载 DTO，可刷新回放，不依赖 Canvas。
- 预览通过 PreviewAdapter；不把 Remotion 组件名写入消息或 spec。
- 本阶段不做 Scrub；仅建立后续 Inspector 所需的稳定 version/clip/object 引用。
- 正常 Chat 必须完成 Skill chip 持久化与刷新回放、首稿完整呈现、后续用户批准、Run 授权/计费、固定版本交付及普通 `revise_video` 修订；Skill 只参与设计，不在修订或 worker 中重新加载。

当前 C2/C5 基础接线已落码，**本批未运行验证**：内置引用为 `{kind:"builtin", skill_id, version}`，外部引用为 `{kind:"external", skill_version_id}`；统一 picker/chip、Home 视频 Skill 卡与首条 handoff 仍只走 `POST /chat`，引用存于用户消息现有 `intent` JSONB，SSE 完成信封与历史刷新均投影同一引用。自然语言只在唯一整名/版本命中时绑定，多版本或同名冲突进入普通 Chat 询问；待选候选以精确引用持久化，紧随其后的 `vN` 回答只在当前仍可访问的候选中解算。显式引用在持久化前复核 owner、版本和能力。Skill 仅由共享设计座传入首版 `design_video`，外部 Skill 不会静默落入 launch-film；`revise_video`、`produce_video`、Run 与 worker 没有 Skill 重载入参。已编写解析、owner/版本、回放和 Home 载荷合同测试，但 pytest、Web 测试、tsc、真实 Chat/Run、移动端/SSR/水合与恶意 Skill 综合验收均未执行，以上复选框因此保持未完成。当前 Chat 外部绑定只加载 instructions，尚未提供 references 路径选择；不得据此宣称外部包全部参考资料已可用。

### 3.3 C 阶段验收

- [x] 原始外部包保存后，instructions、references、声明输入、能力报告、policy 与来源身份完整，owner 隔离和版本不可变经过真实数据库验证。
- [ ] `/任务名 + prompt` 在刷新后仍绑定同一 SkillVersion；内置 `launch-film` 与外部 SkillVersion 都经统一 Skill 引用解算，无隐藏 recipe_id 或第二执行链。
- [ ] Home 视频 Skill 卡与手动 `/任务名 + prompt` 产生相同 Skill chip + prompt 载荷；非 Skill Recipe 的 PromptTemplate 行为不回归。
- [ ] 正常 Chat 完成首稿呈现→用户批准→Run 授权/计费→固定版本交付→普通修订；Skill 不在修订或 worker 中重新执行。
- [x] Strict 不可满足时明确失败/询问；Adaptive 的变化完整可见。
- [x] 外部 instruction-only Skill 可转换；依赖脚本/私有工具的样本得到明确能力缺口而非静默降级。
- [x] held-out 镜头完成真实加载→真实 Agent 创作与预览→方法/参数修订→run-less 精确版本 Output 与实际帧检查；产品加载链无包名、镜头名、URL、commit 或 digest 特化。
- [ ] 恶意 Skill 不能越权读取素材、调用工具、绕过授权或修改系统规则。
- [ ] 个人越权访问、版本固定、旧作品独立性和纯 Chat 回放通过。

## 4. 既有扩展实现与验收证据

本节只保留扩展能力的当前实现、真实证据与验证边界，不再承担后续排期。所有未完成施工、出口与发布门统一归 [新合同](skill-package-promo-video.md)；已有证据不能扩张为完整视听、生产发布或全部能力通过。

### 4.1 创作能力扩展现状

现有扩展只丰富 Composition / CompositionVersion / Generator / tools，不新增作品根、第二意图面、第二内容写口或第二生产链。固定 Skill、外部 Skill 和自由创作共用同一创作循环，Skill 不进入修订或 worker。

不同来源出生后都是 Tracks / Clips / Objects / Animations / Audio / Speech / SourceSnapshots。既有实现不引入外部 124 张镜头卡的全量镜像、通用插件平台、公开 Skill 市场、通用 Activity 平台、分段渲染器或完整 NLE。

**公共集成当前状态（已落码，未运行验证）**：Activity receipt 已扩为 `video_review` / `video_revision` / `component` / `sfx_search` / `sfx_import` 五类白名单，live 与历史共用解析并由原 `WorkSegmentRow` 展开；read-span settle mirror 保留 receipt，revision 与 component 继续走既有 video 活动持久化。SFX 新候选写 `sfx_set` 并保留旧 `set` 读容忍，搜索/导入进入普通 read Activity，provider 搜索失败不再落成成功态；候选、CC0 导入、SourceSnapshot 与原生音频修订仍走原链。公共 design/revise 已接 component 证据与准确 runtime 观察，工具描述和 prompt 已补 component 选择、TSX 修订、旁白与固定媒体边界。公共设计失败预算已覆盖 `design_storyboard` / `design_video`（相同失败第二次停止，不同失败第三次停止）；MG 原文校验返回首处非空白字符差异，storyboard observation 增加确定性末帧 active clips，工具描述明确 Scene-local MG 与 program/component 6 秒上限。统一嵌套 LLM 总预算与共享墙钟仍未实现。公共剧本只增加 receipt 形态门，未新增依赖 provider key 或 runner 的默认剧本。未改 Run、renderer、授权、计费、打字机或交付主链；component bake 仍默认关闭，等待已验证隔离 runner。

上述集成改动仍需当前 `test/core`、Web vitest、tsc 与相关真实旅程复验。用户已实测 MG 设计/文字修订、SFX 搜索/导入及授权制作成功；`review_video` 的 Worked/receipt 已真实出现，但最终续答 provider 失败曾落入通用澄清，当前已落码为按持久化报告摘要、发现和检查范围收尾，并补非流式 tool 续答错误日志与 trace。后续复验取得真实 MiniMax 402 `insufficient_balance_error`：首轮 Chat 未执行，没有新报告；当前已改为无报告时直达本地化 provider 失败帧，402 不再重试。用户随后确认真实审片最终正文已恢复；刷新回放、浏览器试听和 component bake 仍未验收，付费制作的其他作品覆盖不由此扩张；全部剩余出口归新合同。

#### 4.1.1 SFX：检索、试听、固定资产与原生音频修订

SFX 复用现有 `AudioObject`、audio/effect Track、SourceSnapshot、1× source window、通用 move/trim/delete、video-spec 和 renderer。**禁止新增 SfxObject、第二音频 spec、SFX Run 节点或 ASR 处理任务。**行为参考固定为 `vibe-motion/sound@85a3715fc3ec7d1e765e4960643dcbacbc22f8dc` 的查询、许可证筛选、少量候选、试听、下载和署名思路，但不复制其无 LICENSE 代码、HTML 爬虫、home cache、代理脚本或默认任意许可证策略。

1. **Provider 与候选**
   - 新增 `apps/api/app/providers/freesound.py`：有界 HTTPS、超时/重定向/大小限制、typed response、精确 CC0 复核；正式接入优先官方 API，预览/原音的使用条件在上线前核对。
   - 新增 `apps/api/app/tools/video/sfx.py`：provider → 候选领域映射，默认三个可播放候选；保存 provider id、标题、作者、真实时长、来源、许可证和 query。元数据排序不等于 Agent 已试听。
   - 配置只进既有 `config.py` / env 示例与部署配置，不新增配置系统。
2. **Chat action 与候选回放**
   - 新增 `search_sfx` / `import_sfx` 两个非 terminal Chat action，在 `chat/turn_tools.py`、plan/propose 双路径和共享 video seat 接线；不进入 DAG `TOOL_REGISTRY`。
   - `search_sfx` 经现有 `assistant.candidates` + `candidates_log` 发出 `sfx_set`，不读写 `exploration_rows`，不新增候选查询端点。候选完整事实随消息持久化，live 与刷新回放一致。
   - `import_sfx(candidate_set_id, member_index)` 从当前 project 的持久候选解算，重新校验 owner/CC0 并有界下载；LLM 不能提交任意 URL。
3. **固定音频资产**
   - 选中后创建 user-prefixed AUDIO Asset，真实 duration/content hash/origin 完整，出生即 COMPLETED，不请求 ASR；复用 `snapshot_audio_asset` 和 editing SourceSnapshot 登记。
   - `Asset.meta.origin` 保存 provider、源 id、候选/query、source URL、作者、许可证、署名和 retrieval time，冻结时传入 snapshot。重复选择同一候选幂等；Asset 与 snapshot 在后续修订可读取前提交。
4. **公共音频修订**
   - 在公共修订模型增加 `add_audio` / `update_audio`，由 `editing/service.py` 翻译为现有 `BindSource` + `AddTrack` / `AddClip` / `UpdateClip`。同批新 snapshot 的 digest 与完整候选校验必须连续可用，store 仍作 owner/digest 最终裁决。
   - add 接受 snapshot、输出起点、可选源起点/时长/gain，默认使用真实完整时长，不静默循环、拉长或裁短。update 可替换 snapshot/gain，保留稳定 clip/object id 和输出窗；新源不足即冲突。后续 move/trim/delete 复用通用时间内核。
   - 模板默认 SFX 是固定平台资产 + 声明 cue，不在每次制作时重新搜索。cue 按归属 Scene/Clip 参与时间联动；用户明确关闭声音不得被默认值重开。launch-film 首批只补实际镜头需要的 cue，不建设通用音效 DSL。
5. **制作与验收**
   - produce/render 不改主链，固定版本、音频 bytes/digest 与 execution manifest 自动延续。probe 的音轨存在性不代替 cue 时点、非静音、峰值、旁白可懂度和完整试听。
   - 覆盖 provider CC0 映射、候选归属/回放、导入幂等/provenance、add/replace 源窗、stale base 和一条真实「搜索 → 试听 → 选择 → 落轨 → 移动/替换 → 制作」旅程即可，不扩写全供应商故障矩阵。
6. **声音工程收口**
   - 固定资产时记录真实时长、sample/RMS 峰值与音源内部峰值时间；语义动作峰不能机械等同全文件最大峰。cue 由目标动作帧 − 音源峰值滞后 − 当前渲染管线实测输出偏移解算，源分析与输出偏移分开保存，禁止照搬外部仓库的 1.28f 常数。
   - 输出偏移按 Remotion 版本 + codec + sample rate + container 测量；用 2–3 个尖锐 cue 对最终 MP4 做归一化交叉相关，目标残差 ≤0.5f，未测或超过容差不得声称音画同步通过。片头无法完全补偿的 cue 明确记录。
   - 当前 renderer 的 loudnorm 只是处理步骤，`review_video` 另记录实际 integrated LUFS/true peak、归一化状态与削波事实；有旁白时音乐 gain 关键帧避让语音，完整试听仍不可替代。

#### 4.1.2 完整 Remotion 工程 Generator

当前代码的单组件来源与上游 bake 接缝使用 `remotion-project` producer，bake 默认关闭且真实验收未完成。后续不再以单组件为创作上限：完整工程仍使用同一 producer，允许 Agent 按真实内容编写多文件、多组件、共享 helper、Composition 注册与内部时间线，经隔离 runner 固定生产；外部参考源码仍不直接执行。

命名迁移、完整工程来源、隔离 runner、许可成本、预览/修订与真实 Output 的统一施工归 [宣传视频核心 Skill 与渐进式 Skill 包](skill-package-promo-video.md) P0/P3。该合同同时承载内外置 Skill 的渐进读取与全能力 arc 修订；旧单组件扩展不再另起平行计划。P0 命名迁移已落码；旧名只保留于历史实现证据与持久化版本读兼容，完整工程仍未实施。

#### 4.1.3 NarrationAlignment：完整对齐事实、Agent 语义与词锚

数据结构与 READY 冻结合同唯一事实源 = VIDEO_PROJECT §6.4.1。本批必须完整实现 sentences、words、文本范围、整数 start/end ticks、anchored/interpolated 与 Agent semantics，不能用一句 ASR transcript 或供应商句级字幕代替。

当前实现状态（代码实现 + 一次最小真实冒烟，完整验收仍待用户）：已有录音 → 完整对齐 → Agent 语义 → READY → 原生设计/指定词锚的最小闭环已按下述 1–3 接线，已固定 TTS 原件也可复用；源对齐 source window 与词锚统一按绝对源时间量化后取 Clip-local 差值，排队期间 ASR provider/model 漂移会失败闭。migration `c7e2a5f9b413` 已应用为当前 head，相关 compile/import 通过。正常 Chat plan/Start 的新 TTS 冒烟 Run `f69a5959-40c3-41bc-a06b-2f7eb51c3447` 报价 36、实际 34 个 `tts_chars`，产生 VideoNarration `6e9ab624-eb12-437a-82fb-bfcee33be0d7`、AUDIO Asset `9e00e236-9c4e-49b6-ae93-b32d36663437`、SourceSnapshot `cccf1c93-c047-5958-b0e3-c95f8d4e96ab` 与 NarrationAlignment `76d74543-066d-4f90-8b68-d6a17e2f1184`；该 Run 无 CompositionVersion、render、视频 Output 或 `film_seconds`，Chat delivery 持久化 `output_refs=[]`。ALIGNED 经 Agent 完整句级语义进入 READY 后，保存 CompositionVersion `0b6cdb84-d22c-4bc6-8529-3c2897d83b56`；“清晰”两字分别锚定真实 `w000001` / `w000002`，只读 video-spec 编译得到 Clip-local 整数帧，且不含 alignment/provider/model。后续 Chat 的 Run 状态读口已补当前 alignment id/status，Activity、音频、delivery 与分镜刷新可读。固定录音与全新 TTS 两条输入的 READY、设计和正式 Output 真实证据归 §4.1.6；当前完整真实旅程与用户连续视听未执行，不能据此关闭新合同中的其他出口。

1. **持久化、迁移与准备队列**
   - `models/tables.py` 新增 `narration_alignments` 与 Alembic migration；保存 owner、audio_snapshot、精确 text/digests、算法与归一化版本、payload、lease/error 和 PENDING/PROCESSING/ALIGNED/READY/FAILED。使用 String 状态列，不建 PG ENUM；READY 与已被引用行禁止 UPDATE，文本/音频变化只创建新行。
   - 新增 `tools/video/alignment_store.py`：请求去重、owner/digest 校验、独立短会话、lease/claim token、终态写与恢复。`app/worker.py` 增加第五认领源，只处理 PENDING；ALIGNED 等语义、READY 供作品引用，不重复认领。
   - 新增 `tools/video/narration_alignment.py`：从固定音频和精确文本产生完整对齐。优先复用现有 faster-whisper AUDIO 处理事实，脚本约束映射、插值和覆盖率均由确定性代码完成；外部 aligner/model 只有在许可证与部署边界核对后才能成为另一 provider，不复制 video-talkcraft 非商业代码。
2. **旁白准备与 Chat 工具**
   - 新增 `prepare_narration` / `get_narration_alignment` / `annotate_narration` 三个普通 Chat action，经 `POST /chat`、turn_tools 与共享 video seat 接线，不新增意图端点。长任务只由 worker 执行；Chat 侧有界等待、Activity 和失败事实复用现有协议，禁止 FastAPI BackgroundTasks。
   - 已有录音由用户明确 @ AUDIO 资产并提供最终讲稿；TTS 由 Agent 提供最终讲稿、voice/language。Chat seat 对 TTS 只做只读 cache probe：已有固定原件时复用普通 AUDIO Asset/SourceSnapshot 登记；缺失时呈现恰好一个同名 `prepare_narration` task，经现有 `production_intent`、auto/ask、费用守卫和 Start 授权，不在 Chat 工具直接调用 MiniMax。
   - narration-only Run 只允许一个独立根节点，复用 `create_run`、worker、`prepare_speech_media` / `narration_store` 与普通成功步 `capture_step`。报价只计一次缺失的 speed-1.0 原件 `tts_chars`，Start 重算缓存，命中为零；不得计入 `film_seconds`，不得给 `produce_video` 加 skip flag，也不得扩展成通用无 Output 执行框架。执行不保存 CompositionVersion、不创建 render/Output，保留 VideoNarration 占位、固定原件恢复、实际 `record_media_usage` 与未知结果失败闭。
   - Run 终态仅在这个显式 scope 复核已完成的 Output-free step、owner 一致的 AUDIO Asset/SourceSnapshot、同文本/音频 digest 的 NarrationAlignment 与已结算实际用量；其他 Run 的零 Output 规则不变。Chat delivery 持久化空 `output_refs`，只叙述真实音频与当前对齐状态，不展示视频卡或宣称成片；对齐 FAILED 只能部分交付，事实不一致不得报收成功。
   - `annotate_narration` 只在 ALIGNED 接受完整句级 semantics，服务端验证 role/weight/needs、entities 和 emphasis_word_ids，禁止修改文本/ticks。全部必需句标注完成且 digest 重算后才 READY；任一句仍 review_required 就保持不可引用，不能用确认或标注补造时间。`get_narration_alignment` 返回真实状态与完整只读结构。
3. **版本、导演与编译**
   - `editing/alignment.py` 实现纯 Pydantic 模型、payload canonical digest、锚点解算和文本/audio 失效规则。`editing/schemas.py` 给 SpeechObject 增加可空 alignment ref，给 Animation 增加可空 NarrationAnchor；源对齐 SpeechClip 必须绑定对应音频快照，普通固定切点 MG 保持现有字段默认与行为。
   - `design_video` 接受 READY `narration_alignment_id`，Director 读取句/词与语义后选择 Scene、Clip、Preset 和 Generator；代码负责把 emphasis/指定词锚解算为实际帧，LLM 不写近似秒数。普通 `narration` 参数与 fixed-cut 路径不变。
   - `editing/video_spec.py` 只输出最终整数 keyframes、普通 audio 与派生 TextClips；NarrationAlignment/provider/model 不进入 video-spec。派生字幕可消费同一 READY 对齐，手改字幕独立规则不变。
   - 源对齐 Speech 通过完整所属 Clip 修订；文本/媒体更新必须先准备新对齐。确定性时间平移保留并重映射 anchor provenance，Speech time_map/rate 继续能力拒绝。不得将旧词锚静默套到新文案。
4. **本批出口**
   - 纯测试覆盖中英文、CJK 逐字、Latin token、数字、标点、重复词 occurrence、插值标记、低覆盖、非单调/超窗、digest 失效、owner、幂等、lease 恢复和 READY 不可变；锚点找不到/歧义必须报错，不得返回 0。
   - 真实验收至少一条已有录音 + 精确讲稿，以及一条授权 TTS 准备：证明最终讲稿/音频 → 完整对齐 → Agent 语义 → READY → 指定词触发 text-impact → 保存版本。完整知识讲解 Output 归四类 Skill 集成，不在本批提前宣称。

#### 4.1.4 原生文字与十六个分类代表 Preset

高频视觉丰富性由 `editing/presets.py` 的 `PRESET_REGISTRY` 和确定性展开函数提供。Preset 在保存版本前展开为普通 Tracks/Clips/Objects/Animations，renderer 不查注册表；**不新增 Object kind、React 组件运行时或第二套组件 DSL**。复杂且无法预设的画面仍归 `remotion-project`。

首批从真实四类视频的高频语法分类选代表，不照搬外部 124 张镜头卡，也不把所有视觉效果都误做成同一种 Preset：Camera/Scene/Clip 运镜与转场仍归镜头方法，真实网页交互状态归 CapturePlan，媒体变速/定格归通用时间内核，自由 3D、复杂形变与内容特定画面归 `remotion-project`。后续按真实作品缺口扩类，不建设通用插件市场。

1. **文字基础平价**
   - `TextStyle` 增加结构化描边颜色/宽度与阴影颜色/offset/blur，禁止任意 CSS 字符串；`update_text`、Python/TS video-spec、Preview/Render 同步支持。胶囊继续使用 ShapeObject 圆角矩形 + 原生文字，不为单一参考片发明新 Object。
   - 增加一份许可证清晰、内容寻址的 Noto Sans SC Black/Heavy 字体与 digest，开放真实 900 字重；旧版本继续引用旧 font-set digest，不静默改变历史渲染。
2. **十六个内置 Preset（当前已全数落码并完成代表证据收口）**

   | 分类 | id | 原生展开与用途 |
   |---|---|---|
   | 文字与字幕 | `caption-phrases` | 按句/短语生成定时原生字幕；可选 NarrationAlignment cue，保留手改独立语义 |
   | 文字与字幕 | `text-reveal` | line/word/grapheme 的 opacity + blur + position + stagger，覆盖汇聚/散开等可参数化入场 |
   | 文字与字幕 | `text-impact` | TextPart 的 scale + opacity + 短 blur + 落地位移，适合具体词锚砸字 |
   | 文字与字幕 | `typewriter` | 原生 TextPart 按 grapheme 有界显现，可选光标 Shape；不是逐帧烘焙文字 |
   | 文字与字幕 | `keyword-fill` | 指定 TextPart 的颜色/描边/字重随词锚或关键帧切换，其他文字保持不变 |
   | 文字与字幕 | `word-cycle` | 同一槽位的 2–5 个原生词纵向轮换/模糊切换，支持槽位尺寸稳定与词锚 |
   | 文字与字幕 | `claim-layout` | 多行大字与关键词强调的原生 stacked/split 两种版式，错峰入场并保留落定 hold |
   | 标注与信息结构 | `highlight-sweep` | 文字背后的 Shape 宽度 0→1，文本保持原生可改 |
   | 标注与信息结构 | `path-underline` | ShapeObject.path 的 `path.reveal` 0→1，支持下划线/手绘标注 |
   | 标注与信息结构 | `callout` | 原生标签、胶囊与指引线组合入场，用于真实媒体或网页元素旁注释 |
   | 标注与信息结构 | `flow-steps` | 2–5 个原生节点、连接线与有界 stagger，表达流程/因果 |
   | 标注与信息结构 | `comparison-columns` | 两栏面板、标签与条目的错峰 reveal，表达对比 |
   | UI 与图文编排 | `card-stack` | 2–6 个真实图片/网页视图或原生卡片的堆叠、发牌与 spring/overshoot 落定 |
   | UI 与图文编排 | `list-reveal` | 2–8 行原生条目错峰入场，可选勾选状态；内容来自真实输入，不伪造功能完成状态 |
   | UI 与图文编排 | `notification-stack` | 2–5 个原生通知/事件卡依次叠加与收拢，适合活动流表达，不冒充真实产品通知 |
   | 开场与收尾 | `title-lockup` | 标题、辅文、可选品牌 Asset 的原生组合与收拢落定，复用于开场标题卡和结尾落版 |
3. **渲染与修订**
   - `path.reveal` 只接受 ShapeObject.path 和 0..1 数值，Python/TS 共用量化与 golden fixtures；Remotion 以 SVG pathLength/strokeDashoffset 实现。当前没有独立原生 PreviewAdapter，关键边界以同一 evaluator/Remotion Video 的 renderStill 与 MP4 对照，不把共享实现称为双实现 parity；path 数据不变成 renderer 代码。
   - spring/overshoot 使用既有可序列化 easing/keyframes 与有界参数，不把物理引擎或运行时插件带入 spec。涉及真实网页/图片的卡片、列表只引用已冻结 SourceSnapshot；需要真实选中/after 状态时先走 CapturePlan，Preset 不得编造状态。
   - 每个 Preset 接受真实文案、布局和可选 NarrationAnchor；文本变化重新派生 TextPart，旧锚点/动画无法可靠映射时明确冲突。`revise_video` 仍走唯一写口，Preset 在版本出生后不成为隐藏依赖。
   - 十六个 Preset 各有代表性动态帧/参数修订证据，整组另验证描边阴影、900 字重、path reveal、词槽稳定、卡片层序与落定 hold 的 preview/render parity；不能只证明 schema 能保存。

**当前落地与统一收口证据**：`PRESET_REGISTRY` 恰好十六项，十六个代表参数均通过“确定性展开 → 完整候选校验 → video-spec 编译”，只产生普通原生对象与整数关键帧。三条保存后只读渲染的矩阵版本为文字 `4d225402-d512-4a0d-a4b5-07dda86caba3`（600 帧）、信息结构 `caf1e05a-9b0f-450b-b89d-e44cde9a65fd`（600 帧）、卡片/落版 `3923f807-5ddb-48c0-972f-d83f32770001`（480 帧）；实际 MP4 的起始/中间/落定帧覆盖其余十四项，caption-phrases/text-impact 复用上一批 Output `2ca59717-0d26-4493-b817-1374be51687d` 的实际帧。stroke/shadow/真实 900、path.reveal 部分与完整路径、word-cycle 词槽、card-stack 层序/1.08 overshoot 和各入场 Preset 的最终 hold 均已放大核对，四条本地 MP4 均通过现有 render probe。

十六项均经现有 `revise_video` → `apply_composition_edits` 完成一次代表局部修订：base_ref、不可变新版本、系统 change_set、未改 Clip 和 Clip/Object id 保持已核对。typewriter 改文案后完整重派生 grapheme targets；手改字幕转 independent 后保留可证明的已展开普通动画并移除旧词锚 provenance；删除目标词与无法可靠映射的重复词均拒绝且 head 不动。真实 Chat 在两轮内先完成标题文案/900，再将零值 stroke/shadow 对象显式修成 null，最终 CompositionVersion 为 `2d076994-465a-4ddf-9666-eb16b9bce420`，零新 TTS、Run、Output；该版本另完成一次 114 帧本地 render/probe，既有音轨可解码且非静音。旧 Composition `1896a973-9081-4887-9fdb-f862043db2c9` 的 current version 仍为 `0b6cdb84-d22c-4bc6-8529-3c2897d83b56`。

关键 Preview/Render 边界完成了 71 组矩阵 + 8 组 Chat 修订版的同版本/同帧 renderStill 与 MP4 对照；矩阵平均 MAE 约 0.420、最大约 0.568，修订版平均约 0.422，差异符合 H.264 编码噪声。当前没有独立原生 PreviewAdapter，这些只证明共享 video-spec evaluator/Remotion Video 的 still/MP4 一致，不冒充双实现 parity。57 个定向纯测试、11 个 video-spec golden、Python compile/import、两处 TypeScript 与四条 probe 通过；当前 `test/core`、真实旅程和浏览器矩阵未运行。完整连续看片、独立试听、已有录音准备及四类用户手测仍留后续阶段，本批不代表 Gallery 或四类产品通过。

#### 4.1.5 CapturePlan：两阶段网页采集与真实页面状态

领域合同唯一事实源 = VIDEO_PROJECT §9.2。本批保留现有侦察采集，不推倒 `_PolicyProxy`、SSRF、字体/图片等待、弹窗处理或 SourceSnapshot。

1. **CapturePlan 与现有队列**
   - 在 `tools/research/capture.py` 增加 typed CapturePlan、动作/制品校验与 `capture_shots(plan)`；允许 `click/fill/hover/scroll/wait`，禁止任意 JS、登录、凭证、表单提交、购买/删除、外站导航和无界等待。
   - `pipeline/web_capture.py` 检测 Asset.meta 中经服务端生成的 CapturePlan 并调用 `capture_shots`；没有计划的 Asset 继续 `capture_page`。`tools/video/design.py` 只在选定网页镜头后创建最终采集 Asset 并有界等待，复用现有 WEB_PAGE 预处理认领源，不新增 scheduler。
2. **状态、坐标与图层**
   - 每个状态从干净 baseline 执行动作并 settle，随后重新获取 full/view、page height、目标 boxes 和 cutouts。`blank_plate` 与 populated view 必须同状态、同坐标，使用 `visibility:hidden`；普通 2×，仅指定 hero 可有界 4×。
   - `tools/video/preparation.py` 把 populated/blank_plate/cutout/hero 冻结为独立 web views，保存 state_id、artifact role、配对 view、route/action provenance、CSS/pixel boxes、digest 和选中区域正文。所有网页栅格层由 WebObject + view_id 引用，ImageObject source-kind 规则不变。
   - `editing/grounding.py`、storyboard 和 validator 校验 state/element/artifact 引用；必需制品缺失即设计失败。Director 不得把装饰性合成选框当成真实 after/selected 状态。
3. **首批三个真实出口**
   - 选中状态特写：指定 state + element 的真实 focus；
   - 交互前后对照：同布局 before/after WebObjects + crossfade；
   - 空底板 + 元素入场：同源 plate 与 cutout WebObjects + 原生动画。
   - 至少一条真实公开网页旅程同时验证长页选中区域正文、交互后坐标重测、刷新回放和最终 Output 状态保真；不做全站爬虫、通用 3D PageCam 或复杂录屏。

当前实现座位已经接齐：`capture_director` 只选择真实侦察快照中的 source/target/state/action，`bind_capture_plan` 冻结来源身份、selector 与三镜头必需制品；最终采集经 `create_capture_plan_asset_committed` 进入既有 WEB_PAGE 队列，由 worker 的 `web_capture_processor` 执行，再由 `snapshot_web_asset` 冻结独立 web SourceSnapshot。`editing/web_shots.py` 把同一快照的 selected/before/after/plate/cutout 展开为普通 Scene、WebObject、centered crossfade 与原生 Animation；`validate_content` 在保存前检查全部必需制品、配对、动作、坐标、digest 与区域截断事实。没有新增表、scheduler、Object kind、video-spec 网页字段或 renderer 分支。

真实公开 shadcn Tabs 页面已完成同一正常 Chat → 首稿完整呈现/ACK（`run_id=null`）→ 下一轮制作话 → `create_run` → Output 闭环。Project `e44c0f21-02d8-4b7f-b2a3-7bd64a593b83`；侦察 Asset/SourceSnapshot = `4a338646-1c76-4ca0-9d06-0f8ab980b60a` / `57dd29dd-b325-5264-98be-5cb6cd0e2f4c`；最终 CapturePlan Asset/SourceSnapshot = `3c947813-8376-4e33-b50c-dee90ced4927` / `48b06f40-cc0d-54c6-b706-6d61436376dd`，plan digest = `b052afa1d61354b0df78d9ac11a20b6336da7c2fb7b1e2fccdb324da42039dbf`；CompositionVersion = `4beb051e-6bfc-495d-821e-d6436aa0ee2b`，Run = `eea9a0ac-c60f-4389-b24b-bcf9dab6c982`，视频 Output = `b9c67f57-1862-4445-8ce7-c072bce47d70`。最终 worker 采集 8/8 必需制品；before/after/selected 均从独立干净 context 重放，after 与 selected 动作一致。真实区域正文分别为 Overview 与 Analytics，页高 4589 CSS px；动作后目标盒独立重测为 CSS `(520,396,400,174)`，两个区域正文与视觉截断事实均为 false。

交付 MP4 的实际帧已解码并目视核对：selected 为真实 Analytics 特写，before/after 为真实 Overview→Analytics，0.6 秒 crossfade 中点为两态真实混合，plate 起始为空、cutout 以原生 opacity/position/scale 入场并落定。像素 MAE：plate 起始 vs blank plate = 0.341，plate 落定 vs selected view = 0.804，crossfade 中点 vs 按真实进度混合的 before/after = 0.419。真实 Chrome `ignoreCache:true` 硬刷新前后只保留同一交付卡；Asset/SourceSnapshot/版本/Run/Output id 集合均不变，没有重新采集或重启制作。证据在 `scratch/d5-capture-plan/live-journey/`。142 个聚焦 pytest 通过；当前 `test/core`、完整真实旅程、连续看片与独立试听未运行。此出口只证明本批三种限定镜头，不声称任意网页交互、复杂录屏或完整 Gallery 已通过；可进入下一批 Chat-tool UI / 内置 Skill / Home 集成。

#### 4.1.6 内置 Skill 与 Home Gallery

固定与自由创作都直接从普通 Chat 开始；Demo、Home 预填与 `/任务名` 只是可选快捷起点。固定风格必须由视频 Skill chip + 可编辑 prompt 确定性绑定，不能只靠提示词猜测。所有 Skill 都复用 launch-film 已建立的 `SKILL.md + 可选 video-template.json + 代码展开 Preset` 形态，不新增 StylePack 作品层。

**当前集成事实与验证边界**：四个内置包已登记为 `launch-film@1.4.0`、`talking-head-video@1.0.0`、`text-animation@1.0.0`、`knowledge-explainer@1.0.0`；picker、React/DOM chip、历史回放与无网络回退共用本地化任务名，服务端内部 id 与 en/zh 别名只作唯一解算。Home 当前直接呈现四产品主 Tab 与八个典型应用子 Tab，主 Tab 短名复用 `skills.builtin.<id>.shortName`，完整 chip 名不变。网站/产品宣传、观点文字片、概念讲解各接入一张上述新链锚片，精确绑定对应 Skill 版本与真实来源 prompt；其余五个应用显示统一空态，旧 Film 与复用占位片不再进入货架。点击与手动 picker 使用同一 reference + 可编辑 prompt，非 Skill Recipe 载荷不变。定向 Web 27/27 与八组真实 Chrome 代表组合通过，24 次样片点击均为零修改请求；证据归 `scratch/d5-home-four-products/`。完整 Web/TypeScript 与正式公开 Gallery 的用户连续视听未运行，四类产品出口不因此关闭。

十六个 Preset 的真实动态预览已从既有验收 MP4 确定性截段，以 `video-presets/<preset_id>/<sha256>.mp4` 发布并由 `editing/preset_previews.json` 登记 digest、时长与画幅；没有生成新 TTS、图片、源视频或 SFX。`show_video_presets` / `select_video_preset` 已接 plan/propose 双路径、既有 `assistant.candidates` + `candidates_log` 与历史回放；展示只接受 2–4 个注册 id，selection 只重绘，设计/修订由服务端解算持久成员后经 `apply_composition_edits` 落版。文字入场 Preset 应用到已有文字 Clip 时替换其旧 TextPart 入场动画，保留 whole-object 动画、文字与其他 Clip，避免 word/grapheme 混合层级。

候选/selection/apply 的限定真实旅程已由 Project `3a1b6107-427a-4362-83f9-839eeefbfc7d` 验证：普通消息“第二个”只选择，`apply_preset` 只生成目标子版本，全程无额外 Run/Output，硬刷新保留 Skill、当前分镜、交付与完整候选；证据为 `scratch/d5-user-entry-journey.json`，该项目及其 Run/Output/Composition 已清理。

文字动画分类锚片使用保留型 Project `e92babc3-2dab-4876-a31b-ce0e31667d67` / Composition `f7341c53-fce8-4d85-bf8a-84159b9ef4c5`，从真实 Home 卡形成 `text-animation@1.0.0` Skill chip + 可编辑 prompt，经唯一 `POST /chat` 完成两版闭环。首版 `5ae73164-0c3f-4e18-87bd-0f8b4260e63e`（digest `bd2bb6049e3f0c39fd11d05db6a30779012f5c949b492b28437af00155891a77`）完整呈现并 ACK，`run_id=null`；下一轮制作话创建 Run `40228d95-b39e-4ee6-99a8-4076c8fd1133` 与 Output `7a9b803d-9b6f-41da-abf7-8ec72e8e2eeb`。普通 Chat 经 `revise_video` 只把第二幕 `Make every idea readable.` 改为 `Keep every idea readable.`，生成唯一直接子版本 `c2df1934-2ace-4b5f-89fb-95e7f9a67f09`（digest `7b770c3105fc9f8324c4198f33a6e11fb026dfdf13aac1546d91356892b1e937`），未重载 Skill、未新增 Run/Output；修订版 ACK 后，下一轮制作话创建 Run `dac4e2d1-bedf-4bec-b0a9-1775909ce97c` 与 Output `c71525b6-1ab3-4ac3-b694-ce84076efe84`，首版 Output 已归档。两个 Run 均钉住各自已呈现版本与 digest。

两条正式 MP4 均为 1920×1080、30fps、360/360 帧完整解码，真实音轨完整；关键词 cue 的归一化互相关为 0.87285，实测动作残差 0.1887 帧。除 `clp_mg_2` 外两个 render spec 的 Clip 全部一致，首末幕抽样像素逐点相同，两条完整音轨的 578,560 个采样完全一致。真实 Chrome 分别播放两个交付并 `ignoreCache:true` 硬刷新；刷新后 Skill chip、两版事实、消息顺序与两个 Output 卡保留，Asset/SourceSnapshot/Version/Run/Output 集合不变。证据归 `scratch/d5-category-anchors/text-live/`。修订版已按内容寻址 key 上传并登记为 Home 观点文字片开发/手测样片；用户连续动态观看与实际试听仍未完成，不得称为正式公开 Gallery 验收通过。口播指定 VIDEO 与 SourceSnapshot 的对象均 `NoSuchKey`，仍阻塞，未制作替代样片，两个口播应用保持空态。

产品宣传分类锚片已完成内部双版本、双 Output 制作/修订与确定性复验，修订版已作为 Home 网站/产品宣传的开发/手测样片；用户连续看片、实际试听和正式公开 Gallery 验收仍是分类出口。保留型 Project `b8b20d17-28eb-4c60-8656-d937f2593f56` / Composition `8e3b6d3b-a3b6-444a-80f9-54fa32fff5b6` 从真实 Home Product Promo 卡进入，经唯一 `POST /chat` 绑定 `launch-film@1.4.0` / template 2。首版 `3484519b-72ca-4d06-b924-e4414896e2e8` 完整呈现并 ACK（`run_id=null`），后续独立制作话创建 Run `79b8769d-ee4f-488f-8a17-3e06c7632093` 与 Output `8a8f6095-6ae8-49f9-8f2b-ab6cae59a9cc`，Run/Output 均钉住首版 digest。同版包含真实 AgentVeil OG ImageObject、多个独立原生文字、披露来源的既有 TOS demo VideoObject（精确 22–30 秒源窗且原声 muted）及最终 CapturePlan WebObjects；最终快照 `42e7d05a-8b8e-5c57-8a4b-87bc0460ad45` 的 selected/before/after/blank-plate/cutout 都进入实际交付帧。

首版 MP4 已完整解码 3482 帧并逐幕查看 21/21 Scene；唯一一次 exact-Output `review_video` 持久化 16 张实际采样帧和全流音频检查，零新 Run/Output。审片关于 reveal/proof/product-video 错位、标题缺失和 plate 不可辨识的语义发现经同号 JPEG ↔ PyAV 帧对账判为误报，原报告与裁决均保留，未用于修订。首设计回合曾偏离固定资产要求调用一次 `search_sfx`，但未导入或下载候选，保存版只使用声明的固定 CC0 SFX；现已在 plan/propose 两路径增加基于当前用户消息的服务端搜索准入，固定资产声明与禁止搜索表述不会调用 provider。该修复只有准入/装配纯测试证据，未另跑付费首设计。

正常 Chat 修订只执行一次 `revise_video → focus_web(clp_chapter_4_walk_web, s4e0)`，生成直接子版本 `91c7d379-df3b-4076-9881-8978e8ec5000`（digest `084f0dff096351711a8070949c985a9b71e99f71361ece0f1f4f75f612655fd3`），完整呈现并 ACK 时没有新增 Run/Output/Asset/SourceSnapshot。系统 change_set 仅含目标 Clip 的 `animations`；两条既有 scale/position 动画 id、全部 Clip/Object id、文字、素材、网页状态、源窗、音乐、SFX、gain 与 cue 均保持不变。后续独立制作话创建 Run `04ad180c-8f1f-4903-9b5e-49b779ded684` 与 Output `cf91834d-8bc3-40e8-821d-92c5e5e961e3`，二者钉住已呈现 v2/digest，未重跑 `review_video`。首版 Output 按现有生产链归档但未删除，仍可与当前 v2 一起回放。

两条正式 MP4 均为 1920×1080、30fps、3482/3482 帧完整解码。v2 第四章实际解码帧 1642/1761/1880 均恢复页面标题及 Solo / Team / Enterprise 三卡；render spec 只有目标 Clip 改变。60 个非目标采样中 58 个逐像素一致，其余两个仅是距目标 Scene 采样边界五帧内、MAE < 0.01 的视频编码依赖差异。两版原生双声道每声道 5,573,632 个采样帧逐值一致；v2 原生 RMS -18.011 dBFS、sample peak -1.398 dBFS，FFmpeg 实测 -15.85 LUFS / -1.39 dBTP，零 clipped channel samples。首版旧 `+1.27 dBFS` 是 stereo→mono 的 `1/sqrt(2)` 声道矩阵增益造成的测量伪影，不是真实过峰；`inspect_output_audio` 已改为原生 planar 多声道测量，并有双声道回归测试，因此未借修订降低 gain。固定点击音峰值到动作残差约 +0.189 帧、归一化互相关约 0.598，两版一致；这些信号测量不等于实际试听。

真实 Chrome 分别播放两个 Output，随后 `Page.reload(ignoreCache=true)`；两版均实际前进到约 2.63 秒、readyState 4，硬刷新后 Skill chip、首条 prompt、两版事实、消息顺序与两个 Output 卡保留，Asset/SourceSnapshot/Version/Run/Output 集合不变。证据归 `scratch/d5-category-anchors/product-live/`。修订版已按 `demo/outputs/product-promo-agentveil-the-next-move-a2a4b391.mp4` 上传并登记 Home；用户连续动态观看、实际试听与正式公开 Gallery 验收仍未完成。

知识讲解分类锚片已完成内部双版本、双 Run、双 Output 全旅程，修订版已作为 Home 概念讲解的开发/手测样片；用户连续看片、实际试听与正式公开 Gallery 验收仍是分类出口。aligned 与 program Director 现在共同包含 `prompts/_draw_2d_contract.j2`，完整声明 draw-2d 的 `ctx`、逐命令字段和严格边界；Rect 不被描述为支持 stroke/corner，schemas 与静态结果拒绝均未放宽。真实 assemble 对账、合法 fixture 的 schema→展开→实际 Node 执行→固定媒体编译，以及非法 Rect 在保存媒体/版本前被拒绝，共 3 个合同测试通过。修复后正常 Chat 共五回合：首版设计、第一次制作、exact-Output 审片、Generator-only 修订、第二次制作；首版与修订版均先完整呈现并 ACK，制作只在后续独立消息发生。

保留型 Project `0d6104fd-05d0-4029-a1e8-9c193450495e` 中新建 Composition `d42d7f8c-4390-440b-af42-0b813cd9c4ef`。首版 `2d7337c7-57e4-4a55-949f-67d93627c9cc`（content digest `30198dd2587f101fd43454c19e1bf2eeb4d0d8f1e88166a0e31bb2eb30d5b524`）经 Run `0d7379fa-3f1d-4b4c-a9d9-093449d00a5e` 交付 Output `cfb62030-f833-4948-a34a-7e28d568dd0f`。修订只把 `clp_aligned_1_generator` 的 `source_node_count` 从 24 改为 16，生成直接子版 `866b194d-ea31-4c01-af2f-5f17163e5af6`（content digest `0ddaaa28a6c18eec0120530916556fdaf26fe19c370c59ec8a13b6aabd9ac608`），没有修订回合 Run/Output；ACK 后经 Run `9d3a3bb6-8a82-4ae5-be36-cd9ef4011927` 交付 Output `2b791e37-3290-499e-a88f-c83323354911`，首版 Output 只在此时归档。Generator program digest 分别为 `dbf396d7ef25b4dfab351b660043b6a03497721982a4e0a710884dd8d811688d` 与 `2b02ec9612c598e927d9de3974303a5faf19b61430f40be460dee4dfb9eeb11f`；render spec 除目标 Generator Clip 外全部一致，讲稿、固定 AUDIO/SourceSnapshot、READY alignment、原生字幕、标题、音乐及其他 Clip 未变，最终 video-spec 不暴露 drawing-v1/React/Remotion。

两条正式 MP4 均为 1920×1080、30fps、114/114 帧完整解码，实际 Scene 与“清晰”词锚帧已查看：`清` 在帧 0 隐藏、帧 4 落定，`晰` 在帧 7 隐藏、帧 11 落定，v2 保持相同节奏。一次 bounded exact-Output `review_video` 的帧 0 透明起点经同号实际帧判为文字入场而非缺陷；帧 13 标题与 Generator 网格拥挤确认存在，v2 实际帧显示减轻但未完全消除。两版原生双声道 185,344 个采样帧逐值一致，v2 实测 -16.03 LUFS / -2.12 dBTP，固定语音归一化互相关 0.998829；生产均为 `speech_media={}`、`max_tts_characters=0`。真实 Chrome 在共享查看器中分别播放两个精确 Output 到 1.69/2.07 秒，readyState 4、1920×1080，随后 `Page.reload(ignoreCache=true)`；Skill chip、首条 prompt、两版事实与消息因果顺序保留，Asset/SourceSnapshot/NarrationAlignment/VideoNarration/Run/Output 集合零增长。证据归 `scratch/d5-category-anchors/knowledge-live/`。修订版已按 `demo/outputs/knowledge-explainer-clear-expression-73f4a743.mp4` 上传并登记为 Home 概念讲解开发/手测样片。两条历史回复原文保留：首版交付误称未加背景音乐，修订回复误报其他参数与颜色数量。真实 payload/版本/工具观察回放后，前者归因为 Video 交付事实装配缺少音乐轨投影，现由 `run_review` 从实际 video-spec 的 music role Clip 提供三态事实；后者是模型从 delta 与旧读数估算未改总数，现仍在同一 REVISION 法座位明确“没有当前保存版读数就不报未改参数/颜色总数”。未新增观察言语草稿、第二法座位或硬编码回复，也未为文案另跑付费回合。用户连续看片、实际试听、残余拥挤的主观验收与正式公开 Gallery 验收未完成前，不视为公开验收通过。

全新模拟知识文字稿链已在保留型 Project `e9b1bcdd-17a0-4ff5-8890-00a52b30ef1e` / Chat `31fc2b89-e0e2-4c0b-9bc7-e6ffacf342c1` 完成集中预跑。首条消息只携带 `knowledge-explainer@1.0.0` Skill 引用、明确标注的模拟稿和最终中文 `presenter_male` 旁白准备授权，没有视频、图片、网页、旧音频或旧 alignment；正常意图路由另保存同文 TRANSCRIPT Asset，不是额外外部素材。auto/费用授权后恰好一个 `prepare_narration` task 创建 narration-only Run `8ce195c5-1e12-4657-9138-7aaa129753ec`：报价 58、供应商实际返回并只结算一次 `tts_chars=55`，零 `film_seconds`、CompositionVersion、render 或视频 Output，delivery `output_refs=[]`。固定 AUDIO Asset `ae4bfb7b-35e4-4207-bce5-72bd11384a5f`、SourceSnapshot `7170c0ed-856a-5729-b757-d212b6fadd70`、VideoNarration `cb2f7d69-fa32-4e89-bb38-a40e1dcc2b80` 与 NarrationAlignment `aa086a1d-6861-49da-9a04-35ef00d1785d` 的 owner、精确讲稿和音频 digest 一致，原件 103,668 bytes / 567,380 ticks。Run result 证明 PENDING，worker ASR 日志证明实际处理，随后 DB 为 ALIGNED；中途取证未捕捉到 PROCESSING 的轮询快照，不伪称有该快照。Agent 在普通 Chat 一次性填写整句 semantics 后进入 READY，无第二个 Run；原稿为 29 个 Unicode 字符、26 个真实发声 token。

后续 Chat 从真实 READY id/status 设计并完整呈现 Composition `89e76620-c978-47ee-80d5-0ca362b65d53` 的首版 `2873107e-526d-49d9-a17d-bc55e69c10ab`（content digest `fa7f72fea2cf0da569a45451a05114f2cfd58fb7c03f3d01ac835661a65d2923`），ACK 返回 `run_id=null`。版本钉住新固定音频与 READY digest，原生字幕与模拟稿逐字一致，11 个真实 word_id 展开为 44 条 text-impact 属性动画；逐条对账证明所有起止 tick 等于 READY words 的 Clip-local 解算结果，没有手填秒数。唯一主视觉是 Agent 按“复杂知识云 → 概念/关系/例子 → 听众聚焦”编写的 drawing-v1，固定 media digest `097e2578286a36d1d85078656b3d3514235259daf5481f704447632325f9643c`，未开启 component-v1。独立制作话才创建 produce Run `5b721958-fcb3-4639-96f9-e97235db3b9a` 并交付唯一 Output `dbe0481f-5bd9-4a76-8706-052dc8720099`；Run/Output 钉住已呈现版本和 digest，`speech_media={}`、`max_tts_characters=0`，零新 TTS、alignment、Version 或额外 Output，drawing-v1 按 digest 复用且未重新加载 Skill，最终 spec 无 alignment/provider/model/drawing-v1/React/Remotion 泄漏。

正式 MP4 为 1920×1080、30fps，189/189 帧完整解码；唯一 Scene 的实际帧与 11 组词锚帧均已查看，确认固定主视觉、原生标题和按真实词序出现的字幕。实际帧同时确认大标题与中间 Generator 明显重叠，本批未做第二版或第二次 Generator 修订，保留给用户判断。音轨真实存在且可解码，原生双声道 RMS -18.61 dBFS、sample peak -2.10 dBFS，FFmpeg 实测 -16.03 LUFS / -2.07 dBTP，固定旁白归一化互相关 0.998023；这些不等于用户连续看片或实际试听。真实 Chrome 播放精确 Output 后执行 `Page.reload(ignoreCache=true)`，Skill chip、模拟稿、READY/实际用量、分镜和 Output 保持，Asset/Snapshot/Alignment/Version/Run/Output 集合零增长。视频交付回复与已呈现版本、真实 music role Clip、旁白和 Output 一致。

narration 历史回复把供应商 55 个计费 `tts_chars` 写成“讲稿 55 字”，与 29 字符原稿不符；历史原文未改，也未为此重跑付费回合。根因是交付事实行只给 `tts_chars=55`，现同一 `_narration_delivery_lines` 座位改给 `script_unicode_chars=29` 与 `provider_reported_tts_chars=55`，已对真实 Run 无 LLM 重读验证。完整证据归 `scratch/d5-category-anchors/knowledge-text-live/`；四个 dev 服务的退出自动重启与干净重启动证据归 `scratch/dev-supervisor/`。集中预跑的机制与媒体出口因此完成，用户连续视听、首版拥挤判断、发布授权和 Gallery 上架仍开放。

本批既有完整 API 为 **1566 passed**、完整 Web 为 **397 passed**；Web/renderer/video-spec TypeScript、video-spec 11 项测试与 compile/import 已通过。本次续跑另完成 **67 个定向 pytest**、Python compile/import、`bash -n` 与 scoped diff check；未重跑完整 API/Web 套件，亦未因无 Web/renderer/spec TypeScript 改动而重跑 TypeScript。三条既有锚片各完成八组真实 Chrome 代表组合，覆盖 desktop/mobile、en/zh、light/dark、普通/reduced-motion、精确当前 Output 播放、归档/当前版左右键切换、Escape、可见焦点与 `ignoreCache:true` 硬刷新；24/24 通过且三类实体集合均零增长，证据归 `scratch/d5-category-anchors/browser-matrix/`。共享 `MediaLightbox` 关闭后焦点曾落到 `BODY`，现由 base-ui `finalFocus` 接收关闭时保留的当前 Output slot，已包含在上述回归中。全新知识文字稿链已按上段取得独立 Run/READY/版本/Output、完整媒体与真实 Chrome 硬刷新证据，集中预跑机制与媒体出口完成。`scripts/dev.sh` 的 API、worker、render、Web 退出自动重启均已逐一实测，完整重启动与 macOS 子 shell PID 探针通过；自动重启不等于代码热加载。完整真实旅程未运行，分类锚片与新链的用户连续看片、实际试听仍待确认，相关 Gallery 出口保持开放。

**同批先收口四产品的能力表达，不留旧入口/旧自我介绍：**

- Home 首屏可见的视频主分类就是**产品宣传、口播动效、文字动画、知识讲解**，不再以 Ads & UGC 或“产品演示/文字短片”两分类表达产品范围。复用现有两级货架组件，四个产品标签直接成为可见主分类，各带两个典型应用子 Tab；暂无真实样片的应用显示统一空态，不隐藏分类，也不以旧片或替代素材填充。每张真实样片卡与对应内置 Skill 精确版本一一绑定。
- 现有 `/chat/skills` 与内置精确版本回退共同约束 Home 样片卡绑定；前端货架和服务端 `_MENU_PHRASES` 使用相同 Skill id 对账，增加 registry ↔ prompt/货架/i18n 一致性守卫，不新增能力查询端点或第二意图面。空态只是无样片事实，不虚构 Skill 卡或制作能力证据。
- 用户问“你会做什么”时，四类视频产品分别作为四个具体作品组出现；通用全量回答另用一个组承接仍然可用的写作、字幕、配音、剪辑等非四产品能力，不得为凑四类删掉既有真实能力。用户只问“能做什么视频”时只讲这四类。回答仍由唯一 `POST /chat` 生成，菜单只经 `_identity_menu` / `_capability_answer` 的现有座位注入，不硬编码第二份回答。
- 过渡期只陈述当前真实可用能力；四类目标未验收前不得由 Assistant 提前宣传为已能做。全部兑现后，en/zh 的全范围与视频范围回答都不得再回落到旧两产品，不出现工具名、内部 Skill id 或用户未点名的平台。
- 验收覆盖 Home 可见分类、Skill chip 绑定，以及中英文“你会做什么”和“你能做什么视频”的真实 Chat 形态；prompt 面改动由相关真实旅程验收，能力覆盖只锁注册事实与形态，不锁 LLM 逐字文案。

**任务化 Skill 入口与自然语言推断：**

- `/` picker 和 Skill chip 显示用户任务，不显示内部包名：zh 依次为 `/产品宣传视频制作`、`/口播动效视频制作`、`/文字动画视频制作`、`/知识讲解视频制作`；en 依次为 `/Product promo video`、`/Talking-head motion video`、`/Text animation video`、`/Knowledge explainer video`。内部 `skill_id`、目录、版本引用与 `skill_provenance` 继续为 `launch-film` / `talking-head-video` / `text-animation` / `knowledge-explainer`，不改包名来迎合 UI。
- en/zh 的 `skills.builtin.<skill_id>.name` 是 picker/chip 的完整任务名，`shortName` 是 Home 产品主 Tab 短名；共享 `skillDisplayName()` 供 SkillPicker、SkillChip、MentionEditor DOM chip、Home 与历史回放使用，搜索同时匹配本地化 name、现有 description/capabilities 与内部 id。无网络或历史 options 缺失时也回退到本地化名称，永不把内部 id 当用户面名称。服务端内置 Skill metadata 登记相同的 en/zh 任务别名，`resolve_named_skill` 用别名 + 内部 id 解算自然语言；增加 registry ↔ i18n/alias 一致性守卫。
- 用户不点 Skill 时，LLM 可以从普通语言推断四类任务、所需素材和默认下一步，**不得先问“你想选哪类产品”**。推断只选择通用 `design_video` 的创作方向，不伪装成绑定了某个固定 Skill/风格。只有消息实际携带 Skill reference 时，才从该 Skill 的模板、输入要求和固定起点开始；分类不确定且会改变必要输入时仍只问一个可一词回答的问题。
- Home 四类产品只是可选快捷起点，不是用户必须先理解的分类门。直接输入、Home 预填和 `/任务名` 最终都进入同一 `POST /chat`；点击仍只形成 Skill chip + 可编辑 prompt。

**Chat 内 Preset Gallery（复用 SFX Candidate Surface）：**

- 新增非 terminal Chat actions `show_video_presets` / `select_video_preset`，接入 `turn_tools`、plan/propose 双路径和共享 video seat，不进入 DAG `TOOL_REGISTRY`，不新增候选查询端点。只有用户想浏览/比较动效，或 Agent 判断真实审美分歧需要用户选择时才展示；普通创作默认由 Agent 选 Preset，不把浏览组件库变成必经步骤。
- `show_video_presets` 接受 2–4 个当前产品兼容的注册 preset id，服务端从 `PRESET_REGISTRY` 生成 `video_preset_set`；LLM 不提交预览 URL、标题、时长或任意组件代码。候选成员只含 ordinal、preset id、真实 preview asset/url、实际时长/画幅、兼容 Skill 与 digest；卡面名称/说明走 en/zh `videoPresets.<id>` i18n。预览必须使用 §4.1.4 已验收的真实动态样片，内容寻址、权利清晰，不用静态海报冒充动效。
- 复用 `assistant.candidates` SSE、`candidates_log`、最终正文 drain 后揭示、Stop 可见结构注册与刷新回放；只持久化完整 `video_preset_set`，不写 `exploration_rows`，不建新表。前端新增 `VideoPresetCandidateSurface`，卡面只有序号、任务化名称、简短说明、真实播放/画幅/时长与已选择状态；播放/静音/全屏是媒体控制，不是创作写口。
- 卡片不提供直接改作品的点选原语。用户用“第二个”“把第二个用在第三幕”等普通消息选择；下一轮 `select_video_preset(candidate_set_id, member_index)` 从当前 project 的持久候选重解 owner、兼容性和注册状态，只记录 selection 并重绘原卡，**不写 Composition、不建 Run、不产生制作意图**。歧义时只问一个序号/目标问题，不按时间或标题猜。
- 新设计由 `design_video` 接收已解算的 preset choice；已有作品由 `revise_video` 的 `apply_preset` edit 接收目标 + preset choice，经 `apply_composition_edits` 展开为新 CompositionVersion。不得把 preset id 变成隐藏 composer 载荷、mention、第二作品内容写口或直接 renderer 组件。选择后是否继续设计/修订/制作仍由当前用户消息和既有 auto/ask、首稿 hold、报价授权规则决定。
- selection 只更新候选卡；实际设计/修订结果仍由真实版本呈现。失败回合不留下半选择或半版本，旧选择与旧作品不被静默覆盖。

**交付后的动作全部回到 Chat：**

制作完成只由既有 delivery 正文 + Output 卡收口，不自动打开外部 Gallery、Workbench、Inspector 或另一编辑器，不固定追加发布/导出/关注/下一步推荐。用户需要修改时直接输入自然语言，经唯一 `POST /chat` 进入 `revise_video`；播放、下载和既有共享查看器是产物操作，不另建创作流程。可选精确 Inspector 的施工归新合同 P10，不是交付后的必到页面。

- **产品宣传视频（沿用 `launch-film`）**：同一 CompositionVersion 必须混合图片、原生文字、真实视频与网站，至少包含一种本批真实页面状态镜头；补默认 SFX 和完整视听验收。真实网页负责产品证据，Generator 不得伪造界面或数据。
- **口播动效视频（新内置 `talking-head-video`）**：输入用户真人原片，输出 9:16 原声视频与可编辑主标题、副标题、胶囊标签和定时字幕；使用真实粗字重、黑描边/阴影和 Shape 胶囊，达到所给参考片的同类三层文字观感。只改标题不重传素材、不改变其他层，不要求 component-v1 或源对齐旁白。
- **文字动画（新内置 `text-animation`）**：固化一种已验证的文字风格，实际组合本批代表 Preset、原生 Text/TextPart/Shape、NarrationAnchor（有旁白时）和音频能力；无 component 需求时不强行使用新 runtime。
- **知识讲解（新内置 `knowledge-explainer`）**：输入可以只是用户给出的知识，或明确标注的模拟知识文字稿；最终讲稿/音频 → READY NarrationAlignment → Agent 语义 → 分镜与词锚动画。至少一个具体词触发 `text-impact` 或其他代表 Preset，一个 drawing-v1 主视觉镜头解释知识内容，字幕与重要讲解文字保持原生可编辑。真实图片/视频/网页不是必要输入；模拟知识稿不冒充真实采访、研究引用或事实来源。首个版本限定一种真实风格与输入组合，不承诺任意 FredTalk 风格，也不开启 component-v1。

每张 Gallery 卡必须具备：真实目标用户任务、对应 Skill/版本、公开且权利清晰的输入/输出样例、真实完整音轨、可兑现的制作与修订链。点击仍只形成 Skill chip + prompt，不自动发送或 Start。占位片、静音成片、仅领域 run-less 证据或仅能渲染 TSX 均不能上架；四类分别完成「预填 → Chat → 首稿 → 授权 → 制作 → 交付 → 修订」与动态观看/实际试听后才逐张转为 live。

#### 4.1.7 波形试听与精确 Inspector 的共同形态

首个共享 `WaveformPlayer` 只承载真实音频的 play/pause、seek、播放进度与时长；语音消息形态 = 圆形播放钮 + 确定性 bars（已播放部分 clip/mask 变色）+ 单时间显示。bars 可使用绑定稳定 candidate/audio identity 的模拟算法，live/history/remount 必须同形，禁止随机刷新；播放、暂停、seek 与 ended 仍只由真实 HTMLAudioElement 驱动。使用项目现有 `motion/react` 依赖服务播放状态、真实进度和候选卡视觉过渡，reduced-motion 取消过渡，不新增 motion 体系或第二套音频状态机。不得复制参考录音器的录制/发送/Canvas 实时录音、CSS module 或 Next 专用代码。

- SFX 候选使用 `AudioCandidateSurface`：复用 Candidate Surface 的 ordinal、消息持久化、自然语言选择和回放，新增真实播放，不改变既有选段 CandidateSurface 的无播放合同。
- 精确音频 Inspector 复用同一播放器和本地 draft/Apply/Cancel 骨架，目标为明确 version + audio Clip；Apply 只提交 `revise_video(base_ref, clips=[{track_id, clip=完整 audio Clip}])`，连续试听/seek/调值不写 DB、不调 LLM、不建版本。
- 候选搜索、资产导入和作品修订保持三种服务端语义，不合并成大工具；共享 UI 不创造第二内容写口。

## 5. 跨阶段验证与交付纪律

1. 核心 API/DB：按实际改动运行 `cd apps/api && uv run --extra dev python -m pytest test/core -q`，不为覆盖率扩张内部实现测试。
2. 真实旅程：运行 `cd apps/api && uv run python test/journeys/chat.py --only <name>`；需要活 API、当前 migration、fresh worker 与模型配额，付费制作另行授权。prompt 改动同样由相关真实旅程验收。
3. 注册表：网页、宣传视频、时间修订等当前旅程统一由 `test/journeys/chat.py` 的 `JOURNEYS` 维护，断言用户可见结果和持久化事实，不锁 LLM 文案。
5. Web/render：按改动运行 TS schema、纯求值、组件与渲染测试；preview/render parity 需要真实帧证据。
6. 人工验收：完整 Chat、首稿停等、Start、CRUD、刷新恢复、动态看片、独立音轨试听；这些不得由 pytest/tsc 替代。
7. 并发、计费、授权、素材权限和有界失败是上线硬门，不能以“内部开发”名义豁免；不迁移业务数据不等于不做 schema/安全验证。
8. 验证结果写入本文对应阶段和 PROGRESS 当前快照；未运行项明确保留，不合并成“已验收”。

## 6. 阶段 A 开工顺序

1. 在 NAMING/MODULE_ARCHITECTURE 登记 Composition/CompositionVersion、editing 模块、compositions/composition_versions/source_snapshots 与 video-spec；核对当前引用权限、Output.work_id/发布、删除级联与执行互斥接缝。
2. 冻结最小 schemas/timing：身份、三时间域、半开范围、量化与同轨/动画冲突规则；删除保留和未定数值按 §8 明确后再落相应实现。
3. 写 `apply_composition_edits`，先做事务原子性、跨 Chat 并发、请求幂等和 owner 校验，不先接 LLM。
4. 用最小内容与固定素材绑定打通 video-spec → render worker → probe → Output 血缘；不等所有对象/模板类写齐。
5. 扩 SourceSnapshot、Animation/TextPart、字体与 PreviewAdapter，手工构造官网片/MG 对照 fixtures。
6. 补完整素材权限、快照 refresh、split/trim/音频关联、失败恢复、两阶段 digest 与架构门。
7. A 最小出口后转 B 的真实 Chat 闭环；完整视听人工验收在 B 集中做，替代 renderer 归 新合同 P7，不继续扩充独立样片与检查脚本。未授权/未接费用机制的内部渲染入口仍不得暴露。

## 7. 不做清单

- 不做旧业务数据迁移、旧 FilmStoryboard 兼容读或全库回填。
- 不做第二执行引擎、Scene/Clip 执行图节点或 Canvas 版本库。
- 不做自由 NLE、任意关键帧 UI、转场画廊或每字符独立编辑器；最终 video-spec 不开放任意 CSS，受控程序内部采用何种视觉技术按 §2.5.1 选择，不混淆两个边界。
- 不执行导入的第三方 Skill 脚本，不做 Skill 市场、多 Skill 自由叠加或隐藏 recipe 执行参数；B-IV 显式受控的程序画面生产不等于授权执行外部任意脚本。
- 不做 production-time 缺版重设计、LLM 转录 canonical 分镜或视觉修改后保留失实描述。
- 不在 A–C 迁移/删除 Clip，不提前实施完整 Scrub；不建设“复制确切作品”或通用分支合并功能。

## 8. 施工评估与开工前置

**判断：主干可施工，A/B/C 作为已建基线保留证据；后续显式删除清理、Renderer 与发布门统一归新合同。**不重写 Chat/Run 内核，不先建设完整 NLE、全局素材库页面或通用模板语言。UI 可并行施工，既有 Chat 布局也是必验路径；首批成功标准是官网片、文字 MG 与混合实拍内容共享同一内容内核、可精确修订并可靠交付，不以目录/类/名词齐备为完成。

| 必须明确的接缝 | 截止门 | 交付物与失败处理 |
|---|---|---|
| 全局 owner/引用权限、Chat 删除与快照保留、Output.work_id 与发布/归档的对应 | A schema 冻结前 | 查当前代码/约束后冻结最小字段与删除规则；记录不一致，不能假设这些全局能力已实现 |
| 时间量化、Transition handles、split/trim 关键帧与音频关联、字体/文本求值 | A 代表样片前 | 纯函数合同 + 跨语言/预览渲染 fixtures；首版不支持即明确拒绝 |
| 内容摘要、执行输入摘要、准备产物 manifest、请求幂等与恢复 | A 出口 / B Start 接入前 | 模拟超时/重试/并发，证明无重复落版、无执行漂移；实际收费在 B 验证 |
| Chat 正文/活动/产物关联、实际阶段与 attempt 回放 | A 最小 DTO fixtures / B 过程接入前 | 冻结关联与事件最小形状，核对真实阶段发射点；B 用关闭/缓存/失败/重连旅程验证，不用组件演示进度冒充执行事实 |
| TTS 语速上下界、尝试次数、超长/可懂度判定与成本上限 | B 合成接入前 | 使用当前合成能力确定有界制作政策；超界回到修订，不偷改切点 |
| Generator 来源/参数、预览身份、生产 manifest 与受控运行权限 | B-IV drawing-v1 已按真实旅程验收；B-V 扩模型消费者时复核 | 首个 schema 与资源/尝试/费用边界已冻结；内容不回写，成功结果可恢复，重试不重新创作；不另建生产链 |
| 替代 Renderer 的能力与成本、Remotion 商业方案 | 新合同 P7 生产前 | 实测能力与成本差异并作明确选择；不以“已隔离 adapter”冒充已替换 |

**后续依赖**：A/B/C 的既有实现与限定证据如上；任何剩余能力、发布门与切换均按新合同 P0→P10 执行。限定发布不把完整 B/C 或全部视频目标标为完成，程序/生成媒体只暴露实际支持参数。

## 9. 新会话接手入口

当前批次以 **PROGRESS §0** 为准，授权范围以本次用户指令为准；先读本文 §2.0 区分已提交基线、工作树成果、真实验收与保留欠账，不按旧会话提示词重做已完成主链，也不把未试听、未运行或未提交写成通过/已发布。

阅读顺序：CLAUDE.md → PROGRESS §0 → VIDEO_PROJECT §0 → 本文 §1.3/§2.0/§2.4/§2.5 及命中阶段 → VIDEO_PROJECT 对应章节。Generator 施工必读 §4.3.2/§8.1.1/§11/§12；按实际修改补读 Chat/Rendering/Billing 和适用 AGENTS.md，不通读整个 docs。代码先定位 editing、tools/video、Chat tools、video-spec 和 renderer 的实际接缝。

明确本批最小可复用能力和代表旅程后实施。按表达/执行/创作/编辑四层报告；受控视觉程序是内容生产，业务图拓扑仍由代码裁决。所有内容修订经 apply_composition_edits，图变更经 apply_wiring_ops，Run 只经 create_run；不按每个 Object 建执行节点，不增加平行执行引擎或通用插件层。

沿用不可变版本、固定执行身份、既有授权/计费/交付/fencing。沿真实主流程补少量必要守卫，不新增独立样片/检查框架；完成后运行适用检查，分别记录实证与未验收项。保留工作树，禁止 reset/stash/擅自部署；提交、重启及迁移按本次授权和环境约束执行。付费前核对有效授权范围、累计预算与已消费，§2.0 的历史额度不自动重置或扩大；授权已覆盖就继续，缺失只询问必要付费范围，并推进不依赖付费的工作。
