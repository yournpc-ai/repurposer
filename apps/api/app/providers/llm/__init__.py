"""Selectable text/code LLM boundary; media providers stay independent."""

from app.config import settings
from app.providers.llm.base import LLMClient


def get_llm_client() -> LLMClient:
    """Return the deployment's text/code client without cross-provider fallback."""
    if settings.llm_provider == "deepseek":
        from app.providers.llm.deepseek import deepseek_client

        return deepseek_client
    if settings.llm_provider == "gemini":
        from app.providers.llm.gemini import gemini_client

        return gemini_client
    from app.providers.llm.minimax import minimax_client

    return minimax_client


def price_text_tokens(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> float:
    """Price an estimate or a legacy aggregate against its owning provider."""
    selected = provider or (
        "deepseek" if model and model.startswith("deepseek-")
        else "gemini" if model and model.startswith("gemini-")
        else None
    )
    selected = selected or settings.llm_provider
    if selected == "deepseek":
        from app.providers.llm.deepseek import price_tokens

        return price_tokens(prompt_tokens, completion_tokens, model=model)
    if selected == "gemini":
        from app.providers.llm.gemini import price_tokens

        return price_tokens(prompt_tokens, completion_tokens, model=model)
    from app.providers.llm.minimax import price_tokens

    return price_tokens(prompt_tokens, completion_tokens, model=model)
