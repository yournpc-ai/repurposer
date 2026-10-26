# Strategy — 为什么做这些，不做什么

> Status: Active（2026-07-21）
>
> 本文是**战略论证的唯一事实源**。PROGRESS 是排期表、不写论证，只引用本文条目号（`STRATEGY §X`）；竞品原始证据在 `research/` + `DECISION_MATRIX.md`，本文只做综合与判断。
>
> 回答三个问题：2027 年的市场长什么样（§1）、我们凭什么赢（§2–§3）、什么会杀死我们（§4）。所有排期争议的仲裁回到这里；本文结论变更 = 走 ADR。

---

## 1. 三个判断（2027 透镜）

### 判断 1：生成能力商品化，稀缺的是品味、身份、信任

切条、字幕、reframe、文本编辑已全面商品化（七家竞品功能雷同，见 `COMPETITIVE_ANALYSIS.md`）；Veo3 / Sora2 / Seedance 被 Revid 按 100–130 credit 明码标价转售，说明生成能力正在变成按量计价的大宗商品——而**卖大宗商品的中间商会被上游吃掉**（模型超市路线大概率被模型厂商自营或价格战碾平）。

当生成无限供给，稀缺的是三样东西：

| 资产 | 一句话 | 我们的载体 |
|---|---|---|
| **品味** | 知道哪 30 秒值得剪 | Content Director + 首发推荐分 + Gallery（§5） |
| **身份** | 知道这条内容像不像你 | 人设（Persona，Memory 层） |
| **信任** | 知道这次生成收你多少钱 | 成本计量 + 失败不扣费 + 合规底座 |

视频 agent 的竞争重心会从"生成能力"不可逆地转向这三样——这就是 §2 的三资产哲学。

### 判断 2：编辑范式已经收敛，真正的瓶颈在工作流两端

ChatCut 和 Underlord 已证明编辑的终局形态：对话式指令 + 可撤销的真实操作。这个范式 2027 年会普及，不再是差异点——这正是 Editor 薄化、Operation Model 当地基的理由（见 `MODULE_ARCHITECTURE.md`）。

真正的空白在两端：

- **上游**：素材在哪——Zoom 里、RSS 里、机构的 back-catalog 里（Opus 做 OpusSearch 就是闻到了这个味道）；
- **下游**：产出去哪——审校、合规确认、定时分发、newsletter。

七家竞品没有一家打通"理解 → 生成 → 审校 → 分发"全链路：Opus 没有文案，Descript 没有 LinkedIn，Repurpose 没有智能。**2027 年的赢家不是编辑器做得最好的，是工作流断头路最少的。**

### 判断 3："被 agent 调用"成为与"被用户打开"并列的分发面

一年内四家上线 MCP（Opus、Descript、Revid、ChatCut）不是巧合。2027 年相当比例的视频操作会发生在 ChatGPT / Claude 这类入口里，用户甚至不打开产品网页。反直觉结论：**视频 agent 产品同时需要一张 API/MCP 的脸**——产品要有两种形态：给人用的工作流，和给 agent 用的工具面。

---

## 2. 三资产哲学

### 2.1 品味：必须可见、可证伪，否则只是营销文案

每家产品都声称自己有品味，用户无法验证——品味是三资产里最弱的护城河，**除非**满足两个条件：

1. **打分理由可见**：每条 clip 标注"为什么是这 30 秒"（维度明细 + 打分理由，PROGRESS 需求池），让判断可以被审视、被反驳；
2. **删改痕迹回流**：用户删掉哪条、改了哪句，回流校准打分与 persona（persona 校准，PROGRESS 需求池；痕迹回流依赖 Operation Model，✅ 已落地）。

没有反馈回路的"品味"只是营销文案。Gallery（§5）是品味对外的陈列窗，打分理由 + 回流是对内的复利机制——两者缺一不可。

### 2.2 身份：唯一带复利的资产

风格学习用得越久越准——这是我们唯一带**数据网络效应**的资产，切换成本随使用时间增长。打分反馈、改稿痕迹都应回流校准 persona。

Opus 做不出这个，不是技术难，是它的 1600 万网红用户没有"个人文风"可学——**用户结构决定它进不来**。LinkedIn 对"通用 AI 腔"约 94% 检测率 + 30% 触达惩罚，Voice DNA 已成 B2B 必需品（PROGRESS 需求池·多语言质量）——我们的 persona 恰好是正确答案。

工程后果：persona 显化（让用户看到/编辑自己的风格、声纹与皮肤）与校准回路，是身份复利的重要组成；当前实施与启动条件归 `PROGRESS.md` 和 `POSITIONING.md`。

**终态**：persona 的终态兑现 = **identity-driven 的生成能力**。AI 生成结果我们必做，但 persona（风格 + 声纹 + 视觉身份 + 术语表）是身份输入，不是 Factory 通用生成（判断 1：生成能力商品化，persona 不商品化）。与记录剪辑的分界 = **主视频轨 provenance**：clip 线主轨是时间轴上的实拍/stills 记录（选段 / trim / hidden），轨道级 dub、AI 音乐与片头尾卡可在 clip 内合法存在并受 ADR-026 管辖；主轨本身生成时必须如实标 generated，并进入已批准的对应 spec family（当前 clip-spec 与 film-spec 平级）和 R5/ Film 合同，不能伪装记录素材，也不创造第三套 renderer。

**叙事分层（ADR-037）**：身份的用户侧闭环 = **管理 IP → 产生 outputs → 发布**。对外/愿景叙事可讲“打造你的 IP / 自媒体”（zh）；**“IP”禁入英文文案**，en 用 **personal brand / thought leadership**。当前代码身份模块仍是 **人设（Persona）**，多实例扁平；`speaker` 只指素材说话人。定位根升格、渠道/选题归属与人设收窄为表达分区已由 ADR-042 拍板，目标与启动条件归 `POSITIONING.md`；落地前不得把该目标写成现状。

### 2.3 信任：采购门槛，最先兑现

全行业 credit 计费不透明是共同的信任伤口（Opus 锁项目、Descript 改制反弹、Crayo all sales final，见 `DECISION_MATRIX.md`）；EU AI Act Art.50 于 2026-08-02 生效；LinkedIn 对 AI slop 降权。三件事指向同一个机会：**可解释、可审计、失败不扣费、数据不出 EU**。对 C 端是加分项，对机构采购是门槛；七家里只有我们能把这张牌打满（两家法国竞品数据都在美国）。

呈现野心参照：ElevenCreative 把合规做成**具名可购 SKU**——Zero Retention mode、Data Residency options（US/EU/India）、HIPAA BAA，全部挂在定价档上（`research/elevencreative.md` §2）。我们的合规实装仍是 `PROGRESS.md` §1.3 的上线准备项；实现后应以可理解、可验证的产品控制呈现，不能只写安全页徽章，也不能在实装前照抄“已合规”承诺。

### 2.4 时序关系：排期的理论依据

三资产不是并列关系，是时序关系：

> **Trust wins the deal. Identity keeps the customer. Taste is what they tell colleagues about.**

- **信任赢得第一单**（采购门槛）→ 真实计费、失败不扣费、披露与驻留必须先于对应商业承诺；当前阻塞归 `PROGRESS.md` §0.3、§1.3。
- **身份留住第二年**（切换成本复利）→ persona 校准与显化是身份主线；定位根的目标架构与启动条件归 `POSITIONING.md`。
- **品味在日常使用中被感知并推荐给同行** → 打分理由与真实样片先于货架数量；占位片永远不能承担该证据。

### 2.5 控制深度阶梯：品味要兑现，兑现靠控制

**问题**：配方卡（§5）承诺的是剪辑手艺——“我下周三的演讲，之后两周内容有着落”。承诺能不能稳定兑现，不取决于文案，取决于管线的**控制深度**。ElevenCreative Flows 证明流程级控制是手艺兑现的形态（`research/elevencreative.md` §3）；我们的翻译是**内化 DAG + 只读 Product Graph，不做可操作 DAG 编辑器**（ADR-028/035）。

| 级 | 含义 | 现状 |
|---|---|---|
| L0 跑通 | 单趟 plan → executors → 渲染 | ✅ |
| L1 覆盖控制 | 论点→资产有账可查、去重、格式分配（fortnight 分镜表） | ✅ understand/plan 两步走（分镜表 + 覆盖报告，N-17） |
| L2 质量控制 | 分数落库+门槛+理由；persona 保真可验；术语表；节奏/运镜枚举 | 首发推荐分与部分保真检查已有实现；评分维度明细及展示仍是当前欠账，其他能力按 `tasks/output-quality-verify.md` 与 PROGRESS 逐项核对，不把“首批”当完整质量线 |
| L3 寻址控制 | 步骤级重跑、chat 可寻址、run plan 可检视 | `workflow_steps`、`@output` / `@workflow_step`、graph/revise 与只读 Product Graph 已有实现；自然语言目标解算和完整旅程仍以当前验证合同为准 |
| L4 交付控制 | 分发（直发 = 核心，P1）；定时 / 回流（边缘，P2） | 🚧 直发代码完成，待平台凭据联调（DISTRIBUTION.md） |

**排期含义**：控制深度决定我们能否对配方结果作质量承诺，不能用卡面或单次 demo 代替 L2/L3 证据。当前配方可以提供 prompt 捷径，但 live/reserved/hidden、真实样片与完整制作旅程必须分别标注；不把“已有配方卡”写成“所有承诺已稳定兑现”。

---

## 3. 五张牌（打什么、不打什么）

1. **拒绝功能数量军备竞赛，all-in 工作流闭环。** 2027 年 Opus 会有 200 个功能，我们可能只有 20 个——没关系。知识工作者的真实场景是："我下周三有个演讲，之后两周的 LinkedIn 内容、newsletter、德语版都要有着落。"谁能把这条链路做成**一次上传、审核即走**，谁就赢这个市场；竞品每家只握链路的一段。（→ `PROGRESS.md` 需求池·链接摄入、§0.3 Distribution 启动条件）**闭环不是 Distribution 一个模块的事，是全模块的指导方针**：每个模块都要回答"你在闭环的哪一段、你消灭了哪条断头路"。全模块流转与闭环断点见 `MODULE_ARCHITECTURE.md` §2.1 闭环流转图。**闭环的信任主张分叉**：对手 autopilot 卖"不用管"，我们卖"管得住"（ADR-027：个人秒发、机构强制人工确认）——同一个闭环，机构买后者。
2. **persona 做成复利资产，而不是一个 feature。**（→ `POSITIONING.md` 启动条件 + `PROGRESS.md` 需求池·persona 校准）
3. **信任当产品做，不当公关做。** 计费透明、失败不扣费、AI 内容标识、数据不出 EU。（→ `PROGRESS.md` §0.3、§1.3；未实装项不作对外承诺）
4. **在 AI slop 泛滥的 2027，"不像 AI 写的"是最高溢价。** 每个人的 feed 都塞满生成内容时，受众的 AI 嗅觉会极度灵敏。我们的定位——真实素材 + 人设（风格 + 声纹）+ 母语级文案——恰好是 slop 的反面。这不是情怀，是定价权。（→ PROGRESS 需求池·多语言质量）
5. **2026 下半年长出 MCP 这张脸。** 我们的多 agent 图架构天然是工具面（`generate_assets` / `search_assets` / `get_persona_profile`），包装成本远低于对手，而"知识内容"这个 MCP 生态位目前无人占据。这是 P2 清单里最该提前的一项。（→ PROGRESS 明确不在本周期·MCP，周期结束后重排）

**不打的仗**：多轨自由时间线 / 转场画廊 / B-roll 库 / 通用物体追踪与自由重取景 / 模型超市转售——专业编辑需求明确导出 CapCut / Premiere；限定的 `reframe_clip` 生成能力按 RECIPES 当前边界使用，不借此扩张成 L3 编辑器。

---

## 4. 两个风险（什么会杀死我们）

1. **Opus 向 B 端基础设施移动**（OpusSearch + API + 配音）。如果它 2027 年做"面向机构的版本"，我们必须在它之前把 EU 驻留和 persona 复利做成既成事实——**窗口约 12–18 个月**。这是 EU 驻留（PROGRESS 需求池）和 persona 项不能再往后压的理由。2026-07 实证加速：autopilot 闭环产品化 + Viral Presets + 团队工作区/API，周级发版（`research/opusclip.md` §8）。
2. **LinkedIn API 单押。** 平台政策一变，分发链路就抖。newsletter / 机构网站这类**自有渠道**必须与 LinkedIn 并重（→ PROGRESS 明确不在本周期·newsletter ESP，建议提前半档）。

---

## 5. Gallery：品味的陈列窗

**问题**：用户进入 home 不知道怎么开始（激活断点）；home 顶部 hero 文案的对话对象是匿名访客，却对已登录用户反复展示（受众错配）。

**决策**：做**配方库（recipe gallery），不做内容流**。

- **每张卡 = 一个用户任务 + 一段可编辑 prompt**：卡面说明所需素材、具体产物与对应样片；点击只把 `promptTemplate` 预填到 composer，用户可修改并补充素材，发送后才进入 `POST /chat`。没有隐藏的“完整参数集”、`recipe_id` transport、自动发送或第二意图面；用户不必先理解 DAG。
- **为什么品味需要陈列窗**（ADR-048）：自称有品味无法取信，证据必须是可核验的输入/输出与真实样片。Home 货架先让用户按任务自定位，再用对应制作链的真片证明具体能力；点击只预填 prompt，不经过强制 inspect overlay。真实成对示例与未来 Gallery 的公开性、权限和来源谱系先过评审，不能默认公开用户项目。当前 Text Animation 与 ZYMIX Product Demo 使用真实 Film 产物，Product Promo 其余三张复用片只是布局占位，不是品味或制作能力证据；新增/重新上架卡的准入仍是①真实专家场景，②形态或闭环有不可替代价值，③对应当前链的真实示例与全旅程验收。详见 `RECIPES.md` §4、§7～§8。
- **双受众是复用方向，不是当前假象**：已登录 Home 当前有配方/样片货架；landing 的 Gallery 仍隐藏。未来若在 `/` 复用同一证据层，必须先满足真实样片、公开权限与叙事合同，不把 Home 已登录内容默认公开。
- **不是 TikTok 式 feed**：我们的用户不刷内容取乐，6–12 张策展卡片足够。卡片内容必须是知识演讲场景、多语言输出可见（定位纪律，见 CLAUDE.md）。
- **封面方向**：做落地页，整体以 **parallax 滚动视差**为主设计语言；首屏审美锚点 = Google Antigravity（一句话 hero + 双 CTA + 粒子场）。视差服务于叙事——沿工作流滚动展开"原始素材 → AI 选段打分 → 多语言产物 → 配方卡"，让滚动本身演示产品核心价值，而不是装饰性炫技。工程纪律：transform/opacity-only，禁 scroll-jacking，client-only 增强（SSR 首屏为静态布局），`prefers-reduced-motion` 降级，移动端有性能预算。
- **竞品实证（2026-07-21 快照）**：Agent Opus 的灵感 gallery + remix 证明“已登录首页 = composer + gallery”可成立（`research/agent-opus.md`）；其 calendar 是 projects 视图 toggle，不是第二创作入口。我们只借鉴 IA 证据，当前入口与控件仍以 UI_GUIDELINES / RECIPES 为准，不继承旧 Phase 1 排期。
- **配方形态（ADR-040/043）**：配方是提示词捷径，不是 run-plan 参数包或 mention。服务端 `flow/tasks` 只做声明式对账和公共只读投影，不进入发射载荷；实际计划由当前 Chat 根据用户文字、素材与 persona 生成。真实 Gallery/remix 仍 deferred，公开性与项目权限先行；即使未来复用成功 run，也必须另过产品决策，不能恢复隐藏模板播种或模板编辑器。
- **版权纪律**：只用自己录制或获授权的演讲素材，不爬会议视频。
- **激活断点不止在首页**：目标用户带着素材和模糊目标而来，彷徨会在计划中、修订与交付后复发。配方卡接住开始，方案/确认 dock 接住授权，真实产物与修订入口接住结果。**闭环优先于卡片数量**：「预填 → 对话定计划 → 授权 → 制作 → 真实交付 → 修订/再生产」通顺才算通路。顾问姿态 = 每轮最多一问、只问用户能答的、带理由纠偏并给可行默认；成功定义随计划。delivered/partial/failed 收官只陈述事实，不强制默认建议 pills 或“唯一下一步”；不做职业/变现咨询。行为规格归 CHAT_ARCH §3.3、§8.8 与 JOURNEYS。

**当前边界与 deferred**：

- 当前 Home 货架的 registry、真实/占位样片与 prompt-only 发射归 `RECIPES.md`；六张占位卡的替换归 `tasks/home-creation-entry-refresh.md`。
- landing Gallery 仍隐藏；恢复条件是当前 LANDING 合同中的真实证据，而不是取消注释就上线。
- 真实 Gallery / 公开项目 remix 未排期。启动前先在 `MODULE_ARCHITECTURE.md` §4 登记公开性/权限数据归属并作 ADR；发射仍走 prompt-only，不恢复 overlay 或隐藏 recipe 参数包。

---

## 6. 一句话

> **2027 年的视频 agent，生成是水电煤，品味、身份、信任才是资产。我们的赢面不在"也做视频"，在"唯一真正拥有创作者的身份"——own the persona, not the clip.**

---

## 7. 战略 → 当前事实源

本表只导航，不复制完成日期、旧周次或第二份排期。

| 战略主题 | 当前事实源 |
|---|---|
| 品味、质量控制与真实证据 | `tasks/output-quality-verify.md`、`RECIPES.md` §4/§8、`JOURNEYS.md` |
| 身份复利与定位根 | `POSITIONING.md` + `PROGRESS.md` §1.1；当前代码仍只使用 persona |
| 信任、计费与合规 | `BILLING.md`、`PROGRESS.md` §0.3 / §1.3、ADR-026/055/079 |
| 控制深度与 Product Graph | `ARCHITECTURE_NORTH_STAR.md`、`CHAT_ARCHITECTURE.md` §5/§9、`VERIFICATION.md` |
| 工作流闭环与 Distribution | `MODULE_ARCHITECTURE.md` §2.1、`DISTRIBUTION.md`、`PROGRESS.md` §0.3 |
| Gallery / Home 激活 | `RECIPES.md`、`LANDING.md`、`tasks/home-creation-entry-refresh.md`；真实 Gallery 仍在需求池 |
| MCP、newsletter、EU 驻留等后续方向 | `PROGRESS.md` 需求池与对应启动条件；未立项不等于已交付 |
