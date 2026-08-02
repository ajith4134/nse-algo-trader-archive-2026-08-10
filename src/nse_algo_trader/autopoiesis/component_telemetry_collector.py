"""Trunk X AUTOPOIESIS — the RAW-INPUT PIPELINE: the organism's own vital signs, read from itself.

This is the Monitor phase of the MAPE-K cycle (research/172 §3) and the "raw-input pipeline" acceptance
criterion of research/172 §5.3: **every input in §2 read from the REAL organism, never simulated**. It
reads real files off the real state volume, runs a real `PRAGMA integrity_check` against real SQLite
databases, asks the real broker-session stores whether their real tokens are still valid, enumerates
the real threads of the running process, and takes real `psutil` process/host measurements.

--------------------------------------------------------------------------------------------------
WHAT IS READ, PER COMPONENT CLASS (research/172 §2 input table)
--------------------------------------------------------------------------------------------------

| Class | Vital signs | How |
|---|---|---|
| `PERSISTENT_STORE` | mtime age, staleness ratio vs the declared budget, byte size, WAL size, `PRAGMA integrity_check` | `pathlib.stat` + a READ-ONLY `sqlite3` connection |
| `PERSISTED_ARTIFACT` | mtime age, staleness ratio, existence, byte size, load-ability | `pathlib.stat` + `json.loads` / `joblib.load` |
| `BROKER_SESSION` | token validity, hours of expiry shortfall | the real `is_still_valid` of the Kite/Breeze stores |
| `BACKGROUND_THREAD` | liveness by thread name, heartbeat age | `threading.enumerate()` + injected heartbeats |
| `HOST_RESOURCE` | process RSS, CPU, open fds, state-volume free space | `psutil` |
| `CADENCE_ENGINE` / `DATA_ADAPTER` / `EXTERNAL_SERVICE` | last-success age, consecutive failures, error rate | injected through the DI seam (they live inside the running service) |

--------------------------------------------------------------------------------------------------
SIGN CONVENTION — HIGHER VALUE ALWAYS MEANS WORSE
--------------------------------------------------------------------------------------------------
`component_health_index` states the convention explicitly: "a collector that naturally produces a
*goodness* signal must invert it before emitting, so that this module never has to guess a signal's
polarity". Every signal below therefore grows as the component degrades. The two natural goodness
signals in the organism are inverted **here**, at the source, and the inversion is documented on the
emitted reading itself (`normalization_note`):

* free disk space  -> emitted as `state_volume_free_gigabytes_shortfall`
                      = `max(0, minimum_required_free_gb - free_gb)`; `0.0` while there is enough room,
                      growing to `minimum_required_free_gb` at a completely full volume.
* time remaining on a broker token -> emitted as `broker_token_expiry_shortfall_hours`
                      = `max(0, renewal_horizon_hours - hours_remaining)`; `0.0` while the token has
                      more than the renewal horizon left, `= renewal_horizon_hours` exactly at the
                      expiry moment, and growing without bound after it has expired.

Both are monotone, both are zero in the healthy region, and neither saturates before the failure point.

--------------------------------------------------------------------------------------------------
RULE O.3 — A BLIND SPOT IS REPORTED, NEVER PAPERED OVER
--------------------------------------------------------------------------------------------------
"A collector that hides a blind spot is worse than one that reports it." Three availability states are
distinguished, because they are three genuinely different epistemic situations and collapsing them
would lose exactly the information that matters:

* `OBSERVED` — the value was read. `severity_oriented_value` is a finite float.
* `UNAVAILABLE` — the value SHOULD have been readable and the read failed (permission denied, the file
  vanished mid-read, `sqlite3` raised, `psutil` raised, the artifact would not deserialize). The reading
  carries `severity_oriented_value=None` and a concrete `unavailable_reason`, and it is emitted into the
  health index as **NaN**, which `component_health_index` charges at its declared
  `unreadable_signal_severity` (0.5 — the DEGRADED tier: a real loss of observability, but not proof of
  failure) and which also **blocks healthy-baseline admission** for that cycle. That is the correct
  treatment for a transient read failure.
* `NOT_INSTRUMENTED` — the organism has **no mechanism at all** to read this. The archetype is
  `session.angel_one`: Kite and Breeze both have `is_still_valid`, Angel One has no store class and no
  expiry check anywhere in the codebase (research/172 §1). Emitting a healthy `token_expired = 0.0` there
  would be a fabricated reading of a session that could have died hours ago. Instead a dedicated
  `observability_gap:*` signal is emitted with value `1.0` — the gap itself is the measurement — carrying
  `OBSERVABILITY_GAP_SIGNAL_WEIGHT = 0.5`, so the component can never read better than DEGRADED while the
  gap exists, yet the gap (a stable, readable fact) does not permanently block the PCA layer from arming
  the way a NaN would.

`OrganismTelemetryCollection.unavailable_readings()` and `.observability_gap_readings()` make both kinds
enumerable, and `TelemetryCollectionDiagnostics` counts them, so nothing is ever merely dropped.

--------------------------------------------------------------------------------------------------
PERSISTENCE
--------------------------------------------------------------------------------------------------
Every reading is appended to `AutopoiesisStateStore.record_telemetry_samples`. SQLite silently converts
a NaN REAL to NULL, which the store's `signal_value REAL NOT NULL` column rejects outright (verified,
2026-07-27) — so an UNAVAILABLE reading is persisted as a companion `unavailable:<signal_name> = 1.0`
row rather than as a fabricated value. The ledger therefore records "this signal could not be read at
time T" as a positive fact, which is what a forensic ledger has to do.

--------------------------------------------------------------------------------------------------
CONSUMERS (Rule G)
--------------------------------------------------------------------------------------------------
`collect_organism_vital_signs()` returns `ComponentTelemetrySample` objects that satisfy
`component_health_index.ComponentTelemetrySample` exactly, so
`ComponentHealthIndexEstimator.ingest(...)` consumes them with no adaptation, and
`telemetry_signal_severity_specs()` hands that estimator the declared healthy/failed anchors for every
signal this collector emits. `homeostatic_setpoint_keeper` consumes the HOST_RESOURCE readings through
`OrganismTelemetryCollection.essential_variable_measurements()`. The MAPE-K binder
(`autopoiesis_orchestrator`) is queued in `docs/BACKLOG.md`.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final, Protocol

from nse_algo_trader.autopoiesis.autopoiesis_state_store import (
    AutopoiesisStateStore,
    PersistedTelemetrySample,
)
from nse_algo_trader.autopoiesis.component_health_index import (
    ComponentTelemetrySample,
    SignalSeveritySpec,
)
from nse_algo_trader.autopoiesis.component_registry import (
    ORGANISM_STATE_DIRECTORY,
    ComponentClass,
    OrganismComponentRegistry,
    RegisteredComponent,
    build_default_component_registry,
)

LOGGER: Final = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------
# Signal names. Every one of them obeys "higher = worse" (module docstring).
# ---------------------------------------------------------------------------------------------------

SIGNAL_FILE_MTIME_AGE_HOURS: Final = "file_mtime_age_hours"
SIGNAL_STALENESS_RATIO: Final = "staleness_ratio_vs_declared_maximum"
SIGNAL_FILE_MISSING: Final = "file_missing"
SIGNAL_FILE_ZERO_BYTES: Final = "file_zero_bytes"
SIGNAL_FILE_SIZE_MEGABYTES: Final = "file_size_megabytes"
SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES: Final = "write_ahead_log_size_megabytes"
SIGNAL_INTEGRITY_CHECK_FAILURE: Final = "sqlite_integrity_check_failure"
SIGNAL_ARTIFACT_LOAD_FAILURE: Final = "artifact_load_failure"
SIGNAL_BROKER_TOKEN_EXPIRED: Final = "broker_token_expired"
SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS: Final = "broker_token_expiry_shortfall_hours"
SIGNAL_THREAD_NOT_ALIVE: Final = "thread_not_alive"
SIGNAL_THREAD_HEARTBEAT_AGE_SECONDS: Final = "thread_heartbeat_age_seconds"
SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES: Final = "process_resident_set_megabytes"
SIGNAL_PROCESS_MEMORY_FRACTION_OF_HOST: Final = "process_memory_fraction_of_host_total"
SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY: Final = "process_cpu_percent_of_total_capacity"
SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT: Final = "open_file_descriptor_count"
SIGNAL_OPEN_FILE_DESCRIPTOR_FRACTION: Final = "open_file_descriptor_fraction_of_limit"
SIGNAL_STATE_VOLUME_USED_FRACTION: Final = "state_volume_used_fraction"
SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES: Final = "state_volume_free_gigabytes_shortfall"
SIGNAL_HOURS_SINCE_LAST_SUCCESS: Final = "hours_since_last_success"
SIGNAL_CONSECUTIVE_FAILURE_COUNT: Final = "consecutive_failure_count"
SIGNAL_ERROR_RATE: Final = "error_rate"

#: Prefix of the signals that measure a KNOWN, STRUCTURAL blind spot (docstring, `NOT_INSTRUMENTED`).
OBSERVABILITY_GAP_SIGNAL_PREFIX: Final = "observability_gap:"
GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK: Final = f"{OBSERVABILITY_GAP_SIGNAL_PREFIX}broker_token_validity_check"
GAP_SIGNAL_THREAD_HEARTBEAT: Final = f"{OBSERVABILITY_GAP_SIGNAL_PREFIX}thread_heartbeat"
GAP_SIGNAL_OPERATIONAL_OBSERVATION: Final = f"{OBSERVABILITY_GAP_SIGNAL_PREFIX}operational_observation"
GAP_SIGNAL_SQLITE_INTEGRITY_CHECK: Final = f"{OBSERVABILITY_GAP_SIGNAL_PREFIX}sqlite_integrity_check"

#: Prefix under which an UNAVAILABLE reading is persisted (SQLite rejects NaN in a NOT NULL REAL column).
UNAVAILABLE_SIGNAL_PERSISTENCE_PREFIX: Final = "unavailable:"

#: A structural blind spot is charged at the DEGRADED tier, matching the health index's own
#: `unreadable_signal_severity = 0.5`: unobservability is a real loss, but it is not proof of failure.
OBSERVABILITY_GAP_SIGNAL_WEIGHT: Final[float] = 0.5

#: `threading.enumerate()` names of the organism's real long-lived threads, keyed by registry id.
#: Verified against `dashboard/live_paper_trading_service.py` (2026-07-27).
PRODUCTION_THREAD_NAME_BY_COMPONENT_ID: Final[Mapping[str, str]] = {
    "thread.live_paper_loop": "live-paper-loop",
    "thread.hi_fidelity_replay_builder": "hi-fidelity-replay-builder",
    "thread.news_acquisition": "news-acquisition-ladder",
    "thread.exchange_filings": "nse-exchange-filings",
    "thread.win_probability_trainer": "win-probability-engine",
}

#: Which HOST_RESOURCE component owns which host signal — one registry component per resource.
_HOST_RESOURCE_SIGNAL_NAMES_BY_COMPONENT_ID: Final[Mapping[str, tuple[str, ...]]] = {
    "host.process_memory": (
        SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES,
        SIGNAL_PROCESS_MEMORY_FRACTION_OF_HOST,
    ),
    "host.process_cpu": (SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,),
    "host.open_file_descriptors": (
        SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT,
        SIGNAL_OPEN_FILE_DESCRIPTOR_FRACTION,
    ),
    "host.disk_free": (
        SIGNAL_STATE_VOLUME_USED_FRACTION,
        SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES,
    ),
}

_BYTES_PER_MEGABYTE: Final[float] = 1024.0 * 1024.0
_BYTES_PER_GIGABYTE: Final[float] = 1024.0 * 1024.0 * 1024.0
_SECONDS_PER_HOUR: Final[float] = 3600.0


class VitalSignAvailability(str, Enum):
    """Why a reading holds the value it holds — the three epistemic states of the module docstring."""

    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    NOT_INSTRUMENTED = "not_instrumented"


@dataclass(frozen=True)
class VitalSignReading:
    """One vital sign of one component at one instant, with its provenance attached.

    `severity_oriented_value` always follows "higher = worse" and is `None` **iff** the availability is
    `UNAVAILABLE`. `raw_observation` is the human-readable form kept for the Rule-F by-eye pass — the
    number alone rarely tells an operator what it means ("2.51" vs "61.3 h old, budget 24.0 h").
    """

    component_id: str
    signal_name: str
    observed_at: datetime
    availability: VitalSignAvailability
    severity_oriented_value: float | None
    measurement_unit: str
    normalization_note: str
    raw_observation: str = ""
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("VitalSignReading.component_id must be a non-empty identifier")
        if not self.signal_name:
            raise ValueError(f"VitalSignReading.signal_name must be non-empty for {self.component_id}")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError(
                f"VitalSignReading.observed_at must be timezone-aware (UTC-explicit); got "
                f"{self.observed_at!r} for {self.component_id}/{self.signal_name}"
            )
        if self.availability is VitalSignAvailability.UNAVAILABLE:
            if self.severity_oriented_value is not None:
                raise ValueError(
                    f"{self.component_id}/{self.signal_name}: an UNAVAILABLE reading must not carry a "
                    f"value — that is exactly the fabrication Rule O.3 forbids"
                )
            if not self.unavailable_reason:
                raise ValueError(
                    f"{self.component_id}/{self.signal_name}: an UNAVAILABLE reading must state WHY "
                    f"it could not be read"
                )
        else:
            if self.severity_oriented_value is None:
                raise ValueError(
                    f"{self.component_id}/{self.signal_name}: only an UNAVAILABLE reading may omit "
                    f"its value"
                )
            if not math.isfinite(self.severity_oriented_value):
                raise ValueError(
                    f"{self.component_id}/{self.signal_name}: a non-finite value is not an observation "
                    f"— report it as UNAVAILABLE with a reason instead"
                )

    @property
    def is_observed(self) -> bool:
        return self.availability is VitalSignAvailability.OBSERVED

    @property
    def is_observability_gap(self) -> bool:
        return self.availability is VitalSignAvailability.NOT_INSTRUMENTED

    @property
    def health_index_signal_value(self) -> float:
        """The float handed to `component_health_index`; NaN for UNAVAILABLE (charged, never ignored)."""
        return math.nan if self.severity_oriented_value is None else self.severity_oriented_value

    def describe(self) -> str:
        """One line, formatted for the Rule-F by-eye inspection."""
        if self.availability is VitalSignAvailability.UNAVAILABLE:
            body = f"UNAVAILABLE ({self.unavailable_reason})"
        elif self.availability is VitalSignAvailability.NOT_INSTRUMENTED:
            body = f"NOT INSTRUMENTED ({self.unavailable_reason or self.raw_observation})"
        else:
            body = f"{self.severity_oriented_value:.6g} {self.measurement_unit}"
            if self.raw_observation:
                body = f"{body}  [{self.raw_observation}]"
        return f"{self.component_id:38s} {self.signal_name:44s} {body}"


@dataclass(frozen=True)
class TelemetryCollectionCalibration:
    """Every tunable of the raw-input pipeline, in one auditable frozen object.

    The two integrity-check knobs are the ones with a real operational cost: `PRAGMA integrity_check`
    on the organism's 202 MiB `market_data.sqlite3` takes ~21 s (measured on this box, 2026-07-27), so
    it is CADENCED (default: at most once per 24 h per file, verdict cached) rather than run per cycle.
    `maximum_inline_integrity_check_bytes=None` in production means "no size ceiling — check everything
    on its cadence"; setting a ceiling makes oversized files report an explicit
    `observability_gap:sqlite_integrity_check` rather than a fabricated "ok".
    """

    integrity_check_interval_hours: float = 24.0
    maximum_inline_integrity_check_bytes: int | None = None
    perform_sqlite_integrity_checks: bool = True
    verify_artifact_loadability: bool = True
    #: `psutil.Process.cpu_percent(interval=None)` returns 0.0 on its first ever call (no prior sample to
    #: difference against), which would be a fabricated healthy reading. A short blocking interval makes
    #: the very first collection a real measurement.
    cpu_sample_interval_seconds: float = 0.1
    minimum_state_volume_free_gigabytes: float = 5.0
    #: A token with less than this left is already a problem: the organism cannot renew it itself.
    broker_token_renewal_horizon_hours: float = 2.0
    #: Used when a component declares no `maximum_staleness_hours` but does declare a `state_path`.
    default_maximum_staleness_hours: float = 24.0
    cadence_last_success_nominal_hours: float = 2.0
    cadence_last_success_alarm_hours: float = 24.0
    consecutive_failure_alarm_count: float = 5.0
    error_rate_nominal: float = 0.05
    error_rate_alarm: float = 0.50
    thread_heartbeat_nominal_age_seconds: float = 60.0
    thread_heartbeat_alarm_age_seconds: float = 600.0
    #: Staleness ramp: `0.0` severity at exactly the declared budget, fully failed at twice the budget.
    #: (`market_data.sqlite3` at 60.3 h against a 24 h budget = ratio 2.51 -> severity 1.0 -> FAILED.)
    staleness_ratio_nominal: float = 1.0
    staleness_ratio_alarm: float = 2.0
    write_ahead_log_nominal_megabytes: float = 64.0
    write_ahead_log_alarm_megabytes: float = 512.0
    process_memory_fraction_nominal: float = 0.25
    process_memory_fraction_alarm: float = 0.80
    process_cpu_percent_nominal: float = 50.0
    process_cpu_percent_alarm: float = 95.0
    open_file_descriptor_fraction_nominal: float = 0.50
    open_file_descriptor_fraction_alarm: float = 0.95
    state_volume_used_fraction_nominal: float = 0.85
    state_volume_used_fraction_alarm: float = 0.98

    def __post_init__(self) -> None:
        if self.integrity_check_interval_hours < 0.0:
            raise ValueError("integrity_check_interval_hours must be non-negative")
        if (
            self.maximum_inline_integrity_check_bytes is not None
            and self.maximum_inline_integrity_check_bytes <= 0
        ):
            raise ValueError("maximum_inline_integrity_check_bytes must be positive when set")
        if self.cpu_sample_interval_seconds < 0.0:
            raise ValueError("cpu_sample_interval_seconds must be non-negative")
        if self.minimum_state_volume_free_gigabytes <= 0.0:
            raise ValueError("minimum_state_volume_free_gigabytes must be positive (it is the ramp span)")
        if self.broker_token_renewal_horizon_hours <= 0.0:
            raise ValueError("broker_token_renewal_horizon_hours must be positive (it is the ramp span)")
        if self.default_maximum_staleness_hours <= 0.0:
            raise ValueError("default_maximum_staleness_hours must be positive")


def telemetry_signal_severity_specs(
    calibration: TelemetryCollectionCalibration | None = None,
) -> tuple[SignalSeveritySpec, ...]:
    """The declared healthy/failed anchors for every signal this collector emits.

    This is the collector's half of the contract with `component_health_index`: the collector knows what
    each of its signals MEANS, so it — not the health index — declares where "healthy" ends and "failed"
    begins. Signals deliberately left undeclared (`file_size_megabytes`, `open_file_descriptor_count`)
    have no universal anchor; the health index derives a robust ramp for them from the component's own
    healthy baseline once it has `minimum_samples_for_robust_signal_threshold` samples, and abstains
    honestly until then.
    """
    settings = calibration if calibration is not None else TelemetryCollectionCalibration()
    binary_signals = (
        SIGNAL_FILE_MISSING,
        SIGNAL_FILE_ZERO_BYTES,
        SIGNAL_INTEGRITY_CHECK_FAILURE,
        SIGNAL_ARTIFACT_LOAD_FAILURE,
        SIGNAL_BROKER_TOKEN_EXPIRED,
        SIGNAL_THREAD_NOT_ALIVE,
    )
    gap_signals = (
        GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK,
        GAP_SIGNAL_THREAD_HEARTBEAT,
        GAP_SIGNAL_OPERATIONAL_OBSERVATION,
        GAP_SIGNAL_SQLITE_INTEGRITY_CHECK,
    )
    specs: list[SignalSeveritySpec] = [
        SignalSeveritySpec(name, 0.0, 1.0) for name in binary_signals
    ]
    specs.extend(
        SignalSeveritySpec(name, 0.0, 1.0, weight=OBSERVABILITY_GAP_SIGNAL_WEIGHT)
        for name in gap_signals
    )
    specs.extend(
        (
            SignalSeveritySpec(
                SIGNAL_STALENESS_RATIO, settings.staleness_ratio_nominal, settings.staleness_ratio_alarm
            ),
            SignalSeveritySpec(
                SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES,
                settings.write_ahead_log_nominal_megabytes,
                settings.write_ahead_log_alarm_megabytes,
            ),
            SignalSeveritySpec(
                SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS,
                0.0,
                settings.broker_token_renewal_horizon_hours,
            ),
            SignalSeveritySpec(
                SIGNAL_THREAD_HEARTBEAT_AGE_SECONDS,
                settings.thread_heartbeat_nominal_age_seconds,
                settings.thread_heartbeat_alarm_age_seconds,
            ),
            SignalSeveritySpec(
                SIGNAL_PROCESS_MEMORY_FRACTION_OF_HOST,
                settings.process_memory_fraction_nominal,
                settings.process_memory_fraction_alarm,
            ),
            SignalSeveritySpec(
                SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,
                settings.process_cpu_percent_nominal,
                settings.process_cpu_percent_alarm,
            ),
            SignalSeveritySpec(
                SIGNAL_OPEN_FILE_DESCRIPTOR_FRACTION,
                settings.open_file_descriptor_fraction_nominal,
                settings.open_file_descriptor_fraction_alarm,
            ),
            SignalSeveritySpec(
                SIGNAL_STATE_VOLUME_USED_FRACTION,
                settings.state_volume_used_fraction_nominal,
                settings.state_volume_used_fraction_alarm,
            ),
            SignalSeveritySpec(
                SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES,
                0.0,
                settings.minimum_state_volume_free_gigabytes,
            ),
            SignalSeveritySpec(
                SIGNAL_HOURS_SINCE_LAST_SUCCESS,
                settings.cadence_last_success_nominal_hours,
                settings.cadence_last_success_alarm_hours,
            ),
            SignalSeveritySpec(
                SIGNAL_CONSECUTIVE_FAILURE_COUNT, 0.0, settings.consecutive_failure_alarm_count
            ),
            SignalSeveritySpec(SIGNAL_ERROR_RATE, settings.error_rate_nominal, settings.error_rate_alarm),
        )
    )
    return tuple(specs)


# ---------------------------------------------------------------------------------------------------
# DI seams. Production implementations read the real organism; tests inject fakes that live only under
# `tests/` (Rule J), which is how "psutil raises" and "the disk is full" become deterministic.
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HostResourceSnapshot:
    """One `psutil` sweep. A `None` field means that field could not be read; the reason is in the map.

    Fields are kept individually optional (rather than the whole snapshot failing) because `psutil`
    fails per-metric: `num_fds()` is unavailable on some platforms while `memory_info()` works fine, and
    losing the readable metrics because an unreadable one shares the sweep would be self-inflicted
    blindness.
    """

    process_resident_set_bytes: float | None = None
    host_total_memory_bytes: float | None = None
    process_cpu_percent_of_total_capacity: float | None = None
    open_file_descriptor_count: float | None = None
    open_file_descriptor_limit: float | None = None
    state_volume_total_bytes: float | None = None
    state_volume_free_bytes: float | None = None
    unavailable_reason_by_field: Mapping[str, str] = field(default_factory=dict)

    def reason_for(self, field_name: str) -> str:
        return self.unavailable_reason_by_field.get(field_name, "psutil did not supply this metric")


class HostResourceProbe(Protocol):
    """The `psutil` seam (research/172 §2 "Process/host" row)."""

    def read_host_resource_snapshot(self, state_volume_path: Path) -> HostResourceSnapshot: ...


class PsutilHostResourceProbe:
    """The REAL host probe — `psutil` against this very process and the real state volume.

    Every metric is read inside its own guard so one failing metric cannot blank the sweep, and every
    failure is recorded with its exception text rather than being swallowed (Rule O.3).
    """

    def __init__(self, cpu_sample_interval_seconds: float = 0.1) -> None:
        if cpu_sample_interval_seconds < 0.0:
            raise ValueError("cpu_sample_interval_seconds must be non-negative")
        self._cpu_sample_interval_seconds = cpu_sample_interval_seconds

    def read_host_resource_snapshot(self, state_volume_path: Path) -> HostResourceSnapshot:
        import psutil

        reasons: dict[str, str] = {}
        process: Any | None = None
        try:
            process = psutil.Process()
        except Exception as failure:  # noqa: BLE001 - the reason is surfaced, never swallowed
            reasons["process"] = f"psutil.Process() failed: {failure!r}"

        resident_set_bytes = self._read_metric(
            reasons, "process_resident_set_bytes",
            lambda: float(process.memory_info().rss) if process is not None else None,
        )
        total_memory_bytes = self._read_metric(
            reasons, "host_total_memory_bytes", lambda: float(psutil.virtual_memory().total)
        )
        cpu_percent = self._read_metric(
            reasons, "process_cpu_percent_of_total_capacity",
            lambda: self._process_cpu_percent_of_total_capacity(psutil, process),
        )
        descriptor_count = self._read_metric(
            reasons, "open_file_descriptor_count",
            lambda: float(process.num_fds()) if process is not None else None,
        )
        descriptor_limit = self._read_metric(
            reasons, "open_file_descriptor_limit", self._open_file_descriptor_limit
        )
        disk_total = self._read_metric(
            reasons, "state_volume_total_bytes",
            lambda: float(psutil.disk_usage(str(state_volume_path)).total),
        )
        disk_free = self._read_metric(
            reasons, "state_volume_free_bytes",
            lambda: float(psutil.disk_usage(str(state_volume_path)).free),
        )
        return HostResourceSnapshot(
            process_resident_set_bytes=resident_set_bytes,
            host_total_memory_bytes=total_memory_bytes,
            process_cpu_percent_of_total_capacity=cpu_percent,
            open_file_descriptor_count=descriptor_count,
            open_file_descriptor_limit=descriptor_limit,
            state_volume_total_bytes=disk_total,
            state_volume_free_bytes=disk_free,
            unavailable_reason_by_field=reasons,
        )

    def _process_cpu_percent_of_total_capacity(
        self, psutil_module: Any, process: Any | None
    ) -> float | None:
        """Per-core-normalised CPU so the signal means the same thing on a 2-core and a 64-core box.

        `Process.cpu_percent()` returns up to `100 * core_count`; dividing by the core count puts it back
        in `[0, 100]` = "percent of the machine's total compute", which is what a setpoint on CPU means.
        """
        if process is None:
            return None
        raw_percent = float(process.cpu_percent(interval=self._cpu_sample_interval_seconds or None))
        core_count = psutil_module.cpu_count(logical=True) or 1
        return raw_percent / float(max(int(core_count), 1))

    @staticmethod
    def _open_file_descriptor_limit() -> float | None:
        import resource

        soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        return None if soft_limit <= 0 else float(soft_limit)

    @staticmethod
    def _read_metric(
        reasons: dict[str, str], field_name: str, read: Callable[[], float | None]
    ) -> float | None:
        try:
            value = read()
        except Exception as failure:  # noqa: BLE001 - psutil raises many platform-specific types
            reasons[field_name] = f"{type(failure).__name__}: {failure}"
            return None
        if value is None:
            reasons.setdefault(field_name, "the underlying probe returned no value")
            return None
        if not math.isfinite(value):
            reasons[field_name] = f"probe returned a non-finite value ({value!r})"
            return None
        return float(value)


@dataclass(frozen=True)
class BrokerSessionValidityReading:
    """What the organism can (or cannot) say about one broker session's token, right now.

    `has_validity_check=False` is the `session.angel_one` case and is a first-class outcome, not an
    error: Kite and Breeze own `is_still_valid`, Angel One has no store class at all (research/172 §1).
    """

    component_id: str
    has_validity_check: bool
    is_still_valid: bool | None = None
    expires_at: datetime | None = None
    unavailable_reason: str = ""
    detail: str = ""


class BrokerSessionValidityProbe(Protocol):
    """The broker-session seam (research/172 §2 "Broker sessions" row)."""

    def read_broker_session_validity(
        self, component: RegisteredComponent, now: datetime
    ) -> BrokerSessionValidityReading: ...


class RealBrokerSessionValidityProbe:
    """Asks the REAL token stores. Never logs, returns or otherwise leaks a token value.

    Kite and Breeze both persist `generated_at` and derive `expires_at` from the broker's real expiry
    rule (Kite: 06:00 IST the next morning; Breeze: `min(next IST midnight, +24 h)`), so both a boolean
    validity and an exact expiry moment are genuinely available. Angel One has neither a store class nor
    an expiry check anywhere in the codebase, so this probe says so explicitly instead of guessing.
    """

    ANGEL_ONE_MISSING_CHECK_REASON: Final = (
        "no validity check available: session.angel_one has no token store and no is_still_valid() "
        "anywhere in the codebase (Kite and Breeze both have one) — the jwtToken hard-expires unobserved"
    )

    def read_broker_session_validity(
        self, component: RegisteredComponent, now: datetime
    ) -> BrokerSessionValidityReading:
        if component.component_id == "session.kite":
            return self._read_kite_session_validity(component, now)
        if component.component_id == "session.breeze":
            return self._read_breeze_session_validity(component, now)
        if component.component_id == "session.angel_one":
            return BrokerSessionValidityReading(
                component_id=component.component_id,
                has_validity_check=False,
                unavailable_reason=self.ANGEL_ONE_MISSING_CHECK_REASON,
            )
        return BrokerSessionValidityReading(
            component_id=component.component_id,
            has_validity_check=False,
            unavailable_reason=(
                f"no validity check available: {component.component_id} is registered as a "
                f"BROKER_SESSION but this probe knows no expiry rule for it"
            ),
        )

    def _read_kite_session_validity(
        self, component: RegisteredComponent, now: datetime
    ) -> BrokerSessionValidityReading:
        from nse_algo_trader.broker_sessions.kite_access_token_store import KiteAccessTokenFileStore

        def load_record():
            store = (
                KiteAccessTokenFileStore(component.state_path)
                if component.state_path is not None
                else KiteAccessTokenFileStore()
            )
            return store.load()

        return self._validity_from_token_record(component, now, load_record, "Kite access token")

    def _read_breeze_session_validity(
        self, component: RegisteredComponent, now: datetime
    ) -> BrokerSessionValidityReading:
        from nse_algo_trader.broker_sessions.breeze_session_token_store import (
            BreezeSessionTokenFileStore,
        )

        def load_record():
            store = (
                BreezeSessionTokenFileStore(component.state_path)
                if component.state_path is not None
                else BreezeSessionTokenFileStore()
            )
            return store.load()

        return self._validity_from_token_record(component, now, load_record, "Breeze session token")

    def _validity_from_token_record(
        self, component: RegisteredComponent, now: datetime,
        load_record: Callable[[], Any], label: str,
    ) -> BrokerSessionValidityReading:
        try:
            record = load_record()
        except (OSError, ValueError, KeyError, TypeError) as failure:
            return BrokerSessionValidityReading(
                component_id=component.component_id,
                has_validity_check=True,
                unavailable_reason=f"{label} could not be read: {type(failure).__name__}: {failure}",
            )
        if record is None:
            # An absent token is a genuine, unambiguous observation: there is no session at all.
            return BrokerSessionValidityReading(
                component_id=component.component_id,
                has_validity_check=True,
                is_still_valid=False,
                expires_at=None,
                detail=f"{label} has never been saved (no token file) — the session does not exist",
            )
        try:
            expires_at = record.expires_at()
            is_valid = bool(record.is_still_valid(now))
        except (ValueError, TypeError, OverflowError) as failure:
            return BrokerSessionValidityReading(
                component_id=component.component_id,
                has_validity_check=True,
                unavailable_reason=(
                    f"{label} expiry could not be computed: {type(failure).__name__}: {failure}"
                ),
            )
        return BrokerSessionValidityReading(
            component_id=component.component_id,
            has_validity_check=True,
            is_still_valid=is_valid,
            expires_at=expires_at,
            detail=f"{label} expires {expires_at.isoformat()}",
        )


class RunningThreadNameReader(Protocol):
    """The `threading.enumerate()` seam (research/172 §2 "Threads" row)."""

    def read_running_thread_names(self) -> frozenset[str]: ...


class LiveProcessThreadNameReader:
    """The REAL reader: the names of every thread alive in this process right now."""

    def read_running_thread_names(self) -> frozenset[str]:
        return frozenset(thread.name for thread in threading.enumerate() if thread.is_alive())


@dataclass(frozen=True)
class InjectedComponentObservation:
    """Operational facts only the running service can know, handed in through the DI seam.

    Cadence engines, data adapters and the LLM provider pool live INSIDE the process that runs the
    homeostat; their last-success time and failure counters are held by the orchestrator, not on disk.
    Rather than have the collector reach into the service (which would invert the dependency and make it
    untestable), the service passes these in. A component for which nothing is passed reports an
    explicit `observability_gap:operational_observation` — never a healthy default.
    """

    component_id: str
    last_success_at: datetime | None = None
    consecutive_failure_count: int | None = None
    error_rate: float | None = None
    last_heartbeat_at: datetime | None = None
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("InjectedComponentObservation.component_id must be a non-empty identifier")
        for field_name in ("last_success_at", "last_heartbeat_at"):
            moment = getattr(self, field_name)
            if moment is not None and (moment.tzinfo is None or moment.utcoffset() is None):
                raise ValueError(
                    f"InjectedComponentObservation.{field_name} must be timezone-aware (UTC-explicit); "
                    f"got {moment!r} for {self.component_id}"
                )
        if self.consecutive_failure_count is not None and self.consecutive_failure_count < 0:
            raise ValueError(
                f"consecutive_failure_count cannot be negative for {self.component_id}: "
                f"{self.consecutive_failure_count}"
            )
        if self.error_rate is not None and not (
            math.isfinite(self.error_rate) and 0.0 <= self.error_rate <= 1.0
        ):
            raise ValueError(
                f"error_rate must be a finite fraction in [0, 1] for {self.component_id}: "
                f"{self.error_rate!r}"
            )

    @property
    def carries_any_observation(self) -> bool:
        return any(
            value is not None
            for value in (
                self.last_success_at,
                self.consecutive_failure_count,
                self.error_rate,
                self.last_heartbeat_at,
            )
        )


@dataclass(frozen=True)
class TelemetryCollectionDiagnostics:
    """What the sweep could and could not see — Rule O.3's "count and surface", made a return value."""

    component_count: int = 0
    reading_count: int = 0
    observed_reading_count: int = 0
    unavailable_reading_count: int = 0
    observability_gap_reading_count: int = 0
    persisted_sample_row_count: int = 0
    persistence_failure_reason: str = ""
    integrity_check_performed_count: int = 0
    integrity_check_skipped_count: int = 0
    unrecognized_injected_observation_ids: tuple[str, ...] = ()

    @property
    def observability_fraction(self) -> float:
        """Share of vital signs actually observed this sweep. `1.0` = the organism is fully visible."""
        if self.reading_count <= 0:
            return 1.0
        return self.observed_reading_count / float(self.reading_count)


@dataclass(frozen=True)
class OrganismTelemetryCollection:
    """One complete sweep of the organism's vital signs — the Monitor phase's output."""

    collected_at: datetime
    samples: tuple[ComponentTelemetrySample, ...]
    readings: tuple[VitalSignReading, ...]
    diagnostics: TelemetryCollectionDiagnostics

    def readings_for(self, component_id: str) -> tuple[VitalSignReading, ...]:
        return tuple(reading for reading in self.readings if reading.component_id == component_id)

    def reading_for(self, component_id: str, signal_name: str) -> VitalSignReading | None:
        for reading in self.readings:
            if reading.component_id == component_id and reading.signal_name == signal_name:
                return reading
        return None

    def sample_for(self, component_id: str) -> ComponentTelemetrySample | None:
        for sample in self.samples:
            if sample.component_id == component_id:
                return sample
        return None

    def unavailable_readings(self) -> tuple[VitalSignReading, ...]:
        return tuple(
            reading
            for reading in self.readings
            if reading.availability is VitalSignAvailability.UNAVAILABLE
        )

    def observability_gap_readings(self) -> tuple[VitalSignReading, ...]:
        return tuple(reading for reading in self.readings if reading.is_observability_gap)

    def essential_variable_measurements(self) -> dict[str, float]:
        """The HOST_RESOURCE readings, keyed for `homeostatic_setpoint_keeper` (Rule G wiring).

        Only OBSERVED readings are handed over: an unmeasured essential variable must reach the keeper as
        *absent* so the keeper can refuse to relax while blind, never as a plausible-looking number.
        """
        wanted = {
            SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES,
            SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,
            SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT,
            SIGNAL_STATE_VOLUME_USED_FRACTION,
        }
        return {
            reading.signal_name: float(reading.severity_oriented_value)
            for reading in self.readings
            if reading.signal_name in wanted
            and reading.is_observed
            and reading.severity_oriented_value is not None
        }

    def describe_readings(self) -> str:
        """Every reading, one per line — the Rule-F by-eye inspection surface."""
        return "\n".join(reading.describe() for reading in self.readings)


class ComponentTelemetryCollector:
    """Reads the organism's vital signs from the organism, persists them, and returns them.

    Named `collector`, not `engine`, deliberately: research/172 §5.7 reserves "engine" for parts that
    carry a real solver. This part only observes — the solving happens in `component_health_index`,
    `component_failure_hazard_model` and `maintenance_policy_solver` downstream.

    The only carried state is the cadenced SQLite integrity-check cache (path -> verdict + check time),
    which exists because a full `PRAGMA integrity_check` of a 202 MiB store costs ~21 s and must not run
    on every scan cycle.
    """

    def __init__(
        self,
        registry: OrganismComponentRegistry | None = None,
        state_store: AutopoiesisStateStore | None = None,
        calibration: TelemetryCollectionCalibration | None = None,
        host_resource_probe: HostResourceProbe | None = None,
        broker_session_validity_probe: BrokerSessionValidityProbe | None = None,
        running_thread_name_reader: RunningThreadNameReader | None = None,
        thread_name_by_component_id: Mapping[str, str] | None = None,
        state_volume_path: Path = ORGANISM_STATE_DIRECTORY,
    ) -> None:
        self._registry = registry if registry is not None else build_default_component_registry()
        self._state_store = state_store
        self._calibration = calibration if calibration is not None else TelemetryCollectionCalibration()
        self._host_resource_probe: HostResourceProbe = (
            host_resource_probe
            if host_resource_probe is not None
            else PsutilHostResourceProbe(self._calibration.cpu_sample_interval_seconds)
        )
        self._broker_session_validity_probe: BrokerSessionValidityProbe = (
            broker_session_validity_probe
            if broker_session_validity_probe is not None
            else RealBrokerSessionValidityProbe()
        )
        self._running_thread_name_reader: RunningThreadNameReader = (
            running_thread_name_reader
            if running_thread_name_reader is not None
            else LiveProcessThreadNameReader()
        )
        self._thread_name_by_component_id = dict(
            thread_name_by_component_id
            if thread_name_by_component_id is not None
            else PRODUCTION_THREAD_NAME_BY_COMPONENT_ID
        )
        self._state_volume_path = state_volume_path
        self._integrity_verdict_by_path: dict[Path, tuple[datetime, bool, str]] = {}

    @property
    def signal_severity_specs(self) -> tuple[SignalSeveritySpec, ...]:
        """Handed straight to `ComponentHealthIndexEstimator(signal_severity_specs=...)`."""
        return telemetry_signal_severity_specs(self._calibration)

    # -- the sweep ---------------------------------------------------------------------------------

    def collect_organism_vital_signs(
        self,
        now: datetime | None = None,
        injected_observations: Iterable[InjectedComponentObservation] = (),
    ) -> OrganismTelemetryCollection:
        """Read every vital sign of every SELF component, persist them, and return them."""
        moment = _require_utc_moment(now) if now is not None else datetime.now(UTC)
        observation_by_component_id, unrecognized_ids = self._index_injected_observations(
            injected_observations
        )
        self_components = self._registry.self_components()

        host_snapshot = (
            self._read_host_resource_snapshot_guarded()
            if any(c.component_class is ComponentClass.HOST_RESOURCE for c in self_components)
            else HostResourceSnapshot()
        )
        running_thread_names, thread_enumeration_failure = (
            self._read_running_thread_names_guarded()
            if any(c.component_class is ComponentClass.BACKGROUND_THREAD for c in self_components)
            else (frozenset[str](), "")
        )

        readings: list[VitalSignReading] = []
        integrity_performed = 0
        integrity_skipped = 0
        for component in self_components:
            component_readings, performed, skipped = self._readings_for_component(
                component,
                moment,
                host_snapshot,
                running_thread_names,
                thread_enumeration_failure,
                observation_by_component_id.get(component.component_id),
            )
            readings.extend(component_readings)
            integrity_performed += performed
            integrity_skipped += skipped

        samples = self._build_telemetry_samples(readings, moment, self_components)
        persisted_row_count, persistence_failure_reason = self._persist_readings(readings)
        diagnostics = TelemetryCollectionDiagnostics(
            component_count=len(self_components),
            reading_count=len(readings),
            observed_reading_count=sum(1 for r in readings if r.is_observed),
            unavailable_reading_count=sum(
                1 for r in readings if r.availability is VitalSignAvailability.UNAVAILABLE
            ),
            observability_gap_reading_count=sum(1 for r in readings if r.is_observability_gap),
            persisted_sample_row_count=persisted_row_count,
            persistence_failure_reason=persistence_failure_reason,
            integrity_check_performed_count=integrity_performed,
            integrity_check_skipped_count=integrity_skipped,
            unrecognized_injected_observation_ids=unrecognized_ids,
        )
        if diagnostics.unavailable_reading_count or diagnostics.observability_gap_reading_count:
            LOGGER.info(
                "telemetry sweep: %d/%d vital signs observed, %d unavailable, %d structural blind spots",
                diagnostics.observed_reading_count, diagnostics.reading_count,
                diagnostics.unavailable_reading_count, diagnostics.observability_gap_reading_count,
            )
        return OrganismTelemetryCollection(
            collected_at=moment,
            samples=tuple(samples),
            readings=tuple(readings),
            diagnostics=diagnostics,
        )

    # -- per-class readers -------------------------------------------------------------------------

    def _readings_for_component(
        self,
        component: RegisteredComponent,
        moment: datetime,
        host_snapshot: HostResourceSnapshot,
        running_thread_names: frozenset[str],
        thread_enumeration_failure: str,
        observation: InjectedComponentObservation | None,
    ) -> tuple[list[VitalSignReading], int, int]:
        if component.component_class is ComponentClass.PERSISTENT_STORE:
            return self._persistent_store_readings(component, moment)
        if component.component_class is ComponentClass.PERSISTED_ARTIFACT:
            return self._persisted_artifact_readings(component, moment), 0, 0
        if component.component_class is ComponentClass.BROKER_SESSION:
            return self._broker_session_readings(component, moment), 0, 0
        if component.component_class is ComponentClass.BACKGROUND_THREAD:
            return (
                self._background_thread_readings(
                    component, moment, running_thread_names, thread_enumeration_failure, observation
                ),
                0,
                0,
            )
        if component.component_class is ComponentClass.HOST_RESOURCE:
            return self._host_resource_readings(component, moment, host_snapshot), 0, 0
        return self._injected_operational_readings(component, moment, observation), 0, 0

    def _persistent_store_readings(
        self, component: RegisteredComponent, moment: datetime
    ) -> tuple[list[VitalSignReading], int, int]:
        readings, stat_result = self._file_state_readings(component, moment)
        database_path = component.state_path
        if database_path is None:
            return readings, 0, 0
        readings.append(self._write_ahead_log_reading(component, moment, database_path))
        integrity_reading, performed, skipped = self._sqlite_integrity_reading(
            component, moment, database_path, stat_result.st_size if stat_result is not None else None
        )
        readings.append(integrity_reading)
        return readings, performed, skipped

    def _persisted_artifact_readings(
        self, component: RegisteredComponent, moment: datetime
    ) -> list[VitalSignReading]:
        readings, stat_result = self._file_state_readings(component, moment)
        artifact_path = component.state_path
        if artifact_path is None:
            return readings
        if not self._calibration.verify_artifact_loadability:
            readings.append(
                _gap_reading(
                    component.component_id, SIGNAL_ARTIFACT_LOAD_FAILURE, moment,
                    reason="artifact load verification is disabled by configuration",
                )
            )
            return readings
        if stat_result is None:
            readings.append(
                _unavailable_reading(
                    component.component_id, SIGNAL_ARTIFACT_LOAD_FAILURE, moment,
                    reason=f"cannot attempt a load: {artifact_path} could not be stat-ed or is absent",
                )
            )
            return readings
        readings.append(self._artifact_load_reading(component, moment, artifact_path))
        return readings

    def _broker_session_readings(
        self, component: RegisteredComponent, moment: datetime
    ) -> list[VitalSignReading]:
        try:
            validity = self._broker_session_validity_probe.read_broker_session_validity(component, moment)
        except Exception as failure:  # noqa: BLE001 - a probe blowing up is itself a blind spot
            reason = f"broker-session probe raised {type(failure).__name__}: {failure}"
            LOGGER.warning("%s: %s", component.component_id, reason)
            return [
                _unavailable_reading(component.component_id, SIGNAL_BROKER_TOKEN_EXPIRED, moment, reason),
                _unavailable_reading(
                    component.component_id, SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS, moment, reason
                ),
            ]

        if not validity.has_validity_check:
            # THE `session.angel_one` CASE. A healthy-looking `broker_token_expired = 0.0` here would be
            # a fabricated reading of a session that may have died hours ago (research/172 §1).
            return [
                _gap_reading(
                    component.component_id, GAP_SIGNAL_BROKER_TOKEN_VALIDITY_CHECK, moment,
                    reason=validity.unavailable_reason or "no validity check available for this session",
                )
            ]
        if validity.unavailable_reason:
            return [
                _unavailable_reading(
                    component.component_id, SIGNAL_BROKER_TOKEN_EXPIRED, moment,
                    validity.unavailable_reason,
                ),
                _unavailable_reading(
                    component.component_id, SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS, moment,
                    validity.unavailable_reason,
                ),
            ]

        is_valid = bool(validity.is_still_valid)
        readings = [
            VitalSignReading(
                component_id=component.component_id,
                signal_name=SIGNAL_BROKER_TOKEN_EXPIRED,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=0.0 if is_valid else 1.0,
                measurement_unit="indicator",
                normalization_note="1.0 = the token is expired or absent; 0.0 = still valid",
                raw_observation=validity.detail or ("valid" if is_valid else "EXPIRED"),
            )
        ]
        horizon_hours = self._calibration.broker_token_renewal_horizon_hours
        if validity.expires_at is None:
            # No token at all: the shortfall is unbounded in principle. Report the failed end of the ramp,
            # which is a true statement ("there is no time left on a session that does not exist").
            shortfall_hours = horizon_hours
            raw = "no token file — treated as fully expired"
        else:
            hours_remaining = (validity.expires_at - moment).total_seconds() / _SECONDS_PER_HOUR
            shortfall_hours = max(0.0, horizon_hours - hours_remaining)
            raw = (
                f"{hours_remaining:+.2f} h remaining, expires {validity.expires_at.isoformat()}, "
                f"renewal horizon {horizon_hours:.1f} h"
            )
        readings.append(
            VitalSignReading(
                component_id=component.component_id,
                signal_name=SIGNAL_BROKER_TOKEN_EXPIRY_SHORTFALL_HOURS,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=shortfall_hours,
                measurement_unit="hours",
                normalization_note=(
                    "INVERTED goodness signal: max(0, renewal_horizon_hours - hours_remaining). "
                    "0.0 while comfortably valid, = renewal_horizon_hours at the expiry moment, "
                    "growing without bound afterwards"
                ),
                raw_observation=raw,
            )
        )
        return readings

    def _background_thread_readings(
        self,
        component: RegisteredComponent,
        moment: datetime,
        running_thread_names: frozenset[str],
        thread_enumeration_failure: str,
        observation: InjectedComponentObservation | None,
    ) -> list[VitalSignReading]:
        thread_name = self._thread_name_by_component_id.get(component.component_id)
        if thread_name is None:
            readings = [
                _gap_reading(
                    component.component_id, SIGNAL_THREAD_NOT_ALIVE, moment,
                    reason=(
                        f"no runtime thread name is declared for {component.component_id}, so "
                        f"threading.enumerate() cannot be matched against it"
                    ),
                )
            ]
        elif thread_enumeration_failure:
            readings = [
                _unavailable_reading(
                    component.component_id, SIGNAL_THREAD_NOT_ALIVE, moment, thread_enumeration_failure
                )
            ]
        else:
            is_alive = thread_name in running_thread_names
            readings = [
                VitalSignReading(
                    component_id=component.component_id,
                    signal_name=SIGNAL_THREAD_NOT_ALIVE,
                    observed_at=moment,
                    availability=VitalSignAvailability.OBSERVED,
                    severity_oriented_value=0.0 if is_alive else 1.0,
                    measurement_unit="indicator",
                    normalization_note="1.0 = no live thread named this exists; 0.0 = alive",
                    raw_observation=(
                        f"thread {thread_name!r} {'is alive' if is_alive else 'is NOT among the '
                        f'{len(running_thread_names)} live threads'}"
                    ),
                )
            ]
        readings.append(self._heartbeat_reading(component, moment, observation))
        return readings

    def _heartbeat_reading(
        self,
        component: RegisteredComponent,
        moment: datetime,
        observation: InjectedComponentObservation | None,
    ) -> VitalSignReading:
        if observation is None or observation.last_heartbeat_at is None:
            return _gap_reading(
                component.component_id, GAP_SIGNAL_THREAD_HEARTBEAT, moment,
                reason=(
                    f"no heartbeat stamp was supplied for {component.component_id}: liveness is known "
                    f"only from threading.enumerate(), so a wedged-but-alive thread is invisible"
                ),
            )
        age_seconds = (moment - observation.last_heartbeat_at).total_seconds()
        return VitalSignReading(
            component_id=component.component_id,
            signal_name=SIGNAL_THREAD_HEARTBEAT_AGE_SECONDS,
            observed_at=moment,
            availability=VitalSignAvailability.OBSERVED,
            severity_oriented_value=max(0.0, age_seconds),
            measurement_unit="seconds",
            normalization_note="seconds since the thread last stamped a heartbeat; higher = more wedged",
            raw_observation=f"last heartbeat {observation.last_heartbeat_at.isoformat()}",
        )

    def _host_resource_readings(
        self, component: RegisteredComponent, moment: datetime, snapshot: HostResourceSnapshot
    ) -> list[VitalSignReading]:
        signal_names = _HOST_RESOURCE_SIGNAL_NAMES_BY_COMPONENT_ID.get(component.component_id)
        if signal_names is None:
            return [
                _gap_reading(
                    component.component_id, GAP_SIGNAL_OPERATIONAL_OBSERVATION, moment,
                    reason=(
                        f"{component.component_id} is registered as a HOST_RESOURCE but this collector "
                        f"knows no psutil metric for it"
                    ),
                )
            ]
        return [
            self._host_resource_reading(component.component_id, signal_name, moment, snapshot)
            for signal_name in signal_names
        ]

    def _injected_operational_readings(
        self,
        component: RegisteredComponent,
        moment: datetime,
        observation: InjectedComponentObservation | None,
    ) -> list[VitalSignReading]:
        """CADENCE_ENGINE / DATA_ADAPTER / EXTERNAL_SERVICE — observed only through the DI seam."""
        if observation is None or not observation.carries_any_observation:
            reason = (
                observation.unavailable_reason
                if observation is not None and observation.unavailable_reason
                else (
                    f"no operational observation was injected for {component.component_id}: it lives "
                    f"inside the running service, so its last-success time and failure counters are "
                    f"invisible to a standalone sweep"
                )
            )
            return [
                _gap_reading(
                    component.component_id, GAP_SIGNAL_OPERATIONAL_OBSERVATION, moment, reason=reason
                )
            ]
        readings: list[VitalSignReading] = []
        if observation.last_success_at is not None:
            hours_since = max(
                0.0, (moment - observation.last_success_at).total_seconds() / _SECONDS_PER_HOUR
            )
            readings.append(
                VitalSignReading(
                    component_id=component.component_id,
                    signal_name=SIGNAL_HOURS_SINCE_LAST_SUCCESS,
                    observed_at=moment,
                    availability=VitalSignAvailability.OBSERVED,
                    severity_oriented_value=hours_since,
                    measurement_unit="hours",
                    normalization_note="hours since this component last completed successfully",
                    raw_observation=f"last success {observation.last_success_at.isoformat()}",
                )
            )
        if observation.consecutive_failure_count is not None:
            readings.append(
                VitalSignReading(
                    component_id=component.component_id,
                    signal_name=SIGNAL_CONSECUTIVE_FAILURE_COUNT,
                    observed_at=moment,
                    availability=VitalSignAvailability.OBSERVED,
                    severity_oriented_value=float(observation.consecutive_failure_count),
                    measurement_unit="count",
                    normalization_note="consecutive failures since the last success; higher = worse",
                )
            )
        if observation.error_rate is not None:
            readings.append(
                VitalSignReading(
                    component_id=component.component_id,
                    signal_name=SIGNAL_ERROR_RATE,
                    observed_at=moment,
                    availability=VitalSignAvailability.OBSERVED,
                    severity_oriented_value=float(observation.error_rate),
                    measurement_unit="fraction",
                    normalization_note="fraction of recent attempts that errored; higher = worse",
                )
            )
        return readings

    # -- file-level primitives ---------------------------------------------------------------------

    def _file_state_readings(
        self, component: RegisteredComponent, moment: datetime
    ) -> tuple[list[VitalSignReading], os.stat_result | None]:
        """Existence / mtime age / staleness ratio / byte size for one on-disk component.

        Returns the readings plus the `os.stat_result` (or `None`) so callers that need the size — the
        integrity-check ceiling — do not stat the file a second time.
        """
        component_id = component.component_id
        path = component.state_path
        if path is None:
            reason = (
                f"{component_id} is registered as an on-disk component but declares no state_path, so "
                f"there is nothing to stat"
            )
            return (
                [
                    _unavailable_reading(component_id, signal_name, moment, reason)
                    for signal_name in (
                        SIGNAL_FILE_MISSING,
                        SIGNAL_FILE_MTIME_AGE_HOURS,
                        SIGNAL_STALENESS_RATIO,
                        SIGNAL_FILE_SIZE_MEGABYTES,
                        SIGNAL_FILE_ZERO_BYTES,
                    )
                ],
                None,
            )

        try:
            stat_result = path.stat()
        except FileNotFoundError:
            # ABSENCE IS AN OBSERVATION, not a blind spot: we looked, and it is not there.
            reason = f"file does not exist: {path}"
            readings = [
                VitalSignReading(
                    component_id=component_id,
                    signal_name=SIGNAL_FILE_MISSING,
                    observed_at=moment,
                    availability=VitalSignAvailability.OBSERVED,
                    severity_oriented_value=1.0,
                    measurement_unit="indicator",
                    normalization_note="1.0 = the declared state file is absent; 0.0 = present",
                    raw_observation=str(path),
                )
            ]
            readings.extend(
                _unavailable_reading(component_id, signal_name, moment, reason)
                for signal_name in (
                    SIGNAL_FILE_MTIME_AGE_HOURS,
                    SIGNAL_STALENESS_RATIO,
                    SIGNAL_FILE_SIZE_MEGABYTES,
                    SIGNAL_FILE_ZERO_BYTES,
                )
            )
            return readings, None
        except OSError as failure:
            # Permission denied, a dangling symlink, an I/O error: we could NOT determine anything,
            # including whether the file exists. Every signal is unavailable, with the OS reason.
            reason = f"cannot stat {path}: {type(failure).__name__}: {failure}"
            LOGGER.warning("%s: %s", component_id, reason)
            return (
                [
                    _unavailable_reading(component_id, signal_name, moment, reason)
                    for signal_name in (
                        SIGNAL_FILE_MISSING,
                        SIGNAL_FILE_MTIME_AGE_HOURS,
                        SIGNAL_STALENESS_RATIO,
                        SIGNAL_FILE_SIZE_MEGABYTES,
                        SIGNAL_FILE_ZERO_BYTES,
                    )
                ],
                None,
            )

        age_hours = max(0.0, (moment.timestamp() - float(stat_result.st_mtime)) / _SECONDS_PER_HOUR)
        staleness_budget_hours = (
            component.maximum_staleness_hours
            if component.maximum_staleness_hours is not None
            and component.maximum_staleness_hours > 0.0
            else self._calibration.default_maximum_staleness_hours
        )
        size_bytes = int(stat_result.st_size)
        readings = [
            VitalSignReading(
                component_id=component_id,
                signal_name=SIGNAL_FILE_MISSING,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=0.0,
                measurement_unit="indicator",
                normalization_note="1.0 = the declared state file is absent; 0.0 = present",
                raw_observation=str(path),
            ),
            VitalSignReading(
                component_id=component_id,
                signal_name=SIGNAL_FILE_MTIME_AGE_HOURS,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=age_hours,
                measurement_unit="hours",
                normalization_note="hours since the file was last written; higher = more stale",
                raw_observation=(
                    f"mtime {datetime.fromtimestamp(stat_result.st_mtime, UTC).isoformat()}"
                ),
            ),
            VitalSignReading(
                component_id=component_id,
                signal_name=SIGNAL_STALENESS_RATIO,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=age_hours / staleness_budget_hours,
                measurement_unit="ratio",
                normalization_note=(
                    "mtime age divided by the component's declared maximum_staleness_hours; 1.0 = "
                    "exactly at the declared budget, 2.0 = twice as stale as permitted"
                ),
                raw_observation=f"{age_hours:.2f} h old, budget {staleness_budget_hours:.1f} h",
            ),
            VitalSignReading(
                component_id=component_id,
                signal_name=SIGNAL_FILE_SIZE_MEGABYTES,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=size_bytes / _BYTES_PER_MEGABYTE,
                measurement_unit="MiB",
                normalization_note=(
                    "on-disk size; higher = worse because unbounded growth is this class's degradation "
                    "mode (no universal anchor, so the health index derives a ramp from the component's "
                    "own healthy baseline)"
                ),
                raw_observation=f"{size_bytes} bytes",
            ),
            VitalSignReading(
                component_id=component_id,
                signal_name=SIGNAL_FILE_ZERO_BYTES,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=1.0 if size_bytes == 0 else 0.0,
                measurement_unit="indicator",
                normalization_note="1.0 = the file exists but is empty (a truncated store); 0.0 = has content",
                raw_observation=f"{size_bytes} bytes",
            ),
        ]
        return readings, stat_result

    def _write_ahead_log_reading(
        self, component: RegisteredComponent, moment: datetime, database_path: Path
    ) -> VitalSignReading:
        """WAL size: a write-ahead log that never checkpoints grows without bound and eats the volume."""
        write_ahead_log_path = database_path.with_name(database_path.name + "-wal")
        try:
            size_bytes = write_ahead_log_path.stat().st_size
        except FileNotFoundError:
            size_bytes = 0  # No WAL file = nothing pending. A true zero, not a guess.
        except OSError as failure:
            return _unavailable_reading(
                component.component_id, SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES, moment,
                f"cannot stat {write_ahead_log_path}: {type(failure).__name__}: {failure}",
            )
        return VitalSignReading(
            component_id=component.component_id,
            signal_name=SIGNAL_WRITE_AHEAD_LOG_SIZE_MEGABYTES,
            observed_at=moment,
            availability=VitalSignAvailability.OBSERVED,
            severity_oriented_value=size_bytes / _BYTES_PER_MEGABYTE,
            measurement_unit="MiB",
            normalization_note=(
                "uncheckpointed write-ahead log size; higher = worse (a WAL that never checkpoints is a "
                "stuck writer and an unbounded disk consumer)"
            ),
            raw_observation=f"{write_ahead_log_path.name}: {size_bytes} bytes",
        )

    def _sqlite_integrity_reading(
        self, component: RegisteredComponent, moment: datetime, database_path: Path,
        size_bytes: int | None,
    ) -> tuple[VitalSignReading, int, int]:
        """`PRAGMA integrity_check`, cadenced and cached (see `TelemetryCollectionCalibration`)."""
        component_id = component.component_id
        if not self._calibration.perform_sqlite_integrity_checks:
            return (
                _gap_reading(
                    component_id, GAP_SIGNAL_SQLITE_INTEGRITY_CHECK, moment,
                    reason="SQLite integrity checking is disabled by configuration",
                ),
                0,
                1,
            )
        ceiling = self._calibration.maximum_inline_integrity_check_bytes
        cached = self._integrity_verdict_by_path.get(database_path)
        if cached is not None:
            checked_at, is_corrupt, verdict_text = cached
            age_hours = (moment - checked_at).total_seconds() / _SECONDS_PER_HOUR
            if age_hours < self._calibration.integrity_check_interval_hours:
                return (
                    self._integrity_verdict_reading(
                        component_id, moment, is_corrupt,
                        f"{verdict_text} (cached, checked {checked_at.isoformat()})",
                    ),
                    0,
                    1,
                )
        if ceiling is not None and size_bytes is not None and size_bytes > ceiling:
            return (
                _gap_reading(
                    component_id, GAP_SIGNAL_SQLITE_INTEGRITY_CHECK, moment,
                    reason=(
                        f"{database_path.name} is {size_bytes / _BYTES_PER_MEGABYTE:.1f} MiB, above the "
                        f"{ceiling / _BYTES_PER_MEGABYTE:.1f} MiB inline integrity-check ceiling — it "
                        f"must be verified out of band, so its integrity is UNKNOWN here"
                    ),
                ),
                0,
                1,
            )
        try:
            verdict_text = self._run_sqlite_integrity_check(database_path)
        except sqlite3.Error as failure:
            # A badly damaged file makes SQLite RAISE rather than return a non-"ok" row ("database disk
            # image is malformed", "file is not a database"). That is a corruption VERDICT, not a failure
            # to observe — reporting it as UNAVAILABLE would downgrade a hard failure to a blind spot and
            # let the weighted-max fusion charge it at the DEGRADED tier instead of FAILED. Found by
            # test against a real scribbled-over SQLite file, not by inspection.
            if _is_sqlite_corruption_failure(failure):
                self._integrity_verdict_by_path[database_path] = (moment, True, str(failure))
                LOGGER.error(
                    "%s: SQLite integrity check FAILED for %s: %s: %s",
                    component_id, database_path, type(failure).__name__, failure,
                )
                return (
                    self._integrity_verdict_reading(
                        component_id, moment, True, f"{type(failure).__name__}: {failure}"
                    ),
                    1,
                    0,
                )
            return (
                _unavailable_reading(
                    component_id, SIGNAL_INTEGRITY_CHECK_FAILURE, moment,
                    f"PRAGMA integrity_check on {database_path.name} raised "
                    f"{type(failure).__name__}: {failure}",
                ),
                0,
                1,
            )
        except OSError as failure:
            return (
                _unavailable_reading(
                    component_id, SIGNAL_INTEGRITY_CHECK_FAILURE, moment,
                    f"cannot open {database_path} read-only: {type(failure).__name__}: {failure}",
                ),
                0,
                1,
            )
        is_corrupt = verdict_text.strip().lower() != "ok"
        self._integrity_verdict_by_path[database_path] = (moment, is_corrupt, verdict_text)
        if is_corrupt:
            LOGGER.error(
                "%s: SQLite integrity check FAILED for %s: %s", component_id, database_path, verdict_text
            )
        return self._integrity_verdict_reading(component_id, moment, is_corrupt, verdict_text), 1, 0

    @staticmethod
    def _integrity_verdict_reading(
        component_id: str, moment: datetime, is_corrupt: bool, verdict_text: str
    ) -> VitalSignReading:
        return VitalSignReading(
            component_id=component_id,
            signal_name=SIGNAL_INTEGRITY_CHECK_FAILURE,
            observed_at=moment,
            availability=VitalSignAvailability.OBSERVED,
            severity_oriented_value=1.0 if is_corrupt else 0.0,
            measurement_unit="indicator",
            normalization_note="1.0 = PRAGMA integrity_check reported corruption; 0.0 = 'ok'",
            raw_observation=verdict_text,
        )

    @staticmethod
    def _run_sqlite_integrity_check(database_path: Path) -> str:
        """Open READ-ONLY (`mode=ro`) so a health check can never mutate the organism's own data."""
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=5.0)
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        finally:
            connection.close()
        if not rows:
            return "integrity_check returned no rows"
        return "; ".join(str(row[0]) for row in rows)

    def _artifact_load_reading(
        self, component: RegisteredComponent, moment: datetime, artifact_path: Path
    ) -> VitalSignReading:
        """Can this artifact actually be deserialized? A present-but-unloadable model is a dead model."""
        suffix = artifact_path.suffix.lower()
        try:
            if suffix == ".json":
                json.loads(artifact_path.read_text())
                loader = "json.loads"
            elif suffix in (".joblib", ".pkl", ".pickle"):
                import joblib

                joblib.load(artifact_path)
                loader = "joblib.load"
            else:
                artifact_path.read_bytes()
                loader = "read_bytes"
        except Exception as failure:  # noqa: BLE001 - deserializers raise arbitrary types
            LOGGER.warning(
                "%s: artifact %s exists but will not load: %s: %s",
                component.component_id, artifact_path, type(failure).__name__, failure,
            )
            return VitalSignReading(
                component_id=component.component_id,
                signal_name=SIGNAL_ARTIFACT_LOAD_FAILURE,
                observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=1.0,
                measurement_unit="indicator",
                normalization_note="1.0 = the artifact exists but cannot be deserialized; 0.0 = loads",
                raw_observation=f"{type(failure).__name__}: {failure}",
            )
        return VitalSignReading(
            component_id=component.component_id,
            signal_name=SIGNAL_ARTIFACT_LOAD_FAILURE,
            observed_at=moment,
            availability=VitalSignAvailability.OBSERVED,
            severity_oriented_value=0.0,
            measurement_unit="indicator",
            normalization_note="1.0 = the artifact exists but cannot be deserialized; 0.0 = loads",
            raw_observation=f"loaded with {loader}",
        )

    # -- host resources ----------------------------------------------------------------------------

    def _read_host_resource_snapshot_guarded(self) -> HostResourceSnapshot:
        try:
            return self._host_resource_probe.read_host_resource_snapshot(self._state_volume_path)
        except Exception as failure:  # noqa: BLE001 - an injected or platform probe may raise anything
            reason = f"host resource probe raised {type(failure).__name__}: {failure}"
            LOGGER.warning("%s", reason)
            return HostResourceSnapshot(
                unavailable_reason_by_field=dict.fromkeys(
                    (
                        "process_resident_set_bytes",
                        "host_total_memory_bytes",
                        "process_cpu_percent_of_total_capacity",
                        "open_file_descriptor_count",
                        "open_file_descriptor_limit",
                        "state_volume_total_bytes",
                        "state_volume_free_bytes",
                    ),
                    reason,
                )
            )

    def _host_resource_reading(
        self, component_id: str, signal_name: str, moment: datetime, snapshot: HostResourceSnapshot
    ) -> VitalSignReading:
        if signal_name == SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES:
            if snapshot.process_resident_set_bytes is None:
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    snapshot.reason_for("process_resident_set_bytes"),
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=snapshot.process_resident_set_bytes / _BYTES_PER_MEGABYTE,
                measurement_unit="MiB",
                normalization_note="resident set size of the trading process; higher = worse",
                raw_observation=f"{snapshot.process_resident_set_bytes:.0f} bytes RSS",
            )

        if signal_name == SIGNAL_PROCESS_MEMORY_FRACTION_OF_HOST:
            resident = snapshot.process_resident_set_bytes
            total = snapshot.host_total_memory_bytes
            if resident is None or total is None or total <= 0.0:
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    (
                        snapshot.reason_for("host_total_memory_bytes")
                        if total is None
                        else "host total memory reported as zero — the fraction is undefined"
                        if total <= 0.0
                        else snapshot.reason_for("process_resident_set_bytes")
                    ),
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=resident / total,
                measurement_unit="fraction",
                normalization_note=(
                    "process RSS as a fraction of host RAM — the box-independent form of the memory "
                    "setpoint; higher = worse"
                ),
                raw_observation=f"{resident / _BYTES_PER_GIGABYTE:.3f} of {total / _BYTES_PER_GIGABYTE:.3f} GiB",
            )

        if signal_name == SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY:
            if snapshot.process_cpu_percent_of_total_capacity is None:
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    snapshot.reason_for("process_cpu_percent_of_total_capacity"),
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=snapshot.process_cpu_percent_of_total_capacity,
                measurement_unit="% of all cores",
                normalization_note=(
                    "process CPU divided by the logical core count, so the signal means the same on any "
                    "box; higher = worse"
                ),
            )

        if signal_name == SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT:
            if snapshot.open_file_descriptor_count is None:
                return _unavailable_reading(
                    component_id, signal_name, moment, snapshot.reason_for("open_file_descriptor_count")
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=snapshot.open_file_descriptor_count,
                measurement_unit="count",
                normalization_note=(
                    "open file descriptors — SQLite connections and sockets leak here; higher = worse "
                    "(no universal anchor: the health index ramps it off this process's own baseline)"
                ),
            )

        if signal_name == SIGNAL_OPEN_FILE_DESCRIPTOR_FRACTION:
            count = snapshot.open_file_descriptor_count
            limit = snapshot.open_file_descriptor_limit
            if count is None or limit is None or limit <= 0.0:
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    (
                        snapshot.reason_for("open_file_descriptor_limit")
                        if limit is None
                        else "RLIMIT_NOFILE reported as zero/unlimited — the fraction is undefined"
                        if limit <= 0.0
                        else snapshot.reason_for("open_file_descriptor_count")
                    ),
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=count / limit,
                measurement_unit="fraction",
                normalization_note="open fds as a fraction of the RLIMIT_NOFILE soft limit; higher = worse",
                raw_observation=f"{count:.0f} of {limit:.0f}",
            )

        if signal_name == SIGNAL_STATE_VOLUME_USED_FRACTION:
            total = snapshot.state_volume_total_bytes
            free = snapshot.state_volume_free_bytes
            if total is None or free is None:
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    snapshot.reason_for(
                        "state_volume_total_bytes" if total is None else "state_volume_free_bytes"
                    ),
                )
            if total <= 0.0:
                # A zero-byte volume is not "0% used" — it is an unusable reading (Rule O.4).
                return _unavailable_reading(
                    component_id, signal_name, moment,
                    f"state volume {self._state_volume_path} reports a total size of {total!r} bytes, "
                    f"so a used-fraction cannot be computed",
                )
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=_clamp_to_unit_range((total - free) / total),
                measurement_unit="fraction",
                normalization_note=(
                    "INVERTED goodness signal: free space expressed as USED fraction of the state "
                    "volume; higher = worse"
                ),
                raw_observation=(
                    f"{free / _BYTES_PER_GIGABYTE:.2f} GiB free of {total / _BYTES_PER_GIGABYTE:.2f} GiB"
                ),
            )

        if signal_name == SIGNAL_STATE_VOLUME_FREE_SHORTFALL_GIGABYTES:
            free = snapshot.state_volume_free_bytes
            if free is None:
                return _unavailable_reading(
                    component_id, signal_name, moment, snapshot.reason_for("state_volume_free_bytes")
                )
            free_gigabytes = free / _BYTES_PER_GIGABYTE
            minimum_free = self._calibration.minimum_state_volume_free_gigabytes
            return VitalSignReading(
                component_id=component_id, signal_name=signal_name, observed_at=moment,
                availability=VitalSignAvailability.OBSERVED,
                severity_oriented_value=max(0.0, minimum_free - free_gigabytes),
                measurement_unit="GiB",
                normalization_note=(
                    "INVERTED goodness signal: max(0, minimum_required_free_gib - free_gib). 0.0 while "
                    "there is enough room, rising to the full requirement on a completely full volume"
                ),
                raw_observation=f"{free_gigabytes:.2f} GiB free, {minimum_free:.1f} GiB required",
            )

        return _gap_reading(
            component_id, GAP_SIGNAL_OPERATIONAL_OBSERVATION, moment,
            reason=f"this collector has no reader for host signal {signal_name!r}",
        )

    def _read_running_thread_names_guarded(self) -> tuple[frozenset[str], str]:
        try:
            names = self._running_thread_name_reader.read_running_thread_names()
        except Exception as failure:  # noqa: BLE001 - an injected reader may raise anything
            reason = f"thread enumeration raised {type(failure).__name__}: {failure}"
            LOGGER.warning("%s", reason)
            return frozenset(), reason
        return frozenset(names), ""

    # -- assembly + persistence --------------------------------------------------------------------

    def _index_injected_observations(
        self, injected_observations: Iterable[InjectedComponentObservation]
    ) -> tuple[dict[str, InjectedComponentObservation], tuple[str, ...]]:
        indexed: dict[str, InjectedComponentObservation] = {}
        unrecognized: list[str] = []
        for observation in injected_observations:
            if observation.component_id in indexed:
                raise ValueError(
                    f"two InjectedComponentObservation objects were supplied for "
                    f"{observation.component_id!r} — the collector will not silently pick one"
                )
            indexed[observation.component_id] = observation
            if not self._registry.is_recognized(observation.component_id):
                unrecognized.append(observation.component_id)
        if unrecognized:
            LOGGER.warning(
                "telemetry sweep received observations for components the registry does not recognise "
                "(non-self): %s",
                ", ".join(sorted(unrecognized)),
            )
        return indexed, tuple(sorted(unrecognized))

    @staticmethod
    def _build_telemetry_samples(
        readings: Sequence[VitalSignReading],
        moment: datetime,
        components: Sequence[RegisteredComponent],
    ) -> list[ComponentTelemetrySample]:
        """Group readings into the exact `component_health_index.ComponentTelemetrySample` contract."""
        values_by_component_id: dict[str, dict[str, float]] = {}
        for reading in readings:
            values_by_component_id.setdefault(reading.component_id, {})[reading.signal_name] = (
                reading.health_index_signal_value
            )
        return [
            ComponentTelemetrySample(
                component_id=component.component_id,
                captured_at=moment,
                signal_values=values_by_component_id[component.component_id],
            )
            for component in components
            if component.component_id in values_by_component_id
        ]

    def _persist_readings(self, readings: Sequence[VitalSignReading]) -> tuple[int, str]:
        """Append every reading to the state store; an UNAVAILABLE one as an `unavailable:*` marker.

        SQLite coerces a NaN REAL to NULL, which the store's `signal_value REAL NOT NULL` column rejects
        (verified 2026-07-27), so the unavailability is persisted as a positive `1.0` fact under a
        prefixed name instead of as a fabricated value.
        """
        if self._state_store is None:
            return 0, "no AutopoiesisStateStore was supplied — this sweep was not persisted"
        persisted = [
            PersistedTelemetrySample(
                component_id=reading.component_id,
                captured_at=reading.observed_at,
                signal_name=(
                    reading.signal_name
                    if reading.severity_oriented_value is not None
                    else f"{UNAVAILABLE_SIGNAL_PERSISTENCE_PREFIX}{reading.signal_name}"
                ),
                signal_value=(
                    reading.severity_oriented_value
                    if reading.severity_oriented_value is not None
                    else 1.0
                ),
            )
            for reading in readings
        ]
        try:
            return self._state_store.record_telemetry_samples(persisted), ""
        except Exception as failure:  # noqa: BLE001 - a failed write must be surfaced, not fatal
            reason = f"telemetry persistence failed: {type(failure).__name__}: {failure}"
            LOGGER.error("%s", reason)
            return 0, reason


# ---------------------------------------------------------------------------------------------------
# Module-level helpers.
# ---------------------------------------------------------------------------------------------------


def _require_utc_moment(moment: datetime) -> datetime:
    """Reject a naive timestamp outright and normalise an aware one to UTC.

    IST/UTC confusion is a documented past bug class in this repo (Rule O.5), and the state store
    rejects naive datetimes at its own boundary anyway — failing here gives the caller a far clearer
    error than a persistence failure three layers down.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            f"telemetry collection requires a timezone-aware (UTC-explicit) moment; got {moment!r}"
        )
    return moment.astimezone(UTC)


def _clamp_to_unit_range(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _unavailable_reading(
    component_id: str, signal_name: str, moment: datetime, reason: str
) -> VitalSignReading:
    """A signal that SHOULD have been readable and was not — never omitted, never defaulted healthy."""
    return VitalSignReading(
        component_id=component_id,
        signal_name=signal_name,
        observed_at=moment,
        availability=VitalSignAvailability.UNAVAILABLE,
        severity_oriented_value=None,
        measurement_unit="unavailable",
        normalization_note=(
            "emitted to the health index as NaN, which charges the declared unreadable-signal severity "
            "and blocks healthy-baseline admission for this cycle"
        ),
        unavailable_reason=reason,
    )


def _gap_reading(
    component_id: str, signal_name: str, moment: datetime, reason: str
) -> VitalSignReading:
    """A STRUCTURAL blind spot: the organism has no mechanism to read this at all.

    The gap itself is the measurement (`1.0`), weighted at `OBSERVABILITY_GAP_SIGNAL_WEIGHT` so the
    component can never read better than DEGRADED while the gap exists.
    """
    return VitalSignReading(
        component_id=component_id,
        signal_name=signal_name,
        observed_at=moment,
        availability=VitalSignAvailability.NOT_INSTRUMENTED,
        severity_oriented_value=1.0,
        measurement_unit="indicator",
        normalization_note=(
            f"1.0 = this vital sign has no reader in the organism at all; charged at weight "
            f"{OBSERVABILITY_GAP_SIGNAL_WEIGHT} (the DEGRADED tier) — a blind spot is a real loss of "
            f"observability but not proof of failure"
        ),
        unavailable_reason=reason,
    )


#: Substrings SQLite uses when the FILE ITSELF is damaged, as opposed to merely unreachable (locked,
#: busy, permission denied). Matched case-insensitively against the exception text because `sqlite3`
#: signals corruption through the message rather than through a dedicated exception class.
_SQLITE_CORRUPTION_MESSAGE_MARKERS: Final[tuple[str, ...]] = (
    "malformed",
    "not a database",
    "database corrupt",
    "corrupt",
    "encrypted",
)


def _is_sqlite_corruption_failure(failure: sqlite3.Error) -> bool:
    """Does this exception mean "the data is damaged" rather than "I could not look"?

    The distinction is load-bearing: damage is an OBSERVED failure that must reach the health index at
    full severity, while unreachability is a blind spot that must be reported as UNAVAILABLE. Collapsing
    them either way loses information (Rule O.3).
    """
    message = str(failure).lower()
    return any(marker in message for marker in _SQLITE_CORRUPTION_MESSAGE_MARKERS)
