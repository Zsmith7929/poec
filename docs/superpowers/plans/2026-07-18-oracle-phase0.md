# Oracle Phase 0 (Foundations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Oracle foundations — League Service, Game Data Service, poe.ninja-only Price Service, and the compliant DeepLink ListingResolver — behind a Typer CLI, to the PRD Phase 0 DoD.

**Architecture:** A `src`-layout Python package `oracle/` with four services over a shared SQLite store and a single rate-limited httpx client. poe.ninja is the sole external pricing source; specific-listing pricing is delegated to a human via constructed trade-site deep-links behind a `ListingResolver` Protocol. Rules/config live as data (TOML settings, vendored RePoE JSON). Every external call is cached, validated, and source-attributed.

**Tech Stack:** Python 3.12+, uv, Typer, httpx, Pydantic v2, stdlib sqlite3, TOML (tomllib), ruff, mypy (strict on `oracle/`), pytest, hypothesis, pre-commit.

## Global Constraints

- Python `>=3.12`. Managed with **uv** (`uv sync`, `uv run`).
- **Compliance (hard):** no code path may issue an HTTP request to `pathofexile.com` other than the documented league API (`/api/leagues`). No `/api/trade/*`, ever. No OAuth, no credentials, no session cookies in v1.
- **League-agnostic:** no league name hardcoded in code, tests, or fixtures. `"Standard"` may appear ONLY as a config default in `config/settings.toml` and in fixture *metadata*.
- **All external access goes through the Price Service / a dedicated client.** No module calls external APIs directly except the clients in `oracle/http/`, `oracle/pricing/ninja.py`, `oracle/league/service.py`.
- **Robust pricing:** never use the raw minimum listing as the price. Use a configurable percentile band (default 15th) with outlier rejection. Every price carries: percentile value, sample depth, staleness timestamp, league, and source.
- **Rate-limit citizenship:** honor 429 `Retry-After` and rate-limit headers; exponential backoff; descriptive `User-Agent` on every request; poe.ninja cached at ~15-min cadence.
- **Fail loud:** unknown/changed external schema shapes raise, never silently coerce.
- **Reproducibility:** every rendered result embeds league, snapshot timestamp, RePoE snapshot version, and per-price source attribution.
- mypy is **strict** on `oracle/`. ruff clean. Tests green in CI. Live-network tests marked `@pytest.mark.live` and skipped in CI.
- Commit after every task. Commit message trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: Repo scaffold, tooling, CI, package skeleton

**Files:**
- Create: `pyproject.toml`, `oracle/__init__.py`, `oracle/cli.py`, `scanner/__init__.py`, `advisor/__init__.py`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `config/settings.toml`, `tests/__init__.py`, `tests/test_cli_smoke.py`
- Create (empty dirs w/ `.gitkeep`): `data/.gitkeep`, `snapshots/repoe/.gitkeep`

**Interfaces:**
- Produces: a Typer app object `oracle.cli:app`; console-script entry `oracle`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "oracle"
version = "0.0.0"
description = "PoE1 Crafting Companion"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pyyaml>=6.0",
]

[project.scripts]
oracle = "oracle.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "respx>=0.21",
    "ruff>=0.5",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "types-pyyaml>=6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["oracle", "scanner", "advisor"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["oracle"]

[tool.pytest.ini_options]
markers = ["live: hits real external networks; skipped in CI"]
addopts = "-m 'not live'"
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package skeleton**

`oracle/__init__.py`:
```python
__version__ = "0.0.0"
```

`oracle/cli.py`:
```python
import typer

app = typer.Typer(help="Oracle — PoE1 Crafting Companion", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the Oracle version."""
    from oracle import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
```

`scanner/__init__.py` and `advisor/__init__.py`: empty files.

`config/settings.toml`:
```toml
# Oracle settings. League is a runtime parameter everywhere; this is only a default.
default_league = "Standard"
realm = "pc"
user_agent = "oracle/0.0.0 (personal crafting tool; contact: smith7929@gmail.com)"

[pricing]
percentile = 0.15          # 15th-percentile band
outlier_z = 3.0            # reject samples beyond this many MAD-scaled deviations
min_sample_depth = 5       # below this, confidence is heavily penalized

[cache]
ninja_ttl_seconds = 900    # ~15 min
league_ttl_seconds = 3600
observed_price_ttl_seconds = 86400

[store]
db_path = "data/oracle.db"
```

- [ ] **Step 3: Write CI and pre-commit config**

`.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.12
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy
      - run: uv run pytest --cov=oracle --cov-report=term-missing
```

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-pyyaml]
```

- [ ] **Step 4: Write the smoke test**

`tests/test_cli_smoke.py`:
```python
from typer.testing import CliRunner

from oracle.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.0.0"


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Oracle" in result.stdout
```

- [ ] **Step 5: Sync and run**

Run: `cd /home/zac/code/poec && uv sync --dev && uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest`
Expected: deps install; ruff/mypy clean; 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: repo scaffold, tooling, CI, package skeleton"
```

---

### Task 2: Config loader (Pydantic settings over TOML)

**Files:**
- Create: `oracle/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Settings` (Pydantic model) with fields: `default_league: str`, `realm: str`, `user_agent: str`, `pricing: PricingSettings`, `cache: CacheSettings`, `store: StoreSettings`.
  - `PricingSettings(percentile: float, outlier_z: float, min_sample_depth: int)`
  - `CacheSettings(ninja_ttl_seconds: int, league_ttl_seconds: int, observed_price_ttl_seconds: int)`
  - `StoreSettings(db_path: str)`
  - `load_settings(path: Path | None = None) -> Settings` (defaults to `config/settings.toml`).

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path

from oracle.config import Settings, load_settings


def test_loads_default_settings_file() -> None:
    settings = load_settings(Path("config/settings.toml"))
    assert isinstance(settings, Settings)
    assert settings.default_league == "Standard"
    assert 0.0 < settings.pricing.percentile < 1.0
    assert settings.cache.ninja_ttl_seconds > 0
    assert settings.store.db_path.endswith(".db")


def test_rejects_out_of_range_percentile(tmp_path: Path) -> None:
    bad = tmp_path / "s.toml"
    bad.write_text(
        'default_league="X"\nrealm="pc"\nuser_agent="ua"\n'
        "[pricing]\npercentile=2.0\noutlier_z=3.0\nmin_sample_depth=5\n"
        "[cache]\nninja_ttl_seconds=1\nleague_ttl_seconds=1\nobserved_price_ttl_seconds=1\n"
        '[store]\ndb_path="x.db"\n'
    )
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_settings(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: oracle.config).

- [ ] **Step 3: Implement `oracle/config.py`**

```python
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_PATH = Path("config/settings.toml")


class PricingSettings(BaseModel):
    percentile: float = Field(gt=0.0, lt=1.0)
    outlier_z: float = Field(gt=0.0)
    min_sample_depth: int = Field(ge=1)


class CacheSettings(BaseModel):
    ninja_ttl_seconds: int = Field(ge=1)
    league_ttl_seconds: int = Field(ge=1)
    observed_price_ttl_seconds: int = Field(ge=1)


class StoreSettings(BaseModel):
    db_path: str


class Settings(BaseModel):
    default_league: str
    realm: str
    user_agent: str
    pricing: PricingSettings
    cache: CacheSettings
    store: StoreSettings


def load_settings(path: Path | None = None) -> Settings:
    p = path or DEFAULT_PATH
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    return Settings.model_validate(raw)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v && uv run mypy`
Expected: 2 PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/config.py tests/test_config.py
git commit -m "feat: TOML-backed Pydantic settings loader"
```

---

### Task 3: SQLite store base (connection + migrations)

**Files:**
- Create: `oracle/store/__init__.py`, `oracle/store/db.py`, `tests/test_store_db.py`

**Interfaces:**
- Produces:
  - `connect(db_path: str) -> sqlite3.Connection` — opens with `row_factory = sqlite3.Row`, `PRAGMA foreign_keys=ON`, applies migrations idempotently.
  - `MIGRATIONS: list[str]` — ordered DDL statements.

- [ ] **Step 1: Write the failing test**

`tests/test_store_db.py`:
```python
from pathlib import Path

from oracle.store.db import connect


def test_connect_creates_tables(tmp_path: Path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"price_snapshots", "observed_prices"} <= tables


def test_connect_is_idempotent(tmp_path: Path) -> None:
    path = str(tmp_path / "t.db")
    connect(path).close()
    conn = connect(path)  # second call must not raise
    assert conn.execute("SELECT 1").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_db.py -v`
Expected: FAIL (no module `oracle.store.db`).

- [ ] **Step 3: Implement `oracle/store/db.py`**

```python
import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS price_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        category TEXT NOT NULL,
        key TEXT NOT NULL,
        chaos_value REAL NOT NULL,
        sample_depth INTEGER NOT NULL,
        source TEXT NOT NULL,
        confidence REAL NOT NULL,
        ts TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_price_league_cat_ts
        ON price_snapshots (league, category, ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS observed_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        spec_hash TEXT NOT NULL,
        chaos_value REAL NOT NULL,
        observed_ts TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_obs_league_spec_ts
        ON observed_prices (league, spec_hash, observed_ts)
    """,
]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    for ddl in MIGRATIONS:
        conn.execute(ddl)
    conn.commit()
    return conn
```

`oracle/store/__init__.py`: empty.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_store_db.py -v && uv run mypy`
Expected: 2 PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/store/ tests/test_store_db.py
git commit -m "feat: SQLite store with idempotent migrations"
```

---

### Task 4: Shared rate-limited HTTP client

**Files:**
- Create: `oracle/http/__init__.py`, `oracle/http/client.py`, `tests/test_http_client.py`

**Interfaces:**
- Consumes: `Settings.user_agent`.
- Produces:
  - `HttpClient(user_agent: str, allowed_hosts: set[str], max_retries: int = 4)`
  - `.get_json(url: str, params: dict[str, str] | None = None) -> Any` — sets UA, enforces `allowed_hosts` (raises `ComplianceError` otherwise), retries on 429/5xx honoring `Retry-After` with exponential backoff.
  - `ComplianceError(Exception)` — raised when a URL host is not in `allowed_hosts`.

- [ ] **Step 1: Write the failing test**

`tests/test_http_client.py`:
```python
import httpx
import pytest
import respx

from oracle.http.client import ComplianceError, HttpClient

UA = "oracle-test/0"
HOSTS = {"api.pathofexile.com", "poe.ninja"}


@respx.mock
def test_get_json_sends_user_agent_and_parses() -> None:
    route = respx.get("https://poe.ninja/data").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = HttpClient(UA, HOSTS)
    assert client.get_json("https://poe.ninja/data") == {"ok": True}
    assert route.calls.last.request.headers["user-agent"] == UA


def test_rejects_disallowed_host() -> None:
    client = HttpClient(UA, HOSTS)
    with pytest.raises(ComplianceError):
        client.get_json("https://www.pathofexile.com/api/trade/search")


@respx.mock
def test_retries_on_429_then_succeeds() -> None:
    respx.get("https://poe.ninja/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"done": 1}),
        ]
    )
    client = HttpClient(UA, HOSTS)
    assert client.get_json("https://poe.ninja/x") == {"done": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_http_client.py -v`
Expected: FAIL (no module `oracle.http.client`).

- [ ] **Step 3: Implement `oracle/http/client.py`**

```python
import time
from typing import Any
from urllib.parse import urlparse

import httpx


class ComplianceError(Exception):
    """Raised when a request targets a host outside the allowlist."""


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        allowed_hosts: set[str],
        max_retries: int = 4,
        timeout: float = 20.0,
    ) -> None:
        self._allowed = allowed_hosts
        self._max_retries = max_retries
        self._client = httpx.Client(
            headers={"User-Agent": user_agent}, timeout=timeout, http2=True
        )

    def _check_host(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        if host not in self._allowed:
            raise ComplianceError(f"host not in allowlist: {host!r}")

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        self._check_host(url)
        backoff = 1.0
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else backoff
                time.sleep(delay)
                backoff *= 2
                last_exc = httpx.HTTPStatusError(
                    "retryable", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            return resp.json()
        raise last_exc if last_exc else RuntimeError("request failed")

    def close(self) -> None:
        self._client.close()
```

`oracle/http/__init__.py`: empty.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_http_client.py -v && uv run mypy`
Expected: 3 PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/http/ tests/test_http_client.py
git commit -m "feat: rate-limited http client with host allowlist and backoff"
```

---

### Task 5: League Service (GGG league API + ninja cross-check)

**Files:**
- Create: `oracle/models.py`, `oracle/league/__init__.py`, `oracle/league/service.py`, `tests/test_league_service.py`, `tests/fixtures/leagues.json`, `tests/fixtures/ninja_currency_index.json`

**Interfaces:**
- Consumes: `HttpClient.get_json`.
- Produces:
  - `oracle/models.py`: `League(id: str, realm: str, ninja_available: bool)`.
  - `LeagueService(http: HttpClient, ninja_probe: Callable[[str], bool])`
  - `.list_leagues(realm: str = "pc") -> list[League]` — GET `https://api.pathofexile.com/leagues?realm=<realm>`, for each league id call `ninja_probe(id)` to set `ninja_available`.
- Endpoint constant: `LEAGUE_API_URL = "https://api.pathofexile.com/leagues"`.

**Notes:** `ninja_probe` is injected so the service does not itself hardcode ninja wiring; the real probe (Task 7) checks poe.ninja currency-overview coverage for the league. Fixtures use invented league ids in *metadata only* to respect the no-hardcoded-league rule (e.g. `"TestLeagueA"`).

- [ ] **Step 1: Write the failing test**

`tests/fixtures/leagues.json`:
```json
{"leagues": [{"id": "TestLeagueA", "realm": "pc"}, {"id": "TestLeagueB", "realm": "pc"}]}
```

`tests/test_league_service.py`:
```python
import json
from pathlib import Path

from oracle.league.service import LEAGUE_API_URL, LeagueService
from oracle.models import League

FIX = Path(__file__).parent / "fixtures"


class FakeHttp:
    def get_json(self, url: str, params: dict[str, str] | None = None) -> object:
        assert url == LEAGUE_API_URL
        return json.loads((FIX / "leagues.json").read_text())


def test_list_leagues_sets_ninja_flag() -> None:
    covered = {"TestLeagueA"}
    svc = LeagueService(FakeHttp(), ninja_probe=lambda lid: lid in covered)
    leagues = svc.list_leagues()
    assert leagues == [
        League(id="TestLeagueA", realm="pc", ninja_available=True),
        League(id="TestLeagueB", realm="pc", ninja_available=False),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_league_service.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Implement models + service**

`oracle/models.py`:
```python
from datetime import datetime

from pydantic import BaseModel


class League(BaseModel):
    id: str
    realm: str
    ninja_available: bool


class Price(BaseModel):
    key: str
    league: str
    category: str
    chaos_value: float
    sample_depth: int
    source: str
    confidence: float
    ts: datetime


class Maturity(BaseModel):
    league: str
    median_sample_depth: float
    volatility: float
    history_density: float
    score: float
```

`oracle/league/service.py`:
```python
from collections.abc import Callable
from typing import Any, Protocol

from oracle.models import League

LEAGUE_API_URL = "https://api.pathofexile.com/leagues"


class _Http(Protocol):
    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any: ...


class LeagueService:
    def __init__(self, http: _Http, ninja_probe: Callable[[str], bool]) -> None:
        self._http = http
        self._probe = ninja_probe

    def list_leagues(self, realm: str = "pc") -> list[League]:
        payload = self._http.get_json(LEAGUE_API_URL, params={"realm": realm})
        leagues = payload["leagues"] if isinstance(payload, dict) else payload
        result: list[League] = []
        for entry in leagues:
            lid = entry["id"]
            result.append(
                League(
                    id=lid,
                    realm=entry.get("realm", realm),
                    ninja_available=self._probe(lid),
                )
            )
        return result
```

`oracle/league/__init__.py`: empty.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_league_service.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/models.py oracle/league/ tests/test_league_service.py tests/fixtures/leagues.json
git commit -m "feat: league service with live enumeration and ninja cross-check probe"
```

---

### Task 6: Game Data Service (vendor RePoE + schema + mod_pool)

**Files:**
- Create: `oracle/gamedata/__init__.py`, `oracle/gamedata/schema.py`, `oracle/gamedata/service.py`, `tests/test_gamedata.py`
- Create (vendored data): `snapshots/repoe/manifest.json`, `snapshots/repoe/mods.min.json`, `snapshots/repoe/base_items.min.json` (a *reduced* real snapshot; see step 0)

**Interfaces:**
- Produces:
  - `oracle/models.py` addition: `Mod(id, name, weight, group, tags, domain, generation_type)`.
  - `GameDataService.from_snapshot(path: Path) -> GameDataService`
  - `.snapshot_version() -> str`
  - `.mod_pool(base: str, ilvl: int, influence: str | None = None, tags: list[str] | None = None) -> list[Mod]`

- [ ] **Step 0 (spike/vendor): fetch and reduce a RePoE snapshot**

Fetch current RePoE JSON from the repoe-fork gh-pages and vendor it. Because the
full `mods.json` is large, commit a reduced snapshot sufficient for Phase 0 DoD
(must include mods for at least `Vaal Regalia`, `Titanium Spirit Shield`, and one
weapon base). Record provenance in `snapshots/repoe/manifest.json`:
```json
{
  "source": "https://repoe-fork.github.io/",
  "fetched_at": "2026-07-18T00:00:00Z",
  "files": ["mods.min.json", "base_items.min.json"],
  "note": "Reduced Phase-0 snapshot; re-snapshot full data per patch-day runbook."
}
```
Document the exact fetch commands used in `docs/repoe-snapshot.md`.

- [ ] **Step 1: Write the failing test**

`tests/test_gamedata.py`:
```python
from pathlib import Path

from oracle.gamedata.service import GameDataService
from oracle.models import Mod

SNAP = Path("snapshots/repoe")


def test_loads_snapshot_and_reports_version() -> None:
    svc = GameDataService.from_snapshot(SNAP)
    assert svc.snapshot_version()  # non-empty


def test_mod_pool_returns_weighted_mods_for_known_base() -> None:
    svc = GameDataService.from_snapshot(SNAP)
    pool = svc.mod_pool("Vaal Regalia", ilvl=86)
    assert pool, "expected a non-empty mod pool"
    assert all(isinstance(m, Mod) for m in pool)
    assert all(m.weight >= 0 for m in pool)
    # ilvl gate: no mod with a required level above the item level
    assert all(getattr(m, "required_level", 0) <= 86 for m in pool)


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    import pytest

    bad = tmp_path / "repoe"
    bad.mkdir()
    (bad / "manifest.json").write_text('{"files": ["mods.min.json"]}')
    (bad / "mods.min.json").write_text('{"BadMod": {"unexpected": 1}}')
    with pytest.raises(Exception):
        GameDataService.from_snapshot(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gamedata.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Implement schema + service**

`oracle/gamedata/schema.py` — Pydantic models mirroring the RePoE `mods.json`
shape (spawn weights are `[{tag, weight}]`, plus `domain`, `generation_type`,
`required_level`, `type`, `groups`). Validate on load; unknown/missing required
keys raise `ValidationError`.

```python
from pydantic import BaseModel


class SpawnWeight(BaseModel):
    tag: str
    weight: int


class RepoeMod(BaseModel):
    name: str
    domain: str
    generation_type: str
    group: str
    required_level: int = 0
    type: str = ""
    spawn_weights: list[SpawnWeight] = []
    tags: list[str] = []
```

Add `Mod` to `oracle/models.py`:
```python
class Mod(BaseModel):
    id: str
    name: str
    weight: int
    group: str
    tags: list[str]
    domain: str
    generation_type: str
    required_level: int = 0
```

`oracle/gamedata/service.py`:
```python
import json
from pathlib import Path

from oracle.gamedata.schema import RepoeMod
from oracle.models import Mod


class GameDataService:
    def __init__(self, version: str, mods: dict[str, RepoeMod],
                 base_tags: dict[str, list[str]]) -> None:
        self._version = version
        self._mods = mods
        self._base_tags = base_tags

    @classmethod
    def from_snapshot(cls, path: Path) -> "GameDataService":
        manifest = json.loads((path / "manifest.json").read_text())
        raw_mods = json.loads((path / "mods.min.json").read_text())
        mods = {mid: RepoeMod.model_validate(m) for mid, m in raw_mods.items()}
        base_path = path / "base_items.min.json"
        base_tags: dict[str, list[str]] = {}
        if base_path.exists():
            raw_bases = json.loads(base_path.read_text())
            base_tags = {
                b["name"]: b.get("tags", []) for b in raw_bases.values()
            }
        version = manifest.get("fetched_at", "unknown")
        return cls(version, mods, base_tags)

    def snapshot_version(self) -> str:
        return self._version

    def mod_pool(self, base: str, ilvl: int, influence: str | None = None,
                 tags: list[str] | None = None) -> list[Mod]:
        item_tags = set(self._base_tags.get(base, []))
        if tags:
            item_tags |= set(tags)
        result: list[Mod] = []
        for mid, m in self._mods.items():
            if m.required_level > ilvl:
                continue
            weight = 0
            for sw in m.spawn_weights:
                if sw.tag in item_tags or sw.tag == "default":
                    weight = sw.weight
                    break
            if weight <= 0:
                continue
            result.append(
                Mod(id=mid, name=m.name, weight=weight, group=m.group,
                    tags=m.tags, domain=m.domain,
                    generation_type=m.generation_type,
                    required_level=m.required_level)
            )
        return result
```

`oracle/gamedata/__init__.py`: empty.

- [ ] **Step 4: Run tests + spot-check**

Run: `uv run pytest tests/test_gamedata.py -v && uv run mypy`
Expected: PASS. Then manually spot-check `mod_pool` output for 3 bases against
poedb (record results in `docs/repoe-snapshot.md`).

- [ ] **Step 5: Commit**

```bash
git add oracle/gamedata/ oracle/models.py snapshots/repoe/ docs/repoe-snapshot.md tests/test_gamedata.py
git commit -m "feat: game data service with vendored RePoE snapshot and mod-pool query"
```

---

### Task 7: poe.ninja client + ninja probe

**Files:**
- Create: `oracle/pricing/__init__.py`, `oracle/pricing/ninja.py`, `tests/test_ninja_client.py`, `tests/fixtures/ninja_currency_overview.json`, `tests/fixtures/ninja_leagues.json`

**Interfaces:**
- Consumes: `HttpClient.get_json`.
- Produces:
  - `NinjaClient(http: HttpClient)`
  - `.currency_overview(league: str) -> list[NinjaLine]` and `.item_overview(league: str, category: str) -> list[NinjaLine]`
  - `NinjaLine(key: str, chaos_value: float, sample_depth: int)` (normalizes ninja's `currencyTypeName`/`chaosEquivalent`/`count` and item `name`/`chaosValue`/`listingCount`).
  - `.league_is_covered(league: str) -> bool` — used as the `ninja_probe` for Task 5.
  - Endpoint constants for the currency and item overview URLs.

**Notes:** validate response shape; on a missing/renamed key raise `NinjaSchemaError` (fail-loud per Global Constraints).

- [ ] **Step 1: Write the failing test** (using committed fixtures + respx)

`tests/fixtures/ninja_currency_overview.json`:
```json
{"lines": [
  {"currencyTypeName": "Divine Orb", "chaosEquivalent": 180.0,
   "receive": {"count": 42}},
  {"currencyTypeName": "Exalted Orb", "chaosEquivalent": 12.5,
   "receive": {"count": 300}}
]}
```

`tests/test_ninja_client.py`:
```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from oracle.http.client import HttpClient
from oracle.pricing.ninja import CURRENCY_OVERVIEW_URL, NinjaClient, NinjaSchemaError

FIX = Path(__file__).parent / "fixtures"
HOSTS = {"poe.ninja", "api.pathofexile.com"}


@respx.mock
def test_currency_overview_normalizes_lines() -> None:
    respx.get(CURRENCY_OVERVIEW_URL).mock(
        return_value=httpx.Response(
            200, json=json.loads((FIX / "ninja_currency_overview.json").read_text())
        )
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    lines = client.currency_overview("TestLeagueA")
    divine = next(x for x in lines if x.key == "Divine Orb")
    assert divine.chaos_value == 180.0
    assert divine.sample_depth == 42


@respx.mock
def test_schema_drift_fails_loud() -> None:
    respx.get(CURRENCY_OVERVIEW_URL).mock(
        return_value=httpx.Response(200, json={"unexpected": []})
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError):
        client.currency_overview("TestLeagueA")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ninja_client.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Implement `oracle/pricing/ninja.py`**

```python
from typing import Any

from pydantic import BaseModel

from oracle.http.client import HttpClient

CURRENCY_OVERVIEW_URL = "https://poe.ninja/api/data/currencyoverview"
ITEM_OVERVIEW_URL = "https://poe.ninja/api/data/itemoverview"


class NinjaSchemaError(Exception):
    """poe.ninja returned an unexpected shape."""


class NinjaLine(BaseModel):
    key: str
    chaos_value: float
    sample_depth: int


class NinjaClient:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def currency_overview(self, league: str) -> list[NinjaLine]:
        payload = self._http.get_json(
            CURRENCY_OVERVIEW_URL, params={"league": league, "type": "Currency"}
        )
        return self._parse_currency(payload)

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        payload = self._http.get_json(
            ITEM_OVERVIEW_URL, params={"league": league, "type": category}
        )
        return self._parse_items(payload)

    def league_is_covered(self, league: str) -> bool:
        try:
            return bool(self.currency_overview(league))
        except (NinjaSchemaError, Exception):
            return False

    @staticmethod
    def _parse_currency(payload: Any) -> list[NinjaLine]:
        if not isinstance(payload, dict) or "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        out: list[NinjaLine] = []
        for line in payload["lines"]:
            try:
                out.append(
                    NinjaLine(
                        key=line["currencyTypeName"],
                        chaos_value=float(line["chaosEquivalent"]),
                        sample_depth=int(line.get("receive", {}).get("count", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out

    @staticmethod
    def _parse_items(payload: Any) -> list[NinjaLine]:
        if not isinstance(payload, dict) or "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        out: list[NinjaLine] = []
        for line in payload["lines"]:
            try:
                out.append(
                    NinjaLine(
                        key=line["name"],
                        chaos_value=float(line["chaosValue"]),
                        sample_depth=int(line.get("listingCount", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out
```

`oracle/pricing/__init__.py`: empty.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_ninja_client.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/pricing/ tests/test_ninja_client.py tests/fixtures/ninja_currency_overview.json
git commit -m "feat: poe.ninja client with normalized lines and fail-loud schema checks"
```

---

### Task 8: Price aggregation + maturity signals (pure math)

**Files:**
- Create: `oracle/pricing/aggregate.py`, `oracle/pricing/maturity.py`, `tests/test_aggregate.py`, `tests/test_maturity.py`

**Interfaces:**
- Produces:
  - `aggregate(values: list[float], percentile: float, outlier_z: float) -> AggResult` where `AggResult(value: float, sample_depth: int)`. Rejects outliers via MAD, then takes the given percentile of the cleaned set.
  - `confidence(sample_depth: int, min_sample_depth: int, maturity_score: float) -> float` in `[0,1]`.
  - `maturity_signals(sample_depths: list[int], recent_values: list[list[float]], history_len: int) -> tuple[float, float, float, float]` returning `(median_sample_depth, volatility, history_density, score)`.

- [ ] **Step 1: Write failing tests (incl. property tests)**

`tests/test_aggregate.py`:
```python
from hypothesis import given
from hypothesis import strategies as st

from oracle.pricing.aggregate import aggregate, confidence


def test_aggregate_rejects_single_outlier() -> None:
    values = [10.0, 10.5, 9.8, 10.2, 10.1, 1000.0]  # last is a spike
    res = aggregate(values, percentile=0.15, outlier_z=3.0)
    assert res.value < 20.0
    assert res.sample_depth == 5  # outlier removed


def test_aggregate_never_returns_raw_minimum() -> None:
    values = [1.0, 5.0, 5.0, 5.0, 5.0]
    res = aggregate(values, percentile=0.15, outlier_z=3.0)
    assert res.value >= 1.0


@given(st.floats(min_value=0, max_value=1), st.integers(0, 100), st.floats(0, 1))
def test_confidence_in_unit_interval(_p: float, depth: int, mat: float) -> None:
    c = confidence(depth, min_sample_depth=5, maturity_score=mat)
    assert 0.0 <= c <= 1.0
```

`tests/test_maturity.py`:
```python
from oracle.pricing.maturity import maturity_signals


def test_thin_data_scores_lower_than_rich_data() -> None:
    thin = maturity_signals([1, 2, 1], [[10.0, 90.0]], history_len=1)
    rich = maturity_signals([200, 300, 250], [[10.0, 10.1, 10.0]], history_len=30)
    assert rich[3] > thin[3]  # score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_aggregate.py tests/test_maturity.py -v`
Expected: FAIL (no modules).

- [ ] **Step 3: Implement aggregate + maturity**

`oracle/pricing/aggregate.py`:
```python
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class AggResult:
    value: float
    sample_depth: int


def _reject_outliers(values: list[float], outlier_z: float) -> list[float]:
    if len(values) < 3:
        return values
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations) or 1e-9
    return [v for v in values if abs(v - med) / (1.4826 * mad) <= outlier_z]


def aggregate(values: list[float], percentile: float, outlier_z: float) -> AggResult:
    if not values:
        raise ValueError("cannot aggregate empty values")
    cleaned = _reject_outliers(sorted(values), outlier_z) or sorted(values)
    cleaned.sort()
    idx = min(int(percentile * (len(cleaned) - 1)), len(cleaned) - 1)
    return AggResult(value=cleaned[idx], sample_depth=len(cleaned))


def confidence(sample_depth: int, min_sample_depth: int, maturity_score: float) -> float:
    depth_factor = min(sample_depth / max(min_sample_depth, 1), 1.0)
    return max(0.0, min(1.0, 0.5 * depth_factor + 0.5 * maturity_score))
```

`oracle/pricing/maturity.py`:
```python
import statistics


def maturity_signals(
    sample_depths: list[int],
    recent_values: list[list[float]],
    history_len: int,
) -> tuple[float, float, float, float]:
    median_depth = statistics.median(sample_depths) if sample_depths else 0.0
    vols: list[float] = []
    for series in recent_values:
        if len(series) >= 2 and statistics.mean(series):
            vols.append(statistics.pstdev(series) / statistics.mean(series))
    volatility = statistics.mean(vols) if vols else 1.0
    history_density = min(history_len / 30.0, 1.0)
    depth_norm = min(median_depth / 100.0, 1.0)
    score = max(0.0, min(1.0, 0.5 * depth_norm + 0.25 * (1 - min(volatility, 1.0))
                         + 0.25 * history_density))
    return (median_depth, volatility, history_density, score)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_aggregate.py tests/test_maturity.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/pricing/aggregate.py oracle/pricing/maturity.py tests/test_aggregate.py tests/test_maturity.py
git commit -m "feat: percentile aggregation, outlier rejection, maturity signals"
```

---

### Task 9: Price repositories + PriceService orchestration

**Files:**
- Create: `oracle/store/prices.py`, `oracle/pricing/service.py`, `tests/test_price_service.py`

**Interfaces:**
- Consumes: `NinjaClient`, `connect`, `aggregate`, `confidence`, `maturity_signals`, `Settings`.
- Produces:
  - `PriceSnapshotRepo(conn)` with `.insert(price: Price) -> None` and `.recent(league, category, limit) -> list[Price]`.
  - `PriceService(ninja, conn, settings)` with:
    - `.prices(category: str, league: str) -> list[Price]` — fetch ninja lines (currency uses currency endpoint, else item endpoint), aggregate per key, attach maturity-derived confidence + source `ninja:<category>`, persist each snapshot, return list.
    - `.maturity(league: str) -> Maturity`.

**Notes:** Timestamps use `datetime.now(tz=UTC)`. Each ninja line is a single observation of chaos value; aggregation across the historical snapshots for that key produces the percentile band (so `prices()` reads recent history from the repo to aggregate, then writes the new observation).

- [ ] **Step 1: Write the failing test**

`tests/test_price_service.py`:
```python
from oracle.config import load_settings
from oracle.models import Maturity, Price
from oracle.pricing.ninja import NinjaLine
from oracle.pricing.service import PriceService
from oracle.store.db import connect


class FakeNinja:
    def currency_overview(self, league: str) -> list[NinjaLine]:
        return [NinjaLine(key="Divine Orb", chaos_value=180.0, sample_depth=42)]

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        return [NinjaLine(key="Fossil X", chaos_value=3.0, sample_depth=15)]


def _svc(tmp_path):
    settings = load_settings()
    conn = connect(str(tmp_path / "t.db"))
    return PriceService(FakeNinja(), conn, settings)


def test_prices_currency_returns_priced_and_persists(tmp_path) -> None:
    svc = _svc(tmp_path)
    prices = svc.prices("Currency", "TestLeagueA")
    assert prices and isinstance(prices[0], Price)
    divine = next(p for p in prices if p.key == "Divine Orb")
    assert divine.chaos_value == 180.0
    assert divine.source == "ninja:Currency"
    assert 0.0 <= divine.confidence <= 1.0
    # persisted
    again = svc.prices("Currency", "TestLeagueA")
    assert again[0].sample_depth >= 1


def test_maturity_returns_model(tmp_path) -> None:
    svc = _svc(tmp_path)
    svc.prices("Currency", "TestLeagueA")
    mat = svc.maturity("TestLeagueA")
    assert isinstance(mat, Maturity)
    assert 0.0 <= mat.score <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_price_service.py -v`
Expected: FAIL (no modules).

- [ ] **Step 3: Implement repo + service**

`oracle/store/prices.py`:
```python
import sqlite3
from datetime import datetime

from oracle.models import Price


class PriceSnapshotRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, price: Price) -> None:
        self._conn.execute(
            "INSERT INTO price_snapshots "
            "(league, category, key, chaos_value, sample_depth, source, confidence, ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (price.league, price.category, price.key, price.chaos_value,
             price.sample_depth, price.source, price.confidence,
             price.ts.isoformat()),
        )
        self._conn.commit()

    def recent_values(self, league: str, category: str, key: str,
                      limit: int = 50) -> list[float]:
        rows = self._conn.execute(
            "SELECT chaos_value FROM price_snapshots "
            "WHERE league=? AND category=? AND key=? ORDER BY ts DESC LIMIT ?",
            (league, category, key, limit),
        ).fetchall()
        return [r["chaos_value"] for r in rows]

    def recent_depths(self, league: str, limit: int = 200) -> list[int]:
        rows = self._conn.execute(
            "SELECT sample_depth FROM price_snapshots WHERE league=? "
            "ORDER BY ts DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [r["sample_depth"] for r in rows]
```

`oracle/pricing/service.py`:
```python
import sqlite3
from datetime import UTC, datetime
from typing import Protocol

from oracle.config import Settings
from oracle.models import Maturity, Price
from oracle.pricing.aggregate import aggregate, confidence
from oracle.pricing.maturity import maturity_signals
from oracle.pricing.ninja import NinjaLine
from oracle.store.prices import PriceSnapshotRepo


class _Ninja(Protocol):
    def currency_overview(self, league: str) -> list[NinjaLine]: ...
    def item_overview(self, league: str, category: str) -> list[NinjaLine]: ...


class PriceService:
    def __init__(self, ninja: _Ninja, conn: sqlite3.Connection,
                 settings: Settings) -> None:
        self._ninja = ninja
        self._repo = PriceSnapshotRepo(conn)
        self._settings = settings

    def prices(self, category: str, league: str) -> list[Price]:
        if category.lower() == "currency":
            lines = self._ninja.currency_overview(league)
        else:
            lines = self._ninja.item_overview(league, category)
        mat = self.maturity(league)
        now = datetime.now(tz=UTC)
        out: list[Price] = []
        for line in lines:
            history = self._repo.recent_values(league, category, line.key)
            history.append(line.chaos_value)
            agg = aggregate(history, self._settings.pricing.percentile,
                            self._settings.pricing.outlier_z)
            price = Price(
                key=line.key, league=league, category=category,
                chaos_value=agg.value, sample_depth=line.sample_depth,
                source=f"ninja:{category}",
                confidence=confidence(line.sample_depth,
                                      self._settings.pricing.min_sample_depth,
                                      mat.score),
                ts=now,
            )
            self._repo.insert(price)
            out.append(price)
        return out

    def maturity(self, league: str) -> Maturity:
        depths = self._repo.recent_depths(league)
        median_depth, vol, density, score = maturity_signals(depths, [], len(depths))
        return Maturity(league=league, median_sample_depth=median_depth,
                        volatility=vol, history_density=density, score=score)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_price_service.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/store/prices.py oracle/pricing/service.py tests/test_price_service.py
git commit -m "feat: price service orchestration with append-only persistence and maturity"
```

---

### Task 10: ListingResolver — ItemSpec, DeepLinkResolver, trade-link spike

**Files:**
- Create: `oracle/pricing/listings.py`, `tests/test_listings.py`, `docs/trade-deeplinks.md`
- Modify: `oracle/models.py` (add `ItemSpec`, `ModFilter`, `ListingQuote`)

**Interfaces:**
- Produces:
  - `ModFilter(stat_id: str, min_value: float | None = None)`
  - `ItemSpec(base, ilvl=None, influence=None, mod_filters=[], sockets=None, links=None)` with `.spec_hash() -> str` (stable hash of normalized fields).
  - `ListingQuote(spec_hash, league, chaos_value: float | None, deep_link: str, residual_instructions: list[str], source: str, observed_ts: datetime | None)`.
  - `ListingResolver(Protocol)` with `resolve(spec, league) -> ListingQuote`.
  - `DeepLinkResolver(observed_repo)` implementing `resolve` and `record_observed_price(spec, league, chaos_value)`.
  - `TRADE_SITE_BASE = "https://www.pathofexile.com/trade/search"`.

**Notes:** `resolve` performs NO HTTP. It builds a URL to the official trade **site** (human-facing, not `/api/trade/*`) and returns residual instructions for filters that can't be URL-encoded (documented by the spike). If a cached observation within TTL exists, it is returned as the quote.

- [ ] **Step 0 (spike): document trade-site URL pre-population**

Manually determine what the trade site accepts in its URL for pre-populated
searches (the `?q=<url-encoded-json>` query form vs. saved-search hash form).
Test 3 specs of increasing complexity in a browser and record findings, worked
examples, and the residual-instruction fallback in `docs/trade-deeplinks.md`.
The `_build_query` implementation below is written against those findings; adjust
the encoded structure to match what the spike verifies actually pre-populates.

- [ ] **Step 1: Write the failing test**

`tests/test_listings.py`:
```python
from datetime import UTC, datetime

from oracle.models import ItemSpec, ModFilter
from oracle.pricing.listings import TRADE_SITE_BASE, DeepLinkResolver


class FakeObsRepo:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, float, str]] = []

    def record(self, league: str, spec_hash: str, chaos_value: float,
               ts: str) -> None:
        self.rows.append((league, spec_hash, chaos_value, ts))

    def latest(self, league: str, spec_hash: str, ttl_seconds: int):
        for lg, sh, val, ts in reversed(self.rows):
            if lg == league and sh == spec_hash:
                return (val, ts)
        return None


def test_spec_hash_is_stable_and_order_independent() -> None:
    a = ItemSpec(base="Titanium Spirit Shield", ilvl=86,
                 mod_filters=[ModFilter(stat_id="life"), ModFilter(stat_id="es")])
    b = ItemSpec(base="Titanium Spirit Shield", ilvl=86,
                 mod_filters=[ModFilter(stat_id="es"), ModFilter(stat_id="life")])
    assert a.spec_hash() == b.spec_hash()


def test_resolve_builds_deeplink_without_http() -> None:
    resolver = DeepLinkResolver(FakeObsRepo(), ttl_seconds=3600)
    spec = ItemSpec(base="Titanium Spirit Shield", ilvl=86)
    quote = resolver.resolve(spec, "TestLeagueA")
    assert quote.deep_link.startswith(TRADE_SITE_BASE)
    assert "TestLeagueA" in quote.deep_link
    assert quote.chaos_value is None
    assert quote.source == "unresolved"


def test_observed_price_round_trip_and_reuse() -> None:
    repo = FakeObsRepo()
    resolver = DeepLinkResolver(repo, ttl_seconds=3600)
    spec = ItemSpec(base="Titanium Spirit Shield", ilvl=86)
    resolver.record_observed_price(spec, "TestLeagueA", 55.0)
    quote = resolver.resolve(spec, "TestLeagueA")
    assert quote.chaos_value == 55.0
    assert quote.source == "user-observed"
    assert quote.observed_ts is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_listings.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Implement models + resolver**

Add to `oracle/models.py`:
```python
import hashlib
import json


class ModFilter(BaseModel):
    stat_id: str
    min_value: float | None = None


class ItemSpec(BaseModel):
    base: str
    ilvl: int | None = None
    influence: str | None = None
    mod_filters: list[ModFilter] = []
    sockets: int | None = None
    links: int | None = None

    def spec_hash(self) -> str:
        payload = {
            "base": self.base,
            "ilvl": self.ilvl,
            "influence": self.influence,
            "mod_filters": sorted(
                ([f.stat_id, f.min_value] for f in self.mod_filters),
                key=lambda x: str(x[0]),
            ),
            "sockets": self.sockets,
            "links": self.links,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class ListingQuote(BaseModel):
    spec_hash: str
    league: str
    chaos_value: float | None
    deep_link: str
    residual_instructions: list[str] = []
    source: str
    observed_ts: datetime | None = None
```

`oracle/pricing/listings.py`:
```python
import json
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

from oracle.models import ItemSpec, ListingQuote

TRADE_SITE_BASE = "https://www.pathofexile.com/trade/search"


class _ObsRepo(Protocol):
    def record(self, league: str, spec_hash: str, chaos_value: float,
               ts: str) -> None: ...
    def latest(self, league: str, spec_hash: str,
               ttl_seconds: int) -> tuple[float, str] | None: ...


class ListingResolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...


def _build_query(spec: ItemSpec) -> tuple[str, list[str]]:
    """Return (url-encoded query fragment, residual human instructions).

    Structure per docs/trade-deeplinks.md. Filters the URL cannot encode are
    returned as residual instructions rather than silently dropped.
    """
    filters: dict[str, object] = {"type": spec.base}
    residual: list[str] = []
    stats = []
    for f in spec.mod_filters:
        if f.min_value is not None:
            stats.append({"id": f.stat_id, "value": {"min": f.min_value}})
        else:
            residual.append(f"Add mod filter: {f.stat_id} (no min value set)")
    query: dict[str, object] = {"query": {"status": {"option": "online"},
                                          "filters": {"type_filters": {"filters": {}}}},
                                "sort": {"price": "asc"}}
    if spec.ilvl is not None:
        query["query"]["filters"]["misc_filters"] = {  # type: ignore[index]
            "filters": {"ilvl": {"min": spec.ilvl}}}
    if stats:
        query["query"]["stats"] = [{"type": "and", "filters": stats}]  # type: ignore[index]
    query["query"]["type"] = spec.base  # type: ignore[index]
    if spec.influence is not None:
        residual.append(f"Set influence filter: {spec.influence}")
    encoded = quote(json.dumps(query, separators=(",", ":")))
    return encoded, residual


class DeepLinkResolver:
    def __init__(self, observed_repo: _ObsRepo, ttl_seconds: int) -> None:
        self._repo = observed_repo
        self._ttl = ttl_seconds

    def _deep_link(self, spec: ItemSpec, league: str) -> tuple[str, list[str]]:
        encoded, residual = _build_query(spec)
        url = f"{TRADE_SITE_BASE}/{quote(league)}?q={encoded}"
        return url, residual

    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote:
        h = spec.spec_hash()
        url, residual = self._deep_link(spec, league)
        cached = self._repo.latest(league, h, self._ttl)
        if cached is not None:
            value, ts = cached
            return ListingQuote(
                spec_hash=h, league=league, chaos_value=value, deep_link=url,
                residual_instructions=residual, source="user-observed",
                observed_ts=datetime.fromisoformat(ts),
            )
        return ListingQuote(
            spec_hash=h, league=league, chaos_value=None, deep_link=url,
            residual_instructions=residual, source="unresolved",
            observed_ts=None,
        )

    def record_observed_price(self, spec: ItemSpec, league: str,
                              chaos_value: float) -> None:
        ts = datetime.now(tz=UTC).isoformat()
        self._repo.record(league, spec.spec_hash(), chaos_value, ts)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_listings.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/pricing/listings.py oracle/models.py docs/trade-deeplinks.md tests/test_listings.py
git commit -m "feat: ItemSpec + compliant DeepLinkResolver with residual instructions"
```

---

### Task 11: Observed-price repository (SQLite-backed, TTL)

**Files:**
- Create: `oracle/store/observations.py`, `tests/test_observations.py`

**Interfaces:**
- Consumes: `connect`.
- Produces:
  - `ObservedPriceRepo(conn)` matching the `_ObsRepo` Protocol from Task 10:
    - `.record(league, spec_hash, chaos_value, ts: str) -> None`
    - `.latest(league, spec_hash, ttl_seconds) -> tuple[float, str] | None` (returns most recent within TTL, else None).

- [ ] **Step 1: Write the failing test**

`tests/test_observations.py`:
```python
from datetime import UTC, datetime, timedelta

from oracle.store.db import connect
from oracle.store.observations import ObservedPriceRepo


def test_record_and_latest_within_ttl(tmp_path) -> None:
    repo = ObservedPriceRepo(connect(str(tmp_path / "t.db")))
    now = datetime.now(tz=UTC).isoformat()
    repo.record("TestLeagueA", "abc", 55.0, now)
    got = repo.latest("TestLeagueA", "abc", ttl_seconds=3600)
    assert got is not None and got[0] == 55.0


def test_expired_observation_returns_none(tmp_path) -> None:
    repo = ObservedPriceRepo(connect(str(tmp_path / "t.db")))
    old = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    repo.record("TestLeagueA", "abc", 55.0, old)
    assert repo.latest("TestLeagueA", "abc", ttl_seconds=3600) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observations.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Implement `oracle/store/observations.py`**

```python
import sqlite3
from datetime import UTC, datetime, timedelta


class ObservedPriceRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, league: str, spec_hash: str, chaos_value: float,
               ts: str) -> None:
        self._conn.execute(
            "INSERT INTO observed_prices (league, spec_hash, chaos_value, observed_ts)"
            " VALUES (?,?,?,?)",
            (league, spec_hash, chaos_value, ts),
        )
        self._conn.commit()

    def latest(self, league: str, spec_hash: str,
               ttl_seconds: int) -> tuple[float, str] | None:
        row = self._conn.execute(
            "SELECT chaos_value, observed_ts FROM observed_prices "
            "WHERE league=? AND spec_hash=? ORDER BY observed_ts DESC LIMIT 1",
            (league, spec_hash),
        ).fetchone()
        if row is None:
            return None
        observed = datetime.fromisoformat(row["observed_ts"])
        if datetime.now(tz=UTC) - observed > timedelta(seconds=ttl_seconds):
            return None
        return (row["chaos_value"], row["observed_ts"])
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_observations.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/store/observations.py tests/test_observations.py
git commit -m "feat: SQLite observed-price repo with TTL expiry"
```

---

### Task 12: CLI wiring (leagues / prices / modpool / link)

**Files:**
- Modify: `oracle/cli.py`
- Create: `oracle/app.py` (composition root), `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: all services.
- Produces:
  - `oracle/app.py`: `build_services(settings) -> Services` dataclass bundling `league`, `gamedata`, `price`, `resolver`, plus `ALLOWED_HOSTS = {"api.pathofexile.com", "poe.ninja", "www.pathofexile.com"}` (note: `www.pathofexile.com` is used ONLY for building deep-link URL strings, never for HTTP — the http client's allowlist is the narrower `{"api.pathofexile.com", "poe.ninja"}`).
  - CLI commands: `leagues`, `prices <category> --league`, `modpool <base> --ilvl [--influence]`, `link <base> --ilvl [--influence] --json`.

- [ ] **Step 1: Write the failing test** (services injected via a builder override)

`tests/test_cli_commands.py`:
```python
from typer.testing import CliRunner

from oracle.cli import app
from oracle.models import League, Mod

runner = CliRunner()


class FakeServices:
    class _League:
        def list_leagues(self, realm: str = "pc") -> list[League]:
            return [League(id="TestLeagueA", realm="pc", ninja_available=True)]

    class _GameData:
        def mod_pool(self, base, ilvl, influence=None, tags=None) -> list[Mod]:
            return [Mod(id="m1", name="of Life", weight=1000, group="Life",
                        tags=["life"], domain="item",
                        generation_type="suffix", required_level=1)]

    league = _League()
    gamedata = _GameData()


def test_leagues_command(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["leagues"])
    assert result.exit_code == 0
    assert "TestLeagueA" in result.stdout


def test_modpool_command(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["modpool", "Vaal Regalia", "--ilvl", "86"])
    assert result.exit_code == 0
    assert "of Life" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_commands.py -v`
Expected: FAIL (commands not defined).

- [ ] **Step 3: Implement composition root + commands**

`oracle/app.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from oracle.config import Settings, load_settings
from oracle.gamedata.service import GameDataService
from oracle.http.client import HttpClient
from oracle.league.service import LeagueService
from oracle.pricing.listings import DeepLinkResolver
from oracle.pricing.ninja import NinjaClient
from oracle.pricing.service import PriceService
from oracle.store.db import connect
from oracle.store.observations import ObservedPriceRepo

HTTP_ALLOWED_HOSTS = {"api.pathofexile.com", "poe.ninja"}


@dataclass
class Services:
    settings: Settings
    league: LeagueService
    gamedata: GameDataService
    price: PriceService
    resolver: DeepLinkResolver


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or load_settings()
    http = HttpClient(settings.user_agent, HTTP_ALLOWED_HOSTS)
    ninja = NinjaClient(http)
    conn = connect(settings.store.db_path)
    gamedata = GameDataService.from_snapshot(Path("snapshots/repoe"))
    return Services(
        settings=settings,
        league=LeagueService(http, ninja_probe=ninja.league_is_covered),
        gamedata=gamedata,
        price=PriceService(ninja, conn, settings),
        resolver=DeepLinkResolver(ObservedPriceRepo(conn),
                                  settings.cache.observed_price_ttl_seconds),
    )
```

`oracle/cli.py` (replace prior content, keep `version`):
```python
import json as _json

import typer

from oracle.app import build_services
from oracle.models import ItemSpec

app = typer.Typer(help="Oracle — PoE1 Crafting Companion", no_args_is_help=True)


def _services():  # indirection so tests can monkeypatch
    return build_services()


@app.command()
def version() -> None:
    """Print the Oracle version."""
    from oracle import __version__

    typer.echo(__version__)


@app.command()
def leagues() -> None:
    """List live leagues with poe.ninja coverage flags."""
    for lg in _services().league.list_leagues():
        flag = "ninja" if lg.ninja_available else "no-ninja"
        typer.echo(f"{lg.id}\t{lg.realm}\t{flag}")


@app.command()
def prices(category: str, league: str = typer.Option(...)) -> None:
    """Show cleaned chaos-equivalent prices for a category in a league."""
    for p in _services().price.prices(category, league):
        typer.echo(
            f"{p.key}\t{p.chaos_value:.2f}c\tdepth={p.sample_depth}\t"
            f"conf={p.confidence:.2f}\t{p.source}\t{p.ts.isoformat()}"
        )


@app.command()
def modpool(base: str, ilvl: int = typer.Option(...),
            influence: str = typer.Option(None)) -> None:
    """Show the mod pool for a base at an item level."""
    for m in _services().gamedata.mod_pool(base, ilvl, influence):
        typer.echo(f"{m.name}\t{m.generation_type}\t{m.group}\tw={m.weight}")


@app.command()
def link(base: str, ilvl: int = typer.Option(None),
         influence: str = typer.Option(None),
         league: str = typer.Option(...),
         as_json: bool = typer.Option(False, "--json")) -> None:
    """Emit a compliant trade-site deep-link for an item spec."""
    spec = ItemSpec(base=base, ilvl=ilvl, influence=influence)
    quote = _services().resolver.resolve(spec, league)
    if as_json:
        typer.echo(quote.model_dump_json(indent=2))
        return
    typer.echo(quote.deep_link)
    for note in quote.residual_instructions:
        typer.echo(f"  - {note}")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli_commands.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/app.py oracle/cli.py tests/test_cli_commands.py
git commit -m "feat: CLI commands (leagues/prices/modpool/link) with composition root"
```

---

### Task 13: Compliance + no-hardcoded-league guard tests

**Files:**
- Create: `tests/test_compliance.py`

**Interfaces:**
- Consumes: the running codebase and `HttpClient`.
- Produces: two guard tests enforcing Global Constraints.

- [ ] **Step 1: Write the tests**

`tests/test_compliance.py`:
```python
import re
from pathlib import Path

import pytest

from oracle.http.client import ComplianceError, HttpClient

SRC_DIRS = [Path("oracle"), Path("scanner"), Path("advisor")]


def test_http_client_blocks_trade_api() -> None:
    client = HttpClient("ua", {"api.pathofexile.com", "poe.ninja"})
    with pytest.raises(ComplianceError):
        client.get_json("https://www.pathofexile.com/api/trade/search/Standard")


def test_no_trade_api_string_in_source() -> None:
    offenders = []
    for d in SRC_DIRS:
        for py in d.rglob("*.py"):
            text = py.read_text()
            if "/api/trade/" in text:
                offenders.append(str(py))
    assert not offenders, f"/api/trade/ referenced in: {offenders}"


def test_no_hardcoded_league_name_in_source() -> None:
    # "Standard" (and other league names) must not be hardcoded in code.
    offenders = []
    for d in SRC_DIRS:
        for py in d.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if re.search(r"\bStandard\b", line):
                    offenders.append(f"{py}:{i}")
    assert not offenders, f"hardcoded league name in: {offenders}"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_compliance.py -v`
Expected: PASS. If `test_no_hardcoded_league_name_in_source` fails, move the
offending default into `config/settings.toml` (it must live only there).

- [ ] **Step 3: Full suite + quality gates**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest --cov=oracle --cov-report=term-missing`
Expected: all green; core coverage healthy.

- [ ] **Step 4: Commit**

```bash
git add tests/test_compliance.py
git commit -m "test: compliance allowlist and no-hardcoded-league guards"
```

---

### Task 14: Live smoke tests + Phase 0 DoD verification

**Files:**
- Create: `tests/test_live_smoke.py`

**Interfaces:**
- Consumes: real network (marked `@pytest.mark.live`, skipped in CI).

- [ ] **Step 1: Write live smoke tests**

`tests/test_live_smoke.py`:
```python
import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_leagues_live() -> None:
    leagues = build_services().league.list_leagues()
    assert any(lg.ninja_available for lg in leagues)


def test_prices_currency_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    prices = svc.price.prices("Currency", default)
    assert prices
    assert all(p.chaos_value > 0 for p in prices)
```

- [ ] **Step 2: Run live smoke locally**

Run: `uv run pytest -m live -v`
Expected: PASS against live data. (This is a local DoD gate, not CI.)

- [ ] **Step 3: Manual DoD checklist** (record results in `docs/phase0-dod.md`)

- `uv run oracle leagues` shows the live league set + coverage flags.
- `uv run oracle prices currency --league <a-live-league>` shows cleaned prices with depth, timestamps, confidence.
- `uv run oracle modpool "Vaal Regalia" --ilvl 86` matches poedb spot-check for 3 bases.
- `uv run oracle link "Titanium Spirit Shield" --ilvl 86 --league <a-live-league>` produces a URL that pre-populates the trade search (verify for 3 specs of increasing complexity).
- Observed-price round-trip works.

- [ ] **Step 4: Commit + push**

```bash
git add tests/test_live_smoke.py docs/phase0-dod.md
git commit -m "test: live smoke tests and Phase 0 DoD verification notes"
git push
```

---

## Self-Review

**Spec coverage (PRD §Phase 0 deliverables → tasks):**
- Repo scaffold → Task 1 ✓
- League Service → Task 5 (+ ninja probe Task 7) ✓
- Game Data Service → Task 6 ✓
- Price Service (ninja, percentile+outlier, liquidity/depth, maturity, SQLite append-only, source-tagged) → Tasks 7, 8, 9 ✓
- ListingResolver + DeepLinkResolver (ItemSpec, URL construction, observed-price record/retrieve/expire) → Tasks 10, 11 ✓
- Config single settings file → Task 2 ✓
- Spike `docs/trade-deeplinks.md` → Task 10 Step 0 ✓
- Compliance allowlist test → Task 13 ✓
- CLI `leagues/prices/modpool/link` → Task 12 ✓
- DoD verification (live) → Task 14 ✓

**Placeholder scan:** No "TBD"/"handle edge cases" left; the two empirical spikes (RePoE snapshot in Task 6 Step 0, trade-link format in Task 10 Step 0) are explicit, bounded discovery steps with documented outputs, not code placeholders.

**Type consistency:** `Price`, `League`, `Maturity`, `Mod`, `ItemSpec`, `ModFilter`, `ListingQuote` defined in `oracle/models.py`; `NinjaLine` in `ninja.py`; `AggResult` in `aggregate.py`. `ninja_probe: Callable[[str], bool]` (Task 5) is satisfied by `NinjaClient.league_is_covered` (Task 7). `_ObsRepo` Protocol (Task 10) matched by `ObservedPriceRepo` (Task 11). CLI `_services()` indirection consistent between Task 12 and Task 13.

**Note on Task ordering for execution:** Task 7 provides the `ninja_probe` used by Task 5's real wiring, but Task 5 is tested with a fake probe, so it can be built first. Task 12 (composition root) depends on Tasks 2–11 and must come after them.
