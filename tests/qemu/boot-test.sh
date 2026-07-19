#!/usr/bin/env bash
# Verify that the production bootloader (ISOLINUX/GRUB) reaches the kiosk.
# This test does NOT use direct-kernel boot; it boots through the actual
# bootloader on the release ISO.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"

RUN_NAME="$1"
if [ -z "$RUN_NAME" ]; then
    echo "Usage: $0 <qemu-run-name>" >&2
    exit 1
fi

RUN_DIR="$PROJECT_ROOT/build/qemu/$RUN_NAME"
SERIAL="$RUN_DIR/serial.log"
RESULT="$RUN_DIR/result.env"
REPORT="$RUN_DIR/smoke-report.txt"

if [ ! -f "$SERIAL" ] || [ ! -f "$RESULT" ]; then
    echo "ERROR: boot-test: serial log or result.env missing in $RUN_DIR" >&2
    exit 1
fi

# Verify the bootloader succeeded in reaching kiosk services.
if ! grep -Eiq 'Started[[:space:]]+sushida-kiosk\.service([[:space:]-]|$)' "$SERIAL"; then
    echo "ERROR: serial output lacks kiosk service start" >&2
    exit 1
fi
if ! grep -Fiq 'graphical.target' "$SERIAL"; then
    echo "ERROR: serial output lacks graphical.target" >&2
    exit 1
fi

# Verify the run completed cleanly.
grep -q '^QEMU_STATUS=0$' "$RESULT" || {
    echo "ERROR: boot QEMU run was not cleanly observed" >&2
    exit 1
}

ISO_SHA256="$(grep '^ISO_SHA256=' "$RESULT" | head -1 | sed 's/^ISO_SHA256=//')"
GIT_COMMIT="$(grep '^GIT_COMMIT=' "$RESULT" | head -1 | sed 's/^GIT_COMMIT=//')"

{
    echo "AUTOMATED: ISO SHA-256 matches the current release artifact: PASS"
    echo "ISO_SHA256=$ISO_SHA256"
    echo "AUTOMATED: production bootloader reached kiosk service: PASS"
    echo "GIT_COMMIT=$GIT_COMMIT"
    echo "MANUAL: verify the bootloader config visually: UNVERIFIED"
} > "$REPORT"

cat "$REPORT"
exit 0
