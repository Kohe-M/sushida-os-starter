import subprocess
from pathlib import Path

LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
FORBIDDEN_PREFIXES = {
    "--no-sandbox",
    "--disable-gpu",
    "--disable-webgl",
    "--remote-debugging",
}


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _args_array() -> list[str]:
    """Extract CHROMIUM_ARGS array entries from the launcher."""
    content = LAUNCHER.read_text()
    in_array = False
    args: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if "CHROMIUM_ARGS=(" in stripped:
            in_array = True
            continue
        if in_array:
            if stripped == ")":
                break
            if stripped.startswith("#"):
                continue
            args.append(stripped)
    return args


# ── basic structure ─────────────────────────────────────────────────────────


def test_launcher_no_todo() -> None:
    assert "TODO" not in LAUNCHER.read_text()


def test_launcher_strict_mode() -> None:
    assert "set -euo pipefail" in LAUNCHER.read_text()


def test_launcher_no_eval() -> None:
    assert "eval" not in LAUNCHER.read_text()


def test_launcher_no_source() -> None:
    content = LAUNCHER.read_text()
    assert "source " not in content
    assert ". /" not in content


# ── test mode guard ─────────────────────────────────────────────────────────


def test_test_mode_guard() -> None:
    content = LAUNCHER.read_text()
    assert "SUSHIDA_OS_TEST_MODE" in content


def test_production_paths_fixed() -> None:
    content = LAUNCHER.read_text()
    assert "/etc/sushida-os/config.env" in content
    assert "/run/sushida-os" in content


# ── config parser ───────────────────────────────────────────────────────────


def test_parser_single_equals_split() -> None:
    content = LAUNCHER.read_text()
    assert '${line%%=*}' in content
    assert '${line#*=}' in content


def test_parser_handles_crlf() -> None:
    assert 'line%$' in LAUNCHER.read_text()


# ── URL validation ──────────────────────────────────────────────────────────


def test_url_valid_sushida_origin() -> None:
    """The case clause must allow exactly https://sushida.net[/...]."""
    content = LAUNCHER.read_text()
    patterns = [
        line.strip() for line in content.splitlines()
        if "https://sushida.net" in line
    ]
    has_glob = any("sushida.net/*" in p for p in patterns)
    has_root = any("sushida.net|" in p or "sushida.net)" in p for p in patterns)
    assert has_glob and has_root, (
        "URL validation must allow https://sushida.net/*"
    )


def test_url_rejects_http_in_accepted_patterns() -> None:
    """http:// must not appear as an accepted URL pattern."""
    content = LAUNCHER.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if "http://" in stripped and not stripped.startswith("#"):
            assert "ERROR" in stripped or "disallowed" in stripped, (
                f"http:// found outside rejection: {stripped}"
            )


# ── crash suppression ───────────────────────────────────────────────────────


def test_crash_bubble_suppressed() -> None:
    args = _args_array()
    assert any(a == "--hide-crash-restore-bubble" for a in args), (
        "--hide-crash-restore-bubble must be in CHROMIUM_ARGS"
    )


# ── executable pre-check ────────────────────────────────────────────────────


def test_command_v_cage() -> None:
    assert "command -v cage" in LAUNCHER.read_text()


def test_command_v_chromium() -> None:
    assert "command -v chromium" in LAUNCHER.read_text()


# ── Chromium arguments ──────────────────────────────────────────────────────


def test_chromium_args_are_array() -> None:
    assert "CHROMIUM_ARGS=(" in LAUNCHER.read_text()


def test_kiosk_mode() -> None:
    args = _args_array()
    assert any(a == "--kiosk" for a in args), "--kiosk not in CHROMIUM_ARGS"


def test_no_first_run() -> None:
    args = _args_array()
    assert any(a == "--no-first-run" for a in args)


def test_no_default_browser_check() -> None:
    args = _args_array()
    assert any(a == "--no-default-browser-check" for a in args)


def test_user_data_dir_under_run() -> None:
    args = _args_array()
    target = [a for a in args if "user-data-dir" in a]
    assert len(target) == 1
    assert "BASE_RUNTIME" in target[0]


def test_disk_cache_dir_under_run() -> None:
    args = _args_array()
    target = [a for a in args if "disk-cache-dir" in a]
    assert len(target) == 1
    assert "BASE_RUNTIME" in target[0]


def test_ozone_platform_wayland() -> None:
    args = _args_array()
    assert any("ozone-platform=wayland" in a for a in args)


def test_forbidden_flags_absent_from_args() -> None:
    """No forbidden flag or flag prefix may appear in CHROMIUM_ARGS."""
    args = _args_array()
    for a in args:
        for prefix in FORBIDDEN_PREFIXES:
            assert not a.startswith(prefix), (
                f"Forbidden flag prefix found: {a}"
            )


# ── Cage execution ──────────────────────────────────────────────────────────


def test_exec_cage() -> None:
    assert "exec cage" in LAUNCHER.read_text()


def test_exec_cage_dash_dash() -> None:
    assert "cage -- chromium" in LAUNCHER.read_text()


def test_sushida_url_is_last_arg() -> None:
    content = LAUNCHER.read_text()
    assert '"${CHROMIUM_ARGS[@]}" "$SUSHIDA_URL"' in content


# ── environment ─────────────────────────────────────────────────────────────


def test_home_under_run() -> None:
    assert 'HOME="$BASE_RUNTIME/home"' in LAUNCHER.read_text()


def test_xdg_runtime_dir_under_run() -> None:
    assert 'XDG_RUNTIME_DIR' in LAUNCHER.read_text()


def test_tmpdir_under_run() -> None:
    assert 'TMPDIR="$BASE_RUNTIME/tmp"' in LAUNCHER.read_text()


# ── user check ──────────────────────────────────────────────────────────────


def test_user_check() -> None:
    assert 'id -un' in LAUNCHER.read_text()


# ── executable mode ─────────────────────────────────────────────────────────


def test_launcher_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"
