#!/usr/bin/env bash
# Print the set of tracked executable shell files for ShellCheck.
# Only files whose git-index mode is 100755 and that start with a POSIX
# shell shebang are included.
set -euo pipefail

cd "$(dirname "$0")/.."

git ls-files --stage | \
awk '$1 == "100755" {print $4}' | \
while IFS= read -r path; do
    if [ -n "$path" ] && grep -Eqm1 '^(#!/bin/(ba)?sh|#!/usr/bin/(env )?(ba)?sh|#!/usr/bin/dash)' "$path" 2>/dev/null; then
        printf '%s\n' "$path"
    fi
done
