"""Zero-key web access for the research loop (ADR-052 B4 pilot).

DuckDuckGo's HTML endpoint needs no API key; fetching a page's readable
text is one GET plus stdlib tag-stripping. Both functions DEGRADE HONESTLY
— empty on any network/parse failure, never raising into the node:
research is best-effort enrichment, and the loop's agent reads an empty
result as "this trail ran dry", not as an exception.

``trust_env=True`` is explicit: the runner's HTTPS_PROXY (the render-proxy
precedent) must apply to these calls.
"""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

DDG_HTML_URL = "https://html.duckduckgo.com/html/"

_HEADERS = {
    # The HTML endpoint 403s default-script agents; a plain browser UA is
    # the documented workaround for the no-key form.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}

# One fetched page feeds the agent's evidence at this cap — long articles
# stay inside the prompt budget across the loop's iterations.
FETCH_TEXT_CAP = 6000


class _DdgResultsParser(HTMLParser):
    """Scrape DDG's HTML result page: result links ride class="result__a"
    anchors whose href wraps the target in /l/?uddg=<url-encoded>; snippets
    ride class="result__snippet"."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None  # "title" | "snippet"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()
        if "result__a" in classes:
            url = _unwrap_ddg_redirect(attr.get("href") or "")
            self._current = {"title": "", "url": url, "snippet": ""}
            self._capture = "title"
        elif "result__snippet" in classes and self._current is not None:
            self._capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._capture == "title" and self._current is not None:
            self.results.append(self._current)
            self._current = None
            self._capture = None
        elif self._capture == "snippet":
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture:
            self._current[self._capture] += data


def _unwrap_ddg_redirect(href: str) -> str:
    """DDG wraps outbound links as /l/?uddg=<encoded>; unwrap to the target."""
    if "uddg=" not in href:
        return href
    query = parse_qs(urlparse(href).query)
    return (query.get("uddg") or [href])[0]


async def web_search(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """One DDG HTML search → [{title, url, snippet}]; empty on any failure.

    Ads share the result__a class (inside result--ad containers) and ride
    duckduckgo.com/y.js redirect URLs — filtered out so the agent sees
    organic hits only."""
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=True) as client:
            resp = await client.get(DDG_HTML_URL, params={"q": query}, headers=_HEADERS)
        if resp.status_code != 200:
            return []
        parser = _DdgResultsParser()
        parser.feed(resp.text)
        return [
            r
            for r in parser.results
            if r["url"].startswith("http") and "duckduckgo.com" not in r["url"]
        ][:max_results]
    except httpx.HTTPError:
        return []


class _TextExtractor(HTMLParser):
    """Readable text out of an HTML page: skip script/style/navigation
    chrome, keep the body text, collapse whitespace."""

    _SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


async def fetch_text(url: str, *, max_chars: int = FETCH_TEXT_CAP) -> str:
    """One page → its readable text (capped); empty on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, trust_env=True
        ) as client:
            resp = await client.get(url, headers=_HEADERS)
        if resp.status_code != 200:
            return ""
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return ""
        extractor = _TextExtractor()
        extractor.feed(resp.text)
        return extractor.text()[:max_chars]
    except httpx.HTTPError:
        return ""
