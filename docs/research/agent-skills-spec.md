# Agent Skills 规范生态 — 原始证据（Mastra / Agno 官方文档 + 四厂商采用）

> Status: 原始证据（2026-08-21 抓取 Mastra / Agno 官方文档四篇 + MiniMax 仓库解剖交叉；MiniMax 仓库细节专档 `research/minimax-design.md` §11）。本文件只记事实与观察；词与座位的拍板去向 = NAMING 词汇表 / ADR，不在此档。
> 关联：`research/deepseek-harness.md`（同族：agent harness 词汇五源证据）；`research/minimax-design.md` §11（MiniMax skills 仓库解剖）。

## 1. 规范本体：Agent Skills specification

Mastra 与 Agno 文档均原样声明采用 "Agent Skills specification"（Anthropic 创立）。规范形态：

- **单技能 = 一个目录**：`SKILL.md`（指令本体）+ 可选 `references/`（按需加载的支持文档）+ 可选 `scripts/`（可执行辅助代码，须 shebang 行，执行时 cwd = 技能目录）。
- **SKILL.md = YAML frontmatter + markdown 正文**。Agno 版 frontmatter 仅允许六键：`name` / `description` / `license` / `compatibility` / `allowed-tools` / `metadata`（自定义字段如 `version` / `author` / `tags` 收进 metadata）。
- `name` 校验规则（Agno）：lowercase + 数字 + 连字符，≤64 字符，不可首尾连字符、不可连续连字符，**必须与目录同名**；`description` ≤1024 字符（进系统提示）；`compatibility` ≤500 字符。

## 2. 四厂商采用情况

| 厂商 | 采用形态 |
|---|---|
| Anthropic | 规范创立者（Agent Skills / SKILL.md） |
| MiniMax | 技能市场 + GitHub 仓库（`MiniMax-AI/MiniMax-H3` `skills/` 内容技能、`MiniMax-AI/skills` dev 技能 = Claude 插件市场格式）+ 五 harness 镜像（`.claude` / `.agents` / `.codex` / `.cursor-plugin` / `.opencode`）+ `meta.yaml` 市场元数据 + `skills-lock.json`——解剖见 `minimax-design.md` §11 |
| Mastra | 三形态：**inline skill**（代码对象 `createSkill()`）/ **filesystem skill**（SKILL.md 目录，`LocalSkillSource` 加载）/ **dynamic skill**（resolver 函数按 RequestContext 返回 `SkillInput[]`） |
| Agno | `Skills` 类 + `SkillLoader` + `LocalSkills`（文件系统 loader）；加载即校验，失败抛 `SkillValidationError`（可 `validate=False` 绕过） |

## 3. Agent 字段解剖：instructions 与 skills 并存

两家 Agent 定义都同时持有 **`instructions`（内联指引）与 `skills`（打包指令）两个字段**，分工明确：

| 字段 | 内容 | 加载方式 |
|---|---|---|
| `instructions` | 内联指引文本（agent 级行为指导） | 常驻：直接进系统消息 |
| `skills` | 打包的领域专家知识（SKILL.md 目录） | **渐进披露（Progressive Discovery）**：系统提示只进 name + description 元数据（Agno 另进可用 scripts/references 清单与加载说明），正文由模型按需经 skill tools 自取 |
| `tools` | 可调能力（函数） | schema 常驻，模型调用 |

模型侧的 skill 访问工具：Mastra 自动给 agent 三件套 `skill` / `skill_read` / `skill_search`；Agno 给 `get_skill_instructions(skill_name)` / `get_skill_reference(skill_name, reference_path)` / `get_skill_script(skill_name, script_path)`。Agno 称这一模式为 "Domain Expertise on Demand" / "Reusable Knowledge Packages"，四拍 = Browse → Load → Reference → Execute。

**分界规则（两家一致）**：instructions = 每请求恒常的内容（身份 / 语气 / 恒常规则 / 输出格式），稳定且短，模型必须常驻可见；skills = 条件性、大型、动作导向的领域知识，按需加载。毕业信号 = **条件性 + 加载频率**，不是尺寸。Mastra 原话："Instructions are always in context, so keep them for stable behavior that applies to every request. Move anything conditional, large, or action-oriented into tools/ or skills/"；Agno 动机原话："skills let you organize domain knowledge into focused packages…allowing you to save tokens"。

**注入形态（两家一致）**：Agno = skill 元数据（name + description）经 `skills.get_system_prompt_snippet()` **全量常驻**系统提示（无 per-request 过滤、无数量上限文档），正文 runtime 经 skill tools 懒加载，`skills.reload()` 可拾取磁盘变更。两家共同结论：**always-on 内容的官方座位 = instructions；装配期把 skill 正文强制注入系统提示（绕过 skill tools）= 无文档先例**——要 always-on 就放 instructions，要按需才用 skill 系统。

**覆盖与优先级**：两家同为**整体替换（name-wins），无字段级合并**。Mastra = agent-level skills 覆盖 workspace skills（`MergedWorkspaceSkills.list()` 先列主集、滤掉同名次集）；Agno = 多 loader 叠放**后载压前载**，官方推荐分层 = loader 排序（平台/shared 在前，用户/项目在后）。Mastra 侧若要不复制的分层，只能自己在 `createSkill()` 里拼 instructions 字符串。Agno 另有 Team Skills（团队共享包）。

## 4. Tool 与 Workflow 座位

**Mastra tool**：`createTool`（`@mastra/core/tools`）= `id` + `description` + `inputSchema` + `outputSchema` + `execute`；注册 = 挂到 Agent 的 `tools` 属性，stream 里的 toolName 取对象键非 id；工具名与用途写进 agent instructions 引导调用。原话 "A skill is not a runtime tool"——skill = 指引，tool = 运行时可调。subagent / workflow 可投影为 tool（`agent-<key>`）。

**Agno Workflow**：`Workflow` = orchestrator（"orchestrates agents, teams, and functions through a defined control flow"）；`Step` 裹**恰好一个** executor（Agent / Team / Function / 嵌套 Workflow，直接传入自动包裹）；容器 = `Steps` / `Parallel` / `Loop` / `Condition` / `Router`，默认顺序执行；数据流 = Function 步骤经 `StepInput` 取全部前序输出，Agent/Team/嵌套 Workflow 取最近一条。**tools 住 agent 内（`tools` 参数），不是 workflow 的 executor**。

**确定性编排的座位**：Agno 的 **custom Python function 是一等 Step executor**——函数体内可直接调任何 tool / API / agent，模型无 tool-call 决策（"图调用能力"的官方形态；Mastra 文档无对应答案）。

**生命周期与规模（答录事实）**
- 版本：frontmatter `metadata.version` 字段在 + Agno `skills.reload()` 在；**版本 pinning / mid-run 变更行为 / golden-output 测试 / 回滚指引两家均无文档**。
- 目录预算：Agno 全部 skill 摘要恒常驻（无上限机制）；**tool 膨胀的行业硬数字——"Past 20 tools, models start hallucinating tools or picking the wrong one"**，官方解法 = Context Providers（把多工具折叠成 `query_<id>` / `update_<id>` 一对）。
- 组织：Agno 推荐 Toolkit 类分组相关 tools（共享状态、协同设计）；Mastra 无文档答案。
- 确定性标记：**两家均无**"deterministic / 无 LLM"标记惯例；Agno `@tool` flags 只管执行控制（`requires_confirmation` / `external_execution` / `stop_after_tool_call` / `cache_results`）。

## 5. 派生词清单（两家代码/文档实际用词）

- **Mastra**：inline / filesystem / dynamic / workspace / agent-level skills；`createSkill()`、`LocalSkillSource`、`SkillInput[]`、`resolve-skills` span；`skill` / `skill_read` / `skill_search` 三件套。
- **Agno**：`Skills`、`SkillLoader`、`LocalSkills`、`SkillValidationError`；`get_skill_instructions` / `get_skill_reference` / `get_skill_script`；skill tools / skill summaries / Team Skills / Progressive Discovery / Domain Expertise on Demand / Reusable Knowledge Packages。

## 6. 多 agent 协调：subagents / teams（模型路由的监督者形态）

**Mastra subagents**：subagent = 特化的 `Agent` 实例，注册进父 agent 的 `agents` 属性；委派 = **agent-as-tool**（"Subagent invocations are dispatched as tool calls"）；协调**模型驱动**——父 agent 靠自己的 instructions + 各 subagent 的 `description` 决定何时委派（supervisor pattern）；代码侧仅有拦截钩子（`onDelegationStart`）。

**Agno teams**：`Team{model, name, members: Agent[], instructions}`——团队自带一个模型，协调由**团队模型 + instructions** 驱动（"Coordinate with the two members" / "First plan, then summarize"），无独立 leader agent、无代码路由；成员产出可 `show_members_responses=True` 透出。

**观察（事实层）**
- 两家的多 agent 协调同为**模型路由**（父模型/团队模型按 description 与 instructions 临场决定委派），即 supervisor / orchestrator-LLM 形态——与我方「agent 互不对话 + 拓扑代码定」（ADR-028，常备否决）正面对立；否决清单的证据基从 dsh 一家扩到三家。
- agent-as-tool 原语与我方「agent 住节点内、由图调用」**同形**——可调单元一致，路由者不同（父模型 vs 编译图），主权轴差异在协调层再次出现。
- Mastra `description` 字段兼作**路由依据**（父模型按它挑 subagent），与 skills 的 name+description 渐进披露同源——description 在行业里普遍一身二任（触发 + 路由）。

## 7. 项目布局惯例（答录二轮，2026-08-21）

以"厂商中立的项目布局十一问"问两家文档 Ask AI，覆盖 prompt 组织 / 共享件 / agent 组织 / workflow 组织。

**Prompt 组织（两家唯一的硬惯例 = 与 agent 声明同址，无 central prompts/）**
- Mastra 三形态：`instructions.md`（固定文本，构建期内联进生成代码）/ `instructions.ts`（可计算——常量拼装，或 `({requestContext}) => string` 按请求求值）/ 构造器内联（长 prompt 不推荐）；目录结构 = 一 agent 一文件夹（`src/mastra/agents/<name>/`）。
- Agno：`INSTRUCTIONS = """..."""` 常量与声明同文件（`agents/<slug>.py`）；`instructions` 接受 callable（运行时求值，`instructions-via-function`）。

**其余各问的答案分布**
| 问题 | Mastra | Agno |
|---|---|---|
| 目录序列化（registry→prompt）的家 | 无文档 | 无文档（callable 模式 = 可住任何地方） |
| structured-output schema 的家 | 无明确文档（内部 tooling 见 types.ts 同址） | 与 agent 同文件 |
| 计划期词汇 / plan JSON 字段约定 | 无规范；内部 tooling 用 "task list / plan" 指预计算工作项 | 无规范；组合体 = steps/workflow |
| 共享件（lib/utils/shared）惯例 | 无文档（原话 "mostly unopinionated about how you organize or colocate your files"） | 无文档（模板仅 agents/ app/ db/） |
| provider 包装层的家与暴露形态 | 无文档 | 无文档（视作 tools 传给 agents） |
| agent 组织 | 中央 `agents/`（一文件夹一 agent + 目录发现自动注册 + `index.ts` 注册点）；无共享/私有区分 | 中央 `agents/`（一文件一 agent + `app/main.py` 列表注册）；无共享/私有区分 |
| workflow 组织 | 中央 `workflows/` + 每 workflow 一文件夹（steps.ts / workflow.ts / types.ts / utils.ts），手工组合（.then()/.map()） | 声明式 `steps=[...]` 构建期定拓扑 + `Router` 运行时分支 |
| 编译期 plan→DAG / 计划校验层 | 无文档（手工组合） | 无文档（声明即拓扑，校验隐含于构造器） |

观察：同址规则（prompt/schema 与声明同址）与中央 agents/ 是仅有的硬惯例；目录序列化归属、provider 包装、编译期图构建、计划校验层均为文档空白——我方注册表派生（目录 = 注册表自投影）、providers/ 拆分、编译器 + 出生地 ∀-check 落在自由领土，无惯例可违。

## 8. 与我们的座位对照（事实层，非拍板）

| 行业座位（四家一致） | 我们当前座位 |
|---|---|
| skill = 打包指令（SKILL.md，数据） | 指令包（预留词，未建） |
| tool = 可调能力（schema + execute） | 技能（skill，能力注册项，代码）+ tools（机械，确定性单元，禁 LLM） |
| instructions = agent 内联指引 | agent 声明 prompt 模板（agents/roster + 技能私有声明）+ persona 风格六件/guidelines（用户级内联指引） |
| Workflow / Step（orchestrator 裹执行体） | 编译图（节点 ≈ Step 裹单执行体；编译器 ≈ 编译期 Workflow builder） |
| skill 市场 / Team Skills | 配方（用户侧预设）/（无对应，未建） |

观察：行业 Agent 解剖 = Agent{instructions, skills, tools} 三字段分层；我们的对应层都已存在或有预留座位。两个消费侧差异：① skills 层——他们 runtime 模型自取 vs 我们装配期注入的规划方向，且两家均确认"always-on 内容官方座位 = instructions、装配期强制注入无先例"，故我方规划形态 = **skill 包格式 + instructions 式装配消费**的混形（行业无同名先例）；② tool 层——他们模型直调 vs 我们图调用（Agno custom Function step 为同族先例）。

## 9. 来源

- [Mastra Skills 文档](https://mastra.ai/docs/skills) · [Mastra Agents/Tools 文档](https://mastra.ai/docs/agents/tools) · [Mastra Subagents 文档](https://mastra.ai/docs/subagents)
- [Agno Skills Overview](https://docs.agno.com/skills/overview) · [Agno Loading Skills](https://docs.agno.com/skills/loading-skills) · [Agno Creating Skills](https://docs.agno.com/skills/creating-skills) · [Agno Workflows Overview](https://docs.agno.com/workflows/overview) · [Agno Teams 协作示例](https://docs.agno.com/examples/teams/basics/basic-coordination)
- Mastra / Agno 官方文档 Ask AI 答录两轮（2026-08-21）：一轮八问 = instructions 分界 / 覆盖语义 / 装配注入 / 确定性编排 / 版本治理 / 目录预算 / 工具组织 / 确定性标记（融入 §3–§5）；二轮十一问 = 项目布局惯例（§7）
- MiniMax 仓库解剖：`research/minimax-design.md` §11（2026-08-21 抓取）
