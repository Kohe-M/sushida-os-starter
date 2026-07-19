#!/usr/bin/env bash
set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Sushi-da OS builder container"
    echo ""
    echo "Usage:  docker run --rm -v \"\$PWD:/sushida-os\" <image> <command>"
    echo ""
    echo "Tools:  live-build  python3/pytest  shellcheck  bats"
    echo "        make       git             jq          systemd-analyze"
    echo ""
    echo "Examples:"
    echo "  make test-static"
    echo "  make test-shell"
    echo "  shellcheck builder/entrypoint.sh"
    echo "  python3 -m pytest tests/static/"
    exec bash
fi

# Docker Desktop bind-mounts a host directory as root-owned.  Git refuses to
# operate on a repository owned by a different user unless safe.directory is
# set to the mount path.  The verification command itself must carry a
# one-shot safe.directory override because Git rejects even rev-parse on an
# unlisted directory.
if [ -e /sushida-os ]; then
    if [ -L /sushida-os ]; then
        # Symlinked mount points cannot be a safe git repository; skip.
        :
    elif [ -d /sushida-os/.git ] || [ -f /sushida-os/.git ]; then
        git_repo="$(
            git -c safe.directory=/sushida-os \
                -C /sushida-os rev-parse --show-toplevel 2>/dev/null ||
            true
        )"
        if [ "$git_repo" = "/sushida-os" ]; then
            git config --global --add safe.directory /sushida-os
        fi
    fi
fi

exec "$@"
