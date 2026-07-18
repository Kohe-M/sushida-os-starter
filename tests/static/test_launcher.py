import os
import stat
import subprocess
from pathlib import Path

LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
SESSION_HELPER = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-session"
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


def _helper_args_array() -> list[str]:
    """Extract CHROMIUM_ARGS array entries from the session helper."""
    content = SESSION_HELPER.read_text()
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


# ── Launcher tests ──────────────────────────────────────────────────────────

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

def test_test_mode_guard() -> None:
    assert "SUSHIDA_OS_TEST_MODE" in LAUNCHER.read_text()

def test_production_paths_fixed() -> None:
    content = LAUNCHER.read_text()
    assert "/etc/sushida-os/config.env" in content
    assert "/run/sushida-os" in content
    assert "PROD_SESSION" in content

def test_parser_single_equals_split() -> None:
    content = LAUNCHER.read_text()
    assert '${line%%=*}' in content
    assert '${line#*=}' in content

def test_parser_handles_crlf() -> None:
    assert "'\\''r'" in LAUNCHER.read_text() or 'line%$' in LAUNCHER.read_text() or "$'\\r'" in LAUNCHER.read_text()

def test_url_valid_sushida_origin() -> None:
    content = LAUNCHER.read_text()
    patterns = [line.strip() for line in content.splitlines() if "https://sushida.net" in line]
    assert any("sushida.net/*" in p for p in patterns)
    assert any("sushida.net|" in p or "sushida.net)" in p for p in patterns)

def test_url_rejects_http_in_accepted_patterns() -> None:
    content = LAUNCHER.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if "http://" in stripped and not stripped.startswith("#"):
            assert (
                stripped == 'readonly SETUP_URL="http://127.0.0.1:8787/"'
                or "ERROR" in stripped
                or "disallowed" in stripped
            )

def test_command_v_loop() -> None:
    content = LAUNCHER.read_text()
    assert "for cmd in" in content
    assert "command -v" in content
    assert "dbus-run-session" in content

def test_home_under_run() -> None:
    assert 'HOME="$BASE_RUNTIME/home"' in LAUNCHER.read_text()

def test_xdg_runtime_dir_under_run() -> None:
    assert 'XDG_RUNTIME_DIR' in LAUNCHER.read_text()

def test_tmpdir_under_run() -> None:
    assert 'TMPDIR="$BASE_RUNTIME/tmp"' in LAUNCHER.read_text()

def test_user_check() -> None:
    assert 'id -un' in LAUNCHER.read_text()

def test_launcher_exec_dbus_session() -> None:
    """Launcher execs dbus-run-session with helper and URL as separate args."""
    content = LAUNCHER.read_text()
    assert "exec dbus-run-session" in content
    assert '"$SESSION_HELPER" "$START_URL"' in content

def test_launcher_selects_route_from_nm_global_state() -> None:
    content = LAUNCHER.read_text()
    assert "LC_ALL=C nmcli -t -f STATE general" in content
    assert '[ "$nm_state" = "connected" ]' in content
    assert "connected.local" not in content

def test_launcher_offline_url_is_fixed() -> None:
    content = LAUNCHER.read_text()
    assert 'readonly OFFLINE_URL="file://localhost/usr/share/sushida-os/offline.html"' in content
    assert 'START_URL="$OFFLINE_URL"' in content

def test_launcher_writes_atomic_active_route_marker() -> None:
    content = LAUNCHER.read_text()
    assert "mktemp" in content
    assert 'mv -f -- "$route_tmp" "$BASE_RUNTIME/active-route"' in content
    assert 'printf \'%s\\n\' "$ACTIVE_ROUTE"' in content

def test_launcher_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"

def test_launcher_no_forbidden_flags() -> None:
    content = LAUNCHER.read_text()
    for prefix in FORBIDDEN_PREFIXES:
        assert prefix not in content, f"Forbidden flag in launcher: {prefix}"


# ── Session helper tests ────────────────────────────────────────────────────

def test_helper_exists() -> None:
    assert SESSION_HELPER.is_file()

def test_helper_no_todo() -> None:
    assert "TODO" not in SESSION_HELPER.read_text()

def test_helper_strict_mode() -> None:
    assert "set -euo pipefail" in SESSION_HELPER.read_text()

def test_helper_no_eval() -> None:
    assert "eval" not in SESSION_HELPER.read_text()

def test_helper_no_source() -> None:
    content = SESSION_HELPER.read_text()
    assert "source " not in content

def test_helper_is_executable() -> None:
    """Check executable mode on filesystem (helper is untracked, no git mode)."""
    st = SESSION_HELPER.stat()
    assert st.st_mode & stat.S_IXUSR, "Helper must be user-executable"
    assert not (st.st_mode & stat.S_IWGRP), "Helper must not be group-writable"
    assert not (st.st_mode & stat.S_IWOTH), "Helper must not be other-writable"
    assert os.access(SESSION_HELPER, os.X_OK)

def test_helper_url_validation() -> None:
    content = SESSION_HELPER.read_text()
    assert "sushida.net" in content
    assert "https://" in content or "disallowed" in content

def test_helper_allows_only_fixed_offline_file_url() -> None:
    content = SESSION_HELPER.read_text()
    assert 'readonly OFFLINE_URL="file://localhost/usr/share/sushida-os/offline.html"' in content
    assert '"$OFFLINE_URL"' in content

def test_helper_starts_pipewire() -> None:
    text = SESSION_HELPER.read_text()
    assert "pipewire" in text
    assert "SESSION_PIDS" in text

def test_helper_starts_pipewire_pulse() -> None:
    assert "pipewire-pulse" in SESSION_HELPER.read_text()

def test_helper_starts_wireplumber() -> None:
    assert "wireplumber" in SESSION_HELPER.read_text()

def test_helper_starts_cage() -> None:
    assert "cage -- chromium" in SESSION_HELPER.read_text()

def test_helper_has_readiness() -> None:
    text = SESSION_HELPER.read_text()
    assert "pipewire-0" in text
    assert "-S" in text
    assert "AUDIO_TIMEOUT" in text

def test_helper_has_wait_n() -> None:
    assert "wait -n" in SESSION_HELPER.read_text()

def test_helper_has_cleanup_trap() -> None:
    text = SESSION_HELPER.read_text()
    assert "trap" in text
    assert "_cleanup_exit" in text

def test_helper_exit_status_preserved() -> None:
    text = SESSION_HELPER.read_text()
    assert "_CLEANUP_EXIT" in text or "_WAIT_STATUS" in text or "_SESSION_EXIT" in text

def test_helper_detects_audio_exit() -> None:
    text = SESSION_HELPER.read_text()
    assert "SESSION_PIDS" in text
    assert "SESSION_NAMES" in text
    assert "cage" in text

def test_helper_no_exec_cage() -> None:
    assert "exec cage" not in SESSION_HELPER.read_text()

def test_helper_production_xdg_guard() -> None:
    text = SESSION_HELPER.read_text()
    assert "PROD_XDG" in text or "/run/sushida-os" in text

def test_helper_chromium_args_array() -> None:
    assert "CHROMIUM_ARGS=(" in SESSION_HELPER.read_text()

def test_helper_kiosk_mode() -> None:
    args = _helper_args_array()
    assert any(a == "--kiosk" for a in args), "--kiosk not in CHROMIUM_ARGS"

def test_helper_no_first_run() -> None:
    args = _helper_args_array()
    assert any(a == "--no-first-run" for a in args)

def test_helper_no_default_browser_check() -> None:
    args = _helper_args_array()
    assert any(a == "--no-default-browser-check" for a in args)

def test_helper_crash_bubble_suppressed() -> None:
    args = _helper_args_array()
    assert any(a == "--hide-crash-restore-bubble" for a in args)

def test_helper_user_data_dir_under_run() -> None:
    args = _helper_args_array()
    target = [a for a in args if "user-data-dir" in a]
    assert len(target) == 1
    assert "XDG_RUNTIME_DIR" in target[0]

def test_helper_disk_cache_dir_under_run() -> None:
    args = _helper_args_array()
    target = [a for a in args if "disk-cache-dir" in a]
    assert len(target) == 1
    assert "XDG_RUNTIME_DIR" in target[0]

def test_helper_ozone_platform_wayland() -> None:
    args = _helper_args_array()
    assert any("ozone-platform=wayland" in a for a in args)

def test_helper_forbidden_flags_absent() -> None:
    args = _helper_args_array()
    for a in args:
        for prefix in FORBIDDEN_PREFIXES:
            assert not a.startswith(prefix), f"Forbidden flag prefix found: {a}"

def test_helper_url_is_last_arg() -> None:
    """URL is the last Chromium argument."""
    content = SESSION_HELPER.read_text()
    assert '"${CHROMIUM_ARGS[@]}" "$SUSHIDA_URL"' in content or \
           '"${CHROMIUM_ARGS[@]}" "$URL"' in content
