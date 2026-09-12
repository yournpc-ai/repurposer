"""Pure tests for the multi-version auto-fork (2026-09-13 演示实修).

Scope: compile_graph is pure (no DB/LLM) — the demo-blocking chain
(translate zh bilingual + translate fr + dub es over a whole-source
materialization) must compile to ALL-FORK variants (the recipe precedent,
RECIPES §4.1 "all fork") and pass the one-writer gate; a LONE variant keeps
its in-place morph (status quo); an explicitly-forked recipe-style chain is
idempotent under the pass.
"""

from app.pipeline.orchestrator import TaskSpec, compile_graph
from app.pipeline.tracks import assert_single_writer_per_track
from app.pipeline.graph import NODE_KINDS
import app.tools  # noqa: F401 — the registry door (populates NODE_KINDS)
from app.models.schemas import TaskItem


def _compile(tasks: list[TaskItem]):
    return compile_graph(
        TaskSpec(tasks=tasks),
        materialize_profile="media",
    )


def _variants(nodes):
    return [ns for ns in nodes if ns.kind in ("translate_clip", "dub_clip")]


def _gate(nodes):
    assert_single_writer_per_track(
        ((ns.kind, ns.spec) for ns in nodes),
        lambda kind: bool(NODE_KINDS[kind].produces_outputs),
    )


def test_multi_variant_run_forks_every_variant():
    nodes = _compile(
        [
            TaskItem(tool="translate_clip", params={"target_language": "zh", "bilingual": True}),
            TaskItem(tool="translate_clip", params={"target_language": "fr"}),
            TaskItem(tool="dub_clip", params={"target_language": "es"}),
        ]
    )
    variants = _variants(nodes)
    assert len(variants) == 3
    assert all((ns.spec or {}).get("fork") for ns in variants)
    _gate(nodes)  # the one-writer gate must see zero collisions now


def test_lone_variant_keeps_in_place_morph():
    nodes = _compile([TaskItem(tool="translate_clip", params={"target_language": "fr"})])
    variants = _variants(nodes)
    assert len(variants) == 1
    assert not (variants[0].spec or {}).get("fork")
    _gate(nodes)


def test_explicit_recipe_forks_are_idempotent():
    nodes = _compile(
        [
            TaskItem(tool="dub_clip", params={"target_language": "zh", "fork": True}),
            TaskItem(tool="dub_clip", params={"target_language": "fr", "fork": True}),
        ]
    )
    assert all((ns.spec or {}).get("fork") for ns in _variants(nodes))
    _gate(nodes)
