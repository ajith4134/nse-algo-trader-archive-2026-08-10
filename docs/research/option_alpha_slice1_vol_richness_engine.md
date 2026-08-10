# Slice 1 — Vol-Risk-Premium Richness Engine (option_alpha)

Part of the option-bots clean-sheet redesign (`docs/ideas/option_bots_profit_taxonomy_and_redesign.md`).
Highest-leverage first slice: unblock premium selling in FLAT / any regime by replacing the perpetually-None
IV-rank gate with a robust, cross-sectional **vol-richness** signal built from the Variance Risk Premium we
already compute.

## The problem it fixes
Both option selectors decide "sell premium (rich) vs buy vol (cheap)" from `surface.iv_rank`, which is `None`
until ~60 sessions of per-name ATM-IV history (store has ~6-36) → the premium-harvest branches never fire →
the bots can't earn the Θ/theta carry that IS the profit engine of flat markets. Yet the regime engine
already produces `variance_risk_premium = ATM_IV − blended_forecast_RV` per name every cycle — a rich/cheap
signal that needs **no** long IV history. It is simply unused by the decision.

## The engine (not a scalar)
`VolRiskPremiumRichnessEngine` — a cross-sectional + time-series richness ESTIMATOR with carried state.
SOTA analog: Qlib cross-sectional factor normalization + a Bayesian shrinkage estimator (James-Stein style).

**Algorithm.** For each underlying u this cycle:
1. `vrp_u = IV_u − forecastRV_u` (from `VolatilityRegimeState`), plus `rv_u` (trailing realized vol).
2. **Time-series percentile** `p_ts(u)` — where `vrp_u` sits in u's own rolling VRP history (carried state,
   `VrpHistoryStore`); matures as history grows (Rule Q: reported maturity, widened uncertainty when thin).
3. **Cross-sectional percentile** `p_cs(u)` — rank `vrp_u` among ALL names this cycle (the whole universe
   scored against itself — the cross-sectional edge the redesign wants).
4. **Shrinkage blend** `richness_u = w·p_ts(u) + (1−w)·p_cs(u)`, `w = n_u/(n_u+k)` where `n_u` = u's history
   length and `k` a shrinkage constant — a thin name leans on the cross-section, a mature name on its own
   history (James-Stein / empirical-Bayes shrinkage; handles small-N *inside* the full algorithm, Rule Q).
5. Output `VolRichnessState(vrp, realized_vol, richness∈[0,1], maturity, n_history, basis)`.
   `richness` is a percentile by construction → thresholds are self-calibrating (top/bottom tercile = data-
   derived cut, no magic constant).

**Carried STATE.** `VrpHistoryStore` persists each name's dated VRP + RV series (idempotent per session),
trimmed to ~1y; the cross-sectional snapshot is recomputed each cycle. This is real evolving state, not a
stateless recompute.

**Decision integration (changes behavior).** Both selectors gain a `vol_richness: VolRichnessState | None`
input. The "rich → SELL premium" branch fires on `richness ≥ high` (e.g. ≥ 0.66 percentile) **OR** the legacy
`iv_rank ≥ high` when earned; the "cheap → BUY vol" branch on `richness ≤ low` (≤ 0.33). Positive-VRP +
range-bound still required for the sell (don't sell into a stressed regime — the stress gate stays). This
wakes the iron-condor / strangle / credit-spread paths in flat markets using data we have TODAY.

## Depth justification (what a thin version omits)
A diagnostic would print VRP on a panel. This engine: carries a persisted per-name VRP/RV history, computes a
proper time-series AND cross-sectional percentile, shrinks them by history length (real small-N statistics),
exposes a maturity ladder, and REWIRES the live sell/buy-vol decision in both bots — the premium-harvest
engine goes from permanently dormant to active. It is the cross-sectional normalization layer the whole
redesign builds on.

## Modules
- `option_alpha/__init__.py`
- `option_alpha/vol_risk_premium_richness_engine.py` — `VolRichnessState`, `VrpHistoryStore`,
  `VolRiskPremiumRichnessEngine.assess_universe(per_name_inputs) -> dict[str, VolRichnessState]`.
- Wire: both bots compute regime+surface for all names, feed VRP/RV into the engine ONCE per cycle (needs the
  cross-section), then pass each name's `VolRichnessState` into `selector.select(...)`.
- Selector edits: add `vol_richness` param; gate rich/cheap on richness with the iv_rank legacy fallback.

## Verification
- Unit/property: richness ∈ [0,1]; monotone in VRP; thin-history name shrinks toward cross-section; a name
  with the universe's top VRP gets richness→high; empty/degenerate inputs safe.
- Real-data (market open): run over the full index + stock universe on the live store; confirm the VRP
  cross-section is sane (NIFTY/BANKNIFTY vs stocks), richness spread is non-degenerate, and a rich-VRP name
  now triggers a premium-sell structure where before it stood aside. Eyeball the numbers.

## Sourcing (Rule I)
Integrate `numpy`/`scipy.stats` for the percentile + shrinkage; `pandas` for the rolling store. No external
OSS part warranted (bespoke shrinkage percentile is small, exact, and fitter than any library); the heavy
vol modelling (GARCH/HAR) is already integrated in the regime engine we consume. Logged, not skipped.

## Backlog (Rule K)
- India-VIX / historical-chain IV backfill later enriches the prior (VRP path works without it).
- Slice 2 (opportunity scorer) will consume `richness` as one factor among the 5 engine scores.
