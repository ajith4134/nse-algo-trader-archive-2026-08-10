"""Telegram bot credentials, loaded from the environment only (Trunk II SENSES S5; research/152).

The token + chat_id live in gitignored `.env` (`NSE_TELEGRAM_BOT_TOKEN` / `NSE_TELEGRAM_CHAT_ID`) —
NEVER hardcoded (project non-negotiable: secrets from env/secret-store only). `load_telegram_credentials`
returns None when they're absent, so the whole Telegram source disables cleanly (no crash, no orphan).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_TOKEN_ENV = "NSE_TELEGRAM_BOT_TOKEN"
_CHAT_ID_ENV = "NSE_TELEGRAM_CHAT_ID"


@dataclass(frozen=True)
class TelegramCredentials:
    bot_token: str
    chat_id: str


def load_telegram_credentials(env: Mapping[str, str] | None = None) -> TelegramCredentials | None:
    """Read the bot token + chat_id from env (loading .env first). None when either is unset."""
    source: Mapping[str, str]
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass
        source = os.environ
    else:
        source = env
    token = (source.get(_TOKEN_ENV) or "").strip()
    chat_id = (source.get(_CHAT_ID_ENV) or "").strip()
    if not token or not chat_id:
        return None
    return TelegramCredentials(bot_token=token, chat_id=chat_id)
