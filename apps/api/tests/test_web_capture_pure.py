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
from app.tools.research.capture import (
    CaptureBlocked,
    _ip_allowed,
    _parse_ip_literal,
    _stamp_elements,
    check_url_policy,
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
    asset = Asset(
        user_id=owner_id,
        type=AssetType.WEB_PAGE,
        meta={
            "capture_url": "https://agent.example/",
            "research": {
                "url": "https://agent.example/", "body": ["Client-only approval state"],
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
    assert manifest["lines"] == [{"kind": "text", "text": "Client-only approval state"}]
    assert manifest["page"]["storage_key"] in objects
    assert (manifest["page"]["width"], manifest["page"]["height"]) == (200, 400)
    view = manifest["views"][0]
    assert (view["width"], view["height"], view["css_width"]) == (200, 100, 100)
    element = view["elements"][0]
    assert element["storage_key"] in objects
    assert element["digest"]
    assert (element["image_width"], element["image_height"]) == (80, 40)
    assert element["pixel_box"]["width"] == 80


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
    assert [item["storage_key"] for item in items] == [
        "snapshots/view.png", "snapshots/element.png",
    ]
    assert "s0e0" in calls[1][1]


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
