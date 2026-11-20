# 接管基线 353f242d

原 main 比交接记录多一个提交，21 个路径含 test_music_submission.py。唯一未跟踪文件是用户的 docs/tasks/new-agent.md。检查点 09cf1873 保存其原文。原目录的 dev.sh 启动 uvicorn --reload、worker、web 和 renderer。数据库只读调查发现 208 部作品，201 个 Run、322 个 Step 全部终态，素材 518 completed / 22 failed。40 条消息在接管时仍标 in_flight，最新一条 in_flight 来自 11 月 16 日。9 条对齐标 ALIGNED。未见独立 pytest 进程。保留所有现场行与服务。

## 原生工具入口及切除顺序

baseline-wire.json.gz 内 definitions 是完整的 tool_spec（已执行 wire_view）结果，projections 将路线和阶段对应到定义。registered 是部署的声明上界，分阶段条目是受控输入下的投影，archive 是既有 provider 请求中的实际工具，包含媒体阶段二次过滤。仅 archive 代表历史真实流量。草稿内容、绑定 Skill、区域、待答问卷、纠正候选、制作授权均可进一步改写 wire。

| 工具 | 执行与状态持有者 | 裁决 |
|---|---|---|
| revise_video | 两个 Turn._revise_video → revise_video_seat → editing.service.revise_video → expand_revision_op，结果为版本与差异 | 切除模型入口及标题特判。完整实体修改仍有 HTTP 消费者，批处理算法见下表 |
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
| wrap_up | trigger_turn.run_trigger_turn 内的 execute，校验结尾与选项，写入后台审阅消息 | 保留交付收尾 |

只有版本写、快照/资产生成、候选导入等会改变相应持久状态。读取、计划与活动行均不能作为版本提交的证据。

## Editing 调用图

edits.py 的每个 Op 类都是带有验证规则的输入结构，算法位于 _apply_one / temporal.py：

- SetSettings、BindSource、UnbindSource 更新设置或受约束的来源绑定。AddScene、UpdateScene、RemoveScene、MoveScene 管理场景顺序、引用及范围。AddTrack、RemoveTrack、AddClip、UpdateClip 管理归属、ID、实际对象值及失效。SetTransition、RemoveTransition 管理有方向的切点关系。
- TrimClip、RemoveClip 委托 TemporalEdit；保留公共目标解析、关联范围、时间和源范围映射。SplitClip 复用 resolve_temporal_target / slice_clip，负责联动组、对象与动画 ID、转场重接。直接传入已验证 Tool 参数，无需 expand_revision_op。
- EntityWrites / ClipEntityWrite 用于草稿实体去重和合并。apply_ops、apply_entity_writes_raw 维护批处理一致性，store.apply_composition_edits 是持久写入口。
- revisions.py 的 SetTextOp、SetNarrationOp 经 _one_clip 再展开，对文本部件和派生结果有实际作用；RemoveClipOp 属目标解析转发。AddMediaOverlayOp、AddNarrationOp、AddAudioEffectOp、ApplyPresetOp 还会展开绑定、轨道和多个实体，具备原子批处理语义。唯一现役 HTTP 写消费者是 chat.routes.revise_video_clip，用于原生文本 Scrub 手势，只传 ReviseVideoArgs 的完整 Clip。它没有调用 expand_revision_op。ReviseVideoOpsArgs 分支及展开算法目前由 test_promo_authoring 覆盖，其中仍有跨引用权限校验、NarrationAlignment 归属校验及多个实体的原子写。它没有注册为模型工具。

## Prompt、Chat、恢复

PlanTurn.assemble 和 ChatTurn.assemble 读取对话/Run/素材与 video_context_lines；prepare_bound_skill_context 的 reader 在每次模型调用读取最新项目，load_project_context 从 head 与 Version 构建 scene/clip_targets。assemble_video_round 又投影 target、base_ref、region 和可见动作；_compact_title_round 以正则再缩窄一次。保存作品只需一个版本引用、结构摘要和按需读取。ConversationContext.restore 调 select_items 选取历史 exchange / 草稿，ToolLoop 会重新组装 assistant/tool 对。record、read、Stop 的 discard_turn_context 和后台 continue_media_journey 仍需持久记录。

ToolPresentation 驱动 ActivityProjector 的 name_known / ReadExecuting / ReadAccepted 或 rejection，routes 的 SSE pump 与 append_activity_row / settle_activity_row 共用持久帧，刷新从消息读取。终结 answer 保存正文。旧 _present_plan / _propose_tasks 将结果转为 question dock，start_run 再调用编排器。_dock_tasks 自动走此路径，continue_media_journey 又建立后续回合。普通分割应在一次 Tool 执行中提交。

Store._replay_request 校验 owner 和请求 digest，行锁内复查后执行 base CAS，失败回滚；消息 Stop 与最终提交由 service._lock_turn_for_transcript_write 串行化。pipeline 的 orchestrator / lifecycle 管理 Run、claim token、取消和结算，余额、hold/capture/release 与未知供应商结果保持在原执行边界。snapshot_facts / validate_content 校验绑定，交付 pin_video_production 与 renderer manifest 固定输出版本。§9A 审阅事实区分和快照复用，§9B 直接提交的稳定请求身份与事务均在检查点。

## 核对入口与实际改动

解压同目录的 `baseline-wire.json.gz` 可查到 46 个不同的模型工具名、93 份去重后的完整 function 声明及 131 组投影。`tool_index[工具名]` 给出执行函数、状态持有者、结果、是否修改 Composition、处置、Activity 的 key/variant 和可见投影。每份 schema 的 properties、required 和嵌套定义均在 `definitions`。两条用户 Chat 入口、后台 trigger、候选纠正均计入。日期为 11 月 18 日的 archive 条目来自当时的真实流量；日期不同的 wire 独立编号。active-candidate 条目用基线函数与受控草稿输入生成。确认或候选的内容可继续收窄可见字段，这些样例没有穷举所有用户数据组合。

| 位置 | 已经删除或替换的具体行为 | 仍在使用的消费者 |
|---|---|---|
| chat.turn_tools | 删除 _edit_op_signature、_revise_video_wire_view、_direct_revision_wire、_direct_ops_for_target、_restrict_direct_ops 和 version_edit 的 schema 分支 | 初次草稿、素材准备、创作确认仍走原阶段代码 |
| chat.prompts、tools.project_context | 删除 _compact_title_round、_region_target_candidates、_target_resource_projection、region_target_candidates 和默认全量 clip_targets。保存作品每轮读取 head 的结构计数，inspect_timeline 按需读取 24 个片段及源时间窗 | 普通对话仍提供用户文本。首稿与后台恢复继续使用草稿、素材及项目摘要 |
| chat.plan_turn、chat.propose_turn | 删除两个 _revise_video 与歧义回填，接入同一个 execute_editor。直接编辑路径撤掉 Plan/Start 声明 | 真实费用确认、媒体任务和已有运行中的执行仍由旧代码收尾 |
| chat.video_turn_seats、agents.tool_loop | 删除 revise_video_seat、bind_video_revision_base、video_mention_guard、VideoTargetAmbiguityFeedback 与无消费者的 bare_rejection_feedback。删除 SFX/音乐回执对旧 Op 的操作指令 | video_target_hint 读取显式目标，editor 在自己会话内校验归属、版本与请求身份 |
| models.schemas、editing.service | 删除 ReviseVideoTextArgs、专用文字参数分派和 format_revision_text。保留 replace_text_ops 等领域算法 | 文本手势、纯算法及原子媒体批处理验证 |
| chat.service、web/StoryboardCard | 限定时间窗的预览消息引用版本与范围。刷新时按字段匹配范围。range 卡跳过旧制作展示确认 | 历史分镜、交付卡及收费制作确认继续沿用自己的生命周期 |
| chat.conversation_context | 保存作品的普通回合跳过 restore 的历史 assistant/tool 注入。ToolExchange 继续 record，read_conversation_context 可分页取回，媒体 resume 继续原有恢复 | select_items 仍识别历史 revise_video 记录，Stop 仍清理被撤回回合产生的可见上下文 |

## 可靠性边界

| 约束 | 持有者及验证点 |
|---|---|
| Stop 与事务 | chat.service.stop_turn_at_visible_frontier 与 _lock_turn_for_transcript_write 锁同一条 opening Message。split_clip 在持锁会话中提交版本。Stop 先赢则拒绝新写，版本先提交则保留版本。取消后台 Run 仍走 pipeline.orchestrator.cancel_run |
| 身份、重放、竞争 | editor.split_clip 使用 opening UUID 和原生 call ID 得出 request_id。editing.store._replay_request 检查请求摘要，apply_composition_edits 再持锁读 head、验证 base、写版本并移动 head。锁后刷新 ORM 身份缓存，防止在过期本地对象上比较 |
| 来源、快照、交付 | editing.store.get_video_version、snapshot_facts、editing.validators.validate_content 与 tools.video.production.pin_video_production 校验来源、作品归属和确切版本。预览的 renderer spec 与浏览器的 parseScopedPreviewSpec 各自核对其范围 |
| 余额及计费 | platform.billing.check_hold、hold_run、capture_step、release_run 与 wallet/ledger 保留；pipeline.orchestrator 与 lifecycle 保留工作领取、取消和失败处理。本批分割没有发起付费素材任务 |
| 外部结果不明 | tools.video.generated_images、tools.video.narration_store.mark_outcome_unknown、chat.media_journey.dock_media_observation / _remember_music_request / _submit_music_observation 继续区分失败、未知、可复用的事实；worker 与恢复记录没有迁移到 Chat |

后续删除的先决条件是找到并迁走实际消费方。媒体 Dock 和 continue_media_journey 依赖资金、资产和后台续接；先替换已有授权后的实际提交与可试听结果，再移除对应 Start。首稿审阅仍依赖 design_video 和工作草稿，待创建与审阅各有真实操作后再切除。手动画布、历史执行与已交付版本仍可按现有权限读取。
