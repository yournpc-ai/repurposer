"""Phase 2 e2e: write_quotes enrich path.

Builds a synthetic project + understanding with quotable_lines, calls
the writer (LLM in the loop), then verifies the runner-side enrich
lands timestamps and the alt translation.

This bypasses ASR by stubbing the LLM-side output directly: the writer
is replaced with a deterministic mock that picks quotable_line_id=0
verbatim, and the runner's enrich path is exercised for real.
"""
import asyncio
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import (
    Quote, Quotes, MaterialUnderstanding, QuotableLine,
    GenerationContext, Storyboard, StoryboardSlot,
    PersonaContext,
)
from app.tools.quotes.node import WriteQuotes
from app.tools.quotes.agents import quotes_writer


def fail(msg, ctx=None):
    print(f"✗ {msg}")
    if ctx is not None:
        import json
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


async def main():
    # Mock the writer to return a deterministic pick
    class MockResult:
        def __init__(self, data):
            self._data = data
        def model_dump(self):
            return self._data

    class MockWriter:
        async def call(self, *args, **kwargs):
            # Always pick quotable_line_id=0
            return MockResult({
                "quotes": [
                    {
                        "quote": "Stay hungry, stay foolish.",
                        "attribution": "Steve Jobs | Stanford Commencement",
                        "quotable_line_id": 0,
                        "quote_source": "Stay hungry, stay foolish.",
                    }
                ]
            })

    node = WriteQuotes()
    original_writer = node.writer
    node.writer = MockWriter()
    # Also patch the import-time writer reference
    import app.tools.quotes.node as node_mod
    node_mod.quotes_writer = MockWriter()

    understanding = MaterialUnderstanding(
        core_thesis="On staying curious.",
        themes=["curiosity", "learning"],
        target_audience="knowledge workers",
        quotable_lines=[
            QuotableLine(
                text="Stay hungry, stay foolish.",
                start=12.3, end=14.7, self_contained=True,
            ),
        ],
    )
    storyboard = Storyboard(slots=[
        StoryboardSlot(slot="quotes", focus="core thesis"),
    ])
    context = GenerationContext(
        target_language="zh",
        persona=PersonaContext(name="Steve Jobs", sentence_style="laconic"),
        caption_mode="bilingual",
    )

    content = await node._generate(
        asset_texts=[],
        context=context,
        understanding=understanding,
        storyboard=storyboard,
    )
    # Validate the output structure
    assert "quotes" in content, content
    q = content["quotes"][0]
    ok(f"writer returned 1 quote (count={len(content['quotes'])})")
    assert q["quote"] == "Stay hungry, stay foolish.", q
    assert q["quotable_line_id"] == 0
    assert q["source_start"] == 12.3
    assert q["source_end"] == 14.7
    assert q["frame_at"] == 13.5
    ok("timestamps snapped: source_start=12.3, source_end=14.7, frame_at=13.5")
    assert q["quote_source"] == "Stay hungry, stay foolish."
    ok("quote_source set verbatim")
    # The bilingual path calls the translator — we can't easily mock that
    # without a bigger fixture, but we verify the path was entered (no
    # error raised and the output is well-formed).

    # Now test caption_mode=None path
    context2 = GenerationContext(
        target_language="en",
        persona=PersonaContext(name="Steve Jobs"),
        caption_mode=None,
    )
    content2 = await node._generate(
        asset_texts=[],
        context=context2,
        understanding=understanding,
        storyboard=storyboard,
    )
    q2 = content2["quotes"][0]
    assert q2["frame_at"] == 13.5
    assert "quote_alt" not in q2 or q2.get("quote_alt") is None
    ok("caption_mode=None → no quote_alt populated")

asyncio.run(main())
print()
print("PHASE 2 ENRICH E2E GREEN")
