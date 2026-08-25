# ADR-002: Value basis — awarded not estimated, VAT and currency made explicit

**Status:** accepted
**Date:** 2026-08-25

## Context

The kickoff plan flagged "estimated vs. awarded value" as a trap without
deciding it, and the starting schema had three separate value-basis bugs
sitting dormant: (1) no decision on which value each indicator should use;
(2) `awarded_value_lei` and `currency` as sibling columns, which is a
contradiction — a column literally named `_lei` should never need a
`currency` field defaulting elsewhere; (3) no plan for whether SICAP's
published values include VAT, when the legal ceilings in `ref_threshold`
are defined *fără TVA* (excluding VAT). Any of these produces numbers that
are wrong by a consistent, plausible-looking margin rather than an obvious
crash — the worst kind of bug for a project whose value proposition is
defensible numbers.

## Decision

- **All six indicators use awarded value.** Estimated value is not an
  input to any of them. (Awarded ≫ estimated is a candidate for a future,
  separate indicator, not folded into these six.)
- **Currency is stored as observed, never silently coerced.**
  `fct_award` carries `awarded_value_original` + `currency_original`, plus
  a *derived* `awarded_value_lei` with an explicit `fx_rate` and
  `fx_rate_date` sourced from a date-scoped `ref_fx_rate` seed (BNR rates).
- **VAT basis is recorded per record, not assumed.** `value_includes_vat`
  is carried on the raw/staging record, determined empirically from the
  Day 2 DevTools capture (checklist item `W1-08a`), and asserted by a dbt
  test so a change in SICAP's publishing behavior fails loudly instead of
  silently shifting every `threshold_proximity` score by ~19%.

## Consequences

- `threshold_proximity` and `threshold_splitting` are safe to build only
  after `W1-08` answers the VAT question — this is a real, not cosmetic,
  gate on those two models.
- If EUR-denominated (or other non-RON) awards turn out to be vanishingly
  rare, the fallback is to exclude and *count* them, never to silently
  coerce a currency without a rate.
- Every future indicator that touches money inherits this same discipline
  by construction, since `awarded_value_lei` is the only money column
  downstream models are expected to read.

## Alternatives considered

- **Use estimated value where awarded is missing.** Rejected — mixing
  bases within one indicator makes the score's meaning unstable across
  rows, which is worse than a smaller row count with a consistent basis.
- **Assume all values are fără TVA and skip the empirical check.** Rejected
  per the project's own stated standard (§2 of the kickoff plan): a
  scoring choice that can't be defended in public shouldn't ship, and "we
  assumed" is not a defense for a 19% systematic error.
- **Assume RON-only and drop the currency columns.** Deferred, not
  rejected — the schema is built to support this cheaply, but the decision
  itself waits on what `W1-08b` actually shows in the live data.
