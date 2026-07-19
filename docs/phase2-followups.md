# Phase 2 — tracked follow-ups (for later)

Recorded from the final whole-branch review. None are merge-blocking; each is a
known limitation or cleanup with a deliberate reason to defer.

## Behavioral (track — worth fixing before T2 factory output is trusted on partial data)

- **MC renormalization biases P10/P50/P90 on partially-priced tables.**
  `oracle/scanner/factory.py` renormalizes the Monte-Carlo sampling distribution
  over only the *resolved* outcomes (conditions on "a priced outcome happened"),
  whereas the analytic EV simply *excludes* the unresolved probability mass. For
  fully-resolved tables (the golden-test path) and fully-unresolved tables
  (fail-visible `-input_spend`) this is correct. But for **partially**-resolved
  tables the factory P10/P50/P90 are optimistically biased vs. the analytic EV.
  This is exactly the current pre-tuning state (seed tables have unresolved
  outcomes on live data). **Once the seed odds-table item keys are tuned to match
  live poe.ninja strings (see below), tables become fully resolved and the bias
  disappears** — so tuning likely resolves this in practice. If partially-priced
  tables are ever intended to be actionable, decide: redistribute mass (current)
  vs. exclude-and-scale-down (analytic-consistent), and make MC match the EV
  semantics. A code comment marks the spot.

- **Scan-integrated T2 rows don't yet carry a bankroll-fit note.**
  `T2Service.evaluate` accepts a `bankroll` param that isn't threaded into
  `EvEngine.evaluate`, so the scan report's Tier-2 rows have an empty
  `bankroll_note`. The `oracle factory` command IS the full bankroll-fit surface
  (attempts affordable, P(net loss), P10/P50/P90). To also annotate scan rows,
  thread a configured/default bankroll through the scan path, or drop the unused
  param.

## Data tuning (Zac's economic-judgment pass)

- **Seed odds tables' item keys resolve to `missing:`/unresolved on live
  poe.ninja.** Like the Phase 1 transform keys, the `data/odds_t2/*.yaml` outcome
  `PriceRef` keys are illustrative and need one pass to match live poe.ninja item
  names/categories. This is rules-as-data tuning, not a code defect. Until tuned,
  the live T2 scan shows unresolved outcomes and the factory returns full-loss
  projections. **DoD item requiring Zac's manual sign-off:** judge that tuned T2
  opportunities are sane.

## Cosmetic / minor

- `oracle/scanner/report.py` header still says "Oracle Tier-1 Scan" though the
  report now includes a Tier-2 section — rename to "Oracle Scan" or similar.
- `oracle/scanner/bankroll.py` `analytic_ev` and `prob_net_loss_after` are tested
  but not wired into a production path yet (library surface for future use).
