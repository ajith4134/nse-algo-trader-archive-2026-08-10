"""Hermetic tests for the warm-persistent subscription session + the cap→fallback pool behaviour (B48).

The DI seam: a FAKE `ClaudeSDKClient` and a dict `options_factory` are injected so we exercise the real
threading / `anyio` portal / per-call session isolation / reconnect / permanent-death state machine WITHOUT
spending subscription usage (Rule J). The real-data latency pass is a separate one-off script (Rule F).
"""

from __future__ import annotations

import json

import pytest

from nse_algo_trader.llm_strategy import claude_code_subscription_provider as sub_mod
from nse_algo_trader.llm_strategy.claude_code_subscription_provider import (
    ClaudeCodeSubscriptionProvider,
    _extract_text_and_model,
    _shared_warm_session_for,
    build_claude_code_subscription_provider,
    subscription_transport_telemetry,
)
from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmRateLimitError,
    StrategyLlmRequest,
    StrategyLlmResponse,
)
from nse_algo_trader.llm_strategy.swappable_multi_provider_llm_client import (
    SwappableMultiProviderLlmClient,
)
from nse_algo_trader.llm_strategy.warm_claude_subscription_session import (
    WarmClaudeSubscriptionSession,
    WarmSessionUnavailable,
)

# ---- fake SDK message objects (shape read by _extract_text_and_model) --------------------------------


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistant:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeResult:
    def __init__(self, model: str) -> None:
        self.content = []
        self.usage = {"lane": {"canonicalModel": model}}


class _FakeClient:
    """A stand-in `ClaudeSDKClient`. Records connects/queries; can be scripted to die on its first query
    (a transport death) to drive the reconnect path. `receive_response` echoes the last prompt so tests can
    prove which session_id/prompt produced which answer."""

    def __init__(self, options, *, log: dict, die_on_query: bool = False) -> None:
        self.options = options
        self._log = log
        self._die_on_query = die_on_query
        self._last_prompt = ""
        self.model = options.get("model") if isinstance(options, dict) else None
        log.setdefault("clients", []).append(self)
        self.connects = 0

    async def connect(self) -> None:
        self.connects += 1
        self._log["connects"] = self._log.get("connects", 0) + 1

    async def disconnect(self) -> None:
        self._log["disconnects"] = self._log.get("disconnects", 0) + 1

    async def set_model(self, model) -> None:
        self.model = model

    async def query(self, prompt, session_id: str = "default") -> None:
        self._log.setdefault("queries", []).append((prompt, session_id))
        if self._die_on_query:
            raise ConnectionError("simulated transport death")
        self._last_prompt = prompt

    async def receive_response(self):
        yield _FakeAssistant(json.dumps({"echo": self._last_prompt}))
        yield _FakeResult("claude-haiku-4-5")


def _session(client_factory, **kw) -> WarmClaudeSubscriptionSession:
    return WarmClaudeSubscriptionSession(
        "claude-haiku-4-5",
        client_factory=client_factory,
        options_factory=lambda model: {"model": model},
        connect_timeout_s=5,
        request_timeout_s=5,
        **kw,
    )


def _run(session: WarmClaudeSubscriptionSession, prompt: str = "hi"):
    return session.run_structured("sys", prompt, "claude-haiku-4-5", _extract_text_and_model)


# ---- tests ------------------------------------------------------------------------------------------


def test_warm_connects_once_and_reuses_the_subprocess() -> None:
    log: dict = {}
    session = _session(lambda opts: _FakeClient(opts, log=log))
    try:
        _run(session, "one")
        _run(session, "two")
        _run(session, "three")
        assert log["connects"] == 1  # ONE connect for three calls — the warm subprocess is reused
        assert len(log["clients"]) == 1
        assert len(log["queries"]) == 3
    finally:
        session.close()


def test_each_call_uses_a_distinct_session_id_no_context_bleed() -> None:
    log: dict = {}
    session = _session(lambda opts: _FakeClient(opts, log=log))
    try:
        _run(session, "alpha")
        _run(session, "beta")
        session_ids = [sid for _prompt, sid in log["queries"]]
        assert len(session_ids) == len(set(session_ids)) == 2  # isolated sessions, no shared context
    finally:
        session.close()


def test_returned_text_and_model_are_extracted() -> None:
    log: dict = {}
    session = _session(lambda opts: _FakeClient(opts, log=log))
    try:
        text, model = _run(session, "payload-xyz")
        assert "payload-xyz" in text  # the echoed prompt proves the round-trip
        assert model == "claude-haiku-4-5"
    finally:
        session.close()


def test_transport_death_reconnects_once_then_succeeds() -> None:
    log: dict = {}
    made: list[int] = []

    def factory(opts):
        made.append(1)
        # first client dies on query; the reconnect builds a second, healthy client
        return _FakeClient(opts, log=log, die_on_query=len(made) == 1)

    session = _session(factory, max_reconnects=1)
    try:
        text, model = _run(session, "survive")
        assert "survive" in text
        assert len(made) == 2  # original + one reconnect
        assert log.get("disconnects", 0) >= 1  # the dead client was torn down
    finally:
        session.close()


def test_permanent_transport_death_raises_warm_unavailable_for_cold_fallback() -> None:
    log: dict = {}
    session = _session(
        lambda opts: _FakeClient(opts, log=log, die_on_query=True), max_reconnects=1
    )
    try:
        with pytest.raises(WarmSessionUnavailable):
            _run(session, "doomed")
    finally:
        session.close()


def test_connect_failure_disables_warm_for_the_process() -> None:
    def failing_factory(opts):
        class _Dead(_FakeClient):
            async def connect(self):  # connect never succeeds
                raise ConnectionError("cannot reach CLI")

        return _Dead(opts, log={})

    session = _session(failing_factory)
    try:
        with pytest.raises(WarmSessionUnavailable):
            _run(session, "first")
        # second call must fail FAST (disabled), still WarmSessionUnavailable → provider stays on cold
        with pytest.raises(WarmSessionUnavailable):
            _run(session, "second")
    finally:
        session.close()


# ---- cap → fail-over through the REAL swappable pool (the B48 integration criterion) ----------------


class _CappedProvider:
    provider_name = "claude-code-subscription"
    model_name = "claude-haiku-4-5"

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        raise LlmRateLimitError(self.provider_name, "subscription capped: usage limit reached")


class _HealthyFallbackProvider:
    provider_name = "groq"
    model_name = "llama-3.3-70b"

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        return StrategyLlmResponse(
            parsed_output={"ok": True},
            served_by_provider=self.provider_name,
            served_by_model=self.model_name,
            raw_text="{}",
        )


# ---- B48 task #1: shared warm-session singleton + live transport telemetry -------------------------


class _FakeWarmSession:
    """A warm session that always serves via 'warm' without any subprocess."""

    def run_structured(self, system_instruction, user_prompt, model, extract):
        return json.dumps({"ok": True}), "claude-haiku-4-5"


def test_shared_warm_session_is_a_process_singleton() -> None:
    # reset the module singleton so the assertion is about identity, not prior test state
    sub_mod._shared_warm_session = None
    first = _shared_warm_session_for("claude-haiku-4-5")
    second = _shared_warm_session_for("claude-haiku-4-5")
    try:
        assert first is second  # ONE warm subprocess process-wide, reused by every provider instance
    finally:
        first.close()
        sub_mod._shared_warm_session = None


def _request() -> StrategyLlmRequest:
    return StrategyLlmRequest(
        system_instruction="s", user_prompt="u", response_json_schema={"type": "object"}
    )


def test_telemetry_records_a_warm_serve() -> None:
    before = subscription_transport_telemetry()["warm_calls"]
    provider = ClaudeCodeSubscriptionProvider(warm_session=_FakeWarmSession())
    provider.generate_structured(_request())
    after = subscription_transport_telemetry()
    assert provider.last_transport == "warm"
    assert after["warm_calls"] == before + 1  # the REAL serve was counted for the live panel


def test_telemetry_records_a_cold_serve() -> None:
    async def _fake_query(prompt, options):  # one-shot cold path (no warm subprocess)
        class _Msg:
            content = [type("B", (), {"text": json.dumps({"ok": True})})()]

        yield _Msg()

    before = subscription_transport_telemetry()["cold_calls"]
    # sdk_query injected → provider takes the cold one-shot path (no warm session)
    provider = build_claude_code_subscription_provider(sdk_query=_fake_query)
    assert provider is not None
    provider.generate_structured(_request())
    after = subscription_transport_telemetry()
    assert provider.last_transport == "cold"
    assert after["cold_calls"] == before + 1


def test_capped_subscription_fails_over_to_the_next_lane() -> None:
    pool = SwappableMultiProviderLlmClient(
        [_CappedProvider(), _HealthyFallbackProvider()]
    )
    request = StrategyLlmRequest(
        system_instruction="s", user_prompt="u", response_json_schema={"type": "object"}
    )
    response = pool.generate_structured(request)
    assert response.served_by_provider == "groq"  # capped subscription lane was skipped
    status = pool.describe_pool()
    sub = next(p for p in status.providers if p.provider_name == "claude-code-subscription")
    assert sub.cooling_down is True  # the capped lane is now on cooldown
