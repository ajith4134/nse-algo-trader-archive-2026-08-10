"""Maps an Instrument → Angel One's numeric `symboltoken`, for addressing the
Angel One historical source (task #18/#22; research/81, /83).

Angel One's `getCandleData` addresses instruments by a numeric `symboltoken` from
its own **OpenAPIScripMaster** (not our Kite token, not the NSE symbol). This resolver
parses that real, public master into two lookups and plugs straight into
`AngelOneHistoricalBarSource(angel_symbol_token_resolver=…)`:
  - cash equity: NSE symbol → symboltoken   (rows `exch_seg=="NSE"`, `symbol` ends `-EQ`)
  - options: (underlying, CE/PE, strike, expiry) → symboltoken   (rows `exch_seg=="NFO"`,
    `instrumenttype` OPTIDX/OPTSTK; master `strike` is ×100, `expiry` is `DDMMMYYYY`)

The parser is PURE (no network) so it is hermetically testable; the download is a
separate function used only at the composition root (mirrors
`upstox_instrument_key_resolver` / `icici_security_master_stock_code_resolver`).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime

from nse_algo_trader.universe_registry import Instrument, InstrumentKind

_SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)
_CASH_EXCH_SEG = "NSE"
_FNO_EXCH_SEG = "NFO"
_OPTION_INSTRUMENT_TYPES = frozenset({"OPTIDX", "OPTSTK"})
_OPTION_RIGHTS = frozenset({"CE", "PE"})
_ANGEL_STRIKE_SCALE = 100.0  # master strike is in paise (×100 of the rupee strike)
_OPTION_INSTRUMENT_KINDS = frozenset(
    {InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION}
)

# (underlying_symbol, "CE"/"PE", strike rounded to 2dp, expiry date) — the option key.
OptionContractKey = tuple[str, str, float, date]


def _option_contract_key(
    underlying_symbol: str, option_right: str, strike_price: float, expiry: date
) -> OptionContractKey:
    return (underlying_symbol, option_right, round(float(strike_price), 2), expiry)


def _parse_angel_expiry(expiry_text: str) -> date:
    """Angel expiry is `DDMMMYYYY` (e.g. `29DEC2026`); %b is case-insensitive."""
    return datetime.strptime(expiry_text, "%d%b%Y").date()


class AngelOneSymbolTokenResolver:
    """Callable Instrument → Angel symboltoken resolver for the Angel One adapter."""

    def __init__(
        self,
        cash_token_by_symbol: dict[str, str],
        option_token_by_contract: dict[OptionContractKey, str],
    ) -> None:
        self._cash_token_by_symbol = cash_token_by_symbol
        self._option_token_by_contract = option_token_by_contract

    @classmethod
    def from_scrip_master_records(
        cls, scrip_master_records: list[dict]
    ) -> "AngelOneSymbolTokenResolver":
        """Parse OpenAPIScripMaster records (NSE cash + NFO options) into the two
        symboltoken lookups. Futures (FUTSTK/FUTIDX) and other exchanges are ignored —
        this project trades NSE cash + options only."""
        cash_by_symbol: dict[str, str] = {}
        option_by_contract: dict[OptionContractKey, str] = {}
        for record in scrip_master_records:
            token = record.get("token")
            if not token:
                continue
            exch_seg = record.get("exch_seg")
            if exch_seg == _CASH_EXCH_SEG:
                symbol = str(record.get("symbol", ""))
                name = record.get("name")
                if name and symbol.endswith("-EQ"):
                    cash_by_symbol[name] = token
            elif exch_seg == _FNO_EXCH_SEG:
                if record.get("instrumenttype") not in _OPTION_INSTRUMENT_TYPES:
                    continue  # futures — skip
                symbol = str(record.get("symbol", ""))
                option_right = symbol[-2:]
                underlying = record.get("name")
                strike_raw = record.get("strike")
                expiry_text = record.get("expiry")
                if (
                    option_right not in _OPTION_RIGHTS
                    or underlying is None
                    or strike_raw in (None, "")
                    or not expiry_text
                ):
                    continue
                key = _option_contract_key(
                    underlying, option_right,
                    float(strike_raw) / _ANGEL_STRIKE_SCALE,
                    _parse_angel_expiry(expiry_text),
                )
                option_by_contract[key] = token
        return cls(cash_by_symbol, option_by_contract)

    def symbol_token_for(self, instrument: Instrument) -> str:
        if instrument.kind in _OPTION_INSTRUMENT_KINDS:
            key = _option_contract_key(
                instrument.underlying_symbol,
                instrument.option_right.value,
                instrument.strike_price,
                instrument.expiry_date,
            )
            token = self._option_token_by_contract.get(key)
            if token is None:
                raise KeyError(
                    f"{instrument.trading_symbol}: no Angel symboltoken for option "
                    f"{key} — not in the NFO master (check expiry/strike/underlying)"
                )
            return token
        token = self._cash_token_by_symbol.get(instrument.trading_symbol)
        if token is None:
            raise KeyError(
                f"{instrument.trading_symbol}: no Angel symboltoken in the NSE cash "
                "master (delisted, or a non-cash symbol)"
            )
        return token

    def __call__(self, instrument: Instrument) -> str:
        return self.symbol_token_for(instrument)

    def cash_symbol_count(self) -> int:
        return len(self._cash_token_by_symbol)

    def option_contract_count(self) -> int:
        return len(self._option_token_by_contract)


def download_angel_one_scrip_master_records(
    scrip_master_url: str = _SCRIP_MASTER_URL, timeout_seconds: int = 90
) -> list[dict]:
    """Fetch Angel One's public OpenAPIScripMaster into a list of records. Network
    I/O — call at the composition root, not in the parser."""
    return json.loads(
        urllib.request.urlopen(scrip_master_url, timeout=timeout_seconds).read()
    )
