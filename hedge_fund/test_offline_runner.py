"""The CI dotenv fence permits test fixtures without loading checkout secrets."""

from pathlib import Path
import runpy
from unittest.mock import Mock


loader = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "run-offline-tests.py"))["fixture_dotenv_loader"]


def test_fixture_loader_allows_only_explicit_scratch_files(tmp_path):
    scratch = tmp_path / "fixtures"
    scratch.mkdir()
    fixture = scratch / ".env"
    fixture.write_text("SYNTHETIC_KEY=fixture-only\n")
    original = Mock(return_value=True)
    guarded = loader(original, scratch)
    assert guarded(fixture, override=False) is True
    original.assert_called_once_with(fixture.resolve(), override=False)
    original.reset_mock()
    assert guarded() is False
    assert guarded(tmp_path / ".env") is False
    assert guarded(str(scratch) + "-other/.env") is False
    assert guarded(fixture, stream=object()) is False
    assert guarded(fixture, object()) is False
    original.assert_not_called()


def test_fixture_loader_resolves_symlink_escape(tmp_path):
    scratch = tmp_path / "fixtures"
    scratch.mkdir()
    outside = tmp_path / ".env"
    outside.write_text("SYNTHETIC_KEY=outside\n")
    link = scratch / ".env"
    try:
        link.symlink_to(outside)
    except OSError:
        # Windows runners without symlink privileges still exercise lexical
        # containment in the preceding test.
        import pytest
        pytest.skip("symlink creation requires unavailable Windows privileges")
    original = Mock()
    assert loader(original, scratch)(link) is False
    original.assert_not_called()
