# 37 — Layer 9 Dashboard: Implementation Plan

**Origin:** user request (2026-07-23) before starting Layer 9: plan how to
build the dashboard that shows all completed steps, all features, AND the
16 trunks / ~200 branches. Also records the first real use of the two new
`sourcing-oss-parts` / `building-features-from-ideas` skills.

**Status: PLAN. Not built.** Layer 9 begins after Layer 8 sign-off.

---

## 1. What the dashboard is (two audiences, one app)
- **Operator view** — the real trading dashboard: live positions, P&L,
  orders, risk, mode (paper/live), session/square-off status. React SPA
  (decided PLAN §8a.2).
- **Project/AI view** — a living map of the build itself: layer roadmap
  status, the §9 prediction-tables lab with calibration, and the full
  **16-trunk / ~200-branch concept tree** with per-node status and the
  layer each faculty ignites at (research/32–36 + the integration map).

The published **build-console artifact** is the interim of the project
view; Layer 9 turns both views into one real running app.

## 2. Architecture
```
Python engine state (Layers 1–8)                     React SPA (Layer 9)
  paper ledger · prediction scoreboard · promotion   ┌───────────────────┐
  gate · square-off reports · risk gate · positions  │  operator view    │
        │                                             │  project/AI view  │
        ▼                                             └─────────▲─────────┘
  Dashboard read-model API (FastAPI)  ── JSON/WebSocket ────────┘
        │                                             concept-tree data
        └── serves: layer status, live state,         (from docs/research
            lab tables, tree nodes, alerts             32–36, integration map)
```
- **Backend:** a thin FastAPI read-model over the existing Python objects
  (no trading logic in the dashboard — it observes). WebSocket for live
  ticks/positions when the market is open; REST for snapshots.
- **Frontend:** React SPA. Static concept-tree data is generated from the
  research files into a JSON the tree view renders.
- **Interim bridge:** the artifact already renders the project view from
  hand-maintained HTML; Layer 9 replaces its data with the live API.

## 3. Panels (base tier — build first)
1. **Layer roadmap** — the 11 layers with real status + test counts
   (drives from PLAN/flowcharts).
2. **Live trading** — positions, P&L (realized/unrealized), orderbook/
   tradebook, **paper/live mode indicator** (impossible to mistake),
   per-strategy on/off.
3. **§9 lab** — the WIN / deliberate-LOSS / UNCERTAIN tables, calibration
   scoreboard (hit-rate, Brier, reliability curve), the CONFIDENT-WIN >
   CONFIDENT-LOSS check, Skill-vs-Luck verdict feed.
4. **Risk & session** — margin utilization, drawdown, per-strategy
   exposure, MWPL-ban context, square-off countdown + last SquareOffReport
   (unflattened legs alarm).
5. **The 16-trunk / ~200-branch tree** — interactive: expand trunk →
   branches → (later) twigs; each node shows status (built / ignites-L7 /
   matures-L10 / L11 / gated) and links to its research file. This is the
   panel the user specifically wants — the whole tree, navigable.

## 4. Panels (advanced tier — as trunks mature, Layer 10+)
AI self-explanation ("what it learned/why it traded"), knowledge-graph
browser (XV Memory), drive-stack state (III/W1), autonomy-level indicator,
alignment/goal-drift monitors, security/anomaly alerts, constitution &
off-switch status, Referee audit feed. Rendered as "coming online" until
their trunk exists — the tree panel already shows where they'll attach.

## 5. Sourcing plan (apply `sourcing-oss-parts` per piece)
Before hand-building each frontend part, source it:
- **Charts** (candles/equity/P&L, reliability curve): lightweight-charts
  (TradingView, Apache-2.0) or Recharts — source & pick per fit.
- **Tree/graph view** (16 trunks): react-arborist / d3-hierarchy — source.
- **Live table/grid** (positions, tables): TanStack Table — source.
- **State/data-fetching**: TanStack Query + WebSocket — source.
- **Backend read-model**: FastAPI (already Python) — reuse.
Each sourced piece: read README first, evaluate, vendor/depend, verify on
real engine data (Rule F), wire in (Rule G).

## 6. Build order (Rule A)
1. FastAPI read-model exposing current engine snapshots (layer status,
   ledger, lab scoreboard) — verified against the real paper run.
2. React shell + layer-roadmap panel (static-ish, real data).
3. Live trading panel (paper positions/P&L over a replay run first).
4. §9 lab panel (the calibration boards — real scoreboard data).
5. Concept-tree panel (generated tree JSON from research/32–36).
6. Risk/session panel.
7. Advanced-tier placeholders wired to the tree.

## 7. Sample sourcing finding recorded (skill test — CPCV, Layer 7 gap)
First run of `sourcing-oss-parts`, on the CPCV validation gate (PLAN §5
companion to the already-built Deflated-Sharpe gate):
- **Candidates:** `mlfinlab` (canonical, went commercial-licensed),
  `sam31415/timeseriescv` (purged k-fold + CPCV, sklearn), `purgedcv`
  (v0.1.2, MIT), `eslazarev/purged-cross-validation` (has a paper).
- **Winner: `purgedcv`** — MIT, scikit-learn splitter protocol,
  CI/tests/mypy, implements `CombinatorialPurgedCV` + purge/embargo +
  walk-forward AND PSR/DSR/MinTRL (overlaps our own
  `strategy_promotion_gate.py`). Early-stage (v0.1.2), so **vendor-and-
  adapt** the `CombinatorialPurgedCV` splitter rather than depend wholesale,
  and cross-check its DSR against our already-tested implementation.
- **Action (queued for the Layer 7 CPCV slice):** adapt purgedcv's CPCV
  splitter into the promotion gate; verify on real replayed folds.
This is the puzzle-piece method working: a tested piece found instead of
hand-deriving CPCV from the book.
