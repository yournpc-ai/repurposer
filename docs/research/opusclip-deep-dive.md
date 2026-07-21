# OpusClip（Opus Pro）产品流程调研

> 调研时间：2026-07-03  
> 调研方式：实际体验 + 界面截图分析 + 公开资料检索  
> 与 Repurposer 的关系：OpusClip 是“真人视频 AI 剪辑”工具，与 Seedance（AI 生成视频/图片）有本质区别。其“输入 → 配置 → 结果页 → 精修编辑器”的闭环对 Repurposer 的 clip 编辑流程有重要参考价值。

---

## 1. 产品定位

OpusClip 面向内容创作者，核心定位是：

- **输入**：任意公开视频链接（YouTube、Vimeo、Drive 等）或本地上传
- **处理**：AI 自动识别高光、生成多个短视频 clip、自动加字幕/排版
- **输出**：可直接发布的 9:16 / 1:1 / 16:9 短视频
- **商业模式**：Freemium，免费版带水印与功能限制，Pro 版解锁更多模板/导出/无水印

---

## 2. 完整用户流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 1: 首页 / 主入口                                                   │
│  ─────────────────────                                                   │
│  只放一个输入框：                                                         │
│  “Drop a video link or upload a file”                                   │
│  支持 YouTube、Drive、Vimeo、本地上传等                                   │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 2: /workflow 配置页                                                │
│  ────────────────────────                                                │
│  页面展示已粘贴的链接 + 视频缩略图                                        │
│  上方主 CTA：Get clips in 1 click                                        │
│  下方配置区：                                                             │
│    • Speech language 下拉框                                              │
│    • Upload SRT（可选）                                                   │
│    • Credit usage 消耗提示                                                │
│    • Tab 1: AI clipping / Don't clip                                     │
│        - AI clipping: Clip model / Genre / Clip Length / Auto hook       │
│                         Include specific moments prompt                  │
│                         Processing timeframe 滑块                        │
│        - Don't clip: 保留原视频长度，仅做处理                             │
│    • Tab 2: Quick presets / My templates                                 │
│        - Quick presets: 字幕样式预设（No caption / Beasty / Karaoke…）    │
│        - My templates: 用户保存的品牌模板                                 │
│        - Aspect ratio 选择（9:16 等）                                     │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 3: 结果页（clip grid）                                             │
│  ────────────────────────                                                │
│  URL 示例：无固定可见路由，表现为项目结果页                                │
│  页面显示：                                                               │
│    • 顶部：原始视频标题 + 可播放原视频链接（跳转 YouTube）                 │
│    • 搜索/指令框：Find keywords or moments...                            │
│    • 提示词展示：用户进入 workflow 前输入的 prompt                        │
│      例如 “Give me highlight compilations of all the exciting moments”   │
│    • 网格排列生成的 clip 卡片：                                            │
│      - 缩略图 + 时长 + AI 评分（99 / 92 / 89…）                           │
│      - 标题、标签                                                         │
│      - 日历、下载、编辑入口                                               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 4: /editor 精修编辑器                                              │
│  ────────────────────────                                                │
│  点击 clip 卡片上的编辑按钮 → 进入独立 editor 路由                        │
│  首次进入弹出 8 步引导 tour（可 Skip）                                    │
│  页面结构：                                                               │
│    • 顶部：返回按钮、项目标题、Save changes、Export、credit              │
│    • 左侧：transcript 文字稿                                             │
│      - 播放时当前 segment 高亮                                           │
│      - 点击 segment 可跳转视频到对应时间                                 │
│      - 无语音段用 ********* 占位                                         │
│      - 右键菜单：Edit / Delete / Timing / Split & trim / Highlight       │
│      - “+” Add 菜单：AI Image B-Roll / Stock Video B-Roll / Emoji / AI hook
│    • 中间：视频预览（带字幕叠加）                                         │
│    • 右侧：工具面板                                                       │
│      - AI enhance / Captions / Media / Brand template / B-Roll          │
│      - Transitions / Text / Audio / AI hook                              │
│    • 底部：时间线 + 音频波形                                              │
│  引导 tour 8 步：                                                         │
│    1. Edit captions                                                      │
│    2. Add a section (hook)                                               │
│    3. AI enhance                                                         │
│    4. Timeline editing                                                   │
│    5. Adjust layouts (Fill/Fit/Split/Three/Four/ScreenShare/Gameplay)    │
│    6. Customize your caption (font/effect)                               │
│    7. Manual subject tracking                                            │
│    8. AI sound effect                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 关键页面拆解

### 3.1 首页输入

- **极简**：只有一个输入框，降低首屏认知负荷
- **链路短**：粘贴链接后即可进入下一步，不需要先命名项目或选择模板
- **默认动作明确**：输入后引导到 `/workflow` 配置页

### 3.2 /workflow 配置页

这是 OpusClip 的核心“预处理”页面：

| 元素 | 作用 |
|------|------|
| `Get clips in 1 click` | 主 CTA，触发 AI 处理 |
| `Speech language` | 指定 ASR 语言 |
| `Upload SRT` | 允许用户提供已有字幕，提高精度 |
| `Credit usage` | 提前告知消耗 |
| `AI clipping / Don't clip` | 决定是自动切多个 clip，还是只处理整条视频 |
| `Clip model / Genre / Clip Length / Auto hook` | 控制 AI 剪辑策略 |
| `Include specific moments` prompt | 用自然语言指定想要的内容 |
| `Processing timeframe` 滑块 | 只处理视频的某一段，省 credit |
| `Quick presets / My templates` | 字幕样式与品牌模板选择 |
| `Aspect ratio` | 9:16 / 1:1 / 16:9 等 |

**启示**：把所有“生成前决策”集中在一个页面，比分散在 chat 里更高效。

### 3.3 结果页

- **结果导向**：用户直接看到可消费的 clip 卡片
- **评分机制**：每个 clip 有 0-100 的 AI 评分，帮助用户快速筛选
- **提示词回显**：顶部展示用户最初的 prompt，保持上下文
- **可播放原视频**：点击标题可跳转原始来源
- **Co-Pilot 搜索框**：顶部 `Find keywords or moments...` 允许自然语言重新筛选/生成

### 3.4 /editor 编辑器

这是 OpusClip 的精修层，功能非常完整：

| 模块 | 功能 |
|------|------|
| Transcript | 点击跳转、播放高亮、编辑字幕、删除片段、分割修剪 |
| Player | 实时预览字幕与效果 |
| Right tools | AI enhance / Captions / Brand / B-Roll / Transitions / Text / Audio / AI hook |
| Timeline | 片段级剪辑、布局切换、音频波形 |
| Export | 导出最终视频 |

**关键交互细节**：

- 播放时 transcript 当前 segment 高亮
- 点击 transcript 可 seek 到对应时间
- 无语音段用 `*********` 占位
- 右键 transcript 有上下文菜单
- 首次进入有 8 步 onboarding tour

---

## 4. 与 Seedance 的本质区别

| 维度 | Seedance（即梦） | OpusClip（Opus Pro） |
|------|------------------|----------------------|
| 核心能力 | AI 生成视频/图片 | AI 剪辑真人视频 |
| 输入 | prompt / 图片 / 参考 | 视频链接 / 本地视频 |
| 输出 | 从无到有的生成内容 | 从长视频切出的短视频 |
| 交互模型 | Home / Create / Library | 输入 → workflow → 结果页 → editor |
| 编辑深度 | 轻（重生成） | 深（时间线 + transcript + 多轨工具） |
| 用户心智 | “帮我创作” | “帮我剪辑” |

---

## 5. 对 Repurposer 的启发

Repurposer 的定位更接近 **“面向知识演讲者的 OpusClip + 文本内容生成器”**：输入一场演讲/访谈，输出 clips、LinkedIn 长文、quote cards、多语言摘要等。

### 5.1 可直接借鉴

1. **结果页优先**：先生成结果卡片网格，再让用户决定是否需要精修
2. **workflow 配置页**：把生成前的参数选择（语言、输出类型、语气、品牌模板）集中展示
3. **transcript 作为 clip 编辑的主界面**：点击跳转、播放高亮、删除/隐藏 segment
4. **一键 AI 增强**：去 filler words、去停顿、加 hook、换字幕 preset
5. **首次使用 onboarding**：首次进 editor 时给 3-4 步轻量引导
6. **提示词回显**：在结果页显示用户最初的 prompt，方便迭代

### 5.2 需要谨慎照搬

1. **多轨时间线 / B-Roll / 转场 / 音效 / 表情贴图**  
   这些属于 L3 视频编辑功能，违反 Repurposer ADR-016 的 scope 纪律。如需专业剪辑，应导出到 CapCut / Premiere。

2. **复杂的字幕样式自定义**  
   OpusClip 提供大量 free-form 样式。Repurposer 应保持 **preset enum**，确保 clip-spec 可在 Remotion 与 FFmpeg/libass 之间切换。

3. **Manual subject tracking / AI B-Roll**  
   技术复杂度高，MVP 阶段不建议做。

### 5.3 建议的 Repurposer 流程

```
Home: hero + demo gallery + 输入框
        │
        ▼
Create /workflow: 选择输出类型、语言、speaker、brand template
        │
        ▼
/projects/$id: chat thread + 结果卡片展示
        │
        ├── clip 卡片 → /projects/$id/clips/$clipId/edit
        │   └── 轻量 clip editor: transcript + player + presets + AI enhance
        │
        ├── LinkedIn post / summary 卡片 → inline 编辑
        │
        └── quote card → Brand template 页预览编辑
        │
        ▼
Library: 所有生成资产的历史库
```

---

## 6. 调研来源

- 实际产品体验：opus.pro
- 公开文档：
  - [OpusClip API - Create Project](https://help.opus.pro/api-reference/endpoints/create-project)
  - [OpusClip URL to Video AI](https://www.opus.pro/agent/workflows/url-to-video-ai)
  - [OpusClip Homepage](https://www.opus.pro/)
  - [How to Use Opus Clip - passiveincomemd.com](https://passiveincomemd.com/blog/reviews-recommendations/how-to-use-opus-clip-ai-for-your-social-media-videos/)
  - [OpusClip Full Tutorial - KDCC Blog](https://blog.kdcc.social/opus-clip-full-tutorial-grow-youtube-with-ai-clips/)
