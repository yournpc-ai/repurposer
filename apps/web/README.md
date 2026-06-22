# Repurposer Web

TanStack Start 前端。

## 开发

```bash
pnpm install
pnpm dev
```

访问 http://localhost:3000

后端 API 默认在 http://localhost:8000，可在 `.env` 中配置 `VITE_API_URL`。

## 页面

- `/`：Dashboard
- `/speakers`：Speaker 管理
- `/projects`：Project 管理

## 技术栈

- TanStack Start
- TanStack Router
- React 19
- Vite
- TypeScript
- Tailwind CSS

## API 类型生成

后端启动后，从 OpenAPI 生成 TypeScript 类型：

```bash
pnpm generate-api
```
