#!/usr/bin/env bats

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/watch-test"
    mkdir -p "$TEST_ROOT" "$TEST_ROOT/run" "$TEST_ROOT/bin"
    export PATH="$TEST_ROOT/bin:$PATH"
    export SUSHIDA_OS_TEST_MODE=1
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/config.env"
    export SUSHIDA_OS_RUNTIME="$TEST_ROOT/run"
    export SUSHIDA_OS_MAX_ITERATIONS=1

    for prog in systemctl nmcli sleep chromium timeout; do
        cat > "$TEST_ROOT/bin/$prog" <<'INNER'
#!/bin/bash
INNER
    done

    cat > "$TEST_ROOT/bin/systemctl" <<'SHIM'
#!/bin/bash
if [ "${SUSHIDA_OS_TEST_KIOSK_ACTIVE:-1}" = "1" ]; then exit 0; else exit 1; fi
SHIM
    cat > "$TEST_ROOT/bin/nmcli" <<'SHIM'
#!/bin/bash
if [ "${SUSHIDA_OS_TEST_NM_FAIL:-0}" = "1" ]; then exit 1; fi
echo "${SUSHIDA_OS_TEST_NM_STATE:-connected}"
SHIM
    cat > "$TEST_ROOT/bin/sleep" <<'SHIM'
#!/bin/bash
echo "$@" >> "${SUSHIDA_OS_SLEEP_LOG:-/dev/null}"
SHIM
    cat > "$TEST_ROOT/bin/chromium" <<'SHIM'
#!/bin/bash
echo "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"
SHIM
    cat > "$TEST_ROOT/bin/timeout" <<'SHIM'
#!/bin/bash
/usr/bin/timeout "$@"
SHIM
    chmod +x "$TEST_ROOT/bin/"*

    printf '%s\n' 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=30' 'KIOSK_RESTART_SECONDS=2' > "$SUSHIDA_OS_CONFIG"

    export SUSHIDA_OS_SLEEP_LOG="$TEST_ROOT/sleep.log"
    export SUSHIDA_OS_CHROMIUM_LOG="$TEST_ROOT/chromium.log"
    > "$SUSHIDA_OS_SLEEP_LOG"
    > "$SUSHIDA_OS_CHROMIUM_LOG"
    export SUSHIDA_OS_TEST_KIOSK_ACTIVE=1
    export SUSHIDA_OS_TEST_NM_STATE=connected
    FIXTURE_PIDS=()
}

# Cleanup all recorded fixture PIDs: TERM, bounded wait, then KILL.
# Idempotent -- safe to call multiple times.
cleanup_fixtures() {
    local p
    for p in "${FIXTURE_PIDS[@]}"; do
        case "$p" in ''|*[!0-9]*) continue ;; esac
        kill "$p" 2>/dev/null || true
    done
    # bounded wait for graceful exit
    /usr/bin/sleep 0.3 2>/dev/null || true
    for p in "${FIXTURE_PIDS[@]}"; do
        case "$p" in ''|*[!0-9]*) continue ;; esac
        kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true
        wait "$p" 2>/dev/null || true
    done
    FIXTURE_PIDS=()
}

teardown() {
    cleanup_fixtures
}

WATCHER="live-build/config/includes.chroot/usr/local/bin/sushida-network-watch"
SERVICE_UNIT="live-build/config/includes.chroot/etc/systemd/system/sushida-network-watch.service"

reset_run() { rm -f "$TEST_ROOT/run/network-state"; > "$SUSHIDA_OS_SLEEP_LOG"; > "$SUSHIDA_OS_CHROMIUM_LOG"; }

setup_singleton_fixtures() {
    local d="$1"; mkdir -p "$d"
    # Start sleep process (redirect output to avoid holding pipes)
    /usr/bin/sleep 60 > /dev/null 2>&1 &
    FIXTURE_PIDS+=("$!")
    ln -sf "testhost-${FIXTURE_PIDS[-1]}" "$d/SingletonLock"
    local st; st=$(mktemp -d "$d/tmp-socket.XXXXXX")
    local sp="$st/SingletonSocket"
    local cv="COOKIE_DEADBEEF12345678"
    python3 -c 'import socket,os,time,sys;sp=sys.argv[1];s=socket.socket(socket.AF_UNIX);s.bind(sp);s.listen(1);os.chmod(sp,0o700);
while True:
    try: time.sleep(1)
    except: os.unlink(sp); raise
' "$sp" > /dev/null 2>&1 &
    FIXTURE_PIDS+=("$!")
    local w=0
    while [ "$w" -lt 30 ] && [ ! -S "$sp" ]; do /usr/bin/sleep 0.1; w=$((w + 1)); done
    rm -f "$d/SingletonSocket"; ln -sf "$sp" "$d/SingletonSocket"
    ln -sf "$cv" "$st/SingletonCookie"; ln -sf "$cv" "$d/SingletonCookie"
}

putconf() { printf '%s\n' "$@" > "$SUSHIDA_OS_CONFIG"; }

# ── Minimum interval ──────────────────────────────────────────────────────

@test "rejects interval below minimum (29)" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=29'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"below minimum"* ]]; }
@test "rejects interval 5" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=5'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"below minimum"* ]]; }
@test "rejects zero interval" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=0'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"below minimum"* ]]; }
@test "rejects negative interval" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=-5'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "rejects non-integer interval" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=abc'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "rejects empty interval" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS='; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "rejects interval exceeding maximum" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=3601'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"exceeds maximum"* ]]; }
@test "accepts interval 30" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=30'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; }
@test "sleep is called with at least 30" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "30" "$SUSHIDA_OS_SLEEP_LOG"; }

# ── NM state ──────────────────────────────────────────────────────────────

@test "connected (global) is online" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "connected.local is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected.local; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "connected.site is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected.site; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "disconnected is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "connecting is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connecting; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "unknown state is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=unknown; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "nmcli failure is offline" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_FAIL=1; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── State machine ─────────────────────────────────────────────────────────

@test "first offline navigates to offline page once" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "offline steady does not navigate again" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ "$(wc -l < "$SUSHIDA_OS_CHROMIUM_LOG")" -eq 1 ]; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "offline to online recovery navigates to official URL once" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; run "$WATCHER"; run "$WATCHER"; > "$SUSHIDA_OS_CHROMIUM_LOG"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "https://sushida.net/play.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$(wc -l < "$SUSHIDA_OS_CHROMIUM_LOG")" -eq 1 ]; }
@test "online steady does not navigate again" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "online to offline transition navigates to offline page" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; run "$WATCHER"; > "$SUSHIDA_OS_CHROMIUM_LOG"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "multiple cycles do not accumulate invocations" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; run "$WATCHER"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$(wc -l < "$SUSHIDA_OS_CHROMIUM_LOG")" -eq 1 ]; export SUSHIDA_OS_TEST_NM_STATE=connected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "https://sushida.net/play.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$(wc -l < "$SUSHIDA_OS_CHROMIUM_LOG")" -eq 1 ]; export SUSHIDA_OS_TEST_NM_STATE=disconnected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$(wc -l < "$SUSHIDA_OS_CHROMIUM_LOG")" -eq 1 ]; }

# ── Navigation failure ────────────────────────────────────────────────────

@test "navigate failure (chromium exits 1) does not update state (offline)" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\nexit 1\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "navigate failure (chromium exits 1) does not update state (online)" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; run "$WATCHER"; run "$WATCHER"; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\nexit 1\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "https://sushida.net/play.html" "$SUSHIDA_OS_CHROMIUM_LOG"; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "https://sushida.net/play.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── Timeout tests ─────────────────────────────────────────────────────────

@test "chromium hang is bounded by timeout (SIGTERM)" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_NAV_TIMEOUT=1; export SUSHIDA_OS_TEST_NM_STATE=disconnected; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\n/usr/bin/sleep 60\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ ! -f "$SUSHIDA_OS_RUNTIME/network-state" ]; }
@test "SIGTERM-ignore chromium is killed by SIGKILL" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_NAV_TIMEOUT=1; export SUSHIDA_OS_TEST_NM_STATE=disconnected; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\ntrap "" TERM\nwhile true; do /usr/bin/sleep 1; done\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; [ ! -f "$SUSHIDA_OS_RUNTIME/network-state" ]; }
@test "timeout retries with working chromium" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_NAV_TIMEOUT=1; export SUSHIDA_OS_TEST_NM_STATE=disconnected; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\n/usr/bin/sleep 60\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; grep -qF "OFFLINE_FIRST" "$SUSHIDA_OS_RUNTIME/network-state"; }
@test "SIGTERM-ignore timeout retries" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_NAV_TIMEOUT=1; export SUSHIDA_OS_TEST_NM_STATE=disconnected; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\ntrap "" TERM\nwhile true; do /usr/bin/sleep 1; done\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; printf '#!/bin/bash\necho "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"\n' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; grep -qF "OFFLINE_FIRST" "$SUSHIDA_OS_RUNTIME/network-state"; }

# ── Kiosk precondition ────────────────────────────────────────────────────

@test "does not navigate when kiosk service is inactive" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_KIOSK_ACTIVE=0; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }

@test "multiple fixture creations are all cleaned up" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; local p1="${FIXTURE_PIDS[*]}"; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; local p2="${FIXTURE_PIDS[*]}"; [ "${#FIXTURE_PIDS[@]}" -ge 4 ]; cleanup_fixtures; [ "${#FIXTURE_PIDS[@]}" -eq 0 ]; for p in $p1 $p2; do case "$p" in ''|*[!0-9]*) continue ;; esac; kill -0 "$p" 2>/dev/null && return 1 || true; done; }

# ── Singleton validation: Lock ────────────────────────────────────────────

@test "accepts valid Chromium-style singleton artifacts" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "rejects regular file as SingletonLock" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonLock"; touch "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonLock with no PID" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; ln -sf "justahostname" "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonLock with PID 0" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; ln -sf "host-0" "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonLock with non-numeric PID" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; ln -sf "host-abc" "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonLock with nonexistent PID" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; ln -sf "host-999999999" "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects missing SingletonLock" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "accepts SingletonLock with multi-hyphen hostname" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; local p="${FIXTURE_PIDS[0]}"; ln -sf "my-machine-name-$p" "$SUSHIDA_OS_RUNTIME/chromium/SingletonLock"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── Singleton validation: Socket ──────────────────────────────────────────

@test "rejects missing SingletonSocket" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonSocket"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonSocket as regular file" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonSocket"; touch "$d/SingletonSocket"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects SingletonSocket symlink to regular file" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonSocket"; echo x > "$d/reg"; ln -sf "$d/reg" "$d/SingletonSocket"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects broken SingletonSocket symlink" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonSocket"; ln -sf "/nonexistent/path" "$d/SingletonSocket"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }

# ── Singleton validation: Cookie ──────────────────────────────────────────

@test "rejects missing profile SingletonCookie" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonCookie"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects profile SingletonCookie as regular file" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonCookie"; touch "$d/SingletonCookie"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects missing remote SingletonCookie" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; local st; st=$(readlink "$d/SingletonSocket"); rm -f "$(dirname "$st")/SingletonCookie"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects remote SingletonCookie as regular file" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; local st; st=$(readlink "$d/SingletonSocket"); rm -f "$(dirname "$st")/SingletonCookie"; touch "$(dirname "$st")/SingletonCookie"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects cookie mismatch" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonCookie"; ln -sf "WRONG_COOKIE" "$d/SingletonCookie"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects empty profile SingletonCookie" { reset_run; local d="$SUSHIDA_OS_RUNTIME/chromium"; mkdir -p "$d"; setup_singleton_fixtures "$d"; rm -f "$d/SingletonCookie"; ln -sf "" "$d/SingletonCookie" 2>/dev/null || :; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }

# ── Static: UID comparison ────────────────────────────────────────────────

@test "watcher validates SingletonLock UID (source check)" { grep -qE "stat -c.*%u.*/proc" "$WATCHER"; }
@test "watcher validates SingletonLock PID is positive integer (source check)" { grep -qE '\$pid.*\-gt\s*0' "$WATCHER"; }

# ── Timeout command precondition ──────────────────────────────────────────

@test "does not navigate when timeout command fails" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; echo '#!/bin/bash; exit 1' > "$TEST_ROOT/bin/timeout"; chmod +x "$TEST_ROOT/bin/timeout"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }

# ── Sleep after nav failure ───────────────────────────────────────────────

@test "navigation failure still sleeps minimum interval" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; echo '#!/bin/bash; echo "$@" >> "${SUSHIDA_OS_CHROMIUM_LOG:-/dev/null}"; exit 1' > "$TEST_ROOT/bin/chromium"; chmod +x "$TEST_ROOT/bin/chromium"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "30" "$SUSHIDA_OS_SLEEP_LOG"; }

# ── State file ────────────────────────────────────────────────────────────

@test "handles unknown state file content" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; echo "BOGUS_STATE" > "$SUSHIDA_OS_RUNTIME/network-state"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── NAV_TIMEOUT validation ────────────────────────────────────────────────

@test "rejects NAV_TIMEOUT override in production" { unset SUSHIDA_OS_TEST_MODE; export SUSHIDA_OS_NAV_TIMEOUT=5; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"TEST_MODE"* ]]; }
@test "rejects NAV_TIMEOUT empty" { export SUSHIDA_OS_NAV_TIMEOUT=""; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "rejects NAV_TIMEOUT non-integer" { export SUSHIDA_OS_NAV_TIMEOUT=abc; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "rejects NAV_TIMEOUT negative" { export SUSHIDA_OS_NAV_TIMEOUT=-5; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }
@test "accepts NAV_TIMEOUT=1 in test mode" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_NAV_TIMEOUT=1; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── No external requests ──────────────────────────────────────────────────

@test "watcher does not call curl wget or ping" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; for c in curl wget ping dig nslookup traceroute nc ncat; do echo '#!/bin/bash; echo "ERROR: $0 called" >&2; exit 1' > "$TEST_ROOT/bin/$c"; chmod +x "$TEST_ROOT/bin/$c"; done; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; }

# ── URL validation ─────────────────────────────────────────────────────────

# Helper for rejected URL tests: verify status, disallowed message,
# and that chromium was never invoked.
reject_url() { putconf "$1"; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"disallowed"* ]]; [ ! -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; }
@test "rejects arbitrary origin" { reject_url 'SUSHIDA_URL=https://evil.com/play.html'; }
@test "rejects subdomain trick" { reject_url 'SUSHIDA_URL=https://sushida.net.evil.example/play.html'; }
@test "rejects userinfo prefix" { reject_url 'SUSHIDA_URL=https://user:pass@sushida.net/play.html'; }
@test "rejects alternate port" { reject_url 'SUSHIDA_URL=https://sushida.net:8080/play.html'; }
@test "rejects http scheme" { reject_url 'SUSHIDA_URL=http://sushida.net/play.html'; }
@test "rejects file scheme" { reject_url 'SUSHIDA_URL=file:///usr/share/sushida-os/offline.html'; }
@test "rejects javascript scheme" { reject_url 'SUSHIDA_URL=javascript:alert(1)'; }
@test "rejects data scheme" { reject_url 'SUSHIDA_URL=data:text/html,<script>alert(1)</script>'; }

# ── Positive URL tests ───────────────────────────────────────────────────

@test "accepts bare domain" { putconf 'SUSHIDA_URL=https://sushida.net'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; }
@test "accepts domain with slash" { putconf 'SUSHIDA_URL=https://sushida.net/'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; }
@test "accepts subpath" { putconf 'SUSHIDA_URL=https://sushida.net/play.html'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; }
@test "accepts URL with query params" { putconf 'SUSHIDA_URL=https://sushida.net/path?key=value&other=value'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; }

# ── Command injection ─────────────────────────────────────────────────────

@test "does not evaluate command substitution in URL" { putconf 'SUSHIDA_URL=https://sushida.net/$(echo injected)'; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; run "$WATCHER"; run "$WATCHER"; export SUSHIDA_OS_TEST_NM_STATE=connected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF '$(echo injected)' "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "does not evaluate backtick in URL" { putconf 'SUSHIDA_URL=https://sushida.net/'"'"'`echo injected`'"'"''; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; run "$WATCHER"; run "$WATCHER"; export SUSHIDA_OS_TEST_NM_STATE=connected; > "$SUSHIDA_OS_CHROMIUM_LOG"; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF '`echo injected`' "$SUSHIDA_OS_CHROMIUM_LOG"; }
@test "does not evaluate semicolon" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=30; echo injected'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"positive integer"* ]]; }

# ── Config file errors ────────────────────────────────────────────────────

@test "rejects unknown config key" { putconf 'UNKNOWN_KEY=value' 'SUSHIDA_URL=https://sushida.net/play.html'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"Unknown"* ]]; }
@test "rejects duplicate SUSHIDA_URL" { putconf 'SUSHIDA_URL=https://sushida.net/1' 'SUSHIDA_URL=https://sushida.net/2'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"Duplicate"* ]]; }
@test "rejects duplicate NETWORK_CHECK_INTERVAL_SECONDS" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'NETWORK_CHECK_INTERVAL_SECONDS=30' 'NETWORK_CHECK_INTERVAL_SECONDS=60'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"Duplicate"* ]]; }
@test "rejects missing SUSHIDA_URL" { putconf 'NETWORK_CHECK_INTERVAL_SECONDS=30'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"not set"* ]]; }
@test "rejects missing config file" { export SUSHIDA_OS_CONFIG="$TEST_ROOT/nonexistent.env"; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"not found"* ]]; }
@test "rejects invalid line (missing equals)" { putconf 'SUSHIDA_URL=https://sushida.net/play.html' 'BOGUS_LINE_WITHOUT_EQUALS'; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"missing '='"* ]]; }

# ── Offline URL is fixed ──────────────────────────────────────────────────

@test "offline URL is hardcoded" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; run grep -cF "file://" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$output" = "1" ]; }

# ── Test mode guard ───────────────────────────────────────────────────────

@test "rejects config override without TEST_MODE" { unset SUSHIDA_OS_TEST_MODE; export SUSHIDA_OS_CONFIG="$TEST_ROOT/override.env"; touch "$TEST_ROOT/override.env"; echo 'SUSHIDA_URL=https://sushida.net/play.html' > "$TEST_ROOT/override.env"; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"TEST_MODE"* ]]; }
@test "rejects runtime override without TEST_MODE" { unset SUSHIDA_OS_TEST_MODE; export SUSHIDA_OS_RUNTIME="$TEST_ROOT/other-run"; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"TEST_MODE"* ]]; }
@test "rejects max iter override without TEST_MODE" { unset SUSHIDA_OS_TEST_MODE; export SUSHIDA_OS_MAX_ITERATIONS=1; run "$WATCHER"; [ "$status" -ne 0 ]; [[ "$output" == *"TEST_MODE"* ]]; }

# ── Navigation target constraint ──────────────────────────────────────────

@test "only offline URL and official URL are navigated to" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "file:///usr/share/sushida-os/offline.html" "$SUSHIDA_OS_CHROMIUM_LOG"; reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; run "$WATCHER"; run "$WATCHER"; > "$SUSHIDA_OS_CHROMIUM_LOG"; export SUSHIDA_OS_TEST_NM_STATE=connected; run "$WATCHER"; [ "$status" -eq 0 ]; grep -qF "https://sushida.net/play.html" "$SUSHIDA_OS_CHROMIUM_LOG"; }

# ── Forbidden flags ───────────────────────────────────────────────────────
@test "forbidden Chromium flags absent from argv log" { reset_run; setup_singleton_fixtures "$SUSHIDA_OS_RUNTIME/chromium"; export SUSHIDA_OS_TEST_NM_STATE=disconnected; run "$WATCHER"; [ "$status" -eq 0 ]; if [ -s "$SUSHIDA_OS_CHROMIUM_LOG" ]; then for f in --no-sandbox --disable-gpu --disable-webgl --remote-debugging --new-window --new-tab; do run grep -qF -- "$f" "$SUSHIDA_OS_CHROMIUM_LOG"; [ "$status" -ne 0 ]; done; fi; run grep -cE '\-\-no\-sandbox|\-\-disable\-gpu|\-\-disable\-webgl|\-\-remote\-debugging|\-\-new\-window|\-\-new\-tab' "$WATCHER"; [ "$output" -eq 0 ]; }

@test "watcher script is executable" { [ -x "$WATCHER" ]; }
@test "no external connectivity commands" { run grep -cE '\b(curl|wget|ping|dig|nslookup|traceroute|nc|ncat)\b' "$WATCHER"; [ "$output" -eq 0 ]; }

# ── Systemd unit ──────────────────────────────────────────────────────────
@test "unit ExecStart" { run grep 'ExecStart=' "$SERVICE_UNIT"; [[ "$output" == *"/usr/local/bin/sushida-network-watch"* ]]; }
@test "unit runs as kiosk" { run grep 'User=kiosk' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; run grep 'Group=kiosk' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
@test "unit NoNewPrivileges" { run grep 'NoNewPrivileges=true' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
@test "unit empty caps" { run grep 'CapabilityBoundingSet=$' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; run grep 'AmbientCapabilities=$' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
@test "unit deps" { run grep 'After=NetworkManager.service sushida-kiosk.service' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; run grep 'Wants=NetworkManager.service' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
@test "unit no root" { run grep -i 'User=root' "$SERVICE_UNIT"; [ "$status" -ne 0 ]; }
@test "unit no sudo" { run grep -i 'sudo\|SUDO\|ExecStart.*sudo' "$SERVICE_UNIT"; [ "$status" -ne 0 ]; }
@test "unit PartOf" { run grep 'PartOf=sushida-kiosk.service' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
@test "unit no extra caps" { run grep -i 'CapabilityBoundingSet=[^ ]' "$SERVICE_UNIT"; [ "$status" -ne 0 ]; }
@test "unit Install alone does not enable" { run grep 'WantedBy=multi-user.target' "$SERVICE_UNIT"; [ "$status" -eq 0 ]; }
