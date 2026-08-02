# Community / tipster signal harvesting → paper-trading experiment harness

**Seed (user):** *"the online-research organ should also collect data by opening blogs and communities that
give suggestions on stocks and predictions on the market and which stock to watch etc, to include them in
experiments on paper trading."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (research-verification owed — WebSearch exhausted) · extends [idea #4](dual_directional_ai_agents.md) organ + [idea #2](full_universe_opportunity_radar.md) radar

---

## 1. The bigger picture (expand-idea) — the right framing turns a trap into a filter
Naively "follow stock tips" = the retail-loss machine. The disciplined version = a **TIPSTER / EXTERNAL-
SIGNAL EVALUATION HARNESS**: treat **every external source as a HYPOTHESIS, and let paper trading be the
truth-filter.** Harvest → parse → auto-paper-trade → score per source → promote only survivors.

```
harvest calls (blogs/communities)  →  PARSE to structured {ticker, direction, entry/target/stop,
  horizon, source, publish_ts}      →  AUTO-PAPER-TRADE each call (point-in-time, net of cost)
  →  per-SOURCE ledger: hit-rate · net-EV · sample-N · DSR/FDR  →  PROMOTE survivors / CULL noise
  →  promoted sources = one GATED evidence feature into the bots/radar; crowd aggregate = sentiment feature
```
This is the perfect use of the paper-trading engine you already have — **paper trading as a source-
validation lab**, not as a place to blindly copy tips.

## 2. Sources to harvest (behind the Dual-LLM quarantine, low-trust tier)
X/Twitter "fintwit" · **Telegram tip channels** · Reddit (r/IndianStreetBets, r/DalalStreetTalks) ·
Moneycontrol forums/messages · **TradingView ideas** · StockTwits-analog · finance blogs/newsletters ·
YouTube call transcripts (ytgrab) · Trendlyne/Tickertape analyst calls. Collected via the §2d organ
(crawl4ai/browser-use/RSS/API) → parsed by the **quarantined reader** into inert structured calls (never
executed as text instructions).

## 3. The scoring harness (the actual engine)
- **Per-source arm:** every source = a bandit arm / tracked hypothesis. Log every call, auto-paper-trade
  it with the **real cost model + real fills** (Rule F), resolve win/loss, accrue per-source stats.
- **Gates before any weight:** minimum sample-N · **hit-rate + net-of-cost edge** · **Deflated Sharpe /
  BY-FDR** (many sources scanned = multiple testing — idea #2 Wall-2) · liquidity + **F&O-ban/circuit**
  filter on tipped names (tips cluster in illiquid pumpable names — exclude).
- **Point-in-time:** timestamp each call at **publish_ts**; paper-trade only from `bot_observed_ts` (no
  look-ahead — the org's §7-news rule).
- **Output:** a **source-reliability leaderboard**; promoted sources feed a *gated* evidence feature;
  aggregate crowd direction = a **contrarian/confirmation sentiment** feature (crowd extremes often fade).

## 4. The decisive honest caveat (Rule O — surface it)
**Most tipster "edge" is illusory** — survivorship (loud accounts cherry-pick wins), selection bias,
**pump-and-dump** on illiquid names (following = being exit liquidity), and front-running (you see the tip
late). SEBI actively prosecutes finfluencer manipulation. → **The harness's PRIMARY value is proving most
sources are NOISE** (and occasionally surfacing a rare real one), plus the aggregate-sentiment feature.
**Never** trade a tip live until its source is promoted + validated, and even then it is ONE gated evidence
input, never a standalone trade. This is a *research/experiment* organ, not a copy-trading feature.

## 5. Base → Advanced → Ultra
- **Base ✅:** harvest a few sources → parse calls → auto-paper-trade → per-source hit-rate leaderboard.
- **Advanced 🚀:** full source set · DSR/FDR promotion gate · liquidity/ban filters · crowd-sentiment
  aggregate feature · NLP call-parsing (which stock, which direction, target/stop).
- **Ultra 🌌:** the meta-model learns *which source types* pay in *which regime*; contrarian signals from
  crowd extremes; auto-detect coordinated pump patterns (avoid + flag).

## 6. Wiring / reuse
Reuse existing **paper_trading** loop + **experience memory** ledger + **news_sentiment**. Promoted-source
feature → idea #4 bots + idea #2 radar candidates. New: a `source_reliability_ledger` + call-parser.

## 7. Owed (Rule K)
Verify: harvestable community/tip sources + access (Telegram API, Reddit API, TradingView ideas, StockTwits-
analog for India) · finfluencer-manipulation/SEBI legal boundary (harvest for research OK; never amplify/
distribute) · published evidence on tipster hit-rates. Research pass queued (WebSearch exhausted 2026-08-02).

## 8. Finalized decision _[pending research + user pick]_
