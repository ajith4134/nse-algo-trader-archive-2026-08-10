"""The pre-trade COST gate — the redesign's L1 "reality filter" as a decision engine.

The risk gate (`pre_trade_risk_gate`) decides whether a signal is *survivable* and how big it may be.
This gate decides whether it is *worth trading at all* after the market takes its cut: a signal only
enters if its expected edge clears the modelled round-trip cost — statutory charges (STT, NSE exchange
txn, SEBI, GST, stamp, brokerage — from `indian_trading_cost_model`) PLUS slippage (bid-ask half-spread +
size-dependent market impact). If it does not clear, the gate **resizes** to the largest size that does,
or **vetoes**. No signal reaches capital without beating its own cost — the crypto-bot blueprint's rule.

Why this is an engine and not a scalar (Rule P):
- it carries STATE — a `SlippageCalibrationState` that starts from a half-spread PRIOR and ARMS to the
  empirical fill-vs-reference slippage per segment as real fills accrue (Rule Q maturity ladder), plus a
  running tally of pass/resize/veto decisions surfaced to the dashboard;
- it consumes a real input pipeline (live entry/target/quote + ADV for impact);
- its output CHANGES behaviour — it vetoes or shrinks real orders in the entry path.

Cost is expressed in **basis points of the entry notional** so a per-share hurdle and a per-lot option
hurdle compare on one axis against the signal's expected-edge bps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imported lazily at call time to avoid a paper_trading <-> risk_management import cycle
    from nse_algo_trader.paper_trading.market_impact_fill_model import MarketImpactConfig

_OPTION_SEGMENTS = frozenset({"nse_index_options", "nse_stock_options"})
_BPS = 10_000.0


@dataclass(frozen=True)
class CostGateConfig:
    """Policy knobs for the gate. `edge_safety_margin_bps` is the cushion the edge must beat cost by —
    a small non-zero buffer so a trade whose modelled edge only *just* covers cost (where model error
    could flip it negative) is not taken. `resize_search_fractions` are the candidate down-sizes tried
    when the full size fails but a smaller one (less market impact) might clear."""

    edge_safety_margin_bps: float = 5.0
    resize_search_fractions: tuple[float, ...] = (1.0, 0.75, 0.5, 0.25)


@dataclass(frozen=True)
class SlippagePrior:
    """Half-spread prior per segment, in bps of price (one-way). The round trip crosses the spread twice.
    Liquid cash names quote a few bps; near-ATM options a few tens of bps. These are PRIORS — the
    calibration state replaces them with empirical slippage once enough real fills accrue."""

    cash_equity_half_spread_bps: float = 3.0
    option_half_spread_bps: float = 50.0


class SlippageCalibrationState:
    """Carried, arming estimate of one-way slippage (bps) per segment (Rule Q maturity ladder).

    `gathering` → returns the half-spread PRIOR. `earned` (>= `minimum_samples_to_arm` observed fills in
    a segment) → returns a shrinkage blend of the prior and the empirical mean realised slippage, so the
    estimate moves toward reality as evidence accrues without lurching on the first few noisy fills. In-
    memory for now (persistence is a tracked follow-on); observations are fed from real fills by the loop.
    """

    def __init__(
        self, prior: SlippagePrior = SlippagePrior(), minimum_samples_to_arm: int = 30
    ) -> None:
        self._prior = prior
        self._minimum_samples_to_arm = minimum_samples_to_arm
        self._sum_bps: dict[str, float] = {}
        self._count: dict[str, int] = {}

    def _prior_for(self, segment: str) -> float:
        if segment in _OPTION_SEGMENTS:
            return self._prior.option_half_spread_bps
        return self._prior.cash_equity_half_spread_bps

    def observe(self, segment: str, realised_one_way_slippage_bps: float) -> None:
        """Record one real fill's slippage-vs-reference (bps, always taken as a positive cost)."""
        s = abs(float(realised_one_way_slippage_bps))
        self._sum_bps[segment] = self._sum_bps.get(segment, 0.0) + s
        self._count[segment] = self._count.get(segment, 0) + 1

    def one_way_slippage_bps(self, segment: str) -> float:
        prior = self._prior_for(segment)
        n = self._count.get(segment, 0)
        if n < self._minimum_samples_to_arm:
            return prior
        empirical = self._sum_bps[segment] / n
        # Shrinkage toward the prior: weight the empirical mean by n/(n+k), k = the arming threshold.
        k = self._minimum_samples_to_arm
        weight = n / (n + k)
        return weight * empirical + (1.0 - weight) * prior

    def maturity(self, segment: str) -> tuple[str, int, int]:
        """(status, have_n, need_n) for the dashboard's `have N / need M` honesty."""
        n = self._count.get(segment, 0)
        status = "earned" if n >= self._minimum_samples_to_arm else "gathering"
        return status, n, self._minimum_samples_to_arm


class CostGateVerdict(str, Enum):
    PASS = "pass"
    RESIZE = "resize"
    VETO = "veto"


@dataclass(frozen=True)
class CostBreakdownBps:
    statutory_bps: float
    slippage_bps: float

    @property
    def round_trip_bps(self) -> float:
        return self.statutory_bps + self.slippage_bps


@dataclass(frozen=True)
class CostGateDecision:
    verdict: CostGateVerdict
    approved_quantity: int  # after any resize; 0 on veto
    expected_edge_bps: float
    cost: CostBreakdownBps
    required_edge_bps: float  # round_trip cost + safety margin
    shortfall_bps: float  # required - edge when it does not clear (0 when it passes at full size)
    segment: str

    @property
    def approved(self) -> bool:
        return self.verdict is not CostGateVerdict.PASS or self.approved_quantity > 0


@dataclass
class _SegmentTally:
    passed: int = 0
    resized: int = 0
    vetoed: int = 0
    shortfall_bps_sum: float = 0.0


class PreTradeCostGate:
    """Decides PASS / RESIZE / VETO for a sized directional signal on cost-vs-edge, carrying the slippage
    calibration state + a decision tally for the dashboard."""

    def __init__(
        self,
        config: CostGateConfig = CostGateConfig(),
        slippage_state: SlippageCalibrationState | None = None,
        impact_config: MarketImpactConfig | None = None,
    ) -> None:
        from nse_algo_trader.paper_trading.market_impact_fill_model import MarketImpactConfig

        self._config = config
        self._slippage = slippage_state if slippage_state is not None else SlippageCalibrationState()
        self._impact_config = impact_config if impact_config is not None else MarketImpactConfig()
        self._tally: dict[str, _SegmentTally] = {}

    @property
    def slippage_state(self) -> SlippageCalibrationState:
        return self._slippage

    def _cost_bps_at_quantity(
        self,
        segment: str,
        entry_price: float,
        exit_reference_price: float,
        quantity: int,
        opened_short: bool,
        average_daily_quantity: float | None,
    ) -> CostBreakdownBps:
        from nse_algo_trader.paper_trading.indian_trading_cost_model import estimate_round_trip_cost
        from nse_algo_trader.paper_trading.market_impact_fill_model import estimate_market_impact_bps

        entry_notional = abs(entry_price) * abs(quantity)
        if entry_notional <= 0.0 or quantity <= 0:
            return CostBreakdownBps(0.0, 0.0)
        statutory = estimate_round_trip_cost(
            entry_price=entry_price, exit_price=exit_reference_price,
            quantity=quantity, segment=segment, opened_short=opened_short,
        ).total_cost
        statutory_bps = statutory / entry_notional * _BPS
        half_spread_bps = self._slippage.one_way_slippage_bps(segment)
        # Impact is size-dependent (sqrt participation). Unknown ADV -> the impact model returns 0, so
        # the gate charges spread + statutory only (it never invents impact from unknown liquidity).
        impact_bps = (
            estimate_market_impact_bps(quantity, average_daily_quantity, self._impact_config)
            if average_daily_quantity and average_daily_quantity > 0
            else 0.0
        )
        # Round trip crosses the spread + pays impact on BOTH the entry and the exit leg.
        slippage_bps = 2.0 * (half_spread_bps + impact_bps)
        return CostBreakdownBps(statutory_bps=statutory_bps, slippage_bps=slippage_bps)

    def evaluate_directional(
        self,
        segment: str,
        entry_price: float,
        target_price: float,
        opened_short: bool,
        risk_approved_quantity: int,
        average_daily_quantity: float | None = None,
    ) -> CostGateDecision:
        """Gate a sized directional signal (ORB / any long-or-short single instrument).

        Expected edge = the move from entry to the signal's own target, in bps. Round-trip cost is
        recomputed at each candidate size (impact shrinks with size), and the LARGEST size whose edge
        clears cost + margin is taken; if none clears, the signal is vetoed.
        """
        entry_price = abs(float(entry_price))
        expected_edge_bps = (
            abs(float(target_price) - entry_price) / entry_price * _BPS if entry_price > 0 else 0.0
        )
        margin = self._config.edge_safety_margin_bps

        best: CostGateDecision | None = None
        full_size_cost: CostBreakdownBps | None = None
        for fraction in self._config.resize_search_fractions:
            qty = int(risk_approved_quantity * fraction)
            if qty < 1:
                continue
            cost = self._cost_bps_at_quantity(
                segment, entry_price, target_price, qty, opened_short, average_daily_quantity
            )
            if fraction == 1.0:
                full_size_cost = cost
            required = cost.round_trip_bps + margin
            if expected_edge_bps >= required:
                verdict = CostGateVerdict.PASS if qty == risk_approved_quantity else CostGateVerdict.RESIZE
                best = CostGateDecision(
                    verdict=verdict, approved_quantity=qty, expected_edge_bps=expected_edge_bps,
                    cost=cost, required_edge_bps=required, shortfall_bps=0.0, segment=segment,
                )
                break  # fractions descend from 1.0, so the first pass is the largest viable size

        if best is None:
            cost = full_size_cost if full_size_cost is not None else self._cost_bps_at_quantity(
                segment, entry_price, target_price, max(1, risk_approved_quantity),
                opened_short, average_daily_quantity,
            )
            required = cost.round_trip_bps + margin
            best = CostGateDecision(
                verdict=CostGateVerdict.VETO, approved_quantity=0,
                expected_edge_bps=expected_edge_bps, cost=cost, required_edge_bps=required,
                shortfall_bps=max(0.0, required - expected_edge_bps), segment=segment,
            )

        self._record(best)
        return best

    def evaluate_credit_spread(
        self,
        segment: str,
        short_leg_premium: float,
        hedge_leg_premium: float,
        lot_size: int,
        lots: int,
    ) -> CostGateDecision:
        """Gate a defined-risk credit spread. The edge is the net premium collected
        (`short_premium - hedge_premium`); the cost is the round trip on BOTH legs at their OWN full
        premium — a spread sells the short leg AND buys the hedge, and STT/exchange charge each leg's whole
        premium, not the thin net credit. Charging cost on the net credit alone (the old bug) understated
        it several-fold. Compared in rupees: net credit vs both-leg round-trip cost + a margin, then
        re-expressed as bps of the net credit so the tally/threshold stay on one scale."""
        from nse_algo_trader.paper_trading.indian_trading_cost_model import estimate_round_trip_cost

        quantity = max(1, lot_size * lots)
        short_p = abs(float(short_leg_premium))
        hedge_p = abs(float(hedge_leg_premium))
        net_credit_rupees = (short_p - hedge_p) * quantity
        # Exit premium is unknown pre-trade; approximate exit = entry premium (a fair round-trip estimate:
        # STT sell-leg + exchange both-legs + stamp buy-leg all land regardless of the exit level).
        short_leg_cost = estimate_round_trip_cost(
            entry_price=short_p, exit_price=short_p, quantity=quantity,
            segment=segment, opened_short=True,  # sold to open
        ).total_cost
        hedge_leg_cost = estimate_round_trip_cost(
            entry_price=hedge_p, exit_price=hedge_p, quantity=quantity,
            segment=segment, opened_short=False,  # bought to open
        ).total_cost
        total_cost_rupees = short_leg_cost + hedge_leg_cost
        # Slippage: each leg crosses the option half-spread on entry AND exit.
        half_spread_bps = self._slippage.one_way_slippage_bps(segment)
        slippage_rupees = (
            2.0 * half_spread_bps / _BPS * (short_p + hedge_p) * quantity
        )
        total_cost_rupees += slippage_rupees

        base = net_credit_rupees if net_credit_rupees > 0 else 0.0
        cost_bps = (total_cost_rupees / base * _BPS) if base > 0 else _BPS
        expected_edge_bps = _BPS if base > 0 else 0.0  # the whole net credit is the gross edge
        required = cost_bps + self._config.edge_safety_margin_bps
        verdict = CostGateVerdict.PASS if expected_edge_bps >= required else CostGateVerdict.VETO
        decision = CostGateDecision(
            verdict=verdict, approved_quantity=quantity if verdict is CostGateVerdict.PASS else 0,
            expected_edge_bps=expected_edge_bps,
            cost=CostBreakdownBps(
                statutory_bps=(short_leg_cost + hedge_leg_cost) / base * _BPS if base > 0 else _BPS,
                slippage_bps=slippage_rupees / base * _BPS if base > 0 else 0.0,
            ),
            required_edge_bps=required,
            shortfall_bps=max(0.0, required - expected_edge_bps) if verdict is CostGateVerdict.VETO else 0.0,
            segment=segment,
        )
        self._record(decision)
        return decision

    def _record(self, decision: CostGateDecision) -> None:
        tally = self._tally.setdefault(decision.segment, _SegmentTally())
        if decision.verdict is CostGateVerdict.PASS:
            tally.passed += 1
        elif decision.verdict is CostGateVerdict.RESIZE:
            tally.resized += 1
        else:
            tally.vetoed += 1
            tally.shortfall_bps_sum += decision.shortfall_bps

    def snapshot(self) -> dict:
        """Decision tally + slippage maturity per segment, for the dashboard cost-gate surface (Rule N)."""
        out: dict[str, dict] = {}
        agg = {"passed": 0, "resized": 0, "vetoed": 0}
        for segment, t in self._tally.items():
            decided = t.passed + t.resized + t.vetoed
            status, have, need = self._slippage.maturity(segment)
            out[segment] = {
                "passed": t.passed, "resized": t.resized, "vetoed": t.vetoed,
                "decided": decided,
                "veto_rate": (t.vetoed / decided) if decided else 0.0,
                "avg_veto_shortfall_bps": (t.shortfall_bps_sum / t.vetoed) if t.vetoed else 0.0,
                "slippage_status": status, "slippage_have": have, "slippage_need": need,
            }
            agg["passed"] += t.passed
            agg["resized"] += t.resized
            agg["vetoed"] += t.vetoed
        out["_all"] = agg
        return out
