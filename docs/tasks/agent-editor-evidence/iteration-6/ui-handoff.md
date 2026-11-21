# Editor 6D → affectUI U3/U4 Chat 交接

## 提交与状态

交接代码 HEAD 为 `492acc4169f587dde971ee5ef7dda7af50e1d930`，完整消息读写切片为 `ea56282d4ec8f6fd61cf664c798fdb6380950093`。首次提交本交接文档的 SHA 为 `e932584ac723a038393c35edf6f8be99f8e32786`。Chat 执行契约与下列文件的 Editor 施工已结束。交接前已检查该组路径，工作树干净。

API core 489 项通过（3 项警告），Web 42 个文件、337 项通过，TypeScript 通过。真实 Chrome 在同一项目分别播放 v2、v3，逐张硬刷新后重新播放并点击下载，下载的 SHA-256 等于各自 Output。真实 HTTP 已完成批准、媒体、导出和 Stop；Unknown 与取消竞态通过隔离库故障注入。真实 Chrome 尚未逐一复演全部故障注入，也未验证 affectUI 视觉改造。十用户独立窗口为 41 个请求，4 项 Job 各认领一次。详细范围见 [6D 记录](6d.md) 与 [浏览器实测](6d-ui-release.json)。

后续服务端切片 `fd437031` 删除了从未由现役工具发出的 video_draft_review 回执，按用户原话审阅指定 Output。deliver_video 工具结果中的 export_charged_this_opening 和 original_export_charge 分别来自本 opening 与原导出；用户钱包仍以账本为准。已释放的前端文件无需接入新订阅。最新实测见 [6D 验收](6d-acceptance.md)。

## 文件所有权

路径以 `apps/web/src/` 为基准。下表的 RELEASED 状态也适用于相应的 Editor 行为回归用例。

| 文件 | 状态 | 交接边界 |
| --- | --- | --- |
| components/chat/AgentThread.tsx | RELEASED | 开启 original opening、恢复消息、Stop 与 SSE 更新 |
| components/chat/ChatConversation.tsx | RELEASED | 正文、活动、问答与固定输出引用 |
| components/chat/ActivityStream.tsx、timeline/activity.ts、timeline/project.ts、timeline/history.ts、timeline/types.ts | RELEASED | 真实 Activity 及同组成员，按持久身份投影 |
| components/chat/answerSettlement.ts、liveMessageReconcile.ts、blocks/ComponentSlot.tsx、timeline/reveal.ts | RELEASED | 选项回答、行更新与组件释放 |
| components/chat/ChatOutputViewer.tsx、video/StoryboardCard.tsx | RELEASED | 确切版本展示、选定 Output 的播放与下载 |
| lib/anchorCards.ts、lib/chat-stream.ts、lib/types.ts | RELEASED | 交接限于 Chat 与成片字段，修改公共类型时检查其他消费者 |
| lib/runWorkSegment.ts、lib/use-run-events.ts、lib/startRecovery.ts、lib/lifecycleStamp.ts | NOT_APPLICABLE | 已删除 |
| components/chat/RunCard.tsx、RunTaskList.tsx、blocks/RunBlock.tsx、startSettlement.ts、mediaJourneyMessages.ts、chatProtocol.ts | NOT_APPLICABLE | 已删除 |
| components/ui/、styles.css、studio.css、QuestionDock.tsx、Home、Projects 列表、Settings、Login | NOT_APPLICABLE | 由原 UI 施工者掌握；6D 未接手视觉施工 |

## 实际接口与刷新行为

接口前缀为 `/api/v1`。消息类型见 `apps/api/app/models/schemas.py::ChatMessageResponse`。SSE 组包见 `apps/api/app/chat/routes.py::_row_payload` 和 `_make_activity_persister`。前端类型位于 `components/chat/timeline/types.ts`，历史解码位于同目录的 `history.ts`。在 Studio 中刷新由 `AgentThread.tsx` 读取 `GET /chat/conversations/{id}/messages`，以 `Message.seq` 定位消息。SSE 的 `assistant.row.append` 新增消息，`assistant.row.update` 更新原行。

| 用户所见 | 身份与排序 | 完成、失败与恢复事实 |
| --- | --- | --- |
| Activity、Tool Group | `Message.turn_id` 指回原 opening；`intent.type=activity`，`intent.frame` 对应 `ActivityFramePayload`。组内用 `group_id, call_id, tool_name, call_index, call_count` 标识原生调用及声明顺序 | `status` 为 active、completed、failed、cancelled。按 `key` 展示阶段，可携带 `duration_ms, receipt, error`。组成员有独立 `call_state`，包括 queued、running、awaiting_authorization、not_executed 和 provider_unknown。恢复时逐成员处理；另一个成员完成不能充当本成员的结果 |
| 媒体与导出 | `intent.native_call_id`、`operation`、`media_job` 或 `export_job`；结果与 Job 使用同一条执行消息 | `ChatMessageResponse._editor_media_projection` 仅在 Job 已接收而尚无结果时给出 `media_status=accepted`。完成后读 `media_result.status` 与正文。两种 Job 的后台状态为 queued、running、succeeded、failed、cancelled、unknown，客户端不直接订阅数据库枚举。available 是可用，provider_unknown 或 fixed_audio_pending_recovery 需要核对。Stop 后若出现 `stop_requested=true, charged_credits=null`，预占仍保留。详见 `pipeline/{media_jobs,export_jobs}.py`、`chat/editor_media.py::_record_audio/_record_image` |
| 固定媒体卡 | `AudioPlaybackBlock.project_id` 与 `items[].snapshot_id,digest,duration_seconds,peaks,analysis_digest`；图片使用 `ImagePreviewBlock.project_id,snapshot_id,digest` | 来自持久 `Message.blocks`。成功的媒体可以试听或查看，是否已插入由 CompositionVersion 决定。刷新使用原项目与快照 |
| 费用授权 | 对 `question.kind=question` 使用原消息 ID，`options[].id,label` 和服务端正文。POST `/chat/messages/{id}/answer`，option 的 option_id 为 approve 或 decline，bail 也是退出路径 | `answer` 持久记录决定。`chat/editor_media.py::answer_media_permission` 关联执行回执，金额结算读该回执的 `media_result.charged_credits/reserved_credits`。前端报价或按钮点击均不能证明已扣款 |
| Stop | POST `/chat/turns/{opening_id}/stop`。现役 Job 使用 `ChatTurnStopRequest` 的 turn 范围；可见边界为 `prose[].message_id/visible_chars, activity_ids, structure_ids` | `chat/service.py::stop_turn_at_visible_frontier` 保存原 opening 的终态。已提交编辑、媒体和 Output 继续按其原身份读取。若上传状态待核对，停止后也不能显示交付成功；若 Output 先提交，继续显示已提交的成片 |
| 分镜和版本 | `VideoStoryboardBlock` 使用 `presented_message_id, composition_id, composition_version_id, version, content_digest, presentation_digest, presentation_complete` 及可选 `scrub`；见 `StoryboardCard.tsx` 与 `chat/routes.py::complete_video_presentation` | 读取卡片指向的确切版本。完整 DTO、可播放预览和正文就绪后才 POST `/chat/messages/{message_id}/video-presentation`。刷新时匹配当前展示回执的消息、版本和摘要。服务端接受返回 `accepted=true`，旧展示记录在原消息并返回 false，摘要冲突返回 409。切换最新 head 须是用户动作 |
| Output 卡及播放下载 | 最终交付消息的 `intent.output_refs` 和 `reviewed_version` 标明已审阅成片。`GET /projects/{id}/chat/outputs` 返回 `ChatOutputEntry.output_id/output`，按交付记录的引用顺序 | `ChatOutputViewer.tsx` 按所选 ID 取 `output.files.video`，缺少列表项时读取 `GET /outputs/{id}`。已失效的记录呈现 unavailable。导出位置以权限校验后的 `/outputs/{id}/playback` 解析，支持 download 参数。实际下载按钮见 `components/results/MediaLightboxStage.tsx`。export 的 available 表示 MP4 可审阅，正式交付另有持久消息 |

## 删除与剩余消费者

分镜展示 ACK 已删除 `_auto_start_docked_plan`、返回 `run_id` 与前端 `onRunStarted` 回调。媒体与导出恢复已从原生 Job 回执读取。新资金规则的恢复仲裁仍是原 opening。

GET /runs/{id}/events、POST /runs/{id}/cancel、media_preparation Stop 与旧 Run 恢复触发器均已删除。项目详情直接读取素材的 processing_status、processing_requested_at。正式导出的成功回执和交付消息引用各自的固定 Output。当前共享 8000 和热重载 Worker 已暂停。共享库仍有旧 schema。

### 消费边界

`history.ts::mapHistoryRows` 实际消费 `intent.media_status === "accepted"` 来折叠尚无结果的执行消息。当前 UI 的完成文案、音频和图片使用更新后的 `Message.content` 和 `blocks`，卡片不自行换算扣款。操作身份、Job ID 和 `media_result` 是 API 提供的诊断与业务事实。历史 Tool Group 过滤、顺序与状态来自 `activityRowFrame`；`group_id` 与 `call_index` 对应同一轮真实模型声明，失败或 Unknown 的成员原位保留。源码见 `apps/api/app/agents/tool_loop.py`、`app/chat/editor_recovery.py::settle_media_activity` 和前述投影文件。

历史消息不再解码 material_beat 或从相邻用户文字猜测授权问题归属。旧 Step 的 Output 候选兜底已删除。正式交付的 output_refs 仍为现役事实。刷新后已交付旧版本仍由这条消息独立持有。

以下文件已释放给 affectUI U3/U4 施工；Editor 6D 不再并行修改这些文件。

范围为“文件所有权”表中所有 RELEASED 项。共享 8000 与热重载 Worker 保持暂停，联调使用明确隔离的后端。
