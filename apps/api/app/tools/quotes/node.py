"""write_quotes node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``.

Phase 2 (2026-08-25, RECIPES §4.6.2) divergence: the writer picks by
``quotable_line_id`` only; timestamps and ``quote_alt`` are snapped
runner-side via :meth:`WriteQuotes._enrich_quote_cards`. The LLM never
sees ``caption_mode`` — caption rendering is the chat layer's decision,
and the alt translation goes through the existing ``translator`` agent
(registry, already used by ``translate_clip`` / caption lines).
"""

from __future__ import annotations

from typing import Any

from app.agents.registry import translator
from app.models.schemas import (
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
)
from app.pipeline.derivative_dispatch import (
    DerivativeWriterNode,
    validate_derivative_content,
)
from app.tools.quotes.agents import quotes_writer


class WriteQuotes(DerivativeWriterNode):
    kind = "write_quotes"
    task_name = "Create quote cards"
    task_name_zh = "制作金句卡"
    output_type = "quotes"
    slot_label = "Quotes"
    slot_label_zh = "金句"
    count_default = 5  # 2026-08-25 chain variant: the writer judges N based on
                       # how many sentences are needed to express the core
                       # idea (RECIPES §4.6.2); default sits in the middle
                       # of the 3..7 band the chain compositor targets.
    count_limits = (3, 7)  # Chain band: 3 sentences (tight setup→payoff) to
                            # 7 (the 小红书 stacked-card genre ceiling). The
                            # runner passes count into the prompt as a
                            # hint, not a hard pin — the writer picks N
                            # ids to match, not N free compositions.
    writer = quotes_writer
    completion_bounds = (100, 800)  # count cards of one-liners
    images_per_run = 0  # 2026-08-25 Phase 2: no PNG — Phase 3 ships the video card

    async def _enrich_quote_cards(
        self,
        content: dict[str, Any],
        understanding,
        target_language: str,
        caption_mode: str | None,
    ) -> dict[str, Any]:
        """Runner-side post-processing for the chain variant (RECIPES
        §4.6.2, 2026-08-25).

        The writer emits a chain of N ``quotes`` (N=3..7 dynamic) plus
        ``core_idea`` and ``needs_speaker_frame``. This enricher:

        1. **Timestamp snap** for every chain entry: stamp
           ``source_start`` / ``source_end`` / ``frame_at`` from
           ``understanding.quotable_lines[id]``.
        2. **Verbatim enforcement**: snap ``quote_source`` to the picked
           line's text when the writer left it empty.
        3. **Alt translation** when ``caption_mode == "bilingual"`` — the
           translator agent runs per chain entry.
        4. **Chain normalization**: dedupe accidental repeats (writer
           sometimes picks the same id twice when picking blind); trim
           to the count band by clipping overlong chains at the tail
           (short chains are NEVER padded — a 1-entry chain ships as
           the single-card path downstream).

        The chain is ordered by the writer's selection order (setup →
        payoff). The materializer reads ``quotes`` in order — re-ordering
        here would invert the cascade, never do it.
        """
        quotable = list(understanding.quotable_lines or [])
        seen_ids: set[int] = set()
        normalized: list[dict] = []
        for q in content.get("quotes", []):
            qid = q.get("quotable_line_id")
            # Dedupe: a chain entry whose id already shipped is dropped
            # (the LLM sometimes double-picks — RECORD, 2026-08-25).
            if qid in seen_ids:
                continue
            if qid is not None and isinstance(qid, int) and 0 <= qid < len(quotable):
                seen_ids.add(qid)
            line = quotable[qid] if (
                qid is not None
                and isinstance(qid, int)
                and 0 <= qid < len(quotable)
            ) else None
            if line is not None:
                start = line.start
                end = line.end
                q["source_start"] = start
                q["source_end"] = end
                if start is not None and end is not None:
                    q["frame_at"] = round((start + end) / 2, 1)
                else:
                    q["frame_at"] = None
                if not q.get("quote_source"):
                    q["quote_source"] = line.text
            else:
                q.setdefault("source_start", None)
                q.setdefault("source_end", None)
                q.setdefault("frame_at", None)
            normalized.append(q)
        # Band ceiling — clip overlong chains at the tail (keep writer's
        # top-7 picks). No floor: a short chain ships as-is (N=1 routes
        # to the single-card path in the materializer).
        if len(normalized) > 7:
            normalized = normalized[:7]
        content["quotes"] = normalized

        # core_idea / needs_speaker_frame ride verbatim from the LLM
        # verdict. The writer sets them; the runner doesn't second-guess.
        content.setdefault("core_idea", None)
        content.setdefault("needs_speaker_frame", False)

        # Alt translation (Phase 2 bilingual branch — runs for every
        # chain entry).
        if caption_mode == "bilingual" and normalized:
            await self._translate_quote_alts(content, target_language)
        return content

    async def _translate_quote_alts(
        self,
        content: dict[str, Any],
        target_language: str,
    ) -> None:
        """Call the translator agent on each quote's source line, in
        parallel — one LLM call per quote, batched by the agent's
        per-call fan-out. Falls back to None on failure (the card still
        renders with the main caption only)."""
        import asyncio  # local import keeps cold-start path lean

        quotes = content.get("quotes", [])
        if not quotes:
            return
        sources = [q.get("quote_source") or q.get("quote", "") for q in quotes]
        # gather(return_exceptions=True) never raises — per-entry failures
        # land as Exception instances and are skipped below (the card
        # still renders with the main caption only).
        results = await asyncio.gather(
            *(
                translator.call(
                    lines=[s],
                    target_language=target_language,
                )
                for s in sources
            ),
            return_exceptions=True,
        )
        for q, res in zip(quotes, results):
            if isinstance(res, Exception):
                continue
            lines = getattr(res, "lines", None) or []
            if lines:
                q["quote_alt"] = lines[0]

    async def _generate(
        self,
        asset_texts,
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
        feedback=None,
    ):
        """Phase 2 override: enrich the writer's output before schema
        validation, so timestamps and alt translations land on the row
        (the validator runs after, persisting the post-processed dict).
        """
        result = await self.writer.call(
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
            repair_feedback=feedback,
        )
        content = result.model_dump()
        # caption_mode is threaded onto GenerationContext by the dispatcher
        # (derivative_dispatch.run) from run.context. None for non-caption
        # chains (post / carousel / article); "bilingual" / "source_only" /
        # "target_only" for the quote-card path.
        await self._enrich_quote_cards(
            content,
            understanding=understanding,
            target_language=context.target_language,
            caption_mode=getattr(context, "caption_mode", None),
        )
        return validate_derivative_content(self.derivative_type, content)
