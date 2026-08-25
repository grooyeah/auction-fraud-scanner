# Architecture

This document describes the pipeline, the boundary between deterministic
and probabilistic components, and why each layer is built the way it is.
Written before any ingestion code, per the Day 1 discipline in the kickoff
plan: architecture decisions should not be discovered by reading Python.

## Pipeline

```
                    ┌─────────────────────────────────────────┐
                    │              SICAP / e-licitatie.ro       │
                    │  undocumented JSON endpoints (two shapes) │
                    └───────────────┬───────────────────────────┘
                                    │ 2 req/s, cached, resumable
                                    ▼
                    ┌───────────────────────────────┐
                    │  data/cache/                   │  verbatim HTTP responses,
                    │  keyed by request hash          │  never re-fetched
                    └───────────────┬───────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │  data/raw/                      │  Parquet, partitioned by
                    │  IMMUTABLE, append-only          │  ingest_date=, never rewritten
                    └───────────────┬───────────────┘
                                    ▼
        ┌──────────────────────────────────────────────────────┐
        │  DuckDB + dbt                                          │
        │                                                        │
        │  staging          latest-wins dedup on (award_id,      │
        │                   ingested_at); one model per source    │
        │       │                                                │
        │       ▼                                                │
        │  entity resolution   Python step (the one exception     │
        │                       to "everything is dbt"): CUI      │
        │                       validation → normalized-name      │
        │                       match → fuzzy match. Every         │
        │                       decision logged to entity_alias.  │
        │       │                                                │
        │       ▼                                                │
        │  dims / facts     dim_entity, fct_award — resolved,     │
        │                   award-grain, source_url on every row  │
        │       │                                                │
        │       ▼                                                │
        │  indicator marts  one dbt model per indicator, SQL      │
        │                   only. evidence JSON + 0..1 score.     │
        │       │                                                │
        │       ▼                                                │
        │  fct_award_score  published weighted sum over           │
        │                   applicable indicators. Never an       │
        │                   LLM output.                           │
        └───────────────────────────┬────────────────────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │  narrative generator (LLM)      │  sees ONLY evidence JSON
                    │  → fct_award_narrative           │  + the award row. Grounding
                    └───────────────┬───────────────┘  checked in CI (make eval).
                                    ▼
                    ┌───────────────────────────────┐
                    │  Evidence.dev dashboard          │  top-N, county filter,
                    │                                  │  per-contract detail
                    └───────────────────────────────┘
```

## What's deterministic vs. probabilistic

| Component | Deterministic | Probabilistic |
|---|---|---|
| Ingestion | ✓ (bytes in, bytes on disk) | |
| CUI matching | ✓ (exact, validated check digit) | |
| Normalized-name matching | ✓ (exact match on a normalized string) | |
| Fuzzy name matching | | ✓ (rapidfuzz score above a gold-set-derived threshold) |
| Indicator scores | ✓ (SQL, versioned, tested) | |
| Composite score | ✓ (published weighted sum) | |
| Narrative text | | ✓ (LLM), but **constrained**: every number must appear in `evidence` |

Two components are probabilistic by nature — fuzzy entity matching and
narrative generation — and both are treated the same way: measured against
a held-out gold standard (the entity gold set; the 20-case grounding eval),
with the threshold or acceptance criterion derived from that measurement,
never guessed. Everything else in the scoring path is deterministic SQL,
because the project's central claim — these numbers are defensible — only
holds if a skeptical reader can trace every score back through SQL they can
read, to evidence they can check, to a source URL they can open.

## Why each layer is built this way

**DuckDB, not Elasticsearch.** The workload is window functions, joins, and
aggregations over a few million rows — not full-text search. `sicap-explorer`
solves a search problem; Radar solves a different one.

**dbt for the transform layer, non-negotiable.** The moment indicator logic
lives in ad-hoc Python, it stops being versioned, tested, and diffable in
the way a SQL model is. A project whose entire value proposition is
"defensible numbers" cannot have that logic anywhere except a form that a
reviewer — including future-you — can read start to finish and re-run.

**Raw is immutable and partitioned by ingest date, not award date.**
Immutability is what lets an entity-resolution bug found in week 6 be fixed
by re-running the transform, not by re-scraping. Partitioning by award date
would break that guarantee the first time a correction to an old record
arrives: fixing the partition would mean rewriting it. Partitioning by
`ingest_date=` means every write is a new partition, full stop. Temporal
slicing (e.g. "awards made in March 2024") happens in staging, over the
`award_date` column, not over the partition layout.

**The response cache and the raw layer are different things, deliberately.**
`data/cache/` holds verbatim HTTP responses keyed by request hash — its job
is "never make the same request twice." `data/raw/` holds the normalized,
append-only award log — its job is "never lose or silently rewrite a fact."
Conflating them would mean a schema change to the raw layer forces
re-fetching data that's already on disk, which defeats the point of caching.

**Record identity is `(award_id, ingested_at)`, not just `award_id`.**
SICAP records get amended and cancelled upstream. Re-scraping the same
award after an amendment produces a second raw row with the same
`award_id` — that's expected, not a scraper bug. Staging resolves it with
a latest-wins model; a bare `unique(award_id)` test on raw data would fail
for the wrong reason.

**Entity resolution is the one Python step inside the transform layer**,
because CUI validation, name normalization, and fuzzy matching are not
naturally SQL problems, and forcing them into SQL would make the logic
harder to test, not easier. The output of that step — `entity_alias` — is
itself a fact table: every match decision, its method, and its confidence
are logged, so the resolution process has the same auditability as
everything downstream of it.

**The `evidence` JSON is the contract between the deterministic and
probabilistic halves of the pipeline.** The narrative generator is given
*only* `evidence` plus the award row — not the raw source, not other
indicators' evidence, nothing it could use to invent a plausible-sounding
but ungrounded detail. A number in the narrative that doesn't trace back to
`evidence` is mechanically detectable, and the grounding eval (`make eval`)
checks exactly that, in CI, on every change to the narrative prompt.

**`model_version` and `weights_version` are separate and independently
bumped**, because indicator SQL and indicator weights change for different
reasons on different schedules. Recomputing under a new model version or a
new weights version is an insert, not a migration — the old scores stay
queryable, which matters both for debugging ("why did this score change?")
and for the portfolio narrative ("here's how the methodology evolved").

## Traps this architecture is built to survive

These are called out explicitly because they're the kind of thing that
produces *plausible-looking wrong numbers*, which are far more dangerous
than a crash:

- **Estimated vs. awarded value.** Every indicator that touches money uses
  **awarded** value. Estimated value is a candidate for a future indicator
  (large deviation between estimate and award), never an input to these six.
- **Currency.** `awarded_value_original` + `currency_original` are stored
  as observed; `awarded_value_lei` is *derived*, with an explicit
  `fx_rate` and `fx_rate_date`. Nothing gets silently coerced to RON.
- **VAT.** Legal thresholds are *fără TVA*. Whether SICAP's published
  values include VAT is an empirical question for the Day 2 DevTools pass,
  not an assumption — see `docs/sicap-endpoints.md` once it exists.
- **Framework agreements** (*acorduri-cadru*) generate many awards under
  one procedure and would false-positive the threshold-splitting detector
  if not identified and excluded.
- **Lots.** One procedure can have many lots and many suppliers. The grain
  of `fct_award` is the award, never the procedure — `procedure_id`,
  `lot_number`, and `n_lots` are all carried so this is enforceable, not
  just documented.
- **Threshold changes.** Legal ceilings are date-scoped and have changed at
  least once in the 2024+ window. Every money-based indicator joins
  `ref_threshold` on the award date and on `ref_cpv.is_works`. No indicator
  hardcodes a ceiling.
- **Indicator applicability across procedure types.** Direct acquisitions
  and simplified procedures aren't eligible for the same indicators
  (`single_bidder` and `award_speed` need a competitive process that direct
  acquisitions don't have). The composite score normalizes over each
  award's *applicable* weight mass — otherwise direct acquisitions
  structurally under-score regardless of actual risk.
- **The single-bidder baseline.** Romania runs roughly 44% single-bidder
  direct/simplified awards, against an EU average near 28%. That's close
  enough to the local norm that `single_bidder` alone doesn't discriminate
  risk — it's a low-weighted signal, not an anomaly detector on its own.

## What's out of scope for v1

- Open and restricted procedures (only direct acquisitions + simplified
  procedures are in scope — see `docs/decisions/adr-001-scope.md`).
- TED cross-validation.
- The 2007–2020 historical archive (baselines are computed from the 2024+
  scrape; see `docs/decisions/adr-004-baselines.md`).
- Named individuals, in any form, anywhere in the pipeline or the UI.
