"""Assembles the segment-bot pod board data for the ``/pod`` dashboard route (Rule N).

Fast path: build the pod on the production market-store adapters (so each bot's competency reflects its real
persisted track record) and render from the runner's LAST persisted cycle snapshot — the board reads, it
does not run the (heavy) cycle on the web request. The cycle is produced by ``PodRunner`` on the live-loop
tick (or on demand); until that tick has run, the board honestly shows "no cycle yet".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nse_algo_trader.portfolio_supervisor.pod_runner import PodRunner

_IST = timezone(timedelta(hours=5, minutes=30))


def pod_board_html() -> str:
    """Build the full pod board HTML for the ``/pod`` route (reads competencies + last persisted cycle)."""
    from nse_algo_trader.dashboard.render_pod_dashboard_html import render_pod_dashboard_html

    generated_at = datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
    runner = PodRunner()  # production adapters; constructing does not run a cycle
    cycle = PodRunner.load_last_cycle()
    return render_pod_dashboard_html(runner.bots, cycle, generated_at)
