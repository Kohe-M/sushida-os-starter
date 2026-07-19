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
BUILD_INFO="$PROJECT_ROOT/artifacts/build-info.json"

if [ ! -f "$SERIAL" ] || [ ! -f "$RESULT" ]; then
    echo "ERROR: boot-test: serial log or result.env missing in $RUN_DIR" >&2
    exit 1
fi

# Strip ANSI colour sequences from systemd's console output.
_serial_plain() { sed -E $'s/\x1B\\[[0-9;?]*[ -/]*[@-~]//g' "$SERIAL"; }
_exit_report=0

# Verify the bootloader succeeded in reaching kiosk services.
if ! _serial_plain | grep -Eiq 'Started[[:space:]]+sushida-kiosk\.service([[:space:]-]|$)'; then
    echo "ERROR: serial output lacks kiosk service start" >&2
    _exit_report=1
fi
if [ $_exit_report -eq 0 ]; then
    if ! _serial_plain | grep -Fiq 'graphical.target'; then
        echo "ERROR: serial output lacks graphical.target" >&2
        _exit_report=1
    fi
fi

# Verify the run completed cleanly.
if ! grep -q '^QEMU_STATUS=0$' "$RESULT"; then
    echo "ERROR: boot QEMU run was not cleanly observed" >&2
    _exit_report=1
fi

ISO_SHA256="$(grep '^ISO_SHA256=' "$RESULT" | head -1 | sed 's/^ISO_SHA256=//')"
RUN_GIT_COMMIT="$(grep '^GIT_COMMIT=' "$RESULT" | head -1 | sed 's/^GIT_COMMIT=//')"
CURRENT_HEAD="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null || echo 'unknown')"
EXPECTED_SHA=""
BUILD_COMMIT=""

# Compare the observed ISO SHA against the signed artifact checksum file.
if [ -s "$ARTIFACT_SHA256SUM" ]; then
    EXPECTED_SHA="$(awk '{print $1}' "$ARTIFACT_SHA256SUM")"
fi
if [ -s "$BUILD_INFO" ]; then
    BUILD_COMMIT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('git_commit',''))" "$BUILD_INFO" 2>/dev/null || true)"
fi

_sha_ok=true
_git_ok=true
if [ -z "$EXPECTED_SHA" ] || [ "$ISO_SHA256" != "$EXPECTED_SHA" ]; then
    _sha_ok=false; _exit_report=1
fi
if [ -z "$BUILD_COMMIT" ] || [ "$CURRENT_HEAD" != "$BUILD_COMMIT" ]; then
    _git_ok=false; _exit_report=1
fi

{
    if [ "$_sha_ok" = true ]; then
        echo "AUTOMATED: ISO SHA-256 matches artifact SHA256SUMS: PASS"
    else
        echo "AUTOMATED: ISO SHA-256 does NOT match artifact: FAIL"
        echo "EXPECTED_SHA=${EXPECTED_SHA:-missing}"
        echo "OBSERVED_SHA=$ISO_SHA256"
    fi
    if [ "$_git_ok" = true ]; then
        echo "AUTOMATED: build-info.json git_commit matches HEAD: PASS"
    else
        echo "AUTOMATED: build-info.json git_commit does NOT match HEAD: FAIL"
        echo "BUILD_COMMIT=${BUILD_COMMIT:-missing}"
        echo "CURRENT_HEAD=$CURRENT_HEAD"
    fi
    echo "ISO_SHA256=$ISO_SHA256"
    echo "AUTOMATED: production bootloader reached kiosk service: PASS"
    echo "GIT_COMMIT=$RUN_GIT_COMMIT"
    echo "MANUAL: verify the bootloader config visually: UNVERIFIED"
} > "$REPORT"

cat "$REPORT"
exit $_exit_report

cat "$REPORT"
exit 0
