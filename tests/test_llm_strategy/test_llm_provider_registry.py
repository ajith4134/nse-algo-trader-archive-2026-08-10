"""Hermetic test for the provider registry (Rule J): the pool self-sizes to whatever keys
are present in the env mapping, skips absent keys, needs Cloudflare's account id, and pins a
paid Anthropic key first. No network — providers are only constructed, never called.
"""

from __future__ import annotations

from nse_algo_trader.llm_strategy.llm_provider_registry import (
    build_free_tier_provider_pool as _build_pool_under_test,
)


def build_free_tier_provider_pool(env, **kwargs):
    """Hermetic wrapper (Rule J): suppress the LOCAL rung AND the Claude subscription rung unless a
    test opts into them.

    The real builder probes `localhost:11434` for an on-box Ollama server, so without this seam
    every assertion below would depend on whether the developer's machine happens to be serving a
    model — a test that passes on one box and fails on another. Local-rung behaviour is asserted
    explicitly in the dedicated tests at the bottom of this file.

    The subscription rung (`claude-code-subscription`) is prepended FIRST in production (B48, so the
    flat-cost lane leads). These tests bind the FREE-TIER ordering specifically, so we disable the
    subscription lane here; its own placement is covered in the subscription/gateway tests.
    """
    kwargs.setdefault("local_provider_factory", lambda env: None)
    kwargs.setdefault("subscription_provider_factory", lambda env: None)
    return _build_pool_under_test(env, **kwargs)

# The keyless anonymous last-resort tier always joins the pool (even with no keys), pinned
# LAST. Keyed-provider assertions below check the prefix before this tail. (OVHcloud only —
# Pollinations was researched but rejected as non-viable keyless; see docs/BACKLOG.md.)
KEYLESS_TAIL = ["ovhcloud-ai-endpoints"]


def _keyed_names(pool):
    return [p.provider_name for p in pool if p.provider_name not in KEYLESS_TAIL]


def test_pool_self_sizes_to_present_keys():
    env = {"GROQ_API_KEY": "g", "CEREBRAS_API_KEY": "c", "OPENROUTER_API_KEY": "  "}
    pool = build_free_tier_provider_pool(env)
    assert _keyed_names(pool) == ["groq", "cerebras"]  # blank openrouter skipped; order kept
    # keyless fallbacks are appended after the keyed providers
    assert [p.provider_name for p in pool] == ["groq", "cerebras"] + KEYLESS_TAIL


def test_empty_env_yields_only_the_keyless_tail():
    assert [p.provider_name for p in build_free_tier_provider_pool({})] == KEYLESS_TAIL


def test_cloudflare_needs_account_id():
    without = build_free_tier_provider_pool({"CLOUDFLARE_API_KEY": "cf"})
    assert _keyed_names(without) == []  # no account id → cloudflare skipped
    with_id = build_free_tier_provider_pool(
        {"CLOUDFLARE_API_KEY": "cf", "CLOUDFLARE_ACCOUNT_ID": "acct"}
    )
    assert _keyed_names(with_id) == ["cloudflare-workers-ai"]


def test_model_override_via_env():
    pool = build_free_tier_provider_pool({"GROQ_API_KEY": "g", "GROQ_MODEL": "custom-model"})
    assert pool[0].model_name == "custom-model"


def test_keyless_provider_joins_the_pool_with_no_key():
    # OVHcloud is a last-resort keyless fallback: it appears even in an otherwise-empty env,
    # at the bottom of the failover order, so the pool is never empty.
    names = [p.provider_name for p in build_free_tier_provider_pool({})]
    assert names == ["ovhcloud-ai-endpoints"]


def test_keyless_provider_uses_a_supplied_key_when_present():
    pool = build_free_tier_provider_pool({"OVHCLOUD_API_KEY": "ovh-secret"})
    ovh = next(p for p in pool if p.provider_name == "ovhcloud-ai-endpoints")
    assert ovh._api_key == "ovh-secret"  # supplied key raises the anon rate limit


def test_paid_anthropic_is_appended_LAST_not_pinned_first():
    """B33: the operator's cost ladder inverted this contract.

    This previously asserted the PAID provider was pinned FIRST, which meant every call spent money
    while free capacity sat unused. Paid is now the fallback of last resort; the key is still passed
    through correctly, it is just no longer reached until the free tiers are exhausted.
    """
    captured = {}

    def fake_anthropic_factory(api_key):
        captured["key"] = api_key

        class _Stub:
            provider_name = "anthropic-claude"
            model_name = "claude-opus-4-8"

        return _Stub()

    pool = build_free_tier_provider_pool(
        {"ANTHROPIC_API_KEY": "sk-ant", "GROQ_API_KEY": "g"},
        anthropic_provider_factory=fake_anthropic_factory,
    )
    names = [p.provider_name for p in pool]
    assert names == ["groq"] + KEYLESS_TAIL + ["anthropic-claude"]
    assert names[-1] == "anthropic-claude", "paid must be the final fallback"
    assert captured["key"] == "sk-ant"


# --- B33 LOCAL RUNG -------------------------------------------------------------------------
# The operator's ladder is time-dependent: local off-market, free cloud during market hours, paid
# last and never sticky. These bind that rule so a future edit cannot quietly invert it.


class _StubLocalProvider:
    provider_name = "ollama-local"
    model_name = "qwen3:4b"


def _local(_env):
    return _StubLocalProvider()


def test_local_rung_leads_when_the_market_is_CLOSED():
    pool = _build_pool_under_test(
        {"GROQ_API_KEY": "g"}, market_is_open=False, local_provider_factory=_local,
        subscription_provider_factory=lambda env: None,
    )
    assert [p.provider_name for p in pool][0] == "ollama-local", "off-market must try local first"


def test_local_rung_yields_to_free_cloud_while_the_market_is_OPEN():
    """Latency is on a decision path during market hours, so cloud leads — but local still
    outranks PAID, because local is free and paid is not."""
    pool = _build_pool_under_test(
        {"GROQ_API_KEY": "g", "MOONSHOT_API_KEY": "k"},
        market_is_open=True,
        local_provider_factory=_local,
    )
    names = [p.provider_name for p in pool]
    assert names.index("groq") < names.index("ollama-local"), "cloud leads during market hours"
    assert names.index("ollama-local") < names.index("kimi-paid"), "free local must precede PAID"
    assert names[-1] == "kimi-paid", "paid stays the last resort"


def test_absent_local_server_simply_omits_the_rung():
    """An unreachable on-box server is a NORMAL state, not an outage: the pool must be unaffected."""
    pool = _build_pool_under_test(
        {"GROQ_API_KEY": "g"}, market_is_open=False, local_provider_factory=lambda env: None,
        subscription_provider_factory=lambda env: None,
    )
    assert "ollama-local" not in [p.provider_name for p in pool]
    assert [p.provider_name for p in pool] == ["groq"] + KEYLESS_TAIL


def test_local_rung_never_outranks_free_cloud_by_accident_when_clock_unspecified(monkeypatch):
    """market_is_open=None consults the real clock rather than pinning one side of the rule."""
    import nse_algo_trader.llm_strategy.llm_provider_registry as registry

    monkeypatch.setattr(registry, "_local_rung_leads", lambda _: True)
    pool = registry.build_free_tier_provider_pool(
        {"GROQ_API_KEY": "g"}, local_provider_factory=_local,
        subscription_provider_factory=lambda env: None,
    )
    assert [p.provider_name for p in pool][0] == "ollama-local"
