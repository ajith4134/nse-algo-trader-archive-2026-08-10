"""Per-leg option greeks from live premiums — Δ Γ ν Θ via the integrated vollib (Peter Jäckel BSM).

Backs off the live LTP marking (slice 4) with a real pricing model: invert the live premium to an IV, then
compute the greeks. Feeds the marker's net-structure greeks (dashboard) and the book-risk engine's portfolio
net greeks. Robust: an un-invertible premium (deep ITM/OTM, near expiry) yields a zeroed greek set rather than
raising — the caller degrades gracefully (Rule O).
"""

from __future__ import annotations

from dataclasses import dataclass

_MIN_TENOR = 1.0 / (365.0 * 24.0)  # 1 hour — avoid a zero-tenor blow-up at expiry


@dataclass(frozen=True)
class LegGreeks:
    iv: float
    delta: float
    gamma: float
    vega: float
    theta: float


_ZERO = LegGreeks(0.0, 0.0, 0.0, 0.0, 0.0)


def leg_greeks(right: str, strike: float, spot: float, tenor_years: float, rate: float, premium: float) -> LegGreeks:
    """IV (from the live premium) + Δ Γ ν Θ for one option leg. Returns zeros if the premium can't be inverted."""
    if spot <= 0 or strike <= 0 or premium <= 0:
        return _ZERO
    tenor = max(float(tenor_years), _MIN_TENOR)
    flag = "c" if str(right).upper().startswith("C") else "p"
    try:
        from vollib.black_scholes.implied_volatility import implied_volatility
        from vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega

        iv = float(implied_volatility(premium, spot, strike, tenor, rate, flag))
        if not (iv > 0) or iv > 5.0:
            return _ZERO
        return LegGreeks(
            iv=round(iv, 4),
            delta=round(float(delta(flag, spot, strike, tenor, rate, iv)), 4),
            gamma=round(float(gamma(flag, spot, strike, tenor, rate, iv)), 6),
            vega=round(float(vega(flag, spot, strike, tenor, rate, iv)), 4),
            theta=round(float(theta(flag, spot, strike, tenor, rate, iv)), 4),
        )
    except Exception:  # noqa: BLE001 — un-invertible premium / model edge → zeroed greeks, never raise
        return _ZERO


def net_structure_greeks(legs: list[dict], spot: float, tenor_years: float, rate: float, lot_size: int,
                        lots: int) -> LegGreeks:
    """Net Δ Γ ν Θ of a whole structure = Σ over legs (sell = −, buy = +) × lot_size × lots."""
    scale = max(int(lot_size), 1) * max(int(lots), 1)
    nd = ng = nv = nt = 0.0
    for leg in legs:
        cur = leg.get("current_price") or leg.get("entry_price")
        if cur is None:
            continue
        g = leg_greeks(str(leg.get("right")), float(leg.get("strike", 0.0)), spot, tenor_years, rate, float(cur))
        s = 1.0 if str(leg.get("side")) == "buy" else -1.0
        nd += s * g.delta * scale
        ng += s * g.gamma * scale
        nv += s * g.vega * scale
        nt += s * g.theta * scale
    return LegGreeks(iv=0.0, delta=round(nd, 2), gamma=round(ng, 4), vega=round(nv, 2), theta=round(nt, 2))
