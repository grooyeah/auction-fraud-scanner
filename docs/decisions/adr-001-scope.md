# ADR-001: v1 scope is direct acquisitions + simplified procedures

**Status:** accepted
**Date:** 2026-08-25

## Context

The original kickoff plan scoped v1 to direct acquisitions only, on the
grounds that they're the highest-volume, lowest-scrutiny category and where
threshold manipulation lives. But two of the six planned indicators —
`single_bidder` and `award_speed` — are properties of a competitive
procedure. Direct acquisitions in Romania are typically awarded without a
formal offer count and without a meaningful publication→award gap (the
notice can *be* the award). Scoped to direct-only, those two indicators
would be near-constant and would contribute nothing to the top-N ranking.

## Decision

v1 ingests **both** direct acquisitions (*achiziție directă*) and
simplified procedures (*procedură simplificată*), 2024-01-01 → present,
national coverage. All six originally planned indicators stay in scope,
each declaring which procedure type(s) it applies to.

## Consequences

- Two structurally different endpoint shapes to reverse-engineer and
  ingest: direct acquisitions are flat list records; simplified procedures
  are notice → lots → awards, requiring a per-procedure detail fetch.
- The composite score must normalize over each award's *applicable*
  indicator weight mass, not a flat weighted sum — otherwise direct
  acquisitions structurally under-score regardless of actual risk. See
  `docs/architecture.md` and the `applicable_weight_mass()` dbt macro.
- Realistic timeline moves from ~12 to ~16–18 working days (a second
  ingestion pipeline, mostly). Absorbed into entity-resolution days and the
  dashboard days rather than cut from either data source.
- Open and restricted procedures remain out of scope for v1.

## Alternatives considered

- **Direct-only, drop the two inapplicable indicators.** Cheapest, but
  ships with 4 of 6 indicators and no real answer for what single-bidder
  and award-speed risk looks like in the highest-risk category.
- **Direct-only, replace the two indicators with direct-applicable ones**
  (e.g. supplier-dependency, round-value clustering). Keeps the timeline
  short but abandons two indicators the user specifically wanted, and
  those replacements are unvalidated ideas rather than the reviewed plan.
- **Ship all six on direct-only anyway**, documenting them as degenerate.
  Rejected as dishonest — a "top 20" that includes two indicators known in
  advance to be near-constant isn't a top 20 by risk.
