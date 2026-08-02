"""Rule F real-data verification for Trunk III WILL — arbitration + scheduler (research/154).

Builds each real mechanism's multi-objective profile (utility [XIV] · return · −risk · confidence) from
the experience memory, arbitrates + schedules — proving the WILL organs resolve the real objective
conflict (the thin high-return credit-spread vs the confident-but-flat mechanisms) on actual data.
"""

import collections
import sqlite3

from nse_algo_trader.axiology.explicit_utility_function import evaluate_utility
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
)
from nse_algo_trader.will.goal_priority_scheduler import schedule_goals
from nse_algo_trader.will.multi_objective_arbitration import (
    ObjectiveProfile,
    arbitrate,
    confidence_from_sample,
)


def main() -> None:
    connection = sqlite3.connect(str(DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()))
    try:
        rows = connection.execute(
            "SELECT mechanism_name, realized_return_fraction FROM experience_nodes "
            "WHERE realized_return_fraction IS NOT NULL AND mechanism_name IS NOT NULL").fetchall()
    finally:
        connection.close()

    by_mechanism = collections.defaultdict(list)
    for mechanism, ret in rows:
        by_mechanism[mechanism].append(ret)

    profiles = []
    for mechanism, rets in by_mechanism.items():
        u = evaluate_utility(rets)
        profiles.append(ObjectiveProfile(
            mechanism=mechanism, utility=u.utility, mean_return=u.mean_return, neg_risk=-u.volatility,
            confidence=confidence_from_sample(len(rets)), sample_size=len(rets)))

    result = arbitrate(profiles)
    print(f"=== REAL multi-objective arbitration ({len(profiles)} mechanisms) ===")
    print(" ", result.summary)
    print(f"  {'score':>7s} {'PARETO':>7s} {'n':>4s}  {'util':>7s} {'ret':>7s} {'conf':>5s}  mechanism")
    for a in result.ranked:
        p = a.profile
        print(f"  {a.arbitration_score:+7.3f} {'  yes' if a.is_non_dominated else '   no':>7s} "
              f"{p.sample_size:4d}  {p.utility:+7.2f} {p.mean_return:+7.2%} {p.confidence:5.2f}  {a.mechanism[:40]}")

    schedule = schedule_goals(result, max_concurrent=3)
    print("\n=== REAL goal-priority schedule (budget 3) ===")
    print(" ", schedule.summary)
    for g in schedule.goals:
        print(f"  #{g.priority_rank} {'PURSUE' if g.is_active else 'defer '}  {g.mechanism[:44]}")


if __name__ == "__main__":
    main()
