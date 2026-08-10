# Slice 4 — Per-leg option mark-to-market + real exit economics

The pod lifecycle marks positions on the UNDERLYING price (directional proxy; neutral option structures show
unrealised 0), so a short strangle / iron condor — the Θ engine — never shows its true P&L and never exits on
the spread's real value. Slice 4 marks each option structure on its REAL legs from the live chain and exits on
the real spread P&L.

## The engine
### A. Persist the structure legs on the open position
`PodOpenPosition` gains `legs` (right · strike · side · entry_price) + `lot_size`. On open,
`_record_opens` captures them from the synthesized `proposal.structure.legs` (real strikes + entry premiums
from slice 3). `entry_value` = Σ (sell premium − buy premium) × lot (net credit +, debit −).

### B. Option-leg re-pricer (injected, live-chain backed)
`OptionLegMarker` — given (underlying, legs), fetch each leg's CURRENT premium from the live chain (match on
right+strike) and compute the structure's current value = Σ (sell − buy) at current premiums × lot. The pod
builds it from the `MultiBrokerLiveOptionChainSource`; a missing chain → hold (no fabricated mark, Rule J).

### C. Mark + exit on the real spread P&L
For an option-structure position each cycle:
`unrealized = current_value − entry_value` (a short-premium structure gains as premium DECAYS → current value
of the short legs falls → positive P&L). Exit rules on the REAL P&L:
* **profit-take** — close at ≥ X% of max credit captured (Θ structures) / target debit-spread value;
* **defined-risk stop** — close if the loss hits the structure's max-loss fraction;
* **mandatory intraday square-off** at 15:15 IST (unchanged).
Directional single-leg / cash positions keep the exact underlying P&L path (unchanged). This replaces the
neutral-structure `unrealized = 0` with the true spread mark, and the dashboard LTP/P&L columns come alive.

## Why engine-grade
Real per-leg option pricing from live premiums, carried leg state, a real exit policy on the spread value
(profit-target / defined-risk / decay), and it changes the exit DECISION for every option structure. SOTA
analog: a position mark-to-market + exit engine in a real options book.

## Verification (Rule F, live)
Open a synthesized condor on the live chain; re-price its legs from the live chain a cycle later; confirm the
current value ≠ entry value (premiums moved), unrealized P&L has the right sign (short premium + as it decays),
and a profit-take/stop fires when thresholds hit. Hermetic (Rule J): a fake leg-marker returns known premiums
→ the P&L + exit are exact; degenerate/missing-leg inputs are safe.

## Sourcing (Rule I)
Bespoke intrinsic/premium bookkeeping (small, exact) over the live chain we already fetch; numpy for the math.
No external OSS — greeks-based marking (vollib) is a later refinement (queued). Logged.

## Backlog (Rule K)
- Greeks-based mid marking (vollib) + bid/ask spread modelling for fill realism.
- Per-structure profit-target / stop thresholds calibrated from the realised track record (slice-5 learning).
