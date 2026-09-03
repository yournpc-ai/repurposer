# INTENT_COVERAGE — 意图层覆盖全景

> Status: 活跃（**2026-08-04 意图层单面化落地**：四表面坍缩为一表面——`/intent` 与 `/infer-intent` 端点退役，任务书构建/修订/确认并入 `/chat` book path，composer 不再做意图识别；简报 `tasks/intent-surface-unification.md`；**2026-08-05 手测修复**：prompt.txt shim 退役——素材声明由 intent router 识别并升格为 transcript 资产，零素材 generate 一律反问；**2026-08-06 剧本测试扩编 S23–S40**：dock 生命周期（bail/autonomy/409/重建/已答问题入流/附件）+ 四态实分派（task_list/edit_ops/进度/元信息/asset scope）+ checkpoint 全家（三答法/bail 级联/supersede 级联/过期/task_book 不参与 autoResume）——§6 中原"期 N e2e"行（随 API 测试套件删除的覆盖）全部改指剧本测试；**2026-08-18 复核对齐代码**：合并机械 / asset scope / 默认书兜底等漂移修正，剧本测试现到 S45；**2026-08-24 copy-writer 解除硬门禁**：派生 writer 节点 `requires=(TRANSCRIPT,)` → `()`，recipe 卡 `input_slots[0].required=False`，intent_router_system / chat_intent_system 学会"无素材 → instruction 吸收 + persona 撑骨架 + echo 散文告知"，`text_without_material` reason 软信号进 dock，剧本测试加 S48；S13 反问路径仅对 media-needing 工具生效；**2026-09-03 B2 brief 账本 + 出书门槛（ADR-052，简报 `tasks/dialog-workflow-b2-brief-ledger.md`）**：动作集四动作正名（generate→draft；**ask 一等动作**直通 dock 提问机器，payload 带 `slot` 握手 + `default_path` 牙齿——作答经 slot 握手判定结算回填账本 user-stated（ADR-053 R2：判定是 LLM 的、结算是代码的）并回 book path 重判，跳过 = 替身行走默认路径恢复出书）；**brief 账本**（topic/audience/tone/constraints/material_state 五槽位各带来源 + asked 簿，LLM 提议代码 merge，user-stated 恒胜）取代累积 prompt 成 book path 主状态，`pending.prompt` = 出生 prompt 冻结、`MAX_ACCUM_PROMPT_CHARS` 退役；**出书门槛**（draft 判定后的代码裁决）取代零素材反问网与 copy-writer lift 两补丁——无根（topic 空 ∧ material none ∧ 非明确配方指令）→ 代码组装 topic 问一轮（asked 簿记防重问），仍无根 → draft-from-persona dock（`draft_from_persona` reason + echo 散文声明），media-needing 链 ∧ 零素材 ∧ 桌上无书 → answer 素材引导永不 dock；剧本测试加 S50（merge_brief 来源矩阵）/ S51（裸愿望 → 主题问）/ S52（跳过 → draft-from-persona），S13/S48 断言改写归门槛；**2026-09-04 C3 形态律 + 插话支持（ADR-053）+ C4 剧本浓缩（简报 `tasks/de-dialect-question-machine.md`）**：**形态律 R1**——文字问（options 空）= 普通对话消息永不停靠、选项问 = 非阻塞 pill 浮于活输入之上、输入框永不隐藏（blocking morph 拆毁永禁回归）、× = 显式跳过（吃 default_path；interrupt × 停付费 run）、AnsweredQuestion 块只渲染选项问与 task_book 回执；**插话支持 R2**——判定是 LLM 的、结算是代码的：book path = slot 握手（router 在 pending 上下文里提案槽位值 user-stated → 代码结算 freeform 回填），chat path = `pending_disposition` 三态（answer / skip / none 骑信封，非第五提案态），autoResume 收窄为只认选项命中的确定性结算（「任意文本 = freeform 回答」掩盖退役），插话回合回复接代码拼装提醒尾（原问题 + default_path）；**C4 剧本浓缩**：52 本机制碎片（旧 S1–S53）浓缩为 12 条核心用户 story 连续重排，**旧 S 号全部作废**——本文件此前条目里的 S 编号皆为历史引用，现役映射只看 §6）
> 单一事实源：**"用户在任意相位说任何话 → 系统走哪条路"** 的唯一登记表。
> 新增 chat 能力（skill / op / 问题形态 / 相位）时必须在本表登记；发现新缺口按 §6 格式追加。
> 机制细节不复述——task list 契约看 `CHAT_ARCHITECTURE.md`，命名看 `NAMING.md`，实施史看 `tasks/done/intent-ask-primitive.md` 与 `tasks/intent-surface-unification.md`。

---

## 1. 通道地图（一个文本表面 × 三条路径）

| 表面 | 相位 | 用户输入去向 | 推理者 | 裁决 |
|---|---|---|---|---|
| 首页 composer | — | **无意图识别**——send = spinner 建空项目 + 上传素材 + 跳转详情（草稿经 router state 交接） | 无 | 无 |
| Overlay chat（项目） | 首次 / 待决任务书 | `POST /chat`（project scope）→ **book path** | intent router（四动作：draft / ask / answer / start） | 代码：reasons 推导 + derived 预览 + 出书门槛 + dock task_book（无合并机器——面板手改整链 ride prior_intent，intent router 重提全链，ADR-043）；start 复用 answer kind=start 起 run |
| Overlay chat（项目） | 已有 run（running / results） | `POST /chat`（project scope） | chat_intent agent | 代码：四态裁决（task_list / edit_ops / ask / answer）+ autoResume（只认选项命中的确定性结算）+ `pending_disposition` 判定结算（ADR-053 R2） |
| 产物会话（dock + 焦点注入；ChatModal 已退役——ADR-041 / `tasks/results-canvas.md`） | 单产物 | `POST /chat`（project scope + 焦点 output 注入，永不进 book path） | chat_intent agent | 同上（焦点语境注入） |
| 任意 dock | — | `POST /chat/messages/{id}/answer` | **无 LLM** | 代码：kind × question-kind 契约分派 |

book path 进入条件（`prepare_chat_turn` 分派，service.py）：project scope 且（① 有 pending task_book question；② 刚回答了带 `slot` 的提问——slot 握手判定结算已回填账本槽位（user-stated）；③ 无任何 run 且 `pending_brief` 为空或是 ledger-only 行——ask 回合写入的行 `intent=None`，项目仍在出书相位）。start/修订/ask/answer 的判定归 intent router LLM——dock 中的任务书以 `presented_book`（整链 JSON）注入推断上下文，短确认（"开始吧"）才能看见自己在确认什么。

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
| G 明确（产出物+语言都说清） | /chat book path → dock，reasons 空 → 前端自动 Start | ✅（S4——dock → Start → run completed 同径覆盖） |
| G 模糊（"帮我处理一下"） | /chat book path → dock + reasons → 面板确认 | ✅（S1/S4） |
| G 全迷失（"不知道做什么/从哪开始"） | /chat book path → ask 主题问（一词可答 + 默认路径）或 dock（reasons 非空）；永不裸跑、永不出无根书（出书门槛代码兜底） | ✅（S1/S2） |
| Q 能力（"你能做什么"） | /chat book path → answer（普通 assistant 消息） | ✅（S9） |
| 空指令 | 前端本地拦截（toast） | ✅ |
| 只要 clips 但无媒体 | intent router 排除 clips；绕过则出生地 422 | ✅ |
| 贴文即素材（"这是我的文字稿：…" 或直接贴一段自己的内容） | book path 把内容升格为真正的 transcript 资产（`create_transcript_asset_from_text`；LLM 判断"这段话是内容还是请求"，禁长度启发式）→ dock | 🚧（升格机制现役；专项剧本旧 S12/S14 随 C4 浓缩退役——人工走查，回归需求登记后补拍） |
| G 无素材且未贴内容 | 出书门槛统一裁决（2026-09-03 折叠原两路补丁）：链含 media-needing 工具 ∧ material none ∧ 桌上无书 → answer 素材引导（上传或贴文），永不 dock；纯 writer 链不再特殊——topic 有根即 draft + dock（`text_without_material` 软信号保留），无根走 topic 问一轮 | ✅（S1/S2 门槛主径；素材引导 answer 与 writer 软信号的专项断言（旧 S13/S48）随 C4 浓缩退役，裁决单点 = 出书门槛） |
| G 无根（裸愿望："I want a social post." 无素材无主题） | 出书门槛：代码组装 topic 问一轮（选项问 dock，slot=topic，自由文本可答，散文带默认路径）→ 作答回填账本 user-stated 重出 draft；跳过 / 问过仍无根 → draft-from-persona dock（`draft_from_persona` reason + echo 散文声明） | ✅（S1/S2） |
| 配方播种 clips 但无媒体 | dock 保留 clips + 警告，echo 散文主动解释（上传解锁或去 clips 开工）；Start 422 后手编去 clips 可起 | 🚧（机制现役；专项剧本旧 S11 随 C4 浓缩退役） |
| Remix 配方后 revise 字段（"clips only needs 2"） | 配方=预设只铺第一版（不钉任何字段）→ 修订直达 docked 书 | ✅（S5——chat 修订恒胜同径覆盖） |
| S 闲聊 | /chat book path → answer 或默认任务书 dock | ✅（S9——闲聊纯 answer、无 run 无 dock 已锁） |

### 3.1 待决任务书（任务书已 dock，未 Start——chat 的普通状态，不再是独立相位）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 修订链（"加条德语 post"） | /chat book path：面板手改 = 链结构直接编辑（与 LLM 提议同一数据结构），修订回合 LLM 带 presented 整链重提 → 新任务书 dock，旧 supersede；chat 恒胜是结构事实（无合并机器，ADR-043） | ✅（S5） |
| 面板手改 + chat 修订冲突 | 同一数据结构无合并面：chat 修订覆盖链行（"chat 就是在改 plan，没有什么是定死的"，2026-08-05） | ✅（S5） |
| G 修订焦点/指令（"聚焦定价部分"） | 同上（brief 账本 = 累积状态：LLM 每轮提议全量更新，代码按来源优先级 merge，user-stated 恒胜；`pending.prompt` = 出生 prompt 冻结） | ✅（S5） |
| Q 能力（"能发 TikTok 吗"） | /chat book path → answer，任务书不被动 | ✅ |
| Q 计划（"为什么只有 3 条"） | /chat book path → LLM 判 answer（解释）或 draft（改成你要的数量） | ✅（LLM 判断，两可都算对） |
| **C 确认（"好的开始吧"）** | /chat book path → intent router 判 start（`presented_book` 注入，看得见在确认什么）→ answer kind=start 起 run | ✅（S1/S5；读容忍硬化：`tasks:null` + presented_book 上下文） |
| C 取消 | dock Cancel 按钮 → answer kind=bail → 清 pending_brief 回 draft | ✅（按钮；文本"算了"仍无 chat 路径——低频，登记待真实投诉） |
| C 撤销自己上次修订 | 无 chat 命令（重说一遍反向修订 = 新修订）；面板上旧版本 chip 可展开只读快照并一键恢复（2026-08-05 版本条） | ✅（UI 恢复路径） |
| E/T/M/S | /chat book path → LLM 折算成任务书修订（如"配德语"→ dub_clip 任务）或 answer | 🚧（M 类改人设靠 answer 引导；chat 相位见 §3.3 M 行） |
| 手编面板后 Start | dock Start → answer kind=start（edited intent 优先于 stored） | ✅ |
| recipe 发射（点配方卡） | /chat book path——发射载荷 = 预填模板原文（配方 = 提示词，ADR-040），任务书从消息文案推断，与 composer 完全同径 | ✅（S1——与 composer 同径，路径覆盖相同；模板原文逐字断言（旧 S5）随 C4 浓缩退役） |

### 3.2 运行相位（run 在跑）

| 意图 | 路由 | 现状 |
|---|---|---|
| checkpoint 答题：点按钮 | /answer option → resume | ✅（S6a） |
| checkpoint 答题：打字母/序号/原文 | /chat autoResume（零 LLM 确定性结算——ADR-053 后唯一确定性座位）→ resume | ✅（S6b） |
| checkpoint 答题：自由文本 | /chat → chat_intent 判 `pending_disposition=answer` → 代码结算 freeform → resume（判定是 LLM 的、结算是代码的，ADR-053 R2） | ✅（S6c） |
| checkpoint 弃跑 | dock bail 按钮 → 级联 skipped + COMPLETED（永不 failed） | ✅（S6e） |
| checkpoint 不答 | 过期扫描（默认 30min）→ 默认项 auto-answer + resume | ✅（机制现役，TTL 语义 ADR-053 未动；专项剧本旧 S39 随 C4 浓缩退役——人工走查） |
| checkpoint 答题期间另起新题 | 新题 supersede → 级联 bail 那个 run（多 run 不搁浅） | ✅（机制现役；多 run 级联专项（旧 S38）随 C4 浓缩退役，supersede 主径由 S5 覆盖） |
| **checkpoint 停驻中插话**（"跑得到哪了"） | /chat → chat_intent 判 `pending_disposition=none` → 正常回答 + 代码拼装提醒尾（原问题 + default_path）；问题保持待决、run 保持 parked，下轮作答再唤醒 | ✅（S6f，ADR-053 R2） |
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

1. **autoResume（零 LLM 确定性结算，ADR-053 收窄）**：选项问待决 + /chat 文本 → 字母/序号/原文 verbatim 命中 → option 结算（interrupt 命中即唤醒）；**其余文本永不在此结算**（「任意文本 = freeform 回答」掩盖 2026-09-04 退役）——进入 2/3 由 LLM 判定（插话支持：**判定是 LLM 的、结算是代码的**——book path slot 握手 / chat path `pending_disposition` 三态），判为回答的由代码结算 freeform 并经既有 `answered_question` 通道上车；判为插话的正常回答 + 代码拼装提醒尾（原问题 + default_path），问题保持待决。**带 `slot` 的提问（book-path ask）作答时回填账本槽位（user-stated）并直通 book path 重判**。task_book 待决不参与任何结算（它的答案是 dock 按钮与 book path 修订/确认）。
2. **book path（intent router 四动作）**：首次 / 待决任务书的项目级文本 → draft（链整体重提 + reasons + re-dock——面板手改 = 链结构直接编辑，无合并机器，ADR-043）/ ask（一等动作：选项问直通 dock 提问机器，`slot` 握手 → 作答回填账本，`default_path` → dock 散文第二句；同槽位重问被代码翻回 draft——问环有界）/ answer（普通消息）/ start（answer kind=start 起 run）。**出书门槛（代码裁决，draft 判定后）**：无根（topic 空 ∧ material none ∧ 非明确配方指令）→ 代码组装 topic 问一轮（asked 簿记，问过不再问）；仍无根（或用户跳过提问）→ draft-from-persona dock（reasons 标记 + echo 散文声明）；media-needing 链 ∧ material none ∧ 桌上无书 → answer 素材引导，永不 dock。
3. **chat_intent agent 四态**：task_list / edit_ops / ask / answer。ask 是合法输出（2-4 选项 + 自由文本可答），answer 是纯信息直答（无工作请求且无歧义才可用——干活走 task_list/edit_ops，读数有歧义走 ask），永远不死路。**待决问题存在时信封带 `pending_disposition` 三态**（answer / skip / none——非第五提案态）：判 answer/skip 代码结算/跳过该问题；判 none = 插话，正常回复 + 代码提醒尾，问题保持待决。
4. **代码裁决**：registry 校验 skill/params（SkillRejected → 一次 repair_feedback 重试 → 再败则反问）；edit ops 校验（OpRejected → 提示）；出生地校验（requires / clips-media / count 边界 → 422 或反问）。
5. **LLM 故障**：MiniMaxError（含 402/429/5xx，client 边界已统一包装）→ chat loop 反问文案；book path 不兜底——provider 故障穿透到路由边界：JSON 502 / SSE 终帧 `turn.failed`，带 `user_error_line` 本地化行（明确不 dock 编造默认书：错误计划看着像真的，Start 会为它烧一次付费 run）；`tasks:null` 等 LLM 松散输出由 schema 读容忍接住，不降级为兜底。
6. **幂等与竞态**：单待决不变量（新题 supersede 旧题 + 级联 bail）；answer 409（重复回答）；落库去重（首条消息即会话种子）；过期扫描守护式 UPDATE（用户答案永远赢）。

---

## 5. 已登记缺口（按修复性价比排序）

| # | 缺口 | 影响 | 建议修法 | 量级 |
|---|---|---|---|---|
| ~~G-7~~ | ~~短贴文（~25 词开场白式）零素材首轮被判非素材~~ | ✅ **已修（2026-08-06）**：根因 = intent router 上下文真空——`_messages` 只有累积 prompt + 文件名 + presented_book，answer 轮后每条消息在真空里判（看不见"上一轮刚被要素材"），判不准按规则走 ask（迷失旅程反问死循环，S21 短贴文 fixture 3/3 复现）。修法 = **recent 对话注入**（`_plan_turn` 传最近 5 轮、`_messages` 加 "Recent conversation" 段）——只喂上下文不加倾向规则，素材/请求判定归 LLM 凭语境完成；同 08-04 presented_book 硬化先例。回归 fixture（旧 S21 短贴文）随 C4 浓缩退役——recent 注入机制现役，迷失旅程主径由 S1/S2 覆盖 | — | — |
| ~~G-1~~ | ~~确认相位文本"开始吧/可以了"被当成修订~~ | ✅ **已修**：action 加 `"start"` 座位，复用 answer kind=start 路径（presented_book 注入 + `tasks:null` 读容忍硬化） | — | — |
| ~~G-4~~ | ~~/chat 无 answer 形态~~ | ✅ **已修（期 4 补四）**：IntentProposal 第四态 `AnswerProposal`（N-21），纯信息直答落普通 assistant 消息 | — | — |
| ~~G-2~~ | ~~进度询问无节点级数据~~ | ✅ **已修（期 4 补四）**：`_build_context` 注入 latest run steps 量化摘要（`_format_step_progress`，≤12 行） | — | — |
| ~~G-5~~ | ~~发布意图在 chat 是死路~~ | ✅ **已修（期 4 补四）**：answer 引导文案（产物卡发布按钮）；远期 publish skill 仍依赖 Distribution 凭据 | — | — |
| G-3 | running 中无中止语义 | 低频（bail 已覆盖 parked 场景） | 评估是否值得 run 级 cancel（涉及级联语义；**先不做**，等真实投诉） | 大 |
| ~~G-6~~ | ~~元信息修改（人设/皮肤/声音）无引导~~ | ✅ **已修（期 4 补四）**：answer 导航文案（Personas 页面） | — | — |

明确不做：chat 内上传素材（modal 已是最短路径）；chat 内改账户/计费设置（settings 页面）；G-3（见上行）。

---

## 6. 测试矩阵（e2e 覆盖对照）

**剧本测试**：`apps/api/scripts/chat_scenarios.py`——对活 API 跑预设多轮剧本，形态级断言（提案态 / dock / run 数 / 落库 / answer 契约 / checkpoint 状态机 / SSE 帧序），真实 LLM 不锁文案（例外：代码强制文本——提醒尾 / 机器标记 / 确定性回执——那是代码不是 LLM）。**2026-09-04 大浓缩（C4，简报 `tasks/de-dialect-question-machine.md`）**：52 本机制碎片（旧 S1–S53）浓缩为 **12 条核心用户 story，编号连续重排（S1–S12），旧 S 号全部作废**；每条 = 一个完整用户故事，进程内纯函数矩阵（估价 / repair / materialize / merge_brief）按简报「保留并入」随链收编进 S4/S11/S12。S6 checkpoint 族 seed parked run 手工行驱动，收官断言依赖 dev worker（answer 分支零 LLM）；S4/S8 的 run 走真 worker 真 LLM。**历史注**：本表早期引用的"期 N e2e / API 面 e2e"随 API 测试套件一并删除（漂移退役，见 CLAUDE.md Testing），现役唯一自动化验收 = 剧本测试。

| 路径 | 覆盖 |
|---|---|
| **核①** 裸愿望全旅程：主题问（slot=topic + default_path + 选项 2-4 或空）→ 待决重建零内存态 → 自由文本 slot 握手结算（kind=freeform + 账本回填 user-stated）→ 一行一答 409 → 评审卡（merged brief 钢印进 payload）→ 散文确认起 run + pending_brief 清空 | ✅ S1 |
| **核②** 跳过 = 默认路径：主题问 bail → draft-from-persona 书（`draft_from_persona` reason + asked 簿记 + echo 散文声明） | ✅ S2 |
| **核③** 插话：正常回答 + 代码拼装提醒尾（含 default_path 原文）+ 无新题 dock + 问题保持待决 → 下轮作答经 slot 握手结算回填 | ✅ S3 |
| **核④** 素材全链：COMPLETED transcript 资产 → writer 链 run completed + post 产物落库；估价三断言（fold 报价单调性 / NULL 语义 / dangling-transform 编译拒绝）+ repair 只一轮七节（echo / 无第三轮 / transport 不修 / declared fallback / repair_feedback 首试 / streaming repair 非流 / media_text_fallback 复合 4 调用） | ✅ S4 |
| **核⑤** 修订链：re-dock 旧书 supersede 机器标记 / 面板手改存活于无关 refine / chat 修订恒胜覆盖面板钉 / task_book 待决打字母永不误答 / 散文确认起 run | ✅ S5 |
| **核⑥** interrupt 一条：option 答（端点同步唤醒）/ 打字母 autoResume / 自由文本判定结算（kind=freeform + 确定性回执）/ 空白 attachment-only 永不误答 / bail 级联（done(bailed) + 下游 skipped + COMPLETED 永不 failed）/ 插话（回答 + 提醒尾 + 保持 parked）后续跑 | ✅ S6（需 dev worker） |
| **核⑦** caption mode：选项问先 dock 不起 run → 回执 kind=option + mode 钉 pending_brief；en/en 无独立第二语言不问、source_only 入 run.context；答 → 追问 → Start 全链存活（stash 继承） | ✅ S7 |
| **核⑧** research 全链：面板手编 [research, write_post] 起步 → research done + spec.research_brief 钢印 + writer 有序完成 + post 落库（活 DDG 全灭时 caveat 降级也算过） | ✅ S8 |
| **核⑨** 问事不出书：能力问 / 闲聊纯 answer 无 dock；无书 "start it" 不死路不起 run（出书门槛接住）；全程零 run | ✅ S9 |
| SSE 流式：answer 轮 delta 拼接 == 信封散文；draft 轮 echo deltas == intent.answer | ✅ S10 |
| 整条源规则活链（"给我的视频加中英双语字幕" → translate 单独成链 + derived 预览 + materialize_source 注入）+ materialize 三画像矩阵（media / stills / existing + 无画像拒绝 + select_clips 在场不注入，进程内） | ✅ S11 |
| merge_brief 来源优先级矩阵：user-stated 恒胜 / 重申恒胜 / inferred>default / None 永不落账 / 同秩最新胜 / asked 簿永不吃 LLM 提议 | ✅ S12 |
| ask 落库（chat_intent agent ask 提案 → dock 选项问） | ⚠️ 无确定性 scenario（ask 提案靠 LLM 触发，只有人工走查） |
| translate_clip / dub_clip chat 派发 | ❌ 待补（烧声纹/渲染管线，登记为已知空白） |

**随 C4 浓缩退役的专项断言**（机制全部现役，转人工走查；回归需求出现时在对应 story 补拍，不重建碎片）：贴文升格 transcript 资产（旧 S12/S14）、422 矩阵与 count 边界（旧 S11/S29/S35）、recipe 模板原文逐字（旧 S5，同径覆盖归新 S1）、附件持久化与替身行（旧 S30；attachment-only 不答 checkpoint 的拍已并入 S6d）、chat_intent 实分派 task_list/edit_ops（旧 S31/S32）、进度与元信息 answer 形态（旧 S33/S34）、焦点注入（旧 S35）、字幕归类话术（旧 S43，整条源规则归 S11）、copy-writer 软信号与素材引导 answer（旧 S13/S48，裁决单点 = 出书门槛）、checkpoint 过期 TTL 扫描（旧 S39）、多 run supersede 级联（旧 S38，supersede 主径归 S5）、task_book bail+reopen 与 autonomy 透传（旧 S23/S24）、空项目可见性（旧 S8）、checkpoint 答案审查批次（旧 S46/S47 早随机制退役）。

---

## 7. 登记纪律

- 新 skill/op/问题形态落地时：更新 §2 分类（若新类）、§3 矩阵、§6 矩阵。
- 发现用户话术走错路：先登记 §5（含重现话术），再谈修。
- 本表只登记"用户→路由"映射与状态；机制怎么实现看 `CHAT_ARCHITECTURE.md`，为什么这么设计看 `tasks/done/intent-ask-primitive.md` 与各 ADR。
