# OpenFilm 怎样问问题、校验参数和结束一轮

下载目录中的 OpenFilm 桌面版为 0.2.7。对同一个请求“给这个网站做一支宣传片”，OpenFilm 自带的 Pi 代理可以直接调研、规划并着手做片。是否需要问用户，由代理按选错的代价判断。Rookie Cut 的这次请求进入了专门的官网宣传片流程，服务端要求用一张表收齐五项设置。两者对缺信息、坏参数、表单发送失败的处理各不相同。

| 遇到的情况 | OpenFilm 桌面自带 Pi | Rookie Cut 这次实际运行 |
| --- | --- | --- |
| 已知网站，没指定片长和画幅 | 提示词允许自行选择并说明。代价高或方向差异大时再问 | 品牌分析完成，服务端给出五个待选字段，要求调用 `ask_user` |
| 模型漏写题目 | SDK 在执行前返回错误路径和收到的参数。下一次模型调用能看到错误 | 第 02 轮有 7 个校验错误，第一项为 `items.0.question` 缺失 |
| 纠错轮只发工具调用 | 工具循环从消息中取工具调用，对 `ask` 没有附言要求 | 第 03、07 轮的参数离线通过了参数和业务两层校验，线上因正文为空而提前拦截 |
| 参数正确，等待用户 | 工具挂起。用户选项或自由输入作为同一次调用的结果返回 | 先把合法问题写入对话，挂出待答卡片。这次未走到该步骤 |
| 表单发送失败 | Pi 适配器把发送异常映射为取消，把它和跳过转成相同的英文工具结果 | 失败写入下一轮上下文。第 10 轮调用普通 `answer` 正常结束，制作任务数为 0 |
| 助手说要开工就结束 | 提示词要求实际制作并看帧。在查到的 Pi 本轮结束路径中，没有强制检查作品文件或看帧回执 | `answer` 可保存非空正文并结束。该工具不会启动制作 |

## 1. 基础提示词如何组装

**自带 Pi。** `ownAgentPrompt()` 先读取 `apps/desktop/src/agent-prompt.md` 并去掉首尾空白，接上 `## Pointing at Studio` 和 `STUDIO_REFERENCES`，最后把 `packages/openfilm/MANUAL.md` 放进 `<manual>` 标签。手册里的 `npx openfilm` 在这一步统一改成 `openfilm`。随报告提供按这段代码从下载目录重建的基础全文。它还不包含某个具体项目或会话动态带入的内容。[组装代码](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:158) · [角色与工作方式](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agent-prompt.md) · [制作手册](/Users/sylas/Downloads/openfilm-main/packages/openfilm/MANUAL.md) · [组装后的基础全文](openfilm/pi-base-system.txt)

**项目和用户消息。** Pi 使用这份基础系统指令，项目说明文件只保留项目根目录的，技能也受应用配置限制。桌面聊天把用户输入、Studio 里引用的画面或时间点、用户此前在 Studio 保留下来的改动说明、这次点名且该代理会话尚未收到的技能正文依次拼接。引用截图和附件图片作为图片块另传。没有引用、改动说明或选中技能时，这些段不添加。工具通过独立的工具定义传入。自带代理启用 `read`、`bash`、`edit`、`write`、`ask`。[会话配置](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:131) · [消息拼装顺序](/Users/sylas/Downloads/openfilm-main/apps/desktop/chat/src/App.tsx:773) · [ACP 消息转为 Pi 输入](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:285)

**外接代理。** Claude Code 会收到追加到系统消息的简短 `INSTRUCTIONS`。Codex 通过 `developer_instructions` 注入，合并时把已有的个人指令放在前面。其余采用首条消息注入的适配器会在首次发送时加一个文本块，之后清空。外接代理被要求自行读取手册，因此它们的完整模型上下文随代理而异。[外接代理说明](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:139) · [Codex 注入](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:1229) · [Claude 注入](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:1291) · [首条消息注入](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:1357)

## 2. 模型在什么情况下应当提问

提示词先让代理从项目文件和网页了解产品，再逐镜规划、动手做并用 `openfilm look` 检查。提问段的原文是 “Most requests are enough to start: make sensible choices yourself and say what you chose.” 它把提问留给选错会浪费时间或金钱的决定，例如方向明显不同或需要额外付费生成。按这份指令推断，面对同一网址，它可能直接选片长和画幅，也可能只问一个有实质影响的问题。这个下载目录里没有该网址在 OpenFilm 中的真实模型往返，无法据此指定它一定会选哪条路。[提问原文](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agent-prompt.md:30)

## 3. 填错参数、正常回答、发送失败分别怎么走

1. **给模型的工具契约。** `ask.questions` 有 1 至 3 道题。每题要求字符串 `question` 和 2 至 5 个 `options`，每个选项要求 `label`，可加 `description`。题目可带 `header`、`multiSelect`。问画幅和问时长用相同的选项结构。这里的 schema 没有要求配一段聊天正文。[工具定义](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:232) · [实测时取出的完整 schema](openfilm/offline-check.json)
2. **执行前校验。** OpenFilm 的锁文件指定 Pi 1.1.0。其工具循环先调用 `validateToolArguments`，对参数副本做有限的转换，再按工具 schema 校验。缺必填项会抛出带字段路径和收到参数的错误，循环将其转为 `isError: true` 的工具结果，放回模型上下文。模型可以修参再调，是否能修好取决于后续回复。配置里的网络重试次数是另一回事。[锁定版本](/Users/sylas/Downloads/openfilm-main/pnpm-lock.yaml:480) · [校验函数](openfilm/pi-ai-validation.js) · [错误返回模型的循环](openfilm/pi-agent-core-agent-loop.js)
3. **卡片和回答。** `ask.execute` 用代码为各题生成 `q0`、`q1` 等字段和对应的自由输入字段，再 `await createElicitation(...)`。桌面端检查表单能否展示，有答复后将已知选项或非空输入映射回去。Pi 返回题目和 `Answer: …`，模型随后继续。这里的等待由一个仍未完成的调用实现。[构造并等待表单](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:260) · [卡片映射](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:790) · [桌面等待事件](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/local-agents-ipc.mjs:279)
4. **失败分类有一处会合并。** 不能展示的表单会被桌面端 `decline`。Pi 也会把发送表单抛出的异常转为 `cancel`。两者进入同一分支，给模型的原文均为 “The person skipped the questions: decide yourself and say what you chose.” 因此仅凭这句话无法证明用户看过卡片或主动跳过。另有独立的付费视频片段确认逻辑，用户未确认超时时，该生成会被拦下。[无法展示时的分支](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agents.mjs:1253) · [Pi 的返回文字](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:270) · [付费生成确认](/Users/sylas/Downloads/openfilm-main/packages/openfilm/studio/server/get.mjs:341)

**离线复核。** 我从该目录取出原始 `askTool`、`formQuestions`、`formContent` 函数，用锁文件对应的 Pi 校验器和 TypeBox 1.3.27 做本地调用。SDK 包与锁文件的完整性摘要一致。只替换与桌面通信的客户端，以便分别观察应答、拒绝和发送异常。缺题目的真实校验输出是 `questions.0.question: must have required properties question`。合法调用在给出答案前保持等待，给出“官网”后返回了两行文字“希望在哪播放？”和“Answer: 官网”。这些是工具实测输出；没有请求模型生成一条模拟回答。[离线输入形状、错误文本和工具回执](openfilm/offline-check.json)

## 4. 用户看到“开始制作”时，系统有何凭据

OpenFilm 提示词要求写出项目页面和 `film.html`，然后运行 `openfilm look`，逐镜检查并修改。真正运行该命令时，它会抽帧、以不同顺序重复取帧检查一致性，并检查裁字、切点等问题。Pi 桌面适配器结束聊天时读取模型的停止原因。没有发现它在每次 `end_turn` 前自动执行 `look` 或验证文件已经改动。因此它降低了复杂表单引发故障的机会，仍可能出现只发进度话术就收尾的回复。[制作流程](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/agent-prompt.md:9) · [看帧逻辑](/Users/sylas/Downloads/openfilm-main/packages/openfilm/src/look.mjs:88) · [结束一轮](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:325) · [停止原因映射](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-config.mjs:193)

查某次 OpenFilm 的真实返回，可以看对应项目的 `.film/logs/<turn>.model.jsonl` 和桌面开发者模式的 Turn Log。Pi 会记录模型上下文和答复，用增量格式复用相同前缀。外接代理能记录哪些字段取决于各适配器，查看器会显示已知缺口。[落盘位置](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/chat-store.mjs:44) · [逐次记录](/Users/sylas/Downloads/openfilm-main/apps/desktop/src/pi-agent.mjs:92) · [开发者查看器](/Users/sylas/Downloads/openfilm-main/apps/desktop/chat/src/components/TurnLog.tsx:2)

回到截图，第 03、07 轮的问卷参数已经能通过现有五项设置的业务校验。拦下这两轮的是当前消息必须另附正文的要求。最后一句则由普通回复路径写入，后台没有相应的开工回执。[Rookie Cut 的逐轮证据](RookieCut逐轮记录.md)
