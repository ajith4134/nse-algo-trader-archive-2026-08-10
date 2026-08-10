# Option bots — full profit taxonomy + clean-sheet selection architecture (2026-08-04)

The user's ask: replace the two option bots' scan→pick→reject pipeline with a clean-sheet SELECTION
architecture that (1) ranks the whole universe cross-sectionally, (2) uses a scored multi-factor selector +
structure optimizer, (3) uses real option economics, (4) fixes IV-rank starvation, and (5) **earns in ANY
regime including flat markets**, generating its own structure ideas to open+close winning trades.

This maps the FULL space (expand-idea), then specifies the architecture. Numeric params (deltas, DTE, profit
targets, India-VIX levels) are shown as *illustrative* — in the build they are CALIBRATED FROM DATA
(percentiles / optimization / Bayesian), never hardcoded (project self-calibration rule).

---

## PART A — How options ACTUALLY earn money (the profit-mechanism taxonomy)

Options P&L decomposes into the greeks. Every strategy is a bet on one or more:
`dP ≈ Δ·dS + ½Γ·dS² + ν·dσ + Θ·dt + ρ·dr`. The FIVE independent money-engines:

| Engine | You get paid for | Wins when | Structures |
|---|---|---|---|
| **Θ Theta / carry** | time passing (short premium) | market FLAT / range, IV ≥ realized | short strangle, iron condor, iron fly, credit spreads, calendars |
| **Δ Direction** | the underlying moving your way | trend | debit spreads, verticals, risk reversals, ratio backspreads |
| **ν Vega / vol level** | IV rising (long) or falling (short) | vol expands / crushes | straddles/strangles (long ν), condors (short ν), calendars |
| **Γ Gamma** | realized movement > implied (long) | big moves either way | long straddle, 0DTE gamma, backspreads |
| **Skew / term / RV** | mispriced *shape* of the surface | relative value converges | risk reversals, put/call spreads, calendars, dispersion |

**The key insight for "any regime, even flat":** a flat market is not "no trade" — it is the HOME REGIME of
the Theta engine. When nothing moves, short-premium structures collect decay every day. The bot never needs a
directional move to profit; it needs to correctly identify WHICH engine the current regime pays, and deploy a
structure whose dominant greek matches it. That is the whole game.

### Regime → paying engine → structure (the core mapping the engine must encode)
- **Flat / range-bound, IV rich** → Θ + short-ν → iron condor / short strangle (sell the wings the market
  won't reach). Entry: sell ~Δ16 strangle when VRP>0 & range-bound. Exit: take 50% of max credit, or stop at
  ~2× credit, or time-stop; always intraday square-off.
- **Flat, IV cheap** → long Γ cheaply → calendar / long ATM straddle (own convexity when it's underpriced).
- **Trending** → Δ with capped risk → directional debit spread (CE/PE) or ratio backspread. (This is the path
  we just wired.)
- **Vol about to expand (compression → breakout)** → long ν+Γ → long strangle / straddle before the move.
- **Post-shock, IV very high** → short ν (IV mean-reverts down) → defined-risk condor / credit spread.
- **Event (results/expiry)** → IV-crush short-ν straddle pre-event, or 0DTE Γ on expiry day.
- **Range with skew mispriced** → skew RV → risk reversal / put-spread vs call-spread.

### Cross-sectional engines (rank the WHOLE universe, not per-name)
- **VRP carry** — rank names by (IV − forecast realized vol). Sell richest VRP, avoid/buy poorest. *Needs no
  long IV history* — only a vol forecast — so it FIXES the IV-rank starvation directly.
- **Dispersion** — index implied-correlation vs realized: sell index vol / buy constituent vol when implied
  correlation is rich (index premium > basket). The pod already computes implied correlation — lift it into a
  book.
- **Skew RV** — rank names by richness of put skew vs their own/peer history; fade extremes.
- **Term-structure RV** — contango/backwardation across expiries → calendars.
- **IV-rank cross-sectional** (once history exists) — richest → sell, cheapest → buy.

---

## PART B — Three tiers of the redesign (base → advanced → ultra)

### BASE (what a good version does — completes the current playbook)
A **VRP-based rich/cheap signal** (IV − GARCH/HAR forecast RV) replacing the None IV-rank, so premium-selling
structures wake up; the regime→engine→structure map above driving selection per name; the directional-debit
path we built kept for trend. Real option-leg mid P&L in the lifecycle.

### ADVANCED 🚀 (scored, cross-sectional, optimized)
1. **Opportunity Scanner** — for every underlying compute a feature vector: regime, VRP, IV-rank(shrunk),
   skew, term slope, directional verdict+conviction, flow (stock), event phase, liquidity. 
2. **Multi-factor Opportunity Score per engine** — score each of the 5 engines' edge for that name (e.g.
   Θ-score = f(VRP, range-prob, IV-rank); Δ-score = f(trend conviction); ν-score = f(IV vs forecast, vol-of-
   vol)). Cross-sectionally rank all names on the max-engine score → a ranked opportunity book.
3. **Structure Optimizer** — instead of a fixed structure per branch, ENUMERATE candidate structures for the
   winning engine and pick the max-EV one under defined-risk + liquidity constraints, using a regime-
   conditioned Monte-Carlo of the underlying (from the vol model) to price each structure's expected P&L.
4. **Liquidity/microstructure strike filter** — choose strikes by OI / bid-ask / volume; reject illiquid legs;
   model multi-leg slippage.
5. **Real economics** — per-leg mid-to-mid marking, greeks-aware sizing, MFE/MAE, profit-take at % of max.

### ULTRA 🌌 (the bot invents + proves its own trades)
1. **Regime-conditioned generative structure search** — don't pick from a fixed library; SEARCH the leg space
   (strikes × rights × ratios) with an optimizer (pymoo/CVXPY) to synthesize the structure that maximizes
   expected utility for the forecast distribution — the bot literally *composes new structures* (e.g. a
   broken-wing condor skewed to the trend) rather than choosing a named one. This is the "come up with its own
   ideas" ask, made rigorous: the payoff engine + optimizer generate the trade.
2. **Ensemble regime forecast → distributional payoff** — a Monte-Carlo / mixture-of-regimes model of the
   underlying's terminal distribution; every candidate structure scored by expected utility over that
   distribution, not a point view. Profits in flat markets fall out naturally (the optimizer finds the
   Θ-harvest that maximizes EV when the distribution is tight).
3. **Cross-sectional portfolio optimizer** — pick the BOOK of option trades (across the 5 index + 210 stock
   names) that maximizes portfolio expected utility subject to net-greeks/VaR/margin — dispersion, VRP carry
   and directional bets sized jointly (CVXPY), not name-by-name.
4. **Self-learning selection** — a learned model that predicts realized edge per (engine, structure, regime)
   from the accruing track record, re-weighting the opportunity score online (river/LightGBM) — the bot learns
   which of its own ideas actually pay and shifts capital toward them.
5. **Exit optimizer** — a learned/optimized exit policy (profit-target, greeks-based, regime-flip, time) per
   structure, not a fixed stop — maximizing captured edge.

---

## PART C — Clean-sheet architecture (the modules to build)

Shared `option_alpha/` engine (both bots bind to it; index/stock differ only by universe + flow/event inputs):

```
UNIVERSE SCAN  →  per-name FEATURE VECTOR (regime · VRP · IVrank-shrunk · skew · term · trend · flow · event · liquidity)
      │
      ▼
OPPORTUNITY SCORER  →  per-name, per-engine edge scores (Θ/Δ/ν/Γ/RV) → cross-sectional RANK → opportunity book
      │
      ▼
STRUCTURE OPTIMIZER  →  for each booked name+engine: regime-conditioned distribution → enumerate/搜索 structures
                        → max-EV defined-risk structure → liquidity/strike filter → concrete legs
      │
      ▼
PORTFOLIO SIZER  →  greeks/margin/VaR-aware joint sizing (CVXPY) → TradeProposals to the supervisor
      │
      ▼
LIFECYCLE (exists)  →  open · mark per-leg mid · exit optimizer · square-off · record → competency + learning
```

New modules (self-describing names):
- `option_alpha/variance_risk_premium_engine.py` — IV − forecast-RV rich/cheap signal (fixes IV-rank block).
- `option_alpha/iv_rank_shrinkage_estimator.py` — shrunk/pooled IV-rank from thin history + India-VIX proxy.
- `option_alpha/regime_profit_engine_map.py` — regime → paying engine(s) mapping (encoded, calibrated).
- `option_alpha/option_opportunity_scorer.py` — per-name per-engine scores + cross-sectional ranker.
- `option_alpha/terminal_distribution_model.py` — regime-conditioned Monte-Carlo of the underlying.
- `option_alpha/structure_payoff_optimizer.py` — enumerate/search structures, max-EV under constraints.
- `option_alpha/option_liquidity_filter.py` — OI/bid-ask/volume strike gating + slippage model.
- `option_alpha/option_leg_pnl_marker.py` — per-leg mid-to-mid marking for the lifecycle exits.
- (later) `option_alpha/option_book_optimizer.py` — CVXPY cross-name portfolio of option trades.

## Build order (slices, each engine-grade + real-data verified)
1. **VRP engine + shrunk IV-rank** — unblocks premium selling in any regime (highest leverage, uses data we
   have: intraday RV forecast + chain ATM IV). Wire into both selectors' rich/cheap decision.
2. **Regime→engine map + Opportunity Scorer** — replace first-match playbook with scored per-engine selection;
   cross-sectional rank.
3. **Terminal-distribution model + Structure Payoff Optimizer** — max-EV structure per name (the "own ideas").
4. **Liquidity filter + per-leg mid P&L marker** — real economics for entry + exit.
5. **Portfolio/book optimizer + self-learning score re-weighting** — ultra tier.

## Sourcing (Rule I) — libraries to integrate, not reinvent
`arch`/`statsmodels` (already in) for RV forecast; `numpy`/`scipy` for BS pricing + optimization; `pymoo` or
`CVXPY` (already in) for the structure/book optimizer; `river`/`LightGBM` (already in) for online learning.
Per-part mechanical triage via sourcing-oss-parts when each slice is built.

## Open blockers (Rule K)
- India-VIX history + per-name IV backfill from historical chains (data acquisition, Rule I) for the
  shrinkage estimator's prior — VRP path works WITHOUT it.
- All numeric params calibrated from data, not hardcoded.
- Real-data verification per slice on the live market store (market open now).
