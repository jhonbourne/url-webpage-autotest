from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "webpage-scraper-agent"
    debug: bool = False
    log_level: str = "INFO"

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value so the
    # validator below can accept a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # LLM: provider is "dashscope" (Aliyun, OpenAI-compatible) or "claude".
    llm_provider: str = "dashscope"
    # Role-based models. Swap these in .env for the logic-test (small) vs
    # performance-eval (large) profiles; prefer qwen3-*, then higher versions.
    llm_model: str = "qwen3-8b"  # general reasoning: planner, llm_extract
    llm_code_model: str = "qwen3-coder-30b-a3b-instruct"  # code task: selector generation

    # DashScope (read from .env; uvicorn does not export .env into the process env,
    # so the key must be passed to the client explicitly).
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Anthropic (only used when llm_provider == "claude").
    anthropic_api_key: str | None = None

    # Extraction quality / reflection loop
    max_extraction_retries: int = 2
    min_field_coverage: float = 0.5

    # Fetching
    fetch_timeout_ms: int = 30000
    block_private_addresses: bool = True
    # Minimum visible text length before falling back to browser rendering
    static_fetch_min_text: int = 200
    user_agent: str = "webpage-scraper-agent/0.1 (internal data team tool)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
