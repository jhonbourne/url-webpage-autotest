from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "webpage-scraper-agent"
    debug: bool = False
    log_level: str = "INFO"

    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # LLM
    llm_provider: str = "openai"

    # Fetching
    fetch_timeout_ms: int = 30000
    block_private_addresses: bool = True
    # Minimum visible text length before falling back to browser rendering
    static_fetch_min_text: int = 200
    user_agent: str = "webpage-scraper-agent/0.1 (internal data team tool)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
