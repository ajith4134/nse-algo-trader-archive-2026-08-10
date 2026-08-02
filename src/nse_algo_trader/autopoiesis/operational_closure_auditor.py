"""Trunk X AUTOPOIESIS — the OPERATIONAL CLOSURE audit over the organism's `G_maintains` overlay.

**What operational closure means here.** Chemical Organization Theory (Dittrich & Speroni di Fenizio
2007; `docs/research/169` §1.5) defines a reaction network `(M, R)` and, for a subset `A ⊆ M`:

  · `A` is **CLOSED** iff no reaction triggerable from inside `A` produces a species outside `A`.
  · `A` is **SELF-MAINTAINING** iff every species consumed inside `A` is also produced inside `A`
    (the quantitative form is a strictly-positive flux `v'` with `N_A·v' ≥ 0`).
  · `A` is an **ORGANIZATION** iff it is CLOSED **and** SELF-MAINTAINING.

`research/169` §7.2 ports those three conditions onto a "maintained-by" dependency edge, which is the
form implemented here (`is_closed_component_set` / `is_self_maintaining_component_set` /
`is_organization`):

  · **CLOSED(S)** — no component in `S` declares a maintainer outside `S ∪ EXOGENOUS`. `S` does not
    secretly lean on something the audit never accounted for.
  · **SELF-MAINTAINING(S)** — every SELF component in `S` has at least one maintainer *inside* `S`.
    This is the discrete analogue of COT's positive-flux condition: a maintainer that exists and (with
    the optional `active_component_ids` filter of §7.2) is demonstrably running. EXOGENOUS members of
    `S` are exempt by construction — a declared boundary input is legitimately maintained by nobody
    inside the organism, which is the entire point of having an explicit boundary (§7.1).

**The two orientations of the graph, and why both exist.** `research/169` §2.1 fixes the substrate as
`G_maintains` with edge `u -> v` meaning "u is maintained by v" — the *dependency* orientation, and the
orientation `OrganismComponentRegistry.maintains_edges()` emits (maintained, maintainer). §2.3 and §2.6
then speak of "in-degree 0" and "condensation source SCC" for an unmaintained node, and of PageRank on
"the reversed edges"; both of those statements are literally true only in the *maintenance-flow*
orientation `v -> u` ("v maintains u"). This module therefore builds both views explicitly and uses each
where it is correct, rather than transcribing a direction slip into wrong answers:

  · `build_component_maintains_graph()`  — `u -> v` = "u is maintained by v" (§2.1 as declared).
  · `build_maintenance_flow_graph()`     — its reverse, `v -> u` = "v maintains u". In THIS view
    in-degree 0 really does mean "nobody maintains it", and a condensation source SCC really is a
    cluster hanging off nothing (§2.2/§2.3).
  · Criticality PageRank runs on the *maintains* (dependency) graph — i.e. on the reverse of the flow
    graph, which is exactly §2.6's "reverse-PageRank": mass accumulates on the components many others
    lean on, so a high score means "its failure propagates to many dependents".

**The audit** (§7.3): SCCs + condensation (`networkx.strongly_connected_components`,
`networkx.condensation`) → non-trivial SCCs are the candidate COT organizations (mutually-maintaining
clusters); every non-EXOGENOUS node that is unmaintained, or sits in an acyclic condensation source SCC,
is a **closure violation**; `networkx.articulation_points` over the undirected projection plus
reverse-PageRank × betweenness rank the structurally critical components (§2.5/§2.6).

Violations are reported loudly and never auto-remediated (§7.4): synthesising a fake maintainer would
defeat the audit. The two real violations this reproduces against the production registry are documented
in `docs/research/172` §1 — the win-probability model that `load_or_train()` can never retrain (VITAL →
CRITICAL) and the Angel One session with no expiry check anywhere (supporting → WARNING).

This audit is structural only: it needs no history, which is why `research/172` §4's maturity ladder arms
it immediately.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import networkx as nx

from nse_algo_trader.autopoiesis.component_registry import (
    ComponentMembership,
    OrganismComponentRegistry,
    build_default_component_registry,
)

# Severity vocabulary — a closure violation on a VITAL component is CRITICAL, anything else WARNING.
CRITICAL_VIOLATION_SEVERITY = "critical"
WARNING_VIOLATION_SEVERITY = "warning"

# Criticality ranking knobs (research/169 §2.6: "articulation-point flag first, then
# reverse_pagerank × betweenness_centrality ... so the ranking is a total order").
ARTICULATION_POINT_CRITICALITY_OFFSET = 1.0   # lifts every articulation point above every non-AP node
PAGERANK_DAMPING_FACTOR = 0.85
PAGERANK_MAXIMUM_ITERATIONS = 500
PAGERANK_CONVERGENCE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ClosureViolation:
    """One non-EXOGENOUS component that nothing inside the boundary maintains (research/169 §2.3)."""

    component_id: str
    severity: str            # "critical" | "warning"
    reason: str              # human-readable, names the structural cause
    criticality: str         # the registry's declared ComponentCriticality value


@dataclass(frozen=True)
class OperationalClosureReport:
    """The whole audit: is the organism operationally closed, and where is it structurally fragile."""

    is_closed: bool
    violations: tuple[ClosureViolation, ...]
    organizations: tuple[tuple[str, ...], ...]        # non-trivial SCCs = mutually-maintaining clusters
    critical_articulation_points: tuple[str, ...]
    criticality_ranking: tuple[tuple[str, float], ...]  # (component_id, score) descending
    component_count: int
    maintenance_edge_count: int

    @property
    def critical_violations(self) -> tuple[ClosureViolation, ...]:
        """The subset that vetoes rather than merely warns — violations on VITAL components."""
        return tuple(v for v in self.violations if v.severity == CRITICAL_VIOLATION_SEVERITY)

    def violation_for(self, component_id: str) -> ClosureViolation | None:
        for violation in self.violations:
            if violation.component_id == component_id:
                return violation
        return None

    def describe(self) -> str:
        """One human-readable block for the dashboard's Operational Closure panel (research/169 §7.4)."""
        headline = (
            f"operational closure: {'CLOSED' if self.is_closed else 'OPEN'} — "
            f"{len(self.violations)} violation(s) over {self.component_count} components / "
            f"{self.maintenance_edge_count} maintenance edges; "
            f"{len(self.organizations)} mutually-maintaining organization(s)"
        )
        lines = [headline]
        for violation in self.violations:
            lines.append(f"  [{violation.severity.upper()}] {violation.component_id}: {violation.reason}")
        if self.critical_articulation_points:
            lines.append(f"  single points of failure: {', '.join(self.critical_articulation_points)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class OperationalClosureAuditor:
    """Audits whether every SELF component is maintained by something else inside the boundary.

    Built directly on `OrganismComponentRegistry` (`maintains_edges`, `exogenous_component_ids`,
    `vital_component_ids`, `self_components`) — the registry owns membership and the curated overlay;
    this module owns only the graph theory over it.
    """

    registry: OrganismComponentRegistry = field(default_factory=build_default_component_registry)

    # -- graph construction -------------------------------------------------------------------------

    def build_component_maintains_graph(self) -> nx.DiGraph:
        """`G_maintains` in the declared §2.1 orientation: edge `u -> v` = "u is maintained by v".

        Every registered component is added as a node first, so isolated components (no maintainer and
        maintaining nobody — e.g. `external.nse_exchange`) are audited rather than silently absent.
        """
        maintains_graph: nx.DiGraph = nx.DiGraph()
        for component in self.registry.components:
            maintains_graph.add_node(
                component.component_id,
                membership=component.membership.value,
                criticality=component.criticality.value,
                component_class=component.component_class.value,
            )
        for maintained_id, maintainer_id in self.registry.maintains_edges():
            maintains_graph.add_edge(maintained_id, maintainer_id)
        return maintains_graph

    def build_maintenance_flow_graph(self) -> nx.DiGraph:
        """The reverse view, edge `v -> u` = "v maintains u" — the orientation in which §2.3's
        "in-degree 0" and "condensation source SCC" literally mean "nothing maintains it"."""
        return self._flow_view_of(self.build_component_maintains_graph())

    # -- Chemical Organization Theory predicates (research/169 §1.5 → §7.2) -------------------------

    def is_closed_component_set(self, component_ids: Iterable[str]) -> bool:
        """COT CLOSED(S): no member of `S` declares a maintainer outside `S ∪ EXOGENOUS`.

        The empty set is vacuously closed (as in COT, where ∅ is a trivial organization). Unknown
        component ids raise — a typo must never quietly weaken the predicate (Rule O.3).
        """
        candidate_ids = self._validated_component_id_set(component_ids)
        exogenous_ids = self.registry.exogenous_component_ids()
        for component_id in candidate_ids:
            component = self.registry.find(component_id)
            if component is None:  # pragma: no cover - guaranteed by _validated_component_id_set
                raise ValueError(f"unregistered component in candidate set: {component_id!r}")
            for maintainer_id in component.maintained_by:
                if maintainer_id not in candidate_ids and maintainer_id not in exogenous_ids:
                    return False
        return True

    def is_self_maintaining_component_set(
        self,
        component_ids: Iterable[str],
        active_component_ids: Iterable[str] | None = None,
    ) -> bool:
        """COT SELF-MAINTAINING(S): every SELF member of `S` has a maintainer *inside* `S`.

        The discrete analogue of COT's strictly-positive-flux condition `N_A·v' ≥ 0` (§1.5): production
        must actually come from within the set. `active_component_ids`, when supplied, applies §7.2's
        refinement — only maintainers that are demonstrably running count as flux; when omitted the
        check is purely structural (which is what makes the audit history-free, research/172 §4).

        EXOGENOUS members are exempt: a declared boundary input is legitimately maintained by nobody
        inside the organism (§7.1). The empty set is vacuously self-maintaining.
        """
        candidate_ids = self._validated_component_id_set(component_ids)
        active_ids = None if active_component_ids is None else frozenset(active_component_ids)
        for component_id in candidate_ids:
            component = self.registry.find(component_id)
            if component is None:  # pragma: no cover - guaranteed by _validated_component_id_set
                raise ValueError(f"unregistered component in candidate set: {component_id!r}")
            if component.membership is ComponentMembership.EXOGENOUS:
                continue
            maintainers_inside = [m for m in component.maintained_by if m in candidate_ids]
            if active_ids is not None:
                maintainers_inside = [m for m in maintainers_inside if m in active_ids]
            if not maintainers_inside:
                return False
        return True

    def is_organization(
        self,
        component_ids: Iterable[str],
        active_component_ids: Iterable[str] | None = None,
    ) -> bool:
        """COT ORGANIZATION(S) = CLOSED(S) ∧ SELF-MAINTAINING(S) (research/169 §1.5/§7.2)."""
        return self.is_closed_component_set(component_ids) and self.is_self_maintaining_component_set(
            component_ids, active_component_ids=active_component_ids
        )

    # -- SCC / condensation structure (research/169 §2.2) -------------------------------------------

    def mutually_maintaining_organizations(self) -> tuple[tuple[str, ...], ...]:
        """Non-trivial SCCs — size ≥ 2, or a single node with a self-loop (§2.2).

        These are the graph-theoretic image of a COT organization: a cluster whose members maintain each
        other, so the cluster does not hang off anything outside itself. SCCs are orientation-invariant,
        so the maintains and flow views give identical answers.
        """
        return self._non_trivial_strongly_connected_components(self.build_component_maintains_graph())

    # -- the audit (research/169 §2.3 / §7.3) -------------------------------------------------------

    def closure_violations(self) -> tuple[ClosureViolation, ...]:
        """Every non-EXOGENOUS component nothing inside the boundary maintains."""
        maintains_graph = self.build_component_maintains_graph()
        return self._closure_violations_over(maintains_graph, self._flow_view_of(maintains_graph))

    def single_point_of_failure_component_ids(self) -> tuple[str, ...]:
        """Articulation points of the UNDIRECTED projection — maintenance chains with no redundancy.

        Even inside a technically-closed SCC an articulation point marks a fragile link: one failure
        breaks the loop (research/169 §2.5). Reported as a secondary fragility signal, never folded into
        the boolean closure verdict.
        """
        return self._articulation_point_ids(self.build_component_maintains_graph())

    def structural_criticality_ranking(self) -> tuple[tuple[str, float], ...]:
        """Components ordered by how much structure collapses with them (research/169 §2.6)."""
        maintains_graph = self.build_component_maintains_graph()
        return self._structural_criticality_ranking(
            maintains_graph, frozenset(self._articulation_point_ids(maintains_graph))
        )

    def components_downstream_of_violations(self) -> tuple[str, ...]:
        """Components whose maintenance chain transitively hangs off a violating node (§7.3 step 3).

        Deliberately NOT folded into `violations`: those stay root-cause-only so the backlog entry names
        the component to actually fix. This is the blast-radius view of the same finding.
        """
        maintains_graph = self.build_component_maintains_graph()
        flow_graph = self._flow_view_of(maintains_graph)
        violating_ids = {
            v.component_id for v in self._closure_violations_over(maintains_graph, flow_graph)
        }
        affected: set[str] = set()
        for violating_id in violating_ids:
            affected |= nx.descendants(flow_graph, violating_id)
        return tuple(sorted(affected - violating_ids))

    def audit(self) -> OperationalClosureReport:
        """The whole §7.3 algorithm in one pass over one built graph."""
        maintains_graph = self.build_component_maintains_graph()
        flow_graph = self._flow_view_of(maintains_graph)
        violations = self._closure_violations_over(maintains_graph, flow_graph)
        articulation_point_ids = self._articulation_point_ids(maintains_graph)
        return OperationalClosureReport(
            is_closed=not violations,
            violations=violations,
            organizations=self._non_trivial_strongly_connected_components(maintains_graph),
            critical_articulation_points=articulation_point_ids,
            criticality_ranking=self._structural_criticality_ranking(
                maintains_graph, frozenset(articulation_point_ids)
            ),
            component_count=maintains_graph.number_of_nodes(),
            maintenance_edge_count=maintains_graph.number_of_edges(),
        )

    # -- internals ----------------------------------------------------------------------------------

    def _validated_component_id_set(self, component_ids: Iterable[str]) -> frozenset[str]:
        candidate_ids = frozenset(component_ids)
        unknown_ids = sorted(cid for cid in candidate_ids if not self.registry.is_recognized(cid))
        if unknown_ids:
            raise ValueError(
                f"candidate set contains component ids the registry does not recognise: {unknown_ids}"
            )
        return candidate_ids

    @staticmethod
    def _flow_view_of(maintains_graph: nx.DiGraph) -> nx.DiGraph:
        """`v -> u` = "v maintains u"; in-degree 0 here means "nothing maintains it" (§2.3)."""
        flow_graph: nx.DiGraph = maintains_graph.reverse(copy=True)
        return flow_graph

    @staticmethod
    def _non_trivial_strongly_connected_components(
        maintains_graph: nx.DiGraph,
    ) -> tuple[tuple[str, ...], ...]:
        clusters: list[tuple[str, ...]] = []
        for component_set in nx.strongly_connected_components(maintains_graph):
            members = tuple(sorted(str(member) for member in component_set))
            if len(members) >= 2 or maintains_graph.has_edge(members[0], members[0]):
                clusters.append(members)
        # Largest cluster first, then alphabetically — a stable order for the dashboard panel.
        return tuple(sorted(clusters, key=lambda members: (-len(members), members)))

    @staticmethod
    def _acyclic_condensation_source_member_ids(flow_graph: nx.DiGraph) -> frozenset[str]:
        """Members of condensation-DAG source SCCs that are not themselves cyclic (§2.3 clause b2).

        `networkx.condensation` drops self-loops, so a singleton SCC with a self-loop looks like a DAG
        source; it is cyclic (it maintains itself) and therefore excluded here, exactly as §2.2 requires.
        """
        if flow_graph.number_of_nodes() == 0:
            return frozenset()
        condensation_dag = nx.condensation(flow_graph)
        source_members: set[str] = set()
        for scc_index, scc_in_degree in condensation_dag.in_degree():
            if scc_in_degree != 0:
                continue
            members = tuple(str(m) for m in condensation_dag.nodes[scc_index]["members"])
            is_cyclic_scc = len(members) >= 2 or flow_graph.has_edge(members[0], members[0])
            if not is_cyclic_scc:
                source_members.update(members)
        return frozenset(source_members)

    def _closure_violations_over(
        self, maintains_graph: nx.DiGraph, flow_graph: nx.DiGraph
    ) -> tuple[ClosureViolation, ...]:
        """§2.3 verbatim: a violation is any node that is (a) not EXOGENOUS and (b) has in-degree 0 in
        the maintenance-flow view OR belongs to an acyclic condensation source SCC.

        On a registry-validated graph (every declared maintainer is itself registered) the two limbs of
        (b) coincide — a node with an inbound maintenance edge either sits in a cyclic SCC or has a
        non-source SCC. Both are still computed, so the definition also holds on hand-built graphs.
        """
        exogenous_ids = self.registry.exogenous_component_ids()
        vital_ids = self.registry.vital_component_ids()
        acyclic_source_ids = self._acyclic_condensation_source_member_ids(flow_graph)

        violations: list[ClosureViolation] = []
        for node_id in sorted(str(node) for node in maintains_graph.nodes):
            if node_id in exogenous_ids:
                continue  # a declared boundary input is legitimately maintained by nobody (§7.1)
            has_no_maintainer = flow_graph.in_degree(node_id) == 0
            in_acyclic_source_scc = node_id in acyclic_source_ids
            if not (has_no_maintainer or in_acyclic_source_scc):
                continue
            component = self.registry.find(node_id)
            declared_criticality = component.criticality.value if component else "unknown"
            if has_no_maintainer:
                reason = (
                    f"no component inside the boundary declares itself the maintainer of "
                    f"{node_id!r} (in-degree 0 in the maintenance-flow graph): nothing keeps it "
                    f"current, correct or alive"
                )
            else:
                scc_members = sorted(
                    str(member)
                    for member in next(
                        scc for scc in nx.strongly_connected_components(flow_graph) if node_id in scc
                    )
                )
                reason = (
                    f"{node_id!r} sits in the acyclic condensation source SCC {scc_members} — the whole "
                    f"cluster hangs off nothing inside the boundary"
                )
            violations.append(
                ClosureViolation(
                    component_id=node_id,
                    severity=(
                        CRITICAL_VIOLATION_SEVERITY
                        if node_id in vital_ids
                        else WARNING_VIOLATION_SEVERITY
                    ),
                    reason=reason,
                    criticality=declared_criticality,
                )
            )
        # CRITICAL first, then alphabetically — the dashboard reads top-down.
        return tuple(
            sorted(violations, key=lambda v: (v.severity != CRITICAL_VIOLATION_SEVERITY, v.component_id))
        )

    @staticmethod
    def _articulation_point_ids(maintains_graph: nx.DiGraph) -> tuple[str, ...]:
        if maintains_graph.number_of_nodes() < 3:
            return ()  # fewer than 3 nodes cannot be disconnected by removing one
        undirected_projection = maintains_graph.to_undirected(as_view=False)
        undirected_projection.remove_edges_from(nx.selfloop_edges(undirected_projection))
        return tuple(sorted({str(node) for node in nx.articulation_points(undirected_projection)}))

    @staticmethod
    def _reverse_pagerank_scores(maintains_graph: nx.DiGraph) -> dict[str, float]:
        """§2.6's reverse-PageRank: PageRank over the maintains (dependency) orientation, i.e. the
        reverse of the maintenance-flow graph — mass accumulates on components many others lean on."""
        if maintains_graph.number_of_nodes() == 0:
            return {}
        try:
            scores = nx.pagerank(
                maintains_graph,
                alpha=PAGERANK_DAMPING_FACTOR,
                max_iter=PAGERANK_MAXIMUM_ITERATIONS,
                tol=PAGERANK_CONVERGENCE_TOLERANCE,
            )
        except nx.PowerIterationFailedConvergence as failure:  # never swallowed (Rule O.3)
            raise RuntimeError(
                "reverse-PageRank over G_maintains failed to converge in "
                f"{PAGERANK_MAXIMUM_ITERATIONS} iterations; the maintains graph is degenerate "
                "and its criticality ranking cannot be trusted"
            ) from failure
        return {str(node): float(score) for node, score in scores.items()}

    def _structural_criticality_ranking(
        self, maintains_graph: nx.DiGraph, articulation_point_ids: frozenset[str]
    ) -> tuple[tuple[str, float], ...]:
        """§2.6: articulation-point flag first, then reverse_pagerank × betweenness_centrality.

        "Flag first" is implemented as a +1.0 offset over a [0,1]-normalised
        `pagerank × (1 + betweenness)` base, so every articulation point outranks every non-articulation
        point while the whole thing stays a single-float total order usable by the dashboard.
        """
        if maintains_graph.number_of_nodes() == 0:
            return ()
        pagerank_scores = self._reverse_pagerank_scores(maintains_graph)
        betweenness_scores = {
            str(node): float(score)
            for node, score in nx.betweenness_centrality(maintains_graph).items()
        }
        base_scores = {
            node_id: pagerank_scores.get(node_id, 0.0)
            * (1.0 + betweenness_scores.get(node_id, 0.0))
            for node_id in (str(node) for node in maintains_graph.nodes)
        }
        largest_base_score = max(base_scores.values(), default=0.0)
        ranked = [
            (
                node_id,
                (base / largest_base_score if largest_base_score > 0.0 else 0.0)
                + (ARTICULATION_POINT_CRITICALITY_OFFSET if node_id in articulation_point_ids else 0.0),
            )
            for node_id, base in base_scores.items()
        ]
        return tuple(sorted(ranked, key=lambda scored: (-scored[1], scored[0])))


def audit_operational_closure(
    registry: OrganismComponentRegistry | None = None,
) -> OperationalClosureReport:
    """Audit the production organism (or an injected registry — the Rule-J hermetic seam)."""
    return OperationalClosureAuditor(
        registry=registry if registry is not None else build_default_component_registry()
    ).audit()
