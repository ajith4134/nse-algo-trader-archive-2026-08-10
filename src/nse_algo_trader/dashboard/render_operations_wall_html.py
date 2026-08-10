"""The Operations Wall (`/wall`) — a live "TV wall" where every feature on the server shows as a status tile.

Answers the user's ask: see all the features working at a glance, like a wall of screens — the 3 AI bots and
their 2 directional AI features pinned as the hero row, then every operational feature in the Rule-N surface
manifest. It is MANIFEST-DRIVEN: the page renders `FEATURE_SURFACE_MANIFEST` in full, so any feature that
has not yet registered a surface shows a "not yet surfaced" tile, and any FUTURE feature appears here
automatically the moment it joins the manifest — that is the standing rule, made visible.

Each tile is a reserved status light (good/gathering/idle/blocked palette + an icon + a word — never colour
alone, per the dataviz status-tile rule) with its headline metrics, its note, and a live-pulse dot fed by the
pod heartbeat. The page is a thin shell that polls `/api/snapshot` (same auth pattern as the main dashboard)
and re-renders; it reuses the house design tokens so it is theme-aware in light and dark.
"""

from __future__ import annotations

import json

from nse_algo_trader.dashboard.dashboard_feature_surface import FEATURE_SURFACE_MANIFEST

_API_KEY_TOKEN = "/*__LIVE_API_KEY__*/"
_MANIFEST_TOKEN = "/*__MANIFEST__*/"

# The 5 features the user named — pinned as the hero row at the top of the wall.
_HERO_KEYS = (
    "index_option_bot",
    "stock_option_bot",
    "cash_intraday_bot",
    "directional_ai_bull",
    "directional_ai_bear",
)


def render_operations_wall_html(live_api_key: str | None = None) -> str:
    """Render the wall page. `live_api_key` (server mode) is injected so the page can poll `/api/snapshot`."""
    manifest = [{"key": k, "title": t} for k, t in FEATURE_SURFACE_MANIFEST]
    return (
        _PAGE
        .replace(_MANIFEST_TOKEN, json.dumps(manifest))
        .replace("/*__HERO__*/", json.dumps(list(_HERO_KEYS)))
        .replace(_API_KEY_TOKEN, json.dumps(live_api_key))
    )


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Operations Wall — every feature, live</title>
<style>
:root{--ground:#E9EDF0;--panel:#fff;--panel2:#F3F6F8;--ink:#0F171C;--ink2:#47555F;--ink3:#6F7E89;
--rule:#D2DAE0;--rule-soft:#E2E8ED;--p0:#0E4E63;
--good:#1E7A46;--good-bg:#DCEEE3;--warning:#A2650F;--warn-bg:#F7E9CD;--serious:#B4331F;--serious-bg:#F6DAD3;
--neutral:#6F7E89;--neutral-bg:#E5EAEE;--info:#22738D;--info-bg:#DDEBF1;--muted:#8A97A0;}
:root[data-theme=dark]{--ground:#0C1116;--panel:#131A21;--panel2:#171F27;--ink:#E6ECF1;--ink2:#A7B4BE;
--ink3:#7C8A95;--rule:#26313B;--rule-soft:#1E2731;
--good:#3FB673;--good-bg:#123024;--warning:#E0A63C;--warn-bg:#3A2E12;--serious:#E06A54;--serious-bg:#3A1C16;
--neutral:#8A97A0;--neutral-bg:#1E2731;--info:#5AB0C8;--info-bg:#122A34;--muted:#7C8A95;}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ground:#0C1116;--panel:#131A21;
--panel2:#171F27;--ink:#E6ECF1;--ink2:#A7B4BE;--ink3:#7C8A95;--rule:#26313B;--rule-soft:#1E2731;
--good:#3FB673;--good-bg:#123024;--warning:#E0A63C;--warn-bg:#3A2E12;--serious:#E06A54;--serious-bg:#3A1C16;
--neutral:#8A97A0;--neutral-bg:#1E2731;--info:#5AB0C8;--info-bg:#122A34;--muted:#7C8A95;}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
padding:16px 18px 40px;max-width:1500px;margin:0 auto}
a{color:var(--info);text-decoration:none}
.crumb{color:var(--ink3);font-size:12px;letter-spacing:.03em;margin-bottom:4px}
.crumb a{color:var(--ink3)}
h1{font-size:23px;margin:2px 0 2px;display:flex;align-items:center;gap:10px}
.lede{color:var(--ink2);margin:0 0 14px;max-width:820px}
.gen{color:var(--ink3);font-size:12px;margin:0 0 14px}
.pulse{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:var(--ink2)}
.pulse .p{width:9px;height:9px;border-radius:50%;background:var(--muted)}
.pulse.on .p{background:var(--good);animation:blink 1.6s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:0 0 16px}
.stat{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:10px 12px}
.stat .v{font-size:24px;font-weight:800;line-height:1}
.stat .l{font-size:10px;letter-spacing:.09em;color:var(--ink2);margin-top:3px;text-transform:uppercase}
.stat.s-good .v{color:var(--good)}.stat.s-info .v{color:var(--info)}.stat.s-neutral .v{color:var(--neutral)}
.stat.s-serious .v{color:var(--serious)}.stat.s-warning .v{color:var(--warning)}
.toolbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 14px}
.chip{background:var(--panel);border:1px solid var(--rule);border-radius:999px;padding:5px 12px;cursor:pointer;
font-weight:600;font-size:12px;color:var(--ink2);user-select:none}
.chip.active{background:var(--p0);border-color:var(--p0);color:#fff}
.section-h{display:flex;align-items:baseline;gap:10px;margin:20px 0 9px}
.section-h h2{font-size:14px;letter-spacing:.06em;text-transform:uppercase;margin:0;color:var(--ink2)}
.section-h .sub{color:var(--ink3);font-size:12px}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.hero .grid{grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
.tile{background:var(--panel);border:1px solid var(--rule);border-left-width:4px;border-radius:11px;
padding:12px 13px 11px;display:flex;flex-direction:column;gap:7px;min-height:96px}
.tile.hero-tile{min-height:150px;padding:14px 15px}
.tile.b-good{border-left-color:var(--good)}.tile.b-info{border-left-color:var(--info)}
.tile.b-neutral{border-left-color:var(--neutral)}.tile.b-serious{border-left-color:var(--serious)}
.tile.b-warning{border-left-color:var(--warning)}
.tile-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.tile-title{font-weight:700;font-size:13.5px;line-height:1.3}
.hero-tile .tile-title{font-size:15px}
.badge{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;border-radius:6px;padding:2px 8px;
font-size:10px;font-weight:800;letter-spacing:.05em;white-space:nowrap}
.badge .dot{width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px transparent}
.badge.g-good{color:var(--good);background:var(--good-bg)}
.badge.g-info{color:var(--info);background:var(--info-bg)}
.badge.g-neutral{color:var(--neutral);background:var(--neutral-bg)}
.badge.g-serious{color:var(--serious);background:var(--serious-bg)}
.badge.g-warning{color:var(--warning);background:var(--warn-bg)}
.badge.g-good .dot{animation:blink 1.6s ease-in-out infinite}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:3px 12px;margin-top:1px}
.hero-tile .metrics{grid-template-columns:1fr}
.metric{display:flex;justify-content:space-between;gap:8px;font-size:11.5px;border-bottom:1px dotted var(--rule-soft);padding:1px 0}
.metric .ml{color:var(--ink3)}
.metric .mv{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums;text-align:right}
.metric .mv.warn{color:var(--warning)}.metric .mv.bad{color:var(--serious)}.metric .mv.ok{color:var(--good)}
.note{font-size:11px;color:var(--ink3);line-height:1.4;margin-top:auto}
.empty{color:var(--ink3);font-size:13px;padding:20px 4px}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--ink3);margin:4px 0 12px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend .dot{width:9px;height:9px;border-radius:50%}
</style>
</head>
<body>
<div class="crumb"><a id="homelink" href="/">← Dashboard</a> &nbsp;·&nbsp; Operations Wall</div>
<h1>📺 Operations Wall
<span class="pulse" id="pulse"><span class="p"></span><span id="pulsetxt">connecting…</span></span></h1>
<p class="lede">Every feature on the server as a live status tile — the 3 AI bots and their 2 directional AI
features pinned first, then all operational features. Manifest-driven: a feature that hasn't registered a
surface shows as <b>not yet surfaced</b>, and any new feature appears here automatically. That is the rule.</p>
<div class="legend">
<span><i class="dot" style="background:var(--good)"></i> live / active</span>
<span><i class="dot" style="background:var(--info)"></i> gathering</span>
<span><i class="dot" style="background:var(--neutral)"></i> idle · built</span>
<span><i class="dot" style="background:var(--serious)"></i> blocked</span>
<span><i class="dot" style="background:var(--warning)"></i> not surfaced</span>
</div>
<div class="summary" id="summary"></div>
<div class="toolbar" id="toolbar"></div>
<p class="gen" id="gen"></p>

<div class="hero">
  <div class="section-h"><h2>3 AI bots + directional AI</h2><span class="sub">the segment engines &amp; their bull/bear brains</span></div>
  <div class="grid" id="herogrid"></div>
</div>
<div>
  <div class="section-h"><h2>All features</h2><span class="sub" id="allsub"></span></div>
  <div class="grid" id="allgrid"></div>
</div>

<script>
const LIVE_API_KEY = /*__LIVE_API_KEY__*/;
const MANIFEST = /*__MANIFEST__*/;
const HERO = /*__HERO__*/;
const HERO_SET = new Set(HERO);

// status -> {role, icon, label}. Reserved status palette; icon+word carry meaning, never colour alone.
const STATUS = {
  active:    {role:"good",    icon:"●", label:"LIVE"},
  gathering: {role:"info",    icon:"◐", label:"GATHERING"},
  idle:      {role:"neutral", icon:"○", label:"IDLE · BUILT"},
  blocked:   {role:"serious", icon:"▲", label:"BLOCKED"},
  off:       {role:"neutral", icon:"○", label:"OFF"},
  unknown:   {role:"warning", icon:"▲", label:"UNKNOWN"},
  missing:   {role:"warning", icon:"▲", label:"NOT SURFACED"},
};
const FILTERS = ["active","gathering","idle","blocked","missing"];
const state = {statuses:new Set(), api:null};

function esc(s){const d=document.createElement("div");d.textContent=(s==null?"":String(s));return d.innerHTML;}
function keyForKey(k){return LIVE_API_KEY?("?key="+encodeURIComponent(LIVE_API_KEY)):"";}

function metricClass(v){
  const s=String(v).toLowerCase();
  if(s.includes("not-instrumented")||s==="no"||s.includes("defect")) return "bad";
  if(s.includes("gathering")||s.includes("to earn")) return "warn";
  if(s==="yes"||s==="wired"||s.includes("earned —")) return "ok";
  return "";
}

function tile(surface, isHero){
  const st = STATUS[surface.status] || STATUS.unknown;
  const metrics = (surface.metrics||[]).map(m=>
    `<div class="metric"><span class="ml">${esc(m[0])}</span><span class="mv ${metricClass(m[1])}">${esc(m[1])}</span></div>`
  ).join("");
  const note = surface.note ? `<div class="note">${esc(surface.note)}</div>` : "";
  return `<div class="tile ${isHero?"hero-tile":""} b-${st.role}" data-status="${esc(surface.status)}">
    <div class="tile-head"><div class="tile-title">${esc(surface.title)}</div>
      <span class="badge g-${st.role}"><span class="dot"></span>${st.icon} ${st.label}</span></div>
    <div class="metrics">${metrics}</div>${note}</div>`;
}

function render(surfaceByKey){
  // hero row (the 5 named features), in the pinned order
  const heroRows = HERO.map(k => surfaceByKey[k]).filter(Boolean);
  document.getElementById("herogrid").innerHTML =
    heroRows.length ? heroRows.map(s=>tile(s,true)).join("") : `<div class="empty">bot surfaces not yet reported</div>`;

  // all features: every manifest key, in order, placeholder if not surfaced
  const counts={active:0,gathering:0,idle:0,blocked:0,off:0,unknown:0,missing:0};
  const rows=[];
  for(const m of MANIFEST){
    if(HERO_SET.has(m.key)) continue; // shown in hero already
    let s=surfaceByKey[m.key];
    if(!s){ s={key:m.key,title:m.title,status:"missing",metrics:[["surface","not yet registered"]],note:"Manifest feature with no built surface — fails the Rule-N coverage audit."}; }
    counts[s.status]=(counts[s.status]||0)+1;
    if(!state.statuses.size || state.statuses.has(s.status)) rows.push(tile(s,false));
  }
  // hero contributes to counts too
  for(const s of heroRows){ counts[s.status]=(counts[s.status]||0)+1; }

  document.getElementById("allgrid").innerHTML = rows.length ? rows.join("") : `<div class="empty">no features match the filter</div>`;
  document.getElementById("allsub").textContent = `${MANIFEST.length} features in the manifest`;

  // summary tiles
  const total=MANIFEST.length;
  const surfaced=total-counts.missing;
  const S=[
    ["total",total,"neutral"],["live",counts.active,"good"],["gathering",counts.gathering,"info"],
    ["idle · built",counts.idle,"neutral"],["blocked",counts.blocked,"serious"],
    ["not surfaced",counts.missing,counts.missing?"warning":"good"],
  ];
  document.getElementById("summary").innerHTML =
    S.map(([l,v,r])=>`<div class="stat s-${r}"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`).join("")
    + `<div class="stat s-good"><div class="v">${surfaced}/${total}</div><div class="l">surfaced</div></div>`;
}

function buildToolbar(){
  const tb=document.getElementById("toolbar");
  tb.innerHTML = FILTERS.map(f=>{
    const st=STATUS[f]||STATUS.unknown; return `<span class="chip" data-f="${f}">${st.icon} ${st.label}</span>`;
  }).join("") + `<span class="chip" data-f="__all" style="margin-left:auto">show all</span>`;
  tb.querySelectorAll(".chip").forEach(c=>c.addEventListener("click",()=>{
    const f=c.dataset.f;
    if(f==="__all"){ state.statuses.clear(); }
    else { state.statuses.has(f)?state.statuses.delete(f):state.statuses.add(f); }
    tb.querySelectorAll(".chip").forEach(x=>x.classList.toggle("active", x.dataset.f!=="__all" && state.statuses.has(x.dataset.f)));
    if(state.api) render(state.api);
  }));
}

function heartbeat(surfaces){
  // the freshest "live pod cycle" metric drives the top pulse
  let age=null;
  for(const s of surfaces){ for(const m of (s.metrics||[])){ if(m[0]==="live pod cycle"||m[0]==="live pod cycle "){ age=m[1]; } } }
  const p=document.getElementById("pulse"), t=document.getElementById("pulsetxt");
  if(age && age!=="NOT-INSTRUMENTED"){ p.classList.add("on"); t.textContent="pod cycle "+age; }
  else { p.classList.remove("on"); t.textContent = age==="NOT-INSTRUMENTED" ? "pod not instrumented" : "no live feed"; }
}

async function poll(){
  try{
    const r=await fetch("/api/snapshot"+keyForKey());
    if(!r.ok) throw new Error("HTTP "+r.status);
    const snap=await r.json();
    const surfaces=snap.feature_surfaces||[];
    const byKey={}; for(const s of surfaces){ byKey[s.key]=s; }
    state.api=byKey;
    render(byKey);
    heartbeat(surfaces);
    document.getElementById("gen").textContent="updated "+new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById("gen").textContent="live feed unavailable ("+e.message+") — showing the manifest";
    if(!state.api) render({});
  }
}

document.getElementById("homelink").href = "/"+keyForKey();
buildToolbar();
render({});           // paint the manifest immediately (works even with no live feed)
poll();
setInterval(poll, 15000);
</script>
</body>
</html>
"""
