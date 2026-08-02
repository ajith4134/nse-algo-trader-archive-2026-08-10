"""Tests for the component telemetry collector (research/172 §2 input table, §5.3, §6).

Four layers:

  1. **Rule-F REAL-DATA pass** — the collector runs against the LIVE `~/.nse_algo_trader/` directory,
     the live process and the real broker-session stores, and must separate the genuinely degraded
     components from the healthy ones. Every reading is printed for by-eye inspection (research/172 §5.5
     "verified by eye"). Nothing in that directory is mutated: SQLite is opened `mode=ro` and only
     `stat()` / `read_text()` are used.
  2. **Blind-spot honesty (Rule O.3)** — Angel One's missing validity check, a missing file, an
     unreadable file, a raising `psutil`, and a raising thread enumerator must each produce an explicit
     reading with a reason, never a silent omission and never a healthy default.
  3. **Contract** — what the collector emits IS `component_health_index.ComponentTelemetrySample`, and
     the health index consumes it directly and reaches the right verdict.
  4. **Adversarial / degenerate (Rule O.4)** — empty registry, zero-size volume, permission denied,
     corrupt SQLite, duplicate injected observations, naive datetimes.
"""

from __future__ import annotations

import math
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nse_algo_trader.autopoiesis.autopoiesis_state_store import AutopoiesisStateStore
from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentHealthIndexEstimator,
    ComponentTelemetrySample,
    DegradationState,
)
from nse_algo_trader.autopoiesis.component_registry import (
    ComponentClass,
    ComponentCriticality,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)
from nse_algo_trader.autopoiesis.component_telemetry_collector import (
    GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK,
    GAP_SIGNAL_OPERATIONAL_OBSERVATION,
    GAP_SIGNAL_SQLITE_INTEGRITY_CHECK,
    GAP_SIGNAL_THREAD_HEARTBEAT,
    OBSERVABILITY_GAP_SIGNAL_WEIGHT,
    SIGNAL_ARTIFACT_LOAD_FAILURE,
    SIGNAL_BROKER_TOKEN_EXPIRED,
    SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS,
    SIGNAL_CONSECUTIVE_FAILURE_COUNT,
    SIGNAL_ERROR_RATE,
    SIGNAL_FILE_MISSING,
    SIGNAL_FILE_MTIME_AGE_HOURS,
    SIGNAL_FILE_SIZE_MEGABYTES,
    SIGNAL_FILE_ZERO_BYTES,
    SIGNAL_HOURS_SINCE_LAST_SUCCESS,
    SIGNAL_INTEGRITY_CHECK_FAILURE,
    SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT,
    SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,
    SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES,
    SIGNAL_STALENESS_RATIO,
    SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES,
    SIGNAL_STATE_VOLUME_USED_FRACTION,
    SIGNAL_THREAD_NOT_ALIVE,
    SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES,
    UNAVAILABLE_SIGNAL_PERSISTENCE_PREFIX,
    BrokerSessionValidityReading,
    ComponentTelemetryCollector,
    HostResourceSnapshot,
    InjectedComponentObservation,
    RealBrokerSessionValidityProbe,
    TelemetryCollectionCalibration,
    VitalSignAvailability,
    telemetry_signal_severity_specs,
)

REAL_ORGANISM_STATE_DIRECTORY = Path("~/.nse_algo_trader").expanduser()

#: Keeps the real-data pass fast: the organism's `market_data.sqlite3` is 202 MiB and a full
#: `PRAGMA integrity_check` on it takes ~21 s (measured). Above this ceiling the collector must report
#: an explicit blind spot rather than a fabricated "ok" — which this test also asserts.
REAL_DATA_INTEGRITY_CHECK_CEILING_BYTES = 32 * 1024 * 1024


# ===================================================================================================
# Test doubles — Rule-J DI seams. They live only here; production never selects them.
# ===================================================================================================


class StubHostResourceProbe:
    def __init__(self, snapshot: HostResourceSnapshot) -> None:
        self._snapshot = snapshot

    def read_host_resource_snapshot(self, state_volume_path: Path) -> HostResourceSnapshot:
        return self._snapshot


class RaisingHostResourceProbe:
    def read_host_resource_snapshot(self, state_volume_path: Path) -> HostResourceSnapshot:
        raise RuntimeError("psutil: [Errno 3] No such process (pid=12345)")


class StubThreadNameReader:
    def __init__(self, *names: str) -> None:
        self._names = frozenset(names)

    def read_running_thread_names(self) -> frozenset[str]:
        return self._names


class RaisingThreadNameReader:
    def read_running_thread_names(self) -> frozenset[str]:
        raise RuntimeError("threading.enumerate() exploded")


class StubBrokerSessionValidityProbe:
    def __init__(self, reading_by_component_id: dict[str, BrokerSessionValidityReading]) -> None:
        self._reading_by_component_id = reading_by_component_id

    def read_broker_session_validity(self, component, now) -> BrokerSessionValidityReading:
        return self._reading_by_component_id[component.component_id]



def _production_store_fingerprint() -> tuple[bool, int, int]:
    """(exists, size, mtime_ns) of the PRODUCTION homeostat store — compared before/after a test.

    The live service creates this file for real, so its existence is not a failure; a change to it
    during a test IS.
    """
    path = REAL_ORGANISM_STATE_DIRECTORY / "autopoiesis_homeostat.sqlite3"
    if not path.exists():
        return (False, 0, 0)
    stat_result = path.stat()
    return (True, stat_result.st_size, stat_result.st_mtime_ns)

def make_state_store(tmp_path: Path) -> AutopoiesisStateStore:
    """Every test writes its telemetry to tmp_path — never to `~/.nse_algo_trader/`."""
    return AutopoiesisStateStore(tmp_path / "autopoiesis_homeostat.sqlite3")


def make_store_component(component_id: str, path: Path, staleness_hours: float = 24.0):
    return RegisteredComponent(
        component_id=component_id,
        component_class=ComponentClass.PERSISTENT_STORE,
        criticality=ComponentCriticality.VITAL,
        state_path=path,
        maximum_staleness_hours=staleness_hours,
        maintained_by=(),
        role_description="synthetic store for the telemetry collector tests",
    )


def make_artifact_component(component_id: str, path: Path, staleness_hours: float = 24.0):
    return RegisteredComponent(
        component_id=component_id,
        component_class=ComponentClass.PERSISTED_ARTIFACT,
        criticality=ComponentCriticality.SUPPORTING,
        state_path=path,
        maximum_staleness_hours=staleness_hours,
        maintained_by=(),
        role_description="synthetic artifact for the telemetry collector tests",
    )


def collector_over(components, tmp_path: Path, **kwargs) -> ComponentTelemetryCollector:
    kwargs.setdefault("state_store", make_state_store(tmp_path))
    kwargs.setdefault("state_volume_path", tmp_path)
    return ComponentTelemetryCollector(
        registry=OrganismComponentRegistry(components=tuple(components)), **kwargs
    )


# ===================================================================================================
# 1. RULE-F REAL-DATA PASS — the live organism, printed for by-eye inspection.
# ===================================================================================================


@pytest.mark.skipif(
    not REAL_ORGANISM_STATE_DIRECTORY.exists(),
    reason="the real organism state directory is not present on this machine",
)
def test_real_organism_sweep_separates_the_genuinely_degraded_components(tmp_path, capsys):
    """Rule F: run against the REAL organism and detect the components that are really degraded.

    research/172 §5.5 names the bar: the readings must separate the genuinely stale real components
    (a days-old `market_data.sqlite3`, an expired broker token) from the healthy ones, verified by eye.
    """
    production_store_fingerprint_before = _production_store_fingerprint()
    collector = ComponentTelemetryCollector(
        registry=build_default_component_registry(),
        state_store=make_state_store(tmp_path),          # tmp_path — the real dir is never written to
        calibration=TelemetryCollectionCalibration(
            maximum_inline_integrity_check_bytes=REAL_DATA_INTEGRITY_CHECK_CEILING_BYTES,
        ),
    )
    collection = collector.collect_organism_vital_signs()

    with capsys.disabled():
        print("\n" + "=" * 118)
        print("RULE-F REAL-DATA PASS — every vital sign of the live organism, read from the organism")
        print("=" * 118)
        print(collection.describe_readings())
        print("-" * 118)
        print(f"diagnostics: {collection.diagnostics}")
        print(f"observability: {collection.diagnostics.observability_fraction:.1%} of vital signs read")
        print("=" * 118 + "\n")

    diagnostics = collection.diagnostics
    assert diagnostics.component_count == len(build_default_component_registry().self_components())
    assert diagnostics.reading_count > 0
    # Every reading was persisted (one row each, unavailable ones under the `unavailable:` prefix).
    assert diagnostics.persisted_sample_row_count == diagnostics.reading_count
    assert diagnostics.persistence_failure_reason == ""

    # -- the genuinely stale store -----------------------------------------------------------------
    market_data_staleness = collection.reading_for("store.market_data", SIGNAL_STALENESS_RATIO)
    assert market_data_staleness is not None, "market_data.sqlite3 staleness was not read at all"
    assert market_data_staleness.is_observed
    assert market_data_staleness.severity_oriented_value is not None
    # The staleness RATIO is deliberately not asserted to exceed 1.0. Market data only ages in TRADING
    # time: on a Monday pre-open the store is legitimately ~60 h old because the market shut on Friday,
    # and the budget was widened to span a weekend on 2026-07-27 for exactly that reason (see
    # `component_registry`). What must hold is that the ratio is a real measurement consistent with the
    # age and the declared budget — not that a normal weekend closure reads as a fault.
    market_data_age = collection.reading_for("store.market_data", SIGNAL_FILE_MTIME_AGE_HOURS)
    assert market_data_age is not None and market_data_age.severity_oriented_value is not None
    registered_market_data = build_default_component_registry().find("store.market_data")
    assert registered_market_data is not None
    budget_hours = registered_market_data.maximum_staleness_hours
    assert budget_hours is not None
    assert market_data_staleness.severity_oriented_value == pytest.approx(
        market_data_age.severity_oriented_value / budget_hours, rel=1e-6
    ), "the staleness ratio must be the measured age over the DECLARED budget, not a hard-coded one"

    # ...against a store that IS being written: the collector must NOT flag everything.
    news_staleness = collection.reading_for("store.news", SIGNAL_STALENESS_RATIO)
    assert news_staleness is not None and news_staleness.severity_oriented_value is not None
    assert news_staleness.severity_oriented_value < 1.0, (
        "news.sqlite3 is actively written — a collector that flags it too is not discriminating"
    )
    assert news_staleness.severity_oriented_value < market_data_staleness.severity_oriented_value

    # -- the broker sessions -----------------------------------------------------------------------
    expired_sessions = [
        reading.component_id
        for reading in collection.readings
        if reading.signal_name == SIGNAL_BROKER_TOKEN_EXPIRED
        and reading.severity_oriented_value == 1.0
    ]
    assert expired_sessions, (
        "at least one real broker token (Breeze, generated days ago) must read as expired"
    )
    for component_id in ("session.kite", "session.breeze"):
        expired = collection.reading_for(component_id, SIGNAL_BROKER_TOKEN_EXPIRED)
        shortfall = collection.reading_for(component_id, SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS)
        assert expired is not None and expired.is_observed, f"{component_id} validity was not read"
        assert shortfall is not None and shortfall.is_observed
        assert shortfall.severity_oriented_value is not None
        # The two signals must agree: an expired token has run past the whole renewal horizon.
        if expired.severity_oriented_value == 1.0:
            assert shortfall.severity_oriented_value >= 2.0
        else:
            assert shortfall.severity_oriented_value >= 0.0

    # -- Angel One's structural blind spot ---------------------------------------------------------
    angel_one_readings = collection.readings_for("session.angel_one")
    assert len(angel_one_readings) == 1
    gap = angel_one_readings[0]
    assert gap.signal_name == GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK
    assert gap.availability is VitalSignAvailability.NOT_INSTRUMENTED
    assert "no validity check available" in gap.unavailable_reason
    assert collection.reading_for("session.angel_one", SIGNAL_BROKER_TOKEN_EXPIRED) is None, (
        "Angel One must NOT get a fabricated token-validity reading"
    )

    # -- the model-age vital sign that exposes the never-retrains defect ---------------------------
    model_age = collection.reading_for("artifact.win_probability_model", SIGNAL_FILE_MTIME_AGE_HOURS)
    model_staleness = collection.reading_for("artifact.win_probability_model", SIGNAL_STALENESS_RATIO)
    model_load = collection.reading_for("artifact.win_probability_model", SIGNAL_ARTIFACT_LOAD_FAILURE)
    assert model_age is not None and model_age.is_observed
    assert model_staleness is not None and model_staleness.is_observed
    assert model_load is not None and model_load.is_observed, "the real .joblib must be load-tested"
    assert model_load.severity_oriented_value == 0.0, "the real win-probability model must deserialize"

    # -- the real integrity checks that DID run, and the one that honestly did not ------------------
    assert diagnostics.integrity_check_performed_count >= 1, (
        "real PRAGMA integrity_check must have run against the small real SQLite stores"
    )
    for component_id in ("store.experience_memory", "store.news", "store.safety_incidents"):
        verdict = collection.reading_for(component_id, SIGNAL_INTEGRITY_CHECK_FAILURE)
        assert verdict is not None and verdict.is_observed
        assert verdict.severity_oriented_value == 0.0, f"{component_id} reported corruption: {verdict}"
    market_data_integrity = collection.reading_for(
        "store.market_data", GAP_SIGNAL_SQLITE_INTEGRITY_CHECK
    )
    assert market_data_integrity is not None, (
        "the oversized store's integrity must be reported as UNKNOWN, not silently skipped"
    )
    assert "ceiling" in market_data_integrity.unavailable_reason

    # -- real host resources -----------------------------------------------------------------------
    for signal_name in (
        SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES,
        SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,
        SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT,
        SIGNAL_STATE_VOLUME_USED_FRACTION,
        SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES,
    ):
        matches = [r for r in collection.readings if r.signal_name == signal_name]
        assert len(matches) == 1 and matches[0].is_observed, f"{signal_name} was not really measured"
    resident = collection.reading_for("host.process_memory", SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES)
    assert resident is not None and resident.severity_oriented_value is not None
    assert resident.severity_oriented_value > 1.0, "this pytest process really does use memory"

    # -- the real state directory was NOT mutated BY THIS TEST -------------------------------------
    # NOTE (2026-07-27): this originally asserted the production store must not EXIST at all. That
    # became wrong the moment the homeostat was wired into `LivePaperTradingService`, which legitimately
    # creates `~/.nse_algo_trader/autopoiesis_homeostat.sqlite3` in production. The real guarantee this
    # test needs is that *this test run* neither created nor modified it — so it is compared against the
    # snapshot taken before the sweep, which holds whether or not the service has ever run.
    assert _production_store_fingerprint() == production_store_fingerprint_before, (
        "this test mutated the organism's real state directory — its store must live in tmp_path"
    )


@pytest.mark.skipif(
    not REAL_ORGANISM_STATE_DIRECTORY.exists(),
    reason="the real organism state directory is not present on this machine",
)
def test_real_organism_readings_drive_the_health_index_to_the_right_verdicts(tmp_path, capsys):
    """Rule F, end to end: the collector's samples feed the health index with no adaptation."""
    collector = ComponentTelemetryCollector(
        registry=build_default_component_registry(),
        state_store=make_state_store(tmp_path),
        calibration=TelemetryCollectionCalibration(
            maximum_inline_integrity_check_bytes=REAL_DATA_INTEGRITY_CHECK_CEILING_BYTES,
        ),
    )
    collection = collector.collect_organism_vital_signs()
    specs = collector.signal_severity_specs

    health_by_component_id = {}
    for sample in collection.samples:
        estimator = ComponentHealthIndexEstimator(sample.component_id, signal_severity_specs=specs)
        health_by_component_id[sample.component_id] = estimator.ingest(sample)

    with capsys.disabled():
        print("\nRULE-F REAL-DATA PASS — health index over the real readings")
        print("-" * 96)
        for assessment in sorted(health_by_component_id.values(), key=lambda a: a.health_index):
            worst = assessment.worst_contributing_signal
            print(
                f"  {assessment.component_id:38s} h={assessment.health_index:.3f} "
                f"{assessment.degradation_state.value:9s} worst={worst}"
            )
        print("-" * 96 + "\n")

    news = health_by_component_id["store.news"]
    assert news.degradation_state is DegradationState.HEALTHY
    # `store.market_data` is intentionally NOT asserted degraded: its staleness budget now spans a
    # weekend, so on a non-trading day a healthy verdict is the CORRECT one. The genuinely-degraded
    # components below are what this pass must separate from the healthy ones.

    breeze = health_by_component_id["session.breeze"]
    assert breeze.degradation_state is DegradationState.FAILED, (
        f"an expired broker token must read FAILED, got {breeze}"
    )

    # A blind spot is DEGRADED — never healthy, never FAILED (weight 0.5 -> health index 0.5).
    angel_one = health_by_component_id["session.angel_one"]
    assert angel_one.degradation_state is DegradationState.DEGRADED
    assert angel_one.health_index == pytest.approx(1.0 - OBSERVABILITY_GAP_SIGNAL_WEIGHT)


# ===================================================================================================
# 2. BLIND-SPOT HONESTY (Rule O.3)
# ===================================================================================================


def test_angel_one_emits_an_explicit_no_validity_check_signal_not_a_healthy_default(tmp_path):
    """The whole point: Angel One has no `is_still_valid`, so it gets a gap signal, not `expired=0`."""
    registry = build_default_component_registry()
    angel_one = registry.find("session.angel_one")
    assert angel_one is not None
    reading = RealBrokerSessionValidityProbe().read_broker_session_validity(
        angel_one, datetime.now(UTC)
    )
    assert reading.has_validity_check is False
    assert reading.is_still_valid is None, "no boolean may be invented for an unobservable session"
    assert "no validity check available" in reading.unavailable_reason
    assert "angel_one" in reading.unavailable_reason

    collector = collector_over([angel_one], tmp_path)
    collection = collector.collect_organism_vital_signs()
    readings = collection.readings_for("session.angel_one")
    assert [r.signal_name for r in readings] == [GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK]
    assert readings[0].availability is VitalSignAvailability.NOT_INSTRUMENTED
    assert readings[0].severity_oriented_value == 1.0, "the gap itself is the measurement"
    assert collection.diagnostics.observability_gap_reading_count == 1
    assert collection.diagnostics.observed_reading_count == 0


def test_missing_file_reports_absence_as_an_observation_and_the_rest_as_unavailable(tmp_path):
    """Absence is an OBSERVATION ("we looked, it is not there"); the derived signals are UNAVAILABLE."""
    component = make_store_component("store.absent", tmp_path / "never_created.sqlite3")
    collection = collector_over([component], tmp_path).collect_organism_vital_signs()

    missing = collection.reading_for("store.absent", SIGNAL_FILE_MISSING)
    assert missing is not None and missing.is_observed and missing.severity_oriented_value == 1.0

    for signal_name in (
        SIGNAL_FILE_MTIME_AGE_HOURS,
        SIGNAL_STALENESS_RATIO,
        SIGNAL_FILE_SIZE_MEGABYTES,
        SIGNAL_FILE_ZERO_BYTES,
    ):
        reading = collection.reading_for("store.absent", signal_name)
        assert reading is not None, f"{signal_name} was silently omitted — Rule O.3 forbids that"
        assert reading.availability is VitalSignAvailability.UNAVAILABLE
        assert reading.severity_oriented_value is None
        assert "does not exist" in reading.unavailable_reason
        assert math.isnan(reading.health_index_signal_value)

    assert collection.diagnostics.unavailable_reading_count >= 4


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_unreadable_file_reports_every_signal_as_unavailable_with_the_os_reason(tmp_path):
    """Permission denied: we do not even know whether the file exists, so NOTHING may be asserted."""
    protected_directory = tmp_path / "locked"
    protected_directory.mkdir()
    database_path = protected_directory / "store.sqlite3"
    database_path.write_bytes(b"not really sqlite")
    protected_directory.chmod(0o000)
    try:
        component = make_store_component("store.locked", database_path)
        collection = collector_over([component], tmp_path).collect_organism_vital_signs()
        readings = collection.readings_for("store.locked")
        assert readings, "a locked component must still produce readings"
        unavailable = [r for r in readings if r.availability is VitalSignAvailability.UNAVAILABLE]
        assert len(unavailable) >= 5
        missing = collection.reading_for("store.locked", SIGNAL_FILE_MISSING)
        assert missing is not None
        assert missing.availability is VitalSignAvailability.UNAVAILABLE, (
            "with permission denied the collector cannot claim the file is present OR absent"
        )
        assert "Permission" in missing.unavailable_reason or "cannot stat" in missing.unavailable_reason
    finally:
        protected_directory.chmod(0o755)


def test_a_raising_psutil_probe_yields_unavailable_host_signals_with_the_exception_text(tmp_path):
    """Rule O.4 adversarial: `psutil` blowing up must not blank the sweep or fake a healthy host."""
    host_components = [
        RegisteredComponent(component_id, ComponentClass.HOST_RESOURCE, ComponentCriticality.VITAL,
                            maintained_by=(), role_description="host resource under test")
        for component_id in ("host.process_memory", "host.process_cpu", "host.open_file_descriptors",
                             "host.disk_free")
    ]
    collection = collector_over(
        host_components, tmp_path, host_resource_probe=RaisingHostResourceProbe()
    ).collect_organism_vital_signs()

    assert collection.readings, "a raising probe must still produce readings"
    for reading in collection.readings:
        assert reading.availability is VitalSignAvailability.UNAVAILABLE
        assert "No such process" in reading.unavailable_reason
    assert collection.diagnostics.observed_reading_count == 0
    assert collection.diagnostics.unavailable_reading_count == len(collection.readings)


def test_a_raising_thread_enumerator_reports_liveness_as_unavailable_not_dead(tmp_path):
    """"Cannot tell" is not "dead": inventing `thread_not_alive=1.0` would trigger a false repair."""
    component = RegisteredComponent(
        "thread.live_paper_loop", ComponentClass.BACKGROUND_THREAD, ComponentCriticality.VITAL,
        maintained_by=(), role_description="the main writer loop",
    )
    collection = collector_over(
        [component], tmp_path, running_thread_name_reader=RaisingThreadNameReader()
    ).collect_organism_vital_signs()
    liveness = collection.reading_for("thread.live_paper_loop", SIGNAL_THREAD_NOT_ALIVE)
    assert liveness is not None
    assert liveness.availability is VitalSignAvailability.UNAVAILABLE
    assert "exploded" in liveness.unavailable_reason


def test_an_uninjected_in_process_component_reports_an_operational_blind_spot(tmp_path):
    """A cadence engine nobody reported on is UNKNOWN, not fine."""
    component = RegisteredComponent(
        "engine.capital_allocation", ComponentClass.CADENCE_ENGINE, ComponentCriticality.SUPPORTING,
        maintained_by=(), role_description="CVXPY joint capital allocator",
    )
    collection = collector_over([component], tmp_path).collect_organism_vital_signs()
    readings = collection.readings_for("engine.capital_allocation")
    assert [r.signal_name for r in readings] == [GAP_SIGNAL_OPERATIONAL_OBSERVATION]
    assert readings[0].availability is VitalSignAvailability.NOT_INSTRUMENTED
    assert "no operational observation was injected" in readings[0].unavailable_reason


def test_a_thread_without_a_heartbeat_stamp_reports_the_heartbeat_gap_explicitly(tmp_path):
    component = RegisteredComponent(
        "thread.news_acquisition", ComponentClass.BACKGROUND_THREAD, ComponentCriticality.SUPPORTING,
        maintained_by=(), role_description="news acquisition ladder",
    )
    collection = collector_over(
        [component], tmp_path, running_thread_name_reader=StubThreadNameReader("news-acquisition-ladder")
    ).collect_organism_vital_signs()
    liveness = collection.reading_for("thread.news_acquisition", SIGNAL_THREAD_NOT_ALIVE)
    assert liveness is not None and liveness.severity_oriented_value == 0.0
    gap = collection.reading_for("thread.news_acquisition", GAP_SIGNAL_THREAD_HEARTBEAT)
    assert gap is not None and gap.availability is VitalSignAvailability.NOT_INSTRUMENTED
    assert "wedged-but-alive" in gap.unavailable_reason


# ===================================================================================================
# 3. CONTRACT WITH THE HEALTH INDEX
# ===================================================================================================


def test_emitted_samples_satisfy_the_component_health_index_contract_exactly(tmp_path):
    collection = ComponentTelemetryCollector(
        registry=build_default_component_registry(),
        state_store=make_state_store(tmp_path),
        calibration=TelemetryCollectionCalibration(perform_sqlite_integrity_checks=False),
    ).collect_organism_vital_signs()

    assert collection.samples
    for sample in collection.samples:
        assert isinstance(sample, ComponentTelemetrySample)
        assert sample.captured_at.tzinfo is not None
        assert sample.captured_at == collection.collected_at
        assert sample.signal_values, f"{sample.component_id} emitted an empty sample"
        for value in sample.signal_values.values():
            assert isinstance(value, float)
        # Every sampled component is a SELF member — the boundary is respected.
        assert sample.component_id not in build_default_component_registry().exogenous_component_ids()


def test_every_declared_severity_spec_obeys_the_higher_is_worse_convention():
    """`SignalSeveritySpec.__post_init__` enforces `alarm > nominal`, i.e. rising value = degrading."""
    specs = telemetry_signal_severity_specs()
    assert specs
    for spec in specs:
        assert spec.alarm_value > spec.nominal_value
        assert 0.0 < spec.weight <= 1.0
    gap_specs = [s for s in specs if s.signal_name.startswith("observability_gap:")]
    assert len(gap_specs) == 4
    for spec in gap_specs:
        assert spec.weight == OBSERVABILITY_GAP_SIGNAL_WEIGHT


def test_a_stale_store_reads_worse_than_a_fresh_one_through_the_health_index(tmp_path):
    """The end-to-end polarity check: a bigger raw signal must produce a LOWER health index."""
    fresh_path = tmp_path / "fresh.sqlite3"
    stale_path = tmp_path / "stale.sqlite3"
    for path in (fresh_path, stale_path):
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE t (v INTEGER)")
        connection.commit()
        connection.close()
    stale_epoch = (datetime.now(UTC) - timedelta(hours=96)).timestamp()
    os.utime(stale_path, (stale_epoch, stale_epoch))

    components = [
        make_store_component("store.fresh", fresh_path, staleness_hours=24.0),
        make_store_component("store.stale", stale_path, staleness_hours=24.0),
    ]
    collector = collector_over(components, tmp_path)
    collection = collector.collect_organism_vital_signs()

    assessments = {}
    for sample in collection.samples:
        estimator = ComponentHealthIndexEstimator(
            sample.component_id, signal_severity_specs=collector.signal_severity_specs
        )
        assessments[sample.component_id] = estimator.ingest(sample)
    assert assessments["store.stale"].health_index < assessments["store.fresh"].health_index
    assert assessments["store.stale"].degradation_state is DegradationState.FAILED
    assert assessments["store.fresh"].degradation_state is DegradationState.HEALTHY


# ===================================================================================================
# 4. ADVERSARIAL / DEGENERATE (Rule O.4)
# ===================================================================================================


def test_an_empty_registry_collects_nothing_without_raising(tmp_path):
    collection = collector_over([], tmp_path).collect_organism_vital_signs()
    assert collection.samples == ()
    assert collection.readings == ()
    assert collection.diagnostics.component_count == 0
    assert collection.diagnostics.persisted_sample_row_count == 0
    assert collection.diagnostics.observability_fraction == 1.0
    assert collection.essential_variable_measurements() == {}


def test_a_zero_byte_volume_is_unavailable_not_zero_percent_used(tmp_path):
    """Rule O.4 degenerate: a total of 0 bytes makes the used-fraction undefined, not `0.0`."""
    component = RegisteredComponent(
        "host.disk_free", ComponentClass.HOST_RESOURCE, ComponentCriticality.VITAL,
        maintained_by=(), role_description="free disk on the state volume",
    )
    snapshot = HostResourceSnapshot(state_volume_total_bytes=0.0, state_volume_free_bytes=0.0)
    collection = collector_over(
        [component], tmp_path, host_resource_probe=StubHostResourceProbe(snapshot)
    ).collect_organism_vital_signs()

    used_fraction = collection.reading_for("host.disk_free", SIGNAL_STATE_VOLUME_USED_FRACTION)
    assert used_fraction is not None
    assert used_fraction.availability is VitalSignAvailability.UNAVAILABLE
    assert "total size" in used_fraction.unavailable_reason
    # A genuinely FULL volume, by contrast, is a real observation at the failed end of the ramp.
    shortfall = collection.reading_for(
        "host.disk_free", SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES
    )
    assert shortfall is not None and shortfall.is_observed
    assert shortfall.severity_oriented_value == pytest.approx(5.0)


def test_a_full_disk_saturates_the_shortfall_signal_at_the_declared_requirement(tmp_path):
    component = RegisteredComponent(
        "host.disk_free", ComponentClass.HOST_RESOURCE, ComponentCriticality.VITAL,
        maintained_by=(), role_description="free disk on the state volume",
    )
    gigabyte = 1024.0 ** 3
    snapshot = HostResourceSnapshot(
        state_volume_total_bytes=100.0 * gigabyte, state_volume_free_bytes=0.25 * gigabyte
    )
    collection = collector_over(
        [component], tmp_path, host_resource_probe=StubHostResourceProbe(snapshot)
    ).collect_organism_vital_signs()
    used = collection.reading_for("host.disk_free", SIGNAL_STATE_VOLUME_USED_FRACTION)
    shortfall = collection.reading_for("host.disk_free", SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES)
    assert used is not None and used.severity_oriented_value == pytest.approx(0.9975)
    assert shortfall is not None and shortfall.severity_oriented_value == pytest.approx(4.75)


def test_a_corrupt_sqlite_file_is_detected_by_the_real_integrity_check(tmp_path):
    corrupt_path = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(corrupt_path)
    connection.execute("CREATE TABLE t (v INTEGER)")
    connection.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(500)])
    connection.commit()
    connection.close()
    with corrupt_path.open("r+b") as handle:      # scribble over a page, mid-file
        handle.seek(4096)
        handle.write(b"\xde\xad\xbe\xef" * 256)

    component = make_store_component("store.corrupt", corrupt_path)
    collection = collector_over([component], tmp_path).collect_organism_vital_signs()
    verdict = collection.reading_for("store.corrupt", SIGNAL_INTEGRITY_CHECK_FAILURE)
    assert verdict is not None
    assert verdict.is_observed
    assert verdict.severity_oriented_value == 1.0, f"corruption was not detected: {verdict.describe()}"
    assert verdict.raw_observation and verdict.raw_observation != "ok"


def test_the_integrity_verdict_is_cached_between_sweeps_on_its_cadence(tmp_path):
    database_path = tmp_path / "cached.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE t (v INTEGER)")
    connection.commit()
    connection.close()
    collector = collector_over([make_store_component("store.cached", database_path)], tmp_path)

    first = collector.collect_organism_vital_signs()
    second = collector.collect_organism_vital_signs()
    assert first.diagnostics.integrity_check_performed_count == 1
    assert second.diagnostics.integrity_check_performed_count == 0
    assert second.diagnostics.integrity_check_skipped_count == 1
    cached_verdict = second.reading_for("store.cached", SIGNAL_INTEGRITY_CHECK_FAILURE)
    assert cached_verdict is not None and cached_verdict.is_observed
    assert "cached" in cached_verdict.raw_observation


def test_disabling_integrity_checks_reports_the_gap_rather_than_a_clean_bill_of_health(tmp_path):
    database_path = tmp_path / "unchecked.sqlite3"
    sqlite3.connect(database_path).close()
    collection = collector_over(
        [make_store_component("store.unchecked", database_path)], tmp_path,
        calibration=TelemetryCollectionCalibration(perform_sqlite_integrity_checks=False),
    ).collect_organism_vital_signs()
    gap = collection.reading_for("store.unchecked", GAP_SIGNAL_SQLITE_INTEGRITY_CHECK)
    assert gap is not None and gap.availability is VitalSignAvailability.NOT_INSTRUMENTED
    assert "disabled by configuration" in gap.unavailable_reason
    assert collection.reading_for("store.unchecked", SIGNAL_INTEGRITY_CHECK_FAILURE) is None


def test_an_unloadable_artifact_is_flagged_even_though_the_file_exists(tmp_path):
    artifact_path = tmp_path / "world_model_counts.json"
    artifact_path.write_text("{not valid json at all")
    collection = collector_over(
        [make_artifact_component("artifact.broken", artifact_path)], tmp_path
    ).collect_organism_vital_signs()
    missing = collection.reading_for("artifact.broken", SIGNAL_FILE_MISSING)
    load_failure = collection.reading_for("artifact.broken", SIGNAL_ARTIFACT_LOAD_FAILURE)
    assert missing is not None and missing.severity_oriented_value == 0.0
    assert load_failure is not None and load_failure.severity_oriented_value == 1.0
    assert "JSONDecodeError" in load_failure.raw_observation


def test_a_zero_byte_store_is_flagged_as_truncated(tmp_path):
    empty_path = tmp_path / "empty.sqlite3"
    empty_path.touch()
    collection = collector_over(
        [make_store_component("store.empty", empty_path)], tmp_path
    ).collect_organism_vital_signs()
    zero_bytes = collection.reading_for("store.empty", SIGNAL_FILE_ZERO_BYTES)
    assert zero_bytes is not None and zero_bytes.severity_oriented_value == 1.0


def test_write_ahead_log_size_is_measured_and_absent_wal_reads_as_a_true_zero(tmp_path):
    database_path = tmp_path / "walled.sqlite3"
    sqlite3.connect(database_path).close()
    component = make_store_component("store.walled", database_path)

    collection = collector_over([component], tmp_path).collect_organism_vital_signs()
    reading = collection.reading_for("store.walled", SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES)
    assert reading is not None and reading.is_observed and reading.severity_oriented_value == 0.0

    database_path.with_name(database_path.name + "-wal").write_bytes(b"\x00" * (2 * 1024 * 1024))
    collection = collector_over([component], tmp_path).collect_organism_vital_signs()
    reading = collection.reading_for("store.walled", SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES)
    assert reading is not None and reading.severity_oriented_value == pytest.approx(2.0)


def test_live_thread_liveness_is_read_from_the_real_threading_enumerate(tmp_path):
    """Rule F in miniature: a REAL thread, really enumerated — no stub in this one."""
    component = RegisteredComponent(
        "thread.live_paper_loop", ComponentClass.BACKGROUND_THREAD, ComponentCriticality.VITAL,
        maintained_by=(), role_description="the main writer loop",
    )
    collector = collector_over([component], tmp_path)

    before = collector.collect_organism_vital_signs()
    dead = before.reading_for("thread.live_paper_loop", SIGNAL_THREAD_NOT_ALIVE)
    assert dead is not None and dead.severity_oriented_value == 1.0

    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, name="live-paper-loop", daemon=True)
    thread.start()
    try:
        during = collector.collect_organism_vital_signs()
        alive = during.reading_for("thread.live_paper_loop", SIGNAL_THREAD_NOT_ALIVE)
        assert alive is not None and alive.severity_oriented_value == 0.0
        assert "is alive" in alive.raw_observation
    finally:
        stop.set()
        thread.join(timeout=5.0)


def test_injected_observations_become_real_signals(tmp_path):
    component = RegisteredComponent(
        "adapter.multi_broker_historical_bars", ComponentClass.DATA_ADAPTER,
        ComponentCriticality.VITAL, maintained_by=(), role_description="failover bar fleet",
    )
    now = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
    observation = InjectedComponentObservation(
        component_id="adapter.multi_broker_historical_bars",
        last_success_at=now - timedelta(hours=6),
        consecutive_failure_count=3,
        error_rate=0.4,
    )
    collection = collector_over([component], tmp_path).collect_organism_vital_signs(
        now=now, injected_observations=[observation]
    )
    component_id = "adapter.multi_broker_historical_bars"
    assert collection.reading_for(component_id, SIGNAL_HOURS_SINCE_LAST_SUCCESS).severity_oriented_value \
        == pytest.approx(6.0)
    assert collection.reading_for(component_id, SIGNAL_CONSECUTIVE_FAILURE_COUNT).severity_oriented_value \
        == pytest.approx(3.0)
    assert collection.reading_for(component_id, SIGNAL_ERROR_RATE).severity_oriented_value \
        == pytest.approx(0.4)
    assert collection.reading_for(component_id, GAP_SIGNAL_OPERATIONAL_OBSERVATION) is None


def test_duplicate_injected_observations_raise_rather_than_silently_picking_one(tmp_path):
    observation = InjectedComponentObservation("engine.curiosity", consecutive_failure_count=1)
    with pytest.raises(ValueError, match="two InjectedComponentObservation"):
        collector_over([], tmp_path).collect_organism_vital_signs(
            injected_observations=[observation, observation]
        )


def test_observations_for_unrecognised_components_are_surfaced_not_swallowed(tmp_path):
    collection = collector_over([], tmp_path).collect_organism_vital_signs(
        injected_observations=[InjectedComponentObservation("intruder.unknown", error_rate=1.0)]
    )
    assert collection.diagnostics.unrecognized_injected_observation_ids == ("intruder.unknown",)


def test_naive_datetimes_are_rejected_at_every_boundary(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        collector_over([], tmp_path).collect_organism_vital_signs(now=datetime(2026, 7, 27, 3, 0))
    with pytest.raises(ValueError, match="timezone-aware"):
        InjectedComponentObservation("engine.curiosity", last_success_at=datetime(2026, 7, 27))


def test_an_unavailable_reading_never_carries_a_value_and_always_carries_a_reason(tmp_path):
    """The invariant that makes Rule O.3 structural rather than a convention."""
    from nse_algo_trader.autopoiesis.component_telemetry_collector import VitalSignReading

    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="must not carry a value"):
        VitalSignReading("c", "s", now, VitalSignAvailability.UNAVAILABLE, 0.0, "u", "n", "", "why")
    with pytest.raises(ValueError, match="must state WHY"):
        VitalSignReading("c", "s", now, VitalSignAvailability.UNAVAILABLE, None, "u", "n")
    with pytest.raises(ValueError, match="only an UNAVAILABLE reading"):
        VitalSignReading("c", "s", now, VitalSignAvailability.OBSERVED, None, "u", "n")
    with pytest.raises(ValueError, match="non-finite"):
        VitalSignReading("c", "s", now, VitalSignAvailability.OBSERVED, math.nan, "u", "n")


# ===================================================================================================
# 5. PERSISTENCE
# ===================================================================================================


def test_every_reading_is_persisted_and_unavailable_ones_as_an_explicit_marker(tmp_path):
    """SQLite rejects NaN in a NOT NULL REAL column, so unavailability is stored as a positive fact."""
    store = make_state_store(tmp_path)
    component = make_store_component("store.absent", tmp_path / "never_created.sqlite3")
    collector = ComponentTelemetryCollector(
        registry=OrganismComponentRegistry(components=(component,)),
        state_store=store,
        state_volume_path=tmp_path,
    )
    collection = collector.collect_organism_vital_signs()

    assert collection.diagnostics.persisted_sample_row_count == len(collection.readings)
    assert store.telemetry_sample_count("store.absent") == len(collection.readings)

    persisted = {name: value for _, name, value in store.read_recent_telemetry("store.absent")}
    assert persisted[SIGNAL_FILE_MISSING] == 1.0
    marker = f"{UNAVAILABLE_SIGNAL_PERSISTENCE_PREFIX}{SIGNAL_STALENESS_RATIO}"
    assert persisted[marker] == 1.0, "an unavailable signal must persist as an explicit marker row"
    assert SIGNAL_STALENESS_RATIO not in persisted, "no fabricated value may be persisted"
    store.close()


def test_a_missing_state_store_is_reported_rather_than_pretending_to_persist(tmp_path):
    collector = ComponentTelemetryCollector(
        registry=OrganismComponentRegistry(
            components=(make_store_component("store.x", tmp_path / "x.sqlite3"),)
        ),
        state_store=None,
        state_volume_path=tmp_path,
    )
    collection = collector.collect_organism_vital_signs()
    assert collection.diagnostics.persisted_sample_row_count == 0
    assert "not persisted" in collection.diagnostics.persistence_failure_reason


def test_a_failing_state_store_surfaces_the_failure_without_losing_the_sweep(tmp_path):
    class ExplodingStateStore:
        def record_telemetry_samples(self, samples):
            raise sqlite3.OperationalError("database is locked")

    collector = ComponentTelemetryCollector(
        registry=OrganismComponentRegistry(
            components=(make_store_component("store.x", tmp_path / "x.sqlite3"),)
        ),
        state_store=ExplodingStateStore(),  # type: ignore[arg-type]
        state_volume_path=tmp_path,
    )
    collection = collector.collect_organism_vital_signs()
    assert collection.readings, "a persistence failure must not lose the readings"
    assert collection.diagnostics.persisted_sample_row_count == 0
    assert "database is locked" in collection.diagnostics.persistence_failure_reason
