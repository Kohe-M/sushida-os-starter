#!/usr/bin/env bats

setup() {
    QEMU_FIXTURE="${BATS_TEST_TMPDIR}/qemu-dry-run"
    mkdir -p "$QEMU_FIXTURE/scripts" "$QEMU_FIXTURE/artifacts" \
        "$QEMU_FIXTURE/bin" "$QEMU_FIXTURE/build/qemu/bios-offline"

    # Copy the production script (and the library it sources) so the
    # fixture is self-contained.
    mkdir -p "$QEMU_FIXTURE/scripts/lib"
    cp "$BATS_TEST_DIRNAME/../../scripts/run-qemu.sh" \
        "$QEMU_FIXTURE/scripts/run-qemu.sh"
    cp "$BATS_TEST_DIRNAME/../../scripts/lib/qemu-lib.sh" \
        "$QEMU_FIXTURE/scripts/lib/qemu-lib.sh"
    chmod 0755 "$QEMU_FIXTURE/scripts/run-qemu.sh"

    # Fake ISO — the dry-run path only checks existence.
    printf 'fixture ISO\n' > "$QEMU_FIXTURE/artifacts/sushida-os-amd64.iso"

    # Fake qemu binary so the script passes its pre-flight check.
    printf '#!/bin/sh\nexit 0\n' > "$QEMU_FIXTURE/bin/qemu-system-x86_64"
    chmod 0755 "$QEMU_FIXTURE/bin/qemu-system-x86_64"
}

run_qemu_dry() {
    run env PATH="$QEMU_FIXTURE/bin:$PATH" \
        "$QEMU_FIXTURE/scripts/run-qemu.sh" "$@"
}

@test "QEMU BIOS dry run uses only the release ISO and offline NIC" {
    run_qemu_dry --firmware bios --offline --headless --duration 1 --dry-run
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
    run_qemu_dry --firmware uefi --offline --headless --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"if=pflash"* ]]
    [[ "$output" == *"readonly=on"* ]]
    [[ "$output" == *"OVMF_VARS.fd"* ]]
}

@test "QEMU smoke selection is explicit and keeps the ISO read-only" {
    run_qemu_dry --firmware bios --offline --headless --qemu-smoke --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"media=cdrom"* ]]
    [[ "$output" == *"readonly=on"* ]]
}

@test "QEMU writable-media dry run uses only a repository-local ISO copy" {
    run_qemu_dry --firmware bios --offline --headless --writable-media --duration 1 --dry-run
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
    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        printf 'preserve:%s\n' "$file" > "$QEMU_FIXTURE/build/qemu/bios-offline/$file"
    done
    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        sha256sum "$QEMU_FIXTURE/build/qemu/bios-offline/$file" \
            > "$QEMU_FIXTURE/build/qemu/bios-offline/$file.sha256"
    done

    run_qemu_dry --firmware bios --offline --headless --writable-media --duration 1 --dry-run
    [ "$status" -eq 0 ]

    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        [ -f "$QEMU_FIXTURE/build/qemu/bios-offline/$file" ] || {
            echo "ERROR: evidence file was deleted: $file" >&2
            return 1
        }
    done
    for file in serial.log screenshot.png screenshot.ppm monitor.sock result.env \
        smoke-report.txt writable-media.img; do
        sha256sum -c --quiet "$QEMU_FIXTURE/build/qemu/bios-offline/$file.sha256" || {
            echo "ERROR: evidence file was modified: $file" >&2
            return 1
        }
    done
}

@test "QEMU dry run rejects missing ISO" {
    rm "$QEMU_FIXTURE/artifacts/sushida-os-amd64.iso"
    run_qemu_dry --firmware bios --offline --headless --duration 1 --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"verified ISO not found"* ]]
}

@test "QEMU runner rejects invalid firmware" {
    run_qemu_dry --firmware unknown --offline --headless --duration 1 --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"firmware"* ]]
}

@test "QEMU runner rejects unbounded headless execution" {
    run_qemu_dry --firmware bios --offline --headless --duration 0
    [ "$status" -ne 0 ]
    [[ "$output" == *"headless"* ]]
}
