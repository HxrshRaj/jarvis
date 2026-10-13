from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{(ROOT / 'backend' / 'jarvis.db').as_posix()}"
    # Used to sign session tokens. MUST be overridden outside local development.
    secret_key: str = "dev-only-change-me"
    token_ttl_seconds: int = 60 * 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]
    # The only directory tools may touch. Everything outside is refused.
    workspace_root: Path = ROOT / "workspace"
    max_file_bytes: int = 256 * 1024
    command_timeout_seconds: int = 60
    max_output_chars: int = 20_000
    max_plan_steps: int = 8
    # LLM provider: "mock" (deterministic, offline) or "openai_compat"
    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""  # read from env only; never stored in DB or returned by the API
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    # Optional capabilities; empty = not configured (the UI reports them as unavailable).
    llm_vision_model: str = ""
    llm_stt_model: str = ""  # e.g. whisper-1
    llm_tts_model: str = ""  # e.g. tts-1
    llm_tts_voice: str = "alloy"
    # Cost *estimates* only (USD per 1M tokens); 0 means "pricing not configured".
    price_prompt_per_mtok: float = 0.0
    price_completion_per_mtok: float = 0.0
    router: str = "rules"  # "rules" | "model" (use trained classifier when confident)
    rate_limit_per_minute: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
