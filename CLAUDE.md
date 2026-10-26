# Repurposer — Claude Collaboration Guidelines

> 协作规范与高频硬律。两个设计系统的**全文**各有其家：视觉/交互形态 = `docs/UI_GUIDELINES.md`；chat/画布行为 = `docs/CHAT_ARCHITECTURE.md`。本文只载最高频违规的硬律与指针——动一个子系统时读其**相关章节**，不要求通读全部规范或历史。
>
> 文档卫生：本文与 docs 只承载**现行法**（现在时直陈）。只保留一个更新日期、当前规则、必要理由与开放事项；不记录拍板过程、翻案链、退役史或逐轮交付报告。**不创建或维护文档归档，不复制旧版本留底**。被替代内容直接删除，规则就地更新；仍有效的需求、未验证项与阻塞必须留在当前文档。

## 默认阅读与收尾协议

以下规则每个新会话自动执行，无需用户重复提醒；compact 后沿当前任务与交接继续，不重新通读项目历史。

1. 先读本文与 `docs/PROGRESS.md` §0，再按本次任务选合同。先用 `rg -n '^#{1,4} ' 文件` 或关键词定位标题，再读取相关章节及必要上下文；不批量 `cat` 大型文档，不为“了解项目”遍历整个 docs。
2. 局部修复只读相关合同、约束、风险与验收项。接手整个模块、排期或发布评估时才读该模块完整状态与欠账；视频目标与施工合同也不是每次全文必读。
3. 只有当前契约不清、证据缺失或规则冲突时，才定点查对应现行 ADR 与代码、测试或当前运行证据。引用不是递归阅读指令；确认实现位置、适用约束与验收条件后即进入工作，不继续扩大阅读范围。
4. 收尾修改既有事实源：状态覆盖旧快照，合同更新剩余范围；保留未完成需求、未验证项和上线阻塞。普通修复不新增 ADR、会话流水账或重复总结文档；历史叙述与已失效合同直接删除，不另建 archive、事故纪要、验收日志副本或历史索引；删除前把仍有效的开放事项并入当前事实源。
5. 删除 scratch / 旧合同前逐份核对独有语义：未完成需求、负面禁令、标识符、操作数值、迁移资源条件、真实验证边界与仍存活的引用都必须有当前家。验收看“叙事已删、规则仍保留”的 diff，不以历史关键词清零为目标；研究证据与可执行诊断工具不因日期或事故编号删除。
6. compact 交接只保留目标、当前结论、相关文件、已做/未做与下一步；无需重述历次事故。以上阅读节制不能省略本次变更适用的安全、授权、数据与并发约束。

## Key Docs

**固定入口只有两层**：先读本文与 `docs/PROGRESS.md` §0，再读当前任务的状态/合同。随后只读下表命中的具体章节；完整导航与文档职责见 `docs/README.md`。不创建历史文档库；排障需要证据时查当前代码、测试与运行数据。

- **当前状态 / 排期**：`docs/PROGRESS.md` §0 是唯一事实源；局部任务可以维护实施状态，但不得复制全局排期。
- **Video Project / Film/MG**：目标层级 = Project/Chat → Composition → CompositionVersion，同 Chat 多影片、全局 @ 引用；内容唯一写口 = `apply_composition_edits`，仍未实施。新架构施工先读 `docs/VIDEO_PROJECT.md` 的命中章节（目录/新旧代码处置唯一合同 = §12），再读 `docs/tasks/video-project-implementation.md` 当前阶段与验收；现状查 RENDERING 与实际代码，有效视听/创作要求归 VIDEO_PROJECT §15，不再维护旧 Film 施工三件套。
- **模块 / 表 / 队列 / 代码地图**：`docs/MODULE_ARCHITECTURE.md` §4（表归属）、§5（跨模块规则）、§7（代码地图与队列）；新表、新模块、新认领源必须登记。
- **Studio UI**：`docs/UI_GUIDELINES.md` 的相关组件/布局章节；只有改 chat 行为时才同时读 CHAT_ARCHITECTURE。
- **Chat / dock / 画布**：`docs/CHAT_ARCHITECTURE.md` 按改动面选读——工具与 plan path §3、SSE/活动/打字机 §8、修订 §9、禁令 §12。活动行与 WorkSegment 改动脉冲 §8.6～§8.7 的现行规则。
- **Chat 意图 / 多轮 / brief**：`docs/DIALOG_WORKFLOW.md` §2、§4 + CHAT_ARCHITECTURE §3；不读旧交互迁移报告代替现行法。
- **Agent / tools / graph**：`docs/AGENT_ARCHITECTURE.md` §2（四层地图）、§4（Graph）、§5（Harness）、§7（工具包）；报价另读 §8。
- **Rendering / spec families**：`docs/RENDERING.md` §1、§3、§6、§8；新视频内容与版本契约读 VIDEO_PROJECT，编辑器交互另读 `docs/VIDEO_EDITOR.md`。clip-spec 与 film-spec 是平级家族，renderer 概念不得泄漏进任一 spec。
- **Billing / credits / configs**：`docs/BILLING.md` 对应扣费、报价或钱包章节；守卫线任何档都不能被 auto 绕过。
- **定位 / 人设 / 渠道 / 选题 / home**：`docs/POSITIONING.md`（已拍板未实施）与当前任务合同；代码层落地前仍只使用 `persona`。
- **音乐 / UI 文案以外的专门子系统**：按 `docs/README.md` 索引进入对应文档，不从 CLAUDE.md 复制第二份规范。
- **ADR**：在 `docs/DECISIONS.md` 按主题索引和编号定点阅读。普通 bug 修复、字段接线、测试结果和会话汇报不新增 ADR；只有架构边界、产品语义或关键取舍变化才新增独立决策。
- **任务合同**：`docs/tasks/` 只保留仍有实施或验收欠账的当前合同；已完成的长期约束并入对应母文档，剩余验收归当前状态，其余过程内容删除，不留跳转墓碑。

每份文档头部注明其状态；`docs/README.md` 标注的是文档角色，不代表其中所有 PLANNED 内容已经落在 `main`。

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

- **小圆角**：默认 `rounded-md` / `rounded-lg`。`rounded-full` 仅四例外：真圆形图标钮 / 状态徽章红点 / home composer 钉底单行 stadium 条 / gallery 筛选 pill 行。`Badge` 用于元数据恒 `className="rounded-md"` 覆盖。
- **同排控件 `h-9` 中心线对齐**；pill / trigger 文字不加粗。
- **浮层选型**：列表单选 = `DropdownMenu`；内联动作面板 / 多控件设置面板 = `Popover`；表单纯下拉 = `Select`。
- **纵深**：卡 = 基座自带 `ring-foreground/10` 发丝线 + 填充阶浮起；**禁可见描边**（`border-border` / `ring-border` / 强于 /10 的 `ring-foreground/*`）；in-flow 面（卡/composer/媒体 tile）**永不带 shadow**，shadow 只属于浮层；填充优先——fill 已区分就零环零边。
- **灰梯 token 阶**，禁临时 alpha 填充（`bg-muted/50` / `bg-background/60` 等）；hover 一律 `bg-accent`（dark 是半透白纱不是亮阶），禁逐实例硬编码 hover 色值；带 `dark:bg-*` 的元素必须显式配 `dark:hover:bg-accent`。
- **文字三档**：`foreground` / `muted-foreground` / `meta-foreground`（`text-meta` utility）。
- **浮层一律 `overlay-surface`**（styles.css 共享冰霜配方）；overlay chrome 只用 Dialog primitive，**禁手写 backdrop**；视口锚浮层 portal 到 `document.body`。
- **颜色只用 shadcn token**，禁硬编码色值。
- **布局**：`_app` 页面 `flex-1`，禁 `min-h-svh`/`min-h-screen`（home = `h-svh` + 单内部 scrollport 例外；landing 页合法）；页面主体放 `SidebarInset`。
- **侧栏**：导航用 `SidebarMenuButton` + `render={<Link />}`；图标 `h-4.5 w-4.5`；新增入口同步 `nav.*` i18n；**通知铃 = 内容区右上角唯一浮动 chip**，该角全站保留；无全局 AppHeader。（浮动 chip 法适用 md+；<md chrome 全收编进玻璃 `MobileHeader`——品牌/Projects/裸铃/头像 AccountConsole，浮动触发器与浮动铃双撤，侧栏抽屉不再可达。）
- **Dot grid = FlowView 签名，只此一面**；home 与其余任何面禁用。

## Composer / Chat 行为硬律（全文 → `docs/CHAT_ARCHITECTURE.md`）

- **Agent 北极星（ADR-088/089/117）**：Agent 持续生产与修订用户可理解的项目产物；不编译、不直接执行 workflow 内部语言；付费执行只从已呈现且已授权的范围开始（授权 = 制作意图在场 +（常驻 auto 档默认或明示确认），守卫线以上恒问——ADR-139）。**确认只有两种**：执行确认（`confirm_execution`）与费用确认（`confirm_credits`），users.settings 两键默认全 auto，唯一座位 = SettingsDialog「助手」section——composer/dock 控制条永不出现确认偏好控件。
- **composer 零意图识别**：send = spinner（建项目 + 上传素材）→ 直达 `/projects/$id`（canvas + ChatDock 两形态机）。**`POST /chat` 是唯一意图面**——永不新增第二意图入口（如专用 `/intent` 端点）。
- **Prompt 必填**：空提交本地 toast 拦截。纯 prompt 发送不建资产；intent router 判定消息是「用户自己的内容」还是「请求」（LLM 判定，**禁长度启发式**），是内容则提升为 transcript 资产（`create_transcript_asset_from_text`）；无资产无贴文的生成请求得到要素材的回答，永不无中生有计划。
- **中途上传走 dock attach 钮**：选中文件暂存为输入组内生命周期 chips（uploading → done/error，× 删且删资产）；**只有 send 钮消费它们**，骑回合作消息 `attachments`（持久化，刷新重渲染）。选文件自身永不发送；附件单发合法；空消息永不自动作答 docked checkpoint。
- **clips need media**：server 侧双重 enforce——intent router 对纯文本输入排除 clips；`create_run` 出生地镜像 422。
- **打字机律（绝对规范，任何改动不得违背）**：agent 一切言语以打字机节奏出现，**整段瞬移永禁**。两条结构牙：① 散文字段入 schema 必带读容忍（null 读为空默认值——一次 schema 拒收 = 被拒迭代 = 永不流式 = 瞬移）；② 零 delta 路径的最后闸门 = 信封到达后散文照样走 typewriter 节拍释放（`paceSettledProse`），dock 等释放排干才落。新增散文通道 / 改散文字段 / 加提案工具时两牙同批检查（规格 = CHAT_ARCH §8.6）。
- **展示文案二源律（ADR-058）**：用户可见命名类文案只有两个合法来源——① LLM 建图时命名（proposal 的 `name` 字段，null/空读容忍）；② 世界自证（产物徽标 / 节点状态 / 真实数字）。**冻参模板永禁**。**手改撤名**：计划卡任何手改即清空 `name`，回退读当前参数的诚实标签。
- **echo 防编造律（ADR-060）**：回声只回述用户说过的（作品 / 语言 / 数量），**永不发明平台或场所**——a post is just a post until the user names where it lives；渠道合法来源 = 用户点名或渠道授权，永不是默认值。
- **起始句 = LLM 言语（ADR-093）**：start_run 回合先说话再调用，开工句由模型说出并落库为普通 assistant 行；chrome/模板替说全形态永禁。
- **口头确认律（ADR-092，ask 档法律）**：ask 档下方案 dock 后恒等确认——echo 收尾恒为一句朴素的方案判断问句（一词可答），口头 yes 与 Start 钮都化为普通用户消息走 sendChat，下一轮 LLM 到 start_run（同一机器，按钮不直启 run）；收尾永不带「成片出来后再调」式交付后修订预告。**auto 档（默认）无确认拍**——方案呈现即开工，同回合 propose→start_run 是标准道（ADR-117）；但 auto 只免批准拍、**永不创造制作意图**（ADR-139）：dock 生于无制作请求的消息（纯修改/「先给我看方案」/讨论）任何档都等用户发话，`production_intent` 出生事实随六个 dock 工具入参，缺断言=安全侧挂起（Start 钮常驻）；开工确认**复述当前累计方案**（明说要求/已落实改动/建议未选项/未清项——未选项永不称「已确认」，旧版 yes 永不静默授权新稿）；守卫线（`billing.always_confirm_above` / NULL 不可报价族）任何档恒带价问一次。**film 分镜拍（ADR-129/ADR-134/ADR-144）**：分镜设计 = `design_storyboard` 呈现，分镜不是开工也不是方案 dock；fresh compose 首稿/开放重稿默认 review hold ON。**作品首个分镜版本一律先完整呈现并等待用户发话——开场「直接做」、`review_hold=false` 与 auto 都不能同回合开工，`film_presented_message_id` 未持久化时任何 Start 均由 `start.review_hold` 硬拦**。auto 无其他确认债时不显示首稿 approval dock，用户看过后的制作话走普通 sendChat；ask 可显示首稿 dock，Start 钮同样只发送用户消息。下一轮 LLM 调 `start_run` 才放行；后续版本不继承这个首稿专用确认拍，其余生产授权全走通用设置，新版本闭环目标 = `docs/VIDEO_PROJECT.md` §2/§8/§15，施工与实际验证状态 = `docs/tasks/video-project-implementation.md`；当前旧链事实查代码与 RENDERING。
- **Chat / Run 工作段一行两态**：chat 的 now line / Thinking 与工作记录折叠行、run 的制作 / 整理结果 / Worked 同由 `components/chat/ActivityStream.tsx:WorkSegmentRow` 承载；首条 active 从宿主行原位入段，前段打字不得吞掉当前活动；工具完成不收段，首个非空白正文经打字机实际释放或真实终态才原位收成工作记录，busy 时禁「工作了 X 秒 + 另一条 Thinking」。chat live Thinking / 里程碑恒无 chevron 且不可展开，只有收成工作记录后才开放；run 保留可展开的活步骤树，按 RUNNING → REVIEWING → SETTLED 以同一 runId key 原位过渡，terminal 不等于收段，匹配当前 run 的 delivery 首字实际释放才收 Worked，chip 在真实可交付 output 就位后仍等匹配 delivery 首字实际释放或 Worked 收段才挂载，terminal 本身不提前暴露。cancelled 尝试从可见投影退役，不留 ✗ / 删除线，真实 failed 保留一条安静告警；chat 与 run-delivery 各持工作段时钟，互不相加。
- **Mentions**：@-entity chips 随消息 `mentions` 字段送达；注册表架构（前端 `MENTION_REGISTRY` + 服务端解算），已注册 = `asset`（请求族）/ `output`（指认族，钉 id 服务端确定性解出修订目标）。**配方永不是 mention**（配方 = 提示词，卡面预填模板即全部发射载荷）。**Chip 三律**：可见（inline + ×）/ 发送消费 / × 净化。方针全文 = `docs/MENTIONS.md`。
- **修订 = 图变更**：chat 修订骑 `POST /chat` 的 `edit_graph`（wiring 提案）→ `apply_wiring_ops` 唯一写口；卡面 prompt 直改 = 确定性手势走 `POST /projects/{id}/graph/revise`，**dock 零消息**（节点状态周期就是全部反馈），卡面乐观回显永不回闪。
- **画布只读**：FlowView 无 drag/connect/手动布局等结构编辑 API，消费面也没有供背景流程调用的第二套通用相机命令；组件内部 explore 可提供用户 pan/zoom。**程序相机只认用户发起节拍**（draft 图到来整链 fit / 新节点诞生 setCenter；背景 refetch 永不动相机）。
- **Dock 两形态机**（full / panel；移动端恒 full 纯 chat）与保草稿承重结构（单一 root + 恒渲染容器 + 恒定子索引，MentionEditor 跨形态翻转永不 remount）：全文 CHAT_ARCH §1 关键形态事实。
- **chat 修复禁补丁式加禁令（先取证后归因）**：chat bug 的修法 = 先取证再归因到源头，**永不用新增禁令压症状**——上下文盲的禁令（「禁应答粒子」「禁指导用户」式）在合法场景必然拆东墙补西墙。取证 = 回放真实 payload 与机制链：payload 是「代码 × 当时世界状态」的纯函数，无 LLM 台账也能用真实 assemble + 内存拨回世界状态字节级重建。源头只有四类：装配 / 工具观察文本 / 法条座位冲突（两部法打架或适用范围未声明）/ 一法多说（同一部法在多个座位各说一遍）。两条结构律：**一部法只在一个座位说**；**工具观察文本只携带世界事实 + 指回法条座位，永不携带可转述的言语草稿**（被复述的法 = 模型的言语草稿，必被 paraphrase 进回复）。

## Product Positioning

Repurposer serves **European knowledge experts who have content but no time to manage social media** — professors, researchers, lecturers, executives (solo or via assistant). Core positioning = **an AI agent that turns existing material into the content the user names** — guiding people who don't know editing or social media in growing their personal IP — not a self-serve media tool, not "viral short-video clips".

- **Target & input**: 知识专家带素材的模糊目标。**输入不止"演讲"** —— 会议/报告/播客/纯文字稿+照片/幻灯片都可以。
- **Channels**: LinkedIn, 机构站, 邮件 newsletter。**Multi-output 是能力非承诺**：用户点名什么生成什么，承诺句 = "the user names it, the agent makes it"——打包式「一输入全套出」文案永禁；多语言是入场券（FR/DE/ES/IT/EN 等）。
- **GDPR / EU 驻留** = 卖点但对外文案保持「ready 角度」，合规实装后改写。
- **Dual track 命名**（NAMING N-25）：对内 = **agent**；对外 = **assistant / 助手**，"agent" 永不出现于英文文案（zh 用品类句「你的自媒体Agent团队」=品牌妥协，待 N-25 修订）；角色隐喻（运营官/操盘手/班子）禁（N-24）。
- **Copy doctrine**（论证 → STRATEGY §5）：plain & factual。禁资产话术（"knowledge assets" 否）/ 膨胀隐喻（"bigger stage" 否）/ 审批机械化（"You review. It publishes" 否）；身份从 expertise 出发，**不称用户 influencer / creator / 网红**；承诺句 = "You focus on your craft; we handle the rest."（与 hero "We do the rest" 同源）；**禁 MCN / 代运营 / 变现话术**（我们是 agent 不是 agency，不做变现承诺）；**CTA / 控件 = 直给动词 + 具体名词**（"上传你的原视频"/"生成"），禁产品黑话与造词；写作风格 = 风格/style，"voice" = 音频本义（声纹/dub）；Sparkles icon 禁，assistant 视觉 = `LogoMark`；studio home hero = **一行问句**（`home.heroQuestion`）指向 composer——页面唯一目的地是输入框，问句与轮换 placeholder 形成一问一答；品牌名不在 hero 重复，由侧栏锁up / MobileHeader 承载（剩定位归 landing）。配方卡点击唯一归宿 = composer 预填 `promptTemplate`（配方 = 提示词），永不是模板编辑器。
- **用户到来即彷徨**（行为规格 → CHAT_ARCH §3.3）：每步都答「下一步是什么」——开始前配方卡接住 / 计划中确认 dock 接住 / 完成后结果画布闭环接住（ADR-041）。agent 顾问姿态四律：① **每轮一问、每问可一词答、默认路径恒带（散文零宣告）**（ADR-052 判词 5 + ADR-103；只问用户能答的——听众/目的，参数由配方与默认值吸收）② 带理由纠偏（给替代方案，禁静默拒绝）③ 成功定义随计划 ④ 始终给出当前可执行的下一步；全败 run 给确定性原因与至多两个可行选项，成功交付不强制建议 pills 或虚构唯一建议；不做职业/变现咨询（诊断是为了更快给出对方案，不是把生产工具变顾问）。
- **闭环优先于卡片数量**：卡点亮（能力真 + 预览真）≠ 通路；「Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产」全通才算；对外叙事单位 = "完全通路"。
- **闭环叙事与身份命名**（ADR-037 / NAMING N-27）：用户侧闭环 = **管理 IP → 产生 outputs → 发布**，en 用 "personal brand / thought leadership"，zh 用 "IP / 自媒体"；产品内身份模块 = **人设**（多实例扁平：工作号/生活号）。**身份根升格为「定位（Positioning）」已拍板**（ADR-042，目标架构 → `docs/POSITIONING.md`，生产层闭环后动工）——人设收窄为定位的表达分区，渠道/选题/素材挂定位根，品牌/IP 留营销承诺层；落地前代码层只 `persona`。

前端文案 / 工具网格 / 示例占位围绕 **content / LinkedIn / multi-language**，避开 "TikTok / viral / trending"。

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

**ADR-038**：皮肤 = 人设 `brand` JSONB 块（caption 字号/字体/颜色/位置 + style-preset + 标题 + intro/outro + 音乐 `musicId`/`musicMood`/`musicEnabled`）；无独立 brand template 模块，`/brand-template` 307 → `/personas`。**`brand: null` = 系统默认皮肤**。编辑 = 人设页第三 tab「皮肤」（左设置 + 右 Remotion `<Player>` 实时预览，与产物像素级一致，`components/persona/skin-editor.tsx`）；存 = PUT 只更 `brand` 块，「恢复默认」写 `null`。片头尾媒体 = `POST /personas/{id}/media(/upload-url)`（随人设删）。**`logo` 键无渲染消费路径，不入 UI**。**Craft/format 字段非人设列**：`aspect` / `fillMode` / `captionEnabled` / filler removal / 音乐默认 = 配方注册表 + 计划默认；写作风格不在人设表列，住 风格六件 + `guidelines`。烘焙路径见 `MODULE_ARCHITECTURE.md §7` / `brand.py`（`brand_ref` = persona id，clip-spec 契约不变）。**`brand_template_id` 不出现在任何请求载荷**——composer 单身份控件，`persona_id` 经首条 chat 消息送达并在 `create_run` 钉入 `run.context.persona_id`。

## Persona Voice Block (voice)

音频绑定 = 人设 `voice` JSONB：`{kind:"cloned",voice_id,sample_asset_id}` | `{kind:"stock",stock_id}` | `null` = Auto（dub 用项目自身素材声音）。**`voice` 词独占音频本义**（NAMING N-27/N-28），文风在风格六件 + `guidelines`。编辑 = 人设页 Voice 卡（`components/persona/voice-section.tsx`）展示当前绑定 + 上传/换样本（样本 = persona 素材 `type=voice_sample`），存 = PUT 只更 `voice` 块；文案只陈述绑定状态、不许诺效果。STOCK_VOICES 注册表 / 系统音色试听 / dub 链优先级改造 = 缓做项。

## Video Editor & Rendering

**clip-spec 与 film-spec 是平级 spec families**（ADR-016 / ADR-119），**renderer = 可替换黑盒**（首推 Remotion）。详见 `docs/RENDERING.md`（§1 家族与渲染链 / §3 clip-spec 字段契约 / §6 渲染层 / §7 替换路径 / §8 现行轨道契约）与 `docs/VIDEO_EDITOR.md`（编辑器形态 + L2/L3 范围纪律）。**泄漏禁令**：Remotion / React 概念永不入任何 spec。

**clip 编辑器 L3 铁律（每项否决不变）**：禁多轨自由时间线 / 自由层合成 / 转场画廊与自由转场编辑 / stock B-roll 库 / 通用自动人脸或物体追踪 / 客户端引擎——专业需求明确导出剪映 / Premiere；ADR-044 的受控锚/层与进场边枚举不等于自由 NLE，Film composite 的受控元素组合由 ADR-140 单独规定。字幕样式仅枚举，不开放自由版式；styles 限定 CSS + libass 都能表达的子集（保 FFmpeg 替身成本）。硬前提：**多语言 ASR 词级时间戳 + 对象存储流式 / 寻址**（ADR-024）。

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

`apps/api/scripts/reset_db.py [--yes] [--db-only|--storage-only]` 清部署：dry-run 默认（印目标），`--yes` 落地。**保留前缀**：`demo/`（landing + 配方卡营销资产，内容寻址；生产永不再生）+ `music/`（平台默认曲目；`scripts/seed_default_music.py` reconcile 零配额复种）。**生产慎跑**——dry-run banner 先看。完成后重启即 auto-migrate + 默认音乐 reconcile；人设 `brand: null` 走系统默认皮，不布品牌种子；栈不布 demo 项目，`SKIP_DEMO_SEED` 是死旗，不依赖。

## Testing

测试资产只保留两类（ADR-114）：**用户主流程旅程矩阵**（各种类型的用户通过 chat 进行的各种创作流程，全旅程）与**承重架构防漂移守卫**（唯一写口 / 依赖方向 / registry↔prompt 一致性等全站铁律看门）。事故回归锁 / 批次产物 / 镜像实现形态的锁不立；新机制的覆盖需求必须能说出「矩阵哪本旅程的哪一步」，说不出归属旅程先回炉。退役 = 自然死亡：重构使哪本红就删哪本，删除逐案过堂，不留注释尸体。

**部署前仪式链**（按序全绿才可部署）：

1. 纯 pytest：`cd apps/api && uv run --extra dev python -m pytest tests/ -q`
2. check_gates（静态架构门：boot 冒烟 / 依赖方向 / 盲重试禁令 / 退役节点 kind 不回魂）：`cd apps/api && uv run python scripts/check_gates.py`
3. prompt_gate（仅当改动触及 prompt 面——`app/prompts/chat/`、`chat/prompts.py`、registry catalog lines）：`cd apps/api && uv run python scripts/prompt_gate.py`——10 探针（A–I 族，H 含 H4）绝对阈值，`--provider` 参数化（native-tool providers only，探的是工具 loop 线）。失败协议：复跑一次（provider 漂移在阈值内也存在），仍红则二分归因；**永不为放行回归调阈**。
4. 剧本矩阵（唯一活 LLM 闸，需活 API + dev worker + MiniMax 配额）：`cd apps/api && uv run python scripts/chat_scenarios.py`——运行当前 `SCENARIOS` 注册表（目前 S1–S12；S11 = MG 贴链成片全旅程，S12 = 网站入口变体）对活 API 跑形态级断言，harness 公共断言每本自动携带（SSE 工具 loop 线格式 / Activity 帧形态 / dock 形态 / 估价三断言）。永不锁 LLM 文案（代码强制文本例外）；客户端法律（打字机 / remount / 形态机）不进剧本断言——服务端真值才进。

**仪表层**（诊断尺子，非闸——读数供人工判读，不阻塞部署）：`scripts/reply_quality_probe.py` / `accept_quote_card_family.py` / `reconcile_credits.py` / `verify_beat_map.py` / `crop_track_parity.py` / `run_anatomy_matrix.py` / `craft_anatomy.py` / `film_stage_ledger.py`（film 链五段通过率 + failure codes 分布，ADR-119 D4）。

**Deterministic pure-function suites** (`apps/api/tests/*_pure.py`): no database, no LLM, no HTTP; sessions are in-memory stubs. They cover adjudication / pure-mapping layers where branch coverage matters and drift risk is low (the wiring door `apply_wiring_ops` + `_fill_key_for_step`, stream extraction, registry ↔ prompt enumeration consistency). If a behavior needs a real transaction or an LLM to verify, it belongs to the scenario matrix, not here. Run: `cd apps/api && uv run --extra dev python -m pytest tests/<file> -q`.

**Web**：vitest 组件旁置纯函数套件（纯 node 零 DOM）：`cd apps/web && npm test`。

fixture 纪律 / flake 处置 / 配额纪律归 `docs/VERIFICATION.md` §1.3～§1.4（剧本素材先拷 `scenario/` 前缀；常驻 worker 抢跑律；断言只锁形态，红先归因机制，禁调断言放行）。

**Prompt authoring law**: prompt files carry ONLY current-state law. Model-facing text never names dates / ADR numbers / batch or incident labels / retired forms — every law reads as if it was always the law. `{# #}` comment headers stay one-anchor-line: what the file is + operational constraints (include placement, mirror contracts) — no incident narratives; history lives in git and `docs/DECISIONS.md`. Prose-field schema changes still carry the two typewriter teeth (null-read tolerance + settled-prose pacing).
