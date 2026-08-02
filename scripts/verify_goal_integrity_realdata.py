"""Rule-F verification for Trunk VII — the goal-integrity monitor (research/114). Assesses whether
the DECLARED objective (risk-adjusted RETURN within defined risk) is still the EFFECTIVE objective
over the REAL §10 memory, and prints the verdict. On the known real data (positive aggregate return)
the expected result is ALIGNED — an honest all-clear from a real detector.

Run:  python scripts/verify_goal_integrity_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.goal_integrity_monitor import assess_goal_integrity
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    board = memory.calibration_board(minimum_experiments=1, limit=50)
    print(f"Real §10 memory: {len(board)} mechanisms on the calibration board")

    verdict = assess_goal_integrity(memory)
    print("\nGoal-integrity verdict over REAL memory:")
    print(f"  aligned        : {verdict.aligned}")
    print(f"  integrity_score: {verdict.integrity_score:.3f}")
    print(f"  severity       : {verdict.severity}")
    print(f"  drift_flags    : {verdict.drift_flags or '(none)'}")
    print(f"  detail         : {verdict.detail}")

    # The monitor must return a real, structurally-valid verdict over the real data.
    assert verdict.severity in {"clear", "warning", "critical"}
    assert 0.0 <= verdict.integrity_score <= 1.0
    print("\nRESULT: PASS — the goal-integrity monitor produced a real verdict over the real memory "
          f"({'ALIGNED' if verdict.aligned else 'DRIFT: ' + ', '.join(verdict.drift_flags)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
