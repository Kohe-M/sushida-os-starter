"""Static safety and completeness checks for build artifacts."""

import json
import os
import stat
from pathlib import Path


BUILD = Path("scripts/build.sh")
VERIFY = Path("scripts/verify-iso.sh")
ISO_LIB = Path("scripts/lib/iso-extract.sh")
CLEAN = Path("scripts/clean.sh")
MAKEFILE = Path("Makefile")
DOCKERFILE = Path("builder/Dockerfile")


def _verify_text() -> str:
    """Verifier implementation: entry script + sourced extraction library."""
    return VERIFY.read_text() + "\n" + ISO_LIB.read_text()


def test_artifact_scripts_exist_and_are_executable() -> None:
    for path in (BUILD, VERIFY, CLEAN):
        assert path.is_file()
        assert path.stat().st_mode & stat.S_IXUSR
        assert os.access(path, os.X_OK)


def test_scripts_use_strict_mode_without_eval() -> None:
    for path in (BUILD, VERIFY, CLEAN):
        text = path.read_text()
        assert "set -euo pipefail" in text
        assert "eval" not in text
        assert "TODO" not in text


def test_build_produces_exact_required_artifacts() -> None:
    text = BUILD.read_text()
    for name in (
        "sushida-os-amd64.iso",
        "SHA256SUMS",
        "package-manifest.txt",
        "build-info.json",
    ):
        assert name in text
    assert 'mktemp -d "$ARTIFACT_DIR/.build-staging.XXXXXX"' in text
    assert "verify-iso.sh" in text
    assert 'BUILD_LOG="$BUILD_ROOT/iso-build.log"' in text
    assert 'BUILD_RESULT=success' in text
    assert text.index('echo "Published verified artifacts in $ARTIFACT_DIR"') < text.index(
        "BUILD_RESULT=success"
    )


def test_build_info_contains_required_fields() -> None:
    text = BUILD.read_text()
    for field in (
        "schema_version",
        "release_contract_sha256",
        "package_manifest_sha256",
        "git_commit",
        "debian_release",
        "build_timestamp",
        "architecture",
        "chromium_version",
        "cage_version",
        "live_build_version",
        "iso_sha256",
    ):
        assert field in text
    assert "git_dirty=false" in text


def test_build_uses_live_build_output_and_manifest() -> None:
    text = BUILD.read_text()
    assert "live-build/auto/config" in text
    assert "live-build/auto/build" in text
    assert "live-image-amd64.hybrid.iso" in text
    assert "binary.packages" in text
    assert "chroot.packages.install" in text


def test_verify_checks_checksum_metadata_and_manifest() -> None:
    text = VERIFY.read_text()
    assert "sha256sum --check --strict" in text
    assert "jq -e" in text
    assert "metadata ISO checksum mismatch" in text
    assert "package-manifest.txt" in text
    assert "chromium" in text and "cage" in text
    assert "artifact was built from a different Git commit" in text
    assert "dirty Git worktree" in text
    assert 'status --porcelain --untracked-files=all' in text
    assert "current Git worktree is dirty" in text
    # Schema-versioned metadata cross-checks: the artifact set must be tied
    # to the exact release contract and the published package manifest.
    assert "(.schema_version == 1)" in text
    assert "artifact was built against a different release contract" in text
    assert "package manifest does not match build metadata" in text


def test_verify_checks_iso_and_squashfs_contents() -> None:
    text = _verify_text()
    assert "xorriso" in text
    assert "-find / -type f -exec echo" in text
    assert "-find / -type f -print" not in text
    assert "unsquashfs" in text
    assert "filesystem.squashfs" in text
    assert "SUSHIDA-CFG" in text
    # The required path lists live in the release contract; the verifier
    # loops over both regions instead of repeating path literals.
    assert "release-contract.json" in text
    assert 'select(.region == "iso-root")' in text
    assert 'select(.region == "squashfs")' in text
    contract = json.loads(Path("contracts/release-contract.json").read_text())
    squashfs_paths = {
        entry["path"] for entry in contract["required_iso_paths"]
        if entry["region"] == "squashfs"
    }
    for path in (
        "/etc/chromium/policies/managed/sushida-os.json",
        "/etc/systemd/system/sushida-kiosk.service",
        "/etc/systemd/system/sushida-network-watch.service",
        "/etc/systemd/system/sushida-wifi-setup.service",
        "/etc/systemd/system/sushida-config-prepare.service",
        "/usr/local/libexec/sushida-session",
        "/usr/local/libexec/sushida-config-prepare",
        "/usr/local/libexec/sushida-wifi-setup",
        "/usr/share/sushida-os/offline.html",
    ):
        assert path in squashfs_paths


def test_verify_rejects_stale_wifi_runtime_files() -> None:
    text = _verify_text()
    assert "cmp -s" in text
    assert "ISO contains stale content" in text
    assert "unsquashfs -cat" in text
    # Exact verification is contract-driven; the historically byte-compared
    # Wi-Fi/config files must stay declared exact in the manifest.
    assert '.current_verification == "exact"' in text
    contract = json.loads(Path("contracts/release-contract.json").read_text())
    exact_paths = {
        mapping["image_path"]
        for mapping in contract["source_image_mappings"]
        if mapping["current_verification"] == "exact"
    }
    for path in (
        "/usr/local/libexec/sushida-wifi-setup",
        "/etc/systemd/system/sushida-wifi-setup.service",
        "/usr/local/libexec/sushida-config-prepare",
        "/etc/systemd/system/sushida-config-prepare.service",
        "/etc/systemd/system/var-lib-sushida\\x2dconfig.mount",
    ):
        assert path in exact_paths
    # Declared mode/owner/group are enforced inside the image for exact files.
    assert "mode_to_symbolic" in text
    assert "unexpected image owner" in text


def test_verify_restricts_selected_directory() -> None:
    text = VERIFY.read_text()
    assert "outside the repository artifact root" in text
    assert '"$resolved_root"/.build-staging.*' in text


def test_cleanup_uses_only_fixed_repository_roots() -> None:
    text = CLEAN.read_text()
    assert 'BUILD_ROOT="$PROJECT_ROOT/build"' in text
    assert 'ARTIFACT_ROOT="$PROJECT_ROOT/artifacts"' in text
    assert "local/" not in text
    assert "/etc" not in text
    assert "git clean" not in text
    assert "rm -rf -- \"$PROJECT_ROOT\"" not in text


def test_clean_and_distclean_are_separate() -> None:
    text = CLEAN.read_text()
    assert "clean|distclean" in text
    assert 'if [ "$MODE" = "distclean" ]' in text
    assert "sushida-os-amd64.iso" in text


def test_make_targets_call_real_scripts() -> None:
    text = MAKEFILE.read_text()
    assert "iso:\n\t./scripts/build.sh" in text
    assert "verify:\n\t./scripts/verify-iso.sh" in text
    assert "clean:\n\t./scripts/clean.sh clean" in text
    assert "distclean:\n\t./scripts/clean.sh distclean" in text


def test_builder_has_iso_generation_and_inspection_tools() -> None:
    text = DOCKERFILE.read_text()
    for package in (
        "debootstrap",
        "isolinux",
        "grub-efi-amd64-bin",
        "grub-pc-bin",
        "mtools",
        "squashfs-tools",
        "xorriso",
    ):
        assert package in text
