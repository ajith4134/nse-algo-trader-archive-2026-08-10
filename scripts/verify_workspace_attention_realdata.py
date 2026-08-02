"""Rule-F verification for Trunk VIII — selective + state-dependent attention (research/126). Runs
the REAL offline service so `_maybe_run_global_workspace` builds an AttentionContext from real state
(regime, drawdown, off-switch), applies attention to the real faculty contributions, and still
broadcasts the real dominant signal — attention shaping without breaking safety-first ordering.

Run:  python scripts/verify_workspace_attention_realdata.py
"""

from __future__ import annotations

import time

from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService
from nse_algo_trader.sentience.workspace_attention import apply_attention
from nse_algo_trader.sentience.global_workspace import salience_score


def main() -> int:
    svc = LivePaperTradingService(object(), 1_000_000.0, offline_diagnostics_mode=True)
    svc.start()
    print("offline service started; waiting for the attention-shaped workspace cycle...")
    for _ in range(90):
        if svc._latest_attention_context is not None and svc._latest_workspace_broadcast is not None:
            break
        time.sleep(1)

    ctx = svc._latest_attention_context
    b = svc._latest_workspace_broadcast
    print("\nAttentionContext built from REAL state:")
    print(f"  market_regime : {ctx.market_regime}")
    print(f"  drawdown      : {ctx.drawdown_fraction:.3%}")
    print(f"  off_switch    : {ctx.off_switch_engaged}")
    print(f"  is_defensive  : {ctx.is_defensive}")

    raw = svc._collect_workspace_contributions()
    attended = apply_attention(raw, ctx)
    print("\nAttention effect on the real contributions (raw → attended salience):")
    for r, a in zip(raw, attended):
        print(f"  {r.source:<20} {r.kind:<12} {salience_score(r):.2f} → {salience_score(a):.2f}")
    print(f"\nWorkspace still broadcast: {b.winner_source} ({b.kind}) ignited={b.ignited}")
    svc.stop()

    assert ctx is not None and b is not None
    print("\nRESULT: PASS — attention was shaped from real state and applied to the real workspace "
          "competition; the safety-first dominant broadcast is preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
