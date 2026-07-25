"""Keeps a replayed price series continuous across split/bonus ex-dates — the
slice-2 P3 continuity engine (research/62 §4a; research/53 §11.2).

The bot still sees the RAW price that actually printed as "the price now"
(`ReplayUniverseFeed.latest_price_by_token` is untouched). But when it looks at a
*series* — the lookback that feeds indicators — bars from before an ex-date sit on
a different price scale than bars after it, and the structural gap would read as a
crash/spike. This engine multiplies each pre-ex-date bar by the cumulative
adjustment factor of every action between that bar and the replay clock, bringing
older bars onto the current scale so the series is continuous. A bar on/after the
last ex-date keeps factor 1.0 — it stays raw.

It is a pure transform over `CorporateAction` records (sourced from
`market_data.nse_corporate_action_source`); the records come from the real NSE
calendar in production and from an injected fake in hermetic tests.
"""

from __future__ import annotations

from datetime import date

from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.market_data.nse_corporate_action_source import CorporateAction


class CorporateActionAdjustmentEngine:
    def __init__(
        self, corporate_actions_by_symbol: dict[str, list[CorporateAction]]
    ) -> None:
        # Sorted by ex-date so factor products are deterministic.
        self._actions_by_symbol = {
            symbol: sorted(actions, key=lambda action: action.ex_date)
            for symbol, actions in corporate_actions_by_symbol.items()
        }

    def cumulative_price_factor(
        self, trading_symbol: str, bar_date: date, as_of_date: date
    ) -> float:
        """Product of the adjustment factors of every action for `trading_symbol`
        whose ex-date is AFTER `bar_date` and at/before `as_of_date` — i.e. every
        action that has repriced the stock between this bar and the replay clock.
        1.0 when there is none (bar stays raw)."""
        factor = 1.0
        for action in self._actions_by_symbol.get(trading_symbol, ()):
            if bar_date < action.ex_date <= as_of_date:
                factor *= action.price_adjustment_factor
        return factor

    def adjust_bars_for_continuity(
        self, trading_symbol: str, bars: list[PriceBar], as_of_date: date
    ) -> list[PriceBar]:
        """Return `bars` with pre-ex-date prices scaled onto the as-of scale so
        the series is continuous. Prices ×factor; volume ÷factor (turnover
        preserved). Bars with factor 1.0 are returned unchanged."""
        if trading_symbol not in self._actions_by_symbol:
            return bars
        adjusted: list[PriceBar] = []
        for bar in bars:
            factor = self.cumulative_price_factor(
                trading_symbol, bar.timestamp.date(), as_of_date
            )
            if factor == 1.0:
                adjusted.append(bar)
                continue
            adjusted.append(
                PriceBar(
                    instrument_token=bar.instrument_token,
                    timestamp=bar.timestamp,
                    interval=bar.interval,
                    open_price=bar.open_price * factor,
                    high_price=bar.high_price * factor,
                    low_price=bar.low_price * factor,
                    close_price=bar.close_price * factor,
                    volume=int(round(bar.volume / factor)) if factor else bar.volume,
                    open_interest=bar.open_interest,
                )
            )
        return adjusted
