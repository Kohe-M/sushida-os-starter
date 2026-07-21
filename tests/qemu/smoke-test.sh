#!/usr/bin/env bash
# Evaluate evidence that can be checked without adding a guest debug shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
RUN_NAME="${1:-}"
case "$RUN_NAME" in bios-offline|uefi-offline) ;; *) echo "usage: $0 bios-offline|uefi-offline" >&2; exit 2 ;; esac
RUN_DIR="$PROJECT_ROOT/build/qemu/$RUN_NAME"
ISO="$PROJECT_ROOT/artifacts/sushida-os-amd64.iso"
RESULT="$RUN_DIR/result.env"
SERIAL="$RUN_DIR/serial.log"
SCREENSHOT="$RUN_DIR/screenshot.png"
SCREENSHOT_PPM="$RUN_DIR/screenshot.ppm"
REPORT="$RUN_DIR/smoke-report.txt"

[ -s "$RESULT" ] || { echo "ERROR: missing QEMU result: $RESULT" >&2; exit 1; }
[ -s "$ISO" ] || { echo "ERROR: missing release ISO: $ISO" >&2; exit 1; }
[ -f "$SERIAL" ] || { echo "ERROR: missing serial log: $SERIAL" >&2; exit 1; }
[ -s "$SCREENSHOT" ] || { echo "ERROR: missing screenshot: $SCREENSHOT" >&2; exit 1; }
[ -s "$SCREENSHOT_PPM" ] || { echo "ERROR: missing PPM screenshot: $SCREENSHOT_PPM" >&2; exit 1; }
png_signature="$(head -c 8 "$SCREENSHOT" | od -An -tx1 | tr -d ' \n')"
[ "$png_signature" = "89504e470d0a1a0a" ] || {
    echo "ERROR: screenshot is not a PNG image" >&2
    exit 1
}

# shellcheck source=scripts/lib/qemu-lib.sh
. "$PROJECT_ROOT/scripts/lib/qemu-lib.sh"

result_sha="$(result_value "$RESULT" ISO_SHA256)" || {
    echo "ERROR: result.env must contain exactly one ISO_SHA256 entry" >&2
    exit 1
}
case "$result_sha" in
    ''|*[!0-9a-fA-F]*)
        echo "ERROR: result.env ISO_SHA256 is not hexadecimal" >&2
        exit 1
        ;;
esac
[ "${#result_sha}" -eq 64 ] || {
    echo "ERROR: result.env ISO_SHA256 must be exactly 64 hex characters" >&2
    exit 1
}
current_sha="$(sha256sum "$ISO" | awk '{print $1}')"
[ "$result_sha" = "$current_sha" ] || {
    echo "ERROR: QEMU result ISO SHA-256 does not match current ISO" >&2
    exit 1
}

timestamp_pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
run_started="$(result_value "$RESULT" RUN_STARTED_AT)" || {
    echo "ERROR: result.env must contain exactly one RUN_STARTED_AT entry" >&2
    exit 1
}
run_finished="$(result_value "$RESULT" RUN_FINISHED_AT)" || {
    echo "ERROR: result.env must contain exactly one RUN_FINISHED_AT entry" >&2
    exit 1
}
[[ "$run_started" =~ $timestamp_pattern ]] || {
    echo "ERROR: result.env RUN_STARTED_AT has an invalid UTC timestamp" >&2
    exit 1
}
[[ "$run_finished" =~ $timestamp_pattern ]] || {
    echo "ERROR: result.env RUN_FINISHED_AT has an invalid UTC timestamp" >&2
    exit 1
}

if grep -Eiq '(^|[^[:alpha:]])(login:|password:)' "$SERIAL"; then
    echo "ERROR: serial output contains a normal login prompt" >&2
    exit 1
fi
if grep -Eq 'sushida-(wifi-setup|network-watch|navigation-watch).*(ERROR:|Traceback|ModuleNotFoundError)' "$SERIAL"; then
    echo "ERROR: serial output contains a Wi-Fi setup or watcher service failure" >&2
    exit 1
fi
if grep -Fq 'Invalid pattern file://' "$SERIAL"; then
    echo "ERROR: serial output contains an invalid Chromium file URL policy" >&2
    exit 1
fi
grep -q '^QEMU_STATUS=0$' "$RESULT" || {
    echo "ERROR: bounded QEMU run was not cleanly observed" >&2
    exit 1
}
for evidence in \
    'systemd.setenv=WLR_RENDERER=pixman' \
    'var-lib-sushida\x2dconfig' \
    'sushida-config-prepare' \
    'sushida-wifi-setup' \
    'sushida-kiosk' \
    'sushida-network-watch' \
    'sushida-navigation-watch' \
    'graphical.target'; do
    grep -Fq "$evidence" "$SERIAL" || {
        echo "ERROR: serial output lacks boot evidence: $evidence" >&2
        exit 1
    }
done
python3 "$SCRIPT_DIR/check-screenshot.py" "$SCREENSHOT_PPM"

{
    echo "AUTOMATED: ISO SHA-256 matches the current release artifact: PASS"
    echo "ISO_SHA256=$result_sha"
    echo "RUN_STARTED_AT=$run_started"
    echo "RUN_FINISHED_AT=$run_finished"
    echo "AUTOMATED: QEMU stayed alive for the configured observation interval: PASS"
    echo "AUTOMATED: screenshot was captured as PNG: PASS"
    echo "AUTOMATED: screenshot has nonblank, spatially complete kiosk contrast: PASS"
    echo "AUTOMATED: serial log contains no normal login/password prompt: PASS"
    echo "AUTOMATED: serial log contains no Wi-Fi setup backend/watcher error: PASS"
    echo "AUTOMATED: QEMU pixman boot entry reached kiosk services and graphical target: PASS"
    echo "AUTOMATED: writable config filesystem and Wi-Fi setup services started: PASS"
    echo "MANUAL: boot reached the kiosk UI: UNVERIFIED"
    echo "MANUAL: Cage and Chromium are visible and full-screen: UNVERIFIED"
    echo "MANUAL: static offline page is visible: UNVERIFIED"
    echo "MANUAL: Chromium/Cage restart behavior: UNVERIFIED"
} > "$REPORT"

cat "$REPORT"
