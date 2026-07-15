#!/usr/bin/env bats
# Tests for sushida-launch + sushida-session via stubs

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/launch-test"
    mkdir -p "$TEST_ROOT"
    export PATH="$TEST_ROOT/bin:$PATH"
    export SUSHIDA_OS_TEST_MODE=1
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/config.env"
    export SUSHIDA_OS_RUNTIME="$TEST_ROOT/run"
    export SUSHIDA_OS_AUDIO_TIMEOUT=1
    # Portable path to the real helper (works in container / CI)
    export SUSHIDA_OS_SESSION="${BATS_TEST_DIRNAME}/../../live-build/config/includes.chroot/usr/local/libexec/sushida-session"
    mkdir -p "$TEST_ROOT/run" "$TEST_ROOT/bin" "$TEST_ROOT/run/xdg-runtime"
    FIXTURE_PIDS=()

    export CAGE_LOG="$TEST_ROOT/cage.log"
    export CHROMIUM_LOG="$TEST_ROOT/chromium.log"
    export DBUS_LOG="$TEST_ROOT/dbus.log"
    export PW_LOG="$TEST_ROOT/pw.log"
    export WP_LOG="$TEST_ROOT/wp.log"
    export PP_LOG="$TEST_ROOT/pp.log"
    export PID_LOG="$TEST_ROOT/pids.log"
    true > "$CAGE_LOG" 2>/dev/null || true
    true > "$CHROMIUM_LOG" 2>/dev/null || true
    true > "$DBUS_LOG" 2>/dev/null || true
    true > "$PW_LOG" 2>/dev/null || true
    true > "$WP_LOG" 2>/dev/null || true
    true > "$PP_LOG" 2>/dev/null || true
    true > "$PID_LOG" 2>/dev/null || true

    printf '#!/bin/bash\necho "kiosk"\n' > "$TEST_ROOT/bin/id"
    chmod +x "$TEST_ROOT/bin/id"

    cat > "$TEST_ROOT/bin/cage" << 'SHIM'
#!/bin/bash
echo "CAGE_NARGS:$#" >> "${CAGE_LOG}"
for a in "$@"; do echo "CAGE_ARG:[$a]" >> "${CAGE_LOG}"; done
echo "CAGE_DBUS:${DBUS_SESSION_BUS_ADDRESS:-unset}" >> "${CAGE_LOG}"
echo "CAGE_XDG:${XDG_RUNTIME_DIR:-unset}" >> "${CAGE_LOG}"
echo "CAGE_HOME:${HOME:-unset}" >> "${CAGE_LOG}"
echo "cage:$$" >> "${PID_LOG}"
while [ $# -gt 0 ]; do case "$1" in --) shift; break ;; *) shift ;; esac; done
exec "$@"
SHIM
    chmod +x "$TEST_ROOT/bin/cage"

    cat > "$TEST_ROOT/bin/chromium" << 'SHIM'
#!/bin/bash
echo "CHROMIUM_NARGS:$#" >> "${CHROMIUM_LOG}"
for a in "$@"; do echo "CHROMIUM_ARG:[$a]" >> "${CHROMIUM_LOG}"; done
echo "CHROMIUM_DBUS:${DBUS_SESSION_BUS_ADDRESS:-unset}" >> "${CHROMIUM_LOG}"
echo "CHROMIUM_XDG:${XDG_RUNTIME_DIR:-unset}" >> "${CHROMIUM_LOG}"
echo "CHROMIUM_HOME:${HOME:-unset}" >> "${CHROMIUM_LOG}"
echo "chromium:$$" >> "${PID_LOG}"
if [ "${SUSHIDA_OS_CHROMIUM_HOLD:-0}" = "1" ]; then
    exec /usr/bin/sleep 30
fi
exit "${SUSHIDA_OS_CHROMIUM_EXIT:-0}"
SHIM
    chmod +x "$TEST_ROOT/bin/chromium"

    cat > "$TEST_ROOT/bin/pipewire" << 'SHIM'
#!/bin/bash
echo "PW_DBUS:${DBUS_SESSION_BUS_ADDRESS:-unset}" >> "${PW_LOG}"
echo "PW_XDG:${XDG_RUNTIME_DIR:-unset}" >> "${PW_LOG}"
echo "PW_HOME:${HOME:-unset}" >> "${PW_LOG}"
echo "pipewire:$$" >> "${PID_LOG}"
if [ "${SUSHIDA_OS_PW_FAIL:-0}" = "1" ]; then exit 1; fi
mkdir -p "${XDG_RUNTIME_DIR}"
if [ "${SUSHIDA_OS_PW_NO_SOCKET:-0}" = "1" ]; then
    exec /usr/bin/sleep 30
fi
exec python3 -c "
import socket, os, signal, sys, time
sp = os.environ['XDG_RUNTIME_DIR'] + '/pipewire-0'
if os.path.exists(sp): os.unlink(sp)
s = socket.socket(socket.AF_UNIX); s.bind(sp); s.listen(1)
def stop(*_args):
    try: os.unlink(sp)
    except FileNotFoundError: pass
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
if os.environ.get('SUSHIDA_OS_PW_EXIT_AFTER_READY') == '1':
    time.sleep(0.5)
    stop_code = int(os.environ.get('SUSHIDA_OS_PW_EXIT_STATUS', '0'))
    try: os.unlink(sp)
    except FileNotFoundError: pass
    sys.exit(stop_code)
while True: time.sleep(1)
"
SHIM
    chmod +x "$TEST_ROOT/bin/pipewire"

    cat > "$TEST_ROOT/bin/wireplumber" << 'WPSHIM'
#!/bin/bash
echo "WP_DBUS:${DBUS_SESSION_BUS_ADDRESS:-unset}" >> "${WP_LOG}"
echo "WP_XDG:${XDG_RUNTIME_DIR:-unset}" >> "${WP_LOG}"
echo "WP_HOME:${HOME:-unset}" >> "${WP_LOG}"
echo "wireplumber:$$" >> "${PID_LOG}"
if [ "${SUSHIDA_OS_WP_FAIL:-0}" = "1" ]; then exit 1; fi
if [ "${SUSHIDA_OS_WP_EXIT_AFTER_READY:-0}" = "1" ]; then
    /usr/bin/sleep 0.5
    exit "${SUSHIDA_OS_WP_EXIT_STATUS:-0}"
fi
exec /usr/bin/sleep 30
WPSHIM
    chmod +x "$TEST_ROOT/bin/wireplumber"

    cat > "$TEST_ROOT/bin/pipewire-pulse" << 'PPSHIM'
#!/bin/bash
echo "PP_DBUS:${DBUS_SESSION_BUS_ADDRESS:-unset}" >> "${PP_LOG}"
echo "PP_XDG:${XDG_RUNTIME_DIR:-unset}" >> "${PP_LOG}"
echo "PP_HOME:${HOME:-unset}" >> "${PP_LOG}"
echo "pipewire-pulse:$$" >> "${PID_LOG}"
if [ "${SUSHIDA_OS_PP_FAIL:-0}" = "1" ]; then exit 1; fi
if [ "${SUSHIDA_OS_PP_EXIT_AFTER_READY:-0}" = "1" ]; then
    /usr/bin/sleep 0.5
    exit "${SUSHIDA_OS_PP_EXIT_STATUS:-0}"
fi
exec /usr/bin/sleep 30
PPSHIM
    chmod +x "$TEST_ROOT/bin/pipewire-pulse"

    cat > "$TEST_ROOT/bin/dbus-run-session" << 'SHIM'
#!/bin/bash
echo "DBUS_NARGS:$#" >> "${DBUS_LOG}"
for a in "$@"; do echo "DBUS_ARG:[$a]" >> "${DBUS_LOG}"; done
case "$1" in --) shift ;; esac
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
exec "$@"
SHIM
    chmod +x "$TEST_ROOT/bin/dbus-run-session"

    cat > "$TEST_ROOT/bin/sleep" << 'SHIM'
#!/bin/bash
case "$1" in 0.1|0.2|0.3|0.5|1) exec /usr/bin/sleep "$1" ;; *) exec /usr/bin/sleep 2 ;; esac
SHIM
    chmod +x "$TEST_ROOT/bin/sleep"

    printf 'SUSHIDA_URL=https://sushida.net/play.html\nNETWORK_CHECK_INTERVAL_SECONDS=30\nKIOSK_RESTART_SECONDS=2\n' > "$SUSHIDA_OS_CONFIG"
}

teardown() {
    if [ -f "${PID_LOG:-}" ]; then
        while IFS=: read -r _name p; do
            case "$p" in ''|*[!0-9]*) continue ;; esac
            kill -9 "$p" 2>/dev/null || true
        done < "$PID_LOG"
    fi
    for p in "${FIXTURE_PIDS[@]}"; do
        case "$p" in ''|*[!0-9]*) continue ;; esac
        kill -9 "$p" 2>/dev/null || true; wait "$p" 2>/dev/null || true
    done
    FIXTURE_PIDS=()
}

LAUNCHER="live-build/config/includes.chroot/usr/local/bin/sushida-launch"
HELPER="live-build/config/includes.chroot/usr/local/libexec/sushida-session"

reset_logs() {
    true > "$CAGE_LOG"; true > "$CHROMIUM_LOG"; true > "$DBUS_LOG"
    true > "$PW_LOG"; true > "$WP_LOG"; true > "$PP_LOG"
    true > "$PID_LOG"
}

assert_logged_pids_dead() {
    local _name p
    while IFS=: read -r _name p; do
        case "$p" in ''|*[!0-9]*) continue ;; esac
        if kill -0 "$p" 2>/dev/null; then
            echo "fixture process still alive: ${_name}:${p}" >&2
            return 1
        fi
    done < "$PID_LOG"
}

run_launcher() {
    reset_logs
    run "$LAUNCHER"
}

# ── Happy path ─────────────────────────────────────────────────────────────

@test "launcher exits 0, chromium receives kiosk args" {
    run_launcher
    [ "$status" -eq 0 ]
    grep -qF "CHROMIUM_ARG:[--kiosk]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--no-first-run]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--no-default-browser-check]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--ozone-platform=wayland]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--hide-crash-restore-bubble]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--user-data-dir=$SUSHIDA_OS_RUNTIME/chromium]" "$CHROMIUM_LOG"
    grep -qF "CHROMIUM_ARG:[--disk-cache-dir=$SUSHIDA_OS_RUNTIME/cache]" "$CHROMIUM_LOG"
    assert_logged_pids_dead
}

@test "URL is last chromium argument" {
    run_launcher
    [ "$status" -eq 0 ]
    # Verify last CHROMIUM_ARG: line is the URL
    last_arg=$(grep "^CHROMIUM_ARG:" "$CHROMIUM_LOG" | tail -1)
    [ "$last_arg" = "CHROMIUM_ARG:[https://sushida.net/play.html]" ]
}

@test "preserves = and & in URL" {
    printf 'SUSHIDA_URL=https://sushida.net/?foo=bar&baz=qux\n' > "$SUSHIDA_OS_CONFIG"
    run_launcher
    [ "$status" -eq 0 ]
    grep -qF 'CHROMIUM_ARG:[https://sushida.net/?foo=bar&baz=qux]' "$CHROMIUM_LOG"
}

# shellcheck disable=SC2016
@test "does not evaluate command substitution" {
    printf 'SUSHIDA_URL=https://sushida.net/$(id)\n' > "$SUSHIDA_OS_CONFIG"
    run_launcher
    [ "$status" -eq 0 ]
    grep -qF 'CHROMIUM_ARG:[https://sushida.net/$(id)]' "$CHROMIUM_LOG"
}

@test "cage argv starts with -- chromium" {
    run_launcher
    [ "$status" -eq 0 ]
    # Check that first two args are exactly "--" and "chromium"
    first=$(grep "^CAGE_ARG:" "$CAGE_LOG" | sed -n '1s/CAGE_ARG:\[\(.*\)\]/\1/p')
    second=$(grep "^CAGE_ARG:" "$CAGE_LOG" | sed -n '2s/CAGE_ARG:\[\(.*\)\]/\1/p')
    [ "$first" = "--" ]
    [ "$second" = "chromium" ]
}

# shellcheck disable=SC2030  # BATS run sets output/status in its test subshell.
@test "env propagates to all processes" {
    run_launcher
    [ "$status" -eq 0 ]
    expected_dbus="unix:path=${SUSHIDA_OS_RUNTIME}/xdg-runtime/bus"
    expected_xdg="${SUSHIDA_OS_RUNTIME}/xdg-runtime"
    expected_home="${SUSHIDA_OS_RUNTIME}/home"
    grep -qFx "PW_DBUS:$expected_dbus" "$PW_LOG"
    grep -qFx "PW_XDG:$expected_xdg" "$PW_LOG"
    grep -qFx "PW_HOME:$expected_home" "$PW_LOG"
    grep -qFx "WP_DBUS:$expected_dbus" "$WP_LOG"
    grep -qFx "WP_XDG:$expected_xdg" "$WP_LOG"
    grep -qFx "WP_HOME:$expected_home" "$WP_LOG"
    grep -qFx "PP_DBUS:$expected_dbus" "$PP_LOG"
    grep -qFx "PP_XDG:$expected_xdg" "$PP_LOG"
    grep -qFx "PP_HOME:$expected_home" "$PP_LOG"
    grep -qFx "CAGE_DBUS:$expected_dbus" "$CAGE_LOG"
    grep -qFx "CAGE_XDG:$expected_xdg" "$CAGE_LOG"
    grep -qFx "CAGE_HOME:$expected_home" "$CAGE_LOG"
}

# ── URL rejection: launcher ────────────────────────────────────────────────

# shellcheck disable=SC2030,SC2031
reject_url() {
    printf "SUSHIDA_URL=%s\n" "$1" > "$SUSHIDA_OS_CONFIG"
    reset_logs
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
    [ ! -s "$CHROMIUM_LOG" ]
}

@test "launcher rejects arbitrary origin" { reject_url "https://evil.com/play.html"; }
@test "launcher rejects subdomain trick" { reject_url "https://sushida.net.evil.example/play.html"; }
@test "launcher rejects userinfo" { reject_url "https://user:pass@sushida.net/play.html"; }
@test "launcher rejects alternate port" { reject_url "https://sushida.net:8080/play.html"; }
@test "launcher rejects http" { reject_url "http://sushida.net/play.html"; }
@test "launcher rejects file" { reject_url "file:///usr/share/sushida-os/offline.html"; }
@test "launcher rejects javascript" { reject_url "javascript:alert(1)"; }
# shellcheck disable=SC2030  # BATS helper invokes run in this test subshell.
@test "launcher rejects data" { reject_url "data:text/html,<script>alert(1)</script>"; }

# ── URL rejection: helper direct ───────────────────────────────────────────

# shellcheck disable=SC2030,SC2031
reject_helper_url() {
    reset_logs
    run env XDG_RUNTIME_DIR="$TEST_ROOT/run/xdg-runtime" HOME="$TEST_ROOT/run/home" \
        SUSHIDA_OS_TEST_MODE=1 SUSHIDA_OS_AUDIO_TIMEOUT=1 \
        "$HELPER" "$1"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}

@test "helper rejects arbitrary origin" { reject_helper_url "https://evil.com"; }
@test "helper rejects subdomain trick" { reject_helper_url "https://sushida.net.evil.example"; }
@test "helper rejects userinfo" { reject_helper_url "https://user:pass@sushida.net/path"; }
@test "helper rejects alternate port" { reject_helper_url "https://sushida.net:8080/path"; }
@test "helper rejects http" { reject_helper_url "http://sushida.net"; }
@test "helper rejects file" { reject_helper_url "file:///usr/share/sushida-os/offline.html"; }
@test "helper rejects javascript" { reject_helper_url "javascript:alert(1)"; }
@test "helper rejects data" { reject_helper_url "data:text/html,<script>alert(1)</script>"; }
@test "helper rejects wrong arg count" { run "$HELPER"; [ "$status" -ne 0 ]; }

# ── Launcher boundary ──────────────────────────────────────────────────────

@test "rejects non-kiosk user" {
    printf '#!/bin/bash\necho "root"\n' > "$TEST_ROOT/bin/id"
    chmod +x "$TEST_ROOT/bin/id"
    reset_logs
    run "$LAUNCHER"
    [ "$status" -ne 0 ]; [[ "$output" == *"kiosk"* ]]
}

@test "rejects missing config file" {
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/nonexistent.env"
    reset_logs
    run "$LAUNCHER"
    [ "$status" -ne 0 ]; [[ "$output" == *"not found"* ]]
}

@test "rejects session helper override without TEST_MODE" {
    unset SUSHIDA_OS_TEST_MODE
    export SUSHIDA_OS_SESSION="$TEST_ROOT/evil-helper"
    reset_logs
    run "$LAUNCHER"
    [ "$status" -ne 0 ]; [[ "$output" == *"TEST_MODE"* ]]
}

# ── Runtime boundary ───────────────────────────────────────────────────────

@test "helper rejects wrong XDG_RUNTIME_DIR in production mode" {
    unset SUSHIDA_OS_TEST_MODE
    reset_logs
    run env XDG_RUNTIME_DIR=/tmp/foo HOME=/tmp/home "$HELPER" "https://sushida.net/play.html"
    [ "$status" -ne 0 ]; [[ "$output" == *"XDG_RUNTIME_DIR"* ]]
}

@test "helper accepts test mode XDG_RUNTIME_DIR" {
    reset_logs
    run env XDG_RUNTIME_DIR="$TEST_ROOT/run/xdg-runtime" HOME="$TEST_ROOT/run/home" \
        SUSHIDA_OS_TEST_MODE=1 SUSHIDA_OS_AUDIO_TIMEOUT=1 \
        "$HELPER" "https://sushida.net/play.html"
    [ "$status" -eq 0 ]
}

# ── Readiness / audio failure ──────────────────────────────────────────────

# shellcheck disable=SC2030,SC2031
run_helper() {
    reset_logs
    run env "$@" XDG_RUNTIME_DIR="$TEST_ROOT/run/xdg-runtime" HOME="$TEST_ROOT/run/home" \
        SUSHIDA_OS_TEST_MODE=1 SUSHIDA_OS_AUDIO_TIMEOUT=1 \
        "$HELPER" "https://sushida.net/play.html"
}

@test "readiness timeout fails session" {
    run_helper SUSHIDA_OS_PW_NO_SOCKET=1
    [ "$status" -ne 0 ]; [[ "$output" == *"not ready"* ]]
    [ ! -s "$CHROMIUM_LOG" ]
    assert_logged_pids_dead
}

@test "pipewire failure before readiness fails session" {
    run_helper SUSHIDA_OS_PW_FAIL=1
    [ "$status" -ne 0 ]; [[ "$output" == *"pipewire exited"* ]]
    [ ! -s "$CHROMIUM_LOG" ]
}

@test "wireplumber failure before readiness fails session" {
    run_helper SUSHIDA_OS_WP_FAIL=1
    [ "$status" -ne 0 ]; [[ "$output" == *"wireplumber exited"* ]]
    [ ! -s "$CHROMIUM_LOG" ]
}

@test "pipewire-pulse failure before readiness fails session" {
    run_helper SUSHIDA_OS_PP_FAIL=1
    [ "$status" -ne 0 ]; [[ "$output" == *"pipewire-pulse exited"* ]]
    [ ! -s "$CHROMIUM_LOG" ]
}

# ── Post-readiness audio exit ──────────────────────────────────────────────

@test "pipewire post-readiness exit 0 fails session" {
    run_helper SUSHIDA_OS_CHROMIUM_HOLD=1 \
        SUSHIDA_OS_PW_EXIT_AFTER_READY=1 SUSHIDA_OS_PW_EXIT_STATUS=0
    [ "$status" -ne 0 ]
    [[ "$output" == *"pipewire"* ]]
    [ -s "$CHROMIUM_LOG" ]
    assert_logged_pids_dead
}

@test "pipewire post-readiness non-zero exit fails session" {
    run_helper SUSHIDA_OS_CHROMIUM_HOLD=1 \
        SUSHIDA_OS_PW_EXIT_AFTER_READY=1 SUSHIDA_OS_PW_EXIT_STATUS=7
    [ "$status" -ne 0 ]
    [[ "$output" == *"pipewire"* ]]
    [ -s "$CHROMIUM_LOG" ]
    assert_logged_pids_dead
}

@test "wireplumber post-readiness exit 0 fails session" {
    run_helper SUSHIDA_OS_CHROMIUM_HOLD=1 SUSHIDA_OS_WP_EXIT_AFTER_READY=1
    [ "$status" -ne 0 ]
    [[ "$output" == *"wireplumber"* ]]
    [ -s "$CHROMIUM_LOG" ]
    assert_logged_pids_dead
}

@test "pipewire-pulse post-readiness exit 0 fails session" {
    run_helper SUSHIDA_OS_CHROMIUM_HOLD=1 SUSHIDA_OS_PP_EXIT_AFTER_READY=1
    [ "$status" -ne 0 ]
    [[ "$output" == *"pipewire-pulse"* ]]
    [ -s "$CHROMIUM_LOG" ]
    assert_logged_pids_dead
}

# ─── Cage exit status ──────────────────────────────────────────────────────

@test "cage exit 0 results in session exit 0" {
    run_helper
    [ "$status" -eq 0 ]
}

@test "cage exit 5 results in session exit 5" {
    run_helper SUSHIDA_OS_CHROMIUM_EXIT=5
    [ "$status" -eq 5 ]
    assert_logged_pids_dead
}

# ── Signal and cleanup ─────────────────────────────────────────────────────

@test "TERM results in status 143 and no leftover PIDs" {
    reset_logs
    SUSHIDA_OS_CHROMIUM_HOLD=1 "$LAUNCHER" &
    lp=$!
    FIXTURE_PIDS+=("$lp")
    _w=0
    while [ "$_w" -lt 20 ] && [ ! -s "$CHROMIUM_LOG" ]; do
        /usr/bin/sleep 0.1
        _w=$((_w + 1))
    done
    [ -s "$CHROMIUM_LOG" ]
    [ "$(wc -l < "$PID_LOG")" -ge 5 ]
    kill -TERM "$lp" 2>/dev/null || true
    term_status=0
    wait "$lp" 2>/dev/null || term_status=$?
    [ "$term_status" -eq 143 ]
    assert_logged_pids_dead
}

# ── Forbidden flags ─────────────────────────────────────────────────────────

@test "no forbidden flags in source" {
    for f in "$LAUNCHER" "$HELPER"; do
        run grep -cE '\-\-no\-sandbox|\-\-disable\-gpu|\-\-disable\-webgl|\-\-remote\-debugging' "$f"
        [ "$output" -eq 0 ]
    done
}

@test "no forbidden flags in chromium argv" {
    run_launcher
    for flag in --no-sandbox --disable-gpu --disable-webgl --remote-debugging; do
        run grep -qF "$flag" "$CHROMIUM_LOG"
        [ "$status" -ne 0 ]
    done
}
