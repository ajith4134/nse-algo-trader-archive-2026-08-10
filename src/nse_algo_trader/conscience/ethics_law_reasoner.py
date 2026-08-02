"""Ethics / law reasoner (Trunk VII; research/119) — CONSCIENCE regulatory-compliance organ.

A machine conscience must REASON about the law it operates under, not just obey hard-coded
invariants. This bot runs under SEBI's Feb-2025 algo-trading framework (mandatory Apr-1-2026). The
reasoner holds the SEBI algo rulebook as DATA (each rule + its citation), reasons the system's
current regulatory posture against every rule, and produces a cited compliance report — surfacing
exactly which rule would be breached and why. Distinct from the constitution (which ENFORCES
structural articles at order time): this REASONS about and cites the rulebook, like a compliance
review. PURE (no I/O) — the service builds the posture from the real config + structural facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# SEBI's white-box threshold: >= 10 orders/sec/exchange/client crosses into mandatory registration.
SEBI_WHITE_BOX_ORDER_RATE_CEILING = 10


@dataclass(frozen=True)
class RegulatoryRule:
    rule_id: str
    title: str
    citation: str


SEBI_ALGO_RULEBOOK: tuple[RegulatoryRule, ...] = (
    RegulatoryRule("ORDER_RATE", "Order-rate under the white-box ceiling",
                   "SEBI Algo Framework (Feb 2025): <10 orders/sec/exchange/client stays white-box"),
    RegulatoryRule("BROKER_PRINCIPAL", "Broker is principal, bot is agent",
                   "SEBI Algo Framework: orders route THROUGH the broker API, never direct-to-exchange"),
    RegulatoryRule("ALGO_ID", "Every order carries the exchange Algo-ID",
                   "SEBI Algo Framework: exchange-assigned Algo-ID on every algo order"),
    RegulatoryRule("INTRADAY_ONLY", "No overnight carry (intraday-only)",
                   "Project mandate under SEBI framework: square-off before close, no overnight risk"),
    RegulatoryRule("WHITE_BOX_PERSONAL", "Personal white-box use (not offered to others)",
                   "SEBI: offering strategies/signals to others ⇒ Research-Analyst registration"),
)


@dataclass(frozen=True)
class RegulatoryPosture:
    max_orders_per_second: int
    routes_through_broker: bool
    carries_algo_id: bool
    intraday_only: bool
    offered_to_others: bool
    trading_mode: str = "paper"


@dataclass(frozen=True)
class LawFinding:
    rule_id: str
    title: str
    compliant: bool
    severity: str  # 'ok' | 'violation'
    reason: str
    citation: str


@dataclass(frozen=True)
class LawComplianceReport:
    findings: tuple[LawFinding, ...]
    compliant: bool
    violations: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


def _finding(rule: RegulatoryRule, compliant: bool, reason: str) -> LawFinding:
    return LawFinding(
        rule_id=rule.rule_id, title=rule.title, compliant=compliant,
        severity="ok" if compliant else "violation", reason=reason, citation=rule.citation,
    )


def assess_regulatory_compliance(posture: RegulatoryPosture) -> LawComplianceReport:
    """Reason the system's regulatory posture against the SEBI algo rulebook and return a cited
    compliance report. A single non-compliant rule makes the whole report non-compliant."""
    by_id = {r.rule_id: r for r in SEBI_ALGO_RULEBOOK}
    findings: list[LawFinding] = []

    rate_ok = posture.max_orders_per_second < SEBI_WHITE_BOX_ORDER_RATE_CEILING
    findings.append(_finding(
        by_id["ORDER_RATE"], rate_ok,
        f"throttle ceiling {posture.max_orders_per_second}/s "
        f"{'<' if rate_ok else '≥'} {SEBI_WHITE_BOX_ORDER_RATE_CEILING}/s white-box limit",
    ))
    findings.append(_finding(
        by_id["BROKER_PRINCIPAL"], posture.routes_through_broker,
        "all orders route through the broker API" if posture.routes_through_broker
        else "DIRECT-TO-EXCHANGE routing detected — prohibited",
    ))
    findings.append(_finding(
        by_id["ALGO_ID"], posture.carries_algo_id,
        "orders carry the exchange Algo-ID" if posture.carries_algo_id
        else "orders missing the exchange Algo-ID",
    ))
    findings.append(_finding(
        by_id["INTRADAY_ONLY"], posture.intraday_only,
        "intraday-only, square-off before close" if posture.intraday_only
        else "OVERNIGHT carry enabled — prohibited",
    ))
    findings.append(_finding(
        by_id["WHITE_BOX_PERSONAL"], not posture.offered_to_others,
        "personal white-box use (not distributed)" if not posture.offered_to_others
        else "OFFERED TO OTHERS — triggers SEBI Research-Analyst registration",
    ))

    violations = tuple(f.rule_id for f in findings if not f.compliant)
    compliant = not violations
    summary = (
        f"regulatory posture COMPLIANT across {len(findings)} SEBI rules (mode={posture.trading_mode})"
        if compliant else
        f"regulatory VIOLATION(S): {', '.join(violations)} — "
        + "; ".join(f.reason for f in findings if not f.compliant)
    )
    return LawComplianceReport(
        findings=tuple(findings), compliant=compliant, violations=violations, summary=summary,
    )
