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
    # The removable artifact set comes from the release contract; artifact
    # names are not repeated here.  Names are constrained to plain files
    # directly inside the artifact root.
    CONTRACT="$PROJECT_ROOT/contracts/release-contract.json"
    command -v python3 > /dev/null 2>&1 || fail "python3 is required for distclean"
    if [ ! -f "$CONTRACT" ] || [ -L "$CONTRACT" ]; then
        fail "release contract not found: $CONTRACT"
    fi
    while IFS= read -r artifact_name; do
        case "$artifact_name" in
            ''|*/*|.*) fail "unsafe artifact name in release contract" ;;
        esac
        rm -f -- "$ARTIFACT_ROOT/$artifact_name"
    done < <(python3 - "$CONTRACT" <<'PYEOF'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    contract = json.load(stream)
for artifact in contract["artifacts"]:
    if artifact.get("clean"):
        print(artifact["name"])
PYEOF
)
    find "$ARTIFACT_ROOT" -mindepth 1 -maxdepth 1 -type d \
        -name '.build-staging.*' -exec rm -rf -- {} +
fi

echo "$MODE completed."
