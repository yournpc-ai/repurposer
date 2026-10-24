"""R3 读取座 tests — the film output read's facts table, candidate view
catalog, image budget and wire projection (stub DB/storage; no LLM, no
HTTP, no real DB).

The covered laws (设计 = docs/tasks/film-storyboard-orchestration.md §7.2
读取座):

1. **事实表** — version/digest-prefix/params; per-scene lines carry the
   AUTHORED seconds and the timeline duration (authoritative frames ÷ the
   fixed fps) as TWO separate clocks with the provenance labeled
   (actual executed / frozen kept / planned draft / unreadable) — planned
   never passes as executed, authored never mixes with executed; the
   scene's display copy reads back verbatim per type (never summarized,
   never guessed from screenshots); the camera text resolves elements to
   their captured text AND id (internal read; user presentation hides ids).
2. **图片映射** — fold + section shots attach as compressed images whose
   captions bind (page, shot, heading, host, using scenes); the catalog
   and the image set ride the SAME (page, shot) order; an imaged view's
   camera-target inventory (element id · kind · text) prints WITH its
   catalog entry — a scoped read is how a legal FilmFocus.element is
   obtained (never guessed).
3. **预算** — ≤12 thumbnails (640px); exactly one named view reads back in
   high resolution (1280px); over budget is an explicit error with ZERO
   images attached (never a silent partial set) whose remedy names the
   scoped read (screenshots AND element ids); missing view / unstored
   screenshot / unreadable file are three distinct honest lines.
4. **门控** — film_edits_enabled OFF: no images (even when the dispatch
   asks), no candidate catalog, no base_ref, and the wire spec carries no
   ``views`` parameter or image sentence.
5. **钉恒胜** — an explicit @output read stays on THAT output's version;
   facts and images belong to one and the same revision base.
6. **闭环** — element ids from a scoped read compose a legal focus edit
   through the REAL edit core + REAL validator; a guessed id fails the
   same validation by name.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.schemas import (
    FilmStoryboard,
    MediaInput,
    MediaInputType,
    PageElement,
    ShotRef,
    WebPageResearch,
)
from app.tools.film.edits import film_version_identity_digest
from app.tools.film.storyboard import (
    StoryboardPage,
    execution_frames,
    storyboard_content_digest,
)

_URL = "https://example.com/product"
_PARAMS = {"focus": "product story", "language": "en", "aspect": "16:9"}


@pytest.fixture(autouse=True)
def _edits_gate_on(monkeypatch):
    """The read's image slice rides the edit capability gate — tests run
    gate-ON explicitly (the production default stays off); the gate-off
    tests re-close it themselves."""
    monkeypatch.setattr("app.config.settings.film_edits_enabled", True)


def _shots(count: int, *, with_elements: bool = True) -> tuple[ShotRef, ...]:
    out = []
    for i in range(count):
        out.append(
            ShotRef(
                key=f"user/capture/p0-s{i}.png",
                y=i * 900,
                heading="(top)" if i == 0 else f"Section {i}",
                elements=(
                    [
                        PageElement(
                            id=f"s{i}e1", kind="button", text="Start free",
                            x=0.5, y=0.5, w=0.1, h=0.05,
                        )
                    ]
                    if with_elements
                    else []
                ),
            )
        )
    return tuple(out)


def _page(shots=_shots(3), *, asset_id="a1", host="example.com") -> StoryboardPage:
    research = WebPageResearch(
        url=_URL,
        title="Acme — Ship faster",
        description="Acme turns hours of release work into minutes.",
        h1=["Ship faster"],
        h2=[],
        h3=[],
        buttons=["Start free"],
        links=[],
    )
    return StoryboardPage(
        asset_id=asset_id,
        research=research,
        screenshot_key="user/capture/p0-s0.png",
        host=host,
        shots=shots,
    )


def _board() -> FilmStoryboard:
    """A 3-scene board: the ui scene rides page 0 shot 1 with an
    element-named focus. No scene_ids — the read derives them (s1..s3)."""
    return FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": True,
                 "lines": ["Ship faster"]},
                {"type": "ui", "seconds": 9.0, "page": 0, "shot": 1,
                 "focuses": [{"at": 1.0, "element": "s1e1"}],
                 "narration": "The dashboard does the work."},
                {"type": "end", "seconds": 5.0, "name": "Acme",
                 "tagline": "Ship faster"},
            ]
        }
    )


def _base(
    board: FilmStoryboard,
    *,
    version: int = 2,
    cut_state: str | None = "spec",
    cut_frames: list[int] | None = None,
    snapshot: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        film_storyboard=board.model_dump(mode="json"),
        film_storyboard_fingerprint=f"fp-v{version}",
        film_storyboard_version=version,
        film_storyboard_params=dict(_PARAMS),
        film_storyboard_content_digest=storyboard_content_digest(board),
        film_storyboard_execution=snapshot,
        film_created_via="compose",
        film_cut_frames=cut_frames,
        film_cut_state=cut_state,
    )


class _DB:
    """The turn session stand-in: only ``get`` (the output lookup) — the
    page seat and the revision base are patched at their homes."""

    def __init__(self, output):
        self._output = output

    async def get(self, model, key):
        return self._output


def _output() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), project_id="p1", type="film", language="en",
        status="completed", render_spec=None, payload=None,
    )


def _patch_read(monkeypatch, base, pages, *, seen_resolve=None):
    import app.tools.film.storyboard as sb_mod

    async def _resolve(db, project, *, output_id=None):
        if seen_resolve is not None:
            seen_resolve.append(output_id)
        return base

    async def _load(db, project):
        return pages

    monkeypatch.setattr(sb_mod, "resolve_film_revision_base", _resolve)
    monkeypatch.setattr(sb_mod, "load_storyboard_pages", _load)
    monkeypatch.setattr("app.agents.contexts.output_one_liner", lambda o: None)


class _ImageSeam:
    """The _film_view_image stub: records (key, max_px, caption); a key in
    ``fail`` raises (a storage hiccup), a key in ``none`` reads as
    unreadable."""

    def __init__(self, *, fail: set[str] | None = None, none: set[str] | None = None):
        self.calls: list[tuple[str, int, str]] = []
        self.fail = fail or set()
        self.none = none or set()

    async def __call__(self, key: str, max_px: int, caption: str):
        self.calls.append((key, max_px, caption))
        if key in self.fail:
            raise OSError("simulated storage hiccup")
        if key in self.none:
            return None
        return MediaInput(
            type=MediaInputType.IMAGE,
            mime="image/jpeg",
            data_url=f"data:image/jpeg;base64,{key}",
            caption=caption,
        )


async def _read(monkeypatch, output, params, seam: _ImageSeam | None = None):
    from app.chat.perception import executes as ex

    if seam is not None:
        monkeypatch.setattr(ex, "_film_view_image", seam)
    return await ex.output_spec_observation(
        _DB(output), SimpleNamespace(id="p1"), params
    )


# ---------------------------------------------------------------------------
# 1. 事实表 + 时间轴来源标注
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facts_table_with_executed_cut(monkeypatch):
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    seam = _ImageSeam()

    text, images = await _read(
        monkeypatch, output, _params(output), seam
    )
    digest = storyboard_content_digest(board)
    assert f"content digest {digest[:12]}" in text
    assert f"base_ref: {film_version_identity_digest(board, _PARAMS, version=2)}" in text
    # 时间轴两时钟分行: authored = 设计值, actual = 权威帧数 ÷ fps (96f=3.2s,
    # 永不与 authored 4s 混为一谈); 总行随时间轴行
    assert "- Timeline: executed cut" in text and "total 17.2s (516f)" in text
    assert (
        '[s1] words · authored 4s · actual 3.2s (96f) · shows: "Ship faster" '
        "(dark) · silent"
    ) in text
    # 逐场: view 引用 + 取景文本带元素 id(内部读取可带 id, 呈现侧仍隐藏)
    assert (
        '[s2] ui · authored 9s · actual 9s (270f) · view: page 0 shot 1 '
        '"Section 1" · browser frame · camera: wide → push to "Start free" '
        '(button) [s1e1] at 1s → settle · narration: "The dashboard does the '
        'work."'
    ) in text
    assert (
        '[s3] end · authored 5s · actual 5s (150f) · shows: name: "Acme" · '
        'tagline: "Ship faster" · silent'
    ) in text
    # 候选清单 + used-by 映射 + 随图同行的取景元素清单 (id · kind · text)
    assert "Candidate views" in text
    assert 'page 0 — example.com "Acme — Ship faster" (asset a1):' in text
    assert '    shot 0 "(top)" · 1 elements · camera targets:' in text
    assert '      s0e1 · button · "Start free"' in text
    assert '    shot 1 "Section 1" · 1 elements · used by [s2] · camera targets:' in text
    assert '      s1e1 · button · "Start free"' in text
    # 图片: 3 张缩略图 (640px), caption 绑定 page/shot/场景
    assert [c[1] for c in seam.calls] == [640, 640, 640]
    assert len(images) == 3
    assert images[1].caption == (
        'page 0 · shot 1 "Section 1" · example.com · used by scene [s2]'
    )
    assert images[0].caption.endswith("not used by any scene")


@pytest.mark.asyncio
async def test_scene_content_covers_every_scene_type(monkeypatch):
    """逐场画面文案: 各场型的展示字段原值逐字读取 (不概括/不改写/不靠截图
    猜) — 「把结尾那句改一下」类请求的读前事实."""
    board = FilmStoryboard.model_validate(
        {
            "scenes": [
                {"type": "words", "seconds": 4.0, "dark": False,
                 "lines": ["One", "Two"]},
                {"type": "hero", "seconds": 5.0, "word": "Acme",
                 "sub": "Ship faster"},
                {"type": "divider", "seconds": 3.0, "label": "Why",
                 "roll": ["Fast", "Free"]},
                {"type": "plate", "seconds": 6.0, "title": "Numbers",
                 "cards": [{"big": "99%", "label": "uptime"},
                           {"label": "zero setup"}]},
                {"type": "reveal", "seconds": 9.0, "lead": "One more thing.",
                 "word": "Acme", "sub": "Start free", "lead_seconds": 4.5},
                {"type": "end", "seconds": 5.0, "name": "Acme",
                 "tagline": "Ship faster."},
            ]
        }
    )
    base = _base(board, cut_state="kept", cut_frames=[120, 150, 90, 180, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert 'shows: "One" / "Two"' in text
    assert 'shows: word: "Acme" · sub: "Ship faster"' in text
    assert 'shows: label: "Why" · roll: Fast / Free' in text
    assert 'shows: title: "Numbers" · cards: "99%" — "uptime" · "zero setup"' in text
    assert 'shows: lead: "One more thing." · then: "Acme" — "Start free"' in text
    assert 'shows: name: "Acme" · tagline: "Ship faster."' in text
    # 冻结时间轴的标注与总时长
    assert "- Timeline: frozen cut" in text and "total 32s (960f)" in text
    assert "[s4] plate · authored 6s · frozen 6s (180f)" in text


@pytest.mark.asyncio
async def test_timeline_provenance_labels(monkeypatch):
    """kept / draft / unreadable 三态各自的标注; 计划值永不冒充已执行值;
    authored 秒与时间轴秒分两列, 永不混成一行."""
    board = _board()
    output = _output()

    # kept: the frozen cut's frames ride verbatim (100f = 3.3s ≠ authored 4s)
    base = _base(board, cut_state="kept", cut_frames=[100, 260, 155])
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert "- Timeline: frozen cut" in text and "total 17.2s (515f)" in text
    assert "[s1] words · authored 4s · frozen 3.3s (100f)" in text

    # draft: the ONE frame seat on the version's own snapshot grid
    beats = [0.5 * i for i in range(400)]
    base = _base(
        board, cut_state="draft",
        snapshot={"music": {"beats": beats}, "pages": []},
    )
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert "- Timeline: planned" in text
    frames = execution_frames(board, beats)
    assert (
        f"[s1] words · authored 4s · planned {round(frames[0] / 30, 1):g}s "
        f"({frames[0]}f)"
    ) in text
    assert "executed cut" not in text

    # unreadable: named, zero timeline durations, never a recomputed guess
    base = _base(board, cut_state="unreadable")
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert "- Timeline: UNREADABLE" in text
    scene_block = text.split("- Scenes")[1]
    assert '[s1] words · authored 4s · shows: "Ship faster" (dark)' in scene_block
    assert " · actual " not in scene_block
    assert " · frozen " not in scene_block
    assert " · planned " not in scene_block


@pytest.mark.asyncio
async def test_corrupt_cut_frame_count_is_named_not_zipped(monkeypatch):
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270])  # 2 ≠ 3 scenes
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert "frame count does not match the scene count" in text
    scene_block = text.split("- Scenes")[1]
    assert '[s1] words · authored 4s · shows: "Ship faster" (dark)' in scene_block
    assert "(96f)" not in scene_block  # never zipped past its length


# ---------------------------------------------------------------------------
# 2. 图片预算与选择子
# ---------------------------------------------------------------------------


def _params(output, views=None):
    from app.chat.perception import executes as ex

    return ex.GetOutputSpecParams(output_id=output.id, views=views)


@pytest.mark.asyncio
async def test_default_catalog_over_budget_is_an_explicit_error(monkeypatch):
    """13 views > 12: the read attaches ZERO images and says so with the
    remedy — never a silently partial set."""
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page(shots=_shots(13))])
    seam = _ImageSeam()
    text, images = await _read(monkeypatch, output, _params(output), seam)
    assert images == []
    assert seam.calls == []  # no download was even attempted
    assert "Image budget" in text and "13 captured views" in text
    assert "never a silent partial set" in text
    assert "views" in text  # the remedy names the selection param
    # 补救明说 scope 的收获: 截图 + 取景元素清单同组, 元素 id 不另路获取
    assert "camera-target inventories (the element ids)" in text
    # 文本事实表与候选清单完整 (预算只帽图与元素清单, 不帽事实)
    assert 'shot 12 "Section 12"' in text


@pytest.mark.asyncio
async def test_named_views_select_and_single_view_reads_high_res(monkeypatch):
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])

    # A named subset: only those views, in the named order, at 640px — and
    # the scoped read's catalog carries exactly those views' element ids
    # (shot 1 was not named: its inventory stays a summary, the read never
    # implies a complete id list beyond scope).
    seam = _ImageSeam()
    from app.chat.perception import executes as ex

    views = [
        ex.ViewSelector(page=0, shot=2),
        ex.ViewSelector(page=0, shot=0),
    ]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert [c[0] for c in seam.calls] == [
        "user/capture/p0-s2.png",
        "user/capture/p0-s0.png",
    ]
    assert [c[1] for c in seam.calls] == [640, 640]
    assert len(images) == 2
    assert '      s2e1 · button · "Start free"' in text
    assert '      s0e1 · button · "Start free"' in text
    assert "      s1e1" not in text  # unscoped view: no ids promised

    # Exactly ONE named view: the high-resolution re-read (1280px).
    seam = _ImageSeam()
    views = [ex.ViewSelector(page=0, shot=1)]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert [c[1] for c in seam.calls] == [1280]
    assert len(images) == 1
    assert images[0].caption == (
        'page 0 · shot 1 "Section 1" · example.com · used by scene [s2]'
    )


@pytest.mark.asyncio
async def test_named_views_over_budget_and_unknown_views(monkeypatch):
    from app.chat.perception import executes as ex

    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])

    # 13 named views: explicit error, zero images.
    seam = _ImageSeam()
    views = [ex.ViewSelector(page=0, shot=i % 3) for i in range(13)]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert images == [] and "13 named views exceed" in text

    # An unknown (page, shot) is named honestly; the valid ones still attach.
    seam = _ImageSeam()
    views = [ex.ViewSelector(page=0, shot=1), ex.ViewSelector(page=4, shot=9)]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert len(images) == 1
    assert "- page 4 shot 9: no such captured view" in text


@pytest.mark.asyncio
async def test_missing_unstored_and_unreadable_images_are_three_lines(monkeypatch):
    """缺图(视图不存在) / 未存图(capture 降级) / 读取失败(存储) 分述."""
    from app.chat.perception import executes as ex

    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    page = _page()
    # shot 2 exists but its screenshot was never stored (falsy key).
    import dataclasses

    shots = list(page.shots)
    shots[2] = shots[2].model_copy(update={"key": ""})
    page = dataclasses.replace(page, shots=tuple(shots))
    _patch_read(monkeypatch, base, [page])
    seam = _ImageSeam(fail={"user/capture/p0-s1.png"})
    views = [
        ex.ViewSelector(page=0, shot=0),
        ex.ViewSelector(page=0, shot=1),  # unreadable (raises)
        ex.ViewSelector(page=0, shot=2),  # never stored
        ex.ViewSelector(page=0, shot=7),  # no such view
    ]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert len(images) == 1
    assert images[0].caption.startswith('page 0 · shot 0 "(top)"')
    assert "- page 0 shot 1: the stored screenshot could not be read" in text
    assert "- page 0 shot 2: no screenshot stored" in text
    assert "- page 0 shot 7: no such captured view" in text


@pytest.mark.asyncio
async def test_fold_only_page_exposes_its_fold(monkeypatch):
    """Pre-B1 fold-only page (shots=()): the fold rides screenshot_key as
    shot 0 — never an invented section list."""
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    fold_only = StoryboardPage(
        asset_id="a1",
        research=_page().research,
        screenshot_key="user/capture/fold.png",
        host="example.com",
        shots=(),
    )
    _patch_read(monkeypatch, base, [fold_only])
    seam = _ImageSeam()
    text, images = await _read(monkeypatch, output, _params(output), seam)
    assert 'shot 0 "(top)" (fold only — no element inventory)' in text
    assert 'view: page 0 shot 1 (no such captured view)' in text
    assert [c[0] for c in seam.calls] == ["user/capture/fold.png"]
    assert len(images) == 1


# ---------------------------------------------------------------------------
# 3. 门控
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_off_attaches_no_images_even_when_asked(monkeypatch):
    """门控关闭: 读取座永不带图 (dispatch 的 with_images 也救不回), 无候选
    清单, 无 base_ref —— 图片不是绕过编辑门控的另一条路."""
    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    seam = _ImageSeam()
    text, images = await _read(monkeypatch, output, _params(output), seam)
    assert images == [] and seam.calls == []
    assert "base_ref" not in text and "Candidate views" not in text
    # 世界事实仍在 (版本/逐场/时间轴来源)
    assert "Storyboard version: 2" in text and "Timeline: executed cut" in text


def test_wire_spec_gates_the_views_param_and_image_sentence(monkeypatch):
    """声明面门控 (get_output_spec): gate OFF ⇒ wire schema 无 views (孤儿
    $defs 回收), 描述无图片句; gate ON 全量恢复."""
    from app.agents.tool_loop import tool_spec
    from app.chat.perception import perception_chat_tools

    tool = perception_chat_tools("get_output_spec")[0]
    on = tool_spec(tool)["function"]
    assert "views" in on["parameters"]["properties"]
    assert "captured view screenshots" in on["description"]

    monkeypatch.setattr("app.config.settings.film_edits_enabled", False)
    off = tool_spec(tool)["function"]
    assert "views" not in off["parameters"].get("properties", {})
    assert not off["parameters"].get("$defs")  # ViewSelector never leaks
    assert "captured view screenshots" not in off["description"]
    assert "screenshot" not in off["description"]
    # The base capability stands either way.
    assert "Read one output's current state" in off["description"]


# ---------------------------------------------------------------------------
# 4. 钉恒胜 + dispatch 座
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pinned_output_reads_stay_on_that_output(monkeypatch):
    """显式 @output 读取恒指向该 Output: resolve 收到该 output_id, 事实与
    图片来自同一基准 (永不串到最新作品)."""
    board = _board()
    base = _base(board, version=1, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    seen: list = []
    _patch_read(monkeypatch, base, [_page()], seen_resolve=seen)
    seam = _ImageSeam()
    text, images = await _read(monkeypatch, output, _params(output), seam)
    assert seen == [output.id]  # the pin rode to the resolve seat
    assert "Storyboard version: 1" in text
    assert len(images) == 3


@pytest.mark.asyncio
async def test_dispatch_seat_carries_images_into_the_observation(monkeypatch):
    """run_perception_tool (双路共用的 dispatch 座): the film read's images
    ride the ToolObservation the loop projects onto the wire."""
    board = _board()
    base = _base(board, cut_state="spec", cut_frames=[96, 270, 150])
    output = _output()
    _patch_read(monkeypatch, base, [_page()])
    seam = _ImageSeam()

    from app.chat import perception as per
    from app.chat.perception import executes as ex

    monkeypatch.setattr(ex, "_film_view_image", seam)
    obs = await per.run_perception_tool(
        _DB(output),
        SimpleNamespace(id="p1"),
        "get_output_spec",
        ex.GetOutputSpecParams(output_id=output.id),
    )
    assert len(obs.images) == 3
    assert "Candidate views" in obs.text
    assert obs.images[1].caption.endswith("used by scene [s2]")


# ---------------------------------------------------------------------------
# 5. 压缩座 (step_context 一座 — 真实 PIL round-trip, 无存储)
# ---------------------------------------------------------------------------


def test_resized_data_url_bounds_the_long_edge(tmp_path):
    """The resize seat: a 1440×900 capture comes back ≤640 on the long edge
    as a legible JPEG (never an unrecognizable thumbnail); undecodable bytes
    read as None (the caller's 'could not be read' line), never a raise."""
    import base64
    import io

    from PIL import Image

    from app.pipeline.step_context import _resized_data_url

    path = tmp_path / "shot.png"
    Image.new("RGB", (1440, 900), (255, 255, 255)).save(path)
    url = _resized_data_url(path, 640)
    assert url is not None and url.startswith("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))) as img:
        assert max(img.size) <= 640 and img.size == (640, 400)

    path.write_bytes(b"not an image")
    assert _resized_data_url(path, 640) is None


# ---------------------------------------------------------------------------
# 6. 闭环: scoped 读的元素 id → 真实编辑校验 (零猜测) — 评审 P1-② 的必验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_read_element_ids_compose_a_legal_edit_through_real_validation(
    monkeypatch,
):
    """一次 scoped 读 (page 0 shot 0) 返回该视图的取景元素清单
    (id · kind · text); 用读到的 id 构造 update_scene 取景修改, 过真实
    apply_film_edits + 真实 validate_storyboard 被接受; 一个读取从未返回
    的 id (猜测) 被同一校验点名拒绝 —— 合法编辑无需猜 ID."""
    import dataclasses

    from test_film_edit_wiring_pure import (  # 跨文件 fixture 复用先例
        _board as _wiring_board,
        _page as _wiring_page,
    )

    from app.models.schemas import FilmEditUpdateScene
    from app.tools.film.edits import FilmEditError, apply_film_edits
    from app.tools.film.storyboard import (
        canonical_film_params,
        validate_storyboard,
    )

    # The 14-scene wiring board (passes the real validator) on a page whose
    # fold carries a two-element inventory.
    board = _wiring_board()
    fold = ShotRef(
        key="user/capture/fold.png",
        y=0,
        heading="(top)",
        elements=[
            PageElement(
                id="s0e1", kind="button", text="Start free",
                x=0.5, y=0.5, w=0.1, h=0.05,
            ),
            PageElement(
                id="s0e2", kind="heading", text="Why teams switch",
                x=0.5, y=0.3, w=0.6, h=0.08,
            ),
        ],
    )
    page = dataclasses.replace(_wiring_page(), shots=(fold,))

    # 1) The scoped read lands the fold's camera-target inventory verbatim.
    base = _base(board, cut_state="draft")
    output = _output()
    _patch_read(monkeypatch, base, [page])
    from app.chat.perception import executes as ex

    seam = _ImageSeam()
    views = [ex.ViewSelector(page=0, shot=0)]
    text, images = await _read(monkeypatch, output, _params(output, views=views), seam)
    assert '      s0e2 · heading · "Why teams switch"' in text
    assert len(images) == 1  # one named view → the high-res re-read

    # 2) Compose the focus edit with the id COPIED from the read — through
    #    the real edit core + the real validator (the patch path's own wiring:
    #    narration_required follows the patched voiceover flag).
    op = FilmEditUpdateScene.model_validate(
        {"op": "update_scene", "scene_id": "s3",
         "focuses": [{"at": 1.0, "element": "s0e2"}]}
    )

    def _validate(b, p):
        return validate_storyboard(
            b, [page],
            narration_required=canonical_film_params(p)["voiceover"],
        )

    result = apply_film_edits(
        board,
        dict(_PARAMS),
        [op],
        expected_base_digest=film_version_identity_digest(board, _PARAMS),
        validate=_validate,
    )
    edited = result.board.scenes[2]  # s3 keeps its positional id
    assert edited.focuses[0].element == "s0e2"
    assert edited.focuses[0].x is None  # the raw triple was replaced
    assert [
        (e.scene_id, e.fields) for e in result.change_set.edited
    ] == [("s3", ["focuses"])]
    # The base object was never mutated.
    assert board.scenes[2].focuses[0].element is None

    # 3) 对照腿: a GUESSED id (the read never listed it) fails the same real
    #    validation — the inventory is why the model never has to guess.
    guessed = FilmEditUpdateScene.model_validate(
        {"op": "update_scene", "scene_id": "s3",
         "focuses": [{"at": 1.0, "element": "s0e9"}]}
    )
    with pytest.raises(FilmEditError) as err:
        apply_film_edits(
            board,
            dict(_PARAMS),
            [guessed],
            expected_base_digest=film_version_identity_digest(board, _PARAMS),
            validate=_validate,
        )
    assert err.value.code == "validation_failed"
    assert "s0e9 names nothing in shot 0's inventory" in str(err.value)

    # 4) 文案腿 (评审 P1-① 的「据此生成合法编辑」半): 读取逐字展示的 s7 结尾
    #    tagline, 经 copy_slots 白名单改写 (文案取自同一页面语料, 且不与 s14
    #    的 end 屏撞车) 过同一真实校验被接受 —— 读到的原值就是编辑的事实起点.
    copy_op = FilmEditUpdateScene.model_validate(
        {"op": "update_scene", "scene_id": "s7",
         "copy_slots": {"tagline": "Acme turns hours of release work into minutes."}}
    )
    copy_result = apply_film_edits(
        board,
        dict(_PARAMS),
        [copy_op],
        expected_base_digest=film_version_identity_digest(board, _PARAMS),
        validate=_validate,
    )
    assert copy_result.board.scenes[6].tagline == (
        "Acme turns hours of release work into minutes."
    )
    assert copy_result.change_set.edited[0].scene_id == "s7"


# ---------------------------------------------------------------------------
# 7. 当前版本读取座 (无 output_id) + 素材漂移核对 — R3c 评审 finding ①②
# ---------------------------------------------------------------------------


def _params_no_output(views=None):
    from app.chat.perception import executes as ex

    return ex.GetOutputSpecParams(views=views)


@pytest.mark.asyncio
async def test_current_version_read_without_output_id(monkeypatch):
    """Finding ① (待产稿可重读): omitting the output id reads the film's
    CURRENT storyboard version through the revision-base seat itself (the
    live draft when one stands, else the latest delivered film) — the same
    fact table, base_ref mint, candidate catalog and images as an output
    read, so a consecutive edit turn never forms a patch against a stale
    delivered read while a newer draft stands."""
    board = _board()
    base = _base(board, version=3, cut_state="spec", cut_frames=[96, 270, 150])
    seen_resolve: list = []
    _patch_read(monkeypatch, base, [_page()], seen_resolve=seen_resolve)
    seam = _ImageSeam()

    text, images = await _read(monkeypatch, None, _params_no_output(), seam)
    assert seen_resolve == [None]  # the seat itself picked the base
    assert text.startswith(
        "Current film storyboard version (no output id named — the live "
        "draft when one stands, else the latest delivered film's version):"
    )
    assert "- Storyboard version: 3 (created via compose)" in text
    assert (
        f"base_ref: {film_version_identity_digest(board, _PARAMS, version=3)}"
        in text
    )
    assert "- Timeline: executed cut" in text
    assert "Candidate views" in text
    assert len(images) == 3


@pytest.mark.asyncio
async def test_current_version_read_without_any_version_is_honest(monkeypatch):
    """No version anywhere (no draft, no delivered film): the read says so
    and points at design_storyboard — never an empty facts table."""
    _patch_read(monkeypatch, None, [])
    text, images = await _read(monkeypatch, None, _params_no_output())
    assert "No film storyboard version exists in this project yet" in text
    assert "design_storyboard" in text
    assert images == []


@pytest.mark.asyncio
async def test_materials_drift_marks_old_views_unrecoverable(monkeypatch):
    """Finding ② (素材身份核对): the version's execution snapshot froze the
    pages' asset ids at design time; when the project's current material at
    the same index is a DIFFERENT asset (deleted / replaced / re-captured),
    the read names the drift, marks the referencing scene's view as
    unrecoverable (heading/camera never resolved against the wrong page),
    and drops the reference from the used-by mapping — the candidate
    catalog still lists the CURRENT materials an update_scene may name."""
    board = _board()
    base = _base(
        board,
        snapshot={
            "pages": [
                {
                    "asset_id": "a-old",
                    "url": _URL,
                    "screenshot_key": "user/capture/p0-s0.png",
                }
            ],
            "music": None,
        },
    )
    output = _output()
    _patch_read(monkeypatch, base, [_page(asset_id="a-new")])
    seam = _ImageSeam()
    text, images = await _read(monkeypatch, output, _params(output), seam)

    assert (
        "- Materials drift: page(s) 0 changed or were removed since this "
        "version was designed" in text
    )
    s2_line = next(l for l in text.splitlines() if l.startswith("  [s2]"))
    assert (
        "view: page 0 shot 1 (materials changed — the version's original "
        "view is unrecoverable)" in s2_line
    )
    assert "camera:" not in s2_line  # never resolved against the wrong page
    assert '"Section 1"' not in s2_line
    # The drifted reference drops out of used-by: the current view is NOT
    # passed off as the scene's original view (catalog line + caption alike).
    catalog = text.split("- Candidate views")[1]
    assert "used by [s2]" not in catalog
    assert all("used by scene" not in im.caption for im in images)
    assert len(images) == 3


@pytest.mark.asyncio
async def test_snapshotless_legacy_version_skips_the_drift_check(monkeypatch):
    """A version without an execution snapshot (legacy, pre-ADR-130) has no
    material identity to check against — the read skips the drift line
    entirely (never a false alarm) and resolves views against the current
    pages as before."""
    board = _board()
    base = _base(board, snapshot=None)
    output = _output()
    _patch_read(monkeypatch, base, [_page(asset_id="a-new")])
    text, _ = await _read(monkeypatch, output, _params(output))
    assert "Materials drift" not in text
    assert 'view: page 0 shot 1 "Section 1"' in text
    assert "used by [s2]" in text
