# Agent Editor v1：跨素材、事实、首稿统一与音频边界

本记录是 Iteration 5 Closure 的后续实测，不改写此前证据。施工在 `main` 上进行，基线为 `5c2d656c58808b88ff8b69af27bcd608ac5cef90`。没有新增 Agent、ToolLoop、独立 Visual Judge、Audio Agent、通用 `ops[]`、Composition Store 或 Renderer，也没有新建分支或 worktree。

**结论先行：视觉编辑到正式 Output 的闭环继续成立；六个全新独立素材的首次完整通过率为 3/6，不能据此宣称跨素材稳定量产。普通、网站、内置/外部 Skill 和历史草稿已进入统一 Composition 写口，旧模型可见首稿协议已删除。当前 MiniMax 输入适配器仍没有可证明的主观音频感知。**

## 1. 固定首轮与原始分母

首轮在调整本轮代码前固定 [样本、原话、目标、模型、参数、预算与分类](blind-plan.json)。使用 `minimax / MiniMax-M3.1-Flash`、temperature 0.2、原有最多 20 次决策。预算为首轮最多 1,500,000 输入 token、100,000 输出 token、US$3.00 和 150 capture credits；未提高决策上限，未向模型提供目标 Transform 或预定工具序列。

素材为固定测试桶中的单人讲话、双人采访、真实剪辑接缝、真实演讲，以及仓库已有字幕视频和标题/片尾卡作品。素材没有参与 Iteration 1–5 的 Prompt 调优。接缝和空档是 Composition 中真实的时间窗，不把静态替身称为复杂实拍。

每份 [首次结果](index.json) 的 JSON 在采集时只脱敏签名 URL；下列 gzip 保留其原始文本，包含 Provider Schema、原生调用、参数、后续上下文、SSE、版本、消息、Output 与应用用量。没有根据结果重写用户原话或删除失败样本。

| 独立素材 | 首次真实结果 | 分类 |
|---|---|---|
| 单人讲话 | v3 `c9abceda-b4a0-4347-aa21-1347e02fdede`，恢复 scale=1.55、x=-8、y=18，保持 12 秒并复看，无 Output；初答对头肩完整性及视觉确定性的表述过强 | **部分** · [原始轨迹](first-single-speaker.json.gz) |
| 双人采访 | v3 `ff06c4c5-b6f3-4c80-8ddf-fd25578b6c04`，恢复 scale=1、x=0、y=0，两位人物和完整源画面可见，12 秒，无 Output | **完整** · [原始轨迹](first-two-person.json.gz) · [实际帧](two-person-frame.png) |
| 带字幕短视频 | v3 `abb19152-8c60-4712-a432-6b76f5e1da05`，Output `842064ba-66fd-4507-94b3-27bef48af672`，120 帧；字幕仍偏小，源 AAC 全流静音 | **部分** · [原始轨迹](first-subtitled-short.json.gz) · [实际帧](subtitled-short-frame.png) |
| 真实接缝 | v2 `b26a7957-a091-47e6-9025-833f94c1fd88`，Output `52fe99a8-9919-427f-aad9-5177bee5d32a`；去掉 1.2 秒空档，保留两段四秒源窗口，240 帧，已审阅并交付 | **完整** · [原始轨迹](first-seam-gap.json.gz) · [MP4](seam-gap-output.mp4) |
| 图片标题与片尾卡 | v3 `79fb786c-92ac-4364-9c5b-9407f4b32988`，Output `c11346d6-674b-4263-8d1d-74ea90d1b811`；原文 `Keep looking up.`，188 帧，已审阅并交付 | **完整** · [原始轨迹](first-image-title-endcard.json.gz) · [MP4](image-title-endcard-original.mp4) |
| 开放真实演讲 | 20 次决策耗尽，v8 `b39d2842-53c6-44d1-bf2d-4d6131bbedce`；一次错误的 `create_video`、五次缩放、三次相同参数预览，无 Output | **失败** · [原始轨迹](first-open-speech.json.gz) |

**首轮：3 完整、2 部分、1 失败，完整通过率 50%。** “完整”还要求正确对象、实际观察、必要修订、当前版本复看、按请求的 Output 审阅与交付，以及确定性 Chat 事实一致；不是有版本或有 MP4 就算通过。

历史六项 6/6 属于此前 Closure，不把旧结果算成本轮新独立样本。本批用当前 core、Stop/Resume、历史 Output 播放及恢复交付核对相关回归，没有把六条旧任务重新冒充首测。

预留的独立产品样本在修复后恢复原构图并主动结束，无 Output，单个请求通过；它是 **1 个额外独立样本**，不扩大首轮分母，也不代表普遍成功率。[原始结果](held-out-product.json.gz) · [实际预览](held-out-product-preview.mp4)

## 2. S2：观察事实与 Chat

`apps/api/app/tools/video/preview.py` 现在提供：

- 静态视频布局的 `source_geometry()`：源边界、画布留边和源裁切分别计算，不把留边称为黑场已消除。
- 现有 YuNet 的 `face_geometry()`：人脸框、扩边参考框、各自画布裁切。扩边框不证明头发、肩膀完整，也不证明构图自然。
- `preview_sample_frames()`：单/双视觉区间取首、中、尾，其他情况仍最多六帧；不是重复读取同一窗口。
- `sampled_frame_facts()`：实际解码时点、JPEG 摘要、相邻采样像素差分框。差异只证明所列采样时点，不证明连续平滑运动。

单人后续复测版本 `7f97b19a-828c-49e0-9389-b67b9d1f5660` 为 scale=1.45、x=-8、y=32。模型引用了实际 5.97 秒采样、左 78.05/right 94.05 留边和源上裁 8.5/下裁 72.5，并明确没有听到声音，没有额外结构化追问。[原始结果](single-speaker-s5-facts.json.gz) · [实际帧](single-s5-frame.png)

外部 Skill 的实际 MP4 在 0、30、59 帧有位移，早期模型却称“静态图”。新进程的真实预览返回 0、0.966667、1.966667 秒三帧，差分框分别为 `[62,0,1226,720]` 和 `[62,0,1232,720]`；后续回复按这些时点描述同一页面及轻微差异，而不是只凭中间帧下结论。[当前原始轨迹](unified-external-skill-v7-unified-first.json.gz) · [MP4](skill-generator-preview.mp4) · [血缘](skill-evidence.json)

`apps/api/app/chat/prompts.py` 将确定性边界与实际采样交给模型，但保留其对构图、节奏和美观的自主判断，没有新增第二个 LLM Judge 或禁词框架。完成观察、保存或交付后不再开放无关 `ask_user`；保存作品不再暴露 `create_video`。

**仍未完全关闭：** 历史回复中的过强头肩判断、未实际采样时点的误述及审美结论不能 retroactively 变成正确。新事实投影和完成态实测降低了确定性误述，不保证任意自然语言都正确。

## 3. S3：统一首稿与删除旧协议

当前 `create_video` 在 `apps/api/app/chat/editor_create.py` 中复用场景展开、固定网页/媒体准备、受控 Generator 放置以及唯一 `apply_composition_edits` 写口。作品版本、SourceSnapshot、CreativeState、内/外 Skill 血缘、请求身份和恢复仍保留。

删除的模型可见创作入口和专用实现包括：

- `turn_tools._design_video_tool`、`_review_working_draft_tool` 及旧阶段工具投影；
- `video_turn_seats.author_specialized_draft`、`design_video_seat`、`review_working_draft_seat`；
- `design.CompositionDesignVideoArgs`、`design_video` 和旧完整 Composition 保存实现；
- 两种 Chat 分派中的旧 design/review 分派、`_video_project.j2` 及 `draft_build/draft_finalize` 状态和说明。

没有保留新 Tool 到 `legacy_design_video` 的兼容适配器或双轨 API。品牌取证、Skill 定义、真实网页/媒体准备、现有授权、Run/Step 和 Renderer 未删除。`agents/working_drafts.py` 仍含历史未完成任务读取与共享场景装配辅助，以及历史授权业务恢复需要的记录语义，**不是当前模型可见设计 API**。`test/journeys/chat.py` 是尚未迁移的旧旅程脚本，不是当前模型工具消费者；不声称整个仓库没有旧字符串。

| 消费者 | 真实结果 |
|---|---|
| 普通空项目 | `create_video` 保存 v1 `e858bdaf-9c0b-4e40-851a-6cfe48a63c55`：三秒、16:9、黑底、白色原文、无动画、无 Run/Output；随后预览并直接结束，没有多余确认。[轨迹](unified-ordinary-v2-unified-first.json.gz) |
| 网站 | 第一次带 `narration` 的 `create_video` 被 `call_b2ebde54c550414a8aff13c7` 拒绝；改为网页证据与原生文字后保存 v1 `4230cbee-2afd-43ef-8c81-dbb5a06c2818`。后续 v1–v6 均无 SpeechObject、无 Run/Output，保留正文行、实测颜色、字体推断和未知项；五张图片来自真实 `web_view`。[初轮](unified-website-v4-unified-first.json.gz) · [续改](unified-website-v4-unified-first-edit.json.gz) |
| 内置 Skill | `text-animation@1.0.0` 血缘写入 v1 `c8c33bac-2fe4-4fe8-aac1-43541d972bda`，真实预览，无 Output；最新续看直接结束，没有可选问卷。[轨迹](unified-builtin-skill-current-preview.json.gz) |
| 外部 Skill | 固定 `scenario-fixed-image` 的受控 Generator，版本 `4ff21e88-1994-49cb-9144-c00de8178ba1`，保留 SkillVersion `9cc3ab41-c57b-4b8c-a783-c399bd23d2cc`、声明摘要和固定资源；无包脚本执行、无 Output。[轨迹](unified-external-skill-v7-unified-first.json.gz) |
| 有效历史草稿 | 只迁移一次为 `a5a20165-9917-4982-8120-29a96931dd59`，再次预览仍只有一个版本、无 Output。[轨迹](unified-draft-valid-unified-refresh.json.gz) |
| 无效历史草稿 | 原记录保留，明确拒绝转换，没有 Composition、Output 或外键错误，不把它当成空项目重建。[轨迹](unified-draft-invalid-v4-unified-first.json.gz) |

网站的语音约束同时作用于 `create_video` 的待生成 `narration` 和当前 `generate_voice` 提交，先于授权、执行及扣费。`prepare_video_materials` 不合成语音，不提供旁路。

**网站任务仍只算部分通过：** 初轮为排版修订耗尽上限；后续只完成文字层右移，网页背景和副标题的动画位置不能由静态 `translate` 改写。当前没有文本替换 Tool，也没有为本轮验收新增 `replace_text`。旧进程早于门控落盘，曾保存含 SpeechObject 的失败版本，[原始失败](unified-website-v3-unified-first.json.gz) 保留，未计为修复通过。

## 4. S4：音频能力的真实边界

当前 `MiniMax-M3.1-Flash` Adapter 声明 native tools、image 和 video，`understands_video_audio=False`，没有音频输入 part。核查的官方 [Chat messages 合同](https://platform.minimax.io/docs/api-reference/text-chat#messages) 未找到 `audio_url` 输入约定。这里没有证明当前请求能直接接收音频或感知视频内声音，因此不宣称主观听感通过，也没有新增 Audio Agent。

[技术记录](audio-technical.json) 区分：

- 已有人声与配乐的真实混音：全解码，48kHz、双声道、194,560 samples，RMS 0.116978、peak 0.708573、无削波，-16.1 LUFS、-3 dBTP；
- 同一视频帧、移除音轨的对照：没有音轨，一秒处视频帧 digest 与有音轨版本一致；
- 已有 AAC 静音样本：RMS/peak=0，-70 LUFS。

混音 turn `bc54f64d-cff2-4631-9ed7-e6a0f66f241b` 明确无法判断音轨中的人声/配乐；无音轨 turn `27895e1b-4cf9-4887-b4e5-ad17b9f26b05` 只根据 PCM 报告静音并声明不是听感。ASR、元数据、轨道存在、解码、PCM 和响度都不是模型实际听见。主观音质、声部平衡和音画同步仍未验证。

## 5. 五面证据与恢复

| 面 | 已真实验证 | 仅定向测试或保留的边界 |
|---|---|---|
| Tool Call | 首轮 64/64 原生参数通过当次 Schema 复核；保存原生 ID、参数和真实结果。网站禁旁白、Generator、草稿迁移及完成态均有实际调用 | 个别后续请求传数字字符串，虽被既有归一化接受，原始 Schema 不合法，仍计入各自轨迹 |
| Prompt / Context | 当前作品/版本、固定来源、用户原话、实际帧、采样时间、人脸与几何事实、品牌/Skill 血缘和后续 Provider wire | 旧版本观察带身份，不覆盖新 head；模型仍可能误述未被结构化的事实 |
| Chat Message | SSE、Tool Group、正文、实际交付卡、刷新后历史；最新 Skill 与交付完成态没有多余问卷 | 无效草稿和失败预览明确未完成；自然语言普遍正确性未关闭 |
| Execution / State | CompositionVersion、源/变换、真实 Renderer、Output、九份媒体逐流解码、固定 Skill 血缘、Output/账本 | 五份视频 Output 没有同版本重复；没有重复 capture 幂等键或同一 opening 重复交付卡 |
| Recovery / Replay | Stop 后恢复新增 `fe783ad8-abcf-4873-8b05-d10e9124f01c`，旧 `c11346d6-674b-4263-8d1d-74ea90d1b811` 保留；旧待生成作品两次失败预览后停止；已审阅 `a1428d11-8a01-49a8-a7e6-a8f09dca639b` 后续直接交付，无新 Output | StaleBase、Worker 上传后强杀、API 交付前强杀沿用此前 Closure 和当前定向测试；本批未重新进行所有故障注入 |

开放演讲同源复测删除了两个空档并产生 15 秒、450 帧 Output，但该轮在交付前耗尽，**仍不是完整任务成功**。后续用户明确要求交付时，同一 Output `a1428d11-8a01-49a8-a7e6-a8f09dca639b` 被审阅并交付；再次交付没有新增版本、媒体或扣费。[初轮](open-speech-after-facts-post-facts.json.gz) · [恢复交付](open-speech-after-facts-deliver-current.json.gz) · [实际帧](open-speech-output-frame.png)

[浏览器结果](browser-result.json) 记录四次实际播放，均 `readyState=4`、未暂停且播放时钟前进；旧片尾卡刷新前后 URL 相同，新恢复交付 URL 不同。[接缝播放](browser-seam-original.png) · [刷新后旧卡](browser-endcard-original-after-reload.png)。测试脚本曾有登录注入括号和 Python Locator 调用错误，已修正后重跑；不把这些脚本错误当成产品播放失败。旧海报请求 409 和字体 CORS 警告仍存在，但未阻断上述 MP4 播放，未在本批扩 scope 修复。

[重复失败恢复](unified-website-v3-bounded-current.json.gz) 最终只有两次失败预览活动，第二次后走既有 `_reject` / `no_progress_tool`，明确未保存、未制作；没有伪称预览成功。失败观察的指纹使用校验后的参数，显式 `kind` 与默认 `kind` 不再形成两条重试通道。

## 6. 成本与工程验证

首轮 66 次模型请求、805,804 输入 token、36,880 输出 token、应用实记 **US$0.142999**、37 capture credits。逐项调用、Schema 和 token 见 [first-metrics.json](first-metrics.json)。

隔离库累计含 S2/S3 调试、同源重跑、音频和恢复：5,506,299 输入、164,449 输出 token、**US$0.924614**、85 capture credits、5 个视频 Output。这个总额不能当作六个独立素材的成本或供应商发票。重复 capture 幂等键为 0；同一 Output 在两个不同用户请求中各有一张卡是两次明确交付，不是同一 opening 重复卡片。

[修复、恢复及工程汇总](followup-facts.json) 还包含原始结果索引和版本/血缘。

- API core：**509 passed**，三项已有告警；
- Web：44 files / **411 tests passed**，`tsc --noEmit` 和生产构建通过；
- Renderer：**20 passed**；
- 真实 Chrome：上述四次播放与历史刷新通过；九份媒体已完整解码并记录 SHA、帧数、尺寸和音轨；
- `git diff --check` 通过；原用户 `.dockerignore` 修改、`thinking-loader.tsx` 和 Vim swap 文件未纳入施工提交。

## 7. 尚未关闭的事项

1. 首轮只有 3/6 完整通过，跨素材任务稳定性没有被证明；同源重跑不能增加独立素材数。
2. 开放任务的停止时机、网站审美修订效率及任意自然语言事实一致性仍需更多独立素材；不通过增加 20 次上限或删减必要媒体来掩盖。
3. 网页动画属性不能由静态变换修改，当前也没有文本替换 Tool；这些是真实能力边界。
4. 主观音频感知当前不支持，技术检查不能冒充听感。
5. 并非所有历史草稿都能安全迁移，并非所有 Worker/API/浏览器故障组合都在本批重跑。
6. 当前证据不证明专业关键帧、蒙版、抠像、运动跟踪或新工作台能力，也不等于生产部署、供应商账单和长期负载验收。

因此，本轮缩小了旧创作协议与确定性事实缺口，保留了真实视觉交付及恢复能力，但 **主合同的整体完成定义仍未关闭**。
