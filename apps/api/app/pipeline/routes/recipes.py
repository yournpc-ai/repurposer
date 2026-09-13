"""Recipe catalogue router.

Endpoints (prefix ``/api/v1/recipes``):

- ``GET ""`` — the public card catalogue: the public projection of the
  Recipe data package (base structure / flow / example_* / input_slots,
  RECIPES §7.1) PLUS the card's credits quotation (BILLING §7 估价贴 —
  the declared chain's estimate fold × the live consumption ratio, computed
  per request so one config edit moves every sticker). No auth — the landing
  audience is anonymous and reads the same cards. Pin substance (the
  ``tasks`` compile shape) never leaves the server (prohibition #7,
  docs/tasks/recipe-mention.md).
"""

from fastapi import APIRouter

from app.dependencies import DBDep
from app.pipeline.orchestrator import compile_recipe_quote
from app.pipeline.recipes import (
    RECIPE_QUOTE_FACTS,
    RECIPE_REGISTRY,
    EstimateRate,
    RecipePublic,
    list_public_recipes,
)
from app.platform.billing import (
    credits_at_ratio,
    estimate_rate_credits,
    estimate_usd_range,
)
from app.platform.configs import get_config

router = APIRouter()


@router.get("", response_model=list[RecipePublic])
async def list_recipes(db: DBDep) -> list[RecipePublic]:
    """List the registered recipe cards (public, read-only).

    The compile is pure and the ratio read is cached, so pricing the whole
    catalogue per request costs nothing measurable; an unquotable chain
    serves a None sticker, never an error."""
    ratio = await get_config(db, "credits.per_cost_usd")
    cards: list[RecipePublic] = []
    for pub in list_public_recipes():
        entry = RECIPE_REGISTRY[pub.id]
        fold = compile_recipe_quote(entry)
        if entry.quote_form == "per_second":
            # Usage-priced sticker (BILLING §7): rate + one-shot split, so
            # the number scales to the user's real upload in their head —
            # a 20-minute-anchored total misleads the 15-second test and
            # the hour-long upload alike.
            seconds = sum(c["seconds"] for c in RECIPE_QUOTE_FACTS["clips"])
            rate, one_shot = estimate_rate_credits(fold, seconds, ratio)
            cards.append(
                pub.model_copy(
                    update={
                        "estimate_rate": (
                            EstimateRate(per_second=rate, one_shot=one_shot)
                            if rate > 0
                            else None
                        )
                    }
                )
            )
            continue
        usd_low, usd_high = estimate_usd_range(fold)
        low, high = credits_at_ratio(usd_low, ratio), credits_at_ratio(usd_high, ratio)
        cards.append(
            pub.model_copy(
                update={"estimate_credits": [low, high] if (low, high) != (0, 0) else None}
            )
        )
    return cards
