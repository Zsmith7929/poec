# ADR-0002: Prices and recipe/metadata are separate concerns

- **Status:** Accepted
- **Date:** 2026-07-19
- **Related:** ADR-0001 (metadata source), ADR-0003 (grounding rule).

## Context

A transform is structured data, evaluated by deterministic code (no LLM in the
scan path). Its evaluation needs two independent inputs: *does this recipe exist and
what are its legs* (metadata), and *what does each leg cost* (price).

The core realization: **poe.ninja confirms that a price exists, not that a recipe
exists.** It will happily price both legs of a fantasy. The fabricated
"20 Chaos Orbs → 1 Awakener's Orb" row priced perfectly — both items are real
poe.ninja lines — yet the conversion does not exist. A price source can never be the
authority on whether a mechanic is real.

## Decision

Keep the two concerns strictly separated, with a single authority for each:

- **poe.ninja = prices only.** It answers "what is X worth," never "does X→Y exist."
- **poedb metadata table = recipes/facts only** (ADR-0001). It answers "does X→Y
  exist and what are its legs," never prices.
- **Transforms reference the metadata table by key for structure, and poe.ninja for
  the price of each leg.** The two are never conflated; a transform is only "real"
  when its structure is grounded in metadata (ADR-0003), independent of whether its
  legs happen to be priceable.

## Consequences

- The presence of a poe.ninja price for two items is never, by itself, evidence that
  a transform between them is valid.
- Metadata gaps and price gaps are distinct, separately-surfaced conditions (a real
  recipe whose leg poe.ninja can't price is a *pricing* gap, not a fake recipe).
- The metadata table and the price feed can be refreshed and versioned
  independently.
