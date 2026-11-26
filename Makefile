.PHONY: test-fast test-chat test-infra test-api test-web test-render test-all test-e2e eval-chat eval-list

PYTEST_RUN = cd apps/api && uv run --extra dev python scripts/run_pytest.py

# Layer 0: Pure API unit/parity contracts + shared TS packages + Web typecheck
test-fast:
	@cd apps/api && uv run --extra dev ruff check --select F823,F811 app/
	@$(PYTEST_RUN) test/unit -m unit -q
	@pnpm --dir packages/video-spec test
	@pnpm --dir packages/sound-engine test
	@pnpm --dir apps/web exec tsc --noEmit

# Layer 1A: Flagship Chat-Origin deterministic integration suite (real PG + ASGI /api/v1/chat)
test-chat:
	@$(PYTEST_RUN) test/chat_origin -m chat_origin -q

# Layer 1B: Infrastructure & platform contracts (CAS store, storage, migrations, jobs, settings)
test-infra:
	@$(PYTEST_RUN) test/infra -m infra -q

# Full API deterministic suite (Layer 0 + Layer 1A + Layer 1B)
test-api:
	@$(PYTEST_RUN) test/unit test/chat_origin test/infra -q

# Layer 2: Frontend Studio typecheck + Vitest (includes EN<->ZH i18n parity)
test-web:
	@pnpm --dir apps/web exec tsc --noEmit
	@pnpm --dir apps/web test

# Layer 2: Render service typecheck + Node test suite
test-render:
	@pnpm --dir apps/render typecheck
	@pnpm --dir apps/render test

# Layer 2.5: deterministic Chromium + Studio + FastAPI + PostgreSQL
test-e2e:
	@$(PYTEST_RUN) test/e2e_browser -m e2e_browser -v

# Full monorepo deterministic gate (zero live LLM calls, zero paid media IO)
test-all:
	@$(PYTEST_RUN) test/unit test/chat_origin test/infra -q
	@pnpm --dir packages/video-spec test
	@pnpm --dir packages/sound-engine test
	@pnpm --dir apps/render typecheck
	@pnpm --dir apps/render test
	@pnpm --dir apps/web exec tsc --noEmit
	@pnpm --dir apps/web test

# Layer 3: Reusable Live Chat-Origin Audiovisual Eval Harness (real LLM, disposable PG + local:// storage)
SCENARIO ?= motion_block_promo
OUT_DIR ?= scratch/eval-chat/$(SCENARIO)

eval-list:
	@cd apps/api && uv run python scripts/eval_chat_e2e.py --list-scenarios

eval-chat:
	@cd apps/api && uv run python scripts/eval_chat_e2e.py --scenario $(SCENARIO) --out-dir ../../$(OUT_DIR)
