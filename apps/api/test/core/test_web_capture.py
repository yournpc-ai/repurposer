"""Web capture pure tests (MG film 批 D1 — 网页采集资产化).

No DB, no network, no browser. Three layers:

1. ``extract_research`` / ``extract_rendered_research`` — HTML + rendered
   body text → grounding-manifest mapping, with structured-copy dedup,
   entity unescape and bounded lines.
2. Asset → SourceSnapshot freezing and Director media assembly — rendered
   lines, full-page/view/element PNGs, CSS→pixel mapping and immutable keys.
3. The SSRF static gate boundary table — ``check_url_policy`` /
   ``_parse_ip_literal`` / ``_ip_allowed``: scheme whitelist, hostname law,
   the inet_aton spelling launderers, and the IP classification truth table
   (incl. tunnel-embedded v4: mapped / NAT64 / 6to4 / Teredo). The DNS and
   proxy halves are network seams and live outside the pure suite.
"""

import io
from uuid import uuid4

import pytest
from PIL import Image

from app.models.schemas import AssetType
from app.models.tables import Asset, SourceSnapshot
from app.tools.research import capture as capture_module
from app.tools.research.capture import (
    CaptureBlocked,
    CaptureError,
    CaptureRequest,
    ShotCapture,
    _ip_allowed,
    _parse_ip_literal,
    _stamp_elements,
    capture_shots,
    check_url_policy,
    compile_capture_request,
    css_pixel_box,
    extract_rendered_research,
    extract_research,
    render_manifest_text,
)
from app.tools.video import preparation
from app.tools.video.design import _view_media_inputs
from app.editing.templates import ViewFact

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

BASIC_PAGE = """
<html><head>
  <title>  Acme — Ship Faster </title>
  <meta content="The build system for tired teams." name="description">
  <style>.x { color: red; }</style>
  <script>var title = "bait";</script>
</head><body>
  <h1>Build <em>once</em>, ship everywhere</h1>
  <h1>Build once, ship everywhere</h1>
  <h2>Why Acme</h2>
  <h3>Zero config</h3>
  <button type="submit">Start free</button>
  <a href="/pricing">Pricing</a>
  <a href="/docs">Read the docs &amp; guides</a>
  <p>Body text never enters the manifest.</p>
</body></html>
"""


def test_extract_basic_manifest():
    r = extract_research(BASIC_PAGE, "https://acme.example/")
    assert r.url == "https://acme.example/"
    assert r.title == "Acme — Ship Faster"
    # attr order flipped (content before name) still matches — the spike's
    # regex required name-first and missed this shape.
    assert r.description == "The build system for tired teams."
    # nested inline tags flatten; the duplicate h1 is deduped away.
    assert r.h1 == ["Build once, ship everywhere"]
    assert r.h2 == ["Why Acme"]
    assert r.h3 == ["Zero config"]
    assert r.buttons == ["Start free"]
    # entities unescape; body paragraphs never enter any list.
    assert r.links == ["Pricing", "Read the docs & guides"]


def test_extract_skips_script_style_svg():
    html = """
    <html><head><title>Real</title></head><body>
      <script><h1>script bait</h1></script>
      <style><h2>style bait</h2></style>
      <svg><text>svg bait</text></svg>
      <h1>Visible</h1>
    </body></html>
    """
    r = extract_research(html, "https://x.example/")
    assert r.title == "Real"
    assert r.h1 == ["Visible"]
    assert all("bait" not in item for item in r.h1 + r.h2 + r.links)


def test_extract_length_filter_and_cap():
    # 1-char items drop, >90-char items drop, >24 items truncate.
    items = "".join(f'<a href="/p{i}">item number {i}</a>' for i in range(30))
    html = f'<html><body><a href="/x">x</a><button>{"b" * 91}</button>{items}</body></html>'
    r = extract_research(html, "https://x.example/")
    assert "x" not in r.links
    assert r.buttons == []
    assert len(r.links) == 24


def test_extract_nested_capture_tags_keep_outer():
    # An <a> inside a <button>: the visible copy is one unit, attributed to
    # the OUTER tag — the inner open doesn't hijack the buffer.
    html = '<button>Buy <a href="/x">now</a> today</button>'
    r = extract_research(html, "https://x.example/")
    assert r.buttons == ["Buy now today"]
    assert r.links == []


def test_extract_malformed_html_degrades_to_partial():
    r = extract_research("<h1>Unclosed<p>mangled", "https://x.example/")
    assert r.h1 == []  # never flushed — honest absence, no exception


def test_render_manifest_text_dedupes_and_caps():
    r = extract_research(BASIC_PAGE, "https://acme.example/")
    text = render_manifest_text(r)
    assert text.startswith("Acme — Ship Faster")
    assert "Start free" in text
    # title repeated as an h1 would appear once (dict.fromkeys ordering).
    dup = extract_research(
        "<title>T</title><h1>T</h1>", "https://x.example/"
    )
    assert render_manifest_text(dup).count("T") == 1


def test_rendered_body_copy_becomes_citable_text():
    research = extract_rendered_research(
        "<title>Agent</title><h1>Ship safely</h1>",
        "https://agent.example/",
        "Ship safely\nApproval is ready\nApproval is ready\nDynamic detail loaded",
    )
    assert research.body == ["Approval is ready", "Dynamic detail loaded"]
    assert "Approval is ready" in render_manifest_text(research)
    lines = preparation._research_lines(research.model_dump())
    assert {"kind": "text", "text": "Approval is ready"} in lines
    assert {"kind": "text", "text": "Dynamic detail loaded"} in lines


def test_element_css_box_maps_to_full_page_pixels():
    element = _stamp_elements([{
        "kind": "heading", "text": "A target", "x": 0.5, "y": 0.4, "w": 0.4, "h": 0.2,
        "css": {"x": 10.25, "y": 20.5, "width": 100.5, "height": 40.25},
    }], 0)[0]
    assert element["css_box"] == {"x": 10.25, "y": 20.5, "width": 100.5, "height": 40.25}
    assert css_pixel_box(element["css_box"], 2.0) == {
        "x": 20.5, "y": 41.0, "width": 201.0, "height": 80.5,
    }


def _png(width: int, height: int) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "#336699").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_snapshot_freezes_rendered_lines_page_and_element_images(monkeypatch):
    sources = {"view": _png(200, 100), "element": _png(80, 40), "page": _png(200, 400)}
    objects: dict[str, bytes] = {}

    async def read(key):
        return sources[key] if key in sources else objects[key]

    async def exists(key):
        return key in objects

    async def save(key, data, content_type):
        objects[key] = data

    async def register(_db, **kwargs):
        return kwargs["meta"]

    monkeypatch.setattr(preparation.storage, "read", read)
    monkeypatch.setattr(preparation.storage, "exists", exists)
    monkeypatch.setattr(preparation.storage, "save", save)
    monkeypatch.setattr(preparation, "register_snapshot", register)
    owner_id = uuid4()
    plan = _bound_plan(_request())
    asset = Asset(
        user_id=owner_id,
        type=AssetType.WEB_PAGE,
        meta={
            "capture_url": "https://agent.example/",
            "capture_plan": plan.model_dump(mode="json"),
            "capture_plan_digest": capture_module.capture_plan_digest(plan),
            "capture_issues": [{"state_id": "settled", "output_id": "missing", "error": "absent"}],
            "capture_issue_count": 1,
            "research": {
                "url": "https://agent.example/", "body": ["Client-only approval state"],
                "body_truncated": True,
            },
            "page": {
                "key": "page", "css_width": 100, "css_height": 200,
                "device_scale_factor": 2.0,
            },
            "shots": [{
                "key": "view", "y": 0, "heading": "Ready",
                "css_width": 100, "css_height": 50, "device_scale_factor": 2.0,
                "elements": [{
                    "id": "s0e0", "kind": "heading", "text": "Approval",
                    "x": 0.5, "y": 0.5, "w": 0.8, "h": 0.8,
                    "css_box": {"x": 10, "y": 5, "width": 40, "height": 20},
                    "pixel_box": {"x": 20, "y": 10, "width": 80, "height": 40},
                    "device_scale_factor": 2.0, "image_key": "element",
                }],
            }],
        },
    )
    manifest = await preparation.snapshot_web_asset(None, asset, owner_id=owner_id)
    assert manifest["lines"] == [{
        "kind": "text", "text": "Client-only approval state", "line_id": "line_0000",
    }]
    assert manifest["body_truncated"] is True
    assert manifest["capture_issues"] == [{"state_id": "settled", "output_id": "missing", "error": "absent"}]
    assert manifest["capture_issue_count"] == 1
    assert all("truncat" not in line["text"].lower() for line in manifest["lines"])
    assert manifest["page"]["storage_key"] in objects
    assert (manifest["page"]["width"], manifest["page"]["height"]) == (200, 400)
    view = manifest["views"][0]
    assert (view["width"], view["height"], view["css_width"]) == (200, 100, 100)
    element = view["elements"][0]
    assert element["storage_key"] in objects
    assert element["digest"]
    assert (element["image_width"], element["image_height"]) == (80, 40)
    assert element["pixel_box"]["width"] == 80


def test_director_reads_only_known_fixed_arc_group_echoes():
    from app.editing.director import LaunchFilmDirection

    payload = {
        "cold_open": ["Who decides?"],
        "hero": {"hero_word": "L1", "hero_sub": "L3"},
        "chapters": [
            {"pillar": "L4", "chapter_title": "One"},
            {"pillar": "L5", "chapter_title": "Two"},
            {"pillar": "L6", "chapter_title": "Three"},
        ],
        "reveal": {"reveal_lead": "One more thing", "reveal_word": "L7", "reveal_sub": "L8"},
        "proof": {"citation": "L47"},
        "end": {"end_name": "L1", "end_tagline": "L9"},
    }
    direction = LaunchFilmDirection.model_validate(payload)
    assert direction.hero_word.line == 1
    assert direction.reveal_lead == "One more thing"
    assert direction.end_tagline.line == 9
    with pytest.raises(ValueError, match="proof"):
        LaunchFilmDirection.model_validate({**payload, "proof": {"text": "Not a slot"}})
    with pytest.raises(ValueError, match="hero"):
        LaunchFilmDirection.model_validate({
            **payload, "hero": {"hero_word": "L1", "hero_sub": "L3", "unknown": "reject"},
        })


@pytest.mark.asyncio
async def test_director_media_inputs_include_the_frozen_element_crop(monkeypatch):
    calls = []

    async def media_input(key, caption, max_px):
        calls.append((key, caption, max_px))
        return {"storage_key": key, "caption": caption}

    from app.pipeline import step_context
    monkeypatch.setattr(step_context, "media_input_for_image", media_input)
    snapshot_id = uuid4()
    elements = [{
        "id": "s0e0", "kind": "heading", "storage_key": "snapshots/element.png",
        "css_box": {"x": 10, "y": 5, "width": 40, "height": 20},
        "device_scale_factor": 2.0,
    }]
    view = {
        "view_id": "view-0", "storage_key": "snapshots/view.png",
        "width": 200, "height": 100, "elements": elements,
    }
    snapshot = SourceSnapshot(
        id=snapshot_id, digest="d" * 64, kind="web", meta={"views": [view]},
    )
    facts = ViewFact(
        snapshot_id=snapshot_id, snapshot_digest="d" * 64, view_id="view-0",
        width=200, height=100, elements=elements, heading="Ready", page=0,
    )
    items = await _view_media_inputs([snapshot], [facts])
    assert [item["storage_key"] for item in items] == ["snapshots/view.png"]
    from types import SimpleNamespace
    items = await _view_media_inputs(
        [snapshot],
        [facts],
        targets=[SimpleNamespace(
            snapshot_id=snapshot_id, view_id="view-0", element_id="s0e0",
        )],
    )
    assert [item["storage_key"] for item in items] == [
        "snapshots/view.png", "snapshots/element.png",
    ]
    assert "s0e0" in calls[2][1]


# ---------------------------------------------------------------------------
# SSRF static gate — scheme + host boundary table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://example.com/path?q=1",
        "https://EXAMPLE.com./",  # case + trailing dot normalize
        "https://172.15.0.1/",  # public 172.x — the octet law's edge
        "https://172.32.0.1/",
        "https://8.8.8.8/",
        "https://[2001:4860:4860::8888]/",
        "https://[::ffff:8.8.8.8]/",  # mapped PUBLIC v4 — classified by the embed
    ],
)
def test_policy_allows_public(url):
    host = check_url_policy(url)
    assert host  # returns the normalized host


@pytest.mark.parametrize(
    "url",
    [
        # scheme whitelist
        "file:///etc/passwd",
        "ftp://example.com/x",
        "data:text/html,<h1>x</h1>",
        "javascript:alert(1)",
        "chrome://settings",
        "example.com/no-scheme",
        # obviously-internal hostnames (web.py's law, one seat)
        "http://localhost/",
        "http://LOCALHOST:8080/",
        "http://localhost./",  # trailing-dot spelling
        "http://printer.local/",
        "http://127.0.0.1/",
        "http://127.0.0.1./",
        "http://evil@127.0.0.1/",  # userinfo laundering
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",  # cloud metadata
        "http://0.0.0.0/",
        # inet_aton spelling launderers (Chrome/libc accept all of these)
        "http://2130706433/",  # 127.0.0.1 as one decimal int
        "http://0x7f000001/",  # hex int
        "http://0177.0.0.1/",  # octal dotted
        "http://127.1/",  # two-part shorthand
        "http://0x7f.1/",  # mixed radix shorthand
        # literal IP classification
        "http://100.64.0.1/",  # CGNAT shared space
        "http://192.0.2.1/",  # documentation range
        "http://198.18.0.1/",  # benchmarking range
        "http://224.0.0.1/",  # multicast
        "http://255.255.255.255/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",  # v4-mapped laundering
        "http://[64:ff9b::127.0.0.1]/",  # NAT64-embedded loopback
        "http://[2002:7f00:1::]/",  # 6to4-embedded loopback
    ],
)
def test_policy_blocks_internal(url):
    with pytest.raises(CaptureBlocked):
        check_url_policy(url)


def test_policy_normalizes_host():
    assert check_url_policy("https://EXAMPLE.com./path") == "example.com"


# ---------------------------------------------------------------------------
# IP literal parsing + classification truth table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("2130706433", "127.0.0.1"),
        ("0x7f000001", "127.0.0.1"),
        ("0177.0.0.1", "127.0.0.1"),
        ("127.1", "127.0.0.1"),
        ("0x7f.1", "127.0.0.1"),
        ("::1", "::1"),
        ("::ffff:8.8.8.8", "::ffff:808:808"),
    ],
)
def test_parse_ip_literal_forms(host, expected):
    import ipaddress

    assert _parse_ip_literal(host) == ipaddress.ip_address(expected)


@pytest.mark.parametrize("host", ["example.com", "127.0.0.1.256", "1.2.3.4.5", "0xzz", ""])
def test_parse_ip_literal_non_ip(host):
    assert _parse_ip_literal(host) is None


@pytest.mark.parametrize(
    ("ip", "allowed"),
    [
        ("8.8.8.8", True),
        ("172.15.0.1", True),
        ("172.32.0.1", True),
        ("2001:4860:4860::8888", True),
        ("::ffff:8.8.8.8", True),  # mapped PUBLIC — classified by the embed
        ("127.0.0.1", False),
        ("10.0.0.1", False),
        ("172.16.0.1", False),
        ("172.31.255.255", False),
        ("192.168.1.1", False),
        ("169.254.1.1", False),
        ("0.0.0.0", False),
        ("100.64.0.1", False),
        ("192.0.2.1", False),
        ("198.18.0.1", False),
        ("224.0.0.1", False),
        ("255.255.255.255", False),
        ("::1", False),
        ("fe80::1", False),
        ("fc00::1", False),
        ("::ffff:127.0.0.1", False),
        ("64:ff9b::127.0.0.1", False),  # NAT64-embedded loopback
        ("2002:7f00:1::", False),  # 6to4-embedded loopback
        # Teredo-embedded 192.0.2.45 (documentation range) — the tunnel
        # syntax is not a laundering door.
        ("2001:0000:4136:e378:8000:63bf:3fff:fdd2", False),
    ],
)
def test_ip_allowed_truth_table(ip, allowed):
    import ipaddress

    assert _ip_allowed(ipaddress.ip_address(ip)) is allowed


# ---------------------------------------------------------------------------
# Generic CaptureRequest, bounded collections and partial success
# ---------------------------------------------------------------------------


def _source_facts():
    return [{
        "id": uuid4(), "kind": "web", "digest": "a" * 64,
        "meta": {"canonical_url": "https://example.com/"},
    }]


def _request(**overrides):
    payload = {
        "source_url": "https://example.com/",
        "source_snapshot_id": _source_facts()[0]["id"],
        "states": [{"state_id": "settled"}],
        "targets": [{"target_id": "cards", "selector": ".card", "all": True, "max_items": 2}],
        "outputs": [{"output_id": "cards", "state_id": "settled", "kind": "elements", "target_ids": ["cards"]}],
    }
    payload.update(overrides)
    return CaptureRequest.model_validate(payload)


def _bound_plan(request):
    return compile_capture_request(request, snapshots=[{
        "id": request.source_snapshot_id, "kind": "web", "digest": "a" * 64,
        "meta": {"canonical_url": request.source_url},
    }])


def test_capture_state_reads_empty_actions_as_no_actions():
    for value in (None, ""):
        request = _request(states=[{"state_id": "settled", "actions": value}])
        assert request.states[0].actions == []


def test_capture_request_wire_has_no_execution_plan_fields():
    from app.chat.turn_tools import _video_material_tools

    tool = next(tool for tool in _video_material_tools() if tool.name == "capture_web")
    assert tool.params_model is CaptureRequest
    schema = CaptureRequest.model_json_schema()

    def property_names(value):
        if isinstance(value, dict):
            yield from (value.get("properties") or {}).keys()
            for child in value.values():
                yield from property_names(child)
        elif isinstance(value, list):
            for child in value:
                yield from property_names(child)

    names = set(property_names(schema))
    assert {"states", "targets", "outputs", "source_snapshot_id"}.issubset(names)
    assert not {"artifacts", "artifact_id", "artifact_role", "paired_view_id", "role", "shot_id", "arc"} & names
    with pytest.raises(ValueError):
        CaptureRequest.model_validate(_request().model_dump() | {"artifacts": []})
    with pytest.raises(ValueError):
        CaptureRequest.model_validate(_request().model_dump() | {"outputs": [{
            "output_id": "bad", "state_id": "settled", "kind": "page", "required": True,
        }]})


def test_capture_request_compiles_baselines_scale_and_same_state_lineage():
    request = _request(outputs=[
        {"output_id": "page", "state_id": "settled", "kind": "page", "scale": 2},
        {"output_id": "cards", "state_id": "settled", "kind": "elements", "target_ids": ["cards"], "scale": 4, "transparent": True},
        {"output_id": "plate", "state_id": "settled", "kind": "blank_plate", "target_ids": ["cards"], "scale": 4},
    ])
    plan = _bound_plan(request)
    by_id = {artifact.artifact_id: artifact for artifact in plan.artifacts}
    assert by_id["baseline-0-x2"].role == "view"
    assert by_id["baseline-0-x4"].role == "view"
    assert by_id["cards"].paired_view_id == "baseline-0-x4"
    assert by_id["plate"].paired_view_id == "baseline-0-x4"
    assert by_id["cards"].state_id == by_id["baseline-0-x4"].state_id
    assert by_id["cards"].scale == by_id["baseline-0-x4"].scale == 4
    assert not any(artifact.required for artifact in plan.artifacts)
    assert "shot_id" not in plan.model_dump() and "arc" not in plan.model_dump()
    assert capture_module.capture_plan_digest(plan) == capture_module.capture_plan_digest(_bound_plan(request))


def test_capture_request_rejects_collection_actions_and_bad_output_shapes():
    with pytest.raises(ValueError, match="single-element"):
        _request(states=[{
            "state_id": "settled",
            "actions": [{"kind": "click", "target_id": "cards"}],
        }])
    with pytest.raises(ValueError, match="do not accept"):
        _request(outputs=[{"output_id": "page", "state_id": "settled", "kind": "page", "target_ids": ["cards"]}])
    with pytest.raises(ValueError, match="exactly one"):
        _request(outputs=[{"output_id": "bad", "state_id": "settled", "kind": "elements", "target_ids": []}])
    with pytest.raises(ValueError, match="one or more"):
        _request(outputs=[{"output_id": "bad", "state_id": "settled", "kind": "blank_plate", "target_ids": []}])


class _FakeClock:
    async def install(self):
        return None

    async def pause_at(self, _value):
        return None


class _FakeHandle:
    def __init__(self, index):
        self.index = index

    async def evaluate(self, script, _arg=None):
        if script == capture_module._JS_CAPTURE_TARGET:
            return {
                "text": f"Card {self.index}", "kind": "text",
                "full": {"x": 10 + self.index * 30, "y": 20, "width": 24, "height": 12},
                "visible": {"x": 10 + self.index * 30, "y": 20, "width": 24, "height": 12},
                "subject": {"x": 10 + self.index * 30, "y": 20, "width": 24, "height": 12},
                "subject_visible": {"x": 10 + self.index * 30, "y": 20, "width": 24, "height": 12},
                "viewport": {"width": 1440, "height": 900},
                "page": {"width": 1440, "height": 900},
                "scroll_x": 0, "scroll_y": 0, "covered": False, "visually_truncated": False,
            }
        return None


class _FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page

    async def close(self):
        return None


class _FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def new_context(self, **_kwargs):
        return _FakeContext(self.page)


class _FakePage:
    def __init__(self, count=2):
        self.url = "https://example.com/"
        self.clock = _FakeClock()
        self.handles = [_FakeHandle(index) for index in range(count)]
        self.hidden = []
        self.screenshots = []

    async def goto(self, *_args, **_kwargs):
        return None

    async def query_selector_all(self, _selector):
        return self.handles

    async def content(self):
        return "<title>Example</title>"

    async def evaluate(self, script, arg=None):
        if script == "Date.now()":
            return 1000
        if script == capture_module._JS_ELEMENTS:
            return []
        if script == "() => document.body ? document.body.innerText : ''":
            return ""
        if script == capture_module._JS_HIDE_FOR_PLATE:
            self.hidden.append(list(arg))
            return None
        if script in {capture_module._JS_RESTORE_PLATE, capture_module._JS_RESTORE_CUTOUT}:
            return None
        if "document.documentElement.scrollWidth" in script:
            return {"width": 1440, "height": 900, "y": 0}
        raise AssertionError(f"unexpected page evaluation: {script[:80]}")

    async def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)
        return _png(24, 12) if kwargs.get("clip") else _png(100, 80)


@pytest.fixture
def settled_capture_stubs(monkeypatch):
    async def settle(_page):
        return None

    async def dismiss(_page):
        return None

    async def preload(_page):
        return 900

    monkeypatch.setattr(capture_module, "_settle", settle)
    monkeypatch.setattr(capture_module, "_dismiss_consent", dismiss)
    monkeypatch.setattr(capture_module, "_dismiss_overlays", dismiss)
    monkeypatch.setattr(capture_module, "_preload", preload)


@pytest.mark.asyncio
async def test_collection_members_and_common_blank_plate(settled_capture_stubs):
    request = _request(outputs=[
        {"output_id": "opaque", "state_id": "settled", "kind": "elements", "target_ids": ["cards"]},
        {"output_id": "alpha", "state_id": "settled", "kind": "elements", "target_ids": ["cards"], "transparent": True},
        {"output_id": "plate", "state_id": "settled", "kind": "blank_plate", "target_ids": ["cards"]},
    ])
    plan = _bound_plan(request)
    page = _FakePage()
    research, shots, issues = await capture_module._capture_plan_state(
        _FakeBrowser(page), plan, plan.states[0], plan.artifacts,
        device_scale_factor=2.0, state_index=0, url=plan.capture_url,
    )
    assert research.title == "Example" and not issues
    assert [shot.output_id for shot in shots] == [None, "opaque", "opaque", "alpha", "alpha", "plate"]
    assert [shot.member_id for shot in shots[1:3]] == ["cards-m000", "cards-m001"]
    baseline = shots[0]
    assert [element["member_id"] for element in baseline.elements] == ["cards-m000", "cards-m001"]
    assert all(element["member_digest"] for element in baseline.elements)
    assert all(element["full_css_box"] for element in baseline.elements)
    assert shots[1].transparent is False and shots[3].transparent is True
    assert len(page.hidden) == 1 and page.hidden[0] == page.handles
    assert any(call.get("omit_background") for call in page.screenshots)
    assert any(not call.get("omit_background", False) and call.get("clip") for call in page.screenshots)


@pytest.mark.asyncio
async def test_one_output_failure_preserves_other_outputs_and_reports_issue(settled_capture_stubs):
    request = _request(outputs=[
        {"output_id": "page", "state_id": "settled", "kind": "page"},
        {"output_id": "missing", "state_id": "settled", "kind": "elements", "target_ids": ["cards"]},
    ])
    plan = _bound_plan(request)
    page = _FakePage(count=0)
    _research, shots, issues = await capture_module._capture_plan_state(
        _FakeBrowser(page), plan, plan.states[0], plan.artifacts,
        device_scale_factor=2.0, state_index=0, url=plan.capture_url,
    )
    assert [shot.output_id for shot in shots] == [None, "page"]
    assert issues == [{
        "state_id": "settled", "output_id": "missing", "target_id": "cards",
        "error": "capture target 'cards' is absent after the state actions",
    }]


def _capture_plan_for_outcome():
    return _bound_plan(_request())


@pytest.mark.asyncio
async def test_capture_outcome_aggregates_and_bounds_all_issues(monkeypatch):
    plan = _capture_plan_for_outcome()
    shot = ShotCapture(y=0, heading="ok", png=_png(20, 10), view_id="baseline-0-x2", state_id="settled", artifact_role="view")
    issues = [capture_module._capture_issue("settled", f"failure-{index}", output_id=f"out-{index}") for index in range(70)]

    async def fetch(_url):
        return "<title>Example</title>", plan.capture_url

    async def policy(*_args):
        return [shot], None, issues

    monkeypatch.setattr(capture_module, "_fetch_html", fetch)
    monkeypatch.setattr(capture_module, "resolve_chrome_path", lambda: "/fake/chrome")
    monkeypatch.setattr(capture_module, "_capture_shots_with_policy", policy)
    outcome = await capture_shots(plan)
    assert outcome.shots == [shot]
    assert len(outcome.capture_issues) == 64
    assert outcome.capture_issue_count == 70
    assert outcome.capture_issues_truncated is True
    assert outcome.capture_issues[-1]["error"] == "failure-63"


@pytest.mark.asyncio
async def test_zero_usable_views_fail_with_all_bounded_issues(monkeypatch):
    plan = _capture_plan_for_outcome()
    issues = [
        capture_module._capture_issue("settled", "first failed", output_id="one"),
        capture_module._capture_issue("settled", "second failed", output_id="two"),
    ]

    async def fetch(_url):
        return "<title>Example</title>", plan.capture_url

    async def policy(*_args):
        return [], None, issues

    monkeypatch.setattr(capture_module, "_fetch_html", fetch)
    monkeypatch.setattr(capture_module, "resolve_chrome_path", lambda: "/fake/chrome")
    monkeypatch.setattr(capture_module, "_capture_shots_with_policy", policy)
    with pytest.raises(CaptureError) as raised:
        await capture_shots(plan)
    assert "no usable views" in str(raised.value)
    assert "first failed" in str(raised.value) and "second failed" in str(raised.value)


def test_opaque_and_transparent_element_resources_have_real_fixed_consumption():
    common = {
        "id": uuid4(), "kind": "image", "digest": "b" * 64,
        "storage_key": "source-snapshots/element.png",
        "meta": {"origin": "web_view", "artifact_role": "cutout", "width": 20, "height": 10},
    }
    base = {key: value for key, value in common.items() if key != "meta"}
    opaque = preparation.canonical_resource(SourceSnapshot(**base, meta={**common["meta"], "transparent": False}))
    raw_alpha = preparation.canonical_resource(SourceSnapshot(**base, meta={**common["meta"], "transparent": True}))
    canvas_alpha = preparation.canonical_resource(SourceSnapshot(**base, meta={**common["meta"], "transparent": True, "full_canvas": True}))
    assert opaque["consumption"] == "generator_resource" and opaque["fixed_resource"]["path"].endswith(".png")
    assert raw_alpha["consumption"] == "lineage_only" and "fixed_resource" not in raw_alpha
    assert canvas_alpha["consumption"] == "generator_resource" and canvas_alpha["fixed_resource"]


def test_partial_capture_snapshot_does_not_require_failed_peer_views():
    from app.editing.validators import _validate_capture_snapshot

    plan = _bound_plan(_request(outputs=[
        {"output_id": "page", "state_id": "settled", "kind": "page"},
        {"output_id": "missing", "state_id": "settled", "kind": "elements", "target_ids": ["cards"]},
    ]))
    problems = []
    _validate_capture_snapshot(uuid4(), {"meta": {
        "capture_plan": plan.model_dump(mode="json"),
        "views": [{
            "view_id": "page", "state_id": "settled", "artifact_role": "view",
            "storage_key": "source-snapshots/page.png", "digest": "c" * 64,
            "actions": [], "route": "/", "page_height": 900,
        }],
    }}, problems)
    assert problems == []


@pytest.mark.asyncio
async def test_asset_storage_failure_keeps_other_captured_views(monkeypatch):
    from app.pipeline import web_capture as processor

    plan = _bound_plan(_request(outputs=[
        {"output_id": "first", "state_id": "settled", "kind": "page"},
        {"output_id": "second", "state_id": "settled", "kind": "page"},
    ]))
    shots = [
        ShotCapture(
            y=0, heading="first", png=_png(100, 80), view_id="baseline-0-x2",
            state_id="settled", artifact_role="view",
        ),
        ShotCapture(
            y=0, heading="first", png=_png(100, 80), view_id="first",
            state_id="settled", output_id="first", artifact_role="view",
        ),
        ShotCapture(
            y=0, heading="second", png=_png(100, 80), view_id="second",
            state_id="settled", output_id="second", artifact_role="view",
        ),
    ]
    outcome = capture_module.CaptureOutcome(
        research=extract_research("<title>Example</title>", plan.capture_url),
        text="Example", screenshot=shots[0].png, final_url=plan.capture_url,
        shots=shots, capture_plan=plan,
    )

    async def capture(_plan):
        return outcome

    async def save(key, _data, **_kwargs):
        if key.endswith("-s2.png"):
            raise OSError("disk refused second output")

    monkeypatch.setattr(processor, "capture_shots", capture)
    monkeypatch.setattr(processor, "save", save)
    asset = Asset(
        id=uuid4(), user_id=uuid4(), project_id=uuid4(), type=AssetType.WEB_PAGE,
        meta={"capture_url": plan.capture_url, "capture_plan": plan.model_dump(mode="json")},
    )
    result = await processor.web_capture_processor(asset, None)
    assert [shot["view_id"] for shot in result.meta["shots"]] == ["baseline-0-x2", "first"]
    assert result.meta["capture_issue_count"] == 1
    assert result.meta["capture_issues"][0]["output_id"] == "second"
    assert "disk refused second output" in result.meta["capture_issues"][0]["error"]


@pytest.mark.asyncio
async def test_capture_element_lineage_survives_asset_meta_validation(monkeypatch):
    from app.pipeline import web_capture as processor

    plan = _capture_plan_for_outcome()
    lineage = {
        "id": "cards-m000", "target_id": "cards", "member_id": "cards-m000",
        "member_digest": "d" * 64, "kind": "image", "text": "Card",
        "selector": ".card", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2,
    }
    shot = ShotCapture(
        y=0, heading="cards", png=_png(100, 80), elements=[lineage],
        view_id="baseline-0-x2", state_id="settled", artifact_role="view",
    )
    outcome = capture_module.CaptureOutcome(
        research=extract_research("<title>Example</title>", plan.capture_url),
        text="Example", screenshot=shot.png, final_url=plan.capture_url,
        shots=[shot], capture_plan=plan,
    )

    async def capture(_plan):
        return outcome

    async def save(_key, _data, **_kwargs):
        return None

    monkeypatch.setattr(processor, "capture_shots", capture)
    monkeypatch.setattr(processor, "save", save)
    asset = Asset(
        id=uuid4(), user_id=uuid4(), project_id=uuid4(), type=AssetType.WEB_PAGE,
        meta={"capture_url": plan.capture_url, "capture_plan": plan.model_dump(mode="json")},
    )
    result = await processor.web_capture_processor(asset, None)
    stored = result.meta["shots"][0]["elements"][0]
    assert stored["target_id"] == "cards"
    assert stored["member_id"] == "cards-m000"
    assert stored["member_digest"] == "d" * 64
