# Live multi-broker option-chain feed (index options first)

**User priority:** the index-option bot must trade TODAY'S real option chain (live CE/PE, this-week expiry,
live LTP/OI) for all indices — the bot currently runs on a STALE stored bhavcopy snapshot (2026-06-15,
NIFTY@23,853, June expiry), so it can never trade the live options the user sees. Scope: 5 NSE indices
(NFO) + SENSEX/BANKEX (BFO — user authorized beyond phase-1). Multi-broker: use all brokers with creds
(Kite, Upstox, Angel One, ICICI Breeze, Groww) with failover.

## Feasibility (verified live)
Kite `instruments("NFO")` / `("BFO")` return every option contract (tradingsymbol, name, expiry, strike,
CE/PE, lot_size, instrument_token); `kite.ltp/quote(...)` return live LTP + OI. Verified: NIFTY expiry
2026-08-04, 226 strikes, live LTPs (24600 CE ₹7.9 / PE ₹117.75); SENSEX BFO 2722 contracts.

## Engine
`market_data/live_option_chain_source.py`:
- `LiveOptionChainSource` (Protocol) — `option_chain(underlying) -> (chain_df, trade_date, spot)` in the
  SAME shape the bots consume (columns: option_right_code, strike_price, close_price, underlying_price,
  expiry_date, open_interest, total_traded_volume).
- `KiteLiveOptionChainSource` (first provider — active session, full NFO+BFO coverage): cache the NFO/BFO
  instrument dump (per day) via the broker seam; for an underlying pick the nearest non-expired expiry;
  center a strike WINDOW around the live index spot (Kite ltp of the index); batch-`quote` the CE+PE legs in
  that window; assemble the chain DataFrame + trade_date=today + underlying_price=spot.
- `MultiBrokerLiveOptionChainSource` — tries providers in reliability order, first non-empty chain wins
  (failover). Providers: Kite now; Upstox / Angel / Breeze / Groww are ADDITIONAL providers to implement
  (Rule K queued — each has a different option API; Kite's coverage is complete so the feed works now).
- Kite-decoupled: the live fetch lives behind the `broker_sessions` seam; the ANALYSIS adapter calls the
  source, which caches the chain per (underlying, minute) so a cycle burst is one fetch. If no session →
  returns empty → the adapter falls back to the stored bhavcopy (never crashes, Rule J).

## Wiring
`MarketStoreOptionAdapter` gains an optional `live_chain_source`. `option_chain`, `nearest_expiry`,
`implied_atm_vol`, and the price/spot path prefer the LIVE chain when present, else the stored one. The
index bot passes a `MultiBrokerLiveOptionChainSource` when built by the pod (prod), none in tests (Rule J
seam). IV per strike is computed downstream by the existing IV-surface engine (BSM inversion) — the feed
supplies LTP+OI+strike+expiry+spot, not IV.

## Depth justification
Not a scalar: a real ingestion pipeline (instrument-master resolution → ATM-centered strike selection →
batched live-quote fetch → chain assembly in the canonical schema), carried cached state, multi-provider
failover, and it changes EVERY option decision (the bot now sees real strikes/prices/expiry). SOTA analog:
a broker market-data adapter (NautilusTrader's data client) feeding the strategy.

## Verification (Rule F, market LIVE)
Fetch the live chain for each index; confirm today's expiry, ATM strike ≈ live spot, non-zero CE/PE LTP+OI;
run the index bot on the live chain and confirm it proposes structures on REAL strikes; eyeball a few LTPs
vs the broker app. Hermetic test (Rule J): a fake `LiveOptionChainSource` returns a trimmed real-shaped
chain → adapter prefers it → bot builds on it, never touching kiteconnect in tests.

## Sourcing (Rule I)
Integrate the `kiteconnect` SDK (already a dependency) for instruments+quotes — the option-chain assembly
(ATM window, schema mapping) is bespoke glue. Upstox/Angel/Breeze/Groww SDKs already present as deps for
their historical-bar sources; their option-chain methods are the queued providers.

## Backlog (Rule K)
- Additional providers (Upstox/Angel/Breeze/Groww option chains) for true multi-broker failover.
- Live order PLACEMENT on the real chain (still paper today) — separate from the data feed.
- BANKEX (BFO) alongside SENSEX; strike-window width auto-calibrated to the index.
