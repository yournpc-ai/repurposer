# Agent Editor 执行架构

用户的当前要求保存在项目会话的 opening 消息。Agent 通过原生工具读取素材与作品、修改时间线、查看预览、生成素材及交付。实际注册与调度见 `app/chat/turn_tools.py`、`app/chat/editor.py`、`app/chat/plan_turn.py` 与 `app/agents/tool_loop.py`。

| 操作 | 写入或读取 | 恢复身份 |
| --- | --- | --- |
| 首稿与即时剪辑 | `create_video` 支持 `shots` 与原生 `motion_blocks`（含资源绑定、正交 `style_preset` 与幕间 `transition_after`）原子提交 v1；`insert_motion_block` 支持平滑自动扩展画布总时长（上限 180s、间隔上限 2s）；`apply_composition_edits` 校验 head 和 digest，保存新的 CompositionVersion | 原生调用、版本、结果回执 |
| 预览 | preview_range 读取指定版本和窗口的真实帧及混音分析 | 版本、范围、预览摘要 |
| 图片、旁白、音乐 | MediaJob 复用媒体领域实现，固定 SourceSnapshot，结算已有钱包 | 项目、opening、call、Job、claim_token |
| 音效合成 | `generate_sfx` 经 `apps/render` 调 `@repurposer/sound-engine` 零积分确定性合成 48 kHz WAV，固定为 SourceSnapshot；已有作品时支持传 `place_at_seconds` / `gain_db` 原子一步落轨至 `effect` 音频轨 | owner、project、spec_sha256、wav_digest、可选版本回执 |
| 整片风格换装 | `set_composition_style` 经 `apply_composition_edits` 原子切换 `settings.style`、画布底色、Motion Block 继承与派生字幕（保护 `independent` 字幕与全部音频轨不动） | 原生调用、版本、风格回执 |
| 文字与字幕增改 | `insert_text`（直写花字/角标/双语字幕或由已对齐音频/ASR 生成派生字幕轨）与 `edit_text`（按 `clip`/`track`/`all_derived_captions` 原子编辑文案、安全区位置与 11 套行业预设，含 `karaoke_focus` 逐词动画自动重建与 `independent` 字幕/音频轨保护） | 原生调用、版本、文字回执 |
| 模板固化与换料 | `save_composition_as_skill` 脱敏提取 `slot_blueprint_v1`（含 `blueprint.style`，并下发 `skill_saved` 回执提供「编号槽位宣传片」快捷预览入口）；`instantiate_skill_blueprint` 按槽位与可选 `style_preset`/`accent_color` 跨风格换料并原子提交新版本；独立 Slot 宣传片工具（`app/skills/slot_preview.py`、`/api/v1/skills/*`、`scripts/render_slot_preview.py`、`SlotPreviewDialog.tsx`）支持全 13 块 `[01]..[N]` 预览、4 风格切换与 1080p MP4 导出 | SkillVersion、blueprint digest、CompositionVersion |
| 正式导出 | ExportJob 锁定版本，Renderer 上传后核对 MP4，提交 Output、资金和回执 | 版本、Job、对象 key、实际字节摘要 |
| 审阅、交付 | review_video 读取实际 Output，deliver_video 核对已审阅身份 | 持久消息、版本和 Output 引用 |

## 模型推理分档与端到端创作管线

- **模型推理分档（`app/agents/tool_loop.py` & `app/providers/llm/minimax.py`）**：视频编辑/导演轮（`"video_target" in caller_state`）默认开启 `thinking={"type": "adaptive"}`、`reasoning_effort="xhigh"`、`reasoning_split=True`，保证多幕节奏规划、DOM 坐标选择与音画踩点质量；普通轻量对话与 `app/chat/warmup.py` 启动预热保持 `thinking=False`（`reasoning_effort="low"`）以控制首字延迟。
- **主时钟双管线（Beat Sheet）→ 多轨编排 → 视觉自检**：用户只需给出网址、资料或一句简短意图（无需手写分镜或镜头描述）：
  1. **采集与理解**：抓取目标网页真实视图/DOM 坐标或读取用户素材，必要时一次 `ask_user` 对齐核心受众/语言/风格基调；
  2. **确立主时钟与节拍骨架（Beat Sheet）**：
     - *旁白驱动型（产品宣传/知识讲解/口播）*：先定分幕讲稿并生成/对齐旁白，以实测句/词时间轴与 `0.4–0.6s` 幕间气口作为全片节拍骨架；
     - *节拍/音乐驱动型（无旁白快剪/悬念预告/动态文字）*：先锁定配乐与关键时间锚点（Beat Grid），不强行注入旁白；
  3. **围绕节拍骨架多轨编排**：按每拍选择原生 Motion Block（13 块）或真实网页交互/B-Roll 图文叠层（支持幕内 `reveal_at_s` / `callout_steps` 逐拍响应），叠加 BGM 循环与 v2 多轨长短音效（底噪/起势 + 切点重击 + 幕内微点缀）及 5 种电影转场；
  4. **视觉与音频自检闭环（Eval）**：通过 `preview_range` / `review_video` 抽帧与检查音频能量窗/掩蔽提示，发现遮字、偏移或电平冲突立即单实例修订，验收无误再交付或固化为可复用 Template（必要时可由独立工具生成带数字编号的 Slot 宣传片）。

## Chat 对话过程呈现契约与视频编辑提示词组织

- **视频编辑系统提示词（`apps/api/app/prompts/chat/video_editor.j2`）**：`assemble_video_round` 复用共享的 `_identity_menu.j2`、`_interaction_constitution.j2` 与 `_markdown_speech.j2`，以 5 节结构化 Markdown 明确 5 步剪辑闭环、双主时钟 Beat Sheet、正交风格包与多轨声画/自检纪律、局部修订/Skill 规则及硬安全边界；所有工具参数语法、4 套风格包、11 套文字与字幕预设、13 个 Motion Block 与 22 个 v2 音效配方归位到 `app/chat/editor.py` Schema 与 `creative_catalog`。
- **脱敏中段播报、实时阶段焦点与三段式无框工作轨（`tool_loop.py` + `activity.py` + `timeline/liveState.ts` + `ActivityStream.tsx`）**：
  - 服务端在存在 `editor_labels`（含 `composition_id`、`version_id`、`clip_id`、`object_id` 与短前缀映射）时关闭原始 `on_delta` 防内部 ID 泄露，同时保留经 `project_editor_reply` 脱敏后的阶段说明与最终回复；
  - 多步骤创作进入或切换阶段时，模型可与该阶段首个真实工具并行调用零副作用的 `update_focus(focus)` 与 `update_steps(steps)`；`activity.py` 对文案脱敏并向 SSE `assistant.activity` 下发 `kind="focus"` 与 `kind="steps"` 实时帧（均不生成冗余活动步骤行）；回合结算时将最终进度清单写入助手 `Message.intent["steps"]`（正常完成时将残留 `in_progress` 项标为 `done`）供历史回放；
  - 高频编辑工具（`set_composition_style`、`insert_motion_block`、`update_motion_block`、`insert_text`、`edit_text`、`generate_sfx`、`edit_audio_clip`、`set_transition`）在执行入口由 `project_tool_detail` 基于已校验参数确定性投影出不含内部 ID 的结构化 `detail` 字段并随活动帧实时下发与落库，前端经双语字典渲染为参数语义化步骤行，缺失时无缝回退既有静态工具词表；
  - 前端以纯状态机 `timeline/liveState.ts` 统一驱动基于 `@affectui/thinking-state-clean` 的三段式体验：① **直播期（`live_working`）**默认展开，顶栏优先展示 `liveFocus`，工具步骤（语义参数标签 → 静态工具双语动词回退，详细回执按行折叠）与同事口吻阶段说明自然交替呈现；② **末段思考期（`live_post_tool_thinking`）**在工具全部结算后、最终回复吐字前平滑展示实时计时 `Thinking Xs` 状态行；③ **终态（`settled`）**自动清除 `liveFocus` 并将全过程收拢为单条无框 `Worked for Xs ›` 置于最终回复正文上方，点击可完整回溯。真实交互与交付实体（`ask_user` 决策卡、单层 `ApprovalCard`、音频候选、固定 Output 交付卡、孤立终态失败）始终独立留驻、不被吞并。
- **待决卡片旁路插话与转向承接（`prompts.py` + `plan_turn.py` + `video_editor.j2`）**：当会话存在未点击的待回答问题或 `media_permission` 付费授权卡而用户发送自由文本消息时，轮次继续完整装配编辑器上下文与 `pending_question`（付费授权卡附带 `awaiting_media_authorization: true`），并允许直接正文答复不触发 `answer` 取消护栏：① **旁路提问/插话**时，助手用用户语言自然完整答复，保持 `pending_disposition="none"` 保留原待决卡，并在结尾用一句同事口吻温和拉回原确认事项（不附加僵硬系统提示块）；② **明确取消或改走新方向**时，通过 `pending_disposition="skip"` 优雅关闭旧待决卡（对 `media_permission` 同步标记为 `declined` 并取消等待授权的活动行），立即按新方向推进；纯文字回答永不自动放行付费授权。
- **多会话、上下文压缩、质量评估与项目工作台投影**：
  - **Project 1:N Conversation**：同一 `Project` 支持多条独立 `Conversation`（`GET/POST /api/v1/projects/{project_id}/conversations`、`PATCH /api/v1/chat/conversations/{conversation_id}`、`POST /api/v1/chat` 与 `GET /api/v1/chat/conversation` 支持显式 `conversation_id`，省略时默认选取最近活跃会话），各会话私有维护消息记录、待决问题与 `Conversation.context`，同时天然共享项目级 `Asset`、`Composition`、`CompositionVersion` 与 `Output`；默认标题在首条用户消息时自动截取生成。
  - **会话上下文压缩（`POST /api/v1/chat/conversations/{conversation_id}/compact`）**：汇总当前会话已结算消息与关键决策写入 `Conversation.context["compact_summary"]`（含 `compacted_through_seq`）；装配送模历史时跳过已压缩旧消息并将摘要注入本轮上下文，历史消息查询接口仍返回完整可读记录与 `compact_summary` 元数据。
  - **回复质量评估快照（`message_feedback` + `POST /api/v1/chat/messages/{message_id}/feedback`）**：回合结算时在助手 `Message.intent["eval_meta"]` 写入轻量 Prompt/模型/版本指纹（对外 API 序列化不可见）；用户点选 `good`/`bad` 反馈时幂等落库 `message_feedback` 并冻结完整 `context_snapshot`（用户开场输入、助手回复与步骤、Prompt 指纹与上下文摘录、工具活动与拒绝取证、作品版本引用及压缩摘要），点取消则删除反馈行。
  - **项目工作台与异步任务投影（`GET /api/v1/projects/{project_id}/workbench`）**：单次 owner 校验请求聚合项目基础信息、全部 `Composition` 及其有序版本、可见 `Output`、项目 `Asset`、活跃后台任务（排队/运行中的 `ExportJob`、`MediaJob` 及处理中 `Asset`）与用户已保存的 `slot_blueprint_v1` 技能摘要。
- **Studio Workbench 分栏交互与对话流体验（`apps/web/src/components/workbench/`、`ProjectConversationsTree.tsx`、`TurnMinimap.tsx`、`MessageActionBar.tsx`）**：
  - **左侧 `Project → 多 Conversation` 树**：`/projects/$id` 路由支持可选查询参数 `?c=<conversationId>`，侧栏展开项目对话列表（含活跃后台任务脉冲点、消息计数与相对时间）、新建对话、重命名与上下文压缩；切换会话仅更新左侧 `AgentThread`，右侧 `WorkbenchPane` 持续与同一 `Project` 保持资产与版本同步；会话已压缩时在 `compacted_through_seq` 位置展示温和分割提示而不隐藏可读历史。
  - **右侧可折叠/可拖拽多 Tab 产物看板（`WorkbenchPane`）**：基于 `motion/react` 平滑滑入滑出并记住拖拽宽度，内含「草稿预览（版本切换与懒加载 `@remotion/player` / 成片 MP4）」「帧与素材（直接挂载 `MediaRegionSelectionOverlay` 拖框选区并一键引用回左侧输入框）」「槽位宣传片（复用 `SlotPreviewContent`）」三组原生标签页；`AssistantText` 拦截 Markdown 内部产物链接（`#workbench:version|output|asset|skill/<id>`）渲染为行内芯片，点击直达对应 Tab，`StoryboardCard` 与 `OutputDeliveryCard` 同步提供右侧打开入口。
  - **对话流进度与反馈原语**：`ThinkingState` 在顶栏展示进度环与 `done/total steps` 徽章并在展开体顶部渲染动态步骤清单（覆盖实时 SSE `kind="steps"` 与历史 `steps` 回放）；`AsyncJobStrip` 仅在存在活跃后台任务时按 3 秒轻刷并在输入框上方无框提示且不阻断输入；`TurnMinimap` 在桌面端用户轮次 ≥ 3 时提供左侧圆点定位与版本预览；`MessageActionBar` 在每条已结算助手回复底部提供复制、乐观更新 👍/👎 反馈（点 👎 弹出非阻塞标签/原因浮层）与自动刷新的相对时间。
- 费用批准、Stop、租约与原 opening 的续行仲裁由服务端执行。后台 Worker 分别认领素材、旁白对齐、MediaJob、ExportJob、社交发布及支付告警，并清理暂存对象。Publication 记录外部发帖是否已提交；无法核实的结果需要保留凭据。

模型边界位于 `app/providers/llm`。工具的原生名称、参数 Schema、项目事实与消息回放在模型请求时装配。可复核的实测样本见[原生模型请求](tasks/agent-editor-evidence/iteration-6/6d-native-journey.json)。编辑器产品合同、专业剪辑扩展与阶段验收见[主合同](tasks/new-agent.md)。
