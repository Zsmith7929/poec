from pydantic import BaseModel, model_validator


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

    @model_validator(mode="before")
    @classmethod
    def _normalise_repoe_fields(cls, values: object) -> object:
        """Map real RePoE field names to the canonical schema fields.

        RePoE publishes ``groups`` (a list) and ``implicit_tags`` (a list)
        rather than the singular ``group`` and ``tags`` used internally.
        Accept both forms so the schema works against the live snapshot.
        """
        if not isinstance(values, dict):
            return values
        # groups (list) -> group (first element, required)
        if "group" not in values and "groups" in values:
            groups: list[str] = values["groups"]
            if not groups:
                raise ValueError("'groups' list is empty; cannot derive 'group'")
            values = {**values, "group": groups[0]}
        # implicit_tags -> tags (fall back to empty list)
        if "tags" not in values:
            values = {**values, "tags": values.get("implicit_tags", [])}
        return values
