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
composer prefill. Static registry deployed with code — TOOL_REGISTRY 同款
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

Recipe gallery v2 (ADR-048, 2026-08-23; 2026-08-24 text-tribe flip):
the registry owns 8 cards, all ``live`` (text-tribe landed in the
``bake_text_tribe_demos.py`` harvest 2026-08-24). ``"reserved"`` stays in
the schema only because the registry ships with code (TOOL_REGISTRY 同款,
NAMING §5, N-39) — never a real grid state again (RECIPES §10 retired the
Soon pill with the bake landing).
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

    Recipe gallery v2 (ADR-048): ``status`` keeps BOTH ``"live"`` and
    ``"reserved"`` — RECIPES §10 holds: a reserved card sits in the grid
    with a Soon pill (no hover chrome, no overlay), the moment its example
    bake lands it flips to ``"live"`` and joins the rest. The text-tribe
    cards (``social-post`` / ``quote-cards`` / ``carousel``) live in this
    half-state until a real pipeline harvest writes content-hashed
    artifacts under ``demo/outputs/`` (after which they flip to live).
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
    the projection. Status mirrors ``RecipeEntry`` (gallery v2 — both
    ``"live"`` and ``"reserved"`` are public)."""

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

# Card order = insertion order (RECIPES §4, ADR-048 lineup: row 1 has video
# sources, row 2 has text/image sources). The dub card is back to its own
# seat — its capability was always there, the gallery just stopped showing
# it (2026-08-10 配音降为字幕卡配音变体翻案，08-23 配音卡复座). The text-tribe
# cards (social-post / quote-cards / carousel) are NOT registered yet — see
# the file docstring and ``PENDING_BAKE_BLOCK`` below for the bake gate.
RECIPE_REGISTRY: dict[str, RecipeEntry] = {
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
                tool="translate_clip",
                params={"target_language": "zh", "bilingual": True, "fork": True},
            ),
            TaskItem(
                tool="translate_clip",
                params={"target_language": "fr", "fork": True},
            ),
            TaskItem(
                tool="dub_clip",
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
    # 原声AI配音 (voice-dub, RECIPES §4.5): your own voice in another
    # language. The card's name IS its moat (声纹克隆 written into the dish
    # name — a generic LLM can write a translation, it cannot clone your
    # voice, so the capability is doubly non-substitutable, RECIPES §4.5
    # gate ② + C2PA compliance chain ADR-026). Reuses the dub contrast pack
    # already in TOS (the same 4-case EN/ZH/FR/ES bake as the subs-card uses
    # for its dub_es leg): voice-dub is the card those outputs belong on.
    # Their `subs-contrast-*` URLs are the hash-named objects from the
    # 2026-08-07 bake; `label_key` reuses the subs-card's labels because the
    # language identity is the same content.
    "voice-dub": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        tasks=[
            TaskItem(
                tool="dub_clip",
                params={"target_language": "zh", "fork": True},
            ),
            TaskItem(
                tool="dub_clip",
                params={"target_language": "fr", "fork": True},
            ),
            TaskItem(
                tool="dub_clip",
                params={"target_language": "es", "fork": True},
            ),
        ],
        # Same 1:1 source as the subs card — the dub card reuses the same
        # 5s segment so an inspector can compare EN original alongside the
        # 3 dub variants on the inspect overlay.
        aspect="1:1",
        tags=["voice-clone"],
        flow=[
            FlowStep(key="materialize_source"),
            FlowStep(key="dub_clip", fanout=3),
            FlowStep(key="render"),
        ],
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_2_15s.mp4",
                label_key="demo_keynote",
            ),
        ],
        # The dub contrast pack: EN original read + 3 cloned voice variants,
        # baked on 2026-08-07 with `bake_dub_contrast.py`. Per-case posters
        # content-hashed into the demo/ tree. The subs-card uses the same
        # outputs (specifically the es leg); listing them on voice-dub too
        # — with the same label keys — keeps both cards' "evidence" honest
        # and saves a re-bake.
        example_outputs=[
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-en-b5735bd2.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-en-poster-14813bde.jpg",
                label_key="subs_en",
            ),
            ExampleOutput(
                kind="video",
                url=f"{_DEMO}/outputs/subs-contrast-es-dub-c4d1e436.mp4",
                poster_url=f"{_DEMO}/outputs/subs-contrast-es-dub-poster-cf01bd16.jpg",
                label_key="dub_es",
            ),
            # NOTE: the ZH/FR dub legs were baked into the same pack during
            # the multilingual-subs harvest (translate paths). To keep the
            # voice-dub card truthful about ITS capability (voice cloning,
            # not translation), the example_outputs here showcase the EN
            # original + the canonical ES dub — which together demonstrate
            # the voice-clone moat. Re-adding the full 4-case pack would
            # mix translation evidence into the dub card; the subs card
            # owns the translation lineage.
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
        tasks=[
            TaskItem(tool="select_clips", params={}),
            # The card sells "captions and music" (promise + template + the
            # baked demo's add_music leg) — the declared chain names it, or
            # the self-check's compile shape lies about the card.
            TaskItem(tool="add_music", params={}),
        ],
        # The demo set is the WFT keynote's own material: a talk write-up
        # (markdown — the card parses articles: PDF/Word/md/txt) + three
        # on-site photos; the baked slideshow shows exactly these.
        # aspect = the SOURCE frame (2026-08-17 ruling: a chain with no clip
        # tool never changes the frame, so the demo follows the material —
        # the photos are landscape 16:9). Baked by
        # scripts/bake_image_video_demo.py.
        aspect="16:9",
        tags=["no-footage"],
        flow=[
            FlowStep(key="director_understand"),
            FlowStep(key="director_plan"),
            FlowStep(key="align_stills"),
            FlowStep(key="select_clips"),
            FlowStep(key="add_music"),
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
            TaskItem(tool="select_clips", params={}),
            TaskItem(tool="reframe_clip", params={"mode": "auto"}),
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
                url=f"{_DEMO}/outputs/highlight-clips-vertical-ec8e575b.mp4",
                poster_url=f"{_DEMO}/outputs/highlight-clips-vertical-poster-11bc0ca3.jpg",
                label_key="follow_output",
            ),
        ],
    ),
    # 访谈分镜 (reframe, RECIPES §4.3): landscape two-person interview ->
    # vertical speaker reframe — the crop_track craft layer's switch dish.
    # The demo source is a 14.5s segment of xy_1 ([172.5, 187.0] of the full
    # interview — chosen against the full file's real speaker_map turns so it
    # carries exactly one clean question→answer switch mid-clip), so the
    # baked clip shows the cut the card sells. Never loudness-normalize a
    # demo SOURCE: loudnorm fills the ≥0.6s silence gaps whisper's
    # turn-segmentation depends on (bake_reframe_demos.py docstring).
    "reframe": RecipeEntry(
        status="live",
        input_slots=[InputSlot(type="video")],
        tasks=[
            TaskItem(tool="select_clips", params={}),
            TaskItem(tool="reframe_clip", params={"mode": "auto"}),
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
                url=f"{_DEMO}/outputs/reframe-vertical-7bcbb54e.mp4",
                poster_url=f"{_DEMO}/outputs/reframe-vertical-poster-c4eec0b0.jpg",
                label_key="reframe_output",
            ),
        ],
    ),
    # === Text-tribe (RECIPES §4.6): reserved half-state (RECIPES §10). ===
    #
    # The text-tribe cards live in the grid NOW with a Soon pill (no hover
    # chrome, no overlay — RecipeCard gates on `live`). Their data shape is
    # complete (i18n ✓, tasks ✓, flow ✓); only the example harvest is
    # outstanding (`scripts/bake_text_tribe_demos.py`, to be modelled on
    # `bake_dub_contrast.py`). When the bake lands: swap `status` to
    # "live", replace the placeholder.example_outputs URLs with the
    # content-hashed artifacts, and run the prompt-surface gate (§B.4) to
    # confirm each card's template still infers its expected tool kind.
    # === Text-tribe (RECIPES §4.6, ADR-048 §7.3): 2026-08-24 bake. ===
    #
    # The three text-tribe cards went from reserved to live when the
    # `scripts/bake_text_tribe_demos.py` harvest landed: real pipeline runs
    # on demo-article.md, content-hashed under demo/outputs/<stem>-<hash>.{json,png}.
    # Each writer agent is now also pinned to its skill pack
    # (quote-cards / carousel — N-42 指令包纪律), so the writer prompt sees
    # the domain conventions at assembly time.
    "social-post": RecipeEntry(
        status="live",
        # 2026-08-24 lift: transcript is OPTIONAL. The card drafts from
        # prompt + persona when the user has nothing to attach — the
        # promptHint echoes this so the user sees the choice at send time.
        input_slots=[InputSlot(type="transcript", required=False)],
        # write_post requires `language` (CopyWriterParams.language is
        # mandatory — declared in app/pipeline/derivative_dispatch.py).
        # The card defaults to English; chat overrides per language.
        tasks=[TaskItem(tool="write_post", params={"language": "en"})],
        aspect="1:1",
        tags=["text-output"],
        flow=[FlowStep(key="write_post")],
        example_assets=[
            ExampleAsset(
                kind="transcript",
                url=f"{_DEMO}/uploads/demo-article.md",
                label_key="demo_article",
            ),
        ],
        # 2026-08-24 harvest (write_post on demo-article.md, English). JSON
        # payload — the overlay's Examples tab renders the content as a doc
        # preview card (post kind = "image" per the ExampleOutput schema).
        example_outputs=[
            ExampleOutput(
                kind="image",
                url=f"{_DEMO}/outputs/post-699d2254.json",
                poster_url=None,
                label_key="post_output",
            ),
        ],
    ),
    "quote-cards": RecipeEntry(
        status="live",
        # 2026-08-25 Phase 2→4 重设计：quote-cards 不再是 LLM 自由发挥的
        # 1:1 PNG——它是 ASR+Remotion 真管线短视频（9:16 单条金句）。素材
        # 必传：video（OffthreadVideo 渲染底，quote 那段原声+画面+ASR 字幕
        # 一次成型）。transcript 槽不列——ASR 在 chain 内由 video 自动
        # 派生文字稿 + 词级时间戳 → 驱动 understanding.quotable_lines 候选
        # → runner 据此 snap 时间戳；用户无需重复上传文字稿。用户红线：
        # quote 必须有源素材绑定。images 作为未来 image 源 fallback（Phase
        # 4 之后看真实需求再立）。
        #
        # Chain variant (2026-08-25, RECIPES §4.6.2): count is now the
        # writer's HINT, not a hard pin — the writer picks how many
        # sentences are needed to express the core idea (3..7 dynamic).
        # We seed count=5 (the middle of the band) so the prompt has a
        # sensible default; the writer's verdict is final. Materialiser
        # renders ALL chain entries as ONE composite PNG (cascade of
        # caption strips), not N separate cards.
        input_slots=[
            InputSlot(type="video", required=True),
        ],
        tasks=[
            # count=5: chain midpoint — the writer judges actual N (3..7).
            # aspect=9:16: 竖屏短片金句卡，对齐真实小红书金句卡形态。
            # caption_mode 走 Phase 1 chat 反问：bilingual / source_only /
            # target_only 三选一，默认值是 chat 的默认值而非 recipes 端的
            # 默认值（pre-LLM 闸门已撤，run.context.caption_mode 由 LLM 在
            # task_book 落字）。layout_mode="stacked" 触发 chain 合成器；
            # 由 chat 在 task_book 中按用户意图落字（bake-time override）。
            TaskItem(tool="write_quotes", params={"language": "en", "count": 5})
        ],
        aspect="9:16",
        tags=["text-output", "captions"],
        flow=[FlowStep(key="write_quotes")],
        # 2026-08-25 Phase 4 + chain variant: example_assets 跟 recipes
        # §7.1 对账——demo 源是 xy_2.mp4（单人 TED 风 talk，60s 截屏
        # 960×960，ASR 词级时间戳很密），跟实际 baked 流水线一致：writer
        # 选自 understanding.quotable_lines（来自这一段 ASR），runner 据此
        # snap 时间戳并生成 frame_at。video 必传（卡片承诺的视觉底 = 真人
        # 说话帧），transcript 由 ASR 在 chain 内补（资产侧不必显式传文字稿）。
        example_assets=[
            ExampleAsset(
                kind="video",
                url=f"{_DEMO}/uploads/xy_2.mp4",
                label_key="demo_keynote",
            ),
        ],
        # 2026-08-25 Phase 4 + chain variant bake landed: 9:16 视频金
        # 句卡 (xy_2.mp4 → 流水线渲染 → quote-card-chain-*.mp4).
        # writer 判 N=3 句（落在 3..7 band 内），每条 chain entry = 一
        # 张真实视频帧（PyAV 在 frame_at 时刻抓）+ 烤在上面的双语字幕。
        # 几何 = v2 y-stack (overlap=200px, y_top=i*(vh-overlap)) +
        # v3 宽度金字塔（CHAIN_CARD_WIDTH_FACTOR=0.92，顶部最窄、底部
        # 最宽 → 在 overlap 区两侧露出下条边沿，sticky-note cascade
        # 视觉）。绘制顺序 reversed（chain[N-1] 先画在画布底部=z 最
        # 小=back；chain[0] 最后画在画布顶部=z 最大=front），视觉上
        # 后画盖前画。needs_speaker_frame 没启用（纯帧卡 cascade）。
        # stills kind spec + zoom_in 1.05 渲染 4s 9:16 MP4。Examples
        # tab 显示这条视频。
        example_outputs=[
            ExampleOutput(
                kind="image",
                url=f"{_DEMO}/outputs/quote-card-chain-v9-72402480.png",
                poster_url=None,
                label_key="quotes_output",
            ),
        ],
    ),
    "carousel": RecipeEntry(
        status="live",
        # 2026-08-24 lift: transcript is OPTIONAL — see social-post note.
        input_slots=[InputSlot(type="transcript", required=False)],
        tasks=[
            TaskItem(tool="write_carousel", params={"language": "en", "count": 6})
        ],
        aspect="1:1",
        tags=["text-output"],
        flow=[FlowStep(key="write_carousel")],
        example_assets=[
            ExampleAsset(
                kind="transcript",
                url=f"{_DEMO}/uploads/demo-article.md",
                label_key="demo_article",
            ),
        ],
        # 2026-08-24 harvest (write_carousel on demo-article.md, count=6, EN).
        # Carousel has no render-side product (writer's 6 slides are JSON
        # only); poster_url is None — the overlay's Examples tab renders
        # the JSON slides as the preview.
        example_outputs=[
            ExampleOutput(
                kind="image",
                url=f"{_DEMO}/outputs/carousel-f14c251c.json",
                poster_url=None,
                label_key="carousel_output",
            ),
        ],
    ),
}


def list_public_recipes() -> list[RecipePublic]:
    """The public catalogue (card order = registry insertion order).

    Both ``"live"`` and ``"reserved"`` entries ship to the public endpoint
    (RECIPES §10 reserves a grid seat for cards awaiting their bake). The
    frontend guards the click path on ``live`` and pins a Soon pill to
    reserved cards.
    """
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
