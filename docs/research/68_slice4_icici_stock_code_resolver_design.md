# Research/68 — §53 Slice 4 (task #6b): ICICI stock-code resolver (design)

**Rule D design doc.** The P4a real-data pass confirmed the bug: Breeze addresses
instruments by ICICI's own **stock_code**, which differs from the NSE symbol
(RELIANCE→empty; ICICI code is `RELIND`). ITC worked only because its code == its
NSE symbol. This resolver maps NSE symbol → ICICI stock_code so the Breeze adapter
works across the full universe (not just the coincidental matches).

## The real source (verified by inspecting it, Rule I/F)
ICICI's `SecurityMaster.zip`
(`https://directlink.icicidirect.com/MotherAppMaster/SecurityMaster.zip`) contains
`NSEScripMaster.txt` (cash) with columns (quotes + leading spaces to strip):
- `ExchangeCode` = the **NSE symbol** (RELIANCE, TCS, ITC, …)
- `ShortName` = the **ICICI stock_code** (HDFCBANK→`HDFBAN`, INFY→`INFTEC`, ITC→`ITC`)
- `Series` = `EQ` for equities (also W3 warrants etc. → filter to EQ)
The SDK also exposes `get_names`, but parsing the master ourselves keeps the
resolver free of the `breeze_connect` import (which does network I/O at import).

## The build (6b)
`market_data/icici_security_master_stock_code_resolver.py`:
- `IciciSecurityMasterStockCodeResolver(nse_symbol_to_icici_code: dict[str,str])` —
  holds the parsed map; `__call__(instrument) -> str` returns the ICICI code for
  the instrument's underlying (options) or trading symbol (cash), **falling back to
  the raw symbol** when unmapped (so it degrades, never crashes). Callable, so it
  drops straight into `BreezeHistoricalBarSource(stock_code_resolver=…)`.
- `from_nse_scrip_master_text(text)` — parses `NSEScripMaster.txt` (strip quote/
  space, `Series=="EQ"`, `ExchangeCode → ShortName`). PURE (no network) → hermetic.
- `download_icici_nse_scrip_master_text()` — the network fetch (unzip → read the
  file), used at the composition root only, kept out of the pure parser (Rule J).

## Verification
- **Hermetic (Rule J):** parse a small fake master → RELIANCE→RELIND, ITC→ITC,
  unknown→fallback; option resolves via underlying.
- **Real data (Rule F):** download the real master → assert RELIANCE→RELIND (and a
  few more), then fetch real Breeze 1-second bars for RELIANCE THROUGH the resolver
  — proving the previously-empty RELIANCE now returns data (closes the P4a bug).

## Wiring (Rule G) & backlog
Consumer: injected as the Breeze adapter's `stock_code_resolver` at the composition
root that builds the Breeze source (the verification script now; the autonomous
service, task #7, later). 6a (Breeze session-token store) is the sibling sub-slice.
