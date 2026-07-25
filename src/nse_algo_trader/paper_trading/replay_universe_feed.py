"""Replay feed that serves stored bars as if live — the market-CLOSED half of
the 24/7 router (PLAN §1.4, research/26). Paper trading never idles: when the
real market is shut, the loop runs against this feed over stored session
history instead of Kite.

It presents the SAME interface the live universe loop already consumes
(`latest_price_by_token`, `recent_intraday_bars`), so the loop is byte-for-
byte identical in replay and live — the only difference is which feed the
service hands it and that "now" is a replay timestamp, not wall-clock. The
real `NseMarketClock` still evaluates that replay timestamp, so a replayed
day opens positions in the morning and squares off at its own 15:15 exactly
as a live day would.

Bars are pre-loaded into memory (in the main thread) so the writer thread
only ever reads memory — no cross-thread SQLite access.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.causal_leakage_firewall import (
    assert_no_future_leak,
)
from nse_algo_trader.paper_trading.corporate_action_adjustment import (
    CorporateActionAdjustmentEngine,
)
from nse_algo_trader.paper_trading.replay_experience_provenance import (
    DataProvenance,
    ProvenanceStamp,
    ReplayFidelityTier,
)


class ReplayUniverseFeed:
    def __init__(
        self,
        chronological_bars_by_token: dict[int, list[PriceBar]],
        bar_interval: BarInterval = BarInterval.MINUTE_5,
        provenance_stamp: ProvenanceStamp | None = None,
        corporate_action_adjustment_engine: (
            CorporateActionAdjustmentEngine | None
        ) = None,
    ) -> None:
        self._bars_by_token = {
            token: sorted(bars, key=lambda bar: bar.timestamp)
            for token, bars in chronological_bars_by_token.items()
        }
        self._bar_interval = bar_interval
        # Everything this feed serves is real history replayed as-live; the BASE
        # tier is bar-only (research/62 P6). The memory-drain reads this stamp
        # when writing replayed experiences so the brain never mistakes replay
        # for live (research/53 §8.2). Slice-3 consumer (BACKLOG).
        self._provenance_stamp = provenance_stamp or ProvenanceStamp(
            provenance=DataProvenance.REPLAY_FAITHFUL,
            fidelity_tier=ReplayFidelityTier.BAR_ONLY,
        )
        # Optional: keep the lookback series continuous across split/bonus
        # ex-dates (research/62 P3, §11.2). None → identity (raw bars).
        self._corporate_action_adjustment_engine = corporate_action_adjustment_engine
        self._replay_as_of: datetime | None = None

    # --- replay clock (advanced by the service) ---
    def stored_session_timestamps(self) -> list[datetime]:
        """Every distinct bar timestamp in the store, ascending — the ticks the
        service steps the replay clock through."""
        stamps = {
            bar.timestamp for bars in self._bars_by_token.values() for bar in bars
        }
        return sorted(stamps)

    def set_replay_as_of(self, replay_as_of: datetime) -> None:
        self._replay_as_of = replay_as_of

    def has_data(self) -> bool:
        return any(self._bars_by_token.values())

    def provenance_stamp(self) -> ProvenanceStamp:
        """The provenance + fidelity label for everything this feed serves, so
        the learning substrate can weight replayed experience below live."""
        return self._provenance_stamp

    # --- the live-feed interface (identical shape to KiteLiveUniverseFeed) ---
    def latest_price_by_token(self, instruments: list) -> dict[int, float]:
        """Close of each instrument's latest stored bar at/<= the replay clock."""
        if self._replay_as_of is None:
            return {}
        prices: dict[int, float] = {}
        for instrument in instruments:
            bar = self._latest_bar_at_or_before(
                instrument.instrument_token, self._replay_as_of
            )
            if bar is not None:
                # Firewall: nothing served may be dated after the replay clock
                # (research/53 §8.3). The selection already guarantees this;
                # the assert makes the guarantee structural, not incidental.
                assert_no_future_leak(bar.timestamp, self._replay_as_of)
                prices[instrument.instrument_token] = bar.close_price
        return prices

    def recent_intraday_bars(
        self,
        instrument,
        as_of_moment: datetime,
        lookback_calendar_days: int = 7,
        bar_interval: BarInterval = BarInterval.MINUTE_5,
    ) -> list[PriceBar]:
        """Stored bars for one instrument over the lookback window ending at the
        replay timestamp (`as_of_moment` IS the replay clock in replay mode)."""
        # Firewall: a caller must never request bars as-of a moment later than
        # the replay clock — that would hand the loop the future (research/53
        # §8.3). Refuse it structurally rather than trusting the caller.
        if self._replay_as_of is not None:
            assert_no_future_leak(as_of_moment, self._replay_as_of)
        window_start = as_of_moment - timedelta(days=lookback_calendar_days)
        window_bars = [
            bar
            for bar in self._bars_by_token.get(instrument.instrument_token, [])
            if window_start <= bar.timestamp <= as_of_moment
        ]
        # Make the series continuous across any split/bonus ex-date inside the
        # window, as of the replay clock (research/62 P3, §11.2). The current
        # price served by `latest_price_by_token` stays RAW — only this lookback
        # series is scaled, so indicators don't see a structural gap as a crash.
        if self._corporate_action_adjustment_engine is not None:
            return self._corporate_action_adjustment_engine.adjust_bars_for_continuity(
                instrument.trading_symbol, window_bars, as_of_moment.date()
            )
        return window_bars

    def _latest_bar_at_or_before(
        self, instrument_token: int, moment: datetime
    ) -> PriceBar | None:
        latest: PriceBar | None = None
        for bar in self._bars_by_token.get(instrument_token, []):
            if bar.timestamp <= moment:
                latest = bar
            else:
                break
        return latest
