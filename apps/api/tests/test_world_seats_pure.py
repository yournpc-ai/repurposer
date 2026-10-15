"""Pure tests for the world seats (app/tools/world.py) — the consult-first
law's key normalization. No DB, no LLM, no HTTP (suite discipline): the
seat's session paths stay e2e-covered, what's gated here is the canonical
key form — two spellings of the same page must hit the same seat row."""

from app.tools.world import normalize_page_url


def test_scheme_and_host_case_fold() -> None:
    assert normalize_page_url("HTTPS://WWW.Zymix.AI/en/") == "https://www.zymix.ai/en"


def test_bare_trailing_slash_stripped() -> None:
    assert normalize_page_url("https://www.zymix.ai/en/") == normalize_page_url(
        "https://www.zymix.ai/en"
    )


def test_root_path_survives_as_slash() -> None:
    assert normalize_page_url("https://example.com") == "https://example.com/"


def test_fragment_dropped_query_kept() -> None:
    assert (
        normalize_page_url("https://example.com/docs?page=2#section")
        == "https://example.com/docs?page=2"
    )


def test_inner_trailing_slashes_and_whitespace() -> None:
    assert normalize_page_url("  https://example.com/a/b/  ") == "https://example.com/a/b"
