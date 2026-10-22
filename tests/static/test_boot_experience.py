"""Boot experience: silent kernel command line, Plymouth splash, handoff.

These are posture checks on bootloader and unit configuration that only a
real boot can exercise; the handoff and read-ahead helpers themselves are
executed in tests/shell/boot-splash.bats.
"""

import re
from pathlib import Path

AUTO_CONFIG = Path("live-build/auto/config")
GRUB = Path("live-build/config/bootloaders/grub-pc/config.cfg")
ISOLINUX_LIVE = Path("live-build/config/bootloaders/isolinux/live.cfg")
CHROOT = Path("live-build/config/includes.chroot")
PLYMOUTH_CONF = CHROOT / "etc/plymouth/plymouthd.conf"
QUIT_DROPIN = CHROOT / "etc/systemd/system/plymouth-quit.service.d/90-sushida-kiosk.conf"
PRELOAD_UNIT = CHROOT / "etc/systemd/system/sushida-preload.service"
PRELOAD = CHROOT / "usr/local/libexec/sushida-preload"
HANDOFF = CHROOT / "usr/local/libexec/sushida-splash-handoff"
PACKAGE_LIST = Path("live-build/config/package-lists/kiosk.list.chroot")

SILENT_BOOT_TOKENS = (
    "boot=live", "components", "quiet", "splash", "loglevel=3",
    "rd.udev.log_level=3", "udev.log_level=3",
    "systemd.show_status=false", "rd.systemd.show_status=false",
    "vt.global_cursor_default=0",
    "plymouth.ignore-serial-consoles", "plymouth.use-simpledrm",
)
# Parameters that would open a shell, skip the kiosk, or weaken the image.
FORBIDDEN_TOKEN_PREFIXES = (
    "init=", "rdinit=", "single", "emergency", "rescue", "systemd.unit=",
    "systemd.debug-shell", "rd.break", "rd.shell", "nosplash",
    "plymouth.enable=0", "persistence", "systemd.setenv=",
)


def _auto_config_cmdline() -> list[str]:
    match = re.search(r'^BOOTAPPEND_LIVE="([^"]*)"$', AUTO_CONFIG.read_text(), re.M)
    assert match, "BOOTAPPEND_LIVE not found"
    return match.group(1).split()


def _grub_cmdline() -> list[str]:
    lines = [l.strip() for l in GRUB.read_text().splitlines()
             if l.strip().startswith("linux")]
    assert len(lines) == 1, lines
    return lines[0].split()[2:]


def _isolinux_cmdline() -> list[str]:
    lines = [l.strip() for l in ISOLINUX_LIVE.read_text().splitlines()
             if l.strip().startswith("append ")]
    assert len(lines) == 1, lines
    return lines[0].split()[1:]


def _unit_values(path: Path, key: str) -> list[str]:
    return [l.split("=", 1)[1] for l in path.read_text().splitlines()
            if l.startswith(f"{key}=")]


def test_kernel_command_line_is_identical_in_every_boot_path() -> None:
    assert _grub_cmdline() == _auto_config_cmdline()
    assert _isolinux_cmdline() == _auto_config_cmdline()


def test_kernel_command_line_is_silent_and_splash_enabled() -> None:
    tokens = _auto_config_cmdline()
    for token in SILENT_BOOT_TOKENS:
        assert token in tokens, token
    assert "systemd.show_status=true" not in tokens


def test_kernel_command_line_has_no_escape_or_debug_parameters() -> None:
    for token in _auto_config_cmdline():
        for prefix in FORBIDDEN_TOKEN_PREFIXES:
            assert not token.startswith(prefix), token


def test_grub_shows_no_theme_menu_or_beep() -> None:
    text = "\n".join(l for l in GRUB.read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    for needle in ("theme", "gfxterm", "loadfont", "play ", "echo "):
        assert needle not in text, needle


def test_plymouth_packages_and_firmware_logo_theme() -> None:
    packages = PACKAGE_LIST.read_text().split()
    assert "plymouth" in packages
    assert "plymouth-themes" in packages
    lines = PLYMOUTH_CONF.read_text().splitlines()
    assert "[Daemon]" in lines
    assert "Theme=bgrt" in lines


def test_plymouth_quits_through_the_bounded_kiosk_handoff() -> None:
    assert _unit_values(QUIT_DROPIN, "ExecStartPre") == [
        "-/usr/local/libexec/sushida-splash-handoff"
    ]
    # The empty assignment resets the packaged ExecStart before replacing it.
    assert _unit_values(QUIT_DROPIN, "ExecStart") == [
        "", "-/usr/bin/plymouth quit --retain-splash"
    ]
    timeout = int(_unit_values(QUIT_DROPIN, "TimeoutSec")[0])
    handoff_wait = int(re.search(
        r"^readonly PROD_MAX_WAIT_SECONDS=(\d+)$", HANDOFF.read_text(), re.M
    ).group(1))
    assert handoff_wait < timeout, "systemd must not kill the bounded wait"
    assert _unit_values(QUIT_DROPIN, "NoNewPrivileges") == ["yes"]


def test_preload_never_delays_boot_and_runs_unprivileged() -> None:
    assert _unit_values(PRELOAD_UNIT, "Type") == ["exec"]
    assert _unit_values(PRELOAD_UNIT, "DynamicUser") == ["yes"]
    assert _unit_values(PRELOAD_UNIT, "CapabilityBoundingSet") == [""]
    assert _unit_values(PRELOAD_UNIT, "PrivateNetwork") == ["yes"]
    assert _unit_values(PRELOAD_UNIT, "ProtectSystem") == ["strict"]
    assert _unit_values(PRELOAD_UNIT, "NoNewPrivileges") == ["yes"]
    assert _unit_values(PRELOAD_UNIT, "WantedBy") == ["sysinit.target"]
    for key in ("Before", "RequiredBy"):
        for value in _unit_values(PRELOAD_UNIT, key):
            assert "sushida-kiosk" not in value


def test_preload_reads_only_a_fixed_list_under_usr() -> None:
    text = PRELOAD.read_text()
    files = re.findall(r"^\s+(/\S+)$", text, re.M)
    assert files, "fixed preload list not found"
    for path in files:
        assert path.startswith("/usr/"), path
    assert "$1" not in text and "$@" not in text
    assert "eval" not in text


SERIAL_MARKER = CHROOT / "usr/local/libexec/sushida-serial-marker"
SHUTDOWN_MARKER_UNIT = CHROOT / "etc/systemd/system/sushida-shutdown-marker.service"


def test_serial_marker_writes_only_to_the_first_serial_port() -> None:
    text = "\n".join(l for l in SERIAL_MARKER.read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    assert 'readonly PROD_SERIAL_DEVICE="/dev/ttyS0"' in text
    # Never the console or a VT: the marker must not reach the screen.
    for device in ("/dev/console", "/dev/tty0", "/dev/tty1", "/dev/kmsg"):
        assert device not in text, device
    assert "timeout 2 dd" in text
    assert "eval" not in text


def test_splash_handoff_reports_through_the_serial_marker() -> None:
    text = HANDOFF.read_text()
    assert 'readonly PROD_MARKER="/usr/local/libexec/sushida-serial-marker"' in text
    assert '"$MARKER" kiosk-route-published' in text
    assert '"$MARKER" splash-timeout' in text


def test_shutdown_marker_reports_after_the_config_filesystem_stops() -> None:
    before = " ".join(_unit_values(SHUTDOWN_MARKER_UNIT, "Before"))
    # Started before the mount, so it is stopped after the unmount.
    assert "var-lib-sushida\\x2dconfig.mount" in before
    assert "shutdown.target" in before
    assert _unit_values(SHUTDOWN_MARKER_UNIT, "DefaultDependencies") == ["no"]
    assert _unit_values(SHUTDOWN_MARKER_UNIT, "Conflicts") == ["shutdown.target"]
    assert _unit_values(SHUTDOWN_MARKER_UNIT, "ExecStop") == [
        "/usr/local/libexec/sushida-serial-marker shutdown"
    ]
    assert _unit_values(SHUTDOWN_MARKER_UNIT, "CapabilityBoundingSet") == [""]
    assert _unit_values(SHUTDOWN_MARKER_UNIT, "NoNewPrivileges") == ["yes"]
    assert int(_unit_values(SHUTDOWN_MARKER_UNIT, "TimeoutStopSec")[0]) <= 10
