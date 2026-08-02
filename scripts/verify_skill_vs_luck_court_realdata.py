"""Rule-F real-data verification for Layer 7.5 slice 2 — the SHADOW-REJECTED arm + skill-vs-luck
court (research/106). Over the REAL experience memory + real veto set, splits mechanisms into
taken vs shadow-rejected (vetoed), then convenes the court using the real RANDOM-CONTROL comparison
(slice 1) over the real stored sessions. Prints both arms + the combined verdict.

Run:  python scripts/verify_skill_vs_luck_court_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.memory_reflection import vetoed_mechanisms
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
)
from nse_algo_trader.paper_trading.control_arm_comparison import compare_control_arms
from nse_algo_trader.paper_trading.shadow_rejected_arm import analyze_shadow_rejected_arm
from nse_algo_trader.paper_trading.skill_vs_luck_court import convene_skill_vs_luck_court

# Reuse the slice-1 real session loader.
from verify_control_arms_realdata import _load_stored_sessions  # type: ignore


def main() -> int:
    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: experience memory is empty.")
            return 2

        vetoed = vetoed_mechanisms(memory)
        print(f"Vetoed mechanisms (the gate refuses): {sorted(vetoed) or '(none)'}")
        shadow = analyze_shadow_rejected_arm(memory, vetoed)
        for arm in (shadow.taken, shadow.shadow_rejected):
            print(f"  {arm.arm_name:>26}: {arm.mechanisms} mechs · {arm.experiments} exp · "
                  f"win {arm.win_rate:.0%} · mean {arm.mean_return:+.2%}")
        print(f"  rejection verdict: {shadow.detail}")

        sessions = _load_stored_sessions()
        if not sessions:
            print("BLOCKER: no stored sessions for the control-arm comparison.")
            return 2
        champion = ChampionConfigurationStore().load_champion_or_default()
        comparison = compare_control_arms(sessions, champion)

        verdict = convene_skill_vs_luck_court(comparison, shadow)
        print(f"\n  directional skill: {verdict.directional_skill} — {verdict.directional_detail}")
        print(f"  rejection skill:   {verdict.rejection_skill} — {verdict.rejection_detail}")
        print(f"\n  COURT VERDICT: {verdict.overall_verdict}")
        print(f"  {verdict.skill_diagonal_note}")

        assert isinstance(verdict.directional_skill, bool)
        print("\nRESULT: PASS")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
