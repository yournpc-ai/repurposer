const en = {
  common: {
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
    replayTour: "Replay tour",
    credits: "Credits",
    language: "Language",
    settings: "Settings",
    logout: "Log out",
    login: "Log in",
    guest: "Guest",
    new: "New",
    freePlan: "Free plan",
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
      desc: "After a plan is presented, whether it waits for your go-ahead.",
    },
    spending: {
      label: "Spending credits",
      desc: "Before a paid plan starts, whether to confirm once with the price.",
    },
    mode: { auto: "Automatic", ask: "Ask" },
    footnote:
      "The estimate is always shown with the plan. Unusually large or unquotable plans always ask once, whatever you set here.",
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
    /** The user-level shortfall grey row (BILLING §7, 2026-09-10) — strictly
     * two vocabularies with the provider's 402 line. Factual, no CTA: the
     * purchase entry is W11, so there is nothing to sell yet. */
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
    recent: "Recent activity",
    /** The SettingsDialog「积分」section (BILLING §7 展示主轴) — the
     * balance + ledger full-view seat, same two endpoints as the pill. */
    title: "Credits",
    subtitle: "Your balance and recent activity.",
    overview: "Overview",
    planFree: "Free trial",
    plansComing: "Paid plans coming soon",
    showingRecent: "Latest {{count}}",
    viewAll: "View all →",
    tx: {
      empty: "No transactions yet",
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
    subscription: "Subscription",
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
    nav: {
      features: "Features",
      pricing: "Pricing",
      faq: "FAQ",
      menus: {
        features: {
          items: {
            clips: {
              label: "Vertical clips",
              description: "Auto-cut, captioned, on-brand",
            },
            languages: {
              label: "Multi-language versions",
              description: "Native in six European languages",
            },
          },
          promo: {
            title: "How it works",
            description: "From raw material to published, in four steps.",
          },
        },
        faq: {
          items: {
            data: {
              label: "Where is my data stored?",
              description: "GDPR-ready — nothing trains third-party models",
            },
            upload: {
              label: "What can I upload?",
              description: "Video, audio, slides, photos, or a transcript",
            },
            languages: {
              label: "Which languages are supported?",
              description: "EN, FR, DE, ES, IT, NL — written natively",
            },
            autoPublish: {
              label: "Does anything get published automatically?",
              description: "No — nothing ships without your approval",
            },
          },
        },
      },
    },
    signIn: "Sign in",
    openStudio: "Go to app",
    heroTitle1: "You did the talking",
    heroTitle2: "We do the rest",
    heroSubtitle:
      "Repurposer is an AI assistant for experts who have content but no time to manage social media. Just give it what you already have — <b>talk videos</b>, meeting recordings, photos, slides, or even just a transcript. Tell it roughly what you want, and it will offer suggestions, plan, and deliver finished pieces in your style. <b>Select the version you like and publish with one click.</b>",
    ctaTryBeta: "Try the beta",
    ctaSeeHow: "See how it works",
    comparison: {
      ariaLabel: "Before and after: raw material and the generated result",
      caption: "Drag the divider — see what raw material becomes",
      scrollDown: "Scroll down",
      beforeLabel: "Raw",
      afterLabel: "Generated result",
      beforeTags: ["Landscape", "Two people", "Muffled audio", "No captions"],
      afterTags: ["Vertical solo shot", "Captions", "Title", "Clearer audio"],
      unmute: "Play sound",
      mute: "Mute",
    },
    manifesto: {
      statement:
        "You spent months on the research and weeks on the slides. The talk itself is over in forty minutes. Then the room empties. The slides go into a folder. The recording sits on a conference page nobody opens twice — and the people who most needed to hear it weren't in the room. Repurposer exists for everything after.",
    },
    showcase: {
      title: "How it works",
      description:
        "Tell it what you need — it runs the whole pipeline, start to finish.",
      steps: {
        s1: {
          title: "Bring whatever you have",
          body: "Keynote video, podcast audio, slides, or just the transcript. Tell it what you need right in the input box — what to make, and in which languages.",
        },
        s2: {
          title: "You name it, you get it",
          body: "Posts, clips, articles, newsletters — written in your style, exactly to your brief. Nothing extra, nothing missing.",
        },
        s3: {
          title: "Refine in chat",
          body: "Talk to the results: shorten a post, retitle a clip, push a different angle. It rewrites until you approve.",
        },
        s4: {
          title: "One click and it's out",
          body: "Finished pieces go out per channel and language. LinkedIn, newsletter, your website — done.",
        },
      },
      screens: {
        compose: {
          chrome: "New project",
          prompt: "Do something with my ECC keynote — LinkedIn first. Our Berlin office needs German too…",
          chip1: "Video",
          chip2: "Slides",
          chip3: "Transcript",
          cta: "Generate",
        },
        results: {
          chrome: "Results",
          score: "92 Pick score",
          cardTitle: "Why grid storage decides the energy transition",
          cardMeta: "LinkedIn · EN · 1,240 chars",
          row2: "Newsletter — EN",
          row3: "Short clip — DE dub · 9:16",
        },
        chat: {
          chrome: "Chat",
          user: "Make the LinkedIn post shorter — keep the three numbers.",
          agent: "Done — tightened to 680 chars, all three numbers kept.",
        },
        publish: {
          chrome: "Publish",
          note: "Scheduled per channel",
          row1: "LinkedIn — published",
          row2: "Newsletter — queued",
          row3: "Website — draft sent",
        },
      },
      asides: {
        a1: {
          label: "Source",
          title: "ecc26-keynote.mp4",
          body: "38 min · slides attached",
          chip: "Any format works",
        },
        a2: {
          label: "Drafts",
          title: "3 drafts · EN + DE",
          body: "Your style, your terms",
          chip: "Written natively",
        },
        a3: {
          label: "Refine",
          title: "Chat with the results",
          body: "Every edit is one message",
          chip: "Nothing ships silently",
        },
        a4: {
          label: "Distribution",
          title: "3 channels",
          body: "Per-language scheduling",
          chip: "GDPR-ready",
        },
      },
    },
    gallery: {
      title: "Made from one source",
      description: "",
      cards: {
        c1: { type: "LinkedIn post", text: "Storage, not generation, is the bottleneck of the energy transition. Three numbers from my ECC keynote…" },
        c2: { type: "Quote card", text: "“The grid of 2040 is being decided in committee rooms this year.”" },
        c3: { type: "Short clip", text: "0:42 — the battery analogy that got the room laughing. 9:16, captioned." },
        c4: { type: "Newsletter", text: "This month: what grid-scale storage actually costs, and why the curve just bent…" },
        c5: { type: "Artikel (DE)", text: "Warum Speicher — nicht Erzeugung — über die Energiewende entscheidet…" },
        c6: { type: "Résumé (FR)", text: "Trois chiffres à retenir de la keynote ECC sur le stockage réseau…" },
        c7: { type: "Article", text: "A longer read: the four storage myths I hear in every policy panel…" },
        c8: { type: "Quote card", text: "“We don't have an energy problem. We have a timing problem.”" },
        c9: { type: "Thread", text: "1/ Everything you heard about grid batteries is two years out of date…" },
        c10: { type: "Short clip", text: "0:58 — the audience Q&A moment everyone asked about afterwards." },
      },
    },
    channels: {
      title: "Lands where your audience is",
      description:
        "Everything routes straight into the channels you publish on — and in the languages your audience speaks.",
      platforms: {
        linkedin: { name: "LinkedIn", blurb: "Native posts" },
        newsletter: { name: "Newsletter", blurb: "Email-ready" },
        website: { name: "Website", blurb: "Articles for your site" },
        youtube: { name: "YouTube", blurb: "Vertical clips" },
        x: { name: "X", blurb: "Threads" },
        podcast: { name: "Podcast", blurb: "Show notes" },
      },
      languages: {
        en: { name: "English", blurb: "Native" },
        fr: { name: "Français", blurb: "Native" },
        de: { name: "Deutsch", blurb: "Native" },
        es: { name: "Español", blurb: "Native" },
        it: { name: "Italiano", blurb: "Native" },
        nl: { name: "Nederlands", blurb: "Native" },
      },
    },
    testimonials: {
      title: "In their own words",
      description:
        "Researchers, lecturers and comms teams use Repurposer where the work has to hold up in print.",
      items: {
        t1: {
          quote: "My keynote used to die on the conference website. This year it became twelve LinkedIn posts, two essays and a newsletter. My dean asked who my new ghostwriter was.",
          name: "Prof. Marije Albers",
          role: "Professor of Energy Systems, TU Delft",
        },
        t2: {
          quote: "The German versions read like I wrote them myself. Our Berlin office checked twice to be sure I hadn't.",
          name: "Claire Dubois",
          role: "Head of research communications, Paris",
        },
        t3: {
          quote: "We used to choose which keynotes deserved coverage. This year every session at the summit got its own posts, clips and recaps.",
          name: "Jonas Weber",
          role: "Summit programme director, Munich",
        },
        t4: {
          quote: "Review-before-publish is the whole product for me. Nothing with my name on it goes out until I've read every word.",
          name: "Dr. Sofia Ricci",
          role: "Policy researcher, Milan",
        },
        t5: {
          quote: "I record once in English. My Spanish students get a version that doesn't read like a translation — they can tell the difference.",
          name: "Diego Fernández",
          role: "Economics lecturer, Madrid",
        },
        t6: {
          quote: "GDPR was the first question our lawyers asked. The answers were ready — we're in pilot now.",
          name: "Anke Janssen",
          role: "University marketing lead, Amsterdam",
        },
      },
    },
    pricing: {
      title: "Simple pricing",
      description: "Start free. Upgrade when your content starts working harder than you do.",
      monthly: "Monthly",
      yearly: "Yearly",
      perMonth: "/mo",
      billedYearly: "billed yearly",
      billedMonthly: "billed monthly",
      freeForever: "free forever",
      mostPopular: "Most popular",
      footnote:
        "Prices in EUR, VAT excluded. Cancel anytime — your plan runs to the end of the period.",
      tiers: {
        free: {
          name: "Free",
          blurb: "Try the pipeline on your next project.",
          features: {
            f1: "2 projects per month",
            f2: "1 piece of content per talk",
            f3: "English + 1 language",
            f4: "Community support",
          },
          cta: "Start free",
        },
        pro: {
          name: "Pro",
          blurb: "For a packed calendar.",
          features: {
            f1: "10 projects per month",
            f2: "Unlimited content",
            f3: "6 European languages",
            f4: "Voice-matched dubbing",
            f5: "Priority generation",
          },
          cta: "Start with Pro",
        },
        institution: {
          name: "Institution",
          blurb: "For universities and summit teams.",
          features: {
            f1: "Everything in Pro",
            f2: "Unlimited seats",
            // "Shared brand templates" sold a retired module (ADR-038);
            // "EU data residency" was a hard claim — compliance copy stays
            // in the ready angle until it ships.
            f3: "GDPR-ready",
            f4: "SSO & invoicing",
          },
          cta: "Contact us",
        },
      },
    },
    faq: {
      title: "Questions, answered",
      description: "The things experts and institutions ask before the first upload.",
      items: {
        q1: {
          q: "Where is my data stored?",
          a: "Repurposer is GDPR-ready by design: your uploads and outputs never train third-party models, and you can delete everything at any time. EU data residency ships with Institution plans.",
        },
        q2: {
          q: "Which languages are supported?",
          a: "English, French, German, Spanish, Italian and Dutch today, with more European languages on the roadmap. Everything is written natively, never translated word-for-word.",
        },
        q3: {
          q: "What can I upload?",
          a: "Keynote videos, podcast audio, slide decks, photos, or just a transcript. The more context you give, the closer the output sits to your style.",
        },
        q4: {
          q: "Does anything get published automatically?",
          a: "No. Every output lands in a review queue first. Nothing carries your name until you explicitly approve it.",
        },
        q5: {
          q: "Who owns the generated content?",
          a: "You do, outright. Outputs are derived from your material and your persona; we claim no rights over them.",
        },
        q6: {
          q: "Can I cancel anytime?",
          a: "Yes. Plans are monthly or yearly with no lock-in, and your projects stay exportable after cancellation.",
        },
      },
    },
    finalCta: {
      headline: "The room empties. The content is just getting started.",
      subtitle:
        "Free during beta. Drop in a talk, a meeting, or just a transcript — tell it what you want, and it does the rest.",
      ctaPrimary: "Try the free beta",
      ctaSecondary: "See pricing",
    },
    footer: {
      tagline:
        "Turning what you already have into lasting content — posts, clips and newsletters in the languages your audience speaks.",
      cta: "Try the free beta",
      columns: {
        features: {
          title: "Features",
          l1: "Overview",
          l2: "How it works",
          l3: "Gallery",
          l4: "Pricing",
          l5: "FAQ",
        },
        // company/legal/social column copy retired with the columns (dead
        // anchors, Footer.tsx) — restore with the pages.
      },
      copyright: "© {{year}} Repurposer. All rights reserved.",
      note: "Made for experts, GDPR-ready.",
      wordmark: "Repurposer",
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
    // Two-level tab shelf: family pill track × underline sub-tabs ×
    // horizontal shelves, organized by USER TASK (2026-10 investor-demo
    // ruling — never by output media type). Keys mirror
    // components/home/recipeFamilies.ts RECIPE_FAMILIES. A family without real
    // demos never renders (无真 demo 不上架) — MG demo prefill copy lands
    // with its assets (MG 批 D3) at `recipes.shelf.demos.<demoId>.prompt`.
    shelf: {
      families: {
        ads: "Ads & UGC",
        talks: "Talks & Interviews",
        posts: "Social Media",
        templates: "More",
      },
      subs: {
        all: "All",
        saas: "SaaS & Apps",
        brand: "Brand & Business",
        ugc: "UGC",
        product: "Products",
      },
      titles: {
        featured: "Featured Recipes",
        saas: "SaaS & Apps",
        brand: "Brand & Business",
        ugc: "UGC",
        product: "Products",
        talks: "Talks & Interviews",
        posts: "Social Media",
      },
      nextPage: "More",
      usePrompt: "Use prompt",
      playSound: "Play sound",
      mute: "Mute",
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
        "launch-film-linear": {
          prompt: "Turn this website into a short intro film: {{placeholder}}",
        },
        "launch-film-zymix": {
          prompt: "Turn this website into a short intro film: {{placeholder}}",
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
  mentions: {
    pickerEmpty: "No matches",
    remove: "Remove mention",
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
    // The pre-generation top-left form (2026-09-02 形态机): before the first
    // run the menu is just a back pill; the full ProjectMenu arrives with the
    // canvas.
    backShort: "Projects",
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
    tabs: {
      clips: "Clips",
      post: "Post",
      quotes: "Quotes",
      quoteFrame: "Quote frame",
      carousel: "Carousel",
      article: "Article",
    },
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
      honesty: "Repurposer can make mistakes — review before you publish.",
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
    assistantLabel: "Repurposer",
    userLabel: "You",
    thinking: "Thinking...",
    thinkingPhases: {
      capturing: "Waiting for the page captures…",
      storyboarding: "Designing the storyboard…",
      storyboard_revision: "Adjusting the storyboard…",
      composing: "Putting it together…",
    },
    /** 分镜起草落定行（legacy 节拍回放）: the drafting span's
     * SETTLED row (a born-settled material beat) — the log register
     * (verb-object + fact, no progressive), the same 三寄存器 law as the
     * material reading family. */
    storyboard: {
      draftingDone: "Drafted the storyboard",
    },
    /** The now-line's material reading rows (2026-09-24 user ruling —
     * thinking IS the activity row's empty state): assets mid-processing →
     * reading (the filename interpolates). The *Done / *Failed forms are the
     * PERSISTED settled rows (素材节拍入库 — the pipeline records one message
     * row per beat, the replay renders the past tense); Progress carries the
     * batch count "N/M" (带计数 ruling).
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
      craftSkeleton: "Reading the reference's style breakdown…",
      artifact: "Reading the card's details…",
      webPage: "Reading the page…",
      webSearch: "Searching the web…",
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
    },
    /** The Activity Stream's milestone copy (ADR-087 §3 Phase 2): the active
     * frame carries the progressive form, the completed frame the past-tense
     * form; failed/cancelled reuse the active form (the ✗ / strikethrough
     * says the rest). kind is a user-semantic category — never a tool name. */
    /** 2026-09-25 copy batch (user ruling — the machine-status register
     * retired): plain words for the work in flight. The draft kind speaks
     * two faces by tool — proposing a plan / editing existing work (the
     * projector's _EDIT_TOOLS picks the key). Draft / run spans are
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
       * done form renders in the fold's category decomposition. */
      storyboard: "Designing the storyboard…",
      storyboardDone: "Designed the storyboard",
    },
    /** The activity row's bounded expand detail (iter-3 S7, E7 诚实边界):
     * only the wire whitelist's fields — the raw count rides as a labeled
     * meta line (the duration joins inline, formatElapsed is the ONE copy). */
    activityMeta: {
      count: "Count: {{count}}",
    },
    /** The aggregate row (ADR-110 段聚合, 修订 — Flora 解剖): a settled
     * segment folds into ONE quiet total — `worked` carries the segment's
     * wall clock (first row's birth → the prose's arrival) as the ONLY
     * collapsed fact; the expanded view shows the category decomposition
     * (foldCategories ×N rows). `actionCount` is the honest fallback when
     * no measurable elapsed exists (legacy rows without stamps). */
    activityFold: {
      worked: "Worked for {{elapsed}}",
      actionCount: "{{count}} actions",
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
      craftSkeleton: "Read the reference's style breakdown",
      artifact: "Read the card's details",
      webPage: "Read the page",
      webSearch: "Searched the web",
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
    derivativeTypes: {
      post: "Social post",
      quotes: "Quote card",
      article: "Article",
      carousel: "Carousel",
    },
    stepKinds: {
      preprocess: "Analyzing your uploads…",
      persona_bootstrap: "Preparing your persona…",
      understand: "Understanding your material…",
      interrupt: "Waiting for your direction…",
      plan: "Planning the content…",
      select_clips: "Generating your clips…",
      revise_script: "Writing the script…",
      render: "Rendering your video…",
      stills: "Extracting key frames…",
      video: "Processing your video…",
      remove_filler: "Removing filler words…",
      add_music: "Scoring your clips…",
      dub_clip: "Dubbing your voice…",
      translate_clip: "Translating your clip…",
      write_post: "Writing your social post…",
      write_quotes: "Creating your quote cards…",
      write_carousel: "Building your carousel…",
      write_article: "Writing your article…",
      synth_talk_video: "Generating your video…",
      align_stills: "Timing your transcript…",
      verify: "Checking quality…",
      materialize_source: "Preparing your full video…",
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
        clip: "Clip",
        post: "Social post",
        quotes: "Quote card",
        quote_frame: "Quote card",
        carousel: "Carousel",
        article: "Article",
      },
      words: "~{{count}} words",
    },
    openInEditor: "Open in editor",
    uploadFile: "Upload file",
    uploading: "Uploading...",
    composerPlaceholder: "Describe what you want to generate...",
    composerFollowUpPlaceholder: "Ask a follow-up, e.g. 'make the hook shorter' or 'add German version'...",
    emptyStateSubtitle: "Upload the video or text from a talk, meeting or interview — we remember your content and style, and make whatever you ask for.",
    noResultsYet: "Results will appear here...",
    quickActions: {
      regenerateHooks: "Regenerate hooks",
      addLanguage: "Add {{language}} version",
      renderAllClips: "Render all clips",
      exportAll: "Export all",
      makeShorter: "Make shorter",
      makeLonger: "Make longer",
    },
    resultActions: {
      edit: "Edit",
      copy: "Copy",
      regenerate: "Regenerate",
      render: "Render video",
      export: "Export",
    },
    recentChats: "Recent conversations",
    noRecentChats: "No conversations yet",
  },
  generationOverlay: {
    tools: {
      translate_clip: "Captioned version",
      dub_clip: "Voice-over version",
      remove_filler: "Remove filler words",
      add_music: "Background music",
    },
    derive: {
      bilingual: "bilingual",
    },
    planVersion: "Plan v{{n}}",
    versionRestore: "Restore this version",
    versionRestored: "Plan v{{n}} restored — it's the current plan now.",
    // FAUNA-parity mechanics placeholder (2026-09-06 user ruling, final
    // cut — @ verified working in product): FAUNA's form verbatim minus
    // the '/' clause, minus "your" (single-line nowrap ellipsis at the
    // inherited 14px: the 57-char original clips in the 480px panel's
    // input; 46 chars fits). "nodes" is honest here: the @ picker's
    // candidates (assets / outputs) ARE canvas nodes. NO '/' — chat has
    // no slash-command system; advertising it would be a false promise
    // (the 虚构 SKU 货架 ban applies to placeholder copy too). The '/'
    // half earns its seat only if slash commands ever ship. ADR-117: the
    // old "confirms with you before starting" clause left with the
    // ask-default regime — static copy describes the default (auto) truth:
    // presentation IS the authorization.
    chatPlaceholder: "Describe your changes — drag or paste files, or type @ to mention nodes.",
    // The full form's sibling (2026-09-13 user ruling): pre-first-run the
    // canvas doesn't exist yet, so there are no "nodes" to point at — the
    // @ picker's candidates are assets only. Copy follows the world's
    // truth per form; the nodes version returns once the canvas lands
    // (panel / dock forms).
    chatPlaceholderAssets: "Describe what you want to make — drag or paste files, or type @ to mention assets.",
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
    // click rides the typed answer machine (kind="start"), never a canned
    // chat message (ADR-129).
    confirmPillStart: "Start",
    confirmPillStartPriced: "Start · ~{{n}} credits",
    confirmPillStartDeferred: "Start · priced when it runs",
  },
  questionDock: {
    bail: "Stop generation",
    skip: "Skip question",
    recommended: "Recommended",
  },
  clipMenu: {
    more: "More actions",
    download: "Download",
    publishOnSocial: "Publish on Social",
    share: "Share",
    shareCopied: "Link copied",
  },
  login: {
    title: "Sign in to Repurposer",
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
        "Choose Use prompt on a card to fill the composer, then adjust the prompt for your material.",
    },
  },
  notifications: {
    title: "Notifications",
    empty: "You're all caught up",
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
