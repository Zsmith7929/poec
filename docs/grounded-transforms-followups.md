# Grounded transforms — tracked follow-ups

From the grounded-transform reseed (ADR-0001..0004). None block this PR; each is a
deferral with a concrete reason and evidence.

## CORRECTION (2026-07-19, after PR #5)

An earlier version of this file claimed uniques/base-types are unpriceable and deferred
influence flips + div-card→reward "with evidence." **That was wrong** — it came from
guessing endpoint URLs instead of reading `https://poe.ninja/docs/api`. poe.ninja
exposes a **second** overview family the tool wasn't using:

- **`/poe1/api/economy/stash/current/item/overview?league=&type=`** — stash-listed
  items. Types include `UniqueWeapon`, `UniqueArmour`, `UniqueAccessory`, `UniqueJewel`,
  `BaseType`, `SkillGem`, etc. Verified live on Standard: `UniqueAccessory`=372 lines
  (Headhunter = 13,570c / 18 div, 667 listings), `BaseType`=9,092 lines, `UniqueWeapon`
  =656, `SkillGem`=6,442.
- **Response shape differs from the exchange endpoint.** Data is inline in `lines`
  (`items` is empty): each line has `name`, `chaosValue`/`divineValue`, `count`,
  `listingCount`, `itemType`, `levelRequired`, and `detailsId`. Influence + ilvl
  variants are encoded in `detailsId` (e.g. `titanium-spirit-shield-84-shaper-hunter`
  vs `titanium-spirit-shield-84-crusader-redeemer`).

So uniques/bases/gems ARE priceable; the flagship shaper-shield flip is priceable; and
the deferred classes below are **feasible**, not blocked — they just need the tool to
call the stash endpoint. The currency-vendor-recipe work in PR #5 is unaffected
(currency prices via the exchange endpoint, correctly).

## Deferred transform classes (feasible; need stash-endpoint pricing support)

Blocked only on adding stash-endpoint support to the price layer (see next section),
not on any missing data:

- **Influence base flips.** `BaseType` feed carries plain and influenced variants
  (distinguished by `detailsId`). Needs variant-aware keying (name + influence + ilvl →
  `detailsId`) since the current resolver keys by name alone. Pricing is selection-
  biased — surfaced for human judgment (ADR-0004).
- **Div-card → reward.** Harvest de-risked (poedb `Divination_Cards`, 459 cards, set
  size + reward; House of Mirrors = 9 → Mirror verified). Rewards that are uniques
  (Headhunter etc.) are now priceable via the stash endpoint; reward→category routing
  is the remaining work.

## Next enabling work: stash-endpoint price support

The tool currently calls only the exchange overview (currency-like feeds). To unlock the
classes above (and future phases that assume unique/base/gem pricing):

- Add a `stash_overview(league, type)` path to `NinjaClient` with its own parser for the
  inline-`lines` shape (name/chaosValue/listingCount/detailsId), keeping the existing
  exchange parser for currency-like types.
- Route categories to the right endpoint in `PriceService` (Currency/Fragment/
  DivinationCard → exchange; Unique*/BaseType/SkillGem → stash).
- For base types, key on the `detailsId` variant (influence + ilvl), not just name.
- This is the highest-leverage single addition: it lights up uniques, bases, gems, the
  flagship, influence flips, and div-card→unique rewards.

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
