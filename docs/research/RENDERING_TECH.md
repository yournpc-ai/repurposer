# 竞品渲染与编辑技术栈调研

> **状态**: v1.0 · 2026-07-19
> **方法**: JS bundle 取证（下载生产环境 webpack/next chunk 直接 grep）、官方开源仓库（opus-pro/opus-skills、ChatCut-Inc/agent-plugin）、官方 API 文档、招聘 JD、工程博客、DNS/infra 分析
> **关联**: `../COMPETITIVE_ANALYSIS.md`（事实层）、`../DECISION_MATRIX.md`（决策层）、ADR-016（我们的 clip-spec + Remotion 决策）
> **一句话结论**: **Submagic、ChatCut 确认全栈使用 Remotion（与我们相同）；Crayo、Revid 客户端确认 Remotion Player；OpusClip 是自研 GPU 渲染 + 与 clip-spec 结构同构的 JSON EditingScript；Descript 是唯一走客户端 WebCodecs 路线的异类；七家中无人使用 Creatomate/Shotstack 等白标渲染 API。**

---

## 1. 总览表

| 竞品 | 服务端渲染 | 浏览器预览 | 字幕实现 | 预览=导出？ | 置信度 |
|:---|:---|:---|:---|:---|:---|
| **Submagic** | **Remotion Lambda**（us-east-2，50 帧/λ，并发 3，5.3–10GB）+ **EC2/SQS 兜底**，按成本阈值路由 | **Remotion Player 4.0.339** + @remotion/webcodecs | Remotion React 组件（**无 ASS/libass**） | ✅ 同一 composition 两端渲染 | **确认**（bundle 泄露完整配置） |
| **ChatCut** | **Remotion Lambda** + S3；侧车导出 ProRes 4444 / NLE XML | DOM 层预览（Remotion 帧模型） | 浏览器内 "Remotion caption page planner" | ⚠️ **否**——DOM 预览 vs canvas/Lambda 导出，官方文档自曝漂移陷阱 | **确认**（官方插件仓库自述） |
| **Crayo** | 未验证（后端 Render.com） | **Remotion Player** + mediabunny (WebCodecs) | — | 推测分离 | 客户端确认，服务端推测 |
| **Revid** | 未验证；核心是 Veo3/Sora2/Seedance/Kling 模型编排 + 自合成 | **Remotion Player** + MediaBunny（media-parser 兜底） | 预设式 | 推测分离 | 客户端确认，服务端推测 |
| **OpusClip** | **自研闭源 GPU 渲染器**（GCP/GKE + Temporal 工作流 + Celery/Redis；官方明确"不是 ffmpeg，是硬件加速渲染管线"） | **服务端低清预览 MP4**（`VIDEO_PREVIEW` 与 `VIDEO_FILE` 两次独立渲染） | 服务端烧录，逐词 `textElements`（每词 color/timing），emoji 轨，RTL/复杂字形处理；引擎未公开 | ❌ **否**——预览/导出两套产物，字幕不同步投诉集中 | 渲染器细节未公开，其余确认 |
| **Descript** | **客户端 GPU 渲染**（WebCodecs 编解码 + WebGL 合成，全程 GPU 零拷贝）；云端只做无状态转码流（Media Transform Server）+ GPU AI 特效服务器 | 与导出**同一引擎**（WebGL 合成器） | WebGL 合成（跟随转写，wordbar 微调）；无 libass 痕迹 | ✅ 是（同引擎） | **确认**（官方工程博客 + bundle 指纹） |
| **Repurpose.io** | 未验证（AWS us-east-2，legacy Bootstrap/jQuery 面板，无 SPA） | legacy 服务端渲染 UI | 烧录源字幕（推测 FFmpeg） | n/a | 仅 infra 确认 |

## 2. 关键深拆

### 2.1 Submagic —— Remotion 路线的"抄作业"对象

生产 bundle 里泄露了完整的 RenderProvider 配置（服务端逻辑误打进客户端 chunk）：

```
compositionId:"main-comp", fps:30, regions:["us-east-2"],
memorySizeInMb:5308, diskSizeInMb:10240, higherMemorySizeInMb:10240,
timeoutInSeconds:300, highTimeoutInSeconds:600,
concurrencyPerLambda:3, framesPerLambda:50, bucketName:"submagic"
```

- **双渲染路径 + 成本路由**：`getLambdaCostThreshold()`（默认 200）、`isDisabledLambda()/isDisabledEC2()` 开关、EC2 路径走 SQS 队列——**Lambda 与 EC2 按渲染成本动态选择**，这是我们规模化时可直接借鉴的成本模式
- **Remotion 版本 4.0.339**；前端 Next.js/Turbopack on Vercel，tRPC 数据层；导出经 CloudFront
- **字幕 = Remotion React 组件**（主题对象 `captionTheme`、逐语言变换如 `applyGermanCaptionUppercase`），无 ASS 管线——预览与导出天然一致（注：这与此前"预览/导出漂移"的评测报告存在张力；漂移更可能来自字体/emoji 在不同渲染环境（Lambda 容器 vs 浏览器）的 fallback 差异，而非双引擎）

### 2.2 ChatCut —— 官方文档自曝的 preview/export 架构分裂

其开源 agent-plugin 仓库（`skills/*/SKILL.md`）明确写着：

- 云渲染 = **Remotion Lambda** + S3（"Do not tell the user they need to understand HTML-in-Canvas, Remotion Lambda, or S3 unless debugging"）；本地导出 = Chrome html-in-canvas（`gl.texElementImage2D` 读 paint 阶段快照）
- **官方原话承认预览≠导出**："Preview uses a DOM layer instead… Preview rendering correctly is NOT evidence that export will work"——并列出 3 类"预览正常但导出黑帧"的 CSS/SVG 模式（canvas-pipeline-rules.md）
- **这份"canvas-pipeline-rules"文档是我们现成的 clip-spec 渲染 lint 规则清单**——哪些 CSS/SVG 写法不能进 clip-spec，直接引用
- MG（动态图形）是手写 JSX + `frame`/`interpolate()`（Remotion 惯用法）；字幕分页由浏览器内 "Remotion caption page planner" 计算（SRT 侧车导出不复用该 planner，故换行"近似而非字节一致"）
- 数据层 Rocicorp Zero sync + Drizzle；编辑器 React-Router SPA on CloudFront；转写实验用 WhisperX

### 2.3 OpusClip —— 自研渲染 + 与 clip-spec 同构的 EditingScript

- **渲染器自研闭源、GPU 加速**；官方 blog 明确与 ffmpeg 划界："ffmpeg works for simple cases. The OpusClip render API adds aspect-ratio handling, audio crossfade, hardware-accelerated rendering…"
- infra 确认：GCP/GKE + **Temporal** 工作流 + Python/TypeScript + Celery/Redis + vLLM/TensorRT（JD 佐证）；30 秒 clip 重渲染约 30-45 秒；并发上限 50 项目
- **EditingScript = clip-spec 的行业同构证据**（官方开源文档）：
  - 树形结构 **tracks → sections → segments → elements**（KeyFrameTrack/CaptionTrack/EmojiTrack/BRoll/ScreenOverlay/TextOverlay）
  - **双坐标系**：`duration.{sO,eO}`（源素材偏移，含 `sOAdj/eOAdj` 覆盖）+ `timeline.{in,out}`（输出时间）——与 clip-spec 的"segment/crop/字幕轨/样式预设"思路一致
  - Web 编辑器 Save = 提交 EditingScript JSON → 服务端重渲染；API 就是这个 Save 动作的 passthrough
- **预览/导出是两次独立服务端渲染**（`VIDEO_PREVIEW` 低清 artifact vs `VIDEO_FILE` 高清）——无像素一致性，字幕不同步投诉集中（Canny 官方在修）

### 2.4 Descript —— 唯一的客户端引擎派（官方工程博客，2024-07）

- 2018 Electron + 原生 FFmpeg（Beamcoder）→ 2024 重建为 **WebCodecs + WebGL + WebAssembly** 客户端媒体引擎：GPU 内完成解码→合成→编码，4K 导出快 2-3 倍
- **赞助了 libav.js**（FFmpeg 的 WASM port，用于 demux）+ MP4Box.js（mux）；生产 bundle 指纹确认（VideoEncoder.isConfigSupported 探测、loudnorm/volumedetect、mp4box ×13）
- 云端 = 无状态 Media Transform Server（统一转码 + 按需分块流式传输）+ GPU AI 特效服务器（绿幕/眼神校正，帧级 AI 处理快于实时播放）
- **预览=导出同引擎**（WebGL 合成器两端复用）——它用客户端路线实现了我们用 Remotion `<Player>` 实现的同一个目标

## 3. 对我们 clip-spec + Remotion 架构的验证与行动项

### 3.1 被验证的赌注
1. **Remotion 选型正确**：品类里最成功的两家独立产品（Submagic、ChatCut）与我们完全同栈，Crayo/Revid 客户端也在 Remotion Player 上——生态、人才、文档红利都在我们这边
2. **JSON 编辑契约是行业收敛设计**：OpusClip 的 EditingScript（tracks/sections/segments + 双坐标系）与 clip-spec 结构同构——clip-spec 扩展兼容方向正确；**建议对照 EditingScript 的双坐标系（源偏移 sO/eO + 输出 timeline in/out）审查我们 clip-spec 的时间模型**，尤其是"非破坏 hidden + trim 覆盖"与它们 `sOAdj/eOAdj` override 的对应关系
3. **预览=导出同组件（ADR-016）是真实差异化**：Opus（两次独立渲染）、ChatCut（DOM 预览 vs canvas 导出）都在此有系统性痛点；Submagic 与我们同路线。坚持"`<Player>` 即渲染"不可妥协
4. **无人用白标渲染 API**（Creatomate/Shotstack/JSON2Video 零检出）——自渲染是这个品类的入场券，不存在"买 pipeline"的捷径竞争

### 3.2 可直接抄的作业
1. **Submagic 的 Lambda↔EC2 成本路由**（阈值 + kill switch + SQS）：我们渲染规模化时的成本模型参照；其 Lambda 参数（50 帧/λ、并发 3、300s 超时）可作初始基准
2. **ChatCut 的 canvas-pipeline-rules 失败模式清单**：转化为 clip-spec 的**禁止样式 lint 规则**（哪些 CSS/SVG 模式不许进入 clip-spec 子集），从第一天防止预览/导出漂移
3. **OpusClip 的重渲染计费语义**（"Re-rendering is asynchronous and charged"）+ 时间段滑块：成本告知交互参照

### 3.3 需要保持的差异
- Descript 的客户端 WebCodecs 引擎投入巨大（6 年重写）——**不要跟随**；我们的服务端 Remotion 路线对"零剪辑技能 + 机构合规（数据不出 EU）"的场景反而是优势：重活全在服务端，浏览器零门槛
- OpusClip 自研 GPU 渲染器同样不跟随——它服务的是百万级用户的吞吐；我们的差异化在内容智能而非渲染性能

## 4. 未解问题（如需要可深挖）

1. OpusClip 编辑器交互预览的具体实现（auth 墙后，需登录态 WebBridge 抓取 editor bundle）
2. Crayo/Revid 服务端是否也是 Remotion Lambda（无泄露证据；Revid 模型编排后的自合成层未知）
3. Submagic "预览/导出漂移"投诉与其单引擎架构的张力——字体/emoji 在 Lambda 容器 vs 浏览器的 fallback 差异是最可能解释，可在其社区找实证
