"""Proposal arbiter — the ONE place a trade is accepted, resized, or vetoed (crypto §03b rule 6).

Given the sleeves' proposals, the capital allocation (lots per proposal), the netted exposures and the
portfolio risk budget, the arbiter produces the final ``ArbitratedOrder`` list:

* **Veto** expired proposals (signal-expiry discipline) and any the allocator gave zero lots.
* **Net & cap** exposure per underlying: when the gross delta-lots on a name exceed the per-name budget,
  every contributing proposal is scaled down proportionally (no sleeve silently blows the name limit).
* **Resize** to the allocator's lots (the capital budget) intersected with the bot's own size hint.
* The **hard portfolio risk stop** (portfolio CVaR over budget) is applied by the supervisor as a final
  uniform scale — it overrides every bot absolutely (crypto §03b rule 5: an objective, not a bot's veto).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.portfolio_supervisor.net_exposure_netting_layer import NetExposure
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeProposal


class ArbitrationOutcome(str, Enum):
    ACCEPT = "accept"
    RESIZE = "resize"
    VETO = "veto"


@dataclass(frozen=True)
class ArbitratedOrder:
    """The supervisor's final decision on one proposal — what actually reaches execution."""

    proposal: TradeProposal
    approved_lots: int
    outcome: ArbitrationOutcome
    rationale: str


class ProposalArbiter:
    """Turns proposals + allocation + netting + budget into the final approved order set."""

    def arbitrate(
        self,
        proposals: list[TradeProposal],
        allocation_lots: dict[int, int],
        net_exposures: dict[str, NetExposure],
        max_net_delta_lots_per_underlying: float,
        now_epoch: float,
    ) -> list[ArbitratedOrder]:
        # per-underlying proportional scale so gross exposure respects the per-name cap
        scale_by_underlying = self._per_name_scales(net_exposures, max_net_delta_lots_per_underlying)

        orders: list[ArbitratedOrder] = []
        for proposal in proposals:
            if proposal.is_expired(now_epoch):
                orders.append(ArbitratedOrder(proposal, 0, ArbitrationOutcome.VETO, "signal expired"))
                continue
            allocated = allocation_lots.get(id(proposal), 0)
            if allocated <= 0:
                orders.append(ArbitratedOrder(proposal, 0, ArbitrationOutcome.VETO,
                                              "allocator assigned zero capital"))
                continue
            capped = min(allocated, proposal.size_hint_lots)
            scale = scale_by_underlying.get(proposal.underlying, 1.0)
            final = int(max(0, round(capped * scale)))
            if final <= 0:
                orders.append(ArbitratedOrder(proposal, 0, ArbitrationOutcome.VETO,
                                              "netted to zero by per-name exposure cap"))
            elif final < proposal.size_hint_lots or scale < 1.0:
                orders.append(ArbitratedOrder(proposal, final, ArbitrationOutcome.RESIZE,
                                              f"resized by allocation/netting (hint {proposal.size_hint_lots}→{final})"))
            else:
                orders.append(ArbitratedOrder(proposal, final, ArbitrationOutcome.ACCEPT, "accepted at full size"))
        return orders

    @staticmethod
    def _per_name_scales(net_exposures: dict[str, NetExposure], cap: float) -> dict[str, float]:
        scales: dict[str, float] = {}
        for underlying, exposure in net_exposures.items():
            if exposure.gross_delta_lots > cap > 0:
                scales[underlying] = cap / exposure.gross_delta_lots  # proportional shrink to the cap
        return scales
