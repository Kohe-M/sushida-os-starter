"""Security and coverage checks for the production diagnostics command."""

import os
import re
import stat
from pathlib import Path


DIAGNOSTICS = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-diagnostics"
)


def _text() -> str:
    return DIAGNOSTICS.read_text()


def test_diagnostics_is_executable_strict_and_complete() -> None:
    assert DIAGNOSTICS.is_file()
    assert DIAGNOSTICS.stat().st_mode & stat.S_IXUSR
    assert os.access(DIAGNOSTICS, os.X_OK)
    text = _text()
    assert "set -euo pipefail" in text
    assert "TODO" not in text
    assert "eval" not in text
    assert not re.search(r"^\s*(?:source|\.)\s+", text, re.MULTILINE)


def test_default_output_is_volatile_private_and_non_overwriting() -> None:
    text = _text()
    assert 'DEFAULT_DIR="/run/sushida-os/diagnostics"' in text
    assert "umask 077" in text
    assert "chmod 0600" in text
    assert "output already exists" in text
    assert "refusing to overwrite" in text
    assert "mktemp" in text


def test_collects_required_diagnostic_categories() -> None:
    text = _text()
    for value in (
        "/sys/class/drm",
        "gbm|EGL",
        "wayland-client",
        "cage -v",
        "chromium --version",
        "RUNTIME_WEBGL_STATUS",
        "pipewire",
        "wireplumber",
        "wpctl status",
        "nmcli -t -f STATE,CONNECTIVITY general",
    ):
        assert value in text


def test_does_not_collect_secret_bearing_sources() -> None:
    text = _text()
    for forbidden in (
        "nmcli connection show",
        "nmcli --show-secrets",
        "/etc/NetworkManager/system-connections",
        "/proc/*/cmdline",
        "printenv",
        "set |",
        "edid",
        "sudo",
    ):
        assert forbidden not in text.lower()


def test_redacts_common_credentials_and_unique_identifiers() -> None:
    text = _text()
    for marker in (
        "REDACTED-MAC",
        "REDACTED-UUID",
        "password|passwd|psk|secret|token|credential",
        "?[REDACTED]",
    ):
        assert marker in text


def test_no_kiosk_ui_or_privilege_route_is_added() -> None:
    text = _text()
    assert "systemctl enable" not in text
    assert "pkexec" not in text
    assert "sudo" not in text
    assert "chmod 0666" not in text
