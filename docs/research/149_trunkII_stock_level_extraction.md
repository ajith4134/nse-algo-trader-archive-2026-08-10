# research/149 — Trunk II SENSES · stock-S/R level extraction (completes task #2)

**Slice:** the remainder of task #2 — extract per-STOCK price levels (analyst targets / support /
resistance) from headlines, reusing the research/148 gazetteer for symbol resolution. Completes S2's
S/R extraction from index-only to the ~211 F&O stock underlyings (Rule L full universe).

## Sourcing (Rule I) — reuse in-house pieces (no new OSS)
Same verdict as S2 (research/142): no OSS extracts analyst-quoted levels from Indian headlines. Reuses:
the S2 `ExtractedLevel`/`ExtractedLevelSet`/`LevelKind` types + `news_levels` store table +
the research/148 `SymbolGazetteer` (name→F&O-symbol). Bespoke stdlib `re`. spaCy NER already rejected.

## The precision problem for stocks (vs indices)
Index levels used a `[5k–100k]` band; stock prices span ₹10–₹100k so a global band can't gate. The
precision comes instead from **requiring a matched stock name/ticker AND a strong money/target cue**:
- `target of Rs N` / `target Rs N` / `target price of N` → **TARGET** (analyst upside)
- `support at Rs N` / `support of N` → **SUPPORT** · `resistance at Rs N` → **RESISTANCE**
- `₹N` / `Rs N` adjacent to a support/resistance/target word → that kind
A number with a money/target cue AND a resolved F&O symbol in the same headline is a stock level;
anything else is ignored (high precision). New `LevelKind.TARGET` for analyst price targets.

## STEP 1 — Target
`extract_stock_level_sets(item, gazetteer) -> list[ExtractedLevelSet]` — resolve the headline's F&O
symbol(s) via the gazetteer, find the money/target-cued number, emit an `ExtractedLevelSet`
(underlying = the stock symbol, kind TARGET/SUPPORT/RESISTANCE). Stored in the SAME `news_levels`
table as the index levels (underlying is already a free string there).
- **Success test (Rule F):** real stored headlines → `INDIGO TARGET 6580`, `SRF TARGET 3200`,
  `VMM TARGET 165`, `UNITDSPR TARGET 1525` (all from real "Buy X; target of Rs N: Motilal Oswal" lines).

## STEP 2 — Build / wiring
- `stock_level_extraction.py` (PURE): the extractor above (money/target-cue regex + gazetteer symbol
  resolution + kind classification). Reuses S2 types.
- Runner extension: a cadence `_maybe_run_stock_level_extraction` builds the gazetteer + runs the
  extractor over recent stored items → `save_extracted_levels` (same store method). `stock_levels`
  dashboard surface + manifest.
- Consumer: the S2 index levels already feed the (future) index-option S/R gate; stock levels are the
  stock-entry S/R context (a long near its analyst target = limited upside → the S7 gate can weight it
  later). Read-only board now; the S2-index-S/R-proximity + stock-target gate is the queued refinement.

## STEP 3 — Verify
- Hermetic (Rule J): crafted headlines → TARGET/SUPPORT/RESISTANCE for the right symbol; no cue → nothing.
- Real-data (Rule F): the real store's analyst-target headlines → correct stock TARGET levels.

## Rule K — after this (news feature completion tracker)
Remaining news items after stock levels: directional sentiment (FinBERT/VADER — D4) · BSE + more NSE
filing endpoints · S5 social/Telegram (needs channel config) · S6 login seam (disabled) · S4d vision/
proxy (user-deferred) · S7 earning harness (market-gated) · index-option S/R-proximity gate.
