"""Providers — the single home for external-service wrappers (N-42 批④).

A provider wraps a real external service or engine (object storage, ASR,
voice cloning/TTS, vision); the LLM Model seam lives one layer down in
``providers/llm/``. Deterministic mechanics with a single consumer
live in that consumer's tool package instead (dubbing → tools/dub, filler
detection → tools/filler). The iron rule (N-29, new seat): nothing here may
import the decision layer (``app.agents``) or the LLM client — enforced by
``scripts/check_gates.py``.
"""
