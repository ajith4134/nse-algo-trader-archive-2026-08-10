"""Rule-F verification for Trunk XIII — contradiction resolution + misinformation resistance
(research/132). Runs both over the REAL §10 memory (regime cohorts + calibration board) and prints
the real contradictions across regimes and the real source-credibility ranking.

Run:  python scripts/verify_epistemic_defense_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.epistemics.contradiction_resolver import resolve_contradictions
from nse_algo_trader.epistemics.misinformation_resistance import assess_source_credibility
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    cohorts = memory.calibration_by_market_regime(minimum_experiments=1)
    board = memory.calibration_board(minimum_experiments=1, limit=50)
    print(f"Real §10 memory: {len(cohorts)} regime cohorts, {len(board)} mechanisms")

    cr = resolve_contradictions(cohorts)
    print("\nCONTRADICTION RESOLUTION over REAL memory:")
    print(f"  {cr.summary}")
    for c in cr.contradictions[:5]:
        print(f"    {c.regime:<12} regime {c.regime_hit_rate:.0%} vs global {c.global_hit_rate:.0%} "
              f"(z={c.z_score:+.2f}, p={c.p_value:.3f}) → {c.resolution[:60]}")

    mr = assess_source_credibility(board)
    print("\nMISINFORMATION RESISTANCE over REAL memory:")
    print(f"  {mr.summary}")
    for s in mr.sources[:6]:
        tag = "OVER-TRUSTED" if s.is_over_trusted else "ok"
        print(f"    {s.source[:34]:<34} rep {s.reputation:.0%} infl {s.influence:.0%} [{tag}]")

    assert cr is not None and mr is not None
    assert 0.0 <= mr.mean_reputation <= 1.0
    print("\nRESULT: PASS — contradiction resolution + misinformation resistance produced real "
          "epistemic verdicts over the real §10 memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
