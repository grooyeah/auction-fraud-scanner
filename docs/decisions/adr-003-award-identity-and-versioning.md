# ADR-003: Award identity, record versioning, and fact-table grain

**Status:** accepted
**Date:** 2026-08-25

## Context

The starting schema had three related gaps that would each surface as a
confusing bug rather than a clean failure:

1. No record-versioning story. SICAP records get amended and cancelled
   upstream; re-scraping an amended award produces a second raw row with
   the same `award_id`. A bare `unique(award_id)` dbt test on raw data
   would fail on Day 4 for a reason easy to misdiagnose as a scraper bug.
2. No grain enforcement. `docs/radar-kickoff-plan.md` §8 states the grain
   must be the award, not the procedure, and that framework agreements
   must be identified and excluded — but the original `fct_award` had no
   `procedure_id`, `lot_number`, `n_lots`, or `is_framework` columns, so
   neither rule was actually enforceable.
3. `fct_award_score`'s primary key was `award_id` alone, with
   `weights_version` as a plain attribute — which makes it structurally
   impossible to hold two weightings of the same award side by side, even
   though re-weighting in the UI is an explicit goal of the plan (§5).

## Decision

- Raw records are identified by `(award_id, ingested_at)`. Staging
  resolves this to one row per `award_id` via a latest-wins model, and
  carries an `is_cancelled` flag rather than deleting cancelled awards.
- `fct_award`'s grain is the award. It carries `procedure_id`,
  `lot_number`, `n_lots`, and `is_framework`, so lot-deduplication and
  framework-agreement exclusion are enforceable in SQL, not just
  documented as a rule someone has to remember.
- `fct_award_score` is keyed `(award_id, weights_version)`.
- The narrative table is split out from `fct_award_score` entirely, keyed
  `(award_id, model_version)` — narratives are grounded in `evidence`,
  which changes with `model_version`, not with `weights_version`.
  Re-weighting a score should never invalidate a narrative that's still
  accurate.

## Consequences

- Every consumer of `fct_award_score` must know it's one-row-per-weighting,
  not one-row-per-award — the "current" score is whichever
  `weights_version` the UI has selected, not an unqualified lookup.
- `raw/` can be re-run through staging at any time to reflect the latest
  known state of an amended record, without re-scraping.
- The 200-pair entity gold set and the narrative grounding eval are
  unaffected by this ADR — it only touches award identity, not entity
  identity (`entity_alias` already had its own audit trail).

## Alternatives considered

- **Delete-and-replace on amendment.** Rejected — it breaks the immutable
  raw-layer guarantee and destroys the ability to answer "what did this
  record say before it was amended," which has real value for a project
  about procurement transparency.
- **Single `award_id` PK on `fct_award_score`, overwritten on re-weight.**
  Rejected as the status quo bug this ADR fixes — it directly contradicts
  the plan's own goal of user-adjustable weights.
- **Fold `n_lots` derivation into the ingest layer instead of a fact
  column.** Rejected — lot count is a property of the resolved award set,
  better computed in staging where amendments and cancellations are
  already being reconciled.
