"""Chat delivery and media races — unit contracts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.chat import editor_media

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_explicit_voice_prohibition_stops_before_authorization_or_execution():
    from app.chat.editor import GenerateVoiceArgs

    turn = SimpleNamespace(turn_id=None, text="不要配音或新增语音，保留原声和配乐。")
    with pytest.raises(ValueError, match="disallowed narration"):
        await editor_media.submit_editor_media(
            turn, "generate_voice", GenerateVoiceArgs(text="Unrequested speech", language="en"),
            None, None, "forbidden-voice",
        )
