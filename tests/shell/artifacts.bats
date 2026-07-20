#!/usr/bin/env bats

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/repository"
    mkdir -p "$TEST_ROOT/scripts/lib" "$TEST_ROOT/build" "$TEST_ROOT/artifacts" "$TEST_ROOT/local"
    cp scripts/clean.sh scripts/verify-iso.sh "$TEST_ROOT/scripts/"
    cp scripts/lib/iso-extract.sh "$TEST_ROOT/scripts/lib/"
    chmod 0755 "$TEST_ROOT/scripts/clean.sh" "$TEST_ROOT/scripts/verify-iso.sh"
    touch "$TEST_ROOT/build/.gitkeep" "$TEST_ROOT/artifacts/.gitkeep"
    echo secret > "$TEST_ROOT/local/wifi.nmconnection"
}

@test "clean removes disposable build state but preserves artifacts and source" {
    mkdir -p "$TEST_ROOT/build/live-build" "$TEST_ROOT/build/qemu" "$TEST_ROOT/build/verify-artifacts.1"
    echo iso > "$TEST_ROOT/artifacts/sushida-os-amd64.iso"
    echo keep > "$TEST_ROOT/artifacts/keep.txt"
    run "$TEST_ROOT/scripts/clean.sh" clean
    [ "$status" -eq 0 ]
    [ ! -e "$TEST_ROOT/build/live-build" ]
    [ ! -e "$TEST_ROOT/build/qemu" ]
    [ ! -e "$TEST_ROOT/build/verify-artifacts.1" ]
    [ -f "$TEST_ROOT/artifacts/sushida-os-amd64.iso" ]
    [ -f "$TEST_ROOT/artifacts/keep.txt" ]
    [ -f "$TEST_ROOT/local/wifi.nmconnection" ]
}

@test "distclean removes only the four known artifacts" {
    for file in sushida-os-amd64.iso SHA256SUMS package-manifest.txt build-info.json; do
        echo generated > "$TEST_ROOT/artifacts/$file"
    done
    echo keep > "$TEST_ROOT/artifacts/keep.txt"
    mkdir "$TEST_ROOT/artifacts/.build-staging.1"
    run "$TEST_ROOT/scripts/clean.sh" distclean
    [ "$status" -eq 0 ]
    for file in sushida-os-amd64.iso SHA256SUMS package-manifest.txt build-info.json; do
        [ ! -e "$TEST_ROOT/artifacts/$file" ]
    done
    [ ! -e "$TEST_ROOT/artifacts/.build-staging.1" ]
    [ -f "$TEST_ROOT/artifacts/.gitkeep" ]
    [ -f "$TEST_ROOT/artifacts/keep.txt" ]
    [ -f "$TEST_ROOT/local/wifi.nmconnection" ]
}

@test "cleanup rejects a symlinked build root" {
    rm "$TEST_ROOT/build/.gitkeep"
    rmdir "$TEST_ROOT/build"
    ln -s /tmp "$TEST_ROOT/build"
    run "$TEST_ROOT/scripts/clean.sh" clean
    [ "$status" -ne 0 ]
    [[ "$output" == *"symlinked"* ]]
}

@test "cleanup rejects unknown mode" {
    run "$TEST_ROOT/scripts/clean.sh" everything
    [ "$status" -ne 0 ]
    [[ "$output" == *"usage"* ]]
}

@test "verifier rejects artifact directory outside repository" {
    run "$TEST_ROOT/scripts/verify-iso.sh" /tmp
    [ "$status" -ne 0 ]
    [[ "$output" == *"outside"* || "$output" == *"invalid artifact"* ]]
}

@test "verifier rejects a missing artifact set" {
    mkdir -p "$TEST_ROOT/bin"
    for command in xorriso unsquashfs; do
        printf '#!/bin/sh\nexit 1\n' > "$TEST_ROOT/bin/$command"
        chmod 0755 "$TEST_ROOT/bin/$command"
    done
    PATH="$TEST_ROOT/bin:$PATH" run "$TEST_ROOT/scripts/verify-iso.sh"
    [ "$status" -ne 0 ]
    [[ "$output" == *"missing, empty, or unsafe artifact"* ]]
}
