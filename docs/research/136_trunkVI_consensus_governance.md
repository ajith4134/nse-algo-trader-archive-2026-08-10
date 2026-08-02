# VI — consensus/conflict-resolution + multi-agent memory governance  ·  research/136

**Trunk VI SOCIETY — multi-agent.** Design doc (Rule D). Sourcing: real WebSearch (July 2026).

## Sourcing (real search)
Query: "python library aggregate weighted expert opinions consensus disagreement conflict resolution
Dawid-Skene". Findings:
- **Dawid-Skene** (`Toloka/crowd-kit`, `sukrutrao/Fast-Dawid-Skene`) — the canonical consensus-from-
  weighted-experts algorithm: EM jointly estimates each worker's confusion matrix + the latent
  ground-truth from a CROWD-LABELLING MATRIX (many (item, worker, label) triples). **Wrong shape for
  us**: we already HAVE per-desk track-record weights (`council_track_record_store.role_log_loss`);
  we don't need EM to estimate expertise from a labelling dataset — a handful of reputation-weighted
  desk opinions on one proposition is a weighted aggregate + agreement measure. **Verdict: reference
  Dawid-Skene / WISE (society-of-experts debate, arxiv 2512.02405), BUILD bespoke** over the council's
  existing reputations.
[Sources: github.com/Toloka/crowd-kit · github.com/sukrutrao/Fast-Dawid-Skene · arxiv.org/abs/2512.02405]
- Multi-agent governance: no fitting library; bespoke reputation-policy over `role_log_loss`.

## The ideas
- **Consensus / conflict-resolution** — the SOCIETY of desks (council roles + debate roles) each hold
  an opinion; produce a track-record-weighted CONSENSUS, measure the CONFLICT (disagreement), and
  RESOLVE: low conflict → consensus reached; high conflict → deadlock resolved toward the
  highest-track-record desk (the most-proven voice breaks a tie).
- **Multi-agent memory governance** — a reputation POLICY over which desks may contribute to the
  shared belief space: TRUSTED desks (reputation ≥ threshold) participate; persistently-poor desks
  are QUARANTINED (excluded) — governance of the shared cognitive commons, distinct from consensus
  (aggregation) and from XIII misinfo-resistance (which scores mechanism-sources, not agent-desks).

## Targets
- `resolve_consensus(opinions, conflict_threshold) -> ConsensusVerdict` — `opinions` = weighted
  `AgentOpinion`s. Success test: agreeing desks → consensus; a split → deadlock resolved to the
  highest-weight desk.
- `govern_agents(reputations, trust_threshold) -> GovernanceReport` — classify each desk trusted vs
  quarantined by reputation.

## Component parts (`society/` — new package for Trunk VI)
- `society/consensus_resolution.py` — `AgentOpinion`(agent, probability, weight) + `ConsensusVerdict`
  (consensus_probability, conflict, is_consensus, decisive_agent, resolution, summary) +
  `resolve_consensus`.
- `society/multi_agent_governance.py` — `AgentStanding`(agent, reputation, is_trusted, is_quarantined)
  + `GovernanceReport`(standings, trusted, quarantined, summary) + `govern_agents`.

## Wiring (Rule G/N)
Daily `_maybe_run_society` reads the council track-record store (`role_log_loss` → reputations) for
governance + the latest cached council member forecasts for consensus; caches both. Surfaces
`consensus_resolution` + `multi_agent_governance`. READ-ONLY (a consumer — govern which desks feed the
council weighting — is queued, Rule K; the council already track-record-weights).

## Verification
- Hermetic (Rule J): agreeing opinions → consensus; a split → deadlock + decisive highest-weight
  desk; reputations above/below threshold → trusted/quarantined.
- Real-data (Rule F): over the real council track-record store (whatever reputations exist), report
  governance; consensus over the latest real council forecasts (or honest "insufficient desks" when
  the council hasn't run — LLM/live-gated, same pattern as the council's own real-data).

## Atlas impact
consensus/conflict-resolution + multi-agent memory governance 🔴→🟢. VI SOCIETY 3🟢→5🟢 (2🔴 left).
Overall built 60→62/197 (31.5%). NEW feature package `society`.
