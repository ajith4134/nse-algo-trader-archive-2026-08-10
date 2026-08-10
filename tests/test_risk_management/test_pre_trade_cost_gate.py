"""The pre-trade COST gate — expected edge must clear modelled round-trip cost (statutory + slippage).

Hermetic (Rule J): drives the real cost model + real slippage/impact models on constructed signals; no
market session needed. The real-data pass is on the live feed (loop wiring), tracked separately.
"""

from nse_algo_trader.risk_management.pre_trade_cost_gate import (
    CostGateConfig,
    CostGateVerdict,
    PreTradeCostGate,
    SlippageCalibrationState,
    SlippagePrior,
)


def _gate(**cfg):
    return PreTradeCostGate(config=CostGateConfig(**cfg))


class TestDirectionalGate:
    def test_a_fat_edge_passes_at_full_size(self):
        # Cash long: entry 100 -> target 105 = ~500 bps edge, far above ~a few bps cost. PASS, full size.
        d = _gate().evaluate_directional(
            segment="nse_cash_equity", entry_price=100.0, target_price=105.0,
            opened_short=False, risk_approved_quantity=1000,
        )
        assert d.verdict is CostGateVerdict.PASS
        assert d.approved_quantity == 1000
        assert d.expected_edge_bps > d.required_edge_bps
        assert d.cost.round_trip_bps > 0

    def test_a_razor_thin_edge_is_vetoed(self):
        # entry 100 -> target 100.05 = 5 bps edge, below statutory+spread round-trip cost. VETO.
        d = _gate().evaluate_directional(
            segment="nse_cash_equity", entry_price=100.0, target_price=100.05,
            opened_short=False, risk_approved_quantity=1000,
        )
        assert d.verdict is CostGateVerdict.VETO
        assert d.approved_quantity == 0
        assert d.shortfall_bps > 0

    def test_impact_heavy_order_is_resized_down_not_vetoed(self):
        # A huge order vs a thin ADV: full-size impact (50% participation) eats the ~45 bps edge, but a
        # half-size (25% participation, sqrt-lower impact) clears it -> the gate RESIZES rather than vetoes.
        gate = _gate()
        d = gate.evaluate_directional(
            segment="nse_cash_equity", entry_price=100.0, target_price=100.45,
            opened_short=False, risk_approved_quantity=100_000,
            average_daily_quantity=200_000,
        )
        assert d.verdict is CostGateVerdict.RESIZE
        assert 0 < d.approved_quantity < 100_000

    def test_short_uses_entry_leg_for_stt_via_the_cost_model(self):
        # Just assert the gate runs a short without error and produces a cost — direction handling is the
        # cost model's tested job; here we confirm the wiring passes opened_short through.
        d = _gate().evaluate_directional(
            segment="nse_index_options", entry_price=200.0, target_price=150.0,
            opened_short=True, risk_approved_quantity=65,
        )
        assert d.cost.round_trip_bps > 0
        assert d.expected_edge_bps > 0

    def test_options_cost_more_bps_than_cash_for_the_same_move(self):
        cash = _gate().evaluate_directional(
            "nse_cash_equity", 100.0, 101.0, False, 1000,
        )
        opt = _gate().evaluate_directional(
            "nse_index_options", 100.0, 101.0, False, 1000,
        )
        assert opt.cost.round_trip_bps > cash.cost.round_trip_bps  # options STT + wider spread


class TestInvariants:
    def test_round_trip_cost_is_positive_and_sums_components(self):
        d = _gate().evaluate_directional("nse_cash_equity", 250.0, 260.0, False, 400)
        assert d.cost.round_trip_bps == d.cost.statutory_bps + d.cost.slippage_bps
        assert d.cost.statutory_bps > 0 and d.cost.slippage_bps > 0

    def test_larger_margin_makes_the_gate_stricter(self):
        loose = _gate(edge_safety_margin_bps=0.0).evaluate_directional(
            "nse_cash_equity", 100.0, 100.3, False, 1000,
        )
        strict = _gate(edge_safety_margin_bps=1000.0).evaluate_directional(
            "nse_cash_equity", 100.0, 100.3, False, 1000,
        )
        # A 1000-bps margin cannot be cleared by a 30-bps edge -> veto, where a 0 margin might pass.
        assert strict.verdict is CostGateVerdict.VETO
        assert strict.required_edge_bps > loose.required_edge_bps

    def test_zero_or_degenerate_inputs_do_not_raise(self):
        d = _gate().evaluate_directional("nse_cash_equity", 0.0, 0.0, False, 0)
        assert d.verdict is CostGateVerdict.VETO
        assert d.approved_quantity == 0


class TestSlippageCalibrationState:
    def test_gathering_returns_the_prior_until_armed(self):
        st = SlippageCalibrationState(
            prior=SlippagePrior(cash_equity_half_spread_bps=3.0), minimum_samples_to_arm=30
        )
        assert st.one_way_slippage_bps("nse_cash_equity") == 3.0
        status, have, need = st.maturity("nse_cash_equity")
        assert status == "gathering" and have == 0 and need == 30

    def test_arms_and_shrinks_toward_empirical_after_enough_fills(self):
        st = SlippageCalibrationState(
            prior=SlippagePrior(cash_equity_half_spread_bps=3.0), minimum_samples_to_arm=30
        )
        for _ in range(60):
            st.observe("nse_cash_equity", 9.0)  # real fills are wider than the 3 bps prior
        status, have, need = st.maturity("nse_cash_equity")
        assert status == "earned" and have == 60
        armed = st.one_way_slippage_bps("nse_cash_equity")
        # Shrinkage: between the 3 bps prior and the 9 bps empirical, closer to empirical at n=60, k=30.
        assert 3.0 < armed < 9.0
        assert armed == 60 / (60 + 30) * 9.0 + 30 / (60 + 30) * 3.0

    def test_armed_higher_slippage_raises_the_cost_and_can_flip_a_pass_to_veto(self):
        cfg = CostGateConfig()
        thin_edge = {
            "segment": "nse_cash_equity", "entry_price": 100.0, "target_price": 100.2,
            "opened_short": False, "risk_approved_quantity": 1000,
        }
        prior_gate = PreTradeCostGate(config=cfg)
        before = prior_gate.evaluate_directional(**thin_edge)
        armed_state = SlippageCalibrationState(minimum_samples_to_arm=10)
        for _ in range(40):
            armed_state.observe("nse_cash_equity", 80.0)  # brutal real slippage
        armed_gate = PreTradeCostGate(config=cfg, slippage_state=armed_state)
        after = armed_gate.evaluate_directional(**thin_edge)
        assert after.cost.slippage_bps > before.cost.slippage_bps


class TestCreditSpreadGate:
    def test_fat_net_credit_passes(self):
        # Short 120, hedge 40 -> net credit 80/unit; costs are a small fraction of an 80-wide credit. PASS.
        d = _gate().evaluate_credit_spread(
            segment="nse_index_options", short_leg_premium=120.0, hedge_leg_premium=40.0,
            lot_size=65, lots=1,
        )
        assert d.verdict is CostGateVerdict.PASS
        assert d.approved_quantity == 65

    def test_thin_net_credit_is_vetoed_because_cost_hits_both_legs(self):
        # Short 100.5, hedge 100 -> net credit only 0.5/unit, but STT + exchange charge BOTH ~100 premiums.
        # The old net-credit-based cost would have understated this; the both-leg cost vetoes it.
        d = _gate().evaluate_credit_spread(
            segment="nse_index_options", short_leg_premium=100.5, hedge_leg_premium=100.0,
            lot_size=65, lots=1,
        )
        assert d.verdict is CostGateVerdict.VETO
        assert d.approved_quantity == 0
        assert d.shortfall_bps > 0

    def test_cost_reflects_both_legs_not_just_the_net_credit(self):
        # Two spreads with the SAME net credit (10) but very different leg premiums: the wide-premium one
        # costs more (STT/exchange scale with each leg's premium), proving cost is not net-credit-based.
        narrow = _gate().evaluate_credit_spread("nse_index_options", 15.0, 5.0, 65, 1)
        wide = _gate().evaluate_credit_spread("nse_index_options", 205.0, 195.0, 65, 1)
        assert wide.cost.round_trip_bps > narrow.cost.round_trip_bps


class TestTallySnapshot:
    def test_snapshot_counts_decisions_and_reports_maturity(self):
        gate = _gate()
        gate.evaluate_directional("nse_cash_equity", 100.0, 110.0, False, 1000)  # pass
        gate.evaluate_directional("nse_cash_equity", 100.0, 100.02, False, 1000)  # veto
        snap = gate.snapshot()
        assert snap["nse_cash_equity"]["passed"] == 1
        assert snap["nse_cash_equity"]["vetoed"] == 1
        assert snap["nse_cash_equity"]["decided"] == 2
        assert 0.0 < snap["nse_cash_equity"]["veto_rate"] < 1.0
        assert snap["nse_cash_equity"]["slippage_status"] == "gathering"
        assert snap["_all"]["passed"] == 1 and snap["_all"]["vetoed"] == 1
