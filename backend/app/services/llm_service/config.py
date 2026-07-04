# app/services/llm_service/config.py
"""
Centralized configuration for LLM services.
All default model strings are controlled from this single file.
"""

from enum import Enum


class LLMProvider(str, Enum):
    """Available LLM providers"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    COHERE = "cohere"
    OLLAMA = "ollama"


# Centralized default models configuration
# Change these values here to update defaults across all services
DEFAULT_MODELS = {
    LLMProvider.OPENAI: "gpt-4-turbo-preview",
    LLMProvider.CLAUDE: "claude-3-opus-20240229",
    LLMProvider.GEMINI: "gemini-2.0-flash",
    LLMProvider.COHERE: "command-r-plus",
    LLMProvider.OLLAMA: "llama2"
}


def get_default_model(provider: LLMProvider | str) -> str:
    """
    Get the default model for a provider.

    Args:
        provider: LLM provider enum or string name

    Returns:
        Default model name for the provider
    """
    if isinstance(provider, str):
        provider = LLMProvider(provider.lower())

    return DEFAULT_MODELS.get(provider, "")


def get_all_default_models() -> dict[str, str]:
    """
    Get all default models as a dictionary.

    Returns:
        Dictionary mapping provider names to default models
    """
    return {provider.value: model for provider, model in DEFAULT_MODELS.items()}


def update_default_model(provider: LLMProvider | str, model: str) -> None:
    """
    Update the default model for a provider.

    Args:
        provider: LLM provider enum or string name
        model: New default model name
    """
    if isinstance(provider, str):
        provider = LLMProvider(provider.lower())

    DEFAULT_MODELS[provider] = model


# Task-based provider recommendations
TASK_RECOMMENDATIONS = {
    "code_analysis": LLMProvider.CLAUDE,      # Claude excels at code
    "code_generation": LLMProvider.OPENAI,    # GPT-4 good for generation
    "summarization": LLMProvider.COHERE,      # Cohere good at summarization
    "content_review": LLMProvider.CLAUDE,     # Claude good for content analysis
    "web_analysis": LLMProvider.GEMINI,       # Gemini good for web content
    "fast_response": LLMProvider.GEMINI,      # Gemini-2.0-flash is fastest
    "cost_effective": LLMProvider.OLLAMA,     # Ollama is free/local
}


def get_recommended_provider_for_task(task_type: str) -> LLMProvider:
    """
    Get the recommended provider for a specific task.

    Args:
        task_type: Type of task

    Returns:
        Recommended LLM provider
    """
    return TASK_RECOMMENDATIONS.get(task_type.lower(), LLMProvider.OPENAI)