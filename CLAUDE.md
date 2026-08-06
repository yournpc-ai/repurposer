# Repurposer — Claude Collaboration Guidelines

> This document records the frontend conventions and common pitfalls of the Repurposer project, to be followed by AI collaborators.

## Key Docs

Read these before touching a subsystem (check each doc's own status line — some describe proposed work not yet landed on `main`):

- `docs/README.md` — **docs 索引与治理原则（单一事实源表）**，找文档先查这里。
- `docs/PROGRESS.md` — 进展快照 + 排期 + 需求池的**唯一事实源**；排期/优先级只准引用它。
- `docs/MODULE_ARCHITECTURE.md` — 六层模块图 + **表归属契约**（每张表只有一个 owner 模块）+ 跨模块通信规则 + §7 代码地图/队列机制/数据约定（现状架构唯一事实源）；新表/新模块/新认领源必须在此登记。
- `docs/AGENT_ARCHITECTURE.md` — 4-layer agent pipeline (GenerationContext → Content Director → Agent Executors → Consistency Reviser). Implemented on `main`（Layer 4 未实现，图已标注）；the canonical map of `app/pipeline/orchestrator.py` orchestration and the `app/skills/` registry.
- `docs/MUSIC_ARCHITECTURE.md` — AI-generated music library backed by a dedicated `Music` table. Implemented (Layer-4 music verification still future).
- `docs/VIDEO_EDITOR.md` + ADR-016 — clip-spec is the **sole render contract**; the renderer is a replaceable black box. Do not leak Remotion/React concepts into clip-spec.
- `docs/DECISIONS.md` — ADRs，只追加不修改；翻案写新 ADR（如 ADR-025 修订 ADR-004 的 provider 抽象决策）。
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
- **Dark casts no shadows at all** — night has no light source: every `shadow-*` utility compiles to transparent under `.dark` via one switch (`--tw-shadow-color: transparent` in `styles.css`; focus rings survive — they compose via `--tw-ring-shadow`, not the shadow color). Dark elevation = tonal steps + the hairline + glass translucency. `edge-glow` is **light-theme only** (its dark variant is a deliberate no-op); dark hero surfaces take the `ring-foreground/10` hairline instead.
- **Prohibited: visible strokes** — `border` + `border-border`, `ring-1 ring-border`, and `ring-foreground/*` stronger than the /10 hairline. The /10 hairline + a soft ambient shadow MAY coexist (that is the default card); a *visible* stroke must NOT also carry a shadow — pick exactly one. (`border-dashed` dropzones and `border-transparent` variant bases are fine; focus rings are interactivity, not edges.)
- Separation between sections comes from spacing and token steps (`bg-muted` / `bg-inset` fills), never from drawn dividers.
- **Hero surfaces use `edge-glow` instead**: the home composer card + entity blocks strip the hairline (`ring-0`) and take the shared `edge-glow` halo (dark swaps to a white halo automatically) — pick `edge-glow` OR the hairline card look, never stack them.
- **Gray ladder**: surface hierarchy comes from the stepped tokens, never from one-off alpha fills. **Light**: `--background` is **pure white** (1.0) — cards float via the base Card's built-in `ring-foreground/10` hairline + soft shadow, not a gray underlay; `--muted` 0.95 → `--inset` 0.92. **Dark**: `--background` is **near-black** (0.12) and elevation speaks **glass, not ladder** — floating layers are translucent (see `overlay-surface`), `--card`/`--popover` 0.21, `--muted` 0.24, and **`--inset` is INVERTED: 0.15, darker than the panel** (kbd chips / seed values / search inputs sit in darker wells). **`bg-muted/50`, `bg-background/60`, `bg-muted/30` and similar ad-hoc alphas are prohibited** — an inner block uses solid `bg-muted`, a nested block on a muted card inverts to `bg-card`.
- **Hover / highlight = `--accent`, one token both themes**: light = solid 0.95 gray step; **dark = `oklch(1 0 0 / 8%)`, a translucent white veil** (never a lighter solid step). Menu rows, list hovers, picker selected states, ghost-button hovers all consume `bg-accent` (or `/50` for the weak tier), so one variable retunes every hover in the app. Never hardcode hover COLOR VALUES per instance (`dark:hover:bg-[oklch(…)]` banned) — but **variant pairing is still mandatory**: `dark:bg-*` beats a bare `hover:bg-*` in the cascade, so an element carrying `dark:bg-x` must also carry `dark:hover:bg-accent` explicitly.
- **Text is three tiers, not two**: `foreground` (0.145 / dark 0.95) → `muted-foreground` subtitles (0.556 / dark 0.63) → **`meta-foreground`** (0.68 / dark 0.52) for small ALL-CAPS tracked meta labels (the "MODEL / SEED" style), composed via the `text-meta` utility (`uppercase` + `tracking-[0.08em]` + the token color).

### Floating Layers: frosted glass via `overlay-surface`
- **All floating layers** (Popover / DropdownMenu / Dialog / Select / Sheet / Tour) use the shared `overlay-surface` utility defined in `styles.css` — translucent `--popover` + `backdrop-blur` + `saturate(1.4)`, **per-theme recipe**: light = **92% + blur(24px)** (lower opacity lets dark content behind bleed through and tint the panel); dark = **68% + blur(28px)** (over the near-black canvas a high-opacity fill reads as a solid box and the blur has nothing to show). Solid fallback under `@supports not (backdrop-filter)`. Do **not** re-add `bg-popover` to overlay components, and **per-instance frost patches (e.g. `dark:bg-white/10`) are banned** — tune the shared recipe; if a specific instance genuinely needs different opacity, override via its `className` (components merge it last, keeping it the open extension point).
- Dialog / Sheet backdrops are **per-theme**: light = `bg-background/60` (a white wash — a black scrim over the white page reads as gray murk) + `backdrop-blur-[2px]`; dark = `bg-black/30` + `backdrop-blur-[2px]` — the frosted surface reads against a dimmed but clearly visible page in both themes.
- Tooltips and sonner toasts are intentionally excluded (small transient labels stay solid).
- **Scroll fades** (`scroll-fade-y` / `scroll-fade-x` in `styles.css`): mask utilities that dissolve a scrollport's edge before content reaches floating chrome (precedent: the overlay chat viewport). Apply **per surface**, each fade zone paired with that surface's own content padding — **never inside shared primitives**: an unused class sitting in a primitive comes alive the moment a same-named `@utility` is defined.

### Composer / Input Card
- **质感配方（Lovart composer 参照）**：大圆角（`rounded-2xl`）+ 内部空气（`p-5`、输入区 `h-24`）+ **耳语级中控区**——底排控件（Brand pill、AI model pill）一律 `variant="ghost"` 纯文字+小图标，只有 send 一个深色实心锚点。**填充灰（`bg-muted`/`bg-inset`）只给内容容器（inset 块、信息 pill、badge），永远不给操作按钮**——参考图中底排只有 credits 一个信息 pill 有填充，按钮全裸。
- Structure: **entity blocks ride the card's top edge** (negative `-mt-*` margin, `overflow-visible` on the Card — they are NOT inside the card): `Assets` block (opens `AssetsModal`) + `Speaker` block (opens `SpeakerPickerModal`), both `h-24 w-20`. Block anatomy (Opus-style): **icon at the top-left → spacer → title → value as the bottom-most line** (Assets: Plus / first-file type icon, value = "Optional" / "{{count}} files"; Speaker: `User` icon / avatar, value = "Auto" / speaker name). The `MentionEditor` fills the remaining width to their right. Block hover: light = `bg-accent` gray step; dark = a **solid** color-mix lift (`dark:hover:bg-[color-mix(in_oklch,var(--muted),var(--foreground)_5%)]`, the button-secondary recipe) — the blocks STRADDLE the card's top edge, so a translucent veil hover would reveal the page/card seam behind them. In dark the blocks lift one tonal step off the card (`dark:bg-muted` on the card's 0.21; dark casts no shadows, so the card's edge is the `ring-foreground/10` hairline). **Rule: the white-veil hover (`bg-accent` dark) is only for uniform substrates (menu rows, list rows, pickers); any element straddling a surface boundary must hover with a solid fill.**
- Both blocks are **summaries that open modals** — content management lives in the modal, never in the block: `AssetsModal` = upload zone + file grid + remove (video/audio/images/slides/transcripts); `SpeakerPickerModal` = Auto row + speaker cards with style tags / voice-clone status, single-select-and-close. **Modals are pickers/managers, not editors** — persona editing lives on `/speakers`.
- Bottom row is **one continuous row inside the card** (no separate action-bar strip / muted background): Brand pill on the left, AI model pill + circular send button on the right, controls at `h-9`. The composer has **no language / outputs / clip-count controls and runs no inference of its own** (see behavioral contract). The **AI model pill is display-only** (single provider): a `Popover openOnHover` info card (文案/配音/图像音乐 → provider 分解), never a picker — a picker lands only when a real second provider exists, and its user-facing form is a **policy switch** (e.g. "prefer EU-hosted models"), not a model SKU shelf (裁定见 PROGRESS 需求池 "LLM provider 抽象").
- Card padding is controlled by `CardContent` (`Card` adds `py-0` to remove built-in vertical padding, avoiding double padding).
- Do not add a divider / border in the middle of the card to separate the input area from the action bar; keep it as one piece.
- **Teaching lives in the Tour, not the placeholder**: the textarea placeholder stays a single short prompt — no usage instructions in it. First-visit teaching is the 4-step `Tour` (assets → speaker → prompt (send folded in) → recipe gallery, anchored via `data-tour="composer-*"` / `data-tour="home-recipes"` attributes). The seen flag's version is **a pure function of content** (`lib/tour.ts`: djb2 hash of the step config + the EN copy subtree — EN is the locale source of truth, so every copy edit touches it and a language switch never replays): `localStorage["repurposer-tour-seen"]` stores the hash, the tour auto-opens when the stored hash differs, and complete/skip both write the current hash. **Any content change — steps or copy — replays the tour exactly once per user; no manual version constants, no "worth re-showing" judgment** (read/write inside `useEffect` only — never during SSR). New first-visit tours follow the same pattern: own storage key, a static `TourStepDef[]` config hashed with its EN copy subtree, `data-tour` anchors, effect-only reads.
- **Results page has its own tour** (score badge → video area → "···" menu, anchored via `data-tour="results-*"` on the first ready clip card): separate key `localStorage["repurposer-results-tour-seen"]` with the same content-hash rule, fires once clips are rendered and the generation overlay is closed — no matter how the user arrived (fresh generation or from `/projects`).

#### Composer behavioral contract（意图层单面化：chat 唯一入口）
- **Prompt is required**: submitting with an empty prompt is blocked locally (toast), same posture as the auth gate. Files are optional — a prompt-only send creates **no** asset: the PlanAgent judges whether a message IS the user's own content (pasted transcript/draft, with or without "this is my…" framing) and promotes it to a real transcript asset (`create_transcript_asset_from_text`); a generate request with no assets and no pasted content gets an ask-for-material answer, never a groundless task book. Never reintroduce length-based heuristics — content-vs-request is LLM-judged only. Mid-conversation uploads go through the overlay chat's attach button — picked files **stage as lifecycle chips inside the input group** (uploading → done/error, × removes and deletes the asset; direct-to-storage, same flow as the composer) and only the **send button** consumes them, riding the turn as message `attachments` (persisted, re-rendered on refresh). Picking a file never sends anything by itself; an attachment-only send is legal — the plan path infers from an honest stand-in line, and a blank message never auto-answers a docked checkpoint.
- **The composer does NO intent recognition**（简报 `docs/tasks/intent-surface-unification.md`）: send = spinner (create empty project + upload assets) → navigate to `/projects/$id?overlay=chat` with the draft handed over via router state → the overlay chat sends it as the first `POST /chat` message (mentions + `brand_template_id` ride along). `POST /chat` is the **only intent surface**: the plan path builds / refines / confirms the task book (PlanAgent); projects with runs go to the four-state ChatIntentAgent. Never reintroduce a second intent entry (e.g. a dedicated `/intent` endpoint).
- **clips need media**: enforced server-side — the PlanAgent excludes clips for text-only input; `create_run` mirrors with 422 at the birthplace.
- **Show grid ≠ tool grid**: the capability icon row below the composer is display-only — it must not switch outputs or touch composer params.
- **Mentions = the composer's fourth payload field**（brief `docs/tasks/recipe-mention.md`）: @-entity chips ride `mentions` alongside the first chat message. The mention system is a **registry architecture** (frontend `MENTION_REGISTRY` + server-side resolution), `recipe` is the first registered type; new @ types are registry entries, never one-off branches. Input = `MentionEditor` (contentEditable; chips are inline `contenteditable=false` nodes, the DOM owns the text, `syncNow` is the single sync funnel). Chip three laws: **visible** (inline chip with ×), **consumed on send**, **× purifies** (no state lingers across sends). Recipe preset seeding happens **only** server-side (`resolve_recipe_mentions`, in the chat plan path) — the composer never builds `prior`. A recipe is a **preset, never a pin**: it seeds the first book (missing slot types + dub defaults) and every field stays refine-able; panel hand-edits (explicit slots) are three-way merged against the stored book and the fresh inference (`merge_prior_slots`) with **chat revisions always winning** — chat IS how the plan is edited, nothing is locked. Recipe cards' Remix inserts a recipe mention (composer prefill, never a self-contained form modal). 闭环链第 2 周起卡面点开 = **只读配方检视 overlay**（Recipe 数据包的渲染器：base/flow/prompt/原素材/成片五区，RECIPES §7.1），其 Remix 回填 composer——overlay 永不含生成按钮（brief `docs/tasks/results-workspace.md`）。The **operable** DAG canvas is never user-facing; the static recipe flow is the DAG's only user-facing form (ADR-035 三切).

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (operating solo or via an assistant). Its core positioning is **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their own IP — not a self-serve media tool, not "viral short-video clips".

- **Target users**: knowledge experts with content. **Never assume the input is a "speech"**: it can be a meeting, a report, a podcast, or just a transcript plus photos/slides.
- **Core channels**: LinkedIn, institutional websites, email newsletters.
- **Core outputs**: whatever the user names — LinkedIn posts, quote cards, articles, newsletters, multi-language versions, vertical clips. **Multi-output is a capability surface, not the promise**: the promise is "the user names it, the agent makes it" — bundle-style "one input, a full set out" advertising is banned; enumerating capabilities is fine.
- **Multi-language is the entry ticket**: outputs must cover mainstream European languages (FR / DE / ES / IT / EN, etc.).
- **GDPR / EU data residency**: a core selling point; outward compliance copy stays in the "ready" angle until compliance actually ships.
- **Self-label dual track** (NAMING N-25): internal/technical = **agent**; user-facing copy = **assistant / 助手** ("agent" never appears in outward text; zh prefers the pronoun 它). Role-metaphors (运营官 / 操盘手 / 班子) are banned (N-24).
- **Copy doctrine**: plain and factual — no asset jargon ("knowledge assets" rejected), no inflated metaphors ("bigger stage" rejected), no approval-mechanics ("You review. It publishes" rejected). Studio home = hello + spec note only; positioning lives on the landing page. Writing style = 风格/style; "voice" is audio-only (声纹/dub). The Sparkles icon is banned ("AI 用烂了"); the assistant's visual is `LogoMark`.
- **用户到来即彷徨**（论证 → STRATEGY §5，行为规格 → CHAT_ARCH §3.3）：目标用户带着素材和模糊目标而来——不知道做什么、怎么做、做完之后呢。产品的每一步都必须回答"现在该做什么、为什么、下一步是什么"：开始前由配方卡接住，计划中由确认 dock 接住，**完成后由结果页闭环接住**（PROGRESS 第 4 周体验闭环周）。agent 顾问姿态四律：诊断一轮封顶（只问用户能答的——听众/目的；用户不懂的参数由配方与默认值吸收）、带理由纠偏（给替代方案，禁静默拒绝）、成功定义随任务书、永给唯一下一步；不做职业/变现咨询——诊断是为了更快给出对的方案，不是把生产工具变成顾问。
- **闭环优先于卡片数量**：卡点亮（能力真 + 预览真）≠ 通路；「Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产」全通才算通路。对外汇报的叙事单位是"完全通路"，不是"点亮了几张卡"。

Therefore, frontend copy, tool grids, and example placeholders should all revolve around **content / LinkedIn / multi-language**, avoiding descriptions like "TikTok / viral / trending".

## Internationalization (i18n)

### Dictionary Structure
- Source language is English: `apps/web/src/lib/i18n/locales/en.ts` is the source of truth and exports the `Resources` type.
- Chinese `zh.ts` must satisfy `zh: Resources`, so missing keys will be caught at the TypeScript level.

### Adding New Copy
1. Add the key / value in `en.ts` first.
2. Mirror it to `zh.ts` in the same structure.
3. In components, use `const { t } = useTranslation()`; do not hard-code strings.

### Interpolation
```ts
t("home.allProjects", { count: projects.length })
```

### SSR
- First screen defaults to **English** rendering to avoid hydration mismatches.
- `I18nProvider` reads the `repurposer-lang` cookie after hydration to switch languages.

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
  - **Content**: Flat navigation (no group titles): Home, My projects (`/projects`), Brand template, Speakers. The project grid lives on `/projects`, not on the home page (home is composer-only).
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
- **Data vs. copy**: all UI copy goes through i18n; user data (speaker names, project titles, etc.) is displayed as-is — do not treat Chinese text as "not yet internationalized" just because it's Chinese — but **defaults must not fall back to a specific data entry** (e.g., Speaker default should show a localized placeholder "Speaker", letting the user actively select).

## Brand Template Page

- Route `/brand-template`, left settings panel + right real-time preview.
- Settings include font, primary color, accent color, logo, default CTA, language tone; preview is reflected in real time on the quote card and LinkedIn post sample cards.
- **Brand = visual skin only**：voice / audience / contentGuidelines / CTA 归属 Speaker（`/speakers/$id`），生成时经 `GenerationContext.speaker` 注入 Content Director / Clip Agent。理由：同一个 Speaker 可以服务多个 Brand（如大学官方号 vs 个人 IP），内容策略必须跟人走而不是跟皮肤走。
- When adding new settings, simultaneously extend the `brandTemplate.*` i18n keys.

## Video Editor & Rendering (Vertical Shorts)

> Detailed plan in `docs/VIDEO_EDITOR.md` and ADR-016. The following are constraints that collaborators must observe.

- **clip-spec (JSON) is the sole contract**; the renderer is a **replaceable black box** behind it. **Do not leak Remotion / React concepts into clip-spec** — it only describes "what" (segment / crop / subtitle track / style preset / title / soundtrack / brand), remaining renderer-agnostic.
- **The first renderer is Remotion** (server-side, headless Chrome + internal FFmpeg), launched as an independent Node rendering service with **pnpm**, acting as a `spec → MP4 + SRT` black box triggered by the Python queue. **Do not stuff Remotion logic into the Python backend**.
- **Editing form**: transcript editing (deleting a sentence = cutting a segment, **non-destructive**: mark `hidden` instead of actually deleting) + **single-track trim**; preview uses the Remotion `<Player>` (the same component is used for both preview and rendering).
- **Auto-render on generation**: `run_generation` creates `Clip` rows with `render_status=PENDING` when a renderable source (video/image) exists. The worker claims these rows and calls the Remotion render service automatically; the frontend polls `Clip.video_url` until the MP4 is ready. Do not require users to click a manual "Render" button for the standard flow.
- **Scope discipline (critical)**: **do not** add multi-track timelines / layer compositing / transition effects / B-roll library / automatic face reframe / client-side engine — these are L3, explicitly delegated to CapCut / Premiere. Subtitle styles use **preset enums**, no free-form layout.
- **Styles stay within the subset that both CSS and libass can express**, preserving the low-cost option of switching to hand-rolled FFmpeg in the future (clip-spec → filtergraph + shared libass on both ends).
- Hard prerequisites: **multi-language ASR (word-level timestamps) + streamable / seekable video** (**local FS + FastAPI Range endpoint is sufficient**; object storage deferred to scaling, ADR-011).

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

The script prints the target database / bucket before doing anything — on a server, check the banner before passing `--yes`. Afterwards just restart the stack: API startup auto-migrates (`alembic upgrade head`), re-seeds the default brand template, and reconciles the Music rows against the preserved `music/` objects (idempotent, no quota). The stack does not seed demo projects; `SKIP_DEMO_SEED` is a dead flag — do not rely on it.

## Testing

The API test suite was removed because it had drifted from the rapidly changing implementation (stale columns, changed storage paths, outdated mocks). Verify changes by running the relevant flow end-to-end instead of relying on a test suite.
