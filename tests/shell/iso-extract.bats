#!/usr/bin/env bats
# Tests for the shared safe ISO/SquashFS extraction library.

LIB="scripts/lib/iso-extract.sh"

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/iso-extract"
    mkdir -p "$TEST_ROOT/parent"
    export TEST_ROOT
}

# Run a bash snippet with the library sourced, in its own process so the
# EXIT trap installed by iso_scratch_init fires when the snippet ends.
lib_run() {
    run bash -c ". '$LIB'; $1"
}

@test "scratch init creates 0700 directory under the parent" {
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 1
        [ -d "$ISO_SCRATCH_ROOT" ] || exit 1
        [ "$(stat -c %a "$ISO_SCRATCH_ROOT")" = 700 ] || exit 1
        case "$ISO_SCRATCH_ROOT" in
            "$TEST_ROOT/parent"/scratch.*) exit 0 ;;
            *) exit 1 ;;
        esac
    '
    [ "$status" -eq 0 ]
}

@test "cleanup trap removes the scratch directory even on failure exits" {
    run bash -c ". '$LIB'
        iso_scratch_init '$TEST_ROOT/parent' scratch || exit 9
        printf '%s\n' \"\$ISO_SCRATCH_ROOT\" > '$TEST_ROOT/created'
        exit 7
    "
    [ "$status" -eq 7 ]
    created="$(cat "$TEST_ROOT/created")"
    [ -n "$created" ]
    [ ! -e "$created" ]
}

@test "scratch init refuses symlinked parent" {
    mkdir -p "$TEST_ROOT/real-parent"
    ln -s "$TEST_ROOT/real-parent" "$TEST_ROOT/link-parent"
    lib_run 'iso_scratch_init "$TEST_ROOT/link-parent" scratch'
    [ "$status" -ne 0 ]
}

@test "scratch init refuses traversal-style prefixes" {
    for prefix in "../evil" "a/b" ".." ".hidden"; do
        lib_run "iso_scratch_init \"\$TEST_ROOT/parent\" '$prefix'"
        [ "$status" -ne 0 ]
    done
}

@test "cleanup never removes a directory outside the recorded parent" {
    mkdir -p "$TEST_ROOT/victim"
    lib_run '
        _ISO_SCRATCH_PARENT="$TEST_ROOT/parent"
        ISO_SCRATCH_ROOT="$TEST_ROOT/victim"
        iso_scratch_cleanup
    '
    [ "$status" -ne 0 ]
    [ -d "$TEST_ROOT/victim" ]
}

@test "cleanup never follows a symlinked scratch root" {
    mkdir -p "$TEST_ROOT/victim"
    ln -s "$TEST_ROOT/victim" "$TEST_ROOT/parent/scratch.link"
    lib_run '
        _ISO_SCRATCH_PARENT="$TEST_ROOT/parent"
        ISO_SCRATCH_ROOT="$TEST_ROOT/parent/scratch.link"
        iso_scratch_cleanup
    '
    [ "$status" -ne 0 ]
    [ -d "$TEST_ROOT/victim" ]
}

@test "extraction helpers refuse symlinked input images" {
    printf 'data' > "$TEST_ROOT/real.iso"
    ln -s "$TEST_ROOT/real.iso" "$TEST_ROOT/link.iso"
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 9
        iso_list_files "$TEST_ROOT/link.iso" "$ISO_SCRATCH_ROOT/out"
    '
    [ "$status" -ne 0 ]
    [ "$status" -ne 9 ]
}

@test "extraction helpers refuse destinations outside the scratch root" {
    printf 'data' > "$TEST_ROOT/real.iso"
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 9
        iso_list_files "$TEST_ROOT/real.iso" "$TEST_ROOT/outside.txt"
    '
    [ "$status" -ne 0 ]
    [ ! -e "$TEST_ROOT/outside.txt" ]
}

@test "inner path traversal is rejected for ISO and SquashFS reads" {
    printf 'data' > "$TEST_ROOT/image"
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 9
        iso_extract_file "$TEST_ROOT/image" "/live/../etc/passwd" "$ISO_SCRATCH_ROOT/a" && exit 1
        iso_extract_file "$TEST_ROOT/image" "relative/path" "$ISO_SCRATCH_ROOT/b" && exit 2
        squashfs_cat "$TEST_ROOT/image" "../etc/passwd" "$ISO_SCRATCH_ROOT/c" && exit 3
        squashfs_cat "$TEST_ROOT/image" "/absolute/path" "$ISO_SCRATCH_ROOT/d" && exit 4
        exit 0
    '
    [ "$status" -eq 0 ]
}

@test "ISO listing and extraction round-trip with a real image" {
    command -v xorriso > /dev/null 2>&1 || skip "xorriso not available"
    mkdir -p "$TEST_ROOT/tree/live"
    printf 'payload-content\n' > "$TEST_ROOT/tree/live/data.txt"
    xorriso -outdev "$TEST_ROOT/test.iso" \
        -map "$TEST_ROOT/tree" / -commit > /dev/null 2>&1
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 9
        iso_list_files "$TEST_ROOT/test.iso" "$ISO_SCRATCH_ROOT/list" || exit 1
        grep -Eq "^'\''?/live/data\.txt'\''?$" "$ISO_SCRATCH_ROOT/list" || exit 2
        iso_extract_file "$TEST_ROOT/test.iso" /live/data.txt "$ISO_SCRATCH_ROOT/data" || exit 3
        grep -qx "payload-content" "$ISO_SCRATCH_ROOT/data" || exit 4
        exit 0
    '
    [ "$status" -eq 0 ]
}

@test "SquashFS listing and cat round-trip with a real image" {
    command -v mksquashfs > /dev/null 2>&1 || skip "mksquashfs not available"
    command -v unsquashfs > /dev/null 2>&1 || skip "unsquashfs not available"
    mkdir -p "$TEST_ROOT/sqtree/usr/share"
    printf 'squash-content\n' > "$TEST_ROOT/sqtree/usr/share/data.txt"
    mksquashfs "$TEST_ROOT/sqtree" "$TEST_ROOT/test.squashfs" \
        -no-progress -quiet > /dev/null 2>&1
    lib_run '
        iso_scratch_init "$TEST_ROOT/parent" scratch || exit 9
        squashfs_list "$TEST_ROOT/test.squashfs" "$ISO_SCRATCH_ROOT/list" || exit 1
        grep -q "squashfs-root/usr/share/data.txt" "$ISO_SCRATCH_ROOT/list" || exit 2
        squashfs_cat "$TEST_ROOT/test.squashfs" usr/share/data.txt "$ISO_SCRATCH_ROOT/data" || exit 3
        grep -qx "squash-content" "$ISO_SCRATCH_ROOT/data" || exit 4
        exit 0
    '
    [ "$status" -eq 0 ]
}

@test "library has strict path guards and no eval" {
    grep -qF 'trap iso_scratch_cleanup EXIT INT TERM HUP' "$LIB"
    grep -qF 'rm -rf -- "$ISO_SCRATCH_ROOT"' "$LIB"
    run grep -E '\beval\b' "$LIB"
    [ "$status" -ne 0 ]
}
