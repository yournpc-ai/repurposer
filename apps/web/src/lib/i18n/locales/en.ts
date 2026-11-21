const en = {
  agentReceipt: {
    job: "Media operation",
    chargedCredits: "Charged credits · {{count}}",
    reservedCredits: "Reserved credits · {{count}}",
    accepted: "Awaiting execution",
    queued: "Queued",
    running: "Running",
    success: "Succeeded",
    error: "Failed",
    cancelled: "Cancelled",
    unknown: "Result unknown",
    notExecuted: "Not executed",
    pending: "Awaiting confirmation",
    denied: "Declined",
    approved: "Approved",
    versionSaved: "Version saved",
    outputGenerated: "Ready for review",
    delivered: "Delivered",
    group: "Tool calls ({{count}})",
    thinking: "Thinking",
    quote: "Quoted cost",
    limit: "Spending limit",
    approve: "Approve",
    decline: "Decline",
  },
  common: {
    retryHistory: "Reload conversation",
    upload: "Upload",
    googleDrive: "Google Drive",
    delete: "Delete",
    create: "Create",
    creating: "Creating...",
    save: "Save",
    saving: "Saving...",
    search: "Search",
    all: "All",
    back: "Back",
    cancel: "Cancel",
    close: "Close",
    done: "Done",
    previous: "Previous",
    next: "Next",
    remove: "Remove",
    loading: "Loading...",
    untitled: "Untitled",
    preview: "Preview",
    toggleTheme: "Toggle theme",
    preferences: "Preferences",
    helpSection: "Help",
    theme: "Theme",
    themeSystem: "System",
    themeLight: "Light",
    themeDark: "Dark",
    replayTour: "Replay home tour",
    credits: "Credits",
    language: "Language",
    settings: "Settings",
    logout: "Log out",
    login: "Log in",
    guest: "Guest",
    new: "New",
    upgrade: "Upgrade",
    requestFailed: "Request failed",
    networkError: "Network error — check your connection",
    skipToContent: "Skip to content",
  },
  assistant: {
    /** SettingsDialog「助手」section (ADR-117 §1) — the two confirmation
     * prefs' ONLY UI seat. Plain factual copy; the guardrail stays an ops
     * parameter, the footnote is its single honest mention. */
    title: "Assistant",
    subtitle:
      "When the assistant checks with you before acting. Everything else it just does.",
    permissions: "Permissions",
    execution: {
      label: "Taking action",
      desc: "After you ask for work to be made, whether it waits for one more go-ahead.",
    },
    spending: {
      label: "Spending credits",
      desc: "Before a paid plan starts, whether to confirm once with the price.",
    },
    mode: { auto: "Automatic", ask: "Ask" },
    footnote:
      "The estimate is always shown with the plan. Above-guardrail plans always ask once. Unquotable plans ask only when execution or credits is set to Ask; Automatic proceeds without another confirmation.",
    updateFailed: "Couldn't save the setting — please try again",
  },
  general: {
    /** SettingsDialog「通用」section (ADR-123) — display-class prefs. */
    title: "General",
    subtitle: "How the studio lays itself out.",
    workspaceLayout: {
      label: "Workspace layout",
      desc: "Auto pairs the canvas with the chat on wide screens and goes chat-first on narrow ones. Chat-first makes the conversation the workspace on every screen — products arrive in the message flow.",
      auto: "Auto",
      chat: "Chat-first",
    },
    updateFailed: "Couldn't save the setting — please try again",
  },
  credits: {
    /** The one estimate range form every surface shares (dock total /
     * per-task price / — three surfaces, one source, BILLING §7). */
    range: "~{{low}}–{{high}} credits",
    /** The inspector's 对账尺 actual side (2026-09-06) — the metered charge
     * of the product's producing step, shown against credits.range's quote. */
    spent: "{{count}} credits",
    /** The user-level shortfall grey row (BILLING §7) — strictly two
     * vocabularies with the provider's 402 line. Purchase lives in the
     * Settings credits section, not in this inline run error. */
    insufficient:
      "Not enough credits — your balance is {{balance}}, this run needs about {{required}}.",
    /** BILLING §5: a NULL-estimate run may settle the balance negative — the
     * number shows honestly and this note explains it (account console /
     * credits pill). No top-up CTA yet — the purchase entry is W11. */
    negativeNote:
      "Your last run cost more than estimated — the difference has been recorded. Top up to continue.",
    /** The project page's bottom-left credits pill and its popover
     * (BILLING §7 read surface, 2026-09-06). */
    balance: "Balance",
    held: "Held in active runs",
    /** The pill hero's inline held mention (meta row: "Credits · 12 held"). */
    heldInline: "{{count}} held",
    recent: "Recent",
    topups: "Top-ups",
    spending: "Spending",
    page: "{{page}} / {{pages}}",
    /** The SettingsDialog「积分」section (BILLING §7 展示主轴) — the
     * balance + ledger full-view seat, same two endpoints as the pill. */
    title: "Credits",
    subtitle: "Your balance, top-ups, and recent activity.",
    available: "Available credits",
    amount: "Top-up amount",
    buyTitle: "Add credits",
    packageCredits: "{{count}} credits",
    buy: "Buy credits",
    pay: "Pay",
    buying: "Opening…",
    conversion: "{{unit}} = {{credits}} credits",
    rateInfo: "Credit conversion and amount limits",
    amountRange: "Enter {{min}}–{{max}} per top-up.",
    packagesLoadFailed: "Couldn't load top-up options.",
    retry: "Try again",
    paymentSuccess: "Payment successful",
    topupSuccess: "{{count}} credits added. Select Done to view your top-ups.",
    checkAgain: "Check again",
    return: {
      confirming: "Confirming your payment…",
      pending: "Payment is still being confirmed. Check again shortly.",
      cancelled: "Checkout cancelled — no credits were added.",
      failed: "This payment didn't complete — no credits were added.",
    },
    viewAll: "View all",
    tx: {
      empty: "No transactions yet",
      type: "Type",
      orderId: "Order",
      paidAt: "Paid at",
      provider: "Provider",
      reference: "Reference",
      creation: "Creation",
      outputs: "Outputs",
      spentAt: "Spent at",
      project: "Project",
      amount: "Credits spent",
      paymentAmount: "Payment",
      receivedCredits: "Credits received",
      status: "Status",
      success: "Paid",
      credited: "Credited",
      topupEmpty: "No top-ups yet",
      spendEmpty: "No spending yet",
      /** The semantic fold (ADR-057 K4): the user面 only ever sees three
       * families — spend / grant / top-up; the ledger's hold / capture /
       * release machinery folds server-side and never crosses the wire. */
      /** Last-resort spend-row title — only when a run carries neither an
       * LLM-chosen name nor produced types (tx-row.tsx composes the chain). */
      spent: "Spent",
    },
  },
  nav: {
    home: "Home",
    personas: "Personas",
    myProjects: "My projects",
  },
  home: {
    newChat: "New chat",
    // Studio hero: one question line above the composer — the rotating
    // placeholder below answers it with three example prompts.
    heroQuestion: "What should we make today?",
    // Composer placeholder: three first-person example prompts rotating
    // (Lovart-style), NO prefix — each is a complete request in the user's
    // own voice, answering the hero question above. Keep each short enough
    // to stay one line in the docked bar.
    placeholderPrompts: [
      "Make a promo video for my website",
      "Cut my talk into highlight clips",
      "Make a promo video for my restaurant",
    ],
    selectPersona: "Persona",
    noPromptError: "Say what you want to make first",
    personaCreateFailed: "Failed to create persona",
  },
  landing: {

  "heroEyebrow": "Your AI video agent",
  "showcase": {
    "label": "Video creation demonstration",
    "types": "Video types",
    "attach": "Add material",
    "send": "Start a conversation",
    "preview": "Video preview",
    "start": "What would you like to make?",
    "play": "Play demonstration",
    "pause": "Pause demonstration",
    "replies": {
      "product-promo": "The edit opens on the dropper and adds a simple product title.\nYou can ask to change the title or adjust the pace.",
      "talking-head": "The series label sits at the top, and the episode title slides in below the speaker.\nYou can change when the title appears.",
      "text-animation": "Your wording is unchanged, with text beats and emphasis timed to the copy.\nPick any line to change its animation, pacing, or colors.",
      "knowledge-explainer": "The Moon footage sits beside a short explanation of what we see from Earth.\nYou can ask for a longer explanation or change the layout."
    },
    "disclosure": "Sample edit · Stock footage",
    "disclosureShort": "Interaction illustration",
    "requests": {
      "product-promo": "Make a short promo for this serum. Open with the dropper in use.",
      "talking-head": "Give this podcast clip a series label and an animated title.",
      "text-animation": "Animate “Light in motion” over a neon background. Keep the wording.",
      "knowledge-explainer": "Explain why the Moon changes shape, using a Moon shot and a short on-screen explanation."
    },
    "steps": {
      "product-promo": {
        "understand": {
          "active": "Clarifying the product story…",
          "done": "Clarified the product story."
        },
        "storyboard": {
          "active": "Planning the product scenes…",
          "done": "Planned the product scenes."
        },
        "produce": {
          "active": "Adding the product title…",
          "done": "Added the product title."
        }
      },
      "talking-head": {
        "understand": {
          "active": "Reviewing the footage…",
          "done": "Reviewed the footage."
        },
        "storyboard": {
          "active": "Timing the title…",
          "done": "Timed the title."
        },
        "produce": {
          "active": "Adding the label and title…",
          "done": "Added the label and title."
        }
      },
      "text-animation": {
        "understand": {
          "active": "Breaking the copy into beats…",
          "done": "Broke the copy into beats."
        },
        "storyboard": {
          "active": "Designing text motion…",
          "done": "Designed the text motion."
        },
        "produce": {
          "active": "Assembling the text video…",
          "done": "Assembled the text video."
        }
      },
      "knowledge-explainer": {
        "understand": {
          "active": "Structuring the explanation…",
          "done": "Structured the explanation."
        },
        "storyboard": {
          "active": "Pairing the explanation with Moon footage…",
          "done": "Paired the explanation with Moon footage."
        },
        "produce": {
          "active": "Assembling the explainer video…",
          "done": "Assembled the explainer video."
        }
      }
    }
  },
  "story": {
    "demoLabel": "Conversational video creation demo",
    "idea": {
      "title": "Tell us about your video."
    },
    "deliveryTitle": "From storyboard to video.",
    "refineTitle": "Ask for a change in the same chat.",
    "request": "Can you make a short video that shows what my product does?",
    "attachments": {
      "label": "Example attachments",
      "image": "product-image.png",
      "document": "product-brief.pdf"
    },
    "storyboardSummary": "Let’s open with the problem, show the product in use, then end with what it helps people do.",
    "rendering": "Making the video…",
    "delivery": "Here’s the first cut.",
    "posterAlt": "Preview of the first cut",
    "feedback": "Show the product in use right at the start.",
    "revisionOpening": "I’ll move the demo to the opening and shorten the original intro to one line.",
    "followup": "What would you like to change?",
    "scroll": "Keep scrolling"
  },
  "skills": {
    "label": "Skills",
    "titleFirst": "One-click skills,",
    "titleSecond": "ready for your next video",
    "create": "Create with {{name}}",
  },
  "faqSection": {
    "title": "A few things you might be wondering.",
    "experience": {
      "question": "How do I make my first video?",
      "answer": "Tell Rookie Cut what you want to make and who it’s for. Try “Help me make a 30-second video introducing my new product.” You can review the storyboard before production starts."
    },
    "material": {
      "question": "Can I start with just an idea?",
      "answer": "Yes. Describe your idea and Rookie Cut will ask for any material it needs. If you already have a script, images, or footage, add them to the chat. For a product video, you can also share a website link."
    },
    "revision": {
      "question": "Can I change just one part of the video?",
      "answer": "Point to the moment or scene in the same chat and say what you want changed. For example, “Shorten the title at 0:05” or “Move the product close-up to the opening.”"
    },
    "pricing": {
      "question": "When do I use credits?",
      "answer": "Discussing ideas and edits is free. Making a video or producing a revised version uses credits, and you can check the estimate before production. During beta, you can top up as needed without a subscription."
    },
    "download": {
      "question": "How do I download my finished video?",
      "answer": "Open the delivered video in the chat to preview it, then click download to save it as an MP4."
    }
  },
  "footerItems": {
    "pricing": "Pricing",
    "changelog": "Changelog",
    "terms": "Terms of Service",
    "privacy": "Privacy Policy"
  }
,
    nav: {
      features: "How it works",
      pricing: "Pricing",
      faq: "FAQ",
      earlyAccess: "Early access",
    },
    signIn: "Sign in",
    openStudio: "Create a video",
    headerCta: "Get started",
    heroCta: "Create now",
    entry: {
      navigation: "Main navigation",
      community: "Join the community",
    },
    heroTitle1: "Rookies can make great videos too.",
    heroTitle2: "",
    heroSubtitle:
      "No complex timelines or keyframes.\nCreate animated promos and explainer videos—just by chatting.",
    earlyAccess: {
      title: "Make videos without waiting until everything is ready.",
      description: "No tools to wrangle or techniques to learn. It all happens in a Rookie Cut chat.",
      credits: "New accounts get 1,000 free credits. No card needed to sign up.",
      estimate: "See the estimated credit cost before production.",
      note: "During beta, we're continuing to improve production reliability and detailed review.",
    },
    gallery: {
      heading: "Need an idea? Start here.",
      intro: "A few directions to explore. Start with the one closest to your idea.",
      create: "Make one like this",
      items: {
        "product-promo": {
          title: "Product Promo",
          description: "Combine your website, footage, images, and text in one product video.",
          prompt: "Make a short video introducing my product. Show how it works.",
        },
        "talking-head": {
          title: "Talking-head Motion",
          description: "Keep your footage and voice; add titles, captions, and motion.",
          prompt: "Add captions and a few clear titles to my recording. Keep my voice.",
        },
        "text-animation": {
          title: "Text Animation",
          description: "Turn your script into animated type, graphics, and sound.",
          prompt: "Turn this text into an expressive animated video.",
        },
        "knowledge-explainer": {
          title: "Knowledge Explainer",
          description: "Turn what you know into a narrated visual explanation.",
          prompt: "Explain this idea with animation for someone new to the topic.",
        },
      },
    },
    footer: {
      autoTheme: "Auto",
      columns: {
        company: "Company",
        social: "Social media",
        product: "Product",
        legal: "Legal",
      },
      resources: {
        examples: "Video examples",
        app: "Go to app",
        support: "Contact support",
      },
      channels: {
        wechat: "WeChat",
      },
      wechat: {
        title: "Join the WeChat group",
        description: "Scan the QR code with WeChat to join the conversation.",
        qrAlt: "Rookie Cut WeChat group QR code",
      },
      legal: {
        terms: "Terms of Service",
        privacy: "Privacy Policy",
        refund: "Refund Policy",
      },
      copyright: "© {{year}} Rookie Cut. All rights reserved.",
      backToTop: "Back to top",
    },
  },
  composer: {
    persona: "Persona",
    autoGenerate: "Auto",
    assets: "Assets",
    models: "Models",
    // Drag-drop affordance (2026-09-24): the floating pill over the composer
    // while a file drag hovers, and the toast when nothing dropped is a
    // supported type (the ASSETS_ACCEPT list).
    dropHint: "Drop files to upload",
    dropInvalid: "That file type isn't supported yet",
    // Honest Auto panel (2026-08-30): every row is the pipeline's REAL
    // per-modality assignment, read-only — no selectable rows while each
    // modality has exactly one provider.
    modelsRows: {
      copy: "Writing",
      voice: "Voice",
      captions: "Captions",
      music: "Music",
    },
    modelsNames: {
      copy: "MiniMax M3",
      voice: "MiniMax speech-2.6-hd",
      captions: "Whisper",
      music: "MiniMax music-2.6",
    },
    modelsDescs: {
      copy: "Planning, writing, and revisions",
      voice: "Voice cloning + multilingual dubbing",
      captions: "Self-hosted · word-level timestamps",
      music: "AI-generated library · matched by mood",
    },
    personaAutoDesc: "Build or match a persona from this upload",
    voiceBound: "Voice cloned",
    voiceMissing: "No voice clone",
    fileKinds: { video: "Video", audio: "Audio", image: "Image", doc: "Document" },
    assetsUpload: "Upload files",
    assetsFormats: "MP4 · MOV · WEBM · MP3 · WAV · M4A · PNG · JPG · WEBP · TXT · MD · PDF · DOC · DOCX · SRT · VTT",
    uploadFailed: "Upload failed — please try again",
    uploadRetry: "Retry",
    uploadInProgress: "Files are still uploading — give it a moment",
    managePersonas: "Manage personas…",
  },
  // Recipe cards (RECIPES §7) — one block per card id in lib/recipes.ts;
  // reserved cards render disabled with the Soon pill, never launchable.
  recipes: {
    soon: "Soon",
    // Product names reuse skills.builtin; application labels mirror the Home
    // registry. Empty video applications stay visible with an honest empty
    // state. Sample prompts live at recipes.shelf.demos.<demoId>.prompt.
    shelf: {
      subs: {
        "website-product": "Websites & products",
        "course-service": "Courses & services",
        "opinion-talking-head": "Opinion talking head",
        "course-lecture-teaser": "Course & lecture teasers",
        "opinion-text": "Opinion text videos",
        "quote-announcement": "Quotes & announcements",
        "concept-explainer": "Concept explainers",
        "research-report": "Research & reports",
      },
      nextPage: "More",
      previousPage: "Previous",
      upgrading: "Content is being upgraded",
      usePrompt: "Start creating",
      playSound: "Play sound",
      mute: "Mute",
      emptyDemo: "No sample for this application yet.",
      // MG shelf prefill blank: a VISIBLE placeholder, inserted selected so
      // paste replaces it in one gesture; it never becomes a hidden field or
      // a second input surface.
      urlPlaceholder: "[your website URL]",
      urlRequired: "Add your website link first",
      // MG shelf demo prefill copy (D3 — one key per ShelfDemo id in
      // components/home/recipeFamilies.ts). The prompt IS the card's entire
      // launch payload (composer 预填, 配方 = 提示词); {{placeholder}} is the
      // visible website blank the user replaces before send.
      demos: {
        "text-short-gentle-close": {
          prompt:
            "Use this Skill to help me animate this line:\n\nSlow down. Go further.",
        },
        "text-short-genesis": {
          prompt:
            "Use this Skill to help me animate this line:\n\nEvery great idea starts with a small step.",
        },
        "product-demo-zymix": {
          prompt:
            "Use this Skill to help me make a demo showing how this product works: {{placeholder}}",
        },
        // Website-source demos use the capture flow; video-source entries keep
        // upload-based prompts.
        "product-demo-walkthrough": {
          prompt:
            "Use this Skill to help me turn my screen recording into a walkthrough that makes the key steps easy to follow.",
        },
        "product-demo-highlights": {
          prompt:
            "Use this Skill to help me make a short video highlighting this product’s most useful features: {{placeholder}}",
        },
        "product-demo-captioned": {
          prompt:
            "Use this Skill to help me add text explanations that make my video easier to understand.",
        },
        "product-promo-agentveil-the-next-move": {
          prompt:
            "Use this Skill to make a short promotional video from this website, showing viewers the product’s value: {{placeholder}}",
        },
        "product-promo-oxvalue-product-evidence": {
          prompt:
            "Use this Skill to make a short promotional video from this website, showing viewers the product’s value: {{placeholder}}",
        },
        "product-promo-oxvalue-energy-arc": {
          prompt:
            "Use this Skill to make a short promotional video from this website, showing viewers the product’s value: {{placeholder}}",
        },
        "text-short-clear-rhythm": {
          prompt:
            "Animate this copy:\n\nWe often assume that the more we say, the more people understand.\nSo we add context, pile on details, and try to cover every point.\nBut as the information grows, the idea we wanted to share can get lost.\n\nClear communication starts with a clear question.\nExplain the problem, then use a concrete example to show why it matters.\nGive each idea room to breathe, and your audience time to understand.\n\nMaking complex ideas clear takes more than cutting words.\nIt takes a thread people want to follow—and can follow.\nHelp great content move from being seen to being understood.",
        },
        "knowledge-explainer-clear-expression": {
          prompt:
            "Use this Skill to help me make an animation explaining why focusing on one point at a time makes an idea easier to understand, for someone new to the topic.",
        },
      },
    },
    "multilingual-subs": {
      title: "Multilingual captions",
      promise:
        "Caption your video in any language — single-line, or bilingual side-by-side.",
      inputScenario: "For: talks · meetings",
      promptTemplate:
        "Caption my video in Chinese and French — Chinese as bilingual subtitles.",
    },
    "voice-dub": {
      title: "Your-voice AI dub",
      promise:
        "The same talk, in another language — in your voice, not a stock narrator.",
      inputScenario: "For: talks · meetings",
      promptTemplate:
        "Dub my video into Chinese, French, and Spanish — in my own voice, not a stock narrator.",
    },
    "social-post": {
      // Recipe-gallery v2 (ADR-048, §4.6): the loop-value clause on the
      // promise ("the channel's up to you") is what clears gate ② — a
      // generic LLM can translate, it can't own your style + the route.
      title: "Social post",
      promise:
        "Long-form talk or paper, ready-to-post. Written in your style — pick the channel.",
      inputScenario: "For: talks · papers · meeting notes",
      promptTemplate:
        "I want a social post.",
    },
    "quote-cards": {
      // 2026-08-27 v3 (ADR-048 第 7 条): the stacked cascade IS the quote
      // card — the promise names the stacked dish, never the one-liner
      // single card (single-quote images are a chat capability, not the
      // card face).
      title: "Quote cards",
      promise:
        "The sharpest lines of your talk, stacked into one ready-to-post quote card.",
      inputScenario: "For: talk recordings · interviews · transcripts",
      promptTemplate:
        "Make a bilingual quote card.",
    },
    carousel: {
      title: "Carousel slides",
      promise:
        "Talk or deck points, paginated into a swipeable slide deck.",
      inputScenario: "For: scripts · slide notes",
      promptTemplate:
        "I want a carousel.",
    },
    "image-video": {
      title: "Photos to video",
      promise: "No footage — photos plus your script, with captions and music.",
      inputScenario: "For: scripts + photos · slide decks",
      promptTemplate:
        "Turn my transcript and photos into a slideshow video — photos follow the sections, with captions and background music.",
    },
    "highlight-clips": {
      title: "Highlight clips",
      promise:
        "Your long video's best moments as vertical clips — top pick flagged.",
      inputScenario: "For: long talk recordings",
      promptTemplate:
        "Cut the best moment of my talk into a vertical clip — the camera follows the speaker, captions included.",
    },
    reframe: {
      title: "Interview reframe",
      promise: "Two-person talk recut vertical — the camera follows the speaker.",
      inputScenario: "For: two-person interviews",
      promptTemplate:
        "Recut my two-person interview into vertical clips — the camera follows whoever is speaking.",
    },
    "ai-visuals": {
      title: "Virtual scenes",
      promise: "No footage, no photos — every scene is AI-generated for your talk.",
      inputScenario: "For: talk audio",
      promptTemplate:
        "Turn my talk into a short video with AI-generated scenes.",
    },
  },
  // @-mention system (MENTIONS §4): picker copy and type names.
  skills: {
    external: "External Skill",
    builtin: {
// Skills are internal video creation methods, not user-installed products.
      "promo-video": {
        name: "Promotional video",
        shortName: "Promotional video",
        description: "Create a grounded promotional video from your copy, website, images, footage, brand, and sound.",
      },
      "talking-head-video": {
        name: "Talking-head motion video",
        shortName: "Talking-head motion",
        description: "Shape real footage into a vertical video with timed captions.",
      },
      "text-animation": {
        name: "Text animation video",
        shortName: "Text animation",
        description: "Turn your exact copy into editable native text motion.",
      },
      "knowledge-explainer": {
        name: "Knowledge explainer video",
        shortName: "Knowledge explainer",
        description: "Turn knowledge copy into an explainer with aligned narration, word-timed captions, and explanatory drawings.",
      },
    },
  },
  videoPresets: {
    "caption-phrases": { name: "Caption phrases" },
    "text-reveal": { name: "Text reveal" },
    "text-impact": { name: "Word impact" },
    typewriter: { name: "Typewriter" },
    "keyword-fill": { name: "Keyword highlight" },
    "word-cycle": { name: "Word cycle" },
    "claim-layout": { name: "Claim layout" },
    "highlight-sweep": { name: "Highlight sweep" },
    "path-underline": { name: "Path underline" },
    callout: { name: "Callout" },
    "flow-steps": { name: "Flow steps" },
    "comparison-columns": { name: "Comparison columns" },
    "card-stack": { name: "Card stack" },
    "list-reveal": { name: "List reveal" },
    "notification-stack": { name: "Notification stack" },
    "title-lockup": { name: "Title lockup" },
  },
  mentions: {
    pickerEmpty: "No matches",
    remove: "Remove mention",
    regionChip: "{{time}} · {{width}}×{{height}}px",
    regionText: "[selected region: x={{x}}, y={{y}}, width={{width}}px, height={{height}}px; source={{sourceWidth}}×{{sourceHeight}}px; media_time={{time}}]",
    types: {
      asset: "Asset",
      output: "Output",
      workflow_step: "Step",
    },
    fileType: {
      video: "Video",
      audio: "Audio",
      image: "Image",
      document: "Document",
    },
  },
  projects: {
    title: "Projects",
    search: "Search",
    searchPlaceholder: "Search projects...",
    sort: {
      label: "Sort",
      byField: "Sort by",
      byUpdated: "Last modified",
      byCreated: "Creation date",
      order: "Order",
      desc: "Newest first",
      asc: "Oldest first",
    },
    new: "New Project",
    dialogTitle: "New Project",
    dialogDesc: "Pick a persona and enter project info to start turning what you already have into reusable content.",
    labelTitle: "Title",
    titlePlaceholder: "e.g. AI Safety Governance Framework — EU Compliance Perspective",
    labelEvent: "Event name (optional)",
    eventPlaceholder: "e.g. 2026 Europe AI Governance Summit",
    labelPersona: "Persona",
    personaPlaceholder: "Select a persona",
    labelLanguage: "Source language",
    langZh: "Chinese",
    langEn: "English",
    emptyTitle: "No projects yet",
    emptyDesc: "Create your first project and turn your material into social posts, quote cards, articles, and more.",
    noSearchResults: "No projects match your search.",
    noEvent: "No event set",
    deleteConfirm: "Delete this project?",
    status: {
      uploading: "Uploading…",
      processing: "Generating…",
    },
    menuMore: "More actions",
    rename: "Rename",
    renameTitle: "Rename project",
    renamePlaceholder: "Project name",
    deleteDesc: "\"{{title}}\" and all its clips, posts and conversations will be permanently deleted.",
    selection: {
      count: "{{count}} selected",
      delete: "Delete",
      clear: "Clear selection",
      toggle: "Select project",
      deleteConfirm: "Delete {{count}} projects?",
      deleteDesc:
        "The selected projects and all their clips, posts and conversations will be permanently deleted.",
    },
  },
  projectMenu: {
    open: "Project menu",
    backToProjects: "Back to projects",
    backShort: "Projects",
  },
  projectHeader: {
    chat: "Chat",
    canvas: "Canvas",
  },
  personas: {
    title: "Personas",
    subtitle: "Manage personas and their style profiles",
    new: "Create Persona",
    dialogTitle: "Create Persona",
    dialogDesc: "Add a persona, then upload assets to generate a style profile.",
    labelName: "Name",
    labelTitle: "Title",
    emptyTitle: "No personas yet",
    emptyDesc: "Create your first persona and upload past assets to build a style profile.",
    noTitle: "No title set",
    language: "Language: {{lang}}",
  },
  personaDetail: {
    tabPersona: "Style Profile",
    tabMaterials: "Assets ({{count}})",
    tabSkin: "Skin",
    personaTitle: "Style Profile",
    personaDesc: "The persona's style profile, used to guide AI content generation",
    generate: "Generate from Assets",
    generating: "Generating...",
    saveChanges: "Save Changes",
    tone: "Emotional tone",
    sentenceStyle: "Sentence style",
    addItem: "Add",
    emptyList: "None yet",
    removeItem: "Remove",
    editItem: "Edit",
    overview: {
      voice: "Voice",
      skin: "Skin",
      skinDefault: "Default",
      skinCustom: "Custom",
      materials: "Assets",
      calibrated: "Last generated",
      never: "Not yet",
    },
    fields: {
      core_values: "Core values",
      favorite_metaphors: "Favorite metaphors",
      typical_hooks: "Typical hooks",
      avoid_words: "Words to avoid",
    },
    tones: {
      rational: "Rational",
      passionate: "Passionate",
      gentle: "Gentle",
      sharp: "Sharp",
      humorous: "Humorous",
    },
    emptyPersona: "No persona yet. Upload assets on the Assets tab, then click generate.",
    pastMaterials: "Past Assets",
    pastMaterialsDesc: "Upload past transcripts, articles, etc. to help the AI learn the style",
    noMaterials: "No assets uploaded yet.",
    charsExtracted: "{{count}} chars extracted",
    noText: "No text extracted",
    uploadedAt: "Uploaded {{date}}",
    notFound: "Persona not found",
    msgUpdated: "Persona updated",
    msgGenerated: "Persona generated successfully",
    msgUploaded: "Asset uploaded",
    msgDeleted: "Asset deleted",
    deleteConfirm: "Delete this asset?",
    deleteDesc: "\"{{title}}\" will be permanently deleted.",
    rename: "Rename",
    renameTitle: "Rename asset",
    renamePlaceholder: "Asset name",
    uploading: "Uploading...",
    contentStrategyTitle: "Content Strategy",
    contentStrategyDesc: "How this persona sounds and who they speak to",
    audience: "Target audience",
    audiencePlaceholder: "e.g. academic researchers",
    guidelines: "Content guidelines",
    guidelinesPlaceholder: "e.g. avoid jargon, keep paragraphs short",
    cta: "Default CTA",
    ctaPlaceholder: "e.g. Read the full paper →",
    voice: {
      title: "Voice",
      desc: "The voice sample bound to this persona.",
      auto: "Auto",
      autoDesc: "Use each project's own audio",
      mine: "My voice sample",
      noSample: "No sample uploaded",
      sampleMissing: "Sample no longer available",
      stock: "System voice",
      upload: "Upload sample",
      replace: "Replace",
      msgUpdated: "Voice updated",
    },
    skin: {
      title: "Skin",
      desc: "The default look of this persona's clips: captions, title, intro/outro, music.",
      save: "Save skin",
      reset: "Reset to default",
      msgSaved: "Skin saved",
      msgReset: "Skin reset to default",
      groups: {
        caption: "Captions",
        title: "Title",
        intro: "Intro",
        outro: "Outro",
        music: "Music",
      },
      caption: {
        font: "Font",
        size: "Size",
        color: "Color",
        customColor: "Custom color",
        style: "Style",
      },
      titleCard: {
        size: "Size",
        hint: "The hook line is generated per clip; drag the Title marker in the preview to position it.",
      },
      introOutro: {
        type: "Type",
        kinds: {
          text: "Text",
          image: "Image",
          video: "Video",
        },
        introText: "Intro text",
        introPlaceholder: "This talk is from…",
        outroText: "Outro text",
        outroPlaceholder: "Follow for more insights",
        uploadImage: "Upload image",
        uploadVideo: "Upload video",
        duration: "Duration (seconds)",
      },
      music: {
        enable: "Background music",
        gain: "Volume",
        library: "Music library",
        empty: "No music pieces yet",
        play: "Play preview",
        pause: "Pause preview",
        generate: "Generate new music",
        generatePrompt: "e.g. cinematic strings, hopeful, no vocals",
        titlePlaceholder: "Track title (optional)",
        moods: {
          calm: "Calm",
          uplifting: "Uplifting",
          corporate: "Corporate",
          none: "None",
        },
      },
      preview: {
        demo: "Demo",
        hint: "Hover the Title / Caption text to reveal its marker — drag to move, drag a corner to resize.",
        musicOn: "Music on",
        musicOff: "Music off",
      },
    },
  },
  projectDetail: {
    back: "Back",
    status: "Status",
    persona: "Persona",
    notGenerated: "Not generated",
    unknown: "Unknown",
    sourceMaterials: "Source Materials",
    generate: "Generate",
    outputLanguage: "Language:",
    linkedinPosts: "Social posts",
    quoteCards: "Quote cards",
    downloadCard: "Download image",
    carousel: "Carousel",
    slideLabel: "{{index}}/{{total}}",
    summary: "Summary",
    blog: "Blog post",
    jobRunning: "Generating",
    jobFailed: "Generation failed",
    renderFailed: "Render failed",
    generating: "Generating...",
    uploadTranscript: "Upload file",
    uploading: "Uploading...",
    uploadHint: "Upload a transcript, slides, audio, video, or images — clips render from audio/video or an image audiogram",
    noMaterials: "No transcript uploaded yet.",
    generatedClips: "Generated assets ({{count}})",
    titleOptions: "Title options",
    titlePerLine: "One title per line",
    bgm: "BGM",
    score: "Score",
    scriptShots: "Content sections",
    preview: "Preview",
    openEditor: "Open editor",
    visual: "Visual: {{value}}",
    edit: "Edit",
    save: "Save",
    cancel: "Cancel",
    editClip: "Edit clip",
    editDerivative: "Edit content",
    exportAll: "Export all",
    exporting: "Exporting...",
    exportFailed: "Export failed",
    exportSuccess: "Export ready",
    noContentToExport: "No content to export",
    charsExtracted: "{{count}} chars extracted",
    noText: "No text extracted",
    processing: "Processing...",
    processingFailed: "Processing failed",
    retry: "Retry",
    uploadedAt: "{{type}} · Uploaded {{date}}",
    notFound: "Project not found",
    msgUploaded: "Transcript uploaded",
    msgDeleted: "Transcript deleted",
    msgGenerated: "Generated {{count}} assets",
    msgSaved: "Saved",
    deleteConfirm: "Delete this asset?",
  },
  clipEditor: {
    back: "Back",
    title: "Clip editor",
    save: "Save",
    conflictReload: "This clip was modified elsewhere — your unsaved edits were discarded and the latest version loaded.",
    export: "Export video",
    rendering: "Rendering...",
    renderFailed: "Render failed",
    rendered: "Rendered",
    noRenderSpec: "This clip has no renderable video (text-only / no source video)",
    transcript: "Transcript",
    transcriptHint: "Click a word to fix · delete a line to cut",
    noCaptions: "No captions",
    deleteLine: "Delete this line",
    aspect: "Aspect",
    captionStyle: "Caption style",
    captionLanguage: "Caption language",
    translating: "Translating...",
    dubLanguage: "Voice dub",
    dubbing: "Dubbing...",
    dubOff: "Off",
    musicToggle: "Music",
    musicTrack: "Track",
    musicTrackNone: "None",
    musicGain: "Volume",
    titleToggle: "Title toggle",
    titlePlaceholder: "Title / hook text",
    trim: "Trim",
    reframePan: "Horizontal pan",
    reframeZoom: "Zoom",
    staleTrack: {
      dub: "voice dub",
    },
    staleTracks:
      "The {{tracks}} no longer matches this edit — regenerate it when you're ready.",
  },
  languages: {
    zh: "Chinese",
    en: "English",
    fr: "French",
    de: "German",
    es: "Spanish",
    it: "Italian",
  },
  // Caption style labels — one entry per CAPTION_PRESETS member
  // (@repurposer/clip captions.ts); both style selectors derive their
  // options from the catalog and label them from here.
  captionPresets: {
    "clean-bottom": "Clean bottom",
    "karaoke-highlight": "Word highlight",
    "fade-in": "Fade in",
    "pop-in": "Pop in",
    "slide-up": "Slide up",
    stacking: "Stacking",
  },
  results: {
    title: "Results",
    prompt: "Original prompt",
    dock: {
      focus: "Working on: {{name}}",
      // The hidden state (2026-09-02 形态机): the user's gesture folds the
      // dock to a bottom-right logo dot; agent speech / questions / focus
      // recall it.
      hide: "Hide chat",
      show: "Show chat",
      // The right-docked panel's slim header label (2026-09-06 两形态机).
      panelTitle: "Chat",
      // The panel's geometry toggle (2026-09-06, FLORA "Dock panel" parity):
      // float = frosted card over the full-bleed canvas (default); docked =
      // flush right edge full-height, still frosted.
      dockPanel: "Dock panel",
      floatPanel: "Float panel",
      // The dock's resident disclaimer (ADR-051) — names the real risk
      // point: content about to go out, not factual Q&A. ABOVE the input
      // container since the 2026-09-06 FAUNA-parity ruling, hidden with
      // the input on the question morph.
      honesty: "Rookie Cut can make mistakes — review before you publish.",
    },
    // Canvas product-card chrome (ADR-041 D5): the always-on action band's
    // labels. (No "preview" — the video plays inline, the hover expand opens
    // the big player; 2026-08-16 走查拍板.)
    canvas: {
      download: "Download",
      publish: "Publish",
      // The ⋯ menu (node business, 2026-08-17 走查拍板): open the big view /
      // point the chat dock at this node; assets also offer reprocess.
      open: "Open",
      focusNode: "Point it out in chat",
      reprocess: "Reprocess",
      more: "More actions",
      // The graph canvas's document node (ADR-057): the transcript /
      // research brief are the type's named instances; generic documents
      // get the plain label. (The plan document de-stamped — v4.2 C1-b.)
      transcript: "Transcript",
      researchBrief: "Research brief",
      // 两站拆分的文档站 (ADR-072, spec.role-derived — the doc station
      // never carries a builder summary; its cue artifact is the content).
      translationDoc: "Translation",
      dubScriptDoc: "Dub script",
      document: "Document",
      // 词表 v3 fallback labels (ADR-076, C1 休眠键): a node's TYPE name
      // when it carries no builder/LLM summary — generic medium words,
      // never business names (业务身份 = spec.summary / spec.tool 的座位).
      nodeType: {
        text: "Text",
        table: "Table",
        image: "Image",
        video: "Video",
        audio: "Audio",
      },
      // 状态原地表达 (ADR-057 §5 — state speaks in place, the caption's
      // right slot stays empty): the un-run node's dashed region reads its
      // own quotation; queued / skipped / failed / stale are quiet labels.
      draftBody: "Generated when it runs",
      estimateSingle: "≈ {{count}} credits",
      estimateRange: "≈ {{low}}–{{high}} credits",
      // 估价诚实面 (2026-09-10): unquoted nodes in the fold (transform
      // chains price when their clips exist, mid-run) — never promise "≈ 0".
      estimateOpen: "≈ {{count}}+ credits",
      estimateRangeOpen: "≈ {{low}}–{{high}}+ credits",
      estimateAtRun: "Priced at run time",
      queued: "Queued",
      skipped: "Skipped",
      runFailed: "Run failed",
      stale: "Rerun available",
      // The card-face program region (ADR-057 §5): generator/agent nodes
      // read their prompt here (processor nodes read params as fact chips).
      promptLabel: "Prompt",
      // K4 direct edit: while drafting the meta label owns the state; on
      // send the pricing confirmation anchors at the node (受影响子图 =
      // the node ∪ its downstream, priced by the fold of their quotes;
      // balance = the soft compare, 422 stays the fact source).
      promptEditing: "Prompt — editing",
      confirmBlastSingle: "Rerun this node",
      confirmBlast: "Rerun {{count}} nodes",
      confirmStart: "Confirm & run",
      // Canvas navigation controls (explore surfaces, 2026-08-19 — the
      // project page's top-right swap: app chrome out, canvas controls in;
      // 2026-09-28 the pill opens a zoom menu: steps / fit / fixed levels,
      // ⌘+/⌘-/⌘0 live while the pointer is over the canvas).
      zoomMenu: "Zoom",
      zoomIn: "Zoom in",
      zoomOut: "Zoom out",
      zoomFit: "Fit to window",
      zoomToPct: "Zoom to {{pct}}%",
      // The asset card's transcript section (ADR-113 — the transcript is the
      // asset's content layer, never a node): the empty-truth face (ASR
      // completed with zero words), the truncation honesty marker, and the
      // edit affordance (overlay-only — the source layer never moves, C4).
      transcriptEmpty: "Nothing transcribable was found in this material",
      transcriptTruncated: "Only the first part of the timeline is shown",
      editTranscript: "Edit transcript",
      // The deliverable card's track stack (ADR-113 §4 — 成片轨道栈):
      // read-only inspection lanes (the kept segments / the caption
      // sentences, both on the output axis) + the modifier presence strip.
      // The segment label's time range arrives preformatted from the server
      // (the client never formats time).
      videoTrack: "Video track",
      textTrack: "Text track",
      trackSegment: "Segment {{n}} · Source {{src}}",
      // The L1 hover chip's two lines (ADR-115 信息秩三分): the block's own
      // name, then its two preformatted ranges on the output/source axes.
      trackSegmentTitle: "Segment {{n}}",
      trackSegmentOut: "Output {{out}} · Source {{src}}",
      modifierMusic: "Music",
      modifierDub: "Dub",
      // The product dossier (2026-09-06, FLORA node-detail parity): a product
      // click summons it under the zoom pill — 出生证明 rows only, read-only
      // facts (修订只经 chat; FLORA's inline parameter editing stays unported).
      inspector: {
        stepLabel: "Step",
        estimateLabel: "Quote",
        spentLabel: "Charged",
        durationLabel: "Duration",
        createdLabel: "Created",
        languageLabel: "Language",
        sourceLabel: "Source",
        sourceFull: "Full source",
        rangeLabel: "Range",
        specLabel: "Spec",
        modelsLabel: "Models",
        close: "Close details",
      },
      // Render failure projected onto the product card in place (never a
      // separate node); the retry channel is the chat dock (D8). An active
      // render speaks through the BrandLoader alone — no status line.
      renderFailed: "Render failed — ask below to retry.",
      // 选区引用 (2026-09-11 — 段落级指认): the pill a text selection on a
      // product card offers — the pin rides into the dock as an @output chip
      // carrying the quoted passage; the agent revises THAT passage.
      quotePassage: "Quote this",
      // Transcript 卡内就地编辑 (Workspace 合同 v4.2 C4): the edit-mode-only
      // reset — clears the user's edited overlay, showing the source layer.
      resetToSource: "Reset to source",
      // Hover media affordances: expand (top-left) opens the lightbox;
      // sound (top-right) flips the inline video's ambient mute.
      expand: "Expand",
      mute: "Mute",
      unmute: "Unmute",
      // The card-face program region's send button (ADR-057 K4 direct edit
      // — confirmed through the pricing card, never a new channel).
      reviseSend: "Send revision",
      // Version pager (ADR-051 F2 — 变体分页): the fork-family flipper in
      // the card's action band — a separate pill, never merged with the
      // items switcher (variants = item switching ≠ version switching).
      versionOf: "{{current}} of {{total}}",
      versionPrev: "Previous version",
      versionNext: "Next version",
    },
    // The media lightbox's info column (left of the media).
    lightbox: {
      prompt: "Prompt",
    },
    stepper: {
      transcribing: "Transcribing your media…",
      queued: "Queued, starting soon…",
      analyze: "Analyzing your uploads…",
      plan: "Planning the content…",
      prepare: "Preparing generation…",
      selecting_segments: "Picking highlight moments…",
      building_specs: "Assembling your clips…",
      writing_copy: "Writing your copy…",
      researching: "Researching the topic…",
      generating_image: "Generating quote card images…",
      ready_to_render: "About to start rendering…",
      removing_fillers: "Removing filler words…",
      reframing_clips: "Reframing your clips…",
      adding_music: "Scoring your clips…",
      translating_captions: "Translating captions…",
      dubbing: "Dubbing your voice…",
    },
    clipNotRendered: "Click to render this clip.",
    topPick: "Top pick",
    qualityNeedsReview: "Needs review",
    scoreLabel: "Pick score",
    scoreReason: "Why this clip",
    noQuote: "No quote text available.",
    noSlides: "No slides available.",
    generating: "Generating assets...",
    generatingTitle: "Generating assets",
    polling: "Checking generation status...",
    clipDetail: {
      publishTab: "Publish",
      socialCaptionTab: "Social caption",
      topicTab: "Topic",
      transcriptTab: "Transcript",
      title: "Title",
      caption: "Caption",
      hashtags: "Hashtags",
      copyTitle: "Copy title",
      copyCaption: "Copy caption",
      copyHashtags: "Copy hashtags",
      download: "Download",
      editClip: "Edit clip",
      generateCover: "Generate cover",
      close: "Close",
      noTranscript: "No transcript available.",
    },
  },
  chat: {
    scrollToStart: "Scroll to start",
    scrollToEnd: "Scroll to end",
    assistantLabel: "Rookie Cut",
    userLabel: "You",
    thinking: "Thinking...",
    thinkingPhases: {
      capturing: "Reading the pages…",
      storyboarding: "Designing the storyboard…",
      storyboard_revision: "Adjusting the storyboard…",
    },
    /** The now-line for the closing review's generation window (a terminal
     * run's closing speech is an LLM call the trigger poll picks up — an
     * in-flight LLM call always owns a now-line). The copy says the results
     * are being gathered — never that the video is still rendering or being
     * watched. */
    closingReview: "Gathering the results…",
    /** Legacy drafting activity replay: the span's SETTLED row — the log
     * register (verb-object + fact, no progressive), the same 三寄存器 law
     * as the material reading family. */
    storyboard: {
      draftingDone: "Drafted the storyboard",
    },
    /** The now-line's material reading rows (2026-09-24 user ruling —
     * thinking IS the activity row's empty state): assets mid-processing →
     * reading (the filename interpolates). The *Done / *Failed forms are the
     * PERSISTED settled rows (the pipeline writes or reuses one activity
     * row, the replay renders the past tense); Progress carries "N/M".
     * Verb fork (2026-09-27 批「动词」): the verb follows the asset type —
     * video → watch / audio → listen / text & others → read; multi-file
     * batches fall back to the neutral "processing". Both synthesis points
     * fork alike (the ChatDock now-line reads asset.type, the replay reads
     * the persisted beat's intent.asset_type).
     * Stage fork (ADR-095 §2): a lone in-flight asset with a known
     * processing_stage speaks the process truth instead — asr →
     * transcribing, speaker_map/prosody → understandingAsset (the
     * transcribe/understand vocabulary the run stepper shares); unknown or
     * absent stages keep the verb line. Register law (三寄存器): the live
     * rows are the transient surface (the progressive form is legal there);
     * the persisted rows are the activity LOG — verb-object + fact suffix,
     * no person, no progressive, no conversational tone. understandingDone
     * stays for the LEGACY beat replay (ADR-102 retired the beat's producer
     * — old conversations still render their archived rows). */
    material: {
      reading: "Reading {{name}}…",
      reading_video: "Watching {{name}}…",
      reading_audio: "Listening to {{name}}…",
      readingMany: "Processing {{count}} files…",
      transcribing: "Transcribing {{name}}…",
      understandingAsset: "Understanding {{name}}…",
      readingDone: "Read {{name}}",
      readingDone_video: "Watched {{name}}",
      readingDone_audio: "Listened to {{name}}",
      readingDoneProgress: "Read {{name}} ({{count}}/{{total}})",
      readingDoneProgress_video: "Watched {{name}} ({{count}}/{{total}})",
      readingDoneProgress_audio: "Listened to {{name}} ({{count}}/{{total}})",
      readingFailed: "Failed to read {{name}}",
      readingFailed_video: "Failed to watch {{name}}",
      readingFailed_audio: "Failed to listen to {{name}}",
      understandingDone: "Understood your material",
    },
    /** The material reading family's settled category form (ADR-110 修订
     * — 归档归类目): name-free — the instance name is the live phase's
     * speech, settled surfaces speak the category. The verb fork mirrors
     * the reading family (video/audio off the row key's own suffix,
     * web_page off the beat's asset_type). */
    materialCategory: {
      reading: "Read the material",
      reading_video: "Watched the video",
      reading_audio: "Listened to the audio",
      reading_webPage: "Read the page",
    },
    /** The perception family's inspecting chatter (T2b): a read ACTIVITY's
     * active-frame label while a read tool runs (Phase 3 Batch B ③ moved the
     * family from the retired System Status row to the Activity Stream —
     * same registry, same keys). Keys ride the server registry
     * (app/chat/perception) — the tool NAME never surfaces; first-person
     * whisper register. */
    inspecting: {
      outputSpec: "Reading the current settings…",
      node: "Reading the card's full program…",
      understanding: "Reading your material…",
      captionStyles: "Browsing the caption styles…",
      music: "Searching the music library…",
      runStatus: "Checking the run's progress…",
      runHistory: "Reading the run history…",
      pendingPlan: "Reading the plan waiting for confirmation…",
      graph: "Reading the canvas…",
      segment: "Reading the segment…",
      asset: "Looking at the asset…",
      projectMedia: "Listing the project's media…",
      craftSkeleton: "Reading the reference's style breakdown…",
      artifact: "Reading the card's details…",
      webPage: "Reading the page…",
      webSearch: "Searching the web…",
      videoVersion: "Reading the saved version…",
    },
    /** The work-session family (iter-2 ⑥, N-57): the discovery chain's
     * user-safe beats — `searching` rides the read frame (active + done
     * mirror, the inspecting→inspectingDone 同律 at this family's shape);
     * the three milestones fire once at each door success, born-completed,
     * with the artifact count as the only interpolation (user-safe pure
     * count — never params / excerpts / reasoning). */
    explore: {
      searching: "Searching the transcript…",
      searchingDone: "Searched the transcript",
      candidatesReady: "Found {{count}} candidate sections",
      selectsReady: "Picked {{count}} sections",
      plansReady: "Structured {{count}} plans",
    },
    /** Candidate Surface (Workspace 合同 v4.2 C8-c, 2026-09-26): the chat
     * candidate card's expand toggle — default three recommendations, the
     * whole set unfolds on demand (推荐样本，不是只能选 3 个). */
    candidates: {
      more: "{{count}} more",
      less: "Show less",
      selected: "Selected",
    },
    sfx: {
      play: "Play sound",
      pause: "Pause sound",
      seek: "Seek audio",
      previewUnavailable: "Audio preview unavailable",
    },
    preparationProgress: {
      pictureScene: "Preparing storyboard scene {{count}}…",
      voiceScene: "Recording narration for scene {{count}}…",
      visual_assets: "Preparing storyboard images…",
      imagesProcessed: "Preparing storyboard images · {{count}} processed…",
      speech_media: "Recording scene narration…",
      audio_snapshot: "Saving the narration recording…",
      alignment_request: "Requesting narration alignment…",
      music_synthesis: "Generating the score…",
    },
    audio: {
      retry: "Retry playback",
      play: "Play audio",
      pause: "Pause audio",
      narration: "Narration",
      music: "Background music",
      loading: "Preparing audio playback…",
      unavailable: "Audio is not ready to play",
    },
    /** The Activity Stream's milestone copy (ADR-087 §3 Phase 2): the active
     * frame carries the progressive form and the completed frame the
     * past-tense form. Failed rows keep their honest active-form key;
     * cancelled attempts retire from the visible walk instead of becoming
     * crossed-out history. kind is a user-semantic category — never a tool
     * name. */
    /** 2026-09-25 copy batch (user ruling — the machine-status register
     * retired): plain words for the work in flight. The draft kind speaks
     * two faces by tool — proposing a plan / editing existing work (declared
     * by ChatTool.presentation). Draft / run spans are
     * ACTIVE-only (落定即退役 — draft 2026-09-28, extended to run
     * 2026-09-29): the settled receipt retired, the docked plan card / the
     * start speech + RunTaskList receipt is the evidence, so no
     * draftDone/editDone/runDone keys exist (the storyboard pair below is
     * the ONE exception — 分镜不是开工, its settle persists). The repair pair is
     * terminal-only (the rework span opens silently — no active frame):
     * repair fires on the failed terminal (retries exhausted / the turn
     * failed), repairDone on the redirected terminal (a guardrail steered
     * the turn's form to another tool) — work facts, never the model's
     * self-reflection. */
    activity: {
      draft: "Putting the plan together…",
      edit: "Making the change…",
      run: "Getting started…",
      repair: "Couldn't get it done this time",
      repairDone: "Changed approach",
      /** The storyboard span's pair (2026-10-17 user ruling — 分镜不是开工):
       * the ONE draft-family span whose settle persists (its markdown
       * message is the deliverable, no dock card absorbs the beat) — the
       * done form renders in the fold's category decomposition. The EDIT
       * pair is the patch variant (a targeted edit riding the same span):
       * it says adjust, never a fresh design. */
      storyboard: "Designing the storyboard…",
      storyboardDone: "Designed the storyboard",
      storyboardEdit: "Adjusting the storyboard…",
      storyboardEditDone: "Adjusted the storyboard",
      /** The video family's pairs (ADR-145 phase B): the same span anatomy
       * as the storyboard span — design and revision speak their own
       * vocabularies. */
      videoDesign: "Designing the video storyboard…",
      videoDesignDone: "Designed the video storyboard",
      skillRead: "Reading the Skill method…",
      skillReadDone: "Read the Skill method",
      skillPreview: "Checking the Skill preview…",
      skillPreviewDone: "Checked the Skill preview",
      importMusic: "Importing music…",
      imageUnavailable: "Image unavailable",
      recordVoice: "Recording narration…",
      recordVoiceDone: "Recorded narration",
      bindClipSource: "Binding fixed media",
      bindClipSourceDone: "Bound fixed media",
      insertAudio: "Adding audio…",
      insertAudioDone: "Added audio",
      visualAssets: "Preparing storyboard images…",
      checkFixedImages: "Checking existing storyboard images…",
      readFixedImages: "Reading the verified storyboard images…",
      visualAssetsDone: "Checked visual assets",
      readHistory: "Reading conversation history…",
      readHistoryDone: "Read conversation history",
      viewWebPage: "Viewing the webpage…",
      viewWebPageDone: "Viewed the webpage",
      videoMaterials: "Preparing video materials…",
      videoMaterialsDone: "Prepared video materials",
      brandAnalyze: "Analyzing the brand evidence…",
      brandAnalyzeDone: "Analyzed the brand evidence",
      videoCapturePlan: "Capturing the planned webpage state…",
      videoCapturePlanDone: "Captured the planned webpage state",
      videoRevise: "Adjusting the video storyboard…",
      inspectClips: "Inspecting clips",
      inspectClipsDone: "Checked the clips",
      inspectClip: "Inspecting the clip",
      inspectClipDone: "Inspected the clip",
      removeClip: "Removing the clip",
      removeClipDone: "Removed the clip",
      trimClip: "Trimming the clip",
      trimClipDone: "Trimmed the clip",
      moveClip: "Moving the clip",
      moveClipDone: "Moved the clip",
      translate: "Repositioning the object",
      translateDone: "Repositioned the object",
      scale: "Scaling the object",
      scaleDone: "Scaled the object",
      splitClip: "Splitting the clip",
      splitClipDone: "Split the clip into two parts",
      deliverVideo: "Delivering the reviewed video",
      deliverVideoDone: "Delivered the reviewed video",
      setKeyframe: "Adjusting a keyframe",
      setKeyframeDone: "Adjusted a keyframe",
      extendStill: "Extending the closing still",
      extendStillDone: "Extended the closing still",
      exportVideo: "Exporting MP4",
      exportVideoDone: "MP4 exported",
      previewRange: "Checking the preview",
      createVideo: "Creating the first version",
      createVideoDone: "Saved the first version",
      previewRangeDone: "Checked the local preview",
      videoReviseDone: "Adjusted the video storyboard",
      videoReview: "Reviewing the delivered video…",
      videoReviewDone: "Reviewed the delivered video",
      videoDraftScene: "Checking Scene {{count}}…",
      videoDraftSceneDone: "Checked Scene {{count}}",
      videoDraftJoin: "Checking Scene {{count}} and its join from the previous Scene…",
      videoDraftJoinDone: "Checked Scene {{count}} and its join from the previous Scene",
      videoDraftRecheck: "Rechecking Scenes 1–{{count}}…",
      videoDraftRecheckDone: "Rechecked Scenes 1–{{count}}",
      videoSave: "Saving the editable version…",
      videoSaveDone: "Saved the editable version",
      sfxSearch: "Finding sound effects…",
      sfxSearchDone: "Found sound effects",
      sfxImport: "Importing the selected sound…",
      sfxImportDone: "Imported the selected sound",
      musicSearch: "Finding background music…",
      musicSearchDone: "Found background music",
      musicSelection: "Selecting the chosen music…",
      musicSelectionDone: "Selected the music",
      mediaPermission: "Requested permission to generate media",
      musicPrepare: "Preparing the electronic score…",
      musicPrepareDone: "Prepared the electronic score",
      upload: "Uploading video…",
      uploadDone: "Uploaded video",
      narrationPrepare: "Preparing narration alignment…",
      narrationPrepareDone: "Prepared the narration request",
      narrationRead: "Reading narration alignment…",
      narrationReadDone: "Read the narration alignment",
      narrationAnnotate: "Annotating narration…",
      narrationAnnotateDone: "Annotated the narration",
    },
    activityReceipt: {
      sampledFrames: "Sampled frames",
      observed_issue: "Observed issue · {{frame}}",
      aesthetic_suggestion: "Aesthetic suggestion · {{frame}}",
      noFindings: "No content findings in the sampled frames",
      audioIssues: "Audio issues",
      checkedScope: "Review scope",
      checked: "Checked",
      notChecked: "Not checked",
      audio: {
        AUDIO_MISSING: "Expected audio is missing",
        AUDIO_DECODE_FAILED: "Audio could not be fully decoded",
        AUDIO_SILENT: "Expected audio is silent",
        AUDIO_QUIET: "Audio is quiet",
        AUDIO_CLIPPED: "Audio contains clipped samples",
      },
      scope: {
        actual_output_decoded: "Exact delivered video decoded",
        static_frames_checked: "Sampled still frames checked",
        deterministic_output_checks: "Deterministic output checks run",
        sampled_frame_signals_checked: "Sampled-frame signals checked",
        audio_signal_checked: "Audio signal checked",
        motion_and_transitions_checked: "Motion and transitions checked",
        audio_and_av_sync_checked: "Audio and audio-visual sync checked",
      },
      revision: {
        version: "Saved version {{version}}",
        settings: "Canvas settings · {{fields}}",
        addedScene: "Added scene · {{scene}}",
        removedScene: "Removed scene · {{scene}}",
        movedScene: "Moved {{scene}} · {{from}}s → {{to}}s",
        addedClip: "Added {{kind}} clip · {{clip}}",
        removedClip: "Removed clip · {{clip}}",
        updatedClip: "Updated {{clip}} · {{fields}}",
        transitions: "Updated transitions",
        kinds: {
          text: "text",
          image: "image",
          web: "web",
          video: "video",
          audio: "audio",
          shape: "shape",
          speech: "narration",
          generator: "Generator",
        },
        fields: {
          range: "time window",
          object: "content",
          animations: "animations",
          scene_id: "scene",
          source: "source",
          linked_group_id: "linked group",
        },
      },
      component: {
        title: "Component preview · {{clip}}",
        posterAlt: "Representative preview frame for {{clip}}",
        previewFrame: "Representative frame · {{frame}}",
        dynamicSamples: "Motion verified at frames · {{frames}}",
        fixedMedia: "Fixed media · {{digest}}",
      },
      sfx: {
        searchTopic: "Sound search · {{topic}}",
        candidate: "{{ordinal}} · {{title}} · {{duration}}s",
        imported: "Imported {{title}} · {{duration}}s",
        snapshot: "Imported audio · {{id}}",
      },
      music: {
        searchTopic: "Music library · {{topic}}",
        candidate: "{{ordinal}} · {{title}} · {{duration}}s",
        selected: "Selected {{title}} · {{duration}}s",
      },
    },
    /** The activity row's bounded expand detail (iter-3 S7, E7 诚实边界):
     * only the wire whitelist's fields — the raw count rides as a labeled
     * meta line (the duration joins inline, formatElapsed is the ONE copy). */
    activityMeta: {
      count: "Count: {{count}}",
    },
    /** The aggregate row (ADR-110 段聚合): a settled work segment folds
     * into ONE quiet total. Live `worked` time runs from the real work
     * boundary to first VISIBLE prose (or a prose-less terminal), then
     * freezes; replay without that client fact reports only the observable
     * activity span. Expanded rows are the foldCategories ×N decomposition.
     * `actionCount` is the honest fallback when no wall clock exists. */
    recordingGroup: "Preparing narration and music…",
    toolGroup: "{{count}} tool calls",
    toolName: {
      inspect_clip: "Inspect clip",
      inspect_timeline: "Inspect timeline",
      generate_voice: "Generate narration",
      generate_music: "Generate music",
      generate_image: "Generate image",
      insert_audio: "Insert audio",
      split_clip: "Split clip",
      remove_clip: "Remove clip",
      trim_clip: "Trim clip",
      move_clip: "Move clip",
      translate: "Move object",
      scale: "Scale object",
      preview_range: "Preview range",
    },
    callState: {
      provider_unknown: "Provider outcome unknown",
      queued: "Queued",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
      cancelled: "Stopped",
      not_executed: "Not executed",
      awaiting_authorization: "Awaiting approval",
    },
    activityFold: {
      workedWithoutTime: "Worked",
      worked: "Worked for {{elapsed}}",
      failed: "Couldn't finish this time · {{elapsed}}",
      actionCount: "{{count}} actions",
    },
    /** Video presentation companions: activity labels and the optional real
     * Generator preview. The visible storyboard itself is LLM Markdown. */
    videoStoryboard: {
      video: "Video",
      programPreview: "Program preview",
      programPreviewError: "The exact program preview could not be loaded; production has not been acknowledged.",
      pendingMedia: "Media required by this local preview is not ready; no production has started.",
      previewError: "This local preview could not be loaded.",
      title: "Storyboard",
      unavailable: "This storyboard version is no longer available.",
      scrub: {
        trigger: "Adjust text size",
        target: "Text",
        fontSize: "Font size",
        apply: "Apply",
        applyError: "The text size could not be saved. Your edit was rolled back.",
        conflict: "This video changed elsewhere. Reopen the current version before applying.",
        openCurrent: "Open current version",
        isolatedObject: "Isolated text preview; scene layout, occlusion and joins are not checked here.",
      },
    },
    /** Past-tense mirrors of the inspecting family — a read activity's
     * completed frames (chat.inspecting.* stays the active form; the keys
     * ride the server registry, this family mirrors it by prefix swap). */
    inspectingDone: {
      outputSpec: "Read the current settings",
      node: "Read the card's full program",
      understanding: "Read your material",
      captionStyles: "Browsed the caption styles",
      music: "Searched the music library",
      runStatus: "Checked the run's progress",
      runHistory: "Read the run history",
      pendingPlan: "Read the waiting plan",
      graph: "Read the canvas",
      segment: "Read the segment",
      asset: "Looked at the asset",
      projectMedia: "Listed the project's media",
      craftSkeleton: "Read the reference's style breakdown",
      artifact: "Read the card's details",
      webPage: "Read the page",
      webSearch: "Searched the web",
      videoVersion: "Read the saved version",
    },
    /** The inspecting family's failed-form mirror (ADR-102 §5): the read
     * activity's failed-frame label when the read's target is unreadable —
     * the done family's honest counterweight, never a silent lie. */
    inspectingFailed: {
      understanding: "Couldn't read the material",
    },
    completed: "Done",
    failed: "Sorry, I couldn't update this. Please try again.",
    /** The dead-stream reconcile's give-up row (2026-10-15): the pipe was
     * declared dead and abandoned, yet no answer row landed within the
     * reconcile window — the turn may still complete server-side; the
     * archive replay catches it on refresh. */
    connectionLost:
      "The connection dropped and no reply has landed yet — refresh in a moment to check.",
    /** Quiet settles for a dead question's click (2026-09-28 — the answer
     * endpoint's structured 409 codes; the click raced the question's own
     * settlement, so no error toast). */
    questionOutdated: "That question was replaced by a newer one — no answer needed.",
    questionAnswered: "That question was already answered.",
    /** Start recovery copy (2026-10-22 — backend-accepted, receipt-lost):
     * the Start answer's pipe died; the recovery re-reads the world
     * ORIGINAL QUESTION ROW FIRST (a newer dock never proves the start
     * failed) and says exactly ONE honest state — 已启动 / 尚未确认启动 /
     * 暂时无法确定, never an absolute claim it can't prove and never an
     * auto-retry (a second start is only ever the user's re-click, deduped
     * server-side). started → the run surface attaches (info);
     * unconfirmed → the pill restores (info — the request may still be
     * mid-flight); unknown → the state is unconfirmable right now
     * (error). */
    startRecovery: {
      started:
        "The connection dropped, but production had already started — progress is below.",
      unconfirmed:
        "The connection dropped before the start could be confirmed — the request may still be processing. Wait a moment, or start again (a duplicate is safely ignored).",
      unknown:
        "The connection dropped — couldn't confirm whether production started. Retry, or refresh to check.",
    },
    runFailed: "Run failed",
    /** Terminal completion lines retired 2026-09-24 (user ruling — they
     * duplicated the trigger turn's run_completed prose; ONE narrator now). */
    send: "Send",
    stop: "Stop",
    undoLastEdit: "Undo last edit",
    ops: {
      remove_range: "Cut range",
      set_trim: "Trim",
      set_title: "Set title",
      set_caption_style: "Caption style",
      set_music: "Music",
      set_crop: "Reframe",
      set_aspect: "Aspect ratio",
      set_caption_text: "Edit caption",
      restore_version: "Restore version",
    },
    choicePlaceholder: "Something else…",
    legacyStepSummaries: {
      uploaded: "Uploaded",
    },
    productionStages: {
      validate: "Validate approved version",
      fonts: "Prepare fonts",
      generator_media: "Generate visuals",
      speech_media: "Generate narration",
      visual_assets: "Prepare scene images",
      compile_spec: "Compile video specification",
      output_preparation: "Create output",
      output_resume: "Prepared output reuse",
      render_queue: "Submit to render queue",
      produce_video: "Producing your video…",
      prepare_narration: "Preparing narration…",
      render: "Render",
      upload: "Upload",
      delivery: "Delivery check",
      reuseSummary: "{{reused}} of {{total}} reused",
    },
    stepKinds: {
      prepare_visual_assets: "Preparing storyboard images…",
      prepare_visual_assetsDone: "Storyboard image preparation",
      prepare_narration: "Preparing scene narration…",
      prepare_narrationDone: "Scene narration preparation",
      prepare_music: "Preparing the score…",
      prepare_musicDone: "Score preparation",
      preprocess: "Analyzing your uploads…",
      persona_bootstrap: "Preparing your persona…",
      understand: "Understanding your material…",
      interrupt: "Waiting for your direction…",
      plan: "Planning the content…",
      render: "Rendering your video…",
      stills: "Extracting key frames…",
      video: "Processing your video…",
      add_music: "Scoring your clips…",
      verify: "Checking quality…",
    },
    qa: {
      q: "Q",
      a: "A",
      cancelled: "Cancelled — back to draft",
      superseded: "Superseded by a newer plan",
      expired: "Timed out — continued with the default",
      stopped: "Stopped generation",
    },
    retry: "Retry",
    edit: "Edit",
    regenerate: "Regenerate",
    render: "Render video",
    rendering: "Rendering...",
    translate: "Translate",
    copy: "Copy",
    copied: "Copied",
    // 锚卡 (flora-parity-ui ③ · ADR-118): the terminal receipt's static
    // product array — type words feed the name-missing fallback (「类型词 ·
    // 规格」, zero template backfill) + the text seat's word-count spec.
    anchorCards: {
      view: "View {{name}}",
      types: {
        video: "Video",
      },
      words: "~{{count}} words",
    },
    outputCard: {
      version: "v{{number}}",
    },
    outputViewer: {
      downloadError: "Download failed. Please try again.",
      title: "Delivered output",
      selectRegion: "Select region",
      referenceAsset: "Reference this asset",
      regionHint: "Drag to select a region of this frame",
      regionLoading: "Reading frame dimensions…",
      regionSummary: "{{time}} · source {{sourceWidth}}×{{sourceHeight}} · x{{x}} y{{y}} · {{width}}×{{height}}px",
      reselectRegion: "Reselect",
      referenceRegion: "Reference region",
      details: "Output details",
      zoomIn: "Zoom in",
      zoomOut: "Zoom out",
      unavailable: "Output unavailable",
      unavailableDetail: "This exact delivered Output is no longer available. No newer version has been substituted.",
    },
    uploadFile: "Upload file",
    uploading: "Uploading...",
    composerPlaceholder: "Describe what you want to generate...",
    composerFollowUpPlaceholder: "Ask a follow-up, e.g. 'make the hook shorter' or 'add German version'...",
    emptyStateSubtitle: "Upload the video or text from a talk, meeting or interview — we remember your content and style, and make whatever you ask for.",
    noResultsYet: "Results will appear here...",
    resultActions: {
      edit: "Edit",
      regenerate: "Regenerate",
      export: "Export",
    },
    recentChats: "Recent conversations",
    noRecentChats: "No conversations yet",
  },
  generationOverlay: {
    planVersion: "Plan v{{n}}",
    versionRestore: "Restore this version",
    versionRestored: "Plan v{{n}} restored — it's the current plan now.",
    // The editing state's @ candidates include assets and outputs; the first-
    // creation state has assets only. Both states expose the same / Skill picker.
    chatPlaceholder: "Use '@' to mention assets or outputs, '/' to use skills.",
    // Full form before the first run: the @ picker's candidates are assets only.
    chatPlaceholderAssets: "Use '@' to mention assets, '/' to use skills.",
    attachFiles: "Attach files",
    retryUpload: "Retry upload",
    removeAttachment: "Remove attachment",
    assetTypes: {
      video: "Video",
      audio: "Audio",
      image: "Image",
      slides: "Slides",
      transcript: "Transcript",
      file: "File",
    },
    stopped: "Generation stopped.",
    // 确认 pill (ADR-117 §4 — 画板 C): the confirm beat's only chrome, shown
    // exactly when the dock's stamp says a beat is owed. The label family:
    // bare verb (execution ask) / priced (credits ask · guardrail — the
    // number is the server fold's high end, never client-computed) /
    // deferred (the NULL-estimate family — never a fabricated number). The
    // click sends this label as an ordinary chat message through sendChat;
    // the next LLM turn decides whether to call start_run.
    confirmPillStart: "Start",
    confirmPillStartPriced: "Start · ~{{n}} credits",
    confirmPillStartDeferred: "Start · priced when it runs",
  },
  questionDock: {
    customize: "Customize this combination",
    bail: "Stop generation",
    skip: "Skip question",
    recommended: "Recommended",
    previous: "Previous",
    next: "Next",
    submit: "Submit answers",
    page: "{{current}} / {{total}}",
  },
  clipMenu: {
    more: "More actions",
    download: "Download",
    publishOnSocial: "Publish on Social",
    share: "Share",
    shareCopied: "Link copied",
  },
  login: {
    title: "Sign in to Rookie Cut",
    subtitle:
      "Enter your email and we'll send you a sign-in code — no password, and new accounts are created automatically.",
    emailLabel: "Email address",
    emailPlaceholder: "you@company.com",
    sendCode: "Email me a code",
    sending: "Sending...",
    enterCode: "Enter code",
    codeTitle: "Check your email",
    codeSubtitle:
      "Enter the 6-digit code we sent to <b>{{email}}</b>. It's valid for 10 minutes.",
    digitLabel: "Digit {{index}} of {{total}}",
    enterAllDigits: "Enter all 6 digits",
    verifyAndLogin: "Verify & sign in",
    verifying: "Verifying...",
    didntReceive: "Didn't get the email?",
    resendCode: "Resend code",
    resendIn: "Resend in {{count}}s",
    backToSignIn: "Back to sign in",
    sendFailed: "Couldn't send the code — check the address and try again",
    verifyFailed: "Invalid or expired code",
  },
  tour: {
    next: "Next",
    prev: "Back",
    skip: "Skip",
    done: "Done",
    stepOf: "Step {{current}} of {{total}}",
    composer: {
      assetsTitle: "Add your material",
      assetsDesc:
        "Video, audio, slides, photos, or a transcript — use whatever you have. You can also skip this and write your idea below.",
      promptTitle: "Say what to make",
      promptDesc:
        "Write the result you want. Use @ to point to an uploaded asset, then send it.",
      recipesTitle: "Start from a card",
      recipesDesc:
        "Choose Start creating on a card to fill the composer, then adjust the prompt for your material.",
    },
  },
  notifications: {
    title: "Notifications",
    empty: "You're all caught up",
    publishUnknown: "{{platform}} publication awaits verification",
    publishSucceeded: "Published to {{platform}}",
    publishFailed: "Couldn't publish to {{platform}}",
    channelExpired: "{{platform}} connection expired",
    openPost: "Open post",
    retry: "Retry",
    reconnect: "Reconnect",
    retryQueued: "Re-queued — we'll notify you when it's live",
    justNow: "just now",
    minutesAgo: "{{count}}m ago",
    hoursAgo: "{{count}}h ago",
    daysAgo: "{{count}}d ago",
  },
  publish: {
    title: "Publish",
    chooseChannels: "Choose channels",
    connect: "Connect",
    comingSoon: "Coming soon",
    titleLabel: "Title",
    captionLabel: "Post text",
    hashtagsLabel: "Hashtags",
    aiDisclosure:
      "This clip contains AI-generated media and will be labeled as AI-generated.",
    cancel: "Cancel",
    publishNow: "Publish now",
    publishing: "Publishing...",
    queued: "Publishing — you'll be notified when it's live",
    failed: "Couldn't create the publication",
    selectChannel: "Select at least one channel",
  },
  channels: {
    title: "Channels",
    subtitle: "Connect accounts to publish directly",
    connect: "Connect",
    disconnect: "Disconnect",
    connected: "Connected",
    expired: "Connection expired",
    reconnect: "Reconnect",
    comingSoon: "Coming soon",
    connectedToast: "{{platform}} connected",
    connectFailed: "Couldn't connect {{platform}}",
    disconnectedToast: "{{platform}} disconnected",
  },
  settings: {
    title: "Settings",
  },
  a11y: {
    toggleSidebar: "Toggle Sidebar",
    openSidebar: "Open sidebar",
  },
  // 质检环 (产物质量线期 3): human labels for the verify node's check ids —
  // the badge tooltip renders "<label>: <detail>".
  qualityChecks: {
    span_fidelity: "Clip matches its source span",
    quote_verbatim: "Quote is verbatim",
    language_match: "Language matches the target",
    avoid_words: "Avoided words",
    length_in_bounds: "Length in bounds",
    count_match: "Requested count produced",
    slide_count: "Slide count matches the plan",
    shot_dwells: "Shot pacing",
    caption_sync: "Caption sync",
    face_safe_area: "Faces clear of captions",
    emphasis_alignment: "Emphasis on the content peaks",
    repair_scope: "Repair stayed in scope",
    judge_quote_readability: "Quote reads standalone",
  },
}

export default en
export type Resources = typeof en
