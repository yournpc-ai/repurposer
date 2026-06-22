# 架构决策记录（ADR）

## ADR-001：使用单仓库简单目录结构

**状态**：已决策

**背景**：需要同时管理 Python 后端和 Node.js 前端。

**决策**：使用单仓库，前后端分目录，不引入 Turborepo/Nx/Pants 等 monorepo 工具。

```
repurposer/
├── apps/api/
├── apps/web/
├── docs/
└── scripts/
```

**原因**：
- P0 阶段前后端交互简单，没有大量共享代码
- 各用各的包管理器（uv / pnpm），互不干扰
- 用 `Justfile` 或 `scripts/dev.sh` 协调启动即可
- 避免引入不必要的工具学习成本

**替代方案**：
- Turborepo：不适合 Python
- Nx：不是 Python 原生
- Pants/Bazel：太重
- 多仓库：不方便同步改动

---

## ADR-002：后端使用 FastAPI

**状态**：已决策

**决策**：后端使用 FastAPI。

**原因**：
- 自动生成 OpenAPI 文档
- 原生支持 Pydantic，适合结构化输出
- 异步性能优秀
- 团队熟悉

---

## ADR-003：核心智能层使用 MiniMax M3

**状态**：已决策

**决策**：核心 LLM 使用 MiniMax M3。

**原因**：
- 1M 上下文，可吞入演讲稿 + 过往材料 + 示例
- 原生多模态，可处理图片
- 支持结构化输出
- 国内访问稳定

**风险**：
- 如果输出质量不稳定，可能需要 fallback 到其他模型

---

## ADR-004：手搓 Agent 工作流

**状态**：已决策

**决策**：P0 不引入 Pydantic AI / LangGraph / CrewAI 等 Agent 框架，自研 Agent 编排器。

**原因**：
- 单模型（MiniMax M3），不需要 provider 抽象
- Workflow 明确固定：persona → analyze → script → review → revise → HITL
- Prompt 需要精细控制，框架模板可能不够灵活
- 白盒调试更方便

**未来**：如果 P2 workflow 变得非常复杂，再评估 LangGraph 或 Pydantic AI。

---

## ADR-005：Python 包管理使用 uv

**状态**：已决策

**决策**：Python 项目使用 uv 作为包管理器。

**原因**：
- 速度快
- 现代 Python 工作流（lock 文件、venv、run 一体化）
- 适合新项目

---

## ADR-006：前端使用 TanStack Start + TypeScript

**状态**：已决策

**背景**：P0 是内部验证，但未来目标是 SaaS 产品，需要为产品化打好基础。

**决策**：前端使用 TanStack Start + TypeScript。

**原因**：
- 部署平台无关，不绑定 Vercel
- 端到端类型安全强
- 显式服务端/客户端边界，减少 hydration 和密钥泄漏问题
- 为未来 SaaS 产品化做准备

**风险**：
- 框架较新，生态比 Next.js 小
- 团队学习成本
- AI 编码工具对 TanStack Start 支持较弱

**缓解**：
- P0 功能简单，用不到复杂特性
- 文档完善，核心概念清晰

---

## ADR-007：API 类型同步使用 OpenAPI

**状态**：已决策

**决策**：前后端不维护共享类型包，前端类型从后端 OpenAPI 生成。

**原因**：
- 减少共享包维护成本
- 后端是类型权威来源
- 使用 `openapi-typescript` 自动生成

---

## ADR-008：视频渲染先用图片轮播 + 字幕

**状态**：已决策

**决策**：P0 视频渲染不追求复杂剪辑，先用图片轮播 + 字幕 + BGM 的形式。

**原因**：
- 快速验证内容生成质量
- 降低渲染复杂度
- 后续可替换为更复杂的视频引擎

---

## ADR-009：声音克隆 P1 再做

**状态**：已决策

**决策**：P0 使用通用 TTS，P1 再接入声音克隆。

**原因**：
- P0 先验证脚本和内容质量
- 声音克隆涉及授权、效果评估等额外问题
- 通用 TTS 已能满足 demo 需求

---

## ADR-010：数据库使用 PostgreSQL

**状态**：已决策

**决策**：P0 使用 PostgreSQL 作为数据库。

**原因**：
- 未来目标是 SaaS，PostgreSQL 是生产级选择
- 比 SQLite 更适合多用户、并发、数据完整性
- 团队熟悉，生态成熟
- Docker Compose 本地启动简单

**替代方案**：
- SQLite：部署更简单，但扩展性差

---

## ADR-011：文件存储使用本地文件系统

**状态**：已决策

**决策**：P0 上传文件存储在本地文件系统。

**原因**：
- P0 是内部验证，本地存储零成本
- 文件路径抽象一层后，P1 可无缝迁移到对象存储
- 部署简单，无需配置云存储

**未来**：P1 评估 MinIO / 阿里云 OSS / AWS S3。

---

## ADR-012：P0 是内部验证工具，未来目标 SaaS

**状态**：已决策

**背景**：需要明确 P0 的定位，以指导技术选型和功能范围。

**决策**：P0 先作为内部工具跑通核心 workflow，但技术选型为未来 SaaS 化做准备。

**影响**：
- 前端选 TanStack Start 而不是 Streamlit
- 数据库选 PostgreSQL 而不是 SQLite
- 代码结构考虑多用户、权限扩展
- P0 不实现计费、多租户，但预留扩展空间

---

## 待决策事项

| 事项 | 建议 | 决策者 |
|:---|:---|:---|
| 产品名称 | 待定 | 左总 |
| 任务队列 | 纯 asyncio（P0 足够） | 技术 |
| 语音识别 | P0 不做，P1 评估 FunASR / 讯飞听见 | 技术 |
| 视频渲染引擎 | MoviePy + FFmpeg | 技术 |
| 语音合成服务 | P0 不做，P1 评估 MiniMax TTS / 科大讯飞 | 技术 |
| 配乐资源 | Uppbeat / Artlist | 产品/技术 |
| 是否支持 URL 输入 | 本期不做 | 产品 |
| 首期支持语言 | 中英双语 | 产品 |
| 付费模式 | 本期不设计 | 左总 |
