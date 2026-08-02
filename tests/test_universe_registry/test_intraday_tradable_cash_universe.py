"""B1 — only NSE series that can actually be squared off intraday reach the scanner.

The live defect: Kite marks NSE bonds/NCDs as `instrument_type == "EQ"`, so the scanner's "cash
equity universe" was 9,292 instruments of which ~6,077 were debt paper returning no bars. Series
codes and counts below are the REAL ones from the stored 2026-07-24 bhavcopy, not invented.

See `docs/research/b1_intraday_tradable_cash_universe_design_2026-07-27.md`.
"""

from datetime import date

from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)
from nse_algo_trader.universe_registry.intraday_tradable_cash_universe import (
    UNREPORTED_SERIES_LABEL,
    select_intraday_tradable_cash_equities,
)

_TOKEN_SEQUENCE = iter(range(1_000_000, 2_000_000))


def _cash(trading_symbol: str) -> Instrument:
    return Instrument(
        instrument_token=next(_TOKEN_SEQUENCE),
        trading_symbol=trading_symbol,
        exchange_segment=ExchangeSegment.NSE_CASH,
        kind=InstrumentKind.CASH_EQUITY,
        lot_size=1,
        tick_size=0.05,
    )


class TestIntradayTradableSeriesSelection:
    def test_keeps_eq_and_drops_the_real_bond_and_t2t_series(self):
        instruments = [
            _cash("RELIANCE"),      # EQ  — tradable
            _cash("20MICRONS"),     # EQ  — tradable
            _cash("1018GS2026"),    # GS  — government security
            _cash("0ABCL31-N0"),    # N0-style NCD, reported under a debt series
            _cash("SOMET2T"),       # BE  — trade-for-trade
            _cash("SURVEILLED"),    # BZ  — surveillance
            _cash("TINYSME"),       # SM  — SME platform
        ]
        series = {
            "RELIANCE": "EQ",
            "20MICRONS": "EQ",
            "1018GS2026": "GS",
            "0ABCL31-N0": "GB",
            "SOMET2T": "BE",
            "SURVEILLED": "BZ",
            "TINYSME": "SM",
        }
        selection = select_intraday_tradable_cash_equities(instruments, series)

        assert [i.trading_symbol for i in selection.tradable_instruments] == [
            "RELIANCE",
            "20MICRONS",
        ]
        assert selection.excluded_count_by_series == {
            "GS": 1,
            "GB": 1,
            "BE": 1,
            "BZ": 1,
            "SM": 1,
        }

    def test_trade_for_trade_is_excluded_because_it_cannot_be_squared_off_intraday(self):
        """BE settles on compulsory delivery — an intraday-only bot must never open one."""
        selection = select_intraday_tradable_cash_equities(
            [_cash("T2TNAME")], {"T2TNAME": "BE"}
        )
        assert selection.tradable_instruments == ()
        assert selection.excluded_count_by_series["BE"] == 1

    def test_a_symbol_absent_from_the_bhavcopy_is_excluded_and_counted_separately(self):
        """A stale/partial report must be VISIBLE, not a silent universe shrink."""
        selection = select_intraday_tradable_cash_equities(
            [_cash("RELIANCE"), _cash("NEVERREPORTED")], {"RELIANCE": "EQ"}
        )
        assert [i.trading_symbol for i in selection.tradable_instruments] == ["RELIANCE"]
        assert selection.excluded_count_by_series[UNREPORTED_SERIES_LABEL] == 1

    def test_selection_is_narrowing_only_and_never_invents_an_instrument(self):
        instruments = [_cash("A"), _cash("B"), _cash("C")]
        selection = select_intraday_tradable_cash_equities(
            instruments, {"A": "EQ", "B": "BE", "C": "EQ"}
        )
        assert set(selection.tradable_instruments).issubset(set(instruments))
        assert selection.tradable_count + selection.excluded_count == len(instruments)

    def test_empty_series_map_excludes_everything_rather_than_passing_bonds_through(self):
        """The CALLER decides how to handle a missing bhavcopy; the pure filter must not guess."""
        selection = select_intraday_tradable_cash_equities([_cash("RELIANCE")], {})
        assert selection.tradable_instruments == ()
        assert selection.excluded_count_by_series[UNREPORTED_SERIES_LABEL] == 1

    def test_summary_line_reports_the_exclusion_breakdown(self):
        selection = select_intraday_tradable_cash_equities(
            [_cash("RELIANCE"), _cash("X"), _cash("Y")],
            {"RELIANCE": "EQ", "X": "GS", "Y": "GS"},
        )
        line = selection.summary_line()
        assert "1 intraday-tradable" in line
        assert "GS 2" in line

    def test_non_cash_instruments_are_excluded_with_their_own_bucket(self):
        option = Instrument(
            instrument_token=next(_TOKEN_SEQUENCE),
            trading_symbol="NIFTY26JUL23900CE",
            exchange_segment=ExchangeSegment.NSE_FO,
            kind=InstrumentKind.INDEX_OPTION,
            lot_size=65,
            tick_size=0.05,
            underlying_symbol="NIFTY",
            strike_price=23900.0,
            option_right=OptionRight.CALL,
            expiry_date=date(2026, 7, 28),
        )
        selection = select_intraday_tradable_cash_equities(
            [_cash("RELIANCE"), option], {"RELIANCE": "EQ"}
        )
        assert [i.trading_symbol for i in selection.tradable_instruments] == ["RELIANCE"]
        assert selection.excluded_count == 1
