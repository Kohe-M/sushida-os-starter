#!/usr/bin/env bash
# Check evidence from a QEMU monitor system_powerdown run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
RUN_NAME="${1:-}"
case "$RUN_NAME" in
    bios-offline-powerdown|uefi-offline-powerdown) ;;
    *) echo "usage: $0 bios-offline-powerdown|uefi-offline-powerdown" >&2; exit 2 ;;
esac
RUN_DIR="$PROJECT_ROOT/build/qemu/$RUN_NAME"
RESULT="$RUN_DIR/result.env"
SERIAL="$RUN_DIR/serial.log"

[ -s "$RESULT" ] || { echo "ERROR: missing QEMU powerdown result: $RESULT" >&2; exit 1; }
[ -f "$SERIAL" ] || { echo "ERROR: missing QEMU powerdown serial log: $SERIAL" >&2; exit 1; }

result_value() {
    local key="$1"
    awk -F= -v key="$key" '
        $1 == key { count++; value = substr($0, index($0, "=") + 1) }
        END { if (count != 1) exit 1; print value }
    ' "$RESULT"
}

[ "$(result_value POWERDOWN_MODE)" = true ] || {
    echo "ERROR: result is not a powerdown run" >&2
    exit 1
}
[ "$(result_value POWERDOWN_SENT)" = true ] || {
    echo "ERROR: monitor system_powerdown was not sent" >&2
    exit 1
}
[ "$(result_value NATURAL_POWERDOWN)" = true ] || {
    echo "ERROR: QEMU did not report a natural guest shutdown" >&2
    exit 1
}
[ "$(result_value QEMU_STATUS)" = 0 ] || {
    echo "ERROR: QEMU powerdown status was not zero" >&2
    exit 1
}

grep -Fq 'sushida-kiosk.service' "$SERIAL" || {
    echo "ERROR: serial log lacks kiosk startup evidence" >&2
    exit 1
}
grep -Eiq 'poweroff\.target|Powering off|Reached target Shutdown' "$SERIAL" || {
    echo "ERROR: serial log lacks normal systemd poweroff evidence" >&2
    exit 1
}
if grep -Eiq 'failed[^[:cntrl:]]*unmount|unmount[^[:cntrl:]]*failed' "$SERIAL"; then
    echo "ERROR: serial log contains an unmount failure" >&2
    exit 1
fi
if grep -F 'var-lib-sushida\x2dconfig.mount' "$SERIAL" | \
    grep -Eiq 'failed|failure|error'; then
    echo "ERROR: config mount has a shutdown failure" >&2
    exit 1
fi

echo "AUTOMATED: $RUN_NAME reached kiosk and exited through systemd poweroff: PASS"
