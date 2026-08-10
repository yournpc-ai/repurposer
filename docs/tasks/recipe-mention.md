# recipe-mention 实施简报——提及注册表架构 + 配方卡 chip 形态（Remix 复亮）

> Status: 🚧 施工中（2026-08-01 设计定稿；**期 1 已落地 2026-08-02**：双端注册表 + GET /recipes + chip/picker + composer 接线 + /intent 解析 + parked 机械删除 + dub 卡复亮；e2e 已验：pin→pending_intent→compile_graph 三 dub fork、422 拒收矩阵、无钉回归——真机媒体全跑留周五验收；**同日完全体提前**：文本内联 chip（MentionEditor）落地，chip 行/剥除形态整体替换，见 §2.5 注记；**2026-08-04 注记：pin 时机随意图层单面化自 `/intent` 迁入 chat plan path**——`resolve_recipe_mentions` 现由 `chat/service.py` plan path 调用（mentions 随首条 `/chat` 消息到达），行为不变，简报 `tasks/intent-surface-unification.md`；**2026-08-05 语义修订：配方=预设，不是钉**——播种改存在性填充（只补推断没有的槽位类型 + dub 空时填默认，无 explicit），面板手改槽经 `merge_prior_slots` 三方合并存活、chat 修订永远赢，剧本 S15/S16 锁定；本文"钉死/pin"表述除历史叙述外按预设语义理解，NAMING N-25 已加注）
> 依据：`docs/RECIPES.md` §7（卡片层，2026-08-01 修订）/§10（禁令）；`CHAT_ARCHITECTURE.md` §7（mentions）/§1（单一入口）；`NAMING.md`（宪法 §1/§5 + §5 审计触发）
> 迁移：**零表迁移**——提及住既有 `messages.mentions` JSONB 列；配方注册表是代码层静态注册表（SKILL_REGISTRY 同款纪律），随代码部署
> 用户裁决（2026-08-01，RECIPES 头部⑤）：① 配方交互形态 = Opus 式 composer mention（否全屏模态框）；② mention 系统做成**可扩展注册表架构**，功能只开放 recipe，后续 @ 类型 = 填注册项，**禁技巧性补丁**；③ DAG 永不外显，"编辑流程"的等价物 = chat（plan 级 ops + 子图词汇，闭环链线）

## 0. Context

配方卡 R1 落地时 Remix 交互被停用（`RECIPE_REMIX_ENABLED = false`，2026-07-31）：配方状态是 composer 的**不可见 prop**，选过的卡跨发送残留，污染了后续普通发送。同期竞品对照实验结论：ElevenLabs 把配方做成全屏模态框（第二条派发面），Agent Opus 把配方做成 composer 内的可见 mention chip（唯一入口走正常流）。裁决采 Opus 形态——与我们"composer = chat 的第一条消息 / 意图识别归管线"的架构同构，且审阅面板（`?overlay=intent` 逐槽行）原生承担"承诺确定性呈现"，模态框是多余容器。

本期三件事：① **提及注册表架构**（双端：前端 `MENTION_REGISTRY` + 服务端解析注册表），recipe 为第一注册成员，后续 @asset/@output 等只填注册项；② **配方注册表服务端化**——配方结构数据（任务书钉 + 输入槽位）从"前端数据文件"升为服务端静态注册表 + 公开只读端点，钉死（pin）唯一发生地收归服务端；③ **chip 形态复亮 Remix**——chip 三律（可见 / 发送即消费 / × 即删）结构性消除旧事故，删除全部 parked 机械。

## 1. 已核实的现状事实（读码确认，2026-08-01）

- **mention 契约与列已在**：`ChatMention`（`schemas.py:147-159`，`type: Literal["asset","output","transcript_segment","workflow_step"]` + `id` + `label`，`extra="forbid"`）；列 `messages.mentions` JSONB（`tables.py:382`，server_default `[]`）。**type 枚举不含 `recipe`。**
- **mention 的上下文注入已通用**：`_build_context`（`chat/service.py:355-358`）把任意 mention 渲染为 `Mentions (definite references): - {type} id=.. label=..` 行进 intent prompt——**上下文富化效果对任何类型已免费**，这是注册表"效果族"之一的现成座位。
- **chat 请求链路已带 mentions**：`ChatRequest.mentions`（`schemas.py:271`）→ `service.py:1154` 持久化进消息行 → `:1226` 进 `_propose_turn`。**前端 chat 输入尚无 mention 任何痕迹**（grep 无命中）。
- **/intent 钉死机械在跑**：`projects.py:328-338`——`prior.outputs` 经 `merge_explicit_slots` pin-merge，`prior.dub_languages` 有钉规则；pin 后写 `pending_intent`，`?overlay=intent` 审阅面板逐槽行呈现。**prior 目前由前端 composer 构造发送（要消灭的客户端钉）。**
- **compile_graph dub 扇出在跑**（`orchestrator.py:239-255`）：任务书带 `dub_languages` → clips 节点后逐语言 fork dub 节点。
- **出生地约束集中在 `create_run`**：clips-media 门 / SLOT_COUNT_LIMITS 在 `create_run` 内拒绝（ValueError → 422 / chat 反问兜底）——配方派发自动继承，无需新门禁。
- **前端 parked 机械全清单**（本期删除）：`recipes.ts:24` `RECIPE_REMIX_ENABLED=false` 及全卡 Soon 注释；`HomeComposer.tsx` `recipe` prop（`:72`/`:98`）、prefill effect（`:116-125`）、prior 载荷（`:249-260`）；`_app.home.tsx:29` `recipe` state 与 `:91` `onSelect={setRecipe}`。`RecipeCard.tsx` 的 `live = RECIPE_REMIX_ENABLED && status==="live"` 门。
- **配方卡数据现状**：`recipes.ts` `RECIPE_CARDS` 五张（dub live，余 reserved），字段 `slotsPrior`/`params.dubLanguages`/`preview`/`status`；preview URL 住 `recipes.assets.ts`（`upload_recipe_assets.py` 生成的内容寻址映射）；文案住 i18n `recipes.<id>.*`（含 promptTemplate）。`inputSlots` 在 RECIPES §7.1 原设计有、R1 按 YAGNI 修剪——**本期回归（消费者 = chip 提示 + Assets 引导）**。
- **注册表纪律先例**：`SKILL_REGISTRY`（静态 dict 随代码部署，"NOT a plugin system"）；`CAPTION_PRESETS`（单点定义 + Python 成员校验镜像）。配方注册表沿用同款表述：**静态注册表，随代码部署，不是插件系统**。
- **前端无 ChatMention 类型定义**（`lib/types.ts` 无）——随本期补，与后端 schema 同名同形（NAMING §1）。

## 2. 设计论证

### 2.1 提及注册表（双端架构骨架）

提及系统 = **类型注册表 + 效果注册表**，两端各一份，新类型 = 填注册项：

**前端 `apps/web/src/lib/mentions.ts`**——每个提及类型一条注册项：

```ts
interface MentionTypeDef {
  type: ChatMention["type"]
  icon: LucideIcon                    // chip 与 picker 共用
  i18nKey: string                     // mentions.types.<type>（picker 分组名）
  source: () => Promise<MentionCandidate[]>   // 候选供给；recipe = GET /recipes
}
const MENTION_REGISTRY: MentionTypeDef[] = [ recipeMentionDef ]  // v1 唯一成员
```

`MentionCandidate = { id, label, hint? }`（hint 供 picker 副标题，recipe 用 input_slots 推导"需要一段演讲视频"）。**picker 与 chip 组件只读注册表，无任何类型分支**——@asset 落地时注册 `source = 项目素材列表` 即上线。

**服务端**——提及效果分两族，按类型注册：

| 效果族 | 机制 | 状态 |
|---|---|---|
| 上下文富化 | `_build_context` 通用注入（§1 已免费） | 已在，任何类型适用 |
| 任务书钉死 | `resolve_recipe_mentions()` → slots + dub_languages pin | **本期新增，recipe 专属** |

钉死解析器住 `app/pipeline/recipes.py`（新文件，与 skill registry 同包——配方是任务书模板，归 pipeline 层；不够格独立包，NAMING §7）。

### 2.2 配方注册表服务端化（消灭"前端数据文件"）

```python
# app/pipeline/recipes.py — 静态注册表，随代码部署（SKILL_REGISTRY 同款纪律）
RECIPE_REGISTRY: dict[str, RecipeEntry] = {
    "dub": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video", required=True)],
        outputs=[IntentSlot(type="clips", explicit=True, ...)],
        dub_languages=["de", "fr", "es"],
    ),
    ...
}
```

- **钉死实质（outputs / dub_languages）永不出服务端**——前端不再构造任务书任何部分；`GET /api/v1/recipes`（**公开只读**，landing 匿名受众也是卡片的读者）只返回 `{id, status, input_slots}`。
- **前端卡目录重构**：`recipes.ts` 从"数据文件"瘦身为——`GET /recipes` 拉结构（id/status/input_slots）+ `recipes.assets.ts` 供 preview 映射（生成文件不动）+ i18n 供文案（`recipes.<id>.*` 不动）。新增配方 = 服务端注册项 + i18n 键 + preview 资产，三处配置零代码路径。
- `input_slots` 双消费者：前端 chip/picker 提示与 Assets 引导（展示）；服务端 clips-media 门兜底（`create_run` 既有约束，拒收信息含配方所需类型）。
- `RecipeCard.tsx` 渲染数据源切换（静态 import → 注册表查询），布局/交互不变（RECIPES §7.3）。

### 2.3 钉死语义（服务端解析，两个调用点一份解析器）

```
resolve_recipe_mentions(mentions) -> RecipeEntry | None
  · mentions 无 recipe        → None（路径与现状零差异）
  · 一把以上 recipe           → ValueError（v1 一条 run 一把配方——配方是完整任务书，配方组合归后续）
  · 未知 id / reserved 卡     → ValueError（422 / chat 反问兜底）
```

- **调用点 ① /intent**（composer）：`ProjectIntentRequest` 加 `mentions: list[ChatMention] = []`；路由先解析 recipe → 与 `prior` 同路 pin-merge（`merge_explicit_slots` + dub 钉规则原样复用）→ `pending_intent` → 审阅面板。**composer 从此发 mentions 不发 prior；`prior` 字段保留给 API caller。**
- **调用点 ② chat 派发**（`chat/service.py`）：用户消息带 recipe mention → 解析 → 写 `pending_intent` + dock task_book 问题（既有确认面）→ Start 起 run。**LLM 不解释 recipe 提及**——确定性引用直接钉，不占 intent 调用（"LLM 提议代码裁决"的延伸：用户经确定性引用自提议，代码裁决）；mention 仍经 `_build_context` 通用注入进后续轮次的上下文。
- v1 边界：单 run 单配方（多配方 422 不变）；同句其他意图的合并语义随 agent-loop-upgrade（2026-08-02）定格为**合并代数三规则**——① 承诺钉死（recipe.outputs pin 优先）；② 参数默认（dub_languages：用户点名的赢，没点名用配方默认——remix 改"中文"生效）；③ 额外放行（"@配音卡 顺便写篇长文"的长文槽位加性存活）。审阅面板逐槽行呈现合并后的全部真相。
- `create_run` 出生地约束不变：clips-media 门拒收时，composer 表面 422 toast、chat 表面反问兜底——两表面提示均含配方所需素材类型。

### 2.4 chip 三律与组件（旧事故的结构性消除）

三律（写死进组件契约，新旧事故根因的对立面）：

1. **可见**：mention 是 textarea 内的内联 chip（图标 + label + ×），配方被选中这件事永远肉眼可见；
2. **发送即消费**：send 成功、跳转前清空 composer 草稿（prompt + mentions）——就这一行清空，不建任何"消费机制"；
3. **× 即纯化**：删 chip 后本次发送不带任何钉——无残留、无隐式状态。

- 组件：`MentionChip`（chip 本体）、`MentionPicker`（@ 触发的 Popover 候选列表，键盘导航；overlay-surface 纪律）——两组件只读 `MENTION_REGISTRY`，composer 与 chat 输入共用。
- **点卡 = 检视 overlay**（2026-08-10 修订）：`RecipeCard` 的本体点击与 hover Remix 按钮同开配方检视 overlay，chip + `promptTemplate` 预填由 overlay 发射区携带（纯文本预填，可见可改，不是状态）；composer 回填路径退役，composer 侧只留 @ 手选——同一 mention、同一终点。`RECIPE_REMIX_ENABLED` 闸与全部 parked 机械删除（§1 清单）。
- chat 输入：同一 chip + picker；发送走既有 `ChatRequest.mentions`；用户消息泡渲染 mention chip 行（持久化记录，刷新可重放）。
- 发送后：composer 路径 → `?overlay=intent` 审阅面板（逐槽行确定性呈现承诺）→ Start → 打勾流；chat 路径 → task_book dock → Start → 打勾流。**两表面共用确认面与打勾流，零新进度 UI。**

### 2.5 可扩展性证明（后续 @ 类型的注册路径）

以 @asset（"把 @素材2 换成…"）为例，上线只需：① 前端 `MENTION_REGISTRY` 加注册项（icon + i18nKey + `source = 项目素材列表接口`）；② 后端 `ChatMention.type` Literal 加 `"asset"`……已在内（契约预留四类型）；③ 效果 = 上下文富化族，`_build_context` 零改动。@output / @workflow_step 同型。**新类型 = 前端一条注册项 +（如需新效果族）后端一个解析分支注册**——无一处 switch 补丁。Remix/chat 闭环链线是全量 picker 的归属（plan 级 ops + 子图词汇同批）。

**@asset 已随完全体提前落地（2026-08-02，composer 表面）**：注册表第二成员——`source` 经 `MentionContext.files` 读取 composer 已挂文件（id = 文件名，项目尚不存在时名字即身份）；效果走上下文富化族的**自然语言通道**（chip 在句中序列化为 `@文件名`，intent agent 直接读到指令指向哪个文件），服务端零改动（/intent 实验：asset 提及透传正常）。picker 的数据通道同步升级为 `source(ctx)`——注册项仍是静态配置，候选源是活的。chat 表面的 @asset（项目素材，UUID 身份 + `_build_context` 注入）归期 2。

**文本内联 chip 已提前落地（2026-08-02 用户裁决）**：原定在此处等第 7 周的内容被提前——理由是"@ 后句子里找不到提及内容"在日常使用中太出戏。落地形态 = `MentionEditor`（contentEditable，chip 为 `contenteditable=false` 内联节点；**DOM 拥有文本事实源**，所有编辑路径汇于 `syncNow` 单一同步漏斗上报 `{text, mentions}`；提及在文本中序列化为 `@label`，结构化钉走 mentions 数组）。v1 的 chip 行/剥除逻辑已整体删除（不是补丁，是替换）；注册表排他/去重规则在 DOM 层原样执行。picker 改为光标锚定（空间不足时下翻）。tour 第 3/5 步文案同步教 @ 操作与 Remix 自动落 chip，闭环。

## 3. 改动点

**后端（apps/api）**

| 文件 | 改动 |
|---|---|
| `app/pipeline/recipes.py` | 新建：`RecipeEntry` / `InputSlot` / `RECIPE_REGISTRY`（五卡迁移，结构数据自 `recipes.ts` 迁入）+ `resolve_recipe_mentions()` |
| `app/models/schemas.py` | `ChatMention.type` Literal 加 `"recipe"`；`ProjectIntentRequest` 加 `mentions` |
| `app/pipeline/routes/recipes.py` | 新建：`GET /api/v1/recipes` 公开只读（`{id, status, input_slots}`） |
| `app/pipeline/routes/projects.py` | /intent 路由：recipe 解析接入既有 pin-merge |
| `app/chat/service.py` | chat 派发：recipe mention → 解析 → pending_intent + task_book dock |

**前端（apps/web）**

| 文件 | 改动 |
|---|---|
| `src/lib/mentions.ts` | 新建：`ChatMention` 类型 + `MENTION_REGISTRY`（recipe 首成员） |
| `src/components/mentions/MentionChip.tsx` / `MentionPicker.tsx` | 新建（注册表驱动，composer/chat 共用） |
| `src/lib/recipes.ts` | 重构：注册表查询 + preview 映射 + i18n 胶；`RECIPE_REMIX_ENABLED` 删除 |
| `src/components/home/RecipeCard.tsx` | 数据源切注册表；Remix → 开检视 overlay（2026-08-10） |
| `src/components/home/HomeComposer.tsx` | parked 机械删除（recipe prop/prior/prefill effect）→ mentions state + chip + picker + /intent 发 mentions |
| `src/components/chat/`（输入组件） | chip + picker 接入；消息泡 mention chip 行 |
| `src/routes/_app.home.tsx` | recipe state 删除 → mentions state |
| `src/lib/i18n/locales/en.ts` / `zh.ts` | `mentions.*` 键（picker 文案、类型名、input_hint）en 先行 zh 镜像 |

## 4. 命名审计

- `MENTION_REGISTRY`（提及注册表，前端）/ `RECIPE_REGISTRY`（配方注册表，服务端）/ `input_slots`（输入槽位）/ mention type `"recipe"`——全部进 NAMING §2 词汇表；判例 N-25（任务书钉死归服务端注册表解析）。
- 注册表纪律沿用 NAMING §5（枚举 = String 列 + 应用层注册表校验）：mention type 的 Literal 校验 + 注册表双守门。
- 无黑名单后缀（§3）；无新包（§7：recipes.py 住 pipeline，routes 入住模块先例 N-06）。
- "硬编码"一词随本次重构从配方线文档/注释清除——正确表述是**静态注册表，随代码部署**（SKILL_REGISTRY 同款）。

## 5. 分期与验收

| 期 | 内容 | 验收（e2e 真实管线，无测试套件纪律） |
|---|---|---|
| **期 1**（composer + 卡复亮，第 1 周） | 双端注册表 + `GET /recipes` + chip/picker + composer 接线 + /intent 解析 + parked 机械删除 + dub 卡复亮 | 点 dub 卡 → chip 落 composer → 上传视频 → 发送 → 审阅面板逐槽行呈现"clips + DE/FR/ES 配音"→ Start → 单 run 出原声 clips + 三语言派生行；**回归：chip 发送后再发一条普通 prompt，不带任何钉**；@ 手选与点卡同终点 |
| **期 2**（chat 表面，第 1–2 周缓冲） | chat 输入 chip/picker + service 解析 + task_book dock + 消息泡 mention 行 | 项目 chat 输入 @配音卡 → dock 呈现任务书 → Start → run；messages.mentions 持久化，刷新后消息泡 chip 仍在 |
| **期 3**（扩展座位，不实施） | @asset/@output 注册路径评审记录（§2.5）随闭环链简报立项 | — |

配套：RECIPES §7 修订已随本简报同批落地；PROGRESS 第 1 周"三卡定格"行的交互层即期 1，周五验收时回填。

## 6. Prohibited Behaviors

1. **禁**前端构造任务书钉（prior 的客户端构造路径随本期删除；钉死唯一发生地 = 服务端 `resolve_recipe_mentions`）。
2. **禁** mention 类型的一次性分支——新类型 = 双端注册表各一条注册项；picker/chip/解析器永不出现 `if type === "recipe"` 以外的类型判断。
3. **禁** chip 状态跨发送残留（三律：可见 / 发送即消费 / × 即删）。
4. **禁**全屏配方模态框、DAG 画布（形态裁决 2026-08-01；"编辑流程"等价物 = chat plan 级 ops，闭环链线）。
5. **禁**新表——注册表随代码部署；mentions 住既有 `messages.mentions` JSONB。
6. **禁** LLM 解释 recipe 提及（确定性引用直接钉）；**禁**单 run 多 recipe 提及（v1 拒收）。
7. **禁**钉死实质（slots/dub_languages）泄出 `GET /recipes`——端点只回 `{id, status, input_slots}`。
8. **禁**绕开 `orchestrator.create_run`（两表面派发同出生地，零旁路原则不变）。
