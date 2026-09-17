# Operation Model 实施简报——操作日志层地基

> Status: ✅ 已落地（2026-07-26：Phase 1 后端地基 + Phase 2a editor 迁移 + Phase 3 chat 接线全通并实测；Phase 2b 历史面板/editor undo 按钮后置）
> 依据：`docs/ROADMAP.md` §2；`docs/MODULE_ARCHITECTURE.md`（operations 表归属已登记 📋）；`docs/CHAT_ARCHITECTURE.md` §9（edit ops 边界）
> 有新表（`operations`）+ 新模块（`operations/` 包，过 NAMING §7 准入测试：独立表归属）→ **需 ADR-032** + 词汇表登记（NAMING §8）
> 评审重点：§2 的七个设计决策（D1–D7）——本文的核心产出，实施前逐条过

## 0. Context 与范围裁决

RunPlan Phase 1 与 chat loop v1 已在 main：生成侧"步骤皆可寻址"（workflow_steps）已通，chat 已能识别 edit_ops 意图但只回边界文案（`chat/service.py` 的 `_EDIT_OPS_BOUNDARY_TEXT`）。本轮交付**编辑侧的同构地基**：operations 表 + op 注册表 + 应用服务 + undo 语义，让 Editor GUI / chat /（未来）MCP 三个前端共用同一本操作日志。

**范围裁决**：
1. **v1 只做产物级 op，目标 = outputs[type=clip] 的 render_spec**。plan 级 op（`set_node_params` / `regenerate_node` / `swap_slot`）归 RunPlan 小拓扑，不进 operations 表——两个家族分开登记（CHAT_ARCH §3 已钉，本简报执行）。
2. **payload 类产物（文案/quotes）的 op 化不在本轮**——spec_after 列的形状对此留座（见 D1），但不接线。
3. **undo 必做**（VIDEO_EDITOR.md 已承诺 undoable）；redo 顺做（模型免费支持，见 §3）。
4. **render staleness 不动**：op 应用后是否重渲染维持现状（用户点 render）。`outputs.rendered_spec_hash`（"有未渲染修改"提示）记为 v1.5 候选，不抢跑。
5. **回流校准只做读路径设计**（§6 Phase 4），不建 persona 消费端。
6. **重构授权（2026-07-26 用户裁决）**：chat 与 editor 全链路可破坏性升级，**不为旧形态留兼容层**——`PUT /outputs/{id}` 的 render_spec 整包替换分支**直接删除**（editor 前端同迭代迁移到 op 提交，无 `set_spec` 过桥期）；chat 的 EditOp 宽容契约（extra=allow）**直接收紧**为 registry 校验，`_EDIT_OPS_BOUNDARY_TEXT` 边界文案随 Phase 3 退役。`set_spec` 唯一保留形态 = 漂移自愈的 system 内部 op（D7），不对客户端暴露。
7. **反过度设计锚定（2026-07-26 用户裁决）**：本轮产品的主目标 = "用户发现生成物不合理，能通过 chat 修改"的可见体验（参考形态：assistant 消息内嵌 run 结果卡——步骤清单带量化摘要 + 产物缩略图 + 聚合行 + Open in editor）。对账结论：该体验的动作全部是 **skill/run 级**（去口头禅/重剪/加音乐），走 task list → run 小拓扑即可，**不依赖 operations 表**；chat UI + run 结果卡归 chat-loop-v2 简报，不在本简报。本简报因此收缩：**做 Phase 1（后端地基）+ Phase 2a（editor Save 迁移——PUT 已删，必做）+ Phase 3（chat 接 edit ops）**；Phase 2b（历史面板 / editor 内 undo-redo 按钮 / 版本跳转界面）**后置**——undo/redo 后端端点保留（成本接近零，是 VIDEO_EDITOR 承诺与校准回流的唯一地基），undo 能力本轮经端点 + chat 撤销按钮可用。operations 表的存在理由 = 细粒度内容修改（"删掉第二句"）+ undo 承诺 + 校准回流，不为 run 级动作重复造轮子。
8. **chat 操作 DAG 的边界对账（2026-07-26 用户裁决：DAG 画布 UI 不做，只做内核）**：节点级操作（改节点参数、单节点/子图重跑、追加节点）是 **workflow_steps 上的操作**，归 RunPlan 家族，**不进 operations 表**——两家族分离：产物级操作（"删掉第二句"）→ operations 表 + clip-spec diff（本简报）；节点级操作（"这个节点换参数重跑"）→ step spec patch + 子图重跑（chat-loop-v2 的活，ROADMAP §3 plan 级 dispatch）。**DAG 可视化维持旧决策不变**（NAMING 词汇表"RunPlan 不是 DAG 画布，用户不见图"；运行图检视面仍 📋P2 信任工具）——本轮要做的内核 = 节点寻址 + spec patch + 子图重跑 API + chat dispatch plan 级目标，与画布无关；API 形状天然可供未来检视面复用，无需预留。

## 1. 已核实的现状事实（读码确认，实施时以此为准）

- **clip-spec 契约**：`packages/clip/src/types.ts`（TS）与 `apps/api/app/models/schemas.py`（Pydantic `ClipSpec`）双端镜像。`ClipSegment.hidden` 是非破坏删除的雏形；TS 有纯函数 `removeRange` / `setTrim`——Python 镜像在 `app/pipeline/clip_spec.py`（remove_range 已有，remove_filler runner 在用；set_trim 随本轮补入）。**op 注册表只做 params 校验 + 复用这些函数，不再各自移植**（2026-07-26 实施纠偏：简报初稿误判"Python 端没有对应函数"，registry 一度重复移植 remove_range，已重构回收）。
- **render_spec 现存写点（必须全部接线，一个不漏）**：
  1. `PUT /outputs/{id}`（`pipeline/routes/outputs.py:115`）——editor Save 整包替换 render_spec/payload；
  2. `POST /outputs/{id}/translate-captions`（outputs.py:268）——LLM 翻译后整体换 caption_track + target_language；
  3. `POST /outputs/{id}/dub`（outputs.py:318）——T2A 生成后烘焙 dub 轨道；
  4. Pipeline 创建 outputs（出生点，首次写 render_spec）；
  5. 单产物重生成（outputs.py:~155，改 payload——v1 不接，payload 超范围）。
- **editor 前端是 Save 模型**（`_app.projects.$id.clips.$clipId.tsx:192`）：用户动作 → 本地 TS 纯函数改 spec（乐观预览）→ 点 Save 整体 PUT。与"每动作一条 op"不冲突——前端把动作**记成 op 队列**，Save 时批量提交（§4）。
- **chat v1 的 EditOp 契约宽容存储**（`schemas.py:180` EditOp：`op` + `target` + `params`，extra=allow）——op 集合定稿后收紧为 registry 校验，`EditOpsProposal` 从"回边界文案"改为真应用（Phase 3）。
- **`outputs.render_status`**：worker 认领谓词（N-02，NULL=未请求）；op 应用不改它（范围裁决 4）。
- **命名宪法约束**：枚举 = String 列 + 注册表（N-03）；布尔语义用可空时间戳（N-04）；新模块须过准入测试（§7——operations 表归属 → `operations/` 包成立）；新名词登记词汇表（§8）。
- **outputs 三写者规则**（MODULE_ARCH §4）："内容字段的修改必须能产生一条 operation 记录（Operation Model 落地后强制执行）"——本轮把这条规则从纸面变成代码。

## 2. 设计决策（评审沉淀区——实施前逐条确认，实施后勿推翻）

### D1：undo 的机械保证 = 快照（spec_after），不是逆运算

每条 op 行存**应用后的完整 render_spec 快照** + 语义化的 `op` + `params`。undo = 回退到上一条快照；redo / 版本跳转同理。

**为什么不用"逆 op"**（存 op+params，undo 时算反向操作）：
- LLM op（`translate_captions` / `set_dub`）**没有可计算的逆**——逆向 = 再调一次 LLM，又贵又不确定；
- `removeRange` 会**丢掉范围内的 caption cues**（types.ts `removeRange` 实现），逆运算无法复活已丢数据；
- redo 需要 after 状态，纯逆运算模型下 redo = 重放 op，对 LLM op 同样不成立。

快照是 boring but correct（Git 存 tree、diff 是派生物的同构）。params 仍然逐条存——**校准回流要的是语义信号**（"用户删了哪段"），不是快照本身。

**存储估算**：render_spec ≈ 15–30KB（60s clip 词级 caption ≈ 150 cues）；100 次操作 ≈ 2–3MB，JSONB + TOAST 可压缩，可接受。未来若成问题，按 spec_hash 内容寻址去重（schema 不变，只改存取层）。

### D2：baseline 行（op=`snapshot`，seq=0）——懒创建

存量 outputs 有 render_spec 但无 op 历史。每个 output 首次应用 op 时，服务先插一条 baseline 行（`op="snapshot", seq=0, spec_after=当前 render_spec, source="system"`），之后的 op 从 seq=1 开始。**推导不变式：op N 的 before = op N-1 的 spec_after**，于是 undo/redo/版本跳转全部只需 spec_after 一个快照列。baseline 不可被 undo（undo 到 baseline 即停）。

### D3：顺序与并发 = per-output seq + 行锁 + 乐观哈希

- `seq` Integer + `UniqueConstraint(output_id, seq)`——不用 created_at 排序（时钟并列、同事务批量）；
- 应用事务内 `SELECT ... FOR UPDATE` 锁 output 行——editor 与 chat 同时改同一 clip 不撕裂；
- 客户端可带 `base_hash`（它编辑时基于的 spec 哈希）——不匹配返回 **409**，前端 refetch + toast（"此片段已在别处被修改"）。editor 多 tab / chat 并发是真实场景，这不是过度设计。

### D4：否决 `restore_range` 独立 op——恢复语义全归快照层 ⚠️ 设计坑

CHAT_ARCH §9 初集里有"恢复删除"类 op。**评审发现它不成立**：`removeRange` 在 spec 内就把 caption cues 真删了，`restore_range` 作为独立 op 只能 un-hide segments、**复活不了字幕**——恢复出来的片段没有字幕，产物是坏的。

裁决：**v1 不提供 restore_range**；"恢复已删内容"只有一个路径——快照层（undo 那条 remove_range / restore_version 到删除前）。要真做"在编辑器里点选已删句恢复"，前置是 clip-spec 契约扩展（caption cues 也加 hidden 标记、renderer 跳过 hidden cues）——那是 ADR-016 契约改动，单独评审，不混进本轮。

### D5：op 初集冻结（v1）

| op | params | 说明 | 应用方式 |
|---|---|---|---|
| `snapshot` | `{}` | baseline（D2），仅 system，不对用户暴露 | 服务内部 |
| `remove_range` | `{start, end}` | 删句=剪段（移植 TS removeRange） | 纯函数 |
| `set_trim` | `{start, end}` | 单轨 trim（移植 TS setTrim） | 纯函数 |
| `set_title` | `{text, enabled}` | 标题卡 | 纯函数 |
| `set_caption_style` | `{preset?, enabled?, position?}` | 字幕预设枚举（ADR-016 纪律：不自由排版） | 纯函数 |
| `set_music` | `{music_id?, enabled, gain_db}` | 音乐轨道 | 纯函数 |
| `set_crop` | `{x, y, scale}` | 画面裁切 | 纯函数 |
| `set_spec` | `{render_spec}` | **system 内部 op**：仅漂移自愈（D7）使用，**不对客户端暴露** | 直接替换 |
| `restore_version` | `{operation_id}` | 跳到某条 op 的 spec_after；自身也落一行（可 undo） | 快照拷贝 |
| `translate_captions` | `{target_language}` | 包装现有端点（LLM 同步） | 预计算（§4） |
| `set_dub` | `{enabled, gain_db, ...}` | 包装现有 dub 端点（LLM 同步） | 预计算（§4） |

不在 v1：`reorder_segment`（editor 无此 UI，注册表后补零迁移）、`apply_preset`（定义不清，随配方卡线再评）、`restore_range`（D4）、一切 plan 级 op（范围裁决 1）。

### D6：undo/redo = `undone_at` 可空时间戳，append-only 不删行

- undo：找 active（`undone_at IS NULL`）中 seq 最大者（> baseline）→ 打 `undone_at` → render_spec 回退到上一条 active 的 spec_after；
- redo：active head 之上若紧挨 undone 行 → 清 `undone_at` → render_spec = 该行 spec_after；中间插入新 op 后 redo 栈自然失效（undone 行不再紧挨 head），无需删行；
- **新行的 seq 水位 = 全量行的 max(seq)（含 undone 行），不是 active head 的 seq**——undone 行保留 seq 坑位，按 active head+1 插入会撞唯一约束（实施实证）；
- **历史永不删改**——校准回流能看到"用户删了又悔"的完整行为，这也是审计资产。符合 N-04（白得审计信息）。

### D7：现存写点接线与漂移自愈（无兼容层，2026-07-26 用户裁决）

- `PUT /outputs/{id}` 的 **render_spec 分支直接删除**（破坏性升级，不留过桥）——editor 前端在 Phase 2 同迭代迁移到 op 批量提交；payload 分支保留（payload 超范围）。两期间隙 editor Save 不可用是可接受的（同迭代交付，间隔以天计）。
- `translate-captions` / `dub` 端点 → LLM 工作完成后走 `apply_precomputed`（带 op+params+新 spec）落行。
- **漂移自愈**：应用前校验 `hash(当前 render_spec) == active head 的 spec_hash`；不等 = 有写点绕过了 service → 自动补一行 `set_spec`（source=`system`，params 记 drift 标记）把日志拉回真实状态，并 log warning。**日志永不谎称现状**——这是"所有写必须过 operation"规则的 enforcement 兜底，也是 `set_spec` 存在的唯一理由。

## 3. 表结构（迁移 + models/tables.py）

```python
class Operation(Base):
    __tablename__ = "operations"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    output_id  = Column(UUID(as_uuid=True), ForeignKey("outputs.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    seq        = Column(Integer, nullable=False)                      # per-output 单调；baseline=0
    op         = Column(String(50), nullable=False)                   # 注册表守门（N-03）
    params     = Column(JSONB, nullable=False, default=dict)          # 语义信号（校准回流读这里）
    spec_after = Column(JSONB, nullable=False)                        # 应用后快照（D1）；payload 类接入时同列装 payload
    spec_hash  = Column(String(64), nullable=False)                   # sha256(spec_after 规范化 JSON)
    source     = Column(String(20), nullable=False)                   # editor | chat | mcp | system（注册表）
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)   # system 行为空
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True) # chat 血统（哪句话导致的）
    undone_at  = Column(DateTime(timezone=True), nullable=True)       # N-04：可空时间戳替布尔
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (UniqueConstraint("output_id", "seq"),)
```

字段辩护（防 god-table 预演）：
- `project_id` 冗余自 outputs——校准/列表按项目查免 join，值不可变（output 不换项目），可接受；
- `params` vs `spec_after` 各司其职：params = 语义（为什么变），spec_after = 机械（变成什么样）——D1；
- 无 `status` 列：应用是同步事务，行存在即已应用，失败即回滚无行——不养状态机；
- 无 `updated_at`：append-only，行不可变（`undone_at` 是唯一可写字段，自带时间戳语义）。

## 4. 模块与 API

**包** `apps/api/app/operations/`（过准入测试：独立表归属）：
- `registry.py`——OP_REGISTRY：op 名 → {params_model, apply(spec, params)->spec 纯函数 | precomputed 标记}；SOURCE_REGISTRY：editor/chat/mcp/system；启动自检（chat-loop registry 先例）；
- `service.py`——`apply_operations()`（baseline 懒建 → 漂移检查 → 逐 op 校验/应用/落行 → 更新 output，单事务）/ `apply_precomputed()` / `undo()` / `redo()`；
- `routes.py`——下述四个端点；
- spec 纯函数（removeRange/setTrim 的 Python 移植）放 `registry.py` 内，dict in / dict out，ClipSpec parse 校验。

**API**（命名过 NAMING §4）：

```
GET  /api/v1/outputs/{output_id}/operations            # 历史（含 undone 态），editor 时间线/未来校准
POST /api/v1/outputs/{output_id}/operations            # {ops: [{op, params}...], base_hash?} 原子批量 → {output, operations}
POST /api/v1/outputs/{output_id}/operations/undo       # → {output}
POST /api/v1/outputs/{output_id}/operations/redo       # → {output}
```

批量原子是 editor Save 模型的自然形态（§1 现状）：前端动作队列一次提交，全成或全滚。

## 5. 分期（防范围蠕变）

| 期 | 内容 | 验收 |
|---|---|---|
| **Phase 1 后端地基** | 迁移 + 表 + registry + service + 四端点 + spec 纯函数移植 + 写点接线（**PUT render_spec 分支直接删除** / translate / dub 落 op）+ 漂移自愈 | curl 全链：建 baseline → 批量应用 3 op → undo → redo → restore_version → 漂移注入自愈；409 并发路径 |
| **Phase 2a 前端接线（与 Phase 1 同迭代交付，必做）** | editor 动作记 op 队列（本地 TS 函数继续乐观预览）→ Save 批量提交带 base_hash；409 → refetch+toast；i18n `operations.*` | 手测：编辑 5 动作 → Save → operations 表 5 行 → render_spec 正确；chat 改过的 clip 在 editor 保存提示 409 |
| **Phase 2b 编辑器历史 UI（后置，本轮不做）** | 历史面板（op 时间线 + source 图标 + 点击 restore_version）；editor 内 undo/redo 按钮 | （排入后续迭代；undo 能力本轮经后端端点 + chat 撤销按钮可用） |
| **Phase 3 chat v2** | EditOpsProposal → registry 校验（EditOp 契约从宽容收紧）→ service 应用（source=chat + message_id 血统）→ assistant 消息列出已应用 op（可单条 undo）；`_EDIT_OPS_BOUNDARY_TEXT` 退役 | curl：chat 说"删了第二句"→ spec 真变 + operation 行带 message_id → undo 可用 |
| **Phase 4 回流座位** | 只落文档：校准查询模式（按 project/op/时间窗聚合 params 信号）写进 MODULE_ARCH 回流边注记 | 无代码 |

## 6. 禁止行为（Prohibited Behaviors）

1. **禁绕开 `operations/service.py` 直写 render_spec**——现存写点以 §1 清单为准全接线；新写点默认违规（漂移自愈只是兜底，不是许可证）。
2. **禁为 undo/redo 删除或覆写历史行**——append-only，`undone_at` 是唯一可写字段。
3. **禁 plan 级 op 进 operations 表**（`regenerate_node`/`set_node_params`/`swap_slot` 归 RunPlan 小拓扑，两个家族分开登记）。
4. **禁 `restore_range` 独立 op**（D4：caption 不可复活；恢复走快照层）。
5. **禁布尔列 / 禁 op 名裸写字符串不过注册表 / 禁 PG ENUM**（N-02/N-03/N-04 先例）。
6. **禁 LLM 直写 spec**：chat 来的 op 必须过 registry params 校验才应用（chat-loop 硬约束延伸）。
7. **禁新增 op 不评审不登记**——op 名进 NAMING 词汇表，registry 准入过评审（§8）。
8. **禁 MCP 抢跑**：source 注册表留 `mcp` 值即可，不建任何 MCP 代码。

## 7. 配套文档动作（随 Phase 1 同 PR）

- ADR-032：operations 表 + 快照式 undo（D1/D2）+ op 集边界（范围裁决 1 / D4 / D5）——追加进 DECISIONS.md；
- NAMING.md：词汇表加「操作 / `Operation`」「操作源 / `source`」条目；D4 记判例（restore_range 否决理由）；
- MODULE_ARCHITECTURE.md：operations 表状态 📋→✅，§3 Operation Model 行现状代码列更新；
- ROADMAP.md §2：三行状态更新；
- CHAT_ARCHITECTURE.md §9：edit ops 初集注明"产物级定稿见 tasks/operation-model.md D5，plan 级归 RunPlan"；
- VIDEO_EDITOR.md：undo 注记从"待 Operation Model"改为指向本简报。
