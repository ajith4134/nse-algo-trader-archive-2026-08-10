"""B32 (hermetic, Rule J): the 0-DTE planner routes a synthetic trending expiry-day to a directional
plan, a pinned low-vol chain to short premium, and abstains on insufficient data. Real-data pass is an
open blocker until a live expiry session runs (BACKLOG B32)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.strategy_engine.zero_dte_entry_planner import (
    expiry_day_time_window,
    plan_zero_dte_entry,
)
from nse_algo_trader.strategy_engine.zero_dte_regime_router import (
    ExpiryDayTimeWindow,
    ZeroDteStructure,
)
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

IST = ZoneInfo("Asia/Kolkata")
LOT = 50
EXPIRY = date(2026, 7, 28)


def _spot_instrument() -> Instrument:
    return Instrument(
        instrument_token=999, trading_symbol="NIFTY", exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY, lot_size=1, tick_size=0.05,
    )


def _opt(token: int, strike: float, right: OptionRight) -> Instrument:
    return Instrument(
        instrument_token=token, trading_symbol=f"NIFTY{int(strike)}{right.value}",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.INDEX_OPTION,
        lot_size=LOT, tick_size=0.05, underlying_symbol="NIFTY",
        strike_price=strike, option_right=right, expiry_date=EXPIRY,
    )


def _ladder(center: int) -> list[Instrument]:
    ladder, t = [], 1
    for k in range(center - 200, center + 201, 100):
        ladder.append(_opt(t, k, OptionRight.CALL)); t += 1
        ladder.append(_opt(t, k, OptionRight.PUT)); t += 1
    return ladder


def _premia(ladder, center):
    return {o.instrument_token: max(120 - abs(o.strike_price - center) / 100 * 30, 5.0)
            for o in ladder}


def _iv(ladder, value=0.18):
    return {o.instrument_token: value for o in ladder}


def _bars(closes: list[float]) -> list[PriceBar]:
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        hi = max(prev, c) + abs(c - prev) * 0.5 + 0.5
        lo = min(prev, c) - abs(c - prev) * 0.5 - 0.5
        out.append(PriceBar(
            instrument_token=999, timestamp=base + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5, open_price=prev, high_price=hi, low_price=lo,
            close_price=c, volume=1000, open_interest=None))
        prev = c
    return out


def test_time_window_classification():
    d = date(2026, 7, 28)
    assert expiry_day_time_window(datetime.combine(d, datetime.min.time(), IST).replace(hour=9, minute=30)) is ExpiryDayTimeWindow.OPEN_BURST
    assert expiry_day_time_window(datetime.combine(d, datetime.min.time(), IST).replace(hour=12)) is ExpiryDayTimeWindow.MIDDAY_LULL
    assert expiry_day_time_window(datetime.combine(d, datetime.min.time(), IST).replace(hour=14, minute=30)) is ExpiryDayTimeWindow.PRE_CLOSE_GAMMA_RAMP


def test_trending_vol_expanding_underlying_routes_directional_long():
    # 24 calm bars then a strong, widening uptrend → ADX trending + vol-expansion + momentum LONG.
    closes = [20000.0]
    for i in range(24):
        closes.append(closes[-1] + (0.5 if i % 2 else -0.5))
    for _ in range(16):
        closes.append(closes[-1] + 22.0)
    center = 20000
    ladder = _ladder(center)
    now = datetime(2026, 7, 28, 11, 45, tzinfo=IST)
    plan = plan_zero_dte_entry(
        "NIFTY", _spot_instrument(), closes[-1], _bars(closes), ladder,
        _premia(ladder, center), {o.instrument_token: 1000 for o in ladder},
        _iv(ladder), {}, now,
    )
    assert plan.structure is ZeroDteStructure.DIRECTIONAL_LONG_OPTION
    assert plan.is_actionable
    assert plan.defined_risk_per_lot > 0.0


def test_long_gamma_pin_near_max_pain_routes_short_premium():
    # flat, no net move (momentum None, no vol-expansion); CALL open interest dominates → positive
    # GEX → LONG_GAMMA_PIN (dealers dampen); highest total OI on the ATM strike spot sits on →
    # near max-pain. Pin + confirm ⇒ short-premium, independent of ADX.
    closes = [20000.0 + (5 if i % 2 else -5) for i in range(40)]
    center = 20000
    ladder = _ladder(center)
    def _oi(o):
        base = 9000 if o.strike_price == center else 3000
        return base if o.option_right is OptionRight.CALL else 400  # calls dominate → +GEX
    oi = {o.instrument_token: _oi(o) for o in ladder}
    now = datetime(2026, 7, 28, 12, 0, tzinfo=IST)
    plan = plan_zero_dte_entry(
        "NIFTY", _spot_instrument(), 20000.0, _bars(closes), ladder,
        _premia(ladder, center), oi, _iv(ladder), {}, now,
    )
    assert plan.structure is ZeroDteStructure.SHORT_PREMIUM_SPREAD
    assert plan.is_actionable


def test_insufficient_bars_abstains():
    center = 20000
    ladder = _ladder(center)
    now = datetime(2026, 7, 28, 9, 30, tzinfo=IST)
    plan = plan_zero_dte_entry(
        "NIFTY", _spot_instrument(), 20000.0, _bars([20000.0, 20001.0, 20002.0]), ladder,
        _premia(ladder, center), {o.instrument_token: 100 for o in ladder}, _iv(ladder), {}, now,
    )
    assert plan.structure is ZeroDteStructure.ABSTAIN
    assert not plan.is_actionable
    assert plan.reason
