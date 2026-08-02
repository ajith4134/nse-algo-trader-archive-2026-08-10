# Enforcement-hook audit — guide vs rule (2026-08-02)

**Video 1's distinction (Karpathy method):** a CLAUDE.md line is a **guide** — the model can fail to
follow it. A **hook** is a **rule** — the tool layer makes it impossible. Bucket every action:
**always-do** (autopilot) · **ask-first** (human look) · **never-do** (enforced by hook, not prose).
This audit inventories nse-algo-trader's rules A–Q against what is *actually* hard-enforced today, and
names the never-do gaps worth converting.

## 1. What is actually enforced today (8 hooks in `~/.claude/settings.json`)

| Hook (event / matcher) | Mechanism | Hard block? | Backs rule |
|---|---|---|---|
| UserPromptSubmit `*` | injects the RULE+SKILL GATE context each turn | **No** — reminder | routing, D, F, G, H, K |
| PostToolUse `Write\|Edit` on `src/**.py` | injects Rule-H map reminder (throttled 15 min) | **No** — reminder | H |
| PostToolUse `Write\|Edit` on `docs/research/*.md` | injects SOURCING-GATE reminder | **No** — reminder | I |
| PreToolUse `Write\|Edit` (chart/dashboard code) | injects dataviz reminder | **No** — reminder | (dataviz) |
| Stop `*` — src changed, SYSTEM_MAP not | blocks stop until addressed | **Yes** | H, D, F, J |
| Stop `*` — dashboard changed, live page unconfirmed | blocks stop | **Yes** | N |
| Stop `*` — diagram fidelity check fails | blocks stop | **Yes** | H.1 |
| Stop `*` — quality_gate (ruff/mypy) fails | blocks stop | **Yes** | O, P |

**Summary:** the only *hard* rules are the 4 Stop gates (all end-of-turn, all keyed to `src/` changes).
Everything at the *input* side (UserPromptSubmit, PostToolUse, PreToolUse) is a **guide** — an injected
reminder the model can still ignore. **There is no PreToolUse `deny` anywhere** — no action is currently
*prevented*, only reminded-about or checked-at-stop.

## 2. Rule-by-rule: bucket + current enforcement + gap

| Rule | What | Bucket | Enforced by | Gap |
|---|---|---|---|---|
| A | Engine-by-engine, verify before advancing | always | Stop(map) partial | guide-heavy; ok |
| B | Living flow-chart notes | always | Stop(map) | ok |
| C | Self-describing names | always | ruff (quality-gate Stop) partial | mostly guide |
| D | Save research/planning to files | ask-first | UserPromptSubmit reminder + Stop | guide |
| E | License is not a filter | always | none (prose) | guide (low risk) |
| F | Real-data verification gate | **ask-first** | Stop(map) reminder only | **guide — no gate runs the cockpit** |
| G | No orphaned features | always | Stop(map) checkpoint text | guide |
| H / H.1 | System Map current + diagram fidelity | always | **Stop hooks (hard)** | ✅ enforced |
| I | Never compromise; acquire what's needed | always | PostToolUse reminder | guide |
| J | Hermetic sim harness when no real data | always | prose | guide |
| K | No silent skips (BACKLOG) | always | UserPromptSubmit reminder | guide |
| L | Three segments equal by default | always | prose | guide |
| M | Plan altitude / no tunnelling | always | prose | guide |
| N | Every feature visible on dashboard | always | **Stop hook (hard)** | ✅ enforced |
| O / P | Production-grade / engine-grade depth | always | **Stop hook: quality_gate (hard)** | ✅ static only (not depth) |
| Q | Thin data never shrinks a feature | always | prose | guide |
| — | **Regulatory: never trade away** | **never-do** | runtime code only | **no hook** |
| — | **Protect secrets (.env / keys / SSH)** | **never-do** | **NONE** | **biggest gap** |
| — | **No destructive bash (rm -rf, force-push, curl\|sh)** | **never-do** | **NONE** | **gap** |

## 3. The never-do gaps worth converting (highest leverage first)

The three genuine **never-do** items — the buckets Video 1 says *must* be a hook, not prose — are the
only ones with **zero** enforcement today. The others (A–Q) are correctly guides or already Stop-gated;
converting more of them to hooks would add operational debt for little safety gain (the counterweight
principle: when a rule stops changing what gets done, don't harden it).

### 3a. `protect-secrets` — PreToolUse deny on Write/Edit (RECOMMENDED, safe to wire)
Blocks any Write/Edit to `.env*`, `**/secrets/**`, `*.pem`, `*.key`, `id_rsa*`, `~/.claude.json`, shell
profiles. **PreToolUse fails CLOSED** — a wrong block is merely annoying, never wedges a turn (unlike
Stop). This directly protects the posture we relied on when keeping `.env` out of the GitHub push.

```json
{ "matcher": "Write|Edit|NotebookEdit", "hooks": [{ "type": "command", "command":
  "f=$(jq -r '.tool_input.file_path // empty'); case \"$f\" in *.env|*.env.*|*/secrets/*|*.pem|*.key|*id_rsa*|*/.ssh/*|*/.claude.json|*/.bashrc|*/.bash_profile|*/.profile) jq -nc '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"protect-secrets hook: writing to a secret/credential/profile file is a never-do. Put values in .env (gitignored) via the shell, not via an edit.\"}}' ;; *) : ;; esac" }]}
```

### 3b. `block-dangerous-bash` — PreToolUse deny on Bash (RECOMMENDED)
Blocks destructive shapes: recursive delete of `$HOME`/`/`, plain `git push --force` (allow
`--force-with-lease`), pipe-to-shell (`curl … | sh`), world-writable chmod, and piping a secret file
into the network.

```json
{ "matcher": "Bash", "hooks": [{ "type": "command", "command":
  "c=$(jq -r '.tool_input.command // empty'); if printf '%s' \"$c\" | grep -qE 'rm[[:space:]]+-rf?[[:space:]]+(/|~|\\$HOME)([[:space:]]|$)|git[[:space:]]+push[[:space:]].*--force([[:space:]]|$)|curl[[:space:]].*\\|[[:space:]]*(sh|bash)|chmod[[:space:]]+-R?[[:space:]]*777|(\\.env|id_rsa|\\.pem)[^|]*\\|[[:space:]]*(curl|nc|wget)'; then jq -nc '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"block-dangerous-bash: destructive/exfil shape. Use --force-with-lease, avoid pipe-to-shell, never rm -rf home/root.\"}}'; else : ; fi" }]}
```

### 3c. Regulatory never-trade-away — keep in runtime code, NOT a hook
This is enforced correctly by the `pre_trade_risk_gate` in `src/`, exercised in every environment
(Rule F path). A hook cannot see order intent; hardening it belongs in code + tests, not settings.json.

## 4. Recommendation

Wire **3a** and **3b** (both PreToolUse deny — fail-closed, cannot wedge a turn). Leave A–Q as-is:
they are appropriately guides or already Stop-gated. Do **not** add more Stop hooks — Stop fails OPEN,
and every extra one is a chance to leave a turn un-endable (the videos' hard-won lesson: *registered ≠
firing*; test after every edit with `printf '{...}' | hook; echo $?`).

**Wiring is an ask-first change to the live enforcement layer, so it is NOT applied by this audit.**
The two blocks above are ready to paste; on approval I'll wire them via the update-config skill and
test each in isolation before relying on it. Tracked in BACKLOG until then.
