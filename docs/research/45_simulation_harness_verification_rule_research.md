# 45 — Simulation-Harness Verification When Real Data Is Unavailable (Rule J research)

Research + design for a new project rule (operator-proposed 2026-07-24): when a
feature's real production data is not reachable (market closed, no live session,
a source not yet ingested), do not leave it unverified — build a hermetic
simulation/injection harness that verifies every function on the exact data
shape it consumes, with the injected data structurally unable to leak into
production. Verified against established practice before codifying (Rule J
checked by demonstration, below).

## What the practice is called (verified online, 2026)
The operator's idea maps 1:1 onto established software-engineering practice:
- **Hermetic testing** (Google): an isolated environment with NO external
  dependencies; in-memory fakes/stubs replace external components so a test
  fails ONLY on a real code bug, never on an unavailable service. (abseil SWE
  book ch.13 "Test Doubles"; Google CCIW 2023 hermetic/ephemeral SUTs.)
- **Test seam + dependency injection**: dependencies are PASSED IN, not
  instantiated inside — so a test can substitute a test double. This is the
  seam that keeps the fake out of prod.
- **In-memory fake > mock**: a faithful working implementation of the same
  interface (deterministic time provider, in-memory store) beats an ad-hoc
  mock — it verifies behavior, not just calls.
- **Contract test**: the fake and the real adapter implement the SAME protocol;
  a contract test proves the fake is faithful to what the real thing delivers.
- **Test harness / drivers + stubs**: simulate the unavailable module and plug
  in responses matching what the real component will eventually deliver.
- **Isolation = abstract behind an interface + DI**: production selects the
  real adapter; the fake is never wired into the live path.

## How it already appears in THIS project (the pattern is proven here)
- `run_live_universe_scan_pass(state, cash_universe, live_universe_feed, ...)` —
  the feed is an INJECTED parameter (DI seam). Tests pass `_FakeFeed`; prod
  passes `KiteLiveUniverseFeed`.
- `BrokerClient` protocol → `SimulatedBrokerClient` (fake) vs `KiteBrokerClient`
  (real) — same interface, contract-parity tested.
- `ReplayUniverseFeed` — a replay/simulation source with the same interface as
  the live feed (the market-closed half of the router).
- `_FakeKiteClient` in tests — a faithful in-memory Kite stub.
These are exactly hermetic fakes behind DI seams; Rule J formalizes the
discipline + the isolation guarantee + the "does not replace Rule F" guardrail.

## Rule J — verified by demonstration (2026-07-24, before codifying)
Scenario check: the rule targets "real live data unavailable." Demonstration ran
the FULL live-loop verification through the injected `_FakeFeed` seam WITHOUT any
live data — **10 tests pass** (seed → ORB detect → risk gate → open → manage →
15:15 Layer-8 square-off), i.e. every function's input/data-flow/output verified
on injected synthetic bars. **Hermetic-isolation check:** `_FakeFeed` occurs in
**0 `src/` files** and only in `tests/` — production instantiates the REAL
`KiteLiveUniverseFeed`; the fake is structurally unable to reach the live path.
→ The rule's workflow works as claimed; safe to add.

## The rule (as added to CLAUDE.md — Rule J)
When real production data is unreachable, verify the feature with a hermetic
simulation harness: inject the exact data SHAPE (trimmed REAL samples preferred)
through the same swappable interface the real source uses; verify input
contracts, internal file→file flow, output contracts, and error paths. The fake
MUST sit behind the DI seam so production selects the real adapter and the fake
never runs in prod (a fake that can leak into the live path is a bug to fix
first). **This verifies FUNCTIONAL correctness only — it does NOT satisfy Rule
F's real-data sign-off, which stays an OPEN BLOCKER until performed on the actual
production data.** Never present a sim-verified feature as fully done; label it
"functionally verified (sim); real-data pass pending (blocker)."

Pairs with Rule F (sim never substitutes for real-data sign-off), Rule G (the
harness exercises the real interface/wiring, not a parallel toy), Rule A (verify
before advancing), Rule I (if even the data shape is unknown, go acquire a real
sample first).
