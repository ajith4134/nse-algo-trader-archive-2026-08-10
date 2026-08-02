# research/152 — Trunk II SENSES · S5: Telegram social-tier news ingestion

**Slice:** S5 — the tier-3 SOCIAL source (research/140). Ingest messages from the user's Telegram bot
(`TradindAlert_bot`) into the news store as `EXCHANGE_FILING`? NO — as **tier SOCIAL** (advisory-until-
proven): S3 gives SOCIAL a 0.25 reliability prior, BELOW the S7 gate's 0.5 floor, so a social item can
NEVER move the gate alone — exactly the design's "early-warning, can't act alone". Fastest-free relay
(research/143 Agent C: Telegram often beats RSS-indexed sites).

## Sourcing (Rule I) — libraries evaluated
- **`python-telegram-bot`** (PyPI, 26k★) — full async bot framework (handlers, job queue, conversation
  state). REJECTED: overkill for read-only `getUpdates` polling; pulls an async runtime we don't need.
- **`Telethon` / `Pyrogram`** (MTProto user-client libs) — REJECTED: they act as a full user account
  (needs api_id/api_hash + phone login), heavier + more intrusive than a bot token needs.
- **Plain `requests` on the Bot API HTTPS JSON endpoint** — CHOSEN: `requests` is already a dep; the
  Bot API is a documented REST endpoint. **Real-verified NOW:** `getMe` → ok (bot `TradindAlert_bot`),
  `getUpdates` → ok (0 messages queued — poll mechanism works; content arrives as messages hit the bot).
  Source-tier selection (Telegram = fastest free relay) inherited from research/143 Agent C.
Creds are in gitignored `.env` (`NSE_TELEGRAM_BOT_TOKEN` / `NSE_TELEGRAM_CHAT_ID`) — NEVER hardcoded.

## STEP 1 — Target
`TelegramNewsSource.poll(now)` → `getUpdates` → parse messages from the configured chat_id into
`RawNewsItem`s (tier SOCIAL, source_id `telegram_<chat>`) → store (dedup by content_hash) → flow through
S2/sentiment/S3/S7 like any item, but reliability-floored out of the gate (advisory).
- **Success test:** the API is reachable (getMe ok — verified); a fake `getUpdates` payload parses to a
  SOCIAL RawNewsItem with the message text/timestamp; when the bot HAS messages, they ingest + store.

## STEP 2 — Build / wiring
- `telegram_news_source.py`: `fetch_telegram_updates(token)` (Bot API getUpdates, DI seam) +
  `parse_telegram_updates(updates, chat_id, now)` (PURE → RawNewsItems, filtered to the chat_id) +
  `TelegramNewsSource(token, chat_id, fetch_updates)` `.poll()`. Absent creds → disabled no-op (safe).
- `telegram_credentials.py`: read token/chat_id from env (dotenv) → `TelegramCredentials | None`.
- Service: `_maybe_run_telegram_ingestion` (≤5 min) → `NewsIngestionRunner` → store; `telegram_news`
  dashboard surface + manifest. Disabled cleanly when creds absent.

## STEP 3 — Verify
- Hermetic (Rule J): fake getUpdates → SOCIAL items parsed, chat_id filter, non-message updates ignored.
- Real (Rule F): getMe reachability ✅ (done). **Live message ingestion is an OPEN item until the bot
  actually receives messages** (user adds it to a news channel / sends it messages) — honest blocker,
  not a fake pass. The SOCIAL tier means even then it stays advisory (S3-gated).

## Rule K — after S5
Live-message real-data pass (needs messages in the bot's feed) · misinformation/pump flag for the
SOCIAL tier (reuse XIII, research/140) · per-channel reputation once messages resolve.
