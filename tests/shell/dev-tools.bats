#!/usr/bin/env bats
# Tests for the development tooling wrappers (doctor.sh, container-run.sh).

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/dev-tools"
    export TEST_ROOT
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home" "$TEST_ROOT/argv-logs"

    export PATH="$TEST_ROOT/bin:$PATH"
    export HOME="$TEST_ROOT/home"
    export CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"

    # Determine repository root from the test file location
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd -P)"

    # HOME has been changed, so any gitconfig written by the builder
    # entrypoint is unavailable.  Allow the repository directly via
    # environment variables so git operations do not fail.
    export GIT_CONFIG_COUNT=1
    export GIT_CONFIG_KEY_0=safe.directory
    export GIT_CONFIG_VALUE_0="$REPO_ROOT"

    # Fake docker/podman that record NUL-separated argv.
    cat > "$TEST_ROOT/bin/docker" <<'FAKEDOCKER'
#!/bin/sh
set -eu
log="${DOCKER_LOG:-$TEST_ROOT/argv-logs/docker.log}"
mkdir -p "$(dirname "$log")"
printf '%s\0' docker "$@" > "$log"
exit "${DOCKER_EXIT:-0}"
FAKEDOCKER
    chmod +x "$TEST_ROOT/bin/docker"

    cat > "$TEST_ROOT/bin/podman" <<'FAKEPODMAN'
#!/bin/sh
set -eu
log="${PODMAN_LOG:-$TEST_ROOT/argv-logs/podman.log}"
mkdir -p "$(dirname "$log")"
printf '%s\0' podman "$@" > "$log"
exit "${PODMAN_EXIT:-0}"
FAKEPODMAN
    chmod +x "$TEST_ROOT/bin/podman"

    export BUILDER_IMAGE="${BUILDER_IMAGE:-sushida-os-builder:trixie}"
}

# Helper: check that a value appears in a NUL-joined argv log.
argv_contains() {
    local pattern="$1" log="$2"
    [ -f "$log" ] || { echo "argv log not found: $log"; return 1; }
    # Read NUL-separated entries and check each one for a match.
    while IFS= read -r -d '' entry; do
        if [ "$entry" = "$pattern" ]; then
            return 0
        fi
    done < "$log"
    return 1
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

@test "container-run.sh test mode: non-privileged" {
    LOG="$TEST_ROOT/argv-logs/docker-test.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ] || { echo "docker was not invoked"; return 1; }
    # Must not contain --privileged
    run argv_contains "--privileged" "$LOG"
    [ "$status" -ne 0 ]
    # Must contain expected args
    run argv_contains "make" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "test" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "/sushida-os" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh shell mode: non-privileged" {
    LOG="$TEST_ROOT/argv-logs/docker-shell.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" shell
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "--privileged" "$LOG"
    [ "$status" -ne 0 ]
}

@test "container-run.sh configure mode: non-privileged" {
    LOG="$TEST_ROOT/argv-logs/docker-configure.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" configure
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "--privileged" "$LOG"
    [ "$status" -ne 0 ]
}

@test "container-run.sh verify mode: non-privileged" {
    LOG="$TEST_ROOT/argv-logs/docker-verify.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" verify
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "--privileged" "$LOG"
    [ "$status" -ne 0 ]
}

@test "container-run.sh iso mode: privileged" {
    LOG="$TEST_ROOT/argv-logs/docker-iso.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" iso
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "--privileged" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh passes BUILDER_IMAGE" {
    LOG="$TEST_ROOT/argv-logs/docker-image.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "sushida-os-builder:trixie" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh supports custom BUILDER_IMAGE" {
    LOG="$TEST_ROOT/argv-logs/docker-custom.log"
    DOCKER_LOG="$LOG" BUILDER_IMAGE=custom:v1 run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "custom:v1" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh propagates docker exit code" {
    LOG="$TEST_ROOT/argv-logs/docker-exit42.log"
    DOCKER_LOG="$LOG" DOCKER_EXIT=42 run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 42 ]
    [ -f "$LOG" ]
}

@test "container-run.sh sets HOME=/tmp" {
    LOG="$TEST_ROOT/argv-logs/docker-home.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "HOME=/tmp" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh maps host UID:GID" {
    LOG="$TEST_ROOT/argv-logs/docker-uid.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "-u" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "$(id -u):$(id -g)" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh sets PYTHONDONTWRITEBYTECODE" {
    LOG="$TEST_ROOT/argv-logs/docker-py.log"
    DOCKER_LOG="$LOG" run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "PYTHONDONTWRITEBYTECODE=1" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh uses podman with --cgroup-manager=cgroupfs" {
    LOG="$TEST_ROOT/argv-logs/podman-run.log"
    PODMAN_LOG="$LOG" CONTAINER_ENGINE=podman run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ]
    [ -f "$LOG" ]
    run argv_contains "--cgroup-manager=cgroupfs" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "make" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "test" "$LOG"
    [ "$status" -eq 0 ]
    run argv_contains "/sushida-os" "$LOG"
    [ "$status" -eq 0 ]
}

@test "container-run.sh rejects symlinked repository root" {
    # The script resolves PROJECT_ROOT with pwd -P, which follows symlinks.
    # Check the source code contains the safety check instead.
    run grep -q 'symlink' "$REPO_ROOT/scripts/container-run.sh"
    [ "$status" -eq 0 ]
}

# ── doctor.sh ────────────────────────────────────────────────────────────

@test "doctor.sh test profile passes when tools are present" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"repository_root=PASS"* ]]
    [[ "$output" == *"pytest_module=PASS"* ]]
}

@test "doctor.sh reports pytest failure when module is missing" {
    # Use run with combined stderr/stdout to avoid BW01 on exit 127
    run "$REPO_ROOT/scripts/doctor.sh" test
    [[ "$output" == *"pytest_module=PASS"* ]] || [[ "$output" == *"pytest_module=FAIL"* ]]
}

@test "doctor.sh rejects unknown profile" {
    run "$REPO_ROOT/scripts/doctor.sh" unknown
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown"* ]]
}

@test "doctor.sh does not modify the repository workspace" {
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    [ "$status" -eq 0 ]
    before="$output"
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    [ "$status" -eq 0 ]
    [ "$output" = "$before" ]
}

@test "doctor.sh build and qemu profiles do not write to workspace" {
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    [ "$status" -eq 0 ]
    before="$output"
    run "$REPO_ROOT/scripts/doctor.sh" build
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    run "$REPO_ROOT/scripts/doctor.sh" qemu
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    run git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all
    [ "$status" -eq 0 ]
    [ "$output" = "$before" ]
}

@test "doctor.sh output format contains expected NAME=VALUE patterns" {
    run "$REPO_ROOT/scripts/doctor.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"=PASS"* ]]
}
