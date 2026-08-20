# MiniMax Design — 原始证据（发布日走查 + 界面工艺清单）

> Status: 原始证据（2026-08-20 发布日当天账号走查，9 张界面截图 + 公开报道交叉验证；同日二轮 = 用户并排对照走查 + Agent Opus / FLORA / ElevenLabs 存量专档交叉，§8–§10；08-21 三轮 = Skills 生态仓库解剖，§11）。综合与拍板进 `COMPETITIVE_ANALYSIS.md` / `DECISION_MATRIX.md`——本文件只记事实与观察；拍板去向索引见 §12（ADR-046）。
> 关联：`research/flora.md`（同品类：画布 + agent 创作工具）；用户关注点是**界面精致度**，故 §3 工艺清单为本文件主体。

## 1. 产品模型事实

- 2026-08-20 正式发布，定位为"多模态创作 Agent 工作台"，基座 = H3 全模态视频模型（33B，2026-07-31 发布，Artificial Analysis 视频编辑榜第一）。
- 官方叙事：Agent 理解意图 → 拆任务 → 调模型与 Skills → 素材处理 / 生成 / 剪辑 / 交付；生成后可继续自动剪辑与加字幕。
- 差异化部件：**3D 导演台**（三维空间调角色/姿态/机位，构图确认后作为 H3 生成参考）；**ComfyUI Workflows（Beta）**（云端或本地执行，Agent 通过对话调节点参数）。
- Skills 生态开放：官方技能市场 + GitHub 技能仓库（每个技能 = 一个 SKILL.md），支持自定义创建与 GitHub 导入。
- 商业化：Credits 制（截图账号 3,000 credits）+ 订阅（年付优惠）；"AI Generated" 水印默认开，个人非公开用途可关。
- 目标用户自陈（onboarding 八选三）：Short Dramas / Films & Remix / E-commerce / Ads & Brand / Music Videos / Animation / Knowledge & Edu / Other——**创作者自我认证入口**。
- 目标场景（报道）：KOC/UGC 内容、电商种草、直播电商视频、教育内容、创意短片。

## 2. 界面骨架（按面走查）

**Home**：左侧展开式 sidebar（Start Creating / Project Gallery / Asset Center / Skill / ComfyUI Workflows `Beta` / Projects 折叠组）→ 主区点阵底纹，居中大号衬线字 "MiniMax Design" + 灰色副题 "Your Multimodal Agent Team" → 大圆角 composer（placeholder 内嵌 "explore H3 User Guide ↗" 链接）→ composer 下方 `+ / Models / Skills` 三 pill + "Select project" 上下文 chip → 顶条公告 "H3 is LIVE: Claim your Free Trial →" → 分类 tab 行（Featured / Official Skill / Effects / Influencer Marketing / Cinematic Intros，右端挂两个 User Guide ↗ 链接）→ Featured 媒体卡墙（时长角标 0:24）。

**Skill 陈列馆**：四列瀑布流。卡面解剖 = 无框媒体预览（圆角，左上角 H5 斜角缎带）→ 标题 → 路径 `/skills/xxx` → 右对齐元数据 `/SKILL_01 / v0.1.13` → 标签 chips（`动画片 / 动画·策划 / 动画·创意世代 / 动画·后期制作`）→ `/ 简短的` 小节标 → 一两行描述 → `查看详情 →`。

**Canvas 工作台**：点阵无限画布 + 顶栏（视图控件 / 缩放 100% / Minimap）+ 底部居中浮动工具条（`+` / 光标 / 文件夹 / `?`）+ 右侧 New Chat 面板（问候语 + Featured/Skill tab + 推荐行：缩略图 + 标题）+ 右下 composer（`+ / Models / Skills` pill + `Auto` 模型下拉 + 发送，上方年付 upsell 横幅，下方 "Ensure licensed content and lawful use" 免责行）。ComfyUI 工作流 = 画布上一个带标题栏的窗口卡（"Untitled workflow" + ×，状态行"正在检测 ComfyUI 后端…"）。布局模式菜单（⌘\）：Chat + Canvas / Chat on left / Chat on right / Chat only / Canvas only，每项带图标，勾选右对齐。

**账号菜单**：头像 + 昵称 + UID → 工作区切换行（Default / Personal account + 切换图标）→ Credits 行（✳ 3,000，千分位等宽数字）→ Subscription 行（紫色 "Annual plan offer" 徽标）→ Settings 组（Theme = 行内 moon/sun/monitor 三段开关、Memory management、Connect Lark `NEW` + Coming soon）→ Help 组（Tutorial / Changelog）。

**两个弹窗**：
- 水印设置：关键句加粗（"includes an "AI Generated" watermark by default"）+ 两段平实说明 + 开关（标签 + 两行辅助文字，告知以后去哪改：Settings → General → Remove Watermark）+ 唯一主按钮 Save Settings。
- Onboarding 领域选择：3 列选项卡（图标 + 截断标签），左下 "Selected 0 / 3" 计数，未选时 CTA 置灰。

## 3. 精致感清单（逐条可核对的工艺细节）

"精致"不是一处大招，是几十处小纪律的叠加。逐条列出：

1. **衬线/无衬线对比**：品牌字与 hero 标题用衬线，UI 正文用无衬线——编辑部式的高级感，全站就这一对对比。
2. **斜角缎带**：Skill 卡预览左上角的 H5 紫色渐变斜标（对角线切角），一张图一个，标记"用的哪个模型"。
3. **规格表美学**：卡面元数据 `/SKILL_01 / v0.1.13` 右对齐、斜杠分隔、近似等宽——技能 = 有版本的生命周期资产，治理感直接印在卡面上。
4. **层级标签 chips**：`动画·策划` 用 `·` 分隔领域与环节，小一号描边 pill，一张卡四个。
5. **斜杠小节标**：`/ 简短的` 这种 slash 前缀标签（目录路径语感），全站统一。
6. **Tour 的虚线牵引箭头**：深色教学气泡指向被教控件时，画一条手绘虚线弯箭头——气泡和目标之间的视觉连接不靠位置猜。
7. **Tour 用真制品教学**：教 `/` 键时气泡里直接渲染真实的紫色技能 chips（/Storyboard、/Character Cards、/Episode Script），不是抽象示意图。
8. **Tour 进度 = 短横线**（— — —）而非圆点。
9. **行内三段主题开关**：账号菜单里 Theme 行直接内嵌 moon/sun/monitor 分段控件，不进二级页。
10. **Credits 行**：✳ 符号 + 千分位等宽数字 + 右 chevron，数据感。
11. **徽标语言统一**：`Beta` / `NEW` / `Annual plan offer` / 时长角标 / H5 缎带——五种徽标各归各位，尺寸克制。
12. **点阵底纹**：画布区铺极浅点阵而非纯色——"工作台"质感，也帮用户感知平移。
13. **空态即内容**：New Chat 面板不放空插画，放 Featured/Skill 推荐行（缩略图 + 标题），空态直接给下一步。
14. **placeholder 内嵌链接**：composer 占位文案里嵌 "explore H3 User Guide ↗"（与我们"placeholder 只留一句短提示、教学归 Tour"的纪律相反，见 §6）。
15. **菜单项的快捷键标注**：布局模式菜单右上挂 ⌘\，每项带专属图标，勾选对齐右端。
16. **合规微文案可见**：水印弹窗的加粗关键句 + composer 下 "Ensure licensed content and lawful use"——合规文案当作界面工艺做，不是法务脚注。
17. **Upsell 位置**：年付优惠横幅贴在 composer 上方（发送前最后一眼），不打断流程。
18. **截断纪律**：onboarding 选项卡标签一律省略号截断不换行，网格永远整齐。
19. **窗口卡隐喻**：ComfyUI 工作流在画布上是一个带标题栏和 × 的"窗口"，负载状态写在窗口体内（"正在检测 ComfyUI 后端…"）。
20. **分类 tab 行右端挂指南链接**：筛选 tab 与 User Guide ↗ 共用一行，导航密度高但不挤。

## 4. 与我们的语法重合（平行收敛清单)

两套独立团队做出同一套 agent 语法，逐条对应：

| MiniMax Design | Repurposer |
|:---|:---|
| Skill 卡陈列馆（版本号 + 分类标签 + 查看详情） | 配方库 / recipe gallery |
| `@` 选文件和模型 | MentionEditor + MENTION_REGISTRY |
| `/` 调技能 | 技能注册表 + intent prompt 枚举 |
| Chat + Canvas 双区 + 底部 composer | 结果画布 + 底部 dock（ADR-041） |
| 深色 tour 气泡 + 分步 Next | 4 步 Tour（内容哈希版本化） |
| Credits pill | composer 底排 credits 信息 pill |
| 水印默认开 + 设置可关 | （未上线，记录为候选） |

结论性观察：@、/、卡片、画布、dock 已是 agent 产品通用语，交互基准线被这类大厂产品持续抬高。

## 5. 定位分叉（事实层）

- **它是生成优先**：技能全是"X 生成器"（3D动画短片 / 品牌宣传视频 / POV 短片 / FPV 观光…），起点 = 空白 prompt，工具链（3D 导演台 / Character Cards / Storyboard）服务"无中生有"。九张截图中无对用户素材做转写级编辑的界面。
- **我们是 repurposing 优先**：起点 = 用户已有素材（ASR 词级 → speaker_map → 策展/裁切/重构图/配音/多语 → clip-spec 渲染已有 footage）。
- **用户赌注相反**：它一个界面同时伺候专业创作者与小白（ComfyUI 逃生舱 + 可操作画布 + Minimap）；我们禁可操作 DAG、只留只读 FlowView，用户全是小白。
- **合规矩阵**：H3 开源权重许可排除 US/EU/UK/韩国；MiniMax = 中国厂商。EU 数据驻留是我们的楔子。

## 6. 我们侧对照（仅事实，无拍板）

- **配方卡**：我方 = 媒体 tile + 标题 + 元信息；对方多出版本号、taxonomy chips、路径行。我方卡面无"治理资产"信号。
- **Tour**：我方 = 内容哈希版本化、data-tour 锚点；对方多出虚线牵引箭头、气泡内嵌真实技能 chips。两处可低成本移植。
- **Composer 教学位**：我方纪律 = placeholder 只留一句短提示、教学归 Tour；对方把 User Guide 链接嵌进 placeholder。纪律相反，记录备查，不视作我方缺陷。
- **主题切换**：我方 = 设置内切换 + View Transition 圆形揭示；对方 = 账号菜单行内三段控件，路径更短。
- **空态**：对方 New Chat 面板用推荐行填空；我方 overlay chat 空态无内容推荐。
- **账号菜单**：我方 = Profile / Settings / Logout；对方 = 工作区切换 + Credits 行 + 订阅徽标 + 行内主题开关 + Tutorial/Changelog。信息密度高一个量级。
- **画布**：我方 FlowView 只读、纯色底；对方可操作、点阵底、Minimap、布局切换。分叉属拍板结果（ADR-041），非差距。
- **徽标纪律**：对方五种徽标（缎带/Beta/NEW/offer/时长）各归各位；我方徽标使用尚无统一清单。

## 7. 来源

- 界面事实：2026-08-20 账号走查截图 ×9（home / skill 陈列馆 / 水印弹窗 / onboarding / 账号菜单 / sidebar / canvas 工作台 / 布局菜单 / tour×2）。
- [网易科技：H3 开源生态再进一步，MiniMax Design 正式发布](https://www.163.com/tech/article/L4P7SBM200098IEO_pa11y.html)
- [搜狐/上证报：MiniMax Design 正式发布 推动 H3 从模型能力走向商业内容生产](https://m.sohu.com/a/1065255936_120988576?scm=10001.325_13-325_13.0.0-0-0-0-0.5_1334)
- [MarkTechPost：MiniMax H3 模型发布](https://www.marktechpost.com/2026/08/01/minimax-releases-minimax-h3-an-omni-modal-video-model-that-generates-15-second-2k-clips-with-native-stereo-audio/)
- [RunPod：H3 开源权重与许可地域限制](https://www.runpod.io/blog/minimax-h3-the-open-weight-omni-modal-video-model-and-what-it-takes-to-run-it)
- [MiniMax Agent 技能市场](https://agent.minimax.io/skills) · [MiniMax-AI/skills (GitHub)](https://github.com/MiniMax-AI/skills) · [MiniMax-H3 skills 示例 SKILL.md](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/music-video-subtitle-generator/SKILL.md)

## 8. 二轮走查：并排对照新增事实（2026-08-20 当日）

用户将 MiniMax Design 与我方 home 实验台并排对照，逐面盘点出首轮走查未记录的界面事实：

- **Sidebar 色役分层**：item hover 底色 / selected 底色 / item 名色 / 组名色四个角色各占灰阶位置——列表的可操作感来自分层，不是描边。
- **Home 主区**：hero 衬线标题与灰色副标题两阶文字；顶条公告 "H3 is LIVE: Claim your Free Trial →" 是独立色役；点阵底纹色独立于页面底色。
- **Composer 区**：pill 名色 / pill 内图标盒底色 / send enabled 色 / send disabled 色 / 输入框描边色五个角色——**send disabled 是独立色役**（浅灰底 + 灰图标），不是 enabled 态的透明度衰减。
- **配方卡墙**：卡标题色与卡描述色分两阶；卡面上覆盖文字（标题 / 时长）恒白，不随主题。
- **账户菜单**：user card 底色 / UID 色 / Settings 组标题色 / 组内 item（如 Theme）名色 / 黑白分段开关轨道色——一个弹层内至少五个色役；分段开关 = 深轨道 + 白滑块（iOS segmented 形态）。
- **分类 tab 行**（当日三轮核对补记）：selected = **反色实心丸**（黑底白字，Featured），rest = 灰字——与列表导航的弱档选中是两套色役；行右端挂 slash 前缀指南链接（灰）。
- **Sidebar 文字两阶**（同日补记）：主 item（Start Creating / Project Gallery…）文字近黑不降级，二级/子项行（Ungrouped / 项目条目）用灰。
- **公告 pill 两阶同丸**（同日补记）：加粗段 "MiniMax H3 is LIVE" 近黑 + 常态段 "Claim your Free Trial ›" 灰，card 底 + 发丝描边，顶中悬浮。
- **徽标色役**（同日补记）：`Beta` 小丸 = 灰底 + 灰字，无彩色——彩色徽标仅营销面（Annual offer / NEW）。

观察：全部色役住在中性灰阶上，彩色近乎零（例外仅徽标级三处：H5 缎带 / Annual plan offer / `NEW`）——"颜色很多"的观感来自角色粒度细，不是色相多。

## 9. 跨品对照增量（Agent Opus / FLORA / ElevenLabs）

同日以 MiniMax 为镜回查三家存量证据（专档各在，本节只记本轮新增与重新确认的事实）：

- **Agent Opus**（`research/agent-opus.md`）：灵感 gallery 为 masonry 瀑布流，旗舰卡 2 倍宽跨列；卡面语言 = 类目 chip 左上 + 底部 scrim + hover 动作行；通知 = 内容区右上角浮动芯片（无全局顶条）；账户菜单 = 平铺 list（我方账户区现状同此型，与 MiniMax 的 console 分层形成密度对照）。
- **FLORA**（`research/flora.md`）：配方卡 hover 出 "Use Prompt" 快捷动作——其先决是卡面 = 完整单产物 + 零输入依赖；账户偏好两层分工（行内高频开关 + 深度设置 modal）为先例；EU AI Act 透明度偏好项见专档。
- **ElevenLabs / ElevenCreative**（`research/elevencreative.md`）：浅色卡面 = 发丝线 + 软阴影的工艺参照（我方 08-06 前卡面 doctrine 的来源，ADR-046 后改判）；配方 modal "使用此示例" = 访客零上传试跑先例（需求池已登记）。

## 10. 色役粒度盘点（角色清单）

以 MiniMax 界面为样本逐面枚举可见色役（用户并排对照盘点，~21 个角色）：

| 面 | 色役 |
|---|---|
| Sidebar | item hover bg / item selected bg / item name / group name |
| Home 主区 | hero title / 副标题 / 公告条 / 点阵 |
| Composer | pill name / pill 图标盒 bg / send enabled / send disabled / input border / placeholder |
| 配方卡墙 | 卡标题 / 卡描述 |
| 账户菜单 | user card bg / UID / settings group title / 组内 item name / 分段开关轨道 bg |

我方现状对照（`apps/web/src/styles.css`，仅事实）：文字三阶（foreground / muted-foreground / meta-foreground）+ 填充五阶（background / card / subtle / muted / inset）+ accent hover + hairline（ring-foreground/10）。**粒度差在四个缺位角色**：send-disabled / group-title / icon-chip（chip 与文件行内图标盒）/ toggle-track（分段开关轨道）无专属 token，组件内为临时值或借用。

## 11. Skills 生态解剖（仓库级走查，2026-08-21）

以 `design.minimax.io/skill/brand-promo-video-generator` 为入口追到仓库真身（卡片页本身只是 "Open in MiniMax Design" 深链壳）。

**仓库分布**
- `MiniMax-AI/MiniMax-H3` `skills/`：内容生成技能（3d-animation-short-generator / brand-promo-video-generator / music-video-subtitle-generator 等）+ `skills-lock.json` 锁版本。
- `MiniMax-AI/skills`：dev 工具技能（pr-review / pptx / android-native-dev 等），仓库即 Claude 插件市场（`.claude-plugin/marketplace.json`），附 `.codex` / `.cursor-plugin` / `.opencode` 安装适配。

**单技能解剖（brand-promo-video-generator 为样本）**
- 文件构成：`SKILL.md`（189 行指令本体）+ `SKILL.cn.md`（中文版）+ `meta.yaml`（市场元数据）+ `references/` ×5（fallback-policy / model-selection / qc-checklist / shot-table-spec / storyboard-guidelines——用到才加载的渐进披露）。
- frontmatter = Agent Skills 协议键（`name` / `description`）+ MiniMax 扩展：`compatibility`（自陈 "Requires the MiniMax Hub agent…not portable to generic agent harnesses"）+ `allowed-tools`（`webfetch` + `hub_image_search` / `hub_generate_video` / `hub_video_edit` 等 12 个 hub_* 工具 + `task` 的白名单）。
- `meta.yaml`：`display-name-zh` / `version: 0.1.9` / `tag` + `complete-tags`（`商业广告 / 计划制定 / 创作生成 / 后期处理` taxonomy，即卡面 `·` 分隔 chips 的来源）/ 双语 summary+desc / `author` / `source: official-featured`。
- 多 harness 镜像：同技能在 `.claude/skills/` 与 `.agents/skills/` 各一份（含 `agents/openai.yaml`）。

**SKILL.md 工作流（10 步散文，模型逐步直调 allowed-tools 执行）**

intake（素材 + 时长/画幅/受众/推广重点，含"文案语言跟品牌不跟聊天语言"规则）→ 品牌事实表（官方源分级，禁用聚合站/饭制/AI 替代品）→ provenance manifest（素材逐条记 source / rights / authenticity）→ 叙事脊（按品类 4 模板出 2-3 供用户挑）→ 逐拍分镜（30fps 约定，15s = 5-8 beats，beat 字段 8 项）→ 运动语言纪律 → **生成前硬确认**（预制包全量摆给用户，"可以/继续"类明确词才放行）→ hub 生成（音频策略：默认视频模型原生音轨，分离配音仅按需）→ **交付前质检 7 条** → 交付（产物 + 出处清单 + 下一步建议）+ **failure recovery 清单**（错 logo 撤换、像假货即弃、"Never improve an imitation"）。

**观察（事实层）**
- 生成前硬确认 / 交付前质检 / failure recovery = 与我方 confirm 闸、质检、修复一轮同构的需求，实现形态为散文条款——闸门强度依赖模型遵守 prose。
- 技能 = 有版本生命周期的治理资产（版本号印卡面、meta.yaml 注册、lock 文件），与我方配方卡面无版本/治理信号形成对照（§6 已记卡面差异）。
- 内容技能全部是 "X 生成器"，散文工作流适配生成优先（无用户素材硬不变量要守）——§5 定位分叉在技能格式层的延伸。

来源：[MiniMax-H3 `skills/brand-promo-video-generator/SKILL.md`](https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/brand-promo-video-generator/SKILL.md) · [`meta.yaml`](https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/brand-promo-video-generator/meta.yaml) · [MiniMax-AI/skills 仓库树](https://github.com/MiniMax-AI/skills)（均 2026-08-21 抓取）。

## 12. 拍板落档索引

本文件证据的拍板去向：**ADR-046**（studio 视觉骨架重塑——灰底填充阶 / 影子只属浮层 / 实体丸化 / 海报优先画廊 / 去全局 header）；施工简报 `docs/tasks/home-skeleton-revamp.md`（含"角色 → token × 双主题"色役对照表，作验收清单）；doctrine 修订 = 根 CLAUDE.md（Card Depth / Composer / Sidebar & Navigation 三节）。需求池登记两条后续：EU AI Act 内容标记偏好、demo teaser 封面重烘。
