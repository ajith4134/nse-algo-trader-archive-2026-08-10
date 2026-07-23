# 17 — Options-Trading Engine Projects: What to Borrow

Companion to `research/16`. Covers options-trading infrastructure
specifically — Greeks/IV, multi-leg strategy P&L, chain analytics — that
could shortcut this project's options-strategy layers (`research/07` §C,
`research/09` category A/B). Every project verified via direct README
fetch, GitHub metadata as of 2026-07-23.

**Status: research only. Nothing borrowed or implemented yet.**

## Projects found

| Project | Stars | License | Last push | What it is |
|---|---|---|---|---|
| [vollib/py_vollib](https://github.com/vollib/py_vollib) | 418 | MIT | 2026-04 (v1.0.7) | Black/Black-Scholes/BSM pricer with Jäckel's "Let's Be Rational" fast IV solver |
| [rgaveiga/optionlab](https://github.com/rgaveiga/optionlab) | 543 | GPL-3.0 | active | Per-leg Greeks, P/L profile, breakevens, probability-of-profit for multi-leg strategies |
| [michaelchu/optopsy](https://github.com/michaelchu/optopsy) | 1,400 | AGPL-3.0 | 2026-03 (v2.3.0) | Options backtester, 38 built-in multi-leg strategy templates, delta-targeted leg selection |
| [lambdaclass/options_backtester](https://github.com/lambdaclass/options_backtester) | 247 | MIT | 2026-02 | Greeks-aware backtester, Rust (PyO3) compute core, `MaxDelta`/`MaxVega` risk constraints |
| [sirnfs/OptionSuite](https://github.com/sirnfs/OptionSuite) | 297 | MIT | active | Event-driven backtest/live framework; live trading scaffolded but not enabled |
| [dsarkar10/Options-Strategy-Visualizer](https://github.com/dsarkar10/Options-Strategy-Visualizer) | 1 | — | active | Multi-leg payoff diagram + interactive 3D IV surface, Streamlit/Plotly |
| [mirajgodha/options](https://github.com/mirajgodha/options) | 17 | MIT | 2025-01 | NSE-specific: 13 predefined multi-leg strategies, per-leg Greeks, MWPL monitoring, multi-broker |
| [bhanukaranwal/Options-Trading-Bot](https://github.com/bhanukaranwal/Options-Trading-Bot) | 12 | MIT | 2025-09 (v1.0.0) | NIFTY/BANKNIFTY/FINNIFTY-specific, correct lot sizes, Kite paper+live mode switch, VaR/drawdown module |
| [VarunS2002/Python-NSE-Option-Chain-Analyzer](https://github.com/VarunS2002/Python-NSE-Option-Chain-Analyzer) | 642 | GPL-3.0 | 2026-05 (v5.8) | Live NSE chain puller: call/put OI-sum, ITM-ratio, PCR indicators |
| zerodha/pykiteconnect | 1,300 | MIT | 2026-04 (v5.2.0) | Official Kite client — execution substrate, not a borrowable piece |

## Puzzle pieces worth borrowing, and how to upgrade each

- **vollib's IV solver + closed-form Greeks** — standalone, trivially
  vendorable, numerically robust. **Upgrade**: it's dividend-naive
  (Black-Scholes only) — extend with a discrete/escrowed-dividend
  adjustment for NSE single-stock options around dividend dates, and
  vectorize it for batch IV-solving across a whole 200-stock chain per
  tick, feeding `research/14`'s `iv_entry`/`iv_exit` trade-log columns.
- **optionlab's "strategy = list of legs → aggregated Greeks + P/L curve"
  data model** — standalone. **Upgrade**: it's static/offline — turn the
  P/L curve into a live object re-evaluating on every Kite tick, re-solving
  IV per leg via vollib in real time.
- **optopsy's strategy-template taxonomy + delta-targeted leg selection**
  — maps closely to `research/07` §C's full option-type taxonomy.
  **Upgrade**: add NSE lot-size/margin-aware position sizing (SPAN +
  exposure margin) in place of its US-style dollar-based sizing. AGPL
  license — check compatibility before vendoring code directly, safer to
  reimplement the taxonomy/logic than copy the source.
- **options_backtester's risk-constraint architecture** (`MaxDelta`/
  `MaxVega` as first-class objects, Rust compute core) — the best-engineered
  of the group. **Upgrade**: swap its constraints for NSE-specific ones —
  MWPL, SPAN+exposure margin blocks — and reuse the Rust-core pattern for
  real-time margin recomputation under load, directly feeding Layer 5.
- **OptionSuite's `optionPrimitive` abstraction** (a spread/strangle as
  one object) — the multi-leg-as-atomic-unit pattern `research/07` §D
  already requires for Layer 6. **Upgrade**: it's a full opinionated
  framework — steal the abstraction, not the codebase; reimplement against
  Kite's basket-order/GTT APIs.
- **Options-Strategy-Visualizer's IV-surface-from-live-chain rendering**
  — standalone script. **Upgrade**: replace its polling/yfinance source
  with Kite's streaming websocket ticker for a live-redrawing surface —
  feeds the eventual Layer 9 options-analytics panel (`PLAN.md` §2).
- **mirajgodha/options' NSE F&O universe scanner + MWPL alerting** —
  standalone. **Upgrade**: finish the Kite connector it only has on its
  roadmap.
- **bhanukaranwal/Options-Trading-Bot's config-driven instrument/lot-size
  definitions and paper/live mode-switching architecture** — the closest
  existing skeleton to this project's own Layer 6 design (`PLAN.md` §1).
  **Upgrade**: its README doesn't show true atomic multi-leg order
  handling — add basket-order semantics so a 4-leg iron condor fills/fails
  as one unit, exactly the gap `research/07` §D already flags.
- **Python-NSE-Option-Chain-Analyzer's chain-parsing/refresh logic** —
  standalone. **Upgrade**: feed its parsed chain directly into vollib for
  full Greeks, replacing its indicator-only (PCR/ITM-ratio) approach.

## Found, wasn't asked (flagged explicitly)

- **GEX/DEX/VEX dealer-exposure analytics** (gamma/delta/vega exposure as
  a tradeable signal) surfaced via a curated awesome-list
  (`flashalpha-quantconnect`) — directly usable for index-options
  skew/dealer-positioning-aware entries on NIFTY/BANKNIFTY, and adjacent
  to but distinct from `research/13`'s Max Pain/OI filters.
- **pysabr/SSVI** for arbitrage-free volatility-surface fitting — relevant
  once IV-surface work (above) moves past a simple per-strike IV solve.

## Ranked — most worth reading actual source code from next

1. **options_backtester (lambdaclass)** — best-engineered Greeks/risk-
   constraint architecture with a Rust core; standalone, MIT, directly
   portable to NSE margin rules.
2. **vollib** — the IV/Greeks math core everything else depends on; small,
   standalone, MIT, worth reading line-by-line before extending for
   dividends.
3. **optionlab** — cleanest per-leg-Greeks/P&L data model for multi-leg
   strategies; standalone and small enough to fully absorb.
4. **bhanukaranwal/Options-Trading-Bot** — closest architectural analog to
   this project's exact target; read it to steal config/mode-switching
   patterns even though it's small/early-stage.
5. **optopsy** — for its strategy-template taxonomy and delta-targeted
   leg-selection logic, despite AGPL licensing constraints on direct code
   reuse.

Deliberately not in the top 5: OptionSuite (full opinionated framework
that would fight this project's own architecture — worth skimming for
ideas, not for code lifting).

See `research/20` for the consolidated action plan across all borrowable-
project research (`research/15`-`19`).
