"""Renders the DashboardSnapshot into the standalone interactive dashboard HTML.

The read-model produces data; this turns it into the page served as the
browser-reachable dashboard — KPI tiles, an interactive control panel
(paper capital, min/max per trade, segment + strategy switches, mode), the
§9 lab calibration, the layer roadmap, and the 16-trunk/~200-branch tree.
Controls POST live to /api/config in server mode; localStorage + export in
artifact mode. Theme-aware (light/dark), mobile-first.
"""

import json

from nse_algo_trader.dashboard.dashboard_read_model import DashboardSnapshot

_SNAPSHOT_TOKEN = "/*__DASHBOARD_SNAPSHOT_JSON__*/"
_API_KEY_TOKEN = "/*__LIVE_API_KEY__*/"


def render_dashboard_html(
    snapshot: DashboardSnapshot, live_api_key: str | None = None
) -> str:
    """Render the dashboard. When `live_api_key` is given (server mode), the
    control panel POSTs edits live to /api/config; otherwise (artifact mode)
    it persists to localStorage and exports the config JSON."""
    return _DASHBOARD_HTML_TEMPLATE.replace(
        _SNAPSHOT_TOKEN, json.dumps(snapshot.to_json_dict())
    ).replace(_API_KEY_TOKEN, json.dumps(live_api_key))


_DASHBOARD_HTML_TEMPLATE = r"""<title>NSE Algo Trader — Dashboard</title>
<style>
  :root{
    --bg:#f4f6fa; --surface:#ffffff; --surface2:#f9fafc; --line:#e4e8ef; --line2:#eef1f6;
    --text:#161c27; --dim:#5f6b7d; --faint:#8a94a6;
    --brand:#3b53d1; --brand2:#4f6bed; --brandsoft:#eef1fe;
    --profit:#0f9d68; --profitsoft:#e5f5ee; --loss:#d8483f; --losssoft:#fbeae9;
    --warnc:#c07f14; --warnsoft:#fbf1dd;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,system-ui,sans-serif;
    --shadow:0 1px 2px rgba(16,24,40,.04),0 4px 16px rgba(16,24,40,.05);
    --r:14px;
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#0b0e14; --surface:#141924; --surface2:#1a2029; --line:#252d3b; --line2:#1e2531;
    --text:#e7ebf2; --dim:#9aa4b5; --faint:#6b7688;
    --brand:#7f95f5; --brand2:#93a5f8; --brandsoft:#1a2138;
    --profit:#2ecf92; --profitsoft:#12291f; --loss:#f0736e; --losssoft:#2c1717;
    --warnc:#e0a53f; --warnsoft:#2c2411;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.28);
  }}
  :root[data-theme="dark"]{
    --bg:#0b0e14; --surface:#141924; --surface2:#1a2029; --line:#252d3b; --line2:#1e2531;
    --text:#e7ebf2; --dim:#9aa4b5; --faint:#6b7688;
    --brand:#7f95f5; --brand2:#93a5f8; --brandsoft:#1a2138;
    --profit:#2ecf92; --profitsoft:#12291f; --loss:#f0736e; --losssoft:#2c1717;
    --warnc:#e0a53f; --warnsoft:#2c2411;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.28);
  }
  :root[data-theme="light"]{
    --bg:#f4f6fa; --surface:#ffffff; --surface2:#f9fafc; --line:#e4e8ef; --line2:#eef1f6;
    --text:#161c27; --dim:#5f6b7d; --faint:#8a94a6;
    --brand:#3b53d1; --brand2:#4f6bed; --brandsoft:#eef1fe;
    --profit:#0f9d68; --profitsoft:#e5f5ee; --loss:#d8483f; --losssoft:#fbeae9;
    --warnc:#c07f14; --warnsoft:#fbf1dd;
    --shadow:0 1px 2px rgba(16,24,40,.04),0 4px 16px rgba(16,24,40,.05);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
    font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1080px;margin:0 auto;padding:1.5rem 1.15rem 5rem}
  .num{font-variant-numeric:tabular-nums;font-family:var(--mono)}

  header{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1.5rem}
  .logo{display:flex;align-items:center;gap:.7rem}
  .mark{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,var(--brand),var(--brand2));
    display:grid;place-items:center;color:#fff;font-weight:800;font-size:1.1rem;box-shadow:var(--shadow)}
  .logo h1{margin:0;font-size:1.15rem;font-weight:700;letter-spacing:-.01em}
  .logo .sub{font-size:.72rem;color:var(--faint);font-family:var(--mono);letter-spacing:.04em}
  .modebadge{display:inline-flex;align-items:center;gap:.45rem;font-family:var(--mono);font-size:.72rem;
    font-weight:700;padding:.42em .7em;border-radius:999px;letter-spacing:.05em}
  .modebadge.paper{background:var(--profitsoft);color:var(--profit)}
  .modebadge.live{background:var(--losssoft);color:var(--loss)}
  .modebadge .dot{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 22%,transparent)}

  .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:.85rem;margin-bottom:1.75rem}
  .kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:1rem 1.1rem;box-shadow:var(--shadow)}
  .kpi .lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);font-weight:600}
  .kpi .val{font-size:1.5rem;font-weight:750;margin-top:.35rem;letter-spacing:-.02em}
  .kpi .val.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
  .kpi .sub{font-size:.72rem;color:var(--dim);margin-top:.15rem}
  .kpi.profit .val{color:var(--profit)} .kpi.loss .val{color:var(--loss)}

  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
    box-shadow:var(--shadow);margin-bottom:1.25rem;overflow:hidden}
  .card > .head{display:flex;align-items:center;gap:.6rem;padding:.9rem 1.15rem;border-bottom:1px solid var(--line2)}
  .card > .head .bar{width:3px;height:16px;border-radius:2px;background:var(--brand)}
  .card > .head h2{margin:0;font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
  .card > .head .aside{margin-left:auto;font-size:.74rem;color:var(--dim);font-family:var(--mono)}
  .card > .body{padding:1.15rem}

  /* controls */
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:.9rem 1.1rem}
  .field label{display:block;font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600;margin-bottom:.35rem}
  .field input{width:100%;font-family:var(--mono);font-size:1rem;font-weight:600;padding:.6rem .75rem;
    background:var(--surface2);border:1px solid var(--line);border-radius:10px;color:var(--text)}
  .field input:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--brandsoft)}
  .switchrow{margin-top:1.1rem}
  .switchrow .lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600;margin-bottom:.5rem}
  .switches{display:flex;flex-wrap:wrap;gap:.55rem}
  .sw{display:inline-flex;align-items:center;gap:.55rem;padding:.5rem .8rem;border-radius:10px;
    border:1px solid var(--line);background:var(--surface2);cursor:pointer;user-select:none;font-size:.86rem;font-weight:600;color:var(--dim);transition:.12s}
  .sw .knob{width:30px;height:17px;border-radius:999px;background:var(--line);position:relative;transition:.15s;flex:none}
  .sw .knob::after{content:"";position:absolute;top:2px;left:2px;width:13px;height:13px;border-radius:50%;background:#fff;transition:.15s;box-shadow:0 1px 2px rgba(0,0,0,.3)}
  .sw[aria-pressed="true"]{color:var(--text);border-color:color-mix(in srgb,var(--profit) 40%,var(--line))}
  .sw[aria-pressed="true"] .knob{background:var(--profit)}
  .sw[aria-pressed="true"] .knob::after{left:15px}
  .actions{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin-top:1.2rem}
  .btn{font-family:var(--sans);font-size:.84rem;font-weight:600;padding:.55rem .95rem;border-radius:10px;cursor:pointer;border:1px solid var(--line);background:var(--surface2);color:var(--text)}
  .btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
  .btn:hover{filter:brightness(1.04)} .btn:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
  .saved{font-size:.78rem;color:var(--profit);font-weight:600}
  details.cfg{margin-top:1rem} details.cfg summary{cursor:pointer;font-size:.76rem;color:var(--dim);font-family:var(--mono);list-style:none}
  details.cfg summary::-webkit-details-marker{display:none}
  details.cfg pre{margin:.6rem 0 0;font-family:var(--mono);font-size:.74rem;background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:.85rem;overflow-x:auto;color:var(--dim)}

  /* paper KPIs inside card */
  .minikpis{display:grid;grid-template-columns:repeat(4,1fr);gap:.9rem}
  .minikpi .lab{font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600}
  .minikpi .v{font-size:1.15rem;font-weight:700;margin-top:.25rem;font-family:var(--mono)}

  /* lab table */
  .labtbl{width:100%;border-collapse:collapse;font-size:.85rem}
  .labtbl th{text-align:left;padding:.5rem .6rem;font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);border-bottom:1px solid var(--line2)}
  .labtbl td{padding:.6rem;border-bottom:1px solid var(--line2);font-family:var(--mono);font-variant-numeric:tabular-nums}
  .labtbl tr:last-child td{border-bottom:none}
  .tablename{font-family:var(--sans);font-weight:600}
  .tag{display:inline-block;font-size:.64rem;font-weight:700;padding:.15em .5em;border-radius:6px;text-transform:uppercase;letter-spacing:.03em}
  .optbl{margin-bottom:1rem}
  .optbl-head{display:flex;align-items:center;gap:.6rem;margin:1.1rem 0 .3rem}
  .optbl-n{font-size:.72rem;color:var(--faint)}
  .optbl-pnl{margin-left:auto;font-family:var(--mono);font-weight:700;font-size:.8rem}
  .optbl-more{font-size:.72rem;color:var(--faint);padding:.2rem .6rem .6rem}
  .optbl-scroll{max-height:360px;overflow-y:auto;border:1px solid var(--line2);border-radius:8px}
  .optbl-scroll .labtbl th{position:sticky;top:0;background:var(--card,#fff);z-index:1}
  @media (prefers-color-scheme:dark){.optbl-scroll .labtbl th{background:#1a1c23}}
  .segbadge{display:inline-block;font-size:.58rem;font-weight:700;padding:.1em .4em;border-radius:4px;background:var(--line2);color:var(--faint);letter-spacing:.03em;vertical-align:middle}
  .tag.win{background:var(--profitsoft);color:var(--profit)} .tag.loss{background:var(--losssoft);color:var(--loss)} .tag.unc{background:var(--warnsoft);color:var(--warnc)}
  .wbar{height:7px;border-radius:4px;background:var(--line);overflow:hidden;min-width:70px}
  .wbar > i{display:block;height:100%;background:var(--profit);border-radius:4px}
  .verdict{display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;font-weight:600;padding:.4rem .7rem;border-radius:8px;background:var(--profitsoft);color:var(--profit)}
  .note{font-size:.8rem;color:var(--dim);margin:.9rem 0 0;line-height:1.5}

  /* roadmap */
  .rlist{display:flex;flex-direction:column}
  .ritem{display:grid;grid-template-columns:2rem 1fr auto;gap:.3rem .9rem;padding:.7rem 0;border-bottom:1px solid var(--line2);align-items:center}
  .ritem:last-child{border-bottom:none}
  .ritem .rn{font-family:var(--mono);font-weight:700;color:var(--faint);font-size:.85rem}
  .ritem .rt{font-weight:600;font-size:.92rem} .ritem .rd{font-size:.78rem;color:var(--dim)}
  .st{font-size:.64rem;font-weight:700;padding:.28em .6em;border-radius:7px;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}
  .st.built{background:var(--profitsoft);color:var(--profit)} .st.prog{background:var(--warnsoft);color:var(--warnc)}
  .st.none{background:var(--surface2);color:var(--faint);border:1px solid var(--line)} .st.defer{background:var(--brandsoft);color:var(--brand)}

  /* tree */
  .trunk{border:1px solid var(--line);border-radius:12px;background:var(--surface2);margin-bottom:.55rem;overflow:hidden}
  .trunk summary{cursor:pointer;padding:.7rem .9rem;display:grid;grid-template-columns:2.4rem 1fr auto;gap:.7rem;align-items:center;list-style:none}
  .trunk summary::-webkit-details-marker{display:none}
  .trunk .rn{font-family:var(--mono);font-weight:800;color:var(--brand);font-size:.9rem}
  .trunk .tn{font-weight:700;font-size:.95rem} .trunk .te{display:block;font-size:.78rem;color:var(--dim);font-weight:400}
  .ig{font-size:.6rem;font-weight:700;padding:.24em .5em;border-radius:6px;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}
  .ig-built{background:var(--profitsoft);color:var(--profit)} .ig-ignites_l7{background:var(--warnsoft);color:var(--warnc)}
  .ig-matures_l10{background:var(--brandsoft);color:var(--brand)} .ig-frontier_l11{background:var(--surface);color:var(--faint);border:1px solid var(--line)}
  .branches{display:flex;flex-wrap:wrap;gap:.35rem;padding:.2rem .9rem .85rem}
  .branches span{font-family:var(--mono);font-size:.73rem;background:var(--surface);border:1px solid var(--line);padding:.2em .5em;border-radius:6px;color:var(--dim)}
  .gated{font-size:.58rem;font-weight:700;color:var(--warnc);background:var(--warnsoft);padding:.12em .4em;border-radius:5px}
  .alerts{display:flex;flex-direction:column;gap:.5rem;margin-bottom:1.5rem}
  .alert{display:flex;align-items:flex-start;gap:.6rem;padding:.7rem .9rem;border-radius:11px;font-size:.85rem;border:1px solid}
  .alert .ic{flex:none;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:.7rem;font-weight:800;color:#fff;margin-top:1px}
  .alert.info{background:var(--brandsoft);border-color:color-mix(in srgb,var(--brand) 30%,var(--line))}
  .alert.info .ic{background:var(--brand)}
  .alert.warning{background:var(--warnsoft);border-color:color-mix(in srgb,var(--warnc) 40%,var(--line))}
  .alert.warning .ic{background:var(--warnc)}
  .alert.critical{background:var(--losssoft);border-color:color-mix(in srgb,var(--loss) 45%,var(--line))}
  .alert.critical .ic{background:var(--loss)}
  .alert .cat{font-family:var(--mono);font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;font-weight:700;opacity:.75}
  footer{font-size:.74rem;color:var(--faint);font-family:var(--mono);margin-top:2.5rem;text-align:center;line-height:1.7}
  @media (max-width:760px){ .kpis{grid-template-columns:repeat(2,1fr)} .grid2{grid-template-columns:1fr}
    .minikpis{grid-template-columns:repeat(2,1fr)} .ritem{grid-template-columns:1.7rem 1fr} .ritem .st{grid-column:1/-1;justify-self:start}
    .trunk summary{grid-template-columns:2rem 1fr} }
</style>
<div class="wrap">
  <header>
    <div class="logo">
      <div class="mark">N</div>
      <div><h1>NSE Algo Trader</h1><div class="sub" id="sub"></div></div>
    </div>
    <span class="modebadge paper" id="modebadge"><span class="dot"></span><span id="modetext">PAPER</span></span>
  </header>

  <div class="alerts" id="alerts"></div>
  <div class="kpis" id="kpis"></div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Controls</h2><span class="aside" id="ctrlaside"></span></div>
    <div class="body">
      <div class="grid2">
        <div class="field"><label>Paper capital (₹)</label><input type="number" id="capital" min="1000" step="10000"></div>
        <div class="field"><label>Max risk / trade (%)</label><input type="number" id="risk" min="0.1" max="100" step="0.1"></div>
        <div class="field"><label>Min capital / trade (₹)</label><input type="number" id="mincap" min="0" step="1000"></div>
        <div class="field"><label>Max capital / trade (₹)</label><input type="number" id="maxcap" min="0" step="1000"></div>
      </div>
      <div class="switchrow"><div class="lab">Segments</div><div class="switches" id="segments"></div></div>
      <div class="switchrow"><div class="lab">Strategies</div><div class="switches" id="strategies"></div></div>
      <div class="actions">
        <button class="btn" id="modeBtn" type="button">Switch to live</button>
        <button class="btn primary" id="copyBtn" type="button">Copy config JSON</button>
        <button class="btn" id="resetBtn" type="button">Reset</button>
        <span class="saved" id="savestate"></span>
      </div>
      <details class="cfg"><summary>View raw config JSON</summary><pre id="cfgPreview"></pre></details>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Open positions — live paper</h2><span class="aside" id="liveaside"></span></div>
    <div class="body">
      <div class="minikpis" id="livekpis"></div>
      <div class="minikpis" id="segboards"></div>
      <div id="openTbl"></div>
      <p class="note" id="opennote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Closed trades — today</h2><span class="aside" id="closedaside"></span></div>
    <div class="body"><table class="labtbl" id="closedTbl"></table></div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Paper trading — session P&L</h2><span class="aside">real data</span></div>
    <div class="body"><div class="minikpis" id="paperkpis"></div></div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Falsification lab — prediction tables</h2></div>
    <div class="body">
      <table class="labtbl" id="labTbl"></table>
      <p class="note" id="labnote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Layer roadmap</h2><span class="aside" id="roadaside"></span></div>
    <div class="body"><div class="rlist" id="roadmap"></div></div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Autonomous-AI concept tree</h2><span class="aside" id="treeCounts"></span></div>
    <div class="body"><div id="tree"></div></div>
  </div>

  <footer id="foot"></footer>
</div>
<script>
const SNAPSHOT = /*__DASHBOARD_SNAPSHOT_JSON__*/;
const LIVE_API_KEY = /*__LIVE_API_KEY__*/;
const rupee = n => "₹" + Math.round(n).toLocaleString("en-IN");
const rupeeShort = n => { const a=Math.abs(n);
  if(a>=1e7) return "₹"+(n/1e7).toFixed(2)+"Cr"; if(a>=1e5) return "₹"+(n/1e5).toFixed(2)+"L";
  if(a>=1e3) return "₹"+(n/1e3).toFixed(1)+"k"; return "₹"+Math.round(n); };
const CFG_KEY = "nse_algo_trader_control_config";
let cfg = JSON.parse(JSON.stringify(SNAPSHOT.control_config));
if(!LIVE_API_KEY){ try{ const s=localStorage.getItem(CFG_KEY); if(s) cfg=JSON.parse(s); }catch(e){} }

function saveCfg(){
  renderCfg();
  if(LIVE_API_KEY){
    fetch("/api/config?key="+encodeURIComponent(LIVE_API_KEY),{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(cfg)})
      .then(r=>{ const s=document.getElementById("savestate"); s.textContent=r.ok?"saved to VPS ✓":"save rejected";
        if(r.ok) setTimeout(()=>s.textContent="",2500); }).catch(()=>{});
  } else { try{ localStorage.setItem(CFG_KEY,JSON.stringify(cfg)); }catch(e){}
    const s=document.getElementById("savestate"); s.textContent="saved on this device ✓"; setTimeout(()=>s.textContent="",2000); }
}
function renderCfg(){
  document.getElementById("cfgPreview").textContent=JSON.stringify(cfg,null,2);
  const paper=cfg.trading_mode==="paper";
  const b=document.getElementById("modebadge"); b.className="modebadge "+(paper?"paper":"live");
  document.getElementById("modetext").textContent=paper?"PAPER":"LIVE";
  document.getElementById("modeBtn").textContent=paper?"Switch to live":"Switch to paper";
  document.getElementById("ctrlaside").textContent=paper?"virtual money — safe to experiment":"real capital — needs funded account + Algo-ID";
}
function bindNum(id,key){ const el=document.getElementById(id); el.value=cfg[key];
  el.addEventListener("change",()=>{ const v=parseFloat(el.value); if(!isNaN(v)){cfg[key]=v;saveCfg();} }); }
bindNum("capital","account_virtual_capital"); bindNum("mincap","min_capital_per_trade"); bindNum("maxcap","max_capital_per_trade");
const riskEl=document.getElementById("risk"); riskEl.value=(cfg.max_risk_per_trade_fraction*100).toFixed(1);
riskEl.addEventListener("change",()=>{ const v=parseFloat(riskEl.value); if(!isNaN(v)){cfg.max_risk_per_trade_fraction=v/100;saveCfg();} });

function switches(containerId,obj){ const c=document.getElementById(containerId); c.innerHTML="";
  Object.keys(obj).forEach(k=>{ const b=document.createElement("button"); b.type="button"; b.className="sw";
    b.setAttribute("aria-pressed",obj[k]?"true":"false");
    b.innerHTML='<span class="knob"></span><span>'+k.replace(/_/g," ")+'</span>';
    b.addEventListener("click",()=>{ obj[k]=!obj[k]; b.setAttribute("aria-pressed",obj[k]?"true":"false"); saveCfg(); });
    c.appendChild(b); }); }
switches("segments",cfg.segment_enabled); switches("strategies",cfg.strategy_enabled);

document.getElementById("modeBtn").addEventListener("click",()=>{ cfg.trading_mode=cfg.trading_mode==="paper"?"live":"paper"; saveCfg(); });
document.getElementById("copyBtn").addEventListener("click",async()=>{ const t=JSON.stringify(cfg,null,2);
  try{ await navigator.clipboard.writeText(t); const el=document.getElementById("copyBtn"); el.textContent="Copied ✓"; setTimeout(()=>el.textContent="Copy config JSON",1500);}catch(e){} });
document.getElementById("resetBtn").addEventListener("click",()=>{ cfg=JSON.parse(JSON.stringify(SNAPSHOT.control_config)); saveCfg();
  switches("segments",cfg.segment_enabled); switches("strategies",cfg.strategy_enabled);
  bindNum("capital","account_virtual_capital"); document.getElementById("capital").value=cfg.account_virtual_capital;
  document.getElementById("mincap").value=cfg.min_capital_per_trade; document.getElementById("maxcap").value=cfg.max_capital_per_trade;
  riskEl.value=(cfg.max_risk_per_trade_fraction*100).toFixed(1); });
renderCfg();

// --- live data rendering (called on load + on each auto-refresh poll) ---
const alertIcon={info:"i",warning:"!",critical:"!"};
const alertOrder={critical:0,warning:1,info:2};
const tagcls={confident_win:"win",confident_loss:"loss",uncertain:"unc"};
function renderLive(snap){
  document.getElementById("alerts").innerHTML=[...snap.alerts]
    .sort((a,b)=>alertOrder[a.level]-alertOrder[b.level]).map(a=>
    `<div class="alert ${a.level}"><span class="ic">${alertIcon[a.level]}</span>`+
    `<div><span class="cat">${a.category}</span> &nbsp;${a.message}</div></div>`).join("");
  const p=snap.paper_trading;
  const winTable=snap.prediction_tables.find(t=>t.table==="confident_win");
  const built=snap.layer_roadmap.filter(l=>l.status==="built").length;
  const kpi=(cls,lab,val,sub)=>`<div class="kpi ${cls}"><div class="lab">${lab}</div><div class="val mono">${val}</div><div class="sub">${sub}</div></div>`;
  document.getElementById("kpis").innerHTML=
    kpi(p.realized_pnl>=0?"profit":"loss","Paper P&L",rupeeShort(p.realized_pnl),p.fill_count+" fills · "+(p.is_flat?"flat":"OPEN"))+
    kpi("","Win-side accuracy",winTable&&winTable.actual_win_rate!=null?Math.round(winTable.actual_win_rate*100)+"%":"—",winTable&&winTable.trade_count?winTable.trade_count+" confident-win trades":"no trades")+
    kpi("","Layers built",built+"/11","core pipeline complete")+
    kpi("","AI trunks",snap.concept_tree_counts.trunk_count,"faculties mapped")+
    kpi("","AI branches",snap.concept_tree_counts.total_branch_count+"+","sub-features");
  // --- live open positions ---
  const lu=snap.live_universe_status;
  const ops=snap.open_positions||[];
  if(lu){
    document.getElementById("liveaside").textContent=
      (lu.is_market_open?"● market open":"○ market closed")+" · scanning "+lu.cash_universe_size.toLocaleString()+" cash";
    const totUnreal=ops.reduce((s,o)=>s+(o.unrealized_pnl||0),0);
    document.getElementById("livekpis").innerHTML=
      `<div class="minikpi"><div class="lab">Open now</div><div class="v">${lu.open_position_count}</div></div>`+
      `<div class="minikpi"><div class="lab">Unrealized</div><div class="v" style="color:${totUnreal>=0?'var(--profit)':'var(--loss)'}">${rupee(totUnreal)}</div></div>`+
      `<div class="minikpi"><div class="lab">Closed today</div><div class="v">${lu.closed_trade_count}</div></div>`+
      `<div class="minikpi"><div class="lab">Universe seeded</div><div class="v">${lu.seeded_count.toLocaleString()}/${lu.cash_universe_size.toLocaleString()}</div></div>`;
  }
  // Per-segment boards (cash / index-option / stock-option) + combined.
  const segLabel={cash:"NSE Cash",index_option:"Index Options",stock_option:"Stock Options"};
  const boards=snap.segment_boards||[];
  const combUnreal=ops.reduce((s,o)=>s+(o.unrealized_pnl||0),0);
  let segHtml=boards.map(b=>{
    const c=b.unrealized_pnl>=0?'var(--profit)':'var(--loss)';
    return `<div class="minikpi"><div class="lab">${segLabel[b.segment]||b.segment}</div>`+
      `<div class="v">${b.open_count} open</div>`+
      `<div class="sub" style="color:${c}">${rupee(b.unrealized_pnl)}</div></div>`;
  }).join("");
  segHtml+=`<div class="minikpi"><div class="lab">Combined realized</div>`+
    `<div class="v" style="color:${(snap.combined_realized_pnl||0)>=0?'var(--profit)':'var(--loss)'}">${rupee(snap.combined_realized_pnl||0)}</div>`+
    `<div class="sub">+ ${rupee(combUnreal)} unreal</div></div>`;
  document.getElementById("segboards").innerHTML=segHtml;
  // Closed trades table
  const seg3={cash:"cash",index_option:"index-opt",stock_option:"stock-opt"};
  const closed=snap.closed_trades||[];
  document.getElementById("closedaside").textContent=closed.length+" recent";
  let crows="<tr><th>Segment</th><th>Symbol</th><th>Side</th><th>Outcome</th><th>Realized P&L</th></tr>";
  if(!closed.length){ crows+=`<tr><td colspan="5" style="color:var(--faint)">no closed trades yet</td></tr>`; }
  closed.slice(0,25).forEach(c=>{
    const pc=c.realized_pnl>=0?'var(--profit)':'var(--loss)';
    crows+=`<tr><td>${seg3[c.segment]||c.segment}</td><td class="tablename">${c.trading_symbol}</td>`+
      `<td>${c.direction}</td><td>${c.outcome.replace(/_/g," ")}</td>`+
      `<td style="color:${pc}">${rupee(c.realized_pnl)}</td></tr>`;
  });
  document.getElementById("closedTbl").innerHTML=crows;
  // Split the live open positions into the three §9 tables, each a broker-
  // style positions grid (Symbol/Side/Qty/Entry/LTP/P&L/Stop/Target).
  const tableMeta=[
    ["confident_win","Confident WIN","win"],
    ["confident_loss","Confident LOSS","loss"],
    ["uncertain","Uncertain","unc"],
  ];
  const cols="<tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>LTP</th><th>Unreal P&L</th><th>Stop</th><th>Target</th></tr>";
  let html="";
  tableMeta.forEach(([key,label,cls])=>{
    const rows=ops.filter(o=>o.assigned_table===key)
                  .sort((a,b)=>(b.unrealized_pnl||0)-(a.unrealized_pnl||0));
    const grp=rows.reduce((s,o)=>s+(o.unrealized_pnl||0),0);
    html+=`<div class="optbl-head"><span class="tag ${cls}">${label}</span>`+
      `<span class="optbl-n">${rows.length} open</span>`+
      `<span class="optbl-pnl" style="color:${grp>=0?'var(--profit)':'var(--loss)'}">${rows.length?rupee(grp):''}</span></div>`;
    let body=cols;
    if(!rows.length){ body+=`<tr><td colspan="8" style="color:var(--faint)">— none —</td></tr>`; }
    rows.forEach(o=>{
      const up=o.unrealized_pnl; const upc=up==null?'':(up>=0?'var(--profit)':'var(--loss)');
      const sd=o.direction==="long"?'<span style="color:var(--profit)">BUY</span>':
               (o.direction==="short"?'<span style="color:var(--loss)">SELL</span>':'<span class="segbadge">SPREAD</span>');
      const segb=o.segment&&o.segment!=="cash"?`<span class="segbadge">${o.segment==="index_option"?"IDX":"STK"}</span> `:"";
      body+=`<tr><td class="tablename">${segb}${o.trading_symbol}</td><td>${sd}</td><td>${o.quantity}</td>`+
        `<td>${o.entry_price}</td><td>${o.last_price==null?'—':o.last_price}</td>`+
        `<td style="color:${upc}">${up==null?'—':rupee(up)}</td>`+
        `<td>${o.stop_loss_price}</td><td>${o.target_price}</td></tr>`;
    });
    // Scrollable container so ALL rows are reachable by scrolling (no "+N more").
    html+=`<div class="optbl-scroll"><table class="labtbl optbl">${body}</table></div>`;
  });
  if(!ops.length){ html=`<p style="color:var(--faint)">no open positions ${lu&&!lu.is_market_open?"(market closed)":"yet — seeding universe…"}</p>`; }
  document.getElementById("openTbl").innerHTML=html;
  document.getElementById("opennote").innerHTML="Live paper positions on the real feed, grouped by §9 prediction table — simulated fills, virtual capital. Auto-flattened by Layer 8 at 15:15 IST.";
  document.getElementById("paperkpis").innerHTML=
    `<div class="minikpi"><div class="lab">Starting capital</div><div class="v">${rupeeShort(p.starting_virtual_cash)}</div></div>`+
    `<div class="minikpi"><div class="lab">Realized P&L</div><div class="v" style="color:${p.realized_pnl>=0?'var(--profit)':'var(--loss)'}">${rupee(p.realized_pnl)}</div></div>`+
    `<div class="minikpi"><div class="lab">Fills</div><div class="v">${p.fill_count}</div></div>`+
    `<div class="minikpi"><div class="lab">Overnight</div><div class="v" style="color:${p.is_flat?'var(--profit)':'var(--loss)'}">${p.is_flat?"none":"OPEN"}</div></div>`;
  let rows="<tr><th>Table</th><th>Trades</th><th>Predicted</th><th>Actual win</th><th></th><th>Brier</th></tr>";
  snap.prediction_tables.forEach(t=>{
    const tg=`<span class="tag ${tagcls[t.table]||''}">${t.table.replace(/_/g," ")}</span>`;
    if(!t.trade_count){ rows+=`<tr><td class="tablename">${tg}</td><td>0</td><td>—</td><td>—</td><td></td><td>—</td></tr>`; return; }
    const wr=Math.round(t.actual_win_rate*100);
    rows+=`<tr><td class="tablename">${tg}</td><td>${t.trade_count}</td><td>${t.mean_win_probability.toFixed(2)}</td>`+
      `<td>${wr}%</td><td><div class="wbar"><i style="width:${wr}%"></i></div></td><td>${t.brier_score.toFixed(3)}</td></tr>`;
  });
  document.getElementById("labTbl").innerHTML=rows;
  const won=snap.confident_win_beats_confident_loss;
  document.getElementById("labnote").innerHTML=
    (won===null?'':`<span class="verdict">✓ confident-win beats confident-loss</span> `)+
    "Directional signal on a small sample — <b>not a validated edge</b>. No strategy reaches live capital before the Deflated-Sharpe / CPCV gate + human sign-off.";
  document.getElementById("sub").textContent="live dashboard · updated "+snap.generated_at.slice(11,16)+(LIVE_API_KEY?" · auto-refresh 20s":"");
}
renderLive(SNAPSHOT);

// auto-refresh in server mode: poll the snapshot and re-render live sections
if(LIVE_API_KEY){
  setInterval(()=>{ fetch("/api/snapshot?key="+encodeURIComponent(LIVE_API_KEY))
    .then(r=>r.ok?r.json():null).then(s=>{ if(s) renderLive(s); }).catch(()=>{}); }, 20000);
}

// roadmap
const stcls={built:"built",in_progress:"prog",not_started:"none",deferred:"defer"};
const stlab={built:"Built",in_progress:"In progress",not_started:"Planned",deferred:"Deferred"};
document.getElementById("roadaside").textContent=built+" built · 1 in progress";
document.getElementById("roadmap").innerHTML=SNAPSHOT.layer_roadmap.map(l=>
  `<div class="ritem"><span class="rn">${String(l.number).padStart(2,"0")}</span>`+
  `<div><div class="rt">${l.name}</div><div class="rd">${l.note}</div></div>`+
  `<span class="st ${stcls[l.status]}">${stlab[l.status]}</span></div>`).join("");

// tree
document.getElementById("treeCounts").textContent=SNAPSHOT.concept_tree_counts.trunk_count+" trunks · "+SNAPSHOT.concept_tree_counts.total_branch_count+"+ branches";
document.getElementById("tree").innerHTML=SNAPSHOT.concept_tree.map(t=>
  `<details class="trunk"><summary><span class="rn">${t.roman_number}</span>`+
  `<span class="tn">${t.name}<span class="te">${t.essence}${t.is_gated?' · <span class="gated">gated</span>':''}</span></span>`+
  `<span class="ig ig-${t.ignition}">${t.ignition.replace(/_/g," ")}</span></summary>`+
  `<div class="branches">${t.branch_names.map(b=>`<span>${b}</span>`).join("")}`+
  `${t.branch_count>t.branch_names.length?`<span style="color:var(--faint)">+${t.branch_count-t.branch_names.length} more</span>`:""}</div></details>`).join("");

document.getElementById("foot").innerHTML=
  "intraday-only NSE cash + options · Zerodha Kite · paper sandbox, human gate before live capital<br>"+
  "controls "+(LIVE_API_KEY?"write live to the VPS config the bot reads":"persist on this device; export the config to the VPS");
</script>
"""
