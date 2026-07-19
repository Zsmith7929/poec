# ADR-0003: Transforms must be grounded, never fabricated

- **Status:** Accepted
- **Date:** 2026-07-19
- **Supersedes:** PRD §9 Phase 1 "Seed with ~20 transforms…" as-built. The seeded
  `data/transforms_t1.yaml` is deprecated pending a grounded rebuild.

## Context

The Phase 1 seed transforms were authored from a model's *recollection* of PoE
mechanics — the exact hallucination surface the deterministic design was meant to
avoid. The result included fabricated recipes such as "20 Chaos Orbs → 1 Awakener's
Orb" (reported as an 11,575% margin), a conversion that does not exist in the game.

Two distinct failure modes were identified, which must not be confused:

1. **Key mismatch** — a *real* recipe whose item key string doesn't match live
   poe.ninja, so a leg won't price. Surfaces as a `—` (missing) row. *Fixable by
   correcting the key.*
2. **Fictitious recipe** — the recipe *itself* isn't a real mechanic. It may price
   fine and produce an absurd margin. *Not fixable by tuning; must be deleted.*

Rewriting the seed from the same source (recollection) would just produce
more-convincing fiction. The fix is grounding, not "remembering harder."

## Decision

**Every transform must be grounded in a checkable source. None may be authored from
recollection.** A transform qualifies for inclusion only if its structure is either:

- **(a) Self-evidencing from feed structure** — the relationship is inherent in the
  data itself, nothing asserted. *Example: influence-base flips — the plain base and
  the influenced base are two lines in poe.ninja's base-type feed, and the influence
  orb is the documented thing that relates them.*
- **(b) Grounded in a cited metadata-table row** sourced from poedb (ADR-0001).
  *Example: divination card → reward (set size + reward from poedb, verified), or a
  vendor recipe.*

Metadata that is *not* self-evidencing from a price feed and *not* backed by a cited
row does not ship.

### Taxonomy of transform classes (living reference)

| Class | Grounding | Notes |
|---|---|---|
| Influence-base flips | (a) self-evidencing | In scope. Pricing is selection-biased; surfaced for human judgment — see ADR-0004. |
| Divination card → reward | (b) cited metadata | Deterministic (fixed output, no roll). Needs poedb set-size + reward; **not** in the poe.ninja feed. |
| Vendor recipes | (b) cited metadata | Fixed rules not derivable from prices; cite poedb. |
| Currency/card appreciation | (a) self-evidencing over time | A hold/speculation, not a conversion; requires accumulated snapshot history. |

## Consequences

- The existing fabricated entries in `data/transforms_t1.yaml` are deleted, not
  rewritten. The registry is rebuilt from grounded classes, starting small.
- Registry validation should, where feasible, enforce that each entry declares its
  grounding (self-evidencing vs cited-metadata-key) so an ungrounded entry can't be
  added silently.
- An absurd margin (very high margin%) is treated as a **data/grounding defect to
  investigate**, never as a discovered opportunity, until proven real.
