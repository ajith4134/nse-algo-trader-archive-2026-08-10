# Kite-decoupled architecture — independent dashboard + bounded broker adapter

**Seed (user):** *"instead of all features and dashboard relying on Kite, create a separate dashboard
independent of Kite; the Kite paper + live trading exist INSIDE that dashboard; and all other features
except paper/live trading live OUTSIDE Kite."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring · cross-cutting architectural CONSTRAINT on every feature

---

## 1. The bigger picture (expand-idea) — a hard broker boundary
Category = **broker-boundary / hexagonal architecture**: isolate Kite behind ONE seam so the ENTIRE rest
of the organism runs without a Kite session. Kite is a **pluggable "execution + live-feed adapter"**
(swappable for Upstox/Angel/ICICI/Groww or stored data — CLAUDE.md already says data-sourcing is not
Kite-only + "no Kite specifics outside the broker layer"). This directive REALIZES + hardens that rule and
extends it to the **dashboard**.

**INSIDE the Kite boundary (the only Kite-dependent parts):**
- Live tick feed (though this is *also* multi-source: Upstox/Angel/... + replay).
- **Order placement — paper + live trading.**
- Broker session / daily token (KiteAccessTokenFileStore).
These live as ONE bounded module ("Live/Paper Trading") — a panel inside the dashboard that shows a clear
**"broker session required"** state when Kite is absent, and pauses gracefully (never crashes the rest).

**OUTSIDE the boundary (Kite-INDEPENDENT — must run with no Kite session):**
- The **dashboard shell** + ALL feature surfaces (engines, research, coverage, atlas, health).
- ALL intelligence/analysis: the brain, BULL/BEAR bots, radar, regime, memory, validation, cost engine,
  news/online-research organs, LLM gateway, the whole atlas — on **stored / replayed / independent-source**
  data. Analysis is never blocked by live-data absence (Rule F/J: stored/replay is first-class).

## 2. The problem today (why this is a refactor)
`dashboard_server` boots the Kite-dependent live-paper loop and drops to "OFFLINE DIAGNOSTICS mode" when
the token is invalid — i.e. the WHOLE dashboard degrades on Kite absence. The decoupling: the dashboard +
every non-execution feature render + run fully **regardless of Kite**; only the Live/Paper panel reflects
broker state.

## 3. Design (the seam)
```
                 ┌────────────── KITE-INDEPENDENT CORE (always runs) ──────────────┐
   data:  stored │ dashboard shell · all engines/organs · research · memory ·      │
   / replay /    │ validation · LLM gateway · brain · radar · coverage · atlas     │
   Upstox/Angel  └───────────────────────────┬────────────────────────────────────┘
                                             │ reads a Kite-INDEPENDENT read-model
                 ┌───────────────────────────▼──── BROKER BOUNDARY (one seam) ─────┐
                 │ ExecutionAdapter (Kite today; Upstox/Angel swappable) +          │
                 │ LiveFeedAdapter — used ONLY by the Live/Paper Trading module.    │
                 │ Absent/expired → module shows "broker session required", pauses; │
                 │ the core above is UNAFFECTED.                                    │
                 └─────────────────────────────────────────────────────────────────┘
```
- **Reuse:** `broker_oms`(8) + `broker_sessions`(8) are the seam already; the fix = ensure NOTHING outside
  them imports Kite, and the dashboard/read-model never *requires* a live broker to render.
- **Data independence:** a data-source abstraction (Kite | Upstox | Angel | stored/replay) feeds analysis;
  live trading needs a broker, analysis does not.

## 4. Why it matters (honest value)
- **24/7 resilience:** research/analysis/LLM/backtest run when market is closed or the token expired — the
  organism is productive off-hours, not "OFFLINE".
- **Swappability:** switching brokers (or adding Upstox as data) touches only the adapter.
- **Testability:** the whole core is testable with stored data behind the seam (Rule J), no live broker.

## 5. Base → Advanced → Ultra
- **Base ✅:** dashboard shell + all non-execution surfaces render with NO Kite session; Live/Paper panel
  shows broker state and pauses cleanly when absent.
- **Advanced 🚀:** a formal `DataSourceAdapter` (Kite/Upstox/Angel/stored) so analysis is source-agnostic;
  `ExecutionAdapter` fully swappable; a lint/architecture test that FAILS if `kiteconnect` is imported
  outside `broker_*`.
- **Ultra 🌌:** hot broker failover (Kite down → Upstox for data), multi-broker execution routing.

## 6. Cross-cutting constraint (governs the build order)
This is not one feature — it's a **rule on every feature**: no module outside `broker_oms`/`broker_sessions`
may depend on Kite; the dashboard + core must boot and run with no broker. Added to `MASTER_BUILD_ORDER`
as a Phase-0 architectural gate + a governing memory (`feedback_kite_decoupled_architecture`).

## 7. Owed (Rule K)
Audit: grep for `kiteconnect`/Kite imports outside `broker_*` (find the leaks) → an architecture test.
Refactor `dashboard_server` boot so the core renders Kite-independent; the Live/Paper module isolates the
broker dependency. Sourcing (owed): a data-source abstraction pattern (WebSearch reset).

## 8. Finalized decision _[pending — recommend do the leak-audit first, then the dashboard boot refactor]_
