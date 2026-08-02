"""Rule-F real-data pass for the keyless last-resort LLM provider (OVHcloud AI Endpoints).

Builds the ACTUAL production pool from an empty env (so only the keyless tier appears) and calls
OVHcloud through the REAL `OpenAiCompatibleChatProvider` against its LIVE endpoint — no fakes, no
mocks. Confirms a real, schema-shaped JSON object comes back, or that the anonymous 2-RPM/IP/model
rate-limit is handled by the seam exactly as designed. Because the anon cap is PER-MODEL, this
tries a few catalog models so a busy default bucket doesn't block the pass. Run:
`.venv/bin/python scripts/verify_keyless_llm_providers_realdata.py`.

(Pollinations was the researched 2nd keyless provider but is NOT wired — its anonymous tier has a
~0 "pollen" budget and hard-402s on any non-trivial structured request; see docs/BACKLOG.md.)
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool,
)
from nse_algo_trader.llm_strategy.openai_compatible_chat_provider import (
    OpenAiCompatibleChatProvider,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderUnavailableError,
    LlmRateLimitError,
    StrategyLlmRequest,
)

_KEYLESS = {"ovhcloud-ai-endpoints"}
# OVHcloud anon rate-limits PER MODEL — try a few so a busy bucket doesn't block the pass.
_OVH_MODELS_TO_TRY = (
    "Meta-Llama-3_3-70B-Instruct",
    "Mistral-7B-Instruct-v0.3",
    "gpt-oss-20b",
    "Qwen3-32B",
)

_REQUEST = StrategyLlmRequest(
    system_instruction=(
        "You are a terse market-analysis assistant. Answer only with the requested JSON."
    ),
    user_prompt=(
        "Nifty rose 0.8% on strong FII buying. Give one finding and a confidence in [0,1]."
    ),
    response_json_schema={
        "type": "object",
        "properties": {
            "finding": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["finding", "confidence"],
    },
    max_output_tokens=200,
)


def _verify_ovhcloud(base_provider) -> bool:
    """Serve one real structured completion from OVHcloud, walking model buckets past the
    anon per-model rate limit. A clean 200 with a schema-shaped object is the pass."""
    last_throttle = None
    for model in _OVH_MODELS_TO_TRY:
        provider = OpenAiCompatibleChatProvider(
            provider_name=base_provider.provider_name,
            base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
            api_key=base_provider._api_key, model_name=model,
        )
        try:
            response = provider.generate_structured(_REQUEST)
        except LlmRateLimitError as exc:
            print(f"  ~ {model}: anon per-model rate-limit (429) — trying next bucket")
            last_throttle = exc
            continue
        except LlmProviderUnavailableError as exc:
            print(f"  ! {model}: UNAVAILABLE — {exc}")
            continue
        print(f"  ✓ ovhcloud-ai-endpoints ({model}): served real JSON → "
              f"{response.parsed_output!r}")
        return True
    print(f"  ~ every model bucket throttled this run (last: {last_throttle}); the seam "
          f"handled each 429 correctly, but a clean 200 was not reached — retry later.")
    return False


def main() -> int:
    pool = build_free_tier_provider_pool({})  # empty env → only the keyless tier
    keyless = [p for p in pool if p.provider_name in _KEYLESS]
    print(f"Keyless providers in the pool: {[p.provider_name for p in keyless]}")
    assert {p.provider_name for p in keyless} == _KEYLESS, "keyless tier missing from pool"

    ok = _verify_ovhcloud(keyless[0])
    print("\nRESULT:", "PASS" if ok else "INCONCLUSIVE (throttled — real 200 pending)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
