# Repurposer 声音配方研究与架构评审稿

**结论**　三个原创短音可以由少量语义参数稳定地制成固定媒体。现有分析器已实际读通六个 WAV。优先补齐的产品能力是让同一 Agent 从指定 Clip 找回配方、只替换这个实例、并在旁白与配乐中听回结果。现有时间线足以表达这一过程，普通编辑工具在同角色叠音、来源续改、单独调增益以及 Chat 的音效角色上还有具体缺口。

**评审入口**　先播 [三秒同步样片](sync.mp4)，其中保留了已有的真实旁白和配乐样本。再播 [六声原电平对照](comparison.wav)，顺序为 Whoosh、Impact、Click，每组默认在前、修订在后。独立音频的播放回执在 [playback.log](playback.log)。机器完成了解码和实际播放。当前会话没有可以据此签字的听觉判断，柔和度、重复疲劳和旁白可懂度均待人耳听评。样片使用指定动作及已知源信号。

## 1　基线与证据归属

2026-11-22，主仓 /Users/sylas/repurposer，main，开始与核对时 HEAD 均为 b01823d614ddff4972e26fc1a56987f5f5f30336。开始时工作树已有 apps/api/app/chat/plan_turn.py、prompts.py 和 apps/api/test/core/test_provider_tools.py 修改。并行期间文档等继续变化，末次文件列表见 [worktree-end.txt](worktree-end.txt)。本文以所读工作树代码、历史实测回执和本次独立实验分别标明证据。未建分支，未运行主服务、访问产品数据库或调用付费模型。所有新增文件在 /tmp/repurposer-audio-wwrSsj。

macOS 26.5.2 arm64，仓库现有 Python 3.11.14、NumPy 2.4.6、PyAV 17.1.0、Pillow 12.3.0。WAV 生产只需 Python 和 NumPy。独立视频使用 PyAV 内置 libavcodec 62.28.101；现有仓库分析器另记录了其 FFmpeg 身份。网络用于只读检查参考产品。

仓库阅读依据为 README.md、CLAUDE.md、docs/tasks/new-agent.md、docs/tasks/i8.md、docs/VIDEO_PROJECT.md、docs/MUSIC_ARCHITECTURE.md、docs/RENDERING.md、docs/BILLING.md、docs/PROGRESS.md §0。以持续作品、唯一 Native ToolLoop、不可变版本、单一编辑写口及既有作业授权为约束。主仓由 I8 施工，本次不构成正式集成授权。

## 2　从用户请求追到交付

以下相对代码路径以仓库根为基准，API 简写以 apps/api/app 为基准。

| 环节 | 当前消费者与行为 | 对 Sound Recipe 的判断 |
|---|---|---|
| 模型可见面 | chat/turn_tools.py 和 chat/editor.py 注册；chat/prompts.py 根据当前作品、可用媒体和权限裁剪当轮工具，再送 Provider。plan_turn.py 有派发并不意味着每轮可选 | 常规编辑轮可 inspect、generate_music/voice、insert_audio、preview_range；生成受用户禁止条件裁剪。没有 recipe 生成工具 |
| 实际 Provider | I8 的 docs/tasks/agent-editor-evidence/iteration-8/provider-tools.json 中，inventory b99a6e0b… 有 insert_audio/generate_music/prepare_video_materials，无 search_music/show_music_candidates/select_music/search_sfx/import_sfx。model-requests.jsonl 首条响应成功，wire_sha256 与该 inventory 相同 | 证实该次 MiniMax-M3.1-Flash 普通编辑请求所见。与当前投影逻辑一致；本轮未发新线上请求，不能推广到所有历史座位 |
| 来源 | tools/music/score.py 的有界 ScoreSpecDraft → resolved ScoreSpec；generate_music 对外只给时长、风格、BPM、名称。库曲选 Music ID；Voice 固定原速录音、台词与 alignment；SFX 外部候选单独处理 | 音效适合按用途选配方、模板内改语义参数。BGM 的编排、TTS 文本与真实录音各自保留 |
| 生成、分析、固定 | pipeline/media_jobs.py 在执行身份下调用 tools/video/music_preparation.py；浮点 PCM → WAV → 字节摘要 → analyze_audio_bytes → 存分析和 ScoreSpec → register_snapshot。私有 Music 行及 owner/project/score_digest/analyzer-version manifest 可回读校验 | 复用存源字节、精确样本时长、分析器、快照注册和回执校验。programmatic music 可 asset=None；recipe 可沿用此项目内路径，用户上传/外部导入仍用 Asset。不为一个短音建 Music 行 |
| 保存作品 | insert_audio 校验 owner、origin_project_id、kind、duration；普通 start_seconds、可选 duration_seconds、gain_db（−60 至 +12）。fixed_audio_ops 必要时 BindSource/AddTrack，然后 AddClip。以同一次调用身份产生 Clip/Object ID，经 apply_composition_edits 返回版本与回放身份 | 足以首次插入整声或从源头裁短。source_start 固定为 0，scene_id=None，没有标题关联或来源替换参数。源与作品的范围分别量化，长度必须落入两侧有效窗口 |
| 轨道与编辑 | editing/schemas.py 的 ClipSource 存 snapshot_id/digest/source_range；AudioObject 有 gain_db。只有 programmatic_score 映射 music，旁白哈希映射 dialogue，其余为 effect，库曲也可能回退到 effect。track_id 固定 trk_editor_{role}；editing/validators.py 拒绝同轨相交 | 本样片 whoosh 延续至 1.46 s，impact 从 1.40 s 起。现工具会撞轨。复用现有多个 audio Track，按现版本选择首条空闲 effect 轨，必要时稳定建下一条；不为叠音复制时间线 |
| 实际播放与混音 | tools/video/audio_playback.py 读回真实字节、项目归属、摘要、全量分析及 peaks；网页版 AudioPlaybackSurface 解签名 URL，WaveformPlayer 播放。packages/video-remotion/src/Video.tsx 的 AudioClipView 使用源窗、Clip 电平乘 audio.gain 动画，按 spec 渲染。editing/audio.py 有音乐床铺排与首尾增益关键帧 | 播单个源与检查作品混音都需要。当前整片 apps/render/src/video/index.ts 调用 audio.ts 的两遍 loudnorm，目标 −16 LUFS、−1.5 dBTP、LRA 11，重编 48 kHz AAC；短音无需逐个套此目标。全片归一化解决不了声音互相掩盖 |
| Output 与恢复 | export_video、授权、ExportJob 认领，固定版本编译为 video-spec；实际 Output 与版本、执行 spec、媒体可审阅。review_video 对确切 Output 解码；preview_range 返回版本和模型音频能力事实。chat/editor_media.py 开轮/调用重放，editor_recovery.py 恢复已提交写入和媒体回执，pipeline/media_jobs.py 校验租约/token 后终态结算 | 音效固定后才可编辑/导出；交付应关联实际 Output ID 和 digest。重新打开旧版本应播放旧字节。没有任何本轮产品 Output、正式重放或收费实测 |

**已有的声音基础。** ScoreSpec 支持 32/44.1/48 kHz、1/2 声道，正弦/三角/锯齿/方波、带种子的噪声和音高下滑打击乐、线性起落包络、声像、分层浮点叠加、段落动态与淡出、峰值保护和小端 PCM16 WAV。节拍与事件用 Fraction 映射到样本和 90 kHz 源时基；受 120 s 和事件数约束。沿用量化函数、PCM 约定、内容摘要、固定后完整解码与时长测量。共用逻辑按实际调用提取，不要求短音借用 Music 私有 Instrument 类型。和弦、MIDI、拍号、场景段落、乐器编制、authored BeatGrid 留给配乐。tools/music/beats.py 的 PyAV 解码、NumPy 起音能量和自相关用于长曲压拍；短/平信号可返回无可信网格，不能借其 BPM 给点击定位。

**证据层级。** I6 的 media.md、media-native.json.gz 与 media-browser.json 记录同一六秒作品中四秒配乐和 1.439656 秒旁白的制作、插入、刷新前后播放；该样本配乐 0 积分，旁白首次 2、复用 0。I6 media-faults.json 的 SIGKILL 边界使用已记录的供应商音频。旧 S15 有曲库候选、下一轮选曲和修订记录；artifacts/d5-sfx-integration/review-reuse.json 可证历史 Output 复用了审阅，不能据此证明当前 Provider 能选 Freesound，或人已听评。I8 final-replay.json 记录的是已保存视觉编辑的 replay。本次新增证据限于声音制作、同参复现、仓库字节分析器兼容及独立 A/V 输出测量。

## 3　Sound Lab 的机制与许可

浏览器页面实测 Interface 100、Video 100。前者以 tap/select/toggle/feedback 等界面行为组织，后者覆盖 risers/impacts/whooshes/titles 等剪辑用途。Chrome 的 AudioContext 在 running 状态实际启动 Pebble（48 kHz、15,694 帧、首声道 peak 0.465、RMS 0.0494）与 Ascent（293,211 帧、peak 0.714、RMS 0.0701）。记录了本次播放节点的内存统计，研究包未携带参考声音字节。见 [实测记录](reference.log) 和 [产品页](https://reactbits.dev/tools/sound-lab)。

源码基线 701a8acc34f718b305d1ff0cc7d4700df0e1f1c9。每种声音有不同层、起始位置、音高或随时间变化的曲线、包络和路由。tone、noise 与可选 sample 共存。少量 pitch/tone/length/space/punch 控制组合的尺度；同一个 length 会影响主体时间，延迟和混响仍需尾窗。按配方 seed 生成噪声与卷积脉冲，sample 层还能选不同 take。Variation、播放音量、种子及样本变体承担不同职责；不可只存一个 variation 百分比作为再生产合同。试听按 id、形状参数和 variant 缓存渲染结果。离线 Web Audio 渲染经滤波、增益、干湿混合；可加入 echo/chorus 等。实时分析与按单声道汇总的波形分桶、可闻尾窗估计用于反馈。WAV 编码按声道交错，可单声道导出，支持整数及浮点；编码默认 24 位。浏览器试听已测，WAV 导出在本轮按源码核对。[分类与配方](https://github.com/DavidHDev/react-bits/tree/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/src/tools/sound-lab/sounds) · [DSP](https://github.com/DavidHDev/react-bits/blob/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/src/sounds/ts/react-bits-sound.ts) · [播放器和分析](https://github.com/DavidHDev/react-bits/tree/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/src/tools/sound-lab/engine) · [编码](https://github.com/DavidHDev/react-bits/blob/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/src/tools/sound-lab/export/wav.js)

授权文本分别处理工具、声音库和使用工具创作的成品。MIT + Commons Clause 允许符合条件的商业作品使用导出物，同时限制独立销售/再分发声音或导出包，以及托管该工具或实质相似复制品。计划直接移植实现、托管图库或分发配方/声音时，应取得覆盖具体行为的书面授权。此研究借鉴按用途发现、少量可调维度和试听反馈，下面的算法、数值及描述在本研究独立编写，未使用第三方样本或移植源码。[授权原文](https://github.com/DavidHDev/react-bits/blob/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/LICENSE.md)

## 4　最小合同与三套原创配方

[catalog.json](catalog.json) 是 Agent 可读的完整合同。以稳定 ID 为键，含名称、类别、一句话听感、视觉用途、禁忌、建议时长、混音提示、版本和参数 Schema。每项均有整数类型、单位、默认、上下界、听感作用与边界。省略时补默认值，未知字段、布尔值、浮点和越界值均拒绝。下面括号内为合法范围。

| ID / 用途 | 默认参数 | 原创声音构成与创作选择 |
|---|---|---|
| whoosh / 掠入 | duration 560 ms（150–1000），pitch 410 Hz（180–760），tone 58%（10–90），travel 66%（0–100） | 两个经过不同频带整形的噪声层，一条随运动上行的弱滑音；前后包络配合左右声像。时长匹配移动过程，亮度决定高频气流占比；密集旁白下宜收暗 |
| impact / 轻落 | body 115 Hz（55–180），punch 48%（5–90），tail 370 ms（120–650），space 24%（0–80） | 主体下滑到 body，共鸣上叠短暂泛音，左右不同延迟形成早期反射。降低 body 增加低沉感；punch 单独控制触点，space 减少时落点更贴近画面 |
| click / 圆点 | pitch 830 Hz（380–1300），hardness 55%（5–90）；固定 65 ms | 短滑音配快速衰减的非整数倍泛音，软硬同时改变起音速度和泛音幅度。按钮可用，密集台词和快速重复时应听完整上下文 |

[sources.json](sources.json) 分别保存每个版本的完整参数、recipe_version、DSP 版本、源码摘要、NumPy/Python 版本、平台、uint32 seed、48 kHz 双声道 PCM16 编码、规范 JSON 的 spec_sha256 及实际 WAV SHA-256。本实验种子 1248，只有噪声配方消费 PRNG；另两声的音色来自确定的方程。正式身份宜只包含实际影响产物的依赖与不可变 DSP 包摘要；描述文字与用户显示名无需使全部音频缓存失效。相同环境已验证逐字节一致；跨 CPU、FFT/数学库版本须靠 golden WAV 确认。固定成品是历史交付依据。

## 5　实测、二次修改与听评

下表均用实际 WAV 回读。TP 为仓库现有 FFmpeg 分析器的真峰值；RMS 与末尾 RMS 单位 dBFS，尾窗为最后 5 ms。每个文件首尾各声道采样值均为 0；相邻起始样本最大变化 21 LSB，末端变化均为 0。六个文件在 PCM 满幅及仓库 0.999 阈值下削波样本数均为 0。独立 4× 重采样估计也保存在 [测量明细](measurements.json)；[现有分析器输出](existing-analysis.json) 中的 snapshot_id 是测试标识，未创建数据库行。

| 可播放 WAV | 时长 ms | Peak / TP | RMS / 尾窗 | 单参修订的实测结果 |
|---|---:|---:|---:|---|
| [Whoosh 默认](whoosh-default.wav) | 560 | −12.52 / −12.5 | −27.68 / −92.79 | 功率谱质心 1884 Hz |
| [Whoosh 收暗](whoosh-rev.wav) | 560 | −17.20 / −17.2 | −31.15 / −92.79 | tone 58→22，质心降至 656 Hz；同时变轻，不能把电平差全归因于音色 |
| [Impact 默认](impact-default.wav) | 370 | −10.75 / −10.7 | −23.76 / −71.52 | 主谱峰 116.2 Hz |
| [Impact 低沉](impact-rev.wav) | 370 | −10.67 / −10.7 | −23.57 / −72.71 | body 115→75，主谱峰降至 75.7 Hz，电平变化小 |
| [Click 默认](click-default.wav) | 65 | −14.13 / −14.1 | −25.96 / −64.76 | 起始样本步进 21 LSB，质心 915 Hz |
| [Click 变软](click-rev.wav) | 65 | −16.50 / −16.5 | −27.21 / −64.76 | hardness 55→14，起始步进降至 9 LSB，质心 879 Hz，主谱峰仍为 846.2 Hz |

[六份 WAV 完整 SHA-256](repeat.txt)；重启 Python 再生成六份，shasum 全部 OK。短 Click 和 Impact 的 integrated LUFS 在现有分析器中均报 −70，实测有声且峰值显著，应看时间窗和瞬态。每次 afplay 都完成，已提供可重听的默认/修订对照。人工验收应在相同播放增益下听原文件，再做等响对比，最后带旁白和 BGM 听短音是否压字、响尾是否拖入下一拍。样本命名描述的是设计意图和已测参数变化。

## 6　同步实验证据

[sync.py](sync.py) 输出三秒 640×240、30 fps 的 H.264/AAC 样片。第 30–42 帧标题沿三次缓入缓出曲线从 x=20 到 320，第 36 帧附近速度最大，第 42 帧落定，第 65 帧按钮变色。逐帧解码核验标题实测位置（误差 ≤2 px）及首次按下帧。音轨含仓库 I6 已有 BGM 和 “Blue comes first.” 固定旁白；输入摘要、两轨混合峰值和 90 帧观测在 [sync.json](sync.json)。旁白从 0.76 s 起，覆盖入场和落定。

| 目标动作帧 | 文件起点帧 / 样本 | 源内幅度峰样本 | 实际 AAC 中参考峰相对画面 | 匹配相关系数 |
|---|---:|---:|---:|---:|
| 36 / 掠过最快段 | 27 / 43200 | 15112 | +14.833 ms | 0.395 |
| 42 / 标题落定 | 42 / 67200 | 586 | +12.292 ms | 0.667 |
| 65 / 点击 | 65 / 104000 | 262 | +5.458 ms | 0.984 |

每帧 1600 个音频样本。按“目标动作时间 − 源内标志样本 / 48000”求理想入点，round-half-up 取最近执行帧。相对实际解码视频 PTS，在混合 AAC 的预期窗口 ±50 ms 内对已知源做互相关，得到偏移 0、+4、0 个样本，再加源内峰位置。Whoosh 与旁白重叠，相关性较弱；这些数是已知源模板的定位结果。幅度峰也只是此样例的同步标志，设计时可选择能量包络峰、接触点或前导。混前线性总和峰 −11.02 dBFS，回读 AAC −11.00 dBFS；没有正式 Renderer 的 loudnorm 处理。正式版要在 AAC 和整片响度处理之后复核。

正式 Agent 从 inspect_timeline 取得版本、轨道、场景与旁白窗口；inspect_clip 取得标题全局区间及支持的局部变换关键帧，将局部 tick 加到 clip 起点，用实际 easing 找速度峰和落定点。帧率须取版本的有理数，沿用 editing/timing.py 的 [start,end)、源 90000 ticks/s、版本 timebase 和 round-half-up。再用 preview_range 看目标前中后，无法读出的烘焙动画用实际视频观测；无法定位时缩小采样窗口。帧级执行无法保证任意峰样本精确命中；短于一帧的窗口、首帧前无预卷、末尾越界均须在编辑回执中处理。自动识别任意视频、正式预览与 Output 同步一致性仍待验证。

## 7　保留、收窄与退役裁决

| 位置 | 当前消费者和真实职责 | 复用、替代与处置 | 错退风险或验收条件 |
|---|---|---|---|
| providers/freesound.py，tools/video/sfx.py | search_sfx_seat/import_sfx_seat。限 Freesound HTTPS 主机，有大小与超时限制，检查 CC0、预览 MP3、作者及来源；真实录音用于难以合成的拟音和环境声 | 保留为可选外部来源。Recipes 承担产品/MG/解释视频的常见短音 | 删掉会丢失真实现场质感与旧来源溯源；候选授权到导入时可能已改变 |
| chat/turn_tools.py 的 search_sfx/import_sfx；chat/plan_turn.py、video_turn_seats.py | 搜索只出候选；导入从已持久候选集/member 解算，复核归属、许可、真实字节，固定 Asset 和 Snapshot。二者均不落轨 | 保留能力，收窄到明确要外部音源的上下文；若重新投影，要实测 Provider、卡片选中和导入 | 不能从自由 URL 或历史助手文字获得导入授权；搜索、导入、应用不能共用成功状态 |
| chat/sfx_intent.py 与 prompts/chat/sfx_intent.j2 | search_sfx_seat 真实 await sfx_intent_agent.call(user_text=...)；允许 search/add/replace 才调用供应商，分类异常/否决会返回，不是单凭命名猜测的死码 | 新 recipe 路径不接这个前置模型。外部搜索的明确请求、权限和费用边界由主循环及服务端事实承接并验证后，退役专用分类调用与模板 | 过早移除会放开未经请求的外部搜索；保留为通用门禁会重复推断、加延迟与模型费 |
| chat/perception、turn_tools.py、tools/video/music_candidates.py | search_music 查可访问曲库；show_music_candidates 投影可试听候选，select_music 校验持久候选身份并返回 Music ID，prepare_video_materials 再固定 | 保留 BGM 能力；普通编辑轮尚缺候选工具真实入口，应单列其可发现性 | 仅 mood/序号不能固定曲目；保护历史曲目和归属，导入后的角色映射需验证 |
| tools/music/score.py、beats.py、tools/video/music_preparation.py | generate_music → MediaJob → ScoreSpec、WAV、分析、曲目/快照；启动策展对账及工具消费 beat 数据 | 保留乐谱及节拍语义，仅复用生成基础、固定与恢复纪律 | 把每个 SFX 都登记为曲目会混淆选曲、beat snap 与试听 |
| pipeline/routes/music.py、pipeline/music.py | Persona 音乐面板显式 POST /api/v1/music/generate，请求内调 MiniMax，创建 is_public=True 曲目；不同于项目的 MediaJob 音乐生成 | 收窄在仍消费的深链；待项目内可替代其用户目标、权益和可见性后再退役旧付费入口 | 当前不具备项目报价、配额和 prompt 去重；重试有费用/公开性风险，不能拿来生成 SFX |
| apps/web/src/components/persona/music-panel.tsx、skin-editor.tsx | 旧 Persona 深链仍可试听、选曲、写皮肤默认；历史 Output 的 render_spec.music 还参与曲目删除保护 | 保留历史读取/删除保护；深链的默认值只在其消费者内生效，主作品沿用版本内固定源 | 不能让默认曲重开用户明确关闭的音乐；先核对存量公开/私有曲、旧作品和调用入口再删 |
| editing/audio.py、aligned_narration.py、revisions.py | instantiate_music_bed 服务对齐旁白组装的循环音乐床和首尾包络；_add_audio_effect 由 expand_revision_op 展开，使用场景窗口和固定旧轨；fixed_audio_ops 同时供当前 insert_audio | 保留共享 ops 和尚有消费者的 BGM 辅助；旧场景动作在消费者迁走后才退役，不重新对模型暴露 | 旧方法假定部分时基相同、依赖 scene/固定轨与参数散列，直接挪用会在非默认时基、跨场景、重叠时出错 |
| tools/video/audio_playback.py、chat/editor_media.py；前端 AudioCandidateSurface、AudioPlaybackSurface、WaveformPlayer | 候选试听与已固定音频回执用途不同。后者验证分析和签名资源；转录 live/history 均需可回放。_record_audio 现按 music/否则 narration；前端类型及标签也只有这两种 | 共用播放器与 SourceSnapshot 端点；正式扩展 effect 角色、用途标题、实测 peaks 和重开链接，不以候选装饰 bars 顶替分析 | 否则 SFX 会显示为旁白。单个源在浏览器能播不足以证明整片听感；所谓 Inspector 应以当前可操作入口实测，不能从合同推定已可调 |

## 8　推荐的最小正式施工切片

**给标题飞入加柔和 Whoosh，落定加轻 Impact，旁白保持清楚。** 选择有真实旁白、BGM 和可检查变换关键帧的已有作品作为唯一首例。初始内置 Whoosh、Impact 两个配方即可走通该旅程；Click 是本轮另一个已留证的开发样例。配方用途可以由创作 Skill 指导，Native Tool 负责制作，Agent 保留判断。与 MG 共用能力描述、固定来源和作品版本，底层计算仍走各自媒体实现。

1. 用 inspect_timeline/inspect_clip、局部预览确认版本、标题、最快段与落定帧、字幕/旁白字头和 BGM。为有旁白处选择暗一些、短尾的参数，优先调 SFX 的 Clip 增益。确需局部避让时使用现有 audio.gain 包络并复听；未经要求保留旁白及 BGM 原样。首例不引入持续自动 sidechain。
2. 在现有媒体工具中增加一个有界 recipe 生成动作，由按 recipe_id 区分的封闭参数 Schema 提供用途和默认值。支持从“这个 Clip”的固定来源读出旧版本及规范参数，再提交差量并展开为完整的新参数。拒绝模型任意代码、外部 URL 和跨项目源。将该种类贯通投影、禁止生成约束、editor_media 的授权/回执、media_quote、KINDS、worker 分派、Stop 和恢复。当前 worker 的兜底分支会按音乐解析，单加注册名会出错。
3. 现有 MediaJob 产出有界 WAV。用 store_source_bytes 固定规范化配方 JSON 和音频；用实际解码样本数换算源 ticks；register_snapshot 写 project/owner 限定音频、origin.kind=sound_recipe、recipe_ref/digest、DSP 身份、分析引用；回执关联 job、snapshot、audio digest、时长及可用于定位的源内标志。项目授权与筛选在返回资源时再核验。已有 Asset 用于上传/外部导入，此切片可用 asset-less 项目快照，不引入独立配方库表。
4. 复用 insert_audio/fixed_audio_ops，处理相同角色音效重叠时选择可用轨；保存后回执含音效 Clip/Object ID、版本及实际位置。首例可在编辑观察中记录依据的标题 Clip ID、关键帧与 cue 偏移，后续以当前版本重新解算；若产品要求标题移位时音效一起动，必须另验现有链接/移动语义，本切片不承诺持续约束。
5. 次轮“只把落定这一声改低沉”读取被点名 Clip 的旧源，复用同一配方版本及 seed，只改 body。保留原 WAV，固定新 Snapshot，再 BindSource + UpdateClip(source,必要时 range)，携带 base version、精确 clip_id 和预期旧 snapshot/digest；保留 Object ID、增益、动画和其他使用同源的实例。现有 bind_clip_source_ops 只接待绑定图片生成器和特定待对齐 Speech，直接对 AudioObject 调用会拒绝。可扩展该动作的定向音频分支，勿放宽原旁白匹配。若新时长不合原窗，按已确认落点裁/调目标窗，重新校验前后邻居、边界和锚点；不能静默挤动邻片。
6. “声音太大了”只对现有 AudioObject 发 UpdateClip(object=保留身份并调整 gain_db)，普通工具需可表达此属性。继续复用唯一写口、版本基线与重复提交保护。预览时单源检查音色，再听包含旁白和 BGM 的真实范围；导出后按精确 Output 审片，记录是否真的向具备听觉的模型或人提供了音轨。Renderer 的两遍响度处理允许失败后保留原文件，故须测最终交付文件本身。

### 五面真实签收条件

| 面 | 必须保存的证据与通过条件 |
|---|---|
| Tool | 真实 Provider wire schema/工具清单及 native call ID；首轮选中两种正确用途、参数与边界，二轮只改目标的一个参数。混入非法字段或越界值被拒绝；仅降音量的请求不创建媒体作业 |
| Prompt/Context | 同轮可见实际 base_ref、标题/关键帧位置、source 与 output 时间、已有音轨/增益、权限和是否允许生成。观察回执包含版本、观测窗、可用声道/模型能力，缺证时不能宣布听过 |
| Chat | 真实 Activity 和已固定/已落轨/已导出状态分别对得上持久记录；显示 effect、可播源、修订和费用，刷新后链接重新签发，play/seek 有真实进度。独立素材与整片分别盲听，检查两轮差异、旁白逐字可辨、连续点击疲劳 |
| Execution/State | 两个来源均有规范 spec 与 WAV digest、完整解码报告；同一版本快照可重复播放。第二轮只替换目标 Clip 的源，其余视频/BGM/Voice/另一个同源实例及旧版本比对一致。检查重叠轨有效、预览及最终 Output 解码的实际时序（此首例建议落点偏差 ≤ 半个 30 fps 帧）、峰值/真峰值和掩蔽，记下实际播放装置与听评人 |
| Recovery/Replay | 真实隔离项目对同一 opening/call 重放、并发、Stop、强杀与恢复；对照 Job/claim token、spec/WAV/Snapshot、Clip、版本、Activity 及账本。每个用户授权的实例只新增一次，无重复 hold/capture。用户明确要在另一位置复用仍能单独插入 |

### 费用、性能和中断

在本机用 25 次连续生成取三组最快均值，Whoosh 约 1.92 ms、Impact 0.65 ms、Click 0.15 ms（含规范来源构造，不含排队、持久化和分析）。最大配方 1 s，48 kHz 双声道 PCM16 约 192 kB/s；实际 WAV 为 12,524–107,564 字节。本机样本不可当生产并发 SLA。本地合成没有媒体供应商费用；模型决策、存储、导出仍按既有计量。正式零积分由 quote/settle 回执表达，受请求授权、取消和配额约束。

| 中断/重复情形 | 建议处理及验收断言 |
|---|---|
| 重复 Tool Call、同参不同落点 | 区分执行身份、项目内来源缓存键、编辑调用身份。重放原调用返回原回执和版本；第二次合法插入可共用固定音频并得到新 Clip ID |
| 同参并发或过期 worker 迟到 | 以 owner/project/规范 spec digest 单飞或原子争用注册。不要依赖对象存储 exists→save 无锁检查。冲突后重读并验证 spec、字节和完整解码；过期 token 无权提交成功或结算 |
| WAV 已写、API 被杀、快照或回执尚未写 | 原 job 重新认领，按确定性身份找已固定字节/快照/分析补齐；若仅有孤立字节，校验来源、owner、项目及 digest 后续写。已固定结果优先回放。Snapshot 已提交而 manifest 缺失也需修复，不能以成功 URL 作为成功编辑 |
| Stop 在排队/执行/生成后到达 | 各时点注入 Stop。令牌失效、释放适用预占、禁止迟到插入/结算；已提交的版本及可核实固定源按真实结果呈现。允许保存媒体而作品未改 |
| 未知结果、收费供应商或跨版本恢复 | 本地确定性合成可在原身份内核验/有界重算；外部提交后结果未知保留现有 unknown/reconciliation 语义及适用预占，不能自动再提交或宣布零成本。已有明细早于 Stop/强杀时以账本核对，不重复扣费 |
| MediaJob 成功后版本被其他人修改 | 媒体准备和编辑是两次独立事实；检查 base version 并重新 inspect。禁止对已换源的目标盲写，原固定结果仍可引用。已有 committed edit 由原调用恢复，不重新生成或重复插入 |

## 9　复现与证据保存

研究包内的源码、参数、WAV、视频和回执统一列在 [SHA256SUMS](SHA256SUMS)。该文件记录本报告摘要；不对它自身求递归摘要。独立复核请先核对交付摘要，然后复制到新建临时目录运行，保留原件。以下命令使用本机现有仓库环境；REP_REPO 可指向上述提交的只读副本。

```sh
cd /tmp/repurposer-audio-wwrSsj
shasum -a 256 -c SHA256SUMS
audit_dir=$(mktemp -d /tmp/repurposer-audio-replay-XXXXXX)
cp *.py repeat.txt "$audit_dir/"
cd "$audit_dir"
export REP_REPO=/Users/sylas/repurposer
py="$REP_REPO/apps/api/.venv/bin/python"
"$py" -B render.py
shasum -a 256 -c repeat.txt
"$py" -B inspect_audio.py
PYTHONPATH="$REP_REPO/apps/api" "$py" -B verify_existing.py
"$py" -B compare.py
"$py" -B sync.py
afplay comparison.wav
open sync.mp4
```

reference_probe.py 另需网络、Chrome 和 Playwright，记录上游在线站当时的播放节点；站点更新后以旧回执为历史证据。同步验证每次重新解码输出，codec 版本或编码器变化时应比较时序、样本事实与已交付输出，不能预设跨环境 MP4 字节必同。

**证据保管与唯一下一步。** /tmp 会清理。统一产品架构评审时，用 SHA256SUMS 校验后，将原创源码、catalog、规范来源与实际媒体摘要、六份 WAV、实测和同步回执、运动数据、依赖版本及输入 fixture 摘要一起保存到获准的版本化测试证据位置；参考站仅保留链接和观测。正式验收另外保留真实 Provider 请求、Job、账本、版本差异、Output 与签字听评。建议评审的唯一施工候选是上面的“带旁白的标题入场和落定，再单独调低 Impact”。研究到此停止，等待统一评审与正式集成授权。
