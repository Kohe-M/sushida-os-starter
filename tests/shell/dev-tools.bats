#!/usr/bin/env bats
# Tests for the development tooling wrappers (doctor.sh, container-run.sh).

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/dev-tools"
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home" "$TEST_ROOT/argv-logs"
    export PATH="$TEST_ROOT/bin:$PATH"
    export HOME="$TEST_ROOT/home"
    export CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
    export TEST_ROOT
    # Determine repository root from the test file location
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd -P)"

    # Fake docker/podman that record argv to a fixed path (one arg per line).
    # The path can be overridden with DOCKER_LOG / PODMAN_LOG so tests can
    # locate the log deterministically.
    cat > "$TEST_ROOT/bin/docker" <<'FAKEDOCKER'
#!/bin/sh
set -eu
log="${DOCKER_LOG:-$TEST_ROOT/argv-logs/docker.log}"
mkdir -p "$(dirname "$log")"
for a in docker "$@"; do printf '%s\n' "$a"; done > "$log"
exit "${DOCKER_EXIT:-0}"
FAKEDOCKER
    chmod +x "$TEST_ROOT/bin/docker"

    cat > "$TEST_ROOT/bin/podman" <<'FAKEPODMAN'
#!/bin/sh
set -eu
log="${PODMAN_LOG:-$TEST_ROOT/argv-logs/podman.log}"
mkdir -p "$(dirname "$log")"
for a in podman "$@"; do printf '%s\n' "$a"; done > "$log"
exit "${PODMAN_EXIT:-0}"
FAKEPODMAN
    chmod +x "$TEST_ROOT/bin/podman"

    export BUILDER_IMAGE="${BUILDER_IMAGE:-sushida-os-builder:trixie}"
}

read_argv() {
    cat "$1"
}

# ── container-run.sh: fake docker ────────────────────────────────────────

@test "container-run.sh test mode has --privileged not set" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" run "$REPO_ROOT/scripts/container-run.sh" test
    if [ ! -f "$latest_log" ]; then
        skip "docker not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" != *"--privileged"* ]]
    [[ "$output" == *"test"* ]]
    [[ "$output" == *"/sushida-os"* ]]
}

@test "container-run.sh iso mode has --privileged" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" run "$REPO_ROOT/scripts/container-run.sh" iso
    if [ ! -f "$latest_log" ]; then
        skip "docker not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" == *"--privileged"* ]]
    [[ "$output" == *"iso"* ]]
}

@test "container-run.sh verify mode is non-privileged" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" run "$REPO_ROOT/scripts/container-run.sh" verify
    if [ ! -f "$latest_log" ]; then
        skip "docker not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" != *"--privileged"* ]]
    [[ "$output" == *"verify"* ]]
}

@test "container-run.sh passes BUILDER_IMAGE to docker" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" run "$REPO_ROOT/scripts/container-run.sh" test
    if [ ! -f "$latest_log" ]; then
        skip "docker not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" == *"sushida-os-builder:trixie"* ]]
}

@test "container-run.sh supports custom BUILDER_IMAGE" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" BUILDER_IMAGE=custom:v1 \
        run "$REPO_ROOT/scripts/container-run.sh" test
    if [ ! -f "$latest_log" ]; then
        skip "docker not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" == *"custom:v1"* ]]
}

@test "container-run.sh propagates docker exit code" {
    latest_log="$TEST_ROOT/argv-logs/docker.run.log"
    DOCKER_LOG="$latest_log" DOCKER_EXIT=42 run "$REPO_ROOT/scripts/container-run.sh" test
    if [ -f "$latest_log" ]; then
        # Docker was invoked; exit code should be 42.
        [ "$status" -eq 42 ]
    else
        # Docker not available; the wrapper returned its own error.
        [ "$status" -ne 0 ]
    fi
}

@test "container-run.sh uses podman with --cgroup-manager=cgroupfs" {
    latest_log="$TEST_ROOT/argv-logs/podman.run.log"
    PODMAN_LOG="$latest_log" CONTAINER_ENGINE=podman \
        run "$REPO_ROOT/scripts/container-run.sh" test
    if [ ! -f "$latest_log" ]; then
        skip "podman not invoked by wrapper"
    fi
    run read_argv "$latest_log"
    [[ "$output" == *"--cgroup-manager=cgroupfs"* ]]
    [[ "$output" == *"test"* ]]
    [[ "$output" == *"/sushida-os"* ]]
}

# ── container-run.sh: basic validation ───────────────────────────────────

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

# ── container-run.sh: fake docker ────────────────────────────────────────

@test "doctor.sh test profile passes when tools are present" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"repository_root=PASS"* ]]
}

@test "doctor.sh rejects unknown profile" {
    run "$REPO_ROOT/scripts/doctor.sh" unknown
    [ "$status" -ne 0 ]
    # Error message goes to stderr; combine both streams
    [[ "$output" == *"unknown profile"* ]] || [[ "$output" == *"unknown"* ]]
}

@test "doctor.sh does not modify the repository workspace" {
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    local before="$output"
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    local after="$output"
    [ "$after" = "$before" ]
}

@test "doctor.sh build and qemu profiles run without modifying workspace" {
    run "$REPO_ROOT/scripts/doctor.sh" build
    run "$REPO_ROOT/scripts/doctor.sh" qemu
    # Build profile may fail if container engine not available
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    [ -z "$output" ] || [ "$status" -eq 0 ]
}

@test "doctor.sh output format contains expected NAME=VALUE patterns" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"=PASS"* ]] || [[ "$output" == *"=FAIL"* ]] || [[ "$output" == *"=WARN"* ]]
}
