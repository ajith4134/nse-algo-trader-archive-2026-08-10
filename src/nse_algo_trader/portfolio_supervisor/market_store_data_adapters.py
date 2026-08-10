"""Production data adapters that feed the segment-bot pod from the real market store (wiring, Rule F/G).

These implement each bot's data seam against the on-disk market database (``fo_bhavcopy_contracts``,
``atm_implied_volatility_daily``) — real stored NSE data — so the pod produces REAL proposals instead of the
empty-universe placeholder. Everything joins on ``underlying_symbol`` (no token mapping needed):

* option chains + spot from the latest ``fo_bhavcopy`` snapshot per underlying,
* a daily underlying-price series (distinct trade-dates) for the vol-regime engine,
* ATM implied vol from ``atm_implied_volatility_daily``,
* a cash cross-section built from the F&O stocks' daily underlying prices.

The LIVE intraday feed (5m bars, live chain) remains the open blocker (Rule K) — these serve real STORED
data for the real-data pass; production swaps the same seam for the live feed. Read-only; opens its own
sqlite connection per call so it is thread-safe under the dashboard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from nse_algo_trader.market_data.underlying_intraday_price_source import UnderlyingIntradayPriceSource
from nse_algo_trader.segment_bots.segment_bot_protocol import TradeSide
from nse_algo_trader.universe_registry.instrument_types import (
    ExchangeSegment,
    Instrument,
    InstrumentKind,
    OptionRight,
)

_DEFAULT_DB = Path.home() / ".nse_algo_trader" / "market_data.sqlite3"
_INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")
_MIN_INTRADAY_BARS_FOR_DEPTH = 60  # below this the intraday history is too thin to prefer over the daily series


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


class MarketStoreOptionAdapter:
    """Serves the INDEX-OPTION or STOCK-OPTION bot from the real F&O bhavcopy store."""

    def __init__(self, db_path: Path | None = None, *, index: bool, max_underlyings: int = 25,
                 live_chain_source=None):
        self._db = db_path or _DEFAULT_DB
        self._index = index
        self._max = max_underlyings
        self._intraday_prices = UnderlyingIntradayPriceSource(self._db)
        self._live_chain = live_chain_source  # optional LiveOptionChainSource — today's real chain (Rule I/J)
        self._live_expiry: dict[str, str] = {}  # underlying → live nearest expiry (set when a live chain loads)

    def _underlyings(self) -> list[str]:
        if not self._db.exists():
            return []
        con = _connect(self._db)
        try:
            placeholders = ",".join("?" * len(_INDEX_SYMBOLS))
            op = "IN" if self._index else "NOT IN"
            rows = con.execute(
                f"SELECT underlying_symbol, COUNT(*) n FROM fo_bhavcopy_contracts "
                f"WHERE option_right_code IN ('CE','PE') AND underlying_symbol {op} ({placeholders}) "
                f"GROUP BY underlying_symbol ORDER BY n DESC LIMIT {self._max}",
                _INDEX_SYMBOLS,
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            con.close()

    def index_underlyings(self) -> list[str]:
        return self._underlyings() if self._index else []

    def stock_underlyings(self) -> list[str]:
        return self._underlyings() if not self._index else []

    def price_series(self, underlying: str) -> pd.Series:
        if not self._db.exists():
            return pd.Series(dtype=float)
        # Prefer the DEEP 5m intraday history (hundreds–thousands of bars → the regime + directional engines
        # can actually earn); fall back to the shallow daily F&O-derived series only when intraday is absent.
        intraday = self._intraday_prices.close_series(underlying)
        if len(intraday) >= _MIN_INTRADAY_BARS_FOR_DEPTH:
            return intraday
        con = _connect(self._db)
        try:
            df = pd.read_sql_query(
                "SELECT trade_date, AVG(underlying_price) px FROM fo_bhavcopy_contracts "
                "WHERE underlying_symbol=? AND underlying_price>0 GROUP BY trade_date ORDER BY trade_date",
                con, params=(underlying,),
            )
            daily = df["px"].astype(float) if len(df) else pd.Series(dtype=float)
        finally:
            con.close()
        return intraday if len(intraday) > len(daily) else daily

    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str]:
        # prefer the LIVE chain (today's real strikes/LTP/expiry) when a source is wired; else stored bhavcopy
        if self._live_chain is not None:
            try:
                live = self._live_chain.option_chain(underlying)
            except Exception:  # noqa: BLE001 — a live-feed failure falls back to the stored chain (Rule J)
                live = None
            if live is not None and not live[0].empty:
                chain, trade_date, _spot = live
                self._live_expiry[underlying] = str(chain["expiry_date"].iloc[0])[:10]
                return chain, trade_date
        if not self._db.exists():
            return pd.DataFrame(), ""
        con = _connect(self._db)
        try:
            td = con.execute(
                "SELECT trade_date FROM fo_bhavcopy_contracts WHERE underlying_symbol=? "
                "AND option_right_code IN ('CE','PE') GROUP BY trade_date ORDER BY COUNT(*) DESC LIMIT 1",
                (underlying,),
            ).fetchone()
            if td is None:
                return pd.DataFrame(), ""
            chain = pd.read_sql_query(
                "SELECT option_right_code, strike_price, close_price, underlying_price, expiry_date, "
                "open_interest, total_traded_volume FROM fo_bhavcopy_contracts "
                "WHERE underlying_symbol=? AND trade_date=? AND option_right_code IN ('CE','PE') AND close_price>0",
                con, params=(underlying, td[0]),
            )
            return chain, str(td[0])[:10]
        finally:
            con.close()

    def implied_atm_vol(self, underlying: str) -> float | None:
        if not self._db.exists():
            return None
        con = _connect(self._db)
        try:
            row = con.execute(
                "SELECT implied_volatility FROM atm_implied_volatility_daily WHERE underlying_symbol=? "
                "ORDER BY trade_date DESC LIMIT 1", (underlying,),
            ).fetchone()
            return float(row[0]) if row and row[0] else None
        finally:
            con.close()

    def nearest_expiry(self, underlying: str) -> str:
        if underlying in self._live_expiry:
            return self._live_expiry[underlying]  # today's real nearest expiry from the live chain
        chain, _ = self.option_chain(underlying)
        return str(chain["expiry_date"].min())[:10] if len(chain) else ""

    def is_expiry_day(self, underlying: str) -> bool:
        return False  # requires the live trading calendar — LIVE blocker

    def trend_side(self, underlying: str) -> TradeSide:
        return TradeSide.NEUTRAL  # a live trend signal is a LIVE-feed enhancement

    def event_calendar(self):
        """Real NSE corporate-event calendar (board meetings / results) — feeds the stock bot's event gate."""
        if self._index:
            return None  # index options have no single-name event calendar
        from nse_algo_trader.segment_bots.stock_option_bot.nse_event_calendar_source import (
            NseEventCalendarSource,
        )

        if getattr(self, "_event_source", None) is None:
            source = NseEventCalendarSource()
            if not source.signed_days_to_nearest_event("RELIANCE", __import__("datetime").date.today()):
                source.refresh()  # cache empty → fetch the live calendar once
            self._event_source = source
        return self._event_source


class MarketStoreCashAdapter:
    """Serves the CASH bot a cross-section built from the F&O stocks' daily underlying-price series."""

    def __init__(self, db_path: Path | None = None, max_symbols: int = 200, lookback: int = 40):
        self._db = db_path or _DEFAULT_DB
        self._max = max_symbols
        self._lookback = lookback

    def universe_bars(self) -> dict[str, pd.DataFrame]:
        if not self._db.exists():
            return {}
        con = _connect(self._db)
        try:
            symbols = [r[0] for r in con.execute(
                "SELECT underlying_symbol, COUNT(DISTINCT trade_date) n FROM fo_bhavcopy_contracts "
                "GROUP BY underlying_symbol HAVING n>=10 ORDER BY n DESC LIMIT ?", (self._max,)).fetchall()]
            bars: dict[str, pd.DataFrame] = {}
            for sym in symbols:
                df = pd.read_sql_query(
                    "SELECT trade_date, AVG(underlying_price) close FROM fo_bhavcopy_contracts "
                    "WHERE underlying_symbol=? AND underlying_price>0 GROUP BY trade_date "
                    "ORDER BY trade_date DESC LIMIT ?", con, params=(sym, self._lookback))
                if len(df) >= 10:
                    df = df.iloc[::-1].reset_index(drop=True)
                    df["open"] = df["high"] = df["low"] = df["close"]
                    df["volume"] = 0.0
                    bars[sym] = df[["open", "high", "low", "close", "volume"]]
            return bars
        finally:
            con.close()

    def last_price(self, symbol: str) -> float:
        bars = self.universe_bars().get(symbol)
        return float(bars["close"].iloc[-1]) if bars is not None and len(bars) else 0.0

    def round_trip_cost_fraction(self, symbol: str) -> float:
        return 0.0015  # cash intraday round-trip (STT+brokerage+slippage) ~ 15 bps; refine via cost model


class CashBhavcopyUniverseAdapter:
    """Serves the CASH bot the FULL NSE cash-equity universe from the cash-bhavcopy store (Rule L).

    Unlike the F&O-stock proxy, this covers every EQ-series name in ``cash_bhavcopy_delivery`` (~2000
    equities) with real OHLCV + volume per trade-date — the true cross-section. Daily history is currently
    thin (a handful of bhavcopy days); breadth is full, and depth accrues as more days ingest (Rule Q, not a
    shrink). The LIVE intraday 5m feed is the depth enhancement (open blocker).
    """

    def __init__(self, db_path: Path | None = None, max_symbols: int = 2500, lookback_days: int = 30):
        self._db = db_path or _DEFAULT_DB
        self._max = max_symbols
        self._lookback = lookback_days

    def universe_bars(self) -> dict[str, pd.DataFrame]:
        if not self._db.exists():
            return {}
        con = _connect(self._db)
        try:
            # one query over the recent EQ-series rows, then group per symbol (breadth = full universe)
            df = pd.read_sql_query(
                "SELECT trade_date, symbol, open_price AS open, high_price AS high, low_price AS low, "
                "close_price AS close, total_traded_quantity AS volume FROM cash_bhavcopy_delivery "
                "WHERE series='EQ' AND close_price>0 ORDER BY symbol, trade_date", con,
            )
            if df.empty:
                return {}
            bars: dict[str, pd.DataFrame] = {}
            for symbol, group in df.groupby("symbol"):
                frame = group.tail(self._lookback)[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
                if len(frame) >= 2:
                    bars[str(symbol)] = frame
                if len(bars) >= self._max:
                    break
            return bars
        finally:
            con.close()

    def last_price(self, symbol: str) -> float:
        bars = self.universe_bars().get(symbol)
        return float(bars["close"].iloc[-1]) if bars is not None and len(bars) else 0.0

    def round_trip_cost_fraction(self, symbol: str) -> float:
        return 0.0015  # cash intraday round-trip ~15 bps; refine via indian_trading_cost_model


class MarketStoreInstrumentResolver:
    """Resolves cash/option legs to concrete instruments from the real chain (for the order router)."""

    def __init__(self, db_path: Path | None = None):
        self._db = db_path or _DEFAULT_DB
        self._token = 900_000

    def reference_spot(self, underlying: str) -> float | None:
        adapter = MarketStoreOptionAdapter(self._db, index=True)
        chain, _ = adapter.option_chain(underlying)
        return float(chain["underlying_price"].iloc[0]) if len(chain) else None

    def resolve_cash(self, symbol: str) -> Instrument | None:
        self._token += 1
        return Instrument(self._token, symbol, ExchangeSegment.NSE_CASH, InstrumentKind.CASH_EQUITY, 1, 0.05)

    def resolve_option_leg(self, underlying, option_right, moneyness_offset, expiry) -> Instrument | None:
        spot = self.reference_spot(underlying)
        if spot is None:
            return None
        self._token += 1
        target = spot * (1 + moneyness_offset)
        right = OptionRight.CALL if str(option_right).upper().startswith("C") else OptionRight.PUT
        from datetime import date

        try:
            exp = date.fromisoformat(str(expiry)[:10]) if expiry else date.today()
        except ValueError:
            exp = None
        kind = InstrumentKind.INDEX_OPTION if underlying in _INDEX_SYMBOLS else InstrumentKind.STOCK_OPTION
        lot = 50 if underlying in _INDEX_SYMBOLS else 100
        return Instrument(self._token, f"{underlying}{expiry}{option_right}", ExchangeSegment.NSE_FO, kind,
                          lot_size=lot, tick_size=0.05, underlying_symbol=underlying,
                          strike_price=round(target, 2), option_right=right, expiry_date=exp)
