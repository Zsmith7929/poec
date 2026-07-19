"""Divination-card metadata: pure HTML parser, fail-loud loader, transform expander.

See ADR-0006. The runtime never fetches poedb; the dev-time harvester
(`tools/harvest_divination_cards.py`) supplies the HTML. The card leg prices via the
poe.ninja DivinationCard exchange feed; the reward leg prices by name across kind-scoped
feeds via sentinel PriceRef categories (RewardCurrency / RewardUnique).
"""

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from oracle.metadata.models import DivCard, DivCardDoc
from oracle.scanner.models import PriceRef, Transform

DEFAULT_DIVINATION_CARDS_PATH = Path("data/metadata/divination_cards.yaml")
DIVINATION_CARD_CATEGORY = "DivinationCard"
# Sentinel output categories the resolver maps to kind-scoped feed lists (ADR-0006).
REWARD_CURRENCY_CATEGORY = "RewardCurrency"
REWARD_UNIQUE_CATEGORY = "RewardUnique"

_KIND_BY_SPAN = {"currencyitem": "currency", "uniqueitem": "unique"}


class DivCardError(Exception):
    """Raised when the divination-card metadata file has an invalid shape."""


# --- pure HTML parser -------------------------------------------------------

# Card row on poedb's Divination_Cards index: the card anchor, then a property block with
# "Stack Size: 1 / N", then the reward in an explicitMod span whose class gives the kind.
_CARD_RE = re.compile(
    r">([^<]+)</a><div><div class=\"property\">Stack Size:\s*"
    r"<span[^>]*>1 / (\d+)</span></div>"
    r"<div class=\"separator\"></div><div class=\"explicitMod\">(.*?)</div>",
    re.S,
)
_SPAN_RE = re.compile(r"<span class=\"([a-z]+)\"[^>]*>([^<]+)</span>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_QTY_RE = re.compile(r"(\d+)\s*x", re.I)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def parse_divination_cards_html(html: str) -> list[DivCard]:
    """Parse poedb's Divination_Cards index into cards with set size + reward + kind."""
    flat = re.sub(r"\s+", " ", html)
    cards: list[DivCard] = []
    seen: set[str] = set()
    for m in _CARD_RE.finditer(flat):
        name = m.group(1).strip()
        set_size = int(m.group(2))
        reward_inner = m.group(3)
        span = _SPAN_RE.search(reward_inner)
        if not span:
            continue  # reward not a single named item (skip; recorded as unparseable)
        kind = _KIND_BY_SPAN.get(span.group(1).lower(), "other")
        reward_name = span.group(2).strip()
        # The "Nx" quantity may be inline in the span text ("13x Orb of Alteration") or
        # in the text preceding the span ("10x <span>Chaos Orb</span>"). Inline is the
        # common real-page shape; check it first, else fall back to the preceding text.
        inline = re.match(r"(\d+)\s*x\s+", reward_name, re.I)
        if inline:
            reward_qty = float(inline.group(1))
            reward_name = reward_name[inline.end() :].strip()
        else:
            preceding = _TAG_RE.sub("", reward_inner[: span.start()])
            qm = _QTY_RE.search(preceding)
            reward_qty = float(qm.group(1)) if qm else 1.0
        if name in seen:
            continue
        seen.add(name)
        cards.append(
            DivCard(
                name=name,
                set_size=set_size,
                reward_name=reward_name,
                reward_qty=reward_qty,
                reward_kind=kind,
            )
        )
    return cards


# --- loader + expander ------------------------------------------------------


def load_divination_cards(path: Path) -> tuple[DivCardDoc, str]:
    """Load and validate the metadata file; return (doc, sha256-version). Fail loud."""
    raw = path.read_bytes()
    version = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]
    try:
        doc_raw = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DivCardError(f"invalid YAML: {exc}") from exc
    if not isinstance(doc_raw, dict):
        raise DivCardError("top-level document must be a mapping")
    try:
        doc = DivCardDoc.model_validate(doc_raw)
    except ValidationError as exc:
        raise DivCardError(f"invalid divination-card document: {exc}") from exc
    names = [c.name for c in doc.cards]
    if len(names) != len(set(names)):
        raise DivCardError("duplicate card names in divination-card document")
    return doc, version


def _reward_category(kind: str) -> str | None:
    if kind == "currency":
        return REWARD_CURRENCY_CATEGORY
    if kind == "unique":
        return REWARD_UNIQUE_CATEGORY
    return None  # other kinds (bases/gems/maps/multi-item) not emitted in v1 (ADR-0006)


def expand_divination_cards(doc: DivCardDoc) -> list[Transform]:
    """Turn cited cards into auto-priced transforms (currency/unique rewards only)."""
    out: list[Transform] = []
    for c in doc.cards:
        reward_cat = _reward_category(c.reward_kind)
        if reward_cat is None:
            continue
        qty_label = str(int(c.reward_qty)) if c.reward_qty.is_integer() else str(c.reward_qty)
        reward_label = c.reward_name if c.reward_qty == 1.0 else f"{qty_label}x {c.reward_name}"
        out.append(
            Transform(
                id=f"divcard::{_slug(c.name)}",
                name=f"Div card: {c.set_size}x {c.name} -> {reward_label}",
                inputs=[
                    PriceRef(category=DIVINATION_CARD_CATEGORY, key=c.name, qty=float(c.set_size))
                ],
                output=PriceRef(category=reward_cat, key=c.reward_name, qty=c.reward_qty),
                applicability=f"poedb divination card set ({c.reward_kind} reward)",
                friction=0.0,
                enabled=True,
                pricing_mode="auto",
            )
        )
    return out
