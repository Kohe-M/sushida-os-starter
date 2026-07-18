import subprocess
from pathlib import Path

KIOSK_UNIT = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
)
WATCHER_UNIT = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-network-watch.service"
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


def _unit_section(path: Path, name: str) -> dict[str, str]:
    content = path.read_text()
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
    lines: list[str] = []
    for line in HOOK.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("#!/"):
            continue
        lines.append(stripped)
    return lines


_K_sec = lambda s: _unit_section(KIOSK_UNIT, s)
_W_sec = lambda s: _unit_section(WATCHER_UNIT, s)


# ── files exist ──────────────────────────────────────────────────────────────

def test_kiosk_unit_exists() -> None:
    assert KIOSK_UNIT.is_file()


def test_watcher_unit_exists() -> None:
    assert WATCHER_UNIT.is_file()


def test_kiosk_unit_no_todo() -> None:
    assert "TODO" not in KIOSK_UNIT.read_text()


def test_watcher_unit_no_todo() -> None:
    assert "TODO" not in WATCHER_UNIT.read_text()


def test_hook_exists() -> None:
    assert HOOK.is_file()


# ── kiosk unit: [Unit] section ───────────────────────────────────────────────

def test_kiosk_description_set() -> None:
    assert "Description" in _K_sec("Unit")


def test_kiosk_starts_after_networkmanager_without_waiting_online() -> None:
    after = _K_sec("Unit").get("After", "")
    assert "NetworkManager.service" in after
    assert "sushida-wifi-setup.service" in after
    assert "network-online.target" not in after


def test_kiosk_wants_networkmanager_and_setup_service() -> None:
    wants = _K_sec("Unit").get("Wants", "")
    assert "NetworkManager.service" in wants
    assert "sushida-wifi-setup.service" in wants
    assert "network-online.target" not in wants


def test_kiosk_startlimitinterval_disabled() -> None:
    unit = _K_sec("Unit")
    assert "StartLimitIntervalSec" in unit
    assert unit["StartLimitIntervalSec"] == "0"


def test_kiosk_startlimitburst_not_in_service() -> None:
    svc = _K_sec("Service")
    assert "StartLimitBurst" not in svc


def test_kiosk_does_not_wait_for_network_online_target() -> None:
    unit = KIOSK_UNIT.read_text()
    assert "network-online.target" not in unit


# ── kiosk unit: [Service] section ────────────────────────────────────────────

def test_kiosk_user_kiosk() -> None:
    assert _K_sec("Service").get("User") == "kiosk"


def test_kiosk_group_kiosk() -> None:
    assert _K_sec("Service").get("Group") == "kiosk"


def test_kiosk_execstart_correct_path() -> None:
    assert _K_sec("Service").get("ExecStart") == "/usr/local/bin/sushida-launch"


def test_kiosk_restart_always() -> None:
    assert _K_sec("Service").get("Restart") == "always"


def test_kiosk_restartsec_finite_short() -> None:
    val = _K_sec("Service").get("RestartSec", "")
    assert val
    n = int(val)
    assert 1 <= n <= 4


def test_kiosk_timeoutstopsec_finite() -> None:
    val = _K_sec("Service").get("TimeoutStopSec", "")
    assert val
    assert int(val) >= 1


def test_kiosk_killmode_control_group() -> None:
    assert _K_sec("Service").get("KillMode") == "control-group"


def test_kiosk_nonewprivileges_true() -> None:
    assert _K_sec("Service").get("NoNewPrivileges") == "true"


def test_kiosk_capability_bounding_set_empty() -> None:
    svc = _K_sec("Service")
    assert "CapabilityBoundingSet" in svc
    assert svc["CapabilityBoundingSet"] == ""


def test_kiosk_ambient_capabilities_empty() -> None:
    svc = _K_sec("Service")
    assert "AmbientCapabilities" in svc
    assert svc["AmbientCapabilities"] == ""


def test_kiosk_has_safe_sandboxing_without_private_devices() -> None:
    svc = _K_sec("Service")
    for key, value in {
        "ProtectSystem": "strict",
        "ProtectHome": "true",
        "PrivateTmp": "true",
        "ProtectKernelTunables": "true",
        "ProtectKernelModules": "true",
        "ProtectKernelLogs": "true",
        "ProtectControlGroups": "true",
        "LockPersonality": "true",
        "RestrictSUIDSGID": "true",
        "RestrictRealtime": "true",
        "SystemCallArchitectures": "native",
        "ReadWritePaths": "/run/sushida-os",
    }.items():
        assert svc.get(key) == value
    assert "PrivateDevices" not in svc
    assert set(svc.get("RestrictAddressFamilies", "").split()) == {
        "AF_UNIX", "AF_INET", "AF_INET6", "AF_NETLINK",
    }


def test_kiosk_runtime_directory_sushida_os() -> None:
    assert _K_sec("Service").get("RuntimeDirectory") == "sushida-os"


def test_kiosk_runtime_directory_mode() -> None:
    mode = _K_sec("Service").get("RuntimeDirectoryMode", "")
    assert mode in ("0750", "750")


def test_kiosk_type_simple() -> None:
    assert _K_sec("Service").get("Type") == "simple"


def test_kiosk_no_forbidden_flags_in_execstart() -> None:
    path = _K_sec("Service").get("ExecStart", "")
    assert "--no-sandbox" not in path
    assert "--disable-gpu" not in path


# ── kiosk unit: [Install] section ────────────────────────────────────────────

def test_kiosk_wantedby_multi_user() -> None:
    target = _K_sec("Install").get("WantedBy", "")
    assert target in ALLOWED_BY_DEFAULT


# ── watcher unit: [Unit] section ─────────────────────────────────────────────

def test_watcher_description_set() -> None:
    assert "Description" in _W_sec("Unit")


def test_watcher_after_network_and_kiosk() -> None:
    after = _W_sec("Unit").get("After", "")
    assert "NetworkManager.service" in after
    assert "sushida-kiosk.service" in after


def test_watcher_wants_networkmanager() -> None:
    assert _W_sec("Unit").get("Wants", "") == "NetworkManager.service"


def test_watcher_startlimitinterval_disabled() -> None:
    unit = _W_sec("Unit")
    assert "StartLimitIntervalSec" in unit
    assert unit["StartLimitIntervalSec"] == "0"


def test_watcher_has_safe_sandboxing() -> None:
    svc = _W_sec("Service")
    for key in (
        "ProtectSystem", "PrivateTmp", "ProtectKernelLogs", "ProtectHostname",
        "ProtectClock", "RestrictSUIDSGID", "RestrictRealtime", "LockPersonality",
        "SystemCallArchitectures", "RestrictAddressFamilies", "ReadWritePaths",
    ):
        assert key in svc


def test_wifi_setup_disables_start_rate_limit() -> None:
    setup = Path(
        "live-build/config/includes.chroot/etc/systemd/system/sushida-wifi-setup.service"
    ).read_text()
    assert "StartLimitIntervalSec=0" in setup


def test_watcher_partof_not_enable_proxy() -> None:
    """PartOf is a lifecycle relationship, not a substitute for enable."""
    unit = _W_sec("Unit")
    partof = unit.get("PartOf", "")
    assert "sushida-kiosk.service" in partof


# ── watcher unit: [Service] section ──────────────────────────────────────────

def test_watcher_user_kiosk() -> None:
    assert _W_sec("Service").get("User") == "kiosk"


def test_watcher_group_kiosk() -> None:
    assert _W_sec("Service").get("Group") == "kiosk"


def test_watcher_execstart_correct_path() -> None:
    assert _W_sec("Service").get("ExecStart") == "/usr/local/bin/sushida-network-watch"


def test_watcher_restart_always() -> None:
    assert _W_sec("Service").get("Restart") == "always"


def test_watcher_restartsec_bounded() -> None:
    val = _W_sec("Service").get("RestartSec", "")
    assert val
    n = int(val)
    assert 1 <= n <= 10


def test_watcher_timeoutstopsec_finite() -> None:
    val = _W_sec("Service").get("TimeoutStopSec", "")
    assert val
    assert int(val) >= 1


def test_watcher_killmode_control_group() -> None:
    assert _W_sec("Service").get("KillMode") == "control-group"


def test_watcher_nonewprivileges_true() -> None:
    assert _W_sec("Service").get("NoNewPrivileges") == "true"


def test_watcher_capability_bounding_set_empty() -> None:
    svc = _W_sec("Service")
    assert "CapabilityBoundingSet" in svc
    assert svc["CapabilityBoundingSet"] == ""


def test_watcher_ambient_capabilities_empty() -> None:
    svc = _W_sec("Service")
    assert "AmbientCapabilities" in svc
    assert svc["AmbientCapabilities"] == ""


def test_watcher_no_forbidden_flags_in_execstart() -> None:
    path = _W_sec("Service").get("ExecStart", "")
    assert "--no-sandbox" not in path
    assert "--disable-gpu" not in path


def test_watcher_no_root() -> None:
    svc = _W_sec("Service")
    assert svc.get("User") != "root"


# ── watcher unit: [Install] section ──────────────────────────────────────────

def test_watcher_wantedby_multi_user() -> None:
    target = _W_sec("Install").get("WantedBy", "")
    assert target in ALLOWED_BY_DEFAULT


# ── enable hook ──────────────────────────────────────────────────────────────

def test_hook_strict_mode() -> None:
    assert "set -euo pipefail" in HOOK.read_text()


def test_hook_no_todo() -> None:
    assert "TODO" not in HOOK.read_text()


def test_hook_enables_kiosk_and_watcher() -> None:
    """Hook enables the kiosk, watcher, and constrained setup services."""
    exec_lines = _hook_exec_lines()
    enable_lines = [line for line in exec_lines if "systemctl enable" in line]
    assert len(enable_lines) >= 1, "No systemctl enable command found"
    # Collect all .service names from enable commands
    services_found: list[str] = []
    for cmd in enable_lines:
        parts = cmd.split()
        services_found.extend(p for p in parts if p.endswith(".service"))
    assert len(services_found) == 4, (
        f"Expected exactly 4 .service tokens, got {len(services_found)}: {services_found}"
    )
    expected = {
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-config-prepare.service",
        "sushida-wifi-setup.service",
    }
    assert set(services_found) == expected, (
        f"Expected enabled services {expected}, got {set(services_found)}"
    )
    # Reject wildcard, variable expansion, --now, start, restart
    text = HOOK.read_text()
    assert "--now" not in text
    assert "systemctl start" not in text
    assert "systemctl restart" not in text
    assert "systemctl daemon-reload" not in text
    for cmd in enable_lines:
        assert "*" not in cmd, f"Wildcard in enable command: {cmd}"
        assert "${" not in cmd, f"Variable expansion in enable command: {cmd}"


def test_hook_no_start_or_now() -> None:
    """Hook must not use --now, start, restart, or daemon-reload."""
    text = HOOK.read_text()
    assert "--now" not in text
    assert "systemctl start" not in text
    assert "systemctl restart" not in text
    assert "systemctl daemon-reload" not in text


def test_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/020-enable-services.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"
