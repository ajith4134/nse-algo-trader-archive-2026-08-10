"""B25a — the feature/analytics plane runs independently of the trading loop.

Operator requirement: the dashboard and features must *"not stop working or depend on"* trading, and
stay *"operating and active even after market is closed"*.

Before this, all ~45 feature stages shared ONE try block with the trading pass, so a single
exception skipped every later stage AND the publish — and the first publish waited ~89s behind
FinBERT, blanking the dashboard on every restart.
"""

from datetime import datetime

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


class _Broker:
    def instruments(self, *a, **k):
        raise AssertionError("offline must not fetch the universe")

    def ltp(self, *a, **k):
        raise AssertionError("offline must not call the broker")


def _service():
    return LivePaperTradingService(_Broker(), 1_000_000.0, offline_diagnostics_mode=True)


class TestStageIsolation:
    def test_one_exploding_stage_does_not_stop_the_others(self, capsys):
        """THE regression: a single failure used to skip every later stage and the publish."""
        service = _service()
        ran = []

        def _ok_a(_now):
            ran.append("a")

        def _explodes(_now):
            raise RuntimeError("stage blew up")

        def _ok_b(_now):
            ran.append("b")

        service._feature_plane_stages = lambda: [
            ("ok_a", _ok_a, True), ("boom", _explodes, True), ("ok_b", _ok_b, True),
        ]
        failed = service.run_feature_plane_stages_once(datetime.now())

        assert ran == ["a", "b"], "stages after the failure must still run"
        assert failed == 1

    def test_a_failure_is_recorded_BY_NAME_not_silently_skipped(self, capsys):
        service = _service()

        def _explodes(_now):
            raise ValueError("bad telemetry")

        service._feature_plane_stages = lambda: [("goal_integrity", _explodes, True)]
        service.run_feature_plane_stages_once(datetime.now())

        assert "goal_integrity" in service._feature_stage_failures
        assert "ValueError" in service._feature_stage_failures["goal_integrity"]
        assert "feature-plane" in capsys.readouterr().out  # surfaced, not swallowed

    def test_all_stages_healthy_reports_zero_failures(self):
        service = _service()
        service._feature_plane_stages = lambda: [("fine", lambda _n: None, True)]
        assert service.run_feature_plane_stages_once(datetime.now()) == 0

    def test_stages_taking_no_argument_are_called_correctly(self):
        """`_drain_closed_experiments_into_memory()` takes no `now` — the registry records that."""
        service = _service()
        called = []
        service._feature_plane_stages = lambda: [("noarg", lambda: called.append(1), False)]
        assert service.run_feature_plane_stages_once(datetime.now()) == 0
        assert called == [1]


class TestTheRealStageRegistry:
    def test_every_real_stage_is_registered_with_a_name(self):
        service = _service()
        stages = service._feature_plane_stages()
        assert len(stages) > 30, f"expected the full analytics plane, got {len(stages)}"
        for name, callable_, _takes_now in stages:
            assert isinstance(name, str) and name
            assert callable(callable_)

    def test_stage_names_are_unique_so_failures_attribute_correctly(self):
        names = [name for name, _c, _t in _service()._feature_plane_stages()]
        assert len(names) == len(set(names))


class TestThreadLifecycle:
    def test_both_threads_start_and_stop_together(self):
        service = _service()
        service.start()
        try:
            assert service._writer_thread is not None and service._writer_thread.is_alive()
            assert service._feature_plane_thread is not None
            assert service._feature_plane_thread.is_alive()
            assert service._feature_plane_thread.name == "feature-plane"
        finally:
            service.stop()

    def test_the_feature_plane_never_consults_market_hours(self):
        """'Active even after market is closed' — the analytics thread must not gate on the clock."""
        import inspect

        source = inspect.getsource(LivePaperTradingService._run_feature_plane_forever)
        assert "is_market_open" not in source


class TestDeterministicShutdown:
    """B32 — an unstopped service used to ABORT the C++ runtime at interpreter teardown.

    `terminate called without an active exception`, reproducibly core-dumping. Cause: daemon threads
    killed mid-cycle while inside a native torch/transformers frame. Setting a flag was not enough —
    shutdown has to WAKE the loops and WAIT for them, and it has to cover the daemons that feature
    stages spawn themselves (news acquisition, exchange filings, the win-probability trainer), which
    were previously fire-and-forget.
    """

    def test_stop_is_bounded_and_signals_both_loops(self):
        """`stop()` wakes the loops and waits, but a thread mid-STAGE cannot be interrupted — the
        wait is bounded by the join timeout rather than guaranteed to be instant. Asserting
        'always fast' would be claiming more than the code delivers."""
        import time

        service = _service()
        service.start()
        started = time.monotonic()
        service.stop(join_timeout_seconds=3.0)
        elapsed = time.monotonic() - started

        assert not service._running
        assert service._shutdown_event.is_set()
        # Bounded: it must not hang indefinitely on a busy thread. Two joins x 3s + slack.
        assert elapsed < 20.0, f"stop() took {elapsed:.1f}s — not bounded"

    def test_spawned_background_threads_are_tracked_for_shutdown(self):
        """The fire-and-forget daemons must be joinable, or teardown kills them mid-native-call."""
        service = _service()
        assert hasattr(service, "_background_threads")
        assert isinstance(service._background_threads, list)

    def test_stop_is_idempotent(self):
        service = _service()
        service.start()
        service.stop()
        service.stop()  # must not raise
        assert not service._running
