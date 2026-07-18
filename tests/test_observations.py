from datetime import UTC, datetime, timedelta

from oracle.store.db import connect
from oracle.store.observations import ObservedPriceRepo


def test_record_and_latest_within_ttl(tmp_path) -> None:
    repo = ObservedPriceRepo(connect(str(tmp_path / "t.db")))
    now = datetime.now(tz=UTC).isoformat()
    repo.record("TestLeagueA", "abc", 55.0, now)
    got = repo.latest("TestLeagueA", "abc", ttl_seconds=3600)
    assert got is not None and got[0] == 55.0


def test_expired_observation_returns_none(tmp_path) -> None:
    repo = ObservedPriceRepo(connect(str(tmp_path / "t.db")))
    old = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    repo.record("TestLeagueA", "abc", 55.0, old)
    assert repo.latest("TestLeagueA", "abc", ttl_seconds=3600) is None
