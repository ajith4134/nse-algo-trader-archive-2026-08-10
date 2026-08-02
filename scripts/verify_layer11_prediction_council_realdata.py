"""Rule-F real-data verification for Layer 11 slice 5 — the prediction-market council (research/104).

Builds the REAL provider pool from .env and runs the council over the REAL experience memory: each
role forecasts a probability on a real proposition (the most-active mechanism wins its next trade),
aggregated with track-record weights. With an empty reputation ledger the weighted probability
equals the simple mean (honest un-tilted state). Production path: real facts → real role
forecasts → track-record-weighted aggregate.

Run:  python scripts/verify_layer11_prediction_council_realdata.py
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
from nse_algo_trader.llm_strategy.prediction_council import PredictionCouncil
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.memory_reflection.sqlite_experience_memory import (
    SqliteExperienceMemory,
)
from nse_algo_trader.paper_trading.council_track_record_store import (
    CouncilTrackRecordStore,
)


def main() -> int:
    load_env_file_into_environ()

    pool = build_free_tier_provider_pool(os.environ)
    print(f"Configured provider pool ({len(pool)}): {', '.join(p.provider_name for p in pool)}")
    if not pool:
        print("BLOCKER: no LLM provider keys present in .env.")
        return 2

    memory = SqliteExperienceMemory()
    store = CouncilTrackRecordStore()
    try:
        total = memory.experiment_count()
        board = memory.calibration_board(minimum_experiments=1, limit=1)
        print(f"Real experience memory: {total} graded experiences.")
        if total == 0 or not board:
            print("BLOCKER: memory empty / no mechanism to forecast.")
            return 2
        mechanism = board[0].mechanism_name
        print(f"Resolved forecasts accrued: {store.resolved_forecast_count()}")

        attempts: list[str] = []
        client = SwappableMultiProviderLlmClient(
            pool, on_attempt=lambda name, outcome, detail: attempts.append(f"{name}:{outcome}")
        )
        council = PredictionCouncil(client, memory, track_record_store=store)
        forecast = council.forecast(
            proposition_label=f"{mechanism} wins its next trade",
            proposition_question=(
                f"Will mechanism '{mechanism}' WIN its next trade, given its real track record?"
            ),
        )
        if not forecast.generated:
            print(f"\nNOT GENERATED (pool exhausted): {forecast.note}")
            print(f"provider attempts: {attempts}")
            return 1

        print(f"\nProposition: {forecast.proposition_label} — served by {forecast.served_by}")
        for m in forecast.member_forecasts:
            print(f"  {m.role:>15}: P={m.probability:.2f}  (weight {forecast.weight_by_role[m.role]:.2f})")
            print(f"                   {m.rationale[:90]}")
        print(f"  weighted P = {forecast.weighted_probability:.1%}  ·  "
              f"simple mean = {forecast.simple_mean_probability:.1%}  ·  "
              f"reputation-tilted = {forecast.is_reputation_tilted}")

        assert len(forecast.member_forecasts) == 4
        if store.resolved_forecast_count() == 0:
            assert abs(forecast.weighted_probability - forecast.simple_mean_probability) < 1e-6, (
                "with no reputations, weighted must equal simple mean"
            )
        print(f"\nprovider attempts: {attempts}")
        print("RESULT: PASS")
        return 0
    finally:
        store.close()
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
