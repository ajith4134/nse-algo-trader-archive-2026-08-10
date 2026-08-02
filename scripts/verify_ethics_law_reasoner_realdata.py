"""Rule-F verification for Trunk VII — ethics/law reasoner (research/119). Builds the REAL regulatory
posture (the real SEBI order-rate throttle ceiling + the bot's structural facts + the real trading
mode from config) and reasons it against the SEBI algo rulebook, printing the cited compliance
report. The live posture is expected COMPLIANT — an honest cited all-clear.

Run:  python scripts/verify_ethics_law_reasoner_realdata.py
"""

from __future__ import annotations

from nse_algo_trader.broker_oms.order_rate_limiter import OrderRateLimiter
from nse_algo_trader.conscience.ethics_law_reasoner import (
    RegulatoryPosture,
    assess_regulatory_compliance,
)
from nse_algo_trader.dashboard.trading_control_config import load_trading_control_config


def main() -> int:
    config = load_trading_control_config()
    posture = RegulatoryPosture(
        max_orders_per_second=OrderRateLimiter().max_orders_per_second,
        routes_through_broker=True, carries_algo_id=True, intraday_only=True,
        offered_to_others=False,
        trading_mode=getattr(config.trading_mode, "value", str(config.trading_mode)),
    )
    report = assess_regulatory_compliance(posture)
    print(f"Regulatory posture (real config, throttle ceiling {posture.max_orders_per_second}/s, "
          f"mode={posture.trading_mode}):")
    for f in report.findings:
        mark = "OK " if f.compliant else "VIOLATION"
        print(f"  [{mark}] {f.rule_id:<18} {f.reason}")
        print(f"           cite: {f.citation}")
    print(f"\n  summary: {report.summary}")

    assert report.compliant, f"the live posture should be compliant; violations={report.violations}"
    print("\nRESULT: PASS — the ethics/law reasoner finds the live regulatory posture COMPLIANT "
          "across all SEBI algo rules, with citations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
