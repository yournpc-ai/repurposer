# Repurposer

把一场演讲的原始素材（视频、音频、文字稿、幻灯片、照片）自动转化为适合多平台传播的短视频、社媒文案、金句卡和多语言版本。

## 技术栈

- **后端**：FastAPI + Python
- **核心模型**：MiniMax M3
- **前端**：TanStack Start + TypeScript
- **包管理**：后端 `uv`，前端 `pnpm`
- **数据库**：PostgreSQL
- **文件存储**：本地文件系统（P0）
- **本地协调**：`Justfile` / `scripts/dev.sh`
- **部署**：Docker Compose

## 目录结构

```
repurposer/
├── apps/
│   ├── api/                 # FastAPI 后端
│   └── web/                 # TanStack Start 前端
├── docs/                    # 项目文档
│   ├── PRD.md              # 产品需求文档
│   ├── ARCHITECTURE.md     # 架构设计
│   ├── API.md              # API 规范
│   └── DECISIONS.md        # 架构决策记录
├── scripts/
│   └── dev.sh              # 本地一键启动
├── docker-compose.yml
├── Justfile
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
# 后端
cd apps/api
uv sync

# 前端
cd apps/web
pnpm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY 等
```

### 3. 启动开发环境

```bash
# 方式一：Justfile
just dev

# 方式二：shell 脚本
./scripts/dev.sh
```

访问：
- 前端：http://localhost:3000
- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 文档

- [产品需求文档](./docs/PRD.md)
- [架构设计](./docs/ARCHITECTURE.md)
- [API 规范](./docs/API.md)
- [架构决策记录](./docs/DECISIONS.md)
- [开发排期与路线图](./docs/SCHEDULE.md)

## 开发规范

- 后端代码放在 `apps/api/`
- 前端代码放在 `apps/web/`（TanStack Start）
- 文档放在 `docs/`
- 不引入 Turborepo/Nx 等 monorepo 工具，保持简单
- 前后端通过 REST API 通信，类型由后端 OpenAPI 生成
