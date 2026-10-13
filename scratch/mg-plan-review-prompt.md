# 评审请求：AI 内容 agent 的「MG 短片 skill」4 天冲刺计划

你是资深产品架构评审，熟悉 agent 产品架构（Claude Code skills / LangGraph / Remotion / 视频渲染管线）。请**对抗性审查**以下计划——不接受奉承；每个反对意见必须给出具体失败场景（什么输入/状态 → 什么错误结果）。若建议推翻我的既有约束，必须论证约束本身错了，而不是绕过它。

## 0. 产品一句话

Repurposer = 面向知识专家的 AI 内容 agent：用户给素材/链接 + 点名要什么，agent 出方案（画布上的计划图）→ 开工 → 交付产物。已有能力：视频剪辑/字幕/配音/金句卡/轮播/长文（全部基于用户真实素材，由自研 clip-spec 契约驱动渲染）。

## 1. 新能力（本批目标）

同事用 Claude Code skill 包（SKILL.md + prompts + scripts）做出了「给一个 URL → 生成 26 秒产品发布短片」：capture（真实截图+文案抽取）→ LLM 写 storyboard JSON → 确定性渲染（逐帧截图 + ffmpeg）。零素材、纯程序化 MG（大字句/界面推镜/章节卡/片尾卡）。

我已用**自己的技术栈**复刻 spike 验证（同事的代码一行没拷贝）：Remotion 组件库（6 个场景组件：words/hero/ui/divider/reveal/end）+ 手写 storyboard → 780 帧/26s/1080p 渲染 45.5s（≈1.75×实时，本机 Mac）。屏上文案全部取自对目标页的真实抽取。

## 2. 不可动约束（默认接受；认为错了就论证约束本身）

1. **LLM 只写 spec JSON，永不写渲染代码**；渲染组件库人工拥有（宪法级，防 prompt injection 进渲染器 + 可维护性）。
2. **单编排链**：新能力骑既有 run/图/worker/计价，禁第二条编排链。
3. **node face 不变**：图节点类型枚举（text/table/image/video/audio）+ prototype（generator/editor/manual）不动；新能力 = 节点内部 spec 新家族（film-spec 与既有 clip-spec 平级）。
4. **注册表 → prompt 单源投影**：能力菜单/计划目录/意图路由全从 tool 注册表投影生成，禁手写进 prompt（防漂移）。
5. **卡点亮律**：配方卡上架必须有真实渲染的 demo 片；一卡只承诺一个产物。
6. **计费**：hold→capture→release；逐次尝试计价，失败不扣费。
7. **重活全走 Postgres 队列 + worker**，禁请求内执行。
8. 诚实降级 / 工具名不上屏 / 无真实数据支撑的 UI 件不做。

## 3. 4 天计划（10-14 ~ 10-19）

**D1（纯移植日，零未知）**
- render 服务：`apps/render/src/film/` 组件库从 spike 转正 + storyboard zod schema（边界只校验形状）；`server.ts` 加 `spec.family==='film'` 路由（clip 路径零改动）。
- 网页采集资产化：`app/tools/research/capture.py`（结构化文案抽取 + headless Chrome 截图；复用同包 `web.py` 既有 SSRF 守卫/代理纪律；多页 discover = 根页抽站内前 5 链接）+ `app/pipeline/web_capture.py` processor（挂既有 PROCESSORS 链）+ `create_web_page_asset_from_url()`（chat 贴 URL → 资产的提升函数，有现成先例 transcript）+ `AssetType.web_page`。

**D2（唯一真未知日）**
- `app/tools/film/` 编排 tool：LLM 写 storyboard → grounding validator（屏上字符串逐条命中采集文案清单；相机焦点越界拒；场景枚举闭合；失败打回重写）→ spec 落节点 → 既有 render pipeline 入队。
- prompt 面：`app/skills/launch-film/SKILL.md`（craft 约定，行业标准 SKILL.md 形态）+ `film_storyboard.j2`（输出 schema）——一部法一个座位，禁双写；注册表加 capability menu 行（"你会做什么"自动说出新能力）；intent router 加一句 URL 指引（LLM 判定，禁正则/长度启发式）。
- 出生地分叉：create_run 的"必须有素材"422 按 spec.family 豁免 film 族（改验 web_page 资产在场）。
- 缓解：上午先用 fixture storyboard 打通 validator→render 全链，LLM 编排下午并行调。

**D3（集成日）**
- 简式计价：storyboard 秒数 × 费率 + 编排 tokens 平项。
- 配方卡注册 + i18n + demo 真片（用本批管线实渲一条）。
- e2e 打通 + prompt 探针回归。

**D4（回归 + 验收日）**
- 剧本测试加一座（URL→卡→方案→渲染→产物节点，只锁形态不锁文案）+ 纯函数测试（validator/抽取/registry↔prompt 一致性）。
- UI 一日包：项目页三档切换（Chat/Agent/Canvas）+ 活动行 hover/copy/图标 + AI 免责声明行。

**D5（半天顺手项）**：home 两级 tab 货架（原型已数据驱动，直接转正）。

## 4. 关键设计抉择（已拍板，请评审其合理性）

a. **引擎/skill/卡三层**：引擎 = 渲染基座（少）；skill = 族内变体（词汇表 + spec 预设 + prompt 段落 + validator）；卡 = 入口实例（brief 模板 + demo），1:N。同事未来的新 skill 走"四器官拆解（词汇表/spec 契约/编排 prompt/执行器）→ 三问分诊（引擎族已存在？魔法在 prompt 还是引擎？词汇重合度？）"装配线：同族新卡 0.5~1d，新引擎族 4~5d。
b. **URL = 资产**（消息入口提升），不是 agent 的工具调用——意图层即资产化，编排时资产已在场。
c. **v1 只做 16:9**（主渠道 LinkedIn/机构站），竖屏后补。
d. **修订 = 图变更**：改某场景 = 改 storyboard prop → 重渲整片（46s），不做场景级缓存。
e. **grounding validator = 差异化护城河**：屏上文案必须命中采集原文，防 LLM 编造。

## 5. 请按此结构输出

1. **过度设计残留**：哪件还可砍/延期而不伤首日体验？
2. **重复造轮子**：哪里业界或本系统已有更省的解？
3. **技术风险遗漏**：我标了"LLM 编排一次通过率"是唯一真未知——你同意吗？请评估：validator 打回死循环、Chrome 在 worker 的稳定性、渲染并发、SSRF 边界、storyboard 时长漂移。
4. **spec 家族设计**：film-spec 与 clip-spec 平级双家族 vs 统一 spec 超集——哪个对？有没有第三条路？
5. **工期真实性**：4 天哪里会炸？给出你估的逐日天数分布。
6. **装配线规程**：四器官拆解有没有漏器官？
7. **2027 用户习惯对齐度**：计划里有没有"架构自嗨但用户无感"的部分？

## 6. 评审纪律

- 先找错，不接受"计划很全面"式总评。
- 每条意见 = 具体失败场景 → 修法 → 代价。
- 对我们系统不确定的地方标注 [不确定]，不要编造细节。
