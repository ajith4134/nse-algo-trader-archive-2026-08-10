"""Live option-chain feed — today's real CE/PE strikes, LTP, OI and expiry for the index option bots.

The bots previously ran on a stale stored F&O bhavcopy snapshot, so they could never trade the LIVE options a
trader sees. This assembles the real chain from a broker: resolve the underlying's option instruments, center
a strike window on the live index spot, batch-fetch live quotes (LTP + OI), and return a DataFrame in the
exact schema the IV-surface engine consumes (``option_right_code``, ``strike_price``, ``close_price``,
``underlying_price``, ``expiry_date``, ``open_interest``, ``total_traded_volume``).

Kite-decoupled: the broker call goes through the ``broker_sessions`` seam (``build_authenticated_kite_client_if_valid``)
— this module never ``import kiteconnect`` directly, so the architecture guard holds. Multi-broker: providers
are tried in reliability order (``MultiBrokerLiveOptionChainSource``); Kite is the first (active session, full
NFO + BFO coverage); Upstox / Angel / Breeze / Groww are queued additional providers (Rule K). If no provider
returns a chain, the caller falls back to the stored bhavcopy — the feed never crashes a cycle (Rule J).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

import pandas as pd

# project underlying → (broker option-instrument "name", exchange segment, index spot LTP symbol)
_INDEX_SPEC: dict[str, tuple[str, str, str]] = {
    "NIFTY": ("NIFTY", "NFO", "NSE:NIFTY 50"),
    "BANKNIFTY": ("BANKNIFTY", "NFO", "NSE:NIFTY BANK"),
    "FINNIFTY": ("FINNIFTY", "NFO", "NSE:NIFTY FIN SERVICE"),
    "MIDCPNIFTY": ("MIDCPNIFTY", "NFO", "NSE:NIFTY MID SELECT"),
    "NIFTYNXT50": ("NIFTYNXT50", "NFO", "NSE:NIFTY NEXT 50"),
    "SENSEX": ("SENSEX", "BFO", "BSE:SENSEX"),
    "BANKEX": ("BANKEX", "BFO", "BSE:BANKEX"),
}
_STRIKE_WINDOW = 20  # strikes each side of ATM (ITM/ATM/OTM ladder), keeps the quote batch small
_CHAIN_CACHE_SECONDS = 45  # one live fetch serves a burst of same-cycle calls


def _spec_for(underlying: str) -> tuple[str, str, str]:
    """(broker option-name, exchange segment, spot LTP symbol) for an index OR a single-stock F&O underlying.

    Indices carry a distinct spot symbol; a stock option's name IS the equity symbol and its spot is the NSE
    cash quote. A stock with no listed options simply yields an empty chain (caller falls back to stored).
    """
    if underlying in _INDEX_SPEC:
        return _INDEX_SPEC[underlying]
    return (underlying, "NFO", f"NSE:{underlying}")


class LiveOptionChainSource(Protocol):
    """A broker-agnostic live option-chain provider."""

    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str, float] | None:
        """(chain_df, trade_date_iso, spot) in the canonical schema, or None if unavailable for this name."""
        ...


class KiteLiveOptionChainSource:
    """Live option chain from Zerodha Kite (NFO for NSE indices, BFO for SENSEX/BANKEX)."""

    def __init__(self, now_provider=None):
        self._kite = None
        self._kite_loaded = False
        self._instruments: dict[str, list[dict]] = {}  # segment → instrument dump (cached per process)
        self._chain_cache: dict[str, tuple[float, tuple[pd.DataFrame, str, float]]] = {}
        self._now = now_provider or datetime.now

    def _client(self):
        if not self._kite_loaded:
            try:
                from nse_algo_trader.broker_sessions.authenticated_kite_client_builder import (
                    build_authenticated_kite_client_if_valid,
                )

                self._kite = build_authenticated_kite_client_if_valid()
            except Exception:  # noqa: BLE001 — no session → provider simply yields nothing
                self._kite = None
            self._kite_loaded = True
        return self._kite

    def _segment_instruments(self, segment: str) -> list[dict]:
        if segment not in self._instruments:
            kite = self._client()
            self._instruments[segment] = kite.instruments(segment) if kite is not None else []
        return self._instruments[segment]

    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str, float] | None:
        spec = _spec_for(underlying)  # index (mapped) or single-stock F&O (name=symbol, NFO)
        cached = self._chain_cache.get(underlying)
        now_ts = self._now().timestamp()
        if cached is not None and (now_ts - cached[0]) < _CHAIN_CACHE_SECONDS:
            return cached[1]
        try:
            result = self._fetch_chain(underlying, spec)
        except Exception:  # noqa: BLE001 — a broker hiccup must never crash the cycle (Rule J fallback)
            return None
        if result is not None:
            self._chain_cache[underlying] = (now_ts, result)
        return result

    def _fetch_chain(self, underlying: str, spec: tuple[str, str, str]) -> tuple[pd.DataFrame, str, float] | None:
        kite = self._client()
        if kite is None:
            return None
        name, segment, spot_symbol = spec

        spot_quote = kite.ltp([spot_symbol])
        spot = float(spot_quote.get(spot_symbol, {}).get("last_price", 0.0) or 0.0)
        if spot <= 0:
            return None

        options = [r for r in self._segment_instruments(segment)
                   if r.get("name") == name and r.get("instrument_type") in ("CE", "PE")]
        if not options:
            return None
        today = self._now().date()
        future_expiries = sorted({self._as_date(r["expiry"]) for r in options if self._as_date(r["expiry"]) >= today})
        if not future_expiries:
            return None
        expiry = future_expiries[0]  # nearest non-expired expiry
        legs = [r for r in options if self._as_date(r["expiry"]) == expiry]

        strikes = sorted({float(r["strike"]) for r in legs})
        atm = min(strikes, key=lambda k: abs(k - spot))
        atm_i = strikes.index(atm)
        window = set(strikes[max(0, atm_i - _STRIKE_WINDOW): atm_i + _STRIKE_WINDOW + 1])
        window_legs = [r for r in legs if float(r["strike"]) in window]

        quote_keys = [f"{segment}:{r['tradingsymbol']}" for r in window_legs]
        quotes = kite.quote(quote_keys)
        rows = []
        for r in window_legs:
            q = quotes.get(f"{segment}:{r['tradingsymbol']}", {})
            ltp = float(q.get("last_price", 0.0) or 0.0)
            oi = float(q.get("oi", 0.0) or 0.0)
            vol = float(q.get("volume", 0.0) or 0.0)
            rows.append({
                "option_right_code": r["instrument_type"],
                "strike_price": float(r["strike"]),
                "close_price": ltp,
                "underlying_price": spot,
                "expiry_date": expiry.isoformat(),
                "open_interest": oi,
                "total_traded_volume": vol,
                "lot_size": int(r.get("lot_size", 0) or 0),  # exchange contract lot from the live instrument
            })
        chain = pd.DataFrame(rows)
        chain = chain[chain["close_price"] > 0]  # unpriced strikes are useless to the IV engine
        if chain.empty:
            return None
        return (chain.reset_index(drop=True), today.isoformat(), spot)

    @staticmethod
    def _as_date(value) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])


    def resolve_instrument(self, underlying: str, right: str, strike: float, expiry: str):
        """Find the REAL option instrument (tradingsymbol, token, lot_size) for a leg — for live order routing.

        Matches the synthesized leg's exact strike + right + expiry against the live instrument dump, so a
        routed order carries the true contract (not a synthetic moneyness-derived one). None → caller falls back.
        """
        spec = _INDEX_SPEC.get(underlying, (underlying, "NFO", ""))
        name, segment, _ = spec
        want_right = "CE" if str(right).upper().startswith("C") else "PE"
        try:
            want_exp = self._as_date(expiry)
            for r in self._segment_instruments(segment):
                if (r.get("name") == name and r.get("instrument_type") == want_right
                        and abs(float(r.get("strike", 0.0)) - float(strike)) < 0.01
                        and self._as_date(r["expiry"]) == want_exp):
                    return {"tradingsymbol": r["tradingsymbol"], "instrument_token": int(r["instrument_token"]),
                            "lot_size": int(r.get("lot_size", 0) or 0), "exchange": segment}
        except Exception:  # noqa: BLE001 — resolution failure falls back to the synthetic leg
            return None
        return None


class MultiBrokerLiveOptionChainSource:
    """Tries each broker provider in reliability order; the first non-empty live chain wins (failover)."""

    def __init__(self, providers: list | None = None):
        self._providers = providers if providers is not None else [KiteLiveOptionChainSource()]

    def option_chain(self, underlying: str) -> tuple[pd.DataFrame, str, float] | None:
        for provider in self._providers:
            try:
                result = provider.option_chain(underlying)
            except Exception:  # noqa: BLE001 — a failing provider must not stop the next one
                result = None
            if result is not None and not result[0].empty:
                return result
        return None

    def resolve_instrument(self, underlying: str, right: str, strike: float, expiry: str):
        for provider in self._providers:
            resolve = getattr(provider, "resolve_instrument", None)
            if resolve is None:
                continue
            found = resolve(underlying, right, strike, expiry)
            if found is not None:
                return found
        return None
