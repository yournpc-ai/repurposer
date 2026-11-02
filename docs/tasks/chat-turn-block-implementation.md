# Chat TurnBlock 四阶段施工与验收

> Status: 阶段一至四及 Chat 修复上下半批均已落码。当前完整 API 1447 pytest、Web 352 tests、Web tsc、check_gates 均已通过；真实浏览器与付费旅程未运行。当前代码在正常路径只从各 delivery 自己的 `intent.output_refs` 解析交付；同 Run `retry_upload` 以客户端 attachment epoch 重订阅，并以 Run frame 的 `upload_retry_count` 与 trigger ref 区分恢复 delivery。零 delivery 时仅在 review 有界落定或历史水合后展示当前 Run 的真实 delivered 视频，任何 delivery 出现即回到消息自有 refs。pending/answered QA echo 保留 refs，初始慢历史按真实 server id alias 去重。连续工作段的 failed 在原段收成失败收据并进入展开明细，不再追加同级状态行；用户气泡到 assistant 开场为 24px，assistant 内部槽位保持 12px。Chat Stop 的 visible frontier、retract/cancelled 与写口 fence 边界不变。
>
> 当前明确未做：全量 Run cancel/resume 并发重构；真实浏览器中的同 Run 恢复、第二次 delivery、零 delivery 迟到归属、QA 水合、慢历史与刷新旅程；完整数据库旅程和付费视频制作。长期行为法 = [CHAT_ARCHITECTURE §8.10](../CHAT_ARCHITECTURE.md#810-turnblock--runblock-与渐进揭示)；目标目录唯一合同 = [VIDEO_PROJECT §12](../VIDEO_PROJECT.md#12-目标目录与新旧代码处置)。本文只登记当前实施范围、代码接缝与剩余验收，不复制全局排期。
>
> 新增开放批——Worked 工作证据与闭环正文：与 D5 两路能力切片并行，首批仅以现有 `review_video` 打通 typed receipt → Worked 展开 → 结果型正文 → 历史回放；Worked 外层和 Stop/授权边界不变。SFX、component、revision 与 Run 的后续接入归 D5 公共集成。当前未实施、未验证；三路文件所有权唯一合同 = [Video Project 施工合同 §4.5.1](video-project-implementation.md#451-并行切片与文件所有权)。

## 0. 目标与总边界

把当前“正文、活动、Run、结构化卡片平级排列”的消息流，改造成以 `TurnBlock` 为对话工作单元、以 `RunBlock` 为后台制作单元的呈现层。统一处理真实活动、正文打字机、组件渐进揭示、块级动作和历史水合，同时拆开 `ChatDock` 的外壳、传输、时间线、块与叶子行职责。

1. **表现层改造，不建第二领域模型**：不新增持久化 Work/Task 根、通用 UI 事件总线、组件 props wire 或模型生成的 UI schema。`turn_id` 只复用开局 `user_message.id` 表达已有回合关系；Run 继续由 `runId` 持有身份。
2. **不重写未授权的 Chat 行为**：`POST /chat`、plan path、授权、计费、Start、首稿呈现回执与 QuestionDock 保持既有边界；§3C 只改变明确登记的首条消息附件、主动停止/撤回、partial 持久化与 Run 取消语义。Prompt 不负责分组；当前只同步中段言语的 `interim_prose` 称谓，不新增意图规则。
3. **保留承重机制**：持久 `seq`、`birthKey ?? id`、活动原地 append/update、正文 received/shown 分离、实际 drain、一个 Run 一个渲染面、live/history 同事实不得回退。QA、Candidate、material、旧分镜等仍有效旧行读容忍保留；本批明确退役的 Run 级 Output 集合、checkpoint 协议别名和 retracted tombstone 不保留兼容分支。
4. **渐进替换，不做 Big Bang**：每阶段可含多个小提交；机械移动与行为变化分开，静态历史归组先于 live 揭示，Run 与回放清理在 TurnBlock 证明后施工。不得长期保留两套正式时间线真相。
5. **按真实消费者抽象**：`RevealSlot` 首批只服务 Storyboard 与 Output。TTS、Voice 和 Scrub Inspector 只校验适配边界，不在本任务提前实现其业务能力或通用组件平台。
6. **保留并行工作**：施工前核对 HEAD、工作树和文件归属；不用 reset/checkout/stash 制造基线。目录移动与本合同不一致时先更新 VIDEO_PROJECT §12，不在其他文档维护第二份目录树。
7. **Token-only，零新视觉体系**：只消费 `apps/web/src/styles.css` 已注册的语义 token、现有灰梯和 UI primitives，并遵守 `UI_GUIDELINES.md` §4.2～§4.4、§10。不得复制参考组件 CSS/module，不得硬编码色值、创造一次性 alpha/dark 色或新增 TurnBlock 专属 token；缺少视觉角色时先报告，不在组件内补色。

## 1. 目标代码接缝

```text
ChatDock（外壳 / 当前回合与恢复状态编排 / composer 承重结构）
  → ChatConversation（scroller / blocks）
  → timeline 纯投影（types / project / activity / history / speech / reveal）
  → TurnBlock / RunBlock
  → ComponentSlot / RevealSlot / rows / run / video
```

依赖只能向下：`timeline` 不 import React 组件；`history` 不决定布局；`rows` 不读 SSE；`RevealSlot` 只消费真实 `ready` 与前序揭示状态；`RunBlock` 不另建 Run 订阅真相。共享 `OverlayMessage`、ConversationUnit、Block/Slot 类型归 `timeline/types.ts`，不再由历史适配器反向提供。回合/恢复 hooks 只在真实 Block 边界形成后按消费者提取，不预设文件，不为降低行数制造巨型 hook。

## 2. 阶段一——机械拆分与纯时间线地基

### 范围

1. 从 `ChatDock.tsx` 提取 UserMessage、AssistantText、MetaRow 等叶子行；建立 `ChatConversation.tsx`，让 scroller 与消息渲染离开 full/panel 外壳。
2. 回合、恢复、Run 与 composer 的共享状态编排暂留 `ChatDock.tsx`；这些状态共享 refs、seq 观察和回调时序，阶段一不强制建立 `useChatConversation` / `useChatTurn` / `useConversationRecovery`，不以大参数面整体搬迁或制造另一个巨型 hook。
3. 建立 `timeline/types.ts`，承接 `OverlayMessage`、ConversationUnit 与后续 Block/Slot 类型；平移 `chatTimeline`、activity fold、`historyReplay`、`speechSegments` 到目标归属，更新 import 与旁置纯测试。
4. `ChatDock.tsx` 保留外壳、当前状态编排、固定子索引与 MentionEditor 恒渲染结构；阶段一以纯 timeline、叶子行和单一 ChatConversation 接缝为出口，不以文件行数作为独立完成标准。
5. 本阶段不改视觉间距、不改消息协议、不增 `turn_id`、不改 Run 锚点、不改揭示与回放语义。移动叶子组件时保留原有 className 与可见 DOM 结构，不新增 CSS、token 或参考组件样式。

### 出口

- [ ] 所有移动后的 import、类型和依赖方向正确；`timeline` 无 React 组件依赖。
- [ ] full/panel 翻转不 remount MentionEditor；草稿、chips、scrollport 与 output viewer 保持原行为。
- [ ] 相同历史 fixtures 与 live 输入产生逐字节等价的旧投影结果；无消息重排、重复、丢失或键变化。
- [ ] 移动前后的可见 DOM/className 与双主题表现一致；没有新增 CSS、硬编码色值、一次性 alpha/dark 色或 TurnBlock 专属 token。
- [ ] `cd apps/web && npm test` 与 `npx tsc --noEmit` 通过；受影响的既有纯套件在当前 HEAD 重跑，不转信旧基线。

## 3. 阶段二——TurnBlock、渐进揭示与块级动作

> 当前实施状态：A/B/C 与四项收口修复已落码，验收中。Web 298 tests、API 1400 pytest、check_gates 与最新 tsc 均通过；migration 已由用户确认应用并核验，真实浏览器/可访问性验收未完成。四项修复为：question-shaped trigger 的 answered/pending options echo 恢复 run delivery 身份；persisted early failure 按乐观行 id 原位 reconcile 服务端 turn id；Stop 与 send 共用 composer 座位并在停止后聚焦输入；用户真实项目冒烟已证明 Stop→立即重发的新回复正常、旧流不污染新 Turn 且硬刷新一致；每条 chat/answer stream 以局部 owner 阻止旧回调、envelope、failure 与 finally 改写 successor。attached Output 已接入 `RevealSlot`，detached `RunCard` 保留原渲染面，未冒充全部 Output 路径已统一。下方出口在真实浏览器/可访问性验收完成前保持未勾选。
>
> 当前必须走查的已识别风险：`RevealSlot` 以隐藏挂载加载真实 DTO/媒体，hidden video 的 `canPlay` 是否发生决定 Output 能否揭示；正常 delayed-start recovery 仍需真实浏览器验证；`/results` 瞬时失败只保留真实恢复观察，不预防性新增 retry/backoff，取得真实失败证据后再做最小修复。detached RunCard 的 Reveal 消费路径归后续 3B 统一，阶段四 §5.7 只核对无残留双路径。
>

### 3.1 最小身份与静态归组

1. 新产生的相关消息/活动行携带明确 `turn_id = user_message.id`，live SSE 与 history DTO 同批透出；需要的 ORM/DTO/migration 变更按实际写口最小实施。旧列与旧行不伪造关系，不做全库语义回填。
2. `timeline/project.ts` 实现 `rows → units → blocks`：保持持久顺序与稳定 key，不按时间戳、文本相似度或相邻位置猜同一次操作。trigger、material beat、QA 等非普通 Turn 事实保留独立类型或合法关联，不强塞进 TurnBlock。
3. 先用真实历史 fixtures 渲染静态 `TurnBlock`：不同块之间保留回合间距，块内正文、活动与卡片使用独立的紧凑节奏；本步不接 live 动画。
4. 旧数据缺 `turn_id` 时走明确的读容忍回退；回退只保证可读，不宣称恢复了原回合关系。

### 3.2 live 揭示与 ComponentSlot

1. TurnBlock 接管当前活动座位；WorkSegment 可在一个 Turn 内出现多次并独立收成 Worked，WorkSegment 的收口不等于 TurnBlock 完成。
2. 复用现有 `speechSegments` 与 typewriter。组件揭示同时要求真实 payload/reference ready 和必要的前序正文实际 drain；禁止按词数、固定毫秒或完整信封猜用户已经看完。
3. `ComponentSlot` 用 discriminated union 分派现有结构化事实；`RevealSlot` 只负责挂载门槛与首次入场。Storyboard 与 Output 是首两个消费者，history 直接呈现当前状态，不重播 stagger/typewriter。
4. 活动是实时世界事实，不为“假流式”延迟或虚构；未发生、未就绪、未通过交付准入的组件不显示。reduced-motion 取消位移与 stagger，但不改变数据与授权边界。
5. stream Stop 复用 composer send 的原位座位，点击后释放输入并将真实键盘焦点送回 MentionEditor。已有有效回复时保留并持久化真实 partial；没有有效回复时把正文、mentions 与附件缩回 composer，具体持久化与主动停止协议归 §3C。消息流不渲染孤立 Stop 或空动作行，也不预留常驻 `h-9`；只有未来出现真实对象动作时才讨论块级动作。选项建议仍归 dock，重试/制作不得绕过正常授权与计费。

### 出口

- [ ] Thinking → 多动作 Worked → 正文 → 真实组件的主旅程在同一 TurnBlock 内原位演进；组件不与正文/活动平级争抢顶层间距。
- [ ] 开场正文 → 工具 → 中段正文 → 工具 → 最终正文保持真实顺序，多个 WorkSegment 不互相吞并或提前收块。
- [ ] Storyboard 与 Output 的 ready、drain、ACK/交付准入、静态历史与 reduced-motion 行为一致；无假字段流、无固定延时猜测、无刷新重播。
- [ ] 待确认、被拒绝、失败、停止与取消回合无残留活动、未接受预览或虚假 Action；首稿与费用守卫不被组件入场绕过。
- [ ] Block、Slot、Action 和叶子行只使用现有语义 token 与灰梯；双主题无硬编码色值、参考组件 CSS、一次性 alpha/dark 色或新增专属色板。
- [ ] 纯分组/揭示测试覆盖上述分支；web 纯套件、tsc 与针对性真实浏览器旅程通过。

## 4. 阶段三——RunBlock 与制作内部阶段

> 当前实施状态：**3A 薄垂直切片已落码，未封板**。`produce_video` 保持单节点、`retries=0`；真实发射点已接保存版/执行输入校验、字体、实际存在的 Generator/Speech 媒体准备、video-spec 编译、Output 新建或复用，以及 render 排队请求。未启用旁白不写 Speech 阶段；缓存与 resume 只记录实际复用计数/事实。阶段持久于 `workflow_steps.spec.production_stages`，携带稳定 `event_id/kind`、run/step/attempt、持久 `seq`、状态和真实起止；写入使用短事务行锁与当前 attempt/claim_token 围栏，live snapshot、`step.updated` 与历史序列化共用同一 DTO，旧 Run 缺字段仍读原 Prepare/Render。
>
> attached `RunBlock` 只重组 ChatDock 既有 steps/run props 与唯一 `useRunEvents` 数据面，`RunTaskList` 负责步骤与当前 attempt 内部阶段投影；Output 仍由匹配 delivery 的真实首显/drain 或历史水合控制揭示，detached `RunCard` 未另开订阅或重写。真实 render start/finish（`claim_pending_render` / `render_output`）与 delivery admission **未接入阶段记录，明确留给 3B**；本批只有 render queued，不冒充 rendering/delivered。多次 delivery 的逐 Output Reveal、detached 统一及完整失败/重试矩阵仍归 3B。3A 已补受限纯测试；Web 301 tests 与 `npx tsc --noEmit`、API 1400 pytest、`check_gates` 均通过。
>
> 3A 已有真实验证：项目 `2f875e94-8163-4bb6-9be3-d10203ab0319` 的 Run `6215b2ce-7b4a-4232-9041-1195d9ea1c7f` 交付同一 v13 成片，5 个内部阶段在初次打开与硬刷新后一致，单 Run/Output 无重复；共享查看器视频 `readyState=4`、`duration=8.064`、无播放错误，最终结算 16 credits。首次上传受本地代理/DNS 影响失败，复用已渲染字节重传成功，未重新渲染。该证据证明 3A 垂直链，不替代 3B 的真实 render/delivery 阶段与完整旅程。

### 3B 分批顺序

1. **3B-1 视口稳定薄批**：只改 Web 呈现层。复用现有 MessageScroller，为 WorkSegment/Run 明细的用户开合与既有 live → Worked 收段补视口锚定；当前活动 TurnBlock 只在防止真实收缩弹跳所需时保留已达最大高度。按 §8.6 核对真实活动/可见正文与 `bottomNowRow` 不重复，不新增计时器、动画、消息协议或第二活动状态。
2. **3B-2 真实 render/delivery**：在 `claim_pending_render` / `render_output` 与实际交付准入点补 start/finish/failure 记录，沿用 3A 存储、DTO 与 fencing；render queued、rendering、rendered、delivered 不混用。同批收敛 OPTIONS 确定性作答的 QA 单显（上方 Q/A 卡保留、重复用户气泡抑制、Turn 身份不丢）及旧 render `Uploaded` 摘要的本地化读面；跨 attempt Worked 耗时口径仍归 3B-3。
3. **3B-3 多交付与 detached 统一**：逐 Output Reveal、detached RunCard 消费路径、跨回合交付与完整失败/重试/恢复矩阵。Worked 耗时不得把失败后的用户等待或跨 attempt 间隔冒充连续工作；只有前一批代码审查和针对性验证没有未解决阻断才进入下一批，完整全形态矩阵仍可并行走查。

> **3B-1 当前状态（2026-10-31）：已落码；指定历史视口走查与真实 live Run 的 render/terminal 向上阅读已通过，delivery 后 live → Worked 收段那一拍的几何证据仍欠。** chat 与 Run 的 `WorkSegmentRow` 共用 MessageScroller layout-effect 几何补偿与一次自动吸底抑制；用户开合锚定被点击 header，既有 live → Worked 只锚定收段前已在视口内的真实 assistant/Output 阅读边沿，收段触发条件未改。历史 Worked/Run 明细连续开合被点击 header 未跳动；硬刷新无入场动画重播、无额外尾部空白。未观察到独立收缩弹跳，因此不新增 min-height 或活动 Turn 最大高度机制。
>
> 复用 version 21 的正常 Chat 只启动一次 Run `45f3bc2a-ca9e-42b9-bf58-4900433be958`，未新建 CompositionVersion。真实 render 期间向上阅读后，`scrollTop=21582` 与阅读锚点 `top=471.078125` 在各采样帧保持不变，直至 Run terminal，未重新吸底；显式回底后，后续内容增长时 `scrollTop` 随 `scrollHeight` 增长且 `remaining=0`，恢复跟随。新 Output `22a0d66b-022b-42ef-8b9c-b8cb36bbe809` 在 delivery 后的 history 中仅一张，无入场节点、无新 Chat 或 ACK，尾部 spacer 为 0；本次仅 capture 16 credits，held=0。证据为 `artifacts/chat-turn-block-stage3/live-run-scroll.json`、`live-run-scroll-history.json` 及对应截图。该 Run 的 delivery 在浏览器关闭后才持久化，因此当前证据不覆盖 live → Worked 收段瞬间，不以静态 history 的 Worked 冒充。
>
> **3B-2 当前状态（2026-10-31）：已落码；OPTIONS、旧摘要与真实 render/delivery 主链均已通过。** OPTIONS 确定性 option 作答在真实用户行现有 `intent` JSONB 持久化 `answered_question_id`；live 信封与 history 读同一关联，投影先按真实用户行及其 `turn_id` 归组，再只在匹配 option QA 已处于同一投影时抑制重复用户 Slot，真实消息与后续 assistant 的 Turn 归属不变。旧行回退仅限 `question + answer.kind=option` 后紧邻一条用户持久消息、且内容与选中 option label 逐字一致；空 `answer.text` 只作旧行读容忍，expired、superseded、freeform、普通插话、task_book、bail、非紧邻和不同/空白扩展文本均不命中。直接 answer 端点行为未改。正常固定选项作答 live/history 均只显示 Q/A 卡，后续 assistant 保持原 Turn；旧 QA 与后续回复的归属也通过真实历史走查。旧 render step 仅对 `summary === "Uploaded"` 读 `chat.legacyStepSummaries.uploaded`（en `Uploaded` / zh `已上传`），中文旧行已实测显示“已上传”，不重排其他 summary 优先级。
>
> render mirror step 在 `claim_pending_render` 成功提交后同步 Output 的 `render_claim_token` 并递增 attempt，随后复用 `ProductionStages` 短事务行锁、当前 attempt/token fencing 与同一 DTO 写 start；queued 和无稳定围栏的 mirror 不写 running。`render_output` 在无 spec、renderer/probe异常与 fenced Output 成功提交等真实结果边界 settle：upload-only 恢复只记 upload；renderer 明确返回普通任务 `stage=upload` 时记 render completed + upload failed，不冒充 delivery。成功渲染与探针通过后，只有重新读取 Output 且既有 `output_is_delivered`（render completed + video file 及版本准入）成立才追加 delivery admission；不从 Run terminal 或 Output 存在猜测交付。旧 Run 无阶段字段、Speech 规则、delivery 首显收段与 Output Reveal 均未改；多次 delivery、detached RunCard 和跨 attempt Worked 耗时仍归 3B-3。
>
> 本批自动证据：Web 24 files / 306 tests、`npx tsc --noEmit`、API 1403 pytest、`check_gates` 与 `git diff --check` 全绿；既有 upload-failure/recovery DB 旅程使用 mock renderer，证明 claim start、render/upload 成败、delivery admission、attempt 递增及 typed option 的持久关联，不代表真实渲染或付费旅程通过。
>
> **3B-3 当前状态（2026-10-31）：实现已落码，完整矩阵未闭环。** 两个 QA 边界已修：option + assets/focus 保留完整真实用户气泡与 Turn，纯 option 仍只显示 Q/A；expired/superseded 机器作答不再命中 legacy 回退，空 `answer.text` 仅保留旧行读容忍。detached 与 attached 共用真实 ready/Reveal 门槛，单 Run 制作过程仍只有一个面；detached 不复用第一条 delivery 的显示边沿，保留 exact Output 查看入口。真实 detached Output 已在共享查看器播放，旧 Output 初次加载与硬刷新均只出现一次。
>
> Worked 耗时由真实 step/production-stage 起止区间并集计算，重叠不重复累计，排除区间间隙、失败后用户等待与 REVIEWING 交付言语等待；事实不足返回 `null` 并回退真实标题或操作数，RUNNING → REVIEWING → SETTLED 时点未改。**多次 delivery 已改为消息自有持久关联**：新 trigger 行在 `messages.intent.output_refs` 写入本次实际交付的 exact Output ids；同一 Run 恢复交付扣除此前消息已交付 refs，失败零交付写空数组。live/history 都把 refs 投影到自己的消息对象并在正文后渲染；缺 refs 读为空，不保留 Run 级读容忍。共享查看器与 `@output` 只消费已交付视频 Output 身份，不建注册表、不按时间戳猜关联。
>
> live Storyboard ACK 的阻断已定位并修复：`finalizePreview` 与 `stampEnvelopeBlocks` 的 React deferred updater 曾在 `finally` 释放 turn ownership 后再次检查 ownership，因而丢弃 `streaming=false`、`proseDrainedAtMs` 和 blocks。现改为调度时检查所有权，updater 只按稳定 row id 落定，终态 `turnId` 使用已收编的 turn owner 事实；历史 ACK、exact version/digest、制作授权门和打字机节奏均未放宽。正常 Chat 只读展示 Composition `37733138-8c04-4290-be93-aa41f1dc1446` 的 version 21（`2716649a-2031-44fb-b32f-75ae01f34c13`）后，真实浏览器依次完成 storyboard GET 200、`POST /messages/755b65b7-7b53-46d0-a2de-b1ffcb4653d8/video-presentation` 200；服务端 message block 与 pending receipt 均持久化 `presentation_complete=true`。该回合未新建版本、未启动 Run/render/Output/capture，证据为 `artifacts/chat-turn-block-stage3/ack-fixed-live.json`。
>
> version 21 的真实付费主链已通过。首次 Run `a0191d5f-62e3-499b-bc26-e5aef2dfe140` 在 render 前失败：常驻 worker 尚未加载当前 `TextStyle.letter_spacing` schema；validate/fonts 已完成，无 Output/render/capture。重启 worker 后，同一正常 Chat 制作请求创建 Run `a1d74bf8-ddbe-4400-a748-d95bc3417228`，其 `version_ref` 精确钉住 `2716649a-2031-44fb-b32f-75ae01f34c13` 与既有 content/presentation digest，auto 授权报价 16 credits。validate → fonts（3/3 复用）→ compile_spec → output_preparation → render_queue → render → delivery admission 全部完成，Output `c90c53aa-03aa-496d-9833-1f017afdae1d` 为 `render_status=completed`，交付 trigger 行持久化。共享查看器真实播放 `readyState=4`、`duration=8.064`、播放进度从 4.184s 前进到 5.989s、无错误；硬刷新后 Output 卡仍仅一张，history 不再发送 presentation ACK。钱包从 93,308 变为 93,292 credits、held=0，唯一本次 capture 为该 Run 的 16 credits；失败的前次 Run 无 capture。证据为 `artifacts/chat-turn-block-stage3/ack-fixed-production-retry.json`、`ack-fixed-playback.json` 及对应截图。
>
> 本次完整自动门：Web 25 files / 333 tests、`npx tsc --noEmit`、API 1440 pytest、`check_gates` 全绿；未改 Prompt，未运行 prompt_gate。连续真实 Run `77ea2f4a-6177-4df0-aad4-45715270d394` / `f90f6d0e-4956-42c5-91b8-27775a518755` 分别交付 Output `ee519430-403c-4448-a9db-2c468e7a23ca` / `ff1bce2a-ec1d-44b2-bceb-c085e9815c33`，数据库消息 `3463a3ab…` / `100dfcdf…` 各只保存自己的一个 ref；旧卡位置不变，新卡只在新消息，共享查看器从第 8 项翻到第 7 项。两次硬刷新均每卡一张、零入场重播、零尾部 spacer，浏览器无错误；每 Run capture 16 credits。证据为 `artifacts/chat-turn-block-stage3/per-delivery-live*`、`per-delivery-history-*`。另一次 Run `c4c581e5-b714-4af1-ad15-9011e3576cdb` 的向上阅读锚点在 Output 揭示时保持稳定，但脚本把旧 delivery 文字误判为新交付，停止时新 Run 仍在 Gathering results，故不计 live → Worked 几何证据。阶段三实现已完成；delivery 后 live → Worked 几何、完整失败/恢复与全形态矩阵仍欠，阶段四未开工。

### 开工门槛

3B-1 不需要 migration、API 变更或付费执行；历史走查复用现有持久消息与 Run，live 验证不得伪造成已运行。进入 3B-2 前仍须阶段二代码审查无未解决阻断、API pytest 通过，且多段正文/WorkSegment、Storyboard 首稿、Output 真实揭示、停止/取消与硬刷新至少有针对性浏览器证据。full/panel/mobile、双主题、键盘和 reduced-motion 的剩余走查可与本阶段并行，但必须保留在最终矩阵；detached RunCard 的统一 Reveal 归 3B-3，过渡字段与 legacy 清理归阶段四。

### 范围

1. `RunBlock` 按 `runId` 持有制作身份，`RunTaskList` 成为其步骤适配器；attached/detached 历史形态仍共享同一事实，一个 Run 永不出现两个渲染面。
2. 将 Run 的阶段、耗时、RUNNING → REVIEWING → SETTLED、真实交付收口和 Output 准入纳入 RunBlock，不把异步 Run 强塞进发起 Turn 的生命周期。
3. 在 `produce_video` 现有函数调用边界发射真实内部阶段：版本/素材准备、实际发生的生成媒体、实际发生的旁白、规格编译、渲染与交付检查。每个阶段绑定 run/step/attempt、稳定身份、状态和起止事实。
4. 内部阶段复用既有 Run/step 存储与推送机制及短事务/fencing；不为展示拆 Graph、不新增通用事件总线、不把 Scene/Track/Clip 变成执行节点。`set_stage` 只表示当前态，不能冒充可回放历史。
5. 缓存命中、未启用旁白、失败、重试、恢复和旧 attempt 按事实呈现；可复用准备不重复执行或收费，渲染完成不冒充交付完成。
6. 将可替代的 Run 时间戳插入改为明确的持久关联/锚点；不能证明等价前保留现行锚定，不为清理而改乱消息顺序。
7. 同一 Run 多次 delivery 时，后续 Output 不得复用第一条 delivery 的 display edge 提前揭示；各 Output 只随实际交付位置揭示，由最终“多次交付”矩阵验收，不建立 output↔delivery 注册表。

### 出口

- [ ] Prepare/Render 不再是唯一两条粗记录；实际发生的内部阶段在同一 RunBlock 内可展开、可回放，未发生的阶段不出现。
- [ ] WorkSegment/Run 明细开合与 live → Worked 收段不改变正在阅读的行/回答位置；用户向上阅读不被重新吸底，显式回到底部才恢复跟随，历史无额外空白。
- [ ] 真实活动或可见正文已承担活动证据时不重复显示泛化 `bottomNowRow`；收段仍只由既有实际首显/drain 或真实终态触发。
- [ ] 同一 Run 的 live、终态、交付和硬刷新共享一个实例与正确锚点；跨回合交付不串 Turn、不重复订阅或重复卡片。
- [ ] 失败/重试/恢复不重复计费、不让旧 attempt 覆盖新状态；partial/failed/delivered 仍由服务端裁决。
- [ ] API 定向测试、web 纯套件、tsc 与至少一条真实 Chat → 制作 → 交付 → 刷新旅程通过；付费验证只在明确授权与预算内执行。

### 3C 阶段四前阻断修复（A–E）

> Status: 当前修复上半批已落码；API 1447 pytest、Web 337 tests、Web tsc、check_gates、prompt_gate 均已通过。A/D/E 的既有实现边界不变；B/C 已改为下述 `interim_prose`、逐 delta partial 与客户端实际可见 Stop 协议。无可见回复不再保留 retracted tombstone，而是同事务删除整个 Turn。真实首条上传、Stop 两态、Stop/final-commit 竞态、活跃 Run 取消、刷新与 successor Turn 主链仍待真实浏览器验收；本批未发起付费 Run/render，未执行 DB reset。

#### A. 首页素材与首条用户消息

1. `useProjectLaunch.ts` 收集每个 `assets/from-staging` 返回的真实 `ProjectAsset`，与原始 staged item 配对生成首条 `ChatAttachment[]`；router state、`projects.$id.index.tsx` 与 `ChatDock` 使用同一个 first-message handoff 类型，不再只传 text/mentions/persona。
2. 首次 `sendChat` 将真实 asset id、名称、类型、可播放 URL、大小与 uploaded 状态写入既有 `Message.attachments`；乐观用户行立即用同一附件组渲染 `UserBubble`。附件映射抽成纯函数，live 与 `timeline/history.ts` 共用形状。
3. 复用已上传字节和已建 Asset，不重复上传、不再次 from-staging、不新增用户消息表或第二套 UserBlock 领域模型。空回复/无可见内容 Stop 缩回时恢复正文、mentions 与既有附件 chips，不制造重复 chip/Asset。
4. 验收：首条用户消息 live 即见正文与附件，数据库 `attachments` 非空且 id 正确，硬刷新同形同序，项目只有一份 Asset。

#### B. interim_prose / partial 正文持久化

1. 中段言语唯一名称为 `interim_prose`：SSE `assistant.interim_prose`、DB `intent.type='interim_prose'`、服务端 `on_interim_prose` 与客户端 `onInterimProse` 同义；不留 `assistant.checkpoint`、`onCheckpoint` 或 `intent.type='checkpoint'` 别名/读容忍。方向检查点的领域 checkpoint 不属于本次改名。
2. `chat/service.py` 的 interim prose 与 Activity 一样走独立短事务，先持久化消息行和 `seq`，再发携带 `message_id`、`seq`、`turn_id` 的 SSE。禁止在主 Turn session 中途 commit 未完成的计划、制作或授权写。
3. Chat 每个已接受 delta 先追加当前 Turn 的服务端 trailing `partial` 行，再发携带同一 `message_id` 的 delta；interim prose 取代旧 partial，后续 delta 开新行，成功 final commit 删除 trailing partial。answer 流 continuation 不套用普通 prompt Stop frontier。被拒绝迭代、reasoning、Thinking、keepalive 和空 delta 永不落正文。
4. 所有独立 transcript 写口与最终 commit 通过开局用户行锁拒绝 Stop 后迟到写。失败时保留已经独立提交的诚实 transcript；主动 Stop 则只保留控制口记录的可见 frontier，不按 emitted/received 推断。

#### C. Chat Stop：以实际可见边界保留或撤回

1. 主动 Stop 与意外断线分开。`prepare_chat_turn` 提交用户行后由 `_turn_stream` 发 `turn.started`，ChatDock 收编真实 `turn_id` 并保存本次 text/mentions/attachments 快照；OPTIONS answer 流继续原 answer abort/settlement，不进入普通 Turn Stop。
2. `POST /api/v1/chat/turns/{turn_id}/stop` 接收 `prose[{message_id,visible_chars}]`、`activity_ids`、`structure_ids`。`visible_chars` 只表示打字机已经释放的 Unicode code point 前缀；DB committed、SSE emitted 或浏览器 received 但仍在缓冲区都不算看见。structure id 只由真实开放渲染路径在 DOM commit 后注册到同步 ref：RevealSlot 必须满足 `ready && priorDrained`，Candidate 由自身可见卡片注册；hidden/loading/未 drain/历史水合与仅凭 `blocks`/`candidates` 字段存在都不得登记。服务端只接受本 Turn 已有行 id 并按自己的 content clamp，客户端不能上传正文。
3. 控制口在开局用户行锁内原子记录决定与 frontier：零可见正文/Activity/结构时删除整个 Turn 并返回 `retracted`；有部分可见内容时裁掉未显示行与尾部、取消可见 active Activity、写 `turn_state='cancelled'` 并返回该状态。disconnect 只做幂等清理，不能再把 cancelled 改写成 retracted 或反向恢复。
4. 客户端只在收到 `cancelled` / `retracted` 后 abort。Stop 路径 `halt/discard` 未显示缓冲，绝不 drain；SSE quiet close 若先于控制响应到达，先等待本次 Stop Promise，再选择 Stop halt 或普通 drain/failure，两个先后序都只投影一次。`stopPending` 由当前 Turn context 持有，旧 stream finally 与迟到控制响应只在 owner 匹配时清理，不得卡死或误清 successor。retracted 删除本地整 Turn、恢复 draft/mentions/既有 staged chips 并清除首条 router handoff，刷新不得自动重发，cancelled 只保留同一 frontier。既有 owner guard 阻止旧 SSE 修改 successor Turn。
5. final commit 与 Stop 共用同一行锁，所有该处锁读必须 `populate_existing`，防止等待锁之前的 identity-map 旧值覆盖竞态事实。nested Start 在锁 pending question 前先取 opening-row fence，锁序与 Stop 的 opening → transcript 一致；answer/Run/hold 只 flush，由 outer final fence 唯一 commit，worker 在该 commit 前不可见。主 Turn 已持有该 fence 时，同一 async Turn 的独立 transcript Session 共享其锁所有权、不得跨 Session 再等待同一把锁；Stop 等其他请求上下文仍正常加锁，outer execute 在提交、回滚或异常退出时清除共享标记。直接 answer 与 presentation-ACK auto-Start 保持自己的 commit。Stop 先赢则 assistant/Run/hold 所在最终事务回滚，不留新 Run、hold、capture；final commit 先赢则 Stop 返回真实终态且不 abort。既有授权、计费守卫、exact version/digest 不变。nested Start 的 Activity 独立写入已有真实 Postgres 定向覆盖，本次修复后的测试与真实浏览器复验未运行。

#### D. Run 活跃时 Send=Stop 与真实取消

1. 新增 `POST /api/v1/runs/{run_id}/cancel`。`WorkflowStatus` 与 `RenderStatus` 增加 `CANCELLED`，提交匹配 enum migration，并同步 API DTO、Run SSE terminal 集、Web status/terminal 投影。
2. 取消事务校验归属并锁 Run：active Run → CANCELLED；pending/running/waiting steps → cancelled；清 `claim_token`；pending/rendering Output → CANCELLED 并撤 render claim。已完成 Output、既有 delivery 与已发生 capture 不动；释放未消费 hold，项目按真实可交付结果回 REVIEW 或 DRAFT。
3. `jobs.py` 的 node/render 认领排除 cancelled；`orchestrator.py` / `rendering.py` 继续以 fencing 丢弃迟到写。取消后不得认领后续步骤、产生新 capture/delivery/trigger 或由旧 attempt 覆盖状态；worker 在既有执行边界响应，不伪称跨进程强杀外部调用。
4. CANCELLED 是 terminal，不触发 `run_completed` / `run_failed` 收官言语； cancelled Run 行按现行取消律退役，不显示绿色 Worked、红色失败或删除线。
5. `ChatDock` 的 `canStop` 同时覆盖当前可 abort assistant turn 与当前 attached active Run。Run 已出生时 Stop 取消 Run 并结束关联 assistant stream，尚未出生 Run 时走 C 的 Chat Stop。Run 中输入只保留草稿，不插话、不排队、不自动发送；取消请求防重复点击，失败不得假装停止，真实 terminal 后恢复 Send。

#### E. Output 用户层与草稿修订号分家

1. 用户层只有一个当前草稿与多次生产 Output。`OutputDeliveryCard`、`ChatOutputViewer`、ChatDock Output candidates/chips/hints 与 `lib/mentions.ts` 不再展示 `composition_version_number`，也不新造按时间或邻接位置编号的“产出 v1/v2”。
2. 名称继续读真实 Output 的作品名/hook/类型/语言/时长等既有事实；查看器可显示真实创建时间。同名 Output 不强行编号，`@output` 和查看器仍钉 exact Output ID。
3. `CompositionVersion`、exact `composition_version_id`、content/presentation digest、不可变生产快照与 pinned execution version 全部保留；本项不是版本存储删除或读取门放宽。无消费者的版本后缀 helper 同批删除。

#### 施工顺序与出口

- 按 A → B → C → D → E 小批实施，优先复用现有座位做最小修补；C/D 不得先上半截按钮再补后端。实现者只做改动面的快速自检与必要的就近纯测试，不新建大型测试矩阵、取证框架或脚本群；全量仪式链、复杂浏览器/恢复/几何与形态矩阵由用户执行。
- 本批为验证 A–E 所需的真实付费 LLM/Run/render 制作已获用户授权，无需逐次再问；复用现有项目与最低成本真实路径，记录 Run/Output/费用与失败，不为凑矩阵重复制作。
- A–E 代码与快速自检完成后即交用户做复杂验收；未运行项如实列出，不以代码审查冒充通过。A–E 验收后才进入 §5。

## 5. 阶段四——同源回放与旧路径退役

> Status: 当前代码只有一个 RunBlock 工作面，Output 正常只挂在所属 delivery 消息上。同 Run 恢复重读当前 attempt，旧 delivery 不 seal 新 attempt；第二次 delivery 留在自己的消息位置。零 delivery 的当前 Run 在 live 有界 review 落定或历史水合后可展示自己的真实 delivered 视频，迟到 delivery 接管后不留双卡；已有 delivery 缺 refs 仍为空。pending/answered QA echo 保留自己的 refs，历史不由 live-only suggestions 推导 reviewing。初始慢历史按真实 server id alias 合并，保留本地 birth key 与 typing。`LegacyRunOutputs`、通用 Run 级 Output Reveal、`showOutputs` / `anchorOutputs` 和旧无 `output_refs` 消息归属回退不恢复。上述上下半批改动已通过当前完整 API 1447 pytest、Web 352 tests、Web tsc 与 check_gates；真实记录回放与浏览器旅程仍需用户验收。

### 范围

1. live 与 history 正式共用 `timeline → blocks` 投影；历史只水合当前状态，不重演动画，不另建本地 Block 真相。
2. 将历史适配器收敛为旧行形状 → 统一类型的读容忍层；Candidate、QA、trigger、material beat、failure 等分支按实际消费者逐案保留，不以“简化”为名删除有效历史能力。
3. 删除已被 TurnBlock/RevealCoordinator 吸收的顶层碎片拼接、重复活动座位、重复揭示判断和旧正式渲染路径；被替代代码同批删除，不留长期双轨或注释尸体。
4. 核对 VIDEO_PROJECT §12、MODULE_ARCHITECTURE、CHAT_ARCHITECTURE 与当前文档；目标目录一旦成为现状，更新代码地图并移除本任务已完成范围，只保留未验证项与后续欠账。
5. 回合/恢复状态只在真实 Block 边界已经稳定、且提取能降低耦合时迁入对应 hooks；若只是改变复杂度的地址，则保留当前编排座位，不为目录完整度强制收口。
6. 收敛阶段二/三的过渡字段与分支：平坦 `OverlayMessage` 上仅为分组累加的 `turnId` / `independentKind` / `hydrated` 等元数据，在 Block/Slot 判别联合能直接表达后移除重复表示；不得把旧平坦行永久包一层就宣称完成 TurnBlock。`birthKey ?? id`、持久 `seq`、旧 `turn_id=NULL` 读容忍与历史直水合语义继续保留。
7. 阶段四只保留一个 RunBlock 正式渲染面；attached 与 detached 可以是两个数据适配器，不得再各养一套 Worked/Output renderer。统一顺序为 Run 工作段/Worked → 实际 delivery 正文 → 该 delivery 自己的视频 Outputs，Run anchor 读真实 run/message 关联，不再用 `lastStepT` 或 delivery 邻接猜位置。每条消息只读自己的 `output_refs`，缺字段读为空；时间戳和邻接消息不提供 Chat 归属。只有当前 Run 完全零 delivery 时，才允许 §8.7 的有界 RunBlock 视频可读兜底；它不修改消息 refs，任何 delivery 出现即关闭。`LegacyRunOutputs`、`showOutputs`、`anchorOutputs` 与通用 Run 集合不留兼容实现。
8. 逐案审计 legacy 读容忍：有真实旧数据或合法消费者的 QA、Candidate、trigger、material、旧分镜等继续读；无真实数据、无新写口且无消费者的形状凭证据删除。新代码不得再写 legacy 形状，也不为旧测试锁定而保留实现细节。
9. 校准历史投影守卫：测试禁止从历史行存在性推导 planReady、确认或 canvas readiness，但不得以无诊断的字段白名单锁死合法身份/水合/块归属演进。新增或删除投影字段时，同批审计相关白名单与 shape guards；断言必须直接列出非法字段，不逐键盲猜，也不为放行回归删除承重断言。
10. 普通工作段与 Run 工作段统一由 `WorkSegmentRow` 拥有头部、Worked/耗时、disclosure、开合锚定与成败规则；chat activity categories 和 Run steps 只保留 details 适配差异。Run 不再自养绿色勾、独立父级标题收据或第二套 settled 样式，内部 production stages 归并到所属步骤，不铺成第二棵执行树；“交付准入”等内部词改为用户可理解的实际检查/交付文案。

### 出口

- [ ] 同一 fixtures/真实记录驱动 live 与硬刷新，内容、块归属、顺序、状态和组件一致；历史无 typewriter/stagger 重播。
- [ ] 旧无 `turn_id` 行、当前行和异步 Run 均可读；回退不伪造关系，刷新不重启执行、不重新 ACK、不重复交付。
- [ ] 旧正式时间线已退出，无第二进度真相、无重复 Run 面、无仅因本次重构保留的实现形态锁。
- [ ] 过渡元数据与 Output/Reveal 双路径已收敛；保留的 legacy 分支均有真实数据或消费者证据，新写口不再产生 legacy 形状。
- [ ] 历史防漂移测试锁定生命周期不推导等架构不变量，非法字段可诊断，不以脆性形状锁阻碍合法演进。
- [ ] 完成下方全旅程矩阵及适用部署前仪式链；未运行项明确保留，不用代码审查冒充真实验收。

## 6. 最终真实旅程矩阵

| 旅程 | 必须证明 |
|---|---|
| 多工具 + 多段正文 | 活动原位入段、Worked 与正文交替、同 TurnBlock 不拆散、无 remount/瞬移 |
| 工作段开合与收段 | 被点击行及最终回答的视口位置稳定；向上阅读不被吸底，活动 Turn 收缩不弹跳，历史无空白 |
| 分镜首稿与后续修订 | 完整呈现与 ACK 先于授权制作； pending/accepted/rejected 刷新一致；普通修订不伪造 Output |
| 后台制作 | 内部阶段真实、跨回合身份稳定、一个 Run 一个面、交付首显才收段 |
| Run 中停止与多次交付 | 块归属和锚点正确，每次 delivery 只展示自己的视频 refs；同 Run retry_upload 重订阅并恢复 Send=Stop，旧 attempt 事件不污染新 attempt，旧 delivery 不 seal 新 attempt；查看器 exact output 不串项，非视频不进 Chat 卡片/查看器/`@output` |
| Chat Stop 可见边界 | 仅 Thinking、已入库但未显示 interim/partial 均 retracted 且刷新无复活；部分已释放正文只保留 Unicode 前缀与可见事实，未显示尾部不补播；draft/mentions/既有附件 chips 正确恢复 |
| Stop 竞态与 successor | Stop 后迟到 interim/partial/Activity/final commit 被拒；Stop 赢 final commit 时无新 Run/hold/capture；旧 SSE 不污染 successor，OPTIONS answer 不缩成普通 prompt |
| 失败/停止/重试/恢复 | 无虚假完成与未接受组件；同 Run 第一次失败 delivery 后 retry_upload 恢复 active，第二次成功 delivery 正常入流，旧 attempt 不覆盖新尝试；费用与授权语义不变 |
| 零 delivery 视频 | live terminal 不提前出卡，有界 review 落定后只展示真实 delivered 视频；cancelled/partial/trigger 永久静默分支可读，历史不重新 reviewing，迟到 delivery 接管且无双卡或空卡 |
| 历史与旧数据 | seq 不乱、旧行读容忍、无动画重播、无相邻位置猜关系；pending/answered QA refs 保留，初始慢历史与普通发送只留一条 user/assistant 且 birth key 不变 |
| OPTIONS QA 作答 | 确定性选项作答只显示上方 Q/A 卡，不显示重复用户气泡；真实用户行仍承担 Turn，直接 answer、freeform、普通消息与刷新行为均正确 |
| 全形态可访问性 | full/panel/mobile、双主题、键盘/focus、reduced-motion 均可用；Action 不只依赖 hover |

## 7. 验证纪律与不做清单

- 每阶段先跑改动面的纯测试与 tsc；涉及 API 时跑对应 pytest 与 `check_gates`。最终按改动面执行部署前仪式链；上半批已触及 `app/prompts/chat/_read_tools.j2` 的称谓，部署前仍按既有要求核验 `prompt_gate`。**下半批未触及 prompt 面，不需要新增 prompt_gate 探针或阈值调整。**
- 真实浏览器验收使用正常 Chat 与持久数据，不用组件故事、静态截图或客户端计时器冒充执行事实。测试归属遵循 ADR-114：保留主流程旅程与承重防漂移守卫，不新立文件形状锁。
- 禁直接安装/替换整套参考 Chat 或滚动库；禁复制参考项目的 reasoning 展示、模型货架、通用版本树、Sources rail 或与当前需求无关的 chrome。
- 禁为视口稳定新增固定延时、自动展开动画、第二 scrollport 或通用 UI 事件总线；禁为消除状态重复而隐藏真实 review、失败或交付事实。
- 禁把“渐进揭示”做成虚假数据生成；禁让所有组件共用一个巨型状态枚举吞并 QA、授权、Run 和打字机的正交状态。
- 禁为目录整齐一次移动全部文件、禁在机械拆分提交中夹带行为变更、禁以文件行数代替职责边界验收。
