# Agent Editor 的 Chat 执行契约

用户在项目内提交素材和要求。POST /chat 校验所有者，保存用户消息并以该消息作为 opening。后续工具、授权、Stop 和异步续行都能指回这个身份。素材与作品使用项目权限，跨项目提及不授予读取或写入权限。

## 模型如何接手作品

chat/plan_turn.py 组装当前消息、项目素材、已知 Brief 及其来源、最近消息、待回答问题和费用偏好。chat/editor.py 和 chat/turn_tools.py 声明的原生工具经 agents/tool_loop.py 发给 Provider。模型通过 list_project_media、inspect_timeline 等实际读取定位作品；编辑从所选版本和 digest 经 apply_composition_edits 写入新版本。preview_range 返回该版本在指定窗口内的真实观察。模型自选的细节保持建议身份，只有用户说出的约束可作为用户要求。实际请求样本见[模型请求与作品旅程](tasks/agent-editor-evidence/iteration-6/6d-native-journey.json)。

## 媒体、授权和交付

chat/editor_media.py 在生成前校验 opening、项目、原生 call ID、参数指纹和报价。需要授权时持久化带 approve/decline 选项的问题。服务端在回答原问题时使用原参数和上限。报价问题、授权接受、供应商实际返回以及钱包结算分别有自己的事实。

MediaJob 固定旁白、音乐或图片，成功回执包含所属项目、快照、摘要、时长或尺寸、计费与可用状态。插入时间线产生新的 CompositionVersion。ExportJob 固定确切版本与渲染规格；成功的 Output 可以审阅。review_video 读取真实 MP4，deliver_video 核对审片摘要、版本及字节后写入持久交付消息。后续修改保存新版本，之前的卡继续指向当时的 Output。

## 消息、Stop 与恢复

- SSE 提供 turn.started、assistant.row.append、assistant.row.update 和回合完成或失败通知。消息顺序使用会话内 seq。原生 Tool Group 以 group_id 与 call_index 排序，call_id 标识各成员，各自保留结果。
- 客户端按原 opening 发送 Stop，提交实际可见的正文前缀、Activity 和组件 ID。空可见前沿可撤回 opening。已提交版本、固定媒体、Output 与账本按原身份保留。
- 刷新读取原会话消息、原问题和作品引用，同一执行消息可由 Job 更新。Worker 与请求端恢复共用 opening 的数据库锁和持久回执。恢复时原请求、已执行操作、当前 head 与尚未授予的费用仍然可区分。
- 分镜展示 ACK 验证消息、确切版本和 digest。授权在其对应的原生调用上处理。组件按原消息的 blocks、output_refs 及 reviewed_version 回放。用户下载的文件来自所选 Output 的授权播放接口。

Chat 前端的文件归属、字段、排序与恢复见 [UI 交接](tasks/agent-editor-evidence/iteration-6/ui-handoff.md)。作品编辑、音频、字幕和专业剪辑扩展见 [Video Project](VIDEO_PROJECT.md)。
