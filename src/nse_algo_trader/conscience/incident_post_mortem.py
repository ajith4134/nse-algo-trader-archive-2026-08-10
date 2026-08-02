"""Incident post-mortem — the forensic record & review of safety incidents (Trunk VII.14;
research/113).

The three safety organs already built hold their incident state IN MEMORY only, so it is lost on
restart: the Referee's blocked orders (`constitutional_referee`), the off-switch's halts
(`corrigibility_switch`), and the alignment tripwires' critical trips (`alignment_tripwires`).
VII.14 turns those ephemeral events into a durable, reviewable forensic record: a `SafetyIncident`
value per event, persisted append-only by `incident_post_mortem_store`, and summarised here into an
`IncidentPostMortem` (what happened, when, how often, how severe) — a post-mortem the operator can
read after the fact. PURE (no I/O) — the SQLite persistence lives in the store module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# The kinds of safety event worth a forensic record — self-describing incident types.
INCIDENT_TYPE_CONSTITUTION_BLOCK = "constitution_block"      # Referee blocked an order (VII.6)
INCIDENT_TYPE_OFF_SWITCH_HALT = "off_switch_halt"            # off-switch engaged (VII.5)
INCIDENT_TYPE_POSTURE_BREACH = "posture_breach"             # daily posture audit found a violation
INCIDENT_TYPE_WIREHEADING_TRIP = "wireheading_trip"         # wireheading tripwire critical (VII.11)
INCIDENT_TYPE_DECEPTIVE_ALIGNMENT_TRIP = "deceptive_alignment_trip"  # deceptive monitor (VII.10)
INCIDENT_TYPE_GOAL_INTEGRITY_DRIFT = "goal_integrity_drift"  # goal-integrity critical drift (VII)
INCIDENT_TYPE_REGULATORY_VIOLATION = "regulatory_violation"  # SEBI rulebook breach (VII ethics/law)

_CRITICAL_SEVERITIES = frozenset({"critical", "hard"})


@dataclass(frozen=True)
class SafetyIncident:
    """One recorded safety incident. `trace_id` is the dedup key (reuse the constitutional
    verdict's deterministic fingerprint; synthesise a stable one for halts/trips) so the same daily
    event logged twice collapses to one forensic row."""

    incident_type: str
    severity: str
    occurred_at: str  # ISO-8601 timestamp
    subject: str      # the scope / mechanism / config the incident concerns
    detail: str
    trace_id: str

    @property
    def is_critical(self) -> bool:
        return self.severity in _CRITICAL_SEVERITIES


@dataclass(frozen=True)
class IncidentPostMortem:
    """The reviewable summary over a forensic incident record."""

    total: int
    critical_count: int
    count_by_type: dict[str, int]
    count_by_severity: dict[str, int]
    first_seen: str | None
    last_seen: str | None
    most_recent: tuple[SafetyIncident, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return self.total == 0

    @property
    def headline(self) -> str:
        if self.total == 0:
            return "no safety incidents recorded — clean forensic record"
        last = self.most_recent[0] if self.most_recent else None
        last_note = f" · last: {last.incident_type} ({last.occurred_at})" if last else ""
        crit = f" · {self.critical_count} critical" if self.critical_count else ""
        return f"{self.total} safety incident(s){crit}{last_note}"


def summarize_incident_post_mortem(
    incidents: list[SafetyIncident], recent_kept: int = 5
) -> IncidentPostMortem:
    """Summarise a forensic incident record (oldest-first input) into a post-mortem. Pure — the
    dashboard surface and any operator review consume this over the store's `all_incidents()`."""
    if not incidents:
        return IncidentPostMortem(
            total=0, critical_count=0, count_by_type={}, count_by_severity={},
            first_seen=None, last_seen=None, most_recent=(),
        )
    by_type = Counter(i.incident_type for i in incidents)
    by_severity = Counter(i.severity for i in incidents)
    ordered_by_time = sorted(incidents, key=lambda i: i.occurred_at)
    return IncidentPostMortem(
        total=len(incidents),
        critical_count=sum(1 for i in incidents if i.is_critical),
        count_by_type=dict(by_type),
        count_by_severity=dict(by_severity),
        first_seen=ordered_by_time[0].occurred_at,
        last_seen=ordered_by_time[-1].occurred_at,
        most_recent=tuple(reversed(ordered_by_time[-recent_kept:])),  # newest first
    )
