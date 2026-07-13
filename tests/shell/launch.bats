#!/usr/bin/env bats
#
# BATS tests for sushida-launch -- uses stubs, never runs real Cage/Chromium.

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/launch-test"
    mkdir -p "$TEST_ROOT"
    export PATH="$TEST_ROOT/bin:$PATH"
    export SUSHIDA_OS_TEST_MODE=1
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/config.env"
    export SUSHIDA_OS_RUNTIME="$TEST_ROOT/run"
    mkdir -p "$TEST_ROOT/run/home"
    mkdir -p "$TEST_ROOT/bin"

    cat > "$TEST_ROOT/bin/id" <<'SHIM'
#!/bin/bash
echo "kiosk"
SHIM
    chmod +x "$TEST_ROOT/bin/id"

    cat > "$TEST_ROOT/bin/cage" <<'SHIM'
#!/bin/bash
echo "CAGE_SPLIT:" >&2
for arg in "$@"; do echo "  [$arg]" >&2; done
while [ $# -gt 0 ]; do case "$1" in --) shift; break ;; *) shift ;; esac; done
exec "$@"
SHIM
    chmod +x "$TEST_ROOT/bin/cage"

    cat > "$TEST_ROOT/bin/chromium" <<'SHIM'
#!/bin/bash
for arg in "$@"; do echo "ARG:[$arg]"; done
SHIM
    chmod +x "$TEST_ROOT/bin/chromium"

    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net/play.html
NETWORK_CHECK_INTERVAL_SECONDS=30
KIOSK_RESTART_SECONDS=2
CONFIG
}

LAUNCHER="live-build/config/includes.chroot/usr/local/bin/sushida-launch"


# ── happy path ─────────────────────────────────────────────────────────────


@test "cage is invoked with chromium and valid URL" {
    run "$LAUNCHER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARG:[--kiosk]"* ]]
    [[ "$output" == *"ARG:[--no-first-run]"* ]]
}


@test "SUSHIDA_URL is the last chromium argument" {
    run "$LAUNCHER"
    last_arg="$(echo "$output" | grep -E '^ARG:' | tail -1)"
    [ "$last_arg" = "ARG:[https://sushida.net/play.html]" ]
}


@test "preserves = and & in URL" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net/?foo=bar&baz=qux
CONFIG
    run "$LAUNCHER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARG:[https://sushida.net/?foo=bar&baz=qux]"* ]]
}


@test "does not evaluate command substitution" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net/$(id)
CONFIG
    run "$LAUNCHER"
    [ "$status" -eq 0 ]
    # The literal string $(id) must appear, not the result of running id
    [[ "$output" == *'$(id)'* ]]
}


# ── origin / scheme rejection ──────────────────────────────────────────────


@test "rejects arbitrary origin" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://evil.com/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects subdomain-of-sushida trick" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net.evil.example/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects userinfo prefix" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://user:pass@sushida.net/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects alternate port" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net:8080/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects http scheme" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=http://sushida.net/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects file scheme" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=file:///usr/share/sushida-os/offline.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects javascript scheme" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=javascript:alert(1)
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


@test "rejects data scheme" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=data:text/html,<script>alert(1)</script>
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"disallowed"* ]]
}


# ── user rejection ──────────────────────────────────────────────────────────


@test "rejects non-kiosk user" {
    cat > "$TEST_ROOT/bin/id" <<'SHIM'
#!/bin/bash
echo "root"
SHIM
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"kiosk"* ]]
}


# ── config errors ───────────────────────────────────────────────────────────


@test "rejects unknown config key" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
UNKNOWN_KEY=value
SUSHIDA_URL=https://sushida.net/play.html
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Unknown"* ]]
}


@test "rejects duplicate SUSHIDA_URL" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
SUSHIDA_URL=https://sushida.net/1
SUSHIDA_URL=https://sushida.net/2
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Duplicate"* ]]
}


@test "rejects missing SUSHIDA_URL" {
    cat > "$SUSHIDA_OS_CONFIG" <<'CONFIG'
NETWORK_CHECK_INTERVAL_SECONDS=30
CONFIG
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not set"* ]]
}


@test "rejects missing config file" {
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/nonexistent.env"
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not found"* ]]
}


# ── cage argv ────────────────────────────────────────────────────────────────


@test "cage argv: -- then chromium" {
    run "$LAUNCHER"
    [ "$status" -eq 0 ]
    # Cage stub output (stderr) is merged into $output
    [[ "$output" == *"[--]"* ]]
    [[ "$output" == *"[chromium]"* ]]
    # Chromium stub output contains the URL as the last ARG
    [[ "$output" == *"ARG:[https://sushida.net/play.html]"* ]]
}


# ── test mode guard ─────────────────────────────────────────────────────────


@test "rejects config override without SUSHIDA_OS_TEST_MODE" {
    unset SUSHIDA_OS_TEST_MODE
    export SUSHIDA_OS_CONFIG="$TEST_ROOT/override.env"
    touch "$TEST_ROOT/override.env"
    echo 'SUSHIDA_URL=https://sushida.net/play.html' > "$TEST_ROOT/override.env"
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"TEST_MODE"* ]]
}


@test "rejects runtime override without SUSHIDA_OS_TEST_MODE" {
    unset SUSHIDA_OS_TEST_MODE
    export SUSHIDA_OS_RUNTIME="$TEST_ROOT/other-run"
    run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"TEST_MODE"* ]]
}


# ── runtime directories ─────────────────────────────────────────────────────


@test "creates runtime directories with 0700 mode" {
    run "$LAUNCHER"
    for d in chromium cache tmp downloads xdg-runtime; do
        dir="$SUSHIDA_OS_RUNTIME/$d"
        [ -d "$dir" ]
        mode="$(stat -c '%a' "$dir")"
        [ "$mode" = "700" ] || [ "$mode" = "0700" ]
    done
}


# ── executable pre-check ────────────────────────────────────────────────────


@test "reports missing cage" {
    # Isolated PATH with neither cage nor chromium
    missing_bin="$TEST_ROOT/missing-bin"
    mkdir -p "$missing_bin"
    ln -sf "$(command -v bash)" "$missing_bin/bash"
    ln -sf "$(command -v env)" "$missing_bin/env"
    # id stub for user check
    cat > "$missing_bin/id" <<'SHIM'
#!/bin/bash
echo "kiosk"
SHIM
    chmod +x "$missing_bin/id"
    PATH="$missing_bin" run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"cage not found"* ]]
}


@test "reports missing chromium" {
    missing_bin="$TEST_ROOT/missing-bin"
    rm -rf "$missing_bin"
    mkdir -p "$missing_bin"
    ln -sf "$(command -v bash)" "$missing_bin/bash"
    ln -sf "$(command -v env)" "$missing_bin/env"
    cat > "$missing_bin/id" <<'SHIM'
#!/bin/bash
echo "kiosk"
SHIM
    chmod +x "$missing_bin/id"
    # Provide cage stub but no chromium stub
    cp "$TEST_ROOT/bin/cage" "$missing_bin/cage"
    PATH="$missing_bin" run "$LAUNCHER"
    [ "$status" -ne 0 ]
    [[ "$output" == *"chromium not found"* ]]
}


# ── forbidden flags ─────────────────────────────────────────────────────────


@test "forbidden Chromium flags are absent" {
    run "$LAUNCHER"
    [[ "$output" != *"--no-sandbox"* ]]
    [[ "$output" != *"--disable-gpu"* ]]
    [[ "$output" != *"--disable-webgl"* ]]
    # Any flag starting with --remote-debugging is forbidden
    [[ "$output" != *"--remote-debugging"* ]]
}
