"""B10 — the analytics stages must keep working between sessions, not run once and freeze.

Operator's requirement: *"all the features like news, research, memory, self-learning... always
active doing research, learning... PREPARING FOR THE NEXT OPEN MARKET TRADING until the market
opens."*

Before this, 22 stages were guarded by `if last_run_date == today: return` — they ran once at
process start and did nothing for the rest of the day. B25a made the feature THREAD run
market-independently; this makes the stages actually re-run.
"""

from datetime import datetime, timedelta

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


class _Broker:
    def instruments(self, *a, **k):
        raise AssertionError("offline must not fetch")

    def ltp(self, *a, **k):
        raise AssertionError("offline must not call broker")


def _service():
    return LivePaperTradingService(_Broker(), 1_000_000.0, offline_diagnostics_mode=True)


NOW = datetime(2026, 7, 27, 18, 0)


class TestStagesReRunWithinTheSameDay:
    def test_the_b10_regression_a_stage_runs_again_after_its_interval(self):
        """THE fix: previously the second call on the same day was refused forever."""
        service = _service()
        assert service._feature_stage_is_due("memory_consolidation", NOW)
        later = NOW + timedelta(minutes=16)   # interval is 15
        assert service._feature_stage_is_due("memory_consolidation", later), (
            "a stage must re-run within the same day"
        )

    def test_a_stage_is_not_due_before_its_interval_elapses(self):
        service = _service()
        assert service._feature_stage_is_due("memory_consolidation", NOW)
        assert not service._feature_stage_is_due(
            "memory_consolidation", NOW + timedelta(minutes=5)
        )

    def test_llm_backed_stages_are_spaced_further_apart_than_local_compute(self):
        """B33: LLM stages cost real tokens, so they must not run as often as cheap local ones."""
        intervals = LivePaperTradingService.FEATURE_STAGE_INTERVAL_MINUTES
        for llm_stage in ("strategic_reflection", "thesis_debate", "prediction_council"):
            for cheap_stage in ("memory_consolidation", "goal_integrity", "market_breadth"):
                assert intervals[llm_stage] > intervals[cheap_stage], (
                    f"{llm_stage} must be rarer than {cheap_stage}"
                )

    def test_every_named_stage_runs_at_least_hourly_and_a_half(self):
        """No stage may be so rare that it is effectively frozen again."""
        for name, minutes in LivePaperTradingService.FEATURE_STAGE_INTERVAL_MINUTES.items():
            assert 0 < minutes <= 90, f"{name} cadence {minutes}min is effectively frozen"

    def test_an_unnamed_stage_gets_a_frequent_default_not_a_daily_one(self):
        """The failure mode being fixed is a stage that never runs again — default must be short."""
        assert LivePaperTradingService.DEFAULT_FEATURE_STAGE_INTERVAL_MINUTES <= 60
        service = _service()
        assert service._feature_stage_is_due("some_future_stage", NOW)

    def test_stages_are_tracked_independently(self):
        service = _service()
        service._feature_stage_is_due("goal_integrity", NOW)
        assert service._feature_stage_is_due("society", NOW), "one stage must not gate another"

    def test_no_daily_date_guard_survives_in_the_service(self):
        """Regression guard: a reintroduced `last_run_date == today` would re-freeze the plane."""
        import inspect

        source = inspect.getsource(LivePaperTradingService)
        assert "_last_run_date == today" not in source
