"""Configuration de l'application via variables d'environnement."""

import sys
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings

ENV_FILE: Path = Path(__file__).resolve().parent.parent / ".env"

_INSECURE_JWT_SECRET: str = "lexia-dev-secret-change-in-prod"


class Settings(BaseSettings):
    """Parametres de l'application charges depuis .env ou l'environnement."""

    voxtral_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./lexia.db"
    jwt_secret: str = _INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60
    jwt_refresh_token_days: int = 7

    # CORS : origines autorisees (separer par virgule)
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    # LLM : modele Claude a utiliser
    claude_model: str = "claude-sonnet-4-6"
    claude_temperature: float = 0.0
    claude_max_tokens: int = 4096

    # Retrieval : nombre de resultats
    retrieval_top_k_cr: int = 2
    retrieval_top_k_bibles: int = 5

    # Classification : seuil de confiance
    classification_confidence_threshold: float = 0.7

    # Upload : taille max en Mo
    max_upload_size_mb: int = 200

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Retourne les parametres de l'application (caches)."""
    return Settings()


def validate_settings_at_startup() -> None:
    """Valide les parametres critiques au demarrage.

    En mode developpement (SQLite), affiche un avertissement.
    En mode production (PostgreSQL), refuse de demarrer.
    """
    settings = get_settings()
    if settings.jwt_secret == _INSECURE_JWT_SECRET:
        is_production: bool = "postgresql" in settings.database_url
        if is_production:
            print(
                "ERREUR CRITIQUE : JWT_SECRET n'est pas configure. "
                "Definissez la variable d'environnement JWT_SECRET "
                "avec une valeur aleatoire d'au moins 32 caracteres.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(
                "AVERTISSEMENT : JWT_SECRET utilise la valeur par defaut. "
                "Configurez JWT_SECRET avant tout deploiement.",
                file=sys.stderr,
            )
