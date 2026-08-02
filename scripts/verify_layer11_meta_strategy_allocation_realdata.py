"""Rule-F real-data verification for Layer 11 slice 4 — the meta-strategy allocator (research/103).

Builds the REAL provider pool from .env and runs the allocator over the REAL experience memory's
per-strategy performance + the REAL champion store, printing the normalised allocation weights it
proposes across the three strategies and which provider served them. Production path: real
per-strategy facts → real LLM → normalised allocation.

Run:  python scripts/verify_layer11_meta_strategy_allocation_realdata.py
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
from nse_algo_trader.llm_strategy.meta_strategy_allocator import MetaStrategyAllocator
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)
from nse_algo_trader.paper_trading.champion_configuration_store import (
    ChampionConfigurationStore,
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
        allocator = MetaStrategyAllocator(client, memory, ChampionConfigurationStore())
        facts = allocator.build_grounding_facts()
        print(f"\nGrounding facts ({len(facts)}):")
        for fact in facts:
            print(f"  - {fact}")

        allocation = allocator.allocate()
        if not allocation.generated:
            print(f"\nNOT GENERATED (pool exhausted): {allocation.note}")
            print(f"provider attempts: {attempts}")
            return 1

        print(f"\nMeta-strategy allocation — served by {allocation.served_by}:")
        for w in sorted(allocation.weights, key=lambda w: w.weight, reverse=True):
            print(f"  {w.weight:6.1%}  {w.strategy_tag}")
            print(f"          {w.rationale}")
        print(f"  overall: {allocation.overall_rationale}")

        weight_sum = sum(w.weight for w in allocation.weights)
        assert allocation.weights, "a real allocation should weight at least one strategy"
        assert abs(weight_sum - 1.0) < 1e-6, f"weights must sum to 1 (got {weight_sum})"
        print(f"\nweights sum to {weight_sum:.4f}  ·  provider attempts: {attempts}")
        print("RESULT: PASS")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
