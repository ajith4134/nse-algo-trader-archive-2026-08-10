"""B28 — the real Indian round-trip cost model.

The worked example and every rate here trace to the sourcing pass recorded in
`docs/research/b28_indian_trading_cost_model_design_2026-07-27.md`. These tests exist mainly to pin
the three traps that are commonly got wrong:

* STT on an EXERCISED option is charged on INTRINSIC VALUE, not full notional (the pre-2019 rule was
  ~121x more expensive and is six years obsolete);
* GST applies ONLY to brokerage + SEBI fee + exchange charge, never to STT or stamp duty;
* STT lands on the SELL leg, which is the ENTRY for a short — not the exit.
"""

import pytest

from nse_algo_trader.paper_trading.indian_trading_cost_model import (
    NSE_CASH_INTRADAY_COST_RATES,
    NSE_OPTION_COST_RATES,
    cost_rates_for_segment,
    estimate_exercised_option_tax,
    estimate_round_trip_cost,
)

NIFTY_LOT_SIZE = 65  # Jan-2026 series (was 75 before the SEBI-driven revision)


class TestWorkedExample:
    def test_the_sourced_nifty_example_reproduces_to_the_paisa(self):
        """NIFTY, lot 65, buy Rs150 -> sell Rs170 = Rs 72.81 round trip (design doc worked example)."""
        cost = estimate_round_trip_cost(
            entry_price=150.0, exit_price=170.0,
            quantity=NIFTY_LOT_SIZE, segment="nse_index_options",
        )
        assert cost.brokerage == pytest.approx(40.0)
        assert cost.securities_transaction_tax == pytest.approx(16.575)
        assert cost.exchange_transaction_charge == pytest.approx(7.390, abs=0.01)
        assert cost.sebi_turnover_fee == pytest.approx(0.0208, abs=0.001)
        assert cost.goods_and_services_tax == pytest.approx(8.534, abs=0.01)
        assert cost.stamp_duty == pytest.approx(0.2925, abs=0.001)
        assert cost.total_cost == pytest.approx(72.81, abs=0.05)

    def test_cost_is_a_meaningful_fraction_of_a_small_option_trade(self):
        """~0.75% of turnover round trip — the hurdle every trade must clear before it is 'profitable'."""
        cost = estimate_round_trip_cost(
            entry_price=150.0, exit_price=170.0,
            quantity=NIFTY_LOT_SIZE, segment="nse_index_options",
        )
        turnover = (150.0 + 170.0) * NIFTY_LOT_SIZE
        assert 0.003 < cost.total_cost / turnover < 0.006


class TestDirectionMatters:
    def test_stt_is_charged_on_the_entry_for_a_SHORT(self):
        """A short sells at entry, so STT lands there. Charging the exit misprices every short."""
        short_cost = estimate_round_trip_cost(
            entry_price=200.0, exit_price=100.0, quantity=NIFTY_LOT_SIZE,
            segment="nse_index_options", opened_short=True,
        )
        assert short_cost.securities_transaction_tax == pytest.approx(
            0.0015 * 200.0 * NIFTY_LOT_SIZE
        )

    def test_stt_is_charged_on_the_exit_for_a_LONG(self):
        long_cost = estimate_round_trip_cost(
            entry_price=200.0, exit_price=100.0, quantity=NIFTY_LOT_SIZE,
            segment="nse_index_options", opened_short=False,
        )
        assert long_cost.securities_transaction_tax == pytest.approx(
            0.0015 * 100.0 * NIFTY_LOT_SIZE
        )

    def test_stamp_duty_follows_the_buy_leg_which_is_the_exit_for_a_short(self):
        short_cost = estimate_round_trip_cost(
            entry_price=200.0, exit_price=100.0, quantity=NIFTY_LOT_SIZE,
            segment="nse_index_options", opened_short=True,
        )
        assert short_cost.stamp_duty == pytest.approx(0.00003 * 100.0 * NIFTY_LOT_SIZE)


class TestTaxBaseTraps:
    def test_gst_excludes_stt_and_stamp_duty(self):
        """Taxing the whole stack at 18% materially overstates cost."""
        cost = estimate_round_trip_cost(
            entry_price=150.0, exit_price=170.0,
            quantity=NIFTY_LOT_SIZE, segment="nse_index_options",
        )
        expected_gst_base = (
            cost.brokerage + cost.sebi_turnover_fee + cost.exchange_transaction_charge
        )
        assert cost.goods_and_services_tax == pytest.approx(0.18 * expected_gst_base)
        # And explicitly NOT the whole stack:
        whole_stack = expected_gst_base + cost.securities_transaction_tax + cost.stamp_duty
        assert cost.goods_and_services_tax < 0.18 * whole_stack

    def test_exercised_option_tax_uses_intrinsic_value_not_notional(self):
        """THE trap: the pre-Sept-2019 full-notional rule was ~121x larger and is obsolete."""
        intrinsic_tax = estimate_exercised_option_tax(
            intrinsic_value_per_unit=200.0, quantity=NIFTY_LOT_SIZE
        )
        assert intrinsic_tax == pytest.approx(0.0015 * 200.0 * NIFTY_LOT_SIZE)
        assert intrinsic_tax == pytest.approx(19.5, abs=0.01)
        # The obsolete rule would have charged on the ~24,200 spot instead of the 200 intrinsic:
        obsolete = 0.0015 * 24_200.0 * NIFTY_LOT_SIZE
        assert obsolete / intrinsic_tax > 100

    def test_squaring_off_near_intrinsic_costs_the_same_stt_as_exercising(self):
        """Post-2019 there is no STT penalty for letting an ITM option expire."""
        exercised = estimate_exercised_option_tax(200.0, NIFTY_LOT_SIZE)
        squared_off = estimate_round_trip_cost(
            entry_price=150.0, exit_price=200.0,
            quantity=NIFTY_LOT_SIZE, segment="nse_index_options",
        ).securities_transaction_tax
        assert exercised == pytest.approx(squared_off)

    def test_a_worthless_expiry_owes_no_exercise_tax(self):
        assert estimate_exercised_option_tax(0.0, NIFTY_LOT_SIZE) == 0.0
        assert estimate_exercised_option_tax(-5.0, NIFTY_LOT_SIZE) == 0.0


class TestSegmentSeparation:
    def test_cash_and_options_use_different_rate_tables(self):
        assert cost_rates_for_segment("nse_cash_equity") is NSE_CASH_INTRADAY_COST_RATES
        assert cost_rates_for_segment("nse_index_options") is NSE_OPTION_COST_RATES
        assert cost_rates_for_segment("nse_stock_options") is NSE_OPTION_COST_RATES

    def test_reusing_option_rates_for_cash_would_overstate_stt_sixfold(self):
        """Intraday equity STT is 0.025%; options 0.15% — a 6x difference."""
        ratio = (
            NSE_OPTION_COST_RATES.securities_transaction_tax_rate_on_sell
            / NSE_CASH_INTRADAY_COST_RATES.securities_transaction_tax_rate_on_sell
        )
        assert ratio == pytest.approx(6.0)

    def test_every_rate_table_records_its_source(self):
        """A rate with no source cannot be audited for staleness — the real failure mode here."""
        for rates in (NSE_OPTION_COST_RATES, NSE_CASH_INTRADAY_COST_RATES):
            assert "zerodha" in rates.source_note.lower()
            assert "2026" in rates.source_note


class TestRobustness:
    def test_costs_are_never_negative_and_rise_with_turnover(self):
        smaller = estimate_round_trip_cost(100.0, 110.0, 65, "nse_index_options")
        larger = estimate_round_trip_cost(1000.0, 1100.0, 65, "nse_index_options")
        assert smaller.total_cost > 0
        assert larger.total_cost > smaller.total_cost

    def test_a_zero_value_trade_costs_nothing_rather_than_raising(self):
        assert estimate_round_trip_cost(0.0, 0.0, 65, "nse_index_options").total_cost == 0.0

    def test_split_orders_across_the_freeze_quantity_each_pay_brokerage(self):
        split = estimate_round_trip_cost(
            150.0, 170.0, 65, "nse_index_options", order_count=6
        )
        assert split.brokerage == pytest.approx(120.0)

    def test_the_breakdown_sums_to_the_total(self):
        cost = estimate_round_trip_cost(150.0, 170.0, 65, "nse_index_options")
        assert cost.total_cost == pytest.approx(
            cost.brokerage + cost.securities_transaction_tax
            + cost.exchange_transaction_charge + cost.sebi_turnover_fee
            + cost.goods_and_services_tax + cost.stamp_duty
        )
