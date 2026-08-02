"""Rule F real-data verification for the index-level option gate (Trunk II SENSES, research/151).

Reads the REAL stored S2 index news_levels and shows the gate's behaviour at a spot near a real level:
cold-start identity (safe) vs earned → size-down/defer — proving the S2 index levels are now WIRED into
the option entry decision (not display-only).
"""

from nse_algo_trader.news_sentiment.index_level_gate import (
    index_level_size_multiplier,
    nearest_level_distance_pct,
)
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore
from nse_algo_trader.universe_registry.nse_index_options_reference import (
    NSE_INDEX_OPTION_UNDERLYING_SYMBOLS,
)


def main() -> None:
    index_symbols = set(NSE_INDEX_OPTION_UNDERLYING_SYMBOLS)
    store = NewsSqliteStore()
    try:
        levels_by_underlying: dict = {}
        for s in store.load_recent_levels(limit=200):
            if s.underlying in index_symbols:
                levels_by_underlying.setdefault(s.underlying, []).extend(l.value for l in s.levels)
    finally:
        store.close()

    print("=== REAL stored index S/R levels (now wired into the option gate) ===")
    for u, vals in sorted(levels_by_underlying.items()):
        print(f"  {u}: {sorted(set(vals))}")

    if "NIFTY" in levels_by_underlying:
        levels = levels_by_underlying["NIFTY"]
        spot = 24010.0  # near the real 24,000 level
        print(f"\n=== gate at NIFTY spot {spot:,.0f} (nearest level "
              f"{min(levels, key=lambda l: abs(l-spot)):,.0f}, "
              f"{nearest_level_distance_pct(spot, levels):.2%} away) ===")
        print(f"  cold start (NOT earned): multiplier = "
              f"{index_level_size_multiplier(spot, levels, calibration_earned=False):.2f}  → SAFE (identity)")
        print(f"  once EARNED:             multiplier = "
              f"{index_level_size_multiplier(spot, levels, calibration_earned=True):.2f}  → "
              f"sizes-down/defers an entry sitting on the level")
    else:
        print("\n(no NIFTY index levels stored yet — run the S2 index extraction first.)")


if __name__ == "__main__":
    main()
