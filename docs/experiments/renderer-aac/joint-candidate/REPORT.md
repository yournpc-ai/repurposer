# I8 · AAC 联合候选评审

**Renderer 正确性未通过。** 两份已验证的调整可共同修正既知反例，但在正式编译的 24 fps / 191 帧作品上，Remotion 混音将两个声部的入点各推迟了 16 个采样。候选识别到基线音轨超出作品 16 个采样并终止。未启动 Chat 五面，也未申请发布。

## 基线与候选

开工本地与远端 main 均为 70822f2a38f04b77aea58275f991d9a3d4b637c0。归档的 57 项 clock-boundaries 内容逐字节通过原摘要校验。已有三文件 diff 的 SHA-256 为 73201f85a05af650f13c03db1c7df9f89c030d36a94e912a4056de5911765786。本轮在用户明确授权后仅增量修改 audio.ts 与 video/index.ts，原 artifacts.ts 的 v1 → v2 修改原样保留。candidate.diff 包含相对开工 HEAD 的全部三文件差异。另有并行 Agent 的研究文件，不在本轮提交范围。

已有有声路径使用 Remotion H.264/PCM MOV，视频 stream copy、libfdk_aac 封装为 MP4 基线，再选择性两遍响度处理。新增的首流探测复用原有 ffprobe 调用，读取 start_pts、sample_rate、time_base 和 duration_ts。要求零起点、48 kHz、1/48000、正整数有效长度 N，并与 Composition 帧数及帧率换算的最近样本相符。基线时钟不符会使渲染失败。正常无音轨与静音走原跳过分支；可选响度失败按现有日志回退到基线。第二遍执行 atrim=end_sample=N,apad,loudnorm,aresample=48000,atrim=end_sample=N；无固定采样补偿。

公开 ffmpegOverride 仅在有声 H.264 路径收到 pre-stitcher 回调时增加输出参数 -f mp4。Linux 实际仍获得名为 pre-encode.mkv 的临时文件，其内容为 MP4。锁定版本后续通过 -i 自动识别容器，复制视频到 MOV。依赖风险在于未来回调参数布局或消费者改按后缀选择解复用器；此证据仅覆盖 4.0.484。未改第三方包、安装目录、业务模型或混音实现。

## 新反例与首错

正式 Composition 校验与 compile_video_spec 接受 24 fps、191 帧固定作品，重编译 JSON 字节一致。选整数帧率是因为当前 Renderer 显式拒绝分母不为 1 的 fps。视频和音频的独立真值分别是 i/24 和 382000 个 48 kHz 样本。macOS 复跑同一失败得到逐字节相同的 PCM MOV 和 AAC 基线。

|声部|入点帧|预期采样|实际混音命令延时|实测采样及误差|
|---|---:|---:|---:|---:|
|Voice|7|14000|292 ms|14016，+16|
|Whoosh|34|68000|1417 ms|68016，+16|
|Impact|48|96000|2000 ms|96000，0|

Remotion 的 stringify-ffmpeg-filter 对 padStart × 1000 使用 toFixed(0)，再生成以毫秒为单位的 adelay。boundary/merged.wav-filter.txt 是本次真实子进程读取的滤镜文件。三路末端 padding 分别为 128000、258000、248000 个样本；前两路因入点取整分别结束于 382016，第三路止于 382000。amix 后的 audio.wav 为 382016 个真实 PCM 样本。WAV SHA-256 为 bae8ef9c2c1275e4fef5ae36e889560b15e411d07b6a43ef36608c8a2ea81334。参考互相关也测到 +16、+16、0。第一处偏差在现有 Remotion 声部合并，早于有声 MOV、AAC 和响度处理。

macOS 的 MOV 与 raw.mp4 均无内部音频 PTS 空洞，末段旁白晚 16 个采样。AAC 首 PTS/DTS −2048、skip 2048，轨道有效 382016，解码 382976。191 个视频 PTS 与源编号全部正确。守卫抛出 InvalidAudioClock，没有发布 video.mp4，正常异常处理清理 .encode-*。仅将末尾裁小 16 个采样仍会保留两个错误入点；本轮停在可验证首错。原媒体、混音前后 WAV、逐轨命令、spec 和摘要均已保留。

## 既知反例及四出口

25 fps / 199 帧的上轮失败为 382080 → 384000 有效样本、末段晚 1024，间隙 [244736,245760)。30 fps Linux 上轮视频为 160/240 个 PTS 错误，最大 1/3000 秒。逐件对照见两平台测量 JSON；frames 含每帧实际 PTS、实测源编号和预期编号，音频相关建立在解码后按每帧实际 PTS 放置的样本上。

macOS 的 25 fps 成品有效 382080，三个入点和末段零滞后，无内部间隙。基线与成品首 PTS/skip 为 −2048/2048、−1024/1024；成品解码含 896 个窗外尾样本。199 帧时钟与源身份全对。30 fps 基线及正常响度成品分别为 384000，三个声部和末段均对齐，240 帧全对。响度成功成品 SHA 与上一轮已测量响度的留样相同。分析失败与重编码失败各真实退出 8；另一次在文件替换前抛错。三个返回文件均等于该次基线。全零 WAV 保留 384000 个静音样本，纯 Shape 无音轨，两种正常跳过前后字节一致。

## 缓存切换

本机隔离 TMPDIR 模拟同一缓存卷。用旧源码的 renderArtifacts 发布真实旧 MP4 的 ready 记录，再运行真实 v1/v2 HTTP 上传路由，接收端校验 PUT 字节。故意错发给 v2 时 HTTP 409、ARTIFACT_CACHE_MISS、零 PUT；留在 v1 时 200 且一次 PUT，字节 SHA 符合旧文件。旧任务完成后准备独立 v2 身份，v2 返回 200 且一次 PUT，收到新文件的确切 SHA。缓存准备使用固定成品；未演练真实生产流量管理或外部对象存储。cache/result.json 包含两次 PUT 的身份及摘要。

可执行切换办法是维护窗口暂停新导出入口，保持旧 Worker、旧 Renderer 和原缓存卷服务，让已入队及执行中的旧任务走完上传、核对与终态。用现有 ExportJob 及上传回执核对 queued/running/unknown 均已排空，处于上传结果未知的任务先按已有对象身份核实；切换前确认没有新的旧 prepare。无法确认排空则维持旧服务。排空后切换 Renderer、再恢复新导出。不要把 v1 ready 请求交给 v2 重传。本轮演练局限于 HTTP 和缓存边界，未对生产限流或切流。

## 验收边界

Renderer 类型检查通过。实际 Execution 证据覆盖此处的固定媒体，正常退出与受控异常的文件身份及清理均据日志核对。没有以真实 Chat 和原生 ToolLoop 触发关联 opening、call、CompositionVersion、Output 的整条旅程。Tool、Context、Chat、正式 Execution、Recovery 五面均未签署；未触发 provider、云对象存储、付费或生产部署。研究提交只包含本目录。

唯一建议是先评审 24 fps 的声部入点取整边界，确定锁定 Remotion 的公开能力或上游修正能否保留采样级入点。在该反例通过之前，维持生产候选未提交。

## 复核入口

- boundary/boundary.json 由 tools/compile_boundary.py 用上一层目录的 mix.version.json、sources3.json 校验及编译。使用 API 环境设置 PYTHONPATH=apps/api，脚本参数是这两个文件的父目录和临时输出 JSON 路径。
- tools/drive.mts 从当前 apps/render 目录加载 renderVideo 与正式 spec schema。LAB 指向隔离夹具，TMPDIR 单设，RENDER_PORT=49873，NODE_OPTIONS 指向对应记录钩子。mac 和容器各自监听独立的回环地址，使用归档 MG 源、原 silence.wav、上轮 mix/shape/silence spec、25 fps spec 以及本轮 boundary.json。钩子复制输入、记录实际命令，在选定的失败用例内注入错误。候选源码没有故障开关。
- tools/collect.py 的参数分别为平台夹具目录、clock-boundaries/measure.py 及输出 JSON 路径；逐文件按 SHA 去重测量。tools/check_boundary.py 的参数为包含逐轨 WAV 和滤镜脚本的目录、24 fps spec、固定素材目录、同一个 measure.py。测量端使用 PyAV 与 NumPy。
- macOS 25 和 30 fps 新成品可直接按 SHA-256 与 ../clock-boundaries/audio/bounded.mp4 及 ../clock-boundaries/regression/success.mp4 对照；本次实测与上述归档字节相同。Linux 两个正常有声成品在本目录的 linux/。缓存演练的 OLD_MEDIA 指向 ../run/success/video.mp4；两套 /upload 进程只连接本地接收端。

## Linux 结果及执行成本

同镜像 linux/arm64 的联合源码逐字节与工作树一致，镜像 ID 与候选 diff SHA 记录在 environment.json。30 fps 并行预编码、MOV、AAC 基线、响度成品均为 1/90000，240 帧 PTS 与源身份全对；H.264 包摘要为 da0db9784d8382a5d34427da90add8424e7231675e6887133b14f12936fe135c。25 fps 有效 382080、30 fps 有效 384000，两者首包与 skip 符合 macOS 结果，声部与尾段零滞后。两个平台相同作品的 H.264 包相同，AAC 编码后的全文件摘要按平台单独保存。最终响度由同一二进制复测，25 fps 的 macOS/Linux 为 −16.25/−16.24 LUFS，30 fps 为 −16.28/−16.29 LUFS，真峰值见 loudness.json。

Linux 重编码故障真实退出 8，返回 c928fc61fb042e0df4535665029d6f14d9c0d91ca73851284b290e4c89f1f011，与该平台基线逐字节相同。静音与无音轨均正常跳过，前后文件相同。分析失败和替换前失败仅在 macOS 注入。Linux 的 24 fps 再次在响度前拒绝 382016 样本；和 macOS 相同，三个声部与末段误差为 +16、+16、0 及 +16，191 个视频帧正确。两平台各次完整返回和受控拒绝后均无 .encode-* 残留；首次 Linux 诊断钩子因把数字当字符串导致进程异常退出，遗留的空工作目录单列保全，仅修正实验钩子后重跑，未计入渲染结果。该中断不能作为进程强杀清理通过的证据。

本轮 macOS 共九次 renderVideo 调用（含 24 fps 取证复跑），Linux 共六次完成或受控拒绝的调用，另有上述诊断中断一次。macOS 正常有声 30/25 fps 墙钟为 11.214/9.122 秒，Linux 为 134.504/132.978 秒。均含留样与环境开销，未做独立性能基准。Linux 容器整个实验的 cgroup memory.peak 为 3128332288 字节（约 2.91 GiB，含容器缓存与探针）。macOS 八秒实验的 PCM MOV 为 5868476 字节。成功有声路径有一次 H.264 与两次 AAC 编码；两个增量对照都没有额外编码，既有 FFprobe 调用提供时窗参数。无新增依赖。报告覆盖的代码量为三文件相对开工 HEAD 增 66 行、删 22 行（包含开工前的 PCM/缓存候选）。未做长片、高并发或部署容量验收。

归档期间其他提交更新 MG 研究及产品文档，三份生产候选的完整 diff 摘要保持一致。完整变更见 candidate.diff；研究材料的 SHA256SUMS 可在此目录执行 shasum -a 256 -c SHA256SUMS。
