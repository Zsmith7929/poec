# ADR-0009: Divination card reward variants — capture, but don't price qualified rewards

- **Status:** Accepted
- **Date:** 2026-07-19
- **Refines:** ADR-0006 (div-card class), ADR-0008 (which point-fixed only `{Foulborn}`).

## Context

ADR-0008 captured a `{Foulborn}` reward variant, but that was the rarest case. Surveying
poedb's divination-card rewards shows variants are common and appear as **separate
qualifier spans after the item**, not in braces:

- `<span class="corrupted">Corrupted</span>` — **115 cards**
- `<span class="augmented">+20%</span>` after `Quality:` — 22 (quality gems)
- gem `Level 21 …` — 22
- `<span class="enchanted">Synthesised</span>` / implicit counts — a handful
- Fractured, Foulborn, influence — a few each

So a reward is often a **spec** (item + corrupted/synthesised/quality/level/…), or a
**generic category** ("Minion Gem", "Two-Stone Ring"). The tool currently drops the
qualifier and matches the *clean* item's price — silently wrong (a corrupted or
synthesised item is not the clean one; a generic category isn't a single priced line).

We can't reliably price these from poe.ninja by name: corruption/synthesis/quality are
encoded inconsistently (variant fields, separate lines, or not at all), and generic
categories have no single price. Matching to the clean item fabricates a price.

## Decision

**Price a divination-card reward only when it is a plain, unqualified named item.**

- The parser captures any qualifier into a `reward_variant` string (e.g. "Corrupted",
  "Synthesised", "Foulborn", "Quality +20%"), so the metadata is complete — the info is
  recorded, not dropped.
- The expander emits a priced transform only when `reward_variant` is empty (plain
  reward). Qualified rewards are recorded in the metadata file but **not** emitted as
  priced opportunities — better absent than wrong.
- This supersedes ADR-0008's Foulborn-as-priced special case: Foulborn is now recorded
  as a variant and left unpriced like the others (and it was already cross-surface
  `thin` per ADR-0008, so no real opportunity is lost).

## Consequences

- The class of silently-wrong reward prices (variant matched to clean item) is
  eliminated.
- ~150 variant/generic-reward cards become metadata-only records rather than priced
  rows; most were div-card→unique (already cross-surface `thin`), so little firm signal
  is lost. Plain rewards — chiefly div-card→currency (Mirror, Divine, Exalted) and plain
  uniques — still price (uniques remain cross-surface `thin` per ADR-0008).
- The captured `reward_variant` leaves the door open to real variant pricing later
  (e.g. matching poe.ninja's corrupted/gem variant lines), without another metadata pass.
