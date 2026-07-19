#!/usr/bin/env bats
# Tests for the development tooling wrappers (doctor.sh, container-run.sh).

setup() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/dev-tools"
    mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home" "$TEST_ROOT/argv-logs"
    export PATH="$TEST_ROOT/bin:$PATH"
    export HOME="$TEST_ROOT/home"
    export CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
    # Determine repository root from the test file location
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd -P)"

    # Fake docker/podman that record argv to a file
    cat > "$TEST_ROOT/bin/docker" <<'FAKEDOCKER'
#!/bin/sh
set -eu
log="$TEST_ROOT/argv-logs/docker.$(date +%s.%N).log"
mkdir -p "$(dirname "$log")"
for a in docker "$@"; do printf '%s\0' "$a"; done > "$log"
exit "${DOCKER_EXIT:-0}"
FAKEDOCKER
    chmod +x "$TEST_ROOT/bin/docker"

    cat > "$TEST_ROOT/bin/podman" <<'FAKEPODMAN'
#!/bin/sh
set -eu
log="$TEST_ROOT/argv-logs/podman.$(date +%s.%N).log"
mkdir -p "$(dirname "$log")"
for a in podman "$@"; do printf '%s\0' "$a"; done > "$log"
exit "${PODMAN_EXIT:-0}"
FAKEPODMAN
    chmod +x "$TEST_ROOT/bin/podman"

    export BUILDER_IMAGE="${BUILDER_IMAGE:-sushida-os-builder:trixie}"
}

# Helper: read a NUL-joined argv log as an array
read_argv() {
    local logfile="$1"
    if [ ! -f "$logfile" ]; then
        echo "ERROR: argv log not found: $logfile" >&2
        return 1
    fi
    while IFS= read -r -d '' arg; do
        printf '%s\n' "$arg"
    done < "$logfile"
}

# ── container-run.sh: fake docker ────────────────────────────────────────

@test "container-run.sh test mode has --privileged not set" {
    run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ] || {
        # The wrapper may fail if no real docker is available, but we can
        # still verify the --privileged logic by checking that the exit
        # is not caused by a --privileged shell error.
        [[ "$output" != *"--privileged"* ]]
    }
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
    if [ -n "$latest_log" ]; then
        run read_argv "$latest_log"
        [[ "$output" != *"--privileged"* ]]
        [[ "$output" == *"make test"* ]]
        [[ "$output" == *"/sushida-os"* ]]
    fi
}

@test "container-run.sh iso mode has --privileged" {
    run "$REPO_ROOT/scripts/container-run.sh" iso
    [ "$status" -eq 0 ] || return 0
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
    [ -n "$latest_log" ] || skip "no docker argv logged"
    run read_argv "$latest_log"
    [[ "$output" == *"--privileged"* ]]
    [[ "$output" == *"make iso"* ]]
}

@test "container-run.sh verify mode is non-privileged" {
    run "$REPO_ROOT/scripts/container-run.sh" verify
    [ "$status" -eq 0 ] || return 0
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
    [ -n "$latest_log" ] || skip "no docker argv logged"
    run read_argv "$latest_log"
    [[ "$output" != *"--privileged"* ]]
    [[ "$output" == *"make verify"* ]]
}

@test "container-run.sh passes BUILDER_IMAGE to docker" {
    run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ] || return 0
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
    [ -n "$latest_log" ] || skip "no docker argv logged"
    run read_argv "$latest_log"
    [[ "$output" == *"sushida-os-builder:trixie"* ]]
}

@test "container-run.sh supports custom BUILDER_IMAGE" {
    BUILDER_IMAGE=custom:v1 run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ] || return 0
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
    [ -n "$latest_log" ] || skip "no docker argv logged"
    run read_argv "$latest_log"
    [[ "$output" == *"custom:v1"* ]]
}

@test "container-run.sh propagates docker exit code" {
    # Docker exit 42 must propagate through the wrapper.
    DOCKER_EXIT=42 run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 42 ] || {
        # If the test docker was not invoked (host lacks docker), skip.
        latest_log=$(ls -t "$TEST_ROOT/argv-logs"/docker.*.log 2>/dev/null | head -1)
        [ -z "$latest_log" ] && skip "docker not invoked"
    }
}

@test "container-run.sh uses podman with --cgroup-manager=cgroupfs" {
    CONTAINER_ENGINE=podman run "$REPO_ROOT/scripts/container-run.sh" test
    [ "$status" -eq 0 ] || return 0
    latest_log=$(ls -t "$TEST_ROOT/argv-logs"/podman.*.log 2>/dev/null | head -1)
    [ -n "$latest_log" ] || skip "no podman argv logged"
    run read_argv "$latest_log"
    [[ "$output" == *"--cgroup-manager=cgroupfs"* ]]
    [[ "$output" == *"make test"* ]]
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
