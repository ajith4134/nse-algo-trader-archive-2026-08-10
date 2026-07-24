# 40 — Order Types: Kite Connect v3 Spec + Implementation Taxonomy (2026-07-24)

Verified against the live Kite docs (2026-07): orders, gtt, exceptions.
This is the implementation spec for extending Layer 6 (OMS) beyond
MARKET/LIMIT. Sources: kite.trade/docs/connect/v3/orders, /gtt,
/exceptions; Zerodha support (BO discontinued; GTT 365-day validity).

## Order types (order_type)
| order_type | price | trigger_price | meaning |
|---|---|---|---|
| MARKET | ignored | — | fill at market |
| LIMIT | **required** | — | fill at/better than price |
| SL (stop-limit) | **required** | **required** | on trigger → LIMIT at price |
| SL-M (stop-market) | ignored | **required** | on trigger → MARKET |

Trigger semantics: BUY stop → trigger ABOVE LTP (breakout entry); SELL stop
→ trigger BELOW LTP (protective stop). SL fires a LIMIT at `price`; SL-M
fires a MARKET.

## Variety (URL path segment `/orders/:variety`)
regular · amo (after-market) · co (Cover Order: entry + compulsory SL leg,
pass `trigger_price`) · iceberg (`iceberg_legs` 2–50) · auction.
**BO (Bracket Order) is DISCONTINUED (since 2020)** — do not implement;
emulate a bracket with a two-leg OCO GTT after entry fills.

## Product · Validity
product: MIS (intraday, our default — non-negotiable), CNC (delivery),
NRML (F&O carry), MTF. validity: DAY · IOC · TTL (needs `validity_ttl`
minutes). Other fields: disclosed_quantity, market_protection, tag (≤20).

## GTT (/gtt/triggers) — Good Till Triggered
- `type`: `single` (1 trigger → 1 order) or `two-leg` = **OCO** (2 triggers
  [SL, target], 2 orders; first hit fires + cancels the other).
- `condition`: {exchange, tradingsymbol, trigger_values:[…], last_price}.
  OCO: lower (SL) value FIRST, higher (target) second.
- `orders`: index-aligned to trigger_values; **GTT orders are LIMIT-only**
  (mandatory price).
- Lifespan: **365 days**, auto-cancel if untriggered; deactivates once
  fired. Per-user cap ~500 active (equity) — enforce defensively.
- SL+target on a long position = two-leg OCO: orders[0]=SELL LIMIT ~SL,
  orders[1]=SELL LIMIT target.

## Rate limits (per API key unless noted)
Order placement **10 req/s**, **400/min**, ~2000/day per product-class
(per client-id). Quote 1/s, historical 3/s, others 10/s. (SEBI white-box
cap <10 orders/sec is already enforced by `order_rate_limiter`.)

## Recommended taxonomy (broker-agnostic intent → Kite adapter)
Extend `broker_oms/order_types.py`:
```
OrderKind:  MARKET | LIMIT | STOP_LIMIT("SL") | STOP_MARKET("SL-M")
ProductType: INTRADAY("MIS") | DELIVERY("CNC") | CARRY("NRML") | MTF
TimeInForce: DAY | IOC | TTL(+validity_ttl_minutes)
OrderVariety: REGULAR | AFTER_MARKET | COVER | ICEBERG | AUCTION
```
`OrderIntent` gains: order_kind, product, variety, time_in_force,
limit_price, trigger_price, disclosed_quantity, validity_ttl_minutes,
iceberg_legs/quantity, client_tag. `.validate()` enforces the
price/trigger matrix above. New `OcoGttIntent` (exchange, tradingsymbol,
last_price, stoploss_trigger, target_trigger, stoploss_order,
target_order).

Kite-only fields (market_protection, auction_number, GTT last_price) stay
in the adapter, never in strategy code (broker-abstraction rule).

## SimulatedBrokerClient must emulate (for paper — Rule F)
1. LIMIT fill: BUY when LTP ≤ price, SELL when LTP ≥ price.
2. SL/SL-M: hold pending-trigger; each tick compare LTP to trigger
   (BUY ≥ trigger, SELL ≤ trigger) → convert to LIMIT/MARKET, then fill
   (MARKET gets slippage).
3. CO: entry fill + auto child SL leg at trigger.
4. GTT single + two-leg OCO: per-tick evaluator; OCO fires the crossed
   leg, cancels the other; enforce 365-day expiry + max-active cap.
5. Validity: DAY→expire at close, IOC→fill-or-cancel now, TTL→cancel after
   N minutes.
6. Async: return order_id immediately; emit OPEN→TRIGGER_PENDING→
   COMPLETE/CANCELLED/REJECTED via the same status path as live.

## How this plugs into the live loop
The ORB/spread exits (stop_loss_price / target_price) become **real SL-M
(or SL) orders** instead of the current synthetic "if LTP crosses, book at
that price." A two-leg OCO GTT expresses stop+target atomically. This makes
the paper exits path-identical to the live exits (parity, PLAN §1).

## Rule-F items to confirm on a live key before sign-off
- CO placement required fields (docs detail CO *modify* only).
- Programmatic per-user GTT ceiling (read the rejection).
- iceberg_quantity vs quantity/iceberg_legs arithmetic on a real symbol.

## Build order (when picked up)
1. Extend enums + `OrderIntent` + `.validate()` (+ tests). 
2. SimulatedBrokerClient SL/SL-M trigger emulation (+ tests).
3. Kite adapter: map to `/orders/:variety` + `place_gtt`/`OcoGttIntent`.
4. Wire ORB/spread stop+target to SL-M / OCO-GTT in the live loop.
5. GTT/CO/iceberg + validity as follow-on slices.
