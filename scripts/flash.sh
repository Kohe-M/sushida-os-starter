#!/usr/bin/env bash
# Guarded writer for the verified release ISO. Never guesses a target device.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ARTIFACT_DIR="$PROJECT_ROOT/artifacts"
IMAGE="$ARTIFACT_DIR/sushida-os-amd64.iso"
CHECKSUMS="$ARTIFACT_DIR/SHA256SUMS"
ASSUME_REVIEWED=false
TARGET=""
TARGET_BY_ID=""
TEST_MODE=false
VALIDATION_COUNT=0
readonly MAX_TARGET_BYTES=$((128 * 1024 * 1024 * 1024))

usage() {
    echo "Usage: sudo scripts/flash.sh [--yes] /dev/disk/by-id/usb-DEVICE"
}

fail() {
    echo "ERROR: flash: $*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes)
            ASSUME_REVIEWED=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --*)
            fail "unknown option: $1"
            ;;
        *)
            [ -z "$TARGET" ] || fail "exactly one target device is required"
            TARGET="$1"
            shift
            ;;
    esac
done
[ -n "$TARGET" ] || { usage >&2; fail "an explicit target device is required"; }

if [ "${SUSHIDA_OS_FLASH_TEST_MODE:-0}" = "1" ]; then
    TEST_MODE=true
    TEST_ROOT="${SUSHIDA_OS_FLASH_TEST_ROOT:-}"
    [ -n "$TEST_ROOT" ] || fail "test root is required in test mode"
    case "$TEST_ROOT" in /*) ;; *) fail "test root must be absolute" ;; esac
    if [ ! -d "$TEST_ROOT" ] || [ -L "$TEST_ROOT" ]; then
        fail "unsafe test root"
    fi
    TEST_ROOT="$(cd "$TEST_ROOT" && pwd -P)"
    case "$TEST_ROOT" in /tmp/*) ;; *) fail "test root must be below /tmp" ;; esac
    TEST_BY_ID_ROOT="$TEST_ROOT/dev/disk/by-id"
    IMAGE="${SUSHIDA_OS_FLASH_TEST_IMAGE:-}"
    CHECKSUMS="${SUSHIDA_OS_FLASH_TEST_CHECKSUMS:-}"
    if [ -z "$IMAGE" ] || [ -z "$CHECKSUMS" ]; then
        fail "test image and checksum are required"
    fi
else
    [ "$EUID" -eq 0 ] || fail "must run as root"
    PATH=/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
fi

for cmd in \
    awk basename dd dirname find findmnt grep head lsblk readlink \
    sed sha256sum stat swapon sync udevadm wc; do
    command -v "$cmd" > /dev/null 2>&1 || fail "required command not found: $cmd"
done

for path in "$IMAGE" "$CHECKSUMS"; do
    if [ ! -f "$path" ] || [ -L "$path" ] || [ ! -s "$path" ]; then
        fail "unsafe or missing file: $path"
    fi
done
IMAGE="$(readlink -f "$IMAGE")"
CHECKSUMS="$(readlink -f "$CHECKSUMS")"

if [ "$TEST_MODE" = true ]; then
    case "$IMAGE" in "$TEST_ROOT"/*) ;; *) fail "test image is outside test root" ;; esac
    case "$CHECKSUMS" in "$TEST_ROOT"/*) ;; *) fail "test checksum is outside test root" ;; esac
fi

image_name="$(basename "$IMAGE")"
checksum_name="$(awk 'NF == 2 { print $2 }' "$CHECKSUMS")"
[ "$(wc -l < "$CHECKSUMS")" -eq 1 ] || fail "checksum file must contain exactly one line"
[ "$checksum_name" = "$image_name" ] || fail "checksum filename does not match image"
expected_sha="$(awk '{ print $1 }' "$CHECKSUMS")"
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || fail "invalid expected SHA-256"
actual_sha="$(sha256sum "$IMAGE" | awk '{ print $1 }')"
[ "$actual_sha" = "$expected_sha" ] || fail "source image checksum mismatch"
IMAGE_SIZE="$(stat -c %s "$IMAGE")"
case "$IMAGE_SIZE" in ''|*[!0-9]*) fail "cannot determine image size" ;; esac

if [ "$TEST_MODE" = true ]; then
    SYSTEM_DISK="${SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK:-}"
    if [ -n "$SYSTEM_DISK" ]; then
        SYSTEM_DISK="$(readlink -f "$SYSTEM_DISK")"
    fi
else
    root_source="$(findmnt -nro SOURCE /)"
    case "$root_source" in /dev/*) ;; *) fail "cannot determine the physical system disk; refusing to write" ;; esac
    root_source="$(readlink -f "$root_source")"
    SYSTEM_DISK="$root_source"
    while parent_name="$(lsblk -ndo PKNAME "$SYSTEM_DISK")" && [ -n "$parent_name" ]; do
        SYSTEM_DISK="/dev/$parent_name"
    done
    SYSTEM_DISK="$(readlink -f "$SYSTEM_DISK")"
fi

validate_usb_target() {
    local supplied="$1"
    local expected_by_id_root resolved type transport removable hotplug id_bus
    local size_bytes serial model base node descendants swap_devices device_number
    local test_mounted test_swap test_holders

    if [ "$TEST_MODE" = true ]; then
        expected_by_id_root="$TEST_BY_ID_ROOT"
    else
        expected_by_id_root="/dev/disk/by-id"
    fi

    [ "$(dirname "$supplied")" = "$expected_by_id_root" ] || \
        fail "target must be specified using /dev/disk/by-id/usb-*"
    case "$(basename "$supplied")" in
        usb-*) ;;
        *) fail "target must be specified using /dev/disk/by-id/usb-*" ;;
    esac
    [ -L "$supplied" ] || fail "USB by-id target must be a symlink"

    resolved="$(readlink -f -- "$supplied")"
    [ -n "$resolved" ] || fail "USB by-id target cannot be resolved"
    VALIDATION_COUNT=$((VALIDATION_COUNT + 1))

    if [ "$TEST_MODE" = true ]; then
        [ -f "$resolved" ] && [ ! -L "$resolved" ] || \
            fail "test target must resolve to a regular non-symlink file"
        case "$resolved" in "$TEST_ROOT"/*) ;; *) fail "test target is outside test root" ;; esac

        type="${SUSHIDA_OS_FLASH_TEST_TYPE-disk}"
        transport="${SUSHIDA_OS_FLASH_TEST_TRANSPORT-usb}"
        removable="${SUSHIDA_OS_FLASH_TEST_REMOVABLE-1}"
        hotplug="${SUSHIDA_OS_FLASH_TEST_HOTPLUG-1}"
        id_bus="${SUSHIDA_OS_FLASH_TEST_ID_BUS-usb}"
        size_bytes="${SUSHIDA_OS_FLASH_TEST_SIZE_BYTES-$(stat -c %s "$resolved")}"
        serial="${SUSHIDA_OS_FLASH_TEST_SERIAL-TESTSERIAL001}"
        model="${SUSHIDA_OS_FLASH_TEST_MODEL-TEST-USB-FLASH}"
        device_number="${SUSHIDA_OS_FLASH_TEST_DEVICE_NUMBER-$(stat -Lc '%t:%T' "$resolved")}"
        test_mounted="${SUSHIDA_OS_FLASH_TEST_MOUNTED-0}"
        test_swap="${SUSHIDA_OS_FLASH_TEST_SWAP-0}"
        test_holders="${SUSHIDA_OS_FLASH_TEST_HOLDERS-0}"

        if [ "$VALIDATION_COUNT" -gt 1 ]; then
            if [ -v SUSHIDA_OS_FLASH_TEST_SECOND_SERIAL ]; then
                serial="$SUSHIDA_OS_FLASH_TEST_SECOND_SERIAL"
            fi
            if [ -v SUSHIDA_OS_FLASH_TEST_SECOND_DEVICE_NUMBER ]; then
                device_number="$SUSHIDA_OS_FLASH_TEST_SECOND_DEVICE_NUMBER"
            fi
        fi
    else
        [ -b "$resolved" ] || fail "target does not resolve to a block device"
        type="$(lsblk -dnro TYPE "$resolved")"
        transport="$(lsblk -dnro TRAN "$resolved")"
        removable="$(lsblk -dnro RM "$resolved")"
        hotplug="$(lsblk -dnro HOTPLUG "$resolved")"
        size_bytes="$(lsblk -bdnro SIZE "$resolved")"
        serial="$(lsblk -dnro SERIAL "$resolved" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
        model="$(lsblk -dnro MODEL "$resolved" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
        id_bus="$(udevadm info --query=property --name="$resolved" | sed -n 's/^ID_BUS=//p')"
        device_number="$(stat -Lc '%t:%T' "$resolved")"
        test_mounted=0
        test_swap=0
        test_holders=0
    fi

    [ "$type" = "disk" ] || fail "target must be a whole disk"
    [ "$transport" = "usb" ] || fail "target transport is not USB: ${transport:-unknown}"
    [ "$id_bus" = "usb" ] || fail "udev does not identify target as USB"
    [ "$removable" = "1" ] || fail "target is not marked removable"
    [ "$hotplug" = "1" ] || fail "target is not marked hot-pluggable"
    [ -n "$serial" ] || fail "USB serial number is unavailable"

    case "$size_bytes" in ''|*[!0-9]*) fail "cannot determine target capacity" ;; esac
    [ "$size_bytes" -ge "$IMAGE_SIZE" ] || fail "target is smaller than the ISO"
    [ "$size_bytes" -le "$MAX_TARGET_BYTES" ] || \
        fail "target exceeds the 128 GiB safety limit"

    [ "$resolved" != "$SYSTEM_DISK" ] || \
        fail "refusing to overwrite the current system disk: $resolved"

    if [ "$TEST_MODE" = true ]; then
        [ "$test_mounted" = 0 ] || fail "target or one of its partitions is mounted"
        [ "$test_swap" = 0 ] || fail "target or one of its partitions is active swap"
        [ "$test_holders" = 0 ] || \
            fail "target is used by device-mapper, LVM, RAID, or another block device"
    else
        if lsblk -nrpo MOUNTPOINTS "$resolved" | grep -q '[^[:space:]]'; then
            fail "target or one of its partitions is mounted"
        fi

        descendants="$(lsblk -nrpo NAME "$resolved")"
        swap_devices="$(swapon --show=NAME --noheadings --raw)" || \
            fail "cannot determine active swap devices"
        while IFS= read -r node; do
            [ -n "$node" ] || continue
            while IFS= read -r swap_device; do
                [ -n "$swap_device" ] || continue
                if [ "$(readlink -f -- "$node")" = "$(readlink -f -- "$swap_device")" ]; then
                    fail "target or one of its partitions is active swap"
                fi
            done <<< "$swap_devices"

            base="$(basename "$node")"
            [ -d "/sys/class/block/$base/holders" ] || \
                fail "cannot inspect block-device holders for $node"
            if find "/sys/class/block/$base/holders" \
                -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
                fail "target is used by device-mapper, LVM, RAID, or another block device"
            fi
        done <<< "$descendants"
    fi

    TARGET_BY_ID="$supplied"
    TARGET="$resolved"
    TRANSPORT="$transport"
    REMOVABLE="$removable"
    HOTPLUG="$hotplug"
    CAPACITY_BYTES="$size_bytes"
    SERIAL="$serial"
    MODEL="$model"
    DEVICE_NUMBER="$device_number"
}

validate_usb_target "$TARGET"

cat <<EOF
Verified image : $IMAGE
Image SHA-256 : $expected_sha
Target by-id   : $TARGET_BY_ID
Resolved path  : $TARGET
Device model  : ${MODEL:-unknown}
Serial number : $SERIAL
Capacity      : $CAPACITY_BYTES bytes
Transport     : $TRANSPORT
Removable     : $REMOVABLE
Hot-pluggable : $HOTPLUG

ALL DATA ON THIS USB DEVICE WILL BE DESTROYED.
EOF

read_confirmation() {
    local prompt="$1"
    local answer
    if [ "$TEST_MODE" = true ]; then
        printf '%s' "$prompt" >&2
        IFS= read -r answer || return 1
    else
        printf '%s' "$prompt" > /dev/tty
        IFS= read -r answer < /dev/tty || return 1
    fi
    printf '%s' "$answer"
}

if [ "$ASSUME_REVIEWED" = false ]; then
    review="$(read_confirmation 'Continue to final confirmation? [y/N] ')" || fail "confirmation input failed"
    case "$review" in y|Y|yes|YES) ;; *) fail "cancelled" ;; esac
fi

# --yes only skips the preliminary review question. It never skips this exact
# serial confirmation and never bypasses any device safety protection.
required_confirmation="ERASE USB $SERIAL"
final_confirmation="$(read_confirmation \
    "Type '$required_confirmation' to destroy this USB device: ")" || \
    fail "confirmation input failed"
[ "$final_confirmation" = "$required_confirmation" ] || fail "final confirmation did not match"

validated_target="$TARGET"
validated_device_number="$DEVICE_NUMBER"
validated_serial="$SERIAL"

validate_usb_target "$TARGET_BY_ID"
[ "$TARGET" = "$validated_target" ] || fail "target path changed after confirmation"
[ "$DEVICE_NUMBER" = "$validated_device_number" ] || \
    fail "target device number changed after confirmation"
[ "$SERIAL" = "$validated_serial" ] || fail "target serial changed after confirmation"

echo "Writing verified image to $TARGET_BY_ID ..."
dd if="$IMAGE" of="$TARGET_BY_ID" bs=4M iflag=fullblock conv=fsync status=progress
sync

written_sha="$(head -c "$IMAGE_SIZE" "$TARGET_BY_ID" | sha256sum | awk '{ print $1 }')"
[ "$written_sha" = "$expected_sha" ] || fail "written image verification failed"
echo "Flash completed and SHA-256 verification passed."
