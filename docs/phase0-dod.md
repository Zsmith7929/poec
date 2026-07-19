# Phase 0 Definition of Done — Verification Record

**Date:** 2026-07-19
**Branch:** phase-0-foundations
**Suite:** 43 tests, all green. 2 live tests deselected by default (marked `@pytest.mark.live`).

---

## Live Test Status

### Network Reachability

The environment has outbound network access. Both `api.pathofexile.com` (league list) and `poe.ninja`
(price data) respond over HTTPS. **NinjaClient was migrated to the new `/poe1/api/economy` endpoints
in Task 15.** The new `LEAGUES_URL` (`/poe1/api/economy/leagues`) and `OVERVIEW_URL`
(`/poe1/api/economy/exchange/current/overview`) are live and responding 200.

### Live Test Results

Command: `uv run pytest -m live -v` (run 2026-07-19)

```
PASSED tests/test_live_smoke.py::test_leagues_live
PASSED tests/test_live_smoke.py::test_prices_currency_live

2 passed, 43 deselected in 1.08s
```

**Both live smoke tests now pass.** Standard, Hardcore, Mirage, and Hardcore Mirage are
ninja-covered (`ninja_available=True`). Real currency prices returned for Standard.

---

## CLI Smoke Results

### `uv run oracle leagues`

Network: LIVE (GGG league API + poe.ninja leagues API both responded, 2026-07-19).

```
Standard	pc	ninja
Hardcore	pc	ninja
Solo Self-Found	pc	no-ninja
Hardcore SSF	pc	no-ninja
Ruthless	pc	no-ninja
Hardcore Ruthless	pc	no-ninja
SSF Ruthless	pc	no-ninja
Hardcore SSF Ruthless	pc	no-ninja
Mirage	pc	ninja
Hardcore Mirage	pc	ninja
SSF Mirage	pc	no-ninja
HC SSF Mirage	pc	no-ninja
Ruthless Mirage	pc	no-ninja
HC Ruthless Mirage	pc	no-ninja
SSF R Mirage	pc	no-ninja
HC SSF R Mirage	pc	no-ninja
```

Status: **PASS** — league list retrieved from live GGG API; Standard, Hardcore, Mirage, and
Hardcore Mirage correctly flagged `ninja` via the new `/poe1/api/economy/leagues` endpoint.

---

### `uv run oracle prices currency --league Standard`

Network: LIVE (poe.ninja new economy API responded, 2026-07-19).

Output (sample — 93 lines total):
```
Orb of Scouring	1.27c	depth=4541	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Divine Orb	778.50c	depth=120275	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Chaos Orb	1.00c	depth=120275	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Orb of Conflict	1819.00c	depth=70323	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Fracturing Orb	1753.00c	depth=87060	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Mirror of Kalandra	1219806.00c	depth=17890485	conf=0.88	ninja:currency	2026-07-19T00:20:31...
Exalted Orb	11.23c	depth=11807	conf=0.88	ninja:currency	2026-07-19T00:20:31...
...
```

Status: **PASS** — 93 real currency prices returned from poe.ninja Standard via new endpoint.
Note: item-category `type` values (e.g. `UniqueWeapon`, `Fossil`, `Essence`, `DivinationCard`)
should be validated against poe.ninja's supported type list before adding new category support.

---

### `uv run oracle modpool "Vaal Regalia" --ilvl 86`

Network: NOT REQUIRED (uses local RePoE snapshot).

Output (truncated):

```
of the Pupil       suffix  Intelligence              w=1000
of the Student     suffix  Intelligence              w=1000
...
Hale               prefix  IncreasedLife             w=1000
...
Shining            prefix  BaseLocalDefences         w=1000
...
Protective         prefix  DefencesPercent           w=1000
...
Djinn's            prefix  DefencesPercentAndStunRecovery  w=1000
...
Monk's             prefix  BaseLocalDefencesAndLife  w=1000
...
of the Newt        suffix  LifeRegeneration          w=1000
...
of the Whelpling   suffix  FireResistance            w=1000
...
of the Inuit       suffix  ColdResistance            w=1000
...
of the Cloud       suffix  LightningResistance       w=1000
...
of the Lost        suffix  ChaosResistance           w=250
...
of Thick Skin      suffix  StunRecovery              w=1000
...
Thorny             prefix  AttackerTakesDamageNoRange  w=1000
...
of the Worthy      suffix  LocalAttributeRequirements  w=850
...
of Enlivening      suffix  EnergyShieldDelay         w=1000
...
```

Status: **PASS** — mod pool returned from local RePoE snapshot. Mod groups match expected armour
pool (energy shield base with ES-focused mods, resistances, life, attribute requirements).

**MANUAL (Zac):** Spot-check 3 bases against poedb.tw to verify weights and mod groups are
correct. Recommended bases: Vaal Regalia, Titanium Spirit Shield, Astral Plate.

---

### `uv run oracle link "Titanium Spirit Shield" --ilvl 86 --league Standard`

Network: NOT REQUIRED (builds URL locally, no external call).

Output:
```
https://www.pathofexile.com/trade/search/Standard?q=%7B%22query%22%3A%7B%22status%22%3A%7B%22option%22%3A%22online%22%7D%2C%22type%22%3A%22Titanium%20Spirit%20Shield%22%2C%22filters%22%3A%7B%22type_filters%22%3A%7B%22filters%22%3A%7B%7D%7D%2C%22misc_filters%22%3A%7B%22filters%22%3A%7B%22ilvl%22%3A%7B%22min%22%3A86%7D%7D%7D%7D%7D%2C%22sort%22%3A%7B%22price%22%3A%22asc%22%7D%7D
```

Decoded JSON payload:
```json
{
  "query": {
    "status": { "option": "online" },
    "type": "Titanium Spirit Shield",
    "filters": {
      "type_filters": { "filters": {} },
      "misc_filters": { "filters": { "ilvl": { "min": 86 } } }
    }
  },
  "sort": { "price": "asc" }
}
```

Status: **PASS** — URL generated correctly, encodes `type`, `ilvl` filter, `online` status, and
`price asc` sort. URL structure matches the trade site deep-link format documented in
`docs/trade-deeplinks.md`.

**MANUAL (Zac):** Open URL in browser for 3 ItemSpec variations to confirm pre-population:
1. `oracle link "Titanium Spirit Shield" --ilvl 86 --league Standard` (base only)
2. A spec with one mod filter (e.g. `+#% to maximum Energy Shield`)
3. A spec with 2+ mod filters and influence

---

## Phase 0 DoD Checklist

| DoD Item | Status | Evidence |
|---|---|---|
| Repo scaffold (pyproject, src layout, pre-commit) | PASS | Task 1; `uv run pytest` green |
| Single settings file (`config/settings.yaml`) | PASS | Task 2; `test_config.py` |
| League Service (`list_leagues`, ninja probe) | PASS | Task 5; `test_league_service.py`; live GGG API responds |
| Game Data Service (RePoE snapshot, `mods_for`) | PASS | Task 6; `test_gamedata.py`; `oracle modpool` works live |
| Ninja Client (currency/item overview, league probe) | PASS | Task 15; migrated to `/poe1/api/economy` endpoints; `test_ninja_client.py` (11 tests, mocked + drift cases) |
| Price Service (percentile+outlier, liquidity, maturity, SQLite, source-tagged) | PASS | Tasks 8–9; `test_price_service.py`, `test_aggregate.py`, `test_maturity.py`, `test_store_db.py` |
| ListingResolver + DeepLinkResolver (ItemSpec, URL, observed-price record/retrieve/expire) | PASS | Tasks 10–11; `test_listings.py`, `test_observations.py` |
| CLI `leagues` | PASS | Live output above; all 16 GGG leagues listed with ninja flag |
| CLI `prices currency` | PASS | Live: `uv run oracle prices currency --league Standard` → 93 real prices returned (2026-07-19) |
| CLI `modpool` | PASS | Live output above; mod pool for Vaal Regalia ilvl 86 returned from local snapshot |
| CLI `link` | PASS | URL generated and decoded above; encodes type + ilvl correctly |
| Trade deep-link pre-populates in browser (3 specs) | MANUAL (Zac) | Open decoded URLs above in browser to verify trade search pre-populates |
| poedb mod-pool spot-check (3 bases) | MANUAL (Zac) | Compare `oracle modpool` output for Vaal Regalia, Titanium Spirit Shield, Astral Plate vs poedb.tw |
| Observed-price round-trip (MCP/manual flow) | MANUAL (Zac) | Unit tests pass (`test_observations.py`); end-to-end MCP flow requires MCP client configured |
| Compliance allowlist test | PASS | Task 13; `test_compliance.py` |
| Live smoke tests written + registered | PASS | `tests/test_live_smoke.py`; `uv run pytest` deselects them (2 deselected); `uv run pytest -m live` runs them |
| Live tests pass vs real data | PASS | `uv run pytest -m live -v` → 2 passed (2026-07-19); new `/poe1/api/economy` endpoints live |
| mypy strict on `oracle/` | PASS | `uv run mypy` → "no issues found in 22 source files" |
| ruff clean | PASS | `uv run ruff check .` → "All checks passed!" |
| Non-live suite green | PASS | 43 passed, 2 deselected, 0 failures |

---

## Summary

All automated DoD items PASS. Three items remain MANUAL (Zac must verify in a browser and
against poedb): trade deep-link pre-population, mod-pool accuracy spot-check, and observed-price
MCP round-trip. The live pytest tests pass against real poe.ninja data (2026-07-19) after the
Task 15 migration to the new `/poe1/api/economy` endpoints.
