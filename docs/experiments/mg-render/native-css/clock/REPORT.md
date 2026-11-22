# 架构评审 · V7 标题由作品帧驱动

**结论：对本次实际 Motion Block，显式作品时间合同足够。** V7 标题仍在前景 PiP 下方移动，保留原字形、颜色、毛玻璃与余弦位移。Chromium 插值一个数值型 CSS 属性，CSS 求纵向位移。宿主只认作品对象、片段范围、FPS 和暂停的 Animation，无需理解余弦、文字、遮罩或混合模式。

## 求值合同

1. 输入固定版本、整数作品帧 `k`、有理帧率 `num/den`。按原场景半开区间挂载可见对象。局部绝对时间为 `(k − clip.start_frame) × 1000 × den / num` 毫秒。每次从作品重新计算，包括再次请求同一个 `k`。
2. 在 React 的 layout effect 中创建 `KeyframeEffect` 和 `Animation`，立即暂停并定在零，卸载时取消。本块用两端关键帧表达局部帧从 0 到片段长度的线性变化，CSS 计算 `10px × cos(localFrame / 16)`。从作品派生时长，不累加时间，也没有另存关键帧轨道。
3. `flushSync` 提交本帧树和图片地址后，宿主枚举当前动画，按祖先的 `data-object` 找到该帧的活动 clip，检查暂停状态并写入 `currentTime`。等待 `animation.ready`，触发布局求值，等待实际源图 `decode()` 与 `document.fonts.ready`，最后通过 CDP 截图取得浏览器合成结果。截图解码为 1920×1080、按行排列的 RGB8，再求 SHA-256。等待屏障没有猜测性的延时。暂停动画的 hold time 和显式 seek 的行为见 [Web Animations 时间模型](https://www.w3.org/TR/web-animations-1/#setting-the-current-time-of-an-animation)。
4. 本实验沿用固定入口，只处理已挂载、可发现的 DOM 动画。Agent 在此研究子集中可以使用显式帧函数，或把受控动画绑定到作品对象并交给宿主逐次定位。自主播放的 WAAPI、自由运行的 CSS keyframes/transition、用 rAF 或计时器推进状态、以视频播放头驱动画面，以及没有相同绝对定位保证的第三方动画，本次均不准入。此处的暂停检查也不能证明任意 JS 没有其他副作用。

## 同一作品与证据

复用原 C 宿主、两段 H.264 源、按 PTS 选取的源图、原有两个 Motion Blocks 及三条音轨。重建 V7 后先与归档逐字节比较。V8 只换 `signal-title` 的 Generator 源，V9 只改同一对象的 `ink`。V7→V8→V9 的 object_id 始终为 signal-title。两次修改各产生同一 Composition 的一个研究子版本，经原模型及 validator 校验。各页只消费指定版本，原 V7 帧函数另页作参照。源与宿主改动分别见 [Readout.tsx](Readout.tsx) 和 [host.diff](host.diff)。

| 检查 | 观测 |
|---|---|
| 顺序输出与原视觉 | V7 与 V8 的 240 帧整幅 RGB 逐帧相同，含遮罩、混合、模糊与遮挡。 |
| 乱序和重复 | 72、239、30、179、0、45、180、15、209 均匹配顺序表。再取 72、72、30、72，涵盖同帧连取、活动区内倒退和回到原帧。 |
| 同进程等待 | 第 72 帧定位一次，对已经就绪的页面额外等待 0、120、530 ms，连续截图。每次均为 paused / 1400 ms，同一 RGB 摘要。延迟只用于扰动。 |
| 独立进程 | 新 Python 进程和新 Chromium 从帧 239 倒序至 0，240 次均匹配顺序表。复用只读的源图和 bundle。 |
| 定向改色 | V8→V9 的 150 个活动帧均有变化，逐帧校验所有变化像素在标题的实际包围盒内。其余 90 帧零差异。第 72 帧变化界限为 (1264,216)–(1573,283)。 |
| 视频、层级、声音 | 从画面读出的源编号与原 V7 记录吻合，主视频 240/240，PiP 195/195。V8 全画幅与 V7 相同，V9 的层序未改。原混音函数对 V7/V8/V9 输出相同的 48 kHz 双声道 s16le PCM，每声道 384,000 个采样。本轮验证止于未编码画面和混音。 |

原始记录：[顺序、源编号及编辑范围](evidence/sequence.json) · [乱序与重复](evidence/seek.json) · [等待](evidence/hold.json) · [独立逆序](evidence/replay.json) · [混音](evidence/audio.json)。

## 失效条件

上一轮在作品帧固定时观察到自主动画的 opacity 从 0.996661 变成 0.966662，当时仅记录样式值。本轮在同一帧另取完整像素，分别放行标题动画、重演原五秒图像淡出并等待各自的 finished。淡出对照加上 forwards 以保留端点供截图。两次都得到错误画面。恢复暂停并重新按作品帧赋时后，标题回到原像素。在开发对照中，仅依靠 React 的 frame 依赖更新时，同帧请求未重新运行 effect，故将 seek 放在每次抓帧入口。首轮编辑范围断言也曾误把活动标题限制在 y < 300，第 30 帧实际延至 y=301，最终使用每帧实际 DOM 包围盒。[旧观察](../evidence/wall-clock.json) · [原始与恢复的完整像素摘要](evidence/uncontrolled.json)

## 复现

从仓库根运行，沿用 baseline/env.sh 的 macOS arm64、Python 环境、固定 Chromium、字体和 Node 锁。入口在新的临时目录中准备源图和产物，打印结果路径。默认 npm ci，也可通过 ABC_MODULES 指向同锁的 node_modules。确定性结果自动与随附归档比较。清单按 clock 目录为根。

```sh
bash docs/experiments/mg-render/native-css/clock/run.sh
(cd docs/experiments/mg-render/native-css/clock && shasum -a 256 -c SHA256SUMS)
```

## 实际成本与结论边界

同机使用已有同锁 Node 模块、从空源帧缓存运行完整研究命令耗时 **101.19 秒**。0.2 秒间隔采样子进程树 RSS，含 Python、Playwright 和 Chromium。顺序组并行保有三个页面，每帧依次捕获 V7、V8、V9，再做全幅差分，其耗时不能用作单路渲染速度。

| 阶段 | 墙钟秒 | 采样峰值 MiB |
|---|---:|---:|
| 子版本校验与源图准备 | 3.48 | 317 |
| 全片顺序三页对照 | 66.30 | 1,706 |
| 乱序、重复、等待及自主播放负对照 | 11.54 | 723 |
| 独立进程全片逆序 | 18.87 | 1,306 |

两段源视频解出 213 + 184 张 PNG，连 PTS 索引共 68,018,811 字节。测试版页面 bundle 为 611,765 字节，开发对照页和临时浏览器 profile 另计。测试机使用与原归档相同 SHA-256 的 Chromium 149 与 Arial Bold。完整复现还需原仓 Python 依赖、Node 锁与五份固定素材。[时间与 RSS](evidence/bench.jsonl) · [缓存与浏览器摘要](evidence/inputs.json) · [原环境](../evidence/environment.json)

另从空目录使用 npm ci 离线安装锁定的 182 个包，完整复跑耗时 104.95 秒。两个版本文件、三组定位结果、原始失败与恢复摘要及混音记录均与归档逐字节相同。[独立复跑计时](evidence/clean-bench.jsonl)

**评审范围**是固定 Chromium、固定资源、30 fps、无变速片段内的离线逐帧求值。本次可以接受这个时钟合同用于该受信 Motion Block。跨平台像素一致、实时播放、任意第三方动画和生产 Renderer 替换均未验证。
