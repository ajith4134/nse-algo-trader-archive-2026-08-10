"""B32: the 0-DTE carried risk-state — fast time-stop, per-day loss cap, and daily roll."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.paper_trading.zero_dte_risk_state import (
    ZeroDteRiskConfig,
    ZeroDteRiskState,
)

IST = ZoneInfo("Asia/Kolkata")


def _at(hour: int, minute: int = 0, day: int = 28) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=IST)


def test_time_stop_fires_only_after_the_deadline():
    state = ZeroDteRiskState(ZeroDteRiskConfig(time_stop_minutes=45))
    state.register_opened("p1", _at(10, 0))
    assert state.time_stopped_position_ids(_at(10, 30)) == []          # 30 min < 45
    assert state.time_stopped_position_ids(_at(10, 45)) == ["p1"]      # exactly at deadline
    assert state.time_stopped_position_ids(_at(11, 0)) == ["p1"]       # past deadline


def test_closed_position_no_longer_time_stops():
    state = ZeroDteRiskState(ZeroDteRiskConfig(time_stop_minutes=30))
    state.register_opened("p1", _at(10, 0))
    state.record_closed("p1", realized_pnl=-100.0, now=_at(10, 20))
    assert state.time_stopped_position_ids(_at(11, 0)) == []
    assert state.open_position_count() == 0


def test_daily_loss_cap_halts_new_entries():
    state = ZeroDteRiskState(ZeroDteRiskConfig(daily_loss_cap_rupees=1000.0))
    assert state.permits_new_entry(_at(10, 0)) is True
    state.register_opened("p1", _at(10, 0))
    state.record_closed("p1", realized_pnl=-600.0, now=_at(10, 30))
    assert state.permits_new_entry(_at(10, 31)) is True               # 600 loss < 1000 cap
    state.register_opened("p2", _at(10, 40))
    state.record_closed("p2", realized_pnl=-500.0, now=_at(11, 0))
    assert state.realized_loss_today() == 1100.0
    assert state.permits_new_entry(_at(11, 1)) is False               # 1100 >= 1000 cap → halt
    assert state.remaining_loss_budget(_at(11, 1)) == 0.0


def test_wins_reduce_the_loss_tally():
    state = ZeroDteRiskState(ZeroDteRiskConfig(daily_loss_cap_rupees=1000.0))
    state.register_opened("p1", _at(10, 0))
    state.record_closed("p1", realized_pnl=-800.0, now=_at(10, 30))
    state.register_opened("p2", _at(10, 40))
    state.record_closed("p2", realized_pnl=500.0, now=_at(11, 0))      # a win offsets
    assert state.realized_loss_today() == 300.0
    assert state.permits_new_entry(_at(11, 1)) is True


def test_loss_cap_resets_on_a_new_day():
    state = ZeroDteRiskState(ZeroDteRiskConfig(daily_loss_cap_rupees=1000.0))
    state.register_opened("p1", _at(10, 0, day=28))
    state.record_closed("p1", realized_pnl=-1500.0, now=_at(10, 30, day=28))
    assert state.permits_new_entry(_at(11, 0, day=28)) is False
    # next session → tally resets, entries permitted again
    assert state.permits_new_entry(_at(9, 30, day=29)) is True
    assert state.realized_loss_today() == 0.0


def test_net_positive_day_reports_zero_loss():
    state = ZeroDteRiskState()
    state.register_opened("p1", _at(10, 0))
    state.record_closed("p1", realized_pnl=250.0, now=_at(10, 30))
    assert state.realized_loss_today() == 0.0
