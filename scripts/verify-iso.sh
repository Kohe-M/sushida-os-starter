#!/usr/bin/env bash
# Verify artifact checksums, metadata, manifest, and required ISO contents.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ARTIFACT_ROOT="$PROJECT_ROOT/artifacts"
ARTIFACT_DIR="${1:-$ARTIFACT_ROOT}"
ISO_NAME="sushida-os-amd64.iso"

# shellcheck source=scripts/lib/iso-extract.sh
. "$SCRIPT_DIR/lib/iso-extract.sh"

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

for cmd in awk blkid cmp dd git grep jq sha256sum unsquashfs wc xorriso; do
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

current_commit="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null)" || \
    fail "cannot determine current Git commit"
git_status="$(git -C "$PROJECT_ROOT" status --porcelain --untracked-files=all)"
[ -z "$git_status" ] || \
    fail "current Git worktree is dirty; commit source changes before verification"
metadata_commit="$(jq -r '.git_commit' "$resolved_dir/build-info.json")"
[ "$metadata_commit" = "$current_commit" ] || \
    fail "artifact was built from a different Git commit"
[ "$(jq -r '.git_dirty' "$resolved_dir/build-info.json")" = false ] || \
    fail "artifact metadata records a dirty Git worktree"

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

iso_scratch_init "$PROJECT_ROOT/build" "verify-artifacts" || \
    fail "verification scratch path already exists or cannot be created"
VERIFY_ROOT="$ISO_SCRATCH_ROOT"

iso="$resolved_dir/$ISO_NAME"
iso_listing="$VERIFY_ROOT/iso-files.txt"
iso_list_files "$iso" "$iso_listing" || \
    fail "cannot read ISO filesystem"
grep -Eq "^'?/live/filesystem\.squashfs'?$" "$iso_listing" || \
    fail "required ISO path missing: /live/filesystem.squashfs"
grep -Eq "^'?/live/vmlinuz([.-][^/]*)?'?$" "$iso_listing" || \
    fail "live kernel missing from ISO"
grep -Eq "^'?/live/initrd\.img([.-][^/]*)?'?$" "$iso_listing" || \
    fail "live initrd missing from ISO"
grep -Eq "^'?/boot/grub/grub\.cfg'?$" "$iso_listing" || \
    fail "required ISO path missing: /boot/grub/grub.cfg"
grep -Eq "^'?/isolinux/isolinux\.cfg'?$" "$iso_listing" || \
    fail "required ISO path missing: /isolinux/isolinux.cfg"
grep -Eq "^'?/isolinux/live\.cfg'?$" "$iso_listing" || \
    fail "required ISO path missing: /isolinux/live.cfg"

system_area="$VERIFY_ROOT/system-area.txt"
iso_report_system_area "$iso" "$system_area" || \
    fail "cannot inspect hybrid partition table"
grep -Eq '^MBR partition[[:space:]]+:[[:space:]]+3[[:space:]]+0x00[[:space:]]+0x83[[:space:]]+[0-9]+[[:space:]]+131072$' \
    "$system_area" || fail "missing fixed 64 MiB Linux config partition"
grep -Fq 'GPT partname local :   3  Appended3' "$system_area" || \
    fail "missing appended GPT config partition"
config_start="$(awk '$1 == "MBR" && $2 == "partition" && $3 == ":" && $4 == "3" {print $(NF-1)}' "$system_area")"
case "$config_start" in ''|*[!0-9]*) fail "invalid config partition start" ;; esac
dd if="$iso" of="$VERIFY_ROOT/sushida-config.ext4" bs=512 \
    skip="$config_start" count=131072 status=none
config_label="$(blkid -p -s LABEL -o value "$VERIFY_ROOT/sushida-config.ext4")" || \
    fail "cannot identify config filesystem"
[ "$config_label" = SUSHIDA-CFG ] || fail "unexpected config filesystem label"
config_type="$(blkid -p -s TYPE -o value "$VERIFY_ROOT/sushida-config.ext4")" || \
    fail "cannot identify config filesystem type"
[ "$config_type" = ext4 ] || fail "config filesystem is not ext4"

iso_extract_file "$iso" /live/filesystem.squashfs "$VERIFY_ROOT/filesystem.squashfs" || \
    fail "cannot extract SquashFS"
squashfs_list "$VERIFY_ROOT/filesystem.squashfs" "$VERIFY_ROOT/squashfs-files.txt" || \
    fail "cannot list SquashFS"
for path in \
    etc/chromium/policies/managed/sushida-os.json \
    etc/systemd/system/sushida-kiosk.service \
    etc/systemd/system/sushida-network-watch.service \
    etc/systemd/system/sushida-config-prepare.service \
    etc/systemd/system/sushida-wifi-setup.service \
    'etc/systemd/system/var-lib-sushida\x2dconfig.mount' \
    etc/polkit-1/rules.d/60-sushida-wifi-setup.rules \
    usr/local/bin/sushida-launch \
    usr/local/bin/sushida-network-watch \
    usr/local/libexec/sushida-session \
    usr/local/libexec/sushida-config-prepare \
    usr/local/libexec/sushida-wifi-setup \
    usr/share/sushida-os/offline.html; do
    grep -Fq "squashfs-root/$path" "$VERIFY_ROOT/squashfs-files.txt" || \
        fail "required image path missing: /$path"
done

# These files control the exact real-hardware failure mode of the on-device
# Wi-Fi UI. Presence alone is insufficient: reject a stale ISO built from an
# older worktree revision.
embedded_wifi="$VERIFY_ROOT/sushida-wifi-setup"
squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" \
    usr/local/libexec/sushida-wifi-setup "$embedded_wifi" || \
    fail "cannot extract Wi-Fi setup backend from SquashFS"
cmp -s \
    "$PROJECT_ROOT/live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup" \
    "$embedded_wifi" || fail "ISO contains a stale Wi-Fi setup backend"

embedded_wifi_service="$VERIFY_ROOT/sushida-wifi-setup.service"
squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" \
    etc/systemd/system/sushida-wifi-setup.service "$embedded_wifi_service" || \
    fail "cannot extract Wi-Fi setup service from SquashFS"
cmp -s \
    "$PROJECT_ROOT/live-build/config/includes.chroot/etc/systemd/system/sushida-wifi-setup.service" \
    "$embedded_wifi_service" || fail "ISO contains a stale Wi-Fi setup service"

embedded_config_prepare="$VERIFY_ROOT/sushida-config-prepare"
squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" \
    usr/local/libexec/sushida-config-prepare "$embedded_config_prepare" || \
    fail "cannot extract configuration prepare helper from SquashFS"
cmp -s \
    "$PROJECT_ROOT/live-build/config/includes.chroot/usr/local/libexec/sushida-config-prepare" \
    "$embedded_config_prepare" || fail "ISO contains a stale configuration prepare helper"

embedded_config_prepare_service="$VERIFY_ROOT/sushida-config-prepare.service"
squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" \
    etc/systemd/system/sushida-config-prepare.service "$embedded_config_prepare_service" || \
    fail "cannot extract configuration prepare service from SquashFS"
cmp -s \
    "$PROJECT_ROOT/live-build/config/includes.chroot/etc/systemd/system/sushida-config-prepare.service" \
    "$embedded_config_prepare_service" || fail "ISO contains a stale configuration prepare service"

embedded_mount="$VERIFY_ROOT/sushida-config.mount"
squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" \
    'etc/systemd/system/*config.mount' "$embedded_mount" || \
    fail "cannot extract configuration mount unit from SquashFS"
cmp -s \
    "$PROJECT_ROOT/live-build/config/includes.chroot/etc/systemd/system/var-lib-sushida\x2dconfig.mount" \
    "$embedded_mount" || fail "ISO contains a stale configuration mount unit"

echo "Artifact verification passed."
