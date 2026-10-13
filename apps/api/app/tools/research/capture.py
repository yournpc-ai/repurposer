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
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
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

# The extracted_text rendering of the manifest — the prompt-budget twin of
# web.py's FETCH_TEXT_CAP.
MANIFEST_TEXT_CAP = 6000


class _CopyInventoryParser(HTMLParser):
    """Pull the visible copy inventory out of a page: <title>, the meta
    description, heading text (h1-h3), button labels and anchor text.
    Script/style/svg bodies are skipped; entities are unescaped by the
    parser (convert_charrefs)."""

    _SKIP = {"script", "style", "noscript", "svg", "template"}
    _CAPTURE = {"title", "h1", "h2", "h3", "button", "a"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
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
        if not (_ITEM_MIN_LEN <= len(text) <= _ITEM_MAX_LEN):
            return
        target = {
            "h1": self.h1,
            "h2": self.h2,
            "h3": self.h3,
            "button": self.buttons,
            "a": self.links,
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
    )


def render_manifest_text(research: WebPageResearch) -> str:
    """The manifest as plain text — the asset's ``extracted_text`` seat, so
    a web_page counts as text material for the material predicates and the
    assembly layer reads it through the ONE text seat (asset_text_content).
    """
    parts = [research.title, research.description]
    for listing in (research.h1, research.h2, research.h3, research.buttons, research.links):
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


async def _screenshot_with_policy(url: str, chrome: str) -> bytes | None:
    """One viewport screenshot of ``url`` behind the policy proxy, in a
    throwaway credential-free profile. None = the screenshot half degraded
    (browser error / cap / timeout) — logged, never raised."""
    proxy = _PolicyProxy(
        max_requests=settings.web_capture_max_requests,
        max_bytes=settings.web_capture_max_bytes,
    )
    await proxy.start()
    try:
        with tempfile.TemporaryDirectory(prefix="web-capture-") as tmp:
            out_path = Path(tmp) / "capture.png"
            profile_dir = Path(tmp) / "profile"
            args = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
                f"--timeout={_NAV_TIMEOUT_MS}",
                f"--screenshot={out_path}",
                f"--proxy-server=http://127.0.0.1:{proxy.port}",
                # 隔离环境无凭证: a fresh profile per capture — no cookies,
                # no saved credentials, no sync, no extensions.
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--mute-audio",
                "--disable-background-networking",
                "--disable-component-update",
            ]
            if settings.chrome_no_sandbox:
                args.append("--no-sandbox")
            args.append(url)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(
                    proc.wait(), timeout=settings.web_capture_timeout_seconds
                )
            except TimeoutError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                logger.warning("web_capture_chrome_timeout", url=url)
                return None
            if not out_path.exists() or out_path.stat().st_size == 0:
                logger.warning(
                    "web_capture_screenshot_empty", url=url, returncode=proc.returncode
                )
                return None
            return out_path.read_bytes()
    finally:
        await proxy.stop()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class CaptureOutcome:
    """What a capture yields. ``screenshot=None`` is the honest degrade
    (no browser / browser failure) — the manifest still stands."""

    research: WebPageResearch
    text: str
    screenshot: bytes | None
    final_url: str
    warnings: list[str] = field(default_factory=list)


async def capture_page(url: str) -> CaptureOutcome:
    """One explicit URL → manifest + text + screenshot bytes.

    Hard failures (policy refusal, unreachable, non-HTML) raise
    CaptureError/CaptureBlocked — the asset settles FAILED with the honest
    reason. The screenshot half degrades to None instead.
    """
    check_url_policy(url)  # static gate before any byte moves
    html, final_url = await _fetch_html(url)
    research = extract_research(html, final_url)
    text = render_manifest_text(research)
    screenshot: bytes | None = None
    warnings: list[str] = []
    chrome = resolve_chrome_path()
    if chrome is None:
        logger.warning("web_capture_chrome_missing", url=url)
        warnings.append("chrome_missing")
    else:
        try:
            # Chrome navigates the ORIGINAL url: redirect hops are exercised
            # under the proxy, each policy-checked at connect time.
            screenshot = await _screenshot_with_policy(url, chrome)
        except Exception as e:  # noqa: BLE001 — screenshot half degrades
            logger.warning("web_capture_screenshot_failed", url=url, error=str(e))
        if screenshot is None:
            warnings.append("screenshot_failed")
    return CaptureOutcome(
        research=research, text=text, screenshot=screenshot, final_url=final_url,
        warnings=warnings,
    )


def manifest_content_hash(text: str) -> str:
    """``meta.content_sha256`` of the manifest text — the understanding
    digest's addressing key. Stamped by the capture processor itself (the
    chain head has nothing to hash: a web_page is born with no bytes)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
