# Iteration 6D 验收记录

2026-11-21 至 22 日，开工实查为 main@935aab92，最新执行代码为 `fd4370314af35c54a98efd08149292968f8c865f`。本地 Agent 已从新素材完成生成、剪辑、预览、正式导出、审阅、交付及后续修改。五个独立新项目中，三个最终交付了两个版本，其中两个经历重试或恢复。两次十用户负载均通过。该样本没有验证任意素材的通用一次成功率。各提交的调用方、删除项和首次故障见[分片记录](6d.md)。

## 退役与现役执行

| 位置 | 失效实现及删除 | 现役入口、复用与验证 |
| --- | --- | --- |
| Tool 与即时编辑 | 旧 production 节点注册器、工作稿协议、图编译、手工图写口、Plan/Dock/Start 工具 | `chat/editor_create.py`、`chat/editor.py` 处理 create、split、trim、move、translate、scale、insert_audio 等。所有内容写入复用 `editing/store.py::apply_composition_edits`，核对项目、base、请求身份和实际生成的版本。[真实剪辑](6d-cut-regression.json) |
| Prompt 与下一轮输入 | proposer、trigger、event_mode、plan_mode、旧 Run context、跨轮恢复 design_video 工作稿 | `chat/prompts.py`、`plan_turn.py`、`agents/tool_loop.py` 组装用户原话、当前作品、固定来源、最近观察及原生回执。单个实测项目在不同轮次实际看到 29 个工具，留存 13 个请求节选。修复后 review_video 的模型参数只选择 Output 和采样，审阅条件由项目内当前 opening 和写入所审版本的用户原话提供。[Provider 请求与结果](6d-final-wire.json) · [审阅复测](6d-review-user-scope.json) |
| Chat 与 UI | Run SSE、run_completed 触发、Step 活动镜像、RunCard、RunTaskList、RunBlock、runWorkSegment、use-run-events、startRecovery 和旧测试 | `chat/activity.py`、`editor_media.py` 与持久 Message 输出原生 call、group、seq、Job 回执和授权。交付绑定已审阅的 Output、版本及文件摘要。原生 Stop 使用 opening，页面刷新读取原消息。组件与 CSS 的视觉改动由 affectUI 持有。字段、枚举、接口、排序及文件所有权见[交接](ui-handoff.md)。 |
| 后台业务 | pipeline/orchestrator、jobs、graph、graph_store、node_runners、render_ownership、run_review、lifecycle、step_display、conversation_bridge、trigger_events、video/production | `worker.py` 领取素材、字幕对齐、三类 MediaJob、ExportJob、独立 Publication、PaymentAlert，并回收 staging。合成沿用 narration_store、程序化音乐、固定图片、SourceSnapshot；MP4 沿用 Renderer 与 Output。生成的配乐快照原点含真实 media_job_id。[并发媒体](6d-overlapping-media.json) · [新版本与快照](6d-after-revision.json) |
| 交易、Stop 与恢复 | Run 结算、Graph 估价、旧 Run 完成协调与镜像渲染 | 项目删除和付费入队按 Project 锁排序；未知外部结果、未终结任务或未决预占先返回 409。Stop 与成功提交竞争同一 ExportJob。Stop 先提交，禁止交付，待上传核清后 capture 0 并全额释放；Output 先提交则保留原交易。MediaJob/ExportJob 使用原 claim_token、lease、fencing 和钱包。单一原 opening 的续行仲裁保留。[条件 PUT](6d-export-upload.json) · [API 强杀](6d-api-crash.json) |
| 数据库、接口和测试 | graph_edges、graph_nodes、workflow_steps、workflow_runs、workflowstatus、messages.workflow_run_id、Output 的 Step 外键和四个执行字段；项目 graph、runs 列表、Run 详情/事件/取消和手动重渲染；仅验证旧 Graph、Step、渲染屏障、Run 权限及旧草稿的测试 | Alembic j6d01–j6d05 已在独立 PostgreSQL 实升，并从空库安装至 j6d05_project_brief。干净库 30 张表，API health 200，Worker 正常启动。原生出口继续表达 CompositionVersion、MediaJob、ExportJob、SourceSnapshot、Output、Message、Publication 和账本。[schema、实际路由、进程](6d-clean-schema.json) |

最后一个切片删除 `agents/working_drafts.py`、`tools/video/narration_draft.py`、图像批量工作稿与草稿配乐入口。纠正无效的原生参数仍使用 candidate_correction。原生保存的真实版本和 opening 回执取代旧测试中的工作稿 digest 链。明确选择的 Skill 在尚未创建作品、且原 opening 留有实际澄清问题时可以继续继承。页面的确定性剪辑手势仍走已有版本写口。这里没有新增执行器、表或状态机。

## 资金、外部效果与并发

| 实测 | 结果 |
| --- | --- |
| 两次十人窗口，各开两个 Worker | 41 次请求 / 62.836 秒，40 次请求 / 55.451 秒；每次 4 个 Job、4 次认领、合计 15 积分（旁白 3、配乐 0、两次导出各 6），结束时十个钱包预占均为 0。第二次 38 个 HTTP 200、1 个 201、跨用户读取 404。两名编辑、两名生成、两名导出、预览、素材处理、历史 Output、原 opening Stop 同窗运行。逐 Job 的 Worker PID 未采集。[第一次](6d-concurrency.json) · [复测](6d-final-concurrency.json) |
| 同项目边导出边编辑 | 首次 v1 已上传并扣费，却按 v2 校验交付失败；修复后相同请求在 v1 上传期间保存 v2，随后原 opening 审阅交付 v1。一次上传、一次认领、一次扣 6。同版本跨 call ID 重放、异参拒绝、换版本另行授权均有数据库回归。[首错](6d-overlapping-export-first-error.json) · [复测](6d-overlapping-export.json) |
| 同项目边生成边编辑 | 供应商执行期间标题下移 16px，v3 保存。旁白固定为 1.358375 秒，认领和调用各一次，扣 2，迟到结果没有改变 head。[记录](6d-overlapping-media.json) |
| 进程强杀、晚到结果、Stop | API SIGKILL 后双 Worker 在原 opening 恢复同一配乐，1 Job、1 次认领、1 快照。媒体 Worker 分别在提交前、提交后、固化后、结算后被 SIGKILL；最终供应商 POST 均为 1。提交后未知保留 3 积分预占。该组 HTTP 供应商为可计数替身，使用预先真实生成的音频及真实 TOS。隔离库另测 Stop 先于 PUT、PUT 后 Output 前、Output 后、未知上传、重复 Stop 和失权回执。[四个故障边界](6d-final-media-faults.json) · [导出交易测试](../../../../apps/api/test/core/test_export_stop_races.py) |
| 删除保护与公开发布 | PostgreSQL 测试核对 409 前后素材、文件清理调用、两种 Job、消息、Output、快照、用户余额及账本；双连接竞争与结清后删除均通过。平台可能已发帖时 Publication 进入 unknown，有平台 ID 才按原 ID 有界查询。无 ID 时保留原单与资产，有核实证据再登记已发布或未发布。强杀发生在测试 HTTP 接收 POST 后，双 Worker 合计只发一次。未向真实 LinkedIn/TikTok 账户发布。[删除竞争](../../../../apps/api/test/core/test_project_job_deletion.py) · [发布测试](../../../../apps/api/test/core/test_publication_dispatch.py) |

## 新素材的实际完成率

五名新用户分别新建项目并上传同一份获准公开的合成视频 `amber-arc.mp4`，480×270，24 fps，144 帧。Chat 的用户消息驱动真实 MiniMax 决策、真实语音、程序化配乐、Renderer、MP4 审阅和交付。前四个项目独立记录，可复核用户原文、批准/拒绝、原生调用、版本、Job、用量和钱包流水。[前四个完整样本记录](6d-final-journeys.json)

| 项目样本 | 实际交付与首错 | 实扣积分 |
| --- | --- | ---: |
| post-journey | v3 导出交付。源视频额外加上关键帧推镜，随后 110% 静态缩放被拒；未交付新版。另一次明确批准的图片请求真实生成，预占 6，实扣 4。 | 19 |
| replica | 首次请求因对齐问题重试；v2 正式交付。放大后 v3 已保存，随后供应商 HTTP 529；后续从已保存版本审阅并交付。两张卡 Chrome 硬刷新、播放、下载均通过。 | 23 |
| finalcase | 旁白、配乐和三个版本已保存；额外 SpeechObject 尚待对齐，预览及正式交付未完成。测试进程轮换漏等独立 Alignment，认领随后按数据库时钟自然过期并完成对齐。未计为用户交付成功。 | 4 |
| recheck | 原旁白获批，额外报价被拒。真实预览、审阅、交付 v3，再按 110% 修改并交付 v4。Chrome 两张卡验证通过。 | 23 |
| 旧工作稿退役后的新项目 | 两个 MediaJob 各认领一次；v3 导出后审阅错把旁白里的“弧线”当画面要求，额外图片报价被拒，未建图片 Job。修复后用相同请求文字并引用已付费 MP4，原文件获审阅并交付，账本增量为 0。随后 110% 续改保存 v4、预览、真实导出、再次审阅交付。两次导出文件各 150 帧，摘要不同。[首次](6d-after-draft-removal.json) · [审阅复测](6d-review-user-scope.json) · [续改](6d-after-revision.json) · [Chrome](6d-after-revision-browser.json) | 23 |

最后一个复测曾在回复中将原导出的 10 积分描述为“本次扣费”。实际无新扣费。交付回执现从原 ExportJob 消息分别读取原导出扣额和本 opening 扣额。审片的版本摘要也改为明确呈现 dialogue 轨上的固定音频和 SpeechObject。回归测试核对了原 opening 扣额及新 opening 交付同一文件的零扣额。静帧和幅度测量能验证实际采样及音轨信号；未做人工对词、主观混音或全片听感验收。

## 回归、环境与交付状态

- **通过**：在 127.0.0.1:5966 的一次性 PostgreSQL 数据库运行 API core 491 项。3 项警告为一项 SQLAlchemy 连接回收和两项 Pillow 弃用。Web 使用 `a1ceee93` 的已提交前端，42 个文件、339 项通过，TypeScript 通过。Renderer 七个文件、29 项通过，类型检查通过。实际 Chrome 对上述三个成功续改项目的两版 MP4，逐张验证播放、硬刷新、下载按钮及 SHA-256。先前切片的测试数量按当时测试集合保留。
- **未通过的首次请求**：逐案列于上表。另有十用户准备阶段用户明确禁止生成，却曾收到旁白报价。没有入队或扣费；相同原文在工具目录和入队检查修复后创建 v1。[范围复测](6d-explicit-media-scope.json)
- **验证边界**：十用户和故障注入为分开的实测；未对每个故障在十个真实浏览器中重演。四个首批项目的模型用量估计约为 0.045929、0.064910、0.026573、0.043830 USD；用户钱包的积分另列。未核对供应商发票。现有 TOS 有公开 GetObject 策略，媒体验证使用获准公开的合成素材。
- **部署**：共享库、历史账本和 Volume 保留。独立库有新的 Job、Publication 认领与核对字段，已删除旧 Graph、Run/Step 及镜像。新版本 API/Worker 启动时只检查 schema revision。共享库未安装这些迁移，不能直接配合新服务。原 8000 热重载 API 与 dev_worker 保持暂停。
- **Git 与所有权**：本轮 Editor 只在 main 逐片提交。Chat 文件在 `492acc41` 稳定并于 `e932584a` 交接。后续 affectUI 提交及未提交文件归原作者。已提交前端作为浏览器测试输入。验收收口时，GitHub 读取的远端 main 与本地跟踪引用同为 `9309d8ea30dc8248900397435c61d1ac0ed13f6d`。按约定，后续本地提交由用户使用 GitHub Desktop 推送。
- **后续产品能力**：受关键帧控制的属性调整、更多跨素材一次完成率及更丰富的审听属于后续专业剪辑验证。当前共享环境的升级及私有存储部署另行安排。
