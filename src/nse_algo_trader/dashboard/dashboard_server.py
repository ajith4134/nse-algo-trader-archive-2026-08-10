"""FastAPI server that hosts the dashboard over HTTP on the VPS.

Gives a plain http:// link reachable from a phone/laptop, and makes the
control panel truly two-way: edits POST to /api/config and are written to
the same file the paper/live engine reads. Access is gated by a secret
token carried in the URL (`?key=...`) — a capability link — so the page
is not open to the whole internet by accident.

Run:  python -m nse_algo_trader.dashboard.dashboard_server
The paper snapshot is computed once at startup (and on /refresh); config
reads/writes are live per request.
"""

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from nse_algo_trader.dashboard.config_enforced_paper_run import (
    run_config_enforced_orb_paper_lab,
)
from nse_algo_trader.dashboard.dashboard_read_model import build_dashboard_snapshot
from nse_algo_trader.dashboard.render_dashboard_html import render_dashboard_html
from nse_algo_trader.dashboard.trading_control_config import (
    TradingControlConfig,
    load_trading_control_config,
    save_trading_control_config,
)
from nse_algo_trader.market_data import BarInterval, MarketDataSqliteStore
from nse_algo_trader.paper_trading import HistoricalBarReplaySource, PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

_ACCESS_TOKEN_PATH = Path("~/.nse_algo_trader/dashboard_access_token.txt").expanduser()
_INFY = Instrument(
    408065, "INFY", ExchangeSegment.NSE_CASH, InstrumentKind.CASH_EQUITY,
    1, 0.05, None, None, None, None,
)


def get_or_create_access_token() -> str:
    if _ACCESS_TOKEN_PATH.exists():
        return _ACCESS_TOKEN_PATH.read_text().strip()
    token = secrets.token_urlsafe(16)
    _ACCESS_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ACCESS_TOKEN_PATH.write_text(token)
    return token


def _load_stored_intraday_bars() -> list:
    store = MarketDataSqliteStore()
    bars = HistoricalBarReplaySource(
        store, [408065], BarInterval.MINUTE_5
    ).load_chronological_bars()
    store.close()
    return bars


def build_dashboard_app() -> FastAPI:
    access_token = get_or_create_access_token()
    stored_bars = _load_stored_intraday_bars()  # loaded once; the lab re-runs per request
    app = FastAPI(title="NSE Algo Trader Dashboard")

    def _require_key(request: Request) -> None:
        if request.query_params.get("key") != access_token:
            raise HTTPException(status_code=403, detail="invalid or missing access key")

    def _current_snapshot():
        # Re-run the config-enforced paper lab so toggles reflect immediately:
        # disable a segment/strategy on the dashboard -> the results empty out.
        control_config = load_trading_control_config()
        ledger = PaperTradingLedger(control_config.account_virtual_capital)
        scoreboard = PredictionTableScoreboard()
        run_config_enforced_orb_paper_lab(
            control_config, stored_bars, _INFY, ledger, scoreboard
        )
        return build_dashboard_snapshot(
            control_config, ledger, scoreboard, datetime.now()
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        _require_key(request)
        return render_dashboard_html(_current_snapshot(), live_api_key=access_token)

    @app.get("/api/snapshot")
    def snapshot_json(request: Request):
        _require_key(request)
        return JSONResponse(_current_snapshot().to_json_dict())

    @app.get("/api/config")
    def get_config(request: Request):
        _require_key(request)
        return JSONResponse(load_trading_control_config().to_json_dict())

    @app.post("/api/config")
    async def update_config(request: Request):
        _require_key(request)
        try:
            config = TradingControlConfig.from_json_dict(await request.json())
        except (ValueError, KeyError) as invalid:
            raise HTTPException(status_code=400, detail=str(invalid))
        save_trading_control_config(config)
        return {"status": "saved", "config": config.to_json_dict()}

    @app.post("/refresh")
    def refresh(request: Request):
        _require_key(request)
        nonlocal stored_bars
        stored_bars = _load_stored_intraday_bars()  # pick up newly ingested bars
        return {"status": "refreshed", "bar_count": len(stored_bars)}

    return app


if __name__ == "__main__":
    import uvicorn

    token = get_or_create_access_token()
    print(f"Dashboard access token: {token}")
    print(f"Open: http://<this-server-ip>:8080/?key={token}")
    uvicorn.run(build_dashboard_app(), host="0.0.0.0", port=8080, log_level="warning")
