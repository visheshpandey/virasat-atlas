"""Application settings, loaded from the environment and an optional .env file."""
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INSECURE_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./virasat.db"
    SECRET_KEY: str = INSECURE_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALLOWED_ORIGINS: str = "http://localhost:8000"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    MEDIA_DIR: str = str(BASE_DIR / "media")
    MAX_UPLOAD_MB: int = 8

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    SEMANTIC_MODEL: str = ""
    TESSERACT_CMD: str = ""
    TESSDATA_PREFIX: str = ""

    @model_validator(mode="after")
    def _refuse_default_secret_in_production(self) -> "Settings":
        if self.APP_ENV == "production" and self.SECRET_KEY == INSECURE_SECRET:
            raise ValueError("SECRET_KEY must be set when APP_ENV=production")
        return self

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()
