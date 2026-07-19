#!/usr/bin/env bash
# Print all tracked files that should be checked with ShellCheck,
# one per line.  Includes executable shell scripts, *.sh, *.bats,
# *.hook.chroot, and live-build/auto/* files.  Duplicates are removed.
set -euo pipefail

cd "$(dirname "$0")/.."
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

# 1. Pattern-based candidates
git ls-files -- '*.sh' '*.bats' '*.hook.chroot' 'live-build/auto/*' >> "$tmp"

# 2. Mode-100755 files with a shell shebang
git ls-files --stage | \
awk '$1 == "100755" {print $4}' | \
while IFS= read -r path; do
    if [ -n "$path" ] && grep -Eqm1 '^(#!/bin/(ba)?sh|#!/usr/bin/(env )?(ba)?sh|#!/usr/bin/dash)' "$path" 2>/dev/null; then
        printf '%s\n' "$path"
    fi
done >> "$tmp"

sort -u "$tmp"
