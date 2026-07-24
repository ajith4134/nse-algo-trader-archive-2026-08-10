"""Renders the living System Map (docs/SYSTEM_MAP.md) as its own dashboard page.

Served at `/map` (a separate page opened from the main dashboard, not inline)
so the whole architecture & data-flow map — including its Mermaid diagrams —
can be browsed on a phone/laptop. The markdown is rendered client-side
(marked) and the ```mermaid fences are drawn by mermaid.js. Because this page
is served by our own FastAPI server (not under the Artifact CSP), it may load
those two libraries from a CDN; a graceful fallback shows the raw text if the
CDN is unreachable.
"""

from __future__ import annotations

import json
from pathlib import Path

_SYSTEM_MAP_PATH = Path(__file__).resolve().parents[3] / "docs" / "SYSTEM_MAP.md"


def load_system_map_markdown() -> str:
    try:
        return _SYSTEM_MAP_PATH.read_text()
    except OSError:
        return "# System Map\n\n_docs/SYSTEM_MAP.md not found on this server._"


def render_system_map_html(markdown_text: str, live_api_key: str | None = None) -> str:
    # Embed the markdown as JSON in a data island (avoids all escaping issues
    # except a literal </script>, which the map never contains — guard anyway).
    markdown_json = json.dumps(markdown_text).replace("</", "<\\/")
    back_href = f"/?key={live_api_key}" if live_api_key else "/"
    return _SYSTEM_MAP_PAGE_TEMPLATE.replace("__MARKDOWN_JSON__", markdown_json).replace(
        "__BACK_HREF__", back_href
    )


_SYSTEM_MAP_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>System Map — NSE Algo Trader</title>
<style>
  :root{
    --bg:#0e1016; --panel:#151823; --line:#232838; --ink:#e6e8ef;
    --muted:#9aa3b8; --faint:#5f6981; --accent:#818cf8; --accent2:#a78bfa;
  }
  @media (prefers-color-scheme:light){
    :root{--bg:#f6f7fb;--panel:#ffffff;--line:#e6e8f0;--ink:#1a1d29;
          --muted:#5a6478;--faint:#8b93a7;--accent:#4f46e5;--accent2:#7c3aed;}
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    -webkit-font-smoothing:antialiased}
  header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:1rem;
    padding:.8rem 1.2rem;background:color-mix(in srgb,var(--bg) 88%,transparent);
    backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
  header .title{font-weight:700;letter-spacing:.01em}
  header .title .accent{color:var(--accent)}
  .back{color:var(--accent);text-decoration:none;font-weight:600;font-size:.9rem;
    padding:.4rem .7rem;border:1px solid var(--line);border-radius:8px}
  .back:hover{border-color:var(--accent)}
  .wrap{max-width:1080px;margin:0 auto;padding:1.5rem 1.2rem 5rem}
  h1{font-size:1.7rem;text-wrap:balance;margin:1.6rem 0 .6rem;line-height:1.2}
  h2{font-size:1.25rem;margin:2.2rem 0 .5rem;padding-top:1rem;
    border-top:1px solid var(--line);text-wrap:balance}
  h3{font-size:1.02rem;margin:1.4rem 0 .4rem;color:var(--accent2)}
  p,li{color:var(--ink)}
  a{color:var(--accent)}
  code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em;
    background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:.06em .35em}
  pre{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:1rem;overflow-x:auto}
  pre code{background:none;border:none;padding:0}
  table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.9rem;display:block;overflow-x:auto}
  th,td{border:1px solid var(--line);padding:.5rem .7rem;text-align:left;vertical-align:top}
  th{background:var(--panel);color:var(--muted);font-weight:600;text-transform:uppercase;
    font-size:.7rem;letter-spacing:.04em}
  blockquote{margin:1rem 0;padding:.7rem 1rem;border-left:3px solid var(--accent);
    background:var(--panel);border-radius:0 8px 8px 0;color:var(--muted)}
  .mermaid{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:1rem;margin:1.2rem 0;overflow-x:auto;text-align:center}
  hr{border:none;border-top:1px solid var(--line);margin:2rem 0}
  .note{color:var(--faint);font-size:.85rem}
</style>
</head>
<body>
<header>
  <a class="back" href="__BACK_HREF__">&larr; Dashboard</a>
  <span class="title">System Map <span class="accent">&middot; live architecture &amp; data flow</span></span>
</header>
<div class="wrap"><div id="content"><p class="note">Rendering the map&hellip;</p></div></div>

<script type="application/json" id="mapmd">__MARKDOWN_JSON__</script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script type="module">
  const md = JSON.parse(document.getElementById('mapmd').textContent);
  const content = document.getElementById('content');
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  function renderRaw(){ content.innerHTML=''; const pre=document.createElement('pre');
    pre.textContent=md; content.appendChild(pre); }
  try{
    if(!window.marked){ throw new Error('marked failed to load'); }
    content.innerHTML = window.marked.parse(md);
    // turn ```mermaid code blocks into <div class="mermaid"> for mermaid.run()
    content.querySelectorAll('code.language-mermaid').forEach(c=>{
      const d=document.createElement('div'); d.className='mermaid'; d.textContent=c.textContent;
      c.parentElement.replaceWith(d);
    });
    const mermaid = (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
    mermaid.initialize({startOnLoad:false, theme: dark?'dark':'default', securityLevel:'loose'});
    await mermaid.run({querySelector:'.mermaid'});
  }catch(e){
    // CDN blocked / offline -> show the raw markdown so the map is still readable
    renderRaw();
    const n=document.createElement('p'); n.className='note';
    n.textContent='(Diagrams need internet for the renderer; showing the raw map text.)';
    content.prepend(n);
  }
</script>
</body>
</html>
"""
