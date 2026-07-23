"""The MarketClock-gated router — one bar/tick interface, replay when the
market is closed, live when it is open, with a seamless handoff (PLAN §1.4).

Every downstream consumer (paper engine, learning loop, strategies) asks
this router for data and never learns whether a bar came from Kite's live
feed or from historical replay. The `NseMarketClock` is the only thing
that decides the mode. Paper trading consumes this router continuously and
never stops; live trading additionally gates on mode == LIVE before
submitting real orders (that gate lives in the live path, not here).

Live wiring (a real KiteTicker feed) attaches when an open session exists
and Layer 6's authenticated ticker is available — until then the live
source is None and the router serves replay, which is the correct
behaviour whenever the market is closed (Rule F blocker: the live-mode
handoff is verified only during a real open session).
"""

from enum import Enum

from nse_algo_trader.market_data import PriceBar
from nse_algo_trader.paper_trading.historical_bar_replay_source import (
    HistoricalBarReplaySource,
)
from nse_algo_trader.paper_trading.nse_market_clock import NseMarketClock
from datetime import datetime


class DataSourceMode(str, Enum):
    REPLAY = "replay"  # market closed — stream stored history
    LIVE = "live"  # market open — stream the live feed


class MarketClockGatedDataSourceRouter:
    def __init__(
        self,
        nse_market_clock: NseMarketClock,
        historical_replay_source: HistoricalBarReplaySource,
        live_bar_source=None,
    ) -> None:
        self._nse_market_clock = nse_market_clock
        self._historical_replay_source = historical_replay_source
        self._live_bar_source = live_bar_source

    def current_data_mode(self, at_moment: datetime) -> DataSourceMode:
        if self._nse_market_clock.is_market_open(at_moment) and (
            self._live_bar_source is not None
        ):
            return DataSourceMode.LIVE
        return DataSourceMode.REPLAY

    def next_bars(self, at_moment: datetime, loop_replay_forever: bool = True):
        """The single data interface. When closed (or no live source yet),
        yields the replay stream; when open with a live source, yields the
        live feed. Consumers cannot tell which."""
        if self.current_data_mode(at_moment) is DataSourceMode.LIVE:
            yield from self._live_bar_source.stream_bars()
        else:
            yield from self._historical_replay_source.stream_bars(
                loop_forever=loop_replay_forever
            )
