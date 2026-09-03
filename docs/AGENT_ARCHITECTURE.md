# Repurposer Agent Architecture

> Status: Active（2026-08-09 重画，ADR-039 架构规范级大迭代；2026-08-18 随 ADR-043 收口请求层语法；2026-08-20 增 §2.5 行业坐标；2026-08-21 N-42 全量对齐行业命名——skill→tool 换位，更名随命名批 v2，落地前代码仍读旧名）
> 本文是 agent 架构的唯一事实源：**四层工程地图（Model / Harness / Graph / Loop）+ 工具包 + 花名册 + 估价**。排期见 PROGRESS.md；表归属见 MODULE_ARCHITECTURE.md；词汇见 NAMING.md（N-29~N-47）；loop 层行为规格见 CHAT_ARCHITECTURE.md；行业座位映射见 §2.5；**概念层母文档（厚 agent 判词 / 双引擎 workflow / 有界 loop 节点）见 `DIALOG_WORKFLOW.md`（ADR-052，施工中——B1 已落 2026-09-03）**。

## 1. 叙事

Repurposer 是一个 AI 助手，身怀技能（剪辑 / 配音 / 字幕 / 自媒体规划 / 配乐……）。**技能内部，是 agent 调 LLM、用 tools 实现的。**

架构一句话：**外层 loop（chat 治理环）编译出内层 graph（DAG 执行核）；图上每个节点自描述；每个 LLM 决策单元是同一个 Agent 类的声明实例，每次调用过同一个 harness 漏斗；模型经 client 单边界。**

我们是多 agent 系统——但 **agent 互不对话**：协作经落库产物沿 DAG 边流动（素材理解 → 分镜表 → clips → 配音行，每个中间产物可寻址、可复用、可单独重跑），编排者是 `compile_graph`（代码），不是任何 agent。禁 ReAct / 多步推理铁律延伸于此。

## 2. 四层工程地图

```
┌─ Loop（chat 治理环）──────────────────────────────────────┐
│  提议（LLM）→ 裁决（注册表）→ 预览/确认（dock）→ 执行 → 审阅 → 修订 │
│  chat/service.py 状态分派 · CHAT_ARCHITECTURE 行为规格        │
└──────────────────────┬────────────────────────────────────┘
                       │ 每一圈编译出一张图（TaskSpec → compile_graph）
                       ▼
┌─ Graph（DAG 执行核）──────────────────────────────────────┐
│  NodeBase 协议 + 图算法：报价=fold · 执行=topo · 校验=∀ · 对账=⊆ │
│  orchestrator（create_run 唯一出生地）· worker 认领走图          │
│  表：workflow_runs / workflow_steps（计划+账簿一体）             │
└──────────────────────┬────────────────────────────────────┘
                       │ agent 节点调 LLM
                       ▼
┌─ Harness（模型调用面）─────────────────────────────────────┐
│  Agent 漏斗：装配 → 渲染 → 调用 → 校验 → 修复一轮 → 计量 → 兜底 │
│  agents/base.py 唯一类 · agents/registry.py 花名册 · prompts/    │
└──────────────────────┬────────────────────────────────────┘
                       ▼
┌─ Model ──────────────────────────────────────────────────┐
│  MiniMaxClient 单边界（generate/generate_stream，schema 强制）  │
│  usage 捕获点 → metering；provider 政策开关的未来座位           │
└──────────────────────────────────────────────────────────┘
```

| 层 | 回答的问题 | 内核形态 | 家 |
|---|---|---|---|
| Loop | 用户多轮怎么治理 | 状态分派 + 四态提议 + dock/checkpoint | `app/chat/` |
| Graph | 多次调用怎么编排 | `NodeBase` + `compile_graph` + 图算法 | `app/pipeline/` |
| Harness | 每一次 LLM 调用怎么调得好 | Agent 漏斗 + 花名册 + prompts | `app/agents/` |
| Model | 用谁的模型 | client 单边界 + 计量捕获 | `app/providers/llm/` |

## 2.5 行业坐标（业务命名 → 行业座位）

模块分工在行业内已收敛为常数（dsh / Mastra / Agno / LangGraph / Claude Code 五源核对 + Agent Skills 规范四厂商证据，证据 `research/deepseek-harness.md` / `research/agent-skills-spec.md`）。本节是唯一映射表：**我们的业务名 ↔ 传统 agent 架构里的座位 ↔ 差异注记**——业务名随 N-42 与行业对齐（更名随命名批 v2，落地前代码仍读旧名），差异注记说明座位；新模块准入时先在此表找座位。

| 我们 | 行业座位（参照） | 差异注记 |
|---|---|---|
| Loop（chat 治理环） | agent loop（dsh agent-loop / Mastra AgentController 的 Session） | 我们的 loop 只做意图治理，执行下沉 Graph；dsh loop 内含工具循环 |
| Graph（DAG 执行核） | workflow / orchestration（LangGraph graph·node / Agno Workflow） | 拓扑代码定（ADR-028）；dsh 反面 = 模型写编排脚本，永拒 |
| Harness（Agent 漏斗） | agent harness 调用面（dsh core spine：system-prompt + tools + llm） | N-33 两义在案；我们漏斗固定，无插件拦截 |
| Model（MiniMaxClient） | provider seam（dsh `ctx.llm` 适配器注册表） | 单边界（家 = `providers/llm/`）；政策开关座位在 PROGRESS 池 |
| agent | agent（五源同词，N-29） | 一个类 + 声明实例（N-30） |
| tools 工具（N-42 前 skills 技能包） | tool（schema + execute；Agno Function step = 图调用先例） | 非模型可见（禁 ReAct 不变，调用方 = 图） |
| providers | integrations / provider clients | 外部服务包装一统家（含 `llm/` = Model 缝）；LLM 禁 import 门禁迁址于此 |
| skills 指令包 | skill（Agent Skills 规范，四厂商同格式） | 包格式行业同、消费异：装配期按声明注入（instructions 式消费），无 runtime discovery；首包 `linkedin-longform` 在册 |
| TaskSpec 任务书 | plan（Claude Code plan mode）/ goal（dsh） | 确认制；goal 的自治续跑不建 |
| interrupt（N-40 前 checkpoint） | LangGraph `interrupt()` / Mastra `tool_suspended` / Agno approval | 提问-等待-续跑的人在环闸节点 |
| Conversation | thread（Mastra Thread）/ session（Agno） | 撞 auth session 避让在案 |
| `app/memory/` 记忆层 | Agno Memory（语义记忆） | 现住户 = persona；积累式写入路径（≈ Agno Learnings）= persona 校准池条目 |
| persona 人设 | 无行业标准词（≈ 语义记忆的身份区） | 我们的产品层概念，行业无对应 |
| outputs 产物 | artifact（Claude） | N-01 统一产物表 |
| worker 行级认领 | jobs（dsh `ctx.jobs` / Agno background runs） | `FOR UPDATE SKIP LOCKED`，N-13：API 层 job 词汇已清 |
| 打勾流 / meta row | progress events（dsh `agent/*` 观察面） | 确定性进度，非 LLM 叙述（ADR-041 唯一进度面） |
| RunCard / 结果画布 | transcript 投影（dsh `deriveMessages()` / session-projection） | 我们从行记录投影，非事件日志 |
| agent 调用台账（池） | traces（Agno Traces）/ `assistant/message` 事实（dsh） | PROGRESS 需求池 P1 |
| 闸门编目（池） | invariants（dsh）/ guardrails（OpenAI Agents SDK） | PROGRESS 需求池 P2 |
| ——（不建） | compaction / subagent / steering / sandbox | 记录在案的拒绝（§5.4 + 调研文档 §3） |

## 3. RunPlan 概念表（九个，没有第十个）

| 概念 | 一句话 |
|---|---|
| **任务书** `TaskSpec` | 意图归一：唯一请求语法 = 工具链 `tasks` × instruction（语言/数量是链上参数，spec 级只剩默认值）；产物 = 编译图的派生投影，请求层永不声明（ADR-043/N-37）；loop → graph 的交接物 |
| **预处理** `preprocess` | ASR 词级时间戳 + 文本提取（机械，无 LLM） |
| **understand / plan** `understand` `plan` | 两步走：看懂素材（素材级，asset-hash 复用）→ 分任务（请求级，每 run 重排）；共享 crew，住 agents/ |
| **agent** | LLM 决策单元（N-29 正名）：一个 Agent 类的声明实例（N-30） |
| **机械** | "确定性工具"描述语（N-42 退役为子集属性）：无 LLM 决策的工具；providers/ 与确定性工具禁 import agents/LLM client（铁律迁址） |
| **工具包** `tools/`（N-42 前 `skills/`） | 能力的唯一家：节点类 + params + 私有工序 + 估价 + 展示键（+私有 agent 声明） |
| **质检** `verify`（节点 kind） | 单产物/全片质量校验（Phase 3，未实现）；可寻址、可计价、可单独重跑 |
| **施工图** `workflow_steps` | 计划+账簿一体的 DAG 内核：`inputs` 边表 / `spec` 参数 / `output_refs` 产物 / `estimate` 计划侧成本 / `cost` 账簿侧成本 |
| **产物** `outputs` | 统一产物表；产物类型 = 工具的属性（N-32），注册表派生可扩展；用户可见的产物预告 = 干跑编译的派生预览 `derived`（ADR-043） |

分发（Distribution）与 Pipeline 平级，缝 = 产物表，见 MODULE_ARCHITECTURE。

## 4. Graph 层：节点对象化与图算法

### 4.1 NodeBase——内核唯一认识的协议

```python
class NodeBase:
    kind: str                           # 唯一键；技能节点 kind = 技能名（N-35）
    # —— 类属性声明 ——
    output_type: str | None = None      # 产出型节点的产物（outputs 可扩展的家）
    after: tuple[str, ...] = ()         # 拓扑约束
    needs_plan_prelude: bool = False        # 需要 plan 前奏（preprocess→persona∥understand→plan）
    retries: int = 0                    # step 级瞬时重试预算
    requires: tuple[Requirement, ...] = ()  # 出生地门禁（media/transcript/persona_photo/voiceprint）
    # —— 方法（run 唯一必实现，其余有默认）——
    async def run(db, run, node, project) -> list[UUID]   # 执行，返回产物行 id
    def estimate(ctx) -> dict | None  # 自己报价：机械精确价 / agent token 区间；None = 不报价（fan-out / 编译期量未知）
    def label(slot) -> str | None       # 展示名（结果画布 / 步骤流同源）
    def reuse(...) -> UUID | None       # 幂等复用（asset-hash 类，命中则成本为零）
```

### 4.2 内核 = 图算法（大模块无非做一次图遍历）

| 算法 | 形态 |
|---|---|
| **报价** | fold：编译图逐节点 `estimate()` 求和——全图 = 生成前总价（dock 展示），子图 = 修改单价，配方预设图 = 配方卡估价贴 |
| **执行** | topo 走图：worker `FOR UPDATE SKIP LOCKED` 认领 ready 节点 → `NODE_KINDS[kind].run()` → 收尾 `maybe_finalize_run` |
| **校验** | ∀：出生地（`create_run`）对每个节点 `requires` 一次跑完，缺输入 422——链上技能直接携带其节点的 `requires` 声明，驱动器唯一（clips 需媒体 = SelectClips 自己的声明） |
| **对账** | ⊆：配方 flow keys ⊆ 编译图 kind 集，启动自检（`compile_graph` 是纯函数，直接编译配方比对），人肉评审退役 |
| **重跑** | 子图词汇：只跑此节点 / 从这里跑 / 跑到这里（节点可寻址的免费获得） |

### 4.3 拓扑铁律（不变）

- **拓扑代码定，LLM 永不塑形图**（ADR-028）：LLM 提议（task list = 意图面唯一语法，ADR-043），`compile_graph` 纯函数裁决与物化。
- `create_run` 是 WorkflowRun 唯一出生地：clips-media 门、count 边界、requires 校验全部集中于此，入口点零门禁代码。
- 失败语义：确定性失败快速失败 + 下游级联 skipped；provider/网络/存储瞬时故障抛 `TransientNodeError`，按节点 `retries` 预算复位 pending 不级联；`checkpoint` 瘦节点 `Suspend` 挂起等答（waiting / WAITING_HUMAN），bail 优雅退出永不标 failed。
- "全败或无事"：run 只在全部生成节点 failed/skipped 时标 FAILED；render 节点镜像渲染链，永不 hold run。

### 4.4 understand/plan 两步走（两次 LLM 调用，契约不变）

- **看懂素材**（`understand`）：产出素材理解（论点带位置/金句/主题/受众），素材级，`source_ref.asset_hash` 命中即复用（节点 `reuse()` 钩子的本例）；**自足契约**——产物必须足以支撑分任务。
- **分任务**（`plan`）：吃素材理解 + 任务书 → 分镜表（论点→分镜槽位 + 覆盖报告），请求级，每 run 必重排。
- **纯度纪律（签名化，见 §5.3）**：understand 不接收 persona/tone/instruction；plan 不读原稿。

### 4.5 节点分两类

- **工具节点**（N-42 前技能节点）：工具包持有，LLM 可提议（dispatchable），kind = 工具名（`select_clips`/`write_post`/`dub_clip`/`translate_clip`/`remove_filler`/`add_music`/`align_stills`/`revise_script`/`research`…）。
- **内部节点**：内核 crew，永不进提议空间（`preprocess`/`persona_bootstrap`/`understand`/`plan`/`checkpoint`/`render`），住 `pipeline/`。

### 4.6 BoundedLoopNode——agent 性的合法座位（ADR-052 B4，DIALOG_WORKFLOW §2.6）

多轮自主调工具（agent 性）只有一个合法形态：**有界 loop 节点**——`NodeBase` 子类，`run()` 内部驱动迷你工具循环（每迭代一次 agent 裁决 → 一个固定工具调用 → 证据累积），三护栏缺一不可：

1. **迭代上限**：`max_iterations` 类属性声明，循环永不超过它的报价；
2. **报价 = fold**：内核 `estimate()` = 子类 `loop_estimate()`（单次报价）× 上限——最坏情形已计入 run 总价，未来 loop 节点想报错价都报不了；
3. **对外 = DAG 单节点**：topology / roster / SSE 零改动；迭代只投影到自己 step 的 summary 通道，永不投到图上（无新 step / 无 canvas 节点 / 无 SSE 事件类型）。

循环的工具集固定在节点代码里——agent 选动作，永不造工具；开放自治（steering / compaction / 自由 tool-loop / 运行期工具发现）维持否决。**首个实例 = `research`**（`app/tools/research/`）：researcher agent 驱动 search/fetch 迭代（零键 web 对）至上限，收尾把 ResearchBrief 钢印进 `spec.research_brief`；编译期提升（align_stills 先例）让它以 `inputs=[]` 与 prelude 并行，声明 `consumes_research` 的 writer（四写手基类）接线等它并把简报追加进 asset_texts。**诚实降级是结构的一部分**：研究侧失败（funnel / 网络 / 上限耗尽）一律以 caveated brief 完成 step，run 继续——`retries=0`，重试只买同样的空。

## 5. Harness 层：模型调用面

### 5.1 Agent 漏斗——每个 agent 调用必过

```python
class Agent[OutT]:
    name: str            # 花名册键
    prompt: str          # jinja 模板名（版本随代码）
    schema: type[OutT]   # 输出契约

    async def call(**ctx) -> OutT:
        # 装配（纯度由签名保证）→ 渲染 prompt → client.generate(schema)
        # → 校验失败：错误结构化回显，一轮自修复（盲重试退役）
        # → 计量（Model 边界捕获 → workflow_steps.cost，ADR-025）
        # → 兜底：默认禁，显式声明才允许
```

### 5.2 三条纪律

1. **修复带反馈**：schema/裁决失败 → 错误结构化回显 → **一轮**自修复 → 再败才算节点失败（走图的重试语义）。不带反馈的重试只是掷两次骰子。
2. **兜底声明化**：静默降级是例外不是常态——合法先例 = intent router 永不白屏（fallback 任务书可确认可改）、多模态拒绝 → 文本降级；其余默认禁，声明处一眼可查。
3. **纯度签名化**：禁注规则在类型层不可表示——`understand.call(asset_texts, media)` 的签名里没有 persona 参数；比任何 prompt 警告都硬，签名即文档、评审即测试。

### 5.3 花名册与声明归属

- `agents/base.py` = 唯一 Agent 类；`agents/registry.py` = 共享 crew 声明（understand / plan / persona / translator…）；**工具私有声明住工具包**（选段编剧、各 writer、reviser）。
- `AGENTS` dict 收编全部声明，可枚举；启动自检节点→agent 引用存在。
- 流式 = 唯一特殊形态（chat intent，generate_stream + ProseDeltaExtractor 单漏斗，N-26）。
- context 装配：统一装配层 = `agents/contexts.py`——GenerationContext（节点侧，run 任务书 → GenerationContext）与 chat 意图上下文（项目摘要 / per-step 状态段 / mentions 注入 / recent 轮次收口）同住；各 agent 声明的 `assemble` 回调是每 agent 的输入契约（签名即纯度）。`pipeline/step_context.py` 只留机械助手（多模态收集 / 素材摘要 / 行助手）。

### 5.4 明确不建的 harness 部件

- **Context compaction**：那是长程单 context agent 的解法；我们的调用是短调用 + 每节点精确装配，没有可压缩的。
- **Tool-call loop 脚手架**（iteration caps / loop detection）：禁 ReAct，永远不需要。
- **Memory 写入冲突管理**：agent 无共享可变状态（中间产物落库、单写者），结构性规避。

## 6. Model 层

- `MiniMaxClient` 单边界：`generate(response_model=T)` / `generate_stream`——结构化输出在边界单点强制（`model_validate_json`）；usage 捕获点 → `app/metering.py` → `workflow_steps.cost`（ADR-025 不变）。
- 多模态 / 图像 / 音乐生成同边界（`generate_image` / `generate_music`）。
- **provider 政策开关**（未来）：第二 provider 的真实需求（EU 客户要求 EU-hosted）出现时，在 harness 漏斗按 policy 路由，用户-facing 形态 = 策略开关（"优先 EU 托管模型"），不是模型 SKU 货架；现在不预留接口（单边界已够）。

## 7. 工具包（`app/tools/`）

工具 = 能力层注册项（N-42 对齐行业 tool；营销文案里仍叫"技能"，§1 营销泛词豁免）；工具包 = 能力的唯一家：

```
tools/dub/           配音工具
├── node.py          节点类（NodeBase 实现：run/estimate/requires/label/retries=2）
├── params.py        DubClipParams（编译期裁决文档）
├── procedure.py     私有工序（逐翻译单元合成 → 测时长 → 窗口调速 → cue 起点拼接）
└── （agent 声明）    工具私有决策单元（可选；dub 复用共享 translator）
```

- **TOOL_REGISTRY 收编**：`tools/__init__.py` 汇总各包声明——提议空间 / 编译裁决 / 计量 / 展示同源；静态注册表随代码部署，不是插件系统（NAMING §5）。
- **新增工具 = 加一个包 + 一行 import**：重试/校验/拓扑/计量/估价随声明免费获得；禁平行映射表与特判分支（CHAT_ARCH §4 延伸）。
- **产出型工具**声明 `output_type`：产物类型词汇注册表派生（N-32）；请求层没有产物声明——用户看到的「你将得到」= 干跑编译的派生预览 `derived`（ADR-043）；**新增产物 = 一条注册项，intent router 当轮即知**（工具清单同源注入 prompt）。
- 注册项准入过 NAMING §7/§8 评审。

## 8. 估价与计量

- **估价（计划侧）**：`node.estimate(ctx)`——机械节点精确价（TTS 按字符 / render 按秒 / 克隆按次），agent 节点 token 区间（按 prompt 规模 + 输出 schema 给上下界），checkpoint = 0。
- **计量（账簿侧）**：usage → `workflow_steps.cost`（ADR-025 不变）；媒体调用（TTS/克隆/图像/音乐）经 `record_media_usage` 记实际量（`cost.units`）并把价目折钱累进 `cost.fixed_cost`。
- **价目住 Model 层**：`providers/llm/minimax.py` 的 `PRICING` 表 + `price_units`/`price_tokens` 是 MiniMax 价格的唯一事实源——节点报量、client 报价，报价 fold 与计量账簿读同一份价目（量×价两侧同源，校准才可比）。
- **两列对称**：`workflow_steps.estimate`（nullable，NULL = 未估价）与 `cost`——施工图 = 计划+账簿一体。
- **校准闭环**：actual（cost）与 estimate 偏差回归 → 收窄报价区间；报价长期可信的唯一路径。偏差读形已落地（`outputs.step_estimate_deviation` 单节点 / 同 docstring 内 SQL  twin 全舰队回归），呈现与收窄节奏属第九周。
- 用户呈现（PROGRESS 第九周）：dock 生成前总价 / chat 修改单价 / 配方卡估价贴。

## 9. 质检方向（Phase 3，未实现）

verify 节点 kind：单产物质检（分数+理由落库，不合格带反馈打回上游 ≤2 次，再败标"待人工"不阻塞）+ 全片质检（跨产物矛盾/撞车）。Layer-4 的旧概念不是"层"，是图里的一种节点——可寻址、可计价、可单独重跑，失败只打回不合格分支。

## 10. 验收器

- **剧本 harness**（test harness）：`chat_scenarios.py` S1–S45，真实 LLM 跑形态级断言；本架构的回归网。估价三断言在册（S41/S42）：flow 对账自检过 / 报价单调性（子图 ≤ 全图，非负）/ repair 只一轮。
- **启动自检**：runner 注册一致性（`assert_runners_registered` 同款）+ 节点→agent 引用存在 + 配方 flow 对账（§4.2）。
- e2e 真实管线纪律不变（无测试套件）；改 pipeline 代码必重启常驻 worker。

## 11. Critical files

- `app/agents/base.py` — Agent 类（harness 漏斗：装配→渲染→调用→修复一轮→声明兜底）+ StreamingAgent（唯一 sanctioned 子类，流式形态）；`app/agents/registry.py` — 共享 crew 花名册；`app/agents/contexts.py` — 统一装配层（GenerationContext / chat 意图上下文）
- `app/pipeline/step_context.py` — 节点侧机械助手（多模态收集 / 素材摘要 / 行助手）；context 装配在 `agents/contexts.py`
- `app/tools/` — 工具包（clips / dub / captions / posts / quotes / carousel / article / music / filler / stills…）；`tools/__init__.py` — TOOL_REGISTRY 收编
- `app/providers/` — 外部服务包装（asr / voice / storage / vision / dubbing…；N-42 前 `app/tools/`；通用件随消费方归位）
- `app/pipeline/graph.py` — NodeBase 协议 + 图算法；`app/pipeline/orchestrator.py` — create_run / execute_step / 收尾
- `app/pipeline/node_runners.py` — 内部节点 crew（preprocess / understand·plan 节点 / checkpoint / render）
- `app/pipeline/recipes.py` — 配方注册表（播种唯一发生地）
- `app/chat/service.py` — loop 状态分派（不持装配逻辑）；`app/chat/intent.py` — intent_router / chat_intent 两个声明实例（StreamingAgent 流式特殊形态）
- `app/providers/llm/minimax.py` — Model 单边界；`app/metering.py` — 计量
- `app/models/schemas.py` — GenerationContext / TaskSpec / IntentSlot（编译期投影 `spec.slot`，非请求层语法）/ 输出契约（OUTPUT_PAYLOAD_SCHEMAS）
- `app/prompts/*.j2` — prompt 模板（版本随代码）
