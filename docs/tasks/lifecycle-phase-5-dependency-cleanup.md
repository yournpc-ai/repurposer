# Lifecycle Phase 5 施工合同——Dependency Cleanup（依赖方向清零：import 图单向）

> 拍板：2026-09-19（用户，Architecture Freeze）。架构合同 = `docs/DECISIONS.md` ADR-087 §6（Dependency Direction）。
> 前置：核心行为稳定（Phase 1~4 全闭环）。
> 范围纪律：**只做依赖方向清理**。不为目录漂亮移动文件；每一次移动必须有依赖方向理由。

## Product goal

1. pipeline→chat 直接 import 全清零（2 顶层 + 6 deferred），改道 trigger 事件缝。
2. 跨模块私有函数 import 清零。
3. import 图单向（冷导入探针可证）；新增代码零 deferred import workaround。

## Current evidence（锚点已核于 Phase 0 HEAD `d0006ac`；行号会漂移，开工前全量 grep 重新定位）

- 顶层反向 import（2 处）：
  - `apps/api/app/pipeline/routes/projects.py:45`（`from app.chat.service import (...)`）；
  - `apps/api/app/pipeline/routes/outputs.py:32`（`from app.chat.service import chat`）。
- deferred import（6 处，开工时 `grep -rn "from app.chat" apps/api/app/pipeline/` 全量定位）。
- 跨模块私有 import（现状违规）：
  - `apps/api/app/chat/plan_turn.py:547`（`from app.pipeline.morph import _check_transform_targets`——同语裁决是 chat 与 pipeline 共用纯函数，应提升为 public application command / explicit protocol 座位）；
  - `_asset_digest` 等（审计点名，开工时 `grep -rn "import _" apps/api/app/ | grep -v test` 全量定位）。
- `agents/contexts.py`：chat 意图上下文与 GenerationContext 同住 agents/——ownership 归属裁定（候选：chat 侧装配归 `chat/`，GenerationContext 留 `agents/`；施工时按依赖方向定，禁新 deferred import）。
- presentation contract 归位残留：Phase 3 收尾核对（`_read_face` / `activity_key` / `THINKING_PHASE_*` 单一座位）。

## Contract changes

- ADR-087 §6 是唯一合同：允许方向 Agent→Tool→Application Command→Domain；Runtime→Events；Events→Projection；Projection→Transport→Presentation。**跨层回溯只能经过 event seam / public application command / explicit protocol。**
- pipeline→chat 的合法缝 = trigger 事件（现役白名单座位：理解完成 / run 终态 fire-and-forget 触发 `trigger_turn.py`——CHAT_ARCH §8.8）；需要扩白名单时走 ADR 级别评审，不走 import。

## Files（预判）

- `apps/api/app/pipeline/routes/projects.py` / `outputs.py`（顶层 import 拆除，改 trigger 事件缝或显式 protocol）。
- deferred import 6 处（同法）。
- `apps/api/app/pipeline/morph.py` / `apps/api/app/chat/plan_turn.py`（`_check_transform_targets` 提升公共座位）。
- `apps/api/app/agents/contexts.py`（ownership 迁移）。

## Tests（Claude 编写，用户自跑）

- **冷导入探针**（验收主依据）：从 `app.pipeline` 各入口冷导入，断言 `app.chat` 不进入 `sys.modules`（及反向）；探针脚本入库（候选 `apps/api/tests/test_import_direction_pure.py` 同款纯套件形态——无 DB 无 LLM）。
- grep 门禁：pipeline 包内 `from app.chat` / `import app.chat` 零命中；跨模块 `import _` 私有函数零命中（模块内私有 import 豁免）。
- 纯 pytest 全量回归 + 剧本 S5 / S7 / S10 / S11 / S20A 保留。

## Migration strategy

逐处改道：每处 import 一个 commit（先立事件缝 / 公共座位，再删 import），冷导入探针每 commit 自绿。`_check_transform_targets` 先提升公共座位（additive），chat 侧改引用，最后删私有路径。

## Rollback strategy

逐处独立 commit，回滚 = revert 对应处。事件缝与 import 并存期无行为变化。

## Acceptance criteria

- import 图单向（冷导入探针可证）。
- pipeline→chat 8 处清零；跨模块私有 import 清零。
- 新增代码零 deferred import workaround（grep `# deferred` / `deferred: import cycle` 注释零新增）。

## Prohibited Behaviors

- 禁止新增 deferred import 来修架构（冻结条款）。
- 禁止为目录漂亮移动文件（每次移动附依赖方向理由，写进 commit message）。
- 禁止顺手改产品语义 / 顺手重构（平移 = 行为零变化）。
- 禁止把 trigger 事件缝扩成事件总线（白名单制，扩名单走 ADR 评审）。
- 禁止本批拆 service.py / schemas.py / graph_fill.py（Phase 6 的事）。

## 收尾报告格式（每 Phase 同律，§十六）

Goal / Current evidence / Contract changes / Files / Tests / Migration strategy / Rollback strategy / Acceptance criteria / Status（日期 + commit 范围 + 验证状态——compileall / import 探针 / tsc / 剧本 = 用户自跑，报告标注「未跑验证」项）。

## Docs update（同批）

- ADR-087 Consequences Phase 5 行回填 + commit 范围。
- `MODULE_ARCHITECTURE.md` §7.1 代码地图同步（contexts 迁移等）。
- PROGRESS §0.2 状态行更新。

## Status

**CLOSED（2026-09-21，branch `worktree-worktree-phase5-deps`，commits `ca98d86`→`d51c9a7` + 本批 docs commit）**

- **Goal 兑现**：pipeline→chat 8 处清零（2 顶层 + 6 deferred）✅；跨模块私有 import 87→0 ✅；import 图单向（冷导入探针实证）✅；零新增 deferred import workaround（标记 71→65）✅。
- **Current evidence → 终态**：`routes/projects.py` 顶层 import 拆除（读走 `platform/conversation_context.py`、写走 `pipeline/conversation_bridge.py`）；`routes/outputs.py` 顶层 import 拆除（regenerate 端点迁 `chat/routes.py`，URL/method/OpenAPI 不变）；deferred 6 处（node_runners×2 / orchestrator / decompile×2 / verify）全改 `trigger_events` / `conversation_bridge` 顶层 import；`_check_transform_targets` 等 32 名扶正公共（sed 全 callsite）；`agents/contexts.py` 裁定落地（`build_context` → `chat/context.py`，`generation_context`/`output_one_liner` 留 agents 扶正）。
- **Contract changes**：ADR-087 §6 无翻案——四族机制皆合同内既有合法缝（event seam / public application command / explicit protocol）；Consequences Phase 5 行已回填。
- **Files**：新增 `pipeline/trigger_events.py` / `pipeline/conversation_bridge.py` / `chat/seams.py` / `chat/context.py` / `platform/conversation_context.py`；改动见 commit 列（`ca98d86` 事件缝 → `624d664` 会话桥 → `a4adee2` 只读座 → `e5d5368` agents 扶正 → `d5f9ec4` regenerate 迁座 → `9b0568a` build_context 迁座 → `8a10069`/`e312add`/`79796db`/`717ca2a` 四批扶正 → `e43bc57` 探针入库 → `d51c9a7` 修复批）。
- **Tests**：`tests/test_import_direction_pure.py` 五牙 6 例 green from birth（AST 双门 + 冷导入双子进程探针 + 组合根接线保险 + 牙⑤改名碰撞扫描）；`test_trigger_turn_pure` / `test_execution_fencing_pure` 跟随改引用；纯 pytest 358 绿。
- **Migration strategy 执行**：每处独立 commit（先立缝/座，再删 import），冷导入探针每 commit 自绿——探针最后入库但四牙对全历史成立（终态全绿）。
- **Rollback strategy**：逐 commit revert 即可；缝与 import 并存期无行为变化（fire-and-forget 未注册 = 静默降级，bridge 未注册 fail-loudly——组合根接线由探针牙④锁死）。
- **Acceptance criteria**：import 图单向 ✅（探针牙③双向实证）；8 处清零 ✅；跨模块私有 import 清零 ✅（模块内豁免）；零新增 deferred workaround ✅。
- **验证状态**：compileall OK ✅ / 纯 pytest 358 绿 ✅ / check_gates OK ✅ / 零 prompt 改动声明（`app/prompts/` 与 `chat/prompts.py` 零 diff，prompt_gate 豁免）✅ / 剧本座全绿 ✅（S1/S5/S6/S7/S10/S11/S17 首跑即绿；S16/S20 复跑取证猎得两真 bug——`_generation_context` 扶正撞同名局部变量三处 `x = x(...)` 自引用（S16 P2 plan 节点实红）+ scripts/ 旧名残留两处（S20 种子 ImportError）——修复批 `d51c9a7` + 探针牙⑤常驻后全绿；S20A 首跑红 = 披露措辞未匹配，verification-contracts §4 KNOWN VERIFICATION FRAGILITY 正则语序洞在册座，复跑即绿）/ tsc = 零前端改动不涉及。
