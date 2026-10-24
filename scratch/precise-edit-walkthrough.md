# Precise Edit——当前证据与人工验收

> Status: 当前验收合同。既有 live 证据截至 2026-09-25，不能代表当前 HEAD 已复验；后续验收覆盖本文件状态，不追加逐轮日志。行为规范唯一归 `docs/VIDEO_EDITOR.md` §11、ADR-090/091/092 与 `docs/tasks/verification-contracts.md`。

## 1. 当前行为与实现座位

- Chat 精确编辑由 `apps/api/app/chat/propose_turn.py` 承接；四个用户请求族是 `remove_range` / `set_trim` / `set_caption_style` / `set_title`。自然语言 craft 修订走 `revise_output`，不与机械 edit 混用。
- 回合恰一个 `@output` 时，`pinned_output_id` 在服务端强制 target = pin，覆盖或补全模型转述；零个或多个 pin 按当前工具规则解算，绝不靠列表位置猜测。
- `app/operations/service.py` 与 `app/operations/routes.py` 持有 operations、undo 与失败拒绝；`app/pipeline/outputs.py` 及 outputs 路由持有 archived 写门与 restore。精确编辑在 Version 内原地写 operation + journal，不创建新 Version。
- rerun/regeneration 才产生新 Version 并继承 `work_id`。归档历史可读、可 restore、其余写门 409；同 Work 至多一个 active。edit→render 当前定价为 $0，不因此绕过其他付费 run 的授权规则。

## 2. 既有证据的可用范围

已有真实链路证据覆盖：

- 四族及 quote→range 边界：跨 cue、大小写/标点归一化、未命中、多义拒绝；实际区间、3 秒 trim、合法 caption preset 与标题均与 journal/重渲染一致。
- 唯一 pin 的普通命中，以及 pin 写门上线后的四族旅程；undo 后 `undone_at` 与 journal 可溯。
- 真 rerun/wipe 后旧 Version 归档、`work_id` 继承、旧行按 id 可读、默认 results 只显示新 active；operations / undo / PUT / regenerate 对归档行均 409。

这些证据**不覆盖**：

1. **pin 与模型自然分歧**：写门上线后的 live 回合都恰好命中 pin；“模型想改 B、用户钉 A，服务端仍必须改 A”的强制覆盖目前只有纯件证据。需自然分歧 live，或由当前合同明确只接受纯件层级。
2. 当前 HEAD 的完整四族 + rerun/archive/restore 旅程、当前注册矩阵和适用 prompt_gate。旧探针数、旧剧本名与旧全绿计数都不是当前证据。
3. 当前两键设置 `confirm_execution` / `confirm_credits` 的持久化与披露行为。旧 `confirm_strategy` round-trip 曾验证过，但键与授权合同已变化，不能转信；composer/dock 也不再有确认偏好控件。

历史观察中的间歇 render 失败、run 长时间未收官与一次 `/chat` 500 均未形成可复现的当前缺陷结论。只有在新证据中重现时才晋升，并保留当次日志、run/output id 与加载版本；不得把旧异常写成现行 bug，也不得写成已修复。

## 3. 当前人工复验

按 `docs/VIDEO_EDITOR.md` §11.2～§11.3 执行完整矩阵，使用真实素材和至少两条已交付 clip。除四族普通路径外，必须单独记录：

1. **自然 pin 分歧**：保留用户 pin、模型原 target、最终 op target 与产物 id；最终 op 必须等于 pin，未钉产物零 mutation。
2. **归档全写面**：archived 行 operations / undo / PUT / regenerate 全 409；restore 后旧行可写、原 active 自动归档，results 仍至多一个 active。
3. **身份与血统**：rerun 前后 `work_id`、Version id、journal、publication 锚与 `output_refs` 均可读，无死 id。
4. **当前设置**：在 SettingsDialog「助手」分别切换 `confirm_execution` / `confirm_credits` 的 auto/ask，刷新与换会话后读回一致；再按当前授权矩阵验证普通 auto、ask、无制作意图、守卫线与 NULL 不可报价族。不得恢复 composer/dock 偏好控件。
5. **证据包**：记录当前代码 SHA、API/worker/render 实际加载版本、真实项目/run/output id 与每拍结果。未运行的 LLM、浏览器、渲染或付费项明确写“未运行”。

任何静默改错产物、模型覆盖 pin、区间/秒数编造、归档写成功、restore 双 active、journal 丢失或未经授权 hold/capture 都是红灯。

## 4. 验证归属

- 纯函数与静态合同：`docs/tasks/verification-contracts.md` 的“精确编辑四族与归档恢复”行。
- 活 API / dev worker / 真实模型：当前注册旅程矩阵及本文件人工拍位；不恢复 S-edit、S4/S5/S16/S19 等退役名称。
- prompt 面若变化：按根 `CLAUDE.md` 的 prompt_gate 失败协议执行；402/连接错误是 INVALID，不算行为读数，也永不为放行调阈。
