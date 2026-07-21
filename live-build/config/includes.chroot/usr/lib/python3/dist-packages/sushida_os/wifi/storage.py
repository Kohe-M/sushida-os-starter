"""Credential and CSRF token storage for the Wi-Fi setup backend.

Owns the persistent setup.json credential file (atomic temp+rename writes,
symlink refusal, strict ownership/mode checks), the boot-stable CSRF token
file, and the persistent-storage readiness probe.  Exception messages never
contain credential material.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path

from sushida_os.wifi.types import validate_credentials

CONFIG_MOUNT = Path("/var/lib/sushida-config")
CONFIG_DIR = CONFIG_MOUNT / "network"
CONFIG_FILE = CONFIG_DIR / "setup.json"
STORAGE_STATUS = Path("/run/sushida-config/config-storage")
CSRF_TOKEN_FILE = Path("/run/sushida-wifi-setup/csrf-token")
# Content-free, world-readable marker for an in-flight connection attempt.
# It lives in its own 0755 wifi-setup runtime directory (tmpfiles.d) so the
# kiosk-user network watcher can observe it without any access to the
# private /run/sushida-wifi-setup state.
CONNECTION_MARKER_FILE = Path("/run/sushida-wifi-status/connection-in-progress")
FILESYSTEM_LABEL = "SUSHIDA-CFG"
MAX_CONFIG_BYTES = 8192
CSRF_TOKEN_BYTES = 32

_csrf_token_cache: str | None = None


def _test_path(name: str, production: Path) -> Path:
    if os.environ.get("SUSHIDA_WIFI_SETUP_TEST_MODE") != "1":
        return production
    value = os.environ.get(name)
    if not value or not value.startswith("/tmp/"):
        raise RuntimeError(f"unsafe test path for {name}")
    return Path(value)


def config_mount() -> Path:
    return _test_path("SUSHIDA_WIFI_SETUP_CONFIG_MOUNT", CONFIG_MOUNT)


def config_dir() -> Path:
    return config_mount() / "network"


def config_file() -> Path:
    return config_dir() / "setup.json"


def storage_status() -> Path:
    return _test_path("SUSHIDA_WIFI_SETUP_STORAGE_STATUS", STORAGE_STATUS)


def csrf_token_file() -> Path:
    return _test_path("SUSHIDA_WIFI_SETUP_CSRF_TOKEN_FILE", CSRF_TOKEN_FILE)


def connection_marker_file() -> Path | None:
    """Marker path, or None when publication is disabled.

    Unlike the mandatory storage paths, the marker is optional telemetry:
    in test mode it is published only when a test opts in with
    SUSHIDA_WIFI_SETUP_CONNECTION_MARKER (which must stay under /tmp).
    """
    if os.environ.get("SUSHIDA_WIFI_SETUP_TEST_MODE") == "1":
        value = os.environ.get("SUSHIDA_WIFI_SETUP_CONNECTION_MARKER")
        if not value:
            return None
        if not value.startswith("/tmp/"):
            raise RuntimeError(
                "unsafe test path for SUSHIDA_WIFI_SETUP_CONNECTION_MARKER"
            )
        return Path(value)
    return CONNECTION_MARKER_FILE


def set_connection_marker(active: bool) -> None:
    """Best-effort publication of an in-flight connection attempt.

    The marker is empty (existence only) so it can never leak an SSID or
    credential, and any failure is swallowed: publication must never
    affect the connection flow itself.
    """
    path = connection_marker_file()
    if path is None:
        return
    try:
        if active:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644
            )
            os.close(descriptor)
        else:
            path.unlink()
    except OSError:
        return


def _read_csrf_token(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("invalid CSRF token file")
    if info.st_uid != os.getuid() or not (32 <= info.st_size <= 128):
        raise RuntimeError("invalid CSRF token ownership or size")
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        raise RuntimeError("cannot read CSRF token") from error
    if not (32 <= len(token) <= 128) or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in token
    ):
        raise RuntimeError("invalid CSRF token content")
    return token


def csrf_token() -> str:
    """Return a private token that survives an automatic service restart."""
    global _csrf_token_cache
    if _csrf_token_cache is not None:
        return _csrf_token_cache

    path = csrf_token_file()
    try:
        token = _read_csrf_token(path)
    except FileNotFoundError:
        directory = path.parent
        if not directory.is_dir() or directory.is_symlink():
            raise RuntimeError("invalid CSRF runtime directory")
        token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
        temporary = directory / f".csrf-token.{os.getpid()}.{secrets.token_hex(8)}"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="ascii", closefd=True) as stream:
                stream.write(token + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        token = _read_csrf_token(path)

    _csrf_token_cache = token
    return token


def persistent_storage_ready() -> bool:
    try:
        mounted = config_mount().is_mount()
        if os.environ.get("SUSHIDA_WIFI_SETUP_TEST_MODE") == "1":
            mounted = config_mount().is_dir()
        status_info = storage_status().lstat()
        directory_info = config_dir().lstat()
        expected_status_uid = (
            os.getuid()
            if os.environ.get("SUSHIDA_WIFI_SETUP_TEST_MODE") == "1"
            else 0
        )
        return (
            stat.S_ISREG(status_info.st_mode)
            and not storage_status().is_symlink()
            and status_info.st_uid == expected_status_uid
            and stat.S_IMODE(status_info.st_mode) == 0o644
            and storage_status().read_text(encoding="utf-8").strip() == "ready"
            and mounted
            and stat.S_ISDIR(directory_info.st_mode)
            and directory_info.st_uid == os.getuid()
            and stat.S_IMODE(directory_info.st_mode) == 0o700
        )
    except OSError:
        return False


def persist_credentials(ssid: str, password: str) -> None:
    directory = config_dir()
    if not persistent_storage_ready():
        raise OSError("persistent storage unavailable")
    payload = json.dumps(
        {"version": 1, "ssid": ssid, "password": password},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if len(payload) > MAX_CONFIG_BYTES:
        raise OSError("configuration too large")

    temporary = directory / f".setup.{os.getpid()}.{secrets.token_hex(8)}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config_file())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_credentials() -> tuple[str, str] | None:
    path = config_file()
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFIG_BYTES:
            return None
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    ssid = data.get("ssid")
    password = data.get("password")
    if not isinstance(ssid, str) or not isinstance(password, str):
        return None
    if validate_credentials(ssid, password):
        return None
    return ssid, password
