"""The fixed set of NSE index-options underlyings (phase 1 scope).

This list is a stable regulatory/index-launch fact and rarely changes.
Lot sizes DO change often (e.g. the January 2026 lot-size revision) so they
are intentionally NOT hardcoded here — always read current lot sizes off the
live instrument master via `kite_instrument_master_loader`, never off this
file.
"""

NSE_INDEX_OPTION_UNDERLYING_SYMBOLS: tuple[str, ...] = (
    "NIFTY",
    "NIFTYNXT50",
    "FINNIFTY",
    "MIDCPNIFTY",
    "BANKNIFTY",
)

# Trade on BSE, not NSE — deferred to a later phase. Kept here only so
# nothing downstream mistakes them for part of the NSE universe.
BSE_INDEX_OPTION_UNDERLYING_SYMBOLS_DEFERRED: tuple[str, ...] = (
    "SENSEX",
    "BANKEX",
)
