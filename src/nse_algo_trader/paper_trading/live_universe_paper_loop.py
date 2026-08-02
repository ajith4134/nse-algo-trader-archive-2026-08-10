"""The universe-wide live paper loop — positions open and stay OPEN.

Unlike the replay engine (`opening_range_breakout_paper_engine`), which
force-closes every trade at the last bar because the session is already
over, this loop runs *during* the open session: it opens positions and
holds them OPEN across scan passes, managing each against the live price
until its stop/target hits — or until 15:15, when Layer 8 flattens
everything (safe-ordered, never a naked leg). That is why the dashboard
was showing no "open" trades: nothing was ever held open. (docs/research/38)

One scan pass (`run_live_universe_scan_pass`) does, in order:
1. Price the whole universe (one batched-LTP call via the live feed).
2. Manage every open position against its live price -> exit on stop/target.
3. Seed a bounded batch of not-yet-seeded cash instruments: fetch today's
   bars, run the real ORB detector, and either open a held position or —
   if the breakout already stopped/targeted earlier today — record it as a
   completed trade (the per-instrument replay-to-live catch-up).
4. From 15:15 IST, square off every open position through Layer 8.

Paper only: fills are simulated, capital is virtual. The live/real-money
consumer is a separate, market-gated path (PLAN §1.4) not built here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from nse_algo_trader.broker_oms import OrderSide, SimulatedBrokerClient
from nse_algo_trader.indicators.average_directional_index import (
    compute_average_directional_index,
)
from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.opening_range_breakout_paper_engine import (
    PaperSessionOutcome,
)
from nse_algo_trader.paper_trading.fill_slippage_model import (
    FillSlippageConfig,
    make_slippage_fill_adjuster,
    slipped_fill_price,
)
from nse_algo_trader.paper_trading.indian_trading_cost_model import (
    estimate_round_trip_cost,
)
from nse_algo_trader.paper_trading.paper_trading_ledger import PaperTradingLedger
from nse_algo_trader.paper_trading.zero_dte_risk_state import ZeroDteRiskState
from nse_algo_trader.paper_trading.position_excursion_tracker import (
    PositionProfitExcursion,
)
from nse_algo_trader.paper_trading.profit_trail_lock_engine import (
    ProfitTrailState,
    trail_exit_triggered,
    update_profit_trail,
)
from nse_algo_trader.paper_trading.prediction_lab import (
    PredictionTableScoreboard,
    build_orb_prediction_record,
    grade_prediction,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    TradePredictionRecord,
)
from nse_algo_trader.risk_management import (
    RiskBudgetConfig,
    evaluate_opening_range_breakout_signal,
)
from nse_algo_trader.session_management import (
    IntradaySquareOffSchedule,
    OpenPositionLeg,
    execute_intraday_square_off,
)
from nse_algo_trader.strategy_engine import (
    OpeningRangeBreakoutConfig,
    SignalDirection,
    detect_opening_range_breakout,
)
from nse_algo_trader.universe_registry import Instrument

_FORCED_SQUARE_OFF_TIME_IST = time(15, 15)
# Shadow-arm recovery (slice 4): 1 in N vetoed entries opens as a probe.
_SHADOW_PROBE_EVERY = 8
# Layer 11 slice 2c (research/101): debate risk_score thresholds for the entry gate.
# At/above DEFER a high-risk thesis is fully deferred; at/above SIZE_DOWN it opens at
# SIZE_DOWN_MULTIPLIER of the risk-approved quantity. Only applied once the signal is EARNED.
_DEBATE_RISK_DEFER_THRESHOLD = 0.75
_DEBATE_RISK_SIZE_DOWN_THRESHOLD = 0.55
_DEBATE_RISK_SIZE_DOWN_MULTIPLIER = 0.5


def _signal_reward_risk(signal) -> float:
    """Reward:risk of a breakout signal = |target − entry| / |entry − stop| (Trunk IX win-prob edge input)."""
    risk = abs(signal.breakout_close_price - signal.stop_loss_price)
    if risk <= 0:
        return 0.0
    return abs(signal.target_price - signal.breakout_close_price) / risk


@dataclass
class OpenPaperPosition:
    instrument: Instrument
    direction: SignalDirection
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    opened_at: datetime
    strategy_tag: str
    prediction_record: TradePredictionRecord
    #: B23: how far into profit / loss this trade has actually been, and the ratcheting profit lock.
    excursion: PositionProfitExcursion = field(default_factory=PositionProfitExcursion)
    profit_trail: ProfitTrailState = field(default_factory=ProfitTrailState)

    def unrealised_profit_at(self, price: float) -> float:
        """Unrealised P&L in rupees. Sign convention lives HERE, once, so everything downstream
        (excursion, trail) can work in profit space with no direction branch."""
        direction_sign = 1.0 if self.direction is SignalDirection.LONG else -1.0
        return (price - self.entry_price) * self.quantity * direction_sign

    @property
    def initial_risk_amount(self) -> float:
        """1R in rupees — the entry→stop distance across the whole position."""
        return abs(self.entry_price - self.stop_loss_price) * self.quantity

    @property
    def entry_notional(self) -> float:
        return abs(self.entry_price) * self.quantity

    def observe_price_for_excursion(self, price: float) -> None:
        self.excursion.observe_unrealised_profit(self.unrealised_profit_at(price))

    def advance_profit_trail(self) -> None:
        self.profit_trail = update_profit_trail(
            self.profit_trail,
            peak_profit=self.excursion.maximum_favourable_profit,
            initial_risk_amount=self.initial_risk_amount,
            entry_notional=self.entry_notional,
        )

    def has_hit_stop_or_target(self, price: float) -> PaperSessionOutcome | None:
        if self.direction is SignalDirection.LONG:
            if price <= self.stop_loss_price:
                return PaperSessionOutcome.EXITED_STOP
            if price >= self.target_price:
                return PaperSessionOutcome.EXITED_TARGET
        else:
            if price >= self.stop_loss_price:
                return PaperSessionOutcome.EXITED_STOP
            if price <= self.target_price:
                return PaperSessionOutcome.EXITED_TARGET
        return None


@dataclass
class ClosedPaperTrade:
    instrument: Instrument
    direction: SignalDirection
    quantity: int
    entry_price: float
    exit_price: float
    realized_pnl: float
    outcome: PaperSessionOutcome
    opened_at: datetime
    closed_at: datetime
    #: B23: the best and worst this trade ever looked, in rupees. Persisted (not just displayed)
    #: because `maximum_favourable_profit` far above `realized_pnl`, repeatedly, is the EVIDENCE
    #: that targets are capping runs — and `maximum_adverse_profit` near zero on winners is the
    #: evidence that stops are wider than they need to be. Without these the exit parameters can
    #: only ever be guessed at.
    maximum_favourable_profit: float = 0.0
    maximum_adverse_profit: float = 0.0
    exited_on_profit_trail: bool = False
    #: B28: real round-trip cost in rupees (brokerage + STT + exchange + SEBI + GST + stamp).
    #: `realized_pnl` is GROSS; net P&L is `realized_pnl - total_fees`. Keeping them separate makes
    #: it impossible to silently report a gross number as if it were net.
    total_fees: float = 0.0
    #: B33: the §9 table this trade opened under (confident_win | confident_loss | uncertain), so a
    #: confident_loss learning probe is never re-mixed into the bot's real P&L downstream.
    assigned_table: str = "uncertain"


@dataclass
class LiveUniversePaperState:
    """All mutable state of the loop, so a scan pass is a pure step over it."""

    ledger: PaperTradingLedger
    scoreboard: PredictionTableScoreboard
    # Broker carries the slippage model so every fill routed through it
    # (directional options, the L8 square-off) pays the spread; the cash path
    # records straight to the ledger and applies `fill_slippage_config`.
    simulated_broker: SimulatedBrokerClient = field(
        default_factory=lambda: SimulatedBrokerClient(
            fill_price_adjuster=make_slippage_fill_adjuster()
        )
    )
    fill_slippage_config: FillSlippageConfig = field(default_factory=FillSlippageConfig)
    # §53 slice 5c-ii: per-token average daily quantity (real ADV) so fills pay
    # size-dependent market impact. Empty (default) → spread-only fills (no regression);
    # the service populates it from real stored bar volumes.
    average_daily_quantity_by_token: dict = field(default_factory=dict)
    open_positions: dict[int, OpenPaperPosition] = field(default_factory=dict)
    closed_trades: list[ClosedPaperTrade] = field(default_factory=list)
    # Closed §9 experiments awaiting Layer-10 recording: (graded, trade, kind)
    # tuples the dashboard service drains into ExperienceMemory (Rule G).
    closed_experiment_events: list = field(default_factory=list)
    # Antibody (Layer 10 slice 3): mechanism names the memory has statistically
    # refuted — new entries on these are vetoed. Set by the service each pass;
    # the loop never imports Layer 10 (just reads this plain set).
    vetoed_mechanisms: set = field(default_factory=set)
    vetoed_entry_count: int = 0
    # Shadow-arm recovery (slice 4): a vetoed mechanism still opens a small
    # deterministic trickle of probe trades so fresh evidence keeps flowing —
    # the recency-window veto can then lift if the mechanism recovers.
    shadow_probe_counter: dict = field(default_factory=dict)
    shadow_entry_count: int = 0
    seeded_cash_tokens: set[int] = field(default_factory=set)
    # Opponent ledger (Layer 10 §10, slice 1): today's participant-positioning
    # reading (an OpponentLedgerReading or None). Set by the service each day;
    # the loop reads it only to DEFER new entries that institutions oppose while
    # retail is trapped on that side — a multi-day confirmation input, never a
    # trigger. Existing positions are never touched.
    market_positioning_bias: object = None
    positioning_deferred_count: int = 0
    # research/51: per-mechanism additive win-probability bias offset learned by
    # the memory (set by the service). Applied to every prediction record before
    # recording — empty at cold start (identity), so it is safe unconditionally.
    recalibration_offset_by_mechanism: dict = field(default_factory=dict)
    recalibrated_entry_count: int = 0
    # Information-diet accounting (§10, research/52): every candidate entry that
    # gets a prediction record is one "decision considered" — the denominator for
    # each information source's influence share.
    entry_decisions_considered: int = 0
    # Layer 11 slice 2c (research/101): the debate risk_score per mechanism (set by
    # the service each day) + whether that signal has EARNED calibration (set from
    # the prequential harness). The gate below sizes-down / defers high-risk entries
    # ONLY once earned — advisory (identity) until then, so an uncalibrated LLM
    # signal never moves a real trade. Empty map / not-earned = identity (safe).
    debate_risk_score_by_mechanism: dict = field(default_factory=dict)
    debate_risk_calibration_earned: bool = False
    debate_risk_deferred_count: int = 0
    debate_risk_sized_down_count: int = 0
    # Trunk II SENSES S7 (research/147): per-symbol news-EVENT risk in [0,1] (a fresh, reliable
    # filing/news event on the symbol), set by the service each pass, + whether that signal has EARNED
    # calibration. The gate sizes-down / defers entries on a symbol with a fresh material event ONLY
    # once earned — identity (advisory) until then, so an uncalibrated news signal never moves a real
    # trade. Empty map / not-earned = identity (safe). This is the news sense's PRIMARY consumer.
    news_event_risk_by_symbol: dict = field(default_factory=dict)
    news_event_calibration_earned: bool = False
    news_event_deferred_count: int = 0
    news_event_sized_down_count: int = 0
    # Trunk II SENSES index-level gate (research/151): per-index-underlying S2 news S/R level VALUES
    # (set by the service), + earned flag. An index-option entry within a proximity band of a fresh
    # reliable level is sized-down/deferred (reversal caution). Identity (advisory) until earned.
    index_level_values_by_underlying: dict = field(default_factory=dict)
    index_level_calibration_earned: bool = False
    index_level_deferred_count: int = 0
    index_level_sized_down_count: int = 0
    # Trunk IX PREDICTIVE-CORE — ML win-probability engine (research/156). The service sets a callable
    # (prediction_record, direction, instrument_kind, reward_risk, now) -> size multiplier in [floor,1];
    # identity (None → 1.0) until the trained model is performance-earned vs baseline. Counts adjustments.
    win_probability_size_multiplier_fn: object = None
    win_probability_sized_count: int = 0

    def win_probability_size_multiplier(self, prediction_record, direction, instrument_kind,
                                        reward_risk, now) -> float:
        """ML win-probability size lever: identity when no earned model, else a fractional-Kelly edge
        multiplier from the calibrated P(win). Never raises (a model hiccup must not break the loop)."""
        fn = self.win_probability_size_multiplier_fn
        if fn is None:
            return 1.0
        try:
            multiplier = float(fn(prediction_record, direction, instrument_kind, reward_risk, now))
        except Exception:
            return 1.0
        if multiplier < 1.0:
            self.win_probability_sized_count += 1
        return multiplier
    # Trunk III WILL — Capital-Allocation Optimizer (research/163). The service runs the CVXPY optimizer
    # each cadence over the live candidate set and caches the AllocationResult here; the entry sites look
    # up their candidate's size lever. Advisory (size-DOWN-only, clamped ≤1.0) until the engine EARNS the
    # right to act (enough real trading days); un-earned/absent → identity (1.0). The joint up-sizing
    # reallocation path lifts the ceiling once earned + risk-checked (Rule K primary-consumer item).
    capital_allocation_result: object = None       # the latest AllocationResult (set by the service)
    capital_allocation_sized_count: int = 0

    def capital_allocation_size_multiplier(self, candidate_id: str) -> float:
        """Per-candidate size lever from the latest joint allocation: identity until the optimizer is
        earned, else the (size-down-only) weight-vs-equal-weight ratio. The naive equal-weight baseline
        is read from the result itself, so entry sites need not know the batch size. Never raises."""
        result = self.capital_allocation_result
        if result is None:
            return 1.0
        try:
            if not getattr(result, "acted", False):
                return 1.0
            naive_equal_weight = float(result.diagnostics.get("naive_equal_weight", 0.0))
            multiplier = float(result.size_multiplier_for(candidate_id, naive_equal_weight))
        except Exception:
            return 1.0
        multiplier = max(0.0, min(multiplier, 1.0))   # size-DOWN-only for the safe advisory rollout
        if multiplier < 1.0:
            self.capital_allocation_sized_count += 1
        return multiplier
    # Trunk IX PREDICTIVE-CORE — World-Model Planning engine (research/167). The service computes the
    # current market-state planning verdict each cadence (per direction) and caches it here; the entry
    # sites apply it as a size-DOWN/veto lever. Abstains (identity 1.0) unless the world-model is
    # confident for the current state (κ≥τ, discounted by ensemble disagreement, killed by a surprise
    # spike); a confident model that expects the entry to underperform holding vetoes it (multiplier 0).
    world_model_verdicts: dict = field(default_factory=dict)   # {"long": verdict, "short": verdict}
    world_model_sized_count: int = 0
    world_model_vetoed_count: int = 0

    def world_model_size_multiplier(self, direction: str) -> float:
        """Size lever from the cached world-model planning verdict for `direction`. Identity when absent
        or the model abstains (untrusted state); ≤1.0 size-down or 0.0 veto when confident. Never raises."""
        key = "long" if str(direction).lower().startswith("long") else "short"
        verdict = self.world_model_verdicts.get(key)
        if verdict is None:
            return 1.0
        try:
            if getattr(verdict, "abstains", True):
                return 1.0
            multiplier = max(0.0, min(float(verdict.size_multiplier), 1.0))
        except Exception:
            return 1.0
        if getattr(verdict, "vetoes", False):
            self.world_model_vetoed_count += 1
        elif multiplier < 1.0:
            self.world_model_sized_count += 1
        return multiplier
    # Trunk VII.6 CONSCIENCE Referee (research/110): the constitution as a HARD pre-order gate.
    # Set by the service; None = permissive no-op (paths/tests without it are unaffected). Blocks
    # any order that violates a structural constitutional article (scope/overnight/naked/routing).
    constitutional_referee: object = None
    constitution_blocked_order_count: int = 0
    # Trunk VII.5 CONSCIENCE corrigibility: the off-switch. When engaged, ALL new orders are
    # blocked (safe interruptibility). Set by the service; None = no-op (never halted).
    corrigibility_switch: object = None
    corrigibility_blocked_order_count: int = 0
    # Trunk VII CONSCIENCE scalable oversight: per-decision oversight-tier counters. A high-stakes +
    # low-confidence decision is beyond autonomous competence → deferred (human_review tier).
    oversight_autonomous_count: int = 0
    oversight_panel_review_count: int = 0
    oversight_human_review_blocked_count: int = 0
    # Trunk VII CONSCIENCE instrumental-convergence limiter: caps the convergent resource-acquisition
    # drive (concurrent-exposure sprawl) + asserts off-switch dominance. Counts blocked orders.
    convergence_limiter_blocked_order_count: int = 0
    # Trunk VII CONSCIENCE power budget: a daily-resetting meter of order throughput (cumulative
    # daily market power) enforced against an explicit budget. Counts blocked orders.
    power_budget_orders_today: int = 0
    power_budget_day: object = None
    power_budget_blocked_order_count: int = 0
    # Trunk VII CONSCIENCE market-data integrity defense: screens the bars a signal is built from for
    # adversarial/corrupt values before they feed the strategy. Counts screened series + blocks.
    market_data_series_screened_count: int = 0
    market_data_integrity_anomaly_count: int = 0
    market_data_integrity_blocked_signal_count: int = 0
    # Trunk VIII SENTIENCE: the Global Workspace's current dominant broadcast (set by the service each
    # pass). When the integrated global focus is a safety/risk concern, entries are TRIMMED (tighten-
    # only; the integrator acting). None = no dominant global context this cycle.
    workspace_broadcast: object = None
    workspace_caution_applied_count: int = 0
    workspace_caution_deferred_count: int = 0
    # B7: option entries refused because the composed size-down levers left under one whole lot.
    # Counted + last-reason kept so a refusal is visible on the dashboard instead of silent.
    option_size_down_stand_aside_count: int = 0
    last_option_size_down_stand_aside_reason: str | None = None
    # B1: cash names the scanner fetched but which returned no intraday bars. They are now marked
    # seeded so the pointer advances; this counter keeps that visible rather than invisible.
    cash_names_attempted_without_bars_count: int = 0

    def apply_recalibration(self, prediction_record):
        """Bias-correct a freshly-built prediction record with the memory-learned
        per-mechanism offset (research/51). Identity at cold start (empty map);
        counts a record whose win-probability actually moved."""
        from nse_algo_trader.paper_trading.prediction_lab.mechanism_recalibration import (  # noqa: E501
            recalibrate_prediction_record,
        )

        self.entry_decisions_considered += 1  # info-diet denominator (§10)
        recalibrated = recalibrate_prediction_record(
            prediction_record, self.recalibration_offset_by_mechanism
        )
        if recalibrated.win_probability != prediction_record.win_probability:
            self.recalibrated_entry_count += 1
        return recalibrated

    #: B18.1b: set by the service to persist daily ATM IV (loop stays free of storage imports —
    #: Rule G wiring lives in the service, and a None recorder makes this a no-op in tests).
    atm_implied_volatility_recorder = None
    atm_implied_volatility_recorded_count: int = 0

    #: B18 step 6: set by the service. None = fall back to the pure regime router, so the loop
    #: behaves exactly as before when the selector is not wired (no silent behaviour change).
    option_arm_selector = None
    option_arm_posterior_store = None
    last_option_arm_selection = None
    option_arm_selection_count: int = 0
    #: B31: entries refused because ADX was not warm enough to measure the regime. Counted so the
    #: abstention is visible rather than looking like "nothing happened".
    entries_skipped_for_unmeasured_regime_count: int = 0

    def select_option_arm(self, underlying_symbol: str, regime_choice, now):
        """Which option arm should trade this underlying now?

        The ADX regime becomes CONTEXT rather than the router — but it still constrains WHICH arms
        are ELIGIBLE, because a defined-risk credit spread genuinely needs a non-trending tape and a
        breakout structure genuinely needs a trending one. The selector chooses within what the
        regime permits; it never invents a structure the tape does not support.

        With no selector wired this returns exactly what the old regime router returned, so the
        integration cannot silently change behaviour before it is switched on.
        """
        from nse_algo_trader.paper_trading.option_credit_spread_live_path import (
            OPTION_ARM_CREDIT_SPREAD,
            OPTION_ARM_DIRECTIONAL,
        )
        from nse_algo_trader.strategy_engine import V1SessionStrategyChoice

        regime_default = (
            OPTION_ARM_DIRECTIONAL
            if regime_choice is V1SessionStrategyChoice.OPENING_RANGE_BREAKOUT
            else OPTION_ARM_CREDIT_SPREAD
            if regime_choice is V1SessionStrategyChoice.CREDIT_SPREAD
            else None
        )
        if self.option_arm_selector is None or regime_default is None:
            return regime_default
        try:
            selection = self.option_arm_selector.select_arm(
                f"{underlying_symbol}|{regime_choice.value}", now
            )
        except Exception as selector_failure:  # noqa: BLE001 — never break a trading pass
            print(
                f"[arm-selector] {underlying_symbol} failed, falling back to the regime router: "
                f"{type(selector_failure).__name__}: {selector_failure}",
                flush=True,
            )
            return regime_default
        self.last_option_arm_selection = selection
        self.option_arm_selection_count += 1
        return selection.chosen_arm

    def record_option_arm_trade_opened(
        self, trade_id: str, arm_name: str, underlying_symbol: str, regime_value: str, now
    ) -> None:
        """Log which arm/cell owns a freshly-opened option trade. Never blocks the pass."""
        if self.option_arm_posterior_store is None:
            return
        try:
            self.option_arm_posterior_store.record_pending_trade(
                trade_id, arm_name, f"{underlying_symbol}|{regime_value}", now
            )
        except Exception as store_failure:  # noqa: BLE001
            print(f"[arm-selector] pending-write failed: {store_failure!r}", flush=True)

    def resolve_option_arm_trade_closed(
        self, trade_id: str, net_profit_after_costs: float, closed_at
    ) -> None:
        """Feed a closed trade's COST-NET, tail-aware reward back to the arm that opened it."""
        if self.option_arm_posterior_store is None:
            return
        from nse_algo_trader.paper_trading.adaptive_arm_selector import tail_aware_reward

        try:
            self.option_arm_posterior_store.resolve_pending_trade(
                trade_id, tail_aware_reward(net_profit_after_costs), closed_at
            )
        except Exception as store_failure:  # noqa: BLE001
            print(f"[arm-selector] reward-write failed: {store_failure!r}", flush=True)

    def record_daily_atm_implied_volatility(
        self, underlying_symbol: str, trade_date, implied_volatility
    ) -> None:
        """Persist one underlying's ATM IV for today, if a recorder is wired and the IV is usable.

        Never raises: an IV-history write must not break a trading pass (Rule O.3). A failure is
        counted rather than swallowed silently.
        """
        if self.atm_implied_volatility_recorder is None or implied_volatility is None:
            return
        try:
            if self.atm_implied_volatility_recorder(
                underlying_symbol, trade_date, implied_volatility
            ):
                self.atm_implied_volatility_recorded_count += 1
        except Exception as recorder_failure:  # noqa: BLE001
            print(
                f"[iv-history] {underlying_symbol} record failed: "
                f"{type(recorder_failure).__name__}: {recorder_failure}",
                flush=True,
            )

    def positioning_size_down(
        self, entry_is_bullish: bool, instrument_kind: str = "cash_equity"
    ) -> float:
        """B16: the opponent ledger SIZES DOWN an opposed entry instead of refusing it.

        The boolean form below blocked every bullish entry whenever the daily FII lean was bearish —
        which on 2026-07-27 meant blocking the only profitable side of the book (longs 50% win
        +10,282 vs shorts 9.5% win -45,033) on 145 of 377 decisions. A multi-day CONFIRMATION signal
        must not act as a hard trigger-strength veto. Relevance is instrument-scaled: this is one
        market-wide INDEX-futures reading, so it weighs most on index options and least on a single
        cash equity. Tighten-only: never above 1.0.
        """
        from nse_algo_trader.participant_positioning.market_positioning_bias import (
            positioning_size_down_multiplier,
        )

        multiplier = positioning_size_down_multiplier(
            self.market_positioning_bias, entry_is_bullish, instrument_kind
        )
        if multiplier < 1.0:
            self.positioning_deferred_count += 1
        return multiplier

    def positioning_permits_entry(self, entry_is_bullish: bool) -> bool:
        """False when the opponent ledger says institutions are on the other
        side of this entry (strong divergence) — the loop then defers it and
        counts the deferral. True (permit) whenever there is no such opposition
        or no reading yet."""
        from nse_algo_trader.participant_positioning import (
            institutional_positioning_opposes_entry,
        )

        if institutional_positioning_opposes_entry(
            self.market_positioning_bias, entry_is_bullish
        ):
            self.positioning_deferred_count += 1
            return False
        return True

    def entry_decision_for_mechanism(self, mechanism_name: str) -> str:
        """'open' (not vetoed), 'shadow' (vetoed but this is the Kth probe — open
        anyway to gather recovery evidence), or 'veto' (skip). Slice 3 + 4."""
        if mechanism_name not in self.vetoed_mechanisms:
            return "open"
        self.shadow_probe_counter[mechanism_name] = (
            self.shadow_probe_counter.get(mechanism_name, 0) + 1
        )
        if self.shadow_probe_counter[mechanism_name] % _SHADOW_PROBE_EVERY == 0:
            self.shadow_entry_count += 1
            return "shadow"
        self.vetoed_entry_count += 1
        return "veto"

    def debate_risk_size_multiplier(self, mechanism_name: str) -> float:
        """Layer 11 slice 2c (research/101): the position-size lever from the debate risk_score.
        Returns 1.0 (no change) when this mechanism has no debated thesis OR the risk signal has
        not yet EARNED calibration — so an uncalibrated LLM opinion never moves a real trade.
        Once earned: 0.0 (full defer) at/above the defer threshold, `SIZE_DOWN_MULTIPLIER`
        at/above the size-down threshold, else 1.0. Counts each defer / size-down."""
        risk_score = self.debate_risk_score_by_mechanism.get(mechanism_name)
        if risk_score is None or not self.debate_risk_calibration_earned:
            return 1.0
        if risk_score >= _DEBATE_RISK_DEFER_THRESHOLD:
            self.debate_risk_deferred_count += 1
            return 0.0
        if risk_score >= _DEBATE_RISK_SIZE_DOWN_THRESHOLD:
            self.debate_risk_sized_down_count += 1
            return _DEBATE_RISK_SIZE_DOWN_MULTIPLIER
        return 1.0

    def news_event_size_multiplier(self, trading_symbol: str) -> float:
        """Trunk II SENSES S7 (research/147): the position-size lever from per-symbol news-event risk.
        Returns 1.0 (no change) when the symbol has no fresh event OR the signal has not yet EARNED
        calibration — so an uncalibrated news signal never moves a real trade. Once earned: 0.0 (defer)
        at/above the defer threshold, size-down multiplier at/above size-down. Counts each defer/size-down."""
        from nse_algo_trader.news_sentiment.news_entry_gate import (
            NEWS_EVENT_DEFER_THRESHOLD,
            NEWS_EVENT_SIZE_DOWN_THRESHOLD,
            news_event_size_multiplier,
        )

        risk = self.news_event_risk_by_symbol.get(trading_symbol)
        multiplier = news_event_size_multiplier(risk, self.news_event_calibration_earned)
        if risk is not None and self.news_event_calibration_earned:
            if risk >= NEWS_EVENT_DEFER_THRESHOLD:
                self.news_event_deferred_count += 1
            elif risk >= NEWS_EVENT_SIZE_DOWN_THRESHOLD:
                self.news_event_sized_down_count += 1
        return multiplier

    def index_level_size_multiplier(self, underlying_symbol: str, spot_price: float) -> float:
        """Trunk II SENSES index-level gate (research/151): size-down/defer an index-option entry that
        sits at a fresh, reliable S2 news S/R level for its underlying (reversal caution). Identity until
        calibration earned — an uncalibrated signal never moves a real trade. Counts defers/size-downs."""
        from nse_algo_trader.news_sentiment.index_level_gate import (
            INDEX_LEVEL_DEFER_PCT,
            index_level_size_multiplier,
            nearest_level_distance_pct,
        )

        levels = self.index_level_values_by_underlying.get(underlying_symbol)
        multiplier = index_level_size_multiplier(spot_price, levels, self.index_level_calibration_earned)
        if self.index_level_calibration_earned and multiplier < 1.0:
            distance = nearest_level_distance_pct(spot_price, levels)
            if distance is not None and distance <= INDEX_LEVEL_DEFER_PCT:
                self.index_level_deferred_count += 1
            else:
                self.index_level_sized_down_count += 1
        return multiplier

    def constitution_permits_order(self, segment: str, is_option: bool) -> bool:
        """Trunk VII.6 CONSCIENCE: the constitutional Referee as a HARD pre-order gate. Builds the
        proposed action from the system's structural INVARIANTS (intraday-only, atomic multi-leg,
        broker-routed, defined-risk) + the site's segment/kind, and BLOCKS the order if it violates
        a HARD article (scope A7, overnight A1, naked-leg A3/A4, routing A5). Per-trade risk (A8) is
        enforced upstream by the risk gate. None referee = permissive (no-op). Counts blocks.
        VII.5 corrigibility: an engaged off-switch blocks EVERY order first (safe interruptibility)."""
        switch = self.corrigibility_switch
        if switch is not None and not switch.permits_trading():
            self.corrigibility_blocked_order_count += 1  # off-switch engaged → block ALL orders
            return False
        referee = self.constitutional_referee
        if referee is None:
            return True
        from nse_algo_trader.conscience.constitutional_core import ProposedTradingAction

        action = ProposedTradingAction(
            segment=segment,
            is_option=is_option,
            is_overnight_carry=False,      # intraday-only (session square-off invariant)
            option_risk_defined=True,      # our option strategies are defined-risk by construction
            is_atomic_multi_leg=True,      # atomic_multi_leg_executor
            routes_through_broker=True,    # never direct-to-exchange
            has_algo_id=True,
        )
        if referee.adjudicate_order(action):
            return True
        self.constitution_blocked_order_count += 1
        return False

    def oversight_permits_autonomous_order(
        self, win_probability: float, is_option: bool,
        risk_amount: float | None = None, account_capital: float | None = None,
    ) -> bool:
        """Trunk VII CONSCIENCE scalable oversight: enforce the COMPETENCE CEILING — a high-stakes
        AND low-confidence decision is DEFERRED (no human overseer in the paper loop).

        B16: stakes are now measured by MONEY AT RISK relative to capital, not by instrument class.
        Passing `is_high_stakes=is_option` blocked essentially every option entry (option
        win-probabilities sit at 0.07-0.36 after memory recalibration, far under the 0.55 floor)
        while a cash position of ten times the rupee risk passed unexamined. A Rs 5,000 defined-risk
        spread is an order of magnitude LOWER stakes than a Rs 50,000 cash position. The gate is
        unchanged; only the stakes measure is. Falls back to the old instrument-class behaviour when
        risk/capital are unknown, so an uninstrumented caller never silently becomes permissive.
        """
        from nse_algo_trader.conscience.scalable_oversight import (
            OVERSIGHT_AUTONOMOUS,
            OVERSIGHT_HUMAN_REVIEW,
            classify_oversight,
            is_high_stakes_by_risk_amount,
        )

        if risk_amount is None or account_capital is None:
            high_stakes = is_option  # unknown sizing -> keep the conservative legacy behaviour
        else:
            high_stakes = is_high_stakes_by_risk_amount(risk_amount, account_capital)
        decision = classify_oversight(win_probability, is_high_stakes=high_stakes)
        if decision.tier == OVERSIGHT_AUTONOMOUS:
            self.oversight_autonomous_count += 1
        elif decision.tier == OVERSIGHT_HUMAN_REVIEW:
            self.oversight_human_review_blocked_count += 1
        else:
            self.oversight_panel_review_count += 1
        return decision.permit_autonomous

    def convergence_limiter_permits_order(self) -> bool:
        """Trunk VII CONSCIENCE instrumental-convergence limiter: cap the convergent resource-
        acquisition drive (total concurrent open exposures) + assert OFF-SWITCH DOMINANCE (no order
        while halted). Reads its own authoritative open state. Blocks + counts on a breach."""
        from nse_algo_trader.conscience.instrumental_convergence_limiter import (
            assess_convergence,
        )

        open_exposure_count = len(self.open_positions) + len(self.open_option_spreads)
        switch = self.corrigibility_switch
        is_halted = bool(switch is not None and not switch.permits_trading())
        verdict = assess_convergence(open_exposure_count, is_halted)
        if not verdict.permit:
            self.convergence_limiter_blocked_order_count += 1
        return verdict.permit

    # Trunk X AUTOPOIESIS — component-lifecycle homeostat (research/172). The service runs the MAPE-K
    # cycle and publishes the gate here; the entry sites read it. Organism health is a size lever, not
    # a signal: a body whose VITAL parts are failing may not stake full size on their output.
    organism_vitality_gate: object = None          # OrganismVitalityGate, set once by the service
    organism_vitality_sized_count: int = 0
    organism_vitality_vetoed_count: int = 0

    def organism_vitality_multiplier(self, depends_on_component_ids=()) -> float:
        """Size lever from the homeostat's latest assessment of the organism's own body.

        Structurally tighten-only (the gate clamps to [0, 1]), so it acts immediately without an
        earned-calibration gate — a degraded organism trading SMALLER is safe by construction.
        Never raises: a homeostat hiccup must not break the trading loop (Rule O.3)."""
        gate = self.organism_vitality_gate
        if gate is None:
            return 1.0
        try:
            multiplier = float(gate.size_multiplier_for_entry(depends_on_component_ids))
        except Exception:
            return 1.0
        multiplier = max(0.0, min(multiplier, 1.0))
        if multiplier < 1.0:
            self.organism_vitality_sized_count += 1
        return multiplier

    def homeostat_permits_order(self, depends_on_component_ids=()) -> bool:
        """Hard gate: an ACUTE failure of a VITAL component vetoes the entry outright.

        A CHRONIC closure violation deliberately does NOT veto (it prices size down instead) —
        see `organism_vitality_gate`; vetoing on it would halt trading permanently."""
        gate = self.organism_vitality_gate
        if gate is None:
            return True
        try:
            if gate.permits_order(depends_on_component_ids):
                return True
        except Exception:
            return True
        self.organism_vitality_vetoed_count += 1
        return False

    def power_budget_permits_order(self, now) -> bool:
        """Trunk VII CONSCIENCE power budget: meter the day's cumulative order throughput (market
        power) against an explicit daily budget. Resets the counter on a new date; blocks + counts
        when the budget is spent, else increments and permits."""
        from nse_algo_trader.conscience.power_budget import assess_power_budget

        today = now.date()
        if self.power_budget_day != today:
            self.power_budget_day = today
            self.power_budget_orders_today = 0
        verdict = assess_power_budget(self.power_budget_orders_today)
        if not verdict.permit:
            self.power_budget_blocked_order_count += 1
            return False
        self.power_budget_orders_today += 1
        return True

    def market_data_integrity_permits_signal(self, session_bars) -> bool:
        """Trunk VII CONSCIENCE market-data integrity defense: screen the bars a signal is built from
        for adversarial/corrupt values (non-positive prices, crossed candles, impossible moves,
        duplicate/non-monotonic timestamps). Blocks the signal on corruption (no trade on adversarial
        data) + counts anomalies. A clean series passes through untouched."""
        from nse_algo_trader.conscience.market_data_integrity_defense import (
            screen_bar_series,
        )

        self.market_data_series_screened_count += 1
        verdict = screen_bar_series(session_bars)
        if not verdict.clean:
            self.market_data_integrity_anomaly_count += verdict.anomaly_count
            self.market_data_integrity_blocked_signal_count += 1
            return False
        return True

    def workspace_caution_multiplier(self) -> float:
        """Trunk VIII SENTIENCE: the Global Workspace integrator ACTING on decisions. When the
        dominant ignited broadcast is a SAFETY/RISK concern, trim the entry size (tighten-only —
        never loosens, so it is safe-by-construction without a calibration gate). A critical safety
        focus defers entirely (belt-and-suspenders with the off-switch). 1.0 = no dominant concern.
        PURE — the dashboard calls it too; counting happens where an entry is actually trimmed."""
        b = self.workspace_broadcast
        if b is None or not getattr(b, "ignited", False):
            return 1.0
        kind = getattr(b, "kind", "")
        if kind == "safety":
            if getattr(b, "salience", 0.0) >= 0.999:  # critical safety (salience floored to 1.0)
                return 0.0
            return 0.75  # trade at 75% while a safety concern is the global focus
        if kind == "risk":
            return 0.90
        return 1.0  # opportunity/info never loosens sizing

    def record_option_size_down_stand_aside(
        self, underlying_symbol: str, reason: str | None
    ) -> None:
        """B7: tally an option entry refused because the composed size-down levers left under one
        whole lot. Never a silent skip (Rule O.3) — the count and the latest reason are surfaced."""
        self.option_size_down_stand_aside_count += 1
        self.last_option_size_down_stand_aside_reason = (
            f"{underlying_symbol}: {reason}" if reason else underlying_symbol
        )

    def counted_workspace_caution_multiplier(self) -> float:
        """The Global Workspace caution multiplier, COUNTING the trim/defer as it is read — the
        single place the integrator's action on decisions is tallied (the multiplier itself is pure).

        Callers that size an INDIVISIBLE lot count must use this and fold the multiplier into a
        single composed size-down (see `risk_management.discrete_lot_size_down_policy`), because
        applying it here as `int(size * multiplier)` floors a 1-lot option order to zero.
        """
        multiplier = self.workspace_caution_multiplier()
        if multiplier >= 1.0:
            return 1.0
        if multiplier <= 0.0:
            self.workspace_caution_deferred_count += 1
            return 0.0
        self.workspace_caution_applied_count += 1
        return multiplier

    def apply_workspace_caution(self, size: int) -> int:
        """Apply the Global Workspace caution multiplier to a CONTINUOUS entry size (cash shares).

        Safe here only because cash quantities are large enough that flooring is a rounding detail.
        Never use this for option lots — see `counted_workspace_caution_multiplier`.
        """
        multiplier = self.counted_workspace_caution_multiplier()
        if multiplier >= 1.0:
            return size
        if multiplier <= 0.0:
            return 0
        return int(size * multiplier)
    # Positions Layer 8 could NOT flatten (surfaced CRITICAL, never dropped).
    unflattened_square_off_positions: list[OpenPaperPosition] = field(
        default_factory=list
    )
    # Seeded cash names with no breakout YET — watched for a later intraday
    # breakout of their cached opening range (token -> WatchedOpeningRange).
    watched_opening_ranges: dict = field(default_factory=dict)
    # Options credit-spread path (one spread per underlying at a time).
    open_option_spreads: dict = field(default_factory=dict)
    #: B8: every option underlying looked at at least once THIS session. Coverage measure only — it
    #: is deliberately NOT the skip decision any more (it used to be, which gave each underlying
    #: exactly one look per process lifetime, spent in the first ~7 minutes after the open).
    seeded_option_underlyings: set = field(default_factory=set)
    #: B8: underlying symbol -> when it was last EXAMINED (whatever the outcome). Drives the re-look
    #: cooldown and the least-recently-looked-first ordering, so every underlying is reconsidered
    #: repeatedly through the session instead of once.
    last_option_look_at_by_underlying: dict = field(default_factory=dict)
    option_underlying_look_count: int = 0
    closed_option_spreads: list = field(default_factory=list)
    realized_option_spread_pnl: float = 0.0
    # Directional long-option path (trending underlyings; one per underlying).
    open_directional_options: dict = field(default_factory=dict)
    closed_directional_options: list = field(default_factory=list)
    realized_directional_option_pnl: float = 0.0
    # B32: 0-DTE expiry-day engine — multi-leg structures on underlyings expiring today. Carried
    # separately (their own defined-risk + time-stop + daily-loss-cap lifecycle); the live path
    # lazily creates these if absent, but they are declared here so they are visible state.
    open_zero_dte_positions: dict = field(default_factory=dict)
    closed_zero_dte_positions: list = field(default_factory=list)
    zero_dte_risk_state: ZeroDteRiskState = field(default_factory=ZeroDteRiskState)
    # Dashboard capital-per-trade limits (research/41 L9): the risk gate sizes
    # by risk; these clamp the notional down to max_capital_per_trade and skip
    # a trade whose notional is below min_capital_per_trade. Updated each pass
    # by the service from the live TradingControlConfig.
    max_capital_per_trade: float | None = None
    min_capital_per_trade: float | None = None
    # B34 task #4: per-underlying option-entry OUTCOME instrumentation — WHY each looked-at option
    # underlying did or did not open a position this pass. `option_entry_outcome_by_underlying` holds
    # the latest {reason, detail, at} per underlying (a live "why not?" probe); `option_entry_reason_counts`
    # aggregates reasons across the session. Built to pin the INDEX-options firing gate (stocks fire,
    # indices don't) live, and surfaced on the dashboard (Rule N) so the block is never invisible again.
    option_entry_outcome_by_underlying: dict = field(default_factory=dict)
    option_entry_reason_counts: dict = field(default_factory=dict)

    def record_option_entry_outcome(
        self, underlying_symbol: str, reason: str, detail: str = "", now=None
    ) -> None:
        """Record why an option underlying did/didn't open this look. `reason` is a stable slug
        (e.g. 'opened_credit_spread', 'sized_down_to_zero', 'risk_rejected', 'no_breakout'); `detail`
        carries the numbers (composed multiplier, base lots, rejection reasons) that make a floor
        diagnosable. Never raises — instrumentation must never break a trading pass."""
        try:
            self.option_entry_outcome_by_underlying[underlying_symbol] = {
                "reason": reason,
                "detail": detail,
                "at": now.isoformat() if now is not None else None,
            }
            self.option_entry_reason_counts[reason] = (
                self.option_entry_reason_counts.get(reason, 0) + 1
            )
        except Exception:  # noqa: BLE001 — a diagnostic must never break the loop
            pass

    def capital_clamped_quantity(self, entry_price: float, quantity: int) -> int:
        """Apply the min/max capital-per-trade limits to a risk-sized qty;
        returns the clamped qty, or 0 to skip (notional below the min)."""
        if entry_price <= 0 or quantity <= 0:
            return 0
        clamped = quantity
        if self.max_capital_per_trade is not None:
            clamped = min(clamped, int(self.max_capital_per_trade / entry_price))
        if clamped <= 0:
            return 0
        if (
            self.min_capital_per_trade is not None
            and entry_price * clamped < self.min_capital_per_trade
        ):
            return 0
        return clamped

    def open_position_count(self) -> int:
        return len(self.open_positions)

    def open_positions_snapshot(self) -> list[OpenPaperPosition]:
        return list(self.open_positions.values())


@dataclass
class ScanPassReport:
    scanned_price_count: int
    newly_seeded_count: int
    newly_opened_count: int
    closed_this_pass_count: int
    open_position_count: int
    squared_off_at_close: bool


def _regime_adx_warmed_at(recent_bars: list[PriceBar], at_timestamp) -> float | None:
    """ADX at (or just before) the breakout, warmed over the whole multi-day window — ADX needs
    ~2x period bars, which today's ~20 intraday bars alone cannot supply.

    **Returns None when unwarmed, NOT 0.0** (B31). The old 0.0 sentinel was indistinguishable from a
    genuine ADX of zero, and 0.0 <= the range-bound threshold, so an unmeasurable regime was
    classified as a CONFIDENT "range-bound" read. B4 measured the damage: 144 of 376 experiments
    carried win_probability ~= 0.0712 — the exact value produced by ADX 0 — i.e. ~38% of all trades
    were graded, filed and LEARNED FROM under a regime that had never actually been measured.

    That matters more now than when it was written: the regime is the arm selector's CONTEXT KEY, so
    a fabricated regime files a trade's outcome in the wrong cell and poisons the evidence the
    selector exists to accumulate.

    None means "unknown" — `classify_adx_market_regime` already maps it to INDECISIVE/STAND_ASIDE
    ("never trade blind"), and callers abstain rather than inventing a regime.
    """
    if len(recent_bars) < 28:
        return None
    adx_series = compute_average_directional_index(recent_bars)
    warmed_before = [
        adx_series.adx[index]
        for index, bar in enumerate(recent_bars)
        if bar.timestamp <= at_timestamp and adx_series.adx[index] is not None
    ]
    return warmed_before[-1] if warmed_before else None


def _open_position_from_signal(
    state: LiveUniversePaperState,
    signal,
    quantity: int,
    prediction_record: TradePredictionRecord,
    opened_at: datetime,
) -> None:
    entry_side = (
        OrderSide.BUY if signal.direction is SignalDirection.LONG else OrderSide.SELL
    )
    # Pay the spread on entry — the taker fills worse than the reference
    # (research/41: the live loop was frictionless). Buys fill above, sells
    # below; options pay a wider half-spread than cash.
    entry_fill_price = slipped_fill_price(
        signal.instrument, entry_side, signal.breakout_close_price,
        state.fill_slippage_config,
        order_quantity=quantity,
        average_daily_quantity=state.average_daily_quantity_by_token.get(
            signal.instrument.instrument_token
        ),
    )
    state.simulated_broker.update_market_price(
        signal.instrument.instrument_token, signal.breakout_close_price
    )
    state.ledger.record_fill(
        signal.instrument.instrument_token,
        entry_side,
        quantity,
        entry_fill_price,
    )
    state.open_positions[signal.instrument.instrument_token] = OpenPaperPosition(
        instrument=signal.instrument,
        direction=signal.direction,
        quantity=quantity,
        entry_price=entry_fill_price,
        stop_loss_price=signal.stop_loss_price,
        target_price=signal.target_price,
        opened_at=opened_at,
        strategy_tag=signal.strategy_tag,
        prediction_record=prediction_record,
    )


def _close_position(
    state: LiveUniversePaperState,
    position: OpenPaperPosition,
    exit_price: float,
    outcome: PaperSessionOutcome,
    closed_at: datetime,
    exited_on_profit_trail: bool = False,
) -> None:
    exit_side = (
        OrderSide.SELL if position.direction is SignalDirection.LONG else OrderSide.BUY
    )
    # Pay the spread on exit too (stops/targets fill at market near the level,
    # not exactly on it) — no more optimistic frictionless exits (research/41).
    exit_price = slipped_fill_price(
        position.instrument, exit_side, exit_price, state.fill_slippage_config,
        order_quantity=position.quantity,
        average_daily_quantity=state.average_daily_quantity_by_token.get(
            position.instrument.instrument_token
        ),
    )
    recorded = state.ledger.record_fill(
        position.instrument.instrument_token, exit_side, position.quantity, exit_price
    )
    closed_trade = ClosedPaperTrade(
        instrument=position.instrument,
        direction=position.direction,
        quantity=position.quantity,
        entry_price=position.entry_price,
        exit_price=exit_price,
        realized_pnl=recorded.realized_pnl_from_this_fill,
        outcome=outcome,
        opened_at=position.opened_at,
        closed_at=closed_at,
        maximum_favourable_profit=position.excursion.maximum_favourable_profit,
        maximum_adverse_profit=position.excursion.maximum_adverse_profit,
        exited_on_profit_trail=exited_on_profit_trail,
        total_fees=estimate_round_trip_cost(
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            segment="nse_cash_equity",
            opened_short=position.direction is not SignalDirection.LONG,
        ).total_cost,
        assigned_table=position.prediction_record.assigned_table.value,
    )
    state.closed_trades.append(closed_trade)
    graded = grade_prediction(
        position.prediction_record, recorded.realized_pnl_from_this_fill
    )
    state.scoreboard.add_graded_prediction(graded)
    # Emit the closed §9 experiment for Layer 10 to record (a plain (graded,
    # trade, kind) tuple — the loop never imports Layer 10; the service drains
    # these into ExperienceMemory each pass, Rule G).
    state.closed_experiment_events.append(
        (graded, closed_trade, position.instrument.kind.value.lower())
    )
    del state.open_positions[position.instrument.instrument_token]


def _manage_open_positions_against_prices(
    state: LiveUniversePaperState,
    latest_price_by_token: dict[int, float],
    now: datetime,
) -> int:
    closed_count = 0
    for token, position in list(state.open_positions.items()):
        price = latest_price_by_token.get(token)
        if price is None:
            continue
        # B23: fold this price into the position's excursion, then advance its profit trail. Both
        # work in PROFIT space so the same code serves long and short without a sign branch.
        position.observe_price_for_excursion(price)
        position.advance_profit_trail()
        outcome = position.has_hit_stop_or_target(price)
        if outcome is None:
            # B23: the trail is the third exit — it only ever fires once armed, so it can never
            # close a trade earlier than the original stop would have.
            if trail_exit_triggered(position.profit_trail, position.unrealised_profit_at(price)):
                _close_position(
                    state, position, price, PaperSessionOutcome.EXITED_STOP, now,
                    exited_on_profit_trail=True,
                )
                closed_count += 1
            continue
        exit_price = (
            position.stop_loss_price
            if outcome is PaperSessionOutcome.EXITED_STOP
            else position.target_price
        )
        _close_position(state, position, exit_price, outcome, now)
        closed_count += 1
    return closed_count


@dataclass
class WatchedOpeningRange:
    instrument: Instrument
    opening_range_high: float
    opening_range_low: float
    regime_adx: float
    target_risk_reward_ratio: float


def _cache_opening_range_for_watch(
    state, instrument, session_bars, recent_bars, strategy_config, now
) -> None:
    """Cache the opening-range high/low of a seeded-no-signal name so later
    passes can catch an intraday breakout from live LTP."""
    from datetime import timedelta

    session_open = session_bars[0].timestamp
    range_end = session_open + timedelta(minutes=strategy_config.opening_range_minutes)
    opening_bars = [b for b in session_bars if b.timestamp < range_end]
    if len(opening_bars) < 1:
        return
    # Past the latest-entry cutoff -> no point watching.
    if now.timetz().replace(tzinfo=None) >= strategy_config.latest_entry_time_ist:
        return
    # B31: no measured regime -> do not cache a watch we could only grade under a fabricated one.
    # The instrument is simply re-looked on a later pass once enough bars have accrued.
    watch_regime_adx = _regime_adx_warmed_at(recent_bars, recent_bars[-1].timestamp)
    if watch_regime_adx is None:
        state.entries_skipped_for_unmeasured_regime_count += 1
        return
    state.watched_opening_ranges[instrument.instrument_token] = WatchedOpeningRange(
        instrument=instrument,
        opening_range_high=max(b.high_price for b in opening_bars),
        opening_range_low=min(b.low_price for b in opening_bars),
        regime_adx=watch_regime_adx,
        target_risk_reward_ratio=strategy_config.target_risk_reward_ratio,
    )


def check_watched_names_for_live_breakout(
    state: LiveUniversePaperState,
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    strategy_config: OpeningRangeBreakoutConfig,
) -> int:
    """Each pass: price the watched names and open a position on any that
    have now broken their cached opening range (live-LTP breakout). Returns
    the number opened."""
    if not state.watched_opening_ranges:
        return 0
    if now.timetz().replace(tzinfo=None) >= strategy_config.latest_entry_time_ist:
        state.watched_opening_ranges.clear()
        return 0
    watched = list(state.watched_opening_ranges.values())
    price_by_token = live_universe_feed.latest_price_by_token(
        [w.instrument for w in watched]
    )
    opened = 0
    for watch in watched:
        token = watch.instrument.instrument_token
        if token in state.open_positions:
            state.watched_opening_ranges.pop(token, None)
            continue
        ltp = price_by_token.get(token)
        if ltp is None:
            continue
        direction = None
        if ltp > watch.opening_range_high:
            direction = SignalDirection.LONG
        elif ltp < watch.opening_range_low:
            direction = SignalDirection.SHORT
        if direction is None:
            continue
        if _open_watched_breakout(state, watch, direction, ltp, risk_budget, now):
            opened += 1
        state.watched_opening_ranges.pop(token, None)
    return opened


def _open_watched_breakout(state, watch, direction, ltp, risk_budget, now) -> bool:
    from nse_algo_trader.strategy_engine import OpeningRangeBreakoutSignal

    stop = watch.opening_range_low if direction is SignalDirection.LONG else watch.opening_range_high
    risk_per_unit = abs(ltp - stop)
    if risk_per_unit <= 0:
        return False
    target = (
        ltp + watch.target_risk_reward_ratio * risk_per_unit
        if direction is SignalDirection.LONG
        else ltp - watch.target_risk_reward_ratio * risk_per_unit
    )
    signal = OpeningRangeBreakoutSignal(
        instrument=watch.instrument,
        direction=direction,
        triggered_at=now,
        breakout_close_price=ltp,
        opening_range_high=watch.opening_range_high,
        opening_range_low=watch.opening_range_low,
        stop_loss_price=stop,
        target_price=target,
        strategy_tag="opening_range_breakout_v1",
    )
    risk_decision = evaluate_opening_range_breakout_signal(signal, risk_budget)
    if not risk_decision.approved or risk_decision.approved_quantity <= 0:
        return False
    clamped_quantity = state.capital_clamped_quantity(
        signal.breakout_close_price, risk_decision.approved_quantity
    )
    if clamped_quantity <= 0:
        return False  # notional below the min-capital-per-trade floor
    prediction_record = build_orb_prediction_record(
        signal=signal, adx_value=watch.regime_adx, session_date=now.date(),
        target_reward_multiple=watch.target_risk_reward_ratio,
    )
    prediction_record = state.apply_recalibration(prediction_record)
    if state.entry_decision_for_mechanism(prediction_record.mechanism_name) == "veto":
        return False
    # B16: the opponent ledger now SIZES DOWN rather than refusing — it blocked the profitable
    # side of the book outright (see positioning_size_down).
    clamped_quantity = int(
        clamped_quantity
        * state.positioning_size_down(
            entry_is_bullish=direction is SignalDirection.LONG,
            instrument_kind="cash_equity",
        )
        * state.debate_risk_size_multiplier(prediction_record.mechanism_name)
        * state.news_event_size_multiplier(signal.instrument.trading_symbol)  # Trunk II SENSES S7
        * state.win_probability_size_multiplier(  # Trunk IX PREDICTIVE-CORE ML win-prob engine
            prediction_record, signal.direction.value, signal.instrument.kind.value,
            _signal_reward_risk(signal), now)
        * state.capital_allocation_size_multiplier(  # Trunk III WILL — capital-allocation optimizer
            f"{signal.instrument.trading_symbol}|{signal.direction.value}")
        * state.world_model_size_multiplier(signal.direction.value)  # Trunk IX — world-model planning
        * state.organism_vitality_multiplier()  # Trunk X — organism self-health size lever
    )
    clamped_quantity = state.apply_workspace_caution(  # Trunk VIII: integrator trims on cautionary focus
        clamped_quantity
    )
    if clamped_quantity <= 0:
        return False  # Layer 11 debate-risk gate: high-risk thesis deferred (calibration earned)
    if not state.constitution_permits_order("nse_cash_equity", is_option=False):
        return False  # Trunk VII.6 constitutional Referee: order violates the constitution
    if not state.oversight_permits_autonomous_order(
        prediction_record.win_probability, is_option=False
    ):
        return False  # Trunk VII scalable oversight: beyond autonomous competence, escalated
    if not state.convergence_limiter_permits_order():
        return False  # Trunk VII instrumental-convergence limiter: sprawl / off-switch dominance
    if not state.homeostat_permits_order():
        return False  # Trunk X: a VITAL organ has acutely failed
    if not state.power_budget_permits_order(now):
        return False  # Trunk VII power budget: daily action-throughput budget spent
    _open_position_from_signal(
        state, signal, clamped_quantity, prediction_record, now
    )
    return True


def _seed_cash_instrument_from_orb(
    state: LiveUniversePaperState,
    instrument: Instrument,
    recent_bars: list[PriceBar],
    risk_budget: RiskBudgetConfig,
    strategy_config: OpeningRangeBreakoutConfig,
    now: datetime,
) -> bool:
    """Run the ORB detector over TODAY's bars (a slice of `recent_bars`),
    with the regime ADX warmed over the whole multi-day window. If a
    breakout fires and passes the risk gate, either open a held position or
    — if it already stopped/targeted earlier today — record the completed
    trade. Returns True if a position was opened (still open)."""
    state.seeded_cash_tokens.add(instrument.instrument_token)
    today = now.astimezone(recent_bars[0].timestamp.tzinfo).date()
    session_bars = [bar for bar in recent_bars if bar.timestamp.date() == today]
    if not session_bars:
        return False
    if not state.market_data_integrity_permits_signal(session_bars):
        return False  # Trunk VII adversarial-input defense: corrupt/spoofed bars — no trade
    signal = detect_opening_range_breakout(session_bars, instrument, strategy_config)
    if signal is None:
        # No breakout at seed time -> cache the opening range and watch live
        # LTP for a later intraday breakout (post-seed breakout watch).
        _cache_opening_range_for_watch(
            state, instrument, session_bars, recent_bars, strategy_config, now
        )
        return False
    risk_decision = evaluate_opening_range_breakout_signal(signal, risk_budget)
    if not risk_decision.approved or risk_decision.approved_quantity <= 0:
        return False
    clamped_quantity = state.capital_clamped_quantity(
        signal.breakout_close_price, risk_decision.approved_quantity
    )
    if clamped_quantity <= 0:
        return False  # notional below the min-capital-per-trade floor

    seed_regime_adx = _regime_adx_warmed_at(recent_bars, signal.triggered_at)
    if seed_regime_adx is None:
        state.entries_skipped_for_unmeasured_regime_count += 1
        return False  # B31: never grade (and learn from) a trade under an unmeasured regime
    prediction_record = build_orb_prediction_record(
        signal=signal,
        adx_value=seed_regime_adx,
        session_date=session_bars[0].timestamp.date(),
        target_reward_multiple=strategy_config.target_risk_reward_ratio,
    )
    prediction_record = state.apply_recalibration(prediction_record)
    if state.entry_decision_for_mechanism(prediction_record.mechanism_name) == "veto":
        return False  # antibody veto (a 1-in-N shadow probe opens for recovery)
    # B16: graded, not a block.
    clamped_quantity = int(
        clamped_quantity
        * state.positioning_size_down(
            entry_is_bullish=signal.direction is SignalDirection.LONG,
            instrument_kind="cash_equity",
        )
        * state.debate_risk_size_multiplier(prediction_record.mechanism_name)
        * state.news_event_size_multiplier(signal.instrument.trading_symbol)  # Trunk II SENSES S7
        * state.win_probability_size_multiplier(  # Trunk IX PREDICTIVE-CORE ML win-prob engine
            prediction_record, signal.direction.value, signal.instrument.kind.value,
            _signal_reward_risk(signal), now)
        * state.capital_allocation_size_multiplier(  # Trunk III WILL — capital-allocation optimizer
            f"{signal.instrument.trading_symbol}|{signal.direction.value}")
        * state.world_model_size_multiplier(signal.direction.value)  # Trunk IX — world-model planning
        * state.organism_vitality_multiplier()  # Trunk X — organism self-health size lever
    )
    clamped_quantity = state.apply_workspace_caution(  # Trunk VIII: integrator trims on cautionary focus
        clamped_quantity
    )
    if clamped_quantity <= 0:
        return False  # Layer 11 debate-risk gate: high-risk thesis deferred (calibration earned)
    if not state.constitution_permits_order("nse_cash_equity", is_option=False):
        return False  # Trunk VII.6 constitutional Referee: order violates the constitution
    if not state.oversight_permits_autonomous_order(
        prediction_record.win_probability, is_option=False
    ):
        return False  # Trunk VII scalable oversight: beyond autonomous competence, escalated
    if not state.convergence_limiter_permits_order():
        return False  # Trunk VII instrumental-convergence limiter: sprawl / off-switch dominance
    if not state.homeostat_permits_order():
        return False  # Trunk X: a VITAL organ has acutely failed
    if not state.power_budget_permits_order(signal.triggered_at):
        return False  # Trunk VII power budget: daily action-throughput budget spent
    _open_position_from_signal(
        state, signal, clamped_quantity, prediction_record, signal.triggered_at
    )
    position = state.open_positions[instrument.instrument_token]

    # Catch up on the part of today already elapsed: if the breakout already
    # hit stop/target in a later bar, close it there instead of holding.
    for bar in session_bars:
        if bar.timestamp <= signal.triggered_at:
            continue
        outcome = None
        if position.direction is SignalDirection.LONG:
            if bar.low_price <= position.stop_loss_price:
                outcome = PaperSessionOutcome.EXITED_STOP
            elif bar.high_price >= position.target_price:
                outcome = PaperSessionOutcome.EXITED_TARGET
        else:
            if bar.high_price >= position.stop_loss_price:
                outcome = PaperSessionOutcome.EXITED_STOP
            elif bar.low_price <= position.target_price:
                outcome = PaperSessionOutcome.EXITED_TARGET
        if outcome is not None:
            exit_price = (
                position.stop_loss_price
                if outcome is PaperSessionOutcome.EXITED_STOP
                else position.target_price
            )
            _close_position(state, position, exit_price, outcome, bar.timestamp)
            return False
    return True


def square_off_all_open_positions(
    state: LiveUniversePaperState,
    latest_price_by_token: dict[int, float],
    now: datetime,
) -> None:
    """Flatten every open position through Layer 8 — safe-ordered
    (BUY-to-cover before SELL-to-close), never a naked leg. This is the
    loop that finally consumes Layer 8 (Rule G)."""
    if not state.open_positions:
        return
    open_legs = []
    for position in state.open_positions.values():
        signed_quantity = (
            position.quantity
            if position.direction is SignalDirection.LONG
            else -position.quantity
        )
        open_legs.append(
            OpenPositionLeg(position.instrument, signed_quantity, position.strategy_tag)
        )
        exit_price = latest_price_by_token.get(
            position.instrument.instrument_token, position.entry_price
        )
        state.simulated_broker.update_market_price(
            position.instrument.instrument_token, exit_price
        )
    report = execute_intraday_square_off(open_legs, state.simulated_broker)
    # Honor Layer 8's guarantee: only book positions that ACTUALLY flattened.
    # A leg Layer 8 could not flatten stays OPEN and is surfaced as unflattened
    # (never silently booked closed) — the exact failure mode L8 exists to catch.
    unflattened_tokens = {
        leg.instrument.instrument_token for leg in report.unflattened_legs
    }
    for position in list(state.open_positions.values()):
        if position.instrument.instrument_token in unflattened_tokens:
            state.unflattened_square_off_positions.append(position)
            continue
        exit_price = latest_price_by_token.get(
            position.instrument.instrument_token, position.entry_price
        )
        _close_position(
            state, position, exit_price, PaperSessionOutcome.SQUARED_OFF_AT_CLOSE, now
        )


def run_live_universe_scan_pass(
    state: LiveUniversePaperState,
    cash_universe: list[Instrument],
    live_universe_feed,
    risk_budget: RiskBudgetConfig,
    now: datetime,
    max_new_cash_seeds_per_pass: int = 300,
    strategy_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
    square_off_schedule: IntradaySquareOffSchedule = IntradaySquareOffSchedule(
        forced_square_off_time_ist=_FORCED_SQUARE_OFF_TIME_IST
    ),
    market_clock=None,
) -> ScanPassReport:
    # Only open positions need live prices (for stop/target management and
    # square-off); ORB entry reads today's bars, not LTP. Pricing just the
    # held set keeps each pass cheap so a background thread never stalls.
    open_instruments = [
        position.instrument for position in state.open_positions.values()
    ]
    latest_price_by_token = (
        live_universe_feed.latest_price_by_token(open_instruments)
        if open_instruments
        else {}
    )

    closed_this_pass = _manage_open_positions_against_prices(
        state, latest_price_by_token, now
    )

    # Post-seed breakout watch: open any watched name that has now broken its
    # cached opening range on live LTP.
    check_watched_names_for_live_breakout(
        state, live_universe_feed, risk_budget, now, strategy_config
    )

    # Force square-off window: flatten everything, seed nothing more.
    should_square_off = (
        market_clock is not None
        and square_off_schedule.should_force_square_off_now(now, market_clock)
    )
    if should_square_off:
        square_off_all_open_positions(state, latest_price_by_token, now)
        return ScanPassReport(
            scanned_price_count=len(latest_price_by_token),
            newly_seeded_count=0,
            newly_opened_count=0,
            closed_this_pass_count=closed_this_pass,
            open_position_count=state.open_position_count(),
            squared_off_at_close=True,
        )

    newly_seeded = 0
    newly_opened = 0
    for instrument in cash_universe:
        if newly_seeded >= max_new_cash_seeds_per_pass:
            break
        if instrument.instrument_token in state.seeded_cash_tokens:
            continue
        if instrument.instrument_token in state.open_positions:
            continue
        recent_bars = live_universe_feed.recent_intraday_bars(
            instrument, now, bar_interval=BarInterval.MINUTE_5
        )
        newly_seeded += 1
        # B1: mark ATTEMPTED here, not only inside `_seed_cash_instrument_from_orb`. That function
        # is reached only when bars came back, so a bar-less instrument was never marked and the
        # very next pass retried the SAME one — the scan pointer could never advance past it.
        # Live effect: `seeded_count` frozen at 231/9292 for a whole session while the loop ran
        # every ~15 s, burning the entire per-pass budget re-fetching the same dead scrips.
        state.seeded_cash_tokens.add(instrument.instrument_token)
        if not recent_bars:
            state.cash_names_attempted_without_bars_count += 1
            continue
        opened = _seed_cash_instrument_from_orb(
            state, instrument, recent_bars, risk_budget, strategy_config, now
        )
        if opened:
            newly_opened += 1

    return ScanPassReport(
        scanned_price_count=len(latest_price_by_token),
        newly_seeded_count=newly_seeded,
        newly_opened_count=newly_opened,
        closed_this_pass_count=closed_this_pass,
        open_position_count=state.open_position_count(),
        squared_off_at_close=False,
    )
