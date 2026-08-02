"""B16 — the three entry gates are made PROPORTIONATE, not removed.

Each gate independently blocked every index-option entry. The measured evidence for changing gate 1
is this book's own P&L on 2026-07-27: longs 82 trades / 50% win / +10,282 vs shorts 294 / 9.5% /
-45,033 — the veto blocked the ONLY profitable side.

See `docs/research/b16_proportionate_entry_gates_design_2026-07-27.md`.
"""

from dataclasses import dataclass


from nse_algo_trader.conscience.scalable_oversight import (
    classify_oversight,
    is_high_stakes_by_risk_amount,
)
from nse_algo_trader.participant_positioning.market_positioning_bias import (
    institutional_positioning_opposes_entry,
    positioning_size_down_multiplier,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import (
    V1SessionStrategyChoice,
    choose_v1_session_strategy,
)


@dataclass(frozen=True)
class _Reading:
    """The REAL live reading measured on 2026-07-27 that blocked every bullish entry."""

    directional_lean: str = "bearish"
    retail_on_other_side: bool = True
    participation_conviction: str = "normal"
    fii_net_trend: str = "confirming"


class TestGate1PositioningIsGradedNotBinary:
    def test_the_b16_regression_an_opposed_bullish_entry_is_sized_down_not_refused(self):
        """THE fix: the bearish lean must no longer refuse the profitable side outright."""
        multiplier = positioning_size_down_multiplier(
            _Reading(), entry_is_bullish=True, instrument_kind="cash_equity"
        )
        assert 0.0 < multiplier < 1.0, "opposed entry must be sized DOWN, not blocked"

    def test_an_unopposed_entry_is_untouched(self):
        assert positioning_size_down_multiplier(
            _Reading(), entry_is_bullish=False, instrument_kind="cash_equity"
        ) == 1.0

    def test_relevance_is_instrument_scaled_index_option_weighs_most(self):
        """One market-wide INDEX-futures reading says most about an index, least about one stock."""
        index_opt = positioning_size_down_multiplier(_Reading(), True, "index_option")
        stock_opt = positioning_size_down_multiplier(_Reading(), True, "stock_option")
        cash = positioning_size_down_multiplier(_Reading(), True, "cash_equity")
        assert index_opt < stock_opt < cash < 1.0

    def test_an_unknown_instrument_kind_fails_safe_to_the_mildest_effect(self):
        unknown = positioning_size_down_multiplier(_Reading(), True, "something_new")
        assert unknown == positioning_size_down_multiplier(_Reading(), True, "cash_equity")

    def test_tighten_only_no_reading_or_kind_can_increase_a_position(self):
        for kind in ("index_option", "stock_option", "cash_equity", "unmapped"):
            for bullish in (True, False):
                assert 0.0 < positioning_size_down_multiplier(_Reading(), bullish, kind) <= 1.0

    def test_the_underlying_boolean_gate_still_reports_opposition_honestly(self):
        """The gate is NOT removed — it still identifies the divergence; callers grade it."""
        assert institutional_positioning_opposes_entry(_Reading(), entry_is_bullish=True)
        assert not institutional_positioning_opposes_entry(_Reading(), entry_is_bullish=False)

    def test_every_existing_escape_still_returns_full_size(self):
        """No reading / low conviction / weakening FII trend must all remain non-opposing."""
        assert positioning_size_down_multiplier(None, True, "index_option") == 1.0
        assert positioning_size_down_multiplier(
            _Reading(participation_conviction="low"), True, "index_option"
        ) == 1.0
        assert positioning_size_down_multiplier(
            _Reading(fii_net_trend="weakening"), True, "index_option"
        ) == 1.0
        assert positioning_size_down_multiplier(
            _Reading(retail_on_other_side=False), True, "index_option"
        ) == 1.0


class TestGate2StakesAreMoneyNotInstrumentClass:
    CAPITAL = 100_000_000.0  # Rs 10 crore, the live configured capital

    def test_a_small_defined_risk_option_spread_is_not_high_stakes(self):
        """Rs 5,000 at risk on Rs 10cr is 0.005% — the old rule called this high-stakes."""
        assert not is_high_stakes_by_risk_amount(5_000.0, self.CAPITAL)

    def test_a_large_cash_position_IS_high_stakes(self):
        """The old rule called every cash position low-stakes regardless of size."""
        assert is_high_stakes_by_risk_amount(5_000_000.0, self.CAPITAL)

    def test_unknown_risk_or_capital_fails_SAFE_to_high_stakes(self):
        assert is_high_stakes_by_risk_amount(None, self.CAPITAL)
        assert is_high_stakes_by_risk_amount(5_000.0, None)
        assert is_high_stakes_by_risk_amount(5_000.0, 0.0)

    def test_the_oversight_gate_STILL_blocks_high_stakes_low_confidence(self):
        """Criterion 6 — the gate must NOT be weakened."""
        decision = classify_oversight(win_probability=0.20, is_high_stakes=True)
        assert decision.permit_autonomous is False

    def test_a_small_option_entry_at_the_same_low_confidence_now_permits(self):
        """The exact case that blocked every index option: low win-prob, tiny defined risk."""
        high_stakes = is_high_stakes_by_risk_amount(5_000.0, self.CAPITAL)
        decision = classify_oversight(win_probability=0.20, is_high_stakes=high_stakes)
        assert decision.permit_autonomous is True


class TestGate3IndecisiveBandRoutesToDefinedRisk:
    def test_the_banknifty_case_adx_24_96_no_longer_stands_aside(self):
        """Measured live 2026-07-27: BANKNIFTY sat at ADX 24.96, inside the dead band."""
        assert choose_v1_session_strategy(24.96) is V1SessionStrategyChoice.CREDIT_SPREAD

    def test_absent_adx_still_stands_aside_never_trade_blind(self):
        """Criterion 7 — STAND_ASIDE is RETAINED for unusable data."""
        assert choose_v1_session_strategy(None) is V1SessionStrategyChoice.STAND_ASIDE

    def test_trending_and_range_bound_routing_is_unchanged(self):
        assert choose_v1_session_strategy(40.0) is V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT
        assert choose_v1_session_strategy(10.0) is V1SessionStrategyChoice.CREDIT_SPREAD

    def test_the_whole_indecisive_band_is_now_tradable(self):
        for adx in (20.5, 22.0, 24.0, 24.99):
            assert choose_v1_session_strategy(adx) is V1SessionStrategyChoice.CREDIT_SPREAD
