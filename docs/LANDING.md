# LANDING — 落地页叙事工作文档

> Status: 活跃工作文档（2026-10-29）——落地页叙事/结构的唯一事实源；排期只引用 `PROGRESS.md`。

## 1. 当前结构

首页为一屏：LandingHeader + LandingHero，保留原有 ASCII 波场、字体、主题/语言切换、按钮和入场动效。Hero 内容容器最大 1152px，说明最大 768px；桌面标题两行，每行不额外折行，小屏自适应。页面不挂载 SmoothScroll，首屏扣除导航高度。

VideoShowcase、Manifesto、AppShowcase、Channels、Pricing、FAQ、FinalCta、Footer、Gallery 与 Testimonials 不挂载，组件源码保留。导航移除对应锚点，保留 App、社群和开发计划入口；社群与开发计划当前为明确标注的 mock 弹窗，真实链接待接入。App 沿用既有登录及 `/home` 链路。

## 2. 叙事立场

- 定位为内容创作 Agent，不以演讲再利用或知识专家人群定义产品。
- 单助手叙事：用户提出目标，通过对话完成创作与修订；内部工具与子 agent 不承担品牌主语。
- 不虚构发布、合规、渠道或质量承诺。多形态是能力，不是一次输入固定生成全套的承诺。
- 隐藏的作品区仍须满足真实产物、公开权限和制作链验收；Testimonials 仍须具备真实可核查背书才可恢复。

## 3. 当前 Hero

- 英文：`Your content` / `creation agent`；说明：`Create videos with motion graphics, rich animation, and precise editing—all through conversation.`
- 中文：`你的内容` / `创作 Agent`；说明：`通过对话，轻松制作融合动态图形、丰富动画与精细剪辑的视频。`
- 文案事实源为 `en.ts` / `zh.ts` 的 `landing.heroTitle1/2` 与 `heroSubtitle`，页面 metadata 同步。Hero 主按钮为 Go to app / 前往应用，次按钮为加入社群。

## 4. 迭代清单

### 当前实现边界

当前 section 与隐藏状态以 §1 和 `apps/web/src/routes/index.tsx` 为准；落地页改动只更新该现状，不保留逐轮交付清单。FlowView、ChatDock、配方点击和项目工作区的长期规则分别归 `UI_GUIDELINES.md`、`CHAT_ARCHITECTURE.md` 与 `RECIPES.md`，不在本文维护第二份 Studio 规范。

### 长页证据叙事（未排期，不在当前首页呈现）

映射原则：hero 一句话 + 产物证据铺满各幕。FLORA 九幕弧线（identity → 新模块 → 上限 → 过程 → 行业 → 起步 → 价值 → 背书 → 愿景，证据见 `research/flora.md` §2）收敛为**六幕叙事 + 商务尾**；砍掉的三幕均服务专业工具叙事，见本节不采纳清单。

| 幕 | 角色 | 内容 | 对现状的动作 |
|---|---|---|---|
| 1 | identity | Hero 一句话 + 双 CTA | 砍副标题堆叠；在 §3 当前 hero 与承诺边界内迭代 |
| 2 | 证据 | 对比滑块 VideoShowcase（raw → result 真实产物对） | 保留。上限不独立成幕——我们的上限 = 产物本身，证据幕即上限幕 |
| 3 | 过程 | How it works（四步） | 章节保留，叙事改写：从使用教程改为单助手视角（用户说 → 它做） |
| 4 | 广度 | 渠道×语言矩阵 | 原样保留（轴与 FLORA 不同是有意的：行业×flow 服务专业创意人，渠道×语言服务欧洲知识专家） |
| 5 | 起步 = 起步证据 | 配方卡带真实产物上 landing（输入契约：需要什么素材 → 得到什么产物） | 新增，唯一大施工。吸收 Gallery 尸位（FLORA 拆两幕因有几百个 technique；我们就几张配方卡，卡和证据合一幕），恢复条件不变：真实产物，禁虚构文案 |
| 6 | 愿景收束 | Manifesto 后移 + FinalCta 合一幕 | Manifesto 从第三屏挪到叙事末尾 |

- **商务尾（不计入叙事幕）**：Pricing、FAQ 保持原位（FLORA 九幕同样不含，它的定价在付费墙）。
- **第七幕插槽 = 背书**：Testimonials 维持隐藏；真实可验证背书（用户数、机构名、可核查引语）到位后插幕 5/6 之间，不预留占位文案。
- **文案纪律**：每幕标题 ≤8 词、正文 ≤25 词（`research/flora.md` §2 同款硬指标）。
- **前置依赖**：真实样片与输入/输出证据密度、素材公开权限和对应制作链验收；占位片与不可验证背书不能撑起证据骨架。

### 不采纳（FLORA 对照）

- 新模块首发幕、画布独立成幕（FLORA 幕 2/3：单助手无模块概念，上限 = 产物本身；工具叙事 §2 已否）。
- 模型墙 / 模型名标注（用户不懂模型 SKU；我们的槽位留给产物语言与类型）。
- 配方卡 try/open 双入口（我们 chat 首发单入口是有意的）。
- 左侧垂直工具栏、多人协作光标、credits 左下角（无对应 product surface）。
- placeholder 塞教学（教学在 Tour， doctrine 不变）。
