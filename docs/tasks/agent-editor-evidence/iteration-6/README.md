# Iteration 6A · 执行消费者与首错审计

2026-11-21，main 基线 fdd21443。三个原始 gzip 的模型 response、原生 call ID、参数、持久消息与原验收库逐个关联。可复查值见 [audit.json](audit.json)。取证没有重发 TTS、补扣款或修改历史回执。

## 三项首错

接缝先 move 至 v2，图片先 scale、translate 至 v3。两个 opening 各有两次独立原生 export_video({})，分别创建两个 Run。接缝两次领取 262 / 647 次，各 hold 16 并全额 release。片尾卡 239 / 508 次，各 hold 13 并全额 release。四个 Run 均取消，项目 Output 均为零，库中无相应 render mirror 或 capture。没有证据表明正式渲染已经开始。短窗预览另计。

第一次错误的状态转换可以在原 PostgreSQL 实例上复现。claim_ready_node 用数据库 now() 写 started_at。worker._tick 在派发 execute_step 后就在同一轮调用 reap_stale_nodes_older_than，它以 Python datetime.now(UTC) 减 900 秒为边界。实测宿主机领先 23,699 秒。使用连接私有临时表及原函数，单个调用者第一次 claim 后立即 reap，行从 running/T1 变为 pending/NULL，第二次 claim 为 running/T2，T1 的 _fenced_step_write 命中零行。五个失败 Step 的最后一次 started_at 均早于其创建时间数小时。无需假设第二 Worker 或 600 秒执行超时即可解释循环。claim_ready_node 无 attempt 上限；ProduceVideo.retries=0 仅约束异常重试，不约束 reap。claim 只排除 CANCELLED，仍可能领取 FAILED/COMPLETED 下的悬空 pending Step；当前样本未证实此种领取。启动全量 reap_stale 会清其他实例的活跃 token，属于独立缺陷。历史进程数、启动 sweep 次数、每次 token 没有持久日志；重现实测 token 不能反填历史。表中 earliest_retained_stage_attempt 是最早保留的阶段，非首次换权时刻。

旁白已完成真实生产。VideoNarration 行为 done，有供应商 trace、26 字符用量、固定音频 digest；本项目有四个 Asset/SourceSnapshot 对应同一原音。PrepareNarration.run 在独立事务持久化音频及快照，后续 Step 结算丢失权威；Step 的 spec 有 narration_preparation，Run 的 result 缺失。671 次领取后取消，3 积分释放，零 capture。配乐另一个 Step 第 26 次后成功。此样本不应认定为原音仍 Unknown；不可按 attempt 推算供应商提交次数或账单。既有快照保留，禁止按此审计追扣。未确认请求仍须遵守 resolve_original / mark_outcome_unknown 的防重发边界。

## 函数级归属

| 入口和消费者 | 事实与权限 | 迁移边界 |
|---|---|---|
| editor.generate_media 经 editor_media.submit_editor_media | opening/call、用户项目、head/digest、当前实际预览、用户意图；Message 保存指纹和授权问题 | 保留。模型 Schema 无参数，版本由服务端固定 |
| derive_task_estimates → video_quote_facts → compile_graph；answer_media_permission → _submit → submit_confirmed_tasks → create_run | 报价、余额、hold 与 Run/Steps 同事务。create_run 还激活休眠资产 | 单独报价、入队及 hold；导出不唤醒项目所有素材 |
| claim_ready_node → execute_step → ProduceVideo.run → queue_composition_render | 生产者校验版本、准备来源、compile_video_spec，先写 Output，再挂 render owner/barrier | 保留编译、固定来源与所有权。删除原生导出依赖的任务图 |
| claim_pending_render → render_output → _probe_artifacts | 输出 token、条件 PUT、Renderer 缓存及实际文件 probe；capture_video_render 依赖 render mirror 的计费键 | 输出字节、对象 key 和媒体校验保留；Job 的 token 必须随 claim 返回，不能按 ID 重读新持有者的 token |
| _mirror_render_node、_finalize_owning_run → maybe_finalize_run | 镜像 Step、Run 结算、release、触发完成事件 | 新导出不需要此协调。既有非原生制作、retry_upload 的历史 step 引用保留 |
| wait_for_media_result、settle_media_receipt、_record_export | 以 Run 终态和 step 查找 Output；校验固定版，Message 持久化结果 | Job 成功写入与账本/回执同事务。Activity 读取 Job 或已落库文件事实 |
| recover_media_receipts、resume_finished_media、continue_media_turn、service 的 Stop | opening 锁、advisory lock、原调用顺序、已提交版本及终态回执；Stop 目前按 message.workflow_run_id 取消 | 复用 opening 仲裁；移除导出的 run_completed 触发。review_video 读实际 bytes；deliver_video 校验同一 SHA、版本、回合并去重 |
| PrepareNarration、PrepareMusic、PrepareVisualAssets | 固定素材、供应商占位、费用与恢复仍有独立消费者 | 6C。旁白对齐 request_alignment/claim_pending_alignment/process_narration_alignment 是独立领域 |
| claim_pending_asset/process_asset、claim_due_publication/process_publication、flag_stale_webhook_events/claim_payment_alert/process_payment_alert、reap_stale_staging_uploads | 资产、发布、告警及清理均有独立入口 | 各自保留，6B 不改变业务队列 |
| 平台历史与非视频 | 默认开发库还记录旧 plan、preprocess、understand、verify、persona_bootstrap、decompile 等 Step；历史记录本身不证明现役入口。账单、Output 读取和跨 Chat reviewed_output_ref 仍有真实引用 | 不删历史 FK、表或账本。全仓消费者及 legacy fixture 退休留待 6D |

## 数据与接管边界

在原验收库有 10 completed、5 cancelled、9 Output；开发库有 161 completed、40 failed、235 Output。两库均无 pending/running/waiting Step。此盘点不外推线上。开发库按 held() 的旧资金语义仍有 25 个查无 Run 的余额组共 219 积分、两个失败 Run 共 606 积分未释放。不迁移、不冲销这些历史交易；新身份使用独立幂等键和同一钱包。开发库中仍有 9 个当前作品含 speech、18 个含 generator，存在旧生产隐式触发付费来源准备的业务边界。

新执行最少需钉住已授权回执、项目、版本/digest、规格、原生请求和 Output，领取使用同一数据库时钟，限次、带 token 和到期时间。Stop 与终态提交竞争同一行。条件对象键与探测支持上传后重领。五面现状：Tool 与编辑版本成立；原生模型只提交 {}，无需理解图；消息有中断回执；实际导出失败；后台恢复错误已复现。6B 五面真实出口仍须单独验证。

十个独立身份的验收分工：A/B 即时 CAS，C/D 读素材与对齐，E/F 两个正式导出，G 短预览，H 查看历史及越权拒绝，I Stop，J 在旧版导出时提交新 head。跨身份核对 claim 次数、队列和执行时长、ledger、Output/版本和刷新；双 Worker 对同一请求竞争，分别在上传前后及回执边界中断。该矩阵目前为待测项。
