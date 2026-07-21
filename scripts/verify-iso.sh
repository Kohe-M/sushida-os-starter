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

for cmd in awk blkid cmp dd git grep jq mkdir sed sha256sum unsquashfs wc xorriso; do
    command -v "$cmd" > /dev/null 2>&1 || fail "required command not found: $cmd"
done

# The release contract is the manifest this verifier executes.
CONTRACT="$PROJECT_ROOT/contracts/release-contract.json"
if [ ! -f "$CONTRACT" ] || [ -L "$CONTRACT" ]; then
    fail "release contract not found: $CONTRACT"
fi
jq -e '.schema_version == 1' "$CONTRACT" > /dev/null || \
    fail "unsupported release contract schema"
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
    (.schema_version == 1) and
    (.release_contract_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
    (.package_manifest_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
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

# The artifact set must have been built against this exact manifest, and the
# published package manifest must be the one recorded at build time.
contract_sha="$(sha256sum "$CONTRACT" | awk '{print $1}')"
metadata_contract_sha="$(jq -r '.release_contract_sha256' "$resolved_dir/build-info.json")"
[ "$metadata_contract_sha" = "$contract_sha" ] || \
    fail "artifact was built against a different release contract"
manifest_sha="$(sha256sum "$resolved_dir/package-manifest.txt" | awk '{print $1}')"
metadata_manifest_sha="$(jq -r '.package_manifest_sha256' "$resolved_dir/build-info.json")"
[ "$metadata_manifest_sha" = "$manifest_sha" ] || \
    fail "package manifest does not match build metadata"

iso_scratch_init "$PROJECT_ROOT/build" "verify-artifacts" || \
    fail "verification scratch path already exists or cannot be created"
VERIFY_ROOT="$ISO_SCRATCH_ROOT"

iso="$resolved_dir/$ISO_NAME"
iso_listing="$VERIFY_ROOT/iso-files.txt"
iso_list_files "$iso" "$iso_listing" || \
    fail "cannot read ISO filesystem"
# Required ISO paths (iso-root region) come from the release contract.
# Literal paths are regex-escaped; regex entries carry their own pattern.
# Records are NUL-separated: TSV would re-escape backslashes in patterns.
while IFS= read -r -d '' req_path && \
      IFS= read -r -d '' req_pattern && \
      IFS= read -r -d '' req_match; do
    if [ "$req_match" = regex ]; then
        inner_re="${req_pattern#^}"
        inner_re="${inner_re%$}"
    else
        inner_re="$(printf '%s' "$req_path" | sed -e 's/[.[\*^$()+?{|]/\\&/g')"
    fi
    grep -Eq "^'?${inner_re}'?\$" "$iso_listing" || \
        fail "required ISO path missing: $req_path"
done < <(jq -j '.required_iso_paths[] | select(.region == "iso-root")
    | (.path + "\u0000" + (.path_pattern // "") + "\u0000"
       + (.match_type // "literal") + "\u0000")' "$CONTRACT")

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
# Required image paths (squashfs region) come from the release contract.
while IFS= read -r -d '' req_path; do
    grep -Fq "squashfs-root$req_path" "$VERIFY_ROOT/squashfs-files.txt" || \
        fail "required image path missing: $req_path"
done < <(jq -j '.required_iso_paths[] | select(.region == "squashfs")
    | (.path + "\u0000")' "$CONTRACT")

# Convert a contract octal mode (e.g. 0644) to the symbolic form printed by
# unsquashfs -ll so declared modes can be compared inside the image.
mode_to_symbolic() {
    local digits="${1#0}" digit out=""
    [ "${#digits}" -eq 3 ] || return 1
    while [ -n "$digits" ]; do
        digit="${digits%"${digits#?}"}"
        digits="${digits#?}"
        case "$digit" in
            0) out="${out}---" ;; 1) out="${out}--x" ;; 2) out="${out}-w-" ;;
            3) out="${out}-wx" ;; 4) out="${out}r--" ;; 5) out="${out}r-x" ;;
            6) out="${out}rw-" ;; 7) out="${out}rwx" ;;
            *) return 1 ;;
        esac
    done
    printf '%s' "$out"
}

# Mappings with current_verification "exact" are byte-compared against the
# tracked source tree, and their mode/owner/group inside the image must
# match the contract declaration.  Presence alone is insufficient for these
# files: a stale ISO built from an older worktree revision is rejected.
while IFS= read -r -d '' map_source && \
      IFS= read -r -d '' map_image && \
      IFS= read -r -d '' map_mode && \
      IFS= read -r -d '' map_owner && \
      IFS= read -r -d '' map_group; do
    src="$PROJECT_ROOT/$map_source"
    if [ ! -f "$src" ] || [ -L "$src" ]; then
        fail "mapping source missing or symlinked: $map_source"
    fi
    inner="${map_image#/}"
    # unsquashfs matches extract paths as globs; escape glob characters and
    # backslashes so the contract path is taken literally.
    inner_glob="$(printf '%s' "$inner" | sed -e 's/[\\*?[]/\\&/g')"
    extracted="$VERIFY_ROOT/exact$map_image"
    mkdir -p "$(dirname "$extracted")"
    squashfs_cat "$VERIFY_ROOT/filesystem.squashfs" "$inner_glob" "$extracted" || \
        fail "cannot extract from SquashFS: $map_image"
    cmp -s "$src" "$extracted" || fail "ISO contains stale content: $map_image"
    entry="$(grep -F "squashfs-root$map_image" "$VERIFY_ROOT/squashfs-files.txt" | head -n 1)"
    [ -n "$entry" ] || fail "cannot locate image entry: $map_image"
    symbolic="$(mode_to_symbolic "$map_mode")" || \
        fail "invalid contract mode for $map_image"
    [ "${entry%% *}" = "-$symbolic" ] || \
        fail "unexpected image mode for $map_image"
    [ "$(printf '%s\n' "$entry" | awk '{print $2}')" = "$map_owner/$map_group" ] || \
        fail "unexpected image owner for $map_image"
done < <(jq -j '.source_image_mappings[]
    | select(.region == "squashfs" and .current_verification == "exact")
    | (.source + "\u0000" + .image_path + "\u0000" + .mode + "\u0000"
       + .owner + "\u0000" + .group + "\u0000")' "$CONTRACT")

echo "Artifact verification passed."
