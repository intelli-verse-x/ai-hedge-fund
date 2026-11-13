"""Cooperative local ownership for paper-fund mutations.

An atomic sibling directory excludes other processes and threads. Ownership
is deliberately not stolen on age/PID guesses: a crash leaves a blocker for
manual recovery after the process and book/ledger have been checked. This is
not a distributed lock or authorization boundary against the same OS user.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import json
import os
import shutil
from pathlib import Path
import threading
import uuid

_local = threading.local()


class FundBusy(RuntimeError):
    """Another writer owns the fund, or a crashed owner needs recovery."""


def lock_path(directory: str | Path) -> Path:
    directory = Path(directory).resolve()
    return directory.parent / f".{directory.name}.writer.lock"


def _held() -> dict:
    if getattr(_local, "pid", None) != os.getpid():
        _local.pid = os.getpid()
        _local.held = {}
    return _local.held


@contextmanager
def ownership(directory: str | Path):
    path = lock_path(directory)
    held = _held()
    if path in held:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError:
        raise FundBusy(f"{Path(directory).name}: writer ownership exists at {path}; stop the owner or review crash recovery") from None
    token = uuid.uuid4().hex
    owner = {"pid": os.getpid(), "token": token, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        (path / "owner.json").write_text(json.dumps(owner))
    except BaseException:
        # Never remove an existing owner's lock; this directory was just ours.
        (path / "owner.json").unlink(missing_ok=True)
        path.rmdir()
        raise
    held[path] = token
    try:
        yield
    finally:
        del held[path]
        current = read_owner(directory)
        if current is None or current.get("token") != token:
            raise FundBusy(f"{path}: owner changed; recovery required")
        # Remove the active name atomically before cleanup. A stop request
        # racing with release either follows this retired directory or fails;
        # it cannot leave an active orphan after our final unlink/rmdir.
        retired = path.with_name(path.name + ".retired." + token)
        path.rename(retired)
        shutil.rmtree(retired)


def read_owner(directory: str | Path) -> dict | None:
    try:
        value = json.loads((lock_path(directory) / "owner.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or type(value.get("pid")) is not int or value["pid"] <= 0:
        return None
    token = value.get("token")
    if not isinstance(token, str) or len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        return None
    return value


def mark_runner(directory: str | Path) -> None:
    path = lock_path(directory)
    owner = read_owner(directory)
    if owner is None or owner["token"] != _held().get(path):
        raise FundBusy("Runner must hold fund ownership before registering")
    owner["role"] = "runner"
    (path / "owner.json").write_text(json.dumps(owner))


def request_stop(directory: str | Path, pid: int) -> bool:
    owner = read_owner(directory)
    if owner is None or owner.get("role") != "runner" or owner["pid"] != pid:
        return False
    # A token-bound cooperative request cannot signal a reused/unrelated PID.
    try:
        (lock_path(directory) / f"stop.{owner['token']}.json").write_text(json.dumps({"token": owner["token"]}))
    except FileNotFoundError:
        return False  # the owner completed while the request was in flight
    return True


def stop_requested(directory: str | Path, token: str) -> bool:
    try:
        value = json.loads((lock_path(directory) / f"stop.{token}.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and value.get("token") == token


def owned_fund(function):
    @wraps(function)
    def guarded(directory, *args, **kwargs):
        with ownership(directory):
            return function(directory, *args, **kwargs)
    return guarded


def owned_ledger(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with ownership(self.directory):
            return function(self, *args, **kwargs)
    return guarded
