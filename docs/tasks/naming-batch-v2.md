# 命名对齐批 v2 + 默认指令包最小切片 — 动工简报

> Status: 已拍板（2026-08-21 累计拍板：N-42 全量对齐方向、彻底换删零容忍 shim、存量数据全清、批⑥ providers/llm、指令包切片必做）。
> 判例：NAMING N-40/N-41/N-42；证据：`research/agent-skills-spec.md`；排期：PROGRESS 需求池两行（命名批 v2 / 指令包切片）。
> 本简报 = 施工清单 + 验收标准；不动本简报外的架构（四层地图 / 图调用主权 / 打勾流 / 报价=fold / 校验=∀ 一字不碰）。

## Prohibited Behaviors（禁令）

1. **禁留任何旧名 shim/alias**：`SkillEntry` / `SkillRejected` / `dispatchable_skills` / `app/skills/`（能力包）/ `app/tools/`（机械库）/ `clients/` / `roster.py` / `checkpoint`（kind）——换完即删，grep 清零（数据值与历史文档除外）。
2. **禁动节点 kind 字符串**（`dub_clip` 等）与 **UI 用户文案**（营销「技能」原样保留，N-42 豁免）。
3. **禁数据迁移 shim**：存量全清（`reset_db.py`），alembic 只走 schema；不写任何旧格式兼容读。
4. **指令包禁 runtime discovery**：消费只走装配期注入（声明 packs → 装配器织入），模型永不决定何时加载；禁 skill tools 三件套形态。
5. **prompt 措辞翻车只回退模型面**：零假设测试不过 → 只回 `{"skill"}` 字段与目录措辞（词汇表加行「模型面更名未过闸」），代码改名全部保留，整批不回退。
6. **指令包首包禁创作**：`linkedin-longform` 内容 = write_post 内嵌 prompt **逐字节平移**，一字不增删——本切片是架构验证不是内容迭代。
7. 改 pipeline 代码必重启常驻 worker（常备纪律）；禁 FastAPI BackgroundTasks。

## 施工项（六项更名 + 一项切片，各一个 conventional commit）

### ① checkpoint → interrupt（N-40）
- 节点 kind 字符串、`expire_stale_checkpoints` 函数族、`dock_checkpoint_question` 等引用面；alembic schema 迁移（不定数据——全清）。
- 机制词不动：`Suspend` 异常 / `waiting` 状态 / `answer`（N-19/N-54 不变）。

### ② roster.py → registry.py（N-41）
- `agents/roster.py` → `agents/registry.py` + import 面；「花名册」散文词可留。

### ③ skills → tools 换位（N-42 主体）
- `app/skills/`（12 能力包）→ `app/tools/`；`SKILL_REGISTRY` → `TOOL_REGISTRY`；`SkillEntry`→`ToolEntry`、`SkillRejected`→`ToolRejected`、`dispatchable_skills`→`dispatchable_tools`。
- `TaskItem.skill` → `tool`（schemas + 全部生产/消费点）。
- **模型面**：`chat/intent.py` 的 `{"skill"}` 字段 + 散文全换（"Available skills:" / "invent skills" / "the skill chain"… 15+ 处）。
- **消费端重组**（答录校验终案）：plan/intent 数百行散文抽出 → `chat/prompts.py`（Mastra instructions.md 式同址抽取）；目录序列化裂脑修复——`dispatchable_skills()` + `_plan_skill_lines()` 合并为 `tools/__init__` 的 `tool_catalog_lines()`（注册表自投影），chat 只消费。
- 前端 i18n `skills:` 命名空间 → `tools:`（en/zh + 消费方）。
- **零假设测试**：先 stash 对照跑（基线 = 改名前 prompt 快照 + 剧本基线），翻车按禁令 5。

### ④ tools → providers 拆分 + 通用件归位
- `providers/`：`asr.py` / `voice.py` / `vision.py`（+`weights/`）/ `storage.py`。
- 通用件随消费方：`dubbing.py` → `tools/dub/` 包内；`filler.py` → `tools/filler/` 包内；`transcript.py` / `extraction.py` / `music.py` → 动工时按 import 图定（transcript = clips/装配侧，extraction = preprocess 侧，music = 音乐库消费侧；归位表随 commit 落）。
- 判别规则：providers/ = 有真外部服务或引擎的包装；纯函数机械随唯一消费方进包。
- **门禁迁址**：`providers/` 与确定性工具包禁 import agents/、禁 import LLM 决策层（grep 门禁，N-29 铁律新址）。

### ⑤ NAMING 词汇表重写（✅ 已落文档层，本批只去核「更名中」注记）

### ⑥ clients/ → providers/llm/（批⑥）
- `clients/minimax.py`（含 `PRICING` + `price_units`/`price_tokens`）→ `providers/llm/minimax.py`；import 面 + AGENT_ARCH 引用（已落档处仅核）。「client」模块名退役；`app/models/` 不动（DB schema 家）。

### ⑦ 默认指令包最小切片（架构验证，P1）
- **格式**：`app/skills/<pack-name>/SKILL.md`，frontmatter 六键（Agno 规范：`name`/`description`/`license`/`compatibility`/`allowed-tools`/`metadata{version,author,tags}`）；`name` 与目录同名、lowercase-hyphen ≤64。
- **loader + 注册表**：`skills/__init__.py` 扫目录 → 校验（frontmatter/同名/键白名单）→ **SKILL_REGISTRY**（行业本义重生）；启动即校验（SkillValidationError 先例精神）。
- **首包**：`app/skills/linkedin-longform/SKILL.md` ← write_post 内嵌 prompt 逐字节平移（禁令 6）。
- **消费**：agent 声明增 `packs: list[str]` 字段；装配器（`agents/contexts.py`）按声明把 pack 正文织入 prompt；write_post 声明 `packs=["linkedin-longform"]`。
- **覆盖**：name-wins 整包替换（loader 后载压前载；persona 级 loader 下批，本批只平台级）。
- **验收**：零假设——平移前后 write_post 产物等价（同素材同 seed 对照）；S 剧本回归。

## 验证（全批总验收）

1. `git stash` 零假设基线（③模型面 + ⑦切片各一轮对照）。
2. S1–S46 剧本 harness 全跑绿；手工 create_run 真链（含 write_post 产物对照）。
3. 启动自检（runner 注册一致性 + 节点→agent 引用 + 配方 flow 对账）+ 注册表自检（TOOL_REGISTRY / SKILL_REGISTRY 双表）。
4. grep 门禁：无残留旧名（禁令 1 清单）；`providers/` 无 agents/LLM 决策层 import。
5. `reset_db.py --yes` + 常驻 worker 重启 + dev 全链走查（composer → chat → 任务书 → run → 产物）。

## 提交策略

六项更名 + 切片各一个 conventional commit，main 顺序落；⑦ 依赖 ③（座位先空出）。每 commit 过对应项的 grep 门禁 + 快回归，全批过完总验收。
