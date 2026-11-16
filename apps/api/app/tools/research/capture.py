"""Rich web capture: one explicit URL → structured copy inventory + screenshot.

The capture half of the "URL → web_page asset" recipe (MG film batch D1).
Two layers:

- ``extract_research`` / ``extract_rendered_research`` — PURE: settled HTML
  and visible DOM text → the grounding manifest (title / meta description /
  h1-h3 / paragraph, button and link copy, plus otherwise-unrepresented
  rendered body lines). Parser-based (stdlib HTMLParser, malformed-HTML
  tolerant).
- ``capture_page`` — NETWORK: fetch the HTML (per-hop redirect policy,
  byte cap), then use headless Chrome for settled DOM copy, 2× full-page and
  viewport PNGs, and the selected camera candidates' element crops/CSS boxes.

SSRF is enforced at BROWSER level (禁止事项 11 — one policy for top-level
navigation, redirects and sub-resources alike): the screenshot rides an
ephemeral loopback policy proxy, so EVERY request Chrome makes is checked
at connect time — scheme whitelist, private/reserved IP refusal (DNS
resolved and re-verified by us, then dialed directly, closing the rebinding
window), per-capture request/byte caps, an overall wall clock, and a
throwaway credential-free profile (fresh ``--user-data-dir`` per capture).

Degrade-honest law (web.py precedent): a failed screenshot degrades to
``screenshot=None`` (the copy manifest is the substance); a policy-blocked
or unreachable page raises :class:`CaptureError` so the asset settles
FAILED with the honest reason, never a silent empty.
"""

import asyncio
import contextlib
import hashlib
import ipaddress
import re
import shutil
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.models.schemas import WebPageResearch
from app.tools.research.web import _HEADERS, _host_blocked

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Extraction (pure)
# ---------------------------------------------------------------------------

# Spike parity: list items are visible copy of 2..90 chars, deduped, capped
# per field — long enough to hold a CTA, short enough that a paragraph never
# smuggles itself into the button inventory.
_ITEM_MIN_LEN = 2
_ITEM_MAX_LEN = 90
_ITEMS_PER_FIELD = 24
_TITLE_MAX_LEN = 200
_DESCRIPTION_MAX_LEN = 500
# Paragraph copy (the hero claim / feature blurb a film quotes) — one <p> can
# run a sentence-plus; beyond this the parser truncates honestly.
_PARAGRAPH_MAX_LEN = 240

# The extracted_text rendering of the manifest — the prompt-budget twin of
# web.py's FETCH_TEXT_CAP. Rendered body lines remain separately bounded below.
MANIFEST_TEXT_CAP = 20000
_RENDERED_BODY_LINE_CAP = 500
_RENDERED_BODY_LINES_CAP = 80


class _CopyInventoryParser(HTMLParser):
    """Pull the visible copy inventory out of a page: <title>, the meta
    description, heading text (h1-h3), button labels, anchor text, and
    paragraph copy (<p> — the hero claims / feature blurbs a film quotes;
    paragraphs carry their own longer bound, the CTA cap would drop them).
    Script/style/svg bodies are skipped; entities are unescaped by the
    parser (convert_charrefs)."""

    _SKIP = {"script", "style", "noscript", "svg", "template"}
    _CAPTURE = {"title", "h1", "h2", "h3", "button", "a", "p"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
        self.paragraphs: list[str] = []
        self._skip_depth = 0
        self._current: str | None = None  # the capture tag being accumulated
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag == "meta":
            attr = {k.lower(): v for k, v in attrs if v is not None}
            if attr.get("name", "").lower() == "description" and not self.description:
                content = " ".join(attr.get("content", "").split())
                if content:
                    self.description = content[:_DESCRIPTION_MAX_LEN]
            return
        if tag == "br" and self._current is not None:
            # A <br> inside captured copy renders as a visible line break —
            # it separates words just like whitespace does, so it must leave
            # a boundary in the buffer ("actions.<br>Not" → "actions. Not").
            self._buf.append(" ")
            return
        if tag in self._CAPTURE and self._current is None:
            # Nested capture tags (an <a> inside a <button>) keep attributing
            # to the OUTER tag — the visible copy is one unit.
            self._current = tag
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag != self._current:
            return
        text = " ".join("".join(self._buf).split())
        self._current = None
        self._buf = []
        if tag == "title":
            if text and not self.title:
                self.title = text[:_TITLE_MAX_LEN]
            return
        # Paragraphs carry a longer bound (a hero claim is one sentence-plus,
        # not a CTA); everything else keeps the copy-item cap.
        max_len = _PARAGRAPH_MAX_LEN if tag == "p" else _ITEM_MAX_LEN
        if not (_ITEM_MIN_LEN <= len(text) <= max_len):
            return
        target = {
            "h1": self.h1,
            "h2": self.h2,
            "h3": self.h3,
            "button": self.buttons,
            "a": self.links,
            "p": self.paragraphs,
        }[tag]
        if text not in target:
            target.append(text)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._current is not None:
            self._buf.append(data)


def extract_research(html: str, url: str) -> WebPageResearch:
    """HTML → the grounding manifest. Pure: no network, no clock."""
    parser = _CopyInventoryParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 — malformed markup degrades to partial
        logger.warning("web_capture_parse_degraded", url=url)
    return WebPageResearch(
        url=url,
        title=parser.title,
        description=parser.description,
        h1=parser.h1[:_ITEMS_PER_FIELD],
        h2=parser.h2[:_ITEMS_PER_FIELD],
        h3=parser.h3[:_ITEMS_PER_FIELD],
        buttons=parser.buttons[:_ITEMS_PER_FIELD],
        links=parser.links[:_ITEMS_PER_FIELD],
        paragraphs=parser.paragraphs[:_ITEMS_PER_FIELD],
    )


def extract_rendered_research(html: str, url: str, body_text: str) -> WebPageResearch:
    """Ground copy in the settled DOM, then add visible body lines the
    structured inventory could not represent (including client-only copy)."""
    research = extract_research(html, url)
    seen = {
        text
        for value in (
            research.title,
            research.description,
            *research.h1,
            *research.h2,
            *research.h3,
            *research.paragraphs,
            *research.buttons,
            *research.links,
        )
        for text in [value]
    }
    body: list[str] = []
    truncated = False
    for raw in body_text.splitlines():
        text = " ".join(raw.split())
        if len(text) < 2 or text in seen:
            continue
        if len(text) > _RENDERED_BODY_LINE_CAP:
            text = text[:_RENDERED_BODY_LINE_CAP].rstrip()
            truncated = True
        if len(body) >= _RENDERED_BODY_LINES_CAP:
            truncated = True
            break
        body.append(text)
        seen.add(text)
    return research.model_copy(update={"body": body, "body_truncated": truncated})


def render_manifest_text(research: WebPageResearch) -> str:
    """The manifest as plain text — the asset's ``extracted_text`` seat, so
    a web_page counts as text material for the material predicates and the
    assembly layer reads it through the ONE text seat (asset_text_content).
    """
    parts = [research.title, research.description]
    for listing in (
        research.h1,
        research.h2,
        research.h3,
        research.paragraphs,
        research.body,
        research.buttons,
        research.links,
    ):
        parts.extend(listing)
    text = "\n".join(dict.fromkeys(p for p in parts if p))
    return text[:MANIFEST_TEXT_CAP]


# ---------------------------------------------------------------------------
# SSRF policy (pure core + DNS seam)
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}


class CaptureError(Exception):
    """An honest capture failure (network, timeout, too-large) — the asset
    settles FAILED with this message."""


class CaptureBlocked(CaptureError):
    """A policy refusal (scheme / internal host / resolved IP) — same
    FAILED path, distinct name so the ledger reads policy from accident."""


def _parse_num(part: str) -> int | None:
    """One inet_aton numeric component: decimal, 0-octal or 0x-hex."""
    try:
        if part.lower().startswith("0x"):
            return int(part, 16)
        if len(part) > 1 and part.startswith("0"):
            return int(part, 8)
        if part.isdigit():
            return int(part, 10)
    except ValueError:
        return None
    return None


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host that is an IP LITERAL — including the inet_aton family
    Chrome and libc accept (``2130706433``, ``0x7f000001``, ``0177.0.0.1``,
    ``127.1``), the classic SSRF spelling launderers. None = a hostname."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    nums = [_parse_num(p) for p in parts]
    if any(n is None for n in nums):
        return None
    values = [n for n in nums if n is not None]
    # inet_aton arity law: the leading parts are one byte each; the last
    # part absorbs the remaining bytes (a 1-part form is a full 32-bit int).
    if any(v > 0xFF for v in values[:-1]):
        return None
    last_bits = 8 * (5 - len(values))
    if values[-1] > (1 << last_bits) - 1:
        return None
    value = 0
    for v in values[:-1]:
        value = (value << 8) | v
    value = (value << last_bits) | values[-1]
    return ipaddress.IPv4Address(value)


# NAT64 well-known prefix 64:ff9b::/96 — the last 32 bits are an IPv4
# address whose policy the tunnel syntax must not launder.
_NAT64_WKP = b"\x00\x64\xff\x9b" + b"\x00" * 8


def _embedded_ipv4(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | None:
    """The IPv4 address a v6 tunnel form embeds (mapped / 6to4 / Teredo /
    NAT64), if any — policy classifies the EMBEDDED address."""
    if ip.version == 4:
        return None
    assert isinstance(ip, ipaddress.IPv6Address)
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip.teredo is not None:
        return ip.teredo[1]
    if ip.packed[:12] == _NAT64_WKP:
        return ipaddress.IPv4Address(ip.packed[12:])
    return None


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """The ONE IP policy: globally-routable and not multicast. is_global is
    False for private / loopback / link-local / reserved / unspecified /
    CGNAT / documentation / benchmarking ranges — the whole refusal family
    in one stdlib predicate (truth table locked by the pure suite)."""
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        ip = embedded
    return ip.is_global and not ip.is_multicast


def check_url_policy(url: str) -> str:
    """The static gate (pure): scheme whitelist + host law + literal-IP
    classification. Returns the normalized host (lower, no trailing dot).
    Raises CaptureBlocked on refusal. Runs at asset birth (honest refusal
    at creation) and again per hop / per proxy connect at capture time."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise CaptureBlocked(f"scheme not allowed: {parsed.scheme or '(none)'}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise CaptureBlocked("no host")
    # web.py's hostname law stays the ONE seat for obviously-internal names;
    # fed the normalized host so trailing-dot / case spellings can't slip.
    if _host_blocked(f"//{host}"):
        raise CaptureBlocked(f"internal host: {host}")
    ip = _parse_ip_literal(host)
    if ip is not None and not _ip_allowed(ip):
        raise CaptureBlocked(f"internal address: {host}")
    return host


async def _resolve_verified_ips(host: str) -> list[str]:
    """DNS re-verification seam (network): resolve the host ourselves and
    refuse if ANY answer is non-global — a host resolving partly-private is
    an attack shape. Returns the verified IP literals for the caller to dial
    DIRECTLY (never re-resolving), closing the rebinding window."""
    literal = _parse_ip_literal(host)
    if literal is not None:
        return [str(literal)]
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        raise CaptureError(f"dns lookup failed: {host}") from e
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise CaptureError(f"dns lookup empty: {host}")
    for ip in ips:
        if not _ip_allowed(ip):
            raise CaptureBlocked(f"dns resolved to internal address: {host} → {ip}")
    return [str(ip) for ip in ips]


# ---------------------------------------------------------------------------
# HTML fetch (per-hop redirect policy + byte cap)
# ---------------------------------------------------------------------------

_MAX_REDIRECTS = 5


async def _fetch_html(url: str) -> tuple[str, str]:
    """GET the page HTML → (html, final_url). Redirects are followed
    MANUALLY so every hop re-passes the full policy (scheme / host / DNS)
    before a byte of the next hop is read — a public URL redirecting inward
    dies at the hop. ``trust_env=True`` is the runner's proxy discipline
    (web.py precedent)."""
    current = url
    async with httpx.AsyncClient(timeout=15.0, trust_env=True) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            check_url_policy(current)
            await _resolve_verified_ips(urlparse(current).hostname or "")
            try:
                async with client.stream("GET", current, headers=_HEADERS) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise CaptureError("redirect without location")
                        current = urljoin(current, location)
                        continue
                    if resp.status_code != 200:
                        raise CaptureError(f"http {resp.status_code}")
                    content_type = resp.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        raise CaptureError(f"not html: {content_type or '(unknown)'}")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes(65536):
                        total += len(chunk)
                        if total > settings.web_capture_html_max_bytes:
                            raise CaptureError("html over byte cap")
                        chunks.append(chunk)
                    encoding = resp.encoding or "utf-8"
                    return b"".join(chunks).decode(encoding, errors="replace"), str(resp.url)
            except httpx.HTTPError as e:
                raise CaptureError(f"fetch failed: {e}") from e
    raise CaptureError("too many redirects")


# ---------------------------------------------------------------------------
# Screenshot (headless Chrome behind an ephemeral policy proxy)
# ---------------------------------------------------------------------------

WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
# Dev-server HMR sockets never reach virtual-time quiescence (spike
# forensics) — Chrome caps its own page wait with --timeout, never
# --virtual-time-budget. The overall wall clock is ours (wait_for below).
_NAV_TIMEOUT_MS = 9000

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def resolve_chrome_path() -> str | None:
    """THE Chrome-path seat (D1: spike / render / worker never re-derive):
    explicit setting first, then platform candidates, then PATH lookup.
    None = no browser on this host — the caller degrades honestly."""
    override = settings.chrome_path.strip()
    if override:
        if Path(override).is_file():
            return override
        logger.warning("chrome_path_override_missing", path=override)
        return None
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


class _PolicyProxy:
    """An ephemeral loopback HTTP proxy that applies the capture policy to
    EVERY browser request — top-level navigation, redirect and sub-resource
    alike (the browser-level SSRF seat). CONNECT tunnels and plain-HTTP
    forwards both resolve + verify + dial the verified IP themselves.

    Caps: per-capture request count and relayed bytes; over-cap connections
    die, and Chrome degrades to whatever the page managed to load (the
    screenshot is best-effort by contract)."""

    _HEAD_CAP = 64 * 1024

    def __init__(self, *, max_requests: int, max_bytes: int) -> None:
        self._max_requests = max_requests
        self._max_bytes = max_bytes
        self._requests = 0
        self._bytes = 0
        self._server: asyncio.AbstractServer | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._requests += 1
        if self._requests > self._max_requests:
            writer.close()
            return
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            if len(head) > self._HEAD_CAP:
                writer.close()
                return
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = request_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return
            method, target = parts[0].upper(), parts[1]
            if method == "CONNECT":
                await self._tunnel(target, reader, writer)
            else:
                await self._forward(method, target, head, reader, writer)
        except (CaptureError, asyncio.IncompleteReadError, TimeoutError):
            writer.close()
        except Exception as e:  # noqa: BLE001 — a proxy death is a degrade
            logger.warning("web_capture_proxy_error", error=str(e))
            writer.close()

    async def _dial(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Policy + verified dial shared by tunnel and forward: resolve,
        verify, then dial the VERIFIED literal (never the hostname — the
        rebinding window stays closed)."""
        ips = await _resolve_verified_ips(host)
        return await asyncio.open_connection(ips[0], port)

    async def _tunnel(
        self,
        target: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        host, _, port_s = target.rpartition(":")
        host = host.strip("[]").lower().rstrip(".")
        try:
            port = int(port_s)
        except ValueError:
            raise CaptureError(f"bad CONNECT target: {target}")
        if _host_blocked(f"//{host}"):
            raise CaptureBlocked(f"internal host: {host}")
        upstream_reader, upstream_writer = await self._dial(host, port)
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        await self._relay_bidirectional(
            client_reader, client_writer, upstream_reader, upstream_writer
        )

    async def _forward(
        self,
        method: str,
        target: str,
        head: bytes,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        del client_reader  # a forward request carries no body we relay
        parsed = urlparse(target)
        if parsed.scheme.lower() != "http":
            raise CaptureBlocked(f"proxy scheme not allowed: {parsed.scheme}")
        host = (parsed.hostname or "").lower().rstrip(".")
        if _host_blocked(f"//{host}"):
            raise CaptureBlocked(f"internal host: {host}")
        port = parsed.port or 80
        upstream_reader, upstream_writer = await self._dial(host, port)
        try:
            # Re-issue in origin-form with a forced close — one request per
            # connection keeps the byte ledger exact.
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            lines = head.split(b"\r\n")
            lines[0] = f"{method} {path} HTTP/1.1".encode("latin-1")
            kept = [
                line
                for line in lines[1:]
                if line
                and not line.lower().startswith((b"proxy-", b"connection:"))
            ]
            upstream_writer.write(
                b"\r\n".join([lines[0], *kept, b"Connection: close", b"", b""])
            )
            await upstream_writer.drain()
            await self._pump(upstream_reader, client_writer)
        finally:
            upstream_writer.close()
            client_writer.close()

    async def _relay_bidirectional(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        """Pump both directions; when either ends (EOF or byte cap) the
        other is cancelled and both ends close."""
        up = asyncio.create_task(self._pump(client_reader, upstream_writer))
        down = asyncio.create_task(self._pump(upstream_reader, client_writer))
        done, pending = await asyncio.wait(
            {up, down}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            with contextlib.suppress(Exception):
                task.result()  # consume — reset peers are ordinary here
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        upstream_writer.close()
        client_writer.close()

    async def _pump(
        self, src: asyncio.StreamReader, dst: asyncio.StreamWriter
    ) -> None:
        """Copy until EOF or the byte cap; the ledger is per-capture."""
        while True:
            chunk = await src.read(65536)
            if not chunk:
                return
            self._bytes += len(chunk)
            if self._bytes > self._max_bytes:
                return
            dst.write(chunk)
            await dst.drain()


# ---------------------------------------------------------------------------
# Browser session (ADR-121 B1 — playwright drives system Chrome)
# ---------------------------------------------------------------------------
#
# The one-shot Chrome CLI (`--screenshot`) could not scroll, wait, or close
# pop-ups — canvas/JS-rendered heroes (linear.app 实证) captured as black
# rectangles. The session below ports the launch-film skill's four verified
# JS blocks near-verbatim (capture.mjs: settle / preload / consent / anchors
# / elements): close pop-ups → scroll-preload (lazy-load triggers) → fold +
# per-section viewport screenshots, each with its element inventory (the ui
# scene's camera-target data, B2). The policy trio is untouched: _PolicyProxy
# (browser-level SSRF), system Chrome via resolve_chrome_path, degrade-honest
# (a session failure = no shots, never an exception out of the visuals half).

# Sections after the fold (skill `--shots 6` 总量同: fold + 5). Per-shot
# element inventory cap — meta size stays bounded at the birthplace.
_SECTION_SHOT_MAX = 5
_ELEMENTS_PER_SHOT = 30
_ELEMENT_IMAGES_PER_SHOT = 2
_CAPTURE_DEVICE_SCALE = 2.0
# Scroll-preload step/rhythm and the page-height cap (skill values).
_PRELOAD_STEP_PX = 400
_PRELOAD_STEP_MS = 180
_PRELOAD_HEIGHT_CAP = 40000

# Sub-page discovery (ADR-121 B4; skill discoverLinks verbatim): same-host
# product pages only — the three gates are same-origin + BAD_LINK filter +
# cap. Never external sites, never recursive (the spawn seat marks children
# ``discovered_from``; their own captures never re-discover).
_DISCOVER_MAX = 3
_GOOD_LINK_RE = r"feature|product|how-it-works|how it works|solution|platform|pricing|price|plans?\b|about|tour|overview|why|use-?cases?|integrations?|功能|产品|產品|价格|價格|方案|关于|關於|機能|料金|製品|について|funktion|preise|fonctionnalit|tarif|caracter|precios|recursos"
_BAD_LINK_RE = r"log-?in|sign-?in|sign-?up|register|account|blog|news|press|changelog|release|updates?\b|events?\b|webinar|stories|customers?\b|career|jobs?\b|legal|privacy|terms|cookie|contact|support|help|docs?\b|status|download|faq|polic|imprint|impressum|sitemap|rss|\.(pdf|zip|png|jpe?g|mp4)$|登录|注册|博客|新闻|招聘|隐私|条款|帮助|ログイン|採用|ヘルプ"
_JS_DISCOVER = r"""([good, bad, n]) => {
    const G = new RegExp(good, 'i'), B = new RegExp(bad, 'i'), here = new URL(location.href);
    const locale = (here.pathname.match(/^\/([a-z]{2}(?:-[a-z]{2,4})?)(?:\/|$)/i) || [])[1]; // keep the locale prefix
    const seen = new Map();
    for (const a of document.querySelectorAll('a[href]')) {
        let u;
        try { u = new URL(a.getAttribute('href'), location.href); } catch { continue; }
        if (u.origin !== here.origin || !/^https?:$/.test(u.protocol)) continue;
        u.hash = ''; u.search = '';
        const p = u.pathname.replace(/\/+$/, '') || '/';
        if (p === (here.pathname.replace(/\/+$/, '') || '/') || p.split('/').length > 4) continue;
        if (locale && !p.toLowerCase().startsWith('/' + locale.toLowerCase())) continue;
        const label = ((a.innerText || a.getAttribute('aria-label') || '') + ' ' + p).replace(/\s+/g, ' ');
        if (B.test(label)) continue;
        const score = (G.test(label) ? 3 : 0) + (a.closest('header,nav') ? 1 : 0);
        if (score >= 3 && (!seen.has(p) || seen.get(p) < score)) seen.set(p, score);
    }
    return [...seen.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([p]) => here.origin + p);
}"""

# Cookie/consent dismissal (skill capture.mjs — the three regex families +
# known CMP selectors, reject-preferred: clicking "accept" is someone's
# consent decision, "reject" is the privacy-safe default).
_CONSENT_RE = r"cookie|consent|gdpr|privacy|tracking|隐私|隱私|クッキー|datenschutz|confidentialit|privacidad|privacidade|конфиденц|файлы cookie"
_REJECT_RE = r"^(decline( all)?|reject( all)?|deny( all)?|refuse( all)?|disagree|(use )?(only )?(strictly )?(necessary|essential)( cookies)?( only)?|continue without accepting|拒绝|不同意|仅必要|僅必要|拒否|すべて拒否|必要なもののみ|ablehnen|alle ablehnen|nur notwendige|rechazar( todo)?|refuser( tout)?|tout refuser|rifiuta|recusar|rejeitar|отклонить|отказаться)$"
_ACCEPT_RE = r"^(accept( all)?( cookies)?|allow( all)?( cookies)?|agree|i agree|got it|ok(ay)?|understood|同意|接受|全部接受|我知道了|知道了|同意する|すべて受け入れる|akzeptieren|alle akzeptieren|zustimmen|aceptar( todo)?|accepter( tout)?|tout accepter|accetta|aceitar|принять|согласен)$"
_KNOWN_CMP = (
    "#onetrust-reject-all-handler",
    "#CybotCookiebotDialogBodyButtonDecline",
    '[data-testid="uc-deny-all-button"]',
    "#didomi-notice-disagree-button",
    ".cky-btn-reject",
    ".fc-cta-do-not-consent",
    "#truste-consent-required",
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    '[data-testid="uc-accept-all-button"]',
    "#didomi-notice-agree-button",
    ".cky-btn-accept",
    ".fc-cta-consent",
    "#truste-consent-button",
)

# Other pop-ups: newsletter / app-install / region bars / chat widgets.
_CLOSE_RE = r"^(×|✕|✖|╳|close|close (dialog|modal|banner|popup)|dismiss|no,? thanks|not now|maybe later|skip|stay here|continue to site|关闭|不用了|以后再说|稍后再说|暂不|閉じる|今はしない|schließen|nein danke|cerrar|no, gracias|fermer|non merci|chiudi|fechar|закрыть)$"
_REGION_RE = r"you('| a)re (now )?(visiting|viewing|on)|did you mean|switch to|go to .* site|choose (your )?(country|region|language)|select (your )?(country|region|language)|looks like you('| a)re in|您正在访问|是否前往|切换到|选择(国家|地区|语言)|ご覧になっています|地域を選択|sie befinden sich|estás visitando|vous consultez"

# Regex-pick: find a reject/accept button living inside a consent box (the
# picked button is tagged so the click step can name it).
_JS_CONSENT_PICK = r"""([cs, rs, as]) => {
    const consent = new RegExp(cs, 'i'), rej = new RegExp(rs, 'i'), acc = new RegExp(as, 'i'),
        found = {reject: null, accept: null};
    for (const b of document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]')) {
        const r = b.getBoundingClientRect();
        if (r.width < 20 || r.height < 12 || getComputedStyle(b).visibility === 'hidden') continue;
        const label = (b.innerText || b.value || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
        if (!label || label.length > 40) continue;
        let c = b, ok = false;
        for (let i = 0; i < 8 && c; i++, c = c.parentElement) {
            const t = c.innerText || '';
            if (t.length < 4000 && consent.test(t)) { ok = true; break; }
        }
        if (!ok && !consent.test(label)) continue;
        const kind = rej.test(label) ? 'reject' : acc.test(label) ? 'accept' : null;
        if (kind && !found[kind]) {
            b.setAttribute('data-capture-consent', kind);
            found[kind] = true;
        }
    }
    return found.reject ? 'reject' : found.accept ? 'accept' : null;
}"""

# Fallback: hide the consent box outright (no click = no consent signal).
_JS_CONSENT_HIDE = r"""cs => {
    const consent = new RegExp(cs, 'i');
    let n = 0;
    for (const e of document.querySelectorAll('body *')) {
        const st = getComputedStyle(e);
        if (!/fixed|sticky/.test(st.position)) continue;
        const r = e.getBoundingClientRect(), t = e.innerText || '';
        if (e.closest('header,nav,footer') || /^(HEADER|NAV|FOOTER)$/.test(e.tagName)) continue;
        if (r.height > 0 && r.height < innerHeight * 0.6 && t.length < 1500 && consent.test(t) && /cookie|consent|クッキー|隐私|隱私/i.test(t)) {
            e.style.setProperty('display', 'none', 'important');
            n++;
        }
    }
    return n;
}"""

# Pop-up sweep: Escape already pressed by the caller; close-buttons clicked,
# region bars / modal backdrops / chat widgets hidden (never navigated).
_JS_OVERLAYS = r"""([cs, rs]) => {
    const close = new RegExp(cs, 'i'), region = new RegExp(rs, 'i'), W = innerWidth, H = innerHeight;
    let n = 0;
    const label = b => (b.innerText || b.getAttribute('aria-label') || b.getAttribute('title') || b.value || '').replace(/\s+/g, ' ').trim();
    for (const e of document.querySelectorAll('body *')) {
        const st = getComputedStyle(e);
        if (st.position !== 'fixed' && st.position !== 'sticky' && e.getAttribute('role') !== 'dialog' && e.getAttribute('aria-modal') !== 'true') continue;
        const r = e.getBoundingClientRect();
        if (r.width < 40 || r.height < 20 || st.display === 'none' || st.visibility === 'hidden') continue;
        const big = r.width * r.height > W * H * 0.15, bar = r.height < 140 && r.width > W * 0.6;
        const dialog = e.getAttribute('role') === 'dialog' || e.getAttribute('aria-modal') === 'true' || /modal|popup|pop-up|overlay|dialog|newsletter|lightbox|interstitial/i.test(String(e.className) + ' ' + e.id);
        if (!big && !bar && !dialog) continue;
        if (e.closest('header,nav') && !dialog) continue;
        const btn = [...e.querySelectorAll('button,a,[role=button],[aria-label],input[type=button]')].find(b => {
            const t = label(b);
            return t && t.length < 30 && close.test(t) && b.getBoundingClientRect().width > 0;
        });
        if (btn) { btn.click(); n++; continue; }
        if (bar && region.test((e.innerText || '').slice(0, 400))) {
            const hits = [e, ...e.querySelectorAll('*')].filter(d => {
                const q = d.getBoundingClientRect();
                return q.width > W * 0.6 && q.height > 0 && region.test((d.innerText || '').slice(0, 400));
            });
            const t = hits.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length)[0];
            if (t) { t.style.setProperty('display', 'none', 'important'); n++; continue; }
        }
        if (dialog && big) { e.style.setProperty('display', 'none', 'important'); n++; }
    }
    for (const e of document.querySelectorAll('body *')) {
        const st = getComputedStyle(e);
        if (st.position !== 'fixed' || st.display === 'none') continue;
        const r = e.getBoundingClientRect();
        if (!r.width || r.width * r.height > W * H * 0.2 || (r.right < W - 40 && r.bottom < H - 40)) continue;
        const id = [e.id, String(e.className), e.getAttribute('title'), e.getAttribute('aria-label'), e.tagName === 'IFRAME' ? e.src : '', (e.innerText || '').slice(0, 40)].join(' ');
        if (/intercom|drift|crisp|zendesk|zopim|hubspot|hs-|livechat|live chat|tawk|helpscout|freshchat|olark|tidio|chat-?widget|chatbot|launcher|book a demo|在线咨询|在线客服|客服/i.test(id)) {
            e.style.setProperty('display', 'none', 'important');
            n++;
        }
    }
    if (n) for (const el of [document.documentElement, document.body]) {
        el.style.setProperty('overflow', 'auto', 'important');
        el.style.setProperty('position', 'static', 'important');
    } // modals lock scrolling
    for (const e of document.querySelectorAll('body *')) {
        const st = getComputedStyle(e), r = e.getBoundingClientRect();
        if (st.position === 'fixed' && r.width >= W * 0.95 && r.height >= H * 0.95 && !(e.innerText || '').trim() && /rgba\(0, 0, 0, 0\.[2-9]/.test(st.backgroundColor)) {
            e.style.setProperty('display', 'none', 'important');
            n++;
        }
    }
    return n;
}"""

# Height of fixed/sticky bars at the top (sections scroll just under it).
_JS_TOPCOVER = r"""() => {
    let b = 0;
    for (const e of document.querySelectorAll('body *')) {
        const st = getComputedStyle(e);
        if (!/fixed|sticky/.test(st.position) || st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
        const r = e.getBoundingClientRect();
        if (r.top < 200 && r.bottom > 0 && r.height < 240 && r.width > innerWidth * 0.4) b = Math.max(b, r.bottom);
    }
    return Math.round(b);
}"""

# Section anchors: big visible headings with page-absolute y (chrome excluded).
_JS_ANCHORS = r"""() => {
    const body = parseFloat(getComputedStyle(document.body).fontSize) || 16, out = [];
    const inChrome = e => e.closest('header,nav,footer,[role=navigation],[role=banner],[role=contentinfo]') || (() => {
        for (let c = e; c && c !== document.body; c = c.parentElement) if (/fixed|sticky/.test(getComputedStyle(c).position)) return true;
        return false;
    })();
    for (const e of document.querySelectorAll('h1,h2,h3,div,p,span,strong,b,section>*:first-child')) {
        const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
        if (!own && !/^H[1-3]$/.test(e.tagName)) continue;
        const st = getComputedStyle(e), fs = parseFloat(st.fontSize), r = e.getBoundingClientRect();
        const big = fs >= Math.max(20, body * 1.5) || (/^H[12]$/.test(e.tagName) && fs >= body * 1.25);
        if (!big || r.width < 40 || r.height < 10 || st.visibility === 'hidden' || +st.opacity === 0 || inChrome(e)) continue;
        const text = (e.innerText ?? e.textContent ?? '').replace(/\s+/g, ' ').trim();
        if (!text || text.length > 140) continue;
        out.push({y: Math.round(r.top + scrollY), size: fs, text});
    }
    out.sort((a, b) => a.y - b.y);
    return out;
}"""

# Visible text, buttons and large images in the CURRENT viewport, boxes
# normalized to viewport dims (the ui scene's camera-target inventory).
_JS_ELEMENTS = r"""() => {
    const W = innerWidth, H = innerHeight, out = [], seen = new Set(),
        body = parseFloat(getComputedStyle(document.body).fontSize) || 16;
    const pinned = new Map(), inChrome = e => {
        if (e.closest('header,nav,aside,[role=navigation],[role=banner],[role=contentinfo],[role=complementary]')) return true;
        for (let c = e; c && c !== document.body; c = c.parentElement) {
            if (!pinned.has(c)) pinned.set(c, /fixed|sticky/.test(getComputedStyle(c).position) && c.getBoundingClientRect().height < H * 0.4);
            if (pinned.get(c)) return true;
        }
        return false;
    };
    const textOf = e => (e.innerText ?? e.textContent ?? '').replace(/\s+/g, ' ').trim();
    const clip = r => {
        const l = Math.max(0, r.left), t = Math.max(0, r.top), rr = Math.min(W, r.right), b = Math.min(H, r.bottom);
        return {left: l, top: t, width: rr - l, height: b - t};
    };
    const vis = (e, r) => {
        const st = getComputedStyle(e), c = clip(r);
        if (!(r.width > 4 && r.height > 4 && c.width > 0 && c.height > 0 && c.width * c.height >= r.width * r.height * 0.3 && st.visibility !== 'hidden' && +st.opacity > 0.05)) return false;
        return e.checkVisibility ? e.checkVisibility({opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true}) : true;
    };
    const partOf = (t, e, r) => {
        if (!t) return false;
        if (e.contains(t) || t.contains(e)) return true;
        const q = t.getBoundingClientRect();
        return q.left >= r.left - 8 && q.top >= r.top - 8 && q.right <= r.right + 8 && q.bottom <= r.bottom + 8;
    };
    const covered = (e, r) => {
        const c = clip(r), pts = [[.5, .5], [.2, .3], [.8, .3], [.2, .7], [.8, .7]];
        let hidden = 0;
        for (const [fx, fy] of pts) if (!partOf(document.elementFromPoint(c.left + c.width * fx, c.top + c.height * fy), e, r)) hidden++;
        return hidden >= 4;
    };
    const box = r => {
        const c = clip(r);
        return {
            x: +((c.left + c.width / 2) / W).toFixed(4),
            y: +((c.top + c.height / 2) / H).toFixed(4),
            w: +(c.width / W).toFixed(4),
            h: +(c.height / H).toFixed(4),
            css: {
                x: +(c.left + scrollX).toFixed(3),
                y: +(c.top + scrollY).toFixed(3),
                width: +c.width.toFixed(3),
                height: +c.height.toFixed(3)
            }
        };
    };
    const selectorOf = e => {
        const unique = selector => {
            try { return document.querySelectorAll(selector).length === 1 ? selector : null; } catch { return null; }
        };
        if (e.id) {
            const found = unique('#' + CSS.escape(e.id));
            if (found) return found;
        }
        for (const name of ['data-testid', 'data-test', 'name', 'aria-label']) {
            const value = e.getAttribute(name);
            if (value) {
                const found = unique(e.tagName.toLowerCase() + '[' + name + '=' + JSON.stringify(value) + ']');
                if (found) return found;
            }
        }
        const parts = [];
        let current = e;
        while (current && current !== document.body && parts.length < 6) {
            const tag = current.tagName.toLowerCase();
            const parent = current.parentElement;
            const siblings = parent ? [...parent.children].filter(item => item.tagName === current.tagName) : [];
            parts.unshift(tag + ':nth-of-type(' + (siblings.indexOf(current) + 1) + ')');
            const found = unique(parts.join(' > '));
            if (found) return found;
            current = parent;
        }
        return null;
    };
    const blockOf = n => {
        let e = n.parentElement;
        while (e && e !== document.body && getComputedStyle(e).display.startsWith('inline')) e = e.parentElement;
        return e;
    };
    for (const b of document.querySelectorAll('a,button,[role=button],[role=tab]')) {
        const r = b.getBoundingClientRect(), t = textOf(b) || (b.getAttribute('aria-label') || '').trim();
        if (!t || t.length > 60 || !vis(b, r) || r.height > 120) continue;
        out.push({kind: inChrome(b) ? 'pinned' : 'button', text: t, selector: selectorOf(b), main: !!b.closest('main'), control: b.matches('[role=tab],[aria-controls],[data-bs-toggle]'), ...box(r), ...(covered(b, r) ? {covered: true} : {})});
        seen.add(b);
    }
    // A control's stable content container survives the before/after switch
    // even when the previously controlled panel itself becomes hidden.
    let regionCount = 0;
    // Named visual containers are valid capture subjects even without tabs.
    // Keep real DOM geometry and a unique selector; do not infer a card from text.
    for (const region of document.querySelectorAll('main [aria-label],main [role=region],main article')) {
        if (regionCount >= 6) break;
        if (seen.has(region) || region.matches('a,button,input,select,textarea,[role=button],[role=tab]')) continue;
        const r = region.getBoundingClientRect(), selector = selectorOf(region);
        const label = region.getAttribute('aria-label') || '';
        const t = [label, textOf(region)].filter(Boolean).join(' — ');
        if (!t || !selector || !vis(region, r) || r.width < 120 || r.height < 80) continue;
        seen.add(region);
        out.push({kind: 'region', text: t, selector, main: true, ...box(r), ...(covered(region, r) ? {covered: true} : {})});
        regionCount++;
    }
    for (const control of document.querySelectorAll('[aria-controls],[data-bs-toggle],[role=tab]')) {
        if (regionCount >= 6) break;
        const controlledId = control.getAttribute('aria-controls') || (control.getAttribute('data-bs-target') || '').replace(/^#/, '');
        const controlled = controlledId ? document.getElementById(controlledId) : null;
        const tablist = control.closest('[role=tablist]');
        const region = (tablist && tablist.parentElement) || (controlled && controlled.parentElement) || control.parentElement;
        if (!region || seen.has(region)) continue;
        const r = region.getBoundingClientRect(), t = textOf(region);
        if (!t || !vis(region, r) || r.width < 40 || r.height < 20) continue;
        seen.add(region);
        out.push({kind: 'region', text: t, selector: selectorOf(region), main: !!region.closest('main'), ...box(r), ...(covered(region, r) ? {covered: true} : {})});
        regionCount++;
    }
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
        if (n.textContent.trim().length < 2) continue;
        const e = blockOf(n);
        if (!e || seen.has(e) || e.closest('a,button,[role=button],[role=tab]') && seen.has(e.closest('a,button,[role=button],[role=tab]'))) continue;
        seen.add(e);
        const r = e.getBoundingClientRect();
        if (!vis(e, r) || r.height > H * 0.8) continue;
        const t = textOf(e);
        if (!t || t.length > 220) continue;
        const fs = parseFloat(getComputedStyle(e).fontSize);
        // Real heading tags (or ARIA heading roles) earn the "heading" kind —
        // the camera's default picker prefers the section's subject copy over
        // controls; styled-div display copy still lands in the text tier.
        const heading = /^H[1-6]$/.test(e.tagName) || e.getAttribute('role') === 'heading';
        out.push({kind: inChrome(e) ? 'pinned' : heading ? 'heading' : 'text', text: t, size: Math.round(fs), selector: selectorOf(e), main: !!e.closest('main'), ...box(r), ...(covered(e, r) ? {covered: true} : {})});
    }
    for (const m of document.querySelectorAll('img,video,canvas,svg,picture')) {
        if (m.closest('svg') && m.tagName.toLowerCase() !== 'svg' || m.tagName === 'IMG' && m.closest('picture')) continue;
        const r = m.getBoundingClientRect();
        if (!vis(m, r) || r.width * r.height < W * H * 0.02) continue;
        out.push({kind: m.tagName === 'VIDEO' ? 'video' : 'image', text: m.getAttribute('alt') || m.getAttribute('aria-label') || '', selector: selectorOf(m), main: !!m.closest('main'), ...box(r), ...(covered(m, r) ? {covered: true} : {})});
    }
    return out.sort((a, b) => a.y - b.y || a.x - b.x);
}"""


_CAPTURE_ID = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
_CAPTURE_REGION_TEXT_CAP = 4000
_CAPTURE_MAX_ACTIONS = 8
_CAPTURE_MAX_WAIT_MS = 2000
_CAPTURE_TOTAL_WAIT_MS = 6000


class CaptureViewport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=1440, ge=640, le=1920)
    height: int = Field(default=900, ge=480, le=1200)


_CAPTURE_MAX_TARGETS = 8
_CAPTURE_MAX_OUTPUTS = 16
_CAPTURE_MAX_TARGET_MEMBERS = 32
_CAPTURE_MAX_VIEWS = 64
_CAPTURE_MAX_ISSUES = 64
_CAPTURE_ISSUE_ERROR_CAP = 300


class CaptureTarget(BaseModel):
    """A request-local element or bounded collection bound to real DOM evidence."""

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(pattern=_CAPTURE_ID)
    element_id: str | None = Field(default=None, pattern=_CAPTURE_ID)
    selector: str | None = Field(default=None, max_length=300)
    all: bool = False
    max_items: int = Field(default=_CAPTURE_MAX_TARGET_MEMBERS, ge=1, le=_CAPTURE_MAX_TARGET_MEMBERS)

    @field_validator("selector")
    @classmethod
    def _bounded_css(cls, value: str | None) -> str | None:
        if value is None:
            return None
        selector = value.strip()
        if not selector or any(token in selector for token in ("{", "}", ";", "\\")):
            raise ValueError("capture selectors are one bounded CSS selector, never script")
        if "javascript:" in selector.lower() or "expression(" in selector.lower():
            raise ValueError("capture selectors cannot contain executable text")
        return selector

    @model_validator(mode="after")
    def _identity(self) -> "CaptureTarget":
        if self.element_id is None and self.selector is None:
            raise ValueError("a capture target needs a reconnaissance element or CSS selector")
        if not self.all and self.max_items != _CAPTURE_MAX_TARGET_MEMBERS:
            raise ValueError("max_items is only meaningful for a collection target")
        return self


class CaptureAction(BaseModel):
    """One fixed server-implemented action; all fields are data, never code."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["click", "fill", "hover", "scroll", "wait"]
    target_id: str | None = Field(default=None, pattern=_CAPTURE_ID)
    value: str | None = Field(default=None, max_length=240)
    milliseconds: int | None = Field(default=None, ge=50, le=_CAPTURE_MAX_WAIT_MS)
    y: int | None = Field(default=None, ge=0, le=30000)

    @model_validator(mode="after")
    def _shape(self) -> "CaptureAction":
        if self.kind in {"click", "hover"}:
            if self.target_id is None or any(
                value is not None for value in (self.value, self.milliseconds, self.y)
            ):
                raise ValueError(f"{self.kind} takes only target_id")
        elif self.kind == "fill":
            if self.target_id is None or self.value is None or self.milliseconds is not None or self.y is not None:
                raise ValueError("fill takes only target_id and a bounded public-demo value")
        elif self.kind == "scroll":
            if (self.target_id is None) == (self.y is None) or self.value is not None or self.milliseconds is not None:
                raise ValueError("scroll takes only target_id or y; put milliseconds in a separate wait action")
        elif self.kind == "wait":
            if self.milliseconds is None or any(
                value is not None for value in (self.target_id, self.value, self.y)
            ):
                raise ValueError("wait takes only a bounded milliseconds value")
        return self


class CaptureState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: str = Field(pattern=_CAPTURE_ID)
    actions: list[CaptureAction] = Field(default_factory=list, max_length=_CAPTURE_MAX_ACTIONS)

    @model_validator(mode="before")
    @classmethod
    def _empty_actions_are_absent(cls, data):
        if isinstance(data, dict) and data.get("actions") in (None, ""):
            return {**data, "actions": []}
        return data

    @model_validator(mode="after")
    def _bounded_wait(self) -> "CaptureState":
        total = sum(action.milliseconds or 0 for action in self.actions if action.kind == "wait")
        if total > _CAPTURE_TOTAL_WAIT_MS:
            raise ValueError("a state's explicit waits may not exceed 6000ms")
        return self


class CaptureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(pattern=_CAPTURE_ID)
    state_id: str = Field(pattern=_CAPTURE_ID)
    kind: Literal["page", "elements", "blank_plate"]
    target_ids: list[str] = Field(default_factory=list, max_length=_CAPTURE_MAX_TARGETS)
    coverage: Literal["viewport", "full"] = "viewport"
    scale: Literal[2, 4] = 2
    transparent: bool = False

    @model_validator(mode="after")
    def _shape(self) -> "CaptureOutput":
        if self.kind == "page" and self.target_ids:
            raise ValueError("page outputs do not accept target_ids")
        if self.kind == "elements" and len(self.target_ids) != 1:
            raise ValueError("elements outputs name exactly one target")
        if self.kind == "blank_plate" and not self.target_ids:
            raise ValueError("blank_plate outputs name one or more targets")
        if self.kind != "elements" and self.transparent:
            raise ValueError("transparent only applies to elements outputs")
        return self


class CaptureRequest(BaseModel):
    """The only model-facing final webpage capture request."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_snapshot_id: UUID
    source_snapshot_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    route: str = "/"
    viewport: CaptureViewport = CaptureViewport()
    states: list[CaptureState] = Field(min_length=1, max_length=4)
    targets: list[CaptureTarget] = Field(default_factory=list, max_length=_CAPTURE_MAX_TARGETS)
    outputs: list[CaptureOutput] = Field(min_length=1, max_length=_CAPTURE_MAX_OUTPUTS)

    @model_validator(mode="after")
    def _references(self) -> "CaptureRequest":
        states = _unique_by_id(self.states, "state_id", "state")
        targets = _unique_by_id(self.targets, "target_id", "target")
        _unique_by_id(self.outputs, "output_id", "output")
        if sum(target.max_items if target.all else 1 for target in self.targets) > _CAPTURE_MAX_TARGET_MEMBERS:
            raise ValueError("capture targets exceed the 32-member request budget")
        for state in self.states:
            for action in state.actions:
                if action.target_id is not None:
                    target = targets.get(action.target_id)
                    if target is None:
                        raise ValueError(f"action names unknown target {action.target_id!r}")
                    if target.all:
                        raise ValueError("click/fill/hover/scroll actions require a single-element target")
        view_count = len({(output.state_id, output.scale) for output in self.outputs})
        for output in self.outputs:
            if output.state_id not in states:
                raise ValueError(f"output {output.output_id!r} names an unknown state")
            if any(target_id not in targets for target_id in output.target_ids):
                raise ValueError(f"output {output.output_id!r} names an unknown target")
            view_count += (
                targets[output.target_ids[0]].max_items
                if output.kind == "elements" and targets[output.target_ids[0]].all
                else 1
            )
        if view_count > _CAPTURE_MAX_VIEWS:
            raise ValueError("capture outputs exceed the 64-view request budget")
        return self


class CaptureArtifact(BaseModel):
    """Internal worker/provenance structure; never exposed as model input."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(pattern=_CAPTURE_ID)
    state_id: str = Field(pattern=_CAPTURE_ID)
    role: Literal["view", "full", "cutout", "blank_plate", "hero"]
    target_id: str | None = Field(default=None, pattern=_CAPTURE_ID)
    target_ids: list[str] = Field(default_factory=list, max_length=_CAPTURE_MAX_TARGETS)
    paired_view_id: str | None = Field(default=None, pattern=_CAPTURE_ID)
    required: bool = True
    output_id: str | None = Field(default=None, pattern=_CAPTURE_ID)
    scale: Literal[2, 4] | None = None
    coverage: Literal["viewport", "full"] = "viewport"
    transparent: bool = True

    @property
    def target_names(self) -> list[str]:
        return list(dict.fromkeys([
            *([self.target_id] if self.target_id is not None else []), *self.target_ids,
        ]))

    @model_validator(mode="after")
    def _shape(self) -> "CaptureArtifact":
        if self.role in {"cutout", "blank_plate"} and (not self.target_names or self.paired_view_id is None):
            raise ValueError(f"{self.role} needs targets and its populated view")
        if self.role == "cutout" and len(self.target_names) != 1:
            raise ValueError("an internal cutout names exactly one target")
        if self.role in {"full", "hero"} and self.paired_view_id is not None:
            raise ValueError(f"{self.role} does not take a paired view")
        return self


class CapturePlan(BaseModel):
    """Bounded internal execution and immutable asset provenance."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_snapshot_id: UUID
    source_snapshot_digest: str | None = Field(default=None, min_length=64, max_length=64)
    route: str = "/"
    viewport: CaptureViewport = CaptureViewport()
    states: list[CaptureState] = Field(min_length=1, max_length=4)
    targets: list[CaptureTarget] = Field(default_factory=list, max_length=_CAPTURE_MAX_TARGETS)
    artifacts: list[CaptureArtifact] = Field(min_length=1, max_length=_CAPTURE_MAX_VIEWS)

    @model_validator(mode="after")
    def _references(self) -> "CapturePlan":
        states = _unique_by_id(self.states, "state_id", "state")
        targets = _unique_by_id(self.targets, "target_id", "target")
        artifacts = _unique_by_id(self.artifacts, "artifact_id", "artifact")
        for state in self.states:
            for action in state.actions:
                if action.target_id is not None:
                    target = targets.get(action.target_id)
                    if target is None:
                        raise ValueError(f"action names unknown target {action.target_id!r}")
                    if target.all:
                        raise ValueError("capture actions cannot address a collection")
        for artifact in self.artifacts:
            if artifact.state_id not in states:
                raise ValueError(f"artifact {artifact.artifact_id!r} names an unknown state")
            if any(target_id not in targets for target_id in artifact.target_names):
                raise ValueError(f"artifact {artifact.artifact_id!r} names an unknown target")
            if artifact.paired_view_id is not None:
                paired = artifacts.get(artifact.paired_view_id)
                if paired is None or paired.role not in {"view", "hero"}:
                    raise ValueError(f"artifact {artifact.artifact_id!r} needs an existing populated pair")
                if artifact.role in {"cutout", "blank_plate"} and paired.state_id != artifact.state_id:
                    raise ValueError("blank_plate/cutout and their populated view must share a state")
                if paired.scale != artifact.scale:
                    raise ValueError("paired capture artifacts must share a scale")
                if artifact.role == "view" and paired.state_id == artifact.state_id:
                    raise ValueError("a before/after view pair must name different states")
        return self

    @property
    def capture_url(self) -> str:
        return capture_plan_url(self)


def _unique_by_id(items: list[Any], field_name: str, label: str) -> dict[str, Any]:
    result = {str(getattr(item, field_name)): item for item in items}
    if len(result) != len(items):
        raise ValueError(f"duplicate capture {label} id")
    return result


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.hostname.lower() if parsed.hostname else None, parsed.port


def capture_plan_url(plan: CapturePlan) -> str:
    """Resolve the planned route and refuse a cross-origin route before I/O."""
    target = urljoin(plan.source_url, plan.route)
    if _origin(target) != _origin(plan.source_url) or urlparse(target).username or urlparse(target).password:
        raise CaptureBlocked("CapturePlan routes must stay on the source origin without credentials")
    check_url_policy(target)
    return target


def capture_plan_digest(plan: CapturePlan) -> str:
    import json

    payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bind_capture_plan(
    plan: CapturePlan,
    *,
    snapshots: list[dict[str, Any]],
) -> CapturePlan:
    """Bind request-local element ids to the exact frozen reconnaissance."""
    source = next((item for item in snapshots if str(item.get("id")) == str(plan.source_snapshot_id)), None)
    if source is None or source.get("kind") != "web":
        raise ValueError("CaptureRequest source_snapshot_id is not a bound reconnaissance snapshot")
    meta = source.get("meta") or {}
    canonical_url = str(meta.get("canonical_url") or "")
    if plan.source_url != canonical_url:
        raise ValueError("CaptureRequest source_url must exactly match its source snapshot")
    known: dict[str, list[str]] = {}
    for view in meta.get("views") or []:
        for element in view.get("elements") or []:
            element_id = str(element.get("id") or "")
            selector = element.get("selector")
            if element_id and isinstance(selector, str) and selector:
                known.setdefault(element_id, []).append(selector)
    targets: list[CaptureTarget] = []
    for target in plan.targets:
        if target.element_id is not None:
            selectors = known.get(target.element_id) or []
            if not selectors:
                present = any(element.get("id") == target.element_id
                              for view in meta.get("views") or [] for element in view.get("elements") or [])
                if present:
                    raise ValueError(f"target {target.target_id!r} element {target.element_id!r} is captured but lacks a DOM selector for recapture")
                raise ValueError(f"target {target.target_id!r} names an uncaptured element")
            if len(set(selectors)) != 1:
                raise ValueError(f"target {target.target_id!r} is ambiguous across captured views")
            target = target.model_copy(update={"selector": selectors[0]})
        targets.append(target)
    bound = plan.model_copy(update={
        "source_snapshot_digest": str(source.get("digest") or ""),
        "targets": targets,
    })
    capture_plan_url(bound)
    _validate_capture_state_pairs(bound)
    return bound


def compile_capture_request(
    request: CaptureRequest,
    *,
    snapshots: list[dict[str, Any]],
) -> CapturePlan:
    """Mechanically add populated baselines, scales and same-state lineage."""
    source = next((item for item in snapshots if str(item.get("id")) == str(request.source_snapshot_id)), None)
    if source is None:
        raise ValueError("CaptureRequest source snapshot is unavailable")
    if request.source_snapshot_digest is not None and request.source_snapshot_digest != source.get("digest"):
        raise ValueError("CaptureRequest source_snapshot_digest does not match the frozen source")
    state_indexes = {state.state_id: index for index, state in enumerate(request.states)}
    baselines = {
        key: f"baseline-{state_indexes[key[0]]}-x{key[1]}"
        for key in dict.fromkeys((output.state_id, output.scale) for output in request.outputs)
    }
    artifacts = [
        CaptureArtifact(
            artifact_id=artifact_id, state_id=state_id, role="view", required=False,
            scale=scale, output_id=None,
        )
        for (state_id, scale), artifact_id in baselines.items()
    ]
    for output in request.outputs:
        paired = baselines[(output.state_id, output.scale)]
        if output.kind == "page":
            role = "full" if output.coverage == "full" else "view"
            target_id = None
            target_ids: list[str] = []
            paired_view_id = None
        elif output.kind == "elements":
            role = "cutout"
            target_id = output.target_ids[0]
            target_ids = []
            paired_view_id = paired
        else:
            role = "blank_plate"
            target_id = output.target_ids[0] if len(output.target_ids) == 1 else None
            target_ids = output.target_ids
            paired_view_id = paired
        artifacts.append(CaptureArtifact(
            artifact_id=output.output_id, output_id=output.output_id,
            state_id=output.state_id, role=role, target_id=target_id,
            target_ids=target_ids, paired_view_id=paired_view_id, required=False,
            scale=output.scale, coverage=output.coverage, transparent=output.transparent,
        ))
    plan = CapturePlan(
        source_url=request.source_url,
        source_snapshot_id=request.source_snapshot_id,
        source_snapshot_digest=request.source_snapshot_digest,
        route=request.route, viewport=request.viewport, states=request.states,
        targets=request.targets, artifacts=artifacts,
    )
    return bind_capture_plan(plan, snapshots=snapshots)


def _validate_capture_state_pairs(plan: CapturePlan) -> None:
    """Static plates/cutouts need no interaction; before/after views do."""
    states = {state.state_id: state for state in plan.states}
    artifacts = {artifact.artifact_id: artifact for artifact in plan.artifacts}
    for artifact in plan.artifacts:
        if artifact.role != "view" or artifact.paired_view_id is None:
            continue
        paired = artifacts[artifact.paired_view_id]
        before = states[paired.state_id].actions
        after = states[artifact.state_id].actions
        if len(after) <= len(before) or after[:len(before)] != before:
            raise ValueError("a before/after pair must retain the shared scroll/layout prefix")
        delta = after[len(before):]
        changes = [action for action in delta if action.kind in {"click", "fill", "hover"}]
        if len(changes) != 1 or any(action.kind not in {"click", "fill", "hover", "wait"} for action in delta):
            raise ValueError("a before/after pair needs exactly one real state action and bounded waits")


@dataclass
class PageCapture:
    """A settled full-page PNG and its CSS-page dimensions."""

    png: bytes
    css_width: int
    css_height: int
    device_scale_factor: float


@dataclass
class ShotCapture:
    """One captured view of the page: the fold (index 0) or a section stop.
    ``elements`` = the viewport-relative inventory at this stop (element ids
    stamped capture-side: ``s<shot>e<j>``)."""

    y: int
    heading: str
    png: bytes
    elements: list[dict] = field(default_factory=list)
    device_scale_factor: float = 1.0
    view_id: str | None = None
    state_id: str | None = None
    output_id: str | None = None
    artifact_role: str | None = None
    paired_view_id: str | None = None
    target_id: str | None = None
    target_ids: list[str] = field(default_factory=list)
    target_element_id: str | None = None
    member_id: str | None = None
    transparent: bool | None = None
    route: str | None = None
    actions: list[dict] = field(default_factory=list)
    page_height: int | None = None
    region_text: str | None = None
    region_text_truncated: bool | None = None
    region_visually_truncated: bool | None = None


@dataclass
class BrowserCapture:
    """The enhanced products of one settled browser session."""

    research: WebPageResearch
    shots: list[ShotCapture]
    page: PageCapture | None
    element_images: dict[str, bytes]
    discovered: list[str]


def _stamp_elements(
    raw: list[dict], shot_idx: int, *, id_prefix: str | None = None
) -> list[dict]:
    """Raw evaluate output → the meta shape: ids assigned, text capped, the
    list truncated (meta size is bounded at the birthplace)."""
    out: list[dict] = []
    # Repeated pinned navigation must not consume the entire bounded inventory
    # while the actual section's controls are dropped below the cap.
    ordered = sorted(raw, key=lambda element: (
        not (element.get("kind") == "region" or element.get("control")),
        not element.get("main"), element.get("kind") == "pinned",
    ))
    for j, e in enumerate(ordered[:_ELEMENTS_PER_SHOT]):
        item = {
            "id": id_prefix + f"e{j}" if id_prefix is not None else f"s{shot_idx}e{j}",
            "kind": str(e.get("kind") or "text"),
            "text": str(e.get("text") or "")[:90],
            "x": float(e.get("x") or 0),
            "y": float(e.get("y") or 0),
            "w": float(e.get("w") or 0),
            "h": float(e.get("h") or 0),
        }
        selector = e.get("selector")
        if isinstance(selector, str) and selector:
            item["selector"] = selector[:300]
        if e.get("covered"):
            item["covered"] = True
        css = e.get("css")
        if isinstance(css, dict) and all(
            isinstance(css.get(key), (int, float)) for key in ("x", "y", "width", "height")
        ):
            item["css_box"] = {
                key: round(float(css[key]), 3) for key in ("x", "y", "width", "height")
            }
        out.append(item)
    return out


def css_pixel_box(css_box: dict[str, float], device_scale_factor: float) -> dict[str, float]:
    """Map an absolute CSS-page rectangle into full-page image pixels."""
    return {
        key: round(float(css_box[key]) * device_scale_factor, 3)
        for key in ("x", "y", "width", "height")
    }


async def _capture_element_images(page: Any, elements: list[dict]) -> dict[str, bytes]:
    """Capture only the dominant camera candidates, using their absolute
    CSS-page boxes so the same crop is addressable in the full-page image."""
    candidates: list[dict] = []
    for kind in ("heading", "video", "image", "text", "button"):
        pool = [
            element for element in elements
            if element.get("kind") == kind
            and not element.get("covered")
            and isinstance(element.get("css_box"), dict)
            and float(element["css_box"].get("width") or 0) >= 8
            and float(element["css_box"].get("height") or 0) >= 8
        ]
        if pool:
            candidates.append(max(
                pool,
                key=lambda element: float(element["css_box"]["width"])
                * float(element["css_box"]["height"]),
            ))
        if len(candidates) >= _ELEMENT_IMAGES_PER_SHOT:
            break
    images: dict[str, bytes] = {}
    for element in candidates:
        try:
            images[str(element["id"])] = await page.screenshot(
                type="png",
                clip=element["css_box"],
                full_page=True,
                animations="disabled",
                caret="hide",
                scale="device",
                timeout=30000,
            )
        except Exception as exc:  # one crop never discards the settled page
            logger.warning(
                "web_capture_element_failed", element=element.get("id"), error=str(exc)
            )
    return images


def _choose_stops(anchors: list[dict], page_height: int) -> list[tuple[int, str]]:
    """fold + one shot per section, ≥ half a viewport apart (skill
    capture.mjs's pick law); anchor-poor pages fall back to even steps."""
    vh = WINDOW_HEIGHT
    picks: list[tuple[int, str]] = [(0, "(top)")]
    for a in anchors:
        if a["y"] - picks[-1][0] >= vh * 0.5 and a["y"] < page_height - 200:
            picks.append((int(a["y"]), str(a["text"])))
    if len(picks) < 3:
        y = vh * 0.9
        while y < page_height - vh * 0.3 and len(picks) < _SECTION_SHOT_MAX + 1:
            if all(abs(p[0] - y) > vh * 0.4 for p in picks):
                picks.append((round(y), "(step)"))
            y += vh * 0.9
    picks.sort(key=lambda p: p[0])
    max_shots = _SECTION_SHOT_MAX + 1
    if len(picks) <= max_shots:
        return picks
    # Evenly sample the over-long pick list down to the cap (skill same law).
    return [picks[0]] + [
        picks[1 + round(i * (len(picks) - 2) / max(1, max_shots - 2))]
        for i in range(max_shots - 1)
    ]


async def _settle(page: Any) -> None:
    """networkidle + a beat (skill settle); dev-server HMR sockets never
    reach quiescence, so the wait is capped and its failure swallowed."""
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(600)


async def _dismiss_consent(page: Any) -> str | None:
    """Cookie/consent dismissal (skill port): known CMP selectors first
    (reject-preferred), then a regex pick inside a consent box, then hiding
    the box. Returns what happened, None = nothing found."""
    for frame in page.frames:
        for sel in _KNOWN_CMP:
            with contextlib.suppress(Exception):
                el = await frame.query_selector(sel)
                if el is None or not await el.is_visible():
                    continue
                with contextlib.suppress(Exception):
                    await el.click(timeout=3000)
                await page.wait_for_timeout(600)
                accepted = (
                    "accept" in sel or "agree" in sel
                    or sel.endswith("consent-button") or sel.endswith("fc-cta-consent")
                )
                return "accepted" if accepted else "declined"
    for frame in page.frames:
        with contextlib.suppress(Exception):
            pick = await frame.evaluate(
                _JS_CONSENT_PICK, [_CONSENT_RE, _REJECT_RE, _ACCEPT_RE]
            )
            if pick:
                with contextlib.suppress(Exception):
                    await frame.click(f'[data-capture-consent="{pick}"]', timeout=3000)
                await page.wait_for_timeout(600)
                return "declined" if pick == "reject" else "accepted"
    with contextlib.suppress(Exception):
        hidden = await page.evaluate(_JS_CONSENT_HIDE, _CONSENT_RE)
        if hidden:
            return "hidden"
    return None


async def _dismiss_overlays(page: Any) -> int:
    """Newsletter / region-bar / chat-widget sweep (skill port); also runs
    between shots — timed pop-ups appear on scroll."""
    with contextlib.suppress(Exception):
        await page.keyboard.press("Escape")
    try:
        n = await page.evaluate(_JS_OVERLAYS, [_CLOSE_RE, _REGION_RE])
    except Exception:  # noqa: BLE001 — a sweep failure never kills a capture
        return 0
    if n:
        await page.wait_for_timeout(500)
    return int(n or 0)


async def _preload(page: Any) -> int:
    """Scroll through once to trigger lazy loading (skill port), wait out
    straggler images, return to the top. Returns the final page height."""
    height = await page.evaluate("() => document.documentElement.scrollHeight")
    y = 0
    while y < height and y < _PRELOAD_HEIGHT_CAP:
        await page.evaluate("(y) => window.scrollTo(0, y)", y)
        await page.wait_for_timeout(_PRELOAD_STEP_MS)
        height = await page.evaluate("() => document.documentElement.scrollHeight")
        y += _PRELOAD_STEP_PX
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=8000)
    with contextlib.suppress(Exception):
        await page.evaluate(
            "() => Promise.race([Promise.all([...document.images]"
            ".filter(i => !i.complete).map(i => new Promise(r => {"
            " i.onload = i.onerror = r; }))),"
            " new Promise(r => setTimeout(r, 5000))])"
        )
    with contextlib.suppress(Exception):
        await page.evaluate(
            "() => Promise.race([document.fonts ? document.fonts.ready : Promise.resolve(),"
            " new Promise(r => setTimeout(r, 5000))])"
        )
    await page.evaluate("() => window.scrollTo(0, 0)")
    await page.wait_for_timeout(400)
    return await page.evaluate("() => document.documentElement.scrollHeight")


async def _capture_visuals_with_policy(
    url: str, chrome: str
) -> BrowserCapture:
    """Capture settled DOM copy, 2× page/view images and camera candidates
    behind the policy proxy, in a throwaway credential-free context."""
    proxy = _PolicyProxy(
        max_requests=settings.web_capture_max_requests,
        max_bytes=settings.web_capture_max_bytes,
    )
    await proxy.start()
    try:
        # Deferred import: a host without playwright degrades the visuals
        # half honestly (same law as a missing Chrome).
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            args = ["--disable-gpu", "--hide-scrollbars", "--mute-audio"]
            if settings.chrome_no_sandbox:
                args.append("--no-sandbox")
            browser = await pw.chromium.launch(
                executable_path=chrome,
                headless=True,
                args=args,
                proxy={"server": f"http://127.0.0.1:{proxy.port}"},
            )
            try:
                page = await browser.new_page(
                    viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT},
                    device_scale_factor=_CAPTURE_DEVICE_SCALE,
                )
                # Navigation waits only for the EARLY commit signal, never
                # `load`: one stalled sub-resource (a font / analytics chunk
                # on a slow path) blocks the `load` event and burns the whole
                # budget without a single pixel painted (the 2026-10-18
                # snappify incident — text fetched fine, zero page views).
                # Settling is the ladder's job below: best-effort networkidle
                # (suppressed) + fixed beats + scroll preloading.
                await page.goto(
                    url, wait_until="commit", timeout=_NAV_TIMEOUT_MS
                )
                await _settle(page)
                consent = await _dismiss_consent(page)
                overlays = await _dismiss_overlays(page)
                page_height = await _preload(page)
                # Grounding follows the DOM after client rendering and lazy
                # loading, not the earlier server-HTML response.
                rendered_html = await page.content()
                body_text = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
                research = extract_rendered_research(rendered_html, page.url, body_text)
                page_capture: PageCapture | None = None
                try:
                    full_png = await page.screenshot(
                        type="png",
                        full_page=True,
                        animations="disabled",
                        caret="hide",
                        scale="device",
                        timeout=60000,
                    )
                    css_size = await page.evaluate(
                        "() => ({width: document.documentElement.scrollWidth,"
                        " height: document.documentElement.scrollHeight})"
                    )
                    page_capture = PageCapture(
                        png=full_png,
                        css_width=int(css_size["width"]),
                        css_height=int(css_size["height"]),
                        device_scale_factor=_CAPTURE_DEVICE_SCALE,
                    )
                except Exception as exc:  # viewport shots still carry the shot
                    logger.warning("web_capture_full_page_failed", url=url, error=str(exc))
                anchors: list[dict] = []
                with contextlib.suppress(Exception):
                    anchors = await page.evaluate(_JS_ANCHORS)
                stops = _choose_stops(anchors, page_height)
                shots: list[ShotCapture] = []
                element_images: dict[str, bytes] = {}
                for i, (anchor_y, heading) in enumerate(stops):
                    if anchor_y == 0:
                        y = 0
                        await page.evaluate("(y) => window.scrollTo(0, y)", 0)
                        await page.wait_for_timeout(300)
                    else:
                        # Re-measure the pinned bar at the stop — it can
                        # appear/shrink with scroll (skill same law).
                        top_cover = await page.evaluate(_JS_TOPCOVER)
                        y = max(0, anchor_y - 110 - int(top_cover or 0))
                        await page.evaluate("(y) => window.scrollTo(0, y)", y)
                        await page.wait_for_timeout(1000)
                    await _dismiss_overlays(page)  # timed pop-ups
                    png = await page.screenshot(
                        type="png", animations="disabled", caret="hide",
                        timeout=60000,
                    )
                    elements: list[dict] = []
                    with contextlib.suppress(Exception):
                        elements = _stamp_elements(
                            await page.evaluate(_JS_ELEMENTS), i
                        )
                    element_images.update(await _capture_element_images(page, elements))
                    shots.append(
                        ShotCapture(
                            y=y,
                            heading=heading,
                            png=png,
                            elements=elements,
                            device_scale_factor=_CAPTURE_DEVICE_SCALE,
                        )
                    )
                logger.info(
                    "web_capture_visuals",
                    url=url,
                    shots=len(shots),
                    consent=consent,
                    overlays=overlays,
                )
                # B4 子页发现: same session, the page fully settled — one
                # evaluate, capped at the source (禁递归 is the spawn seat's
                # law, not the tool's).
                discovered: list[str] = []
                with contextlib.suppress(Exception):
                    discovered = await page.evaluate(
                        _JS_DISCOVER, [_GOOD_LINK_RE, _BAD_LINK_RE, _DISCOVER_MAX]
                    )
                if discovered:
                    logger.info("web_capture_discovered", url=url, pages=discovered)
                return BrowserCapture(
                    research=research,
                    shots=shots,
                    page=page_capture,
                    element_images=element_images,
                    discovered=discovered,
                )
            finally:
                await browser.close()
    finally:
        await proxy.stop()


# ---------------------------------------------------------------------------
# Final, shot-directed capture
# ---------------------------------------------------------------------------


_JS_CAPTURE_TARGET = r"""(el) => {
    const r = el.getBoundingClientRect();
    const left = Math.max(0, r.left), top = Math.max(0, r.top);
    const right = Math.min(innerWidth, r.right), bottom = Math.min(innerHeight, r.bottom);
    const visible = {
        x: left + scrollX, y: top + scrollY,
        width: Math.max(0, right - left), height: Math.max(0, bottom - top)
    };
    const full = {
        x: r.left + scrollX, y: r.top + scrollY,
        width: Math.max(0, r.width), height: Math.max(0, r.height)
    };
    // A visual subject includes visible overflowing descendants (for example
    // a toast belonging to a card), never just the target's own border box.
    let subjectLeft = full.x, subjectTop = full.y;
    let subjectRight = full.x + full.width, subjectBottom = full.y + full.height;
    for (const child of el.querySelectorAll('*')) {
        const cs = getComputedStyle(child), cr = child.getBoundingClientRect();
        if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity <= 0.05) continue;
        if (child.checkVisibility && !child.checkVisibility({opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true})) continue;
        if (!(cr.width > 0 && cr.height > 0)) continue;
        if (cr.right <= r.left || cr.left >= r.right || cr.bottom <= r.top || cr.top >= r.bottom) continue;
        subjectLeft = Math.min(subjectLeft, cr.left + scrollX);
        subjectTop = Math.min(subjectTop, cr.top + scrollY);
        subjectRight = Math.max(subjectRight, cr.right + scrollX);
        subjectBottom = Math.max(subjectBottom, cr.bottom + scrollY);
    }
    const subject = {
        x: subjectLeft, y: subjectTop,
        width: Math.max(0, subjectRight - subjectLeft),
        height: Math.max(0, subjectBottom - subjectTop)
    };
    const subjectVisible = {
        x: Math.max(subject.x, scrollX), y: Math.max(subject.y, scrollY),
        width: Math.max(0, Math.min(subject.x + subject.width, scrollX + innerWidth) - Math.max(subject.x, scrollX)),
        height: Math.max(0, Math.min(subject.y + subject.height, scrollY + innerHeight) - Math.max(subject.y, scrollY))
    };
    const text = (el.innerText ?? el.textContent ?? '').replace(/\s+/g, ' ').trim();
    const style = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || '';
    const kind = /^h[1-6]$/.test(tag) || role === 'heading' ? 'heading'
        : /^(button|input|textarea|select)$/.test(tag) || /^(button|tab)$/.test(role) ? 'button'
        : /^(img|video|canvas|svg|picture)$/.test(tag) ? 'image' : 'text';
    const centerHit = visible.width > 0 && visible.height > 0
        ? document.elementFromPoint(left + visible.width / 2, top + visible.height / 2)
        : null;
    return {
        text, kind, full, visible, subject, subject_visible: subjectVisible,
        viewport: {width: innerWidth, height: innerHeight},
        page: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
        scroll_x: scrollX,
        scroll_y: scrollY,
        covered: !!(centerHit && centerHit !== el && !el.contains(centerHit) && !centerHit.contains(el)),
        visually_truncated: el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1,
        tag, role,
        type: (el.getAttribute('type') || '').toLowerCase(),
        name: [el.getAttribute('name') || '', el.id || '', el.getAttribute('autocomplete') || ''].join(' '),
        disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
        in_form: !!el.closest('form'),
        href: el.getAttribute('href') || '',
        label: (el.getAttribute('aria-label') || text).slice(0, 160),
        visible_style: style.visibility !== 'hidden' && style.display !== 'none' && +style.opacity > 0.05
    };
}"""

_JS_HIDE_FOR_PLATE = r"""(elements) => {
    const nodes = [...new Set(elements.flatMap(el => [el, ...el.querySelectorAll('*')]))];
    window.__repurposerCaptureHidden = nodes.map(node => ({
        node, value: node.style.getPropertyValue('visibility'),
        priority: node.style.getPropertyPriority('visibility')
    }));
    for (const node of nodes) node.style.setProperty('visibility', 'hidden', 'important');
}"""

_JS_RESTORE_PLATE = r"""() => {
    for (const row of window.__repurposerCaptureHidden || []) {
        if (row.value) row.node.style.setProperty('visibility', row.value, row.priority);
        else row.node.style.removeProperty('visibility');
    }
    delete window.__repurposerCaptureHidden;
}"""

_JS_ISOLATE_CUTOUT = r"""(el) => {
    const attr = 'data-repurposer-capture-cutout';
    const previous = el.getAttribute(attr);
    el.setAttribute(attr, '');
    const style = document.createElement('style');
    style.textContent = 'html,body{background:transparent!important}' +
        'body *{visibility:hidden!important}' +
        '[' + attr + '],[' + attr + '] *{visibility:visible!important}';
    document.head.appendChild(style);
    window.__repurposerCutout = {el, attr, previous, style};
}"""

_JS_RESTORE_CUTOUT = r"""() => {
    const saved = window.__repurposerCutout;
    if (!saved) return;
    saved.style.remove();
    if (saved.previous === null) saved.el.removeAttribute(saved.attr);
    else saved.el.setAttribute(saved.attr, saved.previous);
    delete window.__repurposerCutout;
}"""

_CLICK_DANGER_RE = re.compile(
    r"delete|remove|destroy|buy|purchase|pay|checkout|order|submit|send|save|publish|deploy|"
    r"log\s*in|sign\s*in|register|subscribe|book|schedule|download|install|reset|confirm|accept|agree|"
    r"删除|移除|购买|支付|提交|发送|保存|发布|部署|登录|注册|订阅|预约|下载|安装|重置|确认|接受",
    re.IGNORECASE,
)
_CREDENTIAL_RE = re.compile(
    r"pass|secret|token|credential|card|cvv|cvc|security|otp|密码|凭据|卡号|验证码", re.IGNORECASE
)


def _rounded_box(box: dict[str, Any]) -> dict[str, float]:
    return {key: round(float(box.get(key) or 0), 3) for key in ("x", "y", "width", "height")}


def _target_viewport_clipped(raw: dict[str, Any]) -> bool:
    """Whether the visual subject, including visible overflow, crosses the viewport."""
    full = raw.get("subject") or raw["full"]
    visible = raw.get("subject_visible") or raw["visible"]
    return any(
        float(full[key]) - float(visible[key]) > 0.5
        for key in ("width", "height")
    )


def _target_element(
    raw: dict[str, Any],
    target: CaptureTarget,
    role: str,
    *,
    member_id: str | None = None,
    member_digest: str | None = None,
) -> dict[str, Any]:
    full = _rounded_box(raw.get("subject") or raw["full"])
    visible = _rounded_box(raw.get("subject_visible") or raw["visible"])
    page = raw["page"]
    viewport = raw["viewport"]
    css_box = full if role == "full" else visible
    if role == "cutout":
        normalized = {"x": 0.5, "y": 0.5, "w": 1.0, "h": 1.0}
    else:
        denominator = page if role == "full" else viewport
        offset_x = 0.0 if role == "full" else float(raw.get("scroll_x") or 0)
        offset_y = 0.0 if role == "full" else float(raw.get("scroll_y") or 0)
        normalized = {
            "x": (css_box["x"] - offset_x + css_box["width"] / 2) / max(float(denominator["width"]), 1),
            "y": (css_box["y"] - offset_y + css_box["height"] / 2) / max(float(denominator["height"]), 1),
            "w": css_box["width"] / max(float(denominator["width"]), 1),
            "h": css_box["height"] / max(float(denominator["height"]), 1),
        }
    text = str(raw.get("text") or "")
    element = {
        "id": member_id or target.element_id or target.target_id,
        "target_id": target.target_id,
        "kind": str(raw.get("kind") or "text"),
        "text": text[:90],
        "selector": target.selector,
        "x": round(normalized["x"], 6),
        "y": round(normalized["y"], 6),
        "w": round(normalized["w"], 6),
        "h": round(normalized["h"], 6),
        "css_box": css_box,
        "full_css_box": full,
        "region_text": text[:_CAPTURE_REGION_TEXT_CAP],
        "region_text_truncated": len(text) > _CAPTURE_REGION_TEXT_CAP,
        "region_visually_truncated": bool(raw.get("visually_truncated")),
    }
    if member_id is not None:
        element["member_id"] = member_id
        element["member_digest"] = member_digest
    if raw.get("covered"):
        element["covered"] = True
    return element


async def _query_capture_target_members(page: Any, target: CaptureTarget) -> list[Any]:
    if not target.selector:
        raise CaptureError(f"capture target {target.target_id!r} has no resolved selector")
    handles = await page.query_selector_all(f"css={target.selector}")
    if not handles:
        raise CaptureError(f"capture target {target.target_id!r} is absent after the state actions")
    if not target.all and len(handles) != 1:
        raise CaptureError(f"single capture target {target.target_id!r} resolved to {len(handles)} elements")
    if target.all and len(handles) > target.max_items:
        raise CaptureError(f"collection target {target.target_id!r} exceeds its {target.max_items}-member bound")
    return handles


async def _query_capture_target(page: Any, target: CaptureTarget) -> Any:
    handles = await _query_capture_target_members(page, target)
    if len(handles) != 1:
        raise CaptureError(f"capture action target {target.target_id!r} is not exactly one element")
    return handles[0]


async def _measure_capture_target_members(page: Any, target: CaptureTarget) -> list[dict[str, Any]]:
    import json

    members: list[dict[str, Any]] = []
    for index, handle in enumerate(await _query_capture_target_members(page, target)):
        facts = await handle.evaluate(_JS_CAPTURE_TARGET)
        facts["visually_truncated"] = bool(facts.get("visually_truncated")) or _target_viewport_clipped(facts)
        member_id = f"{target.target_id}-m{index:03d}"
        identity = json.dumps({
            "target_id": target.target_id, "index": index, "text": facts.get("text"),
            "full": facts.get("full"), "subject": facts.get("subject"),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        members.append({
            "handle": handle, "facts": facts, "member_id": member_id,
            "digest": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        })
    return members


async def _measure_capture_target(page: Any, target: CaptureTarget) -> dict[str, Any]:
    members = await _measure_capture_target_members(page, target)
    return dict(members[0]["facts"])


async def _assert_capture_route(page: Any, url: str) -> None:
    current = page.url
    if _origin(current) != _origin(url) or urlparse(current).path != urlparse(url).path:
        raise CaptureBlocked("a capture action attempted navigation outside the planned same-origin route")


async def _run_capture_action(page: Any, action: CaptureAction, targets: dict[str, CaptureTarget], url: str) -> None:
    if action.kind == "wait":
        await page.wait_for_timeout(int(action.milliseconds or 0))
        return
    if action.kind == "scroll" and action.y is not None:
        await page.evaluate("(y) => window.scrollTo(0, y)", action.y)
    else:
        target = targets[str(action.target_id)]
        handle = await _query_capture_target(page, target)
        facts = await handle.evaluate(_JS_CAPTURE_TARGET)
        if facts.get("disabled") or not facts.get("visible_style"):
            raise CaptureError(f"capture target {target.target_id!r} is disabled or hidden")
        if action.kind == "scroll":
            await handle.scroll_into_view_if_needed(timeout=5000)
        elif action.kind == "hover":
            await handle.hover(timeout=5000)
        elif action.kind == "fill":
            if facts.get("tag") not in {"input", "textarea"}:
                raise CaptureBlocked("fill only accepts a public text input or textarea")
            if facts.get("type") not in {"", "text", "search", "url"} or _CREDENTIAL_RE.search(str(facts.get("name") or "")):
                raise CaptureBlocked("fill refuses credentials, secrets, files and non-text controls")
            await handle.fill(action.value or "", timeout=5000)
        elif action.kind == "click":
            tag, role = facts.get("tag"), facts.get("role")
            allowed_anchor = tag == "a" and role == "tab" and str(facts.get("href") or "").startswith("#")
            if not ((tag == "button" or role in {"button", "tab"}) and (tag != "a" or allowed_anchor)):
                raise CaptureBlocked("click accepts only non-submit buttons, safe button roles, or same-page tab anchors")
            if facts.get("in_form") or facts.get("type") in {"submit", "image"}:
                raise CaptureBlocked("CapturePlan never submits a form")
            if _CLICK_DANGER_RE.search(str(facts.get("label") or "")):
                raise CaptureBlocked("capture click refused a consequential or credential action")
            await handle.click(timeout=5000)
        else:  # typed union keeps this unreachable; fail closed at the network boundary
            raise CaptureBlocked(f"unsupported capture action {action.kind!r}")
    await _settle(page)
    await _assert_capture_route(page, url)


def _full_page_inventory(elements: list[dict[str, Any]], page_width: int, page_height: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in elements:
        element = dict(raw)
        box = element.get("css_box")
        if isinstance(box, dict):
            element.update({
                "x": (float(box["x"]) + float(box["width"]) / 2) / max(page_width, 1),
                "y": (float(box["y"]) + float(box["height"]) / 2) / max(page_height, 1),
                "w": float(box["width"]) / max(page_width, 1),
                "h": float(box["height"]) / max(page_height, 1),
            })
        result.append(element)
    return result


def _capture_issue(
    state_id: str,
    error: Any,
    *,
    output_id: str | None = None,
    target_id: str | None = None,
    member_id: str | None = None,
) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "state_id": state_id, "output_id": output_id, "target_id": target_id,
            "member_id": member_id, "error": str(error)[:_CAPTURE_ISSUE_ERROR_CAP],
        }.items()
        if value is not None
    }


def _artifact_scale(artifact: CaptureArtifact) -> float:
    return float(artifact.scale or (4 if artifact.role == "hero" else 2))


def _member_view_id(output_id: str, index: int) -> str:
    candidate = f"{output_id}--m{index:03d}"
    if len(candidate) <= 64:
        return candidate
    return f"{output_id[:32]}-{hashlib.sha256(output_id.encode()).hexdigest()[:16]}-m{index:03d}"


async def _capture_plan_state(
    browser: Any,
    plan: CapturePlan,
    state: CaptureState,
    artifacts: list[CaptureArtifact],
    *,
    device_scale_factor: float,
    state_index: int,
    url: str,
) -> tuple[WebPageResearch, list[ShotCapture], list[dict[str, str]]]:
    context = await browser.new_context(
        viewport=plan.viewport.model_dump(),
        device_scale_factor=device_scale_factor,
    )
    issues: list[dict[str, str]] = []
    try:
        page = await context.new_page()
        await page.clock.install()
        await page.goto(url, wait_until="commit", timeout=_NAV_TIMEOUT_MS)
        await _settle(page)
        if _origin(page.url) != _origin(url):
            raise CaptureBlocked("the final capture redirected to another origin")
        route_url = page.url
        await _dismiss_consent(page)
        await _dismiss_overlays(page)
        await _preload(page)
        targets = {target.target_id: target for target in plan.targets}
        for action in state.actions:
            await _run_capture_action(page, action, targets, route_url)
        await _dismiss_overlays(page)
        await _settle(page)
        await _assert_capture_route(page, route_url)
        await page.clock.pause_at((await page.evaluate("Date.now()")) / 1000 + 0.1)
        rendered_html = await page.content()
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        research = extract_rendered_research(rendered_html, page.url, body_text)
        auto_elements = _stamp_elements(
            await page.evaluate(_JS_ELEMENTS), state_index, id_prefix=f"{state.state_id}-auto-"
        )
        needed_target_ids = {
            target_id for artifact in artifacts for target_id in artifact.target_names
        }
        target_members: dict[str, list[dict[str, Any]]] = {}
        target_errors: dict[str, Exception] = {}
        for target_id in sorted(needed_target_ids):
            try:
                target_members[target_id] = await _measure_capture_target_members(page, targets[target_id])
            except Exception as exc:
                target_errors[target_id] = exc

        def members_for(target_id: str) -> list[dict[str, Any]]:
            if target_id in target_errors:
                raise CaptureError(str(target_errors[target_id]))
            return target_members.get(target_id) or []

        def measured_element(
            target: CaptureTarget,
            member: dict[str, Any],
            role: str,
        ) -> dict[str, Any]:
            element = _target_element(
                member["facts"], target, role,
                member_id=member["member_id"] if target.all else None,
                member_digest=member["digest"] if target.all else None,
            )
            if role != "full" and (
                element["css_box"]["width"] <= 0 or element["css_box"]["height"] <= 0
            ):
                raise CaptureError(f"target {target.target_id!r} is outside the settled viewport")
            return element

        def with_target_elements(base: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
            element_ids = {str(element.get("id")) for element in additions}
            return [element for element in base if str(element.get("id")) not in element_ids] + additions

        shots: list[ShotCapture] = []
        role_order = {"view": 0, "hero": 0, "full": 1, "cutout": 2, "blank_plate": 3}
        for artifact in sorted(artifacts, key=lambda item: role_order[item.role]):
            if artifact.role == "cutout":
                target = targets[str(artifact.target_names[0])]
                if target.target_id in target_errors:
                    issues.append(_capture_issue(
                        state.state_id, target_errors[target.target_id],
                        output_id=artifact.output_id or artifact.artifact_id, target_id=target.target_id,
                    ))
                    continue
                for index, member in enumerate(members_for(target.target_id)):
                    try:
                        target_element = measured_element(target, member, artifact.role)
                        page_size = await page.evaluate(
                            "() => ({width: document.documentElement.scrollWidth,"
                            " height: document.documentElement.scrollHeight, y: scrollY})"
                        )
                        screenshot_args: dict[str, Any] = {
                            "type": "png", "animations": "disabled", "caret": "hide",
                            "scale": "device", "timeout": 60000, "full_page": True,
                            "clip": target_element["css_box"],
                        }
                        if artifact.transparent:
                            await member["handle"].evaluate(_JS_ISOLATE_CUTOUT)
                            try:
                                png = await page.screenshot(**screenshot_args, omit_background=True)
                            finally:
                                await page.evaluate(_JS_RESTORE_CUTOUT)
                        else:
                            png = await page.screenshot(**screenshot_args)
                        region_text = str(member["facts"].get("text") or "")
                        shots.append(ShotCapture(
                            y=int(page_size["y"]), heading=(region_text or state.state_id)[:90], png=png,
                            elements=with_target_elements(list(auto_elements), [target_element]),
                            device_scale_factor=device_scale_factor,
                            view_id=artifact.artifact_id if not target.all else _member_view_id(artifact.artifact_id, index),
                            state_id=state.state_id, output_id=artifact.output_id or artifact.artifact_id,
                            artifact_role=artifact.role, paired_view_id=artifact.paired_view_id,
                            target_id=target.target_id, target_ids=[target.target_id],
                            target_element_id=target.element_id or target.target_id if not target.all else member["member_id"],
                            member_id=member["member_id"], transparent=artifact.transparent,
                            route=plan.route, actions=[action.model_dump(mode="json") for action in state.actions],
                            page_height=int(page_size["height"]),
                            region_text=region_text[:_CAPTURE_REGION_TEXT_CAP],
                            region_text_truncated=len(region_text) > _CAPTURE_REGION_TEXT_CAP,
                            region_visually_truncated=bool(member["facts"].get("visually_truncated")),
                        ))
                    except Exception as exc:
                        issues.append(_capture_issue(
                            state.state_id, exc, output_id=artifact.output_id or artifact.artifact_id,
                            target_id=target.target_id, member_id=member["member_id"],
                        ))
                        logger.warning("web_capture_member_failed", artifact=artifact.artifact_id, error=str(exc))
                continue
            try:
                related_target_ids = list(artifact.target_names)
                if artifact.role in {"view", "hero"}:
                    related_target_ids.extend(
                        target_id
                        for other in plan.artifacts
                        if other.paired_view_id == artifact.artifact_id
                        for target_id in other.target_names
                    )
                target_elements: list[dict[str, Any]] = []
                for target_id in dict.fromkeys(related_target_ids):
                    target = targets[target_id]
                    if target_id in target_errors:
                        if artifact.output_id is not None:
                            raise CaptureError(str(target_errors[target_id]))
                        continue
                    for member in members_for(target_id):
                        try:
                            target_elements.append(measured_element(target, member, artifact.role))
                        except Exception:
                            if artifact.output_id is not None:
                                raise
                raw_members = [
                    member
                    for target_id in artifact.target_names
                    for member in target_members.get(target_id) or []
                ]
                raw_target = raw_members[0]["facts"] if raw_members else None
                page_size = await page.evaluate(
                    "() => ({width: document.documentElement.scrollWidth,"
                    " height: document.documentElement.scrollHeight, y: scrollY})"
                )
                elements = list(auto_elements)
                if artifact.role == "full":
                    elements = _full_page_inventory(elements, int(page_size["width"]), int(page_size["height"]))
                elements = with_target_elements(elements, target_elements)
                screenshot_args = {
                    "type": "png", "animations": "disabled", "caret": "hide",
                    "scale": "device", "timeout": 60000,
                }
                if artifact.role == "full" or artifact.coverage == "full":
                    screenshot_args["full_page"] = True
                if artifact.role == "blank_plate":
                    handles = [
                        member["handle"]
                        for target_id in artifact.target_names
                        for member in members_for(target_id)
                    ]
                    if not handles:
                        raise CaptureError("a blank_plate needs at least one resolved target")
                    before_layout = dict(page_size)
                    await page.evaluate(_JS_HIDE_FOR_PLATE, handles)
                    try:
                        png = await page.screenshot(**screenshot_args)
                        after_layout = await page.evaluate(
                            "() => ({width: document.documentElement.scrollWidth,"
                            " height: document.documentElement.scrollHeight, y: scrollY})"
                        )
                        if after_layout != before_layout:
                            raise CaptureError("visibility-hidden blank_plate changed page layout or scroll")
                    finally:
                        await page.evaluate(_JS_RESTORE_PLATE)
                else:
                    png = await page.screenshot(**screenshot_args)
                region_text = str(raw_target.get("text") or "") if raw_target else None
                single_member = raw_members[0] if len(raw_members) == 1 else None
                single_target = targets[artifact.target_names[0]] if len(artifact.target_names) == 1 else None
                shots.append(ShotCapture(
                    y=int(page_size["y"]), heading=(region_text or state.state_id)[:90], png=png,
                    elements=elements, device_scale_factor=device_scale_factor,
                    view_id=artifact.artifact_id, state_id=state.state_id, output_id=artifact.output_id,
                    artifact_role=artifact.role, paired_view_id=artifact.paired_view_id,
                    target_id=single_target.target_id if single_target else None,
                    target_ids=artifact.target_names,
                    target_element_id=(
                        single_target.element_id or single_target.target_id
                        if single_target is not None and not single_target.all and single_member is not None
                        else single_member["member_id"] if single_member is not None else None
                    ),
                    member_id=single_member["member_id"] if single_member is not None else None,
                    route=plan.route, actions=[action.model_dump(mode="json") for action in state.actions],
                    page_height=int(page_size["height"]),
                    region_text=region_text[:_CAPTURE_REGION_TEXT_CAP] if region_text is not None else None,
                    region_text_truncated=len(region_text) > _CAPTURE_REGION_TEXT_CAP if region_text is not None else None,
                    region_visually_truncated=bool(raw_target.get("visually_truncated")) if raw_target else None,
                ))
            except Exception as exc:
                issues.append(_capture_issue(
                    state.state_id, exc, output_id=artifact.output_id or artifact.artifact_id,
                    target_id=artifact.target_names[0] if len(artifact.target_names) == 1 else None,
                ))
                logger.warning("web_capture_output_failed", artifact=artifact.artifact_id, error=str(exc))
        return research, shots, issues
    finally:
        await context.close()


async def _capture_shots_with_policy(
    plan: CapturePlan, chrome: str, url: str
) -> tuple[list[ShotCapture], WebPageResearch | None, list[dict[str, str]]]:
    proxy = _PolicyProxy(
        max_requests=settings.web_capture_max_requests,
        max_bytes=settings.web_capture_max_bytes,
    )
    await proxy.start()
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            args = ["--disable-gpu", "--hide-scrollbars", "--mute-audio"]
            if settings.chrome_no_sandbox:
                args.append("--no-sandbox")
            browser = await pw.chromium.launch(
                executable_path=chrome, headless=True, args=args,
                proxy={"server": f"http://127.0.0.1:{proxy.port}"},
            )
            try:
                jobs: list[tuple[str, Any]] = []
                for index, state in enumerate(plan.states):
                    scales = sorted({
                        _artifact_scale(artifact) for artifact in plan.artifacts
                        if artifact.state_id == state.state_id
                    })
                    for scale in scales:
                        artifacts = [
                            artifact for artifact in plan.artifacts
                            if artifact.state_id == state.state_id and _artifact_scale(artifact) == scale
                        ]
                        jobs.append((state.state_id, _capture_plan_state(
                            browser, plan, state, artifacts,
                            device_scale_factor=scale, state_index=index, url=url,
                        )))
                results = await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)
                by_state: dict[str, tuple[WebPageResearch | None, list[ShotCapture], list[dict[str, str]]]] = {}
                for (state_id, _), result in zip(jobs, results):
                    previous = by_state.setdefault(state_id, (None, [], []))
                    if isinstance(result, Exception):
                        by_state[state_id] = (
                            previous[0], previous[1],
                            previous[2] + [_capture_issue(state_id, result)],
                        )
                        continue
                    research, shots, issues = result
                    by_state[state_id] = (
                        previous[0] or research, previous[1] + shots, previous[2] + issues,
                    )
                shots: list[ShotCapture] = []
                issues: list[dict[str, str]] = []
                for state in plan.states:
                    _research, state_shots, state_issues = by_state.get(state.state_id, (None, [], []))
                    shots.extend(state_shots)
                    issues.extend(state_issues)
                research = next(
                    (by_state[state.state_id][0] for state in plan.states if by_state.get(state.state_id, (None, [], []))[0]),
                    None,
                )
                return shots, research, issues
            finally:
                await browser.close()
    finally:
        await proxy.stop()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class CaptureOutcome:
    """What a capture yields. ``shots=[]`` is the honest degrade (no browser
    / browser failure) — the manifest still stands. ``screenshot`` stays the
    fold shot's bytes (the legacy single-shot seat). ``discovered`` = the
    same-host sub-page URLs the session's link scan picked (B4; empty when
    the visuals half never ran)."""

    research: WebPageResearch
    text: str
    screenshot: bytes | None
    final_url: str
    shots: list[ShotCapture] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page: PageCapture | None = None
    element_images: dict[str, bytes] = field(default_factory=dict)
    capture_plan: CapturePlan | None = None
    capture_issues: list[dict[str, str]] = field(default_factory=list)
    capture_issue_count: int = 0
    capture_issues_truncated: bool = False


async def capture_shots(plan: CapturePlan) -> CaptureOutcome:
    """Execute all outputs independently and freeze every usable view.

    Every state gets a fresh credential-free browser context and independently
    replays its actions from the clean baseline. Only fixed server-owned
    JavaScript measures layout or temporarily applies visibility:hidden.
    """
    url = capture_plan_url(plan)
    html, final_url = await _fetch_html(url)
    if _origin(final_url) != _origin(url):
        raise CaptureBlocked("the final capture route redirected to another origin")
    fallback_research = extract_research(html, final_url)
    chrome = resolve_chrome_path()
    if chrome is None:
        raise CaptureError("a final CaptureRequest requires Chrome; reconnaissance-only text is insufficient")
    try:
        shots, research, all_issues = await asyncio.wait_for(
            _capture_shots_with_policy(plan, chrome, url),
            timeout=settings.web_capture_timeout_seconds,
        )
    except Exception as exc:
        if isinstance(exc, CaptureError):
            raise
        raise CaptureError(f"final webpage capture failed: {exc}") from exc
    issues = all_issues[:_CAPTURE_MAX_ISSUES]
    issue_count = len(all_issues)
    issues_truncated = issue_count > len(issues)
    if not shots:
        import json

        raise CaptureError("final webpage capture obtained no usable views: " + json.dumps(
            issues, ensure_ascii=False, separators=(",", ":")
        ))
    research = research or fallback_research
    text = render_manifest_text(research)
    warnings: list[str] = []
    if research.body_truncated:
        warnings.append("rendered_body_truncated")
    if issues_truncated:
        warnings.append("capture_issues_truncated")
    return CaptureOutcome(
        research=research,
        text=text,
        screenshot=next((shot.png for shot in shots if shot.artifact_role in {"view", "hero"}), None),
        final_url=final_url,
        shots=shots,
        warnings=warnings,
        capture_plan=plan,
        capture_issues=issues,
        capture_issue_count=issue_count,
        capture_issues_truncated=issues_truncated,
    )


async def capture_page(url: str) -> CaptureOutcome:
    """One explicit URL → manifest + text + fold/section screenshots.

    Hard failures (policy refusal, unreachable, non-HTML) raise
    CaptureError/CaptureBlocked — the asset settles FAILED with the honest
    reason. The visuals half degrades to no-shots instead.
    """
    check_url_policy(url)  # static gate before any byte moves
    html, final_url = await _fetch_html(url)
    research = extract_research(html, final_url)
    text = render_manifest_text(research)
    shots: list[ShotCapture] = []
    discovered: list[str] = []
    warnings: list[str] = []
    page_capture: PageCapture | None = None
    element_images: dict[str, bytes] = {}
    chrome = resolve_chrome_path()
    if chrome is None:
        logger.warning("web_capture_chrome_missing", url=url)
        warnings.append("chrome_missing")
    else:
        try:
            # Chrome navigates the ORIGINAL url: redirect hops are exercised
            # under the proxy, each policy-checked at connect time.
            browser_capture = await asyncio.wait_for(
                _capture_visuals_with_policy(url, chrome),
                timeout=settings.web_capture_timeout_seconds,
            )
            research = browser_capture.research
            text = render_manifest_text(research)
            shots = browser_capture.shots
            discovered = browser_capture.discovered
            page_capture = browser_capture.page
            element_images = browser_capture.element_images
        except Exception as e:  # noqa: BLE001 — the visuals half degrades
            logger.warning("web_capture_screenshot_failed", url=url, error=str(e))
            shots, discovered = [], []
        if not shots:
            warnings.append("screenshot_failed")
    if research.body_truncated:
        warnings.append("rendered_body_truncated")
    return CaptureOutcome(
        research=research,
        text=text,
        screenshot=shots[0].png if shots else None,
        final_url=final_url,
        shots=shots,
        discovered=discovered,
        warnings=warnings,
        page=page_capture,
        element_images=element_images,
    )


def manifest_content_hash(text: str) -> str:
    """``meta.content_sha256`` of the manifest text — the understanding
    digest's addressing key. Stamped by the capture processor itself (the
    chain head has nothing to hash: a web_page is born with no bytes)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
