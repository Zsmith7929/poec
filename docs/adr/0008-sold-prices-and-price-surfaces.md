# ADR-0008: Sold-price semantics, price-surface consistency, and reward variants

- **Status:** Accepted
- **Date:** 2026-07-19
- **Supersedes:** the *directional bracketing* half of ADR-0007 (buy-high/sell-low). The
  *margin-confidence floor* from ADR-0007 stays.
- **Related:** ADR-0002 (price/metadata separation), ADR-0006 (div-card class).

## Context

A live scan reported "8× The Eye of Terror → Mageblood, +62%". At real prices it is a
**loss**. Debugging exposed two distinct defects:

1. **Reward variant dropped.** poedb gives The Eye of Terror a **Foulborn Mageblood** —
   the card row is `<span class="uniqueitem">Mageblood</span> … {Foulborn}`, where the
   `{Foulborn}` variant tag trails the item span and poe.ninja renders it as the prefix
   "Foulborn Mageblood". The harvester captured only "Mageblood", so the tool priced the
   wrong item.
2. **Mixed price surfaces.** The card (buy) leg is priced from poe.ninja's currency-
   **exchange** feed (an *actually-transacted* rate — 8 div/card), while the unique
   reward (sell) leg is priced from the **stash** feed (a *listing/ask* price — 100 div).
   There is no stash feed for divination cards (404) and no exchange feed for uniques, so
   a `card → unique` flip *structurally* compares a transacted buy price against an ask
   sell price. That mismatch — far larger than the 20% noise floor — is the whole "+62%".

**Operator preference (recorded):** value transforms on **actually-sold prices**, not on
buy/sell ask-spread modeling. The exchange feed is the sold-price surface we have;
uniques/bases have only ask (stash) data, and the trade API (real sale velocity) is
off-limits by compliance. So we cannot make everything "sold" — we can be consistent
about what each price *is* and stop counting a cross-surface spread as profit.

## Decision

1. **One sold-proxy price per item.** Drop ADR-0007's directional buy/sell bracketing;
   both legs use a single price (`buy_percentile` set equal to `percentile`, neutralizing
   the bracket). This matches the "sold prices, no ask/bid nuance" preference. The
   mechanism is retained but inert, so it can be re-enabled if ever wanted.
2. **Flag cross-surface margins.** A transform whose output is priced on a different
   surface than *any* of its inputs (exchange vs stash) is marked
   `margin_confidence = "thin"` and ranked below firm rows — its margin mixes a
   transacted price with an ask price and runs optimistic. Same-surface flips (currency
   vendor recipes; base-vs-base influence flips) are unaffected.
3. **Capture the full reward name,** including a trailing `{Variant}` qualifier
   (Foulborn, etc.), so the reward resolves to the actual item, not the clean one.

## Consequences

- Eye of Terror (card=exchange, reward=unique/stash) is now flagged thin and demoted;
  currency vendor recipes and base flips stay firm.
- The noise floor (ADR-0007) still catches within-surface phantoms like History.
- Honest limitation remains: uniques/bases have only ask prices; a card→unique margin is
  inherently optimistic and is surfaced as such, never as a firm edge. Fully resolving it
  needs sold-price data we deliberately don't collect (ADR-0004 human-judgment stance).
