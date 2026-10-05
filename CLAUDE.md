# Repurposer — Claude Collaboration Guidelines

> 协作规范与高频硬律。两个设计系统的**全文**各有其家：视觉/交互形态 = `docs/UI_GUIDELINES.md`；chat/画布行为 = `docs/CHAT_ARCHITECTURE.md`。本文只载最高频违规的硬律与指针——动一个子系统前先读它的全文文档。
>
> 文档卫生：本文与 docs 只承载**现行法**（现在时直陈）。不写日期、拍板过程、翻案链、退役史——历史在 git 与 `docs/DECISIONS.md`（ADR 编号）。

## Key Docs

Read these before touching a subsystem (check each doc's own status line — some describe proposed work not yet landed on `main`):

- `docs/README.md` — **docs 索引与治理原则（单一事实源表）**，找文档先查这里。
- `docs/PROGRESS.md` — 进展快照 + 排期 + 需求池的**唯一事实源**；排期/优先级只准引用它。
- `docs/MODULE_ARCHITECTURE.md` — 六层模块图 + **表归属契约**（每张表只有一个 owner 模块）+ 跨模块通信规则 + §7 代码地图/队列机制/数据约定（现状架构唯一事实源）；新表/新模块/新认领源必须在此登记。
- `docs/UI_GUIDELINES.md` — **studio 视觉/交互设计系统唯一事实源**：圆角/纵深/灰梯/hover/浮层冰霜/composer 视觉解剖/侧栏解剖/页面布局/画布形态。动 `_app` UI 前必读。
- `docs/CHAT_ARCHITECTURE.md` — **chat/画布行为唯一事实源**：终态工具集 / plan path / QuestionDock / SSE / 打字机律 / 三形态机 / 词表 v3 / 相机律。动 chat、dock、画布行为前必读。
- `docs/POSITIONING.md` — **定位根概念架构（运营层母文档，ADR-042，已拍板未实施）**：身份根 = 定位（positioning），人设收窄为表达分区，渠道/选题/素材挂根；施工排期 = PROGRESS 第八~十周运营端。动身份模块/渠道/选题/home 前先读它。
- `docs/AGENT_ARCHITECTURE.md` — 四层工程地图（Model / Harness / Graph / Loop，ADR-039）：工具包 `app/tools/`（能力唯一家）+ agent registry `app/agents/`（一个 Agent 类 + 声明实例）+ `NodeBase` 图内核（报价=fold / 执行=topo / 校验=∀ / 对账=⊆）+ chat 治理环。agent 架构唯一事实源；outputs 可扩展（产物 = 工具的属性，注册表派生）。
- `docs/DIALOG_WORKFLOW.md` — **对话→生产概念架构母文档（ADR-052）**：厚 agent = 产品层一个 agent、身体 = 一条 workflow（聊天 → 意图路由 → brief/计划 → 生产 DAG → 产出）；双引擎分离 / canonical 词汇（router·understand·plan·brief）/ 有界 loop 节点三护栏 / 施工切分 B1~B4。动 chat 意图层 / plan path / 多轮对话 / agent 概念前必读。
- `docs/MUSIC_ARCHITECTURE.md` — AI-generated music library backed by a dedicated `Music` table. Implemented (Layer-4 music verification still future).
- `docs/BILLING.md` — **积分/钱包/计费架构母文档（ADR-055）**：credit / wallet / credit_transactions 三词两层货币 + hold→capture→release 扣费时序 + configs 公共参数表 + 消耗比例参数 + 负余额语义；支付只留 W11 边界。动积分 / 钱包 / configs / 扣费 / 估价展示前先读它。
- `docs/RENDERING.md` + ADR-016 — clip-spec is the **sole render contract**（字段级契约与渲染链架构的唯一事实源）; the renderer is a replaceable black box. Do not leak Remotion/React concepts into clip-spec. 编辑器交互与范围纪律在 `docs/VIDEO_EDITOR.md`。
- `docs/DECISIONS.md` — ADRs，**只保留现行决策**：过时 / 被翻案的内容直接删除（历史在 git，不留痕）；新决策追加新编号，编号不连续属正常。
- `docs/COMPETITIVE_ANALYSIS.md` + `docs/DECISION_MATRIX.md` + `docs/research/` — 竞品综合 / 采纳矩阵 / 原始证据三层，评估竞品功能时按此顺序查。
- `docs/DATABASE_MIGRATIONS.md` — Alembic workflow; `migrations/versions/*.py` is part of the codebase and must be committed.
- `docs/tasks/` — per-feature implementation briefs with acceptance criteria and explicit "Prohibited Behaviors"; read the relevant task before starting and respect its prohibitions. 已完成简报归 `docs/archive/tasks-done/`（历史记录，不再维护）。

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
- All icons must be imported from `lucide-react`. Hand-written SVG icons are prohibited, with two exceptions: third-party logos with no lucide alternative, and **the brand mark** — `src/components/LogoMark.tsx`; its geometry's source of truth is `LogoMark.tsx`, `public/favicon.svg` is the static baked-color copy and must be kept in sync.
- **Inside `Button`, use `size-*` not `h-* w-*`**: every button variant pins `[&_svg:not([class*='size-'])]:size-N` — `h-5 w-5` does NOT match the `:not()` guard and gets silently overridden; `size-5` is exempt. Full size table = `docs/UI_GUIDELINES.md` §2.

## UI 硬律（全文 → `docs/UI_GUIDELINES.md`）

- **小圆角**：默认 `rounded-md` / `rounded-lg`。`rounded-full` 仅四例外：真圆形图标钮 / 状态徽章红点 / home composer 钉顶单行 stadium 条 / gallery 筛选 pill 行。`Badge` 用于元数据恒 `className="rounded-md"` 覆盖。
- **同排控件 `h-9` 中心线对齐**；pill / trigger 文字不加粗。
- **浮层选型**：列表单选 = `DropdownMenu`；内联动作面板 / 多控件设置面板 = `Popover`；表单纯下拉 = `Select`。
- **纵深**：卡 = 基座自带 `ring-foreground/10` 发丝线 + 填充阶浮起；**禁可见描边**（`border-border` / `ring-border` / 强于 /10 的 `ring-foreground/*`）；in-flow 面（卡/composer/媒体 tile）**永不带 shadow**，shadow 只属于浮层；填充优先——fill 已区分就零环零边。
- **灰梯 token 阶**，禁临时 alpha 填充（`bg-muted/50` / `bg-background/60` 等）；hover 一律 `bg-accent`（dark 是半透白纱不是亮阶），禁逐实例硬编码 hover 色值；带 `dark:bg-*` 的元素必须显式配 `dark:hover:bg-accent`。
- **文字三档**：`foreground` / `muted-foreground` / `meta-foreground`（`text-meta` utility）。
- **浮层一律 `overlay-surface`**（styles.css 共享冰霜配方）；overlay chrome 只用 Dialog primitive，**禁手写 backdrop**；视口锚浮层 portal 到 `document.body`。
- **颜色只用 shadcn token**，禁硬编码色值。
- **布局**：`_app` 页面 `flex-1`，禁 `min-h-svh`/`min-h-screen`（home = `h-svh` + 单内部 scrollport 例外；landing 页合法）；页面主体放 `SidebarInset`。
- **侧栏**：导航用 `SidebarMenuButton` + `render={<Link />}`；图标 `h-4.5 w-4.5`；新增入口同步 `nav.*` i18n；**通知铃 = 内容区右上角唯一浮动 chip**，该角全站保留；无全局 AppHeader。
- **Dot grid = FlowView 签名，只此一面**；home 与其余任何面禁用。

## Composer / Chat 行为硬律（全文 → `docs/CHAT_ARCHITECTURE.md`）

- **Agent 北极星（ADR-088/089）**：Agent 持续生产与修订用户可理解的项目产物；不编译、不直接执行 workflow 内部语言；付费执行只从已确认范围开始。
- **composer 零意图识别**：send = spinner（建项目 + 上传素材）→ 直达 `/projects/$id`（canvas + ChatDock 三形态机）。**`POST /chat` 是唯一意图面**——永不新增第二意图入口（如专用 `/intent` 端点）。
- **Prompt 必填**：空提交本地 toast 拦截。纯 prompt 发送不建资产；intent router 判定消息是「用户自己的内容」还是「请求」（LLM 判定，**禁长度启发式**），是内容则提升为 transcript 资产（`create_transcript_asset_from_text`）；无资产无贴文的生成请求得到要素材的回答，永不无中生有计划。
- **中途上传走 dock attach 钮**：选中文件暂存为输入组内生命周期 chips（uploading → done/error，× 删且删资产）；**只有 send 钮消费它们**，骑回合作消息 `attachments`（持久化，刷新重渲染）。选文件自身永不发送；附件单发合法；空消息永不自动作答 docked checkpoint。
- **clips need media**：server 侧双重 enforce——intent router 对纯文本输入排除 clips；`create_run` 出生地镜像 422。
- **打字机律（绝对规范，任何改动不得违背）**：agent 一切言语以打字机节奏出现，**整段瞬移永禁**。两条结构牙：① 散文字段入 schema 必带读容忍（null 读为空默认值——一次 schema 拒收 = 被拒迭代 = 永不流式 = 瞬移）；② 零 delta 路径的最后闸门 = 信封到达后散文照样走 typewriter 节拍释放（`paceSettledProse`），dock 等释放排干才落。新增散文通道 / 改散文字段 / 加提案工具时两牙同批检查（规格 = CHAT_ARCH §8.6）。
- **展示文案二源律（ADR-058）**：用户可见命名类文案只有两个合法来源——① LLM 建图时命名（proposal 的 `name` 字段，null/空读容忍）；② 世界自证（产物徽标 / 节点状态 / 真实数字）。**冻参模板永禁**。**手改撤名**：计划卡任何手改即清空 `name`，回退读当前参数的诚实标签。
- **echo 防编造律（ADR-060）**：回声只回述用户说过的（作品 / 语言 / 数量），**永不发明平台或场所**——a post is just a post until the user names where it lives；渠道合法来源 = 用户点名或渠道授权，永不是默认值。
- **起始句 = LLM 言语（ADR-093）**：start_run 回合先说话再调用，开工句由模型说出并落库为普通 assistant 行；chrome/模板替说全形态永禁。
- **口头确认律（ADR-092）**：方案 dock 后恒等确认——echo 收尾恒为一句朴素的方案判断问句（一词可答），口头 yes 走普通 chat 道到 start_run（与 Start 钮同一机器）；策略直执 / 静默开工永禁；收尾永不带「成片出来后再调」式交付后修订预告。
- **状态行一座两行**：消息流一切瞬态「现在在干什么」行 = 同一个 `components/chat/StatusLine.tsx`；label 恒为当下相位叙事，永不只是冻词 "Thinking"。thinking 行渲染门 = `chatBusy && !proseActive`。
- **Mentions**：@-entity chips 随消息 `mentions` 字段送达；注册表架构（前端 `MENTION_REGISTRY` + 服务端解算），已注册 = `asset`（请求族）/ `output`（指认族，钉 id 服务端确定性解出修订目标）。**配方永不是 mention**（配方 = 提示词，卡面预填模板即全部发射载荷）。**Chip 三律**：可见（inline + ×）/ 发送消费 / × 净化。方针全文 = `docs/MENTIONS.md`。
- **修订 = 图变更**：chat 修订骑 `POST /chat` 的 `edit_graph`（wiring 提案）→ `apply_wiring_ops` 唯一写口；卡面 prompt 直改 = 确定性手势走 `POST /projects/{id}/graph/revise`，**dock 零消息**（节点状态周期就是全部反馈），卡面乐观回显永不回闪。
- **画布只读**：FlowView 无 drag/connect/pan/zoom API；**相机只认用户发起节拍**（draft 图到来整链 fit / 新节点诞生 setCenter；背景 refetch 永不动相机）。
- **Dock 三形态机**（full / panel / dock）与保草稿承重结构（单一 root + 恒渲染容器 + 恒定子索引，MentionEditor 跨形态翻转永不 remount）：全文 CHAT_ARCH §1 关键形态事实。
- **chat 修复禁补丁式加禁令（先取证后归因）**：chat bug 的修法 = 先取证再归因到源头，**永不用新增禁令压症状**——上下文盲的禁令（「禁应答粒子」「禁指导用户」式）在合法场景必然拆东墙补西墙。取证 = 回放真实 payload 与机制链：payload 是「代码 × 当时世界状态」的纯函数，无 LLM 台账也能用真实 assemble + 内存拨回世界状态字节级重建（先例 = ADR-101 时代的 `scratch/replay_material_wait_turn.py`，脚本已退役、存档在 git 历史）。源头只有四类：装配 / 工具观察文本 / 法条座位冲突（两部法打架或适用范围未声明）/ 一法多说（同一部法在多个座位各说一遍）。两条结构律：**一部法只在一个座位说**；**工具观察文本只携带世界事实 + 指回法条座位，永不携带可转述的言语草稿**（被复述的法 = 模型的言语草稿，必被 paraphrase 进回复）。

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (solo or via assistant). Core positioning = **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their personal IP — not a self-serve media tool, not "viral short-video clips".

- **Target & input**: 知识专家带素材的模糊目标。**输入不止"演讲"** —— 会议/报告/播客/纯文字稿+照片/幻灯片都可以。
- **Channels**: LinkedIn, 机构站, 邮件 newsletter。**Multi-output 是能力非承诺**：用户点名什么生成什么，承诺句 = "the user names it, the agent makes it"——打包式「一输入全套出」文案永禁；多语言是入场券（FR/DE/ES/IT/EN 等）。
- **GDPR / EU 驻留** = 卖点但对外文案保持「ready 角度」，合规实装后改写。
- **Dual track 命名**（NAMING N-25）：对内 = **agent**；对外 = **assistant / 助手**，"agent" 永不出现于英文文案（zh 用品类句「你的自媒体Agent团队」=品牌妥协，待 N-25 修订）；角色隐喻（运营官/操盘手/班子）禁（N-24）。
- **Copy doctrine**（论证 → STRATEGY §5）：plain & factual。禁资产话术（"knowledge assets" 否）/ 膨胀隐喻（"bigger stage" 否）/ 审批机械化（"You review. It publishes" 否）；身份从 expertise 出发，**不称用户 influencer / creator / 网红**；承诺句 = "You focus on your craft; we handle the rest."（与 hero "We do the rest" 同源）；**禁 MCN / 代运营 / 变现话术**（我们是 agent 不是 agency，不做变现承诺）；**CTA / 控件 = 直给动词 + 具体名词**（"上传你的原视频"/"生成"），禁产品黑话与造词；写作风格 = 风格/style，"voice" = 音频本义（声纹/dub）；Sparkles icon 禁，assistant 视觉 = `LogoMark`；studio home hero = 品牌锁up + 品类句（剩定位归 landing）。**配方卡素材需求署名在左 Input 小节**（`recipes.<id>.inputTitle`/`inputHint`），上传区文案通用（`recipes.inspect.dropzone`）。
- **用户到来即彷徨**（行为规格 → CHAT_ARCH §3.3）：每步都答「下一步是什么」——开始前配方卡接住 / 计划中确认 dock 接住 / 完成后结果画布闭环接住（ADR-041）。agent 顾问姿态四律：① **每轮一问、每问可一词答、散文恒带默认路径**（ADR-052 判词 5；只问用户能答的——听众/目的，参数由配方与默认值吸收）② 带理由纠偏（给替代方案，禁静默拒绝）③ 成功定义随计划 ④ 永给唯一下一步；不做职业/变现咨询（诊断是为了更快给出对方案，不是把生产工具变顾问）。
- **闭环优先于卡片数量**：卡点亮（能力真 + 预览真）≠ 通路；「Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产」全通才算；对外叙事单位 = "完全通路"。
- **闭环叙事与身份命名**（ADR-037 / NAMING N-27）：用户侧闭环 = **管理 IP → 产生 outputs → 发布**，en 用 "personal brand / thought leadership"，zh 用 "IP / 自媒体"；产品内身份模块 = **人设**（多实例扁平：工作号/生活号）。**身份根升格为「定位（Positioning）」已拍板**（ADR-042，目标架构 → `docs/POSITIONING.md`，生产层闭环后动工）——人设收窄为定位的表达分区，渠道/选题/素材挂定位根，品牌/IP 留营销承诺层；落地前代码层只 `persona`。

前端文案 / 工具网格 / 示例占位围绕 **content / LinkedIn / multi-language**，避开 "TikTok / viral / trending"。

## Internationalization (i18n)

### Dictionary Structure
- Source language is English: `apps/web/src/lib/i18n/locales/en.ts` is the source of truth and exports the `Resources` type.
- Chinese `zh.ts` must satisfy `zh: Resources`, so missing keys will be caught at the TypeScript level.
- **Baked-example labels (`recipes.materials.*`) are UI copy, not content**: name them in the SYSTEM language like every other label — en: "Chinese dub", zh: "中文配音". Never use each language's own name ("Doublage français" in en.ts is a bug class). (Exception that is NOT UI copy: landing demo-card contents and the `channels.languages` native-name list are marketing content by design.)

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
- **Never switch language after hydration**: lazy route boundaries hydrate after root effects have run, so a post-hydration `changeLanguage` makes their SSR'd text mismatch. Language changes come only from explicit user action (`setLocale`) after mount.

## Theme

- Defaults to following the system `prefers-color-scheme`.
- **Defaults to dark treatment**: on first visit or when the preference is `system`, render in dark mode first to avoid SSR / hydration flicker.
- After the user manually switches, write to `localStorage` with the key `repurposer-theme` (values: `system|light|dark`).
- **FOUC prevention**: `__root.tsx` contains a blocking inline script in `head` that reads `localStorage` before the first paint and adds / removes the `dark` class on `document.documentElement`. Do not remove this script.
- **Transition animation**: View Transition API circular expansion reveal (clip-path scales from click position); falls back to direct switching when unsupported or `prefers-reduced-motion`. The default cross-fade is disabled in CSS:
  ```css
  ::view-transition-old(root),
  ::view-transition-new(root) {
    animation: none;
    mix-blend-mode: normal;
  }
  ```

## Routing

- `/` is the **public landing page** (no sidebar); the sidebar studio lives under the `_app` **pathless layout route** (`src/routes/_app.tsx` holds `SidebarProvider`/`AppSidebar`/`SidebarInset`). `__root.tsx` keeps only providers + `Toaster`.
- The studio home is `/home` (`_app.home.tsx`); other app pages keep flat URLs (`_app.projects.tsx` → `/projects`, `_app.projects.$id.tsx` → `/projects/$id`, …).
- `AuthProvider` public paths: `/` only. Everything under `_app` sits behind the login wall automatically.
- **Dynamic links**: TanStack Router enforces literal type constraints on `to`:
```tsx
<Link to="/projects/$id" params={{ id: project.id }} />
// Incorrect: <Link to={`/projects/${project.id}`} />
```

## SSR Safety

- `window`, `document`, `localStorage`, `matchMedia`, etc. can only appear inside `useEffect`, event handlers, or the anti-FOUC inline script.
- `useState` initial values must be consistent between server and client, otherwise hydration errors will occur.

## Persona Skin Block (brand)

**ADR-038**：皮肤 = 人设 `brand` JSONB 块（caption 字号/字体/颜色/位置 + style-preset + 标题 + intro/outro + 音乐 `musicId`/`musicMood`/`musicEnabled`）；无独立 brand template 模块，`/brand-template` 307 → `/personas`。**`brand: null` = 系统默认皮肤**。编辑 = 人设页第三 tab「皮肤」（左设置 + 右 Remotion `<Player>` 实时预览，与产物像素级一致，`components/persona/skin-editor.tsx`）；存 = PUT 只更 `brand` 块，「恢复默认」写 `null`。片头尾媒体 = `POST /personas/{id}/media(/upload-url)`（随人设删）。**`logo` 键无渲染消费路径，不入 UI**。**Craft/format 字段非人设列**：`aspect` / `fillMode` / `captionEnabled` / filler removal / 音乐默认 = 配方注册表 + 计划默认；写作风格不在人设表列，住 风格六件 + `guidelines`。烘焙路径见 `MODULE_ARCHITECTURE.md §7` / `brand.py`（`brand_ref` = persona id，clip-spec 契约不变）。**`brand_template_id` 不出现在任何请求载荷**——composer 单身份控件，`persona_id` 经首条 chat 消息送达并在 `create_run` 钉入 `run.context.persona_id`。

## Persona Voice Block (voice)

音频绑定 = 人设 `voice` JSONB：`{kind:"cloned",voice_id,sample_asset_id}` | `{kind:"stock",stock_id}` | `null` = Auto（dub 用项目自身素材声音）。**`voice` 词独占音频本义**（NAMING N-27/N-28），文风在风格六件 + `guidelines`。编辑 = 人设页 Voice 卡（`components/persona/voice-section.tsx`）展示当前绑定 + 上传/换样本（样本 = persona 素材 `type=voice_sample`），存 = PUT 只更 `voice` 块；文案只陈述绑定状态、不许诺效果。STOCK_VOICES 注册表 / 系统音色试听 / dub 链优先级改造 = 缓做项。

## Video Editor & Rendering (Vertical Shorts)

**clip-spec 是唯一契约**（JSON 字段级 + 轨道模型 ADR-044），**renderer = 可替换黑盒**（首推 Remotion）。详见 `docs/RENDERING.md`（§3 字段契约 / §6 渲染层 / §7 替换路径 / §8 现行轨道契约）与 `docs/VIDEO_EDITOR.md`（编辑器形态 + L2/L3 范围纪律）。**泄漏禁令**：Remotion / React 概念永不入 clip-spec。

**L3 铁律（每项否决不变）**：禁多轨时间线 / 层合成 / 转场效果 / B-roll 库 / 自动人脸重取景 / 客户端引擎——专业需求明确导出剪映 / Premiere。字幕样式仅枚举，不开放自由版式；styles 限定 CSS + libass 都能表达的子集（保 FFmpeg 替身成本）。硬前提：**多语言 ASR 词级时间戳 + 对象存储流式 / 寻址**（ADR-024）。

## Error Handling & Toasts

所有 API 走 `apps/web/src/lib/api.ts:apiFetch`：默认非 OK + 网络失败 → 全局 sonner 带 `detail`；401 清登录态开 LoginDialog（非抑制 toast）；成功静默。`toast: false` / `toast: "..."` / `toast: {success, error}` 三档 per-call 控制。`<Toaster />` 挂在 `__root.tsx`（项目自建 `ThemeProvider`，非 next-themes）。**Auth 失败也走 toast，无双轨**——LoginDialog 不 `{toast:false}` 抑制、不自养 `error`，发验证码冷却/验证码错/网络失败同进全局 toast（form 内清空/复位焦点属输入复位非错误显示）。动作反馈禁内联 `<p>`；页面级 load-failure 占位可内联但 `toast: false` 防双报。错误形态 / 状态码约定 = `docs/API.md §4`。

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

The API test suite was removed because it had drifted from the rapidly changing implementation. Verify changes by running the relevant flow end-to-end instead of relying on a test suite.

**Exception — deterministic pure-function suites** (`apps/api/tests/*_pure.py`): no database, no LLM, no HTTP; sessions are in-memory stubs. They cover adjudication / pure-mapping layers where branch coverage matters and drift risk is low (the wiring door `apply_wiring_ops` + `_fill_key_for_step`, stream extraction, registry ↔ prompt enumeration consistency). If a behavior needs a real transaction or an LLM to verify, it belongs to an e2e run (chat_scenarios), not here. Run: `cd apps/api && uv run --extra dev python -m pytest tests/<file> -q`.

**Prompt authoring law**: prompt files carry ONLY current-state law. Model-facing text never names dates / ADR numbers / batch or incident labels / retired forms — every law reads as if it was always the law. `{# #}` comment headers stay one-anchor-line: what the file is + operational constraints (include placement, mirror contracts) — no incident narratives; history lives in git and `docs/DECISIONS.md`. Prose-field schema changes still carry the two typewriter teeth (null-read tolerance + settled-prose pacing).

**Pre-deploy prompt gate (ADR-071 T2)**: any change touching the prompt surface (`app/prompts/chat/`, `chat/prompts.py`, registry catalog lines) must pass `cd apps/api && uv run python scripts/prompt_gate.py` before deploy — three probes with absolute thresholds (start_run / slot handshake / rootless-wish ask_user), `--provider` parameterized over the PROVIDERS registry (native-tool providers only — the gate probes the tool-loop line). On failure: re-run once (provider drift exists even at threshold), then bisect with the A/B instrument `scratch/router_ab_probe.py` — never retune thresholds to make a regression pass. Full pre-deploy ritual: pure pytest → prompt gate → full `scripts/chat_scenarios.py`.
