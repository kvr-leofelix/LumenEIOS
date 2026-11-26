"""Safety boundaries of the opt-in persistent acceptance launcher."""
import sys
import pytest
from backend.scripts import seeded_learnsphere_acceptance as runner


def test_refuses_database_outside_isolated_root(monkeypatch, tmp_path):
    target = tmp_path / "outside"
    monkeypatch.setattr(sys, "argv", ["acceptance", "prepare", "--run-dir", str(target)])
    with pytest.raises(SystemExit):
        runner.main()
    assert not target.exists()


def test_existing_run_is_never_reset(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "acceptance.db"
    sentinel.write_bytes(b"preserve existing database")
    with pytest.raises(RuntimeError, match="never be reset"):
        runner.prepare(target)
    assert sentinel.read_bytes() == b"preserve existing database"
