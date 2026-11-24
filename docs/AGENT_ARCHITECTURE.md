# Agent Editor 执行架构

用户的当前要求保存在项目会话的 opening 消息。Agent 通过原生工具读取素材与作品、修改时间线、查看预览、生成素材及交付。实际注册与调度见 `app/chat/turn_tools.py`、`app/chat/editor.py`、`app/chat/plan_turn.py` 与 `app/agents/tool_loop.py`。

| 操作 | 写入或读取 | 恢复身份 |
| --- | --- | --- |
| 即时剪辑 | apply_composition_edits 校验 head 和 digest，保存新的 CompositionVersion | 原生调用、版本、结果回执 |
| 预览 | preview_range 读取指定版本和窗口的真实帧及混音分析 | 版本、范围、预览摘要 |
| 图片、旁白、音乐 | MediaJob 复用媒体领域实现，固定 SourceSnapshot，结算已有钱包 | 项目、opening、call、Job、claim_token |
| 音效合成 | `generate_sfx` 经 `apps/render` 调 `@repurposer/sound-engine` v2 零积分确定性合成 48 kHz WAV，固定为 SourceSnapshot | owner、project、spec_sha256、wav_digest |
| 整片风格换装 | `set_composition_style` 经 `apply_composition_edits` 原子切换 `settings.style`、画布底色、Motion Block 继承与派生字幕（保护 `independent` 字幕与全部音频轨不动） | 原生调用、版本、风格回执 |
| 文字与字幕样式 | `apply_text_style` 经 `apply_composition_edits` 按 `clip`/`track`/`all_derived_captions` 原子套用 11 套行业文字/字幕预设（含 `bilingual_cinema` 单 Clip 双语排版与 `karaoke_focus` 逐词 `TextPart` 动画），严格保护 `independent` 字幕、非字幕文字与音频轨 | 原生调用、版本、样式回执 |
| 模板固化与换料 | `save_composition_as_skill` 脱敏提取 `slot_blueprint_v1`（含 `blueprint.style`）；`instantiate_skill_blueprint` 按槽位与可选 `style_preset`/`accent_color` 跨风格换料并原子提交新版本 | SkillVersion、blueprint digest、CompositionVersion |
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
- **脱敏中段播报与三段式无框工作轨（`tool_loop.py` + `timeline/liveState.ts` + `ActivityStream.tsx`）**：
  - 服务端在存在 `editor_labels` 时保持关闭原始 `on_delta` 防内部 ID 泄露，同时保留经 `project_editor_reply` 脱敏后的阶段说明经 `on_interim_prose` 持久并实时下发；
  - 前端以纯状态机 `timeline/liveState.ts` 统一驱动基于 `@affectui/thinking-state-clean` 的三段式体验：① **直播期（`live_working`）**默认展开，工具步骤（覆盖全部 46 个高频工具双语动词，详细回执按行折叠）与同事口吻阶段说明自然交替呈现；② **末段思考期（`live_post_tool_thinking`）**在工具全部结算后、最终回复吐字前平滑展示实时计时 `Thinking Xs` 状态行；③ **终态（`settled`）**自动将全过程收拢为单条无框 `Worked for Xs ›` 置于最终回复正文上方，点击可完整回溯。真实交互与交付实体（`ask_user` 决策卡、单层 `ApprovalCard`、音频候选、固定 Output 交付卡、孤立终态失败）始终独立留驻、不被吞并。
- 费用批准、Stop、租约与原 opening 的续行仲裁由服务端执行。后台 Worker 分别认领素材、旁白对齐、MediaJob、ExportJob、社交发布及支付告警，并清理暂存对象。Publication 记录外部发帖是否已提交；无法核实的结果需要保留凭据。

模型边界位于 `app/providers/llm`。工具的原生名称、参数 Schema、项目事实与消息回放在模型请求时装配。可复核的实测样本见[原生模型请求](tasks/agent-editor-evidence/iteration-6/6d-native-journey.json)。编辑器产品合同、专业剪辑扩展与阶段验收见[主合同](tasks/new-agent.md)。
