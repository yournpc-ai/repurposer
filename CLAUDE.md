# Repurposer — Claude Collaboration Guidelines

> This document records the frontend conventions and common pitfalls of the Repurposer project, to be followed by AI collaborators.

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
- Hand-written SVG icons are prohibited in the project (unless they are third-party logos with no lucide alternative).
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
- Controls in the same row must align in height: action-area controls are uniformly `h-9`, matching the send button height.
- Pill / dropdown trigger **text must not be bold** (do not add `font-medium`), keep it lightweight.

### Overlay Components (DropdownMenu / Popover / Select)
- **List-style single-select** (select and close on click): use `DropdownMenu` + `DropdownMenuItem`.
- **Multi-control settings panel** (needs to stay open while adjusting multiple values): use `Popover`, with segmented button groups inside.
- Triggers are always `render={<Button variant="outline" size="sm" className="h-9 …" />}`, with "icon + label + `ChevronDown`" inside the button.
- To express "currently selected" for an option, use the `Check` icon; for bottom overlays (dropdowns in the footer), remember `side="top"` to pop upward.
- Pure dropdowns in forms use `Select`; parameter selection in the prompt action bar uses the pill pattern above — do not mix styles.

### Card Depth: ring + shadow, no border
- The "edge + lift" effect for cards / inputs is achieved with **two layers of box-shadow**, not a real `border`:
  ```tsx
  <Card className="ring-1 ring-border shadow-xl">
  ```
  - `ring-1 ring-border` = 1px hairline stroke (simulates border, does not affect layout, auto-adapts across themes, no blur on scaling).
  - `shadow-xl` / `shadow-lg` = outer ambient shadow.
- Real `border` is only used when a "positional dividing line" is truly needed; avoid drawing dividers between sections whenever possible.

### Composer / Input Card
- Structure: left side `Transcript` vertical block as the **upload entry point** (clicking triggers a hidden `<input type="file">`), right side `Textarea`.
- Bottom action bar: parameter pills on the left (Speaker / Tone / Format…), credit chip + circular send button on the right, entire row aligned with `items-center`, controls at `h-9`.
- Card padding is controlled by `CardContent` (`Card` adds `py-0` to remove built-in vertical padding, avoiding double padding).
- Do not add a divider / border in the middle of the card to separate the input area from the action bar; keep it as one piece.

## Product Positioning

Repurposer targets the **European knowledge-speaking market**. Its core positioning is **turning speeches into reusable knowledge assets**, not "viral short-video clips".

- **Target users**: academic conference speakers, corporate summit speakers, research institutions.
- **Core channels**: LinkedIn, institutional websites, email newsletters.
- **Core outputs**: LinkedIn long-form posts, quote cards, multi-language summaries, newsletter content, core insights, blog articles, etc.
- **Multi-language is the entry ticket**: outputs must cover mainstream European languages (FR / DE / ES / IT / EN, etc.).
- **GDPR / EU data residency**: a core selling point when selling to European institutions; backend deployment must support EU regions.

Therefore, frontend copy, tool grids, and example placeholders should all revolve around **knowledge assets / LinkedIn / multi-language**, avoiding descriptions like "TikTok / viral / trending".

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

- Sidebar uses `SidebarProvider` + `Sidebar collapsible="icon"` for collapsibility, **collapsed by default** (`SidebarProvider defaultOpen={false}`).
- Navigation items use `SidebarMenuButton` + `render={<Link to="..." />}`, do not use `asChild`.
- **No right border**: add `group-data-[side=left]:border-r-0` on `Sidebar`, background blends with the main area (see UI design guidelines).
- Structural layout:
  - **Header**: Logo + collapse button (same row) + "Invite members" `SidebarMenuButton`.
  - **Content**: Navigation grouped by Create / Post — Create contains Home, Brand template, Library; Post contains Projects, Speakers.
  - **Footer**: User avatar dropdown (`DropdownMenu`, `side="top"` popping upward, containing Profile / Settings / Logout) at the top, followed by account items (Subscription / Learning / Help).
- Navigation / account icons uniformly `h-4.5 w-4.5`; in `sidebarMenuButtonVariants`, expanded `[&_svg]:size-4.5`, collapsed `group-data-[collapsible=icon]:[&_svg]:size-4.5`, keep them consistent.
- **Collapsed state center alignment**: avatar / invite buttons placed in Header / Footer must be centered; add `group-data-[state=collapsed]:items-center` to the container, and the button itself uses `w-12` square in collapsed state; **do not** put these buttons inside `SidebarMenu` (the list padding will limit the width, causing a 4px offset in collapsed state).
- When adding new sidebar entries, simultaneously update the `nav.*` keys in `zh.ts` / `en.ts`.

## UI Design Guidelines

Overall style: restrained, lightweight, unified. Key reference points:

- **Border radius**: global small radius (`rounded-md` / `rounded-lg`), avoid `rounded-full` (except for circular icon buttons and red dots).
- **Border & shadow**: prefer `ring-1 ring-border` for hairline stroke + `shadow-*` for lift; use solid `border` sparingly; avoid drawing dividers between sections whenever possible.
- **Sidebar blending into main area**: `--sidebar` color equals `--background` (both themes aligned in `styles.css`), and no right border, allowing the sidebar and content area to blend seamlessly.
- **Colors**: only use shadcn theme variables (`bg-background` / `text-foreground` / `text-muted-foreground` / `bg-card` / `ring-border`, etc.), no hard-coded color values.
- **Font weight**: body text and controls stay at regular weight; pill / secondary button text is not bold.
- **Data vs. copy**: all UI copy goes through i18n; user data (speaker names, project titles, etc.) is displayed as-is — do not treat Chinese text as "not yet internationalized" just because it's Chinese — but **defaults must not fall back to a specific data entry** (e.g., Speaker default should show a localized placeholder "Speaker", letting the user actively select).

## Brand Template Page

- Route `/brand-template`, left settings panel + right real-time preview.
- Settings include font, primary color, accent color, logo, default CTA, language tone; preview is reflected in real time on the quote card and LinkedIn post sample cards.
- When adding new settings, simultaneously extend the `brandTemplate.*` i18n keys.

## Video Editor & Rendering (Vertical Shorts)

> Detailed plan in `docs/VIDEO_EDITOR.md` and ADR-016. The following are constraints that collaborators must observe.

- **clip-spec (JSON) is the sole contract**; the renderer is a **replaceable black box** behind it. **Do not leak Remotion / React concepts into clip-spec** — it only describes "what" (segment / crop / subtitle track / style preset / title / soundtrack / brand), remaining renderer-agnostic.
- **The first renderer is Remotion** (server-side, headless Chrome + internal FFmpeg), launched as an independent Node rendering service with **pnpm**, acting as a `spec → MP4 + SRT` black box triggered by the Python queue. **Do not stuff Remotion logic into the Python backend**.
- **Editing form**: transcript editing (deleting a sentence = cutting a segment, **non-destructive**: mark `hidden` instead of actually deleting) + **single-track trim**; preview uses the Remotion `<Player>` (the same component is used for both preview and rendering).
- **Scope discipline (critical)**: **do not** add multi-track timelines / layer compositing / transition effects / B-roll library / automatic face reframe / client-side engine — these are L3, explicitly delegated to CapCut / Premiere. Subtitle styles use **preset enums**, no free-form layout.
- **Styles stay within the subset that both CSS and libass can express**, preserving the low-cost option of switching to hand-rolled FFmpeg in the future (clip-spec → filtergraph + shared libass on both ends).
- Hard prerequisites: **multi-language ASR (word-level timestamps) + streamable / seekable video** (**local FS + FastAPI Range endpoint is sufficient**; object storage deferred to scaling, ADR-011).

## Task Queue (Backend)

> See ADR-017 for details.

- Time-consuming tasks (ASR / video rendering / generation) must all go into the **worker process** (`python -m app.worker`), **do not use FastAPI `BackgroundTasks`**.
- When adding new heavy tasks: plug the processor into `PROCESSORS` in `app/services/asset_processing.py`, or add a claim source in the worker (e.g., `Clip.render_status`).
- Use **Postgres `FOR UPDATE SKIP LOCKED`** as the queue, **do not introduce Redis / Celery** (swap when scaling horizontally, caller remains unchanged).

## Commit Messages
- Use conventional commits, for example:
  - `feat: add theme toggle with view transition`
  - `fix: correct SidebarMenuButton render usage`
  - `docs: update i18n and theme conventions`
