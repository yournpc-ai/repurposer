# home-skeleton-revamp 实施简报——studio 视觉骨架重塑：灰底填充阶 / 实体丸化 / 海报优先画廊 / 去全局 header

> Status: ✅ 已落地（2026-08-20 拍板立项；**08-21 排期指认即日四期全落地**——验证：web tsc 绿、在流 shadow grep 清零、landing/home SSR 200、landing 豁免类 SSR 实证；明细见 PROGRESS 第三周 08-21 行）。
> 依据：**ADR-046**；证据 `research/minimax-design.md` §8–§10（MiniMax 发布日走查 + 色役粒度盘点）+ `research/agent-opus.md`（瀑布流 / 通知芯片 / 账户对照）+ `research/flora.md`（hover 动作 / 账户两层先例）+ `research/elevencreative.md`（浅色卡面工艺旧源）；实验台 `/tmp/repurposer-mocks/composer-bg.html` v4（chips 顶置 + 类型化 chips + pill 值状态 + Assets 面板演示）。

## 0. Context

MiniMax Design 发布日走查暴露五处存量病（ADR-046 Context 全表）：浅色 composer 白上白读作 wireframe、配方画廊强制竖槽 + 无封面概念、骑缝 blocks 读作渲染瑕疵、账户区平铺 list 缺层级、AppHeader 三个工具占一条通顶 band。色役盘点（`research/minimax-design.md` §10）给出病根：精致感 = **色役粒度细**（~21 个角色各占中性阶位），我方粒度粗在四个缺位角色无 token（send-disabled / group-title / icon-chip / toggle-track）。本简报把 ADR-046 落成四个施工批 + 一张色役对照表（§2，验收清单）。

不变量（施工全程不许碰）：配方 = 提示词与检视 overlay 唯一发射路径（ADR-040，hover 快捷发射二次否决）；FlowView 只读与"编辑只经 chat"（ADR-035/036/041）；landing 营销面豁免（Scope 条款——本批只动 `_app` + shared components）；rounded-full 禁令（§1 D3 注）。

## 1. 设计决策

| # | 决策 | 要点 |
|---|---|---|
| D1 | **灰底填充阶** | light `--background` 1.0 → **0.96 中性灰**（#f5f5f5 族，禁暖色——与暗色中性族同宗）；`--card` 保持 1.0 升格"最亮一层"；`--sidebar` 跟随 `--background`（融合纪律不变）；hover `--accent` light 0.95 → **0.92**（对 0.96 底重推导，白卡上仍读作清晰但安静的一步）。dark 零改动（0.12/0.21 体系已成立）。landing `/` 不动 |
| D2 | **影子只属浮层** | 文档流表面（卡 / composer / 媒体 tile）双主题去 `shadow-*`；`overlay-surface` 家族 light 标配耳语 `shadow-xl`（dark 保持无影传统——`--tw-shadow-color` 开关不动）。全站 grep 收编现存 `shadow-lg` / 手写影 |
| D3 | **composer 三段带 + 实体丸化** | 卡 = chips 带（顶，类型化：视频缩略图+时长 / 音频波形+时长 / 文档图标+格式标 / 上传中转圈+百分比，× 即删资产）→ MentionEditor 带 → 底排。实体 = 底排左簇 **ghost pills**（Assets 📎 / Persona 16px avatar 圈；**「丸」= ghost 控件形态，圆角仍 `rounded-md`，不是 rounded-full 填充丸**）。**值状态律**：rest = `meta-foreground`（"Optional" / "Auto"），设值 = `foreground`（计数 / 人设名，Persona avatar 圈填实）——一步变色是全部状态表达，无填充无彩色。pills 开**雾面 Popover 面板**（`side="bottom"` 向下开——expanded composer 居视口中部，向上开会盖住输入区，08-21 走查拍板；overlay-surface + 浮层影；滚动列表 `no-scrollbar`）：Assets 面板 = 上传行 + 类型化文件行（**行解剖 = 08-21 mock 转正**：方形类型 tile（h-9 缩略图或 icon-chip）+ 名称 / 类型化 meta 两行（AV = 类型 · 时长 · 体积、图片 = 类型 · 体积、文档 = 格式 · 体积，`formatFileSize` 入 `lib/stagedFiles.ts`）+ × 垂直居中；**列律：文件列方、身份列圆**）+ ×（**一处律**：面板 = chips 带的展开形态，面板开则带收起——文件列表同一时刻只住一处，pill 计数留锚）；Persona 面板 = Auto 行 + 人设行（同构两行：圆形身份 tile（h-9 avatar / Auto 圆 chip）+ 名称 / tags · 声音绑定态 meta）+ manage 链接。`AssetsModal` / `PersonaPickerModal` 退役删除；深度资产管理归未来资产中心页（本批不建） |
| D4 | **画廊 = 海报优先 + 数据驱动瀑布流** | 卡面状态机：静止 = **封面 poster**（类目 chip 左上 + 时长/比例 badge 左下，无 autoplay）→ hover = 播放**带声**（08-21 拍板：声音默认开——unmuted play 先行，浏览器手势策略拒绝则回落 muted 且开关如实反映有效态；任意点击（含开关本身）即授予激活，下一次 hover 起有声）+ 底部 scrim + **动作三件套**（MiniMax 解剖，同日走查）：声音开关居**左下**（占位符 badge 让位——badge 是 rest-only chrome，hover 槽位变形）、白色 stadium **Remix 丸居中**（Wand2 + 文案，开检视 overlay——与卡身点击同一条发射路径，非快捷发射）、expand 钮居右下（同开 overlay = 更大预览）→ click = 检视 overlay（唯一发射路径不变）。布局：CSS grid + `grid-auto-flow: dense` + 行高测量法（`grid-auto-rows: 8px`，JS 按注册表 w/h 元数据算 row-span，ResizeObserver 重排）；featured 大卡注册表标 `span: 2`（人工指定，不做通用算法）。**尺寸进数据不进枚举**——资产改尺寸流自动重排 |
| D5 | **去全局 AppHeader** | `AppHeader` 拆除；主题/语言迁**账户 console**（rail footer avatar → Popover：身份头 → inset **账户块只装价值面**（plan / credits——设置不混此组，MiniMax 分组律，08-21 对批）→ 偏好段**行内尾置 segmented**（theme 图标三态 / 语言 EN·中）+ 设置 chevron 行（开共享 dialog）→ 帮助段 → logout）；**通知 = 内容区右上角唯一浮动芯片**（圆角方块 + 未读点，右上槽位全 `_app` 保留，页面级控件永不占此角）；移动端留浮动 sidebar trigger。深度面 = **共享 SettingsDialog**（08-21 落地，MiniMax/FLORA 弹窗形态：左 section nav + 右内容，`useSettingsDialog` 随处可唤；`/settings` 页面退役、仅存 OAuth 回调 shim） |
| D6 | **色役表治理** | §2"角色 → token × 双主题"对照表为组件唯一取色来源；四缺位角色补 token（§2 标 ✱）；组件禁直引色值（grep 闸入 §4 验收）。多角色 ≠ 多颜色——全表住中性阶梯 |
| D7 | **滚动编排（08-21 走查拍板，同日二轮修订）** | home = 固定 app-shell 面：路由根 `h-svh` 不滚动（点阵固定视口），**唯一滚动口**（`no-scrollbar`）装全部——hero 舞台 / composer / 画廊。**composer 两形态一 DOM**（MentionEditor 永不卸载）：rest 集群居中停驻（`h-[28vh]` spacer 兄弟节点——sticky chrome 内部 padding 会一起钉顶，垫高必须在外）→ 滚动滑上钉顶成**单行 stadium 探索条**（half-radius，rounded-full 禁令第三例外，用户拍板）：左 attach（expanded 时折零宽；钉顶开 `side="bottom"`，带文件计数）+ 单行输入（`h-24`→`h-10`）+ send；chips 带与控制行折叠，**send 改绝对锚点**跨形态常驻。**形变纯滚动链接，永不走时钟过渡**（三轮走查：300ms 过渡跟不上快滚，半途化开的 stadium 悬在中屏）——`dockP` = 距钉点最后 140px 的滚动进度（scrollTop 纯函数，无阈值无迟滞），内边距 20/20/12→8 / 输入带 96→40 / 折叠带 / send 锚点 20·12→10 / 背板透明度全部插值；**半径不随动**——常量 40px（MiniMax 解剖大圆角，五轮走查拍板），坍缩态 CSS 半径帽自动裁成半高 = stadium 零插值自然涌现；**壳 = shadcn InputGroup 收编**（六轮走查拍板——布局已收敛标准解剖：chips block-start / 编辑器 control / 控制行 block-end，描边改 `border-transparent` + 发丝 + bg-card 无影遵守卡律，focus-within 环机制与 cursor-text 点击聚焦白得；**密度住 addon 不住容器**——px-4 侧 / pt-4 chips / pb-3 chin，编辑带 py 16→8 随动防单行裁字；双 addon 折叠走 border-box maxHeight 自带 padding 裁剪）；仅标题保留钉顶二元字号类。sticky chrome 背板（页底+点阵，透明度随 dockP）防宽卡露头；**docked 条下方留白 pb-14**（卡片不得贴条底消失，08-21 走查），再经 32px 底 mask 溶解过客。hero 双速处理（MiniMax 解剖，08-21 用户拍板文案）：**品牌锁up 常驻**（`LogoMark` + "Repurposer"——mark 按 `1.05em` 尺寸随字号缩放，钉顶收缩 `text-3xl/4xl`→`text-xl` 悬于条上），**品类句「你的自媒体Agent团队」**折叠消失（fade + 实测高度收折，收折发生在 chrome 内部、钉顶点上缘之下 → 钉点零位移）；welcome 接待式问候退役。钉点 = chrome `offsetTop` 实测（resize 重测）。全局 `color-scheme` 双主题——原生滚动条/控件随主题 |

## 2. 色役对照表（验收清单）

> 组件只准引角色，不准引色值。✱ = 本批新增 token / 角色指派；其余为既有 token 的角色登记。值 = light / dark。

**文字阶（既有三档，角色登记）**

| 角色 | token | 值（L / D） | 用途 |
|---|---|---|---|
| 标题 / 正文 / 已设值 | `foreground` | 0.145 / 0.95 | hero 标题、卡标题、**nav 主 item（一等文案不降级）**、pill 已设值、菜单主文案 |
| 副标题 / 描述 / placeholder | `muted-foreground` | 0.556 / 0.63 | 副标题、卡描述、输入占位、sidebar 二级/子项行、console 组内 item、tab rest |
| 元信息（caps 小标） | `meta-foreground`（`text-meta`  utility） | 0.68 / 0.52 | 组名（sidebar group / console section ✱角色指派）、UID、时长徽章、规格行 |

**填充阶**

| 角色 | token | 值（L / D） | 备注 |
|---|---|---|---|
| 页面底 | `background` | **0.96** ✱改 / 0.12 | studio 灰底；landing 不动 |
| 浮起层 | `card` / `popover` | 1.0 / 0.21 | 白卡靠填充阶浮起，无影 |
| 最轻填充 | `subtle` | 0.975 / =muted | 卡上 whisper 级填充 |
| 标准填充 | `muted` | 0.95 / 0.24 | chips 底、inset 块 |
| 井（反转） | `inset` | 0.92 / 0.15 | kbd、搜索框、**toggle 轨道 ✱角色指派** |
| hover / 选中弱档 | `accent` | **0.92** ✱改 / 白 8% | 行 hover、菜单选中、ghost 按钮 hover；dark 为白纱非实心 |
| nav 选中（列表弱档） | `accent` + `foreground` | 合成规则 | sidebar 当前页：accent 底 + 文字保持 foreground，与 hover 同底靠"常驻"区分 |
| tab 选中（段选强档） ✱ | `primary` / `primary-foreground` | 反色实心 | 分类 tab 段选（MiniMax Featured 反色实心丸证据）；tab rest = muted-foreground |
| 侧栏融合 | `sidebar` | =background / =background | 既有纪律，随 D1 改值 |

**控件专属**

| 角色 | token | 值（L / D） | 备注 |
|---|---|---|---|
| send enabled | `primary` / `primary-foreground` | 0.24 / 0.90（反色对） | 既有 |
| send disabled | ✱ `--disabled` / `--disabled-foreground` | inset 底 + meta 图标（双主题同构） | 新 token；**禁 `disabled:opacity-50` 一刀切** |
| 图标盒（chip / 文件行 / pill 内） | ✱ `--icon-chip` | card(1.0) on muted / 白 10% veil | 新 token |
| toggle 轨道 / 滑块 | `inset` / `card`(L)·`muted`(D) | 见填充阶 | 角色指派（iOS segmented：深轨道 + 亮滑块） |
| 描边（发丝） | `ring-foreground/10` | 既有 | 唯一合法描边；浮层可叠影，在流卡不叠 |
| 未读点 / 危险 | `destructive` | 既有 | rounded-full 例外其二 |
| 公告 pill ✱ | `card` + 发丝 + `foreground` / `muted-foreground` | 合成规则：加粗段 fg + 常态段 muted，一丸两阶 | 顶中公告（"H3 is LIVE"证据）；瞬态营销面，非常驻 |
| 徽标（Beta / NEW / 版本） ✱ | `muted` + `muted-foreground` | muted 底 + 灰字（Badge `rounded-md` 覆盖不变） | 版本号 / Beta / NEW 小丸；徽标级彩色属营销例外，不进工作室 |
| 媒体上文字 ✱ | 恒白（不随主题） | 白字 + scrim / 黑 35% 雾面 badge 保对比 | 配方卡 poster 上的标题 / 时长——随媒体不随主题，非主题色役 |
| 点阵底纹（✅ 08-21 拍板采纳，同日走查细化） | `dot-grid` utility / FlowView `dots` | muted-foreground 20% / 18%，1px 点、26px 网格 | **home + 结果画布两个工作台面专用**；home 由路由根承载（`h-svh` 不滚动）→ 网格固定视口、内容内滚；第三面即违规 |

## 3. 分期与改动点

依赖序：A（token 地基）先行，B / C 可并行，D 独立可插任意窗口。估时为实际工期（不含重烘素材等待）。

### Phase A：token 地基 + 去影（~1 天）

| 交付 | 文件 |
|---|---|
| `--background` 0.96 / `--sidebar` 跟随 / `--accent` 0.92 / 新 token（`--disabled` 族 / `--icon-chip`） | `apps/web/src/styles.css` |
| `overlay-surface` light 加 `shadow-xl`；dark 无影开关保持 | 同上 |
| 在流表面去影 grep 收编（`shadow-lg` / `shadow-md` 命中清单逐个判） | `components/`、`routes/` 命中面 |
| 双主题截图走查（home / projects / personas / 结果页）——白上白消失、无残影、无融合丢失 | 走查记录 |

### Phase B：composer 三段带 + 丸化（~2 天）

| 交付 | 文件 |
|---|---|
| HomeComposer 重构：chips 带（顶）+ 编辑带 + 底排；类型化 chip 解剖（缩略图/波形/文档/转圈四态，× 即删资产） | `components/home/HomeComposer.tsx`（ chips 子件可拆 `AssetChips`） |
| 实体 ghost pills（Assets / Persona）+ 值状态律（meta→foreground） | 同上 |
| 雾面 Popover 面板 ×2（`side="bottom"`）：Assets 面板（上传行 + 文件行 + ×）/ Persona 面板（Auto + 人设行 + manage 链接） | 新 `components/home/AssetsPanel.tsx` / `PersonaPanel.tsx` |
| `AssetsModal.tsx` / `PersonaPickerModal.tsx` 删除 | `components/home/` |
| tour 锚点重锚（composer-assets / composer-persona 指向 pills；步骤文案随内容哈希自动重播，禁手动版本号） | `lib/tour.ts` 配置 + `en.ts` / `zh.ts` |
| i18n 新键（面板行 / 上传行 / 空态），en 先 zh 后 | `en.ts` / `zh.ts` |

### Phase C：画廊 poster-first + 瀑布流（~2 天；封面重烘随需求池行平行）

| 交付 | 文件 |
|---|---|
| RecipeCard 状态机：静止 = poster（类目 chip + badge）→ hover 播放 + scrim 动作行 → click 检视 overlay | `components/home/RecipeCard.tsx` |
| 注册表加 `w` / `h` / 可选 `span: 2` 元数据；grid + dense + 行高测量重排（ResizeObserver） | `lib/recipes.ts`、`routes/_app.home.tsx`（画廊容器） |
| 封面帧字段进资产映射（重烘后 URL 落盘） | `lib/recipes.assets.ts` |
| demo 封面重烘（需求池 P1 行）：poster 帧 + hover 播放源，走 `scripts/upload_recipe_assets.py` 同款 content-hash 流程 | 烘焙产物（需求池行跟踪） |

### Phase D：chrome 拆除与迁建（~1 天）

| 交付 | 文件 |
|---|---|
| AppHeader 摘除（`_app` 布局回归 SidebarProvider/AppSidebar/SidebarInset 三件） | `routes/_app.tsx`、删 `components/AppHeader.tsx` |
| 账户 console Popover（身份头 / inset 账户组 / 偏好段行内 segmented / 帮助段 / logout）；theme-toggle 与 language-switcher 改行内 segmented 形态迁入 | `components/app-sidebar.tsx` footer、`components/theme-toggle.tsx`、`components/language-switcher.tsx` |
| NotificationBell 迁内容区右上浮芯片（圆角方块 + 未读点；Popover 先例不动） | `components/notifications/NotificationBell.tsx` + `_app` 布局挂载点 |
| 移动端浮动 sidebar trigger | `routes/_app.tsx` |

## 4. 验收

**机械闸**（随批跑）：

- `grep -rn "shadow-" apps/web/src/components apps/web/src/routes` —— 命中仅 overlay-surface 家族与浮层组件（Popover/DropdownMenu/Dialog/Select/Sheet/Tour）。
- `grep -rnE "bg-(muted|background|card)/[0-9]" apps/web/src` —— 零命中（既有 ad-hoc alpha 禁令保持）。
- `grep -rnE "#[0-9a-fA-F]{3,8}|oklch\(" apps/web/src/components apps/web/src/routes` —— 零命中（`styles.css` 与 LogoMark/favicon 既有豁免除外）。
- web `tsc` 绿；en/zh 键对齐（`zh: Resources` 类型闸）。

**行为闸**：

- composer：空 prompt 本地拦截不变；chips 三态（rest / staged / uploading）位置在文字之上；pills 值状态律 meta→foreground 一步变色；面板 `side="bottom"` 雾面 + light 耳语影 / dark 无影、列表无滚动条；行解剖 = 文件列方 tile / 身份列圆 tile + 名称 · meta 两行 + × 居中；上传 → chip 转圈 → done，× 即删资产（与现上传链一致）。
- 画廊：静止无 autoplay、封面即 poster；hover 播放**默认带声**（策略回落 muted 为唯一例外，开关如实反映有效态）+ 动作三件套（左下声音 / 居中 Remix 丸 / 右下 expand，Remix 与 expand 均只开检视 overlay）；click 进检视 overlay（唯一发射）；featured 卡跨列；窗口 resize 重排无内容跳变。
- chrome：全 `_app` 无顶条；bell 右上浮芯片 + 未读点；console 内 theme/language 行内切换即生效（View Transition 与 cookie 写盘不变）；移动端浮动 trigger 开合正常。
- tour：composer 步骤锚到 pills；内容哈希变化自动重播一次；结果页 tour 不受影响。
- 双主题 × en/zh × SSR 首刷无 hydration 错；landing `/` 零改动（git diff 面自查）。
- 滚动编排：home 窗口级无滚动条；画廊滚动 140px 内 hero 文案渐隐折叠、>56px composer 收 compact（pills 隐 / 输入带收）、<24px 回弹；点阵固定不随内容滚动；dark 下系统滚动条呈深色（`color-scheme`）。

## 5. Prohibited Behaviors

- **禁直引色值**（hex / oklch literal 进组件）——只能引 §2 角色 token；新角色先入表再入组件。
- **禁在流表面带 `shadow-*`**（卡 / composer / 媒体 tile，双主题）；浮层影 = overlay-surface 家族专属。
- **禁恢复骑缝 / straddle 形态**（实体块跨卡缘）；实体只有底排 ghost pills 一种形态。
- **禁 `rounded-full` 填充丸**（D3 注：「丸化」= ghost 控件语义；rounded-full 例外仍只有圆形图标按钮与状态点两条）。
- **禁 modal 形态复活**（AssetsModal 类重管理器）；picker 重量 = Popover 面板，更深管理归未来资产中心页（本批不建）。
- **禁 hover 快捷发射**（Use Prompt 类）——检视 overlay 唯一发射路径（ADR-040 不变）；hover 动作行只装预览性动作。
- **禁可操作瀑布流**（拖拽 / 接线 / 用户改 span）；span 来自注册表数据，布局无用户编辑面。
- **禁动 landing**（`/` + `components/landing/` 营销豁免不变）；禁动结果画布 / dock 体系（ADR-041 不受影响）。
- **禁 placeholder 塞教程**（教学归 Tour 不变）；禁给 pill 加填充灰（填充只给内容容器，底排控件全裸——Lovart 配方不变）。
