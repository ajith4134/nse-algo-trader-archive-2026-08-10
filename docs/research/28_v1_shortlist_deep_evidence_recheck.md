# 28 — v1 Shortlist Deep Evidence Re-Check

Follow-up pass on `PLAN.md` §7's proposed v1 shortlist (indicators: EMA,
RSI, Supertrend, VWAP, ATR, IV Rank, PCR; strategies: Opening-Range
Breakout + Bull Put/Bear Call credit spread). You confirmed the shortlist
but asked for a deeper evidence check on whether anything stronger exists,
specifically re-verifying PKScreener, NSE-Stock-Scanner, and
aaryansinha16/AI-trader for concrete backtest numbers.

**Status: research only. No change made to the confirmed shortlist —
this file documents the check and a recommendation, per your instruction
that a "confirm as-is" verdict is a valid outcome.**

**Caveat on this pass's search depth**: this session's WebSearch quota was
exhausted after an initial batch, so the sweep below relies on WebFetch
against GitHub (READMEs, raw files, GitHub API/code search) and Google
Scholar directly, rather than a full multi-engine WebSearch sweep. Where a
claim could not be independently triangulated as a result, it's marked
single-source below rather than presented as settled.

## 1. Re-checking the three named repos for concrete numbers

- **PKScreener** (github.com/pkjmesra/PKScreener) — re-fetched README
  directly. **Confirmed: no backtest performance numbers published** (win
  rate, returns, profit factor). It documents a "Backtests" menu exists and
  links to a report, but the README itself carries zero quantified results.
  Grade: C (tool exists, performance unverified).
- **NSE-Stock-Scanner** (github.com/deshwalmahesh/NSE-Stock-Scanner) —
  re-fetched README directly. **One number found**: its own 44-SMA
  strategy is self-reported at "around 40-45% Hit-Loss%" — i.e., roughly
  coin-flip, and the author explicitly frames the repo as a charting tool,
  not a validated trading system ("not a trading Bot... please do not take
  trades just because this tool gives you the name"). Grade: C, and the one
  number available is a negative result, not supporting evidence.
- **aaryansinha16/AI-trader** (github.com/aaryansinha16/AI-trader) —
  **new concrete numbers found** (Mar-Apr 2026 self-reported backtest):
  MEDIUM risk profile — 71% win rate, ₹53,715 net P&L over 49 trades, R:R
  1.37, max drawdown ₹5,411; HIGH risk — 77% win rate, 52 trades. Substrategy
  breakdown: bearish-momentum 68% win rate, mean-reversion 78%, VWAP
  breakout 100% (n is tiny — likely single digits, so this is anecdotal, not
  a rate). RL exit agent handles ~15% of exits at ~90%+ profitability on
  those exits. **Grade C**: single project, self-reported, ~50-trade sample
  (too small for statistical confidence), no stated out-of-sample/walk-
  forward split, no confirmation options slippage was modeled realistically
  for NSE's wide index-option spreads.

## 2. Stronger alternative to Opening-Range Breakout?

No stronger-evidenced alternative surfaced. `research/11` already
established the strongest available grading: the open being the most
volatile/tradeable window is **A-grade** (Sampath & Gopalaswamy 2020, *J.
Emerging Market Finance*, NSE tick data), while exact ORB win-rate/profit-
factor numbers (~52% win rate, ~1.6 profit factor; an 8-year Nifty study
where shorts drove 75% of profits with only 13% of trades hitting full
target) remain **B/C** (practitioner backtests, not peer-reviewed). A fresh
Google Scholar sweep for "opening range breakout Nifty NSE backtest" found
no peer-reviewed paper isolating ORB specifically — the closest is Waghela,
Sen & Rakshit (2024, Springer, *AI in Prescriptive Analytics*), "A
performance analysis of technical indicators on the Indian Stock Market,"
which backtests indicators across NIFTY 50/sector stocks generally (A-grade
existence, but abstract-level detail only — full-text metrics weren't
accessible via Scholar snippets, so treat as directionally supportive, not
quotable numbers). A newer 2026 IGI Global paper (Karnawat, Agarwal, Munkar)
studies MA/RSI/Bollinger/MACD specifically on Bank Nifty — same caveat.
**Verdict: keep ORB.** No candidate (VWAP mean-reversion, gap-and-go — both
seen only in unstarred, unvalidated GitHub tools, e.g. `Gaurav-UwU/intraday-
playbook`) has better evidence; that repo's one substantive finding worth
keeping is qualitative, not a strategy swap: at ₹10-15k retail capital,
**transaction-cost drag is roughly 30% of edge**, meaning cost modeling
matters more than strategy choice at small size (research/26/Layer 7
already flags realistic cost modeling as a requirement).

## 3. Simpler/safer alternative to Bull Put/Bear Call, or Iron Condor as v1.1?

No peer-reviewed or credible practitioner backtest comparing NSE-specific
credit-spread vs. iron-condor performance was found (a fresh Scholar search
for "Nifty iron condor OR credit spread backtest NSE" returned **zero**
matching articles — a genuine literature gap, not an oversight). The
strongest India-specific source is Zerodha's own Varsity "Option
Strategies" module (re-fetched directly): Bull Put Spread (ch. 3) and Bear
Call Spread (ch. 8) are taught as **directional-view, moderate-conviction**
tools; Iron Condor (ch. 14) is the module's capstone, explicitly built as
"bull put spread + bear call spread combined" for a **non-directional**
view, with a dedicated discussion of NSE's post-June-2020 margin framework
making combined spreads meaningfully more capital-efficient than running
them separately. This is grade A/B "house doctrine" (the broker's own
official education content, India-specific), not an audited return series.
**Verdict: don't swap out Bull Put/Bear Call — keep it as v1** (it's the
simpler two-leg building block and forces you to validate directional-view
credit spreads before combining them). **Do add Iron Condor as the
natural v1.1**, once both spread directions are independently proven in
paper/shadow mode — mechanically it is just running both at once, not a new
risk paradigm, and Zerodha's own margin framework rewards doing so.
Calendar spreads are not recommended for v1.1: they need IV term-structure
modeling (different expiries) that's a materially bigger lift with no
NSE-specific evidence found either way.

## 4. Indicator evidence and the missing regime filter

Academic attention to RSI/EMA/MACD/Bollinger on NIFTY/Bank Nifty is real and
recent (Waghela/Sen/Rakshit 2024; Karnawat et al. 2026; Nesari & Rathod
2026 on Bank Nifty RSI/MACD/Stochastic/Bollinger + OI) — **grade B**:
triangulated existence of peer-reviewed/edited-volume study, but specific
performance rankings weren't extractable from abstracts/snippets, so don't
treat this as "RSI beats X on NSE," only as "RSI/EMA/MACD are legitimately
NSE-studied, not folklore." VWAP, Supertrend, and ATR have no dedicated
peer-reviewed NSE study found; their support is practitioner/tooling
consensus (near-universal in the NSE bot ecosystem: PKScreener, NSE-Stock-
Scanner, AI-trader, and every fresh GitHub tool found this pass all
implement Supertrend/VWAP/ATR) — grade C but very broad practitioner
convergence. PCR is explicitly part of Zerodha Varsity's own options module
alongside Max Pain — grade A/B house doctrine specifically for NSE options,
strengthening its place in the shortlist. IV Rank has no NSE-specific
academic or Varsity citation found this pass; it remains standard
US-options-education content applied by analogy — flag as **weakest-
evidenced item already in the v1 list**, not disqualifying, just not
NSE-verified.

**Missing indicator**: `pandas-ta-classic` (github.com/xgboosted/pandas-ta-
classic, verified: 224 category indicators + 62 candle patterns = 286
implementations) surfaces **ADX/DMI** and, as a secondary option, the
**Choppiness Index** as the clear gap. Neither is in the v1 list, yet the
v1 strategy pair is regime-split by construction — ORB needs a trending
day, credit spreads need a range-bound/low-IV day — and `research/11`
already flagged time-of-day regime-gating as needed without proposing a
concrete indicator to do it. ADX is the standard, simplest choice (0-100
trend-strength scale, near-universal across every NSE tool surveyed) and
directly answers "should today's session run the ORB strategy or the
credit spread strategy" — a real gap, not a nice-to-have.

## Final recommendation

**Confirm the existing v1 shortlist as-is, with one addition and one
flagged v1.1:**
- **Add ADX** to the v1 indicator list (regime gate: trend vs. range,
  decides which of the two v1 strategies runs on a given day/name) —
  strongest concrete addition this pass found.
- **Keep** EMA, RSI, Supertrend, VWAP, ATR, IV Rank, PCR, Opening-Range
  Breakout, and Bull Put/Bear Call spread exactly as proposed — nothing
  found this pass beats them on NSE-specific evidence, including a direct
  re-check of PKScreener, NSE-Stock-Scanner, and AI-trader.
- **Flag Iron Condor as v1.1** (not v1): the logical next step once both
  credit-spread directions are independently validated, backed by Zerodha's
  own margin-framework doctrine, not a strategy to build in parallel now
  per Rule A (one layer, validated, before the next).

## What this pass did NOT establish

No NSE-specific peer-reviewed backtest exists for iron condor/credit
spreads (confirmed gap, not an oversight). Exact ORB and indicator
performance numbers remain B/C-grade (practitioner, not audited) — this
project's own hypothesis-validation pipeline (`research/12`) is still the
right gate before trusting any of these numbers with real capital, exactly
as already planned. This pass's WebSearch quota was exhausted early, so the
sweep leaned on WebFetch/Scholar/GitHub API rather than a full multi-engine
search — a follow-up pass with search budget available could dig further
into IV Rank's NSE-specific evidence (the weakest-evidenced current v1
item) and into full-text access for the two 2024/2026 NIFTY indicator
papers cited above.
