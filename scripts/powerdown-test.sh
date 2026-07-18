#!/usr/bin/env bash
# Exercise a guest ACPI power-button shutdown through QEMU's monitor only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DURATION="${SUSHIDA_QEMU_POWERDOWN_TIMEOUT:-180}"

[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: QEMU powerdown timeout must be a positive integer" >&2
    exit 1
}

for firmware in bios uefi; do
    "$SCRIPT_DIR/run-qemu.sh" \
        --firmware "$firmware" \
        --offline \
        --headless \
        --qemu-smoke \
        --writable-media \
        --powerdown \
        --duration "$DURATION"
    "$PROJECT_ROOT/tests/qemu/powerdown-test.sh" "$firmware-offline-powerdown"
done

echo "QEMU natural powerdown observations completed."
