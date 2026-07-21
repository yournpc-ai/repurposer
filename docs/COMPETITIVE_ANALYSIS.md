# Competitive Analysis — 竞品能力全景与分类（Round 1.2）

> **状态**: Round 1.2 — 能力普查 + 分类框架（经两轮交叉评审与独立事实核查，为后续"单竞品卡片 + 横向决策矩阵"打底）
> **日期**: 2026-07-19
> **覆盖**: Opus.pro (OpusClip) / Descript / Submagic / Repurpose.io / Revid.ai / Crayo.ai / ChatCut
> **数据说明**: 竞品官网 + 定价页 + 官方 changelog/帮助文档 + 第三方评测交叉验证；未能验证的条目在行内标注 ⚠️
> **关联文档**: `research/opusclip-deep-dive.md`（OpusClip 单家深度拆解）、`PRD.md` §3.4（旧版定位对比，颗粒度粗，待 superseded）、§14.5（UX 借鉴表）、ADR-014/016（品类与交互对标结论）
> **修订记录**: v1.1 根据评审修正 9 处事实、增补 6 个维度；v1.2 对评审意见本身做独立核查——确认 13 项、部分修正 4 项、驳回 3 项（OpusClip"积分 3 天清零"、ChatCut"XML 仅见搜索摘要"、Crayo"无按模型计费"均与官方来源冲突，已按官方来源改回），另修正 Descript 翻译/配音语言数为最新官方值

---

## 1. 一句话定位速览

| 竞品 | 一句话定位 | 目标用户 | 公司/数据 |
|:---|:---|:---|:---|
| **Opus.pro (OpusClip)** | 长视频 → 批量病毒式短视频的 AI pipeline，一键发全平台 | 播客、网红、营销团队、机构（宣称 16M+ 用户） | 美国 Palo Alto；SOC 2；数据存 GCP **美国**；GDPR 靠 SCC/DPF |
| **Descript** | "改文字 = 改视频"的文档式全功能编辑器 + Underlord AI 副驾 | 播客、访谈、知识内容团队 | 美国 SF；SOC 2；AWS/GCP **美国**；内容默认不用于训练 |
| **Submagic** | 动态字幕起家的短视频增强器（Magic Clips 切条为附加项） | 创作者、小企业、代理商（宣称 4M+ 用户） | **法国 Submagic SAS（巴黎）**；声明 GDPR，但官方隐私政策写明"服务器位于美国"（AWS/Vercel/Supabase 等子处理器跨美欧），**无 EU-only 驻留** |
| **Repurpose.io** | "Create once, publish everywhere" — 分发自动化管道，零 AI 生成 | 播客、YouTuber、教练、小机构 | 据报加拿大 ⚠️（官网 403 未能验证）；无公开 GDPR 声明 ⚠️ |
| **Revid.ai** | 100+ 工具的生成式短视频工厂（prompt/URL/PDF → 竖屏视频） | 无脸频道主、批量内容运营者 | **法国公司（巴黎）**，但隐私政策自述数据存 GCP **美国** ⚠️ |
| **Crayo.ai** | 模板向导式无脸短视频工具（Reddit 故事/假短信/分屏 gameplay） | 个人 clipper、无脸频道主（宣称 3.2M 用户 ⚠️） | 法律实体/总部不公开 ⚠️；Trustpilot 有计费投诉记录 |
| **ChatCut** | 对话式 AI 编辑器 — 自然语言驱动**真多轨时间线** | 专业剪辑师、播客/访谈/纪录片团队 | 美国 Austin；2025-10 真格领投、Antler 跟投种子轮 $1.35M（已证实）；无 GDPR 声明 |

---

## 2. 能力地图（横向矩阵）

图例：✅ = 核心能力/品类标杆 · ✓ = 具备 · ~ = 部分/附加项/弱 · ✗ = 无

### A. 输入与源

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 本地上传 | ✓ | ✓ (50GB) | ✓ | ✓ | ✓ | ✓ | ✓ |
| 链接导入（YouTube 等） | ✅ 16+ 源 | ✓ Zoom/SquadCast；⚠️ **2025-12-05 官方宣布关闭 YouTube 链接导入**（YouTube 反爬所致） | ✓ 仅 YT | ✅ RSS/Zoom/Drive/Twitch 自动轮询 | ✓ URL/产品页/PDF | ✓ YT/TikTok | ✗ |
| 应用内录制 | ✗ | ✅ Rooms 远程录制 | ✗ | ✗ | ✓ | ✗ | ✗ |

> **注**: Descript 关闭 YouTube 链接导入（官方 changelog 原话："YouTube regularly updates its systems to prevent automated downloading… turn off the YouTube import feature for now"）是七家中最值得注意的输入缺口——"链接抓取"看似简单实则持续被平台反爬打击。这佐证了我们 FR-018（链接自动抓取）的真实价值与维护成本，做之前要预期反爬对抗。

### B. 内容理解与切条

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| AI 高光切条 | ✅ ClipAnything + prompt-to-clip | ✓ Underlord Create Clips | ✓ Magic Clips（+$19/月加购） | ✗ 仅手动 snippet | ~ 生成优先，非切条 | ✗ | ✓ NL 指令切条 |
| **Virality Score** | ✅ **唯一** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 全体裁理解（非 talking-head） | ✅ 游戏/体育/vlog | ~ | ~ | ✗ | ✗ | ✗ | ~ |

### C. 画面改造

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 自动竖屏 reframe | ✅ ReframeAnything + 物体追踪 | ✓ Center Active Speaker | ✓ | ✓ 模板式 | ✓ | ✓ 原生竖屏 | ✓ |
| B-roll | ✅ 图库 + AI 生成规模化（Pro 50 条/天） | ✓ 图库 + Quick Design | ✓ Storyblocks/电影片段 | ✗ | ✅ 生成式 | ✓ gameplay 背景 | ✅ 图库 + AI 生成 |

### D. 字幕

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 动态字幕 | ✓ | ✓ | ✅ **品类标杆** | ~ 烧录源字幕 | ✓ | ✓ 15+ 样式 | ✓ 20+ 样式 |
| ASR/字幕语言数 | 25+ | **26**（官方口径：仅限拉丁字母语言，无中/日/俄——列表已出现希腊语/印地语 beta 例外；字幕翻译 **67**） | **48** | 依赖源字幕 | 70+（配音） | ⚠️ 未公开 | **100+** |
| 说话人分离着色 | ✓ 仅 Business | ✓ 8+ 说话人 | ✗ | ✗ | ✗ | ✗ | ✓ |

> **注**: Descript 官方帮助文档原话："supported transcription languages are limited to those using the Latin alphabet. Languages such as Chinese, Japanese, or Russian are not yet supported." 它的多语言护城河在**翻译/配音**（67 语字幕翻译 + 28 语配音），不在转写。这对我们很重要：对手在"听懂"环节的覆盖远窄于"译出"环节。

### E. 编辑模型

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 文本驱动编辑（删字=剪片） | ✓ | ✅ **品类开创者** | ✓ | ✗ | ~ | ✗ | ✓ |
| 时间线 | ~ 简易 | ✓ | ~ | ✗ | ~ | ~ 轻量 | ✅ **真多轨** |
| 对话式/NL 编辑 | ~ prompt-to-clip | ✓ Underlord 多步 agent | ✗ | ✗ | ~ prompt | ✗ 纯向导 | ✅ **旗舰能力** |
| 导出 XML 交接 NLE | ✓ Pro+ | ✅ Premiere/DaVinci/ProTools | ✗ | ✗ | ✗ | ✗ | ✓ XML/SRT 交接 Premiere/DaVinci（官方页面确认）；导出上限 1080p；ProRes 仅"limited 1080p"，4444 alpha 未证实 ⚠️ |
| **预览 = 导出一致性** | ~ 未见集中投诉 | ~ 未见集中投诉 | ✗ **预览与导出漂移**（字体/emoji/颜色，多家 2026 评测报告 ⚠️ "dealbreaker" 一说未找到一手出处） | — | ⚠️ 未知 | ⚠️ 未知 | ⚠️ 未知 |

> **注**: "预览 = 导出一致性"一行验证我们 ADR-016「preview = output pixel parity」的赌注方向是对的——Submagic 在这一项上被反复点名。同一组件同时服务预览与渲染（Remotion `<Player>`）必须作为不可妥协的架构约束保留。

### F. 生成式媒体

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| AI 视频生成 | ✓ Agent Opus | ✓ | ✓ AI credits | ✗ | ✅ 100+ 工具（Veo 3 / Sora 2 / Seedance 按名暴露、官方明码标价 100 / 130 / 200–1000 credit） | ✓ VEO3 单独计费（官方售卖 VEO3 Credits，$50/5 个） | ✓ Seedance 2.0 |
| AI 头像 | ✗ | ✅ 35+ + 自定义 | ✓ | ✗ | ✓ 换脸/反应视频 | ✗ | ✗ |
| 声音克隆 | ✓ **2026-07-07 上线 Video Dubbing**：25 语配音自动克隆原声（Pro/Business，10 credit/分钟） | ✅ 含 ElevenLabs v3 | ✗ | ✗ | ✓ Ultra 档 | ✓ 高档位 | ✗ |
| AI 音乐/音效 | ✓ 一键音效自动铺点（官方名 Sound Effects，2026-07） | ✓ | ✓ | ✗ | ✓ AI 音乐 20 credit/首；另有 Suno-to-Video 工具（导入 Suno 曲目） | ✓ | ✅ 长度自动匹配 |
| AI 图像 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✅ GPT Image/Nano Banana |

> **注**: OpusClip 的 Video Dubbing（官方 changelog 2026-07-07："translate and dub your videos into 25 languages using a clone of your own voice… no separate setup or voice training"）是它 2026 年最重要的能力补全——从"剪辑工具"补齐"译制"环节，与我们的 voice-clone dubbing（MiniMax，PRD §5.1）进入同一战壕。声音克隆本体在 Agent Opus 中 2025 年底已有，但配音化是全新的（2026 年 4-5 月第三方实测仍为"无配音"）。Round 2 的 Opus 卡片需要单独深拆这一项。

### G. 文案与知识资产 ⭐（与我们定位最相关）

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 社媒短文案（标题/hashtag） | ✓ | ✓ | ✓ | ✓ AI caption | ✓ | ✓ 脚本 | ✗ |
| 长文 / 博客 / newsletter | ✗ | ~ blog posts（被评价为"通用腔"） | ✗ | ✗ | ~ blog-to-video 反向 | ✗ | ✗ |
| Quote card / 图文轮播 | ✗ | ~ AI 图像可凑 | ✗ | ~ Canva 模板 | ~ | ~ AI 图像可凑 | ~ MG 引擎可生成 |
| 说话人风格学习（persona） | ~ brand vocabulary | ~ **Brand Studio + 转写术语表 + 勿译词表**（团队品牌资产，勿译词表限 Business+；见 §4.3 第 2 条） | ~ 词典 | ✗ | ✗ | ✗ | ✗ |
| **多语言原生文案** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

### H. 翻译与配音

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 字幕翻译 | ~ | ✅ **67 语言 + 校对视图** | ✓ Pro 档 | ✗ | ✓ | ✗ | ✗ |
| 配音/口型 | ✓ 25 语配音 + 原声克隆（2026-07，Pro/Business） | ✅ **28 语配音**（营销口径 30）+ 勿译词表（Business+） | ✗ | ✗ | ✓ 70+ 语言配音 | ✗ | ✗ |

> **多语言质量陷阱注记（语言数量 ≠ 质量）**:
> - Submagic 的 RTL 语言（阿拉伯语/希伯来语/乌尔都语/波斯语）字幕渲染损坏——2026 年多家评测报告，与其官方"支持 RTL"的营销直接矛盾（"多年未修"一说未证实，公司 2023 年才成立）
> - Descript 多说话人串话场景转写准确率降至 ~80%（该数字源自竞品 Sonix 的评测，有偏差风险，但有独立评测佐证方向）；专有名词/品牌名需手动修正——其"转写术语表"功能正是为补这个洞而存在
> - 各家宣传的语言数普遍是"能跑"而非"能用"
>
> 这些证据直接支撑我们 §4.3 第 3 条"母语级知识文案"的叙事——竞品的"N 种语言"是营销数字，我们要承诺的是**每种语言都过母语审校级质量**，宁可少而精。

### I. 发布与分发

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 原生调度发布 | ✅ 6 平台 | ~ YouTube + 播客托管 | ✓ 3 平台（新） | ✅ **15+ 平台** | ✓ 3 平台 | ✗ 下载自发 | ✗ 纯导出 |
| **LinkedIn 发布** | ✓ 仅企业号 | ✗ | ✗ | ✅ 个人 + 公司页 | ✗ | ✗ | ✗ |
| 自动化规则（源→目标） | ✗ | ✗ | ✗ | ✅ 核心能力 | ✓ Auto-Mode Workers | ✗ | ✗ |

### J. 团队 / API / Agent 接入

| 能力 | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 团队工作区 | ✓ | ✓ | ✓ | ✓ Agency | ~ | ✗ | ✗（路线图） |
| 公开 API | ✅ + 6 SDK | ✓ 2026 beta | ✓ 2025-07 | ✗ | ✓ | ✗ | ✗ |
| MCP / agent 插件 | ✅ MCP + Claude/Codex skill | ✅ Claude/ChatGPT 连接器 | ✗ | ✗ | ✓ MCP + CLI | ✗ | ✅ **原生 MCP + Codex/ChatGPT 插件** |
| 模型选择 | 自研模型 | ✓ **Underlord 模型选择器**（2025-10 起，Claude/GPT/Gemini 全系，会话级切换；按子任务自选为未来计划） | ✗ | ✗ | ✓ 多生成模型按名暴露 | ✗ | ✓ 多生成模型 |

### K. 定价与合规

| | Opus.pro | Descript | Submagic | Repurpose.io | Revid.ai | Crayo | ChatCut |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 免费档 | 60 分钟/月 | 60 分钟/月 | 3 视频/月 | 14 天试用 | ✗ | ✗ | ✓ |
| 入门价 | $15/月 | $16–24/月 | ~$19/月 ⚠️ | $35/月 | $39/月 ⚠️ 定价频繁变动 | $19/月 | $25/月 |
| 主力档 | $29/月 | $24–35/月 | $40/月 | $79/月 | $99/月 | $39/月 | $100/月 |
| 计量方式 | 源视频分钟数 | 媒体分钟 + AI credit 双表 | 视频条数 + 时长上限 | 发布条数（基本不限） | AI credit | credit + 导出时长 + VEO3 单独计费 | credit |
| **用户反弹焦点** | 处理卡死投诉集中；**取消订阅后项目不可访问（即使积分仍有效）**；取消流程被批故意多步、取消后仍扣费 | 2025-09 双表改制引发老用户反弹（有用户账单 $30→$195/月；**不滚存为官方政策**；失败任务扣 credit 为用户报告级） | 预览/导出漂移；续费/取消投诉 | — | **失败生成照扣 credit**（Trustpilot 集中投诉；退款靠客服裁量，无官方自动返还政策） | **官方退款政策白纸黑字 ALL SALES FINAL**；无免费试用；取消后仍扣费投诉 | — |
| SOC 2 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **EU 数据驻留** | **✗ 全员空白** | ✗ | ✗（法国公司，声明 GDPR 但官方隐私政策写明服务器在美国） | ⚠️ 未知 | ✗（法国公司，数据存美国） | ⚠️ 实体不明 | ✗ |

---

## 3. 分类型总结（六类范式）

七家竞品可清晰归入 **六种产品范式**。同类内部功能雷同度极高，跨类才是真正的能力差异所在。

> **范式短名（下游文档统一引用）**: `Pipeline` / `Editor` / `Caption` / `Factory` / `Chat` / `Distribution`。`research/` 竞品卡片与 `DECISION_MATRIX.md` 以此标注范式来源。

### 类型 1：Pipeline（切条流水线）— Opus.pro
- **范式**: 链接/上传 → AI 选段打分 → reframe + 字幕 → 审核 → 一键发全平台
- **壁垒**: ClipAnything 全体裁理解、**Virality Score（七家独有）**、最宽的输入源
- **2025–2026 扩张清单（向 B 端基础设施与全链路走的信号）**: Agent Opus（文本/链接 → 成片）、**OpusSearch**（企业级视频语义搜索，2025-03 随软银投资发布；企业 API 存在但产品本体为 waitlist 制）、MCP + 6 SDK、**25 语声音克隆配音**（2026-07）、AI 音效一键自动铺点（2026-07）、**Android app**（2026-07）、生成式 B-roll 规模化（Pro 50 条/天）——品类边界在快速模糊化
- **对我们的意义**: 品类正面对标（ADR-014 已确认）；其弱点=学术内容理解浅、20-40% 废片、美国数据处理 — 全部已被 PRD §3.4 锁定

### 类型 2：Editor（文档式编辑器）— Descript
- **范式**: 转写即编辑界面；AI（Underlord）是副驾而非流水线
- **壁垒**: 编辑深度最全（录制→剪辑→配音→头像→发布）、**67 语言字幕翻译 + 28 语言配音（七家最强多语言）**、声音克隆、Underlord 模型选择器（Claude/GPT/Gemini）
- **离 persona 最近的半步**: Brand Studio + 转写术语表 + 勿译词表是七家中最像"风格保持"的东西——但它是**团队品牌资产**（统一术语与品牌词，且勿译词表限 Business+），不是**个人文风学习**；它保证"不说错词"，不保证"说得像我"
- **对我们的意义**: 交互北极星（ADR-016 已确认）；其转写只有 26 种拉丁字母语言、文案生成是英文通用腔 — 我们的"母语级多语言 + persona"仍有空位

### 类型 3：Caption（字幕增强器）— Submagic
- **范式**: 动态字幕做到极致（48 语言、Hormozi 风格），切条是 +$19/月的加购
- **壁垒**: 字幕美学 + 轻量 AI 清理（去静默/去废镜/眼神校正）
- **软肋**: 预览/导出漂移、RTL 语言渲染损坏——"字幕之王"也有质量死角
- **对我们的意义**: 证明"字幕"单独就能撑起可观 ARR（CEO 自述 $8M，2025-06 GetLatka 访谈，无审计验证 ⚠️）— 但也说明它已是 commoditized 能力，不能当我们的卖点；其法国身份值得注意（声明 GDPR 但服务器在美国，见 §4.3）

### 类型 4：Factory（生成式短视频工厂）— Revid.ai + Crayo.ai
- **范式**: 无源素材，prompt/URL/Reddit 链接 → 脚本 + 配音 + 背景画面 → 竖屏成片
- **壁垒**: 病毒格式模板库（Reddit 故事、假短信、分屏 gameplay）、生成量大、便宜；Revid 按名暴露 Veo 3/Sora 2/Seedance 并明码标价，是"生成模型超市"路线；Crayo 的 VEO3 也单独计费（VEO3 Credits $50/5 个）
- **软肋**: 无真实素材理解、无审核深度、Crayo 实体不透明 + 官方 all sales final、Revid 定价频繁变动 + 失败也扣 credit
- **对我们的意义**: **基本不构成竞争** — 服务"无脸流量农场"，与知识资产化定位正交；可借鉴的是 Auto-Mode Workers（定时自动生产）和 Revid 的**渲染前免费成本估算**（公开 calculate-credits API/CLI/MCP，官方文档确认，见 §4.4）

### 类型 5：Chat（对话式编辑器）— ChatCut
- **范式**: 自然语言指令 → 在**真多轨时间线**上执行可编辑操作；随时可手动接管
- **壁垒**: NL 编辑 + 多轨兼得、原生 MCP/Codex 插件（agent 时代的接入面）、XML/SRT 交接 NLE
- **对我们的意义**: 代表"AI 编辑"的下一交互形态（与 Underlord 同向）；其"每条指令都是时间线上可撤销的真实操作"与我们 project-scoped chat（PRD §5.1）的设计哲学一致，值得做 Round 2 深拆

### 类型 6：Distribution（分发自动化）— Repurpose.io
- **范式**: Workflow = 源 → 转换 → 目标平台的自动化规则；**零 AI 生成**
- **壁垒**: 15+ 平台的目的地覆盖（含 Snapchat/Pinterest/Bluesky/Amazon）、RSS/Zoom/Drive 自动轮询、定价不按量计费
- **对我们的意义**: "源→目的地规则引擎"是分发阶段的参照系；**LinkedIn 个人 + 公司页发布**七家中只有它和 Opus 支持 — 正好是我们的核心渠道，验证了我们做 LinkedIn 直发的必要性（PRD 已列 deferred）

---

## 4. 关键结论（雷同点 vs 空白点）

### 4.1 已 commoditized —— 做了不算卖点，不做是缺陷
1. **动态字幕 + 关键词高亮 + emoji**：七家全有，Submagic 是天花板
2. **AI 高光切条**：五家有（Opus/Descript/Submagic/ChatCut 各成一派），唯有 Opus 有打分
3. **自动竖屏 reframe + 人脸/说话人追踪**：七家全有
4. **文本驱动编辑**：四家有，Descript 开创、Submagic/ChatCut 跟进
5. **去静默/去口头禅**：几乎全有
6. **TikTok/YouTube/IG 三件套发布**：五家有

### 4.2 2025–2026 行业级新趋势（值得跟踪）
1. **集体转向 agent 接入面**：Opus（MCP + 6 SDK）、Descript（Claude/ChatGPT 连接器）、Revid（MCP + CLI）、ChatCut（原生 MCP + Codex 插件）— 一年内四家上线 MCP，"被 AI agent 调用"正在成为新分发渠道
2. **AI 副驾多步编辑**：Underlord / Agent Opus / ChatCut — "说一句复杂指令，AI 规划并执行多步"正在取代单点 AI 按钮
3. **生成式媒体内建化**：AI B-roll/音乐/图像从"集成第三方"变为标配内建
4. **自动发布扩容**：Submagic 2026 年才补上发布，说明"切条工具 → 全链路"是共同演化方向
5. **Bring-your-own-frontier-model**：Descript 的 Underlord 模型选择器（2025-10 起，Claude/GPT/Gemini 会话级自选，付费档解锁高级模型）、Revid 按名暴露 Veo 3/Sora 2/Seedance 并明码标价 — 竞品开始把"用什么模型"交给用户/市场，对单模型架构的我们是需要持续跟踪的参照（灵活性与成本透明 vs 体验一致性的权衡）

### 4.3 七家全空白 = 我们的护城河候选（与 PRD 定位互证）
1. **EU 数据驻留**：七家全部空白。唯二的两家欧洲公司数据照样跨境——Submagic（法国）官方隐私政策写明"our servers are located in the United States"，Revid（法国）自述数据存 GCP 美国 — "欧洲公司 ≠ 欧洲数据"，我们的 EU residency 叙事依然独占
2. **说话人 persona 学习**（"听起来像我"）：需要诚实承认——Descript 的 Brand Studio + 术语表 + 勿译词表已走出半步，但那是**团队品牌资产管理**（保证"不说错词"），不是**个人文风学习**（保证"说得像我"）；Opus 的 brand vocabulary 同理。真正的 speaker voice 建模依然无人做
3. **多语言原生知识文案**（非翻译腔的 LinkedIn 长文/newsletter）：七家全空白；Descript 的 blog post 生成是英文通用模板。且竞品普遍存在质量陷阱（Submagic RTL 渲染损坏、Descript 多说话人 ~80%）——"语言数量"是营销数字，"母语级质量"无人承诺
4. **学术/知识内容深度理解**：无一家针对（Opus 官方定位就是娱乐向全体裁）
5. **LinkedIn 优先的渠道策略**：发布功能里 LinkedIn 长期是二等公民（Opus 仅企业号、Descript 没有、Submagic 没有）

### 4.4 需要注意的反直觉发现
- **Virality Score 七家只有 Opus 一家做** — 不是"人人有之的标配"。我们改造为"传播潜力分"时，竞争对手事实上只有一家
- **Submagic 的 Magic Clips 是 +$19/月/人的加购** — 说明"长视频切条"在字幕品类里是增值项而非基础项，侧面印证切条 pipeline 与增强器是两种生意
- **Repurpose.io 完全没有 AI 切条** — 它证明了"分发自动化"可以脱离内容智能独立成立；我们未来做 LinkedIn 直发时，它才是对标，而不是 Opus
- **计费模式是全行业共同的信任伤口，透明定价本身就是差异化机会** — OpusClip 处理卡死投诉集中、取消订阅后项目不可访问（即使付费积分仍有效）、取消流程被批故意多步；Descript 2025-09 双表改制引发老用户反弹（有用户账单从 $30 跳到 $195/月；不滚存是官方政策）；Revid 失败生成照扣 credit（退款只能靠客服裁量）；Crayo 官方白纸黑字 ALL SALES FINAL。可借鉴的缓冲设计：Revid 的**渲染前免费成本估算**（公开 calculate-credits API/CLI/MCP，官方文档确认）——用户先看到价再点生成。我们的定价设计原则应是：可预期 > 便宜，失败不扣费、成本先告知
- **Descript 关闭 YouTube 链接导入（2025-12，官方确认）** — 头部玩家被平台反爬逼退，说明链接抓取是"高价值高维护"功能；我们 FR-018 若做，须预留反爬对抗成本，或优先做 Zoom/Drive/RSS 等平台不反爬的源
- **OpusClip 的配音化（2026-07）是最新威胁信号** — 它把"声音克隆 + 25 语配音"做成了一键功能且无需训练，正好压在我们的 voice-clone dubbing 赛道上；我们的差异只剩"知识文案 + persona + EU 驻留"的组合，单靠配音不再是差异点

---

## 5. Round 2 产出索引（已完成）

1. **单竞品分析卡 × 7**（基础信息 / 核心流程逐步还原 / 功能逐项打分），存放 `research/`：
   - 深拆：[opusclip.md](research/opusclip.md)（含 Video Dubbing 与 OpusSearch 专节）、[chatcut.md](research/chatcut.md)（对话式编辑模型与 MCP 接入面专节）、[descript.md](research/descript.md)（Underlord 模型选择器与多语言栈专节）、[submagic.md](research/submagic.md)（字幕引擎死角与欧洲身份虚实专节）
   - 简版：[repurpose.md](research/repurpose.md)、[crayo.md](research/crayo.md)、[revid.md](research/revid.md)
2. **横向决策矩阵**（核心交付物）：[DECISION_MATRIX.md](DECISION_MATRIX.md) — 40 个功能点 × 七家有无 × 对我们的价值 × 决策（采纳 22 / 改造 9 / 放弃 9）× 优先级 × 现状（对齐 ADR）× 依据
3. **渲染技术栈专项**：[research/RENDERING_TECH.md](research/RENDERING_TECH.md) — 七家渲染/预览/字幕实现取证（Submagic 与 ChatCut 确认全栈 Remotion；OpusClip 自研 GPU + EditingScript 与 clip-spec 同构；Descript 客户端 WebCodecs 派）
3. **文档治理**：本文件为竞品事实唯一入口；PRD §3.4 已标注 superseded（2026-07-19）并链接至此；`research/opusclip-deep-dive.md` 保留为 Opus 单家流程深拆的引用源。竞品能力变化时先改本文件事实层，再同步决策矩阵

---

## 附录：信息可信度备忘

- Repurpose.io 官网对抓取返回 403，其定价/功能经第三方快照交叉验证；HQ 与 GDPR 声明未能验证 ⚠️
- Crayo.ai 定价页为 JS 渲染，价格取自多个第三方评测，数字近似 ⚠️；用户量（3.2M）与营收（$7.2M ARR）均为自述；**VEO3 单独计费已经官方购买弹窗证实**（VEO3 Credits $50/5 个，"VEO3 is paid-only"）
- Revid.ai 定价 2026 年内多次变动，Growth 档 $99 vs $39 促销价并存 ⚠️；官网有 Suno-to-Video 工具页（导入 Suno 曲目成片），但其自研音乐生成（20 credit/首）未声称由 Suno 驱动；calculate-credits 免费预估 API 经官方文档证实
- ChatCut 字幕语言数官网两处自相矛盾（100+ vs 32）⚠️；XML/SRT 导出经官方页面证实；ProRes 仅"limited 1080p"、4444 alpha 未证实 ⚠️；融资 $1.35M（真格领投/Antler 跟投，2025-10-22）经 TechNode Global + Antler 官方博客证实
- OpusClip 并未正式更名 Opus.pro — opus.pro 是品牌家族扩张（OpusSearch / Agent Opus），剪辑产品仍叫 OpusClip；Video Dubbing（25 语 + 自动声音克隆，Pro/Business，10 credit/分钟）经官方 changelog + 帮助文档证实（2026-07-07）
- OpusClip 积分政策的官方口径：取消订阅后**积分保留至原到期日**（月度 60 天/年度 12 个月）；免费档导出 3 天过期；"取消后 3 天积分清零"一说与官方政策冲突，未予采信
- OpusSearch 产品真实（2025-03 随软银投资发布），企业 API 存在但产品本体为 waitlist 制，非自助公开 API
- Submagic "$8M ARR" 为 CEO 在 GetLatka 访谈（2025-06）自述，无第三方审计 ⚠️；其"服务器位于美国"为官方隐私政策原文
- Descript 语言数字（2026-07 官方值）：转写 26（官方口径拉丁字母限定，列表已含希腊语/印地语 beta）；字幕翻译 67；配音帮助文档列表 28 vs 营销页 "30"
- Descript "多说话人 ~80% 准确率"数字源自竞品 Sonix 的评测，方向有独立佐证但精确值有偏差风险 ⚠️
- 各竞品用户数字均为厂商自述，仅供量级参考
