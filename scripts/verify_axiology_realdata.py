"""Rule F real-data verification for Trunk XIV AXIOLOGY (research/153).

Reads the REAL realized-return series from the experience memory (340 real trades) and shows the
explicit utility decomposition + the value-drift verdict — proving the axiology organs run on the
actual data they will operate on.
"""

import sqlite3

from nse_algo_trader.axiology.explicit_utility_function import ValueWeights, evaluate_utility
from nse_algo_trader.axiology.value_drift_monitor import detect_value_drift
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
)


def main() -> None:
    connection = sqlite3.connect(str(DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()))
    try:
        returns = [r[0] for r in connection.execute(
            "SELECT realized_return_fraction FROM experience_nodes "
            "WHERE realized_return_fraction IS NOT NULL ORDER BY occurred_at").fetchall()]
    finally:
        connection.close()

    print(f"=== REAL realized-return series: {len(returns)} trades ===")
    u = evaluate_utility(returns)
    print("EXPLICIT UTILITY (default capital-preservation weights):")
    print(" ", u.summary)
    print(f"  decomposition: return {u.return_term:+.4f} | risk {u.risk_term:+.4f} | "
          f"drawdown {u.drawdown_term:+.4f} | tail {u.tail_term:+.4f}")

    print("\nSame series under RETURN-MAXIMISING values (w_drawdown=w_tail=0):")
    print(" ", evaluate_utility(returns, ValueWeights(w_risk=0.0, w_drawdown=0.0, w_tail=0.0)).summary)

    d = detect_value_drift(returns)
    print("\nVALUE DRIFT verdict:")
    print(" ", "DRIFTING" if d.is_drifting else "STABLE", "|", d.summary)


if __name__ == "__main__":
    main()
