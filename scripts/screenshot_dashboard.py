"""Screenshot the live advanced dashboard — the standing "verify it landed" check after every feature/edit.

Standing rule (`feedback_screenshot_dashboard_after_every_change`): a passing test is NOT proof the page
rendered. This captures the real dashboard so the change can be SEEN. Reads the capability token, drives
headless Chromium (Playwright), saves a full-page PNG, and prints the page title + a scan for the panels
a given feature should surface (so you can grep the shot for "did my thing appear").

Usage:
  python scripts/screenshot_dashboard.py                       # → logs/dashboard_latest.png
  python scripts/screenshot_dashboard.py --out /tmp/x.png
  python scripts/screenshot_dashboard.py --expect subscription --expect served-by   # scan for these
  python scripts/screenshot_dashboard.py --url http://localhost:8080 --port 8080
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import anyio

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = Path("~/.nse_algo_trader/dashboard_access_token.txt").expanduser()
DEFAULT_OUT = REPO_ROOT / "logs" / "dashboard_latest.png"


def _read_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(f"no dashboard token at {TOKEN_PATH} — is the dashboard server running?")
    return TOKEN_PATH.read_text().strip()


async def _capture(url: str, out: Path, expect: list[str]) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SystemExit("playwright not installed: .venv/bin/pip install playwright && playwright install chromium")
    out.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1600, "height": 1000})
            resp = await page.goto(url, wait_until="networkidle", timeout=60000)
            status = resp.status if resp else 0
            await page.wait_for_timeout(1500)
            title = await page.title()
            body = await page.inner_text("body")
            await page.screenshot(path=str(out), full_page=True)
        finally:
            await browser.close()
    ok = status == 200 and bool(title)
    print(f"HTTP {status} · title={title!r} · saved {out}")
    if not ok:
        print("⚠️ page did NOT render cleanly — inspect the shot", file=sys.stderr)
    for token in expect:
        found = re.search(re.escape(token), body, re.IGNORECASE) is not None
        print(f"  expect {token!r}: {'✅ present' if found else '❌ NOT on page'}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Screenshot the live dashboard to verify a change landed.")
    ap.add_argument("--url", default=None, help="base URL (default http://localhost:PORT)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--expect", action="append", default=[], help="text a feature should surface; repeatable")
    ap.add_argument("--path", default="/", help="dashboard path to shoot (e.g. /wall, /catalogue); default /")
    args = ap.parse_args(argv)
    base = args.url or f"http://localhost:{args.port}"
    sep = "&" if "?" in args.path else "?"
    url = f"{base}{args.path}{sep}key={_read_token()}"
    return anyio.run(_capture, url, args.out, args.expect)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
