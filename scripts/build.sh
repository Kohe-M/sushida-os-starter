#!/usr/bin/env bash
# Build the Debian live ISO and publish a verified four-file artifact set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
BUILD_ROOT="$PROJECT_ROOT/build"
BUILD_DIR="$BUILD_ROOT/live-build"
ARTIFACT_DIR="$PROJECT_ROOT/artifacts"
ISO_NAME="sushida-os-amd64.iso"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ "$EUID" -eq 0 ] || fail "ISO build must run as root inside the Debian builder"
for path in "$BUILD_ROOT" "$ARTIFACT_DIR"; do
    [ ! -L "$path" ] || fail "refusing symlinked repository path: $path"
    mkdir -p "$path"
done
for cmd in git jq lb mkfs.ext4 mktemp sha256sum sort tee truncate xorriso; do
    command -v "$cmd" > /dev/null 2>&1 || fail "required build command not found: $cmd"
done

BUILD_LOG="$BUILD_ROOT/iso-build.log"
[ ! -L "$BUILD_LOG" ] || fail "refusing symlinked build log: $BUILD_LOG"
: > "$BUILD_LOG"
exec > >(tee "$BUILD_LOG") 2>&1

git_status="$(git -C "$PROJECT_ROOT" status --porcelain --untracked-files=all)"
[ -z "$git_status" ] || \
    fail "release ISO build requires a clean Git worktree; commit source changes first"

STAGING="$(mktemp -d "$ARTIFACT_DIR/.build-staging.XXXXXX")"
chmod 0700 "$STAGING"
cleanup() {
    rm -rf -- "$STAGING"
}
trap cleanup EXIT INT TERM HUP

"$PROJECT_ROOT/live-build/auto/config"
"$PROJECT_ROOT/live-build/auto/build"

mapfile -t iso_candidates < <(
    find "$BUILD_DIR" -maxdepth 1 -type f \
        \( -name 'live-image-amd64.hybrid.iso' -o -name '*.hybrid.iso' \) \
        -print | LC_ALL=C sort -u
)
[ "${#iso_candidates[@]}" -eq 1 ] || \
    fail "expected exactly one live-build ISO, found ${#iso_candidates[@]}"
base_iso="$STAGING/.base.iso"
config_image="$STAGING/.sushida-config.ext4"
install -m 0600 "${iso_candidates[0]}" "$base_iso"
truncate -s 64M "$config_image"
mkfs.ext4 -q -F \
    -L SUSHIDA-CFG \
    -U 3b8c6880-2a56-4cb2-9a30-b7ac47fc29f1 \
    "$config_image"
xorriso \
    -indev "$base_iso" \
    -outdev "$STAGING/$ISO_NAME" \
    -boot_image any replay \
    -append_partition 3 0x83 "$config_image" \
    -commit
chmod 0644 "$STAGING/$ISO_NAME"
rm -f -- "$base_iso" "$config_image"

mapfile -t manifest_candidates < <(
    find "$BUILD_DIR" -maxdepth 2 -type f \
        \( -name 'live-image-amd64.packages' -o -name 'binary.packages' \
           -o -name 'chroot.packages.install' \) -print | LC_ALL=C sort -u
)
[ "${#manifest_candidates[@]}" -ge 1 ] || fail "live-build package manifest not found"
# Prefer the binary manifest, then the standard live-image manifest.
manifest_source=""
for preferred in binary.packages live-image-amd64.packages chroot.packages.install; do
    for candidate in "${manifest_candidates[@]}"; do
        if [ "$(basename "$candidate")" = "$preferred" ]; then
            manifest_source="$candidate"
            break 2
        fi
    done
done
[ -n "$manifest_source" ] || fail "no supported package manifest found"
LC_ALL=C sort -u "$manifest_source" > "$STAGING/package-manifest.txt"
[ -s "$STAGING/package-manifest.txt" ] || fail "package manifest is empty"

package_version() {
    awk -v package="$1" '$1 == package { print $2; exit }' \
        "$STAGING/package-manifest.txt"
}

chromium_version="$(package_version chromium)"
cage_version="$(package_version cage)"
[ -n "$chromium_version" ] || fail "Chromium version missing from package manifest"
[ -n "$cage_version" ] || fail "Cage version missing from package manifest"

iso_sha256="$(sha256sum "$STAGING/$ISO_NAME" | awk '{print $1}')"
printf '%s  %s\n' "$iso_sha256" "$ISO_NAME" > "$STAGING/SHA256SUMS"

git_commit="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD)"
git_dirty=false
build_timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
live_build_version="$(lb --version | head -n 1)"
# Tie the artifact set to the manifest it was built and verified against.
release_contract_sha256="$(sha256sum "$PROJECT_ROOT/contracts/release-contract.json" | awk '{print $1}')"
package_manifest_sha256="$(sha256sum "$STAGING/package-manifest.txt" | awk '{print $1}')"

jq -n \
    --argjson schema_version 1 \
    --arg release_contract_sha256 "$release_contract_sha256" \
    --arg package_manifest_sha256 "$package_manifest_sha256" \
    --arg git_commit "$git_commit" \
    --argjson git_dirty "$git_dirty" \
    --arg debian_release "trixie" \
    --arg build_timestamp "$build_timestamp" \
    --arg architecture "amd64" \
    --arg chromium_version "$chromium_version" \
    --arg cage_version "$cage_version" \
    --arg live_build_version "$live_build_version" \
    --arg iso_sha256 "$iso_sha256" \
    '{
        schema_version: $schema_version,
        release_contract_sha256: $release_contract_sha256,
        package_manifest_sha256: $package_manifest_sha256,
        git_commit: $git_commit,
        git_dirty: $git_dirty,
        debian_release: $debian_release,
        build_timestamp: $build_timestamp,
        architecture: $architecture,
        chromium_version: $chromium_version,
        cage_version: $cage_version,
        live_build_version: $live_build_version,
        iso_sha256: $iso_sha256
    }' > "$STAGING/build-info.json"

"$PROJECT_ROOT/scripts/verify-iso.sh" "$STAGING"

for file in "$ISO_NAME" SHA256SUMS package-manifest.txt build-info.json; do
    mv -f -- "$STAGING/$file" "$ARTIFACT_DIR/$file"
done

echo "Published verified artifacts in $ARTIFACT_DIR"

{
    printf 'BUILD_RESULT=success\n'
    printf 'BUILD_TIMESTAMP=%s\n' "$build_timestamp"
    printf 'GIT_COMMIT=%s\n' "$git_commit"
    printf 'ISO_SHA256=%s\n' "$iso_sha256"
    printf 'ARTIFACT=%s\n' "$ARTIFACT_DIR/$ISO_NAME"
} | tee -a "$BUILD_LOG"
