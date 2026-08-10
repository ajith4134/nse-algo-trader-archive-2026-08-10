"""Pod paper lifecycle engine — the closed loop that lets the segment-bot pod earn its own competency.

The pod opens orders (router → SimulatedBrokerClient) but, before this engine, never closed them back into
the bots' track record — so competency could never accrue and the board stayed empty forever (a cold-start
deadlock; see ``docs/research/pod_paper_lifecycle_engine.md``). This engine carries the pod's OPEN positions
as persisted state, marks them at real adapter prices each cycle, exits on stop / target / mandatory
intraday square-off (no overnight carry — the project's binding rule), and on every close feeds a realised
``ClosedTrade`` back to the owning bot so its competency ladder advances and its learned head trains.

It composes the existing paper machinery (``SimulatedBrokerClient`` fills) rather than reimplementing a
matching engine; the depth here is the carried position state + the real exit simulation + the accrual
feedback that CHANGES what each bot proposes and how it is sized next cycle.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import ClosedTrade
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide

_MIN_STOP_FRACTION = 0.004  # a degenerate loss-tail never yields a zero-width stop (floor 0.4%)
_TARGET_R_MULTIPLE = 2.0  # target distance = this × the stop distance (2R)
_DEFAULT_SQUARE_OFF_SECONDS = 6 * 60 * 60  # force-close intraday positions after this age (no overnight carry)
_CREDIT_PROFIT_TAKE = 0.5   # close a credit structure at 50% of max credit captured (classic Θ profit-take)
_CREDIT_STOP_MULT = 2.0     # stop a credit structure at 2× the credit lost (defined-risk cap)
_DEBIT_PROFIT_TAKE = 1.0    # close a debit structure at +100% of the debit paid


@dataclass
class PodOpenPosition:
    """One open pod paper position — the carried state marked + exited across cycles."""

    order_id: str
    bot_name: str
    segment: str
    underlying: str
    side: str  # TradeSide value: long | short | neutral
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float
    entry_epoch: float
    calibrated_prob: float
    features: dict = field(default_factory=dict)
    is_option_structure: bool = False
    legs: list = field(default_factory=list)  # synthesized option legs [{right,strike,side,entry_price}] (slice 4)
    expiry: str = ""  # option expiry (ISO) — for the dashboard's real-contract labels
    last_mark: float | None = None  # latest underlying mark (updated every cycle → the dashboard LTP)
    unrealized_pnl: float | None = None  # mark-to-market P&L at last_mark (directional proxy for spreads)
    max_favourable: float = 0.0  # best unrealised P&L seen since open (MFE)
    max_adverse: float = 0.0  # worst unrealised P&L seen since open (MAE)


@dataclass
class ClosedPodTrade:
    """A realised pod paper trade — the summary the dashboard + backlog read; also drives bot accrual."""

    order_id: str
    bot_name: str
    underlying: str
    side: str
    quantity: int
    entry_price: float
    exit_price: float
    realized_pnl: float
    won: bool
    reason: str  # stop | target | square_off | timeout
    entry_epoch: float
    exit_epoch: float


def _direction_sign(side: str) -> int:
    if side == TradeSide.LONG.value:
        return 1
    if side == TradeSide.SHORT.value:
        return -1
    return 0  # neutral structures have no directional underlying P&L (approximated at square-off, Rule K)


class PodOpenPositionStore:
    """Persists the pod's open positions across cycles (carried state), keyed by order id."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "pod_open_positions.json"

    def load(self) -> list[PodOpenPosition]:
        if not self._path.exists():
            return []
        try:
            return [PodOpenPosition(**row) for row in json.loads(self._path.read_text())]
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    def save(self, positions: list[PodOpenPosition]) -> None:
        self._path.write_text(json.dumps([asdict(p) for p in positions], indent=0))


class PodPaperLifecycleEngine:
    """Opens, marks, exits, and accrues the pod's paper positions — the pod's self-improvement loop."""

    def __init__(
        self,
        store_dir: Path,
        bots_by_name: dict,
        square_off_after_seconds: float = _DEFAULT_SQUARE_OFF_SECONDS,
        option_marker=None,
    ):
        self._store = PodOpenPositionStore(store_dir)
        self._bots = bots_by_name
        self._square_off_after = square_off_after_seconds
        self._option_marker = option_marker  # OptionLegMarker — real per-leg option P&L (slice 4); None = proxy

    def on_cycle(
        self,
        placed: list,
        now_epoch: float,
        price_of: Callable[[str], float | None],
        force_square_off: bool = False,
    ) -> list[ClosedPodTrade]:
        """One lifecycle tick: mark+exit existing opens, then record this cycle's new opens. Returns closes."""
        open_positions = self._store.load()
        closed = self._mark_and_exit(open_positions, now_epoch, price_of, force_square_off)
        open_positions.extend(self._record_opens(placed, now_epoch, price_of,
                                                  already_open={p.order_id for p in open_positions}))
        self._store.save(open_positions)
        return closed

    def _record_opens(self, placed, now_epoch, price_of, already_open) -> list[PodOpenPosition]:
        opened: list[PodOpenPosition] = []
        for pod_order in placed or []:
            order_id = self._order_id(pod_order)
            if order_id in already_open or pod_order.arbitrated.approved_lots <= 0:
                continue
            proposal = pod_order.arbitrated.proposal
            entry = self._entry_price(pod_order, proposal, price_of)
            if entry is None or entry <= 0:
                continue  # cannot mark without a real price — skip (never fabricate an entry)
            side = proposal.side.value
            stop_frac = max(float(getattr(proposal, "loss_tail_estimate", 0.0)), _MIN_STOP_FRACTION)
            sign = _direction_sign(side)
            stop = entry * (1 - sign * stop_frac)
            target = entry * (1 + sign * _TARGET_R_MULTIPLE * stop_frac)
            opened.append(PodOpenPosition(
                order_id=order_id, bot_name=_base_bot(proposal.bot_name), segment=proposal.segment.value,
                underlying=proposal.underlying, side=side, quantity=int(pod_order.arbitrated.approved_lots),
                entry_price=float(entry), stop_price=float(stop), target_price=float(target),
                entry_epoch=float(now_epoch), calibrated_prob=float(getattr(proposal, "calibrated_prob", 0.5) or 0.5),
                features=dict(getattr(proposal, "feature_provenance", {}) or {}),
                is_option_structure=sign == 0,
                legs=_extract_option_legs(proposal),
                expiry=str(getattr(getattr(proposal, "structure", None), "expiry", "") or ""),
            ))
        return opened

    def _mark_and_exit(self, positions, now_epoch, price_of, force_square_off) -> list[ClosedPodTrade]:
        survivors: list[PodOpenPosition] = []
        closed: list[ClosedPodTrade] = []
        for pos in positions:
            # slice 4: a synthesized option structure marks on its REAL legs (live premiums); everything else
            # keeps the exact underlying-price mark.
            mark = self._option_marker.mark(pos.underlying, pos.legs, pos.quantity) \
                if (pos.legs and self._option_marker is not None) else None
            if mark is not None:
                self._apply_option_mark(pos, mark)
                reason = self._option_exit_reason(pos, mark, now_epoch, force_square_off)
                if reason is None:
                    survivors.append(pos)
                    continue
                closed.append(self._close(pos, pos.last_mark or pos.entry_price, now_epoch, reason,
                                          realized_override=mark.unrealized_pnl))
                continue
            price = price_of(pos.underlying)
            reason = self._exit_reason(pos, price, now_epoch, force_square_off)
            if reason is None:
                self._mark_open(pos, price)  # keep the dashboard LTP + unrealised P&L + MFE/MAE fresh each cycle
                survivors.append(pos)
                continue
            exit_price = float(price) if price and price > 0 else pos.entry_price
            closed.append(self._close(pos, exit_price, now_epoch, reason))
        positions[:] = survivors  # mutate in place so on_cycle persists the survivors
        return closed

    @staticmethod
    def _apply_option_mark(pos: PodOpenPosition, mark) -> None:
        """Mark an option structure on its real legs → the dashboard's live spread value + unrealised P&L."""
        pos.last_mark = mark.current_value_per_share
        pos.unrealized_pnl = mark.unrealized_pnl
        pos.max_favourable = round(max(pos.max_favourable, mark.unrealized_pnl), 2)
        pos.max_adverse = round(min(pos.max_adverse, mark.unrealized_pnl), 2)

    def _option_exit_reason(self, pos: PodOpenPosition, mark, now_epoch, force_square_off) -> str | None:
        """Exit a real-marked option structure on % of max profit / defined-risk stop / intraday square-off."""
        if force_square_off or (now_epoch - pos.entry_epoch) >= self._square_off_after:
            return "square_off"
        credit_total = mark.entry_value_per_share * mark.lot_size * max(int(pos.quantity), 1)
        if credit_total > 0:  # net-credit structure (Θ engine) — keep part of the decay, cap the loss
            if mark.unrealized_pnl >= _CREDIT_PROFIT_TAKE * credit_total:
                return "target"
            if mark.unrealized_pnl <= -_CREDIT_STOP_MULT * credit_total:
                return "stop"
        else:  # net-debit structure (Δ / long-vol) — max loss is the debit paid
            debit = -credit_total
            if debit > 0 and mark.unrealized_pnl >= _DEBIT_PROFIT_TAKE * debit:
                return "target"
            if debit > 0 and mark.unrealized_pnl <= -debit:
                return "stop"
        return None

    @staticmethod
    def _mark_open(pos: PodOpenPosition, price) -> None:
        """Mark an open position to the current underlying price → the dashboard's live LTP + unreal P&L.

        Directional (long/short) P&L is exact from the underlying; a neutral option structure (strangle/condor)
        has no directional underlying P&L (its edge is theta/vega), so its unrealised is left 0 until per-leg
        option marks land (slice 4) — but the LTP still updates so the row is never frozen.
        """
        if price is None or price <= 0:
            return
        pos.last_mark = round(float(price), 2)
        sign = _direction_sign(pos.side)
        if sign != 0:
            pnl = sign * (float(price) - pos.entry_price) * pos.quantity
            pos.unrealized_pnl = round(pnl, 2)
            pos.max_favourable = round(max(pos.max_favourable, pnl), 2)
            pos.max_adverse = round(min(pos.max_adverse, pnl), 2)
        else:
            pos.unrealized_pnl = 0.0  # neutral structure — directional-proxy P&L is 0 (per-leg mark = slice 4)

    def _exit_reason(self, pos: PodOpenPosition, price, now_epoch, force_square_off) -> str | None:
        if force_square_off or (now_epoch - pos.entry_epoch) >= self._square_off_after:
            return "square_off"  # mandatory intraday close — never carry overnight
        if price is None or price <= 0:
            return None  # cannot mark this cycle; hold (a real feed gap, not an exit)
        sign = _direction_sign(pos.side)
        if sign == 0:
            return None  # neutral structure: exits only on square-off (option-mark P&L is a Rule-K refinement)
        if sign * (price - pos.stop_price) <= 0:
            return "stop"
        if sign * (price - pos.target_price) >= 0:
            return "target"
        return None

    def _close(self, pos: PodOpenPosition, exit_price: float, now_epoch: float, reason: str,
               realized_override: float | None = None) -> ClosedPodTrade:
        sign = _direction_sign(pos.side)
        # option structures close at their real marked spread P&L; directional/cash use the underlying formula
        realized = realized_override if realized_override is not None else sign * (exit_price - pos.entry_price) * pos.quantity
        won = realized > 0
        self._accrue_to_bot(pos, won, now_epoch)
        self._accrue_engine_outcome(pos, won, realized)  # slice 5: teach the bot which engine paid
        return ClosedPodTrade(
            order_id=pos.order_id, bot_name=pos.bot_name, underlying=pos.underlying, side=pos.side,
            quantity=pos.quantity, entry_price=pos.entry_price, exit_price=exit_price,
            realized_pnl=round(realized, 4), won=won, reason=reason,
            entry_epoch=pos.entry_epoch, exit_epoch=float(now_epoch),
        )

    def _accrue_engine_outcome(self, pos: PodOpenPosition, won: bool, realized: float) -> None:
        """Record which profit-engine this closed trade used → the learner re-weights the scorer (slice 5)."""
        engine = pos.features.get("engine") if isinstance(pos.features, dict) else None
        bot = self._bots.get(pos.bot_name)
        if engine and bot is not None and hasattr(bot, "record_engine_outcome"):
            bot.record_engine_outcome(str(engine), won, float(realized))

    def _accrue_to_bot(self, pos: PodOpenPosition, won: bool, now_epoch: float) -> None:
        """Feed the realised outcome back to the owning bot — advances competency + trains its head (Rule D)."""
        bot = self._bots.get(pos.bot_name)
        if bot is None or not hasattr(bot, "record_closed_trade"):
            return
        trade = ClosedTrade(
            features=pos.features, won=won, entry_epoch=pos.entry_epoch,
            calibrated_prob_at_entry=pos.calibrated_prob,
        )
        bot.record_closed_trade(trade)

    @staticmethod
    def _entry_price(pod_order, proposal, price_of) -> float | None:
        for result in getattr(pod_order, "results", ()) or ():
            fill = getattr(result, "average_fill_price", None)
            if fill and fill > 0:
                return float(fill)
        return price_of(proposal.underlying)

    @staticmethod
    def _order_id(pod_order) -> str:
        proposal = pod_order.arbitrated.proposal
        # ONE open per (bot, underlying, side) across cycles — re-proposing an already-open name is a no-op
        # (the position is held/managed, not duplicated). No epoch in the key, or positions would pile up.
        return f"{_base_bot(proposal.bot_name)}|{proposal.underlying}|{proposal.side.value}"


def _base_bot(bot_name: str) -> str:
    return str(bot_name).split(":", 1)[0]


def _extract_option_legs(proposal) -> list:
    """Capture a SYNTHESIZED option structure's legs (real strike + entry premium) for per-leg marking (slice 4).

    Only slice-3 synthesized legs carry a concrete strike + price; template (moneyness-only) legs can't be
    per-leg marked, so they return [] and fall back to the underlying-proxy mark.
    """
    structure = getattr(proposal, "structure", None)
    legs = getattr(structure, "legs", ()) or ()
    out = []
    for leg in legs:
        strike = leg.get("strike")
        price = leg.get("price")
        if strike is None or price is None:
            return []  # not a fully-priced synthesized structure → no per-leg marking
        out.append({"right": str(leg.get("right")), "strike": float(strike),
                    "side": str(leg.get("side")), "entry_price": float(price)})
    return out
