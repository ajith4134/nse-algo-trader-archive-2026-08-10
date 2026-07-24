"""Unit tests for the tradable-universe selection logic (pure functions).

Fixtures are trimmed real-shaped Kite master rows; the live-data coverage
check (9,272 cash + 215 underlyings, 2026-07-24) is the Rule-F sign-off and
lives in the flowchart note, not here.
"""

from datetime import date

from nse_algo_trader.universe_registry import (
    InstrumentKind,
    assemble_tradable_universe,
    select_mainboard_cash_equities,
    select_near_expiry_option_ladder,
)
from nse_algo_trader.universe_registry.kite_instrument_master_loader import (
    build_phase1_instrument_universe,
)

NEAR_EXPIRY = date(2026, 7, 28)
FAR_EXPIRY = date(2026, 8, 4)


def _eq_row(symbol, token):
    return {
        "instrument_token": token, "tradingsymbol": symbol, "name": symbol,
        "exchange": "NSE", "segment": "NSE", "instrument_type": "EQ",
        "lot_size": 1, "tick_size": 0.05, "strike": 0, "expiry": "",
    }


def _opt_row(underlying, strike, right, expiry, token):
    return {
        "instrument_token": token,
        "tradingsymbol": f"{underlying}{strike}{right}",
        "name": underlying, "exchange": "NFO", "segment": "NFO-OPT",
        "instrument_type": right, "lot_size": 75, "tick_size": 0.05,
        "strike": strike, "expiry": expiry.strftime("%Y-%m-%d"),
    }


class TestMainboardCashFilter:
    def test_sme_platform_scrips_are_dropped(self):
        rows = [_eq_row("RELIANCE", 1), _eq_row("SOMESME-SM", 2), _eq_row("TINY-ST", 3)]
        mainboard = select_mainboard_cash_equities(build_phase1_instrument_universe(rows))
        symbols = {i.trading_symbol for i in mainboard}
        assert symbols == {"RELIANCE"}

    def test_mainboard_names_are_kept(self):
        rows = [_eq_row("INFY", 1), _eq_row("TCS", 2), _eq_row("HDFCBANK", 3)]
        mainboard = select_mainboard_cash_equities(build_phase1_instrument_universe(rows))
        assert len(mainboard) == 3


class TestOptionLadderSelection:
    def _chain(self, underlying, strikes, expiry):
        rows = []
        for n, strike in enumerate(strikes):
            rows.append(_opt_row(underlying, strike, "CE", expiry, 1000 + n))
            rows.append(_opt_row(underlying, strike, "PE", expiry, 2000 + n))
        return [
            i for i in build_phase1_instrument_universe(rows)
            if i.kind in (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)
        ]

    def test_ladder_centers_on_atm_and_keeps_both_rights(self):
        strikes = [23400, 23500, 23600, 23700, 23800, 23900, 24000]
        chain = self._chain("NIFTY", strikes, NEAR_EXPIRY)
        ladder = select_near_expiry_option_ladder(
            chain, {"NIFTY": 23650.0}, strikes_each_side_of_atm=1, expiry_date=NEAR_EXPIRY
        )
        selected = sorted({o.strike_price for o in ladder})
        # spot 23650 -> ATM 23600, ±1 -> 23500/23600/23700
        assert selected == [23500.0, 23600.0, 23700.0]
        # both CE and PE for each strike
        assert len(ladder) == 6

    def test_far_expiry_is_excluded(self):
        chain = self._chain("NIFTY", [23600, 23700], NEAR_EXPIRY) + self._chain(
            "NIFTY", [23600, 23700], FAR_EXPIRY
        )
        ladder = select_near_expiry_option_ladder(
            chain, {"NIFTY": 23650.0}, strikes_each_side_of_atm=5, expiry_date=NEAR_EXPIRY
        )
        assert all(o.expiry_date == NEAR_EXPIRY for o in ladder)

    def test_underlying_without_spot_is_skipped_not_guessed(self):
        chain = self._chain("RANDOMSTK", [100, 110, 120], NEAR_EXPIRY)
        ladder = select_near_expiry_option_ladder(
            chain, {}, strikes_each_side_of_atm=2, expiry_date=NEAR_EXPIRY
        )
        assert ladder == []


class TestAssembleTradableUniverse:
    def test_assembles_cash_and_near_expiry_ladder_together(self):
        nse_rows = [_eq_row("INFY", 1), _eq_row("JUNK-SM", 2)]
        nfo_rows = []
        for n, strike in enumerate([23500, 23600, 23700]):
            nfo_rows.append(_opt_row("NIFTY", strike, "CE", NEAR_EXPIRY, 1000 + n))
            nfo_rows.append(_opt_row("NIFTY", strike, "PE", NEAR_EXPIRY, 2000 + n))
        universe = assemble_tradable_universe(
            nse_rows, nfo_rows, {"NIFTY": 23600.0}, strikes_each_side_of_atm=1
        )
        assert len(universe.cash_equity_instruments) == 1  # SME dropped
        assert universe.near_expiry_date == NEAR_EXPIRY
        assert universe.option_underlying_symbols() == ("NIFTY",)
        assert universe.total_instrument_count() == 1 + len(universe.option_ladder_instruments)
