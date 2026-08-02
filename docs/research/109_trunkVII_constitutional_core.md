# Trunk VII CONSCIENCE · Branch 1 — Constitutional Core (design + sourcing)

Date: 2026-07-25. Status: DESIGN → build this slice. AI-atlas branch **VII.1 "constitutional
core"** (SUPREME safety trunk; first branch of the build-to-100% program, `docs/AI_CONCEPT_TREE_
STATUS.md`). Built via the `building-features-from-ideas` + `sourcing-oss-parts` skills (user
directive: every branch is an IDEA → full rules+skills pipeline, not hand-coded from memory).

## 1. Target (pinned)
A first-class safety organ that encodes the project's INVIOLABLE rules as a machine-checkable
constitution and can veto/flag any proposed trading ACTION or system POSTURE that violates them.
- `ConstitutionalCore.review_action(action) -> ConstitutionalVerdict{permitted, violations[], trace_id}`
- `ConstitutionalCore.audit_system_posture(control_config) -> ConstitutionalVerdict`
- **Success test (real data):** the ACTUAL running `TradingControlConfig` passes the posture audit;
  a synthetic overnight-carry / naked-leg / >10-orders-per-sec / out-of-scope-segment / direct-to-
  exchange action is BLOCKED citing the correct article.

## 2. Decomposition (parts)
- A. **Constitution representation** — the inviolable articles [project-specific].
- B. **Action + posture model** — the shapes reviewed [project-specific].
- C. **Rule-evaluation engine** — articles × input → verdict [well-known pattern → shop for it].
- D. **Verdict / audit output** — structured, serialisable, trace-id'd [glue].

## 3. Sourcing (sourcing-oss-parts, per part)
Part C is the only part with real OSS prior art. Surveyed:
- **OPA / Rego** (+ `regopy` C-FFI Python bindings) — industry-standard policy-as-code, but Rego is
  a Datalog/Prolog-style DSL (steep curve), service-oriented, heavy C-FFI dep. Overkill for ~10
  in-process domain predicates.
- **json-rule-engine / json-rules-engine Python ports**, `business-rules`, `PyKnow`, `durable_rules`,
  `simpleruleengine`, PyKE/PyCLIPS — lightweight-to-expert-system rule engines; the Python JSON
  ports are "thin on community support/maintenance" — a risk for a SUPREME safety organ.
- **AWS Cedar** + autoformalization research (arXiv 2606.26649, 2509.23994) — patterns: hard vs soft
  constraints, generator-critic NL→policy, structured JSON audit logs with trace IDs.
- **agentic-guardrails / NeMo Guardrails / Guardrails-AI / Llama-Guard** — guard LLM *text*, wrong
  shape for structured trading actions.

**Verdict (skill step 6 — honest fallback, on the record):** OSS assembly was attempted; the
generic engines are either heavy/DSL (OPA/Rego, C-FFI) or thin-maintenance (JSON ports), and none
carry the NSE/SEBI/intraday constitution content (parts A/B/D). For a zero-dep, deterministic,
fully-auditable safety organ, a small hand-written evaluator is safer than a vendored dependency —
BUT we ADOPT the proven prior-art PATTERNS (not reinvent the design):
1. **hard vs soft** article severity (block vs advisory warning),
2. **policy-as-data** (each rule an `ConstitutionalArticle` object, not scattered `if/else`),
3. **structured audited verdict** (exact article id + evidence + a trace id, JSON-serialisable).

## 4. Build design (slice 1)
`conscience/constitutional_core.py` (PURE, zero-dep):
- `ArticleSeverity(Enum)`: `HARD` (violation ⇒ block) · `SOFT` (violation ⇒ warn).
- `ArticleScope(Enum)`: `ACTION` (per proposed trade) · `POSTURE` (system/config) · `BOTH`.
- `ConstitutionalArticle(article_id, principle, severity, scope, predicate)` — `predicate(subject)
  -> bool` returns True when COMPLIANT. Articles are DATA.
- `CONSTITUTION: tuple[ConstitutionalArticle, ...]` — from CLAUDE.md's binding constraints:
  A1 intraday-only (no overnight) · A2 ≤10 orders/sec/exchange/client · A3 defined-risk only (no
  naked option leg) · A4 never-a-naked-leg (atomic multi-leg) · A5 broker-as-principal (route via
  broker, not direct-to-exchange) · A6 live order carries Algo-ID · A7 phase-1 segment scope (NSE
  cash + NSE options only) · A8 per-trade risk ≤ configured max · A9 capital-per-trade within
  [min,max] · A10 white-box personal-use (not offered to others) [SOFT/flag] · A11 no-secrets
  [POSTURE].
- `ProposedTradingAction` (frozen): segment, instrument_kind, is_overnight_carry,
  option_risk_defined, is_atomic_multi_leg, routes_through_broker, has_algo_id,
  orders_this_second, per_trade_risk_fraction, capital_deployed, is_live.
- `SystemPosture` (frozen): built from `TradingControlConfig` (max_risk_per_trade_fraction, capital
  bounds, enabled segments) + fixed invariants (intraday-only, personal-use).
- `ConstitutionalVerdict(permitted, hard_violations[], soft_warnings[], trace_id, detail)` —
  `permitted = no HARD violation`; `to_json_dict()` for the audit trail.
- `ConstitutionalCore.review_action(action)` / `.audit_system_posture(config)` — evaluate the
  scoped articles; `trace_id` derived deterministically from the subject (no Date/random — stable).

## 5. Wiring (Rule G/N) + queued (Rule K)
- Service `_maybe_run_constitutional_audit(now)` (daily + at start): `audit_system_posture(
  control_config)` → cache; dashboard surface `constitutional_core` (Rule N) — articles count,
  posture permitted?, any warnings. This is a LIVE consumer (config-compliance monitor), not
  display-only.
- **QUEUED (next CONSCIENCE branch — the Referee/audit):** wire `review_action` as a HARD pre-order
  gate at the order-forming sites (`signal_to_order_intents` / the 4 entry sites) so a
  constitution-violating order is blocked + audit-logged. Branch VII.6 "Referee (audit)". Also
  queued: corrigibility/off-switch-as-value, deceptive-alignment monitor, wireheading tripwire,
  incident post-mortem — each its own branch/slice.

## 6. Verification
- Hermetic (Rule J): each article blocks its violation + passes the compliant case; verdict
  serialises; trace_id deterministic.
- Real-data (Rule F): load the REAL `TradingControlConfig` (`load_trading_control_config()`) →
  `audit_system_posture` PERMITTED with no hard violation (the running system is constitutionally
  compliant); a crafted violating action is blocked citing the article.

## 7. Coverage impact
Moves VII.1 constitutional core 🔴→🟢 and upgrades A-related fragments (power-budgets,
corrigibility/off-switch, security) from 🟡 toward consolidation. Updates
`docs/AI_CONCEPT_TREE_STATUS.md`.

Sources: spacelift.io/blog/policy-as-code-tools · github.com/santalvarez/python-rule-engine ·
osohq.com/learn/opa-vs-cedar-vs-zanzibar · arxiv.org/abs/2509.23994 (Policy-as-Prompt) ·
github.com/FareedKhan-dev/agentic-guardrails.
