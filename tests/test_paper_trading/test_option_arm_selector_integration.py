"""B18 step 6 — the selector actually CHANGES which option order is placed.

Until this step the selector was an orphan: perfect posteriors influencing nothing. Rule K is
explicit that display-only does not count. These tests pin the wiring:
selection -> dispatch -> pending record -> cost-net reward on close.
"""

import random
from datetime import datetime, timedelta

import pytest

from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.adaptive_arm_selector import (
    AdaptiveArmSelector,
    tail_aware_reward,
)
from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
    ArmSelectionPosteriorStore,
)
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    OPTION_ARM_CREDIT_SPREAD,
    OPTION_ARM_DIRECTIONAL,
    OPTION_ARM_NAMES,
    option_arm_trade_id,
)
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard
from nse_algo_trader.strategy_engine import V1SessionStrategyChoice

NOW = datetime(2026, 7, 28, 10, 30)


@pytest.fixture
def store(tmp_path):
    store = ArmSelectionPosteriorStore(tmp_path / "arm.sqlite3")
    yield store
    store.close()


def _state(store=None, seed=7):
    state = LiveUniversePaperState(
        ledger=PaperTradingLedger(1e8), scoreboard=PredictionTableScoreboard()
    )
    if store is not None:
        state.option_arm_posterior_store = store
        state.option_arm_selector = AdaptiveArmSelector(
            store, OPTION_ARM_NAMES, random_source=random.Random(seed)
        )
    return state


class TestUnwiredBehaviourIsUnchanged:
    """The integration must not silently alter behaviour before it is switched on."""

    def test_without_a_selector_the_regime_router_decides_exactly_as_before(self):
        state = _state()
        assert state.select_option_arm(
            "NIFTY", V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT, NOW
        ) == OPTION_ARM_DIRECTIONAL
        assert state.select_option_arm(
            "NIFTY", V1SessionStrategyChoice.CREDIT_SPREAD, NOW
        ) == OPTION_ARM_CREDIT_SPREAD

    def test_stand_aside_still_yields_no_arm(self):
        state = _state()
        assert state.select_option_arm(
            "NIFTY", V1SessionStrategyChoice.STAND_ASIDE, NOW
        ) is None

    def test_stand_aside_yields_no_arm_even_WITH_a_selector(self, store):
        """The regime still constrains eligibility — the selector never invents a structure."""
        assert _state(store).select_option_arm(
            "NIFTY", V1SessionStrategyChoice.STAND_ASIDE, NOW
        ) is None


class TestTheSelectorChangesTheDecision:
    def test_a_wired_selector_can_choose_the_arm_the_regime_would_NOT_have_picked(self, store):
        """The point of the slice: the regime is context, not the router."""
        chosen = {
            _state(store, seed=seed).select_option_arm(
                "NIFTY", V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT, NOW
            )
            for seed in range(40)
        }
        assert chosen == set(OPTION_ARM_NAMES), (
            "with a selector wired, BOTH arms must be reachable in a trending regime"
        )

    def test_a_selection_is_recorded_for_audit(self, store):
        state = _state(store)
        state.select_option_arm("NIFTY", V1SessionStrategyChoice.CREDIT_SPREAD, NOW)
        assert state.option_arm_selection_count == 1
        assert state.last_option_arm_selection is not None
        assert state.last_option_arm_selection.selection_reason

    def test_a_failing_selector_falls_back_to_the_regime_router(self, capsys):
        class _Exploding:
            def select_arm(self, *_args):
                raise RuntimeError("posterior store unavailable")

        state = _state()
        state.option_arm_selector = _Exploding()
        arm = state.select_option_arm(
            "NIFTY", V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT, NOW
        )
        assert arm == OPTION_ARM_DIRECTIONAL, "must fall back, not stop trading"
        assert "arm-selector" in capsys.readouterr().out  # surfaced, not swallowed

    def test_contexts_are_per_index_and_per_regime(self, store):
        state = _state(store)
        state.select_option_arm("NIFTY", V1SessionStrategyChoice.CREDIT_SPREAD, NOW)
        state.select_option_arm("BANKNIFTY", V1SessionStrategyChoice.CREDIT_SPREAD, NOW)
        # distinct cells -> both start empty rather than sharing evidence
        assert store.load_cell(
            OPTION_ARM_CREDIT_SPREAD, "NIFTY|credit_spread", NOW
        ).effective_sample_count == 0.0


class TestRewardsReachThePosterior:
    def test_open_then_close_credits_the_arm_that_opened_it(self, store):
        state = _state(store)
        trade_id = option_arm_trade_id("NIFTY", NOW)
        state.record_option_arm_trade_opened(
            trade_id, OPTION_ARM_CREDIT_SPREAD, "NIFTY", "credit_spread", NOW
        )
        assert store.pending_trade_count() == 1

        state.resolve_option_arm_trade_closed(trade_id, 900.0, NOW + timedelta(hours=3))
        assert store.pending_trade_count() == 0
        cell = store.load_cell(
            OPTION_ARM_CREDIT_SPREAD, "NIFTY|credit_spread", NOW + timedelta(hours=3)
        )
        assert cell.effective_sample_count == pytest.approx(1.0)
        assert cell.mean_reward == pytest.approx(tail_aware_reward(900.0))

    def test_a_loss_is_penalised_more_than_an_equal_gain_is_rewarded(self, store):
        """Tail-awareness: a premium-selling arm must not out-vote its own rare large losses."""
        assert tail_aware_reward(-1000.0) < -1000.0
        assert tail_aware_reward(1000.0) == 1000.0

    def test_the_reward_transform_is_monotone(self):
        """A better trade may never score worse — it must not invert two arms' ordering."""
        values = [-5000.0, -100.0, -1.0, 0.0, 1.0, 100.0, 5000.0]
        rewards = [tail_aware_reward(v) for v in values]
        assert rewards == sorted(rewards)

    def test_the_trade_id_is_reproducible_from_the_position(self):
        """It must be derivable at CLOSE from the stored open time, not random."""
        assert option_arm_trade_id("NIFTY", NOW) == option_arm_trade_id("NIFTY", NOW)
        assert option_arm_trade_id("NIFTY", NOW) != option_arm_trade_id("BANKNIFTY", NOW)

    def test_recording_is_a_noop_when_the_store_is_unwired(self):
        state = _state()  # no store
        state.record_option_arm_trade_opened("X", OPTION_ARM_DIRECTIONAL, "NIFTY", "r", NOW)
        state.resolve_option_arm_trade_closed("X", 100.0, NOW)  # must not raise
