# affectUI Clean 迁移验收

U1–U4 清单按当时消费者保留。当前 Chat 滚动与最终依赖审计见 [U4R](../agent-editor-evidence/iteration-6/final-closure.md)。

## U3-B、U4 最终集成验收 · 2026-11-22

**后续存储决定（2026-11-22）**　正式导出采用现有公开 TOS 桶。此前测试遇到的私有桶门禁已撤回。新路径用合成 MP4 实测条件 PUT、匿名 GET 和带文件名下载均返回 200，两次读取与源文件 SHA-256 一致，测试对象已清理。另经当前播放接口读取下文两个历史 Output 的公开原件，SHA-256 均匹配。导出相关 API 测试 43 项、Web 测试 339 项、TypeScript 和生产构建均通过。下文保留 U3/U4 当时的验收结果。

**UI 代码和技术验收通过，整条新作交付旅程有条件通过。** 新项目完成素材上传和编辑，音乐与旁白进入不同的固定版本。新版本正式导出在私有存储门禁处停止；没有产生可审阅、交付的新 Output。两个已经交付的历史版本在当前 UI 重新播放、续签和下载成功。后文各切片的“待交接”“未验证”保留为当时的记录。[本次浏览器、回执与文件校验数据](./u3-u4-integration.json)

Editor 在 `e932584a` 将 Chat 相关文件标记为 RELEASED。UI 提交为 `a2c6f641`（Agent Thread 和旧通用组件退役）、`f33b4654`（素材提及和回执错误详情）、`44645969`（连续文件选择和粘贴）。本次在共享 main 原地施工，只提交所列 UI 路径。隔离 API 位于 19861，PostgreSQL 5966 的验收库为 `rep_6d_qmopb4`，迁移版本为 `j6d05_project_brief`。共享 8000、Worker、数据库配置、Editor 工作树内容均保持原归属。用户接手推送。[逐文件交接](../agent-editor-evidence/iteration-6/ui-handoff.md)

| 验收面 | 当前前端的实际结果 |
|---|---|
| Tool | 两个真实历史项目各有 4 组 9 项、3 组 7 项。逐项对照持久化的 opening、call ID、声明索引与状态。桌面键盘、平板和手机触摸均可展开和关闭；同名不同调用的跨 opening 归属另有挂载回归。 |
| Context | 标准开发来源的 Home 直传 PUT 200。签名、创建项目、绑定附件和 Chat 各一次，库内一条 opening、一份附件。在 375 像素视口粘贴和拖入两个不同文件，分别 PUT 200，草稿完整。项目内 Shift+Enter、粘贴文本、素材 mention、Skill 与 Enter 发送经实际 POST 和数据库核对。资产无 title 时从项目内对应 ID 取显示名。 |
| Chat | 使用 Clean Thread 布局、Thinking、ToolCallCard/Group、受控 ApprovalCard、附件与结果组件。Markdown、原生流、播放器与历史沿用原入口。授权显示服务端原问题与上限。同意和拒绝发送给原问题 ID，历史决定以回执为准。 |
| Execution | 分别拒绝和同意两条音乐授权，刷新后同意独立的旁白授权。音乐与旁白 Job 均一次成功，实际结算 0 与 1 积分。v1、v2、v3 分别固定 1、2、3 个来源。新导出在预览后获得最多 8 积分的授权，服务器返回 private_storage_unavailable，ExportJob 计数为 0，硬刷新仍显示失败及原原因。 |
| Recovery | Stop 向真实 opening 发送一次 POST，无可保留内容的 opening 被撤回，已存作品继续可读。6D 的模拟供应商在提交后遭进程强杀，隔离故障库持久化了 provider_unknown。Chrome 通过实际 FastAPI 历史接口回放，刷新前后均为一条未知回执，预占 3 积分、结算未知。该次仅转发 GET，关闭 lifespan，数据库请求使用回滚事务。 |
| UI 与媒体 | 1280/768/375、中文与英文、明暗、reduced-motion、键盘及触摸视口。两条真实音频播放时钟前进且可暂停；1920 像素图片可打开，Escape 后焦点回到原按钮。两个历史 Output 各解码 150 帧，硬刷新后的下载 SHA-256 和对应固定版本一致。推进客户端时钟触发真实签名续期。系统主题切换、全屏与选区另见独立组件浏览器证据。 |

**回归修复。** 真实长历史中，工具组开合后行高估算会让触摸落到相邻组，已移除消息行的估算高度。按“从列表进入详情 → reload 到 document commit → 立即后退”复核，三种视口都返回列表，未观察到 hydration 异常。另修复了 React 批处理下连续选文件时第二个上传可能不启动，并增加同批重复文件只上传一次的回归。

**退役扫描。** 在 `apps/web/src` 按别名及相对路径解析旧模块消费者。旧 Button、Input、Dialog、Select、Popover、Tooltip、Slider、Avatar、Label、Attachment、Bubble、Marker、Message、旧 MessageScroller 路径均为 0。Git 跟踪的旧通用视觉封装剩余 0；Tour 与 Sonner 分别保留引导与反馈。Base UI 直接引用为 1 条、1 个文件，对应 Tour 所用 Popover 交互原语。Arc token 为 0。最后移除了 5 个旧组件文件，将滚动与视口定位行为迁入 Chat，删除 dock-surface、studio-tools 和 5 个失效样式变量，移除直接依赖 class-variance-authority。开工即存在的未跟踪 thinking-loader.tsx 没有消费者，未纳入提交。未新增 Chat Store、Job Store 或 Zustand。

**技术验证。** Web TypeScript、42 个测试文件的 339 项测试、客户端与 SSR 生产构建均通过。真实对象存储在临时来源端口拒绝预检，失败时草稿和重试入口可用；允许的 localhost:3000 来源上传成功。此次手机验收使用 Chrome 触摸视口，实体软键盘与系统 IME 未验证。当前新版本从私有存储导出到审片交付仍未通过，不扩大公开桶授权。历史 Output 与新导出分别记录。


## U3-A 与独立 U4 切片

**有条件通过。** 开工时本地 main、origin/main 与远端引用同为 `935aab92`。本轮在共享 main 原地提交，使用逐文件 pathspec。Editor 的 API、AgentThread、ChatConversation、timeline 与流协议归 Editor。其并行提交和未提交修改保持原归属。共享 8000 与 dev_worker 保持暂停。UI 联调尚未收到带数据库、迁移与端口的隔离 API 交接。

| 本地 UI 提交 | 范围 |
|---|---|
| `778034ee` | Thinking、费用决定和有序 Tool 回执的纯展示与回归测试 |
| `8fea9ad5` | Composer、Persona、QuestionDock、附件面板与旧控件删除 |
| `8a199198` | Caret 弹层、附件操作与水合前草稿 |
| `cd97c9c7` | 媒体查看、波形、预览、字幕字号、滚动控件与旧组件删除 |

### StoryboardCard 文件交接与回归

| 文件 | UI 释放状态 | 接手方 | 已提交的视觉基线 |
|---|---|---|---|
| `apps/web/src/components/chat/video/StoryboardCard.tsx` | `RELEASED` | `OWNED_BY_EDITOR` | `cd97c9c7` |

在本地 main 的 `3e5513b1` 核对，该文件与视觉基线一致，工作树和暂存区均无该文件的修改。Editor 可接手移除展示回执响应中的 `run_id` 读取和 `onRunStarted` 回调。保留原展示就绪条件，以及对 `presented_message_id || messageId`、`composition_version_id` 和 `presentation_digest` 的确认。UI 后续接手 Chat 文件以 Editor 的 `iteration-6/ui-handoff.md` 逐文件释放为准。

Editor 在 `8def896d` 移除了这条 Run 路径，在 `8321116b` 将分镜卡标记为 `RELEASED` 并交回 UI。交接时该文件没有工作树或暂存修改。AgentThread、ChatConversation、ComponentSlot 与 Activity 投影仍为 `OWNED_BY_EDITOR`。详见 [Editor 文件交接及执行契约](../agent-editor-evidence/iteration-6/ui-handoff.md)。

Chrome 复现了一个展示回执错误。服务端 DTO 为 `video_preview.status=pending_media` 时，预览提示已显示就会触发父级的就绪回调，正文结束后浏览器因此向原消息发送了一次展示完成 POST。分镜卡现在检查预览状态。返回 DTO 缺少所请求的局部预览时，卡片显示读取失败并保留未确认状态。普通分镜没有请求局部预览时，原有正文就绪路径仍然有效。

| Chrome 组件验收 | 观测结果 |
|---|---|
| 英文浅色桌面 1280 和平板 768、中文深色手机 375，三种宽度均启用 reduced-motion | 真实 StoryboardCard、恢复判定和 Remotion Player 使用本机版本 DTO 夹具。媒体待就绪、预览不可用、请求的预览缺失、内容摘要不匹配四种情况下，正文结束后均为 0 次展示 POST。 |
| 固定版本、键盘切换和刷新 | 读取 v1 且首帧就绪后，正文尚未完成时 0 次 POST。正文结束后向 original-message 发送 1 次 POST，正文只含 v1 与本次 DTO 的展示摘要。Enter 打开当前版本才读取 v2，回执计数不变。禁用浏览器缓存并刷新后重新读取 v1。恢复目标匹配时正文就绪后再次回执，切换为其他历史消息时 0 次新增回执。三种宽度的页面异常数均为 0。 |
| 自动化 | 新增 4 项组件回归，覆盖三类不可播放输入与无局部预览的独立正文路径。本轮完整 Web 测试为 47 个文件、418 项通过，TypeScript、客户端及 SSR 生产构建通过。 |

以上请求由浏览器网络夹具接收。真实项目刷新、服务端持久化、用户续改及历史 Output 联调仍未验证。Editor 单独报告的隔离 PostgreSQL HTTP 验证见交接文档。此切片只涉及分镜展示与恢复判定的消费端，Tool、Context 与 Job 执行没有新增联调证据。

### 项目详情路由交接（UI → Editor 6D）

| 文件 | UI 释放状态 | 接手方与范围 |
|---|---|---|
| `apps/web/src/routes/_app.projects.$id.tsx` | `RELEASED` | `OWNED_BY_EDITOR`，接手项目详情页的旧 Run / lifecycle 数据消费与 Chat 接线 |

核对时共享 main 为 `cf8608e0`。该路由的 HEAD、暂存区及工作树内容均为 Git blob `b7bab342f0e86186be5f5ba782228ac52553b3a3`，没有待合入的 UI 改动。6D 可直接接手。除 AgentThread 的 `initialRunId`、`lifecycle` 和 prompt 回退外，该文件还用 `latest_run` 与 `material_pending` 决定素材轮询，用 `runActive` 驱动项目菜单。Home 首发通过 `location.state.firstMessage` 单独传入。此次释放仅涉及该路由，分镜卡继续归 UI。

### 官方源码与接入裁决

使用本地 affectui、affectui-migrate Skills 及条目参考，通过 affectUI MCP 的 search_components、get_component、get_source 读取完整 TSX。apps/web 的 shadcn Registry 配置有效。直接请求免费 tool-call-card-clean 返回 200。当前 shell 无 Registry Token，直接请求 Pro approval-card-clean 返回 401，授权 MCP 成功返回其完整源码。Pro Screen 与 Composer 同样经 MCP 读取。

| 场景 | 官方候选和源码事实 | 当前实现与数据归属 |
|---|---|---|
| 消息和工作过程 | `agent-thread` Screen 将用户消息、正文、工具组、决定、附件与任务穿插在消息流中。simulate 可以播放示例故事。另查 `ai-answer-clean`、`message-actions-clean` 的来源卡、再生成和版本动作。 | 采用流内折叠结构。Chat 的 Markdown、打字机、历史与 Stop 仍由现有宿主负责。正式渲染及动作接线等待文件交接。 |
| 单项和多项 Tool | `tool-call-card-clean` 同一源码导出 ToolCallCard 和 ToolCallGroup，原版三态，按传入子项归组，原生 button 提供 Enter / Space 折叠。 | 保留卡片与组结构。分别翻译 accepted、queued、running、success、error、cancelled、unknown、notExecuted、待确认、已拒绝、已同意、已存版本、待审片与已交付。仅显示调用者提供的耗时与详情。组接收顺序由调用方决定。测试涵盖同名调用的不同结果；生产 call ID 关联仍待 6D。 |
| Thinking | `thinking-loader-clean` 自带阶段轮转和完成计时。 | 保留官方射线和标签过渡，展示调用方传入的单一阶段。 |
| 授权 | `approval-card-clean` 支持 uncontrolled、Always 与自动超时拒绝。`permission-request-clean` 涵盖按时长授权、撤销。 | 使用 Approval Card 的标题、价格详情和操作区。状态、报价、上限与 submitting 由调用方提供，同意与拒绝只发出决定。刷新和资金结果需依赖服务端。 |
| Composer 与附件 | `chat-composer-clean` 有自己的输入、模型、授权模式及示例听写。`dropzone-clean` 有文件状态与进度视图。 | 使用现有 Clean IconButton、Spinner、Tooltip、Popover、Avatar、Card、TextField。保留 MentionEditor 的 DOM chip 和 Skill 引用、文件选择、项目启动、上传与重试。进度来自原上传 hook。 |
| 播放器与结果 | 检索媒体卡、toolbars、Dialog、Popover、加载与错误展示。单独核对 dialog-clean、popover-clean、button-clean、icon-button-clean、select-clean 源码。范围输入检索返回 number-input 等候选。 | Clean 原生 Dialog 加入全屏媒体布局和指定返回焦点。保留底图动画、签名读取、下载、Remotion、真实音频元素和像素选区。字号连续拖动采用原生 range；原 CAS 写口、版本身份与草稿取消路径继续工作。 |

### 删除与代码扫描

口径与 U2 一致，按 apps/web/src 中不同消费者文件计数，识别别名和相对路径。只计旧模块的精确路径。Base UI 按直接 import 语句计数。

| 指标 | 开工复核 | 独立切片后 |
|---|---:|---:|
| 旧 Button / Input / Dialog / Select 消费文件 | 15 / 1 / 1 / 1 | 2 / 0 / 0 / 0 |
| Base UI 直接 import / 文件 | 15 / 12 | 6 / 4 |
| U2 清单中仍存在的旧 UI 文件 | 16 | 8 |
| Arc token | 0 | 0 |

删除 avatar、input、tooltip、dialog、label、popover、select、slider 共 8 个文件及其内嵌样式。移除根 TooltipProvider 和无消费者的 AttachmentTrigger。独立 CSS 文件删除 0，直接依赖删除 0。未跟踪的 thinking-loader.tsx 在开工时即存在，本轮未纳入提交。无新状态库、Chat Store 或 Job Store。

| 剩余文件 | 归属 |
|---|---|
| button | AgentThread、ChatConversation 两个旧按钮消费者均待释放 |
| attachment、bubble、marker、message | Chat 附件、用户消息、MetaRow 与消息正文仍消费。附件操作已用 Clean |
| message-scroller | 有实际视口锚点、滚动恢复和 Chat 消费者。滚动按钮已用 Clean |
| tour、sonner | 首页引导定位和全局反馈。Tour 直接消费 Base UI Popover 的底层定位 |

### 本轮五面与浏览器证据

| 面 | 本轮实际证据 | 尚待联合验收 |
|---|---|---|
| Tool | UI 提交只涉及 Web 与证据。回执测试校验同名 Tool 的顺序和 Unknown / Not Executed | 原生模型调用、call ID 到 Job 的投影 |
| Context | Chrome 输入、Shift+Enter、纯文本粘贴、选中素材 mention 与内置 Skill。实测草稿包含 source.mp4 的身份和 promo-video。Enter 只触发一次组件回调 | 已登录 Home 首发、上传与 Project Chat POST 的持久请求体 |
| Chat | Tool Group 与 Card 的 Enter / Space 折叠。授权组件同意和拒绝回调触发后仍以父级提供的状态为准 | 生产 Activity、审批结果、流式正文、Stop 与历史重放 |
| Execution | 使用既有 MP4、MP3、PNG。Chrome 实际解码、播放、暂停、seek、全屏、框选视频像素并下载，下载内容 SHA-256 与文件一致 | 真实媒体生成、费用预占、失败 / Unknown、正式导出、审片与交付 |
| Recovery | /home 水合前输入两行，修复前可复现水合错误和清空，修复后在桌面与手机视口保留原文。独立 SSR 水合测试同时检查 DOM 身份和 onChange 内容。焦点从详情返回 Lightbox，关闭后回原媒体按钮 | opening 重放、刷新和续聊、历史版本 / Output 身份、签名过期续期 |
| UI | Chrome 1280×820、768×820、375×820。浅 / 深 / System 变化、中文 / 英文、reduce、键盘、鼠标和触摸视口。附件选取与 drop 到达组件回调。项目 / 手机实体键盘与系统 IME 未实测 | 真实项目内完整细节及多设备联调 |

[隔离浏览器测量](u3-u4-browser.json) 使用真实组件和本地媒体样本，回执、费用与输入回调是组件夹具。页面错误、末焦点、草稿、Skill、SHA-256 与调用次数均由浏览器采集。/home 路由另以未登录浏览器断开 API，验证草稿跨水合保留。附件访问出现登录弹层。

Router 精确回归保留：从 /projects 打开项目详情，reload 到 document commit 后立即 goBack。桌面和手机无 API 版本均返回项目列表，无 hydration 错误。含真实项目数据的原序列仍为未验证。

在 apps/web 执行 `pnpm exec tsc --noEmit`、`pnpm test`、`pnpm build`。本轮最后一次完整运行通过 46 个测试文件、415 项测试及客户端、SSR 构建。计数包含当时共享工作树的 Editor 测试。QuestionDock 的选中态断言改查唯一选中的 Clean Card，SkillPicker 定位断言保留原像素与方向检查。

**联合签收仍开放。** 目前仅分镜卡已从 Editor 交回。生产 Tool Group、Activity 与费用确认的接线仍等待其消费者文件释放，真实项目联调等待隔离 API 目标。旧 Run 投影、费用回执、真实 Tool / Job、历史 Output 与交付后续改均需通过同一真实旅程。6B / 6C 的已有记录及本轮静态检查不计入这些项目的验收。

## U0–U2 范围和现场

开工基线为 `fab4017b`，当时远端为 `a83ee492`。U0 为 `eaed729d`，U1 为 `b0fd324d`。共享工作树在 U2 施工期间纳入独立 6C 提交 `ca29ce54`。本目录只记录 Web 迁移。

## 组件与主题

组件取自授权 affectUI MCP 的 Clean 源码。安装到 `apps/web/src/components/ui/` 的实际 Registry slug 如下。

`avatar-clean`, `badge-clean`, `button-clean`, `card-clean`, `checkbox-clean`, `dialog-clean`, `dropdown-menu-clean`, `empty-state-clean`, `icon-button-clean`, `popover-clean`, `segmented-control-clean`, `select-clean`, `skeleton-clean`, `spinner-clean`, `switch-clean`, `text-area-clean`, `text-field-clean`, `tooltip-clean`.

这些组件依赖 React 19，自带局部 CSS。Button 接受 primary / secondary / ghost / destructive、size、loading 及原生表单属性。IconButton 需要 label 和 icon。TextField 与 TextArea 使用原生输入事件，Checkbox 与 Switch 使用原生 checked/onChange。Select 使用 options/value/onChange。Dialog 与 AlertDialog 使用 open/onOpenChange，后者的异步 onConfirm 拒绝后保留弹层。DropdownMenu 使用 items 和 trigger，Popover 使用 open/onClose。Card 的标题链接提供主点击区域。各组件的导出类型与实现同文件。

通用视觉源是 Clean 源码中的尺寸、样式及 `src/styles.css` 的 `--aui-*` 明暗值。Tailwind 语义色读取这些值。原 ThemeProvider 保存 Light / Dark / System，首屏脚本按系统偏好解析。Studio 使用 App Shell Inset 的主面板、侧栏和断点，自行接入真实路由；Home 接入真实 Skill 与上传状态。注册器配置里的 shadcn style 是 CLI schema 使用的值。项目卡的多态元素适配了当前 TypeScript；原生 Dialog 通知既有 Sonner 把同一个提示区域移入当前弹层。

## 删除与消费者

统计范围为 `apps/web/src` 的 TS、TSX、CSS。每个组件的消费者数为不同文件数，识别别名和相对导入，包含测试 mock。Base UI 直接引用按 import 语句计数。未跟踪的其他施工文件不进入基线。

| 指标 | 开工 | U2 |
|---|---:|---:|
| 旧 button 直接消费者 | 43 | 15 |
| 旧 input 直接消费者 | 13 | 1 |
| 旧 dialog 直接消费者 | 9 | 1 |
| 旧 select 直接消费者 | 5 | 1 |
| 旧 UI 文件 | 34 | 16 |
| 其中直接导入 Base UI 的旧文件 | 24 | 12 |
| 全 Web 直接 Base UI import | 31 | 15 |
| 含这些 import 的 Web 文件 | 25 | 12 |
| 不同 Arc token 定义 | 83 | 0 |

U1 删除 `alert`、`checkbox`、`progress`、`scroll-area`、`switch`，以及 animate-ui 下 progress 的组件、原语和 counting-number 原语。U2 删除以下零消费者旧文件。

`badge.tsx`, `card.tsx`, `dropdown-menu.tsx`, `empty-state.tsx`, `input-group.tsx`, `separator.tsx`, `sheet.tsx`, `sidebar.tsx`, `skeleton.tsx`, `tabs.tsx`, `textarea.tsx`, `toggle-group.tsx`, `toggle.tsx`。

删除 26 条已退出的 sidebar/chart 主题声明（含 Tailwind 映射），3 个旧 CSS utility（media-scrim、scroll-fade-x、ambient-glow），2 个无调用的封面动画（rc-lineGrow、rc-qPulse），以及下线的 post、quote、carousel 封面选择器。保留现有 5 种素材封面实际使用的样式和媒体覆盖层语义色。移除 3 个直接依赖及锁文件记录（@base-ui-components/react、tailwindcss-animate、@fontsource-variable/geist）。

### U2 时仍在使用的基线文件

下表路径相对于 `apps/web/src/`。U3 覆盖消息与 Activity，U4 覆盖共享 Composer、预览与媒体控件。依赖链中的旧原语在最后一个消费者切换后删除。Tour 的定位与交互服务首次引导，Sonner 服务全局反馈，二者已接入本轮 Clean 按钮或主题。

| 旧文件 | 直接消费者 | 处理范围 |
|---|---|---|
| `components/ui/attachment.tsx` | `components/chat/AgentThread.tsx`, `components/chat/rows/UserMessage.tsx` | U3/U4 |
| `components/ui/avatar.tsx` | `components/composer/PersonaPanel.tsx` | U4 |
| `components/ui/bubble.tsx` | `components/chat/rows/UserMessage.tsx` | U3 |
| `components/ui/button.tsx` | `components/chat/AgentThread.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/ChatOutputViewer.tsx`, `components/chat/QuestionDock.tsx`, `components/chat/video/StoryboardCard.tsx`, `components/chat/video/TextSizeScrubInput.tsx`, `components/chat/video/WaveformPlayer.tsx`, `components/chat/video/preview/CompositionPreview.tsx`, `components/composer/ComposerIconButton.tsx`, `components/composer/ComposerSendButton.tsx`, `components/results/MediaLightboxStage.tsx`, `components/results/MediaRegionSelectionOverlay.tsx`, `components/ui/attachment.tsx`, `components/ui/dialog.tsx`, `components/ui/message-scroller.tsx` | U3/U4 |
| `components/ui/dialog.tsx` | `components/results/MediaLightbox.tsx` | U3/U4 |
| `components/ui/input.tsx` | `components/chat/QuestionDock.tsx` | U3 |
| `components/ui/label.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/marker.tsx` | `components/chat/rows/MetaRow.tsx` | U3 |
| `components/ui/message-scroller.tsx` | `components/chat/ActivityStream.mount.test.tsx`, `components/chat/ActivityStream.tsx`, `components/chat/AgentThread.mediaJourney.mount.test.tsx`, `components/chat/ChatConversation.mount.test.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/blocks/RunBlock.tsx` | U3 |
| `components/ui/message.tsx` | `components/chat/AgentThread.tsx`, `components/chat/AnsweredQuestion.tsx`, `components/chat/CandidateSurface.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/blocks/ComponentSlot.tsx`, `components/chat/blocks/RunBlock.tsx`, `components/chat/rows/AssistantText.tsx`, `components/chat/rows/UserMessage.tsx`, `components/chat/video/AudioCandidateSurface.tsx`, `components/chat/video/VideoPresetCandidateSurface.tsx` | U3 |
| `components/ui/popover.tsx` | `components/chat/video/TextSizeScrubInput.tsx`, `components/composer/ComposerPanelButton.tsx`, `components/results/MediaLightboxStage.tsx` | U4 |
| `components/ui/select.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/slider.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/sonner.tsx` | `routes/__root.tsx` | 已迁移，全局反馈服务 |
| `components/ui/tooltip.tsx` | `components/composer/ComposerPanelButton.tsx`, `routes/__root.tsx` | U3/U4（根 Provider 随最后一个调用方移除） |
| `components/ui/tour.tsx` | `components/home/HomeComposer.tsx` | 已迁移按钮，保留 Spotlight 定位 |

直接导入 Base UI 的剩余文件如下。

- `components/ui/attachment.tsx`，2 处。
- `components/ui/avatar.tsx`，1 处。
- `components/ui/bubble.tsx`，2 处。
- `components/ui/button.tsx`，1 处。
- `components/ui/dialog.tsx`，1 处。
- `components/ui/input.tsx`，1 处。
- `components/ui/marker.tsx`，2 处。
- `components/ui/popover.tsx`，1 处。
- `components/ui/select.tsx`，1 处。
- `components/ui/slider.tsx`，1 处。
- `components/ui/tooltip.tsx`，1 处。
- `components/ui/tour.tsx`，1 处。

### Arc 定义与消费位置

以下为开工版本中每个定义及直接 var 引用的源位置。Tailwind 工具类经 styles.css 间接消费这些值。U2 后源码中无 `--arc-*`。

| token | 定义（styles.css 行） | 直接消费（styles.css 行或其他文件） |
|---|---|---|
| `--arc-accent` | 687, 838 | 814 |
| `--arc-accent-foreground` | 690 | 815 |
| `--arc-accent-strong` | 688, 839 | 无直接 var 引用 |
| `--arc-accent-subtle` | 689, 840 | 无直接 var 引用 |
| `--arc-background` | 677, 826 | 690, 757, 812 |
| `--arc-border` | 684, 835 | 786, 789 |
| `--arc-border-strong` | 686, 837 | 788, 790, 819 |
| `--arc-border-subtle` | 685, 836 | 787, 818 |
| `--arc-control-fill` | 698, 847 | 610 |
| `--arc-control-glyph` | 693, 842 | 605, 773 |
| `--arc-control-on` | 692, 841 | 604, 698, 699, 772 |
| `--arc-control-on-subtle` | 699 | 无直接 var 引用 |
| `--arc-control-thumb` | 696, 845 | 608 |
| `--arc-control-thumb-on` | 697, 846 | 609 |
| `--arc-control-thumb-shadow` | 700, 848 | 583 |
| `--arc-control-track` | 694, 843 | 606 |
| `--arc-control-track-hover` | 695, 844 | 607 |
| `--arc-danger` | 707, 855 | 785 |
| `--arc-ease-enter` | 753 | 578, 963, 966 |
| `--arc-focus-ring` | 691 | 无直接 var 引用 |
| `--arc-font-body` | 739 | 563, 890 |
| `--arc-font-display` | 738 | 564, 895 |
| `--arc-foreground` | 681, 832 | 767, 769, 771, 775, 781, 813, 817, 875 |
| `--arc-gradient` | 721 | 无直接 var 引用 |
| `--arc-gradient-foreground` | 722, 864 | 无直接 var 引用 |
| `--arc-gradient-from` | 719, 862 | 721 |
| `--arc-gradient-ink` | 725, 867 | 无直接 var 引用 |
| `--arc-gradient-line` | 724, 866 | 无直接 var 引用 |
| `--arc-gradient-soft` | 723, 865 | 无直接 var 引用 |
| `--arc-gradient-to` | 720, 863 | 721 |
| `--arc-leading-body` | 752 | 577, 892 |
| `--arc-leading-display` | 751 | 576, 897 |
| `--arc-neutral-0` | 664 | 677, 678, 679, 821 |
| `--arc-neutral-1` | 665 | 无直接 var 引用 |
| `--arc-neutral-10` | 674 | 无直接 var 引用 |
| `--arc-neutral-11` | 675 | 681, 761, 764, 765, 820 |
| `--arc-neutral-2` | 666 | 680 |
| `--arc-neutral-3` | 667 | 762 |
| `--arc-neutral-4` | 668 | 无直接 var 引用 |
| `--arc-neutral-5` | 669 | 无直接 var 引用 |
| `--arc-neutral-6` | 670 | 无直接 var 引用 |
| `--arc-neutral-7` | 671 | 683 |
| `--arc-neutral-8` | 672 | 682 |
| `--arc-neutral-9` | 673 | 无直接 var 引用 |
| `--arc-paper-0` | 676 | 758 |
| `--arc-series-1` | 715 | 806 |
| `--arc-series-2` | 716, 860 | 807 |
| `--arc-series-3` | 717, 861 | 808 |
| `--arc-series-4` | 718 | 809 |
| `--arc-shadow-floating` | 712, 858 | 27, 582 |
| `--arc-shadow-raised` | 709, 857 | 581 |
| `--arc-shadow-resting` | 708, 856 | 580 |
| `--arc-space-1` | 726 | 579 |
| `--arc-space-10` | 733 | 无直接 var 引用 |
| `--arc-space-12` | 734 | 无直接 var 引用 |
| `--arc-space-16` | 735 | 无直接 var 引用 |
| `--arc-space-2` | 727 | 无直接 var 引用 |
| `--arc-space-20` | 736 | 无直接 var 引用 |
| `--arc-space-24` | 737 | 无直接 var 引用 |
| `--arc-space-3` | 728 | 无直接 var 引用 |
| `--arc-space-4` | 729 | 无直接 var 引用 |
| `--arc-space-5` | 730 | 无直接 var 引用 |
| `--arc-space-6` | 731 | 无直接 var 引用 |
| `--arc-space-8` | 732 | 无直接 var 引用 |
| `--arc-success` | 704, 852 | 782 |
| `--arc-success-subtle` | 705, 853 | 783 |
| `--arc-surface` | 678, 829 | 768, 793 |
| `--arc-surface-muted` | 680, 831 | 774, 776, 777, 780, 816, 868, 874 |
| `--arc-surface-raised` | 679, 830 | 770 |
| `--arc-text-2xl` | 745 | 570 |
| `--arc-text-3xl` | 746 | 571 |
| `--arc-text-4xl` | 747 | 572 |
| `--arc-text-5xl` | 748 | 573 |
| `--arc-text-base` | 742 | 567 |
| `--arc-text-lg` | 743 | 568 |
| `--arc-text-muted` | 683, 834 | 779, 810 |
| `--arc-text-secondary` | 682, 833 | 778 |
| `--arc-text-sm` | 741 | 566 |
| `--arc-text-xl` | 744 | 569 |
| `--arc-text-xs` | 740 | 565 |
| `--arc-tracking-body` | 750 | 575, 891 |
| `--arc-tracking-display` | 749 | 574, 896 |
| `--arc-warning` | 706, 854 | 784 |

## 验收记录

每片均在 apps/web 运行 `pnpm exec tsc --noEmit`、`pnpm test`、`pnpm build`。最终测试 44 个文件、411 项通过。产物包括浏览器端及 SSR 构建。

| 真实浏览器操作 | 结果 |
|---|---|
| Chrome 1280×820、768×820、375×820；中文深色与英文浅色 | Home、Projects、Settings、Login 在三种宽度通过。选择 Skill 后输入内容出现，搜索无结果，Escape 关闭弹层。 |
| 账户外观 | Light、Dark、System 切换写入原偏好；System 对操作系统明暗变更立即响应。 |
| 桌面与手机登录 | 请求验证码、错误验证码提示、焦点回到首格、正确码验证、跳转 Home 全部通过。使用隔离本地 API 邮箱接收验证码，未验证外部邮件投递。 |
| Home 首发 | 浏览器发起 1 次 staging 签名，1 次对象存储 PUT，1 次项目创建，1 次 attach，1 次 Chat POST；消息 API 返回 1 条持久用户消息。 |
| Projects | 真实项目列表、重命名并恢复、打开、等待详情加载后刷新并返回、按字段排序、搜索与清空均通过。 |
| 设置与焦点 | 真实偏好 PUT 成功后恢复原值。Settings → Add credits → Tooltip 分层 Escape；焦点回到 Add credits，再关闭回到账户触发按钮。 |
| 项目删除 | Space 勾选、焦点默认在取消、确认框拒绝 backdrop 关闭。注入批量接口 422 后，错误提示出现在当前 modal 且选择保留。使用真实 API 删除独立 QA 项目后返回项目库。 |
| reduced-motion | 三尺寸浏览器运行开启 reduce；弹层、切页、表单和键盘交互均完成。 |

此前一次快速详情刷新后立即后退在开发服务器触发 Router hydration 警告。等待详情加载再后退的回归通过。未验收实体设备、Safari/Firefox、外部邮件、外部支付或社交 OAuth。

截图按 `页面-宽度-主题.png` 命名。基线、U0 Home、U1 Login 与 U2 分别位于 [before](before)、[u0](u0)、[u1](u1)、[after](after)。Projects 基线测试账户为空；U2 使用隔离测试账户的真实首发项目。
