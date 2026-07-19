# ADR-0006: Divination card → reward transform class

- **Status:** Accepted
- **Date:** 2026-07-19
- **Related:** ADR-0001 (poedb metadata), ADR-0002 (price/metadata separation),
  ADR-0003 (grounding), ADR-0005 (demand). Enabled by the stash pricing endpoint.

## Context

Divination cards are a deterministic transform: turning in a fixed set of N identical
cards yields exactly one named reward, no roll. It is the cleanest grounded class (no
selection bias), but the mapping (set size + reward) is not in any poe.ninja feed — it
lives in poedb. The reward's *price* lives in poe.ninja, but under different feeds
depending on what the reward is (currency vs unique).

Verified on the poedb `Divination_Cards` index page (one fetch, ~459 cards): each card
carries `Stack Size: 1 / N` and a reward in an `explicitMod` span whose CSS class states
the reward kind — `currencyitem` (e.g. House of Mirrors → 9 → Mirror of Kalandra, Rain
of Chaos → 8 → Chaos Orb) or `uniqueitem` (The Doctor → 8 → Headhunter).

## Decision

Add a grounded div-card→reward class following the vendor-recipe pattern (harvest →
cited metadata → expander → existing ScanEngine).

1. **Metadata** (`data/metadata/divination_cards.yaml`, cited): per card — name, set
   size, reward name, reward qty, and **reward kind** classified from the poedb span
   class (`currency` / `unique` / `other`). Harvested by a dev-time tool; refreshed on
   patch day.
2. **Pricing legs** (ADR-0002 separation preserved):
   - **Card leg**: priced via the poe.ninja `DivinationCard` exchange feed (cost =
     set_size × card price). Only cards actually traded there price; the rest surface
     `missing:` (honest).
   - **Reward leg**: priced **by name across a kind-scoped set of feeds** — currency
     rewards try `Currency`/`Fragment`; unique rewards try the `Unique*` stash feeds.
     Resolved via sentinel PriceRef categories (`RewardCurrency`, `RewardUnique`) that
     the resolver maps to that feed list; first priced by-name match (most-liquid) wins.
3. **Scope**: emit transforms only for `currency` and `unique` rewards (the priceable,
   valuable cases). `other`-kind rewards (bases, gems, maps, multi-item) are recorded in
   metadata but not emitted as transforms in v1 — base/map rewards need variant-aware
   keying and aren't worth it yet.
4. Demand flagging (ADR-0005) applies unchanged: a thin reward leg flags the row.

## Consequences

- Div-card flips (e.g. The Doctor → Headhunter) price end to end once both legs resolve;
  friction is 0 (turn-in is free).
- The reward-by-name resolution is a small general capability (price an item by name
  across feeds without knowing its exact category up front). Name collisions across
  feeds are possible but rare for card rewards; kind-scoping + priority order mitigate.
- Perf: pricing unique rewards pulls the large `Unique*` stash feeds; cached per scan,
  and helped by the `price_snapshots(league,category,key)` index. Acceptable; revisit
  with the broader stash-feed cost in Phase 6.
- `other`-kind card rewards remain unpriced until a later pass; documented in followups.
