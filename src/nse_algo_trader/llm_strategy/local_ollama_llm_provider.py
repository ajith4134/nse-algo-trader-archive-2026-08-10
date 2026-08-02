"""The LOCAL rung of the operator's cost ladder: an on-box Ollama server, free and unmetered.

The ladder (operator's standing rule): **local → free cloud → Kimi paid**, and paid is never sticky.
This module supplies the local rung. It is the cheapest provider in the pool by construction — it
costs nothing per token and has no rate limit — so the only reasons not to prefer it are latency and
capability, which is exactly what the position rule below encodes.

**Position depends on the market clock, because the operator's rule is time-dependent:** local during
off-market hours (batch research/learning, where a 21-second answer is free and fine), free cloud
during market hours (where latency is on a decision path). Local never sits behind the PAID tier —
it is free, so preferring paid over it would burn money for no reason.

**The cold-start cliff is the reason `pin_local_model_resident` exists.** Measured on this box
(`docs/research/local_llm_on_box_benchmark_2026-07-27.md`): the same model runs at 2.15 tok/s on the
first call after eviction and 9.6 tok/s warm — a 4.5x swing, because Ollama mmaps the GGUF and the
first generation faults the weights in from disk. Ollama reports this as `load_duration: 0s`, hiding
it inside the generation timing. Without pinning, every call after an idle gap pays ~100 seconds.

Ollama also keeps only ONE model resident by default, so this rung deliberately commits to a single
model: routing across several would force a reload — and pay that cliff — on every switch.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping

from nse_algo_trader.llm_strategy.native_ollama_constrained_chat_provider import (
    NativeOllamaConstrainedChatProvider,
)
from nse_algo_trader.llm_strategy.openai_compatible_chat_provider import HttpPost
from nse_algo_trader.llm_strategy.strategy_llm_client import LlmProvider

#: Ollama's OpenAI-compatible surface. Loopback only — this is an on-box server, never remote.
DEFAULT_LOCAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"

#: Chosen by on-box measurement AND by real end-to-end verification, not by reputation.
#:
#: The fastest model measured was `qwen3:4b` (~9.6 tok/s warm) and it was the default here until real
#: calls exposed two separate reasons it does not work on this box — BOTH confirmed by measurement:
#:   1. Through the OpenAI-compatible `/v1` surface it returned `content: ''` — Ollama routes a
#:      thinking model's chain into a separate `reasoning` field, so at any bounded budget it thinks
#:      and answers NOTHING (`chat_template_kwargs.enable_thinking:false` is not honoured there).
#:   2. Under the NATIVE endpoint's grammar-constrained decoding (`format:`, which this rung now uses)
#:      a constrained generation on qwen3 did NOT finish within 8 minutes — constrained sampling
#:      stacked on a reasoning phase is too slow on this CPU box. The abstain-timeout would fail it
#:      over every call, so it is still the wrong default.
#:
#: `granite4:micro` is instruction-tuned WITHOUT a separate reasoning phase, so constrained decoding
#: returns a clean schema-valid object in ~5-6 s warm. Think-then-answer is still obtained cheaply via
#: the injected leading `rationale` field (see native_ollama_constrained_chat_provider), so dropping
#: the reasoning model costs no reasoning — only the thinking-phase tax.
DEFAULT_LOCAL_OLLAMA_MODEL = "granite4:micro"

#: Models with a dedicated reasoning phase. Even under native constrained decoding they are too slow
#: on this CPU box (measured: no completion in 8 min), and via the OpenAI-compat surface they answer
#: into a `reasoning` field leaving `content` empty. Either way the rung refuses to auto-select one —
#: better an absent rung than one that hangs or answers empty. An explicit `OLLAMA_MODEL` override
#: still wins (the operator may run better hardware).
THINKING_MODELS_UNUSABLE_ON_THIS_BOX: frozenset[str] = frozenset(
    {"qwen3", "deepseek-r1"}
)

LOCAL_OLLAMA_PROVIDER_NAME = "ollama-local"

#: Keep the model resident indefinitely. `-1` is Ollama's "never evict" sentinel.
_PIN_RESIDENT_KEEP_ALIVE = -1

_REACHABILITY_TIMEOUT_SECONDS = 2.0


def _local_ollama_root_url(base_url: str) -> str:
    """Ollama's native API (`/api/...`) sits beside the OpenAI-compatible `/v1` prefix, not under it."""
    return base_url[: -len("/v1")] if base_url.endswith("/v1") else base_url


def local_ollama_served_model_names(
    base_url: str = DEFAULT_LOCAL_OLLAMA_BASE_URL,
    timeout_seconds: float = _REACHABILITY_TIMEOUT_SECONDS,
) -> tuple[str, ...]:
    """Model ids the local server is actually serving, or () if it is not reachable.

    Returning () rather than raising is deliberate: an absent local server is a NORMAL state (the
    operator may not have started it), and it must degrade to "this rung is not available" without
    disturbing the rest of the pool.
    """
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return ()
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return ()
    return tuple(
        str(entry["id"]) for entry in entries if isinstance(entry, dict) and entry.get("id")
    )


def resolve_local_ollama_model(
    env: Mapping[str, str],
    served_model_names: tuple[str, ...],
) -> str:
    """The model this rung should use, or "" if the local server cannot honour a sane choice.

    Verifies the model is genuinely SERVED rather than trusting a default: a configured-but-unpulled
    model would otherwise join the pool and fail every call at request time, which looks like an
    outage instead of an absent optional rung.
    """
    if not served_model_names:
        return ""
    requested = (env.get("OLLAMA_MODEL") or "").strip()
    if requested:
        # An explicit override is honoured even if it is a thinking model — the operator may know
        # something we do not — but it must at least be served.
        return requested if requested in served_model_names else ""
    if DEFAULT_LOCAL_OLLAMA_MODEL in served_model_names:
        return DEFAULT_LOCAL_OLLAMA_MODEL
    usable = [
        name for name in served_model_names if not model_has_reasoning_phase_unusable_here(name)
    ]
    return usable[0] if usable else ""


def model_has_reasoning_phase_unusable_here(model_name: str) -> bool:
    """True for reasoning-phase models this box cannot serve usably, so auto-selection skips them.

    Verified on the real server, not inferred: `qwen3:4b` both returned `content: ''` through the
    OpenAI-compat surface AND failed to finish an 8-minute constrained-decoding call under the native
    endpoint. Either failure alone disqualifies it from being picked automatically; an explicit
    `OLLAMA_MODEL` override still bypasses this (the operator may run faster hardware).
    """
    family = model_name.split(":", 1)[0].strip().lower()
    return family in THINKING_MODELS_UNUSABLE_ON_THIS_BOX


def pin_local_model_resident(
    model_name: str,
    base_url: str = DEFAULT_LOCAL_OLLAMA_BASE_URL,
    in_background: bool = True,
) -> None:
    """Load `model_name` and hold it in memory, so no later call pays the ~100 s cold-start cliff.

    Runs in a background thread by default: the warm-up itself takes ~100 s cold, and pool
    construction happens on the request path — blocking it would trade a slow first LLM call for a
    slow first PAGE LOAD, which is strictly worse. Failure is silent-but-logged: pinning is an
    optimisation, and a system that refuses to start because a warm-up failed is worse than a slow one.
    """

    def _warm_up() -> None:
        request = urllib.request.Request(
            f"{_local_ollama_root_url(base_url)}/api/generate",
            data=json.dumps(
                {
                    "model": model_name,
                    "prompt": "ok",
                    "stream": False,
                    "keep_alive": _PIN_RESIDENT_KEEP_ALIVE,
                    "options": {"num_predict": 1},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                response.read()
        except (urllib.error.URLError, OSError) as unreachable:
            print(
                f"[llm-pool] local model pin failed for {model_name} "
                f"({unreachable}); calls will pay the cold-start cost",
                flush=True,
            )

    if not in_background:
        _warm_up()
        return
    threading.Thread(
        target=_warm_up, name=f"pin-local-llm-{model_name}", daemon=True
    ).start()


def build_local_ollama_provider(
    env: Mapping[str, str],
    http_post: HttpPost | None = None,
    base_url: str | None = None,
    pin_resident: bool = True,
) -> LlmProvider | None:
    """The local provider, or None when no on-box server is serving a usable model.

    None is the honest "this rung is absent" answer and callers simply omit it from the pool — the
    local rung is optional infrastructure, not a dependency.
    """
    resolved_base_url = (
        base_url or (env.get("OLLAMA_BASE_URL") or "").strip() or DEFAULT_LOCAL_OLLAMA_BASE_URL
    )
    served = local_ollama_served_model_names(resolved_base_url)
    model_name = resolve_local_ollama_model(env, served)
    if not model_name:
        return None
    if pin_resident:
        pin_local_model_resident(model_name, resolved_base_url)
    # Native `/api/chat` + `format:` (constrained decoding), NOT the OpenAI-compat `/v1` surface:
    # only the native endpoint constrains decoding and avoids the reasoning-field diversion that
    # returned empty `content` for thinking models. See native_ollama_constrained_chat_provider.
    return NativeOllamaConstrainedChatProvider(
        provider_name=LOCAL_OLLAMA_PROVIDER_NAME,
        root_base_url=_local_ollama_root_url(resolved_base_url),
        model_name=model_name,
        http_post=http_post,
    )
