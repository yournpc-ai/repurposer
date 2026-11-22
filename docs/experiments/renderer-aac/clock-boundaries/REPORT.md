# I8 · AAC 两项时钟反例定向根因报告

**两项第一错误边界均已定位。两项隔离修正分别通过对应反例，现有生产候选仍未通过，未授权合并。**

## 基线与范围

开工看到本地 main 为 bdedeff56fdfe2d4bf78d22968d8ac6c5cce7609。调查期间本地与 GitHub main 同步到 db8ffbed45acf41773562c5d6c451d598e8d701e，该次增量仅有 audio-study 三份研究文件。归档前本地又增加独立 MG 研究提交 2bea062aaef27e8c5bb4a54ac58b603c9200a7f1；当时 ls-remote 的远端 main 仍为 db8ffbed。主工作树的 artifacts.ts、audio.ts、video/index.ts 三处未暂存修改从开工到提交前的 diff SHA-256 一直为 73201f85a05af650f13c03db1c7df9f89c030d36a94e912a4056de5911765786。未进入其他 Agent 的工作树。

实验使用 Remotion 4.0.484、compositor FFmpeg n7.1 和固定源。Linux 使用本机 linux/arm64 镜像 repurposer-render，镜像 ID 为 sha256:2690f95bdf32c950df2ecea68a26a82b1a46025527b1049fe8a3718d932469ee。生产候选快照在 production-candidate-at-start.diff，两份增量 proof.diff 只应用于隔离副本。原始 argv 中的临时路径属于当次采集环境。

## 25 fps / 199 帧

作品应呈现 382080 个 48 kHz 样本，即 7.96 秒。保留的基线 SHA-256 与上轮一致。以原第二遍参数加 -debug_ts、-stats_enc_pre:a 重放，失败 MP4 的 SHA-256 也与上轮一致。按独立模板定位三个声部，另在实际帧 PTS 上放置 PCM，核验末段旁白。

|观测边界|实测|
|---|---|
|基线 AAC/MP4|首 PTS/DTS −2048，skip 2048，有效 382080。解码器返回 382976，含 896 个尾部补齐样本；内部无间隙。|
|独立解码与升采样探针|48 kHz 的 382976 样本连续；单独升至 192 kHz 后 1531904 样本连续。|
|动态 loudnorm 原生 192 kHz 输出|上一块 PTS 960000，长度 15104，下块应从 975104 开始，实际从 979200 开始。**首个间隙为 4096 个 192 kHz 样本**，出现在短块与末尾 556800 样本大块之间。|
|降回 48 kHz|上一块从 239984 开始、长 3776；应接 243760，实接 244784，间隙 1024。|
|真实 native AAC 编码器输入|上一帧 PTS 243712、长度 1024；应接 244736，实接 245760。|
|成品|首 PTS/DTS −1024，skip 1024。有效轨长 384000，实际内部间隙 [244736,245760)，声部入点无误，末段晚 1024 样本，音轨多 40 ms。|

原生滤镜边界由相同滤镜参数输出至 192 kHz PCM 的诊断支路测得。逐块证据使用封装前采集的 PTS 和实际 samp；回读 PCM MOV 可能重分包。原失败命令的编码器输入独立实录。以上证据把首错钉在动态 loudnorm 尾部输出，未进一步断言某一行 FFmpeg 内部实现。

第二遍实际滤镜 L 为：
`loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-20.77:measured_TP=-7.87:measured_LRA=13.80:measured_thresh=-31.20:offset=0.02:linear=true:print_format=summary`。首次分析取得测量值；第二遍日志显示实际走 dynamic。失败命令以 baseline.mp4 为输入，`-c:v copy -af L -ar 48000 -c:a aac -b:a 192k` 输出 MP4。

**失败对照**：仅在 L 前加 `atrim=end_sample=382080`，编码器收到的内容长度恢复 382080，但尾段滞后变成 1920 样本，有效轨长仍为 384000。仅裁掉解码尾块不能解决短块交接错误。

**成功对照**：取已核验基线的有效音轨样本数 N，第二遍使用 `atrim=end_sample=N,apad,L,aresample=48000,atrim=end_sample=N`。前裁排除 AAC 尾块补齐，补零使滤镜在作品边界之前不用刷新短尾块，后裁明确限定输出。整条路径仍由 FFmpeg 原生滤镜求值；没有重写 PTS 或固定提前采样。首次测量及视频流复制沿用原路径。该 proof 对基线要求 time_base=1/48000、sample_rate=48000、duration_ts 为正整数。

结果为有效 382080、首 PTS/DTS −1024、skip 1024、无内部间隙。Voice、Whoosh、Impact 及末段相关滞后均为零；199 个视频帧 PTS 和源身份均正确，H.264 载荷不变。**响度复测**：基线 −20.77 LUFS / −7.87 dBTP；失败和修正成品均为 −16.25 LUFS / −3.21 dBTP。解码器仍返回 382976 个样本，末尾 896 个超出有效轨长。正确性判断以有效窗与实际 PTS 为准。

完整命令、.samples、逐帧与逐声部统计、原始/失败/修正 MP4、原生滤镜 PCM 和两份压缩 debug 日志在 audio/。probe.py 用 FFMPEG 环境变量指定锁定二进制；在临时副本运行。measure.py 的命令格式为 `python measure.py SPEC.json 固定素材目录 媒体文件...`，素材可取本仓 mg-render/baseline/assets。

## Linux 30 fps / 240 帧

Linux 的并行预编码先产生一个仅含视频的 pre-encode.mkv。逐帧读取实际 PTS，前三帧已是 0、33、67 毫秒。**时间精度第一次损失在 H.264 并行预编码写入 Matroska 时；1/16000 第一次出现在后续的 mix.mov。** 将前者写入后者时，528/16000 与 33/1000 指向同一时刻。

|实际文件|原候选时基；开头四帧 PTS|隔离修正时基；开头四帧 PTS|
|---|---|---|
|预编码临时文件|Matroska，1/1000；0、33、67、100|MP4，1/90000；0、3000、6000、9000|
|mix.mov|1/16000；0、528、1072、1600|1/90000；0、3000、6000、9000|
|首次封装的 baseline.mp4|同 MOV|同修正 MOV|
|响度后 final.mp4|同 MOV|同修正 MOV|

原命令为 `-r 30 -f image2pipe -s 1920x1080 -vcodec mjpeg -i - -c:v libx264 -pix_fmt yuv420p -video_track_timescale 90000 -crf 18 -y pre-encode.mkv`。预编码阶段虽已传入 MOV/MP4 的 timescale 参数，实际 Matroska 轨道仍为 1/1000。接着以预编码视频及现有混音 WAV 为输入，用 `-c:a copy -c:v copy` 生成 MOV，再以 `-c:v copy -c:a libfdk_aac -movie_timescale 48000` 生成基线。响度阶段也复制视频。

**失败对照**：只在 MKV → MOV 时补 `-video_track_timescale 90000`，MOV 首帧组变成 0、2970、6030、9000，仍有 160/240 个 PTS 错误。换了刻度，并未找回精度。

**成功对照**：在隔离的 renderMedia 调用使用公开 ffmpegOverride，仅在有声候选的 pre-stitcher 回调中，在输出文件名前显式指定 `-f mp4`。保留 Remotion 给出的临时文件名和 90000 刻度；实读容器确为 MP4。其余阶段没有改命令。四级文件均有 240 个正确帧 PTS 和源编号，最大误差由 1/3000 秒降至零。新旧所有阶段的 H.264 包载荷 SHA-256 均为 da0db9784d8382a5d34427da90add8424e7231675e6887133b14f12936fe135c。修正成品音频有效 384000 样本、无间隙、三个声部及末段零滞后。没有增加视频编码次数。

linux/observed 和 linux/fixed 各自保留四级输出、完整 FFmpeg 子命令和逐帧数据。捕获钩子仅在实验进程内复制输入文件并记录 argv；参数调整由 renderMedia 公开回调承担。此前的修正假设“只调最终 MP4 timescale”现已被失败对照排除。两条 Linux 运行不是性能基准。

## macOS 八秒四出口回归

新起隔离进程运行实际 renderVideo，在响度成功路径启用音频滤镜证明，完成六次完整渲染，覆盖基线、响度成功、三种故障、两种正常跳过。多次渲染均在响度前独立留样。

|出口|本轮结果|
|---|---|
|基线 MP4|384000 有效样本，首 PTS/DTS −2048，skip 2048，声部和末段均对齐。|
|响度成功|384000 有效样本，首 PTS/DTS −1024，skip 1024，PTS 连续。−16.28 LUFS / −3.17 dBTP。|
|响度失败回退|分析和重编码分别真实退出 8，另一次在 rename 前抛错。三次交付的 SHA 均与基线相同，无残留 .encode-* 目录。|
|正常跳过|全零 WAV 有 384000 个静音样本；纯 Shape 成品无音轨。前后摘要分别相同。|

所有回归文件均为 240 帧，PTS 与源身份全部正确。新成功出口的音频再编码字节有变化，按时钟、质量及视频身份验收；失败回退按整文件字节验收。regression/media.json 记录每份输出摘要和实际测量。

## 已 prepare、尚待上传的缓存

同一合成 render_id 与正式 schema 解析后的 spec，通过 v1 renderArtifacts 在独立缓存根发布 ready 标记和真实旧 MP4，再以 v2 缓存逻辑和实际 /upload 路由读取。首次 HTTP 409、ARTIFACT_CACHE_MISS，本地 HTTP 接收端记录 0 次 PUT，旧文件仍可读取，摘要与准备样本一致。用 v2 renderArtifacts 为同一身份准备好有效候选样本后，第二次 /upload 返回 200，接收端记录 1 次 PUT。准备回调用固定媒体留样填充，两次均未启动重渲染。两个键及文件摘要见 cache/result.json。

源码路径上，Worker 正常先 prepare，再记录上传身份并调用 upload。两请求间切换到另一套缓存键会将 409 记录为 rejected；在仍持有租约且未被 Stop 等前提下，会结束为 failed，不会以该旧文件提交 Output。若尚未派发上传且重新进入 prepare，v2 可重新准备；已经派发、结果未知的恢复按对象身份核查。这里实测的是缓存和 HTTP 边界，Worker 终态来自源码；未重跑 DB、账本或恢复系统。切换部署应排空或将同一 prepare/upload 对固定到相同版本和同一缓存卷，直至在途请求完成。历史对象存储中的 Output 不属于此缓存。

## 裁决和归档

两项证明是各自反例的定向验证。未做两个 proof 的全平台组合发布验收、长片或全量五面重验。下一步仅建议架构评审这两份增量 diff 及缓存切换条件。生产候选继续保留为未暂存修改。研究文件均在本目录，SHA256SUMS 可在本目录执行 `shasum -a 256 -c SHA256SUMS` 复核。
