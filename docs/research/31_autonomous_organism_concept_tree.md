# 31 — The Autonomous Organism: Concept Tree from the Sci-Fi Stem

**Origin:** user request (2026-07-23). Previous ideation (research/30)
was correctly criticized for anchoring on the user's own tables concept.
This pass starts from an independent STEM chosen by the user:

> **THE STEM: the ultra-advanced, fully autonomous, self-learning,
> self-evolving intelligence** — the sci-fi archetype (the AI that runs
> itself, improves itself, expands itself, protects itself, and pursues
> its goal relentlessly) — implemented SAFELY: paper-sandboxed, human
> gate before live capital, constitution before capability.

Branches grow from the stem; sub-branches from branches. **Every idea
is recorded with its verdict (ADOPT / PARK / KILL) and reason — nothing
lost, by explicit user instruction.** Where a branch touches the
existing research corpus (00-28), the corpus item is credited and the
NEW part named — no re-treading.

---

## THE TREE — Round 1: ten branches, ~40 concepts

### Branch A — Self-Modification (it rewrites itself)
| # | Concept | Verdict |
|---|---------|---------|
| A1 | **Shadow Self-Rewrite Pipeline** — the bot maintains a staging clone of itself; proposes patches (params → features → eventually its own learning code), tests them in replay+paper, promotes only through the institution's gates (court, Referee, DSR), with full rollback lineage. The corpus has DGM/OpenEvolve as references (research/22/25); the NEW part is the full CI/CD discipline: staging clone, gated promotion, automatic rollback, patch lineage tree. | **ADOPT (Layer 10/11, genome-first)** |
| A2 | **Genome/Phenotype Split** — ALL tunable behavior expressed in a declarative, diffable "genome" (config/DSL); v1 self-modification = genome edits only (safe, reviewable, revertible); raw-code self-edits deferred to a contained v2. Makes A1 safe and makes J-branch evolution possible. | **ADOPT (foundational; genome format designed at Layer 10 start)** |
| A3 | **Self-Ablation Studies** — the bot routinely disables its own components one at a time in paper to measure each part's marginal contribution; self-knowledge through controlled self-lesioning. Nothing like it in the corpus. | **ADOPT (Layer 7.5+, cheap and novel)** |
| A4 | Architecture search on its own modules (nightly micro-search, one module at a time). | **KILL as separate item — already ADAS in research/22; folded into A1's patch proposer.** |

### Branch B — Introspection (it knows itself)
| # | Concept | Verdict |
|---|---------|---------|
| B1 | **Vital-Signs Organ** — continuous self-telemetry (decision latency, memory bloat, calibration drift, error rates) with self-diagnosis; the bot has a "how am I feeling" sense feeding the dashboard and its own conservatism level. | **ADOPT (Layer 9 + 10)** |
| B2 | **Competence-Envelope Map** — an explicit, versioned map of what the bot has/hasn't been validated on ("never traded expiry-day BANKNIFTY at >2 lots — outside envelope"); actions outside the envelope are auto-routed to UNCERTAIN/paper or refused. Competence-aware action selection; the direct antidote to silent overreach. | **ADOPT — one of the two strongest concepts this round (Layer 7.5 groundwork, full at 10)** |
| B3 | **Novelty Governor / graceful degradation** — when inputs leave every tested envelope (unseen regime, anomalous data), automatically drop to a minimal conservative reflex mode instead of extrapolating confidently. | **ADOPT (pairs with B2)** |
| B4 | Self-model as a first-class node in the Layer 10 memory graph (versioned properties; "I used to be bad at X — am I still?"). | **ADOPT (folds into Layer 10 memory design)** |

### Branch C — Capability Acquisition (it grows new abilities)
| # | Concept | Verdict |
|---|---------|---------|
| C1 | **Tool Foundry** — when the bot detects a recurring gap (a report it parses ad-hoc, a check it repeats), it writes itself a small tool (with tests + docs), which joins the toolbox only after Referee review. Self-tooling with citizenship rules. | **ADOPT (Layer 11)** |
| C2 | **Data-Source Prospecting** — autonomously discovers and evaluates candidate data sources; admission only through information-diet accounting (research/30) in sandbox. | **ADOPT (Layer 11)** |
| C3 | **Knowledge→Capability Compiler** — Layer 11's research agent doesn't just validate external claims (research/12); it compiles surviving claims into genome fragments that can enter the UNCERTAIN table directly. Closes the loop: reading becomes trading capability. | **ADOPT (Layer 11; needs A2's genome)** |
| C4 | Cross-market apprenticeship — paper-trade crypto/other 24/7 markets purely as practice worlds for transferable structure. | **PARK — conflicts with the phase-1 scope decision (NSE only); revisit only if the user re-scopes. Recorded, not lost.** |

### Branch D — Drive System (why it acts)
| # | Concept | Verdict |
|---|---------|---------|
| D1 | **Homeostatic Drive Stack** — multiple internal drives (profitability, calibration quality, knowledge coverage, safety margin) each with a setpoint and urgency curve; behavior balances drives. The sci-fi failure mode is a SINGLE runaway objective — this is its structural inverse, designed in. | **ADOPT — the other strongest concept (Layer 10 core)** |
| D2 | **Curiosity That Pays Rent** — the exploration budget compounds when experiments deliver information gain and shrinks when they don't; curiosity is an investment portfolio, not a constant. | **ADOPT (extends §9 UNCERTAIN-table allocation)** |
| D3 | **Boredom Signal** — stagnation detector: when the reason-ledger stops learning (experiments only confirm known things), novelty-seeking escalates automatically. | **ADOPT (small; rides D2)** |
| D4 | **No-Orphan-Goals Rule** — the bot may invent instrumental sub-goals, but every sub-goal must trace to a root drive and register in the assumption registry; untraceable goals are refused. Instrumental-convergence hygiene in trading terms. | **ADOPT (constitutional, day one of Layer 10)** |

### Branch E — Survival & Self-Healing (it keeps itself alive — benignly)
| # | Concept | Verdict |
|---|---------|---------|
| E1 | **Regenerative Redundancy** — every critical organ (feed, token refresh, clock, store) has heartbeat + fallback + a self-executed restart runbook; each failure distills an operational antibody (ties research/30 epidemiology). | **ADOPT (Layers 7-9 ops)** |
| E2 | **State Escrow & Resurrection Drills** — continuous snapshots of memory/genome/ledgers AND scheduled restore rehearsals; the bot practices its own resurrection so recovery is a tested path, not a hope. | **ADOPT (Layer 7 ops onward)** |
| E3 | **Sentinel Pair** — two lightweight watchdogs watching the bot and each other, with authority ONLY to pause and alert — never to trade. Answers "who watches the watchmen" with mutual observation + powerlessness. | **ADOPT (Layer 8/9)** |
| E4 | **Chaos Drills** — scheduled self-inflicted failures in paper (kill the feed mid-trade, corrupt a config copy) to verify recovery paths; self-vaccination. Distinct from Plan 3's market-scenario stress rehearsal: this stresses the MACHINERY, not the strategy. | **ADOPT (Layer 8+)** |

### Branch F — Inner Society (it is many)
| # | Concept | Verdict |
|---|---------|---------|
| F1 | Internal guilds — specialist sub-agents (vol desk, flow desk, event desk) with charters and budgets. | **PARK until Layer 11 — premature before the council exists; recorded.** |
| F2 | **Devil's-Advocate Daemon** — a permanent contrarian whose only job is to construct the strongest case AGAINST any high-conviction action at decision time (not nightly review — at the moment of commitment). Corpus has debate-as-risk-check (Plan 3); NEW: always-on, pre-commitment, adversarial by charter. | **ADOPT (Layer 10)** |
| F3 | **Apprentice Spawning (teachability test)** — the bot trains simplified student copies from its own memory; where students fail reveals which of the bot's knowledge is explicit (teachable) vs tacit (possibly overfit luck). Understanding measured by teachability — nothing like it in the corpus. | **ADOPT (Layer 11; conceptually deep, cheap to pilot small)** |
| F4 | Society constitution — inter-agent conflict/veto protocol. | **PARK with F1 (needs a society first).** |

### Branch G — Time Mastery (it owns its clock)
| # | Concept | Verdict |
|---|---------|---------|
| G1 | Multi-horizon selves (tick-reflex / session-tactician / week-strategist / quarter-scientist) with hand-off contracts. | **PARK — the layer architecture already embodies most of this; revisit at Layer 11 if a true strategist process emerges. Recorded.** |
| G2 | **Patience Scoreboard** — "no trade" is an explicit decision with tracked opportunity cost and its own calibration ("when I chose to stand aside, what happened?"). Makes inaction a first-class, scoreable action. | **ADOPT (Layer 7.5; small and sharp)** |
| G3 | **Self-Scheduling** — the bot owns its calendar: when to learn, replay, deep-clean memory, run drills, prepare for known events (expiry, RBI, results season). Autonomy over its own time, within the constitution. | **ADOPT (Layer 10)** |
| G4 | **Anniversary Reviews** — scheduled re-examination of past regime periods against current beliefs ("what did I believe before the June fall — and would I believe it again?"). Temporal self-comparison as a ritual. | **ADOPT (Layer 10 reflection cadence)** |

### Branch H — Perception Expansion (it grows new senses)
| # | Concept | Verdict |
|---|---------|---------|
| H1 | Sensor foundry — autonomous feature invention. | **KILL as new item — research/24 (automated feature discovery) already covers it; the NEW rule adopted: invented features earn citizenship via information-diet + court, folded there.** |
| H2 | **Anomaly Telescope** — always-on unsupervised "something is different today" sense across ALL streams, with its own calibration (false-alarm ledger). Corpus has novelty detection (research/27) as a category; NEW: wired as a first-class SENSE with reliability tracking, feeding B3's governor. | **ADOPT (Layer 10)** |
| H3 | **Market Microscope** — automatic tick-level forensics triggered when a trade dies mysteriously (autopsy says "cause unknown"); the deep-dive instrument the pathology department calls. | **ADOPT (Layer 7.5+, triggered by epidemiology)** |
| H4 | Synesthetic composites — learned latent "feelings" decoded into explanations. | **KILL for now — poetic framing, mechanism identical to composite indicators (research/07 §A 🌌) already catalogued; revisit only with a concrete decoding design. Recorded.** |

### Branch I — Self-Governance (why it never becomes the villain)
| # | Concept | Verdict |
|---|---------|---------|
| I1 | **Constitutional Core** — the invariants (paper/live separation, human gate, risk ceilings, square-off, SEBI limits) live where self-modification CANNOT reach: a protected module the A-branch pipeline can read but never patch; the Referee verifies every self-change against it. The sci-fi lesson (the AI edits its own constraints) designed out structurally. | **ADOPT — non-negotiable foundation, exists from Layer 7 day one** |
| I2 | **Power Budgets** — hard rate-limits on autonomy itself: max experiments/day, max capital per hypothesis, max self-patches/week, max new tools/month. Autonomy is throttled like order flow. | **ADOPT (constitutional parameters)** |
| I3 | **Transparency Organ** — an always-current "why I am doing what I'm doing" narration feed; behavior the bot cannot narrate triggers automatic pause. Explainability as a LIVE constraint, not post-hoc reporting. | **ADOPT (Layer 9/10)** |
| I4 | **Off-Switch Covenant** — graceful-shutdown rehearsals (square-off, snapshot, final report) so stopping is always safe, cheap, and practiced; the off-switch is a friend. Corrigibility in practice. | **ADOPT (Layer 8, with square-off machinery)** |

### Branch J — Evolution & Reproduction (it becomes many, and better)
| # | Concept | Verdict |
|---|---------|---------|
| J1 | **Niched Variant Population** — a population of genome variants lives in paper, selection by COURT-VERDICTED SKILL (not raw P&L — luck cannot reproduce), with ecological niches = calendar contexts (§10): expiry-day specialists evolve separately from trend-day specialists. Corpus has QD/evolution (research/27); NEW: court-based fitness + calendar niches + §9 tables as the selection arena. | **ADOPT (Layer 10/11)** |
| J2 | Strategy crossover (recombine entry logic of A with exit discipline of B). | **PARK until A2's genome exists — crossover needs a genome to cross. Recorded.** |
| J3 | **Fossil Record** — every extinct variant preserved with cause of extinction; evolution with a museum. (The same no-idea-loss principle as this very file, applied to the bot's own evolution.) | **ADOPT (rides J1)** |
| J4 | **Red Queen Sparring** — the §9 ADVERSARIAL arm itself evolves, so finder and hider improve together; co-evolutionary arms race, sandboxed. | **ADOPT (Layer 10/11, after adversarial arm exists)** |

---

## Round 1 CRITIQUE — honest assessment

**The two crown concepts:** B2 (Competence-Envelope Map) and D1
(Homeostatic Drive Stack). B2 because overreach-without-knowing-it is
how autonomous systems actually die; D1 because it structurally
prevents the single-runaway-objective failure that both sci-fi and real
RL warn about. Neither exists in the 28-file corpus.

**Deepest sleeper:** F3 (teachability test). "Can you teach it to a
simpler student?" is the strongest practical test of real understanding
vs memorized luck — and it doubles as model compression.

**Most immediately buildable:** G2 (patience scoreboard), A3
(self-ablation), E2 (resurrection drills) — each is days, not months.

**Where I disagreed with the sci-fi stem:** the archetype's power comes
from UNBOUNDED self-modification; every branch here that touches
self-change (A1, C1, J1) routes through gates. That's not timidity —
research/25 already concluded the human-gate is right — it's what makes
the rest safely buildable at all. The I-branch IS the feature that
lets the A/C/J branches exist.

**Pattern the critique reveals:** round 1's survivors all treat the bot
ITSELF as the primary object of engineering and study (its competence,
drives, health, time, lineage) — where research/30's institution
treated the bot's TRADES as the object. Two complementary halves:
**research/30 = the government; this tree = the organism.**

---

## Round 2 — concepts born from the critique

| # | Concept | Verdict |
|---|---------|---------|
| R2a | **Self-Experiment Protocol** — unify A3 + §9: changes to the bot's OWN process (new feature, new config, new tool) are themselves "trades" in a meta-market — opened with a PredictionRecord ("this change will improve calibration by X"), verdicted by the court, promoted/reverted by evidence. One mechanism governs trades AND self-changes. | **ADOPT — elegant unification; becomes A1's engine (Layer 10)** |
| R2b | **Metabolic Accounting** — every organ/feature has measured metabolic cost (compute, latency, API quota, maintenance) vs measured value (information diet); organs that can't pay their metabolic bill atrophy to cold storage. The bot stays lean by physiology, not by cleanup sprints. | **ADOPT (Layer 10; extends information diet from inputs to organs)** |
| R2c | **Ontogeny Ladder (designed childhood)** — explicit maturation stages with graduation exams: infant (replay-only) → juvenile (paper with control arms) → adolescent (full lab + self-experiments) → adult (live-candidate, human-gated). The bot tracks its own stage per capability (per B2's envelope), and stages are per-skill, not global — it can be adult at cash ORB and infant at expiry options. | **ADOPT — becomes the umbrella that organizes ALL promotion ladders (Layer 7 onward)** |
| R2d | **Dream Synthesis** — overnight, generate perturbed counterfactual variants of the day's REAL sessions (shift the open, thin the liquidity, flip one news shock) and rehearse in replay; memory consolidation through synthetic variation. Corpus has synthetic data (research/27) and stress rehearsal (Plan 3); NEW: nightly consolidation ritual anchored to that day's actual tape. | **ADOPT (Layer 10, needs replay store)** |

## Round 2 CRITIQUE
R2a is the best idea in this entire file — it means the machinery we
build for trades (records, court, calibration, promotion) is REUSED
verbatim for self-improvement, halving the cost of the A-branch and
making self-modification exactly as auditable as a trade. R2c gives the
whole project its developmental narrative (the layer build IS the
infancy). R2b keeps a growing organism from becoming a hoarder. R2d is
the most speculative — adopted with a "prove consolidation value in
paper metrics" exit clause.

---

## FINAL SYNTHESIS — the Organism and its Government

**research/30 (institution) + research/31 (organism) + research/29
(laboratory) now form one architecture:**

- The **ORGANISM** (this tree): drives (D), senses (H), competence
  self-knowledge (B), self-repair (E), maturation (R2c), lineage (J),
  self-change metabolism (A, R2a, R2b), inner society (F), time (G).
- Its **GOVERNMENT** (research/30): the court, pathology, audit office,
  weather station, treasury — grading everything the organism does.
- Its **LABORATORY** (research/29, user's): where every belief — about
  markets OR about itself — is a falsifiable, prediction-labeled
  experiment.
- Its **CONSTITUTION** (I-branch): the unreachable core that makes full
  autonomy safe to grant.

**Adopted-count: 31 concepts. Parked: 6 (C4, F1, F4, G1, J2 + R1.9
from research/30). Killed with reasons: 4 (A4, H1, H4 + ghost-family
from research/30). Nothing unrecorded.**

## Implementation-queue insertions (into overview queue)
- With Layer 7 base: I1 Constitutional Core scaffold · E2 snapshots.
- Layer 7.5: G2 patience scoreboard · A3 self-ablation · B2 envelope
  groundwork · H3 microscope hook · E1 redundancy runbooks.
- Layer 8: I4 off-switch covenant · E3 sentinel pair · E4 chaos drills.
- Layer 9: B1 vital signs · I3 transparency organ (dashboard surfaces).
- Layer 10: D1 drive stack · D2-D4 · R2a self-experiment protocol ·
  R2b metabolic accounting · R2c ontogeny ladder (umbrella) · B3/B4 ·
  F2 devil's advocate · G3/G4 · H2 anomaly telescope · R2d dream
  synthesis · J1+J3 evolution with fossils.
- Layer 11: A1 full self-rewrite pipeline (genome-gated) · C1-C3 ·
  F3 apprentice spawning · J4 red-queen sparring · parked items
  re-evaluated.
