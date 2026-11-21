# Editor 6D → affectUI U3/U4 分镜卡交接

## 提交与验收范围

分镜卡交接的代码 HEAD 为 `8def896d1a64a0b3a81dedbe1108f68e3aed70a0`。该提交包含前端改动、HTTP 回归与展示恢复测试。Job 回执与刷新时 Stop 的基线为 `0d13f1b8`，Stop 与资金裁决为 `117fe2b4e07d8f3f5cbc4da6aa120197509197a0`。核对代码 HEAD 时下表内文件均无未提交修改。

分镜卡展示契约已完成。最新 Chat 代码交接基线为 `6d657cb9`，项目详情基线为 `f15c7f46`。旧 Run SSE 与取消 API 都已删除，Chat 执行层的消息类型仍在收口。此时 Editor 的 Chat 文件无未提交修改。Web 374 项、API core 498 项和 TypeScript 通过。独立 API、两个 Worker 与 Chrome 实测按 v2 和 v3 两张成片卡分别播放、硬刷新再播放，实际下载的 SHA-256 与各自固定 Output 一致，视频各 150 帧。十用户混合负载尚未验证。

## 文件归属

路径自 `apps/web/src/` 起算。释放范围仅为本表标记 RELEASED 的文件。

| 文件 | 状态 | 可修改范围或保留原因 |
| --- | --- | --- |
| components/chat/video/StoryboardCard.tsx | RELEASED | 可进行 U3/U4 视觉施工，保留下述版本校验、预览就绪与 ACK |
| components/chat/AgentThread.tsx | OWNED_BY_EDITOR | Job 回执恢复与旧消息字段仍在收口 |
| components/chat/ChatConversation.tsx | OWNED_BY_EDITOR | 已移除 Run 展示参数；旧计划版本展示仍在收口 |
| lib/runWorkSegment.ts | NOT_APPLICABLE | 已删除 |
| lib/use-run-events.ts | NOT_APPLICABLE | 文件与 SSE 消费者已删除 |
| components/chat/RunTaskList.tsx | NOT_APPLICABLE | 文件已删除 |
| components/chat/ActivityStream.tsx、timeline/activity.ts、timeline/project.ts、timeline/history.ts、timeline/types.ts | OWNED_BY_EDITOR | Activity 与 Tool Group 的持久投影与旧 Run 显示共用这些文件 |
| components/chat/blocks/ComponentSlot.tsx、timeline/reveal.ts、timeline/reveal.test.ts、ChatConversation.mount.test.tsx（位于 components/chat/） | OWNED_BY_EDITOR | 已移除展示触发 Run 的回调，仍在审查其他 Chat 消费者 |
| components/ui/、QuestionDock.tsx 的视觉组件 | NOT_APPLICABLE | 本交接不变更 affectUI 已有归属 |

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

以下文件已释放给 affectUI U3/U4 施工；Editor 6D 不再并行修改这些文件。

- `apps/web/src/components/chat/video/StoryboardCard.tsx`
