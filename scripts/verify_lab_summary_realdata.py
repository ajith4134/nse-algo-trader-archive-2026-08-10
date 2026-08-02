"""Rule-F real-data verification for Layer 7.5 slice 4 — profit provenance + world-model
scoreboard (research/108). Over the real arms + real memory, decomposes the P&L vs the control
arms and grades the trade-independent world model.

Run:  python scripts/verify_lab_summary_realdata.py
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
from nse_algo_trader.paper_trading.profit_provenance import decompose_profit_provenance
from nse_algo_trader.paper_trading.shadow_rejected_arm import analyze_shadow_rejected_arm
from nse_algo_trader.paper_trading.world_model_scoreboard import score_world_model

from verify_control_arms_realdata import _load_stored_sessions  # type: ignore


def main() -> int:
    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: experience memory is empty.")
            return 2

        # World-model scoreboard (trade-independent).
        wm = score_world_model(memory)
        print("\nWORLD-MODEL SCOREBOARD:")
        print(f"  forecast log-loss = {wm.forecast_log_loss_bits} bits · Brier {wm.forecast_brier}")
        print(f"  regime resolution = {wm.regime_resolution}")
        print(f"  informative? {wm.world_model_informative}")
        print(f"  verdict: {wm.verdict}")

        # Profit provenance (needs the control arms).
        sessions = _load_stored_sessions()
        if not sessions:
            print("BLOCKER: no stored sessions for the control-arm comparison.")
            return 2
        champion = ChampionConfigurationStore().load_champion_or_default()
        comparison = compare_control_arms(sessions, champion)
        shadow = analyze_shadow_rejected_arm(memory, vetoed_mechanisms(memory))
        prov = decompose_profit_provenance(comparison, shadow)
        print("\nPROFIT PROVENANCE:")
        print(f"  total real return  = {prov.total_real_return:+.1%}")
        print(f"  luck baseline      = {prov.luck_baseline:+.1%}")
        print(f"  directional skill  = {prov.directional_skill:+.1%}")
        print(f"  gate saved/refused = {prov.gate_avoided_loss_per_trade}")
        print(f"  dominant source    = {prov.dominant_source}")
        print(f"  detail: {prov.detail}")

        # luck + directional skill must reconstruct the total
        assert abs((prov.luck_baseline + prov.directional_skill) - prov.total_real_return) < 1e-9
        print("\nRESULT: PASS")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
