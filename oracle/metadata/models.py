"""Cited metadata models (recipe/fact side; poedb-sourced). See ADR-0001/0002.

These describe *what a recipe is*, sourced from poedb, kept strictly separate from
price data (poe.ninja). Every document carries a citation so a fact can always be
traced back to its source and refreshed on patch day.
"""

from pydantic import BaseModel, ConfigDict


class MetadataSource(BaseModel):
    """Provenance for a harvested metadata document."""

    model_config = ConfigDict(extra="forbid")

    url: str
    fetched_at: str  # ISO-8601 date/datetime of the harvest run
    page_sha256: str  # sha256 of the source page bytes at harvest time


class VendorRecipeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str  # display name; must match the poe.ninja Currency feed key
    qty: float = 1.0


class VendorRecipe(BaseModel):
    """A currency-for-currency vendor recipe: give `inputs`, receive `output`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    output: VendorRecipeItem
    inputs: list[VendorRecipeItem]
    npc: str = ""


class VendorRecipeDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: MetadataSource
    recipes: list[VendorRecipe]


class DivCard(BaseModel):
    """A divination card: turn in `set_size` copies, receive `reward_qty`x `reward_name`.
    `reward_kind` (currency/unique/other) is classified from poedb and routes pricing."""

    model_config = ConfigDict(extra="forbid")

    name: str
    set_size: int
    reward_name: str
    reward_qty: float = 1.0
    reward_kind: str  # "currency" | "unique" | "other"


class DivCardDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: MetadataSource
    cards: list[DivCard]
