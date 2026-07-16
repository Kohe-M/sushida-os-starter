#!/usr/bin/env bash
# Boot the release ISO in QEMU without modifying host disks or firmware state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ISO="$PROJECT_ROOT/artifacts/sushida-os-amd64.iso"
QEMU_ROOT="$PROJECT_ROOT/build/qemu"
FIRMWARE="bios"
NETWORK="online"
HEADLESS=false
DRY_RUN=false
QEMU_SMOKE=false
DURATION=0

usage() {
    cat <<'EOF'
Usage: scripts/run-qemu.sh [options]
  --firmware bios|uefi  Select legacy BIOS or UEFI (default: bios)
  --offline             Do not create a guest network interface
  --headless            Disable the QEMU display window
  --duration SECONDS    Capture a screenshot and quit after a bounded interval
  --qemu-smoke          Select the QEMU-only software-renderer boot entry
  --dry-run             Print the QEMU command without starting it
EOF
}

fail() {
    echo "ERROR: QEMU: $*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --firmware)
            [ "$#" -ge 2 ] || fail "--firmware requires a value"
            FIRMWARE="$2"
            shift 2
            ;;
        --offline)
            NETWORK="offline"
            shift
            ;;
        --headless)
            HEADLESS=true
            shift
            ;;
        --duration)
            [ "$#" -ge 2 ] || fail "--duration requires a value"
            DURATION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --qemu-smoke)
            QEMU_SMOKE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

case "$FIRMWARE" in bios|uefi) ;; *) fail "firmware must be bios or uefi" ;; esac
[[ "$DURATION" =~ ^[0-9]+$ ]] || fail "duration must be a non-negative integer"
if [ "$HEADLESS" = true ] && [ "$DURATION" -eq 0 ] && [ "$DRY_RUN" = false ]; then
    fail "headless execution requires --duration"
fi
if [ ! -f "$ISO" ] || [ -L "$ISO" ] || [ ! -s "$ISO" ]; then
    fail "verified ISO not found: $ISO"
fi
command -v qemu-system-x86_64 > /dev/null 2>&1 || fail "qemu-system-x86_64 not found"

[ ! -L "$QEMU_ROOT" ] || fail "QEMU output root is a symlink"
mkdir -p "$QEMU_ROOT"
RUN_DIR="$QEMU_ROOT/$FIRMWARE-$NETWORK"
if [ -e "$RUN_DIR" ] && [ -L "$RUN_DIR" ]; then
    fail "QEMU run directory is a symlink"
fi
mkdir -p "$RUN_DIR"
SERIAL_LOG="$RUN_DIR/serial.log"
SCREENSHOT="$RUN_DIR/screenshot.png"
SCREENSHOT_PPM="$RUN_DIR/screenshot.ppm"
MONITOR_SOCKET="$RUN_DIR/monitor.sock"
RESULT_FILE="$RUN_DIR/result.env"
rm -f -- "$SERIAL_LOG" "$SCREENSHOT" "$SCREENSHOT_PPM" "$MONITOR_SOCKET" "$RESULT_FILE"

QEMU_ACCEL="tcg"
if [ -c /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
    QEMU_ACCEL="kvm:tcg"
fi

QEMU_ARGS=(
    -name "sushida-os-$FIRMWARE-$NETWORK"
    -machine "q35,accel=$QEMU_ACCEL"
    -m 2048
    -smp 2
    -boot order=d
    -drive "file=$ISO,media=cdrom,readonly=on"
    -audiodev "driver=none,id=sushida-audio"
    -device ich9-intel-hda
    -device "hda-duplex,audiodev=sushida-audio"
    -serial "file:$SERIAL_LOG"
    -monitor "unix:$MONITOR_SOCKET,server=on,wait=off"
    -no-reboot
)

# virtio-vga provides a stable captured scanout for BIOS. Under OVMF/TCG its
# post-GOP scanout can remain black even when the guest is running, so UEFI
# uses standard VGA with bochs DRM. The isolated UEFI QEMU boot entry also
# selects Chromium's software ANGLE backend; production hardware is unchanged.
if [ "$FIRMWARE" = uefi ]; then
    QEMU_ARGS+=(-vga std)
else
    QEMU_ARGS+=(-device virtio-vga)
fi

if [ "$NETWORK" = offline ]; then
    QEMU_ARGS+=(-nic none)
else
    QEMU_ARGS+=(-nic "user,model=virtio-net-pci")
fi

if [ "$HEADLESS" = true ]; then
    QEMU_ARGS+=(-display none)
else
    QEMU_ARGS+=(-display "${QEMU_DISPLAY:-gtk}")
fi

if [ "$FIRMWARE" = uefi ]; then
    OVMF_CODE=""
    OVMF_VARS=""
    for candidate in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd; do
        if [ -f "$candidate" ]; then OVMF_CODE="$candidate"; break; fi
    done
    for candidate in /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd; do
        if [ -f "$candidate" ]; then OVMF_VARS="$candidate"; break; fi
    done
    if [ -z "$OVMF_CODE" ] || [ -z "$OVMF_VARS" ]; then
        fail "OVMF firmware files not found"
    fi
    VARS_COPY="$RUN_DIR/OVMF_VARS.fd"
    cp -- "$OVMF_VARS" "$VARS_COPY"
    chmod 0600 "$VARS_COPY"
    QEMU_ARGS+=(
        -drive "if=pflash,format=raw,unit=0,readonly=on,file=$OVMF_CODE"
        -drive "if=pflash,format=raw,unit=1,file=$VARS_COPY"
    )
fi

if [ "$DRY_RUN" = true ]; then
    printf '%q ' qemu-system-x86_64 "${QEMU_ARGS[@]}"
    printf '\n'
    exit 0
fi

QEMU_PID=""
cleanup() {
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    rm -f -- "$MONITOR_SOCKET"
}
trap cleanup EXIT INT TERM HUP

qemu-system-x86_64 "${QEMU_ARGS[@]}" &
QEMU_PID=$!

if [ "$DURATION" -eq 0 ]; then
    set +e
    wait "$QEMU_PID"
    status=$?
    set -e
    QEMU_PID=""
    exit "$status"
fi

command -v socat > /dev/null 2>&1 || fail "socat is required for bounded QEMU runs"
for _ in $(seq 1 100); do
    [ -S "$MONITOR_SOCKET" ] && break
    kill -0 "$QEMU_PID" 2>/dev/null || fail "QEMU exited before its monitor became ready"
    sleep 0.1
done
[ -S "$MONITOR_SOCKET" ] || fail "QEMU monitor did not become ready"

if [ "$QEMU_SMOKE" = true ]; then
    # Both bootloaders expose a q hotkey for the isolated QEMU entry. UEFI
    # firmware can take tens of seconds under TCG. Send short waves followed
    # by a quiet period so key repetition cannot interfere with kernel load.
    QEMU_BOOT_MARKER="systemd.setenv=WLR_RENDERER=pixman"
    if [ "$FIRMWARE" = uefi ]; then
        # Synchronize on OVMF handing control to the DVD. Esc stops GRUB's
        # short countdown; Up moves from production entry 1 to QEMU entry 0.
        for _ovmf in $(seq 1 90); do
            grep -Fq 'BdsDxe: starting Boot' "$SERIAL_LOG" && break
            sleep 1
        done
        grep -Fq 'BdsDxe: starting Boot' "$SERIAL_LOG" || \
            fail "UEFI firmware did not start the release ISO"
        for _esc in $(seq 1 15); do
            printf 'sendkey esc\n' | \
                socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
            sleep 1
        done
        for _key in $(seq 1 5); do
            {
                printf 'sendkey up\n'
                printf 'sendkey ret\n'
            } | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
            sleep 1
        done
        for _kernel in $(seq 1 90); do
            grep -Fq "$QEMU_BOOT_MARKER" "$SERIAL_LOG" && break
            sleep 1
        done
    else
        for _wave in $(seq 1 6); do
            for _key in $(seq 1 5); do
                {
                    printf 'sendkey q\n'
                    printf 'sendkey ret\n'
                } | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
                sleep 1
            done
            for _quiet in $(seq 1 30); do
                if grep -Fq "$QEMU_BOOT_MARKER" "$SERIAL_LOG"; then break 2; fi
                sleep 1
            done
        done
    fi
    grep -Fq "$QEMU_BOOT_MARKER" "$SERIAL_LOG" || \
        fail "QEMU-only boot entry was not selected"
fi

sleep "$DURATION"
kill -0 "$QEMU_PID" 2>/dev/null || fail "QEMU exited before the observation interval ended"
if [ "$QEMU_SMOKE" = true ]; then
    SCREENSHOT_CHECK="$PROJECT_ROOT/tests/qemu/check-screenshot.py"
    [ -f "$SCREENSHOT_CHECK" ] || fail "screenshot checker not found"
    screenshot_ready=false
    for _capture in $(seq 1 6); do
        {
            printf 'screendump "%s" -f ppm\n' "$SCREENSHOT_PPM"
        } | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
        if python3 "$SCREENSHOT_CHECK" "$SCREENSHOT_PPM" "$SCREENSHOT" > /dev/null 2>&1; then
            screenshot_ready=true
            break
        fi
        sleep 10
        kill -0 "$QEMU_PID" 2>/dev/null || \
            fail "QEMU exited while waiting for a complete screenshot"
    done
    [ "$screenshot_ready" = true ] || fail "QEMU did not render a complete kiosk screenshot"
else
    {
        printf 'screendump "%s" -f ppm\n' "$SCREENSHOT_PPM"
        printf 'screendump "%s" -f png\n' "$SCREENSHOT"
    } | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
fi
printf 'quit\n' | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
set +e
wait "$QEMU_PID"
qemu_status=$?
set -e
QEMU_PID=""
[ "$qemu_status" -eq 0 ] || fail "QEMU returned status $qemu_status"
[ -s "$SCREENSHOT" ] || fail "QEMU did not create a screenshot"
[ -s "$SCREENSHOT_PPM" ] || fail "QEMU did not create a PPM screenshot"

{
    printf 'FIRMWARE=%s\n' "$FIRMWARE"
    printf 'NETWORK=%s\n' "$NETWORK"
    printf 'DURATION=%s\n' "$DURATION"
    printf 'QEMU_STATUS=%s\n' "$qemu_status"
    printf 'SERIAL_LOG=%s\n' "$SERIAL_LOG"
    printf 'SCREENSHOT=%s\n' "$SCREENSHOT"
    printf 'SCREENSHOT_PPM=%s\n' "$SCREENSHOT_PPM"
} > "$RESULT_FILE"

echo "QEMU observation completed: $RUN_DIR"
