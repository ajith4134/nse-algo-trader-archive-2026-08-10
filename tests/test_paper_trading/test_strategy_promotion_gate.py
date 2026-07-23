import pytest

from nse_algo_trader.paper_trading import (
    StrategyPromotionConfig,
    StrategyPromotionOutcome,
    compute_deflated_sharpe_ratio,
    compute_probabilistic_sharpe_ratio,
    compute_sharpe_ratio,
    evaluate_strategy_for_promotion,
)


class TestSharpe:
    def test_sharpe_of_constant_positive_returns_is_zero_std_guarded(self):
        assert compute_sharpe_ratio([1.0, 1.0, 1.0]) == 0.0

    def test_sharpe_hand_value(self):
        # returns mean 1, sample std 1 -> Sharpe 1.0
        assert compute_sharpe_ratio([0.0, 1.0, 2.0]) == pytest.approx(1.0)

    def test_higher_mean_lower_vol_gives_higher_sharpe(self):
        steady = compute_sharpe_ratio([1.0, 1.1, 0.9, 1.05, 0.95])
        wild = compute_sharpe_ratio([1.0, 5.0, -3.0, 4.0, -2.0])
        assert steady > wild


class TestProbabilisticSharpe:
    def test_psr_rises_with_more_consistent_evidence(self):
        short = compute_probabilistic_sharpe_ratio([0.5, -0.2, 0.6, -0.1, 0.7])
        longer = compute_probabilistic_sharpe_ratio([0.5, -0.2, 0.6, -0.1, 0.7] * 10)
        assert longer > short  # more of the same evidence -> more confident

    def test_psr_in_unit_interval(self):
        psr = compute_probabilistic_sharpe_ratio([0.3, -0.1, 0.4, 0.2, -0.2, 0.5])
        assert 0.0 <= psr <= 1.0


class TestDeflatedSharpe:
    def test_more_trials_deflates_confidence(self):
        returns = [0.4, -0.1, 0.5, 0.2, -0.2, 0.6, 0.1, -0.15, 0.45, 0.3] * 5
        few_trials = compute_deflated_sharpe_ratio(returns, 0.5, 5)
        many_trials = compute_deflated_sharpe_ratio(returns, 0.5, 500)
        assert many_trials < few_trials  # searching harder -> higher bar

    def test_deflated_never_exceeds_undeflated_psr(self):
        returns = [0.4, -0.1, 0.5, 0.2, -0.2, 0.6, 0.1, -0.15, 0.45, 0.3] * 4
        assert compute_deflated_sharpe_ratio(returns, 0.5, 50) <= (
            compute_probabilistic_sharpe_ratio(returns) + 1e-9
        )


class TestPromotionGate:
    def test_too_few_trades_is_rejected_regardless_of_sharpe(self):
        decision = evaluate_strategy_for_promotion(
            [10.0, 12.0, 11.0], number_of_strategy_trials=5,
            sharpe_std_across_trials=0.5,
        )
        assert decision.outcome is StrategyPromotionOutcome.REJECT_INSUFFICIENT_TRADES
        assert not decision.promoted

    def test_weak_edge_with_enough_trades_rejected_on_deflated_sharpe(self):
        # noisy near-zero-edge returns, 50 trades -> DSR far below 0.95
        noisy = [1.0, -1.1, 0.9, -0.8, 1.2, -1.0] * 10
        decision = evaluate_strategy_for_promotion(
            noisy, number_of_strategy_trials=50, sharpe_std_across_trials=0.5,
        )
        assert decision.outcome is StrategyPromotionOutcome.REJECT_DEFLATED_SHARPE_TOO_LOW
        assert not decision.promoted

    def test_strong_consistent_edge_promotes(self):
        # strongly positive, low-vol, many trades, few trials
        strong = [1.0, 1.2, 0.9, 1.1, 1.05, 0.95, 1.15, 0.85] * 8  # 64 trades
        decision = evaluate_strategy_for_promotion(
            strong, number_of_strategy_trials=3, sharpe_std_across_trials=0.3,
            config=StrategyPromotionConfig(minimum_trades=30),
        )
        assert decision.outcome is StrategyPromotionOutcome.PROMOTE_TO_LIVE_CANDIDATE
        assert decision.promoted
        assert decision.deflated_sharpe_ratio >= 0.95
