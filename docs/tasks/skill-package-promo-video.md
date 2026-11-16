# 宣传视频核心 Skill、统一 Skill 包与视频后续施工

> Status: ACTIVE（2026-11-10）。P0–P5 已落码；工作草稿、条件工具、局部 Scrub 与旧 Film 删除已落码；完整 live 矩阵、双片和最终视听仍未验收。本文统筹 Video Project 剩余能力与验收；创作循环的唯一实施合同为 [Composition 创作循环与上下文收敛](composition-authoring-context-convergence.md)，不在两处复制施工细则。目标长期法归 VIDEO_PROJECT，当前优先级只归 PROGRESS §0。

## 0. 目标与硬边界

建立内置与外置 Skill 共用的渐进式创作工作流，让 Agent 像工程师一样按需读文档、读参考源码和查看真实预览，再为当前作品编写视觉来源。`promo-video` 是首个完整消费者，用户面名称为「宣传视频制作」。

- 不引入 `ShotMethod`、`ShotRecipe`、运行期 ShotRegistry、动态镜头 import 或通用插件平台。镜头库是 Skill 包内的创作资源，不是新的作品层。
- 不新增作品根、第二意图面、第二内容写口或第二生产链。作品内容仍只经 `apply_composition_edits` 形成 CompositionVersion。
- Provider 只能通过 harness 的有界只读工具获取当前绑定 SkillVersion 的内容；不能自行访问本地路径、外站或业务数据库。
- 外部卡片、TSX、模板和脚本均为不可信参考。外部脚本永不直接执行，外部 TSX 不因被读取而获得运行资格。
- Generator 允许 LLM 自主编写完整 Remotion 工程：多文件、多组件、共享 helper、Composition 注册与内部时间线均可由创作需要决定。限制的是系统权限、依赖与资源，不是工程内部的创作结构。
- 完整 Remotion 工程只作为 Generator 的不可变生产来源，经隔离 runner 烘焙为固定媒体；最终 video-spec 仍只消费固定媒体，不含 React/Remotion、生成任务或模型请求。
- Home demo 展示精心校准的有限强组合，不是能力全集。Skill、template 和 arc 只决定首稿起点；作品出生后，用户可在 Chat 改 arc、场景、镜头、素材、文字、声音和可用 Generator。
- P0–P10 的编号表达依赖与施工组织，不是用户侧能力围墙；可并行轨道见 §5。任何已注册且验收可用的能力都必须能从 Chat 询问和使用，不要求先出现在 Home。
- Skill 不进入 worker；修订不重新执行外部包。制作继续钉版本、来源、依赖和 digest，恢复不重新创作。
- 支付、通用 Chat 基础设施和其他非 Video Project 工作仍归各自合同，不借本计划扩大范围。

**施工期纪律**：P0–P5 只专注代码正确与功能实现，不写测试、不跑测试套件、不调用真实付费模型/TTS/采集/渲染，也不制作样片。每批必须完成调用链、schema/序列化、import/include、权限与失败分支的静态自查，不留明显断链或明面 bug；落码不等于验收通过。整个 `promo-video` 创作链接通后，由 P6+P7 一次性补用户主流程与承重架构测试、运行付费真实验收、收口 Renderer 生产门并制作/验收样片。部署前的既有完整仪式链不因此取消。

## 1. 统一 Skill 包

内置包位于 `app/skills/<skill_id>/`，随应用部署、内部注册和使用，不开放用户自助安装；外部包持久化为 owner 隔离、不可变 SkillVersion，仅用于内部登记、测试与历史 provenance，不承诺 Claude Code / Codex 插件运行时兼容。两者支持同一组逻辑资源：

```text
SKILL.md
references/
├── shots/<category>/<card>.md
└── sequences/<arc>.md
gallery/
├── api/library.json
└── media/...
demos/
└── <category>/<card>/
    ├── 参考源码
    ├── fixtures / textures
    └── 所需共享资源与依赖说明
template/
└── 可选的完整起始作品、VideoTemplate 与预览
```

分类 id 固定复用：

```text
opening / camera / transition / typography / ui-entrance
interaction / data / effects / rhythm / outro
```

| 资源 | 职责 |
|---|---|
| `SKILL.md` | 任务判断、创作路线与工作流入口 |
| shot cards | 镜头意图、适用场景、能量、参数、已知坑与参考实现位置 |
| sequences | 可选全片 arc、段位、节奏与候选镜头 |
| `library.json` | 静态发现、卡名/变体消歧和预览定位；不是执行注册表 |
| `demos/` | 调校后的参考源码与依赖事实；常规工具只读 |
| `template/` | 可选首稿起点，以及显式声明的隔离 Generator 资源 |

`promo-video` 六类资源齐全。外部包允许缺少 template 或部分资源，能力报告必须明示，不伪造完整度。共享 `assets/lib`、fixtures 和纹理作为 demo 的声明依赖处理，不另建作品概念。

## 2. 命名与 Generator 合同

`GeneratorObject.runtime` 改为 `GeneratorObject.producer`，生产方式的跨栈名称为：

| producer | 含义 |
|---|---|
| `draw-2d` | Agent 编写受控 2D 绘制程序，生产固定图片或视频 |
| `remotion-project` | Agent 编写完整、不可变的 Remotion 工程，经隔离 runner 生产固定媒体 |
| `image-generation` | 保存模型图像生成请求，授权制作后生成并固定图片 |

版本由 schema_version、内容/程序 digest、依赖锁和执行配置承担，不把 `v1` 塞进能力名。旧标识符只在当前实现证据中保留到命名迁移完成，不作为目标名称继续扩展。

`remotion-project` 的来源至少包含：文件集合及逐文件 digest、入口、Composition id、props/schema、固定资源清单、依赖锁、输出约束和执行摘要。预览与制作对同一来源 digest 使用同一固定结果；修订只使受影响生产结果失效。需要独立精修的重要文字、字幕和音频仍优先保留为原生对象，不把整片烘焙后谎称内部可编辑。

## 3. 渐进式创作工作流

绑定 Skill → 在同一普通 Chat 工具循环按需读取方法/预览、采集和准备规范资源 → 多次写入同一服务端工作草稿 → 最终完整校验并经唯一写口保存 → 完整分镜与按需局部 Scrub → 局部反馈/修订 → 既有授权与固定生产。

镜头卡、sequence、demo 是创作资源，不是强制阶段或执行注册表；固定模板由代码展开，自由创作逐完整实体写入，Generator 在目标 Clip 范围内进行有界代码创作和预览纠错。作品出生后，后续修订与 worker 不依赖 Skill 重新创作。

`list_skill_shots` / `read_skill_reference` / `read_skill_demo` / `get_skill_preview` 保留为有 owner/路径/文本/媒体边界的包读取能力。模型可见工具按当前绑定 Skill、活动草稿、保存版本、Output 与真实制作意图逐轮投影，不把全部视频 schema 和无目标修订工具同场发送；执行端权限和状态校验不变。

保留完整工具结果按 call id 回传、owner/来源/几何/唯一写口、总预算、取消/失败真实性、制作与费用授权；设计失败不显示成功，不虚构零消耗，不自动重买设计。局部 schema/语义错误只修目标范围，禁止 fresh-design 整片重交；未保存工作草稿不冒充作品版本。具体协议、文件级删改和验收归 [创作循环合同](composition-authoring-context-convergence.md)，视觉质量与原生可修要求仍归 P6+P7。

## 4. 既有基线与必须保留的欠账

以下是后续施工的起点，不是已完成范围的扩张声明：

- A 的最小 Composition/CompositionVersion、SourceSnapshot、时间/对象/动画与 video-spec 基座已收口；完整能力不能由最小基座推定。
- B 的网页、MG、混合实拍、原生图形、受控程序、单图生成、旁白与限定时间编辑已有各自真实旅程；完整 B 未封板。通用时间内核最新修复、temporal_revision/speech_edit_refusal、过期 base_ref 的代码归 P5，真实 Chat 复验归 P6+P7。
- C 的原始外部包持久化、owner/幂等/不可变、Strict/Adaptive 与 held-out 领域切片已有证据；统一 picker/chip 的代码欠账归 P1/P2/P5，正常授权计费、刷新、移动端和恶意包旅程归 P6+P7。
- SFX 搜索、导入、落轨和公共 Activity 已有用户实测；浏览器试听、刷新回放、音源/输出偏移、完整响度与局部修订复验归 P5/P6+P7。
- 当前单组件 component 接缝已落码但 bake 默认关闭且未验收；不继续按单组件扩展，完整工程归 P3。
- NarrationAlignment 已有新 TTS 最小闭环与真实词锚；已有录音、worker 恢复、READY 不可变、失效规则和完整套件归 P5/P6+P7。
- 十六个原生 Preset 已有代表动态、局部修订和共享 evaluator/Remotion 对照；独立原生 PreviewAdapter 已接通并通过当前浏览器复验，完整连续视听仍归 P6+P7。
- 网页采集批 1 已将 `capture_web` 公开输入收敛为通用 CaptureRequest，服务端自动补 baseline/scale/血缘，支持有界集合、共同 blank plate、普通/透明元素纹理与逐 output 部分成功；CapturePlan 仅留内部 worker/provenance。既有 selected、before/after、plate/cutout 的真实 shadcn Output 保留，连续看片、独立试听与完整检查归 P6+P7。批 2 的 `page_script`/任意 JavaScript 明确未实现；本批真实 Chat 素材采集与首稿验收仍待用户执行。
- Home 当前已有四产品主 Tab、八应用子 Tab及五张新链样片，其余应用为空态。网站/产品宣传下除 AgentVeil 外，新增 OxValue product-evidence Output `73258a3a-0b16-416b-8a61-d256664f0a0f` 与 energy-arc Output `a98d24e9-c100-4646-94f9-4424c30ccd57`，均绑定 `promo-video@1.0.0` 和同一默认预填，不固定 arc。文字动画 Project `e92babc3-2dab-4876-a31b-ce0e31667d67`、产品宣传 Project `b8b20d17-28eb-4c60-8656-d937f2593f56`、知识讲解 Project `0d6104fd-05d0-4029-a1e8-9c193450495e` 及新增两片仍待用户连续看片、实际试听和公开发布判断；知识片标题/Generator 拥挤、product-evidence 前两幕重复与 energy-arc V1 深色字幕底未关闭。
- 全新模拟知识文字稿链 Project `e9b1bcdd-17a0-4ff5-8890-00a52b30ef1e` 已取得独立 Run/READY/版本/Output；首版拥挤、历史 narration 用量措辞偏差和完整用户视听保留，不改写历史消息。
- 口播指定真人 VIDEO 与 SourceSnapshot 字节仍为 NoSuchKey；不用替代素材绕过，恢复或新素材与对应制作归 P6+P7。
- 当前完整 API/Web 的历史通过数不代替当前工作树复证；`test/core`、完整真实旅程和 Web/render 检查统一归 P6+P7，P0–P5 不分散运行。
- 证据继续留在 `artifacts/video-project-b/`、`scratch/c1-external-skill/`、`scratch/d5-category-anchors/` 与 `scratch/dev-supervisor/`；目录名是既有证据身份，不是后续批次名称。

## 5. 依赖、并行轨道与批次

当前可并行：**P1 PackageReader ∥ P3 完整 Generator ∥ P4a 包内容**。P1、P3、P4a 全部落码后，合并执行 **P2+P4b+P5**（Director、包注册与全能力修订）；再进入 **P6+P7**（集中测试、真实验收、Renderer 与样片）。最小 Scrub 与旧 Film 清理已提前落码，不表示 P6+P7 已验收。后续保留 P9 旧 Clip 承接与完整 Inspector；它们不与完整 live 矩阵混作已通过。

并行文件边界：P1 只动 `app/skills` 的读取/持久化接缝及必要 SkillVersion 迁移；P3 只动 Generator、Director、制作准备与 `component-runtime` 相关代码；P4a 只新增 `app/skills/promo-video/` 内容。并行会话不改共享 PROGRESS/合同，由主会话依据报告统一收尾；确需越界时先停下报告，不复制第二实现。

### P0——命名迁移与统一包合同

**范围**：

- 跨栈完成 `GeneratorObject.runtime`→`GeneratorObject.producer` 与 `draw-2d` / `remotion-project` / `image-generation` 重命名；更新 schema、工具、prompt 和现行文档。只改 Generator 这一字段及旧 producer 值，不全局替换其他 `runtime`，不新增或改写测试。
- 新写口只接受/产生新字段与新 id；既有不可变 CompositionVersion 只在现有读边界做最小旧名映射，不改写历史内容、content_digest、skill_provenance 或 Output 血缘，不另建兼容框架。
- 登记六类 Skill 包资源、十类目录与 `promo-video` 命名；不建立 ShotRecipe 层，不在 P0 把尚未实现的 `promo-video` 注册成可选能力。

**出口**：现有消费者的新旧字段与 producer 映射、保存/设计/修订/制作调用链均已改齐；旧名无活跃写口，历史 digest 不变。只做静态自查，不写或运行测试；真实验收归 P6+P7。

### P1——统一 PackageReader 与静态索引

**范围**：

- 实现内置文件系统与外部 SkillVersion 的同构只读 PackageReader。
- 校验六类资源、路径、owner、版本、digest、大小与数量；外部媒体使用内容寻址存储并保持来源身份。
- 从卡片与媒体 manifest 生成/读取静态 library index；index 不携带执行地址，不成为运行期注册表。
- 新模块、表或认领源按实际新增情况登记 MODULE_ARCHITECTURE；能用现有表与存储完成时不新增表。

**代码出口**：内置与外部来源共用同一读取接口，路径、owner、digest、大小与数量检查及失败分支接通；不做真实包验收，归 P6+P7。

### P3——完整 Remotion 工程 Generator（当前可与 P1 并行）

**范围**：

- 将当前单组件来源扩为完整 `remotion-project`：多文件、共享 helper、Composition 注册、内部时间线、typed props/schema 和固定资源。
- 隔离 runner 使用审核后的依赖包与锁定版本；禁止动态 npm install、未声明依赖、网络、业务文件、DB、调度与计费。编译/执行超时、输出字节、进程回收和渲染成本均有界。
- 上游预览与正式准备按 digest 复用同一 MP4/PNG；最终 video-spec 只含普通固定媒体。
- Remotion 许可、能力与成本结论并入 P6+P7 的统一验收，不另跑一轮付费验证。

**代码出口**：多文件工程来源、依赖锁、隔离 runner、digest 复用、修订失效和固定媒体编译链接通；不执行真实生成/渲染，真实预览、Output 与权限验收归 P6+P7。

### P4a——`promo-video` 包内容（当前可与 P1/P3 并行）

**范围**：

- 只新增 `app/skills/promo-video/` 的 `SKILL.md`、references/shots、references/sequences、demos 与可选 template 内容；十类只按真实代表需求填充，不镜像外部 124 张卡。
- 至少提供两种可替换 arc 起点，支持网站、文案、图片、真实视频、品牌和声音输入的导演意图；arc 只是首稿起点。
- 为实际引用的代表镜头提供原创、或许可明确且保留 attribution 的参考 demo 与依赖说明，不执行外部参考代码，不制作占位预览。
- gallery 静态索引和 Director 接线等 P1/P3 就位后由集成批完成；真实媒体与 Home 上架归 P6+P7。

**代码/内容出口**：包内引用、路径、镜头 id 和模板起始结构静态一致；不注册活跃 Skill、不改 Home、不制作样片。

### P2+P4b+P5——Director、promo-video 与全能力修订集成

**前置**：P1、P3、P4a 全部落码。合并这些批次是因为它们共同修改 Director、Chat tools、设计/修订参数和同一作品写口，不宜并行或重复交接。

**范围**：

- 在普通 Chat 工具循环接入 P1 只读工具，让模型按当前任务选卡、读卡、定位预览和读 demo；统一调用/墙钟/上下文预算，嵌套重试不刷新总预算。只有当前消息绑定 Skill 时才投影包读取工具。
- 完成 promo-video 的静态 library index、包绑定、注册、统一素材分配与工作草稿创作；从产品真实内容提取视觉 tokens，使用多个 arc 与可用 Generator，不把固定骨架或中间 Direction 当终身结构。
- 开放 arc 重排、场景增删、镜头替换、素材角色调整、Generator 新增/替换及声音修订；局部修改保持未改范围，开放重稿生成同一 Composition 的子版本。
- 接通外部 Skill 的渐进读取、创作、修订与 Output 代码路径。外部 scripts、allowed-tools 和普通 TSX 引用均不授予执行能力。动态 Skill 的显式 Generator 声明见 [顺序创作 §6.3.1](sequential-video-authoring.md#631-动态-skill-切换与删除)。
- 接通并静态核对通用时间内核、过期 base_ref、SFX 回放/导入/局部音频修订及 NarrationAlignment 的已有录音、恢复与失效规则。
- Home 新入口仍等真实链验收后切换；旧 launch-film 的既有绑定和 provenance 不改名、不漂移。

**代码出口**：内置/外部 Skill、完整 Generator、多个 arc 和全部已声明修订共用同一普通 Chat 循环与 Composition 写口；权限、grounding、授权与费用规则不变。真实 Chat、held-out、恶意包、计费和回放验收归下一批。

### P6+P7——集中测试、真实验收、Renderer 生产门与样片

**范围**：

- 在整个 promo-video 创作链接通后集中补测试：只覆盖真实用户旅程与核心 API/DB 合同，包括新旧命名读兼容、唯一写口、PackageReader 权限/digest、渐进读取、完整工程来源与 renderer-neutral、外部 held-out 和 arc/局部修订。
- 按实际改动运行 `test/core`、当前 `JOURNEYS` 与 Web/render 检查；真实付费调用在本批统一授权和执行，不在施工批分散烧钱。
- 同批完成 Remotion 许可或替代实现结论，覆盖最终 Renderer 与上游 runner；完成能力矩阵、golden fixtures、动态帧/音轨对照、失败闭、PreviewAdapter 和真实渲染成本测量。不支持能力在 Start 前暴露。
- 为宣传视频制作少量不同 arc 的强组合样片；另以 Repurposer 自我介绍视频综合验证 Chat/Skill、外部 SkillVersion、原生对象和 Generator 的创作与修订，不伪造工具、耗时或执行结果。
- 对现有文字动画、产品宣传和知识讲解样片完成用户连续看片与实际试听；口播先恢复指定素材或取得明确授权真人素材。收口 SFX、Preset、CapturePlan、词锚、回复事实、刷新回放和共享查看器。
- 用户明确授权后才逐张公开上架；内部预跑、空态和机制证据不冒充公开 Gallery 通过。

**出口**：测试、许可、能力、预览、成本和失败恢复均有当前证据；机制、动态画面、实际听感、回复事实与 Home 入口分别验收。未通过不得生产发布，未运行项保持开放。

**当前验收状态与阻塞**：当前测试与 Chat/Director 边界见本节末尾专项验收；本轮未重跑完整 API/Web/render/video-spec 套件，不沿用既有全绿读数。共享 Remotion 包已有 macOS Seatbelt runner 真实 bake/完整解码 30 帧 MP4 证据；本次 dev 重启后 render `/health` 实际为 `enabled=false / isolation=disabled`，根 `.env` 的开关未传入 render，当前 Generator 环境未开放；2 秒 / 640×360 / 15fps 作品的实测墙钟为 5.395 秒、51,539 字节，重复 bake 哈希一致。8GiB RSS、512MiB temp、24MiB 输出、超时清理、对抗输入与固定图片证据在 `scratch/final-promo/`。PreviewAdapter 已把只读精确版本的局部 Scrub 编译、pending_media、schema/能力/provenance/scope 准入和按需 ACK 接入既有 storyboard 路由；默认 Storyboard 不返回动态 spec，制作前整片预览永不提供。source-aligned 派生字幕可直接预览，其余未完成的派生媒体仍显式 pending。首稿 review-first 以 Markdown 分镜为主，只有动态需求需比较/澄清、局部修改核对或用户主动看特定效果时才附局部 Scrub/代表帧；通用效果示例走 Preset 候选，不新增第二 Player 或 look 座位；pending 媒体不伪装 ready。运营主体的 Remotion 实际许可配置仍是上线条件，当前进程 runner 开关也需在部署环境中显式配置。当前 `JOURNEYS` 尚未运行。真实 Chat 已保存并呈现 Oxvalue Version 3（`eba97cfa-8e49-4771-bf6e-2adc45d58dea`，5 幕 / 78 秒）；AgentVeil 当前为 V6 `05e27b89-8ffc-4c86-baa4-6bb6aed144fd`（digest `def49890dc86708389e1a2dd2d017a97105cf0d690a660fd00f3168a3e548544`，66 秒五幕），V1 `579a53b6-ec64-4ca9-b72d-119278c170e6` 及原 digest 保留，V2–V6 未新增 Run 或视频 Output；Zymix（`c90614ef-2ccc-4e23-89da-58caa6438425`）尚无版本，恢复时必须先查服务端回合与版本终态，不能直接重发。Oxvalue Run `8bfc2d50-2b24-4c3c-b32c-99df90526fad` 已由用户通过 upload-only 恢复完成（`upload_retry_count=1`），Output `35a06f0a-828e-4798-8636-23aba564ee8f` 已有 MP4，seq 103 的恢复交付只引用该 Output；只读浏览器硬刷新实测显示 Worked 收据与视频卡，无活动 shimmer；另已修复服务端计数先到、Chat 信封再到时客户端重复递增恢复次数的竞态，同 Run 当场恢复仍待复验。AgentVeil Run `71dec983-8e80-41af-8491-6fed3f307cdb` 因 TOS 素材 staging 的 `UND_ERR_CONNECT_TIMEOUT` 全败，且其 `run_failed` 通报的 LLM 调用随后失败，未落通报行；代码已加入 staging 瞬态传输的有界重试和失败通报的确定性事实兜底，新增定向覆盖尚未运行，不能据此宣称该 Run 已恢复。MiniMax 结构化 generate/stream 与 Chat ToolLoop 的工具调用均显式发送 disabled thinking；CapturePlan 无计划诊断上限为 600 字。promo 当前已由普通 Chat 按需读取 Skill/准备资源，并通过多次完整实体写入维护同一服务端工作草稿，最终一次完整校验与落版；条件工具与旧整片重交协议删除已落码，既有定向测试不代替当前核心套件，且尚未完成真实 Skill 旅程验收，不再生成构造 Op、中间镜头草案或完整方向对象。冻结来源修订不重新采集，paired cutout 的布局由服务端按冻结元素、plate 实际 layout/fit 推导，显式 cutout 坐标与不可见 draw stroke 会被拒绝，Shape opacity 动画落到作者指定绝对透明度。镜头库已有 `evidence-push`、`verified-figures`、`action-focus`、`brand-emergence`、`next-step-lockup`、`benefit-cuts`、`kinetic-statement`、`layered-interface` 八个真实 MP4，静态索引指向实际媒体，不执行参考 TSX。既往定向读数不替代当前 `test/core` 与真实旅程复验。AgentVeil V6 的 run-less 精确版本 MP4 已完整解码 1980/1980 帧，66.048027 秒音轨可解码、RMS −18.141 dBFS、Peak −1.432 dBFS、无截幅；采样帧证实橙色路径从左向右显现，同源 blank plate 上真实 APPROVALS cutout 入场且对齐，未改场景沿用 V5 已检查帧与 V5→V6 唯一 Shape paint diff。V6 frames 747/1188 与 Oxvalue 的原生文字覆盖网页标题、右/底边裁切和 caption panel 碰撞逐项对照，采样帧中文字分区、完整且在边界内，结构阅读窗逐项通过。AgentVeil V6 的连续全片视觉与实际试听由用户终审，结果尚未返回；Zymix MP4、完整浏览器/帧/音轨/联系表和独立终审仍待完成。`journey.py`、`journey_browser.mjs` 与 `media_verify.py` 是当前可恢复驱动器，语法检查通过不等于作品证据。P8 的旧 Film 删除与 P10 的最小视觉 Scrub 已落码但未验收；P9、完整 Inspector、部署、发布与公开 Gallery 仍未完成。

**当前能量弧与配乐实施状态**：`promo-energy-arc` 已加入包内 arc 选择，含四段能量分配、真实状态/证据门、停顿与 seam 规则，以及六个 Shotcraft 核心镜头的卡片、逐字节 TSX/helper 参考、静态索引和 Apache-2.0 attribution；它们仍是只读创作参考，不是运行时镜头库，只有两张真实静态海报，未宣称四个无预览镜头具有动态证据。Motion/视觉保真必须由实际 Generator 代码、代表帧与完整动态验收证明。本地 Music 候选、下一轮序号选曲、prepare 冻结、music/effect 分轨及实时/历史 receipt 已落码，builtin_promo_skill 已扩为首稿后试听、下轮选曲、钉选曲后版本制作；Shotcraft 五首对象已导入，公开平台候选库已 reconcile 为 Tech House / Tonight / House Vibez / G Eazy NBA type / Cat Walk；旧 Corporate Drive 已删除，Calm Academic 与 Inspiring Vision 因历史 Output 引用按守卫转为私有，不再进入候选，用户自有音乐不受影响。上述新增真实试听与制作均未运行；`builtin_promo_skill` 已补真实增量草稿链、默认零整片预览与可选局部 Scrub 断言但尚未运行。OxValue energy-arc V1 的技术交付虽已完成，但用户随后明确判定视觉/声音验收不通过：全片没有音乐、收尾 CTA 间距过紧、hero 重要文案左侧被画布裁切；源版本证实 36 条轨道全为 visual、CTA 为 400×62 盒配 28px/1.2 行高文字、hero note 继承网页相机 1.28× zoom 与 rotateY(34°)。此前将左侧缺字解释为近景构图的结论已撤回。共享 promo/Skill 规则已改为宣传片默认克制配乐（用户要求无声/无音乐除外）、无旁白不等于无音乐、重要屏幕文字不得继承网页运镜或被裁切、控件文字间距纳入审片；reviewer 对重要文字裁切和用户要求配乐时的全流静音不得再以“刻意构图”或 spec 未声明音频预期放行。真实 Chat 的 review_video → revise_video 链已保存并呈现 V2 `926b751c-2fbe-4adc-8b40-087360aa3a8c`（digest `71133420892ff2255fcc737b92103cbbd82ef00266c8f44d718913b4c6ffb6f8`），未新增 Run 或 Output。精确差异只含 `c-hero` 的 `src/Hero.tsx`、收尾 CTA shape/text 的共享盒与 shape 圆角及新增原生 music Track/Clip：CTA 从 400×62 调整为 520×100，hero note 移出网页相机树并固定于屏幕空间，Calm Academic Snapshot `38c3f5ed-8b14-5d0e-92a8-918c0d16a4c6` 以 `0..3144000` source range 覆盖全片、gain −10 dB；其余既有 Scene、Clip、来源、时间、动画、转场和设置均由保存后断言确认保留。真实拒绝 payload 的离线回放还修复了 tool observation 首次送达前被折叠、音频 `clip_source` 缺失及实际模型数组/数字字符串方言；新增定向测试尚未运行，不作套件通过声明。V2 错选旧库 Calm Academic，未进入制作。随后严格按真实用户边界发送两条自然语言 POST /chat：第一轮只展示五首候选，第二轮以“选刚才的第一首”完成 select_music → prepare_video_materials → revise_video；未向模型提供内部 base_ref、Snapshot id 或 tick，harness 未直写业务数据，数据库只读核验。V3 `b836ab97-0c1d-4db0-ac53-9cd7d19cb275`（digest `db5d0af225a70fe98078406747a6fa0cd25a1fcb6eed764c1503e441819c290c`）已保存并呈现，选中 Tech House，冻结 Snapshot `0dd8ad0e-aff8-5453-a222-aea75a2a0483`，source range `0..3144000`，未新增 Run/Output；系统 delta 与独立 diff 均只有 `c-music-bed.source`，V2 的 Hero/CTA 和其余内容保持不变。V3 的实际画面、音乐混合、后续授权制作与连续视听验收仍待完成。

**Chat/Director 当前验收边界**：公共上下文由 `tools/project_context.py` 在每次模型 continuation 前从现有表刷新；当前作品完整内容、网页正文、素材与冻结来源带明确身份进入 prompt，过大资源显式 omitted。ToolObservation 的 call/turn/project 生命周期已接通，项目级折叠须确认完整资源键。asset-less 派生快照保留出生项目，设计失败后的下一回合仍可读；Skill 成功读取以 Activity/Message receipt 按不可变包和资源跨回合合并，实际媒体只在当前真实读取后附着。原生文字保留完整文案与合法字号；权限、来源、时间、显式能力与有限资源上限仍校验，保存只走唯一写口。

创作收敛的本地实现、工具批执行/超时及验证结果统一归 [收敛合同 §6](composition-authoring-context-convergence.md#6-当前状态)。

#### 工作草稿与创作反馈合同

- `design_video` 已改为完整设置、来源或完整实体的增量写入：同一个服务端工作草稿跨调用/回合保留，所有内容变化先经 `save=false` 合并；最终 `save=true` 只提交已存在的 `draft_ref`，完整校验后经 `apply_composition_edits` 一次落版，不再同时携带新内容。`fresh_design`、只读被拒候选引用与整片重交恢复协议已删除。本批已落码，待用户验证。
- 新首稿通过多次 `design_video` 写入 ConversationContext 中的服务端工作草稿，每步只校验所属范围；文案引用校验汇总全部不匹配项，返回自然字段路径、引用文字、line_id 和对应原生 TextObject 候选，修复只涉及报错范围。已保存版本仍由 `revise_video(base_ref, 完整实体)` 局部修订。
- 条件工具、预览反馈、分层校验、文件级 Keep/Change/Delete 与验收全部归 [创作循环合同](composition-authoring-context-convergence.md)。不新增 Draft 表、构造 Op、字段 patch、多 Director 阶段链或第二生产链。
- 旧 direct-Composition 链既有真实保存/制作成功，也有三次写入后无版本的失败；单次成功不能证明首稿稳定。当前先完成新主链的真实用户旅程，再继续本批其余 Generator、连续视听、完整 JOURNEYS、runner 环境与许可验收。

#### P6+P7 视觉质量代表镜头施工

当前先以 OxValue 真实估值卡完成一个约 6–8 秒的代表镜头，再扩成完整宣传片。四批是 P6+P7 内部的顺序切片，不新增作品根、生产链、运行期镜头注册表或 renderer 分支；保存、可播放和文件交付不等于视觉验收通过。

代表镜头的固定动作弧为：整页建立场景 → 聚焦并压暗周围 → 推向真实估值卡 → 卡片独立抬升并短暂悬浮 → 真实指标逐项展开 → 卡片归位 → 稳定阅读停留。£18.7m / 94% / High / 03 等内容必须来自冻结来源；不得用整页缩放冒充主体运动，不得用虚构中间数字做滚动。重要新增文案保留原生身份，网页原有文字仍属于真实截图像素。

**视觉质量批 1——运镜语义与网页文字安全区**

- 工作草稿使用既有网页 focus 运镜、对象 Animation 与几何校验；`push_in` 只表示无目标的整页轻推，有明确元素目标时使用 `motion="focus"` 与既有相机关键帧能力。描述与执行不一致、缺少冻结元素或越界的候选在唯一写口前拒绝，不重建一套 promo Direction。
- 在 `editing/grounding.py` 增加纯几何映射，将冻结 view 的元素盒按实际 base layout/fit 映射到归一化画布。新原生 TextLayer 必须完整处于画布内；普通网页 view 上不得覆盖已采集的可见 `heading/text/button`。blank plate 只豁免被正式移除的目标区域，其余文字仍参与避让；不解析 `visual_description` 代替几何校验。
- 校验诊断指出场景、layer 与冲突元素，并进入现有一次汇总修正； Shape 出血、非目标装饰和既有不可变版本不在本批重写。无真实元素盒时不发明坐标，最终可读性仍由成片帧验收。

**当前实施状态**：批 1 已落码；2026-11-06 指定七座验收测试在最小修正后为 183 passed，包含运镜冲突、文字边界/网页碰撞与阅读窗覆盖。真实同源 AgentVeil 参考已渲染并抽帧；OxValue 新项目仍在有界 Chat 验收，不能以纯几何通过代替成片文字、换行和字体可读性。
- 出口：`focus` 沿用既有真实元素取景，非法组合在保存前被拒绝；OxValue 当前出现的中文压英文标题与文字越界形态有确定性拒绝覆盖。纯函数测试归现有 promo/capture 测试座，不新增事故编号套件。

**视觉质量批 2——真实网页资源与 Generator 原生层**

- 在 `editing/sources.py` 保留窄的 web-view 派生 Snapshot 注册，由普通 Chat 的 `capture_web` / `prepare_video_materials` 对每个成功视图调用；失败 output/member 只进入有界 issues，不撤回其他派生。完整视图、共同 blank plate、普通元素纹理和透明 cutout 分别注册为普通 `kind="image"` Snapshot；identity 包含 `web_snapshot_id + view_id + view_digest`，storage/digest 指向真实 PNG，`meta` 保存来源 Snapshot、通用 state/output/target/member 血缘及内部执行配对。透明 cutout 继续派生全画布固定资源。
- 派生图片进入本次 Director 的精确资源清单与最终 facts，复用现有 `RemotionResource`、权限、digest、bake、缓存和恢复；不直接把 `kind="web"` 的清单字节放行给 `_fixed_resources()`，不给资源 schema 增加第二套身份。cutout 分辨率不足以支撑输出特写时失败或重新采集，不把低清放大称为高清。
- Generator 场景与重要文案逐步写入工作草稿；定向修订提交完整所属 Track/Clip：GeneratorObject 承载受控视觉程序，独立 TextObject/ShapeObject 保留原生位置、时间窗与可精修身份。来源引用经 `copy_references(snapshot_id, line_id)` 确定性回填，video-spec 不变。只改原生文字不得使 Generator digest 或固定媒体失效，修改 Generator 不得重写未改原生层。
- 本地真实制作要求 API 与 render 同时开启 `COMPONENT_BAKE_ENABLED=true`，并通过 `/health` 证实真实隔离。保存版制作前的有界 Generator 预览复用同一 runner/digest 缓存，不是 Output；正式制作仍从授权后的 `produce_video` 开始。当前仅有 macOS Seatbelt 隔离，本地样片通过不等于其他部署环境已开放。

**视觉质量批 3——参考方法、真实预览与声音节拍**

- 只新增一个真实消费者 `interaction/spotlight-card`：原创 demo、固定 fixtures、真实 MP4 与由该 MP4 抽出的带时间标注 timeline JPEG，登记 `library.json` 和适用的 sequence。卡片写明 plate/cutout、共享相机、抬升/悬浮/归位、高度阴影、相机锁定后的原生指标与静止阅读段；外部参考源码仍只读不执行。
- 方法与真实预览按当前任务需要读取并复用成功事实；本代表镜头显式要求查看 spotlight 参考，须保留真实读取证据。旧多 Director 研究/提交门已删除，不作为目标工作流恢复；现有 owner、媒体大小与总用量边界保留，不另建 loop。
- 本次代表镜头的 provenance 必须证明指定预览被真实读取（有可用媒体时 `media_files>0`）；现有采集工具取得真实配对 plate/cutout，正式 Composition 包含 Generator 与独立原生指标对象。不以必须生成 ShotDraft/Direction 为验收目标。无预览的外部包记录真实不可用事实，不伪造读取。
- 声音复用现有 SFX 搜索、固定 Snapshot 与 Composition 原生音轨；只给锁定、抬升、指标展开、归位等主要动作选点，不按配额堆音效，不强制旁白。

**视觉质量批 4——逐镜动作复核与样片终审**

- `ReviewVideoArgs` 增加精确的可选 `motion_scene_id`；`tools/video/review.py` 对该 Scene 抽取有界的有序帧序列，报告记录实际场景、时间窗、采样间隔与 `motion_reviewed_scene_ids`，缓存身份和 review schema 同步升级。未取动作序列的场景仍明确未检查连续运动；reviewer 只能依据实际序列判断该镜头的动作阶段与衔接。
- 自动音频检查继续区分 PCM/RMS/peak 与主观听感，不把信号存在写成音画同步或通过试听。整条样片必须连续看片与实际试听；发现问题后走 `revise_video` 形成新版本并复核确切 Output。

**代表镜头与完整片出口**

- 代表镜头：真实卡片独立抬升，plate/cutout 全程对齐，五个动作阶段可辨认，真实指标准确，重要新增文字原生可修，零遮挡/越界/明显低清放大；只改一条原生指标时 Generator digest 与固定媒体不变。
- 完整片：代表镜头通过后，再组合原生开场、产品证据、核心技术/能力、治理流程与原生收尾；时长服务内容，不用长静置截图填片。完成连续看片、试听、一次真实 Chat 局部修订与重新交付后才称视觉样片通过。
- 测试只归核心 API/DB 合同与宣传视频真实旅程：纯几何/资源身份/时间窗、唯一写口、权限、renderer-neutral、重试复用，以及 `builtin_promo_skill` 的 plate → Generator + 原生层 → 制作 → 动作审片 → 只改文字不重 bake。prompt 改动由相关真实旅程验收；模型、采集、声音与渲染分别登记，不以静态检查代替。

**批 2 当前实施状态**：批 2 已落码，现有派生身份/幂等/权限、资源拒绝、原生层、阅读窗、编译与两类修订测试通过。本轮真实采集发现旧 cutout 为不透明紧裁切，不能直接当全画布 alpha 使用；现已在采集端暂停 JS/canvas 状态、隔离目标并取得 RGBA，在准备层以配对目标盒无缩放补齐透明全画布，再登记有原裁切/配对 digest 血缘的普通 image Snapshot。API/render 已开启 COMPONENT_BAKE_ENABLED，render 健康检查与真实参考 bake 证实 macOS Seatbelt 隔离。真实 AgentVeil 原图与 plate+cutout 重建的平均通道误差低于 0.001/255；OxValue 单镜头与完整 energy arc 均已完成正式制作；实际文字修订、program_digest 与固定媒体复用仍待完成。

**批 3 当前实施状态**：原创 spotlight-card 已用重新采集的同状态 AgentVeil view/blank plate/真实透明 cutout 生成正式内部参考，fixture 已替换为实测几何。MP4 为 1920×1200、30fps、8 秒、240/240 帧完整解码、静音，SHA-256 `c51d18cf0f18d8cca44ba863920cf6fc03bb1368ed12a6e4ef39f4ee87deb372`；timeline 从最终同一 MP4 的 17 个时间点抽取，SHA-256 `41a73dc4ef9fd206823798186e60827ee235b1ac015e0509eeea849d8e086fcd`。library 已登记真实路径、mime、digest、byte_size，JPEG 为默认预览、MP4 可显式读取；卡片 digest 与旧 previews=[] 测试已同步，无公开 Home/Gallery 上架。末尾 204–239 的源动作恒定，解码帧平移估计为零，编码像素噪声均值约 0.00824/255；有序抽帧不冒充连续看片。OxValue 真实 Director 已读取 JPEG 与 MP4。验收暴露“卡片已读但预览未补齐、读取窗口耗尽后重复提交”问题：最后研究代明确列出缺失预览并要求批量读取，预算不足立即停止，不降低预览门或增加总预算；两项纯函数回归通过。

**批 4 当前实施状态**：`ReviewVideoArgs` 已增加与 `at_seconds` 互斥的可选 `motion_scene_id`；复核仍只接受 owner 可访问的确切完成 Output 及其钉版执行 spec，目标 Scene 窗口由该 spec 的 clips 汇总，缺场景、空/倒置/越界窗口明确拒绝。动作模式以约 2fps 抽取该 Scene 的有界有序帧，包含首帧和最后可执行帧，最多 16 张且极短场景不重复解码凑数；继续复用 PyAV、JPEG 边界、内容寻址帧存储、active clip/object facts 与严格 frame_id 引用。报告 schema 已升级，记录目标 Scene、实际执行窗口、解码后的首末采样时间/帧数/相邻间隔和 `motion_reviewed_scene_ids`；缓存身份同时包含确切 Output、实际视频 SHA-256、requirements、采样模式、当前 schema/checker 和动作采样元数据，旧报告不继承动作检查范围。reviewer 仅在实际有序序列存在时判断该 Scene 的动作阶段与内部衔接，有意静止阅读段和重复帧仍只是候选而非自动缺陷，其他 Scene、Scene 间转场、连续播放、主观听感与 AV sync 均明确未检查。现有 review 纯函数测试座已补参数/窗口、首末帧/短长场景/唯一性、实际解码间隔、报告范围、缓存与 reviewer 装配覆盖；本轮指定 review 纯函数覆盖已通过；修正了极短 Scene 抽取所有唯一帧、可容纳时按真实 2fps 间隔采样并包含末帧的取点逻辑，长 Scene 仍最多 16 张。真实 spotlight MP4/timeline 已生成并登记，详见批 3；OxValue 单镜头 Output 已有完整解码与独立浏览器播放证据，完整 energy arc 也已有真实 Output，但尚未调用其真实 `motion_scene_id` 复核。连续主观视听、局部修订后的复核与独立终审仍未完成。


**代表镜头当前状态：单镜头与完整片真实交付均已打通。** Project `2ef2e5c1-86c4-4013-bae6-b60fe11e769d` 的 V4 `0ff20eaf-833c-4315-b3ef-78bcc21023f7` 经授权 Run `c235865b-33dd-44c6-af14-4c3092f08ea7` 交付 Output `90760128-432e-4d32-b60e-5ff0d67ef0c8`；1920×1080、30fps、172 帧的 MP4 已完整顺序解码，独立 Chrome 播放至结束且零丢帧，关键帧已目视核对搜索锁定、斜侧推进、轮廓扫描、归位和最终 hold。该版去除了 data-URI grain，并以 CSS 暗场替代原 SVG mask，因此只证明运动结构与电影感复刻，不声称逐像素一致。证据在 `scratch/final-promo/oxvalue-spotlight-live-20261108/`。

完整 OxValue energy arc 的 Project `c83f9898-d97a-47d3-adbd-81c607080548` 已由真实 Chat 保存并完整呈现 V1 `3df54efb-88f2-436f-9bd5-b89451b5b359`（10 幕、36 轨、55 个 Clip、约 34.93 秒，Generator/Web/Image/Text/Shape），presentation ACK 已落库。用户明示授权的 Run `677dd94f-a131-471c-a8c1-3279904845ef` 精确钉住同一 V1/digest，交付 Output `6058cb85-226e-4ca7-a748-a380d615d0df`，没有改出版本。制作链暴露的旧 worker 资源预算、`staticFile` 常量引用过窄、pending 问题在工具接受前被结算三处共享问题均已修复：实际两张 hero 资源合计 4.533MiB，现行单资源 16MiB/单组件 32MiB 加载器接受；受控 `staticFile` 现允许字面量、props、变量与计算表达式，bake 在原始 digest 校验后仅改写临时执行副本，为直接调用注入按当前 Generator 资源清单精确比对的运行时守卫；未声明路径、遍历、URL、非字符串及别名/转交绕过继续拒绝，CompositionVersion 原始源码与 digest 不变；chat 与 plan path 都只在工具终态接受后结算 pending，parked interrupt 唤醒语义保留。本轮资源守卫改造后的 renderer 定向测试与 typecheck 未运行；既往定向结果不冒充本次新机制验证，当前 `test/core`、`JOURNEYS` 与 Web/render 检查未运行。

Home 精确 `promo-video@1.0.0` 提示词的另一 OxValue 项目 `9f7440f8-d552-4732-9763-ada09e8c5476` 已完成真实 Chat 制作与交付，但不是一次通过：首稿前经历实际 schema 修订，V1 初次制作被旧 `staticFile` 静态语法限制拒绝。机制改造后，新 Run `24d8838d-d9f2-48b6-8b7c-f6c9725e59ab` 精确钉住原 V1 `aa5a8f5a-0b52-475e-aee1-0399df0dc818` / digest `f117bcada541394a92bb679d725eb50af0cf56a35297dbe0d855d6d4439cf06d`，四个仍使用 `staticFile(it.path)` 的 Generator 原样完成 bake；改为字面量的 V3 未用于此次交付。Output `a98d24e9-c100-4646-94f9-4424c30ccd57` 由 trigger 消息 `24c82050-75ba-4bc7-85d4-d9c7d4da5478` 自有 `output_refs` 唯一引用。MP4 为 7,391,479 字节、SHA-256 `f9392d8712a8d3e83255a9ff5a1603418fe8dca3341086d20b23f4766487ec65`，1920×1080、30fps、42.5 秒，1275/1275 帧完整解码；Tech House 原生 music Track 覆盖全片，PCM 全程可解码，RMS −17.902 dBFS、peak −4.836 dBFS、零削波。25 帧联系表与六张全尺寸帧已目视核对，六幕原生字幕清晰，错峰升起和收尾飞入画面存在；有序抽帧不冒充连续播放、AV-sync 或人工试听。该历史版本的 `skill_provenance.skill` / `arc_id` 仍为 null；新写口的 arc 血缘规则见「工作草稿与创作反馈合同」，不回填旧版，也不以实际采用 energy arc 的创作结果冒充已有元数据。证据在 `scratch/final-promo/homepromo/`。

Home 原始提示词的新项目 `7386da2b-596e-496b-bb71-01768070ee9e` 已完成“只发送原始 prompt，后续仅回复可以”的真实 Chat 旅程。首轮自动选择 product-evidence、完成采集与音乐准备，但 `composition` 同时携带合法 `timeline` 和额外的 `item: [Track...]`，封闭 schema 拒绝，未保存版本；既有根级单 Track `item` 兼容不覆盖这个位置与形态。用户侧只得到无具体原因的失败文案，首轮约 12 分钟；第二次仅发“可以”后约 14 分钟保存并呈现 V1 `d05092fa-37bd-4f41-bedc-296371600a81`，说明可自恢复，但不能称为顺畅首稿。默认 V1 为 45 秒、7 幕、真实 Web + 原生 Text + Tech House，无 Generator；`role=caption` 实际是左侧说明段而非独立底部字幕条，全部文字背景为 null，`arc_id` 仍为 null。展示 ACK 后再仅发“可以”，正常创建精确钉版的 Run `049c46d9-5be8-418a-963b-dcb788302f57`，交付 Output `73258a3a-0b16-416b-8a61-d256664f0a0f`，trigger `output_refs` 正确。MP4 为 18,929,727 字节、SHA-256 `41356290a9eb80bfb3e78a6c0c6939b9e8dc61998d0de2b63ad919bd9008df2e`，1350/1350 帧完整解码；PCM RMS −17.852 dBFS、peak −4.088 dBFS、零削波。28 帧联系表与全尺寸帧确认无字幕背板，但画面主要是网页推拉，前两幕都显示完整首页，与首幕 panel 裁切意图不完全一致并有重复感；不冒充 energy-arc 视觉等价，也不以 PCM/抽帧冒充连续试听或 AV-sync。证据在 `scratch/final-promo/homepromo-default/`。

首轮失败的逐请求取证确认：实际只有两次内容写入，不是达到通用 12 轮上限。第一次 `design_video` 的 `composition.item` 是 19 条完整 Track；第二次按反馈用 `revise_video(draft_ref)` 重写 8 个 Scene 与全部 53 条 Track，53 条恰好是原 34 条 timeline Track 加 19 条错位 Track，但 working-draft entity merge 没有删除未知 `composition.item` 的操作，因此同一校验错误必然重现。`film_rejection_stop` 只比较工具/kind/detail，第二次相同签名即报 no-progress，没有比较已改变的 candidate digest。最终失败文案由 no-progress 代码拼装，不是模型对 `item` 的解释。重试保留原 45,720 字符完整工具参数、失败回执和修订要求，并附相同项目上下文；请求从 27 条消息变为 30 条，compact JSON 增加 55,320 字符（1,351,013 → 1,406,333），不是无成本的小上下文重试。模型面 prompt 与实际 wire schema 均未声明 `composition.item`；provider 原始响应已经携带该键，本地 parser/normalizer 未见注入路径。单纯增加重试次数不能修复上述保留草稿的确定性失败；`composition.item` 继续由封闭 schema 严格拒绝，不为这次模型错误增加专用字段兼容。当前代码已改为：schema 无效首稿只保留只读候选引用与精确错误，下一次全新 `design_video`；同/跨回合模型上下文不重复携带完整被拒参数；no-progress 增加 candidate digest 同一性判断，三次总预算不变。`arc_id` 的历史空值根因是直接设计 provenance 构造没有 arc 参数或已读 sequence 校验；当前首稿新增经当前包声明与完整读取回执校验的 `arc_id`，写入并继承到 `skill_provenance`，不修改历史版本。上述新协议与 provenance 改动已落码，当前 `test/core` 与真实 Chat 复验均未运行。

交付 MP4 为 7,276,373 字节，SHA-256 `42340b399f3924e1dad3a62ba9e3e989b0fa1217a4aa33b7c44eac9336ee1014`；1920×1080、30fps、34.933 秒，1048/1048 帧完整解码，输出检查零问题，静音音轨可解码。真实 Chat 首次打开与硬刷新后 Output 始终归属交付消息 `7e732d8f-3367-4572-90f5-58b16f1586bb` 并实际播放；独立 Chrome 到达 `ended`，1048 帧全部呈现、0 丢帧、0 损坏、0 stalled。联系表及 hero/breathing/core/climax/launch 全分辨率帧已目视核对，未见文字碰撞或意外越界；hero 左侧是近景运镜裁切，breathing 幕为有意留白。证据在 `scratch/final-promo/oxvaluearc/media-v1/`。

设计回合的 SSE 终态断言仍因 read 后 interim_prose 只叙述过程而未携带结果失败；版本与 storyboard 在断言前真实落库，恢复只读取持久化事实并补 ACK，未再次调用模型。该形态问题、连续主观视听、`motion_scene_id` 动作复核、原生文字修订、固定媒体复用与独立终审仍未关闭；有序抽帧和技术完整播放不冒充连续主观看片/试听。真实 OxValue 配对资源的 overflow 浮层裁切与透明/backdrop blur 重建差异仍保留在终审范围内，资源存在与文件交付不代表全部视觉质量验收完成。

### P8——新链切换、共享执行复核与旧 Film 清理

**范围**：

- 新链默认承接对应视频任务；注册表、prompt、Chat tools、Run 与 UI 的旧入口已关闭。该切换不代替 P6+P7 验收。
- 复核 render owner、并行写入、恢复、产物成员、fresh graph、lifecycle、授权、计费、交付和 Output provenance；保留有效安全与视听守卫。
- 显式删除无消费者的旧 Film 工具/schema、专用 prompt、validator、pending 信封、render family、依赖和失效 fixtures；共享能力先核对 Clip 与其他消费者。
- schema 废弃列/表走新的 Alembic 迁移，保留迁移历史；实际清库按既有授权核对目标与 dry-run。部署前核对 API/worker/render/web 版本并排空或取消旧任务。

**出口**：无新旧双写/双读或回退入口；设计、审阅、制作、交付、@修订与失败恢复重验，旧 Clip 与共享 Run/计费链不回归。

### P9——旧 Clip 高层能力逐项承接

**范围**：

- 在共同底座稳定后，按真实消费者逐项承接 reframe/crop、segments、ASR/caption/translation、dub、music、intro/outro 等旧 Clip 能力。
- 保留 ASR words、speaker_map、源窗、选段与 provenance；每项独立验证读写、渲染、真实旅程和费用，不把基础字幕/音频能力误称为整套旧产品迁移。
- 只有全部仍需能力都有等价承接后，才删除对应旧 Clip 实现；不以删完 Clip 为计划目标。

**出口**：逐项有能力映射、真实用户旅程和回退/删除结论；未承接项保持可用并明确登记。

### P10——Scrub 与 Inspector 精确编辑

**范围**：

- 在稳定 CompositionVersion、Clip/Object id、PreviewAdapter 与唯一内容写口上，先贯通一个明确版本、时间点、目标对象和真实属性。
- 连续调整只更新本地草稿；Apply 携带 base_ref 与完整所属 Clip/Track 实体形成一个新版本，保留取消、冲突、失败回滚和键盘可用性。
- 音频 Inspector 复用现有真实 WaveformPlayer；mousemove、seek、试听和调值不调 LLM、不建版本、不触发付费渲染。
- 旧消息钉旧版本，只有当前版本可编辑；多对象和更多属性按真实消费者后续扩展，制作前整片预览永不开放，不建设完整 NLE。

**出口**：至少一个视觉属性完成本地预览、Apply、版本血缘、冲突与刷新验收；Chat 修订不被强制迁移到独立编辑器。音频属性与完整 Inspector 仍是后续范围。

## 6. 参考产品的可学习边界

video-shotcraft 的 Motion Workbench 是交付后的浏览器微调工具，不是 Skill 加载器。可学习其稳定镜头/clip 身份、typed props/schema、逐镜修订和 Preview/Render 一致性；本计划不复制完整 NLE，也不在交付后强制打开另一编辑器。精确 Inspector 归 P10。

社区存在 Claude + Remotion Skill，可学习其“生成 → 渲染 → 查看实际帧 → 修复”的闭环和 Remotion API 创作知识；它不是 Anthropic 官方的「Claude Motion」产品，不改变本计划的权限与版本边界。

## 7. 新会话接手规则

1. 先读 CLAUDE.md、PROGRESS §0、VIDEO_PROJECT §0/§4.3.2/§7/§8，再读本合同 §4 与当前批次；不通读全部历史证据。
2. 核对当前 HEAD、工作树、并行归属和前一批代码出口与未验证边界；禁止 reset/checkout/stash 制造干净基线，不转信其他会话的基线绿。
3. 一个会话只实施一个合并批或一个已标记的并行切片，并遵守 §5 文件所有权；发现前一批欠账时登记并报告，不为赶进度跳过安全、授权或计费约束。
4. P0–P5 不擅自安装依赖，不写或运行测试，不执行外部包，不调用付费模型/TTS/采集/渲染，不上传 demo 或部署；每批以静态调用链与明显缺陷自查收尾。P6+P7 再按统一范围补测试，并在取得当批明确授权后执行真实付费验收与样片制作。
5. 并行切片只返回施工报告，不改共享合同或 PROGRESS；主会话统一更新本合同、PROGRESS §0 和命中的现行事实源。未运行项明确写未运行，不新增会话编年史或归档副本。
