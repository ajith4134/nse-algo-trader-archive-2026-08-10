"""§53 slice 4 task #6b — ICICI stock-code resolver (hermetic, Rule J + real-data
Rule F). The parser is exercised on a trimmed master; the guarded real-data test
downloads ICICI's actual SecurityMaster and asserts the known mappings.
"""

import os
from datetime import date

import pytest

from nse_algo_trader.market_data.icici_security_master_stock_code_resolver import (
    IciciSecurityMasterStockCodeResolver,
    download_icici_nse_scrip_master_text,
)
from nse_algo_trader.universe_registry import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

# A trimmed NSEScripMaster.txt: quoted, EQ + a non-EQ warrant row to filter out.
_FAKE_MASTER = (
    '"Token","ShortName","Series","ExchangeCode"\n'
    '"2885","RELIND","EQ","RELIANCE"\n'
    '"1660","ITC","EQ","ITC"\n'
    '"1594","INFTEC","EQ","INFY"\n'
    '"9999","RELWAR","W3","RELIANCE"\n'  # non-EQ -> must NOT override the EQ row
)


def _cash(symbol: str) -> Instrument:
    return Instrument(
        instrument_token=1, trading_symbol=symbol,
        exchange_segment=ExchangeSegment.NSE_CASH, kind=InstrumentKind.CASH_EQUITY,
        lot_size=1, tick_size=0.05,
    )


def test_parses_eq_rows_and_maps_nse_symbol_to_icici_code():
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(_FAKE_MASTER)
    assert resolver.icici_code_for_symbol("RELIANCE") == "RELIND"
    assert resolver.icici_code_for_symbol("INFY") == "INFTEC"
    assert resolver.icici_code_for_symbol("ITC") == "ITC"
    assert resolver.symbol_count() == 3  # the W3 warrant row is excluded


def test_unmapped_symbol_falls_back_to_itself():
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(_FAKE_MASTER)
    assert resolver.icici_code_for_symbol("NIFTY") == "NIFTY"  # index / unmapped


def test_callable_resolves_cash_by_symbol_and_option_by_underlying():
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(_FAKE_MASTER)
    assert resolver(_cash("RELIANCE")) == "RELIND"
    option = Instrument(
        instrument_token=2, trading_symbol="RELIANCE26JUL3000CE",
        exchange_segment=ExchangeSegment.NSE_FO, kind=InstrumentKind.STOCK_OPTION,
        lot_size=250, tick_size=0.05, underlying_symbol="RELIANCE",
        strike_price=3000.0, option_right=OptionRight.CALL, expiry_date=date(2026, 7, 30),
    )
    assert resolver(option) == "RELIND"  # option addressed by underlying's ICICI code


def test_real_security_master_maps_known_names():
    """Rule F: the real ICICI SecurityMaster resolves the known divergent codes.
    Env-gated so the normal suite stays offline/fast; run with
    RUN_ICICI_NETWORK_TEST=1."""
    if not os.environ.get("RUN_ICICI_NETWORK_TEST"):
        pytest.skip("network test — set RUN_ICICI_NETWORK_TEST=1 to run")
    text = download_icici_nse_scrip_master_text()
    resolver = IciciSecurityMasterStockCodeResolver.from_nse_scrip_master_text(text)
    assert resolver.icici_code_for_symbol("RELIANCE") == "RELIND"
    assert resolver.icici_code_for_symbol("INFY") == "INFTEC"
    assert resolver.icici_code_for_symbol("HDFCBANK") == "HDFBAN"
    assert resolver.icici_code_for_symbol("ITC") == "ITC"
    assert resolver.symbol_count() > 1500  # the full EQ universe
