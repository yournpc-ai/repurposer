# Iteration 5 验收记录 · 2026-11-21

**正式 MP4 的 Chat 交付及连续修订已实测，完整视听自主审片保留开放。** MiniMax 在真实预览后移动了尾卡，复看新版本，正式导出、审阅并交付。Chrome 播放后，用户通过同一对话延长尾卡半秒，收到另一份正式 MP4。模型没有可证实的主观听感。两次访谈构图任务均用尽 20 次决策，构图修订的稳定性未通过。

## 可播放的作品

| 原生决策所在回合 | 不可变 CompositionVersion | 正式 Output | 文件 |
|---|---|---|---|
| 首次交付 | e3323856-1e22-4407-9dba-f197846cea07 | 6f1eeb55-3a5b-4d93-928b-f595b5aa610d | [4.5 秒 MP4](delivery-v2.mp4) |
| 用户继续修订 | 0cf6c979-652c-409f-9c21-32915c95c05e | c7f108a1-74d9-4adc-b64d-7d638facdd14 | [5 秒 MP4](delivery-v3.mp4) |
| 独立项目再次交付 | bd8597b8-a7f7-454d-bbcb-ef452416a910 | c9ce06dd-bd8a-4136-a773-b88af0ccc980 | [4.5 秒 MP4](take2-delivery-v2.mp4) |
| 独立项目继续修订 | b776f3eb-3f83-4574-b817-70346988db81 | 368820b1-511b-47a7-8159-f4eb80d8ae92 | [5 秒 MP4](take2-delivery-v3.mp4) |

实际视频均为 320×180、30 fps、H.264。逐帧解码得到 135 或 150 帧，48 kHz AAC 解出 218112 或 242688 个样本。浏览器报告的容器时长分别为 4.544 和 5.056 秒。视频轨精确相差 15 帧。每张交付卡的哈希、版本、Output 和当次报告时间均可离线核对。[字节与解码清单](media.json) · [Chrome 播放、硬刷新及历史卡记录](browser.json.gz) · [修订后播放器](revision.png)

## 原始用户旅程

用户在 Studio 输入「这是两张卡组成的项目演示样片。两张卡的原文和展示时长都请保留，希望从头到尾衔接干净、没有多余的停顿。请实际看片，有明显问题就修改，检查最终成片后把正式 MP4 发给我。」

准备代码用现有写入口 `apply_composition_edits` 建立 v1。固定视频素材的源时间为 10–13 秒，编排在 0–3 秒。独立可编辑的文字卡为 “Thanks for watching”，原定 4.5–6 秒。项目另有访谈视频来源，首条成片只使用前一份视频及原生文字。准备代码未提交后续剪辑。浏览器只输入用户原话、点卡、播放、硬刷新和发送追问。工具名称、参数、顺序及是否修订均来自实际模型响应。

1. 首轮 `33976ca7-0b65-486f-9170-8170e72b3ff4` 先读时间线和两个片段，再播放 v1 的 0–6 秒。媒体中间采样点为 3.733 秒，编译及解码证据显示 3–4.5 秒没有可见 Clip。[修改前预览](preview-v1-4af58057.mp4)
2. 下一次模型响应调用 `move_clip({"clip_id":"elm_c","time":3})`，原生调用 ID 为 `call_function_5wbef796ogzj_1`。v2 只移动尾卡并收短所属 Scene 的尾界。原视频、源裁剪、文字、样式、展示时长、快照及其他作品设置逐项相同。模型复看 v2 的 0–4.5 秒，此时两张卡在 3 秒处相接。[修改后预览](preview-v2-3cb376b9.mp4) · [模型实际收到的上下文、媒体清单及响应](wire-studio.json.gz)
3. 模型调用无参数的 `export_video`，取得确定的 Output 后调用 `review_video`，再用 `deliver_video` 发出交付卡。首批审阅沿用旧的按 Scene 中点采样，只有一张静帧，未采到尾卡。该限制在当次报告中可见。后续已改为在 16 帧预算内对可见 Clip 边界分段取样，包括空档。第二个独立项目的正式审阅分别看到 1.5 秒的首卡和 3.733 秒的尾卡，修订后看到 1.5 秒和 4 秒。重测中模型先从时间线识别空档再动手，不能把这条重测计为第二次“先看片后修改”。[首卡样本](frame-30d77f628b3f.jpg) · [尾卡样本](frame-21dada38513b.jpg) · [第二次正式审阅 wire](wire-take2-studio.json.gz)
4. Chrome 实际播放，关闭播放器时 composer 带入确切 Output 引用。用户发送「结尾再留半秒。」回合 `ff4727ee-6493-46d2-a05e-3fb83f254c8f` 将同一 Composition 的静态尾卡从 3–4.5 延至 3–5 秒。v3 增加 45000 个作品 tick。模型曾在新预览之前尝试导出，又在正式审阅前尝试交付，两次都被拒绝。新审阅完成后写入另一张卡。三次禁用缓存的硬刷新及最后重开 v2 均播放对应文件。[修订 wire](wire-revision.json.gz) · [第二个浏览器会话](take2-browser.json.gz)

## 五个切片

| 切片 | Tool 与 Context | Chat 与执行 | 恢复证据 |
|---|---|---|---|
| 5A 观察 | `inspect_timeline`、`inspect_clip`、`preview_range` 返回版本、摘要、窗口、活跃片段、固定来源和实际送模媒体 | 真实视频、标时抽帧和混音技术量测进入 ToolLoop，活动及预览进入原 Thread | 只保留匹配版本的已看窗口，Stop 不写版本；首次空桶缺字体导致两次真实失败，已接入固定字体准备。[原始样本](observe.json.gz) |
| 5B 局部修订 | `move_clip` 等既有单步编辑由模型自行选用；修改后的版本使原预览失效 | 唯一写口同时保存操作身份和版本，Chat 按实际回执显式呈现修订 | 编辑前 Stop、编辑后 Stop、提交后回执前强杀、幂等及跨版本均有下节证据；失败样本保留。[早期修订](repair2.json.gz) |
| 5C 导出 | `export_video({})` 取本回合已看版本。调用同批预览不能充当已经作出的审阅决策 | 现有 `pin_video_production`、`create_run`、`ProduceVideo.run`、`queue_composition_render`、Renderer 和上传后 `_probe_artifacts` 产出正式文件；完成回执明确待审片 | 原调用返回原回执，项目锁与既有在途生产约束阻止并发另收费；另一回合可复用已完成文件，并重新校验对象。[复用重发](wire-reuse.json.gz) |
| 5D 正式审阅 | `review_video(output_id, requirements, …)` 读取确切字节与其版本。复用键覆盖字节哈希、请求、抽样范围与检查器版本 | 既有 reviewer 接受解码 JPEG，报告记录采样时间、尺寸、轨道、检查与局限；预览和正式文件即使哈希相同仍各有独立读取与回执 | 模型故障不能更新此前质量报告；审片进行中并发更新 head，结论仍归原 Output。[审阅竞态](review-race.json.gz) |
| 5E 交付及续改 | `deliver_video(output_id)` 校验本轮报告、选定版本与文件哈希。`extend_still(clip_id, seconds)` 只延长片尾无动画、未链接的静态对象 | 同一开场锁下落一条 `output_refs`；SSE 和历史共用既有播放器。尾卡与 Scene 在同一事务写入 | 同一回合重复交付只取既有卡。旧卡引用随用户消息进入 Chat；旧版与当前版不符时核对基线。[旧版定向问答](wire-stale-fixed.json.gz) |

[模型原生工具清单和完整 JSON Schema](schemas.json) 保存实际请求 ID。所有样本的逐次 wire 保留真实 provider、参数、工具 ID、送模消息、媒体类型及 token，用散列代替内联媒体字节。正式产物和关键预览另存为 MP4。[各回合 SSE](chat.json.gz) · [PostgreSQL 作品、来源、工具交换、消息、Run、Output、账本与模型用量](database.json.gz)

## Stop、并发、崩溃与费用

| 边界 | 结果 |
|---|---|
| Stop 先到 | 实际 POST Stop 返回 retracted，未写版本。一次性报价的原生调用并发重试、Stop 先于授权、在途竞争、报价上限及 head 并发变化另用真实 PostgreSQL 的定向测试运行。[Stop 记录](stop-first.json.gz) · [回归测试](../../../../apps/api/test/core/test_editor_media.py) |
| 编辑先提交 | 活动已完成时 Stop，恢复可见“延长片尾画面（版本 2）”。在另一项目于版本和操作标记已提交、活动仍 active 时向 API 发 SIGKILL。三次历史回读只恢复一个 v2 和一条已保存说明。[边界](ack-boundary.json.gz) · [三次回读](ack-restored.json.gz) · [Stop](save-first.json.gz) |
| Worker 与 API 双中断 | 首次上传并成功探测后 Worker 被强杀，此时 Output 仍为 rendering。启动回收执行了第二次 render step 尝试。两个上传键的字节相同，旧键留下一个未引用对象；一次 Run、一个 Output、一次 12 积分 capture。API 又在正式回执已写、卡未写时被强杀；历史续接实际审片，恢复同一 Output。没有单独采集编码器进程计数。[Worker 边界](worker-interruption.json.gz) · [启动回收](worker-restart.json) · [API 边界](export-interruption.json.gz) · [恢复的 Chat](recovered.json.gz) |
| 审片期间 head 变化 | 正式 reviewer 在工作时，通过独立数据库事务更新同一作品。旧报告仍绑定原版本、旧文件；重复相同审阅复用同一 reviewed_at。随后在 reviewer 边界注入不可用错误，先前报告保留。这个错误为受控故障注入。[回执](review-race.json.gz) |
| 许可、重发与历史卡 | 浏览器取消报价后该开场没有执行。早期“允许”完成渲染后，SSE 事务与续接事务相互等待；修复后重测，从同一报价续接原意并交付，6 秒成片扣 12 积分。先前中断的样本回读明确显示已导出待审。跨开场重发复用原 v3，同项目总数仍为 2 Run、2 Output、2 capture。历史卡编辑确认也未产生新版本或扣费。[批准后的 wire](wire-approved-fixed.json.gz) · [重发](wire-reuse.json.gz) |

## 样本表现与未通过项

下表请求数含正式审阅的模型请求。Schema 合法按各请求真正提供的 JSON Schema 核验；执行仍须通过版本、权限、已看片和已审片等独立条件。每个 Tool 的首次合法性、逐次参数、执行结果及每次请求的输入输出 token 见[完整指标](metrics.json)。没有对应持久回执的调用保留空状态，未计作执行成功。没有把中断/故障注入混进正常用户任务完成率。

| 用户任务 | 请求 | 合法原生调用 / 总数 | 输入 / 输出 token | 用户结果 |
|---|---:|---:|---:|---|
| 首次完整 Studio 交付 | 10 | 9/9 | 80,043 / 2,210 | 完成；真实预览触发修订 |
| 同一作品延长半秒 | 11 | 9/9 | 87,454 / 1,145 | 完成；两次前置条件失败后纠正 |
| 独立 Studio 重测及续改 | 10 + 10 | 9/9 + 8/8 | 77,766 / 1,321；76,163 / 1,033 | 两次交付；一次过早导出被拒 |
| 访谈构图，两次 | 20 + 20 | 20/20 + 20/20 | 172,788 / 12,828；156,751 / 5,334 | 均反复调 scale/translate，达到上限；最终版本未复看 |
| 更开放的演示片交付请求 | 20 | 22/22 | 218,952 / 8,817 | 有编辑，无正式交付 |
| 已交付 v3 另开回合重发 | 8 | 6/6 | 59,673 / 671 | 复用已完成文件，新增媒体扣费为零 |

三个要求交付已有演示片的独立主任务（journey、studio、take2-studio）完成 2/3，两次自然语言续改完成 2/2。以首轮修改前必须先看片为标准，两次成功主任务中只有首个样本满足。访谈构图收敛 0/2。早期 repair 试验受片尾 Scene 约束，repair2 虽消除了中间空档，却把空黑移到开头。上述成功率是这组小样本的观测值。[开放任务](wire-journey.json.gz) · [构图前](visual-final-1-3b336f4c.mp4) · [首次修订后](visual-final-2-c52e7a4e.mp4) · [构图重测](wire-visual-final.json.gz)

每个成功的双交付项目分别扣 9、10 积分。两次 render step 计量分别为 4.5、5.0 视频秒，账面 fixed_cost 为 0.009、0.010 美元。首次双轮 Chat 的模型成本账本分别为 0.013332、0.013805 美元。供应商最终发票未核对。首次 Studio 输入从 6,115 到峰值 10,745 token，续改从 6,160 到 10,947。失败的开放任务峰值为 22,354；模型请求上限保持原值。

空项目有独立验证。首次工作草稿缺少可渲染片段，进入审片后未完成。修复空时间线的工具可用性后，模型保存了可编辑 3 秒字卡，却超出“只要初稿”的请求继续生成素材和正式 Output。收紧首稿展示后再次建空项目，保存一版、正式 Output 为零；首稿中实际字体颜色和入场动画仍偏离“白字、保持静止”，模型如实报告。这项内容任务未通过。初稿规划曾调用配乐工具，最终项目没有对应的 capture。[第一次](wire-new.json.gz) · [过度生成样本](wire-new-fixed.json.gz) · [修复后](wire-new-scope.json.gz)

当前 MiniMax 的连续视频输入带音轨，模型能力声明为不能感知视频声音。正式 reviewer 接收到离散静帧。PCM、响度、峰值和 AAC 解码仅支持技术判断。主观混音、音画同步、逐帧运动质量、任意访谈的构图收敛、任意视频尾帧冻结均没有通过本轮验收。没有覆盖所有新建项目或真实用户的所有表述。

## 入口审计、Git 与复核

已有作品的创作回合使用相同 Editor Tools。移除了首稿工具集中引向普通视频 Plan/Start 的入口、旧“提议 produce_video”的提示、固定制作确认模型分支及方案校验中的视频特例。两个提案执行入口均拒收普通视频生产任务。已保存作品直接进入编辑、审片或导出。空项目的 design_video 与 review_working_draft 仍有首稿消费者。普通非视频任务、已展示的历史报价、人工确认和历史 Run 的消息/费用仍有消费者。AgentThread 复用既有 row_append、output_refs、播放器和历史 UI，本轮只增加一处实时交付消费，没有拆分它或引入平行系统。

基准为 `codex/studio-iteration-4@13670989`，其基准为 `main@32f04518`。施工分支为 `codex/agent-editor-iteration-5`。切片提交依次为 `7245263f`、`965b4677`、`1dfdb284`、`20ff3ec4`、`29f8a2ba`，首稿范围修正为 `d6926596`。最终证据提交可用 `git rev-parse HEAD` 核对。API、Worker、Renderer、Chrome、PostgreSQL 与 S3 兼容的本地隔离桶均为真实执行；媒体供应商初始素材生成另见对应 wire。主工作树原有四项修改保留，Iteration 4 工作树保持清洁。未向远端发布。

在仓库根目录用安装了 PyAV 的 API Python 运行 `python docs/tasks/agent-editor-evidence/iteration-5/verify.py`。脚本离线对照 MP4 全轨解码、来源文件、两棵版本链、当次审阅 JPEG、交付卡、历史播放和故障账本。API core 512 项、Web 411 项通过；Web TypeScript 与 production build 通过。API 有 4 条既有警告。验收中记录的原生 wire 和截图只保留操作数据；凭据未归档。
