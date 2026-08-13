"""Recipe registry (配方注册表, RECIPES §7.1) — the server-side source of
truth for recipe cards.

**配方 = 数据** (2026-08-06 ruling): a recipe IS one data package —

    base            name / promise / tags / aspect / status (text via i18n keys)
    flow            author-curated read-only static flow diagram (ADR-035)
    prompt          example prompt (i18n: recipes.<id>.promptTemplate)
    example_assets  demo source materials (public demo/ tree URLs)
    example_outputs baked result previews (content-addressed URLs)

Every consumer reads the same package: the card face, the inspect overlay
(= the package's renderer, docs/tasks/results-workspace.md D6), and the
composer prefill. Static registry deployed with code — SKILL_REGISTRY 同款
纪律 (NAMING §5, N-25): NOT a plugin system, NOT a table.

**发射 = 提示词** (2026-08-11 ruling): a recipe launch's ENTIRE behavioral
payload is the prefilled prompt template — the card's identity never crosses
the wire (no ``recipe_id`` transport, no server-side seeding; MENTIONS §3).
``outputs`` / ``dub_languages`` / ``caption_languages`` stay server-only as
the card's DECLARED compile shape — the startup self-check's input (the
orchestrator compiles this shape and reconciles flow keys ⊆ the compiled
kinds, AGENT_ARCH §4.2); they never feed a request path.

Visibility is a FIELD-LEVEL property: the public ``GET /api/v1/recipes``
serves the public projection (base / flow / example_* / input_slots).

Drift guard: ``flow`` is curated display data but must truthfully mirror the
graph the declared shape compiles to — both live in this file and are
reviewed together (RECIPES §7.1).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import IntentSlot


class InputSlot(BaseModel):
    """输入槽位 (input_slots): the typed blank a recipe leaves for the user
    ("needs a talk video"). Display-hint layer — the clips-media gate at
    ``create_run`` remains the enforcement floor."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["video", "audio", "images", "slides", "transcript"]
    required: bool = True


class FlowStep(BaseModel):
    """静态流程图一步 (Recipe.flow, ADR-035) — author-curated, read-only:
    the ``key`` IS a node kind (N-35 — the startup self-check reconciles
    flow keys ⊆ the compiled graph's kind set, AGENT_ARCH §4.2), localized
    via the shared ``recipes.flow.*`` i18n namespace; no model names, no
    wiring. ``fanout`` marks parallel branches (dub_clip ×3)."""

    model_config = ConfigDict(extra="forbid")

    key: str
    detail_key: str | None = None
    fanout: int | None = None


class ExampleAsset(BaseModel):
    """示例原素材 (Recipe.example_assets) — the demo material shown in the
    overlay's 原素材 stack item; the proof behind the Assets-block hint."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video", "audio", "image", "slides", "transcript"]
    url: str
    label_key: str | None = None  # shared recipes.materials.* namespace


class ExampleOutput(BaseModel):
    """烘焙成片 (Recipe.example_outputs) — the overlay's big preview."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video", "image"]
    url: str
    poster_url: str | None = None
    label_key: str | None = None


class RecipeEntry(BaseModel):
    """One registered recipe: a card awaiting material.

    ``outputs`` / ``dub_languages`` / ``caption_languages`` are the card's
    DECLARED compile shape — the startup self-check compiles this shape and
    reconciles the curated ``flow`` against it (AGENT_ARCH §4.2). They are
    never a request-path input: a launch's behavioral payload is the prompt
    template alone (2026-08-11 ruling — 配方 = 提示词).
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["live", "reserved"]
    input_slots: list[InputSlot] = Field(default_factory=list)
    outputs: list[IntentSlot]
    dub_languages: list[str] = Field(default_factory=list)
    caption_languages: list[str] = Field(default_factory=list)
    # --- Public display projection (RECIPES §7.1) ---
    aspect: str = "9:16"
    tags: list[str] = Field(default_factory=list)  # shared recipes.tags.* keys
    variants: list[str] = Field(default_factory=list)  # recipes.<id>.variants.* keys
    flow: list[FlowStep] = Field(default_factory=list)
    example_assets: list[ExampleAsset] = Field(default_factory=list)
    example_outputs: list[ExampleOutput] = Field(default_factory=list)


class RecipePublic(BaseModel):
    """The public card catalogue shape (``GET /api/v1/recipes``) — the
    server-internal compile-shape declarations (outputs / dub_languages)
    are not part of the projection."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["live", "reserved"]
    input_slots: list[InputSlot]
    aspect: str
    tags: list[str]
    variants: list[str]
    flow: list[FlowStep]
    example_assets: list[ExampleAsset]
    example_outputs: list[ExampleOutput]


_CLIPS_SLOT = IntentSlot(type="clips")

# Public demo/ tree (content-addressed where baked; source materials curated
# once, RECIPES §7.3 素材策展总账).
_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo"

RECIPE_REGISTRY: dict[str, RecipeEntry] = {
    # Card order = insertion order (2026-08-13 lineup restructure, user
    # ruling, RECIPES §4): multilingual-subs → image-video → talk-clips →
    # reframe → ai-visuals. The dub card left the gallery — the capability
    # stays as the subs card's voice-over variant (chat one-liner; the dub
    # contrast pack objects remain in the bucket as its evidence); the
    # talking-head seat is removed (低频 + 数字人信任风险).
    #
    # R6: one talk -> clips with translated captions (original voice stays —
    # the human voice is the authenticity fingerprint), one fork-semantic
    # translate node per language.
    "multilingual-subs": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
        caption_languages=["fr", "de", "es"],
        tags=["multilingual"],
        variants=["languages", "dub"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="select_clips"),
            FlowStep(key="translate_clip", fanout=3),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_2_15s.mp4",
                label_key="demo_keynote",
            ),
        ],
        # Contrast pack (R6, 2026-08-14): the same 15s keynote segment as the
        # EN original + FR/DE/ES subtitled versions — harvested from a real
        # pipeline run (xy_2_15s → ASR → select_clips → translate_clip×3 fork
        # → render×4), re-uploaded to the demo/ tree by content hash.
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-en-3689d6e7.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-poster-bdd161d5.jpg",
                label_key="subs_en",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-fr-c5e7a871.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-poster-bdd161d5.jpg",
                label_key="subs_fr",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-de-ef29918b.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-poster-bdd161d5.jpg",
                label_key="subs_de",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-es-2c2f6a0b.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-poster-bdd161d5.jpg",
                label_key="subs_es",
            ),
        ],
    ),
    # R2: transcript + photos -> stills slideshow + captions (estimated
    # timeline via align_stills) + music. Voice path deferred to the
    # voiceprint line (RECIPES §4.2, 2026-08-05 ruling). Slides slot added
    # 2026-08-13: decks convert to page images in asset processing, folding
    # the 课件 scenario into this card.
    "image-video": RecipeEntry(
        status="live",
        input_slots=[
            InputSlot(type="images"),
            InputSlot(type="transcript"),
            InputSlot(type="slides", required=False),
        ],
        outputs=[_CLIPS_SLOT],
        tags=["no-footage"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="align_stills"),
            FlowStep(key="select_clips"),
            FlowStep(key="render"),
        ],
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/image-video-preview-818e015e.mp4",
                poster_url=f"{_DEMO}/outputs/image-video-poster-b715a075.jpg",
                label_key="image_video_preview",
            ),
        ],
    ),
    # 演讲短片 seat (talk-clips, RECIPES §4.3): keynote mid-shot -> vertical
    # highlight clips with dynamic speaker tracking (crop_track craft layer,
    # shared with reframe). Card authoring lands with the positioning-root
    # batch (PROGRESS 第八周).
    "talk-clips": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
    ),
    # 访谈分镜 seat (reframe, RECIPES §4.3): landscape two-person interview ->
    # vertical speaker reframe — the static dish of the same crop_track
    # craft layer. Card authoring lands with the positioning-root batch.
    "reframe": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="video")],
        outputs=[_CLIPS_SLOT],
    ),
    # R5 seat: nothing but a talk — every scene AI-generated, the zero-asset
    # end of the source-material spectrum. Positioned as 趣味/实验
    # (2026-08-13 ruling, RECIPES §4.4): honest experimental labeling, no
    # professional promise; lights only after the R5 line is ready.
    "ai-visuals": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="audio")],
        outputs=[_CLIPS_SLOT],
    ),
}


def list_public_recipes() -> list[RecipePublic]:
    """The public catalogue (card order = registry insertion order)."""
    return [
        RecipePublic(
            id=recipe_id,
            status=entry.status,
            input_slots=entry.input_slots,
            aspect=entry.aspect,
            tags=entry.tags,
            variants=entry.variants,
            flow=entry.flow,
            example_assets=entry.example_assets,
            example_outputs=entry.example_outputs,
        )
        for recipe_id, entry in RECIPE_REGISTRY.items()
    ]
