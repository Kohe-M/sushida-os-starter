"""Static tests for audio, graphics, and Wayland configuration."""

import subprocess
from pathlib import Path

AUDIO_HOOK = Path(
    "live-build/config/hooks/live/030-configure-audio.hook.chroot"
)
LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
PACKAGE_LIST = Path(
    "live-build/config/package-lists/kiosk.list.chroot"
)
KIOSK_USER_HOOK = Path(
    "live-build/config/hooks/live/010-create-kiosk-user.hook.chroot"
)


def _package_set() -> set[str]:
    pkgs: set[str] = set()
    for line in PACKAGE_LIST.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        pkgs.add(s.split()[0])
    return pkgs


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ── Audio hook ───────────────────────────────────────────────────────────

def test_audio_hook_exists() -> None:
    assert AUDIO_HOOK.is_file()


def test_audio_hook_no_todo() -> None:
    assert "TODO" not in AUDIO_HOOK.read_text()


def test_audio_hook_strict_mode() -> None:
    assert "set -euo pipefail" in AUDIO_HOOK.read_text()


def test_audio_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/030-configure-audio.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"


def test_audio_hook_no_daemon_start() -> None:
    text = AUDIO_HOOK.read_text()
    assert "--now" not in text
    assert "systemctl start" not in text
    assert "systemctl restart" not in text


def test_audio_hook_no_world_writable_snd() -> None:
    text = AUDIO_HOOK.read_text()
    assert "0666" not in text
    assert "chmod /dev" not in text


def test_audio_hook_no_build_runtime_dir() -> None:
    """Hook must not create /run directories (tmpfs at boot)."""
    text = AUDIO_HOOK.read_text()
    assert "/run" not in text, "Hook must not create /run paths"


def test_audio_hook_no_eval() -> None:
    assert "eval" not in AUDIO_HOOK.read_text()


def test_audio_hook_checks_binaries() -> None:
    text = AUDIO_HOOK.read_text()
    for cmd in ("pipewire", "pipewire-pulse", "wireplumber", "dbus-run-session"):
        assert cmd in text, f"hook should check for {cmd}"


# ── Launcher: audio session ─────────────────────────────────────────────

SESSION_HELPER = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-session"
)


def test_session_helper_exists() -> None:
    assert SESSION_HELPER.is_file()


def test_session_helper_strict_mode() -> None:
    assert "set -euo pipefail" in SESSION_HELPER.read_text()


def test_session_helper_is_executable() -> None:
    """Check helper executable mode on filesystem (untracked file)."""
    import os
    import stat
    st = SESSION_HELPER.stat()
    assert st.st_mode & stat.S_IXUSR, "Helper must be user-executable"


def test_session_helper_starts_pipewire() -> None:
    assert "pipewire" in SESSION_HELPER.read_text()


def test_session_helper_starts_pipewire_pulse() -> None:
    assert "pipewire-pulse" in SESSION_HELPER.read_text()


def test_session_helper_starts_wireplumber() -> None:
    assert "wireplumber" in SESSION_HELPER.read_text()


def test_session_helper_starts_cage() -> None:
    assert "cage -- chromium" in SESSION_HELPER.read_text()


def test_session_helper_has_readiness() -> None:
    text = SESSION_HELPER.read_text()
    assert "pipewire-0" in text
    assert "-S" in text
    assert "AUDIO_TIMEOUT" in text


def test_session_helper_has_wait_n() -> None:
    assert "wait -n" in SESSION_HELPER.read_text()


def test_session_helper_has_cleanup_trap() -> None:
    text = SESSION_HELPER.read_text()
    assert "trap" in text
    assert "_cleanup_exit" in text


def test_session_helper_no_fixed_sleep_only() -> None:
    text = SESSION_HELPER.read_text()
    has_sleep = '"sleep 0.2"' in text or '"sleep 0.3"' in text
    has_socket_check = "-S" in text and "pipewire-0" in text
    if has_sleep and not has_socket_check:
        raise AssertionError("Fixed sleep without socket readiness check")


def test_session_helper_exit_status_preserved() -> None:
    text = SESSION_HELPER.read_text()
    # Must use either _SESSION_EXIT, _CLEANUP_EXIT, or _WAIT_STATUS
    assert "_SESSION_EXIT" in text or "_CLEANUP_EXIT" in text or "_WAIT_STATUS" in text
    assert "exit \"$_SESSION_EXIT\"" in text or 'exit "$_WAIT_STATUS"' in text or 'exit "$_CLEANUP_EXIT"' in text


def test_session_helper_no_exec_cage() -> None:
    content = SESSION_HELPER.read_text()
    assert "exec cage" not in content


def test_launcher_uses_session_helper() -> None:
    text = LAUNCHER.read_text()
    assert "dbus-run-session" in text
    assert "sushida-session" in text or "SESSION_HELPER" in text


def test_launcher_checks_binaries() -> None:
    text = LAUNCHER.read_text()
    for cmd in ("cage", "chromium", "pipewire", "pipewire-pulse", "wireplumber", "dbus-run-session"):
        assert cmd in text, f"Missing reference to {cmd}"
    assert "for cmd in" in text and "command -v" in text


def test_launcher_no_disable_gpu() -> None:
    assert "--disable-gpu" not in LAUNCHER.read_text()


def test_launcher_no_disable_webgl() -> None:
    assert "--disable-webgl" not in LAUNCHER.read_text()


def test_launcher_no_no_sandbox() -> None:
    assert "--no-sandbox" not in LAUNCHER.read_text()


def test_launcher_has_ozone_wayland() -> None:
    assert "--ozone-platform=wayland" in SESSION_HELPER.read_text()


# ── Package list: graphics ──────────────────────────────────────────────

def test_graphics_packages_present() -> None:
    s = _package_set()
    required = {
        "libgl1-mesa-dri",
        "mesa-va-drivers",
        "libegl1",
        "libgles2",
        "libgbm1",
        "libdrm2",
    }
    missing = required - s
    assert not missing, f"Missing graphics packages: {missing}"


def test_wayland_packages_present() -> None:
    s = _package_set()
    required = {"libwayland-client0", "libwayland-server0"}
    missing = required - s
    assert not missing, f"Missing Wayland packages: {missing}"


def test_no_nvidia_driver() -> None:
    s = _package_set()
    nvidia = {"nvidia-driver", "nvidia-kernel-dkms", "nvidia-settings"}
    assert not (s & nvidia), "NVIDIA packages found"


def test_no_xorg_server() -> None:
    s = _package_set()
    xorg = {"xserver-xorg", "xserver-xorg-core", "xorg"}
    assert not (s & xorg), "Xorg package found"


# ── Package list: audio ─────────────────────────────────────────────────

def test_audio_packages_present() -> None:
    s = _package_set()
    required = {
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "libspa-0.2-modules",
        "dbus-user-session",
    }
    missing = required - s
    assert not missing, f"Missing audio packages: {missing}"


def test_no_pulseaudio_daemon() -> None:
    """Legacy pulseaudio daemon must not be explicitly added."""
    assert "pulseaudio" not in _package_set()


def test_no_rtkit() -> None:
    """rtkit is not required; do not add it."""
    assert "rtkit" not in _package_set()


# ── Kiosk user groups ───────────────────────────────────────────────────

def test_kiosk_has_audio_group() -> None:
    """The kiosk user hook must grant the audio group for /dev/snd access."""
    text = KIOSK_USER_HOOK.read_text()
    assert "audio" in text
