# INDEX-OPTION & STOCK-OPTION bots — architecture deep dive (2026-08-04)

Grounding doc before the redesign. How each bot **is** (identity/state), how it **scans** its full universe,
what **criteria pick** a trade, what **criteria reject** it, how it **sizes/structures**, and how it **learns**.
Everything below is the real code path (`segment_bots/index_option_bot/`, `segment_bots/stock_option_bot/`).

## 1. Identity — what each bot IS (not just what it does)
A bot is a `SegmentBot` (Protocol in `segment_bot_protocol.py`) that **PROPOSES only** (crypto §03b) into the
`PortfolioSupervisor`; it never places its own orders. Its identity is 4 things it OWNS:
- **A mandate / segment** — `MarketSegment.INDEX_OPTION` (5 index underlyings) or `STOCK_OPTION` (~210 F&O
  names). Full universe, never a sample (Rule L).
- **A data seam** — `IndexOptionDataAdapter` / `StockOptionDataAdapter` (DI, Rule J). Prod wires the real
  market store; tests inject fakes. The bot has NO DB inside it.
- **Carried STATE / stores** — per-underlying fitted models + rolling histories: `VolatilityRegimeStore`
  (GJR-GARCH + Markov regime), `ImpliedVolRankStore` (rolling ATM-IV → IV-rank), `PcrHistoryStore`
  (stock only, PCR history), `WinProbabilityHeadStore` (the learned ML head), `DirectionalModelStore`
  (per-underlying BULL/BEAR pair), `BotTrackRecordStore` (closed trades → competency).
- **A competency / maturity ladder** — `BotCompetency(level 0-5, closed_trades, is_earned)` derived from its
  own realised track record. This is the bot's "age": it gates LIVE capital weight and scales size (Rule Q).
  Everything the bot fits has its OWN `gathering → earned` maturity, so the bot arms itself as data accrues,
  never a code change.

The three bots are peers coordinated by the supervisor (capital allocation → netting → arbitration → one
hard portfolio-CVaR stop). A bot's "self" is its accumulated fitted state + track record — two bots on the
same code but different histories behave differently.

## 2. Universe scan — how a bot sweeps all its names each cycle
`propose(now_epoch)` (per bot):
1. `begin_cycle()` — reset the per-cycle directional-training budget (cold-start throttle).
2. Loop **every** underlying from the adapter (`index_underlyings()` = 5; `stock_underlyings()` ≤ `max_underlyings`
   ranked by contract liquidity). For each, `_propose_one(...)`:
   - pull `price_series` (now DEEP 5m intraday, slice 2b), `option_chain` (real F&O snapshot), ATM IV.
   - **skip immediately** if prices/chain are empty (a hard data-availability reject).
3. Collect the non-None proposals → return to the supervisor.
The scan is per-underlying independent (no cross-sectional ranking — unlike the cash bot, which ranks names
against each other). Each name is judged on its OWN vol/flow/trend state.

## 3. Feature engines — what each name is scored on (the raw → signal pipeline)
Per underlying, per cycle, the bot fits/updates:
- **Volatility-regime engine** (`volatility_regime_engine.py`) — GJR-GARCH(1,1,1) skew-t + HAR-RV vol
  forecast (`arch`) fused with a `statsmodels` Markov-switching **filtered** regime posterior → `regime_label`
  (calm/elevated/stressed), forecast σ, **variance-risk-premium (VRP)**. Maturity: EWMA fallback < 250 obs.
- **IV-surface engine** (`implied_vol_surface_engine.py`) — SVI smile fit per expiry from the real chain →
  ATM IV, 25Δ **risk-reversal (skew)**, term-structure slope, and **IV-rank / IV-percentile** vs the
  underlying's own rolling ATM-IV history (`ImpliedVolRankStore`). Maturity: IV-rank is `None` until
  ≥ `_MIN_HISTORY_FOR_IV_RANK = 60` sessions — **the current bottleneck** (store has ~6-36 → mostly None).
- **Option-flow engine** (stock only, `option_flow_signals.py`) — PCR-by-OI, its rolling **shift z-score**
  (≥30 sessions to earn), unusual-call/put strikes, net flow bias.
- **Event-proximity gate** (stock only, `event_calendar_gate.py`) — real NSE corporate-event calendar →
  PRE_EVENT / POST_EVENT / CLEAR; PRE_EVENT **blocks naked premium selling** (a risk reject).
- **Directional brain** (`directional_ai/`) — per-underlying BULL(P↑)+BEAR(P↓) LightGBM pair on triple-barrier
  labels → `DirectionalArbiter` → LONG/SHORT/NEUTRAL verdict + conviction. Earns at ≥400 samples (deep
  intraday now supplies it). Per-cycle train budget = 4 (cold-start throttle).

## 4. Pick criteria — what MAKES a trade (the selector playbook)
`IndexOptionStructureSelector.select` / `StockOptionStructureSelector.select` map state → structure. In order:
- **Stressed regime + rich IV** → small defined-risk long-vol (own the tail).
- **Expiry day** → 0DTE directional gamma (if trend) else short-premium iron-fly.
- **Rich IV-rank + positive VRP** (calm/elevated) → SELL premium: put-credit spread (if rich put skew),
  else iron-condor / short-strangle. Conviction blends IV-rank × VRP × skew.
- **Cheap IV-rank** → BUY vol: directional debit spread (if trend) else long strangle.
- **Stock only: unusual bullish call flow** → directional call debit.
- **NEW (2026-08-04): earned directional trend at gathering/mid IV** → **defined-risk directional debit
  spread** (CE long / PE short), gated by the arbiter's edge not the vol floor — the path that lets them
  trade today while IV-rank is starved.
The chosen `StructureDecision` carries plan (legs as moneyness offsets) + side + conviction + rationale.

## 5. Reject criteria — what KILLS a trade (every abstention point)
A name is rejected / stood-aside when ANY of:
- **Data missing** — empty price series or empty chain (hard skip).
- **Selector stand-aside** — stressed regime with no favourable structure; OR mid IV-rank AND no earned
  trend (no edge).
- **Regime stress gate** — never a naked vol sale when `stressed_prob ≥ threshold`.
- **Event gate** (stock) — PRE_EVENT blocks naked premium.
- **Conviction floor** — vol/flow structures below `min_conviction_to_trade = 0.30` are dropped (directional
  debit spreads are exempt — gated by the arbiter instead).
- **Size floor** — lots ≤ 0 → None (cold-start now floors to 1 paper lot so this rarely rejects).
- **Signal expiry** — proposals carry a TTL; the supervisor vetoes expired ones.
- **Supervisor-level** (post-bot) — capital-allocation zero weight, net-exposure cap, cross-bot crowding,
  price-divergence guard, and the one hard portfolio-CVaR stop.

## 6. Size & structure → proposal
`DeterministicIndexOptionPolicy` / stock policy: conviction × max_lots × competency-ramp (1/6 → full over
levels 0→5), cold-start 1-lot paper floor. Builds `TradeProposal(segment, bot_name, underlying, side,
structure, size_hint_lots, conviction, calibrated_prob, expected_expectancy, loss_tail_estimate,
signal_expiry_epoch, regime_label, feature_provenance)`.

## 7. Learn — how a bot improves (the closed loop, slice 2a)
`engineer_features(regime, surface, decision)` → the **learned win-probability head**
(`IndexOptionWinProbabilityHead`, LightGBM + isotonic calibration + SHAP, earns at ≥200 labelled trials).
Until earned, the deterministic P(win) passes through. The pod lifecycle closes each paper trade →
`record_closed_trade` → competency accrues + the head trains on the new labelled trial. Drift → retrain.

## 8. Where it's THIN today (the redesign surface)
- **IV-rank starved** (~6-36 sessions vs 60 needed) → premium-selling paths mostly dormant; only the new
  directional-debit path fires.
- **Per-name independent scan** — no cross-name relative-value / dispersion / rank in the OPTION bots (the
  dispersion overlay lives in the pod, not the bot).
- **Structure library is a fixed playbook** — a hand-authored decision tree, not a search/optimizer over the
  full structure space or a greeks-target solver.
- **Option P&L in the lifecycle is a directional underlying proxy** — not real per-leg mid-to-mid.
- **Selection is single-signal-priority** (first matching branch wins) — not a scored multi-factor ensemble.
- **No microstructure / liquidity / bid-ask / OI-depth filter** on strikes chosen.

## Open questions for the redesign (to resolve before building)
1. "Fiat identity" — confirm meaning (bot mandate/identity? a fiat-currency/notional concept? a per-bot
   persona/constitution?).
2. Replace the fixed structure-playbook with a scored multi-factor selector or a greeks-target optimizer?
3. Add cross-sectional relative-value across the option universe (rank names by edge) vs keep per-name?
4. How aggressive a rewrite: augment the current engines, or a clean-sheet selection→execution architecture?
