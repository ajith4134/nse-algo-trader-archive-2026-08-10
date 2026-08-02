"""The swap-on-limit orchestrator: an ordered pool of LLM providers that automatically
falls over to the next one when the current provider hits its free-tier limit (Layer 11;
research/96). This is the piece the user asked for — "when [a] limit [is] hit you use the
other."

Behaviour:
  * Try providers in configured order, skipping any currently on cooldown.
  * On `LlmRateLimitError` → put that provider on a rate-limit cooldown (honour the
    provider's Retry-After when given) and try the next.
  * On `LlmProviderUnavailableError` / `LlmResponseFormatError` → shorter cooldown, try next.
  * First success returns immediately, recording `served_by` for the dashboard trail.
  * If every provider fails on a call, raise `AllLlmProvidersExhausted` summarising why.

Cooldowns use an INJECTED monotonic clock so tests are deterministic (no real sleeping). The
client is `StrategyLlmClient`-shaped, so callers (the analyst) never see the pool underneath.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmPoolStatus,
    LlmProvider,
    LlmProviderError,
    LlmProviderStatus,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)

MonotonicClock = Callable[[], float]

# Default cooldowns (seconds): a rate-limited provider rests longer than a merely-flaky one.
_DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 90.0
_DEFAULT_FAULT_COOLDOWN_SECONDS = 20.0


class AllLlmProvidersExhausted(LlmProviderError):
    """Every provider in the pool failed (or was cooling down) for one call — the pool has no
    one left to try right now. Carries the per-provider reasons for diagnosis."""

    def __init__(self, failures: dict[str, str]) -> None:
        detail = "; ".join(f"{name}: {why}" for name, why in failures.items()) or "empty pool"
        super().__init__("swappable-pool", f"all providers exhausted ({detail})")
        self.failures = dict(failures)


@dataclass
class _ProviderRuntimeState:
    provider: LlmProvider
    cooldown_until: float = 0.0
    last_served: bool = False


# Observer signature for logging each attempt (provider_name, outcome, detail). Optional.
AttemptObserver = Callable[[str, str, str], None]


class SwappableMultiProviderLlmClient:
    """Round-robins over an ordered provider pool, failing over on limits. Satisfies
    `StrategyLlmClient` so it drops straight into the analyst's DI slot."""

    def __init__(
        self,
        providers: Sequence[LlmProvider],
        monotonic_clock: MonotonicClock | None = None,
        rate_limit_cooldown_seconds: float = _DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        fault_cooldown_seconds: float = _DEFAULT_FAULT_COOLDOWN_SECONDS,
        on_attempt: AttemptObserver | None = None,
    ) -> None:
        self._states = [_ProviderRuntimeState(provider=p) for p in providers]
        self._clock = monotonic_clock or time.monotonic
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._fault_cooldown_seconds = fault_cooldown_seconds
        self._on_attempt = on_attempt
        self._last_served_by = ""

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        now = self._clock()
        failures: dict[str, str] = {}
        for state in self._states:
            provider_name = state.provider.provider_name
            if state.cooldown_until > now:
                failures[provider_name] = (
                    f"cooling down {state.cooldown_until - now:.0f}s"
                )
                continue
            try:
                response = state.provider.generate_structured(request)
            except LlmRateLimitError as exc:
                cooldown = exc.retry_after_seconds or self._rate_limit_cooldown_seconds
                state.cooldown_until = self._clock() + cooldown
                failures[provider_name] = f"rate-limited ({cooldown:.0f}s cooldown)"
                self._observe(provider_name, "rate_limited", str(exc))
                continue
            except (LlmProviderUnavailableError, LlmProviderError) as exc:
                state.cooldown_until = self._clock() + self._fault_cooldown_seconds
                failures[provider_name] = f"fault: {exc}"
                self._observe(provider_name, "fault", str(exc))
                continue
            self._mark_served(state)
            self._observe(provider_name, "served", response.served_by_model)
            return response
        raise AllLlmProvidersExhausted(failures)

    def describe_pool(self) -> LlmPoolStatus:
        now = self._clock()
        statuses = tuple(
            LlmProviderStatus(
                provider_name=s.provider.provider_name,
                model_name=s.provider.model_name,
                cooling_down=s.cooldown_until > now,
                last_served=s.last_served,
            )
            for s in self._states
        )
        return LlmPoolStatus(providers=statuses, last_served_by=self._last_served_by)

    def _mark_served(self, served_state: _ProviderRuntimeState) -> None:
        for state in self._states:
            state.last_served = state is served_state
        self._last_served_by = served_state.provider.provider_name

    def _observe(self, provider_name: str, outcome: str, detail: str) -> None:
        if self._on_attempt is not None:
            self._on_attempt(provider_name, outcome, detail)
