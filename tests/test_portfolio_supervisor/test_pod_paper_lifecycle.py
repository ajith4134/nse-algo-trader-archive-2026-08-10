"""Hermetic tests for the pod paper lifecycle engine — open → mark → exit → competency accrual (Rule J)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nse_algo_trader.portfolio_supervisor.pod_paper_lifecycle import (
    PodPaperLifecycleEngine,
    _direction_sign,
)
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    TradeSide,
)


# ---- minimal fakes behind the same shapes the pod passes (DI seam, never leaks to prod) ----
@dataclass
class _Proposal:
    underlying: str
    side: TradeSide
    bot_name: str
    segment: MarketSegment = MarketSegment.CASH_INTRADAY
    loss_tail_estimate: float = 0.02
    calibrated_prob: float = 0.6
    feature_provenance: dict = None
    structure: OptionStructurePlan = None


@dataclass
class _Arb:
    proposal: _Proposal
    approved_lots: int


@dataclass
class _Placed:
    arbitrated: _Arb
    results: tuple = ()


class _RecordingBot:
    def __init__(self, name):
        self.name = name
        self.recorded = []

    def record_closed_trade(self, trade):
        self.recorded.append(trade)


def _placed(underlying, side, lots, bot="cash_intraday_bot"):
    plan = OptionStructurePlan(OptionStructureKind.NONE, underlying, "")
    prop = _Proposal(underlying, side, bot, feature_provenance={"f": 1.0}, structure=plan)
    return _Placed(_Arb(prop, lots))


def test_open_then_target_exit_long_is_a_win(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    price = {"SBIN": 100.0}
    eng.on_cycle([_placed("SBIN", TradeSide.LONG, 10)], now_epoch=0.0, price_of=lambda u: price[u])
    assert len(eng._store.load()) == 1  # opened, carried state persisted
    price["SBIN"] = 103.0  # long target = 100*(1+2*0.02)=104 → not yet; push past it
    price["SBIN"] = 105.0
    closed = eng.on_cycle([], now_epoch=60.0, price_of=lambda u: price[u])
    assert len(closed) == 1 and closed[0].reason == "target" and closed[0].won
    assert closed[0].realized_pnl == pytest.approx((105.0 - 100.0) * 10)
    assert len(bot.recorded) == 1 and bot.recorded[0].won  # accrued to the bot


def test_stop_exit_short_is_a_loss(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    price = {"KROSS": 200.0}
    eng.on_cycle([_placed("KROSS", TradeSide.SHORT, 5)], now_epoch=0.0, price_of=lambda u: price[u])
    price["KROSS"] = 210.0  # short stop = 200*(1+0.02)=204 → breached
    closed = eng.on_cycle([], now_epoch=60.0, price_of=lambda u: price[u])
    assert len(closed) == 1 and closed[0].reason == "stop" and not closed[0].won
    assert closed[0].realized_pnl == pytest.approx((-1) * (210.0 - 200.0) * 5)  # short: price up = loss


def test_square_off_forces_close_no_overnight_carry(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    price = {"INFY": 1500.0}
    eng.on_cycle([_placed("INFY", TradeSide.LONG, 1)], now_epoch=0.0, price_of=lambda u: price[u])
    closed = eng.on_cycle([], now_epoch=60.0, price_of=lambda u: price[u], force_square_off=True)
    assert len(closed) == 1 and closed[0].reason == "square_off"
    assert eng._store.load() == []  # nothing carried


def test_missing_price_holds_then_no_fabricated_entry(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    # no price for the underlying → no open recorded (never fabricate an entry)
    eng.on_cycle([_placed("XYZ", TradeSide.LONG, 1)], now_epoch=0.0, price_of=lambda u: None)
    assert eng._store.load() == []


def test_accrual_is_monotonic_across_cycles(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    price = {"SBIN": 100.0}
    for i in range(3):
        eng.on_cycle([_placed("SBIN", TradeSide.LONG, 1)], now_epoch=float(i * 1000),
                     price_of=lambda u: price[u])
        eng.on_cycle([], now_epoch=float(i * 1000 + 10), price_of=lambda u: price[u], force_square_off=True)
    assert len(bot.recorded) == 3  # one accrual per closed cycle


def test_neutral_structure_exits_only_on_square_off(tmp_path):
    bot = _RecordingBot("index_option_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"index_option_bot": bot})
    price = {"NIFTY": 20000.0}
    eng.on_cycle([_placed("NIFTY", TradeSide.NEUTRAL, 1, bot="index_option_bot")],
                 now_epoch=0.0, price_of=lambda u: price[u])
    price["NIFTY"] = 25000.0  # a big move must NOT stop/target a neutral structure (no directional exit)
    closed = eng.on_cycle([], now_epoch=60.0, price_of=lambda u: price[u])
    assert closed == []  # still open
    closed = eng.on_cycle([], now_epoch=120.0, price_of=lambda u: price[u], force_square_off=True)
    assert len(closed) == 1 and closed[0].reason == "square_off"


def test_direction_sign():
    assert _direction_sign("long") == 1 and _direction_sign("short") == -1 and _direction_sign("neutral") == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_reproposing_open_name_does_not_duplicate(tmp_path):
    bot = _RecordingBot("cash_intraday_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"cash_intraday_bot": bot})
    price = {"SBIN": 100.0}
    eng.on_cycle([_placed("SBIN", TradeSide.LONG, 5)], now_epoch=0.0, price_of=lambda u: price[u])
    # a later cycle re-proposes the SAME name/side → must NOT open a second position (held, not duplicated)
    eng.on_cycle([_placed("SBIN", TradeSide.LONG, 5)], now_epoch=99999.0, price_of=lambda u: price[u])
    opens = eng._store.load()
    assert len(opens) == 1  # one open per (bot, underlying, side) across cycles


def test_open_position_is_marked_each_cycle(tmp_path):
    bot = _RecordingBot("index_option_bot")
    eng = PodPaperLifecycleEngine(tmp_path, {"index_option_bot": bot})
    price = {"SBIN": 100.0}
    eng.on_cycle([_placed("SBIN", TradeSide.LONG, 10)], now_epoch=0.0, price_of=lambda u: price[u])
    price["SBIN"] = 103.0  # inside stop/target → held + marked
    eng.on_cycle([], now_epoch=60.0, price_of=lambda u: price[u])
    pos = eng._store.load()[0]
    assert pos.last_mark == 103.0  # LTP refreshed → the dashboard row moves
    assert pos.unrealized_pnl == pytest.approx((103.0 - 100.0) * 10)  # directional mark
    assert pos.max_favourable >= pos.unrealized_pnl
