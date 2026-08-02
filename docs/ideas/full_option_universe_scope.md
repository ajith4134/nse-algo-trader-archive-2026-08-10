# Full option universe scope (index incl. Bank Nifty + all stock options)

**Seed (user's words):** *"in option: index options as Bank Nifty etc AND option stocks universe"* —
i.e. the option segment must cover ALL index options (NIFTY + Bank Nifty + FINNIFTY + MIDCPNIFTY + …)
AND the full stock-options universe (~200 F&O underlyings), all contracts (ATM/ITM/OTM ladders).
**Date:** 2026-08-02 · **Status:** 🔵 exploring (2 research agents) · refines [idea #1](main_ai_brain_all_strategies.md) + [idea #2](full_universe_opportunity_radar.md)

---

## 1. The bigger picture (expand-idea)

This is the **option-segment scope definition** shared by the brain (idea #1) and the radar (idea #2).
The full NSE option universe = **~5 index underlyings + ~200 stock F&O underlyings × every strike ×
every listed expiry ≈ tens of thousands of live contracts** (project already has instrument-master
support for this — BACKLOG B34: ~28k contracts, 5 indices + ~208 stock underlyings → **REUSE, don't
rebuild**; source = Kite `/instruments` NFO dump).

**The load-bearing reframe (ties to idea #2's walls):** "full universe" = breadth of what we **WATCH**,
NOT breadth of what we **TRADE**. Two hard realities collapse the tradeable set:
1. **Current structure (SEBI Oct-2024):** only **NIFTY keeps WEEKLY** on NSE (SENSEX on BSE); **Bank
   Nifty / FINNIFTY / MIDCPNIFTY are MONTHLY-only now.** → no weekly-theta / 0DTE play on Bank Nifty;
   monthly premium-selling + directional/hedged instead. [→ agent-A confirm.]
2. **Liquidity + settlement:** index ATM near-expiry options are deeply liquid; **most stock-option
   strikes and far months are thin/untradeable**, and **stock options are PHYSICALLY settled** (delivery/
   assignment + escalating expiry-week margins + ITM auto-exercise STT trap). [→ agent-B.]

So the universe is scanned **wide** (all underlyings, full ladder) but **filtered to a liquid tradeable
subset** (OI/volume/spread, near-ATM band, nearest 1–2 expiries) before anything trades — exactly idea
#2's throughput (Wall-3) + net-EV (Wall-1) gates.

## 2. How it plugs into the two locked ideas
- **Idea #1 (brain + engine library):** the engine library must span **index options (weekly NIFTY +
  monthly Bank Nifty/others) AND stock options** — but strategy applicability DIFFERS by underlying (see
  §4). Engine #1 stays NIFTY-weekly premium-seller; Bank Nifty premium-selling is monthly, stock-option
  premium-selling is risky (single-name gap + physical settlement) → mostly directional/hedged there.
- **Idea #2 (radar):** option scope = the full universe as CANDIDATES, dynamically laddered ATM/ITM/OTM
  per underlying from spot, filtered to liquid tradeable contracts. Bank Nifty + liquid stock options
  enter the scan; illiquid stock strikes are pre-filtered out (never subscribed — Kite 9k ceiling).

## 3. Full option-universe composition (agent-A) ✅
| Index | Exch | Weekly? | Expiry day | Lot* |
|---|---|---|---|---|
| **NIFTY 50** | NSE | **Yes — only NSE weekly** | Tue | 65 |
| BANKNIFTY | NSE | monthly-only | last Tue | 30 |
| FINNIFTY | NSE | monthly-only | last Tue | 60 |
| MIDCPNIFTY | NSE | monthly-only | last Tue | 120 (⚠️75 stale) |
| NIFTY NEXT 50 | NSE | no | monthly | ⚠️ |
| **SENSEX** | BSE | **Yes — only BSE weekly** | Thu | 20 |
| BANKEX | BSE | monthly-only | ⚠️ | ⚠️ |
*\*Lot sizes are the #1 stale-risk figure (revised to keep notional in SEBI's ₹15–20L band; a resize wave hit Jan-2026) → **pull live, never hardcode.***
- **Stock F&O:** **~214 stocks** (Aug-2026, growing via quarterly review). Tightened eligibility Aug-2024
  (MQSOS ₹75L · MWPL ₹1,500cr · ADDV ₹35cr, all three); 3-month-continuous-fail → exit. **Monthly-only,
  physically settled** (since Oct-2019).
- **Contract count (derived, not sourced):** indices ~2–3k + stocks ~17–25k ≈ **20,000–30,000+ live
  contracts**. NIFTY has the deepest ladder (weekly+monthly+quarterly+LEAPS, 50-pt strikes, extra strikes
  in high-vol).
- **Liquidity:** NIFTY dominates NSE options volume; stock options thin outside top names (stock-option
  premium ~₹8k cr/day « index); index-options turnover fell 9% premium / 29% notional post-Oct-2024.
- **Programmatic source (authoritative):** **Kite `/instruments/NFO`** — daily gzipped CSV
  (`tradingsymbol, expiry, strike, lot_size, instrument_type CE/PE/FUT, segment`). Fetch once ~08:30 IST,
  cache. **⚠️ KEY on exchange+tradingsymbol — `instrument_token` is REUSED after a contract expires** (a
  silent primary-key corruption trap). Strike-interval table = pull live (NSE re-tunes it). → **reuse the
  project's existing kite_instrument_master (B34), verify the token-reuse guard.**

## 4. Strategy × underlying applicability (agent-B) ✅
- **Bank Nifty:** monthly-only since **Nov 20 2024** (last weekly Nov 13). Higher beta — daily range
  ~1.3–1.8% vs Nifty 0.7–1%, **IV 30–50% higher** (blog-grade). → theta/pinning only in the **final
  expiry week**; mid-cycle = directional/hedged (slower decay, more capital). ANMI petitioning to
  restore weekly (not reversed as of late-2025).
- **Index vs stock — the core split:** index = **cash-settled + deep ATM liquidity** (full strategy
  spectrum); stock = **physically settled** (~182–185 underlyings), **liquid only in ~20–30 large caps**;
  gap/news + **corporate-action** risk (strike/lot adjust on div≥2%/split/bonus/rights; merger can zero
  ITM) + **STT-exercise funding shock** (~16% profit-erosion example) + escalating expiry-week delivery
  margin.
- **Scanner filters (the tradeable-subset gate):** liquidity-**tier** underlyings (Tier-1 top ~20–30) ·
  OI/volume floors + **bid-ask spread cap** (does most of the index-vs-stock separation) · dynamic
  **ATM±N band** (`round(spot/interval)*interval`; N smaller for illiquid) · **nearest 1–2 expiries
  only** · **MWPL F&O-ban: exclude at OI≥95%, re-admit <80%** (hysteresis) → close-only · corporate-
  action suspend around ex-date · **stock-option expiry-week close-out (T-1/T-2)** to dodge forced delivery.
- **Strategy × underlying matrix:** weekly index (NIFTY) → ALL structures; monthly index (Bank Nifty
  etc.) → expiry-week theta / directional / hedged; **liquid stock → directional / vertical / covered-
  call (NOT naked selling — gap + physical settlement)**; illiquid stock → avoid.
- ⚠️ Gaps flagged: exact STT-exercise rate, post-ban Bank Nifty volume series, production OI/spread
  thresholds (proprietary — treat as tunable). Full citations in run notes.

## 5. Base → Advanced → Ultra
- **Base ✅:** NIFTY weekly + Bank Nifty monthly + top ~10–20 most-liquid stock options, near-ATM ladder,
  liquidity-filtered. (matches idea #2 liquid-subset-first.)
- **Advanced 🚀:** all 5 indices + all liquid stock options, full ATM/ITM/OTM ladders, per-underlying
  strategy routing (weekly vs monthly vs physical-settled).
- **Ultra 🌌:** the entire ~28k-contract universe scanned via multi-key sharding, dispersion (index vs
  single-stock vol), cross-underlying skew RV — earned once the base makes money.

## 6. Open questions (to finalize)
1. Which underlyings in the FIRST tradeable cut — NIFTY + Bank Nifty + top-N liquid stocks (recommend),
   or all indices immediately?
2. Do we trade stock-option premium-selling at all (physical-settlement + gap risk), or keep stock
   options directional/hedged only at first?
3. Bank Nifty (monthly-only) — premium-seller engine, or directional/hedged only?

## 7. Research findings [2 agents]
_[agent-A composition · agent-B index-vs-stock nuances — integrated on completion, cited.]_

## 8. Finalized decision (synthesis — recommendation; confirm/override anytime)

**This is a scope-lock, low genuine ambiguity — the evidence determines it:**
1. **Watch WIDE, trade a LIQUIDITY-GATED subset.** Enumerate the whole ~20–30k-contract universe from
   **Kite `/instruments/NFO` daily** (reuse project's kite_instrument_master, B34; verify the
   token-reuse/exchange+tradingsymbol guard). Scan all underlyings; admit to tradeable only the
   liquidity-tiered subset (OI/volume/spread + ATM±N + nearest 1–2 expiries + not-in-F&O-ban).
2. **Tradeable tiers at launch:** **NIFTY weekly** (the theta engine home) + **Bank Nifty monthly**
   (expiry-week theta / directional-hedged) + **top ~20 liquid stock options**. Scale wider via idea-#2
   sharding once proven.
3. **Stock options = directional / vertical / covered-call ONLY — NO naked premium-selling** (single-name
   gap + physical settlement + STT-exercise + corporate-action risk). Recommended default; override if you
   explicitly want stock theta.
4. **Bank Nifty:** monthly — theta only in the final expiry week; else directional/hedged (higher beta/IV).
5. **Never hardcode lot sizes/strike intervals** — pull live daily.

**Feeds:** idea #1's engine library (per-underlying strategy routing) + idea #2's radar (option scan
scope). Prereq shared: Greeks/IV engine, cost engine, risk gate, the instrument-master universe loader.

**🟢 LOCKED on the above recommended defaults (2026-08-02)** — the one open user choice is #3 (stock-option
premium-selling: default OFF). Tracked in docs/BACKLOG.
