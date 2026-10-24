# Lifecycle——剩余验收与 Hygiene 合同

> Status: 早期验证/对账开放；hygiene 为 PLANNED，未开工。架构原则归 ADR-087；hygiene 只做已登记的零行为变化清理，永不进入关键路径，其他工作不得依赖它。
>
> 启动前置仍未被当前证据证明：早期 lifecycle 验证尾项和旧 Phase 2 步⑤的状态冲突须先在 PROGRESS 对账。不得仅凭旧“CLOSED”记录认定前置已经满足。

## 0. 前置对账与早期验收欠账

以下是启动 hygiene 前必须保留或关闭的 lifecycle 事项，不是新的施工批：

- **当前验证**：compileall/冷导入、web 类型与纯函数检查、当前 lifecycle/material 旅程仍有验证尾项；旧移动端 plan-card 验收改为当前移动端纯 chat、plan echo 与刷新恢复，不复活已退役卡面。
- **生命周期读面**：核对 `derived` / `reasons` 的最终分类与当前 canonical 行为；`PLAN_READY` 和 `CONFIRMATION_READY` 不可混用，缺失 stamp 是 unknown，估价完整性不是 PLAN_READY 前置。
- **旧 Phase 2 步⑤**：旧合同仍标 HOLD，而后来的相位退役与 ADR-133 已改变实现。先记录并完成状态对账；既不要重做删除，也不要仅凭后续文档把 HOLD 写成已关闭。
- **`_read_face` 删除条件**：只有生产 DB 守卫查询证明 `generator` / `processor` / `agent` / `modifier` / `materialize` 五类 legacy 节点与旧 toolset 行均为零后才可删除。开发库计数不能代替生产证据；此前一直是 DEFER。
- **Disclosure 残留**：核对 prompt 中“when the card is shown”一类旧 plan-card 条件；若仍在，按 ADR-111 的现行呈现面清理并跑 prompt_gate，不把旧短语保留为法律。
- **scope 安全缺口**：`delete_node + run` 的精确历史 scope 比较仍是未来领域能力；在可证明之前一律 unproven 并走安全授权路径。targeted `tasks=None` 与 legacy slot-run 整族重试可以是安全 false negative，不得静默改成直接执行；是否投入新能力需单独产品决策。
- **approval provenance 文档/代码差异**：ADR-089 §4 要求有效 confirmed scope/approved provenance；当前 `scope_classifier.load_historical_chains` 仍会把带 `context.tasks` 的历史 run 纳入证明基线。生产 legacy 暴露面**尚未核实**，这不是已确认生产事故。关闭前必须二选一：让缺少有效 approved provenance 的 legacy run 不能授权 `/generate`，或明确重新裁决并同步 ADR/验收；不得只改文档掩盖差异。
- **触发与依赖方向现行法**：当前 trigger kinds 为 `run_completed` / `run_failed` / `craft_decompiled`；ADR-087 若仍列 `understanding_warmed` 应同步删除。pipeline 永不 import chat，只经批准的 event seam、公开应用命令或显式只读协议回接。

## 1. 已批准范围

1. **按职责缝拆分巨文件**：`chat/service.py`、`models/schemas.py`、`pipeline/graph_fill.py`。只沿现有职责平移，不建立第二事实源，不顺手改产品语义。
2. **`Message.intent` 强类型化**：改为明确 union，同时保持 NULL 与 legacy 行可读。迁移顺序为 tolerant reader → narrow writer → tightened type，并有序列化/反序列化覆盖。
3. **`edit_output` 事务对称性**：使 operations 路径的 commit/rollback 与其他写口对称；若确有例外，必须在 ADR/模块合同记录具体理由，并有失败路径零残留测试。
4. **ChatDock 仅评估**：是否继续拆分取决于依赖方向与承重结构，不为缩短文件而拆，不改变两形态机与草稿保活。

其余 threshold / 词汇单主化只有在形成具体清单后才可排入；新发现登记 PROGRESS，不在本批静默扩 scope。

## 2. 实施与回退

- 一文件一批、一缝一提交，每步可独立回退。
- 拆分必须是纯平移；compileall、冷导入探针与当前纯测试证明行为不变。
- 数据/类型收紧先保证旧行读容忍，再收窄写面；不得直接清洗或重写历史消息。
- 触及代码地图时同步 MODULE_ARCHITECTURE §7；普通平移不新增 ADR。

## 3. 验收

- 当前完整纯 pytest、check_gates、适用的 prompt_gate、当前注册旅程矩阵与 web 检查按改动面通过。
- 三个拆分目标没有平行事实源，公开 import 与依赖方向不变。
- `Message.intent` 新类型与 NULL/legacy 读容忍同时成立。
- `edit_output` 失败注入后无部分提交、无孤儿副作用；或存在明确、已批准的例外合同。
- 全部验收只写当前结果；旧文件行数、提交清单和退役剧本名不作为验收证据。

## Prohibited Behaviors

- 禁产品语义变化、禁让其他 lifecycle 工作依赖本批、禁顺手扩项。
- 禁为“整洁”破坏 ChatDock 恒渲染/恒定子索引、SSE、授权或唯一写口。
- 禁把未执行的前置对账写成已完成。
