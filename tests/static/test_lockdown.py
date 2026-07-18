import json
import subprocess
from pathlib import Path

ACCEPTANCE = Path("docs/acceptance-tests.md")
HOOK = Path(
    "live-build/config/hooks/live/050-lock-down-system.hook.chroot"
)
LOGIND = Path(
    "live-build/config/includes.chroot/etc/systemd/logind.conf.d/90-sushida-kiosk.conf"
)
SYSCONF = Path(
    "live-build/config/includes.chroot/etc/systemd/system.conf.d/90-sushida-kiosk.conf"
)
SYSCTL = Path(
    "live-build/config/includes.chroot/etc/sysctl.d/90-sushida-kiosk.conf"
)
LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
SESSION_HELPER = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-session"
)
KIOSK_SERVICE = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
)
POLICY_FILE = Path(
    "live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json"
)
PACKAGE_LIST = Path(
    "live-build/config/package-lists/kiosk.list.chroot"
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _parse_dropin(path: Path, section: str) -> dict[str, str]:
    content = path.read_text()
    mapping: dict[str, str] = {}
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped == f"[{section}]"
            continue
        if not in_section or not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        mapping[k.strip()] = v.strip()
    return mapping


def _hook_exec_lines() -> list[str]:
    """Return execution lines from the lockdown hook
    (no shebang, no blank, no comments)."""
    lines: list[str] = []
    for line in HOOK.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("#!/"):
            continue
        lines.append(s)
    return lines


def _service_section(name: str) -> dict[str, str]:
    content = KIOSK_SERVICE.read_text()
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
        k, v = stripped.split("=", 1)
        mapping[k] = v
    return mapping


def _chromium_policy() -> dict:
    with open(POLICY_FILE) as f:
        return json.load(f)


def _acceptance_operations() -> list[str]:
    """Extract Operation column from the acceptance-tests.md tables."""
    content = ACCEPTANCE.read_text()
    ops: list[str] = []
    in_table = False
    for line in content.splitlines():
        if "|---|---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 3 and cells[1].strip().startswith(("K", "G", "P")) \
               and cells[2].strip():
                ops.append(cells[2].strip())
    return ops


def _package_names() -> list[str]:
    pkgs: list[str] = []
    for line in PACKAGE_LIST.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        pkgs.append(s.split()[0])
    return pkgs


# ── file validity ──────────────────────────────────────────────────────────


def test_hook_exists() -> None:
    assert HOOK.is_file()


def test_hook_no_todo() -> None:
    assert "TODO" not in HOOK.read_text()


def test_hook_strict_mode() -> None:
    assert "set -euo pipefail" in HOOK.read_text()


def test_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/050-lock-down-system.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"


def test_logind_exists() -> None:
    assert LOGIND.is_file()


def test_sysconf_exists() -> None:
    assert SYSCONF.is_file()


def test_sysctl_exists() -> None:
    assert SYSCTL.is_file()


def test_logind_no_todo() -> None:
    assert "TODO" not in LOGIND.read_text()


def test_sysconf_no_todo() -> None:
    assert "TODO" not in SYSCONF.read_text()


def test_sysctl_no_todo() -> None:
    assert "TODO" not in SYSCTL.read_text()


# ── hook: getty lockdown (execution-line based) ────────────────────────────


EXPECTED_MASK_TARGETS = {
    "getty@.service",
    "autovt@.service",
    "serial-getty@.service",
    "console-getty.service",
    "container-getty@.service",
    "ctrl-alt-del.target",
    "apt-daily.timer",
    "apt-daily-upgrade.timer",
    "apt-daily.service",
    "apt-daily-upgrade.service",
}


def test_hook_masks_console_and_apt_units() -> None:
    """Hook must mask login, reboot, and background APT units."""
    exec_lines = _hook_exec_lines()
    mask_cmds = [l for l in exec_lines if l.startswith("systemctl mask")]
    assert mask_cmds, "No systemctl mask command found in hook"
    masked_units = set()
    for cmd in mask_cmds:
        parts = cmd.split()
        # parts[0] = systemctl, parts[1] = mask, parts[2+] = unit(s)
        for unit in parts[2:]:
            masked_units.add(unit)
    assert masked_units == EXPECTED_MASK_TARGETS, (
        f"Masked units = {masked_units}, expected {EXPECTED_MASK_TARGETS}"
    )


def test_hook_does_not_mask_rescue_or_kiosk() -> None:
    exec_lines = _hook_exec_lines()
    for l in exec_lines:
        if l.startswith("systemctl mask"):
            for unit in l.split()[2:]:
                assert unit not in ("rescue.target", "emergency.target",
                                     "sushida-kiosk.service"), (
                    f"Hook must NOT mask {unit}"
                )


# ── logind ────────────────────────────────────────────────────────────────


def test_logind_section_login() -> None:
    cfg = _parse_dropin(LOGIND, "Login")
    assert cfg.get("NAutoVTs") == "0"


def test_logind_reserve_vt() -> None:
    cfg = _parse_dropin(LOGIND, "Login")
    assert cfg.get("ReserveVT") == "0"


def test_logind_no_power_settings() -> None:
    cfg = _parse_dropin(LOGIND, "Login")
    extra = [k for k in cfg if k not in ("NAutoVTs", "ReserveVT")]
    assert not extra, f"Unexpected logind settings: {extra}"


# ── Ctrl+Alt+Delete burst protection ──────────────────────────────────────


def test_ctrl_alt_del_burst_disabled() -> None:
    cfg = _parse_dropin(SYSCONF, "Manager")
    assert cfg.get("CtrlAltDelBurstAction") == "none"


# ── sysctl ────────────────────────────────────────────────────────────────


def test_sysrq_disabled() -> None:
    assert "kernel.sysrq = 0" in SYSCTL.read_text() or \
           "kernel.sysrq=0" in SYSCTL.read_text()


def test_sysctl_no_userns_disabling() -> None:
    content = SYSCTL.read_text()
    assert "kernel.unprivileged_userns_clone" not in content
    assert "user.max_user_namespaces" not in content


# ── gameplay input preservation ───────────────────────────────────────────


def test_no_keyboard_remap_in_hook() -> None:
    content = HOOK.read_text()
    for tool in ("loadkeys", "setxkbmap", "xmodmap"):
        assert tool not in content, f"Keyboard remap tool found in hook: {tool}"


def test_no_keyboard_interception_in_packages() -> None:
    pkgs = _package_names()
    for pkg in ("keyd", "interception-tools", "input-remapper"):
        assert pkg not in pkgs, f"Keyboard interception package found: {pkg}"


# ── artifact-connected controls ────────────────────────────────────────────


def _check_cage_single_app() -> None:
    # Cage invocation now lives in the session helper, not the launcher.
    content = SESSION_HELPER.read_text()
    found = False
    for line in content.splitlines():
        if "cage -- chromium" in line:
            found = True
            assert " -s" not in line, "Cage VT switching (-s) enabled"
    assert found, "Cage invocation not found in session helper"
    # Verify no DE packages added
    de_pkgs = {"gnome", "plasma-desktop", "xfce4", "lxde", "cinnamon"}
    pkgs = set(_package_names())
    assert not (pkgs & de_pkgs), f"DE package found: {pkgs & de_pkgs}"


def _check_restart_recovery() -> None:
    svc = _service_section("Service")
    assert svc.get("Restart") == "always"
    sec = svc.get("RestartSec", "")
    assert sec and 1 <= int(sec) <= 4


def _check_vt_lockdown() -> None:
    # Cage -s absent
    for line in LAUNCHER.read_text().splitlines():
        if "exec cage" in line or "cage -- chromium" in line:
            assert " -s" not in line
    # logind
    lcfg = _parse_dropin(LOGIND, "Login")
    assert lcfg.get("NAutoVTs") == "0"
    assert lcfg.get("ReserveVT") == "0"
    # getty/autovt/serial mask
    exec_lines = _hook_exec_lines()
    masked = set()
    for l in exec_lines:
        if l.startswith("systemctl mask"):
            for u in l.split()[2:]:
                masked.add(u)
    for u in ("getty@.service", "autovt@.service", "serial-getty@.service"):
        assert u in masked, f"VT lockdown requires {u} to be masked"


def _check_ctrl_alt_del() -> None:
    exec_lines = _hook_exec_lines()
    has_mask = any(
        "ctrl-alt-del.target" in l for l in exec_lines
        if l.startswith("systemctl mask")
    )
    assert has_mask, "ctrl-alt-del.target not masked"
    cfg = _parse_dropin(SYSCONF, "Manager")
    assert cfg.get("CtrlAltDelBurstAction") == "none"


def _check_chromium_kiosk() -> None:
    # --kiosk now lives in the session helper
    assert "--kiosk" in SESSION_HELPER.read_text()
    p = _chromium_policy()
    assert "*" in p["URLBlocklist"]
    expected = {
        "https://.sushida.net:443",
        "file://localhost/usr/share/sushida-os/offline.html",
        "http://127.0.0.1:8787",
    }
    assert set(p["URLAllowlist"]) == expected


def _check_incognito_policy() -> None:
    p = _chromium_policy()
    assert p["IncognitoModeAvailability"] == 1
    assert type(p["IncognitoModeAvailability"]) is int


def _check_devtools_policy() -> None:
    p = _chromium_policy()
    assert p["DeveloperToolsAvailability"] == 2
    assert type(p["DeveloperToolsAvailability"]) is int
    assert "view-source:*" in p["URLBlocklist"]


def _check_no_terminal() -> None:
    pkgs = set(_package_names())
    terms = {"xterm", "gnome-terminal", "konsole", "xfce4-terminal",
             "lxterminal", "rxvt-unicode", "terminator", "kgx"}
    assert not (pkgs & terms), f"Terminal emulator found: {pkgs & terms}"
    # Verify no terminal launch in launcher or hook
    launcher_content = LAUNCHER.read_text()
    assert "xterm" not in launcher_content
    # Verify no DE/display manager
    prohibited = {"gdm3", "sddm", "lightdm", "xdm", "gnome", "xfce4"}
    assert not (pkgs & prohibited), f"Prohibited package found: {pkgs & prohibited}"


# ── shortcut → control mapping ─────────────────────────────────────────────


CONTROL_BY_SHORTCUT: dict[str, str] = {
    "Alt+Tab":          "cage_single_app",
    "Alt+F2":           "cage_single_app",
    "Alt+F4":           "restart_recovery",
    "Super":            "cage_single_app",
    "Super+D":          "cage_single_app",
    "Super+R":          "cage_single_app",
    "Ctrl+Alt+T":       "no_terminal",
    "Ctrl+Alt+F1":      "vt_lockdown",
    "Ctrl+Alt+F2":      "vt_lockdown",
    "Ctrl+Alt+F3":      "vt_lockdown",
    "Ctrl+Alt+F4":      "vt_lockdown",
    "Ctrl+Alt+F5":      "vt_lockdown",
    "Ctrl+Alt+F6":      "vt_lockdown",
    "Ctrl+Alt+F7":      "vt_lockdown",
    "Ctrl+Alt+F8":      "vt_lockdown",
    "Ctrl+Alt+F9":      "vt_lockdown",
    "Ctrl+Alt+F10":     "vt_lockdown",
    "Ctrl+Alt+F11":     "vt_lockdown",
    "Ctrl+Alt+F12":     "vt_lockdown",
    "Ctrl+Alt+Delete":  "ctrl_alt_del",
    "Ctrl+Alt+Delete burst": "ctrl_alt_del",
    "Ctrl+L":           "chromium_kiosk",
    "Ctrl+T":           "chromium_kiosk",
    "Ctrl+N":           "chromium_kiosk",
    "Ctrl+Shift+N":     "incognito_policy",
    "Ctrl+W":           "restart_recovery",
    "Ctrl+U":           "devtools_policy",
    "Ctrl+Shift+I":     "devtools_policy",
    "F11":              "chromium_kiosk",
    "F12":              "devtools_policy",
}

CONTROL_FUNCTIONS: dict[str, str] = {
    "cage_single_app":  "_check_cage_single_app",
    "restart_recovery": "_check_restart_recovery",
    "vt_lockdown":      "_check_vt_lockdown",
    "ctrl_alt_del":     "_check_ctrl_alt_del",
    "chromium_kiosk":   "_check_chromium_kiosk",
    "incognito_policy": "_check_incognito_policy",
    "devtools_policy":  "_check_devtools_policy",
    "no_terminal":      "_check_no_terminal",
}

# Locals for dispatch
_check_fns = {
    "cage_single_app":  _check_cage_single_app,
    "restart_recovery": _check_restart_recovery,
    "vt_lockdown":      _check_vt_lockdown,
    "ctrl_alt_del":     _check_ctrl_alt_del,
    "chromium_kiosk":   _check_chromium_kiosk,
    "incognito_policy": _check_incognito_policy,
    "devtools_policy":  _check_devtools_policy,
    "no_terminal":      _check_no_terminal,
}


def test_shortcut_coverage() -> None:
    """Every AGENTS.md shortcut must be mapped to a control."""
    expected = set(CONTROL_BY_SHORTCUT.keys())
    agents_shortcuts = {
        "Alt+Tab", "Alt+F2", "Alt+F4", "Super", "Super+D", "Super+R",
        "Ctrl+Alt+T",
        "Ctrl+Alt+F1", "Ctrl+Alt+F2", "Ctrl+Alt+F3", "Ctrl+Alt+F4",
        "Ctrl+Alt+F5", "Ctrl+Alt+F6", "Ctrl+Alt+F7", "Ctrl+Alt+F8",
        "Ctrl+Alt+F9", "Ctrl+Alt+F10", "Ctrl+Alt+F11", "Ctrl+Alt+F12",
        "Ctrl+Alt+Delete", "Ctrl+Alt+Delete burst",
        "Ctrl+L", "Ctrl+T", "Ctrl+N", "Ctrl+Shift+N", "Ctrl+W",
        "Ctrl+U", "Ctrl+Shift+I",
        "F11", "F12",
    }
    assert expected == agents_shortcuts, (
        f"Mismatch: extra {expected - agents_shortcuts}, "
        f"missing {agents_shortcuts - expected}"
    )


def test_each_control_function_runs() -> None:
    """Each shortcut's control function executes against real artifacts."""
    checked_controls: set[str] = set()
    for shortcut, control_id in CONTROL_BY_SHORTCUT.items():
        if control_id in checked_controls:
            continue
        checked_controls.add(control_id)
        fn = _check_fns.get(control_id)
        assert fn is not None, f"No check function for control {control_id}"
        fn()
    # Verify all controls were covered
    assert checked_controls == set(CONTROL_FUNCTIONS.keys()), (
        f"Missed controls: {set(CONTROL_FUNCTIONS.keys()) - checked_controls}"
    )


# ── acceptance table verification ──────────────────────────────────────────


def test_acceptance_contains_all_shortcuts() -> None:
    """AGENTS.md shortcuts must appear in the acceptance Operation column."""
    ops = _acceptance_operations()
    required = {
        "Alt+Tab", "Alt+F2", "Alt+F4", "Super", "Super+D", "Super+R",
        "Ctrl+Alt+T",
        "Ctrl+Alt+F1", "Ctrl+Alt+F2", "Ctrl+Alt+F3", "Ctrl+Alt+F4",
        "Ctrl+Alt+F5", "Ctrl+Alt+F6", "Ctrl+Alt+F7", "Ctrl+Alt+F8",
        "Ctrl+Alt+F9", "Ctrl+Alt+F10", "Ctrl+Alt+F11", "Ctrl+Alt+F12",
        "Ctrl+Alt+Delete (single)", "Ctrl+Alt+Delete (rapid burst)",
        "Ctrl+L", "Ctrl+T", "Ctrl+N", "Ctrl+Shift+N", "Ctrl+W",
        "Ctrl+U", "Ctrl+Shift+I",
        "F11", "F12",
    }
    for op in required:
        assert op in ops, f"Acceptance table missing: {op}"


def test_acceptance_ids_unique() -> None:
    content = ACCEPTANCE.read_text()
    ids: list[str] = []
    in_table = False
    for line in content.splitlines():
        if "|---|---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 2 and cells[1].strip() and \
               cells[1].strip() != "ID":
                    ids.append(cells[1].strip())
    assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"


def test_acceptance_actual_and_pass_empty() -> None:
    """Un-tested items must have empty Actual result and Pass/Fail."""
    content = ACCEPTANCE.read_text()
    in_table = False
    for line in content.splitlines():
        if "|---|---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 6:
                actual = cells[4].strip() if len(cells) > 4 else ""
                passed = cells[5].strip() if len(cells) > 5 else ""
                if actual or passed:
                    # Allow non-empty for header row check
                    if cells[1].strip() and cells[1].strip() != "ID":
                        raise AssertionError(
                            f"Row {cells[1]}: Actual='{actual}' Pass='{passed}' "
                            "must be empty until tested"
                        )


def test_acceptance_cage_crash_notes_correct() -> None:
    """P02 must reference Restart=always + RestartSec, not just KillMode."""
    content = ACCEPTANCE.read_text()
    found_p02 = False
    in_table = False
    for line in content.splitlines():
        if "|---|---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 7 and cells[1].strip() == "P02":
                found_p02 = True
                notes = cells[6].strip() if len(cells) > 6 else ""
                assert "Restart=always" in notes, (
                    f"P02 notes missing Restart=always: {notes}"
                )
                assert "RestartSec=3" in notes, (
                    f"P02 notes missing RestartSec=3: {notes}"
                )
    assert found_p02, "P02 row not found in acceptance table"


# ── gameplay input in acceptance table ────────────────────────────────────


def test_acceptance_gameplay_operations() -> None:
    """Gameplay input operations must exist in the acceptance table."""
    content = ACCEPTANCE.read_text()
    ops: list[str] = []
    in_table = False
    for line in content.splitlines():
        if "|---|---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 3 and cells[2].strip():
                ops.append(cells[2].strip())
    for item in ("Letters (a-z)", "Digits (0-9)", "Punctuation",
                 "Space", "Enter", "Backspace"):
        assert item in ops, f"Gameplay input missing from acceptance: {item}"


# ── execution lines (hook) ─────────────────────────────────────────────────


def test_acceptance_table_has_alt_f2() -> None:
    ops = _acceptance_operations()
    assert "Alt+F2" in ops, "Alt+F2 missing from acceptance table"


def test_acceptance_table_has_ctrl_alt_f1() -> None:
    ops = _acceptance_operations()
    assert "Ctrl+Alt+F1" in ops, "Ctrl+Alt+F1 missing from acceptance table"
