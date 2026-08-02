# Self-Healing Supervision & Actuation Engineering — the ACTUATOR half of a component-lifecycle homeostat

Research date: 2026-07-27. Scope: the part of a "component-lifecycle homeostat" that actually
PERFORMS autonomous repair (detect a dead/degraded component → decide → act → verify), grounded
against five real prior-art traditions (Erlang/OTP, Kubernetes, Hystrix/resilience4j, AWS retry
engineering, IBM autonomic computing) plus real OSS Python libraries, and mapped explicitly onto
the verified substrate of this repo's `LivePaperTradingService`.

**Verification method**: `WebSearch` was available for this session (no quota exhaustion) and was
used throughout. Primary vendor/foundation documentation (erlang.org, kubernetes.io, resilience4j
readme, AWS Architecture Blog, envoyproxy.io) was fetched directly with `WebFetch` and quoted. Two
primary sources could **not** be fetched directly — flagged explicitly in §9, not silently assumed.
The project's own substrate claims were re-verified by grepping the actual running source
(`src/nse_algo_trader/dashboard/live_paper_trading_service.py`), not taken from the task prompt on
faith — the real file backs every substrate claim in §1 with a line number.

Source grading used below: **[A-primary, fetched]** = the actual vendor doc/source was fetched and
quoted in this session. **[B-secondary]** = corroborated by multiple independent secondary sources
but the primary text could not be fetched this session (see §9).

---

## 0. Bottom line

**Architecture: MAPE-K as the top-level control loop, built as a level-triggered reconciler (à la
Kubernetes controllers), with an Erlang/OTP-style child-spec + restart-intensity supervisor as the
Execute-stage actuator for in-process threads/cadences, resilience4j-style circuit breakers wrapping
every external-dependency call site (already half-present as the LLM cooldown pool — generalize it),
and AWS-style full-jitter exponential backoff + a gRPC/Envoy-style retry budget for every retry path.**
Every autonomous action is bounded by an explicit action budget (OTP's MaxR/MaxT, generalized past
process-restart to any repair action) and a blast-radius ceiling, with dry-run/plan-then-apply and
human escalation above a severity threshold (Google SRE automation-chapter practice, §6).

Libraries to integrate: **`pybreaker`** (circuit breaker, thread-safe, BSD, actively released 2025),
**`tenacity`** (retry/backoff with jitter, actively maintained, Apache-2.0), **`APScheduler`**
(replaces the hand-listed `_maybe_run_*` cadence list with real trigger objects + misfire policy),
**`psutil`** (real process/thread/resource telemetry — the Monitor stage's sensor), **`prometheus_client`**
(in-process metrics registry — the Knowledge stage's time-series substrate, scraped by the existing
dashboard, no external Prometheus server required). Rejected: `circuitbreaker` (fabfuel — thinner,
no half-open trial-permit counting, superseded in capability by pybreaker), `aiobreaker`/`purgatory`
(asyncio-only surface, this codebase is thread-based, not asyncio), `backoff` (unmaintained since
Oct 2022, tenacity is its acknowledged successor), `stamina` (a good opinionated wrapper but adds a
dependency on top of tenacity for marginal ergonomics — take tenacity directly), `py-healthcheck`
(Flask/Tornado HTTP-endpoint framing does not fit an in-process supervisor's needs; build the
health-aggregation struct directly on top of psutil + prometheus_client), `schedule` (weaker than
APScheduler — no misfire/coalesce policy, no persistent job store, string-DSL only), `supervisor`/
`circus` (both manage separate OS **processes** via config files/RPC daemons — wrong unit for
supervising **threads inside one already-running process**; their design principles are copied, not
their code — see §7).

---

## 1. Verified substrate (re-checked against the real running source, not the task prompt)

Grepped directly in `src/nse_algo_trader/dashboard/live_paper_trading_service.py`:

- **One `_run_forever()` loop** (line 928) drives everything. It is wrapped in **one outer
  `try/except Exception as loop_error: print(...); traceback.print_exc()` that swallows any single
  pass's failure and sleeps `self._scan_interval_seconds` before retrying (lines 931, 986–997).
  This is edge-triggered, not level-triggered: if `_advance_one_pass` or any `_maybe_run_*` inside
  the try body raises, that ONE pass is abandoned and printed to stdout, but nothing tracks whether
  the SAME thing keeps failing pass after pass — no restart-intensity limiter, no escalation.
- **37 distinct `_maybe_run_*` cadence methods**, called sequentially from inside that one try body
  (e.g. lines 948–984: `_maybe_run_strategic_reflection`, `_maybe_run_thesis_debate_risk_check`,
  … through `_maybe_run_global_workspace`). Each one is ALSO individually wrapped in its own
  `try: ... except Exception: pass` (confirmed at line ~2884 inside
  `_maybe_run_strategic_reflection`: `except Exception: pass  # never let LLM/network trouble
  disturb the loop`). **This is double-swallowing**: a failure inside a `_maybe_run_*` never even
  reaches the outer loop's `except`, so it is never printed, counted, or surfaced anywhere — the
  cadence method silently no-ops for that pass and tries again next pass. There is currently no
  failure counter, no cooldown, no dashboard signal that a given cadence has been silently failing
  for hours.
- **6 background daemon threads** spawned ad hoc with `threading.Thread(..., daemon=True)`
  (`_writer_thread` lines 537/567, `_high_fidelity_replay_builder_thread` line 579,
  `news-acquisition-ladder` line 3755, `nse-exchange-filings` line 3793,
  `win-probability-engine` line 4292).
- **`is_alive()` appears exactly 3 times** (lines 3725, 3767, 4247), and in every case it gates a
  **re-entrancy check** ("don't start a second news-acquisition thread while one is still running")
  — never a liveness check that triggers a restart. If one of these threads dies mid-run from an
  unhandled exception, `is_alive()` returns `False` and the NEXT scheduled cadence pass simply
  starts a fresh thread — which happens to look like self-healing by accident for these three, but
  only because their cadence check is `if not alive: start`. There is no watchdog, no restart
  counter, no distinction between "finished normally" and "crashed," and the writer thread and
  replay-builder thread (spawned without any such guard) have no revival path at all if they die.
- **Only process-level supervision**: `deploy/nse-dashboard.service` is a systemd unit with
  `Restart=always` / `RestartSec=5` and no liveness probe of its own (systemd just watches whether
  the PID exits) — the OS-level equivalent of an OTP top supervisor with intensity effectively
  unbounded (systemd's own default `StartLimitIntervalSec`/`StartLimitBurst` are not set in this
  unit, so there is no OTP-style "give up after N restarts in T seconds" ceiling at all today).
- **One real circuit-breaker-shaped mechanism already exists**:
  `SwappableMultiProviderLlmClient` (`src/nse_algo_trader/llm_strategy/swappable_multi_provider_llm_client.py`)
  keeps a `_ProviderRuntimeState.cooldown_until` per LLM provider; on `LlmRateLimitError` it sets a
  90 s cooldown (`_DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS`), on other provider errors a 20 s cooldown
  (`_DEFAULT_FAULT_COOLDOWN_SECONDS`), and skips any provider still cooling down before trying the
  next. This is a hand-rolled, single-provider-class-scoped version of exactly the OPEN-state
  behavior described in §4 below — it has no failure-RATE threshold (any single failure opens it),
  no HALF_OPEN trial-permit counting, and no sliding window; it is a good instinct that should be
  generalized into the real primitive rather than re-invented per subsystem.

This substrate maps cleanly onto the "gap" the rest of this document addresses: **there is a
Monitor-ish signal (prints, `is_alive()`) and an Execute-ish signal (thread respawn on next cadence)
already present by convention, but no Analyze stage (failure-rate tracking, restart-intensity
counting), no Plan stage (deciding restart vs. escalate vs. give up), and no Knowledge store (no
persisted history of what has been failing and how often).**

---

## 2. Erlang/OTP supervision trees — the precise semantics to copy

**[A-primary, fetched]** erlang.org, *Supervisor Behaviour* —
https://www.erlang.org/doc/system/sup_princ.html

### 2.1 Restart strategies
- **`one_for_one`**: "If a child process terminates, only that process is restarted." (default)
- **`one_for_all`**: "If a child process terminates, all remaining child processes are terminated.
  Subsequently, all child processes, including the terminated one, are restarted."
- **`rest_for_one`**: "If a child process terminates, the child processes after the terminated
  process in start order are terminated. Subsequently, the terminated child process and the
  remaining child processes are restarted."
- **`simple_one_for_one`**: a simplified `one_for_one` where all children are dynamically-spawned
  instances of the *same* process type (no static child list at init; children are added at runtime
  via `supervisor:start_child/2`).

### 2.2 Child specification fields
| Field | Values | Default | Meaning |
|---|---|---|---|
| `id` | term | — (mandatory) | internal identifier |
| `start` | `{Module, Function, Args}` | — (mandatory) | how to spawn the child |
| `restart` | `permanent` / `transient` / `temporary` | `permanent` | when to restart |
| `shutdown` | `brutal_kill` / timeout(ms) / `infinity` | 5000 ms workers, `infinity` supervisors | how to stop |
| `type` | `worker` / `supervisor` | `worker` | tree shape |
| `modules` | `[Module]` / `dynamic` | `[M]` from `start` | hot-code-reload hint |

- **`permanent`**: "always restarted."
- **`transient`**: "restarted only if it terminates abnormally, that is, with an exit reason other
  than `normal`, `shutdown`, or `{shutdown, Term}`."
- **`temporary`**: "never restarted (not even when the supervisor restart strategy is `rest_for_one`
  or `one_for_all`)."
- **`brutal_kill`**: unconditional `kill` signal, no grace period.
- A finite `shutdown` timeout: supervisor sends the shutdown signal, waits that long, then kills.
- **`infinity`** (recommended for supervisor children): unbounded cleanup time — but the doc warns
  this "can cause a race condition where the child in question unlinks its own children, but fails
  to terminate them before it is killed" if misused on a non-supervisor child.

### 2.3 Restart intensity/period — the MaxR/MaxT limiter (the single most important primitive)
> "To prevent a supervisor from getting into an infinite loop of child process terminations and
> restarts, a maximum restart intensity is defined using two integer values specified with keys
> `intensity` and `period`... if more than MaxR restarts occur within MaxT seconds, the supervisor
> terminates all the child processes and then itself." Defaults: **MaxR = 1, MaxT = 5 seconds** —
> "1 restart per 5 seconds" if unspecified. `SupFlags = #{intensity => MaxR, period => MaxT, ...}`.

Crucially, this is **not** "1 restart total" — it's a **sliding count over a sliding time window**,
which is exactly the same shape as resilience4j's sliding-window failure-rate gate in §4. And in a
multi-level supervision tree, "the total number of restarts (before the top-level supervisor gives
up and terminates the application) will be the product of the intensity values of all the
supervisors" — i.e. nested supervisors compound their budgets, giving deeper trees more total
resilience before a full-application give-up, but each LEVEL still enforces its own local ceiling
first (which is why `one_for_one` at a leaf level contains a flapping child instead of always
escalating all the way to the top).

### 2.4 "Let it crash"
The philosophy is not "prevent crashes" but "assume crashes will happen, and make recovery cheap
and structural rather than defensive": a supervisor's job is "starting, stopping, and monitoring its
child processes... to keep its child processes alive by restarting them when necessary." Defensive
`try/except: pass` around every operation (this repo's current pattern) is the ANTI-pattern OTP
was designed to replace — it hides the crash instead of structurally recovering from it, so nothing
above the swallowing frame ever learns a fault occurred.

### 2.5 A faithful Python port for THREADS inside one process
There is no Erlang-style process isolation for Python threads (they share memory/GIL and an
uncaught exception in a thread just kills that thread silently unless you install
`threading.excepthook`). A faithful port therefore needs three things OTP gets "for free" from the
BEAM VM and that Python does NOT give you:
1. **An explicit child registry** (id → spec: target callable, args, restart policy, shutdown
   grace) — this repo's ad hoc `self._writer_thread = threading.Thread(...)` assignments are
   informal, unregistered child specs.
2. **A `threading.excepthook`-driven or watchdog-polled liveness signal**, since Python threads
   don't "link" to a supervisor the way BEAM processes do. A poll-based watchdog
   (`thread.is_alive()` on a fixed cadence, exactly the pattern already used 3× in this file, but
   generalized to ALL registered children and actually triggering respawn rather than only guarding
   re-entrancy) is the pragmatic equivalent of OTP's exit-signal-based supervision.
3. **A restart-intensity counter per child id** (a small ring buffer of restart timestamps, exactly
   MaxR-in-MaxT), so a thread that dies and gets respawned 10 times in 5 seconds trips the SAME
   "give up and escalate" behavior OTP gives a flapping process — today's substrate has ZERO such
   counter anywhere, so a permanently-crashing thread would be silently, infinitely re-spawned
   forever (or, for the 34 cadence methods with no restart at all, silently no-op forever).

`one_for_one` is the correct strategy for this repo's threads (writer, replay-builder,
news-acquisition, exchange-filings, win-probability are independent — one dying should not restart
the others). The `_run_forever` main loop itself plays the role of the ONE static child under
systemd's `Restart=always`, i.e. `one_for_one` at the OS-process level too, but with **no MaxR/MaxT
ceiling configured today** (`deploy/nse-dashboard.service` sets `Restart=always`/`RestartSec=5` and
nothing else — see §7's systemd gap noted for completeness, out of Python-library scope but worth
adding `StartLimitIntervalSec=`/`StartLimitBurst=` to the unit file as the outermost MaxR/MaxT ring).

---

## 3. Kubernetes controller/self-healing semantics

### 3.1 Probes — exact fields and defaults
**[A-primary, fetched]** kubernetes.io, *Liveness, Readiness, and Startup Probes* —
https://kubernetes.io/docs/concepts/workloads/pods/probes/ and
https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

| Field | Default | Meaning |
|---|---|---|
| `initialDelaySeconds` | 0 | delay after container start before first probe |
| `periodSeconds` | 10 | interval between probes |
| `timeoutSeconds` | 1 | probe must respond within this |
| `successThreshold` | 1 | consecutive successes to flip unhealthy→healthy |
| `failureThreshold` | 3 | consecutive failures to flip healthy→unhealthy |

- **Liveness probe failure** → kubelet **kills and restarts** the container (subject to
  `restartPolicy`). Purpose: detect unrecoverable in-process states (deadlock) that don't crash the
  process on their own.
- **Readiness probe failure** → the pod's IP is **removed from Service endpoints** (no traffic
  sent), the pod is NOT restarted. Purpose: temporarily unavailable ≠ dead.
- **Startup probe** exists so a slow-starting container isn't killed by an impatient liveness probe;
  it gates liveness/readiness until it first succeeds, then gets out of the way.
- With `periodSeconds=10` and `failureThreshold=3` (the stock defaults), Kubernetes waits **30
  seconds of consecutive failures** before acting — i.e. probes are themselves a small
  debounce/hysteresis filter, not an instant trigger, directly analogous to resilience4j's
  `minimumNumberOfCalls` gate in §4.

This maps onto our repo as: **liveness ≈ "is this thread/cadence still making forward progress"**
(currently: nothing checks this for 34 of 37 cadences and 3 of 6 threads have only an incidental
re-entrancy check), **readiness ≈ "should this component's output currently be trusted/consumed"**
(currently: absent entirely — a cadence that's degraded but not dead has no way to flag "don't act
on my output right now," which is exactly what an LLM provider cooldown *is* for the LLM pool
specifically, and what nothing else in the 37-cadence list has generically).

### 3.2 CrashLoopBackOff — the exact exponential-backoff algorithm
**[A-primary, fetched via source]** kubelet source (`pkg/kubelet/kubelet.go`,
`flowcontrol.NewBackOff`), corroborated by
https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ and
https://github.com/kubernetes/enhancements/issues/5734 (2025/2026 KEP proposing tunable decay):

- Standard configuration: **initial backoff 10 s**, **doubling** (10s → 20s → 40s → 80s → 160s →
  300s), **capped at `MaxContainerBackOff` = 300 s (5 min)**.
- **Reset condition**: once a container has run for **10 minutes** without a crash, the backoff
  timer resets to the 10 s floor.
- A 2025/2026 feature-gate (`ReduceDefaultCrashLoopBackOffDecay`, tracked in KEP/enhancement
  #5734) introduces a **reduced** profile: initial 1 s, cap 60 s — for faster local-dev iteration —
  confirming this exact base/cap pair is an intentionally tunable, not incidental, design choice.

This is the CANONICAL "restart with exponential backoff, capped, resettable-on-sustained-success"
shape our thread-watchdog and cadence-restart logic should copy verbatim: same doubling sequence,
same reset-after-sustained-health idea (our equivalent: a component that runs clean for N minutes
should have its failure counter zeroed, not carry a lifetime scar).

### 3.3 The reconciliation loop and why level-triggered beats edge-triggered for us
**[A-primary, fetched]** kubernetes.io, *Controllers* —
https://kubernetes.io/docs/concepts/architecture/controller/ — describes the control-loop metaphor
directly ("a control loop is a non-terminating loop that regulates the state of a system... the
controller(s) for that resource are responsible for making the current state come closer to that
desired state," using a thermostat analogy). The explicit level-vs-edge argument itself is best
sourced from a corroborating secondary explainer since kubernetes.io states the loop but not the
triggering-theory vocabulary by name:

**[B-secondary]**, cross-checked across multiple independent write-ups (James Bowes,
*Level Triggering and Reconciliation in Kubernetes*, https://medium.com/hackernoon/level-triggering-and-reconciliation-in-kubernetes-1f17fe30333d;
golinuxcloud's reconcile-loop explainer; Red Hat's Operator best-practices post): controllers are
driven by an event stream (watch notifications) but their **reconcile function is level-triggered,
not edge-triggered** — it always re-derives "what should exist" vs. "what exists" from current
state, and acts on the DIFF, regardless of which specific event woke it up (or whether it woke up
from a periodic resync rather than any event at all). The stated reason this matters: "if you are
edge triggered you run [the] risk of compromising your state and never being able to re-create the
state... level triggered... is very forgiving, and allows room for components not behaving as they
should to be rectified" — i.e. a MISSED event, a crashed controller that restarts later, or two
events collapsed into one, all self-heal on the NEXT reconcile pass because the reconciler never
trusted the event payload itself, only the fact that *something* changed and a fresh diff is due.

**Why this beats edge-triggered repair for our case specifically**: this repo's current pattern IS
edge-triggered by construction — each `_maybe_run_*` fires (or fails and swallows) exactly once per
pass based on "did the cadence interval elapse," with no separate reconciliation of "is the thing
this cadence is supposed to maintain actually in the state it should be in." If a `_maybe_run_*`
silently no-ops via its inner `except: pass` for 40 consecutive passes, nothing ever re-derives "the
strategic-reflection cache is now 40×`interval` stale, that's a DIFF from desired state, escalate."
A level-triggered supervisor instead asks, every tick, "what is the actual last-success timestamp
per child vs. the expected cadence — is there a diff, and how large," independent of whether any
particular pass's exception was individually caught. This is strictly more robust to the exact
failure mode already observed in the substrate (double-swallowed exceptions) because it does not
rely on the exception path being wired correctly at each of 37 call sites — it derives staleness
from state, not from being told about the failure.

### 3.4 PodDisruptionBudget — blast-radius ceiling
**[A-primary, fetched]** kubernetes.io, *Disruptions* —
https://kubernetes.io/docs/concepts/workloads/pods/disruptions/: "A PDB limits the number of Pods
of a replicated application that are down simultaneously from voluntary disruptions," via
`minAvailable`/`maxUnavailable`, and explicitly distinguishes **involuntary** disruptions (hardware
failure, kernel panic, network partition — "cannot be prevented by PDBs") from **voluntary** ones
(deliberate admin/owner action — "can be constrained by PDBs," with the caveat that directly
deleting a pod/deployment bypasses the PDB entirely). Mapped onto us: this is the "never repair more
than K of N independent things at once" ceiling our repair actuator needs before it, e.g., restarts
several `_maybe_run_*` cadences' backing state stores simultaneously because a shared root cause
(e.g. a disk-full condition) trips many failure counters in the same tick — the actuator must treat
"how many components am I about to act on in this single reconcile pass" as its own bounded
resource, not just each component's individual restart intensity.

### 3.5 Operator pattern
**[A-primary, fetched]** kubernetes.io, *Operator pattern* —
https://kubernetes.io/docs/concepts/extend-kubernetes/operator/: "Operators are software extensions
to Kubernetes that make use of custom resources to manage applications and their components...
[capturing] the key aim of a human operator who is managing a service... deep knowledge of how the
system ought to behave, how to deploy it, and how to react if there are problems," built on "the
control loop." This is the architectural justification for MAPE-K's Knowledge component in §5:
an operator's effectiveness comes from encoding the accumulated tribal knowledge of "what normal
looks like and what corrective action X situation calls for" as data/rules the control loop
consults, not as one-off imperative scripts.

---

## 4. Circuit breakers & bulkheads — resilience4j (Hystrix's maintained successor)

**[A-primary, fetched]** resilience4j.readme.io, *CircuitBreaker* —
https://resilience4j.readme.io/docs/circuitbreaker and *Bulkhead* —
https://resilience4j.readme.io/docs/bulkhead

### 4.1 State machine
Six states total; three "normal": **CLOSED → OPEN → HALF_OPEN**, plus three special-purpose:
`METRICS_ONLY` (always allow, record metrics, never opens), `DISABLED` (always allow, no metrics),
`FORCED_OPEN` (always deny with `CallNotPermittedException`, no metrics — the manual "break glass"
override).

- **CLOSED**: calls flow through; a ring-bit-buffer (0=success, 1=failure) records the sliding
  window; **CLOSED → OPEN** when failure rate ≥ threshold **OR** slow-call rate ≥ threshold.
- **OPEN**: all calls short-circuit immediately with `CallNotPermittedException` (no call attempted
  at all — this is the point: stop hammering a known-down dependency); after `waitDurationInOpenState`
  elapses, **OPEN → HALF_OPEN**.
- **HALF_OPEN**: a limited number of TRIAL calls (`permittedNumberOfCallsInHalfOpenState`) are let
  through to probe recovery; if failure/slow-call rate is still ≥ threshold → back to **OPEN**;
  if both are below threshold → **CLOSED**.

### 4.2 Exact default parameters (what real systems ship with)
| Parameter | Default |
|---|---|
| `failureRateThreshold` | 50% |
| `slowCallRateThreshold` | 100% |
| `slowCallDurationThreshold` | 60,000 ms |
| `slidingWindowType` | COUNT_BASED |
| `slidingWindowSize` | 100 |
| `minimumNumberOfCalls` | 100 |
| `waitDurationInOpenState` | 60,000 ms |
| `permittedNumberOfCallsInHalfOpenState` | 10 |
| `maxWaitDurationInHalfOpenState` | 0 (infinite) |
| `automaticTransitionFromOpenToHalfOpenEnabled` | `false` |

Count-based sliding window aggregates the last N calls; time-based aggregates the last N seconds —
count-based is the right choice for our low/irregular-frequency cadences (many run at most once/day
— a time window would rarely fill), matching what most of the 37 `_maybe_run_*` methods look like.

### 4.3 Bulkhead isolation
- **SemaphoreBulkhead** defaults: `maxConcurrentCalls = 25`, `maxWaitDuration = 0`.
- **ThreadPoolBulkhead** defaults: `coreThreadPoolSize = cores − 1`, `maxThreadPoolSize = cores`,
  `queueCapacity = 100`, `keepAliveDuration = 20 ms`.
- Purpose: cap how many CONCURRENT executions of a given call type are allowed, independent of
  circuit-breaker failure tracking — this is the "one misbehaving dependency shouldn't be able to
  exhaust the shared thread/connection pool and starve unrelated cadences" property. Directly
  relevant here: the 37 `_maybe_run_*` methods currently all run serially in one thread inside
  `_run_forever` (so bulkheading is trivially satisfied by construction — no two cadences ever run
  concurrently today), but the 6 ad hoc daemon threads have NO shared concurrency ceiling; a bulkhead
  around "how many background daemon threads may exist/spawn work simultaneously" prevents an
  incident (e.g. a burst of news-acquisition retries) from spawning unbounded threads.

### 4.4 Generalizing the repo's one real breaker-shaped thing
`SwappableMultiProviderLlmClient`'s per-provider cooldown (§1) should become a `pybreaker`-backed
CLOSED/OPEN/HALF_OPEN breaker per provider (and, more importantly, per EXTERNAL DEPENDENCY across the
whole system — Kite/Breeze API calls, NSE data downloads, Telegram ingestion, the news-acquisition
ladder) rather than the current single-failure-opens, no-half-open, no-sliding-window ad hoc version.

---

## 5. Retry/backoff correctness

### 5.1 Exponential backoff with jitter — exact formulas
**[A-primary, fetched]** AWS Architecture Blog, *Exponential Backoff And Jitter* —
https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

```
No jitter:            sleep = min(cap, base * 2**attempt)
Full Jitter:           sleep = random_between(0, min(cap, base * 2**attempt))
Equal Jitter:          temp  = min(cap, base * 2**attempt)
                       sleep = temp / 2 + random_between(0, temp / 2)
Decorrelated Jitter:   sleep = min(cap, random_between(base, sleep_prev * 3))
```

The article's own conclusion: **Full Jitter performs best overall** — it "uses less work" than
Equal Jitter for comparable end-to-end completion time, because it spreads retries across the widest
possible window rather than guaranteeing a minimum floor sleep that Equal Jitter always pays.
Decorrelated Jitter is competitive but adds implementation complexity (needs the previous sleep
value threaded through). Without jitter, synchronized clients retrying on the same schedule produce
"clusters of calls" (a thundering herd); jitter "spread[s] out the spikes to an approximately
constant rate" — this is the exact failure mode our current substrate is vulnerable to if multiple
`_maybe_run_*` cadences (or multiple LLM-pool cooldowns) happen to align on the same wall-clock
schedule and all retry in lockstep after a shared outage (e.g. a network blip taking out several
external calls in the same pass).

### 5.2 Retry budgets / token buckets — preventing retry storms
**[A-primary, fetched]** Envoy proxy docs, *Circuit breakers (proto)* —
https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto (RetryBudget
message): `budget_percent` (type `Percent`, **default 20%**) — "specifies the limit on concurrent
retries as a percentage of the sum of active requests and active pending requests"; `min_retry_concurrency`
(type `UInt32Value`, **default 3**) — "the limit on the number of active retries may never go below
this number," ensuring a low-traffic period still gets a small absolute retry allowance rather than
being rounded to zero by the percentage.

**[B-secondary]**, corroborated across gRPC's own retry-throttling docs and multiple independent
explainers: gRPC's client-side retry throttling uses a **token bucket** per server: `maxTokens`
(initial/ceiling token count) and `tokenRatio` (tokens credited per successful RPC); each retry
attempt spends a token, each SUCCESS credits `tokenRatio` tokens back; when the bucket falls below
**half of `maxTokens`**, further retries are paused until it recovers — an automatic backpressure
valve independent of, and complementary to, per-call exponential backoff. gRPC's declarative retry
policy fields: `maxAttempts`, `initialBackoff`, `maxBackoff`, `backoffMultiplier`,
`retryableStatusCodes`, with **±20% jitter** applied to the computed backoff by convention.

This maps onto us as: an exponential-backoff retry on a single failing call is necessary but NOT
sufficient — without a budget, 37 independently-retrying cadences (or N daemon threads each retrying
their own network call) can collectively re-create the exact retry storm backoff was meant to
prevent, just distributed across components instead of within one. The actuator needs a
process-wide retry-budget/token-bucket shared resource, not per-component-only backoff.

### 5.3 Idempotency is a precondition, not an optimization
Both the AWS article and gRPC/Envoy's retry-safety framing take as given that **only idempotent
operations may be auto-retried** without an explicit idempotency key/dedup mechanism — retrying a
non-idempotent action (e.g., placing an order) blind is a correctness bug, not a resilience feature.
For this repo specifically: retry logic in the actuator must be scoped to the KNOWN-idempotent
operations (re-reading market data, re-fetching a news page, re-computing a cached model output,
respawning a thread whose target function is itself idempotent-on-restart) and must NEVER be applied
generically to order-placement or position-mutating code paths without an explicit
idempotency-key/dedup layer that does not currently exist in the substrate — flagged here as a hard
boundary the actuator's design must respect, not something to "figure out later."

---

## 6. MAPE-K autonomic computing — the top-level architecture

**[B-secondary]** — IBM's original 2003/2005 white paper, *"An Architectural Blueprint for Autonomic
Computing,"* could not be fetched directly this session (no live IBM-hosted PDF found; see §9). The
architecture below is corroborated across multiple independent, mutually-consistent secondary
sources (ResearchGate figure captions of the original IBM diagram; the MAPE-K academic literature
survey chain, e.g. Bucchiarone et al., *A MAPE-K Approach to Autonomic Microservices*,
https://www.cs.unibo.it/~lanese/newpublications/fulltext/icsa-c2022-autonomic.pdf; and the
arxiv autonomic-architecture paper https://arxiv.org/pdf/2304.10503) which is standard practice for
citing this specific white paper in the self-adaptive-systems literature generally, since IBM's own
hosting of the original document has lapsed.

### 6.1 The five elements
- **Monitor**: sensors collect raw telemetry from the Managed Element.
- **Analyze**: correlates/interprets monitored data against the Knowledge base to detect a
  situation requiring action (this is exactly OTP's restart-intensity counter and resilience4j's
  sliding-window failure-rate computation — both are Analyze-stage logic).
- **Plan**: decides WHAT corrective action to take, informed by Knowledge (this is exactly OTP's
  restart-strategy selection — one_for_one vs. escalate — and Kubernetes' reconcile-diff decision).
- **Execute**: effectors carry out the planned change on the Managed Element (this is exactly OTP's
  actual `start`/`terminate` calls and Kubernetes' actual pod restart/reschedule).
- **Knowledge**: the shared store all four stages read/write — policies, thresholds, and HISTORY
  (this is the piece entirely absent from today's substrate: there is no persisted record of "which
  cadence has been failing, how often, since when").

### 6.2 Self-* properties
IBM's four defining properties: **self-configuring** (reconfigure without human intervention),
**self-healing** (detect and mitigate faults without human intervention — our scope here),
**self-optimizing** (tune performance toward goals without human intervention),
**self-protecting** (defend against misuse without human intervention). This document's actuator is
explicitly scoped to self-healing; self-optimizing (e.g. auto-tuning cadence intervals) and
self-protecting (e.g. auto-throttling under attack/abuse) are adjacent future extensions of the SAME
MAPE-K loop, sharing its Knowledge store, not separate architectures.

### 6.3 Explicit mapping onto our components
| MAPE-K element | This repo's component (today) | This repo's component (target) |
|---|---|---|
| Managed Element | the 37 cadences + 6 daemon threads + external deps (LLM/Kite/Breeze/NSE) | same, but each registered as a formal "child spec" |
| Sensor / Monitor | `is_alive()` (3 call sites, re-entrancy only), stdout `print` on outer-loop exception | `psutil`-backed process/thread/resource telemetry + a per-child last-success timestamp + `prometheus_client` counters |
| Analyze | *absent* — inner `except: pass` discards the signal before it reaches anywhere | a restart-intensity ring buffer per child (OTP MaxR/MaxT) + resilience4j-style sliding failure-rate per external dependency |
| Plan | *absent* — no decision, always "do nothing, try again next pass" | strategy table: `one_for_one` restart vs. circuit-open vs. escalate-to-human, keyed by child + current Knowledge |
| Execute | ad hoc thread (re)spawn on next cadence tick for 3 of 6 threads; nothing for the other 3 threads or any of the 37 cadences | a real supervisor `restart(child_id)` / `open_breaker(dependency)` / `escalate(incident)` effector |
| Knowledge | *absent* | a small persisted store (SQLite, matching this repo's existing per-engine JSON/SQLite convention) of restart history, breaker states, and current health per child |

---

## 7. Safety of autonomous action in a live trading system

**[A-primary, fetched]** Google SRE Book, *Automation at Google* —
https://sre.google/sre-book/automation-at-google/

- **Real cautionary case cited in the book**: an automated decommissioning process misinterpreted an
  empty dataset as "delete everything," triggering mass disk erasure across a CDN — "doing
  automation thoughtlessly can create as many problems as it solves." Directly relevant: our
  actuator must never treat "no data / can't determine current state" as license to act broadly (a
  restart-everything or clear-everything fallback) — absence of a clear signal is a reason to hold,
  not to escalate the blast radius.
- **Automation maturity ladder** (paraphrased from the book's five phases): no automation →
  externally-maintained system-specific scripts → externally-maintained generic tooling →
  internally-maintained system-specific automation (the SERVICE owns its own remediation) →
  autonomous systems needing no glue logic. The book's stated ideal is NOT "jump straight to fully
  autonomous" but reaching the phase where the SAME team that owns the service also owns and
  understands its automation — misaligned ownership ("teams with no production responsibility had
  no incentive to maintain quality") is called out as a direct cause of past incidents.
- **Idempotency as a hard requirement**: fixes must be safely re-runnable, explicitly enabling
  automation to run "every 15 minutes without fearing damage" — the same idempotency requirement as
  §5.3, now stated as an organizational safety practice, not just a retry-correctness detail.
- **Rate limiting / containment after the Diskerase incident**: Google's own post-incident fix was
  adding rate limits and sanity checks to the automation itself — i.e., the actuator needs a
  self-imposed action-rate ceiling independent of any per-component restart-intensity counter (this
  is the PDB-style blast-radius ceiling from §3.4, restated as hard-won operational practice).
- **Automation must expose its own internal state to humans** ("self-repairing" systems still need
  introspection humans can monitor) — directly implies the actuator's Knowledge store from §6 must
  be dashboard-visible (Rule N in this repo's own CLAUDE.md already requires this for every
  user-visible feature; the homeostat is no exception).

**[B-secondary]**, corroborated across current (2026) SRE/AIOps practice write-ups on graded
autonomy for automated remediation: a four-stage maturity model for how much autonomy an automated
remediation system is trusted with — **Read-Only** (observe/explain only) → **Advised** (recommend,
human decides) → **Approved** (execute, but gated on human approval per action) → **Autonomous**
(execute bounded remediation automatically, under guardrails) — with the consistent practitioner
guidance to keep any action that touches PRODUCTION-critical state behind a human approval gate
until the automation has a proven track record on that specific action class. For this repo: thread
respawns and cache invalidations are safely "Autonomous" from day one (cheap, reversible, already
informally happening for 3/6 threads); anything that would clear/rebuild a persisted state store,
force-fail-over an execution-critical dependency mid-session, or restart the `_run_forever` process
itself belongs at "Approved" or "Advised" until the actuator has an operating history to earn trust
— i.e., the escalation threshold should be keyed to blast radius and reversibility of the ACTION,
not just to the failure that triggered it.

**Concrete safety mechanisms to build in, synthesizing §2–§7**:
1. **Action budget** — OTP's MaxR/MaxT generalized to any repair action (not just process restart):
   at most K repairs of a given child/dependency per T-second window; beyond K, STOP repairing and
   escalate (mirrors OTP's supervisor-gives-up-and-terminates, except our "terminate" is "flag for
   human/dashboard attention," never silently keep retrying forever, and never kill the whole
   process over one flapping cadence).
2. **Blast-radius ceiling** — a PDB-style cap on how many DIFFERENT children the actuator may act on
   within one reconcile pass, so a shared root cause (e.g., disk full) triggering many simultaneous
   failures doesn't cause the actuator itself to become a stampede.
3. **Dry-run / plan-then-apply** — the Plan stage computes and logs "what I would do" before the
   Execute stage does it, at least for any action above the cheapest tier (thread respawn = execute
   immediately; anything touching a persisted store or an execution-critical dependency = log the
   plan, then apply on the NEXT tick, giving a human a window to intervene via the dashboard).
4. **Human-in-the-loop escalation threshold** — keyed to action severity (per point above), not
   uniform.
5. **Audit trail** — every Plan/Execute decision written to the Knowledge store (§6), not just
   printed to stdout as today — the dashboard-visible history IS the audit trail.

---

## 8. OSS sourcing — evaluated against `pyproject.toml` (checked first; none of the below are
already present as dependencies)

| Library | Verdict | Why |
|---|---|---|
| **`pybreaker`** | **Integrate** | v1.4.1 released Sep 2025, active (1.3.0 Mar 2025, 1.4.0 Jul 2025) — genuinely maintained, not abandoned. BSD license. Thread-safe by design (matches our thread-based, not asyncio-based, substrate). Optional Redis-backed state (`CircuitRedisStorage`) is available if we ever need cross-process breaker state, but in-memory is correct for our single-process substrate today. Implements Nygard's *Release It!* breaker with event listeners for observability hooks. |
| **`circuitbreaker`** (fabfuel) | **Reject** | Actively released (2.1.3, Mar 2025) and popular (512★, PyPI "critical project" tier by download volume), so NOT rejected for staleness — rejected because it is a thinner decorator-only implementation without pybreaker's explicit HALF_OPEN trial-permit counting or pluggable storage backend; pybreaker covers a strict superset of its capability for our needs. |
| **`aiobreaker`** | **Reject** | asyncio-native fork of pybreaker (replaces Tornado with native `asyncio`). No new PyPI release in the last 12 months (effectively stalled) AND its whole value proposition (asyncio integration) doesn't apply — this codebase's supervisor domain (`live_paper_trading_service.py`) is a synchronous thread-based loop, not asyncio. |
| **`purgatory`** | **Reject** | Well-designed (typed, tested, sync+async factories, pluggable Redis/in-memory storage, current release 3.0.1), but its headline feature over pybreaker is first-class asyncio support, which is not our execution model; adopting it would mean carrying an asyncio-shaped API we'd only ever use synchronously. Re-evaluate if/when the supervisor domain migrates to asyncio. |
| **`tenacity`** | **Integrate** | Actively maintained (9.0.0, Apr 2025; regular releases since), Apache-2.0. Provides `wait_random_exponential` (full-jitter-shaped: random up to `2**x * multiplier` seconds, capped) and `wait_exponential` with configurable min/max — directly implements §5.1's formulas as tested, composable decorators/context-managers rather than hand-rolled sleep loops. |
| **`backoff`** (litl) | **Reject** | Repository is archived; last PyPI release 2.2.1 was Oct 2022 (3+ years stale as of this research date) with unaddressed open issues from 2023–2025. Tenacity is its de facto successor per current community guidance. |
| **`stamina`** (hynek) | **Reject (for now)** | A thin, well-designed opinionated wrapper AROUND tenacity (not a competitor) adding type-preservation and built-in Prometheus/structlog instrumentation. Genuinely good, but adopting both tenacity (for the general retry primitive) and stamina (for its ergonomics layer) is one dependency more than needed for what this repo's call sites require; take tenacity directly and add the few lines of instrumentation ourselves against `prometheus_client` (already being integrated per below) rather than pull in a second retry-flavored package. Revisit if hand-rolled tenacity call sites start accumulating enough duplicated boilerplate to justify it. |
| **`supervisor`** (supervisord) | **Reject** | Manages independent **OS processes** launched from an INI config via a separate `supervisord` daemon + XML-RPC control — the wrong unit of supervision entirely for "threads inside one already-running Python process." Its `[program:x]` restart-policy vocabulary (`autorestart`, `startretries`) is conceptually copied into our own child-spec design (§2.5), not its code. |
| **`circus`** (circus-tent) | **Reject** | Same category as supervisord — manages OS processes/sockets via a ZeroMQ-driven daemon (`circusd`); its "reuse all or part of the system to build your own custom process watcher in Python" angle is closer to our need than supervisord's, but still fundamentally a separate-process orchestrator. Design principle borrowed (ZeroMQ pub/sub event fan-out for watcher state), code not adopted — this repo already vendors `blinker` (research/123) for exactly this kind of in-process pub/sub, so no new dependency is needed to get the equivalent event-fan-out benefit. |
| **`APScheduler`** | **Integrate** | v3.11.3 (Jun 2026), MIT, supports Python 3.8–3.14. Real `IntervalTrigger`/`CronTrigger`/`DateTrigger` objects, configurable job stores (in-memory is sufficient for us; SQLAlchemy-backed available if cadence state ever needs to survive a process restart), and — critically — a real **misfire-grace-time / coalesce policy**, which the current hand-rolled `_maybe_run_*` list has no equivalent of (a cadence that's "due" during a long stall today just fires late with no policy governing whether to catch up once or spam every accumulated occurrence). Replaces the 37-method hand-listed cadence dispatch with a registered-job model that is itself introspectable (job registry = a free Knowledge-store seed for "what should be running and when was it last due"). |
| **`schedule`** (dbader) | **Reject** | Lightweight, zero-dependency, and fine for simple scripts, but has no misfire/coalesce policy, no persistent job store option, and a string-chained DSL (`schedule.every().day.at("10:30")`) that is strictly less capable than APScheduler's trigger objects for a supervisor that needs to introspect "what is this job's exact next-due time" programmatically, not just run a `while: schedule.run_pending()` loop. |
| **`psutil`** | **Integrate** | v7.2.2 (Jan 2026), BSD-3-Clause, explicit Linux ARM64 support (plus Windows/macOS/BSD/Solaris/AIX) matching this box's aarch64 Linux target. Exposes exactly the Monitor-stage sensor data MAPE-K needs per process/thread: CPU%, RSS/USS memory, open file-descriptor count, thread count, I/O counters, disk usage — none of which the substrate currently collects about its own daemon threads at all. |
| **`py-healthcheck`** | **Reject** | Framed entirely around exposing an HTTP `/healthcheck` endpoint for a Flask/Tornado WEB app (checking is inherently pull/HTTP-shaped); this repo's dashboard already IS the HTTP surface (Rule N) and the supervisor's health state needs to be pushed into the SAME dashboard/`prometheus_client` registry the rest of the system uses, not a second bolted-on healthcheck blueprint. Also shows no new PyPI release in the past 12 months (low-maintenance signal, secondary reason). |
| **`prometheus_client`** | **Integrate** | v0.26.0 (Jul 2026), Apache-2.0/BSD-2-Clause dual-licensed, official Python client for Prometheus. Counter/Gauge/Histogram/Summary types are usable purely as an **in-process metrics registry** (no Prometheus server required — the dashboard can read the registry's collected samples directly, or expose `/metrics` later if a real scrape target is ever wanted) — this becomes the Knowledge-store's time-series half (restart counts, breaker-state gauges, cadence-staleness histograms), complementing the small SQLite/JSON history store for point-in-time state. |

---

## 9. Could not verify

1. **IBM's original MAPE-K white paper primary text** — *"An Architectural Blueprint for Autonomic
   Computing"* (IBM Corporation, 2003/2005/2006 revisions cited inconsistently across secondary
   sources) has no currently-live IBM-hosted PDF found via search; academic mirrors
   (semanticscholar.org, researchgate.net, scispace.com) surface citation records and figure
   reproductions but not a directly fetchable full primary text this session. The five-element
   architecture and self-CHOP properties in §6 are corroborated across ≥3 mutually-independent
   secondary academic sources describing the SAME diagram/definitions consistently, which is strong
   secondary corroboration, but is explicitly flagged as not a first-hand primary read.
2. **Exact resilience4j `Bulkhead` `maxWaitDuration` semantics under contention** were fetched but
   the readme.io page's Bulkhead section is thinner than its CircuitBreaker section; the values in
   §4.3 are the documented defaults, but nuanced runtime behavior (e.g. exact queueing fairness) was
   not independently verified against resilience4j's Java source in this session.
3. **`schedule` (dbader) exact last-commit date / archived status** — WebFetch/WebSearch on this
   specific repo's commit history returned only navigational links (commits/issues/branches pages)
   without rendering actual commit timestamps; the rejection in §8 rests on documented FEATURE gaps
   (no misfire policy, no persistent store) verified from its own docs, not on a confirmed staleness
   date, so the reject verdict does not depend on the unverified claim.
4. **systemd's own `StartLimitIntervalSec`/`StartLimitBurst` current values** for
   `deploy/nse-dashboard.service` were confirmed ABSENT by direct file read (not a web-search gap —
   this is a verified fact about our own repo), but the OPTIMAL values to set were not independently
   researched (out of this task's OSS/pattern-research scope; flagged for the eventual build task,
   not left silently unaddressed).

---

## Sources actually fetched or searched this session

- Erlang/OTP: https://www.erlang.org/doc/system/sup_princ.html
- Kubernetes probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/ ,
  https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes pod lifecycle / CrashLoopBackOff:
  https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ ,
  kubelet source `pkg/kubelet/kubelet.go` (via GitHub), 
  https://github.com/kubernetes/enhancements/issues/5734
- Kubernetes controllers: https://kubernetes.io/docs/concepts/architecture/controller/
- Kubernetes operator pattern: https://kubernetes.io/docs/concepts/extend-kubernetes/operator/
- Kubernetes disruptions/PDB: https://kubernetes.io/docs/concepts/workloads/pods/disruptions/
- Level- vs edge-triggered reconciliation (secondary corroboration):
  https://medium.com/hackernoon/level-triggering-and-reconciliation-in-kubernetes-1f17fe30333d
- resilience4j: https://resilience4j.readme.io/docs/circuitbreaker ,
  https://resilience4j.readme.io/docs/bulkhead
- AWS Architecture Blog: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Envoy retry budgets:
  https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto ,
  https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter
- gRPC retry/throttling: grpc.io retry guide (via search summary)
- IBM MAPE-K (secondary corroboration only, see §9):
  https://www.cs.unibo.it/~lanese/newpublications/fulltext/icsa-c2022-autonomic.pdf ,
  https://arxiv.org/pdf/2304.10503 , https://arxiv.org/pdf/2401.16382
- Google SRE Book, Automation at Google: https://sre.google/sre-book/automation-at-google/
- OSS libraries (PyPI pages fetched directly): https://pypi.org/project/pybreaker/ ,
  https://pypi.org/project/APScheduler/ , https://pypi.org/project/psutil/ ,
  https://pypi.org/project/prometheus-client/
- OSS libraries (searched, secondary sources): circuitbreaker (fabfuel), aiobreaker, purgatory,
  tenacity, backoff (litl), stamina (hynek), circus, supervisor, schedule (dbader), py-healthcheck

---

## Backlog note (Rule K)

This is a **research doc only** — no actuator engine exists in `src/` yet (confirmed: no
supervisor/homeostat module found in this repo during this session's grep pass). The named future
consumer is the actual build task ("component-lifecycle homeostat actuator half"), which composes
this doc with whatever the companion "detector/Monitor half" research produces. Logged in
`docs/BACKLOG.md` as the standing to-do so it is not silently lost — see that file's entry for this
research thread.
