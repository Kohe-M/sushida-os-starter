#!/usr/bin/env bats

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/flash-root"
    BY_ID_DIR="$TEST_ROOT/dev/disk/by-id"
    DEVICE_DIR="$TEST_ROOT/devices"
    mkdir -p "$BY_ID_DIR" "$DEVICE_DIR"

    IMAGE="$TEST_ROOT/test.iso"
    CHECKSUMS="$TEST_ROOT/SHA256SUMS"
    TARGET_FILE="$DEVICE_DIR/usb-target"
    SYSTEM_DISK="$DEVICE_DIR/system-device"
    TARGET="$BY_ID_DIR/usb-Test_Vendor_Flash_TESTSERIAL001-0:0"

    printf 'safe test image\n' > "$IMAGE"
    truncate -s 4096 "$TARGET_FILE"
    printf 'old target data\n' > "$TARGET_FILE"
    printf 'system data\n' > "$SYSTEM_DISK"
    ln -s "$TARGET_FILE" "$TARGET"
    (
        cd "$TEST_ROOT" || exit
        sha256sum test.iso > SHA256SUMS
    )

    export SUSHIDA_OS_FLASH_TEST_MODE=1
    export SUSHIDA_OS_FLASH_TEST_ROOT="$TEST_ROOT"
    export SUSHIDA_OS_FLASH_TEST_IMAGE="$IMAGE"
    export SUSHIDA_OS_FLASH_TEST_CHECKSUMS="$CHECKSUMS"
    export SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK="$SYSTEM_DISK"
    export SUSHIDA_OS_FLASH_TEST_TYPE=disk
    export SUSHIDA_OS_FLASH_TEST_TRANSPORT=usb
    export SUSHIDA_OS_FLASH_TEST_REMOVABLE=1
    export SUSHIDA_OS_FLASH_TEST_HOTPLUG=1
    export SUSHIDA_OS_FLASH_TEST_ID_BUS=usb
    export SUSHIDA_OS_FLASH_TEST_SIZE_BYTES=4096
    export SUSHIDA_OS_FLASH_TEST_SERIAL=TESTSERIAL001
    export SUSHIDA_OS_FLASH_TEST_MODEL=TEST-USB-FLASH
    export SUSHIDA_OS_FLASH_TEST_DEVICE_NUMBER=8:64
    export SUSHIDA_OS_FLASH_TEST_MOUNTED=0
    export SUSHIDA_OS_FLASH_TEST_SWAP=0
    export SUSHIDA_OS_FLASH_TEST_HOLDERS=0
    export FLASH="scripts/flash.sh"
    export TARGET TARGET_FILE SYSTEM_DISK
}

@test "flash requires an explicit target" {
    run "$FLASH" --yes
    [ "$status" -ne 0 ]
    [[ "$output" == *"explicit target"* ]]
}

@test "raw dev path is rejected even with --yes" {
    run "$FLASH" --yes "$TEST_ROOT/dev/sdb"
    [ "$status" -ne 0 ]
    [[ "$output" == *"/dev/disk/by-id/usb-*"* ]]
}

@test "non-USB by-id name is rejected" {
    ata_target="$BY_ID_DIR/ata-Test_Disk_001"
    ln -s "$TARGET_FILE" "$ata_target"
    run "$FLASH" --yes "$ata_target"
    [ "$status" -ne 0 ]
    [[ "$output" == *"/dev/disk/by-id/usb-*"* ]]
}

@test "partition target is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_TYPE=part "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"whole disk"* ]]
}

@test "NVMe transport is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_TRANSPORT=nvme "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not USB: nvme"* ]]
}

@test "SATA transport is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_TRANSPORT=sata "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not USB: sata"* ]]
}

@test "non-removable target is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_REMOVABLE=0 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked removable"* ]]
}

@test "non-hotplug target is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

# Fake sysfs for a USB/IP-attached disk: vhci_hcd.0 bound to the vhci_hcd
# driver, with the SCSI disk below it, as usbipd-win exposes it in WSL.
make_vhci_sysfs() {
    local driver_name="${1:-vhci_hcd}" node="${2:-vhci_hcd.0}"
    local sys="$TEST_ROOT/sys"
    mkdir -p "$sys/bus/platform/drivers/$driver_name" \
        "$sys/devices/platform/$node/usb1/1-1/1-1:1.0/host1/target1:0:0/1:0:0:0"
    ln -sfn "$sys/bus/platform/drivers/$driver_name" "$sys/devices/platform/$node/driver"
    VHCI_DEVICE="$sys/devices/platform/$node/usb1/1-1/1-1:1.0/host1/target1:0:0/1:0:0:0"
    export VHCI_DEVICE
}

@test "USB/IP-attached target without the hotplug flag writes and verifies" {
    make_vhci_sysfs
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" \
        bash -c 'printf "ERASE USB TESTSERIAL001\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -eq 0 ]
    [[ "$output" == *"Hot-pluggable : 1 (attached via USB/IP vhci_hcd)"* ]]
    [[ "$output" == *"SHA-256 verification passed"* ]]
    [ "$(head -c 16 "$TARGET_FILE")" = "safe test image" ]
}

@test "USB/IP basis does not bypass the removable check" {
    make_vhci_sysfs
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_REMOVABLE=0 \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked removable"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "USB/IP basis does not bypass the serial, transport or system-disk checks" {
    make_vhci_sysfs
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SERIAL= \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"serial number is unavailable"* ]]
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_TRANSPORT=sata \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not USB: sata"* ]]
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK="$TARGET_FILE" \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"current system disk"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "vhci_hcd node bound to another driver is not a USB/IP basis" {
    make_vhci_sysfs not_vhci
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

@test "vhci_hcd node without a bound driver is not a USB/IP basis" {
    make_vhci_sysfs
    rm "$TEST_ROOT/sys/devices/platform/vhci_hcd.0/driver"
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

@test "look-alike vhci node names are not a USB/IP basis" {
    make_vhci_sysfs vhci_hcd vhci_hcd.0-evil
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$VHCI_DEVICE" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

@test "a vhci path outside the sysfs device tree is not a USB/IP basis" {
    make_vhci_sysfs
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="/elsewhere/devices/platform/vhci_hcd.0/usb1/1-1" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

@test "a native non-hotplug USB path is still rejected" {
    mkdir -p "$TEST_ROOT/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1"
    run env SUSHIDA_OS_FLASH_TEST_HOTPLUG=0 \
        SUSHIDA_OS_FLASH_TEST_SYSFS_DEVICE="$TEST_ROOT/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not marked hot-pluggable"* ]]
}

@test "non-USB udev bus is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_ID_BUS=ata "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"udev does not identify target as USB"* ]]
}

@test "missing serial is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_SERIAL= "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"serial number is unavailable"* ]]
}

@test "target over 128 GiB is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_SIZE_BYTES=137438953473 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"128 GiB safety limit"* ]]
}

@test "target smaller than image is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_SIZE_BYTES=1 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"smaller than the ISO"* ]]
}

@test "mounted descendant is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_MOUNTED=1 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"partitions is mounted"* ]]
}

@test "active swap descendant is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_SWAP=1 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"active swap"* ]]
}

@test "device holder is rejected even with --yes" {
    run env SUSHIDA_OS_FLASH_TEST_HOLDERS=1 "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"device-mapper, LVM, RAID"* ]]
}

@test "--yes cannot bypass system disk protection" {
    run env SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK="$TARGET_FILE" \
        "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"current system disk"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "--force is not a supported escape hatch" {
    run "$FLASH" --force "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown option: --force"* ]]
}

@test "wrong serial confirmation leaves target unchanged" {
    run bash -c 'printf "WRONG\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"did not match"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "changed device number after confirmation is rejected" {
    run env SUSHIDA_OS_FLASH_TEST_SECOND_DEVICE_NUMBER=8:80 bash -c \
        'printf "ERASE USB TESTSERIAL001\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"device number changed"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "changed serial after confirmation is rejected" {
    run env SUSHIDA_OS_FLASH_TEST_SECOND_SERIAL=REPLACEMENT bash -c \
        'printf "ERASE USB TESTSERIAL001\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"serial changed"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}

@test "confirmed safe USB fixture writes and verifies" {
    run bash -c \
        'printf "ERASE USB TESTSERIAL001\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -eq 0 ]
    [[ "$output" == *"Target by-id"* ]]
    [[ "$output" == *"TESTSERIAL001"* ]]
    [[ "$output" == *"SHA-256 verification passed"* ]]
    cmp "$IMAGE" "$TARGET_FILE"
}

@test "USB by-id symlink resolving outside test root is rejected" {
    outside="$BATS_TEST_TMPDIR/outside"
    outside_target="$BY_ID_DIR/usb-Outside_TESTSERIAL001-0:0"
    printf outside > "$outside"
    ln -s "$outside" "$outside_target"
    run "$FLASH" --yes "$outside_target"
    [ "$status" -ne 0 ]
    [[ "$output" == *"outside test root"* ]]
}

@test "source checksum mismatch fails before confirmation or write" {
    printf tampered >> "$IMAGE"
    run "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"checksum mismatch"* ]]
    [ "$(cat "$TARGET_FILE")" = "old target data" ]
}
