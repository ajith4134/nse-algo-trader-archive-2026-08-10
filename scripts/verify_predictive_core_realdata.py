"""Rule-F verification for Trunk IX — surprise/free-energy monitor + ensemble world-models
(research/134). Runs both over the REAL §10 calibration board and prints the real aggregate surprise
+ most-surprising mechanism, and the real ensemble prediction + disagreement.

Run:  python scripts/verify_predictive_core_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.predictive_core.ensemble_world_model import build_ensemble_forecast
from nse_algo_trader.predictive_core.surprise_monitor import monitor_surprise
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    board = memory.calibration_board(minimum_experiments=1, limit=50)
    print(f"Real §10 memory: {len(board)} mechanisms on the calibration board")

    sr = monitor_surprise(board)
    print("\nSURPRISE / FREE-ENERGY over REAL memory:")
    print(f"  {sr.summary}")
    print(f"  mean_surprise={sr.mean_surprise_bits:.3f} bits · most_surprising={sr.most_surprising} "
          f"({sr.most_surprising_bits:.2f} bits) · spike={sr.spike_detected}")

    ef = build_ensemble_forecast(board)
    print("\nENSEMBLE WORLD-MODELS over REAL memory:")
    print(f"  {ef.summary}")
    print(f"  ensemble_prediction={ef.ensemble_prediction:.1%} disagreement=±{ef.disagreement:.1%} "
          f"members={ef.member_count} high_disagreement={ef.high_disagreement}")

    assert sr is not None and ef is not None
    assert sr.mean_surprise_bits >= 0.0 and 0.0 <= ef.ensemble_prediction <= 1.0
    print("\nRESULT: PASS — surprise monitor + ensemble world-model produced real predictive-core "
          "verdicts over the real §10 memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
