# Oracle Phase 1 (Tier-1 Scanner) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tier-1 (deterministic) market-inefficiency scanner — a rules-as-data transform registry, a Price-Service-backed price resolver, a margin/ranking engine, append-only result persistence, a report renderer (terminal + markdown + JSON), and an `oracle scan` CLI command — to the PRD Phase 1 DoD. This is the first profitable milestone.

**Architecture:** A new `oracle/scanner/` subpackage (inherits mypy-strict and the compliance grep) sits on top of the Phase 0 `PriceService` and `DeepLinkResolver`. Transforms live in `data/transforms_t1.yaml` (Pydantic-validated, fail-loud, version-stamped). Each transform's sides are `PriceRef`s resolved to chaos values: `auto` refs go through `PriceService.prices(category, league)` (each category fetched once and cached per scan); `verify` refs go through `DeepLinkResolver` (human-in-the-loop, no fabricated price). The engine computes `margin = output_value − input_cost − friction`, ranks rows by margin, gates on liquidity/confidence thresholds, and flags verify-mode rows. Reports embed league, snapshot timestamp, and the rule-file version. League is always a runtime parameter; compliance is unchanged (only `api.pathofexile.com` + `poe.ninja` fetched; specific-listing pricing only via the existing `DeepLinkResolver`).

**Tech Stack:** Python 3.12+, uv, Typer, Pydantic v2, PyYAML, stdlib sqlite3, ruff, mypy (strict on `oracle/`), pytest, hypothesis. Builds directly on the Phase 0 services in `oracle/`.

## Global Constraints

- Python `>=3.12`. Managed with **uv** (`uv sync`, `uv run`).
- mypy is **strict** on `oracle/`. All new scanner logic lives under **`oracle/scanner/`** (a subpackage of the already-strict `oracle` package) so it inherits strict typing and the existing compliance grep — no new top-level package, no `[tool.mypy] files` change required.
- **Compliance UNCHANGED (hard):** only `api.pathofexile.com` + `poe.ninja` are ever fetched over HTTP; no `/api/trade/*`, ever; specific-listing pricing only via the existing `DeepLinkResolver` (human-in-the-loop). The compliance guard test (`tests/test_compliance.py`) must keep passing — no new module may issue HTTP directly, and no source file may contain the string `/api/trade/`.
- **League-agnostic:** league is always a runtime parameter. No league name hardcoded in code, tests, or fixtures. `"Standard"` may appear ONLY as a config default in `config/settings.toml` and in fixture *metadata*. (The compliance test greps `oracle/`, `scanner/`, `advisor/` for `\bStandard\b`.)
- **Rules as data:** transforms live in `data/transforms_t1.yaml` with Pydantic schema validation; unknown/changed shapes raise (fail-loud), never silently coerce.
- **Robust pricing / liquidity gating / reproducibility:** every scan row carries source attribution, confidence, and timestamps; below-threshold liquidity is demoted/suppressed; reports embed league + snapshot timestamp + rule-file version. Never fabricate a price — a `verify` ref with no observed price resolves to `None`.
- **Fail loud:** unknown YAML shapes and unknown pricing modes raise.
- ruff clean. Tests green in CI. Live-network tests marked `@pytest.mark.live` and skipped in CI.
- Commit after every task. Commit message trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

**Phase 0 interfaces this plan consumes (exact signatures, do not change):**
- `oracle.pricing.service.PriceService.prices(category: str, league: str) -> list[Price]` and `.maturity(league: str) -> Maturity`.
- `oracle.models.Price(key, league, category, chaos_value, sample_depth, source, confidence, ts)`.
- `oracle.pricing.listings.DeepLinkResolver.resolve(spec: ItemSpec, league: str) -> ListingQuote`; `.record_observed_price(spec, league, chaos_value)`.
- `oracle.models.ItemSpec(base, ilvl=None, influence=None, mod_filters=[], sockets=None, links=None)`; `oracle.models.ListingQuote(spec_hash, league, chaos_value: float | None, deep_link, residual_instructions, source, observed_ts)`.
- `oracle.store.db.connect(db_path) -> sqlite3.Connection`; `MIGRATIONS: list[str]`.
- `oracle.config.Settings` / `load_settings(path=None)`.
- `oracle.app.build_services(settings=None) -> Services`; `Services` dataclass; `HTTP_ALLOWED_HOSTS`.
- `oracle.cli.app`, `oracle.cli._services()`.

---

### Task 1: Scanner models + scanner-config section

**Files:**
- Create: `oracle/scanner/__init__.py`, `oracle/scanner/models.py`, `tests/test_scanner_models.py`
- Modify: `oracle/config.py` (add `ScannerSettings` + `scanner` field on `Settings`), `config/settings.toml` (add `[scanner]`)

**Interfaces:**
- Produces (`oracle/scanner/models.py`):
  - `PriceRef(category: str, key: str, qty: float = 1.0, influence: str | None = None, ilvl: int | None = None)`
  - `Transform(id: str, name: str, inputs: list[PriceRef], output: PriceRef, applicability: str = "", friction: float = 0.0, enabled: bool = True, patch_validity: str = "", pricing_mode: Literal["auto", "verify"] = "auto")`
  - `ScanRow(transform_id, name, input_cost, output_value: float | None, margin: float | None, margin_pct: float | None, liquidity: float, confidence: float, pricing_mode: str, deep_link: str | None, source: str, ts: datetime)`
- Produces (`oracle/config.py`): `ScannerSettings(min_margin: float, min_liquidity: float)`, `Settings.scanner: ScannerSettings`.

- [ ] **Step 1: Write the failing test**

`tests/test_scanner_models.py`:
```python
from datetime import UTC, datetime

from oracle.config import ScannerSettings, load_settings
from oracle.scanner.models import PriceRef, ScanRow, Transform


def test_priceref_defaults() -> None:
    ref = PriceRef(category="Currency", key="Divine Orb")
    assert ref.qty == 1.0
    assert ref.influence is None
    assert ref.ilvl is None


def test_transform_defaults_to_auto_enabled() -> None:
    t = Transform(
        id="t1",
        name="Example",
        inputs=[PriceRef(category="Currency", key="Chaos Orb")],
        output=PriceRef(category="Fossil", key="Some Fossil"),
    )
    assert t.enabled is True
    assert t.pricing_mode == "auto"
    assert t.friction == 0.0


def test_transform_rejects_unknown_pricing_mode() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Transform(
            id="t1",
            name="Example",
            inputs=[PriceRef(category="Currency", key="Chaos Orb")],
            output=PriceRef(category="Fossil", key="Some Fossil"),
            pricing_mode="wat",  # type: ignore[arg-type]
        )


def test_scanrow_allows_none_output_for_verify() -> None:
    row = ScanRow(
        transform_id="t1",
        name="Example",
        input_cost=10.0,
        output_value=None,
        margin=None,
        margin_pct=None,
        liquidity=0.0,
        confidence=0.0,
        pricing_mode="verify",
        deep_link="https://www.pathofexile.com/trade/search/X?q=...",
        source="verify",
        ts=datetime.now(tz=UTC),
    )
    assert row.output_value is None
    assert row.deep_link is not None


def test_scanner_settings_loaded_from_config() -> None:
    settings = load_settings()
    assert isinstance(settings.scanner, ScannerSettings)
    assert settings.scanner.min_margin >= 0.0
    assert settings.scanner.min_liquidity >= 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scanner_models.py -v`
Expected: FAIL (no module `oracle.scanner.models`; no `ScannerSettings`).

- [ ] **Step 3: Implement models + config**

`oracle/scanner/__init__.py`: empty file.

`oracle/scanner/models.py`:
```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PriceRef(BaseModel):
    category: str
    key: str
    qty: float = 1.0
    influence: str | None = None
    ilvl: int | None = None


class Transform(BaseModel):
    id: str
    name: str
    inputs: list[PriceRef]
    output: PriceRef
    applicability: str = ""
    friction: float = 0.0
    enabled: bool = True
    patch_validity: str = ""
    pricing_mode: Literal["auto", "verify"] = "auto"


class ScanRow(BaseModel):
    transform_id: str
    name: str
    input_cost: float
    output_value: float | None
    margin: float | None
    margin_pct: float | None
    liquidity: float
    confidence: float
    pricing_mode: str
    deep_link: str | None
    source: str
    ts: datetime
```

Add to `oracle/config.py` — a new settings model and a field on `Settings`:
```python
class ScannerSettings(BaseModel):
    min_margin: float = Field(ge=0.0)
    min_liquidity: float = Field(ge=0.0)
```
and add to `class Settings`:
```python
    scanner: ScannerSettings
```

Add to `config/settings.toml`:
```toml
[scanner]
min_margin = 15.0          # chaos; rows below this margin are suppressed
min_liquidity = 5.0        # min sample-depth-derived liquidity to rank normally
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_scanner_models.py tests/test_config.py -v && uv run mypy`
Expected: PASS, mypy clean. (`tests/test_config.py` still passes because the new `[scanner]` section is present in the default file.)

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/__init__.py oracle/scanner/models.py oracle/config.py config/settings.toml tests/test_scanner_models.py
git commit -m "feat: scanner models (PriceRef/Transform/ScanRow) and [scanner] settings"
```

---

### Task 2: Transform registry (load + validate `transforms_t1.yaml`, fail-loud, versioned)

**Files:**
- Create: `oracle/scanner/registry.py`, `data/transforms_t1.yaml`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `oracle.scanner.models.Transform`, `PriceRef`.
- Produces:
  - `TransformRegistryError(Exception)` — raised on unknown/invalid YAML shapes.
  - `TransformRegistry(transforms: list[Transform], version: str)` with:
    - `.enabled() -> list[Transform]` (only `enabled is True`).
    - `.version` (str: a stable content hash of the file, prefixed `sha256:`).
  - `load_registry(path: Path) -> TransformRegistry` — reads YAML, validates each entry via `Transform.model_validate`, fails loud on malformed shapes, computes a version hash of the raw file bytes.
- `DEFAULT_TRANSFORMS_PATH = Path("data/transforms_t1.yaml")`.

**Notes:** The version is `"sha256:" + hashlib.sha256(raw_bytes).hexdigest()[:16]`, so a data edit changes the stamped rule-file version deterministically. The YAML top level is a mapping with a `transforms:` list.

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:
```python
from pathlib import Path

import pytest

from oracle.scanner.registry import (
    DEFAULT_TRANSFORMS_PATH,
    TransformRegistry,
    TransformRegistryError,
    load_registry,
)


def test_loads_default_seed_and_versions() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    assert isinstance(reg, TransformRegistry)
    assert reg.version.startswith("sha256:")
    assert len(reg.transforms) >= 15  # seed target ~15-20


def test_enabled_filters_disabled() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    assert all(t.enabled for t in reg.enabled())
    # at least one disabled entry exists in the seed (patch-mechanic-dependent)
    assert any(not t.enabled for t in reg.transforms)


def test_disabled_entries_carry_patch_validity_note() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    for t in reg.transforms:
        if not t.enabled:
            assert t.patch_validity, f"{t.id} disabled without a patch_validity note"


def test_ids_are_unique() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    ids = [t.id for t in reg.transforms]
    assert len(ids) == len(set(ids))


def test_version_changes_with_content(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    a.write_text(
        "transforms:\n"
        "  - id: t1\n    name: A\n    inputs:\n"
        "      - {category: Currency, key: Chaos Orb}\n"
        "    output: {category: Fossil, key: F}\n"
    )
    b = tmp_path / "b.yaml"
    b.write_text(
        "transforms:\n"
        "  - id: t1\n    name: B\n    inputs:\n"
        "      - {category: Currency, key: Chaos Orb}\n"
        "    output: {category: Fossil, key: F}\n"
    )
    assert load_registry(a).version != load_registry(b).version


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("transforms:\n  - id: t1\n    unexpected_key: 1\n")
    with pytest.raises(TransformRegistryError):
        load_registry(bad)


def test_missing_transforms_key_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_transforms: []\n")
    with pytest.raises(TransformRegistryError):
        load_registry(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL (no module `oracle.scanner.registry`; no seed file yet).

- [ ] **Step 3: Implement the registry**

`oracle/scanner/registry.py`:
```python
import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from oracle.scanner.models import Transform

DEFAULT_TRANSFORMS_PATH = Path("data/transforms_t1.yaml")


class TransformRegistryError(Exception):
    """Raised when the transforms file has an unknown or invalid shape."""


class TransformRegistry:
    def __init__(self, transforms: list[Transform], version: str) -> None:
        self.transforms = transforms
        self.version = version

    def enabled(self) -> list[Transform]:
        return [t for t in self.transforms if t.enabled]


def load_registry(path: Path) -> TransformRegistry:
    raw = path.read_bytes()
    version = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise TransformRegistryError(f"invalid YAML: {exc}") from exc
    if not isinstance(doc, dict) or "transforms" not in doc:
        raise TransformRegistryError("top-level 'transforms' key is required")
    entries = doc["transforms"]
    if not isinstance(entries, list):
        raise TransformRegistryError("'transforms' must be a list")
    transforms: list[Transform] = []
    for entry in entries:
        try:
            transforms.append(Transform.model_validate(entry))
        except ValidationError as exc:
            raise TransformRegistryError(f"invalid transform entry: {exc}") from exc
    return TransformRegistry(transforms, version)
```

**Fail-loud on extra keys:** so `test_unknown_shape_fails_loud` passes, the models must forbid extras. Add `model_config = ConfigDict(extra="forbid")` to `PriceRef` and `Transform` in `oracle/scanner/models.py`:
```python
from pydantic import BaseModel, ConfigDict
```
and inside `class PriceRef` and `class Transform`:
```python
    model_config = ConfigDict(extra="forbid")
```
(Do NOT add `extra="forbid"` to `ScanRow` — it is constructed only internally.)

- [ ] **Step 4: Write the seed `data/transforms_t1.yaml`**

Categories use ninja `type=` values that the Phase 0 ninja client supports (`Currency`, `Fossil`, `Essence`, `UniqueWeapon`, `UniqueArmour`, `UniqueAccessory`, `BaseType`). ~18 transforms, biased toward `auto`. Patch-mechanic-dependent (sockets/links) entries ship `enabled: false` with a `patch_validity` note. The flagship shaper-shield base+influence case is marked `verify` (base-type-feed dependency: within-category variance is variance-sensitive; PRD §7.2 flags such rares for verify-mode). Prices/keys are illustrative and re-validated on patch day; the DoD shield detection is proven separately via a synthetic fixture in Task 6.

```yaml
# Tier-1 deterministic transforms. Rules-as-data: edit + revalidate on patch day.
# category values map to poe.ninja `type=` values supported by the Phase 0 client.
transforms:
  - id: fossil_bound_reroll
    name: "Bound Fossil arbitrage (buy vs vendor-equivalent)"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 1.0}
    output: {category: Fossil, key: "Bound Fossil"}
    applicability: "Fossil priceable on ninja; deterministic vendor/exchange path"
    friction: 0.0
    enabled: true
    pricing_mode: auto

  - id: fossil_aberrant
    name: "Aberrant Fossil resale"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 1.0}
    output: {category: Fossil, key: "Aberrant Fossil"}
    enabled: true
    pricing_mode: auto

  - id: fossil_pristine
    name: "Pristine Fossil resale"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 1.0}
    output: {category: Fossil, key: "Pristine Fossil"}
    enabled: true
    pricing_mode: auto

  - id: essence_greed_upgrade
    name: "Essence of Greed tier upgrade (3->1 via bench)"
    inputs:
      - {category: Essence, key: "Deafening Essence of Greed", qty: 3.0}
    output: {category: Essence, key: "Deafening Essence of Greed"}
    applicability: "Essence upgrade recipe; both sides ninja-priceable"
    friction: 0.0
    enabled: true
    pricing_mode: auto

  - id: essence_contempt_upgrade
    name: "Essence of Contempt tier upgrade"
    inputs:
      - {category: Essence, key: "Deafening Essence of Contempt", qty: 3.0}
    output: {category: Essence, key: "Deafening Essence of Contempt"}
    enabled: true
    pricing_mode: auto

  - id: essence_wrath_upgrade
    name: "Essence of Wrath tier upgrade"
    inputs:
      - {category: Essence, key: "Deafening Essence of Wrath", qty: 3.0}
    output: {category: Essence, key: "Deafening Essence of Wrath"}
    enabled: true
    pricing_mode: auto

  - id: chrom_recipe
    name: "Chromatic Orb vendor recipe (off-colour base -> chrom)"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 0.1}
    output: {category: Currency, key: "Chromatic Orb"}
    applicability: "Deterministic vendor recipe"
    friction: 0.0
    enabled: true
    pricing_mode: auto

  - id: jeweller_recipe
    name: "Jeweller's Orb vendor / exchange play"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 0.1}
    output: {category: Currency, key: "Jeweller's Orb"}
    enabled: true
    pricing_mode: auto

  - id: fusing_from_jewellers
    name: "Fusing resale via exchange"
    inputs:
      - {category: Currency, key: "Jeweller's Orb", qty: 4.0}
    output: {category: Currency, key: "Orb of Fusing"}
    enabled: true
    pricing_mode: auto

  - id: regret_to_chaos
    name: "Orb of Regret exchange"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 1.0}
    output: {category: Currency, key: "Orb of Regret"}
    enabled: true
    pricing_mode: auto

  - id: divine_from_chaos
    name: "Divine Orb accumulation"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 150.0}
    output: {category: Currency, key: "Divine Orb"}
    enabled: true
    pricing_mode: auto

  - id: annul_exchange
    name: "Orb of Annulment exchange"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 5.0}
    output: {category: Currency, key: "Orb of Annulment"}
    enabled: true
    pricing_mode: auto

  - id: awakener_flip
    name: "Awakener's Orb resale"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 20.0}
    output: {category: Currency, key: "Awakener's Orb"}
    enabled: true
    pricing_mode: auto

  - id: unique_tabula_flip
    name: "Cheap unique acquisition vs resale (Tabula Rasa)"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 10.0}
    output: {category: UniqueArmour, key: "Tabula Rasa"}
    applicability: "Popular unique tracked by ninja unique feed"
    enabled: true
    pricing_mode: auto

  - id: unique_goldrim_flip
    name: "Goldrim resale"
    inputs:
      - {category: Currency, key: "Chaos Orb", qty: 1.0}
    output: {category: UniqueArmour, key: "Goldrim"}
    enabled: true
    pricing_mode: auto

  - id: catalyst_quality_play
    name: "Turbulent Catalyst quality play on ring/amulet base"
    inputs:
      - {category: Currency, key: "Turbulent Catalyst", qty: 10.0}
      - {category: Currency, key: "Chaos Orb", qty: 5.0}
    output: {category: UniqueAccessory, key: "Ventor's Gamble"}
    applicability: "Catalyst quality adds value; approximated via ninja feeds"
    friction: 2.0
    enabled: true
    pricing_mode: auto

  # --- Flagship shaper-shield case: verify-mode (base-type feed variance-sensitive). ---
  - id: shaper_shield_base_influence
    name: "Shaper Titanium Spirit Shield: plain base + Shaper's Orb"
    inputs:
      - {category: BaseType, key: "Titanium Spirit Shield", qty: 1.0, ilvl: 84}
      - {category: Currency, key: "Shaper's Orb", qty: 1.0}
    output:
      {category: BaseType, key: "Titanium Spirit Shield", qty: 1.0,
       influence: shaper, ilvl: 84}
    applicability: >
      Flagship deterministic transform (PRD s2). Output is a specific
      influenced base; ninja base-type category feeds mask within-category
      ilvl/roll variance, so priced via ListingResolver (verify).
    friction: 0.0
    enabled: true
    pricing_mode: verify

  # --- Patch-mechanic-dependent: ships DISABLED until validated against the patch. ---
  - id: six_link_bench
    name: "6-link via bench (socket/link mechanic dependent)"
    inputs:
      - {category: Currency, key: "Orb of Fusing", qty: 150.0}
    output: {category: UniqueArmour, key: "Tabula Rasa"}
    applicability: "Socket/link crafting; validity depends on current patch mechanics"
    enabled: false
    patch_validity: >
      DISABLED: link/socket odds and bench costs are patch-specific; re-validate
      against current patch notes before enabling (see docs/patch-day.md).
    pricing_mode: auto
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_registry.py -v && uv run mypy`
Expected: PASS (>=15 transforms, >=1 disabled with a note, unique ids), mypy clean.

- [ ] **Step 6: Commit**

```bash
git add oracle/scanner/registry.py oracle/scanner/models.py data/transforms_t1.yaml tests/test_registry.py
git commit -m "feat: transform registry with fail-loud YAML validation and versioned seed"
```

---

### Task 3: Price resolution (auto via PriceService, verify via DeepLinkResolver)

**Files:**
- Create: `oracle/scanner/resolve.py`, `tests/test_resolve.py`

**Interfaces:**
- Consumes: `PriceService.prices(category, league) -> list[Price]`; `DeepLinkResolver.resolve(spec, league) -> ListingQuote`; `PriceRef`; `ItemSpec`.
- Produces:
  - `ResolvedPrice(chaos_value: float | None, liquidity: float, confidence: float, source: str, deep_link: str | None)` (a frozen dataclass).
  - `PriceResolver(price_service, resolver, min_sample_depth: int)` with:
    - `.resolve_auto(ref: PriceRef, league: str) -> ResolvedPrice` — looks up the ref's key in the ref's category (fetched once per scan via an internal per-league category cache); `liquidity = Price.sample_depth`; `confidence = Price.confidence`; `source = Price.source`; `chaos_value = Price.chaos_value * ref.qty`. Missing key → `ResolvedPrice(None, 0.0, 0.0, "missing:<category>/<key>", None)` (never fabricate).
    - `.resolve_verify(ref: PriceRef, league: str) -> ResolvedPrice` — builds an `ItemSpec` from the ref and calls `DeepLinkResolver.resolve`; `chaos_value` = observed price (× qty) if present else `None`; `source` = quote.source; `deep_link` = quote.deep_link; liquidity/confidence 0.0 when unobserved.
    - `.clear_cache() -> None` — resets the per-scan category cache (called at the start of each scan).

**Notes:** `_ItemSpec` build maps `PriceRef.key -> base`, `ilvl -> ilvl`, `influence -> influence`. The category cache is keyed `(league, category) -> dict[str, Price]` so each ninja category is fetched at most once per scan (Global Constraint: everything cacheable is cached; PRD perf: full scan <10 min).

- [ ] **Step 1: Write the failing test**

`tests/test_resolve.py`:
```python
from datetime import UTC, datetime

from oracle.models import ItemSpec, ListingQuote, Price
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import PriceResolver, ResolvedPrice


class FakePriceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def prices(self, category: str, league: str) -> list[Price]:
        self.calls.append((category, league))
        now = datetime.now(tz=UTC)
        table = {
            "Currency": [Price(key="Chaos Orb", league=league, category=category,
                               chaos_value=1.0, sample_depth=500, source="ninja:Currency",
                               confidence=0.9, ts=now),
                         Price(key="Divine Orb", league=league, category=category,
                               chaos_value=180.0, sample_depth=300, source="ninja:Currency",
                               confidence=0.95, ts=now)],
            "Fossil": [Price(key="Bound Fossil", league=league, category=category,
                             chaos_value=8.0, sample_depth=40, source="ninja:Fossil",
                             confidence=0.7, ts=now)],
        }
        return table.get(category, [])


class FakeResolver:
    def __init__(self, quote: ListingQuote) -> None:
        self._quote = quote
        self.seen: list[ItemSpec] = []

    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote:
        self.seen.append(spec)
        return self._quote


def _resolver(price_svc: object, quote: ListingQuote) -> PriceResolver:
    return PriceResolver(price_svc, FakeResolver(quote), min_sample_depth=5)


def _quote(value: float | None, source: str) -> ListingQuote:
    return ListingQuote(spec_hash="h", league="L", chaos_value=value,
                        deep_link="https://www.pathofexile.com/trade/search/L?q=x",
                        residual_instructions=[], source=source, observed_ts=None)


def test_resolve_auto_looks_up_key_and_scales_by_qty() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    res = r.resolve_auto(PriceRef(category="Currency", key="Divine Orb", qty=2.0), "L")
    assert res.chaos_value == 360.0
    assert res.liquidity == 300
    assert res.confidence == 0.95
    assert res.source == "ninja:Currency"


def test_resolve_auto_caches_category_per_scan() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    r.resolve_auto(PriceRef(category="Currency", key="Divine Orb"), "L")
    assert svc.calls == [("Currency", "L")]  # fetched once


def test_resolve_auto_missing_key_never_fabricates() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    res = r.resolve_auto(PriceRef(category="Currency", key="Nonexistent"), "L")
    assert res.chaos_value is None
    assert res.liquidity == 0.0
    assert res.source.startswith("missing:")


def test_resolve_verify_unobserved_returns_none_with_link() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield",
                   ilvl=84, influence="shaper")
    res = r.resolve_verify(ref, "L")
    assert res.chaos_value is None
    assert res.deep_link is not None
    assert res.source == "unresolved"


def test_resolve_verify_observed_returns_value_scaled() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(50.0, "user-observed"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", qty=2.0)
    res = r.resolve_verify(ref, "L")
    assert res.chaos_value == 100.0
    assert res.source == "user-observed"


def test_clear_cache_forces_refetch() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    r.clear_cache()
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    assert svc.calls == [("Currency", "L"), ("Currency", "L")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: FAIL (no module `oracle.scanner.resolve`).

- [ ] **Step 3: Implement the resolver**

`oracle/scanner/resolve.py`:
```python
from dataclasses import dataclass
from typing import Protocol

from oracle.models import ItemSpec, ListingQuote, Price
from oracle.scanner.models import PriceRef


class _PriceService(Protocol):
    def prices(self, category: str, league: str) -> list[Price]: ...


class _Resolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...


@dataclass(frozen=True)
class ResolvedPrice:
    chaos_value: float | None
    liquidity: float
    confidence: float
    source: str
    deep_link: str | None


class PriceResolver:
    def __init__(
        self,
        price_service: _PriceService,
        resolver: _Resolver,
        min_sample_depth: int,
    ) -> None:
        self._prices = price_service
        self._resolver = resolver
        self._min_depth = min_sample_depth
        self._cache: dict[tuple[str, str], dict[str, Price]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _category_table(self, category: str, league: str) -> dict[str, Price]:
        cache_key = (league, category)
        cached = self._cache.get(cache_key)
        if cached is None:
            cached = {p.key: p for p in self._prices.prices(category, league)}
            self._cache[cache_key] = cached
        return cached

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        table = self._category_table(ref.category, league)
        price = table.get(ref.key)
        if price is None:
            return ResolvedPrice(
                chaos_value=None,
                liquidity=0.0,
                confidence=0.0,
                source=f"missing:{ref.category}/{ref.key}",
                deep_link=None,
            )
        return ResolvedPrice(
            chaos_value=price.chaos_value * ref.qty,
            liquidity=float(price.sample_depth),
            confidence=price.confidence,
            source=price.source,
            deep_link=None,
        )

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        spec = ItemSpec(base=ref.key, ilvl=ref.ilvl, influence=ref.influence)
        quote = self._resolver.resolve(spec, league)
        value = None if quote.chaos_value is None else quote.chaos_value * ref.qty
        liquidity = 0.0
        confidence = 0.0 if value is None else 0.5
        return ResolvedPrice(
            chaos_value=value,
            liquidity=liquidity,
            confidence=confidence,
            source=quote.source,
            deep_link=quote.deep_link,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_resolve.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/resolve.py tests/test_resolve.py
git commit -m "feat: scanner price resolver (auto via PriceService, verify via DeepLinkResolver)"
```

---

### Task 4: Scan engine (margin math, verify-mode, ranking, gating)

**Files:**
- Create: `oracle/scanner/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: `TransformRegistry.enabled()`, `PriceResolver`, `ScannerSettings`, `Transform`, `PriceRef`, `ScanRow`.
- Produces:
  - `ScanEngine(registry, resolver, settings_scanner, clock: Callable[[], datetime] = ...)` with:
    - `.scan(league: str, min_margin: float | None = None) -> list[ScanRow]` — for each enabled transform: resolve all inputs + the output; `input_cost = Σ resolved.chaos_value` (0.0 for any `None` input contributes but the row is flagged unpriced); a transform is effectively `verify` if `pricing_mode == "verify"` OR any side is a verify side; `margin = output_value − input_cost − friction`; `margin_pct = margin / input_cost` when `input_cost > 0`; `liquidity` and `confidence` = min across all priced sides; carry the output's (or any) deep-link when in verify mode. Rank by `margin` descending (rows with `margin is None`, i.e. verify/unpriced, sorted after priced rows, "provisional"). Suppress auto-priced rows below the effective `min_margin` OR below `settings.min_liquidity`; verify-mode rows are always retained and flagged.

**Notes:** `min` across sides uses only sides that have a numeric price; if any *auto* input/output is unpriced (`None`), the row's `output_value`/`margin` become `None` and it is treated as provisional (cannot fabricate). Verify rows with an unobserved output have `output_value=None` and rank provisionally with their deep-link.

- [ ] **Step 1: Write the failing test**

`tests/test_engine.py`:
```python
from datetime import UTC, datetime

from oracle.config import ScannerSettings
from oracle.scanner.engine import ScanEngine
from oracle.scanner.models import PriceRef, Transform
from oracle.scanner.registry import TransformRegistry
from oracle.scanner.resolve import ResolvedPrice


class StubResolver:
    """Maps (category, key) -> ResolvedPrice for auto; a fixed quote for verify."""

    def __init__(self, auto: dict[tuple[str, str], ResolvedPrice],
                 verify: ResolvedPrice) -> None:
        self._auto = auto
        self._verify = verify

    def clear_cache(self) -> None:
        pass

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._auto[(ref.category, ref.key)]

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._verify


def _auto(value: float, liq: float, conf: float) -> ResolvedPrice:
    return ResolvedPrice(chaos_value=value, liquidity=liq, confidence=conf,
                         source="ninja:x", deep_link=None)


def _settings() -> ScannerSettings:
    return ScannerSettings(min_margin=15.0, min_liquidity=5.0)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _t(tid: str, in_cat: str, in_key: str, out_cat: str, out_key: str,
       friction: float = 0.0, mode: str = "auto") -> Transform:
    return Transform(id=tid, name=tid, inputs=[PriceRef(category=in_cat, key=in_key)],
                     output=PriceRef(category=out_cat, key=out_key),
                     friction=friction, pricing_mode=mode)  # type: ignore[arg-type]


def test_margin_math_and_pct() -> None:
    t = _t("big", "Currency", "Chaos Orb", "Fossil", "Bound Fossil", friction=1.0)
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
            ("Fossil", "Bound Fossil"): _auto(40.0, 50, 0.8)}
    engine = ScanEngine(TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)),
                        _settings(), clock=_clock)
    rows = engine.scan("L")
    assert len(rows) == 1
    row = rows[0]
    assert row.input_cost == 10.0
    assert row.output_value == 40.0
    assert row.margin == 29.0  # 40 - 10 - 1
    assert abs(row.margin_pct - 2.9) < 1e-9
    assert row.liquidity == 50  # min across sides
    assert row.confidence == 0.8


def test_ranking_descending_by_margin() -> None:
    t1 = _t("small", "Currency", "Chaos Orb", "Fossil", "A")
    t2 = _t("large", "Currency", "Chaos Orb", "Fossil", "B")
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
            ("Fossil", "A"): _auto(30.0, 50, 0.8),
            ("Fossil", "B"): _auto(80.0, 50, 0.8)}
    engine = ScanEngine(TransformRegistry([t1, t2], "v"),
                        StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock)
    rows = engine.scan("L")
    assert [r.transform_id for r in rows] == ["large", "small"]


def test_below_min_margin_suppressed() -> None:
    t = _t("thin", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
            ("Fossil", "A"): _auto(20.0, 50, 0.8)}  # margin 10 < 15
    engine = ScanEngine(TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)),
                        _settings(), clock=_clock)
    assert engine.scan("L") == []


def test_below_min_liquidity_suppressed() -> None:
    t = _t("illiquid", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 2, 0.9),  # liq 2 < 5
            ("Fossil", "A"): _auto(80.0, 2, 0.8)}
    engine = ScanEngine(TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)),
                        _settings(), clock=_clock)
    assert engine.scan("L") == []


def test_verify_row_retained_and_flagged_with_deeplink() -> None:
    t = _t("shield", "BaseType", "Plain Base", "BaseType", "Shaper Base", mode="verify")
    auto = {("BaseType", "Plain Base"): _auto(5.0, 40, 0.7)}
    verify = ResolvedPrice(chaos_value=None, liquidity=0.0, confidence=0.0,
                           source="unresolved",
                           deep_link="https://www.pathofexile.com/trade/search/L?q=x")
    engine = ScanEngine(TransformRegistry([t], "v"), StubResolver(auto, verify),
                        _settings(), clock=_clock)
    rows = engine.scan("L")
    assert len(rows) == 1
    assert rows[0].pricing_mode == "verify"
    assert rows[0].output_value is None
    assert rows[0].margin is None
    assert rows[0].deep_link is not None


def test_priced_rows_rank_before_provisional_verify_rows() -> None:
    priced = _t("priced", "Currency", "Chaos Orb", "Fossil", "A")
    prov = _t("prov", "BaseType", "Plain Base", "BaseType", "Shaper Base", mode="verify")
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
            ("Fossil", "A"): _auto(80.0, 50, 0.8),
            ("BaseType", "Plain Base"): _auto(5.0, 40, 0.7)}
    verify = ResolvedPrice(None, 0.0, 0.0, "unresolved",
                           "https://www.pathofexile.com/trade/search/L?q=x")
    engine = ScanEngine(TransformRegistry([priced, prov], "v"),
                        StubResolver(auto, verify), _settings(), clock=_clock)
    rows = engine.scan("L")
    assert [r.transform_id for r in rows] == ["priced", "prov"]


def test_min_margin_override() -> None:
    t = _t("thin", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
            ("Fossil", "A"): _auto(20.0, 50, 0.8)}  # margin 10
    engine = ScanEngine(TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)),
                        _settings(), clock=_clock)
    assert engine.scan("L", min_margin=5.0)  # now passes with override
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine.py -v`
Expected: FAIL (no module `oracle.scanner.engine`).

- [ ] **Step 3: Implement the engine**

`oracle/scanner/engine.py`:
```python
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.config import ScannerSettings
from oracle.scanner.models import PriceRef, ScanRow, Transform
from oracle.scanner.registry import TransformRegistry
from oracle.scanner.resolve import ResolvedPrice


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class ScanEngine:
    def __init__(
        self,
        registry: TransformRegistry,
        resolver: _Resolver,
        settings_scanner: ScannerSettings,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._registry = registry
        self._resolver = resolver
        self._settings = settings_scanner
        self._clock = clock

    def _resolve_side(self, ref: PriceRef, is_verify: bool, league: str) -> ResolvedPrice:
        if is_verify:
            return self._resolver.resolve_verify(ref, league)
        return self._resolver.resolve_auto(ref, league)

    def _row(self, t: Transform, league: str) -> ScanRow:
        is_verify = t.pricing_mode == "verify"
        input_res = [self._resolve_side(ref, is_verify, league) for ref in t.inputs]
        output_res = self._resolve_side(t.output, is_verify, league)

        priced = [r for r in [*input_res, output_res] if r.chaos_value is not None]
        liquidity = min((r.liquidity for r in priced), default=0.0)
        confidence = min((r.confidence for r in priced), default=0.0)
        deep_link = output_res.deep_link or next(
            (r.deep_link for r in input_res if r.deep_link is not None), None
        )
        source = output_res.source

        input_cost = sum(r.chaos_value or 0.0 for r in input_res)
        inputs_priced = all(r.chaos_value is not None for r in input_res)
        output_value = output_res.chaos_value
        if output_value is None or not inputs_priced:
            margin: float | None = None
            margin_pct: float | None = None
        else:
            margin = output_value - input_cost - t.friction
            margin_pct = margin / input_cost if input_cost > 0 else None

        return ScanRow(
            transform_id=t.id,
            name=t.name,
            input_cost=input_cost,
            output_value=output_value,
            margin=margin,
            margin_pct=margin_pct,
            liquidity=liquidity,
            confidence=confidence,
            pricing_mode="verify" if is_verify else "auto",
            deep_link=deep_link,
            source=source,
            ts=self._clock(),
        )

    def scan(self, league: str, min_margin: float | None = None) -> list[ScanRow]:
        threshold = self._settings.min_margin if min_margin is None else min_margin
        self._resolver.clear_cache()
        rows = [self._row(t, league) for t in self._registry.enabled()]

        kept: list[ScanRow] = []
        for row in rows:
            if row.pricing_mode == "verify" or row.margin is None:
                kept.append(row)  # provisional; always retained, flagged in report
                continue
            if row.margin < threshold or row.liquidity < self._settings.min_liquidity:
                continue
            kept.append(row)

        # Priced rows (margin not None) ranked by margin desc; provisional rows last.
        kept.sort(key=lambda r: (r.margin is None, -(r.margin or 0.0)))
        return kept
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_engine.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/engine.py tests/test_engine.py
git commit -m "feat: scan engine with margin math, liquidity gating, verify-mode flagging, ranking"
```

---

### Task 5: Scan-results persistence (migration + repo)

**Files:**
- Create: `oracle/store/scans.py`, `tests/test_store_scans.py`
- Modify: `oracle/store/db.py` (append the `scan_results` migration)

**Interfaces:**
- Consumes: `connect`, `ScanRow`.
- Produces:
  - New migration DDL appended to `MIGRATIONS` creating append-only `scan_results` (id, league, ts, rule_version, transform_id, name, input_cost, output_value, margin, margin_pct, liquidity, confidence, pricing_mode, source) + an index on `(league, ts)`.
  - `ScanResultRepo(conn)` with:
    - `.insert_many(league: str, rule_version: str, rows: list[ScanRow]) -> None`
    - `.recent(league: str, limit: int = 100) -> list[dict[str, object]]` (most recent first, for later margin-decay analysis).

- [ ] **Step 1: Write the failing test**

`tests/test_store_scans.py`:
```python
from datetime import UTC, datetime

from oracle.scanner.models import ScanRow
from oracle.store.db import connect
from oracle.store.scans import ScanResultRepo


def _row(tid: str, margin: float | None) -> ScanRow:
    return ScanRow(transform_id=tid, name=tid, input_cost=10.0,
                   output_value=None if margin is None else 10.0 + margin,
                   margin=margin, margin_pct=None if margin is None else margin / 10.0,
                   liquidity=50.0, confidence=0.8, pricing_mode="auto",
                   deep_link=None, source="ninja:x", ts=datetime.now(tz=UTC))


def test_scan_results_table_exists(tmp_path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {r["name"] for r in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "scan_results" in tables


def test_insert_and_recent_round_trip(tmp_path) -> None:
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("L", "sha256:abc", [_row("a", 30.0), _row("b", None)])
    recent = repo.recent("L")
    assert len(recent) == 2
    assert {r["transform_id"] for r in recent} == {"a", "b"}
    assert all(r["rule_version"] == "sha256:abc" for r in recent)


def test_append_only_accumulates(tmp_path) -> None:
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("L", "v1", [_row("a", 30.0)])
    repo.insert_many("L", "v2", [_row("a", 25.0)])
    assert len(repo.recent("L")) == 2  # nothing overwritten
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_scans.py -v`
Expected: FAIL (no `scan_results` table; no module `oracle.store.scans`).

- [ ] **Step 3: Add migration + implement repo**

Append to `MIGRATIONS` in `oracle/store/db.py` (add these two entries to the end of the list):
```python
    """
    CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        ts TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        transform_id TEXT NOT NULL,
        name TEXT NOT NULL,
        input_cost REAL NOT NULL,
        output_value REAL,
        margin REAL,
        margin_pct REAL,
        liquidity REAL NOT NULL,
        confidence REAL NOT NULL,
        pricing_mode TEXT NOT NULL,
        source TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_scan_league_ts
        ON scan_results (league, ts)
    """,
```

`oracle/store/scans.py`:
```python
import sqlite3

from oracle.scanner.models import ScanRow


class ScanResultRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, league: str, rule_version: str, rows: list[ScanRow]) -> None:
        self._conn.executemany(
            "INSERT INTO scan_results "
            "(league, ts, rule_version, transform_id, name, input_cost, output_value, "
            "margin, margin_pct, liquidity, confidence, pricing_mode, source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    league,
                    r.ts.isoformat(),
                    rule_version,
                    r.transform_id,
                    r.name,
                    r.input_cost,
                    r.output_value,
                    r.margin,
                    r.margin_pct,
                    r.liquidity,
                    r.confidence,
                    r.pricing_mode,
                    r.source,
                )
                for r in rows
            ],
        )
        self._conn.commit()

    def recent(self, league: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT * FROM scan_results WHERE league=? ORDER BY ts DESC, id DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_store_scans.py tests/test_store_db.py -v && uv run mypy`
Expected: PASS (existing store test still green — migrations are additive/idempotent), mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/store/scans.py oracle/store/db.py tests/test_store_scans.py
git commit -m "feat: append-only scan_results persistence with migration and repo"
```

---

### Task 6: Report renderer (terminal + markdown + JSON) with auto/verify separation

**Files:**
- Create: `oracle/scanner/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `ScanRow`.
- Produces:
  - `ScanReport(league, snapshot_ts: datetime, rule_version: str, rows: list[ScanRow])` (frozen dataclass) with:
    - `.auto_rows() -> list[ScanRow]` / `.verify_rows() -> list[ScanRow]`.
    - `.to_terminal() -> str` — aligned table, two clearly separated sections (`AUTO-PRICED` then `VERIFY-REQUIRED`), header embedding league + snapshot ts + rule version.
    - `.to_markdown() -> str` — markdown with a metadata block and two tables; verify section shows deep-links.
    - `.to_json() -> str` — JSON dict with `league`, `snapshot_ts`, `rule_version`, and `rows`.
  - `write_report(report: ScanReport, reports_dir: Path) -> tuple[Path, Path]` — writes markdown + JSON to `reports/<league>/YYYY-MM-DD-HHMM.md` and `.json`, returns their paths.

**Notes:** `write_report` sanitizes the league into a filesystem-safe directory segment; the filename derives from `snapshot_ts` (`%Y-%m-%d-%H%M`). Auto rows and verify rows are always visually distinct (separate sections + a `mode` column).

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
import json
from datetime import UTC, datetime
from pathlib import Path

from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport, write_report


def _auto(tid: str, margin: float) -> ScanRow:
    return ScanRow(transform_id=tid, name=f"name-{tid}", input_cost=10.0,
                   output_value=10.0 + margin, margin=margin, margin_pct=margin / 10.0,
                   liquidity=50.0, confidence=0.8, pricing_mode="auto", deep_link=None,
                   source="ninja:x", ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC))


def _verify(tid: str) -> ScanRow:
    return ScanRow(transform_id=tid, name=f"name-{tid}", input_cost=5.0,
                   output_value=None, margin=None, margin_pct=None, liquidity=0.0,
                   confidence=0.0, pricing_mode="verify",
                   deep_link="https://www.pathofexile.com/trade/search/L?q=x",
                   source="unresolved", ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC))


def _report() -> ScanReport:
    return ScanReport(league="L", snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
                      rule_version="sha256:abc",
                      rows=[_auto("big", 30.0), _auto("small", 20.0), _verify("shield")])


def test_splits_auto_and_verify_rows() -> None:
    r = _report()
    assert [x.transform_id for x in r.auto_rows()] == ["big", "small"]
    assert [x.transform_id for x in r.verify_rows()] == ["shield"]


def test_terminal_has_both_sections_and_metadata() -> None:
    text = _report().to_terminal()
    assert "AUTO-PRICED" in text
    assert "VERIFY-REQUIRED" in text
    assert "L" in text
    assert "sha256:abc" in text
    # auto ordering preserved (big before small)
    assert text.index("big") < text.index("small")


def test_markdown_embeds_metadata_and_deeplink() -> None:
    md = _report().to_markdown()
    assert "sha256:abc" in md
    assert "2026-07-18" in md
    assert "https://www.pathofexile.com/trade/search/L?q=x" in md
    assert "AUTO-PRICED" in md and "VERIFY-REQUIRED" in md


def test_json_round_trips_metadata_and_rows() -> None:
    payload = json.loads(_report().to_json())
    assert payload["league"] == "L"
    assert payload["rule_version"] == "sha256:abc"
    assert len(payload["rows"]) == 3


def test_write_report_creates_league_dir_files(tmp_path: Path) -> None:
    md_path, json_path = write_report(_report(), tmp_path)
    assert md_path.exists() and json_path.exists()
    assert md_path.parent.name == "L"
    assert md_path.name == "2026-07-18-1200.md"
    assert json_path.name == "2026-07-18-1200.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL (no module `oracle.scanner.report`).

- [ ] **Step 3: Implement the renderer**

`oracle/scanner/report.py`:
```python
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from oracle.scanner.models import ScanRow


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _safe_segment(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


@dataclass(frozen=True)
class ScanReport:
    league: str
    snapshot_ts: datetime
    rule_version: str
    rows: list[ScanRow]

    def auto_rows(self) -> list[ScanRow]:
        return [r for r in self.rows if r.pricing_mode == "auto"]

    def verify_rows(self) -> list[ScanRow]:
        return [r for r in self.rows if r.pricing_mode == "verify"]

    def _header(self) -> str:
        return (
            f"Oracle Tier-1 Scan — league={self.league} "
            f"snapshot={self.snapshot_ts.isoformat()} rules={self.rule_version}"
        )

    def to_terminal(self) -> str:
        lines = [self._header(), ""]
        lines.append("== AUTO-PRICED ==")
        lines.append(f"{'transform':<32}{'margin':>10}{'margin%':>10}"
                     f"{'liq':>8}{'conf':>7}")
        for r in self.auto_rows():
            pct = "—" if r.margin_pct is None else f"{r.margin_pct * 100:.0f}%"
            lines.append(f"{r.name[:32]:<32}{_fmt(r.margin):>10}{pct:>10}"
                         f"{r.liquidity:>8.0f}{r.confidence:>7.2f}")
        lines.append("")
        lines.append("== VERIFY-REQUIRED (provisional; click to price) ==")
        for r in self.verify_rows():
            lines.append(f"{r.name[:32]:<32}  input≈{_fmt(r.input_cost)}c  "
                         f"{r.deep_link or ''}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"# Oracle Tier-1 Scan — {self.league}",
            "",
            f"- League: `{self.league}`",
            f"- Snapshot: `{self.snapshot_ts.isoformat()}`",
            f"- Transforms rule version: `{self.rule_version}`",
            "",
            "## AUTO-PRICED",
            "",
            "| Transform | Margin (c) | Margin % | Liquidity | Confidence | Source |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for r in self.auto_rows():
            pct = "—" if r.margin_pct is None else f"{r.margin_pct * 100:.0f}%"
            lines.append(f"| {r.name} | {_fmt(r.margin)} | {pct} | "
                         f"{r.liquidity:.0f} | {r.confidence:.2f} | {r.source} |")
        lines += [
            "",
            "## VERIFY-REQUIRED (provisional — click deep-link to price)",
            "",
            "| Transform | Input cost (c) | Deep-link | Source |",
            "|---|---:|---|---|",
        ]
        for r in self.verify_rows():
            link = f"[open]({r.deep_link})" if r.deep_link else "—"
            lines.append(f"| {r.name} | {_fmt(r.input_cost)} | {link} | {r.source} |")
        return "\n".join(lines) + "\n"

    def to_json(self) -> str:
        payload = {
            "league": self.league,
            "snapshot_ts": self.snapshot_ts.isoformat(),
            "rule_version": self.rule_version,
            "rows": [json.loads(r.model_dump_json()) for r in self.rows],
        }
        return json.dumps(payload, indent=2)


def write_report(report: ScanReport, reports_dir: Path) -> tuple[Path, Path]:
    league_dir = reports_dir / _safe_segment(report.league)
    league_dir.mkdir(parents=True, exist_ok=True)
    stem = report.snapshot_ts.strftime("%Y-%m-%d-%H%M")
    md_path = league_dir / f"{stem}.md"
    json_path = league_dir / f"{stem}.json"
    md_path.write_text(report.to_markdown())
    json_path.write_text(report.to_json())
    return md_path, json_path
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_report.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/report.py tests/test_report.py
git commit -m "feat: scan report renderer (terminal/markdown/json) with auto/verify separation"
```

---

### Task 7: ScanService wiring + `oracle scan` CLI + synthetic shield fixture + league-agnostic proof

**Files:**
- Create: `oracle/scanner/service.py`, `tests/test_scan_service.py`, `tests/test_scan_cli.py`, `tests/fixtures/transforms_synthetic_shield.yaml`
- Modify: `oracle/app.py` (add `scan: ScanService` to `Services`, build it), `oracle/cli.py` (add `scan` command)

**Interfaces:**
- Produces (`oracle/scanner/service.py`):
  - `ScanService(engine, repo, rule_version: str, reports_dir: Path, clock)` with:
    - `.run(league: str, min_margin: float | None = None) -> tuple[ScanReport, Path, Path]` — runs the engine, builds a `ScanReport` (embedding league, snapshot ts, rule version), persists rows via `ScanResultRepo.insert_many`, writes report files, returns `(report, md_path, json_path)`.
- Modifies `oracle/app.py`:
  - `Services` gains `scan: ScanService`.
  - `build_services` constructs: `registry = load_registry(DEFAULT_TRANSFORMS_PATH)`; `resolver = PriceResolver(price_service, deep_link_resolver, settings.pricing.min_sample_depth)`; `engine = ScanEngine(registry, resolver, settings.scanner)`; `ScanService(engine, ScanResultRepo(conn), registry.version, Path("reports"), clock=...)`.
- Modifies `oracle/cli.py`:
  - `scan(league: str = typer.Option(...), min_margin: float = typer.Option(None, "--min-margin"), as_json: bool = typer.Option(False, "--json"))`.

**Notes:** `build_services` reuses the single `conn` and the Phase 0 `PriceService`/`DeepLinkResolver`. The CLI keeps the `_services()` indirection so tests monkeypatch it. No new HTTP host is introduced (compliance unchanged).

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/transforms_synthetic_shield.yaml` (a known shield-class margin the scan MUST detect — PRD DoD allows a synthetic fixture):
```yaml
# Synthetic fixture: a shield-class transform with a KNOWN positive margin,
# priced entirely auto so the engine can prove end-to-end detection without
# live-league margins. league appears in metadata only (test uses an invented id).
transforms:
  - id: synthetic_shaper_shield
    name: "Synthetic shaper shield (plain base + orb -> influenced base)"
    inputs:
      - {category: BaseType, key: "Plain Shield Base", qty: 1.0}
      - {category: Currency, key: "Shaper's Orb", qty: 1.0}
    output: {category: BaseType, key: "Shaper Shield Base", qty: 1.0}
    applicability: "synthetic; both sides auto-priced for deterministic detection"
    friction: 0.0
    enabled: true
    pricing_mode: auto
```

`tests/test_scan_service.py`:
```python
from datetime import UTC, datetime
from pathlib import Path

from oracle.config import ScannerSettings
from oracle.models import ListingQuote, Price
from oracle.scanner.engine import ScanEngine
from oracle.scanner.registry import load_registry
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.service import ScanService
from oracle.store.db import connect
from oracle.store.scans import ScanResultRepo

FIX = Path(__file__).parent / "fixtures"


class SyntheticPriceService:
    """Prices the synthetic shield fixture so the KNOWN margin is detectable."""

    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        table = {
            ("BaseType", "Plain Shield Base"): (5.0, 40),
            ("Currency", "Shaper's Orb"): (10.0, 60),
            ("BaseType", "Shaper Shield Base"): (80.0, 30),  # margin = 80-5-10 = 65
        }
        return [
            Price(key=key, league=league, category=category, chaos_value=val,
                  sample_depth=depth, source=f"ninja:{category}", confidence=0.8, ts=now)
            for (cat, key), (val, depth) in table.items()
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


def _service(tmp_path: Path) -> ScanService:
    reg = load_registry(FIX / "transforms_synthetic_shield.yaml")
    resolver = PriceResolver(SyntheticPriceService(), NullDeepLink(), min_sample_depth=5)
    engine = ScanEngine(reg, resolver, ScannerSettings(min_margin=15.0, min_liquidity=5.0),
                        clock=_clock)
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    return ScanService(engine, repo, reg.version, tmp_path / "reports", clock=_clock)


def test_scan_detects_known_shield_margin(tmp_path: Path) -> None:
    report, md, js = _service(tmp_path).run("SynthLeague")
    shield = next(r for r in report.rows if r.transform_id == "synthetic_shaper_shield")
    assert shield.margin == 65.0
    assert md.exists() and js.exists()


def test_scan_persists_rows(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.run("SynthLeague")
    # repo is internal; re-run and assert files accumulate + persistence didn't raise
    report, _, _ = svc.run("SynthLeague")
    assert report.rule_version.startswith("sha256:")


def test_same_scan_runs_against_second_league_no_code_change(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    r1, _, _ = svc.run("InventedLeagueOne")
    r2, _, _ = svc.run("InventedLeagueTwo")
    assert r1.league == "InventedLeagueOne"
    assert r2.league == "InventedLeagueTwo"
    m1 = next(r.margin for r in r1.rows if r.transform_id == "synthetic_shaper_shield")
    m2 = next(r.margin for r in r2.rows if r.transform_id == "synthetic_shaper_shield")
    assert m1 == m2 == 65.0  # identical logic, different runtime league param
```

`tests/test_scan_cli.py`:
```python
from datetime import UTC, datetime

from typer.testing import CliRunner

from oracle.cli import app
from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport

runner = CliRunner()


class FakeScanService:
    def run(self, league, min_margin=None):  # type: ignore[no-untyped-def]
        row = ScanRow(transform_id="big", name="Big Play", input_cost=10.0,
                      output_value=75.0, margin=65.0, margin_pct=6.5, liquidity=40.0,
                      confidence=0.8, pricing_mode="auto", deep_link=None,
                      source="ninja:Fossil", ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC))
        report = ScanReport(league=league, snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
                            rule_version="sha256:abc", rows=[row])
        return report, None, None


class FakeServices:
    scan = FakeScanService()


def test_scan_command_prints_table(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["scan", "--league", "InventedLeague"])
    assert result.exit_code == 0
    assert "AUTO-PRICED" in result.stdout
    assert "Big Play" in result.stdout
    assert "InventedLeague" in result.stdout


def test_scan_command_json(monkeypatch) -> None:
    import oracle.cli as cli
    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["scan", "--league", "InventedLeague", "--json"])
    assert result.exit_code == 0
    assert '"rule_version"' in result.stdout
    assert "sha256:abc" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scan_service.py tests/test_scan_cli.py -v`
Expected: FAIL (no module `oracle.scanner.service`; no `scan` command; `Services` has no `scan`).

- [ ] **Step 3: Implement service + wire app + CLI**

`oracle/scanner/service.py`:
```python
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from oracle.scanner.engine import ScanEngine
from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport, write_report


class _Repo(Protocol):
    def insert_many(self, league: str, rule_version: str, rows: list[ScanRow]) -> None: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class ScanService:
    def __init__(
        self,
        engine: ScanEngine,
        repo: _Repo,
        rule_version: str,
        reports_dir: Path,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._rule_version = rule_version
        self._reports_dir = reports_dir
        self._clock = clock

    def run(
        self, league: str, min_margin: float | None = None
    ) -> tuple[ScanReport, Path, Path]:
        snapshot_ts = self._clock()
        rows = self._engine.scan(league, min_margin)
        report = ScanReport(
            league=league,
            snapshot_ts=snapshot_ts,
            rule_version=self._rule_version,
            rows=rows,
        )
        self._repo.insert_many(league, self._rule_version, rows)
        md_path, json_path = write_report(report, self._reports_dir)
        return report, md_path, json_path
```

Modify `oracle/app.py` — add the import block and `scan` field, and build it:
```python
from oracle.scanner.engine import ScanEngine
from oracle.scanner.registry import DEFAULT_TRANSFORMS_PATH, load_registry
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.service import ScanService
from oracle.store.scans import ScanResultRepo
```
Add to `class Services`:
```python
    scan: ScanService
```
In `build_services`, after `price = PriceService(...)` is available (construct it into a local first), assemble the scanner and pass everything to `Services`. Replace the return block with:
```python
def build_services(settings: Settings | None = None) -> Services:
    settings = settings or load_settings()
    http = HttpClient(settings.user_agent, HTTP_ALLOWED_HOSTS)
    ninja = NinjaClient(http)
    conn = connect(settings.store.db_path)
    gamedata = GameDataService.from_snapshot(Path("snapshots/repoe"))
    price = PriceService(ninja, conn, settings)
    resolver = DeepLinkResolver(
        ObservedPriceRepo(conn), settings.cache.observed_price_ttl_seconds
    )
    registry = load_registry(DEFAULT_TRANSFORMS_PATH)
    scan_resolver = PriceResolver(price, resolver, settings.pricing.min_sample_depth)
    engine = ScanEngine(registry, scan_resolver, settings.scanner)
    scan = ScanService(engine, ScanResultRepo(conn), registry.version, Path("reports"))
    return Services(
        settings=settings,
        league=LeagueService(http, ninja_probe=ninja.league_is_covered),
        gamedata=gamedata,
        price=price,
        resolver=resolver,
        scan=scan,
    )
```

Add to `oracle/cli.py` (a new command; keep everything else):
```python
@app.command()
def scan(
    league: str = typer.Option(...),
    min_margin: float = typer.Option(None, "--min-margin"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run the Tier-1 scanner for a league; write report files and print the table."""
    report, _md, _json = _services().scan.run(league, min_margin)
    if as_json:
        typer.echo(report.to_json())
        return
    typer.echo(report.to_terminal())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_scan_service.py tests/test_scan_cli.py tests/test_cli_commands.py -v && uv run mypy`
Expected: PASS (including the existing CLI-command test — `Services` now has `scan` but the fake in that test only touches `.league`/`.gamedata`), mypy clean.

- [ ] **Step 5: Commit**

```bash
git add oracle/scanner/service.py oracle/app.py oracle/cli.py tests/test_scan_service.py tests/test_scan_cli.py tests/fixtures/transforms_synthetic_shield.yaml
git commit -m "feat: ScanService + 'oracle scan' CLI; synthetic shield-detection + league-agnostic tests"
```

---

### Task 8: Compliance re-check, live smoke scan, and Phase 1 DoD verification

**Files:**
- Create: `tests/test_scan_live_smoke.py`, `docs/phase1-dod.md`
- (No source changes; this task verifies the whole phase.)

**Interfaces:**
- Consumes: the full built services (real network, marked `@pytest.mark.live`, skipped in CI); the existing `tests/test_compliance.py`.

- [ ] **Step 1: Confirm compliance guards still pass**

Run: `uv run pytest tests/test_compliance.py -v`
Expected: PASS. Specifically:
- `test_no_trade_api_string_in_source` — the scanner uses `TRADE_SITE_BASE` (the human-facing `/trade/search` site path) only via the Phase 0 `DeepLinkResolver`; no scanner source file contains `/api/trade/`.
- `test_no_hardcoded_league_name_in_source` — no `\bStandard\b` in `oracle/scanner/**`. (League ids in tests/fixtures are invented, e.g. `SynthLeague`, `InventedLeagueOne`.)

If either fails, fix the offending source (move any league default to `config/settings.toml`; route any listing lookup through `DeepLinkResolver`) — do NOT weaken the guard test.

- [ ] **Step 2: Write the live smoke scan**

`tests/test_scan_live_smoke.py`:
```python
import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_scan_runs_against_default_league_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    report, md_path, json_path = svc.scan.run(default)
    assert report.league == default
    assert report.rule_version.startswith("sha256:")
    assert md_path.exists() and json_path.exists()
    # auto rows, when present, must be ranked by margin descending
    margins = [r.margin for r in report.auto_rows() if r.margin is not None]
    assert margins == sorted(margins, reverse=True)


def test_scan_runs_against_second_live_league_no_code_change() -> None:
    svc = build_services()
    live = [lg for lg in svc.league.list_leagues() if lg.ninja_available]
    if len(live) < 2:
        pytest.skip("need >=2 ninja-covered leagues to prove league-agnosticism live")
    for lg in live[:2]:
        report, _, _ = svc.scan.run(lg.id)
        assert report.league == lg.id
```

- [ ] **Step 3: Run the live smoke locally**

Run: `uv run pytest -m live tests/test_scan_live_smoke.py -v`
Expected: PASS against live data; a full scan completes well under the 10-min budget (the seed's auto categories are each fetched once). This is a local DoD gate, not CI.

- [ ] **Step 4: Manual DoD checklist** (record results in `docs/phase1-dod.md`)

- `uv run oracle scan --league <a-live-league>` completes in <10 min and prints a ranked table with an `AUTO-PRICED` and a `VERIFY-REQUIRED` section; report files written to `reports/<league>/`.
- Zac judges the top-10 auto-priced rows sane (no obviously fake-price-driven entries).
- The shield-class pattern is detected end-to-end: on live data if margins exist, else via the synthetic fixture test (`tests/test_scan_service.py::test_scan_detects_known_shield_margin`), which asserts the known 65c margin.
- `uv run oracle scan --league <a-second-live-league>` works with zero code changes.
- Each report embeds league + snapshot ts + transforms rule-file version; each row carries source + confidence.

- [ ] **Step 5: Full suite + quality gates**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest --cov=oracle --cov-report=term-missing`
Expected: all green; scanner coverage healthy.

- [ ] **Step 6: Commit + push**

```bash
git add tests/test_scan_live_smoke.py docs/phase1-dod.md
git commit -m "test: live smoke scan and Phase 1 DoD verification notes"
git push
```

---

## Self-Review

**PRD §Phase 1 deliverables → tasks:**
- Transform registry `data/transforms_t1.yaml` (id, name, inputs, output, applicability, friction, enabled, patch-validity, pricing mode; ~20 seed biased to `auto`; socket/link entries disabled) → **Task 2** (+ models in Task 1). ✓
- Scan engine (resolve input bundle + output via Price Service; margin + margin %; liquidity + confidence; verify-mode provisional ranking + deep-link) → **Task 3** (resolve) + **Task 4** (engine). ✓
- Report output (ranked terminal + markdown `reports/<league>/YYYY-MM-DD-HHMM.md` + JSON; auto vs verify visually distinct; per-opportunity detail: margin after friction, liquidity, confidence, deep-link) → **Task 6** (renderer) + **Task 7** (writes files via ScanService). ✓
- Scheduling (league-parameterized; each run persists results for margin-decay analysis) → **Task 5** (append-only `scan_results`) + **Task 7** (`oracle scan --league` is the cron/systemd entrypoint; persistence on every run). ✓

**PRD §Phase 1 DoD → coverage:**
- Full scan <10 min, sane top-10 → **Task 8** live smoke + manual checklist (per-scan category caching in Task 3 keeps fetches minimal). ✓
- Shield-class pattern detected end-to-end (live or synthetic fixture) → **Task 7** `test_scan_detects_known_shield_margin` (synthetic fixture, known 65c margin) + **Task 8** live path. ✓
- Same scan against a second live league, no code changes → **Task 7** `test_same_scan_runs_against_second_league_no_code_change` + **Task 8** `test_scan_runs_against_second_live_league_no_code_change`. ✓

**Global-constraint coverage:**
- Compliance UNCHANGED (only ninja + league API fetched; no `/api/trade/*`; specific listings only via `DeepLinkResolver`) → verify sides route through Phase 0 `DeepLinkResolver`; **Task 8** re-runs `tests/test_compliance.py`. ✓
- League always a runtime param; no hardcoded league in source → all scan APIs take `league`; only fixtures use invented ids; guard test re-run in Task 8. ✓
- Rules as data with Pydantic validation, fail-loud → **Task 2** (`extra="forbid"`, `TransformRegistryError`). ✓
- Reproducibility (source attribution, confidence, timestamps per row; reports embed league + snapshot ts + rule-file version) → **Tasks 1, 4, 6, 7**. ✓
- mypy strict inheritance → all logic under `oracle/scanner/` (no `[tool.mypy] files` change). ✓
- Tests live-marked → **Task 8**. ✓

**Type consistency:** `PriceRef`/`Transform`/`ScanRow` in `oracle/scanner/models.py`; `ResolvedPrice` in `resolve.py`; `TransformRegistry` in `registry.py`; `ScanReport` in `report.py`; `ScannerSettings` on `oracle.config.Settings`. The `_Resolver` Protocol consumed by `ScanEngine` (Task 4) is satisfied by `PriceResolver` (Task 3: `clear_cache`/`resolve_auto`/`resolve_verify`). The `_Repo` Protocol in `ScanService` (Task 7) is satisfied by `ScanResultRepo.insert_many` (Task 5). `PriceResolver` consumes the real `PriceService.prices` and `DeepLinkResolver.resolve` (exact Phase 0 signatures).

**Placeholder scan:** No "TBD"/"similar to Task N" left; all code is complete. The seed transform prices/keys are illustrative-by-design (re-validated on patch day per PRD rules-as-data), and DoD shield detection is proven by the synthetic fixture, not by any live-margin assumption.

**Task ordering (dependencies):** 1 (models/config) → 2 (registry) → 3 (resolve) → 4 (engine, needs registry+resolve) → 5 (persistence, independent, before 7) → 6 (report, independent, before 7) → 7 (service+CLI, needs 2/3/4/5/6) → 8 (compliance/live/DoD, needs all).
