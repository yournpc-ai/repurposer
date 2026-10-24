# Verification Harness 归位——PLANNED 合同

> Status: PLANNED，未开工。当前测试政策与运行纪律已经生效；本合同只覆盖后续文件归位和文档升格，不重做测试矩阵，也不改变任何产品行为。排期归 PROGRESS。

## 1. 目标形态

```text
apps/api/tests/             # 纯函数守卫，位置不变
apps/api/harness/           # live 验证仪器
  ├── README.md             # fixture / worker / 进程 / 配额纪律
  ├── scenarios/            # 共享 core + 按旅程拆分当前 SCENARIOS
  ├── prompt_gate.py
  └── probes/               # 需要长期维护的诊断仪表
apps/api/scripts/           # 运维；demo 烘焙可再分 scripts/demo/
apps/web/src/**/*.test.*    # 纯 node web 套件，位置不变
```

同步把 `docs/tasks/verification-contracts.md` 的合同↔守卫映射和 `test-suite-convergence.md` 的现行运行规范合并为 `docs/VERIFICATION.md`，在 `docs/README.md` 登记为验证唯一事实源；合并后直接删除旧文件，不留跳转页。未完成迁移前，`docs/VERIFICATION.md` 是规划目标而不是可用链接。

## 2. 实施约束

- 先查清当前 `scripts/` 的 `app.*` import 引导机制，harness 沿用同一方式；搬迁不改变场景注册、探针阈值或断言。
- 只搬当前仍使用的资产；一次性诊断和已退役仪器不搬。
- 同批更新 CLAUDE.md、README、PROGRESS、verification contracts 及所有命令中的 `scripts/chat_scenarios.py` / `scripts/prompt_gate.py` 路径。
- 保持零 schema 变更、零新依赖、零产品代码语义变化；web 测试位置不动。
- fixture、worker 抢跑、进程卫生、配额与 round-robin 纪律按 `test-suite-convergence.md` §5 写入新 harness README。

## 3. 验收

1. 新 harness 可收集、可导入；先用收集/import 冒烟，不为搬迁验证烧全量配额。
2. 当前纯 pytest、check_gates、web 检查按改动面通过；prompt_gate 与当前矩阵从新路径做收集/入口验证，付费全量另按授权执行。
3. 全仓旧 `scripts/chat_scenarios.py` / `scripts/prompt_gate.py` 路径引用清零；新文档链接有效。
4. `scripts/` 只剩运维与明确的 demo 烘焙；没有平行测试注册表或第二份验证政策。
5. 完成后更新 PROGRESS 和 README；未运行的全量门禁不得写成通过。

## Prohibited Behaviors

- 禁借搬迁调阈、放松断言、恢复退役剧本或改变旅程语义。
- 禁保留旧路径复制件、注释尸体或文档跳转墓碑。
- 禁把 P3 归位当作其他修复的前置；它是独立的可回退整理批。
