"""sushida_os.config: the single config.env parser and validator.

These tests pin the rules every consumer relies on — the launcher and
network watcher (via the CLI) and the input watcher (via import) — so the
rules can no longer drift between separate implementations.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sushida_os import config

PRODUCTION_CONFIG = Path("live-build/config/includes.chroot/etc/sushida-os/config.env")
DIST_PACKAGES = Path("live-build/config/includes.chroot/usr/lib/python3/dist-packages")
BASE = "SUSHIDA_URL=https://sushida.net/play.html\n"


def _value(text: str, key: str):
    return config.value(config.parse(text), key)


def _error(text: str, key: str = "SUSHIDA_URL") -> str:
    with pytest.raises(config.ConfigError) as info:
        _value(text, key)
    return str(info.value)


# ── syntax ───────────────────────────────────────────────────────────────


def test_production_config_is_valid_for_every_key() -> None:
    raw = config.read(PRODUCTION_CONFIG)
    assert set(raw) == set(config.SETTINGS)
    values = {key: config.value(raw, key) for key in config.SETTINGS}
    assert values == {
        "SUSHIDA_URL": "https://sushida.net/play.html",
        "NETWORK_CHECK_INTERVAL_SECONDS": 30,
        "NETWORK_SETUP_GRACE_SECONDS": 15,
        "AUDIO_VOLUME_PERCENT": 70,
        "SCREEN_BRIGHTNESS_PERCENT": 80,
        "SCREEN_ZOOM_PERCENT": 180,
    }


def test_comments_blank_lines_and_crlf_are_accepted() -> None:
    text = "# comment\n\r\n" + BASE.replace("\n", "\r\n") + "SCREEN_ZOOM_PERCENT=150\r\n"
    assert _value(text, "SUSHIDA_URL") == "https://sushida.net/play.html"
    assert _value(text, "SCREEN_ZOOM_PERCENT") == 150


def test_value_splits_on_the_first_equals_only() -> None:
    url = "https://sushida.net/play.html?a=b=c"
    assert _value(f"SUSHIDA_URL={url}\n", "SUSHIDA_URL") == url


def test_last_line_without_newline_is_read() -> None:
    assert _value(BASE + "SCREEN_ZOOM_PERCENT=120", "SCREEN_ZOOM_PERCENT") == 120


@pytest.mark.parametrize("text, message", [
    (BASE + "broken-line\n", "missing '='"),
    (BASE + "EVIL=value\n", "Unknown config key at line 2"),
    (BASE + " SCREEN_ZOOM_PERCENT=150\n", "Unknown config key"),  # no trimming
    (BASE + "  # indented comment\n", "missing '='"),
    (BASE + BASE, "Duplicate SUSHIDA_URL"),
])
def test_syntax_errors_invalidate_the_whole_file(text: str, message: str) -> None:
    # Syntax is enforced for every key, not just the one asked for.
    for key in config.SETTINGS:
        with pytest.raises(config.ConfigError, match=message):
            _value(text, key)


def test_syntax_errors_never_echo_line_content() -> None:
    assert "secret" not in _error(BASE + "WIFI_PSK=secret\n")
    assert "secret" not in _error(BASE + "secret\n")


# ── SUSHIDA_URL ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [
    "https://sushida.net",
    "https://sushida.net/",
    "https://sushida.net/play.html",
    "https://sushida.net/$(touch /tmp/x)",  # data, never evaluated
])
def test_url_inside_the_official_origin_is_accepted(url: str) -> None:
    assert _value(f"SUSHIDA_URL={url}\n", "SUSHIDA_URL") == url


@pytest.mark.parametrize("url", [
    "https://evil.example/",
    "https://sushida.net.evil.example/",
    "https://user@sushida.net/",
    "https://sushida.net:8443/",
    "http://sushida.net/",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,hello",
    '"https://sushida.net/"',
    " https://sushida.net/",
])
def test_url_outside_the_official_origin_is_rejected(url: str) -> None:
    assert "disallowed" in _error(f"SUSHIDA_URL={url}\n")


def test_url_is_required() -> None:
    assert _error("NETWORK_CHECK_INTERVAL_SECONDS=30\n") == "SUSHIDA_URL not set"
    assert _error("SUSHIDA_URL=\n") == "SUSHIDA_URL not set"


# ── integer settings ─────────────────────────────────────────────────────


@pytest.mark.parametrize("key, low, high, default", [
    ("NETWORK_CHECK_INTERVAL_SECONDS", 30, 3600, 30),
    ("NETWORK_SETUP_GRACE_SECONDS", 0, 60, 15),
    ("AUDIO_VOLUME_PERCENT", 0, 100, None),
    ("SCREEN_BRIGHTNESS_PERCENT", 5, 100, 80),
    ("SCREEN_ZOOM_PERCENT", 50, 300, None),
])
def test_integer_bounds_and_defaults(key: str, low: int, high: int, default) -> None:
    assert _value(BASE, key) == default
    assert _value(BASE + f"{key}={low}\n", key) == low
    assert _value(BASE + f"{key}={high}\n", key) == high
    assert "must be between" in _error(BASE + f"{key}={high + 1}\n", key)
    if low > 0:
        assert "must be between" in _error(BASE + f"{key}={low - 1}\n", key)
    for bad in ("-1", "30x", "1.5", " 40", "４０", "$(reboot)"):
        assert "must be an integer" in _error(BASE + f"{key}={bad}\n", key)


def test_empty_value_unsets_only_optional_settings() -> None:
    assert _value(BASE + "AUDIO_VOLUME_PERCENT=\n", "AUDIO_VOLUME_PERCENT") is None
    assert _value(BASE + "SCREEN_ZOOM_PERCENT=\n", "SCREEN_ZOOM_PERCENT") is None
    for key in ("NETWORK_CHECK_INTERVAL_SECONDS", "NETWORK_SETUP_GRACE_SECONDS",
                "SCREEN_BRIGHTNESS_PERCENT"):
        assert "must be an integer" in _error(BASE + f"{key}=\n", key)


def test_values_are_checked_only_for_the_requested_key() -> None:
    text = BASE + "SCREEN_ZOOM_PERCENT=999\n"
    assert _value(text, "SUSHIDA_URL") == "https://sushida.net/play.html"
    assert "must be between" in _error(text, "SCREEN_ZOOM_PERCENT")


# ── file access and CLI ──────────────────────────────────────────────────


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="Config file not found"):
        config.load("SUSHIDA_URL", tmp_path / "absent.env")


def _cli(*args: str) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ, PYTHONPATH=str(DIST_PACKAGES), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, "-m", "sushida_os.config", *args],
        capture_output=True, env=env, timeout=30,
    )


def test_cli_prints_one_validated_value(tmp_path: Path) -> None:
    path = tmp_path / "config.env"
    path.write_text(BASE + "AUDIO_VOLUME_PERCENT=\n")
    result = _cli("--file", str(path), "SUSHIDA_URL")
    assert (result.returncode, result.stdout) == (0, b"https://sushida.net/play.html\n")
    result = _cli("--file", str(path), "AUDIO_VOLUME_PERCENT")
    assert (result.returncode, result.stdout) == (0, b"\n")
    result = _cli("--file", str(path), "NETWORK_SETUP_GRACE_SECONDS")
    assert (result.returncode, result.stdout) == (0, b"15\n")


def test_cli_reports_errors_on_stderr_only(tmp_path: Path) -> None:
    path = tmp_path / "config.env"
    path.write_text("SUSHIDA_URL=http://sushida.net/\n")
    result = _cli("--file", str(path), "SUSHIDA_URL")
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR: Invalid or disallowed URL")
    result = _cli("--file", str(tmp_path / "absent"), "SUSHIDA_URL")
    assert result.returncode == 1
    assert b"not found" in result.stderr


def test_cli_rejects_keys_outside_the_table(tmp_path: Path) -> None:
    path = tmp_path / "config.env"
    path.write_text(BASE)
    assert _cli("--file", str(path), "PATH").returncode == 2


def test_cli_round_trips_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "config.env"
    path.write_bytes(b"SUSHIDA_URL=https://sushida.net/\xff\n")
    result = _cli("--file", str(path), "SUSHIDA_URL")
    assert (result.returncode, result.stdout) == (0, b"https://sushida.net/\xff\n")


# ── image registration ───────────────────────────────────────────────────


def test_image_ships_and_validates_the_module() -> None:
    hook = Path("live-build/config/hooks/live/090-validate-image.hook.chroot").read_text()
    assert '"$backend_package/config.py"' in hook
    assert "import sushida_os.config\n" in hook
    assert "for key in config.SETTINGS:\n    config.value(raw, key)" in hook
    assert 'fail "shipped config.env does not validate"' in hook
