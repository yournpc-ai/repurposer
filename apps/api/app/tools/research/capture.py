"""Rich web capture: one explicit URL → structured copy inventory + screenshot.

The capture half of the "URL → web_page asset" recipe (MG film batch D1).
Two layers:

- ``extract_research`` — PURE: HTML → the grounding manifest (title / meta
  description / h1-h3 / button and link copy). Parser-based (stdlib
  HTMLParser, malformed-HTML tolerant); the spike's regexes mis-fired on
  attribute order and are retired.
- ``capture_page`` — NETWORK: fetch the HTML (per-hop redirect policy,
  byte cap) and take a headless-Chrome viewport screenshot.

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
import shutil
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import structlog

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
# web.py's FETCH_TEXT_CAP.
MANIFEST_TEXT_CAP = 6000


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
        research.buttons,
        research.links,
        research.paragraphs,
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
        if (e.closest('header,nav,[role=navigation],[role=banner]')) return true;
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
    const box = r => (r = clip(r), {
        x: +((r.left + r.width / 2) / W).toFixed(4),
        y: +((r.top + r.height / 2) / H).toFixed(4),
        w: +(r.width / W).toFixed(4),
        h: +(r.height / H).toFixed(4)
    });
    const blockOf = n => {
        let e = n.parentElement;
        while (e && e !== document.body && getComputedStyle(e).display.startsWith('inline')) e = e.parentElement;
        return e;
    };
    for (const b of document.querySelectorAll('a,button,[role=button],[role=tab]')) {
        const r = b.getBoundingClientRect(), t = textOf(b) || (b.getAttribute('aria-label') || '').trim();
        if (!t || t.length > 60 || !vis(b, r) || r.height > 120) continue;
        out.push({kind: inChrome(b) ? 'pinned' : 'button', text: t, ...box(r), ...(covered(b, r) ? {covered: true} : {})});
        seen.add(b);
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
        out.push({kind: inChrome(e) ? 'pinned' : heading ? 'heading' : 'text', text: t, size: Math.round(fs), ...box(r), ...(covered(e, r) ? {covered: true} : {})});
    }
    for (const m of document.querySelectorAll('img,video,canvas,svg,picture')) {
        if (m.closest('svg') && m.tagName.toLowerCase() !== 'svg' || m.tagName === 'IMG' && m.closest('picture')) continue;
        const r = m.getBoundingClientRect();
        if (!vis(m, r) || r.width * r.height < W * H * 0.02) continue;
        out.push({kind: m.tagName === 'VIDEO' ? 'video' : 'image', text: m.getAttribute('alt') || m.getAttribute('aria-label') || '', ...box(r), ...(covered(m, r) ? {covered: true} : {})});
    }
    return out.sort((a, b) => a.y - b.y || a.x - b.x);
}"""


@dataclass
class ShotCapture:
    """One captured view of the page: the fold (index 0) or a section stop.
    ``elements`` = the viewport-relative inventory at this stop (element ids
    stamped capture-side: ``s<shot>e<j>``)."""

    y: int
    heading: str
    png: bytes
    elements: list[dict] = field(default_factory=list)


def _stamp_elements(raw: list[dict], shot_idx: int) -> list[dict]:
    """Raw evaluate output → the meta shape: ids assigned, text capped, the
    list truncated (meta size is bounded at the birthplace)."""
    out: list[dict] = []
    for j, e in enumerate(raw[:_ELEMENTS_PER_SHOT]):
        item = {
            "id": f"s{shot_idx}e{j}",
            "kind": str(e.get("kind") or "text"),
            "text": str(e.get("text") or "")[:90],
            "x": float(e.get("x") or 0),
            "y": float(e.get("y") or 0),
            "w": float(e.get("w") or 0),
            "h": float(e.get("h") or 0),
        }
        if e.get("covered"):
            item["covered"] = True
        out.append(item)
    return out


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
    await page.evaluate("() => window.scrollTo(0, 0)")
    await page.wait_for_timeout(400)
    return await page.evaluate("() => document.documentElement.scrollHeight")


async def _capture_visuals_with_policy(
    url: str, chrome: str
) -> tuple[list[ShotCapture], list[str]]:
    """fold + per-section screenshots of ``url`` behind the policy proxy, in
    a throwaway credential-free context (playwright contexts are ephemeral
    by construction — no cookies, no sync), plus the same-host sub-page
    discovery list (B4). The visuals half is best-effort by contract: the
    caller wraps failures and degrades to ``shots=[]``."""
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
                    viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}
                )
                # Navigation waits only for the EARLY commit signal, never
                # `load`: one stalled sub-resource (a font / analytics chunk
                # on a slow path) blocks the `load` event and burns the whole
                # budget without a single pixel painted (the 2026-10-18
                # snappify incident — text fetched fine, zero page views).
                # Settling is the ladder's job below: best-effort networkidle
                # (suppressed) + fixed beats + scroll preloading.
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS
                )
                await _settle(page)
                consent = await _dismiss_consent(page)
                overlays = await _dismiss_overlays(page)
                page_height = await _preload(page)
                anchors: list[dict] = []
                with contextlib.suppress(Exception):
                    anchors = await page.evaluate(_JS_ANCHORS)
                stops = _choose_stops(anchors, page_height)
                shots: list[ShotCapture] = []
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
                    shots.append(
                        ShotCapture(y=y, heading=heading, png=png, elements=elements)
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
                return shots, discovered
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
    chrome = resolve_chrome_path()
    if chrome is None:
        logger.warning("web_capture_chrome_missing", url=url)
        warnings.append("chrome_missing")
    else:
        try:
            # Chrome navigates the ORIGINAL url: redirect hops are exercised
            # under the proxy, each policy-checked at connect time.
            shots, discovered = await asyncio.wait_for(
                _capture_visuals_with_policy(url, chrome),
                timeout=settings.web_capture_timeout_seconds,
            )
        except Exception as e:  # noqa: BLE001 — the visuals half degrades
            logger.warning("web_capture_screenshot_failed", url=url, error=str(e))
            shots, discovered = [], []
        if not shots:
            warnings.append("screenshot_failed")
    return CaptureOutcome(
        research=research,
        text=text,
        screenshot=shots[0].png if shots else None,
        final_url=final_url,
        shots=shots,
        discovered=discovered,
        warnings=warnings,
    )


def manifest_content_hash(text: str) -> str:
    """``meta.content_sha256`` of the manifest text — the understanding
    digest's addressing key. Stamped by the capture processor itself (the
    chain head has nothing to hash: a web_page is born with no bytes)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
