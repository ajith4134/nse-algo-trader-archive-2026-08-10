"""B19 — an observability gap must size DOWN, never hard-veto.

The live outage this locks down (2026-07-27): every VITAL component's declared failure signal read
0.0 — `thread.live_paper_loop` reported `thread_not_alive=0.0` while ALSO reporting
`observability_gap:thread_heartbeat=1.0` — yet the gate returned size_multiplier 0.0 /
permits_order False and halted ALL trading in both segments. The organism was blind, not broken.

Signal names below are the REAL ones taken from the live homeostat telemetry store, not invented.
See `docs/research/b19_unobservability_must_not_veto_design_2026-07-27.md`.
"""

from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentHealthAssessment,
    DegradationState,
)
from nse_algo_trader.autopoiesis.component_registry import build_default_component_registry
from nse_algo_trader.autopoiesis.organism_vitality_gate import (
    DEGRADATION_SIZE_MULTIPLIER,
    OrganismVitalityGate,
)

# A real VITAL component id, and a real SUPPORTING one, from the live registry.
VITAL_COMPONENT_ID = "thread.live_paper_loop"
SUPPORTING_COMPONENT_ID = "thread.news_acquisition"


def _assessment(
    component_id: str,
    contributing_signals: tuple[tuple[str, float], ...],
    health_index: float = 0.307,  # the live value when trading halted
    degradation_state: DegradationState = DegradationState.FAILING,
) -> ComponentHealthAssessment:
    return ComponentHealthAssessment(
        component_id=component_id,
        health_index=health_index,
        t_squared=None,
        spe_q=None,
        ewma_level=1.0 - health_index,
        degradation_state=degradation_state,
        sample_count=0,
        required_sample_count=30,
        is_pca_armed=False,  # live: "health model armed 0/36"
        contributing_signals=contributing_signals,
    )


def _gate_with(assessment: ComponentHealthAssessment) -> OrganismVitalityGate:
    gate = OrganismVitalityGate(registry=build_default_component_registry())
    gate.ingest_assessment([assessment])
    return gate


class TestUnobservabilityDoesNotVeto:
    def test_the_live_outage_blind_vital_component_sizes_down_instead_of_halting(self):
        """Criterion 1 — the exact live case."""
        gate = _gate_with(
            _assessment(
                VITAL_COMPONENT_ID,
                (("observability_gap:thread_heartbeat", 0.5),),
            )
        )
        verdict = gate.evaluate()
        assert verdict.permits_order is True
        assert verdict.size_multiplier == DEGRADATION_SIZE_MULTIPLIER[DegradationState.FAILING]
        assert "UNOBSERVABLE" in verdict.reason

    def test_a_genuine_failure_still_vetoes(self):
        """Criterion 2 — the veto must NOT be weakened."""
        gate = _gate_with(
            _assessment(VITAL_COMPONENT_ID, (("thread_not_alive", 1.0),))
        )
        verdict = gate.evaluate()
        assert verdict.permits_order is False
        assert verdict.size_multiplier == 0.0

    def test_blindness_does_not_excuse_an_accompanying_real_failure(self):
        """Criterion 3 — a mix must still veto."""
        gate = _gate_with(
            _assessment(
                VITAL_COMPONENT_ID,
                (("thread_not_alive", 1.0), ("observability_gap:thread_heartbeat", 0.5)),
            )
        )
        verdict = gate.evaluate()
        assert verdict.permits_order is False
        assert verdict.size_multiplier == 0.0

    def test_a_zero_severity_failure_signal_alongside_a_gap_is_still_only_blindness(self):
        """The live shape exactly: `thread_not_alive=0.0` present but NOT charging."""
        gate = _gate_with(
            _assessment(
                VITAL_COMPONENT_ID,
                (("observability_gap:thread_heartbeat", 0.5), ("thread_not_alive", 0.0)),
            )
        )
        verdict = gate.evaluate()
        assert verdict.permits_order is True

    def test_no_charging_signal_at_all_does_not_excuse_a_veto(self):
        """Absence of attribution is not positive evidence of blindness."""
        gate = _gate_with(_assessment(VITAL_COMPONENT_ID, (("thread_not_alive", 0.0),)))
        verdict = gate.evaluate()
        assert verdict.permits_order is False

    def test_a_failed_but_blind_vital_component_still_only_sizes_down(self):
        """FAILED (not just FAILING) on pure blindness is still blindness."""
        gate = _gate_with(
            _assessment(
                VITAL_COMPONENT_ID,
                (("observability_gap:operational_observation", 1.0),),
                health_index=0.05,
                degradation_state=DegradationState.FAILED,
            )
        )
        verdict = gate.evaluate()
        assert verdict.permits_order is True
        assert verdict.size_multiplier == DEGRADATION_SIZE_MULTIPLIER[DegradationState.FAILED]

    def test_a_supporting_component_never_vetoed_either_way(self):
        """Criterion 5 — unchanged behaviour for non-VITAL components."""
        gate = _gate_with(
            _assessment(SUPPORTING_COMPONENT_ID, (("thread_not_alive", 1.0),))
        )
        assert gate.evaluate().permits_order is True

    def test_tighten_only_invariant_holds_on_every_path(self):
        """Criterion 4 — no path can up-size."""
        for signals in (
            (("observability_gap:thread_heartbeat", 0.5),),
            (("thread_not_alive", 1.0),),
            (("observability_gap:operational_observation", 1.0), ("thread_not_alive", 1.0)),
        ):
            gate = _gate_with(_assessment(VITAL_COMPONENT_ID, signals))
            assert 0.0 <= gate.size_multiplier_for_entry() <= 1.0
