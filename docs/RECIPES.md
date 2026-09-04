# RECIPES — 配方架构（Home 能力卡 + 兑现管线）

> Status: 📐 设计定稿（Remix = overlay 内发射，**配方 = 提示词**——预填模板原文即全部发射载荷，方针 `docs/MENTIONS.md` §3；R1–R6 分期见 §8）；**画廊 v3（2026-08-27 拍板，ADR-048）**：三轴模型 + 招牌菜组织原则 + 三级闸门，§4 / §4.8 / §7 已同步
> **架构迭代叠加（ADR-039）**：技能叙事接管——配方 = 技能组合的预设数据包（配方背后是技能，技能内部 = agent 调 LLM 用 tools）；flow key = node kind，启动自检机械对账（§7.1）；配方卡估价贴（报价 = 图 fold）随第七周积分批落地（ADR-055）。
> 上游定位：`STRATEGY.md` §5（配方库 = 品味的陈列窗，不做内容流）；排期唯一事实源 `PROGRESS.md`（架构迭代 + 闭环链 + 人设模块同周 08-10~08-14 三线并行收口）
> 本文档角色：**配方线的母文档**——卡片层 + 能力层的架构与分期；每期施工拆成 `docs/tasks/` 独立简报，引用本文档章节号。新开会话创建 tasks 前必读 §9。
> 用户裁决（现行，设计评审沉淀）：
> ① **配方 = 能力承诺**——上了的卡必须能用用户自己的素材跑出同款，不能写死、不能仅 demo（STRATEGY"配方卡不做营销剧场"的产品化口径）；
> ② 首页形态 = composer 下方**配方卡画廊**（**v3，2026-08-27 拍板，ADR-048**：卡 = 招牌菜、画廊不为覆盖负责，组织原则 = 霸道程度，覆盖需求归选题库 ADR-042；八卡六形态——原声AI配音 voice-dub / 金句卡 quote-cards / 高光切片 highlight-clips / 多语言字幕 multilingual-subs / 图文视频 image-video / 轮播图 carousel / 访谈分镜 reframe / 社媒帖 social-post；选卡三级闸门见 §4.8；卡面 = 工艺示意图封面 + 图下三行，证据层 = overlay 示例 tab），源素材用云端 demo talk；
> ③ 声音的家 = **人设块扩展**（声纹 = 人设属性；stock voices 以"系统音色"身份进人设选择器系统区，不伪装成人设——ADR-037 修订形态），composer 不加 Audio 块；
> ④ v1 图片视频 = **无声版先行**（照片轮播+字幕+音乐，不需要真人说话，无声纹不阻塞）；声音路径（voice_gen / TTS / stock 兜底 / 换声入口）整体后置声纹线（§4.2，排期见 PROGRESS）
> ⑤ **Remix 形态 = overlay 内发射，配方 = 提示词**（对照 ElevenLabs 全屏模态框 / Agent Opus composer mention 后裁决；mention 哲学升级后定稿，MENTIONS §3；2026-08-11 二次修订）：点卡 = 检视 overlay 的发射区直接发射——点卡动作本身已是配方身份，句中 chip 是第三遍冗余；配方**永不是 mention**（两族都不落）。**发射的全部行为载荷 = 预填模板原文**（模板点名产出与语言）：无 `recipe_id` transport、无服务端播种，任务书由 book path 从消息文案推断，与 composer 完全同径（chat 恒胜绝对成立——没有隐藏第二通道能盖过用户对预填文案的编辑）。**否全屏模态框自跑生成**（第二条派发面，与"composer = chat 第一条消息"冲突；承诺呈现归既有审阅面板）。mention 系统是**双端注册表架构**（`asset` 为成员），后续 @ 类型只填注册项；配方结构数据升服务端注册表 + 公开只读端点（卡面 / 检视 / 启动对账自检，§7.1）。DAG 永不外显，"编辑流程"等价物 = chat（plan 级 ops + 子图词汇，排期见 PROGRESS）。
> ⑥ **功能扩展的唯一门 = SKILL_REGISTRY 注册项**：重试/输入校验/拓扑约束/进度文案/计量提示随登记免费获得；禁为单节点开平行映射表或特判分支（CHAT_ARCH §4 扩展门纪律）。

## 0. 已核实的现状事实（读码确认）

- **dub 全链路已在跑**：`tools/dubbing.py`（翻译字幕轨 → 声纹合成 → 替换原音轨）+ `ClipDub` 进 clip-spec + `Clip.tsx` dub 音轨渲染 + dub 技能节点（`skills/dub/node.py`，`DubClip`，kind=`dub_clip`，技能已对象化，`node_runners.py` 无 dub runner）已登记可派发。多语言 = 同族节点按语言扇出，**零新代码**。
- **stills audiogram 全链路已在跑**：`ClipSource.kind="stills"`（图片轮播 + 可选语音轨 + 字幕映射不变 + 音乐循环）；slides→images（`asset_processing.py`）、audio→stills（`skills/clips/node.py`）均在跑；loudnorm 已处理静音渲染。
- **字幕现状**：`caption_style_preset` 枚举 6 值（`clean-bottom`/`karaoke-highlight`/`fade-in`/`pop-in`/`slide-up`/`stacking`）——堆叠字幕已收编落地：`stacking = {layout:"stack", entrance:"fade-in", maxLines:5}`（前行驻留、向下累积），`Clip.tsx` 已渲染 stack 布局（preview=render 双端生效）。
- **crop 是 clip 级静态值** `ClipCrop{x,y,scale}`，无时序；ASR = faster-whisper（词级时间戳，**无 diarization**）。
- **`packages/clip` 是 editor preview 与 render service 的同源组件**——渲染分支加一处，preview=render 双端自动生效。
- **任务书 = 技能链（ADR-043）**：请求层唯一语法 = task list（`tasks[{skill, params}]`），产物 = 编译图的派生投影（`derived` 预览行）；chat book path 接受 `prior_intent`（整链 JSON 随行，chat 修订永远赢——无合并机器）；`pending_brief` + 项目页 dock 恢复管道在（`?overlay=chat` 路由参数 2026-08-31 ADR-051 退役——draft 项目直达 `/projects/$id` 即复活任务书）。
- **composer = prompt-only**（instruction + persona_id），意图识别全在管线。
- **文字稿+照片场景已有 Ready 简报**：`docs/tasks/synthetic-talk-video.md`（`voice_gen`/`synth_visual` 节点设计，声纹 TTS 回配 ASR 时间戳，下游零感知）。
- **demo talk 素材**：`demo/` 前缀是 reset_db 保护区（永不擦除）；配方演示资产内容寻址入桶（哈希 URL 固化在 `apps/web/src/lib/recipes.assets.ts`）。

## 1. 原则

1. **配方 = 待填素材的任务书模板**（Phase 1 形态）。配方与素材的关系只有两层：展示素材（卡片预览，不进管线）+ 类型化输入槽位（"需要一段演讲视频"的约束）。素材是配方留给用户的唯一空格。升级为"待填素材的施工图模板"是 Phase 2（STRATEGY §5，依赖公开性字段 + ADR，不在本文档范围）。
2. **点亮纪律**：五张卡**全部渲染**（presence over gating——画廊存在感优先）；纪律的保留线是**承诺不可点**——能力未兑现的卡（reserved）hover 只给 Soon 标记，不出 Remix 按钮。点亮 = `status` 翻 `live` + Remix 解锁，不要求齐发。
3. **DAG 编排全复用**：每个新动词（节点/契约扩展）落地即免费获得编排、逐节点计量、SSE 打勾流、失败重试、子图重跑。零新表——一切住 JSON 载荷层（clip-spec / node.spec / run.context）。
4. **可扩展词汇一律注册表化**：字幕样式、skill、节点 kind 同纪律（`SKILL_REGISTRY` / `NODE_RUNNERS` 先例）——加成员是填注册项，不是加分支。
5. **内容定位**：卡片围绕 LinkedIn / 多语言 / 专家需求（欧洲 ICP），不做 TikTok 风（CLAUDE.md 产品定位）。
6. **配方 = 数据包**：base + flow + prompt + example_assets + example_outputs（+ 服务端 outputs 预设），schema 见 §7.1。扩展配方 = authoring 数据条目，不是写代码——除非该卡演示的能力本身是新的。卡面立项门槛 = 一道具体的菜 + 三级闸门（§4.8）。

## 2. 三层正交架构

配方的全部变化分解为三个独立演化的层，层间自由组合——"很多种效果"的支持 = 组合免费，不是专用代码路径：

```
视觉底（source.kind）     ⊥  字幕效果（caption catalog）  ⊥  声音/时间源
──────────────────        ─────────────────────────       ─────────────────────────
video（实拍）               clean-bottom                    原声音轨 + ASR 词级时间戳
stills（照片轮播）          karaoke-highlight               TTS 声纹 + ASR 回配时间戳
slides（PPT 转图）          fade-in / pop-in / slide-up     无声：阅读节奏估算（✅ align_stills）
                            stacking                        + music 槽（独立开关，已有）
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

## 4. 八卡六形态（画廊 v3，2026-08-27 拍板，ADR-048）

> **卡 = 招牌菜，画廊不为覆盖负责**（v3 根判）：组织原则 = 霸道程度（ICP 看一眼想要、试做一次被送进 chat 主链路）；覆盖需求归选题库/定位根（ADR-042），首访靠招牌菜接住、回访靠"你的素材还能切什么"接住。**三轴模型**：卡轴 = 产物形态 / 路径轴 = 输入→工艺（宽槽，管线按输入画像自适应）/ 适配轴 = 渠道（发布期变量，永不进卡）。**选卡三级闸门**（§4.8）：① 场景真实性 ② 形态或环路不可替代 ③ demo 霸道。**排序 = 霸道序**（行语义退役；过不了示例验收的卡不进网格，§7.3）。**阵容治理**：座位变更必附翻案条件 + 认路级证据，不当周翻案。处境 × 卡映射（卡的合法性来源）见 ADR-048 动机章。

| 序 | 卡 | 形态 | 承诺 | 输入槽（类） | 点亮 |
|---|---|---|---|---|---|
| 1 | 原声AI配音 `voice-dub` | 多语言版本 | 用你的声音，把同一段视频讲成另一种语言 | 演讲 · 会议录像（转化类，窄槽必填） | ✅ Live |
| 2 | 金句卡 `quote-cards` | 金句叠卡 | 挑出最亮的几句话，叠成一张可以直接发的金句卡 | 录像 / 照片+文稿 / 纯文稿（合成类，宽槽三路径——v3 工程见简报） | ✅ Live |
| 3 | 高光切片 `highlight-clips` | 竖屏短片 | 长视频里最好的几段剪成竖屏短片——镜头自动跟人，最值得先发的也标出来 | 长演讲录像（转化类，窄槽必填） | ✅ Live |
| 4 | 多语言字幕 `multilingual-subs` | 多语言版本 | 为你的视频配上多语言字幕，单行或双语，观众按自己的语言看 | 演讲 · 会议录像（转化类，窄槽必填） | ✅ Live |
| 5 | 图文视频 `image-video` | 图文轮播视频 | 没有录像——照片加文字稿，变成带字幕和音乐的轮播短片 | 文稿 + 照片 · 课件（合成类） | ✅ Live |
| 6 | 轮播图 `carousel` | 轮播幻灯 | 讲稿或课件要点，变成一叠可以翻页的图文幻灯 | 讲稿 · 课件要点（合成类，可空） | ✅ Live |
| 7 | 访谈分镜 `reframe` | 竖屏短片 | 横屏双人对话重剪竖屏——镜头跟着说话人走 | 双人对谈录像（转化类，窄槽必填） | ✅ Live |
| 8 | 社媒帖 `social-post` | 帖子长文 | 讲稿或长文，变成可以直接发的帖子——用你的风格写，发哪个平台你定 | 讲稿 · 论文 · 会议纪要（合成类，可空） | ✅ Live（demo 重修为风格对照，§4.6） |

### 4.1 多语言字幕卡（multilingual-subs）——新旗舰

- **定位**：多语言旗舰从 dub 换成字幕卡（2026-08-13 拍板）。依据：主渠道 LinkedIn 视频默认静音自动播放，**字幕就是主消费层**；原声 = 真实性的指纹（反 slop 战略，STRATEGY 牌 4）——AI 做翻译字幕，真实人声当主角，比"AI 声音当主角"更对得起定位。
- **承诺**（2026-08-23 修订）：为你的视频配上多语言字幕，单行或双语，观众按自己的语言看。——主语从"演讲"放开到"视频"；**配音职责移交 `voice-dub` 卡**（ADR-048 拆分——本卡只卖字幕；配音经 chat 一句"再用我的声音配一版"随叫随到，通道不变）。**卡不含剪辑**（2026-08-14 三次修订，用户拍板）：只展示多语言与字幕能力——流程图摘掉剪辑规划步骤（理解素材 → 翻译字幕×2 → 配音 → 渲染），示例提示词只点名多语言诉求（烘焙示例碰巧是高光片段，但卡不卖剪辑）。
- **能力现状**：caption 翻译链（translator agent + `translate_caption_track`）在跑；重渲染零缺口。**双语对照已落地**（2026-08-14）：`ClipSpec.translation_track` 单元级对照轨 + `translate_clip` 任务参数 `bilingual`（ADR-043 后住任务参数，原任务书字段退役）——fork 保留原文 word 轨、译文入对照轨，渲染端译文主行 + 原文小行在下（stack 布局只画原文轨——双语堆叠墙不可读）；标题 overlay 随字幕同译（`translate_text`，dub 2026-08-09 同款教训）。配音变体同图编译（`dub_clip` fork，声纹克隆原声）。
- **画幅**：clip-spec `aspect` 四档全链放行 `"9:16" | "1:1" | "16:9" | "original"`（`original` = 整条材料化跟源画幅，渲染端 calculateMetadata 探源尺寸，仅 materialize_source 写入；schema / clip_spec clamp / 渲染端 ASPECT_DIMENSIONS 1920×1080 / `set_aspect` op / 编辑器下拉）；画幅请求 = `select_clips` 任务参数 `aspect`（ADR-043 参数化——intent router 从"横版/保持原画幅"等点名识别，省略 = 皮肤默认 9:16），编译进节点 `spec.aspect` 覆盖品牌默认（run.context 的 `aspect` 仅为存量读容忍）。本卡 demo 源是方幅 → 卡烘焙 1:1。卡面/teaser 展示横、方幅时**上下留黑保原比例**（object-contain，抖音横屏竖放惯例），永不裁剪。
- **字幕尺寸按画面推导**（2026-08-14，用户拍板）：不做固定像素——皮肤 `captionSize` 是 1080×1920 竖屏基准值，渲染端按帧高等比缩放（默认 68 → 9:16 保持 68，1:1/16:9 得 38，≈3.5% 帧高 = TikTok/CapCut/YouTube 跨画幅通用比例）；左右边距 8% 随帧宽自适应；标题 overlay 同规则缩放。**双语对照两行打折**：译文主行 ×0.82、原文小行 ×0.55（两行需要空气）。
- **示例提示词教学位**（2026-08-14 二次修订，取代 variants desc）：左区「示例提示词」标题 + 按卡 `recipes.<id>.promptHint` 引导句（字幕卡点名「双语字幕」「中文字幕」「西语配音」示例）——变体教学从承诺句下的 desc 行移入提示词区，引导句不是控件的纪律不变（§7.2）。
- **素材账单**：`demo/uploads/xy_2_15s.mp4`（WFT 登台演讲 530–545s 截取，960×960 方幅，"We Focus on Industries" 内容页稳定窗，已策展 2026-08-13）；预览 = 同选段 1:1 四案例对照包——EN 原声 + 中英双语对照 + FR 单行字幕 + ES 声纹配音——真管线跑出后由 `scripts/bake_subs_contrast.py` 收获（harvest 模式：run 产物 Output id 或本地 mp4 + 每案例独立 poster 帧，内容寻址入 demo/ 树；FR 单行版脚本侧产——run 级双语开关下管线 fork 出来都是双行）。

### 4.2 图文视频卡（image-video，已 Live，扩 slides 槽）

R2 兑现内容不变（无声版先行：照片轮播 + 字幕 + 音乐；`align_stills` 阅读节奏词轴与 ASR 同构）。**输入槽扩 `slides`**：PPT/PDF 转页图已在跑（§0），课件场景并入本卡——"课件讲解"不单立卡：静态课件页 + 字幕 + 讲解音频/声纹对齐 = 三层正交架构内组合（slides 视觉底 × caption catalog × 音频/TTS 时间源）。**动画与转场不做**（L3 范围纪律，VIDEO_EDITOR；委托剪映/Premiere）。承诺句不得写"动态演示"。**画幅跟源**（2026-08-17 拍板）：本卡链无 clip 类技能 = 画面没倒手，输出比例跟素材原画幅（横版照片/课件 → 16:9）——示例片按源烘焙 16:9（照片满幅零裁剪），promptTemplate 点名「保持原画幅」（真实 run 经 intent router 考纲映射源形固定档兑现；任意源形由 renderer `original` 档兜底——整条材料化默认跟源）。

### 4.3 高光切片（highlight-clips）与访谈分镜（reframe）——一个能力，两道菜

- `crop_track` 关键帧轨是同一工艺层：大型中景演讲（**动态人形追踪**）与双人访谈（**静态说话人切换**）共享第三周 spike。spike 范围扩为双验证（2026-08-13 拍板）：静态双人分镜 + 单人中景动态追踪（VIDEO_EDITOR 封存的 auto face reframe 重启评估，立项评审 08-17 已有议程）；验证不过则高光切片卡先出静态中裁版，回退吃第四周缓冲不变。
- 高光切片 = 起家能力（理解 → 选段 → 字幕 → 渲染 + 首发推荐分）+ 追踪工艺。
- **两卡点亮排在定位根落地后**（PROGRESS 第八周批次，用户拍板）：它们是选题库"你的素材还能切什么"的主承载菜，随运营端收口一起 authoring（数据条目 + 预览烘焙）。
- **素材账单**：`xy_2.mp4`（大型登台 PPT 演讲，已策展）→ highlight-clips；`xy_1.mp4`（左右对坐访谈，已策展）→ reframe。

### 4.4 虚拟视频卡（ai-visuals）——出列进需求池（2026-08-23，ADR-048 第 7 条）

证据层改制（§7.3）后 Soon/reserved 形态退役——示例 tab 拿不出真实成对示例的卡不进网格。R5 能力线（PROGRESS 第六~七周）照跑不变；座位重挣条件 = R5 就绪 + 真实成对示例可烘焙 + 三级闸门重过（②形态不可替代它天然满足，①场景真实性需重估）。

### 4.5 原声AI配音卡（voice-dub）——dub 回列为独立卡（2026-08-23，ADR-048）

- **拆分依据**：08-13 的「dub 撤座降为字幕卡配音变体」翻案（用户拍板原话：字幕配音确实要拆）——"保留原声看字幕"与"用我的声音说外语"是两种用户意图；拆分后 8 张满编，轮播图同批进列。
- **卡名即护城河**：「原声AI配音」把声纹克隆写进菜名——通用大模型写得出译文、发不出你的声音（闸门②双重不可替代：声纹克隆形态 + C2PA 合规链 ADR-026）。
- **能力现状**：dub 全链在跑（§0：翻译字幕轨 → 声纹合成 → 替换原音轨 + 逐单元音画对齐）；卡面示例 = 既有 dub 对照包资产（EN 原声 + ZH/FR/ES 配音，`bake_dub_contrast.py` 已收获）——本批唯一示例零新烘焙的新卡。
- **封面 200px 测试对**：与字幕卡的区分 = 人头+声波+语言芯片（本卡）vs 视频框+双字幕条（字幕卡）——图语言纪律：配音卡封面不画主字幕（工艺图强调各自变换，非产物承诺，ADR-048 第 1 条界定）。

### 4.6 文本族三卡（social-post / quote-cards / carousel）——进列依据与形态

- **能力全部在跑**：write_post（06-22 起）/ quotes（06-29 起）/ carousel（06-29 起）；卡面缺的只是数据条目 authoring + 示例烘焙（真管线收获入 demo/ 桶）+ 验收闸扩展——无新能力开发。
- **过闸门的方式各不相同**：金句卡与轮播图靠**产物形态**（排版设计过的图/幻灯——ChatGPT 写得出文字、排不出版）；社媒帖靠**环路上面**（promise 明写"用你的风格写，发哪个平台你定"——人设风格六件 + 渠道发布是通用大模型做不到的两件事；裸帖子文本本身可被简单代替，环路不能）。
- **金句卡 = 叠卡本体**（v3，2026-08-27 拍板）：stacked 叠卡（3–7 条帧 strip 级联）是卡面唯一承诺形态——同族只摆最霸道形态，单句图归 chat 能力；legacy 逐条 fan-out 与 `layout_mode` 字段退役；**帧卡 Output 化**（N 个帧卡 image Output + source_ref 谱系 → 1 张合成卡，chat 逐条精修下期，寻址信息本期留足）——工程与迭代欠账清单见 `docs/tasks/quote-cards-redesign.md`。
- **社媒帖 demo 重修为风格对照**（v3 闸门③标准姿势）：同素材"无人设版 vs 人设版"并排——文本族的霸道 = 可见的人设差异，随烘焙批收获。
- **渠道不进卡面**（ADR-048 三轴模型适配轴）：菜名 = 形态词（社媒帖，非 LinkedIn 帖）；预填模板可点名默认渠道（可见可改），chat 恒胜。
- **overlay 示例形态**：文本/图片产物平铺卡——输入 transcript 摘录卡 ↔ 输出帖子文本卡 / 金句图 / 幻灯序列（与视频卡的成片对照同构，零新机制）。

### 4.7 撤座与退役

- **dub 撤座条款翻案**（2026-08-23）：回列为「原声AI配音」独立卡，见 §4.5。
- **虚拟视频卡出列**（2026-08-23）：见 §4.4。
- **语音转观点卡否决**（2026-08-23，闸门①）："随手录语音变结构化观点帖"是人造场景，不是专家工作方式；能力（ASR + write_post）经 composer/chat 照常可用——卡片缺口 ≠ 能力缺口。
- **talking-head（口播）撤座**：低频 + 数字人对专业人设的信任风险；能力路线若未来成立，按三级闸门重新挣座位。
- **风格卡撤座裁决不变**（风格是产物的修饰不是产物；沉 look 层，三个家不变）。
- **"一鱼多吃"打包卡永久否决**：多产物是能力面不是承诺（07-31 拍板）——扇出由结果画布展示、由 chat/选题库承载，不做"一键产出一整套"的预设卡。

### 4.8 卡面立项门槛（v3，2026-08-27 修订，ADR-048 第 3 条）

一道具体的菜（下限）× **三级闸门**：① **场景真实性**（专家真实高频场景，人造场景一票否决）② **形态或环路不可替代**（ChatGPT 测试；环路价值可上面者豁免）③ **demo 霸道**（成对示例本身就是卖点——金句叠卡形态 A/B、声纹对照包级别；示例平平的，能力再真也不上桌）× 技能链证据（点亮 = 能力真 + 示例真——真实成对示例可烘焙）。**体裁标准答案**：一个能力族只摆最霸道的一种形态上卡，其余形态归 chat 能力——新体裁不触发"找座位"。**阵容治理**：座位变更（进/出/合并/拆分）必附翻案条件 + 认路级证据（复述测试 / 真实用户行为），不当周翻案。候选存档：杂志访谈风 keynote 短片（stacking + 顶部 title + intro 标题页，素材 `xy_2.mp4` 已策展）。

## 5. 声音层（裁决③④落档）

- **家 = 人设块扩展**：声纹 = 人设属性（已决架构不变）；人设选择器加"系统音色"区——stock voices 以**系统音色**身份出现（如 Rachel · Confident，带试听），不伪装成人设（ADR-037 修订形态），与"👤 Anna（cloned ✓）"同列表分区。composer 维持两块不加 Audio 块（避免与人设职责重叠；Opus 的 Style/Assets/Audio 三块形态已评审未采纳）。
- **voice_gen 阻塞语义**：无声纹 → stock 默认声直接出片，**不阻塞**；QuestionDock / 审阅面板可换声（复用提问机器的选项问形态，`tasks/done/intent-ask-primitive.md` 期 3 机制零改动）；引导克隆是轻提示不是拦截（录 10s 样本路径已有 `tools/voice.py:clone_voice`）。
- **stock 声来源**：MiniMax 系统音色（零克隆成本）。**待核实**：系统音色清单与多语言覆盖（EN/DE/FR/ES/IT/ZH 必须齐），核实结果回填本节与 R2 简报。
- **后置**：语速调节、Pronunciation 纠正（归术语表线（PROGRESS 可选需求））。无声版（阅读节奏估算）已落地为 R2 交付本体（`align_stills`，§4.2）。

## 6. 分镜能力指引（简报 B 种子）

> 简报 B 立项时本节内容平移为简报正文；此处锁定方案与决策负担。

- **决策负担**：VIDEO_EDITOR "automatic face reframe = L3（交 CapCut/Premiere）"是封存决策——按 DECISIONS 纪律**写新 ADR**（新编号，封存行同步从 VIDEO_EDITOR 删除），理由：从"自动人脸跟踪"收窄为"**静态双人分镜**"（固定机位、左右分坐——欧洲会议对谈/播客主流形态），工程深度不同；STRATEGY 本将"运镜枚举"列为 L2 缺口，重审有据。
- **检测方案（零新模型依赖）**：whisper 词级时间戳切语音段（已有）→ **M3 视觉 filmstrip**：段内 4–6 帧拼网格，一次调用判"哪侧人物嘴在动" → 说话人时间轴 `speaker_map`。**只分析选中 clip 窗口**（选段后执行，5 clips × 十余段 ≈ 几十次视觉调用，逐节点计量）；双人访谈语音极少重叠，准确率有保障。
- **架构落位**：`speaker_map` = 素材级内部分析产物（`material_understanding` 同款，asset-hash 复用）；clips 选段后、渲染前加分析节点（agent 节点，可寻址可重跑）。
- **契约扩展**：`crop` 静态值 → 增 `crop_track` 关键帧轨（向后兼容，静态值作缺省）；`Clip.tsx` 按 sourceTime 采样当前 crop（preview=render 同源）；滞后/平滑规则（最短驻留 + 缓动，防跳切眩晕）。
- **skill 准入**：`reframe_clip` 过 NAMING §7 评审后登记（CHAT_ARCH §4 纪律）。
- **v1 范围**：静态双人 only；多人/移动机位/侧脸归后续。

## 7. 卡片层（数据 + 交互 + 布局）

### 7.1 卡片数据：Recipe 数据 schema（配方 = 数据一个包）

**配方 = 一个数据包**。一张配方卡 = 五个字段，所有消费方（卡面 / 检视 overlay / book path 播种 / 未来真实 Gallery）读同一个包：

```
Recipe = {
  base:            名称 / 承诺 / 标签 / 画幅 / status        → 卡面 + overlay 发射区抬头
  flow:            只读静态流程图（key = node kind，展示名走 recipes.flow.* i18n，无模型名） → overlay"流程"tab 画布的步骤段（ADR-035/036）+ 启动自检对账
  prompt:          示例 prompt                                → overlay 发射区预填文本（可见可改，修改唯一入口）
  example_assets:  示例原素材（demo/ 桶引用）+ input_slots     → overlay 示例 tab 输入区 + 流程画图源节点 + 发射区素材需求提示
  example_outputs: 烘焙成片（内容寻址引用）                    → overlay 示例 tab 输出区 + 流程画布终节点（卡面 2026-08-23 起不消费烘焙成片——封面 = 工艺示意图，ADR-048）
  tasks:           预设技能链（intent router 同款 task list 语法，ADR-043）→ 仅启动对账自检消费（flow ⊆ 编译图），永不进请求路径
}
```

- **可见性分层 = schema 的字段级属性**：公开投影（base / flow / prompt / example_assets / example_outputs——落地页匿名受众可读）经 `GET /api/v1/recipes` 下发；**预设实质（tasks）永不出服务端**。原"双端分半"纪律收编为字段可见性，不再是两套机制。
- **存储纪律**：结构数据与资产引用直接持有于服务端 `app/pipeline/recipes.py` 静态注册表（SKILL_REGISTRY 同款，随代码部署）；**可翻译文本**（title / promise / prompt）以 i18n 键引用（en 为源语言，现状纪律不变）；烘焙资产以内容寻址 URL 引用（`recipes.assets.ts` 由上传脚本生成，现状不变）。
- **flow ↔ tasks 机械对账**（ADR-039/043）：flow 的 key = node kind（fanout 展开规则不变）；启动自检以 `compile_graph` 纯函数编译配方预设链（tasks + 输入画像推出 materialize 注入），断言 flow keys ⊆ 编译图 kind 集——展示图与真实图**永不漂移**，人肉评审对账退役。
- **配方估价贴**（ADR-039 / NAMING N-34）：预设图编译期定死 → 配方估价 = 图 fold 近常量；卡面"约 X credits"随第七周积分批（逐节点 `estimate()`，ADR-055）落地。
- **flow 的消费规格（D6）**：overlay 右区两 tab——**示例** = example_outputs / example_assets 平铺卡（自动静音循环 + 单张发声开关，零边零图）；**流程** = **唯一图画布**（FlowView 渲染）：素材 → 策展步骤（`fanout=N` 展开为同深度 N 个平行分支，dub ×3 = 三条语言分支）→ 烘焙成片终节点的**一张图**——素材→步骤 = 依赖边，终步→成片 = 血缘边。图只画一次（ElevenCreative 证据：示例平铺输入/输出，流程才是图）；手风琴 / 折叠文本形态退役。
- **新增配方 = 写一条数据条目**（注册项 + i18n 键 + 烘焙资产），零代码路径——除非该卡演示的能力本身是新的（如分镜的 crop_track）。"扩展配方卡"的全部工作自此统一为 authoring 数据。
- **封面 `cover` 不进数据包**（2026-08-23，ADR-048 第 1 条）：卡面媒体 = 前端 inline SVG 工艺示意图组件（`components/recipes/covers/` 按 recipe id 注册）——构图 = 左素材→右成品横向叙事，三档灰吃 token（亮主题自动反转），验收 = 200px 无字测试；零烘焙、零媒体请求。烘焙资产消费面收窄为 overlay 示例 tab + 流程画布。
- `inputSlots` 消费者：发射区 Input 小节图标（前端展示，`input_slots[0].type`）与启动自检的输入画像（服务端 `_recipe_adds_stills` + materialize 注入画像，flow ↔ tasks 对账）。
- **`input_slots` 两类卡语义**（v3，ADR-048 第 6 条）：转化类卡 = 窄槽必填（现状 `required: true` 逐条全覆盖，发射闸门同款）；合成类卡 = 宽槽**"任选一"** + 可空（copy-writer 无素材 lift 已放行空槽）——槽宽 = 管线真实路径的边界，不更宽（诚实纪律）不更窄（不绑死）；路径打通一条槽里加一类，同一道菜长路径永远不是新座位（金句卡三路径：录像 / 照片+文稿 / 纯文稿）。字段命名随实施过 NAMING §7；overlay 发射闸门与 Input 小节文案同步。
- **配方 id 的消费谱系**（2026-08-11 裁定）：id = 橱窗项的键（注册表 / i18n 文案 / 公开端点 / 对账自检迭键），**编译期与展示期合法**（卡面目录 / 检视 overlay / 预填模板 / flow ⊆ 对账 / 估价贴 fold），**请求期禁止**——id 永不作行为输入过请求线（无播种、无 422 塑形、发射不依赖 id，prompt 文本独自完整成立）。新消费面先登记本清单（注册项准入同款纪律）。

### 7.2 点击链路：overlay 内发射（配方 = 提示词）

**入口分工**：**composer = 通用 / 多种 / 复杂 / 自定义提示词的组合式需求入口；配方卡 = 预设快捷需求入口。**两者共用同一发射机构与同一 chat 主线，无平行表单。**配方卡 = 能力的陈列窗 + 新手的坡道**（2026-08-11 定格）：陈列策展的能力组合与同款证据，让零经验用户一键开始；预填模板同时是提示词示例教学——用户看着模板学会"原来可以这样点名"，毕业后自有能力走 composer。

**文案承接四层**（v3，ADR-048 第 4 条）：① 卡面纯菜——三行写这道菜不写能力族，不加"你还可以…"meta 句；② overlay `promptHint` 升格为"还能怎么点"（改口示范 + 能力族暗示；纯文案，控件禁令不变）；③ 示例 tab = 不说话的广度（多形态示例平铺，证据展示广度永远比文案声明广度有力）；④ 画廊末尾一句总承接（全画廊只出现一次）+ 流程内教学（预填模板可改 = 第一次提示词教学，chat 修订 = 第二次，结果画布"下一步"= 第三次）。**Input 小节两类卡文案**：转化类直说要什么（"给一段录像"——窄是这道菜的本性，不尬）；合成类"给什么都行"（只列已验证路径；槽宽 = 真实路径边界）。

```
点卡 → 检视 overlay（左发射区 + 右检视 tabs，D6 二次修订）
     → 发射区 = composer 发送机构挂载（同一发射台的第二个停放位）：
       上传暂存区（主角——素材是配方唯一的空格，Input 小节署名所需素材）
       + promptTemplate 预填 textarea（常显可改，修改唯一入口）
     → 发送：建项目 → 上传 → 跳转 overlay chat → 首条 POST /chat { message, persona_id }
       （与 composer 发送完全相同的路径；overlay 零推断 / 零 prior / 零生成）
     → 服务端 book path 与 composer 完全同径——模板原文即全部载荷，
       任务链从消息文案推断（零播种、零 resolve、配方身份不过线）
     → pending_brief（链 + derived 预览）→ overlay 计划卡逐行呈现 → Start
```

**配方身份不过线**（MENTIONS §3，2026-08-11 裁定）：不进句子、不出 chip、无 transport 字段、无跨发送残留——发射的全部行为载荷 = 预填模板原文，点卡动作与 overlay 标题已各自陈述身份；发射后草稿随导航消亡。服务端注册表的 `tasks` 仅作启动对账自检的**声明形态**（flow ⊆ 编译图，§7.1），不进请求路径。

**修改通道**：预设参数（如 dub 目标语言 zh/fr/es）**永不做选择器控件**（预设空间无界；控件 = A 形态漂移 + prior 旁路）；预设的可见性 = **预填 prompt 文案本身**（模板直接点名产出与语言）+ 示例/流程检视视图——镜像 chips 撤除（与文案重复，且被误读为选择器）；**修改** = 预填文本改字（发送前）/ chat 修订（发送后）——两个时刻一个通道，chat 恒胜。

**示例提示词教学位**（2026-08-14 二次修订，variants desc 机制同日退役）：发射区提示词块标题 = 「示例提示词」，下方一行**按卡**引导句（`recipes.<id>.promptHint` i18n 键，不进注册表——纯文案），职责 = 告诉用户这道菜还能怎么点（字幕卡点名「双语字幕」「中文字幕」「西语配音」），并把用户引到合法修改入口——写法是教路径的引导句，**禁做成选择器控件**（预设参数控件禁令的延伸）；未来若要可点，唯一合法形态 = 点击把示例句子插入预填 textarea（预填文案仍是唯一事实源）——待复述测试级证据再建。与技能标注 chips 分层：chips = "这道菜用了什么"（事实陈列），promptHint = "还能怎么点"（修改引导）。

点卡 = 配方唯一发射入口（composer @ picker 永不出配方项，MENTIONS §3）；chat 输入同组件，派发走既有 task_book dock 确认面。承诺的形状 = **模板文案点名（用户可见可改）+ book path 推断出链 + derived 预览呈现产物**——与 composer 主路同一份保证；LLM 永不解释配方（配方身份不过线）。匿名访客点卡 → 同一套组件预填，发送时走既有 requireAuth 闸（双受众复用，STRATEGY §5）。

### 7.3 布局与素材

- home：composer 区下方卡片画廊（**v3，2026-08-27 拍板，ADR-048**）：**均匀 4 列网格**（`grid-cols-2 md:grid-cols-3 lg:grid-cols-4`，容器 max-w-6xl；MasonryGrid 瀑布流基座与 featured 跨列退役——排序即霸道序），卡序 = 注册表插入序 = **霸道序**（voice-dub → quote-cards → highlight-clips → multilingual-subs → image-video → carousel → reframe → social-post；行语义退役，网格从左到右自然落位）。**卡面 = 16:10 黑白灰工艺示意图封面**（inline SVG，左素材→右成品横向叙事；rest 静止 → hover 播过程动画 + Remix 丸居中 + expand 右上，均只开检视 overlay）+ **图下三行**（菜名 / promise 两行封顶 / 适用素材 meta 行）；badge 与类目 chip 退役（卡面不锁画幅、输入锚点归适用行），渠道名不上卡面（genre only——「社媒帖」非「LinkedIn 帖」，渠道 = 发布期变量：预填模板带默认渠道、chat 恒胜）。**网格零真实媒体**（无视频无 poster 无 preload——证据层 = overlay 示例 tab 的成对前后对比，升格为验收标准：拿不出真实成对示例的卡不进网格，Soon/reserved 形态退役）。点击卡面开检视 overlay（唯一动作）；composer 的 @ picker 只有素材项，配方永不出现在句中（MENTIONS §3）。遵循 CLAUDE.md：rounded-lg、无 ring/border、无投影（封面 tile 底 = `bg-inset` 井，fill-first 准则）。
- 预览资源必须**公开可读**（落地页匿名受众）：`apps/web/public/` 或对象存储公开前缀——现有 asset 端点全是登录态，不可用。
- 素材策展总账：① demo talk（桶 `demo/` 树，✅ `demo/uploads/demo_talk.mp4` 11MB 单人 TED 风演讲——dub 对照包源）；② 双人访谈横屏视频（✅ `demo/uploads/xy_1.mp4` 17MB 左右对坐访谈，访谈分镜卡源）；③ PPT 大型登台演讲（✅ `demo/uploads/xy_2.mp4` 63MB 960×960 方幅 13min，高光切片卡源）＋ **15s 展示切片**（✅ `demo/uploads/xy_2_15s.mp4`，530–545s "We Focus on Industries" 内容页稳定窗，-14 LUFS 已归一，**多语言字幕卡展示源**，2026-08-13）；④ 各卡预览成片（能力兑现后跑真管线收获，烘成静态资源）。多张卡复用 1–2 场源演讲。

## 8. 分期与验收

| 期 | 内容 | 上卡 | 验收（e2e 真实管线，无测试套件纪律） |
|---|---|---|---|
| **R1** | caption catalog 收编 + `stacking` preset + dub 配方接线（clips→dub×N 单 run）+ 卡片层（schema/布局/点击链路/i18n）（实施简报 `docs/tasks/done/recipe-cards-r1.md`；交互形态 = overlay 内发射 + 预填模板载荷，MENTIONS §3） | dub 卡 | 用户素材走 dub 卡 → 单 run 出 clips+多语言 dub 产物；stacking preset 在 editor preview 与导出 MP4 一致 |
| **R2** | `align_stills` 注册项（阅读节奏时间轴）+ DAG 输入画像注入 + stills 字幕轮播链（无声版先行，声音路径后置声纹线，§4.2） | 图片视频卡 | 文字稿+照片 → 照片轮播+字幕（stacking 等 catalog 成员）+音乐成片；词级时间轴与 ASR words 同构，editor/chat 换字幕样式即生效 |
| **R3** | 简报 B：分镜 ADR + filmstrip 检测 + `crop_track` + `reframe_clip`（静态双人分镜 + 单人中景动态追踪双验证，PROGRESS 第三周 spike） | —（能力先行；分镜双子卡卡面 authoring 延至定位根落地后，PROGRESS 第八周） | 双人访谈 → 竖屏分镜 clips，说话人切换正确、无眩晕跳切 |
| **R4** | Recipe 数据 schema 定义（§7.1）+ dub 落成第一个完整数据实例（示例 prompt / 素材账单 / 静态流程图 / 预览烘焙）+ remix→chat 链路走查补缝（08-07 启动 ~ 08-11，PROGRESS 第 2 周） | —（第四卡座位撤，§4.5） | dub 数据包五字段齐，第 2 周配方检视 overlay 装配所需内容全部就绪 |
| **R5** | AI 生成产物线（声纹 / 人设 / Memory，PROGRESS 第六~七周） | —（虚拟视频卡 2026-08-23 出列进需求池，§4.4；R5 就绪后按三级闸门重新挣座位） | — |
| **R6** | 多语言字幕卡点亮（PROGRESS 第二周）：`multilingual-subs` 注册项 + caption 翻译接线 + 预览烘焙（`scripts/bake_subs_contrast.py` harvest 模式）。08-14 二次修订：三档画幅纵贯 + 双语对照（`translation_track`）+ 标题随译 + 默认字号 68 + 承诺句放开到"视频" + 示例提示词教学位（variants desc 退役）。08-14 三次修订：卡不含剪辑（流程图摘掉剪辑规划步、提示词只点名多语言）+ 字幕尺寸按画面推导（帧高等比 + 双语两行打折）+ 卡面横方幅留黑保原比例 + 四案例对照包（EN 原声 / 中英双语 / FR 单行 / ES 配音，dub_clip 入流程图）。08-15 ADR-043 收编：预设 = 技能链（`tasks=[translate zh bilingual, translate fr, dub es]`，全 fork）——簿级字段（caption_languages / dub_languages / aspect / caption_bilingual）退役为任务参数，编译期经 materialize_source 注入兑现「整条视频」承诺 | 多语言字幕卡 | 用户素材走字幕卡 → 单 run 出整条视频的多语言字幕版；横/方/竖画幅按点名生效；双语对照出双行字幕 |

每期配套：对应素材策展 + 该期 `docs/tasks/` 简报（引用本文档章节号）+ PROGRESS 状态更新。

> **点亮 ≠ 通路**：上卡验收只证明能力真实；**完全通路** = Remix → 对话定计划 → 生成 → 结果页知道下一步 → 再生产/精修，由 PROGRESS 第二周闭环链统一承接——五卡共享一条闭环，不为单卡各建。

## 9. 新开会话导读（用本文档创建 tasks）

1. **先读**：`CLAUDE.md`（UI/工程约定）→ `docs/README.md`（治理）→ 本文档目标期章节 → 该期引用的上游文档（§11 表）。
2. **每期一份 `docs/tasks/` 简报**，模板对齐既有简报（Context / 已核实事实 / 设计论证 / 改动点 / 命名审计 / 分期验收 / Prohibited Behaviors），依据行引用本文档章节号（如 "RECIPES §3.2"）；上游文档清单见 §11。
3. **开工前重核 §0 事实**（代码可能已漂移），事实以读码为准。
4. **运维坑**（已踩过）：改 pipeline 代码必须重启常驻 worker；本机服务调用用 `127.0.0.1` 不用 `localhost`；验证用的手工 run 会被常驻 worker 抢跑，验后清数据。
5. **命名登记清单**（随实施进 NAMING.md 词汇表）：`recipe`（配方卡）、caption preset catalog 及原语词 `layout`/`entrance`/`word-highlight`、`stacking`、`stock voice`（系统音色）、`voice_gen`（synth 简报已登记）、`align_stills`（阅读节奏时间轴）、`reframe_clip`（评审后）、`MENTION_REGISTRY`（提及注册表）/`RECIPE_REGISTRY`（配方注册表）/`input_slots`（输入槽位）、`multilingual-subs`（多语言字幕卡）、`highlight-clips`（高光切片卡，2026-08-15 自 talk-clips 更名——名字说你得到什么，"演讲"窄化输入）、`materialize_source`（整条源材料化内部节点，ADR-043）/ `derived`（派生预览）、`aspect`（画幅，select_clips 任务参数，9:16/1:1/16:9 三档；2026-08-27 新增消费面：`ExampleOutput.aspect` / `OutputResponse.aspect` = 声明式画幅单源派生——render_spec.aspect → payload["aspect"]，"original" 归 None，前端禁自探）、`doc_format`（示例文档形态：post / carousel，随 `ExampleOutput.kind="document"` 第四值落码——文档类示例不再是"无视频的 video"）、`bilingual`（双语对照，translate_clip 任务参数）/`translation_track`（对照轨）、`fork`（派生新版本 vs 就地改写标记）、`promptHint`（示例提示词引导句，按卡 i18n 键）、`voice-dub`（原声AI配音卡）/ `social-post`（社媒帖卡）/ `quote-cards`（金句卡）/ `carousel`（轮播图卡）/ `cover`（封面工艺示意图组件，`components/recipes/covers/` 按 recipe id 注册）、v3 词（2026-08-27）：**招牌菜**（画廊组织原则词）/ **产物形态**（卡轴）/ **转化类 · 合成类**（两类卡）/ `any_of`（input_slots 任选一语义，过 NAMING §7 后落码）；退役词：`layout_mode`（金句卡 stacked 本体化后清尸）。

## 10. Prohibited Behaviors

1. **禁**未兑现能力的卡可点（点亮纪律修订后：reserved 卡渲染但 Remix 必须置灰/替换为 Soon——承诺永远先于能力）。
2. **禁**配方承诺的形状来自模板文案之外的隐藏通道（2026-08-11 修订）：发射载荷 = 预填模板原文，任务书 = book path 从消息文案推断 + 三方合并，与 composer 同一份保证。
3. **禁**新表——卡片数据硬编码前端，能力扩展全住 JSON 载荷层。
4. **禁**字幕样式绕过 catalog 加一次性分支；新原语值必须过 libass 映射检查。
5. **禁** composer 加 Audio 块 / 绕过人设另建声音存储（裁决③）。
6. **禁**无声纹阻塞出片（裁决④）；禁 ReAct/多步推理（CHAT_ARCH 铁律延伸）；禁绕过 `orchestrator.create_run`。
7. **禁**卡片预览走登录态 asset 端点（匿名受众必须公开可读）。
8. **禁**分镜跳过 ADR 直接动工；`reframe_clip` 未过 NAMING §7 不进 registry。
9. **禁**服务端播种与前端构造任务书预设（裁决⑤，2026-08-11 修订）：配方发射的全部行为载荷 = 预填模板原文；服务端永不见配方身份，composer/overlay 永不构建 prior。
10. **禁**配方身份编码进 transport 字段或句中 chip——发射载荷只有 prompt 文本（MENTIONS §3）；**禁**全屏配方模态框与 DAG 画布外显。
11. **禁** mention 类型一次性分支——新 @ 类型 = 双端注册表各一条注册项，立案先过 MENTIONS §3 判定三问。
12. **禁** promptHint 引导句做成选择器控件（延伸既有预设控件禁令）：变体教学唯一形态 = 提示词块下的按卡引导句；若未来做可点形态，唯一合法交互 = 点击插入预填 textarea，且需先有 evidence 再立项（§7.2）。
13. **禁**卡面承诺能力族（v3，ADR-048 第 4 条）——promise 写这道菜不写包络线；一个能力族只摆最霸道的一种形态上卡，其余形态归 chat；**禁**画廊按输入类型或渠道分行（遍历陈列永久否决——覆盖归选题库 ADR-042）。
14. **禁**无翻案条件变更阵容（v3，ADR-048 第 8 条）——座位进/出/合并/拆分必附翻案条件 + 认路级证据（复述测试 / 真实用户行为），不当周翻案。

## 11. 与其他文档的关系（引导章节）

| 文档 | 关系 / 需要的更新 |
|---|---|
| `STRATEGY.md` §5 | 配方库定位来源；本文档是其实施架构，论证不复述 |
| `PROGRESS.md` | 第 1–3 周排期含配方卡（第二周字幕卡点亮 R6 + 图文视频卡 slides 槽；分镜双子卡 authoring 延至第八周批次，§4.3） |
| `tasks/synthetic-talk-video.md` | R2 修订点：voice_gen 先行、`synth_visual` 降可选增强、stock 兜底语义、人设块扩展 |
| `tasks/done/intent-ask-primitive.md` | 声音换声复用提问机器的选项问形态（零新机制） |
| `CHAT_ARCHITECTURE.md` §4 | `reframe_clip` 准入评审；`set_caption_style` 枚举随 catalog 扩展 |
| `VIDEO_EDITOR.md` | caption catalog 遵守 preset enum + CSS∩libass 纪律；分镜两步走契约见 `AGENT_ARCHITECTURE.md` §4（understand/plan 两步走） |
| `AGENT_ARCHITECTURE.md` | `voice_gen`/`speaker_map` 节点的内部分析产物 + asset-hash 复用同款哲学 |
| `NAMING.md` | §9.5 清单随实施进词汇表 |
| `docs/README.md` | 本文档已登记索引 |
