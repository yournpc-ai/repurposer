# Iteration 5 在 main 的收口验收

本轮在本地 PostgreSQL 隔离库、独立 S3 兼容桶、真实 Worker、Remotion 和 Chrome 上运行。Chat、正式审阅、语音及配乐使用项目配置的供应商。所有下列账号、对象和扣费记录均来自本轮验收。供应商账单按应用实记用量报告，尚未对账最终发票。

## 整合与提交

- 重新 fetch 后，双方 main 均为 `32f04518`。Iteration 5 领先 13 个提交，落后 0 个，包含 `13670989`。本地 fast-forward 至 `ad3f972c`，完成测试并普通推送，随后独立查询了远端 ref。
- 主目录的 `.dockerignore` 是忽略 Web 本地环境文件的改动。未跟踪的 `apps/web/src/components/ui/thinking-loader.tsx` 是单独的 UI 实验。证据目录的 `.chat-refresh.png.swp` 当时由 Vim 持有。三者均保留。修改过的 `apps/web/components.json` 与 Iteration 4 提交的完整 blob 相同，整合后自然成为干净文件。四项内容和 diff 都在主目录以外备份，未提交用户私有备份。
- 两个此前已有的 Iteration 工作树、主开发库、用户历史作品及手工修改均保留。后续施工直接在 main 上进行。
- `d6566cab` 实现同窗比较和冻结源参照。 `de33e0f4` 接入作品创建和初稿范围。 `e664da36`、`25362e84` 实现按 step 恢复上传并验证并发条件写。 `228430b5` 删除重复分派，统一保存回执、审片前提、续改交付上下文和费用确认。 `a8c45326` 保留取样时点，并收紧费用意图不明确时的处理。

产品依据是完整的 [Agent Editor 主合同](../../../new-agent.md)。工程约束来自 CLAUDE.md、PROGRESS §0、VIDEO_PROJECT、CHAT_ARCHITECTURE、RENDERING 和 VERIFICATION。原始负例可从[现场审计](../../audit.md)、[第一轮](../../iteration-1.md)、[第二轮](../../iteration-2.md)、[第三轮](../../iteration-3.md)、[Studio 验收](../../iteration-4/README.md)及[第五轮原始验收](../README.md)回查。

## C1 从实际视频判断构图

两次原始访谈测试均从同一份三秒素材开始。初始绝对变换为 x=110、y=35、scale=2.6。同一个时间窗和正确的作品一直可定位，模型也收到了成功写入的版本。第一条产生 v2–v10，期间 scale 从 1.0 增至 1.18 又回到 1.0。第二条产生 v2–v11，绝对位移在 (60,90) 和 (−60,−90) 之间跳变。两条都用尽 20 次决策，最后修改没有复看。轨迹没有证明渲染器把位移方向反转。模型把留边、裁切和填满画布交替当成了修订依据。旧媒体随版本失效后，模型缺少同窗旧帧及未裁切的来源参照。[原始调用一](../wire-visual.json.gz) · [原始调用二](../wire-visual-final.json.gz)

`preview_range` 现在一起提供当前 MP4、时间标记帧和最近一次匹配的旧帧。匹配要求为同一作品、同窗、同一组实际取样时点及不同版本。两组像素分别标注版本。对于可验证的单视频布局，另外读取固定 SourceSnapshot 的同一源时点，在匹配摘要后才提供源帧。符合几何计算条件时同时报告源画面在画布的边界。当前版本的导出资格仍只接受当前预览。用户明确要求先看片再决定是否编辑时，首个写入核对已实际送达的预览。独立的明确编辑指令仍可直接执行。

仅补旧帧的第一次重测中，一条再次耗尽上限，另一条误把黑边当作源素材自带。加上源参照的中间样本又发生额外正式导出，随后补齐本轮交付范围与费用回路。这些失败保留在 `visual*` 的 native wire 与账本中。后续 `frame-right` 虽结束且构图正确，仍然经过七次编辑。最终报告分别计算目标结果、重复编辑和请求数。

`left-head` 与 `right-head` 用原话复跑。两次 0–3 秒复看均在 1.466667 秒比较实际帧。源边界从 [10,−109,530,359] 收回至 [60,0,260,180]，源画面 240×216 完整居于 320×180 画布。两次最终像素一致，脸、头顶及肩部的可见范围恢复，左右自然留边。分别执行 2 和 3 次编辑，无完全相同的编辑参数重发，均主动结束，正式 Output 为零。一条首个 `inspect_clip` 的目标无效并得到明确拒绝。[修改前](left-head-1-3b336f4c.mp4) · [修改后](left-head-2-c21876fe.mp4) · [两次原生比较一](wire-left-head.json.gz) · [比较二](wire-right-head.json.gz)

## C2 首稿与保存版

普通空项目直接调用 `create_video`，传入有意义的镜头、文本、颜色、运动及持续时间，由唯一 Composition 写口保存。创建和之后的编辑共享作品投影。现有项目锁与 opening 回执绑定首版创建，原生调用重放取回同一版本，参数改变被拒绝。PostgreSQL 竞争测试让两条 opening 同时创建，只出现一部作品、一个版本。

“做一个三秒钟的白色文字静态字卡，只要初稿，不要正式导出” 保存 v1。没有指定文案的样本使用项目名「空项目首稿」并在回复中告知。另用历史失败原话重测了指定文案 Goodbye。两者的版本均为黑底、原生白色标题、零动画、零来源，未生成正式 Output。QA 通过预览端点渲染保存版，全片解码 90 帧。视频流恰好 3.000 秒，带 AAC 填充的容器 3.050667 秒。「空项目首稿」所有帧至少有 17,677 个 RGB 三通道均大于 245 的像素，与首帧的最大逐通道平均差为 0.00351 灰阶。重放实际原生 call ID 返回原 v1。[三秒字卡](title-head.mp4) · [指定文案](goodbye.mp4) · [像素、版本及重放](title-head-pixels.json.gz)

`title-head` 的回复把播放窗口误述成在 0、1、2、3 秒分别取得静帧，实际静帧只在 1.466667 秒。修复把实际时点保留到下一次模型决策的当前预览上下文。`sample` 在追加“告诉我抽取的是哪些实际时点”后准确报告 1.466667 秒与 0–3 秒播放范围。早期 `card` 的时长参数传入字符串，运行端转换为数值，统计仍记原生 Schema 首次不合法。[错误回复与后续回放](chat.json.gz) · [修复后的模型输入与回执](wire-sample.json.gz)

## C3 固定版本、文件、账本及强杀

正式输出复用原 WorkflowStep。对象 key 包含用户、工程、Output 及按固定 step、版本、spec 派生的身份。首次上传使用签名条件写。并发上传遇到已存在的对象时，Worker 重读文件、探测编解码器与时长、计算 SHA-256，最终事务继续校验 claim。已提交文件复用时也校验已有摘要。无归属证明的历史对象保留。

在上传并探测通过、数据库仍为 rendering 的窗口，故障 Worker 向自己发出 SIGKILL。恢复日志为 `reused_upload=True`，前后的 SHA-256 都是 `3cb376b9ea82068643eb430b0d876eeb5c5c90f41459e1b07a082ae2b3a5c724`。该次项目输出前缀仅一项，同一个 Output 完成。账本为 hold −9、release +9、capture −9。恢复后的字节还经过浏览器播放和刷新。这里检验的是上传完成、结果尚未提交的 Worker 故障窗口。[强杀现场](worker-interruption.json.gz) · [对象、摘要与账本](worker-recovery.json.gz) · [桌面实播](browser.json.gz)

复现时在独立 `rep_closure_*` 本地数据库和 `closure-*` 测试桶运行 API、Renderer，在同一环境中从 `apps/api` 启动下面的故障 Worker，向所选 QA 项目发送真实导出请求。看到 boundary 文件且该 Worker 退出后运行正常 Worker，核对 boundary 中的版本、Output、文件及账本。

```sh
PYTHONPATH=. .venv/bin/python ../../docs/tasks/agent-editor-evidence/iteration-5/closure/interrupt_worker.py "$QA_PROJECT_ID" "$QA_BOUNDARY_FILE"
PYTHONPATH=. .venv/bin/python -m app.worker
```

## C4 入口、续改和恢复

普通首稿、保存作品、图像、TTS、BGM、审片、导出、交付、续改使用原生 Editor 工具。两种 Chat 分派中的重复 `_design_video` 实现已删除，两个旧 Prompt 不再要求普通创作走 `design_video`，已经无效的图操作阶段条目也已删除。ToolLoop 从实际写口回执读取保存事实。普通首稿与保存后编辑无须生成 Plan，只有正式执行使用既有 Run/Step。网站简报、绑定 Skill、已存在的工作稿仍消费专用设计及工作稿审阅。手动 Graph、历史作品读取、真实授权与账本继续有消费者。本次未迁移这些专用职责，也未据此宣称全部设计旧代码退役。

- A 和 E。Studio 先看片再移动尾卡，把 4.5–6 秒移至 3–4.5 秒，复看后导出、正式审阅、Chat 交付。用户仅说「结尾再留半秒」后获得 v3，唯一新增编辑为 `extend_still(seconds=0.5)`。v2 和 v3 视频流分别 135、150 帧，结算 9 和 10 积分。两次硬刷新以及续改后再次打开旧卡均播放正确文件。修复前两条续改只保存 v3，没有交付；这两个历史失败见 `revision` 和 `final-revision`。[首次成片](fourth-studio-delivery-v2.mp4) · [续改成片](fourth-studio-delivery-v3.mp4) · [实际播放时钟及 URL](observed-browser.json.gz)
- D。实际生成约 2.13 秒英文旁白和 4 秒配乐。两份固定来源分别插入作品开头，保存 v2 与 v3，前四秒混音实播。模型侧收到视频及混音量测，provider 能力位表明无法直接感知视频声音。蓝底白圆图片任务生成两次，第一张边缘不符合要求，第二张成为可用素材。两次图像生成各有独立执行与 1 积分结算。[实际混音](sound-head-1-eb258236.mp4) · [媒体决策](wire-sound-head.json.gz) · [图片调用](wire-image.json.gz)
- F。Stop 先到返回 retracted；保存先到返回 cancelled 并保留 v2。另一条在版本已提交、活动仍 active 时对 API 发出 SIGKILL。两次历史读取逐字节相同，只有一条已保存说明和一个 v2。引用历史成片要求冲突即停也确实停下。跨回合主动重发复用原 Output，每个交付 opening 只有一张对应卡。早期批准后出现第二次报价，跨 Session 返回 detached Message 引发 SSE 失败。修复后批准精确原版本，answer.completed，交付一个 Output、capture 12 积分。自动授权账号对时长查询误调导出的回归验证无 Run、无预占。[API 中断](ack-boundary.json.gz) · [恢复历史](ack-restored-1.json.gz) · [Stop](save-first.json.gz) · [历史冲突](wire-stale.json.gz) · [重发](wire-resend.json.gz) · [实际批准](wire-approved-final.json.gz)
- G。Chrome 1240×880、390×844 都展开了实际并列生成旁白和配乐的 Tool Group，硬刷新后成员及状态一致。移动端打开指定正式视频，播放时钟推进，刷新后再次播放，发送新消息并在刷新后找回。桌面通过 Studio 发送首轮与续改。[桌面组](group-1240.png) · [手机组](group-390.png) · [手机播放](mobile-play.png) · [回读](mobile.json.gz)

## 五面交叉复核

| 切片 | Tool Call | Context | Chat Message | Execution | Recovery |
|---|---|---|---|---|---|
| C1 | inspect、scale、translate、preview_range | 固定源参照、同窗新旧像素、绝对坐标、版本摘要 | 回复给出主体、边界、时长和未检查范围 | 已保存 v3/v4 都能解码到同一最终画面 | 历史帧带旧版本，正式导出验证当前预览 |
| C2 | create_video、按需 preview_range | 用户原文、镜头范围、颜色、文案和实际取样点 | 保存的初稿卡可刷新，原始取样误述与修复均保留 | 三秒原生文本、无运动轨、无正式媒体结算 | 复用真实 call ID 取到同一版本，并发首稿只有一个成功创建 |
| C3 | export_video、review_video、deliver_video | 确切版本、Output、摘要、已交付回执 | 两个版本各一张交付卡，重新打开旧卡播放旧片 | 条件 PUT、重读文件、按原 step 结算 | 两次独立 SIGKILL 演练复用原上传，按不同 Output 检查实际引用 |
| C4 | 普通首稿、编辑、媒体、授权续行均用原生声明 | 刚交付的上一轮回执及本轮修订目标 | Stop、费用问题、SSE、Tool Group 与历史读取 | 修改与交付通过原写口和 Worker | 已提交未回执的编辑回读、StaleBase、重复请求和费用重放可核对 |

## 任务与计量

以下六次验收的作品目标均达成。按包括 Chat 取样事实在内的严格标准，首次逐项通过 5/6，初稿的额外取样叙述随后单独修复验证。两条访谈是相同失败夹具的独立复跑。开放任务 `open` 这一次完成了正式交付，期间一次不必要的放大造成字幕左侧裁切，随后复看纠正。一次完成不足以估计开放创作在不同素材上的成功率。

| 任务 | 模型请求 | 原生参数合法 / 调用 | Prompt / Completion tokens |
|---|---:|---:|---:|
| 两卡看片与正式交付 | 16 | 15/15 | 215824 / 3849 |
| 延长半秒并交付新版 | 9 | 7/7 | 86059 / 839 |
| 访谈复跑一 | 7 | 7/7 | 68116 / 971 |
| 访谈复跑二 | 9 | 9/9 | 91128 / 1516 |
| 三秒白字静态初稿 | 3 | 2/2 | 28737 / 559 |
| 旁白、配乐、插入、预览 | 4 | 6/6 | 41911 / 793 |

请求包含为这条 opening 记录的 provider 请求。Schema 以当次请求真正提供的参数定义复核。每个工具的首次合法性、原生参数、执行状态和每次请求 token 见明细。续改有一次过早导出被拒。当前两卡样本在导出前多次查看相同且内容未变的窗口，部分额外观察仍可减少。每次独立的模型或媒体生产也有成本。[逐调用指标](metrics.json) · [SSE](chat.json.gz) · [版本、来源、消息、Output、用量与账本](database.json.gz) · [媒体摘要和逐流解码](media.json)

### 最终代码上的并发复跑

额外在同一个 API 进程同时启动两条访谈、一条空项目字卡、一条配音配乐、一条正式交付和一条含两种时序的 Stop 旅程。首次触发了 3 次 SQLAlchemy QueuePool 超时。SSE 已有自己的执行 Session，路由的权限预检仍占着连接，版本读取 Session 也在等待 Renderer 或媒体任务时占用连接。提交 `7e1207a2` 在权限核验、不可变渲染规格构建及媒体交接后释放只读连接。数据库池配置与事务围栏保持原值。相同入口和并发量复测，五条创作请求均完成，两次 Stop 均获预期回执，池超时为 0。随后在 Studio 原句续改并交付 v3。此次六个作品目标完成 6/6。这个分母包含续改，不含 Stop、故障注入和问答。[最终逐项核对](checks.json) · [初次并发失败与后续 SSE](chat.json.gz)

| 最终验收 | 请求数 | 参数合法 / 原生调用 | 输入 / 输出 tokens | 结果 |
|---|---:|---:|---:|---|
| 自主看片至交付 | 10 | 9/9 | 101519 / 1625 | 首次预览在 move_clip 之前，v2 正式交付 |
| 继续延长半秒 | 10 | 8/8 | 97710 / 910 | 一次过早导出被拒，复看后交付独立 v3 |
| 原访谈一 | 6 | 6/6 | 59318 / 1658 | 两个编辑，复看后结束 |
| 原访谈二 | 10 | 10/10 | 100146 / 2010 | 一个无效目标被拒，三次编辑，复看后结束 |
| 三秒静态白字 | 2 | 1/1 | 17885 / 321 | 只调用 create_video，保存同一 v1，无 Output |
| 生成音频并插入 | 5 | 6/6 | 50546 / 700 | 2.763 秒旁白及 4 秒音乐从开头进入 v3，实播前四秒 |

两条访谈都保留三秒、达到相同的完整源取景，没有重发相同的编辑参数。独立事务在实际 `extend_still` 写入前推进 head 的试验中，Agent 收到冲突并按要求停手。续改后 v2 与 v3 各有一张正式卡，视频帧数及媒体 SHA 可从 manifest 复核。最后一次字卡复用实际 call ID 仍只得到一个 v1。第二次独立强杀的输出前缀后来包含两份文件，它们分别被 v2 与用户续改后的 v3 正式引用。本次没有发现无引用文件。[访谈一](wire-pool-left.json.gz) · [访谈二](wire-pool-right.json.gz) · [字卡像素与重放](pool-card-pixels.json.gz) · [混音实播](pool-sound-1-36a935ab.mp4) · [SSE 与浏览器](pool-play-browser.json.gz) · [竞争写入边界](race-boundary.json.gz) · [第二次强杀和双版本账本](release-recovery.json.gz)

38 个隔离项目含调试与负例。按唯一账本行去重，共 21 次媒体 capture、153 积分，独立 ConversationUsage 合计 0.523205 美元。实际 15 个正式 Output，同一版本的重复 Output 为 0，同一 opening 同一 Output 的重复交付卡为 0，重复 capture 幂等键为 0。账户往来、模型用量和供应商最终发票是不同口径。最终 API core 为 514 passed、4 项既有告警，Web 为 411 passed，Renderer 上传测试 8 passed。Web TypeScript 和生产构建通过，24 个不同 MP4 文件均完整解码。[检查汇总](checks.json)

六项完成率按作品目标计。第二条访谈的最终回复中出现了“黑边已消除”。解码帧及源边界显示过大的单侧留黑已经纠正，但画布左右各保留 60 像素。该条的构图与停止条件通过，Chat 对留边的描述未完全通过。另一条对左右留边的描述与成片一致。[逐字回复和最终变换](checks.json) · [最终画面](left-head-2-c21876fe.mp4)

**开放项。** 当前部署模型没有可证明的主观听感。开放创作、不同拍摄素材的审美判断、Chat 视觉描述准确性和高负载容量仍需更多独立任务验证。专用网站和 Skill 的旧草稿职责仍在使用。首次池超时、早期构图及续改失败和初稿取样误述均保留，完整 Iteration 5 Closure 继续开放。

从仓库根目录可离线复核提交中的媒体与回执。

```sh
apps/api/.venv/bin/python docs/tasks/agent-editor-evidence/iteration-5/closure/verify.py
git log --oneline 32f04518..ad3f972c
git merge-base --is-ancestor ad3f972c main
```

证据中相同 SHA-256 的媒体只保存一份。`media.json` 的 artifact 指向该文件。原生请求保留工具 Schema、上下文及媒体身份，内联媒体按摘要记录，供应商私有推理、访问凭据与签名查询参数已移除。
