"""Persists the daily ICICI Breeze session token to a gitignored file with expiry.

Unlike Kite (TOTP auto-login), Breeze has NO headless login — the session token
comes from a manual browser login and expires 24h after generation OR at midnight
IST, whichever comes first (research/66). This store records the generation moment
and answers "is this token still usable right now?" so consumers never guess, and
the always-on service can tell when it needs a fresh manual token.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

DEFAULT_BREEZE_SESSION_TOKEN_FILE_PATH = Path(
    "~/.nse_algo_trader/breeze_session_token.json"
).expanduser()


@dataclass(frozen=True)
class BreezeSessionTokenRecord:
    session_token: str
    generated_at: datetime  # timezone-aware, IST

    def __repr__(self) -> str:  # the token is a secret; never leak it
        return (
            f"BreezeSessionTokenRecord(session_token='***', "
            f"generated_at={self.generated_at!r})"
        )

    def expires_at(self) -> datetime:
        """24h after generation OR the next IST midnight — whichever is first."""
        generated_ist = self.generated_at.astimezone(INDIA_MARKET_TIMEZONE)
        next_midnight = datetime.combine(
            generated_ist.date() + timedelta(days=1), time(0, 0), INDIA_MARKET_TIMEZONE
        )
        twenty_four_hours = generated_ist + timedelta(hours=24)
        return min(next_midnight, twenty_four_hours)

    def is_still_valid(self, now: datetime | None = None) -> bool:
        now_ist = (now or datetime.now(INDIA_MARKET_TIMEZONE)).astimezone(
            INDIA_MARKET_TIMEZONE
        )
        return now_ist < self.expires_at()


class BreezeSessionTokenFileStore:
    def __init__(
        self, token_file_path: Path = DEFAULT_BREEZE_SESSION_TOKEN_FILE_PATH
    ) -> None:
        self._token_file_path = token_file_path

    def save(self, token_record: BreezeSessionTokenRecord) -> None:
        self._token_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_file_path.write_text(
            json.dumps(
                {
                    "session_token": token_record.session_token,
                    "generated_at": token_record.generated_at.isoformat(),
                }
            )
        )
        os.chmod(self._token_file_path, 0o600)  # owner-only: it's a secret

    def load(self) -> BreezeSessionTokenRecord | None:
        if not self._token_file_path.exists():
            return None
        stored_fields = json.loads(self._token_file_path.read_text())
        return BreezeSessionTokenRecord(
            session_token=stored_fields["session_token"],
            generated_at=datetime.fromisoformat(stored_fields["generated_at"]),
        )

    def load_if_still_valid(
        self, now: datetime | None = None
    ) -> BreezeSessionTokenRecord | None:
        token_record = self.load()
        if token_record is None or not token_record.is_still_valid(now):
            return None
        return token_record
