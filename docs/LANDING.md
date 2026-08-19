# LANDING — 落地页叙事工作文档

> Status: 活跃工作文档（2026-08-19 建）——落地页叙事/结构的唯一事实源；竞品证据引用 `research/flora.md`，排期只引用 `PROGRESS.md`。
> 读法：§1 现状结构，§2 叙事立场（已拍板），§3 讨论中待拍板，§4 迭代清单。

## 1. 现状结构（滚动序）

Hero（标题对 + 副标题 + 双 CTA，ASCII 波场氛围）→ 对比滑块 VideoShowcase（sticky 生长，raw → result 真实产物对）→ Manifesto（宣言一段）→ How it works（AppShowcase 四步）→ Channels（渠道×语言矩阵）→ Pricing → FAQ → FinalCta。

- **隐藏中（注释于 `routes/index.tsx`，未删除）**：Gallery（"Made from one source"——产物卡全是虚构文案，实物感不达标）与 Testimonials（"In their own words"——引语不可验证）。锚点死链已清（header Features 下拉 posts 项、footer features.l3）。恢复 = 取消注释并补回两个菜单项。
- 每个 section 占满视口（`min-h-svh` + 垂直居中，2026-08-19 修"两幕挤一屏"的高度塌陷）；滚动层级感知 = 一屏一幕。

## 2. 叙事立场（已拍板）

- **单助手（agent 叙事），口吻永久单数**：用户只说话、工具素养不可假设——这是定位推导，不是文案偏好。FLORA 的"器物主角/工具叙事"不适用（它默认用户懂工具，卖画布给专业创意人）。
- **角色署名（导演/音乐等内部子 agent 落到用户面）**：讨论封存，不做。对话层与感知层都保持"它"一个。
- **用户面自称**：assistant/助手，zh 代词"它"（NAMING N-25 不变）。
- hero 标题对仗结构（You X / We do the rest）保留，文案可换。

## 3. 讨论中待拍板

### 3.1 Hero 文案四方向（副标题重写稿随 A 走，详见讨论记录）

- A：You did the hard part. / We do the rest.（难的部分你做完了 / 剩下的交给我们）——输入形态全包容 + 身份体面，推荐。
- B：You did the work. —— 最通用最平。
- C：You reached the room. / We reach the rest. —— 情绪最强，但属"更大的舞台"被否角度，待裁定。
- D：You focus on your craft. / We handle the rest. —— 承诺句原文，中介套话感。

### 3.2 九幕叙事骨架（缓做）

FLORA 首页九幕弧线（identity → 新模块 → 上限 → 过程 → 行业 → 起步 → 价值 → 背书 → 愿景，证据见 `research/flora.md` §2）映射到我们 = hero 一句话 + 产物证据铺满各幕。裁定：**当前产物精致度撑不起来，缓做**——先攒真存量（FlowView 精致度、配方真实产物密度），骨架重构待存量到位。

## 4. 迭代清单

### 已落地（2026-08-19）

- Gallery / Testimonials 隐藏 + 死链清理。
- 落地页各 section 全屏化。
- FlowView 边：lineage 品牌色去除（全边统一安静灰，语义仅存于数据）；active 边改单数据包动画（`flow-edge-packet`，整边蚂蚁线退役）。
- 对比滑块 chrome（label/tags/静音钮）去滚动渐变，生长完成即常驻。
- **FlowView 精致度包**（组件仍一个、差异走 props）：
  - 名词节点收窄：画布只渲染 素材 / 文本（任务书）/ 产物 三类节点；过程动词（select_clips / dub / add_music）的 `canvas_group` 授予全部移除、步骤折叠进过程脊（translate_clip 08-15 先例推广；干预通道 = 点产物卡注入 dock 焦点 / 展开脊点步骤 pill 走 @workflow_step）。新 run 唯一 artifact = 任务书；canvas_key 序列化时从节点类现算（从不入行），存量 run 重序列化即同一收窄画布，零迁移。
  - 任务书（plan）= 雾面玻璃文本节点（`dock-surface` 配方——与 dock 同停一片点阵，点格透霜；260×200，六行 relaxed 正文）——对应 FLORA 的 GPT-5 文本节点。
  - mention 锚点：folded 动词的指认改道脊内步骤 pill（锚定机制是步骤驱动的，零改码）。
  - 配方 flow 与结果画布同组件同契约（配方 surface 无 artifact 节点，过程步骤是说明书内容，合法保留）。
  - 结果画布顶栏换血：右上角 home 继承三控件（主题/语言/通知）撤出全屏世界，换画布语境控件 = FlowView `controls` prop（explore 面专属）：雾面缩放 pill（− / 实时 % 点击归位 / +）。app chrome 归 studio shell 的拍板**确认覆盖移动端**（最近入口 = 退回 /projects）。
  - FlowView `groups` prop（区域框 = 大叙事分组框，FLORA technique workflow 形态；ViewportPortal 绘制、垫底于边与节点之下）：配方 surface 首用——策展步骤组包进署名「策展步骤」的圆角框（框只包步骤，不借配方名——头部标题已命名）。
- **画布/chat 小件包**（P2 同日落完）：
  - "Jump to latest" 浮 pill 已存在于 `ui/message-scroller`（`MessageScrollerButton`：live 几何可见性跟踪 + 平滑滚底）——需求池条目为陈欠，核验即关。
  - dock 常驻诚实说明行：一体容器底部常驻一行耳语（`results.dock.honesty`，en "It can make mistakes…" / zh「它可能出错……」），对应 FLORA 的 FAUNA 免责行。
  - 节点工具栏做薄：磨砂条 44px 带（8px 缝 + 36px 条；原 56 = 12 + 44）——按钮 h-7 / 图标 h-3.5 / 信息 11px；hover 化否决不变（小白可发现性优先），只做薄。

### P2 — 候选小件

- chat dock 右侧面板化（dock/undock 改变布局）——缓，agent 叙事下 dock 是主角不收起。

### 不采纳（FLORA 对照）

- 模型墙 / 模型名标注（用户不懂模型 SKU；我们的槽位留给产物语言与类型）。
- 配方卡 try/open 双入口（我们 chat 首发单入口是有意的）。
- 左侧垂直工具栏、多人协作光标、credits 左下角（无对应 product surface）。
- placeholder 塞教学（教学在 Tour， doctrine 不变）。
