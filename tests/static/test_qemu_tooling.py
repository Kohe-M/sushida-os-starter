"""Static checks for bounded and non-invasive QEMU tooling."""

import os
import stat
import subprocess
from pathlib import Path


RUN = Path("scripts/run-qemu.sh")
SMOKE = Path("scripts/smoke-test.sh")
POWERDOWN = Path("scripts/powerdown-test.sh")
CHECK = Path("tests/qemu/smoke-test.sh")
POWERDOWN_CHECK = Path("tests/qemu/powerdown-test.sh")
SCREENSHOT_CHECK = Path("tests/qemu/check-screenshot.py")
MAKEFILE = Path("Makefile")
DOCKERFILE = Path("builder/Dockerfile")
ISOLINUX = Path("live-build/config/bootloaders/isolinux/isolinux.cfg")
ISOLINUX_LIVE = Path("live-build/config/bootloaders/isolinux/live.cfg")
GRUB = Path("live-build/config/bootloaders/grub-pc/config.cfg")


def test_qemu_scripts_are_executable_and_strict() -> None:
    for path in (RUN, SMOKE, POWERDOWN, CHECK, POWERDOWN_CHECK, SCREENSHOT_CHECK):
        assert path.is_file()
        assert path.stat().st_mode & stat.S_IXUSR
        assert os.access(path, os.X_OK)
        text = path.read_text()
        if path.suffix == ".sh":
            assert "set -euo pipefail" in text
        assert "TODO" not in text
        assert "eval" not in text


def test_runner_supports_bios_uefi_offline_and_evidence() -> None:
    text = RUN.read_text()
    for token in ("bios", "uefi", "OVMF_CODE", "OVMF_VARS", "-nic none"):
        assert token in text
    assert "hostfwd" not in text
    assert "serial.log" in text
    assert "screenshot.png" in text
    assert "screenshot.ppm" in text
    assert "smoke-report.txt" in text
    assert "screendump" in text
    assert "-f png" in text
    assert "--duration" in text
    assert "ISO_SHA256" in text
    assert "RUN_STARTED_AT" in text
    assert "RUN_FINISHED_AT" in text


def test_powerdown_mode_is_monitor_only_and_bounded() -> None:
    runner = RUN.read_text()
    script = POWERDOWN.read_text()
    checker = POWERDOWN_CHECK.read_text()
    assert "--powerdown" in runner
    assert "system_powerdown" in runner
    assert "MONITOR_SOCKET" in runner
    assert "build/qemu" in runner
    assert "--writable-media" in script
    assert "--powerdown" in script
    assert "POWERDOWN_SENT" in runner
    assert "NATURAL_POWERDOWN" in runner
    assert r"poweroff\.target" in checker
    assert "var-lib-sushida\\x2dcon" in checker
    assert "SUSHIDA-CFG mount has a shutdown failure" in checker
    assert "GIT_COMMIT" in runner
    assert "build-info.json" in checker
    assert "SHA256SUMS" in checker
    assert "CONFIG_MOUNT_SEEN" in runner
    assert "CONFIG_UNMOUNT_SEEN" in runner
    assert "Started[[:space:]]+sushida-kiosk" in checker
    for forbidden in ("\npoweroff ", "\nshutdown ", "\nreboot "):
        assert forbidden not in runner.lower()
        assert forbidden not in script.lower()


def test_screenshot_checker_rejects_blank_frames(tmp_path: Path) -> None:
    def check(
        name: str, pixels: bytes, png: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        capture = tmp_path / name
        capture.write_bytes(b"P6\n100 100\n255\n" + pixels)
        command = [str(SCREENSHOT_CHECK), str(capture)]
        if png is not None:
            command.append(str(png))
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    offline_like = bytearray(bytes((17, 17, 17)) * 10_000)
    for y in range(45, 55):
        for x in range(30, 70):
            offset = (y * 100 + x) * 3
            offline_like[offset : offset + 3] = bytes((240, 240, 240))
    png = tmp_path / "offline-like.png"
    assert check("offline-like.ppm", bytes(offline_like), png).returncode == 0
    assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert check("white.ppm", bytes((255, 255, 255)) * 10_000).returncode != 0
    assert check("black.ppm", bytes((0, 0, 0)) * 10_000).returncode != 0


def test_runner_never_attaches_a_host_disk_or_debug_shell() -> None:
    text = RUN.read_text()
    assert "artifacts/sushida-os-amd64.iso" in text
    assert "media=cdrom,readonly=on" in text
    assert "/dev/sd" not in text
    assert "/dev/nvme" not in text
    # The direct-kernel boot is acceptable for the isolated QEMU smoke entry.
    # Debug shell init=/bin/sh or rd.break must never appear.
    assert "init=/bin/sh" not in text
    assert "rd.break" not in text


def test_runner_can_boot_an_isolated_writable_copy_for_config_tests() -> None:
    text = RUN.read_text()
    assert "--writable-media" in text
    assert 'WRITABLE_MEDIA="$RUN_DIR/writable-media.img"' in text
    assert 'cp --reflink=auto -- "$ISO" "$WRITABLE_MEDIA"' in text
    assert 'file=$WRITABLE_MEDIA,format=raw,if=virtio' in text
    assert 'QEMU_ARGS+=( -boot "order=c" )' in text
    assert 'QEMU_ARGS+=( -boot "order=d" )' in text


def test_smoke_report_distinguishes_automated_and_manual_checks() -> None:
    text = CHECK.read_text()
    assert "AUTOMATED:" in text
    assert "MANUAL:" in text
    assert "UNVERIFIED" in text
    assert "login:" in text
    assert "ModuleNotFoundError" in text
    assert "Wi-Fi setup or watcher service failure" in text
    assert "Invalid pattern file://" in text
    assert "result_value()" in text
    assert "result_sha" in text
    assert "current_sha" in text
    assert "ISO SHA-256 matches the current release artifact" in text
    assert "RUN_STARTED_AT=$run_started" in text
    assert "RUN_FINISHED_AT=$run_finished" in text


def test_make_qemu_targets_call_real_scripts() -> None:
    text = MAKEFILE.read_text()
    assert "test-qemu-boot:\n\t./scripts/boot-test.sh" in text
    assert "test-qemu-runtime:\n\t./scripts/smoke-test.sh" in text
    assert "test-qemu-powerdown:\n\t./scripts/powerdown-test.sh" in text
    assert "qemu:\n\t./scripts/run-qemu.sh" in text


def test_qemu_smoke_checks_systemd_escaped_mount_name() -> None:
    text = CHECK.read_text()
    assert r"'var-lib-sushida\x2dconfig'" in text
    assert r"'var-lib-sushida\\x2dconfig'" not in text
    for unit_prefix in (
        "sushida-config-prepare",
        "sushida-wifi-setup",
        "sushida-kiosk",
        "sushida-network-watch",
    ):
        assert f"'{unit_prefix}'" in text


def test_builder_has_qemu_uefi_and_monitor_tools() -> None:
    text = DOCKERFILE.read_text()
    for package in ("qemu-system-x86", "ovmf", "socat"):
        assert package in text


def test_bios_and_uefi_boot_menus_have_bounded_autoboot() -> None:
    isolinux = ISOLINUX.read_text()
    grub = GRUB.read_text()
    assert "default vesamenu.c32" in isolinux
    assert "TIMEOUT 30" in isolinux or "timeout 30" in isolinux
    assert "timeout 0" not in isolinux
    assert "ALLOWOPTIONS 0" in isolinux
    assert "NOESCAPE 1" in isolinux
    assert "set default=0" in grub
    assert "set timeout=3" in grub
    assert "set timeout=0" not in grub
    assert '--unrestricted' in grub
    assert 'set superusers="kiosk"' in grub


def test_software_rendering_is_confined_to_explicit_qemu_entries() -> None:
    isolinux = ISOLINUX_LIVE.read_text()
    grub = GRUB.read_text()
    runner = RUN.read_text()
    smoke = SMOKE.read_text()
    marker = "systemd.setenv=WLR_RENDERER_ALLOW_SOFTWARE=1"
    renderer = "systemd.setenv=WLR_RENDERER=pixman"
    chromium_renderer = "systemd.setenv=SUSHIDA_QEMU_CHROMIUM_SWIFTSHADER=1"
    force_offline = "systemd.setenv=SUSHIDA_QEMU_FORCE_OFFLINE=1"

    # Production bootloader configs must not carry the software-renderer
    # markers; they are passed only through direct kernel boot in the
    # QEMU-only test path.
    assert marker not in isolinux
    assert marker not in grub
    assert renderer not in isolinux
    assert renderer not in grub
    assert chromium_renderer not in isolinux
    assert chromium_renderer not in grub
    assert force_offline not in isolinux
    assert force_offline not in grub
    assert "--qemu-smoke" in runner
    # The QEMU-only test uses xorriso to extract the kernel and initrd from
    # the production ISO, then boots with a direct software-renderer cmdline.
    assert "QEMU_ARGS+=(" in runner
    assert "-kernel " in runner
    assert "EXTRACT_DIR/vmlinuz" in runner
    assert "QEMU_BOOT_MARKER" in runner
    assert 'grep -Fq "$QEMU_BOOT_MARKER"' in runner
    # Hotkey-based selection is no longer needed; the kernel cmdline is
    # passed directly.
    assert "sendkey esc" not in runner
    assert "sendkey up" not in runner
    assert "sendkey q" not in runner
    assert "BdsDxe: starting Boot" not in runner
    assert "xorriso -indev" in runner
    assert "EXTRACT_DIR" in runner
    assert 'QEMU_ARGS+=(-vga std)' in runner
    assert 'QEMU_ARGS+=(-device virtio-vga)' in runner
    assert 'rm -f -- "$SERIAL_LOG" "$SCREENSHOT" "$SCREENSHOT_PPM" "$MONITOR_SOCKET"' in runner
    assert '"$RESULT_FILE" "$REPORT"' in runner
    assert runner.index('if [ "$DRY_RUN" = true ]; then') < runner.index('mkdir -p "$QEMU_ROOT" "$RUN_DIR"')
    assert runner.index('if [ "$DRY_RUN" = true ]; then') < runner.index('cp -- "$OVMF_VARS" "$VARS_COPY"')
    assert "[ -c /dev/kvm ]" in runner
    assert 'QEMU_ACCEL="tcg"' in runner
    assert 'QEMU_ACCEL="kvm:tcg"' in runner
    assert "SCREENSHOT_PPM" in runner
    assert "for _capture in $(seq 1 6)" in runner
    assert "partial scanout" in SCREENSHOT_CHECK.read_text()
    assert "spatial coverage" in SCREENSHOT_CHECK.read_text()
    assert "check-screenshot.py" in CHECK.read_text()
    assert smoke.count("--qemu-smoke") == 2
    assert smoke.count("--writable-media") == 2
    assert "SUSHIDA_QEMU_BIOS_DURATION" in smoke
    assert "SUSHIDA_QEMU_UEFI_DURATION" in smoke
    assert smoke.count('SUSHIDA_QEMU_DURATION:-300') == 2
