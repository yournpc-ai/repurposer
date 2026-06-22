# Repurposer 架构设计

## 1. 设计原则

1. **简单优先**：P0 不引入复杂框架，用纯 Python + FastAPI 手搓 Agent 工作流
2. **模块解耦**：媒体处理、智能生成、渲染层可独立替换
3. **人工反馈闭环**：每个生成步骤都支持用户反馈和局部重生成
4. **单模型策略**：核心智能层只用 MiniMax M3

## 2. 抽象架构

```
┌─────────────────────────────────────────────┐
│  前端：TanStack Start                        │
│  上传素材 / 配置 Speaker / 审校结果 / 导出   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  后端：FastAPI                               │
│  REST API / 文件上传 / 任务调度 / 状态管理   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent 工作流编排器                          │
│  定义步骤顺序、状态流转、人工暂停点          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Agent Steps（纯 Python 函数）               │
│  persona / analyze / script / review /       │
│  revise / linkedin / quote_card / translate  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  MiniMax M3 Client                           │
│  统一封装调用、JSON 解析、重试、错误处理     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  媒体处理层                                  │
│  语音识别 / 视频抽帧 / 文档解析 / 图片处理   │
│  声音克隆 / 语音合成 / 视频渲染 / 图形生成   │
│  配乐资源                                    │
└─────────────────────────────────────────────┘
```

## 3. Agent 工作流

### 3.1 核心 Agent

| Agent | 输入 | 输出 | 说明 |
|:---|:---|:---|:---|
| `persona` | 演讲者过往材料 | `SpeakerPersona` | 风格画像 |
| `analyzer` | 演讲稿 + persona | `ContentSegments` | 内容切片与评分 |
| `script` | 片段 + persona + tone | `ClipScript` | 竖屏脚本 |
| `review` | 脚本 + persona | `StyleReview` | 风格评分 |
| `reviser` | 脚本 + 反馈 + persona | `ClipScript` | 修正后的脚本 |
| `hook` | 脚本 + 反馈 | `str` | 重新生成 hook |
| `linkedin` | clip + persona | `LinkedInPost` | LinkedIn 长帖 |
| `quote_card` | clips + persona | `QuoteCards` | 金句卡文案 |
| `translator` | 脚本 + 目标语言 | `ClipScript` | 多语言版本 |

### 3.2 生成流程

```
用户上传素材
    ↓
预处理（转写 / 解析 / 图片处理）
    ↓
Persona Agent → Speaker 风格画像
    ↓
Analyzer Agent → 内容切片 + 传播潜力评分
    ↓
对每个高潜片段：
    Script Agent → 初稿
    Review Agent → 评分
    如果未通过：
        Reviser Agent → 修正
    重复最多 2 次
    ↓
LinkedIn Agent / Quote Card Agent → 衍生内容
    ↓
保存结果，等待用户审校
    ↓
用户反馈 → Reviser Agent → 局部重生成
```

### 3.3 人工反馈循环

用户反馈必须结构化：

```python
class FeedbackRequest(BaseModel):
    clip_id: str
    scope: Literal["hook", "full_script", "tone", "translation"]
    reason: Literal[
        "hook_not_catchy",
        "not_like_speaker",
        "too_complex",
        "too_simple",
        "factually_inaccurate",
        "different_expression",
        "other"
    ]
    detail: Optional[str] = None
```

## 4. 数据流

```
用户上传
    ↓
FastAPI 接收文件 → 本地文件系统
    ↓
写入 PostgreSQL，创建 workflow_run
    ↓
asyncio 后台任务异步处理：
    - 图片 → 压缩 + 描述
    - 幻灯片/PDF → 文档解析（P0 可选）
    ↓
Agent 编排器按步骤执行
    ↓
每步结果写入 workflow_steps 表
    ↓
workflow_run 状态更新为 review
    ↓
TanStack Start 前端：用户审校 / 反馈
    ↓
Reviser Agent 局部重生成
    ↓
用户导出
```

## 5. 代码结构

```
apps/api/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── dependencies.py      # 依赖注入
│   ├── routers/             # API 路由
│   │   ├── speakers.py
│   │   ├── projects.py
│   │   ├── assets.py
│   │   ├── generate.py
│   │   ├── clips.py
│   │   └── derivatives.py
│   ├── services/            # 业务逻辑
│   │   ├── workflow.py
│   │   ├── storage.py
│   │   └── preprocessing.py
│   ├── models/              # 数据库模型 + Pydantic schemas
│   │   ├── database.py
│   │   ├── schemas.py
│   │   └── tables.py
│   ├── agents/              # Agent steps
│   │   ├── __init__.py
│   │   ├── persona.py
│   │   ├── analyzer.py
│   │   ├── script.py
│   │   ├── reviewer.py
│   │   ├── reviser.py
│   │   ├── linkedin.py
│   │   ├── quote_card.py
│   │   └── translator.py
│   ├── prompts/             # Jinja2 模板
│   │   ├── persona.j2
│   │   ├── script.j2
│   │   ├── review.j2
│   │   ├── revise.j2
│   │   ├── linkedin.j2
│   │   └── quote_card.j2
│   └── clients/
│       └── minimax.py       # MiniMax M3 封装
├── pyproject.toml
└── README.md
```

## 6. 状态管理

### 6.1 Workflow Run

记录一次生成任务的完整生命周期：

```python
class WorkflowRun(BaseModel):
    id: UUID
    project_id: UUID
    status: Literal[
        "pending", "running", "waiting_human",
        "completed", "failed"
    ]
    current_step: str
    context: dict
    created_at: datetime
    updated_at: datetime
```

### 6.2 Workflow Step

记录每个 Agent step 的执行情况：

```python
class WorkflowStep(BaseModel):
    id: UUID
    run_id: UUID
    step_name: str
    input_json: dict
    output_json: dict
    attempts: int
    error: Optional[str]
    created_at: datetime
```

## 7. 关键设计决策

- **不用 Turborepo/Nx/Pants**：前后端独立管理，简单目录结构即可
- **手搓 Agent**：单模型、固定 workflow，框架抽象价值不大
- **Pydantic 强类型**：所有 Agent 输入输出都用 Pydantic model
- **结构化反馈**：用户反馈必须选择原因，不能只有自由文本
- **版本历史**：每次重生成保存旧版本，支持对比和回滚

## 8. 扩展点

| 未来需求 | 扩展方式 |
|:---|:---|
| 接入第二个模型 | 新增 `clients/openai.py`，在 `minimax.py` 同级抽象 LLMClient 接口 |
| 多语言扩展 | 新增 `translator.py` 支持更多目标语言 |
| 复杂 workflow | P2 评估 LangGraph 或 Pydantic AI |
| 团队协作 | 新增 `organizations` / `members` 表和权限中间件 |
| 社媒直接发布 | 新增 `routers/publish.py` 调用平台 API |
