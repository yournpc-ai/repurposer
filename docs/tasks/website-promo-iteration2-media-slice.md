# 官网宣传片 Iteration 2：分镜驱动媒体底座与两幕薄片四轮施工

> 当前施工子合同（2026-11-19）。第二轮的官网分镜入口、图片准备交接和波形组件已通过定向检查。标准样例从一次作答到图片审阅、逐幕旁白和配乐试听的真实 Chat 验收仍开放。四轮的施工与验收以本文为准，长期作品规则见 `VIDEO_PROJECT.md`，排期见 `PROGRESS.md`。[父合同](website-promo-evidence-brief-workflow.md)
>
> 每轮只实现本步真实消费者所需的代码和数据，只运行本步定向验证；后续轮次保留明确接缝，不预建空工具、空表、通用平台或未经验证的“提前完成”能力。施工负责人在 Chat 旅程之外批准下一轮验收。产品内的自动推进受已有授权和预算约束。

## 0. 目标、任务与迭代纪律

### 0.1 一条真实用户旅程

真实验收从这条原话开始：

```text
给 https://www.legitevi.com/en 做一只宣传片
```

先完成官网证据和 BrandProfile，再用一次集中 `ask_user` 收齐必要决策。用户一次提交真实答案后，Agent 自行完成分镜、素材、审阅与有界恢复、旁白配乐、编辑和交付。进度可以在原 Chat 中持续呈现。成功路径的交互仅包含最初发话和这一次集中作答。等待用户说「继续」、点击 Start、挑方案、确认首稿、补重试指令，或由测试者发上述任一指令，均判失败。

本轮使用的答复参数是官网品牌介绍、15 秒、产品证据叙事、英文配音与英文字幕、16:9。两幕、24 fps 和纯电子程序化 BGM 由用户在聊天需求中指定。题目只覆盖真正缺失且影响决策的条件。完整 Brief 入口用 fake-provider 检查：所有必要字段已知时跳过提问，进入同一制作链。15 秒和两幕来自这条验收样例。生产中的幕数、镜头语言、素材来源、转场、节奏与适用 Skill 由主模型根据用户意图和证据选择。

新官网请求最多问五题，顺序是「宣传片主要用在哪里，希望怎样呈现？」「希望片长多少秒？」「配音用哪种语言？」「需要哪些语言的字幕？」「画面比例需要哪一种？」。第一题用一个创作方向字段保存完整答案，例如「放在官网首页，用产品演示讲清工作原理」。时长、配音语言、字幕语言和画面比例各自选择，可自由搭配。已有答案直接沿用，末页一次提交各题答案。模型给出题目数组，每个选项包含展示文字和制作值。界面按数组逐题展示，提交时按所选值写入 Brief。

官网读完且还有创作选择时，助手用一句自然的话邀请用户参与，随后显示问卷。若表单参数需要修正，聊天保留原来的邀请。品牌档案留给后续创作使用。用户提交问卷后，助手在开始分镜的同一次响应里简短确认关键选择，并说明怎样据此安排分镜。已有正文时直接显示原话。模型直接开工时，由同一消息通道按已知片长确认一次收件。后续逐幕进度由活动行展示。在某条官网信息确实影响脚本、分镜或视觉选择时，再结合具体决定提及它。用户主动索要官网分析时，按提问作答。

用中文发起上面的请求时，从读取网站的第一句进度到问卷、后台续跑和交付说明，助手都应使用中文。选择英文配音与英文字幕后，仍用中文介绍制作进展。用户明确指定其他交流语言时，后续消息跟随用户的要求。

参考截图用来对齐交互：集中回答一次，之后只看进度和结果。本轮仍按本文的 15 秒媒体合同与受控工具执行。

### 0.2 四轮总出口

这条真实旅程最终完成：

- 由当前主模型直接形成创意主线、两幕语义分镜和两段英文脚本；
- 每幕一张真实 PNG，其中一幕来自受控 SVG 程序，另一幕来自 MiniMax 图片 API；
- 两张 PNG 的真实读回、媒体分析和模型视觉审阅；
- 两段真实 TTS、实测时长、READY NarrationAlignment 和字幕 cues；
- 模型依据实测音频调整分镜，代码负责确定性展开时间；
- 一条程序化生成的纯电子器乐 BGM，无歌声或其他人声；
- 原生标题、必要推镜、真实 cues 字幕和统一整数时间轴；
- 一个可编辑 CompositionVersion 和按 Scene 获取的真实局部画面证据；
- 正式制作时固定 Scene 渲染产物，再组装一个 MP4 Output；
- 完整视频/音频解码、封装与音频技术检查、实际 Output 有序抽帧审阅；
- 前端提供真实可点击的音频波形播放器和最终视频播放入口。

当前四轮止于首次 MP4 技术交付。第 8 步之后另起一次文字修改、第二版制作和重新交付不属于本合同；不扩到 60 秒，不运行与改动无关的旧回归或额外真实媒体任务。

### 0.3 每轮只做自己的一步

每轮施工和汇报必须遵守：

1. 先实现本轮真实消费者需要的协议、执行体和持久化；后续轮次只保留自然接缝，不写占位实现。
2. 只新增/运行本轮命中的 schema、prompt/tools、执行、错误路径、恢复和前端定向检查，不跑无关旧回归。
3. 用纯函数或 fake-provider 检查 N 幕/N 段、已知 Brief 与非官网输入的通用性。真实媒体验收只跑 §0.1 的用户输入。
4. 后续能力不得因 schema 已预留、工具已注册或文件已创建便写成完成。没有执行体和本层证据就不是交付。
5. 每轮测试以本轮已实现的出口为边界。定向测试以替身隔离下一阶段的执行，真实验收使用只交付到本轮的实现。测试者只观察 Chat 事件和产物，产品对话无需「继续」输入。
6. 若本轮必须依赖后续能力才能成立，先报告耦合并缩回最小正确接缝，不以一次性脚本绕过。
7. 验收前配置允许本次请求使用的执行方式、费用授权和预算。可以使用已经生效的授权，或由既有授权机制在唯一问题组的同次提交中取得。图片、旁白和成片沿用普通计划。已授权配乐缓存未命中按 §9B 直接提交，保留报价、授权、内部 Run/Step 和计量。需要额外费用确认或授权不足时，诚实停止并记录本次验收未通过。测试不得代点或绕过费用门。
8. Chat 记录要能证明用户交互次数、当前阶段、调度与停点。超过预算、不可恢复的素材/审阅失败、需要人工判断或缺少自动续行时，Agent 交代实际阻塞并停止。本轮出口缺失即失败，另一次人工诊断的结果只用于定位问题。

正常 Chat 识别起始制作请求后，自主推进到当前已实现的出口。执行与积分确认使用账号原有的 auto 设置及同一报价和计量入口。当前施工止于音频准备，正式保存和渲染随第三、四轮接入。

### 0.4 通用能力，不为两幕写专用代码

- `scene_plan` 和 `SceneAssetSpec[]` 不设置二幕作品上限；服务端按内存、时长、字节、并发和费用预算有界分批。
- 分批大小是部署政策，不是作品 schema 限制；几十幕可跨多次调用完成，超出现行制作政策时诚实拒绝。
- 每幕拥有独立来源、digest、审阅、attempt、渲染和恢复事实；修改一幕只失效真实依赖它的证据。报价前静态校验选中的 SVG，反馈场景与位置。批次结算保留每幕成功或失败结果，后续批次继续处理。
- 图片代码不得包含 LegitEvi 专用 scene id、固定两幕分支或固定提示词模板。
- 音乐代码不得固定 100 BPM、60 秒、25 小节、八段旁白、D minor 或参考片的转场时间数组。
- Scene 数量由模型根据用户约束和叙事需要决定；代码只执行用户明确固定的数量和真实资源边界，不用隐藏模板限制创意。

### 0.5 架构硬边界

- Chat 仍是唯一意图面，作品内容只经 `apply_composition_edits` 保存版本。
- 不新增作品根、第二内容写口、第二时间轴、第三套 Agent loop、完整 NLE 或通用插件平台。
- SourceSnapshot 是素材字节和不可变生产来源的真相；CompositionVersion 是作品真相；Output 只保留现有版本与执行 provenance。
- video-spec 是本项目拥有的 renderer-neutral 合同。Remotion 只是当前 RenderAdapter；FFmpeg/PyAV 是媒体计算底座，均不得反向定义 Composition。
- 模型只能提交有界结构化参数或受控视觉程序，不能获得任意 Shell、数据库、网络、文件系统或 FFmpeg 命令行权限。
- 不迁移 Inspector，不实现 region 动态精确求值，不增加第二渲染器，不恢复整部影片一次性 `render_film.py` 生产链。

## 1. 分镜是创意中枢，主模型拥有创作自由

### 1.1 本次官网宣传片的分轮验收顺序

以下顺序仅适用于本样例。Repurposer 的长期创作对象是持续存在的 Composition 及其版本。Agent 可用已有素材建立粗剪，按需创建媒体、观察视听结果并局部修订。Canvas 可选；Run、Step、队列、计费与恢复由执行层管理。

```text
官网证据 + Brief + BrandProfile
→ 主模型形成创意主线
→ design_video(scene_plan)：模型决定 N 幕、scene_id、intent、visual_description
→ 每幕补齐精确旁白/屏上文字、SceneAssetSpec 和 Skill/Preset/Generator 选择
→ 按 scene_id 准备视觉素材和 TTS
→ 模型根据真实 TTS 时长调整脚本、顺序和 Scene 时长
→ 按真实叙事段落准备 BGM
→ 保存 CompositionVersion
→ Scene 渲染/审阅/局部修复
→ 授权生产、Scene 产物组装、全片 QC 和交付
```

上轮必须先建立可恢复的语义分镜草稿，再按分镜生成图片；不得从“先调图片工具、事后拼分镜”开始。

Scene 是叙事范围和共同坐标，不是 Track 容器，也不要求一幕恰好只有一张图或一个 Clip。一个 Scene 可包含多个原生对象、固定媒体和 Generator 内容。

### 1.2 模型与代码的职责

模型负责：创意主线、幕数、Scene 目的、脚本、画面描述、素材要求、时间调整、Skill 方法选择、受控 Generator 程序和结果判断。

代码负责：来源固定、ID/digest、时间量化、资源展开、执行、持久化、权限、计量和真实错误暴露。

CompositionVersion 保存最终可执行分镜；工作草稿复用 ConversationContext。Skill、SceneAssetSpec、ContentReview、MediaAnalysisReport 和 Scene 渲染产物都围绕稳定 scene_id 与当前 draft/version digest 关联，不另建一份平行 Storyboard 文档真相。

### 1.3 TTS 后的重定时

不把全片时间一次性写死，也不让程序脱离模型创意自动重排整条时间轴：

- 模型先写每幕叙事和脚本；
- 工具生成并测量真实 TTS；
- 模型决定改稿、停顿、Scene 时长、顺序或有限语速适配；
- 代码将已决定内容展开为 ticks/frames/cues，检查不截音、不重叠、不越界；
- 字幕只从真实 Alignment/cues 派生，不按词数估算。

### 1.4 Skill 是方法与资源库，不是固定幕数枷锁

- `SKILL.md/references` 提供创作方法、叙事经验和已知陷阱。
- `shot cards/sequences` 提供可组合的 Scene 目的和画面方法，不强制幕数或复制 demo。
- `Preset` 提供局部参数；`VideoTemplate` 只在用户选择的确需要确定结构的 Skill 中使用。
- Generator 参考源码和固定资源只供读取与创作；模型可在目标 Clip 内编写自己的受控程序。
- 未显式绑定 Skill 时不强制 promo 模板；绑定后尊重其声明方法与资源约束，但不由 demo 的幕数、台词和 BPM 限制创作。
- SkillVersion 只进入作品 provenance；保存后制作和修订不重新执行 Skill。

## 2. 双来源图片与克制的内容门

### 2.1 统一准备协议

模型把 `SceneAssetSpec[]` 写入当前语义分镜。图片准备和计划仅引用 `draft_ref + scene_ids`，报价和 Start 解析当前规格，Run 固定完整输入。按需用 `review_existing=true` 对审阅不可用的固定 PNG 补审一次，复用 Snapshot 和分析证据。分镜拥有的规格字段如下：

```text
scene_id / intent / on_screen_copy
source                    受控 SVG 程序 | MiniMax 图片请求 | 已有固定图片
prompt / program          按来源类型使用一种
subject_region / title_safe_area / caption_safe_area
palette / brand_asset_refs
output constraints
```

来源采用显式判别联合，不使用任意字段袋。服务端按 scene_id 和来源内容生成请求 digest，检查 owner、项目、资源预算、当前 Run 授权和已有固定结果。

### 2.2 受控 SVG 程序

- 视觉程序只在现有受控 runner 边界内执行，固定入口、依赖、资源、尺寸和超时，无网络、数据库、业务调度或任意文件访问。
- SVG 输出须经过静态校验和清洗：禁止脚本、事件属性、外部引用、未固定资源及可逃逸渲染内容。
- 固定视口、字体和光栅化版本，保存程序来源 digest、SVG digest、PNG digest 与执行诊断。Chromium 以 SVG XML 解析并挂载原生 SVG 元素，确定性核验视口和 PNG 尺寸后才送内容审阅。旧版 runner 产物留作历史，当前草稿使用修复后的 runner。
- SVG 内的文字和图形不因保留源码而冒充 Composition 原生可编辑对象。

### 2.3 MiniMax 图片

- 复用现有 `generated_images.py` 的 submitted marker、非幂等提交保护、实际 images 计量、固定 manifest 和 outcome-unknown 失败闭。
- cache probe 不生成图片；缺失图片经普通计划与已授权的自动 Start 进入 Run。验收过程中不出现人工 Start。
- 新生成结果固定为真实 PNG并记录尺寸、mime、请求、provider/model 和 digest。

### 2.4 统一落为 ImageObject

两种来源都先冻结为图片 SourceSnapshot。Snapshot provenance 保存完整生产来源、程序/请求 digest、中间 SVG（如存在）、固定 PNG 和执行版本。

准备工作可以使用 GeneratorObject 表达生产请求；进入正式 Composition 时间线时统一由唯一内容写口写为：

```text
ImageObject + ClipSource(snapshot_id, snapshot_digest)
```

最终 video-spec 只消费固定图片，不包含 SVG 程序、模型请求或生成任务。后续修改生产程序或 prompt 必须准备新 Snapshot，再经直接 Op 或完整所属 Clip 写入新版本；不得原地改写旧 Snapshot。

上轮只交付固定图片和审阅证据；ImageObject 绑定与正式 Composition 保存归第三轮，不在上轮预建无消费者的写口分支。

### 2.5 技术验证、内容验证和人工入口分开

`MediaAnalysisReport` 保存确定性媒体事实；`ContentReview` 保存基于实际像素和 SceneAssetSpec 的内容判断。技术解码成功不等于内容合格，模型没发现问题也不等于全维度通过。

ContentReview 状态只使用：

```text
pass / fail / needs_human / advisory / unavailable
```

- `fail` 必须有实际证据和具体阻断问题，例如必需文字缺失、明显乱码、用户要求的安全区被占据。
- `advisory` 记录可改进的审美选择。装饰线的位置、卡片底色和字体差异只有在破坏明确交付要求时才阻断。分镜分配给后续原生层的文字无需出现在静帧。
- `needs_human/unavailable` 不得冒充通过。
- 内容审阅可由聚焦的同一共享 harness 完成；需要独立判断时再使用独立 reviewer，不默认增加第二模型成本。

## 3. 统一、可版本化、可复现的媒体分析边界

### 3.1 一个报告合同，多个受控分析器

内部 `MediaAnalysisReport` 至少包含：

```text
schema_version / report_digest
source_ref                 snapshot | music | output + 精确内容 digest
media_kind                 image | audio | video
requested_probes[] / parameters
analysis_scope             full | bounded | unavailable
analyzer_set_version
analyzer facts             实际 PyAV/FFmpeg/NumPy 二进制或库版本
media facts                仅记录本轮实际执行的 image/audio/video/container probes
issues[] / limitations[]
```

`report_digest` 由源 digest、探针集合、参数、分析器版本和实际结果共同确定。报告以内容寻址方式保存，SourceSnapshot/Music/Output 只保存精确引用；源内容不变而分析器或参数变化时生成新报告，不覆盖旧报告。

上轮只实现公共 envelope、图片探针和本轮需要的版本事实；音频探针归第二轮，Scene/视频探针归第三、四轮。不得在上轮创建没有执行体的“全媒体分析平台”。

### 3.2 分析器分工

- PyAV：实际解码、逐帧和逐样本访问、时长和计数。
- NumPy：后续短时 RMS、能量包络和确定性电子合成。
- FFmpeg：后续最终封装、Integrated LUFS/True Peak 及明确声明的专项检查。
- 现有 `tools/music/beats.py` 与 `pipeline/prosody.py` 在音频消费者出现时复用或收编，不另写重复算法。

所有分析器都是代码白名单适配器。模型只能选择已实现的探针和有界参数，不能提交 filtergraph 或命令行。

### 3.3 证据语义

- 完整解码证明媒体可完整读取，不证明主观质量。
- 有序抽帧证明所附实际帧被检查，不证明采样点之间的连续运动。
- 波形、BPM、能量、响度和切点偏移属于信号分析，不称为 Agent 已试听。
- 前端【试听】只是用户播放动作，必须连接真实 `WaveformPlayer` 或成片播放器；无需暴露内部分析控制台，也不得伪造人工通过状态。

## 4. Narration、纯电子 BGM 与最少校验

### 4.1 Narration 与 Music 分工

英文 TTS 属于既有 Narration 链，仍按任务参数准备，不作为 Music 的输入或人声乐器。

Music 本批只制作纯电子器乐：不生成歌声，不做 Voice Clone，不做人声压缩、人声驱动 Ducking 或 sonic signature。BGM 时长和段落由当前作品结构与场景边界决定。

### 4.2 通用 ScoreSpec

```text
schema_version / synth_version
bpm（有理数）/ meter / sample_rate / channels
sections[] / harmony[] / instruments[] / events[]
dynamics[] / transitions[] / seed
```

合成器由代码拥有，使用 NumPy 和必要的现有媒体 IO 生成确定性 PCM。模型负责创意、段落和参数，不能执行任意合成代码。

程序化 ScoreSpec 直接产生 `authored BeatGrid`，使用整数源时间 ticks/样本网格；库曲或 AI 生成曲的分析结果标为 `estimated BeatGrid`，二者不得混称。

新增内部 `prepare_music` 准备任务时复用现有 Run/队列、权限、资源限制和固定 manifest，不调用 request-inline 的 `/music/generate` 作为新生产旁路。生成结果进入现有 Music + 对象存储，再冻结为音频 SourceSnapshot；用户作品的音乐默认私有。

### 4.3 事实与权限严格，创意与审美宽松

必须严格的只包括：owner/权限/授权/费用、SourceSnapshot/digest、runner 安全、真实资源上限、媒体可解码、整数时间/帧/样本边界、video-spec 必需字段和 Output 完整性。

机器字段由代码生成或修复：ID、digest、Snapshot 绑定、cues/ticks 展开、源窗和派生时间。不得要求模型反复抄写底层 Track/Clip/Animation，也不得每写一幕就要求重交整部作品。

不得用代码硬判创意对错：幕数、品牌出现位置、叙事方式、视觉来源、BPM、配器、镜头风格和审美偏好由模型依据证据和用户要求决定。只有明确可观察且影响交付的问题才阻断。

单幕写入只校验本实体及可独立判断的来源/权限；完整保存时一次汇总全局问题，只把具体错误返回给对应 Scene/字段，并保留其他正确内容。不得让 validator 替模型重写创意。

## 5. Scene 级局部渲染与精确失效

### 5.1 两类 Scene 渲染，共用同一切片边界

**制作前 Scene 证据渲染（第三轮）**：

- 钉当前 draft/version digest 和 scene_id，只返回该 Scene 的真实 MP4/代表帧。
- 复用 `review_working_draft`、PreviewAdapter、唯一 video-spec 切片和 `/preview`。
- 不创建正式视频 Output，不提供制作前完整成片预览。

**正式制作 Scene 媒体渲染（第四轮）**：

- `produce_video` 内部用同一 compiler 生成 Scene-local video-spec。
- 各 Scene 有界渲染并固定 SceneRenderArtifact，再与全片音频和必要接缝组装。
- 场景内部产物不是用户 Output 画廊，不新增第二交付链。

第三轮只实现实际预览消费者和共享 Scene 切片/digest；持久化生产缓存、并行调度和最终组装归第四轮。

### 5.2 SceneRenderArtifact 身份

第四轮每个 Scene 产物至少固定：

```text
scene_id / scene_render_digest
composition_version_id / content_digest（版本血缘）
scene-local spec digest
输入图片、字体和 Generator 固定媒体 digest
renderer + FFmpeg 版本
实际媒体 digest / 分析报告引用
```

版本血缘与局部渲染身份分开：缓存键只包含真正影响该 Scene 像素的内容。仅绝对输出位置变化而局部内容、设置和接缝未变时，允许复用同一局部渲染；不得用“整片 digest 变了”作为全部重画的唯一理由。

### 5.3 音频与接缝

- Scene 画面使用局部零基时间渲染。
- 跨幕音乐、TTS 和最终混音仍以全片样本轴处理，不把全局音乐机械切成多个 MP3 再拼接。
- 有跨 Scene Transition 时渲染必要 handles；Transition 改变同时使相邻 Scene 的接缝产物失效。
- 全局设置、字体或画布变化使所有相关 Scene 失效。
- 最终组装后仍须完整解码，缓存命中不跳过全片检查。

### 5.4 精确失效矩阵

| 改变 | 必须失效 | 应保持 |
|---|---|---|
| 单张图片 | 该图片分析/ContentReview、对应 ImageObject 绑定、所在 Scene 渲染、当前版本和最终 MP4 | 其他图片、TTS、BGM、无关 Scene |
| TTS 文本或音频 | 新 Audio Snapshot、Alignment、cues、相关 Scene 时间/词锚、全片音频和最终 MP4 | 图片；BGM 字节通常保持 |
| 原生标题 | 目标文字及派生排版、所在 Scene 渲染、当前版本和最终 MP4 | 图片、TTS、BGM Snapshot |
| BGM ScoreSpec | Music/Snapshot、authored BeatGrid、相关卡点派生、全片音频和最终 MP4 | 图片、TTS、Alignment、无需重画的 Scene |
| Transition | 相邻 Scene 接缝产物、最终组装和 MP4 | 无关 Scene 与原始素材 |

旧 Output 的“失效”只表示不能冒充新版本结果；旧成片及历史版本仍可播放、可追溯。

## 6. 四轮施工合同

### 6.1 第一轮：语义分镜、图片分析地基与双来源素材

**当前实施与验证状态**

- 已落码：`SceneAssetSpec` 判别来源与逐幕 digest；N 幕有界分批、缓存、attempt 和恢复；普通 plan/Start/Run 授权；受控 SVG 静态安全与固定资源光栅执行体；复用 `generated_images.py` 的 MiniMax submitted/unknown/实际计量；不可变 PNG SourceSnapshot provenance；内容寻址图片 `MediaAnalysisReport` 与独立 `ContentReview`；真实 PNG/报告完成回合回模及首次送达后折叠。未新增主表、migration、CompositionVersion/ImageObject 绑定、音视频探针或渲染生产链。
- 函数级 fake 定向曾实测 **20 passed, 1 deselected**（18 项本轮用例与 2 项既有模糊/完整入口 golden wire），覆盖 Brief 草稿、显式约束、N 幕缓存/恢复、SVG 安全/digest、MiniMax fake cache/unknown/计量、损坏图片、报告版本、fail/advisory 不重做及结果折叠。新增函数级测试文件与驱动脚本已按要求删除，旧计数不再是当前可复验命令；后续只从真实 Chat 输入按本合同验收。
- 新模块 ruff、命中 Python 文件 py_compile 与本轮 diff whitespace 检查通过。SVG 定向证据使用 fake deterministic rasterizer + 实际 PNG 解码，不等于 Chromium 真实光栅化已验收；MiniMax 证据使用 fake provider，不等于真实图片已生成。
- 2026-11-18 真实执行未通过。任务 1 项目 `dfe21df7-64be-472c-8eac-855f08477f61` 已在真实官网证据/BrandProfile 后出现六字段 `ask_user`（问题 `7b68bffb-f0ac-4f2a-90a9-1118264be371`，group digest `579a14ed…0dd3`），仍待真实用户作答；未代答、未建分镜。任务 2 项目 `80ad9110-354f-4ae8-aa91-1d2ec7b6aea2` 有 15 秒/两幕/24fps Brief、双来源 draft `cnd_4ab3d2ae… / a11262a79678…a885` 及真实 trace，但没有合格出口。
- 任务 2 的 visual Run `c34edab4…`、`3d854ec6…`、`8dd66899…`、`d7d86129…` 均失败：授权 null 序列化假不匹配、SVG 非法 `span`、修复后 XML 不配对、默认 Chromium 不存在。最终静态 XML 校验通过且 Chrome 座位已改为 `resolve_chrome_path()`，但未再取得合格 SVG，不得写成 Chromium 光栅化通过。
- MiniMax 实际提交两次并各固定一张 PNG：原图 Snapshot `44bb7a0e-d60b-5eec-bf1e-8dc1bb5e7f5d` / digest `6a129078…f3d1`，内容重做图 `bd1b079e-48f8-50c1-97d7-efac9f566167` / digest `956062ac…7141`。实际读图分别只有小三角形、含文字且缺方向连接/引用回环，均不合格；当时 ContentReview 均为 `unavailable`（schema 拒收），不是 pass。中轮不得开始。
- 实际记录用量：任务 1 会话 77,285 prompt / 3,381 completion tokens、USD 0.027243；任务 2 会话 1,905,979 / 38,027 tokens、USD 0.617426，MiniMax images=2、图片固定费用 USD 0.007，审阅 step 另记 16,249 / 1,739 tokens。按现有美元分项核算合计 USD 0.651669（任务 1 USD 0.027243 + 任务 2 会话 USD 0.617426 + 图片固定费用 USD 0.007）；审阅 step tokens 未单列美元金额。大量恢复和直接执行属于过度工作，不作为额外验收证据。

**只实现本轮代码**

- 主模型经 `design_video(scene_plan)` 建立可恢复的 N 幕语义分镜和当前 SceneAssetSpec；图片必须引用已存在 scene_id。
- 通用 N 幕 `prepare_visual_assets`、SVG 受控 runner、MiniMax 固定图片、SourceSnapshot provenance。
- MediaAnalysisReport 公共 envelope、图片探针和实际 ContentReview；不实现音频/视频探针。
- Chat cache-miss → 普通计划、授权检查和 Run 的工具投影，真实结果完整送达一次后的折叠与恢复。
- 在最早的图片出口验证最小自动续行。集中作答后的计划复用既有自动 Start，Run 结算事件续行读取证据，按需自主复审或局部重做。续行基于已结算 Run 和当前草稿，同一事件重复投递、刷新或重启后只能推进一次。执行前验证授权、Stop、预算与当前阶段所需证据。

**只跑本轮定向检查**

- 模糊入口一次提交创作方向、时长、配音语言、字幕语言和画幅，五个字段均进入分镜。部分已知时只问缺项，完整入口直接进入分镜。
- fake-provider 覆盖一次作答后自动 Start、结算续行、重复事件幂等、Stop 和预算失败，以及图片未达标时零音频调度。再用 §0.1 做一次真实验收。
- 超过两幕的 scene_plan/SceneAssetSpec 分批、局部缓存和局部失效，无真实 provider 调用。
- SVG 安全边界、程序/SVG/PNG digest、确定性光栅化和真实 PNG 读回。
- MiniMax cache hit/miss、submitted/unknown、权限、计量和不盲重放。
- 图片分析/ContentReview 身份、版本变化、范围和损坏媒体错误。
- 新图片和审阅结果首次完整入模，随后才可折叠。

**真实执行**

- 从 §0.1 原话开始，只允许用户提交一次集中答复。
- 主模型写出两幕语义分镜和 SceneAssetSpec，自动准备一张受控 SVG PNG 和一张 MiniMax PNG，实际读回、分析并审阅。

**授权与停止**

- 按 §0.3 在验收前设定真实执行范围与授权。SVG 仍受执行资源门限制。
- Agent 自行判断和执行有界恢复。固定 PNG 的内容审阅不可用时，同一 Snapshot 最多补审一次。画面内容确实有问题时，最多只对受影响幕做一次有依据的重做。
- 技术提交失败、provider outcome unknown 和内容不符合合同分别处理。结果未知时只查询已验证的固定产物。查不到时，Auto 续行可尝试该幕的本地来源。
- 两次结果仍不合格、媒体不可读或需要更换叙事时停止并报告，不进入第二轮。
- 本轮结束不生成 TTS/Music，不实现 Scene 渲染，不保存正式 CompositionVersion，不调用 produce_video。

**本轮出口数据**

真实旅程保留：最终 Brief、当前 draft_ref、两幕语义分镜、两个 SceneAssetSpec、两个图片来源链、两个 PNG Snapshot/digest、MediaAnalysisReport 引用和 ContentReview 结论。

### 6.2 第二轮：真实 Narration、模型重定时、纯电子 BGM 与波形播放

**当前实施状态**

- 已实现分镜绑定 Narration、原速 Snapshot、READY 对齐回读、真实 cues、单幕模型重定时、通用 ScoreSpec、NumPy 电子合成、私有 Music/Snapshot 和 authored BeatGrid。自动制作在回读音频、完整解码报告和波形后，将试听播放器附在配乐交付消息中。刷新从同一条消息恢复试听。
- 旁白 Run 完成后，每次改稿都按当前幕的原文、音色和语言重新匹配录音，并向模型提供匹配录音的实测总长和剩余时间。仅将缺少匹配录音的幕合批补录，逐幕确认 READY 对齐和全片时长后开始配乐。
- 官网澄清按五个字段一次提交。图片 Run 携带精确草稿引用，后续幕字幕重新量化，配乐前检查时长。自动录音在原会话更新一行进度，每幕只计最近一次实测时长。需要用户决定时，由已保存的待回答问题承接。
- 官网证据就绪后，制作选项有缺项时仅开放一次集中提问。正文中写出的工具标记不会创建问卷，重试仍需通过原生工具提交表单。已有完整要求或本次请求的问卷已结算时直接进入分镜。
- 已通过审阅的图片按幕和快照摘要写入当前草稿，模型可在同一幕提交旁白稿。若画面无法写入时间线，Chat 指明停在哪一幕。受控 SVG 中上屏的 DOI 要与来源或用户原文核对，文字裁切通过换行、移动或调整容器修复。
- 项目 `83a1bc90-266e-4082-b180-3be7b6e7170e` 的旧运行停在图片阶段。后续项目 `ff0604d5-2d2a-4947-a5d6-4374e0bea74c` 一次作答后自动完成五张分镜图，其中两张局部返工后通过。首幕已通过的图片在分镜写入时两次返回 `source_not_ready`，两次图片 Run 后没有音频 Run 或缓存音频交付。该项目另记录了问卷类型重试文案外露，以及为排版而截短 DOI 的问题。
- 收尾由用户从新 Chat 验收。按 §0.1 的标准样例，一次作答后后台应完成两段真实旁白并继续准备纯电子配乐。刷新后应能看到相同的只读进度。五幕样本覆盖按幕绑定图片与旁白的实际使用场景。
- 音频分析使用 worker 随依赖安装的 FFmpeg 测量响度与真峰值。测量失败时，Chat 报告音频已生成及试听交付的停点。真实首幕原音已在隔离数据库通过快照、波形消息写入和重新读回。
- 官网分镜入口使用已冻结的来源校验引用。选择网页视图时可读回对应图片的 ID 和摘要。混用网页与图片引用时，草稿写入会指出需要修正的幕。重新提交单幕素材规格时，其他幕保留原来的规格。[分镜入口验证记录](../VERIFICATION.md#413-官网宣传片-iteration-2-第二轮narrationbgm-与波形)
- 使用官网截图时，每张候选图附带所属网页和段落标题。分镜可用 `source.visible_evidence` 指定截图必须呈现的内容，用 `on_screen_copy` 保存后续原生标题。图片准备按目标画幅等比缩放并居中留边，审阅仍检查原文、主体、可读性和明确指定的留白。首批图片全部退回时，原 Chat 保持制作中，由逐幕返工结果决定是否停止。

**只实现本轮代码**

- 复用 `prepare_narration`、VideoNarration、SourceSnapshot 和 READY NarrationAlignment。
- 将实测时长和 cues 送回当前分镜，由模型提交目标 Scene 的改稿/重定时，代码展开 ticks。
- 实现通用 ScoreSpec、确定性电子合成器、`prepare_music` Run、Music/Snapshot 和 authored BeatGrid。
- 扩展同一 MediaAnalysisReport 的音频探针；复用 ChatDock/ComponentSlot 与 WaveformPlayer。

**只跑本轮定向检查**

- 任意段数 TTS 时长换算、完整 cues、无静默截断和无重叠。
- 模型目标重定时与代码量化分工，不把整片创作交给全局自动重排。
- 多 section、不同 BPM/时长的 ScoreSpec 确定性和缓存身份。
- authored/estimated BeatGrid、采样率/声道、RMS/峰值/削波和 LUFS/TP。
- 无歌声/人声 Music 和 Ducking；波形播放器 live/history、失败和刷新状态真实。

**真实执行与出口**

- Agent 自主准备两段英文 TTS，完成 READY Alignment，并由模型确认/调整分镜时间。
- Agent 自主生成一条适配当前分镜的纯电子 BGM。
- 真实旅程保留两段 TTS Snapshot/READY Alignment/cues/实测时长、更新后的 draft_ref，以及一条 BGM Music+Snapshot+ScoreSpec/authored BeatGrid 和音频分析报告。
- 用户在同一 Chat 中看到按场汇总的只读录音进度，制作自动继续。缺少当前草稿、有效音频或读回报告时，Chat 显示停在哪一步。
- TTS 无法在有界改稿内适配、Alignment 不 READY、BGM 不可解码或分析事实不可信时停止。
- 本轮结束不保存正式 CompositionVersion，不实现 Scene 渲染，不调用 produce_video。

### 6.3 第三轮：CompositionVersion、Scene 证据渲染与局部修复

**第三轮设计审查前提**：既有工具应允许先保存可编辑粗剪，后续按需补充素材。独立验证 Agent 在同一 composition_id 上读取精确版本与区间的真实视听证据，根据观察修改目标 Clip 或对象，再观察新版本的相同区间。记录前后版本、局部变化、保留素材及证据引用；声音或画面未实际检查时分别标明。第二轮音频交付单独验收。

**只实现本轮代码**

- `design_video(scene_plan/scene)` 消费固定 ImageObject、READY Narration、BGM Snapshot 和当前 Brief。
- 原生标题、推镜、重定时后的逐幕 cues 字幕和 BGM AudioObject 经唯一写口保存 CompositionVersion。草稿、旁白、配乐均沿用第二轮实际交付的引用与 digest。
- 当前 digest 的图片来源/ContentReview 绑定门；只检查明确的阻断问题，不把 advisory 变成修复循环。
- 共享 Scene-local video-spec 切片和 scene_render_digest；扩展 `review_working_draft`/PreviewAdapter 获取当前 Scene 真实证据。
- Scene/视频媒体分析探针；不实现正式 Scene 生产缓存和最终组装。

**只跑本轮定向检查**

- 两幕真实样例及无媒体调用的 N 幕编译样例；不得以幕数选择不同生产链。
- ImageObject/Snapshot provenance、TTS 无截音、真实 cues、BGM source window、fps 和 15 秒量化。
- 完整保存一次汇总错误、目标字段修复和其他正确内容保留。
- Scene 切片身份、局部零基时间、相邻接缝范围和无关 Scene digest 不变。
- video-spec 不含 SVG 程序、生成任务、FFmpeg 命令、Remotion 私有概念或 CreativeState 全文。
- stale base、原子版本和局部修复只影响真实依赖。

**真实执行与出口**

- Agent 保存并完整呈现首稿。该呈现是可见进度，验收不等待用户确认。
- 对每幕获取真实 Scene MP4/代表帧并审阅；发现问题时只修受影响 Scene，再重取该 Scene 证据。
- 真实旅程保留当前 CompositionVersion/base_ref、每幕 Scene 证据和审阅结论；不创建正式视频 Output。
- 不为验证局部渲染而强制制造问题，不调用 produce_video，不组装制作前完整成片。
- Scene 证据无法取得、保存版与素材 digest 漂移或局部修复仍失败时停止。

### 6.4 第四轮：授权制作、Scene 产物组装与 MP4 技术交付

**只实现本轮代码**

- `produce_video` 固定版本和所有媒体 digest，以同一 Scene 切片生成 SceneRenderArtifact。
- 固定生产缓存身份、必要 handles、全片音频/转场/Scene 画面组装和有界并发。
- FFmpeg 完成当前混音/响度/封装，PyAV+FFmpeg 完成全帧全音频解码和声明过的专项探针。
- 复用 OutputDeliveryCard/ChatOutputViewer；分析事实进入现有质量读面，不新建第二套 QC UI。

**只跑本轮定向检查**

- SceneRenderArtifact 身份、命中/未命中、绝对位置变化复用和全局设置失效。
- Transition handles、全片音频样本轴、缓存命中仍完整解码和 Output provenance。
- 晚期坏帧、截断音频、封装/响度/峰值报告和失败闭。
- Preview/Render 共用 video-spec 求值边界；不开发替代 Remotion 的第二实现。

**真实执行与最终出口**

- 首稿和逐幕证据就绪后，Agent 在已有执行和费用授权内自动推进。
- 调用一次正式 `produce_video`，生成 1920×1080、24fps、约 15 秒的 MP4。
- 对每个精确 Output 做全帧全音频解码、封装/响度/峰值检查和实际有序抽帧审阅。
- 真实旅程保留一个可播放 MP4 Output、确切 CompositionVersion/execution manifest、SceneRenderArtifact 来源链和统一分析报告。
- 报告分别陈述技术检查、模型离散视觉审阅、音频信号分析、连续播放与人工视听的真实执行状态。
- 本轮结束不另起文字修改、不制作第二版、不扩 60 秒、不运行额外真实回归。

## 7. 恢复、上下文、所有权与逐轮汇报

- 每轮开始重新核对 HEAD、git status 和 diff；禁止 reset/checkout/stash/clean 制造干净基线，不覆盖其他并行任务修改。
- 固定 Asset/Music/SourceSnapshot、NarrationAlignment、ScoreSpec、MediaAnalysisReport、ContentReview、CompositionVersion 和 Run/Scene manifest 是跨轮恢复事实；聊天历史不是第二份作品状态。
- 模型每轮只看到当前分镜范围、当前 SceneAssetSpec、当前媒体、当前审阅/分析/渲染和当前错误；已完成幕保留紧凑引用，不累计全部旧媒体和工具参数。
- 新 PNG、TTS/BGM、分析和 Scene 审阅结果必须完整入模一次后才可折叠。刷新和跨轮恢复重新读取固定引用，不重新执行非幂等生成。
- Stop、失败和 outcome-unknown 继续遵守现有 Turn/Run 边界；不得为赶下一轮而盲重试付费请求。
- 每轮只更新本子合同的当前状态及既有验证登记，不新增会话纪要、重复验收报告或 ADR。

每轮汇报固定包含：

```text
本轮实际代码与数据结构变化
本轮定向自动检查及真实结果
真实入口的项目 id、trace、素材或版本引用
最初输入与集中作答次数、自动 Run 续行记录、下一阶段零调度证据
实际媒体 digest / 分析报告 / 审阅范围
未运行、未证明和仍为后续轮次的能力
真实 provider 用量与费用（无则明确为零/未调用）
工作树并行风险与未解决阻塞
下一轮所需最小工程条件；随后停止等待施工复核
```

## 8. 当前非范围与执行顺序

当前不做：歌声/人声 Music、Voice Clone、Ducking、sonic signature、复杂 3D、30 秒/竖屏衍生、通用素材市场、自动无限重做、第二渲染器、第 8 步后的第二版局部修订和 60 秒扩片。

Scene 级局部渲染是本合同第三、四轮的明确范围，不再推迟到 Iteration 5；但不提前建设通用缓存治理平台、自动扩缩容或第二时间轴。

固定执行顺序：

```text
第一轮：语义分镜 + 图片分析边界 + N 幕双来源素材
  ↓ 图片出口成立，施工复核后接入下一阶段
第二轮：TTS + 模型重定时 + 纯电子 BGM + 波形播放
  ↓ 音频出口成立，施工复核后接入下一阶段
第三轮：CompositionVersion + Scene 证据渲染 + 局部修复
  ↓ 当前版本与每幕证据成立，施工复核后接入下一阶段
第四轮：SceneRenderArtifact + 全片组装 + MP4 + 技术交付
  ↓
停止；第 8 步之后的局部修订另立施工范围
```

第二轮尚未验收通过。真实项目已取得逐幕原音和 READY 对齐。标准 15 秒、两幕样例仍需在同一 Chat 中从一次集中作答走到实测时长合适的分镜、纯电子配乐和刷新后可用的试听入口。第三、四轮未开始。

2026-11-20 第二轮复验：配乐 Start 的草稿读取改为直接读取已提交的 Conversation.context。隔离 PostgreSQL 双会话回归验证最新引用通过，旧摘要及停用候选仍被拒绝；另有 19 项旁白和续行定向测试通过。随后新建项目 `b38acae3-7994-4332-ac4d-5ee25ff434f1`，从 §0.1 原话开始，五题一次作答，在创作方向中明确两幕分别使用受控 SVG 和 MiniMax。两次图片 Run 自动执行。首轮两幕均被内容审阅退回，返工后第一幕通过；第二幕生成图仍缺少可辨识的短视频界面与来源链接，达到内容返工上限。消息 `8cf4d72e-3ccf-46af-9ae7-812002c3156d` 已向用户说明停点。同一项目未进入旁白或配乐，刷新与实际点播条件未满足。会话累计输入 330,177、输出 21,928 token，conversation_usage 记录 US$0.062684，两次图片步骤合计扣 12 积分。此记录不改变第二轮未通过的结论。

**2026-11-20 工具回执施工与实测**。分镜回执按合并前候选与本次实际写入逐幕比较，给出变化、可复用、待准备、仅需复审、待修订及已停止的幕。准备计划的回执使用真实 Run ID 区分已启动与未启动；配乐缓存命中并完成交付时携带已落库的播放消息 ID。用户实际播放仍须浏览器取证。配乐 Start 的精确摘要保护继续生效。

| 新项目 | 同一 Chat 的实际出口 |
| --- | --- |
| `5a727849-5743-470d-8383-20751fea1889` | SVG 首次通过并复用，MiniMax 返工后仍未表达论文到视频的连接关系，图片阶段停止。trace 揭示变化列表误用了合并后草稿作基准，随后已修正。 |
| `cc4c24b8-760f-4f6c-98f8-ec68bbceed05` | 在唯一问卷中指定 SVG 讲解来源关系、生成图展示研究者。分镜参数先后触发结构校验，随后生成了缺少官网依据的 DOI，来源保护拒绝，未创建图片 Run。已将具体标识符的来源要求放入 SVG 参数说明。 |
| `0f3a1486-dc68-49e3-ab9e-e4b8aa5e23ed` | 同样的分工。SVG 图解首次通过。修订回执准确标记只改第二幕、第一幕可复用；后台只重做第二幕。生成图仍呈横向手机，违反模型为该幕设定的竖向拍摄要求，两次内容审阅后停止。 |

三次均一次集中作答，未人工补 Start 或修改状态。会话记账共 US$0.110611，图片步骤合计 20 积分。最新项目没有旁白或配乐 Run，可刷新试听的出口仍开放。下一项独立的对象 Transform 验收已登记在 PROGRESS §0.1。

后续图片诊断已确认一个独立 SVG runner 缺陷。五份原始 SVG 已用真实 Chromium 本地重绘并恢复布局，内容审阅 schema 和规则同步修正，详见 [验证登记](../VERIFICATION.md#412-官网宣传片-iteration-2-上轮语义分镜与双来源图片)。当前仍需从生产 Chat 路径验证真实图片审阅和自动恢复。

作答后的图片计划和后台续行复用普通计划与授权，按原回合保存的工具记录、分镜草稿和媒体结果恢复。助手在问卷提交后确认影响剪法的选择。顺利的逐幕录音、对齐和开始配乐可以跨多轮工具调用，只更新一条活动记录。实测结果需要改稿或换画面时，助手说明具体取舍并继续制作。正文按消息显示一次，后台续行和刷新回读沿用同一份正文。第二轮在配乐可试听处交付。

项目 `029cdef6-70d3-4674-a120-d995764e5229` 的失败路径已修复。图片 Run 会保留已经生成的资产和逐幕错误，按结算结果在同一对话中恢复。SVG 排版报告提供实际画布与字幕安全区坐标，审阅分别判断超出安全区和真实像素裁切。真实 Chat 由用户验收，从一次集中作答继续到音频出口。

## 9. 第二轮施工差异清单与验收记录

本节为第二轮当前生效的专项修订。已授权 prepare_music 缓存未命中时，§9B 优先于前文普通计划与模拟 Start 的描述。先通过 A 的归档回放，再部署通过事务回归的 B，两项通过后执行完整第二轮真实 Chat 验收。

### A. 图片：缩小可触发返工的要求

| 动作 | 当前代码路径与改动 | 归档回归与放行条件 |
| --- | --- | --- |
| 删除审阅中的隐式硬约束 | `tools/video/visual_assets.py::SceneAssetSpec` 保存生成意图及 `source.prompt`。`tools/video/media_analysis.py::review_image_content` 目前序列化整份规格给 reviewer，`prompts/video/visual_content_reviewer.j2` 据此判定“明确要求”。保留完整生成指令；给 reviewer 单独投影本幕应交付的主体、证据、文案与可测约束。硬要求须能指回用户原话、集中作答、可核实的技术约束。模型分配的本幕职责仅用于判断叙事，允许不同画面实现；按各幕职责检查必要关系，其他幕已表达的关系无需重复，孤立图标不足以证明关系成立。模型在 intent 或 prompt 里重复写“必须”不能赋予它这个来源。 | 回放 `0f3a1486-dc68-49e3-ab9e-e4b8aa5e23ed` 的实际问答、两幕分工、第二幕固定 PNG 和原 findings。若唯一偏差为模型选的手机方向，允许 pass/advisory，第二幕不进 repair/blocked，第一幕仍复用。对照同一 PNG，仅把“必须竖装”改为用户明确要求，横装且像素可证时应 fail。不能按“手机方向”写特例。 |
| 合并失败判定和返工依据 | `media_analysis.py::ContentReviewAnswer._status_matches_findings` 目前检查 requirement 和像素 evidence 的格式，不能证明该要求来自哪里。让阻塞 finding 对应上一步给定的本幕要求，并有实际像素证据；无依据的风格偏差仅作建议。沿用 `chat/media_journey.py::media_actions` 已有的 pass/advisory 放行与逐幕处理。 | 回放 `5a727849-5743-470d-8383-20751fea1889`。从原问答和分工判定哪一幕负责“论文到视频”的关系；若分配给该图而确实缺失，应退回该幕。若已由通过的 SVG 表达，不能仅因另一张图没有重复表达而退回。记录判据出处、对应像素和实际返工幕；增加确实缺主体或必要文字不可读的反例。 |
| 保留来源与结构保护 | `tools/video/visual_citations.py::validate_website_scene_citations`、`ControlledSVGSource.program` 及 `prompts/chat/_video_project.j2` 承接 DOI 的来源说明与校验。保留 schema、输出尺寸、解码、适用的安全区与固定来源校验。 | 回放 `cc4c24b8-760f-4f6c-98f8-ec68bbceed05`。原始无效结构仍拒绝；未经证实的具体 DOI 拒绝且图片 Run、图片调用和相应扣费均为零。另用可追溯的完整 DOI 或任务允许的通用来源标签，应能越过该校验。独立计数结构错误和来源错误。 |
| 保留已通过素材与审阅恢复 | `chat/media_journey.py::scene_asset_changes` 继续比较修改前后规格；`tools/video/visual_assets.py::prepare_visual_asset`、`review_fixed_visual_asset` 和 `media_analysis.py::image_reviewer_version` 区分生成内容与审阅版本。旧规格仍可读，恢复时从原始问答和分工取得审阅依据。 | 用原项目、固定 PNG、摘要、旧报告及已有分析回放。审阅规则更新可生成新报告；若像素输入仍适用，图像供应商新增调用为零。修改第二幕来源时只将第二幕计入 changed；首幕不重生成，也不消耗返工次数。原报告留作对照。 |

定向覆盖落在 `apps/api/test/core/test_visual_asset_recovery.py`、`test_media_journey.py` 和 `test_website_promo_wire.py`。先验证真实组装给 reviewer 的输入，再验证 findings 如何进入实际调度；只注入一个预设 pass 不能验证约束来源。

### B. 配乐：已授权且缓存未命中时直接提交

| 动作 | 当前代码路径与改动 | 定向回归与放行条件 |
| --- | --- | --- |
| 删除配乐自动分支的计划往返 | `chat/video_turn_seats.py::prepare_music_seat` → `chat/media_journey.py::dock_media_observation/_dock_tasks` → `chat/plan_turn.py::_present_plan` → `chat/service.py::_auto_start_docked_plan/answer_question`。只在官网旅程、时序就绪且授权成立的 miss 分支，省去 plan_task 外传、计划预览、pending_brief 的本次计划写入、task_book 问题和模拟 Start。同步调整 `chat/turn_tools.py::_prepare_music_tool` 的分支说明。 | 用历史配乐故障样本 `dc28ebcf-f6d6-4b12-b5ae-3a7fd7105b28` 的两次重定时和最终乐谱，走真实工具分派。一次合法调用提交一次执行；新增计划问题、模拟 Start、要求模型重述乐谱或手输 start 均为零。缓存命中直接交付；无效乐谱或失效草稿明确拒绝。 |
| 合并授权判定和执行提交 | 从 `chat/service.py::resolve_confirmation_need/answer_question` 复用报价、实际制作意图、确认策略、授权依据快照及 Stop 的提交边界；复用 `pipeline/lifecycle.py::evaluate_start_gate` 中适用的检查。由 `pipeline/orchestrator.py::create_run` 锁项目、固定授权输入、检查余额并预扣。真实需要确认时保留原 Dock。 | 自动、须询问、超限、不可报价、余额不足、无制作意图及跨 owner 分别覆盖。已批准范围内才可直接提交；须确认时确认前零执行，拒绝时零扣费。Stop 先取得原回合锁则无可认领 Step、无已提交 hold；提交先赢则沿现有取消路径释放未用额度。外部只能在提交成功后看到已接受。 |
| 合并重放到同一次执行 | 服务端在首次执行提交前，将调用身份和确切参数持久化到原回合记录。恢复先读该记录，无需模型重建相同参数或 call ID。在 `create_run` 的项目锁内核对稳定身份、owner、项目和参数摘要，重放查询先于活动 Run 排斥；沿用 `pin_music_preparation` 对当前草稿和乐谱的固定。乐谱内容哈希用于素材复用，不能单独充当用户调用身份。 | 隔离 PostgreSQL 两会话同时提交同一调用、提交成功后丢响应再发、完成后再重放，均取回同一执行；相同身份异参拒绝。两个不同调用竞争同一项目仍遵守活动 Run 互斥。用新调用检验最新摘要通过、旧摘要及 inactive 拒绝；历史重放只取原结果，不把它绑定到已改时长的作品。 |
| 保留 worker、结算与交付 | 沿用 `PrepareMusic.run`、`prepare_programmatic_music`、`platform/billing.py::hold_run/capture_step/release_run`、`audio_playback.py::record_prepared_audio` 及 `media_journey.py::recover_settled_media_journeys`。保留 `compile_graph` 和现有项目并发上限。 | 成功、取消、执行失败、旧 worker 晚写、重启补送和缓存/完成事件竞争分别覆盖。按当前本地合成报价核对账本金额与去重键，零价不能制造正额费用；重复提交不能新增结算。交付核对固定 WAV、ScoreSpec、Snapshot digest、完整分析、唯一播放回执。草稿已改变时仍可追溯旧结果，并阻止过期交付。 |

配乐入口与恢复回归沿用 `apps/api/test/core/test_media_audio_continuation.py`、`test_media_journey.py`、`test_delivery.py`，并在数据库 fixture 验证真实事务及账本；单测中的合成桩不能作为真实试听证据。配乐故障的历史样本与上面三个图片项目分别计数。

### 合并放行条件

- [ ] A 的三份归档逐例列出实际阻塞依据、无效工具调用数、各幕新增生成次数和复用的图片 digest。只改拍摄偏好的用例增加零次生成。保留该退回的来源错误和真实交付缺陷。
- [ ] B 的同一请求分别记录改造前后从 Tool 到持久提交的交接、问题行、模拟 Start、Run、Step、账本记录和交付回执。已授权 miss 达到零计划问题、零模拟 Start，同一调用只有一个执行。真实确认和 Stop 竞争用例均通过后才启用直接路径。
- [ ] A、B 独立回归均通过后，以新项目在同一真实 Chat 一次集中作答，完成约定的 SVG 与 MiniMax 两幕、英文旁白、READY 对齐、实测重定时和纯电子 BGM。记录固定音频与分析引用，刷新后点播并观察播放时间前进。同一份记录报告无效调用、已通过素材重生成次数与实际费用。通过后再逐一检查图片、TTS 的 Dock 路径。

### 2026-11-20 实施与证据

A 的媒体生成继续使用完整规格。图片审阅单独读取原始制作请求、集中作答、各幕叙事职责、来源证据及技术分析。改变用户要求会改变审阅版本，固定 PNG 可复用。以下 digest 为固定 PNG 字节 SHA-256 的前 12 位。无效调用按原会话已持久化的失败工具回执计数。

| 原项目 | 原会话失败调用 | 固定样本回放 | 回放新增图片生成 |
| --- | ---: | --- | ---: |
| `0f3a1486` | 0 | 首幕 `2ffdf1575da0` 已通过。次幕同一 PNG `7c9878962d37` 在原问答下为 advisory；仅新增用户明确要求手机竖装后，横装像素导致 fail，依据为该条用户原话。 | 各幕 0 |
| `5a727849` | 2 | 首幕 `c580025c52e0` 已通过。次幕 `d4bcc0a0be16` 承担可核验回链，但画面里的手机与纸面间缺乏可辨认的对应关系。审阅返回 fail，阻塞依据为该幕叙事。 | 各幕 0 |
| `cc4c24b8` | 3 | 两次结构错误、一次缺乏来源依据的具体 DOI 拒绝。改用通用来源标签后通过来源校验。原项目图片 Run 为 0。 | 各幕 0 |

B 以原制作回合的服务端 ID 和工具名确定一次最终配乐请求。在授权及启动条件成立后，先独立持久化请求 ID、完整参数与摘要，再在持有项目锁的提交事务内创建 Run、Step、计量范围及活动回执。恢复时读取已存请求。同一身份异参明确拒绝。需要确认的调用继续进入原确认入口。

配乐归档 `dc28ebcf` 原先在普通计划的模拟 Start 处报草稿失效，未创建配乐执行。取原最终草稿和乐谱，在隔离 PostgreSQL 重放真实配乐分派，乐谱 digest 为 `537e8abe775e49a3d0b3cc11df2c13a8b7efd01f3a5078213efc5522832083e1`。结果为零计划问题、零模拟 Start、一个 Run、一个 Step，本地合成报价为零。数据库回归另覆盖并发、回滚后恢复、同身份异参、完成后重放及 Stop。此回放只验证提交。

真实项目 `7fc049e8-bfd1-406b-b72c-397bf36261fa` 一次集中作答后，首幕 SVG 首次通过（`74ce0166a65f`）；第二幕生成图局部返工一次后通过（`b118f91cb424`）。已通过的首幕重生成 0 次。两幕写完后，模型在仍开放的 scene 参数上重复填幕两次，触发 scene_order 后停在录制前。持久化失败工具回执共 3 次（另一次为 palette 结构校验），图片结算 10 积分，会话记账 US$0.060242。修正音频阶段的工具参数投影后，已填满的草稿仅开放旁白修订及适用的录制、对齐操作。
