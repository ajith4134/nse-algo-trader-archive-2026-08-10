"""Rule-F verification for Trunk VII — mechanistic interpretability (research/115). Builds the
decision-attribution report over the REAL §10 memory and prints which internal mechanisms drive the
system's decisions and whether each is trustworthy.

Run:  python scripts/verify_mechanistic_interpretability_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.mechanistic_interpretability import (
    explain_decision_mechanisms,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    report = explain_decision_mechanisms(memory)
    print(f"Mechanistic interpretability over REAL memory ({report.total_experiments} decisions):")
    print(f"  summary: {report.summary}\n")
    for a in report.attributions[:8]:
        tag = "RED FLAG" if a.flag else ("ok" if a.reliable and a.edge_positive else "watch")
        print(f"  {a.mechanism_name:<32} infl {a.influence_share:5.0%} "
              f"cal_err {a.calibration_error:.2f} ret {a.mean_return:+.2%}  [{tag}]")

    assert 0.0 <= report.reliable_share <= 1.0
    print(f"\nRESULT: PASS — real decision-attribution report produced ("
          f"{len(report.attributions)} mechanisms, "
          f"{len(report.red_flags)} red flag(s), reliable share {report.reliable_share:.0%}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
