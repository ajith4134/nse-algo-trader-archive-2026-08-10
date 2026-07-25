"""PointInTimeUniverseResolver — survivorship-free per-date universe (research/62
P2, research/53 §11.1). Verified on REAL stored NSE bhavcopy (Rule F); auto-skips
where the real store is absent.
"""

from datetime import date
from pathlib import Path

import pytest

from nse_algo_trader.market_data import MarketDataSqliteStore
from nse_algo_trader.paper_trading.point_in_time_universe_resolver import (
    OptionContractIdentity,
    PointInTimeUniverseResolver,
)

_REAL_STORE = Path("~/.nse_algo_trader/market_data.sqlite3").expanduser()
_DATE_WITH_CASH_AND_FO = date(2026, 7, 23)  # both bhavcopies ingested


def _resolver() -> tuple[PointInTimeUniverseResolver, MarketDataSqliteStore]:
    if not _REAL_STORE.exists():
        pytest.skip("real market_data store not present (CI / fresh checkout)")
    store = MarketDataSqliteStore(db_file_path=_REAL_STORE)
    return PointInTimeUniverseResolver(store), store


def test_cash_universe_is_the_real_eq_series_traded_that_day():
    resolver, store = _resolver()
    try:
        cash = resolver.cash_equity_universe_on(_DATE_WITH_CASH_AND_FO)
        # The real NSE EQ segment is ~2,000+ names — a full universe, not a sample.
        assert len(cash) > 1500
        # Only EQ-series symbols; a govt-security (GS series) that traded that day
        # must be EXCLUDED from the intraday cash universe.
        raw_rows = store.load_cash_bhavcopy_delivery_rows(_DATE_WITH_CASH_AND_FO)
        eq_symbols = {r.symbol for r in raw_rows if r.series == "EQ"}
        assert cash == eq_symbols
        non_eq = {r.symbol for r in raw_rows if r.series != "EQ"}
        assert cash.isdisjoint(non_eq)
    finally:
        store.close()


def test_option_underlyings_are_the_fo_eligibility_snapshot_of_that_day():
    resolver, store = _resolver()
    try:
        underlyings = resolver.option_underlyings_on(_DATE_WITH_CASH_AND_FO)
        # Index + single-stock option underlyings — the full ~215, not a sample.
        assert len(underlyings) > 150
        assert "NIFTY" in underlyings  # index options present
        assert "RELIANCE" in underlyings  # a liquid stock-option underlying
    finally:
        store.close()


def test_option_contracts_are_well_formed_and_non_empty():
    resolver, store = _resolver()
    try:
        contracts = resolver.option_contracts_on(_DATE_WITH_CASH_AND_FO)
        assert len(contracts) > 1000  # full strike/expiry ladders
        sample = contracts[0]
        assert isinstance(sample, OptionContractIdentity)
        assert sample.option_right_code in {"CE", "PE"}
        assert sample.strike_price > 0
        # Every contract's underlying is in the eligibility snapshot.
        underlyings = resolver.option_underlyings_on(_DATE_WITH_CASH_AND_FO)
        assert all(c.underlying_symbol in underlyings for c in contracts)
    finally:
        store.close()


def test_resolve_bundles_cash_and_options_for_a_real_date():
    resolver, store = _resolver()
    try:
        universe = resolver.resolve(_DATE_WITH_CASH_AND_FO)
        assert universe.trade_date == _DATE_WITH_CASH_AND_FO
        assert universe.cash_equity_count > 1500
        assert universe.option_underlying_count > 150
        assert len(universe.option_contracts) > 1000
    finally:
        store.close()


def test_has_universe_for_is_false_for_an_uningested_date():
    resolver, store = _resolver()
    try:
        assert resolver.has_universe_for(_DATE_WITH_CASH_AND_FO) is True
        assert resolver.has_universe_for(date(2005, 1, 3)) is False
    finally:
        store.close()
