# SICAP endpoint capture

This is the record of what was actually observed in DevTools, not what was
guessed. Per CLAUDE.md: endpoint shapes are captured, never guessed. The
`sicap-parser` Postman collection referenced in the kickoff plan is
historical context for the *shape* of the problem (2020-era), not a source
of field names — every value below traces to a fixture captured from the
live portal.

## How to capture an endpoint

1. Open `https://www.e-licitatie.ro/pub/notices/contract-notices/list/0/0`
   in Chrome (or the direct-acquisition / simplified-procedure equivalent
   page).
2. DevTools → Network → filter to **Fetch/XHR**.
3. Trigger the request (page through results, open a record, etc).
4. Right-click the request → **Copy** → **Copy as cURL (bash)**.
5. Paste into a scratch file, e.g. `/tmp/direct-list.curl.txt`.
6. Run:
   ```bash
   make capture NAME=direct-list CURL_FILE=/tmp/direct-list.curl.txt
   ```
   This saves `tests/fixtures/direct-list.json` (the response) and
   `tests/fixtures/direct-list.meta.json` (the request that produced it),
   and prints a field inventory — every key path, its type(s), null rate,
   and an example value.
7. Fill in the section below for that endpoint using the printed inventory
   and the meta file. Commit the fixtures alongside this doc update.

Repeat for each endpoint slot. Four to start; add more sections if DevTools
shows more than expected (e.g. a separate detail endpoint).

---

## Gate questions — answer these before Day 2 client code is trusted

These four determine whether `threshold_proximity`, `threshold_splitting`,
and the entity/award schema are even correctly shaped. See ADR-002 and
ADR-003 for why each one matters.

- [ ] **(a) VAT.** Do awarded/estimated values in the response include VAT,
      or not? (Legal ceilings are *fără TVA* — if SICAP publishes values
      *with* TVA, `threshold_proximity` is off by ~19% unless corrected.)
      **Answer:**
- [ ] **(b) Currency.** Is every value RON, or do other currencies appear
      (e.g. EUR for EU-funded contracts)? **Answer:**
- [ ] **(c) Pagination cap.** What's the highest `pageIndex` /
      `pageIndex * pageSize` offset that still returns results, before the
      API starts erroring or returning empty? (Undocumented SPA endpoints
      commonly cap around 10k — this determines the backfill sharding
      strategy.) **Answer:**
- [ ] **(d) Record identity.** Is there a stable native id in the response?
      Is it award-grain (one id per award) or procedure-grain (one id
      covers multiple lots/suppliers)? **Answer:**

---

## Endpoint: direct-list

- **Purpose:** list direct acquisitions (*achiziții directe*) for a date
  range.
- **URL:**
- **Method:**
- **Required headers** (beyond what Chrome sends by default — anything the
  request 401s/403s without):
- **Request body shape** (paste one real payload, redact nothing — it's a
  public endpoint):
  ```json
  ```
- **Pagination params:**
- **Fixture:** `tests/fixtures/direct-list.json`
- **Notes / surprises:**

## Endpoint: direct-detail

- **Purpose:** (does a per-record detail endpoint exist for direct
  acquisitions, or is the list response already complete? Note whichever
  is true.)
- **URL:**
- **Method:**
- **Required headers:**
- **Request body shape:**
  ```json
  ```
- **Fixture:** `tests/fixtures/direct-detail.json`
- **Notes / surprises:**

## Endpoint: simplified-list

- **Purpose:** list simplified-procedure notices (*proceduri
  simplificate*) for a date range.
- **URL:**
- **Method:**
- **Required headers:**
- **Request body shape:**
  ```json
  ```
- **Pagination params:**
- **Fixture:** `tests/fixtures/simplified-list.json`
- **Notes / surprises:**

## Endpoint: simplified-detail

- **Purpose:** per-procedure detail — lots, offer counts, award(s). This
  is the N+1 fetch referenced in ADR-001; confirm it's actually required
  (i.e. the list response doesn't already carry `n_offers` per lot).
- **URL:**
- **Method:**
- **Required headers:**
- **Request body shape:**
  ```json
  ```
- **Fixture:** `tests/fixtures/simplified-detail.json`
- **Notes / surprises:**

---

## Open questions found during capture

Anything that came up while capturing that isn't one of the four gate
questions but affects the schema or client design — log it here rather
than losing it in DevTools scrollback.
