# Repurposer — Claude Collaboration Guidelines

> This document records the frontend conventions and common pitfalls of the Repurposer project, to be followed by AI collaborators.

## Key Docs

Read these before touching a subsystem (check each doc's own status line — some describe proposed work not yet landed on `main`):

- `docs/README.md` — **docs 索引与治理原则（单一事实源表）**，找文档先查这里。
- `docs/PROGRESS.md` — 进展快照 + 排期 + 需求池的**唯一事实源**；排期/优先级只准引用它。
- `docs/MODULE_ARCHITECTURE.md` — 六层模块图 + **表归属契约**（每张表只有一个 owner 模块）+ 跨模块通信规则 + §7 代码地图/队列机制/数据约定（现状架构唯一事实源）；新表/新模块/新认领源必须在此登记。
- `docs/POSITIONING.md` — **定位根概念架构（运营层母文档，ADR-042，已拍板未实施）**：身份根 = 定位（positioning），人设收窄为表达分区，渠道/选题/素材挂根；施工排期 = PROGRESS 第六~八周。动身份模块/渠道/选题/home 前先读它。
- `docs/AGENT_ARCHITECTURE.md` — 四层工程地图（Model / Harness / Graph / Loop，ADR-039）：技能包 `app/skills/`（能力唯一家）+ agent 花名册 `app/agents/`（一个 Agent 类 + 声明实例）+ `NodeBase` 图内核（报价=fold / 执行=topo / 校验=∀ / 对账=⊆）+ chat 治理环。agent 架构唯一事实源；outputs 可扩展（产物 = 技能的属性，注册表派生）。
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

## Component Usage Guidelines

### Border Radius & Buttons
- **Uniform small radius**: buttons, inputs, cards, pills, and dropdown triggers all use the default `rounded-md` (cards / panels may use `rounded-lg`).
- **`rounded-full` is prohibited**, with only the following two exceptions:
  1. True circular icon buttons (e.g., the send arrow in the bottom-right corner of an input: `h-9 w-9 rounded-full`).
  2. Status badges / red dots (notification corner markers).
- The shadcn `Badge` component's base style is `rounded-full` — always override with `className="rounded-md"` when using it for metadata tags (durations, aspect ratios, labels).
- Controls in the same row must align in height: action-area controls are uniformly `h-9`, matching the send button height.
- Pill / dropdown trigger **text must not be bold** (do not add `font-medium`), keep it lightweight.

### Overlay Components (DropdownMenu / Popover / Select)
- **List-style single-select** (select and close on click): use `DropdownMenu` + `DropdownMenuItem`.
- **Content panels with inline actions** (buttons/links/rows that must not close on click — e.g. the notification panel): use `Popover`, never `DropdownMenu` (precedent: `NotificationBell`).
- **Multi-control settings panel** (needs to stay open while adjusting multiple values): use `Popover`, with segmented button groups inside.
- Triggers are always `render={<Button variant="outline" size="sm" className="h-9 …" />}`, with "icon + label + `ChevronDown`" inside the button.
- To express "currently selected" for an option, use the `Check` icon; for bottom overlays (dropdowns in the footer), remember `side="top"` to pop upward.
- Pure dropdowns in forms use `Select`; parameter selection in the prompt action bar uses the pill pattern above — do not mix styles.

### Card Depth: hairline + soft shadow — no visible strokes
- **The base `Card` primitive ships a `ring-foreground/10` hairline** (dark: white 10%, reads as a glass edge), and product cards add a soft ambient shadow on top (light) — this combination IS the card look (ElevenLabs light reference):
  ```tsx
  <Card className="shadow-lg">
  ```
- **Dark casts no shadows at all** — night has no light source: every `shadow-*` utility compiles to transparent under `.dark` via one switch (`--tw-shadow-color: transparent` in `styles.css`; focus rings survive — they compose via `--tw-ring-shadow`, not the shadow color). Dark elevation = tonal steps + the hairline + glass translucency.
- **Prohibited: visible strokes** — `border` + `border-border`, `ring-1 ring-border`, and `ring-foreground/*` stronger than the /10 hairline. The /10 hairline + a soft ambient shadow MAY coexist (that is the default card); a *visible* stroke must NOT also carry a shadow — pick exactly one. (`border-dashed` dropzones and `border-transparent` variant bases are fine; focus rings are interactivity, not edges.)
- Separation between sections comes from spacing and token steps (`bg-muted` / `bg-inset` fills), never from drawn dividers.
- **Fill first — the hairline is the fallback, not the default**: if a surface's fill already distinguishes it from what sits behind it (a `bg-muted` chip on a `bg-card` panel, media content on the page), it takes NO ring/border at all. The `ring-foreground/10` hairline exists only for same-fill boundaries where the edge would otherwise disappear — a white card on the white page, the frosted modal over its backdrop wash (the sign-in dialog). When a same-fill element needs separation, prefer STEPPING ITS FILL to a token step over drawing a stroke.
- **Hero surfaces are fully flat**: the home composer card carries only the base primitive's `ring-foreground/10` hairline — NO shadow — and its entity blocks (Assets / Persona) are fill-separated chips (`bg-subtle` — the faintest ladder rung, NO ring; solid-fill hovers since they straddle the card edge — light steps one rung down to `bg-muted`, dark takes the solid color-mix lift). **No `backdrop-filter` on the composer card**: it would make the card the containing block for the fixed `MentionPicker` inside the editor (teleporting it), and the home page behind is a uniform fill with nothing to blur. Media tiles (recipe gallery) are fully chromeless: no ring, no shadow — the media content is its own separation.
- **Gray ladder**: surface hierarchy comes from the stepped tokens, never from one-off alpha fills. **Light**: `--background` is **pure white** (1.0) — cards float via the base Card's built-in `ring-foreground/10` hairline + soft shadow, not a gray underlay; `--subtle` 0.975 (the faintest whisper off white — e.g. the composer entity blocks) → `--muted` 0.95 → `--inset` 0.92. **Dark**: `--background` is **near-black** (0.12) and elevation speaks **glass, not ladder** — floating layers are translucent (see `overlay-surface`), `--card`/`--popover` 0.21, `--muted` 0.24 (`--subtle` collapses onto it), and **`--inset` is INVERTED: 0.15, darker than the panel** (kbd chips / seed values / search inputs sit in darker wells). **`bg-muted/50`, `bg-background/60`, `bg-muted/30` and similar ad-hoc alphas are prohibited** — an inner block uses solid `bg-muted`, a nested block on a muted card inverts to `bg-card`.
- **Hover / highlight = `--accent`, one token both themes**: light = solid 0.95 gray step; **dark = `oklch(1 0 0 / 8%)`, a translucent white veil** (never a lighter solid step). Menu rows, list hovers, picker selected states, ghost-button hovers all consume `bg-accent` (or `/50` for the weak tier), so one variable retunes every hover in the app. Never hardcode hover COLOR VALUES per instance (`dark:hover:bg-[oklch(…)]` banned) — but **variant pairing is still mandatory**: `dark:bg-*` beats a bare `hover:bg-*` in the cascade, so an element carrying `dark:bg-x` must also carry `dark:hover:bg-accent` explicitly.
- **Text is three tiers, not two**: `foreground` (0.145 / dark 0.95) → `muted-foreground` subtitles (0.556 / dark 0.63) → **`meta-foreground`** (0.68 / dark 0.52) for small ALL-CAPS tracked meta labels (the "MODEL / SEED" style), composed via the `text-meta` utility (`uppercase` + `tracking-[0.08em]` + the token color).

### Floating Layers: frosted glass via `overlay-surface`
- **All floating layers** (Popover / DropdownMenu / Dialog / Select / Sheet / Tour) use the shared `overlay-surface` utility defined in `styles.css` — translucent `--popover` + `backdrop-blur` + `saturate(1.4)`, **per-theme recipe**: light = **92% + blur(24px)** (lower opacity lets dark content behind bleed through and tint the panel); dark = **68% + blur(28px)** (over the near-black canvas a high-opacity fill reads as a solid box and the blur has nothing to show). Solid fallback under `@supports not (backdrop-filter)`. Do **not** re-add `bg-popover` to overlay components, and **per-instance frost patches (e.g. `dark:bg-white/10`) are banned** — tune the shared recipe; if a specific instance genuinely needs different opacity, override via its `className` (components merge it last, keeping it the open extension point).
- Dialog / Sheet backdrops are **per-theme**: light = `bg-background/60` (a white wash — a black scrim over the white page reads as gray murk) + `backdrop-blur-[2px]`; dark = `bg-black/30` + `backdrop-blur-[2px]` — the frosted surface reads against a dimmed but clearly visible page in both themes.
- **Overlay chrome = the Dialog primitive, never hand-rolled** (`fixed` backdrop + glass div). A hand-rolled backdrop wrapping the panel kills the glass: an ancestor carrying `backdrop-filter` becomes a Backdrop Root, and a descendant panel's `overlay-surface` blur then samples only that subtree (nothing to blur) — silently degenerating to a flat tint. The primitive portals overlay and content side by side, which is the only correct structure.
- **`DialogContent` centers via `-translate-1/2`** — a transformed popup becomes the containing block for `fixed` descendants, teleporting viewport-anchored floaters. Viewport-anchored floaters therefore portal to `document.body` (the `MentionPicker` does), which is immune to ancestor transforms and backdrop-filters; a popup that must host a NON-portaled fixed floater composes `DialogPortal` + `DialogOverlay` + `DialogPrimitive.Popup` by hand and centers with `inset-0 m-auto` (no transform). **A hand-composed popup must mirror `DialogContent` chrome exactly** — `overlay-surface` + `ring-1 ring-foreground/10` hairline + `shadow-xl` + `rounded-xl`; without the hairline the light-theme glass dissolves into the white backdrop wash (RecipeInspectOverlay lost it once, 2026-08-10). (Precedent: `RecipeInspectOverlay`.)
- Tooltips and sonner toasts are intentionally excluded (small transient labels stay solid).
- **Scroll fades** (`scroll-fade-y` / `scroll-fade-x` in `styles.css`): mask utilities that dissolve a scrollport's edge before content reaches floating chrome (precedent: the overlay chat viewport). Apply **per surface**, each fade zone paired with that surface's own content padding — **never inside shared primitives**: an unused class sitting in a primitive comes alive the moment a same-named `@utility` is defined.

### Composer / Input Card
- **质感配方（Lovart composer 参照）**：大圆角（`rounded-2xl`）+ 内部空气（`p-5`、输入区 `h-24`）+ **耳语级中控区**——底排控件（AI model pill）一律 `variant="ghost"` 纯文字+小图标，只有 send 一个深色实心锚点。**填充灰（`bg-muted`/`bg-inset`）只给内容容器（inset 块、信息 pill、badge），永远不给操作按钮**——参考图中底排只有 credits 一个信息 pill 有填充，按钮全裸。
- Structure: **entity blocks ride the card's top edge** (negative `-mt-*` margin, `overflow-visible` on the Card — they are NOT inside the card): `Assets` block (opens `AssetsModal`) + `Persona` block (opens `PersonaPickerModal`), both `h-24 w-20`. Block anatomy (Opus-style): **icon at the top-left → spacer → title → value as the bottom-most line** (Assets: Plus / first-file type icon, value = "Optional" / "{{count}} files"; Persona: `User` icon / avatar, value = "Auto" / persona name). The `MentionEditor` fills the remaining width to their right. Block hover: light = `bg-accent` gray step; dark = a **solid** color-mix lift (`dark:hover:bg-[color-mix(in_oklch,var(--muted),var(--foreground)_5%)]`, the button-secondary recipe) — the blocks STRADDLE the card's top edge, so a translucent veil hover would reveal the page/card seam behind them. In dark the blocks lift one tonal step off the card (`dark:bg-muted` on the card's 0.21; dark casts no shadows, so the card's edge is the `ring-foreground/10` hairline). **Rule: the white-veil hover (`bg-accent` dark) is only for uniform substrates (menu rows, list rows, pickers); any element straddling a surface boundary must hover with a solid fill.**
- Both blocks are **summaries that open modals** — content management lives in the modal, never in the block: `AssetsModal` = upload zone + file grid + remove (video/audio/images/slides/transcripts); `PersonaPickerModal` = Auto row + persona cards with style tags / voice-clone status, single-select-and-close. **Modals are pickers/managers, not editors** — persona editing lives on `/personas`.
- Bottom row is **one continuous row inside the card** (no separate action-bar strip / muted background): AI model pill + circular send button on the right, controls at `h-9`. The composer has **no language / outputs / clip-count controls and runs no inference of its own** (see behavioral contract). The **AI model pill is display-only** (single provider): a `Popover openOnHover` info card (文案/配音/图像音乐 → provider 分解), never a picker — a picker lands only when a real second provider exists, and its user-facing form is a **policy switch** (e.g. "prefer EU-hosted models"), not a model SKU shelf (裁定见 PROGRESS 需求池 "LLM provider 抽象").
- Card padding is controlled by `CardContent` (`Card` adds `py-0` to remove built-in vertical padding, avoiding double padding).
- Do not add a divider / border in the middle of the card to separate the input area from the action bar; keep it as one piece.
- **Teaching lives in the Tour, not the placeholder**: the textarea placeholder stays a single short prompt — no usage instructions in it. First-visit teaching is the 4-step `Tour` (assets → persona → prompt (send folded in) → recipe gallery, anchored via `data-tour="composer-*"` / `data-tour="home-recipes"` attributes). The seen flag's version is **a pure function of content** (`lib/tour.ts`: djb2 hash of the step config + the EN copy subtree — EN is the locale source of truth, so every copy edit touches it and a language switch never replays): `localStorage["repurposer-tour-seen"]` stores the hash, the tour auto-opens when the stored hash differs, and complete/skip both write the current hash. **Any content change — steps or copy — replays the tour exactly once per user; no manual version constants, no "worth re-showing" judgment** (read/write inside `useEffect` only — never during SSR). New first-visit tours follow the same pattern: own storage key, a static `TourStepDef[]` config hashed with its EN copy subtree, `data-tour` anchors, effect-only reads.
- **Results page has its own tour** (score badge → video area → "···" menu, anchored via `data-tour="results-*"` on the first ready output node of the results canvas, ADR-041): separate key `localStorage["repurposer-results-tour-seen"]` with the same content-hash rule, fires once outputs land on the canvas after the completion transition — no matter how the user arrived (fresh generation or from `/projects`).

#### Composer behavioral contract（意图层单面化：chat 唯一入口）
- **Prompt is required**: submitting with an empty prompt is blocked locally (toast), same posture as the auth gate. Files are optional — a prompt-only send creates **no** asset: the PlanAgent judges whether a message IS the user's own content (pasted transcript/draft, with or without "this is my…" framing) and promotes it to a real transcript asset (`create_transcript_asset_from_text`); a generate request with no assets and no pasted content gets an ask-for-material answer, never a groundless task book. Never reintroduce length-based heuristics — content-vs-request is LLM-judged only. Mid-conversation uploads go through the overlay chat's attach button — picked files **stage as lifecycle chips inside the input group** (uploading → done/error, × removes and deletes the asset; direct-to-storage, same flow as the composer) and only the **send button** consumes them, riding the turn as message `attachments` (persisted, re-rendered on refresh). Picking a file never sends anything by itself; an attachment-only send is legal — the plan path infers from an honest stand-in line, and a blank message never auto-answers a docked checkpoint.
- **The composer does NO intent recognition**（简报 `docs/tasks/intent-surface-unification.md`）: send = spinner (create empty project + upload assets) → navigate to `/projects/$id?overlay=chat` with the draft handed over via router state → the overlay chat sends it as the first `POST /chat` message (mentions + `persona_id` ride along). `POST /chat` is the **only intent surface**: the plan path builds / refines / confirms the task book (PlanAgent); projects with runs go to the four-state ChatIntentAgent. Never reintroduce a second intent entry (e.g. a dedicated `/intent` endpoint).
- **clips need media**: enforced server-side — the PlanAgent excludes clips for text-only input; `create_run` mirrors with 422 at the birthplace.
- **Show grid ≠ tool grid**: the capability icon row below the composer is display-only — it must not switch outputs or touch composer params.
- **Mentions = the composer's fourth payload field**（方针 `docs/MENTIONS.md`）: @-entity chips ride `mentions` alongside the first chat message. The mention system is a **registry architecture** (frontend `MENTION_REGISTRY` + server-side resolution), the registered types are `asset` (request family) and `output` (reference family — the pinned id resolves the revision target server-side); new @ types are registry entries, never one-off branches — and a candidate type must first pass the MENTIONS §3 gate (a recipe is NOT a mention: it is just a prompt — the card's prefilled template IS the entire launch payload, 配方 = 提示词). Input = `MentionEditor` (contentEditable; chips are inline `contenteditable=false` nodes, the DOM owns the text, `syncNow` is the single sync funnel) — **one editor family serves every text surface**: the composer AND the persistent chat dock (the generation overlay's bottom row — it becomes the bottom dock when the run completes, ADR-041) all mount it, with per-surface candidate feeds riding `MentionContext`; a separate textarea / hand-rolled picker per surface is banned (the `components/chat/MentionPicker` fork is retired). Failed-turn rollback restores the DOM-owned draft imperatively (`insertText` / `insertMention` — chips re-land at the end, positions aren't kept). Chip three laws: **visible** (inline chip with ×), **consumed on send**, **× purifies** (no state lingers across sends). There is no server-side recipe seeding — the server never sees the card's identity, and the composer never builds `prior`. A recipe is a **preset, never a pin**: the prefilled template is only the first draft and every field stays refine-able; panel hand-edits (explicit slots) are three-way merged against the stored book and the fresh inference (`merge_prior_slots`) with **chat revisions always winning** — chat IS how the plan is edited, nothing is locked. Recipe cards' Remix opens the inspect overlay (the card click launches via the shared launcher, never a self-contained form modal). 卡面点开 = **配方检视 overlay = 检视 tabs + 发射区**（2026-08-08 D6 二次修订，RECIPES §7.1–7.2 + ADR-036）：右区 tabs（示例 = 输出/输入平铺卡 / 流程 = 唯一图画布：素材→策展步骤→烘焙成片一张图，图只画一次），左区 = **composer 发送机构的挂载**（`useProjectLaunch` 共享 hook——同一发射台的第二个停放位：上传暂存 + 常显可编辑预填 prompt + 发送，发送即建项目跳 chat 首发，路径与 composer 完全相同）。**入口分工**：composer = 通用/复杂/自定义组合式需求，配方卡 = 预设快捷需求。overlay 零推断 / 零 prior / **零生成**（禁 modal 直接跑 run = A 形态否决不变）；预设参数永不做选择器控件——预设可见 = 预填 prompt 文案本身（模板点名产出与语言），修改唯一入口 = 预填文本 / chat（chat 恒胜）。The **operable** DAG canvas is never user-facing; the DAG's user-facing forms are **read-only graphs with real nodes and edges**, all rendered by the shared `FlowView` substrate (`components/flow/`) — the recipe fan-out/flow strip and the **results canvas** (桌面默认中心：进度不进图、打勾收官后画布按编译序诞生回放、底部 dock 精修；转正复核 = 小白复述测试，ADR-041). FlowView ships **no drag/connect APIs** (read-only topology is structural, not a convention); pan/zoom are navigation gated per surface (recipe manual = locked fit, results canvas = open), and editing happens **only through chat** (ADR-035 / ADR-036 / ADR-041).

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (operating solo or via an assistant). Its core positioning is **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their own IP — not a self-serve media tool, not "viral short-video clips".

- **Target users**: knowledge experts with content. **Never assume the input is a "speech"**: it can be a meeting, a report, a podcast, or just a transcript plus photos/slides.
- **Core channels**: LinkedIn, institutional websites, email newsletters.
- **Core outputs**: whatever the user names — LinkedIn posts, quote cards, articles, newsletters, multi-language versions, vertical clips. **Multi-output is a capability surface, not the promise**: the promise is "the user names it, the agent makes it" — bundle-style "one input, a full set out" advertising is banned; enumerating capabilities is fine.
- **Multi-language is the entry ticket**: outputs must cover mainstream European languages (FR / DE / ES / IT / EN, etc.).
- **GDPR / EU data residency**: a core selling point; outward compliance copy stays in the "ready" angle until compliance actually ships.
- **Self-label dual track** (NAMING N-25): internal/technical = **agent**; user-facing copy = **assistant / 助手** ("agent" never appears in outward text; zh prefers the pronoun 它). Role-metaphors (运营官 / 操盘手 / 班子) are banned (N-24).
- **Copy doctrine**: plain and factual — no asset jargon ("knowledge assets" rejected), no inflated metaphors ("bigger stage" rejected), no approval-mechanics ("You review. It publishes" rejected). Studio home = hello + spec note only; positioning lives on the landing page. Writing style = 风格/style; "voice" is audio-only (声纹/dub). The Sparkles icon is banned ("AI 用烂了"); the assistant's visual is `LogoMark`. **身份框架必须体面**：目标用户顾虑"当网红"俗气/浪费时间——文案永远从 expertise 出发（expertise → personal brand / thought leadership），**不称用户为 influencer / creator / 网红**；核心承诺句 = "You focus on your craft; we handle the rest."（与 hero "We do the rest" 同源）。**禁 MCN / 代运营 / 变现话术**（"we manage your channels" / "monetize your audience"）——我们是 agent 不是 agency，不做变现承诺。**CTA / 控件文案 = 直给动词 + 具体名词**（"上传你的原视频"、"生成"），禁产品黑话与造词（"需求 / Your request"、"Needs a video" 均被否；"Start making" 否的是该文案本身，不是"动词+具体名词"结构——更具体的按钮文案允许）——用户全是小白，参照成熟竞品的大白话；配方卡的素材需求署名在左区 Input 小节（`recipes.<id>.inputTitle` / `inputHint`），上传区文案本身通用（`recipes.inspect.dropzone`）。
- **用户到来即彷徨**（论证 → STRATEGY §5，行为规格 → CHAT_ARCH §3.3）：目标用户带着素材和模糊目标而来——不知道做什么、怎么做、做完之后呢。产品的每一步都必须回答"现在该做什么、为什么、下一步是什么"：开始前由配方卡接住，计划中由确认 dock 接住，**完成后由结果画布闭环接住**（ADR-041，PROGRESS 第二周闭环链）。agent 顾问姿态四律：诊断一轮封顶（只问用户能答的——听众/目的；用户不懂的参数由配方与默认值吸收）、带理由纠偏（给替代方案，禁静默拒绝）、成功定义随任务书、永给唯一下一步；不做职业/变现咨询——诊断是为了更快给出对的方案，不是把生产工具变成顾问。
- **闭环优先于卡片数量**：卡点亮（能力真 + 预览真）≠ 通路；「Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产」全通才算通路。对外汇报的叙事单位是"完全通路"，不是"点亮了几张卡"。
- **闭环叙事与身份命名**（ADR-037 / NAMING N-27）：用户侧闭环 = **管理 IP → 产生 outputs → 发布**。对外叙事可讲"打造你的 IP / 自媒体"（zh），但 **"IP" 禁入英文文案**（英语语境 IP = intellectual property）——en 叙事用 **personal brand / thought leadership**。产品内身份模块 = **人设（Persona）**：Speaker 退役、`speaker` 让位素材里说话的人（`speaker_map`）；人设多实例扁平（工作号/生活号）。**身份根升格为「定位（Positioning）」已拍板（ADR-042，目标架构见 `docs/POSITIONING.md`，生产层闭环后动工）**：人设收窄为定位的表达分区，渠道/选题/素材挂定位根，品牌/IP 留在营销承诺层；落地前代码层仍只有 `persona`。

Therefore, frontend copy, tool grids, and example placeholders should all revolve around **content / LinkedIn / multi-language**, avoiding descriptions like "TikTok / viral / trending".

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
- **Pages under `_app` fill the viewport with `flex-1`, never `min-h-svh` / `min-h-screen`**: `SidebarInset` is a flex column whose first child is the sticky `AppHeader` (~60px). A page root with `min-h-svh` sits *below* the header, so the document is always 100svh + header tall — a permanent window scrollbar that scrolls exactly the header's height even when content fits. `flex-1` fills viewport-minus-header exactly. (The landing page `/` is outside `_app` — no sticky header there, its `min-h-svh` is legitimate.)

## Sidebar & Navigation

- Sidebar uses `SidebarProvider` + `Sidebar collapsible="icon"`; **PC is a fixed icon rail** — the header toggle renders only on mobile (`md:hidden`), the `Cmd/Ctrl+B` hotkey is guarded to mobile (`isMobile`), and a centered `LogoMark` fills the collapsed header slot. There is NO expand entry on PC; the mobile off-canvas flow is unchanged. (`SidebarProvider defaultOpen={false}`.)
- Navigation items use `SidebarMenuButton` + `render={<Link to="..." />}`, do not use `asChild`.
- **No right border**: add `group-data-[side=left]:border-r-0` on `Sidebar`, background blends with the main area (see UI design guidelines).
- Structural layout:
  - **Header**: PC = centered `LogoMark` (rail is fixed); mobile = logo lockup + toggle. (No "Invite members" entry — do not re-add without an explicit product decision.)
  - **Content**: Flat navigation (no group titles): Home, My projects (`/projects`), Personas (`/personas`). The project grid lives on `/projects`, not on the home page (home is composer-only).
  - **Footer**: User avatar dropdown (`DropdownMenu`, `side="top"` popping upward, containing Profile / Settings / Logout) at the top, followed by account items (Subscription / Learning / Help).
- Navigation / account icons uniformly `h-4.5 w-4.5`; in `sidebarMenuButtonVariants`, expanded `[&_svg]:size-4.5`, collapsed `group-data-[collapsible=icon]:[&_svg]:size-4.5`, keep them consistent.
- **Collapsed state center alignment**: buttons placed in Header / Footer (e.g. the avatar) must be centered; add `group-data-[state=collapsed]:items-center` to the container, and the button itself uses `w-12` square in collapsed state; **do not** put these buttons inside `SidebarMenu` (the list padding will limit the width, causing a 4px offset in collapsed state).
- When adding new sidebar entries, simultaneously update the `nav.*` keys in `zh.ts` / `en.ts`.

## UI Design Guidelines

Overall style: restrained, lightweight, unified. Key reference points:

- **Border radius**: global small radius (`rounded-md` / `rounded-lg`), avoid `rounded-full` (except for circular icon buttons and red dots).
- **Border & shadow**: cards take the base primitive's `ring-foreground/10` hairline + a soft `shadow-*` — **visible strokes** (`border-border` / `ring-border` / stronger `ring-foreground/*`) on cards are prohibited; avoid drawing dividers between sections whenever possible.
- **Sidebar blending into main area**: `--sidebar` color equals `--background` (both themes aligned in `styles.css`), and no right border, allowing the sidebar and content area to blend seamlessly.
- **Colors**: only use shadcn theme variables (`bg-background` / `text-foreground` / `text-muted-foreground` / `bg-card` / `ring-border`, etc.), no hard-coded color values.
- **Font weight**: body text and controls stay at regular weight; pill / secondary button text is not bold.
- **Data vs. copy**: all UI copy goes through i18n; user data (persona names, project titles, etc.) is displayed as-is — do not treat Chinese text as "not yet internationalized" just because it's Chinese — but **defaults must not fall back to a specific data entry** (e.g., the Persona default should show a localized placeholder, letting the user actively select).

## Persona Skin Block (brand)

> **ADR-038 已落地**：独立 Brand Template 模块退役——`brand_templates` 表与端点已删，皮肤 = 人设的 `brand` JSONB 块（全栈一词：人设块 / 烘焙 / clip-spec 段同名）；`/brand-template` 307 重定向 `/personas`，sidebar 单「人设」项。

- The visual skin is the persona's `brand` JSONB block: caption font/size/color/position/style-preset + title + intro/outro + music (`musicId` / `musicMood` fallback, `musicEnabled` master switch). `brand: null` = system default skin.
- **编辑面 = 人设页第三 tab「皮肤」**（`components/persona/skin-editor.tsx`）：左设置右 Remotion `<Player>` 实时预览（与产物像素级一致，clip 编辑页同款先例）+ 拖拽 marker 改位置/字号；保存 = PUT 只更 `brand` 块，「恢复默认」写 `null`。片头尾媒体走 `POST /personas/{id}/media(/upload-url)`（存 persona 上传目录，随人设删除）。`logo` 键无渲染消费路径，不进 UI。
- **Craft/format keys are NOT persona fields**: `aspect` / `fillMode` / `captionEnabled` / filler removal / music defaults come from the recipe registry / task-book defaults (config 三分流, N-28). Writing style ("voice" as prose style) is not a column either — it lives in the style six + `guidelines`.
- At clip-generation time the Pipeline resolves the persona (run-context pin → project mount → `auto_created_at` → earliest created), merges `persona.brand` over `DEFAULT_BRAND_CONFIG` in `app/memory/brand.py` (module name unchanged), and bakes into `render_spec.brand` with `brand_ref` = persona id. **clip-spec's brand segment contract is untouched** (renderer black box, ADR-016).
- The composer has a single identity control (the Persona block); `persona_id` rides the first chat message, pins into `run.context.persona_id` at `create_run`. There is no `brand_template_id` anywhere in request payloads.

## Persona Voice Block (voice)

- The audio binding is the persona's `voice` JSONB block: `{"kind":"cloned","voice_id","sample_asset_id"}` | `{"kind":"stock","stock_id"}` | `null` = Auto（dub 用每个项目自己的素材声音）。`voice` 词独占音频本义（NAMING N-27/N-28）；文风在风格六件 + `guidelines`。
- 编辑面 = 人设页人设 tab 内的 Voice 卡（`components/persona/voice-section.tsx`）：壳形态 = 展示当前绑定 + 上传/换绑声音样本（样本 = persona 素材 `type=voice_sample`），保存 = PUT 只更 `voice` 块；文案只陈述绑定状态、不许诺效果。STOCK_VOICES 注册表 / 系统音色试听 / dub 链读 `persona.voice` 的优先级改造属缓做项（PROGRESS 第二周拍板二）。

## Video Editor & Rendering (Vertical Shorts)

> Render-chain architecture + field-level clip-spec contract in `docs/RENDERING.md`; editor interaction & scope discipline in `docs/VIDEO_EDITOR.md`; decision record ADR-016. The following are constraints that collaborators must observe.

- **clip-spec (JSON) is the sole contract**; the renderer is a **replaceable black box** behind it. **Do not leak Remotion / React concepts into clip-spec** — it only describes "what" (segment / crop / subtitle track / style preset / title / soundtrack / brand), remaining renderer-agnostic.
- **The first renderer is Remotion** (server-side, headless Chrome + internal FFmpeg), launched as an independent Node rendering service with **pnpm**, acting as a `spec → MP4 + SRT` black box triggered by the Python queue. **Do not stuff Remotion logic into the Python backend**.
- **Editing form**: transcript editing (deleting a sentence = cutting a segment, **non-destructive**: mark `hidden` instead of actually deleting) + **single-track trim**; preview uses the Remotion `<Player>` (the same component is used for both preview and rendering).
- **Auto-render on generation**: `run_generation` creates `Clip` rows with `render_status=PENDING` when a renderable source (video/image) exists. The worker claims these rows and calls the Remotion render service automatically; the frontend polls `Clip.video_url` until the MP4 is ready. Do not require users to click a manual "Render" button for the standard flow.
- **Scope discipline (critical)**: **do not** add multi-track timelines / layer compositing / transition effects / B-roll library / automatic face reframe / client-side engine — these are L3, explicitly delegated to CapCut / Premiere. Subtitle styles use **preset enums**, no free-form layout.
- **Styles stay within the subset that both CSS and libass can express**, preserving the low-cost option of switching to hand-rolled FFmpeg in the future (clip-spec → filtergraph + shared libass on both ends).
- Hard prerequisites: **multi-language ASR (word-level timestamps) + streamable / seekable video**（对象存储 + API 重定向/代理流式，见 ADR-024）。

## Error Handling & Toasts

- All API calls go through `apiFetch` in `apps/web/src/lib/api.ts`. By default, non-OK responses (except 401, which clears auth and opens the login dialog) and network failures surface a **global sonner toast** carrying the server's real `detail`; success responses are silent.
- Per-call control via the `toast` option: `toast: false` (fully silent — caller handles feedback), `toast: "..."` (show a success message on 2xx), `toast: { success, error }` (custom overrides; `error` replaces the server detail).
- A single `<Toaster />` is mounted in `__root.tsx` (shadcn sonner, wired to the project's own `ThemeProvider` — **not** next-themes). Do not add inline error `<p>` blocks for action feedback; use the global toast. Page-level load-failure placeholder states may stay inline, but pass `toast: false` on those calls to avoid double reporting.

## Task Queue (Backend)

> See ADR-017 for details.

- Time-consuming tasks (ASR / video rendering / generation) must all go into the **worker process** (`python -m app.worker`), **do not use FastAPI `BackgroundTasks`**.
- When adding new heavy tasks: plug the processor into `PROCESSORS` in `app/pipeline/asset_processing.py`, or add a claim source in the worker (e.g., `Clip.render_status`).
- Use **Postgres `FOR UPDATE SKIP LOCKED`** as the queue, **do not introduce Redis / Celery** (swap when scaling horizontally, caller remains unchanged).

## Commit Messages
- Use conventional commits, for example:
  - `feat: add theme toggle with view transition`
  - `fix: correct SidebarMenuButton render usage`
  - `docs: update i18n and theme conventions`

## Database Reset

`apps/api/scripts/reset_db.py` resets a deployment to a clean slate (dry-run by default, `--yes` to execute; `--db-only` / `--storage-only` escape hatches): it wipes **all** DB rows and purges **all** object-storage objects **except two protected prefixes**:

- `demo/` — landing + recipe-card marketing assets (content-hashed URLs baked into `apps/web/src/lib/recipes.assets.ts`; generated once via `scripts/upload_recipe_assets.py`, production never regenerates them).
- `music/` — platform seed tracks. After the wipe, restore the Music rows with `scripts/seed_default_music.py`: it reconciles against the preserved objects **without spending MiniMax quota** (deleting the objects would force paid regeneration).

The script prints the target database / bucket before doing anything — on a server, check the banner before passing `--yes`. Afterwards just restart the stack: API startup auto-migrates (`alembic upgrade head`) and reconciles the Music rows against the preserved `music/` objects (idempotent, no quota). There is no brand seed — a persona with `brand: null` renders with the system default skin. The stack does not seed demo projects; `SKIP_DEMO_SEED` is a dead flag — do not rely on it.

## Testing

The API test suite was removed because it had drifted from the rapidly changing implementation (stale columns, changed storage paths, outdated mocks). Verify changes by running the relevant flow end-to-end instead of relying on a test suite.
