"""The LOCAL rung of the cost ladder (B33).

The central regression here is NOT the ordering — it is model SELECTION. A thinking model returns
`content: ''` with its answer diverted into a `reasoning` field, so it parses as a failure on every
call. Sitting first in the pool, such a model would silently push every request down to a PAID
provider while appearing healthy. Verified against the real on-box server, then pinned here.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.local_ollama_llm_provider import (
    DEFAULT_LOCAL_OLLAMA_MODEL,
    model_has_reasoning_phase_unusable_here,
    resolve_local_ollama_model,
)


def test_thinking_models_are_recognised_as_unusable():
    # Observed on the real server: both a `content: ''` diversion via /v1 AND an 8-min no-finish
    # under native constrained decoding — either way, unusable on this box.
    assert model_has_reasoning_phase_unusable_here("qwen3:4b")
    assert model_has_reasoning_phase_unusable_here("deepseek-r1:14b")
    assert not model_has_reasoning_phase_unusable_here("granite4:micro")


def test_the_default_model_is_not_a_thinking_model():
    """Guards the exact regression that real-data verification caught: qwen3:4b was the default
    (it benchmarked fastest) and could not serve a usable structured answer on this box."""
    assert not model_has_reasoning_phase_unusable_here(DEFAULT_LOCAL_OLLAMA_MODEL)


def test_no_served_models_means_no_local_rung():
    assert resolve_local_ollama_model({}, ()) == ""


def test_prefers_the_default_when_it_is_served():
    served = ("qwen3:4b", DEFAULT_LOCAL_OLLAMA_MODEL, "deepseek-r1:7b")
    assert resolve_local_ollama_model({}, served) == DEFAULT_LOCAL_OLLAMA_MODEL


def test_falls_back_to_a_usable_model_skipping_thinking_ones():
    """With the default absent, a NON-thinking model is chosen rather than the first served one."""
    assert resolve_local_ollama_model({}, ("qwen3:4b", "deepseek-r1:7b", "phi4:latest")) == "phi4:latest"


def test_all_served_models_thinking_means_no_rung():
    assert resolve_local_ollama_model({}, ("qwen3:4b", "deepseek-r1:14b")) == ""


def test_unserved_override_is_refused_rather_than_failing_at_request_time():
    """A configured-but-unpulled model must yield no rung, not a provider that 404s every call."""
    assert resolve_local_ollama_model({"OLLAMA_MODEL": "not-pulled:1b"}, ("granite4:micro",)) == ""


def test_explicit_override_is_honoured_when_served():
    assert resolve_local_ollama_model({"OLLAMA_MODEL": "qwen3:4b"}, ("qwen3:4b",)) == "qwen3:4b"
