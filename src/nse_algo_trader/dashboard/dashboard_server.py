"""FastAPI server that hosts the dashboard over HTTP on the VPS.

Gives a plain http:// link reachable from a phone/laptop, and makes the
control panel truly two-way: edits POST to /api/config and are written to
the same file the paper/live engine reads. Access is gated by a secret
token carried in the URL (`?key=...`) — a capability link — so the page
is not open to the whole internet by accident.

Run:  python -m nse_algo_trader.dashboard.dashboard_server
A background LivePaperTradingService scans the live universe continuously;
each request reads its latest published snapshot (open positions + §9
tables). Config reads/writes are live per request.
"""

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from nse_algo_trader.dashboard.dashboard_read_model import (
    LiveUniverseStatus,
    OpenPositionSummary,
    build_dashboard_snapshot,
)
from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.dashboard.render_dashboard_html import render_dashboard_html
from nse_algo_trader.dashboard.trading_control_config import (
    TradingControlConfig,
    load_trading_control_config,
    save_trading_control_config,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard

_ACCESS_TOKEN_PATH = Path("~/.nse_algo_trader/dashboard_access_token.txt").expanduser()


def get_or_create_access_token() -> str:
    if _ACCESS_TOKEN_PATH.exists():
        return _ACCESS_TOKEN_PATH.read_text().strip()
    token = secrets.token_urlsafe(16)
    _ACCESS_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ACCESS_TOKEN_PATH.write_text(token)
    return token


def _build_authenticated_kite_client():
    """A live-authenticated KiteConnect, or None if no valid token exists
    (the dashboard still serves; it just shows no live positions)."""
    from kiteconnect import KiteConnect

    from nse_algo_trader.broker_credentials import (
        BrokerName,
        load_broker_api_credentials,
        load_env_file_into_environ,
    )
    from nse_algo_trader.broker_sessions import KiteAccessTokenFileStore

    load_env_file_into_environ()
    token_record = KiteAccessTokenFileStore().load_if_still_valid()
    if token_record is None:
        return None
    credentials = load_broker_api_credentials(BrokerName.ZERODHA_KITE)
    kite_client = KiteConnect(api_key=credentials.api_key)
    kite_client.set_access_token(token_record.access_token)
    return kite_client


def _start_live_paper_trading_service(account_virtual_capital: float):
    """Start the always-on live paper loop, or return None if unauthenticated
    or startup fails (dashboard degrades gracefully to no live positions)."""
    kite_client = _build_authenticated_kite_client()
    if kite_client is None:
        return None
    try:
        service = LivePaperTradingService(kite_client, account_virtual_capital)
        service.start()
        return service
    except Exception:
        return None


def _is_kite_token_valid() -> bool:
    from nse_algo_trader.broker_sessions import KiteAccessTokenFileStore

    return KiteAccessTokenFileStore().load_if_still_valid() is not None


def build_dashboard_app() -> FastAPI:
    access_token = get_or_create_access_token()
    control_config = load_trading_control_config()
    live_service = _start_live_paper_trading_service(
        control_config.account_virtual_capital
    )
    app = FastAPI(title="NSE Algo Trader Dashboard")

    def _require_key(request: Request) -> None:
        if request.query_params.get("key") != access_token:
            raise HTTPException(status_code=403, detail="invalid or missing access key")

    def _current_snapshot():
        control_config = load_trading_control_config()
        if live_service is None:
            # No live auth: serve the static views with an empty live section.
            return build_dashboard_snapshot(
                control_config,
                PaperTradingLedger(control_config.account_virtual_capital),
                PredictionTableScoreboard(),
                datetime.now(),
                kite_access_token_valid=_is_kite_token_valid(),
                stored_bar_count=0,
            )
        published = live_service.published_snapshot()
        open_positions = [
            OpenPositionSummary(
                trading_symbol=view.trading_symbol,
                direction=view.direction,
                quantity=view.quantity,
                entry_price=view.entry_price,
                stop_loss_price=view.stop_loss_price,
                target_price=view.target_price,
                last_price=view.last_price,
                unrealized_pnl=view.unrealized_pnl,
                assigned_table=view.assigned_table,
            )
            for view in published.open_positions
        ]
        live_status = LiveUniverseStatus(
            is_market_open=published.is_market_open,
            cash_universe_size=published.cash_universe_size,
            seeded_count=published.seeded_count,
            open_position_count=published.open_position_count,
            closed_trade_count=published.closed_trade_count,
            last_pass_at=published.last_pass_at,
        )
        return build_dashboard_snapshot(
            control_config,
            live_service.ledger,
            live_service.scoreboard,
            datetime.now(),
            kite_access_token_valid=_is_kite_token_valid(),
            stored_bar_count=1,
            open_positions=open_positions,
            live_universe_status=live_status,
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
        # The live service scans continuously in the background; a refresh
        # just re-reads its latest published snapshot.
        published = (
            live_service.published_snapshot() if live_service is not None else None
        )
        return {
            "status": "refreshed",
            "open_positions": published.open_position_count if published else 0,
            "seeded": published.seeded_count if published else 0,
        }

    return app


if __name__ == "__main__":
    import uvicorn

    token = get_or_create_access_token()
    print(f"Dashboard access token: {token}")
    print(f"Open: http://<this-server-ip>:8080/?key={token}")
    uvicorn.run(build_dashboard_app(), host="0.0.0.0", port=8080, log_level="warning")
