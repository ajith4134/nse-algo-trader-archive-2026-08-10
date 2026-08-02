"""B7 — discrete option-lot size-down policy.

The regression these lock down: `int(1 * 0.90) == 0` silently converted "trim this position by
10%" into "never place this order", which blocked 100% of option entries. See
`docs/research/b7_discrete_option_lot_sizing_design_2026-07-27.md`.
"""

import math

from nse_algo_trader.risk_management import (
    compose_size_down_multipliers,
    size_down_discrete_lots,
)


class TestComposeSizeDownMultipliers:
    def test_composes_to_the_product(self):
        assert compose_size_down_multipliers(0.5, 0.5) == 0.25

    def test_no_levers_is_identity(self):
        assert compose_size_down_multipliers() == 1.0

    def test_is_tighten_only_a_lever_above_one_cannot_upsize(self):
        # A buggy or mis-scaled lever reporting 5.0 must never grow a position.
        assert compose_size_down_multipliers(5.0, 0.5) == 0.5

    def test_a_negative_lever_clamps_to_a_veto(self):
        assert compose_size_down_multipliers(-2.0, 1.0) == 0.0

    def test_non_finite_lever_vetoes_rather_than_being_ignored(self):
        # Unreadable risk telemetry is not evidence that trading is safe.
        assert compose_size_down_multipliers(float("nan"), 1.0) == 0.0
        assert compose_size_down_multipliers(float("inf"), 1.0) == 0.0


class TestSizeDownDiscreteLots:
    def test_the_b7_regression_ninety_percent_of_one_lot_still_trades_one_lot(self):
        decision = size_down_discrete_lots(base_lots=1, composed_multiplier=0.90)
        assert decision.granted_lots == 1
        assert decision.permits_order
        assert decision.stood_aside_reason is None

    def test_a_quarter_of_one_lot_stands_aside_with_a_reason(self):
        decision = size_down_discrete_lots(base_lots=1, composed_multiplier=0.25)
        assert decision.granted_lots == 0
        assert not decision.permits_order
        assert "minimum" in decision.stood_aside_reason
        # The near-miss is preserved so an operator can see how close it came.
        assert math.isclose(decision.intended_lots, 0.25)

    def test_the_real_live_multiplier_stack_on_a_risk_sized_base_trades(self):
        # Measured live 2026-07-27: debate 1.0 x index-level 1.0 x vitality 0.25 x workspace 0.90.
        composed = compose_size_down_multipliers(1.0, 1.0, 0.25, 0.90)
        assert math.isclose(composed, 0.225)
        # Base 1 (the old hard-coded value) could never trade...
        assert size_down_discrete_lots(base_lots=1, composed_multiplier=composed).granted_lots == 0
        # ...but the risk-sized base does, correctly trimmed.
        assert size_down_discrete_lots(base_lots=6, composed_multiplier=composed).granted_lots == 1
        assert size_down_discrete_lots(base_lots=20, composed_multiplier=composed).granted_lots == 5

    def test_rounds_half_up_not_bankers(self):
        # Python's round() is round-half-to-EVEN: round(0.5)==0 and round(1.5)==2, which is
        # inconsistent at exactly the boundary that decides trade-or-not.
        assert size_down_discrete_lots(base_lots=1, composed_multiplier=0.5).granted_lots == 1
        assert size_down_discrete_lots(base_lots=3, composed_multiplier=0.5).granted_lots == 2

    def test_identity_multiplier_leaves_the_risk_sized_count_untouched(self):
        decision = size_down_discrete_lots(base_lots=7, composed_multiplier=1.0)
        assert decision.granted_lots == 7

    def test_explicit_zero_lever_is_a_veto_distinct_from_a_rounding_stand_aside(self):
        decision = size_down_discrete_lots(base_lots=50, composed_multiplier=0.0)
        assert decision.granted_lots == 0
        assert "vetoed" in decision.stood_aside_reason

    def test_no_lots_approved_by_the_risk_gate_stands_aside(self):
        decision = size_down_discrete_lots(base_lots=0, composed_multiplier=1.0)
        assert decision.granted_lots == 0
        assert "risk gate" in decision.stood_aside_reason

    def test_never_upsizes_beyond_the_risk_approved_base(self):
        for base in (1, 3, 25, 400):
            for multiplier in (0.01, 0.25, 0.5, 0.9, 1.0):
                granted = size_down_discrete_lots(base, multiplier).granted_lots
                assert granted <= base, (base, multiplier, granted)

    def test_non_finite_composed_multiplier_stands_aside(self):
        decision = size_down_discrete_lots(base_lots=10, composed_multiplier=float("nan"))
        assert decision.granted_lots == 0
        assert "non-finite" in decision.stood_aside_reason
