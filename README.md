# Oracle — PoE1 Crafting Companion

A personal-use system for Path of Exile 1 that answers one question from two
directions:

> "What does it cost, in expectation, to produce item X, and is that less than
> buying it?"

- **Scanner (push):** batch-sweeps the market for inefficiencies where
  production cost < listed price, ranked by margin and liquidity.
- **Advisor (pull):** given a target item, computes the cheapest viable
  production path and emits step-by-step instructions, or says "buy it."

Both share a single **Pricing Oracle** with three tiers of production-cost
computation. All numbers come from deterministic code; an LLM sits at the
boundary only (intent → structured targets, engine output → human steps).

## Status

Early development. Building **Phase 0 (Foundations)**. See:

- `docs/prd.md` — canonical product spec (v0.3).
- `docs/superpowers/specs/2026-07-18-oracle-phase0-design.md` — Phase 0 design.

## Compliance

The system calls only documented public endpoints (GGG league API) and
poe.ninja's supported economy API. It never calls GGG internal website APIs
(including `/api/trade/*`). Specific-listing lookups are delegated to the human
via constructed trade-site deep-links. This is enforced by a repo-level test.

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run oracle leagues
uv run oracle prices currency --league Standard
uv run pytest
```
