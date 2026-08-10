"""Cross-bot crowding monitor — the supervisor's early-warning that the sleeves are converging (§8b, Rule P).

The net-exposure netting layer catches two bots on the SAME underlying. This catches the subtler, more
dangerous case a multi-manager desk fears: the three sleeves independently piling into the same DIRECTION /
FACTOR across DIFFERENT names, so a single macro shock hits all of them at once (the "pod-shop crowding"
failure). It measures, per cycle:

* **Directional concentration** — the net signed conviction across all proposals (are the bots collectively
  long or short the market?) and the Herfindahl concentration of exposure by underlying.
* **Same-name pile-ups** — underlyings carrying proposals from 2+ bots on the same side.
* **A crowding score in [0,1]** blending the two, with a level (calm / elevated / crowded) the supervisor
  uses to shrink gross risk BEFORE the correlated drawdown — the sibling of the netting cap.

Carried state = a rolling history of the crowding score (persisted), so a RISING crowding trend is itself a
signal, not just the point level.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from nse_algo_trader.segment_bots.segment_bot_protocol import TradeProposal, TradeSide


def _signed_conviction(proposal: TradeProposal) -> float:
    sign = {TradeSide.LONG: 1.0, TradeSide.SHORT: -1.0, TradeSide.NEUTRAL: 0.0}[proposal.side]
    return sign * proposal.conviction * proposal.size_hint_lots


@dataclass(frozen=True)
class CrowdingAssessment:
    """The cross-bot crowding picture for one cycle."""

    crowding_score: float  # [0,1]
    level: str  # calm | elevated | crowded
    net_directional_bias: float  # signed; >0 = collectively long
    exposure_herfindahl: float  # [0,1]; 1 = all exposure on one underlying
    same_name_pileups: tuple[str, ...]  # underlyings with 2+ bots same-side
    rising: bool  # crowding score above its recent rolling mean
    recommended_gross_scale: float  # <1.0 → the supervisor should shrink gross risk
    field_notes: dict = field(default_factory=dict)


class CrossBotCrowdingMonitor:
    """Scores cross-sleeve crowding each cycle and recommends a gross-risk scale, with carried history."""

    def __init__(self, history_path: Path | None = None, crowded_threshold: float = 0.6):
        self._history_path = history_path
        self._crowded = crowded_threshold

    def assess(self, proposals: list[TradeProposal]) -> CrowdingAssessment:
        if not proposals:
            return CrowdingAssessment(0.0, "calm", 0.0, 0.0, (), False, 1.0, {"reason": "no proposals"})

        signed = [_signed_conviction(p) for p in proposals]
        gross = sum(abs(s) for s in signed) or 1.0
        net_bias = sum(signed) / gross  # [-1,1]; magnitude = one-sidedness

        # Herfindahl of |exposure| by underlying — high = concentrated in few names
        by_underlying: dict[str, float] = {}
        for p, s in zip(proposals, signed, strict=False):
            by_underlying[p.underlying] = by_underlying.get(p.underlying, 0.0) + abs(s)
        weights = [v / gross for v in by_underlying.values()]
        herfindahl = sum(w * w for w in weights)

        # same-name pile-ups: 2+ bots proposing the same side on one underlying
        side_by_name: dict[str, set[tuple[str, str]]] = {}
        for p in proposals:
            side_by_name.setdefault(p.underlying, set()).add((p.bot_name.split(":")[0], p.side.value))
        pileups = tuple(sorted(
            u for u, entries in side_by_name.items()
            if len({b for b, _ in entries}) >= 2 and len({sd for _, sd in entries}) == 1
        ))

        # crowding score blends one-sided directional bias + name concentration + pile-up presence
        score = min(1.0, 0.5 * abs(net_bias) + 0.35 * herfindahl + 0.15 * (1.0 if pileups else 0.0))
        rising = self._is_rising(score)
        level = "crowded" if score >= self._crowded else ("elevated" if score >= self._crowded / 2 else "calm")
        # shrink gross risk as crowding rises past the threshold (linear to 0.5 at score 1.0)
        gross_scale = 1.0 if score < self._crowded else max(0.5, 1.0 - (score - self._crowded))

        return CrowdingAssessment(
            crowding_score=round(score, 4), level=level, net_directional_bias=round(net_bias, 4),
            exposure_herfindahl=round(herfindahl, 4), same_name_pileups=pileups, rising=rising,
            recommended_gross_scale=round(gross_scale, 4),
            field_notes={"n_underlyings": len(by_underlying), "gross": round(gross, 2)},
        )

    def _is_rising(self, score: float) -> bool:
        if self._history_path is None:
            return False
        history: list[float] = []
        if self._history_path.exists():
            try:
                history = json.loads(self._history_path.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        recent_mean = (sum(history[-20:]) / len(history[-20:])) if history else score
        history.append(score)
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(json.dumps(history[-200:]))
        return score > recent_mean * 1.15  # >15% above the recent rolling mean = a rising crowding trend
