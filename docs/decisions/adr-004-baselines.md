# ADR-004: Baselines from the 2024+ scrape, with a 2022–2023 entity-history extension

**Status:** accepted
**Date:** 2026-08-25

## Context

Two indicators need a population baseline to be meaningful:
`buyer_concentration` (rolling-12-month HHI) and `award_speed` (z-score
against the median for a CPV division and procedure type). The kickoff
plan mentions the `sicap-explorer` historical archive (2007–mid-2020,
~470k tenders / ~22M direct acquisitions, ~50GB restored) as a way to
build long-run baselines without hammering the live portal, but the
day-by-day plan never actually schedules ingesting it.

Separately, `new_supplier` (is this supplier's first award within 180 days
of ONRC registration) has a left-censoring problem at the scope boundary:
with ingestion starting 2024-01-01, a supplier whose true first award was
in 2023-11 looks new in the data even though it isn't. ONRC registration
date alone answers "is this a genuinely new company" but not "is this
company new to public procurement" — those are different questions, and
the indicator needs the second one.

## Decision

- `buyer_concentration` and `award_speed` baselines (CPV-division ×
  procedure-type medians, HHI distributions) are computed from Radar's own
  2024+ scrape. No historical-archive ingestion in v1.
- CPV divisions with fewer than 50 awards in the scored window are
  suppressed from `award_speed`, not estimated from a smaller sample.
- A second ingestion window, **2022-01-01 to 2023-12-31**, is scraped using
  the same client — for entity and first-award history only. It is never
  scored (no `fct_indicator` or `fct_award_score` rows), and exists solely
  so `new_supplier` can check "have we seen this supplier before,
  anywhere in 2022+" rather than "have we seen this supplier before,
  anywhere in the scored window."
- `int_baseline_*` staging models are the seam where a future historical-
  archive ingestion would plug in, without touching indicator SQL.

## Consequences

- No second, differently-shaped ingestion pipeline for the 2007–2020
  archive in v1 — same client code, same schema, just a wider date range
  for one specific purpose.
- `new_supplier`'s residual censoring (a supplier whose true first award
  was before 2022-01-01) is smaller and explicitly documented rather than
  silently present at the full scope boundary.
- Baseline quality depends on 2024+ volume being sufficient for stable
  medians per CPV division — the <50-award suppression rule is the
  safety valve if it isn't.
- The historical archive remains available as a v2 upgrade: swapping it in
  means populating `int_baseline_*` from a new source, not rewriting the
  indicators that consume it.

## Alternatives considered

- **Ingest the full historical archive now.** Rejected for v1 — a
  differently-shaped 2007-era schema, its own staging layer, and 50GB of
  data are a 2–3 day cost for baseline depth the <50-award suppression
  rule already makes acceptable without it.
- **Do nothing about left-censoring.** Rejected — `new_supplier` would
  misclassify every supplier whose real first award fell in late 2023,
  which is not a small edge case near a hard January 1 boundary.
- **Push the scored window start back to 2022-01-01 instead of adding a
  history-only window.** Rejected — it would double the scored volume for
  a problem that only `new_supplier` has, and would pull two additional
  years of data into every other indicator's baseline for no benefit.
