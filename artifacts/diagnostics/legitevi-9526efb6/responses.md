# MiniMax 返回的原文

下列调用按请求的发起顺序排列。function.arguments 为字符串时，代码块逐字保留原字符串。调用 00 的流式响应由适配器汇总，其参数如为对象则按 JSON 展开。响应原始字段和类型见各轮 response.json。

## 00 · intent_router

[请求原文](calls/00/request.json) · [响应原文](calls/00/response.json) · [系统提示词](calls/00/system.txt)

我先把这个页面采集下来，等素材就绪后再读它的定位和视觉识别。

工具 prepare_video_materials

```json
{"material_urls": ["https://www.legitevi.com/en"]}
```

## 01 · intent_router

[请求原文](calls/01/request.json) · [响应原文](calls/01/response.json) · [系统提示词](calls/01/system.txt)

页面已采集完成，正文和五个页面视图都在。我先把这些内容整理成带来源的品牌档案，供后续剪辑引用。

工具 analyze_brand

```json
{"brief":{"topic":"LegitEvi 官网宣传片","audience":{"value":"高校科研管理者、技术政策制定者及产学研合作领域从业者","source":"user-stated"},"tone":{"value":"rational","source":"user-stated"}}}
```

## brand · website_brand_profile

[请求原文](calls/brand/request.json) · [响应原文](calls/brand/response.json) · [系统提示词](calls/brand/system.txt)

{
  "positioning": "LegitEvi 是面向科学家与内容创作者的 AI 平台，将研究论文转化为可验证、可追溯且由证据支持的短视频。",
  "claims": [
    {
      "text": "Scientists transform their papers into compelling short videos. Every claim is verifiable. Every video is backed by real research. Build influence with evidence you can prove.",
      "line_ids": [
        "line_0016"
      ],
      "kind": "fact"
    },
    {
      "text": "We equip researchers to translate complex science into accessible, accurate narratives.",
      "line_ids": [
        "line_0020"
      ],
      "kind": "fact"
    },
    {
      "text": "We empower creators to communicate responsibly with evidence-backed claims.",
      "line_ids": [
        "line_0021"
      ],
      "kind": "fact"
    },
    {
      "text": "Turn your research papers into short videos that reach millions. Your evidence becomes content, your science gains influence. Manage all your papers on our secure platform—upload, track, and take control of your scientific work.",
      "line_ids": [
        "line_0025"
      ],
      "kind": "fact"
    },
    {
      "text": "Create short videos backed by real scientific papers. Every claim you make can be verified. Build credibility with evidence.",
      "line_ids": [
        "line_0026"
      ],
      "kind": "fact"
    },
    {
      "text": "Every short video is created from research. AI transforms scientific papers into engaging content while preserving verifiable evidence.",
      "line_ids": [
        "line_0028"
      ],
      "kind": "fact"
    },
    {
      "text": "Each short video links directly to its source paper. Viewers can verify every claim. Creators build influence with evidence they can prove.",
      "line_ids": [
        "line_0029"
      ],
      "kind": "fact"
    },
    {
      "text": "Your short videos gain credibility from real research. Build influence that's backed by science, not just opinions.",
      "line_ids": [
        "line_0030"
      ],
      "kind": "fact"
    },
    {
      "text": "We provide AI-powered infrastructure that embeds evidence directly into short-form media — transforming peer-reviewed research into engaging, platform-ready content and enabling creators to back their claims with reputable, verifiable sources.",
      "line_ids": [
        "line_0041"
      ],
      "kind": "fact"
    }
  ],
  "taglines": [
    {
      "text": "Building the Global Standard for Evidence-Backed Short-Form Media",
      "line_ids": [
        "line_0000"
      ]
    },
    {
      "text": "LegitEvi: Where Research Powers Influence",
      "line_ids": [
        "line_0015"
      ]
    },
    {
      "text": "Citations should be as universal as hashtags.",
      "line_ids": [
        "line_0024"
      ]
    },
    {
      "text": "Empowering Scientific Transparency Through Blockchain",
      "line_ids": [
        "line_0033"
      ]
    }
  ],
  "colors": [
    {
      "value": "#DC0000",
      "role": "primary",
      "source": "visual",
      "confidence": "inferred",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0015"
          ]
        }
      ]
    },
    {
      "value": "#000000",
      "role": "text",
      "source": "visual",
      "confidence": "inferred",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0000",
            "line_0016"
          ]
        }
      ]
    },
    {
      "value": "#FFFFFF",
      "role": "background",
      "source": "visual",
      "confidence": "inferred",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": []
        }
      ]
    }
  ],
  "typography": [
    {
      "candidate": "接近 Inter 的现代无衬线字体",
      "weight": "主标题为粗体，正文与导航为常规或中等字重",
      "source": "visual",
      "confidence": "inferred",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0000",
            "line_0015",
            "line_0016"
          ]
        }
      ]
    }
  ],
  "brand_assets": [
    {
      "kind": "wordmark",
      "ref": "导航栏左上角可见“LegitEvi”字样，其中“Legit”为黑色、“Evi”为红色。",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0035",
            "line_0036",
            "line_0050"
          ]
        }
      ]
    },
    {
      "kind": "chatbot_button",
      "ref": "页面右下角可见带对话气泡图标的红色“Ask LegitEvi”按钮。",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0043",
            "line_0049"
          ]
        }
      ]
    },
    {
      "kind": "app_store_badges",
      "ref": "下载区域可见 Apple 标志及“Download on the App Store”徽章，以及 Google Play 标志及“Get it on Google Play”徽章。",
      "source_refs": [
        {
          "snapshot_id": "1cf05a4b-8ef9-5069-9581-0c9d16d3dbec",
          "view_id": "view-0",
          "line_ids": [
            "line_0037",
            "line_0038",
            "line_0039",
            "line_0040",
            "line_0058",
            "line_0059"
          ]
        }
      ]
    }
  ],
  "creative_direction": {
    "summary": "采用极简、高对比的科研传播视觉体系：以大面积白色留白承载清晰信息层级，以黑色无衬线文字建立可信度，并用精确测得的红色强调品牌名称、关键宣言、行动按钮与可信科技元素。视觉叙事应突出“研究—证据—短视频—可验证影响”的清晰转化链路。",
    "media_preferences": [
      "白色或近白色背景",
      "黑色高对比正文",
      "红色品牌强调",
      "简洁居中的英雄区构图",
      "清晰按钮和行动层级",
      "可验证研究证据的视觉表达"
    ],
    "avoid": [
      "未经证据支持的夸张科学效果",
      "削弱可验证性与可追溯性的表达",
      "复杂装饰导致信息层级不清",
      "把视觉观察结果表述为已确认的 CSS 或字体文件"
    ],
    "provenance": "inferred"
  },
  "unknowns": [
    "无法仅凭页面像素确认实际使用的字体家族、字重名称或 CSS 字体声明。",
    "无法从所附视图确认短视频的目标时长、叙事结构、旁白语言或字幕语言。",
    "无法从该视图确认除 English 之外的其他网站语言版本。",
    "无法从该视图确认移动应用的具体功能范围或已上线的应用商店版本。",
    "无法仅凭该页面确认“reach millions”“viral”等表述的实际业务效果。",
    "无法从该视图确认区块链实现的具体技术方案。"
  ],
  "conflicts": []
}

## 02 · intent_router

[请求原文](calls/02/request.json) · [响应原文](calls/02/response.json) · [系统提示词](calls/02/system.txt)

素材齐了。页面讲的是 LegitEvi：把同行评审过的研究论文转成可验证、可追溯的短视频，主张「引用应像标签一样普及」，还提到用区块链支撑科学透明度。视觉上是白底、黑色无衬线文字、红色强调的极简高对比体系。

在动手前，有几件事想跟你确认一下，你的场景和偏好会直接决定片子怎么讲。

工具 ask_user

```json
{"question": "这支片子主要在哪里播放，你希望我们怎样讲这个故事？", "items": [{"slot": "production_direction", "question_language": "zh-CN", "options": [{"use_case": "高校科研管理会议或产学研合作路演", "treatment": "以问题到方案的逻辑展开：先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束"}, {"use_case": "品牌官网首页或线上产品介绍", "treatment": "以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载"}, {"use_case": "科研传播与学术诚信主题的对外沟通", "treatment": "以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平"}]}, {"slot": "target_seconds", "question": "你期望成片大约多长？单位是秒。", "options": [{"value": "30"}, {"value": "45"}, {"value": "60"}]}, {"slot": "narration_language", "question": "旁白要用哪种语言？", "options": [{"label": "中文", "value": "zh-CN"}, {"label": "英文", "value": "en-US"}]}, {"slot": "subtitle_languages", "question": "字幕需要哪些语言？", "options": [{"label": "中文 + 英文", "value": ["zh-CN", "en-US"]}, {"label": "仅中文", "value": ["zh-CN"]}, {"label": "仅英文", "value": ["en-US"]}]}, {"slot": "aspect", "question": "你需要什么画幅？", "options": [{"value": "16:9"}, {"value": "9:16"}, {"value": "1:1"}]}], "default_path": "如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。"}
```

## 03 · intent_router

[请求原文](calls/03/request.json) · [响应原文](calls/03/response.json) · [系统提示词](calls/03/system.txt)

*content 为空。*

工具 ask_user

```json
{"items": [{"options": [{"treatment": "以问题到方案的逻辑展开：先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束。", "use_case": "高校科研管理会议或产学研合作路演"}, {"treatment": "以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载。", "use_case": "品牌官网首页或线上产品介绍"}, {"treatment": "以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平。", "use_case": "科研传播与学术诚信主题的对外沟通"}], "question": "这支片子主要在哪里播放，你希望我们怎样讲这个故事？", "question_language": "zh-CN", "slot": "production_direction"}, {"options": [{"label": "30 秒", "value": "30"}, {"label": "45 秒", "value": "45"}, {"label": "60 秒", "value": "60"}], "question": "你期望成片大约多长？单位是秒。", "slot": "target_seconds"}, {"options": [{"label": "中文", "value": "zh-CN"}, {"label": "英文", "value": "en-US"}], "question": "旁白要用哪种语言？", "slot": "narration_language"}, {"options": [{"label": "中文 + 英文", "value": ["zh-CN", "en-US"]}, {"label": "仅中文", "value": ["zh-CN"]}, {"label": "仅英文", "value": ["en-US"]}], "question": "字幕需要哪些语言？", "slot": "subtitle_languages"}, {"options": [{"label": "16:9 横屏", "value": "16:9"}, {"label": "9:16 竖屏", "value": "9:16"}, {"label": "1:1 方形", "value": "1:1"}], "question": "你需要什么画幅？", "slot": "aspect"}], "question": "这支片子主要在哪里播放，你希望我们怎样讲这个故事？", "default_path": "如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。"}
```

## 04 · intent_router

[请求原文](calls/04/request.json) · [响应原文](calls/04/response.json) · [系统提示词](calls/04/system.txt)

*content 为空。*

工具 ask_user

```json
{"question": "这支片子主要在哪里播放，你希望我们怎样讲这个故事？", "items": [{"options": [{"use_case": "高校科研管理会议或产学研合作路演", "treatment": "以问题到方案的逻辑展开：先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束。"}, {"use_case": "品牌官网首页或线上产品介绍", "treatment": "以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载。"}, {"use_case": "科研传播与学术诚信主题的对外沟通", "treatment": "以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平。"}], "question_language": "zh-CN", "slot": "production_direction"}, {"options": [{"value": "30"}, {"value": "45"}, {"value": "60"}], "question": "你期望成片大约多长？单位是秒。", "slot": "target_seconds"}, {"options": [{"label": "中文", "value": "zh-CN"}, {"label": "英文", "value": "en-US"}], "question": "旁白要用哪种语言？", "slot": "narration_language"}, {"options": [{"label": "中文 + 英文", "value": ["zh-CN", "en-US"]}, {"label": "仅中文", "value": ["zh-CN"]}, {"label": "仅英文", "value": ["en-US"]}], "question": "字幕需要哪些语言？", "slot": "subtitle_languages"}, {"options": [{"label": "16:9 横屏", "value": "16:9"}, {"label": "9:16 竖屏", "value": "9:16"}, {"label": "1:1 方形", "value": "1:1"}], "question": "你需要什么画幅？", "slot": "aspect"}], "default_path": "如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。"}
```

## 05 · intent_router

[请求原文](calls/05/request.json) · [响应原文](calls/05/response.json) · [系统提示词](calls/05/system.txt)

*content 为空。*

工具 ask_user

```json
{"question": "这支片子主要在哪里播放，你希望我们怎样讲这个故事？", "items": [{"options": [{"use_case": "高校科研管理会议或产学研合作路演", "treatment": "以问题到方案的逻辑展开：先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束。"}, {"use_case": "品牌官网首页或线上产品介绍", "treatment": "以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载。"}, {"use_case": "科研传播与学术诚信主题的对外沟通", "treatment": "以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平。"}], "question_language": "zh-CN", "slot": "production_direction"}, {"options": [{"value": "30"}, {"value": "45"}, {"value": "60"}], "question": "你期望成片大约多长？单位是秒。", "slot": "target_seconds"}, {"options": [{"label": "中文", "value": "zh-CN"}, {"label": "英文", "value": "en-US"}], "question": "旁白要用哪种语言？", "slot": "narration_language"}, {"options": [{"label": "中文 + 英文", "value": ["zh-CN", "en-US"]}, {"label": "仅中文", "value": ["zh-CN"]}, {"label": "仅英文", "value": ["en-US"]}], "question": "字幕需要哪些语言？", "slot": "subtitle_languages"}, {"options": [{"label": "16:9 横屏", "value": "16:9"}, {"label": "9:16 竖屏", "value": "9:16"}, {"label": "1:1 方形", "value": "1:1"}], "question": "你需要什么画幅？", "slot": "aspect"}], "default_path": "如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。"}
```

## 06 · intent_router

[请求原文](calls/06/request.json) · [响应原文](calls/06/response.json) · [系统提示词](calls/06/system.txt)

我把问题卡再发一次，请你在这几个点上定下来，我就能直接开工。

工具 ask_user

```json
{"question":"这支片子的创作设定，请确认","items":[{"options":[{"use_case":"高校科研管理会议或产学研合作路演","treatment":"先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束。"},{"use_case":"品牌官网首页或线上产品介绍","treatment":"以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载。"},{"use_case":"科研传播与学术诚信主题的对外沟通","treatment":"以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平。"}],"question_language":"zh-CN","slot":"production_direction"},{"options":[{"value":"30"},{"value":"45"},{"value":"60"}],"question":"你期望成片大约多长？单位是秒。","slot":"target_seconds"},{"options":[{"label":"中文","value":"zh-CN"},{"label":"英文","value":"en-US"}],"question":"旁白要用哪种语言？","slot":"narration_language"},{"options":[{"label":"中文 + 英文","value":["zh-CN","en-US"]},{"label":"仅中文","value":["zh-CN"]},{"label":"仅英文","value":["en-US"]}],"question":"字幕需要哪些语言？","slot":"subtitle_languages"},{"options":[{"label":"16:9 横屏","value":"16:9"},{"label":"9:16 竖屏","value":"9:16"},{"label":"1:1 方形","value":"1:1"}],"question":"你需要什么画幅？","slot":"aspect"}],"default_path":"如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。"}
```

## 07 · intent_router

[请求原文](calls/07/request.json) · [响应原文](calls/07/response.json) · [系统提示词](calls/07/system.txt)

*响应中省略了 content 字段。*

工具 ask_user

```json
{"items":[{"options":[{"treatment":"先点出短视频内容缺乏引用与学术问责的问题，再说明 LegitEvi 如何把同行评审论文转为可验证短视频，落到科研影响力与透明度的价值，收尾以合作邀请收束。","use_case":"高校科研管理会议或产学研合作路演"},{"treatment":"以产品能力为主线：演示论文到短视频的转化链路、每条视频可回溯至原始论文的证据机制，以及科学家、创作者、公众三类用户的分工，节奏紧凑，最后引导下载。","use_case":"品牌官网首页或线上产品介绍"},{"treatment":"以「引用应像标签一样普及」为命题，先呈现无引用的传播现状，再论证证据内嵌的可验证性，说明区块链在科学透明度上的定位，收束于全球科研生态的透明与公平。","use_case":"科研传播与学术诚信主题的对外沟通"}],"question":"这支片子主要在哪里播放，你希望我们怎样讲这个故事？","question_language":"zh-CN","slot":"production_direction"},{"options":[{"label":"30 秒","value":"30"},{"label":"45 秒","value":"45"},{"label":"60 秒","value":"60"}],"question":"你期望成片大约多长？单位是秒。","slot":"target_seconds"},{"options":[{"label":"中文","value":"zh-CN"},{"label":"英文","value":"en-US"}],"question":"旁白要用哪种语言？","slot":"narration_language"},{"options":[{"label":"中文 + 英文","value":["zh-CN","en-US"]},{"label":"仅中文","value":["zh-CN"]},{"label":"仅英文","value":["en-US"]}],"question":"字幕需要哪些语言？","slot":"subtitle_languages"},{"options":[{"label":"16:9 横屏","value":"16:9"},{"label":"9:16 竖屏","value":"9:16"},{"label":"1:1 方形","value":"1:1"}],"question":"你需要什么画幅？","slot":"aspect"}],"default_path":"如果暂时不填，我会按最常见的设定推进：45 秒、中文旁白、中英双语字幕、16:9 画幅，叙事采用以产品能力为主线、兼顾科研影响力价值的方式。","question":"这支片子的创作设定，请确认"}
```

## 08 · intent_router

[请求原文](calls/08/request.json) · [响应原文](calls/08/response.json) · [系统提示词](calls/08/system.txt)

看起来问题卡没能正常送达，我直接按最稳妥的默认设定推进，这样你可以先看到片子，之后随时告诉我改哪里。

默认设定：**45 秒、中文旁白、中英双语字幕、16:9 横屏**，叙事以产品能力为主线，先呈现短视频传播中缺乏引用与学术问责的问题，再讲清 LegitEvi 把同行评审论文转成可验证短视频的链路，最后落到科研影响力与透明度价值并收束于行动号召。

视觉沿用品牌识别：白底留白、黑色无衬线正文、红色强调，构图保持官网首页那种居中英雄区的清晰层级。

我先把这套设定记入需求单。

工具 answer

```json
{"brief":{"topic":{"value":"LegitEvi 官网宣传片","source":"inferred"},"audience":{"value":"高校科研管理者、技术政策制定者及产学研合作领域从业者","source":"user-stated"},"tone":{"value":"rational","source":"user-stated"},"purpose":{"value":"品牌官网首页或线上产品介绍","source":"inferred"},"production_direction":{"value":"用于品牌官网首页与线上产品介绍，以产品能力为主线：先呈现短视频传播中缺乏引用与学术问责的问题，再讲清 LegitEvi 将同行评审论文转为可验证短视频的转化链路与证据回溯机制，落到科研影响力与透明度价值，收尾给出行动号召","source":"inferred"},"narrative_mode":{"value":"问题到方案的递进结构，末段以价值主张收束","source":"inferred"},"target_seconds":{"value":45,"source":"default"},"narration_language":{"value":"zh-CN","source":"default"},"subtitle_languages":{"value":["zh-CN","en-US"],"source":"default"},"aspect":{"value":"16:9","source":"default"},"must_include":{"value":["论文到短视频的转化链路","每条视频可回溯至原始论文的证据机制","科学家、创作者、公众三类用户分工","引用应像标签一样普及这一主张"],"source":"inferred"},"avoid":["未经证据支持的夸张科学效果","无法核实的业务效果表述"]},"source":"inferred","success_criteria":["清楚说明可验证与可追溯这一核心差异","视觉上延续官网高对比极简识别"],"material_state":{"value":"attached","source":"inferred"},"asked":["production_direction","target_seconds","narration_language","subtitle_languages","aspect"],"pending_disposition":"answer"}
```

## 09 · intent_router

[请求原文](calls/09/request.json) · [响应原文](calls/09/response.json) · [系统提示词](calls/09/system.txt)

*响应中省略了 content 字段。*

工具 answer

```json
{"brief":{"topic":{"value":"LegitEvi 官网宣传片","source":"inferred"},"audience":{"value":"高校科研管理者、技术政策制定者及产学研合作领域从业者","source":"user-stated"},"tone":{"value":"rational","source":"user-stated"},"purpose":{"value":"品牌官网首页或线上产品介绍","source":"inferred"},"production_direction":{"value":"用于品牌官网首页与线上产品介绍，以产品能力为主线：先呈现短视频传播中缺乏引用与学术问责的问题，再讲清 LegitEvi 将同行评审论文转为可验证短视频的转化链路与证据回溯机制，落到科研影响力与透明度价值，收尾给出行动号召","source":"inferred"},"narrative_mode":{"value":"问题到方案的递进结构，末段以价值主张收束","source":"inferred"},"target_seconds":{"value":45,"source":"default"},"narration_language":{"value":"zh-CN","source":"default"},"subtitle_languages":{"value":["zh-CN","en-US"],"source":"default"},"aspect":{"value":"16:9","source":"default"},"must_include":{"value":["论文到短视频的转化链路","每条视频可回溯至原始论文的证据机制","科学家、创作者、公众三类用户分工","引用应像标签一样普及这一主张"],"source":"inferred"},"avoid":["未经证据支持的夸张科学效果","无法核实的业务效果表述"]},"pending_disposition":"answer"}
```

## 10 · intent_router

[请求原文](calls/10/request.json) · [响应原文](calls/10/response.json) · [系统提示词](calls/10/system.txt)

我把设定记入需求单，随后开始搭建片子。

工具 answer

```json
{"brief":{"aspect":{"value":"16:9","source":"default"},"audience":{"value":"高校科研管理者、技术政策制定者及产学研合作领域从业者","source":"user-stated"},"avoid":["未经证据支持的夸张科学效果","无法核实的业务效果表述"],"material_state":{"value":"attached","source":"inferred"},"must_include":["论文到短视频的转化链路","每条视频可回溯至原始论文的证据机制","科学家、创作者、公众三类用户分工","引用应像标签一样普及这一主张"],"narrative_mode":{"value":"问题到方案的递进结构，末段以价值主张收束","source":"inferred"},"narration_language":{"value":"zh-CN","source":"default"},"production_direction":{"value":"用于品牌官网首页与线上产品介绍，以产品能力为主线：先呈现短视频传播中缺乏引用与学术问责的问题，再讲清 LegitEvi 将同行评审论文转为可验证短视频的转化链路与证据回溯机制，落到科研影响力与透明度价值，收尾给出行动号召","source":"inferred"},"purpose":{"value":"品牌官网首页或线上产品介绍","source":"inferred"},"subtitle_languages":{"value":["zh-CN","en-US"],"source":"default"},"target_seconds":{"value":45,"source":"default"},"tone":{"value":"rational","source":"user-stated"},"topic":{"value":"LegitEvi 官网宣传片","source":"inferred"}},"pending_disposition":"answer"}
```
