"""Hermetic test for the dashboard offline diagnostics mode (research/122): with no live broker,
the service starts, skips the live-universe fetch (no `kite_client.instruments` call), and still
publishes the full feature-surface set from stored data — so the dashboard stays informative after
the daily Kite token expires. Uses a stub broker that raises if the live path is touched.
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


class _ExplodingBroker:
    """A stand-in that fails LOUDLY if the offline path ever calls the live broker — proving the
    universe fetch/scan is genuinely skipped."""

    def instruments(self, *_a, **_k):
        raise AssertionError("offline mode must NOT fetch the live universe")

    def ltp(self, *_a, **_k):
        raise AssertionError("offline mode must NOT call the live broker")


def test_offline_start_skips_broker_and_publishes_surfaces():
    service = LivePaperTradingService(
        _ExplodingBroker(), 1_000_000.0, offline_diagnostics_mode=True
    )
    service.start()  # must not raise, must not touch the broker
    try:
        published = None
        # The first pass genuinely takes ~90s: it loads a FinBERT model and runs ~45 feature
        # stages before the first publish (measured 89.2s on 2026-07-27). That slowness is a REAL
        # issue tracked as B25a (decouple the feature plane from the trading loop) — this budget
        # measures it honestly rather than hiding it.
        for _ in range(400):
            published = service.published_snapshot()
            # B25a: the TRADING thread now publishes almost immediately, so a non-empty surface set
            # appears long before the feature plane has finished its first cycle. Wait for the
            # analytics evidence itself (memory drained) rather than for "any publish at all",
            # otherwise this exits before the thing it is asserting has had a chance to happen.
            if published.memory_experiment_count > 0 and published.feature_surfaces:
                break
            time.sleep(0.5)
        assert published is not None
        # every manifest feature is surfaced (coverage panel is complete), not an empty degraded view
        from nse_algo_trader.dashboard.dashboard_feature_surface import MANIFEST_KEYS

        surfaced_keys = {s.key for s in published.feature_surfaces}
        assert MANIFEST_KEYS.issubset(surfaced_keys)
        # the stored-memory-backed safety organs actually ran (real experiences, not an empty view)
        assert published.memory_experiment_count > 0
    finally:
        service.stop()


def test_live_mode_still_requires_the_broker_universe():
    # regression guard: the DEFAULT (non-offline) path is unchanged and DOES call the broker.
    service = LivePaperTradingService(_ExplodingBroker(), 1_000_000.0)
    try:
        service.start()
        raise AssertionError("live start() should have hit the exploding broker")
    except AssertionError as e:
        assert "NOT fetch the live universe" in str(e)
