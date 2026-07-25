"""Maps an Instrument → Upstox's `instrument_key`, for addressing the Upstox
historical source (task #22; research/82).

Upstox does not address instruments by NSE symbol — it uses an `instrument_key`
(`NSE_EQ|<ISIN>` for cash, `NSE_FO|<token>` for F&O) drawn from its own instrument
master. This resolver parses that master (the real, public `NSE.json.gz`) into two
lookups and plugs straight into `UpstoxHistoricalBarSource(upstox_instrument_key_
resolver=…)`:
  - cash equity: NSE trading symbol → instrument_key
  - options: (underlying, CE/PE, strike, expiry date) → instrument_key

The parser is PURE (no network) so it is hermetically testable; the download is a
separate function used only at the composition root (mirrors
`icici_security_master_stock_code_resolver`).
"""

from __future__ import annotations

import gzip
import json
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_INDIA_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
_NSE_INSTRUMENT_MASTER_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)
_CASH_SEGMENT = "NSE_EQ"
_FNO_SEGMENT = "NSE_FO"
_OPTION_INSTRUMENT_TYPES = frozenset({"CE", "PE"})
_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)

# (underlying_symbol, "CE"/"PE", strike rounded to 2dp, expiry date) — the option key.
OptionContractKey = tuple[str, str, float, date]


def _option_contract_key(
    underlying_symbol: str, option_right: str, strike_price: float, expiry: date
) -> OptionContractKey:
    return (underlying_symbol, option_right, round(float(strike_price), 2), expiry)


def _expiry_epoch_ms_to_ist_date(expiry_epoch_ms: int) -> date:
    return datetime.fromtimestamp(
        int(expiry_epoch_ms) / 1000, _INDIA_MARKET_TIMEZONE
    ).date()


class UpstoxInstrumentKeyResolver:
    """Callable Instrument → Upstox instrument_key resolver for the Upstox adapter."""

    def __init__(
        self,
        cash_instrument_key_by_symbol: dict[str, str],
        option_instrument_key_by_contract: dict[OptionContractKey, str],
    ) -> None:
        self._cash_instrument_key_by_symbol = cash_instrument_key_by_symbol
        self._option_instrument_key_by_contract = option_instrument_key_by_contract

    @classmethod
    def from_instrument_master_records(
        cls, instrument_master_records: list[dict]
    ) -> "UpstoxInstrumentKeyResolver":
        """Parse Upstox instrument-master records (NSE_EQ + NSE_FO options) into the
        two instrument_key lookups. Non-option F&O (futures) and other segments are
        ignored — this project trades cash + options only."""
        cash_by_symbol: dict[str, str] = {}
        option_by_contract: dict[OptionContractKey, str] = {}
        for record in instrument_master_records:
            segment = record.get("segment")
            instrument_key = record.get("instrument_key")
            if not instrument_key:
                continue
            if segment == _CASH_SEGMENT:
                trading_symbol = record.get("trading_symbol")
                if trading_symbol:
                    cash_by_symbol[trading_symbol] = instrument_key
            elif segment == _FNO_SEGMENT:
                instrument_type = record.get("instrument_type")
                if instrument_type not in _OPTION_INSTRUMENT_TYPES:
                    continue  # skip futures (FUT) — options only
                underlying = record.get("underlying_symbol")
                strike = record.get("strike_price")
                expiry_ms = record.get("expiry")
                if underlying is None or strike is None or expiry_ms is None:
                    continue
                key = _option_contract_key(
                    underlying, instrument_type, strike,
                    _expiry_epoch_ms_to_ist_date(expiry_ms),
                )
                option_by_contract[key] = instrument_key
        return cls(cash_by_symbol, option_by_contract)

    def instrument_key_for(self, instrument: Instrument) -> str:
        if instrument.kind in _OPTION_INSTRUMENT_KINDS:
            key = _option_contract_key(
                instrument.underlying_symbol,
                instrument.option_right.value,
                instrument.strike_price,
                instrument.expiry_date,
            )
            instrument_key = self._option_instrument_key_by_contract.get(key)
            if instrument_key is None:
                raise KeyError(
                    f"{instrument.trading_symbol}: no Upstox instrument_key for option "
                    f"{key} — not in the NSE_FO master (check expiry/strike/underlying)"
                )
            return instrument_key
        instrument_key = self._cash_instrument_key_by_symbol.get(instrument.trading_symbol)
        if instrument_key is None:
            raise KeyError(
                f"{instrument.trading_symbol}: no Upstox instrument_key in the NSE_EQ "
                "master (delisted, or a non-cash symbol)"
            )
        return instrument_key

    def __call__(self, instrument: Instrument) -> str:
        return self.instrument_key_for(instrument)

    def cash_symbol_count(self) -> int:
        return len(self._cash_instrument_key_by_symbol)

    def option_contract_count(self) -> int:
        return len(self._option_instrument_key_by_contract)


def download_upstox_nse_instrument_master_records(
    instrument_master_url: str = _NSE_INSTRUMENT_MASTER_URL, timeout_seconds: int = 90
) -> list[dict]:
    """Fetch + gunzip Upstox's public NSE instrument master into a list of records.
    Network I/O — call at the composition root, not in the parser."""
    gzipped_bytes = urllib.request.urlopen(
        instrument_master_url, timeout=timeout_seconds
    ).read()
    return json.loads(gzip.decompress(gzipped_bytes))
