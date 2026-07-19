#!/usr/bin/env bash
# Run bounded BIOS and UEFI bootloader tests and assess serial evidence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
BIOS_DURATION="${SUSHIDA_QEMU_BIOS_DURATION:-${SUSHIDA_QEMU_DURATION:-120}}"
UEFI_DURATION="${SUSHIDA_QEMU_UEFI_DURATION:-${SUSHIDA_QEMU_DURATION:-120}}"

for duration in "$BIOS_DURATION" "$UEFI_DURATION"; do
    [[ "$duration" =~ ^[1-9][0-9]*$ ]] || {
        echo "ERROR: QEMU boot-test durations must be positive integers" >&2
        exit 1
    }
done

"$SCRIPT_DIR/run-qemu.sh" --firmware bios --offline --headless --qemu-boot-test --writable-media --duration "$BIOS_DURATION"
"$PROJECT_ROOT/tests/qemu/boot-test.sh" bios-offline

"$SCRIPT_DIR/run-qemu.sh" --firmware uefi --offline --headless --qemu-boot-test --writable-media --duration "$UEFI_DURATION"
"$PROJECT_ROOT/tests/qemu/boot-test.sh" uefi-offline

echo "QEMU bootloader tests completed. Review serial logs for GRUB/ISOLINUX evidence."
