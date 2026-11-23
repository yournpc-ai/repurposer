# OxValue · 首个专业 MG 音画镜头纵向集成（Batch 1 现行施工合同）

> **状态（2026-11-23）**：ACTIVE（当前唯一主线）。上位架构见 [Agent Editor 主合同](new-agent.md)、[作品模型](../VIDEO_PROJECT.md)、[声音合同](../MUSIC_ARCHITECTURE.md) 与 [进度 §0](../PROGRESS.md)。I8 基础剪辑已阶段封板，Renderer 音频时钟候选由独立基础设施轨收口。

---

## 1. 为什么做这次升级（产品背景与竞争标杆）

Rookie Cut 的目标不是一次性黑盒视频生成器，而是**面向欧洲知识型专家、教授、顾问、企业高管与创业者的专业 AI 视频剪辑师**——用户只通过 Chat 持续创作、精准修订并交付工作室水准的作品，无需学习任何时间线/节点/关键帧软件。

对照核心竞品（**Descript/Underlord** 的对话剪辑与听感润色、**ElevenLabs Studio/SFX** 的音频质感、**ChatCut** 的 Agent+可编辑工程+MG 模板、**OriginCut** 的智能节奏初剪、**Hypit** 的词锚定结构复用），我们已完成高可靠底座（单一 Native ToolLoop、唯一 Composition/Working Draft、`apply_composition_edits` 唯一写口、CAS/幂等、ExportJob/MediaJob、费用与强杀恢复），但存在三个直接卡死产品竞争力的缺口：

1. **视觉上限不足**：现役 `EDITOR_TOOLS` 仅能静态叠图与简单位移/缩放；`remotion-project` 任意 TSX 沙箱（`apps/render/src/component-runtime/bake.ts`）仅支持 macOS `sandbox-exec`，在生产 Linux x86_64 强制关闭，且烘焙产物为不透明 H.264 无法透明叠层。
2. **听觉与混音链路残缺**：`insert_audio` 硬编码 `trk_editor_effect` 导致相邻音效撞轨且把库曲误归 `effect`；缺少单实例改增益与替换音源能力；`show_music_candidates`/`select_music` 未在 `prompts.py` 投影；`GenerateVoiceArgs` 仅硬编码 2 个音色（现役实际已接 MiniMax `speech-2.6-hd`）；Freesound 检索体验差且无法参数微调。
3. **无原生音频理解模型的“聋子”约束**：现役主模型 MiniMax（以及大多数主流编码/文本模型）的 `understands_video_audio=False`，缺乏结构化声学属性与掩蔽提示时无法精准卡点与控电平。

同时，Batch 1 选用的声明式组件与声音配方结构，必须为后续 **Claude 生态 Skill 导入**及**用户将调试满意的 Composition 固化为带 Slot 的同款 Skill** 留出零改造的纯可序列化数据地基。

---

## 2. 现役代码基线与必须守住的边界

**工作区隔离（开工第一条）**：从 `main@a37afc08f82fcb68577a06e45c8916a60bff3ff2` 拉取独立的干净分支 / `git worktree` 开工。主工作树中并行的 Web 账户设置（Settings UI）和 5 个冻结 Renderer 音频候选文件各有归属，**本主线严禁修改或混入这两批文件**。

**不可违背的架构纪律**：
- 保持单一原生 ToolLoop、唯一 Composition/Working Draft、唯一内容写口 `apply_composition_edits` 与现有权限/费用/Stop/恢复契约。
- **0 新 SQL 数据库表**；不新建第二套作品模型、Workflow DAG、Review Agent、Intent Router 或全局 Memory/Context Manager。
- **不替换生产 Renderer**（薄渲染核心 C 保持冻结），**不在服务端启动 Headless Chrome / `OfflineAudioContext`**。
- **版权红线**：严禁复制 React Bits Sound Lab 源码/预设（MIT + Commons Clause）或 21st.dev 源码/演示素材；首批音效合成器、配方与 Motion Blocks 全部为洁净室原创实现，且不冒充已集成 21st 源码。
- **反过度设计与反过度测试**：不为假想未来建抽象框架，不为内部 helper 或实现细节写冗余测试（遵循 `CLAUDE.md` Testing 律：仅维护必要的核心合同测试 + 真实 Chat 用户旅程验收）。

---

## 3. 拍板的四项核心设计

### 3.1 共享纯 TS 分层音效引擎（`packages/sound-engine`）
- 零 DOM、纯数学 TypeScript，确定性输出 48 kHz 立体声 `Float32Array` 与 PCM16 WAV。
- 采用可演进的声明式 `Layer[]`（oscillator + pitch env / seeded noise / biquad filter / ADSR / stereo pan / early reflections / limiter）+ 直觉宏旋钮（`pitch`, `tone`, `length`/`duration`, `space`, `punch`）。
- 首批内置 5 个洁净室原创配方：`whoosh`、`impact`、`click`、`riser`、`stinger`（参考 `docs/experiments/renderer-aac/audio-study/` 声学参数经验）。
- **前后端同构**：前端 `apps/web` 直接导入 `@repurposer/sound-engine` 通过 `AudioContext.createBuffer()` 实时试听；后端由现役 Node 服务 `apps/render` 挂载轻量内部端点 `/synthesize-sfx` 确定性出 WAV，API 经 `store_source_bytes` + `register_snapshot` 固定，将带版本的 `SoundRecipeOrigin` 写入 `SourceSnapshot.meta.origin`。本地零积分快速路径免付费弹窗，保留 `owner/project/spec_digest` 单飞去重、Stop、幂等与恢复。

### 3.2 Path β 原生声明式 `MotionBlockObject`
- 在 `apps/api/app/editing/schemas.py` 新增原生对象 `MotionBlockObject`（`kind: "motion_block"`，与 `TextObject`/`ShapeObject` 同级，不污染 `GeneratorObject` 的上游烘焙语义）：字段含 `object_id`, `block_id`, `block_version`, 强类型闭集 `props`, 固定图片 `resources`（复用 `RemotionResource`）, `layout`, `fit`, `transform`, `opacity`。
- 贯通 `editing/validators.py` → `editing/video_spec.py` → `packages/video-spec/src/schema.ts`（声明式 `kind: "motion_block"`，不含可执行代码）→ 共享 `packages/video-remotion/src/Video.tsx`，使服务端 Remotion 与前端 `@remotion/player` 完全同构、原生透明叠层、Linux x86_64 零沙箱依赖。
- 首批实现 2 个洁净室原创高质量组件（克制精密的科技/机构风，适配 `agent.oxvalue.ai` 与通用产品宣传，不硬编码 OxValue 模板）：
  1. `kinetic_title`（可透明叠加的主副标题，支持节奏/速度、配色、对齐、排版参数修订）；
  2. `product_showcase`（承载 `capture_web` 冻结界面图，带精密边框、微透视/推近节奏与高亮聚焦，可与标题叠层配合）。
- 纯可序列化 `props` + 显式 `resources` 引用直接为未来 Skill/VideoTemplate 槽位化（填素材做同款）打底。

### 3.3 统一二级分类 Catalog 元数据（加速 LLM 选型，绝不入哈希）
Motion Blocks 与 Sound Recipes 共用同一套发现与决策元数据头（静态注册表承载，0 新表）：
- **公共字段**：`id`, `version`, `domain`, `category`, `name`, `desc`, `use_for[]`, `avoid[]`。
  - Motion Blocks 分类：`text`（`titles_and_phrases`, `testimonials`, `endings_and_cta`）、`product`（`interfaces`, `cursors`, `devices`, `code_and_terminal`, `agents_and_flows`）、`visuals`（`charts_and_numbers`, `logos_and_partners`, `galleries`, `backgrounds`），附加 `supports_alpha`, `suggested_duration_s`, `required_slots`, `optional_slots`。
  - Sound Recipes 分类：`video`（`motion`, `impact`, `riser`, `stinger`, `transition`）、`interface`（`tap`, `select`, `toggle`, `feedback`），附加 `suggested_duration_ms`, `sync_cue`。
- **缓存铁律**：`name` / `desc` / `use_for` / `avoid` / `domain` / `category` **严禁参与 `content_digest` 或 WAV `spec_sha256`**，确保优化 LLM 选型描述不会使历史音频/版本缓存失效。

### 3.4 最小 Native Tool 增量与现役缺陷补齐
- **新增 4 个薄工具**：
  1. `generate_sfx(recipe_id, params?, base_clip_id?, seed?)`：生成或基于目标 Clip 继承版本/seed 修订固定 WAV，回执附确定性声学指标（`duration_ms`, `peak_offset_ms`, `spectral_centroid_hz`, RMS/Peak）；
  2. `edit_audio_clip(clip_id, gain_db?, source_id?)`：经 `apply_composition_edits` 单实例调整音量或仅替换该 Clip 音源（保留 `object_id` 与其他同源实例）；
  3. `insert_motion_block(block_id, start_seconds, end_seconds, props, resources?)`：落轨并自动避开字幕层，返回 `clip_id` / `object_id` 与可控 props；
  4. `update_motion_block(clip_id, props_patch)`：单实例差量修改参数，无关轨道零变动。
- **修补现役声音与观察链**：
  - `apps/api/app/chat/editor.py::edit_clip`（`insert_audio`）：修复库曲归入 `music` 轨；`effect` 轨在 `[start, end)` 重叠时自动选用/新建空闲 `effect` 轨。
  - `apps/api/app/chat/editor.py::_clip_facts`：回显 `sound_recipe` 来源/参数/声学特征与 `motion_block` 的 `block_id`/`props`。
  - `apps/api/app/chat/prompts.py`：向普通创作与编辑轮开放 `show_music_candidates` / `select_music` 及新增 4 工具的精简分类索引。
  - `apps/api/app/chat/editor.py::GenerateVoiceArgs`：在现役 MiniMax `speech-2.6-hd` 上扩充 6–8 个高质感中英文商业/学术音色 ID。
  - `apps/api/app/chat/editor_media.py::_record_audio` 与前端 `AudioPlaybackSurface`：正确呈现 `effect` 角色（不再标为旁白）并支持 `@repurposer/sound-engine` 试听。
  - `preview_range` 观察回执：补齐结构化时间窗能量与旁白/音效重叠掩蔽提示（辅助 MiniMax 精准卡点与控电平，同时诚实保留 `audio_available_to_model=false` 边界）。
  - `capture_web`：闭环验证批 1 的 DB 与真实 Chat 抓取 `https://agent.oxvalue.ai/` 清晰界面图与可引用原文。

---

## 4. 唯一产品验收标准（真实 Chat 用户模拟旅程）

不以“工具数”或“单元测试绿”宣称完成。必须以真实用户视角在隔离栈跑通针对 `https://agent.oxvalue.ai/` 的 **3-Round 连续对话旅程（8–10 秒专业 MG 开场镜头）**：

1. **Round 1（创作首幕）**：用户给出 `https://agent.oxvalue.ai/`，要求制作一段 8–10 秒产品宣传开场镜头（含真实产品界面展示、精致动态标题、权威旁白、合适 BGM，以及标题滑入的柔和 Whoosh 和落定轻 Impact）并预览。
2. **Round 2（双维度单实例精确修订）**：用户要求“标题入场慢一点，把落定那声 Impact 改低沉一点、音量减 3 dB，其他旁白、音乐和画面保持不变，再播给我看”。核对版本 diff 严格限于目标 `MotionBlockObject.props` 与该 Impact Clip 的 `source` + `gain_db`，其余对象/旁白/BGM/Whoosh 快照引用 100% 字节不变。
3. **Round 3（授权交付与恢复）**：用户同意导出正式 MP4 → `ExportJob` → `review_video` → `deliver_video` → Chrome 真实播放与禁缓存刷新恢复，核对同调用重放不双写、不双扣、解码音频无削波且 Whoosh/Impact 落点同步。

**两道放行门禁**：
- **工程五面铁证**：Provider wire（含真实分类索引与工具调用）、版本 diff、解码音频/帧时序与峰值测量、Chrome 刷新恢复与账本回执，以及 Linux Docker 构建无 macOS 依赖验证；
- **真人视听盲评**：产出 Round 1 / Round 2 对比预览与最终 MP4 交付用户亲自看片试听，视觉节奏、排版高级感、旁白/BGM 协调度与音效同步均获人工认可后，方批准进入 Batch 2（完整多幕宣传片、更多 Block/配方与 Skill 槽位固化）。

---

## 5. 施工中必须停下来向用户汇报的情形

遇到以下任一情况，**立即暂停对应分支并清晰汇报选项与取舍，不要擅自拍板或扩张架构**：
1. 首个 `kinetic_title` / `product_showcase` 视觉样式定稿前需要确认具体审美细节（配色、字体层级、动效风格），或 OxValue 官网实际抓取受限/结构异常；
2. 发现现役 `video-spec` / Remotion / `capture_web` / MiniMax 音色列表存在未预料的契约冲突或需要改动共享持久化结构；
3. 发现超出 0 新表边界、需要新依赖、或触发第三方许可/安全红线；
4. 真实 Chat 旅程中 MiniMax 出现系统性选型或卡点障碍，需要评估是否立即切换/对照强多模态模型。
