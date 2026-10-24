# Synthetic Talk Video——R5 声音路径 PLANNED 合同

> Status: **已拍板、未实施、未排定当前交付批次**。目标输入是文字稿 + 照片 + 可选声音样本/已绑定声纹，先生成可复用的发言源，再进入现有下游。R2 的无声照片轮播不视为本需求已完成。启动时须按当前 registry、film-spec、工具与 persona/voice 实现重新核对座位。

## 1. 产品边界

- 服务“只有演讲文字稿和照片、没有录像”的知识专家；生成的是用户自己材料的合成发言源，不是 Factory 通用数字人。
- v1 是 TTS + 照片/文字/音频的确定性合成：动态照片、逐句字幕、可选波形与品牌样式；**不接唇形同步 avatar，不伪装真人出镜**。
- 文字稿 + 照片可以形成 clips 合法输入；纯文字仍只能走无需媒体的文案产物，不能借本需求绕过 clips need media。
- 已有 persona 声纹直接复用；没有时可上传满足 provider 要求的声音样本。样本授权、voice 绑定与删除沿用 persona/voice 和素材权限，不另开隐式克隆入口。

## 2. 目标链与架构约束

1. `voice_gen`：文字稿 → persona 声纹/TTS → 音频 asset，`provenance=generated`，保留文字稿、persona/voice 与样本的来源关系；TTS usage 进入现有计量。
2. `synth_visual`：照片 + 音频 + 对齐字幕 + brand → 合成发言视频 asset，记录输入来源；照片运动、字幕与时长必须可由参数重现。
3. 合成音频/视频进入现有 ASR 与素材处理，获得下游所需词级时间戳；director、clips、文案与交付仍复用同一链路，不按“真实拍摄/合成”分叉。
4. 新步骤注册到当前 StepKind/runner/PROCESSORS 与活动投影，用户只看到诚实的工作描述，不出现工具名或内部 spec 名。
5. 输入拓扑由确定性输入组合推导，不给 `InferredIntent` 新增“生成模式”，不由 LLM 猜输入类型。

**spec 边界**：合成主片不是 clip，不能把主片硬塞进 clip-spec；若生成视频源，必须复用现行 film-spec 的通用视频/图片/文字元素组合与 `spec.family` dispatch，或复用已有等价合成路径。不得为本需求创造第三套 spec、renderer、渲染 API 或录屏专属系统。实现前先确认生成 asset 与最终 output 的契约边界，不能靠改名绕过 family 校验。

## 3. 数据、计量与失败

- 音频与视频 asset 均标 generated，下游 output 保留完整 provenance/source_ref；不能把合成来源写成实拍。
- TTS、ASR、渲染按真实调用分别计量；估价、守卫线和授权在付费执行前生效，不以“合成成本低”绕过费用规则。
- 无声纹且无可用样本时先补齐输入，不静默改用无关 stock voice；用户明确选择 Auto/stock 时按 persona/voice 现行语义处理。
- 确定性检查至少覆盖音画时长、字幕时间戳单调与越界、分辨率、文件可读与 ASR 可用性；失败保留真实原因，不伪装成片。
- 是否增加 LLM judge 不在本合同预设禁令或承诺中，遵循当时统一质量架构；本路径自身不新增第二套 verify 体系。

## 4. 前端与 API

- Home/composer 与出生地的 clips 校验镜像放行“文字稿 + 照片”组合；不能因为本地曾有 demo 素材就把真实输入替换掉。
- 缺声音输入时给可一词回答的下一步或明确上传引导，不弹第二意图入口，不自动发消息。
- 步骤、错误、生成来源标记均 en/zh；中间 asset 与最终 output 在画布/结果面的类型、画幅和谱系一致。

## 5. 验收

1. en 与 de/fr 至少一门欧洲语言：文字稿 + 3 张照片 + 合法声音样本 → 合成发言源 → 可选段 clips；每条可渲染、可进编辑器，词级时间轴可用。
2. 复用已绑定 persona 声纹与现场上传样本各走通一次；未授权/缺失样本不被静默克隆或替换。
3. 检查 audio/video/output 的 generated provenance、source_ref、persona 与原始文字稿/照片回溯。
4. TTS、ASR、渲染 usage/cost 与钱包/台账一致；守卫线和 NULL 不可报价路径仍确认。
5. 音画时长、字幕边界、分辨率或文件检查失败时步骤诚实 failed，错误可读且不产假 output。
6. 实拍的 video/audio 路径回归无行为变化；纯文字不误建 clips；film-spec/clip-spec dispatch、preview/retry/revision/recovery 均无第三通道。
7. 双主题与移动端展示、合成步骤活动、失败重试、刷新回放与交付均通过；真实声音质量由用户试听，不由测试分数替代。

## Prohibited Behaviors

- 禁唇形/真人 avatar、未经许可的声音克隆、把 generated 标成实拍。
- 禁第三 spec/renderer、禁绕过 `spec.family` 与渲染身份围栏。
- 禁无声片冒充本需求完成，禁无素材生成、伪造 ASR/时间戳或吞失败。
- 禁新意图端点/生成模式字段、第二套计费/verify/状态机；禁为 v1 增加非必要录音 widget。
