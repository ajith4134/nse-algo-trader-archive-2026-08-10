"""Tests for the cross-bot crowding monitor (§8b) — scoring + gross-risk recommendation."""

from __future__ import annotations

import pytest

from nse_algo_trader.portfolio_supervisor.cross_bot_crowding_monitor import CrossBotCrowdingMonitor
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    TradeProposal,
    TradeSide,
)


def _p(bot, underlying, side, conviction=0.8, lots=5) -> TradeProposal:
    return TradeProposal(MarketSegment.INDEX_OPTION, bot, underlying, side,
                         OptionStructurePlan(OptionStructureKind.NONE, underlying, ""), lots,
                         conviction, 0.6, 0.05, 0.05, 1e12, "calm")


def test_diverse_two_sided_book_is_calm():
    mon = CrossBotCrowdingMonitor()
    a = mon.assess([_p("b1", "NIFTY", TradeSide.LONG), _p("b2", "INFY", TradeSide.SHORT),
                    _p("b3", "TCS", TradeSide.LONG), _p("b1", "SBIN", TradeSide.SHORT)])
    assert a.level == "calm"
    assert a.recommended_gross_scale == 1.0
    assert abs(a.net_directional_bias) < 0.6


def test_all_same_direction_is_crowded_and_shrinks_gross():
    mon = CrossBotCrowdingMonitor()
    a = mon.assess([_p("b1", "NIFTY", TradeSide.LONG), _p("b2", "BANKNIFTY", TradeSide.LONG),
                    _p("b3", "FINNIFTY", TradeSide.LONG)])
    assert a.level == "crowded"
    assert a.net_directional_bias == pytest.approx(1.0)  # fully one-sided
    assert a.recommended_gross_scale < 1.0  # supervisor should cut gross risk


def test_same_name_pileup_is_flagged():
    mon = CrossBotCrowdingMonitor()
    a = mon.assess([_p("index_option_bot", "NIFTY", TradeSide.LONG),
                    _p("cash_intraday_bot", "NIFTY", TradeSide.LONG)])
    assert "NIFTY" in a.same_name_pileups


def test_rising_trend_detected_via_history(tmp_path):
    path = tmp_path / "crowd.json"
    mon = CrossBotCrowdingMonitor(history_path=path)
    for _ in range(5):  # seed a low-crowding baseline
        mon.assess([_p("b1", "NIFTY", TradeSide.LONG), _p("b2", "INFY", TradeSide.SHORT)])
    spike = mon.assess([_p("b1", "NIFTY", TradeSide.LONG), _p("b2", "BANKNIFTY", TradeSide.LONG),
                        _p("b3", "FINNIFTY", TradeSide.LONG)])
    assert spike.rising  # a jump above the rolling baseline


def test_empty_book_is_calm():
    assert CrossBotCrowdingMonitor().assess([]).level == "calm"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
