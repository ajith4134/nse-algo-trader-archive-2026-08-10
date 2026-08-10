"""Tests for the one-shot holdout custodian (L2 validation; docs/research/166).

Covers: boundary-date correctness for a known timeline + fraction; exhaustive +
disjoint research/holdout membership; the safe `partition_returns` accessor
(research only, order preserved) vs the sealed `holdout_returns` accessor;
seal-before-unseal raises; access-after-unseal succeeds; double-unseal is
recorded AND raised; the audit surface; and degenerate-input guards.

Imported by module path (not the package __init__) because wiring into the
`paper_trading` package is done separately by the main thread.
"""

from datetime import date, timedelta

import pytest

from nse_algo_trader.paper_trading.holdout_custodian import (
    HoldoutCustodian,
    HoldoutSealedError,
    HoldoutSealViolationError,
)


def _make_daily_timeline(length: int, start: date = date(2025, 1, 1)) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(length)]


def _returns_for(dates: list[date]) -> dict[date, float]:
    # Distinct, order-revealing values so we can assert ordering, not just membership.
    return {observation_date: float(index) for index, observation_date in enumerate(dates)}


class TestBoundary:
    def test_boundary_date_for_known_timeline_and_fraction(self):
        # 10 dates, fraction 0.2 -> 2 most-recent dates are the holdout.
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        assert custodian.holdout_boundary_date() == timeline[8]
        assert custodian.research_window() == (timeline[0], timeline[7])
        assert custodian.holdout_window() == (timeline[8], timeline[9])

    def test_boundary_is_a_real_timeline_date_with_gaps(self):
        # Non-contiguous real trading days: boundary must be an actual observation.
        timeline = [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 9), date(2025, 1, 13)]
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.25)
        assert custodian.holdout_boundary_date() == date(2025, 1, 13)
        assert custodian.holdout_window() == (date(2025, 1, 13), date(2025, 1, 13))
        assert custodian.research_window() == (date(2025, 1, 6), date(2025, 1, 9))

    def test_from_date_span_matches_daily_timeline(self):
        span = HoldoutCustodian.from_date_span(date(2025, 1, 1), date(2025, 1, 10), 0.2)
        explicit = HoldoutCustodian(_make_daily_timeline(10), 0.2)
        assert span.holdout_boundary_date() == explicit.holdout_boundary_date()
        assert span.holdout_window() == explicit.holdout_window()

    def test_unsorted_and_duplicate_dates_are_normalized(self):
        timeline = _make_daily_timeline(10)
        shuffled = list(reversed(timeline)) + [timeline[3], timeline[3]]
        custodian = HoldoutCustodian(shuffled, holdout_fraction=0.2)
        assert custodian.holdout_boundary_date() == timeline[8]


class TestMembership:
    def test_partition_is_exhaustive_and_disjoint_over_timeline(self):
        timeline = _make_daily_timeline(25)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        for observation_date in timeline:
            in_r = custodian.is_in_research(observation_date)
            in_h = custodian.is_in_holdout(observation_date)
            assert in_r != in_h  # exactly one is true: exhaustive + disjoint

    def test_dates_outside_timeline_belong_to_neither(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        before = timeline[0] - timedelta(days=5)
        after = timeline[-1] + timedelta(days=5)
        assert not custodian.is_in_research(before)
        assert not custodian.is_in_holdout(before)
        assert not custodian.is_in_research(after)
        assert not custodian.is_in_holdout(after)


class TestSafeAccessor:
    def test_partition_returns_only_research_while_sealed(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        returns = _returns_for(timeline)
        research, holdout = custodian.partition_returns(returns)
        assert research == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]  # research in order
        assert holdout == []  # holdout withheld while sealed

    def test_partition_returns_preserves_date_order_from_unordered_dict(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        returns = dict(reversed(list(_returns_for(timeline).items())))
        research, _ = custodian.partition_returns(returns)
        assert research == sorted(research)  # ascending == date order given our values

    def test_partition_excludes_dates_outside_timeline(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        returns = _returns_for(timeline)
        returns[timeline[-1] + timedelta(days=30)] = 999.0  # stray future date
        research, _ = custodian.partition_returns(returns)
        assert 999.0 not in research

    def test_research_returns_accessor_never_touches_holdout(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        research = custodian.research_returns(_returns_for(timeline))
        assert research == [float(i) for i in range(8)]


class TestSealEnforcement:
    def test_holdout_access_before_unseal_raises(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        with pytest.raises(HoldoutSealedError):
            custodian.holdout_returns(_returns_for(timeline))

    def test_holdout_access_after_unseal_succeeds(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        custodian.unseal_for_final_validation("final validation of ORB strategy v3")
        holdout = custodian.holdout_returns(_returns_for(timeline))
        assert holdout == [8.0, 9.0]  # the two most-recent observations, in order

    def test_partition_returns_holdout_after_unseal(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        custodian.unseal_for_final_validation("final validation")
        research, holdout = custodian.partition_returns(_returns_for(timeline))
        assert research == [float(i) for i in range(8)]
        assert holdout == [8.0, 9.0]

    def test_double_unseal_is_recorded_and_raised(self):
        timeline = _make_daily_timeline(10)
        clock_values = iter(["2026-08-03T10:00:00+00:00", "2026-08-03T11:00:00+00:00"])
        custodian = HoldoutCustodian(
            timeline, holdout_fraction=0.2, audit_clock=lambda: next(clock_values)
        )
        custodian.unseal_for_final_validation("first legitimate final pass")
        with pytest.raises(HoldoutSealViolationError):
            custodian.unseal_for_final_validation("illegitimate second peek")
        status = custodian.seal_status()
        assert status["unseal_count"] == 2
        assert len(status["violations"]) == 1
        assert "illegitimate second peek" in status["unseal_reasons"]

    def test_unseal_requires_a_reason(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        with pytest.raises(ValueError):
            custodian.unseal_for_final_validation("   ")


class TestAuditSurface:
    def test_seal_status_fields_before_and_after_unseal(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(
            timeline, holdout_fraction=0.2, audit_clock=lambda: "2026-08-03T09:00:00+00:00"
        )
        before = custodian.seal_status()
        assert before["sealed"] is True
        assert before["unseal_count"] == 0
        assert before["unseal_reasons"] == []
        assert before["violations"] == []
        assert before["holdout_boundary_date"] == timeline[8]

        custodian.unseal_for_final_validation("final validation pass")
        after = custodian.seal_status()
        assert after["sealed"] is False
        assert after["unseal_count"] == 1
        assert after["unseal_reasons"] == ["final validation pass"]
        assert after["unseal_events"] == [
            {"reason": "final validation pass", "timestamp": "2026-08-03T09:00:00+00:00"}
        ]

    def test_seal_status_is_a_defensive_copy(self):
        timeline = _make_daily_timeline(10)
        custodian = HoldoutCustodian(timeline, holdout_fraction=0.2)
        status = custodian.seal_status()
        status["unseal_reasons"].append("tampered")
        assert custodian.seal_status()["unseal_reasons"] == []


class TestDegenerateGuards:
    def test_empty_timeline_raises(self):
        with pytest.raises(ValueError):
            HoldoutCustodian([], holdout_fraction=0.2)

    def test_single_date_timeline_raises(self):
        with pytest.raises(ValueError):
            HoldoutCustodian([date(2025, 1, 1)], holdout_fraction=0.2)

    @pytest.mark.parametrize("bad_fraction", [0.0, 1.0, -0.1, 1.5])
    def test_degenerate_fraction_raises(self, bad_fraction):
        with pytest.raises(ValueError):
            HoldoutCustodian(_make_daily_timeline(10), holdout_fraction=bad_fraction)

    def test_extreme_but_valid_fraction_keeps_both_windows_nonempty(self):
        timeline = _make_daily_timeline(10)
        tiny = HoldoutCustodian(timeline, holdout_fraction=0.01)  # rounds toward 0
        assert tiny.holdout_window() == (timeline[9], timeline[9])  # forced >= 1
        assert tiny.research_window() == (timeline[0], timeline[8])

        huge = HoldoutCustodian(timeline, holdout_fraction=0.99)  # rounds toward all
        assert huge.research_window() == (timeline[0], timeline[0])  # forced >= 1
        assert huge.holdout_window() == (timeline[1], timeline[9])

    def test_from_date_span_rejects_non_positive_span(self):
        with pytest.raises(ValueError):
            HoldoutCustodian.from_date_span(date(2025, 1, 10), date(2025, 1, 10))
        with pytest.raises(ValueError):
            HoldoutCustodian.from_date_span(date(2025, 1, 10), date(2025, 1, 1))
