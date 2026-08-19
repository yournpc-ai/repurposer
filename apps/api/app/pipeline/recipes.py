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
纪律 (NAMING §5, N-39): NOT a plugin system, NOT a table.

**发射 = 提示词** (2026-08-11 ruling): a recipe launch's ENTIRE behavioral
payload is the prefilled prompt template — the card's identity never crosses
the wire (no ``recipe_id`` transport, no server-side seeding; MENTIONS §3).
``tasks`` stays server-only as the card's DECLARED compile shape (ADR-043 —
the same task-list grammar the PlanAgent proposes): the startup self-check's
input (the orchestrator compiles this chain and reconciles flow keys ⊆ the
compiled kinds, AGENT_ARCH §4.2); it never feeds a request path.

Visibility is a FIELD-LEVEL property: the public ``GET /api/v1/recipes``
serves the public projection (base / flow / example_* / input_slots).

Drift guard: ``flow`` is curated display data but must truthfully mirror the
graph the declared chain compiles to — both live in this file and are
reviewed together (RECIPES §7.1).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import TaskItem


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

    ``tasks`` is the card's DECLARED compile shape (ADR-043 — a task list in
    the PlanAgent's own grammar): the startup self-check compiles this chain
    and reconciles the curated ``flow`` against it (AGENT_ARCH §4.2). It is
    never a request-path input: a launch's behavioral payload is the prompt
    template alone (2026-08-11 ruling — 配方 = 提示词).
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["live", "reserved"]
    input_slots: list[InputSlot] = Field(default_factory=list)
    tasks: list[TaskItem]
    # --- Public display projection (RECIPES §7.1) ---
    aspect: str = "9:16"
    tags: list[str] = Field(default_factory=list)  # shared recipes.tags.* keys
    flow: list[FlowStep] = Field(default_factory=list)
    example_assets: list[ExampleAsset] = Field(default_factory=list)
    example_outputs: list[ExampleOutput] = Field(default_factory=list)


class RecipePublic(BaseModel):
    """The public card catalogue shape (``GET /api/v1/recipes``) — the
    server-internal compile-shape declaration (``tasks``) is not part of
    the projection."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["live", "reserved"]
    input_slots: list[InputSlot]
    aspect: str
    tags: list[str]
    flow: list[FlowStep]
    example_assets: list[ExampleAsset]
    example_outputs: list[ExampleOutput]


# Public demo/ tree (content-addressed where baked; source materials curated
# once, RECIPES §7.3 素材策展总账).
_DEMO = "https://repurposer.tos-ap-southeast-1.volces.com/demo"

RECIPE_REGISTRY: dict[str, RecipeEntry] = {
    # Card order = insertion order (2026-08-13 lineup restructure, user
    # ruling, RECIPES §4): multilingual-subs → image-video → highlight-clips →
    # reframe → ai-visuals. The dub card left the gallery — the capability
    # stays as the subs card's voice-over variant (chat one-liner; the dub
    # contrast pack objects remain in the bucket as its evidence); the
    # talking-head seat is removed (低频 + 数字人信任风险).
    #
    # R6: one video -> multilingual caption forks + a voice-over dub (the card
    # showcases the multilingual/caption capability ONLY — 2026-08-14 ruling:
    # no clip-planning steps in the flow; the baked examples happen to be
    # highlight clips, but the card never sells 剪辑). Original voice stays —
    # the human voice is the authenticity fingerprint. ADR-043 chain shape:
    # transforms alone — the whole source materializes itself (no
    # select_clips, no highlight extraction); each language forks its own
    # derived row.
    "multilingual-subs": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        tasks=[
            TaskItem(
                skill="translate_clip",
                params={"target_language": "zh", "bilingual": True, "fork": True},
            ),
            TaskItem(
                skill="translate_clip",
                params={"target_language": "fr", "fork": True},
            ),
            TaskItem(
                skill="dub_clip",
                params={"target_language": "es", "fork": True},
            ),
        ],
        # The demo source is square (xy_2_15s, 960×960) — the card bakes 1:1
        # (2026-08-14 三档画幅: the card shows the frame the source keeps).
        aspect="1:1",
        tags=["multilingual"],
        flow=[
            FlowStep(key="materialize_source"),
            FlowStep(key="translate_clip", fanout=2),
            FlowStep(key="dub_clip"),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_2_15s.mp4",
                label_key="demo_keynote",
            ),
        ],
        # Contrast pack (R6, 2026-08-14 four-case revision): the same 5s
        # segment as EN original + CN-EN bilingual (translation_track) + FR
        # single-line + ES voice-cloned dub — harvested from a real pipeline
        # run of this card's declared chain (translate zh bilingual + translate
        # fr + dub es, all fork, at 1:1; FR produced script-side single-line)
        # with dimension-derived caption sizing and per-language translated
        # title overlays; per-case posters, content-hashed into the demo/ tree.
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-en-b5735bd2.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-en-poster-14813bde.jpg",
                label_key="subs_en",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-zh-bilingual-26f850f0.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-zh-bilingual-poster-9268b24e.jpg",
                label_key="subs_zh_bilingual",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-fr-d6f7dce5.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-fr-poster-6affb546.jpg",
                label_key="subs_fr",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-es-dub-c4d1e436.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-es-dub-poster-cf01bd16.jpg",
                label_key="dub_es",
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
        tasks=[TaskItem(skill="select_clips", params={})],
        # The demo set is the WFT keynote's own material: a talk write-up
        # (markdown — the card parses articles: PDF/Word/md/txt) + three
        # on-site photos; the baked slideshow shows exactly these.
        # aspect = the SOURCE frame (2026-08-17 ruling: a chain with no clip
        # skill never changes the frame, so the demo follows the material —
        # the photos are landscape 16:9). Baked by
        # scripts/bake_image_video_demo.py.
        aspect="16:9",
        tags=["no-footage"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="align_stills"),
            FlowStep(key="select_clips"),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="transcript",
                url=f"{_DEMO}/uploads/demo-article.md",
                label_key="demo_article",
            ),
            ExampleAsset(
                kind="image",
                url=f"{_DEMO}/uploads/teasers-photo-title.jpg",
                label_key="demo_photos",
            ),
            ExampleAsset(
                kind="image",
                url=f"{_DEMO}/uploads/teasers-photo-industries.jpg",
                label_key="demo_photos",
            ),
            ExampleAsset(
                kind="image",
                url=f"{_DEMO}/uploads/teasers-photo-outcomes.jpg",
                label_key="demo_photos",
            ),
        ],
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/image-video-preview-18833859.mp4",
                poster_url=f"{_DEMO}/outputs/image-video-poster-2b1a8f81.jpg",
                label_key="image_video_preview",
            ),
        ],
    ),
    # 高光切片 (highlight-clips, RECIPES §4.3): long footage -> vertical
    # highlight clips with dynamic speaker tracking (the crop_track craft
    # layer's follow dish, shared with reframe). The demo source is the subs
    # card's curated 15s keynote excerpt — one source, many products is the
    # product's own story. Baked by scripts/bake_reframe_demos.py.
    "highlight-clips": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        tasks=[
            TaskItem(skill="select_clips", params={}),
            TaskItem(skill="reframe_clip", params={"mode": "auto"}),
        ],
        aspect="9:16",
        tags=["auto-framing"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="select_clips"),
            FlowStep(key="reframe_clip"),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_2_15s.mp4",
                label_key="demo_keynote",
            ),
        ],
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/highlight-clips-vertical-ae184e14.mp4",
                poster_url=f"{_DEMO}/outputs/highlight-clips-vertical-poster-cfdaabed.jpg",
                label_key="follow_output",
            ),
        ],
    ),
    # 访谈分镜 (reframe, RECIPES §4.3): landscape two-person interview ->
    # vertical speaker reframe — the crop_track craft layer's switch dish.
    # The demo source is a 15s segment of xy_1 carrying exactly one clean
    # speaker switch (~7.1s in), so the baked clip shows the cut the card
    # sells. Baked by scripts/bake_reframe_demos.py.
    "reframe": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        tasks=[
            TaskItem(skill="select_clips", params={}),
            TaskItem(skill="reframe_clip", params={"mode": "auto"}),
        ],
        aspect="9:16",
        tags=["auto-framing"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="select_clips"),
            FlowStep(key="reframe_clip"),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_1_interview_15s.mp4",
                label_key="demo_interview",
            ),
        ],
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/reframe-vertical-fe2e40e9.mp4",
                poster_url=f"{_DEMO}/outputs/reframe-vertical-poster-7bd6b23a.jpg",
                label_key="reframe_output",
            ),
        ],
    ),
    # R5 seat: nothing but a talk — every scene AI-generated, the zero-asset
    # end of the source-material spectrum. Positioned as 趣味/实验
    # (2026-08-13 ruling, RECIPES §4.4): honest experimental labeling, no
    # professional promise; lights only after the R5 line is ready.
    "ai-visuals": RecipeEntry(
        status="reserved",
        input_slots=[InputSlot(type="audio")],
        tasks=[TaskItem(skill="select_clips", params={})],
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
            flow=entry.flow,
            example_assets=entry.example_assets,
            example_outputs=entry.example_outputs,
        )
        for recipe_id, entry in RECIPE_REGISTRY.items()
    ]
