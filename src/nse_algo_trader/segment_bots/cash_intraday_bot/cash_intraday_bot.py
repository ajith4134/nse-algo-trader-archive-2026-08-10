"""The assembled CASH-INTRADAY bot — a ``SegmentBot`` over the full NSE cash universe (cross-sectional).

Each cycle: ingest the universe's recent bars → engineer cross-sectional factors → score every stock with
the alpha model (trained ranker, or the factor-composite fallback until earned) → build a cost-aware
long/short book (long the top quantile, short the bottom quantile) → emit one cash-equity ``TradeProposal``
per selected name. Proposes only (crypto §03b) into the portfolio supervisor.

Owns its data via an injected ``CashUniverseDataAdapter`` seam (Rule J), its competency/track-record store,
and its self-learning loop (accrues forward-return samples → retrains the cross-sectional ranker).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_alpha_model import (
    CrossSectionalAlphaModel,
    CrossSectionalAlphaStore,
    CrossSectionalSample,
)
from nse_algo_trader.segment_bots.cash_intraday_bot.cross_sectional_features import (
    build_cross_sectional_features,
)
from nse_algo_trader.segment_bots.directional_ai.directional_side_brain import DirectionalSideBrain
from nse_algo_trader.segment_bots.index_option_bot.index_option_bot import BotTrackRecordStore
from nse_algo_trader.segment_bots.segment_bot_protocol import (
    BotCompetency,
    MarketSegment,
    OptionStructureKind,
    OptionStructurePlan,
    TradeProposal,
    TradeSide,
)

_SIGNAL_TTL_SECONDS = 5 * 60
_BOOK_QUANTILE = 0.10  # long the top decile, short the bottom decile
_MAX_SHARES_AT_FULL_CONVICTION = 100
_MIN_NAMES_FOR_BOOK = 20  # need a real cross-section before ranking means anything
_EARNED_MIN_CLOSED_TRADES = 50
_TRADES_PER_LEVEL = 60


class CashUniverseDataAdapter(Protocol):
    """The bot's data seam. Production wires the live universe feed; tests inject a fake. No DB in the bot."""

    def universe_bars(self) -> dict[str, pd.DataFrame]: ...  # {symbol: recent OHLCV bars}
    def last_price(self, symbol: str) -> float: ...
    def round_trip_cost_fraction(self, symbol: str) -> float: ...  # STT+brokerage+slippage as a fraction


class CashIntradayBot:
    """The CASH-INTRADAY SegmentBot: proposes a cross-sectional long/short cash-equity book."""

    name = "cash_intraday_bot"
    segment = MarketSegment.CASH_INTRADAY

    def __init__(self, data_adapter: CashUniverseDataAdapter, store_dir: Path):
        self._adapter = data_adapter
        self._alpha = CrossSectionalAlphaModel(CrossSectionalAlphaStore(store_dir / "alpha"))
        self._track_store = BotTrackRecordStore(store_dir / "track_record")
        self._brain = DirectionalSideBrain(store_dir / "directional")
        Path(store_dir).mkdir(parents=True, exist_ok=True)
        self._sample_path = Path(store_dir) / "cross_sectional_samples.json"

    def competency(self) -> BotCompetency:
        closed = self._track_store.closed_count()
        return BotCompetency(
            level=min(5, closed // _TRADES_PER_LEVEL),
            closed_trades=closed,
            rolling_sharpe=None,
            calibration_error=None,
            is_earned=closed >= _EARNED_MIN_CLOSED_TRADES,
        )

    def propose(self, now_epoch: float) -> list[TradeProposal]:
        # Rule-Q cold-start: build the book from birth (floor size while unearned) so a paper track record can
        # accrue; LIVE capital-weight is gated in the supervisor + at the live-execution seam, not by silence.
        competency = self.competency()
        self._brain.begin_cycle()  # reset the per-cycle directional-training budget (cold-start throttle)

        bars = self._adapter.universe_bars()
        if len(bars) < _MIN_NAMES_FOR_BOOK:
            return []
        features = build_cross_sectional_features(bars)
        alpha = self._alpha.score(features)
        if alpha.empty:
            return []

        ranked = alpha.sort_values(ascending=False)
        k = max(1, int(len(ranked) * _BOOK_QUANTILE))
        longs = ranked.head(k)
        shorts = ranked.tail(k)
        span = float(ranked.iloc[0] - ranked.iloc[-1]) or 1.0

        proposals: list[TradeProposal] = []
        for symbol, score in longs.items():
            if not self._directional_confirms(symbol, TradeSide.LONG, bars):
                continue  # the name's own time-series brain firmly contradicts the cross-sectional long
            p = self._to_proposal(symbol, TradeSide.LONG, abs(score) / span, features, competency, now_epoch)
            if p:
                proposals.append(p)
        for symbol, score in shorts.items():
            if not self._directional_confirms(symbol, TradeSide.SHORT, bars):
                continue
            p = self._to_proposal(symbol, TradeSide.SHORT, abs(score) / span, features, competency, now_epoch)
            if p:
                proposals.append(p)
        return proposals

    def _directional_confirms(self, symbol: str, book_side: TradeSide, bars: dict[str, pd.DataFrame]) -> bool:
        """Meta-label the cross-sectional pick with the name's own directional brain.

        The brain is an INDEPENDENT time-series view; it VETOES a book pick only when it has an earned,
        confident opposing side (LONG book vs brain SHORT, or vice-versa). While the brain is neutral or
        still gathering history — the common case until the pair earns — the cross-sectional decision stands
        unchanged (Rule Q: the gate arms itself automatically as history accrues, it never shrinks the book).
        """
        verdict = self._brain.verdict_for(symbol, bars.get(symbol))
        if verdict.side == TradeSide.NEUTRAL:
            return True
        return verdict.side == book_side

    def _to_proposal(self, symbol, side, conviction, features, competency, now_epoch) -> TradeProposal | None:
        conviction = float(min(max(conviction, 0.0), 1.0))
        # cost gate: skip when the modelled edge cannot clear the round-trip cost (Qlib-style cost awareness)
        cost = self._adapter.round_trip_cost_fraction(symbol)
        expected_edge = 0.02 * conviction  # modelled per-name edge fraction (scaled by conviction)
        if expected_edge <= cost:
            return None
        shares = self._size_shares(conviction, competency)
        if shares <= 0:
            return None
        row = features.loc[symbol].to_dict() if symbol in features.index else {}
        return TradeProposal(
            segment=MarketSegment.CASH_INTRADAY,
            bot_name=f"cash_intraday_bot:{symbol}",
            underlying=symbol,
            side=side,
            structure=OptionStructurePlan(OptionStructureKind.NONE, symbol, ""),
            size_hint_lots=shares,
            conviction=conviction,
            calibrated_prob=0.5 + 0.4 * conviction * (1 if side == TradeSide.LONG else 1),
            expected_expectancy=expected_edge - cost,
            loss_tail_estimate=0.02,  # intraday cash, stop-bounded
            signal_expiry_epoch=now_epoch + _SIGNAL_TTL_SECONDS,
            regime_label="cross_sectional",
            feature_provenance={"alpha_features": row, "cost_fraction": cost, "side": side.value},
        )

    @staticmethod
    def _size_shares(conviction: float, competency: BotCompetency) -> int:
        scale = (min(max(competency.level, 0), 5) + 1) / 6.0
        return int(max(0, round(conviction * _MAX_SHARES_AT_FULL_CONVICTION * scale)))

    def record_forward_return_sample(self, sample: CrossSectionalSample) -> None:
        """Accrue one (features → realised forward-return) training row for the cross-sectional ranker."""
        rows = self._load_samples_raw()
        rows.append({"features": sample.features, "forward_return": sample.forward_return,
                     "as_of_epoch": sample.as_of_epoch})
        self._sample_path.write_text(json.dumps(rows[-200_000:]))

    def _load_samples_raw(self) -> list[dict]:
        if not self._sample_path.exists():
            return []
        try:
            return json.loads(self._sample_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def learn_from_closed_trades(self) -> None:
        """Self-learning: retrain the cross-sectional ranker on accrued forward-return samples (Rule Q gates it)."""
        rows = self._load_samples_raw()
        if rows:
            self._alpha.train([CrossSectionalSample(r["features"], float(r["forward_return"]),
                                                    float(r["as_of_epoch"])) for r in rows])

    def record_closed_trade(self, trade) -> None:
        """Accrue a closed trade for competency (the maturity ladder that gates activation)."""
        self._track_store.record(trade)
