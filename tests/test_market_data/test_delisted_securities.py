"""§53 task #13 — delisted-securities master (hermetic, Rule J + env-gated Rule F)."""

import os

import pytest

from nse_algo_trader.market_data.delisted_securities_ingestion_job import (
    ingest_delisted_securities,
)
from nse_algo_trader.market_data.delisted_securities_source import (
    BseDelistedSecuritiesSource,
    DelistedSecuritiesMaster,
    DelistedSecurity,
    parse_bse_delisted_rows,
)
from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore

# A trimmed real-shaped BSE ListofScripData response (a list of dicts).
_BSE_SAMPLE = [
    {"SCRIP_CD": "500004", "Scrip_Name": "Torrent Power AEC Ltd", "Status": "Delisted",
     "ISIN_NUMBER": "INE424A01014", "scrip_id": "TPAEC"},
    {"SCRIP_CD": "500002", "Scrip_Name": "ABB Ltd Old", "Status": "Delisted",
     "ISIN_NUMBER": "INE117A01013", "scrip_id": "ABBOLD"},
    {"SCRIP_CD": "999999", "Scrip_Name": "No ISIN Co", "Status": "Delisted",
     "ISIN_NUMBER": "", "scrip_id": "NOISIN"},  # skipped: no ISIN
]


def test_parse_skips_rows_without_isin():
    parsed = parse_bse_delisted_rows(_BSE_SAMPLE)
    assert [d.isin for d in parsed] == ["INE424A01014", "INE117A01013"]
    assert parsed[0].name == "Torrent Power AEC Ltd"
    assert parsed[0].symbol == "TPAEC" and parsed[0].source == "bse"


def test_parse_handles_dict_wrapped_variant():
    parsed = parse_bse_delisted_rows({"Table": _BSE_SAMPLE})
    assert len(parsed) == 2


def test_store_roundtrip(tmp_path):
    store = MarketDataSqliteStore(tmp_path / "m.sqlite3")
    records = parse_bse_delisted_rows(_BSE_SAMPLE)
    assert store.save_delisted_securities(records) == 2
    loaded = store.load_delisted_securities()
    assert {d.isin for d in loaded} == {"INE424A01014", "INE117A01013"}
    assert store.save_delisted_securities(records) == 2  # idempotent (INSERT OR REPLACE)
    assert len(store.load_delisted_securities(source="bse")) == 2


def test_master_lookup():
    master = DelistedSecuritiesMaster(parse_bse_delisted_rows(_BSE_SAMPLE))
    assert master.is_delisted_isin("INE424A01014")
    assert not master.is_delisted_isin("INE999Z01011")  # a live name
    assert master.is_delisted_symbol("tpaec")  # case-insensitive
    assert master.delisted_isin_count() == 2


class _FakeDelistedSource:
    def fetch_delisted_securities(self):
        return parse_bse_delisted_rows(_BSE_SAMPLE)


def test_ingestion_job_stores_via_injected_source(tmp_path):
    store = MarketDataSqliteStore(tmp_path / "m.sqlite3")
    count = ingest_delisted_securities(
        delisted_securities_source=_FakeDelistedSource(), market_data_store=store
    )
    assert count == 2
    assert len(store.load_delisted_securities()) == 2


def test_real_bse_delisted_fetch():
    """Rule F: live BSE delisted list has 1000s of real ISIN-carrying rows.
    Env-gated so the suite stays offline; run with RUN_BSE_NETWORK_TEST=1."""
    if not os.environ.get("RUN_BSE_NETWORK_TEST"):
        pytest.skip("network test — set RUN_BSE_NETWORK_TEST=1 to run")
    delisted = BseDelistedSecuritiesSource().fetch_delisted_securities()
    assert len(delisted) > 1000
    assert all(d.isin for d in delisted)
    assert all(d.source == "bse" for d in delisted)
