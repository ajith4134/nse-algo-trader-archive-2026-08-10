"""Directional arbiter — combines BULL P(up) + BEAR P(down) into the trade side (crypto §03b rule 6).

The two directional models each answer a one-sided question; the arbiter is the ONE place their joint
distribution becomes a decision. Meta-labelling logic:

* **Conflict** (both bullish AND bearish confident) → ``FLAT`` — the models disagree, do not take a side.
* **No edge** (neither confident) → ``FLAT``.
* Otherwise the stronger side wins, but only if it clears a **margin** over its opposite AND a minimum
  confidence — a weak directional read never overrides the bot's neutral default.

Conviction scales with how decisively the winning side beats its opposite (the margin), so a barely-there
edge sizes small and a strong, uncontested read sizes large.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.segment_bots.directional_ai.bull_bear_directional_engine import DirectionalView
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide

_MIN_CONFIDENCE = 0.55  # the winning probability must clear this to take a side
_MIN_MARGIN = 0.10  # and beat its opposite by at least this much
_BOTH_CONFIDENT = 0.55  # both sides above this = genuine conflict → FLAT


@dataclass(frozen=True)
class DirectionalVerdict:
    """The arbiter's decision for one instrument."""

    side: TradeSide  # LONG | SHORT | NEUTRAL
    conviction: float  # [0,1]
    p_up: float
    p_down: float
    margin: float  # |p_up - p_down|
    is_conflict: bool
    rationale: str


class DirectionalArbiter:
    """Turns a BULL/BEAR ``DirectionalView`` into a LONG/SHORT/NEUTRAL verdict with conviction."""

    def __init__(
        self,
        min_confidence: float = _MIN_CONFIDENCE,
        min_margin: float = _MIN_MARGIN,
        both_confident: float = _BOTH_CONFIDENT,
    ):
        self._min_conf = min_confidence
        self._min_margin = min_margin
        self._both = both_confident

    def arbitrate(self, view: DirectionalView) -> DirectionalVerdict:
        p_up, p_down = view.p_up, view.p_down
        margin = abs(p_up - p_down)

        if view.maturity != "earned":
            return DirectionalVerdict(TradeSide.NEUTRAL, 0.0, p_up, p_down, margin, False,
                                      "directional models gathering → neutral (bot keeps its existing side)")

        # genuine conflict: both models confident → stand flat (do not guess)
        if p_up >= self._both and p_down >= self._both:
            return DirectionalVerdict(TradeSide.NEUTRAL, 0.0, p_up, p_down, margin, True,
                                      "BULL and BEAR both confident → conflict, FLAT")

        winner_prob = max(p_up, p_down)
        if winner_prob < self._min_conf or margin < self._min_margin:
            return DirectionalVerdict(TradeSide.NEUTRAL, 0.0, p_up, p_down, margin, False,
                                      "no confident, uncontested directional edge → FLAT")

        side = TradeSide.LONG if p_up > p_down else TradeSide.SHORT
        # conviction: how decisively the winner beats its opposite, scaled into [0,1]
        conviction = min(1.0, (margin - self._min_margin) / (1.0 - self._min_margin) + 0.3 * (winner_prob - 0.5) / 0.5)
        return DirectionalVerdict(
            side, round(min(max(conviction, 0.0), 1.0), 4), p_up, p_down, round(margin, 4), False,
            f"{'BULL' if side == TradeSide.LONG else 'BEAR'} wins: P={winner_prob:.2f}, margin {margin:.2f}",
        )
