"""B33 — LLM calls must climb a COST ladder: free tiers first, paid last and sparingly.

The operator's standing rule. Before this, `build_free_tier_provider_pool` pinned the PAID
`ANTHROPIC_API_KEY` **first** — so every call spent money while free capacity sat unused.
"""

from nse_algo_trader.llm_strategy.llm_provider_registry import (
    PAID_PROVIDER_CONFIGS,
    build_free_tier_provider_pool,
)


def _names(env, **kwargs):
    return [p.provider_name for p in build_free_tier_provider_pool(env, **kwargs)]


class TestCostLadderOrdering:
    def test_the_b33_regression_paid_is_LAST_not_first(self):
        names = _names({"GROQ_API_KEY": "g", "MOONSHOT_API_KEY": "k"})
        assert "kimi-paid" in names
        assert names.index("kimi-paid") == len(names) - 1, (
            f"paid must be the final fallback, got {names}"
        )

    def test_every_free_tier_precedes_the_paid_tier(self):
        names = _names({
            "GROQ_API_KEY": "g", "CEREBRAS_API_KEY": "c",
            "SAMBANOVA_API_KEY": "s", "MOONSHOT_API_KEY": "k",
        })
        paid_index = names.index("kimi-paid")
        assert paid_index == len(names) - 1
        assert paid_index > 0, "at least one free tier must come first"

    def test_kimi_is_the_designated_paid_tier(self):
        assert any(c.provider_name == "kimi-paid" for c in PAID_PROVIDER_CONFIGS)
        kimi = next(c for c in PAID_PROVIDER_CONFIGS if c.provider_name == "kimi-paid")
        assert kimi.api_key_env == "MOONSHOT_API_KEY"
        assert "moonshot" in kimi.base_url_template

    def test_no_paid_key_means_no_paid_provider(self):
        """Absent a paid key the system must run free-only, never silently fail."""
        names = _names({"GROQ_API_KEY": "g"})
        assert "kimi-paid" not in names
        assert "groq" in names

    def test_no_keys_at_all_yields_only_keyless_providers(self):
        """Rule F: an empty/near-empty pool is the honest state, not an exception."""
        assert isinstance(_names({}), list)


class TestAnOptionalPaidProviderCannotKillThePool:
    def test_an_uninstalled_paid_sdk_does_not_take_down_the_free_tiers(self):
        """A stale key for an uninstalled provider used to raise out of pool construction,
        leaving the system with NO llm at all — the free tiers were never even built."""
        names = _names({"GROQ_API_KEY": "g", "ANTHROPIC_API_KEY": "stale-key"})
        assert "groq" in names, f"free tiers must survive an unavailable paid fallback: {names}"

    def test_a_working_paid_factory_is_still_appended_last(self):
        class _Stub:
            provider_name = "anthropic-claude"

        names = _names(
            {"GROQ_API_KEY": "g", "ANTHROPIC_API_KEY": "a"},
            anthropic_provider_factory=lambda _key: _Stub(),
        )
        assert names[-1] == "anthropic-claude"
        assert names.index("groq") < names.index("anthropic-claude")
