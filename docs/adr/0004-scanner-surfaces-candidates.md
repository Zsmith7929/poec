# ADR-0004: The scanner surfaces candidates for human judgment, not exact EV

- **Status:** Accepted
- **Date:** 2026-07-19
- **Amends:** PRD §2 proof-of-concept ("A purely deterministic transform"); PRD §7.3
  Tier-1 definition, for the influence-flip class specifically.

## Context

The flagship case (plain base + influence orb vs. influenced base) was framed as a
*purely deterministic* Tier-1 transform. It isn't, quite:

- An influence orb rolls a **random** influence mod from a pool.
- poe.ninja's price for the influenced base is an **aggregate of what people list**,
  skewed toward desirable rolls (junk rolls get rerolled away).

So the listed price ≈ a *good* influenced base, while one orb yields a *random* one.
The naive margin can be a mirage. Strictly, this is probabilistic with a
selection-biased price — not clean Tier-1 arithmetic.

The product response, however, is deliberate: **it is not the tool's job to be
accurate to a T. It is the tool's job to surface real possibilities.** If poe.ninja
says influenced shields sell 20c above (plain base + Shaper's Orb), the operator
wants to *see that* and decide for themselves why the gap exists ("oh, everyone's
rerolling") — with their own eyes on the list. Sometimes the gap is a genuine edge
(the flagship was farmed profitably for weeks); the human distinguishes.

## Decision

The scanner **surfaces grounded candidate opportunities for human judgment**; it does
not claim to compute exact realized profit for classes with hidden variance.

- Influence-base flips stay **in scope** and are surfaced whenever a margin exists,
  precisely so the human can eyeball the "why."
- Where a class carries known hidden variance (selection bias, random roll), the tool
  should make that legible (flag/annotate) rather than either suppress the row or
  present the margin as exact.
- This does not lower the bar on *grounding* (ADR-0003): candidates must still be
  real recipes. "Surface for judgment" applies to *valuation* uncertainty, never to
  *existence* uncertainty.

## Consequences

- The flagship class is retained despite not being cleanly deterministic; its margin
  is a lead to investigate, not a guaranteed number.
- Reports aimed at a human reviewer are the primary Tier-1 surface. Full-accuracy EV
  is reserved for classes where it's genuinely computable (deterministic fixed-output
  recipes; the Tier-2 odds-table engine).
- "Accuracy to a T" is an explicit non-goal for variance-bearing Tier-1 classes.
