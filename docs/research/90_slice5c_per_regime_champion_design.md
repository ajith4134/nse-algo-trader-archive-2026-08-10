# research/90 — Slice 5c-iii: per-market-regime champion (ADVANCED tier §53)

**Date:** 2026-07-25
**Status:** DESIGN + BUILD (this turn). Extends 5c-i/5c-i.b (research/87/88) with 5b's regime axis.
**Rule K:** the champion-challenger queued item "a per-market-regime champion (using 5b's tag)".

## Idea
One global champion ORB config is a compromise across all market conditions. A config that
wins in TRENDING sessions may lose in RANGE_BOUND ones. With the 5a regime classifier and
5b regime axis, we can keep a **champion per market regime** and have the live loop trade
the champion for the CURRENT session's regime — a strictly more expressive policy, still
gated by the same conservative Deflated-Sharpe test per regime.

## Buildable + real-data verifiable now
The 22 real stored sessions already span 3 regimes (12 trending / 6 range / 5 indecisive,
per slice 5a). So we can partition the evaluation set by regime and run the existing
`evaluate_champion_vs_challengers` per regime on REAL data today.

## Design (extend, don't fork — Rule I/G)
1. **`per_regime_champion_evaluator`** (pure): `evaluate_per_regime_champions(labeled_
   sessions, champion_by_regime, challenger_configs) -> dict[regime, ChampionChallengerDecision]`.
   `labeled_sessions` = `[(bars, instrument, market_regime), …]`; partition by regime and
   reuse `evaluate_champion_vs_challengers` per regime (skipping regimes with no sessions).
2. **`champion_configuration_store`** — add an optional `market_regime` to `save_champion`/
   `load_champion_or_default`. JSON becomes `{"global": {...}, "by_regime": {"trending":
   {...}, …}}`; the OLD flat format (a bare config dict) is still read as the global champion
   (back-compat). `market_regime=None` → global (today's behaviour).
3. **Service selection:** `_champion_orb_config()` uses `_current_session_market_regime()` to
   load the regime's champion, falling back to the global champion, then the built-in default.
   Cache becomes per-regime (`_champion_orb_config_by_regime`). Auto-re-eval
   (`_maybe_reevaluate_champion_challenger`) classifies each stored session (5a) and runs the
   per-regime tournament, saving a champion per regime that clears the gate.

## Real-data verification (Rule F)
Classify the 22 real sessions, run the per-regime tournament, and show: a decision per
regime with its own scorecards; the conservative gate keeps/By-regime decisions are coherent
(a regime with too few sessions rejects on insufficient trades). Confirm the store round-trips
per-regime champions and that `_champion_orb_config()` returns the right regime's champion.

## Queued (Rule K)
- Options/credit-spread configs in the per-regime tournament (needs option-chain replay).
- The global champion remains the fallback; retiring it entirely awaits enough per-regime data.

## Files
- `src/nse_algo_trader/paper_trading/per_regime_champion_evaluator.py`
- edits to `paper_trading/champion_configuration_store.py` (per-regime save/load + back-compat)
- edits to `dashboard/live_paper_trading_service.py` (regime-aware selection + auto-re-eval)
- `tests/test_paper_trading/test_per_regime_champion.py`
- `scripts/verify_per_regime_champion_realdata.py`

## Rule check
- **Rule I/C:** reuses the 5c evaluator + gate + 5a classifier; self-describing names.
- **Rule F/J:** hermetic evaluator/store tests + a real per-regime tournament over 22 sessions.
- **Rule G/K:** the per-regime champion drives the live ORB selection (not display-only);
  options configs queued.
- **Rule A:** one slice (per-regime evaluation + store + selection).
