"""Phase 3 e2e: build_quote_card_spec — the recipe adapter's clip-spec wire.

Three branches exercised:

1. Bilingual: caption_track = verbatim source, translation_track = alt.
2. Source-only: caption_track present, translation_track empty.
3. Target-only: caption_track still carries the source text (the chat
   layer's "target_only" decision is a HEADLINE choice — Phase 3 just
   ships the text + alt together when bilingual; the alt drops on
   non-bilingual modes by the same predicate).

Plus negative paths:
- Missing source asset → None
- Source asset without words → None
- Quote missing source_start/source_end → None

The runner-side snap (Phase 2's _enrich_quote_cards) is exercised
indirectly: the input Quote here carries the post-snap timestamps, so
build_quote_card_spec reads them off directly.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.clip_spec import build_quote_card_spec


def fail(msg, ctx=None):
    print(f"✗ {msg}")
    if ctx is not None:
        import json
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


def _fake_video(*, with_words=True, duration=60.0):
    """Build a minimal Asset stand-in (real Asset has many columns)."""
    meta = {
        "words": [
            {"word": "Stay", "start": 10.0, "end": 10.4},
            {"word": "hungry", "start": 10.4, "end": 10.9},
            {"word": "stay", "start": 11.0, "end": 11.3},
            {"word": "foolish", "start": 11.3, "end": 11.9},
        ]
    } if with_words else {}
    return SimpleNamespace(
        id=uuid4(),
        type="video",
        file_url="user/uploads/demo.mp4",
        duration_seconds=duration,
        meta=meta,
    )


def _quote(**overrides):
    base = {
        "quote": "Stay hungry, stay foolish.",
        "attribution": "Steve Jobs | Stanford Commencement 2005",
        "quotable_line_id": 0,
        "source_start": 10.0,
        "source_end": 12.0,
        "frame_at": 11.0,
        "quote_source": "Stay hungry, stay foolish.",
        "quote_alt": "求知若饥，虚心若愚。",
    }
    base.update(overrides)
    return base


# --- 1. Bilingual ---
spec = build_quote_card_spec(
    _fake_video(),
    _quote(),
    target_language="zh",
    source_language="en",
    caption_mode="bilingual",
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("bilingual: spec is None")
if len(spec.caption_track) != 1:
    fail("bilingual: caption_track should have exactly 1 cue", [c.model_dump() for c in spec.caption_track])
cue = spec.caption_track[0]
if cue.text != "Stay hungry, stay foolish.":
    fail("bilingual: caption text not verbatim source", cue.text)
if cue.lang != "en":
    fail("bilingual: caption lang should be source language (en)", cue.lang)
if cue.start > 10.0 or cue.end < 12.0:
    fail("bilingual: cue window should bracket source span + post-pad", (cue.start, cue.end))
ok(f"bilingual caption: text={cue.text!r} lang={cue.lang} span=[{cue.start:.2f},{cue.end:.2f}]")

if len(spec.translation_track) != 1:
    fail("bilingual: translation_track should have exactly 1 cue", [c.model_dump() for c in spec.translation_track])
alt_cue = spec.translation_track[0]
if alt_cue.text != "求知若饥，虚心若愚。":
    fail("bilingual: alt text missing", alt_cue.text)
if alt_cue.lang != "zh":
    fail("bilingual: alt lang should be target (zh)", alt_cue.lang)
ok(f"bilingual translation: text={alt_cue.text!r} lang={alt_cue.lang}")

if spec.target_language != "zh":
    fail("bilingual: target_language not threaded", spec.target_language)
if spec.aspect != "9:16":
    fail("bilingual: aspect not 9:16", spec.aspect)
if not spec.title.enabled or spec.title.text != "Steve Jobs | Stanford Commencement 2005":
    fail("bilingual: title should carry the attribution", spec.title.model_dump())
if len(spec.segments) != 1:
    fail("bilingual: expected 1 segment", spec.segments)
seg = spec.segments[0]
if seg.start >= seg.end:
    fail("bilingual: segment start>=end", (seg.start, seg.end))
ok(f"bilingual spec: aspect={spec.aspect} title={spec.title.text!r} seg=[{seg.start:.2f},{seg.end:.2f}]")


# --- 2. Source-only ---
spec = build_quote_card_spec(
    _fake_video(),
    _quote(),
    target_language="en",
    source_language="en",
    caption_mode="source_only",
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("source_only: spec is None")
if len(spec.translation_track) != 0:
    fail("source_only: translation_track should be empty", [c.model_dump() for c in spec.translation_track])
if len(spec.caption_track) != 1:
    fail("source_only: caption_track should still have the source cue")
ok("source_only: caption_track present, translation_track empty")


# --- 3. Target-only ---
# User wants only the target-language reading shown — caption_track carries
# the LLM's quote (target language), no source cue, no translation track.
spec = build_quote_card_spec(
    _fake_video(),
    _quote(),
    target_language="en",
    source_language="en",
    caption_mode="target_only",
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("target_only: spec is None")
if len(spec.translation_track) != 0:
    fail("target_only: translation_track should be empty", [c.model_dump() for c in spec.translation_track])
if len(spec.caption_track) != 1:
    fail("target_only: caption_track should have exactly 1 cue (the target)", [c.model_dump() for c in spec.caption_track])
cue = spec.caption_track[0]
if cue.text != "Stay hungry, stay foolish.":
    fail("target_only: caption text should be the target-language quote", cue.text)
if cue.lang != "en":
    fail("target_only: caption lang should be target (en)", cue.lang)
ok(f"target_only: caption={cue.text!r} lang={cue.lang} (single main line)")


# --- 4. None mode (legacy / no caption-mode decision yet) ---
# Default = bilingual if quote_alt is present (the runner filled it),
# else single-language. The test data has quote_alt filled, so the
# bilingual fallback applies.
spec = build_quote_card_spec(
    _fake_video(),
    _quote(),
    target_language="zh",
    source_language="en",
    caption_mode=None,
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("none-mode w/ alt: spec is None")
if len(spec.translation_track) != 1:
    fail("none-mode w/ alt: translation_track should have 1 cue (bilingual fallback)", [c.model_dump() for c in spec.translation_track])
if len(spec.caption_track) != 1:
    fail("none-mode w/ alt: caption_track should have 1 cue (the source)")
ok("none-mode w/ alt: bilingual fallback (translation_track filled)")

# Same None mode, but quote_alt is missing — should fall back to single-lang.
spec = build_quote_card_spec(
    _fake_video(),
    _quote(quote_alt=None),
    target_language="zh",
    source_language="en",
    caption_mode=None,
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("none-mode no alt: spec is None")
if len(spec.translation_track) != 0:
    fail("none-mode no alt: translation_track should be empty", [c.model_dump() for c in spec.translation_track])
if len(spec.caption_track) != 1:
    fail("none-mode no alt: caption_track should have 1 cue (source)")
ok("none-mode no alt: single-language fallback (translation_track empty)")


# --- 5. Negative: missing source_start ---
spec = build_quote_card_spec(
    _fake_video(),
    _quote(source_start=None),
    target_language="zh",
    source_language="en",
    caption_mode="bilingual",
    brand=None,
    brand_ref=None,
)
if spec is not None:
    fail("missing source_start: expected None, got spec")
ok("missing source_start → None (no time-bind, no card)")


# --- 6. Negative: source asset has no ASR words ---
spec = build_quote_card_spec(
    _fake_video(with_words=False),
    _quote(),
    target_language="zh",
    source_language="en",
    caption_mode="bilingual",
    brand=None,
    brand_ref=None,
)
if spec is not None:
    fail("no words: expected None, got spec")
ok("source has no ASR words → None")


# --- 7. Round-trip to JSON dict (renderer contract check) ---
spec = build_quote_card_spec(
    _fake_video(),
    _quote(),
    target_language="zh",
    source_language="en",
    caption_mode="bilingual",
    brand=None,
    brand_ref=None,
)
spec_dict = spec.model_dump(mode="json")
# Renderer contract invariants:
for k in ("source", "aspect", "segments", "caption_track", "translation_track",
          "caption_style_preset", "title", "music", "target_language"):
    if k not in spec_dict:
        fail(f"renderer contract: missing key {k}", list(spec_dict.keys()))
if spec_dict["caption_style_preset"] != "clean-bottom":
    fail("renderer contract: caption_style_preset not clean-bottom", spec_dict["caption_style_preset"])
if spec_dict["source"]["kind"] != "video":
    fail("renderer contract: source.kind not video", spec_dict["source"])
ok("renderer contract: all required keys present + source.kind=video + clean-bottom preset")


# --- 8. Locate span snaps to word boundaries ---
# Quote at 10.5–10.8 — start_idx is the first word whose start >= 10.5
# (idx 2, "stay" at 11.0); end_idx is the last word whose end <= 10.8,
# but word 1 ("hungry" ends 10.9) fails, so the helper falls back to
# len(words)-1 (idx 3, "foolish"). After pre-pad the start is bounded by
# the prior word's end (10.9) — never past it.
spec = build_quote_card_spec(
    _fake_video(),
    _quote(source_start=10.5, source_end=10.8),
    target_language="zh",
    source_language="en",
    caption_mode="bilingual",
    brand=None,
    brand_ref=None,
)
if spec is None:
    fail("snap test: spec is None")
cue = spec.caption_track[0]
# start_idx=2 (stay, start=11.0) → start = 11.0
# pre_pad: floor = words[1].end = 10.9 → start = max(10.9, 11.0 - 0.12) = 10.9
# end_idx=3 (foolish, end=11.9) → end = 11.9
# post_pad: candidates = [11.9 + 1.8 = 13.7, 60.0] → end = min(13.7, 60.0) = 13.7
expected_start = 10.9
expected_end = 13.7
if abs(cue.start - expected_start) > 0.01:
    fail(f"snap test: cue start {cue.start} != expected {expected_start}")
if abs(cue.end - expected_end) > 0.01:
    fail(f"snap test: cue end {cue.end} != expected {expected_end}")
ok(f"snap test: cue=[{cue.start:.2f},{cue.end:.2f}] (expected [{expected_start:.2f},{expected_end:.2f}])")


print("\n✓ all build_quote_card_spec assertions passed")