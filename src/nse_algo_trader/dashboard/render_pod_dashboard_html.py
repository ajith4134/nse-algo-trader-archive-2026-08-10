"""Render the segment-bot POD board — the per-bot + supervisor dashboard surface (Rule N).

Surfaces the live pod: each bot's segment + competency (earned/gathering + level + closed trades), and the
supervisor's latest decision — allocation mode, portfolio-CVaR vs the hard-stop budget, per-underlying
net-exposure, and the arbitrated order table. Self-contained (inline CSS+JS, no CDN), theme-aware, with a
status palette that is always label+colour (never colour alone — dataviz).
"""

from __future__ import annotations

import html


def _e(text) -> str:
    return html.escape(str(text), quote=True)


def _competency_badge(is_earned: bool) -> str:
    label, role = ("EARNED", "good") if is_earned else ("GATHERING", "muted")
    return f'<span class="badge b-{role}">{label}</span>'


def _bot_card(bot) -> str:
    comp = bot.competency()
    return (
        f'<div class="card"><div class="card-head"><span class="seg">{_e(bot.segment.value)}</span>'
        f'{_competency_badge(comp.is_earned)}</div>'
        f'<div class="card-title">{_e(bot.name)}</div>'
        f'<div class="metrics"><span>level <b>{comp.level}/5</b></span>'
        f'<span>closed <b>{comp.closed_trades}</b></span></div></div>'
    )


def _orders_table(cycle: dict | None) -> str:
    orders = (cycle or {}).get("orders") or []
    if not orders:
        return '<p class="muted">No orders in the last cycle (gated by competency / advisory allocator until earned).</p>'
    rows = []
    for o in orders:
        outcome = str(o.get("outcome", ""))
        role = {"accept": "good", "resize": "warning", "veto": "serious"}.get(outcome, "muted")
        rows.append(
            f"<tr><td>{_e(o.get('underlying'))}</td><td>{_e(o.get('structure'))}</td>"
            f'<td>{_e(o.get("side"))}</td><td class="num">{_e(o.get("lots"))}</td>'
            f'<td><span class="badge b-{role}">{_e(outcome.upper())}</span></td></tr>'
        )
    return ('<table><thead><tr><th>underlying</th><th>structure</th><th>side</th><th>lots</th>'
            '<th>outcome</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")


def render_pod_dashboard_html(bots, cycle: dict | None, generated_at_ist: str) -> str:
    """Render the pod board from live bot competencies + the runner's last persisted cycle snapshot."""
    cvar_pct = round(100 * float((cycle or {}).get("portfolio_cvar_fraction", 0.0)), 2)
    scale = float((cycle or {}).get("hard_stop_scale", 1.0))
    hard_stop = f"engaged ×{scale:.2f}" if scale < 1.0 else "clear"
    alarms = ", ".join((cycle or {}).get("price_divergence_alarms", [])) or "none"
    mode = (cycle or {}).get("allocation_mode", "—")
    solver = (cycle or {}).get("solver_status", "no cycle yet")
    placed = (cycle or {}).get("orders_placed", 0)
    tiles = "".join([
        f'<div class="tile"><div class="tv">{len(bots)}</div><div class="tl">SEGMENT BOTS</div></div>',
        f'<div class="tile"><div class="tv">{(cycle or {}).get("total_proposals", 0)}</div><div class="tl">PROPOSALS</div></div>',
        f'<div class="tile"><div class="tv">{(cycle or {}).get("accepted_orders", 0)}</div><div class="tl">ACCEPTED</div></div>',
        f'<div class="tile"><div class="tv">{placed}</div><div class="tl">PLACED</div></div>',
        f'<div class="tile"><div class="tv">{cvar_pct}%</div><div class="tl">PORTFOLIO CVaR</div></div>',
        f'<div class="tile"><div class="tv" style="font-size:16px">{_e(mode)}</div><div class="tl">ALLOC MODE</div></div>',
        f'<div class="tile"><div class="tv" style="font-size:16px">{_e(hard_stop)}</div><div class="tl">HARD STOP</div></div>',
        f'<div class="tile"><div class="tv" style="font-size:16px">{_e((cycle or {}).get("crowding_level", "—"))}</div><div class="tl">CROWDING</div></div>',
        f'<div class="tile"><div class="tv" style="font-size:13px">{_e((cycle or {}).get("dispersion", {}).get("action", "—"))}</div><div class="tl">DISPERSION ρ {_e(round((cycle or {}).get("dispersion", {}).get("implied_correlation", 0.0), 2))}</div></div>',
    ])
    return _TEMPLATE.format(
        css=_CSS, generated_at=_e(generated_at_ist), tiles=tiles,
        bot_cards="".join(_bot_card(b) for b in bots),
        orders=_orders_table(cycle), solver=_e(solver), alarms=_e(alarms),
    )


_CSS = """
:root{--bg:#E9EDF0;--panel:#fff;--ink:#0F171C;--ink2:#47555F;--ink3:#6F7E89;--rule:#D2DAE0;
--good:#1E7A46;--warning:#A2650F;--serious:#B4331F;--muted:#8A97A0;--accent:#0E4E63}
@media(prefers-color-scheme:dark){:root{--bg:#0C1116;--panel:#131A21;--ink:#E6ECF1;--ink2:#A7B4BE;
--ink3:#7C8A95;--rule:#26313B;--good:#3FB673;--warning:#E0A63C;--serious:#E06A54;--accent:#5AB0C8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 2px}.gen{color:var(--ink3);font-size:12px;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:16px}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:12px}
.tv{font-size:24px;font-weight:700;color:var(--accent)}.tl{font-size:11px;letter-spacing:.06em;color:var(--ink2);margin-top:2px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;margin-bottom:18px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:12px}
.card-head{display:flex;justify-content:space-between;margin-bottom:4px}.seg{font-size:11px;color:var(--ink3);letter-spacing:.05em}
.card-title{font-weight:700}.metrics{display:flex;gap:14px;color:var(--ink2);font-size:13px;margin-top:4px}
h2{font-size:15px;margin:18px 0 6px;border-bottom:2px solid var(--rule);padding-bottom:3px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:var(--ink3);font-weight:600;font-size:11px;letter-spacing:.04em}
td,th{padding:6px 8px;border-bottom:1px solid var(--rule)}.num{text-align:right;font-variant-numeric:tabular-nums}
.rat{color:var(--ink2);font-size:12px}.muted{color:var(--ink3)}
.badge{border-radius:5px;padding:1px 7px;font-size:10px;font-weight:700;color:#fff;letter-spacing:.04em}
.b-good{background:var(--good)}.b-warning{background:var(--warning)}.b-serious{background:var(--serious)}.b-muted{background:var(--muted)}
"""

_TEMPLATE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Segment-Bot Pod — NSE</title>
<style>{css}</style></head><body><div class=wrap>
<h1>Segment-Bot Pod</h1>
<p class=gen>3 segment-specialist bots + portfolio supervisor · solver <b>{solver}</b> · price-divergence alarms: {alarms} · {generated_at}</p>
{tiles}
<h2>Bots</h2><div class=cards>{bot_cards}</div>
<h2>Arbitrated orders (last cycle)</h2>{orders}
</div></body></html>"""
