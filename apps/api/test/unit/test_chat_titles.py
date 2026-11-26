from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.chat.titles import (
    TitleSummaryPayload,
    _collect_turn_evidence,
    clean_generated_title,
    derive_conversation_title,
    derive_project_title,
    extract_url_brand,
    refine_title_from_composition,
    should_auto_upgrade_title,
    summarize_titles_from_turn,
)


def test_extract_url_brand_skips_generic_subdomains():
    assert extract_url_brand("给 https://agent.oxvalue.ai/ 做一个 30s 中文宣传片") == "Oxvalue"
    assert extract_url_brand("Check https://www.linear.app/features") == "Linear"
    assert extract_url_brand("no url here") is None


def test_derive_project_and_conversation_titles_strip_urls_and_filler():
    prompt = "帮我给 https://agent.oxvalue.ai/ 做一个 30s 中文宣传片"
    proj = derive_project_title(prompt)
    conv = derive_conversation_title(prompt, project_title=proj)
    assert proj == "Oxvalue"
    assert "http" not in conv
    assert conv == "30s 中文宣传片"

    # Short bare noun retains its action verb (e.g. "制作宣传片" instead of stripped "宣传片")
    short_prompt = "给 https://agent.oxvalue.ai/ 制作一个宣传片"
    assert derive_conversation_title(short_prompt, project_title="Oxvalue") == "制作宣传片"


def test_refine_title_from_composition_dedupes_project_prefix():
    assert (
        refine_title_from_composition("OxValue 30 秒宣传片", project_title="OxValue")
        == "30 秒宣传片"
    )
    assert (
        refine_title_from_composition("产品发布预告片", project_title="OxValue")
        == "产品发布预告片"
    )


def test_should_auto_upgrade_respects_user_edited_lock():
    assert should_auto_upgrade_title("New chat") is True
    assert should_auto_upgrade_title("给 https://agent.oxvalue.ai/...", is_project=True) is True
    assert should_auto_upgrade_title("30s 中文宣传片", auto_title="30s 中文宣传片") is True
    assert should_auto_upgrade_title("我的自定义片名", auto_title="30s 中文宣传片") is False
    # Hard lock: once user_edited=True, even default-looking or URL-containing titles stay untouched
    assert should_auto_upgrade_title("New chat", user_edited=True) is False
    assert (
        should_auto_upgrade_title(
            "https://oxvalue.ai 官网片",
            user_edited=True,
            is_project=True,
        )
        is False
    )


def test_clean_generated_title_strips_quotes_urls_and_project_prefix():
    assert (
        clean_generated_title("「OxValue 30秒产品宣传片」", project_title="OxValue")
        == "30秒产品宣传片"
    )
    assert clean_generated_title("https://oxvalue.ai/") is None


def test_collect_turn_evidence_includes_tool_steps_and_webpages():
    msgs = [
        SimpleNamespace(role="user", content="给 https://agent.oxvalue.ai/ 做宣传片", intent=None),
        SimpleNamespace(
            role="assistant",
            content="",
            intent={
                "type": "activity",
                "frame": {"tool_name": "get_web_page", "detail": {"url": "https://agent.oxvalue.ai/"}},
            },
        ),
        SimpleNamespace(
            role="assistant",
            content="我先了解了 OxValue AI 的智能估值平台，建议做 30 秒科技感双语宣传片。",
            intent=None,
        ),
    ]
    readings = [
        SimpleNamespace(url="https://agent.oxvalue.ai/", text="OxValue AI — Intelligent Technology Valuation Agent")
    ]
    digest, step_count = _collect_turn_evidence(msgs, page_readings=readings)
    assert step_count == 2
    assert "get_web_page" in digest
    assert "OxValue AI" in digest


@pytest.mark.asyncio
async def test_summarize_titles_from_turn_uses_llm_generate():
    fake_llm = SimpleNamespace(
        generate=AsyncMock(
            return_value=TitleSummaryPayload(
                project_title="OxValue AI",
                conversation_title="OxValue AI 制作官网宣传片",
            )
        )
    )
    proj, conv = await summarize_titles_from_turn(
        "User: 给 https://agent.oxvalue.ai/ 制作一个宣传片\nTools/Steps executed: get_web_page(https://agent.oxvalue.ai/)",
        ui_language="zh",
        need_project_title=True,
        llm_client=fake_llm,
    )
    assert proj == "OxValue AI"
    assert conv == "制作官网宣传片"
    fake_llm.generate.assert_awaited_once()
