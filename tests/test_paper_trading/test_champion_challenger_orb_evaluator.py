"""§53 slice 5c-i — champion-challenger evaluator + champion store (hermetic)."""

from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_algo_trader.paper_trading.champion_challenger_orb_evaluator import (
    evaluate_champion_vs_challengers,
    score_orb_configuration,
)
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
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
        instrument_token=1, trading_symbol="INFY",
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def _session(day: int, winning: bool):
    """A one-session bar list that yields a LONG winner or loser under the default config."""
    base = datetime(2026, 7, day, 9, 15, tzinfo=IST)

    def bar(i, o, h, l, c):
        return PriceBar(
            instrument_token=1, timestamp=base + timedelta(minutes=5 * i),
            interval=BarInterval.MINUTE_5, open_price=o, high_price=h, low_price=l,
            close_price=c, volume=1000, open_interest=None,
        )

    bars = [bar(0, 100, 101, 99, 100), bar(1, 100, 101, 99, 100), bar(2, 100, 101, 99, 100),
            bar(3, 100, 102, 100, 102)]  # LONG entry 102, stop 99, target 108
    bars.append(bar(4, 102, 109, 102, 108) if winning else bar(4, 102, 102, 98, 99))
    return (bars, _instr())


def test_scorecard_counts_trades_and_hit_rate():
    sessions = [_session(1, True), _session(2, True), _session(3, False)]
    card = score_orb_configuration(OpeningRangeBreakoutConfig(), sessions)
    assert card.sessions_traded == 3
    assert card.hit_rate == 2 / 3
    assert card.total_return > 0


def test_champion_kept_when_it_is_top_scorer():
    sessions = [_session(1, True), _session(2, True)]
    champion = OpeningRangeBreakoutConfig()
    # a challenger with a huge opening range never triggers -> no trades -> lower sharpe.
    challenger = OpeningRangeBreakoutConfig(opening_range_minutes=600)
    decision = evaluate_champion_vs_challengers(champion, [challenger], sessions)
    assert decision.champion_replaced is False
    assert decision.winning_config == champion


def test_challenger_not_promoted_on_thin_evidence():
    # even if a challenger edges ahead, too few trades -> Deflated-Sharpe gate keeps champion.
    sessions = [_session(1, True), _session(2, False)]
    champion = OpeningRangeBreakoutConfig(target_risk_reward_ratio=2.0)
    challenger = OpeningRangeBreakoutConfig(target_risk_reward_ratio=1.5)
    decision = evaluate_champion_vs_challengers(champion, [challenger], sessions)
    # with only ~2 sessions, the gate must not promote (min_trades not met).
    assert decision.champion_replaced is False


def test_champion_store_round_trip(tmp_path: Path):
    store = ChampionConfigurationStore(tmp_path / "champion.json")
    assert store.load_champion_or_default() == OpeningRangeBreakoutConfig()  # default when absent
    promoted = OpeningRangeBreakoutConfig(
        opening_range_minutes=30, target_risk_reward_ratio=1.5,
        latest_entry_time_ist=time(13, 45),
    )
    store.save_champion(promoted)
    loaded = store.load_champion_or_default()
    assert loaded.opening_range_minutes == 30
    assert loaded.target_risk_reward_ratio == 1.5
    assert loaded.latest_entry_time_ist == time(13, 45)


def test_champion_store_bad_file_falls_back_to_default(tmp_path: Path):
    path = tmp_path / "champion.json"
    path.write_text("{ not valid json")
    assert ChampionConfigurationStore(path).load_champion_or_default() == OpeningRangeBreakoutConfig()
