"""Capital-Allocation Optimizer (Trunk III WILL — acting extension; research/163).

A real convex portfolio/risk-allocation ENGINE that splits a bounded risk budget across the SET of
simultaneous entry candidates at a decision tick — replacing per-candidate fixed/Kelly sizing + rank-only
arbitration with a SOLVED, constrained optimisation (research/155 gap #3). Four objective modes
(Mean-CVaR default · Ledoit-Wolf Mean-Variance fallback · Risk-Parity/ERC · Qlib Enhanced-indexing), four
constraint families (per-position/segment caps · gross/net exposure · cardinality · integer lots +
turnover), solved via CVXPY. Advisory-until-earned at the entry sites (Rule P.4); live-accrual is the one
open blocker (Rule K).
"""
