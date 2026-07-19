#!/usr/bin/env bash
# Check host prerequisites for Sushi-da OS development.
# Usage: ./scripts/doctor.sh [profile]
#   profile: test (default), build, qemu
# Returns non-zero when required items are missing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PROFILE="${1:-test}"

case "$PROFILE" in
    test|build|qemu) ;;
    *) echo "ERROR: unknown doctor profile: $PROFILE (use test, build, or qemu)" >&2; exit 1 ;;
esac

_status=0

check() {
    local label="$1" cmd="$2" severity="${3:-REQUIRED}"
    if command -v "$cmd" > /dev/null 2>&1; then
        echo "${label}=PASS"
    else
        echo "${label}=${severity}"
        if [ "$severity" = "REQUIRED" ]; then _status=1; fi
    fi
}

check_path() {
    local label="$1" path="$2"
    if [ -e "$path" ] && [ ! -L "$path" ]; then
        echo "${label}=PASS"
    elif [ -L "$path" ]; then
        echo "${label}=WARN (symlink)"
    else
        echo "${label}=WARN (missing)"
    fi
}

# ── Common (test profile) ────────────────────────────────────────────────
echo "### Profile: ${PROFILE}"
check "git" git
check "make" make
check "python3" python3
check "pytest" pytest
check "shellcheck" shellcheck
check "bats" bats

if [ -d "$PROJECT_ROOT/.git" ] || [ -f "$PROJECT_ROOT/.git" ]; then
    echo "repository_root=PASS"
else
    echo "repository_root=FAIL"
    _status=1
fi

# Check that tracked executable scripts have correct mode bits.
_bad_mode=false
while IFS= read -r path; do
    mode=$(git ls-files --stage "$path" | awk '{print $1}')
    if [ "$mode" != "100755" ]; then
        echo "script_mode:WARN ($path is not 100755)"
        _bad_mode=true
    fi
done < <("$SCRIPT_DIR/shellcheck-targets.sh" 2>/dev/null)
if [ "$_bad_mode" = false ]; then
    echo "script_mode=PASS"
fi

# ── Build profile ────────────────────────────────────────────────────────
if [ "$PROFILE" = build ] || [ "$PROFILE" = qemu ]; then
    check "docker" docker WARN
    check "podman" podman WARN
    if [ -n "${CONTAINER_ENGINE:-}" ]; then
        echo "container_engine_override=PASS"
    fi
    # Check if any container engine connects
    _engine_found=false
    _engines_to_check="${CONTAINER_ENGINE:-docker podman}"
    for engine in $_engines_to_check; do
        if command -v "$engine" > /dev/null 2>&1; then
            if "$engine" info > /dev/null 2>&1; then
                echo "container_daemon_${engine}=PASS"
                _engine_found=true
            else
                echo "container_daemon_${engine}=FAIL (not connected)"
            fi
        fi
    done
    # If CONTAINER_ENGINE is explicitly set, it must be available.
    # Otherwise, at least one engine must work.
    if [ -n "${CONTAINER_ENGINE:-}" ]; then
        if [ "$_engine_found" = false ]; then
            echo "container_daemon=FAIL"
            _status=1
        fi
    elif [ "$_engine_found" = false ]; then
        echo "container_daemon=FAIL"
        _status=1
    fi
    # Check builder image
    _builder_found=false
    _builder_image="${BUILDER_IMAGE:-sushida-os-builder:trixie}"
    for engine in docker podman; do
        if command -v "$engine" > /dev/null 2>&1; then
            if "$engine" image inspect "$_builder_image" > /dev/null 2>&1; then
                echo "builder_image=PASS"
                _builder_found=true
                break
            fi
        fi
    done
    if [ "$_builder_found" = false ]; then
        echo "builder_image=FAIL"
        _status=1
    fi
    # Warn about WSL + Windows mount
    if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
        if echo "$PROJECT_ROOT" | grep -qE '^/(mnt/[a-z]/|.*/host/)'; then
            echo "wsl_mount=WARN (under Windows mount, may affect file modes)"
        fi
    fi
fi

# ── QEMU profile ─────────────────────────────────────────────────────────
if [ "$PROFILE" = qemu ]; then
    check "qemu_system" qemu-system-x86_64
    check "socat" socat
    check_path "ovmf_code" "/usr/share/OVMF/OVMF_CODE.fd"
    check_path "ovmf_vars" "/usr/share/OVMF/OVMF_VARS.fd"
    if [ ! -f /usr/share/OVMF/OVMF_CODE.fd ] && [ ! -f /usr/share/OVMF/OVMF_CODE_4M.fd ]; then
        echo "ovmf_any=FAIL"
        _status=1
    fi
fi

exit $_status
