# PoE Trade Site Deep-Link URL Format

## Overview

The official Path of Exile trade site (`https://www.pathofexile.com/trade/search/<league>`)
accepts a pre-populated search via a URL query parameter `?q=<url-encoded-JSON>`.
The JSON payload is the same query object the site uses internally when you perform
a manual search — the site reads it on page load and populates the search form fields.

This document records the findings of the Phase-0 spike (Task 10) and serves as the
specification that `oracle/pricing/listings.py:_build_query` is written against.

---

## Base URL Pattern

```
https://www.pathofexile.com/trade/search/<league>?q=<url-encoded-JSON>
```

- `<league>` — the league identifier (e.g. `Settlers`, `Standard`, `TestLeagueA`).
  Must be URL-encoded (spaces → `%20`).
- `<url-encoded-JSON>` — the JSON query object (see below), passed through
  `urllib.parse.quote` (percent-encoding, safe characters not escaped).

The code constant is:
```python
TRADE_SITE_BASE = "https://www.pathofexile.com/trade/search"
```

---

## JSON Query Object Structure

```json
{
  "query": {
    "status": {"option": "online"},
    "type": "<base type string>",
    "filters": {
      "type_filters": {
        "filters": {}
      },
      "misc_filters": {
        "filters": {
          "ilvl": {"min": <int>}
        }
      }
    },
    "stats": [
      {
        "type": "and",
        "filters": [
          {"id": "<stat_id>", "value": {"min": <float>}}
        ]
      }
    ]
  },
  "sort": {"price": "asc"}
}
```

Fields:

| Field | Type | Notes |
|-------|------|-------|
| `query.status.option` | `"online"` | Always `"online"` in pre-populated searches |
| `query.type` | string | The item base type (e.g. `"Titanium Spirit Shield"`) |
| `query.filters.type_filters.filters` | object | Item category/rarity filters (empty `{}` in v1) |
| `query.filters.misc_filters.filters.ilvl.min` | int | Minimum item level; omit key if no ilvl constraint |
| `query.stats[].type` | `"and"` | Group operator for stat filters |
| `query.stats[].filters[].id` | string | RePoE stat ID (e.g. `"explicit.stat_3299347043"`) |
| `query.stats[].filters[].value.min` | float | Minimum value for the stat |
| `sort.price` | `"asc"` | Sort by price ascending |

---

## Worked Examples

### Example 1 — Bare Base Type

**Spec:** Titanium Spirit Shield, no other constraints.

**JSON (pretty):**
```json
{
  "query": {
    "status": {"option": "online"},
    "type": "Titanium Spirit Shield",
    "filters": {
      "type_filters": {"filters": {}}
    }
  },
  "sort": {"price": "asc"}
}
```

**Resulting URL (illustrative; actual encoding collapses whitespace):**
```
https://www.pathofexile.com/trade/search/Standard?q=%7B%22query%22%3A%7B%22status%22%3A%7B%22option%22%3A%22online%22%7D%2C%22type%22%3A%22Titanium%20Spirit%20Shield%22%2C%22filters%22%3A%7B%22type_filters%22%3A%7B%22filters%22%3A%7B%7D%7D%7D%7D%2C%22sort%22%3A%7B%22price%22%3A%22asc%22%7D%7D
```

**Human verification:** Opening this URL in a browser should pre-populate the base-type
field with "Titanium Spirit Shield" and show online listings sorted by price.

---

### Example 2 — Base Type + Item Level

**Spec:** Titanium Spirit Shield, ilvl ≥ 86.

**JSON (pretty):**
```json
{
  "query": {
    "status": {"option": "online"},
    "type": "Titanium Spirit Shield",
    "filters": {
      "type_filters": {"filters": {}},
      "misc_filters": {
        "filters": {
          "ilvl": {"min": 86}
        }
      }
    }
  },
  "sort": {"price": "asc"}
}
```

**Residual instructions:** none.

**Expected trade-site behaviour:** The "Item Level" min field is pre-filled to 86.

---

### Example 3 — Base Type + Item Level + Stat Filter

**Spec:** Titanium Spirit Shield, ilvl ≥ 86, `+# to maximum Life` ≥ 80
(stat ID `explicit.stat_3299347043`).

**JSON (pretty):**
```json
{
  "query": {
    "status": {"option": "online"},
    "type": "Titanium Spirit Shield",
    "filters": {
      "type_filters": {"filters": {}},
      "misc_filters": {
        "filters": {
          "ilvl": {"min": 86}
        }
      }
    },
    "stats": [
      {
        "type": "and",
        "filters": [
          {
            "id": "explicit.stat_3299347043",
            "value": {"min": 80}
          }
        ]
      }
    ]
  },
  "sort": {"price": "asc"}
}
```

**Residual instructions:** none (all constraints encoded in URL).

**Expected trade-site behaviour:** Base type pre-filled, ilvl min = 86, one stat
filter row added with the life stat and min value 80.

---

## Residual Instructions Fallback

Some filters **cannot** be reliably encoded in the URL query object in v1 of this
implementation. When a spec contains such filters, `_build_query` returns them as
human-readable strings in the `residual_instructions` field of the `ListingQuote`.
The user is expected to apply these manually after following the deep link.

### v1 Residual Filters

| Filter | Reason | Residual instruction format |
|--------|--------|-----------------------------|
| Influence | The influence filter lives under `query.filters.misc_filters.filters.shaper_item` / `elder_item` / etc. but the exact key mapping varies and is not yet validated in this spike | `"Set influence filter: <influence>"` |
| Mod filter without a `min_value` | Trade site requires a numeric value for stat filters; open-ended "has mod" is not encodable in the same stats array | `"Add mod filter: <stat_id> (no min value set)"` |

Future tasks may promote these from residual to encoded once browser verification
confirms the exact JSON key paths.

---

## Implementation Notes

- `_build_query` in `oracle/pricing/listings.py` is the sole place that constructs
  the JSON. It performs **no network I/O** — it is pure string/dict construction
  followed by `json.dumps` and `urllib.parse.quote`.
- The string `/api/trade/` does **not** appear anywhere in the codebase; only the
  human-facing `/trade/search` path is used.
- `www.pathofexile.com` appears only as the string constant `TRADE_SITE_BASE` —
  it is never fetched.

---

## Phase-0 DoD: Manual Browser Verification (Task 14)

Live browser verification that the `?q=` parameter actually pre-populates the
trade-site search form is a **manual** Definition-of-Done step deferred to Task 14.
Until that step is complete, the URL format above is based on community-documented
knowledge of the trade site's internal query structure and has not been confirmed
to pre-populate in a live browser session.

Action required (Task 14): open each of the three worked-example URLs in a browser
logged into pathofexile.com and confirm the relevant fields are pre-filled.
