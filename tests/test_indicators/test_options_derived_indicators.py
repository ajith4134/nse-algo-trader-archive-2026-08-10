from dataclasses import replace
from datetime import date

import pytest

from nse_algo_trader.indicators import (
    OptionRightForPricing,
    compute_black_scholes_option_price,
    compute_end_of_day_atm_implied_volatility,
    compute_implied_volatility,
    compute_implied_volatility_rank,
    compute_put_call_open_interest_ratio,
)
from nse_algo_trader.market_data.nse_official_reports import (
    FoBhavcopyContractRow,
    FoContractType,
)


def _option_row(
    right_code: str,
    strike: float,
    open_interest: int,
    settlement: float = 100.0,
    expiry: date = date(2026, 7, 28),
    underlying: str = "NIFTY",
    contract_type: FoContractType = FoContractType.INDEX_OPTION,
) -> FoBhavcopyContractRow:
    return FoBhavcopyContractRow(
        trade_date=date(2026, 7, 22), contract_type=contract_type,
        nse_instrument_id=hash((right_code, strike, expiry)) % 10**6,
        underlying_symbol=underlying, expiry_date=expiry, strike_price=strike,
        option_right_code=right_code, open_price=0.0, high_price=0.0,
        low_price=0.0, close_price=settlement, settlement_price=settlement,
        underlying_price=25000.0, open_interest=open_interest,
        change_in_open_interest=0, total_traded_volume=0,
    )


class TestBlackScholesPricing:
    def test_hull_textbook_call_and_put_values(self):
        # Hull, "Options, Futures and Other Derivatives": S=42, K=40,
        # r=10%, sigma=20%, T=0.5y -> C=4.76, P=0.81
        call_price = compute_black_scholes_option_price(
            42.0, 40.0, 0.5, 0.20, OptionRightForPricing.CALL, risk_free_rate=0.10
        )
        put_price = compute_black_scholes_option_price(
            42.0, 40.0, 0.5, 0.20, OptionRightForPricing.PUT, risk_free_rate=0.10
        )
        assert call_price == pytest.approx(4.76, abs=0.01)
        assert put_price == pytest.approx(0.81, abs=0.01)

    def test_expired_option_prices_at_intrinsic(self):
        assert compute_black_scholes_option_price(
            25000.0, 24500.0, 0.0, 0.2, OptionRightForPricing.CALL
        ) == pytest.approx(500.0)


class TestImpliedVolatilityInversion:
    @pytest.mark.parametrize("right", list(OptionRightForPricing))
    @pytest.mark.parametrize("true_volatility", [0.12, 0.35, 0.80])
    def test_round_trip_recovers_the_volatility(self, right, true_volatility):
        fair_price = compute_black_scholes_option_price(
            25000.0, 25100.0, 6 / 365, true_volatility, right
        )
        recovered_volatility = compute_implied_volatility(
            fair_price, 25000.0, 25100.0, 6 / 365, right
        )
        assert recovered_volatility == pytest.approx(true_volatility, abs=1e-4)

    def test_price_below_intrinsic_returns_none(self):
        assert (
            compute_implied_volatility(
                1.0, 25000.0, 24000.0, 6 / 365, OptionRightForPricing.CALL
            )
            is None
        )


class TestEndOfDayAtmImpliedVolatility:
    def test_picks_nearest_future_expiry_and_nearest_strike(self):
        atm_call_price = compute_black_scholes_option_price(
            25000.0, 25000.0, 6 / 365, 0.15, OptionRightForPricing.CALL
        )
        atm_put_price = compute_black_scholes_option_price(
            25000.0, 25000.0, 6 / 365, 0.15, OptionRightForPricing.PUT
        )
        rows = [
            _option_row("CE", 25000.0, 100, settlement=atm_call_price),
            _option_row("PE", 25000.0, 100, settlement=atm_put_price),
            _option_row("CE", 26000.0, 100),  # further strike, ignored
            _option_row("CE", 25000.0, 100, expiry=date(2026, 8, 25)),  # far expiry
        ]
        snapshot = compute_end_of_day_atm_implied_volatility(rows, "NIFTY")
        assert snapshot.expiry_date == date(2026, 7, 28)
        assert snapshot.atm_strike_price == 25000.0
        assert snapshot.atm_implied_volatility == pytest.approx(0.15, abs=1e-3)

    def test_expiring_today_rows_are_excluded(self):
        expiring_today = _option_row("CE", 25000.0, 100, expiry=date(2026, 7, 22))
        assert compute_end_of_day_atm_implied_volatility([expiring_today], "NIFTY") is None

    def test_unknown_underlying_is_none(self):
        assert compute_end_of_day_atm_implied_volatility(
            [_option_row("CE", 25000.0, 100)], "BANKNIFTY"
        ) is None


class TestImpliedVolatilityRank:
    def test_hand_computed_rank(self):
        assert compute_implied_volatility_rank(
            0.20, [0.10, 0.30, 0.15]
        ) == pytest.approx(50.0)
        assert compute_implied_volatility_rank(0.30, [0.10, 0.30]) == pytest.approx(100.0)

    def test_out_of_range_current_iv_clamps(self):
        assert compute_implied_volatility_rank(0.50, [0.10, 0.30]) == 100.0

    def test_thin_or_flat_history_is_none(self):
        assert compute_implied_volatility_rank(0.2, [0.2]) is None
        assert compute_implied_volatility_rank(0.2, [0.15, 0.15, 0.15]) is None


class TestPutCallOpenInterestRatio:
    def test_sums_oi_across_expiries_per_right(self):
        rows = [
            _option_row("CE", 25000.0, 1000),
            _option_row("CE", 25100.0, 500, expiry=date(2026, 8, 25)),
            _option_row("PE", 24900.0, 1200),
            _option_row("PE", 24800.0, 600),
        ]
        pcr = compute_put_call_open_interest_ratio(rows, "NIFTY")
        assert pcr.total_call_open_interest == 1500
        assert pcr.total_put_open_interest == 1800
        assert pcr.ratio == pytest.approx(1.2)

    def test_futures_rows_never_count(self):
        future_row = replace(
            _option_row("CE", 25000.0, 99999),
            contract_type=FoContractType.INDEX_FUTURE,
            strike_price=None, option_right_code=None,
        )
        assert compute_put_call_open_interest_ratio([future_row], "NIFTY") is None

    def test_zero_call_oi_ratio_is_none_not_crash(self):
        pcr = compute_put_call_open_interest_ratio(
            [_option_row("PE", 24900.0, 1200)], "NIFTY"
        )
        assert pcr.ratio is None
