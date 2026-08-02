"""Hermetic tests for S5 Telegram social-tier ingestion (Trunk II SENSES, research/152).

The Bot API fetch is injected (DI seam) — canned getUpdates payloads, no network. Verifies SOCIAL
tagging, chat_id filtering, message/channel-post parsing, the disabled-no-credentials path, and that
a non-text update is ignored.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier
from nse_algo_trader.news_sentiment.telegram_credentials import TelegramCredentials
from nse_algo_trader.news_sentiment.telegram_news_source import (
    TelegramNewsSource,
    parse_telegram_updates,
)

NOW = datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc)
CREDS = TelegramCredentials(bot_token="tok", chat_id="6659010149")

UPDATES = [
    {"update_id": 1, "message": {"message_id": 10, "date": 1785000000,
                                 "chat": {"id": 6659010149}, "text": "NIFTY breakout alert above 24000"}},
    {"update_id": 2, "channel_post": {"message_id": 11, "date": 1785000100,
                                      "chat": {"id": 6659010149}, "text": "INFY looks weak on chart"}},
    {"update_id": 3, "message": {"message_id": 12, "date": 1785000200,
                                 "chat": {"id": 99999}, "text": "from a different chat — must be filtered"}},
    {"update_id": 4, "message": {"message_id": 13, "date": 1785000300,
                                 "chat": {"id": 6659010149}}},  # no text → ignored
]


def test_parses_social_items_filtered_to_chat():
    items = parse_telegram_updates(UPDATES, "6659010149", "telegram_x", "Telegram", fetched_at=NOW)
    assert len(items) == 2  # the other-chat + no-text updates are excluded
    assert all(i.tier == NewsSourceTier.SOCIAL.value for i in items)
    titles = {i.title for i in items}
    assert "NIFTY breakout alert above 24000" in titles
    assert "INFY looks weak on chart" in titles


def test_poll_uses_fetch_seam_and_tags_social():
    source = TelegramNewsSource(CREDS, fetch_updates=lambda token, limit=50: UPDATES)
    results = source.poll(NOW)
    assert results[0].is_usable
    assert len(results[0].items) == 2
    assert results[0].tier == NewsSourceTier.SOCIAL.value


def test_disabled_when_no_credentials():
    source = TelegramNewsSource(None)
    assert not source.is_enabled
    results = source.poll(NOW)
    assert not results[0].is_usable
    assert "disabled" in results[0].fetch_error


def test_empty_updates_flagged_not_silent():
    source = TelegramNewsSource(CREDS, fetch_updates=lambda token, limit=50: [])
    results = source.poll(NOW)
    assert not results[0].is_usable
    assert "no new telegram messages" in results[0].fetch_error
