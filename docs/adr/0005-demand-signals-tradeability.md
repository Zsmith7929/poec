# ADR-0005: Demand/tradeability is distinct from confidence and supply

- **Status:** Accepted
- **Date:** 2026-07-19
- **Related:** ADR-0004 (surface candidates for human judgment); builds on the stash
  price endpoint.
- **Index note:** add a row for this ADR to `docs/adr/README.md` when the ADR-index
  branch and this branch both land on `main` (kept separate here to avoid a merge
  conflict on the index).

## Context

A high margin can be a mirage: an influenced base or unique shows a big gap only because
one or two stale listings sit unsold at an optimistic price. The scanner needs a demand
signal, and it did not have one — worse, it was using supply *as if* it were confidence.

What poe.ninja actually gives, verified live:

- **Exchange feed** (currency, fragments): `volumePrimaryValue` is real trade **volume**
  — a genuine demand/flow signal. This is what the scanner stores as `sample_depth` for
  those categories, so currency recipes already had demand information.
- **Stash feed** (uniques, base types, gems): the per-line fields are `listingCount`
  (**supply** — how many are listed, says nothing about sales), `count` (data points
  behind the price), and `sparkLine.totalChange` (price **momentum**). There is **no
  sold-per-day field.** Before this change the scanner used `listingCount` as
  `sample_depth` and fed it into `confidence()`, so *more supply raised confidence* — the
  opposite of demand. Live example: Bloodgrip at 10.3M chaos, listingCount 5, count 2,
  sparkline flat — a price built off ~2 stale listings, previously unflagged.

Constraint: the obvious demand oracle — which builds use an item — lives in poe.ninja's
builds/profiles API, which the PRD explicitly rules out. So demand must be inferred from
price/supply dynamics, not usage. True sale velocity needs the trade API (also off
limits), so a residual manual check remains (ADR-0004).

## Decision

Treat **price-confidence**, **supply**, and **demand** as three separate things, and
never let supply stand in for either of the others.

1. **Confidence** (data sufficiency): for stash prices, derive it from `count`
   (observations behind the price), **not** `listingCount`. Exchange prices are unchanged
   (volume-derived).
2. **Supply**: `sample_depth` remains the listing count for stash prices — but it is
   supply, and is no longer treated as confidence.
3. **Demand** (new): a `demand` label — `active` / `thin` / `unknown` — computed per
   price and propagated to each scan row (from the sell/output leg):
   - Exchange price: `active` when volume ≥ `min_sample_depth`, else `thin`.
   - Stash price: `active` when it has enough observations *or* the price is moving
     (`|sparkLine.totalChange| ≥ 1%`); otherwise `thin` — the mirage fingerprint (few,
     non-moving observations regardless of how many are listed).
   `thin` rows are flagged in the report (⚠) rather than presented as clean margins.

## Consequences

- The mirage class the flag targets (fat margin off 1–2 stale listings) is now visible,
  not silently ranked as a clean opportunity.
- Confidence for stash prices no longer rises with supply.
- This is a single-snapshot heuristic. The stronger demand model — **margin
  persistence/decay** (a margin that never closes is illusory) and **listing-count
  trajectory** (rising supply + flat price = glut) — needs accumulated history and is
  deferred to Phase 6, where it belongs with margin-decay analytics.
- The residual, irreducible check (actual sale velocity / listing age) stays with the
  human via the deep-link, consistent with ADR-0004.
