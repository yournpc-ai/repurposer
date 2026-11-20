# Iteration 4 实测

## 4A

基线 32f04518。隔离库 rep_editor_i4_1121 复制自上一轮验收库，独立 S3 测试桶 editor-i4，原开发服务继续运行。Chrome 1360×900 与 390×844 通过真实 Home 发送，两端各运行一次纯文本与一次 2477261 字节 MP4。四个项目各有一次 POST /chat。见 home.json 的项目、POST 请求、流帧、持久 opening ID 和刷新后从 Projects 重开的正文。home-wire.json.gz 保留每轮声明、输入和原生响应。模型在部分中文请求中回复韩语。手机图片来自已上传真实文件的页面。

opening-recovery.json 记录同时首发、Stop 撤回后的重放、延迟历史 503 后手动重新加载、重新登录后保留草稿。登录使用正式验证码生成和校验，邮件服务在本机接收验收邮件。桌面系统浅色、手机系统深色。未将浏览器注入会话用于验证邮件投递。

消费者核对：原 projects.$id.index 是唯一 ProjectHeader 使用者，已迁到 _app 父级并保留 ProjectMenu。RecipeShelf、RecipeTabs 和 recipeFamilies 的 import 只有旧首页与货架内部，已连同滚动计算、停靠样式删除。HomeComposer 和项目消息归档、Stream、Question、播放器保留。首发用项目作用域的持久 opening 与消息序号核对，序号跨零可见撤回保留。

## 4B

新 Thread 经真实浏览器完成第二段本地第 5 秒分割、保存和局部播放。split-final 预览为成片第 6–10 秒。硬刷新后同一视频可播，随后模型从保存版读取两段时长。另一个隔离工程在同一界面分别拒绝、同意真实 TTS 报价，点击授权后的原声，Stop 返回 retracted 并恢复原稿。thread-wire.json.gz、thread-chat.json、thread-database.json.gz 与 thread-browser.json 分别记录原生请求和上下文、流帧、版本和费用、实际媒体时钟。早期预览因隔离桶没有给 renderer 提供 fixture 读权限而失败，配置本机桶并使用匹配版本的浏览器后重测。

项目路由原为 ChatDock 唯一运行时消费者，始终传 full、canvasAvailable=false。现在使用 AgentThread。删除无人调用的面板模式、位置存储、隐藏/召回、全屏固定容器、画布插入 ref 和页面重复的 Run SSE。保留了真实的 ChatConversation、时间线投影、输出查看器、费用问题和媒体控件。Web 432 项通过，TypeScript 通过。

## 4C

`batch-wire.json.gz` 保留 MiniMax 的请求、Tool Schema、原生响应、模型使用量和下一次决策的消息。流式响应的工具列表位于 tool_calls，整包响应位于 choices[].message.tool_calls。共捕获 13 次多调用响应、28 个原生调用，含第一次投影失败的回归样本。逐次 decision ID、原始序号、实际状态见 `batch-trace.json`。实际数据库、版本前驱、内容和积分交易在 `batch-database.json.gz`，原始 SSE 在 `batch-sse.json.gz`。观察、收据和卡片均按 opening 与原生调用身份关联。仅 inspect_clip、inspect_timeline 可并发，使用同一固定版本、各自的短数据库会话。媒体与写版本在组内依次提交。

| 核对 | 实测凭据 |
|---|---|
| 两个独立读取、同名调用 | batch-reads2 同一响应包含 offset 0 与 2 的 inspect_timeline，均返回 v1。 |
| 同批媒体、下一次决策插入 | batch-media 同批提交旁白与配乐。两份音频可读，模型下一次使用实际 snapshot_id 插入 v2；账本 hold −2、release +2、capture −2。 |
| 两次已知对象写入 | batch-edits 的 scale、translate 原生调用依次产生 v2 和 v3；前者的版本在下一次请求标为 superseded，后者为当前 head。 |
| 部分失败、乱序完成 | overlap 同一响应含四次 inspect_clip。SSE 的终结顺序为索引 1、0、3、2，缺失片段返回失败。下一次输入与展开的记录保持声明顺序。 |
| 批次中 Stop | Chrome 在真实 preview_range 执行中点击 Stop。返回 200、cancelled；硬刷新显示第一项已停止、第二项未执行。 |
| 费用授权和拒绝 | batch-ask 的第一项出示 2 积分上限，第二项未执行。Chrome 拒绝，数据库无 hold 或 capture，历史第一项为 cancelled。 |
| API 强杀、Worker 晚到 | proof-interruption 在真实旁白已提交给 Worker 后强杀独立 API。Worker 补齐旁白，关闭原组内未开始的音乐。恢复决策生成缺少的配乐。最终仅一张旁白卡、一张配乐卡及一次 2 积分扣款。早期试验曾重复出现旁白卡，已按原 opening 的成功回执修复。 |
| 已提交版本及刷新 | cas-interruption 在第一条写入完成帧到达时强杀 API。两个写口已实际提交；历史报告 v2/v3，四次硬刷新均为同样五行，库中仅 v1/v2/v3。 |
| 真实分组界面 | group-desktop.png 与 group-mobile.png 来自实际项目。batch-browser.json.gz 含展开内容、主题、视口、刷新前后逐项状态及真实 Stop 结果。 |
| 首发引用、历史交付 | 另一次 Home 实发携带 asset mention、MP4 附件及 text-animation 1.0.0。隔离库原有零个 Output；用现有 renderer 生成 v1 的真实 18.048 秒 MP4，建立固定历史引用并归档，再经消息卡打开。实际播放时钟在 0.428 秒，readyState 4。随后从 Thread 发出 trim_clip 并保存 v4。 |

首次试跑遗漏 BatchMember 投影分支，表现为整回合失败，修复后重新执行。历史 Output 的首次本地渲染在 undici 读取测试存储时断开，重测使用隔离的渲染器缓存和同一源文件字节。未人为制造真实付费供应商丢单；未知结果走已有 Worker 的类型化失败事实。本轮未代用户重试未知订单。

### 调用数、版本竞争与回执边界

在 4C 检查点捕获的 13 个多调用响应中有 28 个原生调用。逐个匹配当次请求的工具声明，再用对应的 Pydantic 参数模型重验，28 个参数均合法。26 个出现持久组成员，23 个具有执行开始时间。最终 18 个完成，3 个执行失败，2 个停止（含拒绝授权），3 个未执行。余下 2 个来自修复前第一组，缺少持久回执。业务提交分别用版本、Worker 任务或费用交易核对；开始执行读取不产生版本。每次决策的 usage 在 wire 中，此批所有请求的输入为 5,630–15,213 tokens。补验的 JSON、竞争与强杀样本单列，未重复计入这 28 个。[逐项核对](batch-admission.json) · [模型决定](batch-trace.json) · [实际收据](batch-database.json.gz)

在真实模型的一组 `scale → preview_range → translate` 中，另一个会话从 v2 走同一生产写口提交了 v3。缩放保存为 v2，预览读取 v1 的指定窗口，平移校验本组的 v2 并失败。初测中写口提示重新变基，模型在新决策重读后又执行，与用户要求冲突后停止不符。修正错误观察后，同一原文重测只留下 v1/v2/v3，v3 保留另一编辑者的修改；模型报告基线为 v2，字幕仍为原位置。[三次数据库与分组状态](competition.json.gz) · [原生请求与后续观察](studio-wire.json.gz)

另起隔离 API，在调用生产 Activity 的完成写口之前接入一次性进程故障注入。独立数据库会话确认 v2 和请求身份已提交、同一 Activity 仍为 running 后，向该 API 发 SIGKILL。正常 API 通过浏览器历史读取恢复，第一项由版本事实变为 completed，第二项为 not_executed。四次硬刷新均只有 v1/v2，正文只交代已保存的缩放。API 请求和 Worker 均走原实现。[强杀点与四次重读](ack-recovery.json) · [数据库](final-database.json.gz) · [浏览器](interrupted-group.png)

## 4D

最后一次从 Projects 搜索、排序并打开历史项目，分别使用 1360px 浅色中文、390px 深色英文和 768px 跟随系统（系统深色）中文。三次页面可用宽度均等于视口，控制台未收到页面异常，手机从 Thread 返回作品库再回 Home。正式路由由 TanStack 生成。最终真实 Thread 的四次同名调用中一项失败，三项成功，刷新前后的原生 ID、顺序与逐项状态相同。同一回合结束，顶部余额只回读一次并收到 HTTP 200。开发环境的 Router 调试钮曾遮住手机右下角发送区。现按需通过 VITE_ROUTER_DEVTOOLS=1 开启，默认界面三种宽度均只有一个 StudioHeader。390×844 的 Chrome 触摸会话实际点击 Home 的发送按钮，上传真实 MP4，然后从 Projects 重开，再点击项目输入框的发送按钮。后台收到两条不同的用户消息，各返回一次终帧。[最终浏览器事实](studio-browser.json) · [真实分组](thread-group.png) · [手机界面](studio-mobile.png)

移动端从消息卡查看真实生成的图片，硬刷新前后解码同一摘要的 1920×1080 PNG。归档的 18.048 秒 MP4 在最终界面重新播放，readyState 4，时钟前进。历史回放使用隔离工程中实际渲染的旧版 Output 和为验收写入的固定历史消息引用。4B 另有原生音频、局部预览与新版本回复。中文首发初测出现韩语和越南语提示，排查到语言检测误判了纯汉字输入。修复后用相同原文重跑，真实模型以中文回复素材数 0。[图片弹窗](image-dialog.png) · [归档视频](historical-output.png) · [最终模型输入](studio-wire.json.gz)

使用最终代码重新启动隔离 Worker，另一个临时 API 在原生 voice/music 组提交旁白后被强杀。Worker 处理已提交的旁白，恢复决策补齐配乐。四次硬刷新均为同样的七行，只有一张旁白卡、一张配乐卡及一次 2 积分 capture。[Worker 重读](late-worker.json.gz) · [最终账本](final-database.json.gz) · [触摸首发](touch-home.png)

### 删除与保留的调用方

| 切片 | 删除依据与保留入口 |
|---|---|
| 4A · a82e3469 | 基线的独立项目页独用 ProjectHeader，Home 独用 RecipeShelf、RecipeTabs 和 recipeFamilies。项目页迁到 _app，重复页面壳与首页滚动货架同期删除。|
| 4B · d428a46a | 项目路由是 ChatDock 唯一调用方，始终使用全屏模式。删除面板坐标、召回、旧全屏容器和页面级重复 Run 订阅。沿历史 Run 消息读取已存在的 RunCard；普通剪辑走 AgentThread 的工具组。|
| 4C · b9c9c130、e413b4dc | 删除前台整批拒绝和按最近同名活动关联的路径。SSE、非流式 HTTP 与 Worker 复用同一 Activity 写口。单调用与历史记录继续用现有 ConversationContext、版本和媒体表，无数据库迁移。|
| 4D · 120a96a9 | 将 MobileHeader 与桌面顶栏合并，删除不可见的 ModelsPanel、stickyCompletedRun、伪造的 produce_video 缺省值、传递路由及无入口的 ResultsCanvas。FlowView 的唯一调用方是 ResultsCanvas，连同节点、边、摄像机、布局、Canvas 可见性与其专属测试删除。图节点是 sound-mutex 的唯一声音状态读者，移除其空提供者。移除唯一图依赖 @xyflow/react。历史图、字幕、版本和 Output 的服务端数据保留。|

可在仓库根目录复核以下调用点。第一行列出旧消费者，第二行在最终源码应无匹配，第三行给出唯一 Shell、Thread 和账户栏的实际挂载点。

```sh
git grep -nE 'import .*MobileHeader|<ModelsPanel|stickyCompletedRun|<FlowView' b9c9c130 -- apps/web/src
rg -n 'import .*ChatDock|<ModelsPanel|<FlowView|<ResultsCanvas|stickyCompletedRun' apps/web/src
rg -n '<(AppSidebar|StudioHeader|SidebarProvider|AgentThread|CreditsPill|NotificationBell)\b' apps/web/src/routes apps/web/src/components/StudioHeader.tsx
```

### affectUI 源码与依赖

本机可读 affectUI、affectUI Screens 技能。通过已认证的 MCP tools/list 核对四个工具，再读取 Registry 中的八份实际源码，包括 Pro Screen。App Shell Inset 的面板与容器、Start 的输入内容区、Folders 的网格和搜索排序、Thread 的阅读列及 ToolCallGroup 折叠结构接在现有路由和组件上。保留产品 Composer 的上传、mentions 和 Skill，Markdown 使用现有 Streamdown。未移入 Screen 的示例项目、本地回复、仿真上传/Stop、嵌套 AppShell、假计时步骤及任务页。图标沿用现有 Lucide，无新增运行时包。已登记 Registry 的环境变量名，凭证和 Pro 源文件不入库。[核读源码的 SHA-256](registry.json)

### 五面复核入口

| 切片 | Tool | Context | Chat | Execution | Recovery |
|---|---|---|---|---|---|
| 4A | home-wire 的真实读取 | structured_opening 的原文、mention、附件和 Skill 及对应 studio-wire | home 的首条 SSE | 创建与关联请求、opening ID | opening-recovery 的双击、竞争、慢历史及重新登录 |
| 4B | thread-wire 的 split_clip、preview_range、生成和授权 | 同一 Composition 的目标片段与版本 | thread-chat 的活动、问题、正文和预览块 | thread-database 的版本、账本，thread-browser 的媒体时钟 | 硬刷新、拒绝及同意后的后续消息，Stop 的草稿 |
| 4C | batch-admission 的逐项原生身份与参数校验 | batch-wire 的版本、superseded 观察、实际来源 ID、usage | batch-sse 的组声明和乱序完成 | batch-database、competition、final-database 的保存、竞争与费用 | batch-browser、ack-recovery 的 Stop、晚到、强杀和四次刷新 |
| 4D | studio-wire 的四次同名调用与 JSON Chat | 修正后的中文上下文与归档媒体引用 | studio-browser 中 live 与 restored 原样核对 | 同一媒体摘要、播放时钟与余额回读 | 三种视口导航、历史深链、移动弹窗与刷新 |

### 测试与边界

- 隔离 API 环境运行 `python -m pytest -q test/core`，511 项通过，4 条既有警告。Web 运行 `pnpm test`，44 个测试文件、411 项通过。清理前有 433 项，删除的 22 项全部属于已无消费者的图布局、摄像机和 Canvas 显隐。TypeScript `pnpm exec tsc --noEmit` 与生产客户端、SSR 的 `pnpm build` 通过。构建仍提示个别 chunk 较大。[命令结果](checks.json)
- 在仓库根目录运行 `python3 docs/tasks/agent-editor-evidence/iteration-4/verify.py`，可离线交叉核对浏览器、原生响应和数据库身份。用于实测的库、桶、API、Worker、回环验证码收件器与 renderer 都独立于原开发环境。远端生产上传桶、生产数据和投递服务不在本次验收范围。
- 费用不足及供应商提交后结果未知由受控回归覆盖。真实授权拒绝、批准扣款和后台晚到已实测。第三方真实丢单、生产邮箱及移动真机未实测，手机证据来自 Chrome 移动视口。部分底层工具错误原文为英文，界面逐项状态有中英文。Iteration 5 的自主审片与正式交付仍待施工。
