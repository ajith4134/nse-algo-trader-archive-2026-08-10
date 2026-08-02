"""Higher-order monitoring / metacognition (Trunk VIII; research/131) — the mind watching itself.

Monitors the Global Workspace's OWN operation over recent cycles: is it igniting too often (no
discrimination — everything dominates), too rarely (not functioning), or starved of faculties? A
health state, referencing pybreaker's healthy/degraded state pattern (research/125). Read-only
metacognitive diagnostic. PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass

# Health states (referencing pybreaker's closed/open idea, named for this domain).
HEALTHY = "healthy"
OVER_IGNITING = "over-igniting"      # ignites almost every cycle → no discrimination
UNDER_IGNITING = "under-igniting"    # rarely ignites → workspace not functioning
STARVED = "starved"                  # faculties barely contributing → nothing to integrate


@dataclass(frozen=True)
class MetacognitionReport:
    cycles_observed: int
    ignition_rate: float
    mean_faculty_count: float
    health_state: str
    summary: str = ""

    @property
    def is_healthy(self) -> bool:
        return self.health_state == HEALTHY


def assess_metacognition(
    cycle_log: list,
    min_cycles: int = 4,
    over_threshold: float = 0.95,
    under_threshold: float = 0.10,
    starved_faculty_mean: float = 0.5,
) -> MetacognitionReport:
    """Assess the workspace's own operation from a log of recent `(ignited: bool, faculty_count: int)`
    cycles. Returns the ignition rate + a health state."""
    n = len(cycle_log)
    if n == 0:
        return MetacognitionReport(0, 0.0, 0.0, HEALTHY, "no workspace cycles observed yet")
    ignition_rate = sum(1 for ignited, _ in cycle_log if ignited) / n
    mean_faculty = sum(fc for _, fc in cycle_log) / n

    if mean_faculty < starved_faculty_mean:
        state = STARVED
    elif n >= min_cycles and ignition_rate >= over_threshold:
        state = OVER_IGNITING
    elif n >= min_cycles and ignition_rate <= under_threshold:
        state = UNDER_IGNITING
    else:
        state = HEALTHY

    summary = (
        f"workspace {state}: ignition rate {ignition_rate:.0%} over {n} cycles, "
        f"mean {mean_faculty:.1f} faculties/cycle"
    )
    return MetacognitionReport(
        cycles_observed=n, ignition_rate=ignition_rate, mean_faculty_count=mean_faculty,
        health_state=state, summary=summary,
    )
