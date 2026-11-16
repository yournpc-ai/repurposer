# Rendering — 渲染链架构（spec families · 烘焙缝 · 渲染服务 · 共享包）

> Status: 活跃（2026-11-10 更新）。本文描述当前代码的 clip-spec / video-spec 契约与渲染链。CompositionVersion → video-spec 的架构归 [VIDEO_PROJECT](VIDEO_PROJECT.md)，施工归 [统一视频合同](tasks/skill-package-promo-video.md)。旧 Film renderer 与分派已删除；Clip 保留。
> 上游决策：ADR-016（契约锁定 / 渲染器黑盒）/ ADR-018（服务拆分 + 共享包）/ ADR-020（stills 第二源）/ ADR-023（音乐入库烘焙）/ ADR-024（存储缝）/ ADR-026（C2PA 读 spec）/ ADR-032（Operation Model 快照）/ ADR-044（轨道模型 + 操作集闭包）。
> 分工：本文 = 契约 + 渲染链架构 + 函数地图 + 概念命名。编辑器交互形态与 L2/L3 分工线归 VIDEO_EDITOR.md；竞品渲染技术调研归 `research/RENDERING_TECH.md`（原始素材层）。

## 1. 一条链

```
生成/编辑（写）                                          渲染（读）
──────────────                                          ──────────
select_clips → build_clip_spec ─┐
chat ops / editor 手势 ─────────┤  一切写经 operations/service.py
                                ▼
                    outputs.render_spec（JSONB，锚定真相——段 id/锚/枚举）
                                │  render_status PENDING（worker 认领谓词）
                                │  claim 时铸 render_claim_token，终态写按 token 围栏
                                ▼
                    pipeline/rendering.py 烘焙缝（URL fold 唯一发生地）
                      resolve_spec_urls：按注册表 url_fields 把相对键
                      烘成绝对 URL（新轨注册即自动接管，零逐字段特判）
                                ▼  POST /render {spec, outputs:{put_url}}
                    apps/render（Node 黑盒：spec → MP4+SRT）
                      stage 落盘 → bundle → renderMedia → loudnorm
                      泳道投影在 <Clip> 内求值（types.ts 单一家）——
                      锚 → 输出时间窗，编译产物，永不落库
                                ▼  预签名 PUT 直传对象存储
                    outputs.files（带时间戳键，旧对象删除）

预览面：apps/web 编辑器 <Player> 与渲染服务共用同一个 <Clip> 组件（packages/clip）——
preview == 成片 是结构性的，不是测试出来的。
```

两条铁律（ADR-016）：**spec 只描述"是什么"，零 Remotion/React 概念**（渲染器可换，§7）；**渲染器是黑盒**——不读 DB、不吃相对 URL、不知项目/人设，一切在烘焙缝解析完毕。

**video-spec（ADR-145）**：`family="video"`，CompositionVersion 的编译产物。顶层 = `fps`（有理数 `{num,den}`）+ `width/height/background/sample_rate` + `duration_frames` + `tracks[]` + `provenance`（composition_id / composition_version_id / content_digest，身份事实非权限）。一切时间已量化成整数帧（量化唯一座 = `app/editing/timing.py`，渲染器永不重 round）；Track = `kind(visual|audio)/role/order` + clips，视觉 order 定叠放；Clip = `{start_frame, end_frame}` 输出窗 + 可选 `source`（`url` 烘焙缝绝对化；audio/video 带源窗 `start_frame/end_frame`，1× 律锁等长；静态图片/web 无源窗）+ object（text/image/web/video/audio/shape；Generator 在编译前已解析为固定 video/image）+ clip-local 帧关键帧动画（linear/hold/cubic_bezier，求值唯一座 = `packages/video-spec` animation.ts）。VideoObject 画面与原声共享源窗，layout/fit/transform/opacity/gain/muted 编译进 spec；schema = `packages/video-spec`（zod，零 React/Remotion，核心契约测试 = `apps/api/test/core/test_video_spec.py`）；adapter = `apps/render/src/video/`（capabilities 声明，不支持即失败——当前分数 fps 明确拒绝）；无字幕 sidecar（字幕烧录进画面）。probe 闸读 spec 自带 width/height/duration_frames/有理 fps，任一 audio clip 或未静音 VideoObject → 容器必须带音频流。当前 optional transitions[] 支持 crossfade：编译固定 from/to Clip、start/end/cut_frame 及真实 source handles，adapter 按固定窗叠化，并对 VideoObject 内原声交叉淡化；同轨原始 Clip 仍相邻，扩展窗只属执行 spec。首个消费者限全画幅 cover、不透明且无外部视觉 transform/opacity 动画的 image/web/video；独立关联 AudioClip 转场、其他转场与分数 fps 渲染仍未支持。当前制作政策帽为 3600 帧（默认 30fps 即 120 秒）：Chat 完整作品提交与 video-spec 编译使用同一 `VIDEO_MAX_FRAMES` 前置拒绝，渲染服务保留最终边界；它不是 Composition 的永久 schema 限制。

**Speech 当前边界**：SpeechObject 永不进入 video-spec；源对齐路径消费已保存的 NarrationAlignment，固定切割旁白模板仍可固定实际音频、解码时长与逐句时间。编译只展开实际使用的普通 audio Clip、真实句级 TextClip/CaptionDerivation 和词锚整数关键帧，手改后的独立字幕保持原 Clip；音频与 cue 均不得越过已审阅固定窗口。renderer 不调用模型、不理解 Speech/alignment，也不重新对齐字幕；alignment/provider/model 只留在 Composition 源事实与上游工具座位。

**原生文字与代表 Preset**：TextStyle 以结构化 `stroke {color,width}` 与 `shadow {color,offset,blur}` 表达描边和阴影，不接受任意 CSS；weight 开放 400/500/600/700/800/900。新 font-set digest `85571c8f24f75610320baf3cec0302ba4766b15cea9efc9782b38ecc2b96511c` 将 900 固定到 OFL 许可的 Noto Sans SC Black（`NotoSansSC-Black.otf`，SHA-256 `2267c4a0312d267dff8c0d1609948f7d949a3da8be3e126f5e2690cb9cc883b4`）；旧 font-set digest `11c92f6b5efd1a6b91ed87e04d82ddbf961fd40a6d5d6be2e36d33b2e0d272b3` 保留原映射，不因新增字形而改变历史版本。`text.color` / `text.stroke_color` / `text.weight` / `text.stroke_width` 是普通离散 hold 动画；颜色、字重不做连续插值，共享 evaluator 对非法字符串插值明确失败。共享 TS evaluator 与 `packages/video-remotion` 的同一 Remotion composition 供 renderer 和 Chat PreviewAdapter 使用，pinned FontFace 与 TextPart paint 求值一致，900 不依赖合成粗体。Chat 预览经 `tools/video/preview.py` 只读编译精确版本的显式局部 Scrub：未授权 Speech、生成图片和仍需执行事实的派生字幕显式标记 `pending_media`，不触发制作；`faster-whisper-script-v1` source-aligned 字幕沿用版本内固定文字直接编译。只有本次实际声明的局部 Scrub 参与 ACK 就绪等待，默认 Storyboard 不等待 Player；固定 Generator 媒体缺失、局部 schema/能力/provenance/scope 失配或播放错误不能 ACK 该次带预览的呈现。局部 Player 等待 pinned FontFace 与首帧 img/audio/video 实际就绪，不用计时器代替，也不让旧版本的 settled 状态泄漏到原位新版本。制作前完整 video-spec 永不交给浏览器。Player 座位集中在 `apps/web/src/components/chat/video/preview/`，按 spec 宽高比响应式缩放；`video-spec` 仍零 React/Remotion。

当前 Preset 注册表恰好十六项：`caption-phrases` / `text-reveal` / `text-impact` / `typewriter` / `keyword-fill` / `word-cycle` / `claim-layout` / `highlight-sweep` / `path-underline` / `callout` / `flow-steps` / `comparison-columns` / `card-stack` / `list-reveal` / `notification-stack` / `title-lockup`。`editing.presets.expand_preset` 在 CompositionVersion 保存前把它们确定性展开成普通 Tracks/Clips/Objects/Animations：caption 短语保留精确文本范围，词锚在上游解算为 TextPart 与整数 ticks，组合图形使用普通分轨 Text/Shape/Image/Web/Video Clips，卡片 overshoot 由有界关键帧表达。Preset id、NarrationAlignment/provider/model、React/Remotion 均不进入 video-spec；后续修订仍只经 `revise_video` → `apply_composition_edits`，文字与样式变化通过完整所属 Text Clip 提交，可更新或显式清除 stroke/shadow，选 900 时只升级当前 TextObject 的字体集引用。字体编译同时收集静态样式与 `text.weight` 动画引用的字重，避免动画-only 900 漏发 Black 资源。

`path.reveal` 只接受带非空 path 数据的 ShapeObject，关键帧必须是 0..1 数值，禁止 TextPart 与 NarrationAnchor 目标；无动画时静态 path 完整显示。Python/TS 在 schema/capability 两层拒绝非法目标与值域，共享 evaluator 负责普通整数帧插值；当前 Remotion adapter 用 SVG `pathLength=1` + `strokeDasharray=1` + `strokeDashoffset=1-reveal` 绘制，path 字符串始终只是几何，不变成 renderer 代码。连续看片、独立试听与完整四类产品验收仍归后续阶段。

**Generator 当前边界（draw-2d / remotion-project / image-generation 已接）**：创作层的 draw-2d 在上游受限 Node 进程中执行 Agent 的 `render(ctx)`，经 Pillow/PyAV 固定 MP4/PNG；`program_director` 与 `aligned_narration_director` 共同展开 `prompts/_draw_2d_contract.j2`，ctx、四类命令字段与值域对齐 `tools/video/programs.py` / `program_runner.mjs`，未声明字段由严格校验拒绝。remotion-project 只允许在分离的上游 `/component-bake` 入口执行受控多文件 TSX；API 开关与 render `/health` 报告的活跃隔离必须同时成立，当前隔离实现为 macOS Seatbelt。自由 component 设计可在一个普通 Composition 中顺序组织 1–6 个 Generator Scene；源对齐 MG 仍在同一次 `design_video(narration_alignment_id, mode=motion_graphics)` 中声明至多一个 draw-2d 或 remotion-project 主视觉。两类程序输出都使用完整 Composition 画布和 30fps；源对齐 Scene 的真实 ticks 只向下量化 Generator 窗口，不移动旁白、字幕或 Scene。image-generation 只在授权 produce Run 内请求 MiniMax image-01，校验后固定为不可变图片。编译按来源与执行 manifest 取已准备媒体：程序画面在 video-spec 中是普通 muted video，生成图片是无源窗的普通静态 image；renderer 与 adapter 不执行程序或模型请求，也不知道 TSX、prompt、provider 或 model。来源、预览、缓存、局部修码、明确重生成和 resume 复用合同归 [VIDEO_PROJECT §4.3.2/§8.1.1](VIDEO_PROJECT.md#432-generatorobject可再次生产的画面draw-2d--remotion-project--image-generation-已接)。ShapeObject 以 renderer-neutral 几何进入 spec，由当前 Remotion adapter 用 SVG 绘制。

## 2. 五个包与一个 API 侧

| 家 | 角色 |
|---|---|
| `packages/clip`（@repurposer/clip） | **单一画笔**：`<Clip>` 组件 + spec TS 镜像 + 字幕样式目录；web `<Player>` 与 render 服务共用——parity 之根（ADR-018） |
| `packages/video-spec`（@repurposer/video-spec，ADR-145） | video-spec 唯一 TS 契约 + 纯量化/插值求值 + golden fixtures；零 React/Remotion——renderer 可换的契约面 |
| `packages/video-remotion`（@repurposer/video-remotion） | video-spec 的共享 Remotion composition 与能力声明；renderer 和 Chat PreviewAdapter 共用，不反向污染纯 spec 包 |
| `apps/render` | Remotion 渲染服务（express + @remotion/bundler + @remotion/renderer + 内置 ffmpeg，pnpm 独立于 uv），`POST /render` 黑盒：渲染到临时目录 → 预签名 PUT 上传，无共享卷；`spec.family` 分派（clip 缺省 / video），video adapter 住 `src/video/` |
| `apps/web` | 编辑器预览（`<Player>` 包 `<Clip>`），手势 → ops HTTP |
| `apps/api/app/pipeline/` | spec 构建（`clip_spec.py`）+ 烘焙与驱动（`rendering.py`）；写纪律在 `apps/api/app/operations/`（与 pipeline 平级）；video 家族的 spec 编译在 `app/editing/video_spec.py`（内容域），pipeline 只做烘焙与驱动 |

## 3. clip-spec 字段级契约

**原则**：renderer-agnostic，只描述"是什么"；样式限预设枚举（CSS ∩ libass 双可表达，保手写 FFmpeg 后路，§7）。

```jsonc
{
  // kind="video": 真人实拍，url 为视频；kind="stills": 图片音频幻灯，
  // url 为可选语音轨（无录音为空串），image_urls 为背景图（0→纯色 / 1→满屏 / N→均分硬切）
  "source": { "asset_id": "uuid", "kind": "video", "url": "/api/v1/files/...mp4", "image_urls": [], "fps": 30, "duration": 120.5,
    "image_shots": [                          // 期 2 节拍方案（stills 可选）：剪辑师规划的分镜，非空时代替 image_urls 均分
      { "image_url": "/api/v1/files/...jpg", "dwell_s": 3.2, "motion": "zoom_in", "motion_rate": 1.1 }
      // dwell_s = 该拍词轴跨度（拍平铺首尾相接，Σdwell = 视频体）；motion: none|zoom_in|zoom_out|pan_left|pan_right，rate ∈ [1.0,1.2]
    ]
  },
  "aspect": "9:16",                         // 9:16 | 1:1 | 16:9 | original（整条材料化跟源画幅）
  "segments": [                              // 主轨。删句 = 标 hidden（非破坏）；输出 = 保留段数组序连接
    {
      "id": "a1b2c3d4e5f6",                 // 段实体身份：锚定寻址的单位；出生即铸，切段时第一保留块继承
      "start": 12.4, "end": 31.0,           // 该段源（asset_id 缺省 = 主源）的时间区间
      "hidden": false,
      "asset_id": null,                     // 异源切片段（切 op）= 带 donor asset_id + url 的段
      "url": null,                          // donor 的存储缝 URL，写时解析，烘焙缝按注册表绝对化
      "provenance": null,                   // "generated" = 合成段（C2PA 段级扫描）；null = real
      "transition": "none"                  // 进场边过渡枚举：none 硬切 | fade 黑场淡入 | dip 白闪（每片 ≤3）
    }
  ],
  "crop": { "x": 0.5, "y": 0.5, "scale": 1.0 }, // 归一化窗口中心 + 缩放；空轨时走 transform 实现，非 object-position
  "crop_track": [                            // 裁切关键帧轨（ADR-045）：稀疏取景决策，源时间轴，t 严格递增
    { "t": 49.56, "x": 0.70, "y": 0.39, "scale": 1.27 } // 一次取景决策一行；相邻帧间固定 ~8 帧 smoothstep（渲染常量，不进契约）
  ],                                          // 空轨/缺省 = 静态 crop 退化形态（语义不变）
  "layers": [                                // 层轨：锚定放置物（当前无写者技能，契约先行）
    {
      "id": "f6e5d4c3b2a1",
      "kind": "broll",                      // broll | text_callout | pip | motion_graphic（渲染按 media.kind 单分支）
      "anchor": { "kind": "segment", "segment_id": "a1b2c3d4e5f6", "offset_seconds": 1.0 },
      //           段锚 ↑（段 id + 源偏移）| 边锚 {kind:"edge", edge:"head|tail", offset_seconds} | 比例锚 {kind:"ratio", ratio}
      "duration_seconds": 3.0,              // 位置 = 锚 + 时长；输出时间窗 = 烘焙期投影，永不落库
      "rect": { "x": 0.08, "y": 0.3, "w": 0.4, "h": 0.3 }, // 归一化矩形（CSS ∩ libass 可表达）
      "z": 0,
      "source_ref": null,                   // LLM 提案的实体引用回放（永不带绝对时间码）
      "media": { "kind": "video", "url": "…" },  // video|image → url；text → text
      "provenance": "real"                  // 必填——每条层项自带 ADR-026 分类
    }
  ],
  "caption_track": [                         // ASR 词级时间戳；用户可改字
    { "start": 12.4, "end": 12.9, "text": "So", "lang": "en", "emphasis": false }
    // emphasis（期 2，缺省 false）：该行覆盖到 caption_pop 拍 → 字幕以 pop-in 进场（覆盖预设 entrance）
  ],
  "translation_track": [                     // 双语对照轨：单元级译文 cue（无逐字 karaoke 时轴），与 caption_track 原文行按时间重叠配对；空 = 单语。渲染 = 译文主行 + 原文小行在下（stack 布局只画原文轨）
    { "start": 12.4, "end": 16.8, "text": "Donc une entreprise d'Oxford…", "lang": "fr" }
  ],
  "caption_style_preset": "clean-bottom",   // 预设枚举，非自由样式
  "caption_position": { "x": 0.5, "y": 0.84 }, // 归一化中心点（拖拽定位）；null → 默认底部
  "title": { "text": "The hook", "enabled": true, "size": 56, "position": { "x": 0.5, "y": 0.12 } },
  "music": { "music_id": "uuid", "url": "https://<bucket>/music/<music_id>.mp3", "enabled": true, "gain_db": -18 },
  "dub": { "url": "/api/v1/outputs/.../dub_fr.mp3", "enabled": false, "gain_db": 0 }, // 声纹克隆配音；enabled 时原声静音
  // brand 块由 API 在生成时从人设皮肤块（persona.brand）烘焙；渲染器不读 DB
  "brand": {
    "caption_color": "#22c55e",
    "caption_size": 56,
    "caption_font": "lilita",                 // lilita | inter | playfair | source-serif
    "intro": { "kind": "text", "text": "From the keynote", "duration_seconds": 2 },
    "outro": { "kind": "video", "media_url": "/api/v1/files/.../outro.mp4" },
    "fill_mode": "fill"                       // fill (cover) | fit (contain)
  },
  "brand_ref": "persona_uuid",                // 血统：哪个人设的皮肤
  "target_language": "en"
}
```

- **轨道分区**：spec 顶层字段被 TRACK_REGISTRY（§8.3）整划——每个字段恰好归属一条轨，双端启动自检强制（忘登记 = 拒绝启动）；**无 `tracks: {}` 容器**（ADR-044 D9：平铺字段 + 注册表声明，收益证伪而非兼容妥协）。
- **非破坏**（Descript 同款）：删句 = 标 `hidden`，不真删，可恢复；恢复语义归快照层（N-16）。层条目同理：锚不可解析（段被删/隐藏）时投影跳过该条、存储不动。
- **异源段**（切 op）：段带 `asset_id` + `url` 即换 donor 源——渲染逐段取 src（`seg.url ?? source.url`），字幕/译文只在主源段上匹配（donor 段时间轴不在主源坐标系）。**"剪两段、尾段后移"不存在**：输出轴派生，插入后尾部自动正确。
- **锚三形态**：段锚 `{segment_id + offset_seconds}`（内容跟随，段删则层投影落空）/ 边锚 `{head|tail + offset}`（intro/outro 本质即边锚块）/ 比例锚 `{ratio}`。**绝对时间永不在静止面出现**——层窗口由 `projectLayers` 求值，夹到视频段内。
- `caption_track` 双驱动：内嵌烧录字幕 + 直接导 SRT（交接 CapCut 的交付物）。
- 样式只走 `caption_style_preset` 枚举目录（`captions.ts` CAPTION_PRESETS），**无自由布局**——preview=成片与 libass 可换性的前提。过渡只走段上 `transition` 枚举（ADR-016 L3 修订：**枚举可、画廊不可**）。
- **Brand 入渲染**：`brand` 块由 API 在**生成时**从 `persona.brand` 合并系统默认皮肤烘焙（ADR-038）；渲染服务/预览只读 spec 不读库。
- **音乐入渲染**：`music.url` 为曲目的公开对象 URL（生成时自 `Music.file_path` 烘焙，ADR-023）；`<Audio>` 循环混音，`gain_db` 控增益。
- **头尾卡**：`brand.intro/outro` 存在时，主视频时间轴前后各插一张卡（`duration_seconds`，null → 2s 默认）；卡 = `{kind: text|image|video, ...}`——text 渲染标题卡样式，image/video 满帧填充、超长截断；视频体 `<Sequence>` 后移，字幕 remap 自动对齐。
- **双源形态**（ADR-020）：`kind="video"` 走 `<OffthreadVideo>`；`kind="stills"` 图片音频幻灯——`image_urls` 为背景视觉（1 满屏 / N 均分硬切 / 0 纯色兜底），`url` 为可选语音轨；有语音复用 ASR 词级 `caption_track`，无语音为定长幻灯（每图 `SECS_PER_IMAGE` 秒，后端写合成段）。背景视觉优先级：**slides PDF 页图（`Asset.slide_pages`）优先**，上传照片其次；源选择优先级 VIDEO→AUDIO→SLIDES/IMAGE。**期 2 节拍方案**（产物质量线）：stills 携带非空 `image_shots` 时以剪辑师规划的分镜代替均分——拍在词轴上平铺（dwell = 词跨），`motion`/`motion_rate` 为 Ken Burns 枚举（编译夹带 1.0–1.20，punch_in 强调降格为 zoom_in ≥1.15）；规划失败/为空回退均分，契约向后兼容。**刻意不做**的其余项不变：多句动效文字轨 / 转场画廊（L2 停线，ADR-020；B-roll 已由层轨承接为契约能力，写者技能随能力批）；PROGRESS 需求池的 motion 枚举（P2）若做，限于 **video 源** crop 动态预设，落地需新 ADR 明确与 stills Ken Burns 的边界（ADR-028 关联）。
- **前垫/尾停**（期 2 talking-head 快赢）：video 源的 `locate_span` 在词界吸附后向**相邻静音**扩张——前垫 0.12s（不过上一词尾）、尾停预算 1.8s（不过下一词头、不过素材真实时长）；垫区无词，字幕轨不受影响。无新契约字段，渲染零改动。
- **文本拖拽定位**：`caption_position` / `title.position` 为归一化中心点（= libass `\pos`，可移植），null → 渲染默认；`title.size` / `caption_size` 是 **1080×1920 竖屏参考系上的参考值**——渲染端按帧高等比缩放（9:16 不变，1:1/16:9 ≈ ×0.56；双语对照译文主行再 ×0.82、原文小行 ×0.55；字幕块宽 84% = 两侧 8% 边距随帧宽自适应）。人设页皮肤分区的预览叠透明层支持拖拽 marker 改位置/字号（无独立盒宽高、无关键帧动画）。
- **声纹克隆配音（dub）**：`POST /outputs/{id}/dub` 用人设声纹经 voice_clone + T2A 把（翻译后的）字幕合成目标语言语音，烘入 `dub` 轨；渲染时 `dub.enabled` ⇒ **原声静音**、播放 dub（无唇形同步，ADR-037）。dub 在注册表声明 `depends: ["main"]`——时间轴 op 落地后 ops 响应带 `stale_tracks`（重配一句话的素材；不产生"合法的谎"）。

## 4. 轨道解剖（注册表实证）

spec 的顶层字段被 TRACK_REGISTRY 整划为 9 轨——下表的 family / timeline 是**文档分类**（非可执行 schema；remap 全库一个函数家，见 §5）：

| 轨 | spec 字段（`fields` 分区） | family / timeline | Clip.tsx 渲染位置 | 写者（owner） |
|---|---|---|---|---|
| `main` 主轨 | `source` + `segments` + `aspect` + `target_language` | sequence / 源时间轴 | `<Series>` 逐段 `<OffthreadVideo>`/`Audio`（stills 走 `<Img>` 均分）；**逐段取 src**（`seg.url ?? source.url`） | select_clips / materialize_source（出生）；remove_filler（形态写者） |
| `caption` 字幕 | `caption_track` + style/position/enabled | data / 源时间轴 | `groupLines` → single/stack 两布局，按 sourceTime 反查 | remove_filler |
| `translation` 对照字幕 | `translation_track` | data / 源时间轴（`pairs: [caption]`） | 译文主行 ×0.82 + 原文小行 ×0.55 | translate_clip |
| `crop` 裁切 | `crop`（静态单值）+ `crop_track`（稀疏关键帧） | data / 源时间轴 | 关键帧在场 = 源窗口显式定位（`sampleCrop` 按 sourceTime 采样，固定 smoothstep）；空轨 = 主轨外层 `transform: scale+translate` 静态路 | 出生默认 + reframe_clip（形态写者） |
| `layers` 层轨 | `layers`（锚定放置物） | layer / derived（锚 → 输出窗投影） | `projectLayers` 求窗 → `LayerView` 按 `media.kind` 单分支（video/image/text），z 经 Sequence style | 暂无（insert_broll 随能力批） |
| `title` 标题 | `title` | block / 输出时间轴（片头区淡入；stack 布局 ~3s 自动退场） | 绝对定位 div | 出生 |
| `music` 音乐 | `music` | block / 输出时间轴，循环铺满 | `<Audio loop>` | add_music |
| `dub` 配音 | `dub`（`depends: [main]`） | block / 输出时间轴整段（生成时已按 cue 拼接对齐）；enabled ⇒ 原声静音 | `<Sequence from=introFrames>` 内 `<Audio>` | dub_clip |
| `intro_outro` 头尾卡 | `brand` + `brand_ref` | block / 输出时间轴两端（边锚语义） | 独立 `<Sequence>` + `IntroOutroCardView` | 人设皮肤烘焙 |

时间轴换算的家：`types.ts` 的 `videoTimeline`（保留段 → 视频段内输出时刻累加）/ `sourceTimeAtOutputTime` / `outputTimeAtSourceTime` / `projectLayers`——**字幕按源时间存、按输出时间显示**，双向换算只在这家；Python 孪生在 `clip_spec.py`（同名 snake_case，dict 版吃 JSONB），双端逐值 parity。dub 反例：segments 映射发生在 dub 文件**生成时**（skills/dub/procedure.py 按 cue 起点拼接），spec 层它是输出时间轴整段文件——所以它 `depends: [main]`，时间轴 op 落地即失步（ops 响应 `stale_tracks` 告知）。

## 5. 重要函数地图

### packages/clip（TS，双端共用）

- `types.ts`
  - `keptSegments` / `videoDurationSeconds` / `introSeconds` / `outroSeconds` / `totalDurationSeconds` — 输出时长推导链（intro + kept + outro）。
  - **泳道投影单一家（存法 C）**：`videoTimeline`（保留段 → 视频段内输出时钟）/ `sourceTimeAtOutputTime` / `outputTimeAtSourceTime`（双向 remap；过渡面纱不吃时间轴）/ `projectLayers`（锚三形态 → 输出窗，夹视频段内；不可解析锚进 `unresolved`，存储不动）。
  - `removeRange(spec, start, end)` — 非破坏删段：相交部分切出 `hidden` 段（可恢复），区间内 caption cue 真删（N-16：恢复语义归快照层）。**段 id 规则**：第一保留块继承父 id（锚骑幸存内容），隐藏块与后续块铸新（`mintSegmentId`）；**过渡边规则**：仍以 s.start 起点的块继承入边过渡，切出的块硬切。**Python 同名镜像**（NAMING §1）。
  - `setTrim(spec, start, end)` — 移动首/末保留段边界（id/过渡随段走）。`trimBounds` / `sourceDuration` 为滑杆供数。
  - `ASPECT_DIMENSIONS`（9:16/1:1/16:9；original 由渲染端 calculateMetadata 解析源尺寸）/ `COMPOSITION_FPS=30`（合成 fps，与源 fps 无关）。
- `tracks.ts` — **轨道分区（TS 端）**：`TRACK_FIELDS` = 9 轨 × spec 顶层字段 + `TrackId` + 类型级分区断言（ClipSpec 键必须全登记，tsc 强制）。本端只声明分区——可执行目录在 Python（运行时唯一消费端）。
- `Clip.tsx` — 唯一渲染组件。泳道投影消费 `types.ts` 单一家；`LayerView`（层渲染件，按 `media.kind` 单分支）；`TransitionVeil`（入边过渡单侧面纱：fade 12f 黑场 / dip 8f 白闪，媒体之上、层与文字之下）；`groupLines`（7 词一行）；`lineRevealFrame`（行级入场帧 = `outputTimeAtSourceTime`）；`captionEntrance`（entrance 原语 → opacity/transform，每值过 libass 映射闸；**期 2**：行内任一 cue `emphasis` 则以 pop-in 覆盖预设 entrance，single/stack 两调用点同规则）；stack 布局（锚点上下半场决定容器生长方向，滑窗 `maxLines`）；双语对照配对（闸在主源段——异源段不匹配主源字幕）；`pointStyle`（归一化中心点 → CSS translate，= libass `\pos`）；尺寸按画面推导（`size × height/1920` 参考系）。**期 2 分镜**：`shotFrames`（dwell → 帧数，末拍吸收余数——splitFrames 同款纪律）、`StillShot`（Ken Burns 原语：zoom 1↔rate out-cubic；pan 带底缩放、行程按 `(rate−1)/rate·48%` 安全界——translate 先于 scale 生效，超界露边）；`image_shots` 非空时代替均分（空 = legacy 路径，向后兼容）。
- `captions.ts` — `CAPTION_PRESETS` **字幕样式目录**（注册表先例）：样式 = 三原语（`layout` × `entrance` × `wordHighlight`）组合；**加样式 = 一行登记**（TS 类型由此推导，Python 只校验成员）；**加原语 = 过 libass 映射闸 + Clip.tsx 一分支**（CSS ∩ libass 子集纪律）。
- `fonts.ts` — `fontFamilyFor`（品牌字体枚举 → 字体族栈）。品牌字体只载 latin 子集，CJK 码位逐字落栈回退（`CJK_FALLBACK_STACK`）：容器内字形 = vendored Noto Sans SC（SIL OFL，`apps/api/assets/fonts/`，render Dockerfile 注册进 fontconfig——slim 镜像无它则中文全部烘焙成豆腐块）；dev 机回退 PingFang SC / 微软雅黑。标题层同款栈（sans 设计意图不变）。
- `Root.tsx` — `calculateMetadata`：aspect → 画幅尺寸（original 探源）、`totalDurationSeconds` → 合成时长；`DEFAULT_SPEC` 兜底。

### apps/render（Node 黑盒）

- `server.ts` — `POST /render`：校验 → `artifacts.ts` 复用或生成成片（`upload_only=true` 时只读 ready 缓存，绝不生成）→ `upload.ts` 预签名 PUT 上传 → 返回对象键。`/cache` 静态服务把本地落盘的源经 loopback 喂回 Remotion（CORS `*` 因 bundle-server 跨源 fetch）。
- `render.ts`
  - `renderClip(spec, outDir, basename, preview?)` — 主流程：`stageRemoteSource`（源先落盘）→ 共享 bundle（一次构建复用）→ `selectComposition` → `renderMedia`（h264）→ SRT → `normalizeLoudness`。`preview` 在时提前返回（`srtPath: null`，两个后置 pass 全跳）。
  - `normalizeLoudness` — EBU R128 双 pass 响度归一（`-16 LUFS / TP -1.5`），ffmpeg 二进制取自 Remotion compositor 包（`resolveFfBinary`）；**增强不是正确性**——失败保留原音，永不翻车渲染；无声产物（stills 幻灯）跳过。
  - `stageRemoteSource`（stage.ts）— Remotion 内部 asset fetch 不走系统代理、整文件下载挤在取帧预算内（慢源 = delayRender 超时灾难）；staging 侧代理感知（`dispatcherFor` 读 HTTPS_PROXY）、按 URL 去重、LRU 驱逐。**异源段**：段的 donor url 同样经 staging（渲染器不知同质/异源之别）。
- `srt.ts` — `captionTrackToSrt`：7 词成行、按 `clipStart`（首个保留段起点）重定基——SRT 与 MP4 同起点，交接 CapCut 的交付物。

- **上传与恢复**：源下载的响应头/空闲等待为 300 秒；上传的响应头、空闲等待与单次尝试上限均为 600 秒，每个文件最多尝试 4 次，共享 720 秒总预算（包含退避）。连接重置/断管/临时网络错误/超时及 HTTP 5xx/408/429 可重试；每次重建连接池，指数退避带抖动并遵守 `Retry-After`，等待超出剩余预算则结束。鉴权、证书及未知错误不盲重试；错误日志不含预签名 URL。API 请求默认上限 1800 秒，上传签名至少有效 3600 秒。生成、上传与恢复错误分别返回 `stage=render|upload|recovery`；上传失败提示已生成但未交付，缓存失效只要求重新渲染，不伪装成重传。断连恢复、重试上限、退避/预算与缓存复用已有本地回归；新增 upload-only 旅程与真实代理链路重传仍待验证。
- **成片缓存**：`artifacts.ts` 按 output ID + 规范化 spec + 渲染器缓存版本区分，完整文件生成后原子写 ready marker；上传失败或进程重启后，同配置使用新上传签名重传。修改 spec 重新渲染；缓存保留 24 小时并在请求时清理过期目录。普通渲染请求 miss 时重新生成；chat `retry_upload` 发往独立 `/upload` 端点的 `upload_only` 请求 miss 时返回 409 / `ARTIFACT_CACHE_MISS`，绝不现场重渲染。升级渲染语义须更新缓存版本。clip 与 video 共用恢复机制，`POST /outputs/{id}/render` 的普通重试与 chat 的只重传恢复均可使用，在途重复请求不撤销 claim。
- **代理**：`dev.sh` 按显式 `RENDER_PROXY` → 已导出 HTTP(S) 代理 → macOS 系统 HTTPS 代理 → 本地 6152 默认值选择；`RENDER_PROXY=off` 明确关闭。探测失败保留配置并提示，不自动回退直连；选择结果写 render 日志。
- **交付终态**：render/upload 子步骤失败也使 run FAILED；部分交付只计算实际可用产物。clip/video 须 `render_status=COMPLETED` 且 `files.video` 存在才算已交付；完整性 probe 仍为成功落库前置条件。

### apps/api/app/pipeline（Python 侧）

- `tracks.py` — **TRACK_REGISTRY 可执行目录（唯一运行时端）** + fold 助手：`resolve_spec_urls`（烘焙缝，walker 支持路径中段 `[*]`）/ `spec_provenance`（轨级 + 段/层项级 generated 扫描）/ `track_of_field` / `skill_written_tracks` / `stale_tracks`（派生轨失效声明）/ `assert_single_writer_per_track`（一轨一写者，create_run 编译期 422）+ 两条启动自检（分区对账 + phantom track fixture，挂 `orchestrator.assert_runners_registered`）。
- `clip_spec.py`
  - `build_clip_spec(source, segment, …)` — spec 唯一构建处（段 id 出生即铸）。video / stills 两分支（stills：有声 → 词级字幕 + 语音轨；无声 → `SECS_PER_IMAGE` 定长幻灯 + 合成段）。`beat_plan=`（期 2，stills only）：`_compile_image_shots` 把解析后的拍编译为 `source.image_shots`（dwell = 词跨，rate 夹 1.0–1.20，punch_in→zoom_in ≥1.15），`caption_pop` 拍覆盖到的字幕 cue 标 `emphasis`。
  - `locate_span(words, segment, *, pre_pad_s, post_pad_s, source_end_s)` — 选段定位：agent 数值时间戳优先（**向最近词边界吸附**），否则 start/end marker 文本匹配（渐短探针容忍 LLM 改写），**永不 raise**，兜底全段。垫（期 2）：词界吸附后只向相邻静音扩张——前垫不过上一词尾、尾停不过下一词头与 `source_end_s`（`_pad_span` 单一出口）。
  - `remove_range` / `set_trim` — TS 函数的 Python 镜像（同名同义；id 继承/过渡边规则双端一致）。
  - 泳道投影 Python 孪生（dict 版）：`intro_seconds` / `outro_seconds` / `video_duration_seconds` / `video_timeline` / `source_time_at_output_time` / `output_time_at_source_time` / `project_layer_windows`。
  - `total_output_seconds` — 计价时长 = kept video + 头尾卡秒（坐上面的共享算术）。**已知边界**：时长贡献不随注册表自动收养——未来带时长的轨在此扩展算术（与其渲染件同批）。
- `rendering.py`
  - `render_output(output_id)` — 驱动主流程：读 spec → 烘焙缝 → 预签名 PUT URL → POST 渲染服务 → 写 `files` + COMPLETED。恢复请求从当前 render step 读取一次性 `upload_only` envelope 标记；普通请求不携带该键，spec 两家族均不混入此运行概念。**竞态守卫**：三处终态写都以 `render_claim_token=:mine` 做身份谓词并检查 rowcount；claim 铸 token，re-pend/reap/resume 失势时置 NULL。渲染中途 morph 重排后，旧执行写不动，删孤键、镜像 superseded，永不覆盖新 spec；`render_status==RENDERING` 只是状态，不得代替执行身份。
  - `resolve_upload_retry` / `upload_finished_output` — chat 上传工具的目标解算与写口：只接受结构化 `failure.stage=upload` 的 failed render；@output pin 优先，未指认时取最近失败 run 的唯一候选。独立短事务以 Output token 认领并调用 `/upload`，只更新上传结果；不重开原 run/render step，不进入 worker 队列，不新增付费制作。缓存 miss 禁止重新渲染，多候选要求明确目标，在途/已交付不重复上传。
  - `_absolutize(spec)` — **烘焙缝 = 注册表 fold**：`resolve_spec_urls` 按各轨声明的 `url_fields` 绝对化（source.url / image_urls / image_shots[*].image_url / segments[*].url / brand 卡 / music / dub / layers[*].media.url）——新轨注册即接管，无逐字段特判。
  - `_mirror_render_node` — 渲染生命周期镜像到 run 的 render 步骤（可见性 + 成本的家；run-less 重渲染路径不受影响）；终态移除一次性 `upload_only`，成功保留上传完成或渲染完成的真实摘要，失败保留结构化 `failure.stage`。
- `app/operations/registry.py`（与 pipeline 平级） — op 注册表（ADR-032 + ADR-044）：`OpDef.writes` 声明写入字段（启动对账分区）；`llm_visible=False` 的六 op（reorder_segments / insert_segment / set_transition / add_layer / remove_layer / move_layer = 操作集闭包登记，LLM 词汇随技能批开放）——客户端可调、不进 chat 词表；载荷 = 实体引用（段 id / 锚 / 枚举 / 拍序号），寻址 =（轨, item_id, op）三元校验。ops 路由响应带 `stale_tracks`。
- 认领谓词：`outputs.render_status`（NULL = 未请求 / PENDING 可认领），worker `FOR UPDATE SKIP LOCKED`（ADR-017）；认领原子铸 `render_claim_token`，后续终态写只认该 token（ADR-079）。

### 写纪律（Operation Model 联动）

`render_spec` 的一切修改经 `operations/service.py`（ADR-032）：op 注册表校验 → 应用 → 快照落 `spec_after`；undo/redo/版本跳转对全部 op 统一成立；`base_hash` 乐观锁 409。editor 与 chat 是同一能力层的两个薄适配器（ADR-033）。

## 6. 现状不变量（任何演进不得破坏）

1. **单一画笔**：preview 与成片同一 `<Clip>`——新增渲染行为只准进 packages/clip。
2. **契约无渲染器概念**：spec 只描"是什么"；样式走枚举目录，每个原语过 CSS ∩ libass 闸。
3. **渲染器不读库**：一切外部引用在烘焙缝解析为绝对 URL；spec 自足。
4. **写必经 operations**：快照 undo 与漂移自愈（hash 链校验失败补 `set_spec`）。
5. **轨道分区强制**：spec 顶层字段 ⊆ TRACK_REGISTRY 且恰好一轨（双端启动自检）；新轨 = 一条登记 + 一个渲染件，**禁止 `tracks: {}` 容器**（ADR-044 D9）。
6. **锚是真相，泳道是编译产物**（存法 C）：位置永不落库（段锚/边锚/比例锚三形态），输出时间窗只由 `projectLayers`/`videoTimeline` 求值——泳道永不编辑、永不落库、永不进快照；锚与绝对坐标不得在同一行数据平级共存（双真相禁令）。
7. **op 载荷 = 实体引用**：段 id / 锚 / 枚举；LLM 永不提议绝对时间码，寻址经（轨, item_id, op）注册表校验。
8. **一轨一写者**：同一 run 内一条轨至多一个非 fork 形态写者（出生/派生豁免），撞轨 = 编译期 422，不做运行时合并。
9. **时间轴分道**：`*_track` 字段 = 源时间轴（经 segments 映射）；块字段 = 输出时间轴（dub/音乐/头尾卡）；层轨 = 锚定派生。派生轨在注册表声明 `depends`，时间轴 op 落地经 `stale_tracks` 告知。
10. **尺寸按画面推导**：字号是 1080×1920 参考系上的参考值，按帧高缩放；字幕块宽 84% 随帧宽自适应。
11. **网页状态仍是 WebObject**：CapturePlan 的 populated/full/cutout/blank_plate/hero 制品冻结为同一 web SourceSnapshot 下的独立 `view_id`；普通网页层仍由 `WebObject + view_id` 引用。受控 Generator 的显式派生 image Snapshot 资源由上游准备层校验 owner、原 web/view 与精确 digest，不能直接将 web 清单当 image 使用。共享相机的 RGBA cutout 按配对目标盒无缩放补齐透明全画布，保存原裁切与配对 digest；renderer 只消费固定 Generator 视频与独立原生文字，不拼采集坐标。selected 特写使用冻结元素盒与既有相机数学，before/after 使用普通 centered crossfade，原生 plate/cutout 使用普通 opacity/transform 动画；video-spec 不新增网页状态或 renderer 字段。
12. **Remotion 许可门覆盖最终 Renderer 与上游 runner**：当前锁定 `remotion` / `@remotion/bundler` / `@remotion/renderer` 4.0.484。依[当前许可](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)与[条款](https://www.remotion.dev/docs/terms)，个人、非营利组织及不超过 3 人的营利组织可免费商业创作；4 人及以上营利组织需要 Company License，程序化 render API / Remotion Player 属 Automators 范围。平台生成并渲染自己的模板或 AI 生成 Remotion 代码属于允许形态，终端用户自带 Remotion 工程上传渲染需要 Remotion 另行书面许可；本产品的 Agent 受控 Generator 不等于开放用户上传代码。商业上线前必须由运营主体按真实总人数与调用形态配置适用许可，不能以“未填 license key”推断免费或许可证已覆盖。

## 7. 渲染器替换路径（spec 不变）

| 触发 | 换成 | 成本 |
|:---|:---|:---|
| Remotion 成本 / 规模问题 | **手写 Python+FFmpeg+libass**：clip-spec→FFmpeg filtergraph 一遍出；字幕用 `.ass`，预览侧用 **libass.wasm（JavascriptSubtitlesOctopus）** 渲染同一份 .ass → 两端共享 libass 保 parity | 渲染逻辑自写；.ass 动画有天花板（我们碰不到） |
| 要"视频不出浏览器" + 降本 | **客户端 `@remotion/web-renderer`（WebCodecs)**：我们的合成落在其 CSS 子集内，现实可换 | alpha 阶段；GDPR 收益有限（ASR 仍在服务端）；可能仍需服务端代理 |

> GDPR 主线仍是**服务端全栈 + EU 区部署**；客户端渲染只是降本备选，不是合规答案。

## 8. 轨道模型（现行契约，ADR-044）

> 轨道模型的覆盖：注册表 + 双端自检 + segments widen + 锚/层/过渡契约 + 泳道投影 + 六 op 闭包（过渡封顶覆盖 insert_segment；段/层 id 契约级唯一；双端各守所执）。判据 = **操作集闭包**：registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改（操作走查契约见本文件附录 §8）。弹性验收机械化：spec 顶层字段 ⊆ 轨道注册表（启动自检对账，⊆ 同款代数）+ phantom track 自检（注册一条假轨，烘焙缝/寻址/合规自动接管，消费方零改动；计价不在其列——时长算术坐 `clip_spec.total_output_seconds`，时长贡献轨到来时自带扩展）。

### 8.1 形态：锚定 = 存储格式，泳道 = 编译产物（存法 C）

```
静止面（ops/spec 落库）            渲染面（<Clip> 内一次求值，用完即弃）
─────────────────────              ──────────────────────────────
segments（段 id + 源时刻）  ──求导──►  lane 铺平：输出时间窗 + z 序
layers[{anchor, …}]                  （types.ts 单一家 / clip_spec.py 孪生）
transition（挂段进场边）
▲ ops 只动这里；undo 快照存这里      ▲ 永不编辑、永不落库、永不进快照
```

- 位置**不落库**：层条目挂语义锚，输出时间窗由求导派生——"剪两段、尾段后移"这类 ripple 手势在声明式模型里不存在（插入一段，尾部自动正确）。
- 锚三形态：**段锚**（`{segment_id + 源偏移}`，内容跟随；段删/隐藏则投影落空、存储不动）/ **边锚**（`{head|tail + 偏移}`；intro/outro 本质即边锚块）/ **比例锚**（`{ratio}`）。绝对时间永不在静止面出现。
- 双真相禁令：锚与泳道**不得平级共存在同一行数据**（双写必分歧）；泳道只是编译产物，永不可写。

### 8.2 词汇表（命名宪法 §2 登记，N-38）

| 中文 | 英文 | 定义 | 不是什么 |
|---|---|---|---|
| 轨道 | `track` | spec 命名分区 = 注册表一条声明；**裸用违规，必须带家族限定**（N-38，N-11 同款判例） | 不是 NLE 自由轨；用户永不见 |
| 主轨 | main track | `source` + `segments`，输出 = 数组序连接；唯一持剪辑语义（hidden/trim/reorder） | — |
| 段 | `segment` | 主轨一行：`{id, asset_id?, url?, start, end, hidden, provenance?, transition}`；异源插入 = 带 asset_id 的段 | — |
| 数据轨 | data track（`*_track`） | 源时间轴时序数据：caption / translation / crop（关键帧采样器 = `sampleCrop` 双端逐值 parity） | 不参与叠放 |
| 层 | `layer`（字段 `layers`） | 锚定放置物列表：kind 枚举（`broll` / `text_callout` / `pip` / `motion_graphic`），z 序渲染，条目可带 `source_ref` 回放（PiP）与 `provenance`（ADR-026 必填） | 不是自由轨；不撞 UI 浮层（overlay 一词归 overlay-surface 浮层族——"overlay" 只剩样式义，避让 N-27 同型撞车） |
| 锚 | `anchor` | 层条目的语义挂接；输出时间派生不落库 | 不是时间码 |
| 过渡 | `transition` | 段的进场边效果枚举（none/fade/dip），挂在段上随换序走 | 不是转场画廊（≤3 枚举封顶） |
| 块轨 | block track | 单值轨，输出时间轴：music / dub / title / 头尾卡 | dub⇄原声互斥在注册表声明 |

### 8.3 轨道注册表（TRACK_REGISTRY）

每条轨一份声明，**双端各守所执**：`app/pipeline/tracks.py` = 可执行目录（唯一运行时端，fold 助手消费），`packages/clip/src/tracks.ts` = 仅 `fields` 分区（类型级断言强制登记）——分区在两端各自独立 pinning（Python 启动对账 + TS 类型断言），无镜像漂移面。消费方全部 fold 注册表（不再逐字段特判）：

```python
TrackDef(
    owner,         # 写者技能（出生写者豁免撞轨判；一轨至多一个非 fork 形态写者，撞轨 = 编译期 422）
    pairs,         # 声明耦合（translation ⇄ caption）
    provenance,    # C2PA 分类器 fold（ADR-026；段/层项级 generated 另有扫描）
    url_fields,    # 烘焙缝 fold（resolve_spec_urls；路径中段 [*] 展开列表）
    fields,        # 该轨持有的 spec 顶层字段（分区；启动自检强制完整且不交叠）
    depends,       # 派生轨依赖声明（dub ⟵ main；时间轴 op → stale_tracks 告知）
)
```

family / timeline 分类是文档（§4 表），不进 schema；确定性工艺检查（crop 不出人脸框 / 驻留达标 / 字幕不溢出）随首个住户与其消费方同批回归，禁先注册空座位。

**加一条轨的成本** = TS 分区一项（tsc 强制）+ Python TrackDef 一条（启动对账强制）+ 一个渲染件（新 family 才有）。`crop_track` 是第一条按此成本进场的轨（reframe 能力批，ADR-045）。

视频创作经 Chat 的工作草稿逐步形成并保存 CompositionVersion；首稿完整呈现并等待后续制作用语。制作钉 exact version_ref，worker 不重设计；制作前动态检查只经局部 Scene/Clip/Object Scrub 复用 PreviewAdapter，完整成片预览永不提供，正式渲染与交付后的 Output 播放只消费固定 video-spec。对话行为归 CHAT_ARCHITECTURE 与 VIDEO_PROJECT。

## 9. 共享渲染所有权与验收

编译期为output指定唯一render owner，其inputs静态包含全部写入者；非owner不re-pend/建render step，失败阻断owner，不能交付部分spec。in-place Clip morph持有output行锁，用jsonb_set按TRACK_REGISTRY局部写，合并后完整ClipSpec校验；不同track不丢更新，同track显式冲突/串行。归档不re-pend，跨run在飞render不双重拥有；claim-token fencing、屏障、上传/probe/真实文件与版本门继续保留，reconcile不是正常路径替代。交错/取消/恢复/失败注入验收归 VERIFICATION §5.1。

旧 Film 专用实现与其测试已删除；这不构成新链验收。新视频及未完成视听要求归 VIDEO_PROJECT 与当前施工合同。
