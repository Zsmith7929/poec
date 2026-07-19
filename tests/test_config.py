from pathlib import Path

from oracle.config import Settings, load_settings


def test_loads_default_settings_file() -> None:
    settings = load_settings(Path("config/settings.toml"))
    assert isinstance(settings, Settings)
    assert settings.default_league == "Standard"
    assert 0.0 < settings.pricing.percentile < 1.0
    assert settings.cache.ninja_ttl_seconds > 0
    assert settings.store.db_path.endswith(".db")


def test_rejects_out_of_range_percentile(tmp_path: Path) -> None:
    bad = tmp_path / "s.toml"
    bad.write_text(
        'default_league="X"\nrealm="pc"\nuser_agent="ua"\n'
        "[pricing]\npercentile=2.0\noutlier_z=3.0\nmin_sample_depth=5\n"
        "[cache]\nninja_ttl_seconds=1\nleague_ttl_seconds=1\nobserved_price_ttl_seconds=1\n"
        '[store]\ndb_path="x.db"\n'
    )
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_settings(bad)
