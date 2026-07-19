# ADR-0001: poedb is the canonical source of truth for PoE metadata

- **Status:** Accepted
- **Date:** 2026-07-19
- **Supersedes:** PRD §8 data-sources row for poedb ("Reference only in v1. Do not
  scrape programmatically."); PRD §2 framing of RePoE/pypoe-style exports as the
  metadata backbone.

## Context

Transforms need two different kinds of fact:

1. **Prices** — what an item is worth right now. Sourced from poe.ninja.
2. **Metadata / mechanics** — what a recipe *is*: does a conversion exist, what are
   its inputs/outputs, a divination card's set size and reward, a vendor recipe's
   ingredients, an item's mod pool. This is *not* price data.

The failure that triggered this work (see ADR-0003) came from authoring metadata
from model recollection. We need a single authoritative, checkable source for
metadata so no fact is ever guessed.

Candidate machine-readable sources were evaluated:

- **pypoe-json** (`erosson/pypoe-json`) — proposed as a clean JSON dump. **Rejected.**
  Two disqualifying findings, verified directly:
  - **Abandoned:** last commit `2021-03-15`. "Auto-updated" stopped being true over
    five years ago; it cannot track current leagues or patches.
  - **Incomplete for our needs:** the divination-card export contains only
    `DivinationCardArt` (card → image) and a stash-layout file. **No set size, no
    reward.** The "9 cards → Mirror of Kalandra" fact simply is not in it — reward
    mapping is one of the things messy in raw game data, which is exactly what poedb
    computes for us.
- **poe.ninja** — prices only; cannot attest that a recipe exists (see ADR-0002).
- **RePoE snapshot** (already vendored) — good for mod weights / base items; does not
  cover div-card rewards, vendor recipes, or many cross-item mechanics.
- **poedb** — current (tracks live patches), and actually carries the data. Verified:
  its House of Mirrors page states set size 9 → Mirror of Kalandra. Exposes both HTML
  and `json.php` endpoints.

## Decision

**poedb is the single source of truth for all PoE metadata** — cards, recipes, item
mechanics, mod data cross-reference. Whenever we have a metadata question, poedb is
the rock we build on.

- Extract the metadata we need from poedb **once** into a **local, versioned,
  cited metadata table** stored in-repo, alongside the vendored RePoE snapshot.
- Prefer poedb's `json.php` endpoints where they cover the data; fall back to
  targeted parsing of specific pages only where JSON does not. (Which, and how much
  HTML parsing is actually required, is the subject of a follow-up spike.)
- Refresh the metadata table as a **patch-day step**, cited and versioned exactly
  like the RePoE snapshot.

## Consequences

- PRD §8's "poedb: do not scrape programmatically" row is reversed: a one-time,
  cited, dev-time extraction into a vendored table is now the intended path.
- **Runtime compliance is unaffected.** This is dev-time data vendoring, not a
  runtime dependency — the same posture as the existing RePoE snapshot. The shipped
  tool still makes live calls only to the documented GGG league API and poe.ninja
  (PRD §3.3, §5). poedb is never called at scan time.
- A new component is introduced: the metadata table + loader (schema-validated,
  fail-loud, sha256-versioned, source-cited per row), mirroring the existing rule
  registries.
- pypoe-json is not used anywhere.
