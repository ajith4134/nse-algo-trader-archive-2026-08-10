# 10 — NSE Microstructure Claims: Evidence Check

You named five specific NSE market-behavior claims and asked whether
they're real. This file checks each one against actual sources rather than
assuming retail folklore is correct just because it's widely repeated.

**Status: research only. Nothing implemented.** Grading: **A** =
peer-reviewed/official, **B** = reputable secondary (consistent broker/data
docs), **C** = blog/forum, unverifiable precision.

## 1. 52-week high/low breakout momentum — GRADE A (evidenced)

Real, and specifically confirmed on Indian data, not just the classic US
literature. George & Hwang (*Journal of Finance*, Oct 2004) is the original
finding. India-specific replications, triangulated across ≥3 independent
datasets: Rajan Raju (SSRN 2023, NSE data 2004-2023) finds the 52-week-high
effect is a distinct, robust anomaly — higher returns/Sharpe than plain
momentum, survives size controls; Avik Mandhyan (SSRN 2026, 431 NSE stocks,
2015-2023) finds 0.987%/month for the 52-week-high strategy in mid-caps vs.
0.740%/month for plain momentum. **Verdict: real, ~0.3-1%/month long-short
effect, though still working-paper grade, not top-journal.**

## 2. Circuit filter "accelerating momentum" — GRADE mechanics A, causal claim B/C (unresolved for NSE)

Mechanics are well documented (price bands at 2/5/10/20% off previous
close, tighter for surveillance-flagged stocks, dynamic ±10% for F&O
names) — once a stock hits its band, it mechanically stops trading, which
alone explains the "unfulfilled demand" appearance without any behavioral
story needed. The "magnet effect" (price accelerates *into* the limit) has
real peer-reviewed support — but only in **Taiwan** and **China**; a
European study found the *opposite* (activity slows near limits). **No
NSE-specific stock-level study of this effect was found** — only
market-wide index-level circuit-breaker studies, which answer a different
question. **Verdict: the underlying illiquidity mechanics are certain; the
"accelerating momentum" story is unverified for NSE specifically —
folklore-adjacent, not confirmed, not debunked.**

## 3. GIFT Nifty pre-market influence on NIFTY's open — GRADE B (real, imprecise)

A peer-reviewed 2025 study (*Journal of Risk and Financial Management*,
DOI 10.3390/jrfm18090527) using Granger causality and cointegration over
~8 months of high-frequency data finds a genuine, significant, bidirectional
relationship with GIFT Nifty leading in price discovery. This is a real
structural relationship, not just trader superstition. **But** the
commonly quoted "75-85% accuracy" figure for GIFT-Nifty-predicts-the-open
traces to no verifiable study anywhere — every source citing it is an
anonymous broker blog. Domestic news, RBI events, and overnight
crude/USD-INR moves routinely override the GIFT Nifty signal. **Verdict:
directionally real and academically supported; the specific accuracy
numbers retail traders quote are unsourced and likely invented.**

## 4. Index vs. constituent stock lead-lag — GRADE: genuine research gap

What's real: NSE's own research and an Indian Journal of Finance study
found Nifty futures historically led the spot index by ~9 minutes,
narrowing sharply in the algo/HFT era via index arbitrage and ETF
creation/redemption — this is a **futures-vs-index** relationship, well
studied. **No rigorous study was found that directly tests whether
heavyweight constituents (Reliance, HDFC Bank) lead or lag the index
itself** at the individual-stock level intraday. Broker material calls
these stocks "trend setters" but that's assertion, not evidence. **Verdict:
plausible via arbitrage logic (likely near-simultaneous, given how tight
the futures-spot link already is) but this is inference, not a citation —
an honest open gap, not a confirmed fact.**

## 5. Pre-open call auction (9:00-9:15) predicting the day — GRADE: mechanics A, predictive claim CONTRADICTED

Mechanics (triangulated across ≥4 sources; direct NSE page fetch timed
out): 9:00-9:08 order collection, ~9:08-9:12 single-price matching becomes
the official open, 9:12-9:15 buffer before continuous trading. The
peer-reviewed study on this (Agarwalla, Jacob & Pandey, IIM Ahmedabad,
*Cogent Economics & Finance*, 2014, DOI 10.1080/23322039.2014.944668) found
the auction has **not** meaningfully improved price discovery — low
volume, weak information content, with most genuine price discovery still
happening in the first 15 minutes of continuous trading. **This directly
contradicts** the retail belief that the pre-open print reliably signals
the day's direction. No newer NSE-specific replication was found, so this
could be stale relative to today's much higher algo-trading volumes — but
as it stands, it's the opposite of what's commonly assumed.

## Explicit gaps — could not verify either way

- No NSE-specific stock-level circuit "magnet effect" study exists.
- No direct constituent-vs-index lead-lag microstructure paper exists.
- GIFT Nifty "opening accuracy %" figures circulating online are unsourced.
- No post-2015 replication of pre-open auction price-discovery quality —
  may not reflect today's algo-heavy market.

## What this means for the plan

None of these claims should be hardcoded into a strategy as assumed truth.
Each is exactly the kind of claim that belongs in the hypothesis-validation
pipeline described in `research/12` — extracted as a testable rule, run
through the existing DSR/CPCV gate against real NSE data, and only trusted
if it survives. Claim 1 (52-week high) already has enough independent
academic backing to skip straight to in-house replication; claims 2 and 5
should be tested with the explicit expectation that the retail version may
be wrong; claim 4 has no existing literature to lean on at all, so it's a
first-party research question if pursued.
