import math

import pytest

from nse_algo_trader.paper_trading import (
    CpcvConfig,
    StrategyPromotionConfig,
    StrategyPromotionOutcome,
    compute_cpcv_backtest_path_sharpes,
    evaluate_strategy_with_cpcv_gate,
    partition_returns_into_groups,
)


class TestPartition:
    def test_even_partition(self):
        groups = partition_returns_into_groups(list(range(12)), 6)
        assert len(groups) == 6 and all(len(g) == 2 for g in groups)

    def test_uneven_partition_front_loads_remainder(self):
        groups = partition_returns_into_groups(list(range(13)), 6)
        assert [len(g) for g in groups] == [3, 2, 2, 2, 2, 2]

    def test_too_few_returns_raises(self):
        with pytest.raises(ValueError):
            partition_returns_into_groups([1.0, 2.0], 6)


class TestCpcvPaths:
    def test_number_of_paths_is_c_n_k(self):
        returns = [0.1 * ((-1) ** i) + 0.05 for i in range(60)]
        paths = compute_cpcv_backtest_path_sharpes(
            returns, CpcvConfig(group_count=6, test_group_count=2, embargo_group_count=0)
        )
        # C(6,2) = 15 combinations
        assert len(paths) == 15

    def test_embargo_does_not_corrupt_the_oos_path(self):
        # research/41 fix: for a label-free realized-returns series there is
        # nothing to purge, so the embargo must NOT drop test-group returns
        # from the OOS path — the trial distribution stays intact.
        returns = [0.1 * ((-1) ** i) + 0.05 for i in range(60)]
        no_embargo = compute_cpcv_backtest_path_sharpes(
            returns, CpcvConfig(6, 2, embargo_group_count=0)
        )
        with_embargo = compute_cpcv_backtest_path_sharpes(
            returns, CpcvConfig(6, 2, embargo_group_count=1)
        )
        assert with_embargo == no_embargo  # embargo is a no-op on OOS paths


class TestCpcvGate:
    def test_strong_edge_promotes_via_cpcv(self):
        # consistently positive, low-vol returns across the whole series
        strong = [1.0, 1.1, 0.9, 1.05, 0.95, 1.15, 0.85, 1.0] * 10  # 80 obs
        decision = evaluate_strategy_with_cpcv_gate(
            strong, CpcvConfig(group_count=6, test_group_count=2),
            StrategyPromotionConfig(minimum_trades=30),
        )
        assert decision.outcome is StrategyPromotionOutcome.PROMOTE_TO_LIVE_CANDIDATE
        assert decision.deflated_sharpe_ratio >= 0.95

    def test_noisy_edge_rejected_via_cpcv(self):
        noisy = [1.0, -1.1, 0.9, -0.8, 1.2, -1.0] * 12  # ~zero edge, 72 obs
        decision = evaluate_strategy_with_cpcv_gate(
            noisy, CpcvConfig(6, 2), StrategyPromotionConfig(minimum_trades=30)
        )
        assert decision.outcome is StrategyPromotionOutcome.REJECT_DEFLATED_SHARPE_TOO_LOW

    def test_too_few_trades_rejected(self):
        decision = evaluate_strategy_with_cpcv_gate(
            [1.0, 1.1, 0.9, 1.05, 0.95, 1.15, 0.85, 1.0],  # 8 < 30 min
            CpcvConfig(6, 2), StrategyPromotionConfig(minimum_trades=30),
        )
        assert decision.outcome is StrategyPromotionOutcome.REJECT_INSUFFICIENT_TRADES
