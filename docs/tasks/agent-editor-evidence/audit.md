# 接管基线 353f242d

原 main 比交接记录多一个提交，21 个路径含 test_music_submission.py。唯一未跟踪文件是用户的 docs/tasks/new-agent.md。检查点 09cf1873 保存其原文。原目录的 dev.sh 启动 uvicorn --reload、worker、web 和 renderer。数据库只读调查发现 208 部作品，201 个 Run、322 个 Step 全部终态，素材 518 completed / 22 failed。40 条消息仍标 in_flight，9 条对齐标 ALIGNED。未见独立 pytest 进程。保留所有现场行与服务。

## 原生工具入口及切除顺序

baseline-wire.json.gz 内 definitions 是完整的 tool_spec（已执行 wire_view）结果，projections 将路线和阶段对应到定义。registered 是部署的声明上界，分阶段条目是受控输入下的投影，archive 是既有 provider 请求中的实际工具，包含媒体阶段二次过滤。仅 archive 代表历史真实流量。草稿内容、绑定 Skill、区域、待答问卷、纠正候选、制作授权均可进一步改写 wire。

| 工具 | 执行与状态持有者 | 裁决 |
|---|---|---|
| revise_video | 两个 Turn._revise_video → revise_video_seat → editing.service.revise_video → expand_revision_op，结果为版本与差异 | 切除模型入口及标题特判；保留有 HTTP 消费者的算法 |
| design_video / review_working_draft | design_video_seat / review_working_draft_seat；工作草稿、审阅证据、最后一次保存 | 旧首稿仍有消费者，按创建、观察逐项替换 |
| get_video_version / review_video | perception.executes.get_video_version、read_video_for_presentation、review_video_seat；确切版本或已交付 Output | 保留读面与来源校验 |
| get_understanding / get_asset / search_transcript / get_segment / list_project_media / get_web_page / search_web / search_music | perception.executes 中的同名函数，通过 run_perception_tool 返回素材、来源、词轴、网页或乐库结果 | 观察能力，按需求保留 |
| list_skill_shots / read_skill_reference / read_skill_demo / get_skill_preview | skill_read_seat，绑定包及已读回执 | 保留不可变包读取 |
| prepare_video_materials / capture_web / analyze_brand | 同名 seat；项目素材、快照、品牌事实 | 保留取证，移除工序门控 |
| show_video_presets / select_video_preset / search_sfx / import_sfx / show_music_candidates / select_music | 同名 seat；包、候选回执、SFX Snapshot、选择记录 | 复用素材，分割无需候选或提案 |
| prepare_visual_assets / prepare_narration / prepare_music / get_narration_alignment / annotate_narration | 同名 seat；缓存/真实资产、NarrationAlignment、工作草稿。未命中项由 dock_media_observation 转 Task | 后续以真实授权后的提交取代 _dock_tasks；保留 _remember_music_request、_submit_music_observation 和 worker |
| present_plan / propose_tasks / start_run | 两个 Turn 的提案与启动分派；pending_brief、待确认消息、Run、费用预留 | 从基础编辑切除；后续迁移有费用的消费者 |
| list_runs / get_run_status / get_pending_plan / retry_upload | 前三项 perception.executes 同名，重传走 ChatTurn；Run、Step、上传缓存 | 留在执行恢复面 |
| get_graph / get_node / edit_graph | 同名读取与 edit_manual_graph；Graph 行 | 排除视频编辑；保留手动画布 |
| ask_user / answer | Turn 终结分派；问题或回复 Message | 保留歧义澄清与正文 |
| read_conversation_context / 候选修正工具 | ConversationContext.read / ToolLoop 候选校正；已持久化 exchange、作用域和 digest | 保留精确恢复，取消保存作品编辑的默认历史投影 |

只有版本写、快照/资产生成、候选导入等会改变相应持久状态。读取、计划与活动行均不能作为版本提交的证据。

## Editing 调用图

edits.py 的每个 Op 类都是带有验证规则的输入结构，算法位于 _apply_one / temporal.py：

- SetSettings、BindSource、UnbindSource 更新设置或受约束的来源绑定。AddScene、UpdateScene、RemoveScene、MoveScene 管理场景顺序、引用及范围。AddTrack、RemoveTrack、AddClip、UpdateClip 管理归属、ID、实际对象值及失效。SetTransition、RemoveTransition 管理有方向的切点关系。
- TrimClip、RemoveClip 委托 TemporalEdit；保留公共目标解析、关联范围、时间和源范围映射。SplitClip 复用 resolve_temporal_target / slice_clip，负责联动组、对象与动画 ID、转场重接。直接传入已验证 Tool 参数，无需 expand_revision_op。
- EntityWrites / ClipEntityWrite 用于草稿实体去重和合并。apply_ops、apply_entity_writes_raw 维护批处理一致性，store.apply_composition_edits 是持久写入口。
- revisions.py 的 SetTextOp、SetNarrationOp 经 _one_clip 再展开，对文本部件和派生结果有实际作用；RemoveClipOp 属目标解析转发。AddMediaOverlayOp、AddNarrationOp、AddAudioEffectOp、ApplyPresetOp 还会展开绑定、轨道和多个实体，具备原子批处理语义。编辑 HTTP 与音频 Inspector 仍消费 revise_video，不删除这些算法。

## Prompt、Chat、恢复

PlanTurn.assemble 和 ChatTurn.assemble 读取对话/Run/素材与 video_context_lines；prepare_bound_skill_context 的 reader 在每次模型调用读取最新项目，load_project_context 从 head 与 Version 构建 scene/clip_targets。assemble_video_round 又投影 target、base_ref、region 和可见动作；_compact_title_round 以正则再缩窄一次。保存作品只需一个版本引用、结构摘要和按需读取。ConversationContext.restore 调 select_items 选取历史 exchange / 草稿，ToolLoop 会重新组装 assistant/tool 对。record、read、Stop 的 discard_turn_context 和后台 continue_media_journey 仍需持久记录。

ToolPresentation 驱动 ActivityProjector 的 name_known / ReadExecuting / ReadAccepted 或 rejection，routes 的 SSE pump 与 append_activity_row / settle_activity_row 共用持久帧，刷新从消息读取。终结 answer 保存正文。旧 _present_plan / _propose_tasks 将结果转为 question dock，start_run 再调用编排器。_dock_tasks 自动走此路径，continue_media_journey 又建立后续回合。普通分割应在一次 Tool 执行中提交。

Store._replay_request 校验 owner 和请求 digest，行锁内复查后执行 base CAS，失败回滚；消息 Stop 与最终提交由 service._lock_turn_for_transcript_write 串行化。pipeline 的 orchestrator / lifecycle 管理 Run、claim token、取消和结算，余额、hold/capture/release 与未知供应商结果保持在原执行边界。snapshot_facts / validate_content 校验绑定，交付 pin_video_production 与 renderer manifest 固定输出版本。§9A 审阅事实区分和快照复用，§9B 直接提交的稳定请求身份与事务均在检查点。
