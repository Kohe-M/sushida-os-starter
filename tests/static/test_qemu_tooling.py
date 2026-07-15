"""Static checks for bounded and non-invasive QEMU tooling."""

import os
import stat
from pathlib import Path


RUN = Path("scripts/run-qemu.sh")
SMOKE = Path("scripts/smoke-test.sh")
CHECK = Path("tests/qemu/smoke-test.sh")
MAKEFILE = Path("Makefile")
DOCKERFILE = Path("builder/Dockerfile")
ISOLINUX = Path("live-build/config/bootloaders/isolinux/isolinux.cfg")
ISOLINUX_LIVE = Path("live-build/config/bootloaders/isolinux/live.cfg")
GRUB = Path("live-build/config/bootloaders/grub-pc/config.cfg")


def test_qemu_scripts_are_executable_and_strict() -> None:
    for path in (RUN, SMOKE, CHECK):
        assert path.is_file()
        assert path.stat().st_mode & stat.S_IXUSR
        assert os.access(path, os.X_OK)
        text = path.read_text()
        assert "set -euo pipefail" in text
        assert "TODO" not in text
        assert "eval" not in text


def test_runner_supports_bios_uefi_offline_and_evidence() -> None:
    text = RUN.read_text()
    for token in ("bios", "uefi", "OVMF_CODE", "OVMF_VARS", "-nic none"):
        assert token in text
    assert "serial.log" in text
    assert "screenshot.png" in text
    assert "screendump" in text
    assert "-f png" in text
    assert "--duration" in text


def test_runner_never_attaches_a_host_disk_or_debug_shell() -> None:
    text = RUN.read_text()
    assert "artifacts/sushida-os-amd64.iso" in text
    assert "media=cdrom,readonly=on" in text
    assert "/dev/sd" not in text
    assert "/dev/nvme" not in text
    assert "-kernel" not in text
    assert "init=/bin/sh" not in text
    assert "rd.break" not in text


def test_smoke_report_distinguishes_automated_and_manual_checks() -> None:
    text = CHECK.read_text()
    assert "AUTOMATED:" in text
    assert "MANUAL:" in text
    assert "UNVERIFIED" in text
    assert "login:" in text


def test_make_qemu_targets_call_real_scripts() -> None:
    text = MAKEFILE.read_text()
    assert "test-qemu:\n\t./scripts/smoke-test.sh" in text
    assert "qemu:\n\t./scripts/run-qemu.sh" in text


def test_builder_has_qemu_uefi_and_monitor_tools() -> None:
    text = DOCKERFILE.read_text()
    for package in ("qemu-system-x86", "ovmf", "socat"):
        assert package in text


def test_bios_and_uefi_boot_menus_have_bounded_autoboot() -> None:
    isolinux = ISOLINUX.read_text()
    grub = GRUB.read_text()
    assert "default vesamenu.c32" in isolinux
    assert "timeout 30" in isolinux
    assert "timeout 0" not in isolinux
    assert "set default=1" in grub
    assert "set timeout=3" in grub
    assert "set timeout=0" not in grub


def test_software_rendering_is_confined_to_explicit_qemu_entries() -> None:
    isolinux = ISOLINUX_LIVE.read_text()
    grub = GRUB.read_text()
    runner = RUN.read_text()
    smoke = SMOKE.read_text()
    marker = "systemd.setenv=WLR_RENDERER_ALLOW_SOFTWARE=1"
    renderer = "systemd.setenv=WLR_RENDERER=pixman"

    assert marker in isolinux
    assert marker in grub
    assert renderer in isolinux
    assert renderer in grub
    assert sum(line.startswith("label ") for line in isolinux.splitlines()) == 1
    assert "label qemu-smoke-amd64" in isolinux
    assert "menu default" not in isolinux
    assert marker not in GRUB.read_text().split("menuentry \"QEMU smoke", 1)[0]
    assert "--hotkey=q" in grub
    assert "--qemu-smoke" in runner
    assert "BdsDxe: starting Boot" in runner
    assert "sendkey esc" in runner
    assert "sendkey up" in runner
    assert "sendkey q" in runner
    assert "QEMU_BOOT_MARKER" in runner
    assert 'grep -Fq "$QEMU_BOOT_MARKER"' in runner
    assert "for _wave" in runner
    assert "for _quiet" in runner
    assert smoke.count("--qemu-smoke") == 2
