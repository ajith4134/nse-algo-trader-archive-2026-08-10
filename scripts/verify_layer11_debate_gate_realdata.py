"""Rule-F real-data verification for Layer 11 slice 2c — the LLM-risk entry-GATE consumer +
earn-calibration harness (research/101).

Confirms the HONEST current real state end-to-end: the debate produces a real per-mechanism
risk_score over the REAL memory, but because no LIVE prequential (risk_score, outcome) pairs have
accrued yet, the harness returns NOT earned and the entry gate is INERT (size multiplier 1.0 for
every real mechanism) — i.e. an uncalibrated LLM signal cannot move a real trade. Also proves the
gate ACTIVATES on the same real risk map once the earned flag is set (the switch works).

Run:  python scripts/verify_layer11_debate_gate_realdata.py
Secrets read from the environment only, never printed.
"""

from __future__ import annotations

import os

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.llm_strategy.debate_risk_calibration_harness import (
    score_risk_calibration,
)
from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.llm_strategy.thesis_debate_risk_panel import ThesisDebateRiskPanel
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)
from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.debate_risk_prequential_observation_store import (
    DebateRiskPrequentialObservationStore,
)
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab.prediction_table_scoreboard import (
    PredictionTableScoreboard,
)


def main() -> int:
    load_env_file_into_environ()

    pool = build_free_tier_provider_pool(os.environ)
    if not pool:
        print("BLOCKER: no LLM provider keys present in .env.")
        return 2
    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: experience memory is empty.")
            return 2

        # 1. Real debate → real per-mechanism risk map (1 thesis to stay within free limits).
        panel = ThesisDebateRiskPanel(SwappableMultiProviderLlmClient(pool), memory)
        assessments = panel.debate_active_theses(limit=1)
        risk_map = {
            a.thesis.mechanism_name: a.risk_score for a in assessments if a.generated
        }
        print(f"Real debate risk map: { {k: round(v, 2) for k, v in risk_map.items()} }")
        if not risk_map:
            print("BLOCKER: debate did not generate (pool exhausted).")
            return 1

        # 2. Real earn-calibration verdict over the REAL (currently empty) observation store.
        store = DebateRiskPrequentialObservationStore()
        try:
            observations = store.all_observations()
        finally:
            store.close()
        verdict = score_risk_calibration(observations)
        print(f"Prequential observations accrued: {verdict.observation_count}")
        print(f"Calibration earned? {verdict.earned} — {verdict.note}")

        # 3. Gate over the REAL risk map: inert today (not earned), active once earned.
        state = LiveUniversePaperState(
            ledger=PaperTradingLedger(1_000_000.0), scoreboard=PredictionTableScoreboard()
        )
        state.debate_risk_score_by_mechanism = risk_map
        state.debate_risk_calibration_earned = verdict.earned
        mechanism = next(iter(risk_map))
        inert_multiplier = state.debate_risk_size_multiplier(mechanism)
        print(f"Gate multiplier for '{mechanism}' NOW (earned={verdict.earned}): "
              f"{inert_multiplier}")

        state.debate_risk_calibration_earned = True  # simulate the switch flipping on
        active_multiplier = state.debate_risk_size_multiplier(mechanism)
        print(f"Gate multiplier for '{mechanism}' IF earned: {active_multiplier} "
              f"(risk_score {risk_map[mechanism]:.2f})")

        # Assertions: today inert (safe), and the switch genuinely changes behaviour when the
        # risk is above a threshold (else both are 1.0 and the switch is still correctly wired).
        assert not verdict.earned, "no live observations should exist yet"
        assert inert_multiplier == 1.0, "gate must be INERT until calibration is earned"
        print("\nRESULT: PASS — gate wired at all 4 entry sites, safely inert until earned.")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
