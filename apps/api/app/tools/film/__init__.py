"""film tool family (MG film skill, ADR-119): launch_film — a captured web
page → a storyboarded launch short. Code owns the fixed skeleton (scene
order, durations, camera), the LLM answers bounded creative/citation slots
with a code fixed-fallback (ADR-127), code allocates integer frames, the
existing render chain executes the film-spec. The component vocabulary
lives in the render service (human-owned); this package owns orchestration
+ the grounding validator."""
