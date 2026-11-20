# Iteration 3 · 在已有作品中生成媒体并继续剪辑

2026-11-20。在两个隔离的测试工程中实跑 MiniMax 原生 ToolLoop、PostgreSQL、Worker、对象存储、对齐、Remotion 和 Chrome。素材来自仓库内视频，两个工程先经正式写入口保存为 18 秒访谈。主旅程将英文男声与轻电子配乐剪入同一部作品，v1 → v2 → v3。另一个故障注入回合在双进程重启后续剪至 v6。可直接检查[开场混音 MP4](iteration-3/media/mix-a4c3a33a35.mp4)、[刷新播放截图](iteration-3/mix-refresh.png)和[重启后的桥段 MP4](iteration-3/media/fault4-3667f9ec99.mp4)。

## 接管与删除

接管时指定分支、本地 HEAD 和远端分支均为 `31ac7cd6`。原目录存在开发服务与编辑器。施工在独立 worktree 的 `codex/agent-editor-v1-i3` 进行，保留原工作树和用户数据。施工基于主合同、先前的审计、两轮验收、压缩的原生调用、逐版内容和实际预览。Iteration 1 证明一条原生 `split_clip` 足以完成精确分割；Iteration 2 证明同一回合能连续保存五版，每次继续时均取得新版本。两轮均使用原有编辑引擎。

此前模型选择生成媒体后，`video_turn_seats` 将未命中写成待处理任务，`dock_media_observation`、`_dock_tasks` 和 `plan_turn` 组织计划和启动。Worker 完成后，`continue_media_journey` 再把结果拼成下一轮规划。草稿版本和授权分属不同事务，Chat 的计划状态也无法证明素材已固定或影片已写入。

| 位置 | 实际处理 |
|---|---|
| `chat/media_journey.py`、`plan_turn.py`、`propose_turn.py` | 删除 `media_task_from_observation`、`dock_media_observation`、`_dock_tasks`、`initial_media_journey`、`continue_media_journey`、`finish_narration_batch` 及自动 Start、工作草稿恢复、阶段续行分支。历史在途媒体仍能 Stop。 |
| `turn_tools.py`、`video_turn_seats.py`、`chat/prompts.py`、`prompts/chat/` | 移除旧媒体准备的模型席位、工具按制作阶段筛选、`turn.media_state`、`audio_timing_ready` 和对应提示。上传录音的对齐保留为 `align_recording`。内部三个 `prepare_*` 节点保留 Worker 消费者，提案入口拒绝用它们创建新媒体计划。 |
| `conversation_context.py`、`working_drafts.py`、`audio_playback.py`、`trigger_turn.py`、`worker.py` | 删除围绕已退役媒体阶段的草稿更新、重复播放投影和合成规划回合。保留历史交付、停止、失败说明，以及仍在使用的普通制作和草稿操作。 |
| `test_media_journey.py`、`test_media_audio_continuation.py`、`test_music_submission.py` | 删去以媒体 Dock、模拟 Start 或续规划为成功条件的测试。音频准备、时轴、快照、图片审阅和旧在途授权的底层检查保留。直接入口的幂等、并发、跨工程、费用与停止边界归 `test_editor_media.py`。 |

## 五个面的实现与证据

| 面 | 现场可核对的变化 |
|---|---|
| Tool | 模型直接看到 `generate_music`、`generate_voice`、`generate_image`、`insert_audio` 和原有八个编辑工具。原生参数包含创作输入；身份、报价、快照和对齐由服务端确定。逐次实际声明和调用见[完整 Schema](iteration-3/tool-schemas.json)、[原生 ID 与实参](iteration-3/native-calls.json)、[逐次结构验证](iteration-3/schema-validation.json)。 |
| Context | 当前工程、所选 Composition/version、时长、已有素材、近期操作与有效观察按回合组装。后续请求能看到刚固定的素材、对齐和刚提交的版本。图片审阅取原用户要求和经归属验证的网页证据。记录的 `project_evidence` 中未见上述旧媒体阶段字段。可按模型调用 ID 对照[实际请求和回复](iteration-3/provider-wire.json.gz)与[每轮选择、保留和拒绝记录](iteration-3/cases.json)。压缩记录省略供应商推理文字和临时签名，二进制输入按 SHA-256 对应原文件。 |
| Chat | 生成开始对应真实活动，持久提交后回执可以投影 `accepted`；终态卡从同一回执提供试听或图片。页面刷新重新读取服务端活动和素材；加载时遇到仍在执行的媒体回合，会继续读取历史直到结束。可核对[活动、Accepted 与答复事件](iteration-3/transcript-events.json.gz)。费用同意或取消走账户授权。真实卡片与播放状态见[音乐](iteration-3/music-browser.json)、[图片](iteration-3/image-browser.json)、[影片局部预览](iteration-3/mix-browser.json)。 |
| Execution | `submit_editor_media` 锁定 opening，检查身份、权限、版本、缓存与费用，复用 `submit_confirmed_tasks`、现有队列及 Worker。缓存命中直接返回原素材。生成不写 Composition。插入复用 `fixed_audio_ops` 和 `apply_composition_edits`，在同一事务绑定来源并写轨道、Clip、增益和新版本。[执行、SourceSnapshot、对齐与账本](iteration-3/execution.json.gz) · [固定分析和审阅报告](iteration-3/fixed-reports.json.gz) · [逐版差异](iteration-3/changes.json) |
| Recovery | 同一 opening 与原生 call ID 派生稳定身份；参数指纹不符即拒绝。原回执与内部 Run 关联。API、Worker 和历史回读共用 `settle_media_receipt`。已有触发分发器与 `continue_media_turn` 从原用户原话、固定结果和最新版本恢复同一个 ToolLoop。行锁、advisory lock、原回合恢复标记和版本校验防止二次提交。见[进程强杀前后](iteration-3/crash-recovery.json)及[生成期间作品变化](iteration-3/stale-version.json)。 |

### 三条媒体路径

- **A · 配乐。** 用户原话为“为当前作品生成一段 6 秒、96 BPM 的轻电子器乐，给我试听。先不要加入影片。”原生调用 `chatcmpl-tool-9c17b591d142dd60`。服务端固定 ScoreSpec；`PrepareMusic.run → prepare_programmatic_music → synthesize_score` 生成 WAV，并固定 Music、SourceSnapshot、分析和节拍。命中时 `cached_music_preparation` 核对原 ScoreSpec、归属与文件摘要，无需草稿、网页或已对齐旁白。Chrome 刷新前后都播放，状态为 4，采样时钟为 0.579 和 0.686 秒。另一回合复用了 D 的 6 秒配乐，未启动第二个合成任务。[原生 WAV](iteration-3/media/music-33cd393133.wav)
- **B · 旁白。** 用户要求原速英文男声 “Welcome to the editing studio.”。原生调用 `call_5fbef11891914c4abb180939`。实测 1.96209 秒，五个词，句子对齐为 0–144000 ticks，时基 90000。再次请求返回同一快照。`PrepareNarration.run → prepare_speech_media → synthesize_detailed` 通过原有原音提交保护调用 TTS；`snapshot_narration_original` 固定原音。`request_alignment → claim_pending_alignment → process_narration_alignment` 在原音上执行 faster-whisper；`annotate_alignment` 以实测时间摘要为前置条件，补齐语义进入 READY。D 的原音在独立回合由 ALIGNED 到 READY，六个词，句子范围 0–169200 ticks，音频和时间摘要相同。[原声](iteration-3/media/narration-3197af3456.mp3)
- **C · 图片。** 用户要求缺画面的作品生成一张暖光录音棚麦克风照片。原生调用 `call_01a1f962553e7175ae2ce0b1`。`PrepareVisualAssets.run → prepare_visual_asset → _minimax_image → ensure_generated_image_clip` 调用 MiniMax，随后固定 PNG、分析、ContentReview 及 SourceSnapshot。图片能解码，像素审阅为 pass，刷新前后尺寸均为 1920×1080。受控 SVG 另行经 Chromium 栅格化和像素审阅；重复相同输入命中已有审阅和同一张 PNG。来源事实和用户硬要求进入审阅，自选镜头细节保留为创作选择。[MiniMax 实图](iteration-3/media/image-only-c678d52eb2.png) · [受控 SVG 的实际 PNG](iteration-3/media/svg-9f338226bd.png)

## D · 同一次 Chat 的实际剪辑

> 请先看一下这部访谈的时间线，然后给开场加一句英文男声 “Our story begins in the studio.”，从第 0 秒开始。再加 6 秒轻电子器乐，从开头铺底，音量低于人声。请直接剪入这部作品，检查时长和混音，预览前 4 秒后告诉我实际结果。

工程 `73ed7b1b-f2ef-43e0-ab16-9ac908d98a0d`，作品 `2139664b-3525-46d8-926d-dbddbde24680`。Agent 先读时间线；一次并行生成请求被 ToolLoop 整批拒绝，未提交后台工作。之后逐个调用。

| 动作 | 原生 call ID | 已核实的结果 |
|---|---|---|
| inspect_timeline | `call_a3ef5a98bf8d434f9d8169ad` | v1，18 秒、两个场景 |
| generate_voice | `call_52b97fde5606491f96fbcff0` | 固定英文男声，实测 2.25234 秒 |
| generate_music | `call_01a1f964f55471108f62b2e7` | 固定 6 秒轻电子器乐，100 BPM |
| insert_audio | `call_c3e9ec5a19604a74a5db3ea8` | v2 `4dd83989-d083-425f-b32e-2bdd7e622784`，旁白从 0 秒开始，0 dB；原五个 Clip 均未改变 |
| insert_audio | `call_f574090b1cee467f99db4eeb` | v3 `b0922d90-548d-49d5-aebb-b83521a21060`，音乐从 0 秒开始，−12 dB；已有六个 Clip 均未改变 |
| inspect_timeline、preview_range | `call_01a1f9650a7b730b98e880aa`、`call_01a1f9651058765bba460e12` | 核对新轨、位置与增益；从保存版渲染 0–4 秒。Chrome 刷新后视频与两个音频元素均推进，处于播放状态 |

开场渲染含 120 帧视频；AAC 解码出 194560 个样本/声道。实测 RMS 0.11698，峰值 0.70857，削波样本 0。最初的 FFmpeg 管道读不到尾置索引，返回了无样本的 −70 LUFS 和 0 dBTP。改用可 seek 的输入，新增回归，并对原始 v3 MP4 重新测量得到 **−16.1 LUFS、−3.0 dBTP**。后续版本的同一时间窗也通过原生 `preview_range` 复测。耳听质量、配音表现、单轨主观平衡没有观测依据。[不可变版本](iteration-3/versions.json.gz) · [原文件逐一解码与 SHA-256](iteration-3/media-verification.json)

## 授权、恢复与边界

| 场景 | 证据及结果 |
|---|---|
| 重放、参数冲突、并发 | 数据库定向测试并发提交相同身份，得到同一回执、一个 Run 和一个 Step。同一身份改参数或跨编辑/生成复用被拒；同一插入重放返回原版本。跨项目来源拒绝。 |
| Stop、费用不足、供应商结果未知 | PostgreSQL 定向测试覆盖 Stop 先赢和持久提交先赢。后者保留原执行并走取消。余额不足不产生预占或新任务；设置大额模拟供应商超支并重放 capture，实际扣款不超过原预占。TTS 丢失提交结果后，同执行与另一 Worker 均不能再次发起；图像只有找回已验证结果才允许复用。未知响应边界使用故障注入，未主动对真实付费供应商制造丢单。 |
| 同意与拒绝 | 最初一次同意后，模型只看到“允许”，错把要求的 5 秒、−14 dB 写成了开头、0 dB。修复后真实 3 积分上限 TTS 授权在原请求恢复，旁白从 8 秒开始，−4 dB，预览 8–11 秒。同样的实际费用问题选择“取消”，回执为 declined，未增加 Run、版本、扣费。一次模型自行提普通选项的问题不能充当费用授权，也保留在记录内。 |
| API 和 Worker 同时在交付前被 SIGKILL | 测试钩子仅在已完成 Run、已固定快照、尚未写回 Chat 时向本进程发 SIGKILL。前后核对 PID、原回执、步骤尝试数、账本和版本。初次实验只恢复了素材；后续实验证明 Worker 可直接续剪。最终 `fault4` 无新用户消息，找回 1.75 秒 WAV，按原话在 7–8.75 秒、−15 dB 保存 v6，预览 7–9 秒。相同 Step 只执行一次，两次读历史不产生新版本。 |
| 工作发生变化 | `stale` 在 v6 接受配乐，暂缓 Worker；一个独立编辑通过同一正式写口更新字幕，保存 v7。API 被强杀后重启，原 Worker 完成单次合成。素材可试听，v7 保持原样，来源未绑定。Chat 提示用户在当前版本另选位置。 |
| 已经有编辑提交时中断 | 恢复从实际不可变版本报告已落库的动作。按已经变化的版本、有后续用户回合或已有提交等边界退出自动写入。Iteration 2 的提交后强杀基线与本轮编辑回归保留。 |

`fault2` 因独立 renderer 离线未完成当回合预览；`fault3` 因隔离桶缺固定字幕字体而失败。使用现有 `ensure_font_resources` 校验并发布仓库固定字体后，真实 Chat 成功渲染 15–18 秒字幕窗口。`fault4` 独立验证完整恢复到预览。实际浏览器验证覆盖已交付素材和作品卡的刷新播放；双进程故障期间的自动恢复记录来自数据库、原生模型请求和历史端点。

## 成本、测试与未通过事项

共 21 个真实 Chat 样本，103 次 MiniMax ToolLoop 请求，771,158 个输入、17,681 个输出 token。96 个原生调用中 95 个符合实际声明的结构；一次 Alignment 语义标注的 needs 为对象，声明为数组。以每个样本首次出现的生成或插入动作为分母，24/24 符合 Schema，16/24 同时满足单次只发一个工具的执行规则。数据库折入的对话成本为 US$ 0.115957，媒体步骤折价为 US$ 0.01367435。

- D 主旅程用 9 次模型请求，62001 个输入、1238 个输出 token，一批并行调用被拒。B 的早期样本出现 8 次多余预览失败，修正隔离桶访问后成功。重复生成三个媒体的命中样本各自复用原快照，没有额外付费生成。模型请求数包含失败试验和复测，不能当作典型单片预算。
- 应用账本共预占 15、释放 15、实际扣除 14 积分。媒体 Worker 记录三次不同文本的 TTS，共 87 个计费字符；MiniMax 生图 1 张，另有 1 张本地 SVG，两个不同图像均有模型审阅。程序化音乐无外部音乐供应商费用。全部原生请求按部署费率折合 US$ 0.1262823。按应用费率的金额与供应商发票分别核对；当前未取得发票，进程被杀前的用量也可能尚未折入对话账本。[逐回合用量](iteration-3/metrics.json)
- 后端 `pytest -q test/core` 通过 508 项；Web Vitest 47 个文件、432 项通过，TypeScript `tsc --noEmit` 通过。后端有 4 条警告，含序列化和依赖弃用提示。真实数据库用例与外部故障替身的覆盖分层见上表。[验证结果](iteration-3/regressions.json)
- 原始回复保留已知表达错误。一次中文授权回合用韩语回复；一次恢复回合声称内容摘要未变，数据库显示 v5 和 v6 的摘要不同。少数模型回复带技术标识，或主动提出不必要的问题。服务端执行、入账与版本以回执和不可变数据核对。尚未验收生产部署、真实供应商账单对账、全部模型的通用成功率或主观听感。图片工具交付固定素材；本轮接入的时间线插入工具针对音频。

代码提交 `df9d6b90` 和 `fdcb378e`。本报告及附件以同一施工分支后续证据提交交付。生产数据库和原开发分支未参与实验。隔离数据库保留；关闭独立验收服务前，将测试桶全部 85 个对象持久化在工作树忽略目录 `var/iteration-3-storage/`。已提交的媒体及报告可直接离线打开。
