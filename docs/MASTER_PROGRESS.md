# MASTER PROGRESS — the WHOLE plan at a glance (read FIRST every session + every sign-off)

**Purpose (Rule M — anti-fixation):** one page holding the ENTIRE plan at high altitude so no
area is ever forgotten while deep in another. This is an INDEX over `PLAN.md` (design),
`flowcharts/00_project_overview.md` (layer roadmap), `SYSTEM_MAP.md` (structure), `BACKLOG.md`
(deferrals). Keep current every sign-off. Status: 🟢 done · 🟡 partial · 🔴 not started · ⛔ blocked · ⏸ paused-by-user.
Last updated: **2026-07-25**.

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
| 9 | Dashboard / Monitoring | 🟢 v1; outage FIXED (2026-07-25); 🔴 **#13 no panels for new features** |
| 10 | Memory & Reflection (learning AI) | 🟢 functionally complete + verified; 🟡 multi-regime queries (axis populated via 5b, variety accruing); ⛔ shadow-arm LIVE pass (market) |
| 11 | Strategic LLM / Autonomous-Research-Agent (generative AI) | 🔴 NOT STARTED — deferred until L10 validated (runtime/market-gated, not code-gated) |

## §53 — market-closed real-market simulation (replay engine)
| Slice | Status |
|-------|--------|
| 1 Honest clock (day-walker + firewall + provenance) | 🟢 |
| 2 Point-in-time universe + corp-action adjust | 🟢 |
| 3 Prequential learning + provenance-separable memory | 🟢 |
| 4 Fidelity climb: Breeze 1s 🟢 (autonomous default-on, non-blocking bg build — #14) · multi-broker fleet 1m 🟢 built, 🟡 auto-activation opt-in until focus bounded · P4b depth recorder 🟡 built, ⛔ real capture (market) · depth consumers 🔴 |
| 5 ADVANCED: 5a curriculum 🟢 · 5b regime axis 🟢 · 5c-i champion-challenger 🟢 · 5c-i.b auto-reeval 🟢 · 5c-ii market-impact 🟢 · 5c-iii per-regime champion 🟢 · VPIN 🔴 · OFI/queue fills ⛔ (depth) |

## Cross-cutting / operational
- 🟢 Multi-broker adapters: Upstox, Angel One real-data verified; failover + gap-fill; fleet-in-loop (opt-in).
- ⏸ **Groww** (₹499/mo API sub) · ⏸ **Fyers** (creds) — paused by user until they provide.
- 🔴 **#13** dashboard panels for new features (multi-broker, curriculum, champion-challenger, market-impact, regime memory) — built ≠ displayed.
- 🟢 **#14** high-fidelity replay prebuild non-blocking (background swap) → autonomous Breeze-1s replay back ON by default; fleet auto-activation still opt-in until its focus is bounded (low-pri follow-up).
- ⛔ **Market-gated:** P4b depth capture, shadow-arm live pass (need an open session).

## TOP REMAINING BIG-ROCKS (whole-plan priority order — re-pick from here, don't tunnel)
1. **#13** — surface ALL features on the dashboard (systematic registry + coverage audit; research/91). ← NEXT
2. **§53 slice-5 finish** — VPIN; then depth-gated items when P4b depth accrues.
3. **Layer 11 (LLM/agentic AI)** — the big net-new area, once L10 validation accrues (runtime/market-gated).
4. **Market/creds-gated & paused** — P4b depth capture, shadow-arm (open market); Groww/Fyers (user).
5. Small follow-ups: bound the fleet replay focus so fleet auto-replay can be default-on too.

## How to use this (Rule M)
- **Session start:** read this + BACKLOG; say where we are in the WHOLE plan.
- **Every sign-off:** after the per-feature open items (Rule K), add a one-line altitude check —
  where the finished slice sits here + the top big-rocks above; re-pick next work from this list,
  not from whatever is locally adjacent.
- **Keep current:** update the touched rows every sign-off, same ritual as SYSTEM_MAP/BACKLOG.
