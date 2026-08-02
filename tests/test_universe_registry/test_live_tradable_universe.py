"""Unit tests for the tradable-universe selection logic (pure functions).

Fixtures are trimmed real-shaped Kite master rows; the live-data coverage
check (9,272 cash + 215 underlyings, 2026-07-24) is the Rule-F sign-off and
lives in the flowchart note, not here.
"""

from datetime import date

from nse_algo_trader.universe_registry import (
    InstrumentKind,
    assemble_tradable_universe,
    select_full_option_universe,
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
            chain, {"NIFTY": 23650.0}, strikes_each_side_of_atm=1,
            expiry_date_by_underlying={"NIFTY": NEAR_EXPIRY}
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
            chain, {"NIFTY": 23650.0}, strikes_each_side_of_atm=5,
            expiry_date_by_underlying={"NIFTY": NEAR_EXPIRY}
        )
        assert all(o.expiry_date == NEAR_EXPIRY for o in ladder)

    def test_underlying_without_spot_is_skipped_not_guessed(self):
        chain = self._chain("RANDOMSTK", [100, 110, 120], NEAR_EXPIRY)
        ladder = select_near_expiry_option_ladder(
            chain, {}, strikes_each_side_of_atm=2,
            expiry_date_by_underlying={"RANDOMSTK": NEAR_EXPIRY}
        )
        assert ladder == []


class TestFullOptionUniverseB34:
    """B34 — the operator directive: load EVERY strike × EVERY expiry, no ATM/near-expiry pruning."""

    def _chain(self, underlying, strikes, expiry):
        rows = []
        for n, strike in enumerate(strikes):
            rows.append(_opt_row(underlying, strike, "CE", expiry, hash((underlying, strike, expiry, "CE")) % 10**8))
            rows.append(_opt_row(underlying, strike, "PE", expiry, hash((underlying, strike, expiry, "PE")) % 10**8))
        return [
            i for i in build_phase1_instrument_universe(rows)
            if i.kind in (InstrumentKind.INDEX_OPTION, InstrumentKind.STOCK_OPTION)
        ]

    def test_keeps_every_strike_and_every_expiry(self):
        # 7 strikes on the near expiry + 7 on the far expiry, both rights = 28 contracts.
        chain = self._chain("NIFTY", [23400, 23500, 23600, 23700, 23800, 23900, 24000], NEAR_EXPIRY)
        chain += self._chain("NIFTY", [23400, 23500, 23600, 23700, 23800, 23900, 24000], FAR_EXPIRY)
        full = select_full_option_universe(chain)
        assert len(full) == 28  # nothing pruned
        assert {o.expiry_date for o in full} == {NEAR_EXPIRY, FAR_EXPIRY}
        assert len({o.strike_price for o in full}) == 7

    def test_retains_underlyings_even_without_a_known_spot(self):
        # Unlike the near-expiry ladder (spot-gated), the full universe keeps a no-spot underlying —
        # it is still VISIBLE; it is simply not looked at until a spot is available.
        chain = self._chain("RANDOMSTK", [100, 110, 120], NEAR_EXPIRY)
        assert len(select_full_option_universe(chain)) == 6

    def test_assemble_default_is_full_universe_not_pruned(self):
        nse_rows = [_eq_row("INFY", 1)]
        nfo_rows = []
        # 5 strikes across TWO expiries for NIFTY -> a pruned ATM±1 ladder would keep far fewer.
        for strike in (23400, 23500, 23600, 23700, 23800):
            for expiry in (NEAR_EXPIRY, FAR_EXPIRY):
                nfo_rows.append(_opt_row("NIFTY", strike, "CE", expiry, hash((strike, expiry, "C")) % 10**8))
                nfo_rows.append(_opt_row("NIFTY", strike, "PE", expiry, hash((strike, expiry, "P")) % 10**8))
        full = assemble_tradable_universe(nse_rows, nfo_rows, {"NIFTY": 23600.0})  # default full
        pruned = assemble_tradable_universe(
            nse_rows, nfo_rows, {"NIFTY": 23600.0},
            strikes_each_side_of_atm=1, full_option_universe=False,
        )
        assert len(full.option_ladder_instruments) == 20  # 5 strikes × 2 rights × 2 expiries
        assert len(pruned.option_ladder_instruments) < len(full.option_ladder_instruments)
        # the full universe spans BOTH expiries; the pruned ladder collapses to the nearest one
        assert {o.expiry_date for o in full.option_ladder_instruments} == {NEAR_EXPIRY, FAR_EXPIRY}
        assert {o.expiry_date for o in pruned.option_ladder_instruments} == {NEAR_EXPIRY}


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


class TestPerUnderlyingExpiryB9:
    """B9 — only NIFTY still has weekly expiries, so a single global nearest-expiry filter drops
    every other underlying in ~3 weeks out of 4. These pin the real NSE cadence shape."""

    def _option(self, underlying, strike, expiry, right="CE"):

        from nse_algo_trader.universe_registry.instrument_types import (
            ExchangeSegment,
            Instrument,
            InstrumentKind,
            OptionRight,
        )

        return Instrument(
            instrument_token=abs(hash((underlying, strike, expiry, right))) % 10**8,
            trading_symbol=f"{underlying}{strike}{right}",
            exchange_segment=ExchangeSegment.NSE_FO,
            kind=(
                InstrumentKind.INDEX_OPTION
                if underlying in ("NIFTY", "BANKNIFTY")
                else InstrumentKind.STOCK_OPTION
            ),
            lot_size=65, tick_size=0.05, underlying_symbol=underlying,
            strike_price=float(strike),
            option_right=OptionRight.CALL if right == "CE" else OptionRight.PUT,
            expiry_date=expiry,
        )

    def _mixed_cadence_chain(self):
        """NIFTY weekly (earlier) + BANKNIFTY and a stock on the later monthly — the real shape."""
        from datetime import date as _date

        weekly = _date(2026, 8, 4)
        monthly = _date(2026, 8, 25)
        chain = []
        for strike in (23600, 23650, 23700):
            chain.append(self._option("NIFTY", strike, weekly))
        for strike in (56000, 57000, 58000):
            chain.append(self._option("BANKNIFTY", strike, monthly))
        for strike in (1200, 1250, 1300):
            chain.append(self._option("RELIANCE", strike, monthly))
        return chain, weekly, monthly

    def test_nearest_expiry_is_resolved_per_underlying(self):
        from nse_algo_trader.universe_registry.live_tradable_universe import (
            nearest_expiry_date_by_underlying,
        )

        chain, weekly, monthly = self._mixed_cadence_chain()
        by_underlying = nearest_expiry_date_by_underlying(chain)
        assert by_underlying["NIFTY"] == weekly
        assert by_underlying["BANKNIFTY"] == monthly
        assert by_underlying["RELIANCE"] == monthly

    def test_the_b9_regression_a_nifty_weekly_no_longer_deletes_everything_else(self):
        """THE bug: with one global nearest expiry, only NIFTY survived."""
        from nse_algo_trader.universe_registry.live_tradable_universe import (
            nearest_expiry_date_by_underlying,
            select_near_expiry_option_ladder,
        )

        chain, _, _ = self._mixed_cadence_chain()
        ladder = select_near_expiry_option_ladder(
            chain,
            {"NIFTY": 23650.0, "BANKNIFTY": 57000.0, "RELIANCE": 1250.0},
            strikes_each_side_of_atm=1,
            expiry_date_by_underlying=nearest_expiry_date_by_underlying(chain),
        )
        laddered_underlyings = {o.underlying_symbol for o in ladder}
        assert laddered_underlyings == {"NIFTY", "BANKNIFTY", "RELIANCE"}

    def test_each_underlying_appears_on_exactly_one_expiry(self):
        """Mixing expiries within an underlying would silently compare different contracts."""
        from collections import defaultdict

        from nse_algo_trader.universe_registry.live_tradable_universe import (
            nearest_expiry_date_by_underlying,
            select_near_expiry_option_ladder,
        )

        chain, _, _ = self._mixed_cadence_chain()
        # add a FURTHER-out NIFTY expiry that must not leak in
        from datetime import date as _date

        chain += [self._option("NIFTY", s, _date(2026, 8, 11)) for s in (23600, 23650, 23700)]
        ladder = select_near_expiry_option_ladder(
            chain,
            {"NIFTY": 23650.0, "BANKNIFTY": 57000.0, "RELIANCE": 1250.0},
            strikes_each_side_of_atm=1,
            expiry_date_by_underlying=nearest_expiry_date_by_underlying(chain),
        )
        expiries_by_underlying = defaultdict(set)
        for option in ladder:
            expiries_by_underlying[option.underlying_symbol].add(option.expiry_date)
        for underlying, expiries in expiries_by_underlying.items():
            assert len(expiries) == 1, f"{underlying} laddered across {expiries}"

    def test_monthly_expiry_week_is_unchanged_from_the_old_behaviour(self):
        """Criterion 5: when all expiries coincide the fix is a no-op, never a regression."""
        from datetime import date as _date

        from nse_algo_trader.universe_registry.live_tradable_universe import (
            nearest_expiry_date_by_underlying,
            select_near_expiry_option_ladder,
        )

        monthly = _date(2026, 7, 28)
        chain = (
            [self._option("NIFTY", s, monthly) for s in (23600, 23650, 23700)]
            + [self._option("RELIANCE", s, monthly) for s in (1200, 1250, 1300)]
        )
        ladder = select_near_expiry_option_ladder(
            chain, {"NIFTY": 23650.0, "RELIANCE": 1250.0}, strikes_each_side_of_atm=1,
            expiry_date_by_underlying=nearest_expiry_date_by_underlying(chain),
        )
        assert {o.underlying_symbol for o in ladder} == {"NIFTY", "RELIANCE"}
        assert all(o.expiry_date == monthly for o in ladder)
