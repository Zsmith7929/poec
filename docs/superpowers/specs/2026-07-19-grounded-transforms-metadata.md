# Spec: Grounded transforms via a cited poedb metadata layer

Date: 2026-07-19. Status: approved (Zac, this session). Implements ADR-0001..0004.

## Problem

The Phase-1 `data/transforms_t1.yaml` seed was authored from model recollection and
contained fabricated recipes (e.g. "20 Chaos → Awakener's Orb", a bogus 11,575%
margin). Per ADR-0003, transforms must be *grounded* — self-evidencing from a feed, or
backed by a cited metadata row — never recalled. This replaces the fabricated seed with
a grounded class sourced from poedb, and deletes the fiction.

## Scope decision (evidence-grounded)

Investigated live during design:

- **poe.ninja's new exchange API serves only currency-like categories.** Verified on
  Standard: `Currency`=91 lines, `Fragment`=63, `DivinationCard`=31; **`BaseType`=0,
  `UniqueAccessory`=0**. No current uniques/base-type endpoint was found (classic
  `itemoverview` 404s).
- Consequences:
  - **Ship now — Currency vendor recipes.** All legs are currency → fully priceable
    against the Currency feed. Directly delivers the "2 Jeweller's → 1 Fusing" family.
  - **Defer — influence base flips.** Infeasible on the current API (BaseType empty).
  - **Defer — div-card → reward.** Card set-size + reward harvest is de-risked
    (459 cards parse cleanly from poedb, House of Mirrors = 9 → Mirror verified), but
    the valuable rewards are uniques, unpriceable until a uniques endpoint is found.

Deferred items and the uniques-endpoint gap are recorded in
`docs/grounded-transforms-followups.md`.

## Design

Three parts, mirroring the existing rules-as-data + snapshot patterns.

### 1. Dev-time harvester (`tools/harvest_vendor_recipes.py`)
- Standalone script, **outside the `oracle` package** (not shipped, not subject to the
  runtime HTTP allowlist, not in the compliance scan). Uses its own httpx.
- Fetches poedb `Vendor_recipe_system`, parses the currency-for-currency rows
  (columns: **Offer** = received, **Your Offer** = given (with `Nx` qty), **Note** =
  NPC), keeping only rows whose items are all currency (`item_currency` class).
- Emits `data/metadata/vendor_recipes.yaml` with a citation block (source URL, fetched
  date, page sha256) and one entry per recipe (output item, inputs with qty, npc).
- Cross-checks item names against the live ninja Currency feed and prints a coverage
  report (does not filter the file by coverage — recipe facts are independent of
  pricing, per ADR-0002).
- Re-run on patch day (documented in followups; belongs in the patch-day runbook).

### 2. Runtime metadata layer (`oracle/metadata/`)
- `models.py`: `VendorRecipeItem`, `VendorRecipe`, `VendorRecipeDoc` (Pydantic,
  `extra="forbid"`, fail-loud), including the citation block.
- `vendor_recipes.py`:
  - `load_vendor_recipes(path) -> VendorRecipeDoc` — schema-validated, sha256-versioned,
    fail-loud on unknown shape (mirrors `load_registry`).
  - `expand_vendor_recipes(doc) -> list[Transform]` — pure function; each recipe →
    a `Transform` (id `vendor::<slug>`, `category="Currency"`, `pricing_mode="auto"`),
    reusing the existing `ScanEngine`/`ScanRow` machinery unchanged.

### 3. Composition + seed cleanup
- `build_services` loads the cleaned `transforms_t1.yaml` (hand-authored one-offs) and
  the vendor-recipe metadata, then feeds `registry.transforms + expand_vendor_recipes(...)`
  into a combined `TransformRegistry`. Combined version = `registry.version + "+" +
  doc.version` so reports/persistence stay reproducible.
- `data/transforms_t1.yaml`: fabricated entries deleted. Retains only the flagship
  verify-mode shaper-shield one-off (a real mechanic, human-priced via DeepLinkResolver,
  no fake auto price) as the hand-authored example. The registry file becomes small by
  design; bulk grounded transforms come from the metadata layer.

## Testing
- Metadata models/loader: valid load, sha256 version changes with content, fail-loud on
  unknown shape / missing keys (mirrors `test_registry.py`).
- Parser: a **pinned poedb HTML fixture** (`tests/fixtures/poedb_vendor_recipes.html`)
  → assert exact extraction of a known recipe (e.g. Fusing ← 4× Jeweller's). This makes
  a poedb restyle **fail loud** without network (handles the accepted brittleness once).
- Expander: recipe doc → `Transform` list with correct inputs/output/qty/category.
- Scan integration: a synthetic Currency price table + an expanded vendor recipe →
  a correctly computed margin row (mirrors `test_scan_service.py`).
- Registry tests updated to the grounded reality (the `>=15` fabricated-count assertion
  is removed; structural invariants — unique ids, versioning, fail-loud — retained).
- Compliance: harvester lives in `tools/`, so no new host enters the runtime allowlist;
  data files carry no league names.

## Non-goals (this PR)
- Div-card and influence-flip classes (deferred, see followups).
- Any change to the price pipeline or a new uniques endpoint.
- A generic discovery engine (explicitly rejected — Ship A).
