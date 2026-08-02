"""Trunk X AUTOPOIESIS — the SETPOINT KEEPER: essential variables held inside a VIABILITY SET.

The third acting lever of the component-lifecycle homeostat (research/172 §2/§3 "Setpoints" row, §9
"Throttle"): it modulates the organism's own workload — `scan_interval_seconds`, universe breadth and
LLM call rate — so that its essential variables stay inside a feasible region.

--------------------------------------------------------------------------------------------------
WHY A VIABILITY *SET*, NOT SIX PID LOOPS (research/169 §4)
--------------------------------------------------------------------------------------------------
research/169 §4.3 answers this directly, and the difference is structural rather than incremental:

* A **PID loop** regulates ONE scalar against ONE setpoint through an error signal. It has no concept
  of a feasible region and no concept of "the current control law is about to stop working". Six
  independent PID loops over RSS, CPU, fds, disk, cycle duration and LLM rate would each pull their own
  lever, and would fight: the memory loop widens the universe back out at the same moment the CPU loop
  narrows it, because neither can see that they share one actuator.
* **Ashby's ultrastability** (§4.1) regulates a *vector* of essential variables against a **viability
  zone** with two nested loops: a fast loop that absorbs ordinary perturbation inside a fixed
  parameterization, and a slow loop that **re-parameterizes the fast loop** whenever an essential
  variable leaves its allowed range.
* **Aubin's viability kernel** (§4.2) generalises that to a set: the *viable regulation map* restricts,
  at each state, the admissible controls to those that keep the trajectory inside the constraint set —
  on the boundary the admissible set is small, in the interior it is the full control range.

Both give a principled answer to "what do you do when regulation is about to fail", and both make the
same operational prescription that research/172 §3 states in one line: **the throttle acts on whichever
variable is nearest its boundary**. That is what this module implements.

--------------------------------------------------------------------------------------------------
THE MATH
--------------------------------------------------------------------------------------------------
The viability set is a box `K = X_i [lower_i, upper_i]` in the space of essential variables. Because the
variables carry incommensurable units (MiB, % of cores, file-descriptor counts, a fraction, seconds,
calls/minute), the distance to the boundary is expressed in each variable's **own** normalization scale
(Rule O.4 — normalize before combining scales):

    margin_i(x) = min(x_i - lower_i, upper_i - x_i) / scale_i

* `margin > 0` — inside; the value is the number of scales of headroom before the nearest boundary.
* `margin = 0` — exactly ON the boundary of the viability set.
* `margin < 0` — OUTSIDE; the magnitude is how far outside, in scales.

The **binding variable** is `argmin_i margin_i` — the one nearest (or furthest past) its boundary. It
names the reason, and it selects which levers move (each variable declares a `ThrottleLeverEmphasis`
saying which actuators actually influence it: universe breadth drives memory and file descriptors, the
scan interval drives CPU and cycle duration, the LLM rate drives itself). When several variables are
outside at once, the emphasis is taken as the per-lever MAXIMUM over all of them, so a jointly-violated
state pulls every relevant lever rather than only the worst one's.

A one-sided constraint is expressed with an infinite bound and an explicit scale: RSS is
`(-inf, 4096 MiB]` with `scale = 1024 MiB`, so an *empty* process is not scored as "at a boundary" the
way a symmetric two-sided normalization would score it.

--------------------------------------------------------------------------------------------------
HYSTERESIS / DEADBAND — WHY THE THROTTLE CANNOT OSCILLATE
--------------------------------------------------------------------------------------------------
A bare "tighten while outside, relax while inside" rule chatters: the throttle pushes the state just
inside the boundary, relaxes, the state crosses out again, forever. Two independent guards prevent it:

1. **A margin deadband.** Tightening is triggered at `margin < tighten_margin_threshold` (default 0.0 —
   i.e. actually outside). Relaxation is permitted only at `margin >= relax_margin_threshold`
   (default 0.25 — a quarter of a normalization scale *inside* the boundary). Between the two the
   decision is `HOLD`: neither tighten nor relax. That gap **is** the Schmitt-trigger band, and it is
   exactly the region a bang-bang controller would oscillate in.
2. **A relaxation dwell time.** Even deep inside the set, the throttle may only step back toward nominal
   once per `minimum_relaxation_interval_seconds` (default 60 s) and only by `relaxation_step`
   (default 0.05), against a tightening step of `tightening_step` (default 0.34) that is further scaled
   by how far outside the binding variable sits. Recovery therefore takes ~20 cycles where degradation
   takes ~3 — the asymmetry is the safety property, not an accident.

--------------------------------------------------------------------------------------------------
TIGHTEN-ONLY BY DEFAULT (research/172 §2 "sign/unit conventions")
--------------------------------------------------------------------------------------------------
The throttle level lives in `[0, 1]`, `0` = nominal. The emitted multipliers are clamped structurally:
`scan_interval_multiplier >= 1.0` (it may only ever SLOW the organism down) and
`universe_breadth_multiplier <= 1.0`, `llm_call_rate_multiplier <= 1.0` (they may only ever NARROW it).
There is no arithmetic path by which this module can make the organism do more work than its nominal
configuration — the same structural clamp the vitality gate uses, for the same reason.

A further tighten-only rule covers ignorance: while any declared essential variable is **unmeasured**
(absent, NaN or infinite), relaxation is forbidden outright. A keeper that cannot see its own state must
not be permitted to speed the organism back up.

--------------------------------------------------------------------------------------------------
CONSUMERS (Rule G)
--------------------------------------------------------------------------------------------------
`ComponentTelemetryCollector.collect_organism_vital_signs(...).essential_variable_measurements()`
supplies the four host-resource variables directly (same signal names, same units — that is why the
collector emits disk pressure as a USED fraction). The service supplies the two in-process variables
(`scan_cycle_duration_seconds`, `llm_calls_per_minute`). `autopoiesis_orchestrator` applies the returned
decision to the live loop via `apply_to_scan_interval_seconds` / `apply_to_universe_size` /
`apply_to_llm_calls_per_minute`; it is queued in `docs/BACKLOG.md`.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Final

from nse_algo_trader.autopoiesis.component_telemetry_collector import (
    SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT,
    SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY,
    SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES,
    SIGNAL_STATE_VOLUME_USED_FRACTION,
)

LOGGER: Final = logging.getLogger(__name__)

#: The two essential variables the running service owns (the collector cannot see inside the loop).
VARIABLE_SCAN_CYCLE_DURATION_SECONDS: Final = "scan_cycle_duration_seconds"
VARIABLE_LLM_CALLS_PER_MINUTE: Final = "llm_calls_per_minute"

#: The four the collector supplies, under exactly the signal names it emits.
VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES: Final = SIGNAL_PROCESS_RESIDENT_SET_MEGABYTES
VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY: Final = SIGNAL_PROCESS_CPU_PERCENT_OF_CAPACITY
VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT: Final = SIGNAL_OPEN_FILE_DESCRIPTOR_COUNT
VARIABLE_STATE_VOLUME_USED_FRACTION: Final = SIGNAL_STATE_VOLUME_USED_FRACTION


class ThrottleAction(str, Enum):
    """What this cycle did to the throttle. `HOLD` is the deadband verdict, and it is a real outcome."""

    TIGHTEN = "tighten"
    HOLD = "hold"
    RELAX = "relax"


@dataclass(frozen=True)
class ThrottleLeverEmphasis:
    """How much each actuator actually influences one essential variable, in `[0, 1]`.

    This is the "viable regulation map" made concrete (research/169 §4.2): it restricts which controls
    are admissible responses to a given variable leaving the set. Narrowing the universe genuinely
    reduces resident memory and open file descriptors; lengthening the scan interval genuinely reduces
    CPU and cycle duration; neither does much about the LLM call rate, which has its own lever. Pulling
    a lever that cannot influence the binding variable would slow the organism for no benefit.
    """

    scan_interval: float = 0.0
    universe_breadth: float = 0.0
    llm_call_rate: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("scan_interval", self.scan_interval),
            ("universe_breadth", self.universe_breadth),
            ("llm_call_rate", self.llm_call_rate),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"ThrottleLeverEmphasis.{name} must be a finite fraction in [0, 1]")
        if self.scan_interval == self.universe_breadth == self.llm_call_rate == 0.0:
            raise ValueError(
                "a ThrottleLeverEmphasis with every lever at zero declares an essential variable no "
                "actuator can influence — such a variable cannot be regulated and must not be declared"
            )

    def combined_with(self, other: ThrottleLeverEmphasis) -> ThrottleLeverEmphasis:
        """Per-lever maximum — how several simultaneously-violated variables compose."""
        return ThrottleLeverEmphasis(
            scan_interval=max(self.scan_interval, other.scan_interval),
            universe_breadth=max(self.universe_breadth, other.universe_breadth),
            llm_call_rate=max(self.llm_call_rate, other.llm_call_rate),
        )


@dataclass(frozen=True)
class EssentialVariableInterval:
    """One axis of the viability set: an interval, its unit, its scale, and its admissible controls.

    Either bound may be infinite (a one-sided constraint). `boundary_normalization_scale` is then
    REQUIRED, because a half-open interval has no half-width to normalise by; supplying it explicitly is
    what keeps `margin` comparable across variables measured in MiB, percent and bare counts.
    """

    variable_name: str
    lower_bound: float
    upper_bound: float
    measurement_unit: str
    lever_emphasis: ThrottleLeverEmphasis
    boundary_normalization_scale: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.variable_name:
            raise ValueError("EssentialVariableInterval.variable_name must be a non-empty identifier")
        if math.isnan(self.lower_bound) or math.isnan(self.upper_bound):
            raise ValueError(f"{self.variable_name}: viability bounds must not be NaN")
        if self.lower_bound >= self.upper_bound:
            raise ValueError(
                f"{self.variable_name}: viability interval must have positive width; got "
                f"[{self.lower_bound}, {self.upper_bound}]"
            )
        if self.boundary_normalization_scale is None:
            if not math.isfinite(self.lower_bound) or not math.isfinite(self.upper_bound):
                raise ValueError(
                    f"{self.variable_name}: a one-sided viability interval must declare an explicit "
                    f"boundary_normalization_scale — a half-open interval has no half-width"
                )
        elif (
            not math.isfinite(self.boundary_normalization_scale)
            or self.boundary_normalization_scale <= 0.0
        ):
            raise ValueError(
                f"{self.variable_name}: boundary_normalization_scale must be finite and positive"
            )

    @property
    def normalization_scale(self) -> float:
        """The declared scale, else the interval's own half-width."""
        if self.boundary_normalization_scale is not None:
            return self.boundary_normalization_scale
        return (self.upper_bound - self.lower_bound) / 2.0

    def normalized_boundary_margin(self, value: float) -> float:
        """`min(value - lower, upper - value) / scale`; negative outside, 0 on the boundary.

        The `min` over both bounds is what makes this a SET-membership measure rather than a per-bound
        error: a two-sided variable binds on whichever side it is closer to, with no extra bookkeeping.
        """
        if not math.isfinite(value):
            raise ValueError(
                f"{self.variable_name}: a non-finite measurement ({value!r}) is not an observation — "
                f"omit it so the keeper reports the variable as unmeasured"
            )
        distance_below_upper = self.upper_bound - value
        distance_above_lower = value - self.lower_bound
        nearest = min(distance_above_lower, distance_below_upper)
        if math.isinf(nearest):
            # Both bounds infinite is rejected at construction, so this is the finite-side value.
            nearest = distance_below_upper if math.isfinite(self.upper_bound) else distance_above_lower
        return nearest / self.normalization_scale

    def contains(self, value: float) -> bool:
        return self.lower_bound <= value <= self.upper_bound

    def describe_bounds(self) -> str:
        lower = "-inf" if math.isinf(self.lower_bound) else f"{self.lower_bound:g}"
        upper = "+inf" if math.isinf(self.upper_bound) else f"{self.upper_bound:g}"
        return f"[{lower}, {upper}] {self.measurement_unit}"


#: The organism's essential variables (research/172 §3 "Setpoints" row). Bounds are the operating
#: envelope of the box this runs on (30 GiB RAM, 29 GiB state volume, aarch64) and of the live loop's
#: 5 s nominal scan interval; every one of them is a genuine constraint, not a decorative threshold.
DEFAULT_ESSENTIAL_VARIABLE_INTERVALS: Final[tuple[EssentialVariableInterval, ...]] = (
    EssentialVariableInterval(
        variable_name=VARIABLE_PROCESS_RESIDENT_SET_MEGABYTES,
        lower_bound=-math.inf, upper_bound=4096.0, measurement_unit="MiB",
        boundary_normalization_scale=1024.0,
        lever_emphasis=ThrottleLeverEmphasis(universe_breadth=1.0, scan_interval=0.3, llm_call_rate=0.3),
        description="resident set size — grows with universe breadth (bars, chains, feature frames)",
    ),
    EssentialVariableInterval(
        variable_name=VARIABLE_PROCESS_CPU_PERCENT_OF_CAPACITY,
        lower_bound=-math.inf, upper_bound=85.0, measurement_unit="% of all cores",
        boundary_normalization_scale=25.0,
        lever_emphasis=ThrottleLeverEmphasis(scan_interval=1.0, universe_breadth=0.6),
        description="process CPU as a share of the whole machine — driven by scan frequency x breadth",
    ),
    EssentialVariableInterval(
        variable_name=VARIABLE_OPEN_FILE_DESCRIPTOR_COUNT,
        lower_bound=-math.inf, upper_bound=4096.0, measurement_unit="count",
        boundary_normalization_scale=1024.0,
        lever_emphasis=ThrottleLeverEmphasis(universe_breadth=1.0, scan_interval=0.4),
        description="open file descriptors — SQLite connections and broker sockets leak here",
    ),
    EssentialVariableInterval(
        variable_name=VARIABLE_STATE_VOLUME_USED_FRACTION,
        lower_bound=-math.inf, upper_bound=0.90, measurement_unit="fraction",
        boundary_normalization_scale=0.10,
        lever_emphasis=ThrottleLeverEmphasis(scan_interval=1.0, universe_breadth=0.8),
        description="state-volume pressure — the inverted 'disk free' constraint; writes fill it",
    ),
    EssentialVariableInterval(
        variable_name=VARIABLE_SCAN_CYCLE_DURATION_SECONDS,
        lower_bound=-math.inf, upper_bound=30.0, measurement_unit="seconds",
        boundary_normalization_scale=10.0,
        lever_emphasis=ThrottleLeverEmphasis(universe_breadth=1.0, scan_interval=0.7, llm_call_rate=0.6),
        description="wall time of one scan cycle — a cycle longer than the interval means falling behind",
    ),
    EssentialVariableInterval(
        variable_name=VARIABLE_LLM_CALLS_PER_MINUTE,
        lower_bound=-math.inf, upper_bound=20.0, measurement_unit="calls/minute",
        boundary_normalization_scale=8.0,
        lever_emphasis=ThrottleLeverEmphasis(llm_call_rate=1.0, scan_interval=0.5),
        description="LLM provider pressure — the rate that exhausts free tiers and trips cooldowns",
    ),
)


@dataclass(frozen=True)
class ViabilitySet:
    """The feasible region `K` — the product of every essential variable's interval."""

    intervals: tuple[EssentialVariableInterval, ...] = DEFAULT_ESSENTIAL_VARIABLE_INTERVALS

    def __post_init__(self) -> None:
        if not self.intervals:
            raise ValueError(
                "a ViabilitySet with no essential variables cannot constrain anything — the keeper "
                "would emit a nominal decision forever while claiming to regulate"
            )
        seen: set[str] = set()
        for interval in self.intervals:
            if interval.variable_name in seen:
                raise ValueError(f"duplicate essential variable in ViabilitySet: {interval.variable_name}")
            seen.add(interval.variable_name)

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(interval.variable_name for interval in self.intervals)

    def interval_for(self, variable_name: str) -> EssentialVariableInterval | None:
        for interval in self.intervals:
            if interval.variable_name == variable_name:
                return interval
        return None


@dataclass(frozen=True)
class EssentialVariableMargin:
    """One variable's distance to the boundary of the viability set, in its own normalization scales."""

    variable_name: str
    measured_value: float
    normalized_margin: float
    is_inside: bool
    measurement_unit: str
    bounds_description: str

    def describe(self) -> str:
        position = "INSIDE " if self.is_inside else "OUTSIDE"
        return (
            f"{self.variable_name:38s} {self.measured_value:12.4f} {self.measurement_unit:14s} "
            f"{position} margin {self.normalized_margin:+.4f}  bounds {self.bounds_description}"
        )


@dataclass(frozen=True)
class HomeostaticThrottleDecision:
    """The acting output: how much to slow the organism down, which variable forced it, and why.

    Every multiplier is structurally tighten-only — see the module docstring. `binding_variable_name`
    is `argmin` over the margins, i.e. the Ashby/Aubin "nearest the boundary" variable.
    """

    decided_at: datetime
    action: ThrottleAction
    throttle_level: float
    scan_interval_multiplier: float
    universe_breadth_multiplier: float
    llm_call_rate_multiplier: float
    binding_variable_name: str
    binding_variable_margin: float
    is_within_viability_set: bool
    reason: str
    variable_margins: tuple[EssentialVariableMargin, ...] = ()
    outside_variable_names: tuple[str, ...] = ()
    unmeasured_variable_names: tuple[str, ...] = ()
    unrecognized_variable_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.throttle_level) or not 0.0 <= self.throttle_level <= 1.0:
            raise ValueError(f"throttle_level escaped [0, 1]: {self.throttle_level!r}")
        if not math.isfinite(self.scan_interval_multiplier) or self.scan_interval_multiplier < 1.0:
            raise ValueError(
                f"scan_interval_multiplier must be >= 1.0 (tighten-only: the keeper may only ever slow "
                f"the organism down); got {self.scan_interval_multiplier!r}"
            )
        for name, multiplier in (
            ("universe_breadth_multiplier", self.universe_breadth_multiplier),
            ("llm_call_rate_multiplier", self.llm_call_rate_multiplier),
        ):
            if not math.isfinite(multiplier) or not 0.0 < multiplier <= 1.0:
                raise ValueError(
                    f"{name} must lie in (0, 1] (tighten-only: the keeper may only ever narrow the "
                    f"organism); got {multiplier!r}"
                )
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError(f"decided_at must be timezone-aware (UTC-explicit); got {self.decided_at!r}")

    @property
    def is_nominal(self) -> bool:
        return self.throttle_level <= 0.0

    def apply_to_scan_interval_seconds(self, nominal_scan_interval_seconds: float) -> float:
        """The throttled scan interval. Never shorter than nominal."""
        if not math.isfinite(nominal_scan_interval_seconds) or nominal_scan_interval_seconds <= 0.0:
            raise ValueError(
                f"nominal_scan_interval_seconds must be finite and positive; got "
                f"{nominal_scan_interval_seconds!r}"
            )
        return nominal_scan_interval_seconds * self.scan_interval_multiplier

    def apply_to_universe_size(self, nominal_universe_size: int) -> int:
        """The throttled universe size. Never larger than nominal, and never below 1 while non-empty.

        Flooring at 1 rather than 0 is deliberate: a throttle that can silence the organism entirely is
        an off-switch, and the off-switch is the operator's (research/172 §9) — not this module's.
        """
        if nominal_universe_size < 0:
            raise ValueError(f"nominal_universe_size cannot be negative; got {nominal_universe_size}")
        if nominal_universe_size == 0:
            return 0
        return max(1, int(nominal_universe_size * self.universe_breadth_multiplier))

    def apply_to_llm_calls_per_minute(self, nominal_calls_per_minute: float) -> float:
        """The throttled LLM call budget. Never larger than nominal."""
        if not math.isfinite(nominal_calls_per_minute) or nominal_calls_per_minute < 0.0:
            raise ValueError(
                f"nominal_calls_per_minute must be finite and non-negative; got "
                f"{nominal_calls_per_minute!r}"
            )
        return nominal_calls_per_minute * self.llm_call_rate_multiplier

    def describe(self) -> str:
        """Multi-line summary for the Rule-F by-eye pass and the dashboard surface."""
        header = (
            f"{self.action.value.upper():7s} throttle={self.throttle_level:.3f}  "
            f"scan x{self.scan_interval_multiplier:.3f}  breadth x{self.universe_breadth_multiplier:.3f}  "
            f"llm x{self.llm_call_rate_multiplier:.3f}  binding={self.binding_variable_name} "
            f"(margin {self.binding_variable_margin:+.4f})"
        )
        return "\n".join([header, f"  reason: {self.reason}"]
                         + [f"  {margin.describe()}" for margin in self.variable_margins])


@dataclass(frozen=True)
class SetpointKeeperCalibration:
    """Every tunable of the regulation law, in one auditable frozen object.

    The tighten/relax asymmetry is the safety property: at the defaults it takes ~3 cycles to reach full
    throttle and ~20 (each at least `minimum_relaxation_interval_seconds` apart) to return to nominal.
    """

    #: Below this margin the binding variable is treated as violated and the throttle TIGHTENS.
    #: `0.0` = exactly the boundary of the viability set.
    tighten_margin_threshold: float = 0.0
    #: At or above this margin the throttle may RELAX. The gap to `tighten_margin_threshold` is the
    #: Schmitt-trigger deadband inside which the decision is HOLD — see the module docstring.
    relax_margin_threshold: float = 0.25
    tightening_step: float = 0.34
    relaxation_step: float = 0.05
    #: Ashby's slow loop: a variable deep outside the set re-parameterizes harder than one just outside.
    #: The step is multiplied by `1 + min(|margin|, excursion_response_cap)`.
    excursion_response_cap: float = 2.0
    minimum_relaxation_interval_seconds: float = 60.0
    maximum_scan_interval_multiplier: float = 8.0
    minimum_universe_breadth_multiplier: float = 0.10
    minimum_llm_call_rate_multiplier: float = 0.05
    decision_history_length: int = 256

    def __post_init__(self) -> None:
        if self.relax_margin_threshold <= self.tighten_margin_threshold:
            raise ValueError(
                "relax_margin_threshold must exceed tighten_margin_threshold — the gap between them IS "
                "the hysteresis deadband, and a non-positive gap is a chattering bang-bang controller"
            )
        for name, step in (
            ("tightening_step", self.tightening_step),
            ("relaxation_step", self.relaxation_step),
        ):
            if not 0.0 < step <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1]; got {step}")
        if self.relaxation_step > self.tightening_step:
            raise ValueError(
                "relaxation_step must not exceed tightening_step — the keeper is tighten-only by "
                "default, so it must never recover faster than it degrades"
            )
        if self.excursion_response_cap < 0.0:
            raise ValueError("excursion_response_cap must be non-negative")
        if self.minimum_relaxation_interval_seconds < 0.0:
            raise ValueError("minimum_relaxation_interval_seconds must be non-negative")
        if self.maximum_scan_interval_multiplier < 1.0:
            raise ValueError(
                "maximum_scan_interval_multiplier must be >= 1.0 (tighten-only: the scan interval may "
                "only ever grow)"
            )
        for name, floor in (
            ("minimum_universe_breadth_multiplier", self.minimum_universe_breadth_multiplier),
            ("minimum_llm_call_rate_multiplier", self.minimum_llm_call_rate_multiplier),
        ):
            if not 0.0 < floor <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1]; got {floor}")
        if self.decision_history_length < 1:
            raise ValueError("decision_history_length must be at least 1")


class HomeostaticSetpointKeeper:
    """Holds the organism's essential variables inside the viability set by throttling its workload.

    The carried state is the whole point (it is what makes the hysteresis and the dwell time real, not
    just declared): the current throttle level, the moment of the last relaxation, the consecutive-cycles
    counters, and a bounded decision history for the dashboard.

    Not named `engine`: research/172 §5.7 reserves that for parts carrying a solver. This carries a
    control law and its state, and its role name — `keeper` — is the one research/172 §8 gives it.
    """

    def __init__(
        self,
        viability_set: ViabilitySet | None = None,
        calibration: SetpointKeeperCalibration | None = None,
    ) -> None:
        self._viability_set = viability_set if viability_set is not None else ViabilitySet()
        self._calibration = calibration if calibration is not None else SetpointKeeperCalibration()
        self._throttle_level: float = 0.0
        self._last_relaxation_at: datetime | None = None
        self._consecutive_outside_cycle_count: int = 0
        self._consecutive_inside_cycle_count: int = 0
        self._decision_history: deque[HomeostaticThrottleDecision] = deque(
            maxlen=self._calibration.decision_history_length
        )

    # -- introspection -----------------------------------------------------------------------------

    @property
    def viability_set(self) -> ViabilitySet:
        return self._viability_set

    @property
    def calibration(self) -> SetpointKeeperCalibration:
        return self._calibration

    @property
    def throttle_level(self) -> float:
        """Current carried throttle, `[0, 1]`. `0.0` = the organism runs at its nominal configuration."""
        return self._throttle_level

    @property
    def consecutive_outside_cycle_count(self) -> int:
        return self._consecutive_outside_cycle_count

    @property
    def consecutive_inside_cycle_count(self) -> int:
        return self._consecutive_inside_cycle_count

    @property
    def hysteresis_deadband(self) -> tuple[float, float]:
        """`[tighten_threshold, relax_threshold)` — the margin band in which the decision is HOLD."""
        return (self._calibration.tighten_margin_threshold, self._calibration.relax_margin_threshold)

    def recent_decisions(self, limit: int = 20) -> tuple[HomeostaticThrottleDecision, ...]:
        """Most-recent-last, so a straddling sequence can be inspected in order."""
        history = list(self._decision_history)
        return tuple(history[-limit:]) if limit > 0 else ()

    @property
    def latest_decision(self) -> HomeostaticThrottleDecision | None:
        return self._decision_history[-1] if self._decision_history else None

    # -- the regulation cycle ----------------------------------------------------------------------

    def regulate_toward_viability(
        self,
        essential_variable_measurements: Mapping[str, float],
        now: datetime | None = None,
    ) -> HomeostaticThrottleDecision:
        """One MAPE-K Plan/Execute step: measure the set, find the binding variable, move the levers."""
        moment = _require_utc_moment(now) if now is not None else datetime.now(UTC)
        margins, unmeasured, unrecognized = self._measure_boundary_margins(
            essential_variable_measurements
        )
        if not margins:
            # Every essential variable is unmeasured. The keeper is blind: it must not relax, and it has
            # no basis on which to tighten further either. It HOLDs whatever it already had.
            decision = self._build_decision(
                moment=moment,
                action=ThrottleAction.HOLD,
                binding=None,
                margins=(),
                outside_names=(),
                unmeasured=unmeasured,
                unrecognized=unrecognized,
                reason=(
                    "no essential variable could be measured "
                    f"({', '.join(unmeasured) or 'none declared'}) — holding the throttle at "
                    f"{self._throttle_level:.3f}; a keeper that cannot see its own state may not relax"
                ),
            )
            return self._record(decision)

        binding = min(margins, key=lambda margin: margin.normalized_margin)
        outside = tuple(margin.variable_name for margin in margins if not margin.is_inside)
        is_within = not outside
        if is_within:
            self._consecutive_outside_cycle_count = 0
            self._consecutive_inside_cycle_count += 1
        else:
            self._consecutive_outside_cycle_count += 1
            self._consecutive_inside_cycle_count = 0

        action, reason = self._choose_action(binding, margins, unmeasured, moment)
        if action is ThrottleAction.TIGHTEN:
            self._throttle_level = _clamp_to_unit_interval(
                self._throttle_level + self._tightening_step_for(binding)
            )
        elif action is ThrottleAction.RELAX:
            self._throttle_level = _clamp_to_unit_interval(
                self._throttle_level - self._calibration.relaxation_step
            )
            self._last_relaxation_at = moment

        decision = self._build_decision(
            moment=moment,
            action=action,
            binding=binding,
            margins=margins,
            outside_names=outside,
            unmeasured=unmeasured,
            unrecognized=unrecognized,
            reason=reason,
        )
        if action is not ThrottleAction.HOLD:
            LOGGER.info(
                "setpoint keeper %s: throttle %.3f, binding %s (margin %+.4f), scan x%.3f breadth x%.3f "
                "llm x%.3f",
                action.value, decision.throttle_level, decision.binding_variable_name,
                decision.binding_variable_margin, decision.scan_interval_multiplier,
                decision.universe_breadth_multiplier, decision.llm_call_rate_multiplier,
            )
        return self._record(decision)

    def regulate_from_readings(
        self,
        collector_measurements: Mapping[str, float],
        service_measurements: Mapping[str, float] | None = None,
        now: datetime | None = None,
    ) -> HomeostaticThrottleDecision:
        """Convenience wiring: merge the collector's host readings with the service's loop metrics.

        `collector_measurements` is `OrganismTelemetryCollection.essential_variable_measurements()`;
        `service_measurements` carries `scan_cycle_duration_seconds` / `llm_calls_per_minute`, which only
        the running loop can know.
        """
        merged: dict[str, float] = dict(collector_measurements)
        overlapping = set(merged) & set(service_measurements or {})
        if overlapping:
            raise ValueError(
                f"the collector and the service both supplied {sorted(overlapping)} — the keeper will "
                f"not silently pick one measurement over the other"
            )
        merged.update(service_measurements or {})
        return self.regulate_toward_viability(merged, now)

    def reset_to_nominal(self) -> None:
        """Drop the throttle to nominal — for a supervised restart, never as part of the control law."""
        self._throttle_level = 0.0
        self._last_relaxation_at = None
        self._consecutive_outside_cycle_count = 0
        self._consecutive_inside_cycle_count = 0

    # -- internals ---------------------------------------------------------------------------------

    def _measure_boundary_margins(
        self, measurements: Mapping[str, float]
    ) -> tuple[tuple[EssentialVariableMargin, ...], tuple[str, ...], tuple[str, ...]]:
        margins: list[EssentialVariableMargin] = []
        unmeasured: list[str] = []
        for interval in self._viability_set.intervals:
            if interval.variable_name not in measurements:
                unmeasured.append(interval.variable_name)
                continue
            raw_value = measurements[interval.variable_name]
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                LOGGER.warning(
                    "essential variable %s carried a non-numeric measurement (%r) — treated as "
                    "UNMEASURED rather than coerced",
                    interval.variable_name, raw_value,
                )
                unmeasured.append(interval.variable_name)
                continue
            if not math.isfinite(value):
                LOGGER.warning(
                    "essential variable %s measured as %r — a non-finite reading is not an observation, "
                    "so it is treated as UNMEASURED (relaxation stays blocked)",
                    interval.variable_name, value,
                )
                unmeasured.append(interval.variable_name)
                continue
            margins.append(
                EssentialVariableMargin(
                    variable_name=interval.variable_name,
                    measured_value=value,
                    normalized_margin=interval.normalized_boundary_margin(value),
                    is_inside=interval.contains(value),
                    measurement_unit=interval.measurement_unit,
                    bounds_description=interval.describe_bounds(),
                )
            )
        unrecognized = tuple(
            sorted(set(measurements) - set(self._viability_set.variable_names))
        )
        if unrecognized:
            LOGGER.warning(
                "measurements supplied for variables the viability set does not declare (ignored, but "
                "surfaced on the decision): %s",
                ", ".join(unrecognized),
            )
        # Worst first: the binding variable heads the list on every decision object.
        margins.sort(key=lambda margin: margin.normalized_margin)
        return tuple(margins), tuple(unmeasured), unrecognized

    def _choose_action(
        self,
        binding: EssentialVariableMargin,
        margins: Sequence[EssentialVariableMargin],
        unmeasured: Sequence[str],
        moment: datetime,
    ) -> tuple[ThrottleAction, str]:
        settings = self._calibration
        outside_count = sum(1 for margin in margins if not margin.is_inside)
        if binding.normalized_margin < settings.tighten_margin_threshold:
            if self._throttle_level >= 1.0:
                return (
                    ThrottleAction.HOLD,
                    f"{binding.variable_name} is outside the viability set (margin "
                    f"{binding.normalized_margin:+.4f}) but the throttle is already at maximum — there "
                    f"is no tightening left; {outside_count} variable(s) outside",
                )
            return (
                ThrottleAction.TIGHTEN,
                f"{binding.variable_name} = {binding.measured_value:g} "
                f"{binding.measurement_unit} is OUTSIDE its viability interval "
                f"{binding.bounds_description} (margin {binding.normalized_margin:+.4f}); it is the "
                f"variable nearest/furthest past its boundary of the {len(margins)} measured, and "
                f"{outside_count} variable(s) are outside in total",
            )
        if binding.normalized_margin < settings.relax_margin_threshold:
            return (
                ThrottleAction.HOLD,
                f"{binding.variable_name} sits inside the viability set but within the hysteresis "
                f"deadband [{settings.tighten_margin_threshold:.2f}, "
                f"{settings.relax_margin_threshold:.2f}) at margin "
                f"{binding.normalized_margin:+.4f} — holding the throttle at {self._throttle_level:.3f} "
                f"rather than chattering across the boundary",
            )
        if self._throttle_level <= 0.0:
            return (
                ThrottleAction.HOLD,
                f"every measured essential variable is inside the viability set (binding "
                f"{binding.variable_name} at margin {binding.normalized_margin:+.4f}) and the throttle "
                f"is already nominal",
            )
        if unmeasured:
            return (
                ThrottleAction.HOLD,
                f"the measured variables are comfortably inside, but {len(unmeasured)} essential "
                f"variable(s) are UNMEASURED ({', '.join(unmeasured)}) — a keeper that cannot see its "
                f"whole state may not relax (tighten-only by default)",
            )
        if self._last_relaxation_at is not None:
            seconds_since_relaxation = (moment - self._last_relaxation_at).total_seconds()
            if seconds_since_relaxation < settings.minimum_relaxation_interval_seconds:
                return (
                    ThrottleAction.HOLD,
                    f"relaxation dwell time not yet elapsed ({seconds_since_relaxation:.1f}s of "
                    f"{settings.minimum_relaxation_interval_seconds:.1f}s) — recovery toward nominal is "
                    f"deliberately gradual",
                )
        return (
            ThrottleAction.RELAX,
            f"every measured essential variable is comfortably inside the viability set (binding "
            f"{binding.variable_name} at margin {binding.normalized_margin:+.4f}, beyond the "
            f"{settings.relax_margin_threshold:.2f} relaxation threshold) — stepping the throttle back "
            f"toward nominal by {settings.relaxation_step:.3f}",
        )

    def _tightening_step_for(self, binding: EssentialVariableMargin) -> float:
        """Ashby's slow loop: the further outside, the harder the re-parameterization."""
        excursion = min(abs(binding.normalized_margin), self._calibration.excursion_response_cap)
        return self._calibration.tightening_step * (1.0 + excursion)

    def _effective_lever_emphasis(
        self, binding: EssentialVariableMargin | None, margins: Sequence[EssentialVariableMargin]
    ) -> ThrottleLeverEmphasis:
        """Which levers this state licenses: the binding variable's, unioned over everything outside.

        Taking the per-lever MAX (rather than the binding variable's emphasis alone) is what makes the
        "all variables outside simultaneously" case pull every relevant actuator — the joint constraint
        of research/169 §4.3, as opposed to six loops each acting on its own.
        """
        if binding is None:
            return ThrottleLeverEmphasis(scan_interval=1.0, universe_breadth=1.0, llm_call_rate=1.0)
        emphasis = self._emphasis_for(binding.variable_name)
        for margin in margins:
            if not margin.is_inside and margin.variable_name != binding.variable_name:
                emphasis = emphasis.combined_with(self._emphasis_for(margin.variable_name))
        return emphasis

    def _emphasis_for(self, variable_name: str) -> ThrottleLeverEmphasis:
        interval = self._viability_set.interval_for(variable_name)
        if interval is None:  # pragma: no cover - margins are only built from declared intervals
            raise ValueError(f"{variable_name} is not a declared essential variable")
        return interval.lever_emphasis

    def _build_decision(
        self,
        moment: datetime,
        action: ThrottleAction,
        binding: EssentialVariableMargin | None,
        margins: Sequence[EssentialVariableMargin],
        outside_names: Sequence[str],
        unmeasured: Sequence[str],
        unrecognized: Sequence[str],
        reason: str,
    ) -> HomeostaticThrottleDecision:
        settings = self._calibration
        emphasis = self._effective_lever_emphasis(binding, margins)
        level = self._throttle_level
        scan_multiplier = 1.0 + level * emphasis.scan_interval * (
            settings.maximum_scan_interval_multiplier - 1.0
        )
        breadth_multiplier = 1.0 - level * emphasis.universe_breadth * (
            1.0 - settings.minimum_universe_breadth_multiplier
        )
        llm_multiplier = 1.0 - level * emphasis.llm_call_rate * (
            1.0 - settings.minimum_llm_call_rate_multiplier
        )
        return HomeostaticThrottleDecision(
            decided_at=moment,
            action=action,
            throttle_level=_clamp_to_unit_interval(level),
            # Structural tighten-only clamps: no arithmetic path can make the organism do MORE work.
            scan_interval_multiplier=max(
                1.0, min(scan_multiplier, settings.maximum_scan_interval_multiplier)
            ),
            universe_breadth_multiplier=min(
                1.0, max(breadth_multiplier, settings.minimum_universe_breadth_multiplier)
            ),
            llm_call_rate_multiplier=min(
                1.0, max(llm_multiplier, settings.minimum_llm_call_rate_multiplier)
            ),
            binding_variable_name=binding.variable_name if binding is not None else "",
            binding_variable_margin=binding.normalized_margin if binding is not None else math.inf,
            is_within_viability_set=not outside_names,
            reason=reason,
            variable_margins=tuple(margins),
            outside_variable_names=tuple(outside_names),
            unmeasured_variable_names=tuple(unmeasured),
            unrecognized_variable_names=tuple(unrecognized),
        )

    def _record(self, decision: HomeostaticThrottleDecision) -> HomeostaticThrottleDecision:
        self._decision_history.append(decision)
        return decision


def build_default_setpoint_keeper(
    extra_intervals: Iterable[EssentialVariableInterval] = (),
    calibration: SetpointKeeperCalibration | None = None,
) -> HomeostaticSetpointKeeper:
    """The production keeper. `extra_intervals` exists for the hermetic test seam (Rule J)."""
    return HomeostaticSetpointKeeper(
        viability_set=ViabilitySet(
            intervals=DEFAULT_ESSENTIAL_VARIABLE_INTERVALS + tuple(extra_intervals)
        ),
        calibration=calibration,
    )


def tighten_viability_interval(
    interval: EssentialVariableInterval, upper_bound: float
) -> EssentialVariableInterval:
    """A copy with a stricter upper bound — the operator-facing way to narrow the viability set."""
    if upper_bound >= interval.upper_bound:
        raise ValueError(
            f"{interval.variable_name}: tighten_viability_interval must LOWER the upper bound "
            f"({upper_bound} is not below {interval.upper_bound})"
        )
    return replace(interval, upper_bound=upper_bound)


def _require_utc_moment(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            f"the setpoint keeper requires a timezone-aware (UTC-explicit) moment; got {moment!r}"
        )
    return moment.astimezone(UTC)


def _clamp_to_unit_interval(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"cannot clamp non-finite value {value!r} into [0, 1]")
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value
