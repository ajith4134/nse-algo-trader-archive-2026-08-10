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
  /* B25b charts — roles from the validated palette (see the design doc; validator PASSed
     light+dark categorical and the blue<->red diverging poles). */
  .viz-root{
    --viz-series-1:#2a78d6; --viz-pos:#2a78d6; --viz-neg:#d03b3b; --viz-mid:#f0efec;
    --viz-grid:var(--line2); --viz-ink:var(--dim);
  }
  @media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{
    --viz-series-1:#3987e5; --viz-pos:#3987e5; --viz-neg:#d03b3b; --viz-mid:#383835;
  }}
  :root[data-theme="dark"] .viz-root{
    --viz-series-1:#3987e5; --viz-pos:#3987e5; --viz-neg:#d03b3b; --viz-mid:#383835;
  }
  .vizrow{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem}
  @media (max-width:820px){.vizrow{grid-template-columns:1fr}}
  .viz{margin:0}
  .viz figcaption{font-size:.78rem;font-weight:600;color:var(--text);margin-bottom:.6rem;line-height:1.35}
  .vizsub{display:block;font-weight:400;font-size:.7rem;color:var(--faint);margin-top:.15rem}
  .vizempty{color:var(--faint);font-size:.8rem;padding:1.5rem 0;text-align:center}
  .vizlabel{font-family:var(--mono);font-size:.66rem;fill:var(--viz-ink)}
  .vizvalue{font-family:var(--mono);font-size:.68rem;font-weight:600}
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
  .maplink{text-decoration:none;color:var(--accent);font-weight:600;font-size:.82rem;
    padding:.42em .8em;border:1px solid var(--line2);border-radius:999px;white-space:nowrap}
  .maplink:hover{border-color:var(--accent)}
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
  /* Segment categorical badges (validated palette: cash blue / index-opt magenta / stock-opt teal —
     scripts/validate_palette.js PASS light+dark, distinct from the P&L green/red/amber). Each badge
     always carries its segment text (the required relief for the dark magenta contrast WARN). */
  .tag.seg-cash{background:color-mix(in srgb,#2a78d6 15%,transparent);color:#2a78d6}
  .tag.seg-idx{background:color-mix(in srgb,#b5179e 15%,transparent);color:#b5179e}
  .tag.seg-stk{background:color-mix(in srgb,#0d8f7f 17%,transparent);color:#0d8f7f}
  /* Profit-engine categorical badges on option rows (validated Okabe-Ito ramp: theta blue / delta vermillion /
     vega green / gamma pink / relvalue orange — scripts/validate_palette.js PASS, CVD in the labelled-relief
     band). Each badge always carries its engine text (the required relief). Shows WHICH edge a trade is on. */
  .tag.eng-theta{background:color-mix(in srgb,#0072B2 16%,transparent);color:#0072B2}
  .tag.eng-delta{background:color-mix(in srgb,#D55E00 16%,transparent);color:#D55E00}
  .tag.eng-vega{background:color-mix(in srgb,#009E73 18%,transparent);color:#007a59}
  .tag.eng-gamma{background:color-mix(in srgb,#CC79A7 18%,transparent);color:#a6437e}
  .tag.eng-relvalue{background:color-mix(in srgb,#E69F00 20%,transparent);color:#946600}
  .tag.mini{font-size:.54rem;padding:.1em .4em}
  .wbar{height:7px;border-radius:4px;background:var(--line);overflow:hidden;min-width:70px}
  .wbar > i{display:block;height:100%;background:var(--profit);border-radius:4px}
  /* calibration bullet: actual as fill, predicted as a tick — the gap is seen, not color-coded */
  .calbar{position:relative;height:9px;border-radius:4px;background:var(--line);min-width:130px}
  .calbar > i{position:absolute;left:0;top:0;height:100%;border-radius:4px}
  .calbar > b{position:absolute;top:-3px;width:2px;height:15px;border-radius:1px;background:var(--text)}
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
  .branches span.built{color:var(--profit);background:var(--profitsoft);border-color:color-mix(in srgb,var(--profit) 40%,var(--line))}
  .branches span.partial{color:var(--warnc);background:var(--warnsoft);border-color:color-mix(in srgb,var(--warnc) 40%,var(--line))}
  .gated{font-size:.58rem;font-weight:700;color:var(--warnc);background:var(--warnsoft);padding:.12em .4em;border-radius:5px}
  /* LLM gateway (prominent, subscription-backed pool) */
  .llmcard{border-color:color-mix(in srgb,var(--brand) 32%,var(--line))}
  .llmlead{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;margin-bottom:.9rem}
  .llmlead .leadlbl{font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:700}
  .llmlead .leadbadge{font-family:var(--mono);font-weight:800;font-size:1.02rem;padding:.42em .85em;border-radius:10px;background:var(--brandsoft);color:var(--brand);border:1px solid color-mix(in srgb,var(--brand) 42%,var(--line))}
  .llmladder{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin-bottom:1rem}
  .llmladder .lane{font-family:var(--mono);font-size:.78rem;background:var(--surface);border:1px solid var(--line);padding:.3em .62em;border-radius:8px;color:var(--dim);display:flex;align-items:center;gap:.4rem}
  .llmladder .lane.lead{color:var(--brand);background:var(--brandsoft);border-color:color-mix(in srgb,var(--brand) 45%,var(--line));font-weight:700}
  .llmladder .lane .rank{font-size:.62rem;opacity:.55;font-weight:700}
  .llmladder .sep{color:var(--faint);font-size:.8rem}
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
<div class="wrap viz-root">
  <header>
    <div class="logo">
      <div class="mark">N</div>
      <div><h1>NSE Algo Trader</h1><div class="sub" id="sub"></div></div>
    </div>
    <div style="margin-left:auto;display:flex;align-items:center;gap:.7rem">
      <a id="walllink" class="maplink" href="#">📺 Operations Wall</a>
      <a id="podlink" class="maplink" href="#">🤖 Bot Pod</a>
      <a id="cataloguelink" class="maplink" href="#">📋 Feature Catalogue</a>
      <a id="maplink" class="maplink" href="#">🗺️ System Map</a>
      <span class="modebadge paper" id="modebadge"><span class="dot"></span><span id="modetext">PAPER</span></span>
    </div>
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

  <div class="card llmcard" id="llmGatewayCard">
    <div class="head"><span class="bar"></span><h2>LLM Gateway — subscription-backed provider pool</h2><span class="aside" id="llmaside"></span></div>
    <div class="body">
      <div class="llmlead" id="llmLead"></div>
      <div class="llmladder" id="llmLadder"></div>
      <div class="minikpis" id="llmkpis"></div>
      <p class="note" id="llmnote"></p>
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
    <div class="head"><span class="bar"></span><h2>Performance</h2><span class="aside" id="perfaside"></span></div>
    <div class="body">
      <div class="vizrow">
        <figure class="viz">
          <figcaption>Cumulative NET P&L across closed trades <span class="vizsub">after brokerage, STT, exchange, SEBI, GST &amp; stamp</span></figcaption>
          <div id="equityChart"></div>
        </figure>
        <figure class="viz">
          <figcaption>Capture ratio by mechanism <span class="vizsub">share of the profit each trade REACHED that it actually KEPT</span></figcaption>
          <div id="captureChart"></div>
        </figure>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Closed trades — all sessions (live + replay)</h2><span class="aside" id="closedaside"></span></div>
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
    <div class="head"><span class="bar"></span><h2>Strategy readiness — Deflated-Sharpe / CPCV gate</h2></div>
    <div class="body">
      <table class="labtbl" id="readyTbl"></table>
      <p class="note" id="readynote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Reflection — mechanism calibration (Layer 10 memory)</h2><span class="aside" id="reflectaside"></span></div>
    <div class="body">
      <table class="labtbl" id="reflectTbl"></table>
      <p class="note" id="reflectnote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Assumption tripwires (Layer 10)</h2><span class="aside" id="tripaside"></span></div>
    <div class="body">
      <table class="labtbl" id="tripTbl"></table>
      <p class="note" id="tripnote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Opponent ledger — who's on the other side (Layer 10 §10)</h2><span class="aside" id="oppaside"></span></div>
    <div class="body">
      <table class="labtbl" id="oppTbl"></table>
      <p class="note" id="oppnote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Information diet — what the bot consumes to decide (Layer 10 §10)</h2><span class="aside" id="dietaside"></span></div>
    <div class="body">
      <table class="labtbl" id="dietTbl"></table>
      <p class="note" id="dietnote"></p>
    </div>
  </div>

  <div class="card">
    <div class="head"><span class="bar"></span><h2>Feature coverage — every feature &amp; its live status</h2><span class="aside" id="feataside"></span></div>
    <div class="body">
      <table class="labtbl" id="featTbl"></table>
      <p class="note" id="featnote"></p>
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
document.getElementById("maplink").href = LIVE_API_KEY ? ("/map?key="+encodeURIComponent(LIVE_API_KEY)) : "/map";
document.getElementById("cataloguelink").href = LIVE_API_KEY ? ("/catalogue?key="+encodeURIComponent(LIVE_API_KEY)) : "/catalogue";
document.getElementById("podlink").href = LIVE_API_KEY ? ("/pod?key="+encodeURIComponent(LIVE_API_KEY)) : "/pod";
document.getElementById("walllink").href = LIVE_API_KEY ? ("/wall?key="+encodeURIComponent(LIVE_API_KEY)) : "/wall";
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
const tagcls={confident_win:"win",confident_loss:"loss",uncertain:"unc",
  engine_theta:"eng-theta",engine_delta:"eng-delta",engine_vega:"eng-vega",
  engine_gamma:"eng-gamma",engine_relvalue:"eng-relvalue"};
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

  // ---- B25b charts -------------------------------------------------------------------
  // Inline SVG, no library, no network. Palette roles are CSS vars validated by
  // scripts/validate_palette.js (light+dark categorical PASS; diverging poles PASS at
  // dEta 23.8 protan). Marks per the skill: 2px line, 4px rounded zero-anchored bar ends,
  // recessive grid, direct labels, hover tooltips.
  function vizEmpty(id,msg){ document.getElementById(id).innerHTML=`<div class="vizempty">${msg}</div>`; }

  function drawEquityCurve(closed){
    if(!closed||!closed.length){ return vizEmpty("equityChart","no closed trades yet"); }
    // Oldest -> newest, cumulative NET (gross minus real costs — plotting gross would be the
    // exact lie the cost model exists to stop).
    const pts=[...closed].reverse().reduce((acc,c)=>{
      const net=(c.realized_pnl||0)-(c.total_fees||0);
      acc.push((acc.length?acc[acc.length-1]:0)+net); return acc;
    },[]);
    const W=440,H=190,PL=52,PR=14,PT=12,PB=24;
    const lo=Math.min(0,...pts), hi=Math.max(0,...pts), span=(hi-lo)||1;
    const x=i=>PL+(i/Math.max(1,pts.length-1))*(W-PL-PR);
    const y=v=>PT+(1-(v-lo)/span)*(H-PT-PB);
    const path=pts.map((v,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const zeroY=y(0), last=pts[pts.length-1], lastC=last>=0?"var(--profit)":"var(--loss)";
    document.getElementById("equityChart").innerHTML=
      `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
            aria-label="Cumulative net profit and loss across ${pts.length} closed trades, ending at ${rupee(last)}">
        <line x1="${PL}" x2="${W-PR}" y1="${zeroY}" y2="${zeroY}" stroke="var(--viz-grid)" stroke-width="1"/>
        <text x="${PL-6}" y="${zeroY+3}" text-anchor="end" class="vizlabel">0</text>
        <text x="${PL-6}" y="${y(hi)+3}" text-anchor="end" class="vizlabel">${rupee(hi)}</text>
        <text x="${PL-6}" y="${y(lo)+3}" text-anchor="end" class="vizlabel">${rupee(lo)}</text>
        <path d="${path}" fill="none" stroke="var(--viz-series-1)" stroke-width="2"
              stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${x(pts.length-1)}" cy="${y(last)}" r="4" fill="var(--viz-series-1)"
                stroke="var(--surface)" stroke-width="2"/>
        <text x="${W-PR}" y="${Math.max(PT+10,y(last)-9)}" text-anchor="end"
              class="vizvalue" fill="${lastC}">${rupee(last)}</text>
        <text x="${PL}" y="${H-6}" class="vizlabel">oldest</text>
        <text x="${W-PR}" y="${H-6}" text-anchor="end" class="vizlabel">${pts.length} trades</text>
      </svg>`;
  }

  function drawCaptureChart(rows){
    if(!rows||!rows.length){ return vizEmpty("captureChart","no measured excursion yet — needs closed trades with MFE/MAE"); }
    const data=[...rows].sort((a,b)=>(a.capture_ratio||0)-(b.capture_ratio||0)).slice(0,6);
    const W=440,RH=30,PT=6,PL=8,PR=8,AX=Math.round(W*0.46);
    const H=PT*2+data.length*RH;
    const mx=Math.max(1,...data.map(d=>Math.abs(d.capture_ratio||0)));
    const half=Math.min(AX-PL-70,(W-PR-AX)-46);
    let bars="";
    data.forEach((d,i)=>{
      const v=d.capture_ratio||0, y=PT+i*RH+6, h=RH-14;
      const w=Math.max(2,Math.abs(v)/mx*half);
      const neg=v<0, xs=neg?AX-w:AX;
      const label=(d.mechanism_name||"").slice(0,26);
      // 4px rounded ends anchored to the zero axis; a 2px surface gap between adjacent bars.
      bars+=`<g><title>${label}: kept ${rupee(d.mean_realized_pnl||0)} of ${rupee(d.mean_maximum_favourable_profit||0)} reached over ${d.measured_count||0} trades</title>`+
        `<rect x="${xs}" y="${y}" width="${w}" height="${h}" rx="4"
               fill="${neg?"var(--viz-neg)":"var(--viz-pos)"}"/>`+
        `<text x="${AX-half-8}" y="${y+h-2}" text-anchor="start" class="vizlabel">${label}</text>`+
        `<text x="${neg?xs-6:xs+w+6}" y="${y+h-2}" text-anchor="${neg?"end":"start"}"
               class="vizvalue" fill="${neg?"var(--viz-neg)":"var(--viz-pos)"}">${Math.round(v*100)}%</text></g>`;
    });
    document.getElementById("captureChart").innerHTML=
      `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img"
            aria-label="Capture ratio by mechanism; negative means profit reached was given back">
        <line x1="${AX}" x2="${AX}" y1="${PT}" y2="${H-PT}" stroke="var(--viz-grid)" stroke-width="1"/>
        ${bars}
      </svg>`;
  }

  // Per-segment boards (cash / index-option / stock-option) + combined.
  const segLabel={cash:"NSE Cash",index_option:"Index Options",stock_option:"Stock Options"};
  const boards=snap.segment_boards||[];
  const combUnreal=ops.reduce((s,o)=>s+(o.unrealized_pnl||0),0);
  let segHtml=boards.map(b=>{
    const c=b.unrealized_pnl>=0?'var(--profit)':'var(--loss)';
    // B28: fees are REAL money already paid on this segment's closed trades.
    const fee=b.realised_fees||0;
    return `<div class="minikpi"><div class="lab">${segLabel[b.segment]||b.segment}</div>`+
      `<div class="v">${b.open_count} open</div>`+
      `<div class="sub" style="color:${c}">${rupee(b.unrealized_pnl)}</div>`+
      `<div class="sub" style="color:var(--faint)">fees ${rupee(fee)}</div></div>`;
  }).join("");
  // B28: combined realized is GROSS; show total fees and the NET beside it so a gross number is
  // never mistaken for take-home.
  const totalFees=(snap.closed_trades||[]).reduce((s,c)=>s+(c.total_fees||0),0);
  const grossRealized=snap.combined_realized_pnl||0;
  const netRealized=grossRealized-totalFees;
  // B33: the bot's REAL P&L = confident_win + uncertain only. confident_loss trades are DELIBERATE
  // learning probes (opened predicting a loss) — shown separately, scored on prediction accuracy
  // (a probe that LOST = the loss-prediction was RIGHT), NEVER folded into real money.
  const realRealized=snap.real_realized_pnl||0;
  const probePnl=snap.confident_loss_probe_realized_pnl||0;
  const probeAcc=snap.confident_loss_prediction_accuracy;
  segHtml+=`<div class="minikpi"><div class="lab">REAL P&L (conf-win + uncertain)</div>`+
    `<div class="v" style="color:${realRealized>=0?'var(--profit)':'var(--loss)'}">${rupee(realRealized)}</div>`+
    `<div class="sub">the bot's real money · excludes conf-loss probes</div></div>`;
  segHtml+=`<div class="minikpi"><div class="lab">Confident-loss LAB (probe)</div>`+
    `<div class="v" style="color:var(--dim)">${probeAcc!=null?Math.round(probeAcc*100)+'%':'—'}</div>`+
    `<div class="sub">loss-prediction accuracy · ${rupee(probePnl)} probe P&L (not real)</div></div>`;
  segHtml+=`<div class="minikpi"><div class="lab">Gross realized (incl. probes)</div>`+
    `<div class="v" style="color:${grossRealized>=0?'var(--profit)':'var(--loss)'}">${rupee(grossRealized)}</div>`+
    `<div class="sub">+ ${rupee(combUnreal)} unreal</div></div>`;
  segHtml+=`<div class="minikpi"><div class="lab">Fees paid / NET realized</div>`+
    `<div class="v" style="color:var(--loss)">${rupee(totalFees)}</div>`+
    `<div class="sub" style="color:${netRealized>=0?'var(--profit)':'var(--loss)'}">net ${rupee(netRealized)}</div></div>`;
  document.getElementById("segboards").innerHTML=segHtml;
  // B25b
  document.querySelectorAll(".viz-root").forEach(()=>{});
  drawEquityCurve(snap.closed_trades||[]);
  drawCaptureChart(snap.exit_efficiency_rows||[]);
  const perf=document.getElementById("perfaside");
  if(perf) perf.textContent=(snap.exit_efficiency_rows||[]).length+" mechanisms measured";
  // Closed trades table
  const seg3={cash:"cash",index_option:"index-opt",stock_option:"stock-opt"};
  const closed=snap.closed_trades||[];
  document.getElementById("closedaside").textContent=closed.length+" recent";
  // B33: the §9 table each trade opened under, tagged so a confident_loss LEARNING PROBE is never
  // read as a real loss (its loss = a correct loss-prediction). Real P&L excludes these — see the
  // headline split below.
  const tableLabel={confident_win:"conf-WIN",confident_loss:"conf-LOSS (probe)",uncertain:"uncertain",
    engine_theta:"Θ theta",engine_delta:"Δ delta",engine_vega:"ν vega",
    engine_gamma:"Γ gamma",engine_relvalue:"RV rel-val"};
  let crows="<tr><th>When</th><th>Segment</th><th>Symbol</th><th>Table</th><th>Side</th><th>Outcome</th><th>Realized P&L</th><th>Fees</th><th>Net</th><th>Source</th></tr>";
  if(!closed.length){ crows+=`<tr><td colspan="10" style="color:var(--faint)">no closed trades yet</td></tr>`; }
  closed.slice(0,60).forEach(c=>{
    const pc=c.realized_pnl>=0?'var(--profit)':'var(--loss)';
    const when=(c.closed_at||"").slice(0,16).replace("T"," ");
    const isReplay=c.provenance==='replay_faithful';
    const prov=isReplay?'replay':'live';
    const provc=isReplay?'var(--dim)':'var(--profit)';
    const tbl=c.assigned_table||'uncertain';
    crows+=`<tr><td class="num" style="color:var(--faint)">${when}</td>`+
      `<td>${seg3[c.segment]||c.segment}</td><td class="tablename">${c.trading_symbol}</td>`+
      `<td><span class="tag ${tagcls[tbl]||'unc'}">${tableLabel[tbl]||tbl}</span></td>`+
      `<td>${c.direction}</td><td>${c.outcome.replace(/_/g," ")}</td>`+
      `<td class="num" style="color:${pc}">${rupee(c.realized_pnl)}</td>`+
      `<td class="num" style="color:var(--faint)">${c.total_fees?rupee(c.total_fees):'—'}</td>`+
      `<td class="num" style="color:${(c.realized_pnl-(c.total_fees||0))>=0?'var(--profit)':'var(--loss)'}">${rupee(c.realized_pnl-(c.total_fees||0))}</td>`+
      `<td style="color:${provc};font-size:.72rem;font-weight:600">${prov}</td></tr>`;
  });
  document.getElementById("closedTbl").innerHTML=crows;
  // Split the live open positions into the three SEGMENT tables (cash intraday · index options ·
  // stock options — Rule L segment-equality), each a broker-style positions grid
  // (Symbol/Side/Qty/Entry/LTP/P&L/Stop/Target). The §9 confidence table each position opened under
  // (confident-WIN / confident-LOSS probe / uncertain) is preserved as a per-row badge so a deliberate
  // confident-LOSS learning probe is never misread as a real losing position (Rule K).
  const tableMeta=[
    ["cash","Cash Intraday","seg-cash"],
    ["index_option","Option Index","seg-idx"],
    ["stock_option","Option Stocks","seg-stk"],
  ];
  // B23: Max+ / Max- are this trade's best and worst unrealised P&L since it opened (MFE/MAE);
  // Locked is the ratcheting profit trail (— until it arms).
  const cols="<tr><th>Symbol</th><th>Table</th><th>Side</th><th>Qty</th><th>Entry</th><th>LTP</th><th>Unreal P&L</th><th>Max+</th><th>Max-</th><th>Locked</th><th>Stop</th><th>Target</th></tr>";
  const renderOpenRow=o=>{
    const up=o.unrealized_pnl; const upc=up==null?'':(up>=0?'var(--profit)':'var(--loss)');
    const sd=o.direction==="long"?'<span style="color:var(--profit)">BUY</span>':
             (o.direction==="short"?'<span style="color:var(--loss)">SELL</span>':'<span class="segbadge">SPREAD</span>');
    const ct=o.assigned_table||'uncertain';
    const confb=`<span class="tag mini ${tagcls[ct]||'unc'}">${tableLabel[ct]||ct}</span>`;
    return `<tr><td class="tablename">${o.trading_symbol}</td><td>${confb}</td><td>${sd}</td><td>${o.quantity}</td>`+
      `<td>${o.entry_price}</td><td>${o.last_price==null?'—':o.last_price}</td>`+
      `<td style="color:${upc}">${up==null?'—':rupee(up)}</td>`+
      `<td style="color:var(--profit)">${o.maximum_favourable_profit?rupee(o.maximum_favourable_profit):'—'}</td>`+
      `<td style="color:var(--loss)">${o.maximum_adverse_profit?rupee(o.maximum_adverse_profit):'—'}</td>`+
      `<td style="color:${o.profit_locked==null?'var(--faint)':'var(--profit)'}">${o.profit_locked==null?'—':rupee(o.profit_locked)}</td>`+
      `<td>${o.stop_loss_price}</td><td>${o.target_price}</td></tr>`;
  };
  // Any position whose segment isn't one of the three known keys is surfaced in an "Other" table rather
  // than silently dropped (Rule K).
  const knownSeg=new Set(tableMeta.map(m=>m[0]));
  const boardsToRender=tableMeta.slice();
  const otherRows=ops.filter(o=>!knownSeg.has(o.segment));
  if(otherRows.length) boardsToRender.push(["__other__","Other / unclassified","unc"]);
  let html="";
  boardsToRender.forEach(([key,label,cls])=>{
    const rows=(key==="__other__"?otherRows:ops.filter(o=>o.segment===key))
                  .sort((a,b)=>(b.unrealized_pnl||0)-(a.unrealized_pnl||0));
    const grp=rows.reduce((s,o)=>s+(o.unrealized_pnl||0),0);
    html+=`<div class="optbl-head"><span class="tag ${cls}">${label}</span>`+
      `<span class="optbl-n">${rows.length} open</span>`+
      `<span class="optbl-pnl" style="color:${grp>=0?'var(--profit)':'var(--loss)'}">${rows.length?rupee(grp):''}</span></div>`;
    let body=cols;
    if(!rows.length){ body+=`<tr><td colspan="12" style="color:var(--faint)">— none —</td></tr>`; }
    rows.forEach(o=>{ body+=renderOpenRow(o); });
    // Scrollable container so ALL rows are reachable by scrolling (no "+N more").
    html+=`<div class="optbl-scroll"><table class="labtbl optbl">${body}</table></div>`;
  });
  if(!ops.length){ html=`<p style="color:var(--faint)">no open positions ${lu&&!lu.is_market_open?"(market closed)":"yet — seeding universe…"}</p>`; }
  document.getElementById("openTbl").innerHTML=html;
  document.getElementById("opennote").innerHTML="Live paper positions on the real feed, grouped by SEGMENT — NSE cash intraday · index options · stock options (Rule L). The <b>Table</b> badge keeps each position's §9 confidence class (conf-WIN / conf-LOSS probe / uncertain). Simulated fills, virtual capital. Auto-flattened by Layer 8 at 15:15 IST.";
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
  // --- strategy readiness (Deflated-Sharpe / CPCV promotion gate) ---
  const rd=snap.strategy_readiness||[];
  let rrows="<tr><th>Strategy</th><th>Trades</th><th>Sharpe</th><th>Deflated SR</th><th>Verdict</th></tr>";
  if(!rd.length){ rrows+=`<tr><td colspan="5" style="color:var(--faint)">gathering trades…</td></tr>`; }
  const verdictLabel={promote_to_live_candidate:"✓ promote candidate",reject_insufficient_trades:"gathering",reject_deflated_sharpe_too_low:"✗ not validated",gathering_trades:"gathering"};
  rd.forEach(s=>{
    const v=verdictLabel[s.outcome]||s.outcome;
    const vc=s.promoted?'var(--profit)':(s.outcome==='reject_deflated_sharpe_too_low'?'var(--loss)':'var(--faint)');
    rrows+=`<tr><td class="tablename">${s.strategy}</td><td>${s.trade_count}</td>`+
      `<td>${s.per_trade_sharpe_ratio==null?'—':s.per_trade_sharpe_ratio.toFixed(2)}</td>`+
      `<td>${s.deflated_sharpe_ratio==null?'—':s.deflated_sharpe_ratio.toFixed(3)}</td>`+
      `<td style="color:${vc};font-weight:600">${v}</td></tr>`;
  });
  document.getElementById("readyTbl").innerHTML=rrows;
  document.getElementById("readynote").innerHTML="Each strategy's realized per-trade returns run through CPCV → the Deflated-Sharpe gate (min 30 trades). A 'promote candidate' is a statistical readiness signal only — paper, not live capital.";
  // --- Reflection: per-mechanism predicted-vs-actual calibration (L10 memory) ---
  const rb=snap.reflection_board||[];
  // §53 slice 3a: show the live-vs-replay experience mix so over-reliance on
  // 24/7 historical replay is visible (only when replay experiences exist).
  const prov=snap.experiment_count_by_provenance||{};
  const liveExp=prov.live||0, replayExp=prov.replay_faithful||0;
  const provMix=replayExp>0?` (${liveExp.toLocaleString()} live · ${replayExp.toLocaleString()} replay)`:"";
  document.getElementById("reflectaside").textContent=(snap.memory_experiment_count||0).toLocaleString()+" experiences"+provMix;
  // The gap is over-confidence when predicted >> actual (the danger). Binary
  // signed status, not a 3-way magnitude scale (the red↔amber pair fails CVD
  // separation; the bar shows the gap geometrically instead).
  const calColor=g=>g>=0.15?'var(--loss)':(g<=-0.15?'var(--brand)':'var(--profit)');
  let rbrows="<tr><th>Strategy</th><th>Mechanism</th><th>n</th><th>Calibration&nbsp;— predicted ▏ vs actual&nbsp;█</th><th>Gap</th><th>Brier</th><th title=\"mean log-score, bits — 1.0 = coin-flip; >1 = confidently wrong\">Log</th></tr>";
  if(!rb.length){ rbrows+=`<tr><td colspan="7" style="color:var(--faint)">learning — no closed experiments yet</td></tr>`; }
  rb.slice(0,12).forEach(r=>{
    const gap=r.predicted_win_rate-r.actual_win_rate;
    const pred=Math.round(r.predicted_win_rate*100), act=Math.round(r.actual_win_rate*100);
    const c=calColor(gap);
    const bar=`<div class="calbar" title="predicted ${pred}% · actual ${act}%">`+
      `<i style="width:${act}%;background:${c}"></i><b style="left:${pred}%"></b></div>`;
    // Log-score > 1 bit = worse than a coin-flip (confidently wrong) -> flag red.
    const logv=r.mean_log_score, logc=logv!=null&&logv>=1.0?'var(--loss)':'var(--dim)';
    rbrows+=`<tr><td class="tablename">${r.strategy_tag.replace(/_/g," ")}</td>`+
      `<td style="max-width:22ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.mechanism_name}">${r.mechanism_name}</td>`+
      `<td>${r.experiment_count}</td><td>${bar}</td>`+
      `<td style="color:${c};font-weight:600">${gap>=0?'+':''}${Math.round(gap*100)}%</td>`+
      `<td>${r.mean_brier.toFixed(3)}</td>`+
      `<td style="color:${logc}">${logv!=null?logv.toFixed(2):'—'}</td></tr>`;
  });
  document.getElementById("reflectTbl").innerHTML=rbrows;
  // §53 slice 3b-ii: running prequential forecast SKILL (log-loss bits · Brier),
  // live vs replay. <1.0 bit = better than a coin-flip; higher = confidently wrong.
  const pfs=snap.prequential_forecast_score||{};
  const skill=g=>(g&&g.experiment_count)?`${(g.mean_log_loss_bits).toFixed(2)} bits · Brier ${(g.mean_brier).toFixed(3)}`:"—";
  const replaySkill=(pfs.replay_faithful&&pfs.replay_faithful.experiment_count)?` · replay ${skill(pfs.replay_faithful)}`:"";
  const skillLine=pfs.overall?`<b>Forecast skill (prequential):</b> live ${skill(pfs.live||pfs.overall)}${replaySkill}. `:"";
  document.getElementById("reflectnote").innerHTML=skillLine+"Each closed §9 experiment (cash + options) is a memory node. The bar is the <b>actual</b> win-rate; the tick <b>▏</b> is what was <b>predicted</b>. A tick far to the RIGHT of the bar = over-confident thesis (red) — the bot learns to distrust it; tick left of the bar = under-confident (blue).";
  // --- Assumption tripwires (L10 slice 2) ---
  const tw=snap.assumption_tripwires||[];
  const statusOrder={violated:0,holding:1,insufficient_data:2};
  const tripped=tw.filter(v=>v.status==="violated");
  document.getElementById("tripaside").textContent=tripped.length?(tripped.length+" tripped"):"all holding";
  let twrows="<tr><th>Assumption</th><th>Scope</th><th>n</th><th>Status</th><th>Detail</th></tr>";
  if(!tw.length){ twrows+=`<tr><td colspan="5" style="color:var(--faint)">gathering evidence…</td></tr>`; }
  [...tw].sort((a,b)=>statusOrder[a.status]-statusOrder[b.status]).slice(0,14).forEach(v=>{
    const sc=v.status==="violated"?'var(--loss)':(v.status==="holding"?'var(--profit)':'var(--faint)');
    const label=v.status==="violated"?"✗ TRIPPED":(v.status==="holding"?"✓ holding":"gathering");
    twrows+=`<tr><td class="tablename">${v.assumption_name}</td>`+
      `<td style="max-width:24ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${v.scope}">${v.scope}</td>`+
      `<td>${v.sample_count}</td><td style="color:${sc};font-weight:600">${label}</td>`+
      `<td style="color:var(--dim);font-size:.8rem">${v.detail}</td></tr>`;
  });
  document.getElementById("tripTbl").innerHTML=twrows;
  const vmc=snap.vetoed_mechanism_count||0, vec=snap.vetoed_entry_count||0, sec=snap.shadow_entry_count||0;
  const shadow=sec?` <span style="color:var(--dim)">+ ${sec.toLocaleString()} shadow probe${sec===1?'':'s'} kept alive to allow recovery.</span>`:"";
  const antibody=vmc?`<b style="color:var(--loss)">Antibody active:</b> ${vmc} mechanism${vmc>1?'s':''} auto-vetoed · ${vec.toLocaleString()} new entr${vec===1?'y':'ies'} blocked.${shadow} `:"";
  document.getElementById("tripnote").innerHTML=antibody+"Significance-tested (min 12 trades). A tripped thesis is statistically refuted by the memory — the bot then <b>vetoes new entries</b> on that mechanism (Layer 10 antibody feedback).";
  // --- Opponent ledger: FII vs Client participant-wise OI (L10 §10) ---
  const opp=snap.opponent_ledger;
  const leanColor={bullish:'var(--profit)',bearish:'var(--loss)',neutral:'var(--faint)'};
  if(!opp){
    document.getElementById("oppaside").textContent="no report yet";
    document.getElementById("oppTbl").innerHTML=`<tr><td style="color:var(--faint)">awaiting NSE participant-wise OI (EOD ~19:00 IST)…</td></tr>`;
    document.getElementById("oppnote").innerHTML="NSE's daily Client/DII/FII/Pro open-interest split, read as “who is on the other side.” A multi-day <b>confirmation</b> input, never an intraday trigger.";
  } else {
    const lc=leanColor[opp.directional_lean]||'var(--faint)';
    document.getElementById("oppaside").innerHTML=`<span style="color:${lc};font-weight:600">FII ${opp.directional_lean}</span> · ${opp.report_date_iso}`;
    const sgn=n=>(n>0?"+":"")+Number(n).toLocaleString();
    const netColor=n=>n>0?'var(--profit)':(n<0?'var(--loss)':'var(--faint)');
    let rows="<tr><th>Party</th><th>Index-fut net (L−S)</th><th>Index-opt call bias</th></tr>";
    rows+=`<tr><td class="tablename">FII</td>`+
      `<td style="color:${netColor(opp.fii_index_futures_net)};font-weight:600">${sgn(opp.fii_index_futures_net)}`+
      (opp.fii_index_futures_long_short_ratio!=null?` <span style="color:var(--dim);font-weight:400">L/S ${opp.fii_index_futures_long_short_ratio.toFixed(2)}</span>`:"")+`</td>`+
      `<td style="color:${netColor(opp.fii_index_options_net_call_bias)}">${sgn(opp.fii_index_options_net_call_bias)}</td></tr>`;
    rows+=`<tr><td class="tablename">Client (retail)</td>`+
      `<td style="color:${netColor(opp.client_index_futures_net)};font-weight:600">${sgn(opp.client_index_futures_net)}</td>`+
      `<td style="color:${netColor(opp.client_index_options_net_call_bias)}">${sgn(opp.client_index_options_net_call_bias)}</td></tr>`;
    document.getElementById("oppTbl").innerHTML=rows;
    const trap=opp.retail_on_other_side?` <b style="color:var(--warnc)">⚠ Retail leaning the OTHER way</b> — reversal-trap watch.`:"";
    const convColor={high:'var(--profit)',normal:'var(--dim)',low:'var(--faint)'};
    const conv=opp.participation_conviction?` <span style="color:${convColor[opp.participation_conviction]||'var(--dim)'}">FII activity: <b>${opp.participation_conviction}</b> conviction (churn ${opp.fii_index_futures_churn!=null?opp.fii_index_futures_churn.toFixed(2):'n/a'}${opp.fii_volume_share!=null?', '+Math.round(opp.fii_volume_share*100)+'% of index-fut volume':''}).</span>`:"";
    const trendColor={confirming:'var(--loss)',weakening:'var(--profit)',flat:'var(--dim)'};
    const trend=opp.fii_net_trend?` <span style="color:${trendColor[opp.fii_net_trend]||'var(--dim)'}">${opp.fii_net_window_days}-day FII-net trend: <b>${opp.fii_net_trend}</b> (${opp.fii_net_change_over_window>0?'+':''}${Number(opp.fii_net_change_over_window).toLocaleString()}).</span>`:"";
    const pdc=snap.positioning_deferred_count||0;
    const deferred=pdc?` <b style="color:var(--warnc)">${pdc.toLocaleString()} new entr${pdc===1?'y':'ies'} deferred</b> (institutions on the other side).`:"";
    document.getElementById("oppnote").innerHTML=opp.headline+trap+conv+trend+deferred+" <span style=\"color:var(--dim)\">NSE participant-wise OI + volume · a multi-day confirmation input, not an intraday trigger.</span>";
  }
  // --- Information diet: which sources shape the decisions (L10 §10) ---
  const diet=snap.information_diet;
  const dietStatusColor={healthy:'var(--profit)',warning:'var(--loss)',gathering:'var(--faint)'};
  if(!diet){
    document.getElementById("dietaside").textContent="—";
    document.getElementById("dietTbl").innerHTML=`<tr><td style="color:var(--faint)">no decisions yet</td></tr>`;
    document.getElementById("dietnote").textContent="Accounts for which information sources shape each entry — so an over-reliance, or the memory not influencing trades, is visible.";
  } else {
    const sc=dietStatusColor[diet.health_status]||'var(--faint)';
    document.getElementById("dietaside").innerHTML=`<span style="color:${sc};font-weight:600">${diet.health_status}</span> · ${(diet.decisions_considered||0).toLocaleString()} decisions`;
    const shares=diet.influence_share_by_source||{};
    let rows="<tr><th>Information source</th><th>Influence on decisions</th></tr>";
    Object.keys(shares).forEach(src=>{
      const pct=Math.round((shares[src]||0)*100);
      rows+=`<tr><td class="tablename">${src}</td>`+
        `<td><div class="wbar" style="display:inline-block;width:120px;vertical-align:middle"><i style="width:${pct}%"></i></div> <span style="font-variant-numeric:tabular-nums">${pct}%</span></td></tr>`;
    });
    document.getElementById("dietTbl").innerHTML=rows;
    document.getElementById("dietnote").innerHTML=`<b style="color:${sc}">Memory influence: ${Math.round((diet.memory_influence_share||0)*100)}%</b> — ${diet.note}`;
  }
  // --- Feature coverage: every §53/ADVANCED feature & its live status (Rule N) ---
  const feats=snap.feature_surfaces||[];
  const featColor={active:'var(--profit)',gathering:'var(--faint)',idle:'var(--dim)',blocked:'var(--loss)',off:'var(--faint)',unknown:'var(--warnc)'};
  const featIcon={active:'●',gathering:'◍',idle:'○',blocked:'▲',off:'○',unknown:'▲'};
  if(!feats.length){
    document.getElementById("feataside").textContent="—";
    document.getElementById("featTbl").innerHTML=`<tr><td style="color:var(--faint)">warming up…</td></tr>`;
  } else {
    const shown=feats.filter(f=>f.status!=='unknown').length;
    document.getElementById("feataside").innerHTML=`<span style="font-weight:600">${shown}/${feats.length}</span> surfaced`;
    let rows="<tr><th>Feature</th><th>Status</th><th>Live</th></tr>";
    feats.forEach(f=>{
      const c=featColor[f.status]||'var(--faint)';
      const metrics=(f.metrics||[]).map(m=>`<span style="color:var(--dim)">${m[0]}:</span> ${m[1]}`).join(" &nbsp;·&nbsp; ");
      rows+=`<tr><td class="tablename">${f.title}</td>`+
        `<td><span style="color:${c};font-weight:600">${featIcon[f.status]||'—'} ${f.status}</span></td>`+
        `<td>${metrics||'<span style="color:var(--faint)">—</span>'}</td></tr>`;
    });
    document.getElementById("featTbl").innerHTML=rows;
  }
  // --- LLM Gateway (prominent): the subscription-led cost ladder (idea #8) ---
  const llm=feats.find(f=>f.key==='strategic_llm_analyst');
  const llmCard=document.getElementById('llmGatewayCard');
  if(!llm){ if(llmCard) llmCard.style.display='none'; }
  else {
    if(llmCard) llmCard.style.display='';
    const mget=k=>{const m=(llm.metrics||[]).find(x=>x[0]===k);return m?m[1]:'';};
    const lc=featColor[llm.status]||'var(--faint)';
    document.getElementById('llmaside').innerHTML=`<span style="color:${lc};font-weight:700">${featIcon[llm.status]||'—'} ${llm.status}</span>`;
    const lead=mget('lead lane')||'—';
    document.getElementById('llmLead').innerHTML=
      `<span class="leadlbl">Lead lane</span><span class="leadbadge">${lead}</span>`+
      `<span class="leadlbl">flat-cost · Haiku · auto-failover on cap</span>`;
    const pool=(mget('pool')||lead).replace(/…\s*$/,'').split(',').map(s=>s.trim()).filter(Boolean);
    document.getElementById('llmLadder').innerHTML=pool.map((p,i)=>
      `<span class="lane${i===0?' lead':''}"><span class="rank">${i+1}</span>${p}</span>`+
      (i<pool.length-1?'<span class="sep">›</span>':'')).join('');
    const lk=[['providers',mget('providers')||'—'],['transport',mget('transport')||'—'],['tokens (haiku-4-5)',mget('tokens')||'0 (idle · 0 calls)'],['served by',mget('served by')||'idle'],['status',llm.status]];
    document.getElementById('llmkpis').innerHTML=lk.map(([k,v])=>
      `<div class="minikpi"><div class="lab">${k}</div><div class="v">${v}</div></div>`).join('');
    document.getElementById('llmnote').textContent=llm.note||'';
  }
  document.getElementById("featnote").innerHTML="Every feature must register a surface (Rule N) — a “▲ unknown / not yet surfaced” row fails the coverage audit. Wired-but-invisible ≠ shipped.";
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
document.getElementById("roadaside").textContent=SNAPSHOT.layer_roadmap.filter(l=>l.status==="built").length+" built · 1 in progress";
document.getElementById("roadmap").innerHTML=SNAPSHOT.layer_roadmap.map(l=>
  `<div class="ritem"><span class="rn">${String(l.number).padStart(2,"0")}</span>`+
  `<div><div class="rt">${l.name}</div><div class="rd">${l.note}</div></div>`+
  `<span class="st ${stcls[l.status]}">${stlab[l.status]}</span></div>`).join("");

// tree — atlas build coverage (build-to-100% program): every branch chip is coloured by status.
const _ctc=SNAPSHOT.concept_tree_counts;
document.getElementById("treeCounts").textContent=
  _ctc.built_branch_count+"/"+_ctc.total_branch_count+" branches built ("+_ctc.built_pct+"%) · "+
  _ctc.partial_branch_count+" partial · "+_ctc.trunk_count+" trunks";
document.getElementById("tree").innerHTML=SNAPSHOT.concept_tree.map(t=>{
  const branches=t.branches||t.branch_names.map(n=>({name:n,status:"unbuilt"}));
  return `<details class="trunk"><summary><span class="rn">${t.roman_number}</span>`+
  `<span class="tn">${t.name}<span class="te">${t.essence}${t.is_gated?' · <span class="gated">gated</span>':''}</span></span>`+
  `<span class="ig ig-${t.ignition}">${(t.built_branch_count||0)}/${t.branch_count} built</span></summary>`+
  `<div class="branches">${branches.map(b=>`<span class="${b.status}">${b.name}</span>`).join("")}`+
  `${t.branch_count>branches.length?`<span style="color:var(--faint)">+${t.branch_count-branches.length} more</span>`:""}</div></details>`;
}).join("");

document.getElementById("foot").innerHTML=
  "intraday-only NSE cash + options · Zerodha Kite · paper sandbox, human gate before live capital<br>"+
  "controls "+(LIVE_API_KEY?"write live to the VPS config the bot reads":"persist on this device; export the config to the VPS");
</script>
"""
