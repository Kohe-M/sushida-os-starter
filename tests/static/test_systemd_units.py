import subprocess
from pathlib import Path

UNIT = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
)
HOOK = Path(
    "live-build/config/hooks/live/020-enable-services.hook.chroot"
)
ALLOWED_BY_DEFAULT = {
    "multi-user.target",
    "graphical.target",
    "default.target",
}


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _unit_section(name: str) -> dict[str, str]:
    """Return key→value pairs from a systemd unit section.

    The returned dict distinguishes "key absent" (not in dict) from
    "key present with empty value" (in dict, maps to "").
    """
    content = UNIT.read_text()
    mapping: dict[str, str] = {}
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped == f"[{name}]"
            continue
        if not in_section or not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        mapping[key] = value
    return mapping


def _hook_exec_lines() -> list[str]:
    """Return non-comment, non-empty lines from the enable hook."""
    lines: list[str] = []
    for line in HOOK.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("#!/"):
            continue
        lines.append(stripped)
    return lines


# ── unit: presence ──────────────────────────────────────────────────────────


def test_unit_exists() -> None:
    assert UNIT.is_file()


def test_unit_no_todo() -> None:
    assert "TODO" not in UNIT.read_text()


def test_hook_exists() -> None:
    assert HOOK.is_file()


# ── unit: [Unit] section ───────────────────────────────────────────────────


def test_unit_description_set() -> None:
    unit = _unit_section("Unit")
    assert "Description" in unit


def test_after_network() -> None:
    unit = _unit_section("Unit")
    after = unit.get("After", "")
    assert "network-online.target" in after


def test_startlimitinterval_disabled() -> None:
    unit = _unit_section("Unit")
    assert "StartLimitIntervalSec" in unit, (
        "StartLimitIntervalSec must be present in [Unit]"
    )
    assert unit["StartLimitIntervalSec"] == "0", (
        f"StartLimitIntervalSec={unit['StartLimitIntervalSec']} must be 0"
    )


def test_startlimitburst_not_in_service() -> None:
    """StartLimitBurst must not appear in [Service] (moved to [Unit])."""
    svc = _unit_section("Service")
    assert "StartLimitBurst" not in svc


# ── unit: [Service] section ─────────────────────────────────────────────────


def test_service_user_kiosk() -> None:
    svc = _unit_section("Service")
    assert svc.get("User") == "kiosk"


def test_service_group_kiosk() -> None:
    svc = _unit_section("Service")
    assert svc.get("Group") == "kiosk"


def test_execstart_correct_path() -> None:
    svc = _unit_section("Service")
    assert svc.get("ExecStart") == "/usr/local/bin/sushida-launch"


def test_restart_always() -> None:
    svc = _unit_section("Service")
    assert svc.get("Restart") == "always"


def test_restartsec_finite_short() -> None:
    svc = _unit_section("Service")
    val = svc.get("RestartSec", "")
    assert val
    n = int(val)
    assert 1 <= n <= 4, f"RestartSec={n} must be 1-4 seconds"


def test_timeoutstopsec_finite() -> None:
    svc = _unit_section("Service")
    val = svc.get("TimeoutStopSec", "")
    assert val, "TimeoutStopSec must be set to a finite value"
    n = int(val)
    assert n >= 1, f"TimeoutStopSec={n} must be positive"


def test_killmode_control_group() -> None:
    svc = _unit_section("Service")
    assert svc.get("KillMode") == "control-group"


def test_nonewprivileges_true() -> None:
    svc = _unit_section("Service")
    assert svc.get("NoNewPrivileges") == "true"


def test_capability_bounding_set_empty() -> None:
    svc = _unit_section("Service")
    assert "CapabilityBoundingSet" in svc, (
        "CapabilityBoundingSet must be explicitly set (even if empty)"
    )
    assert svc["CapabilityBoundingSet"] == "", (
        "CapabilityBoundingSet must be empty (no capabilities granted)"
    )


def test_ambient_capabilities_empty() -> None:
    svc = _unit_section("Service")
    assert "AmbientCapabilities" in svc, (
        "AmbientCapabilities must be explicitly set (even if empty)"
    )
    assert svc["AmbientCapabilities"] == "", (
        "AmbientCapabilities must be empty (no capabilities granted)"
    )


def test_runtime_directory_sushida_os() -> None:
    svc = _unit_section("Service")
    assert svc.get("RuntimeDirectory") == "sushida-os"


def test_runtime_directory_mode() -> None:
    svc = _unit_section("Service")
    mode = svc.get("RuntimeDirectoryMode", "")
    assert mode in ("0750", "750"), f"RuntimeDirectoryMode={mode} is not restrictive"


def test_type_simple() -> None:
    svc = _unit_section("Service")
    assert svc.get("Type") == "simple"


def test_no_forbidden_flags_in_execstart() -> None:
    svc = _unit_section("Service")
    path = svc.get("ExecStart", "")
    assert "--no-sandbox" not in path
    assert "--disable-gpu" not in path


# ── unit: [Install] section ─────────────────────────────────────────────────


def test_wantedby_multi_user() -> None:
    install = _unit_section("Install")
    target = install.get("WantedBy", "")
    assert target in ALLOWED_BY_DEFAULT, f"WantedBy={target} is unexpected"


# ── enable hook ─────────────────────────────────────────────────────────────


def test_hook_strict_mode() -> None:
    assert "set -euo pipefail" in HOOK.read_text()


def test_hook_no_todo() -> None:
    assert "TODO" not in HOOK.read_text()


def test_hook_enables_only_kiosk_service() -> None:
    """Hook must enable exactly sushida-kiosk.service (no other services)."""
    exec_lines = _hook_exec_lines()
    # Filter only systemctl enable commands
    enable_lines = [line for line in exec_lines if "systemctl enable" in line]
    assert len(enable_lines) >= 1, "No systemctl enable command found"
    for cmd in enable_lines:
        # Each command should reference only sushida-kiosk.service
        assert "sushida-kiosk.service" in cmd, (
            f"Unexpected enable target: {cmd}"
        )
        # Verify no other .service file is named
        parts = cmd.split()
        services = [p for p in parts if p.endswith(".service")]
        assert all(s == "sushida-kiosk.service" for s in services), (
            f"Extra service(s) enabled: {services}"
        )


def test_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/020-enable-services.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"
