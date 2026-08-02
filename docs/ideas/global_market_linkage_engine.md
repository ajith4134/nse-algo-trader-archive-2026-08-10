# Global / cross-market linkage engine (GIFT Nifty + world markets → NSE)

**Seed (user):** *"AI that keeps track of other markets (USA etc) — how they opened/closed — to find the
relation/how they influence our market and predict NSE opening & close; and how GIFT Nifty influences
Nifty."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (research-verification owed — WebSearch exhausted) · feeds [idea #1](main_ai_brain_all_strategies.md) brain + [idea #4](dual_directional_ai_agents.md) bots

---

## 1. The bigger picture (expand-idea)
A **cross-market lead-lag / global-cues engine**: the NSE session is strongly conditioned by what
happened elsewhere while India slept + what's trading live. The category = **inter-market analysis +
overnight-gap / open-bias prediction**. Data lanes, by IST timing (the lead-lag *is* the structure):

| Lane | Instruments | Timing vs NSE (IST) | Role |
|---|---|---|---|
| **GIFT Nifty** (ex-SGX Nifty, NSE-IX GIFT City) | Nifty futures, ~06:30–02:30 trades ~21h | **pre-open + through session** | **the single strongest Nifty-open predictor** |
| **US (prev night)** | Dow/Nasdaq/S&P + futures, **VIX**, US10Y | closed ~02:00 IST | sets overnight gap tone |
| **Asia (live AM)** | Nikkei, Hang Seng, Shanghai, Kospi | overlaps NSE morning | intraday drift |
| **Europe (live PM)** | FTSE/DAX/CAC (open ~12:30–13:30 IST) | NSE afternoon | afternoon move |
| **FX / commodities** | **USDINR**, DXY, Brent crude, gold | live | sector + macro bias |
| **ADRs of Indian stocks** | INFY/HDFC/ICICI/WIT ADRs (NYSE) | prev US session | **single-stock open predictor** |

## 2. Methods
- **Lead-lag correlation + Granger causality** (which market leads NSE, at what lag) · **cointegration/
  VECM** (long-run linkage) · **overnight-gap predictor** (ML: predict NSE-open return from GIFT + US +
  ADRs + USDINR) · **regime-conditioning** (linkages strengthen in risk-off) · **ADR→stock open** for
  the F&O single names with US listings.
- OSS/data: statsmodels (Granger/VECM) · yfinance / investpy-style global indices · GIFT Nifty quote
  (NSE-IX / broker) · ADR data (US feed). [⚠️ exact free data sources for GIFT Nifty + global indices
  = owed verification.]

## 3. The decisive honest caveat (Rule O — surface it)
**The obvious gap is already PRICED IN by the open.** GIFT Nifty *is* the market's overnight estimate of
Nifty — by 09:15 the open gap largely reflects it, so "predict the gap from global cues" is mostly an
*efficiency* result, not tradeable alpha. Two real uses remain:
1. **Open-BIAS context feature** for the intraday bots/brain (regime tilt: risk-on/off, expected
   volatility, sector bias from crude/USDINR) — NOT a standalone gap trade.
2. **Residual / follow-through** edge: does NSE *over/under-react* to global cues intraday? (a testable,
   gated hypothesis) + **ADR-implied single-stock open** dislocations.
- **We are INTRADAY-ONLY (CLAUDE.md):** cannot hold overnight to capture a gap → the engine is a
  *conditioning/context* organ, never an overnight-carry strategy. Its output is evidence into the gate,
  not a trade.

## 4. Base → Advanced → Ultra
- **Base ✅:** GIFT-Nifty + US-close + USDINR → a daily **open-bias + expected-vol context** feature for the
  brain (risk-on/off regime tilt).
- **Advanced 🚀:** full lane set + Granger/VECM lead-lag map + ADR→stock open dislocation + intraday
  over/under-reaction signal, all gated.
- **Ultra 🌌:** learned cross-market state (which linkages are live *this* regime) feeding the regime
  classifier; sector-level global mapping (crude→energy, US10Y→IT/banks).

## 5. Feeds / wiring
Global-cues context → idea #1 regime classifier (open bias) + idea #4 bots (evidence feature) + the
online-research organ's macro lane (§2e #5). Reuse existing `participant_positioning` / `market_data`.

## 6. Owed (Rule K)
Verify: GIFT-Nifty live/historical data source + license · global-index + ADR free feeds · published
GIFT-Nifty↔Nifty-open correlation magnitude · intraday over/under-reaction evidence. Research pass queued
(WebSearch exhausted 2026-08-02).

## 7. Finalized decision _[pending research + user pick]_
