# R1.1 Batch C1 — Skeleton Cache Identity（并行项，不阻塞任何 milestone）

> Status: PLANNED（2026-09-16 建；**并行项**——可插 Batch 5 空档，**不得阻塞 R1 或 R1.1 的任何验收**；排期唯一事实源 = `docs/PROGRESS.md` §0.3）
> 行号核验于 HEAD `e8dbced`；开工前以 current HEAD 重新定位。

## 1. Product goal

服务 **J2 规模化**：同一个案例视频不重复拆解烧钱；craft_scan 或判断层升级后，旧骨架不串味。

不阻塞旅程闭合——remix 用得越多越疼，属「越用越聪明」的打磨，不是可用性缺口。

## 2. Current state（核验于 e8dbced）

- `_find_reusable_skeleton`（`app/pipeline/decompile.py:74-106`）：取该用户最近 **20 行** craft_skeleton（`:93 limit(20)`）后 Python 循环比对 `source_ref.asset_hash`——无索引、无唯一约束、version 不参与命中。
- warm 行 `step_id=None`（`:342`）——lineage 问题，**本批明确不修**。
- 并发双物化无防护：warm 与 run 路径可同时物化同 hash 骨架。
- `CraftSkeleton.version` 已存在于 payload（扫描层版本），lookup 不比对它；judgment 层（LLM prompt）身份完全不进命中。

## 3. Gap

cache identity 不正确：① 同 hash 可双写；② 版本升级后旧骨架静默命中；③ 查询随数据规模退化。

## 4. Files / modules

- migration（`docs/DATABASE_MIGRATIONS.md` 工作流）
- `apps/api/app/models/tables.py`（outputs 可能需 `user_id` 反范式列——见 T1）
- `apps/api/app/pipeline/decompile.py`（物化盖戳 + lookup 重写）
- `apps/api/tests/`（新增纯函数测试）

## 5. Preconditions

无硬前置（与 R1 各批正交——但**顺序上**排在 R1 停止线之后施工，避免与 Batch 2/4a 的 outputs migration 相互 rebase）。

## 6. Implementation tasks

### T1 — migration：per-user 唯一约束（= dedupe = lookup 索引，三合一）
- **Objective**：`(user_id, type, source_ref->>'asset_hash')` 部分唯一索引（`WHERE type='craft_skeleton' AND source_ref->>'asset_hash' IS NOT NULL`）。
- **VERIFY BEFORE CODING**：`outputs` 无 `user_id` 列（只有 `project_id`）——复用是 per-user 跨项目的，去重域必须是 user。方案 = outputs 加 `user_id` 反范式列（Asset 既有先例）+ 回填 + 索引；或大事务回填 + `CREATE INDEX CONCURRENTLY` 取舍按 `DATABASE_MIGRATIONS.md` 裁定。

### T2 — 物化三戳
- `source_ref` 盖 `{asset_hash, scan_version, judgment_prompt_hash}`：scan_version = `CraftSkeleton.version` 同源；judgment_prompt_hash = judgment j2 模板源在物化时刻的哈希。
- **封顶纪律**：三戳到此为止——不抽象「所有 producer 统一 version model」，不进 renderer/model version（那时再扩）。

### T3 — lookup 重写
- 单条索引查询，三戳全比对；**删除 latest-20 + Python 循环**（`decompile.py:83-106`）。
- 并发双物化：唯一约束冲突 → 回退重查复用（一个赢一个用）。

### T4 — 测试
- 纯函数：三戳命中/不命中矩阵；并发双写一者复用。
- 验证：同 hash 重复物化构造上不可能；version/prompt bump 后旧骨架不再命中。

## 7. Do NOT touch

- **lineage**（warm 行 `step_id=None` 维持原样——「以后一定需要」不是建它的理由，与 Media IR 不提前抽象同款纪律）。
- `_find_reusable_understanding` 同款缺口（挂账，不搭车）。
- Media IR / artifact ontology。
- 骨架时序结构消费（结构级 remix，OPEN）。

## 8. Acceptance

- [ ] 唯一索引在位（EXPLAIN 走索引，无 latest-20 残留代码）
- [ ] 三戳 predicate：同 hash 同版本命中 / version bump 不命中 / prompt bump 不命中
- [ ] 并发双物化 → 单行
- [ ] remix 路径回归不红

## 9. Docs update（完成后同批）

- `docs/PROGRESS.md` §0.3：C1 → DONE + commit。
- `docs/ARCHITECTURE_NORTH_STAR.md` §9.1 Decompiler CURRENT 限制清单相应行翻转。
- 本文件 Status → DONE。
