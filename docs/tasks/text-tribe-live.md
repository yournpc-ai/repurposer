# 配方文本族三卡点亮施工简报（text-tribe-live）

> Status: 已拍板即施工（2026-08-24 用户拍板，PROGRESS 同日行；本日落齐画廊 v2 八卡齐亮最后 3 个卡位）
>
> 母决策：`docs/RECIPES.md` §4.6（文本族三卡承诺句 + 闸门②环路价值豁免）+ ADR-048 §7.3（证据层移交 overlay = 准入验收闸）+ RECIPES §10（Soon/reserved 形态退役） + 命名批 v2（skill/tool 拆家：skill = 装配期指令包，tool = NodeBase 节点）。
>
> 卡面文案唯一事实源：`apps/web/src/lib/i18n/locales/{en,zh}.ts` 的 `recipes.{id}.*` 块；en 源 zh 镜像。
> 卡面 / overlay 形态：`docs/tasks/recipe-gallery-v2.md`（Phase B 已落注册表字段 + i18n 全套，本批只补输出键 + example_outputs 填充 + 状态翻 live）。
>
> 本文只管施工：改动点、分期、验收、禁令。设计论证不复述——查 RECIPES §4.6 / ADR-048。

---

## 1. 背景一句话

画廊 v2 八卡阵容（ADR-048）已就 5 卡 live，3 卡 reserved 占位（social-post / quote-cards / carousel），占位因缺真实成对示例可烘焙 + 缺 Skill 指令包（quote-cards / carousel 现状**裸奔**——writer agent 全靠系统 prompt，无领域知识注入）。今日收口 4 刀：补齐 2 个 Skill 包（命名批 v2 纪律）→ 真管线烘焙 → 注册表翻 live + 填产物 URL → 验收闸 12/12。

## 2. 已核实事实（动工前复核，勿凭记忆）

- **后端 tool 链 100% 就位**（ADR-039 P2 落地形态）：
  - `tools/posts/node.py::WritePost(kind="write_post", output_type="post")` — 继承 `pipeline/derivative_dispatch.DerivativeWriterNode`
  - `tools/quotes/node.py::WriteQuotes(kind="write_quotes", output_type="quotes", images_per_run=1)` — 同源
  - `tools/carousel/node.py::WriteCarousel(kind="write_carousel", output_type="carousel")` — 同源
  - `models/schemas.py::Post / Quotes / CarouselResponse` 输出 schema 齐
  - `DerivativeType.{POST,QUOTES,CAROUSEL,ARTICLE}` 全部登记
- **Skill 现状**：
  - `skills/linkedin-longform/SKILL.md` 已挂 `write_post`（✅ 完备）
  - `skills/quote-cards/`、`skills/carousel/` —— **不存在**（quote-cards / carousel **裸奔**）
  - `skills/stills-editing-craft/SKILL.md` —— image-video 卡用，与本批无关
- **注册表**（`apps/api/app/pipeline/recipes.py:449-517`）：三卡 `status="reserved"`，`tasks=[...]` + `flow=[...]` 已挂，`example_outputs=[]` 空，example_assets 全指向 `demo/uploads/demo-article.md`
- **demo 源**：`demo/uploads/demo-article.md` 已在 TOS 桶（image-video 卡复用同源），reset_db 保护区
- **demo 烘焙先例脚本**（必读）：
  - `scripts/bake_dub_contrast.py`（170 行）—— translate+render+harvest 范式
  - `scripts/bake_reframe_demos.py`（300 行）—— 真管线 `create_run` + 收割
  - `scripts/bake_image_video_demo.py` —— 同上简化版
  - `scripts/bake_subs_contrast.py` —— harvest 模式抽象
- **Agent 装配期 packs 机制**（`agents/base.py:170-173`，命名批 v2 落地）：
  - `Agent` 类有 `packs: list[str]` 字段
  - `pack_instructions(packs)` 多包空行分隔合并进系统 prompt
  - SKILL.md frontmatter 启动期 eager validate（畸形包启动炸，`app/skills/__init__.py:_parse_skill_md`）
  - **运行时不读文件**——改 packs 字段必须重启 worker
- **验收闸**：`apps/api/scripts/accept_prompt_surface.py`（08-20 双子卡 12/12 先例）
- **i18n 输出键现状**：zh.ts:436-447 已挂 `demo_article / reframe_output / follow_output / image_video_preview / subs_en / subs_zh_bilingual / subs_fr / dub_es` 共 8 键——本批需加 `post_output / quotes_output / carousel_output` 3 键

## 3. 设计决策索引（全部已定，施工照做勿再开题）

| # | 决策 | 出处 |
|---|---|---|
| D1 | 文本族三卡 status `reserved` → `live`，无中间态（RECIPES §10 退役 Soon） | ADR-048 §7.3 |
| D2 | 三卡 evidence 层 = overlay 示例 tab 真实成对示例；`example_outputs` 填真管线 harvest 出来的 content-hash URL | ADR-048 §7.3，RECIPES §4.8 |
| D3 | Skill 包纪律（命名批 v2）：writer agent 全挂 `packs=[...]`，装配期唯一注入形态，运行时不读文件；前 Agno 六键 frontmatter 白名单 | NAMING N-42，`app/skills/__init__.py:_FRONTMATTER_KEYS` |
| D4 | 三卡共用 `DerivativeWriterNode` 体（ADR-043 outputs-derive 形态）；节点层零改动，本批不改 pipeline | `pipeline/derivative_dispatch.py:85` |
| D5 | quote-cards 输出形态 = `Quotes` payload（JSON）+ 1 张 PNG 副产物（`_save_quote_card_image`，落 `output.files.image`）；carousel 输出 = `CarouselResponse` payload 纯 JSON，无视频渲染 | `tools/quotes/node.py:images_per_run=1` |
| D6 | 烘焙配额上限：MiniMax ~3 LLM 调用（每卡 1 次 writer call；quote-cards 多 1 次 image gen）+ 0 渲染 + TOS ~6 对象 | 配额预算同 RECIPES §4.6 |
| D7 | i18n 严守双端对齐：`en` 是源，`zh: Resources` 类型抓漏键 | CLAUDE.md i18n 节 |
| D8 | recipe `flow` 字段只声明 writer 一步（director 二件套是上游基础设施自动消费）；本批不动 flow | recipes.py:468/488/507 |
| D9 | 验收闸扩展形态：3 卡 × 双语 × 2 试 = 12 断言；命中节点 kind 唯一（不串味） | recipe-gallery-v2.md §B.4 |

## 4. 改动点（4 刀，按顺序施工）

### 刀 0：Skill 包补齐（命名批 v2 纪律：**禁裸奔**）

1. **新建 `apps/api/app/skills/quote-cards/SKILL.md`** —— Agno 六键 frontmatter（`name: quote-cards` 与目录同名 / `description` ≤1024 / `compatibility` ≤500 / `allowed-tools: [write_quotes]` / `metadata` 含 `version + author + tags` / `license: Proprietary`）+ markdown body 工艺约定（**自包含性** = 脱离上下文也成立 / **单条长度** ≤200 字 / **attribution** 必填且 speaker + 上下文锚 / **钩子优先排序** / **修辞多样性** 4 张至少覆盖 3 种 / **人设保真** / 配图层责任交接）。
2. **新建 `apps/api/app/skills/carousel/SKILL.md`** —— frontmatter 同款（`name: carousel` / `allowed-tools: [write_carousel]`）+ body（**三段骨架** = 封面钩子 / 正文递进 / 收束 CTA / **封面纪律** ≤8 词 + 4 形态 / **正文一要点一张** / **论证链路** 而非时间序 / **CTA 四选一** 拒绝"谢谢观看" / **张数甜区** 6 张 / 视觉一致交接图像层）。
3. **接线 `apps/api/app/tools/quotes/agents.py::quotes_writer`** —— Agent 声明加 `packs=["quote-cards"]`，头部 docstring 注明 pack 来源。
4. **接线 `apps/api/app/tools/carousel/agents.py::carousel_writer`** —— Agent 声明加 `packs=["carousel"]`，头部 docstring 注明。
5. **启动闸零报警**：`uv run python -c "from app.skills import SKILL_REGISTRY; print(sorted(SKILL_REGISTRY.keys()))"` 必须输出 4 键 `['carousel', 'linkedin-longform', 'quote-cards', 'stills-editing-craft']`，缺键即 SKILL.md 校验失败。

### 刀 1：烘焙脚本 `apps/api/scripts/bake_text_tribe_demos.py`

模型：`bake_reframe_demos.py`（真管线 `create_run` 模式）+ `bake_subs_contrast.py`（harvest 模式）。入口：

```bash
uv run python scripts/bake_text_tribe_demos.py social-post
uv run python scripts/bake_text_tribe_demos.py quote-cards
uv run python scripts/bake_text_tribe_demos.py carousel
uv run python scripts/bake_text_tribe_demos.py all
uv run python scripts/bake_text_tribe_demos.py social-post --harvest <project_id>  # 抢救
```

核心 8 步（每张卡统一）：

1. 落 `User(BAKE_EMAIL)`（一次性，无则建）—— 与 `bake_reframe_demos.py:72-79` 同款
2. 建 `Project` + `Asset(demo-article.md)` TOS 对象引用 + 默认 `Persona`（无 voice_clone / 默认皮肤）
3. 调 `orchestrator.create_run(project_id, tasks=[…])`，task list 抄自 recipes.py 注册表
4. 轮询 `WorkflowStep` status，跑到全部 done（worker 真跑 LLM）
5. 取最新 `Output(type=…)` 行的 payload
6. SHA256 → 头 8 位 → 写 `demo/outputs/<key>-<hash>.json`
7. quote-cards 多一步：`output.files.image` 已是 PNG → 同模式 harvest
8. print 3 条 content-hash URL（让注册表填入 step 2）

**前置**：worker 必须重启（刀 0 装 pack 是 Agent 启动期装配）—— `./dev.sh` 重启那步。

### 刀 2：注册表 + i18n 三连

**`apps/api/app/pipeline/recipes.py`** —— 三卡各改 2 字段：
```python
"social-post": RecipeEntry(
    status="live",  # ← "reserved" → "live"
    ...
    example_outputs=[
        ExampleOutput(
            kind="image",  # kind 按 schema 实际接受值（image / video）；JSON payload 通常归 image 预览
            url=f"{_DEMO}/outputs/post-{hash}.json",
            poster_url=None,
            label_key="post_output",
        ),
    ],
),
```
quote-cards / carousel 同款。

**`apps/web/src/lib/i18n/locales/zh.ts`** —— `materials` 命名空间（line 436-447 旁）加 3 键：
```ts
post_output: "帖子样例",
quotes_output: "金句卡样例",
carousel_output: "轮播样例",
```

**`apps/web/src/lib/i18n/locales/en.ts`** —— 镜像：
```ts
post_output: "Post example",
quotes_output: "Quote cards example",
carousel_output: "Carousel example",
```

### 刀 3：验收闸 12/12

**`apps/api/scripts/accept_prompt_surface.py`** —— CARDS 表补 3 行 × 2 语言 × 2 试 = 12 断言。断言形态（仿 08-20 双子卡 12/12）：
- `social-post` promptTemplate → 命中 `write_post`（**不**串到 `write_article` / `write_quotes`）
- `quote-cards` promptTemplate → 命中 `write_quotes`，`count=4` 保留
- `carousel` promptTemplate → 命中 `write_carousel`，`count=6` 保留
- 双语（en/zh）各 1 试
- 输入槽类型 `transcript` 通过（deck-only 不卡）
- 不串味到 `write_post` / `dub_clip` 等其他节点
- locale 真串漂移断言自动生效（recipe-gallery-v2.md §B.4 先例）

## 5. 验收清单

- [ ] SKILL_REGISTRY 4 键全在（`quote-cards` + `carousel` 新增），启动零报警
- [ ] `quotes_writer.packs == ['quote-cards']` / `carousel_writer.packs == ['carousel']`
- [ ] `bake_text_tribe_demos.py all` 跑完：TOS 上 3 条 content-hash 产物 + 金句卡 1 张 PNG
- [ ] `recipes.py` 三卡 `status="live"`，`example_outputs` URL 全部填入
- [ ] i18n zh.ts + en.ts `materials.post_output / quotes_output / carousel_output` 双端齐
- [ ] `npx tsc --noEmit`（web）+ `uv run python -m compileall apps/api` 绿
- [ ] `accept_prompt_surface.py` 12/12 全绿
- [ ] 主页 home (`localhost:3000/home`) 8 卡全亮，Soon pill 全消，无 reserved 占位
- [ ] dev DB 按 FK 序清理 bake scaffolding（项目 + 资产 + 人设 + User 行）—— `bake_reframe_demos.py` 的 FK cleanup 模式照抄
- [ ] 双主题截图：light / dark 下 8 卡封面 token 反相正常（继承画廊 v2 验收）

## 6. Prohibited Behaviors

- **禁裸奔**（命名批 v2 纪律）：quote-cards / carousel writer agent 不接 `packs=[...]` 上线 = 工单不收口；不要"先点亮再补 skill"——skill 与 status 翻 live 同步落档。
- **禁走 `reserved` 中间态**（ADR-048 §7.3）：占位形态退役；status=`"live"` 当且仅当 example_outputs + packs + 验收闸全齐。
- **禁跑批污染 dev 库**（08-20 教训）：常驻 worker 抢跑手工 create_run，scaffolding 验后必须 FK 序清；不要图省事留 demo 项目。
- **禁 pipeline 代码动**（D4）：刀 0-3 不改 `pipeline/derivative_dispatch.py` / `pipeline/recipes.py` 的字段定义层（只改 status + example_outputs 填充）；改了 = 触发 worker 重启 + 验收闸全重跑。
- **禁手工改 SKILL.md frontmatter 跳过 Agno 六键白名单**：`app/skills/__init__.py:_FRONTMATTER_KEYS` 是硬约束；`name != path.parent.name` / `description > 1024` / `compatibility > 500` / 空 body 任意一条 = 启动炸。
- **禁 i18n 只写一端**：en 是源，zh 镜像；`zh: Resources` 类型抓漏键（CLAUDE.md i18n 节）。
- **禁 example_outputs 填本地 URL / 临时桶 URL**：必须 content-hash 入 `demo/` 前缀（reset_db 保护区），且 URL 与 `scripts/upload_recipe_assets.py` 跑出来的 manifest 一致。
- **禁豁免验收闸**：刀 3 12/12 全绿是 status 翻 live 的最后一道闸；不允许"先合再说"。
- **禁与声纹克隆 / R5 管线 / 运营端批次混排**：本批仅触达 recipes.py（数据）+ skills/（指令包）+ scripts/（烘焙 + 验收）；其他模块零修改。
- **禁复用 `bake_image_video_demo.py` 的 select_clips 路径**（图像视频卡才有）：文本族链路无 `select_clips`，照搬会撞 422。
- 禁卡片 id / 模板文案改动（i18n 节承诺已 2026-08-24 校准）：本批只补输出键 + 翻状态。

## 7. 排期锚

PROGRESS 2026-08-24（hook_gate 退役同日）插入批；**窗口已指认 = 当日**——本简报即施工蓝本，工期 ≤ 1 工作日。后续周次不再追排（画廊 v2 八卡齐亮从原排第十周 10-09 提前 33 天）。

## 8. 与既有简报的关系

| 简报 | 关系 |
|---|---|
| `recipe-gallery-v2.md` | Phase B 注册表 5→8 + i18n 命名空间已落（status="live" 当时代码层全部就位仅 voice-dub 缺示例）；本批补 social-post / quote-cards / carousel 三条 example_outputs + 翻 status + 验收闸扩列 |
| `recipe-cards-r1.md`（done） | R1 dub 接线先例；本批继承同一施工形态 |
| `naming-batch-v2.md`（done） | skill/tool 拆家纪律源头；刀 0 直接落 §8 第④「能力层 skills→tools 全量换位」 |
| `output-quality-line.md` | 文本族 writer 受益于期 1 节拍地图（quotables 字段是 quote-cards 的直接素材）；不阻塞本批，期 2/3 已 08-23 落地 |
| ADR-049 | hook_gate 退役同日；本批与之无功能耦合，仅时间对齐 |
