# PRD: Intelligent Talk Repurposing Platform

## 1. Document Information

| Item | Content |
|:---|:---|
| Document Version | v0.4 (Europe Edition, aligned with current implementation) |
| Date | 2026/07/06 |
| Product Name | TBD (internal codename: SpeechRepurposer) |
| Target Audience | Product managers, tech leads, designers, Zuo, European market team |
| Status | Draft |

---

## 2. Product Overview

### 2.1 One-Liner

Transform raw talk materials (video, audio, transcript, slides, photos) into high-quality knowledge assets for LinkedIn, institutional websites, and email newsletters — including social posts, articles, quote cards, and vertical clips — while preserving the speaker's voice and style.

### 2.2 Vision

Enable thought leaders, subject-matter experts, and executives to **zero-edit** their **talks, podcasts, webinars, or interviews** into high-quality knowledge assets for LinkedIn, institutional websites, and email newsletters — with their viewpoints, style, and voice intact throughout.

### 2.3 Core Value Proposition

| Pain Point | Solution |
|:---|:---|
| Talk content is valuable but 90% goes dormant after the event | AI automatically analyzes the full talk, extracting high-virality-potential segments |
| Manual short-form video editing is costly and slow | Agent workflow auto-scripts, self-reviews, and corrects, with a human review loop |
| Multi-language adaptation is expensive | M3 native multi-language, one-click generation for 5 European languages |
| Ghostwriters can't capture the speaker's voice | Learns speaker voice from past materials (books, articles, old talks) |
| Unclear which segments are shareable | AI scores by virality potential and recommends, auto-generating 3 alternative hooks |
| European institutions worry about data security | Optional EU data residency (Cast AI Kimchi), GDPR compliant |

---

## 3. Background & Problem

### 3.1 European Market Context

- **Over 200 million LinkedIn users in Europe**, with Germany, UK, and Netherlands ranking among the top globally for knowledge-content engagement — the core B2B knowledge distribution channel
- **3,000+ academic conferences per year in Europe**, tens of thousands of corporate summits, with post-event repurposing penetration < 5%
- **OpusClip/Descript blind spots in Europe**: Core users are influencers/podcasters, shallow understanding of academic/technical content, and US-based data processing excludes them from European institutional procurement
- **Multi-language is the entry ticket**: 24 official languages in Europe; an English talk without French/German/Spanish versions reaches only 30% of the audience
- **GDPR is a sales weapon**: 73% of European enterprises lack AI governance structures, 64% of Fortune 500 companies operating in Europe face AI compliance pressure; legal risks of cross-border data transfers (Schrems II) put US cloud-processed AI tools at a disadvantage in regulated European procurement

### 3.2 Key Insight

> **SpeechRepurposer is not "another OpusClip" in Europe — it's the only AI knowledge-assetization tool that understands academic talks, speaks 5 European languages natively, and can keep data in the EU.**

- **Core channels are LinkedIn + institutional websites + email newsletters**, not TikTok/Douyin
- **Product positioning shifts from "clip short videos" to "knowledge assetization"**: social posts + articles + quote cards + vertical clips (optional)
- **Multi-language is elevated to P0**: Chinese/English + German/French/Spanish/Italian, M3 native translation, no third-party API
- **EU data residency as a premium differentiator**: GDPR compliance + optional EU data residency via Cast AI Kimchi

### 3.3 User Pain Points

1. **High editing barrier**: Professors/experts can't use editing software, assistants spend too much time editing
2. **Hard to extract content**: Unclear which 30 seconds of a 1-hour talk are worth clipping
3. **Inconsistent style**: Ghostwritten copy doesn't sound like the speaker
4. **High multi-language cost**: Want to take content overseas, but dubbing/translation is expensive
5. **Tedious platform adaptation**: Same content needs manual resizing, subtitle restyling, and copy length adjustments

### 3.4 Competitive Analysis

#### Competitive Landscape (European Perspective)

| Competitor | Positioning | Weakness in Europe | Our Advantage |
|:---|:---|:---|:---|
| **OpusClip** | Long video → batch viral clips | Shallow understanding of academic content; 20-40% of clips need discarding; US data processing | M3 1M context understands full talk logic; Agent closed-loop correction; EU data residency |
| **Descript / Underlord** | Text-driven audio/video editing | Creative editing requires manual work; social copy is generic; US data processing | Learns style from speaker's past materials; native multi-language; EU deployment |
| **InVideo** | Prompt → complete video | Generates from scratch, not based on existing talks; AI scripts are generic | Deep understanding of talk content + past materials; maintains speaker's voice |
| **European Local Tools** | e.g. Lumen5, Pictory | Limited capabilities, no native multi-language support; no Agent loop | M3 capability advantage; multi-language; Agent self-review correction |

#### OpusClip

**Positioning**: Long video → batch short-form viral clips, targeting podcasters, influencers, and marketing teams.

**Core UX Flow**:

```
Upload video → Configure parameters → AI generates clips → Sort by Virality Score → Review preview → Export/publish
```

**Notable Features**:

| Feature | Description | Borrow Value |
|:---|:---|:---|
| **AI Highlight Clips** | Auto-extracts 5-10 viral-potential clips | High — we also need auto-segmentation |
| **Virality Score™** | 0-100 score predicting viral potential | High — can adapt to "virality potential score" |
| **Auto Vertical** | 9:16 with face tracking | Medium — add in P1 |
| **Dynamic Subtitles** | Keyword highlighting, emoji | Medium — can simplify in P0 |
| **AI Hook** | Auto-generates first 3-second title | High — must-have in P0 |
| **Natural Language Filter** | "Find segments discussing pricing strategy" | Medium — add in P1 |

**Limitations**: 20-40% of AI clips need discarding; shallow understanding of complex narratives and academic content; weak creative control.

#### Descript / Underlord

**Positioning**: Text-driven audio/video editor + AI collaborator, targeting podcasts, interviews, and knowledge content.

**Core UX Flow**:

```
Upload audio/video → Auto-transcribe to text → Natural language instructions → AI executes multi-step edits → Review draft → Text refinement
```

**Notable Features**:

| Feature | Description | Borrow Value |
|:---|:---|:---|
| **Text Edits Video** | Edit transcript = edit video | High — P1 subtitle-level editing |
| **Underlord AI Assistant** | Natural language multi-step editing | Medium — similar "regenerate" capability |
| **Filler Word / Pause Cleanup** | One-click remove um/uh/long pauses | Low — non-core need |
| **Show Notes / Chapter Markers** | Auto-generate episode descriptions | Medium — can generate social posts |
| **Multi-language Translation & Dubbing** | 30+ languages with lip sync | Medium — P2 |
| **Overdub** | Text-to-speech in the speaker's voice | Low — P2 consideration |

**Limitations**: Complex multi-track editing still requires professional software; creative edits ("make this more energetic") need manual work; generated social copy is generic.

#### InVideo

**Positioning**: Prompt/text → complete video, targeting social media operators, marketers, and small teams.

**Core UX Flow**:

```
Enter prompt → AI generates script/assets/voiceover/subtitles → Review editor, replace assets → Export
```

**Notable Features**:

| Feature | Description | Borrow Value |
|:---|:---|:---|
| **Brand Kit** | Unified fonts/colors/logo | Medium — P1 subtitle style templates |
| **One-click Multi-language** | 100+ languages | Medium — P2 reference for one-click feel |
| **Voice Selection** | Multiple AI voice options | Medium — P1 general TTS stage usable |
| **Asset Replacement UI** | Left thumbnail strip + right preview | High — P0 review page reference |
| **Prompt Guidance** | Natural language controls generation style | Medium — add "more academic" etc. instructions during generation |

**Limitations**: Generates video from scratch, not based on existing talk content; AI scripts are generic; weak creative control.

#### Differentiation Summary

| Dimension | OpusClip | Descript | InVideo | Our Project |
|:---|:---|:---|:---|:---|
| Target Users | Influencers/podcasters | Podcasts/interviews | Marketing/social media ops | Professors/experts/conference organizers/think tanks |
| Starting Point | Existing long video | Existing audio/video | One-line prompt | Existing talk materials + past materials |
| Core Differentiator | Batch viral clips | Text-edit audio/video | Generate from scratch | Understand speaker + maintain voice + multi-asset input |
| Data Processing | US | US | US | Optional EU residency (GDPR compliant) |
| Multi-language | Translation plugin feel | 30+ language dubbing | 100+ languages | M3 native 6 languages, preserves speaker style |
| Academic Content Understanding | Shallow, 20-40% discard | Medium | None | Deep, based on 1M context + Persona Agent |

**Conclusion**: We borrow their **review workflow, scoring mechanism, text-editing experience, and brand kit**, but core selling points are **"sounds like me", "multi-asset input", "native multi-language", and "EU data residency"**.

---

## 4. Target Users & Personas

### 4.1 Primary Users (Europe Edition)

| User Type | Characteristics | Use Case | Europe-Specific |
|:---|:---|:---|:---|
| **University Professors / Researchers** | Many academic talks, want to expand influence | Auto-generate distribution assets after conference talks | Need multi-language versions (German/French/Spanish) to reach European peers |
| **Corporate Executives / Industry Experts** | Need thought leadership output, time is fragmented | Generate social content after summit talks | Need GDPR compliance proof for corporate procurement |
| **Conference Organizers** | Large volume of talk video assets | Batch-generate conference promotional clips | European academic conferences (e.g. ECA, EMBO) have batch needs |
| **Think Tanks / Research Institutes** | Policy talks need distribution | Turn talks into policy briefs + social content | UK/German think tanks (Chatham House, DIW Berlin) have strong content distribution needs |
| **Corporate Universities / Training Depts** | Internal training content needs reuse | Turn internal training talks into reusable learning assets | Siemens, SAP, Bosch and other European enterprises have internal knowledge management needs |
| **Expert Assistants / Operations Teams** | Actual executors | Upload materials, review AI output, publish | Need GDPR compliance to process internal company talk content |

### 4.2 User Persona Examples

**Professor Zhang (Europe Edition)**
- 55 years old, AI Research Institute Director at a university, frequently attends international conferences
- Can't edit, but wants students/assistants to post his talks on LinkedIn and other professional networks
- Has Twitter/LinkedIn, but posts infrequently
- Wants content to maintain academic rigor while being accessible to non-specialists
- **Europe-specific need**: Needs German version to reach German peers; needs GDPR compliance proof for school procurement approval

**Sarah (UK Think Tank Operations Manager)**
- 32 years old, Chatham House content operations
- Processes 10+ policy talks per month, currently relies on manual editing and writing social posts and articles
- Needs to convert English talks into French/German versions to reach European policy circles
- **Europe-specific need**: All content must be processed in the EU, cannot be transferred to the US; needs native multi-language quality, not stiff machine translation

---

## 5. Product Scope

### 5.1 In Scope (This Cycle)

**Core Features (P0):**

- **Speaker memory auto-persistence and optional management**: After task completion, extract user persona (voice, style, preferences) from input; persist as Speaker; user can view and edit multiple historical personas at `/speakers`; can manually select during project creation, or leave unselected for auto-creation
- Project-level talk material upload (video, audio, transcript, slides, images); input scenarios include talks / podcasts / webinars / interviews
- Speaker past materials upload (books, articles, old talks, social content) — **optional method** to supplement or calibrate persona (not the sole P0 source)
- AI auto-analysis: content segmentation, virality scoring, and Speaker memory extraction from task input
- **AI Generation (P0 Core Outputs):**
  - 3-5 highlight clip scripts (with Hook + subtitles + visual suggestions)
  - Social post (matching Speaker voice)
  - Quote cards / Carousel
  - Article / newsletter content
  - **Multi-language versions:** Chinese/English + German/French/Spanish/Italian, M3 native translation
- **Video rendering (P0, hard prerequisite):** vertical 9:16 MP4 + SRT via Remotion, driven by a declarative `clip-spec(JSON)` contract
- **ASR (word-level timestamps):** faster-whisper self-hosted processing for audio/video uploads
- **Voice-clone dubbing:** MiniMax voice_clone + T2A for translating clip audio into target languages
- Human review interface (script editing, hook selection, visual replacement, feedback regeneration)
- Export: copy (Markdown/TXT), quote card images (PNG), ZIP archive
- Project-scoped chat: natural-language instructions (translate, revise, render, music) dispatch to background runs

**Deferred / Future Features:**

- **EU data residency option:** GDPR-compliant deployment via Cast AI Kimchi or EU cloud region — product differentiator, not implemented in MVP
- **GDPR compliance documentation and data deletion features:** future procurement requirement
- **Link auto-fetch (YouTube / Vimeo / podcasts):** yt-dlp-style fetch to lower input barrier
- **Multi-language UI:** English/German/French/Spanish/Italian interface localization
- **Direct social publishing:** Professional network APIs (e.g. LinkedIn) integration
- **Team collaboration, analytics, billing**

**Out of Scope (This Cycle):**

- Real-time live streaming processing
- AI-generated virtual avatars
- Complex team collaboration permissions (single-user first)
- Entertainment/influencer viral short-form videos (we focus on knowledge content)
- TikTok/Douyin/Xiaohongshu formats (not core channels in Europe)
- Paid subscriptions and billing system

### 5.3 Main Flow Finalized (v0.4 Update): Vertical Clip Output + Editable

After technical review, **"vertical clip output" has been elevated from "P1 optional" to an MVP-mandatory main-flow output, and must be editable**. Detailed plan in [VIDEO_EDITOR.md](./VIDEO_EDITOR.md) and ADR-016. Key points:

- **Category = OpusClip-style**: Server-side AI pipeline + browser **lean editing surface** + deep precision editing **handed off to CapCut/Premiere**. Not a client-side full-featured editor like CapCut Web.
- **Editing form follows Descript**: transcript editing (delete sentence = cut video, non-destructive and recoverable) + word↔timestamp + **single-track trim**; **no** multi-track/layers/transition effects/B-roll library/auto face tracking.
- **"Lighter and weaker" boundary**: Breadth-wise only one main flow, but polished to Descript-level quality (preview = final pixel match, multi-language subtitles editable, one-click export of publishable final output).
- **Technical choice**: Lock in `clip-spec(JSON)` contract; first renderer uses **Remotion** (server-side headless Chrome + FFmpeg) as a replaceable black box; future swap to hand-rolled FFmpeg/client WebCodecs possible, contract unchanged.
- **Dependency escalation**: **ASR (word-level timestamps)** upgraded from P1 to **hard prerequisite**, video needs streamable playback/seek (**local FS + Range endpoint is sufficient, object storage not required, deferred to scale**); therefore MVP input must support video/audio.

---

## 6. User Stories

### 6.1 Upload & Create

**US-001**: As a user, I want the system to automatically persist my style persona after completing a task, and let me view and edit it when needed.

**US-002**: As a user, I want to upload a talk video or audio and have the system automatically transcribe it to text.

**US-003**: As a user, I want to upload a transcript or slides as material for AI analysis.

**US-004**: As a user, I want to upload the speaker's past articles or book chapters to help the AI understand their style.

**US-005**: As a user, I want to upload a voice sample for generating a voice similar to my own.

### 6.2 Generation

**US-006**: As a user, I want the system to automatically extract quotes and highlight segments from the talk.

**US-007**: As a user, I want the system to generate short-form video scripts based on the speaker's style.

**US-008**: As a user, I want the system to generate social post copy.

**US-009**: As a user, I want the system to generate quote images suitable for multiple platforms.

**US-010**: As a user, I want the system to translate content into English or other languages.

### 6.3 Review & Export

**US-011**: As a user, I want to preview AI-generated videos and copy.

**US-012**: As a user, I want to edit generated scripts, subtitles, and titles.

**US-013**: As a user, I want to replace visuals or BGM in the video.

**US-014**: As a user, I want to one-click export all generated content.

---

## 7. Functional Requirements

### 7.1 Speaker Memory Management

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-001 | Auto-create Speaker | P0 | When user hasn't selected a Speaker, auto-extract and create a Speaker memory from task input after task completion |
| FR-002 | Manual Speaker creation | P0 | User can manually create and fill in basic info at `/speakers` in advance |
| FR-003 | Edit Speaker memory | P0 | Modify name, title, avatar, language preferences, and AI-extracted style fields |
| FR-004 | View Speaker style persona | P0 | AI-generated persona summary, editable by human |
| FR-005 | Manage Speaker past materials | P1 | CRUD books, articles, social content as supplementary persona calibration sources |
| FR-006 | Manage Speaker voice samples | P1 | Upload/delete/preview cloning effects |

### 7.2 Project (Talk) Management

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-007 | Create project | P0 | Can select an existing Speaker, or leave unselected; system auto-creates if unselected |
| FR-008 | View project list | P0 | Filter by Speaker/status/date |
| FR-009 | Delete project | P1 | Soft delete |
| FR-010 | Project status tracking | P0 | Uploading/processing/review/completed |
| FR-011 | Select EU data residency | P2 | During project creation: Default (Global) / EU data residency (via Cast AI Kimchi); future procurement differentiator, not in MVP |

### 7.3 Material Upload & Input Sources

> **Understanding: Input sources have two first-class entry points — "upload file" and "paste link".**
> In real scenarios, user content often already lives on YouTube / Zoom / Loom / podcasts; "paste link to auto-fetch" is much smoother than "download first, then upload", a key barrier-reducing entry point (industry standard, see OpusClip).
>
> **Understanding: Input scenarios are not limited to "talks".** Equally support talks / podcasts / webinars / interviews and other "knowledge-oriented oral long-form content".
>
> **Understanding: Non-text input (video/audio/link) must go through ASR transcription.** ASR is not an optional nice-to-have, but a mandatory prerequisite to turn audio/video into "timestamped transcript", directly determining subsequent segment selection, subtitles, and generation. **ASR priority is determined by input ambition** — if P0 accepts video/audio/link, ASR must be elevated accordingly; if P0 only accepts transcripts, ASR can be deferred.
>
> **Input processing pipeline:** `link/file → (yt-dlp-style fetch) → ASR transcription → normalized transcript (with timestamps) → persona understanding / content generation`.
> **External dependencies (not covered by MiniMax, need third-party):** link fetching (yt-dlp-style, supports thousands of sites), ASR transcription (Whisper-style, multi-language).

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-011 | Upload video | P0 | Support common formats, size limit TBD |
| FR-012 | Upload audio | P0 | Support common formats |
| FR-013 | Upload transcript | P0 | Support docx/txt/md, or paste text |
| FR-014 | Upload slides | P0 | Support pdf/ppt/pptx |
| FR-015 | Upload event photos | P0 | Support jpg/png, multiple selection |
| FR-016 | Upload speaker past materials | P0 | Books, articles, old talk transcripts, social content |
| FR-017 | Material preprocessing status display | P0 | Fetching/transcribing/parsing/completed |
| FR-018 | Paste link auto-fetch | P1 | YouTube / Vimeo / Zoom / Loom / Google Drive / podcast links, fetched via yt-dlp-style tool to get video/audio, eliminating manual download-then-upload; after fetch, enters ASR transcription |
| FR-019 | Non-text input auto-transcription (ASR) | P0 | Video/audio → timestamped transcript; multi-language; prerequisite for segment selection/subtitles/generation; implemented with faster-whisper |

### 7.4 Persona Understanding & Style Persona

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-018 | Auto-extract Speaker memory from task input | P0 | Extract values, common metaphors, sentence patterns, terminology preferences, emotional tendencies from current task materials + prompts, persist as Speaker |
| FR-019 | Manual edit Speaker memory | P0 | User can modify, supplement, or disable certain expressions |
| FR-020 | Content segmentation & scoring | P0 | Slice talk into shareable segments, sort by "virality potential score" (0-100) |
| FR-021 | Keyframe/slide page recommendation | P1 | Recommend suitable visuals from uploaded materials |
| FR-022 | Quote extraction | P0 | Auto-extract 5-10 most viral quotes |

### 7.5 Voice Settings

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-023 | Style sliders | P0 | Academic rigor ↔ casual spoken; rational restraint ↔ passionate; concise direct ↔ detailed expansion |
| FR-024 | Target audience selection | P0 | Peer scholars / industry practitioners / general public / investors / policymakers |
| FR-025 | Catchphrases / fixed openers & closers | P1 | User can set common expressions |
| FR-026 | Blocked words | P2 | Avoid certain words appearing |

### 7.6 Voice Samples

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-027 | Upload voice sample | P1 | 1-3 minutes of clear recording |
| FR-028 | Preview cloned voice | P1 | Listen with sample text |
| FR-029 | Toggle for generation | P1 | User can enable/disable cloned voice |
| FR-030 | Multi-language voice mapping | P2 | Chinese uses cloned voice, English can choose British/American |

### 7.7 Content Generation

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-031 | Generate highlight clip scripts | P0 | Default 3-5, each containing: Hook + script + subtitle timestamps + visual suggestions + music mood |
| FR-032 | Generate alternative hooks | P0 | Each clip gets 3 alternative titles/hooks, user can select or customize |
| FR-033 | Generate social post | P0 | 1 post, matching Speaker voice, structure: Hook → Core insight → Personal take → Call to action |
| FR-034 | Generate quote cards | P0 | 3-5 cards, 1:1 or 4:5, with attribution and style templates |
| FR-035 | Generate Carousel | P1 | Multi-page images + text, suitable for social platforms |
| **FR-036** | **Generate multi-language versions** | **P0** | **Chinese/English + German/French/Spanish/Italian, M3 native translation, preserves original meaning and impact** |
| FR-037 | Generate visual/B-roll prompts | P1 | Annotate suggested visuals for each clip, match from uploaded materials |
| FR-038 | Generate music suggestions | P1 | Match BGM by mood tags (calm/passionate/suspenseful/hopeful) |

### 7.8 Review & Editing (Iteration: Direct Edit First, Dialogue as Fallback)

> **Understanding: Output "will inevitably need changes", but "change" ≠ "must be multi-turn dialogue".** Making all changes into dialogue is slower, less controllable, and more token-consuming for the most common small edits. Choose the fastest interaction by edit type:
>
> | What to change | Fastest way | Need dialogue? |
> |:---|:---|:---|
> | Change a word / delete a sentence / adjust word order | Edit directly in text (WYSIWYG) | No — describing is slower than direct editing |
> | This one doesn't work, give me another version | One-click "regenerate" (triggers Reviser) | No — button is faster |
> | Make it shorter / more formal / more casual | Quick actions (shorten / formal / casual…) | No — preset actions are faster |
> | Vague broad direction adjustment ("less jargon, more storytelling") | Natural language sentence | Yes — this is where dialogue adds value |
> | Change quote card template / subtitle style | Change Brand template settings | No |
>
> **Conclusion: Iteration main force = direct editing + local regeneration + quick actions (covers ~80% of edits); free dialogue only as fallback for "vague broad direction adjustments", non-core, can be deferred (MVP can skip dialogue first).**
> When dialogue fallback is used, agent context = talk materials + Speaker memory + current output + necessary history.
> (Chapter 20 is **internal agent orchestration**, separate from the user-facing iteration interaction here.)
>
> **Current gap:** Output is currently read-only display, missing "direct edit" and "local regeneration/quick action" entry points; Reviser endpoint exists but frontend not yet connected (home page "New chat" is just a dialogue-suggesting UI hint).

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-039 | Script editing | P0 | Modify subtitles, hooks, endings, displayed by timeline |
| FR-040 | Title selection/editing | P0 | Select from AI alternative titles or rewrite |
| FR-041 | Visual replacement | P1 | Select alternative visuals from uploaded materials |
| FR-042 | BGM replacement | P1 | Switch background music by mood tags |
| FR-043 | Regenerate | P0 | Local regeneration for a single clip or derivative content (triggers Reviser Agent) |
| FR-044 | Structured feedback | P0 | User feedback types: Hook not working / overall style mismatch / too complex/too simple / factual inaccuracy / want different expression |
| FR-045 | Multi-language review | P0 | Sentence-by-sentence review and correction of multi-language versions |

### 7.9 Export

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-046 | Export copy | P0 | Markdown/TXT, including all language versions |
| FR-047 | Export quote card images | P0 | PNG/JPG, multiple templates available |
| FR-048 | Export video | P0 | MP4 via Remotion renderer, preview = output pixel parity |
| FR-049 | Export subtitle files | P0 | SRT export per clip |
| FR-050 | Batch export | P0 | ZIP archive with all project outputs |
| FR-051 | Export EU compliance certificate | P2 | Generate GDPR data processing statement PDF; future procurement feature, not in MVP |

### 7.10 European Localization Features

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| FR-052 | Multi-language UI | P1 | Frontend UI supports English/German/French/Spanish/Italian switching |
| FR-053 | European time format | P1 | Support 24-hour clock, DD/MM/YYYY date format |
| FR-054 | European academic conference templates | P1 | Output templates for European academic conferences (e.g. ECA, EMBO style) |
| FR-055 | European B2B marketing templates | P1 | Copy templates for European LinkedIn B2B marketing (German rigor, French elegance, British brevity) |

---

## 8. Non-Functional Requirements

### 8.1 Performance

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| NFR-001 | Upload response | P0 | Immediate feedback after material upload, large file chunking |
| NFR-002 | Generation time | P0 | Simple projects (transcript + images) initial draft within 5 minutes |
| NFR-003 | Video rendering | P1 | Single clip render within 2 minutes |
| NFR-004 | Concurrent processing | P1 | Support multiple projects queued for async processing |

### 8.2 Security & Privacy

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| NFR-005 | User data isolation | P0 | Different users' data cannot be accessed by each other |
| NFR-006 | Material secure storage | P0 | Uploaded files encrypted at rest |
| NFR-007 | Voice sample authorization | P1 | Clearly inform users voice samples are only used for their own content generation |
| NFR-008 | Copyright compliance notice | P1 | Provide copyright reminders for music, images, and other materials |
| NFR-009 | EU data residency | P2 | For EU-selected projects, data storage and processing within EU region; future deployment differentiator |
| NFR-010 | GDPR compliance | P2 | Provide data processing statements, user data deletion, export features; future procurement requirement |
| NFR-011 | Cross-border data control | P2 | EU project data must not be transferred to non-EU regions for processing; future procurement requirement |

### 8.3 Usability

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| NFR-012 | Upload guidance | P0 | Clearly tell users "upload at least one type, more is better" |
| NFR-013 | Status transparency | P0 | Show progress for each processing step |
| NFR-014 | Review-friendly | P0 | Generated content displayed side-by-side for easy comparison |
| NFR-015 | Mobile adaptation | P2 | Large file upload recommended on desktop |

### 8.4 Extensibility

| ID | Requirement | Priority | Description |
|:---|:---|:---|:---|
| NFR-016 | Module decoupling | P0 | Media processing, intelligent generation, rendering layer can be independently replaced |
| NFR-017 | Multi-language extension | P1 | Add new languages without changing core logic |
| NFR-018 | Output format extension | P1 | Add new platform formats without changing core logic |

---

## 9. Technical Architecture

### 9.1 Abstract Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│              (Web UI / Mobile UI / Admin Dashboard)        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer: FastAPI                  │
│         (RESTful API, upload endpoints, task scheduling,    │
│          permission management)                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  Core Intelligence Layer: MiniMax M3          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ Long Context │ │ Multimodal  │ │ Structured Content │   │
│  │ Understanding│ │ Understanding│ │ Generation         │   │
│  │              │ │ (Image/Text/ │ │ (JSON scripts/copy)│   │
│  │              │ │  Video)      │ │                    │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ Persona      │ │ Content      │ │ Multi-language      │   │
│  │ Style Persona│ │ Segmentation │ │ Translation         │   │
│  │              │ │ & Scoring    │ │                     │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Async Task Scheduling Layer             │
│              (Task queue + background worker nodes)          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Media Processing Layer                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Speech   │ │ Video    │ │ Document │ │ Image      │      │
│  │ Recognition│ │ Frame    │ │ Parsing  │ │ Processing │      │
│  │ Engine   │ │ Engine   │ │ Engine   │ │ Engine     │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Voice    │ │ Speech   │ │ Video    │ │ Graphics   │      │
│  │ Cloning  │ │ Synthesis│ │ Rendering│ │ Generation │      │
│  │ Service  │ │ Service  │ │ Engine   │ │ Engine     │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐                                              │
│  │ Music/   │                                              │
│  │ Sound    │                                              │
│  │ Resource │                                              │
│  │ Service  │                                              │
│  └──────────┘                                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Data Persistence Layer                  │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────┐   │
│  │ Relational │ │ Object     │ │ Vector Database      │   │
│  │ Database   │ │ Storage    │ │ (optional)           │   │
│  └────────────┘ └────────────┘ └──────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Architecture Description

| Layer | Confirmed Technology | Responsibility |
|:---|:---|:---|
| Client Layer | **TanStack Start** | User material upload, voice configuration, review generation results, export content; supports multi-language UI |
| Application Layer | **FastAPI** | Receive uploads, manage Speaker/project/tasks, expose REST API, coordinate layers |
| Core Intelligence Layer | **MiniMax M3** | Understand all input materials, generate persona, extract quotes, generate scripts and social copy, multi-language translation |
| Async Task Scheduling Layer | **Postgres queue + standalone worker** | `FOR UPDATE SKIP LOCKED` claim rows; worker process runs ASR, generation, and rendering; no Celery/Redis in MVP |
| Media Processing Layer | **faster-whisper, PyMuPDF, Remotion, MiniMax voice_clone/T2A** | ASR transcription, document/slide parsing, video rendering, voice-clone dubbing, music |
| Data Persistence Layer | **PostgreSQL + object storage** | PostgreSQL for metadata; S3-compatible object storage (Volcengine TOS) for uploaded files and generated results (ADR-024) |

### 9.3 Data Flow

```
User input materials
    ├── Upload files (video/audio/transcript/slides/images)
    └── Paste text or prompt in input box
    ↓
FastAPI receives → presign direct upload to object storage → write Asset(PENDING) to PostgreSQL
    ↓
Worker process claims Asset rows and preprocesses:
    ├── Video/audio → ASR transcription (faster-whisper, multi-language) → word-level timestamps
    ├── Images → M3 vision key-point extraction
    └── Slides/PDF → PyMuPDF page rendering + text extraction
    ↓
User clicks Generate → WorkflowRun(PENDING) created
    ↓
Worker claims WorkflowRun and runs agents:
    content_director → clip → post / quotes / carousel / article
    ↓
Clip render_spec written; Derivative rows written
    ↓
User reviews; chat/revise/translate/dub requests create new WorkflowRun rows
    ↓
Render trigger → worker calls Remotion render service → MP4 + SRT
    ↓
TanStack Start frontend review
    ↓
Iteration loop:
    chat instruction → intent parsing → background run → updated clip/derivative
```

### 9.4 Agent Workflow Design

P0 must have built-in Agent workflow, core reason being **users will inevitably be dissatisfied with AI-generated results**, the system needs to support a "generate → self-review → correct → human feedback → local regenerate" closed loop.

#### Core Agent List

| Agent | Responsibility | Trigger Timing |
|:---|:---|:---|
| Persona Agent | Generate Speaker style persona based on past materials | After Speaker creation/update |
| Content Director | Analyze talk content once and produce a unified `ContentPlan` (thesis, themes, audience, per-output plans) | At the start of every full generation run |
| Clip Agent | Select shareable segments and write vertical clip scripts from the `ContentPlan` | During clip generation |
| Post Agent | Generate social posts | During derivative content generation |
| Quotes Agent | Generate quote card copy | During derivative content generation |
| Carousel Agent | Generate Carousel multi-page images + text | During derivative content generation (P1) |
| Article Agent | Generate article / newsletter content | During derivative content generation |
| Translator Agent | Multi-language translation | During multi-language version generation |
| Reviser Agent | Modify specified content based on feedback | After user feedback |

#### Generation Flow

```
Upload materials and preprocess
    ↓
Persona Agent → Speaker style persona (if no speaker selected)
    ↓
Content Director → unified ContentPlan
    ↓
Clip Agent → segment selection + scripts
    ↓
LinkedIn Agent / Quotes Agent / Carousel Agent / Article Agent → derivative content
    ↓
Translator Agent → multi-language versions (German/French/Spanish/Italian)
    ↓
Wait for user review
    ↓
User feedback → Reviser Agent → local regeneration
```

#### Human-in-the-Loop (HITL)

User feedback needs to be structured for the system to process effectively:

| Feedback Type | Processing Scope |
|:---|:---|
| Hook not engaging | Only regenerate hook |
| Overall style doesn't sound like me | Regenerate entire script, may need persona/tone adjustment |
| Information too complex/too simple | Regenerate by audience |
| Factually inaccurate | Prompt user to check source materials, do not auto-correct |
| Want different expression | Optimize based on user-edited content |

---

## 10. Data Models

### 10.1 User

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| email | string | Login email |
| name | string | Username |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

> **Note**: Login is implemented as passwordless email verification-code (Resend) with per-user data isolation across speakers/projects/assets/brand templates/chat sessions. The seeded default user remains only as the owner of shared demo content. UI language preference and EU-region residency are future features.

### 10.2 Speaker / Memory

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| user_id | UUID | Associated user (isolated by user) |
| name | string | Name |
| title | string | Title/position |
| avatar_url | string | Avatar |
| language | string | Primary language |
| persona | JSON | AI-extracted speaker style memory from task input or past materials |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

### 10.3 Project

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| user_id | UUID | Associated user |
| speaker_id | UUID | Associated speaker, **optional** |
| title | string | Project title |
| event_name | string | Event name |
| language | string | Content language |
| status | enum | draft/uploading/processing/review/completed |
| tone_snapshot | JSON | Voice settings snapshot at generation time |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

> **Note**: Project-level EU data residency (`data_region`) is a future differentiator, not implemented in the MVP.

### 10.4 Asset

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| user_id | UUID | Associated user (denormalized for ownership checks) |
| project_id | UUID | Associated project (nullable when attached to speaker) |
| speaker_id | UUID | Associated speaker (nullable when attached to project) |
| type | enum | video/audio/transcript/slides/image/voice_sample/past_material |
| file_url | string | File URL |
| transcript | text | Transcription text (audio/video) |
| extracted_text | text | Extracted text (documents/images) |
| slide_pages | JSON | Slide page list |
| meta | JSON | Processor extras (ASR word-level timestamps, detected language, etc.) |
| processing_status | enum | pending/processing/completed/failed |
| processing_error | text | Failure reason |
| duration_seconds | int | Duration (audio/video) |
| processed_at | datetime | Processing completion time |
| created_at | datetime | Creation time |

### 10.5 Clip

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| project_id | UUID | Associated project |
| hook | string | Opening hook |
| title_options | JSON | Alternative titles |
| music_mood | string | Music mood |
| status | string | `generated` / `rendering` / `completed` / `failed` (legacy field) |
| video_url | string | Generated video URL |
| srt_url | string | Exported subtitles URL |
| duration | int | Duration (seconds) |
| language | string | Language |
| source_segment | JSON | Selected source segment metadata |
| render_spec | JSON | Renderer-agnostic clip-spec contract (source, segments, captions, brand, music, dub) |
| render_status | enum | pending/rendering/completed/failed |
| render_error | text | Render failure reason |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

### 10.6 Derivative

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| project_id | UUID | Associated project |
| type | enum | post / quotes / carousel / article |
| content | text/JSON | Content |
| language | string | Language |
| image_url | string | Image URL (quote card / carousel) |
| status | string | `generated` / `edited` (legacy string field) |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

### 10.7 WorkflowRun

| Field | Type | Description |
|:---|:---|:---|
| id | UUID | Primary key |
| project_id | UUID | Associated project |
| status | enum | pending/running/waiting_human/completed/failed |
| current_step | string | Current step description |
| progress | int | Progress percentage |
| error | text | Failure reason |
| context | JSON | Generation inputs and outputs |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

### 10.8 ChatSession & Message

| Field | Type | Description |
|:---|:---|:---|
| ChatSession.id | UUID | Primary key |
| ChatSession.user_id | UUID | Associated user |
| ChatSession.project_id | UUID | Associated project |
| ChatSession.asset_id | UUID | Associated asset (for asset-scoped chat) |
| ChatSession.asset_type | string | `clip` / `derivative` (when asset_id is set) |
| ChatSession.title | string | Session title |
| Message.id | UUID | Primary key |
| Message.session_id | UUID | Associated chat session |
| Message.role | enum | user / assistant / system |
| Message.content | text | Message content |
| Message.attachments | JSON | Attached files |
| Message.workflow_run_id | UUID | Related generation job |
| Message.intent | JSON | Parsed assistant intent |
| Message.created_at | datetime | Creation time |

---

## 11. Core User Flows

### 11.1 Create and Manage Speaker Memory

```
1. User logs in
2. Method A: Manually create Speaker (optional)
   ├── Enter name, title, language, primary activity field
   ├── Optional avatar upload
   └── Select target audience (peer scholars/industry practitioners/general public/investors/policymakers)
3. Method B: Auto-create after task completion (default path)
   ├── User doesn't select Speaker on home page / during project creation
   ├── System extracts style characteristics from materials + prompts during task processing
   └── After task completion, persists as a Speaker memory record
4. User can view, edit, delete their Speaker memory at /speakers
   ├── Modify basic info
   └── Modify AI-extracted style fields (values, metaphors, sentence patterns, etc.)
5. Optional upload of past materials or voice samples for persona calibration (P1 supports voice cloning)
6. Set voice sliders (academic rigor ↔ casual spoken; rational restraint ↔ passionate; concise direct ↔ detailed expansion)
```

### 11.2 Home Page Task Creation & Content Generation

```
1. User enters home page, sees input box
2. Provide input (choose one or multiple combinations)
   ├── Drag/drop or select files: video/audio/transcript/slides/images
   └── Paste text or enter prompt in input box
3. Configure outputs (all in toolbar below input box, all optional)
   ├── Speaker: select existing Speaker or leave unselected
   ├── Brand template: select existing template or leave unselected
   ├── Tone: professional/thought leader/conversational/academic
   └── Outputs: clips generated by default, optionally social post / quote cards / article / carousel, etc.
4. Click generate button
   ├── Frontend auto calls POST /projects to create Project
   ├── Frontend auto calls POST /projects/{id}/assets to upload materials
   └── Frontend auto calls POST /projects/{id}/generate to trigger async generation
5. System processes asynchronously
   ├── Worker processes Asset: ASR transcription / text extraction / visual image reading
   └── Worker runs Generation: Analyzer → Script / Post / Quotes / Article / Carousel
6. User auto-redirects to project detail page to view generation results
```

### 11.3 Review & Export

```
1. User views generated clips list (left list + right preview)
   ├── Each clip displays: virality potential score, duration, language, status
   └── Right preview: script + subtitle timestamps + visual suggestions
2. Play/preview each clip
3. Edit script, subtitles, hook (select from 3 alternatives or customize)
4. Replace visuals or BGM (select from uploaded materials)
5. View social post, quote cards, article, and multi-language versions
6. Submit feedback (structured: hook/style/complexity/facts/expression)
7. Trigger Reviser Agent local regeneration
8. Confirm and export
   ├── Copy (Markdown/TXT, including all language versions)
   ├── Quote card images (PNG/JPG)
   ├── Video (MP4 + SRT)
   └── ZIP archive with all project outputs
```

---

## 12. Output Specifications

### 12.1 Vertical Highlight Clips

| Attribute | Specification |
|:---|:---|
| Aspect ratio | 9:16 |
| Resolution | 1080 × 1920 |
| Duration | 15-60 seconds, default 30 seconds |
| Subtitles | No more than 12 characters per line, bottom-centered |
| Visuals | Speaker close-up / event photos / slide pages / dynamic text |
| Music | Matched by mood tags |

### 12.2 Hook / Title

- Each clip provides 3 alternative titles
- First 3 seconds of subtitles must have conflict, counter-intuition, or strong data
- Title length suitable for display on all platforms

### 12.3 Social Post

| Attribute | Specification |
|:---|:---|
| Length | 150-300 English words / 300-600 Chinese characters |
| Structure | Hook → Core insight → Personal take → Call to action |
| Voice | Maintain Speaker style, professional but readable |
| Hashtags | Auto-generate 3-5 relevant topic tags |
| Multi-language | Simultaneously generate German/French/Spanish/Italian versions |

### 12.4 Article

| Attribute | Specification |
|:---|:---|
| Length | 600-1,500 English words / 1,000-3,000 Chinese characters |
| Structure | Title → Lead → Core arguments → Evidence/quotes → Conclusion/CTA |
| Voice | Maintain Speaker style; suitable for institutional websites and newsletters |
| Hashtags | Auto-generate 3-5 relevant topic tags |
| Multi-language | Simultaneously generate German/French/Spanish/Italian versions |

### 12.4 Quote Cards

| Attribute | Specification |
|:---|:---|
| Aspect ratio | 1:1 (LinkedIn/Instagram) or 4:5 or 9:16 (Stories) |
| Content | One quote + attribution + date |
| Style | 3-5 template options (tech/academic/minimal/dark/warm) |
| Output | PNG / JPG, high resolution |
| Multi-language | Simultaneously generate multi-language versions |

### 12.5 Carousel

| Attribute | Specification |
|:---|:---|
| Pages | 5-8 pages |
| First page | Title + visual |
| Middle pages | Core arguments / quotes |
| Last page | CTA + attribution + QR code/link |
| Platforms | LinkedIn / Instagram |

### 12.6 Multi-language Versions

| Attribute | Specification |
|:---|:---|
| P0 languages | Chinese, English, German, French, Spanish, Italian |
| Translation quality | M3 native translation, preserves original meaning, impact, and Speaker style |
| Review support | Source + translation side-by-side, sentence-by-sentence editing |
| Translation confidence | Low-confidence content highlighted for attention |
| Dubbing | Voice-clone dubbing via MiniMax voice_clone + T2A (P0 implemented); general TTS fallback available |

---

## 13. API Overview

The detailed API specification is maintained in [API.md](./API.md). At a high level the backend exposes:

- **Speaker management** (`/speakers`)
- **Project management** (`/projects`, including `/generate`, `/jobs`, `/results`, `/export`)
- **Asset upload** (`/projects/{id}/assets` and `/speakers/{id}/assets`)
- **Clip actions** (`/clips/{id}`: regenerate, revise, translate-captions, dub, render)
- **Derivative editing** (`/derivatives/{id}`)
- **Chat** (`/chat`, `/chat/session`, `/chat/sessions/{id}/messages`)
- **Library** (`/library`)
- **File streaming** (`/files`, `/outputs`, `/music`)

---

## 14. UI/UX Requirements

### 14.1 Upload Page

- Clear material type sections (video/audio/transcript/slides/photos)
- Drag-and-drop upload + click upload
- Display processing status for each material (transcribing/parsing/completed)
- **Hint copy**: "Upload at least one type, more is better. Transcript + event photos can produce a first draft."

### 14.2 Speaker Style Persona Page

- Left: AI-generated persona
- Right: User-editable fields
- Provide "re-analyze" button

### 14.3 Generation Results Page

Reference OpusClip's "left list + right preview" layout:

- **Left clip list**: Displays virality potential score, duration, current status
- **Right preview area**: Video preview + subtitle timestamps + editing area
- **Top tabs**: Clips / Post / Quotes / Article / Carousel
- **Action buttons**: Export, regenerate, delete
- **Sort/filter**: Filter by score, duration, status

### 14.4 Review Page

Reference Descript's text-editing experience:

- **Script editor**: Display subtitles by timeline, each sentence independently editable
- **Subtitles = video**: After editing subtitle copy, video subtitles sync update
- **Visual replacement**: Thumbnail grid, select from uploaded materials
- **BGM replacement**: Categorized by mood (calm/passionate/suspenseful/hopeful)
- **Title selection**: A/B/C three alternatives + custom
- **Feedback buttons**: Submit dissatisfaction reasons for clip overall, hook, subtitles, style separately

### 14.5 UX Borrowed from Competitors

| Borrow | Source | P0 Adopted? | Description |
|:---|:---|:---|:---|
| Upload = process, no complex config | OpusClip | ✅ | After user upload, auto-enters processing flow |
| AI generate + score sort | OpusClip | ✅ | Each clip displays virality potential score |
| Left list + right preview | OpusClip | ✅ | Standard review layout |
| Hook/title A/B testing | OpusClip | ✅ | Each clip provides 3 alternative titles |
| Natural language segment filter | OpusClip | ❌ P1 | "Find segments discussing X" |
| Text edits video | Descript | ❌ P1 | Edit subtitle = edit video, P0 only does subtitle editing |
| AI multi-step editing instructions | Descript | ❌ P1 | Similar to "polish this episode into YouTube version" |
| Multi-language translation dubbing | Descript | ❌ P2 | Future extension |

---

## 15. Success Metrics

### 15.1 Content Quality

| Metric | Target | Measurement |
|:---|:---|:---|
| User edit rate | < 50% | Statistically proportion of clips where user modified the script |
| User save rate | > 80% | Proportion of users who save/export after generation |
| Multi-language adoption rate | > 60% | Proportion of users who export multi-language versions |
| Style match score | > 7/10 | User rating "does this sound like me" |

### 15.2 Efficiency Gains

| Metric | Target |
|:---|:---|
| Single project processing time | < 10 minutes (excluding rendering) |
| Human review time | < 15 minutes / project |
| Compared to pure manual editing | Save 80%+ time |
| Multi-language generation time | < 2 minutes / language |

### 15.3 User Retention (European Market)

| Metric | Target |
|:---|:---|
| European seed customers (Q3) | 5-10 paid trials |
| Monthly projects per user | > 3 |
| Multi-language feature usage | > 60% |
| Revision/chat feature usage | > 30% |
| NPS | > 40 |

---

## 16. Risks & Assumptions

### 16.1 Risks

| Risk | Impact | Mitigation |
|:---|:---|:---|
| MiniMax M3 instability on long-text/multimodal understanding | Poor output quality | Start with transcript-driven, multimodal as auxiliary; Agent Review iterative correction |
| Voice cloning quality below expectations | Multi-language versions unavailable | Default to general TTS, cloning as premium |
| Video rendering cost/speed | Poor UX | P0 start with image carousel + subtitles, no complex rendering |
| **Link fetching depends on third-party (yt-dlp-style)** | Site changes/anti-scraping cause fetch failures; copyright risk | On fetch failure, fallback to manual upload; clarify user authorization responsibility; defer non-core sources |
| **ASR is external dependency (Whisper-style, MiniMax doesn't provide)** | Adds service/cost layer; multi-language accuracy fluctuation | Transcript input bypasses ASR; choose mature ASR service; dirty transcripts go through manual/Agent correction |
| Copyright issues (music/images) | Legal risk | Use royalty-free materials, clarify user responsibility |
| Users can't write voice settings | Output doesn't meet expectations | Provide default templates and preview features |
| GDPR compliance audit | Legal risk (future) | Plan EU deployment via Cast AI Kimchi or EU cloud region; prepare compliance docs before institutional sales |
| Cross-border data transfer risk (Schrems II) | European institutional procurement blocked (future) | EU project data stays in EU; provide data processing proof; not required for MVP seed customers |
| European institutional procurement cycle is long | Slow commercialization | Early focus on seed customers and academic conference organizers |

### 16.2 Assumptions

- User-uploaded material audio/video quality is acceptable (or transcript provided)
- Talk content has clear, shareable viewpoints and structure
- User is willing to spend 5-10 minutes on final review
- MiniMax M3 stably outputs structured JSON within 512K context
- European institutional users accept the "AI generate + human review" workflow
- For future EU institutional customers, an EU deployment option (e.g. Cast AI Kimchi or EU cloud region) will be available before sales engagement

---

## 17. Roadmap

See [SCHEDULE.md](./SCHEDULE.md) for detailed schedule.

### Phase 1: P0 MVP (6 weeks)

**Goal**: Run through the core loop of "upload → AI generate scripts → human review → export", validating product-market fit in Europe.

**Tech stack**: FastAPI + MiniMax M3 + hand-rolled Agent + TanStack Start + PostgreSQL + S3-compatible object storage (TOS).

**Includes**:
- Speaker Profile creation + style persona (Persona Agent)
- Video/audio/transcript/slides/image upload
- ASR transcription (faster-whisper, word-level timestamps)
- MiniMax M3 generation: 3-5 clip scripts + social post + quote cards + carousel + article + multi-language versions (German/French/Spanish/Italian)
- Agent closed loop: Script → Review → Reviser (self-review iteration)
- Human review + feedback regeneration (HITL)
- Vertical clip rendering via Remotion (MP4 + SRT)
- Voice-clone dubbing via MiniMax voice_clone + T2A
- Export copy, quote card images, ZIP archive
- Project-scoped chat for natural-language revisions

**Excludes**: link auto-fetch, slide OCR, multi-language UI, complex multi-track editing, social media publishing, EU data residency, GDPR compliance docs.

> **v0.4 adjustment**: Vertical clip output + editor (including ASR + Range streaming endpoint + Remotion rendering + Descript-style transcript editor) has been **elevated to MVP mandatory main flow**, no longer in Phase 2. Object storage still deferred to scale per ADR-011. See ADR-016 / VIDEO_EDITOR.md.

### Phase 2: P1 (6-8 weeks)

**Goal**: Productization preparation, expand input and output capabilities, improve UX.

- Paste link auto-fetch (YouTube / Vimeo / podcasts, yt-dlp-style)
- Slide OCR (PDF/PPT/PPTX → images + searchable text)
- More subtitle styles and brand template options
- Object storage migration (S3/R2/MinIO)
- Multi-language UI (English/German/French/Spanish/Italian)
- Analytics and user system foundations

### Phase 3: P2 (8-12 weeks)

**Goal**: SaaS-ify, scale European market.

- User system and permissions (multi-tenant)
- Billing system (European pricing 20-30% higher than US)
- Direct publishing to LinkedIn and other professional networks (API integration)
- AI-generated dynamic B-roll
- Analytics (virality tracking)
- More platform formats
- EU data residency option (via Cast AI Kimchi or EU cloud region)
- GDPR compliance documentation
- European local sales team (London/Berlin)
- Partnership with academic conference organizers (batch customer acquisition)

---

## 18. Glossary

| Term | Description |
|:---|:---|
| Repurposing | Reprocessing existing content to adapt to different platforms and formats |
| Speaker Profile | Speaker profile, including style persona, voice settings, voice samples |
| Clip | Generated highlight segment |
| Hook | Attention-grabbing opening sentence for video/post |
| Carousel | Multi-page images + text, common on LinkedIn/Instagram and other social platforms |
| SRT | Subtitle file format |
| Persona | Persona style profile |
| B-roll | Supplementary visual material |
| HITL | Human-in-the-Loop, human feedback closed loop |
| EU data residency | Deployment in EU region (e.g. Cast AI Kimchi or EU cloud region), data stays in EU; future differentiator, not in MVP |
| GDPR | EU General Data Protection Regulation |
| GPAI | General Purpose AI, general AI model (EU AI Act term) |
| Virality Score | Virality potential score (0-100), predicts content's viral potential |

---

## 19. Open Decisions

| Item | Proposal | Decision Maker | Status |
|:---|:---|:---|:---|
| Product name | SpeechRepurposer (internal, adjustable) | Zuo | TBD |
| Agent framework selection | **Decided: P0 hand-rolled** | Tech | **Decided** |
| URL input support | Not this cycle, can be added later | Product/Tech | TBD |
| First-phase supported languages | Chinese/English + German/French/Spanish/Italian (P0) | Product | **Decided** |
| EU data residency | Via Cast AI Kimchi or EU cloud region (P2) | Tech | **Decided** |
| Voice cloning | P0 implemented via MiniMax voice_clone + T2A; general TTS fallback available | Product | **Decided** |
| Social media publishing API integration | Consider in P2 | Product | TBD |
| Pricing model | Not designed this cycle | Zuo | TBD |
| European company registration | Q3 launch UK Limited Company | Operations | TBD |
| Academic conference partnerships | Q3 contact ECA, EMBO, London Tech Week | Marketing | TBD |

---

## 20. Agent Framework Selection Decision

### 20.1 Why Agent Workflow is Needed

When users say "not satisfied", it's usually not a full redo, but a local issue:

| Dissatisfaction Type | Handling |
|:---|:---|
| Overall style doesn't sound like me | Return to Speaker Profile for recalibration |
| A certain clip isn't engaging enough | Only regenerate this clip |
| Hook doesn't work | Only regenerate title/hook |
| Translation unnatural | Only retranslate this segment |
| Visuals don't match subtitles | Only change visual prompts or B-roll |
| A certain quote isn't powerful enough | Only regenerate quote card |
| Factually inaccurate | Prompt user to check source materials, do not auto-correct |
| Overall too complex/too simple | Regenerate by audience |

Therefore the system cannot be "generate once and done", it must be: **generate draft → user feedback/self-review → locate issue → local regenerate → user confirm**.

### 20.2 Candidate Frameworks

| Framework | Core Positioning | Suitability for This Project |
|:---|:---|:---|
| **Pydantic AI** | Type-safe LLM Agent | High, but needs MiniMax Custom Model |
| **LangGraph** | Complex state machine workflow | High, strongest HITL, but steep learning curve |
| **ControlFlow** | Structured Agent task flow | High, clearest code, but small ecosystem |
| **CrewAI** | Role-playing multi-Agent | Medium, simple API but weak control |
| **dspy** | LLM program optimization | Medium, suitable for continuous prompt optimization |
| **Hand-rolled** | Self-developed Agent orchestrator | High, fully controllable |

### 20.3 Hand-rolled vs Pydantic AI Comparison

| Dimension | Hand-rolled | Pydantic AI |
|:---|:---|:---|
| Development speed (P0) | Fast, write directly by business | Slightly slower upfront, need MiniMax adapter |
| Learning cost | Low | Medium |
| Type safety | Self-use Pydantic validation | Framework built-in, more elegant |
| MiniMax compatibility | Direct call, zero adaptation | Needs Custom Model adapter |
| Debug/observability | White box | Somewhat black box |
| Module decoupling | Fully controllable | Constrained by framework |
| Future extensibility | Code may get messy | Cleaner |
| Framework risk | None | New framework, potential issues |

### 20.4 Decision Conclusion

**P0 adopts "hand-rolled Agent workflow" solution.**

Reasons:
1. Project scenario is clear, single model (MiniMax M3), doesn't need framework's provider abstraction
2. Workflow is clear (persona → analyze → script → review → revise → HITL), not an open-ended Agent
3. Prompts need fine control, framework templates may not be flexible enough
4. MiniMax M3 needs adaptation, framework advantage is weakened
5. Team is familiar with FastAPI/Pydantic, hand-rolled is just combining these capabilities
6. P0's core is validating "content generation quality", not validating "Agent framework capability"

**Future**: If P1/P2 workflow becomes too complex to maintain in code, evaluate migration to Pydantic AI or LangGraph.

### 20.5 Hand-rolled Architecture Recommendation

```
apps/api/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration management
│   ├── dependencies.py      # Dependency injection
│   ├── worker.py            # Standalone worker process entry point
│   ├── routers/             # API routes
│   │   ├── speakers.py
│   │   ├── projects.py      # Includes generation, export, jobs, clips, derivatives
│   │   ├── assets.py
│   │   ├── clips.py         # Review, render trigger, caption translation
│   │   ├── derivatives.py
│   │   ├── files.py         # Range streaming endpoints (uploads/outputs/music)
│   │   ├── intent.py        # /infer-intent
│   │   └── brand_templates.py
│   ├── services/            # Business logic
│   │   ├── jobs.py          # Queue claiming
│   │   ├── asset_processing.py   # Processing dispatch: ASR / text extraction / slide page rendering / image vision
│   │   ├── generation.py    # Generation flow orchestration
│   │   ├── derivative_dispatch.py # Thin registry for derivative agents
│   │   ├── rendering.py     # Calls Remotion rendering service
│   │   ├── clip_spec.py     # clip-spec construction
│   │   ├── brand.py         # Brand template → ClipBrand/ClipMusic/BrandContentStrategy
│   │   ├── extraction.py    # Text/PDF extraction + PyMuPDF per-page image rendering
│   │   ├── vision.py        # M3 vision: image → key point text
│   │   ├── voice.py         # Voice cloning + T2A synthesis + video audio track extraction
│   │   ├── caption_translate.py  # Caption track translation
│   │   ├── storage.py       # Storage seam
│   │   └── asr.py           # faster-whisper
│   ├── models/              # Database models + Pydantic schemas
│   │   ├── database.py
│   │   ├── schemas.py
│   │   └── tables.py
│   ├── agents/              # Agent steps
│   │   ├── base.py          # Shared MiniMax agent base + helpers
│   │   ├── persona.py
│   │   ├── content_director.py
│   │   ├── clip_agent.py
│   │   ├── reviser.py
│   │   ├── post.py
│   │   ├── quotes.py
│   │   ├── carousel.py
│   │   ├── article.py
│   │   ├── intent.py
│   │   └── caption_translate.py
│   ├── prompts/             # Jinja2 templates
│   └── clients/
│       └── minimax.py       # MiniMax M3 wrapper
├── migrations/              # Alembic migration scripts
├── pyproject.toml
└── Dockerfile
```

### 20.6 Key Design Points

1. **Each Agent step is a pure function**: input context + prompt, output Pydantic model
2. **Unified MiniMax client**: encapsulates calling, JSON cleaning, retry, error handling
3. **Workflow records each step's state**: facilitates debugging and HITL recovery
4. **User feedback is structured**: not free text, but select reason + optional supplementary note
5. **Version history**: each regeneration saves old version, supports A/B comparison and rollback

### 20.7 Dependency Libraries (Non-Framework)

Hand-rolled doesn't mean from scratch, these libraries can be used:

| Purpose | Library |
|:---|:---|
| HTTP calls | httpx |
| Data validation | pydantic |
| Retry mechanism | tenacity |
| Prompt templates | jinja2 |
| Async tasks | asyncio / task queue |
| Logging | structlog / logging |
| Database | SQLAlchemy etc. |

---

## 21. Document History

| Version | Date | Changes | Author |
|:---|:---|:---|:---|
| v0.1 | 2026/06/22 | Initial PRD (General Edition) | Product Team |
| v0.2 | 2026/06/22 | Added Agent framework selection decision, refined technical architecture | Tech Team |
| v0.3 | 2026/06/24 | Europe Edition: incorporated market research, multi-language P0, EU data residency, Agent workflow, European user personas, roadmap adjustment | Product Team + Market Research Team |
| v0.4 | 2026/06/27 | Vertical clip output + editor finalized (elevated to MVP main flow): clip-spec contract + Remotion first renderer + Descript-style transcript editor; ASR elevated to hard prerequisite (video needs streamable playback, local FS + Range sufficient; object storage still deferred to scale) (see ADR-016 / VIDEO_EDITOR.md) | Tech Team |
