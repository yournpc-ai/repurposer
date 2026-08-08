# Persona Identity —— 身份模块重设计（改名 + 字段 + 吸收 Brand + 触点）

> Status: Active（2026-08-08 立项）
> 依据：ADR-037（Speaker→人设正名）/ ADR-038（人设吸收 Brand）/ NAMING N-27、N-28 / STRATEGY §2.2 叙事分层
> 排期：**插入周 08-09~08-14，最高优先级**（2026-08-08 拍板，两刀连续落地；闭环链顺延 1 周）→ W8 一 09-21（门禁 v2）

## 1. 背景与目标

定位升级后，Speaker（演讲者）命名三重断裂（ADR-037 Context）；Brand 拆分理由被多人设反转（ADR-038 Context）。本简报把两个 ADR 落成一次实施：**人设（Persona）成为唯一身份对象**——身份卡 + 风格 + 策略 + 声音 + 皮肤，一个页面、一个 composer 控件、一个代码词。

**设计前提**：人设不是目的地，是维修点——用户主触点在 composer（人设块），人设页只在"产物不像我"时被需要（三个入口：composer 块 hover 摘要 / chat identity echo 链接 / 结果页"不像我"）。

## 2. 终态 schema（`personas` 表）

| 分区 | 字段 | 说明 |
|---|---|---|
| 身份卡 | `id` / `user_id` / `name` / `title?` / `avatar_url?` / `language` | 多实例扁平（工作号/生活号 = 两行人设） |
| 风格块 | `core_values` / `favorite_metaphors` / `sentence_style` / `emotional_tone` / `typical_hooks` / `avoid_words` | 现状六件平移；`emotional_tone` String + 注册表校验（§5） |
| 策略块 | `audience?` / `guidelines?` / `cta?` | **CTA 唯一家**；旧 `voice` 文本列删除（文风并入 `guidelines`）——`voice` 归还唯一合法含义 |
| 声音块 | `voice` JSONB NULL | `{"kind":"cloned","voice_id","sample_asset_id"}` \| `{"kind":"stock","stock_id"}` \| NULL = Auto |
| 皮肤块 | `brand` JSONB NULL | caption 字体/字号/颜色/位置/preset、title 开关+位置、片头尾卡、logo、keyword_highlighter；NULL = 系统默认皮肤。**`brand` 全栈一词**（人设块 / 烘焙 / clip-spec 段同名），模块退役词不退役 |
| 来源与校准 | `learned_from` JSONB NULL / `calibrated_at` ts NULL / `auto_created_at` ts NULL | "它从哪学的" / 最近校准 / 系统 bootstrap 标记（替代 is_default 布尔，§4） |
| 审计 | `created_at` / `updated_at` | — |

**brand_templates 退役，config 三分流**：皮肤字段 → `persona.brand`；工艺开关（`removeFiller` / `captionEnabled` / `aspect` / `fillMode` / 音乐默认）→ 配方注册表 / 任务书默认，**不进人设**；`language_tone` 不单列（风格六件覆盖）。

**引用平移**：`projects.speaker_id` / `assets.speaker_id` → `persona_id`；`projects.brand_template_id` 退役；composer payload 双字段 → 单 `persona_id`；`GenerationContext.brand` ← `persona.brand`；`memory/brand.py` 烘焙改读人设（模块名不动）；**clip-spec `brand` 段不动**。

**默认人设解析链**：项目挂载 > composer 显式选择 > `auto_created_at` 非空 > 最早创建。

**STOCK_VOICES**：代码内静态注册表（id / 名 / 风格标签 / 语言覆盖 / 试听 URL / provider voice_id），不建表。

## 3. 实施两刀（插入周连续落地）

**第一刀（08-09，纯机械）**：全栈改名迁移
- Alembic：`speakers`→`personas`、两 FK 平移
- `SpeakerContext`→`PersonaContext`、schemas / `memory/routes.py` `/personas` / `skills/persona.py`
- 前端 `_app.speakers.*` → `_app.personas.*`、i18n `speakers.*`/`speakerDetail.*` → `personas.*`、composer 人设块
- MODULE_ARCHITECTURE / AGENT_ARCHITECTURE 同步 + NAMING §2 词汇表登记「人设 / Persona」

**第二刀（08-10 ~ 08-13，吸收 + 显化 + 触点）**：
- 08-10：新五列 + `brand` 块 + brand_templates 退役 + config 三分流 + composer Brand pill 退役 + 烘焙改读 + 启动种子模板退役
- 08-11：`voice` 缓存落地（dub 改读人设声纹，克隆一次跨项目复用）+ `STOCK_VOICES` 注册表 + 试听 + 声纹优先级链
- 08-12：人设页五分区（身份/风格含来源说明/策略/声音/皮肤含实时预览）；`/brand-template` 重定向并入；sidebar 收敛单「人设」项
- 08-13：触点入口（composer 人设块 hover 三行摘要 / identity echo 变链接）+ 本人含量门禁 v1（非本人素材不提取人设）+ 全链路回归
- 门禁 v2（W8 一 09-21，`speaker_map` 过滤只从本人段落学）

## 4. 验收口径（用户视角）

1. composer 只剩一个身份控件「人设」（值 = Auto / 人设名），底排无 Brand pill；
2. 人设页一页收齐"它眼中的你"：风格、受众与边界、声音（可试听）、皮肤（改字体颜色实时预览）；每个字段可见"它是从哪学的"；
3. 新建"生活号"人设 = 一页建全（风格/声音/皮肤各自独立），产物互不串味；
4. 克隆过的声音换项目直接复用，不重新克隆；没录过声音选系统音色也能出片；
5. 上传一场多人会议，人设不被与会者风格污染（门禁 v1）。

## 5. Prohibited Behaviors

- **禁**保留 `speaker` 指代用户身份的任何残留（表/字段/端点/i18n/文案）——`speaker` 只指素材里说话的人（NAMING N-27）；
- **禁**把工艺开关（removeFiller / captionEnabled / aspect / fillMode / 音乐默认）塞进 `personas`——它们的家在配方/任务书；
- **禁**为系统音色建表或伪装成人设行——`STOCK_VOICES` 只住代码注册表；
- **禁**改 clip-spec `brand` 段名（渲染黑盒契约，ADR-016）；**禁**引入 `look` 作为字段/块名（`brand` 全栈一词；look 层是 RECIPES §4.4 的组合概念，不撞名）；
- **禁**加 `is_default` 布尔（`auto_created_at` 可空时间戳替代，§4）；
- **禁** composer 出现第二个身份控件（皮肤随人设，配方 look 覆盖是 run 级，不是 composer 控件）；
- **禁**在用户可见文案中使用 "IP"（en）/ influencer / creator 称呼用户（CLAUDE.md copy doctrine 体面框架）；
- 词汇表登记、架构文档同步是第一刀的**完工定义**的一部分，不许"代码改了文档后补"。

## 6. 消费面全审计与迁移地图（2026-08-08 逐点核实）

**渲染链（契约不动，解析改道）**
- clip-spec `brand` 段 / Remotion 渲染服务 / `packages/clip`：**零改动**（ADR-016 黑盒）。
- `memory/brand.py`：烘焙改读 `persona.brand`；`DEFAULT_BRAND_CONFIG` 保留为"系统默认皮肤"（`brand` NULL 时回落）；**`seed_default_brand_template` 退役**——启动不再种子模板，用户首次编辑皮肤才写块（减法）。
- `node_runners._resolve_brand`：改经 `run.context.persona_id` → `project.persona_id` 取 `persona.brand`；历史 run context 里的 `brand_template_id` 键**读取忽略**（重跑回落人设皮肤，读容忍一次写清，不迁移历史 JSON）。
- 音乐默认链修正：`music_id → mood → persona.brand.musicId/musicMood → "calm"`；现状挂在 `project.speaker_id is not None` 上的怪 gate 顺势改挂 `persona_id`。

**DAG / agent loop**
- `persona_bootstrap` 节点（type 字符串不动，历史 `workflow_steps` 零迁移）：写 Persona 行（auto label 由 PersonaAgent 生成，fallback "Auto Persona"）、`project.persona_id` 挂载、素材挂 `assets.persona_id`；加**本人含量门禁**（v1 LLM 判本人素材 / v2 `speaker_map` 过滤）。
- `project_context.speaker_context_from_row` → `persona_context_from_row`；`GenerationContext.speaker` → `persona: PersonaContext`。
- 9 个 j2 模板的 speaker 变量 → persona（`quotes / caption_translate / reviser / article / carousel / director_plan / clip_agent / persona / post`）；纯度纪律不变（understand 禁注 persona）。
- `dubbing.py`：声纹优先级改为 **persona.voice（cloned 缓存）→ 项目 VOICE_SAMPLE → AUDIO > VIDEO → 系统默认音色**；`_speaker_style_hint` → `_persona_style_hint`。

**chat / 配方**
- `ChatRequest.brand_template_id` → `persona_id`（schemas:436）；`PendingIntent.brand_template_id` → `persona_id`（:737，不 clobber 逻辑平移，chat/service.py 三处）；`GenerateRequest.brand_template_id` 退役（:1564，经 persona 解析）；orchestrator ctx 键同步。
- RECIPE_REGISTRY **零改动**（无 brand/speaker 字段）；`RecipeInspectOverlay.brandTemplateId` 预填 → `personaId`；`useProjectLaunch` payload 同步。
- identity echo：i18n `identitySpeakerAuto` → `identityPersonaAuto`；echo 值 = 人设名（+auto 标），W7 变链接进人设页。

**前端**
- `_app.speakers.*`（3 文件）→ `_app.personas.*`；`_app.brand-template.tsx` → 人设页皮肤分区（第二刀）；`SpeakerPickerModal` → `PersonaPickerModal`（+系统音色区）；HomeComposer 人设块 + Brand pill 退役；app-sidebar 两项收敛单「人设」；GenerationOverlay / projects / clips 页 / `types.ts` / `chat-stream.ts` 平移。
- i18n：`speakers.*` / `speakerDetail.*` → `personas.*` / `personaDetail.*`；`brandTemplate.*` → 人设页皮肤分区键（第二刀）；en 源语言先行，zh 镜像（TS 类型守门）。

**种子 / 脚本 / 运维**
- `main.py`：seed 调用与 `brand_templates_router` / `speakers_router` 注册退役，挂 `/api/v1/personas`。
- `reset_db.py` docstring 与 CLAUDE.md「Database Reset」节（"re-seeds the default brand template"）更新为"无需种子：brand NULL = 系统默认皮肤"。
- `scripts/chat_scenarios.py` 里 brand 引用平移（harness 不断言旧键）。

**数据迁移（Alembic 一次，第二刀）**
1. `speakers` → `personas` 表改名；`projects.speaker_id` / `assets.speaker_id` → `persona_id`（PG RENAME COLUMN 自动带约束，`ck_asset_owner_set` 名保留）。
2. 加列：`voice` JSONB / `brand` JSONB / `learned_from` JSONB / `calibrated_at` / `auto_created_at`（存量回填 NULL）。
3. 旧 `voice` 文本：有值行追加进 `guidelines` 末尾，然后删列。
4. `brand_templates`：每用户最新模板的**皮肤键** → 该用户人设的 `brand` 块；工艺/格式键（removeFiller/captionEnabled/aspect/fillMode/音乐默认）**不迁**（由配方/任务书默认吸收）；删表。
5. `projects.brand_template_id` 删列。
6. 历史 `workflow_runs.context` / `pending_intent` JSON：不动数据，读取侧容忍（见渲染链条目）。

## 7. 命名终审（第二轮，全设计过筛）

| 词 | 裁决 | 理由 |
|---|---|---|
| `voice`（JSONB 块） | ✅ 采用 | 词归还音频本义；废 `voice_ref`（`_ref` 行话后缀，§6）；`audio` 否（媒介词，误导） |
| `brand`（JSONB 块） | ✅ 采用 | 全栈一词（块/烘焙/clip-spec 段）；模块退役词不退役；不造 `look`（撞 RECIPES §4.4 look 层） |
| `learned_from` | ✅ 采用 | 废 `bootstrapped_from`（行话）；`bootstrap` 只留节点名 `persona_bootstrap`（冷启动事件 ≠ 来源账，两个概念两个词，且节点 type 字符串有历史数据不动） |
| `calibrated_at` / `auto_created_at` | ✅ 通过 | 可空时间戳纪律（§4），词义直白 |
| `STOCK_VOICES` | ✅ 通过 | "stock voice / 系统音色"已在 RECIPES 命名登记清单注册 |
| `persona` / `PersonaContext` / `/personas` / `PersonaPickerModal` / `personas.*` i18n | ✅ 通过 | 三层同词族（N-27） |
| `title`（人设头衔） | ✅ 保留 | 与"标题"的歧义在 personas 上下文内不成立；LinkedIn headline 语义 |
| `cta` / `typical_hooks` | ✅ 保留 | 已注册行业词（CTA 全库唯一家） |
| fallback 字符串 "Auto Speaker" | 改 "Auto Persona" | 数据内残留清扫 |
| 本人含量门禁 | 不作命名实体 | 描述性短语，机制 = persona skill 判定规则，不开新词 |
