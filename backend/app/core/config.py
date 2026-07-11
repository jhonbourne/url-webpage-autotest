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

    # LLM
    llm_provider: str = "claude"
    # Overrides the provider's built-in default model when set (see llm_service/config.py)
    llm_model: str | None = "claude-sonnet-5"
    # Read from .env and passed explicitly to the client (uvicorn does not export .env
    # into the process environment, so the SDK cannot pick it up on its own).
    anthropic_api_key: str | None = None

    # Fetching
    fetch_timeout_ms: int = 30000
    block_private_addresses: bool = True
    # Minimum visible text length before falling back to browser rendering
    static_fetch_min_text: int = 200
    user_agent: str = "webpage-scraper-agent/0.1 (internal data team tool)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
