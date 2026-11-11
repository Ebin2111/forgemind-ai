"""Application settings.

Values are read from environment variables, then the project-root ``.env`` file, then the
defaults below. Access them through the module-level ``settings`` object (or ``get_settings()``
for dependency injection and tests).
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[3]  # project root (contains data/, backend/, ...)


# Example values from .env.example: never accepted in production.
PLACEHOLDER_SECRETS = frozenset({"ChangeMe-Now-123", "change-me"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- application -------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Insert the demo equipment and work orders from data/sample on startup. Set false for real data.
    seed_sample_data: bool = False  # sample machines are opt-in; by default every number comes from your own data
    auto_register_equipment: bool = True  # a PDF upload also adds the machine it describes to the equipment registry
    log_format: Literal["text", "json"] = "text"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000"

    # --- sign-in -----------------------------------------------------------
    # Set AUTH_ENABLED=false only for a private local demo (everybody then acts as an administrator).
    auth_enabled: bool = True
    # True: every restart of the backend signs everybody out, so the login page always appears first after starting.
    login_on_start: bool = True
    # The first administrator: created automatically on start-up when no user exists yet. More users are added in the app.
    admin_email: str = "admin@forgemind.local"
    admin_password: SecretStr = SecretStr("")  # password of that first administrator; never logged
    session_secret: SecretStr = SecretStr("")  # signs the session cookie; blank = random per start (sessions end on restart)
    session_hours: int = Field(default=12, ge=1, le=168)  # session length without "Remember me"
    remember_days: int = Field(default=30, ge=1, le=90)  # session length with "Remember me"

    # --- generation (Gemini) ----------------------------------------------
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"  # gemini-2.0-flash was shut down; see ai.google.dev/gemini-api/docs/deprecations
    gemini_timeout_seconds: int = Field(default=30, ge=5, le=120)  # per attempt
    gemini_max_retries: int = Field(default=2, ge=0, le=5)  # extra attempts on transient errors
    gemini_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    gemini_temperature: float = Field(default=0.1, ge=0.0, le=1.0)  # low: factual, repeatable answers
    max_context_chars: int = Field(default=12000, ge=1000, le=100000)  # retrieved text sent to the model

    # --- storage -----------------------------------------------------------
    database_url: str = Field(default=f"sqlite:///{ROOT_DIR / 'data' / 'forgemind.db'}", repr=False)  # may hold a password
    uploads_dir: Path = ROOT_DIR / "data" / "uploads"
    processed_dir: Path = ROOT_DIR / "data" / "processed"
    indexes_dir: Path = ROOT_DIR / "data" / "indexes"
    sample_dir: Path = ROOT_DIR / "data" / "sample"
    max_upload_mb: int = Field(default=25, ge=1, le=200)

    # --- retrieval ---------------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    enable_semantic_search: bool = False
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0)
    top_k: int = Field(default=4, ge=1, le=10)

    # --- validators --------------------------------------------------------
    @field_validator("log_level", "log_format", "app_env", mode="before")
    @classmethod
    def _normalise_case(cls, v, info):
        if not isinstance(v, str):
            return v
        return v.upper() if info.field_name == "log_level" else v.lower()

    @field_validator("api_prefix")
    @classmethod
    def _normalise_prefix(cls, v: str) -> str:
        v = v.strip().strip("/")
        return f"/{v}" if v else ""

    @model_validator(mode="after")
    def _cross_field_checks(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.app_env == "production" and "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must not contain '*' in production")
        if self.app_env == "production" and self.auth_enabled:
            password = self.admin_password.get_secret_value()
            secret = self.session_secret.get_secret_value()
            if len(password) < 12 or password in PLACEHOLDER_SECRETS:
                raise ValueError("ADMIN_PASSWORD must be set to a private value of at least 12 characters in production")
            if len(secret) < 32 or secret in PLACEHOLDER_SECRETS:
                raise ValueError("SESSION_SECRET must be set to a random value of at least 32 characters in production")
        return self

    # --- derived values ----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key.get_secret_value().strip())

    @property
    def safe_database_url(self) -> str:
        """Database URL with the password masked, safe to log."""
        return make_url(self.database_url).render_as_string(hide_password=True)

    def safe_summary(self) -> dict:
        """Configuration snapshot that is safe to log: no secrets, database password masked."""
        return {
            "environment": self.app_env,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "api_prefix": self.api_prefix,
            "cors_origins": self.cors_origin_list,
            "auth_enabled": self.auth_enabled,
            "login_on_start": self.login_on_start,
            "auto_register_equipment": self.auto_register_equipment,
            "admin_password_set": bool(self.admin_password.get_secret_value()),
            "database": self.safe_database_url,
            "gemini_model": self.gemini_model,
            "gemini_enabled": self.gemini_enabled,
            "gemini_timeout_seconds": self.gemini_timeout_seconds,
            "gemini_max_retries": self.gemini_max_retries,
            "semantic_search": self.enable_semantic_search,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k": self.top_k,
            "max_upload_mb": self.max_upload_mb,
        }

    def ensure_directories(self) -> None:
        for directory in (self.uploads_dir, self.processed_dir, self.indexes_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
settings.ensure_directories()