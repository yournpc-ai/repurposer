# Development Schedule & Roadmap

> Based on P0 internal validation and future SaaS goals.

---

## 1. P0 Development Schedule (6 Weeks)

**P0 Goal**: Close the core loop: "Upload talk material -> AI generates script -> Simple render -> Human review -> Export".

### Week 1: Project Foundation & Data Layer

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | Project environment setup | `apps/api/` and `apps/web/` runnable, Docker Compose launches PostgreSQL | Backend / Frontend |
| Day 2-3 | Database schema design | SQLAlchemy models: `User`, `Speaker`, `Project`, `Asset`, `Clip`, `Derivative`, `WorkflowRun`, `WorkflowStep` | Backend |
| Day 3-4 | File upload API | `POST /api/v1/projects/{id}/assets`, local filesystem storage | Backend |
| Day 4-5 | Speaker / Project CRUD | Speaker creation, project creation, list / detail APIs | Backend |
| Day 5 | Frontend foundation pages | TanStack Start routing, Speaker list page, Project list page | Frontend |

**Week 1 Milestone**: Backend API can create Speakers and Projects; frontend can display lists.

**Risk**: TanStack Start environment setup may be more complex than expected; reserve 1 day buffer.

---

### Week 2: Speaker Style Persona

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | MiniMax Client wrapper | `clients/minimax.py`: calls, JSON parsing, retry, error handling | Backend |
| Day 2-3 | Pydantic schemas | `SpeakerPersona`, `ClipScript`, `StyleReview`, etc. | Backend |
| Day 3-4 | Persona Agent + prompt | Generate style persona from past materials, Jinja2 templates | Backend |
| Day 4-5 | Speaker material upload UI | Text / PDF upload, style persona display / edit page | Frontend |
| Day 5 | API integration | Frontend can call persona generation endpoint | Frontend + Backend |

**Week 2 Milestone**: After uploading past materials, the system can generate and display a Speaker style persona.

**Risk**: Stability of MiniMax M3 persona output; may need multiple rounds of prompt tuning.

---

### Week 3: Content Analysis & Script Generation

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | Content Director Agent | Unified content plan: thesis, themes, audience, per-output plans | Backend |
| Day 2-4 | Clip Agent | Select segments and generate vertical clip scripts from the content plan | Backend |
| Day 4-5 | Derivative Agents | LinkedIn / Quote / Summary agents wired to the shared ContentPlan | Backend |
| Day 5 | Generation trigger API | `POST /api/v1/projects/{id}/generate` runs the workflow | Backend |

**Week 3 Milestone**: After inputting a transcript, the system can generate 3 clip scripts plus derivative copy.

**Risks**:
- Director plan quality needs human calibration
- Clip Agent quality for Chinese academic speech colloquialization

---

### Week 4: Review & Feedback Loop

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | Reviser Agent | Local regeneration of hook / script based on feedback | Backend |
| Day 2-3 | LinkedIn Agent | Generate long-form post copy | Backend |
| Day 3-4 | Quote Agent | Generate quote card copy | Backend |
| Day 4-5 | Review UI | Left clip list + right preview / editor + feedback buttons | Frontend |
| Day 5 | Integration | Frontend can edit scripts, submit feedback, trigger regeneration | Frontend + Backend |

**Week 4 Milestone**: Users can review AI-generated content in the frontend and submit feedback for regeneration.

**Risk**: HITL (human-in-the-loop) feedback loop state management needs clear design.

---

### Week 5: Rendering & Export

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | Video rendering | MoviePy image slideshow + subtitles + BGM -> MP4 | Backend |
| Day 2-3 | Quote card rendering | HTML/CSS + Puppeteer -> PNG | Backend |
| Day 3-4 | Export API | `POST /api/v1/projects/{id}/export` | Backend |
| Day 4-5 | Export UI | Frontend download video, copy, images | Frontend |
| Day 5 | End-to-end test | One complete project from upload to export | Whole team |

**Week 5 Milestone**: Can go from uploaded transcript to exported video / copy / quote card.

**Risks**:
- MoviePy Chinese fonts, subtitle styling may need debugging
- Video rendering performance (acceptable to be slow in P0)

---

### Week 6: Testing, Tuning & Demo Prep

| Days | Task | Deliverable | Owner |
|:---|:---|:---|:---|
| Day 1-2 | Prompt tuning | Test with 3-5 real talk cases, optimize output quality | Backend |
| Day 2-3 | Bug fixes | Fix issues found during integration | Whole team |
| Day 3-4 | Demo data prep | Prepare 1-2 complete demo cases | Product / Backend |
| Day 4-5 | Demo & P1 planning | Demo to Zuo, compile P1 requirements | Whole team |

**Week 6 Milestone**: P0 demoable, P1 requirement list confirmed.

---

## 2. P0 Key Milestones

| Time | Milestone | Acceptance Criteria |
|:---|:---|:---|
| End of Week 1 | Foundation ready | Docker Compose can launch all services, API and frontend accessible |
| End of Week 2 | Persona generation | After uploading past materials, can generate an editable style persona |
| End of Week 3 | Script generation | Input transcript can generate 3 clip scripts |
| End of Week 4 | Review loop closed | Frontend can edit scripts, submit feedback, regenerate |
| End of Week 5 | End-to-end working | Full upload-to-export pipeline available |
| End of Week 6 | P0 Demo | Demo to Zuo, confirm P1 direction |

---

## 3. Suggested Team Roles

| Role | Responsibilities | Approx. Workload |
|:---|:---|:---|
| **Backend Engineer 1** | FastAPI, database, MiniMax client, Agent workflow | Primary |
| **Backend Engineer 2 / AI Engineer** | Prompt engineering, Agent tuning, video rendering | Primary |
| **Frontend Engineer** | TanStack Start pages, upload components, review UI | Medium |
| **Product Manager / Zuo** | Requirement confirmation, demo cases, quality acceptance | Participating |

**Minimum team**: 2 backend + 1 frontend.

---

## 4. Risks & Buffers

| Risk | Impact | Mitigation |
|:---|:---|:---|
| TanStack Start setup complexity | Week 1 delay | If not solved in 2 days, fall back to Vite + TanStack Router |
| MiniMax M3 output instability | Week 2-3 delay | Add prompt tuning time, prepare fallback to GPT/Claude |
| Video rendering issues | Week 5 delay | P0 can start with "image + subtitle" preview, MP4 not mandatory |
| Insufficient frontend resources | Week 4-5 delay | Simplify review UI first, prioritize backend workflow |

---

## 5. P1 Plan (6-8 Weeks, Goal: Productization Prep)

| Module | Content |
|:---|:---|
| Media expansion | Video / audio upload + auto-transcription (FunASR / iFLYTEK) |
| Slide parsing | PDF / PPT page splitting + OCR |
| Voice sample | Upload voice sample + voice cloning |
| Multilingual | Chinese-English translation + generic TTS dubbing |
| Video rendering upgrade | More subtitle styles, B-roll, layout switching |
| Brand kit | Subtitle font / color / logo templates |
| Batch export | Packaged download of all project outputs |
| Object storage | Migrate to MinIO / cloud storage |
| Task queue | Introduce Celery + Redis |

---

## 6. P2 Plan (8-12 Weeks, Goal: SaaS)

| Module | Content |
|:---|:---|
| User system | Registration / login, multi-user, permission management |
| Billing system | Per-project / per-minute / per-generation billing |
| Multi-tenancy | Team / organization isolation |
| Social publishing | Direct to LinkedIn / WeChat Channels / Douyin / YouTube Shorts |
| AI B-roll | Auto-generate / match B-roll from script |
| Analytics | View count, engagement rate tracking |
| More platform layouts | X/Twitter, Instagram, Xiaohongshu dedicated layouts |
| API access | Third-party integration endpoints |

---

## 7. Daily / Weekly Rhythm Suggestions

### Daily

- **Standup 15 min**: What did yesterday, what today, blockers
- **Doc sync**: Agent prompt changes, API changes updated in docs promptly

### Weekly

- **Mid-week check**: Wednesday afternoon alignment on progress, adjust priorities if needed
- **Friday demo**: Friday afternoon run through current features, screen recording or live demo
- **Weekend planning**: Confirm next week's tasks by end of Friday

---

## 8. P0 Success Criteria

| Metric | Target |
|:---|:---|
| End-to-end flow | 1 real talk case from upload to export |
| Generation quality | User edit rate < 50% |
| Review time | Human review per project < 15 minutes |
| Demo feedback | Zuo approves direction, clear P1 priorities |

---

## 9. Next Steps

1. Confirm if the schedule is reasonable
2. Confirm team staffing
3. Prepare 1-2 real talk cases as test data
4. Start Week 1 development
