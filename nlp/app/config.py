from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """NLP settings from the repo-root `.env` (see `.env.example`). Every NLP module reads settings from here."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    content_dir: Path = REPO_ROOT / "content"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct-q4_K_M"
    asr_device: str = "cpu"  # "mps" to try the Apple GPU
    asr_model: str = "ai4bharat/indic-conformer-600m-multilingual"
    ffmpeg_timeout_sec: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
