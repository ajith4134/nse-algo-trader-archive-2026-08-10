"""Paper-trading ledger — tracks positions and P&L from simulated fills.

Average-cost position accounting: increasing a position updates the
average entry; reducing/closing realizes P&L against it. Purely virtual
money (PLAN §1.4 — paper capital is simulated and dynamic), so this
never touches real funds. Consumed by the paper engine; the prediction-
labeled tables lab (PLAN §9) will attach PredictionRecords to the fills
recorded here.
"""

from dataclasses import dataclass, field

from nse_algo_trader.broker_oms import OrderSide


@dataclass
class PaperPosition:
    instrument_token: int
    net_quantity: int = 0  # +long / -short / 0 flat
    average_entry_price: float = 0.0


@dataclass(frozen=True)
class RecordedPaperFill:
    instrument_token: int
    side: OrderSide
    quantity: int
    price: float
    realized_pnl_from_this_fill: float


class PaperTradingLedger:
    def __init__(self, starting_virtual_cash: float) -> None:
        self.starting_virtual_cash = starting_virtual_cash
        self.realized_pnl = 0.0
        self.recorded_fills: list[RecordedPaperFill] = []
        self._position_by_token: dict[int, PaperPosition] = {}

    def net_quantity(self, instrument_token: int) -> int:
        position = self._position_by_token.get(instrument_token)
        return position.net_quantity if position else 0

    def is_flat(self) -> bool:
        return all(p.net_quantity == 0 for p in self._position_by_token.values())

    def record_fill(
        self, instrument_token: int, side: OrderSide, quantity: int, price: float
    ) -> RecordedPaperFill:
        signed_quantity = quantity if side is OrderSide.BUY else -quantity
        position = self._position_by_token.setdefault(
            instrument_token, PaperPosition(instrument_token)
        )
        realized_from_fill = 0.0

        is_opening_or_increasing = (
            position.net_quantity == 0
            or (position.net_quantity > 0) == (signed_quantity > 0)
        )
        if is_opening_or_increasing:
            combined_quantity = position.net_quantity + signed_quantity
            position.average_entry_price = (
                position.average_entry_price * abs(position.net_quantity)
                + price * abs(signed_quantity)
            ) / abs(combined_quantity)
            position.net_quantity = combined_quantity
        else:
            existing_direction = 1 if position.net_quantity > 0 else -1
            closing_quantity = min(abs(signed_quantity), abs(position.net_quantity))
            realized_from_fill = (
                (price - position.average_entry_price)
                * closing_quantity
                * existing_direction
            )
            self.realized_pnl += realized_from_fill
            leftover = abs(signed_quantity) - abs(position.net_quantity)
            if leftover > 0:  # flipped past flat into the opposite direction
                position.net_quantity = (1 if signed_quantity > 0 else -1) * leftover
                position.average_entry_price = price
            else:
                position.net_quantity += signed_quantity
                if position.net_quantity == 0:
                    position.average_entry_price = 0.0

        recorded_fill = RecordedPaperFill(
            instrument_token, side, quantity, price, realized_from_fill
        )
        self.recorded_fills.append(recorded_fill)
        return recorded_fill

    def unrealized_pnl(self, mark_price_by_token: dict[int, float]) -> float:
        total = 0.0
        for token, position in self._position_by_token.items():
            if position.net_quantity == 0 or token not in mark_price_by_token:
                continue
            total += (
                mark_price_by_token[token] - position.average_entry_price
            ) * position.net_quantity
        return total

    def total_pnl(self, mark_price_by_token: dict[int, float]) -> float:
        return self.realized_pnl + self.unrealized_pnl(mark_price_by_token)
