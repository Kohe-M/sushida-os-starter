#!/usr/bin/env bash
# Run bounded BIOS and UEFI observations and assess automatable evidence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
BIOS_DURATION="${SUSHIDA_QEMU_BIOS_DURATION:-${SUSHIDA_QEMU_DURATION:-300}}"
UEFI_DURATION="${SUSHIDA_QEMU_UEFI_DURATION:-${SUSHIDA_QEMU_DURATION:-300}}"

for duration in "$BIOS_DURATION" "$UEFI_DURATION"; do
    [[ "$duration" =~ ^[1-9][0-9]*$ ]] || {
        echo "ERROR: QEMU smoke durations must be positive integers" >&2
        exit 1
    }
done

"$SCRIPT_DIR/run-qemu.sh" --firmware bios --offline --headless --qemu-smoke --writable-media --duration "$BIOS_DURATION"
"$PROJECT_ROOT/tests/qemu/smoke-test.sh" bios-offline
"$SCRIPT_DIR/run-qemu.sh" --firmware uefi --offline --headless --qemu-smoke --writable-media --duration "$UEFI_DURATION"
"$PROJECT_ROOT/tests/qemu/smoke-test.sh" uefi-offline

echo "QEMU smoke observations completed. Review screenshots for manual-only checks."
