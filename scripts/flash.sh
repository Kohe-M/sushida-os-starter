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
TEST_MODE=false

usage() {
    echo "Usage: sudo scripts/flash.sh [--yes] /dev/WHOLE_DISK"
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

for cmd in awk basename dd dirname findmnt grep head lsblk readlink sed sha256sum stat sync wc; do
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

if [ "$TEST_MODE" = true ]; then
    if [ ! -f "$TARGET" ] || [ -L "$TARGET" ]; then
        fail "test target must be a regular non-symlink file"
    fi
    TARGET="$(readlink -f "$TARGET")"
    case "$TARGET" in "$TEST_ROOT"/*) ;; *) fail "test target is outside test root" ;; esac
    SYSTEM_DISK="${SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK:-}"
    if [ -n "$SYSTEM_DISK" ]; then
        SYSTEM_DISK="$(readlink -f "$SYSTEM_DISK")"
    fi
    MODEL="TEST-FIXTURE"
    CAPACITY="$(stat -c %s "$TARGET") bytes"
    TRANSPORT="test"
else
    [ ! -L "$TARGET" ] || fail "target must not be a symlink"
    [ -b "$TARGET" ] || fail "target is not a block device: $TARGET"
    TARGET="$(readlink -f "$TARGET")"
    [ "$(lsblk -ndo TYPE "$TARGET")" = "disk" ] || fail "target must be a whole disk, not a partition or mapper"

    root_source="$(findmnt -nro SOURCE /)"
    case "$root_source" in /dev/*) ;; *) fail "cannot determine the physical system disk; refusing to write" ;; esac
    root_source="$(readlink -f "$root_source")"
    SYSTEM_DISK="$root_source"
    while parent_name="$(lsblk -ndo PKNAME "$SYSTEM_DISK")" && [ -n "$parent_name" ]; do
        SYSTEM_DISK="/dev/$parent_name"
    done
    SYSTEM_DISK="$(readlink -f "$SYSTEM_DISK")"

    if lsblk -nrpo MOUNTPOINT "$TARGET" | grep -q '[^[:space:]]'; then
        fail "target or one of its partitions is mounted"
    fi
    MODEL="$(lsblk -dn -o MODEL "$TARGET" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    CAPACITY="$(lsblk -dn -o SIZE "$TARGET" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    TRANSPORT="$(lsblk -dn -o TRAN "$TARGET" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
fi

[ "$TARGET" != "$SYSTEM_DISK" ] || fail "refusing to overwrite the current system disk: $TARGET"

cat <<EOF
Verified image : $IMAGE
Image SHA-256 : $expected_sha
Target device : $TARGET
Device model  : ${MODEL:-unknown}
Capacity      : ${CAPACITY:-unknown}
Transport     : ${TRANSPORT:-unknown}

ALL DATA ON THE TARGET DEVICE WILL BE DESTROYED.
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
# target confirmation and never bypasses any system-disk or mount protection.
required_confirmation="WRITE $TARGET"
final_confirmation="$(read_confirmation "Type '$required_confirmation' to continue: ")" || \
    fail "confirmation input failed"
[ "$final_confirmation" = "$required_confirmation" ] || fail "final confirmation did not match"

echo "Writing verified image to $TARGET ..."
dd if="$IMAGE" of="$TARGET" bs=4M iflag=fullblock conv=fsync status=progress
sync

image_size="$(stat -c %s "$IMAGE")"
written_sha="$(head -c "$image_size" "$TARGET" | sha256sum | awk '{ print $1 }')"
[ "$written_sha" = "$expected_sha" ] || fail "written image verification failed"
echo "Flash completed and SHA-256 verification passed."
