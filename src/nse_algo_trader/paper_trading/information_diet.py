"""Information-diet accounting (§10 institution feature, research/52).

Accounts for WHAT information the bot consumes to decide, and whether that diet is
healthy. The point is self-awareness: the loud failure this catches is the whole
Layer-10 learning apparatus (memory veto + recalibration) NOT influencing any
trades — the bot dutifully recording 200+ experiences while trading purely on the
base ADX signal, its learning inert.

Pure aggregation over counters the loop already tracks (defers, vetoes,
recalibrations, shadow probes) plus a `considered` denominator, so it is trivially
testable and safe.
"""

from dataclasses import dataclass


class InformationDietSource:
    """The named information sources that shape an entry decision."""

    ADX_REGIME = "ADX regime confidence"
    OPPONENT_LEDGER = "opponent ledger (positioning)"
    MEMORY_ANTIBODY = "memory antibody (veto)"
    MEMORY_RECALIBRATION = "memory recalibration"
    SHADOW_PROBE = "shadow probe (recovery)"


class InformationDietHealth:
    GATHERING = "gathering"
    HEALTHY = "healthy"
    WARNING = "warning"


# Below this many considered decisions the diet read is not yet meaningful.
_MIN_DECISIONS_FOR_HEALTH = 20

# §53 slice 3b-i (research/64/53 §8.2): when the memory the bot learns from is
# dominated by 24/7 REPLAY experiences rather than real live sessions, that is an
# over-reliance the bot should flag — a replayed, era-thin lesson is lower
# fidelity than a live one. Trips the WARNING once there is enough of an
# experience base to judge the mix.
_MAX_HEALTHY_REPLAY_SHARE = 0.5
_MIN_EXPERIENCES_FOR_REPLAY_MIX = 20


@dataclass(frozen=True)
class InformationDiet:
    """How the sources influenced the decisions considered so far. Each source's
    share in `influence_share_by_source` is its own engagement RATE (that
    source's actions ÷ decisions) — a rate, since one decision can trigger more
    than one memory action (e.g. recalibrated AND vetoed). `memory_influence_share`
    is the combined memory-action rate, CLAMPED to ≤1.0 (a decision counts as
    memory-shaped at most once) so it reads as a share of decisions."""

    decisions_considered: int
    influence_share_by_source: dict[str, float]
    memory_influence_share: float
    health_status: str
    note: str
    # §53 slice 3b-i: fraction of the learned experience base that is 24/7 replay
    # (vs live). High = over-reliance on replayed lessons → a WARNING.
    replay_experience_share: float = 0.0


def read_information_diet(
    decisions_considered: int,
    positioning_deferred: int,
    antibody_vetoed: int,
    memory_recalibrated: int,
    shadow_probes: int,
    live_experience_count: int = 0,
    replay_experience_count: int = 0,
) -> InformationDiet:
    """Aggregate the loop's decision-input counters into a diet + health read.
    ADX regime confidence shapes 100% of decisions (it produces every win-
    probability); the health check is whether the OTHER sources — above all the
    learned memory — actually engage."""
    considered = max(decisions_considered, 0)

    def share(count: int) -> float:
        return round(count / considered, 3) if considered else 0.0

    memory_engagements = antibody_vetoed + memory_recalibrated + shadow_probes
    # Clamp: one decision can trigger several memory actions (recalibrated AND
    # vetoed), so the summed rate can exceed 1 — as a SHARE-of-decisions it caps
    # at 100% (a decision is "memory-shaped" at most once).
    memory_influence_share = min(1.0, share(memory_engagements))
    influence_share_by_source = {
        InformationDietSource.ADX_REGIME: 1.0 if considered else 0.0,
        InformationDietSource.OPPONENT_LEDGER: share(positioning_deferred),
        InformationDietSource.MEMORY_ANTIBODY: share(antibody_vetoed),
        InformationDietSource.MEMORY_RECALIBRATION: share(memory_recalibrated),
        InformationDietSource.SHADOW_PROBE: share(shadow_probes),
    }

    total_experiences = max(live_experience_count, 0) + max(replay_experience_count, 0)
    replay_experience_share = (
        max(replay_experience_count, 0) / total_experiences if total_experiences else 0.0
    )
    over_relies_on_replay = (
        total_experiences >= _MIN_EXPERIENCES_FOR_REPLAY_MIX
        and replay_experience_share >= _MAX_HEALTHY_REPLAY_SHARE
    )

    if considered < _MIN_DECISIONS_FOR_HEALTH:
        status = InformationDietHealth.GATHERING
        note = (
            f"{considered}/{_MIN_DECISIONS_FOR_HEALTH} decisions — gathering before "
            "the diet is meaningful."
        )
    elif memory_engagements == 0:
        status = InformationDietHealth.WARNING
        note = (
            "Learning is INERT: memory (veto + recalibration) shaped 0 of "
            f"{considered} decisions — the bot is trading purely on the base ADX "
            "signal, ignoring what it has recorded."
        )
    elif over_relies_on_replay:
        status = InformationDietHealth.WARNING
        note = (
            f"OVER-RELYING on replay: {replay_experience_share:.0%} of the "
            f"{total_experiences} learned experiences are 24/7 REPLAY (bar-only, "
            "lower fidelity) rather than live — replayed lessons are down-weighted "
            "in the veto/recalibration, but this thin a live base is a caution."
        )
    else:
        status = InformationDietHealth.HEALTHY
        recal_rate = influence_share_by_source[
            InformationDietSource.MEMORY_RECALIBRATION
        ]
        veto_rate = influence_share_by_source[InformationDietSource.MEMORY_ANTIBODY]
        note = (
            f"Memory active over {considered} decisions — recalibration on "
            f"{recal_rate:.0%}, veto on {veto_rate:.0%} — alongside the ADX base "
            "signal (a healthy diet)."
        )
    return InformationDiet(
        decisions_considered=considered,
        influence_share_by_source=influence_share_by_source,
        memory_influence_share=memory_influence_share,
        health_status=status,
        note=note,
        replay_experience_share=round(replay_experience_share, 3),
    )
