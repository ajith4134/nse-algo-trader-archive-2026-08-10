# VII — ethics/law reasoner  ·  research/119

**Trunk VII CONSCIENCE, branch: ethics/law reasoning.** Design doc (Rule D).

## The idea
A machine conscience must be able to REASON about the law it operates under, not just obey hard-
coded invariants. The bot runs under SEBI's Feb-2025 "Safer Participation of Retail Investors in
Algorithmic Trading" framework (mandatory Apr-1-2026). The ethics/law reasoner is an explicit
compliance-officer organ: it holds the SEBI algo rulebook as DATA (each rule + its citation),
reasons the system's current regulatory posture against every rule, and produces a cited compliance
report — surfacing exactly which rule would be breached and why, holistically.

## Distinct from the constitution (VII.1) — not a duplicate
The constitution is a set of INVIOLABLE structural articles enforced at order time (the Referee
blocks a violating order). The ethics/law reasoner is the REASONING layer above it: it assesses the
regulatory POSTURE with citations (like a compliance review), reasoning about the rulebook as such —
order-rate ceiling, broker-principal routing, Algo-ID carriage, intraday-only, and the white-box /
personal-use boundary that keeps the project out of SEBI Research-Analyst-registration territory.
It explains and cites; the constitution enforces.

## The SEBI rulebook (encoded as data — from CLAUDE.md regulatory constraints + research)
1. **ORDER_RATE** — < 10 orders/sec/exchange/client, else it crosses into mandatory-registration
   (white-box) territory (our throttle ceiling is 5).
2. **BROKER_PRINCIPAL** — the broker is principal, the bot is agent; every order routes THROUGH the
   broker API, never direct-to-exchange.
3. **ALGO_ID** — every order carries the exchange-assigned Algo-ID.
4. **INTRADAY_ONLY** — no overnight carry in any segment (also constitutional; cited here as law).
5. **WHITE_BOX_PERSONAL** — personal/white-box use only; offering strategies/signals to other people
   changes the regulatory category (SEBI Research-Analyst registration).

## Component parts (`conscience/ethics_law_reasoner.py`, pure)
- **`RegulatoryRule`** (frozen) — `rule_id`, `title`, `citation`.
- **`SEBI_ALGO_RULEBOOK`** — the tuple of rules above.
- **`RegulatoryPosture`** (frozen) — `max_orders_per_second`, `routes_through_broker`,
  `carries_algo_id`, `intraday_only`, `offered_to_others`, `trading_mode`.
- **`LawFinding`** (frozen) — `rule_id`, `title`, `compliant`, `severity`, `reason`, `citation`.
- **`LawComplianceReport`** (frozen) — `findings`, `compliant`, `violations`, `summary`.
- **`assess_regulatory_compliance(posture)`** — reasons each rule against the posture.

## Wiring (Rule G/N — wired-into-decisions)
Daily `_maybe_run_ethics_law_review` builds the real posture (order-rate ceiling 5 from the SEBI
throttle; broker-routed / Algo-ID / intraday-only structural; personal-use; live mode from config),
runs the reasoner, caches the report. A HARD regulatory VIOLATION engages the off-switch + records a
forensic incident (law-breaking is halt-worthy). Dashboard surface `ethics_law_reasoner`. Rule N.

## Verification
- **Hermetic (Rule J):** a compliant posture → compliant report; order-rate ≥10 → violation; direct-
  to-exchange / offered-to-others → violation with the right citation.
- **Real-data (Rule F):** build the posture from the real config + real throttle ceiling; the live
  posture is COMPLIANT (rate 5<10, broker-routed, Algo-ID, intraday, personal) — an honest
  cited all-clear.

## Atlas impact
ethics/law reasoning 🔴→🟢. VII CONSCIENCE 11🟢→12🟢 (LAST 🔴 cleared). Overall 38→39 / 197 (19.8%).
