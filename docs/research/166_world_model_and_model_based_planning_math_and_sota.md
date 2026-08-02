# Trunk IX — Generative world-model + model-based planning: exact math + SOTA + OSS sourcing · research/166

Date: 2026-07-26. Rule D research pass for the NEXT two 🔴 Trunk IX PREDICTIVE-CORE branches: a real
**generative world-model of market-state DYNAMICS** and **model-based PLANNING** over it, producing a
decision-grade bias/veto on entries. Companion to the two branches already built:
`predictive_core/ensemble_world_model.py` (research/134; forecast ensembling + disagreement) and
`predictive_core/surprise_monitor.py` (research/134; Bayesian surprise + Page-Hinkley spike flag), and
to the prior sourcing pass `docs/research/133` (which rejected `pymdp` as a dependency for the surprise
monitor on the same grounds this pass re-derives independently below). Real web/GitHub/PyPI search and
primary-source fetches run this pass (`WebSearch` budget was exhausted for the session — noted
explicitly per source below; `WebFetch` on direct URLs + local `pip download`/GitHub-API checks used
instead, which is *more* reliable for exact formulas and library metadata than search snippets anyway).

## 0. Grounding: what already exists in this repo (read before designing)

- **Market regime** — `strategy_engine/session_strategy_regime_gate.py`: `MarketRegime = {TRENDING,
  RANGE_BOUND, INDECISIVE}` from a single ADX threshold rule (`classify_adx_market_regime`). This is
  the "regime" axis of the state; it is a **hard threshold rule today, not a learned/probabilistic
  regime model** — §3 below adds a learned regime layer as an optional upgrade, not a replacement (the
  ADX classifier's output is a fine, cheap regime LABEL either way).
- **Market breadth** — `market_data/market_breadth.py`: `MarketBreadthReport` (advance/decline,
  `breadth_pct`, cross-sectional `dispersion`) and `CrossMarketContext` — the "breadth" feature the
  prompt names is already computed, just not yet discretized into a state bucket.
- **Ensemble world-model** — `predictive_core/ensemble_world_model.py`: weighted-mean +
  weighted-stdev across per-mechanism win-probability forecasts → `disagreement` (model uncertainty).
  This is a **cross-sectional** (across mechanisms, same instant) uncertainty signal — complementary to,
  not a substitute for, the **temporal** (state → next-state) uncertainty this research pass is about.
- **Surprise monitor** — `predictive_core/surprise_monitor.py`: per-mechanism Bayesian surprise
  (`−log₂ p`) + a vendored Page-Hinkley change detector for a rising-surprise spike (world-model
  degrading). This is the right consumer to ALSO score the new transition model's calibration against,
  reusing `world_model_scoreboard.py` (research/95) rather than building a parallel scorer (Rule G).
- **Experience tagging** — `tests/test_memory_reflection/test_experience_memory_market_regime.py`
  confirms trades are already tagged with `market_regime`; `scripts/backfill_experience_market_regime.py`
  exists to backfill it. This is the substrate the new transition-count model reads: it needs
  `(state_t, action_t, state_{t+1}, reward_t)` tuples, and `state_t` already has a `market_regime`
  component available per trade.
- **statsmodels is already installed** (`0.14.6`, confirmed via `.venv`) but **not yet declared** in
  `pyproject.toml` — same undeclared-dependency gap research/133 flagged for scipy. It carries
  `statsmodels.tsa.regime_switching` (Hamilton-filter Markov-switching regression) out of the box —
  directly relevant to §1c/§5.

**Discretized state design used throughout this doc** (concrete, not abstract): start with the
SMALLEST state space that stays decision-relevant and only widen it as data volume justifies each added
dimension (§6 "thin-data honesty" makes this a hard rule, not a suggestion):

```
state = (regime: {trending, range_bound, indecisive},         # 3 — ADX gate, already built
         vol_bucket: {low, mid, high})                        # 3 — realized-vol/ATR tertile
# |S| = 9 for the v1 build. Optional later dimensions (only once each earns its data):
#   trend_sign: {up, flat, down}         (3×) — EMA-slope or +DI/−DI sign
#   breadth_bucket: {broad_up, narrow, broad_down}  (3×) — from market_breadth.py, already computed
# Full 4-factor space |S| = 81 — do NOT start there (see §6).
action = {enter_long, enter_short, hold, exit}                 # 4
```

---

## 1. Generative world-model families for a discrete/low-dim market state

### 1a. Tabular / count-based Markov transition model — the honest default

This is the estimator to build first: it is **exact** (no approximation beyond the discretization
itself), **tractable** (closed-form, no iterative fitting), and **honest with little data** (the
smoothing IS the uncertainty quantification).

**Counts.** Over the experience log, accumulate for every observed `(s, a, s′)` transition and reward:

```
N(s, a, s′)  = count of transitions from state s, action a, landing in state s′
N(s, a)      = Σ_{s′} N(s, a, s′)                    (total visits to (s,a))
Σ_reward(s,a) = sum of realized rewards observed from (s,a)
```

**Transition estimator — Dirichlet/Laplace smoothing.** The Categorical distribution `P(·|s,a)` over
next states has a Dirichlet conjugate prior `Dir(α₁,…,α_K)` where `K = |S|`; the posterior after
observing counts `N(s,a,·)` is `Dir(N(s,a,1)+α, …, N(s,a,K)+α)` (symmetric concentration `α`), whose
**posterior mean** is the point estimate to use for the next-state distribution:

```
P̂(s′|s,a) = ( N(s,a,s′) + α ) / ( N(s,a) + α·K )
```

- `α = 1` → **Laplace/add-one smoothing** (classic, conservative).
- `α = 0.5` → **Jeffreys prior** (minimum-information, often preferred for small counts — Krichevsky–
  Trofimov-style; standard recommendation in Bayesian categorical estimation, e.g. Gelman et al.,
  *Bayesian Data Analysis* ch. 3, and MacKay, *Information Theory, Inference, and Learning Algorithms*
  (2003) ch. 3 — canonical, stable textbook material, not independently re-fetched this pass since it is
  basic conjugate-prior algebra unchanged for decades).
- `α → 0` → the plain MLE `N(s,a,s′)/N(s,a)` (undefined/degenerate when `N(s,a)=0` — exactly the
  "1 regime observed" failure mode the prompt flags; `α>0` is what prevents that from ever being
  undefined, and also SHRINKS an untested cell toward the uniform prior `1/K` rather than an
  overconfident 100%-mass single-observation estimate).
- **Posterior is available in full, not just its mean** — `scipy.stats.dirichlet(alpha_vec)` (already a
  declared dependency, `scipy>=1.11`) gives `.mean()`, `.var()`, and `.rvs()` for **posterior-sampling**
  rollouts (§2c, §3's epistemic term) with zero new dependency.

**Reward estimator — shrinkage toward a global prior mean** (empirical-Bayes / Normal-Normal conjugate
mean, the same "don't trust a 2-observation average" logic applied to a continuous reward instead of a
categorical outcome):

```
R̂(s,a) = ( Σ_reward(s,a) + κ · R̄_global ) / ( N(s,a) + κ )
```

where `R̄_global` is the reward mean pooled across ALL states/actions (the "prior") and `κ` is a
pseudo-count controlling how hard to shrink toward it (large `κ` = trust the global average until a
cell has many observations; this is a James–Stein-flavored shrinkage estimator, standard in empirical
Bayes — Efron & Morris 1975 is the canonical reference for this shrinkage form).

**Confidence / effective sample size.** `N(s,a)` (or the Dirichlet's total concentration
`N(s,a)+αK`) IS the model's own calibrated confidence signal for that cell — §6 turns this directly
into the planner's confidence gate; no separate uncertainty model is needed for the tabular family.

### 1b. Linear-Gaussian state-space model (Kalman filter) — for continuous features

For a continuous latent (e.g. an underlying "trend strength" or "volatility intensity" the discretized
`vol_bucket`/`trend_sign` buckets are lossy quantizations of), the standard linear-Gaussian model and
its exact recursive predict/update equations (**verified verbatim against
[Wikipedia: Kalman filter](https://en.wikipedia.org/wiki/Kalman_filter)**, which states them in the
same notation Kálmán's 1960 paper and every textbook since use):

```
Process model:      x_k = F_k x_{k-1} + B_k u_k + w_k,     w_k ~ N(0, Q_k)
Observation model:   z_k = H_k x_k + v_k,                    v_k ~ N(0, R_k)

PREDICT:
  x̂_{k|k-1} = F_k x̂_{k-1|k-1} + B_k u_k
  P_{k|k-1} = F_k P_{k-1|k-1} F_kᵀ + Q_k

UPDATE:
  ỹ_k = z_k − H_k x̂_{k|k-1}                      (innovation / residual)
  S_k = H_k P_{k|k-1} H_kᵀ + R_k                  (innovation covariance)
  K_k = P_{k|k-1} H_kᵀ S_k^{-1}                    (optimal Kalman gain)
  x̂_{k|k} = x̂_{k|k-1} + K_k ỹ_k
  P_{k|k} = (I − K_k H_k) P_{k|k-1}
```

This is directly a **precision-weighted update** (§4): `K_k` is large exactly when the observation's
precision (`R_k^{-1}`) is high relative to the prior's precision (`P_{k|k-1}^{-1}`) — the Kalman filter
*is* the concrete, already-standard instance of the "inverse-variance weighting" the prompt asks about
in §4, not a separate mechanism. `P_{k|k}` is a calibrated variance usable directly as the
`vol_bucket`/`trend_sign` discretization's underlying continuous confidence.

### 1c. Hidden Markov / regime-switching (Baum-Welch) — the regime layer

Two legitimate, non-redundant Python paths exist (evaluated in the sourcing pass, §7):

- **`hmmlearn.GaussianHMM`** — pure sequence model: hidden regime `z_t ∈ {1..K}`, first-order Markov
  transition matrix `A` (`A_ij = P(z_t=j | z_{t-1}=i)`), Gaussian emissions
  `x_t | z_t=k ~ N(μ_k, Σ_k)`. Fit via **Baum-Welch** (the HMM-specific instance of EM):
  - **E-step** (forward-backward): `γ_t(k) = P(z_t=k | x_{1:T})`,
    `ξ_t(i,j) = P(z_t=i, z_{t+1}=j | x_{1:T})`.
  - **M-step**: `A_ij = Σ_t ξ_t(i,j) / Σ_t γ_t(i)`; `μ_k = Σ_t γ_t(k) x_t / Σ_t γ_t(k)`;
    `Σ_k` similarly weighted; `π_k = γ_1(k)`.
  - `hmmlearn`'s `.fit(X, lengths)` implements exactly this; `.predict()` gives the Viterbi-decoded
    most-likely regime path; `.transmat_`/`.means_`/`.covars_` expose the fitted parameters directly —
    genuinely not worth hand-rolling (forward-backward numerical stability, log-space scaling, is
    fiddly to get right).
  - Confirmed: BSD-3 license, PyPI `hmmlearn==0.3.3` ships a **manylinux2014 aarch64 wheel** (verified
    by `pip download` in this session — installs cleanly on this ARM64 box, no source build needed).
    GitHub last push 2024-10-31 (moderately maintained, not abandoned).
- **`statsmodels.tsa.regime_switching.markov_regression.MarkovRegression`** /
  `.markov_autoregression.MarkovAutoregression` — regime-switching **regression**:
  `y_t = α_{S_t} + x_tᵀβ_{S_t} + ε_t, ε_t ~ N(0, σ²_{S_t})` where `S_t` is the latent regime. Estimated
  via the **Hamilton filter** (forward recursion for `P(S_t | y_{1:t})`) + **Kim smoother** (backward
  smoothing for `P(S_t | y_{1:T})`) — citation confirmed directly from statsmodels' own docs: Kim &
  Nelson (1999), *State-Space Models with Regime Switching* (MIT Press) — the standard econometric
  regime-switching reference (Hamilton 1989 is the original model). **Already installed in this repo's
  `.venv` (`statsmodels==0.14.6`, confirmed), just undeclared in `pyproject.toml`.**
  - **Recommendation over hmmlearn for the "regime conditions the next-state/reward model" use case**:
    prefer `statsmodels.tsa.regime_switching` when the regime needs to condition an explicit
    regression (e.g. "expected next-bar return given the regime AND today's ADX/volatility features")
    — it is econometrically the more natural fit AND costs zero new dependencies. Use `hmmlearn` instead
    when the goal is pure **unsupervised clustering/decoding of a multivariate emission** (e.g. jointly
    decode `[return, realized_vol, breadth]` into a regime label without pre-specifying a regression
    form) — genuinely different jobs, not competing for the same slot.

### 1d. Neural sequence world-models (RSSM / PlaNet / Dreamer) — honest verdict: not justified now

**PlaNet** (Hafner et al. 2019, *"Learning Latent Dynamics for Planning from Pixels"*, arXiv:1811.04551,
ICML 2019) and **Dreamer** (Hafner et al. 2020, *"Dream to Control: Learning Behaviors by Latent
Imagination"*, arXiv:1912.01603, ICLR 2020 — fetched directly this pass) learn a **Recurrent
State-Space Model** (RSSM): a deterministic recurrent state `h_t = f(h_{t-1}, s_{t-1}, a_{t-1})` (GRU)
plus a stochastic latent `s_t`, with a prior `p(s_t|h_t)` and an encoder posterior `q(s_t|h_t,o_t)`
trained via an ELBO (reconstruction + KL(posterior‖prior)) end-to-end from **high-dimensional pixel
observations** — solving a problem (learning dynamics *from raw images*) this system does not have.
Dreamer/DreamerV3 (arXiv:2301.04104, 2023) are trained on **millions of environment steps per task**.

This system has, per the prompt, **~1 regime actually observed and limited bars per state** — a data
regime many orders of magnitude below what an RSSM needs to avoid memorizing noise. Two independent,
honest reasons to reject a neural world-model now, not just "it's heavier":
1. **Sample complexity mismatch** — an RSSM's inductive bias (deep recurrent nonlinearity) needs data
   volume to be constrained by; with a handful of regime-transitions observed, a linear-Gaussian/tabular
   model with explicit smoothing generalizes *better* out-of-sample precisely because it has far fewer
   free parameters and an explicit, auditable prior pulling it toward "don't know" when data is thin —
   the opposite of what an unregularized deep net defaults to.
2. **Auditability** — a "confidently wrong" neural latent state driving real capital is far harder to
   diagnose than a Dirichlet cell with `N(s,a)=3` (the tabular model's uncertainty is legible; an RSSM's
   is not, without a whole separate calibration apparatus).

**Verdict: reject for v1, explicitly revisit only if/when** bar-level (not session-level) history spans
enough regime CYCLES (multiple genuine trending/range-bound/indecisive periods per symbol, not one
session snapshot) that a walk-forward backtest can show an RSSM beats the tabular baseline
out-of-sample — never adopt it on architectural fashion alone. This mirrors the project's own Rule-P
bar ("real engines, not skeletons") pointed the other direction: the tabular/Kalman/HMM combination
above **is** the real, decision-grade engine for this data regime; a neural RSSM here would be
over-engineering relative to the data, not under-engineering.

---

## 2. Model-based planning / control

### 2a. Finite-horizon value iteration / dynamic programming (Bellman backup)

Over the learned MDP `(S, A, P̂, R̂)`, exact backward induction (Bellman 1957; standard treatment in
Sutton & Barto, *Reinforcement Learning: An Introduction*, 2nd ed., ch. 3–4; general form confirmed
against [Wikipedia: Bellman equation](https://en.wikipedia.org/wiki/Bellman_equation)):

```
Terminal boundary:   V_H(s) = 0            for all s        (or a bootstrap terminal value)

For h = H−1 downto 0, for every s ∈ S:
  Q_h(s, a) = R̂(s, a) + γ · Σ_{s′∈S} P̂(s′|s, a) · V_{h+1}(s′)      for every a ∈ A
  V_h(s)    = max_a Q_h(s, a)
  π_h(s)    = argmax_a Q_h(s, a)
```

`γ ∈ (0,1]` discounts across the planning horizon `H` (a handful of decision steps ahead —
e.g. the next 3–5 bars/decision points, not an infinite trading career). For the stationary
(infinite-horizon) form, the same backup iterated to convergence is a contraction mapping (Banach
fixed point since `γ<1`):
`V_{k+1}(s) = max_a [ R̂(s,a) + γ Σ_{s′} P̂(s′|s,a) V_k(s′) ]`.

**Tractability note (the actual selling point here):** with `|S| ≤ 81` (or 9 for the v1 state) and
`|A| = 4`, this backup is `O(|S|² · |A| · H)` — on the order of microseconds in pure numpy. **Exact
tabular value iteration needs no approximation at this scale** — CEM/MPC (§2b) and Monte-Carlo rollouts
(§2c) are the right tool only if the state space is later widened past exact-DP tractability (e.g. by
planning directly over continuous Kalman-filtered features instead of discretized buckets). Building
CEM machinery for a 9–81-state MDP would itself be the kind of unjustified complexity §1d warns against
for the world-model side — say this plainly rather than reaching for the fancier tool by default.

### 2b. Model Predictive Control (MPC) with CEM — the upgrade path, not the v1 default

**Cross-Entropy Method** (Rubinstein 1997, *"Optimization of Computer Simulation Models with Rare
Events"*, Eur. J. Operational Research; de Boer, Kroese, Mannor & Rubinstein 2005, *"A Tutorial on the
Cross-Entropy Method"*, Annals of Operations Research 134(1):19–67 — the standard tutorial reference;
Rubinstein & Kroese 2004 book). Confirmed generic form via
[Wikipedia: Cross-entropy method](https://en.wikipedia.org/wiki/Cross-entropy_method): sample from a
parameterized distribution, evaluate, refit the distribution's parameters via maximum likelihood over
the elite (top-`ρ`-quantile) samples, iterate. In model-based RL this is exactly the planner used by
**PETS** (Chua, Calandra, McAllister & Levine 2018, *"Deep Reinforcement Learning in a Handful of
Trials using Probabilistic Dynamics Models"*, arXiv:1805.12114, NeurIPS 2018 — fetched this pass:
combines an ensemble of probabilistic dynamics models with CEM trajectory sampling, reporting 8×–125×
better sample efficiency than SAC/PPO on continuous-control benchmarks) and by **PlaNet** (§1d) for
planning inside its learned latent space; **Dreamer** replaces CEM with a learned actor trained via
analytic value gradients through imagined rollouts — a further step only warranted once the model is a
differentiable neural net, which §1d already rejected here.

**CEM loop (pseudocode, directly implementable in numpy over the tabular/Kalman model)**:

```python
def cem_plan(state, world_model, horizon, n_samples, n_elite, n_iters, gamma):
    """Refine a distribution over ACTION SEQUENCES; return the first action (receding horizon)."""
    dist = init_categorical_action_dist(horizon)      # per-step P(action) over {long,short,hold,exit}
    for _ in range(n_iters):
        candidates = sample_action_sequences(dist, n_samples)         # shape (n_samples, horizon)
        returns = np.empty(n_samples)
        for i, seq in enumerate(candidates):
            s, total, discount = state, 0.0, 1.0
            for a in seq:
                total += discount * world_model.expected_reward(s, a)  # R̂(s,a)
                s = world_model.sample_next_state(s, a)                # ~ P̂(·|s,a)
                discount *= gamma
            returns[i] = total
        elite = candidates[np.argsort(returns)[-n_elite:]]
        dist = refit_categorical_mle(elite)            # M-step: per-step action-frequency in the elites
    return dist.mode(step=0)                            # execute step-0 action; replan next decision point
```

Note this is the **only** place CEM is needed relative to §2a's exact value iteration: when the action
*sequence* space or the *state* is not exhaustively enumerable. For this project's v1 scope (4 discrete
actions, ≤81 discrete states, short horizon) §2a's exact backup dominates CEM on both correctness (no
sampling noise) and speed — CEM is documented here as the justified upgrade path once/if the state
representation goes continuous, not as day-one machinery.

### 2c. Monte-Carlo rollouts for expected action value (and for propagating MODEL uncertainty)

```
Q_MC(s,a) = (1/M) Σ_{m=1}^{M} [ r₀^(m) + γ r₁^(m) + γ² r₂^(m) + … ]
```

each rollout `m` samples `s' ~ P̂(·|s,a)` then follows a rollout policy (greedy w.r.t. the current `V`
estimate, or random) for the remaining horizon. The variant that matters for this system: instead of
rolling out under the single point-estimate `P̂`, **sample a fresh transition matrix from the Dirichlet
posterior for each rollout** (`scipy.stats.dirichlet(N(s,a,·)+α).rvs()`) — a posterior-sampling /
Thompson-sampling-flavored rollout. The **variance of `Q_MC(s,a)` across posterior draws** is then a
direct, computable **epistemic uncertainty** number for that action — precisely the quantity §3's EFE
epistemic term needs, obtained for free from the same Dirichlet machinery §1a already set up (no
separate uncertainty model required). This is the exploration-vs-exploitation link the prompt asks
about in §3, made concrete and numpy-implementable.

---

## 3. Active inference / Expected Free Energy (EFE)

**Primary sources**: Da Costa, Friston, Parr, Sajid et al. 2020, *"Active inference on discrete
state-spaces: A synthesis"*, arXiv:2001.07203 (published *Journal of Mathematical Psychology*, 2020,
DOI 10.1016/j.jmp.2020.102447) — the canonical formal synthesis this section follows; Friston,
FitzGerald, Rigoli, Schwartenbeck & Pezzulo 2017, *"Active Inference: A Process Theory"*, Neural
Computation (the earlier, widely-cited process-theory formulation of the same math). **Flagged
honestly**: this session's `WebFetch` on the Da Costa arXiv abstract page and its `ar5iv` HTML render
both failed to surface the paper's literal equation numbers (abstract-only page / a conversion error on
the HTML mirror respectively) — the decomposition below is triangulated three ways instead of quoted
verbatim from that one paper: (1) it is the same two-term decomposition stated identically across a
decade of active-inference literature (Friston 2017 process theory, Parr & Friston 2019, Smith/Friston/
Whyte 2022 tutorial — all cite the identical form), (2) it is **structurally confirmed directly from
`pymdp`'s actual source** (`pymdp/control.py`, fetched verbatim this session — see below), which
implements exactly this decomposition in running code, and (3) it matches the author's existing
knowledge of extremely well-established, stable (non-time-sensitive) formal material. Treat the
equation below as **A-grade via source-code triangulation**, not as a direct verbatim quote of Da Costa
2020's equation numbering.

**Expected Free Energy of a policy π, summed over a planning horizon:**

```
G(π) = Σ_{τ=1}^{H} G(π, τ)

G(π, τ) = − E_{Q(o_τ|π)}[ ln P(o_τ) ]                                    (pragmatic / extrinsic value)
          − E_{Q(o_τ|π)}[ D_KL[ Q(s_τ|o_τ,π) ‖ Q(s_τ|π) ] ]              (epistemic / intrinsic value)
```

- **Pragmatic/extrinsic value**: expected log-preference over predicted outcomes under the policy — in
  a trading context, `P(o)` is instantiated as the preference distribution over reward/PnL outcomes
  (e.g. `P(o) ∝ exp(reward)` — "goal states" are profitable outcomes), so this term reduces to
  exactly `Σ_τ γ^τ R̂(s_τ,a_τ)`, i.e. the **same expected-reward quantity §2a's value iteration
  computes** — EFE's pragmatic term and classical MDP value are the same object under this
  instantiation.
- **Epistemic/intrinsic value**: expected information gain about hidden states from the outcome the
  policy would produce — i.e., how much visiting `(s,a)` is expected to *reduce uncertainty* about the
  world model itself. §2c's Dirichlet-posterior-variance-across-rollouts number is the tabular-model
  concrete instance of this term (and `pymdp`'s parameter-information-gain functions, below, are the
  same idea applied to model PARAMETERS rather than hidden states — a second, related epistemic term).

**Action selection** — softmax over policies with precision `γ` (confirmed structurally from `pymdp`
source, `pymdp/control.py`, fetched verbatim this session):

```python
# pymdp/control.py (verbatim structure, fetched this session):
#   neg_efe_all_policies = compute_expected_utility(...) + compute_info_gain(...) + ...
#   return nn.softmax(gamma * neg_efe_all_policies + log_stable(E)), neg_efe_all_policies
```

i.e. `P(π) = σ( γ · (−G(π)) + ln E(π) )` — `E(π)` is a prior over policies ("habits"), `γ` is the
precision (confidence) on the whole action-selection process, and the sign convention is: **more
negative `G(π)` (higher combined pragmatic+epistemic value) → higher selection probability.** `pymdp`'s
actual function names make the two-term decomposition unambiguous:
`compute_expected_utility` (pragmatic), `compute_info_gain` (epistemic, states),
`calc_negative_pA_info_gain` / `calc_negative_pB_info_gain` (epistemic, model PARAMETERS — "novelty" —
the Dirichlet-posterior analog of our own `N(s,a)`-based bonus).

**How this unifies exploration + exploitation**: an action with high expected reward (pragmatic) OR
high expected uncertainty-reduction (epistemic, i.e. a thinly-observed cell) both lower `G(π)` and raise
selection probability — the same score naturally trades off "go where the model says money is" against
"go where the model doesn't know yet, to find out." **This project deliberately does NOT want the
second half acted on with real capital** (see §6) — a genuinely novel, load-bearing design choice
relative to canonical active-inference agents (which are typically in a robotics/game setting where
information-seeking IS free or cheap): here the epistemic term is computed and reported, but is wired
only into the **confidence gate**, never into a live capital-allocating "let's go find out" action. This
divergence from the textbook agent is stated explicitly rather than silently — say so at build time too.

---

## 4. Precision weighting + hierarchical predictive layers (sibling branches)

**Precision weighting** = inverse-variance weighting of a prediction error: `precision Π = 1/σ²`;
updates scale with `Π·error` (Rao & Ballard 1999, *"Predictive coding in the visual cortex"*, Nature
Neuroscience — the founding predictive-coding formulation; Friston 2010, *"The free-energy principle: a
unified brain theory?"*, Nature Reviews Neuroscience; Feldman & Friston 2010, *"Attention, Uncertainty,
and Free-Energy"*, Frontiers in Human Neuroscience — precision as attentional gain. These are stable,
long-established, non-time-sensitive references drawn from existing knowledge; not independently
re-fetched this pass given the WebSearch budget exhaustion, flagged accordingly). **This project already
has three concrete, load-bearing instances of precision weighting, once §1–3 are built — worth naming
explicitly since the prompt calls these out as sibling branches to possibly light together**:

1. **The Kalman gain `K_k` (§1b) IS precision weighting**, verbatim: it up-weights the new observation
   exactly in proportion to its precision relative to the prior's.
2. **`ensemble_world_model.py`'s `disagreement`** (already built) is an inverse-precision signal in
   disguise — feed it into the planner's confidence gate `κ(s)` (§6) as an ADDITIONAL discount: high
   cross-mechanism disagreement should lower trust in the planner's action bias even when the
   transition-count `N(s,a)` alone looks sufficient. This is the concrete wiring between the two
   existing IX branches and the two new ones this doc specs.
3. **`surprise_monitor.py`'s Page-Hinkley spike flag** is a second, independent precision signal at the
   monitoring layer (falling calibration ⇒ effectively falling precision) — route a spike flag into the
   same confidence gate as a hard override (spike detected ⇒ `κ(s) = 0` regardless of `N(s,a)`,
   reusing rather than duplicating the existing detector, per Rule G).

**Hierarchical predictive layers**: the natural structure once both new pieces exist is genuinely
already two-level — the session-level regime (HMM/ADX, §1c, the slower "cause") sets the **prior**
(mean/variance) for the bar-level Kalman process noise `Q` (§1b, the faster layer) — classic
hierarchical predictive coding (Friston 2008, *"Hierarchical models in the brain"*, PLoS Computational
Biology; Clark 2013, *"Whatever next? Predictive brains, situated agents, and the future of cognitive
science"*, Behavioral and Brain Sciences — both stable, established references, not re-fetched this
session for the same budget reason, flagged). **Not required for the v1 build** — named here as the
explicit, already-mechanically-available extension point (top layer exists today as the ADX gate;
bottom layer is what §1b adds), not as scope creep to build now.

---

## 5. Thin-data honesty — keeping the world-model calibrated with ~1 regime observed

Every mechanism above already carries a thin-data safeguard; this section makes the composition
explicit as the actual gating pipeline a build must implement, in order:

1. **Smoothing is the uncertainty quantification, not a hack** — §1a's `α` and `κ` shrink every
   under-observed cell toward an agnostic prior (`1/K` for transitions, the global reward mean for
   reward) rather than ever reporting a spuriously confident estimate from 1–2 observations. This is
   the primary defense against "confidently wrong."
2. **Backoff smoothing across the regime hierarchy** (the direct answer to "~1 regime observed"): when
   `N(regime, vol_bucket, a)` is thin, back off to the **regime-marginal** table
   `P̂(s′|vol_bucket, a)` (pooled across regimes), and if THAT is also thin, back off further to the
   fully-marginal `P̂(s′|a)`. This is the same interpolated-backoff pattern classically used for sparse
   categorical count models (Katz 1987 backoff, standard in n-gram language modeling — the identical
   "smaller conditioning context has more data, larger context has more relevance" trade-off applies to
   a market state as much as to a word sequence). **Concretely: never let an unobserved `(regime, …)`
   combination default to a degenerate/undefined estimate — it must always resolve to SOME
   well-populated ancestor table.**
3. **Confidence gate `κ(s,a) = min(1, N(s,a) / N_full)`** (`N_full` a tunable "fully trust the model"
   threshold, e.g. 30–50 observed transitions) interpolates smoothly between "ignore the planner
   entirely" (`κ=0`, defers wholly to existing signals — the ML win-probability model, the ensemble
   forecast) and "trust the planner fully" (`κ=1`). **This is the mechanism that answers the prompt's
   "confidence gating so the planner defers to base signals when the model is uncertain" directly.**
   Additionally discount `κ` by `ensemble_world_model`'s `disagreement` and hard-zero it on a
   `surprise_monitor` spike (§4) — reuse, don't reimplement.
4. **Abstain ≠ veto — keep these semantically distinct in the output type.** A low-confidence cell
   should make the planner **abstain** (defer to the base signal, contribute nothing) — it must NOT
   silently become a confident-looking "veto" through some default-to-zero coding shortcut. A veto is
   only emitted when `κ(s,a)` is HIGH **and** `Q̂(s,a)` for the requested action is confidently negative
   relative to `hold`/`exit`. Collapsing these two states into one boolean is exactly how a thin-data
   model becomes "confidently wrong" by accident — call this out as a concrete implementation bug class
   to test against.
5. **Score the transition model's own calibration via the EXISTING scoreboard**
   (`paper_trading/world_model_scoreboard.py`, research/95) rather than a new parallel scorer (Rule G):
   feed the transition model's next-state predictions through the same prequential log-loss +
   `calibration_by_market_regime` machinery already built. A world-model whose predicted next-state
   distribution scores worse than a coin-flip/uniform baseline should have its planner output
   automatically suppressed (`κ_global` multiplier, on top of the per-cell `κ(s,a)`) — the honest
   circuit-breaker for "the whole model is bad right now," not just "this one cell is thin."
6. **Regularize toward UNIFORM, never toward a directional prior** — at initialization (zero
   observations anywhere), every `P̂(·|s,a)` must reduce to the uniform distribution over `s′`
   (`α`-only, no informative mean baked in) and `R̂(s,a)` to the pooled global reward mean — genuine
   agnosticism, not a disguised directional bet dressed as a "prior."

---

## 6. OSS sourcing pass (Rule D + `sourcing-oss-parts`) — every candidate evaluated on real evidence

**Note on method**: `WebSearch` was exhausted (200/200) for this session before this pass began — all
findings below come from direct `WebFetch` on known/derived URLs, GitHub's public REST API (commit
recency, star counts, archive status — queried directly via `curl`, not scraped from search), and
`pip download --no-deps` against the real PyPI index from inside this project's `.venv` on this actual
aarch64 box (i.e., install feasibility is **directly verified**, not inferred).

| # | Library | PyPI ver. checked | License | ARM64 install | Last GitHub push | Verdict |
|---|---|---|---|---|---|---|
| 1 | `hmmlearn` | 0.3.3 | BSD-3 | ✅ `manylinux2014_aarch64` wheel confirmed via direct `pip download` | 2024-10-31 | **Use** for pure sequence-clustering/Viterbi decoding of a multivariate Gaussian emission (§1c) |
| 2 | `statsmodels` (`tsa.regime_switching`) | 0.14.6 (**already installed**, undeclared) | BSD-3 | ✅ already present in `.venv` | n/a (mature stdlib-adjacent) | **Prefer** for regime-conditioned regression (§1c) — zero new dependency |
| 3 | `filterpy` | 1.4.5 | MIT | sdist only (pure Python+numpy/scipy, builds trivially) | 2024-02-07 (~2.5 yr stale) | **Reject as dependency — vendor the ~20-line formula instead** (§1b's equations are the whole class) |
| 4 | `pymdptoolbox` (`sawcordwell/pymdptoolbox`) | forever-`4.0-b3` | BSD-3 | sdist only | 2023-06-04 (~3 yr stale) | **Reject** — real & correct but stale, and our exact backup (§2a) is ~15 lines of numpy tightly coupled to the confidence-gating logic no generic toolbox anticipates |
| 5 | `inferactively-pymdp` (`pymdp`) | 1.0.3 | MIT | ✅ pure-Python wheel confirmed | **2026-07-24** (2 days before this research date — actively maintained) | **Reject as runtime dependency** (still requires `jax`, `jaxlib`, `equinox`, `mctx`, `networkx`, `matplotlib`, `seaborn` — confirmed via direct wheel-metadata inspection this session, same finding as research/133's independent prior check) — **adopt as reference** for the exact EFE formula/decomposition (§3), confirmed directly from its `control.py` source |
| 6 | `pomdp-py` (`h2r/pomdp-py`) | 1.3.5.1 | MIT | sdist only, needs a Cython build | 2025-10-28 (~9 mo, maintained) | **Reject — overkill machinery.** Built for POMCP/particle-filter planning over large/continuous POMDPs; this MDP is small enough for EXACT value iteration (§2a), no MCTS approximation warranted |
| 7 | `scipy.stats.dirichlet` / `.multinomial` | 1.18.0 (**already installed + declared**) | BSD-3 | ✅ already present | n/a | **Use directly** for Dirichlet posterior mean/var/`.rvs()` (§1a, §2c) — zero new dependency, real value-add over hand-rolled sampling |

**Rejections surfaced for double-check (Rule O)**: #3 `filterpy` and #4 `pymdptoolbox` are both real,
correctly-implemented libraries rejected purely on "the math is small enough to own directly and needs
tight coupling to bespoke confidence-gating logic no generic library anticipates" grounds, not on
quality — flag for the user in case a future slice's scope grows enough that owning the math directly
stops paying off (e.g. if the state space is later widened well past exact-DP tractability, revisit
`pymdptoolbox`; if multiple independent continuous-feature Kalman filters proliferate across the
codebase, revisit vendoring `filterpy` properly instead of re-deriving the ~20 lines each time). #5
`inferactively-pymdp` is rejected as a dependency for the SECOND time on this exact project (research/133
made the same call for the surprise monitor) — the jax-stack weight argument generalizes across both
consumers; flagging in case the project ever does want a full POMDP/continuous-latent active-inference
agent for a *different*, harder problem where the jax stack would actually earn its keep.

---

## 7. Recommended concrete default design (v1 build)

1. **World-model = tabular/count-based transition model** (§1a) over the 9-state (v1) →
   up-to-81-state (later) discretized market state, with **Dirichlet(α=0.5, Jeffreys) smoothing** for
   `P̂(s′|s,a)` and **empirical-Bayes shrinkage** for `R̂(s,a)`, plus **regime→marginal backoff** (§6.2)
   for any thin cell. Regime label sourced from the existing ADX gate now; `statsmodels.tsa.
   regime_switching.MarkovRegression` (already installed, zero new dependency) is the recommended
   upgrade path to a learned/probabilistic regime layer, kept as a named next step rather than built
   today (Rule K: track, don't silently build extra scope this pass).
2. **Planner = exact finite-horizon value iteration** (§2a) over that tabular MDP, `H≈3–5` decision
   steps — no CEM/MC-rollout machinery needed at this scale; §2b/§2c documented explicitly as the
   upgrade path if/when the state goes continuous, not built now.
3. **Action score = EFE-shaped** (§3): pragmatic term = `Q̂(s,a)` from step 2 (the primary, load-bearing
   term); epistemic term = Dirichlet-posterior-variance-across-rollouts (§2c) or the simpler
   `1/(N(s,a)+αK)` proxy — **used only to compute the confidence gate, never as an active
   information-seeking drive that risks capital** (§3's explicit, stated divergence from canonical
   active-inference agents).
4. **Confidence-gated output type** — a `PlanningSignal` with `action_scores: dict[str,float]`,
   `confidence: float` (`κ(s,a)` discounted by `ensemble_world_model.disagreement` and hard-zeroed on a
   `surprise_monitor` Page-Hinkley spike, §4/§6), and an explicit `abstain: bool` vs `veto: bool`
   distinction (§6.4) — never collapsed into one flag.
5. **Verification** — hermetic (Rule J) over constructed transition counts (known-answer Dirichlet/VI
   checks), then real-data (Rule F) against the actual SQLite bar history + trade-experience log, scored
   through the EXISTING `world_model_scoreboard.py` (research/95) prequential/regime-resolution
   machinery rather than a new parallel scorer (Rule G) — a transition model that scores worse than a
   uniform-baseline should auto-suppress its own planner output (§6.5).
6. **No new runtime dependency required for the v1 default** beyond declaring the already-installed
   `statsmodels` and `scipy` explicitly in `pyproject.toml` (both currently undeclared-but-present, a
   pre-existing gap this pass surfaces again). `hmmlearn` is the one genuinely new, justified,
   ARM64-verified dependency to add **only when/if** the regime layer moves from the ADX rule to a
   learned multivariate-emission HMM.

## Sources

**Fetched/verified directly this session** (WebFetch content, GitHub API, or local `pip download` against the
real PyPI index — all graded A/B, dated 2026-07-26):
- https://en.wikipedia.org/wiki/Kalman_filter — predict/update equations (§1b)
- https://en.wikipedia.org/wiki/Bellman_equation — value-iteration/Bellman-optimality form (§2a)
- https://en.wikipedia.org/wiki/Cross-entropy_method — generic CEM algorithm + Rubinstein/de Boer citations (§2b)
- https://hmmlearn.readthedocs.io/en/latest/ — hmmlearn docs, BSD license confirmed (§1c)
- https://www.statsmodels.org/stable/generated/statsmodels.tsa.regime_switching.markov_regression.MarkovRegression.html — Hamilton/Kim citation (§1c)
- https://arxiv.org/abs/1805.12114 (Chua et al., PETS, NeurIPS 2018) — CEM in model-based RL (§2b)
- https://arxiv.org/abs/1912.01603 (Hafner et al., Dreamer, ICLR 2020) — RSSM data requirements (§1d)
- https://raw.githubusercontent.com/infer-actively/pymdp/master/pymdp/control.py — EFE decomposition + softmax policy-selection code, verbatim (§3)
- https://github.com/sawcordwell/pymdptoolbox, https://github.com/rlabbe/filterpy, https://github.com/hmmlearn/hmmlearn, https://github.com/infer-actively/pymdp, https://github.com/h2r/pomdp-py — GitHub API `pushed_at`/`stargazers_count`/`archived` fields, queried directly (§7 table)
- `pip download --no-deps` against real PyPI for `hmmlearn`, `filterpy`, `inferactively-pymdp`, `pymdptoolbox`, `pomdp-py` from this project's `.venv` on this actual aarch64 host — install feasibility directly verified, not inferred (§7)
- Local repo inspection: `predictive_core/ensemble_world_model.py`, `predictive_core/surprise_monitor.py`, `strategy_engine/session_strategy_regime_gate.py`, `market_data/market_breadth.py`, `paper_trading/world_model_scoreboard.py`, `docs/research/133`, `docs/research/108`, `.venv` package versions

**Cited from stable, well-established, non-time-sensitive prior knowledge** (WebSearch was exhausted
mid-session — these are foundational, decades-old-to-2020 formal references that do not change over
time; flagged here explicitly rather than silently presented as freshly verified, per the deep-research
skill's honesty rule):
- Da Costa, Friston, Parr, Sajid et al. 2020, "Active inference on discrete state-spaces: A synthesis," arXiv:2001.07203 / J. Math. Psychology 2020 (§3 — decomposition triangulated via pymdp source, not quoted verbatim from this paper directly)
- Friston, FitzGerald, Rigoli, Schwartenbeck & Pezzulo 2017, "Active Inference: A Process Theory," Neural Computation (§3)
- Bellman, R. 1957, *Dynamic Programming*, Princeton University Press (§2a)
- Sutton, R. & Barto, A. 2018, *Reinforcement Learning: An Introduction*, 2nd ed., ch. 3–4 (§2a)
- Rubinstein, R.Y. 1997, "Optimization of Computer Simulation Models with Rare Events," Eur. J. Op. Res.; de Boer, Kroese, Mannor & Rubinstein 2005, "A Tutorial on the Cross-Entropy Method," Annals of Op. Res. 134(1):19–67 (§2b)
- Hafner et al. 2019, "Learning Latent Dynamics for Planning from Pixels" (PlaNet), arXiv:1811.04551, ICML 2019; Hafner et al. 2023, "Mastering Diverse Domains through World Models" (DreamerV3), arXiv:2301.04104 (§1d/§2b)
- Kim, C.-J. & Nelson, C.R. 1999, *State-Space Models with Regime Switching*, MIT Press; Hamilton, J.D. 1989, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle," Econometrica (§1c)
- Katz, S. 1987, "Estimation of probabilities from sparse data for the language model component of a speech recognizer," IEEE Trans. ASSP (backoff smoothing analogy, §6)
- Efron, B. & Morris, C. 1975, "Data Analysis Using Stein's Estimator and its Generalizations," JASA (shrinkage form, §1a)
- Gelman, A. et al., *Bayesian Data Analysis*, ch. 3; MacKay, D., *Information Theory, Inference, and Learning Algorithms* (2003), ch. 3 (Dirichlet-categorical conjugacy, §1a)
- Rao, R.P.N. & Ballard, D.H. 1999, "Predictive coding in the visual cortex," Nature Neuroscience; Friston, K. 2010, "The free-energy principle: a unified brain theory?," Nature Reviews Neuroscience; Feldman, H. & Friston, K. 2010, "Attention, Uncertainty, and Free-Energy," Frontiers in Human Neuroscience; Friston, K. 2008, "Hierarchical models in the brain," PLoS Comp. Bio.; Clark, A. 2013, "Whatever next? Predictive brains, situated agents, and the future of cognitive science," Behavioral and Brain Sciences (§4)
- Strehl, A.L. & Littman, M.L. 2008, "An analysis of model-based interval estimation for Markov decision processes," J. Computer and System Sciences (count-based exploration-bonus parallel, §3)

## What this pass did NOT cover (explicit, per the skill's completeness rule)

- Did not independently re-derive/quote Da Costa 2020's literal equation numbers (both direct fetch
  attempts failed to surface rendered LaTeX) — mitigated via source-code triangulation (§3), flagged
  rather than silently presented as a verbatim quote.
- Did not benchmark `hmmlearn` vs `statsmodels.tsa.regime_switching` empirically on this project's real
  bar data — the recommendation in §7 is architectural (which job each is naturally shaped for), not a
  measured accuracy comparison; that belongs in the eventual build's Rule-F real-data verification pass.
- Did not investigate GPU/JAX-accelerated alternatives beyond `pymdp` itself (e.g. `blackjax`,
  `numpyro`) since the whole point of §1d/§7 is that this data regime doesn't warrant that class of tool
  at all — named here so the scope-cut is explicit rather than silent.
- `WebSearch` (discovery-by-query) was unavailable for the entire pass (budget exhausted before this
  task began) — every source above was reached by direct URL/API construction from known primary
  sources, GitHub's REST API, and local package-index queries instead. This is noted as a real
  methodology constraint, not glossed over.
