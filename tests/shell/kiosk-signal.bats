#!/usr/bin/env bats
# Tests for the centralized validated kiosk restart helper.

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/kiosk-signal"
    mkdir -p "$TEST_ROOT/bin"
    export PATH="$TEST_ROOT/bin:$PATH"
    export SUSHIDA_OS_TEST_MODE=1
    export SUSHIDA_OS_TEST_CGROUP_FILE="$TEST_ROOT/cgroup"
    export SERVICE_ACTIVE=1
    export SYSTEMCTL_SHOW_FAIL=0
    export TEST_MAIN_PID=0
    HELPER="live-build/config/includes.chroot/usr/local/libexec/sushida-kiosk-signal"
    FIXTURE_PID=""

    printf '0::/system.slice/sushida-kiosk.service\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"

    cat > "$TEST_ROOT/bin/systemctl" <<'SHIM'
#!/bin/bash
case " $* " in
    *" is-active sushida-kiosk.service "*) [ "${SERVICE_ACTIVE:-0}" = 1 ] ;;
    *" show "*)
        [ "${SYSTEMCTL_SHOW_FAIL:-0}" = 0 ] || exit 1
        printf '%s\n' "${TEST_MAIN_PID:-0}"
        ;;
    *) exit 1 ;;
esac
SHIM
    chmod +x "$TEST_ROOT/bin/systemctl"

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

@test "terminates validated MainPID and logs fixed reason" {
    start_kiosk_fixture
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 0 ]
    [[ "$output" == *"kiosk-signal: reason=route-mismatch action=term"* ]]
    assert_fixture_terminated
}

@test "blocked-navigation reason is accepted" {
    start_kiosk_fixture
    run "$HELPER" --reason blocked-navigation
    [ "$status" -eq 0 ]
    [[ "$output" == *"reason=blocked-navigation action=term"* ]]
    assert_fixture_terminated
}

@test "dry run validates without signalling" {
    start_kiosk_fixture
    run "$HELPER" --reason route-mismatch --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"action=dry-run"* ]]
    assert_fixture_alive
}

@test "dry run reports refusal for an invalid target" {
    start_kiosk_fixture
    export SERVICE_ACTIVE=0
    run "$HELPER" --reason route-mismatch --dry-run
    [ "$status" -eq 1 ]
    [[ "$output" == *"action=refused"* ]]
    assert_fixture_alive
}

@test "requires a reason" {
    start_kiosk_fixture
    run "$HELPER"
    [ "$status" -eq 2 ]
    assert_fixture_alive
}

@test "rejects unsupported reason values" {
    start_kiosk_fixture
    run "$HELPER" --reason evil-reason
    [ "$status" -eq 2 ]
    assert_fixture_alive
}

@test "rejects arbitrary pid signal and service arguments" {
    start_kiosk_fixture
    for extra in "--pid 1" "--signal KILL" "--service evil.service" "extra"; do
        # shellcheck disable=SC2086
        run "$HELPER" --reason route-mismatch $extra
        [ "$status" -eq 2 ]
    done
    assert_fixture_alive
}

@test "test cgroup override requires test mode" {
    export SUSHIDA_OS_TEST_MODE=0
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 2 ]
    [[ "$output" == *"SUSHIDA_OS_TEST_MODE"* ]]
}

@test "inactive kiosk service refuses without signal" {
    start_kiosk_fixture
    export SERVICE_ACTIVE=0
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    [[ "$output" == *"action=refused"* ]]
    assert_fixture_alive
}

@test "MainPID zero refuses" {
    export TEST_MAIN_PID=0
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
}

@test "non-numeric MainPID refuses" {
    export TEST_MAIN_PID=oops
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
}

@test "nonexistent MainPID refuses" {
    export TEST_MAIN_PID=99999999
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
}

@test "systemctl show failure refuses" {
    start_kiosk_fixture
    export SYSTEMCTL_SHOW_FAIL=1
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    assert_fixture_alive
}

@test "different owner UID refuses without signal" {
    start_kiosk_fixture
    export STAT_UID=99999
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    assert_fixture_alive
}

@test "wrong cgroup refuses without signal" {
    printf '0::/user.slice/unrelated.service\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"
    start_kiosk_fixture
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    assert_fixture_alive
}

@test "cgroup substring does not pass exact service boundary" {
    printf '0::/system.slice/not-sushida-kiosk.service.extra\n' > "$SUSHIDA_OS_TEST_CGROUP_FILE"
    start_kiosk_fixture
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    assert_fixture_alive
}

@test "missing cgroup file refuses without signal" {
    rm "$SUSHIDA_OS_TEST_CGROUP_FILE"
    start_kiosk_fixture
    run "$HELPER" --reason route-mismatch
    [ "$status" -eq 1 ]
    assert_fixture_alive
}

@test "source validates UID cgroup and MainPID before TERM" {
    grep -qF "MainPID" "$HELPER"
    grep -qF "stat -c '%u'" "$HELPER"
    grep -qF 'sushida-kiosk\.service' "$HELPER"
    grep -qF 'kill -TERM -- "$pid"' "$HELPER"
}

@test "source has no browser invocation or external connectivity probe" {
    run grep -Eq 'chromium|curl|wget|ping|dig|nslookup|traceroute|ncat' "$HELPER"
    [ "$status" -ne 0 ]
}
