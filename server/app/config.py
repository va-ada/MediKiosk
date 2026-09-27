from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Every key from the repo-root `.env` (see `.env.example`)."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://mk:mk@localhost:5433/medikiosk"
    nlp_url: str = "http://localhost:8001"
    his_url: str = "http://localhost:8002"
    relay_url: str = "http://localhost:8003"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct-q4_K_M"
    server_prefix: str = "A"
    wait_limit_min: int = 90
    escalate_after_sec: int = 60
    jwt_secret: str = ""
    master_key_b64: str = ""
    content_dir: Path = REPO_ROOT / "content"
    data_dir: Path = REPO_ROOT / "data"
    voice_languages: str = "hi"  # ASR (IndicConformer) has no English → English questions are tap-only
    run_workers: bool = True  # background loops (outbox, escalation); tests turn them off


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
