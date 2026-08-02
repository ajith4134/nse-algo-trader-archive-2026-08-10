"""Rule-F verification for Trunk XV — memory consolidation + semantic memory (research/135).
Consolidates the REAL §10 calibration board into semantic facts and prints the consolidated knowledge
base.

Run:  python scripts/verify_memory_consolidation_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.memory_reflection.memory_consolidation import consolidate_to_semantic
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    board = memory.calibration_board(minimum_experiments=1, limit=50)
    print(f"Real §10 memory: {len(board)} episodic mechanisms on the calibration board")

    sem = consolidate_to_semantic(board)
    print(f"\nSEMANTIC MEMORY (consolidated from REAL episodic experiences):")
    print(f"  {sem.summary}")
    for f in sem.facts:
        print(f"    [conf {f.confidence:.0%}] {f.statement}")

    assert sem is not None
    for f in sem.facts:
        assert f.sample_size >= 15  # only well-supported patterns are consolidated
    print(f"\nRESULT: PASS — {sem.fact_count} stable semantic fact(s) consolidated from the real "
          "episodic memory (thin patterns correctly withheld).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
