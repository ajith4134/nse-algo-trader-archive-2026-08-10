# 40 — Order Types for the NSE Intraday Bot (Kite Connect v3) — Research

Research pass before implementing order types (operator: "first do research
on all the order types before implementing them"). Verified against the
**primary** Kite Connect v3 docs (kite.trade/docs/connect/v3) + Zerodha
support/bulletins, cross-checked with practitioner sources. As of 2026-07.

## Bottom line (the decision)
This bot is **intraday-only, NSE cash + options, white-box personal algo.**
The order types it should implement, mapped to Kite primitives:

| Bot need | Kite mapping | Notes |
|---|---|---|
| **Entry** | `LIMIT` (default) or `MARKET`+`market_protection` | Options are often illiquid → LIMIT strongly preferred; MARKET on illiquid stock options is RMS-blocked ("place around theoretical price"). |
| **Stop-loss exit — cash/futures** | `SL-M` (trigger_price only) | Clean market-on-trigger. |
| **Stop-loss exit — OPTIONS** | `SL` (stop-loss-**limit**) with a protective limit beyond the trigger (BUY: price>trigger; SELL: price<trigger) | **Critical gotcha: SL-M is BLOCKED for options** (NSE since 2021-09-27, index options too). Mimic SL-M with a wide SL-limit. |
| **Target exit** | `LIMIT` | Resting profit order. |
| **Bracket (SL + target together)** | **Build OCO in-engine** | Zerodha BO is **discontinued**; GTT-OCO is CNC-only (not intraday). The engine must place both and cancel the other on fill. |
| **Forced square-off 15:15** | `MARKET` (cash/fut) / aggressive `LIMIT` or `SL`→market-like (options) | Guarantee flat; Layer 8 already drives this. |
| **Large F&O (> freeze qty)** | `autoslice=true` or `iceberg` | NIFTY options freeze = 1,800 qty; iceberg max 10 legs; each leg = separate order (rate + brokerage). |
| **CO / BO / GTT** | **Do NOT use** | See below — none fit an intraday options bot. |

**Net: implement four `order_type`s (MARKET, LIMIT, SL, SL-M) + an
engine-level OCO bracket + an autoslice/iceberg flag. Skip CO, BO, GTT.**

## 1. Kite order primitives (primary docs)
- **variety**: `regular`, `amo` (after-market), `co` (cover order),
  `iceberg`, `auction`.
- **order_type**: `MARKET` (opt. `market_protection`), `LIMIT` (needs
  `price`), `SL` (stop-loss-limit — needs `price` + `trigger_price`),
  `SL-M` (stop-loss-market — needs `trigger_price`).
- **product**: `CNC` (equity delivery), `NRML` (F&O overnight), `MIS`
  (intraday auto-squareoff), `MTF`. **This bot = MIS always** (intraday
  non-negotiable).
- **validity**: `DAY`, `IOC` (immediate-or-cancel), `TTL` (life in minutes
  via `validity_ttl`).
- **key params**: `tradingsymbol, exchange, transaction_type, order_type,
  quantity, product, price, trigger_price, validity, validity_ttl,
  disclosed_quantity, iceberg_legs (2–50), iceberg_quantity,
  market_protection (>0..100 custom %, or -1 auto), tag (≤20 chars),
  autoslice (bool), auction_number`.
- **status flow**: `VALIDATION PENDING → OPEN PENDING → OPEN → COMPLETE`,
  or `REJECTED / CANCELLED / TRIGGER PENDING`. Partial fills via
  `filled_quantity / pending_quantity / cancelled_quantity`;
  `average_price` only on COMPLETE.

## 2. Stop-loss depth + the options gotcha
- **SL** (stop-loss-limit): `trigger_price` arms it; when the LTP crosses,
  a `LIMIT` order at `price` is placed. Risk: in a fast move price can gap
  past the limit → **no fill** (stop doesn't execute).
- **SL-M** (stop-loss-market): `trigger_price` only; fires a MARKET order →
  guaranteed fill, uncertain price.
- **SL-M is DISABLED for options** (NSE 2021-09-27; index options
  explicitly blocked; BSE discontinued SL-M 2023-10) to curb freak trades.
  → For option stops, use **SL-limit with a protective buffer**: set the
  limit far enough beyond the trigger that it fills like a market order
  (Zerodha's own recommended workaround). The bot must compute this buffer
  from the option's tick size / spread.
- **Trailing stop-loss: NOT offered by Zerodha** (died with BO). Any
  trailing must be **engine-side** (re-modify the SL trigger each bar).

## 3. GTT (Good Till Triggered)
- `trigger_type`: `single` (1 trigger_value, 1 order) or `two-leg`/**OCO**
  (2 trigger_values, exactly 2 orders — SL + target, one cancels other).
- Condition: `{exchange, tradingsymbol, trigger_values[], last_price}`;
  orders: `{transaction_type, quantity, order_type: LIMIT, product, price}`.
- **Lasts up to 365 days; product is CNC/NRML — NOT MIS/intraday.** A GTT
  only *watches*; on trigger it places a **fresh** order (no margin blocked
  until then). **Unsuitable for an intraday-only bot's live positions** —
  but its OCO *semantics* (SL+target, one cancels other) are exactly what
  the bot replicates in-engine.

## 4. Cover Order (CO) & Bracket Order (BO)
- **BO: discontinued** by Zerodha (both target+SL could trigger together in
  volatility, leaving unintended positions). Do not use.
- **CO: still live, but NSE cash-equity intraday ONLY — not BSE, not F&O.**
  Market/limit entry + mandatory SL (trigger within a 10% range). Because
  it excludes options and gives no target leg, it's a poor fit here → skip
  in favor of engine-level OCO on raw primitives.

## 5. Iceberg / freeze quantity
- Exchanges cap single-order size (freeze qty): **NIFTY options freeze =
  1,800**; check NSE "Volume Freeze Quantity" per contract.
- **Iceberg** slices a big order into ≤10 legs, each sent after the prior
  fills. **`autoslice=true`** auto-splits above freeze limits (≤10 slices;
  response is an array, some legs may error). Each leg = a separate order →
  counts against the order-rate limit and brokerage.

## 6. Modification / cancellation / partial fills
- Modify (regular): `order_type, quantity, price, trigger_price,
  disclosed_quantity, validity`. CO child: `price, trigger_price` via
  `parent_order_id`. Cancel: DELETE on OPEN/pending orders.
- The engine must reconcile **partial fills** (poll `filled_quantity`;
  our current `KiteBrokerClient` returns OPEN on acceptance and does NOT
  yet poll — a known gap, audit research/39 [L6]).

## 7. SEBI / rate constraints (choosing order types)
- SEBI Feb-2025 retail-algo framework (mandatory 2026-04): broker=principal,
  bot=agent, every order carries the exchange **Algo-ID**, **< 10 orders/
  sec/exchange/client** (already enforced by `order_rate_limiter`). Iceberg/
  autoslice multiply order count → watch the rate budget.

## Sources (primary A / secondary B)
- A: kite.trade/docs/connect/v3/orders/ ; .../gtt/ (official API).
- A: zerodha.com/marketintel bulletin — SL-M blocked for index options.
- B: Zerodha support — cover orders (cash-only, 10% SL range); "use SL like
  SL-M"; iceberg orders; BO discontinued FAQ.
- B: chittorgarh — GTT (CNC-only, 365-day), order-types overview;
  business-standard — BSE SL-M discontinuation 2023-10.

## What this changes in the code (design, to implement next)
1. Extend `broker_oms/order_types.py` `OrderType`: add `STOP_LOSS_LIMIT`
   (SL) and `STOP_LOSS_MARKET` (SL-M); keep MARKET, LIMIT. Add
   `trigger_price` + optional `limit_price` already present.
2. `KiteBrokerClient`: map SL/SL-M → Kite `order_type` + `trigger_price`;
   **guard: for option instruments never emit SL-M — auto-convert to a
   buffered SL-limit** (the gotcha), and log it.
3. Add an **engine-level OCO bracket** helper (Layer 6/7): entry fill →
   place resting SL (options: buffered SL-limit) + target LIMIT → on either
   fill, cancel the other. This replaces BO/CO/GTT which don't fit.
4. Add `autoslice`/iceberg support for F&O qty over freeze limits.
5. Partial-fill polling (`fetch_order_result`) to close the L6 gap.
6. Paper/simulated broker must model SL/SL-M trigger semantics + the
   options SL-M→SL-limit conversion so paper matches live.
