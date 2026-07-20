# shellcheck shell=bash
# Shared safe ISO / SquashFS extraction helpers for release verification.
#
# Sourced by scripts/verify-iso.sh (and any future manifest-driven
# verifier); not executable on its own.  Every helper confines its writes
# to the scratch directory created by iso_scratch_init, rejects
# traversal-style inner paths, and refuses symlinked inputs, so a crafted
# ISO or a replaced artifact can never redirect extraction outside the
# temporary root.

ISO_SCRATCH_ROOT=""
_ISO_SCRATCH_PARENT=""

# iso_scratch_init <parent_dir> <name_prefix>
# Creates <parent>/<prefix>.$$ mode 0700.  The cleanup trap is installed
# before anything is created so no failure path can leave the scratch
# directory behind.
iso_scratch_init() {
    local parent="$1" prefix="$2"
    [ -d "$parent" ] || return 1
    [ ! -L "$parent" ] || return 1
    case "$prefix" in
        ''|*/*|*..*|.*) return 1 ;;
    esac
    _ISO_SCRATCH_PARENT="$(cd "$parent" && pwd -P)"
    ISO_SCRATCH_ROOT="$_ISO_SCRATCH_PARENT/$prefix.$$"
    [ ! -e "$ISO_SCRATCH_ROOT" ] || return 1
    trap iso_scratch_cleanup EXIT INT TERM HUP
    mkdir -m 0700 "$ISO_SCRATCH_ROOT"
}

# Removes the scratch directory and nothing else: the target must still be
# a non-symlink path directly inside the parent recorded at init time.
iso_scratch_cleanup() {
    [ -n "$ISO_SCRATCH_ROOT" ] || return 0
    case "$ISO_SCRATCH_ROOT" in
        "$_ISO_SCRATCH_PARENT"/*) ;;
        *) return 1 ;;
    esac
    case "${ISO_SCRATCH_ROOT#"$_ISO_SCRATCH_PARENT/"}" in
        */*|*..*) return 1 ;;
    esac
    [ ! -L "$ISO_SCRATCH_ROOT" ] || return 1
    rm -rf -- "$ISO_SCRATCH_ROOT"
}

_iso_require_regular_input() {
    [ ! -L "$1" ] && [ -f "$1" ]
}

_iso_require_scratch_dest() {
    [ -n "$ISO_SCRATCH_ROOT" ] || return 1
    case "$1" in
        "$ISO_SCRATCH_ROOT"/*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        *..*) return 1 ;;
    esac
}

_iso_safe_inner_path() {
    [ -n "$1" ] || return 1
    case "/$1/" in
        *"/../"*) return 1 ;;
    esac
}

# iso_list_files <iso> <out_file>
iso_list_files() {
    local iso="$1" out="$2"
    _iso_require_regular_input "$iso" || return 1
    _iso_require_scratch_dest "$out" || return 1
    xorriso -indev "$iso" -find / -type f -exec echo > "$out" \
        2>> "$ISO_SCRATCH_ROOT/xorriso.log"
}

# iso_report_system_area <iso> <out_file>
iso_report_system_area() {
    local iso="$1" out="$2"
    _iso_require_regular_input "$iso" || return 1
    _iso_require_scratch_dest "$out" || return 1
    xorriso -indev "$iso" -report_system_area plain > "$out" \
        2>> "$ISO_SCRATCH_ROOT/xorriso.log"
}

# iso_extract_file <iso> </absolute/inner/path> <dest_in_scratch>
iso_extract_file() {
    local iso="$1" inner="$2" dest="$3"
    _iso_require_regular_input "$iso" || return 1
    case "$inner" in /*) ;; *) return 1 ;; esac
    _iso_safe_inner_path "$inner" || return 1
    _iso_require_scratch_dest "$dest" || return 1
    xorriso -osirrox on -indev "$iso" -extract "$inner" "$dest" \
        > /dev/null 2>> "$ISO_SCRATCH_ROOT/xorriso.log"
}

# squashfs_list <squashfs> <out_file>
squashfs_list() {
    local squashfs="$1" out="$2"
    _iso_require_regular_input "$squashfs" || return 1
    _iso_require_scratch_dest "$out" || return 1
    unsquashfs -ll "$squashfs" > "$out"
}

# squashfs_cat <squashfs> <relative/inner/path> <dest_in_scratch>
# The inner path is relative (no leading slash) and may contain the glob
# forms unsquashfs itself accepts; traversal segments are rejected.
squashfs_cat() {
    local squashfs="$1" inner="$2" dest="$3"
    _iso_require_regular_input "$squashfs" || return 1
    case "$inner" in /*) return 1 ;; esac
    _iso_safe_inner_path "$inner" || return 1
    _iso_require_scratch_dest "$dest" || return 1
    unsquashfs -cat "$squashfs" "$inner" > "$dest"
}
