# Production Debugging

> Status: 活跃操作手册（2026-10-21）

线上排障先做**只读取证**，再做状态变更。日志、容器状态、镜像元数据、数据库 `SELECT` 都属于取证；重启、重建、删数据、手工改库必须另有明确授权。

## 1. 分层定位

生产链路按四层看，不要只盯浏览器报错：

| 层 | 看什么 | 典型问题 |
|---|---|---|
| 浏览器 trace | `turn.start` / `stream.open` / `stream.frame` / `turn.error` / `turn.finally` | SSE 是否打开、终端帧是 `completed` 还是 `failed` |
| API | `http_request` / `http_error` / `tool_loop_*` / `agent_call_*` / chat failure events | 请求是否到达、工具 loop 是否结束、错误如何被映射给用户 |
| worker | `asset_processed` / `web_capture_*` / `film_*` / queue processor events | 素材处理、网页截图、重活是否执行 |
| render | render request / failure | clip-spec 到 MP4 的渲染是否失败 |

浏览器里的 `stream.error message="stream closed"` 不能单独判故障：正常完成后连接关闭也可能出现它。先看最后的业务帧是 `completed`、`checkpoint` 还是 `failed`，再对服务端日志。

## 2. 时间线和 ID

- 统一用 UTC 对齐浏览器 trace 和 Docker `--timestamps`。
- 先取项目 ID、资产 ID、run ID，再按 ID 回查日志和数据库。
- 用户说“卡住了”时先看 `agent_call_started` 是否已有对应 `agent_call_completed`；长 LLM 调用不等于死锁。

## 3. 常用只读命令

SSH 使用当前机器配置的线上别名；本地别名是 `volc-ide`。

```bash
ssh volc-ide "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"
ssh volc-ide "docker inspect repurposer-api --format 'created={{.Created}} id={{.Id}}'"
ssh volc-ide "docker logs --timestamps --since '2026-10-21T09:00:00Z' repurposer-api-1 2>&1 | grep '<project-id>'"
ssh volc-ide "docker logs --timestamps --since '2026-10-21T09:00:00Z' repurposer-worker-1 2>&1 | grep -Ei 'web_capture|film_|failed|error|exception'"
```

API 请求日志会带 request/response body。复制给外部或贴进报告前，只保留时间、方法、路径、状态和必要 ID，避免泄露用户内容或凭据。

## 4. 容器环境检查

容器内检查环境变量优先用 `docker inspect`，不要依赖 SSH 拼接出来的 shell 展开：

```bash
ssh volc-ide "docker inspect repurposer-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^CHROME_'"
```

`docker exec` 里用非登录 shell，避免登录 shell 重置 `PATH` 造成“依赖不存在”的假证据：

```bash
ssh volc-ide "docker exec repurposer-worker-1 sh -c 'command -v chromium; python -c \"import playwright; print(playwright.__file__)\"'"
```

通过 SSH 传命令时，远端变量要写成 `\$VAR` 或放进单引号脚本；否则本地 shell 会先把 `${VAR}` 展开成空字符串。

## 5. 网页截图 / Film 排障签名

| 日志签名 | 结论 | 下一步 |
|---|---|---|
| `web_capture_chrome_missing` | worker 找不到浏览器 | 查镜像是否有 Chromium、`CHROME_PATH`、`CHROME_NO_SANDBOX` |
| `web_capture_processed ... screenshot=False warnings=['chrome_missing']` | 文本采集成功、视觉采集缺失 | 修容器浏览器运行态，再重发链接触发重抓 |
| `film_direction_preflight_failed need=4 views=0` | Film 前置校验没有可用页面视图 | 回查该项目的 `web_capture_processed` 和资产 `meta.shots` |
| `web_capture_visuals shots=N` | 浏览器采集成功 | `N >= 4` 才满足当前 Film 视图门槛 |
| `agent_call_started` 后暂无 `agent_call_completed` | 模型仍在调用中 | 看耗时和预算，不先判死锁 |
| `film_plan_draft_failed reason=...` | 分镜草稿失败的结构化原因 | 按 `reason` 中的 code 归因，不只引用用户可见文案 |

容器内验证 Chromium 启动：

```bash
ssh volc-ide "docker exec repurposer-worker-1 timeout 15s chromium --headless --no-sandbox --disable-gpu --dump-dom about:blank >/tmp/dom.out 2>/tmp/dom.err; code=\$?; printf 'exit=%s bytes=' \"\$code\"; wc -c </tmp/dom.out"
```

DBus 报错在容器里常见；`exit=0` 且有 DOM 输出即说明 headless 启动成功。

只读调用真实采集函数（不写数据库、不写对象存储）：

```bash
ssh volc-ide "docker exec repurposer-worker-1 python -c 'import asyncio; from app.tools.research.capture import capture_page; o=asyncio.run(capture_page(\"https://example.com\")); print(\"shots=%d screenshot=%s warnings=%s\" % (len(o.shots), bool(o.screenshot), o.warnings))'"
```

## 6. 数据库只读检查

数据库只跑 `SELECT`。`assets.meta` 是 JSON 列，按键查询要显式转 `jsonb`；资产枚举值是大写。

```sql
SELECT id, type, processing_status, processing_error, created_at, processed_at
FROM assets
WHERE project_id = '<project-id>'
ORDER BY created_at;

SELECT id,
       (meta::jsonb) ? 'shots' AS has_shots,
       (meta::jsonb) ? 'screenshot_key' AS has_screenshot
FROM assets
WHERE project_id = '<project-id>';
```

执行方式：

```bash
ssh volc-ide "docker exec repurposer-db-1 psql -U postgres -d repurposer -c '<sql>'"
```

## 7. 部署后验收顺序

1. `docker ps` 确认 api / worker / render / web 都启动。
2. `docker inspect` 核对镜像创建时间和容器启动时间。
3. 查关键环境变量（用 `docker inspect`，不要靠 SSH 展开）。
4. 查容器内代码是否包含目标修复（例如 `grep` 目标分支）。
5. 做一次最小运行时探针（例如 Chromium `about:blank`）。
6. 再做一次不写库的链路探针（例如 `capture_page`）。
7. 最后让用户走真实产品链路；同时看 API 与 worker 日志确认入库和终态。
