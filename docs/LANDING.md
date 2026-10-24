# LANDING — 落地页叙事工作文档

> Status: 活跃工作文档（2026-10-25）——落地页叙事/结构的唯一事实源；竞品证据引用 `research/flora.md`，排期只引用 `PROGRESS.md`。
> 读法：§1 当前结构，§2 叙事立场，§3 当前 hero，§4 仍未实施的迭代方向。Studio chat/画布行为不在此复制，分别归 CHAT_ARCHITECTURE 与 UI_GUIDELINES。

## 1. 现状结构（滚动序）

Hero（标题对 + 副标题 + 双 CTA，ASCII 波场氛围）→ 对比滑块 VideoShowcase（sticky 生长，raw → result 真实产物对）→ Manifesto（宣言一段）→ How it works（AppShowcase 四步）→ Channels（渠道×语言矩阵）→ Pricing → FAQ → FinalCta。

- **隐藏中（注释于 `routes/index.tsx`，未删除）**：Gallery（"Made from one source"——产物卡全是虚构文案，实物感不达标）与 Testimonials（"In their own words"——引语不可验证）。锚点死链已清（header Features 下拉 posts 项、footer features.l3）。恢复 = 取消注释并补回两个菜单项。
- 每个 section 占满视口（`min-h-svh` + 垂直居中）；滚动层级感知 = 一屏一幕。

## 2. 叙事立场（已拍板）

- **单助手（agent 叙事），口吻永久单数**：用户只说话、工具素养不可假设——这是定位推导，不是文案偏好。FLORA 的"器物主角/工具叙事"不适用（它默认用户懂工具，卖画布给专业创意人）。
- **角色署名（导演/音乐等内部子 agent 落到用户面）**：讨论封存，不做。对话层与感知层都保持"它"一个。
- **用户面自称**：assistant/助手，zh 代词"它"（NAMING N-25 不变）。
- hero 标题对仗结构（You X / We do the rest）保留，文案可换。

## 3. 当前 Hero

- 英文：`You did the talking` / `We do the rest`；中文：`你讲完了` / `剩下的交给我们`。事实源 = `apps/web/src/lib/i18n/locales/en.ts` 与 `zh.ts` 的 `landing.heroTitle1/2`。
- 副标题说明专家已有素材、助手给建议/计划/交付的风格与发布动作；修改时必须保持 multi-output 是能力而非固定套餐，且不虚构渠道、合规或质量承诺。
- 后续文案迭代保留 You X / We do the rest 的对仗与单一 assistant 叙事；旧四方向候选不再是待拍板清单。新方向只有进入当前产品决策后才写入本节。

## 4. 迭代清单

### 当前实现边界

当前 section 与隐藏状态以 §1 和 `apps/web/src/routes/index.tsx` 为准；落地页改动只更新该现状，不保留逐轮交付清单。FlowView、ChatDock、配方点击和项目工作区的长期规则分别归 `UI_GUIDELINES.md`、`CHAT_ARCHITECTURE.md` 与 `RECIPES.md`，不在本文维护第二份 Studio 规范。

### P2 — 叙事骨架：六幕 + 商务尾（缓做）

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
