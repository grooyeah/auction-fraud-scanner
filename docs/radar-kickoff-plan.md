# Radar — Romanian Procurement Red-Flag Engine

**First two weeks: scope, data sources, schema, and a day-by-day plan.**

---

## 0. Scope decision (make this before writing any code)

Do **not** try to ingest all of SICAP. Narrow v1 to:

- **Direct acquisitions** (*achiziții directe*) only
- **2024-01-01 to present**
- **National coverage** (don't filter by county — you need the national picture for baselines)

Rationale: direct acquisitions are the highest-volume, lowest-scrutiny, highest-risk category. They're also where threshold manipulation lives. Public tenders (*licitații*) are better documented and already covered by other tools. Add them in v2.

**Definition of done for v1:** someone opens a URL, filters to a county, and sees the 20 highest-scoring direct acquisitions of the period, each with a plain-language explanation and a link back to the SICAP source record.

---

## 1. Data sources

### Primary: SICAP / e-licitatie.ro JSON endpoints

The portal is a SPA backed by undocumented POST/JSON endpoints. Known ones include `GetDirectAcquisitionList`, and there are parallel endpoints for notices and views.

**How to get the current contract:** open `https://www.e-licitatie.ro/pub/notices/contract-notices/list/0/0` in Chrome, open DevTools → Network → XHR, page through results, and "Copy as cURL" each request. Do this yourself — do not let an AI guess endpoint shapes. They change.

Notes:
- Requests need a `Referer` header pointing back at the portal page.
- Data is published under **Licența pentru Guvernare Deschisă v1.0** (Open Government Licence). Attribute it in your README.
- Pagination is `pageIndex` / `pageSize`; date filters exist on publication and finalization dates.

### Reference implementation (read, don't fork)

- `github.com/ciocan/sicap-parser` — a Node utility that scrapes these endpoints; ships a Postman collection under `data/postman-collection.json`. Written ~2020, so treat endpoint details as historical, but the *shape* is correct. CC0 licensed.
- `github.com/ciocan/sicap-explorer` — includes a torrent of a historical archive (2007–mid-2020: ~470k tenders, ~22M direct acquisitions, ~50GB restored). Useful for building long-run baselines without hammering the portal.
- `github.com/ciocan/SICAP.ai` — the current production search engine. Read its `CLAUDE.md` and `docs/architecture.md`. You are building a *different thing* (risk scoring, not search), but it's the best available map of the domain.

### Supporting sources

| Source | What you get | Why you need it |
|---|---|---|
| **data.gov.ro** | ONRC company registry data (CAEN codes, branches, registration history); MFP annual financials by CUI (turnover, profit, employees) | The "new supplier" and "supplier too small for this contract" indicators |
| **ANAF public CUI service** (`webservicesp.anaf.ro`) | VAT registration status, registration date, inactive-taxpayer flag | Entity validation; catching awards to inactive firms |
| **TED** (`ted.europa.eu`) | Above-threshold notices in eForms, official documented API | Cross-validation and gap-filling. Caveat: only a small minority of Romanian procedures reach TED |
| **ANAP** (`anap.gov.ro`) | Official notifications when value thresholds change | Seeding and maintaining `ref_threshold` |

---

## 2. Legal and ethical posture

Write this into your README on day one, not as an afterthought.

- The data is public and openly licensed. You are still a guest on someone's server: rate-limit yourself (start at 2 req/sec), set a descriptive `User-Agent` with a contact address, cache every response to disk, and never re-fetch what you already have.
- **Vocabulary discipline.** Your outputs say *indicator*, *flag*, *pattern*, *elevated risk score*. They never say *fraud*, *corruption*, or *illegal*. A single-bidder tender is usually legal and often legitimate. You measure signals; you do not adjudicate.
- **Entities, not individuals.** Contracting authorities and companies are fair game. Named private individuals (administrators, beneficial owners) are not — leave them out of v1 entirely. It adds GDPR exposure and no analytical value at this stage.
- Publish your methodology and your weights. If you can't defend a scoring choice in public, don't ship it.

---

## 3. Architecture

```
sicap-api ──► raw/ (Parquet, partitioned by year/month, immutable)
                 │
                 ▼
             DuckDB ──► dbt: staging → entity resolution → dims/facts → indicator marts
                                          │ (Python step)
                                          ▼
                                    FastAPI / Evidence.dev dashboard
```

**Choices and why:**

- **DuckDB, not Elasticsearch.** You need window functions, joins, and aggregations — not full-text search. ES is the right tool for SICAP.ai's problem and the wrong tool for yours. One file, zero ops, embarrassingly fast on Parquet.
- **dbt-duckdb for the transform layer.** Your indicators are SQL, versioned, tested, and documented. This is non-negotiable: the moment indicator logic lives in ad-hoc Python scripts, the project dies.
- **Raw layer is immutable.** Never mutate `raw/`. Every re-derivation runs from raw. This is what lets you fix an entity-resolution bug in week 6 without re-scraping.
- **Evidence.dev for the v1 frontend.** Markdown + SQL → a real dashboard. Swap in Next.js later if you want the portfolio to show frontend work too.

---

## 4. Starting schema

```sql
-- ============================================================
-- REFERENCE
-- ============================================================

-- Legal thresholds are DATE-SCOPED. They have changed and will change again.
-- Every indicator that references a threshold must join on the award date.
CREATE TABLE ref_threshold (
    threshold_key   VARCHAR NOT NULL,   -- see seeds below
    valid_from      DATE    NOT NULL,
    valid_to        DATE,               -- NULL = currently in force
    amount_lei      DECIMAL(18,2) NOT NULL,
    legal_basis     VARCHAR NOT NULL,   -- e.g. 'L.98/2016 art.7(5), as amended by L.208/2022'
    source_url      VARCHAR NOT NULL,
    PRIMARY KEY (threshold_key, valid_from)
);

-- Seed values (VERIFY EACH ONE against the source before trusting it):
--   direct_products_services : 135_060  until 2022-09-09
--   direct_products_services : 270_120  from  2022-09-10  (L.208/2022)
--   direct_works             : 450_200  until 2022-09-09
--   direct_works             : 900_400  from  2022-09-10  (L.208/2022)
--   seap_mandatory_products  : 200_000
--   seap_mandatory_works     : 560_000
--   direct_payment_no_offer  :   9_000  from  2022-09-10  (was 4_500)
--   joue_products_services   : 705_819  until 2025-12-31
--   joue_products_services   : 698_460  from  2026-01-01
--   joue_works               : 27_334_460 until 2025-12-31
--   joue_works               : 26_960_556 from  2026-01-01
--   joue_local_regional      : 1_077_624 from  2026-01-01
-- JOUE thresholds are reset by EU delegated regulation roughly every two years.

CREATE TABLE ref_cpv (
    cpv_code    VARCHAR PRIMARY KEY,
    description_ro VARCHAR,
    division    VARCHAR,   -- first 2 digits
    is_works    BOOLEAN    -- drives which threshold applies
);

-- ============================================================
-- ENTITIES (the hard part)
-- ============================================================

CREATE TABLE dim_entity (
    entity_id         BIGINT PRIMARY KEY,
    cui               VARCHAR,          -- normalized: no 'RO' prefix, no leading zeros
    canonical_name    VARCHAR NOT NULL,
    legal_form        VARCHAR,          -- SRL / SA / PFA / II / RA / ...
    county            VARCHAR,
    registration_date DATE,             -- from ONRC via data.gov.ro
    caen_primary      VARCHAR,
    is_authority      BOOLEAN NOT NULL, -- contracting authority vs. supplier
    first_seen        DATE,
    last_seen         DATE
);

-- Every raw name string ever observed, and how it got attached to an entity.
-- This table IS your entity-resolution audit trail and the basis of your eval set.
CREATE TABLE entity_alias (
    alias_id        BIGINT PRIMARY KEY,
    entity_id       BIGINT NOT NULL REFERENCES dim_entity(entity_id),
    raw_name        VARCHAR NOT NULL,
    raw_cui         VARCHAR,
    normalized_name VARCHAR NOT NULL,   -- diacritics stripped, legal form removed, punctuation normalized
    source_system   VARCHAR NOT NULL,   -- 'sicap_da' | 'sicap_notice' | 'onrc' | 'ted'
    match_method    VARCHAR NOT NULL,   -- 'exact_cui' | 'normalized_name' | 'fuzzy' | 'manual'
    match_score     DOUBLE,             -- NULL for deterministic matches
    reviewed_by     VARCHAR,            -- set when you hand-adjudicate
    reviewed_at     TIMESTAMP
);

-- ============================================================
-- FACTS
-- ============================================================

CREATE TABLE fct_award (
    award_id             VARCHAR PRIMARY KEY,   -- stable id derived from the SICAP record
    source_system        VARCHAR NOT NULL,
    source_url           VARCHAR NOT NULL,      -- every row must be traceable to a public page
    procedure_type       VARCHAR NOT NULL,      -- 'direct' | 'simplified' | 'open' | ...
    authority_entity_id  BIGINT REFERENCES dim_entity(entity_id),
    supplier_entity_id   BIGINT REFERENCES dim_entity(entity_id),
    cpv_code             VARCHAR REFERENCES ref_cpv(cpv_code),
    publication_date     DATE,
    award_date           DATE NOT NULL,
    estimated_value_lei  DECIMAL(18,2),
    awarded_value_lei    DECIMAL(18,2) NOT NULL,
    currency             VARCHAR NOT NULL DEFAULT 'RON',
    n_offers             INTEGER,               -- NULL when not published
    contract_title       VARCHAR,
    funding_source       VARCHAR,               -- 'national' | 'eu_cohesion' | 'pnrr' | 'unknown'
    ingested_at          TIMESTAMP NOT NULL
);

-- ============================================================
-- INDICATORS
-- ============================================================

CREATE TABLE fct_indicator (
    award_id       VARCHAR NOT NULL REFERENCES fct_award(award_id),
    indicator_key  VARCHAR NOT NULL,
    score          DOUBLE  NOT NULL,   -- normalized 0..1
    evidence       JSON    NOT NULL,   -- the numbers that produced the score
    computed_at    TIMESTAMP NOT NULL,
    model_version  VARCHAR NOT NULL,   -- bump whenever the SQL changes
    PRIMARY KEY (award_id, indicator_key, model_version)
);

CREATE TABLE fct_award_score (
    award_id       VARCHAR PRIMARY KEY REFERENCES fct_award(award_id),
    composite      DOUBLE NOT NULL,    -- documented weighted sum. NEVER an LLM output.
    weights_version VARCHAR NOT NULL,
    narrative      TEXT,               -- LLM-generated, grounded strictly in `evidence`
    narrative_model VARCHAR,
    narrative_at   TIMESTAMP
);
```

**Two design notes worth internalising:**

1. `fct_indicator.evidence` is the contract between the deterministic layer and the LLM layer. The narrative generator sees *only* this JSON plus the award row. If a number appears in the narrative that isn't in the evidence, that's a hallucination and your eval should catch it automatically.
2. `model_version` and `weights_version` let you recompute without destroying history. You will change your mind about weights. Repeatedly.

---

## 5. The first six indicators

Each returns a normalized 0–1 score plus the evidence rows that produced it.

| Key | Logic | Notes |
|---|---|---|
| `single_bidder` | `n_offers = 1` | Romania runs ~44% single-bidder vs. an EU average around 28%, so this alone won't discriminate — it's a baseline, weighted low |
| `threshold_proximity` | Awarded value falls within 5% below the applicable ceiling on the award date | Join `ref_threshold` on date **and** on `ref_cpv.is_works` |
| `threshold_splitting` | ≥2 direct acquisitions, same authority + same supplier (or same CPV division), inside a rolling 90-day window, summing above the ceiling | The hard one. Window functions. Build it last in week 2 |
| `new_supplier` | Supplier's ONRC registration date is within 180 days of its first award | Needs the data.gov.ro join to work |
| `buyer_concentration` | Rolling-12-month Herfindahl index of one authority's spend across suppliers | Score the *contract*, using the concentration of its buyer |
| `award_speed` | Days from publication to award, as a z-score against the median for that CPV division and procedure type | Requires enough volume for a stable median — skip divisions with <50 awards |

**Composite score is a transparent weighted sum.** Publish the weights. Let users re-weight in the UI. Never let a model produce the number.

---

## 6. Day-by-day

### Week 1 — get data on disk and make it queryable

**Day 1 — architecture, no features.**
Write `docs/architecture.md` by hand before opening Claude Code. Data flow, module boundaries, what's deterministic vs. probabilistic. Then write `CLAUDE.md` (skeleton in §7) and scaffold the repo. Resist writing feature code today.

**Day 2 — the client.**
Reverse-engineer the endpoints in DevTools. Build a typed Python client: rate limiting, exponential backoff, on-disk response cache keyed by request hash, resumable pagination. Pull one day of data end to end and eyeball the JSON. *This is a good Claude Code task* — the shape is clear and the failure modes are mechanical.

**Day 3 — backfill.**
Run the full 2024→present backfill into `raw/`. Expect it to fail partway. Make it resumable, then run it again. Land Parquet partitioned by `year=/month=`.

**Day 4 — warehouse.**
DuckDB + dbt-duckdb scaffolding. Staging models with actual dbt tests: `not_null` on ids and award dates, `unique` on `award_id`, `accepted_values` on procedure type, and a custom test that awarded value is positive and under a sanity ceiling. You will find dirty data on day 4, not day 40.

**Day 5 — thresholds and first indicators.**
Seed `ref_threshold` — **read each legal source yourself**, don't accept the seeds above on faith. Ship `single_bidder` and `threshold_proximity` as dbt models.

**Weekend — the gold set.**
Hand-label 200 company-name pairs as match / no-match. Include the nasty cases: diacritics vs. stripped, `S.C. X S.R.L.` vs. `X SRL`, genuinely different companies with near-identical names, renamed entities. This is the single highest-value hour in the whole project. Everything in week 2 is measured against it.

### Week 2 — resolution, scoring, shipping

**Days 6–7 — entity resolution.**
Deterministic first: normalize CUI (strip `RO`, strip leading zeros, validate the check digit) and match exactly. That will resolve the large majority. Then normalized-name matching, then fuzzy (rapidfuzz `token_sort_ratio` is a reasonable start) for the remainder. Measure precision and recall against the gold set after each stage. Log every decision into `entity_alias`.

**Day 8 — dims and facts.**
Build `dim_entity` and `fct_award` on resolved entities. Re-run the two indicators. Numbers should move; understand why.

**Day 9 — threshold splitting.**
The window-function one. Get the boundary conditions right: overlapping windows, framework agreements, legitimately repeated purchases of consumables. Expect false positives and write down which ones you accept.

**Day 10 — narratives.**
LLM takes the award row plus `evidence` JSON, returns three short paragraphs with inline links to the source. Build a 20-case eval that programmatically checks: does every number in the narrative appear in the evidence? Any that doesn't is a failure. Automate it in CI.

**Days 11–12 — ship.**
Evidence.dev dashboard: county filter, top-N table, per-contract detail page with the indicator breakdown and the narrative. Deploy. Write the README with methodology, weights, limitations, and licence attribution.

---

## 7. `CLAUDE.md` skeleton

```markdown
# Radar

Risk-indicator engine over Romanian public procurement data (SICAP / e-licitatie.ro).

## Non-negotiables
- Indicator logic lives in dbt SQL under `models/marts/`. Never in Python. Never from an LLM.
- Every value in `seeds/ref_threshold.csv` traces to a cited legal source. Do not add or
  modify a threshold without a `source_url`.
- The `raw/` layer is immutable. Transformations never write there.
- Output vocabulary: "indicator", "flag", "elevated score". Never "fraud" or "corruption".
- Every fact row carries a `source_url` back to a public page.

## Stack
Python 3.12 + httpx (ingest) · DuckDB + dbt-duckdb (transform) · Evidence.dev (UI)

## Commands
- `make ingest DATE=YYYY-MM-DD`
- `make backfill FROM=... TO=...`
- `dbt build` — runs models and tests
- `make eval` — entity-resolution precision/recall + narrative grounding check

## Where you help, and where you don't
Good: the HTTP client, retries, pagination, dbt boilerplate, DuckDB SQL, the dashboard.
Do not: invent legal thresholds, invent indicator weights, or write anything in
`models/marts/` or `seeds/` without me reviewing it line by line.
```

---

## 8. Traps

- **Estimated vs. awarded value.** Both exist, they differ, and indicators that confuse them produce nonsense. Decide explicitly which each indicator uses.
- **Framework agreements** (*acorduri-cadru*) generate many awards against one procedure and will light up your splitting detector. Identify and exclude them.
- **Lots.** One procedure, many lots, many suppliers. Your grain must be the *award*, not the procedure.
- **The single-bidder baseline.** At ~44% nationally it is close to the norm, not an anomaly. Weight it accordingly or your top-20 becomes noise.
- **Threshold changes.** Every indicator that touches money must be date-aware. This is the bug that will silently corrupt three months of analysis if you hardcode a number.

---

## 9. First three commits

1. `docs/architecture.md` + `CLAUDE.md` + empty repo skeleton
2. The SICAP client with a cached fixture and a test that parses it
3. `seeds/ref_threshold.csv` with every row cited

If you get those three done well, the rest is execution.
