# 11 — NSE Time-of-Day Session Behavior & Strategy Playbook

Companion to `research/10`. You asked how the market "behaves" from the
9:00-9:15 pre-open through the volatile close, and which
strategies/indicators fit which part of the day. This file separates solid
evidence from practitioner opinion from folklore.

**Status: research only. Nothing implemented.**

## Bottom line

NSE shows a real, academically confirmed U-shaped intraday
volatility/volume curve (high at open and close, lower mid-day) — but once
volume itself is controlled for, the "quiet midday" story is weaker than
commonly claimed. A major structural change — a **formal Closing Auction
Session** — launches 2026-08-03, very close to today, and will change
closing-minute dynamics going forward in ways no current strategy claim
has been tested against.

## 1. Opening session (9:15-9:45) — GRADE A on volatility, B/C on strategy claims

Sampath & Gopalaswamy (2020, *Journal of Emerging Market Finance* 19(3),
using NSE tick data) confirm "unusually high volatility, trading volume and
number of trades during the opening and closing minutes" — a genuine
U-shape. Earlier GARCH studies (Krishnan & Mishra 2013; Karmakar 2007) on
Nifty found the same periodicity. **Caveat the academic study itself
raises**: once volume is controlled for, volatility isn't significantly
different between mid-day and other periods except right at the
open/close extremes — the effect is real but partly a volume artifact.

Opening-Range-Breakout evidence is real but lower-grade: independent
backtests (practitioner blogs, not peer-reviewed) report ~52% win rate,
~1.6 profit factor on NSE indices, and an 8-year Nifty ORB study found
shorts drove 75% of profits with only 13% of trades hitting full target.
**Verdict: the open genuinely is the most volatile/tradeable window (A);
exact ORB backtest numbers are indicative, not audited (B/C).**

## 2. Mid-day (11 AM-2 PM) — mixed evidence

Volatility/volume genuinely dip at midday (same A-grade tick studies), but
the volume-adjusted result above complicates the simple "lunch lull"
story — much of the apparent calm is a volume artifact, not an independent
phenomenon. Practitioner sources describe this window as suited to
scalping/range strategies — plausible and consistent with the volatility
dip, but the "mean-reversion works best here" framing itself is opinion,
not backtested evidence.

## 3. Closing session (2:30-3:30/3:35 PM) — GRADE A on mechanics, real structural change incoming

U-shaped volatility uptick into the close is confirmed (same studies).
Zerodha's **current** auto-square-off (verified against Zerodha's own
support page, not older blog posts that still cite stale times) is
**3:25 PM for equity MIS** and **3:26 PM for equity F&O** — several
commonly-repeated "3:15/3:20 PM" figures online are outdated.

**Structural change, dated and real, not folklore**: NSE is launching a
formal **Closing Auction Session (CAS)** for F&O-eligible stocks, 3:15-3:35
PM, matching at an equilibrium price based on the 3:00-3:15 PM VWAP —
**launching 2026-08-03** (pre-open framework changes following
2026-09-07). Until now NSE has had **no formal closing auction for the
broad market** — the closing price has simply been the last-30-minute
VWAP. Since this hasn't launched yet as of today, **any claim about "how
the closing auction affects price" is necessarily untested** — this is a
live item to build a fresh hypothesis around once real data exists,
not something to assume from other exchanges' closing-auction behavior.

## 4. Pre-open (9:00-9:15) gap behavior — unresolved

The one academic study on this (Agarwalla, Jacob & Pandey 2014, cited in
`research/10` §5) measures price-discovery *efficiency*, not whether gaps
extend or fade after 9:15 specifically — it doesn't answer this question
either way. No dedicated study was found that does. Gap-fade/extend claims
circulating online are practitioner heuristics only (Grade C).

## 5. What Zerodha Varsity / NSE's own materials say

Targeted search of Zerodha Varsity found volatility/options/timeframe
content but **no dedicated content on time-of-day volatility patterns or
ORB specifically** — this isn't "house doctrine" the way some retail
sources imply. NSE's own "Market Pulse" publications exist but no located
report quantifies time-of-day patterns directly; the academic papers using
NSE data (not NSE's own publications) remain the actual primary-adjacent
source.

## Playbook — organized by evidence tier

**Solid (build on this with confidence):**
- Open and close are the highest-volatility/volume windows.
- Midday shows a genuine, if partly volume-driven, dip.
- Zerodha's real current square-off is 3:25 PM (MIS) / 3:26 PM (F&O) —
  use these exact times, not older cited values.
- The NSE Closing Auction Session is real and imminent (2026-08-03).

**Plausible, needs in-house validation before trusting:**
- ORB/first-15-minute strategies are profitable on NSE (real backtests
  exist, but not peer-reviewed or audited to this project's standard).
- Midday specifically favors mean-reversion/scalping over trend-following.

**Folklore/unsupported — do not hardcode:**
- Pre-open gaps reliably "fade" or "extend" in a predictable way.
- Precise doctrine like "9:15-9:45 = momentum only, avoid 3:20-3:30" as a
  taught rule — no Varsity or NSE source states this as house doctrine;
  it's retail repetition, not verified guidance.

## What this means for the plan

Feeds Layer 4 (Strategy/Signal Engine): time-of-day is a legitimate
regime-gating dimension (ties to the HMM/regime-detection work in
`research/01`), but every specific rule here — including the ones with
solid volatility evidence — still needs to go through the hypothesis
validation pipeline in `research/12` before being trusted for entries, not
assumed correct because a practitioner blog said so. The incoming Closing
Auction Session (2026-08-03) means any closing-session strategy work
should explicitly plan to re-validate once that mechanism goes live, since
no historical data reflects it yet.
