# Remotion 4.0.540 与现有 I8 候选

**裁决：未通过。** 官方修复在两平台消除了 24 fps 两个声部晚 16 样本的问题。整体升级另改变了固定素材的选帧语义，24 fps 响度成品的有效播放窗也仍短 16 个样本。保留现有时间语义的前提下，推荐用户下一步仅授权评估路线 B。本轮没有实施 B，两条路线都未获生产验收。

## 基线与方法

开工本地 HEAD 0f914f0d39744e0dc6b8ce5e061b3576fe2727d9，远端 bac35a83f0231a76cc9a7adae90858737a191b00。现有三个生产文件的 diff SHA-256 始终为 189565a5d29729a168fa8f6f3c63577afc6c0befab233fa4761e48d3898f4712，与上一轮 candidate.diff 相同。其他 Agent 的工作未纳入实验。旧版对照复用经摘要核验的 joint-candidate 媒体和逐帧数据，本轮另对真实旧 WAV 重做互相关，并用旧版原生 compositor 提取同一时间点的图像。未重复整个旧矩阵。

在独立 workspace 的三个 manifest 中，将全部直接 remotion、@remotion/bundler、@remotion/renderer、@remotion/player 一起固定到 4.0.540，生成全工作区锁。旧锁 21 项、新锁 27 项 Remotion 家族包分别全部同版（含平台可选包）。两平台按新锁安装 Renderer 闭包。应用代码、三个候选文件、共享 Video.tsx、已编译 spec 和固定源沿用原字节。实际入口为 renderVideo；子进程探针只记录、留样或注入选定响度故障。复用 joint-candidate/tools 的驱动与采集器、clock-boundaries/measure.py 的按 PTS 放置 PCM 和画面内帧号读数。未另做完整 Web 安装、交互验收、Chat 旅程或生产发布。

## 固定作品实测

|作品与平台|音频和有效窗|画面|
|---|---|---|
|24 fps / 191 帧，macOS/Linux|新混音 WAV、PCM MOV、基线 MP4 均为 382000。Voice、Whoosh、Impact 入点分别为 14000、68000、96000；三声部及末段滞后皆为零。响度成品均为 381984，内部无 PTS 间隙。|191 个帧 PTS 精确，191 个源帧编号都不同于锁定旧版判据。|
|25 fps / 199 帧，macOS|382080，有效窗正确，三声部和末段零滞后，动态响度后无间隙。|199 个 PTS 精确，98 个源帧编号不同。|
|25 fps，Linux|补测未取得可复核文件，标记未验证。|未验证。|
|30 fps / 240 帧，macOS/Linux|两平台均为 384000，入点与末段零滞后、无间隙。|两平台均 240 个 PTS 精确，119 个源帧编号不同。|

两平台的 24 fps 原始 WAV 字节相同。旧版两个错误入点为 14016 与 68016；新版保存的真实混音命令分别传 14000S、68000S、96000S。互相关在 Loudnorm 之前就已对齐。macOS 实际运行响度前基线、响度成功、重编码失败回退、静音及无音轨正常跳过。重编码故障退出码 8，最终 MP4 与该次基线字节完全相同；静音保留 384000 个零样本，纯 Shape 无音轨，两次跳过前后字节相同。本轮未重复注入分析失败、替换前失败或 Linux 失败/跳过。所有可读完成件每条路径内的视频包摘要相同，跨版本的视频包不可视为内容等价。详见 metrics/mac.json、linux.json、summary.json 和原始子命令。

## 首个新版行为差异

把同一输入文件和源时间 0.500000 秒交给两个实际 macOS 原生 compositor 的 ExtractFrame；旧返回画面编号 12，新返回 11。源帧 11 和 12 的 PTS 分别为 11011/24000、12012/24000 秒，后者为 0.5005 秒。旧版返回最近的 PTS，新版返回目标时刻及之前的最后一帧。源文件固定为约 23.976 fps。新版 24 和 30 fps 的所有实测帧都符合后一规则。新版标签中的 frame_cache.rs 明确规定了这一选择。首差位于 OffthreadVideo 原生源帧提取，早于编码、封装和响度处理。extract.cjs 是仅供实验使用的单帧探针；结果与两张帧号裁图见 metrics/extract-result.json 与 media/。[新版取帧源码](https://github.com/remotion-dev/remotion/blob/v4.0.540/packages/compositor/rust/frame_cache.rs)

24 fps 音轨另有独立问题。基线 MP4 的 movie timescale 为 48000，音频 edit list 长 382000；响度成品的 movie timescale 为 1000，音频 edit 长 7958 毫秒，只呈现 381984 个样本。成品 AAC 音频 mdhd duration 为 383024，扣除 1024 个 priming 后恰为 382000。两版锁定 FFmpeg 均标识 n7.1。在同一正确基线上，用旧版二进制重放响度命令也得到相同短窗；诊断重放仅把输出 movie timescale 设为 48000 后，edit 长度恢复 382000。这定位到现有响度 MP4 封装，既未实施旧包补丁，也未以裁切补偿入点。详见 metrics/boxes.json、control-boxes.json、mux-controls.json。

## 依赖、接口与资源

- 官方版本发布于 2026-11-02，包含 #12673 以采样设置延迟。本轮对照两个标签源码及 FFmpeg 的 S 单位说明，原始滤镜和两端 PCM 也证明实际生效。[发布记录](https://github.com/remotion-dev/remotion/releases/tag/v4.0.540) · [官方修复](https://github.com/remotion-dev/remotion/pull/12673) · [FFmpeg adelay](https://ffmpeg.org/ffmpeg-filters.html#adelay)
- Chrome Headless Shell 149.0.7790.0 → 158.0.8127.2，本轮新缓存的 macOS/Linux 下载进度总量约 140.3/96 MB，解包磁盘读数约 459/224 MiB。macOS 主机旧缓存约 193 MiB。macOS 26.5.2 / Node 22.15.0 和 Debian bookworm ARM64 / glibc 2.36 / Node 22.23.1 实测。该标签文档列 macOS 15+、常规 Linux glibc 2.35+；锁入的 Rspack 2.3.0 要求 Node ^20.19.0 或 >=22.12.0。[标签版系统要求](https://github.com/remotion-dev/remotion/blob/v4.0.540/packages/docs/docs/getting-started.mdx)
- Rspack 1.7.11 → 2.3.0；主驱动仍用 bundle() 默认 webpack，未启用 Rspack 选项。Mediabunny 1.47.0 → 1.64.0。新锁也更新了无关 Web 范围依赖；isolated-lock.diff 是实验记录，不宜原样提交。三处生产 manifest、一个 pnpm 锁及平台二进制是升级需要核对的包范围。
- 类型检查通过。新版预编码命令使用 remotionshm 共享内存，把既有限定的 ffmpegOverride 应用到 pre-stitcher，显式写 -f mp4。保留 .mkv 临时名，实际字节为 MP4，后续成功读取。PCM MOV → libfdk_aac 基线首包 PTS/DTS −2048 / skip 2048，响度成品为 −1024 / skip 1024。单个作品从预编码到最终 MP4 的 H.264 载荷保持。没有签署性能、长片或并发容量对比。
- 两种包锁均牵涉正式 Renderer、组件烘焙和 Web Player。Component Runtime 与 API 各有写死 4.0.484 的依赖身份，此身份被校验并参与内容摘要。即使下轮选择 B，也须保证补丁构建可识别、历史已烘焙作品和已准备的输出可追溯。未来若考虑 A，须分别验收双方的标识与旧项目重放、Chat 视频预览与皮肤 Player、正式输出选帧与缓存切换。
- 一次 macOS 30 fps 共享内存 ACK 管道中断，当时磁盘余量很低；只迁移本轮浏览器下载到临时 RAM 卷释放空间后，同一份代码和夹具重试成功。Linux 24/30 fps 完成且已复制，补测 25 fps 时 Docker 数据层返回 I/O 错误及只读文件系统，取证失败。隔离容器已停止，Docker 元数据写入失败导致当时无法删除；未重启共享 Docker 或接触其他容器。磁盘事件不计作上游回归。

## 路线裁决

A 官方版已解决本项目的采样入点反例，具有上游维护优势，但变更源帧选择，无法通过现行历史作品语义的验收。B 在 4.0.484 的锁定构建中回移采样延时表达式，预期可隔离该行为，保留原浏览器与 compositor；维护责任包括补丁来源、完整性、实际装载的发布入口及平台回归。B 未实施、未验证，且其本身不能修复独立的响度封装有效窗。**只推荐授权下一轮隔离验证 B。** 合并前仍须独立验收 24 fps 最终有效窗、源帧身份、缓存与正式消费者。本轮停在研究归档。
