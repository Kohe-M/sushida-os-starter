import re
from pathlib import Path

DOCKERFILE = Path("builder/Dockerfile")
ENTRYPOINT = Path("builder/entrypoint.sh")
MAKEFILE = Path("Makefile")
DOCKERIGNORE = Path(".dockerignore")
CONTAINERIGNORE = Path(".containerignore")


def test_dockerfile_uses_debian_trixie() -> None:
    content = DOCKERFILE.read_text()
    assert "FROM debian:trixie" in content


def test_dockerfile_no_todo() -> None:
    assert "TODO" not in DOCKERFILE.read_text()


def test_dockerfile_includes_udevadm_for_flash_validation() -> None:
    content = DOCKERFILE.read_text()
    assert re.search(r"^\s*udev\s*\\$", content, re.MULTILINE)


def test_dockerfile_includes_ext4_config_image_tools() -> None:
    content = DOCKERFILE.read_text()
    assert re.search(r"^\s*e2fsprogs\s*\\$", content, re.MULTILINE)


def test_dockerfile_chmod_entrypoint() -> None:
    content = DOCKERFILE.read_text()
    assert re.search(r"chmod\s+0?755\s+/entrypoint\.sh", content), (
        "Dockerfile must set 0755 on /entrypoint.sh"
    )


def test_dockerfile_entrypoint_exec_form() -> None:
    content = DOCKERFILE.read_text()
    assert re.search(r'ENTRYPOINT\s+\["/entrypoint\.sh"\]', content), (
        "ENTRYPOINT must use exec form: [\"/entrypoint.sh\"]"
    )


def test_dockerfile_cmd_bash_default() -> None:
    content = DOCKERFILE.read_text()
    assert re.search(r'CMD\s+\["bash"\]', content), (
        "CMD must provide bash as default command"
    )


def test_entrypoint_no_todo() -> None:
    assert "TODO" not in ENTRYPOINT.read_text()


def test_entrypoint_no_exit_one() -> None:
    content = ENTRYPOINT.read_text()
    assert "exit 1" not in content


def test_entrypoint_no_eval() -> None:
    assert "eval" not in ENTRYPOINT.read_text()


def test_entrypoint_has_shebang() -> None:
    content = ENTRYPOINT.read_text()
    assert content.startswith("#!/usr/bin/env bash")


def test_entrypoint_uses_exec_star_at() -> None:
    content = ENTRYPOINT.read_text()
    assert 'exec "$@"' in content, (
        "entrypoint must contain exec \"$@\" to pass arguments through"
    )


def test_entrypoint_no_bash_special_case() -> None:
    """Reject any branch that singles out 'bash' to discard further arguments."""
    content = ENTRYPOINT.read_text()
    assert '"$1" = "bash"' not in content, (
        "entrypoint must not special-case '$1 = bash' to drop remaining args"
    )


def test_makefile_builder_uses_container_engine() -> None:
    content = MAKEFILE.read_text()
    assert "$(CONTAINER_ENGINE)" in content


def test_makefile_builder_specifies_dockerfile() -> None:
    content = MAKEFILE.read_text()
    assert "-f builder/Dockerfile" in content


def test_makefile_adds_required_podman_cgroup_manager() -> None:
    content = MAKEFILE.read_text()
    assert "--cgroup-manager=cgroupfs" in content
    assert "CONTAINER_ENGINE_ARGS" in content


def test_builder_context_excludes_generated_state_and_local_secrets() -> None:
    for path in (DOCKERIGNORE, CONTAINERIGNORE):
        content = path.read_text()
        assert "build/" in content or "**" in content
        assert "artifacts/" in content or "**" in content
        assert ".git" in content or "**" in content
        assert "local/" in content or "**" in content
        assert "!builder/Dockerfile" in content
        assert "!builder/entrypoint.sh" in content
