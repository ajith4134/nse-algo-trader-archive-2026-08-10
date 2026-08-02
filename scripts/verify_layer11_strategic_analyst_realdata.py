"""Rule-F real-data verification for Layer 11 slice 1 — the memory-grounded strategic analyst
served by the swappable free-tier LLM pool (research/96).

Builds the REAL provider pool from .env, runs the analyst over the REAL §10 experience memory
(the persisted, graded trades), and prints the resulting reflection plus which provider served
it (exercising swap-on-limit failover against live endpoints). This is the actual production
path: real memory facts → real LLM → structured reflection.

Run:  python scripts/verify_layer11_strategic_analyst_realdata.py

Secrets are read from the environment only and never printed.
"""

from __future__ import annotations

import os

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
)
from nse_algo_trader.llm_strategy.memory_grounded_strategy_analyst import (
    MemoryGroundedStrategyAnalyst,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)


def main() -> int:
    load_env_file_into_environ()

    pool = build_free_tier_provider_pool(os.environ)
    print(f"Configured provider pool ({len(pool)}): "
          f"{', '.join(f'{p.provider_name}/{p.model_name}' for p in pool)}")
    if not pool:
        print("BLOCKER: no LLM provider keys present in .env — cannot run real reflection.")
        return 2

    memory = SqliteExperienceMemory()
    try:
        total = memory.experiment_count()
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0:
            print("BLOCKER: experience memory is empty — no real facts to reflect on.")
            return 2

        attempts: list[str] = []
        client = SwappableMultiProviderLlmClient(
            pool,
            on_attempt=lambda name, outcome, detail: attempts.append(
                f"{name}:{outcome}"
            ),
        )
        analyst = MemoryGroundedStrategyAnalyst(client, memory)

        print("\n--- grounding facts fed to the LLM (from real memory) ---")
        for fact in analyst.build_grounding_facts():
            print(f"  - {fact}")

        print("\n--- calling the swappable LLM pool ---")
        reflection = analyst.reflect()
        print(f"attempt trail: {' -> '.join(attempts) or '(none)'}")

        if not reflection.generated:
            print(f"\nBLOCKER (network/quota): every provider was exhausted.\n"
                  f"reason: {reflection.note}")
            print("The seam + failover + grounding are verified; the live LLM call could not "
                  "complete from this environment. Real reflection pass remains OPEN.")
            return 3

        print(f"\nSERVED BY: {reflection.served_by}")
        print("\nFINDINGS:")
        for f in reflection.findings:
            print(f"  - {f}")
        print("HYPOTHESES:")
        for h in reflection.hypotheses:
            print(f"  - {h}")
        print("DISTRUST MECHANISMS:")
        for d in reflection.distrust_mechanisms:
            print(f"  - {d}")

        assert reflection.findings or reflection.hypotheses or reflection.distrust_mechanisms, \
            "reflection came back empty"
        assert any("opening_range" in f or "orb" in f.lower()
                   for f in reflection.grounding_facts), "grounding facts missing real mechanisms"
        print("\nPASS: real memory -> live LLM -> structured reflection verified.")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
