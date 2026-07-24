"""Adapter registry — one adapter instance per platform (§10.1)."""

from app.models.schemas import ChannelPlatform
from app.services.distribution.adapters.base import PlatformAdapter
from app.services.distribution.adapters.linkedin import LinkedInAdapter
from app.services.distribution.adapters.tiktok import TikTokAdapter

_ADAPTERS: dict[ChannelPlatform, PlatformAdapter] = {
    ChannelPlatform.LINKEDIN: LinkedInAdapter(),
    ChannelPlatform.TIKTOK: TikTokAdapter(),
}


def get_adapter(platform: ChannelPlatform) -> PlatformAdapter:
    return _ADAPTERS[platform]
