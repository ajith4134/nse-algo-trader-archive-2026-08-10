# Research/47 — Opponent Ledger (participant-wise OI) design

**Layer 10 · §10 institution features · slice: opponent ledger.**
Rule D design doc, written before building. Rule I data-acquisition record.
Companion research: participant-wise-OI source verification (this doc rolls it in).

## 1. What the feature is
An **opponent ledger**: "who is on the other side of the market?" It reads NSE's
daily **participant-wise open-interest** report — positioning split across
**Client (retail) / DII / FII / Pro** — and derives a small set of
sentiment/divergence signals the bot can lean on (a confirmation input, never a
standalone trigger). This is one of the PLAN §10 institution features listed
under Layer 10 in the roadmap.

## 2. The data it needs (Rule I — acquired, not stubbed)
The project did not have participant positioning data. Acquired source, verified
live 2026-07-24 (agent research, A-grade / curl-verified):

- **OI URL:** `https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv`
- **Volume URL:** `https://nsearchives.nseindia.com/content/nsccl/fao_participant_vol_DDMMYYYY.csv`
  (legacy `archives.nseindia.com` host also still 200s; `nsearchives` is canonical.)
- **Date token:** `DDMMYYYY`, zero-padded, no separators (e.g. `23072026`).
- **Access:** a real browser **`User-Agent` header alone** returns 200. NO cookie
  handshake / OTP dance (unlike the `www.nseindia.com/api/*` JSON endpoints).
  No UA or a `Python-urllib/*` UA → Akamai 503/blocked.
- **Cadence:** every trading day, EOD ~19:00 IST. **Non-trading day → HTTP 404**
  (use 404 as the holiday/not-yet-published sentinel).
- **Off-market availability:** it is a static archived EOD file — **fetchable right
  now with the market closed** (fetched Thu's file on Fri). → a real Rule-F pass is
  achievable now, not just a Rule-J sim.
- **History:** back to ~April 2014 by URL enumeration.

### Exact file shape (verified from the real bytes)
- **Row 1:** a single preamble line (`""Participant wise Open Interest ... as on Jul 23, 2026"",,,...`) — skip 1 row.
- **Row 2:** header, **15 columns**, some with trailing spaces (`Future Stock Short   `, `Total Long Contracts   `) → **trim headers on parse; map by name, never by position**. Order:
  `Client Type, Future Index Long, Future Index Short, Future Stock Long, Future Stock Short, Option Index Call Long, Option Index Put Long, Option Index Call Short, Option Index Put Short, Option Stock Call Long, Option Stock Put Long, Option Stock Call Short, Option Stock Put Short, Total Long Contracts, Total Short Contracts`
- **Rows 3-7:** `Client`, `DII`, `FII`, `Pro`, `TOTAL`. Values are **contract counts**.
- **Invariant:** the `TOTAL` row has Long == Short by construction (market clears) —
  do NOT read TOTAL as a signal; it is a parse checksum only.

## 3. OSS sourcing verdict (sourcing-oss-parts; license not a filter, Rule E)
| candidate | has participant-OI fn | maintained | anti-bot handled |
|---|---|---|---|
| nsepython `get_fao_participant_oi` | yes | active | **no — bare `pd.read_csv(url)`, blocked by Akamai in 2025-26** |
| jugaad-data | no (issue #38 open since 2022) | best-maintained | n/a |
| nsepy | no | stale | n/a |

**Decision: VENDOR-AND-ADAPT, do not depend.** The "part" is a ~3-line fetch;
depending on nsepython pulls its whole surface for a one-liner that is *broken*
under current NSE anti-bot (no UA). We copy the URL pattern, **fix the UA**, add
404→None, add the `vol` file it lacks, and record provenance. No maintained lib
does the whole structured-participant + ledger feature, so the rest is built.

## 4. Signals the ledger derives (interpretation, B-grade practitioner sources)
Focus on **index futures** (the cleanest directional read) + index options:
- **FII index-futures net** = `Future Index Long − Future Index Short`, and the
  **long-short ratio**. Sustained FII net-long → bullish lean; rising net-short →
  bearish/correction lean. Watch the day-over-day *change* for a reversal lead.
- **Client (retail) = the contrarian / "other side" leg.** Classic trap setup:
  index high + Client heavily long calls while FII cut futures longs / buy puts →
  divergence that often precedes a reversal.
- **Pro** = short-horizon, often counterparty to Client option flow. **DII** rarely
  uses index futures directionally (mostly hedging) → least informative leg.
- **Caveat (every source):** multi-day leaning indicator, NOT an intraday trigger.
  Opponent-ledger = confirmation input only.

Derived fields per day: `fii_index_futures_net`, `fii_long_short_ratio`,
`client_index_futures_net` (opposite sign = the retail-on-the-other-side read),
and a **FII-vs-Client divergence** flag in index futures & options.

## 5. Design — files & seams (Rule C names; Rule J DI seam; Rule G wiring)
New package `src/nse_algo_trader/participant_positioning/`:
- `participant_positioning_source.py` — the **DI seam**: `ParticipantPositioningSource`
  Protocol (`positioning_on(trade_date) -> ParticipantPositioningSnapshot | None`)
  + typed records `ParticipantRow` (client_type + all 15 typed fields) and
  `ParticipantPositioningSnapshot` (report_date + rows keyed by participant).
  Pure, no network — importable by tests and read models.
- `nse_participant_positioning_source.py` — the **real adapter** (vendored fetch,
  UA header, `nsearchives` URL, 1-preamble-skip, header-trim, 404→None, TOTAL
  Long==Short checksum). Provenance note (nsepython URL pattern, MIT, what changed).
- `opponent_ledger.py` — the **read model**: `read_opponent_ledger(snapshot) ->
  OpponentLedgerReading` computing the §4 derived fields + a human `headline`.
- Tests: `InMemoryParticipantPositioningSource` fake (Rule J, lives only under
  `tests/`) → contract test the ledger derivations hermetically; plus a **real-data**
  parse+derive test against a trimmed real sample (Rule F, market-closed-friendly).

**Wiring (Rule G):** the dashboard `LivePaperTradingService` writer fetches the
latest available participant snapshot once per day (cached; 404 → walk back to the
prior trading day), publishes the `OpponentLedgerReading` through the snapshot →
read model → an **"Opponent ledger" dashboard panel** (FII vs Client positioning +
divergence). **Named future consumer:** a later slice feeds the divergence flag
into the strategy bias / assumption registry as an information-diet input (queued,
documented here per Rule G).

## 6. Verification plan
- **Rule J (hermetic sim):** `InMemoryParticipantPositioningSource` behind the seam
  → ledger derivations unit-tested on injected rows; fake never in `src/`.
- **Rule F (real data — achievable now):** fetch a real `fao_participant_oi_*.csv`
  (EOD archive, market-closed OK), parse it, assert the TOTAL Long==Short checksum
  and that FII/Client nets match hand-computed values from the real bytes.
- **Rule H:** SYSTEM_MAP registry block for the new package + ledger edge; two
  flow-chart confirmations. **Rule A:** sign off before the next slice.

## 7. Scope boundary (this slice vs next)
- **This slice:** acquire + parse (real NSE OI) behind the DI seam + opponent-ledger
  read model + dashboard panel + real-data verify.
- **Next (queued):** volume file, multi-day trend of FII net (needs history walk),
  feeding the divergence flag into strategy bias / assumption registry.

---

## Slice 1 (2026-07-24) — divergence → strategy bias (wired into decisions)
The core ledger is display-only; this slice makes it **affect entries** as an
information-diet input (Rule K: the ledger's PRIMARY consumer, not just a panel).

**The bias rule (pure, `market_positioning_bias.py`):**
`institutional_positioning_opposes_entry(reading, entry_is_bullish) -> bool`.
Fires ONLY in the strong divergence case — `reading.retail_on_other_side` is True
AND the FII directional lean is against the entry:
- a **bullish** entry (cash LONG / long CE / bullish put-credit-spread) is opposed
  when FII lean is **bearish** while retail is trapped long;
- a **bearish** entry (cash SHORT / long PE / bearish call-credit-spread) is opposed
  when FII lean is **bullish** while retail is trapped short.
Honors "confirmation input, not a trigger": it never *forces* a trade, only
**defers** a NEW entry on the side retail is trapped on against institutions. Rare
by construction (needs divergence), and multi-day EOD data tilting intraday entries
is exactly how practitioners use it.

**Effect:** at each of the 4 entry sites (2 cash ORB/breakout, directional option,
credit spread), after the antibody-veto check, the loop calls
`state.positioning_permits_entry(entry_is_bullish=…)`; when opposed it skips the
entry and increments `positioning_deferred_count`. Existing open positions are
untouched (never abandons risk — like the veto).

**Wiring (Rule G):** the service already fetches the daily reading; it now also
sets `state.market_positioning_bias = <OpponentLedgerReading>` each day.
`positioning_deferred_count` publishes → read model → server → the Opponent-ledger
panel note ("N new entries deferred — institutions on the other side today").

**Verify:** hermetic bias unit tests (opposed long/short deferred; aligned/neutral
permitted; None permits) + a loop-integration test (a candidate that would open is
deferred when positioning opposes) + a real-reading test (the real 23-Jul FII-bearish
+ retail-long reading defers a LONG entry). Real-data (Rule F) achievable now (EOD).
