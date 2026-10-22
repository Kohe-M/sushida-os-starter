#!/usr/bin/env bash
# Run a Make target inside the Sushi-da OS builder container.
# Usage: CONTAINER_ENGINE=docker|podman ./scripts/container-run.sh <mode>
#   mode: test | shell | configure | iso | verify |
#         qemu-boot | qemu-smoke | qemu-powerdown
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
MODE="${1:-}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
BUILDER_IMAGE="${BUILDER_IMAGE:-sushida-os-builder:trixie}"
readonly MODES="test | shell | configure | iso | verify | qemu-boot | qemu-smoke | qemu-powerdown"

# ── Validation ──────────────────────────────────────────────────────────
if [ -z "$MODE" ]; then
    echo "Usage: CONTAINER_ENGINE=docker|podman $0 <mode>" >&2
    echo "  mode: $MODES" >&2
    exit 1
fi

case "$MODE" in
    test|shell|configure|iso|verify|qemu-boot|qemu-smoke|qemu-powerdown) ;;
    *) echo "ERROR: unknown mode: $MODE (use $MODES)" >&2; exit 1 ;;
esac

if [ -L "$PROJECT_ROOT" ]; then
    echo "ERROR: repository root is a symlink: $PROJECT_ROOT" >&2
    exit 1
fi

case "$CONTAINER_ENGINE" in
    docker|podman) ;;
    *) echo "ERROR: unknown container engine: $CONTAINER_ENGINE (use docker or podman)" >&2; exit 1 ;;
esac

# ── Builder image: local, and built from the current builder/ sources ───
# --pull=never: a missing local image must stop here instead of letting the
# engine resolve the short name against a registry and run whatever image
# of that name it finds there.
expected_hash="$("$SCRIPT_DIR/builder-hash.sh")"
if ! image_hash="$("$CONTAINER_ENGINE" image inspect \
        --format '{{ index .Config.Labels "org.sushida-os.builder-hash" }}' \
        "$BUILDER_IMAGE" 2>/dev/null)"; then
    echo "ERROR: builder image $BUILDER_IMAGE not found locally" >&2
    echo "       run: make builder CONTAINER_ENGINE=$CONTAINER_ENGINE" >&2
    exit 1
fi
if [ "$image_hash" != "$expected_hash" ]; then
    echo "ERROR: builder image $BUILDER_IMAGE is stale (builder/ changed since it was built)" >&2
    echo "       run: make builder CONTAINER_ENGINE=$CONTAINER_ENGINE" >&2
    exit 1
fi

# ── Engine-specific arguments ────────────────────────────────────────────
ENGINE_ARGS=(--pull=never)

ROOTLESS_PODMAN=false
if [ "$CONTAINER_ENGINE" = "podman" ]; then
    ENGINE_ARGS+=(--cgroup-manager=cgroupfs)
    if [ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" = true ]; then
        ROOTLESS_PODMAN=true
    fi
fi

# Only ISO build needs privileged access for loopback mounts.
PRIVILEGED=false
if [ "$MODE" = "iso" ]; then
    PRIVILEGED=true
fi

if [ "$PRIVILEGED" = true ]; then
    ENGINE_ARGS+=(--privileged)
fi

# Map host UID/GID for non-privileged modes so files are not created as root.
# Rootless podman additionally needs keep-id: without it the container UID
# maps to a subordinate host UID that cannot write the bind-mounted build/.
if [ "$PRIVILEGED" = false ]; then
    if [ "$ROOTLESS_PODMAN" = true ]; then
        ENGINE_ARGS+=(--userns=keep-id)
    fi
    ENGINE_ARGS+=(-u "$(id -u):$(id -g)")
    ENGINE_ARGS+=(-e "HOME=/tmp")
    ENGINE_ARGS+=(-e "PYTHONDONTWRITEBYTECODE=1")
fi

# ── QEMU: hardware acceleration and bounded-duration overrides ───────────
case "$MODE" in
    qemu-*)
        if [ -c /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
            ENGINE_ARGS+=(--device /dev/kvm)
            if [ "$ROOTLESS_PODMAN" = true ]; then
                ENGINE_ARGS+=(--group-add keep-groups)
            else
                ENGINE_ARGS+=(--group-add "$(stat -c %g /dev/kvm)")
            fi
        else
            echo "WARNING: /dev/kvm is not usable; QEMU falls back to slow TCG" >&2
            echo "         (UEFI smoke under TCG is a known failure, registry R5)" >&2
        fi
        # Only the documented duration knobs pass through; the QEMU scripts
        # validate their values.
        for name in SUSHIDA_QEMU_DURATION SUSHIDA_QEMU_BIOS_DURATION \
                SUSHIDA_QEMU_UEFI_DURATION SUSHIDA_QEMU_POWERDOWN_TIMEOUT; do
            if [ -n "${!name:-}" ]; then
                ENGINE_ARGS+=(-e "$name=${!name}")
            fi
        done
        ;;
esac

# ── Map mode -> Make target ─────────────────────────────────────────────
case "$MODE" in
    test)    TARGET="test" ;;
    shell)  TARGET="test-shell" ;;
    configure) TARGET="configure" ;;
    iso)    TARGET="iso" ;;
    verify) TARGET="verify" ;;
    qemu-boot) TARGET="test-qemu-boot" ;;
    qemu-smoke) TARGET="test-qemu-runtime" ;;
    qemu-powerdown) TARGET="test-qemu-powerdown" ;;
esac

# ── Run ─────────────────────────────────────────────────────────────────
"$CONTAINER_ENGINE" run --rm \
    "${ENGINE_ARGS[@]}" \
    -v "$PROJECT_ROOT:/sushida-os" \
    -w /sushida-os \
    "$BUILDER_IMAGE" \
    make "$TARGET"
