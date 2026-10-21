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
    # Fixed log tokens only (P5): action names and ok/failed, nothing
    # device-derived.
    assert 'print(f"action={name} result={outcome}", flush=True)' in text
    assert '"ok" if action() else "failed"' in text
    # The mixer control is always one of the fixed candidates.
    assert 'MIXER_CANDIDATES = ("Master", "PCM", "Speaker", "Headphone")' in text


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
        return module.configured_brightness_percent(config)

    assert read("SCREEN_BRIGHTNESS_PERCENT=40\n") == 40
    assert read("SCREEN_BRIGHTNESS_PERCENT=100\n") == 100
    assert read("# comment only\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=0\n") == 80  # below floor
    assert read("SCREEN_BRIGHTNESS_PERCENT=101\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=-5\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=abc\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=$(reboot)\n") == 80
    missing = module.configured_brightness_percent(tmp_path / "absent")
    assert missing == 80
    # Any invalid config falls back to the default rather than half-trusting it.
    assert read("SCREEN_BRIGHTNESS_PERCENT=40\nEVIL=1\n") == 80
    assert read("SCREEN_BRIGHTNESS_PERCENT=40\nSCREEN_BRIGHTNESS_PERCENT=60\n") == 80


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
    assert "SCREEN_ZOOM_PERCENT=180\n" in text


def test_launcher_reads_boot_defaults_through_the_validator() -> None:
    # Validation itself (ranges, empty = unset) is pinned in test_config.py.
    text = LAUNCHER.read_text()
    assert 'AUDIO_VOLUME_PERCENT="$(config_value AUDIO_VOLUME_PERCENT)"' in text
    assert 'SCREEN_ZOOM_PERCENT="$(config_value SCREEN_ZOOM_PERCENT)"' in text
    assert 'export SUSHIDA_AUDIO_VOLUME_PERCENT="$AUDIO_VOLUME_PERCENT"' in text
    assert 'export SUSHIDA_SCREEN_ZOOM_PERCENT="$SCREEN_ZOOM_PERCENT"' in text


def test_session_applies_volume_best_effort() -> None:
    text = SESSION.read_text()
    assert 'wpctl set-volume @DEFAULT_AUDIO_SINK@' in text
    assert 'wpctl set-mute @DEFAULT_AUDIO_SINK@ 0' in text
    # Guarded: absent config, missing wpctl, or wpctl failure never break
    # the session.
    assert "command -v wpctl" in text
    assert text.count("|| true") >= 2


def test_network_watch_shares_the_validator() -> None:
    # The watcher accepts every key in the shared table instead of keeping
    # its own list that must be updated for each new boot default.
    text = WATCHER.read_text()
    assert "python3 -m sushida_os.config" in text
    assert "case \"$key\" in" not in text


# ── image registration ───────────────────────────────────────────────────


def test_service_is_enabled_and_validated_in_hooks() -> None:
    assert "systemctl enable sushida-input-watch.service" in ENABLE_HOOK.read_text()
    validate = VALIDATE_HOOK.read_text()
    assert "/usr/local/libexec/sushida-input-watch" in validate
    assert "sushida-input-watch.service" in validate
    for package in ("alsa-utils", "python3-evdev", "firmware-sof-signed",
                    "alsa-ucm-conf"):
        assert package in validate, package


def _write_stub_amixer(path: Path, exit_code: int, accept: str = "") -> None:
    """Stub amixer: exit 0 only for a control named in `accept` (all if empty)."""
    lines = ["#!/bin/sh"]
    if accept:
        lines.append(
            'for a in "$@"; do [ "$a" = "%s" ] && exit 0; done; exit 1' % accept
        )
    else:
        lines.append("exit %d" % exit_code)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o755)


def test_volume_actions_report_mixer_success_and_failure(tmp_path: Path) -> None:
    module = _load_daemon_module()
    stub = tmp_path / "amixer"

    _write_stub_amixer(stub, 0)
    module.AMIXER = str(stub)
    assert module.volume_up() is True
    assert module.volume_down() is True
    assert module.volume_mute_toggle() is True

    _write_stub_amixer(stub, 1)
    assert module.volume_up() is False

    module.AMIXER = str(tmp_path / "no-such-amixer")
    assert module.volume_up() is False  # missing binary reports failure


def test_mixer_control_falls_back_through_fixed_candidates(tmp_path: Path) -> None:
    module = _load_daemon_module()
    stub = tmp_path / "amixer"
    module.AMIXER = str(stub)

    # Master missing (SOF-style): the probe settles on PCM.
    _write_stub_amixer(stub, 1, accept="PCM")
    assert module.select_mixer_control() == "PCM"
    assert module.MIXER_CONTROL == "PCM"

    # No candidate at all: default stays Master and actions report failure.
    _write_stub_amixer(stub, 1)
    assert module.select_mixer_control() == "Master"
    assert module.volume_up() is False


def test_boot_brightness_retries_until_backlight_appears(tmp_path: Path) -> None:
    module = _load_daemon_module()
    backlight_root = tmp_path / "backlight"
    module.BACKLIGHT_ROOT = backlight_root
    config = tmp_path / "config.env"
    config.write_text("SCREEN_BRIGHTNESS_PERCENT=40\n")
    module.CONFIG_FILE = config

    # udev race: no device yet — must report unapplied, not give up forever.
    assert module.ensure_boot_brightness() is False
    assert module.ensure_boot_brightness() is False

    device = backlight_root / "intel_backlight"
    device.mkdir(parents=True)
    (device / "max_brightness").write_text("1000\n")
    (device / "brightness").write_text("1000\n")
    assert module.ensure_boot_brightness() is True
    assert (device / "brightness").read_text().strip() == "400"

    # Applied exactly once: later calls no-op even if the value changes.
    (device / "brightness").write_text("777\n")
    assert module.ensure_boot_brightness() is True
    assert (device / "brightness").read_text().strip() == "777"


def _make_backlight(root: Path, max_raw: int, current: int) -> Path:
    device = root / "intel_backlight"
    device.mkdir(parents=True)
    (device / "max_brightness").write_text(f"{max_raw}\n")
    (device / "brightness").write_text(f"{current}\n")
    return device


def test_brightness_steps_are_bounded_and_honest(tmp_path: Path) -> None:
    module = _load_daemon_module()
    module.BACKLIGHT_ROOT = tmp_path / "backlight"

    # No backlight at all: both directions report failure.
    assert module.brightness_up() is False
    assert module.brightness_down() is False

    device = _make_backlight(module.BACKLIGHT_ROOT, 1000, 500)
    level = device / "brightness"
    assert module.brightness_up() is True
    assert level.read_text() == "600\n"
    assert module.brightness_down() is True
    assert module.brightness_down() is True
    assert level.read_text() == "400\n"

    # Ceiling: never above max_brightness.
    level.write_text("950\n")
    assert module.brightness_up() is True
    assert level.read_text() == "1000\n"

    # Floor: repeated presses stop at 5%, never black out the panel.
    for _ in range(15):
        assert module.brightness_down() is True
    assert level.read_text() == "50\n"

    # Unreadable current value or a bogus max_brightness: honest failure,
    # nothing written.
    level.write_text("garbage\n")
    assert module.brightness_up() is False
    assert level.read_text() == "garbage\n"
    level.write_text("500\n")
    (device / "max_brightness").write_text("0\n")
    assert module.brightness_down() is False
    assert module.set_brightness_percent(50) is False
    assert level.read_text() == "500\n"


def test_set_brightness_percent_applies_floor_and_ceiling(tmp_path: Path) -> None:
    module = _load_daemon_module()
    module.BACKLIGHT_ROOT = tmp_path / "backlight"
    assert module.set_brightness_percent(50) is False  # no device

    device = _make_backlight(module.BACKLIGHT_ROOT, 255, 0)
    level = device / "brightness"
    assert module.set_brightness_percent(40) is True
    assert level.read_text() == "102\n"
    assert module.set_brightness_percent(0) is True
    assert level.read_text() == "12\n"  # 5% floor
    assert module.set_brightness_percent(150) is True
    assert level.read_text() == "255\n"
