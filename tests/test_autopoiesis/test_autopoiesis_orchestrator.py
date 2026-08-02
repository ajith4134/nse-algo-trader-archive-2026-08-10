"""Trunk X — the MAPE-K cycle, including the Rule-F pass against the REAL organism."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nse_algo_trader.autopoiesis.autopoiesis_orchestrator import (
    MINIMUM_OBSERVED_UPTIME_HOURS,
    AutopoiesisHomeostatOrchestrator,
    build_autopoiesis_homeostat,
)
from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore


@pytest.fixture()
def homeostat(tmp_path) -> AutopoiesisHomeostatOrchestrator:
    """A homeostat with a throwaway store — never touches `~/.nse_algo_trader/`."""
    store = AutopoiesisStateStore(tmp_path / "homeostat.sqlite3")
    built = build_autopoiesis_homeostat(state_store=store)
    yield built
    store.close()


def test_a_cycle_runs_against_the_real_organism_without_errors(homeostat) -> None:
    """Rule F: the MONITOR phase reads the REAL filesystem, process and registry — not fixtures."""
    report = homeostat.run_maintenance_cycle()
    assert report.cycle_error_count == 0, report.cycle_errors
    assert len(report.health_by_component_id) > 0
    assert report.telemetry.samples


def test_the_health_engine_is_bound_to_the_collectors_severity_specs(homeostat) -> None:
    """THE regression test for the 2026-07-27 silent failure.

    An unbound engine maps no signal to a severity, so EVERY component reads perfectly healthy however
    broken the organism is — and the cycle completes with zero errors while reporting vitality 1.000.
    The organism genuinely carries degraded components (an expired Breeze token, a structurally
    unreadable Angel One session), so a bound engine MUST see at least one.
    """
    report = homeostat.run_maintenance_cycle()
    assert report.degraded_component_ids, (
        "no component read as degraded on an organism that really is degraded — "
        "the severity specs are almost certainly unbound"
    )


def test_the_real_organism_reports_its_known_structural_blind_spot(homeostat) -> None:
    """`session.angel_one` has no validity check anywhere, so it can never read perfectly healthy."""
    report = homeostat.run_maintenance_cycle()
    angel_one = report.health_by_component_id.get("session.angel_one")
    assert angel_one is not None
    assert angel_one.health_index < 1.0


def test_the_closure_audit_finds_the_two_real_violations(homeostat) -> None:
    report = homeostat.run_maintenance_cycle()
    violated = {violation.component_id for violation in report.closure.violations}
    assert "artifact.win_probability_model" in violated
    assert "session.angel_one" in violated


def test_repair_is_advisory_until_autonomy_is_granted(homeostat) -> None:
    """The acting path still RUNS every cycle (dry-run), so refusals and budgets stay exercised."""
    assert homeostat.autonomous_repair_enabled is False
    report = homeostat.run_maintenance_cycle()
    assert all(not outcome.executed for outcome in report.executed_outcomes) or not report.executed_outcomes


def test_uptime_is_measured_from_first_observation_not_from_sample_count() -> None:
    """Regression: a survival duration of zero is invalid, and sample_count is not a duration."""
    from nse_algo_trader.autopoiesis.autopoiesis_orchestrator import _observed_uptime_hours

    moment = datetime.now(UTC)
    assert _observed_uptime_hours(None, moment) == MINIMUM_OBSERVED_UPTIME_HOURS
    assert _observed_uptime_hours(moment, moment) == MINIMUM_OBSERVED_UPTIME_HOURS
    assert _observed_uptime_hours(moment - timedelta(hours=5), moment) == pytest.approx(5.0, rel=1e-6)


def test_state_is_carried_across_cycles(homeostat) -> None:
    homeostat.run_maintenance_cycle()
    homeostat.run_maintenance_cycle()
    assert homeostat.cycle_count == 2
    assert homeostat.cumulative_error_count == 0


def test_a_monitor_failure_is_reported_not_raised(homeostat) -> None:
    """A homeostat that can crash the loop it protects is worse than no homeostat (Rule O.3)."""

    class _ExplodingCollector:
        def collect_organism_vital_signs(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201
            raise RuntimeError("probe exploded")

        @property
        def signal_severity_specs(self):  # noqa: ANN201
            return ()

    homeostat.telemetry_collector = _ExplodingCollector()  # type: ignore[assignment]
    report = homeostat.run_maintenance_cycle()
    assert report.cycle_error_count >= 1
    assert any("MONITOR failed" in error for error in report.cycle_errors)


def test_the_vitality_gate_is_published_every_cycle(homeostat) -> None:
    """Rule G: the cycle's whole purpose is to keep the entry-site lever current."""
    homeostat.run_maintenance_cycle()
    assert homeostat.vitality_gate.health_by_component_id
    assert 0.0 <= homeostat.vitality_gate.evaluate().size_multiplier <= 1.0


def test_dashboard_metrics_are_available_before_and_after_a_cycle(homeostat) -> None:
    assert dict(homeostat.dashboard_metrics())
    homeostat.run_maintenance_cycle()
    metrics = dict(homeostat.dashboard_metrics())
    assert metrics["autonomous repair"] == "advisory (dry-run)"
    assert "organism vitality" in metrics


def test_the_cycle_persists_censored_lifetime_rows(homeostat, tmp_path) -> None:
    """Censored rows carry most of the survival information in this organism's permanent regime."""
    homeostat.run_maintenance_cycle()
    events = homeostat.state_store.read_lifetime_events()
    assert events
    assert any(not event.observed_failure for event in events), "expected right-censored survivors"
    assert all(event.uptime_hours > 0.0 for event in events)
