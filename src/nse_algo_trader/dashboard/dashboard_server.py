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

import logging
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
from nse_algo_trader.dashboard.render_feature_catalogue_html import (
    render_feature_catalogue_html,
)
from nse_algo_trader.dashboard.render_system_map_html import (
    load_system_map_markdown,
    render_system_map_html,
)
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
    """A live-authenticated KiteConnect, or None if no valid token exists (the dashboard still serves;
    it just shows no live positions). Delegates to the broker seam so the dashboard carries NO direct
    `kiteconnect` dependency — Kite lives only behind `broker_sessions` (idea #10, Kite-decoupled)."""
    from nse_algo_trader.broker_sessions import build_authenticated_kite_client_if_valid

    return build_authenticated_kite_client_if_valid()


def _start_live_paper_trading_service(account_virtual_capital: float):
    """Start the always-on live paper loop. With a valid broker token: full live+replay trading.
    WITHOUT one (the daily Kite token expired): start in OFFLINE DIAGNOSTICS mode so all stored-data
    panels — the VII safety organs, memory reflection, red-team, ethics/law, atlas — still show and
    update from SQLite (research/122); only live/replay TRADING is paused until re-login. Returns None
    only if even the offline service fails to start."""
    kite_client = _build_authenticated_kite_client()
    if kite_client is None:
        try:
            service = LivePaperTradingService(
                object(), account_virtual_capital, offline_diagnostics_mode=True
            )
            service.start()
            print("[dashboard] no valid broker token — started in OFFLINE DIAGNOSTICS mode "
                  "(stored-data panels live; live trading paused until re-login).", flush=True)
            return service
        except Exception:
            import traceback
            traceback.print_exc()
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
    # Warm up the always-on paper service in a BACKGROUND thread so uvicorn binds
    # immediately. Its start() does heavy synchronous work — notably fetching the
    # autonomous multi-broker replay feed over the network for the focus set — which
    # must NEVER block the web server from serving. Handlers read the holder and degrade
    # gracefully (static views, no live section) until warmup completes.
    import threading

    live_service_holder: dict = {"service": None}

    def _warm_up_paper_service() -> None:
        live_service_holder["service"] = _start_live_paper_trading_service(
            control_config.account_virtual_capital
        )

    threading.Thread(
        target=_warm_up_paper_service, name="paper-service-warmup", daemon=True
    ).start()

    # Segment-bot pod tick: run one pod cycle on a cadence so the /pod board reflects the live pod
    # (proposals → allocation → netting → arbitration → route). Daemon + guarded so it never blocks or
    # crashes the server; bots gate to zero size until their competency earns (Rule Q), so this is cheap
    # while gathering. The LIVE intraday feed is the open blocker — it runs on the real stored data today.
    import time as _time

    def _run_pod_tick_loop() -> None:
        from datetime import datetime

        from nse_algo_trader.portfolio_supervisor.pod_runner import PodRunner
        from nse_algo_trader.session_management.intraday_square_off_schedule import (
            IntradaySquareOffSchedule,
        )
        from nse_algo_trader.paper_trading.nse_market_clock import (
            INDIA_MARKET_TIMEZONE,
            NseMarketClock,
        )

        runner = PodRunner()
        market_clock = NseMarketClock()
        square_off_schedule = IntradaySquareOffSchedule()
        while True:
            try:
                now_ist = datetime.now(INDIA_MARKET_TIMEZONE)
                is_open = market_clock.is_market_open(now_ist)
                # FORCE the mandatory intraday square-off whenever it is at/after the 15:15 pre-close window OR
                # the market is simply CLOSED (after 15:30, weekends, holidays) — so NO paper position is ever
                # carried past the session, and a slow cycle that misses the 15:15-15:30 window still flattens
                # on the next tick. When forcing, do NOT open new positions (only close).
                force = (not is_open) or square_off_schedule.should_force_square_off_now(now_ist, market_clock)
                runner.run_cycle(now_epoch=_time.time(), force_square_off=force, allow_opens=is_open and not force)
            except Exception:  # noqa: BLE001 — a pod-tick failure must never take down the dashboard
                logging.getLogger(__name__).exception("segment-bot pod tick failed")  # surface, never crash
            _time.sleep(300)  # 5-minute cadence

    threading.Thread(target=_run_pod_tick_loop, name="segment-bot-pod-tick", daemon=True).start()
    app = FastAPI(title="NSE Algo Trader Dashboard")

    def _require_key(request: Request) -> None:
        # Constant-time compare so the capability token can't be recovered by
        # timing the 403 response.
        provided = request.query_params.get("key") or ""
        if not secrets.compare_digest(provided, access_token):
            raise HTTPException(status_code=403, detail="invalid or missing access key")

    def _current_snapshot():
        control_config = load_trading_control_config()
        live_service = live_service_holder["service"]
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
        from dataclasses import asdict

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
                segment=view.segment,
                maximum_favourable_profit=view.maximum_favourable_profit,
                maximum_adverse_profit=view.maximum_adverse_profit,
                profit_locked=view.profit_locked,
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
        from zoneinfo import ZoneInfo

        return build_dashboard_snapshot(
            control_config,
            None,  # ledger not read directly — avoids the writer-thread race
            None,  # scoreboard not read directly — same reason
            datetime.now(ZoneInfo("Asia/Kolkata")),
            kite_access_token_valid=_is_kite_token_valid(),
            stored_bar_count=1,
            open_positions=open_positions,
            live_universe_status=live_status,
            precomputed_paper_trading=published.paper_trading_summary,
            precomputed_prediction_tables=list(published.prediction_table_summaries),
            precomputed_confident_win_beats_confident_loss=(
                published.confident_win_beats_confident_loss
            ),
            exit_efficiency_rows=live_service.exit_efficiency_rows(),
            segment_boards=[asdict(b) for b in published.segment_boards],
            closed_trades=[asdict(t) for t in published.recent_closed_trades],
            combined_realized_pnl=published.combined_realized_pnl,
            real_realized_pnl=published.real_realized_pnl,
            confident_loss_probe_realized_pnl=published.confident_loss_probe_realized_pnl,
            confident_loss_prediction_accuracy=published.confident_loss_prediction_accuracy,
            strategy_readiness=list(published.strategy_readiness),
            memory_experiment_count=published.memory_experiment_count,
            reflection_board=[asdict(r) for r in published.calibration_board],
            assumption_tripwires=[asdict(v) for v in published.assumption_verdicts],
            vetoed_mechanism_count=published.vetoed_mechanism_count,
            vetoed_entry_count=published.vetoed_entry_count,
            shadow_entry_count=published.shadow_entry_count,
            opponent_ledger=published.opponent_ledger,
            positioning_deferred_count=published.positioning_deferred_count,
            information_diet=published.information_diet,
            experiment_count_by_provenance=published.experiment_count_by_provenance,
            prequential_forecast_score=published.prequential_forecast_score,
            feature_surfaces=[s.to_json_dict() for s in published.feature_surfaces],
            option_entry_reason_counts=published.option_entry_reason_counts,
            option_index_entry_outcomes=published.option_index_entry_outcomes,
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        _require_key(request)
        return render_dashboard_html(_current_snapshot(), live_api_key=access_token)

    @app.get("/map", response_class=HTMLResponse)
    def system_map_page(request: Request):
        _require_key(request)
        return render_system_map_html(
            load_system_map_markdown(), live_api_key=access_token
        )

    @app.get("/catalogue", response_class=HTMLResponse)
    def feature_catalogue_page(request: Request):
        _require_key(request)
        return render_feature_catalogue_html()

    @app.get("/pod", response_class=HTMLResponse)
    def segment_bot_pod_page(request: Request):
        _require_key(request)
        from nse_algo_trader.dashboard.pod_dashboard_service import pod_board_html

        return pod_board_html()

    @app.get("/wall", response_class=HTMLResponse)
    def operations_wall_page(request: Request):
        _require_key(request)
        from nse_algo_trader.dashboard.render_operations_wall_html import render_operations_wall_html

        return render_operations_wall_html(live_api_key=access_token)

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
            raise HTTPException(status_code=400, detail=str(invalid)) from invalid
        save_trading_control_config(config)
        return {"status": "saved", "config": config.to_json_dict()}

    @app.post("/refresh")
    def refresh(request: Request):
        _require_key(request)
        # The live service scans continuously in the background; a refresh
        # just re-reads its latest published snapshot.
        live_service = live_service_holder["service"]
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
