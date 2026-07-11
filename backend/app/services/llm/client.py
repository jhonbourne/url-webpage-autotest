"""Clean LangChain chat-model factory for the extraction pipeline.

Kept separate from the legacy app.services.llm_service (which is pending removal).
Only Claude is wired today; other providers plug in the same way when needed.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.config import Settings


def build_chat_model(settings: Settings, **overrides: Any) -> BaseChatModel:
    provider = settings.llm_provider.lower()

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        params: dict[str, Any] = {
            "model": settings.llm_model or "claude-sonnet-5",
            "max_tokens": 4096,
            "timeout": 60,
            "temperature": 0,
        }
        if settings.anthropic_api_key:
            params["api_key"] = settings.anthropic_api_key
        params.update(overrides)
        return ChatAnthropic(**params)

    raise ValueError(
        f"Unsupported llm_provider '{settings.llm_provider}'. "
        "Only 'claude' is wired in the P1 extraction pipeline."
    )
