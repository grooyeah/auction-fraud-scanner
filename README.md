# Radar

A risk-indicator engine over Romanian public procurement data — direct
acquisitions and simplified procedures published on SICAP / e-licitatie.ro.

Radar ingests awards, resolves contracting authorities and suppliers to
canonical entities, computes deterministic risk indicators (single-bidder
rate, threshold proximity, threshold splitting, new-supplier, buyer
concentration, award speed), and surfaces the highest-scoring contracts with
a plain-language explanation and a link back to the public source record.

This is a portfolio / learning project. The goal is a fully defensible,
end-to-end pipeline — every number traceable to a cited source or a
documented computation — not maximum coverage.

**Status: Day 1 — architecture and scaffolding. No data has been ingested
yet.** See [`docs/architecture.md`](docs/architecture.md) for the pipeline,
[`docs/decisions/`](docs/decisions/) for why it's built this way, and
[`CLAUDE.md`](CLAUDE.md) for the constraints this repo is built under.

## What this is not

Radar reports **indicators**, not verdicts. A high score means "this
contract has statistical properties associated with reduced competitive
scrutiny," not "this contract is fraudulent" or "this is corruption." A
single-bidder award is usually legal and often legitimate — see
[Traps](docs/architecture.md) for why single-bidder rates alone don't
discriminate risk in Romania. Named individuals (administrators, beneficial
owners) are deliberately out of scope; Radar scores entities — contracting
authorities and companies — never people.

## Data and licensing

Procurement data is published by ANAP under the **Licența pentru Guvernare
Deschisă v1.0** (Open Government Licence). Radar is a guest on the SICAP
infrastructure: requests are rate-limited, cached to disk, and never
re-fetch what's already been retrieved. See `docs/architecture.md` for the
full ingestion posture.

Company registry data (ONRC via data.gov.ro) and VAT status (ANAF) are used
to validate entities and are similarly public-record sources — cited
per-field where they feed an indicator.

## Setup

```bash
uv sync
```

Requires Python 3.12. Warehouse and transform layers (DuckDB, dbt) come
online starting Day 4 — see the project checklist.

## Commands

```bash
make check              # lint + test
make ingest DATE=...    # fetch one day of awards (Day 2+)
make backfill FROM=... TO=...
make capture NAME=... CURL_FILE=...   # turn a DevTools capture into a fixture
make dbt-build          # run transform models + tests (Day 4+)
make eval               # entity-resolution P/R + narrative grounding (Day 6+/10+)
```

## Methodology, weights, and limitations

To be written as indicators ship (checklist item `W2-26`). Will cover: how
each indicator is defined and why, how composite weights were chosen and
their justification, known false-positive patterns we've accepted, and a
corrections process for flagged entities that believe a record is wrong.

## License

MIT for the code in this repository. See **Data and licensing** above for
the terms governing the underlying procurement data, which is not
relicensed by this project.
