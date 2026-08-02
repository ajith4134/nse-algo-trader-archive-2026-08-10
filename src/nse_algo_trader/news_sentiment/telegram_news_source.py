"""Telegram social-tier news ingestion (Trunk II SENSES S5; research/152).

Polls the configured bot's `getUpdates` and turns messages from the configured chat into `RawNewsItem`s
tagged tier SOCIAL — so S3 gives them a 0.25 reliability prior, BELOW the S7 gate's 0.5 floor: a social
tip is ADVISORY (early-warning), never moves a trade alone (the research/140 design). The network fetch
sits behind a `fetch_updates` DI seam (Rule J): production hits the Bot API with `requests`; tests inject
a fake. `parse_telegram_updates` is PURE. Absent credentials → the source is a disabled no-op.
"""

from __future__ import annotations

from datetime import datetime, UTC

from nse_algo_trader.news_sentiment.news_item_types import (
    FeedPollResult,
    NewsSourceTier,
    RawNewsItem,
)

_BOT_API = "https://api.telegram.org/bot{token}/getUpdates"
_FETCH_TIMEOUT_SECONDS = 20


def fetch_telegram_updates(token: str, limit: int = 50) -> list:
    """The real fetch seam: Bot API getUpdates → list[update dict]. [] on any failure."""
    try:
        import requests

        response = requests.get(_BOT_API.format(token=token), params={"limit": limit},
                                timeout=_FETCH_TIMEOUT_SECONDS)
        payload = response.json()
        return payload.get("result", []) if payload.get("ok") else []
    except Exception:
        return []


def _message_of(update: dict) -> dict | None:
    """A news-bearing message from an update: a DM/group message or a channel post."""
    return update.get("message") or update.get("channel_post") or None


def parse_telegram_updates(updates, chat_id: str, source_id: str, source_name: str,
                           fetched_at: datetime) -> tuple:
    """PURE: getUpdates results → tuple[RawNewsItem] (tier SOCIAL), filtered to `chat_id`."""
    items = []
    for update in updates:
        message = _message_of(update)
        if message is None:
            continue
        if str(message.get("chat", {}).get("id", "")) != str(chat_id):
            continue
        text = (message.get("text") or message.get("caption") or "").strip()
        if not text:
            continue
        title = text.splitlines()[0][:120]
        published_at = None
        if message.get("date"):
            published_at = datetime.fromtimestamp(int(message["date"]), tz=UTC)
        message_id = message.get("message_id", "")
        url = f"tg://message?chat={chat_id}&id={message_id}"
        items.append(RawNewsItem(
            source_id=source_id, source_name=source_name, tier=NewsSourceTier.SOCIAL.value,
            title=title, summary=text, url=url, published_at=published_at, fetched_at=fetched_at,
            content_hash=RawNewsItem.compute_content_hash(source_id, url, title)))
    return tuple(items)


class TelegramNewsSource:
    """Polls the bot and returns a `FeedPollResult` of SOCIAL items. Disabled (empty) when no creds.

    `fetch_updates` is the DI seam — defaults to the real Bot API getter; tests inject a fake."""

    def __init__(self, credentials, fetch_updates=fetch_telegram_updates):
        self._credentials = credentials
        self._fetch_updates = fetch_updates

    @property
    def is_enabled(self) -> bool:
        return self._credentials is not None

    def poll(self, now_utc: datetime) -> tuple:
        source_id = f"telegram_{self._credentials.chat_id}" if self._credentials else "telegram_disabled"
        source_name = "Telegram (social tier)"
        if not self.is_enabled:
            return (FeedPollResult(source_id, source_name, NewsSourceTier.SOCIAL.value, (), None,
                                   "telegram disabled (no credentials in env)"),)
        try:
            updates = self._fetch_updates(self._credentials.bot_token)
            items = parse_telegram_updates(updates, self._credentials.chat_id, source_id, source_name,
                                           fetched_at=now_utc)
            if not items:
                return (FeedPollResult(source_id, source_name, NewsSourceTier.SOCIAL.value, (), None,
                                       "no new telegram messages this poll"),)
            # Social items have no reliable per-item staleness need — treat as fresh (advisory anyway).
            from nse_algo_trader.news_sentiment.news_item_types import FeedFreshness
            freshness = FeedFreshness(source_id, 0.0, is_stale=False, reason="social — advisory tier")
            return (FeedPollResult(source_id, source_name, NewsSourceTier.SOCIAL.value, items, freshness, ""),)
        except Exception as fetch_error:
            return (FeedPollResult(source_id, source_name, NewsSourceTier.SOCIAL.value, (), None,
                                   str(fetch_error)[:200]),)
