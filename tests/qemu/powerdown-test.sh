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
ISO="$PROJECT_ROOT/artifacts/sushida-os-amd64.iso"
CHECKSUMS="$PROJECT_ROOT/artifacts/SHA256SUMS"
BUILD_INFO="$PROJECT_ROOT/artifacts/build-info.json"

[ -s "$RESULT" ] || { echo "ERROR: missing QEMU powerdown result: $RESULT" >&2; exit 1; }
[ -f "$SERIAL" ] || { echo "ERROR: missing QEMU powerdown serial log: $SERIAL" >&2; exit 1; }
[ -s "$ISO" ] || { echo "ERROR: missing release ISO: $ISO" >&2; exit 1; }
[ -s "$CHECKSUMS" ] || { echo "ERROR: missing release checksums: $CHECKSUMS" >&2; exit 1; }
[ -s "$BUILD_INFO" ] || { echo "ERROR: missing release metadata: $BUILD_INFO" >&2; exit 1; }

for command_name in awk git python3 sha256sum; do
    command -v "$command_name" > /dev/null 2>&1 || {
        echo "ERROR: required command not found: $command_name" >&2
        exit 1
    }
done

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

current_commit="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null)" || {
    echo "ERROR: cannot determine current Git commit" >&2
    exit 1
}
git_status="$(git -C "$PROJECT_ROOT" status --porcelain --untracked-files=all)"
[ -z "$git_status" ] || {
    echo "ERROR: current Git worktree is dirty; commit source changes first" >&2
    exit 1
}
[ "$(result_value GIT_COMMIT)" = "$current_commit" ] || {
    echo "ERROR: QEMU result was produced from a different Git commit" >&2
    exit 1
}

result_sha="$(result_value ISO_SHA256)"
current_sha="$(sha256sum "$ISO" | awk '{print $1}')"
[ "$result_sha" = "$current_sha" ] || {
    echo "ERROR: QEMU result ISO SHA-256 does not match the current ISO" >&2
    exit 1
}
checksum_sha="$(awk '$2 == "sushida-os-amd64.iso" { print $1; count++ } END { if (count != 1) exit 1 }' "$CHECKSUMS")" || {
    echo "ERROR: SHA256SUMS does not contain exactly one release ISO entry" >&2
    exit 1
}
[ "$checksum_sha" = "$current_sha" ] || {
    echo "ERROR: release SHA256SUMS does not match the current ISO" >&2
    exit 1
}
python3 - "$BUILD_INFO" "$current_commit" "$current_sha" <<'PY'
import json
import sys

metadata_path, expected_commit, expected_sha = sys.argv[1:]
try:
    with open(metadata_path, encoding="utf-8") as stream:
        metadata = json.load(stream)
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit("invalid build-info.json")
if metadata.get("git_commit") != expected_commit:
    raise SystemExit("build-info.json commit does not match current HEAD")
if metadata.get("iso_sha256") != expected_sha:
    raise SystemExit("build-info.json ISO checksum does not match the current ISO")
PY

grep -Eiq 'Started[[:space:]]+sushida-kiosk\.service([[:space:]-]|$)' "$SERIAL" || {
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
[ "$(result_value CONFIG_MOUNT_SEEN)" = true ] || {
    echo "ERROR: serial log lacks successful SUSHIDA-CFG mount evidence" >&2
    exit 1
}
[ "$(result_value CONFIG_UNMOUNT_SEEN)" = true ] || {
    echo "ERROR: serial log lacks successful SUSHIDA-CFG unmount evidence" >&2
    exit 1
}
grep -Eiq \
    'Mounted[[:space:]].*(/var/lib/sushida-config|var-lib-sushida\\x2dconfig\.mount)' \
    "$SERIAL" || {
    echo "ERROR: serial log lacks positive SUSHIDA-CFG mount evidence" >&2
    exit 1
}
grep -Eiq \
    'Unmounted[[:space:]].*(/var/lib/sushida-config|var-lib-sushida\\x2dconfig\.mount)' \
    "$SERIAL" || {
    echo "ERROR: serial log lacks positive SUSHIDA-CFG unmount evidence" >&2
    exit 1
}

echo "AUTOMATED: $RUN_NAME reached the started kiosk service and exited through systemd poweroff with verified release metadata and SUSHIDA-CFG mount/unmount evidence: PASS"
