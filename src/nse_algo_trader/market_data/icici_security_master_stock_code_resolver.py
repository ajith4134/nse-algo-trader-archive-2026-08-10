"""Maps an NSE symbol → ICICI Direct's own **stock_code**, for addressing the
Breeze historical source (§53 slice 4 task #6b; research/68).

Breeze addresses instruments by ICICI's stock_code, which differs from the NSE
symbol for many names (RELIANCE → `RELIND`, INFY → `INFTEC`, HDFCBANK → `HDFBAN`).
The P4a real-data pass caught this (RELIANCE returned nothing). This resolver
parses ICICI's `SecurityMaster` (`NSEScripMaster.txt`: `ExchangeCode` = NSE symbol,
`ShortName` = ICICI code, `Series == "EQ"`) into that map and plugs straight into
`BreezeHistoricalBarSource(stock_code_resolver=…)`.

The parser is PURE (no network) so it is hermetically testable; the download is a
separate function used only at the composition root.
"""

from __future__ import annotations

import csv
import io
import urllib.request
import zipfile

from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_SECURITY_MASTER_ZIP_URL = (
    "https://directlink.icicidirect.com/MotherAppMaster/SecurityMaster.zip"
)
_NSE_CASH_SCRIP_MASTER_FILENAME = "NSEScripMaster.txt"
_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)


def _clean(cell: str) -> str:
    return cell.strip().strip('"').strip()


class IciciSecurityMasterStockCodeResolver:
    """Callable NSE-symbol → ICICI-stock_code resolver for the Breeze adapter."""

    def __init__(self, nse_symbol_to_icici_code: dict[str, str]) -> None:
        self._nse_symbol_to_icici_code = nse_symbol_to_icici_code

    @classmethod
    def from_nse_scrip_master_text(cls, nse_scrip_master_text: str) -> "IciciSecurityMasterStockCodeResolver":
        """Parse `NSEScripMaster.txt` (EQ series only) into the symbol→code map."""
        rows = list(csv.reader(nse_scrip_master_text.splitlines()))
        header = [_clean(h) for h in rows[0]]
        index = {name: i for i, name in enumerate(header)}
        exchange_code_col = index["ExchangeCode"]
        short_name_col = index["ShortName"]
        series_col = index["Series"]
        mapping: dict[str, str] = {}
        for row in rows[1:]:
            if len(row) <= max(exchange_code_col, short_name_col, series_col):
                continue
            if _clean(row[series_col]) != "EQ":
                continue
            nse_symbol = _clean(row[exchange_code_col])
            icici_code = _clean(row[short_name_col])
            if nse_symbol and icici_code:
                mapping[nse_symbol] = icici_code
        return cls(mapping)

    def icici_code_for_symbol(self, nse_symbol: str) -> str:
        """The ICICI stock_code for an NSE symbol, or the symbol itself if unmapped
        (a graceful fallback — many codes DO match, and an index like NIFTY is
        addressed by its own name)."""
        return self._nse_symbol_to_icici_code.get(nse_symbol, nse_symbol)

    def __call__(self, instrument: Instrument) -> str:
        nse_symbol = (
            instrument.underlying_symbol
            if instrument.kind in _OPTION_INSTRUMENT_KINDS
            else instrument.trading_symbol
        )
        return self.icici_code_for_symbol(nse_symbol)

    def symbol_count(self) -> int:
        return len(self._nse_symbol_to_icici_code)


def download_icici_nse_scrip_master_text(
    security_master_zip_url: str = _SECURITY_MASTER_ZIP_URL, timeout_seconds: int = 60
) -> str:
    """Fetch + unzip ICICI's SecurityMaster and return the raw NSE cash scrip
    master text. Network I/O — call at the composition root, not in the parser."""
    zip_bytes = urllib.request.urlopen(security_master_zip_url, timeout=timeout_seconds).read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        return archive.read(_NSE_CASH_SCRIP_MASTER_FILENAME).decode("latin-1")
