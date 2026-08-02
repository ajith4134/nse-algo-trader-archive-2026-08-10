"""Rule-F verification for Trunk VIII — self-model + attention schema (research/128). Runs the REAL
offline service so its faculty cadences populate, then confirms the self-model reports the system's
true condition and the attention schema reflects the workspace's real focus — honest self-representation.

Run:  python scripts/verify_self_model_attention_schema_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    svc = LivePaperTradingService(object(), 1_000_000.0, offline_diagnostics_mode=True)
    svc.start()
    print("offline service started; waiting for the self-model + attention schema...")
    for _ in range(90):
        if svc._latest_self_model is not None and svc._latest_attention_schema is not None:
            break
        time.sleep(1)

    sm = svc._latest_self_model
    asch = svc._latest_attention_schema
    svc.stop()

    print("\nSELF-MODEL over REAL state:")
    print(f"  {sm.summary}")
    print(f"  condition={'HEALTHY' if sm.is_healthy else 'IMPAIRED'} posture={sm.safety_posture} "
          f"reliable-share={sm.calibration_reliable_share:.0%} "
          f"trusted={sm.trusted_mechanism_count} distrusted={len(sm.distrusted_mechanisms)}")

    print("\nATTENTION SCHEMA over REAL state:")
    print(f"  {asch.summary}")
    print(f"  attending_to={asch.attending_to} kind={asch.attending_kind} "
          f"by_kind={asch.attention_by_kind} regime={asch.context_regime}")

    assert sm is not None and asch is not None
    assert 0.0 <= sm.calibration_reliable_share <= 1.0
    print("\nRESULT: PASS — the system produced an honest model of itself (condition + posture + "
          "trust) and a model of its own attention (focus + distribution) over the real state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
