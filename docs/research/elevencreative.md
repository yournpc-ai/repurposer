# ElevenCreative（ElevenLabs 创意套件）— 产品调研卡

> Status: Active（2026-07-22 建立）
> 证据来源：用户实测截图 9 张（2026-07-21）+ 官方发布文与公开报道（见文末来源）
> 产品定性：**ElevenLabs（语音模型厂商）的创意套件产品线**——音频自研，图像/视频全部聚合第三方模型。引用时不要把 ElevenCreative 与 ElevenLabs 混用（同 Agent Opus ≠ OpusClip 的规矩）。

## 0. 一句话

语音模型独角兽（$500M Series D，$11B 估值，2026-04）把 35+ 第三方图像/视频模型 + 自家音频栈包装成**编排层转售商**：composer 首页 + Flows 节点画布 + 模板 + 企业合规 SKU，按 credit 计费。与我们的关系：**不同物种**（Factory/无中生有派 vs 真实演讲素材派），但 Flows 与合规包装是两面值得对着照的镜子。

## 1. IA 全图（截图实测）

侧边栏：主页 / 音色(+) / 工作室 / **流程（Flows）** / 模板 / 资产；已固定工具：文本转语音、音效、图像和视频、人声分离、变声器、音乐、语音转文本、配音、更多工具。顶栏按模态切换：语音 / 图像 / 视频 / 音效 / 音乐 / 变声器 / 人声分离 / 升级 / 更多工具。

主页 = composer（模型+音色选择器："Eleven Multilingual v2 · Roger - Laid-Back, Casual, Resonant" + 快捷意图 chips"讲述一个故事/讲个笑话/录制广告/引导冥想"）+ 配音 V2 alpha 推广卡（92 语种、自动语音克隆、保留情感）+ 模板区。

Onboarding 两问（均可跳过）：用途多选（TTS/有声书/音乐/音效/配音/旁白/语音克隆/STT/图像视频/播客）→ 身份多选（个人/创作者/内容业务/配音演员/工程师/营销/教育/其他）。

## 2. 深拆一：合规做成具名 SKU（截图 + 公开证据）

企业页把合规列为具名象限（不是徽章墙）：**Data Residency options / HIPAA attestation / Zero Retention mode / SOC 2 Type II, ISO 27001**，外加 SSO、审计日志、主服务协议（MSA）、商业权益与知识产权保护、音频工程与训练、托管服务与专业支持。

公开证据补全：

- **认证矩阵**：SOC 2 Type II（零例外）+ SOC 3、ISO 27001/27017/27018/42001、PCI DSS L1、GDPR（独立评估）、CSA STAR L1、AIUC-1；Trust Center 公开（compliance.elevenlabs.io），DPA 公开
- **Zero Retention mode（ZRM）**：处理后不留存输入/输出音频；**HIPAA 合规 = ZRM 开启 + 签 BAA**；声称从不用客户数据训练
- **Data residency**：US / EU / India 区域选项，**Enterprise 档专属**
- **Enterprise 档另有**：自定义 SSO / SLA、forward-deployed 工程师、VPC/on-prem 部署（2026-04 上线）、定制安全评审
- **关键门槛**：HIPAA / ZRM / residency 全部锁在 Enterprise 定制报价之后，非自助——中端受监管客户被迫跳档

**对我们的意义**：合规从"安全页徽章"升级为"定价页上有名字的开关"——正是 STRATEGY §2.3"信任当产品做"的呈现野心参照。HIPAA 与我们无关（医疗）；residency / zero-retention / 审计日志分别对应 ROADMAP §7 各行。

## 3. 深拆二：Flows——节点画布编排（截图 + 官方发布文）

官方定性（2026-03-11 发布）："node-based canvas"，35+ 图像/视频模型 + 全套 ElevenLabs 音频栈（TTS / 语音克隆 / lip-sync / SFX / 音乐）在同一画布链接成端到端管线；2026-06-04 发布 **Flows Agent**（agent 参与建流）；程序化触发 API waitlist 中。

**四个机制（截图实证 + 官方原文）**：

1. **显式 DAG**：节点 = 一次生成调用，卡片上带模型+参数 chip（实测：Nano Banana Pro 9:16 1K / Kling 3.0 专业版 1080p 4:5 / Topaz 图像放大 1536×2752）
2. **@ 引用槽位**：prompt 内 `@character` / `@outfit` 引用上游节点输出 = 节点间类型化数据流；源素材节点（产品图/参考照）带"从这里运行"，可整体替换后重跑
3. **节点级重跑**：官方原文 "rework any individual step without regenerating the full pipeline"
4. **一键成模板**：画布顶栏"创建模板"按钮 + 官方 "Build once, then run it as many times as needed with different inputs" + 批量执行（系统性换输入测变体）+ 创作者共享 Flows 可 remix

辅助界面：画布底部常驻 chat 输入条（"为场景添加背景音乐…"）——自然语言扩展图。

**本质**：确定性编排，无 agent 决策——用户要懂模型名、自己接线、逐节点 debug。官方目标用户：广告 / 播客 / 效果营销团队——AI 内容工作室的**操作员工具**（ComfyUI 平民版）。Flows Agent 的出现说明他们自己也意识到了操作员天花板，正在向"agent 编排"补票——佐证我们"agent 当编排者、人当审阅者"的方向是行业收敛点。

## 4. 计费参照

| 档 | 价格 | 备注 |
|---|---|---|
| Free | 10k credits/月 | 自助 |
| Starter | $6/月 | |
| Creator | $11/月 | |
| Pro | $99/月 | |
| Scale | $299/月 | |
| Business | $990/月 | |
| Enterprise | 定制 | **合规 SKU 全锁此档** |

## 5. 可吸收（手艺层）

| 机制 | 我们的翻译 |
|---|---|
| DAG 作为生成表征 | **内化**：RunPlan 持久化（ADR-028），agent 编排，用户看步骤清单 |
| @ 引用类型化槽位 | 配方的输入槽位（演讲视频=必填 / slides=可选，STRATEGY §5） |
| 节点级重跑 | 步骤级重跑（L3 寻址控制，STRATEGY §2.5） |
| 一键成模板 + 批量换输入 | 配方 = run-plan 模板；成功 run 回流成模板（Gallery Phase 2） |
| 合规具名 SKU | ROADMAP §7 各行的呈现形态（STRATEGY §2.3） |

## 6. 不吸收（防军备）

- **节点画布 UI**：不同物种的形态；我们的"flow"呈现为步骤清单，不是画布
- **模型名外露**（每节点挑模型）：模型超市 = 转嫁选择焦虑，DECISION_MATRIX §I 已判（💡 后排）；多模型路由走 ADR-025 抽象，用户只见步骤名
- **自由生成 DAG 编辑 / Factory 范式**：AI 剧与广告工作室的战场；我们是真实演讲素材派（DECISION_MATRIX §F "AI 视频生成" 💡 后排不变）

## 7. 战略镜子

- 它是**广度对冲**（一个画布聚合 35+ 模型按 credit 转售），我们是**深度对冲**（一条工作流打到底）——卖大宗商品的中间商会被上游吃掉（STRATEGY §1 判断 1）；Flows 是把"转售"做成基础设施的教科书动作，恰恰验证我们不进 Factory 红海的判断
- 合规 SKU 化证明"信任当产品卖"已是头部玩家的标准动作——我们的 EU 窗口（STRATEGY §4 风险 1）真实且有时限
- 我们的物种优势是 agent 原生：不需要像 Flows Agent 那样给画布补票

## 来源

- [Introducing Flows in ElevenCreative（官方博客，2026-03-11）](https://elevenlabs.io/blog/introducing-flows-in-elevencreative)
- [Introducing Flows Agent in ElevenCreative（官方博客，2026-06-04）](https://elevenlabs.io/blog/introducing-flows-agent)
- [ElevenLabs Flows 落地页](https://elevenlabs.io/flows) / [中文页](https://elevenlabs.io/zh/flows)
- [ElevenCreative Flows 官方文档](https://elevenlabs.io/docs/eleven-creative/products/flows)
- [ElevenLabs Launches Flows（createwith 报道）](https://www.createwith.com/tool/elevenlabs/updates/elevenlabs-launches-flows-a-node-based-creative-canvas-for-unified-ai-content-pi)
- [ElevenLabs on Opper — ZDR / 训练姿态 / GDPR DPA](https://opper.ai/provider/elevenlabs)
- [ElevenLabs $500M Series D / $11B 估值（agentmarketcap，2026-04）](https://agentmarketcap.ai/blog/2026/04/10/elevenlabs-500m-series-d-11b-valuation-voice-ai)
- 用户实测截图 9 张（2026-07-21）：首页 IA / onboarding 两问 / 企业合规页 / Flows 营销页 / Flows 画布与节点细节
