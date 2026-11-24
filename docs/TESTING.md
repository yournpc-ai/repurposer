# Testing — Chat-Origin 4-Layer Test Architecture

Rookie Cut is a Chat-Origin video creation studio: every user action enters through `POST /api/v1/chat` and the Studio Workbench. The test suite mirrors that surface in four layers, prioritizing fast deterministic feedback on real user contracts and cross-runtime parity.

## 1. The 4-Layer Pyramid

| Layer | Location | Marker / Runner | Runtime Target | Dependencies | Owned Invariants |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Layer 0 · Pure Contracts & Parity** | `apps/api/test/unit/`, `packages/video-spec/`, `packages/sound-engine/` | `pytest -m unit`, `pytest -m parity`, `pnpm test` | Fast (seconds) | Zero DB, zero LLM, zero network | Timing quantization, `video-spec` Zod parity, 4 `CompositionStyle` + WCAG contrast Py↔TS parity, 11 `TextStyle` + bilingual cinema Py↔TS parity, 22 `sound-engine` v2 recipes Py↔TS parity, 13 Motion Blocks + slot-preview compiler parity, draw-2d/Remotion generator budgets, scrub previews, rendered-artifact probe gate, output audio/video signal checks, SKU pricing/metering/Stripe adjudication, external skill archive safety & `/text-animation`, web capture SSRF IP truth table & readiness, LLM streaming wire/trace protocol, Chat turn tool-surface policy, Layer 3 eval scorer & media probes. |
| **Layer 1A · Chat-Origin Integration** | `apps/api/test/chat_origin/` | `pytest -m chat_origin` | Fast (single session DB) | Real disposable PostgreSQL + FastAPI ASGI (`/api/v1/chat`) + scripted LLM | End-to-end SSE & JSON `/api/v1/chat` creation (`create_video` shots & direct `motion_blocks`, `style_preset`, zero internal ID leakage), multi-turn editing (`set_composition_style`, `insert_text`/`edit_text`, `insert_motion_block` auto-extend, atomic `generate_sfx`, split/trim/move, uploaded video & narration), live observation & side-chat (`update_focus`, `update_steps`, semantic `detail` replay, pending approval/question tangent Q&A, explicit `skip`, paid-credit non-bypass), Project `1:N` Conversation & shared assets, `/compact` context pruning, `message_feedback` Eval `context_snapshot` freeze, `/workbench` active jobs & owner 404 isolation, Skill Blueprints (`save_composition_as_skill` → `instantiate_skill_blueprint` → `/api/v1/skills/{id}/slot-preview`), paid media authorization gates, export/stop commit races, presentation ACK, and media preparation/recovery. |
| **Layer 1B · Infrastructure & Platform** | `apps/api/test/infra/` | `pytest -m infra` | Fast (single session DB) | Real disposable PostgreSQL | FastAPI boot & OpenAPI core route check, single Alembic head + `alembic upgrade head` vs `Base.metadata` table/column parity, Composition CAS write door & idempotency replay, `local://` storage adapter & loopback route, export public URLs & staging cleanup, project/job deletion lock ordering, worker asset claims, owner-scoped Skill store, idempotent publication dispatch, account settings & session revocation. |
| **Layer 2 · Frontend Studio & Renderer** | `apps/web/src/**/*.test.*`, `apps/render/src/**/*.test.ts` | Vitest (`apps/web`), `tsx --test` (`apps/render`), `tsc --noEmit` | Seconds | jsdom / Node (zero backend) | Studio Workbench split pane & Markdown artifact links, multi-conversation thread/timeline projection, ActivityStream & QuestionDock, MessageActionBar feedback, WaveformPlayer & preview spec, EN↔ZH i18n dictionary key & `{{placeholder}}` parity (`apps/web/src/lib/i18n/parity.test.ts`), Remotion render artifact caching, audio staging, upload recovery, and component runtime dynamics. |
| **Layer 3 · Live Chat-Origin Audiovisual Eval** | `apps/api/scripts/eval_chat_e2e.py` | `make eval-chat` (explicit opt-in) | Minutes (live LLM) | Disposable PostgreSQL (`alembic upgrade head`) + `local://` storage + live LLM | Real `/api/v1/chat` multi-turn SSE execution, live `focus`/`steps`/`detail` capture, tool-usage efficiency (`remove_clip` count, iteration bounds), zero internal ID leaks, `message_feedback` Eval snapshot verification, 1080p H.264 + 48 kHz AAC MP4 probing, mid-act PNG extraction, non-black visual & audible non-clipping checks; emits `eval_scorecard.json` + `EVAL_REPORT.md`. |

## 2. Developer Commands

All deterministic gates are unified in the root `Makefile`:

```sh
make test-fast    # Layer 0 pure API unit/parity + video-spec + sound-engine + Web tsc
make test-chat    # Layer 1A Chat-Origin deterministic integration suite
make test-infra   # Layer 1B infrastructure, storage, CAS store & Alembic parity suite
make test-api     # Full API deterministic suite (Layer 0 + Layer 1A + Layer 1B)
make test-web     # Layer 2 Web TypeScript check + Vitest (incl. EN<->ZH i18n parity)
make test-render  # Layer 2 Render service TypeScript check + Node tests
make test-all     # Full monorepo deterministic gate (zero live LLM / zero paid media)
```

Live Layer 3 audiovisual evaluation (opt-in, uses live LLM quota):

```sh
make eval-list                                   # List registered eval scenarios
make eval-chat SCENARIO=motion_block_promo       # Run live scenario -> scratch/eval-chat/
```

Offline media probe against an already rendered MP4:

```sh
cd apps/api && uv run python scripts/eval_chat_e2e.py \
  --probe-mp4 /path/to/film.mp4 --out-dir ../../scratch/eval-probe
```

## 3. Database Isolation & Speed Architecture

- `apps/api/test/conftest.py` creates **one** session-scoped disposable PostgreSQL database with `synchronous_commit = off` and runs `Base.metadata.create_all` once at session start, dropping it once at session end.
- Every DB test receives a clean database via a single pooled-connection batched `DELETE` across all tables (~5–7 ms per test) and disposes its async engine in `finally` to prevent connection leaks.
- Shared DB/ASGI/media helpers live in `apps/api/test/support/` so test modules never import from other test modules.
- `apps/api/test/infra/test_platform_boot_and_migrations.py` verifies on a fresh database that `alembic upgrade head` produces a single head whose tables and columns exactly match `Base.metadata`.

## 4. Authoring Rules

- **Test contracts, not prompt prose**: Never lock exact prompt wording or internal helper constants; verify observable tool schemas, state transitions, SSE frames, database truth, and Py↔TS parity.
- **Keep Layer 0 DB-free**: Tests under `apps/api/test/unit/` must never request the `database` fixture or make network/browser calls.
- **Enter through `/api/v1/chat` for user flows**: New Chat-Origin features add deterministic coverage under `apps/api/test/chat_origin/` using `full_api_client` + `ScriptedToolClient` + `bind_test_database`.
- **Maintain EN↔ZH parity**: Every new key in `apps/web/src/lib/i18n/locales/en.ts` must mirror into `zh.ts` with identical `{{placeholder}}` names; `parity.test.ts` enforces this on every `make test-web`.
