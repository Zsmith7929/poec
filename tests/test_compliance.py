import re
from pathlib import Path

import pytest

from oracle.http.client import ComplianceError, HttpClient

_ROOT = Path(__file__).parent.parent
SRC_DIRS = [_ROOT / "oracle", _ROOT / "scanner", _ROOT / "advisor"]


def test_http_client_blocks_trade_api() -> None:
    client = HttpClient("ua", {"api.pathofexile.com", "poe.ninja"})
    with pytest.raises(ComplianceError):
        client.get_json("https://www.pathofexile.com/api/trade/search/Standard")


def test_no_trade_api_string_in_source() -> None:
    offenders = []
    for d in SRC_DIRS:
        for py in d.rglob("*.py"):
            text = py.read_text()
            if "/api/trade/" in text:
                offenders.append(str(py))
    assert not offenders, f"/api/trade/ referenced in: {offenders}"


def test_src_dirs_resolve_files() -> None:
    total = sum(1 for d in SRC_DIRS for _ in d.rglob("*.py"))
    assert total > 0, "SRC_DIRS resolved no .py files — compliance greps would vacuously pass"


def test_no_hardcoded_league_name_in_source() -> None:
    # "Standard" (and other league names) must not be hardcoded in code.
    offenders = []
    for d in SRC_DIRS:
        for py in d.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if re.search(r"\bStandard\b", line):
                    offenders.append(f"{py}:{i}")
    assert not offenders, f"hardcoded league name in: {offenders}"
