"""Rule-F real-data verification for Trunk VII.1 — the constitutional core (research/109). Audits
the REAL running control-config posture against the constitution, and proves a crafted violating
action is BLOCKED citing the right article.

Run:  python scripts/verify_constitutional_core_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_core import (
    CONSTITUTION,
    ConstitutionalCore,
    ProposedTradingAction,
    audit_control_config_posture,
)
from nse_algo_trader.dashboard.trading_control_config import load_trading_control_config


def main() -> int:
    config = load_trading_control_config()
    print(f"Constitution: {len(CONSTITUTION)} articles "
          f"({sum(1 for a in CONSTITUTION if a.severity.value == 'hard')} hard / "
          f"{sum(1 for a in CONSTITUTION if a.severity.value == 'soft')} soft).")

    # 1. Real running posture must be constitutionally compliant.
    verdict = audit_control_config_posture(config)
    print("\nREAL control-config posture audit:")
    print(f"  permitted = {verdict.permitted} · trace {verdict.trace_id}")
    print(f"  detail: {verdict.detail}")
    assert verdict.permitted, f"the live config VIOLATES the constitution: {verdict.detail}"

    # 2. A crafted violating action must be blocked citing the article.
    core = ConstitutionalCore()
    overnight = ProposedTradingAction(segment="nse_cash_equity", is_overnight_carry=True)
    v = core.review_action(overnight)
    print("\nCrafted overnight-carry action:")
    print(f"  permitted = {v.permitted} · blocked by {[x.article_id for x in v.hard_violations]}")
    assert not v.permitted and "A1" in {x.article_id for x in v.hard_violations}

    out_of_scope = ProposedTradingAction(segment="nse_futures")
    v2 = core.review_action(out_of_scope)
    assert not v2.permitted and "A7" in {x.article_id for x in v2.hard_violations}
    print(f"  out-of-scope (futures) blocked by {[x.article_id for x in v2.hard_violations]}")

    print("\nRESULT: PASS — the live posture is constitutional; violations are blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
