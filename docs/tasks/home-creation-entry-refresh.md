# Home 创作入口与真实样片——当前状态

> Status: 当前开发/手测入口为四产品 × 八应用；三个应用共接入五张来自内部真实旅程的新链样片，另外五个应用显示统一空态。此处不构成正式公开 Gallery 验收；用户连续看片、实际试听与逐类公开发布门统一归 `skill-package-promo-video.md` P6。

## 1. 当前信息架构

旧「广告与 UGC / 演讲与访谈 / 社媒」不再作为 Home 视频分组，旧 Film 样片和复用占位片不进入当前货架。非视频 Recipe 的服务端注册、能力与 prompt 未改。

| 产品主 Tab | 典型应用子 Tab | 当前内容 |
|---|---|---|
| 产品宣传 | 网站/产品宣传、课程/服务宣传 | 前者三张真实样片；后者空态 |
| 口播动效 | 观点口播、课程/讲座预告 | 两者均空态 |
| 文字动画 | 观点文字片、金句/公告短片 | 前者一张真实样片；后者空态 |
| 知识讲解 | 概念讲解、研究/报告解读 | 前者一张真实样片；后者空态 |

主 Tab 短名来自 `skills.builtin.<id>.shortName`，由 `skillDisplayName(..., "short")` 读取；picker、chip 与 `/任务名` 继续使用完整 `name`。Home 不维护第二份产品命名表。子 Tab 与空态均走 en/zh i18n，空态只陈述「该应用暂无样片 / No sample for this application yet.」。

卡片「开始创作 / Start creating」以「用这个 Skill 帮我…… / Use this Skill to help me…」示范使用方式，预填简短需求，并单独绑定既有 Skill。预填不默认指定分幕、时长、画幅、动效、音乐、音效或制作阶段，也不把这些限制隐藏到后台。文字动画提供可直接编辑的示例文案，知识讲解提供可替换的具体概念；产品宣传由用户提供自己的来源。样片是参考，不承诺复刻；制作授权继续由既有流程处理。中英文入口文案已同步，当前改动未做浏览器或制作验证。

## 2. 五张当前样片与来源

| 应用 / demo id | demo key | 来源与精确 Skill | prompt 来源 |
|---|---|---|---|
| 网站/产品宣传 · `product-promo-agentveil-the-next-move` | `demo/outputs/product-promo-agentveil-the-next-move-a2a4b391.mp4` | Project `b8b20d17-28eb-4c60-8656-d937f2593f56`；修订版 `91c7d379-df3b-4076-9881-8978e8ec5000`；Output `cf91834d-8bc3-40e8-821d-92c5e5e961e3`；`launch-film@1.4.0` | 当前预填只描述根据网站或素材表达产品价值；不继承样片的声音和镜头设置 |
| 网站/产品宣传 · `product-promo-oxvalue-product-evidence` | `demo/outputs/product-promo-oxvalue-product-evidence-e1e78348.mp4` | Project `7386da2b-596e-496b-bb71-01768070ee9e`；V1 `d05092fa-37bd-4f41-bedc-296371600a81`；Output `73258a3a-0b16-416b-8a61-d256664f0a0f`；`promo-video@1.0.0` | 与下一张卡共用原始默认预填，不固定 arc；Agent 根据用户材料选择表达路线 |
| 网站/产品宣传 · `product-promo-oxvalue-energy-arc` | `demo/outputs/product-promo-oxvalue-energy-arc-6f210db6.mp4` | Project `9f7440f8-d552-4732-9763-ada09e8c5476`；V1 `aa5a8f5a-0b52-475e-aee1-0399df0dc818`；Output `a98d24e9-c100-4646-94f9-4424c30ccd57`；`promo-video@1.0.0` | 同上；卡片不携带来源旅程额外指定的 energy arc、字幕、配乐或画幅要求 |
| 观点文字片 · `text-short-clear-rhythm` | `demo/outputs/text-short-clear-rhythm-2d594025.mp4` | Project `e92babc3-2dab-4876-a31b-ce0e31667d67`；修订版 `c2df1934-2ace-4b5f-89fb-95e7f9a67f09`；Output `c71525b6-1ab3-4ac3-b694-ce84076efe84`；`text-animation@1.0.0` | 当前预填为有表现力的文字动画与一段可编辑的完整示例文案；不继承样片时长、画幅或逐词入场 |
| 概念讲解 · `knowledge-explainer-clear-expression` | `demo/outputs/knowledge-explainer-clear-expression-73f4a743.mp4` | Project `0d6104fd-05d0-4029-a1e8-9c193450495e`；修订版 `866b194d-ea31-4c01-af2f-5f17163e5af6`；Output `2b791e37-3290-499e-a88f-c83323354911`；`knowledge-explainer@1.0.0` | 当前预填为解释“一次只讲一个重点”的概念需求；不要求用户预先提供最终录音，不携带样片内部资产 |

五份本地文件均已核对真实 Output、实际帧数、fps、画幅与音轨；新增两片还核对了 CompositionVersion content digest 与完整本地 SHA-256：

- AgentVeil 产品片：1920×1080 / 30fps，3482 帧，116.2 秒，含音轨；SHA-256 `4c25ec1c…c84`。
- OxValue product-evidence：1920×1080 / 30fps，1350 帧，45 秒，Tech House 音轨全程可解码；18,929,727 字节；SHA-256 `41356290a9eb80bfb3e78a6c0c6939b9e8dc61998d0de2b63ad919bd9008df2e`。原生文字无底条；前两幕均显示完整首页、视觉重复的问题仍保留。
- OxValue energy-arc：1920×1080 / 30fps，1275 帧，42.5 秒，Tech House 音轨全程可解码；7,391,479 字节；SHA-256 `f9392d8712a8d3e83255a9ff5a1603418fe8dca3341086d20b23f4766487ec65`。当前上架的 V1 原生字幕仍有深色背景，不代表后续无底字幕规则已落实到这张旧片。
- 文字片：1920×1080 / 30fps，360 帧，12.1 秒，含音轨；SHA-256 `50ecc3a8…f15`。
- 知识片：1920×1080 / 30fps，114 帧，3.861 秒，含音轨；SHA-256 `7f26d8aa…146`。

五个内容寻址对象均位于公开 demo 前缀，URL 返回 200，Content-Length 与 ETag/MD5 匹配，且带 immutable 缓存。文字片、知识片与两张新增 OxValue 片均完成公网 SHA-256 全量回读；AgentVeil 产品片只有本地 SHA、公开长度与 ETag 核对，未记为公网 SHA 回读通过。未覆盖任何既有 demo key。

## 3. 交互合同

- 卡片点击唯一行为是进入 composer，形成精确版本的可见 Skill chip + 可编辑 prompt；与手动 Slash/Skill 选择使用同一 reference + prompt 载荷，最终仍只走 `POST /chat`。
- 不自动发送、不自动 Start、不自动上传素材、不建项目或 Run、不产生制作意图；没有 `recipe_id` 旁路、第二意图面或第二执行链。
- 空态没有样片卡或发射动作。五个无样片应用保持可见，不能拿其他应用成片填充。
- 草稿替换/追加、Skill chip 删除与切换、声音互斥、离屏暂停、真实画幅与两级锚点滚动沿用既有实现。DemoCard 的键盘焦点使用可见 `outline-solid`，不是不可见的 `outline-none` 残留。
- 正式公开 Gallery 仍逐类要求完整制作/修订旅程、真实完整音轨、连续动态观看与实际试听；当前开发/手测上架不替代这些门。

## 4. 当前验证

- 原三张卡阶段的定向 Web 纯测试为 **27/27 通过**，真实 Chrome 为 **8/8 代表组合通过**，覆盖 desktop/mobile、en/zh、light/dark、普通/reduced-motion、长 prompt 换行、无页面级横向溢出、键盘可见焦点与 `ignoreCache:true` 硬刷新。原三张卡共点击 24 次，均形成对应 chip + 可编辑 prompt；监听到的修改请求为 **0**，没有 `POST /chat`、上传或创建项目/Run。证据在 `scratch/d5-home-four-products/`，汇总为 `browser-matrix.json`。
- 当前新增的两张 OxValue 卡已登记真实 URL、精确 `promo-video@1.0.0`、wide 画幅与 en/zh 同一默认 prompt，并更新 registry/count 断言。两张公开对象的 200 响应、Content-Length、ETag/MD5 与全量 SHA-256 回读均已实测；**新增后的 Web 测试、TypeScript 与浏览器点击/播放尚未运行**。
- 当前 `test/core`、相关真实旅程与完整 Web 检查本次未运行；新增上架未调用付费模型或制作新版本，未部署。

## 5. 留给用户的逐卡手测

1. **产品宣传 → 网站/产品宣传**：逐一点击三张卡片，确认前两张来源分别绑定 `launch-film@1.4.0` 与 `promo-video@1.0.0`，新增两张 OxValue 卡只形成相同默认 prompt、不暗藏 arc；实际播放公开 MP4。自行提供网站与产品图片/视频后手动发送，先完整审阅首版，再另行明确制作。product-evidence 的前两幕网页重复、energy-arc V1 的深色字幕底仍是已知视觉欠账；连续看片与实际试听尚未完成。
2. **文字动画 → 观点文字片**：确认预填包含简短需求与一段可编辑的完整示例文案；可编辑后手动发送，首版呈现不应同回合开工。连续看片并试听；另做一次局部文字修订，确认只改目标内容。
3. **知识讲解 → 概念讲解**：使用预填概念或换成自己的主题；不会沿用样片内部资产。连续看片并试听，核对词锚字幕和解释性 Generator；v2 标题/Generator 拥挤只减轻、未完全消除，必须实际判断，不能视为视觉验收已通过。
4. **五个空态**：课程/服务宣传、观点口播、课程/讲座预告、金句/公告短片、研究/报告解读只应显示暂无样片，不出现可点视频卡。
5. **口播阻塞**：指定真人 VIDEO 与 SourceSnapshot 仍为 `NoSuchKey`；本批没有制作替代片，也不以空态宣称口播能力已验收。
