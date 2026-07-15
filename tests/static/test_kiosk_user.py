import subprocess
from pathlib import Path

HOOK = Path(
    "live-build/config/hooks/live/010-create-kiosk-user.hook.chroot"
)
TMPFILES = Path(
    "live-build/config/includes.chroot/usr/lib/tmpfiles.d/sushida-os.conf"
)

ALLOWED_GROUPS = {"audio", "video", "render", "input"}


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ── hook: no leftover placeholders ──────────────────────────────────────────


def test_hook_no_todo() -> None:
    assert "TODO" not in HOOK.read_text()


def test_hook_no_eval() -> None:
    assert "eval" not in HOOK.read_text()


# ── hook: account name ──────────────────────────────────────────────────────


def test_hook_account_name_is_kiosk() -> None:
    assert 'KIOSK_USER="kiosk"' in HOOK.read_text()


# ── hook: system account and no home ────────────────────────────────────────


def test_hook_uses_system_account() -> None:
    assert "--system" in HOOK.read_text()


def test_hook_no_create_home() -> None:
    assert "--no-create-home" in HOOK.read_text()


def test_home_is_nonexistent() -> None:
    assert "/nonexistent" in HOOK.read_text()


def test_hook_shell_is_nologin() -> None:
    assert "/usr/sbin/nologin" in HOOK.read_text()


# ── hook: primary group creation ────────────────────────────────────────────


def test_hook_creates_kiosk_group() -> None:
    content = HOOK.read_text()
    assert "groupadd --system" in content
    assert "getent group" in content


def test_hook_rejects_gid_zero() -> None:
    content = HOOK.read_text()
    assert "GID" in content and "eq 0" in content


def test_hook_both_commands_use_gid() -> None:
    """Both useradd (new) and usermod (existing) must specify --gid."""
    content = HOOK.read_text()
    # useradd --gid spans two lines; check both words exist in the file.
    assert 'useradd' in content
    assert 'usermod' in content
    # --gid "$KIOSK_USER" appears twice (once per command)
    count = content.count('--gid "$KIOSK_USER"')
    assert count == 2, (
        f"Expected --gid \"$KIOSK_USER\" twice (useradd + usermod), "
        f"found {count}"
    )


# ── hook: supplemental group pre-validation ─────────────────────────────────


def test_hook_validates_supplemental_groups_exist() -> None:
    content = HOOK.read_text()
    assert "getent group" in content
    assert "does not exist" in content


def test_hook_no_unquoted_command_substitution_for_loop() -> None:
    """The group loop must not use unquoted $(echo | tr)."""
    content = HOOK.read_text()
    # ShellCheck SC2043 flags unquoted command substitution in for loops
    assert '$(echo' not in content
    assert '$(tr' not in content


def test_hook_uses_read_array() -> None:
    """The group split must use IFS read -r -a."""
    content = HOOK.read_text()
    assert 'read -r -a' in content
    assert 'IFS' in content


def test_hook_array_expansion_quoted() -> None:
    """The array must be expanded with "${...[@]}" quotes."""
    content = HOOK.read_text()
    assert '"${KIOSK_GROUP_ARRAY[@]}"' in content


def test_hook_supplemental_groups_are_allowed_set() -> None:
    """KIOSK_GROUPS must equal exactly the allowed set."""
    content = HOOK.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if "KIOSK_GROUPS" in stripped and "=" in stripped:
            value = stripped.split("=", 1)[1].strip().strip('"')
            groups = set(value.split(","))
            assert groups == ALLOWED_GROUPS, (
                f"KIOSK_GROUPS = {groups}, expected {ALLOWED_GROUPS}"
            )
            return
    raise AssertionError("KIOSK_GROUPS assignment not found")


def test_hook_no_prohibited_supplemental_groups() -> None:
    """None of the prohibited group names appear in a group assignment."""
    content = HOOK.read_text()
    prohibited = {
        "sudo", "adm", "wheel", "root", "disk", "tty", "kmem",
        "shadow", "systemd-journal", "netdev",
    }
    # Extract the value of KIOSK_GROUPS and verify it contains none
    # of the prohibited groups.
    for line in content.splitlines():
        stripped = line.strip()
        if "KIOSK_GROUPS" in stripped and "=" in stripped:
            value = stripped.split("=", 1)[1].strip().strip('"')
            groups = set(value.split(","))
            found = groups & prohibited
            assert not found, f"Prohibited group(s) in KIOSK_GROUPS: {found}"
            return
    raise AssertionError("KIOSK_GROUPS assignment not found")


# ── hook: password disabled / locked ────────────────────────────────────────


def test_hook_password_lock() -> None:
    content = HOOK.read_text()
    assert "passwd -l" in content


def test_hook_password_lock_not_silent() -> None:
    """passwd -l must not be silenced with > /dev/null."""
    content = HOOK.read_text()
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "passwd -l" in line:
            assert "> /dev/null" not in line, \
                f"passwd -l must not be silenced: {line}"


def test_hook_no_direct_passwd_edit() -> None:
    assert '/etc/passwd' not in HOOK.read_text()
    assert '/etc/shadow' not in HOOK.read_text()


# ── hook: UID 0 rejection ──────────────────────────────────────────────────


def test_hook_rejects_uid_zero() -> None:
    content = HOOK.read_text()
    assert "UID" in content and "eq 0" in content


# ── hook: idempotent ────────────────────────────────────────────────────────


def test_hook_handles_existing_user() -> None:
    assert "getent passwd" in HOOK.read_text()


# ── hook: executable mode in git index ──────────────────────────────────────


def test_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/010-create-kiosk-user.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"


# ── tmpfiles configuration ──────────────────────────────────────────────────


def test_tmpfiles_exists() -> None:
    assert TMPFILES.is_file()


def test_tmpfiles_exact_paths() -> None:
    content = TMPFILES.read_text()
    paths = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        assert len(fields) >= 7, f"Expected at least 7 fields, got {len(fields)}"
        paths.append(fields[1])
    expected = {
        "/run/sushida-os",
        "/run/sushida-os/home",
        "/run/sushida-os/chromium",
        "/run/sushida-os/cache",
        "/run/sushida-os/tmp",
        "/run/sushida-os/downloads",
        "/run/sushida-os/xdg-runtime",
    }
    assert set(paths) == expected, f"Unexpected runtime paths: {paths}"


def test_tmpfiles_parent_mode_0750() -> None:
    content = TMPFILES.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if fields[1] == "/run/sushida-os":
            assert fields[2] == "0750", f"Expected 0750 for parent: {line}"


def test_tmpfiles_home_mode_0700() -> None:
    content = TMPFILES.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if fields[1] == "/run/sushida-os/home":
            assert fields[2] == "0700", f"Expected 0700 for home: {line}"


def test_tmpfiles_ownership() -> None:
    content = TMPFILES.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        assert fields[3] == "kiosk", f"Owner must be kiosk: {line}"
        assert fields[4] == "kiosk", f"Group must be kiosk: {line}"
