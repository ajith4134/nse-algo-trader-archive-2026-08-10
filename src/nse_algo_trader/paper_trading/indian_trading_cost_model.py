"""What an NSE trade ACTUALLY costs, round trip, in rupees.

Every rate below carries its source and effective date, because the failure mode for this module is
not a wrong formula — it is a **silently stale rate**. Indian charges move by Finance Act and by
exchange circular, and a cost model quietly using last year's numbers makes every expectancy figure
downstream a fiction. That is also why no third-party cost package is used: pinning a dependency
here would pin the staleness (see
`docs/research/b28_indian_trading_cost_model_design_2026-07-27.md`).

Three traps this module deliberately gets right, because getting them wrong is common:

1. **STT on an exercised/ITM option is charged on INTRINSIC VALUE, not full notional.** SEBI/CBDT
   changed this in September 2019. The old full-notional rule was ~121x more expensive, and encoding
   it would make an engine irrationally terrified of ever holding to expiry.
2. **GST applies ONLY to (brokerage + SEBI fee + exchange charge)** — never to STT or stamp duty.
   Taxing the whole stack at 18% materially overstates cost.
3. **STT is charged on the SELL leg only; stamp duty on the BUY leg only.** Charging either on both
   roughly doubles that line.

Slippage is deliberately NOT modelled here. No official NSE spread dataset exists, so any slippage
number is an assumption, not a rate — mixing an assumption into a table of statutory rates would
disguise which numbers are facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Flat brokerage per executed order (Zerodha). Source: zerodha.com/charges, read 2026-07-27.
ZERODHA_FLAT_BROKERAGE_PER_ORDER_INR = 20.0

#: GST applies to this subset ONLY — brokerage + SEBI turnover fee + exchange transaction charge.
GOODS_AND_SERVICES_TAX_RATE = 0.18

#: SEBI turnover fee, both legs, on premium turnover (Rs 10 per crore).
SEBI_TURNOVER_FEE_RATE = 0.000001


@dataclass(frozen=True)
class SegmentCostRates:
    """The statutory + broker rate table for one tradable segment.

    `source_note` is not decoration: it is how a future reader tells a verified rate from a guess,
    and how a stale rate gets caught before it corrupts an expectancy number.
    """

    securities_transaction_tax_rate_on_sell: float
    exchange_transaction_charge_rate: float
    stamp_duty_rate_on_buy: float
    source_note: str
    #: Percentage brokerage of a single order's turnover, capped at the flat per-order fee. `None` means
    #: this segment is billed the flat fee only. Zerodha equity intraday = min(0.03%, Rs 20)/order — for a
    #: small intraday order 0.03% is BELOW Rs 20, so charging a flat Rs 20 overstates its cost. Options are
    #: flat Rs 20/order (percentage brokerage does not apply). Source: zerodha.com/charges 2026-08-03.
    brokerage_percent_of_order_turnover: float | None = None


#: NSE OPTIONS (index + stock). STT raised to 0.15% on sold options effective 1 Apr 2026
#: (Finance Act 2026). Exchange transaction charge 0.03553% of premium turnover — VERIFIED against the
#: PRIMARY source NSE circular NSE/FA/73061 (Rs 3,553/crore premium, each side, eff 2026-03-01), closing
#: the b28 design doc's open circular blocker. Options bill the flat Rs 20/order (no percentage brokerage).
NSE_OPTION_COST_RATES = SegmentCostRates(
    securities_transaction_tax_rate_on_sell=0.0015,
    exchange_transaction_charge_rate=0.0003553,
    stamp_duty_rate_on_buy=0.00003,
    brokerage_percent_of_order_turnover=None,
    source_note="NSE/FA/73061 eff 2026-03-01 (exch 0.03553% premium); zerodha.com/charges 2026-08-03 "
    "(STT 0.15% sell eff 2026-04-01 Finance Act 2026; brokerage flat Rs 20/order)",
)

#: NSE CASH EQUITY, INTRADAY (no delivery). STT 0.025% on the sell side only.
#: Deliberately a SEPARATE table — reusing the option rates here would overstate cash costs ~6x.
NSE_CASH_INTRADAY_COST_RATES = SegmentCostRates(
    securities_transaction_tax_rate_on_sell=0.00025,
    # 0.00307% (Rs 307/crore), each leg. VERIFIED against the PRIMARY source: NSE circular NSE/FA/73061
    # (27-Feb-2026, eff 1-Mar-2026), transaction-charge + IPFT combined. Corrected 2026-08-03 from a stale
    # 0.0000297 that understated this line ~3.4% (closes the b28 design doc's open NSE-circular blocker).
    exchange_transaction_charge_rate=0.0000307,
    stamp_duty_rate_on_buy=0.00003,
    brokerage_percent_of_order_turnover=0.0003,
    source_note="NSE/FA/73061 eff 2026-03-01 (exch 0.00307%); zerodha.com/charges 2026-08-03 "
    "(STT 0.025% sell; brokerage min(0.03%, Rs 20)/order; stamp 0.003% buy)",
)

#: NSE OPTIONS as they stood BEFORE the Finance Act 2026 STT hike — sold-option STT was 0.10% (raised to
#: 0.15% on 1 Apr 2026). Everything else (exchange charge, stamp, brokerage) is unchanged across the
#: boundary (the NSE/FA/73061 txn+IPFT rebalance kept the total exchange outflow the same), so ONLY the STT
#: differs. Point-in-time correctness: a backtest on pre-Apr-2026 option data must use THIS table, not the
#: current one, or it overstates option cost ~1.5x on the STT line and rejects trades that were viable then.
NSE_OPTION_COST_RATES_PRE_2026_04_01 = SegmentCostRates(
    securities_transaction_tax_rate_on_sell=0.0010,
    exchange_transaction_charge_rate=0.0003553,
    stamp_duty_rate_on_buy=0.00003,
    brokerage_percent_of_order_turnover=None,
    source_note="pre-Finance-Act-2026: options STT 0.10% sell (until 2026-03-31); "
    "NSE/FA/73061 exch 0.03553% premium; zerodha.com/charges brokerage flat Rs 20/order",
)

_OPTION_SEGMENTS = frozenset({"nse_index_options", "nse_stock_options"})

#: Effective-dated statutory schedule per segment group: `(effective_from, rates)` tuples, sorted NEWEST
#: FIRST. A trade dated `d` uses the first version whose `effective_from <= d`. Statutory rates are external
#: facts with hard changeover dates (Finance Act / exchange circular), so pinning them by date — rather than
#: silently applying today's rate to old data — is the point-in-time guarantee L0 (bitemporal truth) needs.
#: Only transitions with a VERIFIED primary source + date are encoded (research/164); cash is a single
#: current version (its STT/brokerage were stable and the exchange rebalance was total-neutral).
_OPTION_RATE_SCHEDULE: tuple[tuple[date, SegmentCostRates], ...] = (
    (date(2026, 4, 1), NSE_OPTION_COST_RATES),                 # STT 0.15% (Finance Act 2026)
    (date(1, 1, 1), NSE_OPTION_COST_RATES_PRE_2026_04_01),     # STT 0.10% before the hike
)
_CASH_RATE_SCHEDULE: tuple[tuple[date, SegmentCostRates], ...] = (
    (date(1, 1, 1), NSE_CASH_INTRADAY_COST_RATES),
)


def cost_rates_for_segment(segment: str, on_date: date | None = None) -> SegmentCostRates:
    """Rate table for a segment as of `on_date` (the trade's date). `on_date=None` returns the CURRENT
    (latest) rates — correct for a live trade opened today. Pass the trade's date to price a historical
    (replayed/backtested) trade with the rates that were actually in force then."""
    schedule = _OPTION_RATE_SCHEDULE if segment in _OPTION_SEGMENTS else _CASH_RATE_SCHEDULE
    if on_date is None:
        return schedule[0][1]  # newest-first → latest
    for effective_from, rates in schedule:  # newest-first: first match is the applicable version
        if on_date >= effective_from:
            return rates
    return schedule[-1][1]  # older than every known version → the earliest we have


def _brokerage_for_one_order(rates: SegmentCostRates, order_turnover: float) -> float:
    """Brokerage on a single order. Flat fee for segments with no percentage rate (options); otherwise
    the Zerodha equity-intraday rule min(percent x turnover, flat cap) — a small order pays the percentage,
    a large one is capped at the flat fee."""
    if rates.brokerage_percent_of_order_turnover is None:
        return ZERODHA_FLAT_BROKERAGE_PER_ORDER_INR
    return min(
        rates.brokerage_percent_of_order_turnover * abs(order_turnover),
        ZERODHA_FLAT_BROKERAGE_PER_ORDER_INR,
    )


def _round_trip_brokerage(
    rates: SegmentCostRates, entry_turnover: float, exit_turnover: float, order_count: int
) -> float:
    """Round-trip brokerage: the entry leg + the exit leg, each priced per `_brokerage_for_one_order`.
    Any orders beyond the two legs (a leg split across the exchange freeze quantity) each carry the flat
    cap — a conservative upper bound, since a split order's turnover is a fraction of its leg's."""
    leg_brokerage = _brokerage_for_one_order(rates, entry_turnover) + _brokerage_for_one_order(
        rates, exit_turnover
    )
    extra_split_orders = max(0, order_count - 2)
    return leg_brokerage + ZERODHA_FLAT_BROKERAGE_PER_ORDER_INR * extra_split_orders


@dataclass(frozen=True)
class TradeCostBreakdown:
    """Every cost line separately, not just a total.

    An aggregate that cannot be decomposed cannot be audited — if the total looks wrong, the only
    way to find out WHICH rate is wrong is to see the components.
    """

    brokerage: float
    securities_transaction_tax: float
    exchange_transaction_charge: float
    sebi_turnover_fee: float
    goods_and_services_tax: float
    stamp_duty: float

    @property
    def total_cost(self) -> float:
        return (
            self.brokerage
            + self.securities_transaction_tax
            + self.exchange_transaction_charge
            + self.sebi_turnover_fee
            + self.goods_and_services_tax
            + self.stamp_duty
        )

    def as_metric_rows(self) -> tuple[tuple[str, str], ...]:
        return (
            ("brokerage", f"Rs {self.brokerage:,.2f}"),
            ("STT", f"Rs {self.securities_transaction_tax:,.2f}"),
            ("exchange txn", f"Rs {self.exchange_transaction_charge:,.2f}"),
            ("SEBI fee", f"Rs {self.sebi_turnover_fee:,.2f}"),
            ("GST", f"Rs {self.goods_and_services_tax:,.2f}"),
            ("stamp duty", f"Rs {self.stamp_duty:,.2f}"),
            ("TOTAL", f"Rs {self.total_cost:,.2f}"),
        )


def estimate_round_trip_cost(
    entry_price: float,
    exit_price: float,
    quantity: int,
    segment: str,
    order_count: int = 2,
    opened_short: bool = False,
    trade_date: date | None = None,
) -> TradeCostBreakdown:
    """Full round-trip cost of one closed trade, in rupees.

    `entry_price`/`exit_price` are per unit (premium for options, share price for cash) and
    `quantity` is the total unit count (lots x lot_size for options).

    **Direction matters, and getting it wrong is a real error.** A round trip is always one buy and
    one sell, but WHICH leg is the sell depends on how it was opened:

    * long  — buy at entry, sell at exit  -> STT on the EXIT turnover, stamp duty on the ENTRY
    * short — sell at entry, buy at exit  -> STT on the ENTRY turnover, stamp duty on the EXIT

    Charging STT on the exit unconditionally misprices every short by the ratio of the two legs.

    `order_count` defaults to 2 (one entry, one exit). Pass more when an order had to be split
    across the exchange freeze quantity — each split order carries its own flat brokerage.
    """
    rates = cost_rates_for_segment(segment, trade_date)

    entry_turnover = abs(float(entry_price)) * abs(int(quantity))
    exit_turnover = abs(float(exit_price)) * abs(int(quantity))
    if entry_turnover <= 0.0 and exit_turnover <= 0.0:
        return TradeCostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    combined_turnover = entry_turnover + exit_turnover
    sell_leg_turnover = entry_turnover if opened_short else exit_turnover
    buy_leg_turnover = exit_turnover if opened_short else entry_turnover

    brokerage = _round_trip_brokerage(
        rates, entry_turnover, exit_turnover, max(1, int(order_count))
    )
    securities_transaction_tax = (
        rates.securities_transaction_tax_rate_on_sell * sell_leg_turnover
    )
    exchange_transaction_charge = (
        rates.exchange_transaction_charge_rate * combined_turnover
    )
    sebi_turnover_fee = SEBI_TURNOVER_FEE_RATE * combined_turnover
    # GST base EXCLUDES STT and stamp duty.
    goods_and_services_tax = GOODS_AND_SERVICES_TAX_RATE * (
        brokerage + sebi_turnover_fee + exchange_transaction_charge
    )
    stamp_duty = rates.stamp_duty_rate_on_buy * buy_leg_turnover

    return TradeCostBreakdown(
        brokerage=brokerage,
        securities_transaction_tax=securities_transaction_tax,
        exchange_transaction_charge=exchange_transaction_charge,
        sebi_turnover_fee=sebi_turnover_fee,
        goods_and_services_tax=goods_and_services_tax,
        stamp_duty=stamp_duty,
    )


def estimate_exercised_option_tax(
    intrinsic_value_per_unit: float, quantity: int, trade_date: date | None = None
) -> float:
    """STT owed when an ITM option is left to AUTO-EXERCISE instead of being squared off.

    Charged on **intrinsic value**, not full notional — the September-2019 rule. The pre-2019
    full-notional charge was roughly 121x larger on a typical NIFTY contract, and encoding that
    obsolete rule would make the engine avoid holding to expiry for a cost that no longer exists.
    """
    intrinsic_turnover = max(0.0, float(intrinsic_value_per_unit)) * abs(int(quantity))
    rates = cost_rates_for_segment("nse_index_options", trade_date)
    return rates.securities_transaction_tax_rate_on_sell * intrinsic_turnover
