# 06 — Broker Integration & OMS (Layer 6)

**Status:** v1 built; parity + atomicity tests green; live READ path
verified (no real orders placed — none will be until Layers 7/8 exist
and the PLAN §5 gates pass). Awaiting user sign-off.

## Whole-pipeline data flow so far

```
[L1 Universe] -> [L2 Data] -> [L3 Indicators] -> [L4 Signals] -> [L5 Risk gate]
                                                                     |
                                                   approved decision |
                                                                     v
[Layer 6: broker_oms/]
   signal_to_order_intents
     build_order_intent_for_opening_range_breakout(signal, approved_qty)
     build_order_intents_for_credit_spread(signal, approved_lots)
       -> lots x lot_size shares; hedge BUY first, short SELL second
                    |
                    v
   atomic_multi_leg_executor
     execute_multi_leg_order_atomically(legs, broker_client)
       -> MultiLegExecutionReport
       guarantees: BUY legs before SELL legs (never naked, not for one
       tick); any leg failure -> already-executed legs unwound with
       opposite market orders, reported, never silent
                    |
                    v
   BrokerClient (Protocol)          <- THE paper/live parity boundary
     place_order / fetch_order_result / cancel_order
     ├─ SimulatedBrokerClient  (paper: fills at last known price,
     │    position tracking, fill_price_adjuster hook reserved for
     │    Layer 7's options slippage model)
     └─ KiteBrokerClient       (live: kite.place_order, MIS product,
          variety=regular, tag<=20 chars, exchange NSE/NFO from segment;
          OrderRateLimiter INSIDE the client — no unthrottled path)
```

## Files belonging to this layer

```
src/nse_algo_trader/broker_oms/
├── __init__.py                     # public surface re-exports
├── order_types.py                  # OrderIntent / OrderExecutionResult / enums
├── broker_client_protocol.py       # BrokerClient Protocol
├── simulated_broker_client.py      # paper implementation
├── kite_broker_client.py           # live implementation + param mapping
├── order_rate_limiter.py           # SEBI ceiling self-throttle (5/sec)
├── atomic_multi_leg_executor.py    # spread-as-one-unit guarantee
└── signal_to_order_intents.py      # L4/L5 -> OrderIntents bridge

tests/test_broker_oms/              # 16 tests
├── broker_oms_test_fixtures.py
├── test_order_types_and_intent_building.py
└── test_broker_clients_and_atomic_execution.py
```

## Key decisions encoded here
- **Kite has no atomic multi-leg basket in its trading API** (research/07
  §D's "needs verification" flag now resolved: baskets are a Kite-web
  feature) — atomicity is therefore OUR executor's job: sequential
  placement, hedge-first ordering, unwind-on-failure.
- **Product is always MIS** (intraday) — the no-overnight non-negotiable
  enforced at the order-mapping level, not left to callers.
- **Rate throttle inside KiteBrokerClient** — 5 orders/sec default, half
  of SEBI's 10/sec registration threshold; injectable clock for tests.
- **Kite exceptions become REJECTED results**, feeding the same unwind
  path as any rejection — no exception-shaped escape hatch from
  atomicity.

## How it was verified (2026-07-23)
- 16 tests (148 suite, green) including both PLAN §5 mandates:
  - **Parity test**: identical credit-spread intent sequence executed
    against SimulatedBrokerClient and mocked KiteBrokerClient produces
    identical (symbol, side, quantity) order sequences.
  - **One-leg-failure test**: hedge fills, short leg rejected -> hedge
    unwound, zero net position remains, failure fully reported.
  - Plus: hedge-first reordering of adversarially reversed leg input,
    Kite param mapping (NFO/MIS/tag truncation), rate-limiter window
    behavior, unknown-price rejection (no invented fills).
- **Live read-only check** with the day's auto-generated token:
  kite.margins() / orders() / positions() all OK. Account cash Rs.0
  (live balance -Rs.88) — fine for paper; must be funded before any
  future live order.

## Known limitations / explicitly deferred
- Realistic options fill/slippage model -> Layer 7 (hook reserved).
- Partial-fill monitoring loop (OPEN -> poll -> COMPLETE/timeout) —
  arrives with Layer 7/8's live loop; v1 reports Kite orders as OPEN.
- Broker margin API (order_margins/basket) for true SPAN numbers —
  wire when Layer 7 sizes real paper trades; Layer 5 estimates stand in.
- Exchange Algo-ID tagging — requires the broker's algo registration
  workflow; must be resolved before ANY live order (regulatory).

## Order types extension (added 2026-07-24, research/40)
Extended the OMS order model beyond MARKET/LIMIT to the full Kite v3 set:
- `OrderType`: + STOP_LIMIT (SL), STOP_MARKET (SL-M). New enums
  `ProductType` (MIS default — intraday-only), `TimeInForce` (DAY/IOC/TTL),
  `OrderVariety` (regular/amo/co/iceberg/auction; BO discontinued).
- `OrderIntent` gains trigger_price, product, variety, time_in_force,
  validity_ttl_minutes, disclosed_quantity, iceberg_legs; `__post_init__`
  enforces the price/trigger matrix (SL needs limit+trigger, SL-M needs
  trigger, TTL needs minutes, iceberg needs 2..50 legs, CO needs trigger).
- `SimulatedBrokerClient`: SL/SL-M held TRIGGER_PENDING until the live price
  crosses the trigger (BUY≥trigger, SELL≤trigger), then fills — SL at
  limit, SL-M at market (via the slippage adjuster). Evaluated on every
  `update_market_price`. New `OrderLifecycleState.TRIGGER_PENDING`.
- `KiteBrokerClient`: maps order_type/price/trigger_price/validity/variety
  onto `kite.place_order` (product stays MIS).
- 7 tests (`test_order_types_and_stop_orders.py`); 270 suite green.

**Queued follow-ons (research/40):** wire the loop's ORB/spread stop+target
to real SL-M / two-leg OCO-GTT orders (paper/live exit parity); GTT
create/OCO, Cover Order, iceberg placement; validity DAY/IOC/TTL emulation
in the sim broker.
