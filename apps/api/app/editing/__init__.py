"""Editing — the Composition/CompositionVersion content domain (ADR-145).

Owns the work-content truth: schemas, timing law, validators, the single
content write door (``apply_composition_edits``), the version store,
SourceSnapshot bindings, the canonical storyboard read face and the
video-spec compiler. Dependency direction: this module may read
``app.models`` (data layer) only — never ``app.chat`` / ``app.pipeline`` /
``app.tools`` / ``app.providers`` (check_gates enforces).
"""
