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
    requestFailed: "Request failed",
    networkError: "Network error — check your connection",
    skipToContent: "Skip to content",
  },
  nav: {
    home: "Home",
    personas: "Personas",
    myProjects: "My projects",
    subscription: "Subscription",
  },
  home: {
    newChat: "New chat",
    brandTagline: "The social media agent that gets you and gets the job done",
    // Composer placeholder: fixed prefix + three most-common prompts cycling
    // behind it (Lovart-style rotating placeholder, 2026-08-30). Keep the
    // suffixes short enough to stay one line in the docked bar.
    placeholderPrefix: "Ask Repurposer to ",
    placeholderPrompts: [
      "turn my talk into a week of LinkedIn posts",
      "make quote cards from this podcast episode",
      "dub my keynote into French and German",
    ],
    selectPersona: "Persona",
    generating: "Analyzing your material and generating content, this can take a moment…",
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
    openStudio: "Start repurposing",
    heroTitle1: "You did the talking",
    heroTitle2: "We do the rest",
    heroSubtitle:
      "Repurposer is an AI assistant for experts who have content but no time to manage social media. Just give it what you already have — <b>talk videos</b>, meeting recordings, photos, slides, or even just a transcript. Tell it roughly what you want, and it will offer suggestions, plan, and deliver finished pieces in your style. <b>Select the version you like and publish with one click.</b>",
    ctaTryBeta: "Try the free beta",
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
            f2: "3 pieces of content per talk",
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
    managePersonas: "Manage personas…",
  },
  // Recipe cards (RECIPES §7) — one block per card id in lib/recipes.ts;
  // reserved cards render disabled with the Soon pill, never launchable.
  recipes: {
    sectionTitle: "Get inspired. Then make it yours",
    soon: "Soon",
    expand: "Expand preview",
    mute: "Mute preview sound",
    unmute: "Play preview sound",
    // Static recipe flow steps (ADR-035) — shared namespace; a recipe's flow
    // is WHICH of these steps, in what order, with what fanout.
    flow: {
      // The region frame's label on the 流程 canvas (2026-08-19 走查拍板):
      // the frame wraps ONLY the curated steps (assets/outputs stay outside),
      // so it names itself — never the recipe title (that duplicates the
      // overlay header).
      frameLabel: "Curated steps",
      understand: "Understand the material",
      plan: "Plan the edit",
      align_stills: "Align photos to the script",
      materialize_source: "Prepare the full video",
      select_clips: "Select highlight segments",
      reframe_clip: "Reframe vertical, follow the speaker",
      translate_clip: "Translate the captions",
      dub_clip: "Dub it in your own voice",
      add_music: "Add music",
      render: "Render",
      // Text-tribe flow keys (recipe-gallery v2, ADR-048) — land when the
      // social-post / quote-cards / carousel cards uncomment into the
      // registry. Kept here so the flow lookup never breaks the moment a
      // new card lands.
      write_post: "Write the post",
      write_quotes: "Pick the quote lines",
      write_carousel: "Lay out the slides",
    },
    // Recipe tag chips (info card) — shared namespace.
    tags: {
      multilingual: "Multilingual",
      "no-footage": "No footage needed",
      "auto-framing": "Auto framing",
      "voice-clone": "Voice clone",
      "text-output": "Text output",
    },
    // Example material / output labels (overlay stack items).
    materials: {
      demo_keynote: "Demo keynote excerpt",
      demo_interview: "Demo interview excerpt",
      reframe_output: "Vertical reframe",
      follow_output: "Speaker follow",
      demo_photos: "Event photos",
      demo_article: "Talk write-up",
      image_video_preview: "Slideshow preview",
      subs_en: "Original (EN)",
      subs_zh_bilingual: "CN-EN bilingual",
      subs_fr: "French captions",
      dub_es: "Spanish dub",
      // Post-bake labels for the text-tribe cards (2026-08-24 bake landing).
      post_output: "Post example",
      // quote-cards v3 example matrix (2026-08-28 P3 bake): 形态 A/B ×
      // the three wide-slot paths — each tile one verified input path.
      quotes_form_a: "Speaker layout",
      quotes_form_b: "Full-bleed layout",
      quotes_photo: "Photo + transcript",
      quotes_text: "Transcript only",
      demo_stage_photo: "Curated stage photo",
      carousel_output: "Carousel example",
    },
    // Inspect overlay (RecipeInspectOverlay, D6 二次修订 2026-08-08):
    // right = inspect tabs; left = the launch zone (composer's send
    // mechanism parked inside). The prefilled prompt IS the visible
    // preset — no picker controls, no mirror chips. The dropzone copy is
    // generic; the per-recipe material ask lives in `<id>.inputHint`.
    inspect: {
      tabs: {
        examples: "Examples",
        flow: "Flow",
      },
      sections: {
        outputs: "What you get",
        inputs: "Source material",
      },
      dropzone: "Upload or drag & drop files",
      requiredMissing: "Add the material first: {{input}}",
      promptTitle: "Example prompt",
      promptPlaceholder: "What do you want to make?",
      send: "Generate",
    },
    "multilingual-subs": {
      title: "Multilingual captions",
      promise:
        "Caption your video in any language — single-line, or bilingual side-by-side.",
      inputScenario: "For: talks · meetings",
      inputTitle: "Source video",
      inputHint: "Upload your original video here.",
      promptTemplate:
        "From the uploaded full video (demo source 1:1), make 4 multilingual caption versions — each a separate clip, source untouched: EN original (English voice + English single-line captions, keep 1:1 frame); ZH bilingual (Chinese translation on the main line at font ×0.82 with English original below at ×0.55, translation_track; title overlays translated to Chinese); FR single-line (French single-line captions, original soundtrack stays untouched); ES dub (replace original audio with my cloned voice from the source, ES single-line captions; keep my voice fingerprint — no stock narrator). Caption font size scales with frame (skin default 68 → 38 at 1:1), 8% side margins. Bilingual uses stack layout with only the translation track + a smaller English line — no stacked wall. All versions stay at 1:1 source frame, letterboxed, never cropped.",
      promptHint:
        "Send it as is, or try “bilingual captions”, “French captions”, “add a German version”…",
    },
    "voice-dub": {
      title: "Your-voice AI dub",
      promise:
        "The same talk, in another language — in your voice, not a stock narrator.",
      inputScenario: "For: talks · meetings",
      inputTitle: "Source video",
      inputHint: "Upload your original video here.",
      promptTemplate:
        "From the uploaded full video, make 3 voice-cloned dub versions — each a separate clip, source untouched: ZH dub (replace original audio with my cloned voice from the source, ZH single-line captions), FR dub (same, French), ES dub (same, Spanish). All 3 keep my voice fingerprint — no stock narrator. The original soundtrack stays as a reference layer below the main track so I can hear how natural the clone sounds. Keep the 1:1 source frame, letterboxed, never cropped. Caption font size scales with frame (skin default 68 → 38 at 1:1), 8% side margins. Audio re-times to ASR word-level timestamps — no drift.",
      promptHint:
        "Send it as is, or try “dub it in Mandarin instead”, “add a German version”…",
    },
    "social-post": {
      // Recipe-gallery v2 (ADR-048, §4.6): the loop-value clause on the
      // promise ("the channel's up to you") is what clears gate ② — a
      // generic LLM can translate, it can't own your style + the route.
      title: "Social post",
      promise:
        "Long-form talk or paper, ready-to-post. Written in your style — pick the channel.",
      inputScenario: "For: talks · papers · meeting notes",
      inputTitle: "Source material",
      inputHint: "Your talk transcript, paper draft, or meeting notes — long-form text.",
      promptTemplate:
        "I want a social post.",
      // 2026-08-24 dual-template: when the overlay already has attached
      // files, the launch pre-fills with this richer variant — beginner
      // copy stays on the no-material template (small voice).
      promptTemplateWithMaterial:
        "Turn my source into a social post in my style. The platform is up to you — pick whatever fits. Plain text only — no Markdown (no **bold**, _italic_, # headers, [links](url), or code blocks); every mainstream social platform renders Markdown as raw source, which looks broken.",
      promptHint:
        "Send it as is, or try “shorter, hook-first”, “make it a thread instead”, “in German”…",
    },
    "quote-cards": {
      // 2026-08-27 v3 (ADR-048 第 7 条): the stacked cascade IS the quote
      // card — the promise names the stacked dish, never the one-liner
      // single card (single-quote images are a chat capability, not the
      // card face). Templates keep the bilingual default + chat-driven
      // caption_mode (Phase 1).
      // 2026-08-28 P2 宽槽: three material paths — a recording, photos +
      // a transcript, or a transcript alone (the dark text stack). The
      // input copy names all three, the slot stays optional.
      title: "Quote cards",
      promise:
        "The sharpest lines of your talk, stacked into one ready-to-post quote card.",
      inputScenario: "For: talk recordings · interviews · transcripts",
      inputTitle: "Talk recording, photos, or transcript",
      inputHint: "Upload a talk video, photos with a transcript, or text alone — we'll stack the sharpest lines into one card.",
      // Bilingual CN+EN default example (per brief 2026-08-25 §1.6):
      // real bilingual users type this — short, direct, names the format.
      promptTemplate:
        "Make a bilingual quote card.",
      promptTemplateWithMaterial:
        "From my talk, pick the sharpest lines and turn them into a bilingual quote card.",
      // promptHint teaches the user the two customisation axes (RECIPES
      // §7.2): language pair + caption mode — both are chat-only (no
      // selector widgets, per the promptHint-as-text-not-control rule).
      promptHint:
        "Default is CN+EN bilingual. Tell the chat your own language pair and caption mode (bilingual / source only / target only).",
    },
    carousel: {
      title: "Carousel slides",
      promise:
        "Talk or deck points, paginated into a swipeable slide deck.",
      inputScenario: "For: scripts · slide notes",
      inputTitle: "Source material",
      inputHint: "Your talk script or deck outline — we'll lay it out as slides.",
      promptTemplate:
        "I want a carousel.",
      promptTemplateWithMaterial:
        "Turn my source into a carousel of slides — one idea per slide, ready to post.",
      promptHint:
        "Send it as is, or try “fewer slides”, “add a hook on the first one”, “in French”…",
    },
    "image-video": {
      title: "Photos to video",
      promise: "No footage — photos plus your script, with captions and music.",
      inputScenario: "For: scripts + photos · slide decks",
      inputTitle: "Script and photos",
      inputHint: "Your talk transcript, plus photos or a slide deck (PDF/PPT) — event shots, slides, portraits.",
      promptTemplate:
        "From the uploaded transcript (talk write-up + a set of photos, or a slide deck PDF/PPT), make one stills slideshow: visuals = photo sequence (or deck page images), cut by the transcript's logical sections, each photo holds full-frame while captions advance — no animation or transitions (that's for CapCut); captions = single-line replacement (catalog 6 presets: clean-bottom / karaoke-highlight / fade-in / pop-in / slide-up / stacking), font size scales with frame (skin default 68 → 38 at 16:9), 8% side margins, preserve semantic units from the transcript (don't chop mid-thought); audio = silent version first (voice-clone path comes later), with a background music loop; align_stills estimates the reading-pace timeline, mirror of ASR word-level timestamps. Output = 1 landscape 16:9 video (keep source frame, no cropping); duration driven by transcript length and photo count.",
      promptHint:
        "Send it as is, or try “shorter”, “use the slide deck instead”, “add more photos”…",
    },
    "highlight-clips": {
      title: "Highlight clips",
      promise:
        "Your long video's best moments as vertical clips — top pick flagged.",
      inputScenario: "For: long talk recordings",
      inputTitle: "Source video",
      inputHint: "A talk, meeting or interview recording — mid-shot framing works best.",
      promptTemplate:
        "From the uploaded long talk recording (large mid-shot stage talk works best), cut 3-5 highlight clips — each a separate vertical 9:16 clip: selection = highest information-density moments (concluding statements, key data points, most resonant lines); agent flags the top pick (the one to post first); vertical framing = camera follows the speaker automatically (reframe_clip dynamic mode), speaker centered upper-middle, caption space below — not fixed center-crop; captions = single-line replacement (catalog 6 presets), font size scales with frame (skin default 68), 8% side margins — no stacking; aspect conversion = 9:16 scales by frame height, source frame letterboxed via object-contain, no crop. Output = 3-5 short clips, each 15-60 seconds; original video untouched.",
      promptHint:
        "Send it as is, or try “make them landscape”, “cut a few more”…",
    },
    reframe: {
      title: "Interview reframe",
      promise: "Two-person talk recut vertical — the camera follows the speaker.",
      inputScenario: "For: two-person interviews",
      inputTitle: "Input video",
      inputHint: "A landscape recording of a two-person conversation — an interview or talk show.",
      promptTemplate:
        "From the uploaded two-person conversation recording (landscape left-right interview / talk show works best), cut 2-4 vertical reframe clips — each a separate 9:16 clip: speaker switching = static-reframe mode: detect who's currently speaking (left or right), cut to that person; transitions must be smooth (min dwell + easing), no jarring hard cuts; vertical framing = single speaker centered upper-middle, caption space below — don't try to fit both in frame; captions = single-line replacement (catalog 6 presets), font size scales with frame, 8% side margins; aspect conversion = 9:16 object-contain, letterboxed, source frame preserved. Output = 2-4 vertical clips, each covering one complete turn switch (question → answer); original video untouched.",
      promptHint:
        "Send it as is, or try “cut a few more”, “cover the full interview”, “faster pace”…",
    },
    "ai-visuals": {
      title: "Virtual scenes",
      promise: "No footage, no photos — every scene is AI-generated for your talk.",
      inputScenario: "For: talk audio",
      inputTitle: "Input audio",
      inputHint: "A recording of your talk — every visual is generated around it.",
      promptTemplate:
        "Turn my talk into a short video with AI-generated scenes.",
      promptHint:
        "Use the example to tell Repurposer what you need — feel free to edit it.",
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
    searchPlaceholder: "Search projects...",
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
      draft: "Awaiting confirmation",
    },
    menuMore: "More actions",
    rename: "Rename",
    renameTitle: "Rename project",
    renamePlaceholder: "Project name",
    deleteDesc: "\"{{title}}\" and all its clips, posts and conversations will be permanently deleted.",
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
    empty: {
      clips: "No clips generated yet.",
      post: "No posts generated yet.",
      quotes: "No quote cards generated yet.",
      quoteFrame: "No quote frames generated yet.",
      carousel: "No carousel generated yet.",
      article: "No articles generated yet.",
    },
    dock: {
      history: "History",
      focus: "Working on: {{name}}",
      // The hidden state (2026-09-02 形态机): the user's gesture folds the
      // dock to a bottom-right logo dot; agent speech / questions / focus
      // recall it.
      hide: "Hide chat",
      show: "Show chat",
      // The dock's resident disclaimer (ADR-051, 2026-08-31 — the FLORA
      // FAUNA-line, VERBATIM per user ruling; docked above the input area
      // in the base form, hidden with it on the question morph).
      honesty: "Repurposer is AI and can make mistakes. Check important info.",
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
      // 过程脊 group node (D6): the folded middle steps as one container.
      spine: "Process",
      spineSteps_one: "{{count}} step",
      spineSteps: "{{count}} steps",
      // The artifact node card (D6 修订; 2026-08-19 名词节点收窄): the only
      // live grant is "plan" — the 任务书 glass text node. canvas_key is
      // derived at serialization time from the node CLASS (never persisted),
      // so every run — old or new — renders the same narrowed canvas with
      // zero migration; no other label keys can ever appear.
      artifact: {
        plan: "Plan",
      },
      // Canvas navigation controls (explore surfaces, 2026-08-19 — the
      // project page's top-right swap: app chrome out, canvas controls in).
      zoomIn: "Zoom in",
      zoomOut: "Zoom out",
      zoomFit: "Fit to view",
      // Render failure projected onto the product card in place (never a
      // separate node); the retry channel is the chat dock (D8). An active
      // render speaks through the BrandLoader alone — no status line.
      renderFailed: "Render failed — ask below to retry.",
      // Hover media affordances: expand (top-left) opens the lightbox;
      // sound (top-right) flips the inline video's ambient mute.
      expand: "Expand",
      mute: "Mute",
      unmute: "Unmute",
      // Placeholder slot card (ADR-051 B — 占位物化): the functional
      // teaching line on the quiet card — the @-mention revision channel.
      placeholderHint:
        "Lands here when it's ready — @-mention it in chat to revise.",
      // Hover prompt 框 (ADR-051 F): the per-card revision bar, prefilled
      // with the product's own spec — sending rides the chat channel with
      // the product pinned as focus.
      reviseTooltip: "Revise this product",
      revisePlaceholder: "Ask for a change…",
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
    retry: "Retry",
    retryFailed: "Retry failed output",
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
    completed: "Done",
    failed: "Sorry, I couldn't update this. Please try again.",
    runFailed: "Run failed",
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
      started: "Start generation",
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
    title: "Generation plan",
    planProse:
      "My understanding: {{summary}}. The plan is below — check it, fix anything I got wrong, then hit Start generation.",
    addTask: "Add task",
    tools: {
      translate_clip: "Captioned version",
      dub_clip: "Voice-over version",
      remove_filler: "Remove filler words",
      add_music: "Background music",
    },
    derive: {
      video: "Full video",
      clips: "Clips",
      post: "Post",
      quotes: "Quote cards",
      carousel: "Carousel",
      article: "Article",
      subs: "captioned",
      dub: "voice-over",
      bilingual: "bilingual",
    },
    bilingualToggle: "Bilingual",
    planVersion: "Plan v{{n}}",
    versionRestore: "Restore this version",
    versionRestored: "Plan v{{n}} restored — it's the current plan now.",
    removeSlot: "Remove this task",
    slotAbout: "About",
    slotFor: "For",
    slotTone: "Tone",
    slotMaterial: "Material",
    slotMaterialAttached: "Attached",
    slotMaterialPasted: "Pasted text",
    slotEditMessages: {
      topic: "Topic: {{value}}",
      audience: "Audience: {{value}}",
      tone: "Tone: {{value}}",
    },
    defaultPathLine:
      "Start as-is and I'll generate exactly this — to change anything, just say so in chat.",
    clipsNeedMedia: "Needs a video, audio, or image source — upload to unlock, or remove this row.",
    countDecrease: "Decrease",
    countIncrease: "Increase",
    confirmQuestion: "Save & generate?",
    confirm: "Start generation",
    starting: "Starting…",
    startingLine: "I'm starting your generation — stay to refine it together, or leave and I'll finish in the background.",
    planUpdated: "Got it — I've updated the plan above.",
    chatPlaceholder: "Chat with Repurposer…",
    chatPlaceholderConfirm: "Ask me to adjust the plan…",
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
    failed: "Generation failed",
  },
  questionDock: {
    autonomy: {
      label: "Autonomy",
      auto: "Auto",
      review: "Review",
    },
    bail: "Stop generation",
    skip: "Skip question",
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
      assetsTitle: "Upload your material",
      assetsDesc:
        "A recording, audio, photos or a transcript — whatever you have. Or skip this and just write your idea below.",
      personaTitle: "Whose style and voice",
      personaDesc:
        "If the material doesn't say it already, whose style should we write and speak in? Usually you can leave this on Auto — we generate a style from your material.",
      promptTitle: "Say what you want",
      promptDesc:
        "Write whatever you want made. Use @ to point at specific uploaded assets — that tells us what to do with them.",
      recipesTitle: "Stuck? Browse the templates",
      recipesDesc:
        "Click a template — upload your own material, tweak the prompt to fit your needs, and generate the preset video effect.",
    },
    results: {
      scoreTitle: "Recommendation score",
      scoreDesc:
        "The AI scores each clip's hook, clarity and completeness. Higher scores are more worth posting first — the best one is marked Top pick.",
      videoTitle: "Open the details",
      videoDesc:
        "Click a clip's card to open its details — with a ready-to-copy title, caption and hashtags for your social post.",
      menuTitle: "Quick actions",
      menuDesc:
        "Every product card keeps its actions right under it — preview, download, or publish to social.",
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
