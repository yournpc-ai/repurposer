# 同一浏览器场景里的视频、动效与两次定向修改

2026-11-23 · Repurposer MG 隔离研究 · macOS arm64

**架构裁决为有条件通过。** 在 1080p、30 fps 的同一个八秒工程里，Chromium 可以接收两路实际 H.264 解码像素，在单棵 React 树中完成视频、两个动态组件、柔边遮罩、交叉遮挡、差值混合与背景模糊。输出侧只需捕获最终画布并编码。跨层视觉逻辑可以从原实验的 FFmpeg 滤镜图中移出。确定时钟、媒体适配、缓存、执行隔离仍有实际成本。实验支持把 C 留作候选；生产替换和总维护成本净下降仍待证明。

## 1. 产品基线和研究边界

最初本地 main 与跟踪引用为 a0d354d100f57ae3b2853e1fca2efadb92098448，已越过任务给出的 2f02da61。远程 git 查询超时，改由 GitHub 提交接口核实当时远端 main 已前进至 bdedeff56fdfe2d4bf78d22968d8ac6c5cce7609，本地亦到达该提交。随后 Audio 的归档进入 db8ffbed45acf41773562c5d6c451d598e8d701e。I8 工作树中有三个 renderer 文件在改，本实验在临时目录绕开这三处，只读使用作品合同、编译器、固定素材、既有环境与测量工具。

读取范围包括 CLAUDE、PROGRESS §0、new-agent 的唯一写口与执行分界、I8 的缺口及现行处置、VIDEO_PROJECT 的版本、轨道、对象、生成器和时间合同、RENDERING 与 VERIFICATION。源码核对了 editing 的 schemas、store、video_spec，video-spec 的量化和轨道，video-remotion 的 Sequence/OffthreadVideo，render/video 的导出入口和 component-runtime 的策略、隔离及烘焙职责。仓库以 Project 承载会话、Composition 标识作品、CompositionVersion 固定内容和来源。普通编辑走 apply_composition_edits，预览走有界计算，正式导出固定版本及授权，交给 ExportJob 和 Worker。正式 video-spec 消费固定 Generator 媒体。

旧基线有 A/B/C 三路运行记录。V4 的实际 C 代码让浏览器画遮罩和字幕，FFmpeg 中按 PiP 活动期切段、crop/alphaextract/alphamerge 后 overlay。核对了 V4 版本 JSON、编译数据、二进制清单、源 PTS、Player 定位、音频中间段和媒体。V4 支持单目标透明度，却不能仅用那两张平面定义依赖下层颜色的混合。本轮只更换隔离实验路径。

## 2. 外部源码带来的分工依据

| 来源 | 核对到的具体行为 | 对 Repurposer 的意义 |
|---|---|---|
| 21st Video Blocks | Two-Ink Riso Title 的 registry 示例注册 Remotion Composition，传 schema/defaultProps、30 fps、150 帧和 1920×1080。目录给出 text、kicker、调色和字体等字段。相同摘要的实际发布模块导出 Component、defaults、schema、meta，引用 useCurrentFrame、useVideoConfig、interpolate 和 spring，内部也有普通 React 元素、CSS 字体和颜色、确定性噪声。Metal Card 的源码返回中有 Zod、zColor 和 defineVideoMeta。Riso 的 get_component 返回的 componentCode 只是噪声 helper；单看该字段会漏掉宿主依赖。 | 可借鉴可编辑参数和帧函数。使用现有组件须逐件核对时钟、上下文、素材加载、依赖和许可。对固定 Riso 发布包的 SHA-256 重新下载校验为 14f461853860f87e2577978a34fc4c87469c376b3d62b0f703abdb8cb8ea3d87。 |
| OpenMotion | 固定版本 a44c714d 的 reference-reveal 工程是带内联 CSS/JS 的 HTML。根带 composition ID、时长、画幅、fps，img 和 audio 指向项目内 SVG、WAV，audio 另有 id、起点、时长、轨号和音量。GSAP 创建 paused timeline，针对选择器和 DOM 节点放置 tween，用 main 键注册。Studio 播放适配器调用 tl.seek(t)，文件写入处理版本/ETag 和冲突；seek 后重新应用 DOM 上标记的位置、尺寸和旋转。React/TSX 用于 Studio，例如媒体预览控件。 | 可借鉴可寻址的元素、资源和绝对时间求值。文档选择器、DOM 编辑标记与文件版本各有作用，都需要与我方 object_id 和版本摘要明确映射。单例研究不能推出其全库均为这一种工程形态。 |
| HyperFrames | 固定版本 196eff39 的 videoFrameExtractor 调 FFmpeg 预提帧并处理提取窗口/缓存，videoFrameInjector 在捕获前按媒体身份注帧并同步可见性。frameCapture 驱动页面 seek、等待并用 BeginFrame 或截图回退。audioMixer 另行处理裁剪、音量、淡变、延迟、混音和失败。 | 浏览器会画 CSS。精确取得哪一帧、何时抓图、声音在哪里起止、怎样处理超时和缓存，都要有人实现。我方已有作品、资产快照、授权、作业、恢复与交付。无需为试验引入其 Studio 或整套执行架构。 |

外部程序与图像只读。示例完全复用本仓原创信号素材和新写的组件。外部源码证据可从原始发布方访问。[21st 发布模块](https://cdn.21st.dev/video-bundles/14f461853860f87e2577978a34fc4c87469c376b3d62b0f703abdb8cb8ea3d87/index.mjs) · [OpenMotion 工程](https://github.com/nexu-io/openmotion/blob/a44c714d0e702f3b9b02be8a7512bbf278c6294b/examples/reference-reveal/index.html) · [Studio 播放适配](https://github.com/nexu-io/openmotion/blob/a44c714d0e702f3b9b02be8a7512bbf278c6294b/studio/src/player/lib/playbackAdapter.ts) · [文件写入](https://github.com/nexu-io/openmotion/blob/a44c714d0e702f3b9b02be8a7512bbf278c6294b/studio/src/hooks/useProjectFileWriter.ts) · [HyperFrames 引擎](https://github.com/heygen-com/hyperframes/tree/196eff39eb05752b45d9e2f84fb20c1d530dc166/packages/engine/src/services)

## 3. 作品与比较方法

同一 Composition cef118bc-be7c-5578-83ab-1bd49300b60e 从 V4 派生 V5，再依次得到 V6、V7。每版均经实际 CompositionContent、validate_content、来源摘要及 content_digest_of 校验。版本在实验目录按内容摘要生成稳定 UUID，无 DB 持久写入。五个素材快照、三段音轨、源窗和 90 kHz 时间基延续 V4。普通素材由正式 compile_video_spec 编译，两个 Generator 的 clip-local frame 使用同一量化函数。实验宿主只给投影增加组件入口、参数和目标标识。此投影可丢弃重算，无独立写口；它尚不属于正式 video-spec。

| 活动对象 | 时间与画面 |
|---|---|
| main-film | 0–239 帧。960×540 的 24000/1001 fps H.264 主视频从 0.5 秒取用，全画幅展示。 |
| signal-sweep | 30–179 帧。后层彩带随局部帧移动并旋转，用 difference 读取主视频颜色。 |
| sensor-film | 15–209 帧。480×270、25 fps 的 H.264 从 0.4 秒取用，位置 (1330,88)。父容器对真实帧应用随时间变化的 polygon clip-path 与渐变 mask-image。 |
| signal-title | 30–179 帧。前层文字 Signals in sync 带移动、半透明和 blur(9px) saturate(2) 的 backdrop-filter。在 V5、V6 遮住一部分 PiP。 |
| 声音 | 48 kHz 双声道，既有旁白、Whoosh 和 Impact 按同版起点、裁段和增益混为 PCM，编码一次 AAC，两路在最终 MP4 中复用该流。 |

B 在 Remotion 中以 useCurrentFrame 驱动共享 Scene，用无布局 Sequence 和 OffthreadVideo 解码。C 用 PyAV 读取实际呈现时间戳，按最邻近 PTS 选源帧，等距取后，向相同 DOM 布局提供逐源 PNG。React 同步提交后等 image.decode() 和字体就绪，CDP 取整幅 PNG 直接送 FFmpeg 编码。缓存只含原始源帧，没有预合成的遮挡或特效。两路同分辨率、同视觉源码、同布局、同音频，均用 H.264 / CRF 18 / veryfast / BT.709；编码器发行版、取帧与进程调度不同。C 没有使用 WebCodecs。

本轮宿主导入固定的两个具名组件，按作品对象绑定位置、层序和 PiP 遮罩，场景源码本身含 Sweep 图层的混合样式。正式 Agent 任意写一份 TSX 后按 digest 安全加载、兼容既有 Remotion 项目和所有 video-spec 对象，均超出这个实验已经证明的范围。

## 4. 图像与帧时间的实测

第 72 帧上，C 只关闭 difference 后有 21,336 个像素变化，变化像素 RGB MAE 22.4161/255。独立只关闭 backdrop-filter 后有 19,886 个像素变化，变化像素 MAE 9.4253/255。原画面能看见传感器曲线在玻璃文字下模糊，关闭后线条清晰；PiP 被提到前面时，文字被真实视频遮挡。用同点失活对照可排除单纯声明样式而没有视觉效果。MAE 指 RGB 通道绝对差的算术平均，0 表示完全相同。

每份成片 240 帧均验证 PTS 为 k/30。每帧在实际输出像素中解码源素材自带的十位帧号，并对照原视频逐帧 PTS。三版逐版结果相同。C 主视频 240/240，PiP 195/195；B 主视频 240/240，PiP 192/195 与实验的等距取后规则相符。仅 PiP 输出帧 72、126、156 在两候选等距时出现差别。第 72 帧目标为 2.3 秒，B 取 2.28 秒的 57，C 取 2.32 秒的 58，各自距离目标 20 ms。

V5 定位以 72、239、30、179、0、45、180、15、209 的乱序发出。B 在 renderStill 独立抓图，C 另启浏览器调用同一取帧路径。下表把定位图与本路有损输出比较，另列两路成片的整帧误差。ROI 为包含标题与 PiP 的 580×310 矩形。两侧随机定位的可见源编号均与自身导出一致，C 的 9 张定位 PNG 摘要与顺序出片时的编码前 PNG 完全一致。

| 帧 | B/C 整帧 MAE | B/C ROI MAE | B 定位到自身成片 | C 定位到自身成片 |
|---:|---:|---:|---:|---:|
| 0 | 2.1934 | 2.2154 | 1.0045 | 1.0503 |
| 15 | 2.2496 | 1.8705 | 1.0815 | 1.1289 |
| 30 | 2.2806 | 1.9360 | 1.1482 | 1.2002 |
| 45 | 2.2713 | 1.9108 | 1.1311 | 1.1796 |
| 72 | 2.3285 | 2.5164 | 1.1152 | 1.1619 |
| 179 | 2.2910 | 1.9654 | 1.1651 | 1.2121 |
| 180 | 2.2821 | 1.9013 | 1.1369 | 1.1827 |
| 209 | 2.2852 | 1.9426 | 1.1536 | 1.1956 |
| 239 | 2.4069 | 2.2443 | 1.1427 | 1.1875 |

首帧和尾帧没有活动的动效也有色差，现有实验不能把整帧误差完全归因到遮罩、字体或某个解码器。定位通过的是离线精确抓帧路径；全片交互、实时播放时钟、音频设备延迟和 HDR 色彩均未验证。

## 5. 两次续改与音频

V5→V6 唯一内容差异为 signal-title 的 ink 从 #8acdf5 改成 #ffc152。第 72 帧未经编码的 C 画面变化界限为 (1264,216)–(1573,283)。V6→V7 唯一内容差异为 track-pip 的 order 从 2 改为 4，PiP 移到文字上方。第 72 帧变化界限为 (1306,88)–(1809,357)，包括近旁读取背景的玻璃区域。源视频、两个组件的源码、其余对象和时间保持同一内容。除版本元数据外，结构 diff 各仅一个叶子。两次修订在所查的 0、15、180、209、239 帧均为零像素变化；四个双组件活动检查点均发现局部差异。每版 B/C 都实际导出。

六个成片的解码 PCM 摘要一致，呈现 384,000 个采样/声道，相对由原始 WAV 得到的参考混音，整轨互相关滞后为 0。固定音轨是刻意设置的控制变量。它证明本轮画面修改及最终复用音轨没有移时。本轮没有走 I8 的响度后处理、回退或不同帧率封装。历史 ADTS 路径有 +2,048 样本，I8 更新的候选在另一合法作品上记录了 +1,024 样本内部间隙；两者不可挪到本轮 B/C 比分。[I8 候选反例](https://github.com/yournpc-ai/repurposer/blob/bdedeff56fdfe2d4bf78d22968d8ac6c5cce7609/docs/experiments/renderer-aac/CANDIDATE-REVIEW.md)

## 6. 第一处语义失败

固定输出帧号后，在同一张 C 页面给图像启动五秒 Web Animation，保持作品帧号，再次读取 computed opacity，实测从 0.996661 到 0.966662，动画时钟已到 166.69 ms。浏览器自己的 document timeline 继续走。普通嵌入组件只要依赖自主播放的动画，同一帧就可能随抓图等待时间改变。这个反例与透明度、混合或模糊能否正确着色是不同的问题。只验证了以显式 frame 求值的动画。CSS keyframes、transition、requestAnimationFrame 以及第三方有状态逻辑需要各自的时钟合同。首次运行另有一次输入校验失败，现有受控项目合同要求至少两个源文件，拆分真实遮罩函数为第二个固定模块后通过。原始失败已归档。[Web Animations 时间模型](https://www.w3.org/TR/web-animations-1/) · [React DOM 同步提交](https://react.dev/reference/react-dom/flushSync) · [CSS 混合规范](https://www.w3.org/TR/compositing-1/) · [CDP 页面截图](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot)

## 7. 性能、依赖与代码责任

首轮同机顺序运行，每个命令各起进程，进程树 RSS 约每 0.2 秒采样。冷指没有该路线的场景 bundle/源帧缓存；系统、Node 依赖、共享 PCM/AAC 已就绪。热指复用前次构建/源帧。共享混音和安装不计入各路耗时。每个表格单元只有一次测量。

| 工作 | B 秒 / MiB | C 秒 / MiB |
|---|---:|---:|
| V5 冷整片 | 20.28 / 1935 | 16.36 / 1560 |
| V5 热整片 | 17.07 / 1889 | 14.20 / 1532 |
| V5 乱序 9 帧，含进程启动与取证 | 5.60 / 777 | 1.53 / 666 |
| V6 改颜色后整片 | 17.68 / 1644 | 15.62 / 1225 |
| V7 改层级后整片 | 20.65 / 1413 | 20.91 / 1099 |

C 在该样本保存两段源视频的全部 397 张 PNG 和 PTS 索引，合计 68,018,811 字节，JS 610,583 字节。B 的持久 bundle 为 20,288,485 字节。共用参考 WAV 1,536,044 字节，AAC 123,922 字节，另有约 2.9 MB 的静音视频待封装。此处统计必要的可见缓存字节；不含浏览器 profile、操作系统缓冲及 Remotion 内部瞬时目录峰值。源帧缓存按源长度增长，两路时间亦受同机负载影响。不能用这一对数推断长片或并发收益。

旧 C 有 73 行 FFmpeg/浏览器驱动和 10 行平面 JSX，另有 13 行帧服务。新 C 的 c.py 92 行，浏览器入口 12 行，含测量和反例代码；共同场景 19 行，两个块及遮罩 22 行；B 专用入口与渲染驱动合计 28 行。另有版本派生、打包、混音、测量与校验脚本，均在归档中。行数含注释、空行。两种 C 的测量范围和功能不同，行数不能外推生产规模。新 C 去掉了遮罩/字幕平面、按遮罩窗口切片、alpha 合并、专用 overlay；保留 React、Chromium、FFmpeg，继续用实验已有 PyAV、Playwright/CDP、esbuild。Pillow 写源帧。C 本身没有调用 Remotion，也没有安装 HyperFrames、GSAP 或 WebCodecs 库。新版仍负担 PTS 到像素的规则、缓存大小和键、解码/字体屏障、进程与截图、像素传输、颜色和编码。两路都享有相同原生视觉要求；实验只覆盖受信工程、SDR、两个固定入口等明确子集。生产维护净收益尚无证据。

## 8. I8 接入与退役条件

| 现有机制 | 待验合同 |
|---|---|
| Tool | 在现有工具中定位同一 object_id 和 base_version，经唯一写口保存一个子版本。参数变更可审计，过期版本拒绝。 |
| Context | 传递工程、可编辑参数、确切来源/版本摘要、目标对象与局部观察。把内部 DOM 名称映射到稳定对象。 |
| Chat | 原 opening 和 Tool 回执显示对应版本的修改、预览窗口、交付及刷新回放；一次修改可持续追问。 |
| Execution | 预览和导出使用相同绝对帧、源窗、色彩和资源固定规则。Worker 仅执行既有 ExportJob，处理取消、资源预算、上传及校验。TSX 执行需复用受控源码/依赖审查、已声明资源、宿主级隔离和进程限额。实验页面与打包器只运行本仓受信源码，Chrome 沙箱本身不足以执行外部未审代码。 |
| Recovery | 租约、幂等键、重试、缓存身份、输出校验、费用及交付事务仍归已有系统。编码后强杀、上传前后恢复、旧版本重放和取消清理都有待生产路径证明。 |

最先具备退役可能的是**已验收的帧驱动视觉组件**在最终合成前单独烘焙 MP4/PNG 的消费需求。替换须能从固定 CompositionVersion 安全加载程序、资源、字体并准确预览，证明音频/源帧、重试、历史版本和审片交付一致，且有可接受的资源上限。依赖 Remotion Hooks/Sequence 的既有工程、Player、共享 Video、历史固定产物回放、其他 Generator 和最终 Renderer 各有真实消费者，逐个证明等价后才有退役依据。生产本轮物理删除 0 行。

**唯一建议的下一步**是在同一隔离夹具中，将一个现有块的位移改成暂停且显式 seek 的 Web Animation，让双向乱序定位与顺序出片的原始像素摘要相等。只验证这个已经观测到的时钟失败，继续沿用相同作品、素材和比较基线。

## 9. 复现与交付

从包含本提交的仓库根目录执行以下一条命令，脚本在新的临时目录准备版本、运行两路三个版本和乱序取帧、重算证据。环境沿用已准备的仓库 Python venv、锁定的 Chromium、系统 Arial Bold 和 baseline 的 Node 锁。首次实验复用已有同锁 Node 模块；干净回放另行执行 npm ci。实验不访问数据库，无私有素材。固定语音为基线中已冻结的系统 Samantha 合成 WAV，曲线与音效为基线原创。系统字体只校验摘要，不随包再分发。外部样例的可读取性不授予组件或资产再分发许可。21st 样例保有 Remotion 许可提示。

```sh
bash docs/experiments/mg-render/native-css/run.sh
```

归档包含三个版本、实验源码、两路 V5 代表性 MP4、第 72 帧六格比较、按帧源编号、像素/音频指标、计时、环境清单、负对照、首次失败和 SHA256SUMS。修订版整片与源帧缓存由脚本重建。B V5 的 MP4 SHA-256 为 ece2cc74eb0b4d1e2d41a5fd8815d4705cebbb2fd8922c53a4aae90e4e5424bb，C 为 2c2c1ca9ab3eb116fd8034358442ff7e3bdc65a3b0e98c1e17a53b0da20edf08。首轮各自冷、热输出的完整文件摘要相同。两个摘要分别标识两条路线，不要求互相相等。

独立复跑从空目录离线 npm ci 安装 182 个包，完整执行复现入口。V5–V7 六个 MP4、三个版本、720 行源编号、第 72 帧对照和全部画质、修订、音频指标复得相同摘要或相同值。两路 bundle 字节数随安装目录变化，耗时也发生反转。复跑冷 B/C 为 33.38/44.40 秒，热 B/C 为 25.37/19.51 秒；同机还有其他工作，本轮不能据此排出普适性能顺序。macOS 分析进程同时加载 PyAV 与 OpenCV 时报告重复的 AVFoundation 类名，本次两个分析进程均完成校验。
