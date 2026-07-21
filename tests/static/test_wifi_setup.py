"""First-boot Wi-Fi provisioning and isolated persistence boundaries."""

from pathlib import Path


ROOT = Path("live-build/config/includes.chroot")
LAUNCHER = ROOT / "usr/local/bin/sushida-launch"
SESSION = ROOT / "usr/local/libexec/sushida-session"
WATCHER = ROOT / "usr/local/bin/sushida-network-watch"
BACKEND = ROOT / "usr/local/libexec/sushida-wifi-setup"
BACKEND_PACKAGE = ROOT / "usr/lib/python3/dist-packages/sushida_os/wifi"
MOUNT_UNIT = ROOT / r"etc/systemd/system/var-lib-sushida\x2dconfig.mount"
PREPARE_UNIT = ROOT / "etc/systemd/system/sushida-config-prepare.service"
SETUP_UNIT = ROOT / "etc/systemd/system/sushida-wifi-setup.service"
POLKIT = ROOT / "etc/polkit-1/rules.d/60-sushida-wifi-setup.rules"
POLICY = ROOT / "etc/chromium/policies/managed/sushida-os.json"
ACCOUNT_HOOK = Path(
    "live-build/config/hooks/live/010-create-kiosk-user.hook.chroot"
)
ENABLE_HOOK = Path(
    "live-build/config/hooks/live/020-enable-services.hook.chroot"
)
PACKAGES = Path("live-build/config/package-lists/kiosk.list.chroot")
BUILD = Path("scripts/build.sh")
VERIFY = Path("scripts/verify-iso.sh")


def _backend_text() -> str:
    """All Wi-Fi backend implementation sources (entrypoint + package)."""
    parts = [BACKEND.read_text()]
    if BACKEND_PACKAGE.is_dir():
        for path in sorted(BACKEND_PACKAGE.glob("*.py")):
            parts.append(path.read_text())
    return "\n".join(parts)


def test_setup_uses_dedicated_unprivileged_account() -> None:
    text = ACCOUNT_HOOK.read_text()
    assert 'SETUP_USER="wifi-setup"' in text
    assert "--no-create-home" in text
    assert "/usr/sbin/nologin" in text
    assert 'passwd -l "$SETUP_USER"' in text
    assert "wifi-setup" not in next(
        line for line in text.splitlines() if line.startswith("KIOSK_GROUPS=")
    )


def test_setup_has_only_explicit_networkmanager_polkit_actions() -> None:
    text = POLKIT.read_text()
    assert 'subject.user == "wifi-setup"' in text
    for action in (
        "org.freedesktop.NetworkManager.network-control",
        "org.freedesktop.NetworkManager.settings.modify.system",
        "org.freedesktop.NetworkManager.enable-disable-wifi",
    ):
        assert action in text
    assert "org.freedesktop.NetworkManager.*" not in text
    assert "polkit.Result.YES" in text


def test_config_partition_mount_is_narrow_and_non_executable() -> None:
    text = MOUNT_UNIT.read_text()
    # Mounting by the fixed filesystem UUID is robust against another
    # medium accidentally carrying the SUSHIDA-CFG label (BL-04).  With a
    # public repository neither identifier is a secret; this is collision
    # robustness, not tamper-proofing.
    assert "What=/dev/disk/by-uuid/3b8c6880-2a56-4cb2-9a30-b7ac47fc29f1" in text
    build = Path("scripts/build.sh").read_text()
    assert "-U 3b8c6880-2a56-4cb2-9a30-b7ac47fc29f1" in build
    assert "Where=/var/lib/sushida-config" in text
    for option in ("rw", "nodev", "nosuid", "noexec", "noatime"):
        assert option in text
    assert "Before=sushida-config-prepare.service" in text
    assert "ConditionPathExists=" not in text
    assert "JobTimeoutSec=20s" in text


def test_prepare_service_does_not_make_mount_mandatory_for_boot() -> None:
    text = PREPARE_UNIT.read_text()
    assert "Wants=var-lib-sushida\\x2dconfig.mount" in text
    assert "After=var-lib-sushida\\x2dconfig.mount" in text
    assert "Requires=var-lib-sushida\\x2dconfig.mount" not in text
    assert "Type=oneshot" in text
    assert "RuntimeDirectory=sushida-config" in text
    assert "RuntimeDirectoryMode=0755" in text
    assert "/run/sushida-os" not in text


def test_storage_status_is_independent_of_kiosk_runtime_lifecycle() -> None:
    backend = _backend_text()
    prepare = (
        ROOT / "usr/local/libexec/sushida-config-prepare"
    ).read_text()
    assert 'STORAGE_STATUS = Path("/run/sushida-config/config-storage")' in backend
    assert 'STATUS_DIR="/run/sushida-config"' in prepare
    assert 'STATUS_DIR="/run/sushida-os"' not in prepare


def test_setup_backend_is_loopback_only_and_hardened() -> None:
    text = SETUP_UNIT.read_text()
    assert "User=wifi-setup" in text
    assert "Group=wifi-setup" in text
    assert "NoNewPrivileges=true" in text
    assert "CapabilityBoundingSet=" in text
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=true" in text
    assert "PrivateTmp=true" in text
    assert "IPAddressDeny=any" in text
    assert "IPAddressAllow=localhost" in text
    assert "ReadWritePaths=/var/lib/sushida-config" in text
    assert "RuntimeDirectoryPreserve=restart" in text


def test_backend_constrains_http_and_persists_atomically() -> None:
    text = _backend_text()
    assert 'HOST = "127.0.0.1"' in text
    assert "MAX_REQUEST_BYTES" in text
    assert "csrf" in text.lower()
    assert "hmac.compare_digest" in text
    assert "html.escape" in text
    assert "shell=True" not in text
    assert "os.replace" in text
    assert "os.fsync" in text
    assert "SUSHIDA-CFG" in text
    assert "setup.json" in text
    assert "csrf-token" in text
    assert "os.O_NOFOLLOW" in text
    assert 'stat.S_IMODE(info.st_mode) != 0o600' in text
    assert 'b"Forbidden"' not in text
    assert "with CONNECT_LOCK:" in text
    assert 'errors="replace"' in text
    assert 'pass_fds=tuple(pass_fds)' in text
    assert "TemporaryFile" in text
    assert "802-11-wireless-security.psk:" in text
    assert '"connection", "add"' in text
    assert '"connection", "load"' not in text
    assert '"passwd-file"' in text
    assert "--" + "ask" not in text
    assert "classify_security" in text
    for unsupported in ("wep", "enterprise", "owe", "unsupported"):
        assert f'"{unsupported}"' in text
    assert "_wifi_reason" in text
    for reason in ("(5, 15, 16, 17)", "== 7", "(8, 9, 10, 11)", "== 35", "== 53"):
        assert reason in text
    assert "stage=" in text
    assert "nmcli_exit=" in text
    assert "reason=" in text
    assert 'command.extend(["password", password])' not in text
    assert '"802-11-wireless-security.psk-flags", "0"' in text
    assert '"802-11-wireless-security.key-mgmt", "wpa-psk"' in text
    assert "REQUEST_READ_TIMEOUT_SECONDS" in text
    assert "self.connection.settimeout" in text
    assert 'self.send_header("Referrer-Policy", "same-origin")' in text
    assert 'self.send_header("Referrer-Policy", "no-referrer")' not in text
    assert "if origin == ORIGIN:" in text
    assert "if origin is not None:" in text
    assert "managed_wifi_active()" in text
    assert "saved is None or network_connected()" not in text


def test_setup_ui_avoids_wayland_popup_and_rescans_via_home_route() -> None:
    text = _backend_text()
    assert '<input type="radio" name="ssid"' in text
    assert "<select" not in text
    assert 'action="/"' in text
    assert "urlsplit(self.path)" in text
    assert 'http-equiv="refresh"' not in text


def test_connection_request_is_asynchronous_and_response_ordered() -> None:
    """The POST must be answered before NetworkManager is touched.

    A synchronous nmcli run inside the POST handler aborts the in-flight
    request with ERR_NETWORK_CHANGED when the interface comes up, which used
    to strand the kiosk on a browser error page.  The backend therefore
    queues the credential, completes the response, and only then wakes a
    single serialized worker.
    """
    text = _backend_text()
    assert 'enqueue_interactive(ssid[0], password[0])' in text
    assert "success, message = connect_wifi(ssid[0], password[0])" not in text
    assert "_request_event.set()" in text
    assert "_connect_worker" in text
    assert "threading.Thread(target=_connect_worker, daemon=True).start()" in text
    assert "def enqueue_interactive" in text
    assert "def connect_status()" in text
    assert "def consume_failure()" in text
    assert "def reset_succeeded()" in text
    assert '"/status.json"' in text
    assert 'fetch("/status.json"' in text
    assert "location.reload()" in text
    # The poller never navigates while the network interface changes; only a
    # terminal state reloads the page, after the worker has settled.
    assert 'data.state === "connecting"' in text
    assert 'data.state === "succeeded"' in text
    # The inline poller script is authorized by exact hash, not 'unsafe-inline'.
    assert "script-src 'sha256-" in text
    assert "script-src 'unsafe-inline'" not in text
    assert "def script_csp_hash()" in text
    assert "base64.b64encode(digest)" in text
    # Duplicate submissions are refused without storing the credential.
    assert "HTTPStatus.CONFLICT" in text
    # Public status never carries the SSID or password.
    assert 'data["password"]' not in text
    assert '{"state": state, "message": message}' in text


def test_storage_failure_does_not_disable_wifi_connection() -> None:
    text = _backend_text()
    assert 'connected or not storage_ready or not networks' not in text
    assert '<fieldset class="networks" disabled' not in text
    assert 'name="password" type="password" disabled' not in text
    assert "この起動中だけ接続" in text


def test_connected_state_does_not_disable_or_skip_wifi_setup() -> None:
    text = _backend_text()
    assert "networks = [] if success else scan_networks()" in text
    assert "networks = [] if connected" not in text
    assert "すでにネットワークへ接続されています。" not in text


def test_image_validator_imports_backend_standard_library() -> None:
    validator = Path(
        "live-build/config/hooks/live/090-validate-image.hook.chroot"
    ).read_text()
    for module in ("hmac", "http.server", "secrets", "urllib.parse"):
        assert module in validator


def test_launcher_waits_bounded_then_selects_setup() -> None:
    text = LAUNCHER.read_text()
    assert 'SETUP_URL="http://127.0.0.1:8787/"' in text
    assert "NETWORK_SETUP_GRACE_SECONDS" in text
    assert "15" in text
    assert 'ACTIVE_ROUTE="setup"' in text
    assert "nmcli -t -f STATE,CONNECTIVITY general" in text


def test_setup_origin_is_allowed_at_both_browser_layers() -> None:
    setup_url = "http://127.0.0.1:8787/"
    assert setup_url in SESSION.read_text()
    assert '"http://127.0.0.1:8787"' in POLICY.read_text()
    assert "http://127.0.0.1:8787/*" not in POLICY.read_text()


def test_watcher_transitions_between_setup_and_online() -> None:
    text = WATCHER.read_text()
    assert "online|setup" in text
    assert "sushida_os.runtime.routes" in text
    assert "--setup-active" in text
    assert "sushida-wifi-setup.service" in text
    assert "MIN_INTERVAL=30" in text
    assert "sushida-kiosk-signal" in text
    signal_helper = (
        ROOT / "usr/local/libexec/sushida-kiosk-signal"
    ).read_text()
    assert "kill -TERM" in signal_helper


def test_services_and_required_packages_are_enabled() -> None:
    hook = ENABLE_HOOK.read_text()
    assert "sushida-config-prepare.service" in hook
    assert "sushida-wifi-setup.service" in hook
    assert "sushida-network-watch.service" in hook
    setup_unit = SETUP_UNIT.read_text()
    assert "Restart=always" in setup_unit
    assert "PartOf=sushida-kiosk.service" not in setup_unit
    packages = PACKAGES.read_text()
    assert "polkitd" in packages


def test_build_appends_fixed_size_config_filesystem() -> None:
    text = BUILD.read_text()
    assert "SUSHIDA-CFG" in text
    assert "64M" in text
    assert "mkfs.ext4" in text
    assert "-append_partition 3 0x83" in text
    assert "-boot_image any replay" in text


def test_verifier_checks_config_partition_not_just_iso_files() -> None:
    text = VERIFY.read_text()
    assert "SUSHIDA-CFG" in text
    assert "Appended3" in text
    assert "131072" in text
    assert "blkid" in text
