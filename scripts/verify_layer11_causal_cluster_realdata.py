"""Rule-F real-data verification for Layer 11 slice 3 — the causal-cluster analyst (research/102).

Builds the REAL provider pool from .env and runs the analyst over the REAL experience memory's
multi-hop clusters (temporal dependence + cross-regime calibration + violated assumptions),
printing the falsifiable causal hypotheses it proposes and which provider served them. This is the
actual production path: real cluster facts → real LLM → structured causal hypotheses.

Run:  python scripts/verify_layer11_causal_cluster_realdata.py
Secrets read from the environment only, never printed.
"""

from __future__ import annotations

import os

from nse_algo_trader.broker_credentials.broker_api_credentials_loader import (
    load_env_file_into_environ,
)
from nse_algo_trader.llm_strategy.causal_cluster_analyst import CausalClusterAnalyst
from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
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
        analyst = CausalClusterAnalyst(client, memory)
        facts = analyst.build_grounding_facts()
        print(f"\nGrounding facts ({len(facts)}):")
        for fact in facts:
            print(f"  - {fact}")

        analysis = analyst.analyze()
        if not analysis.generated:
            print(f"\nNOT GENERATED (pool exhausted): {analysis.note}")
            print(f"provider attempts: {attempts}")
            return 1

        print(f"\nCausal hypotheses ({len(analysis.hypotheses)}) — served by {analysis.served_by}:")
        for h in analysis.hypotheses:
            print(f"  • [{h.confidence:.2f}] {h.cluster_label} "
                  f"({', '.join(h.implicated_mechanisms) or '—'})")
            print(f"      cause: {h.suspected_common_cause}")
            print(f"      falsify: {h.falsifiable_prediction}")
        assert analysis.hypotheses, "a real causal analysis should propose at least one hypothesis"
        print(f"\nprovider attempts: {attempts}")
        print("RESULT: PASS")
        return 0
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
