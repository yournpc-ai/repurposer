# Chat 自足、锚卡与 Home 交互——当前合同与剩余验收

> Status: 环境谓词、终态锚卡、交付承接句、copy/免责声明与数据驱动货架已有代码层结果；移动端完整旅程、桌面对照、声音互斥和双主题 live 验收仍未全部销号。活动展示以当前 `WorkSegmentRow` 为准，不恢复旧 ActivityRow/StatusLine 形态。

## 1. 形态与 chat 自足

- 桌面工作区由当前 `workspace_layout=auto|chat` 与视口能力共同决定；移动端恒纯 chat。用户布局偏好只能力关闭画布，不能在移动端虚假强制开启。
- **chat 自足律**：画布隐藏时仍能完成上传 → 计划/授权 → 生成 → 结果 → 修订，不需要用户打开画布寻找唯一按钮或唯一结果。
- 图模型仍是世界事实源，锚卡只是交付消息的静态产品投影，不是第二 live 面或第二执行状态机。
- 活动/工作段遵循 CHAT_ARCHITECTURE §8.6～§8.7：一行两态、真实工作、真实终态、failed 诚实告警、cancelled 从可见投影退役；本合同不另造折叠规则。

## 2. 环境谓词与交付言语

- 客户端唯一能力组成：`canvasAvailable = 视口可承载 && workspace_layout !== "chat"`；`canvasVisible = canvasAvailable && worldLive`。组件不得另按设备名、宽度或偏好推断第二套环境。
- 能力位随 chat 请求送达并以 last-wins 盖章到 conversation；旧客户端未上报时为 unknown，不是 false。
- 服务端 `canvas_visible = canvas_available ∧ world_live`；`world_live = hasRuns ∨ pending-plan`。unknown 时 Environment 行缺席，所有指向卡片的言语门恒闭。
- 双键经 `build_context` 的结构化 Environment 事实行进入模型上下文；模型不得从用户语言或设备特征猜测环境。
- 交付言语现行法座是 `prompts/chat/delivery_system.j2`：只有 delivered/partial、且事实确证对应产品已交付、且 `canvas_visible=false` 时才能指向紧随其后的卡片；failed 不得宣称有可点产品。
- `canvas_visible=true` 时不写交付承接句，不提“右侧/画布/下方”等面。承接句仍是普通 assistant 散文，必须满足打字机两牙与刷新回放一致。
- 代码内若仍把此法条指向旧 `trigger_system.j2`，以实际 delivery include 为准；不要因注释恢复第二座法条。

## 3. 终态锚卡

- 渲染条件为 `!canvasVisible`，读取**渲染时刻**环境，不把历史移动/桌面快照钉进消息。
- 数据只读终态收据已有 `output_refs`；顺序稳定、id 去重，只投影真实 ready 产品，缺 output/未 ready/失败项不伪造卡片。
- N 个产物为数组平铺小卡，不建合集卡；单卡只显示世界自证的缩略图、名称、类型与真实规格。名缺用诚实类型/规格回退，不用冻参模板补名。
- 锚卡唯一父座是终态收据行；无内联播放钮，点击打开 MediaLightbox；无新增 SSE 订阅，不脱离收据独挂。
- 卡片解剖遵守 ring/圆角/零 in-flow shadow/lucide/i18n；复制按钮为纯客户端动作，免责声明为界面事实而非模型言语。

## 4. Home 货架衔接

- Home 两级 tab 与货架是数据驱动注册表；卡片点击唯一归宿是 composer 预填，不发送、不建 run、不打开模板编辑器。
- 空 shelf/sub/family 不上架；无真实动作的 Queue、mic、反馈等入口不得先摆死按钮。
- 当前文字动画与产品演示货架仍是**占位样片**，其替换和真实能力边界归 `home-creation-entry-refresh.md`；SaaS 真片与占位片不得混称。
- Queue chip 若未来重启必须先有真实队列读数；👍👎 若重启先决定持久化与用户利益；这些不是当前已完成能力。

## 5. 剩余验收

1. 移动端不看画布完成上传 → 生成 → delivered/partial/failed → 接受或修订一次；只有实际 delivered/partial 有承接句与可点锚卡。
2. 桌面 auto + world live：同一次交付零锚卡、零承接句，画布正常；切到 chat 后锚卡按渲染时刻出现，不错误重放历史环境。
3. 能力位 unknown、无 world、pending plan、空 output_refs、重复 id、缺失 output、失败与部分交付分别验证，不出现假卡或假承诺。
4. 多产物数组顺序/去重正确，名缺回退诚实；点击开 MediaLightbox 可播，刷新回放一致。
5. MediaLightbox 与 Home/其他播放器遵守全局声音互斥；离屏暂停不释放错误的播放所有权。
6. copy、免责声明、WorkSegment 展开/收段与深浅主题无回归；移动端无横向溢出，MentionEditor 不 remount，背景更新不动相机。
7. 自动检查按改动面覆盖谓词真值表、锚卡投影、环境装配与交付分支；触及 prompt 面才运行 prompt_gate。live 结果未产生前保持“待验收”，不引用旧通过截图代替。

## Prohibited Behaviors

- 禁第二环境谓词、第二交付言语法座、从设备/语言猜环境。
- 禁 failed 分支产品卡承诺、虚构可播放文件、锚卡新订阅或合集卡。
- 禁死按钮/假队列数/无持久化反馈；禁 Agent 英文文案、工具名上屏。
- 禁模式切换造成相机自动节拍或 MentionEditor remount；禁恢复旧 StatusLine/第二工作段。
