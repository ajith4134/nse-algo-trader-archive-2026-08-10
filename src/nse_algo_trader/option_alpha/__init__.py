"""Shared option-alpha engines that both the INDEX-OPTION and STOCK-OPTION bots bind to.

The clean-sheet selection architecture (docs/ideas/option_bots_profit_taxonomy_and_redesign.md): a
cross-sectional, multi-factor pipeline — vol-richness (VRP) · opportunity scoring · structure optimization ·
real option economics — that lets the bots earn across every regime (theta in flat, delta in trend, vega in
vol shifts), ranking the whole universe against itself rather than judging each name in isolation.
"""
