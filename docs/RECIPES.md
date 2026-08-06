# RECIPES — 配方架构（Home 能力卡 + 兑现管线）

> Status: 📐 设计定稿（2026-07-30；**2026-08-01 交互形态修订**：Remix = composer mention chip，裁决⑤，简报 `docs/tasks/recipe-mention.md`；R1–R4 分期见 §8）
> 上游定位：`STRATEGY.md` §5（配方库 = 品味的陈列窗，不做内容流）；排期唯一事实源 `PROGRESS.md`（第 1–3 周）
> 本文档角色：**配方线的母文档**——卡片层 + 能力层的架构与分期；每期施工拆成 `docs/tasks/` 独立简报，引用本文档章节号。新开会话创建 tasks 前必读 §9。
> 用户裁决记录（2026-07-30，四轮设计评审沉淀）：
> ① **配方 = 能力承诺**——上了的卡必须能用用户自己的素材跑出同款，不能写死、不能仅 demo（STRATEGY"配方卡不做营销剧场"的产品化口径）；
> ② 首页形态 = composer 下方**能力演示视频卡**（4 张：风格 / 多语言 dub / 分镜剪辑 / 图片视频），源素材用云端 demo talk；
> ③ 声音的家 = **Speaker 块扩展**（声纹 = Speaker 画像属性，stock voices 作系统内置 Speaker 进 SpeakerPickerModal），composer 不加 Audio 块；
> ④ v1 图片视频 = **有声版 + stock 兜底**（无声纹不阻塞，dock/审阅面板可换声）；**（2026-08-05 修订：R2 先交付无声版——照片轮播+字幕+音乐，不需要真人说话；声音路径整体后置第 5 周声纹线，§4.2）**
> ⑤ **Remix 形态 = composer mention chip**（2026-08-01，对照 ElevenLabs 全屏模态框 / Agent Opus composer mention 后裁决）：点卡 = 往 composer 插入 recipe 提及 chip，走唯一入口正常流；**否全屏模态框**（第二条派发面，与"composer = chat 第一条消息"冲突；承诺呈现归既有审阅面板）。mention 系统做成**双端注册表架构**，recipe 第一成员，后续 @ 类型只填注册项；配方结构数据升服务端注册表 + 公开只读端点，任务书钉死唯一发生地 = 服务端解析（简报 `docs/tasks/recipe-mention.md`）。DAG 永不外显，"编辑流程"等价物 = chat（plan 级 ops + 子图词汇，第 7 周线）。
> ⑥ **功能扩展的唯一门 = SKILL_REGISTRY 注册项**（2026-08-05）：重试/输入校验/拓扑约束/进度文案/计量提示随登记免费获得；禁为单节点开平行映射表或特判分支（CHAT_ARCH §4 扩展门纪律）。

## 0. 已核实的现状事实（读码确认，2026-07-30）

- **dub 全链路已在跑**：`tools/dubbing.py`（翻译字幕轨 → 声纹合成 → 替换原音轨）+ `ClipDub` 进 clip-spec + `Clip.tsx` dub 音轨渲染 + `run_dub_clip` 节点 + `dub_clip` skill 已登记可派发。多语言 = 同族节点按语言扇出，**零新代码**。
- **stills audiogram 全链路已在跑**：`ClipSource.kind="stills"`（图片轮播 + 可选语音轨 + 字幕映射不变 + 音乐循环）；slides→images（`asset_processing.py`）、audio→stills（`node_runners.py:1069`）均在跑；loudnorm 已处理静音渲染。
- **字幕现状**：`caption_style_preset` 枚举 5 值（`clean-bottom`/`karaoke-highlight`/`fade-in`/`pop-in`/`slide-up`），`Clip.tsx` 只渲染当前 active 行——**堆叠字幕（前行驻留、向下累积）不在枚举内**。
- **crop 是 clip 级静态值** `ClipCrop{x,y,scale}`，无时序；ASR = faster-whisper（词级时间戳，**无 diarization**）。
- **`packages/clip` 是 editor preview 与 render service 的同源组件**——渲染分支加一处，preview=render 双端自动生效。
- **任务书 slot 化已落地**：`IntentSlot{type,count,focus,language,tone_override,explicit}`；chat plan path 接受 `prior_intent` 且三方合并保 explicit 槽（`merge_prior_slots`，chat 修订永远赢）；`pending_intent` + `?overlay=chat` 恢复管道在。
- **composer = prompt-only**（instruction + speaker_id + brand_template_id），意图识别全在管线。
- **文字稿+照片场景已有 Ready 简报**：`docs/tasks/synthetic-talk-video.md`（`voice_gen`/`synth_visual` 节点设计，声纹 TTS 回配 ASR 时间戳，下游零感知）。
- **demo talk 素材**：reset_db 不删对象存储，retired `demo/` 树应在桶中可恢复（需人工核实）。

## 1. 原则

1. **配方 = 待填素材的任务书模板**（Phase 1 形态）。配方与素材的关系只有两层：展示素材（卡片预览，不进管线）+ 类型化输入槽位（"需要一段演讲视频"的约束）。素材是配方留给用户的唯一空格。升级为"待填素材的施工图模板"是 Phase 2（STRATEGY §5，依赖公开性字段 + ADR，不在本文档范围）。
2. **点亮纪律（2026-07-31 修订）**：四张卡**全部渲染**（presence over gating——画廊存在感优先）；纪律的保留线是**承诺不可点**——能力未兑现的卡（reserved）hover 只给 Soon 标记，不出 Remix 按钮。点亮 = `status` 翻 `live` + Remix 解锁，不要求四张齐发。
3. **DAG 编排全复用**：每个新动词（节点/契约扩展）落地即免费获得编排、逐节点计量、SSE 打勾流、失败重试、子图重跑。零新表——一切住 JSON 载荷层（clip-spec / node.spec / run.context）。
4. **可扩展词汇一律注册表化**：字幕样式、skill、节点 kind 同纪律（`SKILL_REGISTRY` / `NODE_RUNNERS` 先例）——加成员是填注册项，不是加分支。
5. **内容定位**：卡片围绕 LinkedIn / 多语言 / 专家需求（欧洲 ICP），不做 TikTok 风（CLAUDE.md 产品定位）。
6. **配方 = 数据包**（2026-08-06）：base + flow + prompt + example_assets + example_outputs（+ 服务端 outputs 预设），schema 见 §7.1。扩展配方 = authoring 数据条目，不是写代码——除非该卡演示的能力本身是新的。卡面立项门槛 = 一道具体的菜（§4.4）。

## 2. 三层正交架构

配方的全部变化分解为三个独立演化的层，层间自由组合——"很多种效果"的支持 = 组合免费，不是专用代码路径：

```
视觉底（source.kind）     ⊥  字幕效果（caption catalog）  ⊥  声音/时间源
──────────────────        ─────────────────────────       ─────────────────────────
video（实拍）               clean-bottom                    原声音轨 + ASR 词级时间戳
stills（照片轮播）          karaoke-highlight               TTS 声纹 + ASR 回配时间戳
slides（PPT 转图）          fade-in / pop-in / slide-up     无声：阅读节奏估算（✅ align_stills 落地，2026-08-05）
                            stacking（新增，§3.2）          + music 槽（独立开关，已有）
```

"图片轮播 + 堆叠字幕 + 音乐 + 声纹配音" = 三层各取一项的组合。新增字幕效果只动 catalog；新增视觉底只扩 `source.kind`；新增声音形态只加时间源。

## 3. Caption preset catalog（统一字幕架构）

### 3.1 原语分解

任何字幕样式 = 三个正交原语的组合（`Clip.tsx` 现有代码已隐含此结构，本设计将其正式收编）：

| 原语 | 现有取值 | 说明 |
|---|---|---|
| `layout` | `single`（单行替换）| **新增 `stack`**：已揭示行驻留、新行向下累积（配 `maxLines` 参数） |
| `entrance` | `none` / `fade-in` / `pop-in` / `slide-up` | 新行进场动画（`captionEntrance()` 已隔离此原语） |
| `word-highlight` | `off` / `karaoke` | 词级高亮开关 |

### 3.2 catalog 形态

- **单点定义住 `packages/clip`**（preview 与 render service 同源消费）：`CAPTION_PRESETS: { id → { layout, entrance, wordHighlight, params? } }`。
- **clip-spec 契约不变**：spec 仍只带 preset id 字符串（渲染器无关纪律）；Python schema 只校验枚举成员（镜像 id 列表，行为不下沉 Python）。
- **新样式 = 一行注册**；新**原语值**（如 `layout: stack`）才写代码（少数情况，`Clip.tsx` 一个分支，双端自动生效）。
- **libass 退路**：每个原语值须可映射 `\fad` / `\t(\fscx,\fscy)` / `\move` / 多 event 驻留（VIDEO_EDITOR 的 CSS∩libass 纪律），新原语值入库前过此检查。
- **前端选择器同源**：editor 字幕样式下拉从同一 catalog 列选项（label 走 i18n 键）；`set_caption_style` edit op 枚举随 catalog 扩展，chat 自动获得新样式（"把字幕换成堆叠式"）。
- **stacking 为 catalog 收编后的第一个新成员**：`{ layout: "stack", entrance: "fade-in", maxLines: 5 }`。

## 4. 四张配方卡

> 每张卡：承诺 / 能力现状 / 兑现缺口 / DAG 拓扑 / 素材账单。点击行为统一见 §5。

### 4.1 多语言 dub 卡（R1 兑现）

- **承诺**：一段演讲 → 你的声音说德语/法语/西语（参照 Agent Opus"视频配音"获客形态）。
- **能力现状**：✅ 零缺口（§0）。dub 零件、节点、skill、渲染全在跑。
- **兑现工作 = 纯接线**：单 run 拓扑 `clips_gen → dub×N`（registry `after` 约束已有，配乐/配音修饰节点殿后）；语言集默认建议 **DE + FR + ES**（欧洲 ICP，卡片可配置）；任务书槽表达 = clips 槽 + dub 语言清单进 `spec.target_language` 扇出。
- **合并代数三规则**（2026-08-02，agent-loop-upgrade W1；recipe-mention §2.3 同文；**2026-08-05 修订：配方从钉降为预设**）：① **承诺播种**——`outputs` 只做存在性填充：推断没产出的槽位类型才补，已产出的一律不动；无 explicit——下一轮起每个字段（含槽位存亡）都可经 chat 修订，**chat 修订永远赢**（面板手改经 `merge_prior_slots` 三方合并存活）；② **参数默认**——`dub_languages` 是 DEFAULT 不是承诺：用户在（可编辑的）模板文案里点名的语言赢，没点名才用配方默认（"remix 改成中文"生效）；③ **额外放行**——同句其他意图加性存活（"@配音卡 顺便写篇文章"的 article 槽位并进同一张任务书）。`RecipeEntry` 字段级策略注释即此三规则的代码座位；chat 路径的 fork/morph 选择经 `DubClipParams.fork`（"再来一版" → fork 派生新行，原版保留）。
- **素材账单**：demo talk（恢复桶中 `demo/` 树）；预览 = 原片片段 + 各语言 dub 片段（跑真管线收获后烘成静态公开资源）。

### 4.2 图片视频卡（R2 兑现）

> **2026-08-05 口径修订**：R2 交付**无声版**——照片轮播 + 字幕（catalog 多效果）+ 音乐，不需要真人说话。声音路径（voice_gen / TTS / stock 兜底 / 声样入口）整体让给第 5 周声纹线；原"有声版 + stock 兜底"裁决④同步失效，届时按 §5 重启。

- **承诺**：只有文字稿 + 现场照片 → 照片轮播 + 字幕 + 音乐的短片（字幕效果可在 editor/chat 换：堆叠淡入 / 词高亮等 catalog 成员）。
- **能力现状**：✅ stills 链在跑 + `stacking` preset 已在 catalog；缺口 = 无录音时的字幕时间轴（原痛点：transcript+照片走 stills 分支但无 words，选段时间轴靠编造、无逐词字幕）。
- **兑现工作（2026-08-05 落地）**：
  1. `align_stills` 注册项（tool，确定性）：文字稿 → 阅读节奏估算**词级时间轴**（zh 按字 / 拉丁按词 + 句间停顿常数），写回 transcript asset 的 `meta.words`——与 ASR words 同构，下游零感知；文本哈希幂等复用。
  2. **DAG 注入**：`create_run` 计算输入画像（无 video/audio + 有文字稿 + 有照片）→ `compile_graph` 在 director_plan 与 clips 之间插入 `align_stills`，clips 挂边 `[plan, align]`（mode①/② 共用）；clips 渲染源从 DAG 父节点读（`spec.aligned_asset_id`），不扫全项目。
  3. `build_clip_spec` stills 分支放宽：words 在、无音频 → 字幕轮播（`url=""`）；音频轨只认 AUDIO 源（transcript 的文本文件永不进音轨）。
  4. 简报的 `voice_gen`/`synth_visual`（TTS + Ken Burns 合成主片）**后置第 5 周**；本卡不依赖声纹。
- **DAG 拓扑**：`preprocess → director_understand → director_plan → align_stills → clips(stills) → render`（导演先行，全流程一条 pipeline）。
- **素材账单**：demo talk 文字稿 + 现场照片若干；预览 = stills + stacking + 音乐成片（demo 烘焙用 stacking 配置的品牌模板）。

### 4.3 分镜剪辑卡（R3 兑现，独立简报 B）

- **承诺**：横屏双人访谈 → 竖屏分镜（谁在说话镜头给谁）。
- **能力现状**：❌ 能力不在——crop 静态、无 diarization、VIDEO_EDITOR 封存了 "auto face reframe = L3"。
- **兑现工作**：见 §6（ADR 翻案 + M3 filmstrip 检测 + crop 时序化 + `reframe_clip` skill 评审）。
- **素材账单**：~~demo talk 是单人演讲，喂不了此卡~~ → 已策展 `demo/uploads/xy_1.mp4`（左右对坐访谈，2026-07-30 入库）。

### 4.4 风格卡（座位撤除，2026-08-06）

**风格不作为配方卡存在**（2026-08-06 拍板）：风格是产物的修饰，不是产物——"没有人想得到一个风格"。沉为 **look 层**：caption catalog 成员 × title/intro 结构 × brand 参数的组合，三个家——配方 overlay 预览（每道菜的观感即其 look）、检视器参数直操（字幕样式等控件，简报 `tasks/results-workspace.md` D8）、chat 修订（"换成杂志风"）。

**卡面立项门槛**（同日拍板）：配方必须是**一道具体的菜**——有名字、有画面感、一眼想要的成片（dub 卡"你的声音说德语"为模板）；品类形态（"带字幕的竖屏短片"这类货架标签）不配占位。第四张卡座位在闭环链（PROGRESS 第 2–5 周）完成后按此门槛立项；候选方向存档：杂志访谈风 keynote 短片（stacking + 顶部 title + intro 标题页，素材 `xy_2.mp4` 已策展）。

## 5. 声音层（裁决③④落档）

- **家 = Speaker 块扩展**：声纹 = Speaker 画像属性（已决架构不变）；`SpeakerPickerModal` 加"系统音色"区——stock voices 以系统内置 Speaker 形态出现（如 Rachel · Confident，带试听），与"👤 Anna（cloned ✓）"同列表分区。composer 维持两块不加 Audio 块（避免与 Speaker 职责重叠；Opus 的 Style/Assets/Audio 三块形态已评审未采纳）。
- **voice_gen 阻塞语义**：无声纹 → stock 默认声直接出片，**不阻塞**；QuestionDock / 审阅面板可换声（复用 ask 原语 choice 形态，`tasks/done/intent-ask-primitive.md` 期 3 机制零改动）；引导克隆是轻提示不是拦截（录 10s 样本路径已有 `tools/voice.py:clone_voice`）。
- **stock 声来源**：MiniMax 系统音色（零克隆成本）。**待核实**：系统音色清单与多语言覆盖（EN/DE/FR/ES/IT/ZH 必须齐），核实结果回填本节与 R2 简报。
- **后置**：语速调节、Pronunciation 纠正（归术语表线（PROGRESS 可选需求））。~~无声版（阅读节奏估算）~~ — 已提前落地为 R2 交付本体（`align_stills`，2026-08-05，§4.2）。

## 6. 分镜能力指引（简报 B 种子）

> 简报 B 立项时本节内容平移为简报正文；此处锁定方案与决策负担。

- **决策负担**：VIDEO_EDITOR "automatic face reframe = L3（交 CapCut/Premiere）"是封存决策——按 DECISIONS 纪律**写新 ADR 翻案**（supersedes 标注），理由：从"自动人脸跟踪"收窄为"**静态双人分镜**"（固定机位、左右分坐——欧洲会议对谈/播客主流形态），工程深度不同；STRATEGY 本将"运镜枚举"列为 L2 缺口，翻案有据。
- **检测方案（零新模型依赖）**：whisper 词级时间戳切语音段（已有）→ **M3 视觉 filmstrip**：段内 4–6 帧拼网格，一次调用判"哪侧人物嘴在动" → 说话人时间轴 `speaker_map`。**只分析选中 clip 窗口**（选段后执行，5 clips × 十余段 ≈ 几十次视觉调用，逐节点计量）；双人访谈语音极少重叠，准确率有保障。
- **架构落位**：`speaker_map` = 素材级内部分析产物（`material_understanding` 同款，asset-hash 复用）；clips_pipeline 选段后、渲染前加分析节点（会思考的班底，可寻址可重跑）。
- **契约扩展**：`crop` 静态值 → 增 `crop_track` 关键帧轨（向后兼容，静态值作缺省）；`Clip.tsx` 按 sourceTime 采样当前 crop（preview=render 同源）；滞后/平滑规则（最短驻留 + 缓动，防跳切眩晕）。
- **skill 准入**：`reframe_clip` 过 NAMING §7 评审后登记（CHAT_ARCH §4 纪律）。
- **v1 范围**：静态双人 only；多人/移动机位/侧脸归后续。

## 7. 卡片层（数据 + 交互 + 布局）

### 7.1 卡片数据：Recipe 数据 schema（2026-08-06 修订：配方 = 数据，取代"双端注册表 + 三件配置"的分散形态）

**配方 = 一个数据包**（2026-08-06 拍板）。一张配方卡 = 五个字段，所有消费方（卡面 / 检视 overlay / composer 回填 / plan path 播种 / 未来真实 Gallery）读同一个包：

```
Recipe = {
  base:            名称 / 承诺 / 标签 / 画幅 / status        → 卡面 + overlay 固定信息卡
  flow:            作者策展的只读静态流程图（友好步骤名、无模型名） → overlay"它是怎么做的"堆叠项（ADR-035）
  prompt:          示例 prompt                                → overlay"User prompt"堆叠项 + Remix 回填 composer 的文本
  example_assets:  示例原素材（demo/ 桶引用）+ input_slots     → overlay"原素材"堆叠项 + Assets 块必填提示
  example_outputs: 烘焙成片（内容寻址引用）                    → overlay 大预览 + 卡面自动播放视频
  outputs:         预设任务槽（存在性填充：只补推断没有的槽位类型，无 explicit）→ plan path 预设播种（服务端实质）
}
```

- **可见性分层 = schema 的字段级属性**：公开投影（base / flow / prompt / example_assets / example_outputs——落地页匿名受众可读）经 `GET /api/v1/recipes` 下发；**预设实质（outputs / dub_languages）永不出服务端**。原"双端分半"纪律收编为字段可见性，不再是两套机制。
- **存储纪律**：结构数据与资产引用直接持有于服务端 `app/pipeline/recipes.py` 静态注册表（SKILL_REGISTRY 同款，随代码部署）；**可翻译文本**（title / promise / prompt）以 i18n 键引用（en 为源语言，现状纪律不变）；烘焙资产以内容寻址 URL 引用（`recipes.assets.ts` 由上传脚本生成，现状不变）。
- **flow ↔ outputs 同文件登记**：flow 是策展的展示数据，但必须如实对应 outputs 预设实际编译出的图——同处登记、评审一并过，防漂移。
- **新增配方 = 写一条数据条目**（注册项 + i18n 键 + 烘焙资产），零代码路径——除非该卡演示的能力本身是新的（如分镜的 crop_track）。"扩展配方卡"的全部工作自此统一为 authoring 数据。
- `inputSlots` 消费者：chip/picker 提示 + Assets 块必填提示（前端展示）与 clips-media 门拒收信息（服务端兜底）。

### 7.2 点击链路：mention chip 形态（2026-08-01 修订，取代预填+prior 形态）

```
点卡 Remix → 往 composer 插入 recipe 提及 chip（{type:"recipe", id, label}）
           + promptTemplate 文本预填（可见可改，纯文本不是状态）
           → 用户上传自己的素材（Assets 块，必选动作；chip 旁提示所需槽位）
           → 发送：建项目 → 上传 → 跳转 overlay chat → 首条 POST /chat { message, brand_template_id, mentions }
           → 服务端 plan path resolve_recipe_mentions() 预设播种（播种唯一发生地；composer 永不构建 prior）
           → 三方合并（merge_prior_slots）→ pending_intent → overlay 审阅面板逐槽行呈现承诺 → Start
```

**chip 三律**（2026-07-31 旧事故的结构性消除——事故根因是配方状态不可见且跨发送残留）：
① **可见**——chip 内联 textarea（图标 + label + ×）；② **发送即消费**——随 prompt 清空，payload 只附着当次；③ **× 即纯化**——删 chip 后本次发送不带任何配方效果。

@ 手选与点卡同终点（同一 mention）；chat 输入同组件，派发走既有 task_book dock 确认面。承诺的确定性靠**服务端注册表预设播种 + 三方合并**（代码保证），不靠 LLM 从 prompt 重新推断，也不靠 LLM 解释 recipe 提及。匿名访客点卡 → 同一套组件预填，发送时走既有 requireAuth 闸（双受众复用，STRATEGY §5）。

### 7.3 布局与素材

- home：composer 区下方卡片画廊（Opus 式 2026-07-31 改版）：**9:16 竖屏卡一排四张**（`grid-cols-2 sm:grid-cols-4`，容器 max-w-5xl），视频**自动播放**（静音循环）；**左上**配方类型名，**右上**反色圆形声音开关（同时只响一张），**hover 底部浮出**承诺句 + Remix 按钮（reserved 卡 = Soon pill）。遵循 CLAUDE.md：rounded-lg、无 ring/border、shadow-lg、edge-glow。
- 预览资源必须**公开可读**（落地页匿名受众）：`apps/web/public/` 或对象存储公开前缀——现有 asset 端点全是登录态，不可用。
- 素材策展总账：① demo talk 恢复（桶 `demo/` 树，✅ 已核实：`demo/uploads/demo_talk.mp4` 11MB 单人 TED 风演讲）；② 双人访谈横屏视频（✅ 已策展：`demo/uploads/xy_1.mp4` 17MB 左右对坐访谈，R3 分镜卡源）；③ PPT 大型登台演讲（✅ 已策展：`demo/uploads/xy_2.mp4` 63MB，风格卡/图片视频卡源）；④ 各卡预览成片（能力兑现后跑真管线收获，烘成静态资源）。3–4 张卡复用 1–2 场源演讲。

## 8. 分期与验收

| 期 | 内容 | 上卡 | 验收（e2e 真实管线，无测试套件纪律） |
|---|---|---|---|
| **R1** | caption catalog 收编 + `stacking` preset + dub 配方接线（clips→dub×N 单 run）+ 卡片层（schema/布局/点击链路/i18n）（实施简报 `docs/tasks/done/recipe-cards-r1.md`；**交互形态 2026-08-01 修订为 mention chip**，简报 `docs/tasks/recipe-mention.md` 期 1 随本行复亮 Remix） | dub 卡 | 用户素材走 dub 卡 → 单 run 出 clips+多语言 dub 产物；stacking preset 在 editor preview 与导出 MP4 一致 |
| **R2** | `align_stills` 注册项（阅读节奏时间轴）+ DAG 输入画像注入 + stills 字幕轮播链（**2026-08-05 修订：无声版先行**，声音路径后置第 5 周，§4.2） | 图片视频卡 | 文字稿+照片 → 照片轮播+字幕（stacking 等 catalog 成员）+音乐成片；词级时间轴与 ASR words 同构，editor/chat 换字幕样式即生效 |
| **R3** | 简报 B：ADR 翻案 + filmstrip 检测 + `crop_track` + `reframe_clip` | 分镜卡 | 双人访谈 → 竖屏分镜 clips，说话人切换正确、无眩晕跳切 |
| **R4** | Recipe 数据 schema 定义（§7.1）+ dub 落成第一个完整数据实例（示例 prompt / 素材账单 / 静态流程图 / 预览烘焙）+ remix→chat 链路走查补缝（08-07 启动 ~ 08-11，PROGRESS 第 2 周） | —（第四卡座位撤，§4.4） | dub 数据包五字段齐，第 2 周配方检视 overlay 装配所需内容全部就绪 |
| **R5** | AI 生成产物线（声纹 / Speaker / Memory，PROGRESS 第 5–6 周） | 虚拟画面卡 | — |

每期配套：对应素材策展 + 该期 `docs/tasks/` 简报（引用本文档章节号）+ PROGRESS 状态更新。

> **点亮 ≠ 通路（2026-08-05）**：上卡验收只证明能力真实；**完全通路** = Remix → 对话定计划 → 生成 → 结果页知道下一步 → 再生产/精修，由 PROGRESS 第 4 周体验闭环周统一承接——五卡共享一条闭环，不为单卡各建。

## 9. 新开会话导读（用本文档创建 tasks）

1. **先读**：`CLAUDE.md`（UI/工程约定）→ `docs/README.md`（治理）→ 本文档目标期章节 → 该期引用的上游文档（§11 表）。
2. **每期一份 `docs/tasks/` 简报**，模板对齐既有简报（Context / 已核实事实 / 设计论证 / 改动点 / 命名审计 / 分期验收 / Prohibited Behaviors），依据行引用本文档章节号（如 "RECIPES §3.2"）；上游文档清单见 §11。
3. **开工前重核 §0 事实**（代码可能已漂移），事实以读码为准。
4. **运维坑**（已踩过）：改 pipeline 代码必须重启常驻 worker；本机服务调用用 `127.0.0.1` 不用 `localhost`；验证用的手工 run 会被常驻 worker 抢跑，验后清数据。
5. **命名登记清单**（随实施进 NAMING.md 词汇表）：`recipe`（配方卡）、caption preset catalog 及原语词 `layout`/`entrance`/`word-highlight`、`stacking`、`stock voice`（系统音色）、`speaker_map`、`crop_track`、`voice_gen`（synth 简报已登记）、`align_stills`（阅读节奏时间轴，2026-08-05 随 R2 无声版登记）、`reframe_clip`（评审后）、`MENTION_REGISTRY`（提及注册表）/`RECIPE_REGISTRY`（配方注册表）/`input_slots`（输入槽位）/ mention type `"recipe"`（2026-08-01 随 recipe-mention 简报登记）。

## 10. Prohibited Behaviors

1. **禁**未兑现能力的卡可点（点亮纪律修订后：reserved 卡渲染但 Remix 必须置灰/替换为 Soon——承诺永远先于能力）。
2. **禁**配方承诺靠 LLM 从 prompt 重新推断——必须服务端预设播种 + 三方合并确定性兑现。
3. **禁**新表——卡片数据硬编码前端，能力扩展全住 JSON 载荷层。
4. **禁**字幕样式绕过 catalog 加一次性分支；新原语值必须过 libass 映射检查。
5. **禁** composer 加 Audio 块 / 绕过 Speaker 画像另建声音存储（裁决③）。
6. **禁**无声纹阻塞出片（裁决④）；禁 ReAct/多步推理（CHAT_ARCH 铁律延伸）；禁绕过 `orchestrator.create_run`。
7. **禁**卡片预览走登录态 asset 端点（匿名受众必须公开可读）。
8. **禁**分镜跳过 ADR 翻案直接动工；`reframe_clip` 未过 NAMING §7 不进 registry。
9. **禁**前端构造任务书钉（2026-08-01 裁决⑤）：钉死唯一发生地 = 服务端配方注册表解析；composer/chat 只发 mentions。
10. **禁** chip 状态跨发送残留——三律：可见 / 发送即消费 / × 即删；**禁**全屏配方模态框与 DAG 画布外显。
11. **禁** mention 类型一次性分支——新 @ 类型 = 双端注册表各一条注册项（recipe-mention 简报 §2.5）。

## 11. 与其他文档的关系（引导章节）

| 文档 | 关系 / 需要的更新 |
|---|---|
| `STRATEGY.md` §5 | 配方库定位来源；本文档是其实施架构，论证不复述 |
| `PROGRESS.md` | 第 1–3 周排期含配方卡（三卡定格 / 四卡齐亮，已随本文档落地） |
| `tasks/synthetic-talk-video.md` | R2 修订点：voice_gen 先行、`synth_visual` 降可选增强、stock 兜底语义、Speaker 块扩展 |
| `tasks/done/intent-ask-primitive.md` | 声音换声复用 ask 原语 choice 形态（零新机制） |
| `CHAT_ARCHITECTURE.md` §4 | `reframe_clip` 准入评审；`set_caption_style` 枚举随 catalog 扩展 |
| `VIDEO_EDITOR.md` | caption catalog 遵守 preset enum + CSS∩libass 纪律；分镜翻案 ADR 落 DECISIONS 后回填此节 |
| `AGENT_ARCHITECTURE.md` §12 | `voice_gen`/`speaker_map` 节点的内部分析产物 + asset-hash 复用同款哲学 |
| `NAMING.md` | §9.5 清单随实施进词汇表 |
| `docs/README.md` | 本文档已登记索引 |
