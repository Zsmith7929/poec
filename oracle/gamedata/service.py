import json
from pathlib import Path

from oracle.gamedata.schema import RepoeMod
from oracle.models import Mod


class GameDataService:
    def __init__(
        self,
        version: str,
        mods: dict[str, RepoeMod],
        base_tags: dict[str, list[str]],
    ) -> None:
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
            base_tags = {b["name"]: b.get("tags", []) for b in raw_bases.values()}
        version = manifest.get("fetched_at", "unknown")
        return cls(version, mods, base_tags)

    def snapshot_version(self) -> str:
        return self._version

    def mod_pool(
        self,
        base: str,
        ilvl: int,
        influence: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Mod]:
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
                Mod(
                    id=mid,
                    name=m.name,
                    weight=weight,
                    group=m.group,
                    tags=m.tags,
                    domain=m.domain,
                    generation_type=m.generation_type,
                    required_level=m.required_level,
                )
            )
        return result
