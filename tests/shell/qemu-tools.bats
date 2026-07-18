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
