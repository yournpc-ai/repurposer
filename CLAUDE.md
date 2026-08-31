# Repurposer — Claude Collaboration Guidelines

> This document records the frontend conventions and common pitfalls of the Repurposer project, to be followed by AI collaborators.

## Key Docs

Read these before touching a subsystem (check each doc's own status line — some describe proposed work not yet landed on `main`):

- `docs/README.md` — **docs 索引与治理原则（单一事实源表）**，找文档先查这里。
- `docs/PROGRESS.md` — 进展快照 + 排期 + 需求池的**唯一事实源**；排期/优先级只准引用它。
- `docs/MODULE_ARCHITECTURE.md` — 六层模块图 + **表归属契约**（每张表只有一个 owner 模块）+ 跨模块通信规则 + §7 代码地图/队列机制/数据约定（现状架构唯一事实源）；新表/新模块/新认领源必须在此登记。
- `docs/POSITIONING.md` — **定位根概念架构（运营层母文档，ADR-042，已拍板未实施）**：身份根 = 定位（positioning），人设收窄为表达分区，渠道/选题/素材挂根；施工排期 = PROGRESS 第六~八周。动身份模块/渠道/选题/home 前先读它。
- `docs/AGENT_ARCHITECTURE.md` — 四层工程地图（Model / Harness / Graph / Loop，ADR-039）：工具包 `app/tools/`（能力唯一家，N-42 前 `app/skills/`）+ agent registry `app/agents/`（一个 Agent 类 + 声明实例）+ `NodeBase` 图内核（报价=fold / 执行=topo / 校验=∀ / 对账=⊆）+ chat 治理环。agent 架构唯一事实源；outputs 可扩展（产物 = 工具的属性，注册表派生）。
- `docs/MUSIC_ARCHITECTURE.md` — AI-generated music library backed by a dedicated `Music` table. Implemented (Layer-4 music verification still future).
- `docs/RENDERING.md` + ADR-016 — clip-spec is the **sole render contract**（字段级契约与渲染链架构的唯一事实源）; the renderer is a replaceable black box. Do not leak Remotion/React concepts into clip-spec. 编辑器交互与范围纪律在 `docs/VIDEO_EDITOR.md`。
- `docs/DECISIONS.md` — ADRs，**只保留现行决策**：过时 / 被翻案的内容直接删除（历史在 git，不留痕）；新决策追加新编号，编号不连续属正常。
- `docs/COMPETITIVE_ANALYSIS.md` + `docs/DECISION_MATRIX.md` + `docs/research/` — 竞品综合 / 采纳矩阵 / 原始证据三层，评估竞品功能时按此顺序查。
- `docs/DATABASE_MIGRATIONS.md` — Alembic workflow; `migrations/versions/*.py` is part of the codebase and must be committed.
- `docs/tasks/` — per-feature implementation briefs with acceptance criteria and explicit "Prohibited Behaviors"; read the relevant task before starting and respect its prohibitions. 已完成简报归 `docs/tasks/done/`（历史记录，不再维护）。

## Tech Stack
- Frontend framework: TanStack Router / TanStack Start (React 19 + SSR)
- UI components: shadcn/ui (base-ui version)
- Styling: Tailwind CSS v4
- Icons: lucide-react (sole icon source)
- Internationalization: i18next + react-i18next
- State: React Context + hooks (no Redux / Zustand in this project)

## shadcn / base-ui Conventions

### Use `render` prop, not `asChild`
The shadcn components used in this project are based on **base-ui**. Their trigger components (`Button`, `DialogTrigger`, `DropdownMenuTrigger`, `PopoverTrigger`, `SidebarMenuButton`, `TooltipTrigger`, etc.) **do not support the Radix-style `asChild`**; instead, they use the `render` prop to specify the rendered element.

Incorrect:
```tsx
<Button asChild><Link to="/" /></Button>
```

Correct:
```tsx
<Button render={<Link to="/" />}>Label</Button>
```

### Icons
- All icons must be imported from `lucide-react`.
- Hand-written SVG icons are prohibited in the project, with two exceptions: third-party logos with no lucide alternative, and **the brand mark** — `src/components/LogoMark.tsx` (a solid "delta": one stream fanning out into many). Its geometry's source of truth is `LogoMark.tsx`; `public/favicon.svg` is the static baked-color copy and must be kept in sync. Logo lockups use `<LogoMark />` + the "Repurposer" wordmark — never rebuild the tile by hand.
- Size conventions:
  - Top bar / card action icons: `h-5 w-5`
  - Inline / pill icons: `h-4 w-4`, smaller auxiliary icons: `h-3.5 w-3.5`
  - Sidebar navigation icons: `h-4.5 w-4.5` (consistent when expanded / collapsed; see below)
  - **Inside `Button`, use `size-*` not `h-* w-*`** (2026-08-30 实测坑): every button variant pins `[&_svg:not([class*='size-'])]:size-N` (`size="icon"` pins 3.5 = 14px) — `h-5 w-5` does NOT match the `:not()` guard and gets silently overridden to 14px; `size-5` contains `size-` and is exempt. Measured, not guessed: `h-5 w-5` in an icon Button renders 14px.

## Component Usage Guidelines

### Border Radius & Buttons
- **Uniform small radius**: buttons, inputs, cards, pills, and dropdown triggers all use the default `rounded-md` (cards / panels may use `rounded-lg`).
- **`rounded-full` is prohibited**, with only the following three exceptions:
  1. True circular icon buttons (e.g., the send arrow in the bottom-right corner of an input: `h-9 w-9 rounded-full`).
  2. Status badges / red dots (notification corner markers).
  3. The home composer's docked **one-line explore bar** (stadium / half-height radius, user-ruled 2026-08-21, MiniMax parity — the expanded composer stays `rounded-2xl`).
- The shadcn `Badge` component's base style is `rounded-full` — always override with `className="rounded-md"` when using it for metadata tags (durations, aspect ratios, labels).
- Controls in the same row must align on the row's center line: action-area controls are uniformly `h-9`, matching the send button height. **Exception (2026-08-31, Lovart measured)**: the composer's GHOST circle icon buttons are `h-8 w-8` (32px — one quiet register below the 36px dark send anchor; the size gap IS the hierarchy).
- Pill / dropdown trigger **text must not be bold** (do not add `font-medium`), keep it lightweight.

### Overlay Components (DropdownMenu / Popover / Select)
- **List-style single-select** (select and close on click): use `DropdownMenu` + `DropdownMenuItem`.
- **Content panels with inline actions** (buttons/links/rows that must not close on click — e.g. the notification panel): use `Popover`, never `DropdownMenu` (precedent: `NotificationBell`).
- **Multi-control settings panel** (needs to stay open while adjusting multiple values): use `Popover`, with segmented button groups inside.
- Triggers are always `render={<Button variant="outline" size="sm" className="h-9 …" />}`, with "icon + label + `ChevronDown`" inside the button.
- To express "currently selected" for an option, use the `Check` icon; for bottom overlays (dropdowns in the footer), remember `side="top"` to pop upward.
- Pure dropdowns in forms use `Select`; parameter selection in the prompt action bar uses the pill pattern above — do not mix styles.

### Card Depth: hairline + soft shadow — no visible strokes
- **The base `Card` primitive ships a `ring-foreground/10` hairline** (dark: white 10%, reads as a glass edge). On the light theme the page is a **0.96 neutral-gray underlay** and white cards float via the fill step alone — NO shadow. **Elevation law (both themes, ADR-046): the raised surface is the lighter fill on the darker ground** — light: page 0.96 → card 1.0; dark: page 0.12 → card 0.21.
- **Shadows belong to floating layers only** — in-flow surfaces (cards / composer / media tiles) never carry `shadow-*`, either theme. Light floating layers (the `overlay-surface` frosted family) carry the whisper `shadow-xl` (it lifts the glass off the content beneath); dark keeps its no-shadow tradition (every `shadow-*` utility compiles to transparent under `.dark` via one switch in `styles.css`; focus rings survive — they compose via `--tw-ring-shadow`) — translucency + the hairline do the separating.
- **Prohibited: visible strokes** — `border` + `border-border`, `ring-1 ring-border`, and `ring-foreground/*` stronger than the /10 hairline. The /10 hairline MAY coexist with a shadow only on floating layers; in-flow cards carry neither a visible stroke nor a shadow. (`border-dashed` dropzones and `border-transparent` variant bases are fine; focus rings are interactivity, not edges.)
- Separation between sections comes from spacing and token steps (`bg-muted` / `bg-inset` fills), never from drawn dividers.
- **Fill first — the hairline is the fallback, not the default**: if a surface's fill already distinguishes it from what sits behind it (a `bg-muted` chip on a `bg-card` panel, media content on the page), it takes NO ring/border at all. The `ring-foreground/10` hairline exists only for same-fill boundaries where the edge would otherwise disappear — a white card on the white page, the frosted modal over its backdrop wash (the sign-in dialog). When a same-fill element needs separation, prefer STEPPING ITS FILL to a token step over drawing a stroke.
- **Hero surfaces = 完全平**：home composer = 白平卡 on 灰页（发丝线，无 shadow），entity 走底排 pill（参 Composer 节）。**Composer 卡禁用 `backdrop-filter`** —— 祖先 backdrop-filter 会成为 Backdrop Root，后代 MentionPicker 走其子树 blur（nothing to blur → 退化为纯染色）。Media / schematic tile 无环、无影（fill 步分；gallery 封面 tile = **`bg-card` 浮起面**——2026-08-31 用户裁定：页面已有灰底，8 张封面从 `bg-inset` 灰井改白卡，light 0.96→1.0 / dark 0.12→0.21 高程步；hover chrome = **仅右上 expand 钮**（`bg-accent` token 步）——居中 Remix pill 同日退役：整卡 cursor-pointer + expand 已足够表达可点，居中 pill 只遮挡示意图（示意图就是卡面）；线条吃 `foreground` alpha）。
- **Gallery card state machine（ADR-048 + RECIPES §4 / §4.8）**：封面是单色工艺示意图（**永不实拍**）。Rest = 内联 SVG 静态封面（`components/recipes/covers/<id>.svg`，foreground 灰阶自驱双主题反转，16:10，左输入→右输出）；hover 播 CSS keyframe 过程动画（零视频零声音零媒体请求）。Evidence 入 overlay：网格零真容（Soon/reserved 形态退役），**卡没有真实成对示例 = 不进网格**（RECIPES §4.8 准入）。三行卡下文字 = 菜名 / promise（2 行 clamp）/ 适用素材。**Prohibitive**：无画幅 badge / 无类别 chip / 无渠道名于卡面（卡只承载 genre）；渠道挂发/排期变量（预填模板默认，chat 覆写）。网格 = 4/3/2 列等宽，**无 featured 跨列**（编辑优先 = 排序位），MasonryGrid 退役。Hover-with-sound 已迁入 overlay Examples tab（点击 = 手势，声音原生）。
- **Gray ladder**: surface hierarchy comes from the stepped tokens, never from one-off alpha fills. **Light**: `--background` is **0.96 neutral gray** (ADR-046; pure white retires to the landing page — the marketing register is separate, see the Scope rule) — the white `--card` (1.0) is the raised layer and floats via the fill step, not a shadow; on-card fills stay `--subtle` 0.975 → `--muted` 0.95 → `--inset` 0.92 (they live on white cards / panels). **Dark**: `--background` is **near-black** (0.12) and elevation speaks **glass, not ladder** — floating layers are translucent (see `overlay-surface`), `--card`/`--popover` 0.21, `--muted` 0.24 (`--subtle` collapses onto it), and **`--inset` is INVERTED: 0.15, darker than the panel** (kbd chips / seed values / search inputs sit in darker wells). **`bg-muted/50`, `bg-background/60`, `bg-muted/30` and similar ad-hoc alphas are prohibited** — an inner block uses solid `bg-muted`, a nested block on a muted card inverts to `bg-card`.
- **Hover / highlight = `--accent`, one token both themes**: light = solid 0.92 gray step (derived against the 0.96 page; on white cards it reads as a clear but quiet step); **dark = `oklch(1 0 0 / 8%)`, a translucent white veil** (never a lighter solid step). Menu rows, list hovers, picker selected states, ghost-button hovers all consume `bg-accent` (or `/50` for the weak tier), so one variable retunes every hover in the app. Never hardcode hover COLOR VALUES per instance (`dark:hover:bg-[oklch(…)]` banned) — but **variant pairing is still mandatory**: `dark:bg-*` beats a bare `hover:bg-*` in the cascade, so an element carrying `dark:bg-x` must also carry `dark:hover:bg-accent` explicitly.
- **Text is three tiers, not two**: `foreground` (0.145 / dark 0.95) → `muted-foreground` subtitles (0.556 / dark 0.63) → **`meta-foreground`** (0.68 / dark 0.52) for small ALL-CAPS tracked meta labels (the "MODEL / SEED" style), composed via the `text-meta` utility (`uppercase` + `tracking-[0.08em]` + the token color).

### Floating Layers: frosted glass via `overlay-surface`
- **All floating layers** (Popover / DropdownMenu / Dialog / Select / Sheet / Tour) use the shared `overlay-surface` utility defined in `styles.css` — translucent `--popover` + `backdrop-blur` + `saturate(1.4)`, **per-theme recipe**: light = **92% + blur(24px)** (lower opacity lets dark content behind bleed through and tint the panel); dark = **68% + blur(28px)** (over the near-black canvas a high-opacity fill reads as a solid box and the blur has nothing to show). Solid fallback under `@supports not (backdrop-filter)`. **Shadow law (ADR-046)**: the utility carries the whisper `shadow-xl` in light (lifts the glass off the content beneath) and no shadow in dark (the existing `--tw-shadow-color` switch). Do **not** re-add `bg-popover` to overlay components, and **per-instance frost patches (e.g. `dark:bg-white/10`) are banned** — tune the shared recipe; if a specific instance genuinely needs different opacity, override via its `className` (components merge it last, keeping it the open extension point).
- Dialog / Sheet backdrops are **per-theme**: light = `bg-background/60` (a white wash — a black scrim over the white page reads as gray murk) + `backdrop-blur-[2px]`; dark = `bg-black/30` + `backdrop-blur-[2px]` — the frosted surface reads against a dimmed but clearly visible page in both themes.
- **Overlay chrome = the Dialog primitive, never hand-rolled** (`fixed` backdrop + glass div). A hand-rolled backdrop wrapping the panel kills the glass: an ancestor carrying `backdrop-filter` becomes a Backdrop Root, and a descendant panel's `overlay-surface` blur then samples only that subtree (nothing to blur) — silently degenerating to a flat tint. The primitive portals overlay and content side by side, which is the only correct structure.
- **`DialogContent` centers via `-translate-1/2`** — a transformed popup becomes the containing block for `fixed` descendants, teleporting viewport-anchored floaters. Viewport-anchored floaters therefore portal to `document.body` (the `MentionPicker` does), which is immune to ancestor transforms and backdrop-filters; a popup that must host a NON-portaled fixed floater composes `DialogPortal` + `DialogOverlay` + `DialogPrimitive.Popup` by hand and centers with `inset-0 m-auto` (no transform). **A hand-composed popup must mirror `DialogContent` chrome exactly** — `overlay-surface` + `ring-1 ring-foreground/10` hairline + `shadow-xl` + `rounded-xl`; without the hairline the light-theme glass dissolves into the white backdrop wash (RecipeInspectOverlay lost it once, 2026-08-10). (Precedent: `RecipeInspectOverlay`.)
- Tooltips and sonner toasts are intentionally excluded (small transient labels stay solid).
- **Scroll fades** (`scroll-fade-y` / `scroll-fade-x` in `styles.css`): mask utilities that dissolve a scrollport's edge before content reaches floating chrome (precedent: the overlay chat viewport). Apply **per surface**, each fade zone paired with that surface's own content padding — **never inside shared primitives**: an unused class sitting in a primitive comes alive the moment a same-named `@utility` is defined.

### Composer / Input Card
- **质感配方（Lovart composer 参照）**：大圆角（`rounded-2xl`）+ 内部空气（`p-5`、输入区 `h-24`）+ **耳语级中控区**——底排控件一律 `variant="ghost"` 纯文字+小图标，只有 send 一个深色实心锚点。**填充灰（`bg-muted`/`bg-inset`）只给内容容器（inset 块、信息 pill、badge），永远不给操作按钮**——参考图中底排只有 credits 一个信息 pill 有填充，按钮全裸。
- **Structure（ADR-046 + ADR-048 walkthrough）**：shell = shadcn `InputGroup`（`MentionEditor` 根挂 `data-slot="input-group-control"`）重涂卡律——`border-0` + `bg-card` + `ring-foreground/10` 发丝 + **无 shadow**；保留 block-start / block-end addon 解剖 + focus-within 环 + cursor-text 点击聚焦。**密度活在 addon 上、不在容器上**：padding asymmetric（20/20/12）；折叠带同动画过渡 maxHeight 与单边 padding（flex item 的 padding 在 `max-height:0` 下不裁剪——静态 padding 类禁用）。三带：① 顶 = 资产 chips（视频缩略+时长 / 音频波形+时长 / 文档 icon+格式；page counts 走 pdf.js 不上 chip；上传中 spinner+%；× 删且删资产）② 中 = `MentionEditor` 带 ③ 底 = 控制行。Home = 在 20vh hero 下居中停驻 → 滚动钉顶成 stadium 单行探索条（third `rounded-full` 例外）。**Dock 后内部**：attach 单边折叠零宽，单行输入 `h-14`，send = bottom-right 绝对锚点不参与折叠。**形变走 scroll-linked `dockP`（钉前 140px 纯函数）**，**禁时钟过渡**（快滚滞后成半熔 stadium）；属性 = 插值（padding 20→16、editor 96→56、chips/控制行折叠、radius 16→40、send 锚点、backdrop）。**半径走内联 style**（绕开 `has-data-[align=*]` 的 `:has()` 优先级）。Hero lockup（LogoMark + wordmark，mark em 单位）持续常驻钉缩（`text-3xl/sm:text-4xl` → `text-xl`），品类句折叠（chrome 内 maxHeight + 折叠带低于 chrome 顶边，钉点零位移）；rest offset = `h-[28vh]` spacer 兄弟节点。
- **Entity buttons**（底排左，2026-08-30 从 pill 改制，Lovart 式）：`Assets`（回形针）/ `Persona`（人像）= **纯圆形图标按钮**（`variant="ghost"` **`h-8 w-8` 32px + `size-4.5` 18px glyph**——Lovart devtools 实测解剖：32 钮 / 18 svg / ~13 视觉笔画，62%→56% 比率才不胀；比 36px send 锚点低一个安静 register，尺寸差就是层级——`rounded-full` + 功能 Tooltip），**完全无状态**——无计数、无 Auto/人名 value 文本，选中态只在各自弹窗面板里读（钉顶条同样无文件计数）；暂存文件的可见性 = 既有 chips 带（行为不变）。**glyph 左缘对齐律（2026-08-31 实测）**：左钮组带 `-ml-[7px]`——18px glyph 居中于 32px 钮内（左偏 7px），负边距让首个 glyph 左缘与编辑器文字左缘像素级对齐（Lovart 同；hover 圆底向左溢出属正常；测量锚 = `data-tour="composer-assets"` 的扩态钮，钉顶条隐藏 attach 钮会污染测量）。**按钮开 frosted `Popover` `side="bottom"`**（向下开，扩态卡 mid-viewport 上开盖输入区；overlay-surface + 浮层耳语 shadow；scroll 列表 `no-scrollbar`）。**Assets 面板** = 上传行 + 文件行 + ×；行解剖 = h-9 类型 tile（方 = 文件 / 圆 = 身份）+ 名/类型化 meta 双行（AV = kind · duration · size，`formatFileSize` ∈ `lib/stagedFiles.ts`）+ 垂直居中 ×；**一置律**：面板 = chips 带展开态，开则带收，文件列表只在面板。**Persona 面板** = Auto 行 + 人设行（avatar / Auto 圈 chip 圆 tile + 名 / tags · 声音绑定 meta）+ manage 链。`AssetsModal` / `PersonaPickerModal` 退役（深资管属未来资产中心页；人设编辑仍走 `/personas`）。
- Bottom row is **one continuous row inside the card** (no separate action-bar strip / muted background): entity buttons left, the **Models button** (Box icon) + the circular send button on the right, controls at `h-9`. The composer has **no language / outputs / clip-count controls and runs no inference of its own** (see behavioral contract). **Models = 诚实 Auto 信息面板**（2026-08-30 用户拍板，在此只读形态上取代 2026-08-22 "no model control" 退役裁定）：frosted Popover `w-88` = semibold 标题 + Auto 锁定 Switch（**`readOnly` 非 `disabled`**——readOnly 保全黑 ON 轨不灰化，Auto 是事实展示不是控件）+ **锚点 tabs 行（文案/配音/字幕/音乐——en 标签 = **Writing**/Voice/Captions/Music，"Copy" 动词歧义（读成「复制」）2026-08-31 退役；Lovart tab = 媒体类型名词，bg-inset track + bg-card thumb 共享 segmented 配方）+ 下方单滚动区按模态分 group**（Lovart 结构：tab 不是过滤器，点击平滑滚动到对应 group，scrollspy 让激活 tab 跟随滚动；滚动区 `relative` 容器保证 group `offsetTop` 相对它测量，**底部 spacer 让末组也能锚到顶**，否则 max-scroll 钳位 tab 无法跟随）。**group 解剖 = muted 组标 + 模型行（裸图标 + semibold 模型名 + muted 用途 desc + 右侧 checkbox）**——行主名 = 模型名（MiniMax M3 / speech-2.6-hd / Whisper / **MiniMax music-2.6**，曲库是其 AI 生成产物不是模型名），muted 方 tile 是 Assets 文件行解剖，禁搬到模型面板。**无底部脚注**（2026-08-31 用户裁定删除 Auto 说明句）。**Auto switch 与每行 checkbox 同 register：`readOnly` 锁 ON（非 `disabled`，保全黑填充）——「Auto 在这些模型里挑」是事实展示不是控件**；除此之外全只读、无可选行、无 badge、无计时 chip——每个模态只有一个 provider 时没有可选择的东西，也无档位/延迟数据可展示，虚构 SKU 货架永禁。可选 picker 仍只在真实第二 provider 出现时落地，且用户形态是 **policy switch**（如 "prefer EU-hosted models"），不是模型 SKU 货架（裁定见 PROGRESS 需求池 "LLM provider 抽象"）。
- Card padding is controlled by `CardContent` (`Card` adds `py-0` to remove built-in vertical padding, avoiding double padding).
- Do not add a divider / border in the middle of the card to separate the input area from the action bar; keep it as one piece.
- **Teaching 在 Tour，placeholder 只带示例**：placeholder = **固定前缀 + 3 条最常见 prompt 轮换**（Lovart 式，2026-08-30）：前缀 "Ask Repurposer to " / "让 Repurposer "（`home.placeholderPrefix`），后缀在 `home.placeholderPrompts` 三条间每 3.5s 轮换（React overlay 实现——CSS `attr()` placeholder 不能动画；仅空编辑器可见，padding 随 dockP 插值）。**过渡 = 滚动窗非闪烁**（2026-08-31 用户裁定，首版 blink-swap 退役）：旧行上滚出 + 新行下滚入，同向同时长同缓动（`styles.css` `.placeholder-roll-in/-out` 各 0.5s；`prev` 保持出场行挂载，absolute 不占布局，下行 key 重挂载复播；`prefers-reduced-motion` 出场行 display:none 退化为纯切换）；示例文案 = 直给动词 + 具体名词，保持单行长度（钉顶条只露一行）。用法教学仍归 Tour：新手 = 4 步 Tour（assets → persona → prompt+send → recipe gallery，`data-tour="composer-*"` / `data-tour="home-recipes"`）；**第 4 步锚 = 第五张配方卡**（2026-08-31 用户裁定：tour 滚动走 scrollIntoView block:"center"，锚首卡会滚过头；row-2 首卡居中 = 任何屏高下网格填满视口、钉顶 composer 在顶，相对定位不怕高度差；卡数 <5 步自动跳过；target 串不变 = hash 不变 = 不重放）；**seen 版本 = 内容纯函数**（`lib/tour.ts`：djb2 hash 步骤配置 + EN 副本子树，EN 是 locale 真值源，任何副本改动触发；storage = `localStorage["repurposer-tour-seen"]`；read/write 只在 `useEffect`，禁 SSR）。**任何内容变化触发 Tour 重放一次**——no manual 版本号、no "值得重放"判断。新 tour 沿用同款：独立 storage 键 + 静态 `TourStepDef[]` + EN 副本 hash + `data-tour` 锚点。
- **Results tour**（ADR-041）：独立键 `localStorage["repurposer-results-tour-seen"]` + 同内容 hash 规则；锚 `data-tour="results-*"` 于画布首 ready 产物节点；完成转场后触发一次（fresh 或来自 `/projects` 都一样）。

#### Composer behavioral contract（意图层单面化：chat 唯一入口）
- **Prompt is required**: submitting with an empty prompt is blocked locally (toast), same posture as the auth gate. Files are optional — a prompt-only send creates **no** asset: the PlanAgent judges whether a message IS the user's own content (pasted transcript/draft, with or without "this is my…" framing) and promotes it to a real transcript asset (`create_transcript_asset_from_text`); a generate request with no assets and no pasted content gets an ask-for-material answer, never a groundless task book. Never reintroduce length-based heuristics — content-vs-request is LLM-judged only. Mid-conversation uploads go through the chat dock's attach button — picked files **stage as lifecycle chips inside the input group** (uploading → done/error, × removes and deletes the asset; direct-to-storage, same flow as the composer) and only the **send button** consumes them, riding the turn as message `attachments` (persisted, re-rendered on refresh). Picking a file never sends anything by itself; an attachment-only send is legal — the plan path infers from an honest stand-in line, and a blank message never auto-answers a docked checkpoint.
- **The composer does NO intent recognition**（简报 `docs/tasks/intent-surface-unification.md`）: send = spinner (create empty project + upload assets) → navigate to `/projects/$id` — the project page is **always canvas + chat dock**（ADR-051, 2026-08-31: the `?overlay=chat` / `?overlay=run` route params and the fullscreen overlay shell are retired — never reintroduce an overlay route concept）— with the draft handed over via router state → the chat dock sends it as the first `POST /chat` message (mentions + `persona_id` ride along). `POST /chat` is the **only intent surface**: the plan path builds / refines / confirms the task book (PlanAgent); projects with runs go to the four-state ChatIntentAgent. Never reintroduce a second intent entry (e.g. a dedicated `/intent` endpoint).
- **clips need media**: enforced server-side — the PlanAgent excludes clips for text-only input; `create_run` mirrors with 422 at the birthplace.
- **Show grid ≠ tool grid**: the capability icon row below the composer is display-only — it must not switch outputs or touch composer params.
- **Mentions = 第四载荷字段**（方针 `docs/MENTIONS.md`）：@-entity chips 随首条 chat 消息 `mentions` 字段送达。**注册表架构**（前端 `MENTION_REGISTRY` + 服务端解算）已注册 = `asset`（请求族）/ `output`（指认族，钉 id 服务端确定性解出修订目标，LLM 不猜"第二条"）；候选类型先过 MENTIONS §3 闸门。**配方永不是 mention**——卡面预填模板就是全部发射载荷（配方 = 提示词，ADR-040），服务端永不见 `recipe_id`。**MentionEditor 一家多面**：composer + 持久 chat dock（ADR-041 完成转场后下沉）都挂它；per-surface 候选取流经 `MentionContext`（`components/chat/MentionPicker` fork 已退役）。Input 形态 = contentEditable，chip = `contenteditable=false` inline 节点，DOM 拥有文本，`syncNow` = 唯一同步漏斗；失败轮回滚走 imperative handle（`insertText`/`insertMention`，chip 落尾部）。**Chip 三律**：① 可见（inline + ×）② 发送消费 ③ × 净化（无跨送残留）。**配方 = preset，never pin**：预填模板只是初稿，全字段可改；面板手编 = 第三方合并 `merge_prior_slots`，**chat 修订恒胜**（chat = 修计划的唯一通道）；卡面 Remix 开检视 overlay（共享 launcher，不自养 form modal）。DAG 用户形态 = FlowView 只读图（`components/flow/`），无 drag/connect/pan/zoom API（结构，非约定）；缩放/平移按面门禁（配方说明书 = 锁 fit，结果画布 = 开），**编辑只经 chat**（ADR-035 / 036 / 041）。

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (solo or via assistant). Core positioning = **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their personal IP — not a self-serve media tool, not "viral short-video clips".

- **Target & input**: 知识专家带素材的模糊目标。**输入不止"演讲"** —— 会议/报告/播客/纯文字稿+照片/幻灯片都可以。
- **Channels**: LinkedIn, 机构站, 邮件 newsletter。**Multi-output 是能力非承诺**：用户点名什么生成什么，承诺句 = "the user names it, the agent makes it"——打包式「一输入全套出」文案永禁；多语言是入场券（FR/DE/ES/IT/EN 等）。
- **GDPR / EU 驻留** = 卖点但对外文案保持「ready 角度」，合规实装后改写。
- **Dual track 命名**（NAMING N-25）：对内 = **agent**；对外 = **assistant / 助手**，"agent" 永不出现于英文文案（zh 用品类句「你的自媒体Agent团队」=品牌妥协，待 N-25 修订）；角色隐喻（运营官/操盘手/班子）禁（N-24）。
- **Copy doctrine**（→ STRATEGY §5）：plain & factual。禁资产话术（"knowledge assets" 否）/ 膨胀隐喻（"bigger stage" 否）/ 审批机械化（"You review. It publishes" 否）；身份从 expertise 出发，**不称用户 influencer / creator / 网红**；承诺句 = "You focus on your craft; we handle the rest."（与 hero "We do the rest" 同源）；**禁 MCN / 代运营 / 变现话术**（我们是 agent 不是 agency，不做变现承诺）；**CTA / 控件 = 直给动词 + 具体名词**（"上传你的原视频"/"生成"），禁产品黑话与造词（"需求 / Your request"否、"Start making"否的是该文案本身非结构）；写作风格 = 风格/style，"voice" = 音频本义（声纹/dub）；Sparkles icon 禁（"AI 用烂了"），assistant 视觉 = `LogoMark`；studio home hero = 品牌锁up + 品类句（剩定位归 landing）。**配方卡素材需求署名在左 Input 小节**（`recipes.<id>.inputTitle`/`inputHint`），上传区文案通用（`recipes.inspect.dropzone`）。
- **用户到来即彷徨**（论证 → STRATEGY §5，行为规格 → CHAT_ARCH §3.3）：每步都答「下一步是什么」——开始前配方卡接住 / 计划中确认 dock 接住 / 完成后结果画布闭环接住（ADR-041）。agent 顾问姿态四律：① 诊断一轮封顶（只问用户能答的——听众/目的，参数由配方与默认值吸收）② 带理由纠偏（给替代方案，禁静默拒绝）③ 成功定义随任务书 ④ 永给唯一下一步；不做职业/变现咨询（诊断是为了更快给出对方案，不是把生产工具变顾问）。
- **闭环优先于卡片数量**：卡点亮（能力真 + 预览真）≠ 通路；「Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产」全通才算；对外叙事单位 = "完全通路"。
- **闭环叙事与身份命名**（ADR-037 / NAMING N-27）：用户侧闭环 = **管理 IP → 产生 outputs → 发布**，en 用 "personal brand / thought leadership"，zh 用 "IP / 自媒体"；产品内身份模块 = **人设**（Speaker 退役，`speaker` 让位 `speaker_map`，人设多实例扁平：工作号/生活号）。**身份根升格为「定位（Positioning）」已拍板**（ADR-042，目标架构 → `docs/POSITIONING.md`，生产层闭环后动工）——人设收窄为定位的表达分区，渠道/选题/素材挂定位根，品牌/IP 留营销承诺层；落地前代码层只 `persona`。

前端文案 / 工具网格 / 示例占位围绕 **content / LinkedIn / multi-language**，避开 "TikTok / viral / trending"。

## Internationalization (i18n)

### Dictionary Structure
- Source language is English: `apps/web/src/lib/i18n/locales/en.ts` is the source of truth and exports the `Resources` type.
- Chinese `zh.ts` must satisfy `zh: Resources`, so missing keys will be caught at the TypeScript level.
- **Baked-example labels (`recipes.materials.*`) are UI copy, not content**: name them in the SYSTEM language like every other label — en: "Chinese dub", zh: "中文配音". Never use each language's own name ("Doublage français" in en.ts is a bug class, 2026-08-08). (Exception that is NOT UI copy: landing demo-card contents and the `channels.languages` native-name list are marketing content by design.)

### Adding New Copy
1. Add the key / value in `en.ts` first.
2. Mirror it to `zh.ts` in the same structure.
3. In components, use `const { t } = useTranslation()`; do not hard-code strings.

### Interpolation
```ts
t("home.allProjects", { count: projects.length })
```

### SSR
- **SSR renders in the cookie language**: the root route loader reads the `repurposer-lang` cookie server-side, and `I18nProvider` mounts a fresh per-mount i18n instance already in that language (client reads the same cookie) — SSR HTML and the first client render always agree. Per-request instances are mandatory: a shared singleton's language is mutable state that leaks across concurrent SSR requests.
- **Never switch language after hydration** (no "EN first, switch in effect"): lazy route boundaries hydrate after root effects have run, so a post-hydration `changeLanguage` makes their SSR'd text mismatch. Language changes come only from explicit user action (`setLocale`) after mount.

## Theme

### Defaults
- Defaults to following the system `prefers-color-scheme`.
- **Defaults to dark treatment**: on first visit or when the preference is `system`, render in dark mode first to avoid SSR / hydration flicker.
- After the user manually switches, write to `localStorage` with the key `repurposer-theme` (values: `system|light|dark`).

### FOUC Prevention
`__root.tsx` contains a blocking inline script in `head` that reads `localStorage` before the first paint and adds / removes the `dark` class on `document.documentElement`. Do not remove this script.

### Transition Animation
- Uses the View Transition API for a circular expansion reveal effect (clip-path scales from the click position).
- Falls back to direct switching when the browser does not support it or when the user has `prefers-reduced-motion` enabled.
- The default cross-fade is disabled in CSS:
  ```css
  ::view-transition-old(root),
  ::view-transition-new(root) {
    animation: none;
    mix-blend-mode: normal;
  }
  ```

## Routing

### Layout Split (landing vs. studio)
- `/` is the **public landing page** (no sidebar); the sidebar studio lives under the `_app` **pathless layout route** (`src/routes/_app.tsx` holds `SidebarProvider`/`AppSidebar`/`SidebarInset`/`AppHeader`). `__root.tsx` keeps only providers + `Toaster`.
- The studio home is `/home` (`_app.home.tsx`); other app pages keep flat URLs (`_app.projects.tsx` → `/projects`, `_app.projects.$id.tsx` → `/projects/$id`, …).
- `AuthProvider` public paths: `/` only. Everything under `_app` sits behind the login wall automatically.

### Dynamic Links
TanStack Router enforces literal type constraints on `to`. Dynamic parameters must be written as:
```tsx
<Link to="/projects/$id" params={{ id: project.id }} />
```
Do not use template strings:
```tsx
// Incorrect
<Link to={`/projects/${project.id}`} />
```

## SSR Safety

### Do Not Call Browser APIs on the Server
- `window`, `document`, `localStorage`, `matchMedia`, etc. can only appear inside `useEffect`, event handlers, or the anti-FOUC inline script.
- `useState` initial values must be consistent between server and client, otherwise hydration errors will occur.

## Tailwind

### Colors
- Use shadcn theme variables: `bg-background`, `text-foreground`, `text-muted-foreground`, `bg-card`, `border-border`.
- Do not hard-code color values (e.g., `#333`).

### Layout
- Page main content must be placed inside `SidebarInset`; do not override the sidebar structure with your own `min-h-screen w-full`.
- **Pages under `_app` fill the viewport with `flex-1`, never `min-h-svh` / `min-h-screen`**: `SidebarInset` is a `min-h-svh` flex column (there is no global header, ADR-046) and `flex-1` keeps the page glued to it; taller content scrolls the window. **Exception — home is a fixed app-shell surface**: its root is `h-svh` and never scrolls (the dot grid stays viewport-pinned); ONE internal scrollport (`no-scrollbar`) holds everything — the hero stage, the composer (sticky chrome that parks center-stage at rest and docks at the top as the one-line stadium bar), and the gallery. Any future fixed-surface page follows the same shape: root `h-svh` + exactly one internal scrollport. (The landing page `/` is outside `_app` — its `min-h-svh` is legitimate.)

## Sidebar & Navigation

- Sidebar uses `SidebarProvider` + `Sidebar collapsible="icon"`; **PC is a fixed icon rail** — the header toggle renders only on mobile (`md:hidden`), the `Cmd/Ctrl+B` hotkey is guarded to mobile (`isMobile`), and a centered `LogoMark` fills the collapsed header slot. There is NO expand entry on PC; the mobile off-canvas flow is unchanged. (`SidebarProvider defaultOpen={false}`.) **Rail = 一个顶层栈，logo 不是独立组**（2026-08-31 Lovart devtools，用户两连纠）：折叠 PC **无 SidebarHeader**（`group-data-[state=collapsed]:md:hidden`，header 只剩展开态移动端 lockup+toggle）——LogoMark（**28×28 默认档**，用户裁定 2026-08-31——logo 与 36px 菜单项错开一个尺寸档，品牌高于导航）是 `SidebarContent` 栈的**第一个成员**，栈 `group-data-[state=collapsed]:gap-5 pt-4`（logo→菜单组 = 20px，gap-5 是容器间距不是项间距），`SidebarMenu` 恒 `gap-1`（项间 40px 中心距）；cva `group-data-[collapsible=icon]:size-9!`（36×36，18px glyph 居中，active/hover 吃 `bg-sidebar-accent`）；曾 ① 把 20px 误挂项间 ② 留 logo 在独立 header 组用 pt 补丁伪装——Lovart 蓝框把 logo+菜单罩成一组才是正解。
- Navigation items use `SidebarMenuButton` + `render={<Link to="..." />}`, do not use `asChild`.
- **No right border**: add `group-data-[side=left]:border-r-0` on `Sidebar`, background blends with the main area (see UI design guidelines).
- Structural layout:
  - **Header**: PC = centered `LogoMark` (rail is fixed); mobile = logo lockup + toggle. (No "Invite members" entry — do not re-add without an explicit product decision.)
  - **Content**: Flat navigation (no group titles): Home, My projects (`/projects`), Personas (`/personas`). The project grid lives on `/projects`, not on the home page (home is composer-only).
  - **Footer**: user avatar opens the **account console** — a `Popover`, never a `DropdownMenu` (it carries inline controls, ADR-046): identity header (avatar + name + email) → inset **account block — value surfaces ONLY** (plan / credits slot / subscription; MiniMax grouping law: settings never mixes into the account block) → **偏好** rows (labeled rows with TRAILING controls — theme / language as trailing segmented: `bg-inset` track + `bg-card` thumb, icon-only theme pills; the Settings chevron row opens the **shared `SettingsDialog`**, never a page: MiniMax/FLORA modal pattern — left section nav + right content, summonable from anywhere via `useSettingsDialog().openSettings(section)`; sections register in `components/settings/SettingsDialog.tsx`, channels first. `/settings` survives ONLY as the channels OAuth callback shim — it toasts, opens the dialog, bounces home) → 帮助 section (replay tour — sessionStorage flag + `repurposer:replay-tour` event dual delivery, HomeComposer consumes whichever lands first) → logout. A (post-billing) credits status strip may join the rail footer later.
- **No global AppHeader (ADR-046)**: the studio has no persistent top bar — utilities live in the account console (theme / language), and the **notification bell is the single floating chrome chip at the content area's top-right** (rounded-square chip + unread dot; the top-right slot is reserved app-wide — page-level controls never take that corner). Mobile keeps a floating sidebar trigger.
- Navigation / account icons uniformly `h-4.5 w-4.5`; in `sidebarMenuButtonVariants`, expanded `[&_svg]:size-4.5`, collapsed `group-data-[collapsible=icon]:[&_svg]:size-4.5`, keep them consistent.
- **Collapsed state center alignment**: buttons placed in Header / Footer (e.g. the avatar) must be centered; add `group-data-[state=collapsed]:items-center` to the container, and the button itself uses `w-12` square in collapsed state; **do not** put these buttons inside `SidebarMenu` (the list padding will limit the width, causing a 4px offset in collapsed state).
- When adding new sidebar entries, simultaneously update the `nav.*` keys in `zh.ts` / `en.ts`.

## UI Design Guidelines

Overall style: restrained, lightweight, unified. Key reference points:

- **Scope**: these rules govern the **studio** (`_app` routes + shared components). The landing page (`/` + `components/landing/`) is a marketing surface with its own visual language — its `rounded-full` / `border-border` / `font-medium` usages are template-native, not violations (2026-08-20 ruling).
- **Border radius**: global small radius (`rounded-md` / `rounded-lg`), avoid `rounded-full` (except for circular icon buttons, red dots, and the home composer's docked one-line stadium bar).
- **Border & shadow**: cards take the base primitive's `ring-foreground/10` hairline + a soft `shadow-*` — **visible strokes** (`border-border` / `ring-border` / stronger `ring-foreground/*`) on cards are prohibited; avoid drawing dividers between sections whenever possible.
- **Sidebar blending into main area**: `--sidebar` color equals `--background` (both themes aligned in `styles.css`), and no right border, allowing the sidebar and content area to blend seamlessly.
- **Dot grid = workshop texture, two making surfaces only**: the home page (`dot-grid` utility on the route root — the root is `h-svh` and never scrolls, so the grid stays pinned to the viewport while the gallery scrolls inside) and the results canvas (FlowView's `dots` prop) — one recipe (muted-foreground 20% light / 18% dark, 1px dot, 26px gap). A dotted third surface is a violation (ADR-046 附).
- **Colors**: only use shadcn theme variables (`bg-background` / `text-foreground` / `text-muted-foreground` / `bg-card` / `ring-border`, etc.), no hard-coded color values.
- **Font weight**: body text and controls stay at regular weight; pill / secondary button text is not bold.
- **Data vs. copy**: all UI copy goes through i18n; user data (persona names, project titles, etc.) is displayed as-is — do not treat Chinese text as "not yet internationalized" just because it's Chinese — but **defaults must not fall back to a specific data entry** (e.g., the Persona default should show a localized placeholder, letting the user actively select).

## Persona Skin Block (brand)

**ADR-038**：独立 Brand Template 模块退役——`brand_templates` 表与端点已删，皮肤 = 人设 `brand` JSONB 块（caption 字号/字体/颜色/位置 + style-preset + 标题 + intro/outro + 音乐 `musicId`/`musicMood`/`musicEnabled`）；`/brand-template` 307 → `/personas`，sidebar 单「人设」。**`brand: null` = 系统默认皮肤**。编辑 = 人设页第三 tab「皮肤」（左设置 + 右 Remotion `<Player>` 实时预览，与产物像素级一致，`components/persona/skin-editor.tsx`）；存 = PUT 只更 `brand` 块，「恢复默认」写 `null`。片头尾媒体 = `POST /personas/{id}/media(/upload-url)`（随人设删）。**`logo` 键无渲染消费路径，不入 UI**。**Craft/format 字段非人设列**：`aspect` / `fillMode` / `captionEnabled` / filler removal / 音乐默认 = 配方注册表 + 任务书默认（config 三分流，N-28）；写作风格不在人设表列，住 风格六件 + `guidelines`。烘焙路径见 `MODULE_ARCHITECTURE.md §7` / `brand.py`（`brand_ref` = persona id，clip-spec 契约不变）。**`brand_template_id` 不出现在任何请求载荷**——composer 单身份控件，`persona_id` 经首条 chat 消息送达并在 `create_run` 钉入 `run.context.persona_id`。

## Persona Voice Block (voice)

音频绑定 = 人设 `voice` JSONB：`{kind:"cloned",voice_id,sample_asset_id}` | `{kind:"stock",stock_id}` | `null` = Auto（dub 用项目自身素材声音）。**`voice` 词独占音频本义**（NAMING N-27/N-28），文风在风格六件 + `guidelines`。编辑 = 人设页 Voice 卡（`components/persona/voice-section.tsx`）展示当前绑定 + 上传/换样本（样本 = persona 素材 `type=voice_sample`），存 = PUT 只更 `voice` 块；文案只陈述绑定状态、不许诺效果。STOCK_VOICES 注册表 / 系统音色试听 / dub 链优先级改造 = 缓做项。

## Video Editor & Rendering (Vertical Shorts)

**clip-spec 是唯一契约**（JSON 字段级 + 轨道模型 ADR-044），**renderer = 可替换黑盒**（首推 Remotion）。详见 `docs/RENDERING.md`（§3 字段契约 / §6 渲染层 / §7 替换路径 / §8 现行轨道契约）与 `docs/VIDEO_EDITOR.md`（编辑器形态 + L2/L3 范围纪律）。**泄漏禁令**：Remotion / React 概念永不入 clip-spec。

**L3 铁律（每项否决不变）**：禁多轨时间线 / 层合成 / 转场效果 / B-roll 库 / 自动人脸重取景 / 客户端引擎——专业需求明确导出剪映 / Premiere。字幕样式仅枚举，不开放自由版式；styles 限定 CSS + libass 都能表达的子集（保 FFmpeg 替身成本）。硬前提：**多语言 ASR 词级时间戳 + 对象存储流式 / 寻址**（ADR-024）。

## Error Handling & Toasts

所有 API 走 `apps/web/src/lib/api.ts:apiFetch`：默认非 OK + 网络失败 → 全局 sonner 带 `detail`；401 清登录态开 LoginDialog（非抑制 toast）；成功静默。`toast: false` / `toast: "..."` / `toast: {success, error}` 三档 per-call 控制。`<Toaster />` 挂在 `__root.tsx`（项目自建 `ThemeProvider`，非 next-themes）。**Auth 失败也走 toast，无双轨**（判词 2026-08-24：LoginDialog 不再 `{toast:false}` 抑制或自养 `error`，发验证码冷却/验证码错/网络失败同进全局 toast——form 内清空/复位焦点属输入复位非错误显示）。动作反馈禁内联 `<p>`；页面级 load-failure 占位可内联但 `toast: false` 防双报。错误形态 / 状态码约定 = `docs/API.md §4`。

## Task Queue (Backend)

重活（ASR / 渲染 / 生成）一律入 Postgres 队列（`FOR UPDATE SKIP LOCKED`），由独立 `python -m app.worker` 认领；**禁 FastAPI BackgroundTasks**、禁跨模块直调 service 执行重活。新增 processor → `app/pipeline/asset_processing.py:PROCESSORS`；新增认领源 → worker claim loop。详见 `MODULE_ARCHITECTURE.md §5 规则 1 / §7.2`（ADR-017 + ADR-039 队列与重试机制）。

## Commit Messages
- Use conventional commits, for example:
  - `feat: add theme toggle with view transition`
  - `fix: correct SidebarMenuButton render usage`
  - `docs: update i18n and theme conventions`

## Database Reset

`apps/api/scripts/reset_db.py [--yes] [--db-only|--storage-only]` 清部署：dry-run 默认（印目标），`--yes` 落地。**保留前缀**：`demo/`（landing + 配方卡营销资产，内容寻址；生产永不再生）+ `music/`（平台默认曲目；`scripts/seed_default_music.py` reconcile 零配额复种）。**生产慎跑**——dry-run banner 先看。完成后重启即 auto-migrate + 默认音乐 reconcile；人设 `brand: null` 走系统默认皮，不布品牌种子；栈不布 demo 项目，`SKIP_DEMO_SEED` 是死旗，不依赖。

## Testing

The API test suite was removed because it had drifted from the rapidly changing implementation (stale columns, changed storage paths, outdated mocks). Verify changes by running the relevant flow end-to-end instead of relying on a test suite.
