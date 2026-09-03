# intent-surface-unification 实施简报——意图层单面化：chat 唯一入口

> Status: ✅ 已落地（2026-08-03 立项，2026-08-04 完成）：W1–W7 全部代码 + 文档归位；剧本测试 S1–S8 全绿（真实 LLM，形态级断言）。**施工中两处硬化**（剧本暴露，超简报原范围）：① `InferredIntent` 读容忍 `outputs: null`——LLM 在 start/answer verdict 时惯于把 slots 置 null，此前校验失败被静默降级成默认 generate 任务书；② `presented_plan` 注入——dock 中任务书的一行摘要进 PlanAgent 上下文，裸"开始吧"接模糊首轮的 start 判定从 2/3 误判 → 3/3 稳定。**留用户手测**：composer → 跳转 → overlay 首条消息自动发出 → 任务书 dock → 手编/refine/Start 全链路 + 刷新/跨设备 dock 重建。
> 依据：`docs/INTENT_COVERAGE.md`（现状矩阵）；`docs/CHAT_ARCHITECTURE.md`（task list 契约 / 提问机器）；`tasks/done/intent-ask-primitive.md`（G-1 start 路径）；`tasks/recipe-mention.md`（mention pin）
> 用户裁决（2026-08-03）：① **意图识别只有 chat 一个入口**——composer 点发送 = spinner 建空项目 → 跳转详情 → overlay chat 接管，composer 自身不做任何意图识别；② **任务书确认保留**——pending task_book 从"独立 confirm 相位"降级为"chat 里有一个待决任务书"的普通状态；③ 意图三层模型（L1 用户画像 / L2 补全意图 / L3 歧义澄清）中 **L1 后置**（随需求再做），本期夯实 L2+L3；④ 验收 = **后端剧本测试**（预设多轮对话、形态级断言），前端由用户手测；⑤ 风险清单全部处理（空项目垃圾 / 标题 / mention 时机 / Tour / 出生地校验 / 文档同步）
> 迁移：**零表迁移**——`project.pending_intent`、task_book question、`messages` 全部复用；仅 `ChatRequest` 加两个可选字段

## 0. Context

当前意图层是"两个半 agent"的分裂结构：`POST /projects/{id}/intent` 一套语义（ComposerIntentAgent 三动作 + pin-merge + reasons 推导）+ `POST /chat` 一套语义（ChatIntentAgent 四态）+ confirm 相位又借 `/intent` 做修订（累积 prompt 重推）。同一件事在两个入口各做一遍，IntentCoverage 矩阵要登记"四表面 × 五入口"。

统一后：**composer 退化为"新会话输入框"**（ChatGPT 首页模式），项目即会话；一个上下文装配点、一套裁决与兜底链。`start` 动作的调用点、recipe mention 的 pin 时机、refine 的 pin-merge，全部从 `/intent` 平移进 chat service 的 plan path。

## 1. 已核实的现状事实（读码确认，2026-08-03）

- `HomeComposer.handleGenerate`（HomeComposer.tsx:227-328）：建项目（title = prompt 前 15 字符 + "…"，聊天应用命名惯例）→ 上传素材（无文件时造 `prompt.txt` transcript asset）→ `POST /projects/{id}/intent` → `navigate(overlay: "intent")`。**只有 `/intent` 这一个调用需要摘除**，项目创建与素材上传原样保留。
- `POST /chat/infer-intent`（chat/routes.py:140）**无任何前端调用方**（grep 全仓确认），随本期一并退役。
- `/intent` 的核心逻辑全是可平移的纯函数/服务：`merge_explicit_slots`、`resolve_recipe_mentions`、reasons 推导（`language_default`/`outputs_default`/`clip_count_default`/`clips_without_media`）、`record_intent_turn`、`sync_task_book_question`、`has_renderable_media`——全部已在 `app/chat/service.py` 或可 import。
- G-1 start 路径已复用 run 唯一出生地：`/intent` 的 start 分支调 `answer_question(kind=start)`，`ChatResponse` 已带 `run_id` + `answered_question` 字段——**plan path 起 run 的响应零 schema 改动**。
- `chat()` 的 autoResume 显式跳过 task_book（service.py:1171-1173 注释："its answers are the dock's Start/Cancel and /intent refinements"）——这是唯一的接缝，refine 改道后此注释连同分支一起改写。
- `ChatRequest` 已带 `mentions`（recipe chip 随首条消息进 chat 的通道现成）；缺 `prior_intent`（面板手编书的 pin-merge 输入）与 `brand_template_id`（composer 的品牌选择当前只流向 `/intent`）。
- ComposerIntentAgent 的三动作 prompt（generate / answer / start，含"last line 裁决累积 prompt"规则）现成且经实战调优——**plan builder 保留整个 prompt 与 LLM 判定**，不改成代码侧确定性确认（多语言短确认的词典法太脆，且 plan builder 反正要被调用来区分修订/确认，不省调用）。
- `list_projects`（projects.py:101）无过滤——空项目垃圾的拦截点。
- `apps/api/scripts/` 只有运维脚本（reset_db / seed / migrate），无 e2e 设施——剧本测试 新建。

## 2. 设计论证

### 2.1 W1：plan path——任务书构建/修订/确认并入 chat service

`chat()` 在 autoResume 之后、ChatIntentAgent 之前插入 plan path 分派（仅 project scope；asset scope 永远不进）：

| 条件 | 去向 |
|---|---|
| 有 pending task_book question | plan builder（累积 prompt = stored prompt + 本轮原文；pin-merge prior）→ 三动作分派 |
| 无任何 run 且 `pending_intent` 为空（首次 / bail 后重来） | plan builder（首次推断）→ dock 任务书或 answer |
| 其他（已有 run/outputs 的项目） | ChatIntentAgent 四态（现状不动） |

plan builder = ComposerIntentAgent 更名内化（见 §4 命名审计），prompt 与三动作原样：
- `generate` → reasons 推导 + `sync_task_book_question` re-dock（pin-merge 逻辑含 recipe 规则③、 dub_languages 默认填充规则②，全部平移）
- `start` → `answer_question(kind="start", autonomy)` 复用 G-1 路径，run 从唯一出生地起
- `answer` → 普通 assistant 消息落库，任务书不被动

LLM 故障兜底平移：plan path 推断失败 → 默认任务书 dock（UI 可编可 Start，永不白屏）。

### 2.2 W2：composer 瘦身（前端）

send → 建项目 + 上传素材（现状保留）→ **不再调 `/intent`** → navigate 到 `/projects/$id` 并携带首条消息草稿（router state）→ overlay chat 挂载时自动以第一条 `/chat` 发出（message + mentions + brand_template_id）。spin­ner 只覆盖项目创建 + 素材上传；意图识别的等待发生在 overlay chat 的思考态里，可断线续看。

overlay 相位模型简化：confirm 相位不再是独立相位——pending task_book 就是 chat 的 dock（QuestionDock 现成）；面板手编保留，refine 走 `/chat`（带 `prior_intent`），Start 仍走 answer 端点 kind=start（面板编辑过的书随 `intent` 上送，现状保留）。`overlay: "intent"` search param 改 `overlay: "chat"`。

### 2.3 W3：`ChatRequest` 扩展 + mention pin 时机

`ChatRequest` 加两个可选字段（其余不变）：
- `prior_intent: InferredIntent | None`——refine 时面板当前书的 pin-merge 输入；缺省回落 stored `pending_intent`（平移现有规则）
- `brand_template_id: UUID | None`——仅 plan path dock 任务书时写入 `pending_intent`；后续轮次缺省不覆盖（平移现有规则）

recipe mention：`resolve_recipe_mentions` 从 `/intent` 平移到 plan path，**仍在 LLM 调用前 fail-fast 422**（reserved/unknown/多配方不烧推断）；pin 规则（合并代数三规则）原样。

### 2.4 W4：空项目垃圾 + 端点退役

- `list_projects` 排除"无消息且无 run"的项目（server 侧过滤，API 调用方同益）。窗口说明：建项目到首条消息落库之间项目短暂不可见，首条消息落库即出现——可接受，无需清理任务。
- 标题：平移现有惯例（prompt 前 15 字符），空兜底 `common.untitled`，无 LLM 起名（YAGNI）。
- 删除 `POST /projects/{id}/intent` 与 `POST /chat/infer-intent` 两个端点及 `ProjectIntent*` schemas；`/generate` 保留（retry / targeted / API callers），其 "full scope 必须带 explicit slots" 的 422 出生地校验不变。

### 2.5 W5：出生地校验与兜底链归位

- clips-需媒体：`create_run` 的 422 出生地门禁不动；plan path 的 `clips_without_media` reason 推导平移（`has_renderable_media` 复用）。
- 兜底链按序不变：autoResume（choice）→ plan path / 四态提案 → registry/出生地校验 → LLM 故障兜底 → 幂等竞态（单待决 + 409 + supersede）。IntentCoverage §4 表格中 `/intent` 行改写为 plan path。

### 2.6 W6：剧本验收 harness（后端，本期验收标准）

新建 `apps/api/scripts/chat_scenarios.py`：对活 API 跑预设多轮剧本，**形态级断言**（提案态 / dock 状态 / run 数变化 / 落库行），真实 LLM，不锁文案。剧本即 IntentCoverage §6 测试矩阵的可跑形态：

| # | 剧本 | 逐轮断言（形态级） |
|---|---|---|
| S1 | 模糊首次（有视频）："帮我处理一下这个演讲" → "开始吧" | 轮1 dock task_book（reasons 非空）；轮2 run 起来、pending_intent 清空 |
| S2 | 精确首次："5 clips + a German LinkedIn post" | 轮1 dock（clips×5 + post(de)）；Start 后 run slots 一致 |
| S3 | 修订循环：推断 → "加一条法语帖" → "聚焦 Q&A 部分" → 确认 | 每轮 re-dock（旧书 supersede）；pin 槽存活；最终 run 含 post(fr) |
| S4 | 能力提问："你能做什么" → "那开始吧"（无书时） | 轮1 纯 answer（无 dock 无 run）；轮2 不落 start（降级 plan/answer，不崩） |
| S5 | recipe mention：@dub 卡 + 改提示词语言 | 422 矩阵回归；pin 生效（dub_languages 用户点名赢） |
| S6 | 完成后追问："把第 2 条翻译成法语" | ChatIntentAgent task_list（回归：plan path 不抢已有 run 的项目） |
| S7 | 闲聊/越界 + 进度询问（run 在跑） | answer 形态；无 run 数变化 |
| S8 | 空项目：建项目不发消息 | list_projects 不可见；首发消息后可见 |

### 2.7 W7：文档同步（单事实源纪律）

- `INTENT_COVERAGE.md`：§1 通道地图坍缩（四表面 → 一表面 + dock/answer 按钮面）；§3.0/§3.1 重写（首次/确认并入 chat 相位）；§4 兜底链 `/intent` 行改写；§6 测试矩阵指向剧本测试
- `CHAT_ARCHITECTURE.md`：plan path 入 §3（task_book 仍由系统 raise，N-18 不变）
- `API.md`：`/intent`、`/infer-intent` 删除；`ChatRequest` 扩展字段
- `CLAUDE.md`：composer 行为契约改写（composer 只建项目+发首条消息；意图识别唯一入口 = chat）
- `RECIPES.md` / `tasks/recipe-mention.md`：pin 时机表述从 `/intent` 改为 plan path
- `NAMING.md`：新名登记（见 §4）

## 3. 改动点

| 文件 | 改动 |
|---|---|
| `app/chat/service.py` | W1：plan path 分派 + 三动作处理（自 projects.py 平移）；W3：recipe pin 平移；autoResume task_book 分支改写 |
| `app/chat/intent.py` | W1：`ComposerIntentAgent` → `PlanAgent`（更名内化，prompt 不动）；模块 docstring 重写 |
| `app/pipeline/routes/projects.py` | W4：删 `/intent`；`list_projects` 空项目过滤 |
| `app/chat/routes.py` | W4：删 `/infer-intent` |
| `app/models/schemas.py` | W3：`ChatRequest` + `prior_intent` + `brand_template_id`；删 `ProjectIntent*` / `InferIntent*` |
| `apps/api/scripts/chat_scenarios.py` | W6：新建剧本测试 |
| `apps/web/src/components/home/HomeComposer.tsx` | W2：摘 `/intent` 调用；navigate 携带首条消息草稿 |
| `apps/web/src/components/generation/GenerationOverlay.tsx` | W2：confirm 相位并入 chat dock；refine 改道 `/chat`；删 fallback `/intent` fetch |
| i18n `en.ts` / `zh.ts` + Tour 配置 | W2：composer/overlay 文案同步（"send 后发生什么"变化） |
| 文档 7 处 | W7（见 §2.7） |

## 4. 命名审计

- `PlanAgent`（任务书构建 agent）——ComposerIntentAgent 更名，职责不变：free-form 文本 → 任务书推断（三动作）。入 NAMING §2 词汇表；NAMING §5 同名审计结论更新为"chat 内部分工：ChatIntentAgent 路由 + PlanAgent 构建，入口唯一"。
- `plan path`（plan 路径）——chat service 内分派分支名，沿用 chat loop 既有词汇，无新后缀。
- `chat_scenarios.py`（剧本测试）——scripts 运维脚本同族命名。
- 无新表、无新列、无新包。

## 5. 验收

1. W6 剧本 S1–S8 全绿（形态级断言，真实 LLM；LLM 波动导致的失败人工判读后修 prompt 或补剧本，不锁文案）。
2. 回归：IntentCoverage §6 既有覆盖项（checkpoint 三答法 / autoResume / ask 三态 / pin-merge）在新结构下行为不变。
3. 前端（用户手测口径）：composer 发送 → spinner → 跳转 → overlay chat 首条消息自动发出 → 任务书 dock → 面板手编/refine/Start 全流程；刷新与跨设备 dock 重建不丢。
4. 文档 7 处同步完成，INTENT_COVERAGE 矩阵无 `/intent` 残留行。

## 6. Prohibited Behaviors

1. **禁**第二个意图入口——任何"从文本推断任务书/技能"的调用只能发生在 `/chat`（+ answer 端点）内部；composer 与 overlay 不得直接调任何 LLM/意图端点。
2. **禁**保留 `/intent` / `/infer-intent` 作"兼容残留"——端点、schemas、前端调用整链删除。
3. **禁** composer 侧任务书构建——pin-merge、recipe 解析、reasons 推导只在服务端 plan path；composer 永不构建 prior（recipe-mention 禁令 #1 平移）。
4. **禁**新表/新列——`pending_intent`、task_book question、`messages` 全部复用；`ChatRequest` 两个新字段是传输层扩展，不落库。
5. **禁**确定性词典法识别"开始吧"——start/revise/answer 的判定归 plan builder LLM（多语言短确认词典太脆）。
6. **禁** task_book 进 autoResume——choice 问题的零 LLM 答题不变；待决任务书的文本一律走 plan path。
7. **禁**剧本断言锁 LLM 文案——只断言形态（提案态/dock/run 数/落库）；文案类检查人工判读。
