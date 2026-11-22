import type { Resources } from "./en"

const zh: Resources = {
  agentReceipt: {
    job: "媒体操作",
    chargedCredits: "已结算积分 · {{count}}",
    reservedCredits: "预占积分 · {{count}}",
    accepted: "待执行",
    queued: "排队",
    running: "运行中",
    success: "成功",
    error: "失败",
    cancelled: "已取消",
    unknown: "结果未知",
    notExecuted: "未执行",
    pending: "待确认",
    denied: "已拒绝",
    approved: "已同意",
    versionSaved: "版本已保存",
    outputGenerated: "待审片",
    delivered: "已交付",
    group: "工具调用（{{count}}）",
    thinking: "思考中",
    quote: "报价",
    limit: "费用上限",
    approve: "同意",
    decline: "拒绝",
  },
  common: {
    retryHistory: "重新加载对话",
    upload: "上传",
    googleDrive: "Google Drive",
    delete: "删除",
    create: "创建",
    creating: "创建中...",
    save: "保存",
    saving: "保存中...",
    search: "搜索",
    all: "全部",
    back: "返回",
    cancel: "取消",
    close: "关闭",
    done: "完成",
    previous: "上一页",
    next: "下一页",
    remove: "移除",
    loading: "加载中...",
    untitled: "未命名",
    preview: "预览",
    toggleTheme: "切换主题",
    preferences: "偏好",
    helpSection: "帮助",
    theme: "主题",
    themeSystem: "跟随系统",
    themeLight: "浅色",
    themeDark: "深色",
    replayTour: "重播首页导览",
    credits: "积分",
    language: "语言",
    settings: "设置",
    logout: "退出登录",
    login: "登录",
    guest: "访客",
    new: "新建",
    upgrade: "升级",
    requestFailed: "请求失败",
    networkError: "网络错误，请检查连接",
    skipToContent: "跳到主要内容",
  },
  assistant: {
    /** SettingsDialog「助手」section（ADR-117 §1）——两档确认偏好的唯一
     * UI 座位。文案直陈；守卫线是 ops 参数，footnote 是它唯一的用户面提及。 */
    title: "助手",
    subtitle: "助手在动手前需要询问的时机。其余事情它一律自己完成。",
    permissions: "权限",
    execution: {
      label: "执行操作",
      desc: "你要求制作之后，是否再等你确认一次才开工。",
    },
    spending: {
      label: "消耗积分",
      desc: "付费方案开工前，是否需要一次带价确认。",
    },
    mode: { auto: "自动", ask: "询问" },
    footnote:
      "估价始终随方案显示。超过费用守卫线的方案任何设置下都会先确认；无法提前估价只在执行或费用设为“询问”时确认，自动档不重复询问。",
    updateFailed: "设置保存失败，请重试",
  },
  general: {
    /** SettingsDialog「通用」section（ADR-123）——显示类偏好。 */
    title: "通用",
    subtitle: "工作区的布局方式。",
    workspaceLayout: {
      label: "工作区布局",
      desc: "自动 = 宽屏时画布与对话并排，窄屏时纯对话；纯对话 = 任何屏幕都以对话为工作区，产物在消息流里交付。",
      auto: "自动",
      chat: "纯对话",
    },
    updateFailed: "设置保存失败，请重试",
  },
  credits: {
    range: "约 {{low}}–{{high}} 积分",
    /** 档案面板对账尺的实扣侧（2026-09-06）——产物所属 step 的计量实扣，
     * 与 credits.range 的估价侧并排呈现。 */
    spent: "{{count}} 积分",
    insufficient: "积分不够了——当前余额 {{balance}}，这次生成约需 {{required}}。",
    negativeNote: "上次实际花费超出预估，差额已记账，充值后继续。",
    // 项目页左下角积分 pill 与其弹窗（BILLING §7 读面，2026-09-06）。
    balance: "余额",
    held: "预占中",
    /** pill hero meta 行的预占内联提及（"积分 · 12 预占中"）。 */
    heldInline: "{{count}} 预占中",
    recent: "最近记录",
    topups: "充值记录",
    spending: "消费记录",
    page: "{{page}} / {{pages}}",
    /** SettingsDialog「积分」section（BILLING §7 展示主轴）——余额与台账
     * 的全貌座位，与 pill 同两个端点。 */
    title: "积分",
    subtitle: "余额、充值与消耗记录。",
    available: "可用积分",
    amount: "充值金额",
    buyTitle: "购买积分",
    packageCredits: "{{count}} 积分",
    buy: "购买积分",
    pay: "支付",
    buying: "正在打开…",
    conversion: "{{unit}} = {{credits}} 积分",
    rateInfo: "积分换算与金额限制",
    amountRange: "单次充值 {{min}}–{{max}}。",
    packagesLoadFailed: "充值选项加载失败。",
    retry: "重试",
    paymentSuccess: "支付成功",
    topupSuccess: "{{count}} 积分已到账，点击完成查看充值记录。",
    checkAgain: "重新查询",
    return: {
      confirming: "正在确认付款…",
      pending: "付款仍在确认中，请稍后重新查询。",
      cancelled: "已取消付款，积分未增加。",
      failed: "付款未完成，积分未增加。",
    },
    viewAll: "查看全部记录",
    tx: {
      empty: "暂无变动",
      type: "类型",
      orderId: "订单号",
      paidAt: "充值时间",
      provider: "支付渠道",
      reference: "消费编号",
      creation: "制作",
      outputs: "产物类型",
      spentAt: "消费时间",
      project: "项目",
      amount: "消耗积分",
      paymentAmount: "支付金额",
      receivedCredits: "到账积分",
      status: "状态",
      success: "成功",
      credited: "已入账",
      topupEmpty: "暂无充值记录",
      spendEmpty: "暂无消费记录",
      /** 语义账本塌缩（ADR-057 K4）：用户面只显三族——花费 / 赠送 / 充值；
       * 账本的 hold / capture / release 机器词服务端折叠，永不上 UI。 */
      /** 花费行标题的最后兜底——仅在 run 既无 LLM 命名也无产物类型时
       * 出现（回退链在 tx-row.tsx 一处合成）。 */
      spent: "花费",
    },
  },
  nav: {
    home: "首页",
    personas: "人设",
    myProjects: "我的项目",
  },
  home: {
    examples: {
      overlay: { label: "叠加产品图", prompt: "把附件里的产品图放在视频第 2 到 4 秒，保留字幕和原声，播放这一段。" },
      framing: { label: "调整构图", prompt: "调整这段的构图，让讲者和字幕都清楚可见，然后播放改动的部分。" },
      trim: { label: "剪短片头", prompt: "剪掉开头的停顿，播放新的片头。" },
    },
    newChat: "新对话",
    // Studio hero：composer 上方的一行问句——下方轮换 placeholder 用三条
    // 示例 prompt 作答。
    heroQuestion: "今天做点什么？",
    // Composer placeholder：三条第一人称示例 prompt 轮换（Lovart 式），
    // 无前缀——每条都是用户口吻的完整请求，即上方 hero 问句的答句。
    // 每条保持简短，钉底条里不超一行。
    placeholderPrompts: [
      "把产品图片叠在这个镜头上",
      "剪掉片头的停顿",
      "把标题往左移，再播放这一段",
    ],
    selectPersona: "人设",
    noPromptError: "先说说想做什么",
    personaCreateFailed: "创建人设失败",
  },
  landing: {

  meta: {
    title: "Rookie Cut — 你的 AI 视频剪辑师",
    description: "把素材和想法交给 Rookie Cut AI 视频剪辑师。看过第一版，在同一段对话里指出想改的画面，继续打磨这支片子。",
  },
  "heroEyebrow": "你的 AI 视频 Agent",
  "showcase": {
    "label": "视频制作演示",
    "types": "视频类型",
    "attach": "添加素材",
    "send": "开始对话",
    "preview": "视频预览",
    "start": "你想做什么视频？",
    "play": "播放演示",
    "pause": "暂停演示",
    "replies": {
      "product-promo": "开头是滴管使用特写，下面加了简洁的产品标题。\n想换标题或调节奏，接着说就行。",
      "talking-head": "栏目标签放在顶部，本期标题从人物下方滑入。\n想调整标题出现的时间，接着说就行。",
      "text-animation": "文案没有改，已按语义安排文字节拍和重点动效。\n指定某一句，就能继续换动画、调速度或改配色。",
      "knowledge-explainer": "月球实拍旁放了简短解释，说明我们从地球上看到了什么。\n想多讲一点或调整排版，接着说就行。"
    },
    "disclosure": "素材剪辑示例 · 对话示意",
    "disclosureShort": "交互示意",
    "requests": {
      "product-promo": "给这款精华做个短宣传片，开头先展示滴管怎么用。",
      "talking-head": "给这段播客片段加上栏目标签和入场标题。",
      "text-animation": "在霓虹背景上做一段「Light in motion」的文字动画，文案不要改。",
      "knowledge-explainer": "用月球实拍和简短的屏幕文字，讲清楚月相为什么会变化。"
    },
    "steps": {
      "product-promo": {
        "understand": {
          "active": "正在查找滴管特写…",
          "done": "已查找滴管特写。"
        },
        "storyboard": {
          "active": "正在把特写放在开头…",
          "done": "已把特写放在开头。"
        },
        "produce": {
          "active": "正在加入产品标题…",
          "done": "已加入产品标题。"
        }
      },
      "talking-head": {
        "understand": {
          "active": "正在查看口播画面…",
          "done": "已查看口播画面。"
        },
        "storyboard": {
          "active": "正在安排标题出现的时机…",
          "done": "已安排标题出现的时机。"
        },
        "produce": {
          "active": "正在加入标签与标题…",
          "done": "已加入标签与标题。"
        }
      },
      "text-animation": {
        "understand": {
          "active": "正在拆分文案节拍…",
          "done": "已拆分文案节拍。"
        },
        "storyboard": {
          "active": "正在设计文字动效…",
          "done": "已设计文字动效。"
        },
        "produce": {
          "active": "正在合成文字视频…",
          "done": "已合成文字视频。"
        }
      },
      "knowledge-explainer": {
        "understand": {
          "active": "正在梳理讲解结构…",
          "done": "已梳理讲解结构。"
        },
        "storyboard": {
          "active": "正在匹配月球画面和解说文字…",
          "done": "已匹配月球画面和解说文字。"
        },
        "produce": {
          "active": "正在合成讲解视频…",
          "done": "已合成讲解视频。"
        }
      }
    }
  },
  "story": {
    "demoLabel": "剪辑对话示例",
    "idea": {
      "title": "想让观众看到什么？"
    },
    "deliveryTitle": "看看第一版",
    "refineTitle": "这一版，哪里再改改？",
    "request": "用这些素材剪一支 AgentVeil 上线短片，让大家看到在哪里审批高风险操作。",
    "attachments": {
      "label": "示例附件",
      "image": "product-image.png",
      "document": "product-brief.pdf"
    },
    "storyboardSummary": "我会把审批界面剪进去，让观众看到做决定的那一步。",
    "rendering": "正在剪辑演示片段…",
    "delivery": "这是示例里的第一版，留意画面里的审批按钮。",
    "posterAlt": "第一版成片的预览画面",
    "feedback": "审批按钮那里多停两秒，我想看清上面的字。",
    "revisionOpening": "好，我就在这一版里把这个镜头延长两秒，其他镜头照原来的节奏走。",
    "followup": "接着说说你的想法…",
    "scroll": "对话示例 · 继续滚动"
  },
  "skills": {
    "label": "创作方向",
    "titleFirst": "从产品特写，",
    "titleSecond": "到用文字讲故事。",
    "create": "使用「{{name}}」开始创作",
  },
  "faqSection": {
    "title": "你可能还想知道",
    "experience": {
      "question": "怎么开始剪一支片子？",
      "answer": "把素材发到对话里，说说想剪给谁看。比如「这支新品短片，开头先放产品特写」。看完第一版，接着在这里提修改意见。"
    },
    "material": {
      "question": "手头只有一个想法，可以开始吗？",
      "answer": "可以先聊你想表达什么，Rookie Cut 会告诉你还缺哪些素材。有现成的文稿、图片或视频，可以直接发到对话里。做产品介绍时，也可以贴上网站链接。"
    },
    "revision": {
      "question": "成片里只有一处不满意，可以单独改吗？",
      "answer": "可以在原来的对话里指出具体时间或画面，再说你想怎么改。比如「把第 5 秒的标题换短一点」或「把产品特写放到开头」。"
    },
    "pricing": {
      "question": "什么时候会消耗积分？",
      "answer": "聊想法、讨论修改都免费。生成视频或需要重新制作的修改会消耗积分，制作前可以查看费用预估。内测期间按需充值，无需订阅。"
    },
    "download": {
      "question": "做好后，怎么下载成片？",
      "answer": "在对话里打开交付的视频，先预览，再点击下载，保存为 MP4。"
    }
  },
  "footerItems": {
    "pricing": "定价",
    "changelog": "更新日志",
    "terms": "使用条款",
    "privacy": "隐私政策"
  }
,
    nav: {
      features: "使用方式",
      pricing: "定价",
      faq: "常见问题",
      earlyAccess: "内测",
    },
    signIn: "登录",
    openStudio: "开始对话",
    headerCta: "开始对话",
    heroCta: "立即制作",
    entry: {
      navigation: "主导航",
      community: "加入社群",
    },
    heroTitle1: "新手也能做出好视频",
    heroTitle2: "",
    heroSubtitle:
      "通过对话，轻松制作融合动态图形、\n丰富动画与精细剪辑的视频。",
    earlyAccess: {
      title: "你手上有什么想剪的？",
      description: "一段素材、一份想法，或是一支想再改改的片子，都可以发来。",
      credits: "注册无需绑卡。",
      estimate: "制作前显示预估积分消耗。",
      note: "内测期间，我们仍在完善制作稳定性与细节检查。",
    },
    gallery: {
      heading: "还没想好做什么？看看这些。",
      intro: "看看不同的视频方向，从接近你想法的那个开始。",
      create: "用它开始创作",
      items: {
        "product-promo": {
          title: "产品宣传",
          description: "把网站、实拍、图片和文字组合成一支产品视频。",
          prompt: "给我的产品做个短视频，重点展示它怎么用。",
        },
        "talking-head": {
          title: "口播动效",
          description: "保留真人原片和原声，加入标题、字幕与动态效果。",
          prompt: "给这段口播加上字幕和重点标题，保留我的原声。",
        },
        "text-animation": {
          title: "文字动画",
          description: "把你的文稿变成文字、图形与声音共同推进的动画。",
          prompt: "把这段话做成有表现力的文字动画。",
        },
        "knowledge-explainer": {
          title: "知识讲解",
          description: "把你掌握的知识变成带旁白的可视化讲解。",
          prompt: "用动画讲清楚这个概念，让没有基础的人也能看懂。",
        },
      },
    },
    footer: {
      tagline: "你说，我来剪。",
      autoTheme: "自动",
      columns: {
        company: "公司",
        social: "社交媒体",
        product: "产品",
        legal: "法律条款",
      },
      resources: {
        examples: "视频案例",
        app: "前往应用",
        support: "联系支持",
      },
      channels: {
        wechat: "微信群",
      },
      wechat: {
        title: "加入微信群",
        description: "使用微信扫码，加入产品交流与内测反馈群。",
        qrAlt: "Rookie Cut 微信群二维码",
      },
      legal: {
        terms: "服务条款",
        privacy: "隐私政策",
        refund: "退款政策",
      },
      copyright: "© {{year}} Rookie Cut。保留所有权利。",
      backToTop: "回到顶部",
    },
  },
  composer: {
    persona: "人设",
    autoGenerate: "自动",
    assets: "素材",
    models: "模型",
    // 拖拽上传浮层（2026-09-24）：文件拖入 composer 时的居中 pill，以及
    // 拖入文件全部不符合 ASSETS_ACCEPT 类型时的 toast。
    dropHint: "松开以上传文件",
    dropInvalid: "暂不支持该文件类型",
    // 诚实 Auto 面板（2026-08-30）：每行都是 pipeline 真实的分模态分配，
    // 只读——每个模态只有一个 provider 时没有可选行。
    modelsRows: {
      copy: "文案",
      voice: "配音",
      captions: "字幕",
      music: "音乐",
    },
    modelsNames: {
      copy: "MiniMax M3",
      voice: "MiniMax speech-2.6-hd",
      captions: "Whisper",
      music: "MiniMax music-2.6",
    },
    modelsDescs: {
      copy: "计划、写作与改写",
      voice: "声纹克隆与多语言配音",
      captions: "自托管 · 词级时间戳",
      music: "AI 生成曲库 · 按氛围匹配",
    },
    personaAutoDesc: "从本次素材自动建立或匹配画像",
    voiceBound: "声纹已克隆",
    voiceMissing: "未克隆声纹",
    fileKinds: { video: "视频", audio: "音频", image: "图片", doc: "文档" },
    assetsUpload: "上传文件",
    assetsFormats: "MP4 · MOV · WEBM · MP3 · WAV · M4A · PNG · JPG · WEBP · TXT · MD · PDF · DOC · DOCX · SRT · VTT",
    uploadFailed: "上传失败，请重试",
    uploadRetry: "重试",
    uploadInProgress: "文件还在上传中，请稍候",
    managePersonas: "管理人设…",
  },
  // 配方卡（RECIPES §7）—— 与 lib/recipes.ts 的卡 id 一一对应；
  // reserved 卡在此留座但不可点击发射。
  recipes: {
    soon: "即将推出",
    // 主 Tab 名称复用 skills.builtin；子 Tab 与 Home 注册表一致。无样片的
    // 视频应用保留可见空态；样片 prompt 落在 recipes.shelf.demos.<demoId>.prompt。
    shelf: {
      subs: {
        "website-product": "网站/产品宣传",
        "course-service": "课程/服务宣传",
        "opinion-talking-head": "观点口播",
        "course-lecture-teaser": "课程/讲座预告",
        "opinion-text": "观点文字片",
        "quote-announcement": "金句/公告短片",
        "concept-explainer": "概念讲解",
        "research-report": "研究/报告解读",
      },
      nextPage: "下一页",
      previousPage: "上一页",
      upgrading: "内容升级中",
      usePrompt: "开始创作",
      playSound: "播放声音",
      mute: "静音",
      emptyDemo: "该应用暂无样片。",
      // MG 货架预填空位：可见占位符，插入后即选中，粘贴一次完成替换；
      // 永不变成隐藏字段或第二个输入面。
      urlPlaceholder: "［网站链接］",
      urlRequired: "先填入你的网站链接",
      // MG 货架 demo 预填文案（D3——与 recipeFamilies.ts 的 ShelfDemo id
      // 一一对应）。prompt 即卡片的全部发射载荷（composer 预填，配方 =
      // 提示词）；{{placeholder}} 是发送前由用户替换的网站空位。
      demos: {
        "text-short-gentle-close": {
          prompt:
            "用这个 Skill 帮我把下面这句话做成文字动画：\n\n慢一点，也能走得更远。",
        },
        "text-short-genesis": {
          prompt:
            "用这个 Skill 帮我把下面这句英文做成文字动画：\n\nEvery great idea starts with a small step.",
        },
        "product-demo-zymix": {
          prompt:
            "用这个 Skill 帮我做一支产品演示视频，让观众看懂这个产品怎么用：{{placeholder}}",
        },
        // 网站来源的 demo 使用 capture 链；视频素材入口保留上传素材提示词。
        "product-demo-walkthrough": {
          prompt:
            "用这个 Skill 帮我把录屏做成操作演示，让观众看懂关键步骤。",
        },
        "product-demo-highlights": {
          prompt:
            "用这个 Skill 帮我做一支短视频，突出这个产品最值得关注的功能：{{placeholder}}",
        },
        "product-demo-captioned": {
          prompt:
            "用这个 Skill 帮我给视频加上文字说明，让内容更容易理解。",
        },
        "product-promo-agentveil-the-next-move": {
          prompt:
            "用这个 Skill 根据这个网站做一支宣传短片，让观众了解产品有什么价值：{{placeholder}}",
        },
        "product-promo-oxvalue-product-evidence": {
          prompt:
            "用这个 Skill 根据这个网站做一支宣传短片，让观众了解产品有什么价值：{{placeholder}}",
        },
        "product-promo-oxvalue-energy-arc": {
          prompt:
            "用这个 Skill 根据这个网站做一支宣传短片，让观众了解产品有什么价值：{{placeholder}}",
        },
        "text-short-clear-rhythm": {
          prompt:
            "把下面这段文案做成文字动画：\n\n我们常常以为，讲得越多，别人就懂得越多。\n于是不断补充背景、堆叠细节，生怕漏掉任何一个重点。\n可信息越密，真正想说的话，反而越容易被淹没。\n\n好的表达，从一个清楚的问题开始。\n先说你想解决什么，再用一个具体的例子，让人看见它为什么重要。\n给每个想法一点空间，也给观众一点理解的时间。\n\n把复杂的想法讲清楚，不是把内容变少，\n而是找到那条让人愿意听下去、也能够跟得上的线索。\n让好的内容，从被看见，走向被理解。",
        },
        "knowledge-explainer-clear-expression": {
          prompt:
            "用这个 Skill 帮我做一支动画，讲清楚为什么一次只讲一个重点更容易让人理解，面向没有基础的观众。",
        },
      },
    },
    "multilingual-subs": {
      title: "多语言字幕",
      promise: "为你的视频配上多语言字幕——单行或双语对照。",
      inputScenario: "适用：演讲 · 会议录像",
      promptTemplate:
        "给我的视频配上中文和法语字幕——中文要中英双语对照。",
    },
    "voice-dub": {
      title: "原声AI配音",
      promise:
        "用你的声音把同一段视频讲成另一种语言——不是通用合成声。",
      inputScenario: "适用：演讲 · 会议录像",
      promptTemplate:
        "把我的视频配成中文、法语和西班牙语——用我自己的声音，不要合成播音腔。",
    },
    "social-post": {
      // 配方画廊 v2（ADR-048 §4.6）：承诺句里的环路价值句（"发哪个平台你定"）
      // 是过闸门②的那一句——通用大模型写得翻译文，但握不住你的风格 + 渠道分发。
      title: "社媒帖",
      promise:
        "讲稿或长文 → 可以直接发的帖子。你的风格来写，发哪个平台你定。",
      inputScenario: "适用：讲稿 · 论文 · 会议纪要",
      promptTemplate:
        "帮我写一条社媒帖。",
    },
    "quote-cards": {
      // 2026-08-27 v3（ADR-048 第 7 条）：叠卡就是金句卡本体——承诺句写
      // 叠卡这道菜，不再写"一句话"单卡（单句图归 chat 能力，不上卡面）。
      title: "金句卡",
      promise:
        "挑出最亮的几句话，叠成一张可以直接发的金句卡。",
      inputScenario: "适用：讲座录像 · 访谈 · 文字稿",
      promptTemplate:
        "做一张中英双语金句卡。",
    },
    carousel: {
      title: "轮播图",
      promise:
        "讲稿或课件要点，排成可以翻页的图文幻灯。",
      inputScenario: "适用：讲稿 · 课件要点",
      promptTemplate:
        "帮我做一组轮播。",
    },
    "image-video": {
      title: "图文视频",
      promise: "没有录像——照片加文字稿，变成带字幕和音乐的轮播短片。",
      inputScenario: "适用：文稿 + 照片 · 课件",
      promptTemplate:
        "把我的文稿和照片做成一条图文短片——照片按段落切换，配字幕和背景音乐。",
    },
    "highlight-clips": {
      title: "高光切片",
      promise: "长视频里最好的几段剪成竖屏短片——镜头自动跟人，最值得先发的也标出来。",
      inputScenario: "适用：长演讲录像",
      promptTemplate:
        "把我这场演讲最精彩的部分剪成竖屏短片——镜头跟人，带字幕。",
    },
    reframe: {
      title: "访谈分镜",
      promise: "横屏双人对话重剪竖屏——镜头跟着说话人走。",
      inputScenario: "适用：双人对谈录像",
      promptTemplate:
        "把我的双人访谈重剪成竖屏短片——镜头跟着说话的人走。",
    },
    "ai-visuals": {
      title: "虚拟视频",
      promise: "没有素材也没关系——每个画面都根据你的演讲生成。",
      inputScenario: "适用：演讲录音",
      promptTemplate: "把我的演讲变成一条短片，画面全部 AI 生成，不需要素材。",
    },
  },
  // @-提及系统（MENTIONS §4）：picker 文案与类型名。
  skills: {
    external: "外部 Skill",
    builtin: {
      // 仅保留当前可调用的内部视频 Skill。
      "promo-video": {
        name: "宣传视频制作",
        shortName: "宣传视频",
        description: "用你的文案、网站、图片、真实视频、品牌和声音制作有依据的宣传片。",
      },
      "talking-head-video": {
        name: "口播动效视频制作",
        shortName: "口播动效",
        description: "把真实录像制作成带时间字幕的竖屏口播视频。",
      },
      "text-animation": {
        name: "文字动画视频制作",
        shortName: "文字动画",
        description: "把你的原文制作成可继续编辑的原生文字动画。",
      },
      "knowledge-explainer": {
        name: "知识讲解视频制作",
        shortName: "知识讲解",
        description: "把知识文字稿做成带对齐旁白、词锚字幕和解释性绘图的讲解视频。",
      },
    },
  },
  videoPresets: {
    "caption-phrases": { name: "字幕分句" },
    "text-reveal": { name: "文字显现" },
    "text-impact": { name: "词语强调" },
    typewriter: { name: "打字机" },
    "keyword-fill": { name: "关键词高亮" },
    "word-cycle": { name: "词语轮换" },
    "claim-layout": { name: "观点排版" },
    "highlight-sweep": { name: "高亮扫入" },
    "path-underline": { name: "路径下划线" },
    callout: { name: "标注指引" },
    "flow-steps": { name: "流程步骤" },
    "comparison-columns": { name: "双栏对比" },
    "card-stack": { name: "卡片堆叠" },
    "list-reveal": { name: "列表展开" },
    "notification-stack": { name: "通知堆叠" },
    "title-lockup": { name: "标题组合" },
  },
  mentions: {
    pickerEmpty: "没有匹配项",
    remove: "移除提及",
    regionChip: "{{time}} · {{width}}×{{height}}px",
    regionText: "[框选区域：x={{x}}，y={{y}}，宽={{width}}px，高={{height}}px；源画面={{sourceWidth}}×{{sourceHeight}}px；媒体时间={{time}}]",
    types: {
      asset: "素材",
      output: "产物",
      workflow_step: "步骤",
    },
    fileType: {
      video: "视频",
      audio: "音频",
      image: "图片",
      document: "文档",
    },
  },
  projects: {
    title: "项目",
    search: "搜索",
    searchPlaceholder: "搜索项目…",
    sort: {
      label: "排序",
      byField: "排序方式",
      byUpdated: "最近修改",
      byCreated: "创建时间",
      order: "顺序",
      desc: "最新在前",
      asc: "最早在前",
    },
    new: "新建项目",
    dialogTitle: "新建项目",
    dialogDesc: "选择人设并输入项目信息，开始把你现有的素材变成可复用的内容。",
    labelTitle: "标题",
    titlePlaceholder: "例如：AI 安全治理框架 — 欧盟合规视角",
    labelEvent: "活动名称（可选）",
    eventPlaceholder: "例如：2026 欧洲 AI 治理峰会",
    labelPersona: "人设",
    personaPlaceholder: "选择人设",
    labelLanguage: "源语言",
    langZh: "中文",
    langEn: "英文",
    emptyTitle: "还没有项目",
    emptyDesc: "创建第一个项目，把素材变成社交帖子、金句卡、长文章等内容。",
    noSearchResults: "没有匹配的项目。",
    noEvent: "未设置活动",
    deleteConfirm: "删除此项目？",
    status: {
      uploading: "上传中…",
      processing: "生成中…",
    },
    menuMore: "更多操作",
    rename: "重命名",
    renameTitle: "重命名项目",
    renamePlaceholder: "项目名称",
    deleteDesc: "「{{title}}」及其所有切片、帖子和聊天记录将被永久删除。",
    selection: {
      count: "已选 {{count}} 项",
      delete: "删除",
      clear: "取消选择",
      toggle: "选择项目",
      deleteConfirm: "删除 {{count}} 个项目？",
      deleteDesc: "所选项目及其所有切片、帖子和聊天记录将被永久删除。",
    },
  },
  projectMenu: {
    open: "项目菜单",
    backToProjects: "返回项目列表",
    backShort: "项目",
  },
  projectHeader: {
    chat: "对话",
    canvas: "画布",
  },
  personas: {
    title: "人设",
    subtitle: "管理人设与各自的风格画像",
    new: "创建人设",
    dialogTitle: "创建人设",
    dialogDesc: "添加一个人设，后续上传材料生成风格画像。",
    labelName: "名称",
    labelTitle: "头衔",
    emptyTitle: "还没有人设",
    emptyDesc: "创建第一个人设，上传过往材料建立风格画像。",
    noTitle: "未设置头衔",
    language: "语言: {{lang}}",
  },
  personaDetail: {
    tabPersona: "风格画像",
    tabMaterials: "素材 ({{count}})",
    tabSkin: "皮肤",
    personaTitle: "风格画像",
    personaDesc: "人设的风格画像，用于指导 AI 生成内容",
    generate: "从素材生成",
    generating: "生成中...",
    saveChanges: "保存更改",
    tone: "情绪基调",
    sentenceStyle: "句式风格",
    addItem: "添加",
    emptyList: "暂无",
    removeItem: "移除",
    editItem: "编辑",
    overview: {
      voice: "声音",
      skin: "皮肤",
      skinDefault: "默认",
      skinCustom: "自定义",
      materials: "素材",
      calibrated: "最近提炼",
      never: "尚未提炼",
    },
    fields: {
      core_values: "核心价值观",
      favorite_metaphors: "偏爱隐喻",
      typical_hooks: "典型开场",
      avoid_words: "避免词汇",
    },
    tones: {
      rational: "理性",
      passionate: "激情",
      gentle: "温和",
      sharp: "犀利",
      humorous: "幽默",
    },
    emptyPersona: "还没有风格画像，先在素材页上传材料，然后点击生成。",
    pastMaterials: "过往素材",
    pastMaterialsDesc: "上传过往的发言、文章等材料，帮助 AI 学习你的风格",
    noMaterials: "尚未上传素材。",
    charsExtracted: "已提取 {{count}} 字符",
    noText: "无文本",
    uploadedAt: "上传于 {{date}}",
    notFound: "人设不存在",
    msgUpdated: "人设已更新",
    msgGenerated: "风格画像生成成功",
    msgUploaded: "素材已上传",
    msgDeleted: "素材已删除",
    deleteConfirm: "删除此素材？",
    deleteDesc: "「{{title}}」将被永久删除。",
    rename: "重命名",
    renameTitle: "重命名素材",
    renamePlaceholder: "素材名称",
    uploading: "上传中...",
    contentStrategyTitle: "内容策略",
    contentStrategyDesc: "这个人设的语气与受众",
    audience: "目标受众",
    audiencePlaceholder: "例如：学术研究者",
    guidelines: "内容准则",
    guidelinesPlaceholder: "例如：避免术语，段落简短",
    cta: "默认行动号召",
    ctaPlaceholder: "例如：阅读完整论文 →",
    voice: {
      title: "声音",
      desc: "绑定到这个人设的声音样本。",
      auto: "自动",
      autoDesc: "使用每个项目自己的声音",
      mine: "我的声音样本",
      noSample: "还没有上传样本",
      sampleMissing: "样本已不可用",
      stock: "系统音色",
      upload: "上传样本",
      replace: "更换",
      msgUpdated: "声音已更新",
    },
    skin: {
      title: "皮肤",
      desc: "这个人设视频的默认外观：字幕、标题、片头片尾、配乐。",
      save: "保存皮肤",
      reset: "恢复默认",
      msgSaved: "皮肤已保存",
      msgReset: "已恢复默认皮肤",
      groups: {
        caption: "字幕",
        title: "标题",
        intro: "片头",
        outro: "片尾",
        music: "配乐",
      },
      caption: {
        font: "字体",
        size: "字号",
        color: "颜色",
        customColor: "自定义颜色",
        style: "样式",
      },
      titleCard: {
        size: "字号",
        hint: "标题文案按每条视频生成；在预览里拖动标题标记即可调整位置。",
      },
      introOutro: {
        type: "类型",
        kinds: {
          text: "文字",
          image: "图片",
          video: "视频",
        },
        introText: "片头文字",
        introPlaceholder: "本视频来自…",
        outroText: "片尾文字",
        outroPlaceholder: "关注获取更多洞察",
        uploadImage: "上传图片",
        uploadVideo: "上传视频",
        duration: "持续时间（秒）",
      },
      music: {
        enable: "背景配乐",
        gain: "音量",
        library: "配乐库",
        empty: "暂无配乐",
        play: "试听",
        pause: "暂停试听",
        generate: "生成新配乐",
        generatePrompt: "如：电影感弦乐，充满希望，无人声",
        titlePlaceholder: "曲目名称（可选）",
        moods: {
          calm: "舒缓",
          uplifting: "激励",
          corporate: "商务",
          none: "无",
        },
      },
      preview: {
        demo: "示例",
        hint: "悬停标题 / 字幕文字显示标记——拖动移动，拖角调整字号。",
        musicOn: "配乐开",
        musicOff: "配乐关",
      },
    },
  },
  projectDetail: {
    back: "返回",
    status: "状态",
    persona: "人设",
    notGenerated: "未生成",
    unknown: "未知",
    sourceMaterials: "源材料",
    generate: "生成",
    outputLanguage: "语言:",
    linkedinPosts: "社交帖",
    quoteCards: "金句卡",
    downloadCard: "下载图片",
    carousel: "轮播长图",
    slideLabel: "{{index}}/{{total}}",
    summary: "摘要",
    blog: "博客文章",
    jobRunning: "正在生成",
    jobFailed: "生成失败",
    renderFailed: "渲染失败",
    generating: "生成中...",
    uploadTranscript: "上传素材",
    uploading: "上传中...",
    uploadHint: "上传演讲稿、PPT、音频、视频或图片——成片来自音/视频，或图片音频图（audiogram）",
    noMaterials: "还没有上传演讲稿。",
    generatedClips: "已生成资产 ({{count}})",
    titleOptions: "标题选项",
    titlePerLine: "每行一个标题",
    bgm: "配乐",
    score: "评分",
    scriptShots: "内容分段",
    preview: "预览",
    openEditor: "打开编辑器",
    visual: "视觉元素: {{value}}",
    edit: "编辑",
    save: "保存",
    cancel: "取消",
    editClip: "编辑片段",
    editDerivative: "编辑内容",
    exportAll: "导出全部",
    exporting: "导出中...",
    exportFailed: "导出失败",
    exportSuccess: "导出成功",
    noContentToExport: "没有可导出的内容",
    charsExtracted: "已提取 {{count}} 字符",
    noText: "未提取到文本",
    processing: "处理中...",
    processingFailed: "处理失败",
    retry: "重试",
    uploadedAt: "{{type}} · 上传于 {{date}}",
    notFound: "项目不存在",
    msgUploaded: "演讲稿已上传",
    msgDeleted: "演讲稿已删除",
    msgGenerated: "已生成 {{count}} 项资产",
    msgSaved: "已保存",
    deleteConfirm: "删除此资产？",
  },
  clipEditor: {
    back: "返回",
    title: "片段编辑",
    save: "保存",
    conflictReload: "该片段已在别处被修改——未保存的修改已丢弃，已加载最新版本。",
    export: "导出视频",
    rendering: "渲染中...",
    renderFailed: "渲染失败",
    rendered: "成片",
    noRenderSpec: "该片段没有可渲染的视频（纯文本/无源视频项目）",
    transcript: "字幕文稿",
    transcriptHint: "点词修正 · 删行剪掉该段",
    noCaptions: "暂无字幕",
    deleteLine: "删除这一行",
    aspect: "画面比例",
    captionStyle: "字幕样式",
    captionLanguage: "字幕语言",
    translating: "翻译中...",
    dubLanguage: "语音配音",
    dubbing: "配音中...",
    dubOff: "关闭",
    musicToggle: "配乐",
    musicTrack: "曲目",
    musicTrackNone: "无",
    musicGain: "音量",
    titleToggle: "标题开关",
    titlePlaceholder: "标题 / Hook 文案",
    trim: "裁剪",
    reframePan: "水平构图",
    reframeZoom: "缩放",
    staleTrack: {
      dub: "配音",
    },
    staleTracks: "{{tracks}}已与本次剪辑不同步——可在方便时重新生成。",
  },
  languages: {
    zh: "中文",
    en: "English",
    fr: "法语",
    de: "德语",
    es: "西班牙语",
    it: "意大利语",
  },
  // 字幕样式标签 —— 每个 CAPTION_PRESETS 成员一条
  // （@repurposer/clip captions.ts）；两处样式选择器从 catalog 派生选项、
  // 从这里取标签。
  captionPresets: {
    "clean-bottom": "简洁底部",
    "karaoke-highlight": "逐词高亮",
    "fade-in": "淡入",
    "pop-in": "弹出",
    "slide-up": "上滑",
    stacking: "堆叠",
  },
  results: {
    title: "结果",
    prompt: "原始提示",
    dock: {
      focus: "当前焦点：{{name}}",
      // hidden 态（2026-09-02 形态机）：用户手势把整个 dock 收成右下角
      // logo 点；agent 发言 / 提问 / 焦点会唤回。
      hide: "收起聊天",
      show: "展开聊天",
      // 右侧 docked 面板的细长 header 标题（2026-09-06 两形态机）。
      panelTitle: "对话",
      // 面板几何切换（2026-09-06，FLORA「Dock panel」对齐）：浮动 = 雾面卡
      // 浮于 full-bleed 画布上（默认）；停靠 = 靠右齐边全高，仍是雾面。
      dockPanel: "停靠面板",
      floatPanel: "浮动面板",
      // dock 常驻免责行（ADR-051）——指向真实风险点：即将发布的内容，而非
      // 事实问答。基础形态钉在输入区上方，提问形态随输入行隐藏。
      honesty: "Rookie Cut 可能出错，发布前请检查。",
    },
    // 画布产物卡（ADR-041 D5）：常驻操作带按钮文案。（无「预览」——视频内联自
    // 播，hover 放大开大屏；2026-08-16 走查拍板。）
    canvas: {
      download: "下载",
      publish: "发布",
      // ⋯ 菜单（节点自己的事，2026-08-17 走查拍板）：打开大屏 / 在对话里指认；
      // 素材另有重新处理。
      open: "打开",
      focusNode: "在对话中指认",
      reprocess: "重新处理",
      more: "更多操作",
      // 图画布的文档节点（ADR-057）：转写稿 / 调研简报是该型的命名实例；
      // 通用文档用普通标签。（计划文档已 de-stamp —— v4.2 C1-b。）
      transcript: "转写稿",
      researchBrief: "调研简报",
      // 两站拆分的文档站 (ADR-072, spec.role 派生——文档站不携 builder 摘要,
      // cue artifact 即内容).
      translationDoc: "译文稿",
      dubScriptDoc: "配音稿",
      document: "文档",
      // 词表 v3 回退标签（ADR-076，C1 休眠键）：节点没有 builder/LLM 命名时
      // 读 TYPE 名——通用媒介词，永不是业务名（业务身份 = spec.summary /
      // spec.tool 的座位）。
      nodeType: {
        text: "文本",
        table: "表格",
        image: "图片",
        video: "视频",
        audio: "音频",
      },
      // 状态原地表达（ADR-057 §5——状态在卡内说话，caption 右槽恒空）：未运行
      // 节点虚线空区读自己的估价；排队 / 跳过 / 失败 / 可重跑是安静标签。
      draftBody: "运行后生成",
      estimateSingle: "约 {{count}} 积分",
      estimateRange: "约 {{low}}–{{high}} 积分",
      // 估价诚实面 (2026-09-10): 折叠中存在未估价节点（transform 链在产物
      // 存在时才能报价）——永不许诺「约 0」。
      estimateOpen: "约 {{count}}+ 积分",
      estimateRangeOpen: "约 {{low}}–{{high}}+ 积分",
      estimateAtRun: "估价随运行",
      queued: "排队中",
      skipped: "已跳过",
      runFailed: "运行失败",
      stale: "可重跑",
      // 卡面程序区（ADR-057 §5）：generator/agent 节点在此读自己的 prompt
      // （processor 节点读参数事实 chips）。
      promptLabel: "提示词",
      // K4 直改：起草中 meta 标签承担状态；发送后定价确认卡锚在节点旁
      // （受影响子图 = 本节点 ∪ 图边下游，价格 = 各节点估价 fold；
      // 余额 = 软对照，422 仍是事实源）。
      promptEditing: "提示词——修改中",
      confirmBlastSingle: "重跑此节点",
      confirmBlast: "重跑 {{count}} 个节点",
      confirmStart: "确认开始",
      // 画布导航控件（explore 面，2026-08-19——项目页右上换血：app chrome 出，画布控件进；
      // 2026-09-28 缩放菜单形态——pill 开菜单：步进/fit/定档，⌘+/⌘-/⌘0 悬停画布时生效）。
      zoomMenu: "缩放",
      zoomIn: "放大",
      zoomOut: "缩小",
      zoomFit: "适应窗口",
      zoomToPct: "缩放至 {{pct}}%",
      // 素材卡转写区（ADR-113——转写 = 素材的内容层，永不成节点）：空稿诚实面
      // （ASR 零词）、截断诚实标记、编辑入口（只写覆盖层，源层永不动，C4）。
      transcriptEmpty: "这段素材没有读到可转写的内容",
      transcriptTruncated: "时间轴过长，只显示了前面部分",
      editTranscript: "编辑转写稿",
      // 成片卡轨道栈（ADR-113 §4）：只读检视轨（视频片段块 / 字幕句块，都在
      // 产出轴上）+ 修饰轨存在条。片段标签的时间区间由服务端预格式化
      // （前端永不自建时间格式化）。
      videoTrack: "视频轨",
      textTrack: "文字轨",
      trackSegment: "片段 {{n}} · 源 {{src}}",
      // L1 hover chip 两行（ADR-115 信息秩三分）：块名 + 产出/源两轴预格式化区间。
      trackSegmentTitle: "片段 {{n}}",
      trackSegmentOut: "产出 {{out}} · 源 {{src}}",
      modifierMusic: "音乐",
      modifierDub: "配音",
      // 产物档案面板（2026-09-06，FLORA 节点详情对齐）：点产物节点召唤，
      // 挂在缩放钮下方——只摆出生证明，纯只读事实（修订只经 chat；
      // FLORA 的内联参数编辑有意不搬）。
      inspector: {
        stepLabel: "工序",
        estimateLabel: "估价",
        spentLabel: "实扣",
        durationLabel: "耗时",
        createdLabel: "生成时间",
        languageLabel: "语言",
        sourceLabel: "来源素材",
        sourceFull: "完整素材",
        rangeLabel: "截取区间",
        specLabel: "任务参数",
        modelsLabel: "模型",
        close: "关闭详情",
      },
      // render 失败原地投影在产物卡上（永不是独立节点）；重试通道 = chat dock（D8）。
      // 渲染中由 BrandLoader 独自表达，不落状态行。
      renderFailed: "渲染失败——在下方说一句重试。",
      // 选区引用（2026-09-11——段落级指认）：产物卡上划选文本浮出的钉选钮——
      // 钉选进入 dock 成为带引文的 @output chip，agent 修订的正是这一段。
      quotePassage: "引用这段",
      // Transcript 卡内就地编辑（Workspace 合同 v4.2 C4）：仅编辑态可见的
      // 复位钮——清除用户的改写覆盖层，回到源文字层。
      resetToSource: "恢复原文",
      // 悬停媒体控件：展开（左上）打开 lightbox；声音（右上）切换内联视频的静音。
      expand: "展开",
      mute: "静音",
      unmute: "取消静音",
      // 卡面程序区发送钮（ADR-057 K4 直改——经定价确认卡确认，永不开新通道）。
      reviseSend: "发送修订",
      // 版本分页（ADR-051 F2——变体分页）：卡底动作带的 fork 族翻页——独立的
      // pill，永不与条目切换器合并（variants = 条目切换 ≠ 版本切换）。
      versionOf: "{{current}} / {{total}}",
      versionPrev: "上一版",
      versionNext: "下一版",
    },
    // 媒体 lightbox 的信息栏（媒体左侧）。
    lightbox: {
      prompt: "提示词",
    },
    stepper: {
      transcribing: "正在转写你的媒体…",
      queued: "正在排队，马上开始…",
      analyze: "正在分析上传的素材…",
      plan: "正在规划内容结构…",
      prepare: "正在准备生成…",
      selecting_segments: "正在挑选高光片段…",
      building_specs: "正在组装片段…",
      writing_copy: "正在撰写文案…",
      researching: "正在调研…",
      generating_image: "正在生成金句卡图片…",
      ready_to_render: "即将开始渲染…",
      removing_fillers: "正在去除口头禅…",
      reframing_clips: "正在智能分镜…",
      adding_music: "正在为片段配乐…",
      translating_captions: "正在翻译字幕…",
      dubbing: "正在为你的声音配音…",
    },
    clipNotRendered: "点击渲染此片段。",
    topPick: "首发推荐",
    qualityNeedsReview: "待复核",
    scoreLabel: "推荐度",
    scoreReason: "推荐理由",
    noQuote: "暂无名言文本。",
    noSlides: "暂无轮播图内容。",
    generating: "正在生成资产...",
    generatingTitle: "正在生成资产",
    polling: "正在检查生成状态...",
    clipDetail: {
      publishTab: "发布",
      socialCaptionTab: "社交配文",
      topicTab: "选题",
      transcriptTab: "字幕稿",
      title: "标题",
      caption: "配文",
      hashtags: "话题标签",
      copyTitle: "复制标题",
      copyCaption: "复制配文",
      copyHashtags: "复制话题标签",
      download: "下载",
      editClip: "编辑片段",
      generateCover: "生成封面",
      close: "关闭",
      noTranscript: "暂无字幕稿。",
    },
  },
  chat: {
    scrollToStart: "滚动到开头",
    scrollToEnd: "滚动到末尾",
    assistantLabel: "Rookie Cut",
    userLabel: "你",
    thinking: "思考中...",
    thinkingPhases: {
      capturing: "正在读网页…",
      storyboarding: "正在设计分镜…",
      storyboard_revision: "正在调整分镜…",
    },
    /** 收官言语生成窗口的 now-line（终态 run 的收官言语是一次 LLM 调用，
     * 由触发轮询拾取——有 LLM 调用就必定有 now-line）。文案只说在整理
     * 制作结果，永不暗示仍在渲染或在检查视频画面。 */
    closingReview: "正在整理制作结果…",
    /** 分镜起草落定行（legacy 活动回放）：跨度的落定行（born-settled
     * activity）——活动日志寄存器（动宾+事实，无进行态），与素材读取族同
     * 三寄存器律。 */
    storyboard: {
      draftingDone: "起草完分镜",
    },
    /** now-line 的素材阅读行（2026-09-24 用户拍板——thinking 就是 activity
     * 行的空态）：素材处理中 → reading（文件名插值）。*Done / *Failed 是
     * 持久化的完成态行（统一 activity 行——pipeline 完成时写入或复用
     * 同一消息行，回放映过去时）；Progress 带批次计数「N/M」。
     * 动词分叉（2026-09-27 批「动词」）：动词随资产类型——video=看 /
     * audio=听 / 文本及其他=读；多文件批次落中性词「处理」。typed key
     * 缺席时回落基 key（前后端两个合成点同一分叉律：ChatDock now-line
     * 读 asset.type，回放读节拍入库的 intent.asset_type）。
     * 工序分叉（ADR-095 §2）：单个在处理资产带已知 processing_stage 时
     * 说工序真相——asr → transcribing（转写）、speaker_map/prosody →
     * understandingAsset（理解，与 run stepper 共用同一工序词表）；
     * 未知/缺席 stage 回落动词行。寄存器律（三寄存器）：live 行是瞬态面
     * （进行态合法）；入库行是活动日志——动宾 + 事实后缀，无人称、无
     * 进行态、无省略号、无会话语气。understandingDone 为旧节拍回放保留
     * （ADR-102 已退役其生产者——历史会话的归档行照常渲染）。 */
    material: {
      reading: "正在阅读 {{name}}…",
      reading_video: "正在看 {{name}}…",
      reading_audio: "正在听 {{name}}…",
      readingMany: "正在处理 {{count}} 个文件…",
      transcribing: "正在转写 {{name}}…",
      understandingAsset: "正在理解 {{name}}…",
      readingDone: "读完 {{name}}",
      readingDone_video: "看完 {{name}}",
      readingDone_audio: "听完 {{name}}",
      readingDoneProgress: "读完 {{name}}（{{count}}/{{total}}）",
      readingDoneProgress_video: "看完 {{name}}（{{count}}/{{total}}）",
      readingDoneProgress_audio: "听完 {{name}}（{{count}}/{{total}}）",
      readingFailed: "读 {{name}} 失败",
      readingFailed_video: "看 {{name}} 失败",
      readingFailed_audio: "听 {{name}} 失败",
      understandingDone: "素材理解完成",
    },
    /** 素材读取族的落定类目形态（ADR-110 修订——归档归类目）：不带实例
     * 名——文件名是 live 期的言语，落定面只说类目。动词分叉与 reading
     * 族同形（video/audio 随行键自身后缀，web_page 随节拍的
     * asset_type）。 */
    materialCategory: {
      reading: "读完素材",
      reading_video: "看完视频",
      reading_audio: "听完音频",
      reading_webPage: "读完网页",
    },
    /** 感知族的查询碎碎念（T2b）：读工具运行期间 read 活动帧的文案
     * （Phase 3 Batch B ③ 自退役的 System Status 行迁入 Activity Stream，
     * 同注册表同 key）。key 随服务端注册表（app/chat/perception）——
     * 工具名永不上用户面。 */
    inspecting: {
      outputSpec: "正在读当前设置…",
      node: "正在读卡片的完整程序…",
      understanding: "正在查看素材内容…",
      captionStyles: "正在翻字幕样式…",
      music: "正在查曲库…",
      runStatus: "正在查看运行进度…",
      runHistory: "正在读运行历史…",
      pendingPlan: "正在读待确认的计划…",
      graph: "正在看画布…",
      segment: "正在读片段…",
      asset: "正在查看素材…",
      projectMedia: "正在列出项目素材…",
      craftSkeleton: "正在读案例的风格拆解…",
      artifact: "正在读卡片的详情…",
      webPage: "正在读网页…",
      webSearch: "正在搜网页…",
      videoVersion: "正在读已存版本…",
    },
    /** 工作会话族（迭代二⑥，N-57）：发现链的用户安全节拍——searching 骑
     * 读帧（进行态 + 完成态镜像，与 inspecting→inspectingDone 同律的
     * 本族形态）；三个里程碑在写门成功处一发 completed 帧，唯一插值 =
     * 产物计数（user-safe 纯计数——永不带参数/摘录/推理）。 */
    explore: {
      searching: "正在检索转写内容…",
      searchingDone: "已检索转写内容",
      candidatesReady: "找到 {{count}} 段候选",
      selectsReady: "选定 {{count}} 段",
      plansReady: "整理好 {{count}} 个方案",
    },
    /** Candidate Surface（Workspace 合同 v4.2 C8-c，2026-09-26 封板）：chat
     * 候选卡的展开开关——默认 3 个推荐，全量按需展开（推荐样本，不是只能
     * 选 3 个）。 */
    candidates: {
      more: "另外还有 {{count}} 个",
      less: "收起",
      selected: "已选择",
    },
    sfx: {
      play: "播放音效",
      pause: "暂停音效",
      seek: "调整播放进度",
      previewUnavailable: "音频预览不可用",
    },
    preparationProgress: {
      pictureScene: "正在准备第{{name}}条分镜…",
      voiceScene: "正在录制第{{name}}条旁白…",
      visual_assets: "正在准备分镜画面…",
      imagesProcessed: "正在准备分镜画面，已处理 {{count}} 幅…",
      speech_media: "正在录制分镜旁白…",
      audio_snapshot: "正在保存旁白录音…",
      alignment_request: "正在提交旁白对齐…",
      music_synthesis: "正在生成配乐…",
    },
    audio: {
      retry: "重试播放",
      play: "播放音频",
      pause: "暂停音频",
      narration: "旁白",
      music: "背景音乐",
      loading: "正在准备音频播放…",
      unavailable: "音频尚未就绪，暂时无法播放",
    },
    /** 活动流里程碑文案（ADR-087 §3 Phase 2）：active 帧带进行态、completed
     * 帧带完成态；failed 保留诚实的进行态键，cancelled 尝试从可见时间线
     * 退役，不变成删除线历史。 */
    /** 2026-09-25 文案批 (用户拍板——「计划已起草 / 创建 workflow」那套
     * 机器状态腔退役): 说人话，说当下在干的事。draft 按工具分两副面孔
     * ——出方案 / 改已有产物（由 ChatTool.presentation 声明）。draft / run
     * 跨度只有 active 态（落定即退役——2026-09-28 draft、2026-09-29 扩到
     * run）：落定收据行退役，方案卡 / 开工言语 + RunTaskList 收据就是证据，
     * 故无 draftDone/editDone/runDone 键（下方分镜键族是唯一例外——分镜
     * 不是开工，其落定留存；storyboardEdit 两键 = 定点调整的 patch 变体，
     * 说调整永不说新设计）。repair 两键 = 言语提交协议批
     * 终态专用（重试跨度静默开启，无 active 帧）：repair 只在失败终态
     * （重试耗尽 / 回合失败）发射，repairDone 只在转向终态（护栏把回合
     * 形式引去别的工具）发射——说工作事实，永不说模型自我反思。 */
    activity: {
      draft: "正在整理方案…",
      edit: "正在修改…",
      run: "正在开工…",
      repair: "这次没能完成",
      repairDone: "换了个方式",
      storyboard: "正在设计分镜…",
      storyboardDone: "已设计分镜",
      storyboardEdit: "正在调整分镜…",
      storyboardEditDone: "已调整分镜",
      /** 视频设计族两对（ADR-145 阶段 B）：与分镜跨度同构——设计与修订各
       * 说各的话。 */
      videoDesign: "正在设计视频分镜…",
      videoDesignDone: "已设计视频分镜",
      skillRead: "正在读取 Skill 方法…",
      skillReadDone: "已读取 Skill 方法",
      skillPreview: "正在查看 Skill 预览…",
      skillPreviewDone: "已查看 Skill 预览",
      importMusic: "正在导入音乐…",
      imageUnavailable: "图片暂时无法显示",
      recordVoice: "正在生成旁白",
      recordVoiceDone: "旁白已生成",
      bindClipSource: "正在绑定素材",
      bindClipSourceDone: "已绑定素材",
      insertVisual: "正在插入图片",
      insertAudio: "正在加入音频",
      insertVisualDone: "已插入图片",
      insertAudioDone: "已加入音频",
      visualAssets: "正在准备分镜画面…",
      checkFixedImages: "正在核对已有的分镜画面…",
      readFixedImages: "正在读取已核对的分镜画面…",
      visualAssetsDone: "已查看画面素材",
      readHistory: "正在查看对话记录…",
      readHistoryDone: "已查看对话记录",
      viewWebPage: "正在查看网页…",
      viewWebPageDone: "已查看网页",
      videoMaterials: "正在准备视频素材…",
      videoMaterialsDone: "已准备视频素材",
      brandAnalyze: "正在提炼品牌档案…",
      brandAnalyzeDone: "已提炼品牌档案",
      videoCapturePlan: "正在采集计划的网页状态…",
      videoCapturePlanDone: "已采集计划的网页状态",
      videoRevise: "正在调整视频分镜…",
      inspectClips: "正在检查片段",
      inspectClipsDone: "已检查片段",
      inspectClip: "正在查看片段",
      inspectClipDone: "已查看片段",
      removeClip: "正在移除片段",
      removeClipDone: "已移除片段",
      trimClip: "正在裁剪片段",
      trimClipDone: "已裁剪片段",
      moveClip: "正在移动片段",
      moveClipDone: "已移动片段",
      translate: "正在平移画面",
      translateDone: "已平移画面",
      scale: "正在缩放画面",
      scaleDone: "已缩放画面",
      splitClip: "正在分割片段",
      splitClipDone: "已将片段分为两部分",
      deliverVideo: "正在交付成片",
      deliverVideoDone: "已交付成片",
      setKeyframe: "正在调整关键帧",
      setKeyframeDone: "已调整关键帧",
      extendStill: "正在延长片尾画面",
      extendStillDone: "已延长片尾画面",
      exportVideo: "正在导出正式 MP4",
      exportVideoDone: "正式 MP4 已导出",
      previewRange: "正在检查局部预览",
      createVideo: "正在创建初稿",
      createVideoDone: "已保存初稿",
      previewRangeDone: "已检查局部预览",
      videoReviseDone: "已调整视频分镜",
      videoReview: "正在检查成片…",
      videoReviewDone: "已检查成片",
      videoDraftScene: "正在检查第 {{count}} 幕…",
      videoDraftSceneDone: "已检查第 {{count}} 幕",
      videoDraftJoin: "正在检查第 {{count}} 幕与上一幕的衔接…",
      videoDraftJoinDone: "已检查第 {{count}} 幕与上一幕的衔接",
      videoDraftRecheck: "正在复查第 1–{{count}} 幕…",
      videoDraftRecheckDone: "已复查第 1–{{count}} 幕",
      videoSave: "正在保存可编辑版本…",
      videoSaveDone: "已保存可编辑版本",
      sfxSearch: "正在查找音效…",
      sfxSearchDone: "已找到音效",
      sfxImport: "正在导入选中的音效…",
      sfxImportDone: "已导入选中的音效",
      musicSearch: "正在查找配乐…",
      musicSearchDone: "已找到配乐",
      musicSelection: "正在选择配乐…",
      musicSelectionDone: "已选择配乐",
      mediaPermission: "已请求素材生成授权",
      musicPrepare: "正在准备电子配乐…",
      musicPrepareDone: "已准备电子配乐",
      upload: "正在上传视频…",
      uploadDone: "已上传视频",
      narrationPrepare: "正在准备旁白对齐…",
      narrationPrepareDone: "已提交旁白对齐准备",
      narrationRead: "正在读取旁白对齐…",
      narrationReadDone: "已读取旁白对齐",
      narrationAnnotate: "正在标注旁白语义…",
      narrationAnnotateDone: "已标注旁白语义",
    },
    activityReceipt: {
      sampledFrames: "采样帧",
      observed_issue: "发现的问题 · {{frame}}",
      aesthetic_suggestion: "画面建议 · {{frame}}",
      noFindings: "采样帧中没有内容发现",
      audioIssues: "音频问题",
      checkedScope: "实际检查范围",
      checked: "已检查",
      notChecked: "未检查",
      audio: {
        AUDIO_MISSING: "应有音频缺失",
        AUDIO_DECODE_FAILED: "音频未能完整解码",
        AUDIO_SILENT: "应有音频为静音",
        AUDIO_QUIET: "音频音量偏低",
        AUDIO_CLIPPED: "音频存在削波样本",
      },
      scope: {
        actual_output_decoded: "解码指定的已交付成片",
        static_frames_checked: "检查采样静帧",
        deterministic_output_checks: "运行确定性输出检查",
        sampled_frame_signals_checked: "检查采样帧信号",
        audio_signal_checked: "检查音频信号",
        motion_and_transitions_checked: "检查运动与转场",
        audio_and_av_sync_checked: "检查音频与音画同步",
      },
      revision: {
        version: "已保存第 {{version}} 版",
        settings: "画布设置 · {{fields}}",
        addedScene: "新增场景 · {{scene}}",
        removedScene: "移除场景 · {{scene}}",
        movedScene: "移动 {{scene}} · {{from}} 秒 → {{to}} 秒",
        addedClip: "新增{{kind}}片段 · {{clip}}",
        removedClip: "移除片段 · {{clip}}",
        updatedClip: "更新 {{clip}} · {{fields}}",
        transitions: "已更新转场",
        kinds: {
          text: "文字",
          image: "图片",
          web: "网页",
          video: "视频",
          audio: "音频",
          shape: "图形",
          speech: "旁白",
          generator: "Generator",
        },
        fields: {
          range: "时间窗",
          object: "内容",
          animations: "动画",
          scene_id: "场景",
          source: "来源",
          linked_group_id: "联动组",
        },
      },
      component: {
        title: "组件预览 · {{clip}}",
        posterAlt: "{{clip}} 的代表预览帧",
        previewFrame: "代表帧 · {{frame}}",
        dynamicSamples: "已在这些帧验证运动 · {{frames}}",
        fixedMedia: "固定媒体 · {{digest}}",
      },
      sfx: {
        searchTopic: "音效搜索 · {{topic}}",
        candidate: "{{ordinal}} · {{title}} · {{duration}} 秒",
        imported: "已导入 {{title}} · {{duration}} 秒",
        snapshot: "已导入音频 · {{id}}",
      },
      music: {
        searchTopic: "配乐候选 · {{topic}}",
        candidate: "{{ordinal}} · {{title}} · {{duration}} 秒",
        selected: "已选择 {{title}} · {{duration}} 秒",
      },
    },
    /** 活动行的有界展开明细（迭代三 S7，E7 诚实边界）：只有 wire 白名单
     * 字段——原始计数带标签成行（耗时内联同行，formatElapsed 是唯一措辞）。 */
    activityMeta: {
      count: "数量：{{count}}",
    },
    /** 聚合行（ADR-110 段聚合）：落定工作段折成一条安静的总量。实时
     * `worked` 从真实工作边界计到正文首显（或无正文真实终态）并冻结；
     * 回放缺少该客户端事实时只报可观察活动跨度。展开 = 类目分解
     * （foldCategories 的 ×N 行）；无墙钟事实时 `actionCount` 诚实显示操作数。 */
    recordingGroup: "正在生成旁白与配乐",
    toolGroup: "{{count}} 项操作",
    toolName: {
      inspect_clip: "查看片段",
      inspect_timeline: "检查时间线",
      generate_voice: "生成旁白",
      generate_music: "生成配乐",
      generate_image: "生成图片",
      insert_visual: "插入图片",
      insert_audio: "插入音频",
      split_clip: "分割片段",
      remove_clip: "移除片段",
      trim_clip: "裁剪片段",
      move_clip: "移动片段",
      translate: "平移画面",
      scale: "缩放画面",
      preview_range: "预览选段",
    },
    callState: {
      provider_unknown: "供应商结果未知",
      queued: "等待执行",
      running: "执行中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已停止",
      not_executed: "未执行",
      awaiting_authorization: "等待授权",
    },
    activityFold: {
      workedWithoutTime: "已工作",
      worked: "工作了 {{elapsed}}",
      failed: "这次没能完成 · {{elapsed}}",
      actionCount: "{{count}} 项操作",
    },
    /** 视频呈现随行件：活动标签与可选的真实 Generator 预览。
     * 用户可见分镜本体是 LLM 的 Markdown 创作概要。 */
    videoStoryboard: {
      video: "短片",
      programPreview: "程序画面预览",
      programPreviewError: "当前程序预览未能加载，尚未确认完整呈现。",
      pendingMedia: "这个局部预览所需的媒体尚未就绪，当前尚未开始制作。",
      previewError: "这个局部预览未能加载。",
      title: "分镜",
      unavailable: "这个分镜版本已不可用。",
      scrub: {
        trigger: "调整字号",
        target: "文字",
        fontSize: "字号",
        apply: "应用",
        applyError: "字号未能保存，已撤销本次编辑。",
        conflict: "影片已在其他位置更新，请重新打开当前版本后再应用。",
        openCurrent: "打开当前版本",
        isolatedObject: "独立文字预览，不代表完整场景中的布局、遮挡与衔接。",
      },
    },
    /** inspecting 族的完成态镜像——读活动 completed 帧的文案（键随服务端
     * 注册表，本族按前缀交换镜像）。 */
    inspectingDone: {
      outputSpec: "已读当前设置",
      node: "已读卡片的完整程序",
      understanding: "已理解素材",
      captionStyles: "已翻完字幕样式",
      music: "已查曲库",
      runStatus: "已查看运行进度",
      runHistory: "已读运行历史",
      pendingPlan: "已读待确认的计划",
      graph: "已看画布",
      segment: "已读片段",
      asset: "已查看素材",
      projectMedia: "已列出项目素材",
      craftSkeleton: "已读案例的风格拆解",
      artifact: "已读卡片的详情",
      webPage: "已读网页",
      webSearch: "已搜网页",
      videoVersion: "已读已存版本",
    },
    /** inspecting 族的失败态镜像（ADR-102 §5）——读目标不可读时读活动
     * failed 帧的文案（与 done 族互为诚实对偶，永不默谎）。 */
    inspectingFailed: {
      understanding: "素材没能读出来",
    },
    completed: "完成",
    failed: "抱歉，这次没能完成修改，请再试一次。",
    /** 死流对账的放弃行（2026-10-15）：连接被判死并放弃后，窗口内没有
     * 等到回答落库——回合仍可能在服务端完成，刷新时归档回放会补上。 */
    connectionLost: "连接中断了，回复还没有落库——过一会儿刷新页面看看。",
    /** 已落定问题的静默收口（2026-09-28——回答端点的结构化 409 码；
     * 点击与问题自身的落定竞态，不报错误 toast）。 */
    questionOutdated: "这个问题已被更新的提问取代，不用再回答了。",
    questionAnswered: "这个问题已经回答过了。",
    /** Start 断流恢复文案（2026-10-22——后端已接受、回执丢失）：Start 回答
     * 的管道静默死亡后，恢复机制以**原问题行优先**重读世界（新 dock 永不
     * 能证明原 Start 失败），只说一个诚实状态——已启动 / 尚未确认启动 /
     * 暂时无法确定，永不声称无法证明的事实，永不自动重试（第二次 start
     * 只可能是用户的再次点击，服务器侧去重）。started → run 面板挂载
     * （info）；unconfirmed → pill 恢复（info——请求可能仍在处理中）；
     * unknown → 当前无法确认（error）。 */
    startRecovery: {
      started: "连接中断了，但制作已经开始——进度见下方任务列表。",
      unconfirmed:
        "连接中断，尚未确认制作是否启动——请求可能仍在处理中。可以稍等片刻，或重新开始（重复请求会被安全忽略）。",
      unknown: "连接中断——暂时无法确认制作是否已开始。可以重试，或刷新页面确认。",
    },
    runFailed: "运行失败",
    /** 收官句已于 2026-09-24 退役（用户拍板——与 trigger 回合的
     * run_completed 散文重复；现在只有 trigger 一个叙事者）。 */
    send: "发送",
    stop: "停止",
    undoLastEdit: "撤销上一步修改",
    ops: {
      remove_range: "剪掉片段",
      set_trim: "裁剪首尾",
      set_title: "设置标题",
      set_caption_style: "字幕样式",
      set_music: "音乐",
      set_crop: "画面重构",
      set_aspect: "画幅比例",
      set_caption_text: "修改字幕",
      restore_version: "恢复版本",
    },
    choicePlaceholder: "其他想法…",
    legacyStepSummaries: {
      uploaded: "已上传",
    },
    productionStages: {
      validate: "校验已确认版本",
      fonts: "准备字体",
      generator_media: "生成画面",
      speech_media: "生成旁白",
      visual_assets: "准备分镜图片",
      compile_spec: "编译视频规格",
      output_preparation: "创建待交付产物",
      output_resume: "复用已准备产物",
      render_queue: "提交渲染队列",
      produce_video: "正在制作你的视频…",
      prepare_narration: "正在准备配音…",
      render: "渲染",
      upload: "上传",
      delivery: "交付检查",
      reuseSummary: "{{total}} 项中复用 {{reused}} 项",
    },
    stepKinds: {
      prepare_visual_assets: "正在准备分镜画面…",
      prepare_visual_assetsDone: "分镜画面准备",
      prepare_narration: "正在准备分镜旁白…",
      prepare_narrationDone: "分镜旁白准备",
      prepare_music: "正在准备配乐…",
      prepare_musicDone: "配乐准备",
      preprocess: "正在分析上传的素材…",
      persona_bootstrap: "正在准备你的人设…",
      understand: "正在看懂你的素材…",
      interrupt: "等你选定方向…",
      plan: "正在规划内容结构…",
      render: "正在渲染视频…",
      stills: "正在抽取关键帧…",
      video: "正在处理视频…",
      add_music: "正在为你的片段配乐…",
      verify: "质检中…",
    },
    qa: {
      q: "问",
      a: "答",
      cancelled: "已取消——回到草稿",
      superseded: "已被更新的计划取代",
      expired: "超时未选——已按默认方向继续",
      stopped: "已停止生成",
    },
    retry: "重试",
    edit: "编辑",
    regenerate: "重新生成",
    render: "渲染视频",
    rendering: "渲染中...",
    translate: "翻译",
    copy: "复制",
    copied: "已复制",
    // 锚卡 (flora-parity-ui ③ · ADR-118): 终态收据行下的静态产物数组 —
    // 类型词供名缺回退(「类型词 · 规格」,零模板回填) + 文本族的字数规格。
    anchorCards: {
      view: "查看{{name}}",
      types: {
        video: "视频",
      },
      words: "约 {{count}} 字",
    },
    outputCard: {
      version: "v{{number}}",
    },
    outputViewer: {
      downloadError: "下载失败，请重试。",
      title: "已交付产物",
      selectRegion: "局部选择",
      referenceAsset: "引用此素材",
      regionHint: "拖动框选当前画面",
      regionLoading: "正在读取画面尺寸…",
      regionSummary: "{{time}} · 源画面 {{sourceWidth}}×{{sourceHeight}} · x{{x}} y{{y}} · {{width}}×{{height}}px",
      reselectRegion: "重新框选",
      referenceRegion: "引用选区",
      details: "产物详情",
      zoomIn: "放大",
      zoomOut: "缩小",
      unavailable: "产物不可用",
      unavailableDetail: "这个确切的历史交付已不可用，没有替换成更新的版本。",
    },
    uploadFile: "上传源文件",
    uploading: "上传中...",
    composerPlaceholder: "描述你想生成的内容...",
    composerFollowUpPlaceholder: "输入后续指令，例如“把 hook 改短”或“添加德语版本”...",
    emptyStateSubtitle: "上传演讲、会议或访谈的视频或文字——我们记住你的内容与风格，你点名什么，就做什么。",
    noResultsYet: "结果将在这里显示...",
    resultActions: {
      edit: "编辑",
      regenerate: "重新生成",
      export: "导出",
    },
    recentChats: "最近对话",
    noRecentChats: "暂无对话",
  },
  generationOverlay: {
    planVersion: "计划 v{{n}}",
    versionRestore: "恢复此版本",
    versionRestored: "已恢复为计划 v{{n}}——它是当前计划了。",
    // 修改态的 @ 候选包括素材与产物；首次创作态只有素材。两种形态都提供
    // 同一个 / Skill picker，不宣传不存在的 # 入口。
    chatPlaceholder: "输入 @ 引用素材或产物，输入 / 使用 Skill。",
    // full 形态（首次 run 前）专用：@ 候选只有素材。
    chatPlaceholderAssets: "描述你想做什么，输入 @ 引用素材，输入 / 使用 Skill。",
    attachFiles: "上传文件",
    retryUpload: "重试上传",
    removeAttachment: "移除附件",
    assetTypes: {
      video: "视频",
      audio: "音频",
      image: "图片",
      slides: "幻灯片",
      transcript: "文字稿",
      file: "文件",
    },
    stopped: "已停止生成。",
    // 确认 pill（ADR-117 §4 — 画板 C）：确认拍仅剩的 chrome，只在 dock 戳记
    // 说欠一拍时出现。label 族：裸动词（执行=询问）/ 带价（费用=询问 · 守卫线
    // ——数字恒为服务端 fold 上限，客户端永不自算）/ 延期报价（NULL 族——永不
    // 编数字）。点击把当前 label 作为普通用户消息交给 sendChat，下一轮 LLM
    // 再决定是否调用 start_run。
    confirmPillStart: "开始",
    confirmPillStartPriced: "开始 · 约 {{n}} 积分",
    confirmPillStartDeferred: "开始 · 估价随运行确定",
  },
  questionDock: {
    customize: "自定义这组设置",
    bail: "停止生成",
    skip: "跳过问题",
    recommended: "推荐",
    previous: "上一页",
    next: "下一页",
    submit: "提交回答",
    page: "{{current}} / {{total}}",
  },
  clipMenu: {
    more: "更多操作",
    download: "下载",
    publishOnSocial: "发布到社媒",
    share: "分享",
    shareCopied: "链接已复制",
  },
  login: {
    title: "登录 Rookie Cut",
    subtitle: "输入邮箱接收登录验证码，无需密码；首次登录会自动创建账号。",
    emailLabel: "邮箱地址",
    emailPlaceholder: "you@company.com",
    sendCode: "发送验证码",
    sending: "发送中…",
    enterCode: "输入验证码",
    codeTitle: "查收验证码邮件",
    codeSubtitle: "输入发送到 <b>{{email}}</b> 的 6 位验证码，10 分钟内有效。",
    digitLabel: "第 {{index}} 位，共 {{total}} 位",
    enterAllDigits: "请输入全部 6 位数字",
    verifyAndLogin: "验证并登录",
    verifying: "验证中…",
    didntReceive: "没收到邮件？",
    resendCode: "重新发送",
    resendIn: "{{count}} 秒后可重发",
    backToSignIn: "返回登录",
    sendFailed: "验证码发送失败，请检查邮箱地址后重试",
    verifyFailed: "验证码无效或已过期",
  },
  tour: {
    next: "下一步",
    prev: "上一步",
    skip: "跳过",
    done: "完成",
    stepOf: "第 {{current}} 步，共 {{total}} 步",
    composer: {
      assetsTitle: "添加你的素材",
      assetsDesc:
        "视频、音频、幻灯片、照片或文字稿都行，有什么放什么。也可以先不上传，直接在下面写想法。",
      promptTitle: "说明要做什么",
      promptDesc: "写下想要的结果。用 @ 点名已上传的素材，然后发送。",
      recipesTitle: "试试剪辑示例",
      recipesDesc: "点一个示例填入输入框，再按你的素材修改要求。",
    },
  },
  notifications: {
    title: "通知",
    empty: "没有新通知",
    publishUnknown: "{{platform}} 发布结果待核对",
    publishSucceeded: "已发布到 {{platform}}",
    publishFailed: "发布到 {{platform}} 失败",
    channelExpired: "{{platform}} 连接已过期",
    openPost: "查看帖子",
    retry: "重试",
    reconnect: "重新连接",
    retryQueued: "已重新排队，发布后通知你",
    justNow: "刚刚",
    minutesAgo: "{{count}} 分钟前",
    hoursAgo: "{{count}} 小时前",
    daysAgo: "{{count}} 天前",
  },
  publish: {
    title: "发布",
    chooseChannels: "选择渠道",
    connect: "连接",
    comingSoon: "即将上线",
    titleLabel: "标题",
    captionLabel: "正文",
    hashtagsLabel: "话题标签",
    aiDisclosure: "此片段包含 AI 生成内容，将被标记为 AI 生成。",
    cancel: "取消",
    publishNow: "立即发布",
    publishing: "发布中...",
    queued: "正在发布——上线后会通知你",
    failed: "创建发布单失败",
    selectChannel: "请至少选择一个渠道",
  },
  channels: {
    title: "渠道",
    subtitle: "连接账号即可直接发布",
    connect: "连接",
    disconnect: "断开连接",
    connected: "已连接",
    expired: "连接已过期",
    reconnect: "重新连接",
    comingSoon: "即将上线",
    connectedToast: "{{platform}} 已连接",
    connectFailed: "连接 {{platform}} 失败",
    disconnectedToast: "{{platform}} 已断开",
  },
  settings: {
    title: "设置",
  },
  a11y: {
    toggleSidebar: "切换侧边栏",
    openSidebar: "打开侧边栏",
  },
  // 质检环（产物质量线期 3）：verify 节点检查项的人话标签——
  // 徽标悬浮层渲染「<标签>: <明细>」。
  qualityChecks: {
    span_fidelity: "切片与源片段一致",
    quote_verbatim: "金句逐字一致",
    language_match: "语言符合目标",
    avoid_words: "规避词未命中",
    length_in_bounds: "长度在区间内",
    count_match: "数量符合请求",
    slide_count: "页数符合规划",
    shot_dwells: "分镜节奏",
    caption_sync: "字幕同步",
    face_safe_area: "人脸避开字幕区",
    emphasis_alignment: "强调贴在内容峰值上",
    repair_scope: "修复未越界",
    judge_quote_readability: "金句独立可读",
  },
}

export default zh
