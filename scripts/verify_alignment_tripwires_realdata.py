"""Rule-F verification for Trunk VII.10+11 — alignment tripwires (research/112). Runs the
wireheading + deceptive-alignment tripwires over the REAL §10 memory and prints the verdicts. On
this data, per-mechanism wireheading flags are expected on the known high-win/negative-return
mechanisms; systemic + deceptive are likely clear (overall return is positive).

Run:  python scripts/verify_alignment_tripwires_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.alignment_tripwires import (
    deceptive_alignment_monitor,
    wireheading_tripwire,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: memory empty.")
            return 2

        wire = wireheading_tripwire(memory)
        print("\nWIREHEADING tripwire:")
        print(f"  tripped={wire.tripped} · severity={wire.severity}")
        print(f"  flagged: {list(wire.flagged) or '—'}")
        print(f"  {wire.detail}")

        deceptive = deceptive_alignment_monitor(memory)
        print("\nDECEPTIVE-ALIGNMENT monitor:")
        print(f"  tripped={deceptive.tripped} · severity={deceptive.severity}")
        print(f"  {deceptive.detail}")

        # both must produce a coherent verdict; a CRITICAL trip would engage corrigibility in the loop
        assert wire.severity in {"clear", "warning", "critical"}
        assert deceptive.severity in {"clear", "warning", "critical"}
        print("\nRESULT: PASS — alignment tripwires evaluated over the real memory.")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
