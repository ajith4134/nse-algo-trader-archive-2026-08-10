"""Global Workspace / broadcast bus (Trunk VIII keystone; research/123) — the integrator.

Global Workspace Theory (Baars; Dehaene's global neuronal workspace; Blum & Blum's Conscious Turing
Machine): parallel specialist processes compete for a LIMITED-CAPACITY workspace, the winning
coalition crosses an IGNITION THRESHOLD, and is BROADCAST as the dominant global context the whole
system sees. Here the specialists are the bot's faculties (VII safety organs, debate panel,
allocator, opponent ledger, calibration…); each cycle collects their current signals as uniform
`WorkspaceContribution`s, scores salience, picks the winner, and — if it ignites — broadcasts it.

Sourcing (research/123): the broadcast BUS is the vendored `blinker` (MIT, Pallets/Flask-proven —
the one production-usable OSS piece); the record/scorer/competition/ignition/loop are thin project
glue (no OSS fits the trading-signal domain), structured after `ctm-ai`'s up-tree→workspace→down-tree
shape. blinker gotcha: receivers are weak-ref by default and get GC'd → `connect(weak=False)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blinker import signal

# Salience weights (weighted sum, each factor 0..1 → salience 0..1). Urgency dominates — a workspace
# should be grabbed by what is time-critical, then relevance, then the signal's own confidence.
_SALIENCE_URGENCY_WEIGHT = 0.5
_SALIENCE_RELEVANCE_WEIGHT = 0.3
_SALIENCE_CONFIDENCE_WEIGHT = 0.2

_GLOBAL_WORKSPACE_SIGNAL_NAME = "global_workspace_broadcast"


@dataclass(frozen=True)
class WorkspaceContribution:
    """One faculty's bid for the workspace. `kind` groups signals (safety/opportunity/risk/info).
    A critical safety contribution short-circuits salience to the top — safety dominates the mind."""

    source: str
    kind: str
    urgency: float       # 0..1 — how time-critical
    relevance: float     # 0..1 — how relevant to the current decision
    confidence: float    # 0..1 — the faculty's own confidence in the signal
    content: str         # human-readable summary of what this faculty is saying
    is_critical: bool = False


def salience_score(contribution: WorkspaceContribution) -> float:
    """Salience of a contribution (0..1). A critical safety contribution is floored to 1.0 so it
    always wins the workspace; otherwise a weighted sum of urgency, relevance, and confidence."""
    if contribution.is_critical:
        return 1.0
    return (
        _SALIENCE_URGENCY_WEIGHT * contribution.urgency
        + _SALIENCE_RELEVANCE_WEIGHT * contribution.relevance
        + _SALIENCE_CONFIDENCE_WEIGHT * contribution.confidence
    )


@dataclass(frozen=True)
class WorkspaceBroadcast:
    """The outcome of one workspace cycle. `ignited` False = nothing crossed the threshold (nothing
    dominant this cycle). `coalition` = the sources within ε of the winner (co-active signals)."""

    winner_source: str
    kind: str
    content: str
    salience: float
    ignited: bool
    coalition: tuple[str, ...] = field(default_factory=tuple)
    runner_up: str | None = None


class GlobalWorkspace:
    """The limited-capacity workspace + ignition + broadcast bus. Each `run_cycle` scores the
    contributions, picks the winner, and — if salience ≥ the ignition threshold — broadcasts it over
    a `blinker` signal so any subscriber sees the dominant global context."""

    def __init__(
        self, ignition_threshold: float = 0.55, coalition_epsilon: float = 0.10
    ) -> None:
        self._ignition_threshold = ignition_threshold
        self._coalition_epsilon = coalition_epsilon
        self._signal = signal(_GLOBAL_WORKSPACE_SIGNAL_NAME)
        self._subscribers: list = []  # strong refs (blinker receivers are weak by default)
        self.latest_broadcast: WorkspaceBroadcast | None = None

    def subscribe(self, receiver) -> None:
        """Register a subscriber that receives every IGNITED broadcast as `broadcast=<WorkspaceBroadcast>`.
        Held with a strong ref + connected `weak=False` so it survives to fire (research/123 gotcha)."""
        self._subscribers.append(receiver)
        self._signal.connect(receiver, weak=False)

    def run_cycle(
        self, contributions: list[WorkspaceContribution]
    ) -> WorkspaceBroadcast | None:
        """Collect → score → compete → ignite → broadcast. Returns the cycle's broadcast (with its
        `ignited` flag), or None when there were no contributions. Only an IGNITED broadcast is sent
        on the bus (GWT: only ignited content becomes global); the current focus is always cached."""
        if not contributions:
            return None
        from nse_algo_trader.sentience.coalition_formation import form_coalition

        scored = sorted(contributions, key=salience_score, reverse=True)
        winner = scored[0]
        # Coalition formation (research/127): co-active same-kind signals corroborate and their
        # COMBINED salience — amplified above the lone winner's — drives ignition.
        coalition = form_coalition(
            [(c, salience_score(c)) for c in scored], epsilon=self._coalition_epsilon
        )
        effective_salience = coalition.combined_salience
        ignited = effective_salience >= self._ignition_threshold
        broadcast = WorkspaceBroadcast(
            winner_source=winner.source, kind=winner.kind, content=winner.content,
            salience=effective_salience, ignited=ignited, coalition=coalition.members,
            runner_up=coalition.runner_up,
        )
        self.latest_broadcast = broadcast
        if ignited:
            self._signal.send("global_workspace", broadcast=broadcast)
        return broadcast
