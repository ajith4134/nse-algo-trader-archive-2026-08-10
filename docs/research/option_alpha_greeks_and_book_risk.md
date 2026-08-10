# Greeks marking + Option Book Risk Engine (finishing "do all")

Two remaining redesign items, built to respect the user's "NO limit on option paper trades" directive.

## A. Per-leg greeks (`option_alpha/option_greeks.py`)
Reuse the already-integrated `vollib` (Peter Jäckel BSM) to compute each leg's IV (from its live premium) and
greeks — Δ, Γ, ν (vega), Θ (theta). `leg_greeks(right, strike, spot, tenor, rate, premium) → {iv, delta,
gamma, vega, theta}`. Feeds (1) the marker's net-structure greeks for the dashboard, and (2) the book risk
engine's portfolio net greeks. This is the greeks-based enrichment of slice 4's live-LTP mark.

## B. Option Book Risk Engine (`option_alpha/option_book_risk_engine.py`) — the "book optimizer", non-capping
A portfolio view over the pod's OPEN option book (all synthesized structures): aggregate **net greeks** (ΣΔ,
ΣΓ, Σν, ΣΘ across every leg × lot), a portfolio **VaR/CVaR** from the per-structure terminal-P&L distributions,
and total **expected P&L**. It ALSO solves a CVXPY utility-maximising LIVE-SIZING recommendation — per-name
lot multipliers that maximize expected P&L penalised by portfolio variance + a net-greek-neutrality preference,
subject to a margin budget. CRUCIAL: this NEVER caps PAPER acceptance (the user wants every option name traded
on paper) — it is a DIAGNOSTIC + a recommended LIVE sizing (used only when live trading is enabled). So the
"book optimizer" delivers portfolio-level awareness + a real CVXPY solve without undoing the no-limit rule.

Output `OptionBookRisk(net_delta, net_gamma, net_vega, net_theta, expected_pnl, portfolio_cvar,
live_size_multipliers)` → surfaced on the dashboard (a book-risk tile) + available to the live-execution seam.

## Why engine-grade
Real greeks from a real pricing model; a real CVXPY quadratic-utility solve over the book with margin +
greek-neutrality constraints; carried from the live open positions; decision output = the live-sizing vector +
the portfolio-risk numbers the operator/executor acts on. SOTA analog: a portfolio option-risk book +
mean-variance sizing (Riskfolio / cvxportfolio, but bespoke here for the option-greek structure).

## Verification (Rule F)
Compute greeks for a real NIFTY leg (Δ near 0.5 ATM, Γ>0, ν>0); aggregate the live open book's net greeks +
CVaR; confirm the CVXPY solve returns finite multipliers and that paper acceptance is UNCHANGED (no cap).
Hermetic: known legs → known greeks + a solvable tiny book.

## Sourcing (Rule I)
INTEGRATE `vollib`/`py_vollib_vectorized` (present, already used by the IV surface) for greeks; `cvxpy`
(present) for the sizing solve. No external OSS to vendor; bespoke aggregation is small. Logged.

## Backlog (Rule K)
- Live margin model per structure (SPAN-style) for the sizing budget (approximate now).
- Wire the live-sizing vector into the execution seam once live trading is enabled.
