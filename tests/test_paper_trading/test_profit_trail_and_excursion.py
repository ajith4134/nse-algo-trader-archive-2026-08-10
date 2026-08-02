"""B23 — profit-trail gating + MFE/MAE excursion tracking.

The core property under test is the RATCHET: `locked_profit` must be non-decreasing over ANY price
path. If that ever fails, the feature has done the opposite of its purpose — it would hand back
profit it had already protected.

See `docs/research/b23_profit_trail_and_excursion_design_2026-07-27.md`.
"""

import random

from nse_algo_trader.paper_trading.position_excursion_tracker import (
    PositionProfitExcursion,
)
from nse_algo_trader.paper_trading.profit_trail_lock_engine import (
    ProfitTrailPolicy,
    ProfitTrailState,
    arm_trigger_reason,
    candidate_locked_profit_levels,
    extended_target_profit,
    trail_exit_triggered,
    update_profit_trail,
)

RISK = 1000.0  # 1R = Rs 1,000
NOTIONAL = 100_000.0
ATR_AMOUNT = 400.0


def _advance(trail, peak, **kwargs):
    return update_profit_trail(
        trail,
        peak_profit=peak,
        initial_risk_amount=kwargs.get("risk", RISK),
        atr_profit_amount=kwargs.get("atr", ATR_AMOUNT),
        entry_notional=kwargs.get("notional", NOTIONAL),
        policy=kwargs.get("policy"),
    )


class TestExcursionTracking:
    def test_mfe_rises_and_mae_falls_and_both_start_at_zero(self):
        excursion = PositionProfitExcursion()
        assert excursion.maximum_favourable_profit == 0.0
        assert excursion.maximum_adverse_profit == 0.0
        for profit in (500.0, -300.0, 900.0, -50.0, 200.0):
            excursion.observe_unrealised_profit(profit)
        assert excursion.maximum_favourable_profit == 900.0
        assert excursion.maximum_adverse_profit == -300.0
        assert excursion.observation_count == 5

    def test_a_trade_that_never_goes_green_reports_zero_mfe_not_none(self):
        excursion = PositionProfitExcursion()
        for profit in (-100.0, -400.0, -250.0):
            excursion.observe_unrealised_profit(profit)
        assert excursion.maximum_favourable_profit == 0.0
        assert not excursion.has_been_in_profit

    def test_an_unavailable_or_non_finite_price_is_ignored_not_fabricated(self):
        excursion = PositionProfitExcursion()
        excursion.observe_unrealised_profit(700.0)
        excursion.observe_unrealised_profit(None)
        excursion.observe_unrealised_profit(float("nan"))
        excursion.observe_unrealised_profit(float("inf"))
        assert excursion.maximum_favourable_profit == 700.0
        assert excursion.observation_count == 1

    def test_extremes_are_monotone_over_a_random_path(self):
        rng = random.Random(20260727)
        excursion = PositionProfitExcursion()
        best, worst = 0.0, 0.0
        for _ in range(500):
            profit = rng.uniform(-5000.0, 5000.0)
            excursion.observe_unrealised_profit(profit)
            best, worst = max(best, profit), min(worst, profit)
            assert excursion.maximum_favourable_profit == best
            assert excursion.maximum_adverse_profit == worst


class TestArmTrigger:
    def test_r_multiple_arms_first_when_the_stop_is_meaningful(self):
        reason, _ = arm_trigger_reason(RISK, RISK, ATR_AMOUNT, NOTIONAL, ProfitTrailPolicy())
        assert "R" in reason

    def test_not_armed_below_every_threshold(self):
        reason, _ = arm_trigger_reason(10.0, RISK, ATR_AMOUNT, NOTIONAL, ProfitTrailPolicy())
        assert reason == ""

    def test_a_pathologically_tight_stop_still_arms_via_the_percentage_floor(self):
        """1R of a near-zero stop is noise — the % floor is what makes this case sane."""
        reason, _ = arm_trigger_reason(
            peak_profit=1500.0,
            initial_risk_amount=0.01,
            atr_profit_amount=None,
            entry_notional=NOTIONAL,
            policy=ProfitTrailPolicy(),
        )
        assert reason != ""

    def test_unavailable_inputs_abstain_and_are_named_never_fabricated(self):
        reason, abstained = arm_trigger_reason(
            peak_profit=1.0,
            initial_risk_amount=None,
            atr_profit_amount=None,
            entry_notional=None,
            policy=ProfitTrailPolicy(),
        )
        assert reason == ""
        assert len(abstained) == 3
        assert any("initial_risk" in note for note in abstained)

    def test_a_zero_threshold_is_the_degenerate_arm_immediately_case(self):
        policy = ProfitTrailPolicy(arm_at_risk_multiple=0.0)
        reason, _ = arm_trigger_reason(0.01, RISK, None, None, policy)
        assert reason != ""


class TestTrailDistanceBlend:
    def test_the_median_is_used_not_the_tightest_or_loosest(self):
        levels = candidate_locked_profit_levels(5000.0, RISK, ATR_AMOUNT, ProfitTrailPolicy())
        assert len(levels) == 4
        trail = _advance(ProfitTrailState(), 5000.0)
        assert min(levels) < trail.locked_profit < max(levels)

    def test_candidates_abstain_when_their_input_is_missing(self):
        levels = candidate_locked_profit_levels(5000.0, None, None, ProfitTrailPolicy())
        assert len(levels) == 2  # only the two peak-fraction methods survive

    def test_a_locked_level_never_exceeds_the_profit_actually_earned(self):
        for peak in (0.0, 100.0, 5000.0, 1_000_000.0):
            for level in candidate_locked_profit_levels(
                peak, RISK, ATR_AMOUNT, ProfitTrailPolicy()
            ):
                assert 0.0 <= level <= peak


class TestRatchetInvariant:
    def test_the_lock_never_loosens_over_a_random_price_path(self):
        """THE core property: no sequence of prices may ever lower an existing lock."""
        rng = random.Random(4242)
        for _ in range(60):
            trail = ProfitTrailState()
            excursion = PositionProfitExcursion()
            previous_lock = -1.0
            profit = 0.0
            for _ in range(200):
                profit += rng.uniform(-1200.0, 1200.0)
                excursion.observe_unrealised_profit(profit)
                trail = _advance(trail, excursion.maximum_favourable_profit)
                if trail.is_armed:
                    assert trail.locked_profit >= previous_lock, "the trail LOOSENED"
                    previous_lock = trail.locked_profit

    def test_a_deep_retrace_after_a_big_run_does_not_release_the_lock(self):
        trail = _advance(ProfitTrailState(), 10_000.0)
        locked_at_peak = trail.locked_profit
        assert locked_at_peak > 0.0
        # Peak-so-far cannot fall (MFE is monotone), so re-advancing keeps the lock.
        trail = _advance(trail, 10_000.0)
        assert trail.locked_profit >= locked_at_peak

    def test_before_arming_the_trail_never_exits_a_trade(self):
        trail = _advance(ProfitTrailState(), 5.0)
        assert not trail.is_armed
        assert not trail_exit_triggered(trail, -9_999.0)

    def test_after_arming_an_exit_fires_when_profit_retraces_to_the_lock(self):
        trail = _advance(ProfitTrailState(), 6000.0)
        assert trail.is_armed
        assert trail_exit_triggered(trail, trail.locked_profit)
        assert trail_exit_triggered(trail, trail.locked_profit - 1.0)
        assert not trail_exit_triggered(trail, trail.locked_profit + 1.0)

    def test_an_unavailable_price_never_triggers_an_exit(self):
        trail = _advance(ProfitTrailState(), 6000.0)
        assert not trail_exit_triggered(trail, None)
        assert not trail_exit_triggered(trail, float("nan"))


class TestTargetExtension:
    def test_is_inert_by_default_rule_q(self):
        assert extended_target_profit(2000.0, 9999.0, RISK) == 2000.0

    def test_when_armed_the_target_retreats_ahead_of_a_running_trade(self):
        policy = ProfitTrailPolicy(target_extension_risk_multiple=1.0)
        extended = extended_target_profit(2000.0, 9000.0, RISK, policy)
        assert extended == 10_000.0

    def test_never_pulls_a_target_inward(self):
        policy = ProfitTrailPolicy(target_extension_risk_multiple=1.0)
        assert extended_target_profit(50_000.0, 100.0, RISK, policy) == 50_000.0

    def test_abstains_when_risk_is_unknown(self):
        policy = ProfitTrailPolicy(target_extension_risk_multiple=1.0)
        assert extended_target_profit(2000.0, 9000.0, None, policy) == 2000.0


class TestCreditSpreadSignConvention:
    def test_a_credit_spread_profits_as_the_net_premium_falls(self):
        """The sign trap: for a spread, FALLING premium is PROFIT. Working in profit space means the
        trail needs no per-type sign handling — this test pins that contract."""
        entry_net_credit, lots, lot_size = 40.0, 2, 75
        excursion = PositionProfitExcursion()
        trail = ProfitTrailState()
        for net_premium in (40.0, 30.0, 18.0, 25.0):
            profit = (entry_net_credit - net_premium) * lots * lot_size
            excursion.observe_unrealised_profit(profit)
            trail = _advance(trail, excursion.maximum_favourable_profit)
        # Best was at premium 18 -> (40-18)*150 = 3300
        assert excursion.maximum_favourable_profit == 3300.0
        assert trail.is_armed
        assert trail.locked_profit > 0.0
