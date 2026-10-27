# Video Project 四阶段施工与验收

> Status: 施工中（2026-10-28）。目标架构唯一事实源 = [VIDEO_PROJECT](../VIDEO_PROJECT.md)；本文维护 A/B/C/D 阶段及 B 内增量批次、依赖与验收。当前入口 = **B-III 混合合成底座**；MG/跨 Chat 与官网片真实主链已通过，B-II 保留听感、循环接缝、付费 prompt_gate 等未验收项，完整 B 未封板。新增混合合成/程序画面/生成媒体批次见 §2.5；A 最小基座及剩余能力见 §1.2–1.3。状态就地更新，全局优先级归 [PROGRESS §0](../PROGRESS.md)。
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
- 当前支持 Text/Image/Web 静帧/Audio、固定字体 digest、TextPart line/word/grapheme、整体/分段动画、scale/Bezier。四个 base/edited 样片位于 `artifacts/video-project-a2/{website,mg}/`，Git 忽略；它们证明内容表达与局部版本编辑，不代表 Chat 可用或人工审美验收通过。
- `move_scene` 原子平移所属 Clips，源窗/Clip-local 动画与全局音乐不动；`remove_scene` 删除所属内容并清理旁白引用。带内容 Scene 的范围重设不能静默只改标记：移动走 move_scene，缩放/改时长当前明确不支持。复制 Scene、split/trim、Transition 等仍未实现，不宣称完整 NLE CRUD。
- SourceSnapshot 登记/绑定与字体描述归 editing；资源读取、冻结上传及字体发布归 `tools/video/preparation.py`，editing 不依赖 providers。快照当前消费已有 Asset/采集结果，尚未接入 Chat 素材流程。
- 收口验证：受影响 editing/DB/animation/spec/样片契约测试 **44 项通过**，check_gates 通过；只新增 Scene 移动/删除两项承重用例，未扩写验收脚本。未复跑全量 API/web/render，未重渲染或人工播放验收样片；已有样片与批 1 渲染证据不升级为本次新证据。
- 旧 Film 入口/Clip 链不切换。所有改动仍在 feat/mg 未提交；开发基座收口不等于生产就绪。

### 1.3 A 出口与保留的能力欠账

A 的最小出口：版本写口与权限/幂等成立、代表性静态网页/MG 内容可编译渲染、Scene 移动/删除语义明确、内容/存储/renderer 边界检查通过。上述出口已达到，可以进入 B；停止增加同类样片与通用检查脚本。

以下能力不因 A 收口取消，也不标成已完成：

| 剩余项 | 实施 / 验收位置 |
|---|---|
| Video/Speech、旁白准备、两阶段执行 manifest/digest | B 在具体设计/制作消费者接入前实现；付费合成仍受预算授权约束 |
| launch-film 模板所需的 Scene/Clip/Object CRUD、split/trim、转场与 BeatGrid | B 按内置模板和真实修改需要补齐；模板不得静默省略不支持能力。自由 NLE/完整转场库后置 |
| 源时间 Video/原声联动、同源多切片完整对照 | B 出现相应媒体输入时实现并验证，不能用静态网页样片冒充 |
| 跨 Chat 引用/删除保留、素材 refresh/生产接入、重试/恢复 | B 的真实用户链路；已有 DB 验证不替代端到端权限与恢复验证 |
| PreviewAdapter | B 先用隔离的服务端 MP4 预览，复用现有播放器；交互式预览后续扩展 |
| 字体/排版与预览导出一致性、动态画面、独立音轨听感 | B 最小闭环接通后集中人工验收；只对实际失败补定向回归 |
| 替代 renderer spike / 商业许可 / 能力矩阵 | D2，生产前必须收口 |

## 2. 阶段 B——launch-film Skill 化、Chat 分镜与 CRUD 制作闭环

### 2.0 B 当前状态（2026-10-28）

上下半批均已落码于 `feat/mg`，具体提交状态以 git 为准；**真实 MG 制作/交付/播放与跨 Chat 修订闭环均已通过，B 主链收口，仍未封板**（欠账见下）。不要按旧提示词重做上半批或生产链。

- **已有实现**：`editing/service.py`、`chat/video_turn_seats.py` 共用 plan/propose，canonical 卡片、真实消息 id、完整呈现 ACK、首稿批准守卫、明确后续修订并制作的延迟启动与现有确认/费用设置接线。补齐版本上下文、幕数/时长/背景约束、背景修订、全局 @asset/@output owner 读面。新增 `tools/video/params.py`、`tools/video/production/`，produce_video 经既有图写口/create_run 固定版本、估价/hold、manifest、渲染/上传/probe、成功 capture、交付；成功才归档同作品旧完成产物。
- **环境**：默认闸仍 false，本机忽略的 `.env` 已开 `VIDEO_PROJECT_ENABLED=true`；DB head `z5d8f1b3a7c2`。API8000、web3000、render3001；worker/render 不热加载，改执行代码后无活跃任务再重启。日志 `/tmp/rep-api.log`、`/tmp/rep-video-b-worker.log`、`/tmp/rep-video-b-render.log`。
- **真实成功（同 Chat）**：Chat `2cce4c18`，Composition `05c66c6f`；Run `e32ed9f2` COMPLETED，Output `94ccf1d8`（v3）。
- **真实成功（跨 Chat，2026-10-27 收尾通过）**：Chat `1b89291a` @output 引用成片，仅改第三幕为 Keep editing 并直接制作；保存 v4 `0d6df014`，浏览器回放卡片完整呈现 → ACK → 延迟启动 Run `f6b64fb6`（version_ref 钉 v4）→ 渲染/上传/probe → Output `36383c3f` COMPLETED，hold→release→capture 各一次（-12 积分），旧片在新片成功后才归档；浏览器真实播放，5.2s 帧确认第三幕为 Keep editing、其余不变（"in focus" 是 v2 的用户修订，非串改）。成片存 `artifacts/video-project-b/`（已 git 忽略）。
- **本批修复**：① 回放洞——pending/已答 task_book 行的 video_storyboard blocks 不进历史流，刷新后卡片不再呈现、ACK 永不再发、授权延迟启动永久卡死；`historyReplay.ts` 两条分支现携带 blocks 回放（已答 echo 行与 pending echo 行），旧无 blocks 的 plan dock 行为不变。② `_video_project.j2` REVISION 律补状态真言：改版卡片呈现完成前制作未开始，禁称"渲染已在后台进行"。③ 三个守卫测试随门控世界更新（工具桶 XOR 断言、plan stub 补 user_id、trigger 工具预算 18→21 注明出处）。
- **检查（本批末轮改动后实测）**：API pytest 1310 全绿、check_gates 通过、apps/render tsc 干净（web 未改动，沿用上半批 web257/web-tsc 绿）。完整付费 prompt_gate 未跑（prompt 面有改动：SKILL.md v1.3.0 重写 + `DesignVideoArgs.music`，部署前须补）。
- **真实成功（官网片，同 Chat 全闭环，2026-10-27 独立复验）**：项目 `bd2b2f2e` / Chat `9ee217bc` / Composition `79035790`。首稿 v1 `e09d8509` 完整呈现 → ACK `run_id=None`（呈现不动工）→ 用户批准 → Run 钉 v1 digest；首 Run `98a70678` FAILED（render POST 被系统代理截断，hold 176 全额 release），重试 `b943bf22` COMPLETED（capture 一次）。局部修订「hero 副标题补空格」→ v2 `dc75f1ba`（settings/sources 逐字节相同，timeline 仅 `clp_hero_text1` 文本变，零重新采集、零重新设计费），普通修订零 Run；「改完直接做」→ Run `3f3262f5` 钉 v2 → Output `31e444aa`。同版再产 → Run `59762ae8` → Output `558c6547`（终片，88s/1920×1080）。每次 Run hold→release→capture 恰各一次；ACK 重放 `accepted: false` 不产生新 Run；渲染中 Output `files={}` 不冒充完成。帧级核验：屏幕文字取页面原文且字体正常、hero 文案空格已复、章节字幕正确、音乐床全程约 -20dB 且 88s 处淡出至静音、无旁白（内容模型无语音对象，结构性保证）。
- **本批修复（官网片链，均有真实证据）**：① `SKILL.md` 陈旧槽位词汇（法条座位冲突，首设计回合 29 个 schema 错误的根因）全文重写为 v1.3.0；② `CiteLine._fold` 从未注册为 validator → 接上 `model_validator` 并扩拼写（非法引用仍 raise，纯函数实测）；③ 字幕 `{text,citation}`/片段列表 fold 成纯文本（不丢词不乱序，不可解析结构 raise 不静默置空，纯函数实测）；④ 音乐床：`video-template.json` 增 `trk_music` + `MusicBed` 平铺 + gain 关键帧淡入淡出 + `resolve_bed_track` 三态（off 终态无人 reopen，实测 `off→None` 且不建空音轨）+ `snapshot_music_track` 内容寻址冻结；⑤ `storage.py` S3 client 显式 `proxies={}`（urllib3 隐式走 macOS 系统代理吞大 PUT 响应，boto3 全项目仅此一座）；⑥ `rendering.py` render POST `trust_env=False`（长渲染请求被代理中途切断）；⑦ 字体缺陷：`fonts.py`/`schema.ts`/`Video.tsx` 给 emoji 字体资源加 `unicode_range`（Noto Emoji 含拉丁字形且 family 排序在前，整行拉丁渲染成 emoji 面、词距崩塌；修复后帧实测正常）；⑧ `capture.py` 研究清单把 `<br>` 视为词边界（`actions.<br>Not` 空格被吞，真实页面 HTML 实测修复）；⑨ `grounding.py`：focus 取元素**可见部分**（视口裁剪截图的元素坐标可越界 >1）+ camera 平移钳制在 cover 余量内（聚焦越界元素会把画面推出画布露黑；真实 view-1 库存上纯函数实测钳到界内）。
- **本次代码审查与必要修复（2026-10-28）**：相机原钳制把 cover 图片的额外像素误作实际 Img 盒子的可移动余量，且忽略起点/末段漂移；改为按 renderer 的画布大小盒子与各关键点实际 scale 限位，并由模板透传起始 scale。CiteLine canonical `line` 改 strict integer，拒绝此前会被折叠成1的 bool/整值float；字幕空/空白片段列表不再静默变成 null，而交字段校验拒绝。增加12个现有套件参数用例；API1322、web257、web/render tsc、video-spec9、check_gates 通过。用现有本地入口实际渲染4秒/120帧边缘聚焦白底短片，全部边缘RGB=255；这是针对裁切盒边界的真实 renderer 验证，不冒充原官网片重渲染或音乐试听。样片位于 `artifacts/video-project-b/camera-review/camera-coverage.mp4`，未调用付费模型。
- **未验收欠账**：原官网片 v1/v2 为修复前烘焙键帧，未用新内容重渲染；新的相机限位已通过独立 renderer 120帧边界验证，真实网页视觉取景随下一首稿核验；音乐未亲耳试听（结构与电平核验，听感不冒充验收）；音乐多瓦片循环接缝未真实渲染（本素材单瓦片即够长）；`run_failed` 触发回合沉默一次（FAILURE FACTS 装配正确但模型读满预算未发声，同机制其余回合正常，登记为 LLM 漫游方差未修）；完整付费 prompt_gate；§2.4 剩余条目（TTS 有界适配、多作品同 Chat 并行、移动端/双主题/reduced-motion 等）。
- **预算**：本轮授权累计人民币30元；ConversationUsage 累计 LLM USD1.62（上一批 USD1.12 + 本批 USD0.50，≈¥11.6）；本批真实 Run capture 176×3=528 积分（dev 额度）；无超额。当前 Text/Image/Web静帧/Audio；Video/Speech/Transition、完整NLE/交互式Preview 未实现，保留合同欠账。UIArc/ReUI仅调研；C/D不在本批扩张。

### 2.1 目标

新链按 §2.5 分批支持“网页/MG/混合内容 → 分镜 → 首稿审阅 → 授权 → 制作 → 交付 → 持续修改”，逐步接入程序画面、生成媒体与旁白；不能把文字动画的阶段成果称为全部画面能力。launch-film 在新链只是 Skill，不再拥有专用设计或生产链。

### 2.2 施工范围

**B1. 内置 Skill 与通用设计**

- `app/skills/launch-film/SKILL.md` 保留创作工艺；新增 `video-template.json` 承接固定场景结构、Tracks/Clips/Objects/Animations、3–5 章 repeat 和可选 plate。
- `app/editing/templates.py` 实现有界槽位、repeat、variant 和展开；Template 不含 assistant 文案或可执行脚本。
- 新建通用 `design_video`：有 Skill 时实例化 VideoTemplate，无 Skill 时以结构化 edits 自由设计；两者共用 validator 与版本写口。
- Director 只输出创意槽位、精确脚本和每幕 `visual_description`；事实文案仍走 citation/grounding。
- capture、citation、网页视图绑定和容量校验保留在代码能力中，不复制进 Skill 文本。

**B2. 统一 Chat 编辑服务与工具**

- `design_video` / `revise_video` / `produce_video` 共用一个应用服务；plan/propose 不再各复制 compose/patch。
- `revise_video` 支持 Scene、Clip、Object、Animation 的当前所需 CRUD；结构化修改和开放修改都产生子版本。
- 新增 `get_video_version(version_id | composition_id + current)`，返回 canonical 保存版；多影片不能隐式选择 Chat 最新产物。
- 视觉内容的 Chat 修订同步更新受影响 `visual_description`；确定性手势修改则清空该字段并回退事实标签。
- 新版本完整呈现、change_set、未解决项与当前制作设置都由保存版生成；仅内容修订不产生虚假已交付 Output，制作成功后才交付新产物，旧产物保留。
- @output 服务端解算确切 CompositionVersion；“继续修改”与“当素材使用”分开。旧版不是 current 时明确差异与选择，以当前 head 条件提交，不静默覆盖。

**B3. Canonical Storyboard 与首稿授权**

- `storyboard_payload(version)` 由服务端生成完整表格：时间/帧、visual_description、精确屏上文字、旁白、素材和音频事实。
- Chat 不再让 LLM 转录唯一分镜真相；结构化 payload + 组件/确定性表格负责呈现，LLM 只补充解释和下一步。
- 持久化 `presented_message_id + presentation_digest + composition_version_id` 到通用确认状态；首稿 Start 校验三者。
- 按 VIDEO_PROJECT §2.3 明确完整呈现与中断的回执边界；生成 payload 不冒充已呈现，回执不冒充用户已读，首稿另需呈现之后的批准。
- 保留“首版先完整呈现并等待”、普通修订不重制、明确“改完直接做”才进入制作、auto/ask 与守卫线规则。
- 所有 assistant 散文与 LLM 散文字段继续满足 null 读容忍和打字机节拍；结构化组件不得成为瞬移旁路。

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
- [ ] 固定切点下旁白有界语速适配通过；超长明确冲突、切点不动；手改字幕不被重生成覆盖。
- [ ] 纯 Chat 无 Canvas 时可完成设计、审阅、Start、交付和修订；Graph/Run 状态不依赖布局坐标。
- [ ] 正文、工具活动、版本与成片卡顺序一致；刷新/重连不丢失、不重复、不串作品；拒绝回合不泄漏未接受的预览或产物。
- [ ] 同一后端数据可驱动既有 Chat 与整合 block 呈现原型；异步 Run 跨回合仍可准确关联，刷新不重启执行，停止接收流不误作后台取消。原型验证不代表 UIArc 选型通过。
- [x] 旁白关闭、准备缓存命中、渲染后交付检查、失败恢复与重试均呈现真实阶段；旧 attempt 不覆盖新状态，未交付不提前显示完成。live 与回放对应同一执行事实。（实测：无旁白为内容模型结构性保证；失败 Run 全额 release + 诚实文案；重试 capture 恰一次；渲染中 Output files={} 不冒充完成；ACK 重放 accepted:false）
- [ ] 默认布局与选定呈现组件均保持授权、工作段收口、打字机、中英文、移动端、键盘可用性及 reduced-motion；不依赖模型整块汇报才知道进度。
- [ ] 完整动态看片与独立音轨试听通过；配置、probe 或静帧不冒充动态/听感验收。
- [ ] 有界失败、统一 LLM 调用预算、报价/实扣、重试幂等和过期 base_ref 均有真实旅程证据。

- [ ] **B-III**：动态背景、中央录像、独立标题/字幕、原声/音乐可混合；源窗/输出窗与声画同步正确，Chat 局部修订不串改其他层，真实播放与试听通过。
- [ ] **B-IV**：至少一条原生图形动画可精确修订；至少一条程序画面通过固定程序/资源/参数生产并入片，渲染重试不重新创作，不虚构烘焙媒体内部可编辑性。
- [ ] **B-V**：至少一个明确声明的图片或视频生成用例，经请求/费用授权、真实生成、固定结果、合成与交付；失败/重试/明确重新生成的身份与收费边界正确。单一用例不等于两类生成均支持。

### 2.5 B 的增量批次与出口

下列罗马编号标识增量批次，依赖按 §8，§2.2 的 B1–B7 仍为职责清单。批次分开不取消原合同；每次仅实施一个明确出口，不要求一次 compact 完成全部 B。

| 批次 | 内容与出口 | 当前层级 |
|---|---|---|
| **B-I 基础 Chat 闭环** | MG 设计/呈现/批准/制作/播放，同作品多轮与跨 Chat @output 修订；唯一写口、固定版本、计费/交付可靠性 | 主链真实通过，剩余过程/恢复守卫持续按实际缺口补 |
| **B-II 官网片与过程收口** | 官网模板/grounding/快照/镜头/字幕/音乐；真实 Chat 首稿审阅→制作→播放/试听→局部修订；刷新恢复、真实阶段和剩余 prompt 检查 | 真实 Chat 闭环、修订同一性、刷新恢复与帧级播放核验已通过（证据见 §2.0）；欠账：听感试听、付费 prompt_gate、运镜修复像素级复验（随下一首稿）、音乐循环接缝真实渲染 |
| **B-III 混合合成底座** | VideoObject 的 schema→source/probe→编译→adapter→Chat 全链；源窗与输出窗、原声同步/音量/静音、画面位置/尺寸/裁切；与原生标题/字幕、动态背景/音乐同时合成 | 待施工；原计划 Video/源时间欠账在此兑现，不推到 D3 |
| **B-IV 原生 MG 与程序画面** | 先按代表场景补最少必要图元/路径及动画，支持原生参数修改；再以一条真实 2D 或 3D 程序画面证明程序/资源/参数固定、受控生产、缓存复用及媒体合成 | 待施工；可分两个纵向小批，不先建设全量图形引擎或代码平台 |
| **B-V 模型生成媒体** | 从一个确切 provider 与图片或视频用例开始，显式生成请求/参考输入/费用批准→生成→固定媒体/血缘→同一 Composition 合成；重试复用成功结果，明确重新生成另立执行身份 | 待施工；先单模型单用例，不预建全供应商框架；图片与视频分别声明支持 |
| **B-VI 旁白与原合同余项** | Speech/TTS 固定切点、有界语速、超长冲突、字幕派生及手改保护；剩余 split/trim/必要转场/BeatGrid 按真实消费者实施与验收 | 原有欠账保留；Speech 为独立消费者，不因本轮重新分批取消 |

**B-III 的代表性验收**：动态背景 + 中央真实录像 + 独立顶部标题 + 定时字幕 + 原声/音乐，在同一 Scene/Composition 混合；通过 Chat 只改一处字幕或中央录像布局，未改内容/源窗保持，再制作交付。背景可先用已有动态素材或受支持对象动画，不把复杂自由 MG 当作混合合成的前置。此后 B-IV 再验证原生/程序画面替换背景，B-V 再验证生成媒体替换其中一段；不为每次接入重复建设生产链。

**声明与发布门**：§2.4 逐项按证据更新，未实现/未验收不勾选。首个限定能力发布可以只声明 B-I～III 中实际通过的内容，但仍需完整授权/收费/恢复/交付和 D1/D2 发布门；明确不支持的旁白、代码画面、生成媒体等继续留在合同，不标完整 B 完成。需要这些能力的产品承诺必须先完成对应批次。不因新增 B-IV/V 批次自动授权外部模型费用、安装依赖或部署。

**实现纪律**：一次代表性真实旅程驱动必要功能及少量承重守卫；不提前创建未来模块/表/空目录，不建立另一份目录树。新增文件/模块按 VIDEO_PROJECT §12 及模块图同批登记。用户可用入口、版本和成片优先于样片脚本数量；仅对实际修改运行必要检查，最终集中回归。

## 3. 阶段 C——个人 Skill 保存、调用与外部导入

### 3.1 目标

用户能把满意的作品保存为自己的 Skill，并在以后通过 `/skill + prompt` 或明确点名复用；外部 Claude/Codex Skill 能安全转换为当前能力可表达的 SkillDraft。

### 3.2 施工范围

**C1. Skill 存储与版本**

- 新增用户 Skill 与 SkillVersion 持久化；平台内置 Skill 继续走代码注册表，用户 Skill 按 owner 隔离。
- SkillVersion 包含 instructions、VideoTemplate、Presets、输入/能力要求、可选 PromptTemplate、示例 provenance 和 source hash。
- 保存时从 CompositionVersion 确定性抽取，不由 LLM 重写数值；LLM 只协助名称、description 和使用说明。
- 默认排除用户事实文案和源素材；示例引用必须遵守权限与公开性。
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
- `scripts/` 不执行；`allowed-tools` 不授权；任意渲染代码、网络/文件访问和私有工具不进入运行链。
- 只能映射到已注册 Objects、Animations、Binders 和 Validators；缺失能力明确列出。
- 外部内容视为不可信创作输入，不能覆盖系统、grounding、权限、报价和授权。
- 用户用真实素材审阅生成的 CompositionVersion 后才可保存。

**C5. 复用 Chat 预览与引用组件**

- Storyboard/CompositionPreview 以版本引用加载 DTO，可刷新回放，不依赖 Canvas。
- 预览通过 PreviewAdapter；不把 Remotion 组件名写入消息或 spec。
- 本阶段不做 Scrub；仅建立后续 Inspector 所需的稳定 version/clip/object 引用。

### 3.3 C 阶段验收

- [ ] 保存 Skill 后，结构、Track、布局、动画和参数与来源 CompositionVersion 的声明范围一致。
- [ ] `/skill + prompt` 在刷新后仍绑定同一 SkillVersion，无隐藏 recipe_id 或第二执行链。
- [ ] Strict 不可满足时明确失败/询问；Adaptive 的变化完整可见。
- [ ] 外部 instruction-only Skill 可转换；依赖脚本/私有工具的样本得到明确能力缺口而非静默降级。
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
- 不做自由 NLE、任意 CSS、任意关键帧 UI、转场画廊或每字符独立编辑器。
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
| 替代 Renderer 的能力与成本、Remotion 商业方案 | D2 生产前 | 实测能力与成本差异并作明确选择；不以“已隔离 adapter”冒充已替换 |

**依赖顺序**：A → B-I → B-II → B-III；B-III 后优先按代表需求推进 B-IV/B-V，B-VI 保留独立实施出口。C 在稳定且已声明的内容能力上复用创作方法，不阻塞首批发布；遇未支持的程序/生成能力必须列缺口。D2 可并行研究，生产前通过；所声明 B 能力验收 + D2 → D1。B-III 后可安排 D4 首版，不依赖 C 或全部 B-IV～VI；程序/生成媒体仅暴露实际支持参数。D3 后置且不阻塞 B-III。任何限定发布均不把完整 B 或全部 ABCD 标为完成。

## 9. 新会话接手入口

当前执行 **B-III 混合合成底座**，范围与出口见 §2.5；先读 §2.0 的真实状态，不重做 B-I/B-II，不把 B-II 余项写成通过。B-II 原官网片仍需听感、循环接缝及付费 prompt_gate 等发布前验证，保持登记；当前用户仅授权接手新批，不自动增加外部调用预算。

阅读顺序：CLAUDE.md → PROGRESS §0 → 本文 §1.3/§2.0/§2.4/§2.5 → VIDEO_PROJECT §4/§6/§8/§10/§11/§12/§15 中的相关内容；按实际修改补读 Chat/Rendering/Billing 和适用 AGENTS.md，不通读整个 docs。代码先查 editing schemas/validators/video_spec、素材快照写口、video-spec契约、renderer adapter、video design/revision/production 共座。

本批把已有视频素材通过真实 Chat 放进 Composition：动态背景 + 中央录像 + 独立标题/字幕 + 原声/音乐，支持明确源窗、位置/尺寸/裁切、静音/音量与局部修订。同 owner @asset/@output 按媒体使用时固定确切文件，不与继续编辑原作品混淆；原声随视频源窗/输出窗同步，无新增轨道UI。先保持1×、无转场，使用已有动态素材/对象动画作背景，不提前做 B-IV/V/VI。

沿用不可变版本、固定执行身份、唯一内容/图/Run写口、既有授权/计费/交付/fencing。不得把所有 Clip 变成图节点，不新建执行引擎或通用插件层。主要时间写功能，沿真实主流程补少量必要守卫，不新增独立样片/检查框架；完成后集中适用回归，真实操作证据与未验收项分别记录。保留工作树，禁止 reset/stash/擅自部署；提交按本次用户明确授权执行。付费沿用本轮累计人民币30元并先核实已消费，不重置预算。worker/render 不热加载，无活跃任务再重启。
