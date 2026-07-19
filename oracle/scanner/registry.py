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
