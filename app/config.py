"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings.

    All values come from environment variables or a `.env` file. Never
    hardcode secrets in code or templates.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Telegram ───
    bot_token: str = Field(default="", description="Telegram bot token from @BotFather.")
    bot_mode: Literal["polling", "webhook"] = "polling"
    webhook_base_url: HttpUrl | None = None
    webhook_secret: str = ""

    # ─── Google Sheets ───
    google_sheet_url: str = ""
    google_credentials_file: Path = Path("google_key.json")

    # ─── Auth ───
    jwt_secret: str = Field(default="change-me-please-use-openssl-rand-hex-32")
    jwt_ttl_days: int = 7
    owner_ids: str = ""

    # ─── Web ───
    host: str = "0.0.0.0"
    port: int = 8000
    env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ─── Integrations ───
    nova_poshta_api_key: str = ""

    # ─── Cache ───
    sheets_cache_ttl_seconds: int = 30

    # ─── Derived ───
    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def owner_ids_list(self) -> list[str]:
        return [x.strip() for x in self.owner_ids.split(",") if x.strip()]

    @property
    def webhook_path(self) -> str:
        """Secret path Telegram should POST updates to."""
        if not self.webhook_secret:
            return "/telegram/webhook"
        return f"/telegram/webhook/{self.webhook_secret}"

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 16:
            # In dev we let weak secrets pass with a warning; production check
            # happens in `validate_for_production`.
            return v
        return v

    def validate_for_production(self) -> list[str]:
        """Return a list of misconfiguration errors, empty if OK."""
        errors: list[str] = []
        if not self.bot_token:
            errors.append("BOT_TOKEN is required")
        if not self.google_sheet_url:
            errors.append("GOOGLE_SHEET_URL is required")
        if (
            len(self.jwt_secret) < 32
            or self.jwt_secret == "change-me-please-use-openssl-rand-hex-32"
        ):
            errors.append("JWT_SECRET must be at least 32 random bytes in production")
        if self.bot_mode == "webhook" and not self.webhook_base_url:
            errors.append("WEBHOOK_BASE_URL is required when BOT_MODE=webhook")
        if self.bot_mode == "webhook" and not self.webhook_secret:
            errors.append("WEBHOOK_SECRET is required when BOT_MODE=webhook")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Wrapped in `lru_cache` so tests can monkeypatch env vars and call
    `get_settings.cache_clear()` between cases.
    """
    return Settings()
