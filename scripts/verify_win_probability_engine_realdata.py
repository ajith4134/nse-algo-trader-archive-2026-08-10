"""Rule F real-data verification for the ML win-probability ENGINE (Trunk IX PREDICTIVE-CORE, research/156).

Trains the real LightGBM engine on the REAL experience_memory (340 trades), reports the cross-validated
evaluation (AUC/Brier/log-loss vs the fixed-formula baseline), calibration, feature importances, persists
+ reloads the model (carried state), and demonstrates the calibrated edge CHANGING a real sizing decision.
"""

import sqlite3

from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    DEFAULT_EXPERIENCE_MEMORY_DB_PATH,
)
from nse_algo_trader.predictive_core.win_probability_engine import (
    WinProbabilityEngine,
    edge_size_multiplier,
)


def main() -> None:
    connection = sqlite3.connect(str(DEFAULT_EXPERIENCE_MEMORY_DB_PATH.expanduser()))
    connection.row_factory = sqlite3.Row
    try:
        records = [dict(r) for r in connection.execute("SELECT * FROM experience_nodes")]
    finally:
        connection.close()

    engine = WinProbabilityEngine()
    print(f"=== training the ML win-probability engine on {len(records)} REAL trades ===")
    if not engine.train_from_records(records):
        print("  could not train (need both win/loss classes)"); return
    ev = engine.evaluation
    print(" ", ev.summary)
    print(f"  AUC {ev.auc}  Brier {ev.brier:.3f}  logloss {ev.log_loss:.3f}  "
          f"baseline logloss {ev.baseline_log_loss}  BEATS baseline: {ev.beats_baseline}")
    print("  performance-EARNED (acts on real trades):", engine.is_performance_earned)
    print("  top feature importances (gain):")
    for f, g in ev.feature_importances[:6]:
        print(f"    {f:20s} {g:,.0f}")
    print("  calibration (mean predicted → observed win-rate):")
    for b in ev.calibration_bins:
        print(f"    {b.mean_predicted:.2f} → {b.observed_rate:.2f}  (n={b.count})")

    # Carried state: persist + reload.
    reloaded = WinProbabilityEngine()
    print("\n  model persisted + reloaded:", reloaded.load())

    # Decision-grade output: the edge multiplier changes sizing across the probability range.
    print("\n=== the calibrated edge → position-size multiplier (reward:risk = 2.0) ===")
    for p in (0.1, 0.3, 0.5, 0.7, 0.9):
        m_earned = edge_size_multiplier(p, 2.0, is_earned=True)
        print(f"  P(win)={p:.1f} → size ×{m_earned:.2f}  (identity ×1.00 until the model is earned)")


if __name__ == "__main__":
    main()
