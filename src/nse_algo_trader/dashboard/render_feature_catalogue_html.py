"""Render the project-wide Feature Catalogue as a self-contained HTML page.

Two surfaces over one measured dataset (see ``feature_catalogue_status_prober`` — Rule R):
  * **Catalogue** — every feature by phase, forgotten rows amber-railed, filterable; the "plan" view.
  * **Status Wall** — a card grid whose badge is the MEASURED build status + the real source file; the
    "true-to-server" view, footered "generated · never hand-edited · measured <ts>".
  * **Atlas** — the 16-trunk / 197-branch cognitive tree with measured coverage.

The page is fully static (inline CSS+JS, no CDN) and theme-aware (light/dark). Status is always shown as a
text badge (label + colour, never colour alone) so identity never depends on colour (dataviz / Rule R).
"""

from __future__ import annotations

import html

from nse_algo_trader.dashboard.feature_catalogue_status_prober import (
    STATUS_DISPLAY,
    FeatureCatalogueMeasurement,
    MeasuredFeatureRow,
    measure_feature_catalogue,
)

# Functional catalogue sections first (crypto order), then the 16 atlas trunks in canonical order.
_FUNCTIONAL_SECTION_ORDER = [
    "Market data & ingestion",
    "Feature engineering",
    "Models",
    "Strategy families",
    "Execution",
    "Options layer",
    "Risk",
    "Portfolio",
    "Validation & research",
    "Operations",
    "Security",
    "Intelligence",
    "Governance",
    "Observability",
    "Dashboard",
    "Cognition/AI-organism",
]
_ATLAS_TRUNK_ORDER = [
    "I MIND",
    "II SENSES",
    "III WILL",
    "IV BODY",
    "V SELF",
    "VI SOCIETY",
    "VII CONSCIENCE",
    "VIII SENTIENCE & GLOBAL WORKSPACE",
    "IX PREDICTIVE CORE / ACTIVE INFERENCE",
    "X AUTOPOIESIS / SELF-PRODUCTION",
    "XI GENERATIVITY & OPEN-ENDEDNESS",
    "XII INTRINSIC MOTIVATION / CURIOSITY",
    "XIII EPISTEMICS / TRUTH & UNCERTAINTY",
    "XIV AXIOLOGY / VALUES & PRACTICAL WISDOM",
    "XV MEMORY & KNOWLEDGE BASE",
    "XVI UNIVERSAL ACCESS & ACQUISITION",
]
_PHASE_ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "—"]


def _e(text: str) -> str:
    return html.escape(text or "", quote=True)


def _phase_pill(phase: str) -> str:
    cls = phase.lower() if phase.startswith("P") else "none"
    return f'<span class="phase phase-{cls}">{_e(phase)}</span>'


def _status_badge(measured_status: str) -> str:
    label, role = STATUS_DISPLAY.get(measured_status, (measured_status.upper(), "muted"))
    return f'<span class="status status-{role}" data-status="{_e(measured_status)}">{_e(label)}</span>'


def _row_search_blob(row: MeasuredFeatureRow) -> str:
    return _e(" ".join([row.feature, row.note, row.section, " ".join(row.sources)]).lower())


def _catalogue_row_html(row: MeasuredFeatureRow) -> str:
    forgotten_cls = " forgotten" if row.forgotten else ""
    missed_tag = '<span class="missed">MISSED</span>' if row.forgotten else ""
    return (
        f'<div class="row{forgotten_cls}" data-phase="{_e(row.phase)}" '
        f'data-status="{_e(row.measured_status)}" data-forgotten="{"1" if row.forgotten else "0"}" '
        f'data-text="{_row_search_blob(row)}">'
        f'<div class="cell-feature"><span class="fname">{_e(row.feature)}</span> {missed_tag}</div>'
        f'<div class="cell-phase">{_phase_pill(row.phase)}</div>'
        f'<div class="cell-note">{_e(row.note)}</div>'
        f"</div>"
    )


def _card_html(row: MeasuredFeatureRow) -> str:
    ref = row.code_reference or ("no code" if not row.code_present else "")
    measured_line = _e(row.note)[:180] if row.note else ("code present" if row.code_present else "designed only; no code and no measurement")
    forgotten_cls = " forgotten" if row.forgotten else ""
    orphan_tag = '<span class="missed orphan-tag">ORPHAN</span>' if row.is_orphan else ""
    return (
        f'<div class="card{forgotten_cls}" data-phase="{_e(row.phase)}" '
        f'data-status="{_e(row.measured_status)}" data-forgotten="{"1" if row.forgotten else "0"}" '
        f'data-text="{_row_search_blob(row)}">'
        f'<div class="card-head">{_phase_pill(row.phase)}{orphan_tag}{_status_badge(row.measured_status)}</div>'
        f'<div class="card-title">{_e(row.feature)}</div>'
        f'<div class="card-measured">{measured_line}</div>'
        f'<div class="card-ref">{_e(ref)}</div>'
        f"</div>"
    )


def _section_order(present_sections: set[str], atlas: bool) -> list[str]:
    base = _ATLAS_TRUNK_ORDER if atlas else _FUNCTIONAL_SECTION_ORDER
    ordered = [s for s in base if s in present_sections]
    ordered += sorted(present_sections - set(ordered))
    return ordered


def _build_sections(rows: list[MeasuredFeatureRow], atlas: bool, row_renderer) -> str:
    by_section: dict[str, list[MeasuredFeatureRow]] = {}
    for row in rows:
        by_section.setdefault(row.section, []).append(row)
    blocks: list[str] = []
    for index, section in enumerate(_section_order(set(by_section), atlas), start=1):
        section_rows = by_section[section]
        built = sum(1 for r in section_rows if r.measured_status == "built")
        rendered_rows = "".join(row_renderer(r) for r in section_rows)
        container = "cards" if row_renderer is _card_html else "rows"
        blocks.append(
            f'<section class="feature-section" data-section="{_e(section)}">'
            f'<div class="section-head"><span class="section-idx">{index:02d}</span>'
            f'<span class="section-title">{_e(section)}</span>'
            f'<span class="section-count">{built}/{len(section_rows)} built</span></div>'
            f'<div class="{container}">{rendered_rows}</div></section>'
        )
    return "".join(blocks)


def _stat_tiles(m: FeatureCatalogueMeasurement) -> str:
    def tile(value, label, sub, tone=""):
        return (
            f'<div class="tile {tone}"><div class="tile-value">{value}</div>'
            f'<div class="tile-label">{_e(label)}</div><div class="tile-sub">{_e(sub)}</div></div>'
        )

    phase = m.phase_counts
    built_pct = round(100 * m.built_with_code_count / max(1, m.feature_row_count))
    tiles = [
        tile(m.feature_row_count, "FEATURES", "catalogued"),
        tile(m.built_with_code_count, "BUILT", f"{built_pct}% · code-verified", "tone-good"),
        tile(m.status_counts.get("partial", 0), "PARTIAL", "wired, incomplete", "tone-warning"),
        tile(m.status_counts.get("blocked", 0), "BLOCKED", "gated / open", "tone-serious"),
        tile(m.forgotten_count, "FORGOTTEN", "amber-railed", "tone-amber"),
        tile(m.unverified_claim_count, "UNVERIFIED", "claimed, no code", "tone-serious"),
        tile(m.orphan_count, "ORPHANS", "code, not wired", "tone-serious"),
        tile(m.undocumented_count, "UNDOCUMENTED", "code, not in plan", "tone-amber"),
        tile(phase.get("P0", 0), "P0", "before capital"),
        tile(phase.get("P1", 0), "P1", "before first live"),
        tile(phase.get("P2", 0), "P2", "before second"),
        tile(phase.get("P3", 0), "P3", "at scale"),
        tile(f"{m.atlas_built_count}/{m.atlas_branch_count}", "AI ATLAS", "branches built", "tone-info"),
    ]
    return f'<div class="tiles">{"".join(tiles)}</div>'


def _most_forgotten(rows: list[MeasuredFeatureRow]) -> str:
    forgotten = [r for r in rows if r.forgotten and not r.is_atlas_branch]
    forgotten.sort(key=lambda r: (_PHASE_ORDER.index(r.phase) if r.phase in _PHASE_ORDER else 99))
    top = forgotten[:20]
    items = "".join(
        f'<li><span class="mf-rank">{i}</span><span class="mf-name">{_e(r.feature)}</span>'
        f'{_phase_pill(r.phase)}<span class="mf-note">{_e(r.note)[:120]}</span></li>'
        for i, r in enumerate(top, start=1)
    )
    return (
        '<section class="forgotten-block"><h2>The most-forgotten, ranked</h2>'
        '<p class="muted">Amber-railed rows are the ones commonly forgotten until they cost money or time '
        "— the reason this catalogue exists.</p>"
        f'<ol class="most-forgotten">{items}</ol></section>'
    )


def render_feature_catalogue_html(measurement: FeatureCatalogueMeasurement | None = None) -> str:
    """Render the whole Feature Catalogue page (measured live if no measurement is supplied)."""

    m = measurement or measure_feature_catalogue()
    rows = list(m.rows)
    feature_rows = [r for r in rows if not r.is_atlas_branch]
    atlas_rows = [r for r in rows if r.is_atlas_branch]

    catalogue_sections = _build_sections(feature_rows, atlas=False, row_renderer=_catalogue_row_html)
    wall_sections = _build_sections(feature_rows, atlas=False, row_renderer=_card_html)
    atlas_sections = _build_sections(atlas_rows, atlas=True, row_renderer=_card_html)

    status_legend = "".join(
        f'<span class="status status-{role}">{label}</span>'
        for label, role in _dedup_display()
    )

    return _PAGE_TEMPLATE.format(
        css=_CSS,
        js=_JS,
        generated_at=_e(m.generated_at_ist),
        real_modules=m.real_module_count,
        total_features=m.feature_row_count,
        atlas_total=m.atlas_branch_count,
        atlas_built=m.atlas_built_count,
        tiles=_stat_tiles(m),
        status_legend=status_legend,
        most_forgotten=_most_forgotten(rows),
        catalogue_sections=catalogue_sections,
        wall_sections=wall_sections,
        atlas_sections=atlas_sections,
    )


def _dedup_display():
    seen = set()
    out = []
    for label, role in STATUS_DISPLAY.values():
        if role in seen:
            continue
        seen.add(role)
        out.append((label, role))
    return out


_CSS = """
:root{--ground:#E9EDF0;--panel:#fff;--panel2:#F3F6F8;--ink:#0F171C;--ink2:#47555F;--ink3:#6F7E89;
--rule:#D2DAE0;--rule-soft:#E2E8ED;--amber:#A2650F;--amber-bg:#F7E9CD;--amber-rule:#D9A445;
--p0:#0E4E63;--p0bg:#D6E7EE;--p1:#22738D;--p1bg:#DDEBF1;--p2:#3F8DA3;--p2bg:#E4EFF3;--p3:#6AA7B8;--p3bg:#EAF2F5;
--good:#1E7A46;--warning:#A2650F;--serious:#B4331F;--neutral:#6F7E89;--info:#22738D;--muted:#8A97A0;}
:root[data-theme=dark]{--ground:#0C1116;--panel:#131A21;--panel2:#171F27;--ink:#E6ECF1;--ink2:#A7B4BE;
--ink3:#7C8A95;--rule:#26313B;--rule-soft:#1E2731;--amber-bg:#3A2E12;--amber:#E0A63C;
--p0bg:#0F2833;--p1bg:#122A34;--p2bg:#14303A;--p3bg:#173842;
--good:#3FB673;--warning:#E0A63C;--serious:#E06A54;--neutral:#8A97A0;--info:#5AB0C8;--muted:#7C8A95;}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ground:#0C1116;--panel:#131A21;
--panel2:#171F27;--ink:#E6ECF1;--ink2:#A7B4BE;--ink3:#7C8A95;--rule:#26313B;--rule-soft:#1E2731;
--amber-bg:#3A2E12;--amber:#E0A63C;--p0bg:#0F2833;--p1bg:#122A34;--p2bg:#14303A;--p3bg:#173842;
--good:#3FB673;--warning:#E0A63C;--serious:#E06A54;--info:#5AB0C8;}}
*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 80px}
.crumb{color:var(--ink3);font-size:12px;letter-spacing:.03em;margin-bottom:4px}
h1{font-size:22px;margin:2px 0 2px}.lede{color:var(--ink2);margin:0 0 16px;max-width:760px}
.gen{color:var(--ink3);font-size:12px;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:14px 0 18px}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:12px 12px 10px}
.tile-value{font-size:24px;font-weight:700}.tile-label{font-size:11px;letter-spacing:.08em;color:var(--ink2);margin-top:2px}
.tile-sub{font-size:11px;color:var(--ink3);margin-top:1px}
.tone-good .tile-value{color:var(--good)}.tone-warning .tile-value{color:var(--warning)}
.tone-serious .tile-value{color:var(--serious)}.tone-amber .tile-value{color:var(--amber)}.tone-info .tile-value{color:var(--info)}
.tabs{display:flex;gap:6px;margin:6px 0 12px;flex-wrap:wrap}
.tab{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:7px 14px;cursor:pointer;font-weight:600;color:var(--ink2)}
.tab.active{background:var(--p0);border-color:var(--p0);color:#fff}
.toolbar{position:sticky;top:0;z-index:5;background:var(--ground);padding:8px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--rule-soft)}
.toolbar input{flex:1;min-width:180px;padding:8px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--panel);color:var(--ink)}
.pill{border:1px solid var(--rule);border-radius:7px;padding:6px 10px;cursor:pointer;background:var(--panel);color:var(--ink2);font-size:12px;user-select:none}
.pill.on{background:var(--p1);border-color:var(--p1);color:#fff}
.counter{color:var(--ink3);font-size:12px;margin-left:auto}
.feature-section{margin:18px 0}
.section-head{display:flex;align-items:baseline;gap:8px;border-bottom:2px solid var(--rule);padding-bottom:4px;margin-bottom:6px}
.section-idx{color:var(--ink3);font-size:12px;font-variant-numeric:tabular-nums}
.section-title{font-size:16px;font-weight:700}.section-count{margin-left:auto;color:var(--ink3);font-size:12px}
.row{display:grid;grid-template-columns:minmax(200px,1.3fr) 60px 1.6fr;gap:10px;align-items:start;
padding:8px 10px;border-bottom:1px solid var(--rule-soft);background:var(--panel)}
.row:nth-child(odd){background:var(--panel2)}
.row.forgotten{border-left:3px solid var(--amber-rule);background:var(--amber-bg)}
.fname{font-weight:600}.cell-note{color:var(--ink2)}
.missed{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-rule);border-radius:4px;padding:0 5px;font-size:10px;letter-spacing:.05em;font-weight:700;vertical-align:middle}
.orphan-tag{background:var(--serious);color:#fff;border-color:var(--serious)}
.phase{display:inline-block;border-radius:5px;padding:1px 7px;font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}
.phase-p0{background:var(--p0bg);color:var(--p0)}.phase-p1{background:var(--p1bg);color:var(--p1)}
.phase-p2{background:var(--p2bg);color:var(--p2)}.phase-p3{background:var(--p3bg);color:var(--p3)}
.phase-p4{background:var(--p3bg);color:var(--p3)}.phase-p5{background:var(--p3bg);color:var(--p3)}
.phase-none{background:var(--rule-soft);color:var(--ink3)}
.status{display:inline-block;border-radius:5px;padding:1px 7px;font-size:10px;font-weight:700;letter-spacing:.04em;color:#fff}
.status-good{background:var(--good)}.status-warning{background:var(--warning)}.status-serious{background:var(--serious)}
.status-neutral{background:var(--neutral)}.status-info{background:var(--info)}.status-muted{background:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:10px 12px}
.card.forgotten{border-left:3px solid var(--amber-rule)}
.card-head{display:flex;justify-content:space-between;margin-bottom:4px}
.card-title{font-weight:700}.card-measured{color:var(--ink2);font-size:12px;margin-top:3px}
.card-ref{color:var(--ink3);font-size:11px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:5px;word-break:break-all}
.forgotten-block{margin:20px 0}.forgotten-block h2{font-size:16px;margin:0 0 2px}
.most-forgotten{list-style:none;padding:0;margin:8px 0;counter-reset:mf}
.most-forgotten li{display:grid;grid-template-columns:26px minmax(180px,1fr) 46px 1.4fr;gap:8px;align-items:baseline;padding:6px 8px;background:var(--panel);border-left:3px solid var(--amber-rule);border-bottom:1px solid var(--rule-soft)}
.mf-rank{color:var(--amber);font-weight:700}.mf-name{font-weight:600}.mf-note{color:var(--ink2);font-size:12px}
.legend{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 4px}
.muted{color:var(--ink3)}.footer{margin-top:26px;color:var(--ink3);font-size:12px;border-top:1px solid var(--rule);padding-top:10px}
.hidden{display:none!important}
@media(max-width:640px){.row{grid-template-columns:1fr 48px;grid-auto-rows:auto}.cell-note{grid-column:1/-1}
.most-forgotten li{grid-template-columns:22px 1fr 42px}.mf-note{grid-column:1/-1}}
"""

_JS = """
const root=document.documentElement;
const themeBtn=document.getElementById('theme');
themeBtn.onclick=()=>{const cur=root.getAttribute('data-theme');
 root.setAttribute('data-theme', cur==='dark'?'light':'dark');};
function activeViewRows(){const v=document.querySelector('.view:not(.hidden)');return v?[...v.querySelectorAll('.row,.card')]:[];}
const state={q:'',phases:new Set(),statuses:new Set(),forgottenOnly:false};
function apply(){let shown=0,total=0;
 document.querySelectorAll('.view:not(.hidden) .row,.view:not(.hidden) .card').forEach(el=>{total++;
  const t=el.dataset.text||'';const okQ=!state.q||t.includes(state.q);
  const okP=!state.phases.size||state.phases.has(el.dataset.phase);
  const okS=!state.statuses.size||state.statuses.has(el.dataset.status);
  const okF=!state.forgottenOnly||el.dataset.forgotten==='1';
  const ok=okQ&&okP&&okS&&okF;el.classList.toggle('hidden',!ok);if(ok)shown++;});
 document.querySelectorAll('.view:not(.hidden) .feature-section').forEach(s=>{
  const any=[...s.querySelectorAll('.row,.card')].some(e=>!e.classList.contains('hidden'));
  s.classList.toggle('hidden',!any);});
 document.getElementById('counter').textContent=shown+' / '+total+' shown';}
document.getElementById('search').oninput=e=>{state.q=e.target.value.toLowerCase();apply();};
document.querySelectorAll('.pill[data-phase]').forEach(p=>p.onclick=()=>{p.classList.toggle('on');
 const v=p.dataset.phase;state.phases.has(v)?state.phases.delete(v):state.phases.add(v);apply();});
document.querySelectorAll('.pill[data-status]').forEach(p=>p.onclick=()=>{p.classList.toggle('on');
 const v=p.dataset.status;state.statuses.has(v)?state.statuses.delete(v):state.statuses.add(v);apply();});
const fo=document.getElementById('forgottenOnly');fo.onclick=()=>{fo.classList.toggle('on');
 state.forgottenOnly=!state.forgottenOnly;apply();};
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
 document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));t.classList.add('active');
 document.querySelectorAll('.view').forEach(v=>v.classList.add('hidden'));
 document.getElementById(t.dataset.view).classList.remove('hidden');apply();});
apply();
"""

_PAGE_TEMPLATE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Feature Catalogue — NSE Autonomous Trading System</title><style>{css}</style></head><body>
<div class=wrap>
<div class=crumb>NSE autonomous trading system / Feature catalogue / measured</div>
<h1>Feature Catalogue &amp; Status Wall</h1>
<p class=lede>Everything the system has built, half-built, planned, discussed, prototyped as an idea, or
forgot and skipped — nothing omitted. The plan is authored; every <b>build-status is measured from the real
code</b> on the server (Rule R), never hand-typed.</p>
<p class=gen>Generated by <code>feature_catalogue_status_prober</code> · never hand-edited · measured against
{real_modules} live modules · {total_features} features · AI atlas {atlas_built}/{atlas_total} branches ·
<b>{generated_at}</b></p>
{tiles}
<div class=tabs>
 <div class="tab active" data-view=view-catalogue>Catalogue</div>
 <div class=tab data-view=view-wall>Status Wall (measured)</div>
 <div class=tab data-view=view-atlas>AI Atlas (16 trunks)</div>
</div>
<div class=toolbar>
 <input id=search placeholder="Filter features, notes, sections…">
 <span class="pill" data-phase=P0>P0</span><span class="pill" data-phase=P1>P1</span>
 <span class="pill" data-phase=P2>P2</span><span class="pill" data-phase=P3>P3</span>
 <span class="pill" data-status=built>built</span><span class="pill" data-status=partial>partial</span>
 <span class="pill" data-status=blocked>blocked</span><span class="pill" data-status=not-built>not-built</span>
 <span class="pill" id=forgottenOnly>Forgotten only</span>
 <span class=counter id=counter></span>
 <span class="pill" id=theme>◐ Theme</span>
</div>
<div class=legend>{status_legend}</div>
<div id=view-catalogue class=view>
{most_forgotten}
{catalogue_sections}
</div>
<div id=view-wall class="view hidden">{wall_sections}</div>
<div id=view-atlas class="view hidden">{atlas_sections}</div>
<div class=footer>Generated by <code>feature_catalogue_status_prober</code> · never hand-edited ·
build-status measured from the live <code>src/nse_algo_trader</code> module set (Rule R) · {generated_at}</div>
</div><script>{js}</script></body></html>"""


if __name__ == "__main__":  # pragma: no cover
    print(render_feature_catalogue_html()[:1500])
