"""Trunk X AUTOPOIESIS — the organism's MEMBERSHIP set (boundary maintenance) + the maintains-graph.

This module answers two autopoietic questions the system could not previously ask about itself:

  1. **What am I made of?** (self vs non-self) — the explicit registry of every component that is a
     member of this organism, its class, its criticality, and the vital signs it is expected to emit.
     Anything not registered is non-self: it may be an EXOGENOUS boundary input (the broker API, the NSE
     feed, the OS clock, the human operator) or an intruder, and the two are distinguished by explicit
     declaration — never by inference.
  2. **What maintains what?** — the curated `G_maintains` overlay, where an edge `u -> v` means
     "component u is maintained/produced by component v" (v keeps u alive, current, or correct).

`G_maintains` is deliberately NOT the Python import graph. An import edge means "u *uses* v's code",
which is neither necessary nor sufficient for "v maintains u" (research/169 §2.1). Chemical Organization
Theory's species are named, explicit entities, so the maintenance relation must be declared by hand and
audited — which is exactly what makes an unmaintained component (a closure violation) detectable.

The registry is the substrate for `operational_closure_auditor` (SCC/condensation over these edges) and
for `component_telemetry_collector` (which vital signs to read per component class).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ORGANISM_STATE_DIRECTORY = Path("~/.nse_algo_trader").expanduser()


class ComponentClass(str, Enum):
    """Population groups for hierarchical partial pooling (research/168 §5).

    Components of the same class share a failure-rate prior, so a class with many members (8 SQLite
    stores) lends statistical strength to each individual member that has seen no failures yet. This
    is what makes day-one estimates principled instead of undefined (Rule Q).
    """

    PERSISTENT_STORE = "persistent_store"        # SQLite databases
    PERSISTED_ARTIFACT = "persisted_artifact"    # JSON/joblib state + trained models
    BROKER_SESSION = "broker_session"            # daily-expiring broker auth
    BACKGROUND_THREAD = "background_thread"      # long-lived worker threads
    CADENCE_ENGINE = "cadence_engine"            # the _maybe_run_* decision engines
    DATA_ADAPTER = "data_adapter"                # historical/live market-data sources
    EXTERNAL_SERVICE = "external_service"        # LLM provider pool, remote APIs
    HOST_RESOURCE = "host_resource"              # CPU/RAM/disk/file descriptors


class ComponentCriticality(str, Enum):
    """How much organism function is lost when this component fails.

    Drives both the maintenance-policy cost structure and the vitality gate's severity: a VITAL
    component that is FAILING vetoes trading outright; a SUPPORTING one only tightens size.
    """

    VITAL = "vital"              # trading cannot proceed correctly without it
    SUPPORTING = "supporting"    # degrades quality/coverage but trading remains sound
    ANCILLARY = "ancillary"      # observability/comfort only


class ComponentMembership(str, Enum):
    """The self/non-self boundary (research/169 §3 — engineering equivalent of an immune registry)."""

    SELF = "self"              # a member of the organism, subject to maintenance and repair
    EXOGENOUS = "exogenous"    # declared outside the boundary: legitimately maintained by nobody here


@dataclass(frozen=True)
class RegisteredComponent:
    """One member of the organism, with everything needed to watch and maintain it."""

    component_id: str
    component_class: ComponentClass
    criticality: ComponentCriticality
    membership: ComponentMembership = ComponentMembership.SELF
    # Where this component's liveness is observable on disk (stores/artifacts); None for in-process ones.
    state_path: Path | None = None
    # How old this component's state may become before it counts as degraded. None = no staleness axis.
    maximum_staleness_hours: float | None = None
    # Components this one is maintained BY (the G_maintains edges out of this node).
    maintained_by: tuple[str, ...] = ()
    # Free-text role, surfaced on the dashboard so a human can read the organism's own self-description.
    role_description: str = ""
    # A healthy sibling this component's consumers can fall back to when it is quarantined (Rule I:
    # quarantine without a fallback would degrade the organism rather than protect it).
    fallback_component_id: str | None = None

    @property
    def is_self(self) -> bool:
        return self.membership is ComponentMembership.SELF

    @property
    def is_maintained(self) -> bool:
        """A SELF component with no declared maintainer is a closure violation by construction."""
        return bool(self.maintained_by)


def _store(component_id: str, filename: str, criticality: ComponentCriticality,
           maximum_staleness_hours: float, maintained_by: tuple[str, ...],
           role_description: str) -> RegisteredComponent:
    return RegisteredComponent(
        component_id=component_id,
        component_class=ComponentClass.PERSISTENT_STORE,
        criticality=criticality,
        state_path=ORGANISM_STATE_DIRECTORY / filename,
        maximum_staleness_hours=maximum_staleness_hours,
        maintained_by=maintained_by,
        role_description=role_description,
    )


def _artifact(component_id: str, filename: str, criticality: ComponentCriticality,
              maximum_staleness_hours: float, maintained_by: tuple[str, ...],
              role_description: str) -> RegisteredComponent:
    return RegisteredComponent(
        component_id=component_id,
        component_class=ComponentClass.PERSISTED_ARTIFACT,
        criticality=criticality,
        state_path=ORGANISM_STATE_DIRECTORY / filename,
        maximum_staleness_hours=maximum_staleness_hours,
        maintained_by=maintained_by,
        role_description=role_description,
    )


# ---------------------------------------------------------------------------------------------------
# THE ORGANISM — every component declared, with who maintains it.
#
# `maintained_by=()` on a SELF component is NOT an oversight: it is the audit target. The closure
# auditor reports each one, and the known real cases are documented in research/172 §1 (the
# win-probability model that can never retrain; the Angel One session with no expiry check).
# ---------------------------------------------------------------------------------------------------

_PERSISTENT_STORES: tuple[RegisteredComponent, ...] = (
    # STALENESS IS MEASURED IN WALL-CLOCK HOURS, BUT MARKET DATA ONLY AGES IN TRADING TIME.
    # Found by the Rule-F pass on 2026-07-27 (a Monday, pre-open): the store was 60 h old purely
    # because the market had been shut since Friday's close, which is entirely normal — yet against a
    # 24 h budget it read FAILED, and the vitality gate correctly vetoed ALL trading. Wiring that in
    # would have halted the system every Monday and every pre-open morning.
    # The budget below spans a three-day weekend so normal closures cannot trip it, while a genuinely
    # abandoned store (≥5 days) still alarms. This is an APPROXIMATION: the correct fix is to measure
    # staleness against the last NSE trading session using `paper_trading/nse_market_clock`
    # (`NseMarketClock.is_trading_day`), which is tracked in docs/BACKLOG.md.
    _store("store.market_data", "market_data.sqlite3", ComponentCriticality.VITAL, 96.0,
           ("thread.live_paper_loop",), "OHLC bars + option chains — the signal substrate"),
    _store("store.experience_memory", "experience_memory.sqlite3", ComponentCriticality.VITAL, 96.0,
           ("thread.live_paper_loop",), "episodic trade experiences — what every learner trains on"),
    _store("store.news", "news.sqlite3", ComponentCriticality.SUPPORTING, 12.0,
           ("thread.news_acquisition", "thread.exchange_filings"),
           "deduped headlines + extracted index levels"),
    _store("store.safety_incidents", "safety_incidents.sqlite3", ComponentCriticality.VITAL, 720.0,
           ("engine.incident_post_mortem",), "append-only forensic record of safety incidents"),
    _store("store.council_track_record", "council_track_record.sqlite3",
           ComponentCriticality.SUPPORTING, 168.0, ("engine.prediction_council",),
           "per-desk forecasting track record"),
    _store("store.debate_risk_observations", "debate_risk_observations.sqlite3",
           ComponentCriticality.SUPPORTING, 168.0, ("engine.debate_risk_gate",),
           "prequential observations for the debate-risk gate"),
    _store("store.replay_curriculum", "replay_curriculum.sqlite3", ComponentCriticality.SUPPORTING,
           168.0, ("engine.deficit_driven_replay_selector", "engine.curiosity"),
           "which replay sessions have been covered"),
)

_PERSISTED_ARTIFACTS: tuple[RegisteredComponent, ...] = (
    # The documented closure violation: nothing retrains this model once the file exists
    # (`load_or_train()` short-circuits to `load()` forever). maintained_by=() is the finding.
    _artifact("artifact.win_probability_model", "win_probability_model.joblib",
              ComponentCriticality.VITAL, 168.0, (),
              "trained LightGBM win-probability model — sizes real entries via Kelly"),
    _artifact("artifact.world_model_counts", "world_model_counts.json", ComponentCriticality.SUPPORTING,
              24.0, ("engine.world_model_planning",), "transition/reward counts for model-based planning"),
    _artifact("artifact.capital_allocation_state", "capital_allocation_state.json",
              ComponentCriticality.SUPPORTING, 24.0, ("engine.capital_allocation",),
              "carried allocation optimizer state"),
    _artifact("artifact.curiosity_state", "curiosity_state.json", ComponentCriticality.SUPPORTING,
              24.0, ("engine.curiosity",), "learning-progress + novelty counts"),
    _artifact("artifact.trading_control_config", "trading_control_config.json",
              ComponentCriticality.VITAL, 8760.0, ("operator.human",),
              "paper/live mode + the off-switch — maintained by the human, by design"),
    _artifact("artifact.nse_equity_master", "nse_equity_master.json", ComponentCriticality.VITAL,
              168.0, ("thread.live_paper_loop",), "tradable universe master"),
)

_BROKER_SESSIONS: tuple[RegisteredComponent, ...] = (
    RegisteredComponent(
        "session.kite", ComponentClass.BROKER_SESSION, ComponentCriticality.VITAL,
        state_path=ORGANISM_STATE_DIRECTORY / "kite_access_token.json",
        maximum_staleness_hours=24.0, maintained_by=("operator.human",),
        role_description="execution + live-data broker session (expires daily 06:00 IST)",
        fallback_component_id="session.breeze",
    ),
    RegisteredComponent(
        "session.breeze", ComponentClass.BROKER_SESSION, ComponentCriticality.SUPPORTING,
        state_path=ORGANISM_STATE_DIRECTORY / "breeze_session_token.json",
        maximum_staleness_hours=24.0, maintained_by=("operator.human",),
        role_description="ICICI Breeze session — 1-second replay fidelity",
    ),
    # No expiry check exists anywhere for this session (research/172 §1) — declared so the auditor
    # reports it rather than leaving the gap invisible.
    RegisteredComponent(
        "session.angel_one", ComponentClass.BROKER_SESSION, ComponentCriticality.SUPPORTING,
        maximum_staleness_hours=24.0, maintained_by=(),
        role_description="Angel One SmartAPI session — jwtToken hard-expires, NO validity check exists",
    ),
)

_BACKGROUND_THREADS: tuple[RegisteredComponent, ...] = (
    RegisteredComponent("thread.live_paper_loop", ComponentClass.BACKGROUND_THREAD,
                        ComponentCriticality.VITAL, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="the main writer loop — scans, decides, publishes"),
    RegisteredComponent("thread.hi_fidelity_replay_builder", ComponentClass.BACKGROUND_THREAD,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="builds the high-fidelity replay feed, then swaps it in"),
    RegisteredComponent("thread.news_acquisition", ComponentClass.BACKGROUND_THREAD,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="news acquisition ladder (curl_cffi -> Chromium)"),
    RegisteredComponent("thread.exchange_filings", ComponentClass.BACKGROUND_THREAD,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="NSE corporate-filings poller"),
    RegisteredComponent("thread.win_probability_trainer", ComponentClass.BACKGROUND_THREAD,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="trains the win-probability model (currently never re-trains)"),
)

_EXTERNAL_SERVICES: tuple[RegisteredComponent, ...] = (
    RegisteredComponent("service.llm_provider_pool", ComponentClass.EXTERNAL_SERVICE,
                        ComponentCriticality.SUPPORTING,
                        maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="swappable multi-provider LLM pool with cooldown failover"),
    RegisteredComponent("adapter.multi_broker_historical_bars", ComponentClass.DATA_ADAPTER,
                        ComponentCriticality.VITAL, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="failover historical-bar fleet across 5 brokers",
                        fallback_component_id="store.market_data"),
)

_HOST_RESOURCES: tuple[RegisteredComponent, ...] = (
    RegisteredComponent("host.process_memory", ComponentClass.HOST_RESOURCE,
                        ComponentCriticality.VITAL, maintained_by=("engine.setpoint_keeper",),
                        role_description="resident set size of the trading process"),
    RegisteredComponent("host.process_cpu", ComponentClass.HOST_RESOURCE,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.setpoint_keeper",),
                        role_description="CPU utilisation of the trading process"),
    RegisteredComponent("host.open_file_descriptors", ComponentClass.HOST_RESOURCE,
                        ComponentCriticality.SUPPORTING, maintained_by=("engine.setpoint_keeper",),
                        role_description="open file descriptors (SQLite + sockets leak here)"),
    RegisteredComponent("host.disk_free", ComponentClass.HOST_RESOURCE, ComponentCriticality.VITAL,
                        maintained_by=("engine.setpoint_keeper",),
                        role_description="free disk on the organism's state volume"),
)

# The maintainers themselves — including the homeostat, which must be maintained by something or the
# organism is not closed. It is maintained by the operator (who restarts the process) and by systemd.
_MAINTAINER_COMPONENTS: tuple[RegisteredComponent, ...] = (
    RegisteredComponent("engine.autopoiesis_homeostat", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.VITAL,
                        maintained_by=("operator.human", "platform.systemd"),
                        role_description="this engine — supervises and repairs every other component"),
    RegisteredComponent("engine.setpoint_keeper", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING,
                        maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="holds essential variables inside the viability set"),
    RegisteredComponent("engine.incident_post_mortem", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.VITAL, maintained_by=("engine.autopoiesis_homeostat",),
                        role_description="forensic post-mortem of every safety incident"),
    RegisteredComponent("engine.world_model_planning", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="model-based planner over the discretized market state"),
    RegisteredComponent("engine.capital_allocation", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="CVXPY joint capital allocator"),
    RegisteredComponent("engine.curiosity", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="learning-progress curiosity engine"),
    RegisteredComponent("engine.prediction_council", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="track-record-weighted forecasting council"),
    RegisteredComponent("engine.debate_risk_gate", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="LLM debate-as-risk-check entry gate"),
    RegisteredComponent("engine.deficit_driven_replay_selector", ComponentClass.CADENCE_ENGINE,
                        ComponentCriticality.SUPPORTING, maintained_by=("thread.live_paper_loop",),
                        role_description="deficit-driven replay curriculum"),
)

# Declared OUTSIDE the boundary. These are legitimately maintained by nobody inside the organism, so
# the closure audit must not report them — that is the whole point of an explicit boundary.
_EXOGENOUS_ENTITIES: tuple[RegisteredComponent, ...] = (
    RegisteredComponent("operator.human", ComponentClass.EXTERNAL_SERVICE, ComponentCriticality.VITAL,
                        membership=ComponentMembership.EXOGENOUS,
                        role_description="the human operator — refreshes tokens, flips the off-switch"),
    RegisteredComponent("platform.systemd", ComponentClass.EXTERNAL_SERVICE,
                        ComponentCriticality.VITAL, membership=ComponentMembership.EXOGENOUS,
                        role_description="process supervisor (Restart=always) — outside the organism"),
    RegisteredComponent("external.broker_api", ComponentClass.EXTERNAL_SERVICE,
                        ComponentCriticality.VITAL, membership=ComponentMembership.EXOGENOUS,
                        role_description="broker REST/WebSocket APIs"),
    RegisteredComponent("external.nse_exchange", ComponentClass.EXTERNAL_SERVICE,
                        ComponentCriticality.VITAL, membership=ComponentMembership.EXOGENOUS,
                        role_description="NSE — the market itself"),
)

ORGANISM_COMPONENTS: tuple[RegisteredComponent, ...] = (
    _PERSISTENT_STORES + _PERSISTED_ARTIFACTS + _BROKER_SESSIONS + _BACKGROUND_THREADS
    + _EXTERNAL_SERVICES + _HOST_RESOURCES + _MAINTAINER_COMPONENTS + _EXOGENOUS_ENTITIES
)


@dataclass(frozen=True)
class OrganismComponentRegistry:
    """The organism's model of its own membership — the boundary, made explicit and queryable."""

    components: tuple[RegisteredComponent, ...] = field(default_factory=lambda: ORGANISM_COMPONENTS)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for component in self.components:
            if component.component_id in seen:
                raise ValueError(f"duplicate component_id in registry: {component.component_id}")
            seen.add(component.component_id)
        # Every declared maintainer must itself be a registered component, or the maintains-graph would
        # contain phantom nodes and the closure audit would be meaningless.
        for component in self.components:
            for maintainer_id in component.maintained_by:
                if maintainer_id not in seen:
                    raise ValueError(
                        f"{component.component_id} declares unknown maintainer {maintainer_id!r}"
                    )

    def component_ids(self) -> tuple[str, ...]:
        return tuple(component.component_id for component in self.components)

    def find(self, component_id: str) -> RegisteredComponent | None:
        for component in self.components:
            if component.component_id == component_id:
                return component
        return None

    def members_of_class(self, component_class: ComponentClass) -> tuple[RegisteredComponent, ...]:
        """The population a hierarchical prior pools over (research/168 §5)."""
        return tuple(c for c in self.components
                     if c.component_class is component_class and c.is_self)

    def self_components(self) -> tuple[RegisteredComponent, ...]:
        return tuple(c for c in self.components if c.is_self)

    def exogenous_component_ids(self) -> frozenset[str]:
        return frozenset(c.component_id for c in self.components if not c.is_self)

    def vital_component_ids(self) -> frozenset[str]:
        return frozenset(c.component_id for c in self.self_components()
                         if c.criticality is ComponentCriticality.VITAL)

    def maintains_edges(self) -> tuple[tuple[str, str], ...]:
        """`G_maintains` edges as (maintained, maintainer) pairs — the closure auditor's substrate."""
        return tuple(
            (component.component_id, maintainer_id)
            for component in self.components
            for maintainer_id in component.maintained_by
        )

    def unmaintained_self_component_ids(self) -> tuple[str, ...]:
        """SELF components with no declared maintainer — the direct closure violations.

        This is a purely structural check (no history needed), which is why the closure branch is
        armed from day one under the Rule-Q maturity ladder.
        """
        return tuple(c.component_id for c in self.self_components() if not c.is_maintained)

    def is_recognized(self, component_id: str) -> bool:
        """Self/non-self test: is this identifier a member the organism recognises at all?"""
        return self.find(component_id) is not None

    def classify_membership(self, component_id: str) -> ComponentMembership | None:
        component = self.find(component_id)
        return component.membership if component else None


def build_default_component_registry(
    extra_components: Iterable[RegisteredComponent] = (),
) -> OrganismComponentRegistry:
    """The production registry. `extra_components` exists for the hermetic test seam (Rule J)."""
    return OrganismComponentRegistry(components=ORGANISM_COMPONENTS + tuple(extra_components))
