#!/usr/bin/env bats
# Dynamic tests for the low-frequency kiosk route watcher.

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/network-watch"
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/run"
    export PATH="$TEST_ROOT/bin:$PATH"
    export SUSHIDA_OS_TEST_MODE=1
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/config.env"
    export SUSHIDA_OS_RUNTIME="$TEST_ROOT/run"
    export SUSHIDA_OS_MAX_ITERATIONS=1
    export SUSHIDA_OS_TEST_CGROUP_FILE="$TEST_ROOT/cgroup"
    export NM_STATE=connected
    export NM_FAIL=0
    export SERVICE_ACTIVE=1
    export SETUP_SERVICE_ACTIVE=1
    export SYSTEMCTL_SHOW_FAIL=0
    export TEST_MAIN_PID=0
    WATCHER="live-build/config/includes.chroot/usr/local/bin/sushida-network-watch"
    FIXTURE_PID=""

    printf 'SUSHIDA_URL=https://sushida.net/play.html\nNETWORK_SETUP_GRACE_SECONDS=15\nNETWORK_CHECK_INTERVAL_SECONDS=30\n' > "$SUSHIDA_OS_CONFIG"
    printf 'online\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    printf '0::/system.slice/sushida-kiosk.service\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"
    : > "$TEST_ROOT/sleep.log"

cat > "$TEST_ROOT/bin/nmcli" <<'SHIM'
#!/bin/bash
[ "${NM_FAIL:-0}" = 0 ] || exit 1
printf '%s\n' "${NM_STATE:-connected}:${NM_CONNECTIVITY:-full}"
SHIM
    chmod +x "$TEST_ROOT/bin/nmcli"

    cat > "$TEST_ROOT/bin/systemctl" <<'SHIM'
#!/bin/bash
case " $* " in
    *" is-active sushida-wifi-setup.service "*) [ "${SETUP_SERVICE_ACTIVE:-0}" = 1 ] ;;
    *" is-active sushida-kiosk.service "*) [ "${SERVICE_ACTIVE:-0}" = 1 ] ;;
    *" show "*)
        [ "${SYSTEMCTL_SHOW_FAIL:-0}" = 0 ] || exit 1
        printf '%s\n' "${TEST_MAIN_PID:-0}"
        ;;
    *) exit 1 ;;
esac
SHIM
    chmod +x "$TEST_ROOT/bin/systemctl"

    cat > "$TEST_ROOT/bin/sleep" <<'SHIM'
#!/bin/bash
printf '%s\n' "$1" >> "${TEST_ROOT}/sleep.log"
SHIM
    chmod +x "$TEST_ROOT/bin/sleep"

    cat > "$TEST_ROOT/bin/stat" <<'SHIM'
#!/bin/bash
if [ -n "${STAT_UID:-}" ]; then printf '%s\n' "$STAT_UID"; else exec /usr/bin/stat "$@"; fi
SHIM
    chmod +x "$TEST_ROOT/bin/stat"
    export TEST_ROOT
}

teardown() {
    if [ -n "${FIXTURE_PID:-}" ]; then
        kill -9 "$FIXTURE_PID" 2>/dev/null || true
        wait "$FIXTURE_PID" 2>/dev/null || true
    fi
}

start_kiosk_fixture() {
    /usr/bin/sleep 30 &
    FIXTURE_PID=$!
    export TEST_MAIN_PID="$FIXTURE_PID"
}

assert_fixture_alive() {
    kill -0 "$FIXTURE_PID"
}

assert_fixture_terminated() {
    local attempts=0
    while kill -0 "$FIXTURE_PID" 2>/dev/null && [ "$attempts" -lt 5 ]; do
        /usr/bin/sleep 0.05
        attempts=$((attempts + 1))
    done
    ! kill -0 "$FIXTURE_PID" 2>/dev/null
    wait "$FIXTURE_PID" 2>/dev/null || true
    FIXTURE_PID=""
}

run_watcher() { run "$WATCHER"; }

@test "same online route does not restart kiosk" {
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "same setup route does not restart kiosk" {
    printf 'setup\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "QEMU smoke markers keep offline route despite connected test NIC" {
    printf 'offline\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    export SUSHIDA_QEMU_FORCE_OFFLINE=1
    export SUSHIDA_QEMU_CHROMIUM_SWIFTSHADER=1
    export WLR_RENDERER=pixman
    export WLR_RENDERER_ALLOW_SOFTWARE=1
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "watcher rejects QEMU force-offline marker without renderer markers" {
    export SUSHIDA_QEMU_FORCE_OFFLINE=1
    run_watcher
    [ "$status" -ne 0 ]
    [[ "$output" == *"requires all QEMU renderer markers"* ]]
}

@test "online to setup transition terminates validated MainPID" {
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_terminated
}

@test "setup to online transition terminates validated MainPID" {
    printf 'setup\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_terminated
}

@test "nmcli failure selects setup and triggers a validated transition" {
    export NM_FAIL=1
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_terminated
}

@test "limited connectivity states select setup" {
    local state
    for state in connected.local connected.site connecting unknown disconnected; do
        export NM_STATE="$state"
        start_kiosk_fixture
        run_watcher
        [ "$status" -eq 0 ]
        assert_fixture_terminated
    done
}

@test "setup backend failure preserves matching offline fallback" {
    printf 'offline\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    export NM_STATE=disconnected SETUP_SERVICE_ACTIVE=0
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "missing active route marker fails closed without signal" {
    rm "$SUSHIDA_OS_RUNTIME/active-route"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "invalid active route marker fails closed without signal" {
    printf 'ONLINE\n' > "$SUSHIDA_OS_RUNTIME/active-route"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "inactive kiosk service fails closed without signal" {
    export NM_STATE=disconnected SERVICE_ACTIVE=0
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "MainPID zero fails closed" {
    export NM_STATE=disconnected TEST_MAIN_PID=0
    run_watcher
    [ "$status" -eq 0 ]
}

@test "non-numeric MainPID fails closed" {
    export NM_STATE=disconnected TEST_MAIN_PID=oops
    run_watcher
    [ "$status" -eq 0 ]
}

@test "nonexistent MainPID fails closed" {
    export NM_STATE=disconnected TEST_MAIN_PID=99999999
    run_watcher
    [ "$status" -eq 0 ]
}

@test "systemctl show failure fails closed" {
    export NM_STATE=disconnected SYSTEMCTL_SHOW_FAIL=1
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "different owner UID fails closed without signal" {
    export NM_STATE=disconnected STAT_UID=99999
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "wrong cgroup fails closed without signal" {
    printf '0::/user.slice/unrelated.service\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "missing cgroup file fails closed without signal" {
    rm "$SUSHIDA_OS_TEST_CGROUP_FILE"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "cgroup substring does not pass exact service boundary" {
    printf '0::/system.slice/not-sushida-kiosk.service.extra\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"
    export NM_STATE=disconnected
    start_kiosk_fixture
    run_watcher
    [ "$status" -eq 0 ]
    assert_fixture_alive
}

@test "watcher sleeps at configured minimum after iteration" {
    run_watcher
    [ "$status" -eq 0 ]
    grep -qFx 30 "$TEST_ROOT/sleep.log"
}

reject_interval() {
    printf 'SUSHIDA_URL=https://sushida.net/play.html\nNETWORK_CHECK_INTERVAL_SECONDS=%s\n' "$1" > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -ne 0 ]
}

@test "rejects interval below minimum" { reject_interval 29; }
@test "rejects zero interval" { reject_interval 0; }
@test "rejects negative interval" { reject_interval -1; }
@test "rejects non-integer interval" { reject_interval 30x; }
@test "rejects interval above maximum" { reject_interval 3601; }
@test "accepts maximum interval" {
    printf 'SUSHIDA_URL=https://sushida.net/play.html\nNETWORK_CHECK_INTERVAL_SECONDS=3600\n' > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -eq 0 ]
    grep -qFx 3600 "$TEST_ROOT/sleep.log"
}

reject_url() {
    printf 'SUSHIDA_URL=%s\nNETWORK_CHECK_INTERVAL_SECONDS=30\n' "$1" > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -ne 0 ]
    [[ "$output" == *disallowed* ]]
}

@test "rejects arbitrary origin" { reject_url https://evil.example/; }
@test "rejects subdomain trick" { reject_url https://sushida.net.evil.example/; }
@test "rejects userinfo" { reject_url https://user@sushida.net/; }
@test "rejects alternate port" { reject_url https://sushida.net:8443/; }
@test "rejects HTTP" { reject_url http://sushida.net/; }
@test "rejects file URL" { reject_url file:///etc/passwd; }
@test "rejects javascript URL" { reject_url 'javascript:alert(1)'; }
@test "rejects data URL" { reject_url 'data:text/html,hello'; }

@test "rejects unknown config key" {
    printf 'SUSHIDA_URL=https://sushida.net/\nEVIL=value\n' > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -ne 0 ]
}

@test "rejects duplicate URL" {
    printf 'SUSHIDA_URL=https://sushida.net/\nSUSHIDA_URL=https://sushida.net/play.html\n' > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -ne 0 ]
}

@test "does not evaluate config content" {
    marker="$TEST_ROOT/injected"
    printf 'SUSHIDA_URL=https://sushida.net/$(touch %s)\n' "$marker" > "$SUSHIDA_OS_CONFIG"
    run_watcher
    [ "$status" -eq 0 ]
    [ ! -e "$marker" ]
}

@test "test cgroup override requires test mode" {
    export SUSHIDA_OS_TEST_MODE=0
    run "$WATCHER"
    [ "$status" -ne 0 ]
}

@test "max iterations override requires test mode" {
    export SUSHIDA_OS_TEST_MODE=0
    unset SUSHIDA_OS_CONFIG SUSHIDA_OS_RUNTIME SUSHIDA_OS_TEST_CGROUP_FILE
    run "$WATCHER"
    [ "$status" -ne 0 ]
}

@test "source has no browser invocation or external connectivity probe" {
    run grep -Eq 'chromium|curl|wget|ping|dig|nslookup|traceroute|ncat' "$WATCHER"
    [ "$status" -ne 0 ]
    run grep -Eq 'Singleton(Lock|Socket|Cookie)|remote-debugging' "$WATCHER"
    [ "$status" -ne 0 ]
}

@test "source validates UID cgroup and MainPID before TERM" {
    grep -qF "MainPID" "$WATCHER"
    grep -qF "stat -c '%u'" "$WATCHER"
    grep -qF 'sushida-kiosk\.service' "$WATCHER"
    grep -qF 'kill -TERM -- "$pid"' "$WATCHER"
}
