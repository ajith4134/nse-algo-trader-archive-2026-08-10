# 03 — OpenAlgo Deep-Dive (Verified)

Companion to `02_broker_abstraction_framework_alternatives_research.md`
(that file ranks OpenAlgo against alternatives; this file is the detailed,
cited deep-dive on OpenAlgo alone, since it's the closest existing match to
"paper and live trade with no code difference").

**Status: research only, nothing implemented.**

## Bottom line

OpenAlgo (`github.com/marketcalls/openalgo`) is real, actively maintained
(AGPL-3.0), and genuinely uses one code path for paper vs. live trading — a
mode flag routes the same API calls to either a simulated sandbox or the
real broker. But its own docs are explicit that simulated fills are not a
realistic exchange emulator, and some features (e.g. GTT orders) aren't
implemented in sandbox mode at all.

## What it is / architecture

Self-hosted web app, not a pip-installable library. Backend: Flask 3.0 +
SQLAlchemy 2.0, Flask-SocketIO, ZeroMQ for message distribution. Frontend:
React 19 + TypeScript, Vite, Tailwind. Exposes a REST API (`/api/v1/`), a
hosted Python-strategy runner, and a no-code "Flow" builder. Repo language
mix: Python 76%, TypeScript 21% (github.com/marketcalls/openalgo, fetched
2026-07-23).

## Paper vs. live — the key claim, checked skeptically

Confirmed (docs.openalgo.in, Jul 2026): a single boolean toggle
(`POST /api/v1/analyzer/toggle`, `mode: true/false`) switches ALL
order/account endpoints between a sandbox backend
(`sandbox/order_manager.py`, isolated `db/sandbox.db`, ₹1 Cr virtual
capital, simulated margin/T+1/auto-square-off) and the live broker modules.
The API surface a strategy calls is identical in both modes — genuinely one
code path.

**But**: the docs themselves flag this is not a true exchange emulator —
"broker-specific RMS checks, queue priority, slippage, partial fills,
outages... can differ from Analyzer results" — and Analyzer GTT operations
return HTTP 501 (unimplemented)
(docs.openalgo.in/new-features/api-analyzer). GitHub issue #1640
("Holding in Sandbox are not getting sold," 2026-07-16) is a live example of
sandbox-vs-real divergence. No independent Reddit/forum litigation of this
specific claim was found either way — unverified, not refuted.

## Broker support / abstraction quality

34 broker plugins (33 Indian brokers — Zerodha Kite, Angel One, Upstox,
Fyers, 5paisa, AliceBlue, Shoonya/Finvasia, Dhan, etc. — plus Delta Exchange
for crypto). Abstraction is real but loose: a documented adapter pattern
normalizes order/symbol data into an "OpenAlgo common format," but the
integration docs admit broker-specific payloads aren't exhaustively
identical across all 34 plugins — a convention layer, not a strictly
enforced interface. Open bugs (#1647 Dhan SL-M→LIMIT conversion, #1658 Delta
Exchange P&L miscalculation) show per-broker rough edges.

## Dashboard

Real-time positions, orderbook/tradebook, P&L, WebSocket-streamed
quotes/orders, Telegram alerts, and 12 options-analytics tools (Greeks, IV
Smile, Max Pain, GEX).

## Deployment model

Both hosted Python strategy scripts (IST scheduling, process isolation) and
a drag-and-drop "Flow" builder, plus webhook-style external signals
(TradingView, Amibroker, ChartInk, Excel/Sheets, MetaTrader) and an MCP
server for AI-agent integration.

## License / maturity

AGPL-3.0 (modifications used to offer a network service must also be
open-sourced — relevant only if we ever resold/hosted a derivative for
others, not for personal use). 2,302 stars, 1,093 forks, 239 open issues,
55 releases (latest v2.0.1.5, 2026-07-10), last push 2026-07-23, created
Feb 2024 (api.github.com/repos/marketcalls/openalgo).

## Limitations

Steep learning curve requiring Python fluency; explicit "educational use,
use at own risk" disclaimer; feature completeness (GTT, OCO) varies by
broker/mode.

## What this means for us

Do not adopt OpenAlgo wholesale — see the recommendation in
`02_broker_abstraction_framework_alternatives_research.md` (build the
broker-abstraction layer in-house, borrowing Freqtrade's `dry_run`-flag
pattern and NautilusTrader's client-interface split). OpenAlgo's dashboard
feature list and options-analytics tools are still a useful reference for
what our own dashboard should eventually cover — see `../PLAN.md`.
