"""Static coverage for the final live-build chroot validation hook."""

import os
import re
import stat
from pathlib import Path


HOOK = Path("live-build/config/hooks/live/090-validate-image.hook.chroot")


def _text() -> str:
    return HOOK.read_text()


def test_hook_exists_and_is_executable() -> None:
    assert HOOK.is_file()
    mode = HOOK.stat().st_mode
    assert mode & stat.S_IXUSR
    assert os.access(HOOK, os.X_OK)


def test_hook_is_last_numbered_validation_stage() -> None:
    hooks = sorted(HOOK.parent.glob("*.hook.chroot"))
    assert hooks[-1] == HOOK


def test_hook_strict_without_eval_or_source() -> None:
    text = _text()
    assert "set -euo pipefail" in text
    assert "eval" not in text
    assert not re.search(r"^\s*(?:source|\.)\s+", text, re.MULTILINE)


def test_hook_validates_kiosk_account_boundary() -> None:
    text = _text()
    for value in (
        "getent passwd kiosk",
        "getent shadow kiosk",
        "/usr/sbin/nologin",
        "/nonexistent",
        "uid",
        "gid",
        "audio video render input",
        "root sudo adm wheel disk shadow",
    ):
        assert value in text


def test_hook_validates_dedicated_setup_account_boundary() -> None:
    text = _text()
    for value in (
        "getent passwd wifi-setup",
        "getent shadow wifi-setup",
        'id -nG wifi-setup)" = "wifi-setup"',
        "wifi-setup has supplementary groups",
    ):
        assert value in text


def test_hook_validates_required_packages() -> None:
    text = _text()
    for package in (
        "live-boot", "cage", "chromium", "network-manager", "polkitd", "pipewire",
        "wireplumber", "libgl1-mesa-dri", "libgbm1", "python3-minimal", "python3",
    ):
        assert package in text
    assert "dpkg-query" in text
    assert "require_package" in text


def test_hook_rejects_prohibited_packages() -> None:
    text = _text()
    for package in (
        "openssh-server", "dropbear", "sudo", "xterm", "gdm3",
        "xserver-xorg", "nvidia-driver",
    ):
        assert package in text
    assert "reject_package" in text


def test_hook_parses_and_checks_policy() -> None:
    text = _text()
    assert "json.load" in text
    for policy in (
        "DeveloperToolsAvailability",
        "BrowserGuestModeEnabled",
        "IncognitoModeAvailability",
        "DownloadRestrictions",
        "URLBlocklist",
        "URLAllowlist",
    ):
        assert policy in text
    assert "https://.sushida.net:443" in text
    assert "file:///usr/share/sushida-os/offline.html" in text
    assert '"http://127.0.0.1:8787"' in text


def test_hook_validates_units_and_lockdown() -> None:
    text = _text()
    assert "systemd-analyze verify" in text
    assert "systemctl is-enabled" in text
    for unit in (
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-config-prepare.service",
        "sushida-wifi-setup.service",
        "var-lib-sushida\\x2dconfig.mount",
        "getty@.service",
        "serial-getty@.service",
        "ctrl-alt-del.target",
        "apt-daily.timer",
        "apt-daily-upgrade.timer",
        "apt-daily.service",
        "apt-daily-upgrade.service",
    ):
        assert unit in text


def test_hook_validates_jis_keyboard_and_session_environment() -> None:
    text = _text()
    for value in (
        "/etc/default/keyboard",
        "XKBMODEL=\"pc105\"",
        "XKBLAYOUT=\"jp\"",
        "XKBVARIANT=\"106\"",
        "XKBOPTIONS=\"\"",
        "BACKSPACE=\"guess\"",
        "-name 'cached_*.kmap.gz'",
        "cached_setup_keyboard.sh",
        "Environment=XKB_DEFAULT_MODEL=pc105",
        "Environment=XKB_DEFAULT_LAYOUT=jp",
        "Environment=XKB_DEFAULT_VARIANT=106",
        "Environment=XKB_DEFAULT_OPTIONS=",
        "setupcon",
        "HandlePowerKey=poweroff",
        "HandlePowerKeyLongPress=ignore",
        "PowerKeyIgnoreInhibited=yes",
        "custom power event daemon",
    ):
        assert value in text


def test_hook_validates_runtime_and_logs() -> None:
    text = _text()
    assert "/usr/lib/tmpfiles.d/sushida-os.conf" in text
    assert "Storage=volatile" in text
    assert "/persistence.conf" in text
    for path in ("home", "chromium", "cache", "tmp", "downloads", "xdg-runtime"):
        assert path in text


def test_hook_validates_executable_ownership_and_wifi_mode() -> None:
    text = _text()
    assert "root:root:755" in text
    assert "root:root:600" in text
    assert "sushida-launch" in text
    assert "sushida-network-watch" in text
    assert "sushida-diagnostics" in text
    assert "sushida-session" in text
    assert "sushida-config-prepare" in text
    assert "sushida-wifi-setup" in text


def test_hook_rejects_unresolved_markers() -> None:
    text = _text()
    assert "unresolved marker" in text
    assert "REPLACE_WITH_" in text


def test_hook_has_single_success_message() -> None:
    assert _text().count("Image validation passed.") == 1
