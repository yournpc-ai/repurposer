# 官网品牌宣传片：证据驱动 Brief、品牌档案与素材试制

> Status: 当前任务合同（2026-11-17，Iteration 1A 已落码；fake-provider/临时数据库/Web 自动验收及真实网页、准备阶段与集中作答已复验；首稿和后续媒体迭代尚未开始，不属于本批施工或验收面）。本合同收敛官网宣传片的集中澄清、品牌理解、素材试制和全链继承；实施状态与优先级以 `PROGRESS.md` 为准，现行作品、渲染与 Chat 规则仍以母文档为准。

## 0. 目标、范围与硬边界

### 0.1 目标

从“给某个官网做一只宣传片”开始，形成以下可重复工作流：

```text
官网证据
→ 缺失字段集中澄清
→ 可验证的品牌理解
→ 创意与脚本
→ 分场素材试制与真实 PNG/TTS 审阅
→ 锁定 CompositionVersion
→ 配音、字幕、音乐与合成
→ 技术/内容质检
→ 定向修复与复验
→ MP4 交付及后续衍生
```

首版不直接追求复刻一条 60 秒参考片，而是先完成 12–18 秒、两幕的完整薄片。**缩场景，不缩环节**；通过后再扩到六至八幕和 60 秒。

### 0.2 不做什么

- 保留通用人工审阅、费用和执行策略。Iteration 2 的验收旅程须在有效授权和预算内一次集中作答后自主完成，自主交互约束见子合同。
- 不复制参考 Agent 的临时终端命令、一次性 Python 脚本或 FFmpeg 工程；复用现有 `CompositionVersion → video-spec → Renderer`。
- 不新增作品根、第二意图入口、第二内容写口、第二时间轴、第三套 Agent loop 或完整 NLE。
- 不把网页原文当成品牌档案，不把提示词中的自我陈述当成已保存事实，不把读取文件路径当成看过图片。
- 不在第一轮同时建设完整品牌 CSS 引擎、结构化原创配乐、通用 3D、30 秒/竖屏衍生和局部渲染。
- 不因为参考片固定使用六张图、八幕、116 词、100 BPM，就把这些数值变成所有宣传片的模板约束。

## 1. 参考流程与当前证据

### 1.1 参考流程提供的外部行为

参考记录展示的顺序是：

1. 先查看官网定位、品牌视觉和核心卖点；
2. 一次收集创作方向（用途与表达方式）、时长、配音语言、字幕语言和画幅；
3. 获取并实际查看多张 PNG，向用户反馈品牌理解；
4. 按分镜生成视觉素材并再次查看；
5. 生成和测量配音，制作字幕、音乐和音效；
6. 进入合成、抽帧检查、修复和最终交付。

这能证明外部产品行为，不能仅凭截图证明其内部是一次工具调用还是多次调用被 UI 合并。我们要复制的是**证据顺序、实际媒体检查和局部反馈闭环**，不是其内部实现形态。

### 1.2 当前已验证的产品基础

- 官网采集支持动态 DOM、滚动加载、交互状态、视图截图和不可变 SourceSnapshot。LegitEvi 的既有 dry-run 已取得使命、三类受众、AI 转译、原始宣言、5 张 2× 视图和两个子页面。
- 当前已有真实 `CompositionVersion`、Track/Clip/Object、整数 ticks、原生文字动画、固定媒体、TTS、真实字幕 cues、Renderer 和 Output。
- 既有定向测试覆盖 video-spec、render probe、音频信号和 TypeScript；24fps/60 秒可纯编译为 1440 帧。上述均不等于同输入 60 秒成片已实测。
- 当前已有局部 Generator 预览修复、真实 Output 抽帧 reviewer、不可变版本和定向修订，但最终内容质检与自动修复闭环仍不完整。

### 1.3 主要差距按制作顺序

| 制作环节 | 当前差距 |
|---|---|
| 制作 Brief | 官网片必填槽位与集中缺失分析已接；其他任务默认值与完整输入识别仍需真实对话校准 |
| 官网证据 | 已有每轮纯 Readiness 门；真实 LegitEvi 采集与刷新恢复未验收 |
| 品牌理解 | 已有带来源/置信度的 BrandProfile 和真实 PNG 输入；真实网站的事实覆盖、冲突与未知项质量未验收 |
| 创意脚本 | 英文叙事质量、品牌首次出现时间和全片事实审计未形成稳定合同 |
| 分镜时间 | 时间轴强，但缺少脚本—TTS—镜头时长的全局优化 |
| 视觉素材 | 模型图片通常在正式制作后才生成，制作前无法完成参考式 PNG 筛选重做 |
| 动态排版 | 原生能力较强，实际安全区、字体、遮挡和连续运动仍需成片验证 |
| 英文配音 | 真实时长适配已接；全片超时后的自动改稿和专业人声处理不足 |
| 字幕 | 真实 cues 是优势；长句拆分、缺字、遮挡、对比度和 SRT sidecar 不足 |
| 音乐混音 | 以库曲为主；结构化配乐、自动 ducking、sonic signature 和音频硬指标不足 |
| 渲染交付 | MP4 链真实存在；完整解码、部分封装指标和生产环境验收未全部硬化 |
| 质检修复 | 技术 probe 与按需 reviewer 存在，但“发现→局部修复→复验”未形成统一闭环 |
| 衍生复现 | 固定执行复现较强；30 秒/竖屏需要语义重作，完整 spec 改变后仍整片渲染 |

## 2. 两个领域对象，而不是两个新作品根

### 2.1 现有结构不能简单说成“没有”

当前已有：

- `Brief`：`topic / audience / tone / constraints[] / material_state / asked`，槽位带 `user-stated / inferred / default` 来源，代码负责合并，见 `apps/api/app/models/schemas.py:2186-2305`。
- `PendingPlan.brief`：计划阶段的持久工作 Brief，见 `apps/api/app/models/schemas.py:2530-2597`。
- `WebPageResearch` 与 `SourceSnapshot.meta`：保存网页正文、引用行、视图、元素和采集事实，见 `apps/api/app/models/schemas.py:98-123`、`apps/api/app/models/tables.py:410-442`。
- `CompositionVersion`：保存 settings/sources/scenes/timeline/skill_provenance/content_digest，见 `apps/api/app/models/tables.py:535-564`。
- `Conversation.context`：保存已完成的工具交换和媒体证据，不是作品状态或 Brief 的权威存储，见 `apps/api/app/chat/conversation_context.py:1-5`。

它们分别覆盖了通用路由 Brief 和原始品牌证据，但还不是完整的 `CreativeBrief` 与 `BrandProfile`。

### 2.2 为什么仍然是两个结构

`CreativeBrief` 和 `BrandProfile` 回答不同问题、拥有不同来源和变化原因：

| 对象 | 回答的问题 | 主要来源 | 变化原因 |
|---|---|---|---|
| `CreativeBrief` | 用户到底要做什么片子 | 用户原话、集中回答、明确默认 | 用户补充或改变制作目标 |
| `BrandProfile` | 这个品牌是谁、官网证据支持什么 | SourceSnapshot、CSS/DOM/截图、用户纠正 | 网站更新、证据补充、品牌理解修正 |

把二者合并会导致：

- 用户的制作目标与官网事实相互覆盖；
- 无法区分 `user-stated` 与 `inferred`；
- 网站更新时误改用户已经确认的用途、时长和语言；
- 无法判断一条品牌结论是证据事实还是创意推断。

**两个领域对象不等于两张表，也不等于两套作品模型。**代码上优先扩展现有 `Brief`，不要新建平行 `BriefV2`；需要强调创作语义时使用 `CreativeBrief` 作为领域称谓。`BrandProfile` 是新的派生值对象。跨阶段只传递一个 `CreativeState`，以 `brief` 和 `brand_profile` 两个属性分别承载二者，不扩散成多个顶级字段。

### 2.3 CreativeBrief：扩展现有 Brief

保留现有字段及合并规则，新增宣传片所需的一等槽位：

```text
production_direction    一项完整的创作方向，例如「在官网首页用产品演示说明工作原理」
target_seconds          目标秒数，整数
narration_language      每个 Scene 的单一配音语言
subtitle_languages      字幕语言数组
aspect                  16:9 / 9:16 / 1:1
voice_requirements      音色、语言、克制程度等用户要求
must_include            必须保留的表达、Logo、宣言、网址等
avoid                   禁用事实、风格、虚构 UI、营销数据等
success_criteria        本片的验收重点
```

要求：

- 新槽位继续使用 `BriefSlot` 和来源优先级，不从 LLM 文本反向覆盖 `user-stated`。
- 新问卷将方向保存为单个字符串，时长、配音语言、字幕语言、画幅各有自己的题目和答案。旧 Brief 中的 `purpose` 和 `narrative_mode` 继续可读，只给出其中一项时，提问沿用该信息。
- `target_seconds / aspect` 与 `design.py` 已有显式约束使用同一映射，不能形成正则解析与 Brief 两套真相。
- `subtitle_languages` 是值数组；集中回答的 `answers[]` 是另一层协议，不要混为一谈。
- `asked` 由代码按槽位维护，支持一组问题，不把“组数”当成已经问过哪些槽位。
- 缺失项由当前任务类型和已有值计算，不把 `PREPARING/AUTHORING/REVIEWING` 持久阶段字段塞进 Brief。

### 2.4 BrandProfile：带来源的品牌派生值对象

```text
schema_version
source_refs[]            SourceSnapshot id + digest + view/line 引用
extractor_version
positioning              定位、使命、受众
claims[]                 产品主张；每项带 citable line 和事实/推断标记
taglines[]               官网原有宣言和辅助语
colors[]                 色值、用途、来源、置信度
typography[]             字体候选、字重、来源、置信度
brand_assets[]           Logo / Wordmark / 图标及固定媒体引用
creative_direction       美术方向、媒介偏好、避免项，明确标记为 inferred
unknowns[]               无法确认的信息
conflicts[]              多页面、CSS、截图或用户纠正之间的冲突
content_digest
```

约束：

- CSS/DOM 直接取得的事实与视觉模型推断必须分开；只看到截图时只能写“接近 Inter”，不能写“官网字体就是 Inter”。
- 原始 SourceSnapshot 永不被品牌理解覆盖。用户纠正和后续提炼作为带来源的新版本，不原地修改旧证据。
- `creative_direction` 是创作解释，不伪装成官网原话。
- 初版不需要覆盖所有网站的所有 CSS；先支持主色、字体候选、Logo/Wordmark、宣言和核心事实。

### 2.5 命名与心智负担：一个 CreativeState，两个属性

代码上的创作简报继续使用现有 `Brief`，需要强调领域语义时称 `CreativeBrief`，不采用容易与 `Production Intent / produce_video` 混淆的 `ProductionBrief`。`BrandProfile` 保留，但限定为“本项目、特定 SourceSnapshot 派生的品牌档案”，不是全局品牌手册，也不是 `persona.brand`。

跨阶段只传递一个 `CreativeState` 对象，内部保留两个独立属性，避免维护五套顶级字段：

```text
CreativeState
├── schema_version
├── brief                 用户制作目标，即扩展现有 Brief
├── brand_profile         官网证据派生的品牌理解
├── source_refs[]         仅保留 SourceSnapshot 身份，不复制原始证据
└── content_digest
```

它是一个状态载荷，不是新的作品根，也不把两种语义合并。`brief` 与 `brand_profile` 仍分别更新；`GenerationContext`、Chat `RunContext`、Agent `RequestContext` 仍只承担执行装配，不与该对象混用。

## 3. 全生命周期的正确存放方式

### 3.1 当前存储断点

- `projects.pending_brief` 在 Start 后清空，见 `apps/api/app/chat/service.py:2379-2382`。
- `run.context.confirmed_scope` 保存任务、报价和确认设置，不保存完整 Brief/BrandProfile，见 `apps/api/app/chat/service.py:2395-2411`。
- `CompositionVersion` 当前没有制作 Brief 或品牌档案字段。
- `Conversation.context` 只保存工具历史，且会按预算折叠，不能承担长期权威真相。
- `SourceSnapshot` 是不可变事实，不能为了补写品牌理解而原地 `UPDATE meta`。

因此，当前**没有一套让两类信息贯穿全程的正确完整机制**，但有可复用座位，不需要新作品根。

### 3.2 世界级实现的参考结论

- [OpenAI Agents SDK — Sessions](https://openai.github.io/openai-agents-python/sessions/) 管会话历史；[Context management](https://openai.github.io/openai-agents-python/context/) 明确区分本地 run context 与 LLM 可见上下文，且 run context 不等于会话状态。对应结论：Conversation 不能替代 CreativeState，单次 Run 的上下文不能替代长期作品版本。
- [LangGraph — Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 将 thread-scoped checkpointer 与跨 thread Store 分开。对应结论：当前创作线程的恢复状态与作品/品牌长期事实不是同一种存储。
- [Mastra — Request context](https://mastra.ai/docs/server/request-context) 用于请求期数据，并明确区别于 agent memory；其动态 instructions/tools 也支持按真实请求状态投影。对应结论：执行期输入与提示词投影可以复用，但不能把请求期数据当长期作品版本。
- [Temporal — Workflow Definition](https://docs.temporal.io/workflow-definition) 推荐单个对象承载 workflow 输入，并要求 replay 确定性。对应结论：Run 的输入必须固定且可恢复，不能在恢复时读取“当前最新 Brief/Brand”。

这些实现支持的是**分层存储**：会话历史归会话，创作中状态归 PendingPlan，不可变作品归 CompositionVersion，执行输入归 Run，交付只保留版本引用。统一的是 `CreativeState` 的数据形状，不是把所有表和生命周期强行合并。

### 3.3 从五个座位压缩为“两个权威家 + 两个引用面”

| 层次 | 存储形状 | 是否权威副本 |
|---|---|---|
| 创作中（可修改） | `PendingPlan.creative_state` | **权威家 1：创作中状态** |
| 作品版本（不可变） | `CompositionContent.creative_state` → `CompositionVersion.creative_state` | **权威家 2：作品版本** |
| 素材试制 Run（尚无版本） | `run.context.creative_state` | 必要的执行期固定副本，不是第三个长期家 |
| 正式 produce Run | 只读 `version_ref` 指向的版本 | **引用面，不复制** |
| Output | 沿用现有 composition/version/content_digest provenance | **引用面，不重复存全文** |
| Conversation.context | 仅作工具历史和媒体投影 | 不是权威存储 |

工作草稿不另设独立座位：它直接携带未来 CompositionContent 的同一个 `creative_state`，保存时进入 CompositionVersion。

必要改动：

- `PendingPlan` 增加可选 `creative_state`，其中 `brief` 为扩展现有 Brief；旧数据按缺省/空值读取。
- `CompositionContent` 与 `CompositionVersion` 增加可选 `creative_state`；新版本写入，历史版本为 NULL。
- `editing/store.py` 将整个对象纳入版本内容和 digest；`editing/service.py` 在修订时保留未改部分。
- 素材试制尚无 CompositionVersion 时，必须把同一对象复制进 `run.context`；正式 produce 已有版本时只读 `version_ref`，不重复复制。
- Output 继续使用现有 composition/version/content_digest provenance，不新增 CreativeState 全文或多余 digest。
- 初版不新增 `creative_briefs` / `brand_profiles` 两张主表。若后续证明同一品牌需要跨作品、跨 Chat 复用，再单独评审内容寻址的派生表，不能提前建大层。

### 3.4 不变量

1. 原始网页证据与派生品牌理解分开，用户制作目标与网站事实分开。
2. `pending_brief` 清空不等于 Brief 丢失：保存版或素材试制 Run 必须已有不可变 CreativeState。
3. 一个 CompositionVersion 只对应一个 CreativeState；Run 永不读取“当前最新品牌理解”。
4. 旧 Output 的 Brief/Brand 永不随后续版本或网站更新而变化。
5. 模型不得直接写这些表；所有持久化都经过现有工具执行体、编辑写口或 Run 上下文写口。
6. 不把 `persona.brand` 当作本项目的 BrandProfile；前者是用户长期视觉皮肤，后者是本片官网证据解释。
7. `GenerationContext`、Run/RequestContext 只做执行装配；它们不是作品内容，不新增平行 context 名词。

## 4. 集中澄清：一次交互、多个必要字段

### 4.1 新产品规则

把当前“每轮最多一个问题”改为：

> **每轮最多一次澄清交互；一次交互可以集中询问多个必要字段。**

LLM 负责判断哪些字段缺失、为什么值得问；代码负责已知字段去重、槽位合法性、默认值、来源优先级和答案校验。已经由用户明确给出的字段不得重复询问。

这里的“分页”是**同一问题组在客户端分页展示**，不是服务端对消息行分页。仍只保留一个 pending question 行，现有单一待决、auto-bail、刷新恢复和 Stop 语义不破坏。

### 4.2 建议的数据形状

新增问题项：

```text
BriefQuestionItem
├── slot                 production_direction / target_seconds / narration_language / subtitle_languages / aspect
├── question             用户可读问题
├── options[]            与当前单问相同的 Option
├── recommended_id       可选推荐项
├── allow_freeform
├── required             必须回答还是允许默认
└── default_path         未回答时的安全默认
```

`QuestionPayload` 以 additive 方式增加：

```text
items: BriefQuestionItem[] = []
group_digest: str | None
```

现有 `question/options/slot/default_path` 保留给单问和历史行；当 `items` 非空时按问题组渲染。`group_digest` 由服务端根据问题组内容和 Brief 基线计算，模型不得提交。

最终数组提交：

```json
{
  "kind": "group",
  "group_digest": "server-issued-digest",
  "answers": [
    {"slot": "production_direction", "kind": "freeform", "text": "官网首页，用产品演示说明工作原理"},
    {"slot": "target_seconds", "kind": "freeform", "text": "45"},
    {"slot": "narration_language", "kind": "option", "option_id": "1"},
    {"slot": "subtitle_languages", "kind": "option", "option_id": "2"},
    {"slot": "aspect", "kind": "option", "option_id": "1"}
  ]
}
```

服务端必须：

- 校验 pending 行、group_digest、槽位白名单、重复答案、required 和 option 归属；
- freeform 非空且有长度上限；
- 一次原子结算同一问题行并回填全部槽位；
- 将答案来源标为 `user-stated`，默认值不得冒充用户回答；
- `AnswerPayload` 增加 group 形态和 `answers[]`，保留旧 option/freeform/bail/start；
- 重放同一请求幂等，过期 digest 或已结算返回 409；
- 不允许多个 pending question 组，不为每页创建一个 pending 行。

### 4.3 前端与接口联动范围

不能只改 `QuestionPayload.items`；当前全链都是单问结构，必须同步：

- `apps/api/app/models/schemas.py`：PlanAskArgs/ChatAskArgs、QuestionPayload、AnswerRequest、AnswerPayload。
- `apps/api/app/chat/routes.py`：`question.preview` 携带 items/group_digest。
- `apps/api/app/chat/plan_turn.py`：问题组 dock、Brief 合并和恢复。
- `apps/api/app/chat/service.py`：数组答案原子结算与旧单问兼容。
- `apps/web/src/lib/chatStreamFrames.ts`：预览类型。
- `apps/web/src/components/chat/timeline/types.ts`：QuestionPayload、QuestionAnswer、QA items；当前类型本身也未完整声明所有运行时字段，应一次补齐。
- `apps/web/src/components/chat/timeline/history.ts`：问题组历史映射和答案文本。
- `apps/web/src/components/chat/QuestionDock.tsx`：同一组件支持 items 分页，不新增按 kind 分裂的第二套 Dock。
- `apps/web/src/components/chat/ChatDock.tsx`：识别问题组，保存分页和草稿答案，最终一次提交。
- `apps/web/src/components/chat/AnsweredQuestion.tsx`：支持多项 Q/A 归档，不强制拼成一段字符串。
- en/zh i18n、相关 vitest 和 core tests。

### 4.4 分页和预览的交互要求

- 默认每页恰好 1 个字段，支持下一页/上一页；页码只住客户端。
- 草稿答案以 `question.id + group_digest` 为键保存在 ChatDock，不能因 full/panel 形态切换或信封替换而丢失。
- 最后一页一次提交 `answers[]`，不是每页各创建一个问题或一次 Run。
- 顶层 `options.length > 0` 不再是唯一显示条件；`items.length > 0` 同样进入选项问形态。
- preview 期选择沿用现有寄存语义，真实问题行落库后再发射；被拒问题组全部撤回。
- × 跳过整组未答字段并按 default_path 续行；不得把跳过写成 user-stated。
- 保留键盘、屏幕阅读器、双主题、长文本换行和移动端的可用性。

## 5. 真实输入的当前提示词与问题

### 5.1 证据边界

本次“给 https://www.legitevi.com/en 做一只宣传片”已有真实 provider trace。最终数字选项作答项目为 `655521c2-a0dd-46df-b8d8-cc85e77fbd17`，完整请求、实际 System/User、tools、响应和折叠记录见 `scratch/website-promo-batch1-canonical-answers-20261117/trace/`；问题组与媒体生命周期摘要见同目录 `context-audit.json`。persona、UI locale、浏览器 surface 和用户确认设置仍会影响其他请求，跨账户逐字比较必须先固定 golden wire。

### 5.2 当前装配顺序

```text
Home useProjectLaunch
→ POST /chat，message 为原话；本例无附件、无显式 Skill
→ prepare_chat_turn：新项目无 Run，进入 plan path
→ PlanTurn.assemble
   ├─ prime_web_page_captures_from_text：URL 创建为 PENDING WEB_PAGE 资产
   ├─ 读取 assets/brief/persona/pending/确认设置
   └─ 准备 material excerpt/understanding（新项目尚未完成采集时为空）
→ resolve_chat_skill：当前别名不会命中“宣传片”这一泛称，故 skill=None
→ assemble_video_round
   ├─ compute_source_readiness 读取当前 Asset/SourceSnapshot/CreativeState
   ├─ 正文或必要 PNG 未就绪时直接解析为 source_preparing
   └─ video_round_tools 只保留当前合法动作
→ intent_router.call_loop
   ├─ System：chat/system.j2 的视频专属分支 + 当前阶段规则
   ├─ User：plan 分支的用户原话和上下文
   └─ tools：首轮实际仅 prepare_video_materials / answer
→ 每次 continuation 重新读取世界并投影：analyze_brand → 集中 ask_user → draft_build
```

关键代码：`apps/api/app/chat/readiness.py`、`apps/api/app/chat/prompts.py`、`apps/api/app/chat/turn_tools.py`、`apps/api/app/chat/plan_turn.py`、`apps/api/app/agents/tool_loop.py`。

真实首轮和 golden wire 均为 `stage=source_preparing`，不存在先按 design_video 得到 draft_build、再撤工具的投影顺序。业务上处于 plan path 不等于渲染 `plan_mode.j2`。

### 5.3 首个请求中确定或典型的内容

本轮实际 System 来自 `apps/api/app/prompts/chat/system.j2` 的 `video_stage != "none"` 分支，开头为：

```text
You are the user's video agent at Rookie Cut. Work from the user's request and the server-derived current round.
Every message text is speech to the user; never put speech into tool arguments.
Close with exactly one terminal tool after any needed non-terminal work.
```

随后注入：

- answer/ask_user/其他工具的约束和 read-tool 规则；
- `_video_project` 当前阶段的官网证据规则与诚实边界；
- source_preparing 的素材准备和禁止提前提问/设计规则；
- pending_question、rejection 和 interim prose 规则。

`apps/api/app/prompts/chat/plan_mode.j2` 也存在“普通视频请求先准备素材”和“只在真正缺答案时提问”的规则，但**本例的实际阶段投影不采用该模板**，不能把 plan_mode 的文本直接当成本次线上 System 原文。

User 侧按 `apps/api/app/prompts/chat/user.j2` 的 plan 分支组装，典型为：

```text
System（顶层唯一语言规则）: Speech language: reply in the language of the user's CURRENT message ...
User message: 给 https://www.legitevi.com/en 做一只宣传片
The brief so far ...:
- material: none
Confirmation settings: execution=auto, spending=auto.
No file uploaded (text-only input).
```

其中：

- persona 行取决于账户，不能编造；
- 若 UI 是中文，会附加中文回复/镜像用户语言规则；
- surface=canvas 时另有 workspace 提示；
- 没有历史 pending question、presented plan 或 pinned Skill；
- `CURRENT VIDEO ROUND` 作为动态世界事实另行注入，本例首轮包含 `video_stage=source_preparing`、六项缺失 Brief 和 `required_next_action=prepare_video_materials`。

### 5.4 修复前核对出的问题（历史基线）

以下清单记录修复前的代码核对，不表示这些缺口在当前工作树仍然存在；当前证据与剩余失败见 §6 的 Iteration 1A 实施状态及 `VERIFICATION.md`。

1. **证据顺序不受保证**：URL 已入队不等于官网已读完；`ask_user` 可以先于实际页面证据被调用。
2. **Brief 槽位不足**：时长、画幅、配音语言、字幕语言和用途主要依赖自由 constraints 或其他正则路径，不能统一集中提问与回填。
3. **一轮一问不适合品牌宣传片**：可能先问 topic 或直接进入默认创意，而不是集中确定四个制作变量。
4. **没有品牌档案步骤**：没有强制先查看实际 PNG、形成带来源的品牌理解后再进入脚本。
5. **普通“宣传片”不自动绑定固定 promo Skill**：不能假设已经获得 Shotcraft 的默认旁白、音乐和镜头方法；增加一个别名也不能解决证据顺序。
6. **等待状态文案不完整**：URL 资产已创建时仍可能出现 `No file uploaded`，而网站采集 pending 与文件 processing 不是同一提示路径。
7. **阶段与工具需要统一理解**：`resolve_video_stage` 先得到 draft_build，`video_round_tools` 后才隐藏 design_video；虽然可以表达“准备中”，但缺少一个明确的“官网证据和 Brief 尚未就绪”阶段合同，不能仅靠模型理解为什么当前不能设计。
8. **缺少可重放 golden wire**：不能靠口头描述判断提示词是否优化，必须保存脱敏后的真实装配请求并验证工具与证据顺序。

### 5.5 任务类型不等于 Skill 绑定，不向模型展示 Skill 注册表

上一版“展示 `AVAILABLE VIDEO ROUTES`”会把任务分类和 Skill 绑定混在一起，容易让模型过早进入 Skill 路径，现予以撤销。参考截图里的“我先看一下这个网站的定位、品牌视觉和核心卖点，再据此确定宣传片的风格与结构”只是用户可见的 assistant prose，**不能据此推断其隐藏 System prompt，也不需要模仿成一段四类视频/Skill 清单。**

本方案只增加一个轻量的内部任务判断：

```text
task_kind = website_promo | talking_head | text_animation | knowledge_explainer | generic
```

它只回答“当前需要哪类证据和哪些 Brief 字段”，不回答“使用哪个 Skill 包”。`task_kind` 与现有 `skill_reference` 是两个不同概念：

- `task_kind` 决定证据门：网站宣传片先读取官网，再判断缺失字段；
- `skill_reference` 仍只来自用户显式 chip 或现有唯一自然语言匹配；
- 没有 `skill_reference` 时不注入任何包清单、包方法或 Skill 绑定；
- Brief 完成后才评估是否需要/继续使用 Skill，不能为了证据门而强制绑定。

因此，LegitEvi 首轮不需要看到四种流程或四个 Skill。当前只需要类似下面的单一工作指令：

```text
这是网站品牌宣传任务。先读取该网站的定位、品牌视觉与核心卖点；
在证据就绪前不要询问创作风格或生成分镜，证据就绪后再判断还缺哪些制作信息。
```

其他 task_kind 使用各自的证据要求，不套用官网门；generic 请求不强行进入任何固定流程。这样既保留四类任务的可扩展性，也不把模型提前送进 Skill。

### 5.6 阶段投影到底是什么

“阶段投影”不是再建一个工作流引擎，也不是给数据库增加一个阶段字段。它的含义是：

> **每次模型调用前，服务端根据当前真实世界，重新决定这一轮给模型看哪份说明书、哪些事实和哪些工具。**

当前已有 `round_assembler → resolve_video_stage → video_round_tools → chat_system` 这条投影链。新增的只是 draft_build 之前的两个读面，不是第三套 loop。

以 LegitEvi 为例：

#### 第 1 次模型调用：官网尚未读完

服务端投影：

```text
stage = source_preparing
user = 给 https://www.legitevi.com/en 做一只宣传片
facts = URL 已创建，正文和 PNG 尚未就绪
tools = prepare_video_materials / answer
```

模型只能先调用 `prepare_video_materials`。此时不能 `design_video`，也不能问“喜欢什么风格”这种应该基于品牌证据回答的问题。

#### 第 2 次模型调用：官网已读完，但 Brief 不完整

工具结果带回 SourceSnapshot、citable lines 和实际 PNG。服务端重新投影：

```text
stage = briefing
facts = 官网正文、PNG、已有 Brief 槽位、缺失槽位、当前 CreativeState
tools = analyze_brand / answer（无当前 BrandProfile）
```

BrandProfile 落库后的下一次调用只投 `ask_user / answer`，由模型生成简短邀请并一次收集缺失项。用途与表达方式共同决定创作方向，时长、配音语言、字幕语言和画幅各自独立。两个 briefing 读面都不暴露 `design_video`。

如果用户最初已经给全参数，就不调用 ask_user，直接确认 Brief 后进入下一步。

#### 第 3 次模型调用：答案已回填，Brief 与 BrandProfile 就绪

服务端再次投影：

```text
stage = draft_build
facts = 完整 Brief、BrandProfile、SourceSnapshot
tools = design_video / Skill reads / material preparation / answer
```

这时才恢复分镜创作和后续 Skill 路径。

所以它不是人工推进 `source_preparing → briefing → draft_build` 三个数据库状态，而是每次根据“官网是否读完、Brief 是否完整、是否已有草稿”重新计算。**存的是 Brief、BrandProfile 和作品数据；阶段只是这些事实的当轮读法。**

### 5.7 为什么只加提示词不够

如果只写“先看官网，再判断缺失字段”，模型仍可能在第一次调用时先问问题或先出方向，因为 `ask_user` 和 `design_video` 都在工具列表里。

阶段投影同时做两件事：

- System 只描述当前该做什么，减少歧义；
- tools 只开放当前合法动作，保证即使模型判断失误也无法越过证据门。

这与 Mastra 根据 RequestContext 动态生成 instructions/tools 的思路一致：不是增加另一个 Agent，而是让同一个 Agent 在正确事实和正确能力下工作。

## 6. 分轮实施路线

所有批次共用同一当前工作面投影与直接 Op 修订协议：模型每轮只读取当前目标、相关来源、实际选区和兼容工具；局部修订以一批 Op 原子落版，不另长 action 翻译层。需要现场编写视觉公式或专用代码时，只能使用目标 Clip 内受控 Generator，并经隔离 runner 固定媒体；不恢复任意 Shell 或专用生产脚本。后续批次的素材审阅、局部修复、精确编辑和衍生均复用这一底座。

### Iteration 1：官网证据、集中 Brief、品牌档案

不生成付费媒体。

- 扩展 Brief 与 BrandProfile 和全链存储。
- 完成问题组 API、SSE、QuestionDock、历史 Q/A 和旧单问兼容。
- 完成 source_preparing/briefing 投影与 golden wire。
- LegitEvi 验收：缺字段时集中问清；完整输入不重复问；#DC0000、红黑白、Wordmark 和原始宣言有证据；字体推断不冒充 CSS 事实。

出口：刷新后 Brief/Brand 可恢复，Start 后仍能从试制 Run 或 CompositionVersion 回读，不新增作品根。

### Iteration 1A：装配修复的详细施工方案

#### 1. 先修判定顺序，而不是先改长提示词

当前真实问题是：`resolve_video_stage` 先因为已声明 `design_video` 得到 `draft_build`，`video_round_tools` 随后才因证据未就绪移除它。System 因而看似可以创作，实际官网证据尚未完成。

本批必须将判定改为**先读真实 readiness，再投影阶段**：

```text
if task_kind == website_promo:
    if 官网正文或必要 PNG 未就绪:
        stage = source_preparing
    elif Brief 或 BrandProfile 未就绪:
        stage = briefing
    else:
        stage = draft_build
else:
    沿用现有阶段解析
```

`task_kind` 只决定证据要求，**不是 Skill reference，不展示 Skill 注册表，不强制绑定 promo-video**。

#### 2. 新增纯计算 SourceReadiness，不新增持久阶段字段

建议座位：`apps/api/app/chat/readiness.py`（若评审认为应留在 `turn_tools.py`，不新增模块也可以，但必须纯函数、无 DB/LLM IO）。

输入使用当前已有事实：

```text
用户原文中的 URL
Asset.processing_status / meta.research / meta.shots
SourceSnapshot / views / citable_lines
PendingPlan.creative_state.brief / brand_profile
当前工作草稿
```

输出：

```text
task_kind
has_url
capture_pending / capture_failed / capture_ready
text_ready
required_views_ready
brief_missing_slots[]
brand_profile_ready
draft_present
required_next_action
```

约束：

- 每轮重新读取世界事实并计算，不将 `source_preparing/briefing` 写进数据库；
- `required_views_ready` 不只是 `shots` 非空，还要满足当前宣传片所需页面证据；
- 采集失败不得被当成 ready，也不得生成 BrandProfile；
- `required_next_action` 只由代码推导，模型不得提交。

#### 3. 三轮 System、上下文和工具的完整投影

| 轮次 | 进入条件 | System 允许做什么 | 工具白名单 |
|---|---|---|---|
| `source_preparing` | URL 存在，正文/必要 PNG 未就绪 | 只准备网站证据，说明真实等待；不得问创作偏好或出分镜 | `prepare_video_materials / answer` |
| `briefing` | 官网正文和必要 PNG 已可读，Brief/BrandProfile 未完成 | 形成 BrandProfile、反馈事实/推断/未知、集中问缺失字段 | `analyze_brand / ask_user / answer` |
| `draft_build` | 必填 Brief、BrandProfile、SourceSnapshot 均就绪 | 恢复分镜、素材和后续 Skill 路径 | `design_video / 必要 Skill reads / preparation / answer` |

非 `website_promo` 不套用上述门；generic 请求保持通用路径。采集失败时只允许 `answer` 说明失败和可行恢复路径。

#### 4. `source_preparing` 的提示词样例

System 增量规则保持短小：

```text
这是网站品牌宣传任务。先读取该网站的定位、品牌视觉和核心卖点。
在正文和必要页面图像就绪前，不要判断创作风格、不要提出制作问题，
不要生成图片、配音或分镜。
```

动态上下文改为：

```text
CURRENT ROUTE: website_promo
CURRENT READINESS:
- URL: https://www.legitevi.com/en
- Capture ready: false
- Text ready: false
- Required views ready: false
- Brief ready: false
REQUIRED NEXT ACTION: prepare_video_materials
```

不再用 `No file uploaded (text-only input)` 描述 URL 资产，改为：

```text
Website capture is pending for this URL.
The page is not readable evidence yet.
```

用户可见的第一句可以是“我先看一下这个网站的定位、品牌视觉和核心卖点，再据此确定宣传片的风格与结构”，但其后只能先调用准备工具。

#### 5. `briefing` 的提示词样例

```text
先根据官网正文和实际页面图像形成品牌理解。
区分已确认事实、视觉推断和无法确认的信息。
然后只询问仍然缺失、且会改变制作方案的信息；已经给出的字段不得重复询问。
在 Brief 和品牌档案就绪前，不要生成正式视觉、配音或分镜。
```

动态上下文：

```text
CURRENT ROUTE: website_promo
CURRENT READINESS:
- Capture ready: true
- Text ready: true
- Required views ready: true
- Brand profile ready: false
- Brief missing slots: [production_direction, target_seconds, narration_language, subtitle_languages, aspect]
REQUIRED NEXT ACTION: analyze_brand
```

`analyze_brand` 完成后，若仍有缺失字段，下一动作是一次集中 `ask_user`；若字段已全，直接确认 Brief 并进入 `draft_build`，不为了形式而提问。

#### 6. `analyze_brand` 的合同

这是准备工具，不是付费生成 Run，也不是读取文件路径的伪视觉检查。

输入：

```text
citable_lines[]
SourceSnapshot refs[]
实际 PNG media inputs[]
当前 Brief 槽位
```

输出并写入 `PendingPlan.creative_state.brand_profile`：

```text
positioning / claims / taglines
colors / typography / brand_assets
creative_direction（必须标 inferred）
unknowns / conflicts
source_refs / extractor_version / content_digest
```

要求：

- PNG 必须作为真实视觉内容进入模型请求，不能只传路径；
- CSS 未确认字体时只能写“接近 Inter”；
- 原始 SourceSnapshot 不被覆盖；
- 失败时没有 BrandProfile，也不编造创意方向；
- 工具执行体通过独立短事务保存派生结果，LLM 不直接写 DB。

#### 7. 集中澄清与数组答案

LLM 判断缺失字段，服务端去重后一次返回多个 `BriefQuestionItem`。前端在同一 pending 行中分页展示，最后一次提交：

```json
{
  "kind": "group",
  "group_digest": "server-issued-digest",
  "answers": [
    {"slot": "production_direction", "kind": "freeform", "text": "官网首页，用产品演示说明工作原理"},
    {"slot": "target_seconds", "kind": "freeform", "text": "45"},
    {"slot": "narration_language", "kind": "option", "option_id": "1"},
    {"slot": "subtitle_languages", "kind": "option", "option_id": "2"},
    {"slot": "aspect", "kind": "option", "option_id": "1"}
  ]
}
```

后端一次原子结算并回填 `PendingPlan.creative_state.brief`。不得为每页创建问题或 Run，不得将默认值冒充 `user-stated`。

#### 8. CreativeState 的存储落地

只使用一个对象：

```text
CreativeState
├── schema_version
├── brief
├── brand_profile
├── source_refs[]
└── content_digest
```

继承链：

```text
PendingPlan.creative_state
→ 工作草稿中的同一对象
→ CompositionVersion.creative_state
→ 尚无版本时的 run.context.creative_state
→ 正式 produce 只读 version_ref
→ Output 沿用现有 composition/version/content_digest
```

不另建作品根或两张主表，不重复保存到 Output，不将 Conversation.context 当权威存储。原始网页证据继续由 SourceSnapshot 保存。

#### 9. 实际施工顺序

按以下顺序小步提交，每一步必须保留可回归状态：

1. `chat/readiness.py` + 纯函数测试：覆盖 pending/ready/failed、缺图、Brief 缺失、非 website_promo。
2. `turn_tools.py::resolve_video_stage` + `video_round_tools`：先 readiness，后工具投影；不再仅凭 design_video 是否声明决定 draft_build。
3. `prompts.py::assemble_video_round` + `chat/system.j2` + `_video_project.j2`：注入 route/readiness/required_next_action 和对应短规则。不要只改 plan_mode.j2，因为本例不使用它。
4. `analyze_brand` + `PendingPlan.creative_state`：真实 PNG 输入、派生结果校验与独立短事务。
5. 问题组后端：`models/schemas.py`、`plan_turn.py`、`service.py`、`routes.py`，完成数组答案和原子结算。
6. 问题组前端：`chatStreamFrames.ts`、`timeline/types.ts`、`timeline/history.ts`、`QuestionDock.tsx`、`ChatDock.tsx`、`AnsweredQuestion.tsx` 和 en/zh i18n。
7. `CompositionContent/CompositionVersion.creative_state` 及 Alembic migration、digest、修订继承和试制 Run 继承。
8. golden wire 与 LegitEvi 用户旅程。真实模型/网页联调另行授权，不能以 fake provider 结果冒充真实成片通过。

#### 10. 本批必须通过的 golden wire

用 fake provider 捕获实际 `messages` 和 tools，不调用真实模型：

- 新 URL 未采集：`stage=source_preparing`；无 `design_video`、无创作型 `ask_user`；下一动作只能 `prepare_video_materials`。
- 官网完成：`stage=briefing`；BrandProfile 输入含真实正文和必要 PNG；仍无 `design_video`。
- 缺字段：只出现一次问题组，不先出分镜。
- 完整输入：不重复问已有字段，Brief 就绪后恢复 `design_video`。
- 采集失败：无 BrandProfile、无编造方向，只允许失败说明与恢复路径。
- 非 website_promo：不套用官网门。
- 普通“宣传片”：不得伪称已绑定固定 Skill。

断言 system/user 顺序、阶段、工具白名单和实际媒体数量，不断言模型会说什么。

#### 11. 第一批交付与未交付边界

交付：Readiness、阶段/工具投影、BrandProfile、集中问题组、CreativeState、golden wire、LegitEvi 证据链和对应测试。

**验收终点**：本批只覆盖 `source_preparing`、`briefing`、完整 Brief 后恢复 `draft_build` 的投影能力，以及集中作答和本批状态恢复。首稿内容写作、`draft_repair`、CompositionVersion 的实际保存/呈现、Run/Output 制作和 Iteration 2 媒体均不在本批施工或验收面。后续迭代尚未开始；其既有实现或自动续行的结果不记入本批通过/失败，不因此新增本批测试或修复。

不交付：实际 PNG/TTS 素材、两幕薄片、原创配乐、60 秒成片、复杂 3D、30 秒/竖屏、局部渲染。上述分别属于 Iteration 2–5，施工时不得顺手提前实现。

#### 12. Iteration 1A 实施状态与剩余项

已落码：纯 SourceReadiness 与 source_preparing/briefing/draft_build 投影；扩展现有 Brief 的官网片槽位；真实 PNG 多模态 analyze_brand 与独立短事务；单一 CreativeState 在 PendingPlan、CompositionContent/Version 和无版本 Run 间的继承；集中问题组的 schemas、SSE、数组答案原子结算、QuestionDock 分页、草稿恢复及多项 Q/A；`composition_versions.creative_state` 的可选 migration。没有新增主表、作品根、第二意图入口、第二内容写口、第三套 Agent loop、AVAILABLE VIDEO ROUTES 或强制 Skill 绑定。

当前自动证据：fake provider 的 LegitEvi 模糊/完整输入 golden wire 通过；QuestionDock、整组作答、语言装配和授权定向检查通过；TypeScript 通过。完整输入回填 60 秒、16:9、使命科技感、英文配音和英文字幕；`#DC0000` 与原始宣言在 fake 证据中保留，字体只标“接近 Inter”。数字 option_id 与语义标签分离的整组作答回归已覆盖，避免把数字 ID 回填成 Brief 值。这里只记录当前定向结果，不沿用历史全量计数，不代表任何后续阶段已验收。

真实 LegitEvi 复验：实际 SourceSnapshot 和生产 `analyze_brand_seat` 形成的 BrandProfile 包含实测 `#DC0000`（visual/inferred）、“接近 Inter”和原始宣言。组跳过默认路径已验；项目 `655521c2-a0dd-46df-b8d8-cc85e77fbd17` 另完成真实六字段数组作答：preview/正式 digest 相同，六槽在 PendingPlan 与 CreativeState 一致且均标 `user-stated`，过期 digest/重复结算均 409，刷新后 pending=null，最终 `required_next_action=design_video`。完整 trace 与上下文生命周期证据位于 `scratch/website-promo-batch1-canonical-answers-20261117/`。真实 answer 结算即本批终点；现有接口的后续自动续行不属于本批证据。

剩余项：本地开发库已确认 `h8e5a2c4d7f1 (head)`；生产 migration 与 migration 后恢复未验证。本批真实浏览器的 full/panel/双主题/移动端问题组旅程未运行。未提交选择只保证同标签 sessionStorage 刷新恢复，不跨设备同步；只有整组提交或跳过才调用 answer API。Iteration 2 的实施和验收状态由子合同登记。

### Iteration 2：12–18 秒、两幕完整薄片

当前四轮施工、真实证据与验收停点统一归 [分镜驱动媒体底座与两幕薄片子合同](website-promo-iteration2-media-slice.md)。模糊输入只允许一次集中作答，之后在有效授权和预算内自动推进。完整 Brief 跳过已知问题。Brief 就绪后由主模型建立语义分镜，再按 scene_id 准备素材并走到首次 MP4 技术交付；视觉协议支持 N 幕受控 SVG 程序/MiniMax 双来源并统一落为 ImageObject，Music 本批只新增纯电子程序化器乐，统一媒体分析、Scene 证据渲染、Scene 生产产物与 Renderer 解耦同步建立。

当前四轮不包含第 8 步之后另起的局部修改和重新交付。后续整体闭环仍需单独验证：修改第二幕时第一幕媒体 digest 不变、重新制作和交付，以及真人连续看片与试听；不得把这些后续项写进当前四轮的通过结论。

### Iteration 3：素材试制、筛选与局部修复

扩展当前子合同已经建立的通用 `prepare_visual_assets`，继续复用执行内核、计量、固定媒体和 digest，不新增第二生产链；本迭代的新增重点是自动筛选、重做策略和联合时间适配，而不是重新创建素材入口。

- 每场形成 SceneAssetSpec：叙事目的、媒介、主体位置、安全区、品牌色、提示词、媒体 digest、审阅结果。
- 试制后真实 PNG 返回工作草稿；视觉 reviewer 给 pass/regenerate/needs_human。
- 最多自动重做 1–2 次，只重做当前场，超限升级人工。
- 品牌宣传片增加 narration-led 路径：粗略脚本→分段原速 TTS→真实时长→改稿/停顿/有限调速→锁时间轴；MG 固定窗口路径保留。

出口：不合格图片只重做当前场；超长旁白能改稿并重新测量；缺字/溢出有发现、修复和复验记录；未受影响素材不重生成。

### Iteration 4：音频基本盘、交付 QC、扩到 60 秒

先让薄片可交付，再扩六至八幕。

- loudnorm 前增加人声驱动 ducking，参数进入执行 manifest。
- 最终文件重新实测 Integrated LUFS/True Peak，失败不得放行。
- 主要切点使用现有 SFX；结构化原创配乐和 sonic signature 后置。
- 完整视频/音频解码、异常黑帧、封装规格、字体 glyph、字幕冲突、Logo/宣言/网址检查。
- reviewer 只负责构图、遮挡、品牌一致性等模型适合的判断；连续看片与实际试听仍单列。

出口：颜色错误、缺字、黑帧、截音、超响度等故障注入均能阻断；报告标明检查范围；通过后再做 60 秒。

### Iteration 5：专业化和规模化

- 结构化原创配乐与 sonic signature。
- 更复杂真人/3D 素材与统一性评估。
- 跨版本 Scene 缓存治理、并发调度与规模化成本优化。
- 30 秒语义衍生与 9:16 重构。
- 多版本盲评和持续质量回归。

## 7. 代码改造地图

### 7.1 领域模型、存储与迁移

- `apps/api/app/models/schemas.py`：扩展 Brief、BrandProfile、CreativeState、问题组协议。
- `apps/api/app/models/tables.py`：CompositionVersion 的可选 creative_state。
- `apps/api/app/editing/schemas.py`：CompositionContent 的可选 creative_state。
- `apps/api/app/editing/store.py`：digest、保存和恢复。
- `apps/api/app/editing/service.py`：修订继承。
- `apps/api/app/tools/project_context.py`：当前 CreativeState 的确定性投影。
- `apps/api/app/tools/video/design.py`：Brief 与现有显式约束的统一映射。
- `apps/api/app/tools/video/production/` 与素材试制 Run：run.context.creative_state 的固定继承。
- Alembic migration 与 `DATABASE_MIGRATIONS.md`；表归属同步 `MODULE_ARCHITECTURE.md`。

### 7.2 提示词与 Chat 编排

- `apps/api/app/chat/intent.py`：新 Brief 槽位的 brief_lines。
- `apps/api/app/chat/prompts.py`：source_preparing/briefing/draft_build 的当轮投影。
- `apps/api/app/chat/turn_tools.py`：对应工具开放和恢复条件。
- `apps/api/app/chat/plan_turn.py`：证据准备、集中问题组、答案合并与恢复。
- `apps/api/app/chat/service.py`：数组答案原子结算。
- `apps/api/app/chat/routes.py`：SSE 问题组预览。
- `apps/api/app/prompts/chat/plan_mode.j2`、`_asking_strategy.j2`、`_pending_question.j2`、`_video_project.j2`：只保留当前阶段的规则，不复制多份法律。
- `apps/api/app/skills/resolution.py`：不得只靠增加“宣传片”别名掩盖 Brief 和证据顺序；Skill 绑定在 Brief 明确后评估。

### 7.3 前端

- `apps/web/src/lib/chatStreamFrames.ts`
- `apps/web/src/components/chat/timeline/types.ts`
- `apps/web/src/components/chat/timeline/history.ts`
- `apps/web/src/components/chat/QuestionDock.tsx`
- `apps/web/src/components/chat/ChatDock.tsx`
- `apps/web/src/components/chat/AnsweredQuestion.tsx`
- en/zh locales 与旁置 vitest。

### 7.4 必须同步的母文档

- `docs/NAMING.md`：CreativeBrief 是现有 Brief 的扩展，BrandProfile 的职责与边界；CreativeState 仅是二者的状态载荷，不是新作品根。
- `docs/DIALOG_WORKFLOW.md`：Brief 与集中澄清的新规则。
- `docs/CHAT_ARCHITECTURE.md`：问题组、QuestionDock、SSE 和答案结算。
- `docs/VIDEO_PROJECT.md`：CreativeState 的版本、Run 和修订继承。
- `docs/MODULE_ARCHITECTURE.md`：新增 JSONB 的表归属。
- `docs/API.md`：问题组与 answers[]。
- `docs/UI_GUIDELINES.md`：分页 QuestionDock 的组件、键盘和双主题。
- `docs/VERIFICATION.md`：当前验证范围与仍未运行的真实视听项。

## 8. 验收合同

### 8.1 Brief 与 BrandProfile

- 旧 Brief 行按原义读取；新字段为空不触发修复循环。
- user-stated 永远高于 inferred/default；网站刷新不能覆盖用户已确认的用途和语言。
- 原始 SourceSnapshot 不被 BrandProfile 覆盖；不同 extractor_version/source_digest 不混用。
- Start 后、刷新后、素材试制恢复后均可回读同一个 CreativeState。
- 修订只改变目标内容；未改 Brief/Brand digest 不变；旧 Output 仍指向制作时版本。

### 8.2 问题组 API 与前端

- 旧 option/freeform/bail/start 行为不变。
- 四个以上字段可在同一 pending 行分页展示并一次提交；不得产生多个 pending 行或多次 Run。
- 错误 option、重复 slot、缺 required、过期 group_digest、重复结算均被正确处理。
- preview 被拒后零可见残片；full/panel 切换、刷新和跨设备恢复不丢答案。
- 单一待决、auto-bail、default_path、Stop、打字机和消息顺序不回归。

### 8.3 提示词 golden wire

用 fake provider 捕获实际 `messages` 和 tools，不调用真实模型：

1. 新项目、URL 尚未采集完成：只能是 source_preparing；design_video 不可见，等待事实明确，不能先问内容型问题。
2. 官网已完成：BrandProfile 输入包含真实正文和必要 PNG；不得只给路径。
3. 缺四类字段：只出现一次集中问题组，不得先设计或先出分镜。
4. 完整输入：不得重复问已有字段，Brief 就绪后才恢复 design_video。
5. 普通“宣传片”：不得伪称已绑定固定 Skill；绑定发生时有明确来源。
6. 断言 system/user 顺序、当前阶段、工具白名单和实际媒体数量，而不是断言模型会说什么。

### 8.4 LegitEvi 用户旅程

首条真实消息固定为：

```text
给 https://www.legitevi.com/en 做一只宣传片
```

验证：

- 先完成官网证据，再集中澄清；
- 回答后 Brief 含 60 秒、16:9、使命科技感、英文配音和字幕；
- 品牌红 #DC0000 有证据，原始宣言逐字保留；
- 先完成两幕薄片再扩 60 秒；
- PNG 被真实读取，TTS 被真实测量；
- 字幕无溢出/缺字，旁白完整无重叠，Logo/宣言/网址完整；
- MP4 全帧全音频可解码，最终响度接近 -16 LUFS；
- 故障修复只影响目标素材/场景，复验有明确范围；
- 连续看片与实际试听单独记录，不能由 schema、静帧或文件导出冒充。

## 9. 当前未决事项

- `BrandProfile` 是否先只住 PendingPlan/CompositionVersion，还是已有足够跨作品复用需求需要独立派生表：初版按前者，后续以真实复用证据裁决。
- 问题组默认值已按“官网品牌宣传片”任务拍板：缺字段先集中提问；用户跳过时，未答槽位使用 `website`、30 秒软目标、`product_evidence`、证据主语言（本例英文）、16:9 与极简科技风，来源记为 `default`，不冒充用户明确选择。用户可明确选择 60 秒等其他值；这些默认值不全局化。
- 固定 promo Skill 在 Brief 完成后的绑定方式：沿用显式/唯一自然语言匹配，不为追求参考流程而暗中扩大绑定。
- 素材试制的报价与预算：必须复用现有计量、非幂等生成保护和失败闭，具体信用点由实施批次的 BILLING 合同决定。
- 60 秒的 fps、AAC bitrate、原创配乐与局部渲染属于后续质量/规模化项，不阻塞第一轮证据和 Brief 主链。


---

# 附录 A：全部迭代的实施分解

## A.0 实施顺序与依赖

后续批次不能只用一句“扩到 60 秒”概括。依赖关系固定为：

```text
I1 证据与 Brief
→ I2 两幕真实媒体薄片
→ I3 素材筛选、局部修复与时间适配
→ I4 音频基本盘、交付 QC、60 秒
→ I5 专业化、衍生与规模化
```

每轮只有当前出口全部成立才进入下一轮。技术交付、内容质量和主观音视听分别记录，任何一层都不能用另一层代替。

## A.1 Iteration 1：证据、Brief 与集中澄清

### 工作包 1：领域模型与存储

- 扩展 `Brief`，新增 `CreativeState` 及其读容忍。
- 让 `PendingPlan/CompositionContent/CompositionVersion` 能保存可选 `creative_state`。
- 让素材试制 Run 能固定同一个 `creative_state`。
- 保留原始 SourceSnapshot、原始网页行和用户原话，不反向覆盖。

### 工作包 2：问题组

- 完成后端问题项、问题组、数组答案和原子结算。
- 完成 SSE 预览、QuestionDock、客户端分页、历史 Q/A。
- 保留旧单问、单一待决、auto-bail、default_path、Stop 和刷新恢复。

### 工作包 3：阶段投影与品牌分析

- 增加 `source_preparing / briefing` 的当轮投影。
- 在 briefing 中生成带证据的 BrandProfile，实际附上必要 PNG。
- LLM 判断缺失字段；代码去重、校验、回填并冻结 Brief。
- 完整输入不再重复问；缺字段时一次集中展示。

### 出口产物

- 扩展后的 Brief 与 BrandProfile。
- 问题组 API 与前端组件。
- 脱敏 golden wire fixtures。
- LegitEvi 品牌事实报告及明确的 unknowns/conflicts。

## A.2 Iteration 2：两幕完整薄片

当前四轮实施分解统一见 [分镜驱动媒体底座与两幕薄片子合同](website-promo-iteration2-media-slice.md)，本节不再复制另一份执行清单。子合同以主模型创建的语义分镜为中枢，从入口即支持 N 幕分批、受控 SVG/MiniMax 双来源、统一媒体分析、纯电子程序化 BGM 和 Scene 级局部渲染；两幕只是真实验收样例。

### 当前出口产物

真实用户旅程形成：

- 两个 SceneAssetSpec、一张受控 SVG PNG和一张 MiniMax PNG及各自来源/审阅/分析引用；
- 两段原速 TTS、音频 Snapshot、READY Alignment、真实 cues 和实测时长；
- 一条纯电子 BGM 的 Music、SourceSnapshot、ScoreSpec、authored BeatGrid 和分析报告；
- 一个可编辑 CompositionVersion、每幕 Scene 证据、正式 SceneRenderArtifact、一份执行 manifest、一个 MP4 Output 和分层技术证据。

### 后续闭环余量

以下不属于当前四轮，完成后仍需单独施工与验收：

- 修改第二幕一句文案，确认第一幕图片、TTS、BGM 和其他未改媒体 digest 不变，再重新交付；
- 真人连续看片与实际试听；
- 更复杂素材筛选、自动重做策略、60 秒扩片、sonic signature 和规模化缓存治理。

### 明确不做

当前四轮不做六至八幕或 60 秒真实扩片、歌声/人声 Music、Voice Clone、Ducking、复杂 3D、30 秒/竖屏、第二渲染器、通用缓存治理平台和通用插件平台。

## A.3 Iteration 3：素材筛选、局部修复与联合时间适配

### 工作包 1：通用素材试制节点

在当前通用 `prepare_visual_assets` 上扩展素材筛选与复用策略，不再创建另一个入口：

- 接受当前 SceneAssetSpec 和对应的 CreativeState；
- 复用执行内核、估价、授权、计量和失败闭；
- 保存请求、执行身份、供应商、实际用量、媒体字节和 digest；
- 预览只读取已固定媒体，不能任意触发额外付费生成；
- 正式 produce 只消费同一 digest，缺失时按合同处理，不静默换图。

### 工作包 2：有界审阅与重做

- 每场独立 pass/regenerate/needs_human。
- 检查主体、构图、安全区、人物异常、虚假 UI/文字、品牌偏离和跨场一致性。
- 自动重做最多 1–2 次，反馈只携带当前场问题。
- 超限保留实际失败并升级人工，不无限重试。
- 记录原候选、修复候选、通过候选及各自 digest。

### 工作包 3：narration-led 时间适配

保留 MG 的固定窗口路径，品牌宣传片新增：

```text
粗略脚本
→ 分段原速 TTS
→ 真实时长汇总
→ 只改超时段落 / 调整停顿 / 有限调速
→ 重新测量
→ 锁定 Scene/Clip/Animation 时间
```

处理顺序：

1. 缩短超时段落，只重做被改段；
2. 调整句间停顿；
3. 小幅语速适配；
4. 仍不合法才调整镜头分配；
5. 始终不裁音、不跨 dialogue 重叠、不牺牲结尾品牌停留。

### 工作包 4：字幕与文字质量

- 长句按语义和阅读时长拆分，保留原始文本映射。
- 检查字体 glyph、实际换行、动画极值、字幕与标题/CTA/Logo 冲突。
- 在亮、暗及复杂背景上检查对比度；必要时使用原生背板，而非全局固定一种字幕样式。
- 从同一 cues 生成 SRT/字幕 JSON；用户手改字幕不被派生覆盖。

### 工作包 5：质量闭环记录

统一记录：

```text
finding → target scene/clip/object
→ revised CompositionVersion
→ invalidated media
→ reused media
→ recheck scope
→ remaining limitations
```

### 出口

- 不合格图片只重做当前场；
- 超长旁白能自动改稿并重新测量，而非直接报错或裁音；
- 缺字、遮挡、溢出可形成发现、修复、复验闭环；
- 未点名 Scene/Object/媒体保持身份与 digest。

## A.4 Iteration 4：音频基本盘、交付 QC 与 60 秒

### 工作包 1：人声与音乐

- loudnorm 前增加旁白驱动的平滑 ducking，可使用 sidechain 类 DSP。
- 保留人声、音乐、SFX 分轨事实及 ducking 参数，不能只留一个无法解释的混合文件。
- 主要切点使用真实 SFX，按叙事需要而非按配额堆叠。
- 结尾降低编曲密度，sonic signature 仍属后续，不伪造已经拥有。
- 最终重新实测 Integrated LUFS 和 True Peak；归一化或测量失败不得交付。
- 目标输出音频为 48kHz、双声道；256k AAC 是否成为本片固定规格在 Brief 中明确，不能暗中沿用 192k 冒充参考规格。

### 工作包 2：技术 Delivery QC

- 全视频和全音频完整解码。
- H.264、分辨率、fps、视频流帧数、实际封装时长。
- yuv420p、Fast Start、音轨采样率和声道按本片规格检查。
- 全片异常黑帧、缺音轨、静音、削波、截尾、LUFS/True Peak。
- probe 失败、响度失败、完整解码失败均不得进入 COMPLETED。

### 工作包 3：内容 QC

- 生成真实联系表和单 Scene 必要动作序列。
- 检查颜色、字体、缺字、字幕遮挡、主体安全区、网页状态、品牌收尾。
- Logo、宣言、网址与保存版精确一致。
- reviewer 只能引用真实 Output 帧和实际采样范围，不把 Scene 中点当成整幕、不把离散帧当成连续播放。

### 工作包 4：扩到 60 秒

- 六至八幕只是参考范围，实际 Scene 数由叙事决定。
- 覆盖问题、证据鸿沟、AI 转译、主张验证、研究者/创作者、公众信任和品牌宣言；不机械复制参考文案。
- 全片旁白真实总时长不超过可用窗口，结尾有稳定品牌停留。
- 完成一次真实局部修订、重新交付及同点复验。

### 出口

- 颜色错误、缺字、黑帧、截音、超响度等故障注入均阻断交付。
- 60 秒 MP4 的技术 QC 通过，内容 QC 范围明确。
- 完成真人连续看片和实际试听，并登记仍未覆盖的审美不确定性。

## A.5 Iteration 5：专业化、衍生与规模化

### 工作包 1：结构化原创音频

- 按叙事段落生成有起伏的原创配乐，而不是一条循环底。
- 转场、使命段和 Logo 收尾与音乐结构对应。
- 生成简短品牌 sonic signature，保留音符、时间和来源。
- 对音乐遮蔽、抽动和人声清晰度做实际试听及必要信号检查。

### 工作包 2：复杂视觉与统一性

- 按需要引入真人、抽象 3D 和高级程序视觉，不把生成静帧等同于生成视频。
- 跨场检查人物、光线、材质、品牌色和视觉节奏。
- 建立参考样片盲评，不用“生成了”代替“达到导演质量”。

### 工作包 3：规模化 Scene 缓存治理

- 在当前 Scene 局部渲染底座上扩展跨版本缓存生命周期、容量和并发治理。
- 观察真实缓存命中、渲染成本和存储曲线后再调整政策，不另建第二渲染协议。
- 保持未改 Generator、TTS、图片和 Scene 的固定产物复用，并验证大规模组装恢复。

### 工作包 4：30 秒与竖屏衍生

- 60→30 秒先做语义删减和叙事重组，不做全片 0.5×。
- 重配被改段落的 TTS 和字幕，保留核心宣言与品牌收尾。
- 16:9→9:16 重新安排主体、标题、字幕和 Logo，不仅改变画布尺寸。
- 每种衍生都重新执行技术 QC 和必要视听验收。

### 工作包 5：持续复现与质量回归

- 固定版本重试零重新设计、零重新采样。
- 重放 provider 只在明确重新生成时发生，并产生新执行身份。
- 建立同输入多轮回归和真实样片盲评，保留失败签名而不是只保留成功截图。

---

# 附录 B：完整能力矩阵

状态：`A` 产品原生自动完成；`B` 可由产品内工作流编排；`C` 依赖外部专项工具/服务；`D` 明显人工介入；`E` 当前无法完成；`U` 未验证。自动调用 MiniMax/Freesound 等专项服务标 `C` 不代表一定手工；普通创意大模型不逐项重复标 `C`。本矩阵不把首稿授权当能力缺口。

| 能力环节 | 当前状态 | 当前证据与真正差距 | 收敛迭代 |
|---|:---:|---|:---:|
| 官网读取 | B | 动态正文、视图、元素和快照已验证；多页事实完整性仍需检查 | I1 |
| 动态网站处理 | B | 支持滚动、交互和状态；加载残帧识别与多页冲突检测不足 | I1 |
| 品牌色与字体提取 | B | 已有结构化 BrandProfile、来源和推断标记；完整 CSS 色板/font-family/Logo 覆盖与真实网站质量未验证，原生字体不自动跟随官网 | I1 |
| 模糊需求澄清 | B | 已有集中问题组 API、Dock 分页与数组结算；真实模型是否稳定只问缺失字段仍待验收 | I1 |
| 创意定位 | B | Agent 可生成，定位深度与事实/推断分离未验证 | I1 |
| 60 秒英文脚本 | B | 可写逐幕 narration，英文节奏、品牌首现和全片事实审计未验证 | I2/I4 |
| 分镜设计 | B | 有真实 CompositionVersion/Storyboard，创意质量不等于通过 | I2 |
| 分场景视觉生成 | U | 机制存在，但没有参考式多场 PNG 预生成、筛选、重做证据 | I2/I3 |
| 构图与字幕安全区 | B | 网页有几何避让，生成图实际主体与安全区需看帧 | I2/I3 |
| 真人/3D/信息图形混合 | B | 可混合上传视频、静帧、程序与原生 MG；原生通用 3D/文生视频不存在 | I5 |
| 精确时间轴 | A | 整数 ticks 统一量化；24fps/60 秒纯编译为 1440 帧 | 已有 |
| 推镜与平移 | A | transform scale/position 与网页 focus 已接，审美另计 | I2 |
| 多组文字错峰 | A | 多 Clip、TextPart、stagger、关键帧已接，排版质量另计 | I2 |
| 场景交叉转场 | A | 支持适用的全画幅固定媒体 crossfade，不是通用转场库 | I2 |
| 英文 TTS | C | MiniMax 已接；目标美式女声及自然度需实测 | I2 |
| 配音超时检测 | A | 每段测真实时长并检查窗口；全片联合优化不足 | I2/I3 |
| 分段配音防重叠 | B | 同轨和窗口可校验，跨 dialogue 轨语义重叠不足 | I3 |
| 语义字幕拆分 | B | sentence cues 可用，长句二次语义拆分与阅读控制不足 | I2/I3 |
| 字幕真实配音对齐 | A | 真实 TTS cues/词级对齐优于词数比例估算 | 已有 |
| 原创结构化配乐 | D | Chat 主要选库；另有生成端点但无叙事结构化作曲闭环 | I5 |
| 转场音效 | C | Freesound CC0 搜索、冻结、effect 轨可用，非原创合成 | I2/I4 |
| 品牌声音标识 | E | 没有音符级 sonic signature 生成能力 | I5 |
| 人声自动回避 | E | 只有 gain/关键帧，没有短时人声音量 sidechain | I4 |
| LUFS 与 True Peak | B | loudnorm 目标存在，失败可放行；最终实测不硬 | I4 |
| 精确 60 秒合成 | A | 视频流级 1440 帧已纯编译验证；封装与 probe 容差另计 | I4 |
| 自动抽帧 | B | exact Output 抽帧和单 Scene 动作序列存在，非默认全量检查 | I4 |
| 联系表检查 | E | 独立 JPEG 证据帧存在，没有原生联系表产物 | I4 |
| 字体与颜色异常检测 | U | 多模态可尝试，缺确定性 glyph/品牌色检测证据 | I3/I4 |
| 自动修复与复验 | D | 局部 Generator 可修，交付后主要靠用户发起 review/revise/produce | I3/I4 |
| 完整解码检查 | C | 交付硬门只首帧，完整解码需扩为正式 QC | I4 |
| 黑帧检测 | U | 只有采样 flat candidates，不等于全片黑帧检测 | I4 |
| 最终 MP4 交付 | A | 真实渲染、上传恢复、固定版本交付存在；生产验收仍需补 | I2/I4 |
| 可编辑时间轴 | A | CompositionVersion 真数据可编辑；烘焙内部不伪称逐层可编辑 | 已有 |
| 局部修改 | B | 内容与固定媒体可局部复用，完整 spec 改变仍整片渲染 | I3/I5 |
| 30 秒与竖屏衍生 | D | 可开放重稿；通用 time_map 拒绝 Speech/Generator/Video 缩放 | I5 |
| 可复现与失败恢复 | B | 固定来源/执行/digest 可靠；重新生成不保证像素一致 | I2/I5 |

总体工程判断仍为 L2：多阶段 Agent 工作流存在，但素材筛选、审美验收和自动质量修复仍需较多人工。该判断与刻意的产品授权无关。

---

# 附录 C：质量验收与人工评估边界

## C.1 不能用功能存在替代的质量项

| 维度 | 必须取得的证据 | 不能只依赖什么 |
|---|---|---|
| 品牌理解 | 官网事实、CSS/PNG 证据、品牌宣言与 unknowns | 模型一句“红黑科技感” |
| 叙事节奏 | 完整脚本和连续看片 | Scene 数量、时长合法 |
| 视觉原创性 | 实际候选图/视频及跨场比较 | 有图像生成工具 |
| 视觉统一性 | 人物、光线、材质、品牌色和镜头节奏 | 同一 prompt 风格词 |
| 信息密度 | 每幕阅读理解和信息层级 | 把网页段落全部搬入 |
| 动效专业度 | 连续运动、衔接、稳定阅读段 | schema 有 keyframes |
| 字幕可读性 | 实际换行、对比度、遮挡和动画极值 | 布局盒在画布内 |
| 英文配音自然度 | 实际试听及加速后听感 | TTS 返回成功、音频非静音 |
| 音乐叙事性 | 开头、发展、使命、收尾的音乐结构 | 库曲标题/风格标签 |
| 人声清晰度 | ducking、实际混音和遮蔽试听 | 最终有响度、PCM 非零 |
| 结尾记忆点 | Logo、宣言、网址、停留与声音收尾 | 最后一帧有品牌名 |
| 交付可靠性 | 完整解码、硬 QC、恢复与生产环境验证 | 文件存在/能下载 |
| 可修改性 | 只改目标对象、其他 digest 不变、可复验 | 保存了一个新 JSON |
| 可复现性 | 固定版本、来源、字体、媒体、执行摘要 | 同提示词重新调用模型 |

## C.2 人工审美不是授权缺口

首稿确认和费用确认是产品设计，不计为制作能力不足。以下则是专业品牌片仍然需要明确记录的人工判断：

- 创意定位与英文叙事；
- 真人/3D/信息图形的媒介选择；
- 视觉原创性、统一性和电影感；
- 动效是否克制、专业；
- 字幕在真实画面上的阅读体验；
- 英文配音自然度与广告腔；
- 音乐叙事、人声清晰度与 sonic signature；
- 结尾品牌记忆点。

如果要宣称“达到参考水平”，应提供参考 MP4，至少 3 人盲评；没有参考文件时，只能做“是否满足制作记录”的 anchored review，不能声称做了同等质量 A/B。

---

# 附录 D：同输入最小复现测试

## D.1 固定输入

```text
给 https://www.legitevi.com/en 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。
```

同时另测最初的模糊输入：

```text
给 https://www.legitevi.com/en 做一只宣传片
```

前者不得重复问已给字段；后者应先读官网，再集中询问必要缺失项。

## D.2 步骤、输出与验收

| 步骤 | 输入 → 输出 | 自动验收 | 人工审美验收 |
|---|---|---|---|
| 1. 冻结环境 | 当前代码、配置、provider、字体 → 测试 manifest | commit/worktree、模型、字体 digest、renderer、runner、SkillVersion 固定 | 无 |
| 2. 官网侦察 | URL → 正文、PNG、子页面、SourceSnapshot | 包含全球标准、三类受众、可验证主张、AI 转译和原始宣言；无加载残帧；无虚构客户数/用户量 | 定位概括是否准确，多页信息取舍是否合理 |
| 3. Brief | 原话 + 证据 → CreativeBrief | 60s、16:9、国际科技感、使命叙事、英文 TTS、英文字幕一致；不重复问 | 是否还缺真正影响制作的受众或用途 |
| 4. 品牌档案 | CSS/DOM/PNG/图标 → BrandProfile | 原生品牌红精确 #DC0000；Logo、Wordmark、宣言有证据；推断有标记 | 红黑灰是否克制，是否科学编辑感而非模板/赛博朋克 |
| 5. 脚本分镜 | Brief+BrandProfile → CompositionVersion | 精确 60s；叙事覆盖完整；无未证实数字；旁白完整；Logo/宣言/网址存在于版本 | 品牌首现、英文文案、信息密度、情绪递进 |
| 6. 分场视觉 | SceneAssetSpec → 固定 PNG/程序视觉 | 分辨率足够；无伪造 UI/文字/Logo；媒体可追溯；失败重做只影响当前场 | 真人真实性、3D 质感、原创性、统一性、媒介选择 |
| 7. TTS 与字幕 | 每段脚本 → 音频、cues、原生字幕 | 解码时长真实；无重叠/裁音；末句完整；品牌停留 ≥1.5s；字幕误差中位数 ≤120ms、P95 ≤250ms；无溢出/缺字 | 音色自然、克制、加速后听感、字幕阅读舒适度 |
| 8. 音乐与混音 | 切点、TTS → 配乐、SFX、混音 | 48kHz stereo；人声期平滑 ducking；-16±0.5 LUFS；TP ≤ -1.5dBTP；目标 AAC 256k | 音乐起伏、是否盖人声、SFX 是否克制、品牌声音记忆点 |
| 9. 渲染与硬 QC | video-spec → MP4 | 1920×1080、24fps、1440 帧、H.264、yuv420p、Fast Start；视频流 60.000s；全帧全音频无解码错误；无异常黑帧 | 连续观看是否有静帧无法发现的跳变、闪烁、衔接问题 |
| 10. 内容复核 | MP4+版本 → 联系表、报告 | 字幕不溢出/遮挡；无乱码；Logo/宣言/网址精确；原生品牌红一致；检查范围明确 | 品牌一致性、排版、结尾记忆点 |
| 11. 故障修复 | 注入颜色、缺字、超时、遮挡 → 修复版本 | 问题被检出；只使目标媒体失效；复验通过；旧 Output 在新交付前可用 | 修复是否引入新审美问题 |
| 12. 局部修改与复现 | “第七段更克制”及同版重试 → 新版本/Output | 未点名 Scene/Object/media digest 不变；重试零重新设计/采样；不重复收费/产出 | 第七段是否更克制且衔接自然 |

## D.3 时长判定

分别记录：

- 视频流必须为 `1440/24 = 60.000s`；
- 封装时长目标 60.000s，同时记录 AAC/mux padding；
- 若业务要求封装也精确到毫秒，需另有封装修正与验收，不得裁画面或旁白凑数；
- 不用 59.3/61.8 秒冒充精确 60 秒，也不为消除合理封装 padding 破坏内容。

## D.4 真正达到参考流程的判据

必须同时满足：

1. 所有技术硬门通过；
2. 所有官网事实可追溯；
3. 分场视觉服务叙事，而非只换背景；
4. 人工盲评不存在重大品牌、叙事、可读性或听感问题；
5. 至少一次真实故障被自动发现并局部修复；
6. “第七段更克制”不破坏其他镜头；
7. 固定版本恢复不重新设计、不重新采样；
8. 衍生 30 秒或竖屏仍保留旁白逻辑、字幕安全区和品牌收尾。

仅得到红色、60 秒、带英文声音的 MP4，不能视为达到参考流程。

---

# 附录 E：自动化、外部依赖与人工操作边界

## E.1 从完整 Brief 到 MP4 的操作口径

本批以子合同的单次集中作答为准。首稿呈现、视觉判断、试制和有界修复由 Agent 在授权与预算内推进。产品可提供用户选择的审阅模式；该模式的逐步确认不计入本批自主验收通过路径。真实连续视听和主观质量需另行记录。

## E.2 哪些“自动”仍可能隐藏人工

- 自动品牌理解不等于自动获得精确色板、字体和 Logo；
- 自动生成分镜不等于英文叙事已达标；
- 自动图像请求不等于制作前看过实际图片；
- 自动选 Music 不等于按叙事原创作曲；
- 技术 probe 不等于完成内容审片；
- 自动局部修订不等于局部渲染。

## E.3 没有外部专项工具时的边界

- 无图像生成：仍可用网页、上传图片/视频、draw-2d 和 Remotion 程序画面。
- 无 TTS：可用用户录音或做无声片。
- 无音乐生成：可用现有合法 Music 或用户上传音频。
- 无编码器：不能交付新 MP4，只能保留作品数据、预览和 video-spec。
- 仍可做：官网读取、事实清单、原生文字/图形、分镜、可编辑时间轴、版本管理和字幕时间数据。

## E.4 第一轮素材不合格

目标行为不是“再全部生成一次”，而是：

- 本地程序视觉：预览→诊断→修改当前程序→再预览；
- 模型图像：试制固定→真实读取→只重做当前 Scene；
- TTS：真实测量→只改超时段→重新对齐；
- 超出有界次数：保留失败和证据，升级人工。

当前模型图像主要在正式制作后生成，不能直接宣称已经具备该闭环；Iteration 2/3 就是为此补链。

## E.5 “第七段更克制”的局部修改

内容层应做到：

- 只修改第七段相关 Scene/Clip/Speech/必要字幕和动画；
- 其他 Scene/Object id、媒体 digest 不变；
- 未受影响图片、TTS、Generator 固定媒体复用；
- 形成新的不可变 CompositionVersion；
- 旧 Output 在新交付前仍可用。

当前代码在第四轮施工前仍按整片渲染；Scene 证据渲染和生产产物复用分别由子合同第三、四轮交付。对应真实证据出现前不得声称已经实现，完成后也不得跳过最终全片组装与完整解码。

---

# 附录 F：参考流程的取舍与最终优先级

## F.1 不值得机械照搬的部分

- 六张图、八幕、116 词、100 BPM 是单片创作选择，不是通用模板。
- 真实 TTS 句子/词级对齐优于按词数比例分配字幕。
- 逐段有界重合成优于全片统一 1.15×，但需要全片联合优化。
- 合法库曲不天然低分；关键是叙事、授权、音画关系和可复现。
- 整片重渲染不值得保留为最终形态，应逐步做 Scene 级缓存。
- 首稿集中审阅可保留，不应为追求无人值守删除。
- 视频流帧精度与封装时长必须分开，不能拿 mux padding 冒充内容时长错误。

## F.2 全部能力的最终优先级

### P0：稳定交付前必须完成

1. 真实同输入主链与生产环境验收；
2. 完整解码、黑帧、封装、响度等硬 Delivery QC；
3. 内容问题→局部修复→复验的质量闭环。

### P1：专业品牌质量必须完成

1. BrandProfile 与集中 CreativeBrief；
2. 全片叙事—TTS—镜头联合时间优化；
3. 分场视觉试制与制作前筛选；
4. 字幕 glyph、换行、遮挡和对比度；
5. ducking、音频实测和专业混音。

### P2：效率、编辑性和规模化

1. 跨版本 Scene 缓存治理与规模化调度；
2. 30 秒与竖屏语义衍生；
3. 联系表、SRT、字幕 JSON、技术 QC 和版本 manifest 交付包；
4. 更复杂结构化原创配乐、sonic signature 和复杂视觉。

## F.3 最终判断

当前产品不是缺少 URL→MP4 的基本主链，而是缺少把以下事实稳定连成一体的导演级工作流：

```text
证据正确的 Brief
→ 可验证的品牌理解
→ 实际看过的素材
→ 真实测过的声音
→ 可编辑的时间轴
→ 完整技术/内容质检
→ 只改受影响部分的复验与交付
```

本合同全部批次的共同验收原则是：**不丢失关键环节，不把实现技术差异当成缺陷，不把未运行、未观看、未试听的结果写成已经达标。**
