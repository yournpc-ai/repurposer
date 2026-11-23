# Sound Recipes 独立复核 · 2026-11-23

**Sound Recipes 研究阶段通过，二次声音校准已取消。** 用户确认 Whoosh、Impact、Click 三组 A/B 均有明显可辨的差异，每组两个版本都可接受。此前反馈中的“差异不明显”指用户未选出偏好的版本。用户确认三秒样片声画同步自然，旁白清晰可闻，没有被遮盖。

从仓库根目录运行以下命令。脚本在临时目录中合成、测量、制作并重新解码视频，标准输出可与签入结果比较。

```sh
study=docs/experiments/renderer-aac/audio-study
(cd "$study" && shasum -a 256 -c SHA256SUMS)
apps/api/.venv/bin/python -B "$study/replay.py" > /tmp/sound-recipe-replay.json && diff -u "$study/replay.json" /tmp/sound-recipe-replay.json
```

## 来源、基线与权限

本地 main 和 GitHub main 在提交前核为 bdedeff56fdfe2d4bf78d22968d8ac6c5cce7609。用户给出的 2f02da61 之后，a0d354d1 已归档原包，bdedeff5 已记录 AAC 候选修复反例。核对时三个 Renderer 文件有未暂存修改。研究依托现有 audio-study 目录，保留历史报告、失败和摘要原件。本轮从原始临时包逐项验证清单，比较了仓库副本和 I8 复产副本的共有文件。

|实际来源|核查结果|
|---|---|
|/tmp/repurposer-audio-wwrSsj|25 项摘要通过，含配方源码、参数、六声、同步片、对照声、原始日志；完整目录与 Git 归档一致|
|/tmp/i8-aac.FohV07/recipe 与同级 REPORT.md|复产源码、WAV、参数、测量与同步片共有文件相同；两份额外日志记录 I8 的重测。其报告中“尚未入库”对应历史基线|
|本包三种 SFX|检查 render.py 与 catalog.py，原研究声明独立编写。仅从方程和带 seed 的噪声生成六声，未读入第三方预设或样本。版权链未做独立法律审计|
|同步片|背景与旁白来自仓库 iteration-6 的 sample-generate_music.wav 和 sample-generate_voice.mp3；固定摘要见 sync.json。其用途为既有研究夹具，商业公开分发授权未验证。本次提交仅新增复核说明、脚本和读数|

重读 CLAUDE.md、PROGRESS §0、new-agent 的五面合同、i8 的现役能力与缺口、VIDEO_PROJECT 的 §0、时间与来源绑定、MUSIC_ARCHITECTURE、RENDERING 以及 VERIFICATION 的执行、恢复与人工验收边界。以下代码路径均相对于仓库根。

## 三组声音与复现边界

[参数合同](catalog.json) 逐字段列出整数类型、单位、上下界、默认值、听觉作用和边界提示。[合成源码](render.py) 与 [参数定义](catalog.py) 保留原文件身份。所有配方旋钮都作用于源，改值后重制固定 WAV。默认 uint32 seed 为 1248，仅 Whoosh 消耗 PCG64 随机数，零和最大合法 seed 都只选择不同噪声实现。单次播放音量使用 AudioObject.gain_db。缩短自然衰减需改源参数，剪掉片尾才用 Clip 源窗。每次取值、算法版本、源码摘要和六份 WAV 的完整 SHA 见 [固定输入及输出身份](sources.json)。

|意图|单字段修订|同长度默认及修订实测|
|---|---|---|
|Whoosh 更柔和|tone 58 → 22%|560 ms，功率谱质心 1883.8 → 655.8 Hz，RMS 同降 3.47 dB|
|Impact 更低沉|body 115 → 75 Hz|370 ms，主谱峰 116.2 → 75.7 Hz，RMS 变化 +0.19 dB|
|Click 触感更柔和|hardness 55 → 14%|65 ms，起始步进 21 → 9 LSB，质心 915.1 → 878.9 Hz|

两个独立 Python 进程合成，逐一核验完整 WAV 摘要，再通过 PyAV 全量解码，与归档 WAV 的原始 PCM 双声道数组逐样本比较。随后复算 catalog、sources、measurements、同步片及逐帧记录，全部字节相同。六声为 48 kHz、立体声 PCM16；零满幅样本，首尾均为零，末端相邻差为零。末 5 ms RMS 为 −92.79 至 −64.76 dBFS。绝对 DC 最大 0.00006915 FS，内部相邻步进最大 0.0770 FS，见逐声道和逐文件读数。这些读数用于检查截尾、越幅或异常跳变。[声学指标](measurements.json) · [PCM 哈希与新增读数](replay.json) · [试听对照](comparison.wav)

已验证环境为 macOS 26.5.2 arm64、CPython 3.11.14、NumPy 2.4.6、PyAV 17.1.0、Pillow 12.3.0；各 libav 版本见 replay.json。单独合成只需前两项软件。运行完整复核需要仓库内上述两份媒体夹具。其他 FFT、CPU、编码器或字体环境的 WAV/MP4 字节一致性未验证。

## 同步与重叠

独立 PyAV 样片长 3 s、30 fps，每帧 1600 个采样。BGM 从 0 起，旁白入点 36480，Whoosh 入点 43200，Impact 入点 67200，Click 入点 104000。帧 42 标题到达 x=320，帧 65 按钮变色；逐帧解码验证 90 个位置。各 SFX 模板在 AAC 的匹配滞后分别为 0、+4、0 个采样，计入源内幅度峰后相对对应视觉事件为 +14.833、+12.292、+5.458 ms。运动声模板相关仅 0.3945，幅度峰位置也含帧量化。[同步样片](sync.mp4) · [逐帧证据](sync.json)

复核脚本按独立固定入点重建三秒 PCM16 参考，记录 WAV 摘要，检查实际视频解码音频 PTS 连续。在两声重叠的 [67200,70080) 区间，分别移除 Whoosh、Impact、旁白或 BGM 后，相对成片的均方误差分别上升 4.90、42.97、28.06、22.46 dB。该 60 ms 窗口内四个声部均有可测贡献。

正式 Renderer 的旧调查记录有声部晚 2048 采样。候选修复的 25 fps 反例在响度成功后出现 1024 采样内部间隙，尾段晚 21.333 ms。本次未走生产 Renderer，生产缺陷状态依据 I8 的留证。配方重合成只对无损源做确定性判定。[原始失败](../REPORT.md) · [候选反例](../CANDIDATE-REVIEW.md)

## Sound Lab 与授权

上游 main 核为 701a8acc34f718b305d1ff0cc7d4700df0e1f1c9。其 Recipe 组合振荡器、噪声和可选采样层；每层有入点、增益、包络、滤波及声像。Pitch 按半音缩放频率，Length 缩放主体及层内时间，Tone 改变明暗，Space 调混响量与尾窗，Punch 改瞬态。OfflineAudioContext 合成固定缓冲。噪声与卷积可用种子；试听时 sample take 可随机选择，想重建一次变体需要保存实际选项、参数和渲染环境。可吸收的是从听觉意图到可测参数的映射。[产品说明](https://www.reactbits.dev/tools/sound-lab) · [合成器与变体实现](https://github.com/DavidHDev/react-bits/blob/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/src/sounds/ts/react-bits-sound.ts)

MIT + Commons Clause 对随产品使用导出成果、单独分发工具或声音、以及托管工具或实质相似副本分别作出规定。允许商用成品内使用导出物，限制单独再分发声音包和托管复制品。当前六声来自上述原创 DSP，归档未引入上游代码、导出物或预设。[许可原文](https://github.com/DavidHDev/react-bits/blob/701a8acc34f718b305d1ff0cc7d4700df0e1f1c9/LICENSE.md)

## 回到现有 I8 剪辑循环

|面|当前代码与最小映射|
|---|---|
|Tool|chat/editor.py 注册 generate_music，tools/music/score.py 接受 duration_seconds、style、bpm、name，生成有节拍与编排的器乐。pipeline/media_jobs.py 和 tools/video/music_preparation.py 固定 WAV 与 ScoreSpec。普通 SFX 可取用户音频或获准导入的外部源，制作完才可插入。insert_audio 的必填项为项目内音频快照 source_id 和非负 start_seconds，可选正数 duration_seconds（缺省全长）与 gain_db（默认 0，−60 至 +12）。源从零开始、原速，须容纳于作品及源窗口。当前 trk_editor_effect 固定选轨，editing/validators.py 拒绝同轨相交。建议先选稳定顺序中窗口空闲的 effect 音轨，均占用才复用 AddTrack。|
|Context|editing/sources.py 以 owner、Asset 或稳定来源身份、种类与字节 digest 注册不可变 SourceSnapshot，并保存 storage_key、duration_ticks、项目和 meta。建议把配方 ID、版本/代码摘要、完整参数、seed 与 WAV digest 随源固定；inspect_clip 从目标 Clip 的快照读回。版本和目标身份用于消除“第二个”的歧义。|
|Chat|现有 editor_media、tools/video/audio_playback.py 与播放卡可回读固定字节；在同轮呈现该声及 preview_range 的混音窗口，刷新按持久回执回放，区分已制成、已写入版本与已交付。实际听过才记录主观结论。|
|Execution|editing/revisions.py 的 fixed_audio_ops 按需绑定源、建轨并加 Clip。schemas.py 的 Clip.range 是作品 ticks，ClipSource 带 snapshot_id、snapshot_digest、source_range，AudioObject 保存 object_id、gain_db。建议复用现有来源准备与 MediaJob 授权/费用边界；替换第二个 Impact 时，经 editing/store.py 的 apply_composition_edits 校验 base_version，仅重绑该 clip 的来源并校验源窗，保留 clip/object ID、入点和 gain。另两处和旧版继续引用旧快照。editing/video_spec.py 编译并核对摘要；packages/video-remotion/src/Video.tsx 让各轨同时播放，线性增益乘局部动画。整片经 apps/render/src/video/index.ts、audio.ts 及现有 ExportJob 处理、授权交付。|
|Recovery|沿用 editor_recovery.py、媒体回执、执行 token/lease、Stop、预占与结算。明确区分源已保存和编辑已提交。相同任务恢复时校验 owner/project、字节、配方与版本；对已提交写入重放，对过时基线重新定位，对外部结果未知保留核对。旧 Output 固定原版本。|

设计增量限于来源元数据、既有工具的选轨/单实例操作和相应消费者。没有产品 Schema、运行时、时间线或作业改动。本轮仅在本机制作研究证据，未测试正式报价、结算、并发写入或恢复。Sound Recipes 的正式 Chat → Native Tools → Audio Clip → 单实例续改与恢复链路尚未实施，留待后续 I8 集成任务。
