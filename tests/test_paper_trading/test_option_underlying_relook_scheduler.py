"""B8 — option underlyings must be re-examined through the session, fairly.

The live defect: `seeded_option_underlyings` was a permanent skip set that was never cleared, so each
of the ~215 underlyings got exactly ONE look per process lifetime — all of them spent within ~7
minutes of the open, when no opening-range breakout can exist yet. Index options sat at 0 all day
while NIFTY/NIFTYNXT50/MIDCPNIFTY showed live ORB breakouts hours later.

See `docs/research/b8_option_underlying_relook_design_2026-07-27.md`.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
    OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS,
    select_option_underlyings_due_for_look,
)

IST = ZoneInfo("Asia/Kolkata")
OPEN_MOMENT = datetime(2026, 7, 27, 9, 20, tzinfo=IST)
UNIVERSE = ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY", "NIFTYNXT50")


def _due(
    last_look_at_by_underlying=None,
    open_positions=frozenset(),
    now=OPEN_MOMENT,
    budget=25,
    universe=UNIVERSE,
):
    return select_option_underlyings_due_for_look(
        candidate_underlying_symbols=universe,
        last_look_at_by_underlying=last_look_at_by_underlying or {},
        underlyings_with_open_positions=open_positions,
        now=now,
        maximum_looks_this_pass=budget,
    )


class TestOptionUnderlyingRelookScheduler:
    def test_never_looked_underlyings_are_all_due(self):
        assert set(_due()) == set(UNIVERSE)

    def test_the_b8_regression_an_examined_underlying_becomes_due_again(self):
        """Criterion 1 — the whole point: a look is not permanent."""
        looked = {"NIFTY": OPEN_MOMENT}
        later = OPEN_MOMENT + timedelta(
            seconds=OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS + 1
        )
        assert "NIFTY" in _due(looked, now=later)

    def test_a_recently_examined_underlying_is_not_re_examined(self):
        """Criterion 2 — the fetch budget is still respected."""
        looked = {"NIFTY": OPEN_MOMENT}
        soon = OPEN_MOMENT + timedelta(
            seconds=OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS - 1
        )
        assert "NIFTY" not in _due(looked, now=soon)

    def test_ordering_is_least_recently_looked_first(self):
        """Criterion 3 — the fairness property; alphabetical ordering would starve the tail."""
        stale = OPEN_MOMENT
        recent = OPEN_MOMENT + timedelta(minutes=4)
        now = OPEN_MOMENT + timedelta(minutes=10)
        looked = {"BANKNIFTY": recent, "NIFTY": stale, "FINNIFTY": recent}
        order = _due(looked, now=now)
        # NIFTY was looked at earliest, so it must come before the two more recent ones.
        assert order.index("NIFTY") < order.index("BANKNIFTY")
        assert order.index("NIFTY") < order.index("FINNIFTY")

    def test_never_looked_outrank_even_the_stalest_looked(self):
        now = OPEN_MOMENT + timedelta(hours=3)
        looked = {name: OPEN_MOMENT for name in UNIVERSE if name != "MIDCPNIFTY"}
        assert _due(looked, now=now, budget=1) == ["MIDCPNIFTY"]

    def test_every_underlying_is_looked_once_before_any_is_looked_twice(self):
        """Criterion 3, end to end: round-robin under a budget smaller than the universe."""
        universe = tuple(f"SYM{index:03d}" for index in range(10))
        last_look: dict[str, datetime] = {}
        now = OPEN_MOMENT
        first_sweep: list[str] = []
        # Budget 3 per pass, passes spaced past the cooldown so everything stays eligible.
        for _ in range(4):
            for symbol in _due(last_look, now=now, budget=3, universe=universe):
                last_look[symbol] = now
                first_sweep.append(symbol)
            now += timedelta(seconds=OPTION_UNDERLYING_RELOOK_INTERVAL_SECONDS + 1)
        # The first 10 looks must be 10 DISTINCT symbols — nothing looked twice while one waited.
        assert len(set(first_sweep[:10])) == 10

    def test_an_underlying_with_an_open_position_is_never_re_seeded(self):
        """Criterion 4."""
        assert "NIFTY" not in _due(open_positions={"NIFTY"})

    def test_the_per_pass_budget_is_honoured(self):
        assert len(_due(budget=2)) == 2

    def test_a_zero_or_negative_budget_yields_nothing(self):
        assert _due(budget=0) == []
        assert _due(budget=-5) == []

    def test_ordering_is_deterministic_for_equal_staleness(self):
        assert _due(budget=3) == sorted(UNIVERSE)[:3]

    def test_an_empty_universe_is_handled(self):
        assert _due(universe=()) == []
