"""Renders the DashboardSnapshot into the standalone interactive dashboard HTML.

The read-model produces data; this turns it into the page served as the
browser-reachable artifact — data views (layer roadmap, §9 lab calibration,
the 16-trunk/~200-branch tree) plus the editable control panel (paper
capital, min/max per trade, segment + strategy on/off, mode). Controls
persist per-device (localStorage) and export the exact TradingControlConfig
JSON the engine reads. Theme-aware, mobile-friendly.
"""

import json

from nse_algo_trader.dashboard.dashboard_read_model import DashboardSnapshot

_SNAPSHOT_TOKEN = "/*__DASHBOARD_SNAPSHOT_JSON__*/"


def render_dashboard_html(snapshot: DashboardSnapshot) -> str:
    return _DASHBOARD_HTML_TEMPLATE.replace(
        _SNAPSHOT_TOKEN, json.dumps(snapshot.to_json_dict())
    )


_DASHBOARD_HTML_TEMPLATE = r"""<title>NSE Algo Trader — Dashboard</title>
<style>
  :root{ --paper:#eef1ee; --raised:#e3e7e2; --line:#c9cec6; --text:#1b211d; --dim:#5b6259;
    --accent:#a9781f; --accent2:#8a611a; --ok:#3f8f5f; --okbg:#dcecdf; --attn:#b3762b; --attnbg:#f3e3cf;
    --neu:#948d7d; --neubg:#e6e4df; --def:#8d7a99; --defbg:#eae4ee; --adv:#3f7f9a; --advbg:#dbe8ee;
    --bad:#b33f3f; --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace; --serif:Charter,Georgia,serif; }
  @media (prefers-color-scheme:dark){ :root{ --paper:#14191a; --raised:#1b2123; --line:#333c3a; --text:#e7e9e4;
    --dim:#9aa39a; --accent:#dcab52; --accent2:#efc275; --ok:#4caf74; --okbg:#173423; --attn:#d29645; --attnbg:#3a2a12;
    --neu:#5c625b; --neubg:#26292a; --def:#8b7aa0; --defbg:#241f2b; --adv:#5fa8c4; --advbg:#152a33; --bad:#d46a6a; } }
  :root[data-theme="dark"]{ --paper:#14191a; --raised:#1b2123; --line:#333c3a; --text:#e7e9e4; --dim:#9aa39a;
    --accent:#dcab52; --accent2:#efc275; --ok:#4caf74; --okbg:#173423; --attn:#d29645; --attnbg:#3a2a12; --neu:#5c625b;
    --neubg:#26292a; --def:#8b7aa0; --defbg:#241f2b; --adv:#5fa8c4; --advbg:#152a33; --bad:#d46a6a; }
  :root[data-theme="light"]{ --paper:#eef1ee; --raised:#e3e7e2; --line:#c9cec6; --text:#1b211d; --dim:#5b6259;
    --accent:#a9781f; --accent2:#8a611a; --ok:#3f8f5f; --okbg:#dcecdf; --attn:#b3762b; --attnbg:#f3e3cf; --neu:#948d7d;
    --neubg:#e6e4df; --def:#8d7a99; --defbg:#eae4ee; --adv:#3f7f9a; --advbg:#dbe8ee; --bad:#b33f3f; }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--text);font-family:var(--serif);font-size:16px;line-height:1.5}
  .wrap{max-width:1000px;margin:0 auto;padding:1.5rem 1.1rem 4rem}
  header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:.5rem 1rem;
    border-bottom:1px solid var(--line);padding-bottom:1rem;margin-bottom:1.25rem}
  .brand .tag{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;color:var(--dim)}
  .brand h1{margin:.25rem 0 0;font-size:1.4rem}
  .meta{font-family:var(--mono);font-size:.74rem;color:var(--dim);text-align:right}
  .stat-row{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:1.5rem;font-family:var(--mono)}
  .stat{background:var(--raised);padding:.8rem}
  .stat .n{font-size:1.35rem;font-weight:700;font-variant-numeric:tabular-nums}
  .stat .l{font-size:.6rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin-top:.15rem}
  .stat.ok .n{color:var(--ok)} .stat.attn .n{color:var(--attn)} .stat.ac .n{color:var(--accent2)}
  h2{font-family:var(--mono);font-size:.76rem;text-transform:uppercase;letter-spacing:.13em;color:var(--dim);
    margin:2rem 0 .5rem;padding-bottom:.4rem;border-bottom:1px dashed var(--line)}
  h2 .i{color:var(--accent2);margin-right:.4em}
  .note{font-size:.86rem;color:var(--dim);margin:.25rem 0 1rem}
  /* control panel */
  .panel{border:1px solid var(--line);background:var(--raised);padding:1rem 1.1rem}
  .modebar{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem;flex-wrap:wrap}
  .modepill{font-family:var(--mono);font-size:.72rem;font-weight:700;padding:.35em .7em;border:1px solid;text-transform:uppercase;letter-spacing:.06em}
  .mode-paper{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
  .mode-live{background:#f1dede;border-color:var(--bad);color:var(--bad)}
  .ctrl-grid{display:grid;grid-template-columns:1fr 1fr;gap:.9rem 1.25rem}
  .ctrl{display:flex;flex-direction:column;gap:.3rem}
  .ctrl label{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
  .ctrl input[type=number]{font-family:var(--mono);font-size:.95rem;padding:.5rem .6rem;background:var(--paper);
    border:1px solid var(--line);color:var(--text);width:100%}
  .toggles{display:flex;flex-wrap:wrap;gap:.5rem}
  .toggle{font-family:var(--mono);font-size:.8rem;padding:.45em .7em;border:1px solid var(--line);background:var(--paper);
    color:var(--dim);cursor:pointer;user-select:none}
  .toggle[aria-pressed="true"]{background:var(--okbg);border-color:var(--ok);color:var(--ok);font-weight:700}
  .actions{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1rem}
  button.act{font-family:var(--mono);font-size:.8rem;padding:.55em 1em;border:1px solid var(--accent);background:transparent;
    color:var(--accent2);cursor:pointer}
  button.act:hover{background:var(--accent);color:var(--paper)}
  button.act:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  pre.cfg{font-family:var(--mono);font-size:.72rem;background:var(--paper);border:1px solid var(--line);padding:.8rem;
    margin-top:.9rem;overflow-x:auto;white-space:pre;color:var(--dim)}
  /* tables/rows */
  .ledger{display:flex;flex-direction:column;border:1px solid var(--line)}
  .row{display:grid;grid-template-columns:2rem 1fr auto;gap:.2rem .8rem;padding:.6rem .8rem;border-bottom:1px solid var(--line);align-items:center}
  .row:last-child{border-bottom:none}
  .row:nth-child(odd){background:color-mix(in srgb,var(--raised) 55%,transparent)}
  .row .num{font-family:var(--mono);font-weight:700;color:var(--dim);font-size:.85rem}
  .row .nm{font-size:.94rem;font-weight:600} .row .nt{font-size:.8rem;color:var(--dim)}
  .pill{font-family:var(--mono);font-size:.62rem;font-weight:700;padding:.28em .5em;border:1px solid;text-transform:uppercase;white-space:nowrap}
  .p-built{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
  .p-prog{background:var(--attnbg);border-color:var(--attn);color:var(--attn)}
  .p-none{background:var(--neubg);border-color:var(--neu);color:var(--dim)}
  .p-defer{background:var(--defbg);border-color:var(--def);color:var(--def)}
  table.tbl{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:.8rem}
  table.tbl th,table.tbl td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line);white-space:nowrap}
  table.tbl th{color:var(--dim);font-size:.66rem;text-transform:uppercase}
  .scroll{overflow-x:auto;border:1px solid var(--line);background:var(--raised)}
  details.trunk{border:1px solid var(--line);background:var(--raised);margin-bottom:.4rem}
  details.trunk summary{cursor:pointer;padding:.6rem .8rem;display:grid;grid-template-columns:2.6rem 1fr auto;gap:.7rem;align-items:center;list-style:none}
  details.trunk summary::-webkit-details-marker{display:none}
  .rn{font-family:var(--mono);font-weight:700;color:var(--accent2)} .tnm{font-weight:700}
  .te{display:block;font-size:.78rem;color:var(--dim);font-weight:400}
  .ig{font-family:var(--mono);font-size:.58rem;font-weight:700;padding:.22em .45em;border:1px solid;text-transform:uppercase}
  .ig-built{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
  .ig-ignites_l7{background:var(--attnbg);border-color:var(--attn);color:var(--attn)}
  .ig-matures_l10{background:var(--advbg);border-color:var(--adv);color:var(--adv)}
  .ig-frontier_l11{background:var(--defbg);border-color:var(--def);color:var(--def)}
  .branches{display:flex;flex-wrap:wrap;gap:.3rem;padding:.3rem .8rem .8rem}
  .branches span{font-family:var(--mono);font-size:.72rem;background:var(--paper);border:1px solid var(--line);padding:.18em .45em}
  .gated{font-family:var(--mono);font-size:.58rem;color:var(--accent2);border:1px solid var(--accent);padding:.15em .4em}
  footer{font-family:var(--mono);font-size:.72rem;color:var(--dim);border-top:1px dashed var(--line);margin-top:2.5rem;padding-top:1rem}
  @media (max-width:640px){ .stat-row{grid-template-columns:repeat(2,1fr)} .ctrl-grid{grid-template-columns:1fr}
    .row{grid-template-columns:1.6rem 1fr} .row .pill{grid-column:1/-1} details.trunk summary{grid-template-columns:2rem 1fr} }
</style>
<div class="wrap">
  <header>
    <div class="brand"><span class="tag">nse-algo-trader · live dashboard</span><h1>Trading Dashboard</h1></div>
    <div class="meta" id="meta"></div>
  </header>
  <div class="stat-row" id="stats"></div>

  <h2><span class="i">§</span>Controls <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--dim)">— edits saved on this device; export the config to the VPS</span></h2>
  <div class="panel">
    <div class="modebar">
      <span id="modepill" class="modepill mode-paper">Paper mode</span>
      <button class="act" id="modeBtn" type="button">Switch mode</button>
      <span class="note" id="modenote" style="margin:0"></span>
    </div>
    <div class="ctrl-grid">
      <div class="ctrl"><label>Paper capital (₹)</label><input type="number" id="capital" min="1000" step="10000"></div>
      <div class="ctrl"><label>Max risk / trade (%)</label><input type="number" id="risk" min="0.1" max="100" step="0.1"></div>
      <div class="ctrl"><label>Min capital / trade (₹)</label><input type="number" id="mincap" min="0" step="1000"></div>
      <div class="ctrl"><label>Max capital / trade (₹)</label><input type="number" id="maxcap" min="0" step="1000"></div>
    </div>
    <div class="ctrl" style="margin-top:1rem"><label>Segments</label><div class="toggles" id="segments"></div></div>
    <div class="ctrl" style="margin-top:.9rem"><label>Strategies</label><div class="toggles" id="strategies"></div></div>
    <div class="actions">
      <button class="act" id="copyBtn" type="button">Copy config JSON</button>
      <button class="act" id="resetBtn" type="button">Reset to saved</button>
    </div>
    <pre class="cfg" id="cfgPreview"></pre>
  </div>

  <h2><span class="i">§</span>Paper trading — last replay run (real data)</h2>
  <div class="scroll"><table class="tbl" id="paperTbl"></table></div>

  <h2><span class="i">§</span>Falsification lab — prediction tables &amp; calibration</h2>
  <div class="scroll"><table class="tbl" id="labTbl"></table></div>
  <p class="note" id="labnote"></p>

  <h2><span class="i">§</span>Layer roadmap</h2>
  <div class="ledger" id="roadmap"></div>

  <h2><span class="i">§</span>Autonomous-AI concept tree — <span id="treeCounts"></span></h2>
  <p class="note">Every faculty of the self-learning bot, and the layer it becomes real at. Tap a trunk to see its branches.</p>
  <div id="tree"></div>

  <footer id="foot"></footer>
</div>
<script>
const SNAPSHOT = /*__DASHBOARD_SNAPSHOT_JSON__*/;
const rupee = n => "₹" + Math.round(n).toLocaleString("en-IN");
const CFG_KEY = "nse_algo_trader_control_config";
let cfg = JSON.parse(JSON.stringify(SNAPSHOT.control_config));
try { const saved = localStorage.getItem(CFG_KEY); if (saved) cfg = JSON.parse(saved); } catch(e){}

function saveCfg(){ try{ localStorage.setItem(CFG_KEY, JSON.stringify(cfg)); }catch(e){} renderCfg(); }
function renderCfg(){
  document.getElementById("cfgPreview").textContent = JSON.stringify(cfg, null, 2);
  const paper = cfg.trading_mode === "paper";
  const mp = document.getElementById("modepill");
  mp.textContent = paper ? "Paper mode" : "LIVE mode";
  mp.className = "modepill " + (paper ? "mode-paper" : "mode-live");
  document.getElementById("modenote").textContent = paper
    ? "virtual money — safe to experiment"
    : "real capital — requires a funded Kite account + exchange Algo-ID (not enabled here)";
}
function num(id, key){ const el=document.getElementById(id); el.value=cfg[key];
  el.addEventListener("change",()=>{ const v=parseFloat(el.value); if(!isNaN(v)){cfg[key]=v; saveCfg();} }); }
num("capital","account_virtual_capital"); num("mincap","min_capital_per_trade");
num("maxcap","max_capital_per_trade");
const riskEl=document.getElementById("risk"); riskEl.value=(cfg.max_risk_per_trade_fraction*100).toFixed(1);
riskEl.addEventListener("change",()=>{ const v=parseFloat(riskEl.value); if(!isNaN(v)){cfg.max_risk_per_trade_fraction=v/100; saveCfg();} });

function toggleGroup(containerId, obj){
  const c=document.getElementById(containerId); c.innerHTML="";
  Object.keys(obj).forEach(k=>{
    const b=document.createElement("button"); b.type="button"; b.className="toggle";
    b.textContent=k.replace(/_/g," "); b.setAttribute("aria-pressed", obj[k]?"true":"false");
    b.addEventListener("click",()=>{ obj[k]=!obj[k]; b.setAttribute("aria-pressed",obj[k]?"true":"false"); saveCfg(); });
    c.appendChild(b);
  });
}
toggleGroup("segments", cfg.segment_enabled);
toggleGroup("strategies", cfg.strategy_enabled);

document.getElementById("modeBtn").addEventListener("click",()=>{
  cfg.trading_mode = cfg.trading_mode==="paper" ? "live" : "paper"; saveCfg(); });
document.getElementById("copyBtn").addEventListener("click", async ()=>{
  const t=JSON.stringify(cfg,null,2);
  try{ await navigator.clipboard.writeText(t); document.getElementById("copyBtn").textContent="Copied ✓";
    setTimeout(()=>document.getElementById("copyBtn").textContent="Copy config JSON",1500);}catch(e){}
});
document.getElementById("resetBtn").addEventListener("click",()=>{
  cfg=JSON.parse(JSON.stringify(SNAPSHOT.control_config)); saveCfg();
  toggleGroup("segments",cfg.segment_enabled); toggleGroup("strategies",cfg.strategy_enabled);
  document.getElementById("capital").value=cfg.account_virtual_capital;
  document.getElementById("mincap").value=cfg.min_capital_per_trade;
  document.getElementById("maxcap").value=cfg.max_capital_per_trade;
  riskEl.value=(cfg.max_risk_per_trade_fraction*100).toFixed(1);
});
renderCfg();

// meta + stats
document.getElementById("meta").innerHTML =
  "snapshot " + SNAPSHOT.generated_at.slice(0,16).replace("T"," ") + "<br>observes the engine · never trades";
const built = SNAPSHOT.layer_roadmap.filter(l=>l.status==="built").length;
const prog = SNAPSHOT.layer_roadmap.filter(l=>l.status==="in_progress").length;
document.getElementById("stats").innerHTML =
  `<div class="stat ok"><div class="n">${built}</div><div class="l">Layers built</div></div>`+
  `<div class="stat attn"><div class="n">${prog}</div><div class="l">In progress</div></div>`+
  `<div class="stat ok"><div class="n">${SNAPSHOT.paper_trading.is_flat?"flat":"OPEN"}</div><div class="l">Paper positions</div></div>`+
  `<div class="stat ac"><div class="n">${SNAPSHOT.concept_tree_counts.trunk_count}</div><div class="l">AI trunks</div></div>`+
  `<div class="stat ac"><div class="n">${SNAPSHOT.concept_tree_counts.total_branch_count}+</div><div class="l">AI branches</div></div>`;

// paper table
const p=SNAPSHOT.paper_trading;
document.getElementById("paperTbl").innerHTML =
  "<tr><th>metric</th><th>value</th></tr>"+
  `<tr><td>starting virtual capital</td><td>${rupee(p.starting_virtual_cash)}</td></tr>`+
  `<tr><td>realized P&amp;L</td><td style="color:${p.realized_pnl>=0?'var(--ok)':'var(--bad)'}">${rupee(p.realized_pnl)}</td></tr>`+
  `<tr><td>fills</td><td>${p.fill_count}</td></tr>`+
  `<tr><td>flat at end (no overnight)</td><td>${p.is_flat}</td></tr>`;

// lab table
let lab="<tr><th>table</th><th>n</th><th>mean p</th><th>actual win</th><th>Brier</th></tr>";
SNAPSHOT.prediction_tables.forEach(t=>{
  if(!t.trade_count){ lab+=`<tr><td>${t.table}</td><td>0</td><td>—</td><td>—</td><td>—</td></tr>`; return; }
  lab+=`<tr><td>${t.table}</td><td>${t.trade_count}</td><td>${t.mean_win_probability.toFixed(2)}</td>`+
    `<td>${Math.round(t.actual_win_rate*100)}%</td><td>${t.brier_score.toFixed(3)}</td></tr>`;
});
document.getElementById("labTbl").innerHTML=lab;
document.getElementById("labnote").textContent =
  "CONFIDENT-WIN beats CONFIDENT-LOSS: " + SNAPSHOT.confident_win_beats_confident_loss +
  ". Directional signal on a small sample — not a validated edge; no strategy reaches live capital before the Deflated-Sharpe/CPCV gate + human sign-off.";

// roadmap
const pmap={built:"p-built",in_progress:"p-prog",not_started:"p-none",deferred:"p-defer"};
const plabel={built:"Built",in_progress:"In progress",not_started:"Not started",deferred:"Deferred"};
document.getElementById("roadmap").innerHTML = SNAPSHOT.layer_roadmap.map(l=>
  `<div class="row"><div class="num">${String(l.number).padStart(2,"0")}</div>`+
  `<div><div class="nm">${l.name}</div><div class="nt">${l.note}</div></div>`+
  `<span class="pill ${pmap[l.status]}">${plabel[l.status]}</span></div>`).join("");

// tree
document.getElementById("treeCounts").textContent =
  SNAPSHOT.concept_tree_counts.trunk_count+" trunks · "+SNAPSHOT.concept_tree_counts.total_branch_count+"+ branches";
document.getElementById("tree").innerHTML = SNAPSHOT.concept_tree.map(t=>
  `<details class="trunk"><summary><span class="rn">${t.roman_number}</span>`+
  `<span class="tnm">${t.name}<span class="te">${t.essence}${t.is_gated?' · <span class="gated">gated</span>':''}</span></span>`+
  `<span class="ig ig-${t.ignition}">${t.ignition.replace(/_/g," ")}</span></summary>`+
  `<div class="branches">${t.branch_names.map(b=>`<span>${b}</span>`).join("")} `+
  `<span style="color:var(--dim)">+${Math.max(0,t.branch_count-t.branch_names.length)} more</span></div></details>`).join("");

document.getElementById("foot").innerHTML =
  "intraday-only NSE cash + options · Zerodha Kite (v1) · paper sandbox, human gate before live capital<br>"+
  "controls persist on this device and export the config the bot reads on the VPS · live two-way control needs an exposed API (not enabled)";
</script>
"""
