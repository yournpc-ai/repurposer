# 竖屏短片编辑器 — 设计与实现计划

> 本文档记录 Repurposer「竖屏短片成片 + 可编辑」这条主流程的最终方案。
> 它是多轮技术评审（对照 OpusClip / Descript / InVideo / CapCut Web）的收口结论。
> 配套：ADR-016（决策记录）、ADR-017（队列地基，已实施）。

## 1. 背景与品类定位

「竖屏短片成片」是 MVP **必须项**，且**必须可编辑**（用户对 AI 产出"必然要改"）。

- **我们的品类 = OpusClip 类**：服务端 AI 流水线 + 浏览器**瘦编辑面** + 把深度精剪**甩给剪映/Premiere**。
- **不是 CapCut Web**：那是客户端 WASM 引擎的"全功能编辑器"，是另一个品类；其技术深度对我们是过度配置。
- **Descript 是交互北极星**：文档式编辑、词↔时间码绑定、非破坏性删除——这些**抄**；它的多图层合成 / 多轨 / Electron 桌面引擎——**不抄**。
- **InVideo** 的对话式微调（"开头改短/翻成法语"）作为编辑辅助入口，后置。<br>　　↳ 届时 UI 可用 shadcn chat 组件（`MessageScroller` + `Bubble` + `Marker` 显示"正在翻译…/裁剪…"，2026-06 changelog）——现在不引（无对话面，引即负债）。注意它们与本项目 base-ui 版 shadcn 的 registry/风格需先确认兼容。

> 核心哲学：**在"广度"上弱到只剩一条主流程，但这条线做到 Descript 级精致。** 线之外一律砍掉、诚实交给下游。

## 2. 「更轻更弱」的边界（做什么 / 不做什么）

| 级别 | 内容 | 取舍 |
|:---|:---|:---|
| **L1** | 文本资产 + 字幕纠错 + 模板图形（金句卡） | 大半已建 |
| **L2（本文档主体）** | 基础竖屏成片：裁段 + 烧字幕 + 品牌样式 + 配乐 + 片头尾 → MP4 + SRT；文字稿式编辑 + 单轨 trim | **已实施** |
| **L3** | 多轨 / 图层合成 / 转场特效 / B-roll 库 / 自动人脸追踪 reframe / 桌面离线 / 客户端引擎 | **永不做，甩剪映** |

**精致的标准**：① 预览=成片像素一致；② 多语字幕准且可一键改；③ 一键就有能直接发的成片（编辑可选非必须）；④ 删句=剪视频可撤销；⑤ 克制统一 UI + 诚实（做不到的明说"导出到剪映精修"）。

## 3. 核心决策：钉死契约，渲染器当可替换黑盒

**唯一钉死的架构决策 = 一份声明式 `clip-spec(JSON)` 作为唯一契约。** 它背后的渲染器是可替换实现。

```
clip-spec(JSON)  ← 永久契约（渲染器无关，只描述「是什么」，不含 React/Remotion 概念）
     │
     ├──► 预览：Remotion <Player> 在浏览器实时渲染（编辑器画布）
     └──► 出片：Remotion 渲染服务（无头 Chrome + 内部 FFmpeg）→ MP4 + SRT
```

- **第一个渲染器选 Remotion**（服务端，无头 Chrome + FFmpeg）：parity（预览=成片）结构上天然成立、媒体脏活（音画同步/解码/seek/字体）成熟、`<Player>` 直接当预览、与我们 React 栈契合。
- **把它当黑盒**：`spec 进 → MP4+SRT 出`。Python 队列经 HTTP/CLI 触发，边界干净，不与 Python 后端纠缠。
- **低后悔**：因为 spec 是稳定契约，将来若有**账单/规模**问题，可换成**手搓 FFmpeg**（见 §9）或**客户端 WebCodecs**，spec 不动、不伤筋动骨。
- **为什么不一开始就手搓**：我们干的是"视频处理"，FFmpeg 确实对口，但手搓要自己保证 parity（两端渲染引擎不同会漂）+ 自己趟一长串媒体边界坑。对小团队，Remotion 把这些一次性买掉，换来更快的精致 MVP。代价是一个 Node 渲染服务 + license（4+ 人 $25/seat 或 $0.01/render）。
- **为什么不上 CapCut Web / 客户端引擎**：编辑需求最高只到"裁段+字幕+样式"，够不到多轨 NLE；自研 WASM 引擎是给不存在的需求付几年工程。

## 4. 契约层：clip-spec 数据结构

**原则**：渲染器无关；只描述"是什么"；样式限定在**一组预设内（CSS 与 libass 都能表达）**，以保留将来换手搓 FFmpeg 的低成本。

```jsonc
{
  // kind="video"：真人出镜，url 是视频；kind="stills"：图片音频图，
  // url 是可选语音轨（无录音为 ""），image_urls 是垫底图（0→纯色 / 1→满屏 / N→均分硬切轮播）
  "source": { "asset_id": "uuid", "kind": "video", "url": "/api/v1/files/...mp4", "image_urls": [], "fps": 30, "duration": 120.5 },
  "aspect": "9:16",                         // 9:16 | 1:1
  "segments": [                              // 保留区间列表；删句=把某区间标 hidden（非破坏性）
    { "start": 12.4, "end": 31.0, "hidden": false }
  ],
  "crop": { "x": 0.5, "y": 0.5, "scale": 1.0 }, // 归一化中心+缩放；用 transform 实现，不用 object-position
  "caption_track": [                         // 来自 ASR 词级时间戳；用户可改 text
    { "start": 12.4, "end": 12.9, "text": "So", "lang": "en" }
  ],
  "caption_style_preset": "clean-bottom",   // 预设枚举，非自由样式
  "caption_position": { "x": 0.5, "y": 0.84 }, // 归一化中心点(拖拽定位)；null→默认底部
  "title": { "text": "The hook", "enabled": true, "size": 56, "position": { "x": 0.5, "y": 0.12 } },
  "music": { "track_id": "calm", "url": "/api/v1/music/calm", "enabled": true, "gain_db": -18 },
  "dub": { "url": "/api/v1/outputs/.../dub_fr.mp3", "enabled": false, "gain_db": 0 }, // 语音克隆配音；enabled 时静音原声
  // brand 块在生成时由 API 从选定 BrandTemplate(brand_template_id，缺省取最新)解析并烘焙，renderer 不读 DB
  "brand": {
    "logo_url": "https://example.com/logo.png",
    "cta": "Read the full talk →",
    "cta_position": { "x": 0.5, "y": 0.92 },  // 归一化中心点(拖拽定位)
    "caption_color": "#22c55e",
    "caption_size": 56,
    "caption_font": "lilita",                 // lilita | inter | playfair | source-serif
    "intro_text": "From the keynote",
    "outro_text": "Follow for more insights",
    "fill_mode": "fill"                       // fill (cover) | fit (contain)
  },
  "brand_ref": "brand_template_uuid",       // provenance：哪个品牌模板
  "target_language": "en"
}
```

- **非破坏性**（抄 Descript）：删一句 = 把该 `segment` 标 `hidden`，不真删，可恢复。
- `caption_track` 既驱动**烧录字幕**，也直接导出 **SRT**（给下游剪映精修的交接物）。
- 样式走 `caption_style_preset` 枚举（如 `clean-bottom` / `karaoke-highlight`），**不开放自由排版**——这正是"所见即所得"和"将来可换 libass"的前提。
- **品牌进渲染**：`brand` 块在生成时由 API 解析 `BrandTemplate` 并**烘焙进 spec**，渲染服务/预览只读 spec、不读 DB，保证 parity 且 renderer 保持黑盒。
- **配乐进渲染**：`music.url` 指向内置 mood 曲库（`/api/v1/music/<mood>`）或任意绝对 URL，`<Audio>` 循环混音，gain 用 `gain_db`。
- **片头尾**：`brand.intro_text` / `brand.outro_text` 存在时，输出时间轴前后各插 2 秒标题卡；视频主体 `<Sequence>` 后移，字幕重映射自动对齐。
- **两种 source kind（成片不限真人录像）**：`source.kind="video"` 走 `<OffthreadVideo>`（现状）；`source.kind="stills"` 是**图片音频图**——`image_urls` 作垫底视觉（1 张满屏 / N 张按时长均分**硬切**轮播 / 0 张纯色兜底），`url` 为可选语音轨。有音频时复用 ASR 词级 `caption_track`；无音频时为固定时长幻灯片（每图 `SECS_PER_IMAGE` 秒）。垫底视觉来源：**幻灯片 PDF 逐页渲染图（`Asset.slide_pages`）在前** + 上传照片在后；选源优先级 VIDEO→AUDIO→SLIDES/IMAGE。**刻意不做**转场 / Ken-Burns / 多句动画文字轨 / B-roll（守 L2，见 ADR-020）。
- **文字拖拽定位**：`caption_position` / `title.position` / `brand.cta_position` 是归一化中心点 `{x,y}∈[0,1]`（= libass `\pos`，可移植），null→渲染器默认。`title.size` 是合成像素字号。品牌页在预览上叠透明层拖拽这三个文字叠层(safe-zone + clamp)。**只移动，不做缩放/关键帧运动**。
- **语音克隆配音（dub）**：`POST /clips/{id}/dub` 用演讲者声音(VOICE_SAMPLE/AUDIO/VIDEO 抽轨)经 MiniMax voice_clone + T2A 把(翻译后的)字幕配成目标语言，烘焙成 `dub` 轨；渲染时 `dub.enabled` 则**静音原声**改播配音(叠加、不口型同步，见 ADR-021 与 memory)。
- **图片视觉理解**：IMAGE 资产经 M3 多模态(`services/vision.py:describe_image`)提取核心信息写入 `Asset.extracted_text`，像其它素材一样进 analyzer 的 materials。
- **意图通道**：主页提示词 = `GenerateRequest.instruction`，传给 analyzer/script 及 linkedin/quote_card/carousel/summary/blog，据此挑片段、定 hook/标题、产出侧重。
- **品牌模板多套**：CRUD + 启动种默认；生成时 `brand_template_id` 选用(缺省取最新)。`aspect`(9:16/1:1)与三处位置点也从模板烘焙进 spec。
- **Speaker = 用户画像**（ADR-021）：persona(风格) + 声纹(声音样本/克隆 voice_id)挂在画像上;dub 优先用画像声纹、克隆一次复用。本次主题/意图属 Project。

## 5. 前置依赖（从可选 P1 升级为硬前置）

没有这两块，编辑器搭不起来：

| 前置 | 选型 | 为什么是硬前置 |
|:---|:---|:---|
| **可流式播放/seek 的视频 URL** | **本地文件系统 + FastAPI Range(206) 流式端点即可**。对象存储（MinIO/S3 EU）是**规模化/多实例**事项，按 ADR-011 留到 P1/生产，**不是 MVP 前置** | 裁段/预览要在浏览器**播放 + seek** 源视频 |
| **多语 ASR（词级时间戳）** | 自托管 WhisperX / faster-whisper（EU/GDPR，非云 API） | 字幕实时叠层 + 字幕编辑的根基（= Descript "forced alignment" 的等价物） |

标准 MP4/H.264 上传**浏览器直接可播**（走本地 Range 端点），无需转码。仅当上传**非浏览器可播放格式**（.mov/.mkv/奇怪编码）时才需 proxy 转码（H.264/AAC）——这一步**可延后**，不是 MVP 前置。注意：**Remotion 渲染自带打包的 ffmpeg，faster-whisper 用 PyAV(wheel 内置 ffmpeg)**，二者都**不需要系统 ffmpeg**；系统 ffmpeg 只有 proxy 转码这一处可能用到。

**未来上云的口子（现在就预留）**：保持 `storage.py` 为唯一存储边界（ADR-011 已抽象一层），纪律：
- 视频 URL（`Clip.video_url` / 源视频）一律是**间接寻址**——前端 / Remotion 拿到的是"一个可播放 URL"，由存储层解析，**绝不写死本地路径**。
- 现在该 URL 指向**本地 Range 端点**；将来换对象存储时，存储层改为返回 **MinIO/S3 预签名 URL**（同样支持 Range），`clip-spec`、前端、Remotion 组件、worker **全部不改**。
- Range/读取逻辑收在存储层之后；迁移 = 只换 `storage.py` 实现 + 配置，调用方零改动。

## 6. 渲染层

```
┌────────────┐   spec(JSON)   ┌──────────────────────┐
│ Python      │ ──HTTP/CLI──► │ Remotion 渲染服务(Node)│
│ worker(队列) │               │ 无头 Chrome 渲帧 +     │
│ 已建        │ ◄──MP4+SRT──── │ 内部 FFmpeg 编码       │
└────────────┘                └──────────────────────┘
```

- Remotion 组件 `<Clip>` 消费 `clip-spec` 作为 `inputProps`；**同一份组件**给 `<Player>`（预览）和渲染服务（出片）。
- Node 渲染服务用 **pnpm** 启动（符合 ADR-001 各用各的包管理器），自托管在 EU。
- 触发：现有 Postgres 队列（见 ADR-017）新增一个"渲染"认领源（`Clip.render_status`），worker 调渲染服务。
- 照抄 Remotion 的 FFmpeg 编码参数（codec/bitrate/pixfmt），这部分本就是纯 FFmpeg。

**项目结构（ADR-018）**：`<Clip>` 组件必须被 web 的 `<Player>`（预览）和 render 的 `renderMedia`（出片）共用——这是 parity 的根，所以抽成共享包：

```
apps/render/        Remotion 渲染服务（@remotion/bundler + renderer + express）→ POST /render: spec→MP4+SRT
packages/clip/      共享 <Clip> 组件 + clip-spec TS 类型（mirror Pydantic）
apps/web/           编辑器用 @repurposer/clip 的 <Clip> 放进 <Player>
pnpm-workspace.yaml web/render/clip 工作区；api 独立用 uv，不在工作区
```

源视频 URL：render 的 `spec.source.url` 必须是**绝对 URL**（worker 调用前把存储 seam 的相对 URL 绝对化）。render 把 MP4/SRT 写到共享 `data/outputs`，api 经 Range 端点服务。

## 7. 编辑器交互（瘦编辑面，非多轨 NLE）

一屏布局（参考 OpusClip/Descript，但只留主干）：

```
┌────────────────────────┬───────────────────────────┐
│   9:16 预览 (<Player>)  │  转写文本（可编辑）⟵编辑重心 │
│  实时字幕 + 可拖裁切框   │  点词改字（修 ASR/翻译错）   │
│      ▶                  │  选句删除 = 段落标 hidden(可恢复)│
│                        │  Tab: 字幕|构图|品牌|配乐    │
├────────────────────────┴───────────────────────────┤
│ ▭▭ 单轨片段带  [⟸trim  trim⟹]  ●场景标记 ▭▭▭▭▭▭ │ ⟵ 只 trim/scrub/跳转
└──────────────────────────────────────────────────────┘
                                         [ 导出 MP4+SRT ]
```

- **编辑重心在转写文本面板**（删句/改字/换语言），单轨带只做 trim/scrub。
- 换语言：切 `caption_track` 的 `lang`（触发重新翻译）。
- 默认产出即可发；编辑是可选。

## 8. 数据模型扩展

`Clip` 表新增（走 Alembic 迁移，复用已建队列）：

| 字段 | 类型 | 用途 |
|:---|:---|:---|
| `render_spec` | JSON | clip-spec 契约 |
| `render_status` | Enum(pending/rendering/completed/failed) | 渲染任务状态（worker 认领源） |
| `render_error` | Text nullable | 失败原因 |
| `video_url` | String（已有） | 成片 MP4 |
| `srt_url` | String nullable | 导出字幕 |

**同一迁移顺手清理旧 ADR-008 图片轮播模型的死列**（实测从未写入/读取）：`Asset.keyframes`、`Clip.subtitles`（字幕改由 `render_spec.caption_track` 承载）。`Asset.slide_pages` 现已启用：SLIDES 上传时 PyMuPDF 逐页渲染成图存入，喂给 stills 的 `image_urls`（见 ADR-020）。

**新旧模型协调（关键设计决策，勿遗漏）**：现有 `Clip.script`（ADR-008 的分镜脚本：`time_range`/`visual`/`mood`）与 `music_mood` 是"图片轮播 + 画面建议"范式，与新的"真实视频段 + ASR 字幕"范式部分冲突。落地 clip-spec 时必须明确：
- `render_spec` **替代** `script`，还是 `script` 退化为"AI 建议"用来 **seed** `render_spec`；
- `visual`（画面建议）对应 B-roll，属 L3，不进 render_spec；
- 生成流程（`services/generation.py`）需相应产出 clip-spec，而非只产出旧 shots。
- `virality_score` 与"反 viral、知识资产"定位的清理是**独立议题**，不在本编辑器范围内。

## 9. 未来可替换路径（spec 不变）

| 触发 | 换成 | 代价 |
|:---|:---|:---|
| Remotion 账单/规模问题 | **手搓 Python+FFmpeg+libass**：clip-spec→FFmpeg filtergraph 一遍过；字幕用 `.ass`，预览侧用 **libass.wasm（JavascriptSubtitlesOctopus）** 渲同一个 .ass → 两端共享 libass 保证 parity | 渲染逻辑自己写；.ass 动画有天花板（我们够不到） |
| 想要"视频不出浏览器" + 降本 | **客户端 `@remotion/web-renderer`（WebCodecs）**：我们的合成落在其 CSS 子集内（见限制清单），是真实可行的开关 | alpha 阶段；GDPR 收益有限（ASR 仍服务端）；可能仍需服务端 proxy |

> GDPR 主线仍是**服务端全栈 + EU 区域部署**；客户端渲染只是降本备选，不是 GDPR 答案。

## 10. 阶段拆分

```
0. 队列地基（已建：Postgres 当队列 + worker + Asset 状态机）  ✅
1. Range 流式端点（本地文件，可播放/seek）+ 源视频 proxy 转码（格式归一）
   —— Range 已建；proxy 转码延后（非浏览器可播格式才需要）
2. 多语 ASR（词级时间戳）→ 已接进 worker 的 asset processor  ✅
3. clip-spec 契约 + 表迁移 + Remotion 组件 + Node 渲染服务 + 队列触发 → ✅
   品牌（logo/CTA/色/字号/字体/fill/片头尾）与配乐已烘焙进 clip-spec  ✅
4. 编辑器 UI：<Player> 预览 + 文字稿编辑（删句=剪段/非破坏性）+ 单轨 trim + 样式/标题/配乐 + 字幕换语言  ✅
```

## 11. 验证

- 打通即验证：上传演讲视频 → ASR 出词级字幕 → 编辑器改一句/删一句/换语言 → 预览实时反映 → 导出 → **成片与预览像素一致** + SRT 可被剪映导入。
- parity 回归：随机抽 spec，比对 `<Player>` 截帧与渲染服务出片首帧。
