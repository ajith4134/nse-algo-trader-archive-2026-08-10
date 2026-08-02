# B18 — index-options strategy ensemble + meta-selector: RESEARCH pass (2026-07-27)

Step 3 of `idea-to-institutional-spec`. Clears the sourcing-gate blocker logged against B18. Three
independent live-web research passes were run on Sonnet (research fan-out only; all code written on
the main thread per the operator's standing rule). Clarify decisions: see
`index_options_profitability_clarify_decisions_2026-07-27.md`. Cost model: see
`b28_indian_trading_cost_model_design_2026-07-27.md`.

**Framing this report earns:** the operator asked for *"all algorithms, and AI chooses which to
follow based on their performance."* The research says the hard part is **not** the arms — it is that
the selector cannot get enough signal at this trade rate. That finding reshapes the whole spec.

---

## 1 · The finding that reshapes the brief: only NIFTY still has a weekly expiry

Per SEBI's Oct-2024 framework (one weekly-expiry index per exchange) and NSE's Sept-2025 rollout:

| index | expiry cadence | expiry day |
|---|---|---|
| **NIFTY** | **weekly + monthly** — the only NSE index with weeklies | **Tuesday** |
| BANKNIFTY / FINNIFTY / MIDCPNIFTY / NIFTYNXT50 | **monthly only** (weeklies discontinued 20 Nov 2024) | last Tuesday |

Consequences the spec must absorb:
- **0-DTE strategies are a NIFTY-only capability.** Any arm that assumes weekly/0-DTE mechanics
  applies to four of the five indices is wrong.
- **IV-rank lookbacks for the other four indices are contaminated** by the weekly→monthly transition
  until roughly Sept 2026 — a 252-day IV percentile spanning that structural break is not comparing
  like with like. The engine must know this and abstain rather than emit a confident IV rank.
- This makes backlog **B9 worse than logged**: a single global `nearest_expiry_date` resolves to a
  NIFTY weekly outside monthly-expiry week, dropping ~210 stock options **and the other four
  indices** from the ladder.

---

## 2 · The arms — what survived research

### ARM 1 · IV-rank / IV-percentile + term structure — **BUILD**
Formulas trace to tastytrade's definitions (IVR = position in the 52-week IV range; IVP =
percentage of days IV was lower). Cited threshold heuristic: sell premium at IVR > 50, buy at
IVR < 20 — **explicitly flagged by the source as a heuristic, not a backtested edge**. The closest
rigorous analog is Simon & Campasano (2014, *Journal of Derivatives*). SOTA analog: **ORATS**.
Caveat found: term-structure calendar spreads **cannot be executed intraday** (they need multi-day
holding) — usable only as a same-day *signal*, not as a tradable structure here.

### ARM 2 · Delta-neutral / gamma scalping — **REJECT as scoped (honest verdict)**
The edge `P&L = ½·Γ·S²·(σ²_realized − σ²_implied)·Δt` is real and was triangulated four ways, but it
is **structurally multi-day**: one session yields a single noisy realized-vol draw, and Indian
per-leg costs (§B28) are paid on *every rehedge* with no multi-day amortisation. Under a forced
intraday square-off this arm pays full costs to harvest a fraction of one vol observation. SOTA
analog: Buehler et al., *Deep Hedging* (2019). The intraday-native cousin (0-DTE dealer-gamma / GEX
flow) needs NSE dealer-positioning data that does not exist at SpotGamma-grade maturity.
**Recorded as a researched rejection, not a silent omission** — this is the one arm the operator's
"build all four" instruction should not get, and the reason is cost arithmetic, not preference.

### ARM 3 · Trained direction + variance-risk-premium model — **BUILD, gated**
Gradient boosting (LightGBM/XGBoost/CatBoost) on engineered features is the recommended class. A
directly relevant walk-forward study on MNQ futures found **neither LSTM nor GBM reached statistical
significance on ~4 years of single-symbol 5-min data** — a data-volume problem, not an architecture
problem. Sequence models should only be attempted *pooled across all five indices*. VRP formalised
via Carr & Wu; recommended realized-vol estimator is **Yang-Zhang** (handles overnight jumps, which
matches NSE's pre-open auction / GIFT-Nifty gap dynamics) over realized kernels, which need denser
tick data than Kite provides. SOTA analog: **Microsoft Qlib**.
**Blocker found:** Kite flushes option instrument tokens every expiry, making multi-year
option-level training data infeasible through the broker alone → needs a paid vendor (TrueData /
Global Datafeeds exist; coverage unconfirmed).

### ARM 4 · Repaired ADX regime router — **BUILD** (already in-repo; close the 20–25 dead band).

**OSS sourcing (arms):** `vollib` and `QuantLib` → **INTEGRATE** (QuantLib shipped a release the day
of this research). **REJECT** on hard mechanical facts: `mibian`, `py_vollib_vectorized`, `pysabr`
(staleness / Python-floor).

---

## 3 · The meta-selector — the central finding

Every algorithm family reduces to the **same arithmetic wall**: resolving an edge that is 5–20% of
per-trade noise SD, at ~2.5–7.5 closed trades/day/arm, needs an effective memory of **weeks to
years**, while intraday-options regimes plausibly turn over in **days to ~2 weeks**.

> **No single textbook algorithm satisfies both "enough samples to be confident" and "short enough
> memory to forget stale regimes" at this trade rate.**

Quantified rejections (not vibes):
- **Plain Thompson Sampling / UCB1** — a 10-point win-rate gap needs ~390 trades/arm (~4 months); a
  3-point gap ~4,360 trades/arm (~3.5 years). No native forgetting; the posterior grows *more*
  confident in stale data forever.
- **NeuralUCB / NeuralTS** — theorems require network widths never used in practice; needs
  5,000–10,000+ trades/arm (2–11 years). Reject.
- **EXP3 / EXP4** — bound not tight at realistic counts (~25% average per-trade regret at 600
  trades); requires true edge > ~5.5–9.6% normalised just to be informative, larger than the edge we
  have. Seldin et al. (JMLR 2012) confirm EXP3 "cannot keep up with UCB1" in stochastic settings.
- **Hedge / MWU** — needs FULL information (what every non-deployed arm *would* have earned), i.e. a
  shadow-fill model whose bias leaks silently into the guarantee.
- **CUSUM / BOCPD change-point bandits** — detection delay is inversely proportional to *the same
  tiny signal* plain comparison already struggles with. **Change detection is strictly harder here,
  not easier.**
- **Bayesian Model Averaging** — this is the **M-open** case (no arm is "the truth"), where BMA
  provably collapses to the single closest candidate. Domingos (ICML 2000) shows BMA weights are
  exponentially noise-sensitive: a worked example produced a **120:1 weight ratio from pure sampling
  noise** between models differing 1–5% in true accuracy. Actively dangerous here.

### Recommendation — a composite, not a textbook algorithm
**Hierarchical (empirical-Bayes), discounted, contextual Thompson Sampling, with a permanent
forced-exploration floor and asynchronous delayed-reward updates.** Rationale:
1. TS degrades most gracefully under sparse/delayed feedback (Chapelle & Li, NeurIPS 2011).
2. TS is the natural substrate for **hierarchical shrinkage** — a new (index × regime) cell inherits
   a population hyper-prior instead of a flat one, which is what keeps per-cell sample needs in the
   *weeks* regime rather than *years*. James-Stein / Dimmery-Bakshy-Sekhon (KDD 2019, validated on
   17 Facebook experiments) show shrinkage strictly dominates raw per-cell means, and the benefit
   **grows with the number of arms**.
3. Forgetting via **exponential discounting**, NOT change-point detection (see above).
4. Auditable: log posterior mean, variance, effective sample size and the drawn sample per decision.

**Delayed reward is a solved problem.** Joulani et al. (ICML 2013): in the stochastic setting delay
inflates regret only **additively**, and any non-delayed algorithm works unmodified via a black-box
reduction — log `(arm, context, open_ts, trade_id)` as pending, apply the posterior update whenever
the trade closes, never block new selections. Production template: Spotify's *Impatient Bandits*
(arXiv:2501.07761) blends a short-term surrogate (our unrealised mark-to-market) with the eventual
true reward via a Bayesian filter.

**Mandatory safeguards, used concurrently:** (a) burn-in — no arm exceeds a near-uniform share until
≥15–20 closed trades *in that context*; (b) hierarchical shrinkage on every posterior mean;
(c) a permanent 10–15% ε-floor so a temporarily-losing arm is never starved of the data needed to
prove whether it was bad or unlucky; (d) optimise a **CVaR / mean-variance-adjusted** statistic, not
raw mean P&L — a premium-selling arm's rare large loss must not be averaged away before enough tail
events exist.

**OSS sourcing (selector) — INTEGRATE:** `vowpalwabbit` (cp312 wheels, v9.11.2 2026-03-07),
`PyBandits` (v8.0.0, explicit 3.9–3.14), `river` (v0.25.0 — **non-contextual only**; its own docs call
contextual `LinUCBDisjoint` "too slow to realistically be used in practice").
**REJECT with reasons:** `mabwiser` (best API of the group but ~23 months dormant; a 2026-03 "is this
maintained?" issue went unanswered — judgment call, fork-worthy), `contextualbandits` (sdist-only, no
CI, binary-reward-only design incompatible with continuous P&L), `SMPyBandits` (author states it is
"NOT meant to be a library"), `bandits` (repo 404), `bgalbraith/bandits` (never on PyPI, deprecated
pymc3), `scikit-bandit` (archived, never released), `banditpylib` (never released), `Facebook Ax`
(no standalone bandit class; heavy BoTorch stack, disproportionate to 4 arms), `TF-Agents Bandits`
(no 3.12 support, stale), `Open Bandit Pipeline` (stale, offline-OPE design — revisit as a *backtest*
tool).

**No library ships the composite.** Use PyBandits/river as the posterior core and write the
shrinkage / discounting / floor / async-delay wrapper in-repo — bounded custom code, not
reimplementing bandit math.

---

## 4 · Named SOTA analogs
ORATS (options analytics) · Buehler et al. *Deep Hedging* · Microsoft **Qlib** (its "online serving"
is deterministic retrain-under-drift, **not** bandit arm selection — adjacent precedent only) ·
**pysystemtrade** (Rob Carver) — the closest *production* analog: combines rules by forecast weights
from bootstrapped out-of-sample windows or "handcrafting", **EWMA-smoothed (span 125)** explicitly to
control switching costs, plus a hard cost ceiling excluding rules too expensive to trade.

**Honest gap stated by the research:** no verifiable, named production system doing bandit-based
selection between competing independent algo-trading strategies with disclosed live results was
found. What exists is academic proposals in backtest, production bandit math in ads/recsys (Yahoo
LinUCB +12.5% clicks; MSN Decision Service +26%; Netflix artwork), and pysystemtrade's non-bandit
solution to the same combining problem.

---

## 5 · What this changes about the spec (to write next)
1. **Three arms, not four** — gamma scalping rejected on cost arithmetic, recorded with its reason.
2. **The selector is the hard part**, and it is a composite with mandatory safeguards, not a library call.
3. **0-DTE is NIFTY-only**; IV-rank must abstain for the four monthly-only indices until ~Sept 2026.
4. **B9 (per-underlying expiry) is a prerequisite**, not a parallel nicety.
5. **B28's cost model is the denominator** of the acceptance bar and is now built.
6. Arm 3 needs a historical options data vendor — an acquisition task (Rule I), logged as B30.
