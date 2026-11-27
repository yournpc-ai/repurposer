---
name: brand-promo
description: Narrated commercial product promo and brand launch films using real website captures, human-cadence voiceover with pauses and emotion, word-anchored motion blocks, and curated BGM/SFX.
license: Proprietary
compatibility: Native motion blocks, pinned website screenshots, MiniMax speech-2.8-hd voiceover, curated music and sound-engine v3.
metadata:
  version: "1.0.0"
  author: repurposer
  tags: [brand-promo, product-promo, voiceover, storytelling, word-sync]
---

有旁白的商业宣传片，**先有一篇自身通顺、优雅、有章法的好文章，再用画面与词级动效去丰富它**。先读官网真实卖点与实测 CSS 品牌视觉（`css_facts` / `brand_profile`），再按产品气质与用户所选方向构思完整文稿与叙事结构，绝不为了迁就画面格子把口播写碎，也绝不机械套用同一套固定顺序。

## 1. 品牌真实色彩与视觉基因优先

- **以官网实测 CSS 决定底色与强调色**：读取 `prepare_video_materials` 与 `analyze_brand` 返回的真实 `css_facts` / `css_style_suggestion`（含实测 `canvas_bg`、`accent_color`、`theme_polarity` 与字体信息），在 `create_video` 中直接透传 `canvas_bg` 和 `accent_color` 让成片与官网视觉血脉一致：
  - 官网为**浅色底**（`theme_polarity == "light"`）：优先选 `swiss_paper` 或 `vox_editorial`，并传入官网真实 `canvas_bg` 与 `accent_color`（不要把浅色官网默认拍成黑底 `#0A0F16`），仅在高潮或反差转折处局部穿插 1–2 幕深色 `theme: "dark"` 冲击拍。
  - 官网为**深色底**（`theme_polarity == "dark"`）：优先选 `institutional_dark` 或 `kinetic_anime`，并传入官网真实 `canvas_bg` 与 `accent_color`，局部穿插 1–2 幕浅色反差拍制造记忆点。

## 2. 先成文，后分镜：口播稿本身必须是一篇好文章

有旁白的影片，**文稿是主干，画面是注解与放大器**。动笔写画面之前，必须先把整篇口播写成一篇有起承转合的完整短文：**提出真实困境或主张 → 点明产品如何破局 → 用具体案例与核心机制讲透为什么可信 → 治理/信任收束与自然落版**。

- **脱图可读铁律**：把全片口播单独抽出来朗读，不看任何画面也必须逻辑连贯、句意完整、听感优雅。每一句都要有完整的主谓宾与清晰语义，句子之间用自然的口语衔接和因果递进（如“但真正难的是…”“它是怎么做到的？”“更关键的是…”），短句立势、长句说理，绝不写成彼此割裂的 PPT 备注。
- **严禁电报体、报菜名与生硬翻译腔（硬禁令）**：
  - 严禁“名词，名词，名词”的无谓语清单式念法；严禁把数字孤零零丢在没有主语和动词的短语里；严禁把英文界面词生硬直译成非母语词（如把 `Approval gates` 直译成“闸口”）。
  - 反例（严禁）：`一千八百七十万英镑，证据覆盖百分之九十四。证据，推理，交付，每一层都清晰。VEST 理论，八大行业库，二十七套算法。定义，取证，复核，发布，四步受控。闸口保住专家判断。`
  - 正例（范本）：`在这份真实算例里，系统给出了 1870 万英镑的企业估值，背后 94% 的判断都有源可查。它是怎么做到的？系统把原始证据、逻辑推理和最终交付拆成清晰的三层，底层由原创的 VEST 理论、8 大行业数据库和 27 套算法共同支撑；从定义边界到取证、复核、发布，每个关键节点都由专家把关、全程留痕。`
- **文稿定调，画面做减法**：先写好自然优雅的人话，再为文稿选配画面；**绝不为了凑够 3–4 张卡片或截图框去往口播里硬塞标签**。屏上文字提炼为 2–5 词视觉锚点，与口播形成“完整优雅人话 + 精炼视觉锚点”的互补双声部，绝不全文复读，也绝不看图念标签。
- **声画严格对应与创意差异化**：每一幕视觉必须直接丰富当下口播正在讲的意群——讲抽象困境或主张时用排版冲击幕（`statement_hook` / `kinetic_beat` / `split_compare`），绝不把无关整屏截图硬塞在抽象旁白底下；当口播切入产品动作、真实案例数字、技术机制或流程时，再顺势切入对应的 `product_showcase` / `zoom_follows_click` / `metric_grid` / `step_timeline` / `flow_diagram` / `bento_features` / `ui_montage` / `device_mockup`。

## 3. 先录整篇连续口播，再贴着文稿切画面

- **默认首选连续口播（先文后画的工程保证）**：同一人声讲完的商业宣传片，备齐官网素材与声纹后，先通读自检整篇口播稿（确认无报菜名、无翻译腔、主谓完整、段落衔接自然），再调用 `generate_voice(text=完整口播稿, speed=..., emotion=...)` 一次录成连贯人声。拿到回执的 `snapshot_id` 与实测 `word_cues` 后，再调用 `create_video(voiceover_snapshot_id=...)`，按意群把下一幕的 `start_cue_phrase` 设为入点词（或把上一幕的 `end_cue_phrase` 设为出点词，同一切点给一侧即可）。这样**一句完整流畅的话可以自然跨 2–3 个画面镜头**，彻底消除逐幕硬切带来的断句生硬感。双语字幕的 `caption_translations` 按整段口播顺序填写，省略逐幕 `narration`。
- **字数预算与自然时长弹性**：按总时长控制整篇文稿体量（30 秒约 100–140 中文字 / 55–75 英文词；45 秒约 155–200 中文字 / 85–110 英文词；60 秒约 210–270 中文字 / 115–150 英文词），让句子舒展、有呼吸感。首稿落位在目标时长 ±25% 内即视为自然成立，绝不为硬凑整秒删毁句子或破坏口播呼吸。
- **静音视觉拍与逐幕适用场景**：连续录音固定从 0.15 秒起播；30–45 秒宣传片可在起势或高潮转折处保留一段 2–3.5 秒无旁白视觉节奏段（连续录音中可用 `<#2.0#>` 等停顿预留纯音乐画面，并用前一词尾与后一词首框定）。仅当不同幕需要切换不同声线或强烈情绪/语速反差时，才退回逐幕 `narration`——且即便逐幕填写，把各幕拼起来也必须是一篇首尾呼应、衔接流畅的完整文章。
- **句内停顿与呼吸感**：在核心反差、关键数字或结论揭晓前插入 `<#0.3#>` 或 `<#0.4#>` 停顿标签，必要时在转折气口克制加入 Speech 2.8 原生呼吸/微语气标签如 `(breath)`、`(emm)`、`(chuckle)`（系统会在派生字幕与词轨中自动剥离所有标签，绝不印上屏幕）。
- **按整体气质微调语速与语气**：科技/机构理性叙事可用 `speed: 0.98–1.03`、`emotion: "calm"`（沉稳可信，不念经）；亮眼新品发布可用 `emotion: "fluent"` 或 `"happy"`（克制提亮，不夸张）；逐幕录音时可按开场（1.03–1.06）→ 实演证据（0.96–1.02）→ 落版（0.94–0.98）微调弧线。

## 4. 词级画面丰富（意群对位，画面服务文稿）

- **声画意群对位法**：画面是文稿的视觉放大器——给 `product_showcase.callout_steps[]`、`product_showcase.cursor`、`metric_grid.items[]`、`flow_diagram.nodes[]`、`step_timeline.steps[]`、`bento_features.cards[]`、`split_compare` 条目、`data_chart.points[]` 或 `statement_hook` 声明 **`cue_phrase`**（填写本幕自然口播句子里对应的词或短语，如 `"1870 万英镑"`、`"原始证据"`、`"VEST 理论"`、`"专家把关"`），服务端按真实语音时间戳自动解算精确秒数，让框选、点击和卡片刚好踩在自然说到该意群的瞬间。
- **画面精简，数字精准**：屏幕上出现的卡片与数字必须与口播一致（画面写 `£18.7m`，中文口播自然念出“一千八百七十万英镑”或“1870 万英镑”），口播里没展开讲的细节就从屏幕上裁掉；即便卡片标题是英文或精炼短词，`cue_phrase` 绑定口播里的自然中文原词即可，**严禁为了让卡片命中而把通顺人话改成名词罗列**。
- 点击用 `cue_phrase`，地址栏打字与加载分别用 `type_cue_phrase`、`load_cue_phrase`。换词文案与口播用词不同时，按 `words` 顺序提供 `word_cues`。同页多个细节用 `callout_steps[].zoom_scale` 连续推拉。
- 幕间转场（`whip_pan` / `zoom_through` / `wipe_reveal` / `iris_focus`）落在意群切换或停顿气口；0.7–1.5 秒无旁白快切间用干脆硬切。
- 收到 `create_video.sync_warnings` 后，预览前用 `update_motion_block` 逐项消除问题——遇到 `orphan_item` 时**优先删减多余卡片或把 `cue_phrase` 改绑到口播里已有的自然词，绝不为了消告警把流畅口播改回电报体**。核对修订后的 `resolved_visual_cues[].at_seconds`，从中挑 3–5 处核心弹卡或点击，用 `generate_sfx` 的 `align_peak_at_seconds` 对齐 `select_tick` 或 `soft_pop`。

## 5. 多样化选曲与视觉混搭

- 调用 `search_music({})` 查看全库曲目的 BPM、曲风与情绪，**根据本片叙事方向与品牌气质挑选最匹配的曲目**（如机构/理性叙事选沉稳极简鼓组或电子脉冲，动感产品演示选 Funk / Electro / Tech House，轻快创意品牌选 Upbeat Indie），切勿机械默认只选第一首。
- 混搭真实界面幕（`browser_url_load`、`product_showcase`、`zoom_follows_click`、`device_mockup`、`ui_montage`）与排版/数据幕（`kinetic_beat`、`statement_hook`、`metric_grid`、`flow_diagram`、`data_chart`、`closing_cta`），并在高潮处用 1–2 幕明暗 `theme` 反转制造记忆点。
