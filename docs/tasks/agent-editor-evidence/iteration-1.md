# Agent Editor v1 首次直接剪辑验收

2026-11-20，在原 checkout 的 `codex/agent-editor-v1` 分支施工。接管时 main/origin/main 是 `353f242d`。用户提供的合同位于 `docs/tasks/new-agent.md`，900 行，`taks/new-agent.md` 与 `tasks/new-agent.md` 均不存在。检查点 `09cf1873` 以该 main 为父提交，保存唯一未跟踪合同。§9A、§9B 及配乐事务测试已在父提交中。审计与首批实现提交为 `45224742`，直接剪辑与前端提交为 `49c60ce5`。施工使用原目录；接管期间短暂创建的施工 worktree 已移除，原有 adr117-credits worktree 继续保留。

## 用户任务

“把第二段视频从它自己的第5秒切开，然后播放成片第7到9秒，告诉我实际看到什么。”

使用本地隔离 PostgreSQL 数据库 `rep_editor_live_1120a`，测试账号先通过现有唯一写口保存一部 13 秒、3 个 Clip 的 Composition。前两段引用仓库中的带原声视频 `apps/api/test/fixtures/video_project/media/pricing-talk-source.mp4` 的不同源时间窗。开场提示只含项目、素材摘要、版本身份、3 个片段、1 个场景、时间基准和总时长。标题卡文字没有写在提示或 Clip 的标识里。请求经过带真实 JWT 的 POST /api/v1/chat、原生 ToolLoop、配置的 MiniMax-M3.1-Flash、真实数据库和本机 renderer。该请求使用 ASGI HTTP transport。后续浏览器和 Stop 使用隔离的本机 HTTP API。

[实际首轮提示、完整 wire schema、原生 call ID 与参数、执行回执、两版内容、活动和恢复记录](video-acceptance.json)

| 次序 | 原生调用或响应 | 核对结果 |
|---|---|---|
| 1 | inspect_timeline({}) | 正确读到 elm_b 为第二段，成片 3–11 秒、源片 30–38 秒 |
| 2 | split_clip({"clip_id":"elm_b","time":5}) | 以 90,000 ticks/s 保存 v2，成片切点 720,000 ticks、源切点 3,150,000 ticks |
| 3 | preview_range({"start_seconds":7,"end_seconds":9}) | 返回横跨两个 Clip 的 v2 预览。模型请求中含真正的 video_url、image_url 及解码帧的时间标签 |
| 4 | 助手发出正文，漏调终结工具 | 原有收尾规则要求再答一次，期间没有执行额外剪辑 |
| 5 | answer({}) 与最终正文 | 告知左右段为 3–8、8–11 秒，识读画面的 “The team workspace”、“Product, pricing and plans”、“A practical overview”，指出切点两侧相同 |

v1 为 `94c0877e-2e25-4a33-92d0-fd2f461acad8`；v2 为 `e7a3a401-110b-4aaa-9112-85ad05b8c9be`，base 指回 v1。左段沿用 `elm_b`，右段为 `clp_0a2683a736b15561aab50ae5bd7bb041`。两个未选中 Clip 的规范化 JSON 哈希在两版间逐一相等，settings、sources、scenes、轨道元数据及转场也相等。数据库中该作品只有这两个版本，验收库无 Run、Step 或交付 Output。信用账本仅有一条 grant，分割和本地预览没有触发 hold、capture 或 release。

## Chat 与真实媒体

三个 Activity 都有开始、完成及耗时，历史消息的正文与版本块和 turn.completed 一致。Chrome 打开项目后读取持久消息，拉取指定版本与 7–9 秒范围，实际点击播放；随后忽略缓存硬刷新，再次播放成功。两次底层 video 都是 readyState 4、paused=false，均无缓冲或 HTTP 错误。修复了 JSONB 字段次序变化导致有效范围在前端校验失败的问题。两次均未发起 Start。界面仍沿用非终结工具的内部 Activity kind=read，用户看到的分割文案由真实分割回执驱动。此次中文对话还保留了一句英文临时正文 “I'll look at the timeline first.”，最终答复为中文。

[硬刷新后播放器与 Chat 截图](chat-refresh.png) · [实际传给模型的 MP4](split-preview.mp4) · [8.733333 秒解码帧](split-preview.jpg)

局部画面为 320×180、30 fps、60 帧 H.264。AAC 双声道解码峰值 0.571、RMS 0.117，容器含编码填充共 2.048 秒，画面窗口为 2 秒。当前模型的音频感知标记为 false；本次可核实的是对画面的识读和文件中存在真实音轨。证据同时包含视频和一张真实帧，无法从回执区分模型识字时依赖哪一种输入。

## 指标和失败记录

最终视频任务的三个操作均首次给出合法参数，执行成功 3/3。计入终结工具后，实际产生的具名调用首次合法 4/4、执行成功 4/4。目标选择正确，重复写版本 0 次，无效收尾重试 1 次。5 次 provider 请求的 prompt tokens 为 2,990、3,556、3,363、4,140、4,170，合计 18,219，包含缓存及媒体上下文；completion 合计 743。供应商没有单列项目摘要的 token 数。首轮实际消息和参数可在 JSON 中复查。以上为单项任务实测，不是线上分布。

| 其他现场任务 | 真实结果 |
|---|---|
| 首轮形状素材 | 分割成功。两次预览调用同批被拒，旧窗口参数校验拒绝一次，后续提交半秒 MP4 时供应商 HTTP 400，Chat 未走完。由此改用成片时间窗，并把短窗代表帧明确标记为单帧证据。用户播放器仍保留原时间窗 |
| 第二轮形状素材 | 分割并观察到蓝色椭圆。最终文案泄漏技术 ID，终结动作漏调两次。调整保存作品的提示与正文规则 |
| 第三轮形状素材 | 分割并观察所请求的完整窗口。模型又请求两个更窄窗口，一次混合调用被拒，最终描述采用了额外窗口的近似时间 |
| 带原声视频 | 完成上面的用户任务。四个不同测试作品都只各新增一个分割版本，早期失败在上述相应环节发生 |

## 恢复、边界与可复查命令

- PostgreSQL 定向测试使用独立会话竞争同一 base，验证恰好一个成功、另一个 StaleBase。同一原生调用分别从旧、新 head 重放都返回同一版本及相同的左右引用。更改同一请求内容、切在边界或跨用户请求会被拒绝。Stop 在提交前可阻止写入，在提交后保留已保存版本。
- 另一次通过真实 HTTP SSE 发起分割，收到 turn.started 即 POST /chat/turns/{id}/stop。响应 accepted=true、turn_state=retracted。重新读取消息未见该回合，前后版本列表完全相同。此次 Stop 的位置在首个编辑动作前。尚无在数据库提交与 Chat 回执之间强杀进程、再重启客户端的端到端演练。
- 后端 `cd apps/api && .venv/bin/pytest test/core -q` 为 531 项通过、4 条 warning。包括作品事务、Stop、真实 PostgreSQL 的新分割测试，以及 §9A/§9B 的回归。前端 `cd apps/web && pnpm exec vitest run` 为 47 个文件、432 项通过；同目录 `pnpm exec tsc --noEmit` 通过。首个官网宣传片旧任务的第二轮验收未继续运行。
- 已保存工程的普通回合展示 8 个工具，包括全部三个直接编辑和观察工具；多个作品时可按明确作品名称或引用定位，过期、越项目和不明确的引用无法写入。仍需首稿、媒体后台续接或交付确认的路径有旧消费者。当前不支持在保存作品工具面执行 trim、move、translate、scale、关键帧或媒体生成；这些属于后续迭代。小于一秒的预览在当前模型上只以真实抽帧作证，听感、动态素材跨切点的运动质量以及生产库负载均未在此次验收中评定。
