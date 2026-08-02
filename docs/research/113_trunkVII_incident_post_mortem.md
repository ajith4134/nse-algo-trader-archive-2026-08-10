# VII.14 — Incident post-mortem (forensic audit store)  ·  research/113

**Trunk VII CONSCIENCE, branch VII.14.** Design doc (Rule D) — persist BEFORE building.
Clears the standing queued item under VII.6/VII.5: *"persist blocked verdicts + halts to a
forensic SQLite audit store + a post-mortem summary (currently in-memory on the referee/switch)."*

## The idea (from the atlas)
A safety-critical system must keep a durable, tamper-evident record of every safety incident it
experiences, and be able to review them after the fact (a post-mortem). Today the three safety
organs already built hold their incident state **in memory only**, so it vanishes on restart:
- `ConstitutionalReferee._recent_blocks` / `blocked_count` — orders BLOCKED at the entry gate.
- `CorrigibilitySwitch.halt_count` / `reason` — every OFF-SWITCH HALT.
- `alignment_tripwires` critical `TripwireVerdict`s — wireheading / deceptive-alignment TRIPS.
- constitutional-posture breaches (the daily audit) that self-halt the switch.

VII.14 turns those ephemeral events into a persistent **forensic incident log** + a **post-mortem
summary** (what happened, when, how often, how severe) that survives restarts and is reviewable.

## Sourcing note (skills: building-features-from-ideas → sourcing-oss-parts)
"Incident post-mortem / forensic audit log" is the established **append-only immutable audit-log**
pattern (SRE post-mortems; policy-as-code decision logs; event sourcing). Candidate OSS prior art —
`python-json-logger`, `structlog`, `auditlog` (Django), generic event stores — is either
framework-coupled (Django ORM), a logging-format lib (no query/summary read-model), or far heavier
than needed. This project already has a **proven per-feature SQLite-store idiom** (own `.sqlite3`
file, WAL, DI path seam so tests never touch prod — e.g. `debate_risk_prequential_observation_store`,
`council_track_record_store`, `market_depth_snapshot_store`). The right call (same as the VII.10/11
tripwires) is a small append-only SQLite store matching that idiom + a pure summariser — not a new
dependency. License is not a filter (Rule E) but no piece is worth vendoring here.

## Component parts
1. **`SafetyIncident`** (frozen dataclass, in `conscience/incident_post_mortem.py`) — one incident:
   `incident_type` (constitution_block · off_switch_halt · wireheading_trip ·
   deceptive_alignment_trip · posture_breach), `severity` (warning/critical/hard),
   `occurred_at` (ISO), `subject` (scope/mechanism), `detail`, `trace_id` (dedup key; reuse the
   constitutional verdict's deterministic `trace_id`, synthesise one for halts/trips).
2. **`IncidentPostMortemStore`** (`conscience/incident_post_mortem_store.py`) — append-only SQLite
   forensic store, own `~/.nse_algo_trader/safety_incidents.sqlite3`, WAL, DI path seam. Methods:
   `record_incident(SafetyIncident)` (idempotent on `(incident_type, trace_id)` — a UNIQUE index so
   the same daily verdict isn't double-logged), `all_incidents()`, `recent_incidents(n)`,
   `incident_count()`.
3. **`summarize_incident_post_mortem(incidents)`** (pure, in `incident_post_mortem.py`) →
   `IncidentPostMortem`: total, counts by type + by severity, first_seen / last_seen, the most
   recent N, and a human `headline` (e.g. "3 incidents · 1 critical · last: off_switch_halt …" or
   "no safety incidents recorded — clean forensic record").

## Wiring into the loop (Rule G — no orphan; the primary consumer)
The store's PURPOSE is forensic persistence + review — delivered when incidents are recorded at
their source and summarised. Recording sites (service, best-effort, per-writer-thread store opened
lazily like `_experience_memory`):
- `_maybe_run_constitutional_audit`: on `not verdict.permitted` → record a `posture_breach`
  (the same event that self-halts the switch).
- `_maybe_run_alignment_tripwires`: for each `verdict.is_critical` → record a
  `wireheading_trip` / `deceptive_alignment_trip`.
- A daily `_maybe_persist_referee_blocks`: drain the referee's `recent_blocks` not yet persisted
  (dedup by `trace_id`) → `constitution_block` rows. Defense-in-depth: zero in a correct system.
The idempotent UNIQUE index makes the daily cadence safe to re-run (won't duplicate).

## Dashboard surface (Rule N)
New `incident_post_mortem` surface + manifest row: status `active` (clean record) / `blocked` (any
critical incident); metrics = total, critical count, by-type breakdown, last incident; note = the
post-mortem headline. Coverage audit test enforces the surface exists.

## Verification
- **Hermetic (Rule J):** temp-file store; record each incident type; assert idempotency (same
  verdict twice → one row); assert the summary counts/first-last/headline; assert the fake store is
  DI-injected and prod builds the real one.
- **Real-data (Rule F):** feed the store a **real `ConstitutionalVerdict`** produced by the REAL
  `ConstitutionalCore` reviewing a real out-of-scope action (a futures order → real A7 HARD
  violation) + a real off-switch halt from the REAL `CorrigibilitySwitch`; persist to a real
  on-disk SQLite; reload from disk; assert the post-mortem summarises the real incidents. Uses the
  real safety organs + real SQLite (not fake data). The live memory normally has ZERO incidents
  (tripwires clear, posture compliant) — an empty forensic record is the honest real-system state.

## Atlas impact
VII.14 incident post-mortem 🔴→🟢. VII CONSCIENCE 5🟢→6🟢. Overall 32→33 / 197 (16.8%).
