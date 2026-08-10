"""AddMusicParams — compile-time adjudication document (see registry)."""

from pydantic import BaseModel, Field


class AddMusicParams(BaseModel):
    mood: str | None = Field(default=None, description="Music mood keyword (e.g. calm, upbeat); null = pick from the content brief")
    music_id: str | None = Field(default=None, description="A specific library track id; null = auto-pick by mood")
    gain_db: float | None = Field(default=None, description="Music bed gain in dB; null = library default")
