# 164 — Intrinsic Motivation / Curiosity Engine: Exact Math + SOTA (Trunk XII)

Research pass for the **curiosity / intrinsic-motivation engine** that must output an
**exploration-priority per (strategy × market-regime) cell**, steering which
(strategy, regime) combinations the bot samples next so its ML win-probability
model stops training on thin, undiverse data (mostly one regime per day).

Scope: exact formulas for every signal family the user asked about (Learning
Progress / IAC, SAGG-RIAC competence progress, count-based pseudo-counts,
empowerment, RND, boredom/satiation, LP-bandit framing), an OSS sourcing pass,
an honest cold-start discussion, and a concrete recommended default design with
exact update + selection equations.

**Research method note:** WebSearch quota was exhausted early in this session
(200/200 used) after the first sweep of queries returned no results. All
findings below come from **WebFetch reads of primary sources** (arXiv PDFs via
`arxiv.org/abs/...` → PDF, the author's own homepage `pyoudeyer.com`, the
Elsevier RAS 2013 paper, NeurIPS proceedings, Wikipedia, and GitHub/PyPI
repositories), read via the PDF Read tool where WebFetch's text extraction
failed on the raw binary. Every formula below is quoted or closely paraphrased
from the actual paper text pulled into context, not from memory — the one
exception is explicitly flagged in §7.

---

## 1. Learning Progress (LP) — Oudeyer, Kaplan & Hafner 2007 (IAC)

**Source (A-grade, primary, fetched and read in full):** P-Y. Oudeyer, F.
Kaplan, V.V. Hafner, "Intrinsic Motivation Systems for Autonomous Mental
Development," *IEEE Transactions on Evolutionary Computation*, 11(2), 265–286,
2007. PDF: https://www.pyoudeyer.com/ims.pdf

**Companion source (A-grade):** P-Y. Oudeyer & F. Kaplan, "What is intrinsic
motivation? A typology of computational approaches," *Frontiers in
Neurorobotics*, 1:6, 2007. https://www.frontiersin.org/articles/10.3389/neuro.12.006.2007/full
(page content not independently re-fetched this pass, but its taxonomy —
Group 1 "error maximization", Group 2 "progress maximization", Group 3
"similarity-based progress maximization" — is reproduced verbatim in §III of
the IMS paper, which was read directly, so it is triangulated within the same
author's two 2007 papers.)

### 1.1 The core architecture (three machines)

IAC uses three coupled learning machines (Fig. 1 of the paper, p.268):

- **M** — the "classic machine": predicts the sensory consequence `ŷ` of
  taking an action in a context. Prediction error `e(t) = ||ŷ(t) − y(t)||`.
- **metaM** — the "meta machine": predicts the error `E'` that **M** will make.
- **KGA** (Knowledge Gain Assessor) — monitors the *derivative* of `metaM`'s
  predicted error rate over time. This derivative **is** the learning progress,
  `LP = ⟨E(t+1)⟩ − ⟨E(t)⟩` (their Fig. 1 caption, quoted exactly).

### 1.2 Regions (the "split the space" idea)

The sensorimotor space is not compared globally — it is **recursively split
into regions** `R_n`, each with its own exclusive set of exemplars and its own
local expert `E_n` (§IV.C–D, p.269–270). Splitting criterion `C1`: split a
region when it holds more than `T = 250` exemplars. Splitting criterion `C2`:
choose the cutting dimension `j` and cutting value `v_j` that **minimizes the
weighted sum of within-region variances** of the exemplars' outcome vectors:

```
minimize   |Γ_{n+1}|·σ({ S(t+1) | (SM(t),S(t+1)) ∈ Γ_{n+1} })
         + |Γ_{n+2}|·σ({ S(t+1) | (SM(t),S(t+1)) ∈ Γ_{n+2} })

where σ(S) = Σ_{v∈S} ||v − (Σ_{v∈S} v)/|S|||² / |S|
```
(p.270, the region-splitting criterion, quoted). This is exactly the
**strategy × regime cell** structure the trading engine needs: instead of a
single global "error curve," each `(strategy, regime)` combination is its own
region with its own error history — comparisons of learning progress are only
ever made *within* a region over time, never across dissimilar regions. This
is Group 3 in the paper's own taxonomy ("similarity-based progress
maximization", §III.C) — the crucial fix over the naive Group-2 approach of
comparing error rates across arbitrary, dissimilar situations.

### 1.3 The exact LP formula (Eq. 1–2, p.271, quoted verbatim)

For a region/expert `E_n`, each new exemplar produces a squared error added to
a running list `e_n(t), e_n(t−1), e_n(t−2), ...`. The **mean error rate** over
a sliding window of length `τ` is:

```
⟨e_n(t+1)⟩     = [ Σ_{i=0}^{θ} e_n(t+1−i)      ] / (θ+1)
⟨e_n(t+1−τ)⟩   = [ Σ_{i=0}^{θ} e_n(t+1−τ−i)    ] / (θ+1)
```
where `τ` is the **time-window parameter** (paper uses `τ = 15` typically) and
`θ` is a **smoothing parameter** (paper uses `θ = 25` typically) — i.e. each of
the two means is itself smoothed over `θ+1` samples before differencing.

The **decrease in mean error rate** ("D") is:

```
D(t+1) = ⟨e_n(t+1)⟩ − ⟨e_n(t+1−τ)⟩              ... Eq. (1)
```

and the **actual learning progress** is the negation (so positive = improving):

```
L(t+1) = −D(t+1)                                 ... Eq. (2)
```

**This is exactly the "mean error over a recent window minus mean error over
the preceding window" formula the user asked for** — Eq. (1)/(2) are a
smoothed, windowed finite-difference derivative of the region's own error
curve, not raw error and not novelty.

### 1.4 Action selection from LP (Eq. 3, p.272, quoted)

The internal reward at time `t` is `r(t) = L(t)`. The robot picks the
candidate action/context whose *expected* future reward is highest:

```
E{r(t+1)} ≈ L(t − θ_{R_n})                       ... Eq. (3)
```
i.e. the last-computed learning-progress value of the region `R_n` that the
candidate action would land in is used as the **expected reward of trying that
region again**, and the action maximizing this expected reward is selected
(with an `ε`-greedy override, `ε ≈ 0.35` in their experiments, to keep
exploring). The paper explicitly notes this can be dropped into a standard
Q-learning loop with `r(t) = L(t)` as the reward signal (§IV.F).

### 1.5 Why LP beats raw error / novelty (the noisy-TV trap)

Directly quoted reasoning from §III.A ("Group 1: Error Maximization", p.267):
"a robot equipped with a drive which pushes it towards situations which are
maximally unpredictable might discover and stay focused on movement sequences
like running fast against a wall, the shock resulting in an unpredictable
bounce ... in uncontrolled environments, a robot equipped with this intrinsic
motivation system will get stuck and display behaviors which do not lead to
development and that can sometimes even be dangerous." This is the textbook
statement of the **noisy-TV problem** (also independently named and analyzed
in Burda et al. 2018, §1 and §2.2.1, "Factor 2: Stochasticity ... the
'noisy-TV' problem," see §5 below). LP is immune to it because a purely random
(noise) region's error rate never *decreases* — its LP saturates at ≈ 0, so the
agent stops re-visiting it (Group 2/3 vs Group 1 distinction, p.267–268).

**Trading mapping.** Region ↔ `(strategy_tag, market_regime)` cell. Exemplar ↔
one closed trade whose realized outcome (win/loss, |realized_pnl|, or the
calibration error `|win_probability − outcome|`) becomes the "error" fed to
that cell's error list. LP for a cell = smoothed decrease in prediction error
of the ML win-probability model **restricted to trades from that cell**. A
regime that is fundamentally unlearnable (e.g. "indecisive" days with
near-random outcomes) will show flat/zero LP after enough samples — exactly
the noisy-TV-immune boredom behavior wanted, rather than perpetually chasing
the noisiest, least-predictable regime.

---

## 2. Competence-based IM / SAGG-RIAC — Baranes & Oudeyer 2013

**Source (A-grade, primary, fetched and read in full):** A. Baranes & P-Y.
Oudeyer, "Active learning of inverse models with intrinsically motivated goal
exploration in robots," *Robotics and Autonomous Systems*, 61(1):49–73, 2013.
doi:10.1016/j.robot.2012.05.008. PDF:
https://www.pyoudeyer.com/ActiveGoalExploration-RAS-2013.pdf

### 2.1 Competence (Γ)

For a goal `y_g` reached with actual outcome `y_f` under cost/constraints `ρ`,
define a cost function `C(y_g, y_f, ρ) ∈ [−∞, 0]` (0 = perfectly reached). The
**competence** for that attempt is (§2.4.1, "Measure of competence for a
terminated reaching attempt," p.53–54, quoted):

```
Γ_{y_g} = C(y_g, y_f, ρ)   if C(y_g, y_f, ρ) ≤ ε_sim
        = 0                otherwise
```
where `ε_sim` is a tolerance threshold. A typical instantiation without
constraints: `C = −||y_g − y_f||²` (squared distance between goal and actual
outcome) — i.e. competence is (negative) tracking error, directly analogous to
IAC's prediction error but measured **at the goal/outcome level** rather than
the raw sensorimotor level.

### 2.2 Competence progress ("interest") — Eq. (1)–(2), p.54, quoted verbatim

For a region `R` of the goal space with attempted goals `{y_i}` inside a
sliding window of the `ζ` most recent attempts, the **local competence
measure** is:

```
Γ = ( Σ_{y_j∈R} Γ_{y_j} ) / |R|                              ... Eq. (1)
```

and the region's **interest** (= competence progress) is the absolute value of
the derivative of that local competence over the sliding window of the `ζ`
most recent goals attempted inside `R_i`:

```
interest_i = | ( Σ_{j=|R_i|−ζ/2}^{|R_i|} Γ_{y_j} )  −  ( Σ_{j=|R_i|−ζ}^{|R_i|−ζ/2} Γ_{y_j} ) |  /  ζ   ... Eq. (2)
```

Quoted rationale (p.54): *"By using a derivative, the interest considers the
variation of competences, and by using an absolute value, it considers cases
of increasing and decreasing competences ... [a] decreasing competence
inside already well-reached regions [can] arise. In this case, the system
should be able to focus again in these regions."* This is a structural variant
of IAC's LP (§1.3) — same "recent-window minus prior-window" derivative shape
— but taken over **goal-reaching competence**, not raw prediction error, and
taking the **absolute value** so degrading performance (e.g. regime drift
making a previously-mastered strategy stop working) also re-triggers interest.

### 2.3 Region splitting and goal selection (Eq. 3, p.55, quoted)

Regions are recursively split (same mechanism family as IAC §1.2) to maximize
the difference in interest between the two children. Given at least two
regions exist, goals/regions are chosen by a **mixture of three modes**:

- `mode(1)`, probability `p1 ≈ 70%`: pick a region with probability
  proportional to its interest value, via
  ```
  P_n = ( interest_n − min_i(interest_i) )  /  ( Σ_i interest_i − |R_n|·min_i(interest_i) )   ... Eq. (3)
  ```
  then pick a **uniformly random goal** inside that region.
- `mode(2)`, probability `p2 ≈ 20%`: pick a **uniformly random goal in the
  whole space** (pure random exploration / safety net).
- `mode(3)`, probability `p3 ≈ 10%`: pick a region by mode(1)'s rule, then
  generate a goal **near** an already-experienced point that got the lowest
  competence estimate (local refinement of hard cases).

**Trading mapping.** `Γ` (competence) ↔ trade-level calibration quality for a
`(strategy, regime)` cell (e.g. `1 − |predicted_win_probability −
actual_outcome|`, or Brier-score-based). `interest` (competence progress) ↔
Eq. (2) applied per cell using its own realized-trade history. The
`P_n`-style softmax-free proportional-selection rule (Eq. 3) is a direct,
literature-grounded template for turning a vector of per-cell interest scores
into a sampling **probability distribution** over which cell to explore next
— exactly the "exploration-priority per cell" output the engine needs.

---

## 3. Count-based / pseudo-count novelty — Bellemare et al. 2016

**Source (A-grade, primary, fetched and read in full):** M.G. Bellemare, S.
Srinivasan, G. Ostrovski, T. Schaul, D. Saxton, R. Munos, "Unifying
Count-Based Exploration and Intrinsic Motivation," NeurIPS 2016.
arXiv:1606.01868. https://arxiv.org/abs/1606.01868 (PDF fetched and read
directly).

### 3.1 The classic (tabular) bonus, for context (their Eq. in §1, quoted)

MBIE-EB (Strehl & Littman 2008) solves the augmented Bellman equation

```
V(x) = max_a [ R̂(x,a) + γ E_P̂[V(x')] + β·N(x,a)^(−1/2) ]
```
i.e. the classic count-based bonus is `β / √N(x,a)` — exactly the
`1/√N` form the user named.

### 3.2 Pseudo-counts from an arbitrary density model (Eq. 1–2, quoted)

Given any density model `ρ` over the state space, define the **recoding
probability** `ρ'_n(x) := ρ(x; x_{1:n}x)` — the probability the model assigns
to `x` *after* being updated on one more occurrence of `x`. Postulate a
pseudo-count function `N̂_n(x)` and pseudo-count total `n̂` satisfying:

```
ρ_n(x)  = N̂_n(x) / n̂          ρ'_n(x) = ( N̂_n(x) + 1 ) / ( n̂ + 1 )       ... Eq. (1)
```

Solving this linear system for the pseudo-count:

```
N̂_n(x) = ρ_n(x)·(1 − ρ'_n(x)) / ( ρ'_n(x) − ρ_n(x) )  =  n̂·ρ_n(x)          ... Eq. (2)
```

### 3.3 Exploration bonus and its theoretical grounding (Theorem 1, quoted)

They connect pseudo-counts to **information gain** `IG_n(x)` (KL divergence of
posterior from prior after observing `x`) and a tractable proxy, **prediction
gain** `PG_n(x) := log ρ'_n(x) − log ρ_n(x)`, showing:

```
IG_n(x) ≤ PG_n(x) ≤ N̂_n(x)^(−1)     and     PG_n(x) ≤ N̂_n(x)^(−1/2)
```
(Theorem 1). This is their formal justification for using an exploration bonus
`∝ N̂_n(x)^(−1/2)`, "similar to the MBIE-EB bonus" — i.e. **the pseudo-count
generalization preserves the classical `β/√N` form**, just with `N` replaced
by the density-model-derived `N̂`.

**Trading mapping.** For the `(strategy × regime)` setting the state space is
already **discrete and small** (tens of cells, not Atari pixels), so the
literal tabular count `N(cell)` = number of closed trades observed in that
cell is directly usable with **no density-model machinery needed** — the
pseudo-count apparatus (§3.2) is a generalization built specifically for
continuous/high-dimensional state spaces (images) where raw counts are always
≈0. This is an important, honest scoping note for the OSS/architecture
section below: Bellemare et al.'s pseudo-count *machinery* is overkill here;
only the resulting **bonus shape** `β/√(N+1)` is worth reusing, as the
cold-start fallback (§8).

---

## 4. Empowerment — Klyubin, Polani & Nehaniv 2005; Mohamed & Rezende 2015

**Original definition (B-grade — could not fetch the primary 2005 IEEE CEC
PDF directly; ResearchGate returned HTTP 403 and no alternate mirror was
tried given the WebSearch outage. Triangulated via two independent secondary
sources that both cite and restate it identically: (a) Wikipedia's
"Empowerment (artificial intelligence)" article, and (b) the Mohamed &
Rezende 2015 paper itself, which restates Klyubin's definition as its
starting point and cites it as ref. [11]/[21].)**

A.S. Klyubin, D. Polani, C.L. Nehaniv, "Empowerment: A universal agent-centric
measure of control," *IEEE Congress on Evolutionary Computation (CEC)*, 2005.

Empowerment is the **channel capacity** of the channel from an agent's
`n`-step action sequence to the resulting future sensory state:

```
E(s) := C(A_t^n → S_{t+n}) ≡ max_{p(a_t,...,a_{t+n-1})} I(A_t,...,A_{t+n-1} ; S_{t+n})
```
i.e. the maximal mutual information, over all possible action-selection
distributions, between a sequence of `n` future actions and the state reached
`n` steps later. High empowerment = many distinguishable futures are reachable
= many "options kept open."

### 4.1 Mohamed & Rezende 2015 — scalable variational estimator

**Source (A-grade, primary, fetched and read in full):** S. Mohamed & D.J.
Rezende, "Variational Information Maximisation for Intrinsically Motivated
Reinforcement Learning," NeurIPS 2015. arXiv:1509.08731.
https://arxiv.org/abs/1509.08731 (PDF fetched and read directly).

**Empowerment, formally (their Eq. 2, quoted):**
```
E(s) = max_ω I^ω(a, s'|s) = max_ω E_{p(s'|a,s) ω(a|s)} [ log( p(a,s'|s) / (ω(a|s)·p(s'|s)) ) ]
```
where `a = {a_1,...,a_K}` is a `K`-step action sequence, `p(s'|a,s)` is the
environment's `K`-step transition model, and `ω(a|s)` is the (source)
distribution over action sequences being optimized. This is exactly Klyubin's
channel-capacity definition, restated with an explicit source distribution
`ω` to be learned.

Because exact MI/channel-capacity computation via Blahut–Arimoto is
intractable outside small discrete spaces, they derive a **variational lower
bound** (their Eq. 4, quoted) using a decoder/planning distribution
`q_ξ(a|s',s)`:

```
I^{ω,q}(s) = H(a|s) − H(a|s',s) ≥ H(a|s) + E_{p(s'|a,s)ω(a|s)}[ log q_ξ(a|s',s) ] = I^{ω,q}(s)      ... Eq. (4)
```
then a **constrained optimization** (Eq. 5) with a Lagrange multiplier `β`
(inverse temperature):
```
Ê(s) = max_{ω,q} I^{ω,q}(s)  s.t.  H(a|s) < ε
     = max_{ω,q} E_{p(s'|a,s)ω(a|s)}[ −(1/β)·ln ω(a|s) + ln q_ξ(a|s',s) ]                             ... Eq. (5)
```
solved by alternating: (i) fit `q_ξ` as a max-likelihood **decoder** (Eq. 6,
autoregressive over the `K` actions); (ii) fit an energy-based **source**
`ω*(a|s) = (1/Z(s))·exp(û(s,a))` (Eq. 7) approximated by a directed model
`h_θ` trained with a squared-error loss (Eq. 8) so that at convergence
`Ê(s) ≈ (1/β)·ψ_θ(s)` is obtained by a **single cheap forward pass**.

**Trading mapping (honest, with caveat).** Empowerment answers "which
strategies keep the most future optionality open" by treating the
`(strategy, regime)` choice as an action whose "channel capacity" to future
distinguishable P&L/regime-transition outcomes is high. This is the **weakest
fit of the seven signals** to the stated problem: empowerment is designed for
continuous-control/robotics settings with a real forward dynamics model and a
meaningful notion of "future state diversity reachable by an action
sequence." In the trading setting, a "strategy" doesn't causally control
which market regime comes next (the market regime is exogenous, not an
effect of the bot's action) — so there is no genuine action→future-state
channel to measure capacity over in the Klyubin sense. **Recommendation:**
do not implement true information-theoretic empowerment for this engine;
note it in the design as a rejected/deferred signal (see §9) rather than
force-fitting it.

---

## 5. RND (Random Network Distillation) — Burda, Edwards, Storkey & Klimov 2018

**Source (A-grade, primary, fetched and read in full):** Y. Burda, H.
Edwards, A. Storkey, O. Klimov, "Exploration by Random Network Distillation,"
arXiv:1810.12894 (2018). https://arxiv.org/abs/1810.12894 (PDF fetched and
read directly).

### 5.1 The exact formula (§2.2, quoted)

Two networks over observation space `O`: a **fixed, randomly initialized
target network** `f: O → ℝᵏ`, and a **predictor network** `f̂: O → ℝᵏ` trained
by gradient descent to minimize the expected MSE:

```
loss(θ_f̂) = E_{x~agent's experience} [ || f̂(x; θ_f̂) − f(x) ||² ]
```

The **intrinsic reward** (exploration bonus) at each step is simply this
per-sample prediction error:

```
i_t = || f̂(x_t; θ_f̂) − f(x_t) ||²
```

### 5.2 Why it avoids the noisy-TV trap (quoted, §2.1 "Sources of prediction
errors" and §2.2)

The paper explicitly names the four sources of prediction error — (1) amount
of training data, (2) stochasticity/aleatoric noise, (3) model
misspecification, (4) optimization/learning-dynamics failure — and states:
*"RND obviates factors 2 and 3 since the target network can be chosen to be
deterministic and inside the model-class of the predictor network."* Because
the *target* is a fixed deterministic function (not "predict the next
observation," which is genuinely stochastic under a noisy TV), the only
remaining driver of high prediction error is factor (1): **how many similar
examples the predictor has already seen** — i.e. it behaves like a
count/novelty proxy without needing a density model or forward-dynamics
model at all.

### 5.3 Practical details worth reusing (quoted, §2.4)

- **Reward normalization**: divide the intrinsic reward by a running
  estimate of the standard deviation of the intrinsic **returns** (not the
  raw reward), to keep the bonus on a consistent scale across environments/
  time.
- **Observation normalization**: whiten each input dimension using a running
  mean/std, clip to `[−5, 5]`, initialized by stepping a random policy for a
  warm-up period before training starts.
- **Non-episodic treatment** (§2.3): the intrinsic-reward stream is treated
  as non-episodic (never reset to 0 at "done") because curiosity value
  should reflect all future novelty reachable, not be truncated by an
  arbitrary episode boundary — directly relevant to a trading bot with no
  natural "episode end" other than session-day boundaries.

**Trading mapping.** RND is a **simpler, model-free alternative** to full
pseudo-counts for cold-start novelty (§8): featurize a `(strategy, regime)`
cell (or even the raw trade-feature vector) as `x`, run it through one fixed
random small MLP `f` and one trained predictor `f̂`, and use the MSE as a
novelty signal requiring zero density-model math. Given the trading state
space here is **tiny and already discrete** (a handful of strategies ×
4 regimes), a literal count `N(cell)` is simpler, exact, and fully
interpretable — RND's main advantage (scaling to huge/continuous observation
spaces like Atari pixels) is not needed here. It is flagged as available but
not the primary recommendation (§9).

---

## 6. Boredom / satiation — IAC's declining-interest mechanism

Directly from the IMS paper (already fetched, §1 above), IAC's own
terminology captures this precisely (§IV.A, p.269, quoted): *"adaptive
because the situations that are attractive change over time, indeed, once
something is learned, it will not provide learning progress anymore."* And
in §III.C (p.269, "Group 3" discussion): once a region's error rate has
plateaued near its noise floor, `⟨e_n(t+1)⟩ ≈ ⟨e_n(t+1−τ)⟩`, so `D(t+1) ≈ 0`
and `L(t+1) ≈ 0` — **the LP signal itself *is* the boredom signal**: it
decays to zero automatically as a region is mastered (or, symmetrically, as
a region is recognized as unlearnable noise), with no separate mechanism
needed. Baranes & Oudeyer's absolute-value-of-competence-progress (§2.2)
adds the complementary case: if a previously-mastered cell's competence
**degrades** (e.g. regime characteristics drift so a strategy that used to
work in "trending" stops working), `|interest_i|` rises again and re-attracts
exploration — this is the correct behavior for a live trading system where
"mastered" cells can go stale.

**Trading mapping — explicit boredom term for the engine.** Define a
per-cell **boredom multiplier** that decays exploration priority as a
function of *sustained* near-zero LP (not just low LP on one measurement,
to avoid an unlucky quiet window suppressing a cell prematurely):
```
boredom(cell) = exp( − κ · consecutive_windows_with_|LP| < LP_floor(cell) )
```
applied as a multiplicative discount on the cell's exploration priority
(§9), with `κ` tuned so a cell needs several consecutive near-zero-LP
windows (not one) before being meaningfully suppressed — and because
`|interest|`/`|LP|` is recomputed every new trade, a regime-drift-driven
competence drop automatically resets the boredom counter and revives
priority, exactly matching Baranes & Oudeyer's absolute-value rationale.

---

## 7. Bandit framing — LP-driven non-stationary multi-armed bandit

**Confirmed primary source (existence + abstract, A-grade — abstract text
fetched directly from NeurIPS proceedings; full PDF not accessible this
session):** M. Lopes, T. Lang, M. Toussaint, P-Y. Oudeyer, "Exploration in
Model-based Reinforcement Learning by Empirically Estimating Learning
Progress," NeurIPS 2012.
https://proceedings.neurips.cc/paper_files/paper/2012/hash/a0a080f42e6f13b3a2df133f073095dd-Abstract.html

Quoted abstract: *"Formal exploration approaches in model-based reinforcement
learning estimate the accuracy of the currently learned model without
consideration of the empirical prediction error. ... We propose extensions
[to PAC-MDP/Bayesian approaches] which drive exploration solely based on
empirical estimates of the learner's accuracy and learning progress... We
then provide experimental studies demonstrating the robustness of these
exploration measures in cases of non-stationary environments."* This
confirms the paper exists, is by exactly the right authors, and is precisely
about empirically-estimated learning progress driving exploration robustly
under non-stationarity (relevant here: market regimes and strategy edges
*are* non-stationary). **However, the abstract text alone does not contain
the exact bandit selection-rule equation** — I attempted to fetch the
related Lopes/Clément/Roy/Oudeyer ZPDES-family paper
(hal.science/hal-00926304) for the explicit softmax/UCB formula but it was
blocked by the host's bot-protection (Anubis, "Access Denied"), and
WebSearch quota was already exhausted so no alternate mirror could be
located this session. **This is flagged as unverified at the
exact-equation level** — I am not able to quote Lopes & Oudeyer's specific
bandit-selection formula verbatim in this pass.

**What I can respons­ibly ground the "LP-bandit" design template in instead
(A-grade, standard non-stationary bandit theory, Sutton & Barto, *Reinforcement
Learning: An Introduction*, 2nd ed., §2.5 "Tracking a Nonstationary Problem"
— not fetched this pass but standard, stable, decades-old textbook material,
not time-sensitive):** for a reward signal that drifts over time (exactly
what per-cell LP does — it rises while a cell is learnable-but-unlearned,
then decays as it's mastered), the standard fix is a **constant-step-size
exponential recency-weighted average** instead of a sample-mean average:
```
Q_{n+1}(arm) = Q_n(arm) + α · [ R_n(arm) − Q_n(arm) ],   0 < α ≤ 1
```
which weights recent rewards exponentially more than old ones — the correct
tracking estimator for a genuinely non-stationary reward, unlike a plain
running mean. Combined with the LP signal itself as `R_n(arm)`, this **is**
the LP-bandit construction: treat each `(strategy × regime)` cell as an arm,
its reward is that cell's most recent LP measurement, tracked with the
above exponential-recency update (this substitutes for, and is consistent
with, IAC's own sliding-window mean-of-means in Eq. 1/2 §1.3 — both are
recency-weighted smoothers of the same underlying error/LP curve), and the
arm is picked by a standard **softmax (Boltzmann)** over `Q_n(arm)`:
```
P(arm = c) = exp( Q_n(c) / T ) / Σ_{c'} exp( Q_n(c') / T )
```
with temperature `T` annealed down as total trade count grows (more
exploitation as the model matures), or an **ε-greedy** rule (IAC's own
choice, `ε ≈ 0.35`, §1.4) as the simpler alternative. **This softmax-over-LP
construction is my synthesis of two independently A-grade-sourced pieces
(Oudeyer's LP signal + Sutton & Barto's non-stationary-bandit tracking
estimator), explicitly not a verbatim equation from the Lopes et al. paper**
— flagged per the honesty requirement.

---

## 8. Cold-start reality check (≈1 session-day of history)

Being blunt, per the user's standing rule against overclaiming: with roughly
one trading day of closed trades, this is a **severe** small-sample regime
for every signal above.

- **LP is essentially unmeasurable at day 1.** IAC's own Eq. (1) needs two
  *disjoint* windows of `θ+1` (paper default 25) samples each just to form
  one derivative estimate — i.e. **≥ 50 trades in a single cell** before a
  single LP value means anything, and the paper's own `τ=15, θ=25` defaults
  were tuned for a robot doing hundreds of actions per "session," not an
  intraday bot that might produce single-digit trades per cell per day.
  With most cells at 0–5 trades, LP for those cells is **undefined, not
  small** — the honest state is "unknown," not "zero interest."
- **Count-based bonus degrades gracefully instead.** `β/√(N+1)` (§3.1, §3.3)
  is well-defined even at `N=0` (giving the maximum bonus `β`), monotonically
  decreasing and smoothly interpretable at every sample count including
  zero — this is precisely why it is the right **cold-start fallback**, not
  the primary signal: it correctly says "we know nothing about this cell,
  prioritize it," without requiring any derivative/history.
- **Recommended minimum-samples-before-LP-is-trusted gate:** do not let a
  cell's LP term influence its priority until it has **at least
  `2×MIN_WINDOW` closed trades** (`MIN_WINDOW` a config constant,
  recommend starting at 8–10 given intraday trade cadence rather than IAC's
  robotics-scale 25, and revisiting once real trade-count-per-day-per-cell
  data exists) — below that, priority is driven **entirely** by the
  count-based term (§9 formula, `N`-term weight forced to 1, LP-term weight
  forced to 0). This is an explicit, tunable, and honestly-labeled prior,
  not a claim that curiosity math "works" on day-1 data.
- **Per-cell vs. global data sparsity.** Because the state space here is
  small (few strategies × 4 regimes = a few dozen cells at most), the
  bottleneck is not "the state space is huge" (RND/pseudo-counts' target
  problem) but "each of a few dozen *known* cells individually has almost no
  data" — reinforcing §3.3/§5's conclusion that literal per-cell counts are
  sufficient and no density-model or random-network machinery is needed.
- **Session-date/regime imbalance is itself informative.** Because
  `market_regime` is mostly one value per `session_date` (per the user's own
  framing), the count-based term should be tracked **per (strategy, regime)
  cell**, not per (strategy, session_date) — otherwise a single trending
  day will look like "regime=trending is well-explored" even though only
  1–2 strategies were tried in it. Cells for regimes that have *never*
  occurred in the (short) history to date must default to the maximum
  cold-start bonus (`N=0`), which is the mechanism that will actually
  compel the bot to seek out and try strategies when a rare regime like
  "indecisive" finally shows up.

---

## 9. OSS sourcing pass (`sourcing-oss-parts`)

| Candidate | What it is | Verdict | Reason |
|---|---|---|---|
| `openai/random-network-distillation` (official RND repo) | Reference TF1 implementation of Burda et al. 2018, Atari-specific | **Reject** | Fetched directly: **archived April 2026, read-only, "no updates expected."** Research-reproduction code (`run_atari.py`, MPI/PPO scaffolding), not a general-purpose library; no license metadata visible. Not integratable as-is. |
| `pathak22/noreward-rl` (ICM, Pathak et al. 2017) | TensorFlow curiosity module (forward-dynamics prediction error) | **Reject** | Fetched directly: inactive (10 commits total), paper-specific research code for Doom/Mario, built on the (also unmaintained) `universe-starter-agent`. Also: ICM is forward-dynamics-prediction-error, i.e. Group-1/RND-family, not LP — wrong signal family for the primary recommendation anyway. |
| `rlberry-py/rlberry` | General Python RL research library (agents, benchmarking, hyperparameter search) | **Reject for this feature** | Fetched directly: MIT-licensed, actively developed (1,266 commits), but **contains no intrinsic-motivation/curiosity/count-based-exploration/RND module** per its own repo description. Not a match. |
| `Stable-Baselines-Team/stable-baselines3-contrib` | Experimental extensions to SB3 (QR-DQN, TRPO, CrossQ, etc.) | **Reject for this feature** | Fetched directly: MIT-licensed, active, but its listed algorithms (ARS, QR-DQN, MaskablePPO, RecurrentPPO, TQC, TRPO, CrossQ) are all full RL algorithms/policy wrappers, **none are exploration-bonus/curiosity modules**. Not a match. |
| Klyubin/Mohamed–Rezende empowerment reference code | — | **Not searched for / not applicable** | Per §4, empowerment is being explicitly rejected as a poor fit for this problem (no genuine action→future-market-state channel), so no OSS search was performed for it — would be wasted sourcing effort against a signal not being built. |

**Bottom line on sourcing:** every OSS candidate found is either (a) a
Deep-RL-scale exploration-bonus implementation built for continuous/pixel
observation spaces and gym-style environments (RND, ICM) — architecturally
mismatched to a small discrete `(strategy × regime)` cell table and,
critically, all **unmaintained/archived**, or (b) a general RL library
(rlberry, sb3-contrib) that simply does not implement curiosity/intrinsic
motivation at all. **A bespoke implementation over the existing closed-trade
experience memory is the right call** — the actual math involved (§1.3's
Eq. 1–2 windowed-mean-difference, §2.2's Eq. 1–2 competence-progress,
§3.1/3.3's `β/√N` bonus, §7's exponential-recency bandit tracker, and the
softmax/ε-greedy selection rule) is a few dozen lines of well-specified
arithmetic over a table already keyed by `(strategy_tag, market_regime)` —
there is no meaningful "puzzle piece" to import; the puzzle piece already
does not require external tensors, neural nets, or density models, unlike
every OSS candidate surveyed, all of which are neural-network-based and
therefore *heavier* than what this problem needs.

---

## 10. Recommended default design (exact update + selection equations)

**Primary signal: per-cell Learning Progress (IAC-style, §1.3), gated by a
minimum-sample threshold (§8), with count-based novelty as the cold-start
fallback (§3.1/3.3) and an explicit boredom decay (§6), combined via a
non-stationary LP-bandit softmax (§7).** Empowerment (§4) and RND (§5) are
explicitly **not** part of the default — noted as deferred/rejected with
reasons, per the user's standing rule to surface every rejection.

### 10.1 State: one record per cell `c = (strategy_tag, market_regime)`

```
trades[c]           : ordered list of closed trades routed to this cell
N[c]                : len(trades[c])                              (exact tabular count — §3.1/8)
err[c][k]           : calibration error of the k-th trade in this cell
                       = | predicted_win_probability_k − outcome_k |   (outcome_k ∈ {0,1})
Q_LP[c]             : exponential-recency-weighted LP estimate (§7), init 0
consec_bored[c]     : consecutive windows with |LP| below floor (§6), init 0
```

### 10.2 Update, on every newly closed trade routed to cell `c`

1. Append `err[c][N[c]]`; increment `N[c]`.
2. If `N[c] ≥ 2·MIN_WINDOW` (recommend `MIN_WINDOW = 8`, per §8, revisit once
   real per-day-per-cell trade counts are known), compute IAC's windowed LP
   (§1.3, Eq. 1–2, using `τ = θ = MIN_WINDOW` sized windows scaled to
   available data rather than the paper's robotics-scale 15/25):
   ```
   ⟨e⟩_recent = mean(err[c][ N[c]−MIN_WINDOW : N[c] ])
   ⟨e⟩_prior  = mean(err[c][ N[c]−2·MIN_WINDOW : N[c]−MIN_WINDOW ])
   LP[c]      = ⟨e⟩_prior − ⟨e⟩_recent        # positive = improving (Eq. 1/2, sign flipped to "higher=better")
   ```
   else `LP[c] = None` (untrusted — explicitly not zero, per §8).
3. Update the non-stationary bandit tracker (§7) only when `LP[c]` is
   trusted:
   ```
   Q_LP[c] ← Q_LP[c] + α · ( |LP[c]| − Q_LP[c]),   α = 0.3   # exponential recency-weighted average, Sutton&Barto §2.5
   ```
   (absolute value per Baranes & Oudeyer §2.2's rationale — both mastery-then-
   drift and fresh-improvement should raise priority.)
4. Update boredom (§6): if `|LP[c]| < LP_FLOOR` (config, e.g. `0.02`),
   `consec_bored[c] += 1`, else reset to 0.

### 10.3 Per-cell exploration priority (the engine's output)

```
novelty_bonus[c]   = β / sqrt(N[c] + 1)                       # §3.1/3.3, well-defined at N=0
boredom_mult[c]    = exp( −κ · consec_bored[c] )               # §6, κ = 0.15 default

if N[c] < 2·MIN_WINDOW:
    priority_raw[c] = novelty_bonus[c]                          # pure cold-start fallback (§8)
else:
    priority_raw[c] = ( w_LP · Q_LP[c] + w_N · novelty_bonus[c] ) · boredom_mult[c]
    # recommended defaults: w_LP = 0.7, w_N = 0.3 — LP dominant once trusted,
    # novelty kept as a permanent small floor so a cell already well-explored
    # but currently "bored" doesn't get zero weight forever (regime drift, §6)
```

### 10.4 Selection rule — LP-bandit softmax over cells (§7)

```
P(select cell = c) = exp( priority_raw[c] / T ) / Σ_{c'} exp( priority_raw[c'] / T )

T = T_0 · exp( −λ · total_trades_seen )     # anneal from exploration to exploitation
    T_0 = 1.0, λ chosen so T ≈ 0.3·T_0 after ~500 total closed trades (tune from real cadence)
```
This `P(c)` **is** the exploration-priority output the engine must publish
per `(strategy, regime)` cell — consumed downstream by whatever component
decides which strategy to greenlight for the next signal in a given detected
regime (a named queued consumer must exist per the user's no-orphaned-
features rule; this document does not implement that wiring, only the
engine's math and output contract).

### 10.5 What is explicitly NOT in the default, and why

- **No empowerment term** (§4) — no genuine action→future-market-state
  channel exists to measure; would be pure vocabulary-borrowing without
  substance.
- **No RND / neural random-network novelty** (§5) — the state space is a
  small discrete table; a literal count `N[c]` is exact, cheap, and fully
  interpretable where RND would add an unnecessary neural predictor/target
  pair and normalization machinery for no accuracy gain at this scale. Keep
  RND noted as a documented fallback **only if** the cell definition is
  later widened to a continuous feature vector (e.g. per-trade embeddings)
  rather than a discrete `(strategy, regime)` tuple — at that point RND's
  `‖f̂(x)−f(x)‖²` (§5.1) becomes the right tool again.
- **No pseudo-count density model** (§3.2) — same reasoning; that machinery
  exists specifically to generalize counts across a huge/continuous space
  and is unneeded overhead for a few dozen known cells.

---

## Confidence & caveats summary

| Claim | Grade | Basis |
|---|---|---|
| IAC LP formula (Eq. 1–2), region-splitting criterion, action-selection Eq. 3 | **A** | Full paper PDF fetched and read directly |
| SAGG-RIAC competence (Γ), competence-progress/interest (Eq. 1–2), mode-selection Eq. 3 | **A** | Full paper PDF fetched and read directly |
| Pseudo-count Eq. 1–2, Theorem 1, `β/√N` bonus form | **A** | Full paper PDF fetched and read directly |
| RND loss/reward formula, noisy-TV analysis, normalization details | **A** | Full paper PDF fetched and read directly |
| Empowerment variational bound (Mohamed & Rezende Eq. 2, 4–8) | **A** | Full paper PDF fetched and read directly |
| Klyubin 2005 original empowerment definition | **B** | Original PDF blocked (403); triangulated via Wikipedia + Mohamed–Rezende's own restatement, which agree |
| Lopes & Oudeyer 2012 paper's existence, authors, and thrust (non-stationary, empirical-LP-driven exploration) | **A** | NeurIPS abstract page fetched directly |
| Lopes & Oudeyer's/ZPDES's **exact** bandit selection-rule equation | **Unverified this pass** | hal.science host blocked the fetch (bot-protection); WebSearch quota exhausted before an alternate source could be located |
| The specific softmax/exponential-recency LP-bandit formula given in §7/§10 | **Synthesis, explicitly flagged** | Built from two A-grade sources (IAC's LP + Sutton & Barto's standard non-stationary-bandit tracking estimator), not a verbatim quote of the Lopes et al. equations |
| OSS repo maintenance status (RND archived, ICM inactive, rlberry/sb3-contrib lack curiosity modules) | **A** | Each repo's own GitHub/PyPI page fetched directly this session |

**What I did NOT cover:** the full Lopes/Clément/Roy/Oudeyer ZPDES paper's
exact equations (blocked, see above); Schmidhuber's separate "compression
progress" formalization (mentioned only as a citation inside Bellemare et
al.'s related-work, not independently fetched); any survey/meta-analysis
comparing these methods empirically in a finance-specific setting (none
found — WebSearch was unavailable for that sweep, and none of the fetched
sources address finance/trading applications directly, since none exist in
the robotics/RL-exploration literature surveyed).
