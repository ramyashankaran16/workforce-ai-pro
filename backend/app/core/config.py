"""Application settings loaded from environment / .env."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# backend/ -- app/core/config.py -> core -> app -> backend
BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Absolute path, not ".env". A relative path resolves against the current
    # working directory, so running a script from anywhere other than backend/
    # would silently load no settings at all.
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "WorkForce AI Pro"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- database (PostgreSQL) ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "workforce_ai_pro"
    DB_SCHEMA: str = "public"

    JWT_SECRET_KEY: str = "insecure-dev-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ORIGINS: str = "http://localhost:5173"

    UPLOAD_DIR: str = "uploads"
    DATASET_DIR: str = "datasets"
    ML_MODEL_DIR: str = "ml_models"
    MAX_UPLOAD_SIZE_MB: int = 10

    DEFAULT_ADMIN_EMAIL: str = "admin@workforce.ai"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@123"

    @property
    def DATABASE_URL(self) -> URL:
        """
        Built with URL.create so special characters (@ # / % :) in the password
        never break the connection string.
        """
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    @property
    def SERVER_URL(self) -> URL:
        """Connection to the server itself, without selecting a database."""
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database="postgres",
        )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def describe_source(self) -> str:
        """Where settings were loaded from - useful in error messages."""
        return f"{ENV_FILE} (exists={ENV_FILE.exists()})"

    def ensure_directories(self) -> None:
        for path in [
            self.UPLOAD_DIR,
            os.path.join(self.UPLOAD_DIR, "documents"),
            os.path.join(self.UPLOAD_DIR, "profiles"),
            self.DATASET_DIR,
            self.ML_MODEL_DIR,
            "logs",
        ]:
            os.makedirs(path, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
