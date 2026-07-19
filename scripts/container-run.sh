#!/usr/bin/env bash
# Run a Make target inside the Sushi-da OS builder container.
# Usage: CONTAINER_ENGINE=docker|podman ./scripts/container-run.sh <mode>
#   mode: test | shell | configure | iso | verify
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
MODE="${1:-}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
BUILDER_IMAGE="${BUILDER_IMAGE:-sushida-os-builder:trixie}"

# ── Validation ──────────────────────────────────────────────────────────
if [ -z "$MODE" ]; then
    echo "Usage: CONTAINER_ENGINE=docker|podman $0 <mode>" >&2
    echo "  mode: test | shell | configure | iso | verify" >&2
    exit 1
fi

case "$MODE" in
    test|shell|configure|iso|verify) ;;
    *) echo "ERROR: unknown mode: $MODE" >&2; exit 1 ;;
esac

if [ -L "$PROJECT_ROOT" ]; then
    echo "ERROR: repository root is a symlink: $PROJECT_ROOT" >&2
    exit 1
fi

case "$CONTAINER_ENGINE" in
    docker|podman) ;;
    *) echo "ERROR: unknown container engine: $CONTAINER_ENGINE (use docker or podman)" >&2; exit 1 ;;
esac

# ── Engine-specific arguments ────────────────────────────────────────────
ENGINE_ARGS=()

if [ "$CONTAINER_ENGINE" = "podman" ]; then
    ENGINE_ARGS+=(--cgroup-manager=cgroupfs)
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
if [ "$PRIVILEGED" = false ]; then
    ENGINE_ARGS+=(-u "$(id -u):$(id -g)")
    ENGINE_ARGS+=(-e "HOME=/tmp")
    ENGINE_ARGS+=(-e "PYTHONDONTWRITEBYTECODE=1")
fi

# ── Map mode -> Make target ─────────────────────────────────────────────
case "$MODE" in
    test)    TARGET="test" ;;
    shell)  TARGET="test-shell" ;;
    configure) TARGET="configure" ;;
    iso)    TARGET="iso" ;;
    verify) TARGET="verify" ;;
esac

# ── Run ─────────────────────────────────────────────────────────────────
"$CONTAINER_ENGINE" run --rm \
    "${ENGINE_ARGS[@]}" \
    -v "$PROJECT_ROOT:/sushida-os" \
    -w /sushida-os \
    "$BUILDER_IMAGE" \
    make "$TARGET"
