# shellcheck shell=bash
# Shared QEMU evidence helpers for the runner (scripts/run-qemu.sh) and the
# assessors (tests/qemu/*-test.sh); sourced, not executable.
#
# These existed as up-to-four diverging copies: the pipefail/SIGPIPE fix had
# to be applied twice while two copies were immune only by accident.  Any
# change to how serial evidence or result records are read happens here once.

# serial_without_ansi <serial-log>
# systemd's serial console decorates status lines with ANSI colour sequences.
# Strip those sequences before matching lifecycle evidence so the checks are
# based on the actual unit messages rather than terminal presentation.
serial_without_ansi() {
    sed -E $'s/\x1B\\[[0-9;?]*[ -/]*[@-~]//g' "$1"
}

# serial_matches <serial-log> <ERE>
serial_matches() {
    # grep must consume the whole stream: with pipefail, `grep -q` exiting at
    # the first match sends SIGPIPE to sed once the log outgrows the pipe
    # buffer, turning genuine matches into pipeline failures.
    serial_without_ansi "$1" | grep -Ei -- "$2" > /dev/null
}

# result_value <result-env> <key>
# Print the value recorded exactly once for <key>; fail on zero or duplicates.
result_value() {
    awk -F= -v key="$2" '
        $1 == key { count++; value = substr($0, index($0, "=") + 1) }
        END { if (count != 1) exit 1; print value }
    ' "$1"
}
