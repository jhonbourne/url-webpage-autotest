# app/services/llm_service/llm_selector.py
"""
LLM Service Selector - Factory for selecting and initializing different LLM providers.
Allows agents to dynamically choose the best LLM model based on requirements.
"""

from typing import Any

from .config import LLMProvider


class LLMSelector:
    """
    Factory class for selecting and instantiating LLM services.
    Provides unified interface for different LLM providers.
    """
    
    # Default models for each provider
    DEFAULT_MODELS = {
        LLMProvider.OPENAI: "gpt-4-turbo-preview",
        LLMProvider.CLAUDE: "claude-3-opus-20240229",
        LLMProvider.GEMINI: "gemini-2.0-flash",
        LLMProvider.COHERE: "command-r-plus",
        LLMProvider.OLLAMA: "llama2"
    }
    
    @staticmethod
    def get_service(
        provider: LLMProvider | str,
        base_url: str | None = None
    ) -> Any:
        """
        Get LLM service instance for specified provider.
        
        Args:
            provider: LLM provider enum or string name
            base_url: Optional base URL (used for Ollama)
            
        Returns:
            Instantiated LLM service
            
        Raises:
            ValueError: If provider is not supported
        """
        # Convert string to enum if needed
        if isinstance(provider, str):
            provider = LLMProvider(provider.lower())
        
        if provider == LLMProvider.OPENAI:
            from .openai_service import LLMService
            return LLMService()
        
        elif provider == LLMProvider.CLAUDE:
            from .claude_service import LLMService
            return LLMService()
        
        elif provider == LLMProvider.GEMINI:
            from .gemini_service import LLMService
            return LLMService()
        
        elif provider == LLMProvider.COHERE:
            from .cohere_service import LLMService
            return LLMService()
        
        elif provider == LLMProvider.OLLAMA:
            from .ollama_service import LLMService
            return LLMService(base_url=base_url or "http://localhost:11434")
        
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    @staticmethod
    def get_model_name(provider: LLMProvider | str) -> str:
        """
        Get default model name for a provider.
        
        Args:
            provider: LLM provider
            
        Returns:
            Default model name for the provider
        """
        if isinstance(provider, str):
            provider = LLMProvider(provider.lower())
        
        return LLMSelector.DEFAULT_MODELS.get(provider, "")
    
    @staticmethod
    def list_providers() -> dict[str, str]:
        """
        List all available providers with their default models.
        
        Returns:
            Dictionary of provider names and their default models
        """
        return {
            provider.value: model 
            for provider, model in LLMSelector.DEFAULT_MODELS.items()
        }


# Example usage:
# selector = LLMSelector()
# 
# # Get service for OpenAI
# openai_service = selector.get_service(LLMProvider.OPENAI)
# 
# # Get service for Claude
# claude_service = selector.get_service("claude")
# 
# # List all available providers
# providers = selector.list_providers()
