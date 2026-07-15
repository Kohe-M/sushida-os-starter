#!/usr/bin/env bats

setup() {
    DIAGNOSTICS="live-build/config/includes.chroot/usr/local/bin/sushida-diagnostics"
    REPORT="$BATS_TEST_TMPDIR/diagnostics.txt"
}

@test "diagnostics writes a private report to an explicit path" {
    WIFI_PSK="do-not-record-this-secret" run "$DIAGNOSTICS" --output "$REPORT"
    [ "$status" -eq 0 ]
    [ -s "$REPORT" ]
    [ "$(stat -c %a "$REPORT")" = "600" ]
    grep -q '^SUSHIDA_OS_DIAGNOSTICS_VERSION=1$' "$REPORT"
    grep -q '^## DRM and graphics$' "$REPORT"
    grep -q '^## Audio$' "$REPORT"
    grep -q '^## NetworkManager$' "$REPORT"
    run grep -q 'do-not-record-this-secret' "$REPORT"
    [ "$status" -ne 0 ]
}

@test "diagnostics refuses to overwrite an existing report" {
    echo existing > "$REPORT"
    run "$DIAGNOSTICS" --output "$REPORT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
    [ "$(cat "$REPORT")" = "existing" ]
}

@test "diagnostics rejects a relative output path" {
    run "$DIAGNOSTICS" --output relative.txt
    [ "$status" -ne 0 ]
    [[ "$output" == *"absolute"* ]]
}

@test "diagnostics rejects a symlinked output directory" {
    mkdir "$BATS_TEST_TMPDIR/real"
    ln -s "$BATS_TEST_TMPDIR/real" "$BATS_TEST_TMPDIR/link"
    run "$DIAGNOSTICS" --output "$BATS_TEST_TMPDIR/link/report.txt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"unsafe"* ]]
}
