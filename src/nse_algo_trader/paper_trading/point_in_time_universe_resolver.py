"""Reconstructs the REAL tradeable NSE universe AS IT WAS on a past trading
date — survivorship-bias-free (research/62 part P2; research/53 §11.1).

When the sim rewinds to a past day, it must trade *that day's* universe, not
today's projected backward: a stock that has since delisted but traded that day
must be present, and a name not yet listed (or not yet F&O-eligible) that day
must be absent. Projecting today's survivor list onto the past is the classic
backtest lie — it teaches the bot the market was safer and narrower than it was.

The truth of "what traded that day" is the official NSE bhavcopy already in the
Layer-2 store: `cash_bhavcopy_delivery` lists every cash symbol that traded, and
`fo_bhavcopy_contracts` lists every option/future contract that traded (so the
distinct option underlyings ARE the F&O-eligibility snapshot for that date).
This resolver reads those, filtered to the intraday-eligible cash segment and to
option contracts, and returns the point-in-time universe.

Deep-history masters (delisted list, index-constituent history) refine this
further (BACKLOG); bhavcopy alone already gives a correct *traded-that-day* set
for every date we have ingested — no survivorship bias by construction.
"""

from dataclasses import dataclass
from datetime import date

from nse_algo_trader.market_data import MarketDataSqliteStore

# The intraday-eligible cash segment is the normal rolling-settlement equity
# series `EQ`. Excluded (not intraday-squareable / not the equity universe):
# BE/BZ (trade-to-trade — delivery mandatory), SM/ST (SME), GS/GB/MF/IV/... (non
# equity). Configurable, so a later phase can widen it deliberately.
_DEFAULT_INTRADAY_ELIGIBLE_CASH_SERIES = frozenset({"EQ"})

# F&O bhavcopy contract-type codes that are OPTIONS (index + stock). Futures
# (IDF/STF) are a deferred phase and excluded here.
_OPTION_CONTRACT_TYPE_CODES = frozenset({"IDO", "STO"})


@dataclass(frozen=True)
class OptionContractIdentity:
    """One option contract that actually traded on the date — the atoms of the
    point-in-time option universe (strike/expiry ladders come from these)."""

    underlying_symbol: str
    expiry_date: date
    strike_price: float
    option_right_code: str  # "CE" (call) / "PE" (put)
    nse_instrument_id: int


@dataclass(frozen=True)
class PointInTimeUniverse:
    """The real tradeable set for one past date: cash symbols, option
    underlyings (the F&O-eligibility snapshot), and the option contracts."""

    trade_date: date
    cash_equity_symbols: frozenset[str]
    option_underlyings: frozenset[str]
    option_contracts: tuple[OptionContractIdentity, ...]

    @property
    def cash_equity_count(self) -> int:
        return len(self.cash_equity_symbols)

    @property
    def option_underlying_count(self) -> int:
        return len(self.option_underlyings)


class PointInTimeUniverseResolver:
    def __init__(
        self,
        market_data_store: MarketDataSqliteStore,
        intraday_eligible_cash_series: frozenset[str] = (
            _DEFAULT_INTRADAY_ELIGIBLE_CASH_SERIES
        ),
    ) -> None:
        self._market_data_store = market_data_store
        self._intraday_eligible_cash_series = intraday_eligible_cash_series

    def cash_equity_universe_on(self, trade_date: date) -> frozenset[str]:
        """Every intraday-eligible cash symbol that actually traded on
        `trade_date` (from that date's real cash bhavcopy)."""
        return frozenset(
            row.symbol
            for row in self._market_data_store.load_cash_bhavcopy_delivery_rows(
                trade_date
            )
            if row.series in self._intraday_eligible_cash_series
        )

    def option_underlyings_on(self, trade_date: date) -> frozenset[str]:
        """The distinct underlyings that had option contracts trading on
        `trade_date` — the F&O-eligibility snapshot as of that date."""
        return frozenset(
            row.underlying_symbol
            for row in self._market_data_store.load_fo_bhavcopy_contract_rows(
                trade_date
            )
            if row.contract_type.value in _OPTION_CONTRACT_TYPE_CODES
        )

    def option_contracts_on(
        self, trade_date: date
    ) -> tuple[OptionContractIdentity, ...]:
        """Every option contract that actually traded on `trade_date` (the
        strike/expiry ladder per underlying, as it really was)."""
        return tuple(
            OptionContractIdentity(
                underlying_symbol=row.underlying_symbol,
                expiry_date=row.expiry_date,
                strike_price=row.strike_price,
                option_right_code=row.option_right_code,
                nse_instrument_id=row.nse_instrument_id,
            )
            for row in self._market_data_store.load_fo_bhavcopy_contract_rows(
                trade_date
            )
            if row.contract_type.value in _OPTION_CONTRACT_TYPE_CODES
        )

    def has_universe_for(self, trade_date: date) -> bool:
        """True when this date has ingested bhavcopy to reconstruct from — the
        gate the archive walk uses so it only replays dates it can resolve."""
        return bool(
            self._market_data_store.load_cash_bhavcopy_delivery_rows(trade_date)
        ) or bool(
            self._market_data_store.load_fo_bhavcopy_contract_rows(trade_date)
        )

    def resolve(self, trade_date: date) -> PointInTimeUniverse:
        return PointInTimeUniverse(
            trade_date=trade_date,
            cash_equity_symbols=self.cash_equity_universe_on(trade_date),
            option_underlyings=self.option_underlyings_on(trade_date),
            option_contracts=self.option_contracts_on(trade_date),
        )
