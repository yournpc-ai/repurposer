# 测试资产大整顿：用例目录 → 瘦身 → 归位

> Status: 已拍板待开工（2026-09-29 用户拍板：四阶段顺序 + VERIFICATION.md 独立成文 + 巨石瘦身后再拆 + 删前过堂门）
> 施工合同。开工先通读本文；排期/优先级归 `PROGRESS.md`，本文只管怎么施工。

## 1. 背景与目标

言语真值大迭代（批次一/二/三，均已验收闭环）与此前多轮形态重建（三形态机 / dock 确认 pill / workspaceBorn / 活动投影）之后，测试资产两层失修：

- **漂移**：纯 pytest 11 个既有失败（PROGRESS 需求池 P1）；剧本 27 座中部分断言的链路形态可能已退役；prompt_gate 探针数与 CLAUDE.md 记载漂移（三探针 → 实际 11）。
- **散落**：验证仪器 / 运维脚本 / 营销烘焙三族混居 `apps/api/scripts/`（26 个）；承重仪器 `router_ab_probe.py` 被 CLAUDE.md 预部署仪式引用却住 `scratch/`；`chat_scenarios.py` 为 5000 行巨石。

目标：测试资产**回归现行用户体验链路**（每个存活座能指认它守的用例），且**各归其家**（仪器 / 运维 / 烘焙 / 一次性探针分家，承重仪器升编）。

## 2. 现状盘点（2026-09-29 实测，以此为锚）

| 家 | 实测 | 处置方向 |
|---|---|---|
| `apps/api/tests/` | 42 个纯函数套件 | 不动结构；11 个失败逐座裁决 |
| `apps/api/scripts/` | 26 个脚本 = 验证仪器（chat_scenarios / prompt_gate / reply_quality_probe / check_gates / verify_beat_map / crop_track_parity / reframe_smoke / accept_* / craft_anatomy / run_anatomy_matrix / track_model_fixture…）+ 运维（reset_db / seed_default_music / cleanup_stuck / reconcile_credits / migrate_to_tos / backfill_graph / restamp_draft_graph）+ 烘焙（bake_* ×6 / spike_reframe / upload_recipe_assets） | 三族分家 |
| `apps/api/scripts/chat_scenarios.py` | ~5000 行，注册表 27 座（S1~S24 + S-explore-2 + S-edit） | 瘦身后按旅程拆文件 |
| `apps/web/src/**/*.test.*` | 10 座 vitest 组件旁置（answerSettlement / optionMatch / historyReplay / chatStreamFrames / chatTimeline / activityReducer / lifecycleStamp / stagingUploads / utils / layout） | 不动 |
| `scratch/` | 13+ 探针/harness（router_ab_probe / reply_quality 已升编先例 / repro_chat_500 / precise_edit_live_drive / probe_F_forensic / ab_tool_wire_probe …） | 承重者升编，一次性留堆 |

## 3. 四阶段（删前过堂门是硬闸）

### P0 用例目录（只读，先行的地基）
产出**用例目录草案**：旅程 × 拍 → 用例 → 现有座位（纯 pytest / vitest / 剧本 / gate 探针 / live-only）→ 状态。

**P0 交付的第一个动作 = 向用户完整呈现用户旅程地图与用例目录**（四条旅程逐拍讲清楚、每拍对应哪些用例、每用例现有座位），不是只交一张表——**用户确认「这就是我们的旅程和要守的用例」后 P1 才开工**。理解错了，后面普查全错。

- 三源并集：`docs/JOURNEYS.md` 四旅程逐拍 + 批次三收官验收 17 条（PROGRESS §0.2 批次三行 / ADR-094 批次报告）+ `docs/CHAT_ARCHITECTURE.md` 行为律。
- **并行输入**：主会话同期在排查用户 live 测出的缺陷——每个确认的缺陷若暴露未守的链路，补为用例目录的一行（缺陷修复本身不在本批）。首批三条（2026-09-29 用户 live 测出）：① 上传视频发送拍画布即出生（违反「内容到达才出生」）→ 用例 = 画布只在首个非 Source 实体越过 queued 占位时翻转；② trigger 首读表格渲成裸文本 → 用例 = 首读表格永远渲成表格；③ 选项作答后新节点右长而相机左移空白区 → 用例 = 新节点诞生相机恒指向新节点（C6）。
- live-only 是合法座位：打字机节奏 / 原地不 remount / dock 形态这类客户端法律标 live-only，**不补假剧本座**。
- 同时暴露反向洞：有用例无座位 = 覆盖洞，登记（决定补座或显式 live-only）。

### P1 裁决 + 普查（只读）
- **11 个既有失败逐个裁决**（decompile×1 / graph_wiring×8 / import_direction×1 / wire_tiers×1）：每座判定 = 法律仍现行（修代码或修测试）/ 法律已退役（删测试）/ 法律已变更（改写守新法），**附证据**（该座守的法律条文出处 + 现状代码行为）。⚠️ 「失败 ≠ 过时」——`import_direction` 是模块分层静态门，先按真回归嫌疑审。
- **全资产普查表**：42 纯座 + 10 vitest + 27 剧本 + gate 探针 + scratch 仪器，逐个映射用例目录；映射不上 = 退役候选。
- **退役名单交用户过目拍板后才进 P2**（硬闸，不可跳过）。

### P2 瘦身执行（动手）
按拍板名单删/修；per-commit 自绿；删就删透（历史在 git，不留注释尸体）。PROGRESS 需求池 P1 行随裁决结果闭环或改述。

### P3 归位（动手，幸存者搬家——不搬尸体）
```
apps/api/tests/            # 不动
apps/api/harness/          # 新家：一切 live 验证仪器
  ├── README.md            # harness 律（见 §5）
  ├── scenarios/           # chat_scenarios 拆巨石：共享 core + 按旅程分文件
  ├── prompt_gate.py
  └── probes/              # reply_quality_probe + router_ab_probe（自 scratch 升编）等
apps/api/scripts/          # 收窄 = 纯运维
apps/api/scripts/demo/     # bake_* 烘焙一族
scratch/                   # 只留真一次性；被任何文档/仪式引用即升编
```
- **搬迁前查清现有 import 引导机制**（scripts 如何解析 `app.*` 导入），harness/ 沿用同款；验证 = 收集/import 冒烟（**不烧配额跑全量**，全量留预部署仪式）。
- 引用面同批更新：CLAUDE.md 预部署仪式、`docs/README.md`、PROGRESS、`verification-contracts.md` 等一切 `scripts/chat_scenarios.py` / `scripts/prompt_gate.py` 路径引用。
- **文档升格**：`docs/tasks/verification-contracts.md` 吸收进新家 `docs/VERIFICATION.md`（用例目录 + 合同↔座位登记 + Known Variance），README 信息类型表登记，原文件删除（去历史化律：内容合并进新文档现在时叙事，不留迁移注记）。

## 4. Prohibited Behaviors

- 永不调阈值 / 放松断言让失败通过；prompt_gate 绝对阈值不动。
- 不留注释尸体（注释掉的测试 = 删除）。
- 不搬未审之物：P2 名单不过堂不动手；P3 只搬幸存者。
- 剧本不断言客户端法律（typewriter / remount / 形态机）——服务端真值才进剧本。
- 不顺手修与本批无关的失败/缺陷（登记入 PROGRESS 需求池）。
- 零 schema 变更；零新依赖；`apps/web` 测试位置不动。
- 搬迁后 prompt_gate 必须从新家可收集可导入（冒烟），路径引用零残留。

## 5. harness README 必载律（P3 落）

- **fixture 前缀隔离律**：剧本素材先拷 `scenario/` 前缀（delete_project 会 unlink 外部共享 key）。
- **dev worker 抢跑律**：常驻 worker 会并发执行手工 run——手工验证前后清数据；改 pipeline 代码必须重启 worker。
- **进程卫生律**：`uv run` 包装器 kill 会孤儿 worker——`start_new_session` + `killpg`。
- **配额纪律**：剧本/gate 全量 ≈ 一次小额充值；合并改动后一次跑；探针必须 round-robin（顺序批混杂 provider 漂移）。
- **升编律**：scratch 脚本被任何文档/仪式引用即升编入 harness/。

## 6. 验收标准

- P0 第一闸：用户旅程地图 + 用例目录已向用户完整呈现并获确认；P1 三件套（11 失败裁决表 / 普查退役名单）经用户过堂。
- P2 后纯 pytest 全绿或每座残留红有登记在案的原因与 owner；vitest 100 座不减少绿数。
- P3 后：`scripts/` 只剩运维与 demo 两族；harness/ 从新家可收集可导入；全 repo `scripts/chat_scenarios.py` / `scripts/prompt_gate.py` 旧路径引用零命中；`docs/VERIFICATION.md` 在 README 信息类型表登记。
- 全批 conventional commits，per-commit 自绿，文末署名 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
