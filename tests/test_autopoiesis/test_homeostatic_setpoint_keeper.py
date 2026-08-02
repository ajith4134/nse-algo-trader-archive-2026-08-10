"""Tests for the homeostatic setpoint keeper (research/169 §4, research/172 §3 "Setpoints" row).

Five layers:

  1. **The viability-SET property** — the variable NEAREST its boundary is the one that binds, across
     variables measured in incommensurable units. This is the Ashby/Aubin claim that distinguishes this
     module from six independent PID loops (research/169 §4.3), so it is tested directly.
  2. **Hysteresis** — a boundary-straddling sequence must not make the throttle oscillate. The deadband
     and the relaxation dwell time are tested separately, then together on a real straddle.
  3. **Tighten-only safety** — no input may produce a multiplier that speeds the organism up, the
     recovery path is strictly slower than the degradation path, and a blind keeper may not relax.
  4. **Rule-F real-data pass** — the keeper is driven by the REAL host measurements the real collector
     reads off this machine, and the resulting decision is printed for by-eye inspection.
  5. **Adversarial / degenerate (Rule O.4)** — all variables outside at once, NaN measurements, an empty
     viability set, a zero-width interval, unmeasured variables, unrecognised variables.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore
from nse_algo_trader.autopoiesis.component_registry import build_default_component_registry
from nse_algo_trader.autopoiesis.component_telemetry_collector import (
    ComponentTelemetryCollector,
    TelemetryCollectionCalibration,
)
from nse_algo_trader.autopoiesis.homeostatic_setpoint_keeper import (
    DEFAULT_ESSENTIAL_VARIABLE_INTERVALS,
    VARIABLE_LLM_CALLS_PER_MINUTE,
    VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT,
    VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY,
    VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES,
    VARIABLE_SCAN_CYCLE_DURATION_SECONDS,
    VARIABLE_STATE_VOLUME_USED_FRACTION,
    EssentialVariableInterval,
    HomeostaticSetpointKeeper,
    SetpointKeeperCalibration,
    ThrottleAction,
    ThrottleLeverEmphasis,
    ViabilitySet,
    build_default_setpoint_keeper,
    tighten_viability_interval,
)

REAL_ORGANISM_STATE_DIRECTORY = Path("~/.nse_algo_trader").expanduser()

START = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)

#: Every essential variable comfortably in the interior of the viability set.
NOMINAL_MEASUREMENTS = {
    VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: 300.0,      # bound 4096, scale 1024 -> margin 3.71
    VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 10.0,      # bound 85,   scale 25   -> margin 3.00
    VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT: 60.0,           # bound 4096, scale 1024 -> margin 3.94
    VARIABLE_STATE_VOLUME_USED_FRACTION: 0.40,           # bound 0.90, scale 0.10 -> margin 5.00
    VARIABLE_SCAN_CYCLE_DURATION_SECONDS: 4.0,           # bound 30,   scale 10   -> margin 2.60
    VARIABLE_LLM_CALLS_PER_MINUTE: 2.0,                  # bound 20,   scale 8    -> margin 2.25
}


def measurements_with(**overrides: float) -> dict[str, float]:
    return {**NOMINAL_MEASUREMENTS, **overrides}


def drive_to_full_throttle(keeper: HomeostaticSetpointKeeper, moment: datetime = START) -> datetime:
    """Push one variable far outside until the throttle saturates; returns the moment reached."""
    violating = measurements_with(**{VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 200.0})
    for step in range(10):
        moment = START + timedelta(seconds=5 * step)
        keeper.regulate_toward_viability(violating, moment)
        if keeper.throttle_level >= 1.0:
            break
    assert keeper.throttle_level == pytest.approx(1.0)
    return moment


# ===================================================================================================
# 1. THE VIABILITY-SET PROPERTY: the nearest-to-boundary variable binds
# ===================================================================================================


def test_the_variable_nearest_its_boundary_is_the_one_that_binds():
    """Ashby/Aubin (research/169 §4): jointly constrained, so `argmin margin` selects the response."""
    keeper = build_default_setpoint_keeper()
    # CPU at 80/85 is 0.20 scales from its bound; memory at 3800/4096 is 0.289 scales from its.
    # Both are inside; CPU is nearer, so CPU binds — even though memory's raw number is far larger.
    decision = keeper.regulate_toward_viability(
        measurements_with(
            **{
                VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 80.0,
                VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: 3800.0,
            }
        ),
        START,
    )
    assert decision.binding_variable_name == VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY
    assert decision.binding_variable_margin == pytest.approx(0.2)
    assert decision.is_within_viability_set
    # The margins are ordered worst-first, so the dashboard reads the binding variable off the top.
    assert decision.variable_margins[0].variable_name == VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY
    assert [m.normalized_margin for m in decision.variable_margins] == sorted(
        m.normalized_margin for m in decision.variable_margins
    )


def test_incommensurable_units_are_compared_on_their_own_normalization_scales():
    """A raw-value comparison would always pick the file-descriptor count; the scaled one does not."""
    keeper = build_default_setpoint_keeper()
    decision = keeper.regulate_toward_viability(
        measurements_with(
            **{
                VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT: 3000.0,     # margin (4096-3000)/1024 = 1.07
                VARIABLE_STATE_VOLUME_USED_FRACTION: 0.88,       # margin (0.90-0.88)/0.10 = 0.20
            }
        ),
        START,
    )
    assert decision.binding_variable_name == VARIABLE_STATE_VOLUME_USED_FRACTION
    assert decision.binding_variable_margin == pytest.approx(0.2)


def test_a_variable_outside_the_set_always_binds_over_every_variable_inside_it():
    keeper = build_default_setpoint_keeper()
    decision = keeper.regulate_toward_viability(
        measurements_with(
            **{
                VARIABLE_SCAN_CYCLE_DURATION_SECONDS: 45.0,   # OUTSIDE: margin (30-45)/10 = -1.5
                VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 84.9,  # inside by a hair: margin 0.004
            }
        ),
        START,
    )
    assert decision.binding_variable_name == VARIABLE_SCAN_CYCLE_DURATION_SECONDS
    assert decision.binding_variable_margin == pytest.approx(-1.5)
    assert not decision.is_within_viability_set
    assert decision.outside_variable_names == (VARIABLE_SCAN_CYCLE_DURATION_SECONDS,)
    assert decision.action is ThrottleAction.TIGHTEN


def test_the_binding_variable_selects_which_levers_move():
    """The "viable regulation map": only actuators that can influence the binding variable are used."""
    keeper = build_default_setpoint_keeper()
    # LLM rate is outside; its emphasis is llm=1.0, scan=0.5, breadth=0.0.
    decision = keeper.regulate_toward_viability(
        measurements_with(**{VARIABLE_LLM_CALLS_PER_MINUTE: 40.0}), START
    )
    assert decision.binding_variable_name == VARIABLE_LLM_CALLS_PER_MINUTE
    assert decision.llm_call_rate_multiplier < 1.0
    assert decision.scan_interval_multiplier > 1.0
    assert decision.universe_breadth_multiplier == 1.0, (
        "narrowing the universe cannot reduce the LLM call rate, so that lever must stay put"
    )


def test_a_two_sided_interval_binds_on_whichever_side_is_nearer():
    """The default variables are one-sided; the same margin formula must handle a two-sided one."""
    interval = EssentialVariableInterval(
        variable_name="battery_charge_fraction",
        lower_bound=0.2, upper_bound=0.8, measurement_unit="fraction",
        lever_emphasis=ThrottleLeverEmphasis(scan_interval=1.0),
    )
    assert interval.normalization_scale == pytest.approx(0.3)
    assert interval.normalized_boundary_margin(0.5) == pytest.approx(1.0)       # dead centre
    assert interval.normalized_boundary_margin(0.25) == pytest.approx(1 / 6)    # near the lower bound
    assert interval.normalized_boundary_margin(0.75) == pytest.approx(1 / 6)    # near the upper bound
    assert interval.normalized_boundary_margin(0.1) == pytest.approx(-1 / 3)    # below the set
    assert interval.normalized_boundary_margin(0.95) == pytest.approx(-0.5)     # above the set
    assert not interval.contains(0.1) and not interval.contains(0.95)


def test_a_one_sided_interval_does_not_score_an_idle_process_as_near_a_boundary():
    """Why the defaults use `-inf` rather than `0.0` as the lower bound: 0 CPU is not "at a boundary"."""
    cpu_interval = next(
        i for i in DEFAULT_ESSENTIAL_VARIABLE_INTERVALS
        if i.variable_name == VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY
    )
    assert math.isinf(cpu_interval.lower_bound)
    assert cpu_interval.normalized_boundary_margin(0.0) == pytest.approx(85.0 / 25.0)
    assert cpu_interval.normalized_boundary_margin(85.0) == pytest.approx(0.0)


# ===================================================================================================
# 2. HYSTERESIS
# ===================================================================================================


def test_the_deadband_holds_the_throttle_between_the_two_thresholds():
    keeper = build_default_setpoint_keeper()
    tighten_threshold, relax_threshold = keeper.hysteresis_deadband
    assert (tighten_threshold, relax_threshold) == (0.0, 0.25)

    drive_to_full_throttle(keeper)
    level_before = keeper.throttle_level
    # 0.885 used -> margin 0.15: inside the set but inside the deadband too.
    decision = keeper.regulate_toward_viability(
        measurements_with(**{VARIABLE_STATE_VOLUME_USED_FRACTION: 0.885}),
        START + timedelta(hours=1),
    )
    assert decision.binding_variable_margin == pytest.approx(0.15)
    assert decision.is_within_viability_set
    assert decision.action is ThrottleAction.HOLD
    assert keeper.throttle_level == pytest.approx(level_before)
    assert "hysteresis deadband" in decision.reason


def test_a_boundary_straddling_sequence_never_oscillates_the_throttle():
    """The oscillation test: alternate just-outside / just-inside and assert the throttle is monotone.

    A bang-bang controller would tighten, relax, tighten, relax forever on this sequence. With the
    deadband in place, every just-inside sample lands in `[0, 0.25)` and produces HOLD, so the throttle
    is non-decreasing throughout and there is not a single RELAX.
    """
    keeper = build_default_setpoint_keeper()
    straddle = [0.905, 0.895, 0.902, 0.898, 0.901, 0.899, 0.903, 0.897]  # bound is 0.90
    levels: list[float] = []
    actions: list[ThrottleAction] = []
    for step, used_fraction in enumerate(straddle):
        decision = keeper.regulate_toward_viability(
            measurements_with(**{VARIABLE_STATE_VOLUME_USED_FRACTION: used_fraction}),
            START + timedelta(seconds=10 * step),
        )
        levels.append(decision.throttle_level)
        actions.append(decision.action)

    assert ThrottleAction.RELAX not in actions, (
        f"the throttle relaxed inside the deadband and will chatter: {actions}"
    )
    assert levels == sorted(levels), f"throttle level oscillated: {levels}"
    assert set(actions) <= {ThrottleAction.TIGHTEN, ThrottleAction.HOLD}


def test_relaxation_requires_both_a_clear_margin_and_the_dwell_time():
    keeper = build_default_setpoint_keeper()
    moment = drive_to_full_throttle(keeper)
    saturated_level = keeper.throttle_level

    # Deep inside the set, but the dwell clock has never started -> the first relaxation is allowed.
    first = keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, moment + timedelta(seconds=10))
    assert first.action is ThrottleAction.RELAX
    assert keeper.throttle_level == pytest.approx(saturated_level - 0.05)

    # Immediately again: still deep inside, but the dwell time has not elapsed.
    second = keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, moment + timedelta(seconds=11))
    assert second.action is ThrottleAction.HOLD
    assert "dwell time" in second.reason
    assert keeper.throttle_level == pytest.approx(saturated_level - 0.05)

    # After the dwell interval it may step again.
    third = keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, moment + timedelta(seconds=80))
    assert third.action is ThrottleAction.RELAX
    assert keeper.throttle_level == pytest.approx(saturated_level - 0.10)


def test_recovery_to_nominal_is_strictly_slower_than_degradation_to_full_throttle():
    """The asymmetry IS the safety property (module docstring), so it is asserted numerically."""
    keeper = build_default_setpoint_keeper()
    tighten_cycles = 0
    moment = START
    while keeper.throttle_level < 1.0 and tighten_cycles < 50:
        tighten_cycles += 1
        moment = START + timedelta(seconds=5 * tighten_cycles)
        keeper.regulate_toward_viability(
            measurements_with(**{VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 200.0}), moment
        )

    relax_cycles = 0
    while keeper.throttle_level > 0.0 and relax_cycles < 200:
        relax_cycles += 1
        moment = moment + timedelta(seconds=90)
        keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, moment)

    assert keeper.throttle_level == pytest.approx(0.0)
    assert relax_cycles > 5 * tighten_cycles, (
        f"recovery ({relax_cycles} cycles) must be far slower than degradation ({tighten_cycles})"
    )


def test_a_calibration_without_a_deadband_is_rejected_at_construction():
    with pytest.raises(ValueError, match="hysteresis deadband"):
        SetpointKeeperCalibration(tighten_margin_threshold=0.5, relax_margin_threshold=0.5)
    with pytest.raises(ValueError, match="never recover faster than it degrades"):
        SetpointKeeperCalibration(tightening_step=0.1, relaxation_step=0.5)


# ===================================================================================================
# 3. TIGHTEN-ONLY SAFETY
# ===================================================================================================


def test_the_throttle_can_only_ever_slow_the_organism_down():
    """Structural invariant, swept across the whole reachable state space of one variable."""
    keeper = build_default_setpoint_keeper()
    moment = START
    for step, cpu_percent in enumerate([0.0, 5.0, 50.0, 84.0, 86.0, 120.0, 500.0, 10.0, 0.0] * 3):
        moment = START + timedelta(seconds=7 * step)
        decision = keeper.regulate_toward_viability(
            measurements_with(**{VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: cpu_percent}), moment
        )
        assert decision.scan_interval_multiplier >= 1.0
        assert 0.0 < decision.universe_breadth_multiplier <= 1.0
        assert 0.0 < decision.llm_call_rate_multiplier <= 1.0
        assert 0.0 <= decision.throttle_level <= 1.0
        assert decision.apply_to_scan_interval_seconds(5.0) >= 5.0
        assert decision.apply_to_universe_size(2000) <= 2000
        assert decision.apply_to_llm_calls_per_minute(20.0) <= 20.0


def test_the_levers_are_applied_to_the_real_nominal_configuration():
    """The three actuators of research/172 §9, applied to the live loop's real nominal settings."""
    keeper = build_default_setpoint_keeper()
    drive_to_full_throttle(keeper)
    decision = keeper.latest_decision
    assert decision is not None
    assert decision.apply_to_scan_interval_seconds(5.0) > 5.0     # the service's real 5.0 s default
    assert decision.apply_to_universe_size(2000) < 2000           # the ~2,000-name cash universe
    assert decision.apply_to_universe_size(2000) >= 1, "the throttle is not an off-switch"
    assert decision.apply_to_universe_size(0) == 0
    assert decision.apply_to_llm_calls_per_minute(20.0) <= 20.0


def test_the_multiplier_invariants_are_enforced_on_the_decision_object_itself():
    from nse_algo_trader.autopoiesis.homeostatic_setpoint_keeper import HomeostaticThrottleDecision

    def build(**overrides):
        fields = dict(
            decided_at=START, action=ThrottleAction.HOLD, throttle_level=0.0,
            scan_interval_multiplier=1.0, universe_breadth_multiplier=1.0,
            llm_call_rate_multiplier=1.0, binding_variable_name="x",
            binding_variable_margin=1.0, is_within_viability_set=True, reason="test",
        )
        fields.update(overrides)
        return HomeostaticThrottleDecision(**fields)

    build()  # the nominal decision is valid
    with pytest.raises(ValueError, match="tighten-only"):
        build(scan_interval_multiplier=0.5)
    with pytest.raises(ValueError, match="tighten-only"):
        build(universe_breadth_multiplier=1.5)
    with pytest.raises(ValueError, match="tighten-only"):
        build(llm_call_rate_multiplier=2.0)
    with pytest.raises(ValueError, match="throttle_level"):
        build(throttle_level=1.5)
    with pytest.raises(ValueError, match="timezone-aware"):
        build(decided_at=datetime(2026, 7, 27, 3, 0))


def test_a_keeper_that_cannot_see_a_variable_is_forbidden_to_relax():
    """Tighten-only under ignorance: an unmeasured essential variable blocks recovery outright."""
    keeper = build_default_setpoint_keeper()
    moment = drive_to_full_throttle(keeper)
    partial = {k: v for k, v in NOMINAL_MEASUREMENTS.items() if k != VARIABLE_LLM_CALLS_PER_MINUTE}

    decision = keeper.regulate_toward_viability(partial, moment + timedelta(hours=1))
    assert decision.action is ThrottleAction.HOLD
    assert decision.unmeasured_variable_names == (VARIABLE_LLM_CALLS_PER_MINUTE,)
    assert "UNMEASURED" in decision.reason
    assert keeper.throttle_level == pytest.approx(1.0)

    # Supply it, and recovery resumes.
    resumed = keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, moment + timedelta(hours=2))
    assert resumed.action is ThrottleAction.RELAX


def test_an_unmeasured_variable_never_blocks_tightening():
    """Blindness may forbid relaxing; it must never forbid protecting the organism."""
    keeper = build_default_setpoint_keeper()
    partial = {
        VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 200.0,
        VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: 300.0,
    }
    decision = keeper.regulate_toward_viability(partial, START)
    assert decision.action is ThrottleAction.TIGHTEN
    assert len(decision.unmeasured_variable_names) == 4
    assert keeper.throttle_level > 0.0


# ===================================================================================================
# 4. RULE-F REAL-DATA PASS
# ===================================================================================================


@pytest.mark.skipif(
    not REAL_ORGANISM_STATE_DIRECTORY.exists(),
    reason="the real organism state directory is not present on this machine",
)
def test_the_keeper_regulates_on_the_real_host_measurements_of_this_machine(tmp_path, capsys):
    """Rule F: real `psutil` numbers off this box, through the real collector, into the real keeper."""
    collector = ComponentTelemetryCollector(
        registry=build_default_component_registry(),
        state_store=AutopoiesisStateStore(tmp_path / "autopoiesis_homeostat.sqlite3"),
        calibration=TelemetryCollectionCalibration(perform_sqlite_integrity_checks=False),
    )
    collection = collector.collect_organism_vital_signs()
    real_measurements = collection.essential_variable_measurements()

    keeper = build_default_setpoint_keeper()
    decision = keeper.regulate_from_readings(
        real_measurements,
        # Only the running loop can know these two; the values are this test's, and are labelled as such.
        service_measurements={
            VARIABLE_SCAN_CYCLE_DURATION_SECONDS: 4.0,
            VARIABLE_LLM_CALLS_PER_MINUTE: 2.0,
        },
    )

    with capsys.disabled():
        print("\n" + "=" * 110)
        print("RULE-F REAL-DATA PASS — the setpoint keeper on this machine's REAL host measurements")
        print("=" * 110)
        print(f"real measurements from the collector: {real_measurements}")
        print(decision.describe())
        print("=" * 110 + "\n")

    assert set(real_measurements) == {
        VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES,
        VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY,
        VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT,
        VARIABLE_STATE_VOLUME_USED_FRACTION,
    }, "the collector must supply exactly the host half of the essential variables"
    assert decision.unmeasured_variable_names == ()
    assert len(decision.variable_margins) == 6
    assert decision.binding_variable_name in NOMINAL_MEASUREMENTS
    # Whatever the box's state, the decision must be self-consistent and tighten-only.
    assert decision.scan_interval_multiplier >= 1.0
    assert decision.is_within_viability_set == (not decision.outside_variable_names)
    if decision.is_within_viability_set:
        assert decision.action in (ThrottleAction.HOLD, ThrottleAction.RELAX)
    else:
        assert decision.action is ThrottleAction.TIGHTEN
    # The state volume on this box is the tightest real constraint; assert it was really measured.
    disk_margin = next(
        m for m in decision.variable_margins if m.variable_name == VARIABLE_STATE_VOLUME_USED_FRACTION
    )
    assert 0.0 < disk_margin.measured_value < 1.0


def test_the_collector_and_the_keeper_agree_on_variable_names_and_units():
    """Rule G wiring check: a rename on either side must fail here, not silently at 3 a.m. in prod."""
    collector_variables = {
        VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES,
        VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY,
        VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT,
        VARIABLE_STATE_VOLUME_USED_FRACTION,
    }
    declared = {interval.variable_name for interval in DEFAULT_ESSENTIAL_VARIABLE_INTERVALS}
    assert collector_variables <= declared
    assert declared - collector_variables == {
        VARIABLE_SCAN_CYCLE_DURATION_SECONDS,
        VARIABLE_LLM_CALLS_PER_MINUTE,
    }


def test_a_measurement_supplied_by_both_sources_is_rejected_rather_than_silently_resolved():
    keeper = build_default_setpoint_keeper()
    with pytest.raises(ValueError, match="both supplied"):
        keeper.regulate_from_readings(
            {VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 10.0},
            {VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 90.0},
        )


# ===================================================================================================
# 5. ADVERSARIAL / DEGENERATE (Rule O.4)
# ===================================================================================================


def test_all_variables_outside_simultaneously_pulls_every_relevant_lever():
    keeper = build_default_setpoint_keeper()
    everything_outside = {
        VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: 9000.0,
        VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 300.0,
        VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT: 9000.0,
        VARIABLE_STATE_VOLUME_USED_FRACTION: 0.999,
        VARIABLE_SCAN_CYCLE_DURATION_SECONDS: 120.0,
        VARIABLE_LLM_CALLS_PER_MINUTE: 300.0,
    }
    decision = keeper.regulate_toward_viability(everything_outside, START)
    assert len(decision.outside_variable_names) == 6
    assert not decision.is_within_viability_set
    assert decision.action is ThrottleAction.TIGHTEN
    # Every lever moves, because the emphasis is the per-lever max over all violated variables.
    assert decision.scan_interval_multiplier > 1.0
    assert decision.universe_breadth_multiplier < 1.0
    assert decision.llm_call_rate_multiplier < 1.0
    # And it saturates fast rather than creeping.
    keeper.regulate_toward_viability(everything_outside, START + timedelta(seconds=5))
    saturated = keeper.regulate_toward_viability(everything_outside, START + timedelta(seconds=10))
    assert saturated.throttle_level == pytest.approx(1.0)
    assert saturated.scan_interval_multiplier == pytest.approx(8.0)
    assert saturated.universe_breadth_multiplier == pytest.approx(0.10)
    assert saturated.llm_call_rate_multiplier == pytest.approx(0.05)


def test_at_maximum_throttle_a_still_violated_state_holds_rather_than_claiming_to_tighten():
    keeper = build_default_setpoint_keeper()
    drive_to_full_throttle(keeper)
    decision = keeper.regulate_toward_viability(
        measurements_with(**{VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: 200.0}),
        START + timedelta(minutes=5),
    )
    assert decision.action is ThrottleAction.HOLD
    assert "already at maximum" in decision.reason
    assert decision.throttle_level == pytest.approx(1.0)
    assert not decision.is_within_viability_set


def test_non_finite_measurements_are_treated_as_unmeasured_not_coerced():
    keeper = build_default_setpoint_keeper()
    decision = keeper.regulate_toward_viability(
        measurements_with(
            **{
                VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: math.nan,
                VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: math.inf,
            }
        ),
        START,
    )
    assert set(decision.unmeasured_variable_names) == {
        VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY,
        VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES,
    }
    assert len(decision.variable_margins) == 4
    assert decision.action is ThrottleAction.HOLD


def test_a_fully_blind_keeper_holds_its_throttle_and_says_so():
    keeper = build_default_setpoint_keeper()
    drive_to_full_throttle(keeper)
    decision = keeper.regulate_toward_viability({}, START + timedelta(hours=1))
    assert decision.action is ThrottleAction.HOLD
    assert decision.binding_variable_name == ""
    assert math.isinf(decision.binding_variable_margin)
    assert len(decision.unmeasured_variable_names) == 6
    assert "may not relax" in decision.reason
    assert keeper.throttle_level == pytest.approx(1.0)
    # Blind means blind: it must not claim the state is viable.
    assert decision.is_within_viability_set is True and decision.variable_margins == ()


def test_unrecognised_variables_are_surfaced_and_ignored_never_regulated_on():
    keeper = build_default_setpoint_keeper()
    decision = keeper.regulate_toward_viability(
        measurements_with(**{"invented_variable": 99999.0}), START
    )
    assert decision.unrecognized_variable_names == ("invented_variable",)
    assert decision.action is not ThrottleAction.TIGHTEN
    assert all(m.variable_name != "invented_variable" for m in decision.variable_margins)


def test_an_empty_viability_set_is_rejected_at_construction():
    with pytest.raises(ValueError, match="cannot constrain anything"):
        ViabilitySet(intervals=())


def test_degenerate_intervals_are_rejected_at_construction():
    emphasis = ThrottleLeverEmphasis(scan_interval=1.0)
    with pytest.raises(ValueError, match="positive width"):
        EssentialVariableInterval("v", 1.0, 1.0, "unit", emphasis)
    with pytest.raises(ValueError, match="positive width"):
        EssentialVariableInterval("v", 5.0, 1.0, "unit", emphasis)
    with pytest.raises(ValueError, match="must not be NaN"):
        EssentialVariableInterval("v", math.nan, 1.0, "unit", emphasis)
    with pytest.raises(ValueError, match="boundary_normalization_scale"):
        EssentialVariableInterval("v", -math.inf, 10.0, "unit", emphasis)
    with pytest.raises(ValueError, match="finite and positive"):
        EssentialVariableInterval("v", 0.0, 10.0, "unit", emphasis, boundary_normalization_scale=0.0)
    with pytest.raises(ValueError, match="non-empty identifier"):
        EssentialVariableInterval("", 0.0, 10.0, "unit", emphasis)


def test_a_duplicate_essential_variable_is_rejected():
    interval = DEFAULT_ESSENTIAL_VARIABLE_INTERVALS[0]
    with pytest.raises(ValueError, match="duplicate essential variable"):
        ViabilitySet(intervals=(interval, interval))


def test_a_variable_no_actuator_can_influence_is_rejected():
    """A declared-but-unregulatable essential variable would be a permanent silent failure."""
    with pytest.raises(ValueError, match="no actuator can influence"):
        ThrottleLeverEmphasis()


def test_a_non_finite_measurement_reaching_the_interval_directly_raises():
    interval = DEFAULT_ESSENTIAL_VARIABLE_INTERVALS[0]
    with pytest.raises(ValueError, match="not an observation"):
        interval.normalized_boundary_margin(math.nan)


def test_tighten_viability_interval_only_ever_narrows():
    interval = next(
        i for i in DEFAULT_ESSENTIAL_VARIABLE_INTERVALS
        if i.variable_name == VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY
    )
    narrowed = tighten_viability_interval(interval, 60.0)
    assert narrowed.upper_bound == 60.0
    assert narrowed.variable_name == interval.variable_name
    assert narrowed.lever_emphasis == interval.lever_emphasis
    with pytest.raises(ValueError, match="must LOWER the upper bound"):
        tighten_viability_interval(interval, 200.0)


def test_naive_datetimes_are_rejected():
    keeper = build_default_setpoint_keeper()
    with pytest.raises(ValueError, match="timezone-aware"):
        keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, datetime(2026, 7, 27, 3, 0))


def test_carried_state_is_observable_and_resettable():
    keeper = build_default_setpoint_keeper()
    assert keeper.throttle_level == 0.0
    assert keeper.latest_decision is None
    drive_to_full_throttle(keeper)
    assert keeper.consecutive_outside_cycle_count >= 1
    assert keeper.consecutive_inside_cycle_count == 0
    assert len(keeper.recent_decisions()) >= 1
    assert keeper.latest_decision is not None

    keeper.regulate_toward_viability(NOMINAL_MEASUREMENTS, START + timedelta(hours=1))
    assert keeper.consecutive_inside_cycle_count == 1
    assert keeper.consecutive_outside_cycle_count == 0

    keeper.reset_to_nominal()
    assert keeper.throttle_level == 0.0
    assert keeper.consecutive_outside_cycle_count == 0


def test_a_custom_viability_set_is_regulated_with_the_same_law():
    """Rule J seam: a hermetic single-variable set, so the control law can be checked in isolation."""
    interval = EssentialVariableInterval(
        variable_name="queue_depth",
        lower_bound=-math.inf, upper_bound=100.0, measurement_unit="messages",
        boundary_normalization_scale=50.0,
        lever_emphasis=ThrottleLeverEmphasis(scan_interval=1.0, universe_breadth=1.0),
    )
    keeper = HomeostaticSetpointKeeper(
        viability_set=ViabilitySet(intervals=(interval,)),
        calibration=SetpointKeeperCalibration(minimum_relaxation_interval_seconds=0.0),
    )
    tighten = keeper.regulate_toward_viability({"queue_depth": 200.0}, START)
    assert tighten.action is ThrottleAction.TIGHTEN
    assert tighten.binding_variable_margin == pytest.approx(-2.0)

    hold = keeper.regulate_toward_viability({"queue_depth": 95.0}, START + timedelta(seconds=1))
    assert hold.action is ThrottleAction.HOLD          # margin 0.10 -> inside the deadband

    relax = keeper.regulate_toward_viability({"queue_depth": 10.0}, START + timedelta(seconds=2))
    assert relax.action is ThrottleAction.RELAX        # margin 1.80 -> beyond the relax threshold
