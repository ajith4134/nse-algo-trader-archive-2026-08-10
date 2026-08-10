# 168 — L3 ops floor: crash-safety trio (idempotent order IDs + order-intent WAL + broker-truth reconciler)

**Date:** 2026-08-03 · **Redesign layer:** L3 (build order #4) · **Skill:** building-engine-grade-features
**North-star (redesign §3 L3):** *"Pre-trade risk gate (salvage) hardened · idempotent order IDs ·
order-intent WAL · state reconciliation from broker truth on restart · rate-limit budgeter · kill switch.
Nothing lives before this."*

## 1. Read-first — what exists
- **Rate limiter:** `broker_oms/order_rate_limiter.py` ✅ (SEBI ≤10 orders/sec). REUSE.
- **Kill switch:** `conscience/…corrigibility` off-switch ✅ (blocks every order when engaged). REUSE.
- **Pre-trade risk gate:** `risk_management/pre_trade_risk_gate.py` ✅ (+ the new L1 cost gate). REUSE.
- **Order path:** `broker_oms/order_types.py::OrderIntent` (frozen; NO client id) → `broker_client_protocol.place_order(intent) -> OrderExecutionResult(broker_order_id, filled_quantity, …)`; Kite has NO native idempotency key.

## 2. The gap (crash-safety trio — `reconcil:0`, `write_ahead:0`, `client_order:0`)
A crash/restart mid-session today can (a) double-place an order on retry, (b) lose the record of an
in-flight intent, and (c) leave the bot blind to what is ACTUALLY open at the broker. This is the
"nothing lives before this" layer — required before any live capital.

## 3. Three engine parts (parallel opus agents; I integrate)
- **A. `broker_oms/idempotent_order_identity.py`** — `deterministic_client_order_id(intent, session_key)`:
  a stable, collision-resistant id from the intent's identifying fields (instrument, side, quantity,
  strategy_tag, prices, order_type) + a session/day key, so the SAME logical intent always yields the SAME
  id (a retry can be recognized + deduped). Kite-tag-safe (≤ the broker tag length; documented).
- **B. `broker_oms/order_intent_write_ahead_log.py`** — a SQLite WAL of order intents: `record_pending`
  BEFORE the broker call; `mark_placed(broker_order_id)` / `mark_filled` / `mark_rejected` after;
  `state_of(client_order_id)` (idempotency probe) + `pending_intents()` (unacked, for restart replay).
  Carried, persistent state; never loses an in-flight intent across a crash.
- **C. `broker_oms/broker_state_reconciler.py`** — `reconcile(local_positions, broker_positions,
  wal_pending) -> ReconciliationReport`: the diff of the bot's belief vs BROKER TRUTH — orphan-local
  (bot thinks open, broker flat), unknown-broker (broker open, bot unaware), quantity mismatches, and
  unresolved WAL intents — plus a corrective action plan (adopt / flatten / alert).

## 4. Integration (mine — Rule G)
A `CrashSafeOrderPlacer` wraps the broker: compute the client id → probe the WAL (skip if already
placed/filled — idempotency) → `record_pending` → `place_order` → mark the result. On service startup,
run the reconciler against broker truth (live only) + replay `pending_intents()`. Dashboard surface
(Rule N): WAL pending/placed/filled counts + last reconciliation report. All behind the existing broker
seam so PAPER is unaffected.

## 5. Verification
Unit + property + adversarial (double-record same id → one WAL row; crash between record_pending and place
→ intent surfaces in pending_intents; reconciler finds every diff class) + Rule-J hermetic through the
broker protocol with a fake. **Rule-F is LIVE-gated** (no live broker session today — paper only): the
real reconciliation-against-broker-truth + real duplicate-suppression pass is the ONE permissible open
blocker (Rule K), logged; the engines ship complete + hermetically verified.

## 6. Sourcing (Rule O.1) — executed per-part by the agents
Each agent runs `sourcing-oss-parts` (idempotency-key libs, write-ahead-log / event-sourcing libs, broker
reconciliation patterns). Expected: bespoke on the repo's SQLite pattern (idempotency + a domain WAL are a
few functions; event-sourcing frameworks are wrong-shape for one embedded file) — agents record queries +
tier-labelled rejects.
