"""TranslateClipParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class TranslateClipParams(BaseModel):
    target_output_id: str | None = Field(default=None, description="Translate only this one output (uuid); null = all clips in scope")
    target_language: str = Field(description="ISO code of the caption language (required — no meaningful default)")
    bilingual: bool = Field(
        default=False,
        description="True when the user asks for BILINGUAL side-by-side "
        "subtitles — the original text stays on screen under the translation "
        "(e.g. '双语字幕', '中英对照', 'bilingual subtitles'). false = the "
        "translated captions replace the original.",
    )
    fork: bool = Field(
        default=False,
        description="True = create a NEW derived version and keep the source "
        "clip untouched (user said '再来一版' / '加一版' / 'another version' "
        "or asked to keep the original, or the translation is one of several "
        "language versions made together); False = rewrite in place",
    )
