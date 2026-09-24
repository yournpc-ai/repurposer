# 精确编辑迭代：edit_output 受控刀 / quote→range 解算 / 产物归档不变量 / 计费偏好集成

> Status: **CLOSED（2026-09-24 Final Hardening 收口，代码 + live 验收双绿）**——ADR-090/091/092 同批拍板落档（`4052db4`）；Gate 0/1 证据链 = live 验收六拍 + 修红批 `6b93b24` + Restore×Rerun/计费链取证。施工进度：S0 `1610bac` / S1 `0f2b9fc`（归档两列 + 两 wipe 点 + 读面 + 换态，迁移回滚实证）/ S2 `a8efdf8`（解算器置信谱 19 纯件）/ S3 `47175f7`（edit_output + 顺形律 kind 推断，探针 H 11/12）/ S4 `b7ef524`（settings API + dock 披露分级，web tsc/vitest 绿）/ S5 `6171085`（S-edit 剧本首跑 PASS + 走查脚本）/ S6 docs 收口（本批）。**欠账**：~~prompt_gate 全量干净读数~~ **已销（2026-09-24：八探针全 PASS**——A 12 / B 12 / C 12 / D 11 / E 11 / F 9 / G 12 / H 11；期间 F/H 红为 402 污染，gate INVALID 化加固 `37c1536`）；live 走查 **已收口（2026-09-24 Final Hardening，Claude 代跑经用户授权）**：B1 `9ddf3ec`（apply_edit_ops 全退役 + kind 参数解码 + 写门纵深）/ B2 `f9f32de`（归档不可变 409 六门）/ B4 `35e572e`（pin 钉恒胜）/ billing 持久化修红 `4a3059d`；prompt_gate 10/11（F = provider 漂移实证）+ 体感四族/解算边界/undo/真 wipe 归档/409 全绿（验收记录 = `scratch/precise-edit-walkthrough.md`）；P1 出批 = operations 用户级 undo/restore UI + set_caption_visibility（PROGRESS 需求池在册）。
> 母合同 = ADR-090（edit_output + 解算器）+ ADR-091（work/version + 归档不变量）+ ADR-092（计费偏好集成）+ ADR-089 §1/§5（终态词表 / 停顿定律）+ ADR-074②（渲染台账律）+ PROGRESS §0.4 规则 9（认知验收）。取证底座 = 年底审计（最大公约数量尺：架构冻结，精确编辑 = 唯一缺口）。

## 1. 主线与冻结条（施工硬约束）

**主线**：把「产物已经在手上，用户要改它」从**绕行整条重生成**升格为**精确、可回滚、身份存活**的第一类编辑——用户说「把开头那句删掉 / 第二条再短 3 秒 / 字幕换 karaoke / 标题改成 X」，agent 落到具体 op，历史可溯，重跑不再销毁交付物。

**冻结条**（逐条即施工禁令）：

1. **受控词表律**：LLM 只见 `edit_output(target, kind, params)` 一个终态工具 + enum kinds——**21 个原始 ops 永不进 LLM 词表**（ADR-089 P0-③ 同款代偿禁复发）；`set_caption_visibility` 延后 P1，MVP 四件之外一律域拒绝。
2. **LLM 永不写执行事实**：时间戳 / UUID / op 参数内部形状零出现——range 只收 quote 文本，解算归代码；指认只骑 @output pin / plan_ref 序位（R20 既有双通道）。
3. **归档不变量**：交付后的产物历史不可销毁，只可归档——三处 wipe 点（select_clips wipe / derivative sweep / verify 回退）中**前两处改归档写**；verify 回退保持物理删除（ADR-091 §3 例外：生产中途未交付，无历史权）。既有死 id 旧数据永不迁移、永不修复（读面读容忍）。
4. **写门零新增**：edit ops 经既有 operations 机制落账（base_hash/409 / snapshot undo/redo 一字不改）；图写经 `apply_wiring_ops` 唯一口；重渲染出生复用 morph re-pend 同族座位 + **镜像步骤同步补登**（ADR-074② 台账律——修红批刚为 verify 回退补过的同一法律，任何新渲染出生地同律适用，新认领源登记 MODULE_ARCH §7.2）。
5. **停顿定律不破**：确认闸复用 plan dock 唯一座位，形态 = **披露强度分级 + CTA 显价**，零新增手势、零新增 dock 类型（「确认失效 → 再弹一次确认」形态明令禁止，iter-3 冻结条 2 同律）。
6. **语义层分工判据**：精确请求（可机械执行的变更）→ edit_output；开放意图（需重买内容判断）→ revise_output；判不准 = 域拒绝回环，永不猜。plan 级变更仍归 revise_plan。
7. **计费机制零新增**：MVP 四件零 LLM 成本不收钱；render $0 定价不动；hold→capture→release 不动；订阅/支付 W11 边界不重开。
8. **L3 铁律不动**：字幕样式仅枚举，不开放自由版式；专业需求仍导出剪映/Premiere。
9. **验收口径**：四请求族 e2e 全通 + undo 可回滚 + 归档后 publication/operations 不连坐，live 走查证据齐才算成；批次完成度不顶替。

## 2. Product Contract v1（施工项按依赖序）

1. **归档不变量先行**（S1）：`outputs` 增 `status`（active/archived，default active）+ `work_id`（出生 = 新 UUID；重跑/修订重建继承 doomed 行）两列 + wipe 点改写 + 读面 active 默认过滤。服务「历史不再蒸发」。
2. **quote→range 解算器服务化**（S2）：`locate_span` 地基升格 edit 面服务 + 置信裁决 + 域拒绝回环。服务「把开头那句删掉」。
3. **edit_output 终态工具**（S3）：注册表 + args schema + R20 指认复用 + ops 落账 + 重渲染台账 + prompt 面双路（chat path 主座）。服务四请求族。
4. **计费偏好集成**（S4）：confirm_strategy 服务端化 + composer 换源 + dock 披露分级 + configs 阈值。服务「偏好真生效」。
5. **剧本座与 live 走查**（S5）：确定性尾剧本 + LLM 拍位 + 走查脚本。服务验收口径。
6. **docs 收口**（S6）：ADR 现在时注记 + PROGRESS 池销记 + JOURNEYS 旅程三修订拍状态。

**明确不做**：operations 前端 UI（undo/redo 卡面、版本 pager 扩面）——P1 出本批；`set_caption_visibility`；21 ops 任何形式的 LLM 可见性；既有死 id 数据修复；存储压缩/GC 机制（观察行已挂池）；自治修；edit 衍生的新停顿形态。

## 3. 工程拍板项（全带推荐答案）

**E1. 归档形态**：`outputs.status` + `outputs.work_id` 两列（推荐——ADR-091 批准 A 起步）。work_id = work 的物理锚：publication / operations 查询面挂 work_id（version 行 id 仍是生产事实键）；读面（画布 / run_review / OutputInspector）默认 `status=active`。`restore_version` = archived ↔ active 换态（同 work 内至多一 active）。**B（work 表分离）触发升级条件**：publication 真要挂根运营或跨项目引用出现时。

**E2. edit_output args 形状**：`{target: {output_id?: UUID, plan_ref?: string}, kind: enum, params: {quote?: string, seconds?: number, style?: string, title?: string}}`——指认二选一（@output pin 服务端解算 / plan_ref 序位骑 R20 快照），全空 = ask 反问；params 按 kind 取用，多给 = 域拒绝。读容忍牙（null → 缺省）同 revise_output 先例。

**E3. 解算置信谱**：精确数值（agent 引用产物已展示的区间）> marker 精确匹配 > 全文唯一文本匹配 > 多义命中 / 未命中 = **拒绝回环**（回环话术给可答形态：「这句在片里出现了两次，说第几次」/「没找到这句，把原话贴我」）。判据与阈值 = 纯函数 + 纯测试锁定。

**E4. 重渲染出生座**：复用 morph re-pend 同族（render_spec 改写 → render_status 重 PENDING → **镜像步骤同形状补登**——`render_step_label` 与 spec 形状律照抄，verify 修红批同款）——不发明第三座位。edit 落账与重挂在同一事务边界内完成（op 写 + re-pend + 镜像 = 原子）。

**E5. confirm_strategy 座位**：`users.settings` JSONB 新键（persona brand/voice 的 user 级先例）+ GET/PUT API；`large` 阈值 = configs 表 `billing.confirm_large_threshold`（ADR-055 参数座位，默认待施工定，建议 20）；composer localStorage 降级为首访回退。

**E6. 强制档闸形态**：披露强度分级（推荐）——`never` = estimate 槽现状；`always` = 费用五面完整披露行（ADR-087 §2.1）+ CTA 显价（「Confirm · 12 credits」/「确认 · 12 积分」）；`large` = quote 超阈值时同 `always`。**手势仍是 Start 一次**——停顿定律零破，差异化全在披露强度。

## 4. Prohibited Behaviors（施工期红线）

- 禁把任何原始 op 名 / op 参数内部形状写进 prompt 面或 LLM schema。
- 禁 LLM 输出时间戳 / UUID / 节点 id；quote 之外的范围表达一律域拒绝。
- 禁对已 `active` 交付产物行执行 DELETE（项目删除级联除外）——wipe 点只准写 `archived`。
- 禁迁移 / 修复既有死 id 旧数据；读面读容忍是唯一合法姿态。
- 禁新写门 / 新渲染出生座 / 新 dock 类型 / 新停顿手势。
- 禁静默失败：解算多义 / 未命中、指认落空、kind 越界——全部域拒绝回环带可答形态，永不猜、永不硬编默认值。
- 禁改动 scope classifier 本体 / Start 四合取 / operations 锁机制 / verify 回退的物理删除语义。
- 词表先登记（N-59：edit_output / quote→range / work / version / archived / confirm_strategy）再动工；i18n en 先 zh 镜像；展示文案二源律（op 回声 = 世界自证事实句，禁冻参模板）。

## 5. 切片与验收

| 片 | 内容 | 门禁 |
|---|---|---|
| S0 | N-59 词表登记 + ADR 交叉注记 + PROGRESS 池行销记开工 | check_gates |
| S1 | 归档两列 + migration + 两 wipe 点改写 + 读面过滤 + restore_version 换态 | 纯 pytest（wipe/读面/换态矩阵）+ migration 回滚实证 |
| S2 | 解算器服务化 + 置信谱 + 域拒绝回环 | 纯 pytest（置信谱全支 + 边界） |
| S3 | edit_output 注册表/schema/双路 + ops 落账 + 重渲染台账 + prompt 面 | 纯 pytest + prompt_gate（新增探针 = 四请求族路由） |
| S4 | settings API + composer 换源 + dock 披露分级 + configs 阈值 | 纯 pytest + web tsc/vitest |
| S5 | 确定性尾剧本（S-edit）+ LLM 拍位 + live 走查脚本 | 剧本座就位（live 用户自跑） |
| S6 | docs 收口（ADR 现在时 / PROGRESS / JOURNEYS） | 文档卫生 |

**验收标准**（逐条 = DoD）：
1. 「把开头那句删掉」→ remove_range 落账 + 重渲染 + 回声事实句带区间（「我把 0.0–4.2s 这段去掉了」）。
2. 「第二条再短 3 秒」→ set_trim，target 指认骑 @output pin，序位词不解为 id。
3. 「字幕换 karaoke」→ set_caption_style 枚举，自由版式请求域拒绝带可答形态。
4. 「标题改成 X」→ set_title。
5. undo（API 面）恢复上一 active version；archived 链完整可查。
6. 修订重跑后：publication 记录存活、operations journal 可溯、output_refs 不再累积死 id。
7. 三档 × 费用大小矩阵：never 档零披露变化 / always 档五面 + CTA 显价 / large 档阈值上下两态。
8. 认知验收（规则 9）：agent 看见了什么（产物卡 + 词级 transcript reads）/ 怎么知道自己对了（解算回声事实句 + 域拒绝零猜测）。
