from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    voxtral_api_key: str = ""
    mistral_api_key: str = ""

    model_config = {"env_file": str(ENV_FILE), "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
