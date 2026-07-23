# AI Trunk/Branch ↔ Layer Integration & Sequencing Map

**Purpose:** answer, in one place, the questions the user asked before
Layer 7: *how do the 16 trunks / ~200 branches (research/32-36) connect
to each other AND to the existing layer roadmap, and at what step does
each start being implemented?* Read `00_project_overview.md` (roadmap)
and PLAN §9-16 first; this file is the bridge between the concept tree
and the buildable layers.

---

## 1. The central principle: the tree is built THROUGH the layers

The 16 trunks are **not** a separate future project bolted on after
Layer 11. They are already partially built, and each faculty grows
**inside the existing layer roadmap, just-in-time, at the layer where it
first becomes real.** Layers 1-6 already instantiate the BODY and SENSES
trunks in code. Every later layer lights up more trunks. Nothing is
built speculatively ahead of the layer that gives it real data to
operate on (Rule F, below).

```
        THE STEM (autonomous · sentient · self-evolving trading intelligence)
                                   │
   ┌───────────────┬──────────────┼───────────────┬──────────────────┐
 BODY/SENSES     EPISTEMICS/     CONSCIENCE      MIND/SELF/          UNIVERSAL
 (already        PREDICTIVE      (Referee +      SOCIETY/            ACCESS +
  built L1-6)    /MEMORY seed    Constitution    SENTIENCE/          SELF-MOD
                 (Layer 7 lab)    Layer 7)       CURIOSITY/          (Layer 11)
                                                 AXIOLOGY (Layer 10)
```

## 2. Trunk → layer-of-first-appearance → layer-of-maturity

| Trunk | First appears | Matures | How (which layer gives it real data) |
|-------|---------------|---------|--------------------------------------|
| **II SENSES** | L1-3 (built) | L7.5/L10 | market data + indicators ARE perception; anomaly/microstructure later |
| **IV BODY** | L6 (built) | L7 | OMS = actuation; execution/slippage realism at L7; survival = ops L7+ |
| **XVI UNIVERSAL ACCESS** | L2/L6 (built, partial) | L11 | broker/data APIs already; internet-research + tool-foundry gated to L11 |
| **XIII EPISTEMICS** | **L7** | L10 | the §9 lab (calibration/Brier, WIN/LOSS/UNCERTAIN) IS epistemics starting |
| **IX PREDICTIVE CORE** | **L7** | L10 | the replay engine + pre-mortem IS a proto world-model |
| **XV MEMORY** | **L7** | L10 | PredictionRecords + trade log = proto episodic memory; graph at L10 |
| **VII CONSCIENCE** | **L7** | L10 | Constitutional Core + Referee codified at L7; security/alignment at L10 |
| **I MIND** | L4 (proto) | L10 | strategy logic = proto reasoning; learning subsystem at L10 |
| **III WILL** | L4 (proto) | L10 | regime gate = proto decision; full drive stack at L10 |
| **XIV AXIOLOGY** | L5 (implicit) | L10 | risk/sizing encode implicit values; explicit value system at L10 |
| **VIII SENTIENCE/WORKSPACE** | L10 | L10 | needs ≥2 modules to bind — the workspace integrator arrives with L10 |
| **XII CURIOSITY** | L7 (seed) | L10 | UNCERTAIN-table allocation is proto-curiosity; intrinsic-motivation at L10 |
| **V SELF** | L10 | L11 | ontogeny ladder organizes L7+ paper stages; self-mod/evolution at L10/11 |
| **VI SOCIETY** | L9 | L10 | human interface = dashboard (L9); council/external-agents at L10 |
| **X AUTOPOIESIS** | L7 (ops) | L10 | self-maintenance/heartbeats at L7; metabolic accounting at L10 |
| **XI GENERATIVITY** | L10 | L11 | strategy evolution/open-endedness — needs the lab + memory first |

**Reading:** three trunks are already substantially built (SENSES, BODY,
part of UNIVERSAL ACCESS). **Layer 7 is the big ignition** — it is where
FIVE trunks first become real at once (EPISTEMICS, PREDICTIVE CORE,
MEMORY, CONSCIENCE, and the CURIOSITY/SELF seeds), because the paper lab
is the first place the bot forms beliefs, predicts, remembers outcomes,
and is audited. Layer 10 is where the remaining "mind" trunks bloom.
Layer 11 is universal-access + self-modification.

## 3. Reverse view — what each LAYER contributes to the trunks

- **L1-3 (done):** SENSES (perception), seed of MIND (features).
- **L4-5 (done):** proto MIND (strategy reasoning), proto WILL (regime
  decision), implicit AXIOLOGY (risk values), proto CONSCIENCE (risk gate).
- **L6 (done):** BODY (actuation), part of UNIVERSAL ACCESS (broker API).
- **L7 (next):** EPISTEMICS + PREDICTIVE CORE + MEMORY + CONSCIENCE
  ignite; CURIOSITY/SELF/AUTOPOIESIS seeds. *This is the AI's birth.*
- **L8:** BODY (square-off effector), CONSCIENCE (off-switch/corrigibility).
- **L9:** SOCIETY (human interface), CONSCIENCE (transparency surfaces) —
  the dashboard renders every trunk's state.
- **L10:** MIND, WILL, SELF, SOCIETY, SENTIENCE/WORKSPACE, CURIOSITY,
  AXIOLOGY, MEMORY-graph, AUTOPOIESIS all mature — the integration layer.
- **L11:** UNIVERSAL ACCESS (internet/tools), SELF (self-modification),
  GENERATIVITY (evolution) — the frontier, gated.

## 4. How the trunks connect to EACH OTHER (the wiring)

Four hubs bind 16 specialists into one mind:
- **VIII Global Workspace = the bus.** Every trunk publishes to it; it
  broadcasts back. This is the integrator that makes the 16 act as one
  (arrives L10, when there are modules to bind).
- **IX Active Inference = the currency.** Perception, action, learning,
  curiosity all reduce to minimizing prediction error over the world-
  model — unifying SENSES, BODY, MIND, CURIOSITY, EPISTEMICS.
- **XV Memory = the substrate.** Every trunk reads/writes it; the
  temporal knowledge graph is the shared long-term store.
- **VII Conscience = the envelope.** Everything runs inside the
  Constitutional Core; the Referee audits every other trunk; GATED
  branches (self-mod, tool-foundry, internet) only act with its consent.

Concept-file → trunk wiring (no loss): research/29 lab → EPISTEMICS+
MEMORY+CONSCIENCE; research/30 institution → EPISTEMICS+CONSCIENCE+
PREDICTIVE; research/31 organism → SELF+BODY+WILL+CONSCIENCE; research/
32-36 = the full trunk/branch enumeration these fold into.

## 5. When do the ~200 branches get implemented?

**Rule: a branch is implemented at the layer where its trunk gives it
real data — never earlier.** The `00_project_overview.md` AI/dashboard
implementation queue is the concrete ordered list; this map explains
WHY each item sits where it does. Twig-level specs for a trunk are
written one file per trunk, just-in-time, right before that trunk's
layer — not now.

## 6. The gate on all of it (see Rule F)
Every layer/feature/branch — including all 200 — is signed off only
after verification against the REAL data it operates on, per the new
Rule F. The map above deliberately places each faculty at the layer
where that real data first exists, so Rule F is always satisfiable.
