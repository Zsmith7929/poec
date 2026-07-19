# ADR-0007: Conservative margin bracketing + a margin-confidence floor

- **Status:** Accepted
- **Date:** 2026-07-19
- **Related:** ADR-0004 (surface candidates, not exact EV), ADR-0005 (demand).

## Context

A live scan reported "5× History → 2× Hinekora's Lock, +12%". At real trade prices it is
a **−2.5% loss**. Debugging the reconciliation exposed three compounding causes:

1. **Wrong price surface (structural).** The tool prices from poe.ninja's currency-
   *exchange* feed, whose bulk rates run ~12–18% below trade-site prices (History 287 vs
   ~340 divine; Hinekora 739 vs ~829). Even raw-feed ratios show a ~+3% phantom because
   the exchange ratio ≠ the trade-site ratio. We deliberately can't use the trade API
   (compliance), so this gap is inherent to our data.
2. **Symmetric aggregation drifting asymmetrically (amplifier).** Both legs used the
   same 15th-percentile aggregate. The sell leg drifted *above* its own current price
   (stale-high history + outlier rejection), while the buy leg tracked current —
   manufacturing spread and pushing +3% → +12%.
3. **No spread/slippage model.** It compared bulk-mid to bulk-mid; real execution buys
   at ask and sells at bid.

The unifying insight: **the reported margin was smaller than the tool's own pricing
error (~15–20%).** Low-headroom rows (History 12%, Slumbering 20%, Divine Beauty 10%)
are noise; high-headroom rows (Eye of Terror 62%, The Demon 80%) survive it.

## Decision

1. **Directional bracketing.** Price the *buy* side (transform inputs) at a high
   percentile (`buy_percentile`, default 0.85 — what you'll actually pay) and the *sell*
   side (the output) at a low percentile (`sell_percentile`, default 0.15 — what you'll
   actually get). This removes aggregation-manufactured spreads and builds in a margin of
   safety. `Price` carries both `buy_value` and `sell_value`; the engine sums input
   `buy_value` and takes output `sell_value`.
2. **Margin-confidence floor.** An auto row whose `margin_pct` is below `min_margin_pct`
   (default 0.20) is marked `margin_confidence = "thin"` — it is within pricing noise, so
   it is ranked *below* firm rows and rendered with a ⚠, not presented as a clean
   opportunity. Verify-mode (human-priced) rows are exempt (already human-judged).

## Consequences

- Phantom margins from the aggregation asymmetry disappear; the residual structural
  exchange-vs-trade-site gap is caught by the floor rather than silently ranked.
- Verified: History drops from +12% toward/through zero and is flagged thin; the
  high-headroom flips (Eye of Terror, The Demon, Headhunter cards) stay firm and ranked.
- We still cannot see true trade-site prices (compliance), so the floor is a margin of
  safety, not precision — consistent with ADR-0004 (surface for judgment).
- Thin data (a single snapshot) yields `buy_value == sell_value`; bracketing only bites
  once a distribution exists, so it never invents a spread from nothing.
