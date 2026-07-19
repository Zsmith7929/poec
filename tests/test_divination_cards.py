from pathlib import Path

import pytest

from oracle.metadata.divination_cards import (
    DivCardError,
    expand_divination_cards,
    load_divination_cards,
    parse_divination_cards_html,
)
from oracle.metadata.models import DivCard, DivCardDoc, MetadataSource

FIX = Path(__file__).parent / "fixtures" / "poedb_divination_cards.html"


# --- parser (pinned fixture) ------------------------------------------------


def test_parser_extracts_set_size_reward_and_kind() -> None:
    cards = {c.name: c for c in parse_divination_cards_html(FIX.read_text())}
    hom = cards["House of Mirrors"]
    assert hom.set_size == 9 and hom.reward_name == "Mirror of Kalandra"
    assert hom.reward_kind == "currency" and hom.reward_qty == 1.0
    doc = cards["The Doctor"]
    assert doc.set_size == 8 and doc.reward_name == "Headhunter" and doc.reward_kind == "unique"


def test_parser_reads_reward_quantity_before_span() -> None:
    cards = {c.name: c for c in parse_divination_cards_html(FIX.read_text())}
    rain = cards["Rain of Chaos"]
    assert rain.reward_name == "Chaos Orb" and rain.reward_qty == 10.0


def test_parser_reads_reward_quantity_inline_in_span() -> None:
    # Real poedb puts the multiplier INSIDE the span ("13x Orb of Alteration"); the qty
    # must be split out of the name, else the reward never name-matches a feed line.
    cards = {c.name: c for c in parse_divination_cards_html(FIX.read_text())}
    sea = cards["A Sea of Blue"]
    assert sea.reward_name == "Orb of Alteration" and sea.reward_qty == 13.0


def test_parser_classifies_noncurrency_nonunique_as_other() -> None:
    cards = {c.name: c for c in parse_divination_cards_html(FIX.read_text())}
    assert cards["A Chilling Wind"].reward_kind == "other"


def test_parser_captures_reward_variant_prefix() -> None:
    # poedb trails the reward with a "{Foulborn}" variant tag; poe.ninja prefixes it.
    # Dropping it prices the clean item instead of the actual (variant) reward.
    cards = {c.name: c for c in parse_divination_cards_html(FIX.read_text())}
    eot = cards["The Eye of Terror"]
    assert eot.reward_name == "Foulborn Mageblood" and eot.reward_kind == "unique"


# --- loader -----------------------------------------------------------------


def _doc_yaml() -> str:
    return (
        "source: {url: u, fetched_at: '2026-07-19', page_sha256: s}\n"
        "cards:\n"
        "  - {name: The Doctor, set_size: 8, reward_name: Headhunter, reward_qty: 1.0, "
        "reward_kind: unique}\n"
    )


def test_loads_and_versions(tmp_path: Path) -> None:
    p = tmp_path / "d.yaml"
    p.write_text(_doc_yaml())
    doc, version = load_divination_cards(p)
    assert isinstance(doc, DivCardDoc) and version.startswith("sha256:")
    assert doc.cards[0].reward_name == "Headhunter"


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "source: {url: u, fetched_at: d, page_sha256: s}\ncards:\n  - {name: X, junk: 1}\n"
    )
    with pytest.raises(DivCardError):
        load_divination_cards(bad)


def test_duplicate_names_fail_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(_doc_yaml() + _doc_yaml().split("cards:\n")[1])
    with pytest.raises(DivCardError):
        load_divination_cards(bad)


# --- expander ---------------------------------------------------------------


def _doc(*cards: DivCard) -> DivCardDoc:
    return DivCardDoc(
        source=MetadataSource(url="u", fetched_at="2026-07-19", page_sha256="s"),
        cards=list(cards),
    )


def test_expand_emits_currency_and_unique_routes_by_kind() -> None:
    doc = _doc(
        DivCard(
            name="House of Mirrors",
            set_size=9,
            reward_name="Mirror of Kalandra",
            reward_kind="currency",
        ),
        DivCard(name="The Doctor", set_size=8, reward_name="Headhunter", reward_kind="unique"),
    )
    ts = {t.id: t for t in expand_divination_cards(doc)}
    mirror = ts["divcard::house_of_mirrors"]
    assert mirror.inputs[0].category == "DivinationCard"
    assert mirror.inputs[0].key == "House of Mirrors" and mirror.inputs[0].qty == 9.0
    assert mirror.output.category == "RewardCurrency" and mirror.output.key == "Mirror of Kalandra"
    hh = ts["divcard::the_doctor"]
    assert hh.output.category == "RewardUnique" and hh.output.key == "Headhunter"


def test_expand_skips_other_kind_rewards() -> None:
    doc = _doc(
        DivCard(
            name="A Chilling Wind",
            set_size=4,
            reward_name="Level 21 Vaal Cold Snap",
            reward_kind="other",
        ),
    )
    assert expand_divination_cards(doc) == []
