# quote-cards 配方 v3——叠卡本体 + 帧卡 Output 化 + 宽槽三路径

> Status: ✅ 已落地（2026-08-25 初版拍板并落地 Phase 1–4 + chain variant；2026-08-27 v3 修订拍板：叠卡 = 卡本体，legacy fan-out 与 `layout_mode` 退役，帧卡 Output 化，宽槽三路径；画廊 v3 母决策 = ADR-048；2026-08-28 P1 欠账清零 + P2 帧卡 Output 化 + **P3 烘焙与清场全绿收官**——形态 A/B × 三路径示例矩阵烘焙入 demo/（v9 形态 C 对象退役删除）、示例 tab hover-only veil pill（D17）、`_phase*` 探针清场 14 件、verify bounce 家族堆叠根修、accept 闸全绿）
> 依据：ADR-016（clip-spec 契约）/ ADR-040（配方 = 提示词）/ ADR-044（轨道模型）/ ADR-048 v3（三轴模型 + 两类卡输入规则）/ RECIPES §4.6
> 前置读：`docs/RENDERING.md`、`docs/RECIPES.md` §4/§4.6/§7、`docs/DECISIONS.md` ADR-048

## 0. Context

**起源**（2026-08-25 用户判词）：小红书真实金句卡（查理·芒格 / 学术访谈截图）= 9:16 竖屏、真人是底、字幕叠加——当时实现是 MiniMax `image-01` 自由发挥的 1:1 静态 PNG（CJK 必糊、无源素材绑定），方向性错误。用户红线：这是**剪辑和字幕活**，走 ASR + Remotion，必须绑定源素材。

**v3 动因**（2026-08-27）：叠卡体裁（cascade 金句卡）在 TikTok/小红书是已验证体裁，但 v2 画廊按输入遍历组织，新体裁找不到座位；chat 实际产出（legacy 逐条 fan-out）与卡面示例（叠卡）不一致，违反"配方 = 能力承诺"裁决①。v3 拍板：**叠卡就是金句卡本体**——同族只摆最霸道形态，单句图归 chat 能力（ADR-048 第 3 条）。

## 1. 已落地现状（2026-08-25/26，含缺陷清单）

**已 land**：

- **Phase 1 caption_mode 反问**：write_quotes 链未点名字幕模式时 dock 三选一（bilingual / source_only / target_only），bilingual 关键词直通；回答落 `run.context.caption_mode`（`chat/service.py`）。
- **Phase 2 writer 收敛**：`quotes.j2` 改为核心立意链条策展——按 `quotable_line_id` 挑 3–7 句（setup→payoff），LLM 不写时间戳；runner `_enrich_quote_cards` snap `source_start/end/frame_at` + dedupe + 截 >7；bilingual 时调 `translator` 填 `quote_alt`（`tools/quotes/node.py`）。
- **Phase 3 渲染**：`build_quote_card_spec`（逐句视频卡，word-boundary snap + 0.12s/1.8s pad，caption_mode 四分支）+ `build_stacked_quote_card_spec`（叠卡合成 PNG 的 stills 包装）（`pipeline/clip_spec.py`）；`_materialize_quote_card_outputs` 落 clip Output + 扇出 render（`pipeline/derivative_dispatch.py`）；MiniMax image-01 PNG 路径已杀（`images_per_run=0`）。
- **Phase 4 recipe & i18n**：`input_slots=[video 必传]`、aspect 9:16、双模板 i18n、`accept_prompt_surface` 双模板闸门、harness S1 三回合旅程 + S48。
- **chain variant**：PIL 叠卡合成器（v2 y-stack + v3 宽度金字塔 + 可选 speaker frame），示例已烘焙入 demo/ 桶。
- 附带：FAILED run → project 打回 DRAFT；render.ts image_shots 走 loopback 代理。

**缺陷清单（v3 一次清账）**：

| # | 缺陷 | 位置 | 修法 |
|---|---|---|---|
| D1 | **卡面示例 ≠ chat 实际产出**：stacked 仅 bake 脚本手工 seed `layout_mode="stacked"` 可达；chat 路径 None → legacy 逐条 fan-out（3–7 条论证碎片单卡） | `derivative_dispatch.py` chain 分支条件 | None 路由进 stacked（§2.1），legacy 分支退役 |
| D2 | `layout_mode` 字段是 LLM 可见的无 prompt 通道（schema 描述随机发芽） | `schemas.py:827` | 字段退役清尸（§2.1） |
| D3 | 用户 chain 合成图写进 `demo/outputs/`（reset_db 营销保护区） | `derivative_dispatch.py:203` | 改项目作用域 key（§2.4） |
| D4 | alt 语言盲取 `run.target_language`：源语言 == target 时 bilingual 退化为恒等翻译 | `tools/quotes/node.py` `_translate_quote_alts` | alt 取"源语言的对面"（§2.3） |
| D5 | `quote`（writer 按 target_language 写）与 `quote_alt`（translator 译）双译本并存，可能同屏两译 | writer/materializer | 职责收窄：字幕副行统一取 `quote_alt`，`quote` 仅作 hook/元数据（§2.3） |
| D6 | 卡面 promise "Pull **one** sharp line" vs 实际 3–7 句 chain——文案与实现漂移 | en.ts/zh.ts | 改叠卡承诺（§2.5） |
| D7 | 死代码/硬编码：死 import（`composite_stacked_quote_card`/`find_context_spans`）、死参（`output`、`brand_music_id`）、chain `duration=8` vs spec `duration_s=6.0`、`music_mood="calm"` 硬编码、`[caption_mode:]` 机器标记骑 `specific_instruction`、`_translate_quote_alts` 死 try/except、node.py docstring 声称"补短链"代码没有 | 多处 | 逐个清（随 §3 P1） |
| D8 | S13 断言变弱（`has_prose` 反问断言被删） | `chat_scenarios.py` | 补回媒体需路径的反问断言（§3 P1） |
| D9 | 已知非目标：write_quotes 重试路径 DB 事务卡顿（verify bounce 重试 session 不释放） | worker 重试路径 | 另起 ticket（本简报不修，登记 PROGRESS 需求池） |
| D10 | 14 个 `_phase*` 临时脚本未跟踪 | `apps/api/scripts/` | harness 覆盖已足者删除， durable 的（bake_*）保留（§3 P3） |
| D11 | **全解码内存炸弹**：`extract_video_frames` 把整段视频全部解码驻留内存再取帧（`quote_card_stack.py:225-236` `frames.append(f)` 全量驻留）——讲座级长视频必 OOM / httpx 300s 超时；demo 15s 短片没炸纯属侥幸 | `quote_card_stack.py` | 改流式：按 timecode 升序解码、到点即取、取完即停（或 PyAV seek 最近关键帧）（P1） |
| D12 | **生产环境 CJK 字体缺失**：`_load_font` 候选全是 macOS/Linux 桌面路径（`:58-62`），容器里 fallback DejaVuSans **无 CJK——中文必成豆腐块**；本机烘焙正常纯属 macOS 侥幸 | `quote_card_stack.py` | vendor CJK TTF（Noto Sans SC 或同级）进仓/镜像，`_load_font` 首选 vendor 路径（P1） |
| D13 | **中文永不换行**：`_wrap_text` 按空格 split（`:349-374`），CJK 无空格 → 整句一词 → 单行溢出画布 | `quote_card_stack.py` | CJK 占比超阈值时逐字 wrap；char budget 区分 CJK 1.0em / Latin 0.55em（P1） |
| D14 | 字号按 primary/secondary 角色定（`:465-481`）而非按文字脚本——中文源+英译时中文反而比英文小 | `quote_card_stack.py` | 按脚本定大小：CJK 行大（主）、Latin 行小（次）（P1，与 §2.6 双语同条规则一致） |
| D15 | **形态与参考体裁不符**（2026-08-27 用户供 TikTok 图文帖参考两张）：当前 = N 视频帧堆叠"帧墙"；参考 = 统一背景（顶部人像 / 全幅照片）+ 文字链条为主体；身份呈现 = 40px 左上小字 vs 参考竖排大字 rails；invalid `frame_at` → -1.0 → clamp 0.0 → 静默取 t=0 帧（大概率黑场/片头帧） | `quote_card_stack.py` chain 段 + `derivative_dispatch._build_stacked_quote_spec` | §2.6 形态对齐（P2） |
| D16 | v1 cascade 整段死代码（`find_context_spans` / `ContextSpan` / `composite_stacked_quote_card` + v1 布局常量，`:40-431`——chain variant 后无调用方，`derivative_dispatch` 的 import 也是死的）+ 调参残骸（`CHAIN_CARD_WIDTH_FACTOR` 死常量、v1→v6 调参注释史） | `quote_card_stack.py` | 整段删除（P1） |
| D17 | 底部 80px 留白是为 overlay 示例 pill 让路的 hack（`:805-811` 注释自证）——产物图为展示壳改设计，本末倒置 | `quote_card_stack.py:811` | 留白回 16px；overlay label pill 挪到图外/hover 才显（归产物展示统一简报 P2 联动，P3 核销） |

## 2. v3 目标形态

### 2.1 叠卡 = 金句卡本体

- `_materialize_quote_card_outputs`：`layout_mode == "stacked"` 条件删除——`len(quotes) >= 2` 即走叠卡合成；单句（chain length 1）走 `build_quote_card_spec` 单卡路径（不是 legacy fan-out，是 N=1 的同一道菜）。
- **legacy 逐条 fan-out 分支退役**：writer 产出是 setup→payoff 的链条，拆成单卡就是论证碎片（旧 prompt"独立成立"要求已随 chain 重写移除，无回退必要）。
- **`layout_mode` 字段退役**：`InferredIntent` / `TaskSpec` / `run.context` 三处清尸；schema 描述、accept 闸门、harness 同步。未来若有新版式，按 ADR-048 第 3 条"同族最霸道形态"原则重评，不 resurrect 字段。

### 2.2 帧卡 Output 化（chat 精修的寻址地基）

- 每条 chain entry 落一个 **image Output**（帧 + 字幕条小卡，独立可发）；合成叠卡落 1 个 image Output，`source_ref` 记 `{parents: [帧卡 Output ids], quotable_line_ids, core_idea}`；motion MP4（zoom_in 包装）作合成卡的子节点（`type="clip"`），不当主承诺。
- 结果画布：N 帧卡节点扇出 → 谱系边汇入 → 合成卡节点（FlowView 血缘边，复用 results-canvas 既有渲染）。
- **chat 逐条精修放下期**：本期只把 source_ref 寻址信息留足（quotable_line_id + frame_at + quote_alt 可重算）；下期形态 = "换第三句 / 第三张换一帧"经 chat op 重合成。

### 2.3 caption_mode 与 alt 语言修正

- **alt = 源语言的对面**：推导序 = 用户点名的目标语言（chat/prompt）→ 项目/UI locale（≠ 源语言时）→ `run.target_language`（≠ 源语言时）；三者皆 == 源语言 → bilingual 无意义，跳过反问直接 source_only。
- **双译本收窄**：字幕副行统一取 `quote_alt`（translator 产物）；writer 的 `quote` 字段收窄为 hook/元数据，不进字幕候选——同屏永不出现两个译本。

### 2.4 存储纪律

- 用户产物（帧卡 / 合成卡 / MP4）一律项目作用域 key；`demo/` 前缀只收配方卡 display 烘焙产物（reset_db 保护区，ADR-048 后果条）。

### 2.5 卡面与 i18n

- promise 改叠卡承诺（"挑出最亮的几句话，叠成一张可以直接发的金句卡"方向）；`inputTitle`/`inputHint` 按合成类口吻（"给什么都行——录像、文稿、照片"）；`promptHint` 保留语言对 + 字幕模式引导（chat-only，无控件）。
- `input_slots` 宽槽三路径：录像（帧 strip）/ 照片+文稿（照片底 strip）/ 纯文稿（纯文字 strip，学术椅型——`needs_speaker_frame=False` 与 `video_bytes=None` 降级路径已在跑）。**只列已验证路径**；照片底路径需补 compositor 底图分支（本简报 P2）。
- 卡序第 2 位（霸道序，ADR-048 第 7 条）。

## 2.6 产物形态对齐（2026-08-27 参考图实证，用户供 TikTok 图文帖两张）

两张参考：**#35 人像型**（查理·芒格）= 顶部 ~45–50% 人像 + 竖排身份 rails（左「查理·芒格 Charlie Thomas Munger」/ 右头衔与出处）+ 下方深色底上半透文字条级联（条高随文字、左右错位阶梯、**中英同条：中文大行 + 英文小行**）；**#34 全幅背景型**（学术访谈）= 全幅单张现场照 + 居中纯中文文字行直下（无卡体）。共同点：**统一背景 + 文字链为主体 + 静态图**（TikTok 图文帖，不是视频）。当前实现的"N 视频帧堆叠帧墙"（形态 C）不是这个体裁——而且 N 个相邻秒数的帧视觉上近乎重复，参考用的是**一张策展好照片**。

v3 形态取参考公约数；writer 的 `needs_speaker_frame` verdict 保留但**重映射**：

- **形态 A（人像型，`needs_speaker_frame=True`）**：顶部人像区（~50% 高，策展帧，见下）+ 底部深色渐变延伸 + N 条文字条（条高随文字 110–150px、半透黑底、左右错位 ±40px 阶梯）+ 身份 rails。P2 先做**横排大字版**（人像区内左下：姓名一行 + 头衔/出处一行，attribution 字段终于上屏）；竖排 CJK rails（逐字排或旋转绘制）单独评估，不阻塞 P2。
- **形态 B（全幅背景型，`needs_speaker_frame=False`）**：全幅单背景（策展帧 = chain 第一条的帧；用户传照片则首张照片）+ 整体压暗 ~30% + N 行文字居中直下（无卡体、等距）；单语或双语同条。
- **形态 C（帧墙，当前 v9 已烘焙示例）**：形态 A/B 落地后**退役**，P3 重烘焙替换——此后无独立代码路径（无有效帧时的兜底 = 形态 B 的暗底分支）。
- **策展帧**（治"中点帧表情差 + N 帧重复"两病）：speaker frame 不取 chain[0] 的 frame_at 中点帧——取第一条 quotable line 所在段的**最佳帧**（人脸框最大 + 清晰度高；YuNet 人脸检测已在仓，`tools/vision.py` 复用，零新引擎）；用户照片素材直接用照片。
- **帧卡 = 单句卡**（§2.2 帧卡 Output 化的形态定义）：一张策展帧/照片 + 一句文字条（双语则同条）——独立可发，且是合成卡的构成件：N 帧卡 Output 散射 → 谱系边 → 1 张合成卡 Output（用户蓝图，结果画布兑现）。
- **双语同条排版**：按文字脚本定大小——CJK 行大（主）、Latin 行小（次），同条内主行在上次行在下（D14）；char budget 分 CJK 1.0em / Latin 0.55em（D13）。
- **主产物 = 静态 PNG**（图文帖形态，与 §2.2 互证）；MP4（Ken Burns zoom_in）= motion 衍生品，画布上挂合成卡子节点，永不当主承诺。

## 3. 工程分期

| 期 | 内容 | 验收 |
|---|---|---|
| **P1 欠账清零**（1 天） | D1（None→stacked）/ D2（layout_mode 清尸）/ D3（key 前缀）/ D6（文案）/ D7（死代码）/ D8（S13 断言）/ **D11（流式取帧）/ D12（CJK 字体 vendor）/ D13（中文 wrap）/ D14（按脚本定字号）/ D16（v1 死代码整段删）** | 真管线 chat 路径发"做一张金句卡"→ 出叠卡且中文正常换行；S1/S13/S48 全绿；grep 无 layout_mode；1h 长视频取帧不 OOM |
| **P2 帧卡 Output 化 + 形态对齐**（2 天） | §2.2（帧卡 Output + 谱系）+ §2.3（alt 规则 + 双译本收窄）+ **§2.6 形态 A/B + 策展帧 + 身份 rails 横排版** + 宽槽三路径（`any_of` 过 NAMING §7）+ 照片底 strip | 形态 A/B 各出真管线样张（人像型 / 全幅背景型）；帧卡 → 合成卡谱系正确；英文源+中文 locale 出 EN/ZH 双语同条；纯文稿出文字叠卡 |
| **P3 烘焙与清场**（0.5 天） | 三路径 × 两形态示例重烘焙（形态 C 退役替换，内容寻址入 demo/）+ D17（底部 80px 让位 hack 移除——配展示统一简报 P2 的 label pill 挪位联动）+ `_phase*` 脚本清场 + accept 闸门同步 | overlay 示例 tab 展示形态 A/B 同款；accept 全绿 |

**chat 逐条精修（"换第三句"）下期**：依赖 P2 的 source_ref 寻址 + ops 词汇评审，单独立项。

## 4. 已绑红线（拍板即不再议）

1. **不引新工具**——叠卡走 clips 通道 + adapter，不开 `write_quote_card` 新 tool。
2. **不引新渲染技术栈**——只走 Remotion，不动 FFmpeg / 任何自造渲染器（PIL 叠卡合成 = 工序内部工序，不进 clip-spec 契约）。
3. **写手职能收敛为"挑金句"**——不写时间戳（runner snap）；字幕副行统一 translator 产物，writer `quote` 仅作 hook/元数据。
4. **chat 反问只对 quote-cards 触发**——其他 recipe 的语言走原 pipeline；caption_mode 永不进 overlay 控件（ADR-048 第 4 条）。
5. **失败重试 DB 事务卡顿**（D9）是另一 ticket，不在本简报范围。
6. **保留 quotes.j2 verbatim 守则**——改动只在结构，不破坏原文保真逻辑。
7. **叠卡 = 卡本体**（v3 新增）——不做"默认/可选"开关；单句图归 chat 能力，不上卡面。

## 5. Prohibited Behaviors

1. **禁**复活 legacy 逐条 fan-out / `layout_mode` 字段（v3 退役词）。
2. **禁**用户产物写 `demo/` 前缀（reset_db 保护区；display 烘焙除外）。
3. **禁**卡面/overlay 加字幕模式、语言、路径选择器控件——参数只在对话里问（一轮封顶、关键词直通、chat 恒胜）。
4. **禁**宽槽列出未验证路径（诚实纪律）；路径打通一条加一类，永不因此加座位。
5. **禁** `quote` / `quote_alt` 同屏双译——副行统一 `quote_alt`。
6. **禁** PIL 取帧全量解码驻留（流式 seek 唯一合法）；**禁**字体依赖系统路径（vendor TTF 唯一合法——生产容器无桌面字体）。
7. **禁**产物图为展示壳改设计（D17 类让位 hack）——壳让图，不是图让壳。

## 6. 实施导引（新会话零讨论施工版）

### 6.0 基线状态（动手前必知）

- **git 工作树有 ~2300 行未提交改动**（quote-cards Phase 1–4 + copy-writer 六闸门 lift + chain 叠卡合成器，commit `55783aa` 只含叠卡合成器一部分）。**这层未提交代码就是你的新基线**——不是垃圾、不要 revert、不要 stash；本简报的 P1 是在它之上做修正。先 `git status && git diff --stat` 通读。
- 关键既有实现（都在工作树里）：`apps/api/app/pipeline/derivative_dispatch.py` 的 `_build_stacked_quote_spec`（~:102）/ `_materialize_quote_card_outputs`（~:231）；`apps/api/app/pipeline/clip_spec.py` 的 `build_quote_card_spec`（~:372）/ `build_stacked_quote_card_spec`（~:551）；`apps/api/app/tools/quotes/node.py` 的 `_enrich_quote_cards`（~:48）/ `_translate_quote_alts`（~:125）/ `_generate`（~:157）；`apps/api/app/chat/service.py` 的 caption_mode 反问族（~:259-420 / :882-961 / :1463-1504 / :1685-1748）。
- 用户产物存储 key 惯例：`{user_id}/outputs/projects/{project_id}/{filename}`（`app/providers/storage.py:12` 注释 + `:109`），写入走 `save_output`（`storage.py:295`）、取 URL 走 `output_url`（`storage.py:170`）——`pipeline/images.py:63-69` 是现成调用样例。
- Output 类型：用户可见 = `clip|post|quotes|carousel|article`；内部类型由 `INTERNAL_OUTPUT_TYPES`（`models/schemas.py:1878`）过滤。帧卡若用新类型（如 `quote_frame`）必须登记该集合的用户可见侧，并在前端 `lib/types.ts` + `OutputChatCard` 派发同步（与产物展示统一简报的 MediaKind 对齐）。

### 6.1 P1 逐项施工单（D1–D8，估 0.5–1 天）

| # | 动作 | 落点与思路 |
|---|---|---|
| D1 | None → stacked | `derivative_dispatch.py` `_materialize_quote_card_outputs`：chain 分支条件 `if layout_mode == "stacked" and len(quotes) >= 2:` 改 `if len(quotes) >= 2:`；`len == 1` 走单卡（`build_quote_card_spec`，N=1 的同一道菜）；**else 的 legacy 逐条 fan-out 循环整支删除**（含其 Output/render 扇出辅助）。删后通读该函数确认无悬空引用 |
| D2 | `layout_mode` 清尸 | `models/schemas.py:826-836`（`InferredIntent.layout_mode` 字段+docstring）、`pipeline/orchestrator.py:144-147`（`TaskSpec.layout_mode`）、`chat/service.py:1025`（透传行）、`models/schemas.py:1523` 附近如有 GenerationContext 侧残留一并清；全仓 grep `layout_mode` → 0（bake 脚本 `bake_quote_stacked.py`/`bake_quote_chain.py` 里的 seed 行同步删） |
| D3 | 存储 key 改项目作用域 | `derivative_dispatch.py:203` `key = f"demo/outputs/quote-chain-{digest}.png"` → 走 `save_output` 惯例（`{user_id}/outputs/projects/{project_id}/quote-chain-{digest}.png`）；函数签名补 `user_id`/`project_id` 透传（调用点就在同文件 P3 接线处）；已误传进 demo/ 的历史对象手动删（TOS 控制台或脚本） |
| D6 | 卡面文案对齐 | `apps/web/src/lib/i18n/locales/en.ts` + `zh.ts` 的 `recipes.quote-cards.*`：promise 改叠卡承诺（en 参考方向 "The sharpest lines of your talk, stacked into one ready-to-post quote card." / zh "挑出最亮的几句话，叠成一张可以直接发的金句卡。"）；`inputTitle`/`inputHint` 改合成类口吻（"Talk recording, transcript, or photos — whatever you have."）；`promptTemplateWithMaterial` 保留双语点名；`accept_prompt_surface.py` 的 quote-cards `variants` 同步（它会逐字对账 i18n，先改脚本预期再跑） |
| D7 | 死代码/硬编码清理 | `derivative_dispatch.py`：删死 import（`composite_stacked_quote_card`、`find_context_spans`，~:41/:43）、删 `_materialize_quote_card_outputs` 未用的 `output` 参（~:236）与 `brand_music_id` 绑定（~:295）；chain ClipPayload `duration=8` 与 spec `duration_s=6.0` 统一为同一常量（~:357 vs :118）；`music_mood="calm"` 改从 brand 块/常量取；`tools/quotes/node.py`：`_translate_quote_alts` 外层死 try/except 删（`asyncio.gather(return_exceptions=True)` 不会抛）、`_enrich_quote_cards` docstring "补短链" 描述删；`chat/service.py`：`specific_instruction` 不再拼 `[caption_mode: …]` 机器标记——caption_mode 已经由 `TaskSpec.caption_mode` 结构化透传（确认下游 reader 都不读这个标记后删拼接点，~:900 附近 `_replay_stashed_caption_intent`） |
| D8 | S13 断言补回 | `scripts/chat_scenarios.py` S13：恢复"媒体需 + 无素材 → 有反问散文"断言（被删的原形：`check(has_prose(turn1["assistant_message"]), "an ask-for-material reply lands", ...)`，git diff 可查），注意现行语义 = S13 只管媒体需路径（copy-writer 路径是 S48），断言要保持"caption_mode dock 可出现但 task_book/run/pending_intent 不落"的兼容 |
| D11 | 流式取帧 | `quote_card_stack.py:209-256`：`extract_video_frames` 删"全解码驻留"段（`:225-230` `frames.append(f)` 循环）——改 timecodes 升序遍历、单遍解码到点即取、取完最后一张即 `break`；或 `container.seek(int(t / stream.time_base))` 到最近关键帧再解码 ≤2s。验收 = 1h 视频抓 7 帧内存平稳 |
| D12 | CJK 字体 vendor | 下载 Noto Sans SC（或同级 SIL OFL 字体）Regular+Bold 进 `apps/api/assets/fonts/`（新目录，Dockerfile/部署同步 COPY）；`_load_font`（`:88-97`）候选列表**最前**插 vendor 路径（`Path(__file__).parents[2] / "assets" / "fonts"`）；系统路径保留作本机 fallback |
| D13 | 中文 wrap | `_wrap_text`（`:349-374`）：先判 CJK 占比（`sum('一' <= c <= '鿿' for c in text) / len(text) > 0.3`）→ CJK 逐字切 token（`list(text)` 而非 `text.split()`）；char budget 系数分脚本：CJK 1.0em / Latin 0.55em（调用点 `:787` / `:793` 按行内容分别传） |
| D14 | 按脚本定字号 | `_draw_caption_strip`：不再用 font_primary/font_secondary 固定角色——按每行内容的 CJK 占比选字体（CJK 行用大字、Latin 行用小字）；`CHAIN_PRIMARY_*` / `CHAIN_SECONDARY_*` 常量改名 `CHAIN_CJK_*` / `CHAIN_LATIN_*`（注释同步，调参史删除） |
| D16 | v1 死代码整段删 | `quote_card_stack.py`：`find_context_spans` / `ContextSpan` / `_split_sentences` / `composite_stacked_quote_card` / `_draw_caption_card` / v1 布局常量（`FRAME_*` / `CAPTION_H` / `_SENTENCE_BREAK_S` / `_FONT_REGULAR_CANDIDATES` 若仅 v1 用）整段删除；`derivative_dispatch.py` 的死 import（`composite_stacked_quote_card`、`find_context_spans`）同步删；`CHAIN_CARD_WIDTH_FACTOR` 死常量删。删后 `grep -rn "find_context_spans\|composite_stacked_quote_card" apps/ → 0` |

### 6.2 P2 要点锚（帧卡 Output 化 + 形态对齐，估 2 天）

- 帧卡 Output：每条 chain entry 合成"帧+字幕条小卡"PNG（形态 A/B 的单条渲染复用 §2.6 排版规则）→ `save_output` 项目作用域 → `Output(type="quote_frame", provenance="real")`，`files.image` 填 URL；合成卡 Output 的 `source_ref = {"parents": [帧卡 ids], "quotable_line_ids": [...], "core_idea": ...}`。
- 谱系边：结果画布 FlowView 读 `source_ref.parents` 画 N→1 汇入边（查 `runFlow.ts` 现有 source_ref 消费方式，缺则补映射）。
- alt 语言推导（D4）：`_translate_quote_alts` 的 `target_language` 改推导序——chat 点名 > 项目/UI locale（≠源语言）> run.target_language（≠源语言）；全等于源语言 → 跳过反问走 source_only（落点在 `chat/service.py` `_needs_caption_mode_question`）。
- 双译本收窄（D5）：字幕副行统一 `quote_alt`；`build_quote_card_spec` 的 bilingual 分支确认只读 `quote_source`/`quote_alt`；writer `quote` 字段只进 `hook`/元数据。
- 宽槽三路径：`input_slots` 加"任选一"语义（新字段名先过 NAMING §7 再落码）；compositor 加照片底 strip 分支（`video_bytes=None` 但有 images 时用照片当 strip 底图，纯文稿走现有文字 strip）；`slotCoversFile`（`apps/web/src/lib/recipes.ts`）与 overlay 闸门（`RecipeInspectOverlay.tsx` `handleLaunch` 的 uncovered 判定）同步改"任一覆盖即过"。
- 形态 A/B（D15）：`composite_chain_quote_card` 按 `needs_speaker_frame` 分两路——A = 人像区（`_crop_to_card` 1080×960）+ 深色渐变延伸底 + 文字条（条高随文字、半透黑底、左右错位 ±40px）；B = 全幅单背景（策展帧 `_crop_to_card` 1080×1920）+ 压暗 30% + 文字行居中直下。策展帧：入参新增 `curated_frame`（runner 用 `tools/vision.py` YuNet 人脸框在第一条 line 段内选最大脸+高清晰帧；无脸 → 段中点帧）；`frame_at` invalid 时**跳过该条**不再 clamp 0.0。身份 rails 横排版：`attribution` 拆"姓名 | 出处"两行画在形态 A 人像区左下（字号 48/36，白字描边）。
- 形态 C 退役：A/B 全绿后删 `speaker_frame + N 帧堆叠` 的旧分支（保留仍读 v9 示例的展示，P3 重烘焙替换 URL 后删干净）。

### 6.3 验证清单（全绿才算完）

```bash
cd apps/api && uv run python -m compileall app          # 语法
cd apps/api && uv run python scripts/chat_scenarios.py --only S1,S13,S48
cd apps/api && uv run python scripts/accept_prompt_surface.py
cd apps/web && npx tsc --noEmit
grep -rn "layout_mode" apps/                            # → 0
```

真管线 e2e（P1 收尾）：chat 发"做一张金句卡"（dev 环境 `./dev.sh` 全起）→ caption dock → 答 bilingual → Start → 产物 = 1 张叠卡（不再是 N 条单卡）+ 合成图 key 在项目作用域。**注意**：常驻 worker 会抢跑手工 run（验证后清理数据）；改 pipeline 代码必须重启 worker；本机服务互调用 `127.0.0.1` 不用 `localhost`；渲染侧若直连 TOS 超时，带 `HTTPS_PROXY=127.0.0.1:6152` 重启渲染服务。
