# 竞品卡片：Opus.pro / OpusClip

> **范式**: Pipeline（切条流水线）· **优先级**: 深拆 #1 · **更新**: 2026-07-19
> **事实基础**: 官网/定价页/官方 changelog/帮助文档（2026-07 核查），详见 `../COMPETITIVE_ANALYSIS.md` 及附录可信度备忘；单家流程拆解另见 `./opusclip-deep-dive.md`

---

## 1. 基础信息

| 项 | 内容 |
|:---|:---|
| 定位一句话 | 长视频 → 批量病毒式短视频的 AI pipeline，一键发全平台（自称 "world's No.1 AI video agent"） |
| 目标用户 | 播客、网红、营销团队、媒体公司、代理商（宣称 16M+ 用户） |
| 公司 | 美国加州（Palo Alto/Mountain View），2022 年创立；2025-03 软银愿景基金 2 期投资 |
| 商业模式 | 订阅 + credit 计量（1 credit = 1 分钟源视频）：Free 60/月 · Starter $15/150 · Pro $29/300 · Business 定制；年付约 5 折；月 credit 60 天有效、取消订阅后保留至原到期日（官方政策） |
| 免费档 | 60 分钟/月，水印，仅 9:16，导出 3 天过期，无打分无编辑 |
| 数据驻留 | GCP **美国**；GDPR 靠 SCC + 欧美数据隐私框架；SOC 2 Type II；EU 用户可邮件 opt-out 训练数据使用 |
| 平台 | Web 应用 + API/MCP + Android app（2026-07，iOS 先有） |

## 2. 核心流程逐步还原

```
输入 → 配置 → 生成 → 审阅/编辑 → 导出/发布
```

1. **输入**：粘贴链接或上传。16+ 源：YouTube、Google Drive、Vimeo、Zoom、Rumble、Twitch、Facebook、LinkedIn、X、Dropbox、Riverside、Loom、Frame.io、StreamYard、Kick、公开 mp4 URL、本地上传（Free/Starter 10GB，Pro+ 30GB）
2. **配置**：处理时间段滑块（只烧选中区间的 credit）、clip 长度预设（0-1m 至 10-15m）、体裁选择；Pro 档加 Topics 搜索与 **prompt-to-clip**（自然语言指定切什么），支持 reprompt 重试
3. **生成**：ClipAnything 模型（视觉/音频/情感线索，支持游戏/体育/vlog 等非 talking-head 体裁）选段 → ReframeAnything 竖屏化（物体追踪）→ 动态字幕 + hook + B-roll → 每条 clip 附 **Virality Score**
4. **审阅/编辑**：按分数排序的结果页；内建编辑器（文本编辑 + 简易时间线，Starter+）；字幕文本编辑；品牌模板套用
5. **导出/发布**：MP4 下载、批量导出、XML 导出 Premiere/DaVinci（Pro+）、可分享项目链接；原生调度直发 YouTube/IG/TikTok/FB/**LinkedIn（仅企业号）**/X

## 3. 功能清单逐项打分

借鉴价值 = 对我们（知识资产化/LinkedIn/多语言/GDPR 定位）的价值，非其自身质量。

| 功能 | 借鉴价值 | 备注 |
|:---|:---|:---|
| AI 高光切条（ClipAnything） | **高** | 品类标杆；但学术内容理解浅、废片率 20-40% 是公认弱点 |
| **Virality Score** | **高（需改造）** | 七家唯一；opaque 单分、娱乐向品味——改造为可解释的知识受众传播潜力分 |
| prompt-to-clip / reprompt | **高** | "帮我找讨论定价的片段"——与我们 project chat 天然契合 |
| 处理时间段滑块（只烧选中区间 credit） | **高** | 成本透明的优秀交互，1 小时素材先试 10 分钟 |
| 输入源广度（16+） | 中 | 价值高但维护重；Descript 已被 YouTube 反爬逼退，需选择性做 |
| 动态字幕模板 + 关键词高亮 | 中 | 已是标配，追平即可 |
| ReframeAnything（物体追踪） | 低 | ADR-016 已定人脸追踪为 L3 不做；静态 crop 够用 |
| 品牌模板（字体/色/logo/intro-outro） | 中 | 我们品牌模板页已有对应物 |
| 原生调度发布 6 平台 | 中 | LinkedIn 仅企业号——正好留出我们"个人+公司页"的空间 |
| XML 导出 NLE（Pro+） | 中 | 与我们"L3 交给 CapCut/Premiere"的 handoff 策略一致，P2 |
| 团队工作区 / API / MCP | 中（P2） | 2026 年快速补齐的 agent 接入面，趋势信号 |
| 说话人字幕着色 | 低 | 仅 Business 档，非核心 |

## 4. 深拆：Video Dubbing（2026-07-07 上线）

- **能力**：25 语配音翻译，**自动克隆源视频原声**，无需单独训练或设置；一键批量配音
- **官方原文**："translate and dub your videos into 25 languages using a clone of your own voice… No separate setup or voice training is required"
- **语言**：EN/DE/ES/FR/PT/IT/NL/RU/PL/ID/UK/SV/TR/NO/HR/RO/SK/EL/DA/FI/HU/CS/JA/KO/VI
- **档位与计量**：Pro 与 Business 专享，**10 credit/分钟**（= 源视频 10 倍速烧钱，重计费项）
- **背景**：声音克隆本体 2025 年底已在 Agent Opus 中存在；配音化是全新的（2026 年 4-5 月第三方实测仍为"无配音"）
- **对我们的冲击与应对**：
  - 直接压在我们 voice-clone dubbing（MiniMax，PRD §5.1）赛道上——**单靠配音不再是差异点**
  - 它的配音是"译制视频"，我们的是"知识资产的多语言版"（配音 + 母语级文案 + persona 保持的组合）；且 10 credit/分钟的重计费 + 美国数据处理给我们留出"透明定价 + EU 驻留"的正面战场
  - 需跟踪：其配音质量是否过"审校线"、是否支持术语表（暂未见）

## 5. 深拆：OpusSearch（2025-03 发布）

- **能力**：企业级视频语义搜索——自然语言检索视频库内容（People/Topics/Mood/Duration 过滤），"instantly search and reuse anything in their video catalogs"
- **形态**：产品本体为 **waitlist 制**（面向专业创作者/企业）；另有企业 API（2026-03 官方博客确认，语义搜索视频库）；技术底为 Milvus + RAG（Zilliz 工程文佐证）
- **信号意义**：Opus 正从"C 端切条工具"向"**B 端视频理解基础设施**"走——与软银投资同日发布不是巧合
- **对我们的意义**：机构用户（高校/智库/大会主办方）的 back-catalog 资产化正是我们的目标场景；OpusSearch 验证了这个需求存在且无人做好。我们的差异：搜索不是终点，搜索到的片段可直接进入知识资产生成 pipeline

## 6. 用户投诉与信任伤口（定价/交付）

- **处理卡死**：长时间挂起甚至永不完成，是 Trustpilot 集中投诉点（"#1 投诉"一说源自竞品评测，未独立证实，但卡死投诉确实密集）
- **取消后项目锁死**：订阅失效后项目不可访问——即使付费积分仍有效（官方政策积分保留至原到期日，但项目进不去）
- **取消流程**：被批故意多步、取消后仍扣费的投诉存在（Trustpilot 4.0-4.1 分，两极分化）
- **教训**：生成失败必须退费/不扣费；订阅结束后用户资产（项目/导出）必须保持可访问——写进我们的计费原则

## 7. 一句话总结

Opus 是品类定义者也是我们唯一的正面对标：它验证了"打分 + 批量切条 + 直发"的需求，但它的品味是娱乐的、数据是美国的、文案是没有的、配音是刚补的——我们的生存空间恰好全在它的盲区里。
