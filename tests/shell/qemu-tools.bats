#!/usr/bin/env bats

@test "QEMU BIOS dry run uses only the release ISO and offline NIC" {
    run scripts/run-qemu.sh --firmware bios --offline --headless --duration 1 --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"qemu-system-x86_64"* ]]
    [[ "$output" == *"sushida-os-amd64.iso"* ]]
    [[ "$output" == *"media=cdrom"* ]]
    [[ "$output" == *"readonly=on"* ]]
    [[ "$output" == *"-nic none"* ]]
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
