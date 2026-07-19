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
