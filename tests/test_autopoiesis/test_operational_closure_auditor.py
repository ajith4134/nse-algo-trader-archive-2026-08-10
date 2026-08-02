"""Tests for the operational-closure auditor (research/169 §1.5/§2/§7, research/172 §3/§5).

Three layers:

  1. **Real-registry (Rule F)** — the audit runs against the PRODUCTION organism registry and must
     reproduce the two documented closure violations (research/172 §1): the win-probability model that
     `load_or_train()` can never retrain (VITAL → CRITICAL) and the Angel One session with no expiry
     check (supporting → WARNING) — and must report none of the four declared EXOGENOUS entities.
  2. **Synthetic structure** — hand-built registries exercising each clause of the §2.3 violation
     definition, the COT predicates of §1.5/§7.2 independently, and §2.5 articulation points.
  3. **Adversarial / degenerate (Rule O.4)** — empty graph, single node, self-loop-only node, fully
     disconnected components, and a maintenance cycle that runs through an EXOGENOUS entity.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    ComponentMembership,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.operational_closure_auditor import (
    CRITICAL_VIOLATION_SEVERITY,
    WARNING_VIOLATION_SEVERITY,
    OperationalClosureAuditor,
    audit_operational_closure,
)

# The two violations research/172 §1 documents in the real organism, with their required severities.
KNOWN_REAL_CLOSURE_VIOLATIONS = {
    "artifact.win_probability_model": CRITICAL_VIOLATION_SEVERITY,
    "session.angel_one": WARNING_VIOLATION_SEVERITY,
}


def make_component(
    component_id: str,
    maintained_by: tuple[str, ...] = (),
    criticality: ComponentCriticality = ComponentCriticality.SUPPORTING,
    membership: ComponentMembership = ComponentMembership.SELF,
) -> RegisteredComponent:
    """A minimal synthetic component — only membership, criticality and the maintains edges matter."""
    return RegisteredComponent(
        component_id=component_id,
        component_class=ComponentClass.CADENCE_ENGINE,
        criticality=criticality,
        membership=membership,
        maintained_by=maintained_by,
        role_description=f"synthetic test component {component_id}",
    )


def make_auditor(*components: RegisteredComponent) -> OperationalClosureAuditor:
    return OperationalClosureAuditor(registry=OrganismComponentRegistry(components=components))


def make_three_cycle_auditor(
    extra: tuple[RegisteredComponent, ...] = (),
) -> OperationalClosureAuditor:
    """`a` maintained by `b` maintained by `c` maintained by `a` — a fully closed organization."""
    return make_auditor(
        make_component("a", maintained_by=("b",)),
        make_component("b", maintained_by=("c",)),
        make_component("c", maintained_by=("a",)),
        *extra,
    )


# ---------------------------------------------------------------------------------------------------
# 1. Real registry (Rule F) — the production organism, audited for real.
# ---------------------------------------------------------------------------------------------------


def test_real_organism_audit_reproduces_the_two_documented_closure_violations() -> None:
    report = audit_operational_closure()

    assert report.is_closed is False
    reported = {violation.component_id: violation.severity for violation in report.violations}
    assert reported == KNOWN_REAL_CLOSURE_VIOLATIONS


def test_real_organism_violation_severities_follow_declared_criticality() -> None:
    report = audit_operational_closure()

    win_probability_model = report.violation_for("artifact.win_probability_model")
    angel_one_session = report.violation_for("session.angel_one")
    assert win_probability_model is not None
    assert angel_one_session is not None
    assert win_probability_model.severity == CRITICAL_VIOLATION_SEVERITY
    assert win_probability_model.criticality == ComponentCriticality.VITAL.value
    assert angel_one_session.severity == WARNING_VIOLATION_SEVERITY
    assert angel_one_session.criticality == ComponentCriticality.SUPPORTING.value
    # CRITICAL sorts ahead of WARNING so the dashboard panel reads worst-first.
    assert report.violations[0].component_id == "artifact.win_probability_model"
    assert report.critical_violations == (win_probability_model,)


def test_real_organism_audit_never_reports_a_declared_exogenous_entity() -> None:
    registry = build_default_component_registry()
    report = OperationalClosureAuditor(registry=registry).audit()

    exogenous_ids = registry.exogenous_component_ids()
    assert exogenous_ids == {
        "operator.human",
        "platform.systemd",
        "external.broker_api",
        "external.nse_exchange",
    }
    assert not {v.component_id for v in report.violations} & exogenous_ids


def test_real_organism_audit_agrees_with_the_registrys_own_unmaintained_query() -> None:
    """The auditor's graph answer must equal the registry's direct structural answer."""
    registry = build_default_component_registry()
    report = OperationalClosureAuditor(registry=registry).audit()

    assert {v.component_id for v in report.violations} == set(
        registry.unmaintained_self_component_ids()
    )
    assert report.component_count == len(registry.components)
    assert report.maintenance_edge_count == len(registry.maintains_edges())


def test_real_organism_criticality_ranking_puts_the_homeostat_first() -> None:
    report = audit_operational_closure()

    ranked_ids = [component_id for component_id, _ in report.criticality_ranking]
    assert len(ranked_ids) == report.component_count
    assert ranked_ids[0] == "engine.autopoiesis_homeostat"
    # The supervisor and the main writer loop are the real single points of failure.
    assert "engine.autopoiesis_homeostat" in report.critical_articulation_points
    assert "thread.live_paper_loop" in report.critical_articulation_points
    scores = [score for _, score in report.criticality_ranking]
    assert scores == sorted(scores, reverse=True)


def test_real_organism_has_no_mutually_maintaining_cycle_yet() -> None:
    """A real finding, not an accident: every maintenance chain terminates on the human/systemd."""
    report = audit_operational_closure()

    assert report.organizations == ()
    assert "OPEN" in report.describe()
    assert "artifact.win_probability_model" in report.describe()


# ---------------------------------------------------------------------------------------------------
# 2. Synthetic structure — the §2.3 violation clauses and the §2.5 fragility signal.
# ---------------------------------------------------------------------------------------------------


def test_fully_closed_three_cycle_is_closed_with_one_organization_and_no_violations() -> None:
    report = make_three_cycle_auditor().audit()

    assert report.is_closed is True
    assert report.violations == ()
    assert report.organizations == (("a", "b", "c"),)
    assert report.component_count == 3
    assert report.maintenance_edge_count == 3


def test_adding_an_unmaintained_node_breaks_closure_and_reports_exactly_that_node() -> None:
    report = make_three_cycle_auditor(extra=(make_component("orphan"),)).audit()

    assert report.is_closed is False
    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation.component_id == "orphan"
    assert violation.severity == WARNING_VIOLATION_SEVERITY
    assert "no component inside the boundary declares itself the maintainer" in violation.reason
    # The closed cycle is untouched by the new orphan.
    assert report.organizations == (("a", "b", "c"),)


def test_unmaintained_vital_component_is_critical_while_supporting_is_only_a_warning() -> None:
    auditor = make_auditor(
        make_component("vital_orphan", criticality=ComponentCriticality.VITAL),
        make_component("supporting_orphan", criticality=ComponentCriticality.SUPPORTING),
        make_component("ancillary_orphan", criticality=ComponentCriticality.ANCILLARY),
    )

    severities = {v.component_id: v.severity for v in auditor.audit().violations}
    assert severities == {
        "vital_orphan": CRITICAL_VIOLATION_SEVERITY,
        "supporting_orphan": WARNING_VIOLATION_SEVERITY,
        "ancillary_orphan": WARNING_VIOLATION_SEVERITY,
    }


def test_component_maintained_only_by_an_exogenous_entity_is_not_a_violation() -> None:
    auditor = make_auditor(
        make_component("operator.human", membership=ComponentMembership.EXOGENOUS),
        make_component("session.broker", maintained_by=("operator.human",)),
    )

    report = auditor.audit()
    assert report.is_closed is True
    assert report.violations == ()


def test_exogenous_entity_maintained_by_nobody_is_itself_never_reported() -> None:
    auditor = make_auditor(
        make_component("external.nse", membership=ComponentMembership.EXOGENOUS),
        make_component("adapter", maintained_by=("external.nse",)),
    )

    assert auditor.audit().violations == ()


def test_violation_blast_radius_names_the_components_hanging_off_the_violating_root() -> None:
    auditor = make_auditor(
        make_component("root"),                              # nothing maintains it -> the violation
        make_component("child", maintained_by=("root",)),
        make_component("grandchild", maintained_by=("child",)),
    )

    report = auditor.audit()
    assert {v.component_id for v in report.violations} == {"root"}
    assert auditor.components_downstream_of_violations() == ("child", "grandchild")


def test_barbell_graph_identifies_the_bridge_node_as_a_single_point_of_failure() -> None:
    """Two mutually-maintaining triangles joined through one node (research/169 §2.5)."""
    auditor = make_auditor(
        make_component("a1", maintained_by=("a2",)),
        make_component("a2", maintained_by=("a3",)),
        make_component("a3", maintained_by=("a1",)),
        make_component("bridge", maintained_by=("a1",)),
        make_component("b1", maintained_by=("bridge", "b2")),
        make_component("b2", maintained_by=("b3",)),
        make_component("b3", maintained_by=("b1",)),
    )

    report = auditor.audit()
    assert "bridge" in report.critical_articulation_points
    # a1 and b1 are the two ends the bridge attaches to; the interior cycle members are redundant.
    assert set(report.critical_articulation_points) == {"a1", "bridge", "b1"}
    assert "a2" not in report.critical_articulation_points
    assert report.organizations == (("a1", "a2", "a3"), ("b1", "b2", "b3"))
    assert report.violations == ()
    # "Articulation-point flag first" — every articulation point outranks every other component.
    ranking = dict(report.criticality_ranking)
    assert min(ranking[node] for node in report.critical_articulation_points) >= 1.0
    assert max(
        score for node, score in ranking.items() if node not in report.critical_articulation_points
    ) < 1.0


# ---------------------------------------------------------------------------------------------------
# 2b. Chemical Organization Theory predicates, tested independently (research/169 §1.5 / §7.2).
# ---------------------------------------------------------------------------------------------------


def test_closed_predicate_holds_only_when_every_maintainer_is_inside_the_set() -> None:
    auditor = make_three_cycle_auditor()

    assert auditor.is_closed_component_set({"a", "b", "c"}) is True
    assert auditor.is_closed_component_set({"a", "b"}) is False   # b is maintained by c, outside
    assert auditor.is_closed_component_set({"a"}) is False


def test_closed_predicate_treats_an_exogenous_maintainer_as_inside_the_boundary() -> None:
    auditor = make_auditor(
        make_component("operator.human", membership=ComponentMembership.EXOGENOUS),
        make_component("session.broker", maintained_by=("operator.human",)),
    )

    # CLOSED(S) allows maintainers in S ∪ EXOGENOUS (research/169 §7.2).
    assert auditor.is_closed_component_set({"session.broker"}) is True
    # ...but S is not SELF-MAINTAINING until the maintainer is actually a member.
    assert auditor.is_self_maintaining_component_set({"session.broker"}) is False
    assert auditor.is_organization({"session.broker"}) is False
    assert auditor.is_organization({"session.broker", "operator.human"}) is True


def test_self_maintaining_predicate_requires_a_maintainer_inside_the_set() -> None:
    auditor = make_three_cycle_auditor()

    assert auditor.is_self_maintaining_component_set({"a", "b", "c"}) is True
    # a is maintained by b (inside), but b is maintained only by c (outside) — the set leaks.
    assert auditor.is_self_maintaining_component_set({"a", "b"}) is False
    assert auditor.is_self_maintaining_component_set({"a"}) is False
    assert auditor.is_self_maintaining_component_set({"a", "c"}) is False  # neither maintains the other


def test_self_maintaining_predicate_honours_the_active_maintainer_refinement() -> None:
    """§7.2's discrete flux condition: a maintainer that is not running produces nothing."""
    auditor = make_three_cycle_auditor()

    assert auditor.is_self_maintaining_component_set(
        {"a", "b", "c"}, active_component_ids={"a", "b", "c"}
    ) is True
    assert auditor.is_self_maintaining_component_set(
        {"a", "b", "c"}, active_component_ids={"a", "b"}
    ) is False   # c is dead, so b has no live maintainer
    assert auditor.is_self_maintaining_component_set({"a", "b", "c"}, active_component_ids=set()) is False


def test_organization_is_exactly_closed_and_self_maintaining() -> None:
    auditor = make_three_cycle_auditor()

    assert auditor.is_organization({"a", "b", "c"}) is True
    assert auditor.is_organization({"a", "b"}) is False        # self-maintaining but not closed
    assert auditor.is_organization({"a"}) is False


def test_empty_candidate_set_is_the_trivial_organization() -> None:
    auditor = make_three_cycle_auditor()

    assert auditor.is_closed_component_set(set()) is True
    assert auditor.is_self_maintaining_component_set(set()) is True
    assert auditor.is_organization(set()) is True


def test_predicates_reject_unregistered_component_ids_instead_of_silently_ignoring_them() -> None:
    auditor = make_three_cycle_auditor()

    with pytest.raises(ValueError, match="does not recognise"):
        auditor.is_closed_component_set({"a", "ghost"})
    with pytest.raises(ValueError, match="does not recognise"):
        auditor.is_self_maintaining_component_set({"ghost"})


# ---------------------------------------------------------------------------------------------------
# 3. Adversarial / degenerate inputs (Rule O.4).
# ---------------------------------------------------------------------------------------------------


def test_empty_registry_audits_to_a_vacuously_closed_empty_report() -> None:
    report = make_auditor().audit()

    assert report.is_closed is True
    assert report.violations == ()
    assert report.organizations == ()
    assert report.critical_articulation_points == ()
    assert report.criticality_ranking == ()
    assert report.component_count == 0
    assert report.maintenance_edge_count == 0


def test_single_unmaintained_self_node_is_the_minimal_violation() -> None:
    report = make_auditor(make_component("lonely", criticality=ComponentCriticality.VITAL)).audit()

    assert report.is_closed is False
    assert len(report.violations) == 1
    assert report.violations[0].severity == CRITICAL_VIOLATION_SEVERITY
    assert report.critical_articulation_points == ()
    # The ranking is normalised against the most critical component, so a lone node scores 1.0.
    assert report.criticality_ranking == (("lonely", 1.0),)


def test_single_exogenous_node_registry_is_closed() -> None:
    report = make_auditor(
        make_component("operator.human", membership=ComponentMembership.EXOGENOUS)
    ).audit()

    assert report.is_closed is True
    assert report.violations == ()


def test_self_loop_only_node_is_a_degenerate_organization_not_a_violation() -> None:
    """A node that maintains itself is a size-1 non-trivial SCC (research/169 §2.2) — cyclic, so the
    condensation-source clause must not fire even though the condensation drops the self-loop."""
    report = make_auditor(make_component("self_maintainer", maintained_by=("self_maintainer",))).audit()

    assert report.is_closed is True
    assert report.violations == ()
    assert report.organizations == (("self_maintainer",),)
    assert report.maintenance_edge_count == 1


def test_fully_disconnected_registry_reports_every_self_component() -> None:
    report = make_auditor(
        make_component("island_a"),
        make_component("island_b", criticality=ComponentCriticality.VITAL),
        make_component("island_c", membership=ComponentMembership.EXOGENOUS),
    ).audit()

    assert {v.component_id for v in report.violations} == {"island_a", "island_b"}
    assert report.organizations == ()
    assert report.critical_articulation_points == ()
    # With no edges at all, PageRank is uniform and betweenness zero — the ranking is still total.
    assert len(report.criticality_ranking) == 3


def test_cycle_running_through_an_exogenous_entity_is_an_organization_with_no_violation() -> None:
    report = make_auditor(
        make_component("platform.systemd", maintained_by=("engine.core",),
                       membership=ComponentMembership.EXOGENOUS),
        make_component("engine.core", maintained_by=("platform.systemd",),
                       criticality=ComponentCriticality.VITAL),
    ).audit()

    assert report.is_closed is True
    assert report.violations == ()
    assert report.organizations == (("engine.core", "platform.systemd"),)


def test_long_acyclic_maintenance_chain_is_closed_once_it_terminates_on_an_exogenous_root() -> None:
    """The real organism's shape: chains, not cycles — legal only because they end on the boundary."""
    auditor = make_auditor(
        make_component("operator.human", membership=ComponentMembership.EXOGENOUS),
        make_component("supervisor", maintained_by=("operator.human",)),
        make_component("worker", maintained_by=("supervisor",)),
        make_component("store", maintained_by=("worker",), criticality=ComponentCriticality.VITAL),
    )

    report = auditor.audit()
    assert report.is_closed is True
    assert report.organizations == ()
    assert auditor.is_self_maintaining_component_set({"supervisor", "worker", "store"}) is False
    assert auditor.is_organization({"operator.human", "supervisor", "worker", "store"}) is True


def test_graph_orientation_helpers_are_exact_reverses_of_each_other() -> None:
    auditor = make_three_cycle_auditor()

    maintains_graph = auditor.build_component_maintains_graph()
    flow_graph = auditor.build_maintenance_flow_graph()
    assert maintains_graph.has_edge("a", "b")        # "a is maintained by b"
    assert flow_graph.has_edge("b", "a")             # "b maintains a"
    assert not flow_graph.has_edge("a", "b")
    assert set(maintains_graph.nodes) == set(flow_graph.nodes)
    assert maintains_graph.number_of_edges() == flow_graph.number_of_edges()
