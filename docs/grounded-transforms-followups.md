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

## Stash-endpoint price support — DONE (follow-up PR to #5)

Implemented: `NinjaClient.stash_overview` + parser (`StashLine` with variant/ilvl),
`PriceService` routing (`STASH_TYPES` → stash; currency-like → exchange), `Price`
gains `variant`/`ilvl` with a variant-qualified `storage_key()`, and the resolver does
variant-aware matching (base-type refs match influence-set + ilvl; name-only refs like
uniques collapse to the most-liquid variant). Verified live on Standard: Headhunter
13,570c; the flagship `crusader_shield_base_influence` auto-prices end-to-end (plain
Titanium ilvl84 10c + Crusader's Exalted Orb → Crusader base, +4,129c / 360% — a
selection-biased *candidate* per ADR-0004, not guaranteed profit).

- Fixed while wiring this: the flagship seed had used the **defunct** "Shaper's Orb"
  (a recollection error — the very failure mode ADR-0003 targets). Replaced with the
  Conqueror exalt (Crusader's Exalted Orb), which is real and in the currency feed.

## Transform classes

- **Div-card → reward — SHIPPED** (ADR-0006). Harvested 444 cards from poedb
  (`data/metadata/divination_cards.yaml`, cited); expander emits the 296 currency/unique
  rewards (79 card-legs priced on the DivinationCard feed). Reward priced by name across
  kind-scoped feeds. Verified live: The Doctor → Headhunter prices end-to-end (currently
  −51%, correctly gated). Remaining: `other`-kind rewards (bases/gems/maps/multi-item,
  148 cards) — need base variant keying / gem+map feeds; deferred.
- **Influence base flips** — the flagship works; generalizing to more bases/influences
  is a data-authoring pass (enumerate base × influence × ilvl from the `BaseType` feed,
  or hand-author high-value ones). Pricing is selection-biased — surfaced for judgment.

## Demand / tradeability (ADR-0005)

Shipped (follow-up PR): a `demand` label (`active`/`thin`/`unknown`) per price and scan
row, so mirage margins (fat gap off 1–2 stale, non-moving listings) get flagged ⚠ instead
of ranking as clean opportunities. Stash confidence now derives from `count`
(observations), not `listingCount` (supply). Deferred, needs history (Phase 6):

- **Margin persistence/decay** — the strongest demand proxy we can own: a margin that
  never closes across scans is illusory; one that closes fast was real demand. Belongs
  with the Phase-6 margin-decay analytics over the append-only snapshot history.
- **Listing-count trajectory** — rising supply + flat price = glut = weak demand.
- **Input-leg demand** — the row's demand currently reflects the sell (output) leg only;
  a thin *input* (can't actually buy the cheap side) could also be surfaced.
- **Persist `demand` on `scan_results`** — currently report-only (no DB column); add it
  when wiring margin-decay so demand history is queryable.
- **Threshold tuning** — `demand_label` reuses `min_sample_depth` and a 1% movement
  epsilon; revisit once history exists to calibrate false-positive rate.

## Performance note (surfaced while testing)

The stash `BaseType` feed is large (~9k lines); a scan touching it fetches and inserts
~9k snapshots and does a `recent_values` lookup per line. `price_snapshots` has no index
on `key`, so this degrades as history grows. Add an index on `(league, category, key)`
(or scope base-type harvesting to the bases actually referenced by transforms) before
base-type scanning is run routinely. Not a correctness issue.

## Notes / smaller follow-ups

- Stash prices skip the historical percentile aggregate benefits only as history
  accumulates; variant-qualified `storage_key()` keeps base variants from sharing a
  series in `price_snapshots` (no schema change needed).
- Maturity's `recent_depths` now also sees stash `listingCount`s (slightly broadens the
  league-wide signal); acceptable, revisit in Phase 6 if it skews false-positive tuning.
- Runes/Oils in the vendor-recipe file still price as `missing:` (separate ninja feeds);
  mapping those feeds is a small future addition.

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
