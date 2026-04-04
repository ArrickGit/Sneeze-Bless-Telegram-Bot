from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    bot_token: str
    mongodb_uri: str
    database_name: str
    bot_mode: str
    webhook_base_url: str | None
    webhook_path: str
    webhook_secret: str | None
    default_unbless_penalty: int
    scoreboard_limit: int
    log_level: str

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url:
            raise RuntimeError("WEBHOOK_BASE_URL is required when BOT_MODE=webhook")
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"

    @classmethod
    def from_env(cls) -> "Settings":
        bot_mode = os.getenv("BOT_MODE", "polling").strip().lower() or "polling"
        webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip() or None
        webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
        webhook_path = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook"

        if not webhook_path.startswith("/"):
            webhook_path = f"/{webhook_path}"

        settings = cls(
            bot_token=_require_env("BOT_TOKEN"),
            mongodb_uri=_require_env("MONGODB_URI"),
            database_name=os.getenv("DATABASE_NAME", "blessyou_bot").strip() or "blessyou_bot",
            bot_mode=bot_mode,
            webhook_base_url=webhook_base_url,
            webhook_path=webhook_path,
            webhook_secret=webhook_secret,
            default_unbless_penalty=_int_env("DEFAULT_UNBLESS_PENALTY", 1),
            scoreboard_limit=_int_env("SCOREBOARD_LIMIT", 10),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )

        if settings.bot_mode not in {"polling", "webhook"}:
            raise RuntimeError("BOT_MODE must be either 'polling' or 'webhook'")

        if settings.bot_mode == "webhook" and not settings.webhook_base_url:
            raise RuntimeError("WEBHOOK_BASE_URL is required when BOT_MODE=webhook")

        if settings.default_unbless_penalty < 1:
            raise RuntimeError("DEFAULT_UNBLESS_PENALTY must be at least 1")

        if settings.scoreboard_limit < 1:
            raise RuntimeError("SCOREBOARD_LIMIT must be at least 1")

        return settings
