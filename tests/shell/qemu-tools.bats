#!/usr/bin/env bats

@test "QEMU BIOS dry run uses only the release ISO and offline NIC" {
    run scripts/run-qemu.sh --firmware bios --offline --headless --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"qemu-system-x86_64"* ]]
    [[ "$output" == *"sushida-os-amd64.iso"* ]]
    [[ "$output" == *"media=cdrom"* ]]
    [[ "$output" == *"readonly=on"* ]]
    [[ "$output" == *"-nic none"* ]]
    [[ "$output" != *"hostfwd"* ]]
    [[ "$output" != *"/dev/sd"* ]]
    [[ "$output" != *"/dev/nvme"* ]]
}

@test "QEMU UEFI dry run uses readonly code and a per-run vars copy" {
    run scripts/run-qemu.sh --firmware uefi --offline --headless --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"if=pflash"* ]]
    [[ "$output" == *"readonly=on"* ]]
    [[ "$output" == *"OVMF_VARS.fd"* ]]
}

@test "QEMU smoke selection is explicit and keeps the ISO read-only" {
    run scripts/run-qemu.sh --firmware bios --offline --headless --qemu-smoke --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"media=cdrom"* ]]
    [[ "$output" == *"readonly=on"* ]]
}

@test "QEMU writable-media dry run uses only a repository-local ISO copy" {
    run scripts/run-qemu.sh --firmware bios --offline --headless --writable-media --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"writable-media.img"* ]]
    [[ "$output" == *"format=raw"* ]]
    [[ "$output" == *"if=virtio"* ]]
    [[ "$output" == *"order=c"* ]]
    [[ "$output" != *"media=cdrom"* ]]
    [[ "$output" != *"/dev/sd"* ]]
    [[ "$output" != *"/dev/nvme"* ]]
}

@test "QEMU dry run preserves existing evidence" {
    test_root="$BATS_TEST_TMPDIR/qemu-repository"
    mkdir -p "$test_root/scripts" "$test_root/artifacts" \
        "$test_root/build/qemu/bios-offline" "$test_root/bin"
    cp scripts/run-qemu.sh "$test_root/scripts/run-qemu.sh"
    chmod 0755 "$test_root/scripts/run-qemu.sh"
    printf 'fake ISO\n' > "$test_root/artifacts/sushida-os-amd64.iso"
    printf '#!/bin/sh\nexit 0\n' > "$test_root/bin/qemu-system-x86_64"
    chmod 0755 "$test_root/bin/qemu-system-x86_64"

    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        printf 'preserve:%s\n' "$file" > "$test_root/build/qemu/bios-offline/$file"
    done

    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        sha256sum "$test_root/build/qemu/bios-offline/$file" \
            > "$test_root/build/qemu/bios-offline/$file.sha256"
    done

    run env PATH="$test_root/bin:$PATH" \
        "$test_root/scripts/run-qemu.sh" --firmware bios --offline \
        --headless --writable-media --duration 1 --dry-run
    [ "$status" -eq 0 ]

    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        run sha256sum --check --strict \
            "$test_root/build/qemu/bios-offline/$file.sha256"
        [ "$status" -eq 0 ]
    done
}

@test "QEMU smoke checker binds evidence to the current ISO" {
    test_root="$BATS_TEST_TMPDIR/qemu-evidence"
    run_dir="$test_root/build/qemu/bios-offline"
    mkdir -p "$test_root/tests/qemu" "$test_root/artifacts" "$run_dir"
    cp tests/qemu/smoke-test.sh "$test_root/tests/qemu/smoke-test.sh"
    cp tests/qemu/check-screenshot.py "$test_root/tests/qemu/check-screenshot.py"
    chmod 0755 "$test_root/tests/qemu/"*.sh "$test_root/tests/qemu/"*.py
    printf 'fixture ISO\n' > "$test_root/artifacts/sushida-os-amd64.iso"
    iso_sha="$(sha256sum "$test_root/artifacts/sushida-os-amd64.iso" | awk '{print $1}')"

    printf '%s\n' \
        'systemd.setenv=WLR_RENDERER=pixman' \
        'var-lib-sushida\x2dconfig' \
        'sushida-config-prepare' \
        'sushida-wifi-setup' \
        'sushida-kiosk' \
        'sushida-network-watch' \
        'sushida-navigation-watch' \
        'graphical.target' > "$run_dir/serial.log"
    printf '%s\n' \
        'QEMU_STATUS=0' \
        "ISO_SHA256=$iso_sha" \
        'RUN_STARTED_AT=2026-07-18T00:00:00Z' \
        'RUN_FINISHED_AT=2026-07-18T00:02:00Z' > "$run_dir/result.env"
    python3 - "$run_dir" <<'PY'
from pathlib import Path
import sys

run_dir = Path(sys.argv[1])
width = height = 100
pixels = bytearray([17, 17, 17]) * (width * height)
for y in range(45, 55):
    for x in range(20, 80):
        offset = (y * width + x) * 3
        pixels[offset : offset + 3] = bytes((240, 240, 240))
(run_dir / "screenshot.ppm").write_bytes(
    f"P6\n{width} {height}\n255\n".encode() + pixels
)
(run_dir / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
PY

    run "$test_root/tests/qemu/smoke-test.sh" bios-offline
    [ "$status" -eq 0 ]
    [[ "$output" == *"ISO_SHA256=$iso_sha"* ]]

    printf 'changed ISO\n' > "$test_root/artifacts/sushida-os-amd64.iso"
    run "$test_root/tests/qemu/smoke-test.sh" bios-offline
    [ "$status" -ne 0 ]
    [[ "$output" == *"does not match current ISO"* ]]
}

@test "QEMU runner rejects invalid firmware" {
    run scripts/run-qemu.sh --firmware coreboot --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"bios or uefi"* ]]
}

@test "QEMU runner rejects unbounded headless execution" {
    run scripts/run-qemu.sh --firmware bios --headless
    [ "$status" -ne 0 ]
    [[ "$output" == *"requires --duration"* ]]
}

@test "QEMU runner rejects nonnumeric duration" {
    run scripts/run-qemu.sh --duration forever --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"non-negative integer"* ]]
}
