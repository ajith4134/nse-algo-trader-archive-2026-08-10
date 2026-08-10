"""Tests for the STOCK-OPTION bot — option-flow, event gate, single-name selector, assembled bot."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nse_algo_trader.segment_bots.index_option_bot.implied_vol_surface_engine import (
    ImpliedVolSurfaceState,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import MarketSegment, SegmentBot, TradeSide
from nse_algo_trader.segment_bots.stock_option_bot.event_calendar_gate import (
    EventPhase,
    EventProximityGate,
)
from nse_algo_trader.segment_bots.stock_option_bot.option_flow_signals import (
    OptionFlowEngine,
    PcrHistoryStore,
)
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_bot import StockOptionBot
from nse_algo_trader.segment_bots.stock_option_bot.stock_option_structure_selector import (
    StockOptionStructureSelector,
)


def _chain(put_oi=1000, call_oi=1000, put_vol=500, call_vol=500) -> pd.DataFrame:
    rows = []
    for strike in (900, 950, 1000, 1050, 1100):
        rows.append({"option_right_code": "CE", "strike_price": strike, "open_interest": call_oi,
                     "total_traded_volume": call_vol})
        rows.append({"option_right_code": "PE", "strike_price": strike, "open_interest": put_oi,
                     "total_traded_volume": put_vol})
    return pd.DataFrame(rows)


def _surface(iv_rank):
    return ImpliedVolSurfaceState("INFY", "2026-08-03", 1000.0, "2026-08-28", 0.30,
                                  {"2026-08-28": 0.30}, 0.0, 0.0, iv_rank, iv_rank, (), 50, "earned")


# ---- option flow ----
def test_pcr_and_unusual_activity_from_chain(tmp_path):
    eng = OptionFlowEngine("INFY", PcrHistoryStore(tmp_path))
    # heavy put OI + a put volume spike (fresh positioning)
    state = eng.compute(_chain(put_oi=2000, call_oi=1000, put_vol=5000, call_vol=200), "2026-08-03")
    assert state.pcr_open_interest == pytest.approx(2.0)  # 2000/1000
    assert state.unusual_put_strikes  # put volume 5000 >> 2× OI 2000
    assert state.net_flow_bias < 0.0  # put-side fresh flow dominates → bearish tilt


def test_pcr_shift_gates_to_gathering_then_earns(tmp_path):
    eng = OptionFlowEngine("INFY", PcrHistoryStore(tmp_path))
    first = eng.compute(_chain(), "2026-01-01")
    assert first.maturity == "gathering" and first.pcr_shift_z is None
    from datetime import timedelta

    start = date(2026, 1, 2)
    for off in range(35):
        eng.compute(_chain(put_oi=1000 + off * 5), (start + timedelta(days=off)).isoformat())
    earned = eng.compute(_chain(put_oi=4000), (start + timedelta(days=60)).isoformat())
    assert earned.maturity == "earned" and earned.pcr_shift_z is not None


# ---- event gate ----
class _FakeCalendar:
    def __init__(self, days):
        self._days = days

    def signed_days_to_nearest_event(self, underlying, as_of):
        return self._days


def test_event_gate_phases_and_caps():
    gate = EventProximityGate()
    pre = gate.assess("INFY", date(2026, 8, 3), _FakeCalendar(1))
    assert pre.phase == EventPhase.PRE_EVENT and pre.blocks_naked_premium and pre.size_cap_fraction < 1.0
    post = gate.assess("INFY", date(2026, 8, 3), _FakeCalendar(-1))
    assert post.phase == EventPhase.POST_EVENT
    clear = gate.assess("INFY", date(2026, 8, 3), _FakeCalendar(20))
    assert clear.phase == EventPhase.CLEAR and clear.size_cap_fraction == 1.0
    unknown = gate.assess("INFY", date(2026, 8, 3), None)
    assert unknown.phase == EventPhase.UNKNOWN


# ---- selector ----
def test_pre_event_forces_defined_risk():
    sel = StockOptionStructureSelector()
    pre = EventProximityGate().assess("INFY", date(2026, 8, 3), _FakeCalendar(1))
    flow = OptionFlowEngine("INFY").compute(_chain(), "2026-08-03")
    d = sel.select("INFY", "2026-08-28", _surface(0.85), flow, pre)
    assert not d.stand_aside and d.plan.is_defined_risk  # never a naked strangle into an event


def test_post_event_cheap_iv_buys_vol():
    sel = StockOptionStructureSelector()
    post = EventProximityGate().assess("INFY", date(2026, 8, 3), _FakeCalendar(-1))
    flow = OptionFlowEngine("INFY").compute(_chain(), "2026-08-03")
    d = sel.select("INFY", "2026-08-28", _surface(0.15), flow, post)
    assert not d.stand_aside and d.plan.net_vega > 0  # long vol


# ---- assembled bot ----
class _FakeAdapter:
    def __init__(self):
        rng = np.random.default_rng(1)
        self._prices = pd.Series(1000.0 * np.exp(np.cumsum(rng.normal(0, 0.004, 500))))
        self._chain = _chain(put_oi=1200, call_oi=1200, put_vol=600, call_vol=600)

    def stock_underlyings(self):
        return ["INFY"]

    def price_series(self, u):
        return self._prices

    def option_chain(self, u):
        # add pricing columns the IV-surface needs
        c = self._chain.copy()
        c["close_price"] = 30.0
        c["underlying_price"] = 1000.0
        c["expiry_date"] = "2026-09-25"
        return c, "2026-08-26"

    def implied_atm_vol(self, u):
        return 0.35

    def nearest_expiry(self, u):
        return "2026-09-25"

    def trend_side(self, u):
        return TradeSide.NEUTRAL

    def event_calendar(self):
        return None


def test_bot_satisfies_protocol_and_cold_starts(tmp_path):
    bot = StockOptionBot(_FakeAdapter(), tmp_path)
    assert isinstance(bot, SegmentBot) and bot.segment == MarketSegment.STOCK_OPTION
    # Rule-Q cold-start: the unearned bot runs the pipeline (not silenced); [] here reflects no edge in the
    # fake chain, not a competency gate.
    assert isinstance(bot.propose(now_epoch=1000.0), list)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
