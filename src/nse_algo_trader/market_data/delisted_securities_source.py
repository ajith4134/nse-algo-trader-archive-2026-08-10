"""Delisted-securities master — a free cross-source for §53 survivorship work
(task #13; research/79).

Helps distinguish a **delisted** (permanently gone) name from one that is merely
**suspended / untraded** when reconstructing the point-in-time universe from
bhavcopy. NSE's own delisted list is bot-blocked; BSE's `ListofScripData` API is
free, open, and carries **ISIN** (so it keys to our ISIN-keyed reference data).
BSE ≠ NSE, so this is a corroborating cross-source, combined with the
bhavcopy-presence-gap signal — not an NSE authority on its own.

The adapter does network I/O only when called (not at import), so it sits behind
the `DelistedSecuritiesSource` DI seam and tests inject a fake / a real sample.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_BSE_DELISTED_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
    "?Group=&Scripcode=&industry=&segment=Equity&status=Delisted"
)
# BSE's API rejects non-browser clients; this UA + Referer is the documented
# anti-bot handshake (research/79), not an auth bypass.
_BSE_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}


@dataclass(frozen=True)
class DelistedSecurity:
    """One delisted security. `isin` is the join key to our reference data;
    `symbol` is BSE's scrip_id (closest to an NSE trading symbol) for name matching."""

    isin: str
    name: str
    symbol: str
    scrip_code: str
    source: str  # e.g. "bse"


@runtime_checkable
class DelistedSecuritiesSource(Protocol):
    def fetch_delisted_securities(self) -> list[DelistedSecurity]: ...


class BseDelistedSecuritiesSource:
    """Fetches BSE's free delisted-equity list and yields broker-neutral records."""

    def __init__(self, delisted_url: str = _BSE_DELISTED_URL, timeout_seconds: int = 40):
        self._delisted_url = delisted_url
        self._timeout_seconds = timeout_seconds

    def fetch_delisted_securities(self) -> list[DelistedSecurity]:
        request = urllib.request.Request(self._delisted_url, headers=_BSE_REQUEST_HEADERS)
        raw = urllib.request.urlopen(request, timeout=self._timeout_seconds).read()
        return parse_bse_delisted_rows(json.loads(raw.decode("utf-8", "replace")))


def parse_bse_delisted_rows(raw_response) -> list[DelistedSecurity]:
    """Parse BSE's ListofScripData JSON (a list of dicts, or a dict wrapping one)
    into `DelistedSecurity` records. Rows without an ISIN are skipped (the ISIN is
    the whole point — the join key)."""
    if isinstance(raw_response, list):
        rows = raw_response
    elif isinstance(raw_response, dict):
        rows = raw_response.get("Table") or next(
            (v for v in raw_response.values() if isinstance(v, list)), []
        )
    else:
        rows = []
    delisted: list[DelistedSecurity] = []
    for row in rows:
        isin = (row.get("ISIN_NUMBER") or "").strip()
        if not isin:
            continue
        delisted.append(
            DelistedSecurity(
                isin=isin,
                name=(row.get("Scrip_Name") or "").strip(),
                symbol=(row.get("scrip_id") or "").strip(),
                scrip_code=str(row.get("SCRIP_CD") or "").strip(),
                source="bse",
            )
        )
    return delisted


class DelistedSecuritiesMaster:
    """An in-memory lookup over stored delisted records — `is_delisted_isin` /
    `is_delisted_symbol` for consumers (the §53 suspension-vs-delisting test and the
    universe-gap cross-check)."""

    def __init__(self, delisted_securities: list[DelistedSecurity]):
        self._by_isin = {d.isin for d in delisted_securities}
        self._by_symbol = {d.symbol.upper() for d in delisted_securities if d.symbol}

    def is_delisted_isin(self, isin: str) -> bool:
        return isin in self._by_isin

    def is_delisted_symbol(self, symbol: str) -> bool:
        return symbol.upper() in self._by_symbol

    def delisted_isin_count(self) -> int:
        return len(self._by_isin)
