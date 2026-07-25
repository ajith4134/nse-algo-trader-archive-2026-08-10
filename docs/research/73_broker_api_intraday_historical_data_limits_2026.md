# Broker API Intraday Historical Data Limits — NSE Cash + F&O with OI (2026-07-25)

Research method: parallel WebSearch + WebFetch of primary sources (official docs, official GitHub
SDK repos/issues, official pricing/FAQ pages, official developer forums) per broker. Some sub-agents
exhausted their WebSearch quota partway through and fell back to WebFetch-only (direct fetch + the
`r.jina.ai` reader proxy for JS-rendered SPA doc sites); this is noted per broker below. All numbers
are the broker's own documented text, quoted verbatim where possible — not memory/estimate.

## Summary table

| Broker | 1-min max lookback | 1-sec support | F&O + OI | Cost | Doc URL |
|---|---|---|---|---|---|
| **ICICI Breeze** | ~3 years (uniform across all intervals per ICICI FAQ; 1000-row/request cap is the real bottleneck) | Yes, `interval="1second"` in `get_historical_data_v2` | Yes, OI field confirmed to 1-min; 1-sec OI unconfirmed | Free (ICICIdirect account) | api.icicidirect.com/breezeapi/documents; github.com/Idirect-Tech/Breeze-Python-SDK |
| **Zerodha Kite Connect** | 60 days/request (page for more; day data goes back to ~1990s-2015 depending on segment) | No | Yes (`oi=1` param), but **no data for expired F&O contracts** | ₹500/month per API key (cut from ₹2000 in May 2025; order/portfolio APIs free since Mar 2025) | kite.trade/docs/connect/v3/historical |
| **Upstox v3** | 1 month/request (data from Jan 2022) | No | Yes, OI embedded in candle array; **expired contracts gated behind paid "Upstox Plus"** | Free (API subscription); execution brokerage promo separately, status unclear as of Jul 2026 | upstox.com/developer/api-documentation/v3/get-historical-candle-data |
| **Angel One SmartAPI** | **30 days/request** (NOT 2000 days — that figure is for ONE_DAY) | No | Yes, but via separate `getOIData` endpoint, not embedded in candles; **no expired-contract data, free or paid** | Free, no subscription fee found anywhere | smartapi.angelbroking.com/docs/Historical |
| **Dhan (DhanHQ)** | 90 days/request, **5 years total archive** | No | Yes, `oi` field on intraday/historical candle endpoint | Free, no tier | dhanhq.co/docs/v2/historical-data |
| **Fyers** | 100 days/request, **archive since 3 Jul 2017** (~9 yrs) | Yes, but only rolling **last 30 trading days** | Yes, `oi_flag=1` on same History endpoint (NFO/BFO/MCX/CDS only) | Free ("Standard" tier); paid "Prime" only raises rate limits | myapi.fyers.in/docsv3 (live OpenAPI spec) |
| **Finvasia Shoonya** | Undocumented — no max-lookback number found in any reachable source | Unknown | Yes (`get_option_chain`, `oi`/`poi` fields) | Claimed "100% free," FAQ/pricing page unreachable (403) to confirm | github.com/Shoonya-Dev/ShoonyaApi-py; shoonya.com/api (docs SPA didn't render) |
| **Alice Blue ANT** | 2 years (NSE cash); **F&O/CDS/MCX = current expiry only** | No | F&O yes, OI not confirmed | Unconfirmed (docs domain returned HTTP 402) | quoted via PyPI `alice-blue` wrapper page, official domain blocked |
| **Motilal Oswal** | Undocumented | Unknown | Unconfirmed | "Free API Access" (marketing page only) | invest.motilaloswal.com/moAPI (technical docs portal unreachable) |
| **5paisa (Xstream)** | 6 months/interval window (ambiguous: per-chunk or ceiling) | No | Yes, OI confirmed via websocket in `py5paisa` SDK (freshest SDK release, Aug 2025) | ₹0 stated on pricing page | xstream.5paisa.com/dev-docs/market-data-system/historical-candles |
| **IIFL** | No public developer/algo API found at all | — | — | — | none found; likely institutional-only/discontinued for retail |

## Key corrections to prior assumptions
- **Kite Connect is not free** — ₹500/month per API key as of the May 2025 price cut (previously ₹2000/month; order/portfolio-only APIs are free since March 2025).
- **Angel One's "2000 days" figure applies to the ONE_DAY interval, not ONE_MINUTE.** ONE_MINUTE is capped at 30 days per request — worse than Dhan or Fyers for 1-minute data, contrary to common assumption.
- **Zerodha and Upstox (free tier) do not retain data for expired F&O contracts** — a major gap for options backtesting that ICICI Breeze and Dhan do not appear to share (both retain history within their stated window regardless of expiry).
- **Fyers has the deepest confirmed 1-minute archive with F&O+OI, entirely free**: since 3 July 2017 (~9 years), 100-day pagination chunks, `oi_flag=1` covers NSE derivatives directly on the same endpoint. This is the strongest all-around free option for 1-minute-and-coarser cash+F&O+OI history.
- **ICICI Breeze remains the only broker offering documented 1-second granularity with F&O+OI**, at a genuinely free, ~3-year window — but this headline number is undermined in practice by a hard 1000-candles-per-request cap (a 3-year clean 1-second pull is a huge number of paginated calls) plus multiple 2024 GitHub Issues / TradingQnA reports of empty responses, duplicate rows, and conflicting OHLC specifically on `get_historical_data_v2`/1-second interval. Treat the 3-year figure as documented-but-not-independently-verified-as-cleanly-achievable.

## Bottom line — which ONE broker wins
- **Deepest free 1-minute (or coarser) NSE cash+F&O+OI history, most reliably: Fyers** (~9-year archive, native OI flag, free Standard tier, no expired-contract-history exclusion found in docs).
- **Only broker with documented (if imperfectly verified) 1-second granularity: ICICI Breeze**, free, ~3 years, but flagged for real-world data-quality and pagination-throughput caveats.
- If the project needs 1-second bars specifically, Breeze is the only legitimate option investigated; if 1-minute is sufficient and reliability/OI-cleanliness matters more than raw interval fineness, Fyers is the stronger pick.

## Gaps / open items not resolved in this pass
- Finvasia Shoonya's actual max lookback for 1-minute data — docs SPA never rendered, FAQ blocked (403). Needs a follow-up with browser-based fetch or direct account testing.
- Whether ICICI Breeze's `get_historical_data_v2` 1-second OI field is populated with real (non-null/placeholder) values for options — no doc or example confirms this.
- Zerodha Kite Connect's request-rate limits (req/sec) were not verified against a primary source in this pass.
- Upstox Plus (paid tier unlocking expired-contract history) has no published price anywhere; account-level check needed.
- The open-ended "any other free Indian broker/data vendor" sweep (beyond the 11 named above) could not be completed — the sub-agent covering it exhausted its WebSearch quota before running the broad discovery queries. Alice Blue, Motilal Oswal, and IIFL docs were also largely unreachable (HTTP 402/404) — their entries above are the best available secondary evidence, not primary-source-confirmed.
- Per Rule K (no silent skips): these gaps should be tracked in `docs/BACKLOG.md` if the project intends to act on Shoonya, Alice Blue, or the broader "any other broker" sweep later.
