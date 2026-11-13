"""Hosted-CI entry point: deny inherited dotenv files, permit scratch fixtures.

Dependency installation is separate. pytest-socket fences external sockets
during tests; this helper never supplies provider or wallet credentials.
"""

from pathlib import Path
import tempfile


def fixture_dotenv_loader(original, fixture_root):
    root = Path(fixture_root).resolve()

    def load(dotenv_path=None, *args, **kwargs):
        # No auto-discovery, streams, or caller-provided alternate sources.
        if dotenv_path is None or args or kwargs.get("stream") is not None:
            return False
        try:
            candidate = Path(dotenv_path).resolve()
        except (TypeError, ValueError, OSError):
            return False
        if not candidate.is_relative_to(root):
            return False
        return original(candidate, *args, **kwargs)

    return load


def main():
    import dotenv
    import pytest

    with tempfile.TemporaryDirectory(prefix="aihf-offline-") as scratch:
        fixture_root = Path(scratch) / "pytest"
        dotenv.load_dotenv = fixture_dotenv_loader(dotenv.load_dotenv, fixture_root)
        return pytest.main([
            "hedge_fund/", "--disable-socket", "--allow-unix-socket",
            "--allow-hosts=127.0.0.1,::1", "--full-trace",
            f"--basetemp={fixture_root}", "--junitxml=sync-test-results.xml",
        ])


if __name__ == "__main__":
    raise SystemExit(main())
