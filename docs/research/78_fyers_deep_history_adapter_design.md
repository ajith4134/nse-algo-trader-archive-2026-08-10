# Research/78 — Fyers deep-history HistoricalBarSource adapter (design)

**Rule D design doc**, grounded in the Fyers API-shape sourcing (2026-07-25, source
read directly from the `fyers-apiv3` 3.1.14 wheel + official FyersDev `fyers-skills`
docs). Adds Fyers as a **deep, free minute-history** source (cash + F&O + OI, since
**3-Jul-2017 ~9y**) — deeper than Breeze's ~3y and free (research/77 top win, task #11).

## Sourcing facts that shape the design
- **SDK:** `fyers-apiv3` (MIT). ⚠ **hard-pinned deps** (`requests==2.31.0`,
  `aiohttp==3.9.3`, `aws_lambda_powertools==1.25.5`) that can collide with the
  project's pins. **Do NOT add to the main env now.** The adapter takes an INJECTED
  `FyersModel`-shaped client and NEVER imports `fyers_apiv3`, so the adapter +
  hermetic tests need no install; install (isolated) only for the real-data pass.
- **Import/construction hermetic:** `import fyers_apiv3` = zero I/O; `FyersModel()`
  = no network (only opens `fyersApi.log`/`fyersRequests.log` under `log_path` — a
  cwd gotcha for real use, irrelevant to the injected-fake adapter).
- **History call:** `fyers.history(data={symbol, resolution, date_format:"0",
  range_from, range_to (epoch s), cont_flag, oi_flag:"1"})` →
  `{"s":"ok","candles":[[epoch,o,h,l,c,v(,oi)]]}`.
- **Resolutions:** seconds `5S…45S` (NO 1s!), minutes `1,2,3,5,10,15,20,30,60,120,240`,
  `D`/`1W`/`1M`. ⇒ **Fyers has NO 1-second** — it is the deep MINUTE source; Breeze
  stays the 1-second source. Map our `BarInterval` minute/day values; `SECOND_1` →
  unsupported (raise, like Kite).
- **Per-call range caps → chunking:** minute ≤ **100 days**/call; daily/weekly/monthly
  ≤ **366 days**; seconds ≤ 30 trading days. Rate limit 10/s · 200/min · 100k/day
  (every history call counts).
- **Symbols:** cash `NSE:{SYMBOL}-EQ`; options `NSE:{UNDER}{YY}{MMM}{STRIKE}{CE|PE}`
  (monthly) / weekly single-letter month code. Master at `public.fyers.in/sym_details/`.
- **Auth:** manual daily browser login (no official headless) → daily `access_token`;
  creds = `client_id` (`XXXXXXXXX-100`), `secret_key`, `redirect_uri`.

## The build (task #11)
`market_data/fyers_historical_bar_source.py`: `FyersHistoricalBarSource(
authenticated_fyers_client, fyers_symbol_resolver=default_fyers_symbol)` implements
`HistoricalBarSource.fetch_historical_bars`:
- `FYERS_RESOLUTION_BY_BAR_INTERVAL` (minute+day subset; `SECOND_1`→ValueError).
- `default_fyers_symbol(instrument)` → cash `NSE:{sym}-EQ`; **options raise** a clear
  error pointing to the symbol-master resolver (options-symbol formatting is fiddly —
  monthly vs weekly month codes — and needs the master; tracked as a follow-up so we
  don't ship a wrong format). Injectable resolver seam for the master-backed version.
- Chunk `[from,to]` into ≤100-day (minute) / ≤366-day (day) windows (epoch seconds),
  dedupe by timestamp, parse `candles` → `PriceBar` (timestamp = epoch→IST-aware;
  `oi_flag="1"`, OI from row[6] when present). Empty/`s!="ok"` → [] (best-effort).

## Wiring (Rule G)
Implements the SAME `HistoricalBarSource` seam Kite/Breeze do, so it plugs directly
into the existing `build_replay_bars_by_token_from_source` (P4a-wire) — i.e. a deep
minute-history replay/backfill is one call away, no new plumbing. Named consumer: the
replay-feed builder + a future deep-backfill job.

## Verification
- **Hermetic (Rule J):** injected fake `FyersModel` returning real-shaped
  `{"s":"ok","candles":[...]}` — resolution map, cash symbol formatting, chunk
  windows (≤100d minute) + dedupe, OHLCV+OI parse, `SECOND_1`/options errors, empty
  envelope. No `fyers_apiv3` install needed.
- **Real data (Rule F) — OPEN BLOCKER:** needs the user's Fyers creds + a daily
  token, and an ISOLATED `fyers-apiv3` install (dep pins). Then pull real minute bars
  for RELIANCE over a multi-year range and assert non-empty/ordered/OHLC-sane.

## Backlog (Rule K)
- Fyers **options symbol-master resolver** (monthly/weekly formatting from
  `public.fyers.in/sym_details/NSE_FO`) — follow-up.
- Fyers **session/token store** (like Breeze #6a) + isolated dependency install —
  needed for the real-data pass + autonomous use.
