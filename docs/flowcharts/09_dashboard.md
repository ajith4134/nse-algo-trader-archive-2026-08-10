# 09 — Dashboard, Monitoring & Alerting (Layer 9)

**Status:** foundation built (v1) — read-model + control config + HTML
renderer + published browser-reachable dashboard. Rule-F verified from a
real paper run. Live two-way remote control (an exposed API) not enabled.

## Whole-pipeline data flow so far
```
[L1..L8 engine state]                          editable knobs
  paper ledger · §9 scoreboard · positions      (dashboard writes)
        │                                              │
        ▼                                              ▼
[Layer 9: dashboard/]                          TradingControlConfig
   build_dashboard_snapshot(control_config,       (JSON file the engine reads:
     paper_ledger, scoreboard, generated_at)       paper capital, min/max per
     -> DashboardSnapshot (JSON-serializable):      trade, segment on/off,
        layer roadmap · 16-trunk concept tree ·     strategy on/off, mode)
        paper summary · §9 lab table · win>loss
        │
        ▼
   render_dashboard_html(snapshot) -> standalone HTML
     (data views + interactive control panel, theme-aware, mobile)
        │
        ▼
   published Artifact  ── browser link, phone/laptop ──> operator
```

## Files
```
src/nse_algo_trader/dashboard/
├── __init__.py
├── project_status_data.py       # layer roadmap + 16-trunk/branch tree (static data)
├── trading_control_config.py    # editable config the engine reads (file-based)
├── dashboard_read_model.py      # build_dashboard_snapshot (observes engine)
└── render_dashboard_html.py     # snapshot -> standalone interactive HTML
tests/test_dashboard/test_control_config_and_read_model.py   # 9 tests
```

## What the dashboard shows (both views, one page)
- **Controls (interactive):** paper capital, max risk/trade, min/max
  capital per trade, per-segment on/off (cash / index-opt / stock-opt),
  per-strategy on/off (ORB / credit-spread), paper/live mode. Persist per
  device (localStorage); "Copy config JSON" exports the exact
  TradingControlConfig the bot reads.
- **Paper trading:** starting capital, realized P&L, fills, flat-at-close.
- **§9 lab:** WIN / deliberate-LOSS / UNCERTAIN tables with mean predicted
  prob, actual win rate, Brier; the CONFIDENT-WIN>CONFIDENT-LOSS check.
- **Layer roadmap:** all 11 layers with status + notes.
- **Concept tree:** all 16 trunks, each expandable to its branches, tagged
  with the layer it ignites at and gated markers.

## Accessibility (browser link, phone/laptop)
Published as a claude.ai Artifact — reachable from any device via its
link, theme-aware, responsive. The VPS exposes only SSH; no public web
port is opened. **The control panel is a real control plane, not
cosmetic:** it produces the `TradingControlConfig` JSON that
`load_trading_control_config` reads on the VPS. Flow: edit on phone ->
Copy config JSON -> place at `~/.nse_algo_trader/trading_control_config.json`
on the VPS (or paste in a session). Live two-way control (the phone
directly driving the running bot) would need an exposed authenticated
API — deferred, flagged, needs a firewall/port + auth decision.

## Verification (Rule F — real data, 2026-07-23)
- 9 tests (218 suite total, green).
- **Real-data pass:** snapshot built from a real 22-session INFY paper run
  (with slippage) -> realized P&L ₹72,274, 34 fills, flat; §9 tables
  CONFIDENT_WIN 12 @ 92% (Brier 0.087) / CONFIDENT_LOSS 4 @ 50%; 11 layers,
  16 trunks, 120 branch-tags rendered. HTML generated, snapshot injected
  (token replaced), published to the browser link.

## Remaining slices
- FastAPI read-model endpoint + WebSocket for a self-refreshing live app
  (the artifact is a snapshot; a running server gives live ticks).
- Wire the paper/live engine to actually READ TradingControlConfig for
  segment/strategy gating + sizing (config model exists; enforcement in
  the engine is the next wiring step).
- Alerting (breach/anomaly/unflattened-leg push).
- Advanced AI panels as their trunks mature (L10+).
