"""Behavior tests for the volatile runtime-state protocol."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

DIST_PACKAGES = Path(
    "live-build/config/includes.chroot/usr/lib/python3/dist-packages"
).resolve()
if str(DIST_PACKAGES) not in sys.path:
    sys.path.insert(0, str(DIST_PACKAGES))

from sushida_os.runtime import runtime_state  # noqa: E402
from sushida_os.runtime.runtime_state import RuntimeState  # noqa: E402


GOOD = RuntimeState(
    active_route="online",
    time_sync_required=False,
    connection_in_progress=False,
    last_reason="online-full",
)


def test_round_trip(tmp_path: Path) -> None:
    runtime_state.write_state(tmp_path, GOOD)
    assert runtime_state.read_state(tmp_path) == GOOD


def test_write_replaces_existing_state_atomically(tmp_path: Path) -> None:
    runtime_state.write_state(tmp_path, GOOD)
    replacement = RuntimeState("setup", True, True, "setup-available")
    runtime_state.write_state(tmp_path, replacement)
    assert runtime_state.read_state(tmp_path) == replacement
    leftovers = [p.name for p in tmp_path.iterdir()]
    assert leftovers == ["runtime-state.json"]


def test_state_file_is_single_line_ascii_json(tmp_path: Path) -> None:
    runtime_state.write_state(tmp_path, GOOD)
    raw = (tmp_path / "runtime-state.json").read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    data = json.loads(raw)
    assert data["schema_version"] == 1
    assert set(data) == {
        "schema_version", "active_route", "time_sync_required",
        "connection_in_progress", "last_reason",
    }


def test_state_file_is_world_readable_despite_writer_umask(tmp_path: Path) -> None:
    old_umask = os.umask(0o077)
    try:
        runtime_state.write_state(tmp_path, GOOD)
    finally:
        os.umask(old_umask)
    mode = (tmp_path / "runtime-state.json").stat().st_mode & 0o777
    assert mode == 0o644


def test_write_refuses_symlinked_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n")
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "runtime-state.json").symlink_to(outside)
    with pytest.raises(OSError):
        runtime_state.write_state(tmp_path / "run", GOOD)
    assert outside.read_text() == "{}\n"


def test_write_refuses_symlinked_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(OSError):
        runtime_state.write_state(link, GOOD)


def test_write_rejects_unknown_route_and_free_text_reason(tmp_path: Path) -> None:
    for bad in (
        GOOD.__class__("broken", False, False, "online-full"),
        GOOD.__class__("", False, False, "online-full"),
        GOOD.__class__("online", False, False, ""),
        GOOD.__class__("online", False, False, "https://evil.example/"),
        GOOD.__class__("online", False, False, "Reason With Spaces"),
        GOOD.__class__("online", False, False, "a" * 65),
    ):
        with pytest.raises(ValueError):
            runtime_state.write_state(tmp_path, bad)
    assert runtime_state.read_state(tmp_path) is None


def _write_raw(tmp_path: Path, payload: bytes) -> None:
    (tmp_path / "runtime-state.json").write_bytes(payload)


def test_read_fails_closed_on_corrupted_json(tmp_path: Path) -> None:
    _write_raw(tmp_path, b"{broken\n")
    assert runtime_state.read_state(tmp_path) is None


def test_read_fails_closed_on_unknown_schema_version(tmp_path: Path) -> None:
    payload = {
        "schema_version": 2, "active_route": "online",
        "time_sync_required": False, "connection_in_progress": False,
        "last_reason": "online-full",
    }
    _write_raw(tmp_path, json.dumps(payload).encode("ascii"))
    assert runtime_state.read_state(tmp_path) is None


def test_read_fails_closed_on_extra_or_missing_keys(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1, "active_route": "online",
        "time_sync_required": False, "connection_in_progress": False,
        "last_reason": "online-full", "extra": "x",
    }
    _write_raw(tmp_path, json.dumps(payload).encode("ascii"))
    assert runtime_state.read_state(tmp_path) is None
    del payload["extra"], payload["last_reason"]
    _write_raw(tmp_path, json.dumps(payload).encode("ascii"))
    assert runtime_state.read_state(tmp_path) is None


def test_read_fails_closed_on_symlink_missing_and_oversize(tmp_path: Path) -> None:
    assert runtime_state.read_state(tmp_path) is None
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({
        "schema_version": 1, "active_route": "online",
        "time_sync_required": False, "connection_in_progress": False,
        "last_reason": "online-full",
    }))
    (tmp_path / "runtime-state.json").symlink_to(outside)
    assert runtime_state.read_state(tmp_path) is None
    (tmp_path / "runtime-state.json").unlink()
    _write_raw(tmp_path, b" " * 5000)
    assert runtime_state.read_state(tmp_path) is None


def test_read_fails_closed_on_wrong_value_types(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1, "active_route": "online",
        "time_sync_required": "no", "connection_in_progress": False,
        "last_reason": "online-full",
    }
    _write_raw(tmp_path, json.dumps(payload).encode("ascii"))
    assert runtime_state.read_state(tmp_path) is None


def _run_cli(*args: str, test_mode: bool = True) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": str(DIST_PACKAGES), "PYTHONDONTWRITEBYTECODE": "1",
           "PATH": "/usr/bin:/bin"}
    if test_mode:
        env["SUSHIDA_OS_TEST_MODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "sushida_os.runtime.runtime_state", *args],
        capture_output=True, text=True, timeout=10, env=env,
    )


def test_cli_writes_state(tmp_path: Path) -> None:
    result = _run_cli(
        "--directory", str(tmp_path), "--route", "offline",
        "--time-sync-required", "1", "--reason", "time-sync-pending",
    )
    assert result.returncode == 0, result.stderr
    state = runtime_state.read_state(tmp_path)
    assert state == RuntimeState("offline", True, False, "time-sync-pending")


def test_cli_directory_override_requires_test_mode(tmp_path: Path) -> None:
    result = _run_cli(
        "--directory", str(tmp_path), "--route", "online",
        "--reason", "online-full", test_mode=False,
    )
    assert result.returncode != 0
    assert "SUSHIDA_OS_TEST_MODE" in result.stderr


def test_cli_rejects_unknown_flags_and_bad_values(tmp_path: Path) -> None:
    for bad in (
        ["--directory", str(tmp_path), "--route", "online",
         "--reason", "online-full", "--evil", "1"],
        ["--directory", str(tmp_path), "--route", "broken",
         "--reason", "online-full"],
        ["--directory", str(tmp_path), "--route", "online",
         "--reason", "online-full", "--time-sync-required", "yes"],
        ["--route", "online", "--reason", "online-full"],
        ["--directory"],
    ):
        result = _run_cli(*bad)
        assert result.returncode != 0, bad
    assert runtime_state.read_state(tmp_path) is None
