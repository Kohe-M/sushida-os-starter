#!/usr/bin/env bats

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/flash-root"
    mkdir "$TEST_ROOT"
    IMAGE="$TEST_ROOT/test.iso"
    CHECKSUMS="$TEST_ROOT/SHA256SUMS"
    TARGET="$TEST_ROOT/target-device"
    SYSTEM_DISK="$TEST_ROOT/system-device"
    printf 'safe test image\n' > "$IMAGE"
    printf 'old target data\n' > "$TARGET"
    printf 'system data\n' > "$SYSTEM_DISK"
    (
        cd "$TEST_ROOT" || exit
        sha256sum test.iso > SHA256SUMS
    )
    export SUSHIDA_OS_FLASH_TEST_MODE=1
    export SUSHIDA_OS_FLASH_TEST_ROOT="$TEST_ROOT"
    export SUSHIDA_OS_FLASH_TEST_IMAGE="$IMAGE"
    export SUSHIDA_OS_FLASH_TEST_CHECKSUMS="$CHECKSUMS"
    export SUSHIDA_OS_FLASH_TEST_SYSTEM_DISK="$SYSTEM_DISK"
    export FLASH="scripts/flash.sh"
    export TARGET SYSTEM_DISK
}

@test "flash requires an explicit target" {
    run "$FLASH" --yes
    [ "$status" -ne 0 ]
    [[ "$output" == *"explicit target"* ]]
}

@test "--yes cannot bypass system disk protection" {
    run bash -c 'printf "WRITE %s\n" "$SYSTEM_DISK" | "$FLASH" --yes "$SYSTEM_DISK"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"current system disk"* ]]
    [ "$(cat "$SYSTEM_DISK")" = "system data" ]
}

@test "wrong final confirmation leaves target unchanged" {
    run bash -c 'printf "WRONG\n" | "$FLASH" --yes "$TARGET"'
    [ "$status" -ne 0 ]
    [[ "$output" == *"did not match"* ]]
    [ "$(cat "$TARGET")" = "old target data" ]
}

@test "confirmed test-mode write verifies exact regular-file fixture" {
    run bash -c 'printf "WRITE %s\n" "$TARGET" | "$FLASH" --yes "$TARGET"'
    [ "$status" -eq 0 ]
    [[ "$output" == *"SHA-256 verification passed"* ]]
    cmp "$IMAGE" "$TARGET"
}

@test "test mode rejects target outside its isolated root" {
    outside="$BATS_TEST_TMPDIR/outside"
    printf outside > "$outside"
    run "$FLASH" --yes "$outside"
    [ "$status" -ne 0 ]
    [[ "$output" == *"outside test root"* ]]
}

@test "source checksum mismatch fails before confirmation or write" {
    printf tampered >> "$IMAGE"
    run "$FLASH" --yes "$TARGET"
    [ "$status" -ne 0 ]
    [[ "$output" == *"checksum mismatch"* ]]
    [ "$(cat "$TARGET")" = "old target data" ]
}
