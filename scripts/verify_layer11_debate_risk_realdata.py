"""Rule-F real-data verification for Layer 11 slice 2 — the debate-as-risk-check panel
(research/100). Builds the REAL provider pool from .env, derives the active theses from the
REAL §10 calibration memory, and runs the bull/bear/risk debate through the live swappable
pool — the actual production path: real memory facts → three real LLM roles → risk_score.

Run:  python scripts/verify_layer11_debate_risk_realdata.py
Secrets are read from the environment only and never printed. Debates ONE thesis by default to
stay within free-tier limits (3 role calls); pass an int arg to debate more.
"""

from __future__ import annotations

import os
import sys

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
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


def main() -> int:
    load_env_file_into_environ()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    pool = build_free_tier_provider_pool(os.environ)
    print(f"Configured provider pool ({len(pool)}): "
          f"{', '.join(p.provider_name for p in pool)}")
    if not pool:
        print("BLOCKER: no LLM provider keys present in .env — cannot run a real debate.")
        return 2

    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: experience memory is empty — no real theses to debate.")
            return 2

        attempts: list[str] = []
        client = SwappableMultiProviderLlmClient(
            pool, on_attempt=lambda name, outcome, detail: attempts.append(f"{name}:{outcome}")
        )
        panel = ThesisDebateRiskPanel(client, memory)
        theses = panel.theses_from_calibration_board(limit=limit)
        if not theses:
            print("BLOCKER: no active theses on the calibration board yet.")
            return 2

        all_ok = True
        for thesis in theses:
            print(f"\n=== Debating: {thesis.mechanism_name} (strategy {thesis.strategy_tag}) ===")
            assessment = panel.debate(thesis)
            if not assessment.generated:
                print(f"  NOT GENERATED (pool exhausted): {assessment.note}")
                all_ok = False
                continue
            for verdict in assessment.verdicts:
                print(f"  {verdict.role:>12}: soundness={verdict.soundness:.2f} "
                      f"main_risk={verdict.main_risk[:80]!r}")
            print(f"  → disagreement={assessment.disagreement_score:.2f} "
                  f"adverse={assessment.adverse_conviction:.2f} "
                  f"RISK_SCORE={assessment.risk_score:.2f}")
            print(f"  served by: {assessment.served_by}")
            # sanity: real three-role debate with a bounded risk_score
            assert len(assessment.verdicts) == 3
            assert 0.0 <= assessment.risk_score <= 1.0

        print(f"\nprovider attempts: {attempts}")
        print("RESULT:", "PASS" if all_ok else "FAIL")
        return 0 if all_ok else 1
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
