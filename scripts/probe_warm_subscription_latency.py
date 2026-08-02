"""Rule-F real-data pass for B48: prove the warm-persistent subscription client is faster than cold start
on the LIVE subscription. Market-independent (pure LLM), so runnable any time.

Issues N identical structured calls through the real `ClaudeCodeSubscriptionProvider` (warm enabled) and
prints per-call wall time + transport + served-by. Expectation: call #1 pays cold start (subprocess spawn +
connect), calls #2..N reuse the warm subprocess and are markedly faster. Spends a few Haiku calls of
subscription usage. If the OAuth token is expired, it prints the blocker instead of a spurious pass.

Run:  .venv/bin/python scripts/probe_warm_subscription_latency.py [N]
"""

from __future__ import annotations

import sys
import time

from nse_algo_trader.llm_strategy.claude_code_subscription_provider import (
    build_claude_code_subscription_provider,
    subscription_transport_telemetry,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmProviderError,
    StrategyLlmRequest,
)


def main(argv: list[str]) -> int:
    n = int(argv[1]) if len(argv) > 1 else 3
    provider = build_claude_code_subscription_provider()
    if provider is None:
        print("subscription provider disabled (CLAUDE_SUBSCRIPTION_DISABLED) — nothing to probe")
        return 2
    request = StrategyLlmRequest(
        system_instruction="You classify sentiment.",
        user_prompt="Classify the sentiment of: 'the market rallied hard into the close'.",
        response_json_schema={
            "type": "object",
            "properties": {"label": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["label", "confidence"],
        },
        purpose="b48_latency_probe",
    )
    timings: list[float] = []
    for i in range(1, n + 1):
        start = time.monotonic()
        try:
            response = provider.generate_structured(request)
        except LlmProviderError as exc:
            print(f"BLOCKER (Rule F): subscription lane unavailable at probe time — {exc}")
            print("  → re-run after `claude` re-login refreshes the OAuth token.")
            return 3
        elapsed = time.monotonic() - start
        timings.append(elapsed)
        print(
            f"call #{i}: {elapsed:6.2f}s · transport={provider.last_transport:4s} · "
            f"served_by={response.served_by_provider}·{response.served_by_model} · out={response.parsed_output}"
        )
    if len(timings) >= 2:
        cold, warm_best = timings[0], min(timings[1:])
        speedup = cold / warm_best if warm_best > 0 else float("inf")
        print(
            f"\ncold(call#1)={cold:.2f}s · warm-best={warm_best:.2f}s · speedup×{speedup:.1f}"
        )
        print("PASS: warm reuse beat cold start." if warm_best < cold else
              "UNEXPECTED: warm not faster — investigate (harness may have cached the subprocess).")
    # task #1: prove the LIVE transport telemetry the LLM Gateway panel reads climbs on REAL serves,
    # and print the exact label the panel formats from it.
    tele = subscription_transport_telemetry()
    panel_label = f"warm {tele['warm_calls']} · cold {tele['cold_calls']}"
    print(f"\ntelemetry after {tele['total_calls']} real serves: {tele}")
    print(f"panel transport label → {panel_label!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
