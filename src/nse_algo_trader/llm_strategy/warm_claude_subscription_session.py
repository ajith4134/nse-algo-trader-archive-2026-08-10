"""Warm-persistent Claude Code subscription session — the speed engine behind the subscription LLM lane
(B48, design `docs/research/b48_warm_persistent_subscription_client_2026-08-02.md`).

Why this exists: the subscription provider's cold path spawns a fresh `claude` CLI subprocess **per call**
(`anyio.run(query(...))`), and that cold start dominates the ~4–9 s latency. This engine keeps ONE
`ClaudeSDKClient` (hence one warm subprocess) alive for the whole process, so the 2nd…Nth structured
generation skips cold start. Correctness is preserved two ways:
  • **No context bleed** — every call runs under a fresh `session_id` on the same warm client, so
    independent structured generations never see each other's context (and token cost never accretes).
  • **Degrade, never halt** — a start/connect failure or an unrecoverable transport death raises
    `WarmSessionUnavailable`, and the provider transparently falls back to the cold one-shot path. A
    usage-cap or model error is NOT swallowed here; it propagates so the provider's error-mapping turns it
    into the pool's `LlmRateLimitError` fail-over signal.

Sync-facing: the async `ClaudeSDKClient` lives on an `anyio` `BlockingPortal` (a background event loop),
so this drops into the synchronous provider pool unchanged. The SDK client + portal are injected behind a
DI seam (`client_factory` / `portal_factory`) so tests exercise start / per-call isolation / reconnect /
permanent-death without spending subscription usage (Rule J).
"""

from __future__ import annotations

import atexit
import contextlib
import os
import threading
from collections.abc import Callable
from itertools import count
from typing import Any

import anyio
from anyio.from_thread import start_blocking_portal

# Default request budget: a warm structured call should return fast; if it hangs past this the lane is
# treated as transient-unavailable and the pool moves on. Env-overridable (self-calibrating, Rule: no
# hard-coded magic — the operator can widen it without a code change).
_DEFAULT_REQUEST_TIMEOUT_S = float(os.environ.get("CLAUDE_SUBSCRIPTION_WARM_REQUEST_TIMEOUT_S", "90"))
_DEFAULT_CONNECT_TIMEOUT_S = float(os.environ.get("CLAUDE_SUBSCRIPTION_WARM_CONNECT_TIMEOUT_S", "60"))

# The generic connect-time contract. The per-request domain `system_instruction` is folded into the prompt
# body (connect-time options are fixed for the warm client), so one warm client serves every request shape.
_WARM_SYSTEM_PROMPT = (
    "You are a structured JSON generator. Reply with ONLY a single JSON object matching the required "
    "schema. No prose, no code fences, no explanation."
)


class WarmSessionUnavailable(Exception):
    """The warm path cannot serve this call at all (SDK missing / connect failed / unrecoverable transport
    death). Signals the provider to fall back to the cold one-shot path. Deliberately NOT an
    `LlmProviderUnavailableError` so it never reaches the pool as a lane failure — the cold path still gets
    a chance on the same subscription first."""


def _is_transport_death(exc: BaseException) -> bool:
    """True for the connection/process errors that a reconnect can plausibly cure (vs a cap/model error,
    which reconnecting would not fix). Read by class NAME so we do not hard-depend on SDK error identities
    across versions."""
    name = type(exc).__name__.lower()
    if any(s in name for s in ("connection", "process", "brokenpipe", "clinotfound", "transport")):
        return True
    blob = str(exc).lower()
    return any(s in blob for s in ("broken pipe", "connection reset", "process exited", "not connected"))


class WarmClaudeSubscriptionSession:
    """Process-lifetime holder of one connected `ClaudeSDKClient` on a background event loop.

    Lazy: the portal opens and the client connects on the FIRST `run_structured`. Thread-safe (a lock
    guards start/reconnect/teardown). If start fails once, the session self-disables for the process (warm
    off → the provider cold-paths every call) rather than paying a slow failed connect on each call; a
    process restart re-enables it."""

    def __init__(
        self,
        model_name: str,
        *,
        client_factory: Callable[[Any], Any] | None = None,
        portal_factory: Callable[[], Any] | None = None,
        options_factory: Callable[[str], Any] | None = None,
        request_timeout_s: float = _DEFAULT_REQUEST_TIMEOUT_S,
        connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S,
        max_reconnects: int = 1,
    ) -> None:
        self.model_name = model_name
        self._client_factory = client_factory  # None → resolve the real ClaudeSDKClient lazily
        self._portal_factory = portal_factory or start_blocking_portal
        self._options_factory = options_factory  # None → real ClaudeAgentOptions
        self._request_timeout_s = request_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._max_reconnects = max_reconnects

        self._lock = threading.Lock()
        self._portal_cm: Any = None
        self._portal: Any = None
        self._client: Any = None
        self._current_model: str = model_name
        self._session_counter = count(1)
        self._started = False
        self._disabled = False  # set True after a start failure → warm off for the process
        self._closed = False
        atexit.register(self.close)

    # ---- real-SDK resolution (only when no fake was injected) -------------------------------------
    def _resolve_client_factory(self) -> Callable[[Any], Any]:
        if self._client_factory is not None:
            return self._client_factory
        from claude_agent_sdk import ClaudeSDKClient  # imported only when actually warming

        return lambda options: ClaudeSDKClient(options=options)

    def _build_options(self) -> Any:
        if self._options_factory is not None:
            return self._options_factory(self.model_name)
        from claude_agent_sdk import ClaudeAgentOptions

        return ClaudeAgentOptions(
            model=self.model_name,
            max_turns=1,
            setting_sources=[],   # do NOT load CLAUDE.md/harness → cuts the ~33k-token cache load
            allowed_tools=[],     # no tools for a structured-generation call
            system_prompt=_WARM_SYSTEM_PROMPT,
        )

    # ---- async ops that run ON the portal loop (the client is touched nowhere else) ---------------
    async def _aconnect(self) -> None:
        options = self._build_options()
        self._client = self._resolve_client_factory()(options)
        with anyio.fail_after(self._connect_timeout_s):
            await self._client.connect()
        self._current_model = self.model_name

    async def _adisconnect(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            # teardown must never raise; a dead client is already gone
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def _aask(self, system_instruction: str, user_prompt: str, session_id: str, model: str) -> list:
        if model and model != self._current_model:
            await self._client.set_model(model)
            self._current_model = model
        folded = (
            f"{system_instruction}\n\n{user_prompt}" if system_instruction else user_prompt
        )
        messages: list[Any] = []
        with anyio.fail_after(self._request_timeout_s):
            await self._client.query(folded, session_id=session_id)
            async for msg in self._client.receive_response():
                messages.append(msg)
        return messages

    # ---- lifecycle (sync, lock-guarded) ----------------------------------------------------------
    def _ensure_started(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started or self._disabled:
                if self._disabled:
                    raise WarmSessionUnavailable("warm session disabled after a prior start failure")
                return
            try:
                self._portal_cm = self._portal_factory()
                self._portal = self._portal_cm.__enter__()
                self._portal.call(self._aconnect)
                self._started = True
            except Exception as exc:  # noqa: BLE001 — any start failure → warm off, provider cold-paths
                self._disabled = True
                self._teardown_portal_locked()
                raise WarmSessionUnavailable(f"warm connect failed: {exc}") from exc

    def _reconnect_locked(self) -> None:
        """Disconnect the dead client and connect a fresh one on the SAME portal loop."""
        self._portal.call(self._adisconnect)
        self._portal.call(self._aconnect)

    def _teardown_portal_locked(self) -> None:
        if self._portal is not None:
            with contextlib.suppress(Exception):
                self._portal.call(self._adisconnect)
        if self._portal_cm is not None:
            with contextlib.suppress(Exception):
                self._portal_cm.__exit__(None, None, None)
        self._portal = None
        self._portal_cm = None
        self._client = None

    # ---- the sync entry point the provider calls -------------------------------------------------
    def run_structured(
        self,
        system_instruction: str,
        user_prompt: str,
        model: str,
        extract: Callable[[list], tuple[str, str]],
    ) -> tuple[str, str]:
        """Run one structured generation on the warm client and return (text, canonical_model).

        Raises `WarmSessionUnavailable` when the warm path cannot serve (→ provider falls back to cold).
        Any OTHER exception (usage cap, model error, timeout) propagates unchanged so the provider's
        error-mapping classifies it (cap → fail-over, transient → unavailable). `extract` turns the raw SDK
        message list into (text, model) — injected to keep this engine content-agnostic (no import cycle)."""
        if self._closed:
            raise WarmSessionUnavailable("warm session already closed")
        self._ensure_started()
        session_id = str(next(self._session_counter))
        attempts = 0
        while True:
            try:
                messages = self._portal.call(self._aask, system_instruction, user_prompt, session_id, model)
                return extract(messages)
            except WarmSessionUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                if _is_transport_death(exc) and attempts < self._max_reconnects:
                    attempts += 1
                    with self._lock:
                        try:
                            self._reconnect_locked()
                        except Exception as reconnect_exc:  # noqa: BLE001 — reconnect failed → cold path
                            self._disabled = True
                            self._teardown_portal_locked()
                            self._started = False
                            raise WarmSessionUnavailable(
                                f"warm reconnect failed: {reconnect_exc}"
                            ) from reconnect_exc
                    continue  # retry the call on the fresh client
                if _is_transport_death(exc):
                    # out of reconnect budget → give the cold path a turn
                    raise WarmSessionUnavailable(f"warm transport death: {exc}") from exc
                raise  # cap / model / timeout → let the provider map it

    def close(self) -> None:
        if self._closed:
            return
        with self._lock:
            self._closed = True
            self._teardown_portal_locked()
            self._started = False
