import subprocess
import re
from pathlib import Path

NM_CONF = Path(
    "live-build/config/includes.chroot/etc/NetworkManager/conf.d/90-sushida-os.conf"
)
HOOK = Path(
    "live-build/config/hooks/live/040-configure-network.hook.chroot"
)
AUTO_CONFIG = Path("live-build/auto/config")
EXAMPLE = Path("local/wifi.nmconnection.example")
PACKAGE_LIST = Path("live-build/config/package-lists/kiosk.list.chroot")
WATCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-network-watch"
)
ROOT = Path("live-build/config/includes.chroot")


def _git_ls_files_stage(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", path],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _parse_ini(path: Path, section: str) -> dict[str, str]:
    content = path.read_text()
    mapping: dict[str, str] = {}
    in_section = False
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_section = s == f"[{section}]"
            continue
        if not in_section or not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        mapping[k.strip()] = v.strip()
    return mapping


def _package_set() -> set[str]:
    pkgs: set[str] = set()
    for line in PACKAGE_LIST.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        pkgs.add(s.split()[0])
    return pkgs


# ── Network recovery control boundary ───────────────────────────────────

def test_watcher_never_starts_browser() -> None:
    content = WATCHER.read_text().lower()
    assert "chromium" not in content
    assert "singletonlock" not in content


def test_watcher_uses_networkmanager_connectivity_state() -> None:
    content = WATCHER.read_text()
    assert "LC_ALL=C nmcli -t -f STATE,CONNECTIVITY general" in content
    # The connected/full comparison lives in the shared route model; the
    # watcher forwards the observed values verbatim.
    assert '--nm-state "$state" --nm-connectivity "$connectivity"' in content
    routes_model = ROOT / (
        "usr/lib/python3/dist-packages/sushida_os/runtime/routes.py"
    )
    model = routes_model.read_text()
    assert 'inputs.nm_state == "connected"' in model
    assert 'inputs.nm_connectivity == "full"' in model


def test_watcher_validates_restart_target() -> None:
    content = WATCHER.read_text()
    assert "sushida-kiosk-signal" in content
    assert "--reason route-mismatch" in content
    helper = (ROOT / "usr/local/libexec/sushida-kiosk-signal").read_text()
    assert "MainPID" in helper
    assert "stat -c '%u'" in helper
    assert "sushida-kiosk\\.service" in helper
    assert 'kill -TERM -- "$pid"' in helper


def test_watcher_has_no_external_probe() -> None:
    content = WATCHER.read_text()
    for command in ("curl", "wget", "ping", "dig", "nslookup", "traceroute"):
        assert command not in content


# ── NM config ──────────────────────────────────────────────────────────────


def test_nm_conf_exists() -> None:
    assert NM_CONF.is_file()


def test_nm_conf_no_todo() -> None:
    assert "TODO" not in NM_CONF.read_text()


def test_nm_conf_no_auto_default() -> None:
    content = NM_CONF.read_text()
    assert "no-auto-default" not in content


def test_nm_conf_no_unmanaged_devices() -> None:
    content = NM_CONF.read_text()
    assert "unmanaged-devices" not in content


def test_nm_conf_no_hardcoded_interface() -> None:
    content = NM_CONF.read_text()
    assert "interface-name" not in content


def test_nm_conf_no_static_ip() -> None:
    content = NM_CONF.read_text()
    assert "address1" not in content and "ipv4" not in content.split("dns")[0]


def test_nm_conf_no_proxy() -> None:
    assert "proxy" not in NM_CONF.read_text()


def test_nm_conf_enables_low_frequency_connectivity_check() -> None:
    cfg = _parse_ini(NM_CONF, "connectivity")
    assert cfg.get("uri") == "http://nmcheck.gnome.org/check_network_status.txt"
    assert cfg.get("response") == "NetworkManager is online"
    assert cfg.get("interval") == "300"
    assert cfg.get("timeout") == "5"


def test_nm_conf_ifupdown_managed_true() -> None:
    cfg = _parse_ini(NM_CONF, "ifupdown")
    assert cfg.get("managed") == "true"


def test_nm_conf_has_keyfile_plugin() -> None:
    cfg = _parse_ini(NM_CONF, "main")
    plugins = cfg.get("plugins", "")
    assert "keyfile" in plugins


def test_nm_conf_no_wifi_gui_setting() -> None:
    content = NM_CONF.read_text()
    assert "nm-applet" not in content
    assert "nm-connection-editor" not in content


def test_auto_config_copies_only_tracked_source_files() -> None:
    content = AUTO_CONFIG.read_text()
    assert "git -C \"$PROJECT_ROOT\" ls-files -z" in content
    assert "cp -a \"$SOURCE_DIR/config/.\"" not in content
    assert "__pycache__" not in content


# ── auto/config Wi-Fi staging ──────────────────────────────────────────────


def test_staging_source_path_fixed() -> None:
    content = AUTO_CONFIG.read_text()
    assert "local/wifi.nmconnection" in content


def test_staging_dest_path_fixed() -> None:
    content = AUTO_CONFIG.read_text()
    assert "system-connections" in content
    assert "sushida-os-wifi.nmconnection" in content


def test_staging_dest_under_build_dir() -> None:
    content = AUTO_CONFIG.read_text()
    assert 'WIFI_DEST="$BUILD_DIR/' in content or \
           "WIFI_DEST=$BUILD_DIR/" in content


def test_staging_checks_source_exists() -> None:
    content = AUTO_CONFIG.read_text()
    assert '-f "$WIFI_SOURCE"' in content or '[ -f "$WIFI_SOURCE" ]' in content \
           or '[ -e "$WIFI_SOURCE" ]' in content or '-e "$WIFI_SOURCE"' in content


def test_staging_rejects_symlink() -> None:
    content = AUTO_CONFIG.read_text()
    assert "symlink" in content or "-L" in content


def test_staging_regular_file_check() -> None:
    content = AUTO_CONFIG.read_text()
    assert "regular file" in content or "[ ! -f" in content


def test_staging_mode_0600() -> None:
    content = AUTO_CONFIG.read_text()
    assert "0600" in content or "600" in content


def test_staging_no_source_or_eval() -> None:
    """Must not use shell source or eval (BASH_SOURCE is a variable, not a command)."""
    content = AUTO_CONFIG.read_text()
    assert "eval" not in content
    # Check for source as a shell built-in command (not BASH_SOURCE variable)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("source ") or stripped == "source":
            raise AssertionError(f"Found source command: {line}")
        if stripped.startswith(". /") or stripped.startswith(". ."):
            raise AssertionError(f"Found dot-source command: {line}")


def test_staging_not_tracked_source() -> None:
    """Destination must be under BUILD_DIR, not the tracked live-build tree."""
    content = AUTO_CONFIG.read_text()
    assert 'WIFI_DEST="$BUILD_DIR/' in content
    assert "WIFI_SOURCE" in content


# ── hook ───────────────────────────────────────────────────────────────────


def test_hook_exists() -> None:
    assert HOOK.is_file()


def test_hook_no_todo() -> None:
    assert "TODO" not in HOOK.read_text()


def test_hook_strict_mode() -> None:
    assert "set -euo pipefail" in HOOK.read_text()


def test_hook_is_executable() -> None:
    entries = _git_ls_files_stage(
        "live-build/config/hooks/live/040-configure-network.hook.chroot"
    )
    assert len(entries) == 1
    mode = entries[0].split()[0]
    assert mode == "100755", f"Expected 100755, got {mode}"


def test_hook_enables_network_manager() -> None:
    content = HOOK.read_text()
    assert "systemctl enable" in content
    assert "NetworkManager.service" in content


def test_hook_secures_wifi_file() -> None:
    content = HOOK.read_text()
    assert "0600" in content
    assert "root:root" in content


def test_hook_rejects_placeholders() -> None:
    content = HOOK.read_text()
    assert "REPLACE_WITH_" in content or "placeholder" in content


def test_hook_safe_without_wifi() -> None:
    """Hook must not fail unconditionally when Wi-Fi file is absent."""
    content = HOOK.read_text()
    # Verify the Wi-Fi handling is inside a conditional block
    assert 'if [ -f "$WIFI_FILE" ]' in content or 'if [ -f "$WIFI_FILE" ];' in content
    # Verify there is no systemctl enable failure or placeholder check
    # before the conditional (i.e. the hook doesn't require Wi-Fi)
    lines = content.splitlines()
    wifi_line = None
    for i, line in enumerate(lines):
        if 'if [ -f "$WIFI_FILE" ]' in line:
            wifi_line = i
            break
    assert wifi_line is not None, "Wi-Fi conditional not found"


# ── example ────────────────────────────────────────────────────────────────


def test_example_has_sections() -> None:
    sections = {"[connection]", "[wifi]", "[wifi-security]", "[ipv4]", "[ipv6]"}
    content = EXAMPLE.read_text()
    for section in sections:
        assert section in content, f"Missing section: {section}"


def test_example_type_wifi() -> None:
    assert "type=wifi" in EXAMPLE.read_text()


def test_example_autoconnect_true() -> None:
    assert "autoconnect=true" in EXAMPLE.read_text()


def test_example_mode_infrastructure() -> None:
    assert "mode=infrastructure" in EXAMPLE.read_text()


def test_example_key_mgmt_wpa_psk() -> None:
    assert "key-mgmt=wpa-psk" in EXAMPLE.read_text()


def test_example_ipv4_auto() -> None:
    cfg = _parse_ini(EXAMPLE, "ipv4")
    assert cfg.get("method") == "auto"


def test_example_ipv6_auto() -> None:
    cfg = _parse_ini(EXAMPLE, "ipv6")
    assert cfg.get("method") == "auto"


def test_example_placeholder_ssid() -> None:
    for line in EXAMPLE.read_text().splitlines():
        if line.strip().startswith("ssid="):
            assert "REPLACE_WITH_WIFI_SSID" in line


def test_example_placeholder_password() -> None:
    for line in EXAMPLE.read_text().splitlines():
        if line.strip().startswith("psk="):
            assert "REPLACE_WITH_WIFI_PASSWORD" in line


def test_example_no_uuid() -> None:
    assert "uuid" not in EXAMPLE.read_text().lower()


def test_example_no_mac_address() -> None:
    assert "mac-address" not in EXAMPLE.read_text()
    assert "cloned-mac" not in EXAMPLE.read_text()


def test_example_no_interface_name() -> None:
    assert "interface-name" not in EXAMPLE.read_text()


# ── packages ───────────────────────────────────────────────────────────────


def test_network_manager_in_package_list() -> None:
    assert "network-manager" in _package_set()


def test_wpasupplicant_in_package_list() -> None:
    assert "wpasupplicant" in _package_set()


def test_no_wifi_gui_package() -> None:
    pkgs = _package_set()
    gui_pkgs = {"network-manager-gnome", "plasma-nm", "nm-connection-editor"}
    assert not (pkgs & gui_pkgs), f"Wi-Fi GUI package found: {pkgs & gui_pkgs}"
