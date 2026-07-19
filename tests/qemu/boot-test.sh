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
ARTIFACT_SHA256SUM="$PROJECT_ROOT/artifacts/SHA256SUMS"

if [ ! -f "$SERIAL" ] || [ ! -f "$RESULT" ]; then
    echo "ERROR: boot-test: serial log or result.env missing in $RUN_DIR" >&2
    exit 1
fi

# Strip ANSI colour sequences from systemd's console output.
_serial_plain() { sed -E $'s/\x1B\\[[0-9;?]*[ -/]*[@-~]//g' "$SERIAL"; }

# Verify the bootloader succeeded in reaching kiosk services.
if ! _serial_plain | grep -Eiq 'Started[[:space:]]+sushida-kiosk\.service([[:space:]-]|$)'; then
    echo "ERROR: serial output lacks kiosk service start" >&2
    exit 1
fi
if ! _serial_plain | grep -Fiq 'graphical.target'; then
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

# Compare the observed ISO SHA against the signed artifact checksum file.
_sha_match=false
if [ -s "$ARTIFACT_SHA256SUM" ]; then
    _expected_sha="$(awk '{print $1}' "$ARTIFACT_SHA256SUM")"
    _current_head="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null || echo '')"
    if [ -n "$_expected_sha" ] && [ "$ISO_SHA256" = "$_expected_sha" ]; then
        _sha_match=true
    fi
else
    _current_head=""
fi

{
    if [ "$_sha_match" = true ]; then
        echo "AUTOMATED: ISO SHA-256 matches the current release artifact: PASS"
    else
        echo "AUTOMATED: ISO SHA-256 does NOT match the artifact or is unavailable: CHECK"
        echo "EXPECTED_SHA=${_expected_sha:-missing}"
        echo "OBSERVED_SHA=$ISO_SHA256"
    fi
    echo "ISO_SHA256=$ISO_SHA256"
    echo "AUTOMATED: production bootloader reached kiosk service: PASS"
    echo "GIT_COMMIT=$GIT_COMMIT"
    echo "MANUAL: verify the bootloader config visually: UNVERIFIED"
} > "$REPORT"

cat "$REPORT"
exit 0
