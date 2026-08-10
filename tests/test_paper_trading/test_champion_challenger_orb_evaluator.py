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


def test_l2_honest_trial_count_accumulates_across_batches(tmp_path: Path):
    """The core overfitting fix (research/166): the registry's trial N is CUMULATIVE across evaluations,
    not reset to this batch each time — so the DSR deflates against every config ever tried."""
    from nse_algo_trader.paper_trading.strategy_trial_registry import StrategyTrialRegistry

    registry = StrategyTrialRegistry(db_file_path=tmp_path / "trials.sqlite3")
    sessions = [_session(d, True) for d in range(1, 6)]
    champion = OpeningRangeBreakoutConfig()
    evaluate_champion_vs_challengers(
        champion, [OpeningRangeBreakoutConfig(opening_range_minutes=600)], sessions,
        trial_registry=registry,
    )
    n_after_first = registry.cumulative_trial_count("orb_cash")
    assert n_after_first >= 2  # champion + challenger registered as trials
    # A SECOND evaluation with a DIFFERENT challenger must GROW the honest N (cross-batch memory).
    evaluate_champion_vs_challengers(
        champion, [OpeningRangeBreakoutConfig(opening_range_minutes=300)], sessions,
        trial_registry=registry,
    )
    assert registry.cumulative_trial_count("orb_cash") > n_after_first
    # Re-running the SAME two configs does NOT inflate N (config-hash dedup).
    before = registry.cumulative_trial_count("orb_cash")
    evaluate_champion_vs_challengers(
        champion, [OpeningRangeBreakoutConfig(opening_range_minutes=600)], sessions,
        trial_registry=registry,
    )
    assert registry.cumulative_trial_count("orb_cash") == before


def test_l2_holdout_is_excluded_from_the_tournament_selection():
    """Leak prevention: with a custodian, the champion-challenger scoring must run ONLY on the research
    window — the sealed holdout can never influence which config is selected."""
    from datetime import datetime as _dt

    from nse_algo_trader.paper_trading.holdout_custodian import HoldoutCustodian

    research_days, holdout_days = [1, 2, 3], [9, 10]
    sessions = [_session(d, True) for d in research_days + holdout_days]
    dates = [_dt(2026, 7, d).date() for d in research_days + holdout_days]
    custodian = HoldoutCustodian(observation_dates=dates, holdout_fraction=0.4)  # newest 2/5 → holdout
    decision = evaluate_champion_vs_challengers(
        OpeningRangeBreakoutConfig(),
        [OpeningRangeBreakoutConfig(opening_range_minutes=600)], sessions,
        holdout_custodian=custodian,
    )
    # Only the 3 research sessions could have been scored (never the 2 holdout sessions).
    assert decision.champion_scorecard.sessions_traded <= len(research_days)


def test_l2_minbtl_rejects_a_short_backtest_with_many_trials():
    from nse_algo_trader.paper_trading.strategy_promotion_gate import (
        StrategyPromotionOutcome,
        evaluate_strategy_for_promotion,
    )

    returns = [0.01, -0.004] * 20  # 40 observations, > minimum_trades, real variance
    decision = evaluate_strategy_for_promotion(
        returns, number_of_strategy_trials=100_000, sharpe_std_across_trials=0.5,
        observation_count=40,
    )
    assert decision.outcome is StrategyPromotionOutcome.REJECT_BELOW_MINIMUM_BACKTEST_LENGTH
    assert decision.backtest_length_margin < 0  # short of the MinBTL requirement


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
