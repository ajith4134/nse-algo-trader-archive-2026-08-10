"""Provenance + fidelity tagging for replayed experience — the safety firewall
that stops 24/7 simulation from silently corrupting the live brain (research/62
part P6; research/53 §8.2, §10.3).

The more indistinguishable-from-live the replay feels, the more the learning
substrate MUST know which experiences were truly live versus replayed, and — for
replayed ones — how faithful that particular day's data actually was. Fidelity
is era-dependent (research/53 §10.3): depth does not exist for the past (record
forward only), per-order tick only starts ~Dec-2007, news is sparse before ~2010.
A lesson drawn from a thin 2009 bar-only day must not carry the same weight as one
from a full-depth 2026 session.

Every replayed datum/experience is stamped with a `DataProvenance` and a
`ReplayFidelityTier` so the information-diet ledger and the antibody can weight and,
when needed, down-weight sim-derived confidence — and a replay-only lesson can never
outrank live evidence. This module only assigns and carries the tags; consuming them
in the calibration/antibody path is the slice-3 memory-drain wiring (BACKLOG).
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class DataProvenance(str, Enum):
    """Where an experience's data came from — the top-level trust axis."""

    LIVE = "live"  # real live market session — the ground truth
    REPLAY_FAITHFUL = "replay_faithful"  # real historical archive replayed as-live
    COUNTERFACTUAL = "counterfactual"  # a real day perturbed (ADVANCED tier)
    SYNTHETIC = "synthetic"  # a day that never happened (ULTRA tier)


class ReplayFidelityTier(str, Enum):
    """How complete the replayed data was — the era-dependent fidelity axis
    (research/53 §10.3). Ordered best→thinnest."""

    FULL_LIVE_DEPTH = "full_live_depth"  # today/forward: recorded L2/L3 depth
    RECORDED_DEPTH = "recorded_depth"  # depth we recorded forward ourselves
    TICK_DERIVED = "tick_derived"  # licensed per-order tick (~Dec-2007+), no true depth
    TRADES_ONLY = "trades_only"  # trade prints only (NSE archive 1995–2007)
    BAR_ONLY = "bar_only"  # OHLCV candles only (free/broker source) — the BASE floor


# NSE per-order tick history begins ~Dec-2007; before it the archive is
# trades-only; true recorded depth only exists from when we start recording
# forward. These era boundaries drive the default fidelity of a replayed day
# (research/53 §10.3, research/54, research/59).
_NSE_PER_ORDER_TICK_ERA_START = date(2007, 12, 1)


@dataclass(frozen=True)
class ProvenanceStamp:
    """The trust label carried alongside a replayed datum or experience."""

    provenance: DataProvenance
    fidelity_tier: ReplayFidelityTier
    session_date: date | None = None


class ReplayExperienceProvenanceTagger:
    """Stamps replayed data with its provenance and (era-appropriate) fidelity.

    The default fidelity is the honest floor for the BASE tier — bar-only replay
    of a free/broker source. `best_available_fidelity_for` raises the tier for a
    date once a richer source (recorded depth, licensed tick) is actually wired
    in, keeping fidelity truthful to what that specific day's data really was.
    """

    def __init__(
        self,
        provenance: DataProvenance = DataProvenance.REPLAY_FAITHFUL,
        default_fidelity_tier: ReplayFidelityTier = ReplayFidelityTier.BAR_ONLY,
    ) -> None:
        self._provenance = provenance
        self._default_fidelity_tier = default_fidelity_tier

    def stamp_for_session(self, session_date: date | None = None) -> ProvenanceStamp:
        return ProvenanceStamp(
            provenance=self._provenance,
            fidelity_tier=self._default_fidelity_tier,
            session_date=session_date,
        )

    @staticmethod
    def best_available_fidelity_for(
        session_date: date,
        have_recorded_depth: bool = False,
        have_licensed_tick: bool = False,
    ) -> ReplayFidelityTier:
        """The richest fidelity tier truthfully available for a replayed day,
        given which higher-fidelity sources are wired in. BASE runs bar-only;
        this ratchets up as slices 4+ add recorded depth / licensed tick."""
        if have_recorded_depth:
            return ReplayFidelityTier.RECORDED_DEPTH
        if have_licensed_tick:
            if session_date >= _NSE_PER_ORDER_TICK_ERA_START:
                return ReplayFidelityTier.TICK_DERIVED
            return ReplayFidelityTier.TRADES_ONLY
        return ReplayFidelityTier.BAR_ONLY
