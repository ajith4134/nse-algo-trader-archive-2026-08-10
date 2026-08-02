# MASTER PROGRESS — the WHOLE plan at a glance (read FIRST every session + every sign-off)

**Purpose (Rule M — anti-fixation):** one page holding the ENTIRE plan at high altitude so no
area is ever forgotten while deep in another. This is an INDEX over `PLAN.md` (design),
`flowcharts/00_project_overview.md` (layer roadmap), `SYSTEM_MAP.md` (structure), `BACKLOG.md`
(deferrals). Keep current every sign-off. Status: 🟢 done · 🟡 partial · 🔴 not started · ⛔ blocked · ⏸ paused-by-user.
Last updated: **2026-07-27**.

## ⚠️ TRUE SCOPE = the AI CONCEPT-TREE ATLAS, not the 11 layers
The 11-layer roadmap below is the ENGINEERING scaffold. The project's actual ambition is the
**16-trunk / ~197-branch autonomous-AI concept tree** (`docs/research/32-36`; encoded in
`dashboard/project_status_data.py::CONCEPT_TREE`; dashboard "AI TRUNKS 16 · BRANCHES 197+").
**Coverage reality (2026-07-25): only ~40–55 of ~197 branches have ANY implementation (~70–80%
unbuilt).** Substantially built: **II SENSES, IV BODY** (the L1–6 substrate). Partial: **XIII
EPISTEMICS, IX PREDICTIVE-CORE, VI SOCIETY, XV MEMORY, XVI UNIVERSAL-ACCESS, I MIND, XI
GENERATIVITY**. **VII CONSCIENCE ✅ COMPLETE (14/14) + VIII SENTIENCE ✅ COMPLETE (13/13, 2026-07-26) — the
SUPREME safety trunk AND the integrator that binds the faculties into one mind are both fully built. ~Absent whole trunks: III WILL · V SELF · 
SENTIENCE/GLOBAL-WORKSPACE (the integrator that would bind the faculties) · X AUTOPOIESIS · XII
CURIOSITY · XIV AXIOLOGY.**
- **When assessing "what's left" / progress / altitude: reconcile against the ATLAS (branches),
  not just the layer table.** A layer/slice being done ≠ the atlas advancing. See memory
  `feedback_reconcile_against_16_trunk_atlas`.
- **`docs/AI_CONCEPT_TREE_STATUS.md` is the per-branch tracker** (🟢 built / 🟡 partial / 🔴
  unbuilt + implementing module) — READ IT at session start; every slice names which branch(es)
  it moves to 🟢 and updates the coverage %. **User goal (2026-07-25): drive ALL 197 branches to
  🟢 100%.** Current: **87/197 = 44.2% built** / 26% partial / 30% unbuilt. **✅ X AUTOPOIESIS COMPLETE (9/9, 2026-07-27)** — component-lifecycle homeostat, 14 modules, wired at all 4 entry sites + live dashboard surface. **VII ✅ + VIII ✅ COMPLETE; partials
  advancing (user: finish ALL partials before absent trunks): XIII 🔴-clear, IX 4🟢, XV 6🟢, VI 5🟢, II 6🟢
  + **sentiment/news COMPLETE 🟢 (S1 ingestion + S2 index S/R + S3 reliability + S4a-c acquisition/filings + S7 entry-gate)**
  (research/140+142-147; RSS→staleness→store; headlines→news_levels; curl_cffi static→Chromium fallback;
  NSE filings tier EXCHANGE_FILING; beta-reputation board filings 91%>news 67%>stale 50%; **S7 per-symbol news-event risk WIRED into the entry gate — advisory until earned; sense 🟡→🟢, atlas 65/197 33.0%**; OPEN BLOCKER: earning harness market-gated; S4d/S5-S6 + stock-option S/R queued).** Original: VII CONSCIENCE
  (safety) → VIII SENTIENCE/global-workspace (integrator) → finish strong-partials → absent trunks.

## Layers 1–11 (build roadmap)
| # | Layer | Status |
|---|-------|--------|
| 1 | Universe & Instrument Registry | 🟢 signed off |
| 2 | Market Data (real-time + historical) | 🟢 v1 (Kite) + 🟡 multi-broker: Kite/Breeze/Upstox/Angel LIVE, failover+gap-fill; ⏸ Fyers/Groww |
| 3 | Indicators / Features | 🟢 v1 |
| 4 | Strategy / Signal Engine | 🟢 v1 (ORB + ADX gate + credit spread) + 🟢 champion-challenger auto-tunes ORB (global + per-regime) |
| 5 | Risk Management | 🟢 v1 |
| 6 | Broker OMS | 🟢 v1 + 🟢 market-impact fills |
| 7 | Backtesting & Paper Trading | 🟢 v1 (24/7 router, §9 lab, DSR/CPCV gates) + §53 replay engine (below) |
| 8 | Session / Square-off | 🟢 signed off |
| 9 | Dashboard / Monitoring | 🟢 v1; outage FIXED; 🟢 #13 Feature-coverage panel; 🟢 Closed trades from PERSISTED memory; 🟢 **offline diagnostics mode — panels show+update from stored SQLite even after the daily Kite token expires (research/122, real-page verified)** |
| 10 | Memory & Reflection (learning AI) | 🟢 functionally complete + verified; 🟡 multi-regime queries (axis populated via 5b, variety accruing); ⛔ shadow-arm LIVE pass (market) |
| 11 | Strategic LLM / Autonomous-Research-Agent (generative AI) | 🟢 **generative slices 1–6 ALL DONE, REAL-DATA ✅** — swappable pool (+ keyless OVHcloud) + analyst + debate-as-risk-check + **LLM-risk entry-GATE at all 4 sites (calibration-gated)** + causal-cluster analyst + meta-strategy allocator + prediction-market council + **synthetic stress rehearsal**. 13/13 dashboard surfaces. Gate is in the decision path (self-gated); the rest advisory. 🟡 remaining: the queued DECISION-CONSUMERS (market-gated earn-harness) + Layer-7.5 rehearsal executor |

## §53 — market-closed real-market simulation (replay engine)
| Slice | Status |
|-------|--------|
| 1 Honest clock (day-walker + firewall + provenance) | 🟢 |
| 2 Point-in-time universe + corp-action adjust | 🟢 |
| 3 Prequential learning + provenance-separable memory | 🟢 |
| 4 Fidelity climb: Breeze 1s 🟢 (autonomous default-on, non-blocking bg build — #14) · multi-broker fleet 1m 🟢 built, 🟡 auto-activation opt-in until focus bounded · P4b depth recorder 🟡 built, ⛔ real capture (market) · depth consumers 🔴 |
| 5 ADVANCED: 5a curriculum 🟢 · 5b regime axis 🟢 · 5c-i champion-challenger 🟢 · 5c-i.b auto-reeval 🟢 · 5c-ii market-impact 🟢 · 5c-iii per-regime champion 🟢 · VPIN 🟢 · OFI/queue fills ⛔ (depth) |

## Cross-cutting / operational
- 🟢 Multi-broker adapters: Upstox, Angel One real-data verified; failover + gap-fill; fleet-in-loop (opt-in).
- ⏸ **Groww** (₹499/mo API sub) · ⏸ **Fyers** (creds) — paused by user until they provide.
- 🟢 **#13** dashboard Feature-coverage panel (Rule N) — all features surfaced (incl. VPIN) + coverage audit; closed trades from persisted memory.
- 🟢 **#14** high-fidelity replay prebuild non-blocking (background swap) → autonomous Breeze-1s replay back ON by default; fleet auto-activation still opt-in until its focus is bounded (low-pri follow-up).
- ⛔ **Market-gated:** P4b depth capture, shadow-arm live pass (need an open session).

## TOP REMAINING BIG-ROCKS (whole-plan priority order — re-pick from here, don't tunnel)
1. **Layer 7.5 control-arms lab** — 🟢 **ALL 4 DONE + real-verified** (research/95/106/107/108):
   RANDOM-CONTROL edge · skill-vs-luck COURT (verdict SKILL) · per-trade pre-mortem CVaR ·
   world-model scoreboard + profit provenance (total +9.7% = luck +0.8% + skill +9.0%). Read-only
   diagnostics; the acting consumers (train-on-skill-diagonal, CVaR sizing) are queued/market-gated.
2. **Layer 11 decision-consumers** (mostly market-gated) — turn the advisory LLM outputs into
   decisions via the shared calibration-gated earn-harness: analyst distrust, causal
   prediction-scoring, allocator sizing, council probability + reputation accrual, debate-risk
   runtime accrual (task #6). Accrue as live sessions run.
3. **§53 slice-5** — only depth-gated OFI/queue fills remain (market-gated). ADVANCED code-complete.
4. **Market/creds-gated & paused** — P4b depth capture, shadow-arm (open market); Groww/Fyers (user).
5. Small follow-ups: bound the fleet replay focus; per-feature dashboard drill-downs; reconcile
   free-tier model IDs from the provider-research pass. **LLM pool (2026-07-25):** keyless
   OVHcloud last-resort wired + real-verified; Pollinations rejected (anon 0-budget hard-402s on
   structured calls); pending USER keys — free: Scaleway/Hyperbolic/GitHub Models/Cohere; paid:
   Kimi `kimi-k3` (decision confirmed, research/99) + Anthropic. All drop in via `.env`, no code.

## How to use this (Rule M)
- **Session start:** read this + BACKLOG; say where we are in the WHOLE plan.
- **Every sign-off:** after the per-feature open items (Rule K), add a one-line altitude check —
  where the finished slice sits here + the top big-rocks above; re-pick next work from this list,
  not from whatever is locally adjacent.
- **Keep current:** update the touched rows every sign-off, same ritual as SYSTEM_MAP/BACKLOG.
