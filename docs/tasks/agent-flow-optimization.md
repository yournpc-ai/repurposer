# Task：从 Composer 到 Results 的 Agent 流程优化

> 对应 plan：`/Users/sylas/.claude/plans/sharded-plotting-ocean.md`
> 状态：**已完成**

## 背景

当前生成管线存在以下问题：
- `materials` 命名与 `Asset` 混用，agent/prompt 中容易歧义。
- Composer 硬编码 clips always included，未利用意图识别推断 clip_count 和 outputs。
- Derivative agent 串行执行，生成慢且进度不透明。
- `ContentPlan` 未持久化，无法复用。
- Result 页只有 "Generating…"，没有分阶段 loading。
- 一个 agent 失败导致整个 run failed。
- `carousel` / `blog` 已生成但前端未暴露。

本 task 一次性重构解决。

## 验收标准

1. 后端不再有 `materials` / `media_inputs` 的模糊命名；统一为 `asset_texts` / `asset_media`。
2. Composer 尊重推断的 `outputs` 和 `clip_count`；clips 可被用户排除；carousel/blog 可选。
3. Derivative agent 并发执行，每个 output 有独立进度/失败状态。
4. `ContentPlan` 持久化到 `Project.content_plan`；重新生成时复用。
5. Result 页在 `loading` 阶段显示 Stepper，之后用 Skeleton 渐进填充。
6. 失败 output 自动重试一次，仍失败显示手动 retry 按钮，retry 只重跑该 output。
7. carousel/blog 在 Composer 和 Result 页完整可用。

## 子任务拆分（已完成）

### Phase 1：后端命名统一 ✅
- 重命名 `collect_materials` → `collect_asset_texts`
- 重命名 `_trim_materials` → `_trim_texts`
- 重命名 `_collect_media_inputs` → `collect_asset_media`
- 更新所有 agent `generate(...)` 签名为 `asset_texts`
- 更新 `derivative_dispatch.py` 和 `generation.py` 调用点
- 更新所有 prompt 模板里的 `materials` 变量名和文案
- 更新 `app/routers/speakers.py` 的 persona 调用

### Phase 2：意图识别增强 + 数据模型 ✅
- `InferredIntent` 增加 `clip_count`，outputs 支持 carousel/blog
- Intent agent prompt 提取 clip_count，支持排除 clips
- `Project` 表增加 `content_plan` JSON 列 + Alembic 迁移 `eb812df93567`
- `ProjectResponse` 返回 `content_plan`

### Phase 3：并行生成 + ContentPlan 持久化 + 失败重试 ✅
- `run_generation` 改为：Content Director → 持久化 plan → 删除旧输出 → Clip Agent（如请求）→ `asyncio.gather` 并发 derivatives
- 每个 output 包 try/except + 一次自动重试
- `run.context["output_status"]` 记录 per-output 状态/错误
- 复用 `project.content_plan` 跳过 Director
- `WorkflowRun.current_step` 在 planning 阶段细分为 `analyze` / `plan` / `prepare`，供 Stepper 使用

### Phase 4：前端 Composer 改造 ✅
- `OUTPUT_OPTIONS` 加入 carousel/blog
- clips 不再强制 included
- 应用 inferred `clip_count`（默认 5）
- `lockedParams` 覆盖 outputs / language / speaker（clip_count 由意图识别决定，无手动编辑 UI）
- i18n 补充 carousel/blog 相关文案，并把 "Multi-language summary" 改为 "Summary"

### Phase 5：Result 页 Loading 升级 ✅
- 新增 `GenerationStepper` 组件（真实 3 步：analyze / plan / prepare）
- 新增 `ClipCardSkeleton`、`DerivativeCardSkeleton` 组件
- `projects.$id.tsx` 根据 `current_step` 切换 Stepper / Skeleton / 真实内容
- `ResultsTabs` 根据请求 outputs 动态渲染，显示进行中/失败 badge
- i18n 补充 stepper/retry 文案

### Phase 6：Carousel / Blog 卡片 ✅
- 新增 `CarouselCard` 组件
- 新增 `BlogCard` 组件
- `ResultsTabs` 类型扩展
- 后端确保 carousel/blog derivative dispatch 正常

### Phase 7：端到端验证 ✅
- 后端 `py_compile` + 模块导入通过
- 前端 `tsc --noEmit` + `npm run build` 通过
- `./scripts/dev.sh` 增加 API ready 等待与异步 demo seed，避免前端 race

## 关键文件

后端：
- `apps/api/app/services/project_context.py`
- `apps/api/app/agents/base.py`
- `apps/api/app/services/generation.py`
- `apps/api/app/agents/{content_director.py, clip_agent.py, linkedin.py, quote_agent.py, carousel.py, summary.py, blog.py, persona.py}`
- `apps/api/app/services/derivative_dispatch.py`
- `apps/api/app/agents/intent.py`
- `apps/api/app/models/schemas.py`
- `apps/api/app/models/tables.py`
- `apps/api/app/routers/projects.py`
- `apps/api/app/routers/speakers.py`
- `apps/api/app/prompts/*.j2`
- `apps/api/migrations/versions/eb812df93567_add_project_content_plan.py`
- `apps/api/app/config.py`
- `apps/api/app/main.py`
- `scripts/dev.sh`

前端：
- `apps/web/src/components/home/HomeComposer.tsx`
- `apps/web/src/components/home/RecentProjects.tsx`
- `apps/web/src/routes/projects.$id.tsx`
- `apps/web/src/components/results/ResultsTabs.tsx`
- `apps/web/src/components/results/GenerationStepper.tsx`（新增）
- `apps/web/src/components/results/ClipCardSkeleton.tsx`（新增）
- `apps/web/src/components/results/DerivativeCardSkeleton.tsx`（新增）
- `apps/web/src/components/results/CarouselCard.tsx`（新增）
- `apps/web/src/components/results/BlogCard.tsx`（新增）
- `apps/web/src/lib/i18n/locales/en.ts`
- `apps/web/src/lib/i18n/locales/zh.ts`
- `apps/web/src/lib/types.ts`

## 依赖关系

```
Phase 1 命名统一
    ↓
Phase 2 意图识别 + 数据模型
    ↓
Phase 3 并行生成 + 失败重试
    ↓
Phase 4 Composer 改造
    ↓
Phase 5 Result 页 loading
    ↓
Phase 6 Carousel/Blog 卡片
    ↓
Phase 7 验证
```

## 注意事项

- 命名重构是机械替换，prompt 模板中 `for material in materials` 已同步改完。
- 并行生成时，"删除旧输出"在所有新写入之前完成。
- `ContentPlan` 复用逻辑 V1 简单判断存在即复用，后续再加 materials hash 失效。
- 失败重试在 orchestration 层只做一次，底层 MiniMax client 已有 3 次网络重试。
- 新增 UI 组件优先使用现有 shadcn/ui primitive，未引入新依赖。
- `Summary` 不再称为 "Multi-language summary"；多语言是 `target_language` 驱动的全局属性，不是单独 output。
