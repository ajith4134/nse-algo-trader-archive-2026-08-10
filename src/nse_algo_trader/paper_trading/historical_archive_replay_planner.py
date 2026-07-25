"""Makes the replay feed survivorship-correct — the slice-2 driver that puts the
point-in-time universe INTO the loop (research/62 slice 2; research/53 §11.1).

The live service used to keep a replayed bar only if its instrument is in
*today's* tradable universe. That is the survivorship-bias trap: a stock that
traded on a past day but has since dropped out of today's universe would be
silently erased from that past day's replay, teaching the bot a cleaner past
than the real one.

This planner replaces that test with the honest one: keep a bar only if its
instrument was in the cash universe **on that bar's own date**, per the
`PointInTimeUniverseResolver` (real NSE bhavcopy). When a date has no ingested
bhavcopy to resolve from, it PASSES THE BAR THROUGH unchanged — it never drops
data it cannot adjudicate (that would be a different silent corruption). As
deep-history bhavcopy + delisted-name bars are ingested (BACKLOG), the same code
becomes fully survivorship-free with no further change.
"""

from collections import defaultdict
from datetime import date

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.paper_trading.point_in_time_universe_resolver import (
    PointInTimeUniverseResolver,
)


class HistoricalArchiveReplayPlanner:
    def __init__(
        self, point_in_time_universe_resolver: PointInTimeUniverseResolver
    ) -> None:
        self._point_in_time_universe_resolver = point_in_time_universe_resolver
        # date -> the real cash universe that day, or None when unresolved.
        self._cash_universe_by_date: dict[date, frozenset[str] | None] = {}

    def _cash_universe_on(self, trade_date: date) -> frozenset[str] | None:
        if trade_date not in self._cash_universe_by_date:
            resolver = self._point_in_time_universe_resolver
            self._cash_universe_by_date[trade_date] = (
                resolver.cash_equity_universe_on(trade_date)
                if resolver.has_universe_for(trade_date)
                else None
            )
        return self._cash_universe_by_date[trade_date]

    def symbol_is_eligible_on(self, trading_symbol: str, trade_date: date) -> bool:
        """Was `trading_symbol` in the real cash universe on `trade_date`? True
        by pass-through when that date cannot be resolved (no bhavcopy yet)."""
        cash_universe = self._cash_universe_on(trade_date)
        if cash_universe is None:
            return True
        return trading_symbol in cash_universe

    def filter_bars_to_point_in_time_universe(
        self,
        bars_by_token: dict[int, list[PriceBar]],
        trading_symbol_by_token: dict[int, str],
    ) -> dict[int, list[PriceBar]]:
        """Keep each bar only if its instrument was in the cash universe on that
        bar's own date (survivorship-correct). Tokens with no known symbol are
        dropped (cannot be adjudicated); tokens left with no surviving bars are
        omitted entirely."""
        filtered_bars_by_token: dict[int, list[PriceBar]] = defaultdict(list)
        for instrument_token, bars in bars_by_token.items():
            trading_symbol = trading_symbol_by_token.get(instrument_token)
            if trading_symbol is None:
                continue
            for bar in bars:
                if self.symbol_is_eligible_on(trading_symbol, bar.timestamp.date()):
                    filtered_bars_by_token[instrument_token].append(bar)
        return {token: bars for token, bars in filtered_bars_by_token.items() if bars}
