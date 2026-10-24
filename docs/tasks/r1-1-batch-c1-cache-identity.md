# R1.1 Skeleton Cache Identity——PLANNED 合同

> Status: PLANNED，可独立排期，不阻塞任何 milestone。目标是同一案例不重复拆解，且扫描/判断升级后旧骨架不串味；排期只读 PROGRESS §0.3。

## 1. 当前缺口

复用查找仍是 per-user 最近行 + Python 扫描，缺少并发去重和完整身份匹配：同一 asset hash 可双写，`CraftSkeleton.version` 与 judgment prompt 身份不参与命中，数据量增长后查询退化。

## 2. 实施合同

1. **per-user 唯一性**：以 `(user_id, type, source_ref->>'asset_hash')` 建 craft_skeleton 部分唯一索引。若 outputs 仍无 user_id，按当时 schema 选择反范式列 + 回填或等价方案；迁移遵守 DATABASE_MIGRATIONS 的锁与并发索引纪律。
2. **三类身份戳**：物化时写 `asset_hash`、`scan_version`（与 CraftSkeleton.version 同源）和 `judgment_prompt_hash`（物化时模板源哈希）。不提前抽象通用 producer version model。
3. **索引查找**：lookup 单条索引查询并同时比对三戳，移除 latest-N + Python 循环。
4. **并发复用**：唯一约束冲突时回退重查，一个写者胜出，另一个复用同一行，不重复计费。
5. **范围**：不搭车修改 warm lineage、Media IR、骨架时序结构消费或 `_find_reusable_understanding`；后者如需同样治理另立需求。

## 3. 验收

- 唯一索引生效且查询使用索引；同 hash 并发物化只产生一行。
- 同 hash + 同 scan_version + 同 judgment prompt 命中；任一身分变化均不命中。
- remix 当前旅程不回归，重复复用不重复收费。
- 迁移可回退或有明确前滚路径，既有行读容忍；不以“已建索引”代替并发实证。
