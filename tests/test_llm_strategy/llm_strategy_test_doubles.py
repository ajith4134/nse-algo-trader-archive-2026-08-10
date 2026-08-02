"""Hermetic test doubles for Layer 11 (Rule J): fakes that live ONLY under tests/, so the
injected fake is structurally unable to reach a real network call or a real LLM. Production
never imports this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.llm_strategy.strategy_llm_client import (
    LlmPoolStatus,
    StrategyLlmRequest,
    StrategyLlmResponse,
)
from nse_algo_trader.memory_reflection.experience_memory import (
    CalibrationBoardRow,
    MarketRegimeCalibration,
    MechanismReliability,
    OutcomeSequenceDependence,
)


@dataclass
class ScriptedLlmProvider:
    """A single provider whose behaviour is scripted: each call pops the next action, either
    an exception to raise (rate-limit / unavailable) or a `StrategyLlmResponse` to return."""

    provider_name: str
    model_name: str
    actions: list  # each item: an Exception instance OR a dict of parsed_output
    calls: list = field(default_factory=list)

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        self.calls.append(request)
        action = self.actions.pop(0) if self.actions else {}
        if isinstance(action, Exception):
            raise action
        return StrategyLlmResponse(
            parsed_output=dict(action),
            served_by_provider=self.provider_name,
            served_by_model=self.model_name,
            raw_text="",
        )


@dataclass
class CapturingFakeLlmClient:
    """A `StrategyLlmClient` that captures the request and returns a canned reflection — lets
    the analyst test assert the prompt literally contains the real memory facts."""

    canned_output: dict
    captured_request: StrategyLlmRequest | None = None

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        self.captured_request = request
        return StrategyLlmResponse(
            parsed_output=dict(self.canned_output),
            served_by_provider="fake-provider",
            served_by_model="fake-model",
            raw_text="",
        )

    def describe_pool(self) -> LlmPoolStatus:
        return LlmPoolStatus()


@dataclass
class RoleScriptedFakeLlmClient:
    """A `StrategyLlmClient` that picks its parsed_output by `request.purpose` — so the three
    debate roles (`thesis_debate_bull/bear/risk_officer`) each get a distinct soundness — and
    records EVERY request for prompt assertions. `fail_with`, when set, raises on every call
    (drives the pool-exhaustion path). Unknown purposes fall back to `default_output`."""

    output_by_purpose: dict
    default_output: dict = field(default_factory=dict)
    captured_requests: list = field(default_factory=list)
    fail_with: Exception | None = None

    def generate_structured(self, request: StrategyLlmRequest) -> StrategyLlmResponse:
        self.captured_requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        output = self.output_by_purpose.get(request.purpose, self.default_output)
        return StrategyLlmResponse(
            parsed_output=dict(output),
            served_by_provider="fake-provider",
            served_by_model="fake-model",
            raw_text="",
        )

    def describe_pool(self) -> LlmPoolStatus:
        return LlmPoolStatus()


@dataclass
class InMemoryExperienceMemoryStub:
    """A minimal `ExperienceMemory` returning canned read-model rows — enough to drive the
    analyst deterministically. The REAL SQLite memory is exercised by the real-data verify
    script (Rule F); this stub keeps the unit test fast and hermetic."""

    total_experiences: int = 200
    regime_counts: dict = field(
        default_factory=lambda: {"trending": 90, "range_bound": 70, "indecisive": 40}
    )
    board_rows: list = field(
        default_factory=lambda: [
            CalibrationBoardRow(
                strategy_tag="orb", mechanism_name="opening_range_breakout",
                experiment_count=120, predicted_win_rate=0.62, actual_win_rate=0.41,
                mean_brier=0.29, mean_return_fraction=-0.004, mean_log_score=1.2,
            ),
        ]
    )
    regime_calibration: list = field(
        default_factory=lambda: [
            MarketRegimeCalibration(
                market_regime="trending", experiment_count=90, hit_rate=0.48,
                mean_brier=0.26, mean_return_fraction=0.002,
            ),
        ]
    )
    recent: list = field(
        default_factory=lambda: [
            {"actual_outcome": "win"}, {"actual_outcome": "loss"},
            {"actual_outcome": "loss"},
        ]
    )
    # Multi-hop cluster reads (slice 3): one mechanism whose outcomes cluster in time, plus a
    # Murphy reliability diagnosis — enough to drive the causal-cluster analyst deterministically.
    sequence_dependence: list = field(
        default_factory=lambda: [
            OutcomeSequenceDependence(
                strategy_tag="orb", mechanism_name="opening_range_breakout",
                experiment_count=120, overall_win_rate=0.41,
                post_win_win_rate=0.55, post_loss_win_rate=0.28,
                dependence_gap=0.27, clusters=True,
            )
        ]
    )
    reliability: list = field(
        default_factory=lambda: [
            MechanismReliability(
                strategy_tag="orb", mechanism_name="opening_range_breakout",
                experiment_count=120, reliability=0.05, resolution=0.02,
                uncertainty=0.24, diagnosis="biased but discriminates — recalibratable",
            )
        ]
    )

    def experiment_count(self) -> int:
        return self.total_experiences

    def outcome_sequence_dependence(self, minimum_experiments=12):
        return list(self.sequence_dependence)

    def reliability_decomposition(self, minimum_experiments=12):
        return list(self.reliability)

    def experiment_count_by_market_regime(self) -> dict:
        return dict(self.regime_counts)

    def calibration_board(self, minimum_experiments=1, limit=20, **_):
        return list(self.board_rows)[:limit]

    def calibration_by_market_regime(self, strategy_tag=None, minimum_experiments=1):
        return list(self.regime_calibration)

    def recent_closed_experiences(self, limit=50):
        return list(self.recent)[:limit]
