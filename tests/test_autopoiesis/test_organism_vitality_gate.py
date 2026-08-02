"""Trunk X — the entry-site lever. The chronic-vs-acute split is the load-bearing property here."""

from __future__ import annotations

import pytest

from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentHealthAssessment,
    DegradationState,
)
from nse_algo_trader.autopoiesis.operational_closure_auditor import audit_operational_closure
from nse_algo_trader.autopoiesis.organism_vitality_gate import (
    CRITICAL_CLOSURE_VIOLATION_SIZE_MULTIPLIER,
    IDENTITY_SIZE_MULTIPLIER,
    OrganismVitalityGate,
)


def _assessment(component_id: str, health: float, state: DegradationState) -> ComponentHealthAssessment:
    return ComponentHealthAssessment(
        component_id=component_id,
        health_index=health,
        t_squared=None,
        spe_q=None,
        ewma_level=0.0,
        degradation_state=state,
        sample_count=40,
        required_sample_count=30,
        is_pca_armed=False,
        contributing_signals=(),
    )


def _healthy_vital_assessments(gate: OrganismVitalityGate) -> list[ComponentHealthAssessment]:
    return [
        _assessment(component_id, 1.0, DegradationState.HEALTHY)
        for component_id in sorted(gate.registry.vital_component_ids())
    ]


def test_no_assessment_yet_is_permissive_identity() -> None:
    """A homeostat that has not measured anything must not tighten anything."""
    verdict = OrganismVitalityGate().evaluate()
    assert verdict.permits_order is True
    assert verdict.size_multiplier == IDENTITY_SIZE_MULTIPLIER


def test_a_chronic_closure_violation_prices_down_but_never_vetoes() -> None:
    """THE regression test for the 2026-07-27 finding.

    Every component perfectly healthy, but the real organism carries a permanent CRITICAL closure
    violation (`artifact.win_probability_model` is maintained by nothing). Vetoing on that halted ALL
    trading indefinitely. It must price size down instead.
    """
    gate = OrganismVitalityGate()
    gate.ingest_assessment(_healthy_vital_assessments(gate), audit_operational_closure())
    verdict = gate.evaluate()
    assert verdict.permits_order is True, "a chronic structural fact must never halt trading"
    assert verdict.size_multiplier == pytest.approx(CRITICAL_CLOSURE_VIOLATION_SIZE_MULTIPLIER)
    assert verdict.binding_component_id == "artifact.win_probability_model"


def test_an_acute_failure_of_a_vital_component_vetoes() -> None:
    gate = OrganismVitalityGate()
    assessments = [a for a in _healthy_vital_assessments(gate) if a.component_id != "store.market_data"]
    assessments.append(_assessment("store.market_data", 0.0, DegradationState.FAILED))
    gate.ingest_assessment(assessments, audit_operational_closure())
    verdict = gate.evaluate()
    assert verdict.permits_order is False
    assert verdict.size_multiplier == 0.0
    assert verdict.binding_component_id == "store.market_data"


def test_a_degraded_non_vital_component_tightens_without_vetoing() -> None:
    gate = OrganismVitalityGate()
    assessments = _healthy_vital_assessments(gate)
    assessments.append(_assessment("store.news", 0.55, DegradationState.DEGRADED))
    gate.ingest_assessment(assessments)
    verdict = gate.evaluate(depends_on_component_ids=["store.news"])
    assert verdict.permits_order is True
    assert 0.0 < verdict.size_multiplier < IDENTITY_SIZE_MULTIPLIER


def test_the_tightest_lever_wins_rather_than_the_average() -> None:
    """Chronic and acute risk compose by min(), never by averaging — one real problem must not be
    diluted by everything else being fine (the same weighted-max principle the health index uses)."""
    gate = OrganismVitalityGate()
    assessments = [a for a in _healthy_vital_assessments(gate) if a.component_id != "store.market_data"]
    assessments.append(_assessment("store.market_data", 0.4, DegradationState.FAILING))
    gate.ingest_assessment(assessments, audit_operational_closure())
    verdict = gate.evaluate()
    # FAILING on a VITAL component is acute -> veto dominates the 0.50 chronic multiplier.
    assert verdict.permits_order is False


@pytest.mark.parametrize(
    "health,state",
    [
        (1.0, DegradationState.HEALTHY),
        (0.7, DegradationState.DEGRADED),
        (0.3, DegradationState.FAILING),
        (0.0, DegradationState.FAILED),
    ],
)
def test_the_multiplier_can_never_exceed_one(health: float, state: DegradationState) -> None:
    """Structural tighten-only guarantee: no state of the organism may up-size a trade."""
    gate = OrganismVitalityGate()
    gate.ingest_assessment([_assessment("store.news", health, state)])
    assert 0.0 <= gate.size_multiplier_for_entry(["store.news"]) <= IDENTITY_SIZE_MULTIPLIER


def test_a_nan_health_index_cannot_reach_the_gate_at_all() -> None:
    """Defence in depth, verified at the real boundary.

    The gate clamps NaN to the safe identity, but that path is unreachable in practice because
    `ComponentHealthAssessment` refuses to be constructed with a non-finite health index. Asserting
    the CONTRACT is the honest test — asserting the gate's dead branch would be theatre.
    """
    with pytest.raises(ValueError, match="escaped"):
        _assessment("store.news", float("nan"), DegradationState.HEALTHY)


def test_the_clamp_normalises_a_non_finite_multiplier_to_identity() -> None:
    """The gate's own arithmetic guard, tested directly rather than through an impossible input."""
    from nse_algo_trader.autopoiesis.organism_vitality_gate import _clamp_unit

    assert _clamp_unit(float("nan")) == IDENTITY_SIZE_MULTIPLIER
    assert _clamp_unit(-5.0) == 0.0
    assert _clamp_unit(99.0) == IDENTITY_SIZE_MULTIPLIER


def test_an_internal_failure_never_raises_into_the_trading_loop() -> None:
    """The entry sites call this inside their multiplier chain; it must not be able to break them."""
    gate = OrganismVitalityGate()

    class _ExplodingRegistry:
        def vital_component_ids(self):  # noqa: ANN202 - deliberately hostile double
            raise RuntimeError("registry exploded")

    gate.registry = _ExplodingRegistry()  # type: ignore[assignment]
    gate.ingest_assessment([_assessment("store.news", 0.2, DegradationState.FAILING)])
    verdict = gate.evaluate()
    assert verdict.permits_order is True
    assert verdict.size_multiplier == IDENTITY_SIZE_MULTIPLIER
    assert gate.internal_failure_count == 1


def test_an_unrelated_degraded_component_does_not_bind_an_entry_that_never_used_it() -> None:
    gate = OrganismVitalityGate()
    assessments = _healthy_vital_assessments(gate)
    assessments.append(_assessment("store.news", 0.1, DegradationState.FAILED))
    gate.ingest_assessment(assessments)
    # store.news is not VITAL and this entry does not declare a dependency on it.
    assert gate.permits_order() is True


def test_dashboard_metrics_expose_the_maturity_ladder() -> None:
    gate = OrganismVitalityGate()
    gate.ingest_assessment(_healthy_vital_assessments(gate))
    metrics = dict(gate.dashboard_metrics())
    assert "components armed" in metrics
    assert "organism vitality" in metrics
