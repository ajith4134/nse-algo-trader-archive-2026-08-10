"""What does each feature actually CONSUME, and what does anything actually consume FROM it?

The dashboard's job here is to make the system legible: for any feature, its real inputs, its real
outputs, and whether anything downstream uses it at all.

**Derived from the code's AST import graph, never hand-written.** That is the whole point. A
hand-maintained inputs/outputs list drifts the moment someone adds an import, and a panel showing a
stale edge is worse than no panel — it is a confident lie about how the system is wired.
`docs/SYSTEM_MAP.md` documents `IN:`/`OUT:` for only 12 of the 25 packages, so hand-writing the other
13 would mean inventing edges.

Edge direction: if package A imports package B, then **data flows B → A** (A consumes B's output).
The import arrow and the data arrow point opposite ways, which is the single easiest thing to get
backwards here.

This module answers structure ("what CAN flow"), not behaviour ("what DID flow"). A feature can be
richly connected and still change nothing — see `decision_influence` below, which is the honest
counterweight: only a handful of packages actually alter an order, and a view that paints all 25 as
equally alive would be the prettiest lie in the system.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent

#: Packages whose output demonstrably CHANGES an order (entry, size, veto, exit) — established by
#: reading the four files that can alter an order: `live_universe_paper_loop`,
#: `option_credit_spread_live_path`, `pre_trade_risk_gate`, `trading_control_config`.
#: Everything else is display-only or inert. Kept explicit and small precisely because it is a
#: CLAIM about behaviour, unlike the import graph which is derived.
DECISION_CHANGING_FEATURES: frozenset[str] = frozenset({
    "broker_credentials", "broker_sessions", "universe_registry", "market_data",
    "indicators", "strategy_engine", "risk_management", "broker_oms",
    "session_management", "paper_trading", "memory_reflection",
    "participant_positioning", "dashboard", "conscience", "sentience",
    "predictive_core", "autopoiesis",
})

#: Packages wired to a consumer but currently returning an identity/neutral value every cycle, so
#: they cannot change an outcome today. Named individually because "inert" is a finding, not a guess.
INERT_FEATURES: frozenset[str] = frozenset({"news_sentiment", "capital_allocation", "llm_strategy"})


@dataclass(frozen=True)
class FeatureDataflowNode:
    """One feature package: what flows in, what flows out, and whether it matters."""

    feature_name: str
    module_count: int
    consumes_from: tuple[str, ...]   # data flows FROM these INTO this feature
    feeds_into: tuple[str, ...]      # this feature's output flows INTO these

    @property
    def decision_influence(self) -> str:
        """`changes_decisions` | `inert` | `display_only` — the honest counterweight to a pretty graph."""
        if self.feature_name in INERT_FEATURES:
            return "inert"
        if self.feature_name in DECISION_CHANGING_FEATURES:
            return "changes_decisions"
        return "display_only"

    @property
    def is_orphan(self) -> bool:
        """Nothing consumes this feature's output — a Rule-G smell worth seeing on the page."""
        return not self.feeds_into


@lru_cache(maxsize=1)
def build_feature_dataflow_graph(source_root: Path | None = None) -> tuple[FeatureDataflowNode, ...]:
    """Parse every module and derive the real feature-to-feature data-flow graph.

    Cached: it is a full AST walk of ~276 modules, and the graph only changes on deploy.
    """
    root = source_root or _SOURCE_ROOT
    imports_by_feature: dict[str, set[str]] = {}
    modules_by_feature: dict[str, int] = {}

    for module_path in sorted(root.rglob("*.py")):
        relative = module_path.relative_to(root).parts
        if len(relative) < 2:
            continue  # top-level __init__, not a feature package
        feature = relative[0]
        modules_by_feature[feature] = modules_by_feature.get(feature, 0) + 1
        imports_by_feature.setdefault(feature, set())
        if module_path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(module_path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue  # a file we cannot parse must not take the whole graph down
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if not node.module.startswith("nse_algo_trader."):
                    continue
                imported_feature = node.module.split(".")[1]
                if imported_feature != feature:
                    imports_by_feature[feature].add(imported_feature)

    # A imports B  =>  data flows B -> A.
    feeds_into: dict[str, set[str]] = {name: set() for name in imports_by_feature}
    for consumer, produced_by in imports_by_feature.items():
        for producer in produced_by:
            feeds_into.setdefault(producer, set()).add(consumer)

    return tuple(
        FeatureDataflowNode(
            feature_name=name,
            module_count=modules_by_feature.get(name, 0),
            consumes_from=tuple(sorted(imports_by_feature.get(name, set()))),
            feeds_into=tuple(sorted(feeds_into.get(name, set()))),
        )
        for name in sorted(imports_by_feature)
    )


def feature_dataflow_rows() -> list[dict]:
    """JSON-serialisable rows for the dashboard — one per feature package."""
    return [
        {
            "feature_name": node.feature_name,
            "module_count": node.module_count,
            "consumes_from": list(node.consumes_from),
            "feeds_into": list(node.feeds_into),
            "decision_influence": node.decision_influence,
            "is_orphan": node.is_orphan,
        }
        for node in build_feature_dataflow_graph()
    ]
