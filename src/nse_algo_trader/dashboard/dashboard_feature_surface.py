"""Feature-surface registry — the systematic way EVERY feature shows on the dashboard
(Rule N; research/91).

Instead of hand-writing a panel per feature (which is forgotten), each feature emits a
uniform `DashboardFeatureSurface` (title, live status, headline metrics, optional note).
The dashboard renders them all in one "Feature coverage" panel, and a manifest + audit
make a missing surface a TEST FAILURE + a visible "not yet surfaced" row — so "is the
dashboard up to date with all features?" is answerable at a glance and can't silently rot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A feature's live state. Statuses map to the dashboard's status colours (good/warn/
# neutral), always shown with a label + dot — never colour alone (accessibility).
_VALID_STATUSES = ("active", "gathering", "idle", "blocked", "off", "unknown")


@dataclass(frozen=True)
class DashboardFeatureSurface:
    key: str  # stable manifest key
    title: str
    status: str  # one of _VALID_STATUSES
    metrics: tuple[tuple[str, str], ...] = ()  # (label, value) headline metrics
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unknown feature-surface status: {self.status!r}")

    def to_json_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "status": self.status,
            "metrics": [list(m) for m in self.metrics], "note": self.note,
        }


# The canonical list of features that MUST surface on the dashboard. A feature whose key
# is here but has no built surface renders as "not yet surfaced" and fails the coverage
# audit — the enforcement point behind Rule N. Add a row when a user-visible feature ships.
FEATURE_SURFACE_MANIFEST: tuple[tuple[str, str], ...] = (
    ("multi_broker_sourcing", "Multi-broker data sourcing (failover + gap-fill)"),
    ("replay_fidelity", "Replay fidelity tier (market-closed)"),
    ("replay_curriculum", "Deficit-driven replay curriculum (regime coverage)"),
    ("champion_challenger", "Champion-challenger strategy config (global + per-regime)"),
    ("market_impact_fills", "Market-impact fill model"),
    ("market_regime_memory", "Market-regime memory calibration"),
)

MANIFEST_KEYS: frozenset[str] = frozenset(k for k, _ in FEATURE_SURFACE_MANIFEST)


@dataclass(frozen=True)
class FeatureCoverageReport:
    """The full coverage picture: every manifest feature with its surface (or a
    'not yet surfaced' placeholder). What the dashboard panel + the audit consume."""

    surfaces: tuple[DashboardFeatureSurface, ...] = field(default_factory=tuple)

    def by_key(self) -> dict[str, DashboardFeatureSurface]:
        return {s.key: s for s in self.surfaces}

    def missing_keys(self) -> frozenset[str]:
        """Manifest features with no surface (the coverage GAP — must be empty for Rule N)."""
        return MANIFEST_KEYS - set(self.by_key())

    def rows_in_manifest_order(self) -> list[DashboardFeatureSurface]:
        """Every manifest feature in order, with a placeholder 'not yet surfaced' row for
        any that has no built surface — so ALL features are always listed."""
        built = self.by_key()
        return [
            built.get(key, DashboardFeatureSurface(key=key, title=title, status="unknown",
                                                   note="not yet surfaced"))
            for key, title in FEATURE_SURFACE_MANIFEST
        ]
