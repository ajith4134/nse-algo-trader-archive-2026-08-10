"""CausalLeakageFirewall — makes look-ahead leakage structurally impossible
(research/62 P5, research/53 §8.3).

Hermetic harness (Rule J): real-shaped PriceBars (the exact type the replay path
consumes) are streamed through the firewall behind the same interface the live
source uses. Real *intraday* archive replay stays an open blocker (needs the
Kite/Breeze backfill) — logged in BACKLOG.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.paper_trading.causal_leakage_firewall import (
    CausalLeakageFirewall,
    CausalOrderingViolation,
    FutureLeakageError,
    assert_no_future_leak,
)

IST = ZoneInfo("Asia/Kolkata")
OPEN = datetime(2020, 3, 12, 9, 15, tzinfo=IST)  # a real COVID-crash session
CLOSE = datetime(2020, 3, 12, 15, 30, tzinfo=IST)


def _bar(hour: int, minute: int, close_price: float) -> PriceBar:
    ts = datetime(2020, 3, 12, hour, minute, tzinfo=IST)
    return PriceBar(408065, ts, BarInterval.MINUTE_5, close_price, close_price,
                    close_price, close_price, 10000)


def _session_bars() -> list[PriceBar]:
    return [_bar(9, 15, 100.0), _bar(11, 0, 92.0), _bar(13, 30, 95.0),
            _bar(15, 15, 90.0)]


def test_stream_never_reveals_a_bar_before_its_timestamp():
    firewall = CausalLeakageFirewall(OPEN, CLOSE)
    revealed: list[PriceBar] = []
    for bar in firewall.stream_causally(_session_bars()):
        # At the instant each bar is revealed, virtual-now equals its timestamp
        # and NO later bar has been seen — the core no-future-leak guarantee.
        assert firewall.virtual_now == bar.timestamp
        for already_seen in revealed:
            assert already_seen.timestamp <= bar.timestamp
        revealed.append(bar)
    assert [b.timestamp for b in revealed] == [b.timestamp for b in _session_bars()]


def test_out_of_order_input_raises_causal_ordering_violation():
    firewall = CausalLeakageFirewall(OPEN, CLOSE)
    out_of_order = [_bar(11, 0, 92.0), _bar(9, 15, 100.0)]
    with pytest.raises(CausalOrderingViolation):
        list(firewall.stream_causally(out_of_order))


def test_data_outside_the_session_window_is_dropped():
    firewall = CausalLeakageFirewall(OPEN, CLOSE)
    yesterday = _bar(9, 15, 100.0).__class__(
        408065, datetime(2020, 3, 11, 15, 15, tzinfo=IST), BarInterval.MINUTE_5,
        1, 1, 1, 1, 1,
    )
    tomorrow = _bar(9, 15, 100.0).__class__(
        408065, datetime(2020, 3, 13, 9, 15, tzinfo=IST), BarInterval.MINUTE_5,
        1, 1, 1, 1, 1,
    )
    stream = [yesterday] + _session_bars() + [tomorrow]
    revealed = list(firewall.stream_causally(stream))
    assert all(OPEN <= b.timestamp <= CLOSE for b in revealed)
    assert len(revealed) == len(_session_bars())


def test_assert_observable_blocks_a_future_peek():
    firewall = CausalLeakageFirewall(OPEN, CLOSE)
    firewall.advance_to(datetime(2020, 3, 12, 11, 0, tzinfo=IST))
    firewall.assert_observable(datetime(2020, 3, 12, 10, 0, tzinfo=IST))  # past — ok
    with pytest.raises(FutureLeakageError):
        firewall.assert_observable(datetime(2020, 3, 12, 14, 0, tzinfo=IST))


def test_clock_cannot_rewind():
    firewall = CausalLeakageFirewall(OPEN, CLOSE)
    firewall.advance_to(datetime(2020, 3, 12, 13, 0, tzinfo=IST))
    with pytest.raises(CausalOrderingViolation):
        firewall.advance_to(datetime(2020, 3, 12, 12, 0, tzinfo=IST))


def test_stateless_guard_raises_on_future_timestamp():
    now = datetime(2020, 3, 12, 11, 0, tzinfo=IST)
    assert_no_future_leak(datetime(2020, 3, 12, 10, 0, tzinfo=IST), now)  # ok
    with pytest.raises(FutureLeakageError):
        assert_no_future_leak(datetime(2020, 3, 12, 12, 0, tzinfo=IST), now)
