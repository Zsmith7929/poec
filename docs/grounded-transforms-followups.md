# Grounded transforms — tracked follow-ups

From the grounded-transform reseed (ADR-0001..0004). None block this PR; each is a
deferral with a concrete reason and evidence.

## Deferred transform classes

- **Influence base flips — infeasible on the current poe.ninja API.** Verified during
  design: the new exchange API (`/poe1/api/economy/exchange/current/overview`) returns
  **0 lines for `type=BaseType`** on Standard. Base types aren't served, so plain-vs-
  influenced base pricing can't be computed. Blocked on the uniques/base-type endpoint
  gap below. (The flagship shaper-shield remains as a single verify-mode one-off in
  `data/transforms_t1.yaml`, priced via the human-in-the-loop DeepLinkResolver.)

- **Div-card → reward — harvest de-risked, pricing blocked.** The poedb
  `Divination_Cards` page yields all ~459 cards with set size + reward from one fetch,
  in stable class-tagged HTML (`stackSize`, `explicitMod`/`currencyitem`); House of
  Mirrors = 9 → Mirror of Kalandra verified. But the valuable rewards are **uniques**,
  which the current poe.ninja API doesn't price (see below). Card→currency-reward cards
  (e.g. → Mirror/Divine) are a viable subset; deferred until the reward-category
  resolution is worth building for that subset alone.

## Cross-cutting gap (affects more than this PR)

- **No known current poe.ninja endpoint for uniques / base types / gems.** The exchange
  API serves only currency-like feeds (verified: `Currency`=91, `Fragment`=63,
  `DivinationCard`=31; `BaseType`=0, `UniqueAccessory`=0). The classic
  `api/data/itemoverview` 404s. This limits *every* class whose legs are uniques/bases
  (div-card→unique rewards, influence flips, unique flips), and affects future phases
  that assume unique/base pricing. **Action:** identify the endpoint poe.ninja's own
  site uses for unique/base pricing (or an alternative source), then revisit the
  deferred classes. Until then, the tool can only price currency-exchange items.

## Data-coverage notes (vendor recipes, this PR)

- Of 40 harvested currency vendor recipes, **14 price end-to-end** on Standard; the rest
  reference **Oils and Runes**, which poedb classes as currency-type items but poe.ninja
  files under separate feeds (`Oil`, and Runes are a newer mechanic). They surface as
  `missing:` rows (honest), not fabricated. Adding those feeds as priceable categories
  (mapping the recipe legs to the right poe.ninja `type`) would light them up — a small
  follow-up once the multi-feed price routing is desired.
- Most vendor-recipe margins are near-zero or negative (expected — vendor rates are
  usually worse than market). The scanner's margin/liquidity gate correctly drops them;
  they exist to catch occasional market dislocations (e.g. Chromatic ← 3× Jeweller's
  showed a small positive margin on Standard during testing).

## Operational

- **Patch-day step:** re-run `uv run python tools/harvest_vendor_recipes.py --league <permanent>`
  and commit the regenerated `data/metadata/vendor_recipes.yaml`. The pinned parser
  fixture test fails loud if poedb's markup changes. Add this to the Phase-6 patch-day
  runbook.
