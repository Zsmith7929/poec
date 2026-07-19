# Oracle Phase 2 (Tier-2 Gamble EV) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tier-2 (single-roll gamble) expected-value layer — a rules-as-data odds-table registry, an analytic EV/variance engine that reuses the Phase 1 `PriceResolver` (auto + verify), bankroll math, a deterministic Monte-Carlo "factory" planner, a clearly-separated PROBABILISTIC section in the scan report, append-only EV-result persistence, an `oracle factory` CLI command, and T2 integration into `oracle scan` — to the PRD Phase 2 DoD. This is the second profitable milestone.

**Architecture:** A new set of modules under `oracle/scanner/` (inherits mypy-strict and the compliance grep) sits on top of the Phase 1 `PriceResolver` (`resolve_auto`/`resolve_verify` -> `ResolvedPrice`). Odds tables live in `data/odds_t2/*.yaml` (Pydantic-validated, `extra="forbid"`, fail-loud on unknown shapes AND on outcome probabilities that do not sum to ~1.0 within a configured tolerance; version-stamped via a directory sha256 digest). Each table's input and each outcome's `result` are `PriceRef`s resolved to chaos values exactly as in Phase 1 — a `None` price is surfaced and flagged, never fabricated or silently treated as 0. The EV engine computes `ev_gross = Σ p·price`, `ev_net = ev_gross − input_cost − service_cost`, `variance = Σ p·(price − ev_gross)²`, `stddev = sqrt(variance)`. Bankroll math derives affordable attempts and probability-of-net-loss analytically from the per-attempt distribution. Factory mode samples the outcome distribution `N` times with an injected `random.Random(seed)` for deterministic P10/P50/P90. Reports embed league, snapshot timestamp, and the odds-rule-file version. League is always a runtime parameter; compliance is unchanged (only `api.pathofexile.com` + `poe.ninja` fetched; specific-listing pricing only via the existing `DeepLinkResolver`).

**Tech Stack:** Python 3.12+, uv, Typer, Pydantic v2, PyYAML, stdlib `sqlite3`, stdlib `random`, stdlib `math`, ruff, mypy (strict on `oracle/`), pytest, hypothesis. Builds directly on the Phase 0/1 services in `oracle/`. **No numpy** (PRD defers vectorization to Phase 3).

## Global Constraints

- Python `>=3.12`. Managed with **uv** (`uv sync`, `uv run`). mypy **strict** on `oracle/`; ruff clean; tests green; live tests `@pytest.mark.live` (skipped in CI).
- All new T2 logic lives under **`oracle/scanner/`** (a subpackage of the already-strict `oracle` package) so it inherits strict typing and the existing compliance grep — no new top-level package, no `[tool.mypy] files` change.
- **Compliance UNCHANGED (hard):** only `api.pathofexile.com` + `poe.ninja` are ever fetched over HTTP; no `/api/trade/*`, ever; specific-listing pricing only via the existing `DeepLinkResolver` (human-in-the-loop). The compliance guard test (`tests/test_compliance.py`) must keep passing — no new module may issue HTTP directly, and no source file may contain the string `/api/trade/`.
- **League always a runtime param; NO hardcoded league name** in code, tests, or fixtures. The compliance guard now scans `tests/` too for `\b(Standard|Hardcore|Settlers)\b` — use invented names like `TestLeagueA`. `"Standard"` may appear ONLY as the config default in `config/settings.toml`.
- **Rules as data:** odds tables live in `data/odds_t2/*.yaml` with Pydantic schema validation, `extra="forbid"`, fail-loud on unknown shapes AND on probabilities that don't sum to ~1.0 (within tolerance).
- **Determinism boundary:** the engine produces numbers, never prose. NEVER fabricate a price — an outcome or input with no resolvable price yields `None` and is surfaced/flagged, never guessed. Robust pricing / liquidity / reproducibility metadata as in Phase 1 (source attribution, confidence, timestamps; reports embed league + snapshot ts + rule-file version).
- **Monte Carlo MUST be deterministic in tests:** use stdlib `random.Random(seed)` with an injected seed (do NOT add numpy in Phase 2). No unseeded `random.*` module-level calls in engine code.
- **Fail loud:** unknown YAML shapes, bad probability sums, and unknown enum values raise.
- ruff clean. Tests green in CI. Commit after every task. Commit message trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

**Phase 0/1 interfaces this plan consumes (exact signatures, do not change):**
- `oracle.scanner.models.PriceRef(category: str, key: str, qty: float = 1.0, influence: str | None = None, ilvl: int | None = None)` — `model_config = ConfigDict(extra="forbid")`.
- `oracle.scanner.resolve.PriceResolver(price_service, resolver, min_sample_depth: int)` with `.resolve_auto(ref: PriceRef, league: str) -> ResolvedPrice`, `.resolve_verify(ref: PriceRef, league: str) -> ResolvedPrice`, `.clear_cache() -> None`.
- `oracle.scanner.resolve.ResolvedPrice(chaos_value: float | None, liquidity: float, confidence: float, source: str, deep_link: str | None)` — a frozen dataclass.
- `oracle.scanner.report.ScanReport(league, snapshot_ts: datetime, rule_version: str, rows: list[ScanRow])` — frozen dataclass with `.to_terminal()`, `.to_markdown()`, `.to_json()`; `write_report(report, reports_dir) -> tuple[Path, Path]`.
- `oracle.scanner.service.ScanService(engine, repo, rule_version, reports_dir, clock)` with `.run(league, min_margin=None) -> tuple[ScanReport, Path, Path]`.
- `oracle.store.db.connect(db_path) -> sqlite3.Connection`; `MIGRATIONS: list[str]` (additive/idempotent, `CREATE ... IF NOT EXISTS`).
- `oracle.config.Settings` / `load_settings(path=None)`; existing `ScannerSettings`, `PricingSettings`.
- `oracle.app.build_services(settings=None) -> Services`; `Services` dataclass (`settings`, `league`, `gamedata`, `price`, `resolver`, `scan`); `HTTP_ALLOWED_HOSTS`.
- `oracle.cli.app`, `oracle.cli._services()` (indirection so tests monkeypatch).

---

### Task 1: T2 models (Outcome / OddsTable / EvRow / OutcomeEv) + `[t2]` config section

**Files:**
- Create: `oracle/scanner/t2_models.py`, `tests/test_t2_models.py`
- Modify: `oracle/config.py` (add `T2Settings` + `t2` field on `Settings`), `config/settings.toml` (add `[t2]`)

**Interfaces:**
- Consumes: `oracle.scanner.models.PriceRef`.
- Produces (`oracle/scanner/t2_models.py`):
  - `Outcome(result: PriceRef, probability: float, notes: str = "")` — `probability` in `[0, 1]`; `model_config = ConfigDict(extra="forbid")`.
  - `OddsTable(id: str, name: str, input: PriceRef, service_cost: float = 0.0, outcomes: list[Outcome], source: str, patch_validity: str = "", enabled: bool = True, prob_sum_tolerance: float | None = None)` — `model_config = ConfigDict(extra="forbid")`; a model-validator raises `ValueError` if `Σ probability` deviates from `1.0` by more than the effective tolerance (`prob_sum_tolerance` if set, else a default checked by the registry — Task 2 passes the config tolerance in; the model itself enforces its own field when present).
  - `OutcomeEv(result_key: str, probability: float, price: float | None, contribution: float, notes: str)` (Pydantic model) — per-outcome breakdown; `price is None` means unresolved (excluded from EV, flagged).
  - `EvRow(table_id, name, ev_gross: float, ev_net: float, input_cost: float, service_cost: float, variance: float, stddev: float, per_outcome: list[OutcomeEv], liquidity: float, confidence: float, bankroll_note: str, source: str, deep_link: str | None, unresolved_outcomes: int, ts: datetime)` (Pydantic model; nullable-free numeric fields because unresolved outcomes are *excluded* and counted, not represented as `None` EV — see Task 4 semantics).
- Produces (`oracle/config.py`): `T2Settings(prob_sum_tolerance: float, default_service_cost: float, mc_trials: int, mc_seed: int)`, `Settings.t2: T2Settings`.

**Notes:** `Outcome.probability` uses `Field(ge=0.0, le=1.0)`. `OddsTable` enforces its own `prob_sum_tolerance` only when the field is explicitly set on the table; the registry (Task 2) applies the global `[t2] prob_sum_tolerance` when a table omits it, so both a per-table override and a global default are fail-loud.

- [ ] **Step 1: Write the failing test**

`tests/test_t2_models.py`:
```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oracle.config import T2Settings, load_settings
from oracle.scanner.models import PriceRef
from oracle.scanner.t2_models import EvRow, OddsTable, Outcome, OutcomeEv


def _ref(key: str) -> PriceRef:
    return PriceRef(category="UniqueAccessory", key=key)


def test_outcome_probability_bounds() -> None:
    Outcome(result=_ref("X"), probability=0.5)
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=1.5)
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=-0.1)


def test_outcome_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=0.5, bogus=1)  # type: ignore[call-arg]


def test_oddstable_valid_sum_ok() -> None:
    t = OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[
            Outcome(result=_ref("A"), probability=0.25),
            Outcome(result=_ref("B"), probability=0.25),
            Outcome(result=_ref("C"), probability=0.5),
        ],
        source="https://example.com/odds",
        prob_sum_tolerance=1e-6,
    )
    assert len(t.outcomes) == 3
    assert t.enabled is True
    assert t.service_cost == 0.0


def test_oddstable_bad_sum_fails_loud() -> None:
    with pytest.raises(ValidationError):
        OddsTable(
            id="t",
            name="T",
            input=PriceRef(category="Currency", key="Vaal Orb"),
            outcomes=[
                Outcome(result=_ref("A"), probability=0.25),
                Outcome(result=_ref("B"), probability=0.25),
            ],  # sums to 0.5
            source="https://example.com/odds",
            prob_sum_tolerance=1e-6,
        )


def test_oddstable_within_tolerance_ok() -> None:
    # 0.333*3 = 0.999; tolerance 0.01 accepts it.
    OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[Outcome(result=_ref(k), probability=0.333) for k in "ABC"],
        source="https://example.com/odds",
        prob_sum_tolerance=0.01,
    )


def test_oddstable_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        OddsTable(
            id="t",
            name="T",
            input=PriceRef(category="Currency", key="Vaal Orb"),
            outcomes=[Outcome(result=_ref("A"), probability=1.0)],
            source="s",
            bogus=1,  # type: ignore[call-arg]
        )


def test_evrow_and_outcome_ev_construct() -> None:
    row = EvRow(
        table_id="t",
        name="T",
        ev_gross=100.0,
        ev_net=90.0,
        input_cost=8.0,
        service_cost=2.0,
        variance=25.0,
        stddev=5.0,
        per_outcome=[OutcomeEv(result_key="A", probability=1.0, price=100.0,
                               contribution=100.0, notes="")],
        liquidity=40.0,
        confidence=0.8,
        bankroll_note="10 attempts at 10c each",
        source="ninja:x",
        deep_link=None,
        unresolved_outcomes=0,
        ts=datetime.now(tz=UTC),
    )
    assert row.ev_net == 90.0
    assert row.per_outcome[0].price == 100.0


def test_t2_settings_loaded_from_config() -> None:
    settings = load_settings()
    assert isinstance(settings.t2, T2Settings)
    assert settings.t2.prob_sum_tolerance > 0.0
    assert settings.t2.mc_trials >= 1
    assert settings.t2.mc_seed >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_t2_models.py -v`
Expected: FAIL (no module `oracle.scanner.t2_models`; no `T2Settings`).

- [ ] **Step 3: Implement models + config**

`oracle/scanner/t2_models.py`:
```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oracle.scanner.models import PriceRef


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: PriceRef
    probability: float = Field(ge=0.0, le=1.0)
    notes: str = ""


class OddsTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    input: PriceRef
    service_cost: float = 0.0
    outcomes: list[Outcome]
    source: str
    patch_validity: str = ""
    enabled: bool = True
    prob_sum_tolerance: float | None = None

    @model_validator(mode="after")
    def _check_probability_sum(self) -> "OddsTable":
        if self.prob_sum_tolerance is None:
            return self  # registry applies the global default before/at load
        total = sum(o.probability for o in self.outcomes)
        if abs(total - 1.0) > self.prob_sum_tolerance:
            raise ValueError(
                f"odds table '{self.id}' probabilities sum to {total}, "
                f"not ~1.0 (tolerance {self.prob_sum_tolerance})"
            )
        return self


class OutcomeEv(BaseModel):
    result_key: str
    probability: float
    price: float | None
    contribution: float
    notes: str


class EvRow(BaseModel):
    table_id: str
    name: str
    ev_gross: float
    ev_net: float
    input_cost: float
    service_cost: float
    variance: float
    stddev: float
    per_outcome: list[OutcomeEv]
    liquidity: float
    confidence: float
    bankroll_note: str
    source: str
    deep_link: str | None
    unresolved_outcomes: int
    ts: datetime
```

Add to `oracle/config.py` — a new settings model and a field on `Settings`:
```python
class T2Settings(BaseModel):
    prob_sum_tolerance: float = Field(gt=0.0)
    default_service_cost: float = Field(ge=0.0)
    mc_trials: int = Field(ge=1)
    mc_seed: int = Field(ge=0)
```
and add to `class Settings` (after `scanner: ScannerSettings`):
```python
    t2: T2Settings
```

Add to `config/settings.toml`:
```toml
[t2]
prob_sum_tolerance = 0.01     # odds tables must sum to 1.0 within this tolerance
default_service_cost = 0.0    # default per-attempt service cost (e.g. temple carry) in chaos
mc_trials = 10000             # default Monte-Carlo trials for factory mode
mc_seed = 1234                # default seed for reproducible factory runs
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_t2_models.py tests/test_config.py -v && uv run mypy`
Expected: PASS, mypy clean. (`tests/test_config.py` still passes because the new `[t2]` section is present in the default file.)

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/t2_models.py oracle/config.py config/settings.toml tests/test_t2_models.py
git commit -m "feat: T2 models (Outcome/OddsTable/EvRow) with prob-sum validation and [t2] settings"
```

---

### Task 2: Odds registry (load + validate `data/odds_t2/*.yaml`, fail-loud, dir-digest versioned) + seed tables

**Files:**
- Create: `oracle/scanner/t2_registry.py`, `data/odds_t2/vaal_amulet.yaml`, `data/odds_t2/temple_double_corrupt.yaml`, `data/odds_t2/tainted_currency.yaml`, `tests/test_t2_registry.py`

**Interfaces:**
- Consumes: `oracle.scanner.t2_models.OddsTable`, `Outcome`; `oracle.scanner.models.PriceRef`.
- Produces:
  - `OddsRegistryError(Exception)` — raised on unknown/invalid YAML shapes and bad probability sums.
  - `OddsRegistry(tables: list[OddsTable], version: str)` with `.enabled() -> list[OddsTable]` (only `enabled is True`) and `.version` (str, `sha256:<16hex>` over the sorted concatenation of all file bytes so a data edit changes the stamped version deterministically).
  - `load_odds_registry(dir_path: Path, prob_sum_tolerance: float) -> OddsRegistry` — reads every `*.yaml` (sorted by name), validates each `tables:`-list entry via `OddsTable.model_validate`, applies `prob_sum_tolerance` to any table that omits its own, fails loud on malformed shapes / bad sums, computes the directory digest.
  - `DEFAULT_ODDS_DIR = Path("data/odds_t2")`.

**Notes:** Each YAML file's top level is a mapping with a `tables:` list (mirrors Phase 1's `transforms:` key). Applying the global tolerance: for each raw entry that lacks `prob_sum_tolerance`, set it to `prob_sum_tolerance` before `model_validate`, so the model-validator always runs against a concrete tolerance. Version digest concatenates `path.read_bytes()` for files in sorted order (deterministic across runs).

- [ ] **Step 1: Write the failing test**

`tests/test_t2_registry.py`:
```python
from pathlib import Path

import pytest

from oracle.scanner.t2_registry import (
    DEFAULT_ODDS_DIR,
    OddsRegistry,
    OddsRegistryError,
    load_odds_registry,
)

TOL = 0.01


def test_loads_default_seed_and_versions() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    assert isinstance(reg, OddsRegistry)
    assert reg.version.startswith("sha256:")
    assert len(reg.tables) >= 3  # seed: vaal amulet, temple double-corrupt, tainted


def test_seed_ids_unique() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    ids = [t.id for t in reg.tables]
    assert len(ids) == len(set(ids))


def test_seed_tables_cite_source_and_probs_sum() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    for t in reg.tables:
        assert t.source, f"{t.id} missing source"
        total = sum(o.probability for o in t.outcomes)
        assert abs(total - 1.0) <= TOL, f"{t.id} sums to {total}"


def test_seed_has_bricked_salvage_outcome() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    all_notes = " ".join(o.notes.lower() for t in reg.tables for o in t.outcomes)
    assert "brick" in all_notes  # at least one bricked/salvage outcome documented


def test_enabled_filters_disabled() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    assert all(t.enabled for t in reg.enabled())


def test_version_changes_with_content(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "a.yaml").write_text(
        "tables:\n  - id: t1\n    name: A\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: s\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 1.0}\n"
    )
    v1 = load_odds_registry(d, TOL).version
    (d / "a.yaml").write_text(
        "tables:\n  - id: t1\n    name: B\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: s\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 1.0}\n"
    )
    v2 = load_odds_registry(d, TOL).version
    assert v1 != v2


def test_bad_probability_sum_fails_loud(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text(
        "tables:\n  - id: t1\n    name: A\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: s\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 0.3}\n"
        "      - {result: {category: UniqueAccessory, key: Y}, probability: 0.3}\n"
    )
    with pytest.raises(OddsRegistryError):
        load_odds_registry(d, TOL)


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text(
        "tables:\n  - id: t1\n    name: A\n    unexpected_key: 1\n"
    )
    with pytest.raises(OddsRegistryError):
        load_odds_registry(d, TOL)


def test_missing_tables_key_fails_loud(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text("not_tables: []\n")
    with pytest.raises(OddsRegistryError):
        load_odds_registry(d, TOL)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_t2_registry.py -v`
Expected: FAIL (no module `oracle.scanner.t2_registry`; no seed dir yet).

- [ ] **Step 3: Implement the registry**

`oracle/scanner/t2_registry.py`:
```python
import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from oracle.scanner.t2_models import OddsTable

DEFAULT_ODDS_DIR = Path("data/odds_t2")


class OddsRegistryError(Exception):
    """Raised when an odds file has an unknown shape or bad probability sum."""


class OddsRegistry:
    def __init__(self, tables: list[OddsTable], version: str) -> None:
        self.tables = tables
        self.version = version

    def enabled(self) -> list[OddsTable]:
        return [t for t in self.tables if t.enabled]


def load_odds_registry(dir_path: Path, prob_sum_tolerance: float) -> OddsRegistry:
    files = sorted(dir_path.glob("*.yaml"), key=lambda p: p.name)
    hasher = hashlib.sha256()
    tables: list[OddsTable] = []
    for path in files:
        raw = path.read_bytes()
        hasher.update(raw)
        try:
            doc = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise OddsRegistryError(f"{path.name}: invalid YAML: {exc}") from exc
        if not isinstance(doc, dict) or "tables" not in doc:
            raise OddsRegistryError(f"{path.name}: top-level 'tables' key required")
        entries = doc["tables"]
        if not isinstance(entries, list):
            raise OddsRegistryError(f"{path.name}: 'tables' must be a list")
        for entry in entries:
            if isinstance(entry, dict) and entry.get("prob_sum_tolerance") is None:
                entry = {**entry, "prob_sum_tolerance": prob_sum_tolerance}
            try:
                tables.append(OddsTable.model_validate(entry))
            except ValidationError as exc:
                raise OddsRegistryError(f"{path.name}: invalid table: {exc}") from exc
    version = "sha256:" + hasher.hexdigest()[:16]
    return OddsRegistry(tables, version)
```

- [ ] **Step 4: Write the seed `data/odds_t2/*.yaml`**

`PriceRef` categories use ninja `type=` values the Phase 0 client supports (`Currency`, `UniqueAccessory`, `UniqueArmour`, `UniqueWeapon`, `Fragment`). Probabilities per table sum to ~1.0. Each table cites a `source` URL and a `patch_validity`. **Illustrative-by-design (revalidated on patch day)** — the numbers are placeholders whose *shape* is correct; DoD golden EV is proven with pinned prices in Task 8, and patch-day revalidation is the runbook's job. Each table includes a "bricked" outcome carrying a salvage-value `PriceRef` (a corrupted/vendor scrap the item is worth after a bad roll).

`data/odds_t2/vaal_amulet.yaml`:
```yaml
# Tier-2 gamble odds. Rules-as-data: edit + revalidate on patch day.
# Illustrative probabilities (shape correct; magnitudes revalidated per patch).
# category values map to poe.ninja `type=` values supported by the Phase 0 client.
tables:
  - id: vaal_amulet_corrupt
    name: "Vaal Orb on a rare amulet (item-class corruption outcomes)"
    input: {category: Currency, key: "Vaal Orb", qty: 1.0}
    service_cost: 0.0
    source: "https://www.poewiki.net/wiki/Vaal_Orb (revalidate per patch)"
    patch_validity: "Illustrative Vaal outcome split for amulets; revalidate on patch day."
    outcomes:
      - result: {category: UniqueAccessory, key: "Amulet No Change (resell)"}
        probability: 0.25
        notes: "No change: item survives unmodified, priced as the input rare's resale."
      - result: {category: UniqueAccessory, key: "Amulet Corrupted Implicit A"}
        probability: 0.25
        notes: "Gains a corrupted implicit (variant A)."
      - result: {category: UniqueAccessory, key: "Amulet Corrupted Implicit B"}
        probability: 0.25
        notes: "Gains a corrupted implicit (variant B)."
      - result: {category: Currency, key: "Vaal salvage scrap"}
        probability: 0.25
        notes: "Bricked: reforged rare / white socket loss; salvage value only."
```

`data/odds_t2/temple_double_corrupt.yaml`:
```yaml
# Temple of Atzoatl double-corrupt on uniques. Illustrative; revalidate per patch.
tables:
  - id: temple_double_corrupt_unique
    name: "Temple double-corrupt on a popular unique"
    input: {category: UniqueArmour, key: "Popular Unique (input copy)", qty: 1.0}
    service_cost: 20.0          # temple carry / service cost in chaos (config-overridable)
    source: "https://www.poewiki.net/wiki/Corrupting_Altar (revalidate per patch)"
    patch_validity: "Illustrative double-corrupt split; revalidate on patch day."
    outcomes:
      - result: {category: UniqueArmour, key: "Unique Double-Corrupt Jackpot"}
        probability: 0.10
        notes: "Best-case double-implicit jackpot outcome."
      - result: {category: UniqueArmour, key: "Unique Good Corrupt"}
        probability: 0.20
        notes: "Useful single beneficial corruption."
      - result: {category: UniqueArmour, key: "Popular Unique (input copy)"}
        probability: 0.35
        notes: "No meaningful change: resells as the input unique."
      - result: {category: Currency, key: "Vaal salvage scrap"}
        probability: 0.35
        notes: "Bricked: corrupted/worthless; salvage value only."
```

`data/odds_t2/tainted_currency.yaml`:
```yaml
# Tainted currency set (corrupted-item currency). Illustrative; revalidate per patch.
tables:
  - id: tainted_mythic_orb
    name: "Tainted Mythic Orb on a corrupted unique"
    input: {category: Currency, key: "Tainted Mythic Orb", qty: 1.0}
    service_cost: 0.0
    source: "https://www.poewiki.net/wiki/Tainted_currency (revalidate per patch)"
    patch_validity: "Illustrative tainted-currency split; revalidate on patch day."
    outcomes:
      - result: {category: UniqueWeapon, key: "Reforged Corrupted Unique A"}
        probability: 0.30
        notes: "Reforges into a valuable corrupted unique (variant A)."
      - result: {category: UniqueWeapon, key: "Reforged Corrupted Unique B"}
        probability: 0.30
        notes: "Reforges into a corrupted unique (variant B)."
      - result: {category: Currency, key: "Tainted salvage scrap"}
        probability: 0.40
        notes: "Bricked: low-value reforge; salvage value only."
```

*Lab enchant pools:* OMITTED from the seed — reliable per-helmet enchant probabilities are not cleanly obtainable without a curated source. Documented here so the omission is explicit; add a `data/odds_t2/lab_enchants.yaml` on a patch day once a cited odds source exists (PRD allows omit-and-note).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_t2_registry.py -v && uv run mypy`
Expected: PASS (>=3 tables, unique ids, all sums ~1.0, a bricked/salvage outcome present), mypy clean.

- [ ] **Step 6: Commit**

```bash
git add oracle/scanner/t2_registry.py data/odds_t2/ tests/test_t2_registry.py
git commit -m "feat: odds registry with fail-loud validation (shape+prob-sum) and seed T2 tables"
```

---

### Task 3: EV engine (analytic EV / variance / stddev; None-price handling; liquidity/confidence)

**Files:**
- Create: `oracle/scanner/ev.py`, `tests/test_ev.py`

**Interfaces:**
- Consumes: `PriceResolver.resolve_auto(ref, league) -> ResolvedPrice`, `.resolve_verify(...)`, `.clear_cache()`; `OddsTable`, `Outcome`, `EvRow`, `OutcomeEv`, `PriceRef`.
- Produces:
  - `EvEngine(resolver, clock: Callable[[], datetime] = ...)` with:
    - `.evaluate(table: OddsTable, league: str, bankroll: float | None = None) -> EvRow` — resolve the input `PriceRef` and each outcome's `result` `PriceRef` (auto by default; `resolve_verify` when a ref carries `influence`/`ilvl`, matching Phase 1 verify semantics), then compute:
      - `input_cost = resolved_input.chaos_value or 0.0` (input unresolved is flagged via `unresolved_outcomes` count contribution and source).
      - For each outcome: `price = resolved.chaos_value`; if `None`, exclude from EV, mark `OutcomeEv.price=None, contribution=0.0`, and increment `unresolved_outcomes`. Never treat `None` as `0` silently.
      - `ev_gross = Σ p·price` over resolved outcomes only.
      - `ev_net = ev_gross − input_cost − service_cost`.
      - `variance = Σ p·(price − ev_gross)²` over resolved outcomes; `stddev = sqrt(variance)`.
      - `liquidity` / `confidence` = `min` across all resolved sides (input + resolved outcomes); a confidence penalty (`× (resolved / total_outcomes)`) is applied when any outcome is unresolved, so surfacing beats guessing.
      - `bankroll_note`: filled by `bankroll` module (Task 5); in this task pass `""` (Task 5 wires the note in via `EvEngine`'s use of `bankroll.note(...)`). To keep Task 3 self-contained, set `bankroll_note=""` here and populate it in Task 5.
    - `.evaluate_all(tables: list[OddsTable], league: str) -> list[EvRow]` — `clear_cache()` once, then evaluate each; returns rows sorted by `ev_net` descending.

**Notes:** A frozen helper `_resolve_ref(ref, league)` picks `resolve_verify` when `ref.influence is not None or ref.ilvl is not None`, else `resolve_auto` — identical to how Phase 1 distinguishes sides, so bricked-salvage refs (plain `Currency`) resolve auto. `attempt_cost = input_cost + service_cost` is exposed as a method for Task 5's bankroll math.

- [ ] **Step 1: Write the failing test**

`tests/test_ev.py`:
```python
import math
from datetime import UTC, datetime

from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable, Outcome
from oracle.scanner.ev import EvEngine


class StubResolver:
    """Maps (category, key) -> ResolvedPrice; missing key -> None price."""

    def __init__(self, table: dict[tuple[str, str], ResolvedPrice]) -> None:
        self._t = table
        self.cleared = 0

    def clear_cache(self) -> None:
        self.cleared += 1

    def _lookup(self, ref: PriceRef) -> ResolvedPrice:
        return self._t.get(
            (ref.category, ref.key),
            ResolvedPrice(None, 0.0, 0.0, f"missing:{ref.category}/{ref.key}", None),
        )

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)


def _p(value, liq=50.0, conf=0.8):  # type: ignore[no-untyped-def]
    return ResolvedPrice(value, liq, conf, "ninja:x", None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _table(service_cost: float = 0.0) -> OddsTable:
    return OddsTable(
        id="t", name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        service_cost=service_cost,
        outcomes=[
            Outcome(result=PriceRef(category="U", key="Jackpot"), probability=0.5),
            Outcome(result=PriceRef(category="U", key="Brick"), probability=0.5,
                    notes="bricked salvage"),
        ],
        source="s", prob_sum_tolerance=1e-6,
    )


def test_ev_gross_and_net_hand_computed() -> None:
    # 0.5*200 + 0.5*0  wait -> use 0.5*200 + 0.5*20 = 110 gross
    table = _table(service_cost=5.0)
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "Jackpot"): _p(200.0),
        ("U", "Brick"): _p(20.0),
    })
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.ev_gross == 110.0            # 0.5*200 + 0.5*20
    assert row.input_cost == 3.0
    assert row.service_cost == 5.0
    assert row.ev_net == 110.0 - 3.0 - 5.0  # 102.0


def test_variance_and_stddev_hand_computed() -> None:
    table = _table()
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "Jackpot"): _p(200.0),
        ("U", "Brick"): _p(20.0),
    })
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    # ev_gross = 110; var = 0.5*(200-110)^2 + 0.5*(20-110)^2 = 8100
    assert row.variance == 8100.0
    assert abs(row.stddev - math.sqrt(8100.0)) < 1e-9


def test_none_outcome_price_excluded_not_zero() -> None:
    table = _table()
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "Jackpot"): _p(200.0),
        # "Brick" missing -> None price
    })
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.unresolved_outcomes == 1
    # None excluded (not treated as 0): ev_gross = 0.5*200 = 100, NOT 100+0.
    assert row.ev_gross == 100.0
    brick = next(o for o in row.per_outcome if o.result_key == "Brick")
    assert brick.price is None
    assert brick.contribution == 0.0
    # confidence penalized because 1/2 outcomes unresolved
    assert row.confidence < 0.8


def test_liquidity_confidence_min_across_resolved_sides() -> None:
    table = _table()
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0, liq=100.0, conf=0.9),
        ("U", "Jackpot"): _p(200.0, liq=30.0, conf=0.7),
        ("U", "Brick"): _p(20.0, liq=80.0, conf=0.6),
    })
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.liquidity == 30.0           # min across sides
    assert abs(row.confidence - 0.6) < 1e-9  # min, all outcomes resolved -> no penalty


def test_evaluate_all_clears_cache_once_and_sorts_by_ev_net() -> None:
    lo = OddsTable(id="lo", name="lo", input=PriceRef(category="Currency", key="Vaal Orb"),
                   outcomes=[Outcome(result=PriceRef(category="U", key="A"), probability=1.0)],
                   source="s", prob_sum_tolerance=1e-6)
    hi = OddsTable(id="hi", name="hi", input=PriceRef(category="Currency", key="Vaal Orb"),
                   outcomes=[Outcome(result=PriceRef(category="U", key="B"), probability=1.0)],
                   source="s", prob_sum_tolerance=1e-6)
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "A"): _p(10.0),
        ("U", "B"): _p(500.0),
    })
    rows = EvEngine(resolver, clock=_clock).evaluate_all([lo, hi], "TestLeagueA")
    assert resolver.cleared == 1
    assert [r.table_id for r in rows] == ["hi", "lo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ev.py -v`
Expected: FAIL (no module `oracle.scanner.ev`).

- [ ] **Step 3: Implement the engine**

`oracle/scanner/ev.py`:
```python
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import EvRow, OddsTable, OutcomeEv


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class EvEngine:
    def __init__(
        self,
        resolver: _Resolver,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._resolver = resolver
        self._clock = clock

    def _resolve_ref(self, ref: PriceRef, league: str) -> ResolvedPrice:
        if ref.influence is not None or ref.ilvl is not None:
            return self._resolver.resolve_verify(ref, league)
        return self._resolver.resolve_auto(ref, league)

    def evaluate(
        self, table: OddsTable, league: str, bankroll: float | None = None
    ) -> EvRow:
        resolved_input = self._resolve_ref(table.input, league)
        input_cost = resolved_input.chaos_value or 0.0

        per_outcome: list[OutcomeEv] = []
        resolved_prices: list[tuple[float, float]] = []  # (probability, price)
        liq_candidates: list[float] = []
        conf_candidates: list[float] = []
        if resolved_input.chaos_value is not None:
            liq_candidates.append(resolved_input.liquidity)
            conf_candidates.append(resolved_input.confidence)

        unresolved = 0
        deep_link = resolved_input.deep_link
        for outcome in table.outcomes:
            res = self._resolve_ref(outcome.result, league)
            if res.chaos_value is None:
                unresolved += 1
                per_outcome.append(
                    OutcomeEv(
                        result_key=outcome.result.key,
                        probability=outcome.probability,
                        price=None,
                        contribution=0.0,
                        notes=outcome.notes,
                    )
                )
                if res.deep_link is not None and deep_link is None:
                    deep_link = res.deep_link
                continue
            resolved_prices.append((outcome.probability, res.chaos_value))
            liq_candidates.append(res.liquidity)
            conf_candidates.append(res.confidence)
            per_outcome.append(
                OutcomeEv(
                    result_key=outcome.result.key,
                    probability=outcome.probability,
                    price=res.chaos_value,
                    contribution=outcome.probability * res.chaos_value,
                    notes=outcome.notes,
                )
            )

        ev_gross = sum(p * v for p, v in resolved_prices)
        ev_net = ev_gross - input_cost - table.service_cost
        variance = sum(p * (v - ev_gross) ** 2 for p, v in resolved_prices)
        stddev = math.sqrt(variance)

        liquidity = min(liq_candidates, default=0.0)
        confidence = min(conf_candidates, default=0.0)
        total = len(table.outcomes)
        if total > 0 and unresolved > 0:
            confidence *= (total - unresolved) / total

        return EvRow(
            table_id=table.id,
            name=table.name,
            ev_gross=ev_gross,
            ev_net=ev_net,
            input_cost=input_cost,
            service_cost=table.service_cost,
            variance=variance,
            stddev=stddev,
            per_outcome=per_outcome,
            liquidity=liquidity,
            confidence=confidence,
            bankroll_note="",
            source=resolved_input.source,
            deep_link=deep_link,
            unresolved_outcomes=unresolved,
            ts=self._clock(),
        )

    def evaluate_all(self, tables: list[OddsTable], league: str) -> list[EvRow]:
        self._resolver.clear_cache()
        rows = [self.evaluate(t, league) for t in tables]
        rows.sort(key=lambda r: -r.ev_net)
        return rows
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_ev.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/ev.py tests/test_ev.py
git commit -m "feat: analytic EV engine (ev/variance/stddev; None-price surfaced, never fabricated)"
```

---

### Task 4: Bankroll math (affordable attempts, P(net loss after N), analytic-EV property test)

**Files:**
- Create: `oracle/scanner/bankroll.py`, `tests/test_bankroll.py`

**Interfaces:**
- Consumes: `oracle.scanner.t2_models.OddsTable`, `Outcome`, `EvRow`; per-outcome distribution as `list[tuple[float, float]]` (probability, net-profit-per-attempt).
- Produces:
  - `attempts_affordable(bankroll: float, attempt_cost: float) -> int` — `floor(B / attempt_cost)` when `attempt_cost > 0` else `0`.
  - `net_profit_distribution(outcomes: list[tuple[float, float]], attempt_cost: float) -> list[tuple[float, float]]` — maps each `(p, gross_value)` to `(p, gross_value − attempt_cost)` (per-attempt net profit).
  - `prob_single_attempt_loss(dist: list[tuple[float, float]]) -> float` — `Σ p where net < 0`.
  - `prob_net_loss_after(dist: list[tuple[float, float]], n: int) -> float` — probability the *summed* net profit over `n` i.i.d. attempts is `< 0`, computed by exact distribution convolution (small outcome sets; deterministic, no sampling).
  - `analytic_ev(dist: list[tuple[float, float]]) -> float` — `Σ p·net`.
  - `bankroll_note(ev_row_like, bankroll: float | None) -> str` — human-readable note: attempts affordable + single-attempt loss prob (empty string when `bankroll is None`). Consumed by the EV engine wiring (this task adds a `bankroll` param path).

**Notes:** `prob_net_loss_after` convolves the discrete per-attempt net-profit distribution `n` times. Values are floats; bucket by rounding to a small epsilon grid to keep the convolution finite and deterministic. For `n` up to a few hundred with ≤~6 outcomes this is fast enough (PRD Phase-2 scale; numpy deferred). Property test uses hypothesis to assert `analytic_ev == Σ p·v` exactly (within float tolerance).

- [ ] **Step 1: Write the failing test**

`tests/test_bankroll.py`:
```python
import math

from hypothesis import given, strategies as st

from oracle.scanner.bankroll import (
    analytic_ev,
    attempts_affordable,
    net_profit_distribution,
    prob_net_loss_after,
    prob_single_attempt_loss,
)


def test_attempts_affordable_floor() -> None:
    assert attempts_affordable(100.0, 7.0) == 14
    assert attempts_affordable(100.0, 0.0) == 0
    assert attempts_affordable(0.0, 5.0) == 0


def test_net_profit_distribution_subtracts_attempt_cost() -> None:
    dist = net_profit_distribution([(0.5, 200.0), (0.5, 0.0)], attempt_cost=10.0)
    assert dist == [(0.5, 190.0), (0.5, -10.0)]


def test_prob_single_attempt_loss() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert prob_single_attempt_loss(dist) == 0.5


def test_analytic_ev_hand() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert analytic_ev(dist) == 90.0


def test_prob_net_loss_after_one_attempt_matches_single() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert abs(prob_net_loss_after(dist, 1) - 0.5) < 1e-9


def test_prob_net_loss_after_shrinks_for_positive_ev() -> None:
    # Positive-EV bet: loss probability over many attempts should fall.
    dist = [(0.5, 190.0), (0.5, -10.0)]
    p1 = prob_net_loss_after(dist, 1)
    p5 = prob_net_loss_after(dist, 5)
    assert p5 <= p1


def test_prob_net_loss_certain_when_all_negative() -> None:
    dist = [(1.0, -10.0)]
    assert abs(prob_net_loss_after(dist, 3) - 1.0) < 1e-9


@given(
    st.lists(
        st.tuples(st.floats(0.01, 1.0), st.floats(-1000.0, 1000.0)),
        min_size=1, max_size=6,
    )
)
def test_analytic_ev_equals_sum_p_v(pairs: list[tuple[float, float]]) -> None:
    total_p = sum(p for p, _ in pairs)
    norm = [(p / total_p, v) for p, v in pairs]  # normalize to a valid distribution
    expected = sum(p * v for p, v in norm)
    assert math.isclose(analytic_ev(norm), expected, rel_tol=1e-9, abs_tol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bankroll.py -v`
Expected: FAIL (no module `oracle.scanner.bankroll`).

- [ ] **Step 3: Implement bankroll math**

`oracle/scanner/bankroll.py`:
```python
import math
from collections import defaultdict

_EPS = 1e-6


def attempts_affordable(bankroll: float, attempt_cost: float) -> int:
    if attempt_cost <= 0.0:
        return 0
    return math.floor(bankroll / attempt_cost)


def net_profit_distribution(
    outcomes: list[tuple[float, float]], attempt_cost: float
) -> list[tuple[float, float]]:
    return [(p, gross - attempt_cost) for p, gross in outcomes]


def prob_single_attempt_loss(dist: list[tuple[float, float]]) -> float:
    return sum(p for p, net in dist if net < 0.0)


def analytic_ev(dist: list[tuple[float, float]]) -> float:
    return sum(p * net for p, net in dist)


def _round_key(value: float) -> float:
    return round(value / _EPS) * _EPS


def prob_net_loss_after(dist: list[tuple[float, float]], n: int) -> float:
    if n <= 0:
        return 0.0
    # Exact convolution of the discrete per-attempt net-profit distribution.
    current: dict[float, float] = {0.0: 1.0}
    for _ in range(n):
        nxt: dict[float, float] = defaultdict(float)
        for total, ptot in current.items():
            for p, net in dist:
                nxt[_round_key(total + net)] += ptot * p
        current = dict(nxt)
    return sum(prob for total, prob in current.items() if total < 0.0)


def bankroll_note(
    attempt_cost: float,
    single_loss_prob: float,
    bankroll: float | None,
) -> str:
    if bankroll is None:
        return ""
    n = attempts_affordable(bankroll, attempt_cost)
    return (
        f"bankroll {bankroll:.0f}c affords {n} attempts at {attempt_cost:.2f}c each; "
        f"P(loss per attempt)={single_loss_prob:.2f}"
    )
```

- [ ] **Step 4: Wire the bankroll note into the EV engine**

Modify `oracle/scanner/ev.py` — import bankroll and populate `bankroll_note` when `bankroll` is given. Add the import at the top:
```python
from oracle.scanner import bankroll as bankroll_math
```
Replace the `bankroll_note=""` line in the `EvRow(...)` return with a computed note. Just before the `return EvRow(...)`, add:
```python
        attempt_cost = input_cost + table.service_cost
        outcome_pairs = [(p, v) for p, v in resolved_prices]
        net_dist = bankroll_math.net_profit_distribution(outcome_pairs, attempt_cost)
        single_loss = bankroll_math.prob_single_attempt_loss(net_dist)
        note = bankroll_math.bankroll_note(attempt_cost, single_loss, bankroll)
```
and change `bankroll_note=""` to `bankroll_note=note`.

Add a regression test to `tests/test_ev.py`:
```python
def test_evaluate_fills_bankroll_note_when_bankroll_given() -> None:
    table = _table(service_cost=2.0)
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "Jackpot"): _p(200.0),
        ("U", "Brick"): _p(20.0),
    })
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA", bankroll=100.0)
    assert "affords" in row.bankroll_note
    row_none = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row_none.bankroll_note == ""
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_bankroll.py tests/test_ev.py -v && uv run mypy`
Expected: PASS (incl. the hypothesis property test), mypy clean.

- [ ] **Step 6: Commit**

```bash
git add oracle/scanner/bankroll.py oracle/scanner/ev.py tests/test_bankroll.py tests/test_ev.py
git commit -m "feat: bankroll math (affordable attempts, P(net loss after N)) + EV bankroll note; hypothesis EV property test"
```

---

### Task 5: Factory mode / Monte Carlo (deterministic seeded sampling → P10/P50/P90)

**Files:**
- Create: `oracle/scanner/factory.py`, `tests/test_factory.py`

**Interfaces:**
- Consumes: `oracle.scanner.t2_models.OddsTable`, `EvRow`; `EvEngine.evaluate`; `PriceResolver`; `random.Random`.
- Produces:
  - `FactoryPlan(table_id: str, name: str, attempts: int, input_unit_cost: float, service_cost: float, total_input_spend: float, expected_total_profit: float, p10: float, p50: float, p90: float, trials: int, seed: int, unresolved_outcomes: int, bankroll: float | None, attempts_affordable: int | None)` (Pydantic model).
  - `FactoryEngine(ev_engine, resolver, clock)` with:
    - `.plan(table: OddsTable, league: str, attempts: int, rng: random.Random, trials: int, bankroll: float | None = None) -> FactoryPlan` — evaluates the table once (for prices/EV), builds the resolved outcome distribution `[(cum_prob, net_profit)]`, then runs `trials` Monte-Carlo simulations: each trial sums `attempts` sampled per-attempt net profits using `rng`; the resulting `trials` totals give `expected_total_profit` (mean), P10/P50/P90 (percentiles). Deterministic given `rng` (injected `random.Random(seed)`). `total_input_spend = attempts * (input_unit_cost + service_cost)`.

**Notes:** Sampling uses `rng.random()` against the cumulative distribution built from *resolved* outcomes only (unresolved outcomes are excluded and surfaced via `unresolved_outcomes`, matching Task 3 — never sampled as 0). If ALL outcomes are unresolved, the distribution is empty and the plan reports zero profit with `unresolved_outcomes == len(outcomes)` (fail-visible, not fail-silent). Percentiles via `statistics.quantiles` or manual `sorted()` indexing. `seed` is recorded on the plan so a run is reproducible; two calls with `random.Random(same_seed)` produce identical plans (the determinism test).

- [ ] **Step 1: Write the failing test**

`tests/test_factory.py`:
```python
import random
from datetime import UTC, datetime

from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable, Outcome


class StubResolver:
    def __init__(self, table: dict[tuple[str, str], ResolvedPrice]) -> None:
        self._t = table

    def clear_cache(self) -> None:
        pass

    def _lookup(self, ref: PriceRef) -> ResolvedPrice:
        return self._t.get(
            (ref.category, ref.key),
            ResolvedPrice(None, 0.0, 0.0, "missing", None),
        )

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)


def _p(value):  # type: ignore[no-untyped-def]
    return ResolvedPrice(value, 50.0, 0.8, "ninja:x", None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _table() -> OddsTable:
    return OddsTable(
        id="t", name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        service_cost=2.0,
        outcomes=[
            Outcome(result=PriceRef(category="U", key="Jackpot"), probability=0.5),
            Outcome(result=PriceRef(category="U", key="Brick"), probability=0.5),
        ],
        source="s", prob_sum_tolerance=1e-6,
    )


def _engine() -> tuple[FactoryEngine, StubResolver]:
    resolver = StubResolver({
        ("Currency", "Vaal Orb"): _p(3.0),
        ("U", "Jackpot"): _p(200.0),
        ("U", "Brick"): _p(20.0),
    })
    ev = EvEngine(resolver, clock=_clock)
    return FactoryEngine(ev, resolver, clock=_clock), resolver


def test_plan_is_deterministic_given_seed() -> None:
    eng, _ = _engine()
    p1 = eng.plan(_table(), "TestLeagueA", attempts=100,
                  rng=random.Random(42), trials=2000)
    eng2, _ = _engine()
    p2 = eng2.plan(_table(), "TestLeagueA", attempts=100,
                   rng=random.Random(42), trials=2000)
    assert p1.p10 == p2.p10
    assert p1.p50 == p2.p50
    assert p1.p90 == p2.p90
    assert p1.expected_total_profit == p2.expected_total_profit


def test_percentiles_ordered_and_sane() -> None:
    eng, _ = _engine()
    plan = eng.plan(_table(), "TestLeagueA", attempts=100,
                    rng=random.Random(7), trials=5000)
    assert plan.p10 <= plan.p50 <= plan.p90
    # per-attempt net EV = 0.5*(200-5) + 0.5*(20-5) = 105; *100 attempts ≈ 10500
    assert 9000.0 < plan.expected_total_profit < 12000.0
    assert plan.total_input_spend == 100 * (3.0 + 2.0)


def test_plan_records_seed_and_trials_and_bankroll() -> None:
    eng, _ = _engine()
    plan = eng.plan(_table(), "TestLeagueA", attempts=10,
                    rng=random.Random(99), trials=1000, bankroll=500.0)
    assert plan.trials == 1000
    assert plan.attempts == 10
    assert plan.bankroll == 500.0
    assert plan.attempts_affordable == 100  # 500 / (3+2)


def test_all_unresolved_outcomes_is_fail_visible() -> None:
    resolver = StubResolver({("Currency", "Vaal Orb"): _p(3.0)})  # outcomes missing
    eng = FactoryEngine(EvEngine(resolver, clock=_clock), resolver, clock=_clock)
    plan = eng.plan(_table(), "TestLeagueA", attempts=10,
                    rng=random.Random(1), trials=100)
    assert plan.unresolved_outcomes == 2
    assert plan.expected_total_profit == -plan.total_input_spend or \
        plan.expected_total_profit == 0.0  # no resolvable upside; loss surfaced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_factory.py -v`
Expected: FAIL (no module `oracle.scanner.factory`).

- [ ] **Step 3: Implement the factory engine**

`oracle/scanner/factory.py`:
```python
import random
import statistics
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from oracle.scanner import bankroll as bankroll_math
from oracle.scanner.ev import EvEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class FactoryPlan(BaseModel):
    table_id: str
    name: str
    attempts: int
    input_unit_cost: float
    service_cost: float
    total_input_spend: float
    expected_total_profit: float
    p10: float
    p50: float
    p90: float
    trials: int
    seed: int | None
    unresolved_outcomes: int
    bankroll: float | None
    attempts_affordable: int | None


class FactoryEngine:
    def __init__(
        self,
        ev_engine: EvEngine,
        resolver: _Resolver,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._ev = ev_engine
        self._resolver = resolver
        self._clock = clock

    def plan(
        self,
        table: OddsTable,
        league: str,
        attempts: int,
        rng: random.Random,
        trials: int,
        bankroll: float | None = None,
    ) -> FactoryPlan:
        row = self._ev.evaluate(table, league, bankroll)
        attempt_cost = row.input_cost + table.service_cost
        total_input_spend = attempts * attempt_cost

        # Resolved per-attempt net-profit outcomes (unresolved excluded, surfaced).
        resolved = [(o.probability, o.price) for o in row.per_outcome if o.price is not None]
        net = [(p, price - attempt_cost) for p, price in resolved]

        # Build cumulative distribution for sampling.
        cum: list[tuple[float, float]] = []
        acc = 0.0
        norm = sum(p for p, _ in net)
        if norm > 0.0:
            for p, value in net:
                acc += p / norm
                cum.append((acc, value))

        totals: list[float] = []
        if cum:
            for _ in range(trials):
                trial_total = 0.0
                for _ in range(attempts):
                    r = rng.random()
                    for threshold, value in cum:
                        if r <= threshold:
                            trial_total += value
                            break
                    else:
                        trial_total += cum[-1][1]
                totals.append(trial_total)
        else:
            # No resolvable outcomes: the whole spend is a surfaced loss.
            totals = [-total_input_spend] * trials

        totals_sorted = sorted(totals)
        expected = statistics.fmean(totals_sorted)

        def _pct(fraction: float) -> float:
            idx = min(len(totals_sorted) - 1, int(fraction * len(totals_sorted)))
            return totals_sorted[idx]

        affordable = (
            bankroll_math.attempts_affordable(bankroll, attempt_cost)
            if bankroll is not None
            else None
        )
        return FactoryPlan(
            table_id=table.id,
            name=table.name,
            attempts=attempts,
            input_unit_cost=row.input_cost,
            service_cost=table.service_cost,
            total_input_spend=total_input_spend,
            expected_total_profit=expected,
            p10=_pct(0.10),
            p50=_pct(0.50),
            p90=_pct(0.90),
            trials=trials,
            seed=None,
            unresolved_outcomes=row.unresolved_outcomes,
            bankroll=bankroll,
            attempts_affordable=affordable,
        )
```

**Note on `seed`:** `random.Random` does not expose its seed, so `FactoryPlan.seed` is set by the CLI (Task 7) which owns the seed value; the engine takes an already-seeded `rng` for testability and sets `seed=None`. The CLI passes the seed through and overrides `plan.seed` for reporting. Adjust `test_plan_records_seed_and_trials_and_bankroll` to NOT assert on `plan.seed` (it asserts `trials`, `attempts`, `bankroll`, `attempts_affordable` only — as written above).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_factory.py -v && uv run mypy`
Expected: PASS (determinism holds, percentiles ordered, EV in range), mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/factory.py tests/test_factory.py
git commit -m "feat: deterministic seeded Monte-Carlo factory planner (P10/P50/P90, expected total profit)"
```

---

### Task 6: EV-results persistence + report T2 section (separate PROBABILISTIC block)

**Files:**
- Create: `oracle/store/ev_results.py`, `tests/test_store_ev.py`, `tests/test_t2_report.py`
- Modify: `oracle/store/db.py` (append `ev_results` migration), `oracle/scanner/report.py` (extend `ScanReport` to carry + render `EvRow`s)

**Interfaces:**
- Consumes: `connect`, `EvRow`, `ScanRow`.
- Produces:
  - New migration DDL appended to `MIGRATIONS` creating append-only `ev_results` (id, league, ts, rule_version, table_id, name, ev_gross, ev_net, input_cost, service_cost, variance, stddev, liquidity, confidence, unresolved_outcomes, bankroll_note, source, deep_link) + index on `(league, ts)`.
  - `EvResultRepo(conn)` with `.insert_many(league: str, rule_version: str, rows: list[EvRow]) -> None` and `.recent(league: str, limit: int = 100) -> list[dict[str, object]]`.
  - `ScanReport` gains a field `ev_rows: list[EvRow] = field(default_factory=list)` and:
    - `.to_terminal()` appends a `== PROBABILISTIC (Tier-2) ==` section (EV net, per-attempt stddev, bankroll note) AFTER the deterministic sections.
    - `.to_markdown()` appends a `## PROBABILISTIC (Tier-2)` section with an EV table (EV gross/net, stddev, liquidity, confidence, bankroll note) and, when present, deep-links for verify-priced tables.
    - `.to_json()` includes an `ev_rows` key.

**Notes:** `ScanReport` is a frozen dataclass; add `ev_rows` as a defaulted field so existing Phase 1 construction (`rows=...` only) is unchanged. The T2 section is clearly separate from the deterministic AUTO-PRICED / VERIFY-REQUIRED sections (DoD: "report cleanly separates deterministic and probabilistic opportunities").

- [ ] **Step 1: Write the failing tests**

`tests/test_store_ev.py`:
```python
from datetime import UTC, datetime

from oracle.scanner.t2_models import EvRow
from oracle.store.db import connect
from oracle.store.ev_results import EvResultRepo


def _row(tid: str, ev_net: float) -> EvRow:
    return EvRow(table_id=tid, name=tid, ev_gross=ev_net + 10.0, ev_net=ev_net,
                 input_cost=3.0, service_cost=2.0, variance=100.0, stddev=10.0,
                 per_outcome=[], liquidity=40.0, confidence=0.8,
                 bankroll_note="", source="ninja:x", deep_link=None,
                 unresolved_outcomes=0, ts=datetime.now(tz=UTC))


def test_ev_results_table_exists(tmp_path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {r["name"] for r in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ev_results" in tables


def test_insert_and_recent_round_trip(tmp_path) -> None:
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("TestLeagueA", "sha256:abc", [_row("a", 90.0), _row("b", 5.0)])
    recent = repo.recent("TestLeagueA")
    assert len(recent) == 2
    assert {r["table_id"] for r in recent} == {"a", "b"}
    assert all(r["rule_version"] == "sha256:abc" for r in recent)


def test_append_only_accumulates(tmp_path) -> None:
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("TestLeagueA", "v1", [_row("a", 90.0)])
    repo.insert_many("TestLeagueA", "v2", [_row("a", 85.0)])
    assert len(repo.recent("TestLeagueA")) == 2
```

`tests/test_t2_report.py`:
```python
import json
from datetime import UTC, datetime

from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport
from oracle.scanner.t2_models import EvRow, OutcomeEv


def _auto(tid: str, margin: float) -> ScanRow:
    return ScanRow(transform_id=tid, name=f"name-{tid}", input_cost=10.0,
                   output_value=10.0 + margin, margin=margin, margin_pct=margin / 10.0,
                   liquidity=50.0, confidence=0.8, pricing_mode="auto", deep_link=None,
                   source="ninja:x", ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC))


def _ev(tid: str, ev_net: float) -> EvRow:
    return EvRow(table_id=tid, name=f"gamble-{tid}", ev_gross=ev_net + 5.0,
                 ev_net=ev_net, input_cost=3.0, service_cost=2.0, variance=100.0,
                 stddev=10.0,
                 per_outcome=[OutcomeEv(result_key="A", probability=1.0, price=100.0,
                                        contribution=100.0, notes="")],
                 liquidity=40.0, confidence=0.7,
                 bankroll_note="bankroll 100c affords 20 attempts",
                 source="ninja:x", deep_link=None, unresolved_outcomes=0,
                 ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC))


def _report() -> ScanReport:
    return ScanReport(league="TestLeagueA",
                      snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
                      rule_version="sha256:abc",
                      rows=[_auto("big", 30.0)],
                      ev_rows=[_ev("vaal", 90.0)])


def test_terminal_has_separate_probabilistic_section() -> None:
    text = _report().to_terminal()
    assert "AUTO-PRICED" in text
    assert "PROBABILISTIC (Tier-2)" in text
    # deterministic section appears before probabilistic section
    assert text.index("AUTO-PRICED") < text.index("PROBABILISTIC")
    assert "gamble-vaal" in text
    assert "affords 20 attempts" in text


def test_markdown_has_probabilistic_table() -> None:
    md = _report().to_markdown()
    assert "## PROBABILISTIC (Tier-2)" in md
    assert "gamble-vaal" in md
    assert "90.00" in md  # ev_net


def test_json_includes_ev_rows() -> None:
    payload = json.loads(_report().to_json())
    assert len(payload["ev_rows"]) == 1
    assert payload["ev_rows"][0]["table_id"] == "vaal"


def test_default_ev_rows_empty_keeps_phase1_construction() -> None:
    r = ScanReport(league="TestLeagueA",
                   snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
                   rule_version="v", rows=[_auto("x", 20.0)])
    assert r.ev_rows == []
    assert "PROBABILISTIC" in r.to_terminal()  # section header present even if empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_store_ev.py tests/test_t2_report.py -v`
Expected: FAIL (no `ev_results` table / module; `ScanReport` has no `ev_rows` / T2 section).

- [ ] **Step 3: Add migration + repo**

Append to `MIGRATIONS` in `oracle/store/db.py` (two entries at the end of the list):
```python
    """
    CREATE TABLE IF NOT EXISTS ev_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        ts TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        table_id TEXT NOT NULL,
        name TEXT NOT NULL,
        ev_gross REAL NOT NULL,
        ev_net REAL NOT NULL,
        input_cost REAL NOT NULL,
        service_cost REAL NOT NULL,
        variance REAL NOT NULL,
        stddev REAL NOT NULL,
        liquidity REAL NOT NULL,
        confidence REAL NOT NULL,
        unresolved_outcomes INTEGER NOT NULL,
        bankroll_note TEXT NOT NULL,
        source TEXT NOT NULL,
        deep_link TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_ev_league_ts
        ON ev_results (league, ts)
    """,
```

`oracle/store/ev_results.py`:
```python
import sqlite3

from oracle.scanner.t2_models import EvRow


class EvResultRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, league: str, rule_version: str, rows: list[EvRow]) -> None:
        self._conn.executemany(
            "INSERT INTO ev_results "
            "(league, ts, rule_version, table_id, name, ev_gross, ev_net, input_cost, "
            "service_cost, variance, stddev, liquidity, confidence, unresolved_outcomes, "
            "bankroll_note, source, deep_link) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    league,
                    r.ts.isoformat(),
                    rule_version,
                    r.table_id,
                    r.name,
                    r.ev_gross,
                    r.ev_net,
                    r.input_cost,
                    r.service_cost,
                    r.variance,
                    r.stddev,
                    r.liquidity,
                    r.confidence,
                    r.unresolved_outcomes,
                    r.bankroll_note,
                    r.source,
                    r.deep_link,
                )
                for r in rows
            ],
        )
        self._conn.commit()

    def recent(self, league: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT * FROM ev_results WHERE league=? ORDER BY ts DESC, id DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Extend `ScanReport`**

Modify `oracle/scanner/report.py`. Add imports and the `ev_rows` field, and render the T2 section.

At the top, add the field import and EvRow import:
```python
from dataclasses import dataclass, field
```
```python
from oracle.scanner.t2_models import EvRow
```
Add to the `ScanReport` dataclass body (after `rows: list[ScanRow]`):
```python
    ev_rows: list[EvRow] = field(default_factory=list)
```
In `to_terminal`, before `return "\n".join(lines)`, append:
```python
        lines.append("")
        lines.append("== PROBABILISTIC (Tier-2) ==")
        lines.append(f"{'gamble':<32}{'ev_net':>10}{'stddev':>10}{'conf':>7}")
        for e in self.ev_rows:
            lines.append(
                f"{e.name[:32]:<32}{e.ev_net:>10.2f}{e.stddev:>10.2f}{e.confidence:>7.2f}"
            )
            if e.bankroll_note:
                lines.append(f"    {e.bankroll_note}")
            if e.unresolved_outcomes:
                lines.append(f"    ! {e.unresolved_outcomes} outcome(s) unpriced (excluded)")
```
In `to_markdown`, before `return "\n".join(lines) + "\n"`, append:
```python
        lines += [
            "",
            "## PROBABILISTIC (Tier-2)",
            "",
            "| Gamble | EV gross (c) | EV net (c) | Stddev | Liquidity | Confidence | Bankroll |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for e in self.ev_rows:
            lines.append(
                f"| {e.name} | {e.ev_gross:.2f} | {e.ev_net:.2f} | {e.stddev:.2f} | "
                f"{e.liquidity:.0f} | {e.confidence:.2f} | {e.bankroll_note or '—'} |"
            )
```
In `to_json`, add `"ev_rows"` to the payload dict:
```python
            "ev_rows": [json.loads(e.model_dump_json()) for e in self.ev_rows],
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_store_ev.py tests/test_t2_report.py tests/test_report.py tests/test_store_scans.py -v && uv run mypy`
Expected: PASS (existing Phase 1 report + store tests still green — `ev_rows` defaults to `[]`, migrations additive), mypy clean.

- [ ] **Step 6: Commit**

```bash
git add oracle/store/ev_results.py oracle/store/db.py oracle/scanner/report.py tests/test_store_ev.py tests/test_t2_report.py
git commit -m "feat: append-only ev_results persistence + separate PROBABILISTIC (Tier-2) report section"
```

---

### Task 7: T2 service wiring + `oracle scan` T2 integration + `oracle factory` CLI

**Files:**
- Create: `oracle/scanner/t2_service.py`, `tests/test_t2_service.py`, `tests/test_factory_cli.py`
- Modify: `oracle/scanner/service.py` (accept an optional `T2Service` and attach EV rows to the report), `oracle/app.py` (build the odds registry, `EvEngine`, `FactoryEngine`, `EvResultRepo`, `T2Service`; wire into `Services` and `ScanService`), `oracle/cli.py` (extend `scan` output already carries T2 via the report; add `factory` command)

**Interfaces:**
- Produces (`oracle/scanner/t2_service.py`):
  - `T2Service(ev_engine, factory_engine, registry, repo, rule_version, clock)` with:
    - `.evaluate(league: str, bankroll: float | None = None) -> list[EvRow]` — evaluate enabled tables via `ev_engine.evaluate_all`, persist via `repo.insert_many`, return rows.
    - `.factory(table_id: str, league: str, bankroll: float, attempts: int, seed: int, trials: int) -> FactoryPlan` — look up the enabled table by id (raise `KeyError` if unknown), run `factory_engine.plan` with `random.Random(seed)`, set `plan.seed = seed`, return it.
- Modifies `oracle/scanner/service.py`:
  - `ScanService.__init__` gains an optional `t2: T2Service | None = None` parameter (keyword, defaulted so Phase 1 tests are unchanged).
  - `.run(...)` — after building deterministic rows, if `t2` is set, call `t2.evaluate(league)` and pass the result as `ev_rows=` to the `ScanReport` constructor.
- Modifies `oracle/app.py`:
  - `Services` gains `t2: T2Service`.
  - `build_services` builds: `odds = load_odds_registry(DEFAULT_ODDS_DIR, settings.t2.prob_sum_tolerance)`; `ev_engine = EvEngine(scan_resolver)`; `factory_engine = FactoryEngine(ev_engine, scan_resolver)`; `t2 = T2Service(ev_engine, factory_engine, odds, EvResultRepo(conn), odds.version)`; pass `t2=t2` to `ScanService(...)` and to `Services(...)`.
- Modifies `oracle/cli.py`:
  - Add `factory(table_id: str, league: str = typer.Option(...), bankroll: float = typer.Option(...), attempts: int = typer.Option(...), seed: int = typer.Option(None), trials: int = typer.Option(None), as_json: bool = typer.Option(False, "--json"))` — resolves `seed`/`trials` from `settings.t2` defaults when omitted, calls `_services().t2.factory(...)`, prints the production plan.

**Notes:** The CLI needs the settings for `t2` defaults; reuse `_services()` which already builds them (`svc.settings.t2.mc_seed` / `.mc_trials`). `ScanService`'s new `t2` param keeps Phase 1 construction working (`ScanService(engine, repo, version, dir)` still valid).

- [ ] **Step 1: Write the failing tests**

`tests/test_t2_service.py`:
```python
from datetime import UTC, datetime
from pathlib import Path

from oracle.models import ListingQuote, Price
from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.t2_registry import load_odds_registry
from oracle.scanner.t2_service import T2Service
from oracle.store.db import connect
from oracle.store.ev_results import EvResultRepo

FIX = Path(__file__).parent / "fixtures"


class FixturePriceService:
    """Prices everything the golden fixture table references."""

    PRICES = {
        ("Currency", "Vaal Orb"): (3.0, 500),
        ("UniqueAccessory", "Golden Unique Jackpot"): (300.0, 20),
        ("UniqueAccessory", "Golden Unique NoChange"): (50.0, 30),
        ("Currency", "Vaal salvage scrap"): (1.0, 900),
    }

    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        return [
            Price(key=key, league=league, category=category, chaos_value=val,
                  sample_depth=depth, source=f"ninja:{category}", confidence=0.8, ts=now)
            for (cat, key), (val, depth) in self.PRICES.items()
            if cat == category
        ]


class NullDeepLink:
    def resolve(self, spec, league):  # type: ignore[no-untyped-def]
        return ListingQuote(spec_hash="h", league=league, chaos_value=None,
                            deep_link="https://www.pathofexile.com/trade/search/x?q=x",
                            residual_instructions=[], source="unresolved",
                            observed_ts=None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _service(tmp_path: Path) -> T2Service:
    reg = load_odds_registry(FIX / "odds_golden", 0.01)
    resolver = PriceResolver(FixturePriceService(), NullDeepLink(), min_sample_depth=5)
    ev = EvEngine(resolver, clock=_clock)
    fac = FactoryEngine(ev, resolver, clock=_clock)
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    return T2Service(ev, fac, reg, repo, reg.version, clock=_clock)


def test_evaluate_returns_and_persists(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    rows = svc.evaluate("TestLeagueA")
    assert rows
    row = next(r for r in rows if r.table_id == "golden_vaal")
    # ev_gross = 0.5*300 + 0.3*50 + 0.2*1 = 150 + 15 + 0.2 = 165.2
    assert abs(row.ev_gross - 165.2) < 1e-9


def test_factory_by_id_deterministic(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    plan = svc.factory("golden_vaal", "TestLeagueA", bankroll=100.0,
                       attempts=50, seed=7, trials=2000)
    assert plan.table_id == "golden_vaal"
    assert plan.seed == 7
    assert plan.p10 <= plan.p50 <= plan.p90
    svc2 = _service(tmp_path)
    plan2 = svc2.factory("golden_vaal", "TestLeagueA", bankroll=100.0,
                         attempts=50, seed=7, trials=2000)
    assert plan.p50 == plan2.p50


def test_factory_unknown_table_raises(tmp_path: Path) -> None:
    import pytest
    with pytest.raises(KeyError):
        _service(tmp_path).factory("nope", "TestLeagueA", bankroll=1.0,
                                   attempts=1, seed=1, trials=10)
```

`tests/fixtures/odds_golden/golden_vaal.yaml` (a golden table with prices pinned by `FixturePriceService` — DoD golden EV, hand calc documented in Task 8):
```yaml
# Golden fixture for the DoD EV hand-calc (prices pinned in test/notebook).
tables:
  - id: golden_vaal
    name: "Golden Vaal amulet (pinned-price EV fixture)"
    input: {category: Currency, key: "Vaal Orb", qty: 1.0}
    service_cost: 0.0
    source: "fixture: hand-calc EV; not a live odds source"
    patch_validity: "Fixture only — pinned prices, deterministic EV."
    outcomes:
      - result: {category: UniqueAccessory, key: "Golden Unique Jackpot"}
        probability: 0.5
        notes: "jackpot"
      - result: {category: UniqueAccessory, key: "Golden Unique NoChange"}
        probability: 0.3
        notes: "no change, resells"
      - result: {category: Currency, key: "Vaal salvage scrap"}
        probability: 0.2
        notes: "bricked salvage"
```

`tests/test_factory_cli.py`:
```python
from oracle.cli import app
from oracle.config import T2Settings
from oracle.scanner.factory import FactoryPlan
from typer.testing import CliRunner

runner = CliRunner()


class FakeT2:
    def factory(self, table_id, league, bankroll, attempts, seed, trials):  # type: ignore[no-untyped-def]
        return FactoryPlan(table_id=table_id, name="Fake Gamble", attempts=attempts,
                           input_unit_cost=3.0, service_cost=2.0,
                           total_input_spend=attempts * 5.0,
                           expected_total_profit=1000.0, p10=200.0, p50=900.0,
                           p90=1800.0, trials=trials, seed=seed,
                           unresolved_outcomes=0, bankroll=bankroll,
                           attempts_affordable=20)


class FakeSettings:
    t2 = T2Settings(prob_sum_tolerance=0.01, default_service_cost=0.0,
                    mc_trials=5000, mc_seed=1234)


class FakeServices:
    t2 = FakeT2()
    settings = FakeSettings()


def test_factory_command_prints_plan(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["factory", "golden_vaal", "--league", "TestLeagueA",
                                 "--bankroll", "100", "--attempts", "50"])
    assert result.exit_code == 0
    assert "Fake Gamble" in result.stdout
    assert "P10" in result.stdout and "P50" in result.stdout and "P90" in result.stdout
    assert "1000.0" in result.stdout  # expected total profit


def test_factory_command_json(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["factory", "golden_vaal", "--league", "TestLeagueA",
                                 "--bankroll", "100", "--attempts", "50", "--json"])
    assert result.exit_code == 0
    assert '"expected_total_profit"' in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_t2_service.py tests/test_factory_cli.py -v`
Expected: FAIL (no `T2Service`; no `factory` CLI command; `Services` has no `t2`).

- [ ] **Step 3: Implement the service, wire app + CLI**

`oracle/scanner/t2_service.py`:
```python
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine, FactoryPlan
from oracle.scanner.t2_models import EvRow
from oracle.scanner.t2_registry import OddsRegistry


class _EvRepo(Protocol):
    def insert_many(self, league: str, rule_version: str, rows: list[EvRow]) -> None: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class T2Service:
    def __init__(
        self,
        ev_engine: EvEngine,
        factory_engine: FactoryEngine,
        registry: OddsRegistry,
        repo: _EvRepo,
        rule_version: str,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._ev = ev_engine
        self._factory = factory_engine
        self._registry = registry
        self._repo = repo
        self._rule_version = rule_version
        self._clock = clock

    def evaluate(self, league: str, bankroll: float | None = None) -> list[EvRow]:
        rows = self._ev.evaluate_all(self._registry.enabled(), league)
        self._repo.insert_many(league, self._rule_version, rows)
        return rows

    def factory(
        self,
        table_id: str,
        league: str,
        bankroll: float,
        attempts: int,
        seed: int,
        trials: int,
    ) -> FactoryPlan:
        table = next((t for t in self._registry.enabled() if t.id == table_id), None)
        if table is None:
            raise KeyError(f"unknown or disabled odds table: {table_id}")
        plan = self._factory.plan(
            table, league, attempts, random.Random(seed), trials, bankroll
        )
        return plan.model_copy(update={"seed": seed})
```

Modify `oracle/scanner/service.py` — import `T2Service`, add the `t2` param and attach EV rows:
```python
from oracle.scanner.t2_service import T2Service
```
Change the `__init__` signature to add (keyword, defaulted):
```python
        t2: "T2Service | None" = None,
```
and store `self._t2 = t2`. In `run`, replace the `ScanReport(...)` construction so it includes EV rows:
```python
        ev_rows = self._t2.evaluate(league) if self._t2 is not None else []
        report = ScanReport(
            league=league,
            snapshot_ts=snapshot_ts,
            rule_version=self._rule_version,
            rows=rows,
            ev_rows=ev_rows,
        )
```

Modify `oracle/app.py`:
```python
from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.t2_registry import DEFAULT_ODDS_DIR, load_odds_registry
from oracle.scanner.t2_service import T2Service
from oracle.store.ev_results import EvResultRepo
```
Add to `class Services`:
```python
    t2: T2Service
```
In `build_services`, after `engine = ScanEngine(...)` and before `scan = ScanService(...)`:
```python
    odds = load_odds_registry(DEFAULT_ODDS_DIR, settings.t2.prob_sum_tolerance)
    ev_engine = EvEngine(scan_resolver)
    factory_engine = FactoryEngine(ev_engine, scan_resolver)
    t2 = T2Service(ev_engine, factory_engine, odds, EvResultRepo(conn), odds.version)
    scan = ScanService(engine, ScanResultRepo(conn), registry.version, Path("reports"), t2=t2)
```
and add `t2=t2` to the `Services(...)` return.

Add to `oracle/cli.py`:
```python
@app.command()
def factory(
    table_id: str,
    league: str = typer.Option(...),
    bankroll: float = typer.Option(...),
    attempts: int = typer.Option(...),
    seed: int | None = typer.Option(None),
    trials: int | None = typer.Option(None),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a Tier-2 production plan (buy N inputs; expected profit; P10/P50/P90)."""
    svc = _services()
    use_seed = svc.settings.t2.mc_seed if seed is None else seed
    use_trials = svc.settings.t2.mc_trials if trials is None else trials
    plan = svc.t2.factory(table_id, league, bankroll, attempts, use_seed, use_trials)
    if as_json:
        typer.echo(plan.model_dump_json(indent=2))
        return
    typer.echo(f"Factory plan: {plan.name} (league={league})")
    typer.echo(f"  Buy {plan.attempts} inputs; total input spend "
               f"{plan.total_input_spend:.2f}c")
    typer.echo(f"  Expected total profit: {plan.expected_total_profit:.1f}c "
               f"(trials={plan.trials}, seed={plan.seed})")
    typer.echo(f"  P10 {plan.p10:.1f}c   P50 {plan.p50:.1f}c   P90 {plan.p90:.1f}c")
    if plan.attempts_affordable is not None:
        typer.echo(f"  Bankroll {plan.bankroll:.0f}c affords "
                   f"{plan.attempts_affordable} attempts")
    if plan.unresolved_outcomes:
        typer.echo(f"  ! {plan.unresolved_outcomes} outcome(s) unpriced (excluded)")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_t2_service.py tests/test_factory_cli.py tests/test_scan_service.py tests/test_scan_cli.py tests/test_cli_commands.py -v && uv run mypy`
Expected: PASS (Phase 1 scan-service/CLI tests still green — `ScanService.t2` defaults to `None`; existing `Services` fakes only touch used fields), mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/t2_service.py oracle/app.py oracle/cli.py oracle/scanner/service.py tests/test_t2_service.py tests/test_factory_cli.py tests/fixtures/odds_golden/
git commit -m "feat: T2Service, oracle scan T2 integration, and 'oracle factory' CLI"
```

---

### Task 8: Golden EV test, compliance re-check, live T2 smoke, Phase 2 DoD verification

**Files:**
- Create: `tests/test_golden_ev.py`, `tests/test_t2_live_smoke.py`, `docs/phase2-dod.md`
- (Reuses the `tests/fixtures/odds_golden/` fixture from Task 7.)

**Interfaces:**
- Consumes: `EvEngine`, `PriceResolver` with a pinned-price stub; the full built services (real network, `@pytest.mark.live`); the existing `tests/test_compliance.py`.

**Notes:** The golden EV test is the PRD DoD gate: "Temple double-corrupt EV for popular uniques matches a hand calculation within tolerance, priced from live Standard ninja data" — reproduced here deterministically with PINNED prices (so the test is reproducible regardless of live state, mirroring the Phase 3 snapshot-pinning philosophy). `docs/phase2-dod.md` records the hand calc.

- [ ] **Step 1: Write the golden EV test (pinned prices, documented hand calc)**

`tests/test_golden_ev.py`:
```python
import math
from datetime import UTC, datetime

from oracle.models import ListingQuote, Price
from oracle.scanner.ev import EvEngine
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.t2_models import OddsTable, Outcome
from oracle.scanner.models import PriceRef


# --- Pinned prices for the golden temple double-corrupt hand calc. ---
# Hand calc (documented in docs/phase2-dod.md):
#   input Popular Unique copy = 40c ; service_cost = 20c
#   outcomes:
#     0.10  Jackpot      = 800c  -> 80.0
#     0.20  Good Corrupt = 150c  -> 30.0
#     0.35  No Change    =  40c  -> 14.0
#     0.35  Bricked scrap=   2c  ->  0.7
#   ev_gross = 80 + 30 + 14 + 0.7 = 124.7
#   ev_net   = 124.7 - 40 (input) - 20 (service) = 64.7
PINNED = {
    ("UniqueArmour", "Golden Popular Unique"): 40.0,
    ("UniqueArmour", "Golden Jackpot"): 800.0,
    ("UniqueArmour", "Golden Good Corrupt"): 150.0,
    ("Currency", "Golden scrap"): 2.0,
}


class PinnedPriceService:
    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        return [
            Price(key=key, league=league, category=category, chaos_value=val,
                  sample_depth=100, source=f"ninja:{category}", confidence=0.8, ts=now)
            for (cat, key), val in PINNED.items()
            if cat == category
        ]


class NullDeepLink:
    def resolve(self, spec, league):  # type: ignore[no-untyped-def]
        return ListingQuote(spec_hash="h", league=league, chaos_value=None,
                            deep_link="https://www.pathofexile.com/trade/search/x?q=x",
                            residual_instructions=[], source="unresolved",
                            observed_ts=None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _golden_table() -> OddsTable:
    return OddsTable(
        id="golden_temple",
        name="Golden temple double-corrupt (pinned hand-calc)",
        input=PriceRef(category="UniqueArmour", key="Golden Popular Unique"),
        service_cost=20.0,
        outcomes=[
            Outcome(result=PriceRef(category="UniqueArmour", key="Golden Jackpot"),
                    probability=0.10, notes="jackpot"),
            Outcome(result=PriceRef(category="UniqueArmour", key="Golden Good Corrupt"),
                    probability=0.20, notes="good"),
            Outcome(result=PriceRef(category="UniqueArmour", key="Golden Popular Unique"),
                    probability=0.35, notes="no change"),
            Outcome(result=PriceRef(category="Currency", key="Golden scrap"),
                    probability=0.35, notes="bricked salvage"),
        ],
        source="fixture: hand-calc", prob_sum_tolerance=1e-9,
    )


def test_golden_temple_double_corrupt_ev_matches_hand_calc() -> None:
    resolver = PriceResolver(PinnedPriceService(), NullDeepLink(), min_sample_depth=5)
    row = EvEngine(resolver, clock=_clock).evaluate(_golden_table(), "TestLeagueA")
    assert math.isclose(row.ev_gross, 124.7, rel_tol=1e-9, abs_tol=1e-6)
    assert math.isclose(row.ev_net, 64.7, rel_tol=1e-9, abs_tol=1e-6)
    assert row.unresolved_outcomes == 0
```

- [ ] **Step 2: Run the golden test**

Run: `uv run pytest tests/test_golden_ev.py -v`
Expected: PASS (EV gross 124.7, EV net 64.7 — exact within tolerance).

- [ ] **Step 3: Confirm compliance guards still pass**

Run: `uv run pytest tests/test_compliance.py -v`
Expected: PASS. Specifically:
- `test_no_trade_api_string_in_source` — no T2 source file contains `/api/trade/`; verify pricing routes only through the Phase 0/1 `DeepLinkResolver`.
- `test_no_hardcoded_league_name_in_source` — no `\b(Standard|Hardcore|Settlers)\b` in `oracle/**` or `tests/**` (all T2 tests/fixtures use invented ids like `TestLeagueA`, and seed odds files carry no league names).

If either fails, fix the offending source/test — do NOT weaken the guard.

- [ ] **Step 4: Write the live T2 smoke**

`tests/test_t2_live_smoke.py`:
```python
import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_t2_evaluates_against_default_league_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    rows = svc.t2.evaluate(default)
    assert rows  # enabled seed tables evaluated
    for r in rows:
        # EV numbers are finite; unresolved outcomes surfaced, never fabricated.
        assert r.ev_gross == r.ev_gross  # not NaN
        assert r.unresolved_outcomes >= 0


def test_scan_includes_probabilistic_section_live() -> None:
    svc = build_services()
    report, _md, _json = svc.scan.run(svc.settings.default_league)
    assert "PROBABILISTIC (Tier-2)" in report.to_terminal()
```

- [ ] **Step 5: Run the live smoke locally**

Run: `uv run pytest -m live tests/test_t2_live_smoke.py -v`
Expected: PASS against live data (a full T1+T2 scan well under the 10-min budget; category prices fetched once per scan). Local DoD gate, not CI.

- [ ] **Step 6: Manual DoD checklist** (record results in `docs/phase2-dod.md`)

- `uv run oracle scan --league <a-live-league>` prints a report whose deterministic (`AUTO-PRICED` / `VERIFY-REQUIRED`) and probabilistic (`PROBABILISTIC (Tier-2)`) sections are clearly separate (DoD: "report separates deterministic and probabilistic opportunities").
- `uv run oracle factory <table_id> --league <a-live-league> --bankroll 1000 --attempts 100` prints buy-N-inputs, expected total profit, and P10/P50/P90; re-running with the same `--seed` reproduces identical percentiles (determinism DoD).
- Golden temple double-corrupt EV reproduces the documented hand calc within tolerance (`tests/test_golden_ev.py`) — the notebook/`docs/phase2-dod.md` records the same arithmetic against live-Standard ninja prices for 3 real uniques (human fills the observed live prices; the code path is identical).
- Bankroll math validated by the hypothesis property test (`tests/test_bankroll.py::test_analytic_ev_equals_sum_p_v`).
- Each EV row carries source + confidence + timestamp; the report embeds league + snapshot ts + odds rule-file version; `ev_results` persists append-only.

- [ ] **Step 7: Full suite + quality gates**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest --cov=oracle --cov-report=term-missing`
Expected: all green; T2 coverage healthy.

- [ ] **Step 8: Commit + push**

```bash
git add tests/test_golden_ev.py tests/test_t2_live_smoke.py docs/phase2-dod.md
git commit -m "test: golden EV hand-calc, live T2 smoke, and Phase 2 DoD verification notes"
git push
```

---

## Self-Review

**PRD §Phase 2 deliverables → tasks:**
- Odds table format `data/odds_t2/*.yaml` (transform id, input spec, outcome list with probability + notes, odds source URL, patch validity) → **Task 2** (registry + seed) + **Task 1** (models). ✓
- Seed tables (Vaal corruption by item class, temple double-corrupt, tainted currency set; lab enchant pools "if odds obtainable" — OMITTED-and-noted per PRD; ninja-priceable outcomes; verify via ListingResolver for influence/ilvl refs) → **Task 2**. ✓
- EV engine (`Σ p·price` with per-outcome resolution incl. bricked salvage; minus inputs and service costs; temple carry cost as config) → **Task 3** (engine) + **Task 1** (`service_cost` field) + `[t2] default_service_cost` in **Task 1**. ✓
- Scanner integration (T2 in the same ranked report, flagged probabilistic, with EV, per-attempt variance, bankroll-fit annotation) → **Task 6** (separate PROBABILISTIC section, stddev, bankroll note) + **Task 4** (bankroll math) + **Task 7** (scan wires EV rows in). ✓
- Factory mode (production plan: buy N inputs, expected total profit, P10/P50/P90 via Monte Carlo) → **Task 5** (deterministic MC) + **Task 7** (`oracle factory` CLI + service). ✓

**PRD §Phase 2 DoD → coverage:**
- Temple double-corrupt EV matches a hand calc within tolerance, priced from ninja data → **Task 8** `test_golden_temple_double_corrupt_ev_matches_hand_calc` (pinned prices, documented hand calc) + live path in `docs/phase2-dod.md`. ✓
- Report separates deterministic and probabilistic opportunities → **Task 6** `test_terminal_has_separate_probabilistic_section` / `test_markdown_has_probabilistic_table`. ✓
- Bankroll math validated by a property-based test → **Task 4** `test_analytic_ev_equals_sum_p_v` (hypothesis). ✓

**Global-constraint coverage:**
- Compliance UNCHANGED (only ninja + league API; no `/api/trade/*`; specific listings only via `DeepLinkResolver`) → verify-priced refs route through the Phase 1 `PriceResolver.resolve_verify` → Phase 0 `DeepLinkResolver`; **Task 8** re-runs `tests/test_compliance.py`. ✓
- League always a runtime param; no hardcoded league in code/tests/fixtures (guard scans `tests/` too) → all T2 APIs take `league`; all tests/fixtures use invented ids (`TestLeagueA`); seed odds files carry no league names; **Task 8** re-runs the guard. ✓
- Rules as data, `extra="forbid"`, fail-loud on unknown shapes AND bad probability sums → **Task 1** (`OddsTable` validator, `extra="forbid"`) + **Task 2** (`OddsRegistryError` on shape + sum). ✓
- Determinism boundary; never fabricate a price (None surfaced/flagged, never 0) → **Task 3** (`unresolved_outcomes`, confidence penalty, None excluded) + **Task 5** (unresolved excluded from sampling, surfaced) + tests `test_none_outcome_price_excluded_not_zero`, `test_all_unresolved_outcomes_is_fail_visible`. ✓
- Monte Carlo deterministic via injected `random.Random(seed)`, no numpy → **Task 5** (`rng` injected, `test_plan_is_deterministic_given_seed`) + **Task 7** (`random.Random(seed)`, seed recorded). ✓
- Reproducibility (source/confidence/timestamps per EV row; reports embed league + snapshot ts + odds rule-file version; append-only persistence) → **Tasks 1, 3, 6, 7**. ✓
- mypy strict inheritance → all logic under `oracle/scanner/` + `oracle/store/`. ✓
- Tests live-marked → **Task 8**. ✓

**Type consistency:** `Outcome`/`OddsTable`/`OutcomeEv`/`EvRow` in `oracle/scanner/t2_models.py`; `OddsRegistry` in `t2_registry.py`; `EvEngine` in `ev.py`; bankroll functions in `bankroll.py`; `FactoryPlan`/`FactoryEngine` in `factory.py`; `T2Service` in `t2_service.py`; `EvResultRepo` in `oracle/store/ev_results.py`; `T2Settings` on `oracle.config.Settings`. The `_Resolver` Protocol consumed by `EvEngine` and `FactoryEngine` is satisfied by the real `PriceResolver` (`clear_cache`/`resolve_auto`/`resolve_verify` — exact Phase 1 signatures). `ScanReport.ev_rows` defaults to `[]` so Phase 1 construction is unchanged. `ScanService.t2` defaults to `None` so Phase 1 tests are unchanged. `EvEngine` imports `bankroll` (Task 4 augments Task 3's module).

**Placeholder scan:** No "TBD"/"similar to Task N" left; all code is complete. Seed odds numbers are illustrative-by-design (revalidated on patch day per PRD rules-as-data); DoD EV is proven with the pinned-price golden fixture, not a live-odds assumption.

**Task ordering (dependencies):** 1 (models/config) → 2 (odds registry, needs models) → 3 (EV engine, needs models + Phase 1 resolver) → 4 (bankroll, augments EV engine) → 5 (factory MC, needs EV engine + bankroll) → 6 (persistence + report, needs models; independent of 3-5, before 7) → 7 (T2Service + CLI + scan wiring, needs 2/3/5/6) → 8 (golden/compliance/live/DoD, needs all).
