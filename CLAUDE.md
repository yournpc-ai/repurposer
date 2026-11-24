# Repurposer — Claude Collaboration Guidelines

> 通用视觉与交互使用 affectUI Clean，组件使用见 `docs/UI_GUIDELINES.md`，消息与回放行为见 `docs/CHAT_ARCHITECTURE.md`。

> 文档卫生：本文与 docs 只承载**现行法**（现在时直陈）。只保留一个更新日期、当前规则、必要理由与开放事项；不记录拍板过程、翻案链、退役史或逐轮交付报告。**不创建或维护文档归档，不复制旧版本留底**。被替代内容直接删除，规则就地更新；仍有效的需求、未验证项与阻塞必须留在当前文档。

## 默认阅读与收尾协议

以下规则每个新会话自动执行，无需用户重复提醒；compact 后沿当前任务与交接继续，不重新通读项目历史。

1. 先读本文与 `docs/PROGRESS.md` §0，再按本次任务选合同。先用 `rg -n '^#{1,4} ' 文件` 或关键词定位标题，再读取相关章节及必要上下文；不批量 `cat` 大型文档，不为“了解项目”遍历整个 docs。
2. 局部修复只读相关合同、约束、风险与验收项。所有 Video Project 阶段施工先读 `docs/VIDEO_PROJECT.md` §0 的长期创作方针，再读当前批次；接手整个模块、排期或发布评估时才读该模块完整状态与欠账，不要求全文通读。
3. 只有当前契约不清、证据缺失或规则冲突时，才定点查相关源码、测试和当前运行证据；需要追溯取舍时再查对应 ADR。引用不是递归阅读指令；确认实现位置、适用约束与验收条件后即进入工作，不继续扩大阅读范围。
4. 收尾修改既有事实源：状态覆盖旧快照，合同更新剩余范围；保留未完成需求、未验证项和上线阻塞。普通修复不新增 ADR、会话流水账或重复总结文档；历史叙述与已失效合同直接删除，不另建 archive、事故纪要、验收日志副本或历史索引；删除前把仍有效的开放事项并入当前事实源。
5. 删除 scratch / 旧合同前逐份核对独有语义：未完成需求、负面禁令、标识符、操作数值、迁移资源条件、真实验证边界与仍存活的引用都必须有当前家。验收看“叙事已删、规则仍保留”的 diff，不以历史关键词清零为目标；研究证据与可执行诊断工具不因日期或事故编号删除。
6. compact 交接只保留目标、当前结论、相关文件、已做/未做与下一步；无需重述历次事故。以上阅读节制不能省略本次变更适用的安全、授权、数据与并发约束。

## Key Docs

**固定入口只有两层**：先读本文与 `docs/PROGRESS.md` §0，再读当前任务的状态/合同。随后只读下表命中的具体章节；完整导航与文档职责见 `docs/README.md`。不创建历史文档库；排障需要证据时查当前代码、测试与运行数据。

- **当前状态 / 排期**：`docs/PROGRESS.md` §0 是唯一事实源；局部任务可以维护实施状态，但不得复制全局排期。
- **Video Project**：项目、作品、版本与唯一内容写口读 `docs/VIDEO_PROJECT.md` §0、§8 与命中章节，目录契约见 §12。当前主线施工合同读 `docs/tasks/batch2-multiscene-skill.md`（I8 基础剪辑已阶段封板，见 `docs/tasks/i8.md`）。当前优先级见 PROGRESS §0。
- **模块 / 表 / 队列 / 代码地图**：`docs/MODULE_ARCHITECTURE.md` §4（表归属）、§5（跨模块规则）、§7（代码地图与队列）；新表、新模块、新认领源必须登记。
- **Studio UI**：`docs/UI_GUIDELINES.md` 的相关组件/布局章节；只有改 chat 行为时才同时读 CHAT_ARCHITECTURE。
- **Chat、多轮与用户约束**：读 `docs/CHAT_ARCHITECTURE.md` 和 `docs/tasks/new-agent.md`。
- **Agent、原生工具与后台作业**：读 `docs/AGENT_ARCHITECTURE.md`，费用与结算另读 `docs/BILLING.md`。
- **Rendering**：`docs/RENDERING.md` 管 video-spec、渲染、上传、围栏与交付。作品结构见 VIDEO_PROJECT，编辑器交互见 VIDEO_EDITOR。
- **Billing / credits / configs**：`docs/BILLING.md` 对应扣费、报价或钱包章节；守卫线任何档都不能被 auto 绕过。
- **Payments / Stripe / 充值**：长期架构、凭据/部署、订单字段与 webhook 规则读 `docs/PAYMENTS.md`；首批一次性积分充值施工与验收读 `docs/tasks/stripe-credit-topup.md`。
- **音乐 / UI 文案以外的专门子系统**：按 `docs/README.md` 索引进入对应文档，不从 CLAUDE.md 复制第二份规范。
- **ADR**：在 `docs/DECISIONS.md` 按主题索引和编号定点阅读。普通 bug 修复、字段接线、测试结果和会话汇报不新增 ADR；只有架构边界、产品语义或关键取舍变化才新增独立决策。
- **任务合同**：`docs/tasks/` 只保留仍有实施或验收欠账的当前合同；已完成的长期约束并入对应母文档，剩余验收归当前状态，其余过程内容删除，不留跳转墓碑。

每份文档头部注明其状态；`docs/README.md` 标注的是文档角色，不代表其中所有 PLANNED 内容已经落在 `main`。

## Tech Stack
- Frontend framework: TanStack Router / TanStack Start (React 19 + SSR)
- UI components: affectUI Clean (React 19)
- Styling: Tailwind CSS v4
- Icons: lucide-react (sole icon source)
- Internationalization: i18next + react-i18next
- State: React Context + hooks (no Redux / Zustand in this project)

## 通用 UI

新页面与通用控件使用 `apps/web/src/components/ui/*-clean.tsx` 中的实际导出和 Props。Clean 控制尺寸、动效、状态与弹层行为，`apps/web/src/styles.css` 提供明暗主题值。页面使用现有路由和 Context 接入真实数据。组件来源与剩余旧消费者见 [迁移清单](docs/tasks/affectui-evidence/README.md)。

### Icons

Use lucide-react for application icons. Third-party logos and the existing brand mark retain their own geometry.

## Studio 界面约定

共享 Composer、预览与媒体查看控件使用 Clean 的尺寸、边界、交互和焦点样式。媒体选区坐标、帧时间、字幕字号草稿与缩放值由各自的领域组件提供。Studio 页面沿用现有 Shell 的内容区和滚动容器。新增导航入口同步 `nav.*` 翻译。通知入口继续使用当前 Studio chrome 的位置。

## Composer、Chat 与产品定位

Repurposer 是通过自然语言操作持久视频工程的专业 AI 剪辑师。用户提供目标与素材，Agent 定位对象、执行编辑、观察并续改。保留 MentionEditor、附件、显式 Skill、原问题、费用授权、Stop 和按版本回放。仅在必要决定阻塞时提问。分镜按需展示，历史交付始终钉住原 Output。通用 UI 用 Clean，布局用 Tailwind，过渡用 Motion。

正式产品能力按 Chat-Origin End-to-End 验收：同一真实 Chat 从 Provider 工具调用追到不可变版本、实际播放或交付，再验证续改与恢复。隔离测试只证明测到的边界。施工先按 [Agent 总合同](docs/tasks/new-agent.md) 扩展现有 ToolLoop。视觉来源与原生 `MotionBlockObject` 边界见 [作品模型](docs/VIDEO_PROJECT.md)，共享纯 TS 音效引擎与声音合同见 [声音合同](docs/MUSIC_ARCHITECTURE.md)，当前主线验收见 [Batch 2 多幕与 Skill 合同](docs/tasks/batch2-multiscene-skill.md)。禁止恢复 Plan、DAG 或 Graph 创作协议，也不为动效和音效另建执行、播放或交付链。

## Internationalization (i18n)

### Dictionary Structure
- Source language is English: `apps/web/src/lib/i18n/locales/en.ts` is the source of truth and exports the `Resources` type.
- Chinese `zh.ts` must satisfy `zh: Resources`, so missing keys will be caught at the TypeScript level.
- **Baked-demo labels (`recipes.shelf.demos.*`) are UI copy, not content**: name them in the SYSTEM language like every other label — en: "Chinese dub", zh: "中文配音". Never use each language's own name ("Doublage français" in en.ts is a bug class). (Exception that is NOT UI copy: landing demo-card contents and the `channels.languages` native-name list are marketing content by design.)

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

历史 Persona 深链仍可编辑 `brand`、预览皮肤并保存，`brand: null` 使用系统默认。保留片头尾素材、曲库选择、归属与删除保护。Home 的普通剪辑示例仅预填文字，首条消息使用用户实际提交的素材及显式 Skill。Persona、Publication 和旧作品的处置见 [I8 §15](docs/tasks/i8.md#15-现行处置与交付)。

## Persona Voice Block (voice)

音频绑定 = 人设 `voice` JSONB：`{kind:"cloned",voice_id,sample_asset_id}` | `{kind:"stock",stock_id}` | `null` = Auto（dub 用项目自身素材声音）。**`voice` 词独占音频本义**（NAMING N-27/N-28），文风在风格六件 + `guidelines`。编辑 = 人设页 Voice 卡（`components/persona/voice-section.tsx`）展示当前绑定 + 上传/换样本（样本 = persona 素材 `type=voice_sample`），存 = PUT 只更 `voice` 块；文案只陈述绑定状态、不许诺效果。STOCK_VOICES 注册表 / 系统音色试听 / dub 链优先级改造 = 缓做项。

## Video Editor & Rendering

`video-spec` 是唯一在线渲染入口，消费声明式原生对象（含原生 `MotionBlockObject`）与固定媒体；共享 `@repurposer/video-remotion` 同时驱动服务端 Remotion 渲染与 Web `@remotion/player` 预览，原生支持透明叠层且无跨平台沙箱阻塞。`GeneratorObject` 专用于上游烘焙/生成固定媒体（`draw-2d`、`image-generation` 与未来 Linux 隔离下的 `remotion-project`）。音效合成由洁净室共享纯 TS 包 `@repurposer/sound-engine` 驱动前后端同构产出 48 kHz 立体声 WAV。薄渲染核心 C 保留可行性研究结论，暂不替换生产 Renderer。原生文字、字幕和音频保留可编辑身份。详见 `docs/RENDERING.md`、`docs/VIDEO_PROJECT.md` 与 `docs/MUSIC_ARCHITECTURE.md`。


## Error Handling & Toasts

所有 API 走 `apps/web/src/lib/api.ts:apiFetch`：默认非 OK + 网络失败 → 全局 sonner 带 `detail`；401 清登录态开 LoginDialog（非抑制 toast）；成功静默。`toast: false` / `toast: "..."` / `toast: {success, error}` 三档 per-call 控制。`<Toaster />` 挂在 `__root.tsx`（项目自建 `ThemeProvider`，非 next-themes）。**Auth 失败也走 toast，无双轨**——LoginDialog 不 `{toast:false}` 抑制、不自养 `error`，发验证码冷却/验证码错/网络失败同进全局 toast（form 内清空/复位焦点属输入复位非错误显示）。动作反馈禁内联 `<p>`；页面级 load-failure 占位可内联但 `toast: false` 防双报。错误形态 / 状态码约定 = `docs/API.md §4`。

## Task Queue (Backend)

长任务与可重试生产链（ASR / 渲染 / 生成 / 发布）一律入 Postgres 队列（`FOR UPDATE SKIP LOCKED`），由独立 `python -m app.worker` 认领；**禁 FastAPI BackgroundTasks**、禁跨模块直调 service 执行重活。当前请求内联例外仅限既有 `POST /music/generate`、cover、revise、translate-captions、dub 路由，不得推广为新增重活的先例。新增 processor → `app/pipeline/asset_processing.py:PROCESSORS`；新增认领源 → worker claim loop。详见 `MODULE_ARCHITECTURE.md §5 规则 1 / §7.2`（ADR-017 + ADR-039 队列与重试机制）。

## Commit Messages
- Use conventional commits, for example:
  - `feat: add theme toggle with view transition`
  - `fix: correct SidebarMenuButton render usage`
  - `docs: update i18n and theme conventions`

## Database Reset

`apps/api/scripts/reset_db.py [--yes] [--db-only|--storage-only]` 清部署：dry-run 默认（印目标），`--yes` 落地。**保留前缀**：`demo/`（landing + 配方卡营销资产，内容寻址；生产永不再生）+ `music/`（Shotcraft 五首平台策展曲目；`scripts/import_library_music.py` 只导入缺失对象，启动 reconcile 零配额补行）。**生产慎跑**——dry-run banner 先看。启动前核对数据库目标，显式运行 Alembic 迁移；服务启动检查 revision，再进行音乐 reconcile；人设 `brand: null` 走系统默认皮，不布品牌种子；栈不布 demo 项目，`SKIP_DEMO_SEED` 是死旗，不依赖。

## Testing

测试体系按四层 Chat-Origin 金字塔组织（完整规范见 `docs/TESTING.md`）：**Layer 0 纯合同与 Py↔TS 跨运行时一致性**（`apps/api/test/unit/`、`packages/*`）、**Layer 1A Chat-Origin 集成套件**（`apps/api/test/chat_origin/`，经真实 ASGI `/api/v1/chat` + 一次性 PostgreSQL）、**Layer 1B 基础设施与迁移一致性**（`apps/api/test/infra/`）、**Layer 2 Web Studio 与 Render 服务**（含 EN↔ZH i18n 一致性门禁），以及按需运行的 **Layer 3 真实视听评测 CLI**（`apps/api/scripts/eval_chat_e2e.py`）。内部 helper、提示词文案与实现形态不另立永久测试。

**部署前检查**（统一经根目录 `Makefile` 运行，按改动面全绿才可部署）：

1. 快速纯合同门禁：`make test-fast`（Layer 0 API `unit` + `video-spec` + `sound-engine` + Web `tsc`）。
2. Chat-Origin 与全量 API 确定性测试：`make test-chat` / `make test-api`（不调用真实模型、不执行付费制作；会话级一次性 PostgreSQL + 每测毫秒级表清理）。
3. Web 与 Render：`make test-web`（`tsc` + Vitest 含 i18n parity）、`make test-render`（`tsc` + Node 测试）；整仓确定性总门禁 `make test-all`。
4. 真实视听评测（按需授权）：`make eval-chat SCENARIO=motion_block_promo`（独立临时 PostgreSQL + `local://` 存储，产出 `eval_scorecard.json` 与 `EVAL_REPORT.md`）。

真实浏览器交互、最终动态视听、生产环境与公开发布仍需对应人工验收；确定性测试或评测脚本通过不能替代这些证据。失败先归因机制，禁止为放行削弱断言。运行与故障处置细则归 `docs/TESTING.md` 与 `docs/VERIFICATION.md`。

诊断脚本不是部署门禁，其读数不能替代上述测试或真实验收。

**Prompt authoring law**: prompt files carry ONLY current-state law. Model-facing text never names dates / ADR numbers / batch or incident labels / retired forms — every law reads as if it was always the law. `{# #}` comment headers stay one-anchor-line: what the file is + operational constraints (include placement, mirror contracts) — no incident narratives; history lives in git and `docs/DECISIONS.md`. Prose-field schema changes still carry the two typewriter teeth (null-read tolerance + settled-prose pacing).
