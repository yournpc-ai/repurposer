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
