"""Vendor-recipe metadata: pure HTML parser, fail-loud loader, transform expander.

The parser is a pure `str -> list[VendorRecipe]` function so it is unit-testable
against a pinned poedb fixture with no network (see ADR-0003: brittleness is handled
once, at a boundary that fails loud). The runtime never fetches poedb; the dev-time
harvester (`tools/harvest_vendor_recipes.py`) supplies the HTML.
"""

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from oracle.metadata.models import VendorRecipe, VendorRecipeDoc, VendorRecipeItem
from oracle.scanner.models import PriceRef, Transform

DEFAULT_VENDOR_RECIPES_PATH = Path("data/metadata/vendor_recipes.yaml")
CURRENCY_CATEGORY = "Currency"


class VendorRecipeError(Exception):
    """Raised when the vendor-recipe metadata file has an unknown or invalid shape."""


# --- pure HTML parser -------------------------------------------------------

_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_QTY_RE = re.compile(r"(\d+)\s*x", re.I)


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", fragment)).strip()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _parse_cell(cell: str) -> tuple[list[VendorRecipeItem], list[bool]]:
    """Extract currency items from a table cell.

    Returns (items, is_currency_flags). A quantity is the ``Nx`` token appearing in the
    text immediately before each anchor (default 1).
    """
    items: list[VendorRecipeItem] = []
    currency_flags: list[bool] = []
    pos = 0
    for m in _ANCHOR_RE.finditer(cell):
        preceding = _strip_tags(cell[pos : m.start()])
        qm = _QTY_RE.search(preceding)
        qty = float(qm.group(1)) if qm else 1.0
        attrs, inner = m.group(1), m.group(2)
        name = _strip_tags(inner)
        if name:
            items.append(VendorRecipeItem(name=name, qty=qty))
            currency_flags.append("item_currency" in attrs)
        pos = m.end()
    return items, currency_flags


def _residual_has_words(cell: str, items: list[VendorRecipeItem]) -> bool:
    """True if the cell carries non-item text (e.g. '6 Sockets') beyond its currencies."""
    text = _strip_tags(cell)
    text = _QTY_RE.sub("", text)
    for it in items:
        text = text.replace(it.name, "")
    return bool(re.sub(r"[^A-Za-z]", "", text))


def parse_vendor_recipes_html(html: str) -> list[VendorRecipe]:
    """Parse poedb's Vendor_recipe_system page into currency-for-currency recipes.

    Columns are Offer (received) | Your Offer (given, with Nx qty) | Note (NPC). Only
    rows whose Offer and Your Offer are purely currency items are kept; conditional
    recipes (e.g. '6 Sockets') and non-currency legs are skipped.
    """
    recipes: list[VendorRecipe] = []
    seen: set[str] = set()
    for tr in _TR_RE.finditer(html):
        cells = _TD_RE.findall(tr.group(1))
        if len(cells) < 2:
            continue
        offer_items, offer_flags = _parse_cell(cells[0])
        give_items, give_flags = _parse_cell(cells[1])
        note = _strip_tags(cells[2]) if len(cells) >= 3 else ""
        if len(offer_items) != 1 or not give_items:
            continue
        if not (all(offer_flags) and all(give_flags)):
            continue
        if _residual_has_words(cells[0], offer_items) or _residual_has_words(cells[1], give_items):
            continue
        output = offer_items[0]
        rid = _slug(output.name) + "_from_" + "_".join(_slug(i.name) for i in give_items)
        if rid in seen:
            continue
        seen.add(rid)
        recipes.append(VendorRecipe(id=rid, output=output, inputs=give_items, npc=note))
    return recipes


# --- loader + expander ------------------------------------------------------


def load_vendor_recipes(path: Path) -> tuple[VendorRecipeDoc, str]:
    """Load and validate the metadata file; return (doc, sha256-version). Fail loud."""
    raw = path.read_bytes()
    version = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]
    try:
        doc_raw = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise VendorRecipeError(f"invalid YAML: {exc}") from exc
    if not isinstance(doc_raw, dict):
        raise VendorRecipeError("top-level document must be a mapping")
    try:
        doc = VendorRecipeDoc.model_validate(doc_raw)
    except ValidationError as exc:
        raise VendorRecipeError(f"invalid vendor-recipe document: {exc}") from exc
    ids = [r.id for r in doc.recipes]
    if len(ids) != len(set(ids)):
        raise VendorRecipeError("duplicate recipe ids in vendor-recipe document")
    return doc, version


def _qty_label(qty: float) -> str:
    return str(int(qty)) if qty.is_integer() else str(qty)


def expand_vendor_recipes(doc: VendorRecipeDoc) -> list[Transform]:
    """Turn cited currency vendor recipes into auto-priced Tier-1 transforms."""
    out: list[Transform] = []
    for r in doc.recipes:
        inputs = [PriceRef(category=CURRENCY_CATEGORY, key=i.name, qty=i.qty) for i in r.inputs]
        output = PriceRef(category=CURRENCY_CATEGORY, key=r.output.name, qty=r.output.qty)
        given = " + ".join(f"{_qty_label(i.qty)}x {i.name}" for i in r.inputs)
        note = f" (NPC: {r.npc})" if r.npc else ""
        out.append(
            Transform(
                id=f"vendor::{r.id}",
                name=f"Vendor: {r.output.name} <- {given}",
                inputs=inputs,
                output=output,
                applicability=f"poedb currency vendor recipe{note}",
                friction=0.0,
                enabled=True,
                pricing_mode="auto",
            )
        )
    return out
