# Persona Style Panel —— 人设页风格面板渲染重构（表单 → 卡片/标签）

> Status: Active（2026-08-13 立项）
> 依据：外部评审建议经闸门过滤后采纳（多模型决策工作流）； persona-identity 简报 §4 验收 2 的体验补刀
> 排期：**第二周（08-09~08-14）顺做**，估 1 天；不占周五 08-14 联合验收关键路径，挤压则吃第三周缓冲（2026-08-13 拍板（四），PROGRESS 第二周）

## 1. 背景与目标

人设页「人设」tab 把四个**列表型字段**用 `\n` join 塞进四个 Textarea（`_app.personas.$id.tsx:385-394`）——数据库里本来就是 JSON 数组（`tables.py:94-99`），是前端把它压成了灰框长文。AI 提炼（`POST /personas/{id}/generate`，`memory/routes.py:150`）的结果以"待批改的调查问卷"形态呈现，专家读不出"AI 眼中的我"。

**目标：呈现形态从表单渲染升级为卡片/标签渲染——纯前端，数据形状、保存载荷、提炼端点零变化。** 数据一模一样，阅读体验从"填表"变成"看 AI 给我画的像"。

**范围外（已进需求池，本简报禁止夹带）**：per-field 再提炼（"换一版"）、persona 对话微调、AI 印象摘要字段。

## 2. 改动面（按字段逐一裁决）

| 字段 | 现状 | 终态 | 理由 |
|---|---|---|---|
| `core_values` | Textarea（\n join） | **chips 云**：短词标签，× 删除 + 行尾「+ 增加」行内 Input | 短词列表，标签天然形态 |
| `avoid_words` | Textarea | **chips 云**（`destructive` token 变体，醒目但克制） | 禁区词需要一眼可扫 |
| `typical_hooks` | Textarea | **金句卡**：句子型条目逐条成引用块卡片，× 删除 + 末尾「+ 增加」 | 句子不是词，塞 chip 会破行 |
| `favorite_metaphors` | Textarea | **金句卡**（同上） | 同上 |
| `emotional_tone` | Select | **不动** | 已是控件化枚举 |
| `sentence_style` | Input | **不动** | 短语单行，表单形态合适 |
| `guidelines` | Textarea | **不动** | 自由长文，表单形态天然正确 |
| `audience` / `cta` | Input | **不动** | 单行文本 |

**交互三律**（chips 与金句卡共用）：× 即删（无确认，保存才落库）；「+ 增加」行内展开单行 Input，回车/失焦提交；点击条目进入行内编辑。保存仍走现有 `handleUpdatePersona` PUT 整个 persona——**状态从 `\n` join 字符串还原为 `string[]`**，join/split 逻辑（:123-128 / :155-160 / :182-187）随 Textarea 一起删除。

**页头概览卡**（现有字段拼装，无 AI 摘要）：当前页头只有 name/title 两行。升级为一张概览卡，聚合已存在的数据——name / title / language、`voice` 绑定状态（Auto / 已绑声纹 / 系统音色）、`brand` 状态（默认皮肤 / 自定义）、素材数（materials count）、`calibrated_at`（最近提炼时间）。零新字段、零新端点；各状态项点击跳对应 tab。

**组件家**：新组件落 `components/persona/style-chips.tsx`（chips 云 + 金句卡两个导出，与 `skin-editor.tsx` / `voice-section.tsx` 同目录同命名风）。

## 3. 设计纪律（对闸门后的提案修正）

外部提案的视觉细节按项目设计系统修正如下，施工时以本节为准：

- **禁 emoji 装饰**（🌐🔗🚫✨🪄 全砍）：图标唯一来源 lucide-react；`avoid_words` 的醒目用 `destructive` token 的 chip 变体，不用 emoji、不硬编码色值；
- **chips 形状**：`rounded-md`（Badge 系 override 纪律；`rounded-full` 禁令适用）；
- **fill-first**：chips / 金句卡用 `bg-muted` 实心填充，**不画 ring/border**；金句卡左侧可用 `text-meta` 的引号符或 lucide `Quote` 小图标点睛，不画竖线描边；
- **文案**：控件文案 = 直给动词 + 具体名词（"添加价值观"、"添加禁区词"）；**禁**"定妆照 / 数字人名片 / AI 印象"等造词进 UI（概览卡标题用现有 `personaDetail.personaTitle` 语义）；
- **i18n**：新增文案 en.ts 先行、zh.ts 镜像（TS 类型守门）。

## 4. 验收口径（用户视角）

1. 打开人设页「人设」tab，AI 学到的价值观 / 口头禅 / 禁区词是一眼可扫的标签云与金句卡，不再是四个灰框段落；
2. 点 × 删一条、「+ 增加」补一条、点条目改一条，保存后刷新仍在（PUT 载荷与现状同为 `string[]`）；
3. 点「重新提炼」（generate）后，新结果以同样的卡片形态呈现，无形态回退；
4. 页头概览卡一眼看到：这个人设是谁、声音绑没绑、皮肤是不是默认、学了几份素材、上次什么时候提炼的；点状态项跳对应 tab；
5. en / zh 双语无硬编码文案。

## 5. Prohibited Behaviors

- **禁**改后端任何一行：`personas` 表 / schema / `generate` 端点 / PUT 载荷形状全部不动（列表字段仍是 `string[]`）；
- **禁**夹带范围外三件：per-field 再提炼端点调用（"换一版"按钮）、任何对话微调气泡 / 微型 chat 面、AI 摘要的拼凑（拿 `guidelines` 截断冒充摘要）——均已在需求池登记，另行拍板；
- **禁** emoji 进 UI、禁硬编码色值、禁 `rounded-full`、禁可见描边（§3）；
- **禁**把 `guidelines` 也 chips 化（自由长文保留 Textarea）；
- **禁**新增非 i18n 文案；禁 Sparkles 图标；
- **禁**保留 `\n` join/split 兼容层——Textarea 退役即删干净，不留双形态分支。

## 6. 实施锚点

- 改动文件：`_app.personas.$id.tsx`（四个 Textarea 块 :385-394、join/split 状态三处 :123-128 / :155-160 / :182-187、页头 :299-312 升概览卡）；
- 新文件：`components/persona/style-chips.tsx`；
- i18n：`personaDetail.*` 增补 chips/金句卡/概览卡键（en 先行）；
- 回归点：generate 按钮流程（提炼后卡片刷新）、保存流程（string[] 直出）、空列表占位态（未提炼时的引导文案沿用现有 `fieldPlaceholder` 语义）。
