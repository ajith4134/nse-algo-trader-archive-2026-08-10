# Slice 2 — Option Opportunity Scorer (option_alpha)

Part of the option-bots clean-sheet redesign. Replaces the selectors' FIRST-MATCH branch priority (whichever
regime condition matches first wins) with a PRINCIPLED, SCORED, CROSS-SECTIONAL choice: score every profit
engine's edge for every name, deploy the engine with the strongest score, and rank the whole universe so the
best opportunities lead.

## The problem it fixes
Today the structure is chosen by the ORDER of if-branches in the selector: stress → expiry → sell-premium →
buy-vol → directional. If two engines both qualify (e.g. rich premium AND a directional trend), the earlier
branch wins by position, not by which edge is actually stronger. And names aren't ranked against each other —
a marginal opportunity trades the same as a strong one. There is no single place that says "for THIS name,
right now, the Θ engine scores 0.8 but the Δ engine only 0.3, so harvest premium."

## The engine (not a scalar)
`OptionOpportunityScorer` — a multi-factor, per-engine edge-scoring + cross-sectional ranking engine.
SOTA analog: Qlib's cross-sectional factor model producing a per-instrument score that drives selection.

**Five engine scores per name** (each ∈ [0,1], from the gathered feature vector — regime, VRP richness,
skew, term slope, trend conviction, flow, event, realized vol):
- **Θ (theta / premium harvest)** — `f(richness↑, VRP>0, calm/range regime, ¬stressed, ¬pre-event)`. The
  flat-market engine.
- **Δ (directional)** — `f(trend_conviction, regime trending)`. Capped-risk directional debit.
- **ν (long vega)** — `f(cheapness↑, vol-compression, expected expansion)`. Buy vol when cheap.
- **Γ (gamma)** — `f(expiry proximity, cheap vol, big-move expectation)`. 0DTE / long gamma.
- **RV (skew / term relative-value)** — `f(|skew| extreme, |term slope| extreme)`. Risk reversals / calendars.

**Best engine** = argmax of the five (with a minimum-score floor → abstain if no engine clears it — the
scored replacement for "stand aside"). **Cross-sectional rank** = names ranked by their best-engine score
(percentile), so a book cap / sizing can favour the strongest opportunities (Rule L: still the FULL universe,
just prioritized).

**Carried STATE** — `OpportunityScoreLedger` persists each cycle's (name, engine, score, chosen) rows +
(later) realised outcome, so slice-5 self-learning can re-weight the factor→score maps from what actually
paid. This is the calibration substrate, not a stateless recompute.

**Decision integration (changes behavior).** The bot asks the scorer for `best_engine` per name and dispatches
the selector to build the structure for THAT engine (a new `select_for_engine(engine, …)` path), instead of
first-match. When the best score is below the floor → stand aside. Cross-sectional rank feeds a book-size
tilt. This makes selection scored + universe-aware, the core of the redesign.

## Depth justification (what a thin version omits)
A diagnostic would print the 5 scores. This engine: computes each engine's edge from a real multi-factor
function, argmax-selects with an abstention floor, ranks the whole universe cross-sectionally, DISPATCHES the
structure choice by score (not branch order), and persists a score/outcome ledger for online re-weighting —
it replaces the selection logic, changing every trade decision.

## Modules
- `option_alpha/option_opportunity_scorer.py` — `ProfitEngine` enum (THETA/DELTA/VEGA/GAMMA/RELVALUE),
  `EngineScores`, `OpportunityScore(underlying, scores, best_engine, best_score, rank_percentile)`,
  `OpportunityScoreLedger` (carried state), `OptionOpportunityScorer.rank_universe(feature_vectors) ->
  dict[str, OpportunityScore]`.
- Selector: add `select_for_engine(engine, …)` that returns the structure for a chosen engine (reuses the
  existing branch bodies, now dispatched by engine rather than fallen-through).
- Bots: after `assess_universe` (slice 1), build the feature vectors, `rank_universe`, then per name
  `select_for_engine(best_engine)`; skip names below the abstention floor; tilt size by rank.

## Calibration (no hardcoded)
Score-combination weights start as documented, equal-ish priors; the ledger + slice-5 learner will fit them
from realised edge. The abstention floor is a cross-sectional quantile (data-derived), not a magic constant.
Engine sub-scores are built from already-normalized inputs (percentile richness, conviction ∈[0,1], bounded
regime probs) so no raw-scale magic numbers.

## Verification
- Unit/property: each engine score ∈ [0,1]; Θ score rises with richness + falls when stressed; Δ score rises
  with trend conviction; argmax picks the dominant engine; abstains below the floor; rank is a valid
  percentile; ledger persists.
- Real-data: run over the live index + stock universe; confirm the best-engine mix is sane (rich names → Θ,
  strong-trend names → Δ), the cross-sectional ranking orders names by edge, and the dispatched structure
  matches the winning engine. Eyeball a few names end-to-end.

## Sourcing (Rule I)
Integrate `numpy`/`scipy.stats` (percentile rank, already used). No external OSS — the per-engine scoring is
bespoke domain logic (the mapping from greeks-regime to edge), exact and small; a library can't encode this
project's engine taxonomy. Logged, not skipped.

## Backlog (Rule K)
- Slice 3 structure optimizer consumes `best_engine` + the distribution to synthesize the max-EV structure.
- Slice 5 learner fits the score weights from the `OpportunityScoreLedger` realised outcomes.
