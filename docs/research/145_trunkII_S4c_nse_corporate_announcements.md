# research/145 — Trunk II SENSES · S4c: NSE corporate-announcement filings (fastest-free filings)

**Slice:** S4c of S4-advanced (research/143). The highest-SIGNAL news for trading: official exchange
filings (board-meeting outcomes, results, dividends, director changes, orders) — polled seconds after
they post, straight from NSE's own JSON backend. Feeds the same store → S2 extraction → (queued) S7 gate.

## Sourcing (research/143 Agent C) + the decision
Agent C's verdict: NSE/BSE announcements are the **fastest realistic FREE** filings source — the
unofficial libs (`NseIndiaApi`, `BseIndiaApi`) work by hitting the exchange's own JSON backend
(seconds after filing), needing a session-cookie handshake + browser headers + ~3 req/s self-throttle.
- **Decision: fetch the NSE JSON DIRECTLY with our S4b `curl_cffi` session, NOT the `nse` PyPI lib.**
  Rationale (Rule I — acquire what fits, don't just take what's handy): direct fetch reuses our
  already-verified Chrome-TLS ban-resistance, adds NO new dependency, gives full control of endpoint/
  headers, and — critically — I **real-tested it from THIS datacenter box and it works** (below),
  whereas the lib does its own `requests` calls that may be blocked from datacenter egress. The lib
  stays a backlog fallback if NSE ever changes the handshake in a way the lib tracks faster than we do.

## Empirical spike (Rule F, 2026-07-26) — it works from our egress
`curl_cffi` session: `GET nseindia.com/` (bootstrap 4 cookies) → `GET /api/corporate-announcements?
index=equities` (Referer set) → **HTTP 200, 20 records in 0.2 s**. Real filings returned. This is the
site Agent A worried might 403 like Business Standard — it does NOT (curl_cffi's Chrome handshake
clears NSE's bot wall; NSE is not behind Akamai-grade IP-reputation blocking for this endpoint).

Record shape (real, captured): `symbol` ("SMCGLOBAL"), `sm_name`, `desc` (subject — "Outcome of Board
Meeting"), `attchmntText` (detail), `attchmntFile` (full PDF URL on nsearchives), `an_dt` / `sort_date`
("2026-07-26 21:31:57", IST — real timestamp → freshness knowable), `sm_isin`, `seq_id`.

## STEP 1 — Target
`NseAnnouncementsSource.poll(now)` → fetch the announcements JSON → parse each record into a
`RawNewsItem` (title `"{symbol}: {desc}"`, summary `attchmntText`, url `attchmntFile`, published_at
`sort_date` IST→UTC, tier **EXCHANGE_FILING**) → same `FeedPollResult` → existing `NewsIngestionRunner`
→ dedup store. Success test (Rule F): real filings stored with correct symbol/subject/UTC timestamp;
re-poll delta ≈ 0 (dedup).

## STEP 2 — Parts (mostly reuse)
- session fetch (NEW, thin) — reuse S4b `curl_cffi`; a session variant (homepage bootstrap + api) ·
  record parser (NEW, pure) · RawNewsItem/FeedPollResult/freshness/store/runner (REUSE) · new tier
  `EXCHANGE_FILING` on `NewsSourceTier` (provenance for S3 reliability — filings get the highest prior).

## STEP 3 — Build / wiring
- `nse_announcements_source.py`: `fetch_nse_announcements(index)` (curl_cffi session, DI seam, [] on
  fail) + `parse_announcement_records(...)` (PURE, IST→UTC) + `NseAnnouncementsSource(indices, fetch_json)`
  `.poll()`. `EXCHANGE_FILING` added to `news_item_types.NewsSourceTier`.
- Live service: `_maybe_run_exchange_filings` (background thread — a hung NSE call must never stall the
  loop; ≤5 min) → runner → store; `exchange_filings` dashboard surface + manifest.
- Named consumer (Rule K): S7 entry-gate — a filing on a held/candidate symbol (results/board outcome)
  is a size-down/defer catalyst. Read-only until S7.

## STEP 4 — Verify
- Hermetic (Rule J): fake `fetch_json` returns canned real-shape records → assert parse (symbol/subject/
  UTC), tier=EXCHANGE_FILING, freshness, one bad index never breaks the poll.
- Real-data (Rule F): real NSE fetch from this box → real filings stored; re-poll delta ≈ 0.

## Rule K — queued after S4c
BSE announcements (`BseIndiaApi` endpoint — same shape, BSE-listed overlap) · S4d vision + residential
proxy (403 sites) · S3 source reliability (EXCHANGE_FILING = highest prior) · S7 entry-gate (PRIMARY).
NSE also exposes board-meetings + results-calendar + bulk/block deals endpoints — queued as more
filing sources once this base lands.
