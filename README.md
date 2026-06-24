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

本项目后端用 [`uv`](https://github.com/astral-sh/uv) 管理 Python 依赖，前端用 [`pnpm`](https://pnpm.io/) 管理 Node 依赖。

**为什么用这俩：**
- **uv**：Rust 写的 Python 包管理器，比 `pip`/`venv` 快 10–100 倍，自动管理虚拟环境和 Python 版本，`uv sync` 按 lockfile 精确复现依赖。
- **pnpm**：用硬链接共享全局缓存，安装更快、占用磁盘更小，依赖隔离更严格，避免 npm 的「幽灵依赖」问题。

**如果还没装：**

```bash
# 安装 uv（macOS / Linux）
curl -LsSf https://astral.sh/uv/install.sh | sh
# macOS 也可用 Homebrew： brew install uv
# Windows（PowerShell）： powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装 pnpm（需要 Node.js 18+）
npm install -g pnpm
# 或独立安装脚本： curl -fsSL https://get.pnpm.io/install.sh | sh -
# macOS 也可用 Homebrew： brew install pnpm
```

> 装完后重开终端（或 `source` 一下 shell 配置）让 `uv` / `pnpm` 进入 PATH，可用 `uv --version`、`pnpm --version` 验证。

**安装项目依赖：**

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

### 3. 用 Docker 启动数据库

项目使用 PostgreSQL，推荐用 Docker 跑数据库，省去本地安装。

```bash
# 只启动数据库容器（postgres:16-alpine，端口 5432，库名 repurposer）
docker compose up -d db

# 常用操作
docker compose ps          # 查看状态
docker compose logs -f db  # 看日志
docker compose stop db     # 停止
```

- 默认连接串（已写入 `.env.example`）：
  `postgresql+asyncpg://postgres:postgres@localhost:5432/repurposer`
- 数据持久化在 Docker 卷 `postgres_data`，`docker compose stop` 不会丢数据。
- 提示：`./scripts/dev.sh` 会在 5432 端口空闲时自动用 Docker 拉起一个 `repurposer-db` 容器；
  如果你已经用上面的 `docker compose up -d db` 起好了，脚本会自动跳过，不会重复启动。

> Docker 不可用时，脚本会打印警告并跳过，此时请自行保证 5432 端口有可连接的 PostgreSQL。

### 4. 一键启动应用，然后访问 3000

```bash
# 方式一：shell 脚本（推荐）
./scripts/dev.sh

# 方式二：Justfile
just dev
```

脚本会同时拉起 **后端（:8000）** 和 **前端（:3000）**，并在需要时自动启动数据库。
启动完成后，浏览器打开 👉 **http://localhost:3000**

| 服务 | 地址 |
|------|------|
| 前端（Web App） | http://localhost:3000 |
| 后端（API） | http://localhost:8000 |
| API 文档（Swagger） | http://localhost:8000/docs |

### 5.（可选）全栈 Docker 一键运行

无需本地装 Node / Python，直接用 Docker 跑 db + api + web：

```bash
docker compose up --build
# 完成后同样访问 http://localhost:3000
```

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
