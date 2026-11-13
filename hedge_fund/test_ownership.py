"""Local synthetic ownership cases; never provider calls, signals or trades."""
from concurrent.futures import ThreadPoolExecutor
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from hedge_fund.ownership import (
    FundBusy, lock_path, mark_runner, owned_fund, ownership,
    read_owner, request_stop, stop_requested,
)


def test_nested_owner_and_other_fund_are_allowed(tmp_path):
    directory = tmp_path / "fund"
    with ownership(directory):
        token = read_owner(directory)["token"]
        with ownership(directory):
            assert read_owner(directory)["token"] == token
        with ownership(tmp_path / "other"):
            assert lock_path(directory).is_dir()
    assert not lock_path(directory).exists()


def test_other_thread_cannot_enter_and_exception_releases(tmp_path):
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ownership(tmp_path / "fund"):
            with pytest.raises(FundBusy):
                pool.submit(lambda: _enter(tmp_path / "fund")).result(timeout=5)
    with pytest.raises(ValueError):
        with ownership(tmp_path / "fund"):
            raise ValueError("synthetic failure")
    with ownership(tmp_path / "fund"):
        pass


def _enter(directory):
    with ownership(directory):
        return True


def test_stale_or_unrecognized_lock_is_never_stolen(tmp_path):
    directory = tmp_path / "fund"
    path = lock_path(directory)
    path.mkdir()
    sentinel = path / "unknown-owner"
    sentinel.write_text("retain for recovery")
    with pytest.raises(FundBusy):
        _enter(directory)
    assert sentinel.read_text() == "retain for recovery"


def test_another_python_process_cannot_acquire_owned_directory(tmp_path):
    import hedge_fund.ownership as module
    directory = tmp_path / "fund"
    code = '''import importlib.util,sys
spec=importlib.util.spec_from_file_location("reviewed_ownership",sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:
 with m.ownership(sys.argv[2]):pass
except m.FundBusy:print("blocked")
else:raise SystemExit("unexpected competing writer")
'''
    with ownership(directory):
        result = subprocess.run([sys.executable, "-I", "-c", code, module.__file__, str(directory)],
                                text=True, capture_output=True, timeout=10, check=True)
        assert result.stdout.strip() == "blocked"


def test_stop_is_token_bound_and_requires_registered_runner(tmp_path):
    directory = tmp_path / "fund"
    with ownership(directory):
        owner = read_owner(directory)
        assert not request_stop(directory, os.getpid())
        mark_runner(directory)
        assert not request_stop(directory, os.getpid() + 1)
        assert request_stop(directory, os.getpid())
        assert stop_requested(directory, owner["token"])
        assert not stop_requested(directory, "0" * 32)
    assert not lock_path(directory).exists()


def _actual_function(relative_file, name, namespace):
    path = Path(__file__).parent / relative_file
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("relative_file,name", [
    ("paper/tick.py", "tick"), ("paper/tick.py", "redo"),
    ("paper/runner.py", "run"), ("paper/runner.py", "serve"),
])
def test_real_writer_entrypoints_refuse_before_reading_or_billing(tmp_path, relative_file, name):
    touched = []
    ns = dict(owned_fund=owned_fund, Path=Path,
              load_deployed=lambda directory: touched.append(directory), is_running=lambda directory: False,
              threading=SimpleNamespace(Event=lambda: touched.append("event")))
    operation = _actual_function(relative_file, name, ns)
    with ownership(tmp_path / "fund"):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(FundBusy):
                pool.submit(operation, tmp_path / "fund", object()).result(timeout=5)
    assert touched == []


def test_real_wipe_refuses_running_fund_before_deleting_anything(tmp_path):
    directory = tmp_path / "paper" / "fund"
    directory.mkdir(parents=True)
    (directory / "book.json").write_text("retain")
    mandates = tmp_path / "mandates"
    mandates.mkdir()
    (mandates / "fund.yaml").write_text("retain mandate")
    ns = dict(ownership=ownership, paths=SimpleNamespace(PAPER_DIR=directory.parent, MANDATES_DIR=mandates),
              validate_fund_name=lambda x:x, receipts=lambda x:[], shutil=shutil)
    wipe = _actual_function("tui/funds.py", "wipe_fund", ns)
    with ownership(directory):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(FundBusy):
                pool.submit(wipe, "fund").result(timeout=5)
    assert (directory / "book.json").read_text() == "retain"
    assert (mandates / "fund.yaml").read_text() == "retain mandate"
    wipe("fund")
    assert not directory.exists() and not (mandates / "fund.yaml").exists()


@pytest.mark.parametrize("value", ["-1", "0", "-100", "corrupt", ""])
def test_real_pid_reader_rejects_process_group_and_broadcast_ids(tmp_path, value):
    (tmp_path / "runner.pid").write_text(value)
    read = _actual_function("paper/runner.py", "_read_pid", dict(Path=Path, PID_FILE="runner.pid"))
    assert read(tmp_path) is None


def test_real_stop_runner_never_sends_a_signal(tmp_path):
    touched = []
    stop = _actual_function("paper/runner.py", "stop_runner", dict(
        _read_pid=lambda directory:1234, is_running=lambda directory:True,
        request_stop=lambda directory,pid:touched.append((directory,pid)) or True,
        os=SimpleNamespace(kill=lambda *args:pytest.fail("OS signal sent"))))
    assert stop(tmp_path)
    assert touched == [(tmp_path,1234)]


def test_real_serve_observes_cooperative_stop_without_os_signals(tmp_path):
    directory = tmp_path / "fund"
    directory.mkdir()
    handlers = []
    def fake_run(directory, data_client, *, stop, **kwargs):
        assert request_stop(directory, os.getpid())
        assert stop.wait(2), "cooperative stop watcher did not wake the runner"
    signals = SimpleNamespace(SIGTERM=15, SIGINT=2, signal=lambda *args:handlers.append(args))
    serve = _actual_function("paper/runner.py", "serve", dict(
        owned_fund=owned_fund, Path=Path, is_running=lambda directory:False,
        threading=threading, signal=signals, os=SimpleNamespace(getpid=os.getpid),
        PID_FILE="runner.pid", mark_runner=mark_runner, read_owner=read_owner,
        stop_requested=stop_requested, run=fake_run,
        _read_pid=lambda directory:os.getpid()))
    serve(directory, object())
    assert not (directory / "runner.pid").exists()
    assert not lock_path(directory).exists() and len(handlers) == 4


def test_stop_request_racing_completed_owner_does_not_raise_or_leave_lock(tmp_path, monkeypatch):
    directory = tmp_path / "fund"
    before_write, release_write = threading.Event(), threading.Event()
    original = Path.write_text
    def paused_write(path, *args, **kwargs):
        if path.name.startswith("stop."):
            before_write.set()
            assert release_write.wait(5)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", paused_write)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ownership(directory):
            mark_runner(directory)
            pending = pool.submit(request_stop, directory, os.getpid())
            assert before_write.wait(5)
        release_write.set()
        assert pending.result(timeout=5) is False
    with ownership(directory):
        pass
    assert not lock_path(directory).exists()


def test_old_stop_request_cannot_replace_new_owner_stop(tmp_path, monkeypatch):
    directory = tmp_path / "fund"
    before_write, release_write = threading.Event(), threading.Event()
    original = Path.write_text
    old_token = None
    def paused_old_write(path, *args, **kwargs):
        if path.name == f"stop.{old_token}.json":
            before_write.set()
            assert release_write.wait(5)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", paused_old_write)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ownership(directory):
            mark_runner(directory)
            old_token = read_owner(directory)["token"]
            pending = pool.submit(request_stop, directory, os.getpid())
            assert before_write.wait(5)
        with ownership(directory):
            mark_runner(directory)
            new_token = read_owner(directory)["token"]
            assert new_token != old_token
            assert request_stop(directory, os.getpid())
            release_write.set()
            pending.result(timeout=5)
            assert stop_requested(directory, new_token)
    assert not lock_path(directory).exists()
