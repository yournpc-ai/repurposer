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

## 3. 一次成稿与词级时间轴（默认直出，稳定高效）

- **默认首选 `create_video` 一次性编排成稿**：先通篇构思好一篇起承转合完整、无报菜名、无翻译腔的口播文稿，再按完整意群自然分到 8–10 个 `motion_blocks` 的 `narration` 中（每幕承载 1–2 句舒展完整的话，幕间自然承接，**绝不为了塞进一幕硬砍主谓宾**），直接传入 `voice_id`、`music_id` 和按情绪弧线微调的 `voice_speed` / `voice_emotion` 一次调用 `create_video` 成稿。服务端自动通过 MiniMax `speech-2.8-hd` 实时获取毫秒级词轨、精准对齐全片动效和字幕，速度最快、稳定性最高。
- **字数预算与自然时长弹性**：按总时长提前控制整篇文稿体量（30 秒约 95–125 中文字 / 45–60 英文词；45 秒约 140–175 中文字 / 65–82 英文词；60 秒约 190–235 中文字 / 95–115 英文词），让句子舒展有呼吸感。首稿实测时长落在目标时长 ±35% 内即视为自然成立；**v1 成稿保存后，严禁为压缩几秒时长去 `remove_clip` / `move_clip` / `trim_clip` 或重新调用 `generate_voice` 拆删重拼已录好的旁白幕**，略长时保留完整优雅口播直接铺音效、预览并导出交付，如实说明实际时长即可。
- **开场即立意，不要让观众在前 3 秒发懵**：商业宣传片的前 2 秒必须让观众一眼看懂主题或视觉抓手——可以安排一个 0.8–1.8 秒的干脆视觉/字效起势拍（无旁白，配音乐与轻音效，用 `kinetic_beat` 的 `impact_cut` / `inline_badge_split` 或 `browser_url_load` 直接亮出完整主张或产品画面），也可以让首幕标题干脆完整地一次落位，不要让大字逐词慢吞吞挤牙膏导致观众听着旁白却看不清画面在讲什么。
- **静音视觉拍与可选连续轨**：30–45 秒宣传片在起势或高潮转折处穿插 1–2 个 `0.8–1.8` 秒无旁白视觉节奏拍（`narration` 留空，靠字效/快闪与配乐接拍）。仅当用户明确要求「半句话不断气直接跨幕切镜」时，才可选用 `generate_voice` 录整篇并传 `create_video(voiceover_snapshot_id=...)`（切点只填单侧 `start_cue_phrase` 即可，且一旦录音在目标时长 ±30% 内严禁重录）。
- **句内停顿与呼吸感**：在核心反差、关键数字或结论揭晓前插入 `<#0.3#>` 或 `<#0.4#>` 停顿标签，必要时在转折气口克制加入 Speech 2.8 原生呼吸/微语气标签如 `(breath)`、`(emm)`、`(chuckle)`（系统会在派生字幕与词轨中自动剥离所有标签，绝不印上屏幕）。
- **按情绪弧线微调语速与语气**：开场钩子与痛点转折 `voice_speed: 1.02–1.06`；真实界面演示与数据证据 `voice_speed: 0.96–1.02`、`voice_emotion: "calm"`（沉稳可信，不念经）；核心突破可克制用 `"fluent"` 或 `"happy"`；结尾落版 `voice_speed: 0.94–0.98`、`voice_emotion: "calm"`。

## 4. 词级画面丰富（意群对位，画面服务文稿）

- **声画意群对位法**：画面是文稿的视觉放大器——给 `product_showcase.callout_steps[]`、`product_showcase.cursor`、`metric_grid.items[]`、`flow_diagram.nodes[]`、`step_timeline.steps[]`、`bento_features.cards[]`、`split_compare` 条目、`data_chart.points[]` 或 `statement_hook` 声明 **`cue_phrase`**（填写本幕自然口播句子里对应的词或短语，如 `"1870 万英镑"`、`"原始证据"`、`"VEST 理论"`、`"专家把关"`），服务端按真实语音时间戳自动解算精确秒数，让框选、点击和卡片刚好踩在自然说到该意群的瞬间。
- **画面精简，数字精准**：屏幕上出现的卡片与数字必须与口播一致（画面写 `£18.7m`，中文口播自然念出“一千八百七十万英镑”或“1870 万英镑”），口播里没展开讲的细节就从屏幕上裁掉；即便卡片标题是英文或精炼短词，`cue_phrase` 绑定口播里的自然中文原词即可，**严禁为了让卡片命中而把通顺人话改成名词罗列**。
- 点击用 `cue_phrase`，地址栏打字与加载分别用 `type_cue_phrase`、`load_cue_phrase`。换词文案与口播用词不同时，按 `words` 顺序提供 `word_cues`。同页多个细节用 `callout_steps[].zoom_scale` 连续推拉。
- 幕间转场（`whip_pan` / `zoom_through` / `wipe_reveal` / `iris_focus`）落在意群切换或停顿气口；0.7–1.5 秒无旁白快切间用干脆硬切。
- 收到 `create_video.sync_warnings`（如 `unmatched_cue`、`numeric_parity`）后，预览前用 `update_motion_block` 消除真实错配即可，无需为追求机械“逐字对表”而牺牲画面松弛感或口播流畅度。核对修订后的 `resolved_visual_cues[].at_seconds`，从中挑 3–5 处核心弹卡或点击，用 `generate_sfx` 的 `align_peak_at_seconds` 对齐 `select_tick` 或 `soft_pop`。

## 5. 多样化选曲、自主混音与电影感镜头语言

- 调用 `search_music({})` 查看全库曲目的 BPM、曲风、情绪与实测 **LUFS 响度**，**根据本片叙事方向与品牌气质挑选最匹配的曲目**（如机构/理性叙事选沉稳极简鼓组或电子脉冲，动感产品演示选 Funk / Electro / Tech House，轻快创意品牌选 Upbeat Indie），切勿机械默认只选第一首。**根据曲目的实测 LUFS 自主在 `create_video(bgm_gain_db=...)` 中设定混音电平**（系统默认 0 dB 不再替你暗中压低：旁白段通常结合曲目 LUFS 适当衰减使人声清晰通透，纯画面节奏段可更高能量，随后用 `preview_range` 返回的 `audio_windows` 校验实际电平）。
- **像真实发布大片一样变化镜头语法，避免反复同款框选**：不同产品展示幕应按意图选用最恰当的表现形式——首次亮出官网用 `browser_url_load`（打字加载）、单点交互特写用 `zoom_follows_click`（纯光标推镜无重边框）、图文并列或双端展示用 `device_mockup`（`split_focus` / `dual` / `hero_bleed`）、多屏纵深巡航用 `ui_montage`（`cascade_3d` / `fan_slide`）；使用 `product_showcase` 时，纯净的 `dolly_zoom` / `tilt_left` / `scroll_reveal` 运镜往往比满屏框选更高级，只在确有必要从密集界面中抠出局部信息时再点缀 `callout_steps`。同时与 `kinetic_beat`（5 种字效模式）、`split_compare`、`metric_grid`、`flow_diagram`、`data_chart`、`closing_cta` 交替混搭，并在高潮处用 1–2 幕明暗 `theme` 反转制造记忆点。
