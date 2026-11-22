# Remotion 4.0.484 采样级延时回移与 MP4 播放窗口

**路线 B 的隔离研究有条件通过。** macOS 三件作品的 630 个画面均匹配原版的源帧、PTS 和 H.264 包载荷。24 fps 在混音时已经采样级对齐，第二次封装显式使用 48 kHz movie timescale 后，最终有效播放窗口也恢复完整。Linux 本次没有产出可测文件。建议进入下一轮最小生产候选评审，跨平台签署仍需健康 Linux 的实物证据。Chat-Origin 五面尚未验收。

## 基线与范围

开工本地 main 为 `0d16d514c80cefd4d5273bba1bcd3abb407a800a`，远端 main 为 `07945bd7cd92b4326b79661009ad6b7c99cc526b`。本轮期间其他提交推进了本地分支。受保护的 artifacts.ts、audio.ts、video/index.ts 三文件完整 diff 的 SHA-256 前后均为 `189565a5d29729a168fa8f6f3c63577afc6c0befab233fa4761e48d3898f4712`，与 joint-candidate/candidate.diff 字节相同。其他工作区变更包括 Web 工作、audio-study/REPLAY.md 与上轮 upstream-4.0.540 研究目录。此次本地提交范围仅为 backport-4.0.484。

在临时目录按相同源码、固定编译 spec 与固定源渲染。源码基线、归档候选、旧版和升级实验的媒体与 SHA 清单均已核对。本次将 24 fps 的呈现长度同媒体的 edit list 交叉验证。复用旧测量器重建独立参考、按解码帧 PTS 放置 PCM、做互相关，并解码画面内嵌编号。运行环境为 macOS 26.5.2 arm64、Node 22.15.0、pnpm 10.20.0、Chromium 149.0.7790.0、PyAV 17.1.0、NumPy 2.4.6。只使用本地素材、回环 HTTP 和隔离目录。未调用产品数据库、付费 Provider、Chat、外部 Output 或生产部署。

## 依赖边界与可复现性

4.0.484 的 adelay 表达式先将秒取整为毫秒。4.0.540 使用实际采样率取整，并附加 FFmpeg 的 S 单位。补丁在 `@remotion/renderer@4.0.484` 的 CJS 单文件和 ESM bundle 中各替换同一表达式，其他逻辑保持旧版。逐字节比对 653 个发布文件，只有这两处不同。Compositor 包和测试实际使用的 Chromium 整个分发目录也按文件 SHA 与原版比较。四份固定 tag 源文件及原生二进制摘要见 evidence/identities.json。旧版 frame cache 取最近帧，新版在目标时刻及之前选帧，回移范围仅为音频表达式。[旧版音频源码](https://github.com/remotion-dev/remotion/blob/v4.0.484/packages/renderer/src/stringify-ffmpeg-filter.ts) · [新版音频源码](https://github.com/remotion-dev/remotion/blob/v4.0.540/packages/renderer/src/stringify-ffmpeg-filter.ts) · [旧版取帧](https://github.com/remotion-dev/remotion/blob/v4.0.484/packages/compositor/rust/frame_cache.rs) · [新版取帧](https://github.com/remotion-dev/remotion/blob/v4.0.540/packages/compositor/rust/frame_cache.rs)

使用 pnpm patch 和 patch-commit 生成版本限定的补丁。补丁 1,449 字节，SHA-256 和锁内 patch_hash 均为 `2a914fa1fa9c60887f1bd370040872c062f92303a7b00555e8b5a9b689472713`。第二个空安装目录与空 pnpm store 使用 frozen lock 安装，增加 248 个包，日志记录 246 个下载、0 个复用。两套安装独立比对均通过，并用第二套实际渲染。未升级 Remotion 家族、Chromium 或 FFmpeg。Chromium 复用了原有已校验分发文件，未单独测试浏览器下载服务。

## 三件固定作品

|macOS 作品|PCM MOV / AAC 基线 / 响度成品的有效采样|成品解码返回的采样|按 PTS 的间隙|Voice / Whoosh / Impact / 尾段偏移|逐帧 PTS、源身份与原版视频包|
|---|---:|---:|---:|---|---|
|24 fps × 191|382000 / 382000 / 382000|382976|0|0 / 0 / 0 / 0|191 帧完全相符|
|25 fps × 199|382080 / 382080 / 382080|382976|0|0 / 0 / 0 / 0|199 帧完全相符|
|30 fps × 240|384000 / 384000 / 384000|384000|0|0 / 0 / 0 / 0|240 帧完全相符|

旧 24 fps 混音长 382016，声部实际入点为 14016、68016、96000。此次从实际滤镜脚本读到两个声道分别使用 14000S、68000S、96000S。在进入 PCM MOV 前，混音 WAV 已恰好 382000 采样，三个独立声部相对参考的相关峰均在零。三件作品成功成品的 Loudnorm 日志均报告 Dynamic、−16.0 LUFS、−3.2 dBTP。25 fps 尾段互相关为零，逐段 PTS 检查没有跳跃。各文件 SHA、包与逐帧数据保存在 evidence/mac.json 和 evidence/clocks.json。

Linux docker run 在容器创建前遇到现有镜像内容存储 blob 的 input/output error。只读 image inspect 在收尾时仍返回同一错误。未重置或清理共享 Docker。24、25、30 fps 及 Linux 专有并行预编码时钟本轮均为**未验证**。已有旧候选及 4.0.540 的记录只作历史对照。

## 第二次 MP4 封装的单变量对照

用本轮同一份 24 fps AAC 基线、同一个 FFmpeg、相同 Loudnorm 分析参数、相同编码选项重放，仅变更输出 movie timescale。下表 edit 长度使用 movie 时间单位，media start 使用音频轨的 48 kHz 单位。

|24 fps 文件|movie timescale|音频 edit 长度 / media start|首音包 PTS = DTS / skip_samples|有效采样|
|---|---:|---|---|---:|
|首次 PCM → AAC/MP4|48000|382000 / 2048|−2048 / 2048|382000|
|Loudnorm，FFmpeg 默认封装|1000|7958 / 1024|−1024 / 1024|381984|
|Loudnorm，显式 48 kHz|48000|382000 / 1024|−1024 / 1024|382000|

两个响度成品的音轨 mdhd duration 都是 383024，解码均返回 382976 采样。AAC 包载荷 SHA-256 同为 `4bc293370e48521d7e4800fd95761adc782074d52eb460696662d93a96fee233`，H.264 包载荷也相同。默认封装的音频 edit 仅有 7958 毫秒，少 16 个有效采样。显式 48 kHz 的成品正确排除 priming 和解码尾部补齐，末段相对参考的偏移为零。两个真实成品与编码前混音已归档在 media/。两次封装的精确参数和退出记录见 evidence/mac-commands.jsonl、evidence/mux-1000-command.json。

## 四出口与成本

- **响度前基线**保留 2048 个 skip_samples，入点、音频窗和视频均通过。
- **响度成功**保留新编码器的 1024 个 skip_samples，两次封装均复制视频流。正常有声作品实测各一次 H.264、两次 AAC 编码。相对联合候选，各增加零次。
- **响度失败回退**在 30 fps 的第二次编码注入无效选项，实际退出 8，正式 catch 返回可完整解码的基线。返回文件与同次基线及正常渲染的基线 SHA-256 均为 `76a6df677bbd` 开头，完整值见 clocks.json。四次 renderVideo 均无遗留 .encode-*。本轮未重复分析失败、替换前失败或强杀。
- **正常跳过**从同一 30 fps 基线派生无音轨与全零音轨两份输入，直接运行正式 normalizeLoudness。前后文件 SHA-256 分别完全相同，均保留全部 240 帧及视频包。静音轨 384000 有效采样、峰值为零，无音轨文件没有音频流。两次均未产生响度临时输出。此项覆盖后处理边界，本轮没有从另一个 Composition 重跑跳过旅程。
- 四次 renderVideo 用时 19.090、9.358、10.130、9.930 秒，依次为 24、25、30 fps 成功及 30 fps 编码失败回退。另有两次直接跳过和一次默认时基负对照重放。此计时包含留样和本机负载，不能据此给出性能差值。隔离 Renderer 的 tsc --noEmit 通过。未引入新混音器、运行时依赖、视频编码、时间映射或帧率特判。未进行部署容量或生产五面测试。

## 复现与下轮维护范围

从仓库内以 bash 执行 tools/replay-mac.sh。需要 pnpm 10.20.0、未经改写的原版 4.0.484 Renderer 及已缓存 Chromium，可通过 MEASURE_PYTHON 指定有 PyAV 和 NumPy 的 Python。脚本在新临时目录恢复固定 commit、原候选 diff、包补丁与隔离 mux 调整。端口 49873 用于固定夹具。tools/check_clocks.py 会对参考、帧、包、窗口、负对照和退出文件作断言。归档脚本由本次分步执行的命令组成，另做过 shell 语法、补丁应用和锁字节校验。现有归档可在本目录用 `shasum -a 256 -c SHA256SUMS` 校验，不需要渲染。

下一轮生产候选的增量范围是一份针对精确版本的 pnpm 补丁、工作区声明与锁记录，以及已有 Loudnorm 输出命令的一对封装参数。Renderer 与 Web 的 Dockerfile 目前在安装前仅显式复制锁和 manifest，构建层需能读取补丁并实际做 frozen 安装。构建身份应包含 patch_hash，避免与旧缓存混用。以后升级 Remotion 时复核 CJS/ESM 产物、采样单位和三件夹具，再决定移除或更新补丁。verify_install.py 在版本不匹配、目标文件变化或出现额外改动时失败。

当前 macOS 结果没有发现否决路线 B 的新错误。唯一待补的本轮技术证据为健康 Linux 上使用同一锁、同一补丁的实物复核，尤其是 25 fps 尾段及 30 fps 并行预编码 PTS。建议有条件进入最小生产候选施工，由架构评审另行授权。正式合并、部署与 Chat-Origin 五面保持待验。
