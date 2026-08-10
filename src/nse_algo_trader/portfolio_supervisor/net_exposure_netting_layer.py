"""Net-exposure netting layer — the #1 most-forgotten pod control (crypto Feature-Catalogue rank 1).

Two bots on opposite sides of the same underlying pay fees BOTH ways and carry offsetting risk the top of
the book never sees. This layer aggregates every proposal's signed delta-exposure per underlying, surfaces
conflicts (both long and short present on one name), and reports the NET and GROSS exposure so the arbiter
can cap by the portfolio risk budget rather than let the sleeves silently fight each other.

Exposure is measured in delta-lots: ``side_sign · size_hint_lots · |structure.net_delta|`` — a directional
long call and a short put on the same index net against each other; two premium-selling condors on the same
index add up (gross) toward the per-name cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.segment_bots.segment_bot_protocol import TradeProposal, TradeSide


def _signed_delta_lots(proposal: TradeProposal) -> float:
    sign = {TradeSide.LONG: 1.0, TradeSide.SHORT: -1.0, TradeSide.NEUTRAL: 0.0}[proposal.side]
    # a delta-neutral structure still carries structural directional exposure via its net_delta sign
    delta = proposal.structure.net_delta if proposal.structure.net_delta != 0.0 else sign
    return sign_or(delta, sign) * proposal.size_hint_lots * abs(proposal.structure.net_delta or 1.0)


def sign_or(delta: float, side_sign: float) -> float:
    """Use the structure's net-delta sign when it carries one, else the trade side sign."""
    if delta > 0:
        return 1.0
    if delta < 0:
        return -1.0
    return side_sign


@dataclass(frozen=True)
class NetExposure:
    """The aggregated exposure of all proposals on one underlying."""

    underlying: str
    net_delta_lots: float  # signed — longs and shorts cancel
    gross_delta_lots: float  # absolute sum — everything adds
    contributing_bots: tuple[str, ...]
    is_conflicting: bool  # both a long-biased and a short-biased proposal present on this name
    proposal_ids: tuple[int, ...] = field(default_factory=tuple)


class NetExposureNettingLayer:
    """Aggregates proposals into per-underlying net/gross exposure and flags cross-sleeve conflicts."""

    def net(self, proposals: list[TradeProposal]) -> dict[str, NetExposure]:
        by_underlying: dict[str, list[TradeProposal]] = {}
        for proposal in proposals:
            by_underlying.setdefault(proposal.underlying, []).append(proposal)

        result: dict[str, NetExposure] = {}
        for underlying, group in by_underlying.items():
            signed = [_signed_delta_lots(p) for p in group]
            net = sum(signed)
            gross = sum(abs(s) for s in signed)
            has_long = any(s > 0 for s in signed)
            has_short = any(s < 0 for s in signed)
            result[underlying] = NetExposure(
                underlying=underlying,
                net_delta_lots=net,
                gross_delta_lots=gross,
                contributing_bots=tuple(sorted({p.bot_name for p in group})),
                is_conflicting=has_long and has_short,
                proposal_ids=tuple(id(p) for p in group),
            )
        return result
