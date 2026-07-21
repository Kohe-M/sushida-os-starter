#!/usr/bin/env bats
# End-to-end stale/tamper rejection tests for the manifest-driven verifier.
#
# A fixture repository (git-committed copy of the tracked production tree,
# the release contract, and the verifier) gets a fixture artifact set built
# from a *separate* squashfs input copy.  Tampering that copy produces a
# self-consistent artifact set (checksums and metadata all match) whose
# content nevertheless diverges from the tracked sources — exactly the
# stale-ISO case verification must reject.  Stages are exercised via the
# sourced function interface; verify_partitions needs a real hybrid-boot
# ISO and is exercised only for its rejection path.

setup() {
    command -v mksquashfs > /dev/null 2>&1 || skip "mksquashfs not available"
    command -v xorriso > /dev/null 2>&1 || skip "xorriso not available"
    command -v jq > /dev/null 2>&1 || skip "jq not available"

    REPO="$BATS_TEST_TMPDIR/fixture-repo"
    ROOT_COPY="$BATS_TEST_TMPDIR/root"
    mkdir -p "$REPO/scripts/lib" "$REPO/contracts" "$REPO/build" "$REPO/artifacts"
    cp scripts/verify-iso.sh "$REPO/scripts/"
    cp scripts/lib/iso-extract.sh "$REPO/scripts/lib/"
    cp contracts/release-contract.json "$REPO/contracts/"
    # Tracked production tree exactly as committed (modes preserved).
    git archive HEAD live-build/config/includes.chroot live-build/config/bootloaders \
        | tar -x -C "$REPO"
    printf 'artifacts/\nbuild/\n' > "$REPO/.gitignore"
    git -C "$REPO" init -q
    git -C "$REPO" -c user.email=fixture@test -c user.name=fixture add -A
    git -C "$REPO" -c user.email=fixture@test -c user.name=fixture commit -qm fixture

    # Separate squashfs input copy; tampering happens here, never in REPO.
    mkdir -p "$ROOT_COPY"
    cp -a "$REPO/live-build/config/includes.chroot/." "$ROOT_COPY/"
    export REPO ROOT_COPY
}

write_metadata() {
    local art="$REPO/artifacts"
    local iso_sha manifest_sha contract_sha commit
    iso_sha="$(sha256sum "$art/sushida-os-amd64.iso" | awk '{print $1}')"
    printf '%s  sushida-os-amd64.iso\n' "$iso_sha" > "$art/SHA256SUMS"
    manifest_sha="$(sha256sum "$art/package-manifest.txt" | awk '{print $1}')"
    contract_sha="$(sha256sum "$REPO/contracts/release-contract.json" | awk '{print $1}')"
    commit="$(git -C "$REPO" rev-parse HEAD)"
    jq -n \
        --argjson schema_version 1 \
        --argjson source_date_epoch 1753056000 \
        --arg release_contract_sha256 "$contract_sha" \
        --arg package_manifest_sha256 "$manifest_sha" \
        --arg git_commit "$commit" \
        --argjson git_dirty false \
        --arg debian_release trixie \
        --arg build_timestamp "2026-07-21T00:00:00Z" \
        --arg architecture amd64 \
        --arg chromium_version "131.0.0-1" \
        --arg cage_version "0.2.0-1" \
        --arg live_build_version "fixture 1.0" \
        --arg iso_sha256 "$iso_sha" \
        '{schema_version: $schema_version,
          source_date_epoch: $source_date_epoch,
          release_contract_sha256: $release_contract_sha256,
          package_manifest_sha256: $package_manifest_sha256,
          git_commit: $git_commit, git_dirty: $git_dirty,
          debian_release: $debian_release, build_timestamp: $build_timestamp,
          architecture: $architecture, chromium_version: $chromium_version,
          cage_version: $cage_version, live_build_version: $live_build_version,
          iso_sha256: $iso_sha256}' > "$art/build-info.json"
}

build_fixture() {
    local variant="${1:-default}"
    local stage="$BATS_TEST_TMPDIR/stage" art="$REPO/artifacts"
    rm -rf "$stage"
    mkdir -p "$stage/live" "$stage/boot/grub" "$stage/isolinux"
    mksquashfs "$ROOT_COPY" "$stage/live/filesystem.squashfs" \
        -all-root -no-progress -quiet > /dev/null 2>&1
    printf 'kernel\n' > "$stage/live/vmlinuz-fixture"
    printf 'initrd\n' > "$stage/live/initrd.img-fixture"
    if [ "$variant" != no-grub ]; then
        cp "$REPO/live-build/config/bootloaders/grub-pc/config.cfg" \
            "$stage/boot/grub/grub.cfg"
    fi
    cp "$REPO/live-build/config/bootloaders/isolinux/isolinux.cfg" "$stage/isolinux/"
    cp "$REPO/live-build/config/bootloaders/isolinux/live.cfg" "$stage/isolinux/"
    rm -f "$art/sushida-os-amd64.iso"
    xorriso -outdev "$art/sushida-os-amd64.iso" -map "$stage" / -commit \
        > /dev/null 2>&1
    if [ "$variant" = no-chromium ]; then
        printf 'cage 0.2.0-1\n' > "$art/package-manifest.txt"
    else
        printf 'cage 0.2.0-1\nchromium 131.0.0-1\n' > "$art/package-manifest.txt"
    fi
    write_metadata
}

# Run every stage except verify_partitions (a real hybrid-boot ISO is needed
# for its positive path; its rejection path has a dedicated test below).
run_verify() {
    run bash -c "cd '$REPO' && source scripts/verify-iso.sh \
        && verify_environment && verify_artifact_set && verify_checksums \
        && verify_metadata && verify_iso_root && verify_squashfs"
}

@test "pristine fixture artifact set passes every stage except partitions" {
    build_fixture
    run_verify
    [ "$status" -eq 0 ]
}

@test "one stale byte in the Chromium policy is rejected" {
    printf ' ' >> "$ROOT_COPY/etc/chromium/policies/managed/sushida-os.json"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"stale content: /etc/chromium/policies/managed/sushida-os.json"* ]]
}

@test "stale kiosk unit is rejected" {
    printf '# stale\n' >> "$ROOT_COPY/etc/systemd/system/sushida-kiosk.service"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"stale content: /etc/systemd/system/sushida-kiosk.service"* ]]
}

@test "stale Wi-Fi backend is rejected" {
    printf '# stale\n' >> "$ROOT_COPY/usr/local/libexec/sushida-wifi-setup"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"stale content: /usr/local/libexec/sushida-wifi-setup"* ]]
}

@test "missing navigation watcher is rejected" {
    rm "$ROOT_COPY/usr/local/bin/sushida-navigation-watch"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"required image path missing: /usr/local/bin/sushida-navigation-watch"* ]]
}

@test "mode change on the launcher is rejected" {
    chmod 0777 "$ROOT_COPY/usr/local/bin/sushida-launch"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"unexpected image mode for /usr/local/bin/sushida-launch"* ]]
}

@test "symlink replacement of the offline page is rejected" {
    rm "$ROOT_COPY/usr/share/sushida-os/offline.html"
    ln -s /etc/hostname "$ROOT_COPY/usr/share/sushida-os/offline.html"
    build_fixture
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"/usr/share/sushida-os/offline.html"* ]]
}

@test "missing bootloader config in the ISO is rejected" {
    build_fixture no-grub
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"required ISO path missing: /boot/grub/grub.cfg"* ]]
}

@test "metadata ISO checksum mismatch is rejected" {
    build_fixture
    jq '.iso_sha256 = ("0" * 64)' "$REPO/artifacts/build-info.json" \
        > "$REPO/artifacts/build-info.json.new"
    mv "$REPO/artifacts/build-info.json.new" "$REPO/artifacts/build-info.json"
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"metadata ISO checksum mismatch"* ]]
}

@test "package manifest tampering after build is rejected" {
    build_fixture
    printf 'extra-package 1.0\n' >> "$REPO/artifacts/package-manifest.txt"
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"package manifest does not match build metadata"* ]]
}

@test "missing required package is rejected" {
    build_fixture no-chromium
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"chromium missing from package manifest"* ]]
}

@test "metadata recording a different release contract is rejected" {
    # A contract edit in the worktree is already intercepted by the
    # clean-HEAD checks; this pins the hash cross-check itself.
    build_fixture
    jq '.release_contract_sha256 = ("0" * 64)' "$REPO/artifacts/build-info.json" \
        > "$REPO/artifacts/build-info.json.new"
    mv "$REPO/artifacts/build-info.json.new" "$REPO/artifacts/build-info.json"
    run_verify
    [ "$status" -ne 0 ]
    [[ "$output" == *"built against a different release contract"* ]]
}

@test "fixture ISO without hybrid partitions fails the partition stage" {
    build_fixture
    run bash -c "cd '$REPO' && source scripts/verify-iso.sh \
        && verify_environment && verify_artifact_set && verify_checksums \
        && verify_metadata && verify_iso_root && verify_partitions"
    [ "$status" -ne 0 ]
    [[ "$output" == *"config partition"* ]]
}

@test "executing the script never skips stages" {
    grep -qF 'if [ "${BASH_SOURCE[0]}" = "$0" ]; then' scripts/verify-iso.sh
    grep -qF 'verify_main' scripts/verify-iso.sh
    run grep -E 'SUSHIDA[A-Z_]*SKIP|VERIFY_SKIP' scripts/verify-iso.sh
    [ "$status" -ne 0 ]
}
