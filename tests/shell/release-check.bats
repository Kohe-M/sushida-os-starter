#!/usr/bin/env bats
# Tests for scripts/release-check.sh with a fake container engine.

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/release-check"
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/out"
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd -P)"
    export PATH="$TEST_ROOT/bin:$PATH"
    export CONTAINER_ENGINE=docker
    export SUSHIDA_RELEASE_CHECK_DIR="$TEST_ROOT/out"
    export CALLS="$TEST_ROOT/calls"
    export GIT_CONFIG_COUNT=1
    export GIT_CONFIG_KEY_0=safe.directory
    export GIT_CONFIG_VALUE_0="$REPO_ROOT"
    FAKE_BUILDER_HASH="$("$REPO_ROOT/scripts/builder-hash.sh")"
    export FAKE_BUILDER_HASH
    : > "$CALLS"

    # Fake engine: records each make target, prints assessor lines for QEMU
    # targets (FAKE_QEMU_RESULT, or nothing when FAKE_QEMU_SILENT=1), and
    # fails the target named by FAKE_FAIL_TARGET.
    cat > "$TEST_ROOT/bin/docker" <<'FAKE'
#!/usr/bin/env bash
set -eu
case "$1" in
    image) printf '%s\n' "$FAKE_BUILDER_HASH"; exit 0 ;;
esac
target="${!#}"
printf '%s\n' "$target" >> "$CALLS"
case "$target" in
    test-qemu-*)
        if [ "${FAKE_QEMU_SILENT:-0}" != 1 ]; then
            printf 'AUTOMATED: fixture check: %s\n' "${FAKE_QEMU_RESULT:-PASS}"
        fi
        ;;
esac
[ "$target" != "${FAKE_FAIL_TARGET:-}" ] || exit 3
exit 0
FAKE
    chmod +x "$TEST_ROOT/bin/docker"
}

run_check() { run "$REPO_ROOT/scripts/release-check.sh"; }

@test "runs iso, verify, boot, smoke in order and passes" {
    run_check
    [ "$status" -eq 0 ]
    [ "$(tr '\n' ' ' < "$CALLS")" = "iso verify test-qemu-boot test-qemu-runtime " ]
    grep -qx 'result=PASS' "$TEST_ROOT/out/summary.txt"
    grep -qx 'head_stable=yes' "$TEST_ROOT/out/summary.txt"
    grep -q '^step qemu-smoke=PASS (exit 0, AUTOMATED 1 PASS / 0 FAIL)$' "$TEST_ROOT/out/summary.txt"
    grep -q "^git_head=$(git -C "$REPO_ROOT" rev-parse HEAD)\$" "$TEST_ROOT/out/summary.txt"
}

@test "stops at the first failing step and skips the rest" {
    FAKE_FAIL_TARGET=verify run_check
    [ "$status" -ne 0 ]
    [ "$(tr '\n' ' ' < "$CALLS")" = "iso verify " ]
    grep -qx 'step verify=FAIL (exit 3)' "$TEST_ROOT/out/summary.txt"
    grep -qx 'step qemu-boot=SKIPPED' "$TEST_ROOT/out/summary.txt"
    grep -qx 'result=FAIL' "$TEST_ROOT/out/summary.txt"
}

@test "a QEMU assessor FAIL line fails the step even with exit 0" {
    FAKE_QEMU_RESULT=FAIL run_check
    [ "$status" -ne 0 ]
    grep -qx 'step qemu-boot=FAIL (exit 0, AUTOMATED 0 PASS / 1 FAIL)' "$TEST_ROOT/out/summary.txt"
}

@test "a QEMU step without assessor evidence is not a pass" {
    FAKE_QEMU_SILENT=1 run_check
    [ "$status" -ne 0 ]
    grep -qx 'step qemu-boot=FAIL (exit 0, AUTOMATED 0 PASS / 0 FAIL)' "$TEST_ROOT/out/summary.txt"
}

@test "each step keeps its own full log" {
    run_check
    [ "$status" -eq 0 ]
    for step in iso verify qemu-boot qemu-smoke; do
        [ -f "$TEST_ROOT/out/$step.log" ]
    done
    grep -q 'AUTOMATED: fixture check: PASS' "$TEST_ROOT/out/qemu-smoke.log"
}

@test "refuses a symlinked output directory" {
    ln -s "$TEST_ROOT/out" "$TEST_ROOT/link"
    SUSHIDA_RELEASE_CHECK_DIR="$TEST_ROOT/link" run_check
    [ "$status" -ne 0 ]
    [[ "$output" == *"symlinked"* ]]
    [ ! -s "$CALLS" ]
}
