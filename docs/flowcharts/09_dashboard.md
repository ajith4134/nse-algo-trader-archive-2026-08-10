# 09 — Dashboard, Monitoring & Alerting (Layer 9)

**Status:** core built (v1) — read-model + control config & enforcement +
redesigned browser dashboard + **two-way live control API (server mode)** +
monitoring alerts + auto-refresh. Rule-F verified. Deferred: push alerts,
live WebSocket tick feed (blocked on an open session), advanced AI panels
(Layer 10).

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
  16 trunks, 197 branch-tags rendered (16 trunks). HTML generated, snapshot injected
  (token replaced), published to the browser link.

## Remaining slices
- FastAPI read-model endpoint + WebSocket for a self-refreshing live app
  (the artifact is a snapshot; a running server gives live ticks).
- Wire the paper/live engine to actually READ TradingControlConfig for
  segment/strategy gating + sizing (config model exists; enforcement in
  the engine is the next wiring step).
- Alerting (breach/anomaly/unflattened-leg push).
- Advanced AI panels as their trunks mature (L10+).

## HTTP server slice (added 2026-07-23) — the browser link
```
src/nse_algo_trader/dashboard/dashboard_server.py   # FastAPI app
```
- `python -m nse_algo_trader.dashboard.dashboard_server` serves the
  dashboard on `0.0.0.0:8080`, capability-token gated (`?key=...`).
- Endpoints: `GET /` (dashboard HTML, live mode), `GET /api/snapshot`,
  `GET /api/config`, **`POST /api/config`** (validates + writes the
  `TradingControlConfig` file the engine reads — TWO-WAY live control),
  `POST /refresh` (re-runs the paper lab). New deps: fastapi, uvicorn.
- Token persisted at `~/.nse_algo_trader/dashboard_access_token.txt`.
- **Verified locally (Rule F):** GET / -> 403 without key / 200 with key;
  POST /api/config persisted `account_virtual_capital` + segment toggle to
  the real config file. The dashboard's control panel POSTs edits live when
  served from the server (localStorage fallback in artifact mode).

## Exposure status (needs two out-of-band steps — deliberately not
## auto-done, they expose a port to the internet)
1. **OS firewall:** `sudo firewall-cmd --permanent --add-port=8080/tcp &&
   sudo firewall-cmd --reload` (auto-blocked for the agent; the user runs
   it).
2. **OCI VCN security list:** add an ingress rule 0.0.0.0/0 -> TCP 8080 in
   the Oracle Cloud console (only the account owner can).
Then reachable at `http://<public-ip>:8080/?key=<token>` or via the free
`http://<public-ip>.sslip.io:8080/?key=<token>` (no domain registration).
**Security:** capability-token gated; paper-only today. Before ANY live
trading is exposed, real auth (login) + HTTPS are mandatory — flagged.
Permanence across reboots wants a systemd unit (a later slice).

## Config enforcement + visual redesign (added 2026-07-23)
- `config_enforced_paper_run.py`: `map_control_config_to_risk_budget`
  (paper capital + risk% + max-capital-per-trade cap -> RiskBudgetConfig),
  `is_orb_cash_trading_enabled` (segment+strategy gate),
  `clamp_quantity_to_capital_limits` (min/max capital per trade),
  `run_config_enforced_orb_paper_lab`. The server re-runs the enforced lab
  per request, so toggling a segment/strategy off empties the results.
  9 tests; verified: cash-segment OFF -> 0 fills, ON -> fills return.
- `render_dashboard_html.py` redesigned: KPI tiles, card layout with depth,
  toggle switches, colour-coded P&L, calibration bars, collapsed JSON,
  indigo accent + semantic green/red, theme-aware, mobile-first (was
  all-mono/plain).
- **Ops lesson:** `pkill -f dashboard_server` self-matches the launching
  shell (its cmdline contains the pattern) and SIGKILLs it — silent exit 1.
  Kill with the bracket trick `ps|grep '[d]ashboard_server'` instead.
  Server must be launched outside the agent sandbox (network bind blocked
  in-sandbox).

## Monitoring & alerting (added 2026-07-23)
- `monitoring_alerts.py`: `generate_dashboard_alerts(config, ledger,
  scoreboard, kite_token_valid, stored_bar_count) -> list[MonitoringAlert]`
  with `AlertLevel` INFO/WARNING/CRITICAL. Conditions: LIVE mode (warn),
  open position / no-overnight breach (CRITICAL), CONFIDENT-WIN not
  beating CONFIDENT-LOSS (calibration warn), expired Kite token (warn),
  no stored bars (warn), else a single "all nominal" INFO.
- Wired into `DashboardSnapshot.alerts`; the server passes real token
  validity (`KiteAccessTokenFileStore.load_if_still_valid`) and bar count.
- Rendered as a prominent alerts banner (critical first, colour-coded).
- 6 tests (235 total green); verified live: healthy state -> "all nominal".

## Layer 9 status
**Core built (v1):** read-model · editable control config + enforcement
(toggles gate trading) · browser-reachable dashboard (redesigned,
theme-aware, mobile) · two-way live control API · monitoring/alerts —
all Rule-F verified. **Remaining/deferred:** push alerting (Telegram/
email channel) · live WebSocket tick feed (blocked on an open market
session + KiteTicker auth) · advanced AI panels (self-explanation,
knowledge-graph browser — arrive as Layer 10 trunks mature).

## Auto-refresh (added 2026-07-23)
The dashboard's live sections (alerts, KPIs, paper results, §9 lab) now
re-render from a 20s poll of `/api/snapshot` in server mode (guarded by
`LIVE_API_KEY`; artifact mode stays static). Render logic refactored into
`renderLive(snap)`, called on load and each poll. Verified: page + snapshot
API both 200. This is the last non-blocked Layer 9 slice; remaining
(push alerts, live tick feed, advanced AI panels) are channel/market/L10
gated.
