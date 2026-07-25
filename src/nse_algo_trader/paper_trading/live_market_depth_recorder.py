"""Records live order-book depth forward during market hours (§53 slice 4 P4b).

Historical depth cannot be bought — recording our own forward is the only way to
ever have it. Each call snapshots a bounded focus set's book from the injected
`MarketDepthSource` and persists it to the `MarketDepthSnapshotStore`, so depth
history accumulates for future microstructure / depth-replay features.
"""

from nse_algo_trader.market_data.broker_data_source_protocols import (
    MarketDepthSource,
)
from nse_algo_trader.market_data.market_depth_snapshot_store import (
    MarketDepthSnapshotStore,
)


class LiveMarketDepthRecorder:
    def __init__(
        self,
        market_depth_source: MarketDepthSource,
        market_depth_snapshot_store: MarketDepthSnapshotStore,
    ) -> None:
        self._market_depth_source = market_depth_source
        self._market_depth_snapshot_store = market_depth_snapshot_store

    def record_once(self, instrument_tokens: list[int]) -> int:
        """Snapshot the focus set's order book once and persist it. Returns the
        number of snapshots stored (0 if none had depth)."""
        if not instrument_tokens:
            return 0
        snapshots = self._market_depth_source.fetch_market_depth(instrument_tokens)
        if not snapshots:
            return 0
        return self._market_depth_snapshot_store.save_snapshots(
            list(snapshots.values())
        )
