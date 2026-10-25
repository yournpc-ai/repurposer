# Film 编排与持续修改——现行设计与延期契约

> Status: 人工试用与定点收尾（2026-10-24）。本文是 Film/MG 技术契约事实源：当前能力写 CURRENT；已拍板但未实现的设计必须写 PLANNED。实现与验证层级归 [progress](film-storyboard-orchestration-progress.md)，剩余工作与验收归 [execution](film-storyboard-orchestration-execution.md)，全局排期归 [PROGRESS](../PROGRESS.md)。本文不记录事故、方案演进或逐轮验收。
> 范围纪律：保持 SaaS/App 路径可用；不建通用插件平台、依赖引擎或第三方脚本环境；不让模型执行任意渲染代码；不削弱事实校验、授权、并发与计费保护。

## 0. 一句话

分镜是有稳定场景/元素身份、可结构化编辑的作品版本。网页源与文字源共用版本、编辑、音频、单体 `launch_film` 执行、渲染和计费链；媒体是可组合元素，文字有独立内容、空间与时间窗。模型负责创作决策，工具表达修改，代码保证执行正确性。新建默认无配音，配音、音乐、视频原声分别表达；完整知识视频专项不在当前范围。

## 1. 当前链路与代码地图

| 阶段 | 当前实现与座位 |
|---|---|
| Chat 意图与方向 | `app/prompts/chat/_website_film.j2`、`_text_film.j2`、通用 intent prompts；无第二意图端点 |
| 设计与修改 | `design_storyboard` 双路 dispatch：`app/chat/plan_turn.py`、`propose_turn.py`；工具声明在 `turn_tools.py` |
| 分镜/版本/校验/编译 | `app/tools/film/storyboard.py`；Pydantic 契约在 `app/models/schemas.py` |
| 结构化编辑 | `app/tools/film/edits.py` 唯一 ops 应用座；系统有序、原子应用并生成 change_set 与完整当前版本事实 |
| 素材与作品读取 | `app/chat/perception/`、`tools/research/capture.py`、`project_media_candidates`、`get_output_spec`；图片经 tool observation parts 携带 |
| 授权与 Start | `app/pipeline/lifecycle.py`、chat dock/Start gate；版本、制作意图、费用和 review hold 分别校验 |
| 执行 | 当前为单体 `LaunchFilm.run`：消费钉版快照 → 帧分配 → 音乐/旁白 → spec/Output/计费 → render 入队；宏阶段是 PLANNED |
| 旁白与音乐 | `tools/film/narration.py`、`narration_store.py`、音乐库与 beat grid；原始合成音频项目级复用，窗口不适配时真实重新合成并计量 |
| 渲染与质量 | film-spec 第二家族，`apps/render/src/film/`；renderer 是可替换黑盒；`pipeline/render_probe.py` 做容器级闸，Layer-4 自动画面验收不存在 |
| 计费与作品身份 | hold→capture→release；失败与重试按现有幂等边界；`Output.work_id` 保留作品物理身份，原 Output 不被修改版覆盖 |

### 已知实现观察（不是已完成能力）

- `end.logo_url` 当前恒为 None；`accent2` 没有渲染消费者；`FilmSceneUi` 旧 captions 字段仍有残留。
- 部分 `_scene_plan` / `_MIN_VIEWS` 注释与现行约束分层不完全一致；注释不能替代代码事实。
- `on_row_append` 分镜发布座仍无调用点；当前分镜行依赖终封筒，长跨度中流失败时的可见性缺口仍是挂单，不得宣称已经修复。

## 2. 责任与复用边界

- 模型读取素材与当前作品、理解需求、选择工具并作出创作判断；代码负责 id、digest、几何、帧量化、校验、权限、计费和持久化。
- 复用音乐库/beat grid、对象存储、统一渲染、计费三件套、版本与授权闭环、persona voice、`work_id` 和修订基准恢复链。
- 字幕按 film 旁白 cue 与 clip ASR 两条合法来源分化，不为统一而合并。Film 不搬 clip 的可视化编辑器；结构化 ops 是修改面。
- 网页、文字、录屏、相机视频和普通上传视频是素材来源，不是各自一套生产系统。配方与 skill 指导组合能力，不发明第二套执行链。

## 3. CURRENT / PLANNED 总览

| 状态 | 能力 |
|---|---|
| CURRENT（落码；验证分层见 progress） | 网页源与文字源 film；words 与 composite；版本/scene/element id；`update_scene`、`update_element`、`reorder_scenes`、`remove_scene`、`set_music`、`set_voiceover`；当前稿/旧 Output 读取；素材发现；精确动画与独立元素时序；旁白复用；默认无配音与音频独立开关；单体执行与真实 Tasks |
| PLANNED（已拍板，未实现） | `set_aspect` 与画幅变体；voice 设计期钉版、STOCK_VOICES 与试听；自动网页录屏；`typeface` 字体枚举（字号档、对齐、强调样式已 CURRENT）；R5/R6 宏阶段与链式结算；R8-M 统一 10 次设计调用上限（上线必需）；R8-F 完整字段级修复（条件触发）；本地音频速度派生 |
| PLANNED / 需重新确认范围 | R7 residual（独立 compose flag、完整 warning 降级层等）；复杂浏览器操作；知识视频专项。重启条件归 execution §2～§3，不因旧文档出现过就自动开工 |

## 4. 当前硬边界

- 当前 120s 帧帽、屏容、正时长、素材真实区间、元素窗和动画窗都是硬约束；创作默认值与阅读估计不得冒充技术边界。
- 网页片首稿不能直接携带精确时序/样式参数，需先出稿再 `update_scene`；web 导演词汇不含 composite，patch 也没有元素新增 op。
- Composite 元素不与音乐 beat grid 联动；节拍对齐跳过组合幕两侧切点，保留幕长和元素时间窗；不支持变速、循环、尾帧填充、从头重播或自由 CSS。文字元素 ≤4 行、每幕 ≤6 元素等当前帽以 §7.8 为准。
- 图片输入用于素材截图/上传素材理解；已交付成片的自动逐帧评审不在当前能力内，人工动态看片与试听仍是独立验收。
- 本地 `FILM_EDITS_ENABLED=true` 不是生产上线；生产默认关闭，启用与部署另行授权。

## 5. 延期设计导航

| 设计 | 当前效力 |
|---|---|
| §8.2～§8.3 字段级修复与统一预算 | PLANNED；R8-M 统一调用上限是上线必需，R8-F 完整字段级修复按条件重启。当前只有有界候选、文字链无进展早停、Chat Film 设计每回合拒绝预算、原子编辑与 begin 终态拒绝，不得称两者已交付 |
| §9 宏执行阶段 | PLANNED；当前执行与 Tasks 都是单体 `launch_film`，重启与结算验收见 execution §4.1 |
| §10.2～§10.4 的变体、指纹迁移与链式结算部分 | 仅对应变体/宏链的段落是 PLANNED；旧版读容忍、旁白 store 与单体计费是 CURRENT |
| 画幅、声音试听、录屏、字体等外部延期项 | 剩余范围、依赖和最小验收以 execution §2～§3 为执行入口；本文只保留必要契约理由 |

## 6. 契约阅读约定

- 版本/digest/schema 新键必须读容忍；`absent`、显式 `null`、显式 `0` 不得混为一谈。
- 当前旅程示例只描述单体执行。涉及 `film_prepare` / `film_narrate` / `film_assemble` 的内容全部属于 §9 的 PLANNED 设计，不是当前运行事实。
- “Decided / 已拍板”不等于“已落码 / 已验证 / 可上线”。任何能力状态与欠账以 progress 的最新快照为准。

## 7. 状态与工具契约

### 7.1 作品 / 版本 / 场景身份

- **Work**（`work_id`，已有）：作品物理身份；版本与产物挂其下；原版本产物永不改写。
- **Storyboard version**：`{version, base_version, created_via: compose|patch|variant, change_set, content_params{focus,language,voiceover,music_mood}, constraints_choice, scenes[带稳定 scene_id], content_digest, execution_snapshot}`。存储座位不变（活设计 = pending_brief；执行血缘 = run.context；恢复 = `resolve_film_revision_base`），**不新增版本表**（寻址需求已被恢复链覆盖；版本浏览 UI 出现时再立）。
- **scene_id**：出生即分配（compose 时模型给语义 slug 或代码兜底 `s1..sN`；slot 模式用骨架 key）；**重排不改变 id**；legacy 板读容忍（无 id → 位置派生，下次 patch 一次性升级）。
- **digest 两级**：整板 content_digest = 全板 canonical dump（含顺序——重排是有意义变化，digest 应变，`storyboard_content_digest` 2728-2748 的 list 序敏感已满足）；**场级 digest**（新增）= 单场 canonical dump 的 hash，与位置无关——复用与 diff 的身份。
- **参数与指纹（CURRENT）**：canonical 参数包含 focus/language/voiceover/music_mood/aspect，文字源还钉原文与命名形状；aspect 当前仍在内容指纹内。局部编辑由显式 op 表达意图，路由不反推“变体”。
- **画幅变体（PLANNED）**：未来把 aspect 移出内容指纹，纯呈现 delta 走 `set_aspect` → 同内容版本 + aspect override → 新 run/Output（同 work_id），并携带取景调整与 provenance。未实现前不得按此路径宣称成功。

### 7.2 工具契约

**`design_storyboard`（唯一创作/修改入口，不新增 chat 工具）**增两互斥形：

```
edits: list[FilmEditOp] | null   # patch 路径：对 base 版本的结构化编辑
# edits 空 = compose 路径（首稿；或带 specific_instruction 的开放重编排）
requirements: {total_seconds?: [min,max], scene_count?: [min,max]} | null  # 仅用户明确点名时钉
# 新增可选钉：base_output_id（@output 提及已支持）→ 确定性解析 base 版本+digest
```

**CURRENT FilmEditOp（六个：`update_scene` / `update_element` / `reorder_scenes` / `remove_scene` / `set_music` / `set_voiceover`；`insert_scene` 不是当前 op，compose 可增删场景）**：

| op | 字段与校验 | 失效推导（按实际变化，不按 op 名） |
|---|---|---|
| `update_scene` | scene id；view/frame/seconds/focuses/narration/文案槽；words 的 dark、时序与样式字段。视图/元素必须存在，文案接地，时长与动画窗合法 | 场 digest 变 → 仅 narration 文本变的场重合成；seconds/结构变 → 时序重算；改时长不改旁白文本时先复用并检查窗口适配 |
| `update_element` | scene_id + element_id；按 kind 修改文字/媒体内容、rect/fit/z、源区间/播放窗、keep_audio、时序与样式；不适用字段具体拒，不能换素材 | 未触碰元素不变；只按真实变化重查时间窗、音频和渲染依赖，详见 §7.8 |
| `reorder_scenes` | 全 id 排列，不重不漏；EMPTY_CHAPTER 按新序重查 | 场 digest 不变；逐场重查窗口适配，时序重算重 snap |
| `remove_scene` | 删除后结构仍合法 | 重排与音频依赖按新板重查 |
| `set_music` | mood 或显式 `off`；`retime=keep_cut\|recut`；曲目与节拍网格可解 | keep_cut 保帧；recut 重 snap/reveal onset 并逐场重查音频窗口；音频本体优先复用 |

**PLANNED：`set_aspect` 不在当前 schema 或 op 词汇中，aspect 仍在 canonical 内容指纹内。** 画幅请求当前诚实拒绝；变体契约与验收归 execution §2，不能经导演重设计冒充。

`set_voiceover`：`false` = 关配音（纯减法）；`true` = 重开配音——合成/复用版本**既有** narration 行，零重设计。零旁白行的板开配音 = 结构化内容缺口（`voiceover_needs_narration`），先写旁白行再开配音；不得把内容缺口冒充 TTS/声音故障。

**应用语义（系统座）**：ops 有序、原子应用于 base 版本的内存拷贝 → 有效约束校验 → **成功才提交新版本（version+1），失败保留原有可用版本**（零部分落库）。未触碰场景字节级不变由构造保证（系统应用，非模型照抄）。compose 路径的保留核验**不依赖模型自报 kept/changed 自洽**：系统按 scene_id 独立比对场级 digest，kept 集合外的实际变化全部进 change_set 呈现（用户「其他内容不变」类要求由系统核验背书）。整批应用完成后统一判变（内容/参数/存活执行意图三者皆无变 = `unchanged` 拒，不创建无意义版本与制作任务——op 前后可抵消，故只在最后判）。

**`copy_slots` 文案形状**：words 文案只接受 `{"lines":[...]}`；字符串不得拆成单字符列表，嵌套 `words` 或其他错误形状必须明确拒绝。words/lines 单位切换时，旧非空 timing 必须在同一 op 重设或清空。

**修订次数**：产品层没有修订轮数上限；`max_iterations` 只是单回合工具执行预算，不得变成整段对话的修订次数限制。

**base 引用协议（目标版本匹配的接线律）**：`expected_base_digest` 是**读取时刻**服务端铸造并记录的基准引用（读取座呈现当前版本时随响应返回 `film_version_identity_digest`，模型随 edits 原样传回；编造/过期引用在执行时必不匹配 = 安全失败，故「不信模型自报」= 不接受模型编造的基准，而非执行时重算一个恒匹配的期望值）。执行时核对当前解析 base 与该引用一致才应用；提交新版本前再复核一次（并发回防： committed 世界与读取基准按**全身份**比对——内容 + canonical 参数 + 有序场 id + 版本号 + 冻结时间轴三元组，同一 `film_version_identity_digest` 座铸造（`committed_film_state_identity`），版本号或内容 digest 单独相等永不证明身份相同）。读取时无 pending、随后出现并发 pending 的语义：出现的 pending 与读取基准字节级同一版本状态（同号同稿同参数同冻结态）才可发布，其余一律诚实丢弃并提示重读；committed 行无法证明身份（板/参数/版本缺失或损坏的 legacy 行）同样丢弃——可恢复的（digest 从板自重算、legacy 场 id 位置派生）正常比对。发布前检查还要求本 draft marker 仍在 staleness 预算内（自身过期 = 所有权失效，fail closed 不覆盖接管者）；提交写入骑回合事务（版本 + 呈现同提交），检查→提交的残余窗口由 marker 协议 + 活性前提收口。**禁止用刚解析出的 base 现算期望值**（自比较恒匹配，防不了过期编辑）。显式 @output 钉旧版本 = 以该版本为 base 的分支语义，按其既定版本策略处理，永不静默换成最新版。

**change_set**（四类变化分列）：`moved`（id+from+to）/ `edited`（id+字段清单）/ `added`/`removed` / `retimed`（id+秒数 delta）/ `presentation`（aspect+取景调整）/ `music` / `warnings`。工具结果同时携带系统变化摘要与共享呈现座生成的完整当前版本事实；回复先列本次变化（文字修改含精确前后文），再展示完整 Markdown 分镜表、累计制作设置与具体未解决项。模型不得用旧表加差异自行重建当前表。内部 `scene_id`、`base_ref` 与 digest 不上用户面的分镜表。

**Chat 的 Film 执行闭环**：只认「已呈现版本 → 既有提案/报价 → versioned Start」。`edit_graph` 对既有 `launch_film` 节点做 `edit_prompt`，或解析出的 run 子图包含 `launch_film`，均在 graph savepoint 提交前拒绝；通用 chat run dispatcher 复用同一 guard 作后挡。普通非 Film wiring 的 continuation/dock 行为不变；typed `/generate` 与 legacy fresh orchestration 不被此 Chat 专门外卡误伤。

**设计拒绝的有界终态**：`design_storyboard` 的当前拒绝与上一拒绝事实的工具名、kind、detail 完全同签名时，在第 2 次失败即以独立的 `no_progress_tool` 终态停止；不同签名允许继续修复，但**同一回合累计第 3 次 Film 设计拒绝无论签名都停止**，不再发起下一次模型调用，也不转整稿导演。该计数是本回合失败预算，accepted read 或成功设计不清零；它不是 R8-M 的统一嵌套 LLM 调用预算。Chat 收尾明确区分本回合是否已保存过版本、是否开始制作，旧版本与旧成片保留；其他工具与其他 agent 的默认重试不变。

**冻结时间轴 = 版本状态**（失效推导的同一法则延伸到执行面）：已确定的切点（已执行版本的 spec 逐场帧 / 草稿版本的冻结帧）随版本**继承**——任何不动时间轴的批次（无 moved/removed/added/retimed、无存活 recut）继承 base 的切点，不因本轮是否出现 `set_music` 而丢失；结构变化或存活 recut 合法丢弃，run 重新 allocate+snap。基准恢复链路携带切点来源（`film_cut_state` = spec/kept/draft/unreadable）：`kept` 也包括 Start 投影进 `run.context` 的冻结切点——**run 在 Output 创建前失败不丢冻结状态**（无 Output ≠ 普通草稿）；只有确无冻结状态的普通版本才按 draft 规则用其可信的已呈现计划时间轴；**已执行作品 spec 缺失/损坏、或冻结状态损坏/keep_cut 指令无帧 = 实际切点不可恢复，保时间轴的编辑结构化拒绝（`base_cut_unreadable`，指引重读或显式 recut）——永不静默重算冒充原片**。run 消费门 = `film_kept_frames` 在场即 fail-closed 消费（keep_cut 指令无帧 = 半写信封同罪），旁白 flex 同门冻结。

**读取座（编辑模型的眼睛，§六的落地）**：
- `get_output_spec` film 分支：当前版本事实（版本/digest 前缀/scene_id/类型/秒数/帧数/视图引用/取景文本/旁白状态/音乐/画幅）+ 时间轴来源标注（已执行 spec 帧 / 冻结 kept 帧 / 计划轴——计划值永不标成已执行值 / 不可恢复点名）+ 候选视图清单（page·shot·heading·used-by 场景映射·asset id）。页面座 = `load_storyboard_pages`（与编辑校验同座，(page,shot) 引用同义）；fold-only 页（pre-B1）如实退化为仅 fold。
- **图片携带（CURRENT）**：读工具结果可带压缩图（`ToolObservation.images` → loop 的 role:tool 消息 content parts）；MiniMax tool-role 图片已有真实 POSITIVE 验证，synthetic user 消息不是默认路径。预算：每次 ≤12 张 ~640px 缩略图；`views` 选择子点名读取，恰好一张 = 1280px 高清；超预算显式报错并给补救路径，**不静默丢图**；缺图/未存图/读取失败分述。图片与候选清单随编辑能力门控同闸，chat loop max_iterations=12 容纳「读图→改→再改」。**图片范围 = 素材截图与上传素材**；已交付成片的自动逐帧检查不在当前能力内，人工视觉验收见 §14。

### 7.3 约束四层

| 层 | 内容 | 违反后果 |
|---|---|---|
| L1 执行/安全硬约束 | 事实文案引用可解析且接地；focus 元素存在于所指视图且未遮挡、永不裸坐标；fps=30；FILM_MAX_FRAMES=3600 帧帽；每幕结构下限帧（渲染器行为法）；音频流承诺；配音承诺 fail-closed（NARRATION_MISSING） | 硬错误 |
| L2 渲染表达限制 | 8 场景型（含 composite）/ 相机 walk 模板 / plate 2..4 卡 / backdrop 枚举 / 字幕 cue 烧录 / 硬切转场 | 硬错误（新增表达能力 = 渲染施工） |
| L3 用户明确要求 | 时长目标/画幅/语言/静音/保留范围——结构化钉入 brief | 覆盖 L4 |
| L4 配方默认值 | web 弧配方、70–118s 总时长、8–20 幕、per-type 秒带、plate≤2；文字源默认值见 §7.6 | **agent 创作选择可覆盖**（基于素材与目标判断，在方案中呈现所选）；不得把 agent 选择标为用户要求——版本记录 `constraints_choice.source: user|agent|default` |
| 质量提醒降级（PLANNED） | REPEATED_VIEW / PADDING_SCENE 当前仍由 validator 产生硬违例；降为 warning 属 R7 residual，未实施 | CURRENT = 硬错误；只有未来明确落地 warning 通道后才可改为不打回 |
| 保持硬错误 | EMPTY_CHAPTER（章节卡后无**实质内容** = 影片自身结构说谎；实质 = ui walk 或 plate 等现有场景型，不把网页 walk 固定为唯一章节内容，新场景型问世时同席重估） | 硬错误 |
| 素材预检 | 引用合法性（ui 场所指 page/shot 必须存在）+ 零可用视图不烧 LLM 的诚实预检；素材单薄 warning 属 PLANNED | 当前按真实引用与可用性分层拒绝，不恢复全局 `_MIN_VIEWS=4` 硬门 |
| 旁白帽（语义统一） | 字符/秒 = **估计规则**：当前设计期走有界候选修复；字段级定点修复是 PLANNED（§8.2）。执行真值 = 实际合成时长（ADR-136 阶梯+弹性；装不下 = 诚实失败点名场景） | 设计期有界修复；执行期硬 |

网页 manifest 的逐字 grounding 只约束**屏上文案**；narration 可以用自然言语复述已有页面事实，但不得引入无来源事实。来源展示必须区分页面与章节，不得用重复域名代替实际来源。

### 7.4 兜底边界（不变，重申）

`fixed_direction` 仅 worker 无人值守道且仅首次生成；修订/变体/设计旅程永不兜底——失败 = 诚实拒绝，当前已呈现版本保持；生产 run 只执行被引用版本、漂移即停；永不静默修剪文案/替换素材/换固定骨架冒充成功。

### 7.5 音频三态与试听（ADR-138）

**三态语义**（「参数可选」是产品语义，不是把执行字段全变 nullable）：

| 态 | 语义 | 实施座 |
|---|---|---|
| 未指定 | 按配方选默认值，制作设置如实呈现所选 | canonical params 缺省 → 解析链现状；完整「制作设置」读取行（真实 voice_id 与来源 / 音乐 / 画幅）是 PLANNED，当前只陈述可证明字段 |
| 明确关闭 | 真实状态，persona/默认值永不重开 | `voiceover=false` 已是真状态；音乐增显式 off（参数语义），`resolve_film_music` 的 mood→brand→calm 链遇 off 短路——关闭不得回落为默认 calm |
| 明确选定 | 版本与执行同一选择，读取能说真实配置 | **voice 解析上移设计期**（`resolve_film_voice` 同座——persona voice block → 选定 stock → house narrator；先例 = 设计期解析音乐 `film_snapshot_track`），`voice_id` 钉入版本 params/执行快照（与旁白复用 content_hash 的 voice_id 同键）（**延期未实施**——现行 = 合成期解析 persona voice block，声音未钉版进版本）；音乐选定 = 既有 mood 钉版 |

- **解析优先级（一条链，全音频参数同律）**：用户明确选择或明确关闭 → 既有版本已钉的选择（修订/变体继承）→ persona/默认回退。明确关闭是终端态——后续版本继承它，persona 与默认值**永不重新打开**被关闭的项。
- **声音选择契约（PLANNED）**：设计期选择/修改、真实 voice_id 读取、版本保存与执行快照五面必须一致；当前只有既有 set_voiceover 与合成期 persona 解析，未完成设计期钉版。未来执行只消费钉入的 voice_id，不临场换成另一声音。
- **mood ≠ 曲目身份**：music_mood 是创作偏好标签；试听、版本与成片绑定的是**具体曲目/资源**（track id + 文件），执行快照已钉 `track_id`——同一 mood 的库内换曲不改变已钉版本。旧版只有 mood 的数据走明确兼容路径：按 mood 解析当前曲目并在版本上补钉曲目身份，解析不出则如实按未钉处理。
- **旁白复用依据实际合成配置**（content_hash = 归一化文本 | 解析后的 voice_id | language | 合成配置——§10.1），永不依据展示名或未解析的 Auto/默认标签。
- **声音目录**（PLANNED，重启合同见 execution §2）：STOCK_VOICES 最小注册表（少量系统声音 id + 名称 + 语言/性别标签）——注册表纪律同 TOOL_REGISTRY（静态 dict 随代码部署，非插件平台）。
- **重开配音不强迫全片重设计**：`set_voiceover(true)` 入 op 词汇（旁白文字 = 版本既有 narration 字段，直接走合成/复用，零重设计）。
- **试听**（PLANNED，重启合同见 execution §2；当前不构成任何前置）：用户要求「先听一下再决定」⇒ chat 给出**真正可播放**的样例并等待选择——只报名字不算试听完成。样例来源 = **优先复用已有资源**（已有样例、既有库曲目文件、既有版本已合成的旁白段），都不够时按需生成**短样例**（明示实际调用成本）；**不把完整预生成样例库作为前置工程**。试听选择钉入版本（`voice_id`/mood 同一配置进执行快照）——试听一种、成片另一种 = 契约违反。试听 UI 骑结构化卡片面（助理消息 markdown 不渲染裸 HTML，只发链接文本不可播放；先例 = 锚卡族 output_refs 投影，扩 audio kind）。**授权**：用户明示先试听/先审阅 ⇒ 不得提前制作（hold 语义覆盖该请求）；用户要求直接制作 ⇒ 不新增强制确认步骤（ADR-117 不动）。试听不产生整片旁白。

### 7.6 文字视频（ADR-138，CURRENT；剩余枚举见 PLANNED 总览）

- **素材源抽象**：分镜来源 = 网页 manifest **或** 用户文字稿，二源同型进编排；文字稿不伪造网页接地——validator 的接地语料 = 用户文案本身（`validate_storyboard` 的 pages/corpus 参数按源分派）；出生门按源替换（文字源无 `_MIN_VIEWS` 预检，改零文案诚实预检 + 素材可行性预检，见下）。**不另建文字视频系统**——版本/编辑/音频/执行/渲染/计费全复用；素材源抽象与自由编排共用同一契约。
- **方向拍（对话入口）**：文字片与网页片同构三拍——方向拍 → 分镜拍 → 方案拍。**逐字展示与改编是用户意图选择，不是素材输入后的隐含默认**：用户贴文/指向文字但作品方向未定（逐字上屏还是提炼改编、片子的任务与篇幅重点）→ 先读材料、给出一个带理由的建议、问那一个最改变作品的选择（`ask_user` 一词可答选项或 `answer` 平问）；其余参数（颜色/字体/幕数/音乐）走合理默认并随方案呈现，永不一次问齐。明确指定（"全文保留做成 20 秒竖屏文字片，先给分镜"）直接设计不重复问；明确委托（"你决定，直接做"）在委托范围内推进。材料、设计意图、制作意图是三个不同事实——`production_intent` 只管开工，方向未定时任何档都先讨论。
- **文字输入双模**：① 用户提供原文且要求逐字保留（`verbatim=true`，零改写法）；② 提炼改编或用户仅提供创作需求，由 agent 写稿再编排（`verbatim=false`）。② **不得被「零文案」预检直接拒绝**——零文案预检只拦「既无原文也无创作需求」的空输入；② 的接地语料 = 生成的文案本身（生成稿落库后即用户文案同律）。输入角色三分：用户原文 / 创作要求 / 生成稿——版本记录区分三者，不混淆来源。不建知识检索或来源管理平台。
- **命名形状参数三态**：开放重稿中的 `target_seconds` / `scene_count` / `group_chars` 以字段 presence 区分——省略 = 继承 base，显式 `null` = 清除该约束，给值 = 覆盖。清除后 canonical params 不再携带该键；不得经 null 读容忍吞成「省略」。patch 与 compose 参数仍互斥，清除形状约束走开放重稿，不把 patch 扩成第二套 compose。
- **编排与逐字律**：模型决定分段/持续时间（改编模式连出现顺序一并决定）；逐字保留 ⇒ 文案槽零改写、**每行被引用恰好一次**（装配期确定性覆盖校验——漏引 = 静默删字，重引 = 编造，点名行号拒）且**引用必须按文本自身顺序升序**（顺序半边同为装配期确定性校验——更细的引用粒度使意外乱序机械可达，逐字 = 原文自己的顺序，无「用户另指顺序」例外）；允许视觉换行；不允许擅自增删文字、替换措辞、重复句子或改变出现顺序；文案超出排版/时长能力时给出**具体问题**（哪一段、超出多少、可选的处置），永不静默删字、永不靠无限缩小字体硬塞。
- **引用单元（manifest）**：段落 → 句子 → 子句边界（，、；：,;）**每界自立一行**（贪心多子句打包会使「按逗号拆成更多屏」机械不可表达：打包行在 fit=full + 恰好一次覆盖下不可拆）→ 词原子帽切只接超帽单子句（拉丁词不切断——切断点落在词中间退到词首，单词自身超帽才硬切，与显示折行的超帽 token 同律）。**引用单元 ≠ 一屏**：导演把连续行**组合**上同一屏（一段多引），用户点名拆分时一行一屏；幕数上界 = 行数随之细化（逐字片可拆到子句粒度）。分段永不改字符；原文随版本钉存，语料锚点从原文投影，不靠事后猜空格恢复。**抄录漂移注记**：逐字重稿重述 `text` 且与 base 版本钉住文案有出入 = 观察文本附子句级诚实注记（`text_source_drift_note`，呈现永不称「原文一字未改」；有意改文案合法，永不硬拒——pin 只在 text 缺省时继承，重述按法被逐字信任，故漂移必须被点名而不是被拦截）。
- **时长约束分层（真实技术边界与阅读估计分开）**：
  - **硬律（真实技术/数据界，无条件，代码依据在座）**：总时长上界 = 渲染帧帽 `FILM_MAX_FRAMES / FILM_FPS` = 3600/30 = **120.0s**（分配后帧帽护栏同座把守）；屏容 ≤4 显示行（引用行必须一屏放得下——屏幕溢出是真实界）；动画时序不越幕窗；单幕时长为正（零/负窗渲不出任何东西——非法数据，编辑层与 validator 双座把守）；半秒渲染格（量化后场景归零 = 真实拒绝）。
  - **阅读时间估计 = 默认节奏推荐，永不是技术边界**：未点名节奏时 allocator 按估计地板排（默认建议较长、可读）；**用户明确点名更短时长 = 合法选择**——地板按比例双向缩放（更慢或更快），呈现层 pace note 如实标注「快于自然语速 ~Xs」，永不拒绝、永不静默；逐幕 patch 同理落地。幕数带 2–30 与总时长下界 5s = 创作默认（建议与冲突发现，validator 不据以拒绝；web 源 70–118s / 8–20 幕法律不动）。默认算法给出的估计时长只是其中一种可行方案，不是唯一合法方案。
  - **冲突发现（估计的合法用途）**：点名时长超 120s 帧帽（两模式同律）、或点名幕数落在真实可行区间（最密打包幕数 .. 行数——**两界均由逐字全覆盖律派生，仅 verbatim**）之外 = 预检诚实命名冲突；**未点名时长**且默认节奏排不下（估计地板和 >120s——**同为 verbatim-only**：估计量的是输入原文）= `film_text_beyond_reach`，文案给出全部出路（删短/改编/拆集/**点名时长按更快节奏排**——该出路真实存在：已点名 ≤帽 时长时预检不据估计拦截，由分配器缩放到用户值）。
- **素材可行性预检（模型调用前）**：贪心最密打包给出全片最小足迹——默认节奏地板和超 120s 帧帽 ⇒ `film_text_beyond_reach`（verbatim-only）；点名时长超帧帽（两模式同律）、或点名幕数落在**真实可行区间**（最密打包幕数 .. 行数——下界外装不下文案是屏容硬约束，上界外有幕无行可引；**两界仅 verbatim**）之外 ⇒ `film_text_target_overflow`。**改编模式（verbatim=False）的输入 = 参考材料：输入长度 ≠ 输出篇幅**——模型把参考提炼成自己的文案，预检不设任何输入派生的幕数界或阅读估计界；候选的真实限制（屏容/元素窗/素材区间/总帧帽）由装配与真实 validator 在候选上判，不在此估算，校验不因此放宽。**真正不能合法表示的素材在烧模型之前识别**——永不一边要求完整引用、一边让模型反复拆一个不可拆的引用。梯级内同一违例签名集连续两候选复现 ⇒ 无进展早停，不再整篇重滚。失败解释三键分派：素材超限（`film_text_beyond_reach`）/ 点名目标真实冲突（`film_text_target_overflow`）/ 梯级耗尽（`film_text_ungrounded`——文案本身没问题，是编排没通过校验；系统内部约束矛盾永不包装成用户"字数、时长、幕数没给对"）。
- **排版枚举**（入分镜契约，L3 枚举纪律——不开放自由版式）：对齐枚举（`align` left/center）/ 字号档枚举（`size` small/medium/large，medium = legacy 168px 签名档；words 幕 120/168/232，文字元素 56/80/120——双端同一 `TEXT_SIZE_PX` 表，容量校验按像素档估算（1em CJK / 0.5em latin 前进量的估算口径，非真实字体排版测量））/ 强调样式枚举（`accent_style` chip/color——chip = 既有 `*word*` 反白块，color = theme accent 色文字；文字元素另有整行 `tone="accent"`）**已落码**；typeface 枚举未建（中文可用为先，vendored Noto Sans SC 粗体为默认；新增字体随渲染镜像 vendor）。换行与溢出 = renderer 负责收缩/换行不裁字；超容量 = 校验具体拒（哪行、超多少显示单位），永不静默截字。
- **文字运动枚举**（作用于文字画面本身，不只是网页相机）：静止 / 缓慢推近 / 缓慢拉远；入场效果 `enter_style` = rise（默认淡入+上移+模糊）/ fade（纯透明度）/ slide（确定性纯平移，无透明度渐变、无模糊、精确起止帧）。`enter` 的 lines/words 决定组织单位，`enter_style` 决定每个单位如何出现；二者正交。spec 字段 = 枚举值，renderer 按枚举实现（remotion spring/interpolate 既有机制）。
- **背景**：纯色枚举（黑/白现状 + 少量品牌色档）；既有图片/logo 直接复用（persona brand 媒体既有座）——不扩建素材平台。
- **模板 = 默认配方**：文字视频配方卡预填 promptTemplate 即全部发射载荷——不建模板市场。

## 7.7 场景/元素/动画时间最小契约（ADR-139 §4，CURRENT）

agent 能读取、修改并呈现**确定的动画时间安排**（「第二幕开始后 0.3 秒，文字依次出现，相邻字符间隔 0.12 秒，每个字符入场持续 0.25 秒，随后停留到本幕结束」是已实现的合法需求），而不只是挑选固定效果。

**契约面（words 场型六字段，紧凑参数，代码展开为帧级安排）**：

- `enter_start`：首个 token/整行相对幕开始的秒偏移（缺省 0）。
- `enter_interval`：相邻 token/整行的开始间隔。words 缺省 = legacy 公式 `clamp(floor(dur*0.6/total),2,4)` 帧；lines 缺省 = legacy 8 帧。
- `enter_duration`：单 token/整行入场持续（参数化时缺省 12 帧；零 = 即时出现）。
- `enter_hold_until`：停留终点（缺省 = 幕末；显式设置 = 离场时刻——文字在该帧离场；配 `exit_duration` 时文字在终点前的末段淡出，背景永不随之淡）。以上四参适用于 `enter="words"` 与 `enter="lines"`；缺省 enter = lines。未带任何时序键的旧 lines 板仍走原固定 8 帧与无参 spring，不改变数值行为。
- `exit_duration`：退场淡出秒数——占文字窗的最后一段（终点 = hold 端点，缺省 = 幕末/元素窗末）；只淡文字，**背景永不淡**（words/composite 幕的背景由 Film.tsx 恒透明度铺底，Fade 罩只罩内容——深极性幕在幕界不再向白根画布闪白）。
- `motion_start` / `motion_end`：既有 push/pull 的起止窗口（缺省 = 全幕 [0, dur]），需 motion 为 push/pull；`motion_scale` = 推/拉幅度（缺省 1.06；落字后继续轻微推近 ≈ 1.02–1.04），同需 push/pull。
- 样式四键（words 幕与文字元素同律）：`align`（left 默认 / center——居中同时把推/拉原点换到 center center）、`size`（small/medium/large 字号档）、`accent_style`（chip 默认 / color）、`enter_style`（rise 默认 = 淡入+上移+模糊 / fade = 纯透明度 / slide = 纯平移——无 opacity ramp、无 blur，确定性插值到精确结束帧；入场效果与 enter 的组织维度正交：lines/words 定「谁一起出现」，enter_style 定「每个单位怎么出现」）。整组同时纯淡入 = `enter="words"` + `enter_interval=0` + 短 `enter_duration` + `enter_style="fade"`；严格逐行纯滑动 = `enter="lines"` + `enter_style="slide"` + `enter_interval>=enter_duration`，前一行完全进入后下一行才开始。interval=0 只保证同时，不去上移/模糊。
- **Fade 罩所有权**：外层幕罩永不二次改变显式元素动画——words 幕带显式入场（时序键或 enter_style）时外层 fadeIn 退场、带 exit_duration 时外层 fadeOut 退场；composite 幕无幕级罩，**罩逐元素挂在元素窗上**（默认 7f 只罩贴幕边的元素边——at=0 的入场边与窗末=幕末的离场边，与旧幕罩覆盖范围一致；显式入场/退场动画的元素该方向罩退让）——一个文字元素的淡出配置永不牵连同幕其他视频/图片/文字。
- **presence 三态**：absent = 保持现值；explicit null = 恢复默认；explicit 0 = 真实零值（`is not None` 判定，真值性永不吞零）。在 words/lines 间切换组织单位时，同一 op 必须显式重设或清空每个既有非空 enter timing；否则以 `timing_unit_change` 拒绝，旧 token cadence 永不静默按 line cadence 解释。

**展开律（代码座，LLM 永不逐字符输出时间戳，不建每字符数据库轨道）**：

- 秒→帧唯一转换：**就近取帧、半点进位**——双端同一 float64 公式 `floor(s×fps + 0.5 + 1e-9)`（Python `film_seconds_to_frames` ≡ TS `secondsToFrames`，非「各自 round 声称等价」；1e-9 epsilon 稳住恰好半帧边界如 0.25s→7.5→f8）。误差纪律：**单值量化误差 < 半帧**（30fps 下 <0.017s），但逐 token/line 间隔的量化偏差随单位数**线性累计**——呈现层如实给出每个值的请求秒 → 帧 → 实现秒（0.12s→f4 实渲 0.133s），并预报**最后一个 token/line 的入场开始/完成帧与秒**；整段序列的诚实披露 = 计算后的落点，永不把单值亚帧误差说成整段累计误差上限。
- words 的拆分单位复用 `tokenizeWords` 语义：CJK 逐字、latin 按词；accent 边界先切分（chip 边缘 = token 边缘，latin 串不跨 chip 合并）。lines 的单位 = 当前版本完整显示行，不再经 tokenizer。
- **超出本幕时长 = 诚实报告**（哪一幕、需要多少、超出多少 + 可选处置），永不静默压缩/丢弃——逐字律同一教义。设计时按 authored 秒校验，`build_film_spec` 按**实际分配帧**复校（卡点/弹性改动后的溢出同样拒）；hold ≤ 最后 token/line 起点 = 拒（零时长/零间隔退化形态永不出不可见板）。
- **文案修改后**：受影响幕的时间安排按规则确定性重算；无法容纳 = 上述诚实报告；**未修改幕的时序逐帧保持**（op 作用域保证，测试锁定 digest 逐字节不变）。
- **旧 spec 读容忍**：缺省新参数 = legacy 固定公式行为逐字节不变（十二键入 `_LEGACY_ABSENT_SCENE_KEYS`——时序六键 + exit_duration/motion_scale + 样式四键：null 读缺席，显式零参与 digest；renderer 无任何时序键时走旧公式 + 无参 spring，无样式键时 = 左对齐/medium 档/chip 强调/rise 入场）。
- **独立性**：配音、音乐与视觉时序互不耦合（无音乐无配音链已帧级实证）。
- **动画种类 ≠ 时间参数**：「逐字出现」不等于「逐字跳起」——时间参数只调既有枚举的节奏，不冒称新动作；新动作枚举是独立的渲染施工。

**接线（已贯通的实际链路）**：Chat 需求 → 工具参数（design_storyboard 文字源首稿 / update_scene op）→ 版本草稿 → 读取事实（get_output_spec 逐场行带 `seconds→fN` 落帧）→ 编辑 → 累计方案呈现（`words_timing_clause` 一座三骑）→ Start/编译（时序 = 分镜内容，骑版本钉的 `prepared_storyboard` 进 `LaunchFilm.run`，**不经 launch slot 白名单**——slot 白名单只管 launch 参数族）→ spec（set 才携带，显式零在内）→ renderer。契约核对面：schema 双端 → digest 律 → 呈现行 → spec 序列化 → renderer 消费 → run_review 对账（`_SCENE_CONTENT_KEYS` 含时序八键 + 样式四键；元素对账为排除制，新键自动入比对）。UI 场景的 `page` / `shot` 是烘焙前选择器，spec 已解析为 `url` / `image`，选择器缺失不作字段漂移；选择器身份由 storyboard digest 核对。只有实际交付的 film 才进入这份一致性对账，未交付渲染只报可用性事实。

**已知边界**：**网页片首稿目前不能携带时序/样式参数**（`FilmDirection` 冷启动无此字段）——网页片必须先出稿、再经 update_scene 定点编辑加入；文字片首稿可直接带。不建时间轴编辑器、通用关键帧系统、字体目录；新增动作枚举仍需独立的渲染施工与双端契约，不能靠时序参数冒充。参考片只作观感锚，不阻塞开发。

## 7.8 组合幕（composite）——媒体元素 + 独立文字元素（ADR-140）

录屏、相机视频、普通上传视频首先都是视频素材；「录屏产品演示」「纯文字视频」「网页介绍」是创作目标/配方，不各自拥有重复的裁切、文字动画、版本和修改系统。scene 仍是叙事组织与用户定位单位；`composite` 幕 = 主题色背景（`dark` 两档极性，与 words 同一词汇）+ 有序 `elements` 列表。「视频+左标题」「录屏+底部文字」「图片+逐字文字」是同一组合结构的不同元素配置，**共享同一文字实现**（渲染侧 `TextPlane` 单座，words 幕与 composite 文字元素同骑——tokenizer / accent chip / enter 时序 / motion 全部复用，无第二套文字动画）。

**元素模型**（判别子 `kind`，封闭三枚举）：

| kind | 内容字段 | 时间字段 | 空间字段 |
|---|---|---|---|
| `video` | `asset`（素材 id，代码解算存储 key——模型永不写 URL，ui 幕同律）+ `keep_audio`（默认 false）| `source_start`/`source_end`（**源素材秒**）+ `at` + `duration` | `rect` + `fit`（cover/contain）+ `z` |
| `image` | `asset` | `at` + `until` | `rect` + `fit` + `z` |
| `text` | `lines` + `tone`（light/dark/accent——accent = 整行 theme accent 色）+ `copy_text`（语料锚点，words 幕同律）| `at` + `until` + enter/motion 六参族 + `exit_duration` + `motion_scale` | `rect` + `z` + 样式四键（`align`/`size`/`accent_style`/`enter_style`）|

- **元素身份**：`element_id` 出生即铸（缺席按位置派生 `e1..eN`，scene_id 同一升级律）；身份句柄，永不进内容 digest；编辑/读取以其寻址，永不依赖数组下标。
- **两个时间空间（硬律，同一字段名永不换义）**：`source_start`/`source_end` = **源素材秒**（只存在于 video 元素）；`at`（出现）/`until`（离场，null = 幕末）/ `duration`（video 播放窗长，null = 源区间全长）= **幕相对输出秒**；`enter_*`/`motion_*` 六参 = **元素窗内相对秒**（元素窗 = 文字的"小幕"，enter_hold_until 在元素上不设——`until` 即离场时刻，同一语义；`exit_duration` 在其前末段淡出文字）。秒→帧唯一量化座 `film_seconds_to_frames`（双端同一 float64 公式）；幕开始输出时刻 = 前序幕帧数和（既有顺序时间轴）。
- **区间规则**：源区间 [source_start, source_end) 必在素材真实时长内——时长在册（asset.duration_seconds）即校验；不在册 = 写座（编辑/run）先探测真值（PyAV 容器头，`download_to_cache` 共享缓存 + `_probe_media_dims` 先例；探测精确值钉 `meta["probed_duration_seconds"]`，Integer 列存 FLOOR 仅供展示座）再判，读座只如实报「时长未在册」。播放窗 ≤ 源区间（截尾诚实）；播放窗 > 源区间 = **拒**——无变速、无循环、无尾帧填充、无从头重播。**量化契约（一端一式）**：源端点先量化（`film_seconds_to_frames`，renderer 的 startFrom/endAt 同一公式同一座），默认播放窗 = 量化后的 span（永不量化差值——差值量化可多出一帧 trim 里不存在的画面），显式 duration 量化后 ≤ 量化源帧数；源 span 量化不足一帧 = 空区间拒；任何座不补帧。元素窗必须落在幕窗内：设计时按 authored 秒校验，`build_film_spec` 按实际分配帧复校（words 时序同一双座律；snap/弹性致溢出 = 具体冲突拒，永不静默截断）。元素离场 = 离开画面（背景或下层元素显露），无尾帧冻结。
- **空间**：`rect` = 归一化 {x,y,w,h} ∈ [0,1]（clip-spec layers 同一坐标法），缺省 = 全画面；媒体元素 `fit` = cover（裁切填满）/ contain（完整容纳），作用于 rect 盒内；`z` 整数定叠放（同 z 按列表序，确定性）；媒体未覆盖处显露幕背景极性。不开放任意 CSS，不做自由画布。
- **文字元素**：复用 words 平面全部能力——`enter`（lines/words）/ `motion`（static/push/pull）/ `enter_start`/`enter_interval`/`enter_duration`（元素窗内）/ `motion_start`/`motion_end`/`motion_scale` / `exit_duration`（元素窗末段淡出文字，背景不淡）/ 样式四键（`align`/`size`/`accent_style`/`enter_style`，字号档 = 元素档 56/80/120，容量按 rect 宽度估算且随推/拉幅度收缩——rect 裁切真实存在）；presence 三态同律（absent = 保持 / explicit null = 恢复默认 / explicit 0 = 真实零值）；逐 token/整行排程必须落入元素窗（overflow = 具体冲突拒）。字族不变（不新建字体系统）；每元素 ≤4 行（屏容律同 words，超帽 = 点名该行与超出量具体拒）。独立位置或独立窗口的文字块 = 不同文字元素各带 `at` 窗；同一文字块内整行顺序入场 = 一个元素的 `enter="lines"` + 显式行时序，不拆元素也不伪造停顿。
- **音频三面独立**：视频原声 = 元素 `keep_audio`（默认 false——用录屏不自动开声），只在元素播放窗内出现，源裁切 = 音频裁切（同一 startFrom/endAt，构造保证）；旁白 = 幕级 `narration`（现有合成/字幕投影链不动）；音乐 = 片级床（现有链）。无声需求 = 三者全关。render_probe 的音轨承诺纳入 keep_audio=true 的元素。
- **素材身份与漂移**：版本板钉素材 id；执行快照增列引用素材（id + key + 时长，空集不进 digest——旧快照逐字节稳定）；素材删除/替换/不可读 = run 漂移校验诚实失败，永不静默换素材。录屏与普通上传视频进同一条资产链，无 screen_recording 专属语义；无声/无 ASR 视频合法可用（时长探测不依赖 transcript）。
- **版本与编辑**：元素内容全量入场景 digest（element_id 除外）；新 op `update_element`（scene_id + element_id + presence 敏感字段，kind 不适用字段 = `field_not_applicable` 具体拒）；change_set 逐元素命名字段（`elements.<id>.<field>`），呈现带 now: 行；未触碰元素与同版未触碰场景字节级不变（系统应用保证，非模型自报）。局部编辑只动声明范围——改文字颜色/入场间隔不重排视频、不改文案、不重新卡点。
- **来源模式**：composite 在 web 片与文字片两源均合法（它不是页耦合场景——`TEXT_ILLEGAL_SCENES` 不收它）；文字片的逐字律座位（装配期全覆盖校验 / `_sync_text_source` 语料跟随）对 composite 文字元素同律生效（`copy_text` 锚点逐元素）。
- **出生面（现行法）**：composite 经**文字源设计链**自然语言出生——文字导演的段词汇 = words 段 ∪ composite 段（`FilmCompositeSegment` + 导演侧草稿元素模型，无 `element_id`——代码出生时铸 e1..eN，wire 不教身份句柄）；素材发现 = `list_project_media` 读工具与导演 prompt 同读一座（`project_media_candidates`——项目级 video+image 候选，id/kind/标题/时长（已知或如实未知）/尺寸/可用性，storage key 永不出栈）；组合出生与编辑能力同骑 `film_edits_enabled` 门（prompt 面 + 装配面 + 执行面同门）。幕长代码派生：元素窗帧端（端点先量化同一会计）取最大，向上对齐 0.5s 格、≥1s——装配永不自拒；无界幕（无视频播放窗且无显式 until）= 可修复违例。逐字律全覆盖跨混合段（words 段与 composite 文字元素同一引用宇宙）；`target_seconds` 下 words 幕向（目标 − 组合幕合计）缩放，余量 ≤0 = 诚实拒；**全组合 + 命名总时长 = 帧级符合律**——命名总时长与素材派生总时长经同一量化座比帧数：符合即过；不符合 = 具体差额拒（帧数 + 方向），永不索要 words 占位幕，系统永不静默拉伸/循环/补帧用户的源区间或动画时序。**命名 scene_count 预检只判可证不可能**（复审② + 定点收尾）：最密组合排（6 文字元素 × 4 行 = 24 显示行/幕）为幕数下界，逐字 + 无可用素材时文案行数为幕数上界（全覆盖律 + 无文字幕不可立）——**两界均由逐字全覆盖律派生，仅 verbatim**；**改编模式（verbatim=False）的输入 = 参考材料（输入长度 ≠ 输出篇幅），无输入派生的幕数界或阅读估计界**——候选的屏容/元素窗/素材区间/总帧帽由装配与真实校验在候选上判，显式超帧帽时长仍拒（两模式同律）；`current_text_direction_dict` 全量投影（组合幕不再静默丢失）。**发现面恢复路径（复审③）**：40 行打印帽 = 分页（读座 `offset` 翻页 + 截断行如实告知翻页 offset；`media_more` 截断计数随导演 prompt 如实告知）+ ids 精确选读（`list_project_media(ids=[…])`——帽外素材依然可读）；用户 @ 钉选经 draft 座 `pinned_asset_ids` 提首进导演上下文（钉选经项目查询过滤——外来 id 永不具现，项目权限不借钉选放松）；截断 ≠ 不存在，校验按 id 解算真实媒体宇宙，不以列表成员资格为准。**web 源导演词汇仍不含 composite**（页耦合弧未评估组合出生——patch 链对 composite 完整可用，web 片要组合幕只能经编辑链加不进去：patch 无元素新增 op，诚实边界）。**已知边界**：composite 元素与音乐 beat 网格不联动（snap 只动幕边界，元素窗随幕平移，溢出由 spec 构建复校诚实拒）；视频元素窗随幕时长变化不伸缩（幕变短致元素出窗 = 校验拒）。

## 8. 校验失败与有界修复

### 8.1 现行重试链审计（逐项实证）

| 层 | 次数/预算 | 嵌套关系 | 是否丢弃已有候选 | 依据 |
|---|---|---|---|---|
| provider/transport | tenacity 3 次，指数退避 2-10s；流式只在首 delta 前重试 | 最内层 | — | `minimax.py:423-424,544,717-719` |
| schema 解析 | 每次 agent 调用 1 轮修复（结构化回声） | 套在 transport 外 | 是（同 prompt+回声重新生成整篇） | `agents/base.py:267-284` |
| 多模态降级 | 声明式 1 次纯文本重试（film_director 已声明） | 同上 | 是 | `agents/base.py:155-158,344-358` |
| 语义校验（导演 repair） | 首次 + 最多 `FILM_STORYBOARD_MAX_RETRIES` 次纠错，默认 10 次；总预算 1800s，文字源相同错误重复仍提前停止 | 套在 agent 调用外 | **是——每候选整篇重新生成，回声只带违例文本不带前候选内容** | 全局 Settings；文字/网页编排与估价共用 `MAX_REWRITES` |
| chat tool loop | max_iterations=12（trigger 6） | 最外层（回合） | 守卫拒绝消耗迭代 | `chat/intent.py:325,361` |
| worker 节点 | LaunchFilm retries=0；TransientNodeError 预算 = node.retries | run 层 | — | `storyboard.py:3689`；`orchestrator.py:1531` |
| render | render_max_attempts=3（poison-pill 边界：cap 内可认领，越界终态）；render_concurrency=2；timeout 900s | 渲染链 | — | `config.py:77-89`；`jobs.py:37-43,272` |

最坏嵌套：3 候选 ×（1+1 schema 修复）= 6 次生成 × transport 3 = 18 次传输执行，同烧一个 1800s 预算。**无无限重试**；当前缺口在候选级整篇丢弃——一个字段失败可能让全稿重生成。

### 8.2 字段级有界修复与统一预算（PLANNED）

> 本节混合两项不同优先级的延期设计：统一 10 次调用上限属于 **R8-M，上线必需**；完整字段级修复属于 **R8-F，按真实旅程成功率条件重启**。执行合同分别见 execution §4.3 与 §4.2，不得用 R8-F 延期吞掉 R8-M。

compose 路径的 `orchestrate_storyboard` 改为**保留候选 + 定点修复**：

1. 模型只填判断字段；帧数/几何/cue 时间/URL 全代码派生（现状已满足，不动）。
2. 调用前可行性预检（零可用视图不烧 LLM——保留）。
3. **可解析候选保留**：未通过校验的版本永不发布为执行版本（现状已满足：只在通过时落库）；未通过的内容作为修复基准持有。
4. **两层失败都进字段级通道**（不只覆盖 schema 通过后的语义错误）：
   - JSON 可解析但个别字段不合法（pydantic `ValidationError`，`errors()` 的 `loc` 可映射 scene_id/字段路径）→ 升级为结构化违例，走同一定点修复——**不整篇重滚**；
   - JSON 不可解析（候选不可用）→ 有界整篇重生成（≤1 次，共享同一预算）；
   - 语义校验违例 → 定点修复（现状机制升级）。
5. **结构化违例回声**：每违例带 scene_id + 字段路径 + 错误类型 + 实际值 + 约束（`FilmViolation` 增 `scene_id`/`field`/`actual`/`bound` 字段——现 detail 是自由文本，升级为结构化+人话双载；schema 层 `loc` 映射同一形状）。
6. **定点修复调用**：模型只返修正字段（`repairs: [{scene_id, field, value}]`，小输出），系统确定性合入保留候选 → **重查受影响约束 + 整体一致性** → 过则发布。整候选重新生成只在候选不可解析或整体结构不可用（如视图引用大面积失效）时允许——仍有界。
7. **全局调用预算（明确）**：设计回合一个预算座——总墙钟 1800s（现状不变）+ **总 LLM 生成调用硬上限 = 10 次**（= 初稿 1 + 定点修复 ≤4 轮 + 每次生成随附的 schema 层修复 ≤1 + 整篇重生成 ≤1 的算术上界 1+4+5=10）；所有层共享同一计数，**嵌套层（schema 修复/多模态降级）不得刷新或新设计数**，外层守卫拒绝 / chat loop 迭代不重置该预算；超限即停止并诚实失败。
8. **无进展判据（不仅凭错误数量）**：违例签名 = (scene_id, field, code)；① 同一签名连续两轮复现；② 合入后签名集两轮无变化；③ 一轮修复引入的新违例多于修掉的（倒退）——任一命中即停止并诚实失败（带上当前违例集）。
9. **错误分类**：模型可修复（schema 字段/语义违例）→ 定点修复；输入缺口（素材不足/页面不可读）→ 诚实告知要素材；系统错误（DB/网络/provider 非 schema 类）→ **永不进导演修复通道**——transport 归 tenacity，DB/装配异常直接冒泡为系统失败。

edit 路径无需此循环：ops 拒纯以结构化错误回 chat loop（同字段形状），模型在回合迭代内修复重调。

### 8.3 PLANNED 修复实例（一个字段失败的完整旅程）

素材：三页采集。首候选 12 幕通过 schema；validator 报两违例：

```
- scene[s4].narration: 125 speech units over the ~104 estimate cap for a 8.0s window（估计帽——字段级可修复违例）
- scene[s7].focuses[0].element: "s2e99" not in view (page=1, shot=2) 的元素清单（硬错误）
```

当前路径：整篇重生成（125 个字段全重摇）。PLANNED 路径：

1. 候选保留（未发布）。
2. 修复调用只带两违例 + 相关场景的现状字段 + s7 所指视图的有效元素清单；模型返回：
   `repairs: [{scene_id:"s4", field:"narration", value:"更短的新句"}, {scene_id:"s7", field:"focuses", value:[{at:2.0, element:"s2e4", intent:"feature"}]}]`
3. 系统合入 → 重查：s4 旁白帽（过）、s7 focus 元素法（过）→ 整体一致性（总时长带/重复视图/章节完整）→ 过 → 发布为新版本。
4. 其余 10 幕字节级未动（合入是系统行为）。墙钟：修复调用只输出两行修正 ≈ 秒级，而非整篇 100s+。

## 9. 宏执行阶段

> **状态：PLANNED。** 当前执行 = 单体 `LaunchFilm` 节点，Tasks = 单步真实显示；本节全文（阶段表/计费边界/时间轴所有权/注册兼容）保留作重启设计依据。重启条件与施工合同见 execution §3～§4.1。

### 9.1 为什么是节点边界而不是只拆函数

阶段产出需要**独立持久化**（执行计划/音频索引/spec），失败后恢复不重做已成功阶段的工作；需要**独立重试预算**（TransientNodeError/attempt 计数是步骤机自带）；需要**独立计费结算**（capture 以步骤为单位，失败步骤不 capture 的现行语义按阶段如实生效）；需要 **Tasks 可见性**（步骤行 = Tasks 行，失败落在真实阶段）。这些全是步骤机现成能力；拆成函数则要重建全部。节点形态 = 编译期注入的内部节点（`internal=True` 先例 = `materialize_source`，ADR-043：永不注册为 LLM 工具、用户永不点名）——**agent 面向的创作/编辑工具（design_storyboard）与后端执行阶段是两个层次，内部节点不暴露给 LLM**。

### 9.2 阶段表（输入 / 持久化输出 / 完成条件 / 失败与重试）

| 阶段节点 | 输入 | 持久化输出 | 完成条件 | 失败语义 | 重试 |
|---|---|---|---|---|---|
| `film_prepare`（准备执行） | run.context 的钉版分镜 + digest（**消费确定稿，永不重创作**）；项目 READY 页面 | `run.context.film_execution` 执行计划：页面清单解析 + 音乐曲目/节拍网格 + 意图时间轴（allocate+snap）+ **旁白复用计划**（逐场 hash 查 reuse store：reuse/missing/unfit）+ 逐 aspect 取景调整 | 计划落库 + 漂移校验过（对当前页面重校验，ADR-129 现状保留） | 漂移/音乐不可解/节拍网格不可得 → FAILED（诚实，请求重设计）；DB/存储异常 = TransientNodeError | 瞬时预算重试（幂等：计划重算无副作用） |
| `film_narrate`（准备旁白） | 执行计划的 missing/unfit 清单 | `film_narrations` 行（内容寻址）+ 执行计划补音频引用 + **最终时间轴**（见 9.3） | 每段承诺旁白都有适配窗口的音频 | voiceover 承诺下合成不出 = fail-closed FAILED（现状法）；TTS 传输瞬时重试 | 阶段重试 = 重查复用计划，已合成场命中 store，**天然断点续跑** |
| `film_assemble`（装配作品） | 最终执行计划 | Output 行（type=film，provenance digests + aspect + 调整记录）+ film-spec + `record_media_usage`（film_seconds 计费座）+ `pend_outputs_for_render`（render mirror 出生） | spec 落 Output + 渲染入队 | spec 校验/probe 前置失败 → FAILED；同 spec 重跑幂等清旧 Output（现状 3861-3885 保留） | 瞬时重试幂等 |
| `render`（渲染+校验） | outputs.render_status 认领 | 成片文件 + probe 结果 | probe 过（h264/分辨率/帧数 ±1/音频流） | FAILED + `spec.failure{stage:"probe"}`（现状） | render_max_attempts=3（现状不动） |

`LaunchFilm` 的注册形态**不退役**（最小兼容方案，§9.6）；原单体 run() 的逻辑按上表分家，**零行为新意**（同顺序同校验），只是把中间产物从内存变量变成持久化计划。

**计费边界（保持单体结算语义，不以「失败阶段不收费」宣称政策未变）**：单体时代 launch_film 是一步——中途失败则该步零 capture、钱包零变动。拆分后为保持同一钱包结果：**capture 座唯一 = film_assemble 成功时**（= 单体步骤成功点），金额 = 链累计 metered 成本（prepare+narrate+assemble 各行 cost 之和，经现有 capture_step 的 prior 减法幂等）；prepare/narrate 成功只 meter 落步骤行（observability 可见），**不触发钱包 capture**；prepare/narrate/assemble 任一失败 = 钱包零变动（与单体同点失败一致）；render mirror 语义现状不动（render 失败不退链上已 capture——单体时代亦然）。实现 = 内部阶段节点声明 `capture=False`（orchestrator 在步骤成功处按此跳过 capture_step，assemble 行捕获全链合计）——这是结算语义的真改动点，验收闸 14 锁它。

### 9.3 时间轴所有权（审阅轴 vs 最终轴）

- **审阅时间轴**（设计期呈现读它）：意图轴 = allocate + snap 的结果，由设计拍/Start 快照钉住——呈现稿与执行快照同源（ADR-130 不动）。
- **最终合成时间轴**：`film_narrate` 阶段末定稿（唯一写口）——ADR-136 弹性（无声场零和借帧、donor≤30%/receiver≤40%/Σ帧不变）在此处应用。**允许调整范围 = 弹性界内**；超出 = 诚实失败点名场景，永不静默改轴。
- **两轴关系**：assemble 只消费最终轴烘 spec（含 reveal onset 压网格）；probe 校验最终轴；若 narrate 的移动非零，交付事实如实列出（哪些场次帧数动了、动多少）——呈现时展示的意图轴与成片最终轴的差永远收敛在弹性界内且可解释，不是「呈现一套执行一套」。

### 9.4 新建 / 变体 / 编辑的执行推导（真实依赖，非 op 名路由）

三种 run **同一条四阶段链**；各阶段的工作量由执行计划的实际差异决定：
- 新建：复用计划全 missing → narrate 全量合成。
- 变体（set_aspect）：计划重算仅取景维度；复用计划全命中 → narrate 零合成（其 done 摘要如实报「12/12 幕复用既有配音」）；assemble 烘新 aspect spec。
- 局部编辑：复用计划只列变化场；重排/重卡点后**已有音频逐场重查窗口适配**（适配失败 = 该场进 missing 重合成，或诚实拒并说明）。
- **Tasks 显示** = 四个宏阶段行的真实状态/耗时/成本 + done 摘要带复用计数；失败行落在真实阶段；恢复重跑只重做失败及下游阶段（上游产出已持久化）。不按场景拆 step，不造空壳节点凑行数。

### 9.5 画布形态

画布**保持一个作品生成节点**（launch_film，node_type=video 词表不动）；阶段是 run 内部步骤，不上画布；画布节点状态 = 链的 rollup 投影（现状机制）。

### 9.6 注册兼容（launch_film 的最小兼容方案——不默认链定义能直接替代注册节点）

- `launch_film` **保持注册节点 kind 不动**：NODE_KINDS 自举、工具注册表条目（提案/能力菜单/意图目录三面投影）、报价 fold、出生地 `requires=(WEB_PAGE,)` 门、画布归属全部沿用现状座位。
- 拆分走**编译期展开**：compile 把 launch_film 一步展开为三个 internal 步骤（`film_prepare`/`film_narrate`/`film_assemble`）+ 既有 render mirror——先例 = `materialize_source` 的编译期注入（`orchestrator.py:627-631`、`graph_fill.py:1173`）；internal kinds 声明 `internal=True`（自举豁免先例 `graph.py:239-242`），永不入 LLM 工具目录。
- 报价等价：链 estimate = 三阶段 estimate 之和 ≡ 旧单体公式（编辑/变体 run 的分叉报价同法折算）——等价性入验收断言。
- output_type 归属：Output 出生座 = film_assemble（`type="film"`/`_RENDER_CONTRACTED` 判定/run_review 映射扩展读链，现状 `run_review.py:45` 单点映射改读链尾）。
- **重启时早期验证项（有阻塞证据再报告）**：编译展开对既有图形状/birthplace ∀-门/画布投影/`pend_outputs_for_render` 认领链的兼容——未定稿前不把「链定义可替代注册节点」当已验证。

## 10. 复用、计费与迁移

### 10.1 旁白复用存储（最小实现）

新表 `film_narrations`（MODULE_ARCH §4 登记 + alembic 迁移）：`(project_id, content_hash, storage_key, duration_s, voice_id, language, config_hash, status, owner_token, lease_expires_at, created_at, updated_at)`，unique `(project_id, content_hash)`。**项目级作用域**（已定）。

- **content_hash** = sha256（归一化文本 | voice_id | language | 合成配置）——复用依据覆盖文本/声音/语言/配置；**窗口适配是时间条件**（音频真实时长 ≤ 新窗口，超出走弹性阶梯）——hash 命中 ≠ 可用，适配检查是第二道。
- **当前音频适配口径**：命中且适配直接复用、零 TTS；不适配沿用有界重新 TTS，须按实际调用计量并在报价/复用说明中区分。不得称其为从原音频确定性恢复或承诺零费用。本地速度派生及其 staging 恢复验收是 PLANNED 增强，不阻塞当前闭环；无论采用何种路径，冻结时间轴和适配上限仍须遵守。
- **原始音频与速度适配结果分开**：store 只存原始合成音频与真实时长。速度适配 = 执行期**重新合成**（命中不适配时按已知 1.0 时长续爬梯，真实供应商调用、按字符计量——不是本地变速，不是从原音频字节确定性恢复）：**适配产物 = run 级 staging 文件**（spec 引用的逐场 audio URL 指向它），**不入 store、不进 hash**；恢复语义 = run 重试/恢复不依赖上轮 staging 存活——store 原件的已知时长 + 目标窗口决定重新合成的请求（再计量）；staging 文件随 Output 生命周期（现状输出文件同律）。
- **并发（唯一索引不防重复调 TTS，写路径全部带所有权条件，禁止无条件后到覆盖）**：
  1. **原子占位**：`INSERT … ON CONFLICT (project_id, content_hash) DO NOTHING RETURNING`——拿到行 = 成为 owner（owner_token = 本 run 随机 token + lease 过期时刻）；没拿到 = 读已提交行，done 则直接用。
  2. **有界等待**：占位行 synthesizing → 有界轮询（独立短事务读）；lease 过期未落定 → **有界接管**：`UPDATE … SET owner_token=我, lease=新, status='synthesizing' WHERE … AND status='synthesizing' AND lease_expires_at < now`——影响 1 行才接管成功，0 行 = 他人已接管/已完成，回去重读。
  3. **完成（拥有者校验）**：音频先传 **staging key**（带 owner token 后缀的临时对象）→ `UPDATE … SET status='done', storage_key=<staging>, duration_s WHERE … AND owner_token=我 AND status='synthesizing'`——影响 0 行 = 我已失去所有权（被接管/已 done）→ **删除我自己的 staging 对象**，重读行取他人结果；任何写都不覆盖非我所有的行或文件。
  4. **过期任务不得覆盖/删除新结果**：所有 UPDATE/DELETE 带 `owner_token=我 AND status='synthesizing'` 双条件；staging 对象按 token 后缀隔离，清理只碰自己的。
  5. 合成失败的占位行由 owner 条件删除（不留毒）；run 失败时已 done 的行保留（资源合法，后续 run 可复用）。
- **文件丢失**：读时 storage 对象不存在 = 删行当 miss 重合成（自愈，如实记日志）。
- **清理**：随项目级联删除（同 assets 律）。
- **估算**：估价 tts_chars 行 = 设计拍 change_set 已知的失效场字数（edit/variant）或全量（新建）。

### 10.2 旧作品兼容

旧 Output 自带 render_spec + run.context.prepared_storyboard（provenance）。**CURRENT**：可从 provenance 恢复编辑基准并重证 digest；场景无 id 时按位置派生一次性升级。**PLANNED 画幅变体**：在同一恢复基准上走正常变体链，验收必须包含可证明 provenance 的旧作品正腿，不得只验证新代码生成的作品（fixture 用同构手工板 + spec，不动原项目）。

旁白复用**按需收割**：旧 spec 的逐场 audio URL + 同文本 captions 可重建 hash 输入（文本来自 spec captions，voice/language/config 来自 run context）→ 文件存在性核验通过才入 store；**无法证明复用条件（文件丢失/字段缺失）= 如实按 miss 重合成并在 change_set 说明**。不全库迁移。

### 10.3 计费语义（CURRENT 单体 / PLANNED 宏链）

- **报价**：CURRENT = compile 期 estimate fold；新建 = 导演 token 最坏界 + film_seconds 锚 + tts_chars 全量；编辑按设计拍已算失效范围报价（零导演 token 行、tts_chars 只算失效场、film_seconds 按实际板秒数）。PLANNED 变体沿用同一实际范围原则；PLANNED 宏链报价 = 各阶段 estimate 之和，必须与单体公式等价。
- **实际成本记录**：CURRENT = 单体 LaunchFilm 步骤记录实际成本；「零导演调用」≠ 零 token——edit 的 chat 回合 token 现行不计入生产计量，TTS/渲染如实计量。PLANNED 宏链才把 meter 拆到各阶段行。
- **结算边界**：CURRENT = 单体 LaunchFilm 成功点 capture，失败按现有 hold/release 与幂等规则处理；render mirror 语义不变。PLANNED 宏链的钱包 capture 唯一座 = film_assemble 成功，金额 = 链累计 metered；prepare/narrate/assemble 失败均为零 capture。拆分前后必须显式核对净扣费、hold 释放/退款相等且无重复收费，不能用“政策不变”替代等价性验收。
- **失败与重试**：幂等键现状（run/step/attempt 三级）；capture_step 的 prior 减法现状。PLANNED 阶段重试不得重复 capture。

### 10.4 迁移与回退（CURRENT / PLANNED 分列）

- **CURRENT**：新增 schema 字段全部读容忍（scene_id/change_set/constraints_choice 缺省读旧形），增量兼容；film_narrations 为增量表。资源记录回退 = 停读停写并回落既有 per-output 存储路径；表可留空不拆。具体 alembic、env/flag、字体/音乐资源与回退验收归 execution §1.2。
- **PLANNED 画幅指纹迁移**：aspect 移出 canonical 集后，旧存储指纹不会匹配新算法；参数 delta 分类器对 aspect-only delta 判变体，其余判诚实的重呈现一次（不触发导演）。回退 = 恢复 aspect 入集，双向存储行不受影响。
- 每批回退按该批 feature flag 或 revert 设计；renderer/spec 是否变化必须按实际改动核对，不作“一律零改动”的预设。

## 11. 授权法则应用（ADR-139 / ADR-144 现行法）

**现行法：auto 只免批准、不创造制作意图。** 正确次序（用户拍板）：

1. **当前对话**决定用户想做什么、方案是否确定、是否现在制作——讨论（「为什么这样安排？」）只解释不修改不制作；歧义修改（「换个样式可以吗？」）必要时澄清、不擅自选择；纯修改（「第四幕文案改成……」）授权修改草稿，**不等于立即渲染**；「先给我看方案」= 保持审阅不启动；「按这版制作」= 制作意图在场；「直接做，细节你决定」= 委托范围内决定并执行。
2. 已有明确执行意图后，**execution 设置**决定是否还要额外执行批准拍。
3. **credits 设置与守卫线**（`billing.always_confirm_above` / 不可报价族）决定费用确认——任何档恒问不变。
4. **auto 只能免去对应批准步骤**，不能创造用户没有表达的制作意图；ask 档不得替代创作需求澄清。
5. 既有额度保护、材料就绪、版本匹配、计费与幂等规则继续有效。

**落地写法**：

- **生产意图 = dock 出生事实**：六个 dock 工具参数族（present_plan / propose_tasks / edit_graph / propose_plans / revise_plan / revise_selects）携带 `production_intent`（模型按法判断，禁关键词启发式）；auto 开工道放行 = dock 无确认债 **∧** 出生回合有制作意图；缺意图 stamped `awaiting_production`（复用确认 dock 形态，bare Start pill 常驻邀请，零新 chrome）；None 读安全侧 = 无意图。
- **Film 分镜阶段门**：本回合 `design_storyboard` 已落新版本，而 `present_plan` / `propose_tasks` 的 `production_intent` 非 `true` 时，结构性拒绝其中的 `launch_film` 提案；完整呈现当前保存版本后走 `answer`，不建制作 dock。阶段门必须先于**所有提案副作用**，包括 URL capture、caption 与 dock 准备，不只是 run 创建。普通修改询问「要按这版重新制作吗？」；review-only 展示后停止、不问开工。当前消息明确「改完直接做」才以 `production_intent=true` 进入既有提案、报价与执行道；旧 run 完成或旧版批准不授权后续新版本。
- **确认前呈现 = 累计方案复述**：制作确认拍在问句之前（同一消息，不新增拍）基于当前真实草稿复述累计状态（素材与文案 / 画幅 / 总时长 / 幕数 / 配音音乐 / 累计修改 / 保持不变的范围）；简洁摘要 + 当前分镜表即可，不机械四分类；用户未选的选项与未澄清事项永不复述为已确认；用户边等边改 = 更新草稿再呈现；版本/token 绑定（`start.stale_storyboard` 409）保证旧确认不授权新版本。
- **作品首稿强制审阅（ADR-144）**：`film_storyboard_version == 1` 且 `film_presented_message_id` 尚未持久化时，任何 Start（含同回合 auto 与过早显式 Start）都由 `422 start.review_hold` 失败闭。auto 无其他确认债时不显示首稿 approval dock，用户看过后的制作话走普通 sendChat；ask 可显示首稿 dock，Start 钮同样只发送用户消息，不直接创建 run。呈现行落库后，下一轮 LLM 才通过 `start_run` 放行；后续版本不继承这个首稿专用确认拍，仍走当前制作意图、auto/ask、review hold、费用与版本守卫。
- **ADR-134 收窄不动**：fresh 稿 review_hold 默认 ON（①作品首稿；②compose 开放重编排）；edit/variant 不新增 hold——但其授权语义收窄为「授权这个版本的修改」，开工仍走出生事实。
- 用户明示 review-only（「先让我看看」）仍挂 hold（`review_hold=true` 参数保留为唯一逃生门）；Start 门 `422 start.review_hold` 兜底不动。
- ADR-129（批准 = 消费呈现版）不变。
- 能力诚实：交付承接建议与能力菜单只承诺已支持的 ops 集合。

## 12. 当前旅程与执行示例

### 12.1 网页源

贴链接 → 读取/讨论方向 → `design_storyboard` compose → 呈现完整当前保存版（首稿 review hold 默认 ON）→ **作品首稿一律等待用户看过后的制作话，开场“直接做”与 auto 也不同回合创建 run；auto 无其他确认债时不显示首稿 dock，ask 的 Start 同样只发送制作用户消息** → 下一轮 LLM `start_run` → **单体 `launch_film`** → render/probe → 交付。交付后可以 run provenance 恢复基准并继续 patch；pending 清空不等于失去作品。

画幅修改当前诚实拒绝：没有 `set_aspect`，不得把“再来个 1:1”静默转成导演重设计。画幅变体的未来旅程与验收归 execution §2。

### 12.2 文字源与组合幕

用户提供原文或创作需求 → 确定逐字/改编与创作方向 → 素材发现（有媒体时）→ compose words/composite → 完整呈现 → 按授权制作。修改时先读当前版本，再用一次原子 edits 批次修改所有声明范围；工具返回系统变化摘要与完整当前保存版事实。

- 普通修改：完整新版呈现后 `answer` 询问是否重制，不先建制作 dock。
- 只看方案：完整呈现后停止，不问开工。
- 当前消息明确“改完直接做”：进入既有提案、报价与执行道；shortfall、drift、review hold、费用与 Start 版本绑定继续生效。
- 交付后修改产生新 Output，原 Output 保留；修改本身不授权渲染。

### 12.3 局部编辑与音乐

- 局部内容：`update_scene` / `update_element` 只动声明字段；未触碰场景和元素由系统保持，change_set 与完整新版同时呈现。旁白只按真实文本变化与窗口适配结果复用或重合成。
- 重排：`reorder_scenes` 保持场级 digest、改变整板 digest；逐场重查音频窗口，divider 序号与时序确定性重算。
- 音乐：`set_music(retime=keep_cut)` 保帧；`retime=recut` 重 snap、重算 reveal onset 并复查音频窗口。模型按用户原话选择，不能因出现 set_music 就丢失本应继承的冻结切点。

### 12.4 录屏与长片边界

录屏是普通视频素材；文字、源区间、输出窗、位置、原声与动画都走 §7.7～§7.8 的同一组合契约。静态截图推拉不得冒充动态录屏，带烧录字的参考成片不得冒充干净底片。

约 139s 案例超过当前 120s 帧帽。调整上限必须同步后端、render、超时、费用与全长验收；在形成结论前不得静默截断或宣称支持。当前处置与验收归 execution §1。

## 13. 执行与剩余工作

当前优先、剩余批次、依赖、授权边界和上线条件不在本文重复：全局排期读 [PROGRESS §0](../PROGRESS.md)，Film 当前执行读 [execution §0～§1](film-storyboard-orchestration-execution.md)，延期能力读 execution §2～§4，实际完成与未验证状态读 [progress](film-storyboard-orchestration-progress.md)。

## 14. 验收归属与证据边界

- 当前验收针对真实 Chat 旅程、原子编辑、版本与授权、单体执行、费用、渲染和浏览器表现；分组与发布条件归 execution §1，延期项验收归 execution §4。
- 验收状态只读 progress。纯函数、schema round-trip、stub 导演、隔离渲染、真实 LLM、真实存储/渲染服务与人工视听是不同证据层级，不得互相冒充。
- 视觉验收仍包括必要的帧检查与**全片动态看片**；音频配置在场不等于听过成片。当前没有运行时自动视觉闭环。
- MiniMax tool-role 图片支持已有真实 POSITIVE 证据，当前验证范围见 progress；不再需要把 synthetic user 兜底当作默认路径。
- 验收只保留当前可执行条目与最新结论；旧闸表、逐轮数字和事故证据不作为本契约的隐藏附录。

## 15. 不做清单

第三方 skill 执行平台 / 自由渲染代码 / 行业专用流水线 / 新场景型与转场大扩展 / 可视化编辑器（含自由画布）/ 任意 CSS / 通用关键帧系统 / 多轨编辑器 / 模板市场 / 版本浏览产品（版本表随之延后）/ 通用依赖框架 / 自动视觉验收系统 / `insert_scene` 快捷 op（compose 可增删场景）/ 导演工具 loop / **AI 生图（文字视频背景不虚构画面）** / **完整知识视频专项建设（资料检索/事实核查/复杂知识图解/专业图表/自动教学结构）** / **通用工作流平台或第二套文字视频系统** / 餐馆素材接入（另立批）/ 全库迁移 / 修改用户计费政策。

## 16. skill 库方向

skill 指导 agent **组合**现有能力（ops/场景型/约束分层），不是给固定生成器喂文案。只改 skill 的适用范围 = 弧配方、节奏、选图与取景工艺、旁白声音与呈现口吻；新 op/约束 override/材料源适配才扩工具或 schema；新场景型/转场/字幕样式/自由布局才扩渲染底座。不得把每个创作方法都做成新的后端生产工具。

- **三层职责**：engine = 可复用执行基座；skill = 族内变体（词汇表、spec 预设、prompt 与 validator）；recipe = 入口实例（brief 模板、输入要求与 demo）。三者是 1:N 关系，不以卡名复制引擎。
- **新 skill 分诊**：先拆词汇表 / spec 契约 / 编排 prompt / 执行器四件，再回答四问——引擎族是否已存在？差异在 prompt 还是引擎？词汇重合度多少？输入、失败恢复与交付生命周期能否复用？同族不代表这些生命周期自动相同。
- **横切核对**：每个新 skill 必须分别审查输入与来源契约、验证与失败契约、交付与生命周期契约；registry→prompt 保持单源投影，grounding 由确定性 validator 把守，降级必须诚实。
- **用户自建 skill（PLANNED）**：若运营端开放，只允许参数与模板，不允许用户提交可执行渲染代码；渲染组件始终由人工维护。触发与排期归 PROGRESS 需求池。
