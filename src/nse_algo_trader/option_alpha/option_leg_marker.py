"""Option-leg mark-to-market — the REAL P&L of a multi-leg option structure from the live chain (slice 4).

The pod lifecycle marked option positions on the underlying price (a directional proxy; a neutral strangle /
condor showed unrealised 0). This prices each leg at its CURRENT premium on the live chain and computes the
structure's true mark-to-market P&L, so the Θ engine's premium-decay gains are real and exits fire on the
spread's actual value.

P&L per share for a position = Σ over legs of  s·(entry_price − current_price)  where s = +1 for a leg you
SOLD (you keep the credit as it decays) and −1 for a leg you BOUGHT. Total = P&L/share × lot_size × lots.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructureMark:
    """The live mark of one option structure: total unrealised P&L + the current net spread value."""

    unrealized_pnl: float
    current_value_per_share: float  # net current premium (Σ sell − Σ buy at live prices)
    entry_value_per_share: float    # net entry premium
    lot_size: int


class OptionLegMarker:
    """Prices a structure's legs at their current live-chain premiums → real mark-to-market P&L."""

    def __init__(self, live_chain_source):
        self._chain_source = live_chain_source

    def mark(self, underlying: str, legs: list[dict], lots: int) -> StructureMark | None:
        """Return the live mark, or None if the chain / any leg is unavailable (caller holds — Rule J)."""
        if not legs or self._chain_source is None:
            return None
        try:
            fetched = self._chain_source.option_chain(underlying)
        except Exception:  # noqa: BLE001 — a feed hiccup holds the position, never fabricates a mark
            return None
        if fetched is None:
            return None
        chain, _trade_date, _spot = fetched
        if chain is None or chain.empty:
            return None

        lot_size = int(chain["lot_size"].iloc[0]) if "lot_size" in chain.columns and len(chain) else 1
        current: dict[tuple[str, float], float] = {}
        for _, row in chain.iterrows():
            right = "CE" if str(row["option_right_code"]).upper().startswith("C") else "PE"
            current[(right, float(row["strike_price"]))] = float(row["close_price"])

        entry_net = 0.0
        current_net = 0.0
        pnl_per_share = 0.0
        for leg in legs:
            key = (str(leg["right"]), float(leg["strike"]))
            cur = current.get(key)
            if cur is None or cur <= 0:
                return None  # a leg's strike vanished from the chain → cannot mark this cycle
            s = 1.0 if str(leg["side"]) == "sell" else -1.0
            entry_price = float(leg["entry_price"])
            leg["current_price"] = round(cur, 2)  # stamp the live premium on the leg → the dashboard shows it
            entry_net += s * entry_price
            current_net += s * cur
            pnl_per_share += s * (entry_price - cur)  # sold legs profit as premium falls; bought legs the reverse

        unrealized = pnl_per_share * lot_size * max(int(lots), 1)
        return StructureMark(
            unrealized_pnl=round(unrealized, 2),
            current_value_per_share=round(current_net, 2),
            entry_value_per_share=round(entry_net, 2),
            lot_size=lot_size,
        )
