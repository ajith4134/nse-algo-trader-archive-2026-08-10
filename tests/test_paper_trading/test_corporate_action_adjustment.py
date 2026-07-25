"""CorporateActionAdjustmentEngine — keeps a replayed series continuous across
split/bonus ex-dates (research/62 P3, §11.2).

Hermetic tests use real ratios (a 1:5 split). A guarded real-data test fetches
LIVE NSE actions via nselib and proves a real split is made continuous (Rule F);
it skips if the network / nselib is unavailable.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.market_data.nse_corporate_action_source import (
    CorporateAction,
    CorporateActionType,
)
from nse_algo_trader.paper_trading.corporate_action_adjustment import (
    CorporateActionAdjustmentEngine,
)

IST = ZoneInfo("Asia/Kolkata")


def _bar(day: date, close: float) -> PriceBar:
    ts = datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST)
    return PriceBar(1, ts, BarInterval.MINUTE_5, close, close, close, close, 1000)


def _split_1_for_5(symbol: str, ex: date) -> CorporateAction:
    return CorporateAction(symbol, ex, CorporateActionType.SPLIT, 0.2)


def test_pre_ex_bars_are_scaled_to_the_post_ex_scale_series_is_continuous():
    ex = date(2026, 7, 3)
    engine = CorporateActionAdjustmentEngine({"ACME": [_split_1_for_5("ACME", ex)]})
    # Pre-split price 500 really printed; post-split 100 really printed.
    series = [_bar(ex - timedelta(days=1), 500.0), _bar(ex, 100.0)]
    adjusted = engine.adjust_bars_for_continuity("ACME", series, as_of_date=ex)
    assert adjusted[0].close_price == pytest.approx(100.0)  # 500 * 0.2
    assert adjusted[1].close_price == pytest.approx(100.0)  # on/after ex → raw
    assert adjusted[0].close_price == pytest.approx(adjusted[1].close_price)


def test_volume_is_scaled_up_so_turnover_stays_continuous():
    ex = date(2026, 7, 3)
    engine = CorporateActionAdjustmentEngine({"ACME": [_split_1_for_5("ACME", ex)]})
    pre = engine.adjust_bars_for_continuity(
        "ACME", [_bar(ex - timedelta(days=1), 500.0)], as_of_date=ex
    )[0]
    assert pre.volume == 5000  # 1000 / 0.2 — quantity scales inversely to price


def test_no_action_symbol_returns_bars_untouched():
    engine = CorporateActionAdjustmentEngine({})
    series = [_bar(date(2026, 7, 1), 123.0)]
    assert engine.adjust_bars_for_continuity("NONE", series, date(2026, 7, 2)) is series


def test_action_after_as_of_is_not_applied_yet():
    ex = date(2026, 7, 10)
    engine = CorporateActionAdjustmentEngine({"ACME": [_split_1_for_5("ACME", ex)]})
    # Replay clock is BEFORE the ex-date → the split hasn't happened yet, no scaling.
    bar = engine.adjust_bars_for_continuity(
        "ACME", [_bar(date(2026, 7, 5), 500.0)], as_of_date=date(2026, 7, 8)
    )[0]
    assert bar.close_price == pytest.approx(500.0)


def test_real_nse_split_is_made_continuous_live():
    """Rule-F real-data pass: fetch LIVE NSE corporate actions and prove a real
    split's fake gap is removed. Skips on any network/nselib failure."""
    try:
        from nse_algo_trader.market_data.nse_corporate_action_source import (
            NseLibCorporateActionSource,
        )

        actions = NseLibCorporateActionSource().corporate_actions_by_symbol(
            date(2026, 6, 20), date(2026, 7, 24)
        )
    except Exception:  # noqa: BLE001 — offline / bot-gated → skip, not fail
        pytest.skip("nselib corporate-action fetch unavailable (offline / gated)")
    real_splits = {
        s: a
        for s, a in actions.items()
        if any(x.action_type is CorporateActionType.SPLIT for x in a)
    }
    if not real_splits:
        pytest.skip("no real split in the fetched window")
    symbol, symbol_actions = next(iter(real_splits.items()))
    split = next(a for a in symbol_actions if a.action_type is CorporateActionType.SPLIT)
    engine = CorporateActionAdjustmentEngine(actions)
    raw_post = 500.0 * split.price_adjustment_factor
    series = [_bar(split.ex_date - timedelta(days=1), 500.0), _bar(split.ex_date, raw_post)]
    adjusted = engine.adjust_bars_for_continuity(symbol, series, as_of_date=split.ex_date)
    assert adjusted[0].close_price == pytest.approx(adjusted[1].close_price)
