#!/usr/bin/env bats
# Tests for the development tooling wrappers (doctor.sh, container-run.sh).

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/dev-tools"
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home"
    export PATH="$TEST_ROOT/bin:$PATH"
    export CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
    export HOME="$TEST_ROOT/home"
    # Determine repository root from the test file location
    REPO_ROOT=$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd -P) || true
}

# ── container-run.sh ─────────────────────────────────────────────────────

@test "container-run.sh requires a mode argument" {
    run "$REPO_ROOT/scripts/container-run.sh"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "container-run.sh rejects unknown mode" {
    run "$REPO_ROOT/scripts/container-run.sh" unknown
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown mode"* ]]
}

@test "container-run.sh has --cgroup-manager=cgroupfs for podman" {
    run grep -c '--cgroup-manager=cgroupfs' "$REPO_ROOT/scripts/container-run.sh"
    [ "$status" -eq 0 ]
    [ "$output" -ge 1 ]
}

@test "container-run.sh mode iso has --privileged" {
    run grep -c 'PRIVILEGED.*true\|--privileged' "$REPO_ROOT/scripts/container-run.sh"
    [ "$status" -eq 0 ]
    [ "$output" -ge 1 ]
}

# ── doctor.sh ────────────────────────────────────────────────────────────

@test "doctor.sh test profile passes when tools are present" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"repository_root=PASS"* ]]
}

@test "doctor.sh rejects unknown profile" {
    run "$REPO_ROOT/scripts/doctor.sh" unknown
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown profile"* ]]
}

@test "doctor.sh does not modify the repository workspace" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    git -C "$REPO_ROOT" status --porcelain
}

@test "doctor.sh output format contains expected NAME=VALUE patterns" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"=PASS"* ]] || [[ "$output" == *"=FAIL"* ]] || [[ "$output" == *"=WARN"* ]]
}
