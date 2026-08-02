# Repurposer — Claude Collaboration Guidelines

> This document records the frontend conventions and common pitfalls of the Repurposer project, to be followed by AI collaborators.

## Key Docs

Read these before touching a subsystem (check each doc's own status line — some describe proposed work not yet landed on `main`):

- `docs/README.md` — **docs 索引与治理原则（单一事实源表）**，找文档先查这里。
- `docs/PROGRESS.md` — 进展快照 + 十周排期 + 需求池的**唯一事实源**（ROADMAP 已并入本文并退役，2026-07-31）；排期/优先级只准引用它。
- `docs/MODULE_ARCHITECTURE.md` — 六层模块图 + **表归属契约**（每张表只有一个 owner 模块）+ 跨模块通信规则 + §7 代码地图/队列机制/数据约定（现状架构唯一事实源，ARCHITECTURE.md 已并入）；新表/新模块/新认领源必须在此登记。
- `docs/AGENT_ARCHITECTURE.md` — 4-layer agent pipeline (GenerationContext → Content Director → Agent Executors → Consistency Reviser). Implemented on `main`（Layer 4 未实现，图已标注）；the canonical map of `app/pipeline/orchestrator.py` orchestration and the `app/skills/` registry.
- `docs/MUSIC_ARCHITECTURE.md` — AI-generated music library backed by a dedicated `Music` table; supersedes ADR-019's filesystem-only mood library. Implemented (Layer-4 music verification still future).
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
- **Content panels with inline actions** (buttons/links/rows that must not close on click — e.g. the notification panel): use `Popover`, never `DropdownMenu` (precedent: `NotificationBell`, 2026-07-28).
- **Multi-control settings panel** (needs to stay open while adjusting multiple values): use `Popover`, with segmented button groups inside.
- Triggers are always `render={<Button variant="outline" size="sm" className="h-9 …" />}`, with "icon + label + `ChevronDown`" inside the button.
- To express "currently selected" for an option, use the `Check` icon; for bottom overlays (dropdowns in the footer), remember `side="top"` to pop upward.
- Pure dropdowns in forms use `Select`; parameter selection in the prompt action bar uses the pill pattern above — do not mix styles.

### Card Depth: shadow only — NO ring, NO border
- **Cards / panels must not have any visible outline.** `ring-1 ring-border` and `border` on cards are prohibited — the outlined-card look is a UI style this project explicitly avoids.
- Depth comes from **soft ambient shadow + background contrast** alone:
  ```tsx
  <Card className="shadow-lg">
  ```
  - `shadow-lg` / `shadow-xl` = outer ambient shadow that lifts the card off the background.
  - Separation between sections comes from spacing and `bg-card` vs `bg-background` contrast, never from strokes.
- Real `border` is only used when a "positional dividing line" is truly needed; avoid drawing dividers between sections whenever possible.
- **Edges via `edge-glow`, never `ring-*` / `border`**: in contexts where `bg-card` == `bg-background` (light theme) a downward shadow alone can't define the top edge. The approved treatment is the shared `edge-glow` utility in `styles.css` — an outward-fading halo on all sides layered over a soft ambient drop (dark theme swaps to a white halo automatically). Precedent: the home composer card + entity blocks (2026-07-27). The old `ring-1 ring-border` / `ring-foreground/*` look remains prohibited.
- (Legacy note: older screens still carry `ring-1 ring-border` from the previous convention — remove it when touching those screens; do not copy it into new code.)

### Floating Layers: frosted glass via `overlay-surface`
- **All floating layers** (Popover / DropdownMenu / Dialog / Select / Sheet / Tour) use the shared `overlay-surface` utility defined in `styles.css` — translucent `--popover` (75%) + `backdrop-blur` (10px) + `saturate(1.5)`, with a solid fallback under `@supports not (backdrop-filter)`. Do **not** re-add `bg-popover` to overlay components; if a specific instance needs different opacity, override via its `className` (components merge it last, keeping it the open extension point).
- **Dark-context light frost** (2026-08-02 precedent, composer model pill): over dark surfaces, 75%-opacity dark `--popover` reads as a solid black box (the blur has nothing to show). The approved instance override is `dark:bg-white/10` — the light-frost family of the recipe-card chips (`bg-white/15 backdrop-blur-sm`), applied via `className` so `dark:` wins the cascade. Promote to a global overlay-surface dark variant only after this instance proves out.
- Dialog / Sheet backdrops are `bg-black/30` + `backdrop-blur-[2px]` (not the default near-solid `bg-black/80`) so the frosted surface reads against a dimmed but clearly visible page.
- Tooltips and sonner toasts are intentionally excluded (small transient labels stay solid).

### Composer / Input Card
- Structure: **entity blocks ride the card's top edge** (negative `-mt-*` margin, `overflow-visible` on the Card — they are NOT inside the card): `Assets` block (opens `AssetsModal`) + `Speaker` block (opens `SpeakerPickerModal`), both `h-24 w-20`. Block anatomy (Opus-style, confirmed 2026-07-27): **icon at the top-left → spacer → title → value as the bottom-most line** (Assets: Plus / first-file type icon, value = "Optional" / "{{count}} files"; Speaker: `User` icon / avatar, value = "Auto" / speaker name). The `MentionEditor` fills the remaining width to their right. Block hover = a lift of the SAME color family (dark: `dark:hover:bg-[oklch(0.31_0.008_260)]` on the block's own hue) — never an accent hop, and never rely on plain `hover:bg-*` against a `dark:bg-*` (dark variants beat hover in the cascade; pair them explicitly, 2026-08-02).
- Both blocks are **summaries that open modals** — content management lives in the modal, never in the block: `AssetsModal` = upload zone + file grid + remove (video/audio/images/slides/transcripts); `SpeakerPickerModal` = Auto row + speaker cards with style tags / voice-clone status, single-select-and-close. **Modals are pickers/managers, not editors** — persona editing lives on `/speakers`.
- Bottom row is **one continuous row inside the card** (no separate action-bar strip / muted background): Brand pill on the left, AI model pill + circular send button on the right, controls at `h-9`. The composer has **no language / outputs / clip-count controls and runs no inference of its own** (see behavioral contract). The **AI model pill is display-only** (single provider): a `Popover openOnHover` info card (文案/配音/图像音乐 → provider 分解), never a picker — a picker lands only when a real second provider exists, and its user-facing form is a **policy switch** (e.g. "prefer EU-hosted models"), not a model SKU shelf (2026-08-02 ruling, PROGRESS 需求池 "LLM provider 抽象").
- Card padding is controlled by `CardContent` (`Card` adds `py-0` to remove built-in vertical padding, avoiding double padding).
- Do not add a divider / border in the middle of the card to separate the input area from the action bar; keep it as one piece.
- **Teaching lives in the Tour, not the placeholder**: the textarea placeholder stays a single short prompt — no usage instructions in it. First-visit teaching is the 4-step `Tour` (assets → speaker → prompt (send folded in) → recipe gallery, anchored via `data-tour="composer-*"` / `data-tour="home-recipes"` attributes). The seen flag's version is **a pure function of content** (`lib/tour.ts`: djb2 hash of the step config + the EN copy subtree — EN is the locale source of truth, so every copy edit touches it and a language switch never replays): `localStorage["repurposer-tour-seen"]` stores the hash, the tour auto-opens when the stored hash differs, and complete/skip both write the current hash. **Any content change — steps or copy — replays the tour exactly once per user; no manual version constants, no "worth re-showing" judgment** (read/write inside `useEffect` only — never during SSR). New first-visit tours follow the same pattern: own storage key, a static `TourStepDef[]` config hashed with its EN copy subtree, `data-tour` anchors, effect-only reads.
- **Results page has its own tour** (score badge → video area → "···" menu, anchored via `data-tour="results-*"` on the first ready clip card): separate key `localStorage["repurposer-results-tour-seen"]` with the same content-hash rule, fires once clips are rendered and the generation overlay is closed — no matter how the user arrived (fresh generation or from `/projects`).

#### Composer behavioral contract（2026-07-27 修订：意图识别归管线，composer 瘦身）
- **Prompt is required**: submitting with an empty prompt is blocked locally (toast), same posture as the auth gate. Files are optional (prompt-only → a `prompt.txt` transcript asset).
- **Intent recognition lives in the pipeline, not the composer**: `POST /generate` with `outputs` / `target_language` omitted → the route runs `ComposerIntentAgent` on the instruction (the first asset's `file_url` supplies media context) → TaskSpec. The composer sends only `instruction` + `speaker_id` + `brand_template_id`. Explicit `outputs` (retries, targeted runs, API callers) skip intent.
- **clips need media**: enforced server-side — the intent agent excludes clips for text-only input; `/generate` mirrors with 422 against the resolved outputs.
- **Zero-asset quick start retired** (its trigger was the outputs pill).
- **Show grid ≠ tool grid**: the capability icon row below the composer is display-only — it must not switch outputs or touch composer params.
- **Mentions = the composer's fourth payload field**（2026-08-01，brief `docs/tasks/recipe-mention.md`）: @-entity chips ride `mentions` alongside `instruction` + `speaker_id` + `brand_template_id`. The mention system is a **registry architecture** (frontend `MENTION_REGISTRY` + server-side resolution), `recipe` is the first registered type; new @ types are registry entries, never one-off branches. Input = `MentionEditor` (contentEditable; chips are inline `contenteditable=false` nodes, the DOM owns the text, `syncNow` is the single sync funnel — 完全体 landed 2026-08-02). Chip three laws: **visible** (inline chip with ×), **consumed on send**, **× purifies** (no state lingers across sends). Task-book pinning happens **only** server-side (`resolve_recipe_mentions`) — the composer never builds `prior`. Recipe cards' Remix inserts a recipe mention (no fullscreen modal; the DAG is never user-facing).

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (operating solo or via an assistant). Its core positioning is **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their own IP — not a self-serve media tool, not "viral short-video clips".

- **Target users**: knowledge experts with content. **Never assume the input is a "speech"** (2026-08-01 baseline): it can be a meeting, a report, a podcast, or just a transcript plus photos/slides.
- **Core channels**: LinkedIn, institutional websites, email newsletters.
- **Core outputs**: whatever the user names — LinkedIn posts, quote cards, articles, newsletters, multi-language versions, vertical clips. **Multi-output is a capability surface, not the promise** (2026-07-31): the promise is "the user names it, the agent makes it" — bundle-style "one input, a full set out" advertising is banned; enumerating capabilities is fine.
- **Multi-language is the entry ticket**: outputs must cover mainstream European languages (FR / DE / ES / IT / EN, etc.).
- **GDPR / EU data residency**: a core selling point; outward compliance copy stays in the "ready" angle until compliance actually ships (2026-08-01).
- **Self-label dual track** (2026-08-01, NAMING N-25): internal/technical = **agent**; user-facing copy = **assistant / 助手** ("agent" never appears in outward text; zh prefers the pronoun 它). Role-metaphors (运营官 / 操盘手 / 班子) are retired 话术 (N-24).
- **Copy doctrine** (2026-08-01): plain and factual — no asset jargon ("knowledge assets" rejected), no inflated metaphors ("bigger stage" rejected), no approval-mechanics ("You review. It publishes" rejected). Studio home = hello + spec note only; positioning lives on the landing page. Writing style = 风格/style; "voice" is audio-only (声纹/dub). The Sparkles icon is banned ("AI 用烂了"); the assistant's visual is `LogoMark`.

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

## Sidebar & Navigation

- Sidebar uses `SidebarProvider` + `Sidebar collapsible="icon"`; **PC is a fixed icon rail (2026-08-02)** — the header toggle is retired (`md:hidden`), the `Cmd/Ctrl+B` hotkey is guarded to mobile (`isMobile`), and a centered `LogoMark` fills the collapsed header slot. There is NO expand entry on PC; the mobile off-canvas flow is unchanged. (`SidebarProvider defaultOpen={false}`.)
- Navigation items use `SidebarMenuButton` + `render={<Link to="..." />}`, do not use `asChild`.
- **No right border**: add `group-data-[side=left]:border-r-0` on `Sidebar`, background blends with the main area (see UI design guidelines).
- Structural layout:
  - **Header**: PC = centered `LogoMark` (rail is fixed); mobile = logo lockup + toggle (unchanged). (The "Invite members" entry was removed on 2026-07-25 — do not re-add without an explicit product decision.)
  - **Content**: Flat navigation (no group titles): Home, My projects (`/projects`), Brand template, Speakers. The project grid lives on `/projects`, not on the home page (home is composer-only).
  - **Footer**: User avatar dropdown (`DropdownMenu`, `side="top"` popping upward, containing Profile / Settings / Logout) at the top, followed by account items (Subscription / Learning / Help).
- Navigation / account icons uniformly `h-4.5 w-4.5`; in `sidebarMenuButtonVariants`, expanded `[&_svg]:size-4.5`, collapsed `group-data-[collapsible=icon]:[&_svg]:size-4.5`, keep them consistent.
- **Collapsed state center alignment**: buttons placed in Header / Footer (e.g. the avatar) must be centered; add `group-data-[state=collapsed]:items-center` to the container, and the button itself uses `w-12` square in collapsed state; **do not** put these buttons inside `SidebarMenu` (the list padding will limit the width, causing a 4px offset in collapsed state).
- When adding new sidebar entries, simultaneously update the `nav.*` keys in `zh.ts` / `en.ts`.

## UI Design Guidelines

Overall style: restrained, lightweight, unified. Key reference points:

- **Border radius**: global small radius (`rounded-md` / `rounded-lg`), avoid `rounded-full` (except for circular icon buttons and red dots).
- **Border & shadow**: **no outlines on cards** — depth via `shadow-*` + background contrast only; `ring` / `border` strokes on cards are prohibited; avoid drawing dividers between sections whenever possible.
- **Sidebar blending into main area**: `--sidebar` color equals `--background` (both themes aligned in `styles.css`), and no right border, allowing the sidebar and content area to blend seamlessly.
- **Colors**: only use shadcn theme variables (`bg-background` / `text-foreground` / `text-muted-foreground` / `bg-card` / `ring-border`, etc.), no hard-coded color values.
- **Font weight**: body text and controls stay at regular weight; pill / secondary button text is not bold.
- **Data vs. copy**: all UI copy goes through i18n; user data (speaker names, project titles, etc.) is displayed as-is — do not treat Chinese text as "not yet internationalized" just because it's Chinese — but **defaults must not fall back to a specific data entry** (e.g., Speaker default should show a localized placeholder "Speaker", letting the user actively select).

## Brand Template Page

- Route `/brand-template`, left settings panel + right real-time preview.
- Settings include font, primary color, accent color, logo, default CTA, language tone; preview is reflected in real time on the quote card and LinkedIn post sample cards.
- **Brand = visual skin only**（自 MVP_SPEC §4.6 迁入）：voice / audience / contentGuidelines / CTA 归属 Speaker（`/speakers/$id`），生成时经 `GenerationContext.speaker` 注入 Content Director / Clip Agent。理由：同一个 Speaker 可以服务多个 Brand（如大学官方号 vs 个人 IP），内容策略必须跟人走而不是跟皮肤走。
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

The script prints the target database / bucket before doing anything — on a server, check the banner before passing `--yes`. Afterwards just restart the stack: API startup auto-migrates (`alembic upgrade head`), re-seeds the default brand template, and reconciles the Music rows against the preserved `music/` objects (idempotent, no quota). Demo-project seeding is retired and `SKIP_DEMO_SEED` is a dead flag (never existed in code) — do not rely on it.

## Testing

The API test suite was removed because it had drifted from the rapidly changing implementation (stale columns, changed storage paths, outdated mocks). Verify changes by running the relevant flow end-to-end instead of relying on a test suite.
