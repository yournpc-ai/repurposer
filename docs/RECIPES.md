# RECIPES — 配方与 Home 货架

> Status: 当前规范（2026-10-27）。本文描述配方、Home 货架及其兑现能力的现行边界；样片与入口的最新验收状态归 `tasks/home-creation-entry-refresh.md`，排期归 `PROGRESS.md`。
>
> 配方是提示词，不是 mention、模板编辑器或隐藏执行通道。点击卡片只预填 composer；用户随后编辑并发送，才进入唯一的 `POST /chat` 意图面。

## 0. 当前事实

- 服务端 `app/pipeline/recipes.py:RECIPE_REGISTRY` 注册八个配方：`multilingual-subs`、`voice-dub`、`highlight-clips`、`reframe`、`social-post`、`quote-cards`、`carousel` 为 `live`；`image-video` 为 `reserved`。`GET /api/v1/recipes` 提供公共只读投影。
- Home 前端另以 `components/home/recipeFamilies.ts:RECIPE_FAMILIES` 组织用户任务货架。`ads` 是默认族；`talks` 与 `posts` 当前 `disabled`；`templates` 是未映射服务端卡片的 catch-all。
- `DEMO_HIDDEN_CARDS` 当前隐藏 `quote-cards` 与 `image-video`。隐藏只影响货架曝光，不删除 live 能力、prompt 注册或公共 API。
- Home 的 Ads 族只展示 Text Animation（文字短片）与 Product Promo 两个子 tab。Text Animation 使用项目 `9345ddc2` 与 `f52c489c` 的真实文字源 Film；Product Promo 前两张为 ZYMIX / AgentVeil 真片，其余两张仍复用既有片作布局占位。`brand` / `ugc` / `product` 是空货架，按规则不渲染。
- `RecipeCard` 只有 `status="live"` 才可点击；`reserved` 显示 Soon 且不可发射。点击不自动发送、不建项目或 run、不打开 overlay。
- `packages/clip` 同时服务 editor preview 与 render service；clip-spec 与 film-spec 是平级 spec families，按 `spec.family` 分派。配方不得创建第三套 spec 或 renderer。
- R5 合成发言视频是已拍板但未实施的能力，合同归 `tasks/synthetic-talk-video.md`；`voice_gen` / `synth_visual` 是目标能力名，不表示当前已注册。

## 1. 原则

1. **配方 = 用户可编辑的提示词捷径**。发射载荷就是预填文本；没有 `recipe_id` transport、服务端播种或前端构造的隐式计划。
2. **卡面承诺必须由当前能力兑现**。live、reserved、disabled、hidden 是不同状态，不得相互冒充；货架可点不等于真实制作旅程已验收。
3. **能力扩展走注册表**。新 tool、节点 kind、caption preset 或 mention 都登记到各自唯一注册表，不为单卡建立平行派发分支。
4. **多产物是能力，不是打包承诺**。卡片只承诺一种具体结果；不做“一次输入生成全套”的预设卡。
5. **用户点名的渠道才是渠道**。卡片和预填不得把默认平台写成用户已作出的选择；后续 chat 修改始终优先。
6. **样片证据分级**。真实样片证明对应样例；布局占位只证明货架形态；二者都不能代替 Chat → 方案 → 授权 → 制作 → 交付全旅程验收。

## 2. 三层职责

```text
服务端 RECIPE_REGISTRY       前端 RECIPE_FAMILIES          实际制作能力
公共配方数据与状态      →     任务族 / 子 tab / 货架     →   TOOL_REGISTRY + 持久图 + spec
声明式 flow/tasks 对账       demo URL 与预填 key             报价、授权、执行、交付
```

- 服务端 `tasks` 只作声明式编译形状和启动对账，不进入请求路径；`RecipePublic` 不含 `tasks`。
- 前端映射决定 RecipeCard 的货架归属；新增、隐藏或换族必须同时核对服务端投影、前端映射和 i18n。
- `resolveFamilies()` 依次过滤空 shelf、空 sub、空 family；保留座不等于可见占位卡。
- demo 货架不读 recipes API。demo URL 使用公开、内容寻址的 `demo/` 对象；reset 保留该前缀，替换不得覆盖共享 key。

## 3. Caption preset catalog

### 3.1 原语

字幕 preset 由布局、入场和词级高亮等正交原语组成。当前布局含单行替换与 `stack`；`stack` 让已揭示行驻留并向下累积。

### 3.2 当前 catalog

`packages/clip/src/captions.ts:CAPTION_PRESETS` 当前有六项：

```text
clean-bottom
karaoke-highlight
fade-in
pop-in
slide-up
stacking
```

`stacking = { layout: "stack", entrance: "fade-in", wordHighlight: false, maxLines: 5 }`。

- spec 只携带 preset id；Python schema 与 `app/pipeline/clip_spec.py` 镜像枚举，不复制渲染行为。
- 新样式优先新增 catalog 条目；新增原语值才扩渲染实现，并保持 preview/render 同源。
- 样式必须限定在 CSS 与 libass 都能表达的子集；新原语入库前检查映射成本。
- editor 与 `set_caption_style` 消费同一枚举，不为某张卡增加一次性字幕分支。

## 4. 当前配方与货架

### 4.1 多语言字幕（multilingual-subs）

- 承诺是字幕翻译与多语言版本，不暗中包含配音或额外剪辑。
- caption translation、`translation_track` 双语对照与标题随译属于 clip-spec 当前链；stack 布局不渲染不可读的双语堆叠墙。
- 画幅由当前 spec/任务参数表达；`original` 的源画幅语义只在支持它的材料化路径使用，不由卡面自行猜测。
- 用户明确点名配音时才进入 dub 能力，并继续受声纹、报价和授权规则约束。

### 4.2 图文视频（image-video，reserved）

- 当前是服务端 `reserved` 且被 Home 隐藏；不得作为可点击配方宣传。
- 照片/幻灯片、字幕、音频与音乐仍按现有 clip-spec 能力组合；保留 reserved 不等于删除底层 stills 能力。
- 重新上架前必须用真实输入/输出对验证承诺，并更新状态、Home 隐藏清单与样片证据。
- 本卡不承担 R5 合成发言视频；R5 的目标契约见 §8。

### 4.3 高光切片与访谈分镜（highlight-clips / reframe）

- 高光切片负责理解、选段、字幕与渲染；访谈分镜负责按真实说话人和画面做重取景。两者是不同用户请求，不共享一张“全能剪辑”卡。
- 当前分镜使用 `speaker_map` 素材事实与 `crop_track` 稀疏关键帧；静态 `crop` 仍是合法退化形态。
- `reframe_clip` 支持访谈切换、单人跟随与静态中裁等当前注册模式；实际可用模式与报价以 registry/编译结果为准。
- `crop_track` 属于 video 源取景，不得把 stills 扩张成 Ken-Burns 动效画廊。
- 检测、缓存、残毫秒竞态与精确报价的剩余项归 `PROGRESS.md` 需求池，不在卡面宣称已消除。

### 4.4 人设皮肤与声音归属

- 皮肤是 `persona.brand`，不是独立配方模板或新的 `look` 数据块；caption、标题、片头尾与音乐默认按当前 persona/render 合同消费。
- 声音是 `persona.voice`；composer 不增加另一套 Audio 状态或声音存储。
- `brand: null` 与 `voice: null` 都是合法默认，不等于用户已选择某种皮肤、声纹或 stock 音色。

### 4.5 原声 AI 配音（voice-dub）

- dub 链把翻译字幕、声纹合成与替换音轨接入同一 clip-spec 产物；多语言是同族节点扇出，不新增 renderer。
- 声纹克隆是明确能力，不能把通用 TTS 或 stock 音色描述成“用户自己的声音”。
- 缺声纹时不得静默换成 stock 并宣称完成原声配音；需要补充信息、换声或付费时走现有 Chat/QuestionDock/确认机器。
- AI 合成声音的披露与 provenance 按 ADR-026 处理；合规实现未完成前不得宣称已经满足法定披露。

### 4.6 文本族（social-post / quote-cards / carousel）

- `write_post`、quotes 与 carousel 是当前能力；`quote-cards` 虽被 Home 隐藏，仍可由明确用户请求触达。
- copy-writer 可在无素材请求下工作，但不得编造用户经历、渠道或引用；素材存在时仍以真实素材为证据。
- 渠道不进入卡轴。帖子只是帖子，直到用户点名 LinkedIn、机构站或 newsletter。
- 文本与图片示例若用于货架，必须来自真实对应链，不能用另一种产物顶替。

#### 4.6.1 社媒帖与轮播

社媒帖的重点是用户风格与可编辑文本；轮播的重点是分页图文产物。两者分别验收文本、分页、导出和后续修订，不以“能生成一段字”代替完整产物验收。

#### 4.6.2 金句叠卡链

- 当前主产物是**一张静态复合 PNG**，由 3–7 条动态选择的字幕/金句 strip 组成；不是 N 帧帧墙，也不固定条数。
- 形态 A 可带 speaker frame；形态 B 使用全幅背景与文字排版。可选 frame card sibling 与 `source_ref.parents` 保留来源谱系。
- 每个 script 有字体上限、换行与布局约束；recipe count、prompt 和实际渲染范围必须一致。
- 逐字保真、引用范围和用户修改边界按对应 quote 工具与 clip/spec 合同执行；不得为填满卡片发明引文。
- 单句图等其他形态仍是 Chat 能力，不因此增加货架座位。

### 4.7 撤座、隐藏与否决

- 隐藏是曝光决策，撤座是货架决策，删除能力是代码/产品决策；三者分别记录，不能借隐藏之名暗删能力。
- 语音转观点卡、风格修饰卡与“一鱼多吃”打包卡不进入货架；对应底层能力仍可由 Chat 使用。
- talking-head/数字人与 R5 合成发言不是同一承诺。R5 已拍板范围以 `tasks/synthetic-talk-video.md` 为准，v1 不接唇形 avatar。
- 重新上架或改变阵容需要真实场景、对应示例与当前用户证据；不能只改排序或复制另一货架样片。

### 4.8 上架门槛

一张卡必须同时满足：

1. **场景真实**：目标知识专家确实需要这道具体结果。
2. **形态或闭环有价值**：不是把普通文本生成包装成新能力。
3. **示例真实且有辨识度**：输入与输出属于同一当前制作链。
4. **能力可兑现**：技能、spec、报价、授权、失败与交付路径真实存在。
5. **全旅程独立验收**：预填 → Chat → 方案 → 授权 → 制作 → 交付 → 修订通过，不能只验卡面。

未满足时使用 reserved/disabled/hidden 或保持未注册；不得用占位样片绕过门槛。

## 5. 声音层

- 人设 `voice` 数据形态为 `{kind:"cloned", voice_id, sample_asset_id}`、`{kind:"stock", stock_id}` 或 `null`。`null` = Auto，dub 使用项目自身素材声音的当前回退语义按实现执行。
- 人设 Voice 卡负责展示绑定与上传/更换 voice sample；文案只陈述绑定状态，不许诺克隆质量。
- `STOCK_VOICES` 注册表、系统音色目录与试听仍是 deferred。不得写成已经上线，也不得声称多语言 stock 覆盖已核实。
- R5 缺声纹时不得静默换 stock；是否阻塞、提问或采用用户明确选择，按该任务合同与当前授权机器执行。
- 语速、发音纠正与固定术语读法属于后续术语表/声音能力，不由配方卡另建参数面板。

## 6. 分镜与素材事实

- ASR 词级时间戳、YuNet 检测、话轮归属与 `speaker_map` 是素材/派生事实；LLM 不得覆写已确定的时间码。
- `speaker_map` 只描述画面中说话者的位置、话轮与归属，不做人脸身份识别。
- `crop_track` 用稀疏关键帧表达取景决定，写侧负责最短驻留、死区与平滑约束，渲染侧只采样。
- Film 分镜另有独立的 storyboard/review hold/版本与执行合同；不得把 clip 的 `crop_track` 当成 Film storyboard，也不得把 Film 三段时间轴塞进 RecipeCard 参数。
- 长素材 CJK 检索、reframe 缓存和动态视听验收仍按 `PROGRESS.md` 与当前任务合同跟踪。

## 7. 卡片数据与交互

### 7.1 数据边界

服务端公共投影包含卡面/示例所需的 `flow`、`example_assets`、`example_outputs`、`input_slots` 等字段；它们存在不代表 Home 仍有 inspect overlay。

- 公共卡片由 `GET /api/v1/recipes` 匿名可读；`tasks` 永不下发。
- 可翻译文本走 en/zh i18n；en 是源语言，zh 必须满足同一 `Resources` 类型。
- demo 资源必须公开可读，不能使用登录态 asset 端点。
- 前端 `RECIPE_CARD_FAMILY` 决定 RecipeCard 归属；未映射项进入 `templates`。
- RecipeCard 预填 key = `recipes.<id>.promptTemplate`；demo 预填 key = `recipes.shelf.demos.<id>.prompt`。
- 未来真实 Gallery 若复用配方数据包，必须先登记公开性、素材权限、来源谱系与再制作边界；不能默认公开用户项目。

### 7.2 点击与发送

```text
点击 live 卡 / demo
  → composer 预填 prompt
  → 用户可修改、上传或补充素材
  → 用户点击发送
  → 正常建项目/上传/POST /chat 主链
  → 方案、制作意图与费用授权
  → 当前图与 worker 执行
```

- 空草稿或仍等于上次预填原文时，另一卡可替换预填；已有用户文字或 mention 时按当前 composer 合同保留并追加，不静默清空。
- 选文件本身不发送；只有 send 消费上传 chips。
- 预填不暴露工具、spec、版本或内部配方 id，不锁死用户未要求的画幅、幕数、时长或配音。
- 配方永不出现在 @ picker，不建立模板编辑器、第二发送钮或专用意图端点。

### 7.3 布局与播放

- Home 以 hero + composer 为主入口，货架位于其下；composer 滚动后是**视口底部**单行 stadium dock。
- 货架按用户任务组织，不按输出介质或渠道堆卡；空层级不渲染。
- demo 视频默认静音循环；IntersectionObserver 离屏暂停、回视口恢复；声音遵循 Home 全局单例互斥。
- 卡片画幅取真实文件，不拉伸；窄屏不得产生页面级横向溢出。
- 视觉细节与控件形态归 `UI_GUIDELINES.md` §4.1/§6，本文不复制第二套 CSS 规范。

## 8. 延期能力与验收

- **R5 合成发言视频**：已拍板、未实施、未排当前批次。`voice_gen` 产 generated audio，`synth_visual` 产 generated video；保留 generated provenance/source_ref、计量、失败与真实试听验收。不得绕过 clips need media，不创造第三套 spec/renderer，v1 不接唇形 avatar。
- **stock 目录与试听**： deferred；重启时先核实 provider 真实音色、多语言覆盖、权限和费用。
- **真实 Gallery/remix**：未排期；公开性字段与真实项目权限先行，复用当前 prompt-only 发射，不恢复 overlay 发射机器。
- **Home 六张占位卡**：等待用户选定对应真实样片后做数据替换；替换与验收步骤归 `tasks/home-creation-entry-refresh.md`。
- **配方验收**：分别检查货架交互、样片内容真实性和完整制作旅程。自动检查、真实模型、浏览器、声音与导出证据各自标注，未运行不得合并成“已验收”。

## 9. 新增或修改配方

1. 先确认它属于真实用户任务，并指出 `JOURNEYS.md` 的旅程与拍点。
2. 核对服务端 registry、前端货架映射、i18n、prompt registry 与能力注册表，不先写卡片特判。
3. 明确 live/reserved/disabled/hidden 与真实样片来源。
4. 保留 prompt-only、唯一 Chat 意图面、制作意图、报价和守卫线。
5. 用对应链真实输入/输出验收；占位只能标为布局证据。
6. 更新本文件当前事实与 Home 状态合同；不新增分期施工日记。

## 10. Prohibited Behaviors

- 禁把占位样片、卡面可点或公共 API 返回说成制作能力通过。
- 禁恢复 overlay 内发射、隐藏 `recipe_id`、服务端播种或第二意图入口。
- 禁自动发送、自动建 run、静默覆盖用户草稿或绕过制作意图/费用确认。
- 禁为单配方新增表、renderer、spec family 或平行执行链。
- 禁绕过 caption catalog、`TOOL_REGISTRY`、mention registry 或唯一图写口。
- 禁把 stock/TTS 说成用户声纹；禁在 R5 缺声纹时静默换 stock。
- 禁发明用户未点名的平台，禁“一次输入全套出”承诺。
- 禁覆盖共享 demo key、使用私有素材作匿名展示、拉伸画幅或绕过离屏暂停与声音互斥。
