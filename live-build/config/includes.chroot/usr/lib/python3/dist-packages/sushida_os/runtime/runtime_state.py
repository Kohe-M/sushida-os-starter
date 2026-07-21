"""Volatile route state protocol: /run/sushida-os/runtime-state.json.

Schema version 1 carries exactly four values — ``active_route``,
``time_sync_required``, ``connection_in_progress``, and ``last_reason`` —
none of which may contain URLs, SSIDs, or credential material
(``last_reason`` is restricted to a short lowercase enum-style token).
Writes are atomic (temp file + rename) and refuse symlinked directories
or targets.  Reads fail closed: any missing, symlinked, oversized,
malformed, unknown-versioned, or extra-keyed file reads as ``None``.

The file is single-line JSON so shell readers can consume it with a
line-oriented parser, and Python readers use :func:`read_state`.  Shell
writers invoke ``python3 -m sushida_os.runtime.runtime_state`` with the
fixed flags parsed by :func:`main`.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from sushida_os.runtime.routes import ROUTES

SCHEMA_VERSION = 1
STATE_BASENAME = "runtime-state.json"
PROD_RUNTIME_DIR = Path("/run/sushida-os")
MAX_STATE_BYTES = 4096
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class RuntimeState:
    active_route: str
    time_sync_required: bool
    connection_in_progress: bool
    last_reason: str


def _validate(state: RuntimeState) -> None:
    if state.active_route not in ROUTES:
        raise ValueError("unknown active_route")
    if not isinstance(state.time_sync_required, bool):
        raise ValueError("time_sync_required must be a boolean")
    if not isinstance(state.connection_in_progress, bool):
        raise ValueError("connection_in_progress must be a boolean")
    if not _REASON_PATTERN.match(state.last_reason):
        raise ValueError("last_reason must be a short lowercase token")


def state_path(directory: Path) -> Path:
    return directory / STATE_BASENAME


def write_state(directory: Path, state: RuntimeState) -> None:
    """Atomically publish state; never follow symlinks."""
    _validate(state)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OSError("runtime state directory is not a real directory")
    target = state_path(directory)
    try:
        if stat.S_ISLNK(target.lstat().st_mode):
            raise OSError("runtime state target is a symlink")
    except FileNotFoundError:
        pass
    payload = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "active_route": state.active_route,
            "time_sync_required": state.time_sync_required,
            "connection_in_progress": state.connection_in_progress,
            "last_reason": state.last_reason,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii") + b"\n"
    if len(payload) > MAX_STATE_BYTES:
        raise OSError("runtime state too large")
    temporary = directory / f".{STATE_BASENAME}.{os.getpid()}.{secrets.token_hex(8)}"
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # The launcher runs with umask 077; the protocol file must stay
        # readable for every runtime reader.
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_state(directory: Path) -> RuntimeState | None:
    """Return the published state, or None whenever anything is off."""
    target = state_path(directory)
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATE_BYTES:
            return None
        data = json.loads(target.read_text(encoding="ascii"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    expected_keys = {
        "schema_version", "active_route", "time_sync_required",
        "connection_in_progress", "last_reason",
    }
    if set(data) != expected_keys:
        return None
    if data["schema_version"] != SCHEMA_VERSION:
        return None
    state = RuntimeState(
        active_route=data["active_route"],
        time_sync_required=data["time_sync_required"],
        connection_in_progress=data["connection_in_progress"],
        last_reason=data["last_reason"],
    )
    try:
        _validate(state)
    except ValueError:
        return None
    return state


def _parse_bool_flag(value: str) -> bool | None:
    if value == "0":
        return False
    if value == "1":
        return True
    return None


def main(argv: list[str]) -> int:
    """Fixed-flag CLI for shell callers.

    Modes (mutually exclusive with the write flags):
      write:              --directory D --route R --reason T [--time-sync-required 0|1]
                          [--connection-in-progress 0|1]
      read:               --directory D --print active-route|time-sync-required
      clear time-sync:    --directory D --clear-time-sync
      set progress:       --directory D --set-connection-in-progress 0|1
                          (both read-modify-write; they fail closed when no
                          valid state exists)

    A non-production directory requires SUSHIDA_OS_TEST_MODE=1, matching
    every other runtime script's test-override gate.  Reads print only the
    validated value; failures exit non-zero without echoing dynamic values.
    """
    directory: Path | None = None
    route = ""
    time_sync_required = False
    connection_in_progress = False
    reason = ""
    print_field: str | None = None
    clear_time_sync = False
    set_progress: bool | None = None
    write_flags_seen = False
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag == "--clear-time-sync":
            clear_time_sync = True
            index += 1
            continue
        if flag not in ("--directory", "--route", "--time-sync-required",
                        "--connection-in-progress", "--reason", "--print",
                        "--set-connection-in-progress"):
            return 2
        index += 1
        if index >= len(argv):
            return 2
        value = argv[index]
        index += 1
        if flag == "--directory":
            directory = Path(value)
        elif flag == "--print":
            if value not in ("active-route", "time-sync-required"):
                return 2
            print_field = value
        elif flag == "--set-connection-in-progress":
            parsed = _parse_bool_flag(value)
            if parsed is None:
                return 2
            set_progress = parsed
        elif flag == "--route":
            write_flags_seen = True
            route = value
        elif flag == "--reason":
            write_flags_seen = True
            reason = value
        elif flag == "--time-sync-required":
            parsed = _parse_bool_flag(value)
            if parsed is None:
                return 2
            write_flags_seen = True
            time_sync_required = parsed
        else:
            parsed = _parse_bool_flag(value)
            if parsed is None:
                return 2
            write_flags_seen = True
            connection_in_progress = parsed
    if directory is None:
        return 2
    if ((print_field is not None) + clear_time_sync
            + (set_progress is not None) + write_flags_seen) > 1:
        return 2
    if directory != PROD_RUNTIME_DIR and \
            os.environ.get("SUSHIDA_OS_TEST_MODE") != "1":
        print("ERROR: runtime-state directory override requires "
              "SUSHIDA_OS_TEST_MODE=1", file=sys.stderr)
        return 2
    if print_field is not None:
        state = read_state(directory)
        if state is None:
            return 1
        if print_field == "active-route":
            print(state.active_route)
        else:
            print("1" if state.time_sync_required else "0")
        return 0
    if clear_time_sync:
        state = read_state(directory)
        if state is None:
            return 1
        try:
            write_state(directory, RuntimeState(
                active_route=state.active_route,
                time_sync_required=False,
                connection_in_progress=state.connection_in_progress,
                last_reason=state.last_reason,
            ))
        except (OSError, ValueError):
            return 1
        return 0
    if set_progress is not None:
        state = read_state(directory)
        if state is None:
            return 1
        if state.connection_in_progress == set_progress:
            return 0
        try:
            write_state(directory, RuntimeState(
                active_route=state.active_route,
                time_sync_required=state.time_sync_required,
                connection_in_progress=set_progress,
                last_reason=state.last_reason,
            ))
        except (OSError, ValueError):
            return 1
        return 0
    try:
        write_state(directory, RuntimeState(
            active_route=route,
            time_sync_required=time_sync_required,
            connection_in_progress=connection_in_progress,
            last_reason=reason,
        ))
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
