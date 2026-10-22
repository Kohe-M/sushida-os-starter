#!/usr/bin/env bats
# Tests for the boot-splash handoff gate and the boot read-ahead helper.

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/boot-splash"
    mkdir -p "$TEST_ROOT"
    HANDOFF="live-build/config/includes.chroot/usr/local/libexec/sushida-splash-handoff"
    PRELOAD="live-build/config/includes.chroot/usr/local/libexec/sushida-preload"
    MARKER_HELPER="live-build/config/includes.chroot/usr/local/libexec/sushida-serial-marker"
    STATE_FILE="$TEST_ROOT/runtime-state.json"
    WRITER_PID=""
    # The handoff reports through the serial marker; a stub records the stage
    # so these tests never touch a real serial port.
    MARKER_STUB="$TEST_ROOT/marker-stub"
    MARKER_LOG="$TEST_ROOT/marker.log"
    printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n' "$MARKER_LOG" > "$MARKER_STUB"
    chmod +x "$MARKER_STUB"
    SERIAL_FILE="$TEST_ROOT/ttyS0"
    : > "$SERIAL_FILE"
}

teardown() {
    if [ -n "${WRITER_PID:-}" ]; then
        kill -9 "$WRITER_PID" 2>/dev/null || true
        wait "$WRITER_PID" 2>/dev/null || true
    fi
}

run_handoff() {
    SUSHIDA_OS_TEST_MODE=1 \
    SUSHIDA_SPLASH_STATE_FILE="$STATE_FILE" \
    SUSHIDA_SPLASH_MAX_WAIT_SECONDS="$1" \
    SUSHIDA_SPLASH_MARKER="$MARKER_STUB" \
        run "$HANDOFF"
}

run_marker() {
    SUSHIDA_OS_TEST_MODE=1 \
    SUSHIDA_SERIAL_MARKER_DEVICE="$SERIAL_FILE" \
    SUSHIDA_SERIAL_MARKER_CONFIG_MOUNT="$1" \
        run "$MARKER_HELPER" "$2"
}

@test "handoff returns at once when the route is already published" {
    printf '{}\n' > "$STATE_FILE"
    SECONDS=0
    run_handoff 5
    [ "$status" -eq 0 ]
    [ "$output" = "splash-handoff: stage=route-published" ]
    [ "$SECONDS" -lt 2 ]
    [ "$(cat "$MARKER_LOG")" = "kiosk-route-published" ]
}

@test "handoff releases the splash as soon as the launcher publishes the route" {
    ( /usr/bin/sleep 0.5; printf '{}\n' > "$STATE_FILE" ) &
    WRITER_PID=$!
    SECONDS=0
    run_handoff 10
    [ "$status" -eq 0 ]
    [ "$output" = "splash-handoff: stage=route-published" ]
    [ "$SECONDS" -lt 5 ]
}

@test "handoff wait is bounded and still lets Plymouth quit" {
    SECONDS=0
    run_handoff 1
    [ "$status" -eq 0 ]
    [ "$output" = "splash-handoff: stage=timeout" ]
    [ "$SECONDS" -lt 5 ]
    [ "$(cat "$MARKER_LOG")" = "splash-timeout" ]
}

@test "handoff still releases the splash when the marker fails" {
    printf '{}\n' > "$STATE_FILE"
    printf '#!/bin/sh\nexit 1\n' > "$MARKER_STUB"
    run_handoff 5
    [ "$status" -eq 0 ]
    [ "$output" = "splash-handoff: stage=route-published" ]
}

@test "handoff rejects a marker override outside test mode" {
    SUSHIDA_SPLASH_MARKER="$MARKER_STUB" run "$HANDOFF"
    [ "$status" -eq 1 ]
    [[ "$output" == *"overrides require SUSHIDA_OS_TEST_MODE=1"* ]]
}

@test "serial marker writes one fixed line for a mounted config filesystem" {
    run_marker / kiosk-route-published
    [ "$status" -eq 0 ]
    [ "$output" = "sushida-os-marker: stage=kiosk-route-published config=mounted" ]
    [ "$(tr -d '\r' < "$SERIAL_FILE")" = "$output" ]
}

@test "serial marker reports an absent config filesystem at shutdown" {
    mkdir -p "$TEST_ROOT/not-a-mount"
    run_marker "$TEST_ROOT/not-a-mount" shutdown
    [ "$status" -eq 0 ]
    [ "$output" = "sushida-os-marker: stage=shutdown config=unmounted" ]
    [ "$(tr -d '\r' < "$SERIAL_FILE")" = "$output" ]
}

@test "serial marker appends rather than overwriting the serial stream" {
    printf 'earlier output\n' > "$SERIAL_FILE"
    run_marker / splash-timeout
    [ "$status" -eq 0 ]
    [ "$(head -1 "$SERIAL_FILE")" = "earlier output" ]
    [ "$(tail -1 "$SERIAL_FILE" | tr -d '\r')" = "sushida-os-marker: stage=splash-timeout config=mounted" ]
}

@test "serial marker accepts only its fixed stages" {
    run_marker / "online https://example.invalid/"
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown serial marker stage"* ]]
    [[ "$output" != *example.invalid* ]]
    [ ! -s "$SERIAL_FILE" ]
    run_marker / ""
    [ "$status" -eq 1 ]
}

@test "serial marker rejects overrides outside test mode" {
    SUSHIDA_SERIAL_MARKER_DEVICE="$SERIAL_FILE" run "$MARKER_HELPER" shutdown
    [ "$status" -eq 1 ]
    [[ "$output" == *"overrides require SUSHIDA_OS_TEST_MODE=1"* ]]
    [ ! -s "$SERIAL_FILE" ]
}

@test "handoff never prints the state file content" {
    printf '{"route":"online","reason":"SECRET-MARKER"}\n' > "$STATE_FILE"
    run_handoff 5
    [ "$status" -eq 0 ]
    [[ "$output" != *SECRET-MARKER* ]]
    [[ "$output" != *"$STATE_FILE"* ]]
}

@test "handoff rejects a state-file override outside test mode" {
    SUSHIDA_SPLASH_STATE_FILE="$STATE_FILE" run "$HANDOFF"
    [ "$status" -eq 1 ]
    [[ "$output" == *"overrides require SUSHIDA_OS_TEST_MODE=1"* ]]
}

@test "handoff rejects a wait override outside test mode" {
    SUSHIDA_SPLASH_MAX_WAIT_SECONDS=1 run "$HANDOFF"
    [ "$status" -eq 1 ]
    [[ "$output" == *"overrides require SUSHIDA_OS_TEST_MODE=1"* ]]
}

@test "handoff rejects a non-numeric wait" {
    run_handoff "1; true"
    [ "$status" -eq 1 ]
    [[ "$output" == *"invalid splash handoff wait"* ]]
}

@test "preload is best-effort and reports a bounded summary" {
    run "$PRELOAD"
    [ "$status" -eq 0 ]
    [[ "$output" =~ ^"preload: stage=done files="[0-9]+/10$ ]]
}

@test "preload ignores arguments and the environment" {
    PRELOAD_FILES=/etc/shadow run "$PRELOAD" /etc/shadow
    [ "$status" -eq 0 ]
    [[ "$output" =~ ^"preload: stage=done files="[0-9]+/10$ ]]
}

@test "initramfs trim hook takes only the large AMD/Xe GPU drivers off the queue" {
    TRIM="live-build/config/includes.chroot/etc/initramfs-tools/hooks/sushida-trim-gpu"
    queue="$TEST_ROOT/modules-queue"
    printf '%s\n' i915 amdgpu radeon xe amdxcp xe_foo usb_storage amdgpu > "$queue"

    run "$TRIM" prereqs
    [ "$status" -eq 0 ]
    [ -z "$output" ]

    __MODULES_TO_ADD="$queue" run "$TRIM"
    [ "$status" -eq 0 ]
    [ "$(cat "$queue")" = "$(printf '%s\n' i915 radeon amdxcp xe_foo usb_storage)" ]
}

@test "initramfs trim hook empties a queue holding only dropped drivers" {
    TRIM="live-build/config/includes.chroot/etc/initramfs-tools/hooks/sushida-trim-gpu"
    queue="$TEST_ROOT/modules-queue"
    printf '%s\n' amdgpu xe > "$queue"
    __MODULES_TO_ADD="$queue" run "$TRIM"
    [ "$status" -eq 0 ]
    [ ! -s "$queue" ]
}

@test "initramfs trim hook is a no-op without a module queue" {
    TRIM="live-build/config/includes.chroot/etc/initramfs-tools/hooks/sushida-trim-gpu"
    __MODULES_TO_ADD="" run "$TRIM"
    [ "$status" -eq 0 ]
    __MODULES_TO_ADD="$TEST_ROOT/missing" run "$TRIM"
    [ "$status" -eq 0 ]
    [ ! -e "$TEST_ROOT/missing" ]
}
