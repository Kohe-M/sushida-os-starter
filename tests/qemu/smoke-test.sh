#!/usr/bin/env bash
# Evaluate evidence that can be checked without adding a guest debug shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
RUN_NAME="${1:-}"
case "$RUN_NAME" in bios-offline|uefi-offline) ;; *) echo "usage: $0 bios-offline|uefi-offline" >&2; exit 2 ;; esac
RUN_DIR="$PROJECT_ROOT/build/qemu/$RUN_NAME"
RESULT="$RUN_DIR/result.env"
SERIAL="$RUN_DIR/serial.log"
SCREENSHOT="$RUN_DIR/screenshot.png"
REPORT="$RUN_DIR/smoke-report.txt"

[ -s "$RESULT" ] || { echo "ERROR: missing QEMU result: $RESULT" >&2; exit 1; }
[ -f "$SERIAL" ] || { echo "ERROR: missing serial log: $SERIAL" >&2; exit 1; }
[ -s "$SCREENSHOT" ] || { echo "ERROR: missing screenshot: $SCREENSHOT" >&2; exit 1; }
png_signature="$(head -c 8 "$SCREENSHOT" | od -An -tx1 | tr -d ' \n')"
[ "$png_signature" = "89504e470d0a1a0a" ] || {
    echo "ERROR: screenshot is not a PNG image" >&2
    exit 1
}
if grep -Eiq '(^|[^[:alpha:]])(login:|password:)' "$SERIAL"; then
    echo "ERROR: serial output contains a normal login prompt" >&2
    exit 1
fi
grep -q '^QEMU_STATUS=0$' "$RESULT" || {
    echo "ERROR: bounded QEMU run was not cleanly observed" >&2
    exit 1
}

{
    echo "AUTOMATED: QEMU stayed alive for the configured observation interval: PASS"
    echo "AUTOMATED: screenshot was captured as PNG: PASS"
    echo "AUTOMATED: serial log contains no normal login/password prompt: PASS"
    echo "MANUAL: boot reached the kiosk UI: UNVERIFIED"
    echo "MANUAL: Cage and Chromium are visible and full-screen: UNVERIFIED"
    echo "MANUAL: offline page is visible: UNVERIFIED"
    echo "MANUAL: Chromium/Cage restart behavior: UNVERIFIED"
} > "$REPORT"

cat "$REPORT"
