# ADR-049 钩子预览闸退役——简报（2026-08-24）

> 状态：✅ 落地
> 拍板：2026-08-24（用户判词："这是过度设计"——评审点错位 + 决策疲劳）
> 简报：ADR-049 落档 + 4 bug 前置清理 + 代码整套退役
> 排期下一期：节拍方案产品面形态（chat 流卡片 vs overlay vs canvas 节点 metadata）

## 哲学

产品核心流：**chat-as-review / render-as-execution / canvas-as-result** 三段不破。

- 必要评审在 chat 完成
- chat 收敛后走渲染
- 渲染好进 canvas node

原 hook_gate 在 chat 之外插一段"评审视频"环节，把评审 AI 钩子质量的责任交给知识专家用户。三处冲突：

1. **决策疲劳**：用户擅长"我想要什么"判断，不擅长"AI 钩子写得对不对"
2. **评审点错位**：评渲染结果（视频）≠ 评 AI 决策内容（节拍方案）
3. **哲学违和**：ADR-041 + ADR-035 三段不破

正确评审面 = **节拍方案（beat plan）**——timeline 创作层的中间产物（图序/运动/切点/强调），纯数据 + 图片引用，零渲染成本，chat 评审的可寻址产物。让用户在 chat 看节拍方案卡片 = 评 AI 决策内容本身。

降级由 **AI 自评自动 set_title**（运行期 AI 触发），保留 set_title op。闸感抑制（避免白烧）的工程价值由 **chat 报价 fold + AI 自评质检环** 覆盖——产品不再有"渲染前用户卡"形态。

## 落地 5 commits

### Commit 1（5170d6c）：bug #1 — 闸注入条件

根因：闸条件 `not modifiers`——translate_clip / dub_clip 实际进了 modifiers 列表，`not modifiers` 总 False，闸不进图。

修：`not has_inplace_morph`——INPLACE_MORPH_KINDS + fork 标志判定。fork=True 允许闸，in-place morph 拒绝。

顺手：闸 spec 接收 pending_subs / pending_dubs（fork 派生行 target 语言），闸文案挂上让用户知道 fork 行会并行渲染。

8 个编译探针过：review+select_clips（注入）、+translate fork=true（注入）、+translate fork=false（拒绝）、+dub fork=true（注入）、+dub fork=false（拒绝）、+remove_filler（拒绝）、auto+select_clips（拒绝）、混合 pending_subs/pending_dubs 进闸 spec。

### Commit 2（8b0f524）：bug #2 — set_trim 上界 + HookPreview.source_duration

根因：dock 的调尾切点步进器（±1s）原只防下界 trimStart+1，上界盲信 initialEnd+5——源材料可能只有 initialEnd 那么长，server set_trim 没卡，renderer 拿到超出源的 trim 后画静止尾帧。

修：
- clip_spec.set_trim 加 source.duration 上界（ValueError），边界 inclusive
- schemas.HookPreview 加 source_duration 字段（None = 未知 → fallback 旧 +5）
- QuestionDock trim 上界改读 preview.source_duration ?? initialEnd+5

5 trim 探针 + tsc 全过。

### Commit 3（103dadd）：bug #3 — render_hook_preview previous_key

根因：闸跑前从 output.files.hook_preview 读旧 key 入 spec，再调 render_hook_preview；新 key 写回 row.files，但 storage 上老对象永远没人清——retry 一次多一份孤立对象。

修：render_hook_preview 加 previous_key 参数，闸调用前从 output.files 抽出传入；新渲染前调 delete 删老对象。best-effort，删失败不阻塞。

签名兼容：previous_key 默认 None = 旧调用路径不破。

### Commit 4（8eeb8be）：bug #4 — hook_gate 单事务 park

根因：原 park 拆 3 个事务（preview keys commit / dock message commit / node waiting commit）。1-2 之间 / 2-3 之间任何 crash 让 run 留 RUNNING 状态，preview keys 已落库，user answer 来了 resume_waiting_interrupt 找不到 waiting 节点，run 永远卡死。

修：3 事务合 1——同一 db session 顺序写 preview keys → dock_interrupt_question → node.waiting + suspend_payload → run.WAITING_HUMAN → 单 commit → raise Suspend。orchestrator 的 Suspend catch 变幂等 no-op。

顺手：dock_interrupt_question 移到主 session（去掉 AsyncSessionLocal 嵌套）；闸文案挂 pending_subs / pending_dubs。

ruff + 接线验证过。

### Commit 5（942556b）：代码整套退役

删除清单：

**后端 Python（apps/api）**
- `app/pipeline/hook_gate.py` 整文件
- `app/tools/__init__.py` 导入行
- `app/pipeline/orchestrator.py` §2.5 编译注入块（has_inplace_morph / pending_subs / pending_dubs 全段）
- `app/tools/clips/node.py` gated 分支（释放闸感抑制，仅留 _later_inplace_morph_exists）
- `app/pipeline/rendering.py` render_hook_preview 函数
- `app/models/schemas.py` HookPreview / HookTrim / AskPayload.previews + OutputResponse.files 解析元组去掉 hook_preview
- `app/operations/registry.py` SwapHookShotParams + _apply_swap_hook_shot + OP_REGISTRY 条目

**渲染服务（apps/render）**
- `src/server.ts` preview 请求体参数 + 分支
- `src/render.ts` preview 参数 + 帧范围/scale/crf 分支 + RenderResult.srtPath nullable → string

**前端（apps/web）**
- `components/chat/QuestionDock.tsx` HookPreviewStrip / HookPreviewTile / HookPreviewItem / applyHookOp + useState / apiFetch import
- `components/generation/GenerationOverlay.tsx` QuestionPayload.previews + HookPreviewItem import + previews 透传
- `lib/i18n/locales/{en,zh}.ts` hookGate.* 块 + step 钩子里的 hook_gate / release_renders 文案

11 files changed, +8 / -818。hook_gate.py delete mode 100644。

## 验证

- 编译探针：review+select_clips / +translate(fork=true) / +dub(fork=true) / auto+全链全部不再 inject hook_gate / release_renders
- assert_runners_registered：8 配方 flow ⊆ 编译图全过（无配方流仍名 hook_gate / release_renders）
- ruff：未引入新违规（pre-existing 错误与改前同形）
- tsc：apps/web + apps/render 全干净
- import 烟雾：`import app.pipeline.hook_gate` → ModuleNotFoundError（确认删除）
- Post-commit cold start：NODE_KINDS 无 hook_gate / release_renders；OP_REGISTRY 无 swap_hook_shot

## 已知未落档（混合文件，gallery v2 同期落地）

为保证 commit 边界干净（[[repurposer-rename-batch-per-commit-green]] "每 commit 冷启动验证或声明不可拆"），下列文件的 hookGate 残留待 gallery v2 commit 一起清：

- `apps/web/src/lib/i18n/locales/en.ts` + `zh.ts`：hookGate.* 块、step 钩子的 hook_gate / release_renders 文案已删（参见 commit 5 之前 session 的实际 edit），但同一文件同期被 gallery v2 改动——en.ts +82/-80 是混合 diff。整文件已在 gallery v2 工作中同步更新。
- `docs/DECISIONS.md`：ADR-049 全文已落档（参见 commit 之前 session 的 edit），同期 ADR-048 引用已并入。
- `docs/PROGRESS.md`：08-24 排产行已落档，同期 gallery v2 排产行已并入。

机制层已完整退役；上述残留待 gallery v2 commit 一起落档。

## 下一期：节拍方案产品面形态

ADR-049 拍板 beat plan 为评审界面，不决呈现位置。下一期单独拍板，候选：

- **chat 流卡片**（最直接）：每拍一张小卡，inline 渲染；chat loop 同面，最小摩擦
- **overlay**（类 dock）：消息触发节拍方案展开 overlay，沉浸式审阅
- **canvas 节点 metadata**（最克制）：节点解剖承载节拍方案，不在 chat 多开流

建议合并入"节拍方案卡片化"下一期，与 verify 节点质检环升级并行。呈现位置拍板后端侧把 beat plan 落 Output.payload 或新表（ADR-047 §1 中间产物路径已铺）。

## 相关

- ADR-047 §5（本条翻案去向，§5 现标题"评审回 chat"）
- ADR-041（评审在 chat、渲染进 canvas 的哲学基底）
- ADR-035（可操作画布永拒不变）
- ADR-040（chat 唯一发射路径不变）
- ADR-039（节点对象化 + 估价 = fold，渲染前用户可见是估价而非视频预览）
- 简报 `docs/tasks/output-quality-line.md`（节拍方案产品面施工与验收）
- a867112（commit 基线，作为机制退役的前置基线；其上 4 bug 修复为本 ADR 落地时的清理参考）
