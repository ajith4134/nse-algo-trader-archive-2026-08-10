# B25c — dashboard delivery stack: the REAL sourcing pass (2026-07-27)

Clears the sourcing-gate blockers logged against `b25b_performance_charts_design` and B25c. Verified
live against PyPI JSON APIs, GitHub Releases, and — for the safety-critical offline claims —
**direct inspection of installed wheel contents**, not documentation prose.

## The operator's hard constraints (all four are gates, not preferences)

1. **No broker token dependency** — every panel except live open/close renders from local state.
2. **Offline-capable** — no CDN/network at runtime; must work on a phone with no external access.
3. **Phone-usable.**
4. **Single maintainer** — maintenance burden outweighs feature ceiling.

## Recommendation

**FastAPI (keep) + Jinja2/`DictLoader` panel templates + HTMX 2.0.10 (vendored, 14KB) +
`sse-starlette` 3.4.6 for push + uPlot 1.6.32 (vendored, 21KB gzip) for charts.**

Smallest structural change that actually solves the problem: it keeps the existing phone-tuned CSS
and the Python-returns-HTML model, and decomposes the one giant HTML string into ~70 addressable,
independently-refreshable fragments. Migration is **incremental** — panel by panel, dashboard fully
working throughout — unlike a framework move where the whole rendering model changes at once.

**Runner-up: NiceGUI 3.15.0** — the only Python-native framework that mechanically clears all four
gates (offline verified at byte level: 337 bundled JS + 10 CSS, zero absolute http URLs in
`index.html`; native `ui.run_with()` FastAPI sub-mount; Quasar mobile-first; company-backed). It
loses only on the operator's own tiebreaker: adopting it means re-expressing 70 panels in its
reactive component model and discarding CSS that already works. **The documented escape hatch if the
HTMX refactor starts feeling like a worse home-made framework.**

## REJECT table — every rejection with its evidence tier

| candidate | verdict | reason (hard fact vs judgement) |
|---|---|---|
| Streamlit 1.60.0 | REJECT | **hard** — deck.gl/pydeck/Plotly-map chunks hardcode `unpkg.com` (issue #12451); ASGI mount only ~6 months old; open mobile layout regression #8801 |
| Panel 1.9.3 | REJECT | **hard** — CDN is the pip-install *default*; offline widget breakage open (#7429, #7073); mobile layout issue open since 2021 (#2980) |
| Reflex 0.9.7 | REJECT | **hard** — compiles a Next.js frontend at build time; `reflex init` fails air-gapped (#4780). Owning a JS build pipeline breaks two gates at once |
| FastHTML 0.14.9 | REJECT | **hard** — wheel inspection: `pico.py`/`core.py` hardcode CDN assets; Alpha; open FastAPI-mount bug where `app.state` isn't shared (#687). *The right idea, not yet a safe implementation* — its SSE/WS primitives are worth studying |
| Gradio 6.20.0 | REJECT | **hard+judgement** — offline only fixed 2026-06-04 (PR #13463) with analytics/version-ping still default-on; maintainer on record that it "doesn't scale well as the number of elements increase" — fatal for 70 panels |
| Dash 4.4.1 | REJECT | **judgement** — mechanically fine (offline default, first-party FastAPI backend) but an 8.9MB React/webpack SPA is a heavy rewrite for uncertain gain; desktop-first widgets |
| Lit 3.3.3 | REJECT | **hard** — Lit's own docs discourage the single-file bundle path that "no build step" requires; assumes npm + bundler. Also doesn't reduce JS authoring, just reshapes it |
| Chart.js 4.5.1 | REJECT (charts) | **hard** — candlesticks need `chartjs-chart-financial`, last released 2024-03-23, not first-party |
| Observable Plot 0.6.17 | REJECT | **judgement** — exploratory grammar-of-graphics, wrong tool class for a persistent console; no pan/zoom/touch API |
| D3 7.9.0 | REJECT as primary | **judgement** — zero built-in chart types means perpetual hand-rolling, the exact pattern we are escaping. Best touch story though; keep as fallback |
| Apache ECharts 6.1.0 | INTEGRATE (runner-up) | offline `dist/echarts.js` documented; native candlestick; but 359KB gzip ≈ 17× uPlot |
| WebSockets | not chosen | **judgement** — our flow is one-directional; WS buys a bidirectional channel we don't need and requires hand-rolled reconnect |

## Why SSE over WebSockets (decision-grade)

Starlette does **not** natively frame `text/event-stream`; its own docs point to `sse-starlette`'s
`EventSourceResponse`. `EventSource` **auto-reconnects with zero client code** (server tunes via
`retry:`), whereas WebSocket has no built-in reconnect — we'd hand-write backoff on both ends.
`EventSource` is Baseline-widely-available (~96.7%, iOS Safari since v5), so no mobile risk. Our data
flow is server→browser snapshot push, so WS's bidirectionality buys nothing today. Revisit only for
true bidirectional needs (e.g. a live order-cancel channel).

## Stated weaknesses of this research (carried, not buried)

- **Mobile usability is the weakest-evidenced dimension** across every option — based on issue
  trackers and doc claims, not hands-on device testing. **Test uPlot's touch plugin and ECharts'
  touch behaviour on a real phone before committing.**
- Panel's release date had one conflicting fetch; discarded in favour of the internally-consistent
  chronology. Low stakes — the offline/mobile issues drive the verdict regardless.
- No performance/memory benchmarking was done for any option.

## Sequencing note (Rule K)

**This stack is NOT the next thing to build.** B10 — 22 of 37 feature stages frozen after one run per
day — blocks the operator's actual requirement that the system researches and learns between
sessions. A new dashboard over 22 frozen engines would render the freeze beautifully. B10 first.
