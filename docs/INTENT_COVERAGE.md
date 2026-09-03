# INTENT_COVERAGE — 意图层覆盖全景

> Status: 活跃（**2026-08-04 意图层单面化落地**：四表面坍缩为一表面——`/intent` 与 `/infer-intent` 端点退役，任务书构建/修订/确认并入 `/chat` book path，composer 不再做意图识别；简报 `tasks/intent-surface-unification.md`；**2026-08-05 手测修复**：prompt.txt shim 退役——素材声明由 intent router 识别并升格为 transcript 资产，零素材 generate 一律反问；**2026-08-06 剧本测试扩编 S23–S40**：dock 生命周期（bail/autonomy/409/重建/已答问题入流/附件）+ 四态实分派（task_list/edit_ops/进度/元信息/asset scope）+ checkpoint 全家（三答法/bail 级联/supersede 级联/过期/task_book 不参与 autoResume）——§6 中原"期 N e2e"行（随 API 测试套件删除的覆盖）全部改指剧本测试；**2026-08-18 复核对齐代码**：合并机械 / asset scope / 默认书兜底等漂移修正，剧本测试现到 S45；**2026-08-24 copy-writer 解除硬门禁**：派生 writer 节点 `requires=(TRANSCRIPT,)` → `()`，recipe 卡 `input_slots[0].required=False`，intent_router_system / chat_intent_system 学会"无素材 → instruction 吸收 + persona 撑骨架 + echo 散文告知"，`text_without_material` reason 软信号进 dock，剧本测试加 S48；S13 反问路径仅对 media-needing 工具生效；**2026-09-03 B2 brief 账本 + 出书门槛（ADR-052，简报 `tasks/dialog-workflow-b2-brief-ledger.md`）**：动作集四动作正名（generate→draft；**ask 一等动作**直通 dock 提问机器，payload 带 `slot` 握手 + `default_path` 牙齿——作答由 autoResume 回填账本 user-stated 并回 book path 重判，跳过 = 替身行走默认路径恢复出书）；**brief 账本**（topic/audience/tone/constraints/material_state 五槽位各带来源 + asked 簿，LLM 提议代码 merge，user-stated 恒胜）取代累积 prompt 成 book path 主状态，`pending.prompt` = 出生 prompt 冻结、`MAX_ACCUM_PROMPT_CHARS` 退役；**出书门槛**（draft 判定后的代码裁决）取代零素材反问网与 copy-writer lift 两补丁——无根（topic 空 ∧ material none ∧ 非明确配方指令）→ 代码组装 topic 问一轮（asked 簿记防重问），仍无根 → draft-from-persona dock（`draft_from_persona` reason + echo 散文声明），media-needing 链 ∧ 零素材 ∧ 桌上无书 → answer 素材引导永不 dock；剧本测试加 S50（merge_brief 来源矩阵）/ S51（裸愿望 → 主题问）/ S52（跳过 → draft-from-persona），S13/S48 断言改写归门槛）
> 单一事实源：**"用户在任意相位说任何话 → 系统走哪条路"** 的唯一登记表。
> 新增 chat 能力（skill / op / 问题形态 / 相位）时必须在本表登记；发现新缺口按 §6 格式追加。
> 机制细节不复述——task list 契约看 `CHAT_ARCHITECTURE.md`，命名看 `NAMING.md`，实施史看 `tasks/done/intent-ask-primitive.md` 与 `tasks/intent-surface-unification.md`。

---

## 1. 通道地图（一个文本表面 × 三条路径）

| 表面 | 相位 | 用户输入去向 | 推理者 | 裁决 |
|---|---|---|---|---|
| 首页 composer | — | **无意图识别**——send = spinner 建空项目 + 上传素材 + 跳转详情（草稿经 router state 交接） | 无 | 无 |
| Overlay chat（项目） | 首次 / 待决任务书 | `POST /chat`（project scope）→ **book path** | intent router（四动作：draft / ask / answer / start） | 代码：reasons 推导 + derived 预览 + 出书门槛 + dock task_book（无合并机器——面板手改整链 ride prior_intent，intent router 重提全链，ADR-043）；start 复用 answer kind=start 起 run |
| Overlay chat（项目） | 已有 run（running / results） | `POST /chat`（project scope） | chat_intent agent | 代码：四态裁决（task_list / edit_ops / ask / answer）+ autoResume |
| 产物会话（dock + 焦点注入；ChatModal 已退役——ADR-041 / `tasks/results-canvas.md`） | 单产物 | `POST /chat`（project scope + 焦点 output 注入，永不进 book path） | chat_intent agent | 同上（焦点语境注入） |
| 任意 dock | — | `POST /chat/messages/{id}/answer` | **无 LLM** | 代码：kind × question-kind 契约分派 |

book path 进入条件（`prepare_chat_turn` 分派，service.py）：project scope 且（① 有 pending task_book question；② 刚回答了带 `slot` 的提问——autoResume 已回填账本槽位；③ 无任何 run 且 `pending_brief` 为空或是 ledger-only 行——ask 回合写入的行 `intent=None`，项目仍在出书相位）。start/修订/ask/answer 的判定归 intent router LLM——dock 中的任务书以 `presented_book`（整链 JSON）注入推断上下文，短确认（"开始吧"）才能看见自己在确认什么。

非文本路径（不经意图层）：dock 按钮（Start/Cancel/autonomy/选项）、面板手编任务书、retry 按钮（`/generate` 该类链 full run）、发布对话框、编辑器内操作。

---

## 2. 意图分类法（用户会说什么）

七类。示例话术以 en 为主（目标市场），zh 对照。

| 类 | 名 | 示例 |
|---|---|---|
| **G** | 生成类 | "cut 3 clips and a LinkedIn post" / "帮我处理一下这个演讲" / "再来一版，聚焦 Q&A 部分" |
| **E** | 精编类 | "把第 3 条的标题改成 X" / "trim 掉 0:12–0:18" / "字幕样式换成 bold" |
| **T** | 翻译/配音类 | "translate clip 2 into French" / "配音成德语" / "字幕加西语版" |
| **Q** | 提问类 | "你能做什么" / "还要多久" / "这条为什么这么剪" / "为什么计划里只有 3 条" |
| **C** | 控制类 | "好的开始吧" / "停下" / "撤销" / "算了不要了" |
| **M** | 元信息类 | "换个人设皮肤" / "把目标语言改成法语"（改设置而非改产物） |
| **S** | 闲聊/越界 | "你好" / "今天天气如何" / 与项目无关的请求 |

---

## 3. 全分叉矩阵（相位 × 意图类 → 路由 → 现状）

状态口径：✅ 闭环 / 🚧 能走但有损（兜底接住，体验打折）/ ❌ 缺口（走错路或死路）

### 3.0 首次（首页 composer → 建项目 → overlay chat）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 明确（产出物+语言都说清） | /chat book path → dock，reasons 空 → 前端自动 Start | ✅（S2） |
| G 模糊（"帮我处理一下"） | /chat book path → dock + reasons → 面板确认 | ✅（S1） |
| G 全迷失（"不知道做什么/从哪开始"） | /chat book path → ask 主题问（一词可答 + 默认路径）或 dock（reasons 非空）；永不裸跑、永不出无根书（出书门槛代码兜底） | ✅（S17/S18/S21，2026-08-05；门槛兜底 2026-09-03） |
| Q 能力（"你能做什么"） | /chat book path → answer（普通 assistant 消息） | ✅（S4） |
| 空指令 | 前端本地拦截（toast） | ✅ |
| 只要 clips 但无媒体 | intent router 排除 clips；绕过则出生地 422 | ✅ |
| 贴文即素材（"这是我的文字稿：…" 或直接贴一段自己的内容） | book path 把内容升格为真正的 transcript 资产（`create_transcript_asset_from_text`；LLM 判断"这段话是内容还是请求"，禁长度启发式）→ dock | ✅（S12/S14，2026-08-05） |
| G 无素材且未贴内容 | 出书门槛统一裁决（2026-09-03 折叠原两路补丁）：链含 media-needing 工具 ∧ material none ∧ 桌上无书 → answer 素材引导（上传或贴文），永不 dock；纯 writer 链不再特殊——topic 有根即 draft + dock（`text_without_material` 软信号保留），无根走 topic 问一轮 | ✅（S13 门槛断言改写；S48 writer 软信号，2026-09-03） |
| G 无根（裸愿望："I want a social post." 无素材无主题） | 出书门槛：代码组装 topic 问一轮（choice dock，slot=topic，freeform 恒在，散文带默认路径）→ 作答回填账本 user-stated 重出 draft；跳过 / 问过仍无根 → draft-from-persona dock（`draft_from_persona` reason + echo 散文声明） | ✅（S51/S52，2026-09-03） |
| 配方播种 clips 但无媒体 | dock 保留 clips + 警告，echo 散文主动解释（上传解锁或去 clips 开工）；Start 422 后手编去 clips 可起 | ✅（S11） |
| Remix 配方后 revise 字段（"clips only needs 2"） | 配方=预设只铺第一版（不钉任何字段）→ 修订直达 docked 书 | ✅（S15，2026-08-05） |
| S 闲聊 | /chat book path → answer 或默认任务书 dock | 🚧（无专门拒绝形态，靠 LLM 判断力） |

### 3.1 待决任务书（任务书已 dock，未 Start——chat 的普通状态，不再是独立相位）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 修订链（"加条德语 post"） | /chat book path：面板手改 = 链结构直接编辑（与 LLM 提议同一数据结构），修订回合 LLM 带 presented 整链重提 → 新任务书 dock，旧 supersede；chat 恒胜是结构事实（无合并机器，ADR-043） | ✅（S3/S16） |
| 面板手改 + chat 修订冲突 | 同一数据结构无合并面：chat 修订覆盖链行（"chat 就是在改 plan，没有什么是定死的"，2026-08-05） | ✅（S16） |
| G 修订焦点/指令（"聚焦定价部分"） | 同上（brief 账本 = 累积状态：LLM 每轮提议全量更新，代码按来源优先级 merge，user-stated 恒胜；`pending.prompt` = 出生 prompt 冻结） | ✅（S3） |
| Q 能力（"能发 TikTok 吗"） | /chat book path → answer，任务书不被动 | ✅ |
| Q 计划（"为什么只有 3 条"） | /chat book path → LLM 判 answer（解释）或 draft（改成你要的数量） | ✅（LLM 判断，两可都算对） |
| **C 确认（"好的开始吧"）** | /chat book path → intent router 判 start（`presented_book` 注入，看得见在确认什么）→ answer kind=start 起 run | ✅（S1；读容忍硬化：`tasks:null` + presented_book 上下文） |
| C 取消 | dock Cancel 按钮 → answer kind=bail → 清 pending_brief 回 draft | ✅（按钮；文本"算了"仍无 chat 路径——低频，登记待真实投诉） |
| C 撤销自己上次修订 | 无 chat 命令（重说一遍反向修订 = 新修订）；面板上旧版本 chip 可展开只读快照并一键恢复（2026-08-05 版本条） | ✅（UI 恢复路径） |
| E/T/M/S | /chat book path → LLM 折算成任务书修订（如"配德语"→ dub_clip 任务）或 answer | 🚧（M 类改人设靠 answer 引导；chat 相位见 §3.3 M 行） |
| 手编面板后 Start | dock Start → answer kind=start（edited intent 优先于 stored） | ✅ |
| recipe 发射（点配方卡） | /chat book path——发射载荷 = 预填模板原文（配方 = 提示词，ADR-040），任务书从消息文案推断，与 composer 完全同径 | ✅（S5） |

### 3.2 运行相位（run 在跑）

| 意图 | 路由 | 现状 |
|---|---|---|
| checkpoint 答题：点按钮 | /answer option → resume | ✅ |
| checkpoint 答题：打字母/序号/原文 | /chat autoResume（零 LLM）→ resume | ✅ |
| checkpoint 答题：自由文本 | freeform → resume | ✅ |
| checkpoint 弃跑 | dock bail 按钮 → 级联 skipped + COMPLETED（永不 failed） | ✅ |
| checkpoint 不答 | 过期扫描（默认 30min）→ 默认项 auto-answer + resume | ✅ |
| checkpoint 答题期间另起新题 | 新题 supersede → 级联 bail 那个 run（多 run 不搁浅） | ✅ |
| **Q 进度（"到哪了/还要多久"）** | /chat → answer 形态；`_build_context` 注入 latest run 的节点级量化摘要（kind: status — summary，≤12 行），waiting checkpoint 行天然传达"在等你" | ✅（期 4 补四 G-2） |
| **C 停止（"停下来/不要跑了"）** | /chat → 无 stop skill；checkpoint bail 只在 parked 时可用 | ❌ **缺口 G-3**（running 中无中止语义；明确先不做） |
| G 新需求（"顺便来个法语版"） | /chat → task_list（translate_clip/dub_clip/write_*）→ 新 run | ✅ |
| **Q 能力（"你能做 X 吗"）** | /chat → **answer 第四态**（N-21）：纯信息直答，不落 task、不起 run、不 dock；与 confirm 相位同待遇 | ✅（期 4 补四 G-4） |
| Q 解释（"这条为什么这么剪"） | /chat → answer 形态凭 outputs one-liner 答 | ✅（路由已闭环；深度凭 one-liner 有限，深化归 context 丰富化后续） |
| S 闲聊 | /chat → answer 形态礼貌回应 | ✅（期 4 补四 G-4 收编） |

### 3.3 完成相位（results）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 整类重做（"post 重写一版"） | retry 按钮（/generate：该类自己的链原样重跑——text 族=单 writer 任务，clips 族=链内 clips 族任务原序原参数）或 chat task_list write_post | ✅ |
| G 全部重出（"换个角度再来一版"） | chat task_list 多 skill / /generate full | ✅ |
| E 精确编辑（改标题/裁剪/字幕样式/音乐/裁切比/恢复版本） | /chat → edit_ops → apply_operations（undo 免费） | ✅ |
| E 改文案内容（"开头改得更抓人"） | /chat → revise_script（或进编辑器） | ✅ |
| T 翻译字幕 / T 配音 | /chat → task_list translate_clip / dub_clip（precomputed ops 不走 edit_ops） | ✅ |
| T 去口头禅 / T 加音乐 | task_list remove_filler / add_music（确定性 tool） | ✅ |
| C 撤销 | chat 撤销按钮 / undo 端点 | ✅ |
| **C 发布（"发到 LinkedIn"）** | /chat → answer 引导文案（"产物卡的发布按钮"）；远期 publish skill 依赖 Distribution 凭据 | ✅（期 4 补四 G-5，answer 引导收编） |
| **E 纠错（"这个词译错了，应该是 X"）** | /chat → revise_script 单点修；**无法"到处都改"** | 🚧（glossary 的对话入口——未来走 dispatch 注册表，不开新通道） |
| **M 元信息（"换人设/换皮肤/换声音"）** | /chat → answer 导航文案（Personas 页面） | ✅（期 4 补四 G-6，answer 引导收编） |
| M 目标语言改 | chat task_list（translate/write 新任务）折算 | ✅（产物级正解） |
| 上传新素材 | overlay 输入组回形针：文件暂存为 chip（上传进度/失败重试/× 删除），随发送按钮随轮发出（`attachments` 随消息持久化，刷新重放）；attachment-only 发送合法（book path 以替身行推断，空文本不 autoResume checkpoint） | ✅（2026-08-05 手测修复；原"上传完自动发消息且无响应"缺陷退役） |
| **G 再来一条同族 writer（"再写一条德语 post"/"also 4 quote cards about AI"），已有 project 未上新素材** | chat → task_list write_post(de) / write_quotes(count=4) 等；从 persona + instruction 起草，**永不**反问上传（2026-08-24 lift：copy-writer 不再被硬门禁要求素材） | ✅ |

### 3.4 产物会话（dock + 焦点注入；ChatModal / asset scope 已退役——ADR-041）

| 意图 | 路由 | 现状 |
|---|---|---|
| E 改稿（"改短一点"） | /chat → revise_script，target_output_id 自动注入会话 scope | ✅ |
| T 翻译/配音 | /chat → translate_clip / dub_clip | ✅ |
| E 精确编辑 | edit_ops（target 即本会话产物） | ✅ |
| Q 内容（"这段讲了什么"） | /chat → LLM 凭上下文答 | ✅ |
| Q 能力 | /chat → answer 形态（同 §3.2 G-4 修复） | ✅ |
| LLM 故障 | 反问文案（唯一形态；asset scope 已退役，其 revise_script 降级随之退役） | ✅ |

---

## 4. 裁决与兜底层（每条路径的安全网）

按序生效，上一层失败落到下一层：

1. **autoResume（零 LLM）**：choice 待决 + /chat 文本 → 字母/序号/原文命中 → option；否则 allow_freeform → freeform；否则进入 2。**带 `slot` 的提问（book-path ask）作答时额外回填账本槽位（user-stated）并直通 book path 重判**。task_book 待决不参与（它的答案是 dock 按钮与 book path 修订/确认）。
2. **book path（intent router 四动作）**：首次 / 待决任务书的项目级文本 → draft（链整体重提 + reasons + re-dock——面板手改 = 链结构直接编辑，无合并机器，ADR-043）/ ask（一等动作：choice 直通 dock 提问机器，`slot` 握手 → 作答回填账本，`default_path` → dock 散文第二句；同槽位重问被代码翻回 draft——问环有界）/ answer（普通消息）/ start（answer kind=start 起 run）。**出书门槛（代码裁决，draft 判定后）**：无根（topic 空 ∧ material none ∧ 非明确配方指令）→ 代码组装 topic 问一轮（asked 簿记，问过不再问）；仍无根（或用户跳过提问）→ draft-from-persona dock（reasons 标记 + echo 散文声明）；media-needing 链 ∧ material none ∧ 桌上无书 → answer 素材引导，永不 dock。
3. **chat_intent agent 四态**：task_list / edit_ops / ask / answer。ask 是合法输出（2-4 选项 + freeform 回落），answer 是纯信息直答（无工作请求且无歧义才可用——干活走 task_list/edit_ops，读数有歧义走 ask），永远不死路。
4. **代码裁决**：registry 校验 skill/params（SkillRejected → 一次 repair_feedback 重试 → 再败则反问）；edit ops 校验（OpRejected → 提示）；出生地校验（requires / clips-media / count 边界 → 422 或反问）。
5. **LLM 故障**：MiniMaxError（含 402/429/5xx，client 边界已统一包装）→ chat loop 反问文案；book path 不兜底——provider 故障穿透到路由边界：JSON 502 / SSE 终帧 `turn.failed`，带 `user_error_line` 本地化行（明确不 dock 编造默认书：错误计划看着像真的，Start 会为它烧一次付费 run）；`tasks:null` 等 LLM 松散输出由 schema 读容忍接住，不降级为兜底。
6. **幂等与竞态**：单待决不变量（新题 supersede 旧题 + 级联 bail）；answer 409（重复回答）；落库去重（首条消息即会话种子）；过期扫描守护式 UPDATE（用户答案永远赢）。

---

## 5. 已登记缺口（按修复性价比排序）

| # | 缺口 | 影响 | 建议修法 | 量级 |
|---|---|---|---|---|
| ~~G-7~~ | ~~短贴文（~25 词开场白式）零素材首轮被判非素材~~ | ✅ **已修（2026-08-06）**：根因 = intent router 上下文真空——`_messages` 只有累积 prompt + 文件名 + presented_book，answer 轮后每条消息在真空里判（看不见"上一轮刚被要素材"），判不准按规则走 ask（迷失旅程反问死循环，S21 短贴文 fixture 3/3 复现）。修法 = **recent 对话注入**（`_plan_turn` 传最近 5 轮、`_messages` 加 "Recent conversation" 段）——只喂上下文不加倾向规则，素材/请求判定归 LLM 凭语境完成；同 08-04 presented_book 硬化先例。S21 fixture 保持 25 词短贴文作回归 | — | — |
| ~~G-1~~ | ~~确认相位文本"开始吧/可以了"被当成修订~~ | ✅ **已修**：action 加 `"start"` 座位，复用 answer kind=start 路径（presented_book 注入 + `tasks:null` 读容忍硬化） | — | — |
| ~~G-4~~ | ~~/chat 无 answer 形态~~ | ✅ **已修（期 4 补四）**：IntentProposal 第四态 `AnswerProposal`（N-21），纯信息直答落普通 assistant 消息 | — | — |
| ~~G-2~~ | ~~进度询问无节点级数据~~ | ✅ **已修（期 4 补四）**：`_build_context` 注入 latest run steps 量化摘要（`_format_step_progress`，≤12 行） | — | — |
| ~~G-5~~ | ~~发布意图在 chat 是死路~~ | ✅ **已修（期 4 补四）**：answer 引导文案（产物卡发布按钮）；远期 publish skill 仍依赖 Distribution 凭据 | — | — |
| G-3 | running 中无中止语义 | 低频（bail 已覆盖 parked 场景） | 评估是否值得 run 级 cancel（涉及级联语义；**先不做**，等真实投诉） | 大 |
| ~~G-6~~ | ~~元信息修改（人设/皮肤/声音）无引导~~ | ✅ **已修（期 4 补四）**：answer 导航文案（Personas 页面） | — | — |

明确不做：chat 内上传素材（modal 已是最短路径）；chat 内改账户/计费设置（settings 页面）；G-3（见上行）。

---

## 6. 测试矩阵（e2e 覆盖对照）

**剧本测试**：`apps/api/scripts/chat_scenarios.py`（2026-08-04 建，2026-08-06 扩编）——对活 API 跑预设多轮剧本，形态级断言（提案态 / dock / run 数 / 落库 / answer 契约 / checkpoint 状态机），真实 LLM 不锁文案。S1–S45 全绿（S22 随 recipe_id 传输带退役、编号留空；S46 reframe 派发、S47 workflow_step 提及、S48 copy-writer 无素材软信号，2026-08-24；S50 merge_brief 来源矩阵、S51 ask 一等动作、S52 出书门槛，2026-09-03）；迷失用户横切变体 S17–S21 散入五族（迷失是用户状态不是意图类别；`# W4 升级:` 注释 = 顾问姿态落地时要收紧的断言钩子）。checkpoint 族（S36–S39）seed parked run 手工行驱动，收官断言依赖 dev worker（answer 分支零 LLM）。**历史注**：本表早期引用的"期 N e2e / API 面 e2e"随 API 测试套件一并删除（漂移退役，见 CLAUDE.md Testing），现役唯一自动化验收 = 剧本测试。

| 路径 | 覆盖 |
|---|---|
| 首次：模糊 dock + "开始吧"起 run + pending_brief 清空 | ✅ S1 |
| 首次：精确 slots（clips×5 + post(de)）+ dock Start + run slots 一致 | ✅ S2 |
| 修订循环：re-dock / supersede / 未修订任务存活（brief 账本重提全链）/ 确认起 run | ✅ S3 |
| 能力提问纯 answer + 无书"start it"不死路不起 run | ✅ S4 |
| 配方发射 = 模板原文（无 recipe_id 传输带；模板点名的产出与字幕语言全提取） | ✅ S5 |
| 已有 run 项目不进 book path（回归） | ✅ S6 |
| 闲聊 / 发布引导 answer 形态 + run 数不变 | ✅ S7 |
| 空项目列表不可见 → 首发消息可见 | ✅ S8 |
| checkpoint 三答法（option 按钮 / 打字母 autoResume / 自由文本）+ 答题即唤醒 | ✅ S36 |
| checkpoint bail：节点 done(bailed) + 下游级联 skipped + COMPLETED（永不 failed） | ✅ S37 |
| checkpoint 多 run 级联：新题 supersede → 旧 run 收官 COMPLETED | ✅ S38 |
| checkpoint 过期：TTL 扫描默认项 auto-answer（expired 标记）+ 续跑 | ✅ S39 |
| autoResume 边界：空白 attachment-only 不答 checkpoint；task_book 不参与 autoResume | ✅ S36d / S40 |
| ask 落库（chat_intent agent ask 提案 → dock choice） | ⚠️ 无确定性 scenario（ask 提案靠 LLM 触发，只有人工走查） |
| 单待决 supersede（task_book re-dock / checkpoint 到题）+ 待决重建（pending_question） | ✅ S27 / S38 / S26 |
| answer 端点契约：一行一答 409 / kind×question-kind 422 / autonomy 透传 run.context | ✅ S25 / S24（422 矩阵见 S11、S29、S35） |
| 出生地 guards：clips-media 门 + count 边界（节点 `count_limits` 声明派生：clips 1-10 / quotes 1-20 / carousel 2-15） | ✅ S11 / S29 |
| chat_intent agent 实分派：task_list 新 run / edit_ops operations 行（chat 血统 + message_id） | ✅ S31 / S32 |
| G-1 started 联合 + task_book kind=start + pending_brief 清空 | ✅ S1（期 4 补四 e2e 的继承者） |
| G-4 answer 形态（能力/发布问题：无 run、无 dock、run 数不变） | ✅ S4/S7 |
| G-2 进度询问 answer 形态（节点级上下文注入，无新 run） | ✅ S33 |
| G-6 元信息修改（品牌/说话人）answer 导航形态 | ✅ S34 |
| 焦点注入：focus_output 随轮落库、不开新会话、不进 book path；退役 asset scope 参数被 422 | ✅ S35 |
| 附件：attachment-only 发送持久化 + 替身行推断不死路 | ✅ S30 |
| task_book bail → 回 draft 可重开；已答问题入流（superseded/start 标记） | ✅ S23 / S27 |
| translate_clip / dub_clip chat 派发 | ❌ 待补（烧声纹/渲染管线，登记为已知空白） |
| 字幕归类："subtitle them in French" → translate_clip(fr/de) | ✅ S43 |
| 整条视频字幕："给我的视频加中英双语字幕" → 变换技能单独成链 + materialize_source 注入 | ✅ S44 |
| repair 有界重试：schema 拒 → 一轮修复带结构化回显，再拒即败无第三轮；transport 不修 | ✅ S41 |
| 估价地基：flow 对账自检 + 报价 fold 单调性（子图 ≤ 全图、非负）+ NULL 语义 | ✅ S42 |
| materialize 注入矩阵：media / stills 注入（stills 先 align_stills）、existing 空 inputs、无画像编译期拒绝、select_clips 在场不注入 | ✅ S45 |
| copy-writer 无素材软信号：无素材 + 写帖 → draft + dock 带 `text_without_material` reason + Start 起 run；media-needing 不夹带（原硬门禁 lift 已折进出书门槛） | ✅ S48（2026-08-24，门槛同车改写） |
| ask 一等动作：裸愿望 → 选项问 dock（slot=topic + default_path + 2-4 选项 + freeform 恒在）→ 作答回填账本 user-stated | ✅ S51 |
| 跳过提问 = 默认路径：选项问 bail + slot → 替身行恢复 book path → draft-from-persona dock（reasons 标记 + asked 簿 + echo 散文） | ✅ S52 |
| merge_brief 纯函数：来源优先级矩阵（user-stated 恒胜 / 重申恒胜 / inferred 可覆写）+ asked 簿永不吃 LLM 提议 | ✅ S50 |

---

## 7. 登记纪律

- 新 skill/op/问题形态落地时：更新 §2 分类（若新类）、§3 矩阵、§6 矩阵。
- 发现用户话术走错路：先登记 §5（含重现话术），再谈修。
- 本表只登记"用户→路由"映射与状态；机制怎么实现看 `CHAT_ARCHITECTURE.md`，为什么这么设计看 `tasks/done/intent-ask-primitive.md` 与各 ADR。
