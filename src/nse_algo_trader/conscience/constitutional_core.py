"""Constitutional core — the machine-checkable conscience (Trunk VII.1; research/109).

The project's INVIOLABLE rules encoded as DATA (a constitution of articles), plus a reviewer that
judges any proposed trading ACTION or system POSTURE against them and returns a structured,
audited verdict (permitted? + which articles + a trace id). This is the root safety organ of the
CONSCIENCE trunk — a machine should not gain autonomy without limits it cannot rewrite.

Design (sourced via sourcing-oss-parts, research/109): OSS policy engines (OPA/Rego, json-rule-
engine, Cedar) were surveyed but not vendored — for a SUPREME, zero-dependency, fully-auditable
organ evaluating ~a dozen NSE/SEBI/intraday-specific predicates, a hand-written evaluator is safer
than a heavy DSL or a thin-maintenance dep. We ADOPT the proven prior-art PATTERNS: hard-vs-soft
constraint severity, policy-as-DATA (articles, not scattered if/else), and a structured audited
verdict (exact article + evidence + trace id). PURE, zero-dep, deterministic (no clock/random).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

# Phase-1 scope (CLAUDE.md): the ONLY segments the bot may trade. Anything else (futures,
# commodity, BSE index) violates the constitution's segment-scope article.
ALLOWED_SEGMENTS: frozenset[str] = frozenset(
    {"nse_cash_equity", "nse_index_options", "nse_stock_options"}
)
_MAX_ORDERS_PER_SECOND = 10  # SEBI: crossing this = mandatory-registration territory
_MAX_ALLOWED_RISK_PER_TRADE = 0.05  # a config setting per-trade risk above this is unsafe
_RISK_EPSILON = 1e-9


class ArticleSeverity(str, Enum):
    HARD = "hard"  # a violation BLOCKS the action / fails the posture
    SOFT = "soft"  # a violation is an advisory WARNING (flagged, not blocked)


class ArticleScope(str, Enum):
    ACTION = "action"  # judged per proposed trading action
    POSTURE = "posture"  # judged against the system/config posture


@dataclass(frozen=True)
class ConstitutionalArticle:
    """One inviolable rule as DATA. `predicate(subject) -> True` means COMPLIANT."""

    article_id: str
    principle: str
    severity: ArticleSeverity
    scope: ArticleScope
    predicate: Callable[[object], bool]


@dataclass(frozen=True)
class ProposedTradingAction:
    """A trade the system intends to place — the subject of an ACTION review."""

    segment: str
    is_live: bool = False
    is_option: bool = False
    is_overnight_carry: bool = False
    option_risk_defined: bool = True
    is_atomic_multi_leg: bool = True
    routes_through_broker: bool = True
    has_algo_id: bool = True
    orders_this_second: int = 1
    per_trade_risk_fraction: float = 0.0
    max_risk_per_trade_fraction: float = 0.01


@dataclass(frozen=True)
class SystemPosture:
    """The running system's configuration + fixed invariants — the subject of a POSTURE audit."""

    intraday_only: bool
    personal_use_only: bool
    max_risk_per_trade_fraction: float
    min_capital_per_trade: float
    max_capital_per_trade: float
    enabled_segments: tuple[str, ...]
    secrets_committed: bool = False


@dataclass(frozen=True)
class ArticleViolation:
    article_id: str
    principle: str
    severity: str

    def to_json_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "principle": self.principle,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ConstitutionalVerdict:
    """The audited outcome of a review. `permitted` is False iff any HARD article was violated;
    SOFT violations are surfaced as warnings but do not block. `trace_id` is a deterministic
    fingerprint of the subject for the forensic audit trail (pattern from the policy-as-code
    literature, research/109)."""

    permitted: bool
    scope: str
    trace_id: str
    hard_violations: tuple[ArticleViolation, ...] = ()
    soft_warnings: tuple[ArticleViolation, ...] = ()
    detail: str = ""

    def to_json_dict(self) -> dict:
        return {
            "permitted": self.permitted,
            "scope": self.scope,
            "trace_id": self.trace_id,
            "hard_violations": [v.to_json_dict() for v in self.hard_violations],
            "soft_warnings": [v.to_json_dict() for v in self.soft_warnings],
            "detail": self.detail,
        }


# ----- the constitution (CLAUDE.md binding constraints, as DATA) -----

CONSTITUTION: tuple[ConstitutionalArticle, ...] = (
    ConstitutionalArticle(
        "A1", "Intraday-only: no overnight carry, ever", ArticleSeverity.HARD,
        ArticleScope.ACTION, lambda a: not a.is_overnight_carry),
    ConstitutionalArticle(
        "A2", f"Order rate ≤ {_MAX_ORDERS_PER_SECOND}/sec/exchange/client (SEBI)",
        ArticleSeverity.HARD, ArticleScope.ACTION,
        lambda a: a.orders_this_second <= _MAX_ORDERS_PER_SECOND),
    ConstitutionalArticle(
        "A3", "Defined-risk only: no naked option leg", ArticleSeverity.HARD,
        ArticleScope.ACTION, lambda a: (not a.is_option) or a.option_risk_defined),
    ConstitutionalArticle(
        "A4", "Never-a-naked-leg: multi-leg orders execute atomically", ArticleSeverity.HARD,
        ArticleScope.ACTION, lambda a: a.is_atomic_multi_leg),
    ConstitutionalArticle(
        "A5", "Broker-as-principal: route via the broker API, never direct-to-exchange",
        ArticleSeverity.HARD, ArticleScope.ACTION, lambda a: a.routes_through_broker),
    ConstitutionalArticle(
        "A6", "Every LIVE order carries the exchange Algo-ID", ArticleSeverity.HARD,
        ArticleScope.ACTION, lambda a: (not a.is_live) or a.has_algo_id),
    ConstitutionalArticle(
        "A7", "Phase-1 segment scope: NSE cash + NSE options only", ArticleSeverity.HARD,
        ArticleScope.ACTION, lambda a: a.segment in ALLOWED_SEGMENTS),
    ConstitutionalArticle(
        "A8", "Per-trade risk within the configured budget", ArticleSeverity.HARD,
        ArticleScope.ACTION,
        lambda a: a.per_trade_risk_fraction <= a.max_risk_per_trade_fraction + _RISK_EPSILON),
    ConstitutionalArticle(
        "A9", "Intraday-only posture: square-off enforced", ArticleSeverity.HARD,
        ArticleScope.POSTURE, lambda p: p.intraday_only),
    ConstitutionalArticle(
        "A10", f"Config risk-per-trade in (0, {_MAX_ALLOWED_RISK_PER_TRADE}]",
        ArticleSeverity.HARD, ArticleScope.POSTURE,
        lambda p: 0.0 < p.max_risk_per_trade_fraction <= _MAX_ALLOWED_RISK_PER_TRADE),
    ConstitutionalArticle(
        "A11", "Capital-per-trade bounds valid (0 < min ≤ max)", ArticleSeverity.HARD,
        ArticleScope.POSTURE,
        lambda p: 0.0 < p.min_capital_per_trade <= p.max_capital_per_trade),
    ConstitutionalArticle(
        "A12", "Only phase-1 segments enabled", ArticleSeverity.HARD, ArticleScope.POSTURE,
        lambda p: all(s in ALLOWED_SEGMENTS for s in p.enabled_segments)),
    ConstitutionalArticle(
        "A13", "No API secrets committed / exposed", ArticleSeverity.HARD, ArticleScope.POSTURE,
        lambda p: not p.secrets_committed),
    ConstitutionalArticle(
        "A14", "White-box personal-use (not offered to others — else SEBI RA registration)",
        ArticleSeverity.SOFT, ArticleScope.POSTURE, lambda p: p.personal_use_only),
)


class ConstitutionalCore:
    """Reviews proposed actions and system postures against the constitution."""

    def __init__(self, constitution: tuple[ConstitutionalArticle, ...] = CONSTITUTION) -> None:
        self._constitution = constitution

    def review_action(self, action: ProposedTradingAction) -> ConstitutionalVerdict:
        return self._review(action, ArticleScope.ACTION)

    def audit_system_posture(self, posture: SystemPosture) -> ConstitutionalVerdict:
        return self._review(posture, ArticleScope.POSTURE)

    def _review(self, subject: object, scope: ArticleScope) -> ConstitutionalVerdict:
        hard: list[ArticleViolation] = []
        soft: list[ArticleViolation] = []
        for article in self._constitution:
            if article.scope is not scope:
                continue
            if article.predicate(subject):
                continue
            violation = ArticleViolation(
                article.article_id, article.principle, article.severity.value
            )
            (hard if article.severity is ArticleSeverity.HARD else soft).append(violation)
        permitted = not hard
        detail = (
            "compliant with the constitution"
            if permitted and not soft
            else _summarise(hard, soft)
        )
        return ConstitutionalVerdict(
            permitted=permitted,
            scope=scope.value,
            trace_id=_trace_id(subject),
            hard_violations=tuple(hard),
            soft_warnings=tuple(soft),
            detail=detail,
        )


def audit_control_config_posture(control_config) -> ConstitutionalVerdict:
    """Convenience: build the `SystemPosture` from the live `TradingControlConfig` (+ the fixed
    intraday-only / personal-use invariants) and audit it — the constitutional-compliance monitor
    the dashboard surfaces (Trunk VII.1 live consumer, research/109)."""
    posture = SystemPosture(
        intraday_only=True,  # enforced by session_management square-off (a code invariant)
        personal_use_only=True,  # CLAUDE.md: white-box personal use
        max_risk_per_trade_fraction=control_config.max_risk_per_trade_fraction,
        min_capital_per_trade=control_config.min_capital_per_trade,
        max_capital_per_trade=control_config.max_capital_per_trade,
        enabled_segments=tuple(
            s for s, on in control_config.segment_enabled.items() if on
        ),
        secrets_committed=False,  # .env is gitignored; no secret is ever committed
    )
    return ConstitutionalCore().audit_system_posture(posture)


def _summarise(
    hard: list[ArticleViolation], soft: list[ArticleViolation]
) -> str:
    parts = []
    if hard:
        parts.append("BLOCKED — hard: " + ", ".join(f"{v.article_id} ({v.principle})" for v in hard))
    if soft:
        parts.append("warnings: " + ", ".join(f"{v.article_id}" for v in soft))
    return " · ".join(parts)


def _trace_id(subject: object) -> str:
    """Deterministic fingerprint of the subject for the audit trail (no clock/random so the same
    subject always traces identically)."""
    return hashlib.sha1(repr(subject).encode("utf-8")).hexdigest()[:12]
