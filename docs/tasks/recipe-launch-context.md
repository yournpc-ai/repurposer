# recipe-launch-context 实施简报——配方脱离 mention 体系（recipe_id 发射通道）

> Status: 🗄 已翻案（2026-08-11，ADR-040 配方 = 提示词）：`recipe_id` transport 与播种块当日退役——配方对 plan agent 不可见是结构病灶（ask 判决当轮无书可 dock，S11 连败），且双份表达可漂移；发射的全部行为载荷 = 预填模板原文，服务端永不见配方身份。本文余下章节均为历史记录（原状态：✅ 已落地 2026-08-11 晨间，mention 哲学升级——配方不是对 AI 说的话，是发射上下文）。
> 方针母文档：`docs/MENTIONS.md`（§2 两族分类、§3 排除清单）；配方卡架构归 `RECIPES.md`。
> 排期：PROGRESS 第二周闭环链期间顺做（改动面小、无新表、harness 有回归网）。

## 0. Context

配方 mention chip 的历史任务已完成：它诞生于"Remix 回填 composer"时代（句中钉 = 预设播种的唯一载体）；overlay 内发射落地后，点卡动作本身就是配方身份，句中 chip 沦为第三遍冗余（overlay 标题、预填文案、chip 各说一遍）。mention 哲学升级为两族（请求 / 指认）后，配方两族都不属于——它必须从 mention 体系退出，降级为**发射元数据**。

关键约束（不可退让）：配方预设播种的确定性**不能**随 chip 一起删除——承诺兑现靠"服务端注册表播种 + 三方合并"，不靠 LLM 从 prompt 文本重新推断（RECIPES 禁令 #2）。`recipe_id` 载荷是确定性的新钥匙。

## 1. 已核实事实（读码确认，2026-08-11）

- `ChatRequest`（`models/schemas.py:411`）已有 **plan-path transport 家族**：`prior_intent` / `persona_id`——"carry only, never persisted on the message"。`recipe_id` 落同座位。
- 配方播种唯一调用点：`chat/service.py:897` — `resolve_recipe_mentions(request.mentions)`。
- `resolve_recipe_mentions`（`pipeline/recipes.py:259`）：按 mention id 查 `RECIPE_REGISTRY`，unknown / reserved → 422。
- 前端注册表：`lib/mentions.ts` `MENTION_REGISTRY` 两项（recipe / asset）；`recipeSource` 已过滤 `status === "live"`（reserved 不进 picker）。
- overlay 现状：`RecipeInspectOverlay` 发射区有静态 chip 行（`MentionChip`）+ `mentions` state，launch 时随 `mentions` 发出。
- harness 配方 fixtures：`scripts/chat_scenarios.py` S5（mention pin + unknown/reserved 422 矩阵）、S15（recipe refine）、S16（三方合并）均以 `mentions: [{type:"recipe",…}]` 构造。
- `run.context.recipe_id` 穿线（闭环链 D5 配方身份三站）从 plan path 播种结果派生，不直接读 mention——改键后链路自动延续。
- flow ↔ outputs 启动自检（`orchestrator.py:1001`）直读 `RECIPE_REGISTRY`，与 mention 无关，不受影响。

## 2. 设计决策

| # | 决策 | 要点 |
|---|---|---|
| D1 | **配方 = 发射上下文，非 mention** | `MENTION_REGISTRY` 删 recipe 注册项；composer @ picker 只剩 @asset；overlay 删 chip 行与 mentions state（发射区 = 标题/说明 + Input 小节 + 上传 + 提示词 textarea + 生成） |
| D2 | **`recipe_id` 走 plan-path transport** | `ChatRequest` 加 `recipe_id: str \| None = None`（与 `persona_id` 同家族：carry only, never persisted）；仅配方 overlay 的首发消息携带 |
| D3 | **播种改键不改行为** | `resolve_recipe_mentions(mentions)` → `resolve_recipe_launch(recipe_id)`：按 id 查注册表 + live 校验（unknown/reserved 422 不变）；存在性填充 + `merge_prior_slots` 三方合并原样 |
| D4 | **历史消息渲染不断** | `ChatMention.type` 的 `"recipe"` 保留为渲染残留（旧消息气泡的 chip 正常显示）；前端 chip/picker 组件读注册表，注册项删除后自然不再可新建 |
| D5 | **@skill 不在本简报** | 方针已立（MENTIONS §5）；落地等 SKILL_REGISTRY 公开投影端点，单独简报 |

## 3. 改动点

### 服务端

| 改动 | 文件 |
|---|---|
| `ChatRequest` 加 `recipe_id: str \| None = None`（plan-path transport 注释家族内） | `models/schemas.py` |
| plan path：`resolve_recipe_mentions(request.mentions)` → `resolve_recipe_launch(request.recipe_id)` | `chat/service.py:897` |
| `resolve_recipe_mentions` 改名改键为 `resolve_recipe_launch(recipe_id: str \| None)`；未知 id / reserved 422 文案不变 | `pipeline/recipes.py` |

### 前端

| 改动 | 文件 |
|---|---|
| `LaunchInput` 加 `recipeId?: string`；firstMessage router state 携带 | `lib/useProjectLaunch.ts` |
| 首发 /chat 消息体加 `recipe_id`（读 firstMessage.recipeId） | overlay chat 首发装配点（`components/chat/`） |
| 删 chip 行 + `mentions` state；`launch({ prompt, files, recipeId: card.id })` | `components/recipes/RecipeInspectOverlay.tsx` |
| 删 recipe 注册项 + `recipeSource`；`ChatMention.type` 保留 `"recipe"`（渲染残留注记） | `lib/mentions.ts` |
| 首发消息类型加 `recipeId` 透传字段 | `lib/types.ts` / chat-stream 相关 |

### harness

| 改动 | 文件 |
|---|---|
| S5/S15/S16（及 S10/S11/S22 中配方相关构造）改走 `recipe_id`；unknown/reserved 422 断言保留 | `scripts/chat_scenarios.py` |

### 文档（现在时改写，随码同提交）

- `RECIPES.md` 头部裁决⑤：Remix = mention chip 形态由"配方 = 发射上下文（`recipe_id` 载荷）"取代，改指 `MENTIONS.md`；§7.2 链路图 chip 行删除；§7.1 数据包消费方表述同步。
- `tasks/recipe-mention.md`：状态行注记——mention 注册表架构保留（asset 等后续成员照旧），recipe 成员退役，原因改指 MENTIONS §3。
- `CLAUDE.md` composer 段 mentions 描述同步（recipe 不再是第一注册成员）。
- `NAMING.md` mention type 行：`recipe` 注记退役（渲染残留）。
- `docs/README.md`：登记 `MENTIONS.md`。

## 4. 命名审计

| 名 | 义 | 备注 |
|---|---|---|
| `recipe_id`（载荷字段） | plan-path transport：配方身份，carry only never persisted | 与 `persona_id` 同家族；入 NAMING 词汇表 |
| `resolve_recipe_launch` | 服务端播种函数（按 id 查注册表） | 取代 `resolve_recipe_mentions`；NAMING 同步 |
| mention type `"recipe"` | 退役 | 类型联合保留供历史渲染；注册表项删除 |

无新表、无新列。

## 5. 验收

1. 点 dub 卡 → 发射区无 chip → 上传视频 → 生成 → 任务书照旧确定性播种（clips 槽 + zh/fr/es 配音），dock 逐槽行呈现不变。
2. 发射区把提示词语言改成"德语"→ 发送 → 用户点名赢配方默认（S5 语义沿新通道复绿）。
3. composer @ picker 无配方项，只剩素材；旧项目历史消息里的 recipe chip 正常渲染。
4. `POST /chat` 带 `recipe_id="unknown"` / reserved 卡 id → 422，提示含配方所需素材类型。
5. 剧本 harness 全绿（S1–S40 无回归）；无配方发送（`recipe_id` 缺省）行为与现状逐字节一致。

## 6. Prohibited Behaviors

1. **禁**把配方身份编码进 prompt 文本（拼接 "@视频配音" 字符串等）——文本是给 LLM 读的大白话，身份走 `recipe_id` 字段。
2. **禁** LLM 从 prompt 重新推断配方预设——确定性播种唯一发生地 = `recipe_id` → 服务端注册表。
3. **禁** `recipe_id` 开第二通道（项目列、run 配置等）——唯一通道 = 首发消息 transport；run 内配方身份从 plan path 派生（`run.context.recipe_id` 现状链路）。
4. **禁** composer @ picker 出现配方项回归；mention 新类型未过 MENTIONS §3 判定三问不得立案。
5. **禁**删除 `ChatMention.type` 的 `"recipe"` 成员（历史消息渲染依赖）。
