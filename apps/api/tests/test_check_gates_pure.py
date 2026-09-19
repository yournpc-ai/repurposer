"""Teeth probes for the ADR-087 architecture gates (Phase 2.5 Batch B-5).

A gate that never bites is a comment. These probes pin the gate-5 patterns'
decision boundary BOTH ways — the legal shape must pass (server-stamp reads
stay legal forever; 5c protects GENERATING local truth, never READING the
projection) and the violating shape must fail.

Pure: regex-level only, no app import beyond the gate module itself (which
is paths + compiled patterns at module scope).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_gates as gates  # noqa: E402


# --- 5a: the ToolLoop kernel never speaks Activity construction vocabulary --


def test_5a_bites_on_activity_construction():
    assert gates.BANNED_KERNEL_IMPORT.match("from app.chat.activity import ActivityProjector")
    assert gates.BANNED_KERNEL_IMPORT.match("import app.pipeline.lifecycle")
    assert gates.BANNED_KERNEL_ACTIVITY_VOCAB.search("    frame = ActivityFrame(")
    assert gates.BANNED_KERNEL_ACTIVITY_VOCAB.search('"event": "assistant.activity"')
    assert gates.BANNED_KERNEL_ACTIVITY_VOCAB.search('key = "chat.activity.draft"')
    assert gates.BANNED_KERNEL_ACTIVITY_VOCAB.search("KIND_REPAIR")


def test_5a_legal_kernel_surface_passes():
    # The kernel's actual imports and its docstring's prose naming the
    # boundary are legal — the ban is on CONSTRUCTION vocabulary, not words.
    assert not gates.BANNED_KERNEL_IMPORT.match("from app.providers.llm.base import LLMError")
    assert not gates.BANNED_KERNEL_IMPORT.match("from app.agents.base import AGENTS")
    assert not gates.BANNED_KERNEL_ACTIVITY_VOCAB.search(
        "meaning is the Activity Projection's job, never the kernel's"
    )
    assert not gates.BANNED_KERNEL_ACTIVITY_VOCAB.search(
        "``app/chat/activity.py`` is the channel's only consumer"
    )


# --- 5b: the Lifecycle Projection never imports Presentation -----------------


def test_5b_bites_on_presentation_import():
    assert gates.BANNED_PRESENTATION_IMPORT.match("from app.chat import service")
    assert gates.BANNED_PRESENTATION_IMPORT.match("  import app.chat.routes")
    assert not gates.BANNED_PRESENTATION_IMPORT.match("from app.pipeline.graph import NODE_KINDS")
    assert not gates.BANNED_PRESENTATION_IMPORT.match("from app.tools import validate_task_list")


# --- 5c: the client never generates lifecycle truth locally -------------------


def test_5c_bites_on_local_readiness_derivation():
    # Retired artifact-existence derivation (Phase 1), prose included.
    assert gates.BANNED_CLIENT_LIFECYCLE_DERIVATION.search("const hasDraftGraph = nodes.length > 0")
    assert gates.BANNED_CLIENT_LIFECYCLE_DERIVATION.search("// the hasDraftGraph gate")
    # Local readiness predicates whose RHS never touches the stamp.
    assert gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match(
        '  const planReady = nodes.some((n) => n.state === "draft")'
    )
    assert gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match(
        "const confirmationReady = Boolean(taskBook) && assets.every(ok)"
    )
    assert gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match("const materialReady = assets.length > 0")


def test_5c_stamp_reads_stay_legal():
    # The projection is for READING — server-named stamp consumption must
    # never trip the gate (today's lawful shapes, pinned as positives).
    assert not gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match(
        "  const planReady = lifecycle?.plan_ready ?? false"
    )
    assert not gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match(
        "const confirmationReady = lifecycle ? lifecycle.confirmation_ready : true"
    )
    assert not gates.BANNED_CLIENT_LIFECYCLE_DERIVATION.search(
        "lifecycle?.plan_ready"
    )
    # The stamp's TS type declaration is a definition, not a derivation.
    assert not gates.BANNED_CLIENT_LIFECYCLE_LOCAL.match("  plan_ready: boolean")
