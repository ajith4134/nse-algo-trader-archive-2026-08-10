# research/147 — Trunk II SENSES · S7: the news entry-gate consumer (the 🟡→🟢 primary)

**Slice:** S7 — the PRIMARY consumer of the whole news sense (research/140). Turns the acquired +
trust-weighted news (S1/S2/S4 items + S3 reliability) from advisory diagnostics into an actual
**entry-gate decision**, flipping II SENSES sentiment/news 🟡→🟢. Rule K's load-bearing slice.

## What it decides (buildable now, no sentiment model needed)
A **news-EVENT risk gate**: a candidate entry on a symbol that has a FRESH, HIGH-RELIABILITY news/
filing event (S4c NSE filing or S1/S4 headline, weighted by S3 reliability) faces elevated event
uncertainty → **size-down / defer** the entry (don't open into an unresolved material event). This
needs no adverse/favourable sentiment — the PRESENCE of a fresh material event IS the risk. The
directional (adverse-vs-favourable) refinement needs FinBERT/LLM sentiment → QUEUED.

## The pattern it MUST mirror (Rule G/consistency) — the debate-risk gate
`live_universe_paper_loop` already gates entries with `debate_risk_size_multiplier(mechanism)`:
returns 1.0 (identity) when the signal is NOT calibration-earned or has no score; once EARNED, 0.0
(defer) at/above the defer threshold, 0.5 at/above size-down. Applied as `clamped_quantity *= mult`
at the two cash-ORB entry sites (lines 708, 782). S7 adds `news_event_size_multiplier(symbol)` the
SAME way, applied at the SAME sites. **Advisory-until-earned = identity at cold start → an
uncalibrated news signal can NEVER move a real trade** (the project's universal safety pattern).

## Sourcing (Rule I) — N/A: pure in-house integration, no external component
S7 is decision-wiring glue: it connects already-built in-house signals (S2 `news_levels`, S3
`news_source_reliability`, S4c filings in the store) to the already-built in-house entry-gate pattern
(`live_universe_paper_loop.debate_risk_size_multiplier`). There is no algorithm/parser/library to
source — the whole slice is bespoke domain integration over existing project code. No OSS search
applies (logged here + in BACKLOG per the sourcing gate, not silently skipped). The one future part
that WILL owe a sourcing pass is directional sentiment (FinBERT/VADER — already sourced in research/138,
to be built in a later sentiment slice).

## Build
- `news_entry_gate.py` (PURE): `build_news_event_risk_by_symbol(items, reliability_by_source, now,
  config) -> dict[symbol,float]` — per symbol, Σ over items within a recency window of
  (source_reliability × linear recency-weight), clamped to [0,1]; items below a reliability floor
  (0.5) are ignored (a low-trust source alone never moves the gate — research/140). Filings key on
  the "SYMBOL: subject" title; headline symbol-matching is the queued stock-gazetteer (task #2).
  `news_event_size_multiplier(risk, earned, config)` — mirrors the debate thresholds (defer ≥0.75,
  size-down ≥0.55 → 0.5, else 1.0; identity if not earned).
- `live_universe_paper_loop` state: fields `news_event_risk_by_symbol`, `news_event_calibration_earned`
  (False at cold start), `news_event_deferred_count`, `news_event_sized_down_count`; method
  `news_event_size_multiplier(trading_symbol)`. Applied at sites 708 + 782 alongside debate-risk.
- Service: `_maybe_run_news_entry_gate` computes the risk map each pass (store recent items × the S3
  reliability board) and sets it on the state; `news_entry_gate` dashboard surface + manifest.

## Verify
- Hermetic (Rule J): a symbol with a fresh high-reliability filing → risk high → (earned) size-down/
  defer multiplier; NOT earned → 1.0 identity (safety); low-reliability-only source → risk ~0 (floor).
- Real-data (Rule F): build the risk map from the REAL store (the 20 NSE filings + reliabilities) →
  the symbols with fresh filings (HEROMOTOCO/YESBANK…) carry event risk; confirm cold-start earned=
  False makes the multiplier identity (safe) and that once forced-earned the multiplier sizes-down.

## Rule K — after S7 (the sense is 🟢 decision-wired; these refine it)
- **Calibration EARNING of the news-event signal is market/prequential-gated (OPEN BLOCKER)** — same
  gate as the debate/council/all decision consumers; the multiplier is identity (advisory) until the
  prequential harness proves the signal predicts adverse outcomes. Tracked, not silently deferred.
- Directional sentiment (FinBERT/LLM) so the gate distinguishes adverse vs favourable · materiality
  weighting (results/board-outcome > routine "newspaper publication") · S2 index S/R-level proximity
  gate for index-option entries · stock-symbol gazetteer so headlines (not just filings) match symbols.
