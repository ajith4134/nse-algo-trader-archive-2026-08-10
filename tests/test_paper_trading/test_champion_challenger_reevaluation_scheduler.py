"""§53 slice 5c-i.b — champion-challenger re-eval scheduler + service auto-promotion
(hermetic). Scheduler due-logic + an end-to-end re-eval that promotes a clearly-better
challenger over injected sessions and persists it to the champion store."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nse_algo_trader.dashboard.live_paper_trading_service import (
    LivePaperTradingService,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.champion_challenger_reevaluation_scheduler import (
    DEFAULT_ORB_CHALLENGER_GRID,
    is_reevaluation_due,
)
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
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


def test_reevaluation_due_only_once_per_day():
    today = date(2026, 7, 24)
    assert is_reevaluation_due(None, today) is True           # never run
    assert is_reevaluation_due(date(2026, 7, 23), today) is True   # rolled over
    assert is_reevaluation_due(today, today) is False         # already ran today


def test_default_grid_is_nonempty_and_distinct_from_default():
    assert len(DEFAULT_ORB_CHALLENGER_GRID) >= 2
    assert OpeningRangeBreakoutConfig() not in DEFAULT_ORB_CHALLENGER_GRID


def _forced_decision(winning_config):
    """A ChampionChallengerDecision that promotes `winning_config` — the gate itself is
    covered by the 5c-i evaluator tests; here we test the service's HANDLING of a promotion."""
    from nse_algo_trader.paper_trading.champion_challenger_orb_evaluator import (
        ChampionChallengerDecision,
        ConfigurationScorecard,
    )

    card = ConfigurationScorecard(
        config=winning_config, sessions_traded=40, per_session_returns=[0.01] * 40,
        hit_rate=1.0, total_return=0.4, sharpe_ratio=2.0,
    )
    return ChampionChallengerDecision(
        champion_scorecard=card, challenger_scorecards=[card],
        winning_config=winning_config, champion_replaced=True,
        promotion_deflated_sharpe=0.99, promotion_reason="forced promote (test)",
    )


def test_service_reeval_promotes_persists_and_gates_once_per_day(tmp_path: Path, monkeypatch):
    champ_path = tmp_path / "champ.json"  # injected store path -> the real store is untouched
    winning_config = OpeningRangeBreakoutConfig(opening_range_minutes=42, target_risk_reward_ratio=1.5)
    # Force BOTH the global and the per-regime evaluators to promote (each looks the name up
    # in its own module), so the test never touches the real backtester with dummy bars.
    import nse_algo_trader.paper_trading.champion_challenger_orb_evaluator as ev_mod
    import nse_algo_trader.paper_trading.per_regime_champion_evaluator as pr_mod
    forced = lambda *a, **k: _forced_decision(winning_config)
    monkeypatch.setattr(ev_mod, "evaluate_champion_vs_challengers", forced)
    monkeypatch.setattr(pr_mod, "evaluate_champion_vs_challengers", forced)

    service = LivePaperTradingService(
        object(), 1_000_000.0, champion_challenger_min_sessions=1,
        champion_configuration_store_path=champ_path,
    )
    call_count = []
    service._load_stored_benchmark_sessions_labelled = lambda: (
        call_count.append(1), [("bars", "instr", "trending")]
    )[1]

    now = datetime(2026, 7, 24, 18, 0, tzinfo=IST)
    service._maybe_reevaluate_champion_challenger(now)

    store = ChampionConfigurationStore(champ_path)
    assert store.load_champion_or_default().opening_range_minutes == 42  # GLOBAL persisted
    assert store.load_champion_or_default(market_regime="trending").opening_range_minutes == 42
    assert service._champion_orb_config_by_regime["global"].opening_range_minutes == 42
    assert service._champion_challenger_last_run_date == now.date()
    assert len(call_count) == 1

    # same-day second call: scheduler gate -> no re-run (session loader not touched again).
    service._maybe_reevaluate_champion_challenger(now)
    assert len(call_count) == 1


def test_service_reeval_below_min_sessions_marks_day_without_promoting(tmp_path: Path):
    champ_path = tmp_path / "champ.json"
    service = LivePaperTradingService(
        object(), 1_000_000.0, champion_challenger_min_sessions=10,
        champion_configuration_store_path=champ_path,
    )
    service._load_stored_benchmark_sessions_labelled = lambda: [("bars", "instr", "trending")]  # 1 < 10
    now = datetime(2026, 7, 24, 18, 0, tzinfo=IST)
    service._maybe_reevaluate_champion_challenger(now)
    assert service._champion_challenger_last_run_date == now.date()  # day marked, no crash
    assert not champ_path.exists()  # nothing promoted
