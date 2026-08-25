# Radar

Risk-indicator engine over Romanian public procurement data (SICAP / e-licitatie.ro).
Portfolio project. The point is defensible numbers with a visible derivation, not
throughput.

## Non-negotiables

- Indicator logic lives in dbt SQL under `transform/models/marts/indicators/`.
  Never in Python. Never from an LLM.
- Every value in `seeds/ref_threshold.csv` traces to a cited legal source. Do not add
  or modify a threshold without a `source_url` the user has read.
- `data/raw/` is immutable and append-only. Transformations never write there.
- Output vocabulary: "indicator", "flag", "elevated score". Never "fraud",
  "corruption", or "illegal". A single-bidder tender is usually legal and often
  legitimate. We measure signals; we do not adjudicate.
- Entities, not individuals. No named administrators or beneficial owners, anywhere,
  in v1. PFA and Întreprindere Individuală names are natural-person names — they carry
  a suppression flag; check it before displaying.
- Every fact row carries a `source_url` back to a public page.
- The composite score is a published weighted sum. Never a model output.

## Stack

Python 3.12 (pinned via uv) + httpx — ingest
DuckDB + dbt-duckdb — transform
Evidence.dev — UI
DuckDB is single-writer: never run the Evidence dev server during `dbt build`.

## Commands

- `make ingest DATE=YYYY-MM-DD`
- `make backfill FROM=... TO=...` — resumable; safe to kill and restart
- `make capture NAME=... CURL_FILE=...` — replay a pasted cURL, save a fixture, print
  a field inventory
- `make dbt-build` — models and tests
- `make eval` — entity-resolution precision/recall + narrative grounding check
- `make check` — lint + test (this is the one that should always be green)

## Scope (ADR-001)

v1 = **direct acquisitions + simplified procedures**, 2024-01-01→present, national.
Scored window is 2024+. A 2022-01→2023-12 window is also ingested, for entity history
and first-award detection only — it is never scored.

Open procedures, restricted procedures, and TED cross-validation are v2.

## Decisions already made — do not re-derive these

Full reasoning in `docs/decisions/`. Summary:

- **Indicator applicability.** Indicators declare which procedure types they apply to.
  `single_bidder` and `award_speed` are simplified-only. `threshold_splitting` is
  direct-only. The composite normalizes over *applicable* weight mass, or direct
  acquisitions structurally under-score. See `applicable_weight_mass()`.
- **Award identity.** `award_id` derives from the SICAP native record id where one is
  award-grain; the native id is always stored alongside. Raw carries
  `(award_id, ingested_at)`; staging is latest-wins. Records get amended and cancelled
  upstream — a duplicate `award_id` in raw is expected, not a bug. (ADR-003)
- **Grain.** The award, never the procedure. `fct_award` carries `procedure_id`,
  `lot_number`, `n_lots`, `is_framework`. Framework agreements are excluded from
  `threshold_splitting`. (ADR-003)
- **Value basis.** All indicators use **awarded** value, not estimated. Estimated value
  is a separate signal, not an input to these six. Thresholds are *fără TVA*; the
  VAT basis of source values is recorded per-record and asserted by a dbt test. (ADR-002)
- **Currency.** Store `awarded_value_original` + `currency_original`; derive
  `awarded_value_lei` with an explicit `fx_rate` and `fx_rate_date` from
  `ref_fx_rate` (BNR). Never coerce a non-RON value silently. (ADR-002)
- **Thresholds are date-scoped.** Every indicator touching money joins `ref_threshold`
  on the award date **and** on `ref_cpv.is_works`. Never hardcode an amount. This is
  the bug that silently corrupts months of analysis.
- **Baselines** come from the 2024+ own-scrape. CPV divisions with <50 awards are
  suppressed, not estimated. The ciocan historical archive is a v2 option behind the
  `int_baseline_*` seam. (ADR-004)
- **Output language.** English UI and narratives. Romanian source strings — contract
  titles, entity names, CPV descriptions — render verbatim and are never translated
  or "cleaned up" for display.
- **Raw partitioning** is by `ingest_date=`, not award date, so late corrections never
  rewrite an existing partition. `data/cache/` (verbatim HTTP responses, keyed by
  request hash) and `data/raw/` (normalized append log) are different things.

## The evidence contract

`fct_indicator.evidence` is the boundary between the deterministic layer and the LLM
layer. The narrative generator sees **only** that JSON plus the award row. A number in
a narrative that isn't in the evidence is a hallucination and `make eval` fails on it.
When you add an indicator, the evidence JSON is part of its interface — design it as
carefully as the score.

`model_version` (indicator SQL) and `weights_version` (the weighted sum) are separate
and independently bumped. Narratives key on `model_version`, scores on
`weights_version`.

## Being a good guest

The data is public and openly licensed (Licența pentru Guvernare Deschisă v1.0,
attributed in the README). The server is still someone else's. Rate limit at 2 req/s,
descriptive `User-Agent` with a contact address, `Referer` set to the portal page,
cache every response to disk, never re-fetch what we already have.

## Where you help, and where you don't

**Good:** the HTTP client, retries, pagination, caching, dbt boilerplate, DuckDB SQL,
entity-matching code, the eval harnesses, the dashboard.

**Do not:** invent legal thresholds, invent indicator weights, invent endpoint shapes,
or write anything in `transform/models/marts/` or `transform/seeds/` without the user
reviewing it line by line.

**Endpoint shapes are captured, never guessed.** SICAP's JSON endpoints are
undocumented and they change. Models are written from committed fixtures in
`tests/fixtures/` that came from a real DevTools capture. The 2020 sicap-parser
Postman collection is historical context for the *shape* of the problem, not a source
of field names.

## Working style

The user is learning this architecture deliberately, not just consuming output.
Explain the reasoning behind non-obvious choices as you make them. Keep diffs small
enough to read end to end. When something in `docs/radar-kickoff-plan.md` turns out to
be wrong, say so and write an ADR — don't silently route around it.
