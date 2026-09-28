# UI Guidelines — Studio 视觉与交互设计系统

> Status: 活跃（2026-09-28 建——自 CLAUDE.md 迁入，现行法全文唯一家）
> **Scope**：studio（`_app` 路由 + 共享组件）。落地页（`/` + `components/landing/`）是营销面，自有视觉语言，其 `rounded-full` / `border-border` / `font-medium` 用法是模板原生，不受本文约束。
> 行为层规格（chat 回合 / dock 状态机 / 画布数据面）归 `CHAT_ARCHITECTURE.md`；本文只管视觉与交互形态。整体风格：克制、轻量、统一。

## 1. 圆角与按钮

- **统一小圆角**：按钮、输入框、卡、pill、下拉触发器用默认 `rounded-md`（卡 / 面板可 `rounded-lg`）。
- **`rounded-full` 例外清单**（除此之外禁用）：
  1. 真圆形图标按钮（如输入框右下角发送箭头 `h-9 w-9 rounded-full`）；
  2. 状态徽章 / 红点（通知角标）；
  3. home composer 钉顶后的**单行探索条**（stadium / 半高圆角；展开的 composer 保持 `rounded-2xl`）——stadium 只属于真单行盒，dock 输入组全形态恒 `rounded-xl`；
  4. home gallery 的**筛选 pill 行**（stadium pills：active = `bg-foreground` 深底 pill，inactive = `bg-card` 白 chip 靠填充步浮在灰页上）。
- shadcn `Badge` 基座是 `rounded-full`——用于元数据标签（时长 / 画幅 / 标签）时恒 `className="rounded-md"` 覆盖。
- **同排控件中心线对齐**：动作区控件统一 `h-9`，与发送钮同高；composer 底排整排 `h-9`（圆钮 / cost-confirm pill / send 同高，glyph 统一 `size-4.5`）。
- pill / 下拉触发器**文字不加粗**（禁 `font-medium`），保持轻量。
- **Button 内图标用 `size-*`，不用 `h-* w-*`**：每个 button variant 钉了 `[&_svg:not([class*='size-'])]:size-N`（`size="icon"` 钉 3.5 = 14px）——`h-5 w-5` 不匹配 `:not()` 守卫，会被静默覆盖成 14px；`size-5` 含 `size-` 字样因此豁免。

## 2. 图标

- 全部图标从 `lucide-react` 导入。禁手写 SVG，两个例外：无 lucide 替代的第三方 logo；**品牌 LogoMark**（`src/components/LogoMark.tsx`，实心 delta：一股流散成多股——几何真值源是该组件，`public/favicon.svg` 是它的静态烘焙色副本，两者必须同步）。Logo 锁up = `<LogoMark />` + "Repurposer" 字标，永不手工重拼 tile。
- 尺寸约定：顶栏 / 卡动作图标 `h-5 w-5`；内联 / pill 图标 `h-4 w-4`，更小辅助 `h-3.5 w-3.5`；sidebar 导航 `h-4.5 w-4.5`；**Button 内一律 `size-*`**（见 §1）。

## 3. 浮层组件选型（DropdownMenu / Popover / Select）

- **列表式单选**（点击即选即关）：`DropdownMenu` + `DropdownMenuItem`。
- **带内联动作的内容面板**（点击行内按钮/链接不得关闭面板，如通知面板）：`Popover`，永不 `DropdownMenu`（先例 `NotificationBell`）。
- **多控件设置面板**（调整多个值时要保持打开）：`Popover` + 内部分段钮组。
- 触发器统一 `render={<Button variant="outline" size="sm" className="h-9 …" />}`，内部「图标 + label + `ChevronDown`」。
- 选项的「当前选中」用 `Check` 图标；底部浮层记得 `side="top"` 向上弹出。
- 表单里的纯下拉用 `Select`；prompt 动作条的参数选择用 pill 模式——两套风格不混。

## 4. 卡面纵深：发丝线 + 柔影，无可见描边

- **基座 `Card` 自带 `ring-foreground/10` 发丝线**（dark：白 10%，读作玻璃边）。light 主题页面是 **0.96 中性灰底**，白卡只靠填充步浮起，**无 shadow**。**高程律（双主题，ADR-046）：浮起面 = 深底上的更浅填充**——light：page 0.96 → card 1.0；dark：page 0.12 → card 0.21。
- **shadow 只属于浮层**——in-flow 面（卡 / composer / 媒体 tile）永不带 `shadow-*`，双主题同律。light 浮层（`overlay-surface` 冰霜族）带耳语级 `shadow-xl`（把玻璃从底下内容上抬起）；dark 保持无影传统（`styles.css` 一个开关让 `.dark` 下一切 `shadow-*` 编译为透明；focus ring 幸免——它经 `--tw-ring-shadow` 组合）。
- **禁可见描边**：`border` + `border-border`、`ring-1 ring-border`、强于 /10 的 `ring-foreground/*` 全禁。/10 发丝线只在浮层上可与 shadow 共存；in-flow 卡既不带可见描边也不带 shadow。（`border-dashed` dropzone 与 `border-transparent` variant 基座合法；focus ring 是交互不是描边。）
- 分区隔离来自留白与 token 填充步（`bg-muted` / `bg-inset`），永不画分隔线。
- **填充优先——发丝线是兜底不是默认**：填充已能区分前后（`bg-muted` chip 在 `bg-card` 面板上、媒体内容在页面上）→ 零环零边。`ring-foreground/10` 只为同 fill 边界存在（白卡在白页上、冰霜 modal 在 backdrop wash 上）。同 fill 元素需要分离时，优先**调它的填充阶**，不画线。
- **Hero 面 = 完全平**：home composer = 灰页上的白平卡（发丝线、无 shadow）。**Composer 卡禁用 `backdrop-filter`**——祖先 backdrop-filter 会成为 Backdrop Root，后代 MentionPicker 的 blur 只采样其子树（无物可 blur → 退化为纯染色）。
- 媒体 / 示意图 tile 无环无影（填充步分离）。gallery 封面 tile = **`bg-card` 浮起面**（页面已有灰底，封面是白卡：light 0.96→1.0 / dark 0.12→0.21 高程步）；hover chrome = **仅右上 expand 钮**（`bg-accent` token 步）——整卡 cursor-pointer + expand 已足够表达可点；线条吃 `foreground` alpha。

### 4.1 Gallery 卡状态机（ADR-048 + RECIPES §4 / §4.8）

- 封面是单色工艺示意图，**永不实拍**。rest = 内联 SVG 静态封面（`components/recipes/covers/<id>.svg`，foreground 灰阶自驱双主题反转，16:10，左输入→右输出）；hover 播 CSS keyframe 过程动画（零视频零声音零媒体请求）。
- 证据入 overlay：网格零真容。**卡没有真实成对示例 = 不进网格**（RECIPES §4.8 准入）。
- 三行卡下文字 = 菜名 / promise（2 行 clamp）/ 适用素材。卡面禁画幅 badge / 类别 chip / 渠道名（卡只承载 genre）；渠道是挂发/排期变量（预填模板默认，chat 覆写）。
- 网格 = 4/3/2 列等宽，**无 featured 跨列**（编辑优先 = 排序位）。
- hover 带声音示例住 overlay 的 Examples tab（点击 = 手势，声音原生）。

### 4.2 灰梯

- 面层级来自阶梯 token，永不来自一次性 alpha 填充。**Light**：`--background` = **0.96 中性灰**（纯白退给落地页——营销 register 独立，见 Scope）；白 `--card`（1.0）是浮起层，靠填充步浮起不靠 shadow；卡上填充阶 = `--subtle` 0.975 → `--muted` 0.95 → `--inset` 0.92（它们活在白卡 / 面板上）。**Dark**：`--background` = **近黑**（0.12），高程说玻璃不说阶梯（浮层半透，见 §5）；`--card`/`--popover` 0.21，`--muted` 0.24（`--subtle` 并入它），**`--inset` 反转 = 0.15，比面板更暗**（kbd chip / 种子值 / 搜索输入坐在更暗的井里）。
- **`bg-muted/50`、`bg-background/60`、`bg-muted/30` 等临时 alpha 全禁**——内层块用实色 `bg-muted`，muted 卡上的嵌套块反转为 `bg-card`。

### 4.3 Hover / 高亮 = `--accent`，双主题一个 token

- light = 实色 0.92 灰阶（对 0.96 页面推导；在白卡上读作清晰但安静的一步）；**dark = `oklch(1 0 0 / 8%)` 半透白纱**（永不是更亮的实色阶）。菜单行、列表 hover、picker 选中态、ghost 钮 hover 一律吃 `bg-accent`（弱档 `/50`）——一个变量回调全站 hover。
- 禁逐实例硬编码 hover 色值（`dark:hover:bg-[oklch(…)]` 禁）。**variant 配对仍是硬要求**：`dark:bg-*` 在级联里压过裸 `hover:bg-*`——带 `dark:bg-x` 的元素必须显式带 `dark:hover:bg-accent`。

### 4.4 文字三档

`foreground`（0.145 / dark 0.95）→ `muted-foreground` 副题（0.556 / dark 0.63）→ **`meta-foreground`**（0.68 / dark 0.42）用于小型全大写追踪 meta 标签（"MODEL / SEED" 式）与耳语句（dock 免责行），经 `text-meta` utility 组合（`uppercase` + `tracking-[0.08em]` + token 色）。

## 5. 浮层冰霜：`overlay-surface`

- **一切浮层**（Popover / DropdownMenu / Dialog / Select / Sheet / Tour）用 `styles.css` 的共享 `overlay-surface` utility——半透 `--popover` + `backdrop-blur` + `saturate(1.4)`，**分主题配方**：light = **92% + blur(24px)**（低不透明度让背后的深内容透出染色）；dark = **68% + blur(28px)**（近黑画布上高不透明度填充会读作实心盒，blur 无物可显）。`@supports not (backdrop-filter)` 下实色兜底。影律（ADR-046）：utility 在 light 带耳语 `shadow-xl`，dark 无影。
- 浮层组件**禁回加 `bg-popover`**；**逐实例 frost 补丁（如 `dark:bg-white/10`）禁**——调共享配方；实例确需不同不透明度时经 `className` 覆盖（组件最后合并它，这是开放的扩展点）。
- Dialog / Sheet backdrop 分主题：light = `bg-background/60`（白 wash——白页上黑罩读作灰浊）+ `backdrop-blur-[2px]`；dark = `bg-black/30` + `backdrop-blur-[2px]`——冰霜面在调暗但清晰可辨的页面上读出来。
- **Overlay chrome = Dialog primitive，禁手写**（`fixed` backdrop + glass div）：手写 backdrop 包住面板会杀死玻璃——带 `backdrop-filter` 的祖先成为 Backdrop Root，后代面板的 `overlay-surface` blur 只采样该子树（无物可 blur）→ 静默退化为平染色。primitive 把 overlay 与 content 并排 portal，这是唯一正确结构。
- **`DialogContent` 经 `-translate-1/2` 居中**——带 transform 的弹窗会成为 `fixed` 后代的包含块，把视口锚浮层传送走。视口锚浮层因此 portal 到 `document.body`（`MentionPicker` 先例），免疫祖先 transform 与 backdrop-filter；必须宿主**非 portal** fixed 浮层的弹窗，手组 `DialogPortal` + `DialogOverlay` + `DialogPrimitive.Popup` 并用 `inset-0 m-auto` 居中（无 transform）。**手组弹窗必须镜像 `DialogContent` chrome**：`overlay-surface` + `ring-1 ring-foreground/10` 发丝 + `shadow-xl` + `rounded-xl`——缺发丝线时 light 主题玻璃会溶进白 backdrop wash（先例 `RecipeInspectOverlay`）。
- tooltip 与 sonner toast 有意排除（小型瞬态标签保持实色）。
- **滚动渐隐**（`scroll-fade-y` / `scroll-fade-x`，styles.css）：让 scrollport 边缘在内容抵达浮动 chrome 前溶解的 mask utility（先例：overlay chat 视口）。**按面施用**，每个渐隐区与该面自身的内容 padding 配对——**永不进共享 primitive**：primitive 里闲置的类名会在同名 `@utility` 定义出现的那一刻活过来。

## 6. Composer / 输入卡

- **质感配方**：大圆角（`rounded-2xl`）+ 内部空气（`p-5`、输入区 `h-24`）+ **耳语级中控区**——底排控件一律 `variant="ghost"` 纯文字 + 小图标，send 是唯一深色实心锚点。**填充灰（`bg-muted`/`bg-inset`）只给内容容器（inset 块、信息 pill、badge），永不给操作按钮**。
- **结构**：shell = shadcn `InputGroup`（`MentionEditor` 根挂 `data-slot="input-group-control"`）重涂卡律——`border-0` + `bg-card` + `ring-foreground/10` 发丝 + **无 shadow**；保留 block-start / block-end addon 解剖 + focus-within 环 + cursor-text 点击聚焦。**密度活在 addon 上不在容器上**：padding asymmetric（20/20/12）；折叠带同动画过渡 maxHeight 与单边 padding（flex item 的 padding 在 `max-height:0` 下不裁剪——静态 padding 类禁用）。
- 三带：① 顶 = 资产 chips（视频缩略+时长 / 音频波形+时长 / 文档 icon+格式；page count 走 pdf.js 不上 chip；上传中 spinner+%；× 删且删资产）② 中 = `MentionEditor` 带 ③ 底 = 控制行。
- **Home 形变**：在 20vh hero 下居中停驻 → 滚动钉顶成 stadium 单行探索条（§1 例外 3）。形变走 scroll-linked `dockP`（钉前 140px 纯函数），**禁时钟过渡**（快滚会滞后成半熔 stadium）；属性 = 插值（padding 20→16、editor 96→56、chips/控制行折叠、radius 16→40、send 锚点、backdrop）。**半径走内联 style**（绕开 `has-data-[align=*]` 的 `:has()` 优先级）。Hero lockup（LogoMark + wordmark，mark 用 em 单位）常驻钉缩（`text-3xl/sm:text-4xl` → `text-xl`），品类句折叠（chrome 内 maxHeight + 折叠带低于 chrome 顶边，钉点零位移）；rest offset = `h-[28vh]` spacer 兄弟节点。
- **Entity 钮**（底排左）：`Assets`（Plus 图标）= **纯圆形图标钮**（`variant="ghost"` `h-9 w-9` 36px + `size-4.5` 18px glyph + `rounded-full` + 功能 Tooltip；实现 = 共享叶子 `components/composer/ComposerPanelButton`），**完全无状态**——无计数、无 Auto/人名 value 文本，选中态只在各自弹窗面板里读（钉顶条同样无文件计数）；暂存文件的可见性 = 既有 chips 带。`Persona` 钮隐藏（`SHOW_PERSONA` 旗标留座，随定位/memory 运营端迭代回归）。
- **glyph 左缘对齐律**：左钮组带 `-ml-[9px]`——18px glyph 居中于 36px 钮内（左偏 9px），负边距让首个 glyph 左缘与编辑器文字左缘像素级对齐（hover 圆底向左溢出属正常；测量锚 = `data-tour="composer-assets"` 的扩态钮，钉顶条隐藏 attach 钮会污染测量）。dock 的 12px rail 对应 `ml-[3px]`/`mr-[3px]`——同一法律两个取值。
- 按钮开 frosted `Popover` `side="bottom"`（向下开；overlay-surface + 浮层耳语 shadow；scroll 列表 `no-scrollbar`）。**Assets 面板** = 上传行 + 文件行 + ×；行解剖 = h-9 类型 tile（方 = 文件 / 圆 = 身份）+ 名/类型化 meta 双行（AV = kind · duration · size，`formatFileSize` ∈ `lib/stagedFiles.ts`）+ 垂直居中 ×；**一置律**：面板 = chips 带展开态，开则带收，文件列表只在面板。面板组件住 `components/composer/`（AssetsPanel / PersonaPanel / ModelsPanel）。人设编辑走 `/personas`。
- 底排 = **卡内一整行**（无独立 action-bar 条 / muted 背景）：左 entity 钮，右 **Models 钮**（Box 图标）+ 圆形 send 钮，控件 `h-9`。composer 无语言 / 产出 / 条数控件、零推断（行为合同归 CHAT_ARCHITECTURE）。
- **Models = 诚实 Auto 信息面板**：frosted Popover `w-88` = semibold 标题 + Auto 锁定 Switch（**`readOnly` 非 `disabled`**——readOnly 保全黑 ON 轨不灰化，Auto 是事实展示不是控件）+ **锚点 tabs 行**（Writing / Voice / Captions / Music；tab 是媒体类型名词；`bg-inset` track + `bg-card` thumb 共享 segmented 配方）+ 下方单滚动区按模态分 group（tab 不是过滤器，点击平滑滚动到对应 group，scrollspy 让激活 tab 跟随滚动；滚动区 `relative` 容器保证 group `offsetTop` 相对它测量；**底部 spacer 让末组也能锚到顶**，否则 max-scroll 钳位 tab 无法跟随）。**group 解剖 = muted 组标 + 模型行（裸图标 + semibold 模型名 + muted 用途 desc + 右侧 checkbox）**——行主名 = 模型名（曲库是 AI 生成产物不是模型名）；muted 方 tile 是 Assets 文件行解剖，禁搬到模型面板。无底部脚注。Auto switch 与每行 checkbox 同 register：`readOnly` 锁 ON（非 `disabled`）。除此之外全只读、无可选行、无 badge、无计时 chip——每个模态只有一个 provider 时没有可选择的东西，虚构 SKU 货架永禁。可选 picker 只在真实第二 provider 出现时落地，且用户形态是 policy switch（如 "prefer EU-hosted models"），不是模型 SKU 货架。
- 卡 padding 由 `CardContent` 控制（`Card` 加 `py-0` 去掉内建垂直 padding，避免双重 padding）。卡中部禁加分隔线 / border 来切开输入区与动作条——保持一整件。
- **Teaching 在 Tour，placeholder 只带示例**：placeholder = **固定前缀 + 3 条最常见 prompt 轮换**——前缀 "Ask Repurposer to " / "让 Repurposer "（`home.placeholderPrefix`），后缀在 `home.placeholderPrompts` 三条间每 3.5s 轮换（React overlay 实现——CSS `attr()` placeholder 不能动画；仅空编辑器可见，padding 随 dockP 插值）。**过渡 = 滚动窗**：旧行上滚出 + 新行下滚入，同向同时长同缓动（`styles.css` `.placeholder-roll-in/-out` 各 0.5s；`prev` 保持出场行挂载，absolute 不占布局，下行 key 重挂载复播；`prefers-reduced-motion` 出场行 display:none 退化为纯切换）；示例文案 = 直给动词 + 具体名词，保持单行长度（钉顶条只露一行）。
- **Tour = 3 步**（assets → prompt+send → recipe gallery；锚 `data-tour="composer-*"` / `data-tour="home-recipes"`）；**末步锚 = 第五张配方卡**（tour 滚动走 scrollIntoView block:"center"；row-2 首卡居中 = 任何屏高下网格填满视口、钉顶 composer 在顶；卡数 <5 该步自动跳过；target 串不变 = hash 不变 = 不重放）。**seen 版本 = 内容纯函数**（`lib/tour.ts`：djb2 hash 步骤配置 + EN 副本子树，EN 是 locale 真值源；storage = `localStorage["repurposer-tour-seen"]`；read/write 只在 `useEffect`，禁 SSR）。**任何内容变化触发 Tour 重放一次**——无手工版本号。新 tour 沿用同款：独立 storage 键 + 静态 `TourStepDef[]` + EN 副本 hash + `data-tour` 锚点。
- **Show grid ≠ tool grid**：composer 下方的能力图标行纯展示——不得用它切换产出或触碰 composer 参数。
- composer 无语言 / 产出 / 条数控件，零推断（行为合同归 `CHAT_ARCHITECTURE.md`）。

## 7. 侧栏解剖

- `SidebarProvider` + `Sidebar collapsible="icon"`；PC rest 为图标 rail，**可展开**：展开入口 = 折叠 rail 的 **hover-logo 槽位**（24px LogoMark 槽 hover/focus-within 交叉淡入成 PanelLeft 展开钮 + tooltip `a11y.openSidebar`，opacity 互换非 display——保键盘可达与槽位几何）+ 全端 `Cmd/Ctrl+B` hotkey。展开/折叠状态**持久化**——primitive 的 `setOpen` 写 `sidebar_state` cookie，`_app.tsx` loader 读回喂 `SidebarProvider defaultOpen`（SSR 首帧与 hydrate 一致；cookie 名从 `ui/sidebar.tsx` 的 `SIDEBAR_COOKIE_NAME` export 复用，禁硬编码）。
- **Rail = 一个顶层栈，logo 不是独立组**：折叠 PC **无 SidebarHeader**（`group-data-[state=collapsed]:md:hidden`；header 只在展开态出现 = lockup + 右侧 collapse 钮，全端同形）。logo 槽（**24×24 rail 档**；hover 展开钮同槽同步 24px + `size-4` glyph，形变零位移）是 `SidebarContent` 栈的**第一个成员**；栈 `group-data-[state=collapsed]:gap-5 pt-4`（logo→菜单组 = 20px，gap-5 是容器间距不是项间距），`SidebarMenu` 恒 `gap-1`（项间 40px 中心距）。
- 菜单项：cva `group-data-[collapsible=icon]:size-9!`（36×36，18px glyph 居中，active/hover 吃 `bg-sidebar-accent`）；rest 文字/图标 = `text-sidebar-foreground/70`（安静 rest 态；hover/active 经 cva 既有 `text-sidebar-accent-foreground` 转全色）。rail 宽 **52px**（`SIDEBAR_WIDTH_ICON = "3.25rem"`）。
- 导航项用 `SidebarMenuButton` + `render={<Link to="..." />}`，禁 `asChild`。
- **右发丝线**：`Sidebar` 保留 primitive 的 `border-r` 并显式发 `border-sidebar-border`（Tailwind v4 默认 border 色 = currentColor，必须显式 token；light oklch(0.9) / dark 白 10%）；`--sidebar == --background` 的填充融合不变（same fill + hairline）。
- 结构：
  - **Header**：只在展开形态渲染（PC 展开 + 移动 off-canvas）= logo lockup + 尾部 collapse 钮（全端，无 `md:hidden`）。无 "Invite members" 入口——无明确产品决策不得复活。
  - **Content**：扁平导航（无组标题）：Home、My projects（`/projects`）。Personas（`/personas`）入口隐藏（路由存活，随定位/memory 运营端迭代回归；composer 的 Persona 钮同批隐藏）。项目网格住 `/projects`，不在 home（home 只有 composer）。
  - **Footer**：用户头像开 **account console**——`Popover`，永不 `DropdownMenu`（它承载内联控件）：身份头（avatar + name + email）→ inset **账户块——只放 value surface**（plan / credits 槽位 / 订阅；settings 永不混进账户块；plan 行带文字**升级链接**）→ **偏好**行（标签行 + 尾部控件——theme / language 尾部 segmented：`bg-inset` track + `bg-card` thumb，theme 纯图标 pill；Settings chevron 行开**共享 `SettingsDialog`**，永不建站：左 section 导航 + 右内容，任何处可经 `useSettingsDialog().openSettings(section)` 唤起；section 在 `components/settings/SettingsDialog.tsx` 注册，channels 居首。`/settings` 只作 channels OAuth 回调 shim 存活——toast、开 dialog、bounce 回 home）→ 帮助区（replay tour——sessionStorage flag + `repurposer:replay-tour` 事件双通道送达，HomeComposer 消费先到者）→ logout。
  - **展开态 footer 行解剖**：`[avatar + name/免费版 两行][升级 pill]`——**一个容器持有 hover/open 填充**，但 **pill hover 时行底色让位**（`:has()` 守卫：`group-data-[state=expanded]:not-has-[[data-slot=button]:hover]:hover:bg-sidebar-accent`；open 态底色由 consoleOpen 驱动——pill 与头像区永不得读作两个独立视觉单元，且 pill 是独立交互目标）；trigger = **PopoverTrigger 原生 button 直挂类名**（不经 Button 组件——ghost variant 自带的 hover/aria-expanded 填充会与容器底色打架）；pill 是独立 `Button variant="outline"`（hover 补 `bg-accent`）`render={<Link to="/" hash="pricing" />}`，**永不嵌进 PopoverTrigger**；折叠 = 仅头像圆（+ tooltip，trigger 自带 `group-data-[state=collapsed]:hover:bg-sidebar-accent`）。升级目的地 = 落地页 pricing 锚，直到 W11 应用内购买入口落地。
- **无全局 AppHeader（ADR-046）**：studio 无常驻顶栏——工具件住 account console（theme / language），**通知铃 = 内容区右上角唯一浮动 chrome chip**（圆角方块 chip + 未读点；右上角槽位全站保留——页面级控件永不占那个角）。移动端保留浮动 sidebar 触发器。
- 导航 / 账户图标统一 `h-4.5 w-4.5`；`sidebarMenuButtonVariants` 里展开 `[&_svg]:size-4.5`、折叠 `group-data-[collapsible=icon]:[&_svg]:size-4.5`，保持一致。
- **折叠态居中对齐**：Header / Footer 里放的按钮（如头像）必须居中——容器加 `group-data-[state=collapsed]:items-center`，按钮自身折叠态用 `w-12` 方形；**不要**把这些按钮放进 `SidebarMenu`（列表 padding 会限宽，折叠态偏移 4px）。
- 新增侧栏入口时，同步更新 `zh.ts` / `en.ts` 的 `nav.*` 键。

## 8. 页面布局

- 页面主体放 `SidebarInset` 内；禁自带 `min-h-screen w-full` 覆盖侧栏结构。
- **`_app` 下页面用 `flex-1` 填满视口，永不 `min-h-svh` / `min-h-screen`**：`SidebarInset` 是 `min-h-svh` flex 列（无全局 header，ADR-046），`flex-1` 让页面贴着它；更高内容滚动窗口。**例外——home 是固定 app-shell 面**：根 `h-svh` 永不滚动；**一个内部 scrollport**（`no-scrollbar`）容纳一切——hero 舞台、composer（sticky chrome，rest 居中停驻、滚动钉顶成单行 stadium 条）与 gallery。未来任何固定面页面同形：根 `h-svh` + 恰好一个内部 scrollport。（落地页 `/` 在 `_app` 外——它的 `min-h-svh` 合法。）
- gallery 筛选行 = sticky chrome 的第三寄存器（骑 chrome 吸顶，零自养动画），按素材维度过滤（`GALLERY_FILTERS`，宽槽卡多归属）。
- **输入框独立层律**：输入组永远是独立层，永不与消息流融合——历史区作为自有磨砂层浮在它上方（与 question pill 同一 dock-surface 族）。
- **Dot grid = 结果画布签名，只此一面**：只有 FlowView 的 `dots` prop 携带它——32px 间距 + 2px 直径点（react-flow `size` 是直径）+ muted-foreground 32% light / 30% dark；纯世界空间，随 zoom 缩放（不重铺、不加 zoom 补偿）。home 无点阵——不可平移的面背后放固定纹理是在广告不存在的 affordance，且单面使用让点阵**意味着**「你进入了图」。没有 `dot-grid` CSS utility；任何第二个点阵面即违规（ADR-046 附）。

## 9. 结果画布（FlowView）形态

> 数据面 / 相机律 / 图契约归 `CHAT_ARCHITECTURE.md` §5（词表 v3、相机 C6、直读持久图）；本节是它的视觉与交互形态。

- DAG 用户形态 = 只读图（`components/flow/`），无 drag/connect/pan/zoom API（结构，非约定）；缩放/平移按面门禁（配方说明书 = 锁 fit，结果画布 = 开）。手动布线 UI 永不开放。
- **端口法则**：**进 = 消费区域的左下角，一条角律两个区域**——媒体流 video/audio 的消费区域 = 内容区，锚内容区左下角（PROMPT 分界上 16px，底锚上堆）；文本流 text/ctx = 提示词区左下（factsbar 带上）。**出 = 生产区域右上，出锚语义律（ADR-067）**：出锚 = 节点自身产出媒介（媒介五值直出、text/table 读 prose，素材档案按 asset_type，modifier/materialize 过渡词按 frame_class——一节点一出发锚，出边同点出发），入锚 = 边承载类型；跨媒介边 = 边上转译叙事（video→text），源节点永不长外来 glyph；image/slides 出锚 = 渲染侧第五 glyph（从不过线），ctx 引用流无自有 glyph——入锚并入共享 T（@ 永不上画布：node 左舷只有 T / image / video 三类 icon）；video/audio/text/ctx 类型化着色；连线 = 圆缘贝塞尔（可见圆即 Handle，xyflow 原生锚 = 矩形位向外缘，切线水平出右缘入左缘）。
- **节点态原地表达**：draft 虚线估价 / running CSS 擦除封顶 96% / done 内容自证 / failed 卡内红 / stale factsbar 徽；caption 右槽恒空。**失败人话行**：failed 卡读 `spec.error`（sync 时从 failed family step 烤入、家族恢复即清）。
- **卡面交互律**：factsbar 动作 = copy-or-download + 发布（Send——发布取代删除上栏，产物删除在画布无家；素材条只保下载——删除全画布无家）；无 ⋯ 菜单。**点击 = 选中 + 右侧档案（OutputInspector，全产物类型）**；大屏查看归 hover expand 钮的 lightbox，无居中播放器 modal。
- **全文卡律（ADR-063）+ 封顶滚动律（ADR-067）**：卡面内容 = 原文全文，永无摘要/浓缩/省略号——DocumentCard 全文渲染 + 卡高封顶 560（`DOCUMENT_MAX_H`），超出正文卡内就地滚动（nowheel+nopan）；文档框出生即全文需求高、同值封顶（graph_store `_document_frame` ↔ layout.ts 一条测量律两镜像互引——间距常数同律：`_GAP_MAIN`/`_GAP_CROSS`/`_FRESH_COLUMN_RISE` ↔ `GAP_MAIN`/`GAP_CROSS`）。**DocumentCard 最小产物尾**：`output_ids` 非空 → 卡内底部 factsbar = 版本 pager + copy/download + 开 OutputInspector。
- **估价诚实面**：折叠含未报价节点时全 NULL 显示「估价随运行」、部分折叠开口「+」——确认拍永不许诺 ≈0。
- **比例尺 pill = 缩放菜单**（Figma parity）：pill（实时百分比 + chevron）开 DropdownMenu：放大 / 缩小（中心步进）/ 适应窗口（共享 padding fitView）/ 缩放至 50/100/150%（xyflow zoomTo 中心锚）；⌘+/⌘-/⌘0 快捷键仅指针悬停画布时绑定；浏览器自身缩放出画布不染。
- 编辑 = chat 或卡面 prompt 直改（同一个 `edit_prompt` wiring op；通道分家与反馈律归 CHAT_ARCHITECTURE §9）。

## 10. 颜色与字重

- 只用 shadcn 主题变量（`bg-background` / `text-foreground` / `text-muted-foreground` / `bg-card` / `ring-border` 等），禁硬编码色值（如 `#333`）。
- 正文与控件保持常规字重；pill / 次级按钮文字不加粗。
- **数据 vs 文案**：一切 UI 文案走 i18n；用户数据（人设名、项目标题等）原样显示——别因为中文就当「未国际化」；但**默认值不得回退到某个具体数据条目**（如 Persona 默认显示本地化占位，让用户主动选）。
