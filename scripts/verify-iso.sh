#!/usr/bin/env bash
# Verify artifact checksums, metadata, manifest, and required ISO contents.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ARTIFACT_ROOT="$PROJECT_ROOT/artifacts"
ARTIFACT_DIR="${1:-$ARTIFACT_ROOT}"
ISO_NAME="sushida-os-amd64.iso"

fail() {
    echo "ERROR: artifact verification: $*" >&2
    exit 1
}

[ ! -L "$ARTIFACT_ROOT" ] || fail "artifact root is a symlink"
if [ ! -d "$ARTIFACT_DIR" ] || [ -L "$ARTIFACT_DIR" ]; then
    fail "invalid artifact directory"
fi
resolved_root="$(cd "$ARTIFACT_ROOT" && pwd -P)"
resolved_dir="$(cd "$ARTIFACT_DIR" && pwd -P)"
case "$resolved_dir" in
    "$resolved_root"|"$resolved_root"/.build-staging.*) ;;
    *) fail "artifact directory is outside the repository artifact root" ;;
esac

for cmd in jq sha256sum awk grep xorriso unsquashfs; do
    command -v "$cmd" > /dev/null 2>&1 || fail "required command not found: $cmd"
done
for file in "$ISO_NAME" SHA256SUMS package-manifest.txt build-info.json; do
    path="$resolved_dir/$file"
    if [ ! -f "$path" ] || [ -L "$path" ] || [ ! -s "$path" ]; then
        fail "missing, empty, or unsafe artifact: $file"
    fi
done

checksum_line_count="$(wc -l < "$resolved_dir/SHA256SUMS")"
[ "$checksum_line_count" -eq 1 ] || fail "SHA256SUMS must contain exactly one line"
expected_name="$(awk '{print $2}' "$resolved_dir/SHA256SUMS")"
[ "$expected_name" = "$ISO_NAME" ] || fail "unexpected checksum filename: $expected_name"
(
    cd "$resolved_dir"
    sha256sum --check --strict SHA256SUMS
)

jq -e '
    (.git_commit | type == "string" and test("^[0-9a-f]{40,64}$")) and
    (.git_dirty | type == "boolean") and
    (.debian_release == "trixie") and
    (.build_timestamp | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T")) and
    (.architecture == "amd64") and
    (.chromium_version | type == "string" and length > 0) and
    (.cage_version | type == "string" and length > 0) and
    (.live_build_version | type == "string" and length > 0) and
    (.iso_sha256 | type == "string" and test("^[0-9a-f]{64}$"))
' "$resolved_dir/build-info.json" > /dev/null || fail "invalid build-info.json"

computed_sha="$(sha256sum "$resolved_dir/$ISO_NAME" | awk '{print $1}')"
metadata_sha="$(jq -r '.iso_sha256' "$resolved_dir/build-info.json")"
[ "$computed_sha" = "$metadata_sha" ] || fail "metadata ISO checksum mismatch"

for package in chromium cage; do
    version="$(awk -v package="$package" '$1 == package { print $2; exit }' \
        "$resolved_dir/package-manifest.txt")"
    [ -n "$version" ] || fail "$package missing from package manifest"
    metadata_version="$(jq -r ".${package}_version" "$resolved_dir/build-info.json")"
    [ "$version" = "$metadata_version" ] || fail "$package version mismatch"
done

VERIFY_ROOT="$PROJECT_ROOT/build/verify-artifacts.$$"
[ ! -e "$VERIFY_ROOT" ] || fail "verification scratch path already exists"
mkdir -m 0700 "$VERIFY_ROOT"
cleanup() {
    rm -rf -- "$VERIFY_ROOT"
}
trap cleanup EXIT INT TERM HUP

iso="$resolved_dir/$ISO_NAME"
iso_listing="$VERIFY_ROOT/iso-files.txt"
xorriso -indev "$iso" -find / -type f -print > "$iso_listing" 2> "$VERIFY_ROOT/xorriso.log" || \
    fail "cannot read ISO filesystem"
grep -Eq "^'?/live/filesystem\.squashfs'?$" "$iso_listing" || \
    fail "required ISO path missing: /live/filesystem.squashfs"
grep -Eq "^'?/live/vmlinuz([.-][^/]*)?'?$" "$iso_listing" || \
    fail "live kernel missing from ISO"
grep -Eq "^'?/live/initrd\.img([.-][^/]*)?'?$" "$iso_listing" || \
    fail "live initrd missing from ISO"

xorriso -osirrox on -indev "$iso" \
    -extract /live/filesystem.squashfs "$VERIFY_ROOT/filesystem.squashfs" \
    > /dev/null 2>> "$VERIFY_ROOT/xorriso.log" || fail "cannot extract SquashFS"
unsquashfs -ll "$VERIFY_ROOT/filesystem.squashfs" > "$VERIFY_ROOT/squashfs-files.txt" || \
    fail "cannot list SquashFS"
for path in \
    etc/chromium/policies/managed/sushida-os.json \
    etc/systemd/system/sushida-kiosk.service \
    etc/systemd/system/sushida-network-watch.service \
    usr/local/bin/sushida-launch \
    usr/local/bin/sushida-network-watch \
    usr/local/libexec/sushida-session \
    usr/share/sushida-os/offline.html; do
    grep -Eq "squashfs-root/${path}$" "$VERIFY_ROOT/squashfs-files.txt" || \
        fail "required image path missing: /$path"
done

echo "Artifact verification passed."
