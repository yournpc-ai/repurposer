# 作品中的声音 · BGM、Voice 与 SFX

声音可以来自用户素材、曲库、录制或合成。来源决定如何制作和授权。Agent 将固定音频放入同一 Composition 的 Clip，调整入点和增益，随画面预览与导出。轨道角色表达剪辑用途。作品模型和唯一写口见 [Video Project](VIDEO_PROJECT.md)。

## 现役来源与操作

后台已实现下列来源。普通编辑/创作轮已开放曲库候选投影、11 个活体验证 MiniMax `speech-2.6-hd` 音色、多 `effect` 轨避撞、库曲映射 `music` 轨与无断缝多段连续循环铺底（首段淡入、末段淡出，零协议新增字段）、以及 `edit_audio_clip(clip_id, gain_db?, source_id?, fade_in_seconds?, fade_out_seconds?, duck_windows?)` 单实例修订。[工具注册](../apps/api/app/chat/turn_tools.py) · [每轮实际投影](../apps/api/app/chat/prompts.py) · [Batch 2 合同](tasks/batch2-multiscene-skill.md)

| 内容 | 如何取得来源 | 如何进入作品 |
|---|---|---|
| BGM 配乐 | 从可访问的 Music 库搜索，或用 `show_music_candidates` 试听、`select_music` 解析持久化的候选。需要原创配乐时，`generate_music` 经 MediaJob 将受控乐谱合成为 WAV | 库曲经 `prepare_video_materials(material_music_ids=…)` 固定音频并映射为 `music` 轨；短于作品总长的 BGM 自动按连续标准 `Clip` 无缝循环铺满，首段淡入、末段淡出（保存为 Skill 时保留首尾淡变）。旁白下 BGM 常规压低至 `−24 ~ −26 dB` |
| Voice 旁白 | `generate_voice` 经 MediaJob 调用现役 MiniMax `speech-2.6-hd`（支持 `en/zh/fr/de/es/it` 与 11 组商业/学术音色）合成语音，回执含固定音频、台词和对齐身份 | 独立录音可用 `insert_audio`，多幕旁白留 `0.4–0.6s` 呼吸气口避免撞车。已有待配音 Clip 可用 `bind_clip_source` 绑定匹配来源，SpeechObject 保留台词和对齐语义 |
| SFX 音效 | **主力来源**：洁净室共享纯 TS 分层引擎 `@repurposer/sound-engine` v3（80 个配方，24 个分类）经 `generate_sfx` 确定性合成 48 kHz 立体声 WAV 并固定为项目 `SourceSnapshot`（0 新 SQL 表）。**可选外部来源**：Freesound（`search_sfx` / `import_sfx`，CC0 复核） | 固定快照经 `insert_audio` 落入空闲 `effect` 轨（支持同幕多音效重叠不撞轨）；单实例调增益或仅替换目标音效音源走 `edit_audio_clip`，保留其他同源实例与旧版本 |

## 共享纯 TS 分层音效引擎（`@repurposer/sound-engine` v3）

**现行架构（`SOUND_ENGINE_VERSION = 3`，0 新 SQL 表，零浏览器依赖）。** 洁净室编写纯数学 TypeScript 共享包 `packages/sound-engine`，直接输出 48 kHz 双声道 `Float32Array` 与 PCM16 WAV：

- **前后端同构与零降级 DSP**：前端与服务端（`apps/render` 内部端点 `/synthesize-sfx`）运行完全相同的纯 TS 代码，**无需 Headless Chrome 或 `OfflineAudioContext`**，同参数同 seed 逐字节一致。DSP 内核包含：
  - **抗混叠多声部振荡器**：`sine` / `triangle` / PolyBLEP 抗混叠 `sawtooth` & `square`，支持 `1..8` voices 微失谐（`detune`）与自动对称立体声展开、曲线频率斜坡；
  - **三色确定性噪声**：高斯 `white`、Paul Kellet 7 态 `pink`、12 Hz 泄漏积分 `brown`；
  - **滤波与多段包络**：Audio EQ Cookbook 5 模双二阶滤波器（`lowpass` / `highpass` / `bandpass` / `peaking` / `notch`）+ 总线高/低通，支持带曲率的 `attack / rise / hold / decay / release`；
  - **立体声空间与母带**：左右声道独立互质延迟的 4 路阻尼梳状 + 2 级 Moorer 格型 Schroeder 全通算法混响（`predelayMs` / `decaySec` / `dampHz` / `mix`）+ M/S 立体声宽度（`width`）；ITU-R BS.1770-4 K 加权积分响度（`lufs`）+ 24-tap Blackman-sinc 4 倍过采样真峰值检测 + 2 ms 前瞻立体声联动柔和限幅（峰值精准归一至 `−2.0 dBFS`，真峰值 `≤ −1.75 dBTP`）+ 升余弦无爆音残余直流归零。
- **80 个母体**分属交互与影视两域，各覆盖 12 类。FM 与分数延迟拨弦构成玻璃、木击与和弦，磁带刹停、采样保持、饱和及交叉反馈回声塑造转场。
- **调音与贴拍**共用七维 `SoundTune`。工作台在浏览器中合成试听并引用参数。Agent 可用 `target_duration_ms` 伸缩包络，用 `align_peak_at_seconds` 将实测峰值落在切点。原有配方保留 `params` 和 seed。
- **统一二级分类 Catalog 与 TS↔Python 零漂移校验**：每个配方声明 `domain`（`video` | `interface`）、`category`、`name`、`desc`、`use_for`、`avoid`、`suggested_duration_ms`、`sync_cue`（`onset` / `energy_peak` / `end_peak`）。**发现元数据绝不参与 WAV/spec 摘要哈希**；核心测试通过一次 Node 子进程强制校验 TS 与 Python 侧全部 80 个目录项、边界舍入及 canonical JSON SHA-256 逐字节一致。
- **商业级多轨声音堆叠规范**：避免 1 条平铺 BGM 配 2–3 声孤立滴答的单薄感；60 秒旗舰片与首页模板推荐按节拍分层叠加（`BGM 铺底 + 切点前 1.0–1.5s 长 Riser/Sub Swell 铺垫 + 切点第 0 帧 Deep Hit/转场音效砸点 + 幕内 Callout Ping/Metric Chime/Soft Pop 跟随字幕微点缀 + 痛点转折 Sub Drop 配合 BGM 短暂闪避留白`），旁白下常规点缀控制在 `−14 ~ −10 dB`。
- **结构化声学特征（解决无原生听觉模型的盲剪问题）**：回执携带 `duration_ms`、`peak_offset_ms`、`peak_dbfs`、`rms_dbfs`、`lufs`、`spectral_centroid_hz` 与 32 段波形包络；`preview_range` 同步输出音频能量窗与掩蔽警告。确定性指标不冒充主观听感，成片仍须实听验收。

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
