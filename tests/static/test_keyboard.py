"""Static checks for physical Japanese JIS keyboard propagation."""

import os
import stat
from pathlib import Path


KEYBOARD = Path("live-build/config/includes.chroot/etc/default/keyboard")
SERVICE = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
)
HOOK = Path("live-build/config/hooks/live/035-configure-keyboard.hook.chroot")


def test_default_keyboard_is_exact_jis_configuration() -> None:
    assert KEYBOARD.read_text().splitlines() == [
        'XKBMODEL="pc105"',
        'XKBLAYOUT="jp"',
        'XKBVARIANT="106"',
        'XKBOPTIONS=""',
        'BACKSPACE="guess"',
    ]


def test_kiosk_service_exports_jis_environment_to_cage_and_chromium() -> None:
    text = SERVICE.read_text()
    for line in (
        "Environment=XKB_DEFAULT_MODEL=pc105",
        "Environment=XKB_DEFAULT_LAYOUT=jp",
        "Environment=XKB_DEFAULT_VARIANT=106",
        "Environment=XKB_DEFAULT_OPTIONS=",
    ):
        assert line in text
    assert "ExecStart=/usr/local/bin/sushida-launch" in text


def test_chroot_hook_generates_jis_console_cache() -> None:
    assert HOOK.is_file()
    assert HOOK.stat().st_mode & stat.S_IXUSR
    assert os.access(HOOK, os.X_OK)
    text = HOOK.read_text()
    assert "set -euo pipefail" in text
    assert "setupcon --save-only" in text
    assert "-name 'cached_*.kmap.gz'" in text
    assert "cache_file" in text
    assert "cached_setup_keyboard.sh" in text
    assert "-name 'cached*' -delete" in text
    assert "XKBLAYOUT=\"jp\"" in text
    assert "XKBVARIANT=\"106\"" in text
    assert "rm -f" in text
    assert "TODO" not in text


def test_no_input_interceptor_or_ime_is_added_for_jis() -> None:
    package_list = Path("live-build/config/package-lists/kiosk.list.chroot").read_text()
    assert "ibus" not in package_list.lower()
    assert "fcitx" not in package_list.lower()
    assert "input-interceptor" not in package_list.lower()
