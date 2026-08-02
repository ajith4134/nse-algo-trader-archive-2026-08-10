"""I/O contracts for the capital-allocation optimizer (research/163 §2). PURE — no I/O, no solver.

`AllocationCandidate` is one entry candidate at a decision tick (the optimiser allocates a risk-budget
weight across the SET of them). `AllocationResult` is the solved allocation the entry path consumes:
per-candidate weights → capital → integer lots, plus the objective mode used, solver status, the
portfolio's tail-risk/vol, cardinality, turnover, scenario sufficiency, and the earned-gate verdict.
Sign conventions (Rule O.5): weights are fractions in [0, 1]; `expected_edge_mu` is a per-unit return
fraction (positive = favourable); `per_unit_risk` and all risk measures (CVaR/vol) are POSITIVE loss
magnitudes; capital is in the account currency (₹).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The three segments (Rule L). Used for per-segment caps + the segment-budget scope level.
SEGMENT_INDEX_OPTION = "index_option"
SEGMENT_STOCK_OPTION = "stock_option"
SEGMENT_CASH = "cash_equity"
VALID_SEGMENTS = (SEGMENT_INDEX_OPTION, SEGMENT_STOCK_OPTION, SEGMENT_CASH)


@dataclass(frozen=True)
class AllocationCandidate:
    """One entry candidate competing for the risk budget at a decision tick.

    `expected_edge_mu` is the per-unit expected return (win_prob·R:R − (1−win_prob)); it comes from the
    win-probability engine and is 0.0 when that engine is un-earned (so the allocator degrades to a pure
    risk model, not a garbage return signal). `pnl_scenario_returns` is this candidate's historical
    per-trade `realized_return_fraction` samples from experience_memory — the empirical CVaR scenarios;
    empty/thin → the engine falls back to a parametric risk model (research/163 §4).
    """

    candidate_id: str
    segment: str                     # one of VALID_SEGMENTS
    underlying: str
    direction: str                   # long | short (sign of the position)
    instrument_kind: str             # cash_equity | index_option | stock_option
    expected_edge_mu: float          # per-unit expected return fraction (may be 0.0 when no edge)
    per_unit_risk: float             # positive loss magnitude per unit (stop-distance / structural max-loss)
    entry_price: float               # per-unit price (₹) — for capital→lots conversion
    lot_or_tick_size: int            # tradeable increment (option lot size; 1 for cash shares)
    est_margin_per_unit: float       # margin ₹ consumed per unit/lot (for the margin budget)
    pnl_scenario_returns: tuple[float, ...] = ()  # historical realized_return_fraction samples

    def __post_init__(self) -> None:
        if self.segment not in VALID_SEGMENTS:
            raise ValueError(f"unknown segment {self.segment!r}; expected one of {VALID_SEGMENTS}")
        if self.per_unit_risk < 0.0:
            raise ValueError(f"per_unit_risk must be a positive loss magnitude, got {self.per_unit_risk}")
        if self.lot_or_tick_size <= 0:
            raise ValueError(f"lot_or_tick_size must be positive, got {self.lot_or_tick_size}")

    @property
    def direction_sign(self) -> int:
        """+1 for a long, −1 for a short — for the NET-exposure constraint."""
        return -1 if str(self.direction).lower().startswith("short") else 1


@dataclass(frozen=True)
class AllocationResult:
    """The solved allocation the entry path consumes (research/163 §2).

    `weights`/`capital`/`lots` are keyed by candidate_id. `is_earned` gates whether the allocation ACTS
    (moves real size) or is advisory-only (identity) — an un-earned engine never moves a trade (Rule P.4).
    `fell_back` is True when thin scenarios forced the parametric Mean-Variance mode. All risk measures
    (`portfolio_cvar`, `portfolio_vol`) are positive loss magnitudes.
    """

    weights: dict[str, float]
    capital: dict[str, float]
    lots: dict[str, int]
    objective_mode_used: str         # mean_cvar | mean_variance | risk_parity | enhanced_indexing
    solver_status: str               # optimal | optimal_inaccurate | infeasible | error | trivial
    portfolio_cvar: float            # expected tail (α) loss: positive = expected loss; <0 = even the tail profits
    portfolio_vol: float             # positive std-dev of portfolio return
    active_count: int                # positions with a non-trivial weight (cardinality realised)
    turnover: float                  # ‖w − w_prev‖₁
    scenario_count: int              # min per-candidate real sample count (data sufficiency)
    fell_back: bool                  # True → thin scenarios forced parametric MV
    is_earned: bool                  # True → the allocation ACTS; False → advisory identity
    diagnostics: dict = field(default_factory=dict)

    @property
    def acted(self) -> bool:
        """The allocation actually moved sizing (earned AND a real optimal solve)."""
        return self.is_earned and self.solver_status in ("optimal", "optimal_inaccurate")

    def size_multiplier_for(self, candidate_id: str, naive_equal_weight: float) -> float:
        """Per-candidate size multiplier vs the naive equal-weight baseline — the decision-grade output
        the entry site applies. Identity (1.0) when un-earned or the candidate got no allocation basis."""
        if not self.acted or naive_equal_weight <= 0.0:
            return 1.0
        return self.weights.get(candidate_id, 0.0) / naive_equal_weight
