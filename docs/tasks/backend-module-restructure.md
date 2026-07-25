# Task: Backend Module Restructure — 目录对准模块图

> **Base branch**: `main`
> **Naming reference**: `docs/NAMING.md`（§7 准入测试；判例 N-05/N-06/N-07）
> **Architecture reference**: `docs/MODULE_ARCHITECTURE.md` §3/§4（模块职责与表归属）
> **Status**: ✅ Implemented（2026-07-25；验收：OpenAPI 60 路径前后一致、uvicorn/worker 启动正常、grep 硬指标零命中）
> **Owner**: TBD

---

## 1. Context

`docs/MODULE_ARCHITECTURE.md` 早已定义六模块边界与表归属，但代码目录没跟上：

- `services/` 是抽屉柜——18 个文件混四个架构层（run graph 内核、队列、确定性工具、业务服务），找"配乐能力"要猜 `music.py` / `music_generation.py` / `brand.py`（判例 N-07）。
- `routers/` 平顶排列 13 个文件，与模块归属无对应关系（判例 N-06）。
- `services/distribution/` 证明模块包是自包含的正确形态——本次重整是把它的示范效应推广到全 backend。
- 即将落地的 registry（CHAT_ARCHITECTURE）、voice_gen/synth_visual（synthetic-talk-video）会新增文件——**先收拾好抽屉，新东西才不会继续往缝里塞**。

**性质：纯搬运重构，零行为变化，URL 契约不动，前端零感知。**

## 2. Target Layout

```
app/
├── main.py                 # 只负责 include 各模块 routes
├── config.py / dependencies.py / worker.py / demo_seed.py
├── metering.py             # 横切：计量
│
├── chat/                   # Agent Interface 模块
│   ├── routes.py           # ← routers/chat.py + routers/intent.py
│   ├── service.py          # ← services/chat.py
│   └── intent.py           # ← agents/intent.py
│
├── pipeline/               # Pipeline 模块（run graph 内核）
│   ├── routes/
│   │   ├── projects.py     # ← routers/projects.py
│   │   ├── assets.py       # ← routers/assets.py
│   │   ├── outputs.py      # ← routers/outputs.py
│   │   ├── music.py        # ← routers/music.py
│   │   └── library.py      # ← routers/library.py（纯读面，就近归 Pipeline）
│   ├── orchestrator.py     # ← services/orchestrator.py（含 compile_graph，见 §4.1）
│   ├── node_runners.py     # ← services/node_runners.py
│   ├── jobs.py             # ← services/jobs.py
│   ├── asset_processing.py # ← services/asset_processing.py
│   ├── clip_spec.py        # ← services/clip_spec.py
│   ├── rendering.py        # ← services/rendering.py
│   ├── outputs.py          # ← services/outputs.py（visible_outputs 等）
│   └── music.py            # ← services/music.py（表 CRUD + seed，见 §4.2）
│
├── skills/                 # LLM 决策单元（现 agents/ 改名，减去 intent.py）
│   ├── base.py / content_director.py / clip_agent.py
│   ├── post.py / quotes.py / carousel.py / article.py
│   ├── reviser.py / persona.py / caption_translate.py
│
├── tools/                  # 确定性执行单元（无 LLM 决策）
│   ├── asr.py              # ← services/asr.py
│   ├── voice.py            # ← services/voice.py
│   ├── extraction.py       # ← services/extraction.py
│   ├── music.py            # ← services/music_generation.py（改名，见 §4.2）
│   ├── caption_translate.py# ← services/caption_translate.py（见 §4.3）
│   └── storage.py          # ← services/storage.py
│
├── memory/                 # Memory 模块
│   ├── routes.py           # ← routers/speakers.py + routers/brand_templates.py
│   └── brand.py            # ← services/brand.py
│
├── distribution/           # ✅ 已就位（services/distribution/ 上移）
│   ├── routes.py           # ← routers/distribution.py
│   └── core.py / channels.py / publishing.py / adapters/
│
├── platform/               # 平台层（MODULE_ARCH §4"暂不属于任何模块"）
│   ├── routes.py           # ← routers/auth.py + routers/files.py + routers/notifications.py
│   ├── auth.py             # ← services/auth.py
│   ├── email.py            # ← services/email.py
│   ├── notifications.py    # ← services/notifications.py
│   └── project_context.py  # ← services/project_context.py（ownership 校验）
│
├── models/  prompts/  clients/   # 不动
└── migrations/                   # 不动
```

**`services/` 与 `agents/` 两个目录整体废除。**

## 3. 依赖纪律（违反 = 重构失败）

1. **依赖方向单向**：`routes → 本模块 service → skills/tools`，下层永不 import 上层。跨模块需要的数据经参数传递或 DB，不经 import。
2. **routes 只 import 本模块的服务**：`pipeline/routes/outputs.py` 不得 import `memory/` 的函数；允许跨模块的读（如 brand 数据）经本模块自己的服务函数做收口。
3. **skills/ 与 tools/ 永远没有 routes**：它们不面对 HTTP。发现给 tool 开 HTTP 端点 = 架构漏洞，立即修。

## 4. 命名审计（借搬运窗口一并执行，NAMING §5）

### 4.1 已定

- **`lower_plan` → `compile_graph`**（判例 N-04）：`orchestrator.py` 定义处 + `create_run` 调用处 + 文档引用（`AGENT_ARCHITECTURE.md` §12、本简报）。

### 4.2 music 双文件拆分（同名不同物）

- `services/music.py`（Music 表 CRUD + seed + in-use 检查）→ `pipeline/music.py`——music 表 owner 本来就是 Pipeline（MODULE_ARCH §4"渲染资产库"），owner 守 owner，§4 登记无需改动；`memory/brand.py` 经它读取，符合"其他模块经 owner 服务函数访问"。
- `services/music_generation.py`（MiniMax 生成 + 持久化）→ `tools/music.py`——确定性生成机械。
- 同名不同层（pipeline/music vs tools/music），沿用 caption_translate 判例：概念同名，层由包位置表达。

### 4.3 caption_translate 同名双文件

- `agents/caption_translate.py`（LLM 翻译）→ `skills/caption_translate.py`（决策单元）。
- `services/caption_translate.py`（轨道编排 + 落库）→ `tools/caption_translate.py`（执行）。
- 同名保留——同一概念的两层，符合 NAMING §1（概念同名，层由包位置表达）。

### 4.4 退役词汇清除

- `services/derivative_dispatch.py`：run graph 后其职责已被 `node_runners` 吸收，残留部分（`_AGENTS` 注册表 + 校验）并入后续 `pipeline/registry.py`（CHAT_ARCHITECTURE）；本重构中**不新建 registry**，只把文件搬进 `pipeline/` 并在文件头标注"待并入 registry"。`derivative` 词汇的最终清除随 registry 落地完成。

### 4.5 显式不改名

- `routers/projects.py` 600 行不拆——归属正确即可，文件瘦身是独立任务。
- `models/` / `prompts/` / `clients/` 不动。

## 5. 执行计划（R1 纪律）

1. **单 commit 纯搬运**：全部文件移动 + import 机械替换 + `main.py` include 更新 + `worker.py` / `demo_seed.py` import 更新。零行为变化，不含任何新代码（registry、chat loop 一律不在本 commit）。
2. **同 commit 内改名仅两个**：`lower_plan` → `compile_graph`；`music_generation.py` → `tools/music.py`（其余 audit 项按 §4 结论执行）。
3. **import 更新清单**（ grep 核实）：`routers/*`（消亡）、`worker.py`、`demo_seed.py`、`agents/*`（消亡）、`services/*`（消亡）、`main.py`。迁移脚本 `migrations/` 若 import app 模块需一并检查。
4. 验收后更新 `MODULE_ARCHITECTURE.md` §3"现状代码"列、`AGENT_ARCHITECTURE.md` §11 critical files、`CLAUDE.md` 相关路径引用。

## 6. 验收

1. `grep -r "app.services\|app.agents\|from services\|from agents" apps/api/app` 零命中。
2. `grep -rn "lower_plan" apps/api docs` 零命中。
3. `uv run uvicorn main:app` 起服务，demo seed 全绿（同 runplan Phase 1 验收口径：run COMPLETED、节点全 done、cost 非空、clip 产物齐备）。
4. 前端手测：composer 生成 → results 步骤清单 → editor 渲染 → library，全链路无回归。
5. 依赖纪律抽查：`skills/`、`tools/` 内零 `from app.pipeline` / `from app.chat` import。

## 7. Prohibited Behaviors

- **禁止**在本重构中加入 registry、chat loop、SSE、voice_gen/synth_visual 等任何新功能代码。
- **禁止**新建 `ai/`、`common/`、`shared/`、`core/`（platform 语义）之外的顶层包（判例 N-05）。
- **禁止**改动任何 URL 路径、请求/响应 schema、表结构。
- **禁止**给 skills/tools 开 HTTP 端点。
- **禁止**拆分 `routers/projects.py`（独立任务）。

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 搬运中漏改 import | grep 硬指标（§6.1/6.2）+ uvicorn 启动即验证 |
| music 归属微调越权 | §4.2 显式标注需先在 MODULE_ARCH §4 登记 |
| demo_seed / worker 隐式依赖旧路径 | §6.3 全绿为验收硬门槛 |
