"""Hotkey volume/brightness control: source, unit, and pure-logic checks.

The input watcher is the only root-owned process that reacts to kiosk-user
keystrokes, so these tests pin its security posture: a fixed key->action
table, constant mixer argv, bounded steps and rate, a brightness floor that
can never black out the panel, and a hardened systemd unit.
"""

from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

DAEMON = Path("live-build/config/includes.chroot/usr/local/libexec/sushida-input-watch")
UNIT = Path("live-build/config/includes.chroot/etc/systemd/system/sushida-input-watch.service")
CONFIG = Path("live-build/config/includes.chroot/etc/sushida-os/config.env")
LAUNCHER = Path("live-build/config/includes.chroot/usr/local/bin/sushida-launch")
SESSION = Path("live-build/config/includes.chroot/usr/local/libexec/sushida-session")
WATCHER = Path("live-build/config/includes.chroot/usr/local/bin/sushida-network-watch")
ENABLE_HOOK = Path("live-build/config/hooks/live/020-enable-services.hook.chroot")
VALIDATE_HOOK = Path("live-build/config/hooks/live/090-validate-image.hook.chroot")


def _load_daemon_module():
    spec = importlib.util.spec_from_loader(
        "sushida_input_watch", loader=None, origin=str(DAEMON)
    )
    module = importlib.util.module_from_spec(spec)
    code = compile(DAEMON.read_text(), str(DAEMON), "exec")
    sys.modules["sushida_input_watch"] = module
    try:
        exec(code, module.__dict__)
    finally:
        del sys.modules["sushida_input_watch"]
    return module


# ── source posture ───────────────────────────────────────────────────────


def test_daemon_is_executable_root_script() -> None:
    assert DAEMON.is_file()
    assert DAEMON.stat().st_mode & stat.S_IXUSR
    text = DAEMON.read_text()
    assert text.startswith("#!/usr/bin/env python3")
    assert "eval" not in text
    assert "TODO" not in text


def test_daemon_actions_are_fixed_and_bounded() -> None:
    text = DAEMON.read_text()
    # Fixed action table over exactly the five media keys.
    for key in ("KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_MUTE",
                "KEY_BRIGHTNESSUP", "KEY_BRIGHTNESSDOWN"):
        assert text.count(key) == 1, key
    # Constant mixer argv; event data never reaches a subprocess.
    assert '[AMIXER, "-q", *args]' in text
    assert 'AMIXER = "/usr/bin/amixer"' in text
    assert "shell=True" not in text
    # Bounded steps and rate limit.
    assert "VOLUME_STEP_PERCENT = 5" in text
    assert "BRIGHTNESS_STEP_PERCENT = 10" in text
    assert "MIN_ACTION_INTERVAL_SECONDS = 0.15" in text
    # Fixed log tokens only (P5).
    assert 'print(f"action={name}", flush=True)' in text


def test_daemon_reads_only_the_fixed_config_and_sysfs_paths() -> None:
    text = DAEMON.read_text()
    assert 'CONFIG_FILE = Path("/etc/sushida-os/config.env")' in text
    assert 'BACKLIGHT_ROOT = Path("/sys/class/backlight")' in text


# ── pure logic ───────────────────────────────────────────────────────────


def test_brightness_clamp_never_reaches_zero() -> None:
    module = _load_daemon_module()
    for max_raw in (1, 7, 100, 255, 19200):
        for percent in (0, 1, 5, 50, 100, 999):
            raw = module.clamp_brightness_raw(percent, max_raw)
            assert 1 <= raw <= max_raw, (percent, max_raw, raw)
    assert module.clamp_brightness_raw(100, 19200) == 19200
    assert module.clamp_brightness_raw(50, 200) == 100


def test_config_percent_parser_fails_closed(tmp_path: Path) -> None:
    module = _load_daemon_module()
    config = tmp_path / "config.env"

    def read(content: str) -> int:
        config.write_text(content)
        return module.read_config_percent(
            "SCREEN_BRIGHTNESS_PERCENT", 80, 5, 100, path=config
        )

    assert read("SCREEN_BRIGHTNESS_PERCENT=40\n") == 40
    assert read("SCREEN_BRIGHTNESS_PERCENT=100\n") == 100
    assert read("# comment only\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=0\n") == 80  # below floor
    assert read("SCREEN_BRIGHTNESS_PERCENT=101\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=-5\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=abc\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=$(reboot)\n") == 80
    missing = module.read_config_percent(
        "SCREEN_BRIGHTNESS_PERCENT", 80, 5, 100, path=tmp_path / "absent"
    )
    assert missing == 80


# ── systemd unit ─────────────────────────────────────────────────────────


def test_unit_is_hardened_root_service() -> None:
    text = UNIT.read_text()
    assert "ExecStart=/usr/local/libexec/sushida-input-watch\n" in text
    assert "Restart=always\n" in text
    assert "NoNewPrivileges=true\n" in text
    assert "CapabilityBoundingSet=\n" in text
    assert "AmbientCapabilities=\n" in text
    assert "ProtectSystem=strict\n" in text
    assert "ProtectHome=yes\n" in text
    assert "PrivateNetwork=yes\n" in text
    assert "DevicePolicy=closed\n" in text
    assert "DeviceAllow=char-input rw\n" in text
    assert "DeviceAllow=char-alsa rw\n" in text
    assert "MemoryDenyWriteExecute=yes\n" in text
    assert "SystemCallArchitectures=native\n" in text
    assert "WantedBy=multi-user.target\n" in text
    # /sys/class/backlight writes require kernel tunables to stay writable;
    # PrivateDevices would hide /dev/input and /dev/snd.
    assert "ProtectKernelTunables" not in text
    assert "PrivateDevices" not in text


# ── config plumbing ──────────────────────────────────────────────────────


def test_config_env_declares_boot_defaults() -> None:
    text = CONFIG.read_text()
    assert "AUDIO_VOLUME_PERCENT=70\n" in text
    assert "SCREEN_BRIGHTNESS_PERCENT=80\n" in text


def test_launcher_validates_and_exports_volume() -> None:
    text = LAUNCHER.read_text()
    assert "AUDIO_VOLUME_PERCENT)" in text
    assert "SCREEN_BRIGHTNESS_PERCENT) ;;" in text
    assert 'export SUSHIDA_AUDIO_VOLUME_PERCENT="$AUDIO_VOLUME_PERCENT"' in text
    assert "AUDIO_VOLUME_PERCENT exceeds maximum 100" in text


def test_session_applies_volume_best_effort() -> None:
    text = SESSION.read_text()
    assert 'wpctl set-volume @DEFAULT_AUDIO_SINK@' in text
    assert 'wpctl set-mute @DEFAULT_AUDIO_SINK@ 0' in text
    # Guarded: absent config, missing wpctl, or wpctl failure never break
    # the session.
    assert "command -v wpctl" in text
    assert text.count("|| true") >= 2


def test_network_watch_tolerates_the_new_keys() -> None:
    text = WATCHER.read_text()
    assert "AUDIO_VOLUME_PERCENT) ;;" in text
    assert "SCREEN_BRIGHTNESS_PERCENT) ;;" in text


# ── image registration ───────────────────────────────────────────────────


def test_service_is_enabled_and_validated_in_hooks() -> None:
    assert "systemctl enable sushida-input-watch.service" in ENABLE_HOOK.read_text()
    validate = VALIDATE_HOOK.read_text()
    assert "/usr/local/libexec/sushida-input-watch" in validate
    assert "sushida-input-watch.service" in validate
    for package in ("alsa-utils", "python3-evdev", "firmware-sof-signed",
                    "alsa-ucm-conf"):
        assert package in validate, package
