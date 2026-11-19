# LegitEvi 宣传片对话的提示词、模型原文与校验

2026 年 11 月 19 日，用户发出“给 https://www.legitevi.com/en 做一只宣传片”。项目 `07d486a1-0073-465c-98fa-793ca8b1732b`，用户回合 `9526efb6-a3ee-47b9-b4dd-132f7cf9c871`。这一次有 11 次意图路由调用（从 00 编到 10），另有 1 次嵌套的品牌分析调用。模型均为 MiniMax 的 `minimax-m3`。网页采集和品牌分析成功，表单经过六次尝试仍未挂出，最后一次普通回复结束了回合。

## 查原文

| 需要看的材料 | 文件 |
| --- | --- |
| 整个回合实际请求和响应，含时间、模型调用 ID、组装记录和工具定义 | [按回合从原始日志逐行提取的 24 条记录](exchange.jsonl) |
| 每次模型的回复正文和工具参数，保留空正文与缺少正文字段的区别 | [12 次返回的原文](responses.md) |
| 所有调用的顺序、工具集、模板文件与 SHA-256 | [调用索引](index.json) |
| 第一次发问时送到模型的完整请求、实际渲染的系统提示和工具契约 | [请求](calls/02/request.json) · [系统提示全文](calls/02/system.txt) · [ask_user 的完整 schema](ask_user.schema.json) |
| 最后一句对应的模型响应、用原参数离线重跑的校验、数据库核查 | [最后的返回](calls/10/response.json) · [校验结果](local-validation-replay.json) · [项目状态](project-state.json) |

原始 trace 自带本地脱敏与二进制外置规则。截图用本地文件引用、摘要和大小表示。第 00 轮为流式，响应日志保存的是适配器汇总后的返回；其他各轮的返回保留提供方响应结构。每个目录的 `request.json`、`response.json` 按缩进重排 JSON，原 JSONL 行另有保留。[记录器](/Users/sylas/repurposer/apps/api/app/providers/llm/trace.py:1)

## 1. 请求是怎样从文件组装出来的

1. **入口与路由。** `intent_router` 以 plan 模式运行工具循环，用户上下文模板为 `chat/user.j2`，开启 `service_per_call=True`。每次循环按本轮项目状态重新计算视频阶段、可用工具和系统提示。00 轮可用 `prepare_video_materials / answer`，01 轮可用 `analyze_brand / answer`，02 至 10 轮可用 `ask_user / answer`。这些路由请求使用 `tool_choice: auto`。[代理声明](/Users/sylas/repurposer/apps/api/app/chat/intent.py:252) · [按阶段组装](/Users/sylas/repurposer/apps/api/app/chat/prompts.py:218) · [工具筛选](/Users/sylas/repurposer/apps/api/app/chat/turn_tools.py:853)
2. **系统消息。** 首次提问所在的 02 轮，日志列出主模板 `system.j2`，读取规则、Markdown 与剪辑用语、视频阶段规则、待答问题规则四个子模板，以及单次调用规则和语言提示两个补充模板。补充模板由工具循环追加。具体哪些条件分支实际产生文本，可以直接看 `system.txt`。本回合模板快照由日志导出，已逐份按 trace 自带的 SHA-256 对过。[主模板](templates/chat/system.j2) · [视频阶段条件](templates/chat/_video_project.j2) · [连续调用措辞](templates/chat/_tool_service.j2) · [追加补充模板的代码](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:738) · [实际文本](calls/02/system.txt)
3. **消息顺序。** 在第 02 轮，`payload.messages[0]` 是系统消息，`[1]` 是模板生成的 `application_context`（素材、人设、现有 Brief 和执行设置），`[2]` 是 `project_evidence`（更新过的项目事实及 `required_next_action: ask_user`），`[3]` 是用户发来的原句。随后是两组“助手调用／工具结果”。从第 03 轮起又附上失败的调用、工具错误以及一条名为 `tool_feedback` 的纠错消息。第 10 轮累积到 25 条消息。第 02 轮开场上下文还留着“网站采集仍在等待”，同一请求的项目证据和工具结果已经报告采集完成。这是可见的上下文不一致，日志没有证明它引发本次校验错误。[首次提问](calls/02/request.json) · [第一次重试](calls/03/request.json) · [最后一次请求](calls/10/request.json) · [拼装顺序](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:1108)
4. **工具契约。** `ask_user` 独立出现在 `payload.tools`。顶层必填 `question / items / default_path`。每种缺失字段有自己的选项格式。制作方向用 `{use_case, treatment}`，时长用正整数，画幅用枚举字符串，旁白语言用 `{label, value}`，字幕语言的 `value` 用语言数组。制作方向另要求本题的 `question_language`。例如服务端给模型的时长选项可以是 `30`，模型首次返回的是 `{"value":"30"}`。[当时的完整工具定义](ask_user.schema.json) · [按字段构造 schema](/Users/sylas/repurposer/apps/api/app/chat/turn_tools.py:718)
5. **嵌套的品牌分析。** `analyze_brand` 内部另调模型，以 Python 中的品牌证据说明作为系统消息，渲染 `video/brand_profile.j2`，同时提供网站文字和页面图片。采集得到五个视图；这次品牌模型请求的多模态消息里实际附了一个 PNG 块及其 V1 标注。该模型返回的 JSON 正文和外层 `analyze_brand` 工具结果是两份不同记录。[品牌代理](/Users/sylas/repurposer/apps/api/app/tools/video/brand_agent.py:223) · [模板快照](templates/video/brand_profile.j2) · [品牌请求](calls/brand/request.json) · [品牌返回](calls/brand/response.json)

## 2. 从发问到结束，逐轮发生了什么

轮号采用 trace 中从 0 开始的 iteration。03、07 的“离线通过”指将原始参数单独交给当前工作区的 `PlanAskArgs.model_validate`，再用与当时相同的五个缺失字段调用 `website_promo_question_items`。两层均返回五个合法项目。线上在进入这两层前就拒绝了这些调用。[离线结果](local-validation-replay.json)

| 轮号 | 提供方返回 | 系统实际结果 |
| --- | --- | --- |
| 00 | 正文和 `prepare_video_materials` | 网站采集完成。[原文](calls/00/response.json) |
| 01 / brand | 正文和 `analyze_brand`，内部模型返回品牌证据 JSON | 品牌档案写入项目。[外层原文](calls/01/response.json) · [内部原文](calls/brand/response.json) |
| 02 | 品牌总结、邀请用户，再调 `ask_user` | 7 个参数错误。制作方向缺题目；三个时长和三个画幅选项均用只带 `value` 的对象，进入内部 Option 模型后缺 `label`。[原文](calls/02/response.json) · [实际错误](calls/02/feedback.json) |
| 03 | `content: ""`，一个 `ask_user` | 参数已修到能离线通过两层校验。线上因缺正文提前拒绝。[原文](calls/03/response.json) · [实际错误](calls/03/feedback.json) |
| 04、05 | 两次均为 `content: ""` 和一个 `ask_user` | 两次都先命中空正文检查。这两份参数离线也未通过。[04 原文](calls/04/response.json) · [05 原文](calls/05/response.json) |
| 06 | “我把问题卡再发一次，请你在这几个点上定下来，我就能直接开工。”和 `ask_user` | 4 个参数错误。制作方向仍缺题目，三个时长选项仍缺 `label`。[原文](calls/06/response.json) · [实际错误](calls/06/feedback.json) |
| 07 | 响应省略 `content`，一个 `ask_user` | 参数再次离线通过两层。线上仍以缺正文拒绝。[原文](calls/07/response.json) · [实际错误](calls/07/feedback.json) |
| 08 | “看起来问题卡没能正常送达，我直接按最稳妥的默认设定推进……”和 `answer` | 顶层多出 `source / success_criteria / material_state / asked`，四项均为 `extra_forbidden`，此段默认设定没有成为界面最终回复。[全文和参数](calls/08/response.json) · [实际错误](calls/08/feedback.json) |
| 09 | 响应省略 `content`，一个 `answer` | 在参数校验之前被空正文检查拒绝。[原文](calls/09/response.json) · [实际错误](calls/09/feedback.json) |
| 10 | “我把设定记入需求单，随后开始搭建片子。”和 `answer` | 有正文，顶层形状合法。内部 Brief 的两个字段结构错误，按容错策略整份更新被丢弃。普通回复结束了回合。[原文](calls/10/response.json) · [参数重放](local-validation-replay.json) · [最终状态](project-state.json) |

## 3. 为什么已经修好的表单仍没有出现

同一份实际系统提示中既有“工具重试时只修正参数，不要重复邀请”，也有“同一阶段的连续工具调用可以不附正文”。实现确实暂存了首次 `ask_user` 的邀请语。但更早的执行检查读取**当前响应**的 `prose.strip()`，在 `service_per_call` 开启时，一次有多个工具或当前没有正文都会直接拒绝，错误消息共用。03 和 07 各只有一个工具，因此可以确定命中的是缺正文。暂存的邀请语要到后面调用执行器时才被采用。[提示词第 14 行](calls/02/system.txt) · [暂存邀请](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:1229) · [提前拒绝](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:1412) · [传入暂存邀请](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:1721)

通过前置检查后，循环才会调用 Pydantic。前端看到的对象还要经过选项归一化、五项缺失字段覆盖校验、选项值校验和组摘要计算，最后才挂出卡片。所以错误里的“缺 label”反映的是归一化后的内部模型，与提供方看到的“时长应直接给整数”处在不同层。[Pydantic 入口](/Users/sylas/repurposer/apps/api/app/agents/tool_loop.py:1575) · [选项归一化](/Users/sylas/repurposer/apps/api/app/models/schemas.py:499) · [业务层约束](/Users/sylas/repurposer/apps/api/app/chat/readiness.py:511) · [挂出卡片的执行入口](/Users/sylas/repurposer/apps/api/app/chat/plan_turn.py:1370)

## 4. 为什么画面上出现了“记入需求单”

直到第 10 轮，`project_evidence` 中的下一步仍为 `ask_user`，工具列表同时提供 `answer`，选择方式为 `auto`。模型选了 `answer`，其中 `brief.must_include` 和 `brief.avoid` 都是裸数组；Brief 的对应字段要求带 `value` 的槽位对象。当前代码用原始参数重跑得到两项错误。随后 `_drop_bad_brief` 记录 `brief_dropped`，将整份建议更新置为 `None`，外层 `PlanAnswerArgs` 校验照常通过。[当轮请求](calls/10/request.json) · [当轮参数](calls/10/response.json) · [Brief 容错](/Users/sylas/repurposer/apps/api/app/models/schemas.py:973) · [answer 模型](/Users/sylas/repurposer/apps/api/app/models/schemas.py:1726)

`_answer` 写入助手正文，所得结果不带制作任务。数据库核查与此相符：用户回合状态为 `settled`，该回合没有问题卡，项目已存品牌档案，时长、画幅、旁白语言和字幕语言仍为空，制作任务数和作品数均为 0。可以从本次调用确定上述行为；提示词中文化对其他请求的总体影响，需要另做对照评估。[普通回复的执行逻辑](/Users/sylas/repurposer/apps/api/app/chat/plan_turn.py:1654) · [项目状态](project-state.json)
