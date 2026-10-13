"""film tool family (MG film skill, ADR-119): launch_film — a captured web
page → a storyboarded launch short. The LLM authors a storyboard (grounded
in the page's capture manifest), code allocates integer frames, the existing
render chain executes the film-spec. The component vocabulary lives in the
render service (human-owned); this package owns orchestration + the
grounding validator."""
