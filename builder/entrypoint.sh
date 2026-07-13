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

exec "$@"
