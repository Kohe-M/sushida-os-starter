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
WRITABLE_MEDIA_MODE=false
POWERDOWN=false
DURATION=0

usage() {
    cat <<'EOF'
Usage: scripts/run-qemu.sh [options]
  --firmware bios|uefi  Select legacy BIOS or UEFI (default: bios)
  --offline             Do not create a guest network interface
  --headless            Disable the QEMU display window
  --duration SECONDS    Capture a screenshot and quit after a bounded interval
  --qemu-smoke          Select the QEMU-only software-renderer boot entry
  --writable-media      Boot a private writable copy under build/qemu
  --powerdown           Send monitor system_powerdown and require natural exit
  --dry-run             Print the QEMU command without starting it
EOF
}

fail() {
    echo "ERROR: QEMU: $*" >&2
    exit 1
}

# systemd's serial console decorates status lines with ANSI colour sequences.
# Strip those sequences before matching lifecycle evidence so the checks are
# based on the actual unit messages rather than terminal presentation.
serial_without_ansi() {
    sed -E $'s/\x1B\\[[0-9;?]*[ -/]*[@-~]//g' "$SERIAL_LOG"
}

serial_matches() {
    serial_without_ansi | grep -Eiq "$1"
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
        --writable-media)
            WRITABLE_MEDIA_MODE=true
            shift
            ;;
        --powerdown)
            POWERDOWN=true
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
if [ "$POWERDOWN" = true ] && [ "$WRITABLE_MEDIA_MODE" = false ]; then
    fail "--powerdown requires --writable-media"
fi
if [ "$POWERDOWN" = true ] && [ "$DURATION" = 0 ]; then
    DURATION="${SUSHIDA_QEMU_POWERDOWN_TIMEOUT:-180}"
fi
[[ "$DURATION" =~ ^[0-9]+$ ]] || fail "duration must be a non-negative integer"
if [ "$HEADLESS" = true ] && [ "$DURATION" -eq 0 ] && [ "$DRY_RUN" = false ]; then
    fail "headless execution requires --duration"
fi
if [ ! -f "$ISO" ] || [ -L "$ISO" ] || [ ! -s "$ISO" ]; then
    fail "verified ISO not found: $ISO"
fi
for cmd in date git qemu-system-x86_64 sha256sum; do
    command -v "$cmd" > /dev/null 2>&1 || fail "required command not found: $cmd"
done

[ ! -L "$QEMU_ROOT" ] || fail "QEMU output root is a symlink"
RUN_SUFFIX=""
if [ "$POWERDOWN" = true ]; then
    RUN_SUFFIX="-powerdown"
fi
RUN_DIR="$QEMU_ROOT/$FIRMWARE-$NETWORK$RUN_SUFFIX"
if [ -e "$RUN_DIR" ] && [ -L "$RUN_DIR" ]; then
    fail "QEMU run directory is a symlink"
fi
SERIAL_LOG="$RUN_DIR/serial.log"
SCREENSHOT="$RUN_DIR/screenshot.png"
SCREENSHOT_PPM="$RUN_DIR/screenshot.ppm"
MONITOR_SOCKET="$RUN_DIR/monitor.sock"
RESULT_FILE="$RUN_DIR/result.env"
REPORT="$RUN_DIR/smoke-report.txt"
WRITABLE_MEDIA="$RUN_DIR/writable-media.img"

QEMU_ACCEL="tcg"
if [ -c /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
    QEMU_ACCEL="kvm:tcg"
fi

QEMU_ARGS=(
    -name "sushida-os-$FIRMWARE-$NETWORK"
    -machine "q35,accel=$QEMU_ACCEL"
    -m 2048
    -smp 2
    -audiodev "driver=none,id=sushida-audio"
    -device ich9-intel-hda
    -device "hda-duplex,audiodev=sushida-audio"
    -serial "file:$SERIAL_LOG"
    -monitor "unix:$MONITOR_SOCKET,server=on,wait=off"
    -no-reboot
)

if [ "$WRITABLE_MEDIA_MODE" = true ]; then
    QEMU_ARGS+=( -boot "order=c" )
    QEMU_ARGS+=( -drive "file=$WRITABLE_MEDIA,format=raw,if=virtio" )
else
    QEMU_ARGS+=( -boot "order=d" )
    QEMU_ARGS+=( -drive "file=$ISO,media=cdrom,readonly=on" )
fi

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

mkdir -p "$QEMU_ROOT" "$RUN_DIR"
rm -f -- "$SERIAL_LOG" "$SCREENSHOT" "$SCREENSHOT_PPM" "$MONITOR_SOCKET" \
    "$RESULT_FILE" "$REPORT"

if [ "$WRITABLE_MEDIA_MODE" = true ]; then
    rm -f -- "$WRITABLE_MEDIA"
    cp --reflink=auto -- "$ISO" "$WRITABLE_MEDIA"
    chmod 0600 "$WRITABLE_MEDIA"
fi

if [ "$FIRMWARE" = uefi ]; then
    cp -- "$OVMF_VARS" "$VARS_COPY"
    chmod 0600 "$VARS_COPY"
fi

ISO_SHA256="$(sha256sum "$ISO" | awk '{print $1}')"
GIT_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null)" || \
    fail "cannot determine current Git commit"
RUN_STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

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

if [ "$POWERDOWN" = true ]; then
    # Wait for the managed kiosk to reach the booted session before sending an
    # ACPI power-button event. The monitor is always the per-run socket below
    # build/qemu; no host shutdown command is ever used.
    kiosk_ready=false
    for _boot in $(seq 1 "$DURATION"); do
        if serial_matches 'Started[[:space:]]+sushida-kiosk\.service([[:space:]-]|$)'; then
            kiosk_ready=true
            break
        fi
        kill -0 "$QEMU_PID" 2>/dev/null || fail "QEMU exited before kiosk startup"
        sleep 1
    done
    [ "$kiosk_ready" = true ] || fail "kiosk did not start before powerdown timeout"
    printf 'system_powerdown\n' | socat - "UNIX-CONNECT:$MONITOR_SOCKET" > /dev/null
    powerdown_sent=true
    natural_powerdown=false
    for _shutdown in $(seq 1 "$DURATION"); do
        if ! kill -0 "$QEMU_PID" 2>/dev/null; then
            natural_powerdown=true
            break
        fi
        sleep 1
    done
    [ "$natural_powerdown" = true ] || fail "guest did not power down naturally"
    set +e
    wait "$QEMU_PID"
    qemu_status=$?
    set -e
    QEMU_PID=""
    [ "$qemu_status" -eq 0 ] || fail "QEMU returned status $qemu_status after powerdown"
    config_mount_seen=false
    config_unmount_seen=false
    if serial_matches \
        'Mounted[[:space:]].*(/var/lib/sushida-config|var-lib-sushida\\x2dconfig)'; then
        config_mount_seen=true
    fi
    if serial_matches \
        'Unmounted[[:space:]].*(/var/lib/sushida-config|var-lib-sushida\\x2dconfig)'; then
        config_unmount_seen=true
    fi
    RUN_FINISHED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    {
        printf 'FIRMWARE=%s\n' "$FIRMWARE"
        printf 'NETWORK=%s\n' "$NETWORK"
        printf 'WRITABLE_MEDIA=%s\n' "$WRITABLE_MEDIA_MODE"
        printf 'POWERDOWN_MODE=true\n'
        printf 'POWERDOWN_SENT=%s\n' "$powerdown_sent"
        printf 'NATURAL_POWERDOWN=%s\n' "$natural_powerdown"
        printf 'DURATION=%s\n' "$DURATION"
        printf 'QEMU_STATUS=%s\n' "$qemu_status"
        printf 'ISO_SHA256=%s\n' "$ISO_SHA256"
        printf 'GIT_COMMIT=%s\n' "$GIT_COMMIT"
        printf 'CONFIG_MOUNT_SEEN=%s\n' "$config_mount_seen"
        printf 'CONFIG_UNMOUNT_SEEN=%s\n' "$config_unmount_seen"
        printf 'RUN_STARTED_AT=%s\n' "$RUN_STARTED_AT"
        printf 'RUN_FINISHED_AT=%s\n' "$RUN_FINISHED_AT"
        printf 'SERIAL_LOG=%s\n' "$SERIAL_LOG"
        printf 'MONITOR_SOCKET=%s\n' "$MONITOR_SOCKET"
    } > "$RESULT_FILE"
    echo "QEMU powerdown completed: $RUN_DIR"
    exit 0
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

RUN_FINISHED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

{
    printf 'FIRMWARE=%s\n' "$FIRMWARE"
    printf 'NETWORK=%s\n' "$NETWORK"
    printf 'WRITABLE_MEDIA=%s\n' "$WRITABLE_MEDIA_MODE"
    printf 'DURATION=%s\n' "$DURATION"
    printf 'QEMU_STATUS=%s\n' "$qemu_status"
    printf 'ISO_SHA256=%s\n' "$ISO_SHA256"
    printf 'GIT_COMMIT=%s\n' "$GIT_COMMIT"
    printf 'RUN_STARTED_AT=%s\n' "$RUN_STARTED_AT"
    printf 'RUN_FINISHED_AT=%s\n' "$RUN_FINISHED_AT"
    printf 'SERIAL_LOG=%s\n' "$SERIAL_LOG"
    printf 'SCREENSHOT=%s\n' "$SCREENSHOT"
    printf 'SCREENSHOT_PPM=%s\n' "$SCREENSHOT_PPM"
} > "$RESULT_FILE"

echo "QEMU observation completed: $RUN_DIR"
