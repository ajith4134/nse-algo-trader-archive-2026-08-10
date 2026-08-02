"""Goal-priority scheduler (Trunk III WILL; research/154). PURE — no I/O.

Turns the multi-objective arbitration into a concrete PLAN: given a concurrency budget (how many
goals the system can pursue at once), schedule the highest-priority mechanisms first — non-dominated
mechanisms ahead of dominated ones, then by arbitration score — and defer the rest. The (queued)
consumer is the entry loop: when capital/concurrency-constrained, open the scheduled mechanisms' candidates first.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScheduledGoal:
    mechanism: str
    priority_rank: int          # 1 = pursue first
    arbitration_score: float
    is_active: bool             # within the concurrency budget → pursue now; else deferred
    is_non_dominated: bool


@dataclass(frozen=True)
class GoalSchedule:
    goals: tuple = field(default_factory=tuple)   # ScheduledGoal, priority order
    active_count: int = 0
    deferred_count: int = 0
    max_concurrent: int = 0
    summary: str = ""


def schedule_goals(arbitration, max_concurrent: int = 3) -> GoalSchedule:
    """Priority-order the arbitrated mechanisms; the top `max_concurrent` are ACTIVE, the rest deferred.

    Ordering: non-dominated (Pareto front) first, then by arbitration score — so the concurrency budget
    is spent on genuinely non-dominated goals before dominated ones."""
    ranked = list(getattr(arbitration, "ranked", ()) or ())
    if not ranked:
        return GoalSchedule(max_concurrent=max_concurrent, summary="no goals to schedule")

    ordered = sorted(ranked, key=lambda m: (not m.is_non_dominated, -m.arbitration_score))
    goals = []
    for rank, m in enumerate(ordered, start=1):
        goals.append(ScheduledGoal(
            mechanism=m.mechanism, priority_rank=rank, arbitration_score=m.arbitration_score,
            is_active=rank <= max_concurrent, is_non_dominated=m.is_non_dominated))

    active = [g for g in goals if g.is_active]
    summary = (f"scheduled {len(goals)} goals; {len(active)} active (budget {max_concurrent}), "
               f"{len(goals) - len(active)} deferred; top: "
               + ", ".join(g.mechanism[:24] for g in active[:3]))
    return GoalSchedule(
        goals=tuple(goals), active_count=len(active), deferred_count=len(goals) - len(active),
        max_concurrent=max_concurrent, summary=summary)
