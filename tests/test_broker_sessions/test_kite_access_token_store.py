from datetime import datetime
from pathlib import Path

from nse_algo_trader.broker_sessions import (
    KiteAccessTokenFileStore,
    KiteAccessTokenRecord,
)
from nse_algo_trader.broker_sessions.kite_access_token_store import (
    INDIA_MARKET_TIMEZONE,
)


def _ist_datetime(*args) -> datetime:
    return datetime(*args, tzinfo=INDIA_MARKET_TIMEZONE)


SAMPLE_TOKEN_RECORD = KiteAccessTokenRecord(
    access_token="fake_access_token_value",
    kite_user_id="HZV381",
    generated_at=_ist_datetime(2026, 7, 23, 8, 45),
)


class TestKiteAccessTokenExpiry:
    def test_morning_token_expires_next_day_6am_ist(self):
        assert SAMPLE_TOKEN_RECORD.expires_at() == _ist_datetime(2026, 7, 24, 6, 0)

    def test_post_midnight_token_expires_same_day_6am_ist(self):
        post_midnight_record = KiteAccessTokenRecord(
            access_token="t", kite_user_id="u",
            generated_at=_ist_datetime(2026, 7, 24, 1, 30),
        )
        assert post_midnight_record.expires_at() == _ist_datetime(2026, 7, 24, 6, 0)

    def test_validity_flips_exactly_at_expiry(self):
        assert SAMPLE_TOKEN_RECORD.is_still_valid(_ist_datetime(2026, 7, 24, 5, 59))
        assert not SAMPLE_TOKEN_RECORD.is_still_valid(_ist_datetime(2026, 7, 24, 6, 0))

    def test_repr_never_exposes_the_token(self):
        assert "fake_access_token_value" not in repr(SAMPLE_TOKEN_RECORD)


class TestKiteAccessTokenFileStore:
    def test_save_then_load_round_trips(self, tmp_path: Path):
        store = KiteAccessTokenFileStore(tmp_path / "kite_access_token.json")
        store.save(SAMPLE_TOKEN_RECORD)
        assert store.load() == SAMPLE_TOKEN_RECORD

    def test_saved_file_is_owner_only(self, tmp_path: Path):
        token_file_path = tmp_path / "kite_access_token.json"
        KiteAccessTokenFileStore(token_file_path).save(SAMPLE_TOKEN_RECORD)
        assert (token_file_path.stat().st_mode & 0o777) == 0o600

    def test_load_returns_none_when_never_saved(self, tmp_path: Path):
        assert KiteAccessTokenFileStore(tmp_path / "missing.json").load() is None

    def test_load_if_still_valid_rejects_expired_token(self, tmp_path: Path):
        store = KiteAccessTokenFileStore(tmp_path / "kite_access_token.json")
        store.save(SAMPLE_TOKEN_RECORD)
        assert store.load_if_still_valid(_ist_datetime(2026, 7, 24, 5, 0)) is not None
        assert store.load_if_still_valid(_ist_datetime(2026, 7, 24, 7, 0)) is None
