# Design: Oracle Phase 0 (Foundations)

Date: 2026-07-18. Status: approved. Scope: Phase 0 only.

This document captures the concrete engineering decisions the PRD (`docs/prd.md`,
v0.3) intentionally leaves open for Phase 0. The PRD is the canonical spec; this
is the thin supplement that pins the stack, module boundaries, and interfaces.

## Scope

Phase 0 (Foundations) only. Deliverables, per PRD §Phase 0:

1. Repo scaffold (tooling, `src` layout, CI).
2. **League Service** — live league enumeration + poe.ninja coverage cross-check.
3. **Game Data Service** — vendored RePoE snapshot loader + mod-pool query.
4. **Price Service** — poe.ninja-only client, percentile aggregation, liquidity
   metrics, data-maturity signals, append-only SQLite snapshot persistence.
5. **ListingResolver + DeepLinkResolver** — `ItemSpec` model, compliant
   trade-site URL construction, observed-price record/retrieve/expire.
6. Config — single TOML settings file.
7. Spike doc `docs/trade-deeplinks.md`; compliance allowlist test.

Out of scope: everything in Phases 1–6. No OAuth, no credentials, no
trade-API client, no `/api/trade/*` calls anywhere.

## Tech stack

| Concern | Choice | Rationale |
|---|---|---|
| Env/packaging | **uv** | Fast, single-tool; PRD offered "uv or poetry" |
| CLI | **Typer** | Type-hint driven, matches mypy-strict core |
| HTTP | **httpx** | Timeouts, retries, HTTP/2; one client for ninja + league API |
| Validation | **Pydantic v2** | Config, price/item models, RePoE schema validation |
| Storage | **stdlib `sqlite3`** + thin repository layer | 1–2 users; no ORM weight |
| Settings | **TOML** (`config/settings.toml`) | Human-editable, stdlib `tomllib` reader |
| Rule data | **YAML** | Per PRD "rules as data"; empty in Phase 0 |
| Lint/type/test | ruff, mypy (strict on `oracle/`), pytest, hypothesis, pre-commit | Per PRD §10 |

## Repository layout

```
oracle/                     # core package (mypy strict)
  __init__.py
  config.py                 # Pydantic settings loader over config/settings.toml
  cli.py                    # Typer app: leagues / prices / modpool / link
  models.py                 # shared Pydantic models (Price, League, Maturity, ...)
  league/
    service.py              # LeagueService: enumerate + ninja cross-check
  gamedata/
    service.py              # GameDataService: RePoE load, index, mod_pool query
    schema.py               # Pydantic models for RePoE shapes (fail-loud)
  pricing/
    ninja.py                # poe.ninja client (all economy endpoints, TTL cache)
    aggregate.py            # percentile band + outlier rejection + liquidity
    maturity.py             # per-league data-maturity signals (§7.1)
    service.py              # PriceService: orchestrates ninja + aggregate + store
    listings.py             # ItemSpec, ListingQuote, ListingResolver, DeepLinkResolver
  store/
    db.py                   # SQLite connection + migrations
    prices.py               # append-only price snapshot repo
    observations.py         # observed-price repo (record/retrieve/expire)
  http/
    client.py               # shared httpx client: UA, backoff, 429 Retry-After
scanner/__init__.py         # empty package stub (Phase 1)
advisor/__init__.py         # empty package stub (Phase 5)
data/                       # versioned rule files (YAML) — empty in Phase 0
snapshots/repoe/            # vendored RePoE JSON + version manifest
config/settings.toml        # default settings (default league = Standard)
tests/                      # unit + recorded-fixture integration + compliance
docs/trade-deeplinks.md     # Phase 0 spike output
.github/workflows/ci.yml    # ruff + mypy + pytest
pyproject.toml              # uv-managed
```

## Service interfaces (contracts, not internals)

### League Service
```python
class League(BaseModel):
    id: str            # e.g. "Standard"
    realm: str         # "pc" default
    ninja_available: bool

class LeagueService:
    def list_leagues(self) -> list[League]: ...
```
Enumerates GGG's documented league API, cross-checks each id against poe.ninja
category availability, returns the intersection with a coverage flag. No league
name is hardcoded; `Standard` lives only as a config default.

### Game Data Service
```python
class Mod(BaseModel):
    id: str; name: str; weight: int; group: str; tags: list[str]
    domain: str; generation_type: str  # prefix/suffix/...

class GameDataService:
    def mod_pool(self, base: str, ilvl: int,
                 influence: str | None = None,
                 tags: list[str] | None = None) -> list[Mod]: ...
```
Loads the vendored RePoE snapshot, validates every shape on load (unknown shape
=> raise), indexes mods by base/tag/domain for the query.

### Price Service
```python
class Price(BaseModel):
    key: str                 # item/currency identifier
    league: str
    chaos_value: float       # percentile-band price, chaos-equivalent
    sample_depth: int
    ts: datetime             # snapshot time
    source: str              # "ninja:<category>" | "user-observed"
    confidence: float        # derived from maturity + sample depth

class Maturity(BaseModel):
    league: str
    median_sample_depth: float
    volatility: float
    history_density: float
    score: float             # 0..1 composite

class PriceService:
    def prices(self, category: str, league: str) -> list[Price]: ...
    def maturity(self, league: str) -> Maturity: ...
```
poe.ninja is the sole external pricing source. Every price is persisted
append-only (timestamped, league-tagged, source-tagged) — history is an asset.
Aggregation uses a configurable percentile band (default 15th) with outlier
rejection; never the raw minimum.

### ListingResolver (the v0.3 pivot)
```python
class ItemSpec(BaseModel):
    base: str
    ilvl: int | None = None
    influence: str | None = None
    mod_filters: list[ModFilter] = []   # stat id + min value
    sockets: int | None = None          # patch-annotated
    links: int | None = None            # patch-annotated

class ListingQuote(BaseModel):
    spec_hash: str
    league: str
    chaos_value: float | None           # None until a human observes one
    deep_link: str
    residual_instructions: list[str]     # filters the URL couldn't encode
    source: str                         # "user-observed" | "unresolved"
    observed_ts: datetime | None

class ListingResolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...

class DeepLinkResolver:  # v1 shipped backend
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...
    def record_observed_price(self, spec: ItemSpec, league: str,
                              chaos_value: float) -> None: ...
```
`DeepLinkResolver.resolve` builds the official trade-site search URL from the
spec (no HTTP call), returns it plus any residual human instructions. A cached
observed price within TTL short-circuits and is returned as the quote. Only a
resolver implementation may know how listings are obtained (PRD §3.3).

## Data flow

```
CLI command
  -> Service (League / GameData / Price / Resolver)
     -> cache check (SQLite, TTL)
        -> miss: external fetch via shared http client (ninja / league API ONLY)
     -> Pydantic-validate response (fail loud on drift)
     -> aggregate (percentile + outlier + liquidity + maturity)
     -> persist snapshot (append-only)
  -> render (terminal table + JSON)
```
Every rendered price/opportunity embeds: league, snapshot ts, RePoE snapshot
version, rule-file versions, and per-price source attribution.

## Error handling

- **Schema drift** (RePoE unknown shape, ninja response shape change): raise a
  structured error / loud log; never silently coerce.
- **Rate limits**: shared http client honors 429 `Retry-After` and rate-limit
  headers, exponential backoff, descriptive User-Agent. poe.ninja responses
  cached at ~15-min cadence.
- **Compliance**: a repo-level test walks the codebase / mocks the http layer to
  assert no request targets `pathofexile.com` except the documented league API
  (allowlist). Fails CI on violation.
- **Unresolved listings**: `DeepLinkResolver` returns a quote with
  `chaos_value=None` and `source="unresolved"` + the deep-link — never a fake
  number.

## Testing strategy

- **Unit** per service (aggregation math, maturity signals, URL construction,
  observation TTL expiry).
- **Recorded-fixture integration** for the ninja client and league API: JSON
  cassettes committed under `tests/fixtures/`; no live calls in CI.
- **Property tests** (hypothesis) for percentile/outlier math and maturity
  monotonicity (thinner data => wider band, lower confidence).
- **Compliance test** (allowlist) as above.
- **Live smoke tests** marked `@pytest.mark.live`, skipped in CI, runnable
  locally against Standard for the DoD checks.

## Phase 0 DoD mapping (from PRD)

| DoD item | Verified by |
|---|---|
| `oracle leagues` returns live set + coverage flags | live smoke + recorded-fixture unit |
| `oracle prices currency --league Standard` w/ depth, ts, maturity | live smoke + unit |
| `oracle modpool "Vaal Regalia" --ilvl 86` correct vs poedb (3 bases) | manual spot-check + unit |
| `oracle link` emits correct pre-populated search (3 specs) | manual (spike) + unit on URL builder |
| observed-price round-trip (record/retrieve/expire) | unit |
| CI green | CI |
| no league name outside config/fixtures | grep-based test |
| zero HTTP to pathofexile.com except league API | compliance allowlist test |

## Open items carried from PRD (Phase 0 relevant)

1. Exact trade-site URL pre-population capabilities — resolved by the spike
   (`docs/trade-deeplinks.md`); the `DeepLinkResolver` URL builder is written
   against the spike's findings.
2. RePoE snapshot version to vendor — fetch current from repoe-fork gh-pages,
   record commit/version in `snapshots/repoe/manifest.json`, validate on load.
