# VII — security/adversarial defense (🟡→🟢 upgrade)  ·  research/121

**Trunk VII CONSCIENCE, branch: security/adversarial defense.** Design doc (Rule D).

## The idea & the upgrade
An autonomous system's INPUTS are an attack surface (adversarial ML / data poisoning). For a trading
bot the surface is the market-data feed: a spoofed or corrupt bar — an impossible price jump, a
zero/negative price, a crossed candle (high<low), a stale/duplicate timestamp — can trigger a false
signal and a bad trade. Today this branch is 🟡 (the adversarially-TESTED `pre_trade_risk_gate` is a
narrow echo). The upgrade to 🟢 is a real **market-data integrity / adversarial-input defense**: an
input-integrity screen that validates the bars a decision is built from BEFORE they feed the
strategy, and refuses to trade on corrupted data.

## Distinct from the causal-leakage firewall (II SENSES)
The leakage firewall stops FUTURE data leaking into a replay decision (temporal integrity). This
defends against ADVERSARIAL/CORRUPT data (value integrity) — a different threat: bad values, not
bad timing. Complementary.

## Component parts (`conscience/market_data_integrity_defense.py`, pure)
- **`IntegrityLimits`** (frozen) — `max_single_bar_move_fraction` (a >X% one-bar move is suspicious),
  `min_price` (>0).
- **`BarIntegrityVerdict`** / **`SeriesIntegrityVerdict`** (frozen) — `clean`, `anomalies` (names),
  `reason` / `anomaly_count`, `worst`.
- **`screen_bar(bar, previous_close)`** — checks price positivity, OHLC consistency
  (low ≤ open,close ≤ high; high ≥ low), and an impossible move vs the previous close.
- **`screen_bar_series(bars)`** — screens each bar + detects duplicate / non-monotonic timestamps
  (stale/replayed ticks); returns the aggregate verdict.

## Wiring (Rule G/N — wired-into-decisions)
`LiveUniversePaperState.market_data_integrity_permits_signal(session_bars)` — screens the exact bars
a cash ORB signal is built from; on corruption it BLOCKS the signal (no trade on adversarial data)
and counts anomalies. Wired in `_seed_cash_instrument_from_orb` before `detect_opening_range_breakout`.
Dashboard surface `market_data_integrity` (series screened, anomalies detected, blocks). Rule N.

## Verification
- **Hermetic (Rule J):** a clean series → clean; a crossed candle (high<low), a negative price, a
  20%+ impossible jump, and duplicate timestamps are each flagged; the state gate blocks a corrupted
  series + counts.
- **Real-data (Rule F):** screen the REAL stored benchmark session bars — they are clean (no
  anomalies) → the defense passes real data and would only block genuinely corrupt input.

## Backlog (Rule K)
- 🔵 **Option-path screening** — screen the spot bars the option signals are built from (Rule L
  segment parity); the cash ORB path ships first.

## Atlas impact
security/adversarial defense 🟡→🟢. VII CONSCIENCE 13🟢→**14🟢 — TRUNK VII COMPLETE**. Overall
built 40→41 / 197 (20.8%), partial 59→58.
