# 去方言批：提问机器命名统一 + 形态律 + 剧本测试浓缩

> Status: 已拍板（2026-09-03），待施工。
> 本文是这批施工的**唯一任务书**：前因后果 / 批次计划 / 禁令 / 验收全在此。施工者零上下文起手时，按 §0 的顺序读文档。
> 验收分工按仓库惯例：施工侧做到代码层全绿（py_compile / tsc / import / 冷启动 `assert_runners_registered`），**剧本测试运行与产品试用归用户**。

## 0. 施工者先读（按序）

1. 本简报（唯一任务书）
2. `docs/README.md`——docs 索引与治理原则
3. `docs/CHAT_ARCHITECTURE.md`——chat 机器规格。**§8.5（QuestionDock 与 question/answer）是 C3 的直改对象**：阻塞 morph 的规格出处（"2026-08-31 形态切换"条）、autoResume 映射规则、checkpoint 形态、task_book 形态都在此；本批落地后该节同步改写（见 C3「规格同步」）
4. `docs/DIALOG_WORKFLOW.md`——对话→生产概念架构（ADR-052，B1~B4 已落；§6 不变量含「提问机器与停靠法则」一行，形态律落地后同步修订）
5. `docs/AGENT_ARCHITECTURE.md`——四层工程地图（注意：其中 §10「剧本 harness」等措辞是**本批要改的旧方言**，以本简报为准）
6. `docs/NAMING.md`——命名判例（N-33 harness 两义、N-40 interrupt；本批将结案 N-33 并追加新判例）
7. `docs/DECISIONS.md`——现行 ADR 集（ADR-051 dock 形态条款、ADR-052；形态律与插话支持的判词随 C3 登记于此）
8. `CLAUDE.md`——项目协作规范（前端 base-ui / i18n / 主题 / 队列纪律）
9. `docs/INTENT_COVERAGE.md`——意图覆盖矩阵（S 编号引用在 C4 同批更新）
10. `docs/PROGRESS.md`——排期唯一事实源（C1 文档 commit 记行处）

按需查阅：`docs/MODULE_ARCHITECTURE.md`（表归属：messages 归 Agent Interface / projects 归 Pipeline）；`docs/RECIPES.md` §4.7（caption mode 上下文）。

冲突裁决：文档/代码与本简报冲突时，以本简报为准；简报与代码现状冲突时，**停下报告，不自行发挥**。

## 1. 前因后果

### 1.1 触发：一次产品试用（2026-09-03）

用户点 post 配方卡（预填模板原文 = "I want a social post."）发出首条消息，得到：一个**只有自由文本框、没有选项**的问题卡（"What should the post be about?"），且该卡以**阻塞 morph** 形态没收了整个输入区（输入行与免责行隐藏，只剩问题 pill）。

机制上这是 B2 的验收场景按设计发生（裸愿望 → router 判 ask + slot=topic → dock 提问机器，带 default_path 牙齿），但试用暴露了四层问题。

### 1.2 四个发现（全部经代码阅读证实）

**发现①：options 被装配层饿死（bug）。** 提问策略②要求选项「2-4 个一词可答的具体值，来源 = persona / 项目上下文」，但 `_assemble_book_turn`（`app/chat/intent.py`）与 `app/prompts/intent_router.j2` 的装配里**根本没有 persona 块**——router 被要求从一个它看不见的源头取材，裸愿望 + 空账本 + 新项目时只能按豁免条款（"empty options only when no sensible options exist"）交白卷。渲染层与传输层无辜（`QuestionDock.tsx` 有 options 就渲染；`service.py` 原样透传）；caption mode 问 / direction interrupt / chat shape C 三条构造侧带 options 的通路证明 options 渲染是活路径。**断的只有 book-path ask 一条。**

**发现②：单个轻问题用了全场最重的形态（UX 倒挂）。** `ChatDock.tsx` 自己写着：task_book（最重的决策）= 非阻塞 pill（"the input group stays live below it"）；单个 choice 问题（最轻的决策）= 唯一的阻塞 morph（"the input row and the disclaimer hide"）。且与提问策略③自相矛盾：策略说"每个问题都可安全跳过"，阻塞 morph 下跳过必须做显式 bail 手势，挂起期间用户除答题外什么都不能说。世界级 agent chat（ChatGPT/Claude/Gemini/Devin/v0/Perplexity）的澄清问全走对话消息或消息+chips，**输入框从不消失**。

**发现③：一套机器，四套方言（过度命名，非过度设计）。** 提问机器只有一台（`messages` 表一行两态：question 载荷 + answer 载荷），但各层长了不同词域：
- schemas 层叫 **Ask***（`AskPayload`/`AskProposal`/`AskOption`，~48 处）
- DB/service/前端层叫 **question***（`question` 列/`_dock_question`/`QuestionDock`/`pendingQuestion`）
- 前端归档层叫 **Qa***（`QaPair`/`QaAnswer`/`qaAnswerText`，~18 处）
- 文档注释叫 **ask primitive**（~12 处）与**提问机器**（~16 处）
- 枚举层有同义对：kind `choice` vs answer kind `option`
- **测试脚本叫「剧本 harness」**（NAMING N-33 登记了 harness 两义并存，当年是"登记歧义"而非杀歧义 + "不是测试套件"的防御性命名——API 测试套件已删多年，防御早到期）

**发现④：剧本脚本随架构多轮迭代已大面积过时，且概念过载。** `apps/api/scripts/chat_scenarios.py`（S1–S53，S22 退役留空）历经 outputs-derive（ADR-043）、interrupt 更名（N-40）、brief 账本（ADR-052 B2）、预填评审卡（B3）、research（B4）多次架构迭代，多处断言旧形态/旧行为；它就是一个测试脚本，不应背负任何概念名。

**附带发现：`apps/web/src/components/chat/OpsCard.tsx` 是死代码**（全 src 无 import，仅自引用），随 C1 删除。

### 1.3 拍板（2026-09-03，用户连拍四条）

- **R1 形态律**：ask 保留为 router 动作动词。**纯文字问（options 空）= 普通对话消息**（作答 = 普通回复）；**选项问（options 非空）= 非阻塞 pill 停靠在活的输入框上方**（task_book pill 同款解剖），答完显示归档组件。**dock 形态只跟 options 走，不再有第三个形态判别维度。**
- **R2 插话支持**：任何待决问题期间用户可以随时说一句无关的话。系统判"这句答没答"：答了 → 正常结算（slot 回填 / interrupt 续跑）；**没答 → 正常回答这句话本身，回复末尾附带未决问题的提醒（代码拼装固定句，携带原问题 + default path），问题保持 pending 诚实挂着**——不强制、不掩盖、不把无关消息冒充成答案。明说跳过 = 说"跳过"或点 ×（pill 的 bail）。
- **R3 去方言**：词根统一为 **question / answer**；**ask 只留 router action 动词一个座位**；option 管选项。kind 收敛为 `{task_book, question}`（全系统对 kind 的语义分支只有"是不是任务书"一处，其余结算全走载荷握手字段：`workflow_run_id`→续跑 / `slot`→回填 / `caption_mode_` 前缀→恢复模式）。**禁造新概念词**——clarify / archive / receipt / eval / primitive 一律不进词汇表（它们在世界级产品里不存在，造了就是下一代方言）。
- **R4 剧本浓缩**：剧本脚本就是测试脚本（叫**剧本测试**，harness 一词回归单义 = 四层地图的 Agent 漏斗层，NAMING N-33 结案）。浓缩到**只保核心用户 story**。

## 2. 去方言终态（改名唯一事实表）

| 层 | 现名 | 新名 |
|---|---|---|
| schemas | `AskPayload` | `QuestionPayload` |
| schemas | `AskProposal` | `QuestionProposal`（其 `kind` 字段经 grep 确认无读者后**直接删除**——LLM 永远只产普通问题） |
| schemas | `AskOption` | `Option` |
| schemas | kind 枚举 `["task_book","choice","confirm"]` | `["task_book","question"]`，默认 `"question"`；`confirm` 空座删除；旧行 `"choice"` 走 `@model_validator` 读容忍升级为 `"question"` |
| 前端 | `QaAnswer`（QaPair.tsx） | `QuestionAnswer` |
| 前端 | `QaPair` 组件 | `AnsweredQuestion` |
| 前端 | `qaAnswerText` / `pushQaArchive` | `answeredQuestionText` / `pushAnsweredQuestion`（施工时按实际签名对齐） |
| 注释/文档 | "ask primitive" ×12 | "提问机器 / the question machine" |
| 注释/文档 | "剧本 harness / test harness" | "剧本测试" |
| NAMING.md | :44 harness 限定注 / :84 剧本验收行 / N-33 两义判例 | :44 限定注删；:84 改「剧本测试 = `chat_scenarios.py`」（"无测试套件"纪律注摘出保留）；**N-33 结案删除**（历史在 git），新判例登记「harness 单义 = 调用面 Agent 漏斗」+ 本轮全部改名判例（N-48 起） |

答案 kind（`option`/`freeform`/`bail`/`start`）不动。`interrupt`（N-40）不动——pipeline 节点层概念，只是经提问机器发问。`task_book` 作为 kind 值不动。

## 3. 批次计划

每批 commit 级自绿（py_compile + tsc + import + 冷启动 `assert_runners_registered`），每个 commit 可独立引导。工期为指示性估算（velocity 80%）。

### C1 去方言命名批（约 1 天，零行为变化）

- §2 全表改名 + kind 收敛 + 读容忍 + OpsCard.tsx 删除。
- Commit 切分：① schemas/service 层 ② 前端层 ③ 文档 + NAMING 判例 + PROGRESS 记行。每个 commit 冷启动绿。
- wire 安全：改名只动类名/枚举默认值，载荷字段名（kind/options/default_path/slot/brief…）不变；前后端同仓同部署，枚举值切换同批原了。
- LLM 面向：`chat/prompts.py` 与 `intent_router.j2` 中 "kind 永远是 'choice'" 类措辞同步为 "question"；LLM 按旧习输出 `"choice"` 由读容忍兜住。
- 文档清扫面（"剧本 harness"→"剧本测试"、"ask primitive"→"提问机器"）：`docs/AGENT_ARCHITECTURE.md`（§10 等）、`docs/INTENT_COVERAGE.md`（~20 处）、`docs/CHAT_ARCHITECTURE.md`、`docs/DIALOG_WORKFLOW.md`、`docs/MODULE_ARCHITECTURE.md`、`docs/PROGRESS.md`、`docs/NAMING.md`、`docs/tasks/` 现役简报。

### C2 options 装配缺口（约 0.5 天，小修）

- `_assemble_book_turn` 增加 persona 块：从 `project.persona_id` / `pending_brief.persona_id` 解析 persona，按 Memory 单向注入规则（消费者拉取）把**受众 + 身份/领域摘要**注入装配；`intent_router.j2` 加 persona block（有则渲染）。
- 具体注入字段施工时从 `app/models/tables.py` 的 personas 列现状取（audience / guidelines / 身份卡），**注入量克制**——够提问策略②取材即可，不把整个 persona 倒进去。
- 效果断言（供 C4 剧本）：有 persona 时裸愿望 → 主题问**带 2-4 个一词选项**；无 persona / 无可取材时 options 空 = 合法（策略②豁免条款）。

### C3 形态律 + 插话支持（约 2-3 天，行为批，本批的重心）

**形态律落地（R1）：**
- `AskPayload`（新 `QuestionPayload`）的渲染分流：`options` 空 → 普通 assistant 消息（问题文本即 content，停留消息流）；`options` 非空 → 非阻塞 question pill 停靠在**活的输入框上方**（复用 task_book pill 的解剖：pill 在上、输入组常驻）。
- **拆除阻塞 morph**：`ChatDock.tsx` 约 :3044 的 "the dock MORPHS (input row and the disclaimer hide)" 整形态退役。
- 归档渲染规则：options 非空的问题答完 → `AnsweredQuestion` 收据入流；options 空的文字问答 = 普通消息双向即收据，**不渲染归档组件**。
- 五个 choice 来源逐一过：book-path ask（slot 握手）/ topic gate backstop（options=[] 是设计 → 自然落对话形态）/ caption mode 问（options → pill）/ direction interrupt（options → pill，run 挂起）/ chat shape C（options → pill）。

**插话支持（R2）：**
- 判定归 LLM、结算归代码：book path 每轮 router 看账本+recent+待决问题（待决问题显式进 router 上下文）；**router 提议了该 slot 的 user-stated 值 = 答了** → 代码结算 pending 行（answer=freeform）并照常经 merge_brief 回填；**未提议 = 没答** → 本轮按其自身 verdict 正常处理，pending 行保持，回复末尾由**代码拼装提醒尾**（固定句，双语，含原问题 + default path——code-forced text 先例，不借 LLM 之声）。
- chat path（post-run）：`chat_intent` 上下文本已携带 pending question（`prompts.py` "act on the question + answer together" 规则），补另一半：判没答则不结算、正常回答 + 同样的提醒尾。
- **杀掉掩盖本体**：autoResume「任意消息强记为 freeform 答案」的映射退役——只有判为作答的消息才结算 pending 行。
- interrupt（run 挂起）问同样可插话：插话正常回答 + 提醒，run 保持 parked；× bail 语义不变（pill 保留 × 作为明说跳过的诚实出口；文字问无 ×，跳过 = 不理或明说）。
- `expire_stale_interrupts` TTL auto-answer 不变。
- i18n：提醒尾等全部新文案 en.ts 先行、zh.ts 镜像（`Resources` 类型 catch）。

**两处已核的规格裁决（写死，施工不重新发明）：**
- autoResume 现 spec（CHAT_ARCH §8.5）本有「未命中选项且 allow_freeform=false → 按新 intent 处理、问题保持待决」分支——**那就是插话支持的半个座位**。本批把它泛化到 allow_freeform=true 的问题并加提醒尾；要杀的只是「allow_freeform=true 时任意文本强记为 freeform 答案」那一半。字母/序号/原文命中的确定性映射保留（那本来就是无歧义作答）。
- × 的去留：CHAT_ARCH §8.5 有「非阻塞提问不配负向动作」条款（task_book Cancel 退役的出处）。choice 转非阻塞后该条款与 R2 的 × 保留相冲突——**裁决：pill 的 × 保留，语义 = 明说跳过并走 default path（bail），不是 Cancel 复活**；条款措辞随 §8.5 改写同步修订。

**规格同步（随 C3 文档 commit 一并做）：**
- `CHAT_ARCHITECTURE.md` §8.5 改写：删「2026-08-31 形态切换」（阻塞 morph）条款；停靠法则改写为「文字问对话形态 / 选项问非阻塞 pill / 归档组件只对选项问」；autoResume 条款按新结算语义改写；「非阻塞提问不配负向动作」条款按上面 × 的裁决修订。
- `DIALOG_WORKFLOW.md` §6 不变量行「提问机器与停靠法则（CHAT_ARCH §8.5）」措辞修订。
- `DECISIONS.md` 登记形态律 + 插话支持判词（按现行编号追加新 ADR）。

### C4 剧本测试浓缩（约 1-2 天，依赖 C3 落地后的终态行为）

对 `apps/api/scripts/chat_scenarios.py` 的预期动作，按序：

1. **正名**：文件头注释改写——这是剧本测试脚本（不是 harness）。
2. **基线盘点**：通读现存全部剧本（S1–S53，S22 空），逐条标 keep / rewrite / delete + 一行理由（理由写进 commit message 或剧本行注释）。先确认哪些对当前 main 已红/已过时——删除优先于改写。
3. **删除**：断言旧形态/旧语法/旧行为者（阻塞 morph、autoResume 强制映射、slots 语法遗留、退役概念、被 C3 改写的 S51/S52 旧断言、S13/S48 已被门槛吸收的中间态）。
4. **浓缩重写**：只保核心用户 story，每条 = 一个完整用户故事（不是机制碎片）。建议清单（施工时可并拆，总量目标 8–12 条）：
   - 核① 裸愿望 → 文字主题问 → 作答回填 → 评审卡（槽位行渲染）→ start → run 起步
   - 核② 裸愿望 → 跳过 → draft-from-persona 书 + 默认路径声明
   - 核③ 插话未答 → 正常回答 + 提醒尾 + 问题保持 pending → 下轮作答 → 回填
   - 核④ 带素材全链：任务书 → 确认 → run 完成 → 产物落库（估价三断言随此链：fold / 报价单调性 / repair 只一轮——原 S41/S42 保留并入）
   - 核⑤ chat 修订链：refine → chat 修订恒胜 / prior_intent 面板编辑存活
   - 核⑥ interrupt：三答法 + bail 级联 + 插话后续跑（期 4 家族浓缩为一条）
   - 核⑦ caption mode：options pill → 答后双语参数落 run.context + AnsweredQuestion 收据
   - 核⑧ research 全链：活 DDG（网络全灭时 caveat 降级也算过）+ writer 收到 research brief
5. **重排编号连续**（S1…Sn；本次是大浓缩，不再沿用留空洞先例），`docs/INTENT_COVERAGE.md` 的 S 引用**同 commit** 全部对齐。
6. **验收**：浓缩后脚本对活 API 全绿（归用户跑；施工侧做到脚本可导入、断言与现状代码逐条对齐并如实报告未跑）。

## 4. Prohibited Behaviors

- **禁新方言词**：clarify / archive / receipt / eval / primitive 及任何自造概念词不入代码、不入文档。词汇只有：question / answer / ask（仅 action 动词）/ option / 提问机器 / 剧本测试。
- **C1 禁行为变化**（纯改名批）；每 commit 冷启动绿，不可拆的 commit 必须声明。
- **禁第二提问通道 / 第二意图面**（POST /chat 唯一）；禁平行映射表（提问机器只有一台）。
- **禁任何形式的阻塞式输入替换**（morph 永不再回来）；禁把未答消息强制结算为答案。
- **禁 LLM 簿记**：asked roll 永远代码持有；material_state 永远代码钢印。
- **禁复活"测试套件"概念**：剧本测试就是 scripts/ 下的测试脚本，不配概念名。
- **禁复活 OpsCard**（死代码删了就是删了）。
- 改 pipeline 代码必重启常驻 worker（施工提醒；worker 抢跑坑在案）。
- 新文案一律 en.ts → zh.ts 镜像；组件遵守 CLAUDE.md 全部 UI 纪律（base-ui `render` prop、禁 `asChild`、lucide 唯一图标源、overlay-surface 浮层配方等）。

## 5. 验收

| 批 | 验收 |
|---|---|
| C1 | 三 commit 各自冷启动绿；全库 grep 无 `AskPayload`/`AskProposal`/`AskOption`/`QaPair`/`QaAnswer`/"ask primitive"/"剧本 harness" 残留；NAMING 新判例落档 |
| C2 | 代码层：persona 块进装配与 j2；有 persona 时主题问带选项的断言路径可供 C4 剧本使用 |
| C3 | 代码层：阻塞 morph 零残留；五种问题来源形态分流正确；插话未答 → 回答+提醒尾+pending 保持；作答 → 正常结算；× bail 不变；tsc 绿 |
| C4 | 浓缩后剧本集（8–12 条核心 story）编号连续、INTENT_COVERAGE 对齐；脚本可导入、断言与代码逐条对齐；**运行全绿归用户** |

## 6. Critical files

- `apps/api/app/models/schemas.py`——AskPayload/AskProposal/AskOption/BriefLedger/InferredIntent/PendingBrief（C1 主战场）
- `apps/api/app/chat/service.py`——`_book_turn` / `_propose_turn` / `_dock_question` / `latest_pending_question` / `_settle_open_questions` / `answer_question` / `sync_task_book_question` / `dock_interrupt_question` / `_topic_gate_question` / `_build_caption_mode_question` / `merge_brief`（C3 主战场）
- `apps/api/app/chat/intent.py` + `apps/api/app/prompts/intent_router.j2` + `apps/api/app/chat/prompts.py`——装配与 prompt（C2 主战场）
- `apps/web/src/components/chat/ChatDock.tsx`——OverlayMessage/QuestionPayload/阻塞 morph/pill 解剖（C1+C3 前端主战场）
- `apps/web/src/components/chat/QuestionDock.tsx` / `QaPair.tsx`（→ AnsweredQuestion）/ `OpsCard.tsx`（删）
- `apps/web/src/lib/i18n/locales/en.ts` / `zh.ts`
- `apps/api/scripts/chat_scenarios.py`（C4 唯一战场）
- `docs/NAMING.md` / `docs/INTENT_COVERAGE.md` / `docs/AGENT_ARCHITECTURE.md` / `docs/PROGRESS.md`
