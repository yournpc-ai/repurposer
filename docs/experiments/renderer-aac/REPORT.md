# I8 · 正式 AAC 音画同步取证

**调查有条件通过，正式 AAC 正确性未通过。生产裁决为建议最小修复，待批准。** 在本机锁定的正式代码中，混音准确，AAC 中间文件首度多出 2,048 个呈现采样。响度成功和异常回退均可交付带偏移的 MP4。无音频流的正常返回已在正式函数边界测到，尚未在本配置下从合法作品端到端触发。真实 ExportJob、部署容器和播放器设备未执行。

## A. 基线和执行环境

- 本地与远端 main 开工与收尾一致，均为 2f02da61ed5c2f4e3f5377e291719d15b887bb85。主工作树始终显示 main...origin/main，无已登记改动。按委派，主仓施工归 I8；Git 没有文件级租约，无法从干净状态断言其他 Agent 离线。另有 iteration4、iteration5 工作树，未进入。
- macOS 26.5.2 arm64，Darwin 25.5.0，Node 22.15.0，pnpm 10.20.0，Python 3.11.14，NumPy 2.4.6，PyAV 17.1.0，Pillow 12.3.0。pnpm-lock.yaml SHA-256 为 f22f8e7e06c6fcde826ee7bab0339b9f244f849cc37aa47eae62e010074e274d。Remotion、renderer、bundler 与 Darwin compositor 均为 4.0.484，React / React DOM 19.2.7，Chrome headless shell VERSION 为 149.0.7790.0，实际 FFmpeg/ffprobe 为 compositor n7.1。
- 从 HEAD 导出正式 TS 源文件，复制已有锁定依赖和浏览器到临时目录，保留正常 bundle、selectComposition、renderMedia 参数和 normalizeLoudness。当前 Python 编译器直接读取主仓源码，以内存快照事实编译合成版本。临时 Express 仅供固定源和 staging 缓存，驱动用正式 schema 校验后调用 renderVideo。诊断只在本进程观察子进程、复制边界文件和注入指定故障，未加生产开关。早期驱动额外提供了 NODE_PATH，后以原 pnpm tsx 启动器默认环境重跑，两份最终文件逐字节一致。机器 PATH 没有 ffmpeg/ffprobe，实际 pnpm 启动器能解析 compositor；普通 node 的 require.resolve 失败没有构成产品缺陷。
- 范围包括 CLAUDE、PROGRESS §0、new-agent、VIDEO_PROJECT §0、RENDERING、MUSIC_ARCHITECTURE、VERIFICATION，MG 指定报告、源、命令与媒体；读取 editing/{schemas,video_spec}、tools/video/export、chat/editor_media、pipeline/{export_jobs,rendering}、产物 probe、render 的 server、stage、video、audio、Remotion root、共享 Video 与 video-spec、锁内 compress-audio 和 stitch-frames-to-video。运行范围止于本地文件。没有写主仓文件、数据库、历史 Output 或其他工作树，没有运行收费服务、访问私人项目、提交、推送或部署。新增报告和媒体均在本临时目录。
- 复核入口为 fixture.py、shape.py、launch.sh、repo/apps/render/drive.ts、observe.cjs、measure.py、clock.py。完整 FFmpeg/ffprobe argv、实际路径及退出码见 commands.jsonl，故障栈和各次返回见 run.log，各唯一产物的探测和逐帧表在 run/ 对应目录，汇总见 metrics.json。目录位于 /tmp，不具有长期留存保证。

## B. 正式音频调用图

固定 CompositionVersion → export 的媒体准备检查 → compile_video_spec → enqueue_export 保存 render_spec → Worker 认领 execute_export → 绝对化 URL → /prepare-export → videoSpecSchema → 缓存未命中时 renderVideo → stageRemoteSource 核摘要 → bundle + selectComposition("Video", {spec: stagedSpec}) → renderMedia(h264，MP4，180000 ms) → normalizeLoudness → 返回 videoPath → /upload 取已有文件条件上传 → Worker 回读、probe、SHA-256、执行身份围栏 → Output。编译、schema、正式 renderVideo 及其下游在本轮实际运行；队列、HTTP 交付、存储、结算与 Output 提交由源码确认。

编译器将作品 ticks、来源窗和转场量化到输出帧。共享 Video 以 Sequence 的 from、duration 定位片段。OffthreadVideo 按源窗、mute、基础增益、动画与转场音量输出原声。Voice、BGM、SFX 使用各自 Audio Clip 的源窗、分贝增益和局部 gain 动画，重叠轨在 Remotion 混音。本夹具实测三个 Audio Clip，主视频静音，BGM、视频原声与变速等不在实测推广范围内。终检关心 H.264、尺寸、帧率、帧数与所需音频流存在性，未比较 PCM 时间轴、首包跳样、包间隙或声音入点。

/preview 共用 renderVideo，/render 与 /prepare-export 共用生成座位。上传恢复只用缓存，复用已有 Output 时走核验，均不重跑响度。component-runtime 的 renderMedia 是上游固定媒体烘焙。所读最终视频出口只在 renderVideo 内调用一次响度。

## C. 四出口验收矩阵

下表音频时间均按 48 kHz。恢复/跳过的“相同”表示运行内前后整文件哈希相同。所有列入表的唯一文件均完整解码，按文件摘要复用相同字节的测量。

|出口与实测输入|首音包 PTS/DTS；skip|解码 PCM / 轨道时间跨度|三个声部相对参考|结果|
|---|---|---:|---|---|
|A 正式 renderMedia 原件|0/0；无|386048 / 386048|各 +2048|未通过|
|B 两遍 loudnorm 成功|−1024/−1024；1024|386048 / 388800|入点各 +2048，后段另见 D|未通过|
|C 分析失败，FFmpeg exit 8|同 A|同 A|同 A|回退通过，时序未通过|
|C 重编码失败，FFmpeg exit 8|同 A|同 A|同 A|回退通过，时序未通过|
|C 编码完成、rename 前失败|同 A|同 A|同 A|回退通过，时序未通过；遗留完整临时文件|
|D 全零 WAV；静音主视频且无 Audio Clip；纯 Shape|0/0；无|386048 / 386048|全零，相关滞后不可定义|负无穷跳过通过，轨长未通过|
|D 真正无音频流 MP4|不适用|无音轨|不适用|正式函数通过，作品端到端未验证|

成功出口的第一遍测量退出 0，第二遍复制视频并重编码 native AAC、192k、48 kHz，rename 后只留下目标，视频包摘要相同。原始/成品重新测得 −20.89 / −16.31 LUFS，−7.69 / −3.27 dBTP；滤镜执行报告为 dynamic，输出 −16.0 LUFS。解码无削波。是否正常播放用全流软件解码、帧编号和采样验证；设备实播与主观听评未验证。

两个子进程故障在指定命令加入无效选项，真实 FFmpeg 分别退出 8；第三个在临时文件确实存在后、调用系统 rename 前抛错。三次相同 catch 都记录错误栈并正常返回原 videoPath，未见响度成功日志。返回类型没有响度结果，上层可以宣布成片 ready。此次前两次未生成响度临时文件，第三次保留的 video.loudnorm.mp4 与 B 字节相同；audio.ts 的异常路径没有 unlink。没有模拟真实断电或存储故障。

全零 WAV、仅静音视频、纯形状三个合法作品都实际输出静音 AAC；后两者甚至实际执行 anullsrc。三者测量均为 −inf，第二遍、rename、临时文件均未出现。单独以同视频包 stream copy 生成真无音轨样本，调用原 normalizeLoudness，只运行 probe 即正常返回，前后哈希相同，240 帧完整。正式函数正常跳过的两个 return 均已区分。

## D. 时钟、采样与文件身份

固定合成作品为 1920×1080、30 fps、240 帧，视频源从第 15 个输出帧对应的源时刻起读。每帧 PTS 应为 i/30，内容应是源时刻 (i+15)/30 最近帧的二进制编号；以实际源帧 PTS 匹配。所有主画面样本 240/240 正确，纯 Shape 样本按第 20 帧出现的矩形核对，240/240 正确。所有视频首包 PTS 0、DTS −6000（时基 1/90000），首个呈现帧 0，视频时长 8.000 s。主画面 H.264 包序列 SHA-256 为 da0db9784d8382a5d34427da90add8424e7231675e6887133b14f12936fe135c（每包 4 字节大端长度加有效载荷）。

|固定声音|源起点|输出帧区间|声音增益|参考采样区间|A/B/C 入点|
|---|---:|---|---:|---|---:|
|Voice|0|[9,159)|−4 dB|[14400,254400)|16448|
|Whoosh|0|[42,78)|−3 dB|[67200,124800)|69248|
|Impact|0|[60,84)|−3 dB|[96000,134400)|98048|

三声重叠为 [96000,124800)，主混音的 Voice 与 SFX 联合重叠为 [67200,134400)。各声部用各自固定 WAV 作匹配，入点表示由整段模板测得的放置误差，允许源本身有静音或软起音。三声相对间隔保持，整个重叠区相对视频晚 2048 采样。参考独立由源 PCM16、线性增益和恒功率 mono→stereo 求和，预期起点双流均为零、总长 384000。参考交错双声道 f32le 摘要 0a0b9caf26f4a6cf29d3251307d263def918eee3ef3018870e959fff77da25b0；版本内容摘要 911e142de5050bed0c956d1e98a433f5f229326080eaef89ddd72a8c0c93b6fd。每份源文件已和编译使用的 digest 比对，见 mix.json。MG 存量 275 项校验见 mg-hashes.txt。

判据为流时间基、首包及 side data、解码 PCM、逐帧 PTS、全部源帧身份、混音与三个声部的互相关都可独立复算。互相关搜索 ±5000 采样。merged.wav 对参考相关 0.99999996，原始 MP4 为 0.989236，成功响度为 0.988805（按最佳平移对齐后计算）。流起点零只能证明媒体时间轴的起始标记；两个声部稠密重叠时也能从模板辨认实际位置。

B 的容器时长为 8.100000 s，A 为 8.042667 s。B 扣去本次编码产生且正确标记的 1024 个前导采样后，解码 PCM 有 386048 个。包 246784 有 1024 个实际解码样本，下一包从 250560 开始。播放时间轴在 [247808,250560) 缺 2752 个采样位置，计时跨度为 388800。以时间戳放置 PCM，在参考尾部窗口 [246000,254400) 实测相对参考 +4800 时相关 0.99975，+2048 时为 −0.0433。三个入点均在间隙前。此处没有将末端 AAC 块补齐算作连续声音，间隙内具体播放器如何输出未验证。

|文件身份|整文件 SHA-256|
|---|---|
|A，三个 C 原件及返回文件|ac59b7927be4eefd9f16ad7302589c77875797434f4aeea915c274b6c1446ced|
|B，hostDefault 重跑，rename 失败遗留的响度文件|cc8a6414fb8b6491576d72384253b1cab6f647d8337d0d5933a54a145e0d66e9|
|D 全零 WAV / 静音视频，前后|29fe0ad53b5a47349845607404fac82144daf0e2c997c1240e0436acd8e991bf|
|D 纯形状，前后|01619c3604ed41b50b4624dbc4712e9eef94674c258124d529694ebaceb67494|
|D 真无音轨函数夹具，前后|1cc785d3819fd3d5cacc3a7f49e7449242c01922e00f175e9785170f19d00ab0|

## E. 第一处错误

1. 真实 merged.wav 有 384000 个采样，首 PTS 0，三个声部滞后均为 0。因此本夹具的来源量化、Clip 放置与混音均已排除。
2. 实际压缩子命令的关键参数为 `-i merged.wav -c:a libfdk_aac -f adts -b:a 320k -cutoff 18000 -y audio.aac`。留下的文件确为裸 AAC/ADTS；解码 386048，三个声部首次均为 +2048，首 PTS 0，无 Skip Samples。裸 ADTS 的 ffprobe 估计时长依赖码率，见 metrics.json；判定使用完整解码。
3. 拼接以 30 fps 的 JPEG 帧序列和 audio.aac 为输入，`-c:a copy -c:v libx264 ... -crf 18 -movflags faststart` 输出 MP4。去除 ADTS 头之后，音频包载荷与原始 MP4 的包载荷 SHA-256 同为 f434c01c151da533a7240ebf43f2241b0c1d9764b5838e4db57ba6549a12d261。MP4 将多出的声音从零开始计时。正式驱动采用默认 320k 和 JPEG，历史 MG 对照采用 192k 和 PNG；二者共享决定性的 ADTS 和音频 stream copy。
4. 独立对照使用本次 merged.wav、同一 FFmpeg、编码器、码率与截止频率，换用 MP4 容器保存中间音频，再与同一视频包 stream copy。最终首 PTS/DTS −2048、skip 2048，解码与时钟都为 384000，三个声部滞后皆为零。control.mp4 是诊断对照。它与 A 的视频载荷相同。
5. 对 A 执行正式 loudnorm 后，native AAC 只标记自己新产生的前导延迟；输入已经多出的 2048 个采样被保留。以正确的原始输入副本加 -debug_ts 重跑第二遍得到与 B 相同的文件摘要。调试日志中，AAC 编码器收到的 frame_pts 已从 246784 跳到 250560。单独响度滤镜输出 PCM、单独 native AAC 转码两组对照均未见该内部间隙，FFmpeg 内部更深的具体函数未定位。另一次诊断误以已替换的 B 作输入，control-2.log 仅为二次处理，不用于本裁决。使用对齐的 control.mp4 重测第一遍、沿用正式第二遍参数，最终 384000 采样、零滞后且 PTS 连续；不需要据此增加第二个生产时间修正。见 clock.json、debug-from-raw.log、aligned-control.json 和 metrics.json。

## F. Audio Agent 研究归档盘点

实际位置 /tmp/repurposer-audio-wwrSsj；25 项 SHA256SUMS 均通过。逐文件计算 Git blob ID 并与 HEAD 树比对，没有一份研究包原文件按相同字节登记在 HEAD。仓库有 MG 独立素材与历史合成旁白/配乐输入。研究包依赖的原始 WAV 和同步片均可读。六份 WAV、测量、同步片及同步记录在本目录 recipe/ 从副本重算。

|资产|找到位置（相对上述旧临时目录）|字节及摘要|复现与缺口|
|---|---|---|---|
|Whoosh 源码与两份 WAV|render.py、catalog.py、whoosh-{default,rev}.wav|各 107564 B，SHA 前缀 a7da9d78 / 48de1dcb|同字节；tone 58→22%|
|Impact 源码与两份 WAV|同源码、impact-{default,rev}.wav|各 71084 B，a3a65969 / a7c4b60f|同字节；body 115→75 Hz|
|Click 源码与两份 WAV|同源码、click-{default,rev}.wav|各 12524 B，25bf5445 / 0de17c16|同字节；hardness 55→14%|
|参数合同|catalog.py/json、sources.json、render.py|已核摘要，含整数类型、单位、上下界、默认、听觉说明、单参数变体、seed 1248|当前环境可复产；主观盲听未验证|
|同步样片|sync.py、sync.mp4、sync.json|MP4 b0b2a89363a228e771373060034b2180b2f9d3828d8c0c2f8f563054496a434d|从本仓 iteration-6 固定研究样本重算，同步片与 JSON 同字节|
|校验、清单与脚本|inspect_audio.py、measurements.json、verify_existing.py、repeat.txt、SHA256SUMS 等|25 项通过，重算 measurements.json 完全相同|本轮复测合成与测量；历史播放日志未重演|
|依赖、许可与来源|REPORT.md、sources.json、catalog.py、sync.py|核对源码、版本、来源摘要与独立原创声明|无单独环境锁或独立再分发许可文件。原创声明不等于授权审计|

最小归档设计是一个研究包，包含原创脚本、目录、参数、固定六 WAV、同步片、测量和完整哈希，记录 Python/NumPy/PyAV/Pillow 及架构、固定输入的仓库相对路径与摘要、复产命令及来源权限说明。批准归档时在新目录复算校验；本轮未实施归档或产品集成。

## G. 生产修复裁决

**建议最小修复，待施工授权。** 已验证的机制是保留编码器的时钟与跳样。4.0.484 的 compress-audio 对 AAC 显式选择 ADTS，公开 ffmpegOverride 仅到 pre-stitcher/stitcher，不能改变那次中间编码。对齐中间文件的实验证据并不证明安装目录可以作为应用修复入口。

建议评审一个项目内、可用当前公共 API 实现的最小切片，拟涉及 apps/render/src/video/index.ts 与 apps/render/src/audio.ts。下列为 diff 设计，尚未将其接入 renderVideo 执行：

- 在 video/index.ts 将渲染目标改为本次任务私有临时 MOV，保留 H.264 与原视觉参数，仅指定公开 audioCodec 为 pcm-16。锁内 H.264/PCM 允许 MOV，PCM 分支复制合并 WAV。无音轨文件需保持无音轨。
- 在 audio.ts 增加生成基线 MP4 的局部操作，读临时 MOV，只复制视频，选择可选音轨并在 MP4 muxer 内直接编码 libfdk_aac，沿用 48 kHz、320k、18 kHz 配置。先完整关闭并原子发布基线，再执行现有可失败的 normalizeLoudness。基线生成失败走渲染失败，不能返回视频单轨残件。临时文件按本次调用清理。保持既有音频跳过和回退语义。
- 此设计增加本地临时 I/O。对齐实验证明的是容器机制，拟议 MOV 方案的像素、色彩、音轨、首尾、成本、无音轨可达性与异常恢复均需单独验证。现有成功响度在对齐输入上已通过本片的时钟对照，暂不另加时间轴滤镜。没有按采样常数改 Clip 或直接升级任何依赖。

**单独验收合同。** 固定本报告四出口与三类注入；加入非 AAC 块整数倍、非 30 fps、视频原声/BGM、裁剪、多段有后段可辨信号的样本，以及目标 Linux 镜像。原始、成功、失败、合法跳过均检查帧身份和载荷、每个声部时间、完整 PTS 连续性、流时长及尾块有效样本；分别核对处理前后 SHA、响度、真峰、无声和无音轨语义。针对本 8 s 夹具要求 240 正确帧、有效跨度及样本 384000、三声部相关峰零偏移、视频起点零、无中段间隙；AAC 本身可有正确声明的负首包。原始 MP4 通过后方可作为回退文件。任一未解释偏差不得交付。

## H. 五面影响

未实施产品变更，五面保留现有合同，本轮没有重新宣称通过。未来切片验收需分别检查：

- Tool：同一用户调用触发原 export_video、授权和 ExportJob；没有额外编辑或生成。
- Context：快照摘要、Clip 源窗、版本与编译时间事实相同，旧版可回放。
- Chat：进度、停止、失败、回退、预览、最终交付与真实文件身份一致。
- Execution：本地矩阵扩展到真实隔离 ExportJob，核对 Output、帧、样本、摘要、费用和版本，核算额外 I/O。
- Recovery：在基线封装、响度替换和上传边界 Stop、重试及强杀，校验围栏、临时文件、原子替换、缓存身份、幂等和费用。

## I. 成本、风险与唯一下一步

8 次完整 renderVideo，依次 18.415、8.310、8.604、9.364、8.831、9.079、5.951、9.886 秒，累计 78.440 秒；另有 1 次无音轨 normalizeLoudness 函数调用。分析和重编码各一次故意 exit 8，一次故意阻止 rename。2 组单阶段时钟控制、1 组换封装并复用视频的控制、2 次 debug 重放（一次输入选错已排除）、2 次对齐输入响度对照。另做探测/解码、六 WAV 与同步片复产。使用本机 CPU、Chrome 和临时磁盘，目录含隔离依赖逻辑占用约 1.7 GiB，run 约 90 MiB；未测整进程树峰值内存。无外部订单或产品费用。风险主要是临时证据可能被系统清理、部署平台与长片未覆盖，以及音频存在性探针无法识别已证实时序错误。

**唯一下一步：架构评审者审批准入上述 AAC 基线封装切片及独立四出口验收合同。**
