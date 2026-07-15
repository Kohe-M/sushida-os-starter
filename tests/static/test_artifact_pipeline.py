"""Static safety and completeness checks for build artifacts."""

import os
import stat
from pathlib import Path


BUILD = Path("scripts/build.sh")
VERIFY = Path("scripts/verify-iso.sh")
CLEAN = Path("scripts/clean.sh")
MAKEFILE = Path("Makefile")
DOCKERFILE = Path("builder/Dockerfile")


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


def test_build_info_contains_required_fields() -> None:
    text = BUILD.read_text()
    for field in (
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


def test_verify_checks_iso_and_squashfs_contents() -> None:
    text = VERIFY.read_text()
    assert "xorriso" in text
    assert "unsquashfs" in text
    for path in (
        "filesystem.squashfs",
        "sushida-os.json",
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-session",
        "offline.html",
    ):
        assert path in text


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
