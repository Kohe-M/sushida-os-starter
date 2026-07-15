#!/usr/bin/env bash
# Run bounded BIOS and UEFI observations and assess automatable evidence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DURATION="${SUSHIDA_QEMU_DURATION:-90}"

[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: SUSHIDA_QEMU_DURATION must be a positive integer" >&2
    exit 1
}

"$SCRIPT_DIR/run-qemu.sh" --firmware bios --offline --headless --qemu-smoke --duration "$DURATION"
"$PROJECT_ROOT/tests/qemu/smoke-test.sh" bios-offline
"$SCRIPT_DIR/run-qemu.sh" --firmware uefi --offline --headless --qemu-smoke --duration "$DURATION"
"$PROJECT_ROOT/tests/qemu/smoke-test.sh" uefi-offline

echo "QEMU smoke observations completed. Review screenshots for manual-only checks."
