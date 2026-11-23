# 作品中的声音 · BGM、Voice 与 SFX

声音可以来自用户素材、曲库、录制或合成。来源决定如何制作和授权。Agent 将固定音频放入同一 Composition 的 Clip，调整入点和增益，随画面预览与导出。轨道角色表达剪辑用途。作品模型和唯一写口见 [Video Project](VIDEO_PROJECT.md)。

## 现役来源与操作

后台已实现下列来源。Batch 1 主线正在补齐普通编辑/创作轮对曲库候选的投影、MiniMax `speech-2.6-hd` 多音色扩展、多 `effect` 轨避撞、库曲正确映射 `music` 轨，以及 `edit_audio_clip(clip_id, gain_db?, source_id?)` 单实例修订能力。[工具注册](../apps/api/app/chat/turn_tools.py) · [每轮实际投影](../apps/api/app/chat/prompts.py) · [Batch 1 合同](tasks/oxvalue-mg-sound.md)

| 内容 | 如何取得来源 | 如何进入作品 |
|---|---|---|
| BGM 配乐 | 从可访问的 Music 库搜索，或用 `show_music_candidates` 试听、`select_music` 解析持久化的候选。需要原创配乐时，`generate_music` 经 MediaJob 将受控乐谱合成为 WAV | 库曲经 `prepare_video_materials(material_music_ids=…)` 固定音频并映射为 `music` 轨。程序化配乐保存乐谱引用、版本、音频摘要和项目快照。Agent 再用 `insert_audio` 指定入点、时长和增益 |
| Voice 旁白 | `generate_voice` 经 MediaJob 调用现役 MiniMax `speech-2.6-hd`（支持 `en/zh/fr/de/es/it` 与多组精选商业/学术音色）合成语音，回执含固定音频、台词和对齐身份 | 独立录音可用 `insert_audio`。已有待配音 Clip 可用 `bind_clip_source` 绑定匹配来源，SpeechObject 保留台词和对齐语义 |
| SFX 音效 | **主力来源**：洁净室共享纯 TS 分层引擎 `@repurposer/sound-engine` 经 `generate_sfx` 确定性合成 48 kHz 立体声 WAV 并固定为项目 `SourceSnapshot`（0 新 SQL 表）。**可选外部来源**：Freesound（`search_sfx` / `import_sfx`，CC0 复核） | 固定快照经 `insert_audio` 落入空闲 `effect` 轨（支持同幕多音效重叠不撞轨）；单实例调增益或仅替换目标音效音源走 `edit_audio_clip`，保留其他同源实例与旧版本 |

## 共享纯 TS 分层音效引擎（`@repurposer/sound-engine`）

**现行架构（替代原独立 Python 脚本，0 新 SQL 表）。** 洁净室编写零 DOM、纯数学 TypeScript 共享包 `packages/sound-engine`，直接输出 48 kHz 双声道 `Float32Array` 与 PCM16 WAV：

- **前后端同构**：前端 React Studio（`apps/web`）直接导入 `@repurposer/sound-engine` 通过 `AudioContext.createBuffer()` 实时试听与调参；服务端通过现役 Node 服务 `apps/render` 的轻量内部端点 `/synthesize-sfx` 运行完全相同的 TS 代码，**无需 Headless Chrome 或 `OfflineAudioContext`**，前后端逐采样确定性一致。
- **可演进分层模型**：内部采用声明式 `Layer[]` 合成图（oscillator + pitch envelope / seeded noise / biquad filter / ADSR / stereo pan / early reflections / limiter），对外暴露少量直觉化宏旋钮（`pitch`、`tone`、`length`/`duration`、`space`、`punch` 等）。首批内置 5 个洁净室原创配方：`whoosh`、`impact`、`click`、`riser`、`stinger`（吸收原声学研究参数经验，不复制任何外部代码或预设）。
- **统一二级分类 Catalog 元数据**：每个配方声明 `domain`（`video` | `interface`）、`category`（`motion` / `impact` / `riser` / `stinger` / `transition` / `tap` / `select` / `toggle` / `feedback`）、`name`、`desc`、`use_for`、`avoid`、`suggested_duration_ms`、`sync_cue`（如 `energy_peak` / `onset`）。**发现与决策元数据绝不参与 WAV/spec 摘要哈希**，避免优化提示词文案导致音频缓存失效。
- **持久身份与零新表**：`SourceSnapshot.meta.origin` 保存带版本的 Typed JSON（`schema_version`, `kind: "sound_recipe"`, `engine`, `recipe_id`, `recipe_version`, `params`, `seed`, `acoustics`, `wav_digest`）。`generate_sfx` 按 `owner/project/spec_digest` 单飞去重，本地零积分快速路径免付费确认弹窗，仍严格遵守 opening/call 幂等、Stop 边界与恢复契约。
- **结构化声学特征（解决无原生音频理解模型的“聋子”问题）**：每个生成回执携带确定性声学指标（`duration_ms`、`peak_offset_ms`、`spectral_centroid_hz`、RMS/Peak）；`preview_range` 同步输出时间窗能量与旁白/音效重叠掩蔽提示，使当前 MiniMax 等无原生听觉模型也能准确卡点与控制电平。确定性指标不冒充主观听感，成片仍需人工或具备听觉能力的多模态模型听评。

ReactBits Sound Lab 仅作交互、分类与分层参数设计参考。其 MIT + Commons Clause 限制独立再分发声音包及托管实质相似工具，**严禁复制其源码、音效或预设进入生产**。原有 3 配方 Python 研究证据保留归档于 [audio-study](experiments/renderer-aac/audio-study/REPLAY.md)。已有乐谱合成、快照、播放器和导出按需复用，音效沿用同一音轨模型与 ToolLoop。[现有配乐合成](../apps/api/app/tools/music/score.py) · [固定音频及乐谱来源](../apps/api/app/tools/video/music_preparation.py)

## 数据、权限与历史消费者

- 平台策展曲使用公开的 Music 行和 `music/` 对象。Agent 的程序化配乐按 owner 和项目准备，新曲默认私有。版本引用 SourceSnapshot 与实际音频摘要，Renderer 按编译后的 video-spec 播放。
- 历史 Persona 深链仍能试听曲库、保存皮肤默认值和显式调用 `POST /api/v1/music/generate`。该路由在请求内生成并上传，创建默认公开的 Music 行，尚无项目报价、配额或 prompt 去重。此行为仅适用于该曲库入口。项目内的 `generate_music` 走 MediaJob 和现役授权机制。[曲库路由](../apps/api/app/pipeline/routes/music.py) · [项目媒体作业](../apps/api/app/pipeline/media_jobs.py)
- 曲库删除保护仍检查历史 Output 中的 `render_spec.music` 引用。保存版本中的快照、用户曲目、Persona、历史 Output 与许可记录均须保护；新作品使用 Composition 写口。[曲库与引用检查](../apps/api/app/pipeline/music.py)

## 策展曲库与启动对账

默认 catalog 由 `CURATED_MUSIC_CATALOG` 的五首 Shotcraft BGM 组成：Tech House、Cat Walk、G Eazy NBA type、House Vibez、Tonight。平台不再自动补入 Calm Academic、Inspiring Vision、Corporate Drive；启动时会删除未被历史 Output 引用的旧平台行及其对象，仍被引用的行转为私有以保留历史而不进入候选库。用户自己生成的音乐不受影响。

- `app/pipeline/music.py:seed_default_music` 在应用启动时 reconcile：按 mood 查缺，对象存在而记录缺失时补记录。
- 启动 reconcile **不调用 MiniMax、不生成音频、不花配额**；对象不存在时保持缺失并诚实跳过。
- 五首都来自 Shotcraft 的 `assets/audio/bgm`。除 Tech House 外的四首有逐曲作者和 URL；`bgm-tech-house.mp3` 的原曲名、作者与逐曲 URL 无法反查，库中明确标记“商用前复核”。代码与音乐的许可分别记录，不把 Shotcraft 的 Apache-2.0 当成音乐许可。
- 策展字节由 `apps/api/scripts/import_library_music.py <Shotcraft/assets/audio/bgm>` 显式导入。脚本只读五首白名单本地 MP3，解码探测真实时长、计算 SHA-256 并上传缺失对象；已有对象仅字节完全相同才复用，绝不覆盖。它不写 DB、不调用模型。
- 启动 reconcile 保存来源、许可、作者、风格、参考 BPM 和实际时长/digest，并尽力补齐 BeatGrid；参考 BPM 不冒充新分析结果，BeatGrid 缺失时保持为空。
- reset_db 保留 `music/` 对象前缀，清库后重启只重建可对应记录。

## 向共享曲库上传音乐（待实施）

开放曲库上传前必须具备：

1. 明确权利声明并持久化到上传记录；
2. ToS 中用户责任、平台撤下权与投诉流程；
3. 默认 `is_public=FALSE`，公开分享需要显式 opt-in 与平台审核；
4. 文件类型、大小、存储、租户隔离与审计限制；
5. DMCA/当地法适用的投诉、删除和争议流程；
6. 法务评估“平台把上传音乐合成进衍生视频”是否影响 safe harbor。

未满足这些条件时，不得仅复用普通 Asset 上传就开放音乐库。

## 版权与公开库

**仍需核实 provider 当前条款**：商业使用、再分发/平台托管、输出权属、终端用户视频分发、是否要求署名。

条款不足时的回退顺序：换有明确商业许可的 provider、委托并取得原创音乐权利，或关闭音乐能力。不得用技术生成事实替代授权。

公开库还需决定：

- 谁审核用户生成公开曲、如何处理投诉与撤下；
- 是否允许艺术家署名或收益分配（未拍板，不是当前承诺）；
- 自定义生成的配额、付费和公平使用模型；
- 是否做 prompt/内容缓存，以及缓存键、跨用户共享和隐私边界。

## 真实证据与开放项

- I6 中 Agent 生成过固定旁白和四秒程序化配乐，再分别插入同一作品。Chrome 刷新前后均播放了两条音频。样本中的配乐为零积分，旁白首次生成两积分，同文复用零积分。它覆盖该样本的生产、落轨与回放。[I6 媒体记录](tasks/agent-editor-evidence/iteration-6/media.md)
- 旧 S15 留有本地五首候选、下一轮按序号选曲及 music 修订的一次真实 Chat 记录。完整制作与主观混音仍待验。后续验收须对照同一版本实际试听音画时序、响度、循环接缝及旁白可懂度。
- Sound Recipes 仍缺真实的“描述音效 → 固定音频 → 落轨 → 试听 → 只改这一声”的往返证据，重放还须核对版本、音频与费用。正式导出和费用遵循 [现役 Agent 合同](tasks/new-agent.md) 与 [账本](BILLING.md)。
