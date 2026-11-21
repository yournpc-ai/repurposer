# Iteration 6 收官验收

2026-11-22，上海时间。三次 Chrome 入口均在隔离环境连接真实 MiniMax。模型请求的工具集合、选择、provider call ID、原生观察、持久回答、版本、账本及下载摘要见 [A 文字动画](final-a-trace.json)、[B 显式 Skill](final-b-trace.json)、[普通官网宣传片回归](final-c-trace.json)。请求 SHA-256 对应发送的完整模型载荷。节选排除了身份凭据、模型思维过程及内嵌二进制。

## U4R

| 消费者 | 改动与实测 |
| --- | --- |
| Chat 长线程 | 移除 MessageScroller 的 `@shadcn/react/message-scroller` 和旧 viewport/follow 实现。核对 affectUI MCP、Registry 与 Pro Agent Thread 源码后沿用其用户滚动意图、底端跟随和 ResizeObserver 行为。保留单一业务 viewport、流式分组折叠时的读边、Jump to Latest 与 Clean IconButton。整屏 Pro 示例自带模拟数据和布局，项目继续使用真实消息与工具卡。 |
| 样式及依赖 | 删除旧样式入口 `shadcn/tailwind.css` 和运行时依赖，更新锁文件。Tailwind v4 继续承担布局和响应式，Registry 安装所需的 shadcn CLI 归入开发依赖。 |
| Settings、通知、账户、引导 | Settings 使用 Clean Dialog、SegmentedControl、Select，Channels/Credits 使用现有 Clean Button/Card 等，通知为 Clean IconButton/Popover，账户用 Clean Popover。Tour 依赖 Base UI 对真实页面目标的定位，Sonner 承载业务 toast 与弹层，Motion/Lucide 均有生产消费者。 |
| Chrome | 真实长历史在 1280 和 390 CSS 像素下展开工具组，按钮上沿分别保持 227.39 和 252.78 像素。键盘 Home 阅读历史、视口变高变矮、Enter 返回末尾和刷新恢复通过。补充官网片实际流式响应中，视口先停在底端 107/341/234，按 Home 后内容由 341 增至 432 像素，scrollTop 仍为 0，点击跳底后恢复。 |
| 构建 | Web TypeScript、Vitest（42 文件 339 项）、生产构建通过。pnpm 离线 frozen lockfile 校验通过。 |

## 通用创作与 Skill 边界

文字动画从内置能力目录、方法文件、前端可选项与创建 chip 中删除。Landing 类型、示例及历史 chip 继续显示，Home 和旧 handoff 仅预填文案。历史 Output 从固定版本、对象、文件读取，读取历史 chip 可按旧引用生成显示信息。未变更历史数据。TextObject、Animation、text_beats、模板展开和 Renderer 继续存在。

在服务端，`skills/resolution.py` 仅解算显式引用，校验已安装版本或外部 SkillVersion 所有权。删掉别名匹配、同名版本追问，以及从前 32 条对话自动继承绑定的入口。同一 opening 中回答原问题时可读取该 opening 已保存的版本。项目来源事实和报价贯穿续跑。会话归档中方法工具的读取和索引按当前绑定过滤。A 的首请求没有方法段、包工具或 Skill 载荷，MiniMax 直接选了 `create_video`。独立官网回归的首调用是 `list_project_media`，随后自行准备网站来源、创建作品，未触发强制 Brief。

## 显式 promo-video 审计

**确实发现了仍能控制创作的旧宿主路径。** `readiness.py → prompts.py → plan_turn.py` 曾按官网分类把允许的动作收窄到取证、品牌分析、必填问卷。`service.py` 对跳过问卷的操作还写入 30 秒、16:9 等设置。删除固定下一动作、必填组、强制提问指令和默认值回填。保留已答历史问题、必要澄清、用户实填字段和同 URL 来源核验。另修复已就绪网页通过资产关联到快照时仍被视为素材待处理的问题。验证真实来源和作品编辑继续使用现有写口。

Chrome 的可见选择器形成 `promo-video@bdd94be16d60fa8f`。包目录为 `~/.local/share/repurposer/skills/promo-video/bdd94be16d60fa8f`，实际 manifest 名为 `video-shotcraft`，根文件 SHA-256 为 `9e6b2d68f50cae3d5405178d35d2bd305ee2045691fa726b63bae3ab8bb62e6b`。内置包走 `resolution → package_reader → package_session → video_turn_seats.prepare_bound_skill_context`。上传的外部 Skill 另由 `skills/loading.py` 检查不可变版本。本次未把两者混为一个安装源。

实际读取完整 SKILL.md（11260 字符）、references/pipeline.md、references/aesthetic-rules.md，以及 gallery/api/library.json（列表回执 80 条）。本次未读取单张 shot card 的实现、模板工程、演示媒体或音轨。包的方法要求先看产品，再选择模板、自主或共同创作。自主路线文档包含创作步骤和工程示例。它们作为文本进入模型；本次调用中没有启动包脚本、安装模板、向第三方发帖或由包发起制作。固定三幕、时长、画幅、音乐及示例文案均未追加到用户要求。模型实际看到 `tool_choice=auto` 和 21 个可选工具。首调用 `prepare_video_materials` 针对用户 URL，随后自选品牌分析和原生 `ask_user`。

实际主线为 Chat 消息及版本引用 → 服务端开包 → prompt/context 和原生 schema → MiniMax tool_calls → agents/tool_loop → plan_turn.execute → editor.create_video/execute_editor → editing.store 的版本 CAS。媒体和正式输出分别由 editor_media、MediaJob/ExportJob、Worker 和原 Chat 回执承接。查阅加载器、宿主 prompt、注册表、工具 handler、Worker 和 provider 记录，未见旧 launch-film、design_video、Run/Graph 或包内另一个创作写口实际执行。

## A · 无 Skill 的 30 秒文字动画

原始消息为「制作一条 30 秒、像 Apple 发布视频那样简洁有力的文字动画。」没有 Skill，未预填文案。首次模型保存了 25 秒，宿主漏识别“一条 30 秒、”的明确时长。修正现有约束提取后，第二次创建了 30 秒，但黑底列表沿用预设深色。修复 list-reveal 对 Agent 选择颜色的传播。首错项目依次为 `d695f438-5e2b-420d-bba8-421bec8a5bbf`、`86c5757b-45ec-466e-b830-e97f2d051d7e`。第二个项目提议的图片生成未获授权。

最终项目 `aa2051e5-e795-4a42-9b7c-2c7e61d85cd9` 由模型选定四段，包含「少即是多」「一触即达」、逐项出现的列表和结尾。预览覆盖开场与后半段，跨过预览窗口上限的调用被拒后分段完成。审阅并交付 v1。测试者要求放大开场标题时，已有 scale 关键帧限制静态变换，模型重试后停止。另一条独立后续要求是把结尾文字提前半秒收起，保留总时长，模型实际使用 inspect、trim、preview、export、review、deliver，交付 v2。两份文件均为 1920×1080、30 fps、900 帧，两个 ExportJob 各认领一次，各 capture 60 积分，MediaJob 为零。项目会话成本计量 0.049467 美元。两份 Output 都在 Chrome 刷新前后播放，下载字节 SHA-256 与数据库相同。

- [文字动画初版 MP4](https://repurposer.tos-ap-southeast-1.volces.com/exports/87014683-8c1c-46a0-aadf-66ebad9c0f6a/aa2051e5-e795-4a42-9b7c-2c7e61d85cd9/3dc912b0-73a1-50a0-a741-71c12a99eb15.mp4)
- [文字动画再编辑版 MP4](https://repurposer.tos-ap-southeast-1.volces.com/exports/87014683-8c1c-46a0-aadf-66ebad9c0f6a/aa2051e5-e795-4a42-9b7c-2c7e61d85cd9/032b0293-4212-5688-88c7-56334acd0206.mp4)

独立抽帧发现导出版的辅助文字仍偏暗，列表及主标题可读。修复了 title-lockup 副标题忽略作者显式前景色的问题，并以新创建版本的实际 TextObject 断言复测。上述两份历史成片保留原字节。

## B · OxValue 原项目

原始消息为「请为我的产品制作一个宣传片，这是网站：https://agent.oxvalue.ai/」。原始 Chrome 请求仅附可见 chip。项目 `837057ff-545f-44c0-a61f-9fa93ce54343`。真实原站返回 200，项目保存 2941 字符正文及六个页面视图。模型识别用户定位、审阅流程、原型界面数值与事实的区别。用户独立回答「自主自由创作」持久化于问题 `16571169-fe4a-407b-adfe-3de3c90f7bf0`，与 opening `a8e8a185-fbf3-4a02-be11-45e3250ccd45` 关联。续轮有模式标签、相同版本的方法段以及独立的工具选择。模型先读 pipeline 和镜头目录，继而读美学规则与来源，尝试 create_video。

第一次未能写入版本。单次 JSON 回答路径的 interim prose 在长事务持有 opening 行锁，而同一请求又从独立会话要求该锁。隔离 PostgreSQL 显示 writer 22417 被 22346 阻塞。另查到已回答的 opening 仍是 settled，与原生写入的 in_flight 合同冲突。取消隔离库内这一条等待查询后，已提交的模式回答与原站证据仍在。修复为短事务记录 interim prose，原 opening 的普通回答续跑复用 editor 恢复锁，写前重新进入 in_flight，结束时与 Stop 竞争结算。数据库回归从已 settled 的问题检验独立 writer 的可见性及最后结算。实际恢复使用同一项目内新的显式发送，未重写原回答。另修复合法的派生网页视图在创建工具未加载其项目内父快照的问题。

自主初版 `74ae352f-beff-4390-a334-25d78cb578b5` 采用八镜头、64.5 秒、六段中文旁白。三者均是模型决定。开场可预览，包含待录音对象的区间真实返回 pending_media。第一段获得确认并实扣 5 积分。后续模型曾请求生成与分镜不符的新文案；inspect_clip 原先只回显 TextObject 的文字，未返回 SpeechObject 的原稿、语言和声音。补齐既有检查工具的返回，拒绝错单后用原文重新取得报价。

页面正文支持「一个理论框架、八套行业数据库、二十七套算法」及 Frame / Enrich / Value / Defend 四步。八个镜头中，首尾为原生标题，中间使用原站视图。原项目 pending_brief 的时长、画幅、语言、叙事模式均为空，未写入默认偏好。普通官网回归在首次可选动作中先读项目媒体，固定来源后未做品牌分析即成功创建 `7d148ffd-918f-4ec9-86a9-99fc1f963753`。两次不同的首动作和各轮实际工具集合均可从 provider 记录核对。

### 费用和交付进度

用户将原稿六段的预算从 30 调整为 45 积分。每张原生报价按初版片段的原文、语言和声音核对，仅接受匹配的六行。见 B 证据中的 `voice_verification`。六个 MediaJob 各认领一次且均成功，钱包合计 hold 45、release 45、capture 44，剩余预占为零。另一次新文案报价已拒绝，未建立 Job。各段数据按镜头顺序排列。

| 场景 | 报价（积分） | 实扣（积分） | 固定录音（秒） |
| --- | ---: | ---: | ---: |
| 2 | 5 | 5 | 5.155 |
| 3 | 9 | 9 | 9.764 |
| 4 | 8 | 8 | 9.125 |
| 5 | 7 | 6 | 7.674 |
| 6 | 9 | 9 | 10.879 |
| 7 | 7 | 7 | 7.674 |

续跑观察到一处宿主提示错误。`chat/prompts.py` 泛化要求以 insert_audio 插入固定旁白，模型在处理已有待配音片段时另起了一轨。v8 的 12.5–22.5 秒预览中，原生 speech 和单独 audio 编译时引用了同一起点、同一录音。其余两个重复位置是独立录音与未绑定的 speech 占位对象，正式导出返回 dependencies_not_ready，未产生 ExportJob。修正了当前提示，分别说明已有片段的绑定与独立新增音频的插入。费用结算没有重复。两段声音超出初稿预留窗口约 0.13 秒和 0.88 秒，需要调整相邻对白的时间。

截至 v8，六段录音已经可用，成片仍未交付。需要裁定如何使用已有 RemoveClip 版本操作去重。B 的正式审片、Chrome 下载及交付后再编辑待验。此时项目会话成本计量为 0.268435 美元，中断且未提交用量行的调用未计入。

## 六面裁决

| 面 | 当前结果 | 依据 |
| --- | --- | --- |
| Tool | 有条件通过 | 无 Skill 创作、真实来源准备、逐对象检查、版本编辑有实测；关键帧控制的 scale 请求已拒绝。 |
| Context | 通过 | 完整根方法与资源只进入显式绑定。A 与独立官网回归没有包指令；B 的方法选择、来源、实际工具和已保存字段有独立记录。 |
| Chat | 有条件通过 | 原始输入、独立回答、费用拒绝/允许、A 的两张交付卡可复查；B 的输出交付待验。 |
| Execution | 有条件通过 | A 两次正式导出，B 六段声音均已生成、逐项结算。B 的重复轨道和占位对象阻断正式交付。 |
| Recovery | 有条件通过 | A 刷新后旧版可播可下载，B 原回答和采集在失败重试后留存。普通回答的锁问题有数据库回归；原项目重入使用了新的显式发送。 |
| UI | 通过 | 真实流、键盘、长历史、工具组、移动视口、下载与刷新已实测。Chrome 进入通知空列表，打开账户 Settings，切换 Channels、Assistant、Credits，读到真实余额并用 Escape 关闭。 |

## 环境、验证和 Git

- 基线为本地 main 与 GitHub main 的 `4b28e891dce343dd408d4206fd9e703f532b2b82`。结束前直连 GitHub 的 Git 传输超时，使用 GitHub API 单独核对远端 main 仍在该提交。
- 独立 PostgreSQL 5966 数据库 `rep_u4r_20261122` 实际迁移至 `j6d05_project_brief`。共享数据库端口 5432 开工探测超时，未对其执行迁移。API 19881、Renderer 19887、生产前端预览 19889 和 Worker 均使用验收配置。公开 TOS 保存正式成片。模型和媒体分别计量，无第三方发布。
- 最新 API core 475 项通过，另有 1 项 SQLAlchemy 连接回收警告、2 项 Pillow 弃用警告。Web 339 项通过。十用户及 Worker 故障矩阵沿用 6D 验收，本次复核已修改的调用链。
- 实现提交为 `61f394fa`，38 个路径，新增 315 行、删除 1682 行。完整文件及增删状态可用 `git show --name-status 61f394fa` 复核。本报告所在提交可以用 `git log -1 --format=%H -- docs/tasks/agent-editor-evidence/iteration-6/final-closure.md` 定位。未推送。
- 未纳入提交的既有工作为 `.dockerignore`、`apps/web/src/components/ui/thinking-loader.tsx`、`docs/tasks/affectui-migration.md`。
- 现行合同同步到 CLAUDE、Web AGENTS、new-agent、PROGRESS、VIDEO_PROJECT、VIDEO_EDITOR、CHAT_ARCHITECTURE、UI_GUIDELINES、RECIPES、RENDERING、索引及 Skill 合同。原官网工作协议和 UI/入口旧报告加历史标识，既有 6D 实测数值、提交、原片与失败记录保留。

以下列出本批实现的实际路径，D 表示删除，M 表示修改。

- M `apps/api/app/chat/context.py`
- M `apps/api/app/chat/conversation_context.py`
- M `apps/api/app/chat/editor.py`
- M `apps/api/app/chat/editor_create.py`
- M `apps/api/app/chat/plan_turn.py`
- M `apps/api/app/chat/prompts.py`
- M `apps/api/app/chat/readiness.py`
- M `apps/api/app/chat/service.py`
- M `apps/api/app/chat/turn_tools.py`
- M `apps/api/app/chat/video_turn_seats.py`
- M `apps/api/app/editing/presets.py`
- M `apps/api/app/models/schemas.py`
- M `apps/api/app/skills/resolution.py`
- D `apps/api/app/skills/text-animation/SKILL.md`
- M `apps/api/app/tools/project_context.py`
- M `apps/api/app/tools/video/design.py`
- M `apps/api/test/core/test_delivery.py`
- M `apps/api/test/core/test_editor_create.py`
- M `apps/api/test/core/test_media_preparation.py`
- M `apps/api/test/core/test_promo_authoring.py`
- M `apps/api/test/core/test_question_groups.py`
- M `apps/api/test/core/test_skill_catalog.py`
- M `apps/api/test/core/test_skill_store.py`
- M `apps/api/test/core/test_website_promo_readiness.py`
- M `apps/api/test/core/test_website_promo_wire.py`
- M `apps/web/package.json`
- M `apps/web/src/components/chat/ChatConversation.tsx`
- M `apps/web/src/components/chat/MessageScroller.tsx`
- M `apps/web/src/components/landing/LandingSkills.tsx`
- M `apps/web/src/components/landing/content.ts`
- M `apps/web/src/lib/i18n/locales/en.ts`
- M `apps/web/src/lib/i18n/locales/zh.ts`
- M `apps/web/src/lib/landingCreate.ts`
- M `apps/web/src/lib/skills.test.ts`
- M `apps/web/src/lib/skills.ts`
- M `apps/web/src/routes/_app.home.tsx`
- M `apps/web/src/styles.css`
- M `pnpm-lock.yaml`

本批规范及证据路径如下。

- `CLAUDE.md`
- `apps/web/AGENTS.md`
- `docs/CHAT_ARCHITECTURE.md`
- `docs/PROGRESS.md`
- `docs/README.md`
- `docs/RECIPES.md`
- `docs/RENDERING.md`
- `docs/UI_GUIDELINES.md`
- `docs/VIDEO_EDITOR.md`
- `docs/VIDEO_PROJECT.md`
- `docs/tasks/affectui-evidence/README.md`
- `docs/tasks/home-creation-entry-refresh.md`
- `docs/tasks/new-agent.md`
- `docs/tasks/skill-package-promo-video.md`
- `docs/tasks/website-promo-evidence-brief-workflow.md`
- `docs/tasks/website-promo-iteration2-media-slice.md`
- `docs/tasks/agent-editor-evidence/iteration-6/final-closure.md`
- `docs/tasks/agent-editor-evidence/iteration-6/final-a-trace.json`
- `docs/tasks/agent-editor-evidence/iteration-6/final-b-trace.json`
- `docs/tasks/agent-editor-evidence/iteration-6/final-c-trace.json`
