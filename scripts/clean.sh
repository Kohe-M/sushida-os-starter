#!/usr/bin/env bash
# Remove only fixed generated paths below this repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
BUILD_ROOT="$PROJECT_ROOT/build"
ARTIFACT_ROOT="$PROJECT_ROOT/artifacts"
MODE="${1:-clean}"

fail() {
    echo "ERROR: cleanup: $*" >&2
    exit 1
}

case "$MODE" in clean|distclean) ;; *) fail "usage: clean.sh [clean|distclean]" ;; esac
for root in "$BUILD_ROOT" "$ARTIFACT_ROOT"; do
    [ ! -L "$root" ] || fail "refusing symlinked generated root: $root"
    [ -d "$root" ] || fail "missing generated root: $root"
    resolved="$(cd "$root" && pwd -P)"
    [ "$resolved" = "$root" ] || fail "unexpected generated root: $resolved"
done

for path in \
    "$BUILD_ROOT/live-build" \
    "$BUILD_ROOT/qemu" \
    "$BUILD_ROOT/smoke-test"; do
    rm -rf -- "$path"
done
find "$BUILD_ROOT" -mindepth 1 -maxdepth 1 -type d \
    \( -name 'verify-artifacts.*' -o -name 'flash-test.*' \) -exec rm -rf -- {} +

if [ "$MODE" = "distclean" ]; then
    for file in \
        sushida-os-amd64.iso SHA256SUMS package-manifest.txt build-info.json; do
        rm -f -- "$ARTIFACT_ROOT/$file"
    done
    find "$ARTIFACT_ROOT" -mindepth 1 -maxdepth 1 -type d \
        -name '.build-staging.*' -exec rm -rf -- {} +
fi

echo "$MODE completed."
