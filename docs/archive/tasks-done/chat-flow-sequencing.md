# 对话流时序与取证批（chat flow sequencing batch）

> 状态：待施工（2026-09-04 立项，用户拍板「全动」）。
> 驱动：同日产品试用逮到的六个流程级缺陷，全部已取证定位（本简报 §2 含 file:line 与证据，执行者无需重新排查）。
> 先读：仓库根 `CLAUDE.md`、`docs/CHAT_ARCHITECTURE.md`（§3.1 book path / §6 上下文 / §8.5 提问机器）、`docs/DECISIONS.md` ADR-053（形态律）与 ADR-054（任务书密度律）、`docs/PROGRESS.md` 2026-09-04 各行（同日已落的相关拍板）。

## 1. 问题陈述（用户实测原话提炼）

英文 UI、中文人设、裸愿望 "I want a social post." 全旅程：

1. **选项点选后停滞**：点选项后整个提问卡停着等 loading，消息流里什么都没有。
2. **时序倒置**：随后发 "you can start"，上一轮 echo（"Got it — a LinkedIn post…"）显示在 thinking **下面**。
3. **Thinking 静态无相位**：从发送到画布出现全程一句 "Thinking…"，无「正在理解 / 正在创建 workflow」等相位；画布转场近乎瞬移。
4. **历史里 echo 消失**：展开历史（刷新同构）后，"Got it…" 整条消息不见了；run 卡三行冗余（"分析素材 57s" 组头 / "Analyzing your uploads… 56s" 状态行 / "◐ 分析素材" 节点行说的是同一节点）；步骤清单无法折叠。
5. **一个 social post 冒出七大步**：preprocess / persona_bootstrap / understand / interrupt / plan / write_post / verify 全部列进清单；且 preprocess 卡死 12m41s 一动不动。

## 2. 取证结论（根因链，全部实证）

### 2.1 总根一：SSE 传输漏 `Accept-Language`（**已修，工作树未提交**）

`apps/web/src/lib/chat-stream.ts` 用 `@microsoft/fetch-event-source` 直连 `POST /chat`，绕过了 `api.ts:apiFetch` 的 `Accept-Language: i18n.language` 注入（api.ts:44-48）——浏览器默认 zh-CN 长驱直入：`run.context.ui_language=zh`（DB 实证）、步骤名中文、画布 "1 LinkedIn 帖子 · 中文"、言语中文。**已在 chat-stream.ts headers 补注入**（含注释）。后端侧同日已落言语语言律（`chat/intent.py:_speech_language_line` 注入两相位装配 + `intent_router.j2` `speech_language` 块 + `prompts.py` 两个 system 头术语定义与策略②翻译条款）——本批不要动这层。

### 2.2 总根二：薄书 echo 没有消息实体（问题 2 + 问题 4 消失，同一个根）

- task_book 助手行的 `content` 持久化的是**机器摘要行**（`apps/api/app/chat/service.py:907`：`content = f"Plan ready for confirmation: {_task_book_summary(...)}"`，DB 实证 `"Plan ready for confirmation: post(zh)"`）。
- LLM echo 散文只存在 `pending_brief.intent.answer`（start 即清空——S1 剧本断言 `pending_brief cleared on start`），**没有消息行**。
- 前端唯一渲染座 = `ChatDock.tsx:2500-2511` planCard 读 `intent.answer ?? planProseSingle`；内联锚 `planCardInline`（:2845-2854）**只在流式 book 回合生效**（`m.id === liveBookMessageId`）；answer POST 的 follow_up 不走流式（:2167 `void handleAssistantMessage(...)`）→ echo 钉在最底 → 用户再发一条就视觉倒置（问题 2）。
- `handleAssistantMessage`（:1786-1838）：docking task_book → `setPendingQuestion` + `await fetchPendingBrief()` → `return`，**echo 从不 push 成消息**。
- 恢复（:1279-1294）：带 `question` 的行折叠成 QA 归档块（`content: ""`）→ echo 无处可渲染（问题 4 消失）。
- task_book QA 归档的确认行文案 = `generationOverlay.confirmQuestion`（"Save & generate?"，en.ts:1242；组装点执行时溯源确认）。

### 2.3 问题 1：选项作答 await 全链

`ChatDock.tsx:2152-2171` `handleOptionAnswer`：await 整个 answer POST（含一整轮 book-path LLM 续写）→ 才归档 QA → 才渲染 follow_up；从不置 `chatBusy`（thinking 行不显示）；`handleSend`（:2236）只挡 `chatBusy || isStarting`，**作答飞行中发送无任何守卫**。freeform 铅笔路已是乐观范式（乐观气泡 + sendChat + rollbackId），选项路未对齐。

### 2.4 问题 3：thinking 相位通道存在但被丢弃

- SSE 本有 `assistant.thinking` 帧（`apps/api/app/chat/routes.py:131-142`），但载荷恒 `"{}"`（纯保活）。
- 前端 `chat-stream.ts` 的调用点（ChatDock.tsx:1946-1949）**只传 `onDelta`，从不传 `onThinking`**；`ThinkingRow`（:862-876）= 静态 shimmer（`chat.thinking`）。

### 2.5 问题 4（冗余/折叠）+ 问题 5（七大步）：RunTaskList 显示层

`apps/web/src/components/chat/RunTaskList.tsx`：

- :113-123 组头 = `running?.summary || title` + 总时长；:126-134 shimmer 状态行 = `step.stage` → `results.stepper.${stage}` locale 映射，fallback `chat.stepKinds.${kind}`；:138-142 节点行 `TaskRow`。首节点运行时三行同指一个节点 = 三重冗余。
- `chat.stepKinds.preprocess` = "Analyzing your uploads…"（en.ts:1132）**零上传时不实**（no-material lift 没改文案）；节点名服务端按 `ui_language` 烘焙、状态行前端 locale——一张卡两种语言（zh 根已修，文案诚实性待修）。
- RunTaskList **无折叠钮**；用户记得的折叠是 dock 层 `RunStatusRow`（RunTaskList.tsx:191-229，ChatDock.tsx:3190-3205 接线，点开历史）；历史打开后清单恒展开。
- 七大步 = 写手链固定 prelude（preprocess/persona_bootstrap/understand/plan + interrupt）全列。实测无素材模式下 persona_bootstrap 75ms / understand 89ms / interrupt 37ms / plan 35ms——近瞬时代码节点，列为七行清单纯属仪式感。薄链（copy-writer-only 无素材）按形态律同原则应减重显示。

### 2.6 问题 5（卡死）：worker 无围栏 + 无运行期收割（**环境已修，代码待办**）

- 当日机器上有**两个 worker**：当前 dev 会话进程 + 两天前孤儿进程（09-02 旧代码）。worker 设计假设单实例（`apps/api/app/pipeline/jobs.py:162` `reap_stale` docstring 明说 "In dev there is a single worker"），SKIP LOCKED 让孤儿抢走 preprocess 后事件循环死亡（远古无超时调用挂着），认领不执行。
- `orchestrator.py:912` `execute_step` 对 `executor.run(...)` **零超时包裹**；`reap_stale` **只在 worker 启动时跑一次**（`worker.py:99-101`），`_tick` 无周期收割 → 节点 running 到永远。
- 铁证：节点重置回 pending 后，活 worker **125ms** 跑完 preprocess（无素材纯写手链 = 纯 DB 读，`node_runners.py:130-168`）——12m41s 全空转。
- **已做（环境）**：杀孤儿进程、重置卡死节点、run 已复活流完。**代码待办即本批工作项 D**。
- 另注意：MiniMax 客户端自带 120-180s httpx 超时（`providers/llm/minimax.py`），所以围栏阈值按节点级另设，不依赖客户端。

### 2.7 连带登记（**本批不修**）

内容语言被中文人设 + 中文主题槽值拖成 `post(zh)`（规则本是"默认跟 prompt 语言"）。言语语言律只治言语不治产物；"人设语言 ≠ 内容默认语言"护栏 = 独立后续项，本批只在 PROGRESS 登记一句，不动任务参数规则。

## 3. 工作项

### A. echo 实体化（治问题 2 倒置 + 问题 4 消失）

A1. **服务端**：`service.py:907` 附近——task_book dock 行的 `content` 改存**本轮 echo 散文**（book path 的 answer 散文；选项问行的 content 本来就是问题文本，不动）。先 grep 确认 "Plan ready for confirmation" 无前端消费再改；机器摘要如仍有内部消费就挪进 question payload，不进 content。
A2. **前端 live**：`handleAssistantMessage` docking task_book 时，先把 echo push 成**时间序正确的流内消息**（role=assistant, content=message.content），再 dock——除非本回合已有流式气泡承载同一 echo（`messages.some(m => m.streaming)` / 既有 liveBubblePresent 等价判定）。planCard 的 echo 渲染座（:2500-2511 单任务分支与 :2523-2528 多任务卡内 echo 段）加去重门，已有消息实体则不重渲。
A3. **前端恢复**：恢复循环（:1279-1294）对已答 task_book 行 = **先 push 散文消息（m.content），再 push QA 归档块**（QA 确认行维持现行 `generationOverlay.confirmQuestion` 组装）；已答选项问行不变（content = 问题文本折叠进 QA）。
A4. 密度律不变：薄书仍无卡无 pill（ADR-054）——echo 实体化是**消息化**，不是恢复评审卡。

### B. 选项作答乐观化（治问题 1）

`handleOptionAnswer` 改乐观范式，对齐 freeform 路：

- 点中立即：行内 spinner 保留（点击即时反馈，既有）+ **乐观 QA 入流**（question = `pendingQuestion.content`，answer = 点中 option 的 label，复用 `answeredQuestionText` 的 option 分支语义）+ `setPendingQuestion(null)` + `setChatBusy(true)`（thinking 行入场）。
- POST 成功：用服务端 `answered_question` 替换乐观 QA（真值裁决）+ `handleAssistantMessage(follow_up)`。
- POST 失败：摘乐观 QA、重新 dock 问题、（apiFetch 自动 toast）——复用 freeform 路既有 rollbackId 模式。
- `handleSend` / `handleFreeformAnswer` 守卫加 `answering`（与 chatBusy 并列），堵死作答飞行中并发回合（问题 2 的并发面）。

### C. thinking 相位（治问题 3）

- 服务端：book 回合在真实相位切换点发带标签的 `assistant.thinking` 帧——锚点：`routes.py` 的 `on_delta`/`on_reasoning` 已有发帧通道；相位源在 `service.py:execute_chat_turn`（进入 intent router = 理解中；start 裁决执行 create_run = 创建 workflow）。**只标真实相位，2~3 个封顶**，禁虚构粒度。载荷形如 `{"phase": "understanding" | "creating_run"}`。
- 前端：`chat-stream.ts` `onThinking` 签名带载荷；ChatDock 调用点传入并置 `thinkingLabel` state；`ThinkingRow` 渲染相位文案（i18n 双语新键，默认回退 `chat.thinking`）。`prefers-reduced-motion` 不动。
- 画布转场节奏（"瞬移"感）：顺手把首 run 到达的形态机转场（ADR-051 条款 7 的 grid-rows 1fr→0fr + canvas fade）时长/缓动调到可感知——一个节奏常数的事，禁引入新动画系统。

### D. worker 围栏与周期收割（治问题 5 卡死）

D1. **节点超时围栏**：`execute_step` 的 `executor.run(...)` 包 `asyncio.wait_for`，超时阈值 600s（D9 保险丝先例）；TimeoutError 走既有异常路径（错误落节点行 + 下游级联 skip），禁静默。核实要点：runtime_fanout 节点的 `executor.run` 立即返回（渲染链自持终态），围栏不覆盖渲染/ASR 本体；若有节点合法超过 600s 在 executor.run 内，先报告再定值。
D2. **周期收割（按年龄）**：`reap_stale(db, older_than_seconds: float | None = None)`——启动调用 None = 现行全量语义不变；`_tick` 每轮以阈值调用（UPDATE … WHERE status='running' AND started_at < now()-阈值，三表同理）。阈值纪律：节点 900s（健康 LLM 节点 ≤180s，余量充足）；渲染/ASR 资产耗时长，**先查清 `asset_processing` / 渲染的最长合法耗时再定**，不确定就只先收割节点，资产/渲染留启动收割并在简报记录决定。
D3. 多 worker 共存防御不进本批（单实例假设是部署纪律）；但 `reap_stale` docstring 的 "single worker" 假设注一句：孤儿进程会让启动收割误杀同伴的活节点——周期收割按年龄免疫此坑，这正是 D2 的另一重价值。

## 4. 验收标准（用户自跑验证）

1. 选项点选：QA 瞬时入流 + thinking 行紧跟；卡不停顿；断网/500 时乐观 QA 回滚、问题重新 dock。
2. 时序：选项作答后直接发 "you can start"，上轮 echo 恒在 "you can start" **上方**；刷新后顺序不变。
3. 历史：薄书 echo 散文在恢复历史中**存在**（流内消息），QA 归档块随后；任何界面不再出现 "Plan ready for confirmation: …" 机器行。
4. Thinking：start 回合可见相位文案变化（至少 理解中 → 创建 workflow 两相）；无相位帧时回退 "Thinking…"。
5. RunTaskList：单节点不再三行冗余；组头恒为计划标题；运行节点行的副标题 = 当前状态；零上传时 preprocess 文案诚实；薄链显示 = prelude 组行（可折叠）+ 产物行，不再七行平铺。
6. Worker：手工把一个节点摁死在 running（如 DB 直改），围栏/周期收割能在阈值内将其失败化或重置——验证后清理现场（项目纪律）。
7. `chat_scenarios.py` S1 全绿（用户跑）；tsc 干净（用户跑）；en.ts/zh.ts 新键双语齐全且 `zh: Resources` 满足。

## 5. Prohibited Behaviors

- 禁第二意图入口 / 禁 overlay 路由概念回归 / 禁为薄书恢复确认 pill（ADR-054 不动）。
- 结算语义一字不动：autoResume（字母/数字/label 命中）/ slot 握手 / `pending_disposition` 三态 / answer 端点判别联合 **kind 守卫**（"kind 外字段 422"——`OptionAnswerRequest` 无 `.text`，09-04 已炸过一次）。
- 形态律不动（ADR-053 R1）：选项问阻塞 morph 保留；铅笔行保持 item 解剖；问题卡无 default_path 行。
- UI 律：`rounded-full` 四例外外禁；禁手写 SVG icon（lucide 唯一）；禁硬编码色值；卡面禁可见描边（`ring-foreground/10` 上限）；**滚动容器内禁 shadow/glow**（两侧被 scroller 裁剪——对比用 `bg-muted/50` 系）；变体配对律（`dark:bg-*` 必须显式 `dark:hover:*`，`bg-transparent` 必须 `dark:bg-transparent`）；base-ui 用 `render` prop 不用 `asChild`。
- i18n：先 en.ts 后 zh.ts（`zh: Resources` 类型兜底）；组件内 `useTranslation`，禁硬编码字符串。
- 后端：禁 FastAPI BackgroundTasks；重活一律 Postgres 队列 + worker；禁跨模块直调 service 执行重活。
- 禁引入新动画系统 / 新状态管理 / 新依赖（fetch-event-source 已在）。
- 文档治理：过时内容直接删除换现在时；PROGRESS 新行落本批（含 2.7 连带登记一句）；echo 消息化若在 ADR-054 语义上有增补，同批改 ADR-054 条款并注日期；RunTaskList 显示律若成文，落 CHAT_ARCH §8.5 附近一节。

## 6. 环境与工作树状态（执行前必读）

- 仓库 `/Users/sylas/repurposer`；API = `apps/api`（uvicorn --reload :8000 在跑），worker = `python -m app.worker`（在跑），dev DB = Postgres localhost:5432/repurposer。改 pipeline 代码**提醒用户重启 worker**（worker 不吃 reload）。
- **工作树有同日未提交改动，在其上继续，禁 revert**：言语语言律三件套（intent.py/j2/prompts.py）、chat-stream.ts 的 Accept-Language、service.py answer kind 守卫、prompts.py 选项数 3/2 + 薄书 CTA 去魔法词、`planProseSingle` 双语、QuestionDock 阻塞形态 + 点中行 loading 座、chat_scenarios.py S1 契约拍③、当日 PROGRESS/DECISIONS/CHAT_ARCH 各行。
- Pyright 在 IDE 里报的全仓库 "Alternative syntax for unions requires Python 3.10" / 导入解析失败 = **解释器指错的既有噪音**（项目用 uv venv 3.12），忽略。
- 剧本：`cd apps/api && uv run python scripts/chat_scenarios.py --only S1`（真 LLM，需要 :8000 + worker + DB）。
- 验证纪律：**compileall / tsc / 剧本复跑 / 产品试用全部归用户自跑**；执行者只做代码层实现与 review，交付报告标「未跑验证」；Python 改动可用 ast.parse 做最低语法自检（先例允许）。

## 7. 交付物清单（DoD）

- [ ] A1~A4 echo 实体化（服务端 content + 前端 live/恢复两路）
- [ ] B 选项作答乐观化 + 发送守卫
- [ ] C thinking 相位（服务端标签帧 + 前端接线 + 双语键 + 转场节奏常数）
- [ ] D1 节点超时围栏 + D2 周期年龄收割 + D3 docstring 注
- [ ] RunTaskList 显示层（组头=标题 / 状态行并入节点行 / 诚实 preprocess 文案 / prelude 组折叠）——挂在工作项 C 之外的独立前端改动
- [ ] i18n 新键 en+zh
- [ ] PROGRESS 新行 + 涉及律条的 ADR/CHAT_ARCH 同批
- [ ] 交付报告（改动清单 + 每验收项的验证指引 + 「未跑验证」声明）
