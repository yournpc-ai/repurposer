"""Recipe registry (配方注册表, RECIPES §7.1) — the server-side source of
truth for recipe cards.

Static registry deployed with code — SKILL_REGISTRY 同款纪律 (NAMING §5,
N-25): NOT a plugin system, NOT a table. The pin substance (``outputs`` /
``dub_languages``) never leaves the server: the public ``GET /api/v1/recipes``
returns only ``{id, status, input_slots}``, and pinning happens exclusively
here via ``resolve_recipe_mentions`` (the composer sends mentions, never a
client-built prior — prohibition #1, docs/tasks/recipe-mention.md).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import ChatMention, IntentSlot


class InputSlot(BaseModel):
    """输入槽位 (input_slots): the typed blank a recipe leaves for the user
    ("needs a talk video"). Display-hint layer — the clips-media gate at
    ``create_run`` remains the enforcement floor."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["video", "audio", "images", "slides", "transcript"]
    required: bool = True


class RecipeEntry(BaseModel):
    """One registered recipe: a task-book template awaiting material.

    ``outputs`` are explicit-pinned slots (they survive re-inference via the
    pin-merge rule); ``dub_languages`` pins the run's voice-dub fan-out.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["live", "reserved"]
    input_slots: list[InputSlot] = Field(default_factory=list)
    outputs: list[IntentSlot]
    dub_languages: list[str] = Field(default_factory=list)


class RecipePublic(BaseModel):
    """The public card catalogue shape (``GET /api/v1/recipes``) — pin
    substance deliberately excluded."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["live", "reserved"]
    input_slots: list[InputSlot]


_CLIPS_SLOT = IntentSlot(type="clips", explicit=True)

RECIPE_REGISTRY: dict[str, RecipeEntry] = {
    # R1: one talk -> clips + your cloned voice speaking DE/FR/ES (fork
    # semantics — originals and all language versions coexist).
    "dub": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
        dub_languages=["de", "fr", "es"],
    ),
    # R2 seat: transcript + photos -> stills + stacking captions + voice.
    "image-video": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="images"), InputSlot(type="transcript")],
        outputs=[_CLIPS_SLOT],
    ),
    # R3 seat: landscape two-person interview -> vertical speaker reframe.
    "reframe": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
    ),
    # R4 seat: style showcase (content TBD, RECIPES §4.4).
    "style": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
    ),
    # R5 seat: nothing but a talk — every scene AI-generated, the zero-asset
    # end of the source-material spectrum.
    "ai-visuals": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="audio")],
        outputs=[_CLIPS_SLOT],
    ),
}


def list_public_recipes() -> list[RecipePublic]:
    """The public catalogue (card order = registry insertion order)."""
    return [
        RecipePublic(id=recipe_id, status=entry.status, input_slots=entry.input_slots)
        for recipe_id, entry in RECIPE_REGISTRY.items()
    ]


def resolve_recipe_mentions(mentions: list[ChatMention]) -> RecipeEntry | None:
    """Resolve the recipe pinned by a turn's mentions (task-book pin family).

    Returns ``None`` when no recipe is mentioned (path identical to today).
    Raises ``ValueError`` on a rejected pin — the /intent surface maps it to
    422, the chat surface to a re-ask fallback:

    - more than one recipe per run (v1: a recipe is a complete task book;
      recipe composition is a later iteration);
    - unknown id or a ``reserved`` card (a promise is never deliverable
      before its capability is real).
    """
    recipe_mentions = [m for m in mentions if m.type == "recipe"]
    if not recipe_mentions:
        return None
    if len(recipe_mentions) > 1:
        raise ValueError("One recipe per run — a recipe is a complete task book.")
    entry = RECIPE_REGISTRY.get(recipe_mentions[0].id)
    if entry is None:
        raise ValueError(f"Unknown recipe: {recipe_mentions[0].id}")
    if entry.status != "live":
        raise ValueError(f"Recipe not yet available: {recipe_mentions[0].id}")
    return entry
