from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from nse_algo_trader.market_data import BarInterval, PriceBar
from nse_algo_trader.market_data.market_data_sqlite_store import (
    DealDisclosureKind,
    MarketDataSqliteStore,
)
from nse_algo_trader.market_data.nse_official_reports import (
    parse_bulk_or_block_deals,
    parse_cash_bhavcopy_with_delivery,
    parse_fo_ban_list,
    parse_fo_bhavcopy_contract_rows,
    parse_mwpl_position_limits,
)
from tests.fixtures.sample_nse_official_report_texts import (
    SAMPLE_BULK_DEALS_CSV,
    SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV,
    SAMPLE_FO_BAN_LIST_CSV,
    SAMPLE_FO_BHAVCOPY_CSV,
    SAMPLE_MWPL_POSITION_LIMIT_CSV,
)

SAMPLE_TRADE_DATE = date(2026, 7, 22)


@pytest.fixture
def sqlite_store(tmp_path: Path):
    store = MarketDataSqliteStore(tmp_path / "market_data.sqlite3")
    yield store
    store.close()


def _sample_price_bar(minute: int, close_price: float) -> PriceBar:
    return PriceBar(
        instrument_token=408065,
        timestamp=datetime(2026, 7, 22, 9, minute, tzinfo=timezone.utc),
        interval=BarInterval.MINUTE_5,
        open_price=100.0, high_price=101.0, low_price=99.0,
        close_price=close_price, volume=1000, open_interest=None,
    )


class TestBitemporalAvailabilityTime:
    """L0 (research/167): a bar is only readable AS-OF a moment once it has CLOSED — the structural
    look-ahead guard. A 5-min bar stamped 09:15 becomes available at 09:20."""

    def test_as_of_excludes_a_bar_that_has_not_closed_yet(self, sqlite_store):
        sqlite_store.save_price_bars([_sample_price_bar(15, 100.5)])  # closes 09:20
        before_close = datetime(2026, 7, 22, 9, 17, tzinfo=timezone.utc)
        assert sqlite_store.load_price_bars(
            408065, BarInterval.MINUTE_5, as_of=before_close
        ) == []

    def test_as_of_includes_a_bar_at_and_after_its_close(self, sqlite_store):
        sqlite_store.save_price_bars([_sample_price_bar(15, 100.5)])  # closes 09:20
        at_close = datetime(2026, 7, 22, 9, 20, tzinfo=timezone.utc)
        later = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
        assert len(sqlite_store.load_price_bars(408065, BarInterval.MINUTE_5, as_of=at_close)) == 1
        assert len(sqlite_store.load_price_bars(408065, BarInterval.MINUTE_5, as_of=later)) == 1

    def test_no_as_of_returns_everything_live_behaviour(self, sqlite_store):
        sqlite_store.save_price_bars([_sample_price_bar(15, 100.5), _sample_price_bar(20, 101.0)])
        assert len(sqlite_store.load_price_bars(408065, BarInterval.MINUTE_5)) == 2

    def test_migration_backfills_a_pre_availability_database(self, tmp_path: Path):
        import sqlite3

        db_path = tmp_path / "legacy.sqlite3"
        legacy = sqlite3.connect(str(db_path))
        legacy.execute(
            "CREATE TABLE price_bars (instrument_token INTEGER NOT NULL, bar_interval TEXT NOT NULL,"
            " bar_timestamp TEXT NOT NULL, open_price REAL NOT NULL, high_price REAL NOT NULL,"
            " low_price REAL NOT NULL, close_price REAL NOT NULL, volume INTEGER NOT NULL,"
            " open_interest INTEGER, PRIMARY KEY (instrument_token, bar_interval, bar_timestamp))"
        )
        legacy.execute(
            "INSERT INTO price_bars VALUES (408065,'5m','2026-07-22T09:15:00+00:00',100,101,99,100.5,1000,NULL)"
        )
        legacy.commit()
        legacy.close()
        # Opening through the store runs the migration: column added + backfilled to the 09:20 close.
        store = MarketDataSqliteStore(db_path)
        try:
            before = datetime(2026, 7, 22, 9, 17, tzinfo=timezone.utc)
            at_close = datetime(2026, 7, 22, 9, 20, tzinfo=timezone.utc)
            assert store.load_price_bars(408065, BarInterval.MINUTE_5, as_of=before) == []
            assert len(store.load_price_bars(408065, BarInterval.MINUTE_5, as_of=at_close)) == 1
            store2 = MarketDataSqliteStore(db_path)  # re-open: migration is idempotent, no double work
            store2.close()
        finally:
            store.close()

    def test_replay_source_respects_as_of(self, sqlite_store):
        from nse_algo_trader.paper_trading.historical_bar_replay_source import (
            HistoricalBarReplaySource,
        )

        sqlite_store.save_price_bars([_sample_price_bar(15, 100.5), _sample_price_bar(25, 101.0)])
        horizon = datetime(2026, 7, 22, 9, 22, tzinfo=timezone.utc)  # after 09:15-bar close, before 09:25's
        source = HistoricalBarReplaySource(
            sqlite_store, [408065], BarInterval.MINUTE_5, as_of=horizon
        )
        bars = source.load_chronological_bars()
        assert len(bars) == 1 and bars[0].close_price == 100.5  # the future bar is withheld


class TestPriceBarPersistence:
    def test_bars_round_trip_in_timestamp_order(self, sqlite_store):
        sqlite_store.save_price_bars(
            [_sample_price_bar(20, 101.0), _sample_price_bar(15, 100.5)]
        )
        loaded_bars = sqlite_store.load_price_bars(408065, BarInterval.MINUTE_5)
        assert [bar.timestamp.minute for bar in loaded_bars] == [15, 20]
        assert loaded_bars[0] == _sample_price_bar(15, 100.5)

    def test_resaving_same_bar_replaces_not_duplicates(self, sqlite_store):
        sqlite_store.save_price_bars([_sample_price_bar(15, 100.5)])
        sqlite_store.save_price_bars([_sample_price_bar(15, 999.0)])
        loaded_bars = sqlite_store.load_price_bars(408065, BarInterval.MINUTE_5)
        assert len(loaded_bars) == 1
        assert loaded_bars[0].close_price == 999.0

    def test_time_range_filter_is_inclusive(self, sqlite_store):
        sqlite_store.save_price_bars(
            [_sample_price_bar(m, 100.0) for m in (15, 20, 25)]
        )
        loaded_bars = sqlite_store.load_price_bars(
            408065,
            BarInterval.MINUTE_5,
            from_timestamp=datetime(2026, 7, 22, 9, 20, tzinfo=timezone.utc),
            to_timestamp=datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc),
        )
        assert [bar.timestamp.minute for bar in loaded_bars] == [20, 25]


class TestNseReportPersistence:
    def test_cash_bhavcopy_rows_round_trip(self, sqlite_store):
        parsed_rows = parse_cash_bhavcopy_with_delivery(
            SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV
        )
        sqlite_store.save_cash_bhavcopy_delivery_rows(parsed_rows)
        loaded_rows = sqlite_store.load_cash_bhavcopy_delivery_rows(SAMPLE_TRADE_DATE)
        assert sorted(loaded_rows, key=lambda r: r.symbol) == sorted(
            parsed_rows, key=lambda r: r.symbol
        )

    def test_fo_contracts_round_trip_with_underlying_filter(self, sqlite_store):
        parsed_rows = parse_fo_bhavcopy_contract_rows(SAMPLE_FO_BHAVCOPY_CSV)
        sqlite_store.save_fo_bhavcopy_contract_rows(parsed_rows)
        abcapital_rows = sqlite_store.load_fo_bhavcopy_contract_rows(
            SAMPLE_TRADE_DATE, underlying_symbol="ABCAPITAL"
        )
        assert len(abcapital_rows) == 2  # the STO and STF fixture rows
        assert {row.underlying_symbol for row in abcapital_rows} == {"ABCAPITAL"}

    def test_ban_list_round_trips_and_missing_date_is_none(self, sqlite_store):
        ban_report = parse_fo_ban_list(SAMPLE_FO_BAN_LIST_CSV)
        sqlite_store.save_fo_ban_list_report(ban_report)
        assert sqlite_store.load_fo_ban_list_report(date(2026, 7, 23)) == ban_report
        assert sqlite_store.load_fo_ban_list_report(date(2026, 1, 1)) is None

    def test_mwpl_rows_round_trip_preserving_ban_marker(self, sqlite_store):
        parsed_rows = parse_mwpl_position_limits(SAMPLE_MWPL_POSITION_LIMIT_CSV)
        sqlite_store.save_mwpl_position_limit_rows(parsed_rows)
        loaded_rows = sqlite_store.load_mwpl_position_limit_rows(SAMPLE_TRADE_DATE)
        assert loaded_rows == sorted(parsed_rows, key=lambda r: r.underlying_symbol)
        assert loaded_rows[1].is_in_ban_period is True  # KAYNES

    def test_deals_reingest_replaces_whole_day_per_kind(self, sqlite_store):
        parsed_deals = parse_bulk_or_block_deals(SAMPLE_BULK_DEALS_CSV)
        sqlite_store.save_bulk_or_block_deal_rows(
            parsed_deals, DealDisclosureKind.BULK_DEAL
        )
        sqlite_store.save_bulk_or_block_deal_rows(
            parsed_deals, DealDisclosureKind.BULK_DEAL
        )
        loaded_deals = sqlite_store.load_bulk_or_block_deal_rows(
            SAMPLE_TRADE_DATE, DealDisclosureKind.BULK_DEAL
        )
        assert len(loaded_deals) == len(parsed_deals)  # no duplication
        assert (
            sqlite_store.load_bulk_or_block_deal_rows(
                SAMPLE_TRADE_DATE, DealDisclosureKind.BLOCK_DEAL
            )
            == []
        )
