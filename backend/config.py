"""Configuration de l'application via variables d'environnement."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings

ENV_FILE: Path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Parametres de l'application charges depuis .env ou l'environnement."""

    voxtral_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./lexia.db"
    jwt_secret: str = "lexia-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60
    jwt_refresh_token_days: int = 7

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Retourne les parametres de l'application (caches)."""
    return Settings()
