"""Phase 2 alt translation e2e: bilingual → translator → quote_alt."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import (
    MaterialUnderstanding, QuotableLine, GenerationContext, Storyboard, StoryboardSlot,
    PersonaContext,
)
from app.tools.quotes.node import WriteQuotes


def fail(msg, ctx=None):
    print(f"✗ {msg}")
    if ctx is not None:
        import json
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


async def main():
    class MockResult:
        def __init__(self, data): self._data = data
        def model_dump(self): return self._data

    class MockWriter:
        async def call(self, *args, **kwargs):
            return MockResult({
                "quotes": [{
                    "quote": "Stay hungry, stay foolish.",
                    "attribution": "Steve Jobs | Stanford",
                    "quotable_line_id": 0,
                    "quote_source": "Stay hungry, stay foolish.",
                }]
            })

    node = WriteQuotes()
    import app.tools.quotes.node as node_mod
    node_mod.quotes_writer = MockWriter()
    node.writer = MockWriter()

    understanding = MaterialUnderstanding(
        core_thesis="curiosity",
        themes=["learning"],
        target_audience="tech",
        quotable_lines=[
            QuotableLine(text="Stay hungry, stay foolish.", start=12.3, end=14.7, self_contained=True),
        ],
    )
    storyboard = Storyboard(slots=[StoryboardSlot(slot="quotes", focus="curiosity")])
    context = GenerationContext(
        target_language="zh",
        persona=PersonaContext(name="Steve Jobs"),
        caption_mode="bilingual",
    )

    content = await node._generate(
        asset_texts=[],
        context=context,
        understanding=understanding,
        storyboard=storyboard,
    )
    q = content["quotes"][0]
    assert q["quote_source"] == "Stay hungry, stay foolish."
    alt = q.get("quote_alt")
    if alt is None:
        fail("bilingual path must populate quote_alt via translator", q)
    if alt == q["quote_source"]:
        fail("alt must differ from source (got the same string back)", {"alt": alt, "src": q["quote_source"]})
    print(f"✓ translator populated quote_alt = {alt!r}")
    print(f"  source = {q['quote_source']!r}")
    print(f"  alt    = {alt!r}")

asyncio.run(main())
print()
print("PHASE 2 ALT TRANSLATION GREEN")
