# research/148 — Trunk II SENSES · stock symbol↔name gazetteer + headline symbol-matching

**Slice:** the first half of "stock-option S/R" (task #2), delivered as a clean unit that WIRES NOW:
resolve company names in headlines → NSE F&O symbols, and feed those matches into the S7 news-event
gate so **headlines (not just "SYMBOL:" filings) contribute event risk**. This is a real coverage
upgrade to the just-built S7 + the foundation the fuller stock-S/R level extractor needs next.

## Sourcing (Rule I) — acquire the gazetteer, don't compromise
The name→symbol map is not in the repo offline. Two real sources, both verified reachable NOW:
- **NSE official equity master** `EQUITY_L.csv` — fetched via our working curl_cffi NSE session:
  **HTTP 200, 2,387 rows, header `SYMBOL,NAME OF COMPANY,…`**; e.g. `INDIGO,InterGlobe Aviation Limited`.
  This is the authoritative SYMBOL↔company-name map (Rule I acquisition).
- **F&O underlying set** — the **216 distinct `underlying_symbol`** already stored in
  `market_data.sqlite3::fo_bhavcopy_contracts` (matches CLAUDE.md's 215 option underlyings; INDIGO/
  HINDPETRO present). Bounds the gazetteer to the TRADABLE universe (Rule L) → precision + relevance.
No OSS library needed — this is data acquisition + a bespoke normalizer/matcher (spaCy NER rejected in
research/143 as too heavy; exact + normalized-name matching is higher-precision for a finite gazetteer).

## STEP 1 — Target
`SymbolGazetteer.match_symbols(text) -> set[str]` — the F&O symbols a headline mentions, by exact
ticker token OR full normalized company-name phrase. Fed into S7's `build_news_event_risk_by_symbol`.
- **Success test (Rule F):** the gazetteer resolves "InterGlobe Aviation" → INDIGO from the REAL equity
  master, and real stored stock headlines ("Buy InterGlobe Aviation; target of Rs 6580: Motilal Oswal")
  now attribute event risk to INDIGO — coverage S7 didn't have (filings only).

## STEP 2 — Build / wiring
- `nse_symbol_gazetteer.py`: `fetch_nse_equity_master(fetch_csv)` (curl_cffi session, DI seam) →
  [(symbol, name)]; `build_symbol_gazetteer(rows, restrict_symbols)` → normalized-name→symbol +
  ticker set (F&O-bounded); `SymbolGazetteer.match_symbols(text)`. Persist rows to
  `~/.nse_algo_trader/nse_equity_master.json` (fetch ≤ daily; DI seam keeps prod/tests separate).
- **Precision guards:** normalize (lowercase, strip Ltd/Limited/The/punctuation); match a company only
  by its FULL normalized name as a phrase (high precision) OR its exact uppercase ticker as a whole
  word; drop names shorter than a floor. Longest-name-first so "Bajaj Finance" beats "Bajaj".
- Wire: `build_news_event_risk_by_symbol(..., gazetteer=None)` — items without a "SYMBOL:" prefix get
  their symbols from `gazetteer.match_symbols(title)`. Service builds the gazetteer (cached, F&O-bounded
  from the bhavcopy set) and passes it to `_maybe_run_news_entry_gate`; `stock_symbol_gazetteer` surface.

## STEP 3 — Verify
- Hermetic (Rule J): fake equity-master rows → gazetteer resolves names/tickers; false-positive guards
  (short/generic tokens don't match); headline → correct symbol set.
- Real-data (Rule F): real EQUITY_L.csv fetch → INDIGO etc.; real store headlines → F&O symbols;
  S7 event-risk now covers headline-mentioned stocks, not just filing symbols.

## Rule K — after this slice (still task #2's remainder)
Stock-S/R LEVEL extraction (the analyst-target/support numbers per stock — "target of Rs 6580") using
this gazetteer + a per-stock plausibility approach (require a level/target keyword + the ₹/Rs cue, since
stock prices span ₹10–₹100k so a global band can't gate) → a `news_levels`-style stock board. Then the
S2 index S/R-level proximity gate for index-option entries. changedetection/BSE items unchanged.
