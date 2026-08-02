# B32 — 0-DTE Expiry-Day Options Engine — INSTITUTIONAL SPEC (2026-07-28)

Front-end: `idea-to-institutional-spec`. Build target: `building-engine-grade-features` (Rule P).
Research done inline (operator near token budget — no research-agent fan-out). SOTA grounded from
first-principles options theory + documented desk practice; OSS sourcing gate below (Rule O.1).

---

## 0 · Intent & the decision it changes
Today option entries are **hostage to one trigger**: the directional arm only fires on an Opening
Range Breakout (`option_credit_spread_live_path.py:481`), and the credit-spread arm is dark for ~60
sessions (IV-rank abstention). Result: on a volatile **expiry day** — the single richest intraday
gamma environment on NSE — the system opens almost no option trades.

This engine adds a **0-DTE expiry-day options arm** that (a) is triggered by MANY non-ORB signals so
it trades across regimes, (b) selects among ALL defined-risk structures (directional / long-straddle /
short-premium) via a regime router, and (c) trades the **expiring-day contract** on index AND stock —
never avoids it. It changes the **entry decision** (new candidates generated where none were) and the
**structure/size decision** (which option structure, how many lots). A thin version — a single
buy-CE-on-breakout — would reproduce exactly today's failure and ignore the pin/short-gamma regimes.

**Operator directive (2026-07-28, MCQ):** ALL structures, ALL triggers (momentum/vol-expansion +
time-window + OI/IV-flow + KEEP ORB), build both slices (0-DTE engine first → A3 next), risk =
defined-risk + hard time-stop + mandatory square-off + daily 0-DTE loss cap. Goal: **more option
trades across every regime + gather data.**

---

## 1 · Scope (Rule L)
- **Underlyings:** every underlying whose **nearest expiry == today** (the 0-DTE set). On a monthly
  expiry day (e.g. 2026-07-28) that is all 5 indices + ~210 stock underlyings; on a NIFTY-weekly day
  it is NIFTY only. Selected off the live per-underlying expiry map (B9) — no hard-coding.
- **Segments:** `nse_index_options` + `nse_stock_options`. Both traded on their 0-DTE day.
- **Contracts:** the near-expiry ATM ± ladder already assembled by `select_near_expiry_option_ladder`.
- **Out of scope (this slice):** multi-day holds (forced square-off forbids), gamma scalping (A4,
  rejected on cost arithmetic — see B18 spec), calendar spreads (can't execute under square-off).

---

## 2 · The structures (all defined-risk; router picks per regime)
| Structure | Regime it needs | Payoff | Dominant failure | Greeks as DTE→0 |
|---|---|---|---|---|
| **S1 · Directional long** (buy ATM/ITM CE or PE) | trend / vol-expansion, directional thrust | unbounded up, loss=premium | chop/pin bleeds premium fast | +gamma +delta, brutal −theta |
| **S2 · Long straddle/strangle** (buy ATM CE+PE) | big move, direction unknown (event) | profit on large move either way | pin at strike = double theta loss | ++gamma, −vega, −−theta |
| **S3 · Short-premium defined-risk** (iron fly / iron condor / credit spread) | pin / range / IV-rich | credit kept if underlying pins | fast trend runs through a short strike | −gamma +theta (harvest) |
| **S4 · ORB directional (kept)** | opening-range break | as S1, ORB-triggered | as S1 | as S1 |

Short structures are **always spreads (defined risk)** — never naked short — so max loss = width −
credit even on a 0-DTE fast move. This is the non-negotiable containment for short gamma.

---

## 3 · Entry triggers (the fix for "ORB-only" — union, not replacement)
A candidate is generated if **ANY** trigger fires; the router then maps (trigger, regime) → structure.
1. **Momentum / vol-expansion** — Yang-Zhang realized-vol (handles NSE open gaps) breaks its rolling
   band AND spot displacement > k·ATR → directional (S1) in the thrust direction.
2. **Time-window** — expiry-day clock structure: post-open burst (≈09:20–10:00) and pre-close gamma
   ramp (≈14:00+). In-window + confirming vol/OI → S1/S2 (burst) or S3 (midday pin).
3. **Option-flow / OI + IV** — ATM IV crush + OI unwind at a strike → pin thesis (S3 iron fly at that
   strike); IV spike + skew shift → directional (S1). Uses live OI/IV already in the option ladder.
4. **Gamma-positioning (GEX)** — sign of dealer gamma exposure: long-gamma (dealers dampen → pin →
   S3) vs short-gamma (dealers amplify → trend → S1/S2). GEX from the option chain OI × gamma.
5. **ORB (kept)** — existing `detect_opening_range_breakout` → S4, so ORB days still trade.

Every trigger **abstains with a counted reason** when its inputs are unwarmed (Rule K visibility);
never emits a neutral signal.

---

## 4 · Regime router → structure (extends the B18 arm selector, does not replace it)
Decision variables: realized-vs-implied vol, ADX/trend strength, time-of-day bucket, GEX sign, OI
concentration (max-pain distance). Router table:
- trend ∧ (short-gamma ∨ vol-expansion) → **S1**
- event/ambiguous ∧ vol-expansion → **S2**
- pin ∧ (long-gamma ∨ IV-rich ∨ near max-pain) → **S3**
- ORB fired → **S4**

The chosen structure is fed through the **existing B18 hierarchical Thompson-sampling selector** as
additional arms `zero_dte_directional`, `zero_dte_straddle`, `zero_dte_short_premium` so allocation is
learned per (structure × index × regime) cell with burn-in + ε-floor — i.e. the router proposes,
the posterior selector arbitrates and gathers the data the operator asked for.

---

## 5 · Risk containment (0-DTE-specific)
- **Defined-risk only:** long premium (loss=premium) or spreads (loss=width−credit). No naked short.
- **Hard intraday time-stop** per position (fast theta on 0-DTE — a position not working by T+N min is cut).
- **Mandatory square-off ~15:00–15:15 IST** — no 0-DTE position may be held into expiry settlement.
- **Daily 0-DTE loss budget / kill-switch:** once cumulative expiry-day loss hits the cap, no new 0-DTE
  entries that day (theta days bleed via many small losses).
- Reuses existing `size_defined_risk_spread_lots` + composed size-down levers (B7/B16/vitality/etc.).

---

## 6 · I/O contracts
**Inputs:** per 0-DTE underlying — spot bars (≥28×5m for ADX/RV warm), the near-expiry option ladder
(strikes, OI, IV, greeks, lot size), live premia by token, `now` (IST), the per-underlying expiry map
(B9), account/risk config. Point-in-time correct (no future bars).
**Outputs:** `ZeroDteProposal{ underlying, trigger, regime, structure, legs[], defined_risk_per_lot,
lots, square_off_deadline, abstain_reason? }` → routed into the B18 selector → order intents. Sign
conventions: loss positive-defined per leg; deadline is a hard IST timestamp.

---

## 7 · Acceptance criteria (Rule P — pass/fail)
1. **Real algorithm:** Yang-Zhang RV estimator, GEX from chain, regime router, greeks from a real
   pricing lib — not scalar thresholds. (unit + property tests)
2. **Carried state + store:** per-day 0-DTE loss budget, per-position time-stop deadlines, arm posteriors
   persisted (survives restart).
3. **Raw-input pipeline:** consumes the live option ladder (OI/IV/greeks) + bars, not precomputed scalars.
4. **Decision-grade output:** generates option entries where ORB-only generated none, and picks structure
   by regime — behavior visibly changes (index_option/stock_option open_count rises on expiry day).
5. **Tests:** unit (each trigger, each structure builder), property/invariant (short leg always a spread;
   never holds past square-off; loss ≤ defined max), adversarial (fast-trend through short strike;
   pin at strike for straddle), **Rule-F real-data pass** on a live expiry day.
6. **Vocabulary:** correct (0-DTE, gamma, pin, GEX, Yang-Zhang, iron fly), no cosmetic renaming.

---

## 8 · Verification plan (Rule F / J)
- **Rule F (real):** on a live expiry day (next: today 2026-07-28 monthly, or any NIFTY-weekly day),
  confirm ≥1 index-option AND ≥1 stock-option 0-DTE entry, correct structure per logged regime, and a
  clean forced square-off before 15:15. **This is the single permissible open blocker** until an
  expiry session runs post-deploy.
- **Rule J (hermetic sim):** injected fake ladder+bars behind the existing DI seam replays a synthetic
  expiry day (trend / pin / event) and asserts the router picks S1 / S3 / S2 respectively, square-off
  and loss-cap fire — never leaks to prod.

---

## 9 · OSS sourcing (Rule O.1 — surface for double-check)
- **INTEGRATE `py_vollib` / `py_vollib_vectorized`** — Black-76 greeks/IV for the chain (fast, vectorized). Already referenced in B18 research.
- **INTEGRATE `QuantLib`** — fallback pricer / American-style if needed (heavy but authoritative).
- **INTEGRATE `LightGBM`** — for Slice 2 (A3 trained direction).
- **Yang-Zhang RV:** no clean maintained standalone lib → implement the estimator directly (~40 LOC, well-specified formula) rather than vendor a stale package. **REJECTED** vendoring `arch` for this (overkill — it's a GARCH lib, not a simple RV estimator).
- **GEX:** no NSE-specific OSS → compute from the chain (Σ OI × gamma × contract-multiplier, signed by dealer convention) per the SqueezeMetrics GEX white-paper method. Build in-repo.
- **REJECT `mibian`** (unmaintained, inaccurate greeks), `tastytrade`/broker SDKs (US-only).

**SOTA analog:** documented professional 0-DTE desk practice (regime-routed defined-risk structures +
dealer-gamma positioning) — measured against SpiderRock/SqueezeMetrics-style dealer-gamma logic and,
for the trained arm, **Qlib**'s model pipeline (per B18 spec).

---

## 10 · Decomposition (build order, Rule A — one slice at a time)
**Slice 1 (this spec):**
1. `strategy_engine/yang_zhang_realized_volatility.py` — RV estimator + rolling band.
2. `strategy_engine/dealer_gamma_exposure.py` — GEX from the option chain.
3. `strategy_engine/zero_dte_regime_router.py` — (trigger, regime) → structure.
4. `paper_trading/zero_dte_option_structures.py` — S1/S2/S3 defined-risk leg builders.
5. `paper_trading/zero_dte_expiry_day_live_path.py` — the entry loop: gather 0-DTE set, run triggers,
   route, size (defined-risk), record §9 prediction, place via existing OMS; time-stop + square-off +
   daily loss cap as carried state.
6. Register `zero_dte_*` arms in `OPTION_ARM_NAMES` + B18 selector; wire into `live_universe_paper_loop`.
7. Tests (unit + property + adversarial + hermetic sim) + Rule-F expiry-day plan.
8. Dashboard surface `zero_dte_expiry_engine` (Rule N): 0-DTE set size, triggers fired, structure
   chosen per underlying, open 0-DTE positions, loss-budget remaining, square-off countdown.

**Slice 2 (queued — task #4):** A3 — LightGBM trained direction + variance-risk-premium (Carr-Wu),
Yang-Zhang RV feature; activation-gated per B18 spec.

---

## 11 · Dashboard wiring (Rule G/N)
Consumer: `live_universe_paper_loop` entry pass (the 0-DTE path runs each pass on expiry-day
underlyings). Visibility: new `zero_dte_expiry_engine` feature surface + the existing
`arm_selector`/`option_lot_sizing`/`segment_boards` reflect the new arms. No orphan — the path is the
primary consumer, wired into the loop in step 6.
