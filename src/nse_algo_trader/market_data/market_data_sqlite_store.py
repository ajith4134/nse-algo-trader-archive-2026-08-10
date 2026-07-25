"""SQLite persistence for Layer 2 market data — bars + all five NSE reports.

This is the store the Layer 7 `HistoricalReplaySource` will replay from
and Layer 3 indicators will read history out of (`docs/PLAN.md` §8a.12).
All saves are idempotent: re-ingesting the same day/file replaces rather
than duplicates, so jobs can be re-run safely.
"""

import sqlite3
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.market_data.nse_official_reports import (
    BulkOrBlockDealRow,
    CashBhavcopyDeliveryRow,
    FoBanListReport,
    FoBhavcopyContractRow,
    FoContractType,
    MwplPositionLimitRow,
)

DEFAULT_MARKET_DATA_DB_FILE_PATH = Path(
    "~/.nse_algo_trader/market_data.sqlite3"
).expanduser()


class DealDisclosureKind(str, Enum):
    BULK_DEAL = "bulk"
    BLOCK_DEAL = "block"


_TABLE_CREATION_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS price_bars (
        instrument_token INTEGER NOT NULL,
        bar_interval TEXT NOT NULL,
        bar_timestamp TEXT NOT NULL,
        open_price REAL NOT NULL, high_price REAL NOT NULL,
        low_price REAL NOT NULL, close_price REAL NOT NULL,
        volume INTEGER NOT NULL, open_interest INTEGER,
        PRIMARY KEY (instrument_token, bar_interval, bar_timestamp))""",
    """CREATE TABLE IF NOT EXISTS cash_bhavcopy_delivery (
        trade_date TEXT NOT NULL, symbol TEXT NOT NULL, series TEXT NOT NULL,
        prev_close REAL NOT NULL, open_price REAL NOT NULL,
        high_price REAL NOT NULL, low_price REAL NOT NULL,
        last_price REAL NOT NULL, close_price REAL NOT NULL,
        average_price REAL NOT NULL, total_traded_quantity INTEGER NOT NULL,
        turnover_lakhs REAL NOT NULL, trade_count INTEGER NOT NULL,
        delivered_quantity INTEGER, delivered_percent REAL,
        PRIMARY KEY (trade_date, symbol, series))""",
    """CREATE TABLE IF NOT EXISTS fo_bhavcopy_contracts (
        trade_date TEXT NOT NULL, contract_type TEXT NOT NULL,
        nse_instrument_id INTEGER NOT NULL, underlying_symbol TEXT NOT NULL,
        expiry_date TEXT NOT NULL, strike_price REAL, option_right_code TEXT,
        open_price REAL NOT NULL, high_price REAL NOT NULL,
        low_price REAL NOT NULL, close_price REAL NOT NULL,
        settlement_price REAL NOT NULL, underlying_price REAL NOT NULL,
        open_interest INTEGER NOT NULL, change_in_open_interest INTEGER NOT NULL,
        total_traded_volume INTEGER NOT NULL,
        PRIMARY KEY (trade_date, nse_instrument_id))""",
    """CREATE TABLE IF NOT EXISTS fo_ban_list_symbols (
        ban_trade_date TEXT NOT NULL, underlying_symbol TEXT NOT NULL,
        PRIMARY KEY (ban_trade_date, underlying_symbol))""",
    """CREATE TABLE IF NOT EXISTS mwpl_position_limits (
        trade_date TEXT NOT NULL, isin TEXT NOT NULL, scrip_name TEXT NOT NULL,
        underlying_symbol TEXT NOT NULL,
        market_wide_position_limit INTEGER NOT NULL,
        aggregate_open_interest INTEGER NOT NULL,
        future_equivalent_open_interest REAL NOT NULL,
        next_day_fresh_position_limit INTEGER,
        PRIMARY KEY (trade_date, underlying_symbol))""",
    """CREATE TABLE IF NOT EXISTS bulk_block_deals (
        trade_date TEXT NOT NULL, deal_kind TEXT NOT NULL, symbol TEXT NOT NULL,
        security_name TEXT NOT NULL, client_name TEXT NOT NULL,
        is_buy INTEGER NOT NULL, quantity_traded INTEGER NOT NULL,
        weighted_average_price REAL NOT NULL, remarks TEXT)""",
    """CREATE INDEX IF NOT EXISTS idx_fo_contracts_by_underlying
        ON fo_bhavcopy_contracts (underlying_symbol, trade_date)""",
]


class MarketDataSqliteStore:
    def __init__(self, db_file_path: Path = DEFAULT_MARKET_DATA_DB_FILE_PATH):
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_file_path))
        self._connection.execute("PRAGMA journal_mode=WAL")
        for table_creation_statement in _TABLE_CREATION_STATEMENTS:
            self._connection.execute(table_creation_statement)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # -- price bars ---------------------------------------------------------

    def save_price_bars(self, price_bars: list[PriceBar]) -> None:
        self._connection.executemany(
            "INSERT OR REPLACE INTO price_bars VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    bar.instrument_token, bar.interval.value,
                    bar.timestamp.isoformat(), bar.open_price, bar.high_price,
                    bar.low_price, bar.close_price, bar.volume, bar.open_interest,
                )
                for bar in price_bars
            ],
        )
        self._connection.commit()

    def load_price_bars(
        self,
        instrument_token: int,
        bar_interval: BarInterval,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[PriceBar]:
        query = (
            "SELECT instrument_token, bar_interval, bar_timestamp, open_price,"
            " high_price, low_price, close_price, volume, open_interest"
            " FROM price_bars WHERE instrument_token=? AND bar_interval=?"
        )
        query_parameters: list = [instrument_token, bar_interval.value]
        if from_timestamp is not None:
            query += " AND bar_timestamp >= ?"
            query_parameters.append(from_timestamp.isoformat())
        if to_timestamp is not None:
            query += " AND bar_timestamp <= ?"
            query_parameters.append(to_timestamp.isoformat())
        query += " ORDER BY bar_timestamp"
        return [
            PriceBar(
                instrument_token=row[0], interval=BarInterval(row[1]),
                timestamp=datetime.fromisoformat(row[2]), open_price=row[3],
                high_price=row[4], low_price=row[5], close_price=row[6],
                volume=row[7], open_interest=row[8],
            )
            for row in self._connection.execute(query, query_parameters)
        ]

    # -- cash bhavcopy with delivery ----------------------------------------

    def save_cash_bhavcopy_delivery_rows(
        self, delivery_rows: list[CashBhavcopyDeliveryRow]
    ) -> None:
        self._connection.executemany(
            "INSERT OR REPLACE INTO cash_bhavcopy_delivery VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    row.trade_date.isoformat(), row.symbol, row.series,
                    row.prev_close, row.open_price, row.high_price, row.low_price,
                    row.last_price, row.close_price, row.average_price,
                    row.total_traded_quantity, row.turnover_lakhs, row.trade_count,
                    row.delivered_quantity, row.delivered_percent,
                )
                for row in delivery_rows
            ],
        )
        self._connection.commit()

    def load_cash_bhavcopy_delivery_rows(
        self, trade_date: date
    ) -> list[CashBhavcopyDeliveryRow]:
        return [
            CashBhavcopyDeliveryRow(
                trade_date=date.fromisoformat(row[0]), symbol=row[1], series=row[2],
                prev_close=row[3], open_price=row[4], high_price=row[5],
                low_price=row[6], last_price=row[7], close_price=row[8],
                average_price=row[9], total_traded_quantity=row[10],
                turnover_lakhs=row[11], trade_count=row[12],
                delivered_quantity=row[13], delivered_percent=row[14],
            )
            for row in self._connection.execute(
                "SELECT trade_date, symbol, series, prev_close, open_price,"
                " high_price, low_price, last_price, close_price, average_price,"
                " total_traded_quantity, turnover_lakhs, trade_count,"
                " delivered_quantity, delivered_percent"
                " FROM cash_bhavcopy_delivery WHERE trade_date=? ORDER BY symbol",
                (trade_date.isoformat(),),
            )
        ]

    def latest_cash_bhavcopy_trade_date(self) -> date | None:
        """The most recent trade date with stored cash bhavcopy, or None. Used to
        rank the Breeze-replay focus by real liquidity (§53 task #8)."""
        row = self._connection.execute(
            "SELECT MAX(trade_date) FROM cash_bhavcopy_delivery"
        ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    # -- F&O bhavcopy (historical OI) ---------------------------------------

    def save_fo_bhavcopy_contract_rows(
        self, contract_rows: list[FoBhavcopyContractRow]
    ) -> None:
        self._connection.executemany(
            "INSERT OR REPLACE INTO fo_bhavcopy_contracts VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    row.trade_date.isoformat(), row.contract_type.value,
                    row.nse_instrument_id, row.underlying_symbol,
                    row.expiry_date.isoformat(), row.strike_price,
                    row.option_right_code, row.open_price, row.high_price,
                    row.low_price, row.close_price, row.settlement_price,
                    row.underlying_price, row.open_interest,
                    row.change_in_open_interest, row.total_traded_volume,
                )
                for row in contract_rows
            ],
        )
        self._connection.commit()

    def load_fo_bhavcopy_contract_rows(
        self, trade_date: date, underlying_symbol: str | None = None
    ) -> list[FoBhavcopyContractRow]:
        query = (
            "SELECT trade_date, contract_type, nse_instrument_id,"
            " underlying_symbol, expiry_date, strike_price, option_right_code,"
            " open_price, high_price, low_price, close_price, settlement_price,"
            " underlying_price, open_interest, change_in_open_interest,"
            " total_traded_volume FROM fo_bhavcopy_contracts WHERE trade_date=?"
        )
        query_parameters: list = [trade_date.isoformat()]
        if underlying_symbol is not None:
            query += " AND underlying_symbol=?"
            query_parameters.append(underlying_symbol)
        return [
            FoBhavcopyContractRow(
                trade_date=date.fromisoformat(row[0]),
                contract_type=FoContractType(row[1]), nse_instrument_id=row[2],
                underlying_symbol=row[3], expiry_date=date.fromisoformat(row[4]),
                strike_price=row[5], option_right_code=row[6], open_price=row[7],
                high_price=row[8], low_price=row[9], close_price=row[10],
                settlement_price=row[11], underlying_price=row[12],
                open_interest=row[13], change_in_open_interest=row[14],
                total_traded_volume=row[15],
            )
            for row in self._connection.execute(query, query_parameters)
        ]

    def has_fo_bhavcopy_for_date(self, trade_date: date) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM fo_bhavcopy_contracts WHERE trade_date=? LIMIT 1",
                (trade_date.isoformat(),),
            ).fetchone()
            is not None
        )

    def list_stored_fo_bhavcopy_trade_dates(self) -> list[date]:
        return [
            date.fromisoformat(row[0])
            for row in self._connection.execute(
                "SELECT DISTINCT trade_date FROM fo_bhavcopy_contracts"
                " ORDER BY trade_date"
            )
        ]

    # -- F&O ban list --------------------------------------------------------

    def save_fo_ban_list_report(self, ban_list_report: FoBanListReport) -> None:
        ban_date_iso = ban_list_report.ban_trade_date.isoformat()
        self._connection.execute(
            "DELETE FROM fo_ban_list_symbols WHERE ban_trade_date=?",
            (ban_date_iso,),
        )
        self._connection.executemany(
            "INSERT INTO fo_ban_list_symbols VALUES (?,?)",
            [(ban_date_iso, symbol) for symbol in ban_list_report.banned_underlying_symbols],
        )
        self._connection.commit()

    def has_fo_ban_list_for_date(self, ban_trade_date: date) -> bool:
        """Whether any F&O ban row exists for this date. NOTE: a genuinely
        zero-ban trading day also stores no rows, so this returns False for
        both "never ingested" and "ingested, zero bans" — the two are
        indistinguishable in this table. That is acceptable for the risk
        gate (both mean "no underlying is banned"); a stale-ingestion guard
        belongs in the ingestion job's own log, not here."""
        row = self._connection.execute(
            "SELECT 1 FROM fo_ban_list_symbols WHERE ban_trade_date=? LIMIT 1",
            (ban_trade_date.isoformat(),),
        ).fetchone()
        return row is not None

    def load_fo_ban_list_report(self, ban_trade_date: date) -> FoBanListReport | None:
        """Returns the banned underlyings for the date, or None when no ban
        rows exist (see `has_fo_ban_list_for_date` for the zero-ban vs
        never-ingested caveat)."""
        banned_symbols = [
            row[0]
            for row in self._connection.execute(
                "SELECT underlying_symbol FROM fo_ban_list_symbols"
                " WHERE ban_trade_date=? ORDER BY underlying_symbol",
                (ban_trade_date.isoformat(),),
            )
        ]
        if not banned_symbols:
            return None
        return FoBanListReport(
            ban_trade_date=ban_trade_date,
            banned_underlying_symbols=tuple(banned_symbols),
        )

    # -- MWPL ----------------------------------------------------------------

    def save_mwpl_position_limit_rows(
        self, mwpl_rows: list[MwplPositionLimitRow]
    ) -> None:
        self._connection.executemany(
            "INSERT OR REPLACE INTO mwpl_position_limits VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    row.trade_date.isoformat(), row.isin, row.scrip_name,
                    row.underlying_symbol, row.market_wide_position_limit,
                    row.aggregate_open_interest,
                    row.future_equivalent_open_interest,
                    row.next_day_fresh_position_limit,
                )
                for row in mwpl_rows
            ],
        )
        self._connection.commit()

    def load_mwpl_position_limit_rows(
        self, trade_date: date
    ) -> list[MwplPositionLimitRow]:
        return [
            MwplPositionLimitRow(
                trade_date=date.fromisoformat(row[0]), isin=row[1],
                scrip_name=row[2], underlying_symbol=row[3],
                market_wide_position_limit=row[4], aggregate_open_interest=row[5],
                future_equivalent_open_interest=row[6],
                next_day_fresh_position_limit=row[7],
            )
            for row in self._connection.execute(
                "SELECT trade_date, isin, scrip_name, underlying_symbol,"
                " market_wide_position_limit, aggregate_open_interest,"
                " future_equivalent_open_interest, next_day_fresh_position_limit"
                " FROM mwpl_position_limits WHERE trade_date=?"
                " ORDER BY underlying_symbol",
                (trade_date.isoformat(),),
            )
        ]

    # -- bulk/block deals ----------------------------------------------------

    def save_bulk_or_block_deal_rows(
        self, deal_rows: list[BulkOrBlockDealRow], deal_kind: DealDisclosureKind
    ) -> None:
        """Replaces every stored deal of this kind for the dates present in
        `deal_rows` (the daily file is the whole day's truth)."""
        for deal_trade_date in {row.trade_date for row in deal_rows}:
            self._connection.execute(
                "DELETE FROM bulk_block_deals WHERE trade_date=? AND deal_kind=?",
                (deal_trade_date.isoformat(), deal_kind.value),
            )
        self._connection.executemany(
            "INSERT INTO bulk_block_deals VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    row.trade_date.isoformat(), deal_kind.value, row.symbol,
                    row.security_name, row.client_name, int(row.is_buy),
                    row.quantity_traded, row.weighted_average_price, row.remarks,
                )
                for row in deal_rows
            ],
        )
        self._connection.commit()

    def load_bulk_or_block_deal_rows(
        self, trade_date: date, deal_kind: DealDisclosureKind
    ) -> list[BulkOrBlockDealRow]:
        return [
            BulkOrBlockDealRow(
                trade_date=date.fromisoformat(row[0]), symbol=row[1],
                security_name=row[2], client_name=row[3], is_buy=bool(row[4]),
                quantity_traded=row[5], weighted_average_price=row[6],
                remarks=row[7],
            )
            for row in self._connection.execute(
                "SELECT trade_date, symbol, security_name, client_name, is_buy,"
                " quantity_traded, weighted_average_price, remarks"
                " FROM bulk_block_deals WHERE trade_date=? AND deal_kind=?"
                " ORDER BY symbol, client_name",
                (trade_date.isoformat(), deal_kind.value),
            )
        ]
