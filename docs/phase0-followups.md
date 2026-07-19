# Phase 0 — tracked follow-ups (for Phase 1+)

Recorded from the final whole-branch review. None are merge-blocking for Phase 0;
each is a known limitation or forward-looking cleanup with a deliberate reason to
defer.

## Functional

- **Maturity volatility signal is not yet wired.** `PriceService.maturity()` passes
  an empty `recent_values` list to `maturity_signals`, so the volatility term
  (`0.25 * (1 - volatility)`) always contributes 0; the score currently reflects
  sample depth + history density only. This is deferred deliberately: volatility is
  only meaningful once multiple price snapshots accumulate per key over time (a fresh
  DB has one observation per key, so volatility is undefined/zero regardless). Wiring
  it belongs with the margin/price-history work (PRD Phase 6). Fix when history
  exists: add a repo query returning recent per-key value series for a league and feed
  it into `maturity_signals`.

- **Non-currency category routing is unvalidated.** `PriceService.prices(category,
  league)` passes any non-`currency` category straight through as the poe.ninja `type`
  param. A category string that isn't a valid poe.ninja `type` won't fail loud. Phase 1
  should validate category against poe.ninja's supported type list (and add the
  `item_overview` routing test).

## Config (reserved, intentionally unwired in Phase 0)

- `cache.ninja_ttl_seconds` and `cache.league_ttl_seconds` are defined and validated
  but not yet consumed — no poe.ninja/league response caching layer exists yet
  (Phase 1). `observed_price_ttl_seconds` IS used.
- `default_league` is loaded/validated but not used as a CLI fallback; every command
  requires `--league` explicitly (keeps the CLI league-agnostic and unambiguous). Wire
  it as a fallback default if/when that UX is wanted.

## Test coverage gaps (low risk)

- `prices` and `link` CLI commands have no CLI-layer tests (their underlying services
  `PriceService`/`DeepLinkResolver` are well tested; only the thin Typer glue is
  uncovered).
- `PriceService` test doesn't assert `ts` is tz-aware (production code is correct;
  add `assert p.ts.tzinfo is not None`).

## Housekeeping

- CI `astral-sh/setup-uv@v3` and `.pre-commit-config.yaml` pins (ruff `v0.5.0`, mypy
  `v1.10.0`) are stale; bump in a maintenance pass.
- `snapshots/repoe/manifest.json` carries an extra `base_items_source` key (inert;
  `from_snapshot` reads only `fetched_at`).

## Note on poe.ninja API migration (handled in Phase 0)

During Phase 0 verification, poe.ninja was found to have retired its classic
`/api/data/currencyoverview` / `itemoverview` endpoints (now HTTP 404) in favor of
`/poe1/api/economy/exchange/current/overview`. `NinjaClient` was migrated to the new
API (see `docs/` and the git history); live pricing against Standard is confirmed
working. This is exactly the "poe.ninja API drift (unversioned)" risk called out in
the PRD; the patch-day runbook (Phase 6) should include re-verifying these endpoints.
