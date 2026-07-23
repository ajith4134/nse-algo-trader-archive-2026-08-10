# Project: NSE Autonomous Algo Trading Bot

## What this is
An autonomous, intraday-only trading system for Indian markets. Positions are
always squared off before market close — no overnight carry, ever, in any
segment.

**Phase 1 scope (active now):** NSE cash equity intraday + NSE options
intraday (index options: NIFTY, NIFTYNXT50, FINNIFTY, MIDCPNIFTY, BANKNIFTY;
plus NSE single-stock options, ~185-208 names, list reviewed quarterly).

**Deferred to a later phase (do not build yet):** NSE/BSE futures, commodity
derivatives, BSE index options (SENSEX, BANKEX).

**Stack decisions already made:** Python (broker SDK + ML ecosystem fit).
Broker (execution): Zerodha Kite Connect (chosen for phase 1; broker-
integration layer must stay swappable — do not hardcode Kite specifics
outside the broker integration layer). Data sourcing (Layer 2): **not
Kite-only** — Upstox, Angel One, ICICI Direct, and Groww APIs are also
planned as interchangeable data sources (decided `docs/PLAN.md` §8a.12);
the data-ingestion layer must treat every broker's data API as swappable
the same way the execution layer treats brokers as swappable.

## Regulatory constraints (binding, not optional)
- Runs under SEBI's Feb 2025 "Safer Participation of Retail Investors in
  Algorithmic Trading" framework (fully mandatory as of Apr 1, 2026).
- Broker is "principal," this bot is "agent" — all orders route through the
  broker's API, never direct-to-exchange.
- This is a **white-box** algo (personal use only, not distributed to other
  users). Must stay under 10 orders/sec/exchange/client, or it crosses into
  mandatory-registration territory.
- Every order must carry the exchange-assigned Algo-ID once wired up in the
  execution layer.
- If this bot is ever offered to other people, that changes the regulatory
  category entirely (SEBI Research Analyst registration) — flag loudly before
  building anything that shares strategies/signals with another account.

## Rule A — Layer-by-layer build, verify before advancing
Build one feature/layer at a time, in dependency order (see
`docs/flowcharts/00_project_overview.md` for the layer roadmap). After
building a feature:
1. Verify it (tests + a manual check against real/sample data).
2. Explicitly confirm — out loud, in conversation — that nothing more is
   needed on this feature.
3. Only then move to the next layer. Do not start the next layer's code
   while the current one is still open.

## Rule B — Living flow-chart notes (update after every feature)
After every feature is completed, update the running notes in
`docs/flowcharts/`, written like cumulative class notes:
- A data-flow diagram from the very start of the pipeline through the new
  feature (not just the new feature in isolation).
- For the new feature specifically: every function name, every import, the
  exact type/shape of data it exports, and the full list of files that
  belong to it.
- Never delete old notes — they accumulate. One file per layer/feature,
  cross-linked from `00_project_overview.md`.

## Rule C — Self-describing names
Every file, module, function, class, and variable name must reveal its role
by name alone — if you only read the name, you should know what it does.
No generic `utils.py` / `helper()` / `data` / `manager` unless qualified with
what it actually does. Applies to edits of existing code too, not just new
code.

## Rule D — Research, planning, and important discussions get saved to files, every time, without fail
Any non-trivial research pass, planning/architecture discussion, or decision
made in conversation must be written to a file under `docs/research/` (or
`docs/flowcharts/` if it's about an already-built feature's data flow)
before the turn is considered done — never left to live only in chat
history. This includes: research findings and sources, candidate plans and
their ranking/recommendation, and the reasoning behind any non-obvious
decision. Update the relevant index file (`docs/flowcharts/00_project_overview.md`
or a new `docs/research/` index) to point to it so it's discoverable later.

## Rule E — License is not a filter when researching borrowable code
This project is for individual/personal use only and will not be
distributed, sold, hosted as a service, or open-sourced. When researching
or recommending existing open-source projects/code to borrow features
from, evaluate on technical merit only — never exclude or downrank a
project because of its license (GPL/AGPL/no-license-asserted/proprietary).
Copyleft source-disclosure obligations trigger on distribution or
offering a network service to others, not on private personal use. If
this project's status ever changes (offered to others, hosted, distributed
— which already changes the regulatory category per the constraints
below), revisit every borrowed piece's license at that point, not before.

## Rule F — Real-data verification gate (every feature, every branch)
No feature, layer, or branch — including all 16 trunks and ~200 AI
branches (research/32-36) — is considered done until it has been
verified against the **real data it will operate on in production**, not
fake/synthetic data.
- Synthetic fixtures may scaffold deterministic unit tests, but they
  NEVER substitute for the real-data verification pass, which is the
  actual sign-off. (Prefer fixtures that are trimmed *real* samples over
  invented ones.)
- "Real data" = the actual source the feature consumes in production:
  live/replayed NSE market data, real Kite API responses, the real NSE
  official reports, and — for AI/learning/paper features — the real
  paper/replay/live stream they learn from. A feature is tested on the
  same data it will run on.
- If the real data is not reachable yet (e.g. live ticks need an open
  market session), that is recorded as an explicit blocker against the
  feature — never a reason to sign off on fake data instead.
- This pairs with Rule A's "verify before advancing": Rule A requires
  tests + a manual check; Rule F fixes that the manual check must be
  against production-real data, for everything, including AI branches.

## Non-negotiables carried through every layer
- Intraday only. Every position auto-squares-off before close. No exceptions
  per-segment, ever, unless a future phase explicitly revisits this.
- Never commit API keys/secrets — `.env` is gitignored; broker credentials
  are loaded from environment/secret store only.
