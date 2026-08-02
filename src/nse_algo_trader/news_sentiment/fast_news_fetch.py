"""Fast, ban-resistant static page fetch for near-live news acquisition (Trunk II SENSES S4b; research/144).

`curl_cffi` impersonates a real Chrome TLS/JA3 fingerprint — the single highest-leverage anti-block
fix (research/143 Agent C): it defeats the fingerprint layer that instantly flags plain `requests`/
`httpx`, while being ~130× faster than a headless-Chromium render (0.3 s vs ~40 s, real-measured on
this box 2026-07-26). Used as the FAST rung of the acquisition ladder; only prod imports curl_cffi,
so the fetch stays behind the ladder's DI seam (Rule J). Returns "" on any failure — one bad page
never breaks the poll.
"""

from __future__ import annotations

_FAST_FETCH_TIMEOUT_SECONDS = 25
_IMPERSONATE = "chrome"  # curl_cffi picks a current Chrome TLS/JA3 profile


def fast_fetch_html(url: str) -> str:
    """Static HTML via curl_cffi with a real-Chrome fingerprint. "" on non-200 / error (never raises)."""
    try:
        from curl_cffi import requests as curl_requests

        response = curl_requests.get(
            url, impersonate=_IMPERSONATE, timeout=_FAST_FETCH_TIMEOUT_SECONDS  # type: ignore[arg-type]  # curl_cffi Literal over-strict on str const
        )
        if response.status_code != 200:
            return ""
        return response.text or ""
    except Exception:
        return ""
