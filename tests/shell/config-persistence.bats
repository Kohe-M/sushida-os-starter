#!/usr/bin/env bats

setup() {
    export TEST_ROOT="$BATS_TEST_TMPDIR/config-persistence"
    mkdir -p "$TEST_ROOT/config"
    export SUSHIDA_CONFIG_TEST_MODE=1
    export SUSHIDA_CONFIG_TEST_ROOT="$TEST_ROOT"
    PREPARE="live-build/config/includes.chroot/usr/local/libexec/sushida-config-prepare"
}

@test "missing config mount is a nonfatal unavailable state" {
    run "$PREPARE"
    [ "$status" -eq 0 ]
    [ "$(< "$TEST_ROOT/run/config-storage")" = unavailable ]
    [ ! -e "$TEST_ROOT/config/network" ]
}

@test "non-ext4 config mount is refused without preparing writable state" {
    export SUSHIDA_CONFIG_TEST_MOUNTED=1
    export SUSHIDA_CONFIG_TEST_FSTYPE=vfat
    run "$PREPARE"
    [ "$status" -eq 0 ]
    [ "$(< "$TEST_ROOT/run/config-storage")" = unavailable ]
    [ ! -e "$TEST_ROOT/config/network" ]
}

@test "ext4 config mount creates only private network state" {
    export SUSHIDA_CONFIG_TEST_MOUNTED=1
    export SUSHIDA_CONFIG_TEST_FSTYPE=ext4
    run "$PREPARE"
    [ "$status" -eq 0 ]
    [ "$(< "$TEST_ROOT/run/config-storage")" = ready ]
    [ "$(stat -c %a "$TEST_ROOT/config/network")" = 700 ]
}

@test "status update replaces a symlink without modifying its target" {
    outside="$TEST_ROOT/outside"
    printf '%s\n' sentinel > "$outside"
    mkdir -p "$TEST_ROOT/run"
    ln -s "$outside" "$TEST_ROOT/run/config-storage"

    run "$PREPARE"
    [ "$status" -eq 0 ]
    [ ! -L "$TEST_ROOT/run/config-storage" ]
    [ "$(< "$TEST_ROOT/run/config-storage")" = unavailable ]
    [ "$(< "$outside")" = sentinel ]
}

@test "symlinked persistent network directory is refused without following it" {
    outside="$TEST_ROOT/outside-directory"
    mkdir "$outside"
    chmod 0755 "$outside"
    ln -s "$outside" "$TEST_ROOT/config/network"
    export SUSHIDA_CONFIG_TEST_MOUNTED=1
    export SUSHIDA_CONFIG_TEST_FSTYPE=ext4

    run "$PREPARE"
    [ "$status" -eq 0 ]
    [ "$(< "$TEST_ROOT/run/config-storage")" = unavailable ]
    [ -L "$TEST_ROOT/config/network" ]
    [ "$(stat -c %a "$outside")" = 755 ]
}

@test "test path override is rejected outside test mode" {
    unset SUSHIDA_CONFIG_TEST_MODE
    run "$PREPARE"
    [ "$status" -ne 0 ]
    [[ "$output" == *"requires test mode"* ]]
}

@test "test root must stay below tmp" {
    export SUSHIDA_CONFIG_TEST_ROOT=/var/lib/sushida-config-test
    run "$PREPARE"
    [ "$status" -ne 0 ]
    [[ "$output" == *"unsafe config test root"* ]]
}
