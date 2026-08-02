"""Trunk II SENSES — sentiment/news sense (research/140).

An external-news SENSE for the bot: ingest Indian financial-news feeds, extract the items that
matter to our segments (index-option support/resistance, stock-option / intraday catalysts), score
them, weight each source by learned reliability, and feed per-underlying flags + a market mood into
the entry gate. Built in slices (research/140 build order):
  S1 feed base (this) → S2 NIFTY/BankNifty S/R extraction → S3 source reliability → S4 browsing
  agent (full article bodies) → S5 social/Telegram → S6 login seam (disabled) → S7 entry-gate consumer.

S1 delivers the ingestion foundation: poll tier-1 RSS feeds, detect per-feed staleness (a feed that
returns HTTP 200 with months-old content — e.g. Moneycontrol — is rejected), dedupe + store, and
surface on the dashboard.
"""
