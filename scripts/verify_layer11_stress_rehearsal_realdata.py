"""Rule-F real-data verification for Layer 11 slice 6 — the synthetic stress-scenario generator
(research/105). Builds the REAL provider pool from .env and runs the generator over the REAL
experience memory's weakness surface, printing the adversarial stress scenarios it red-teams and
which provider served them. Production path: real weaknesses → real LLM → structured scenarios.

Run:  python scripts/verify_layer11_stress_rehearsal_realdata.py
Secrets read from the environment only, never printed.
"""

from __future__ import annotations

import os

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.llm_strategy.synthetic_stress_rehearsal import (
    SyntheticStressScenarioGenerator,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    load_env_file_into_environ()

    pool = build_free_tier_provider_pool(os.environ)
    print(f"Configured provider pool ({len(pool)}): {', '.join(p.provider_name for p in pool)}")
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

        attempts: list[str] = []
        client = SwappableMultiProviderLlmClient(
            pool, on_attempt=lambda name, outcome, detail: attempts.append(f"{name}:{outcome}")
        )
        generator = SyntheticStressScenarioGenerator(client, memory)
        facts = generator.build_grounding_facts()
        print(f"\nWeakness-surface grounding facts ({len(facts)}):")
        for fact in facts:
            print(f"  - {fact}")

        rehearsal = generator.generate()
        if not rehearsal.generated:
            print(f"\nNOT GENERATED (pool exhausted): {rehearsal.note}")
            print(f"provider attempts: {attempts}")
            return 1

        print(f"\nStress scenarios ({len(rehearsal.scenarios)}) — served by {rehearsal.served_by}:")
        for s in sorted(rehearsal.scenarios, key=lambda s: s.severity, reverse=True):
            print(f"  • [{s.severity:.2f}] {s.scenario_label} → targets {s.targeted_mechanism}")
            print(f"      condition: {s.market_condition}")
            print(f"      failure:   {s.predicted_failure_mode}")
            print(f"      mitigate:  {s.mitigation}")
        assert rehearsal.scenarios, "a real rehearsal should generate at least one scenario"
        print(f"\nprovider attempts: {attempts}")
        print("RESULT: PASS")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
