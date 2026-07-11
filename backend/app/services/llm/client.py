"""Role-based LangChain chat-model factory for the extraction pipeline.

Kept separate from the legacy app.services.llm_service (which is pending removal).

Two roles map to two configured models:
- "general": planner + llm_extract (Qwen3 general instruct model)
- "code":    selector generation, a code task (Qwen3-Coder model)

Providers: "dashscope" (Aliyun, via the OpenAI-compatible endpoint) or "claude".
"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from app.core.config import Settings

Role = Literal["general", "code"]


def _model_for_role(settings: Settings, role: Role) -> str:
    return settings.llm_code_model if role == "code" else settings.llm_model


def build_chat_model(
    settings: Settings, role: Role = "general", **overrides: Any
) -> BaseChatModel:
    provider = settings.llm_provider.lower()
    model_name = _model_for_role(settings, role)

    if provider == "dashscope":
        from langchain_openai import ChatOpenAI

        params: dict[str, Any] = {
            "model": model_name,
            "base_url": settings.dashscope_base_url,
            # Placeholder when unset so the server still boots (structure-only mode
            # and /docs work without a key); real LLM calls then fail with a clear
            # auth error surfaced as PLANNING_FAILED / EXTRACTION_FAILED.
            "api_key": settings.dashscope_api_key or "not-set",
            "max_tokens": 4096,
            "timeout": 60,
            "temperature": 0,
        }
        params.update(overrides)
        return ChatOpenAI(**params)

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        params = {
            "model": model_name,
            "max_tokens": 4096,
            "timeout": 60,
            "temperature": 0,
        }
        if settings.anthropic_api_key:
            params["api_key"] = settings.anthropic_api_key
        params.update(overrides)
        return ChatAnthropic(**params)

    raise ValueError(
        f"Unsupported llm_provider '{settings.llm_provider}'. Expected 'dashscope' or 'claude'."
    )
