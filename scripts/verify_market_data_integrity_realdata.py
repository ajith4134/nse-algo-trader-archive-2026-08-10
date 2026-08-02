"""Rule-F verification for Trunk VII — market-data integrity / adversarial-input defense
(research/121). Screens the REAL stored benchmark session bars: real market data is clean (no
anomalies), so the defense passes it through and would only block genuinely corrupt/spoofed input.
Also confirms an injected corrupt bar IS caught.

Run:  python scripts/verify_market_data_integrity_realdata.py
"""

from __future__ import annotations

from dataclasses import replace

from nse_algo_trader.conscience.market_data_integrity_defense import screen_bar_series
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    service = LivePaperTradingService(object(), 1_000_000.0)
    sessions = service._load_stored_benchmark_sessions()
    print(f"Loaded {len(sessions)} REAL stored benchmark sessions")
    if not sessions:
        print("RESULT: SKIP — no stored sessions to screen.")
        return 0

    total_bars = 0
    dirty_sessions = 0
    for bars, _ in sessions:
        total_bars += len(bars)
        if not screen_bar_series(bars).clean:
            dirty_sessions += 1
    print(f"Screened {total_bars} REAL bars across {len(sessions)} sessions: "
          f"{dirty_sessions} session(s) with anomalies")
    assert dirty_sessions == 0, "real stored market data should screen clean"

    # Inject a corrupt (crossed-candle) bar into a real session → the defense must catch it.
    real_bars = list(sessions[0][0])
    corrupted = real_bars[:-1] + [replace(real_bars[-1], high_price=real_bars[-1].low_price - 1)]
    verdict = screen_bar_series(corrupted)
    print(f"Injected a crossed-candle into a real session → clean={verdict.clean} "
          f"anomalies={verdict.anomalies[:3]}")
    assert not verdict.clean

    print("\nRESULT: PASS — the adversarial-input defense passes REAL clean market data and catches "
          "an injected corrupt bar (no trade on poisoned data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
