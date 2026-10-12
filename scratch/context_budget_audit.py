"""Context-budget audit (ADR-117 D4, B4): read the conversation_usage
ledger's prompt_tokens distribution to calibrate ``chat.context_budget_tokens``.

The assembly-budget calibration source (contract B4 「装配预算审计先行」):
once the B3 ledger has live rows, this prints the token distribution that
the 120000 default is checked against. It writes nothing and asserts
nothing — a reading instrument, not a gate (数字断言不落库、不进闸).

Family attribution caveat: conversation_usage carries no turn-family
column (contract schema) — router / plan / explore / answer / trigger rows
are indistinguishable. The overall distribution still bounds the budget
(every family assembles through the same window predicate); if the reading
shows a bimodal tail worth attributing, the fold seats know their family
and a ``family`` column is the follow-up.

Usage (from apps/api, live DB):
    uv run python ../scratch/context_budget_audit.py [--days 14]
"""

import argparse
import asyncio
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import ConversationUsage  # noqa: E402


def _percentile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    idx = min(len(sorted_values) - 1, int(q * len(sorted_values)))
    return sorted_values[idx]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(
                        ConversationUsage.prompt_tokens,
                        ConversationUsage.completion_tokens,
                        ConversationUsage.cached_tokens,
                        ConversationUsage.cost_usd,
                        ConversationUsage.created_at,
                    ).where(
                        ConversationUsage.created_at
                        >= datetime.now(UTC) - timedelta(days=args.days)
                    )
                )
            ).all()
        )

    if not rows:
        print(f"no conversation_usage rows in the last {args.days} days — "
              "the B3 ledger needs live turns first")
        return

    prompts = sorted(r.prompt_tokens for r in rows)
    completions = sorted(r.completion_tokens for r in rows)
    cached = [r.cached_tokens for r in rows if r.cached_tokens is not None]
    total_cost = sum(r.cost_usd for r in rows)

    print(f"conversation_usage — last {args.days} days, {len(rows)} turns")
    print(f"prompt_tokens     p50={_percentile(prompts, 0.50):>8} "
          f"p90={_percentile(prompts, 0.90):>8} "
          f"p99={_percentile(prompts, 0.99):>8} max={prompts[-1]:>8}")
    print(f"completion_tokens p50={_percentile(completions, 0.50):>8} "
          f"p90={_percentile(completions, 0.90):>8} "
          f"p99={_percentile(completions, 0.99):>8} max={completions[-1]:>8}")
    if cached:
        hit_rate = statistics.mean(c / p for c, p in zip(
            [r.cached_tokens for r in rows if r.cached_tokens is not None],
            [r.prompt_tokens for r in rows if r.cached_tokens is not None],
        ) if p)
        print(f"prefix-cache      rows reporting={len(cached)}/{len(rows)} "
              f"mean hit share={hit_rate:.1%}")
    print(f"cost              total=${total_cost:.4f} "
          f"mean=${total_cost / len(rows):.5f}/turn")

    p99 = _percentile(prompts, 0.99)
    print()
    print("calibration read (budget = history window, world state excluded):")
    print(f"  current default chat.context_budget_tokens = 120000")
    print(f"  ledger p99 prompt_tokens = {p99} "
          f"(window + world state + tools overhead ride on top)")
    if p99 > 100000:
        print("  ⚠ p99 is within 20% of the default — the window may already "
              "be folding routine turns; consider raising the budget or "
              "attributing the tail before tuning")


if __name__ == "__main__":
    asyncio.run(main())
