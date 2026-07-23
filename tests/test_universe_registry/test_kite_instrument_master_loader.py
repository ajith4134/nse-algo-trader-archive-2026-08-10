from nse_algo_trader.universe_registry.instrument_types import InstrumentKind, OptionRight
from nse_algo_trader.universe_registry.kite_instrument_master_loader import (
    build_phase1_instrument_universe,
    classify_kite_instrument_row,
)
from tests.fixtures.sample_kite_instrument_rows import SAMPLE_KITE_INSTRUMENT_ROWS


def test_build_phase1_instrument_universe_keeps_only_cash_and_options():
    universe = build_phase1_instrument_universe(SAMPLE_KITE_INSTRUMENT_ROWS)

    # Fixture has 1 equity, 1 index option, 1 stock option, 1 NFO future,
    # 1 MCX future. Futures must be dropped -> 3 instruments remain.
    assert len(universe) == 3
    kinds = {instrument.kind for instrument in universe}
    assert kinds == {
        InstrumentKind.CASH_EQUITY,
        InstrumentKind.INDEX_OPTION,
        InstrumentKind.STOCK_OPTION,
    }


def test_classify_kite_instrument_row_identifies_index_option_by_underlying():
    row = SAMPLE_KITE_INSTRUMENT_ROWS[1]  # NIFTY option row
    instrument = classify_kite_instrument_row(row)
    assert instrument is not None
    assert instrument.kind == InstrumentKind.INDEX_OPTION
    assert instrument.underlying_symbol == "NIFTY"
    assert instrument.option_right == OptionRight.CALL


def test_classify_kite_instrument_row_identifies_stock_option():
    row = SAMPLE_KITE_INSTRUMENT_ROWS[2]  # RELIANCE option row
    instrument = classify_kite_instrument_row(row)
    assert instrument is not None
    assert instrument.kind == InstrumentKind.STOCK_OPTION
    assert instrument.underlying_symbol == "RELIANCE"


def test_classify_kite_instrument_row_drops_futures():
    future_row = SAMPLE_KITE_INSTRUMENT_ROWS[3]
    assert classify_kite_instrument_row(future_row) is None


def test_classify_kite_instrument_row_drops_non_nse_family_exchanges():
    mcx_row = SAMPLE_KITE_INSTRUMENT_ROWS[4]
    assert classify_kite_instrument_row(mcx_row) is None
