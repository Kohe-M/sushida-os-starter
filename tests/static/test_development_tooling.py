"""Static checks for the development tooling layer.

These tests inspect the Makefile, CI workflow, wrapper scripts, and
documentation to ensure the development environment contract is consistent.
No runtime behaviour is verified here.
"""

from pathlib import Path


MAKEFILE = Path("Makefile")
CI_WORKFLOW = Path(".github/workflows/ci.yml")
CONTAINER_RUN = Path("scripts/container-run.sh")
DOCTOR = Path("scripts/doctor.sh")
SHELLCHECK_TARGETS = Path("scripts/shellcheck-targets.sh")
BUILD_DOCS = Path("docs/build.md")
README = Path("README.md")


# ── Makefile targets ─────────────────────────────────────────────────────


def test_existing_make_targets_preserved() -> None:
    text = MAKEFILE.read_text()
    for target in (
        "builder", "configure", "iso", "test", "test-static", "test-shell",
        "test-qemu", "test-qemu-boot", "test-qemu-runtime",
        "test-qemu-powerdown", "qemu", "verify", "clean", "distclean",
    ):
        assert f"{target}:" in text, f"target {target} is missing"


def test_new_make_targets_added() -> None:
    text = MAKEFILE.read_text()
    for target in (
        "help", "doctor", "doctor-build", "doctor-qemu", "ci",
        "container-test", "container-shell", "container-configure",
        "container-iso", "container-verify",
    ):
        assert f"{target}:" in text, f"target {target} is missing"


def test_ci_target_includes_test_and_git_diff() -> None:
    text = MAKEFILE.read_text()
    # ci expands to test-static + test-shell + git diff
    assert "ci: test-static test-shell" in text or "ci: test-static test-shell" in text
    # Check that git diff --check is called
    assert "git diff --check" in text


def test_test_static_uses_strict_flags() -> None:
    text = MAKEFILE.read_text()
    assert "--strict-markers" in text
    assert "-ra" in text


# ── CI workflow ──────────────────────────────────────────────────────────


def test_ci_workflow_exists() -> None:
    assert CI_WORKFLOW.is_file()


def test_ci_workflow_no_privileged_or_iso_or_qemu() -> None:
    text = CI_WORKFLOW.read_text()
    assert "privileged" not in text
    assert "make iso" not in text
    assert "make test-qemu" not in text
    assert "make qemu" not in text
    assert "flash.sh" not in text


def test_ci_workflow_calls_make_ci() -> None:
    text = CI_WORKFLOW.read_text()
    assert "make ci" in text


def test_ci_workflow_permissions_read_only() -> None:
    text = CI_WORKFLOW.read_text()
    assert "contents: read" in text or "contents: read" in text


# ── Container run wrapper ────────────────────────────────────────────────


def test_container_run_privilege_boundary() -> None:
    text = CONTAINER_RUN.read_text()
    assert '"iso"' in text
    assert '--privileged' in text
    assert 'PRIVILEGED=false' in text or 'false' in text


def test_container_run_rejects_unknown_mode() -> None:
    text = CONTAINER_RUN.read_text()
    assert "unknown mode" in text


def test_container_run_sets_python_no_bytes() -> None:
    text = CONTAINER_RUN.read_text()
    assert "PYTHONDONTWRITEBYTECODE=1" in text


def test_container_run_uses_host_uid_gid_for_test() -> None:
    text = CONTAINER_RUN.read_text()
    assert 'id -u' in text
    assert 'id -g' in text


def test_container_run_verifies_repository_root_is_not_symlink() -> None:
    text = CONTAINER_RUN.read_text()
    assert "symlink" in text


# ── Doctor ───────────────────────────────────────────────────────────────


def test_doctor_has_test_build_qemu_profiles() -> None:
    text = DOCTOR.read_text()
    assert "test|build|qemu)" in text


def test_doctor_no_file_modification() -> None:
    text = DOCTOR.read_text()
    for dangerous in ("mkfs", "dd ", "partition", "flash"):
        assert dangerous not in text
    # No write operations to repository files
    assert "write_bytes" not in text
    assert "os.replace" not in text


def test_doctor_output_contains_name_value() -> None:
    text = DOCTOR.read_text()
    assert "PASS" in text
    assert "FAIL" in text
    assert "WARN" in text


# ── ShellCheck targets ───────────────────────────────────────────────────


def test_shellcheck_targets_includes_bats_and_hook() -> None:
    text = SHELLCHECK_TARGETS.read_text()
    assert "*.bats" in text
    assert "*.hook.chroot" in text
    assert "live-build/auto/*" in text
    assert "*.sh" in text


# ── Documentation ────────────────────────────────────────────────────────


def test_build_docs_mentions_developer_targets() -> None:
    text = BUILD_DOCS.read_text()
    for target in ("make doctor", "make builder", "make container-test", "make ci", "make container-iso"):
        assert target in text


def test_readme_mentions_developer_workflow() -> None:
    text = README.read_text()
    for target in ("make doctor", "make builder", "make container-test", "make ci"):
        assert target in text
