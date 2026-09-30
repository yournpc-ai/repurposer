# 渲染所有权与就绪语义 — 施工简报（ADR-096）

> Status: 拍板待开工（2026-09-30）。批次切分：A 立即批 → B 恢复批 → D 终态批 / E 同族批（D、E 同族分开验证）。
> 架构母法 = ADR-096；用户面就绪语义唯一化 = ADR-097 §5（本简报不动它）。

## 背景（取证定案）

一次交付的实现链 `select_clips → translate(seq 11) ∥ reframe(seq 12)`（同层并发、非 fork、不同 track，变体并行律内合法）：reframe 先完工认领渲染（payload = 缺翻译轨旧 spec）→ translate 后完工按 seq 存在性 defer（render_status=NULL、不建 step）→ 在飞渲染被 token CAS 正确丢弃 → 所有权落空，产物永久黑卡；verify 不查文件通过；run_completed 按 payload 播报成功。根因 = 运行期用 seq/状态/墙钟猜编译期已知事实。事故全量时间线入 ADR-096 Context。

## 批次 A：过渡立即律（D2-status + D3 双职责）

### 施工点

1. **defer 状态感知**（`app/pipeline/morph.py`）：`later_inplace_morph_exists` 的判定从「更晚 seq 非 fork morph 存在」改为「更晚 seq 非 fork morph 的 step 状态 ∈ {pending, running}」。调用序核查：判定必须在该 morph 对 output 行的 re-pend（行锁）之后、同一事务内执行——现行 morph runner（reframe/captions/dub/filler/music 五座）均为此序，施工时逐座复核不假设。
2. **verify 拒错误完工（两态判负 + 三态弃权）**：判负只取两态矛盾——render_status NULL 且无文件（所有权洞）、COMPLETED 且无文件（终态矛盾），走既有 fidelity bounce / needs_human；pending / rendering / failed 弃权（verify 与渲染赛跑是设计形态，FAILED 由渲染镜像与 render_failed gap 呈现，双门只会误弹生成器）。`run_review` landed facts 同律（payload-complete/files-empty 不得计 landed，事实行标 render=NOT-READY）。
3. **finalize reconcile**：run 收尾（`maybe_finalize_run` verdict 之前）幂等扫描本 run 产物中「有 render_spec 但 render_status=NULL 且**未归档**且无 pending render step（跨 run 防御——他者已认领的渲染永不双重拥有）」者，经既有 `pend_suppressed_base_renders` 路径 re-pend（谓词抽纯 `needs_render_reconcile`；归档排除承重——claim 门永不拾 archived 行，re-pend 归档产物 = pend 一个无 worker 认领的渲染，run 永远开着）。

### 验收

- 事故交错序列回归（translate ∥ reframe 两种完工序各一遍）：终态 = 一产出一有效文件，无永久 NULL；
- 在飞渲染被 re-pend 杀死后必有新渲染接替（「已被新的渲染取代」恒为瞬态）；
- verify 对空文件产物判不过；
- 纯函数/集成测试覆盖 defer 判定真值表（更晚 morph ∈ pending/running/done/failed/skipped 五态）。

## 批次 B：D4 恢复（条件流程，目标 = dev DB 产物 `1cab75fc-7429-4c3f-91d8-62261e1ba2da`）

严格按 ADR-096 §6：前置核实（属事故 run 且未归档 / spec 含全部预期 morph 终改 / 无有效 pending·running render step / 文件无效且无有效在飞 token / 不触发重复扣费与重复建任务）→ 事务内条件 UPDATE + 行数断言 → 经既有 fan_out/enqueue 建任务（**不是只改状态**）→ 确认认领、完工、文件有效、run 与产物状态一致。禁裸 SQL 状态改写。

## 批次 D：终态批——编译静态所有权 + 渲染屏障（删 defer 律）

### 施工点

1. 编译器为每份 output 静态指定唯一 **render owner**（通常 = 装配站；与 ADR-097 的 artifact owner 同一编译期事实的两个消费面）；
2. 非 owner morph 不再 re-pend、不再建 render step（`fan_out_renders` 收窄为 owner 专属）；
3. owner 的 render step `inputs` 屏障 = 同产物全部并行写入者 step——编译期静态可枚举；
4. `later_inplace_morph_exists` 与 defer 分支**整条删除**；
5. **失败语义**：非 owner morph 失败 → owner 阻断 + 命名修复路径，**永不拿部分 spec 渲染看似成功的终产物**（morph-failure rescue 既有座承接，ADR-096 §1）。

### 验收（交错序列全覆盖，缺一不收）

owner 先启动他者后启动 / 非 owner 先完工 / owner 先完工 / 非 owner 失败（阻断语义）/ owner 屏障等待中被取消 / run 恢复后屏障与 owner 不重复执行 / 多 output fork 时各 owner 只等自己的写入者；并行链零死渲染、零提前渲染。

## 批次 E：track 原子写（与 D 同族，分开验证）

in-place morph 的 spec 写改 output 行锁内 track 级局部更新（`jsonb_set`，track 注册表为写入权限依据）+ 合并后 `ClipSpec.model_validate` 全量重校验。验收 = 并发不同 track 不丢更新；同 track 冲突显式拒绝或串行；跨 track 联合不变量重校验无漏。

## Prohibited Behaviors

- 禁改 worker 认领机制与 claim token CAS（ADR-079 承重面零 diff）；
- 禁立即批与终态批对同一产物同时生效（双机制 = 新竞态源）；
- 禁裸 SQL 恢复生产数据；
- 禁 reconcile 成为正常路径依赖（它是修复机制，正常路径必须在 morph/runner 层自给）；
- 禁非 owner 失败后静默部分交付；
- 禁 verify 只查文件存在不查版本对应；
- 禁以 seq/时间戳/墙钟重新引入任何形式的所有权推断。
