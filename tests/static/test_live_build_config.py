import subprocess
from pathlib import Path

AUTO_CONFIG = Path("live-build/auto/config")
AUTO_BUILD = Path("live-build/auto/build")
AUTO_CLEAN = Path("live-build/auto/clean")
ALL_AUTO = [AUTO_CONFIG, AUTO_BUILD, AUTO_CLEAN]
MAKEFILE = Path("Makefile")


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ── no leftover placeholders ────────────────────────────────────────────────


def test_auto_config_no_todo() -> None:
    assert "TODO" not in AUTO_CONFIG.read_text()


def test_auto_build_no_todo() -> None:
    assert "TODO" not in AUTO_BUILD.read_text()


def test_auto_clean_no_todo() -> None:
    assert "TODO" not in AUTO_CLEAN.read_text()


# ── safe scripting ──────────────────────────────────────────────────────────


def test_auto_scripts_no_eval() -> None:
    for path in ALL_AUTO:
        assert "eval" not in path.read_text(), f"eval found in {path}"


def test_auto_scripts_pass_arguments() -> None:
    for path in (AUTO_CONFIG, AUTO_BUILD):
        assert '"$@"' in path.read_text(), f'{path} missing "$@" argument forwarding'


# ── path derivation (BASH_SOURCE / PROJECT_ROOT / BUILD_ROOT) ───────────────


def test_auto_scripts_use_bash_source() -> None:
    for path in ALL_AUTO:
        content = path.read_text()
        assert "BASH_SOURCE" in content, f"{path} must use BASH_SOURCE"
        assert "PROJECT_ROOT" in content, f"{path} must derive PROJECT_ROOT"


def test_auto_scripts_define_build_root() -> None:
    for path in ALL_AUTO:
        content = path.read_text()
        assert 'BUILD_ROOT="$PROJECT_ROOT/build"' in content or \
               "BUILD_ROOT=$PROJECT_ROOT/build" in content, \
               f"{path} must define BUILD_ROOT"


def test_auto_scripts_use_absolute_build_dir() -> None:
    for path in (AUTO_CONFIG, AUTO_BUILD):
        content = path.read_text()
        assert 'BUILD_DIR="$RESOLVED_BUILD_ROOT/' in content, \
               f"{path} BUILD_DIR must derive from RESOLVED_BUILD_ROOT"


# ── BUILD_ROOT symlink rejection (config + build) ───────────────────────────


def test_auto_config_rejects_symlinked_build_root() -> None:
    content = AUTO_CONFIG.read_text()
    assert '-L "$BUILD_ROOT"' in content, \
        "auto/config must reject symlinked BUILD_ROOT with -L check"
    assert "symlink" in content


def test_auto_config_resolves_build_root() -> None:
    content = AUTO_CONFIG.read_text()
    assert "RESOLVED_BUILD_ROOT" in content
    assert "EXPECTED_BUILD_ROOT" in content
    assert "pwd -P" in content or 'pwd -P' in content


def test_auto_build_rejects_symlinked_build_root() -> None:
    content = AUTO_BUILD.read_text()
    assert '-L "$BUILD_ROOT"' in content, \
        "auto/build must reject symlinked BUILD_ROOT with -L check"
    assert "symlink" in content


def test_auto_build_resolves_build_root() -> None:
    content = AUTO_BUILD.read_text()
    assert "RESOLVED_BUILD_ROOT" in content
    assert "EXPECTED_BUILD_ROOT" in content
    assert "pwd -P" in content or 'pwd -P' in content


# ── live-build/auto/config specifics ────────────────────────────────────────


def test_auto_config_debian_trixie() -> None:
    assert "--distribution trixie" in AUTO_CONFIG.read_text()


def test_auto_config_amd64() -> None:
    assert "--architectures amd64" in AUTO_CONFIG.read_text()


def test_auto_config_binary_images_iso_hybrid() -> None:
    assert "--binary-images iso-hybrid" in AUTO_CONFIG.read_text()


def test_auto_config_source_false() -> None:
    assert "--source false" in AUTO_CONFIG.read_text()


def test_auto_config_disables_implicit_recommends() -> None:
    assert "--apt-recommends false" in AUTO_CONFIG.read_text()


def test_auto_config_uses_only_explicit_firmware_packages() -> None:
    content = AUTO_CONFIG.read_text()
    assert "--firmware-binary false" in content
    assert "--firmware-chroot false" in content


def test_auto_config_archive_areas() -> None:
    assert "non-free-firmware" in AUTO_CONFIG.read_text()


def test_auto_config_noauto() -> None:
    content = AUTO_CONFIG.read_text()
    assert "noauto" in content
    assert "--no-auto" not in content


def test_auto_config_copies_only_tracked_config_files() -> None:
    content = AUTO_CONFIG.read_text()
    assert "copy_tracked_tree \"live-build/config\"" in content
    assert 'git -C "$PROJECT_ROOT" ls-files -z' in content
    assert "cp -p --" in content
    assert "cp -a" not in content


def test_auto_config_copies_only_tracked_auto_files() -> None:
    content = AUTO_CONFIG.read_text()
    assert "copy_tracked_tree \"live-build/auto\"" in content
    assert 'git -C "$PROJECT_ROOT" ls-files -z' in content
    assert "cp -p --" in content
    assert "cp -a" not in content


def test_auto_config_no_symlinks() -> None:
    assert "ln -s" not in AUTO_CONFIG.read_text()


def test_auto_config_build_dir_safety_check() -> None:
    content = AUTO_CONFIG.read_text()
    assert "TARGET=" in content
    assert "EXPECTED=" in content
    assert 'rm -rf --' in content


def test_auto_config_marker_after_lb_config() -> None:
    content = AUTO_CONFIG.read_text()
    config_line = next(i for i, line in enumerate(content.splitlines())
                       if "lb config" in line)
    marker_line = next(i for i, line in enumerate(content.splitlines())
                       if ".configured" in line)
    assert marker_line > config_line, \
        ".configured marker must be created after lb config"


# ── live-build/auto/build specifics ─────────────────────────────────────────


def test_auto_build_noauto() -> None:
    content = AUTO_BUILD.read_text()
    assert "noauto" in content
    assert "--no-auto" not in content


def test_auto_build_checks_config_and_marker() -> None:
    content = AUTO_BUILD.read_text()
    assert 'BUILD_DIR/config' in content
    assert '.configured' in content


def test_auto_build_rejects_symlinked_build_dir() -> None:
    content = AUTO_BUILD.read_text()
    assert '-L "$BUILD_DIR"' in content, \
        "auto/build must reject symlinked BUILD_DIR with -L check"
    assert "Build directory is a symlink" in content


def test_auto_build_resolves_build_dir() -> None:
    content = AUTO_BUILD.read_text()
    assert "RESOLVED_BUILD_DIR" in content
    assert "EXPECTED_BUILD_DIR" in content


def test_auto_build_resolve_before_marker() -> None:
    """RESOLVED_BUILD_DIR comparison must precede .configured check."""
    content = AUTO_BUILD.read_text()
    lines = content.splitlines()
    resolve_line = next(i for i, line in enumerate(lines)
                        if "RESOLVED_BUILD_DIR" in line)
    marker_line = next(i for i, line in enumerate(lines)
                       if ".configured" in line)
    assert resolve_line < marker_line, \
        "BUILD_DIR resolution must be checked before .configured"


# ── live-build/auto/clean specifics ─────────────────────────────────────────


def test_auto_clean_safety_check() -> None:
    content = AUTO_CLEAN.read_text()
    assert "TARGET=" in content
    assert "EXPECTED=" in content


def test_auto_clean_uses_dash_dash() -> None:
    assert "rm -rf --" in AUTO_CLEAN.read_text()


def test_auto_clean_does_not_target_artifacts() -> None:
    assert "artifacts" not in AUTO_CLEAN.read_text()


def test_auto_clean_does_not_target_local() -> None:
    assert "local" not in AUTO_CLEAN.read_text()


def test_auto_clean_handles_missing_dir() -> None:
    assert "Nothing to clean" in AUTO_CLEAN.read_text()


# ── Makefile ────────────────────────────────────────────────────────────────


def test_makefile_configure_calls_auto_config() -> None:
    assert "./live-build/auto/config" in MAKEFILE.read_text()


# ── file mode (git index) ───────────────────────────────────────────────────


def test_auto_scripts_are_executable() -> None:
    entries = _git_ls_files_stage("live-build/auto/")
    assert len(entries) == 3, f"Expected 3 auto scripts, got {len(entries)}"
    for entry in entries:
        mode = entry.split()[0]
        assert mode == "100755", f"Expected 100755, got {mode}: {entry}"
