# Batch 2 · 多幕商业 MG 宣传片与 Skill + Slot 同款复刻（验收归档）

> **状态（2026-11-24）**：DONE（已合入 `main@857d475a`）。Checkpoint 2A（38.0s OxValue 英文投资人版 v40）与 Checkpoint 2B（Round 4 固化 `oxvalue-promo-blueprint` → Round 5 中文技术转移/治理视角复刻 v7 与单实例零漂移续改）全部真实 Chat 闭环通过并获用户拍板；0 新 SQL 表；全仓核心回归（API 498 · Web 42/42 · 342 · Render 7/7 · sound-engine 2/2 · video-spec 11/11）及 Linux `apps/render/Dockerfile` 构建全绿；8,000 字符窗口 128 次调用实测截断率 6.25%、0 约束丢失；隔离 `gemini.py` 适配器静默预留（无 `GEMINI_API_KEY`，以 MiniMax 实证收口）。上位架构见 [Agent Editor 主合同](new-agent.md)、[作品模型](../VIDEO_PROJECT.md)、[声音合同](../MUSIC_ARCHITECTURE.md) 与 [进度 §0](../PROGRESS.md)。

---

## 1. 产品目标

将 Rookie Cut 从 Batch 1 验证通过的“9 秒单镜原型”推进至**欧洲教授、顾问、创业者可直接挂官网首页或发 LinkedIn 的 35–40 秒商业宣传片 AI 剪辑师**，并打通“满意作品一键固化为带 Slot 的个人 Skill → 换素材/跨角度/跨语言复刻为活工程继续精修”的最小复利闭环。

---

## 2. 不可违背的架构与施工护栏

1. **两道内部检查点（先审美、再复刻）**：
   - **Checkpoint 2A**：完成主干合并、`MotionBlockObject.resources[0..N]` 统一 staging、3 个新 Motion Blocks + 2 处存量轻量增强、`crossfade` 扩展、BGM `audio.gain` 淡入淡出/闪避、`swoosh_cut` 配方与多幕导演提示词；以现役 MiniMax 交付 35–40s OxValue 英文投资人版商业成片，**暂停交付真人看片盲评**；
   - **Checkpoint 2B**：2A 盲评通过后，交付 `save_composition_as_skill` + 复用 `/` SkillPicker 的 `instantiate_skill_blueprint` 最小闭环，并以 OxValue 跨角度/跨语言复刻（Round 4–5）验收。
2. **0 新 SQL 表与单一写口**：严禁新增数据库表或 Alembic 迁移；Skill 固化与展开完全复用既有 `UserSkill` / `SkillVersion`（`apps/api/app/skills/`），所有作品写入仍经唯一 `apply_composition_edits` 与 `CompositionVersion`。不做 Skill 市场、不做 `SKILL.md` 文件上传 UI、不做模板求解 DSL。
3. **复刻展开的时长与事务边界**：`blueprint.json` 中的 `target_duration_s` 仅作节奏基线；换新旁白时按实际旁白时长 + `0.4–0.6s` 气口自动适配幕长，SFX 偏移按相对幕起止/落点解算。**严禁在 `apply_composition_edits` 数据库事务锁内发 HTTP 调用 `/synthesize-sfx`**，必须先在事务外固定 SFX 快照再原子落版。
4. **`closing_cta` Logo 视觉保护**：无 Logo 时默认纯排版高级文字锁屏；传入可选 `logo_resource` 时支持 `logo_surface: "light_pill" | "raw"`，避免浅底网页截屏 Logo 贴在深色收尾卡上出现白框。
5. **纯帧驱动双栈兼容**：所有新 Motion Blocks 保持洁净室原创、纯帧驱动 React 函数（无 `requestAnimationFrame`/DOM 副作用），对标顶级微动效质感（遮罩逐行/逐词揭示、克制弹簧 settle、关键词高亮扫过、数字/微曲线顺滑滚入），确保当前兼容 Remotion 且未来无缝兼容冻结的渲染核心 C（**核心 C 继续冻结，不替换生产 Renderer**）。
6. **克制测试与上下文观测**：严守 `CLAUDE.md` Testing 律，仅维护必要核心合同测试 + 真实 Chat 旅程；记录 `tool_loop.py` 8,000 字符最近对话窗在 35–40s 多幕多轮修订中的真实截断率，未实测丢失约束前不新增滚动摘要层。TOS 非标隔离端口字体 CORS 归运维配置，不在 API 写字体反代。

---

## 3. 最小可行范围与技术拆解

### 3.1 Checkpoint 2A · 视觉、转场、声音与多图 staging

- **多图 staging 收债（`apps/render/src/video/index.ts`）**：对 `clip.object.kind === "motion_block"` 并行调用 `stageRemoteSource` 缓存全部 `object.resources[0..N]`，解除多资源 Block 阻塞。
- **新增 3 个通用原生 `MotionBlockObject`**（支持 Option B 浅色工作室主调与深色高对比幕，统一二级 Catalog 元数据不入哈希）：
  1. `statement_hook`（`text/titles_and_phrases`）：独立 3–5s 纯排版开场钩子/幕间金句（`eyebrow?`, `headline`, `highlight_phrase?`, `subheadline?`, `theme`, `layout_variant`, `accent_color`, `entrance_duration_s`, `exit_duration_s`, `show_backdrop`）；解决首页截屏复读大标题问题。
  2. `metric_grid`（`visuals/charts_and_numbers`）：2–4 项精密指标卡矩阵（`eyebrow?`, `title?`, `items: [{value, label, detail?, badge?}]`, `columns: 2|3`, `theme`, `accent_color`, `stagger_s`, `count_up`, `show_backdrop`），带弹簧落定、数值确定性帧滚入与微高光扫过。
  3. `closing_cta`（`text/endings_and_cta`）：品牌收尾定版卡（`brand_name`, `tagline`, `cta_label?`, `url_text?`, `theme`, `accent_color`, `entrance_duration_s`, `logo_surface: "light_pill" | "raw"`, `show_backdrop`；可选 `resources: [logo]`）。
- **2 处存量轻量增强（向后兼容 v1）**：
  - `product_showcase` 增加可选 `callout?: {x, y, width, height, label?}` 局部聚光灯高亮框与 `chrome_mode?: "browser" | "frameless"`；
  - `kinetic_title` 增加 `surface_style: "pill_caption"` 轻量功能角标。
- **多幕转场与 BGM 起伏（复用现有 Composition）**：
  - `apps/api/app/editing/transitions.py` 与 `video_spec.py` 放开全画幅不透明 `MotionBlockObject`（`show_backdrop=True`）参与既有 `crossfade`；暴露薄工具 `set_transition(from_clip_id, to_clip_id, kind="crossfade", duration_seconds=0.4)` 发既有 `SetTransition` Op；
  - `edit_audio_clip` 增加可选 `fade_in_seconds`、`fade_out_seconds`、`duck_windows?`，编译为标准 `Animation(property="audio.gain")` 关键帧（`Video.tsx` 原生支持），实现开场渐入、旁白稳态 `-25 dB`、气口微抬、片尾平滑淡出。
- **声音包微增**：`@repurposer/sound-engine` 仅补 1 个过渡配方 `swoosh_cut`（`video/transition`，240–420 ms 对称双向切镜扫音，`-2.0 dBFS` 归一化）。

### 3.2 Checkpoint 2B · Skill + Slot 最小闭环（0 新 SQL 表）

- **固化（`save_composition_as_skill`）**：确定性扫描当前 `CompositionVersion`，剥离所有原项目 `snapshot_id` 与隐私文案，生成标准 `SKILL.md`（写入 `SkillVersion.instructions`）、纯声明式 `references/blueprint.json` 与 `declared_inputs`，调用既有 `import_external_skill()` 持久化到 `UserSkill` / `SkillVersion`（owner 隔离、不可变、幂等去重），即时出现在前端 `/` SkillPicker。
- **复刻展开（`instantiate_skill_blueprint`）**：用户在新 Chat 通过 `/` 选中该 Skill 并提供新视角素材/语言目标；后端复用 `resolve_chat_skill` → `load_skill_creative_context`，先在事务外合成所需 SFX 快照与旁白，按实测旁白时长 + `0.4–0.6s` 气口解算每幕区间与 SFX 落点，再经唯一写口 `apply_composition_edits` 原子落版为可继续精修的 `CompositionVersion`。

### 3.3 原生音视频多模态对照（隔离预留，不阻塞主线）

- 按 `apps/api/app/providers/llm/base.py` 的 `LLMClient` 契约预留极薄的隔离 **Gemini 2.5 Pro**（`understands_video_audio=True`）对照适配器，无 `GEMINI_API_KEY` 时不影响主线运行。待配置密钥后在相同冻结 OxValue 多视图与剧本上跑同题对照，输出盲评、轮次、耗时与 USD 成本对比。

---

## 4. 唯一产品验收旅程（真实 Chat 5-Round 闭环）

- **Checkpoint 2A（Round 1–3，目标 `https://agent.oxvalue.ai/`）**：
  1. **Round 1**：创作 35–40s 面向欧洲投资人与科研机构的 OxValue 英文商业宣传片（纯排版开场钩子 → 至少 2 个不同真实界面视图特写 → 指标卡 → 品牌收尾 CTA，分幕旁白 + 淡入淡出 BGM + 克制 SFX）。
  2. **Round 2**：单句跨幕多维度精确修订（修改开场钩子与深浅主题、更新指标卡单项与交错节奏、拉长片尾 BGM 淡出并调整指定切镜音电平），核对零漂移 diff 与 8,000 字符窗口截断日志。
  3. **Round 3**：授权导出 1080p MP4 → `review_video` → `deliver_video` → 重复授权 `409` → Chrome 播放与禁缓存硬刷新恢复 → 解码音频无削波与淡出验证 → **暂停交付真人盲评**。
- **Checkpoint 2B（Round 4–5，2A 盲评通过后开启）**：
  4. **Round 4**：在同 Chat 固化该满意成片为个人 Skill `oxvalue-promo-blueprint`（0 新表、零私有 `snapshot_id` 泄漏、`/` SkillPicker 立即可见）。
  5. **Round 5**：新 Chat 选中 `oxvalue-promo-blueprint`，围绕 OxValue 做**跨角度/跨语言复刻**（切换 Platform / Core Technology / Governance 真实视图 + 中文技术转移/治理视角 + 新指标与中文旁白），展开后按新旁白时长自动适配幕长并做 1 轮自然语言续改预览，证明 100% Slot 替换且为活工程。
