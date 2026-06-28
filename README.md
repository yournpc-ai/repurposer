# Repurposer

把一场演讲的原始素材（视频、音频、文字稿、幻灯片、照片）自动转化为适合多平台传播的短视频、社媒文案、金句卡和多语言版本。

## 技术栈

- **后端**：FastAPI + Python（含队列 worker）
- **核心模型**：MiniMax M3
- **前端**：TanStack Start + TypeScript
- **视频渲染**：Remotion（`apps/render`，Node 服务，clip-spec → MP4+SRT）
- **语音识别**：faster-whisper（自托管，词级时间戳）
- **任务队列**：Postgres（`FOR UPDATE SKIP LOCKED`）+ 独立 worker，不上 Redis
- **包管理**：后端 `uv`；前端/渲染/共享组件用 `pnpm` workspace（`web`/`render`/`clip`）
- **数据库**：PostgreSQL
- **文件存储**：本地文件系统（对象存储留到规模化）
- **本地协调**：`scripts/dev.sh`
- **部署**：Docker Compose

## 目录结构

```
repurposer/
├── apps/
│   ├── api/                 # FastAPI 后端（队列 worker / ASR）
│   │   └── migrations/      # Alembic 数据库迁移
│   ├── web/                 # TanStack Start 前端（含竖屏编辑器）
│   └── render/              # Remotion 渲染服务（clip-spec → MP4+SRT, Node）
├── packages/
│   └── clip/                # 共享 Remotion <Clip> 组件（web 预览 + render 出片，保 parity）
├── docs/                    # 项目文档
│   ├── PRD.md              # 产品需求文档
│   ├── ARCHITECTURE.md     # 架构设计
│   ├── VIDEO_EDITOR.md     # 竖屏短片编辑器设计
│   ├── DECISIONS.md        # 架构决策记录
│   └── DATABASE_MIGRATIONS.md  # 数据库迁移指南
├── scripts/
│   └── dev.sh              # 本地一键启动
├── pnpm-workspace.yaml     # web/render/clip 工作区（api 独立用 uv，不在工作区内）
├── docker-compose.yml
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

# 前端 + 渲染服务 + 共享组件（pnpm workspace，在仓库根目录执行一次即可）
pnpm install
```

> `pnpm install` 在根目录执行会一次装好 `apps/web`、`apps/render`、`packages/clip` 三个 workspace 包。
> 首次启动渲染服务时 Remotion 会下载一个无头 Chromium（约几百 MB），属正常。

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY 等
```

### 3. 用 Docker 启动数据库

项目使用 PostgreSQL，推荐用 Docker 跑数据库，省去本地安装。

```bash
# 只启动数据库容器（postgres:18-alpine，端口 5432，库名 repurposer）
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

### 4. 运行数据库迁移

后端使用 [Alembic](https://alembic.sqlalchemy.org/) 管理数据库 schema 变更。首次启动前或拉取新代码后，需要应用迁移到最新版本：

```bash
cd apps/api
uv run alembic upgrade head
```

常用命令：

```bash
# 查看当前迁移版本
uv run alembic current

# 生成新的自动迁移（修改 models 后执行）
uv run alembic revision --autogenerate -m "describe your change"

# 回滚一级
uv run alembic downgrade -1
```

> **注意**：`./scripts/dev.sh` 会在启动 API 前自动运行 `uv run alembic upgrade head`，所以日常本地开发不手动跑迁移也可以。但首次部署或 CI 中建议显式执行。

### 5. 一键启动应用，然后访问 3000

```bash
./scripts/dev.sh
```

脚本会同时拉起 **后端（:8000）**、**队列 worker**、**渲染服务（:3001）** 和 **前端（:3000）**，并在需要时自动启动数据库。
启动完成后，浏览器打开 👉 **http://localhost:3000**

| 服务 | 地址 |
|------|------|
| 前端（Web App） | http://localhost:3000 |
| 后端（API） | http://localhost:8000 |
| API 文档（Swagger） | http://localhost:8000/docs |
| 渲染服务（Remotion） | http://localhost:3001 |

> 渲染服务（`apps/render`）是 api worker 调用的黑盒（clip-spec → MP4+SRT）；纯文本产出流程不需要它。

### 5.（可选）全栈 Docker 一键运行

无需本地装 Node / Python，直接用 Docker 跑全栈 **db + api + worker + render + web**：

```bash
MINIMAX_API_KEY=sk-xxx docker compose up --build
# 完成后访问 http://localhost:3000
```

服务编排说明：

| 服务 | 镜像/构建 | 说明 |
|---|---|---|
| `db` | postgres:18-alpine | 数据库，数据持久化在卷 `postgres_data` |
| `api` | `apps/api/Dockerfile`（uv） | FastAPI，:8000 |
| `worker` | 同 api 镜像，`command: python -m app.worker` | 队列消费者；调用 render 服务 |
| `render` | `apps/render/Dockerfile`（构建上下文=仓库根） | Remotion 渲染服务，:3001，内置 Chromium |
| `web` | `apps/web/Dockerfile`（构建上下文=仓库根） | TanStack Start SSR，:3000 |

注意：
- `render` / `web` 都依赖 workspace 包 `@repurposer/clip`，构建上下文是**仓库根**（不是各自子目录）。
- 容器内主机名互联：`API_PUBLIC_URL=http://api:8000`、`RENDER_URL=http://render:3001/render`（render 通过 HTTP 回拉源视频，渲染结果写共享卷 `./data/outputs`）。
- `render` 镜像内置无头 Chromium 的系统库；Chromium 二进制（约 90MB）在**首次渲染时**惰性下载（构建期不依赖外网，更适合 CI/受限网络）。
- `web` 当前用 `vite preview` 起 SSR，适合 MVP/staging；高流量部署可换成围绕导出的 fetch handler 的轻量 node 适配层（见 ADR-018）。

## 文档

- [产品需求文档](./docs/PRD.md)
- [架构设计](./docs/ARCHITECTURE.md)
- [API 规范](./docs/API.md)
- [架构决策记录](./docs/DECISIONS.md)
- [开发排期与路线图](./docs/SCHEDULE.md)

## 开发规范

- 后端代码放在 `apps/api/`
- 前端代码放在 `apps/web/`（TanStack Start）
- 视频渲染服务放在 `apps/render/`（Remotion，Node）；共享的 `<Clip>` 组件放在 `packages/clip/`
- 文档放在 `docs/`
- 用轻量 **pnpm workspace** 串起 `web`/`render`/`clip`（共享 Remotion 组件以保证「预览=成片」）；**不引入 Turborepo/Nx 等重型 monorepo 工具**。`apps/api` 独立用 `uv`，不在 workspace 内
- 前后端通过 REST API 通信，类型由后端 OpenAPI 生成
