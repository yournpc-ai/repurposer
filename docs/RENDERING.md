# Rendering — 渲染链架构（clip-spec 契约 · 烘焙缝 · 渲染服务 · 共享包）

> Status: 活跃（2026-08-17 建）。本文是 **clip-spec 字段级契约与渲染链的唯一事实源**（2026-08-17 自 VIDEO_EDITOR.md §4/§6/§9 迁入）；轨道模型（§8）= **现行契约（ADR-044，2026-08-17 过会，08-17~18 落地）**。
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

## 2. 三个包与一个 API 侧

| 家 | 角色 |
|---|---|
| `packages/clip`（@repurposer/clip） | **单一画笔**：`<Clip>` 组件 + spec TS 镜像 + 字幕样式目录；web `<Player>` 与 render 服务共用——parity 之根（ADR-018） |
| `apps/render` | Remotion 渲染服务（express + @remotion/bundler + @remotion/renderer + 内置 ffmpeg，pnpm 独立于 uv），`POST /render` 黑盒：渲染到临时目录 → 预签名 PUT 上传，无共享卷 |
| `apps/web` | 编辑器预览（`<Player>` 包 `<Clip>`），手势 → ops HTTP |
| `apps/api/app/pipeline/` | spec 构建（`clip_spec.py`）+ 烘焙与驱动（`rendering.py`）+ 写纪律（`operations/`） |

## 3. clip-spec 字段级契约

**原则**：renderer-agnostic，只描述"是什么"；样式限预设枚举（CSS ∩ libass 双可表达，保手写 FFmpeg 后路，§7）。

```jsonc
{
  // kind="video": 真人实拍，url 为视频；kind="stills": 图片音频幻灯，
  // url 为可选语音轨（无录音为空串），image_urls 为背景图（0→纯色 / 1→满屏 / N→均分硬切）
  "source": { "asset_id": "uuid", "kind": "video", "url": "/api/v1/files/...mp4", "image_urls": [], "fps": 30, "duration": 120.5 },
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
  "crop": { "x": 0.5, "y": 0.5, "scale": 1.0 }, // 归一化中心 + 缩放；transform 实现，非 object-position
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
    { "start": 12.4, "end": 12.9, "text": "So", "lang": "en" }
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
- **双源形态**（ADR-020）：`kind="video"` 走 `<OffthreadVideo>`；`kind="stills"` 图片音频幻灯——`image_urls` 为背景视觉（1 满屏 / N 均分硬切 / 0 纯色兜底），`url` 为可选语音轨；有语音复用 ASR 词级 `caption_track`，无语音为定长幻灯（每图 `SECS_PER_IMAGE` 秒，后端写合成段）。背景视觉优先级：**slides PDF 页图（`Asset.slide_pages`）优先**，上传照片其次；源选择优先级 VIDEO→AUDIO→SLIDES/IMAGE。**刻意不做**：Ken-Burns / 多句动效文字轨 / 转场画廊（L2 停线，ADR-020；B-roll 已由层轨承接为契约能力，写者技能随能力批）；PROGRESS 需求池的 motion 枚举（P2）若做，限于 **video 源** crop 动态预设，落地需新 ADR 明确与 Ken-Burns 拒绝的边界（ADR-028 关联）。
- **文本拖拽定位**：`caption_position` / `title.position` 为归一化中心点（= libass `\pos`，可移植），null → 渲染默认；`title.size` / `caption_size` 是 **1080×1920 竖屏参考系上的参考值**——渲染端按帧高等比缩放（9:16 不变，1:1/16:9 ≈ ×0.56；双语对照译文主行再 ×0.82、原文小行 ×0.55；字幕块宽 84% = 两侧 8% 边距随帧宽自适应）。人设页皮肤分区的预览叠透明层支持拖拽 marker 改位置/字号（无独立盒宽高、无关键帧动画）。
- **声纹克隆配音（dub）**：`POST /outputs/{id}/dub` 用人设声纹经 voice_clone + T2A 把（翻译后的）字幕合成目标语言语音，烘入 `dub` 轨；渲染时 `dub.enabled` ⇒ **原声静音**、播放 dub（无唇形同步，ADR-037）。dub 在注册表声明 `depends: ["main"]`——时间轴 op 落地后 ops 响应带 `stale_tracks`（重配一句话的素材；不产生"合法的谎"）。

## 4. 轨道解剖（注册表实证）

spec 的顶层字段被 TRACK_REGISTRY 整划为 9 轨——每道的时间轴归属是注册表声明（`timeline` 只声明不实现，remap 全库一个函数家）：

| 轨 | spec 字段（`fields` 分区） | family / timeline | Clip.tsx 渲染位置 | 写者（owner） |
|---|---|---|---|---|
| `main` 主轨 | `source` + `segments` + `aspect` + `target_language` | sequence / 源时间轴 | `<Series>` 逐段 `<OffthreadVideo>`/`Audio`（stills 走 `<Img>` 均分）；**逐段取 src**（`seg.url ?? source.url`） | select_clips / materialize_source（出生）；remove_filler（形态写者） |
| `caption` 字幕 | `caption_track` + style/position/enabled | data / 源时间轴 | `groupLines` → single/stack 两布局，按 sourceTime 反查 | remove_filler |
| `translation` 对照字幕 | `translation_track` | data / 源时间轴（`pairs: [caption]`） | 译文主行 ×0.82 + 原文小行 ×0.55 | translate_clip |
| `crop` 裁切 | `crop`（静态单值） | data / 源（整条常量） | 主轨外层 `transform: scale+translate` | 出生默认（crop_track 关键帧轨 = 一条登记 + 一个采样器） |
| `layers` 层轨 | `layers`（锚定放置物） | layer / derived（锚 → 输出窗投影） | `projectLayers` 求窗 → `LayerView` 按 `media.kind` 单分支（video/image/text），z 经 Sequence style | 暂无（insert_broll 随能力批） |
| `title` 标题 | `title` | block / 输出时间轴（片头区淡入；stack 布局 ~3s 自动退场） | 绝对定位 div | 出生 |
| `music` 音乐 | `music` | block / 输出时间轴，循环铺满 | `<Audio loop>` | add_music |
| `dub` 配音 | `dub`（`depends: [main]`；`mutex: [original_audio]`） | block / 输出时间轴整段（生成时已按 cue 拼接对齐）；enabled ⇒ 原声静音 | `<Sequence from=introFrames>` 内 `<Audio>` | dub_clip |
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
- `tracks.ts` — **TRACK_REGISTRY 目录（双端真相源）**：9 轨 TrackDef（family/timeline/owner/mutex/pairs/provenance/url_fields/checks/fields/depends）；类型级分区断言（ClipSpec 键必须全登记）；`scripts/check_track_registry.py`  diff 双端。
- `Clip.tsx` — 唯一渲染组件。泳道投影消费 `types.ts` 单一家；`LayerView`（层渲染件，按 `media.kind` 单分支）；`TransitionVeil`（入边过渡单侧面纱：fade 12f 黑场 / dip 8f 白闪，媒体之上、层与文字之下）；`groupLines`（7 词一行）；`lineRevealFrame`（行级入场帧 = `outputTimeAtSourceTime`）；`captionEntrance`（entrance 原语 → opacity/transform，每值过 libass 映射闸）；stack 布局（锚点上下半场决定容器生长方向，滑窗 `maxLines`）；双语对照配对（闸在主源段——异源段不匹配主源字幕）；`pointStyle`（归一化中心点 → CSS translate，= libass `\pos`）；尺寸按画面推导（`size × height/1920` 参考系）。
- `captions.ts` — `CAPTION_PRESETS` **字幕样式目录**（注册表先例）：样式 = 三原语（`layout` × `entrance` × `wordHighlight`）组合；**加样式 = 一行登记**（TS 类型由此推导，Python 只校验成员）；**加原语 = 过 libass 映射闸 + Clip.tsx 一分支**（CSS ∩ libass 子集纪律）。
- `fonts.ts` — `fontFamilyFor`（品牌字体枚举 → 字体族）。
- `Root.tsx` — `calculateMetadata`：aspect → 画幅尺寸（original 探源）、`totalDurationSeconds` → 合成时长；`DEFAULT_SPEC` 兜底。

### apps/render（Node 黑盒）

- `server.ts` — `POST /render`：校验 → 临时目录 → `renderClip` → 预签名 PUT 上传 → 返回对象键。`/cache` 静态服务把本地落盘的源经 loopback 喂回 Remotion（CORS `*` 因 bundle-server 跨源 fetch）。
- `render.ts`
  - `renderClip(spec, outDir, basename)` — 主流程：`stageRemoteSource`（源先落盘）→ 共享 bundle（一次构建复用）→ `selectComposition` → `renderMedia`（h264）→ SRT → `normalizeLoudness`。
  - `normalizeLoudness` — EBU R128 双 pass 响度归一（`-16 LUFS / TP -1.5`），ffmpeg 二进制取自 Remotion compositor 包（`resolveFfBinary`）；**增强不是正确性**——失败保留原音，永不翻车渲染；无声产物（stills 幻灯）跳过。
  - `stageRemoteSource`（stage.ts）— Remotion 内部 asset fetch 不走系统代理、整文件下载挤在取帧预算内（慢源 = delayRender 超时灾难）；staging 侧代理感知（`dispatcherFor` 读 HTTPS_PROXY）、按 URL 去重、LRU 驱逐。**异源段**：段的 donor url 同样经 staging（渲染器不知同质/异源之别）。
- `srt.ts` — `captionTrackToSrt`：7 词成行、按 `clipStart`（首个保留段起点）重定基——SRT 与 MP4 同起点，交接 CapCut 的交付物。

### apps/api/app/pipeline（Python 侧）

- `tracks.py` — TRACK_REGISTRY Python 镜像 + fold 助手：`resolve_spec_urls`（烘焙缝，walker 支持路径中段 `[*]`）/ `spec_provenance`（轨级 + 段/层项级 generated 扫描）/ `total_output_seconds`（计价时长镜像，坐 clip_spec.py 的共享算术）/ `track_of_field` / `skill_written_tracks` / `stale_tracks`（派生轨失效声明）/ `assert_single_writer_per_track`（一轨一写者，create_run 编译期 422）+ 两条启动自检（分区对账 + phantom track fixture，挂 `orchestrator.assert_runners_registered`）。
- `clip_spec.py`
  - `build_clip_spec(source, segment, …)` — spec 唯一构建处（段 id 出生即铸）。video / stills 两分支（stills：有声 → 词级字幕 + 语音轨；无声 → `SECS_PER_IMAGE` 定长幻灯 + 合成段）。
  - `locate_span(words, segment)` — 选段定位：agent 数值时间戳优先（**向最近词边界吸附**），否则 start/end marker 文本匹配（渐短探针容忍 LLM 改写），**永不 raise**，兜底全段。
  - `remove_range` / `set_trim` — TS 函数的 Python 镜像（同名同义；id 继承/过渡边规则双端一致）。
  - 泳道投影 Python 孪生（dict 版）：`intro_seconds` / `outro_seconds` / `video_duration_seconds` / `video_timeline` / `source_time_at_output_time` / `output_time_at_source_time` / `project_layer_windows`。
- `rendering.py`
  - `render_output(output_id)` — 驱动主流程：读 spec → 烘焙缝 → 预签名 PUT URL → POST 渲染服务 → 写 `files` + COMPLETED。**竞态守卫**：条件 UPDATE（`render_status == RENDERING`）——渲染中途 morph 重排（re-pend）时本次产物为陈品，删孤键、镜像 superseded，永不覆盖新 spec。
  - `_absolutize(spec)` — **烘焙缝 = 注册表 fold**：`resolve_spec_urls` 按各轨声明的 `url_fields` 绝对化（source.url / image_urls / segments[*].url / brand 卡 / music / dub / layers[*].media.url）——新轨注册即接管，无逐字段特判。
  - `_mirror_render_node` — 渲染生命周期镜像到 run 的 render 步骤（可见性 + 成本的家；run-less 重渲染路径不受影响）。
- `operations/registry.py` — op 注册表（ADR-032 + ADR-044）：`OpDef.writes` 声明写入字段（启动对账分区）；`llm_visible=False` 的六 op（reorder_segments / insert_segment / set_transition / add_layer / remove_layer / move_layer）= 操作集闭包登记——客户端可调、LLM 词汇随技能批开放；载荷 = 实体引用（段 id / 锚 / 枚举），寻址 =（轨, item_id, op）三元校验。ops 路由响应带 `stale_tracks`。
- 认领谓词：`outputs.render_status`（NULL = 未请求 / PENDING 可认领），worker `FOR UPDATE SKIP LOCKED`（ADR-017）。

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

## 7. 渲染器替换路径（spec 不变）

| 触发 | 换成 | 成本 |
|:---|:---|:---|
| Remotion 成本 / 规模问题 | **手写 Python+FFmpeg+libass**：clip-spec→FFmpeg filtergraph 一遍出；字幕用 `.ass`，预览侧用 **libass.wasm（JavascriptSubtitlesOctopus）** 渲染同一份 .ass → 两端共享 libass 保 parity | 渲染逻辑自写；.ass 动画有天花板（我们碰不到） |
| 要"视频不出浏览器" + 降本 | **客户端 `@remotion/web-renderer`（WebCodecs)**：我们的合成落在其 CSS 子集内，现实可换 | alpha 阶段；GDPR 收益有限（ASR 仍在服务端）；可能仍需服务端代理 |

> GDPR 主线仍是**服务端全栈 + EU 区部署**；客户端渲染只是降本备选，不是合规答案。

## 8. 轨道模型（现行契约，ADR-044）

> 2026-08-17 过会，08-17~18 落地：注册表 + 双端自检 + segments widen + 锚/层/过渡契约 + 泳道投影 + 六 op 闭包。判据 = **操作集闭包**：registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改（12 操作走查全表 = 简报 `tasks/done/track-model.md` 附录 §8）。弹性验收机械化：spec 顶层字段 ⊆ 轨道注册表（启动自检对账，⊆ 同款代数）+ phantom track 自检（注册一条假轨，烘焙缝/寻址/合规/计价自动接管，消费方零改动）。

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
| 段 | `segment` | 主轨一行：`{id, asset_id?, url?, start, end, hidden, provenance?, transition}`；异源插入 = 带 asset_id 的段 | 不是 block（讨论期占位词，退役） |
| 数据轨 | data track（`*_track`） | 源时间轴时序数据：caption / translation / crop（关键帧采样随能力批） | 不参与叠放 |
| 层 | `layer`（字段 `layers`） | 锚定放置物列表：kind 枚举（`broll` / `text_callout` / `pip` / `motion_graphic`），z 序渲染，条目可带 `source_ref` 回放（PiP）与 `provenance`（ADR-026 必填） | 不是自由轨；不撞 UI 浮层（overlay 一词归 GenerationOverlay/overlay-surface，避让 N-27 同型撞车） |
| 锚 | `anchor` | 层条目的语义挂接；输出时间派生不落库 | 不是时间码 |
| 过渡 | `transition` | 段的进场边效果枚举（none/fade/dip），挂在段上随换序走 | 不是转场画廊（≤3 枚举封顶） |
| 块轨 | block track | 单值轨，输出时间轴：music / dub / title / 头尾卡 | dub⇄原声互斥在注册表声明 |

讨论期占位词 lane / blocks / junctions / placements 一律不采用（草稿阶段死亡，不留痕）。

### 8.3 轨道注册表（TRACK_REGISTRY）

每条轨一份声明（双端：`packages/clip/src/tracks.ts` = 真相源，`app/pipeline/tracks.py` = 镜像，`scripts/check_track_registry.py` diff 守门），消费方全部 fold 注册表（不再逐字段特判）：

```python
TrackDef(
    family,        # sequence | data | layer | block
    timeline,      # source | output | derived——只声明不实现，remap 全库一个函数家
    owner,         # 写者技能（出生写者豁免撞轨判；一轨至多一个非 fork 形态写者，撞轨 = 编译期 422）
    mutex,         # 互斥槽位声明（dub ⇄ original）
    pairs,         # 声明耦合（translation ⇄ caption）
    provenance,    # C2PA 分类器 fold（ADR-026；段/层项级 generated 另有扫描）
    url_fields,    # 烘焙缝 fold（resolve_spec_urls；路径中段 [*] 展开列表）
    checks,        # 确定性工艺检查（crop 不出人脸框 / 驻留达标 / 字幕不溢出——
                   # verify 的第一批住户，随技能包出生）
    fields,        # 该轨持有的 spec 顶层字段（分区；启动自检强制完整且不交叠）
    depends,       # 派生轨依赖声明（dub ⟵ main；时间轴 op → stale_tracks 告知）
)
```

**加一条轨的成本** = 一条登记（忘登记则分区自检直接红：TS 类型级断言 + Python 启动对账双闸）+ 一个渲染件（新 family 才有）。`crop_track` 随 08-19 能力批以此形态进场。
