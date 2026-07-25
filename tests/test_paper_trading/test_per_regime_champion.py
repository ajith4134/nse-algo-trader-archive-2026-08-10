"""§53 slice 5c-iii — per-market-regime champion (hermetic). The per-regime evaluator
partitions sessions and runs the tournament per regime; the store round-trips per-regime
champions with flat-format back-compat; the service selects the live session's regime champion."""

from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)
from nse_algo_trader.paper_trading.per_regime_champion_evaluator import (
    evaluate_per_regime_champions,
    partition_sessions_by_regime,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
)

IST = ZoneInfo("Asia/Kolkata")


def _instr() -> Instrument:
    return Instrument(
        instrument_token=1, trading_symbol="B", exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY, lot_size=1, tick_size=0.05,
    )


def _session(day: int, winning: bool):
    base = datetime(2026, 7, day, 9, 15, tzinfo=IST)

    def bar(i, o, h, l, c):
        return PriceBar(
            instrument_token=1, timestamp=base + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5, open_price=o, high_price=h, low_price=l,
            close_price=c, volume=1000, open_interest=None,
        )

    bars = [bar(0, 100, 101, 99, 100), bar(1, 100, 101, 99, 100), bar(2, 100, 101, 99, 100),
            bar(3, 100, 102, 100, 102)]
    bars.append(bar(4, 102, 109, 102, 108) if winning else bar(4, 102, 102, 98, 99))
    return (bars, _instr())


def test_partition_groups_by_regime():
    labelled = [
        (_session(1, True)[0], _instr(), "trending"),
        (_session(2, True)[0], _instr(), "trending"),
        (_session(3, False)[0], _instr(), "range_bound"),
    ]
    by_regime = partition_sessions_by_regime(labelled)
    assert set(by_regime) == {"trending", "range_bound"}
    assert len(by_regime["trending"]) == 2 and len(by_regime["range_bound"]) == 1


def test_evaluate_returns_a_decision_per_regime():
    labelled = [
        (_session(1, True)[0], _instr(), "trending"),
        (_session(2, False)[0], _instr(), "range_bound"),
    ]
    decisions = evaluate_per_regime_champions(labelled, {}, [OpeningRangeBreakoutConfig(opening_range_minutes=30)])
    assert set(decisions) == {"trending", "range_bound"}
    # thin evidence -> conservative gate keeps the (default) incumbent in each regime.
    assert all(not d.champion_replaced for d in decisions.values())


def test_store_per_regime_round_trip_and_flat_backcompat(tmp_path: Path):
    path = tmp_path / "champ.json"
    store = ChampionConfigurationStore(path)
    default = OpeningRangeBreakoutConfig()
    # per-regime save/load
    store.save_champion(OpeningRangeBreakoutConfig(opening_range_minutes=30), market_regime="trending")
    store.save_champion(OpeningRangeBreakoutConfig(opening_range_minutes=45), market_regime="range_bound")
    store.save_champion(OpeningRangeBreakoutConfig(opening_range_minutes=20))  # global
    assert store.load_champion_or_default(market_regime="trending").opening_range_minutes == 30
    assert store.load_champion_or_default(market_regime="range_bound").opening_range_minutes == 45
    assert store.load_champion_or_default().opening_range_minutes == 20  # global
    # a regime with no stored champion falls back to global.
    assert store.load_champion_or_default(default, market_regime="indecisive").opening_range_minutes == 20

    # flat (legacy) format is read as the global champion.
    import json
    path.write_text(json.dumps({"opening_range_minutes": 33, "target_risk_reward_ratio": 2.0,
                                "latest_entry_time_ist": "14:30"}))
    assert ChampionConfigurationStore(path).load_champion_or_default().opening_range_minutes == 33


def test_service_selects_current_regime_champion(tmp_path: Path, monkeypatch):
    path = tmp_path / "champ.json"
    store = ChampionConfigurationStore(path)
    store.save_champion(OpeningRangeBreakoutConfig(opening_range_minutes=30, latest_entry_time_ist=time(13, 0)),
                        market_regime="trending")
    store.save_champion(OpeningRangeBreakoutConfig(opening_range_minutes=20))  # global fallback

    service = LivePaperTradingService(object(), 1_000_000.0, champion_configuration_store_path=path)

    service._current_session_market_regime = lambda: "trending"
    assert service._champion_orb_config().opening_range_minutes == 30  # regime champion
    # a regime without its own champion -> global fallback.
    service._current_session_market_regime = lambda: "range_bound"
    assert service._champion_orb_config().opening_range_minutes == 20
    # unknown -> global.
    service._current_session_market_regime = lambda: "unknown"
    assert service._champion_orb_config().opening_range_minutes == 20
